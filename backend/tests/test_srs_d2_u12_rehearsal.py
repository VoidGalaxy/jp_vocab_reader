"""Gate D-2 U12: one continuous synthetic rehearsal of U1~U11 on the same synthetic
accounts and cards (A = main flow, B = account-separation control, L = legacy control,
O = owner of the shared decks).

The flow starts from the pre-SRS SQLite structure (no SRS tables or columns), upgrades
it, and then runs every approved step in order through the real repository functions,
the real HTTP endpoints (FastAPI TestClient) and the operator tools. Time moves only
through one controlled server clock (every module's `now_utc`); no stored log time is
rewritten to stand in for a normal step and no QA hook is added to the product.

Each step records what it compares in `self.steps` (ids, counts, versions, states,
fingerprints only -- no card text, token or JSON value). Set U12_OUT=<path> to write
that table to a JSON file.

Synthetic SQLite only (a throwaway file under a temporary directory). Synthetic
schedules are not evidence of a learning effect or of real recall.

Run directly:      python tests/test_srs_d2_u12_rehearsal.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import race_support  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import app.database as database  # noqa: E402
from app import main  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.database import compute_review_schedule, get_connection  # noqa: E402
from app.repositories import (  # noqa: E402
    learning_plan_repository, lexeme_repository, stats_history_repository, stats_repository, vocab_repository,
)
from app.repositories.lexeme_repository import add_word_to_shared_deck, get_or_create_subscription, upsert_lexeme  # noqa: E402
from app.repositories.user_repository import create_user  # noqa: E402
from app.srs import identity, migration, queue, restoration, reviews  # noqa: E402
from app.srs.completion import DRAFT_METRIC_VERSION, METRIC_VERSION  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

import d2_snapshot_minimize  # noqa: E402
import d2_snapshot_prune  # noqa: E402

UTC = timezone.utc
DAY = timedelta(days=1)
# 12:00 KST, the rehearsal's first migration day. U12_T0 (ISO) moves the whole timeline, e.g.
# to seed a database for a live server whose real clock must be after the last review.
T0 = datetime.fromisoformat(os.environ["U12_T0"]) if os.environ.get("U12_T0") else datetime(2026, 6, 1, 3, 0, tzinfo=UTC)
SECRET = "u12-rehearsal-synthetic-secret-not-a-real-key"
CLOCKED = (database, reviews, migration, queue, vocab_repository, lexeme_repository, stats_repository,
           stats_history_repository, learning_plan_repository)
CARD_COLS = ("srs_engine", "srs_card_version", "srs_state", "srs_stability", "srs_effective_due_at", "srs_participation",
             "srs_history_quality", "evidence_from_log_id", "history_intro_status", "completion_metric_version",
             "first_completed_at", "first_completed_source", "version_first_completed_at",
             "version_first_completed_version", "review_level", "next_review_at")


def iso(value):
    return value.isoformat()


class Rehearsal(unittest.TestCase):
    # ------------------------------------------------------------------ setup ----
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_u12_", dir=BACKEND)
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "qa_u12_synthetic.db"
        env = mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}", "APP_ENV": "test",
                                           "JWT_SECRET_KEY": SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.clock = T0 - 400 * DAY
        for module in CLOCKED:
            patch = mock.patch.object(module, "now_utc", side_effect=lambda: self.clock)
            patch.start()
            self.addCleanup(patch.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.steps = []
        self.req = 0
        self.versions = {}

    def record(self, step, **facts):
        self.steps.append(dict(step=step, **facts, cards=self.checkpoint()))

    def has_table(self, name):
        return bool(self.sql("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)))

    def checkpoint(self):
        """Card versions never go down; per tracked card: version, engine, state, boundary,
        completion source, log count, receipt count (no content)."""
        if not hasattr(self, "c"):
            return {}
        tracked = dict(self.c, **{k: getattr(self, k) for k in ("new", "copy_card") if hasattr(self, k)})
        out = {}
        for name, ref in tracked.items():
            user = self.B if name == "b" else self.L if name == "l" else self.A
            row = self.card("personal", ref, user)
            logs = self.logs("personal", ref)
            receipts = (self.sql("SELECT id FROM srs_review_receipts WHERE card_kind = 'personal' AND card_ref = ?", (ref,))
                        if self.has_table("srs_review_receipts") else [])
            entry = {"exists": row is not None, "logs": len(logs), "receipts": len(receipts)}
            if row is not None:
                entry.update(version=row.get("srs_card_version"), engine=row.get("srs_engine"), state=row.get("srs_state"),
                             boundary=row.get("evidence_from_log_id"), source=row.get("first_completed_source"),
                             v3=row.get("version_first_completed_version"))
                previous = self.versions.get(name)
                if previous is not None and entry["version"] is not None:
                    self.assertGreaterEqual(entry["version"], previous, name)
                if entry["version"] is not None:
                    self.versions[name] = entry["version"]
            out[name] = entry
        x = self.card("lexeme", self.X)
        out["lexeme_X"] = {"version": x.get("srs_card_version"), "engine": x.get("srs_engine"),
                           "logs": len(self.logs("lexeme", self.X))}
        return out

    def tearDown(self):
        out = os.environ.get("U12_OUT")
        if out:
            Path(out).write_text(json.dumps(self.steps, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    # ---------------------------------------------------------------- helpers ----
    def headers(self, user):
        return {"Authorization": "Bearer " + create_access_token({"id": user, "email": f"u12-{user}@example.test"})}

    def sql(self, statement, params=()):
        with get_connection() as c:
            return [dict(r) for r in c.execute(statement, params).fetchall()]

    def card(self, kind, ref, user=None):
        user = user or self.A
        rows = (self.sql("SELECT * FROM vocab_items WHERE id = ?", (ref,)) if kind == "personal" else
                self.sql("SELECT * FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (user, ref)))
        return rows[0] if rows else None

    def view(self, kind, ref, user=None):
        row = self.card(kind, ref, user)
        return None if row is None else {k: row.get(k) for k in CARD_COLS}

    def logs(self, kind, ref, user=None):
        user = user or self.A
        if kind == "personal":
            return self.sql("SELECT * FROM review_logs WHERE vocab_item_id = ? ORDER BY id", (ref,))
        return self.sql("SELECT * FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ? ORDER BY id", (user, ref))

    def fingerprint(self, rows):
        return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def account(self, user):
        """Everything of one account, as fingerprints and counts (no content)."""
        out = {}
        for table, col in (("vocab_items", "user_id"), ("user_word_progress", "user_id"), ("review_logs", "user_id"),
                           ("lexeme_review_logs", "user_id"), ("srs_review_receipts", "user_id"),
                           ("srs_migration_snapshots", "user_id"), ("srs_card_deletions", "user_id")):
            rows = self.sql(f"SELECT * FROM {table} WHERE {col} = ? ORDER BY id", (user,))
            out[table] = (len(rows), self.fingerprint(rows))
        return out

    def everything(self):
        out = {}
        for table in ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "srs_review_receipts",
                      "srs_migration_snapshots", "srs_migration_runs", "srs_card_deletions", "srs_evidence_restarts",
                      "srs_card_identity_flags"):
            out[table] = self.fingerprint(self.sql(f"SELECT * FROM {table} ORDER BY 1"))
        return out

    def review(self, kind, ref, rating="good", user=None, deck=None, request=None, version="current", expect=200,
               legacy=False):
        user = user or self.A
        if version == "current":
            row = self.card(kind, ref, user)
            version = None if row is None else row["srs_card_version"]
        self.req += 1
        request = request or f"u12-{kind}-{ref}-{self.req}"
        body = ({"rating": rating} if legacy else  # what the legacy client sends
                {"rating": rating, "request_id": request, "session_id": "u12", "expected_card_version": version})
        path = f"/study-items/{ref}/review" if kind == "personal" else f"/shared-decks/{deck}/words/{ref}/review"
        response = self.client.post(path, headers=self.headers(user), json=body)
        if expect is not None:
            self.assertEqual(response.status_code, expect, response.text[:300])
        return response

    def queue(self, user=None, **params):
        response = self.client.get("/study-queue", headers=self.headers(user or self.A), params=params)
        self.assertEqual(response.status_code, 200, response.text[:300])
        return response.json()

    def run_cli(self, script, *args):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"
        done = subprocess.run([sys.executable, str(SCRIPTS / script), "--sqlite-db", str(self.db_path), *args],
                              capture_output=True, text=True, timeout=180, env=env, encoding="utf-8")
        return done.returncode, done.stdout, done.stderr

    def tool(self, script, *args, user=None):
        printed = []
        with mock.patch.object(script, "print", side_effect=lambda text, **k: printed.append(text)):
            try:
                result = script.main(["--sqlite-db", str(self.db_path), "--user-id", str(user or self.A), *args])
            except SystemExit as stop:
                return (json.loads(printed[-1]) if printed else None), stop.code
        return result, 0

    def set_mode(self, user, mode):
        stamp = iso(self.clock)
        with get_connection() as c:
            c.execute("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
            c.execute("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, "
                      "updated_at) VALUES (?, ?, 20, 0, ?, ?)", (user, mode, stamp, stamp))

    # ----------------------------------------------- the pre-SRS structure (S0) ----
    def legacy_chain(self, kind, ref, user, ratings_times, deck=None):
        """Logs exactly as the legacy app wrote them (level / due chain), and the card row."""
        level, due, correct, wrong, last = 0, None, 0, 0, None
        with get_connection() as c:
            for rating, at in ratings_times:
                new_level, new_due = compute_review_schedule(rating, level, at)
                if kind == "personal":
                    c.execute("INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, "
                              "previous_review_level, next_review_level, previous_next_review_at, next_review_at) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (user, ref, deck, rating, iso(at), level, new_level, due,
                                                                    new_due))
                else:
                    c.execute("INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, "
                              "previous_review_level, new_review_level, previous_next_review_at, new_next_review_at, "
                              "previous_status, new_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', "
                              "'unknown', ?)", (user, ref, deck, rating, level, new_level, due, new_due, iso(at)))
                level, due, last = new_level, new_due, at
                correct, wrong = correct + (rating != "again"), wrong + (rating == "again")
            table, where = (("vocab_items", "id = ?"), (ref,)) if kind == "personal" else \
                (("user_word_progress", "user_id = ? AND lexeme_id = ?"), (user, ref))
            c.execute(f"UPDATE {table[0]} SET review_level = ?, next_review_at = ?, last_reviewed_at = ?, correct_count = ?, "
                      f"wrong_count = ? WHERE {table[1]}", (level, due, iso(last), correct, wrong, *where))

    def old_card(self, user, deck, name, created, status="unknown"):
        with get_connection() as c:
            return c.execute(
                "INSERT INTO vocab_items (deck_id, surface, base_form, reading, part_of_speech, normalized_form, meaning_ko, "
                "status, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?) RETURNING id",
                (deck, name, name, f"{name}-よみ", name, f"{name}-뜻", status, iso(created), iso(created), user),
            ).fetchone()["id"]

    def old_deck(self, user, name):
        stamp = iso(T0 - 400 * DAY)
        with get_connection() as c:
            return c.execute("INSERT INTO decks (name, description, created_at, updated_at, user_id) VALUES (?, '', ?, ?, ?) "
                             "RETURNING id", (name, stamp, stamp, user)).fetchone()["id"]

    def build_old_structure(self):
        with mock.patch.object(database, "ensure_srs_schema", lambda connection, is_postgres: None):
            database.init_db()
        tables = {r["name"] for r in self.sql("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertFalse({"srs_user_settings", "srs_migration_runs", "srs_review_receipts"} & tables)
        self.A = create_user(email="u12-a@example.test", display_name="A", password_hash="x")["id"]
        self.B = create_user(email="u12-b@example.test", display_name="B", password_hash="x")["id"]
        self.L = create_user(email="u12-l@example.test", display_name="L", password_hash="x")["id"]
        self.O = create_user(email="u12-o@example.test", display_name="O", password_hash="x")["id"]
        old = T0 - 400 * DAY
        self.deck = self.old_deck(self.A, "A-main")
        c = {}
        c["full"] = self.old_card(self.A, self.deck, "full", old)
        self.legacy_chain("personal", c["full"], self.A, [("good", T0 - 200 * DAY), ("good", T0 - 190 * DAY),
                                                          ("good", T0 - 150 * DAY)], self.deck)
        c["late"] = self.old_card(self.A, self.deck, "late", old)  # kept out of the first run (step 5)
        self.legacy_chain("personal", c["late"], self.A, [("good", T0 - 120 * DAY), ("good", T0 - 100 * DAY)], self.deck)
        c["pb"] = self.old_card(self.A, self.deck, "pb", old)  # plan B (step 6)
        self.legacy_chain("personal", c["pb"], self.A, [("good", T0 - 120 * DAY)], self.deck)
        c["pb2"] = self.old_card(self.A, self.deck, "pb2", old)  # repeated plan B (step 7)
        self.legacy_chain("personal", c["pb2"], self.A, [("good", T0 - 110 * DAY)], self.deck)
        with get_connection() as conn:  # plan B is for U5 (incomplete-history) cards: a lost link
            for ref in (c["pb"], c["pb2"]):
                conn.execute("UPDATE review_logs SET previous_review_level = 7 WHERE vocab_item_id = ?", (ref,))
        c["draft"] = self.old_card(self.A, self.deck, "draft", old)
        self.legacy_chain("personal", c["draft"], self.A, [("good", T0 - 90 * DAY), ("good", T0 - 80 * DAY)], self.deck)
        c["inc"] = self.old_card(self.A, self.deck, "inc", old)
        self.legacy_chain("personal", c["inc"], self.A, [("good", T0 - 100 * DAY), ("good", T0 - 90 * DAY)], self.deck)
        with get_connection() as conn:  # the old app lost one link of this chain
            conn.execute("UPDATE review_logs SET previous_review_level = 7 WHERE vocab_item_id = ? AND id = "
                         "(SELECT MAX(id) FROM review_logs WHERE vocab_item_id = ?)", (c["inc"], c["inc"]))
        c["nolog"] = self.old_card(self.A, self.deck, "nolog", old)
        with get_connection() as conn:  # studied before logs were kept
            conn.execute("UPDATE vocab_items SET correct_count = 2, review_level = 2, last_reviewed_at = ?, "
                         "next_review_at = ? WHERE id = ?", (iso(T0 - 30 * DAY), iso(T0 - DAY), c["nolog"]))
        c["known"] = self.old_card(self.A, self.deck, "known", old, status="known")
        self.legacy_chain("personal", c["known"], self.A, [("easy", T0 - 60 * DAY)], self.deck)
        c["fresh"] = self.old_card(self.A, self.deck, "fresh", old)
        c["mixed"] = self.old_card(self.A, self.deck, "mixed", T0 - 10 * DAY)  # logs older than the card itself
        self.legacy_chain("personal", c["mixed"], self.A, [("good", T0 - 50 * DAY)], self.deck)
        gone = self.old_card(self.A, self.deck, "gone", old)  # the old app deleted it and kept its log
        self.legacy_chain("personal", gone, self.A, [("good", T0 - 300 * DAY)], self.deck)
        with get_connection() as conn:
            conn.execute("DELETE FROM vocab_items WHERE id = ?", (gone,))
        self.gone = gone
        bdeck = self.old_deck(self.B, "B-main")
        c["b"] = self.old_card(self.B, bdeck, "b-full", old)
        self.legacy_chain("personal", c["b"], self.B, [("good", T0 - 200 * DAY), ("good", T0 - 190 * DAY)], bdeck)
        ldeck = self.old_deck(self.L, "L-main")
        c["l"] = self.old_card(self.L, ldeck, "l-card", old)
        self.legacy_chain("personal", c["l"], self.L, [("good", T0 - 20 * DAY)], ldeck)
        # shared decks: X in both decks (one progress row), Y never studied, Z for the copy
        stamp = iso(old)
        with get_connection() as conn:
            self.s1 = conn.execute("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, "
                                   "updated_at) VALUES (?, 'S1', '', 'public', ?, ?) RETURNING id", (self.O, stamp, stamp)
                                   ).fetchone()["id"]
            self.s2 = conn.execute("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, "
                                   "updated_at) VALUES (?, 'S2', '', 'public', ?, ?) RETURNING id", (self.O, stamp, stamp)
                                   ).fetchone()["id"]
            self.s3 = conn.execute("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, "
                                   "updated_at) VALUES (?, 'S3-copy', '', 'public', ?, ?) RETURNING id", (self.O, stamp, stamp)
                                   ).fetchone()["id"]
            conn.execute("INSERT INTO shared_deck_items (shared_deck_id, surface, base_form, reading, part_of_speech, "
                         "normalized_form, meaning_ko, dictionary_gloss, context_explanation_ko, example_sentence, quality_tag, "
                         "created_at) VALUES (?, 'x-語', 'x-語', 'x', '', 'x-語', 'x-뜻', '', '', '', 'normal', ?)",
                         (self.s3, stamp))
        self.X, self.Y, self.Z = (upsert_lexeme(n, n) for n in ("x-語", "y-語", "z-語"))
        for order, lex in enumerate((self.X, self.Y, self.Z)):
            add_word_to_shared_deck(self.s1, lex, order)
        add_word_to_shared_deck(self.s2, self.X, 0)
        for deck in (self.s1, self.s2):
            get_or_create_subscription(self.A, deck)
        with get_connection() as conn:
            conn.execute("UPDATE user_deck_subscriptions SET imported_at = ? WHERE user_id = ?", (stamp, self.A))
            conn.execute("INSERT INTO user_word_progress (user_id, lexeme_id, status, created_at, updated_at) "
                         "VALUES (?, ?, 'unknown', ?, ?)", (self.A, self.X, stamp, stamp))
        self.legacy_chain("lexeme", self.X, self.A, [("good", T0 - 140 * DAY), ("good", T0 - 130 * DAY)], self.s1)
        self.c = c
        self.record("S0 old structure", srs_tables=False, accounts=4,
                    card_ids={k: v for k, v in c.items()}, deleted_card=gone,
                    logs=len(self.sql("SELECT id FROM review_logs")) + len(self.sql("SELECT id FROM lexeme_review_logs")))

    # ------------------------------------------------------------ the flow ----
    def test_rehearsal(self):
        self.build_old_structure()
        c = self.c
        original_logs = {t: {r["id"]: r for r in self.sql(f"SELECT * FROM {t}")} for t in ("review_logs", "lexeme_review_logs")}

        # S1 upgrade, ID references, explicit rebuild, identity flags --------------------
        self.clock = T0 - DAY
        database.init_db()
        self.assertTrue({"srs_user_settings", "srs_migration_runs"} <= {
            r["name"] for r in self.sql("SELECT name FROM sqlite_master WHERE type = 'table'")})
        code, out, err = self.run_cli("d2_card_identity.py")
        self.assertEqual(code, 0, err[-300:])
        report = json.loads(out)
        self.assertGreaterEqual(max(report["references"].values()), self.gone)
        before_rebuild = self.everything()
        code, out, err = self.run_cli("d2_card_identity.py", "--apply-rebuild", "--apply-flags")
        self.assertEqual(code, 0, err[-300:])
        flags = self.sql("SELECT card_kind, card_ref FROM srs_card_identity_flags")
        self.assertIn(("personal", c["mixed"]), [(f["card_kind"], f["card_ref"]) for f in flags])
        after_rebuild = self.everything()
        for table in ("review_logs", "lexeme_review_logs"):
            self.assertEqual(after_rebuild[table], before_rebuild[table])  # history rows untouched
        probe = self.old_card(self.B, None, "probe", T0 - DAY)
        self.assertGreater(probe, self.gone)  # a deleted id is never handed out again
        with get_connection() as conn:
            conn.execute("DELETE FROM vocab_items WHERE id = ?", (probe,))
        self.record("S1 upgrade / references / rebuild / flags", max_reference=max(report["references"].values()),
                    deleted_id=self.gone, new_id_after_rebuild=probe, identity_flags=len(flags),
                    logs_unchanged=True)
        # pre-U11 draft completion written by the earlier build: fixture of old data
        self.set_mode(self.A, "fsrs")
        self.set_mode(self.B, "fsrs")
        self.set_mode(self.L, "legacy")
        b_before, l_before = self.account(self.B), self.account(self.L)

        # S2 dry run, limited apply, interruption, resume, rerun -------------------------
        self.clock = T0
        keys = [CardKey("personal", self.A, c[k]) for k in ("full", "inc", "nolog", "known", "fresh", "draft", "mixed")]
        plan = migration.dry_run(keys)
        quality = {k: p.quality for k, p in zip(("full", "inc", "nolog", "known", "fresh", "draft", "mixed"),
                                                 sorted(plan, key=lambda p: keys.index(p.key)))}
        self.assertEqual(quality["full"], "complete")
        self.assertEqual(quality["inc"], "incomplete")
        self.assertEqual(quality["nolog"], "incomplete")
        self.assertEqual(quality["mixed"], "identity_unknown")
        self.assertEqual(self.everything(), after_rebuild)  # dry run writes nothing
        real_update, calls = migration.update_card, {"n": 0}

        def failing(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic interruption")
            return real_update(*a, **k)

        migration.apply_plan(plan, "u12-run-1", approved=True, batch_size=2)  # first limited batch
        self.assertEqual(json.loads(self.sql("SELECT summary_json FROM srs_migration_runs WHERE run_key = 'u12-run-1'")[0][
            "summary_json"])["cursor"], 2)
        with mock.patch.object(migration, "update_card", failing), self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "u12-run-1", approved=True, batch_size=3)  # interrupted inside the batch
        run1 = self.sql("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 'u12-run-1'")[0]
        cursor_after_failure = json.loads(run1["summary_json"])["cursor"]
        self.assertEqual(run1["status"], "failed")
        self.assertGreater(cursor_after_failure, 2)
        results = migration.apply_plan(plan, "u12-run-1", approved=True, batch_size=10)  # resume
        run1 = self.sql("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 'u12-run-1'")[0]
        self.assertEqual(run1["status"], "completed")
        state_after = self.everything()
        rerun = migration.apply_plan(plan, "u12-run-1", approved=True)
        self.assertEqual(self.everything(), state_after)  # same key again: stored results, no write
        # stored results; an earlier "applied" is answered as "already_applied" (existing contract)
        self.assertEqual([r["result"] for r in rerun],
                         ["already_applied" if r["result"] == "applied" else r["result"] for r in results])
        by_ref = {r["ref_id"]: r for r in rerun}
        self.assertEqual(by_ref[c["mixed"]]["result"], "blocked")
        self.assertEqual(self.view("personal", c["known"])["srs_participation"], "paused")
        self.assertEqual(self.view("personal", c["nolog"])["history_intro_status"], "before_tracking")
        lx_plan = migration.dry_run([CardKey("lexeme", self.A, self.X)])
        self.assertEqual(lx_plan[0].quality, "complete")
        migration.apply_plan(lx_plan, "u12-run-lx", approved=True)
        self.assertEqual(self.account(self.B), b_before)
        self.assertEqual(self.account(self.L), l_before)
        with get_connection() as conn:  # the draft build's output on this card (old data fixture)
            conn.execute("UPDATE vocab_items SET completion_metric_version = ?, first_completed_at = ? WHERE id = ?",
                         (DRAFT_METRIC_VERSION, iso(T0 - 5 * DAY), c["draft"]))
        self.record("S2 dry run / apply / interrupt / resume / rerun", qualities=quality, cursor_after_failure=cursor_after_failure,
                    run_status=run1["status"], rerun_writes=0, identity_unknown_blocked=True, b_unchanged=True,
                    l_unchanged=True)

        # S3 real reviews, lost answer, retry, two windows, late answer, account / permission --
        self.clock = T0 + DAY
        first = self.review("personal", c["full"], "good", request="u12-lost-1")
        before = self.everything()
        again = self.review("personal", c["full"], "good", request="u12-lost-1",
                            version=first.json()["srs"]["card_version"] - 1)
        self.assertEqual(again.content, first.content)
        self.assertEqual(self.everything(), before)
        stale = first.json()["srs"]["card_version"] - 1
        late = self.review("personal", c["full"], "good", version=stale, expect=409)  # second window, old version
        self.assertEqual(late.json()["detail"], "card_version_conflict")
        self.review("personal", c["full"], "good", user=self.B, expect=404)  # account switch: not B's card
        x1 = self.review("lexeme", self.X, "good", deck=self.s1).json()
        x_row = self.card("lexeme", self.X)
        x2 = self.review("lexeme", self.X, "good", deck=self.s2).json()  # the other deck: same progress row
        self.assertEqual(x2["srs"]["card_version"], x_row["srs_card_version"] + 1)
        y_first = self.client.post(f"/shared-decks/{self.s1}/words/{self.Y}/review", headers=self.headers(self.A),
                                   json={"rating": "easy", "request_id": "u12-y-first", "session_id": "u12",
                                         "expected_card_version": None})
        self.assertEqual(y_first.status_code, 200)
        y_retry = self.client.post(f"/shared-decks/{self.s1}/words/{self.Y}/review", headers=self.headers(self.A),
                                   json={"rating": "easy", "request_id": "u12-y-first", "session_id": "u12",
                                         "expected_card_version": None})
        self.assertEqual(y_retry.content, y_first.content)
        inc_first = self.review("personal", c["inc"], "good").json()
        self.assertEqual(self.view("personal", c["inc"])["evidence_from_log_id"], self.logs("personal", c["inc"])[-1]["id"])
        nolog_first = self.review("personal", c["nolog"], "good").json()
        self.assertEqual(nolog_first["srs"]["introduced_today_status"], inc_first["srs"]["introduced_today_status"])
        paused = self.review("personal", c["known"], "good", expect=409)
        self.assertEqual(paused.json()["detail"], "card_paused")
        # identity unknown: never converted (S2) and never served; a direct request on the still
        # legacy card takes the existing legacy path (observation, see REPORT 40).
        self.assertNotIn(("personal", c["mixed"]), [(i["card_kind"], i["card_id"]) for i in self.queue()["items"]])
        flagged = self.review("personal", c["mixed"], "good", expect=None)
        self.flagged_direct = flagged.status_code
        self.assertEqual(self.card("personal", c["mixed"])["srs_engine"], "legacy")
        self.assertNotIn("srs", flagged.json())
        # concurrency: two windows submit against the same version at once
        version = self.card("personal", c["fresh"])["srs_card_version"]

        def send(n):
            return lambda: self.review("personal", c["fresh"], "good", version=version, request=f"u12-twin-{n}",
                                       expect=None).status_code

        a, b = race_support.start("a", send(1)), race_support.start("b", send(2))
        codes = sorted(race_support.finish(self, t) for t in (a, b))
        self.assertEqual(codes, [200, 409])
        # a failure inside the review transaction leaves nothing behind
        before = self.everything()
        with mock.patch.object(reviews, "update_card", side_effect=RuntimeError("synthetic")):
            with self.assertRaises(RuntimeError):
                self.review("personal", c["full"], "good", expect=None)
        self.assertEqual(self.everything(), before)
        # a brand-new personal card in the FSRS account
        created = self.client.post("/vocab-items", headers=self.headers(self.A),
                                   json={"surface": "new-語", "base_form": "new-語", "reading": "new", "meaning_ko": "새",
                                         "deck_id": self.deck})
        self.assertEqual(created.status_code, 200, created.text[:200])
        self.new = created.json()["id"]
        self.assertEqual(self.view("personal", self.new)["srs_card_version"], 0)
        # an old copy-mode shared deck with the same word as X, copied by A: its own history
        copied = self.client.post(f"/shared-decks/{self.s3}/import", headers=self.headers(self.A))
        self.assertEqual(copied.status_code, 200, copied.text[:200])
        copy_cards = self.sql("SELECT id FROM vocab_items WHERE user_id = ? AND deck_id = ?", (self.A, copied.json()["deck_id"]))
        self.assertEqual(len(copy_cards), 1)
        self.copy_card = copy_cards[0]["id"]
        x_before = self.view("lexeme", self.X)
        self.review("personal", self.copy_card, "good")
        self.assertEqual(self.view("lexeme", self.X), x_before)  # the subscribed progress of the same word is separate
        copy_view = self.view("personal", self.copy_card)
        self.review("lexeme", self.X, "good", deck=self.s1)
        self.assertEqual(self.view("personal", self.copy_card), copy_view)
        # legacy account keeps its legacy behaviour
        l_review = self.review("personal", c["l"], "good", user=self.L, legacy=True).json()
        self.assertNotIn("srs", l_review)
        self.assertEqual(self.card("personal", c["l"], self.L)["srs_engine"], "legacy")
        # permission loss: unsubscribe S2, the S2 path is refused; S1 still works
        with get_connection() as conn:
            conn.execute("UPDATE user_deck_subscriptions SET is_active = 0 WHERE user_id = ? AND shared_deck_id = ?",
                         (self.A, self.s2))
        lost = self.review("lexeme", self.X, "good", deck=self.s2, expect=None)
        self.assertIn(lost.status_code, (403, 404))
        with get_connection() as conn:
            conn.execute("UPDATE user_deck_subscriptions SET is_active = 1 WHERE user_id = ? AND shared_deck_id = ?",
                         (self.A, self.s2))
        q = self.queue()
        self.record("S3 reviews / retry / windows / accounts / permission", retry_identical=True, late_answer=409,
                    other_account=404, shared_progress_versions=[x1["srs"]["card_version"], x2["srs"]["card_version"]],
                    subscribed_first_review=200, boundary_set=True, known_paused=409, identity_unknown_not_served=True, identity_unknown_direct=self.flagged_direct,
                    concurrent=codes, mid_failure_rollback=True, new_card_version=0, copy_separate=True,
                    legacy_unchanged=True, permission_loss=lost.status_code, queue_counts=q["counts"])

        # S4 V3 completion, failure, first completion / source / current split ------------
        results = []
        for d in (1, 9, 75):
            self.clock = T0 + d * DAY
            results.append(self.review("personal", self.new, "easy").json())
        self.assertEqual([r["completed"] for r in results], [False, False, True])
        done_at = results[-1]["accepted_at"]
        self.clock = T0 + 301 * DAY
        failed = self.review("personal", self.new, "again").json()
        self.assertEqual((failed["completed"], failed["srs"]["needs_relearning"], failed["srs"]["first_completed_at"]),
                         (False, True, done_at))
        draft_answer = self.review("personal", c["draft"], "good").json()
        draft_view = self.view("personal", c["draft"])
        self.assertEqual((draft_view["first_completed_at"], draft_view["first_completed_source"]),
                         (iso(T0 - 5 * DAY), DRAFT_METRIC_VERSION))
        # the answer carries only the V3 first completion: this review's time if V3 is met now, else none
        self.assertEqual(draft_answer["srs"]["first_completed_at"],
                         draft_answer["accepted_at"] if draft_answer["completed"] else None)
        self.assertEqual(draft_view["version_first_completed_at"], draft_answer["srs"]["first_completed_at"])
        new_view = self.view("personal", self.new)
        self.assertEqual((new_view["first_completed_source"], new_view["version_first_completed_version"],
                          new_view["completion_metric_version"]), (METRIC_VERSION, METRIC_VERSION, METRIC_VERSION))
        self.record("S4 V3 completion / failure / sources", completed=[r["completed"] for r in results],
                    needs_relearning_after_failure=True, draft_source=DRAFT_METRIC_VERSION,
                    draft_answer_completed=draft_answer["completed"], draft_first_kept=True, current_version=METRIC_VERSION)

        # S5 rollback in the window -> restore -> follow-up ------------------------------
        self.clock = T0 + 310 * DAY
        late_plan = migration.dry_run([CardKey("personal", self.A, c["late"])])
        migration.apply_plan(late_plan, "u12-run-late", approved=True)
        self.clock = T0 + 311 * DAY
        self.review("personal", c["late"], "good")
        late_logs = self.fingerprint(self.logs("personal", c["late"]))
        self.clock = T0 + 312 * DAY
        rb = migration.rollback_plan("u12-run-late", "u12-rb-late", user_id=self.A, approved=True)
        self.assertEqual(rb[0]["result"], "rolled_back")
        self.assertEqual(self.fingerprint(self.logs("personal", c["late"])), late_logs)  # history kept
        restored = migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["late"])]), "u12-re-late",
                                        approved=True)
        self.assertEqual(restored[0]["reconversion"], "restored")
        self.clock = T0 + 340 * DAY
        follow = self.review("personal", c["late"], "good").json()
        self.assertIsNot(follow["completed"], None)  # the restore gap is proven: evidence stays complete
        self.record("S5 rollback / restore / follow-up", rollback="rolled_back", logs_kept=True, reconversion="restored",
                    follow_up_completion_status=follow["srs"]["completion_status"])

        # S6 rollback -> real change -> plan B -> first review -> follow-ups ---------------
        self.clock = T0 + 350 * DAY
        migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["pb"])]), "u12-run-pb", approved=True)
        self.clock = T0 + 351 * DAY
        self.review("personal", c["pb"], "good")
        self.clock = T0 + 352 * DAY
        self.assertEqual(migration.rollback_plan("u12-run-pb", "u12-rb-pb", user_id=self.A, approved=True)[0]["result"],
                         "rolled_back")
        self.clock = T0 + 353 * DAY
        self.set_mode(self.A, "legacy")  # a real legacy review while the card is legacy again (synthetic account)
        self.review("personal", c["pb"], "good", legacy=True)
        self.set_mode(self.A, "fsrs")
        pb_re = migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["pb"])]), "u12-re-pb", approved=True)
        self.assertEqual(pb_re[0]["reconversion"], "state_none_restart")
        old_boundary = self.view("personal", c["pb"])["evidence_from_log_id"]
        self.clock = T0 + 354 * DAY
        self.review("personal", c["pb"], "good")
        new_boundary = self.view("personal", c["pb"])["evidence_from_log_id"]
        self.assertNotEqual(new_boundary, old_boundary)
        self.assertEqual(new_boundary, self.logs("personal", c["pb"])[-1]["id"])
        self.clock = T0 + 360 * DAY
        self.review("personal", c["pb"], "good")
        self.record("S6 plan B", reconversion="state_none_restart", boundary_replaced=True,
                    restarts=len(self.sql("SELECT id FROM srs_evidence_restarts")))

        # S7 repeated plan B, delayed first review, old permission stays dead -------------
        self.clock = T0 + 361 * DAY
        migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["pb2"])]), "u12-run-pb2", approved=True)
        self.clock = T0 + 362 * DAY
        self.review("personal", c["pb2"], "good")
        self.clock = T0 + 363 * DAY
        migration.rollback_plan("u12-run-pb2", "u12-rb-pb2", user_id=self.A, approved=True)
        self.set_mode(self.A, "legacy")
        self.review("personal", c["pb2"], "good", legacy=True)
        self.set_mode(self.A, "fsrs")
        first_b = migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["pb2"])]), "u12-re-pb2",
                                       approved=True)
        self.assertEqual(first_b[0]["reconversion"], "state_none_restart")
        old_snapshot = max(s["id"] for s in self.sql(
            "SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
            "WHERE r.mode = 'apply' AND s.card_ref = ? AND s.card_kind = 'personal'", (c["pb2"],)))
        self.clock = T0 + 364 * DAY  # rolled back again before its first review
        migration.rollback_plan("u12-re-pb2", "u12-rb-pb2-again", user_id=self.A, approved=True)
        again_b = migration.apply_plan(migration.dry_run([CardKey("personal", self.A, c["pb2"])]), "u12-re-pb2-again",
                                       approved=True)
        self.assertEqual(again_b[0]["reconversion"], "restored")
        with get_connection() as conn:
            permission = restoration.restart_permission(conn, CardKey("personal", self.A, c["pb2"]),
                                                        self.card("personal", c["pb2"]), self.logs("personal", c["pb2"]))
        self.assertIsNotNone(permission)
        self.assertNotEqual(permission["snapshot_id"], old_snapshot)  # the older permission is not reused
        self.clock = T0 + 420 * DAY  # delayed first review
        delayed = self.review("personal", c["pb2"], "good").json()
        self.assertEqual(delayed["card_id"], c["pb2"])
        self.assertEqual(len(self.sql("SELECT id FROM srs_evidence_restarts WHERE source_snapshot_id = ?",
                                      (old_snapshot,))), 0)
        self.record("S7 repeated plan B / delayed first review", reconversions=["state_none_restart", "restored"],
                    new_permission=True, old_permission_used=False, delayed_days=56)

        # S8 U10-b minimize -> U10-d refusal -> U10-e prune -> follow-up -------------------
        minimized, code = self.tool(d2_snapshot_minimize, "--apply", "--confirm-user-id", str(self.A))
        self.assertEqual((code, minimized["unsupported"], minimized["conflicts"]), (0, [], []))
        before = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            migration.rollback_plan("u12-run-1", "u12-rb-too-late", user_id=self.A, approved=True)
        self.assertEqual(caught.exception.code, "rollback_window_closed")
        self.assertEqual(self.everything(), before)
        pruned, code = self.tool(d2_snapshot_prune, "--apply", "--confirm-user-id", str(self.A))
        self.assertEqual((code, pruned["snapshots"]["unsupported"], pruned["runs"]["conflicts"]), (0, [], []))
        self.assertTrue(pruned["runs"]["pruned"])
        self.clock = T0 + 421 * DAY
        after_prune = self.review("personal", c["full"], "good").json()
        self.assertEqual(after_prune["card_id"], c["full"])
        self.record("S8 U10-b / U10-d / U10-e", minimized=len(minimized["minimized"]), rollback_after_window="closed",
                    pruned_runs=len(pruned["runs"]["pruned"]), pruned_records=len(pruned["snapshots"]["pruned"]),
                    protected=len(pruned["snapshots"]["protected"]), follow_up_review=200)

        # S9 completed key recall, other request conflict, tool reruns ---------------------
        before = self.everything()
        recall = migration.apply_plan(plan, "u12-run-1", approved=True)
        self.assertEqual([r["result"] for r in recall], [r["result"] for r in rerun])
        self.assertEqual(migration.rollback_plan("u12-run-late", "u12-rb-late", user_id=self.A, approved=True), rb)
        self.assertEqual(self.everything(), before)
        with self.assertRaises(SrsWriteError) as caught:
            migration.apply_plan(lx_plan, "u12-run-1", approved=True)
        self.assertEqual(caught.exception.code, "migration_run_conflict")
        again_min, _ = self.tool(d2_snapshot_minimize, "--apply", "--confirm-user-id", str(self.A))
        again_prune, _ = self.tool(d2_snapshot_prune, "--apply", "--confirm-user-id", str(self.A))
        self.assertEqual((again_min["minimized"], again_prune["runs"]["pruned"], again_prune["snapshots"]["pruned"]),
                         ([], [], []))
        self.assertEqual(self.everything(), before)
        self.record("S9 recalls / conflict / reruns", apply_recall_writes=0, rollback_recall_writes=0,
                    other_request="migration_run_conflict", tool_reruns=0)

        # Branches on dedicated cards (before the deletes, the boundary card is in the deleted deck)
        self.branches()
        if os.environ.get("U12_DB_OUT"):  # a copy for the live app check (before the deletes)
            import shutil
            shutil.copyfile(self.db_path, os.environ["U12_DB_OUT"])
            Path(os.environ["U12_DB_OUT"] + ".json").write_text(json.dumps(
                {"A": self.A, "B": self.B, "L": self.L, "s1": self.s1, "s2": self.s2, "deck": self.deck,
                 "cards": self.c, "new": self.new, "last_clock": iso(self.clock)}), encoding="utf-8")

        # S10 delete word and deck, evidence kept, content gone, retry of a deleted card ---
        full_logs = self.fingerprint(self.logs("personal", c["full"]))
        receipt_rows = self.sql("SELECT id FROM srs_review_receipts WHERE card_kind = 'personal' AND card_ref = ?",
                                (c["full"],))
        history_day = (T0 + DAY).astimezone(timezone(timedelta(hours=9))).date().isoformat()
        stats_before = self.client.get("/stats/history/day", headers=self.headers(self.A), params={"date": history_day})
        with get_connection() as conn:
            introduced_before = reviews.introduced_on(conn, self.A, T0 + DAY).as_dict()
        self.assertEqual(self.client.delete(f"/vocab-items/{c['full']}", headers=self.headers(self.A)).status_code, 204)
        self.assertEqual(self.fingerprint(self.logs("personal", c["full"])), full_logs)  # logs kept
        ledger = self.sql("SELECT card_ref, history_intro_status FROM srs_card_deletions WHERE card_ref = ?", (c["full"],))
        self.assertEqual(len(ledger), 1)
        for row in self.sql("SELECT response_json FROM srs_review_receipts WHERE card_kind = 'personal' AND card_ref = ?",
                            (c["full"],)):
            self.assertNotIn("full-뜻", row["response_json"])
        for row in self.sql("SELECT legacy_json FROM srs_migration_snapshots WHERE card_kind = 'personal' AND card_ref = ?",
                            (c["full"],)):
            self.assertNotIn("full-뜻", row["legacy_json"])
        gone_retry = self.review("personal", c["full"], "good", request="u12-lost-1", version=0, expect=404)
        self.assertNotIn("full-뜻", gone_retry.text)
        stats_after = self.client.get("/stats/history/day", headers=self.headers(self.A), params={"date": history_day})
        self.assertEqual(stats_after.status_code, stats_before.status_code)
        self.assertEqual(stats_before.status_code, 200)
        self.assertGreater(stats_before.json()["review_count"], 0)
        deck_delete = self.client.delete(f"/decks/{self.deck}", headers=self.headers(self.A))
        self.assertEqual(deck_delete.status_code, 200, deck_delete.text[:200])
        stats_final = self.client.get("/stats/history/day", headers=self.headers(self.A), params={"date": history_day}).json()
        for key in ("review_count", "ratings"):  # the day's reviews stay counted after both deletes
            self.assertEqual(stats_final[key], stats_before.json()[key], key)
        with get_connection() as conn:
            introduced_after = reviews.introduced_on(conn, self.A, T0 + DAY).as_dict()
        self.assertEqual(introduced_after, introduced_before)  # new-word results (or "unknown") kept
        self.assertEqual(self.account(self.B)["review_logs"], b_before["review_logs"])
        with get_connection() as conn:
            identity.personal_id_references(conn)
        for table, rows in original_logs.items():  # every pre-SRS log, compared with its S0 fingerprint
            now = {r["id"]: r for r in self.sql(f"SELECT * FROM {table}")}
            for log_id, row in rows.items():
                self.assertEqual({k: now[log_id].get(k) for k in row}, row, (table, log_id))
        self.record("S10 deletes", original_logs_unchanged=sum(len(r) for r in original_logs.values()), word_delete=204, logs_kept=True, ledger_rows=len(ledger), receipt_rows_before=len(receipt_rows),
                    content_in_receipts=False, deleted_retry=404, deck_delete=200, day_review_count=stats_final["review_count"],
                    introduced_kept=introduced_after)


    def branches(self):
        # damaged snapshot: a card without boundary keeps being rated, a window card is refused
        self.clock = T0 + 430 * DAY
        plain = self.client.post("/vocab-items", headers=self.headers(self.A),
                                 json={"surface": "dmg-語", "base_form": "dmg-語", "reading": "d", "meaning_ko": "손상"}
                                 ).json()["id"]
        self.review("personal", plain, "easy")
        self.clock = T0 + 438 * DAY
        self.review("personal", plain, "easy")
        log = self.logs("personal", plain)[-1]
        after = json.loads(log["srs_after_json"])
        after["stability"] = 10 ** 400
        with get_connection() as conn:
            conn.execute("UPDATE review_logs SET srs_after_json = ? WHERE id = ?", (json.dumps(after), log["id"]))
        self.clock = T0 + 504 * DAY
        dmg = self.review("personal", plain, "easy").json()
        self.assertIsNone(dmg["completed"])
        inc = self.c["inc"]
        window_log = self.logs("personal", inc)[-1]
        after = json.loads(window_log["srs_after_json"])
        after["stability"] = 10 ** 400
        with get_connection() as conn:
            conn.execute("UPDATE review_logs SET srs_after_json = ? WHERE id = ?", (json.dumps(after), window_log["id"]))
        refused = self.review("personal", inc, "good", expect=None)
        q = self.queue()
        self.assertEqual(refused.status_code, 409)
        self.assertNotIn(("personal", inc), [(i["card_kind"], i["card_id"]) for i in q["items"]])
        # unexplained version gap on a new card: no completion
        gap = self.client.post("/vocab-items", headers=self.headers(self.A),
                               json={"surface": "gap-語", "base_form": "gap-語", "reading": "g", "meaning_ko": "공백"}
                               ).json()["id"]
        answers = []
        for d, bump in ((505, False), (513, True), (579, False)):
            self.clock = T0 + d * DAY
            if bump:
                with get_connection() as conn:
                    conn.execute("UPDATE vocab_items SET srs_card_version = srs_card_version + 2 WHERE id = ?", (gap,))
            answers.append(self.review("personal", gap, "easy").json()["completed"])
        self.assertNotIn(True, answers)
        self.record("branches", damaged_plain=dmg["srs"]["completion_status"], damaged_window=refused.status_code,
                    window_card_in_queue=False, unexplained_gap_completed=answers,
                    queue_invalid_state=q["counts"]["invalid_state"])


if __name__ == "__main__":
    unittest.main()
