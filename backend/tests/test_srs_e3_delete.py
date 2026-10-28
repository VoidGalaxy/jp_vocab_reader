"""Gate E-3 pre-review (E-D1, NOT approved): what deleting personal cards does today.

One synthetic scenario, run on a session-only SQLite file (always) and -- only with the
E-1 harness opt-in -- on the protected local PostgreSQL test database through the E-2
adapter. It deletes one word at a time (a normal new card, a past-learning-marked card, a
migrated card with a snapshot) and then a whole deck, and observes, before and after each
step:

- personal log counts per card and per account, the subscribed (lexeme) log count;
- today's / an earlier day's new-card count, the remaining daily goal, the history calendar;
- the deletion ledger with its past-learning evidence, receipts, migration snapshots,
  identity findings;
- CONTRACT 3-3 invariants I1..I6 (I3 per engine);
- on PostgreSQL, the real catalog row of every foreign key on review_logs (by columns and
  delete action, not by name).

Nothing here changes product code, schema or data outside the scenario's own synthetic
accounts. It does not implement or bypass E-D1: the PostgreSQL comparison is marked as an
expected failure while the CASCADE is there, so a future change shows up as an
"unexpected success" to be reviewed, never silently.

Run (SQLite part):  python tests/test_srs_e3_delete.py
E3_OUT=<file.json> writes the observations (no ids, no secrets) for the report.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
import _srs_pg_harness as harness  # noqa: E402

UTC = cmp.UTC
DAY = timedelta(days=1)
T0 = cmp.T0  # 2026-06-01 12:00 KST
TODAY = T0 + timedelta(hours=1)
EARLIER = T0 - 2 * DAY + timedelta(hours=1)
STEPS = (("word_new_today", "n1"), ("word_history_marked", "h1"), ("word_migrated", "m1"), ("deck_bulk", None))


class DeleteScenario:
    def __init__(self, sc: cmp.Scenario) -> None:
        self.sc = sc
        self.ids: dict[str, int] = {}
        self.decks: dict[str, int] = {}

    # ---- inputs ---------------------------------------------------------------
    def add_card(self, user: int, label: str, deck: int | None = None) -> int:
        body = {"surface": label, "base_form": label, "reading": f"{label}-r", "meaning_ko": f"{label}-m",
                "status": "unknown"}
        if deck is not None:
            body["deck_id"] = deck
        response = self.sc.client.post("/vocab-items", headers=self.sc.headers(user), json=body)
        assert response.status_code == 200, response.status_code
        ident = int(response.json()["id"])
        rows = self.sc.sql("SELECT user_id, deck_id FROM vocab_items WHERE id = ?", (ident,))
        assert rows and rows[0]["user_id"] == user and (deck is None or rows[0]["deck_id"] == deck)
        self.sc.labels.put("personal", ident, label, owner=self.sc.labels.name("user", user))
        self.ids[label] = ident
        return ident

    def build(self) -> None:
        from app.repositories.lexeme_repository import add_word_to_shared_deck, get_or_create_subscription, upsert_lexeme
        from app.srs import migration
        from app.srs.engine import CardKey

        sc = self.sc
        sc.clock = T0 - 10 * DAY
        self.A, self.B = sc.user("da"), sc.user("db")
        sc.set_mode(self.A, "legacy")
        h1, m1 = self.add_card(self.A, "h1"), self.add_card(self.A, "m1")
        # past learning without any log (legacy counters only): the U4 past-learning mark
        sc.sql("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, review_level = 2 WHERE id = ?",
               ((T0 - 5 * DAY).isoformat(), h1))
        sc.clock = T0 - 8 * DAY
        sc.review(self.A, m1, "good", legacy=True)
        sc.clock = T0 - 3 * DAY
        sc.set_mode(self.A, "fsrs")
        plan = migration.dry_run([CardKey("personal", self.A, h1), CardKey("personal", self.A, m1)])
        self.migration = [r["result"] for r in migration.apply_plan(plan, "e3-run-1", approved=True)]
        sc.clock = T0 - 2 * DAY
        n1, n2 = self.add_card(self.A, "n1"), self.add_card(self.A, "n2")
        deck = sc.client.post("/decks", headers=sc.headers(self.A), json={"name": "e3-bulk"})
        assert deck.status_code == 200, deck.status_code
        self.decks["bulk"] = int(deck.json()["id"])
        b1, b2 = self.add_card(self.A, "b1", self.decks["bulk"]), self.add_card(self.A, "b2", self.decks["bulk"])
        sc.clock = EARLIER
        for ref in (n2, b2, m1):
            assert sc.review(self.A, ref, "good")["status"] == 200
        sc.clock = TODAY
        for ref in (n1, n2, b1):
            assert sc.review(self.A, ref, "good")["status"] == 200
        sc.set_mode(self.B, "fsrs")
        x1 = self.add_card(self.B, "x1")
        assert sc.review(self.B, x1, "good")["status"] == 200
        # a subscribed word of A in a deck B owns (legacy-format lexeme review)
        with mock.patch.object(sc, "clock", TODAY):
            pass
        shared = sc.sql("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, "
                        "updated_at) VALUES (?, 'e3-shared', '', 'public', ?, ?) RETURNING id",
                        (self.B, T0.isoformat(), T0.isoformat()))[0]["id"]
        lexeme = upsert_lexeme("e3-lx", "e3-lx")
        add_word_to_shared_deck(shared, lexeme, 1)
        get_or_create_subscription(self.A, shared)
        self.shared, self.lexeme = shared, lexeme
        response = sc.client.post(f"/shared-decks/{shared}/words/{lexeme}/review", headers=sc.headers(self.A),
                                  json={"rating": "good", "request_id": "e3-lx-1", "session_id": "e3",
                                        "expected_card_version": None})
        assert response.status_code == 200, response.text[:200]

    # ---- observations ---------------------------------------------------------
    def label_of(self, ident: int) -> str:
        for label, value in self.ids.items():
            if value == ident:
                return label
        return "<not a scenario card>"

    def observe(self) -> dict:
        from app.database import get_connection
        from app.srs import goals, identity

        sc, A, B = self.sc, self.A, self.B
        out: dict = {}
        out["cards_present"] = sorted(l for l, i in self.ids.items()
                                      if sc.sql("SELECT 1 AS x FROM vocab_items WHERE id = ?", (i,)))
        out["logs_by_card"] = {l: sc.count("review_logs", "WHERE vocab_item_id = ?", (i,)) for l, i in sorted(self.ids.items())}
        out["logs_A"] = sc.count("review_logs", "WHERE user_id = ?", (A,))
        out["logs_B"] = sc.count("review_logs", "WHERE user_id = ?", (B,))
        out["lexeme_logs_A"] = sc.count("lexeme_review_logs", "WHERE user_id = ?", (A,))
        with get_connection() as c:
            out["introduced"] = {name: goals.introduction_count(c, A, at).as_dict()
                                 for name, at in (("today", TODAY), ("earlier", EARLIER))}
        sc.clock = TODAY + timedelta(minutes=30)
        queue = sc.client.get("/study-queue", headers=sc.headers(A))
        out["new_goal"] = queue.json().get("new_goal") if queue.status_code == 200 else queue.status_code
        # The calendar has two sources: review counts / ratings come from the logs; the
        # saved-word count comes from the cards that still exist (by design, both engines).
        reviews, saved = {}, {}
        for month in ("2026-05", "2026-06"):
            r = sc.client.get("/stats/history", headers=sc.headers(A), params={"month": month})
            assert r.status_code == 200, r.status_code
            for d in r.json().get("days", []):
                if d.get("review_count"):
                    reviews[d["date"]] = {"review_count": d["review_count"], "ratings": d.get("ratings")}
                if d.get("saved_word_count"):
                    saved[d["date"]] = d["saved_word_count"]
        out["history_reviews"], out["history_saved_words"] = reviews, saved
        out["ledger"] = [{"card": self.label_of(r["card_ref"]), "history_intro_status": r["history_intro_status"],
                          "history_intro_known_by": r["history_intro_known_by"]}
                         for r in sc.sql("SELECT card_ref, history_intro_status, history_intro_known_by FROM "
                                         "srs_card_deletions WHERE user_id = ? ORDER BY id", (A,))]
        receipts = sc.sql("SELECT r.card_ref, r.review_log_id, l.id AS log_found FROM srs_review_receipts r "
                          "LEFT JOIN review_logs l ON l.id = r.review_log_id WHERE r.user_id = ? "
                          "AND r.card_kind = 'personal' ORDER BY r.id", (A,))  # lexeme receipts: lexeme logs
        out["receipts"] = {"count": len(receipts),
                           "log_ref_dangling": sorted(self.label_of(r["card_ref"]) for r in receipts
                                                      if r["review_log_id"] is not None and r["log_found"] is None)}
        snaps = sc.sql("SELECT card_ref, legacy_json FROM srs_migration_snapshots WHERE user_id = ? ORDER BY id", (A,))
        dangling = []
        for s in snaps:
            last = json.loads(s["legacy_json"]).get("last_log_id")
            if isinstance(last, int) and last and not sc.sql("SELECT 1 AS x FROM review_logs WHERE id = ?", (last,)):
                dangling.append(self.label_of(s["card_ref"]))
        out["snapshots"] = {"count": len(snaps), "last_log_dangling": sorted(dangling)}
        with get_connection() as c:
            findings = identity.scan_identity(c).findings
        out["identity_findings_A"] = len([f for f in findings if getattr(f, "user_id", None) == A])
        out["invariants"] = self.invariants()
        return out

    def invariants(self) -> dict:
        sc, A = self.sc, self.A
        orphan = sc.sql("SELECT l.vocab_item_id AS ref FROM review_logs l LEFT JOIN vocab_items v ON v.id = l.vocab_item_id "
                        "WHERE l.user_id = ? AND v.id IS NULL", (A,))
        ledger = {r["card_ref"] for r in sc.sql("SELECT card_ref FROM srs_card_deletions WHERE user_id = ? AND "
                                                "card_kind = 'personal'", (A,))}
        i1 = sorted({self.label_of(r["ref"]) for r in orphan if r["ref"] not in ledger})
        i2 = sc.count("review_logs l JOIN vocab_items v ON v.id = l.vocab_item_id", "WHERE l.user_id <> v.user_id")
        refs = [r["m"] or 0 for r in sc.sql(
            "SELECT MAX(id) AS m FROM vocab_items UNION ALL SELECT MAX(vocab_item_id) FROM review_logs "
            "UNION ALL SELECT MAX(card_ref) FROM srs_card_deletions UNION ALL "
            "SELECT MAX(card_ref) FROM srs_review_receipts WHERE card_kind = 'personal' UNION ALL "
            "SELECT MAX(card_ref) FROM srs_migration_snapshots WHERE card_kind = 'personal'")]
        if self.sc.engine == "postgresql":
            seq = sc.sql("SELECT last_value AS v FROM vocab_items_id_seq")[0]["v"]
        else:
            rows = sc.sql("SELECT seq AS v FROM sqlite_sequence WHERE name = 'vocab_items'")
            seq = rows[0]["v"] if rows else 0
        i5 = sc.count("srs_review_receipts r LEFT JOIN review_logs l ON l.id = r.review_log_id",
                      "WHERE r.user_id = ? AND r.card_kind = 'personal' AND r.review_log_id IS NOT NULL "
                      "AND l.id IS NULL", (A,)) + \
            sc.count("vocab_items v LEFT JOIN review_logs l ON l.id = v.evidence_from_log_id",
                     "WHERE v.user_id = ? AND v.evidence_from_log_id IS NOT NULL AND l.id IS NULL", (A,))
        return {"I1_orphan_logs_without_ledger": i1, "I2_log_card_account_mismatch": i2,
                "I3_sequence_at_least_max_ref": int(seq >= max(refs)), "I5_dangling_log_refs": i5}

    def fk_catalog(self) -> list[dict]:
        if self.sc.engine != "postgresql":
            return [{"engine": "sqlite", "note": "review_logs has no FOREIGN KEY (PRAGMA foreign_key_list)",
                     "rows": len(self.sc.sql("PRAGMA foreign_key_list(review_logs)"))}]
        rows = self.sc.sql(
            "SELECT c.conname, a.attname AS col, rt.relname AS ref_table, ra.attname AS ref_col, c.confdeltype, "
            "c.convalidated, c.condeferrable FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey) "
            "JOIN pg_attribute ra ON ra.attrelid = c.confrelid AND ra.attnum = ANY (c.confkey) "
            "WHERE c.contype = 'f' AND n.nspname = 'public' AND t.relname = 'review_logs' ORDER BY a.attname")
        actions = {"c": "CASCADE", "n": "SET NULL", "r": "RESTRICT", "a": "NO ACTION", "d": "SET DEFAULT"}
        return [{"column": r["col"], "references": f"{r['ref_table']}({r['ref_col']})",
                 "on_delete": actions.get(r["confdeltype"], r["confdeltype"]), "validated": bool(r["convalidated"]),
                 "deferrable": bool(r["condeferrable"]), "name": r["conname"]} for r in rows]

    def run(self, old_schema: bool = False) -> dict:
        """old_schema (PostgreSQL only): build the data under the pre-change schema (card FK
        ON DELETE CASCADE), then run the real upgrade, then delete."""
        sc = self.sc
        upgrade = {}
        if old_schema:
            import _srs_e2_adapter as adapter
            from test_srs_e3_fk_real import old_schema as build_old

            sc.run.track_creation(adapter.schema_step(build_old), expected=adapter.expected_schema_tables())
            self.build()
            upgrade["fk_before_upgrade"] = self.fk_catalog()
            before = self.observe()
            sc.run.track_creation(adapter.schema_step(), expected=set())
            upgrade["observed_unchanged_by_upgrade"] = int(self.observe() == before)
        else:
            sc.stage_upgrade()
            self.build()
        out = {"engine": sc.engine, "migration": self.migration, "fk_review_logs": self.fk_catalog(),
               "upgrade": upgrade, "steps": {"before": self.observe()}}
        for step, label in STEPS:
            sc.clock = TODAY + timedelta(minutes=10)
            if label:
                r = sc.client.delete(f"/vocab-items/{self.ids[label]}", headers=sc.headers(self.A))
            else:
                r = sc.client.delete(f"/decks/{self.decks['bulk']}", headers=sc.headers(self.A))
            observed = self.observe()
            observed["delete_status"] = r.status_code
            out["steps"][step] = observed
        return out


def run_sqlite(path: str) -> dict:
    with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{path}", "APP_ENV": "test"}):
        with cmp.Scenario("sqlite") as sc:
            return DeleteScenario(sc).run()


def run_postgres(run, old_schema: bool = False) -> dict:
    import _srs_e2_adapter as adapter

    with adapter.app_scope(run):
        with cmp.Scenario("postgresql", run) as sc:
            return DeleteScenario(sc).run(old_schema=old_schema)


def _write(name: str, value: dict) -> None:
    target = os.environ.get("E3_OUT")
    if target:
        path = Path(target)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data[name] = value
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def assert_kept(case: unittest.TestCase, out: dict) -> None:
    """Card deletion keeps logs (I6), the account's per-date new-card results with their
    status / lower bound, the remaining daily goal and the calendar's review counts (I7),
    other accounts' and subscribed logs, receipt / snapshot log references and I1 / I2 /
    I3 / I5. Saved-word counts and remaining cards are not I7 (they follow live cards)."""
    steps = out["steps"]
    before = steps["before"]
    goal_keys = ("introduced_today", "introduced_today_status", "introduced_today_at_least", "account_remaining")
    for name, observed in steps.items():
        with case.subTest(engine=out["engine"], step=name):
            if name != "before":
                case.assertIn(observed["delete_status"], (200, 204))
            case.assertEqual(observed["logs_A"], before["logs_A"])
            case.assertEqual(observed["logs_by_card"], before["logs_by_card"])
            case.assertEqual(observed["introduced"], before["introduced"])
            case.assertEqual({k: observed["new_goal"][k] for k in goal_keys}, {k: before["new_goal"][k] for k in goal_keys})
            case.assertEqual(observed["history_reviews"], before["history_reviews"])
            case.assertEqual((observed["logs_B"], observed["lexeme_logs_A"]), (before["logs_B"], before["lexeme_logs_A"]))
            case.assertEqual((observed["receipts"]["log_ref_dangling"], observed["snapshots"]["last_log_dangling"]), ([], []))
            inv = observed["invariants"]
            case.assertEqual((inv["I1_orphan_logs_without_ledger"], inv["I2_log_card_account_mismatch"],
                              inv["I3_sequence_at_least_max_ref"], inv["I5_dangling_log_refs"]), ([], 0, 1, 0))
    ledger = steps["deck_bulk"]["ledger"]
    case.assertEqual(([e["card"] for e in ledger[:3]], sorted(e["card"] for e in ledger[3:])),
                     (["n1", "h1", "m1"], ["b1", "b2"]))  # one statement per deck
    case.assertEqual([(e["history_intro_status"], e["history_intro_known_by"]) for e in ledger[1:3]],
                     [("before_tracking", "2026-05-27"), ("logged", None)])  # past-learning evidence kept


class SqliteDeleteTests(unittest.TestCase):
    """The approved SQLite behaviour (U3/U4/U9/U10): logs stay, evidence stays."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e3_", ignore_cleanup_errors=True)
        cls.out = run_sqlite((Path(cls.directory.name) / "e3.db").as_posix())
        _write("sqlite", cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_logs_and_aggregates_survive_card_deletion(self):
        assert_kept(self, self.out)
        self.assertEqual(self.out["fk_review_logs"][0]["rows"], 0)


def _opt_in() -> bool:
    try:
        return harness.requested(os.environ) is not None
    except harness.UnsafePostgresTarget:
        return True


@unittest.skipUnless(_opt_in(), "Real PostgreSQL delete reproduction NOT RUN (opt-in not set)")
class PostgresDeleteReproduction(unittest.TestCase):
    """E-3 (E-D1 A approved): on the protected local test database, a new schema and an
    upgraded pre-change schema must both behave like SQLite.

    Changed 2026-10-18 with the approved fix: the former `expectedFailure` comparison is now
    a normal check, and the former "exactly one CASCADE card FK" check is split into the new
    schema (none) and the upgraded old schema (one CASCADE FK before, none after)."""

    @classmethod
    def setUpClass(cls):
        cls.pg = {}
        for name, old in (("new_schema", False), ("upgraded_old_schema", True)):
            run = harness.PgRun(harness.requested(os.environ))
            run.start()
            try:
                cls.pg[name] = run_postgres(run, old_schema=old)
            finally:
                run.teardown()
            _write(f"postgresql_{name}", cls.pg[name])
        with tempfile.TemporaryDirectory(prefix="jp_vocab_e3_", ignore_cleanup_errors=True) as d:
            cls.sqlite = run_sqlite((Path(d) / "e3.db").as_posix())

    @staticmethod
    def card_fks(catalog):
        return [f for f in catalog if f["column"] == "vocab_item_id"]

    def test_card_fk_absent_new_and_dropped_on_upgrade(self):
        self.assertEqual(self.card_fks(self.pg["new_schema"]["fk_review_logs"]), [])
        old = self.pg["upgraded_old_schema"]
        before = self.card_fks(old["upgrade"]["fk_before_upgrade"])
        self.assertEqual([(f["references"], f["on_delete"], f["deferrable"]) for f in before],
                         [("vocab_items(id)", "CASCADE", False)])
        self.assertEqual(self.card_fks(old["fk_review_logs"]), [])
        for out in self.pg.values():  # the account FK stays
            self.assertEqual([(f["column"], f["references"], f["on_delete"]) for f in out["fk_review_logs"]],
                             [("user_id", "users(id)", "CASCADE")])
        self.assertEqual(old["upgrade"]["observed_unchanged_by_upgrade"], 1)

    def test_logs_aggregates_and_references_kept(self):
        for out in self.pg.values():
            assert_kept(self, out)

    def test_postgresql_matches_sqlite_after_deletions(self):
        drop = {"fk_review_logs", "engine", "upgrade"}
        for name, out in self.pg.items():
            with self.subTest(schema=name):
                self.assertEqual(cmp.compare({k: v for k, v in self.sqlite.items() if k not in drop},
                                             {k: v for k, v in out.items() if k not in drop}), [])


if __name__ == "__main__":
    unittest.main()
