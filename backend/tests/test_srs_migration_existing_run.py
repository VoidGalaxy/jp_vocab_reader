"""OPS_MIGRATION_RESUME_PLAN 9-2: `apply_plan(..., existing_run_only=True, expected_progress=...)` (P2).

Synthetic SQLite only: every test gets a throwaway database file made by the test (QueueCase). The
environment is fixed before anything from `app` is imported; no PostgreSQL, Neon, backend/vocab.db
or real data is touched. The expected values are computed here, independently of the product helper,
from the contract's own rules (UTF-8 SHA-256 of the stored texts, None for SQL NULL, the snapshot rows
of this run as [id, user_id, kind, ref] sorted by id, compact JSON). SQLite's `BEGIN IMMEDIATE` is not
evidence of PostgreSQL row locks.

Run directly:      python tests/test_srs_migration_existing_run.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

from test_srs_migration_new_run import NewRunCase  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402


def sha(text):
    return None if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


class ExistingRunCase(NewRunCase):
    def sql(self, query, params=()):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(query, params)
            connection.commit()
        finally:
            connection.close()

    def pre_read(self, run_key):
        """The caller's pre-read (contract 9-2), computed from the stored rows by the test itself."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute("SELECT * FROM srs_migration_runs WHERE run_key = ?", (run_key,)).fetchone()
            snaps = connection.execute("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots "
                                       "WHERE run_id = ? ORDER BY id", (row["id"],)).fetchall()
        finally:
            connection.close()
        listed = json.dumps([[r[0], r[1], r[2], r[3]] for r in snaps], separators=(",", ":"), ensure_ascii=True)
        return {"run_id": row["id"], "status": row["status"], "mode": row["mode"],
                "config_version": row["config_version"], "started_at": row["started_at"],
                "finished_at": row["finished_at"], "scope_sha256": sha(row["scope_json"]),
                "summary_sha256": sha(row["summary_json"]), "snapshots_sha256": sha(listed)}

    def resume(self, plan, key, expected, **kwargs):
        return migration.apply_plan(plan, key, approved=True, existing_run_only=True, expected_progress=expected,
                                    connect=self.connect, **kwargs)

    def card_row(self, card):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute("SELECT * FROM vocab_items WHERE id = ?", (card,)).fetchone()
        finally:
            connection.close()

    def snapshot_rows(self, key):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute("SELECT s.* FROM srs_migration_snapshots s JOIN srs_migration_runs r "
                                      "ON r.id = s.run_id WHERE r.run_key = ? ORDER BY s.id", (key,)).fetchall()
        finally:
            connection.close()

    def partial(self, names, key, done=1):
        cards = self.cards(*names)
        plan = self.plan(cards)
        migration.apply_plan(plan, key, approved=True, batch_size=done)
        return cards, plan


class Resumes(ExistingRunCase):
    def test_partial_run_resumes_and_keeps_committed_cards(self):
        outside = self.cards("outside")[0]
        theirs = self.cards("theirs", user=self.other)[0]
        cards, plan = self.partial(["a", "b", "c"], "run-res")
        first, first_snap = self.card_row(cards[0]), self.snapshot_rows("run-res")
        untouched = (self.card_row(outside), self.card_row(theirs))
        results = self.resume(plan, "run-res", self.pre_read("run-res"))
        self.assertEqual([r["result"] for r in results], ["already_applied", "applied", "applied"])
        self.assertEqual(self.card_row(cards[0]), first)                        # committed card untouched
        self.assertEqual(self.snapshot_rows("run-res")[:1], first_snap)          # its snapshot untouched
        self.assertEqual(len(self.snapshot_rows("run-res")), 3)
        self.assertEqual(self.run_row("run-res")["status"], "completed")
        self.assertEqual((self.card_row(outside), self.card_row(theirs)), untouched)

    def test_failed_run_resumes(self):
        cards = self.cards("f1", "f2", "f3")
        plan = self.plan(cards)
        real, seen = migration.update_card, []

        def fail_second(connection, key, version, values):
            seen.append(1)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real(connection, key, version, values)
        with mock.patch.object(migration, "update_card", fail_second), self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "run-failed", approved=True)
        self.assertEqual(self.run_row("run-failed")["status"], "failed")
        first = self.card_row(cards[0])
        results = self.resume(plan, "run-failed", self.pre_read("run-failed"))
        self.assertEqual([r["result"] for r in results], ["already_applied", "applied", "applied"])
        self.assertEqual(self.card_row(cards[0]), first)
        self.assertEqual(self.run_row("run-failed")["status"], "completed")

    def test_comparison_happens_after_the_lock_and_before_the_window(self):
        cards, plan = self.partial(["o1", "o2"], "run-order")
        order = []
        lock, values, window = migration.begin_card_write, migration.run_progress_values, migration._require_window

        def logged(name, fn):
            def call(*a, **k):
                order.append(name)
                return fn(*a, **k)
            return call
        with mock.patch.object(migration, "begin_card_write", logged("lock", lock)), \
                mock.patch.object(migration, "run_progress_values", logged("compare", values)), \
                mock.patch.object(migration, "_require_window", logged("window", window)):
            self.resume(plan, "run-order", self.pre_read("run-order"))
        self.assertEqual(order[:3], ["lock", "compare", "window"])


