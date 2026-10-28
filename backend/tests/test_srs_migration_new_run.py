"""OPS_MIGRATION_CLI_PLAN 4-4-2-1: `apply_plan(..., new_run_only=True)` -- first-run guarantee (P1).

Synthetic SQLite only: every test gets a throwaway database file made by the test (QueueCase). The
environment is fixed before anything from `app` is imported; no PostgreSQL, Neon, backend/vocab.db
or real data is touched. The race test uses two threads with their own SQLite connections; the
order is shown by timestamps around the real account lock, not by a sleep or a fake return value.

Run directly:      python tests/test_srs_migration_new_run.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import sqlite3  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

from test_srs_d2_intro import IntroCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402


class NewRunCase(IntroCase):
    def setUp(self):
        super().setUp()
        self.calls: list[bool] = []

    def connect(self, *, read_only=False):
        self.calls.append(read_only)
        return database.get_connection(read_only=read_only)

    def cards(self, *names, user=None):
        return [self.past_card(name, iso(NOW - timedelta(days=5)), user=user) for name in names]

    def plan(self, cards, user=None):
        return migration.dry_run([CardKey("personal", user or self.user, c) for c in cards])

    def dump(self) -> list[str]:
        connection = sqlite3.connect(self.db_path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def run_row(self, run_key):
        with database.get_connection() as c:
            return dict(c.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = ?",
                                  (run_key,)).fetchone())

    def refused(self, code, plan, run_key, **kwargs):
        before = self.dump()
        with self.assertRaises(SrsWriteError) as caught:
            migration.apply_plan(plan, run_key, approved=True, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.args, (code,))                 # no state, account or cursor in it
        self.assertEqual(self.dump(), before)                             # no run, card, snapshot or config change
        return caught.exception


class NewRunOnly(NewRunCase):
    def test_new_key_is_applied_normally(self):
        cards = self.cards("a", "b")
        results = migration.apply_plan(self.plan(cards), "run-new", approved=True, connect=self.connect,
                                       new_run_only=True)
        self.assertEqual([r["result"] for r in results], ["applied", "applied"])
        self.assertEqual(self.calls, [False] * 4)                         # start, two cards, finish: all allowed
        self.assertEqual(self.run_row("run-new")["status"], "completed")

    def test_existing_runs_of_any_state_are_refused(self):
        started = self.cards("s1", "s2")
        migration.apply_plan(self.plan(started), "run-started", approved=True, batch_size=1)
        failed = self.cards("f1", "f2")
        real, seen = migration.update_card, []

        def fail_second(connection, key, version, values):
            seen.append(1)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real(connection, key, version, values)
        with mock.patch.object(migration, "update_card", fail_second), self.assertRaises(RuntimeError):
            migration.apply_plan(self.plan(failed), "run-failed", approved=True)
        done = self.cards("c1")
        migration.apply_plan(self.plan(done), "run-done", approved=True)
        aborted = self.cards("x1")
        migration.apply_plan(self.plan(aborted), "run-aborted", approved=True)
        with database.get_connection() as c:                              # a closed run (state injection)
            c.execute("UPDATE srs_migration_runs SET status = 'aborted' WHERE run_key = 'run-aborted'")
        for run_key, cards, status in (("run-started", started, "started"), ("run-failed", failed, "failed"),
                                       ("run-done", done, "completed"), ("run-aborted", aborted, "aborted")):
            with self.subTest(status=status):
                self.assertEqual(self.run_row(run_key)["status"], status)
                self.calls.clear()
                self.refused("migration_run_exists", self.plan(cards), run_key, connect=self.connect,
                             new_run_only=True)
                self.assertEqual(self.calls, [False])                     # the first connection only
        other_scope = self.cards("o1")
        self.refused("migration_run_exists", self.plan(other_scope), "run-done", new_run_only=True)

    def test_other_accounts_key_is_refused_without_details(self):
        theirs = self.cards("t1", user=self.other)
        migration.apply_plan(self.plan(theirs, user=self.other), "run-shared", approved=True)
        mine = self.cards("m1")
        error = self.refused("migration_run_exists", self.plan(mine), "run-shared", new_run_only=True)
        self.assertNotIn(str(self.other), repr(error) + str(error))

    def test_false_and_omitted_keep_resume_and_recall(self):
        for flag in ({}, {"new_run_only": False}):
            with self.subTest(flag=flag):
                cards = self.cards(*(f"r{len(flag)}{i}" for i in range(2)))
                plan, key = self.plan(cards), f"run-keep-{len(flag)}"
                first = migration.apply_plan(plan, key, approved=True, batch_size=1, **flag)
                self.assertEqual([r["result"] for r in first], ["applied"])
                resumed = migration.apply_plan(plan, key, approved=True, **flag)
                self.assertEqual([r["result"] for r in resumed], ["already_applied", "applied"])
                before = self.dump()
                recalled = migration.apply_plan(plan, key, approved=True, **flag)
                self.assertEqual([r["result"] for r in recalled], ["already_applied", "already_applied"])
                self.assertEqual(self.dump(), before)

    def test_invalid_types_open_no_connection(self):
        plan = self.plan(self.cards("v1"))
        for value in (1, 0, "true", None, [True]):
            with self.subTest(value=repr(value)):
                self.calls.clear()
                self.refused("invalid_new_run_only", plan, "run-type", connect=self.connect, new_run_only=value)
                self.assertEqual(self.calls, [])

    def test_failure_after_a_new_start_keeps_partial_commit(self):
        cards = self.cards("p1", "p2")
        real, seen = migration.update_card, []

        def fail_second(connection, key, version, values):
            seen.append(1)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real(connection, key, version, values)
        with mock.patch.object(migration, "update_card", fail_second), self.assertRaises(RuntimeError):
            migration.apply_plan(self.plan(cards), "run-partial", approved=True, new_run_only=True)
        row = self.run_row("run-partial")
        self.assertEqual((row["status"], migration.json.loads(row["summary_json"])["cursor"]), ("failed", 1))


class Race(NewRunCase):
    """Two threads, two SQLite connections, the same account and key, both new_run_only=True."""

    def test_only_one_first_call_creates_the_run(self):
        cards = self.cards("q1", "q2")
        plan = self.plan(cards)
        real_lock = migration.begin_card_write
        log: list[tuple[str, str, float]] = []
        b_requesting = threading.Event()
        lock_count = {"A": 0, "B": 0}

        def lock(connection, user_id, **kwargs):
            name = threading.current_thread().name
            first = lock_count[name] == 0
            lock_count[name] += 1
            if first:
                log.append((name, "lock_request", time.monotonic()))
                if name == "B":
                    b_requesting.set()
            real_lock(connection, user_id, **kwargs)
            if first:
                log.append((name, "lock_acquired", time.monotonic()))
                if name == "A":
                    self.assertTrue(b_requesting.wait(10))                # B is about to wait on the real lock

        def connect(*, read_only=False):
            context = database.get_connection(read_only=read_only)
            name = threading.current_thread().name

            class Tracked:
                def __enter__(self):
                    return context.__enter__()

                def __exit__(self, *exc):
                    try:
                        return context.__exit__(*exc)
                    finally:
                        log.append((name, "connection_closed", time.monotonic()))
            return Tracked()

        outcomes: dict[str, object] = {}

        def call(name):
            try:
                outcomes[name] = migration.apply_plan(plan, "run-race", approved=True, connect=connect,
                                                      new_run_only=True)
            except Exception as error:                                     # recorded, judged below
                outcomes[name] = error

        with mock.patch.object(migration, "begin_card_write", lock):
            a = threading.Thread(target=call, args=("A",), name="A")
            a.start()
            while not any(n == "A" and e == "lock_acquired" for n, e, _ in log):
                if not a.is_alive():
                    break
                time.sleep(0.005)                                         # polling only; the proof is the log
            b = threading.Thread(target=call, args=("B",), name="B")
            b.start()
            a.join(30)
            b.join(30)
        self.assertIsInstance(outcomes["A"], list)
        self.assertIsInstance(outcomes["B"], SrsWriteError)
        self.assertEqual(outcomes["B"].code, "migration_run_exists")
        times = {(n, e): t for n, e, t in log if e != "connection_closed"}
        a_first_close = next(t for n, e, t in log if n == "A" and e == "connection_closed")
        self.assertLess(times[("B", "lock_request")], a_first_close)      # B asked while A held the lock
        self.assertGreater(times[("B", "lock_acquired")], a_first_close)  # and got it only after A's first commit
        with database.get_connection() as c:
            count = c.execute("SELECT COUNT(*) FROM srs_migration_runs WHERE run_key = 'run-race'").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(self.run_row("run-race")["status"], "completed")


if __name__ == "__main__":
    unittest.main()
