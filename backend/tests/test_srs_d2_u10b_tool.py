"""Gate D-2 U10-b: the one-time tool that rewrites an account's format-1 snapshot / rollback
records to format 2 (scripts/d2_snapshot_minimize.py -> migration.minimize_snapshots).

Every record here is written in format 1 (BaselineCase.FORMAT1 rewrites each new record
to the pre-U10 shape), then the tool runs against this test's own synthetic SQLite file.

Run directly:      python tests/test_srs_d2_u10b_tool.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_value_shape import ValueShapeCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import d2_snapshot_minimize  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import identity, migration, reviews, storage  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

DAY = timedelta(days=1)
COMPARED = ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "srs_review_receipts",
            "srs_evidence_restarts", "srs_card_deletions")


class ToolCase(ValueShapeCase):
    FORMAT1 = True

    def everything(self):
        out = super().everything()
        with get_connection() as c:
            out["srs_evidence_restarts"] = [tuple(r) for r in c.execute("SELECT * FROM srs_evidence_restarts ORDER BY 1")]
        return out

    def tool(self, *extra, user=None):
        printed = []
        with mock.patch.object(d2_snapshot_minimize, "print", side_effect=lambda text, **k: printed.append(text)):
            try:
                result = d2_snapshot_minimize.main(["--sqlite-db", str(self.db_path), "--user-id", str(user or self.user),
                                                    *extra])
            except SystemExit as stop:
                return json.loads(printed[-1]) if printed else None, stop.code
        return result, 0

    def apply_tool(self, *extra):
        return self.tool("--apply", "--confirm-user-id", str(self.user), *extra)

    def rows(self, user=None):
        with get_connection() as c:
            return {r["id"]: dict(r) for r in c.execute(
                "SELECT s.*, r.mode FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                "WHERE s.user_id = ? ORDER BY s.id", (user or self.user,))}

    def scenario(self):
        """Format-1 records of: a personal and a subscribed card rolled back after reviews, a
        restored card, a plan-B card waiting for its first review, plus damaged ones."""
        refs = {}
        refs["p_rolled"], _ = self.card_with_records("p-rolled")
        deck = self.shared_deck("s")
        lexeme = self.converted("lexeme", "lx-rolled", deck)
        self.rate_at("lexeme", lexeme, NOW, "good", deck=deck)
        self.now = NOW
        self.rollback("lexeme", lexeme)
        refs["lexeme"], refs["deck"] = lexeme, deck
        refs["restored"], _ = self.card_with_records("restored")
        self.reconvert("personal", refs["restored"])
        refs["plan_b"], _, _, refs["plan_b_at"] = self.to_plan_b("personal", name="pb-wait")
        damaged = {}
        for name, change in (("unsupported", lambda p: p.update(note="뜻-사본")),
                             ("fingerprint", lambda p: p.get("baseline", {}).update(card_fingerprint="뜻-사본")),
                             ("insufficient", lambda p: p["card"].pop("srs_state"))):
            ref, _ = self.card_with_records(f"dmg-{name}")
            mode = "rollback" if name == "fingerprint" else "apply"
            record = [r for r in self.records("personal", ref) if r["mode"] == mode][0]
            payload = self.payload(record)
            change(payload)
            with get_connection() as c:
                c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                          (json.dumps(payload, ensure_ascii=False), record["id"]))
            damaged[name] = record["id"]
        ref, _ = self.card_with_records("dmg-column")
        record = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        after = json.loads(record["srs_after_json"])
        after["srs_state"] = {"meaning_ko": "뜻-사본"}
        with get_connection() as c:  # the record itself is a valid format-1 one; only the column is damaged
            c.execute("UPDATE srs_migration_snapshots SET srs_after_json = ? WHERE id = ?",
                      (json.dumps(after, ensure_ascii=False), record["id"]))
        damaged["column"] = record["id"]
        refs["damaged"] = damaged
        # one record already in format 2
        ref, _ = self.card_with_records("already-2")
        record = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        with get_connection() as c:
            columns = migration._card_columns(c, "personal")
            shape = migration._record_shape("apply", "personal", ref, self.payload(record), columns)
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (migration._json(shape), record["id"]))
        refs["format2"] = record["id"]
        return refs

    def other_account_record(self):
        self.set_mode(self.other, "fsrs")
        card = self.personal("theirs", user=self.other)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
                      (iso(NOW - 9 * DAY), iso(NOW - timedelta(hours=1)), card))
        migration.apply_plan(migration.dry_run([CardKey("personal", self.other, card)]), "run-theirs", approved=True)
        return self.rows(self.other)


# ---------------------------------------------------------------------------
class ContractTests(ToolCase):
    def test_dry_run_apply_rerun(self):
        refs = self.scenario()
        theirs = self.other_account_record()
        before = self.everything()
        rows_before = self.rows()
        report, code = self.tool()
        self.assertEqual(code, 0)
        self.assertEqual(self.everything(), before)  # dry-run writes nothing
        self.assertFalse(report["applied"])
        unsupported = {e["id"] for e in report["unsupported"]}
        self.assertEqual(unsupported, {refs["damaged"][k] for k in ("unsupported", "fingerprint", "column")})
        self.assertEqual([e["id"] for e in report["insufficient"]], [refs["damaged"]["insufficient"]])
        self.assertEqual(report["already_minimal"], 1)
        expected = set(rows_before) - unsupported - {refs["damaged"]["insufficient"], refs["format2"]}
        self.assertEqual({e["id"] for e in report["minimized"]}, expected)
        self.assertNotIn("뜻", json.dumps(report, ensure_ascii=False))
        self.assertNotIn("p-rolled", json.dumps(report, ensure_ascii=False))
        # apply needs the account confirmation
        _, code = self.tool("--apply")
        self.assertEqual(code, 2)
        _, code = self.tool("--apply", "--confirm-user-id", str(self.other))
        self.assertEqual(code, 2)
        applied, code = self.apply_tool()
        self.assertEqual((code, {e["id"] for e in applied["minimized"]}), (0, expected))
        after = self.everything()
        for table in COMPARED:
            self.assertEqual(after[table], before[table], table)  # cards, logs, receipts, restarts, ledger
        self.assertEqual(after["srs_migration_runs"], before["srs_migration_runs"])  # run status / times
        rows_after = self.rows()
        for record_id, row in rows_after.items():
            old = rows_before[record_id]
            self.assertEqual({k: row[k] for k in row if k != "legacy_json"}, {k: old[k] for k in old if k != "legacy_json"})
            if record_id in expected:
                new, prev = json.loads(row["legacy_json"]), json.loads(old["legacy_json"])
                self.assertEqual(new["format"], 2)
                for key in ("last_log_id", "restart", "baseline"):
                    self.assertEqual(new.get(key), prev.get(key))
                self.assertEqual(new["card"], {k: prev["card"][k] for k in new["card"]})
                self.assertNotIn("뜻", row["legacy_json"])
            else:
                self.assertEqual(row["legacy_json"], old["legacy_json"])  # damaged / format 2 untouched
        self.assertEqual(self.rows(self.other), theirs)  # other account untouched
        with get_connection() as c:
            identity.personal_id_references(c)  # ID references still resolve
        again, code = self.apply_tool()
        self.assertEqual((again["minimized"], again["already_minimal"]), ([], 1 + len(expected)))
        self.assertEqual(self.everything(), {**after, "srs_migration_snapshots": after["srs_migration_snapshots"]})

    def test_results_are_the_same_with_and_without_minimization(self):
        refs = self.scenario()
        with get_connection() as c:
            for record_id in refs["damaged"].values():  # keep the twin runs comparable
                c.execute("DELETE FROM srs_migration_snapshots WHERE id = ?", (record_id,))
        copy = Path(self.directory.name) / "twin.db"
        shutil.copyfile(self.db_path, copy)
        report, _ = self.apply_tool()
        self.assertTrue(report["minimized"])

        def outcomes():
            results = {}
            self.now = NOW
            results["rollback_restored"] = migration.rollback_plan(f"re-personal-{refs['restored']}-2"
                                                                   if False else self.latest_apply_run(refs["restored"]),
                                                                   "rb-twin", user_id=self.user, approved=True)
            results["reconvert"] = [r.get("reconversion") for r in migration.apply_plan(
                migration.dry_run([self.key("personal", refs["restored"])]), "re-twin", approved=True)]
            results["reconvert_p"] = [r.get("reconversion") for r in migration.apply_plan(
                migration.dry_run([self.key("personal", refs["p_rolled"])]), "re-twin-p", approved=True)]
            results["reconvert_lx"] = [r.get("reconversion") for r in migration.apply_plan(
                migration.dry_run([self.key("lexeme", refs["lexeme"])]), "re-twin-lx", approved=True)]
            for gap in (20, 40):
                self.rate_at("personal", refs["restored"], NOW + gap * DAY, "good")
            results["proof"] = list(self.seen[-2:])
            self.rate_at("personal", refs["plan_b"], refs["plan_b_at"] + 60 * DAY, "good")  # delayed first review
            self.now = NOW
            with get_connection() as c:
                results["refs"] = identity.personal_id_references(c)
                results["tables"] = {t: [tuple(r) for r in c.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in COMPARED}
            return results

        minimized = outcomes()
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{copy.as_posix()}"}):
            original = outcomes()
        self.assertEqual(minimized, original)

    def latest_apply_run(self, ref):
        with get_connection() as c:
            return c.execute("SELECT r.run_key FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                             "WHERE s.card_ref = ? AND s.card_kind = 'personal' AND r.mode = 'apply' ORDER BY s.id DESC "
                             "LIMIT 1", (ref,)).fetchone()[0]


class BatchTests(ToolCase):
    def make(self, n):
        for i in range(n):
            self.card_with_records(f"b{i}")
        return sorted(self.rows())

    def test_failure_rolls_back_the_batch_and_resume_finishes(self):
        ids = self.make(3)  # 6 records
        real = migration._json
        calls = {"n": 0}

        def failing(value):
            calls["n"] += 1
            if calls["n"] == 3:  # first write of the second batch
                raise RuntimeError("synthetic failure")
            return real(value)

        before = self.rows()
        with mock.patch.object(migration, "_json", failing):
            report, code = self.apply_tool("--batch-size", "2")
        self.assertEqual((code, report["failed"]), (1, "RuntimeError"))
        self.assertEqual(report["cursor"], ids[1])  # the last committed id, not further
        rows = self.rows()
        self.assertEqual([json.loads(rows[i]["legacy_json"]).get("format") for i in ids], [2, 2, None, None, None, None])
        self.assertEqual({i: rows[i] for i in ids[2:]}, {i: before[i] for i in ids[2:]})
        resumed, code = self.apply_tool("--batch-size", "2", "--after-id", str(report["cursor"]))
        self.assertEqual((code, len(resumed["minimized"])), (0, 4))
        again, _ = self.apply_tool()
        self.assertEqual((again["minimized"], again["already_minimal"]), ([], 6))

    def test_conflict_is_reported_left_and_reprocessed(self):
        ids = self.make(2)
        real = migration._srs_columns_shape
        holder = {"done": False}

        def changing(mode, before_text, after_text):
            result = real(mode, before_text, after_text)
            if not holder["done"]:
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_migration_snapshots SET srs_after_json = srs_after_json || ' ' "
                                       "WHERE id = ?", (ids[0],))
            return result

        real_min = migration.minimize_snapshots

        def wrapped(connection, *a, **k):
            holder["conn"] = connection
            return real_min(connection, *a, **k)

        with mock.patch.object(migration, "_srs_columns_shape", changing), \
                mock.patch.object(migration, "minimize_snapshots", wrapped):
            report, code = self.apply_tool()
        self.assertEqual(code, 0)
        self.assertEqual([e["id"] for e in report["conflicts"]], [ids[0]])
        self.assertIsNone(json.loads(self.rows()[ids[0]]["legacy_json"]).get("format"))  # not overwritten
        again, _ = self.apply_tool()
        self.assertEqual([e["id"] for e in again["minimized"]], [ids[0]])

    def test_rows_added_during_the_run_are_left_for_later(self):
        ids = self.make(2)
        real = migration._record_shape
        holder = {"done": False, "new": None}

        def adding(*a, **k):
            if not holder["done"]:
                holder["done"] = True
                cursor = holder["conn"].execute(
                    "INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                    "config_version, started_at) VALUES ('late', 'apply', 'completed', ?, 'fsrs', 'x', 'x', ?) RETURNING id",
                    (json.dumps({"user_id": self.user, "cards": []}), iso(NOW)))
                run = cursor.fetchone()["id"]
                holder["new"] = holder["conn"].execute(
                    "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                    "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                    "SELECT ?, user_id, card_kind, card_ref, card_version_before, legacy_json, srs_before_json, "
                    "srs_after_json, history_quality, history_flags, created_at FROM srs_migration_snapshots WHERE id = ? "
                    "RETURNING id", (run, ids[0])).fetchone()["id"]
            return real(*a, **k)

        real_min = migration.minimize_snapshots

        def wrapped(connection, *a, **k):
            holder["conn"] = connection
            return real_min(connection, *a, **k)

        with mock.patch.object(migration, "_record_shape", adding), mock.patch.object(migration, "minimize_snapshots", wrapped):
            report, _ = self.apply_tool("--batch-size", "1")
        self.assertEqual(report["upper_id"], ids[-1])
        self.assertNotIn(holder["new"], {e["id"] for e in report["minimized"]})
        self.assertIsNone(json.loads(self.rows()[holder["new"]]["legacy_json"]).get("format"))
        later, _ = self.apply_tool()
        self.assertEqual([e["id"] for e in later["minimized"]], [holder["new"]])


# ---------------------------------------------------------------------------
class RaceTests(ToolCase):
    def race(self, first, second, jobs, target, name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            if not entered.is_set() and threading.current_thread().name == first:
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(target, name, slow):
            a = race_support.start(first, jobs[first])
            self.assertTrue(entered.wait(15))
            b = race_support.start(second, jobs[second])
            self.assertTrue(probe.wait("waiting", second))
            time.sleep(0.3)
            self.assertNotIn(("acquired", second), probe.events)
            probe.mark("released", first)
            release.set()
            results = {first: race_support.finish(self, a), second: race_support.finish(self, b)}
        probe.assert_serialized(self, first, second)
        return results

    def tool_job(self):
        def run():
            with get_connection() as connection:
                return migration.minimize_snapshots(connection, self.user, apply=True,
                                                    lock=lambda c, u: storage.begin_card_write(c, u))
        return run

    def op_jobs(self, name, tag):
        if name == "review":
            ref = self.converted("personal", f"race-rv-{tag}")
            self.rate_at("personal", ref, NOW, "good")
            self.now = NOW
            version = self.card_row("personal", ref)["srs_card_version"]

            def op():
                with mock.patch.object(reviews, "now_utc", return_value=NOW + 3 * DAY):
                    return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-rv-{tag}",
                                                          expected_card_version=version, session_id="s1")
            return op, (reviews, "introduced_on"), ref
        if name == "plan_b":
            ref, _, _, at = self.to_plan_b("personal", name=f"race-pb-{tag}")
            version = self.card_row("personal", ref)["srs_card_version"]

            def op():
                with mock.patch.object(reviews, "now_utc", return_value=at):
                    return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-pb-{tag}",
                                                          expected_card_version=version, session_id="s1")
            return op, (reviews, "introduced_on"), ref
        if name == "rollback":
            ref = self.converted("personal", f"race-rb-{tag}")
            run = self.first_run("personal", ref)
            return (lambda: migration.rollback_plan(run, f"rb-race-{tag}", user_id=self.user, approved=True),
                    (migration, "_rollback_input"), ref)
        if name == "reconvert":
            ref, _ = self.card_with_records(f"race-re-{tag}")
            plan = migration.dry_run([self.key("personal", ref)])
            return (lambda: migration.apply_plan(plan, f"re-race-{tag}", approved=True), (migration, "record_intro"), ref)
        ref, _ = self.card_with_records(f"race-del-{tag}")
        return (lambda: vocab_repository.delete_vocab_item(self.user, ref), (migration, "strip_card_snapshots"), ref)

    def check(self, name, first):
        op, op_block, ref = self.op_jobs(name, first)
        jobs = {"tool": self.tool_job(), name: op}
        target = (migration, "_record_shape") if first == "tool" else op_block
        second = name if first == "tool" else "tool"
        results = self.race(first, second, jobs, *target)
        report = results["tool"]
        self.assertEqual(report["conflicts"], [])
        self.assertIsNotNone(results[name])
        for record in self.records("personal", ref):
            payload = json.loads(record["legacy_json"])
            if record["id"] <= report["upper_id"]:
                self.assertEqual(payload.get("format"), 2, (name, first, record["id"]))
        return results

    def test_review(self):
        for first in ("tool", "review"):
            with self.subTest(first=first):
                self.check("review", first)

    def test_plan_b_first_review(self):
        for first in ("tool", "plan_b"):
            with self.subTest(first=first):
                results = self.check("plan_b", first)
                self.assertEqual(results["plan_b"]["card_kind"], "personal")

    def test_rollback(self):
        for first in ("tool", "rollback"):
            with self.subTest(first=first):
                results = self.check("rollback", first)
                self.assertEqual(results["rollback"][0]["result"], "rolled_back")

    def test_reconvert(self):
        for first in ("tool", "reconvert"):
            with self.subTest(first=first):
                results = self.check("reconvert", first)
                self.assertEqual(results["reconvert"][0]["reconversion"], "restored")

    def test_delete(self):
        for first in ("tool", "delete"):
            with self.subTest(first=first):
                self.check("delete", first)


if __name__ == "__main__":
    unittest.main()