class RefusedWithoutWrites(ExistingRunCase):
    def refused_resume(self, code, plan, key, expected):
        before = self.dump()
        self.calls.clear()
        with self.assertRaises(SrsWriteError) as caught:
            self.resume(plan, key, expected)
        self.assertEqual((caught.exception.code, caught.exception.args), (code, (code,)))
        self.assertEqual(self.dump(), before)                    # no run, card, snapshot or config change
        self.assertEqual(self.calls, [False])                    # one (first) connection, rolled back

    def test_missing_run_is_never_created(self):
        cards, plan = self.partial(["m1", "m2"], "run-exists")
        expected = self.pre_read("run-exists")
        self.refused_resume("migration_run_missing", plan, "run-other-key", expected)
        with database.get_connection() as c:
            self.assertIsNone(c.execute("SELECT id FROM srs_migration_runs WHERE run_key = ?",
                                        ("run-other-key",)).fetchone())

    def test_states_that_cannot_resume(self):
        cards, plan = self.partial(["s1", "s2"], "run-done", done=2)            # completed
        expected = dict(self.pre_read("run-done"), status="started")
        self.refused_resume("migration_run_not_resumable", plan, "run-done", expected)
        self.sql("UPDATE srs_migration_runs SET status = 'started', finished_at = NULL WHERE run_key = 'run-done'")
        self.refused_resume("migration_run_not_resumable", plan, "run-done", self.pre_read("run-done"))  # cursor end
        cards, plan = self.partial(["s3", "s4"], "run-closed")
        expected = self.pre_read("run-closed")
        self.sql("UPDATE srs_migration_runs SET status = 'aborted' WHERE run_key = 'run-closed'")
        self.refused_resume("migration_run_closed", plan, "run-closed", expected)

    def test_scope_account_and_config_mismatch(self):
        cards, plan = self.partial(["c1", "c2"], "run-scope")
        expected = self.pre_read("run-scope")
        self.refused_resume("migration_run_conflict", self.plan(self.cards("c3", "c4")), "run-scope", expected)
        theirs = self.cards("t1", "t2", user=self.other)
        self.refused_resume("migration_run_conflict", self.plan(theirs, user=self.other), "run-scope", expected)
        self.sql("UPDATE srs_migration_runs SET config_version = 'other-config' WHERE run_key = 'run-scope'")
        self.refused_resume("migration_run_conflict", plan, "run-scope", self.pre_read("run-scope"))

    def test_summary_snapshot_and_row_changes_are_refused(self):
        changes = {
            "summary text": "UPDATE srs_migration_runs SET summary_json = summary_json || ' ' WHERE id = :run",
            "snapshot added": "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, "
                              "card_version_before, legacy_json, created_at) SELECT run_id, user_id, card_kind, "
                              "card_ref + 1000, card_version_before, legacy_json, created_at "
                              "FROM srs_migration_snapshots WHERE run_id = :run",
            "snapshot deleted": "DELETE FROM srs_migration_snapshots WHERE run_id = :run",
            "snapshot replaced": None,
            "started_at text": "UPDATE srs_migration_runs SET started_at = replace(started_at, '+00:00', 'Z') "
                               "WHERE id = :run",
            "status started -> failed": "UPDATE srs_migration_runs SET status = 'failed' WHERE id = :run",
            "finished_at set": "UPDATE srs_migration_runs SET finished_at = '2026-10-01T00:00:00+00:00' "
                               "WHERE id = :run",
        }
        for n, (label, statement) in enumerate(changes.items()):
            with self.subTest(change=label):
                key = f"run-x{n}"
                cards, plan = self.partial([f"x{n}a", f"x{n}b", f"x{n}c"], key)
                expected = self.pre_read(key)
                run = {"run": expected["run_id"]}
                if statement is None:                     # same card, new snapshot row id (delete, re-insert)
                    connection = sqlite3.connect(self.db_path)
                    try:
                        connection.execute("CREATE TEMP TABLE kept AS SELECT * FROM srs_migration_snapshots "
                                           "WHERE run_id = :run", run)
                        connection.execute("DELETE FROM srs_migration_snapshots WHERE run_id = :run", run)
                        connection.execute("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, "
                                           "card_ref, card_version_before, legacy_json, srs_before_json, "
                                           "srs_after_json, history_quality, history_flags, created_at) SELECT "
                                           "run_id, user_id, card_kind, card_ref, card_version_before, legacy_json, "
                                           "srs_before_json, srs_after_json, history_quality, history_flags, "
                                           "created_at FROM kept")
                        connection.commit()
                    finally:
                        connection.close()
                else:
                    self.sql(statement, run)
                self.refused_resume("migration_run_changed", plan, key, expected)

    def test_a_normal_cursor_advance_is_also_refused(self):
        cards, plan = self.partial(["n1", "n2", "n3"], "run-n")
        expected = self.pre_read("run-n")
        migration.apply_plan(plan, "run-n", approved=True, batch_size=1)     # another caller moved the cursor
        self.refused_resume("migration_run_changed", plan, "run-n", expected)

    def test_other_runs_snapshots_do_not_count(self):
        cards, plan = self.partial(["o1", "o2"], "run-mine")
        self.partial(["o3", "o4"], "run-theirs")
        expected = self.pre_read("run-mine")
        theirs = self.pre_read("run-theirs")["run_id"]
        self.sql("DELETE FROM srs_migration_snapshots WHERE run_id = ?", (theirs,))
        results = self.resume(plan, "run-mine", expected)
        self.assertEqual([r["result"] for r in results], ["already_applied", "applied"])


