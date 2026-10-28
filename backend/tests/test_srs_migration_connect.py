"""OPS_MIGRATION_CLI_PLAN 6-1: the optional connection function of dry_run / apply_plan.

Synthetic SQLite only: every test gets a throwaway database file made by the test (QueueCase).
The environment is fixed before anything from `app` is imported; no PostgreSQL, Neon,
backend/vocab.db or real data is touched.

Run directly:      python tests/test_srs_migration_connect.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_intro import IntroCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402


def forbidden(*_, **__):
    raise AssertionError("the default get_connection was used although a function was injected")


class ConnectCase(IntroCase):
    def setUp(self):
        super().setUp()
        self.calls: list[bool] = []

    def connect(self, *, read_only=False):
        """Test connection function: the real app connection to this test's synthetic file."""
        self.calls.append(read_only)
        return database.get_connection(read_only=read_only)

    def cards(self, *names):
        return [self.past_card(name, iso(NOW - timedelta(days=5))) for name in names]

    def keys(self, cards):
        return [CardKey("personal", self.user, card) for card in cards]

    def dump(self) -> list[str]:
        """Every row of the synthetic file, read outside the app."""
        connection = sqlite3.connect(self.db_path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def run_row(self, run_key):
        with database.get_connection() as c:
            row = c.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = ?",
                            (run_key,)).fetchone()
        return dict(row)

    def engine(self, card):
        with database.get_connection() as c:
            return c.execute("SELECT srs_engine FROM vocab_items WHERE id = ?", (card,)).fetchone()[0]


class DryRun(ConnectCase):
    def test_injected_read_only_and_no_writes(self):
        keys = self.keys(self.cards("a", "b"))
        before = self.dump()
        with mock.patch.object(migration, "get_connection", forbidden):
            plan = migration.dry_run(keys, connect=self.connect)
        self.assertEqual(self.calls, [True])
        self.assertEqual(self.dump(), before)
        self.assertEqual(plan, migration.dry_run(keys))                  # same result without injection

    def test_bad_function_is_refused_before_any_connection(self):
        keys = self.keys(self.cards("a"))
        for value in ("connect", 7, object()):
            with self.subTest(value=type(value).__name__), mock.patch.object(migration, "get_connection", forbidden):
                with self.assertRaises(SrsWriteError) as caught:
                    migration.dry_run(keys, connect=value)
                self.assertEqual(caught.exception.args[0] if caught.exception.args else None,
                                 "invalid_connection_factory")


class Apply(ConnectCase):
    def plan(self, cards):
        return migration.dry_run(self.keys(cards))

    def test_every_apply_connection_goes_through_the_function(self):
        cards = self.cards("a", "b")
        plan = self.plan(cards)
        with mock.patch.object(migration, "get_connection", forbidden):
            results = migration.apply_plan(plan, "run-connect", approved=True, connect=self.connect)
        self.assertEqual(self.calls, [False] * 4)                     # start, two cards, finish
        self.assertEqual([r["result"] for r in results], ["applied", "applied"])
        self.assertEqual(self.run_row("run-connect")["status"], "completed")
        self.assertEqual([self.engine(c) for c in cards], ["fsrs", "fsrs"])

    def test_failure_mark_resume_and_completed_recall(self):
        cards = self.cards("a", "b", "c")
        plan = self.plan(cards)
        real_update = migration.update_card
        seen = []

        def fail_second(connection, key, version, values):
            seen.append(key.ref_id)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real_update(connection, key, version, values)
        with mock.patch.object(migration, "get_connection", forbidden), \
                mock.patch.object(migration, "update_card", fail_second):
            with self.assertRaises(RuntimeError):
                migration.apply_plan(plan, "run-fail", approved=True, connect=self.connect)
        self.assertEqual(self.calls, [False] * 4)                     # start, card 1, card 2 (failed), failure mark
        row = self.run_row("run-fail")
        self.assertEqual((row["status"], migration.json.loads(row["summary_json"])["cursor"]), ("failed", 1))
        self.assertEqual([self.engine(c) for c in cards], ["fsrs", "legacy", "legacy"])   # card 2 rolled back
        self.calls.clear()
        with mock.patch.object(migration, "get_connection", forbidden):
            results = migration.apply_plan(plan, "run-fail", approved=True, connect=self.connect)
        self.assertEqual(self.calls, [False] * 4)                     # start, cards 2 and 3, finish
        self.assertEqual([r["result"] for r in results], ["already_applied", "applied", "applied"])
        self.assertEqual(self.run_row("run-fail")["status"], "completed")
        self.assertEqual([self.engine(c) for c in cards], ["fsrs", "fsrs", "fsrs"])
        before = self.dump()
        self.calls.clear()
        with mock.patch.object(migration, "get_connection", forbidden):
            again = migration.apply_plan(plan, "run-fail", approved=True, connect=self.connect)
        self.assertEqual(self.calls, [False])                         # start only
        self.assertEqual([r["result"] for r in again], ["already_applied"] * 3)
        self.assertEqual(self.dump(), before)                         # no row changed

    def test_batches_and_window_unchanged(self):
        cards = self.cards("a", "b")
        plan = self.plan(cards)
        with mock.patch.object(migration, "get_connection", forbidden):
            first = migration.apply_plan(plan, "run-batch", approved=True, batch_size=1, connect=self.connect)
        self.assertEqual((self.calls, len(first)), ([False] * 3, 1))   # start, one card, finish (marks nothing)
        self.assertEqual(self.run_row("run-batch")["status"], "started")
        late = migration.now_utc() + migration.ROLLBACK_WINDOW + timedelta(days=1)
        self.calls.clear()
        with mock.patch.object(migration, "get_connection", forbidden), \
                mock.patch.object(migration, "now_utc", return_value=late):
            with self.assertRaises(Exception) as caught:
                migration.apply_plan(plan, "run-batch", approved=True, connect=self.connect)
        self.assertIn("window", str(caught.exception.args[0] if caught.exception.args else caught.exception))
        self.assertEqual(self.calls, [False])
        self.assertEqual(self.run_row("run-batch")["status"], "started")  # a closed window changes no status

    def test_without_injection_the_result_is_the_same(self):
        default_cards, injected_cards = self.cards("a", "b"), self.cards("c", "d")
        default = migration.apply_plan(self.plan(default_cards), "run-default", approved=True)
        self.assertEqual(self.calls, [])
        with mock.patch.object(migration, "get_connection", forbidden):
            injected_plan = migration.dry_run(self.keys(injected_cards), connect=self.connect)
            injected = migration.apply_plan(injected_plan, "run-injected", approved=True, connect=self.connect)

        def shape(results):
            return [{k: v for k, v in r.items() if k != "ref_id"} for r in results]
        self.assertEqual(shape(default), shape(injected))
        self.assertEqual(self.run_row("run-default")["status"], self.run_row("run-injected")["status"])
        with database.get_connection() as c:
            rows = {card: dict(c.execute("SELECT srs_engine, srs_state, srs_due_at, srs_history_quality, "
                                         "srs_participation FROM vocab_items WHERE id = ?", (card,)).fetchone())
                    for card in default_cards + injected_cards}
        self.assertEqual([rows[c] for c in default_cards], [rows[c] for c in injected_cards])

    def test_bad_function_is_refused_before_any_connection(self):
        plan = self.plan(self.cards("a"))
        before = self.dump()
        with mock.patch.object(migration, "get_connection", forbidden):
            with self.assertRaises(SrsWriteError):
                migration.apply_plan(plan, "run-bad", approved=True, connect="not callable")
        self.assertEqual(self.dump(), before)


if __name__ == "__main__":
    unittest.main()