class InputContract(ExistingRunCase):
    def bad(self, code, plan, **kwargs):
        before = self.dump()
        self.calls.clear()
        with self.assertRaises(SrsWriteError) as caught:
            migration.apply_plan(plan, "run-in", approved=True, connect=self.connect, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual((self.calls, self.dump()), ([], before))      # nothing opened, nothing changed

    def test_types_combinations_and_shapes_open_no_connection(self):
        cards, plan = self.partial(["i1", "i2"], "run-in")
        good = self.pre_read("run-in")
        for value in (1, 0, "true", None, [True]):
            self.bad("invalid_existing_run_only", plan, existing_run_only=value, expected_progress=good)
        self.bad("invalid_run_mode", plan, new_run_only=True, existing_run_only=True, expected_progress=good)
        self.bad("invalid_run_mode", plan, expected_progress=good)
        self.bad("invalid_run_mode", plan, existing_run_only=False, expected_progress=good)
        self.bad("invalid_expected_progress", plan, existing_run_only=True)
        broken = [dict(good, run_id=str(good["run_id"])), dict(good, run_id=True), dict(good, run_id=0),
                  dict(good, status="completed"), dict(good, status="aborted"), dict(good, mode="dry_run"),
                  dict(good, config_version=""), dict(good, started_at=None), dict(good, started_at=1),
                  dict(good, finished_at=""), dict(good, scope_sha256=good["scope_sha256"].upper()),
                  dict(good, summary_sha256="0" * 63), dict(good, snapshots_sha256=None),
                  {k: v for k, v in good.items() if k != "finished_at"}, dict(good, extra=1), list(good.items()),
                  None]
        for value in broken:
            with self.subTest(value=repr(value)[:60]):
                self.bad("invalid_expected_progress", plan, existing_run_only=True, expected_progress=value)


class DefaultPathsKept(ExistingRunCase):
    def test_omitted_arguments_keep_resume_recall_and_first_run(self):
        cards, plan = self.partial(["k1", "k2"], "run-keep")
        resumed = migration.apply_plan(plan, "run-keep", approved=True)
        self.assertEqual([r["result"] for r in resumed], ["already_applied", "applied"])
        before = self.dump()
        recalled = migration.apply_plan(plan, "run-keep", approved=True)
        self.assertEqual([r["result"] for r in recalled], ["already_applied", "already_applied"])
        self.assertEqual(self.dump(), before)
        with self.assertRaises(SrsWriteError) as caught:
            migration.apply_plan(plan, "run-keep", approved=True, new_run_only=True)
        self.assertEqual(caught.exception.code, "migration_run_exists")
        fresh = migration.apply_plan(self.plan(self.cards("k3")), "run-new", approved=True, new_run_only=True)
        self.assertEqual([r["result"] for r in fresh], ["applied"])


if __name__ == "__main__":
    unittest.main()
