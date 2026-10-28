"""Gate E-6: safety / correctness checks of the read benchmark (tests/e6_read_benchmark.py) on a
small synthetic SQLite world (session files only; no vocab.db)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import e6_read_benchmark as e6  # noqa: E402

SMALL = 40


class Small(e6.BenchCase, unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e6_", dir=e6.BACKEND)
        self.addCleanup(self.directory.cleanup)
        self.use("a.db")

    def use(self, name):
        from app.database import init_db

        self.db_path = Path(self.directory.name) / name
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
                                           "JWT_SECRET_KEY": e6.SECRET})
        env.start()
        self.addCleanup(env.stop)
        with e6.fixed_clock(e6.Clock(e6.T_CREATE)):
            init_db()

    def test_generation_shortcuts_write_exactly_what_the_plain_app_paths_write(self):
        e6.build_world(SMALL, fast=True)
        fast = self.content_hash()
        self.use("b.db")
        e6.build_world(SMALL, fast=False)       # own connection per call, full introduced read
        self.assertEqual(self.content_hash(), fast)
        self.assertGreater(fast["srs_review_receipts"][0], 0)

    def test_small_world_passes_every_check_and_is_unchanged_by_the_timing(self):
        record = self.run_size(SMALL)
        self.assertTrue(record["unchanged_after"])
        self.assertEqual(set(record["requests"]), set(e6.scenarios(record["expected"])))
        self.assertTrue(all(v["n"] == e6.REPEAT for v in record["requests"].values()))
        self.assertTrue(all(d["statements"] > 0 for d in record["diagnostic"].values()))

    def test_expectation_check_catches_a_card_in_another_state(self):
        exp = e6.build_world(SMALL)["expected"]
        with e6.fixed_clock(e6.Clock(e6.T_REF)), mock.patch.dict(os.environ, {"JWT_SECRET_KEY": e6.SECRET}):
            client = e6.Client(exp["user_id"])
            try:
                answers = lambda: {n: client.get(p, q).json() for n, (p, q) in e6.scenarios(exp).items()}  # noqa: E731
                self.assertEqual(e6.check_expectations(exp, answers()), [])
                moved = exp["due_now_all"][0]          # a due card, now due next year
                self.sql("UPDATE vocab_items SET srs_due_at = ?, srs_effective_due_at = ? WHERE id = ?",
                         ("2027-10-20T00:00:00+00:00", "2027-10-20T00:00:00+00:00", moved))
                bad = e6.check_expectations(exp, answers())
            finally:
                client.close()
        self.assertTrue(any(line.startswith("due_now_all") for line in bad), bad)
        self.assertTrue(any(line.startswith("queue_all.counts") for line in bad), bad)

    def test_timed_reads_cannot_write(self):
        e6.build_world(SMALL)
        with self.read_only():
            with self.assertRaises(Exception):
                self.sql("UPDATE users SET display_name = 'x'")
        self.sql("UPDATE users SET display_name = display_name")      # writable again afterwards


class ConnectionTiming(unittest.TestCase):
    """The PG connection diagnostic only times: the guard still runs, every connection is
    counted once, nested levels are kept apart, and everything is restored afterwards."""

    def test_counts_and_times_without_changing_the_guarded_hand_over(self):
        import _srs_e2_adapter as adapter
        from app import database

        calls = []

        class FakeRun:
            def _connect(self, url, **kwargs):
                calls.append("driver")
                time.sleep(0.002)
                return mock.MagicMock()

            def _guarded_connect(self, url, **kwargs):
                calls.append("preflight")
                return self._connect(url, **kwargs)

            def verify_app_connection(self, connection):
                calls.append("verify")
                time.sleep(0.001)

        run = FakeRun()
        guarded = adapter._GuardedPsycopg(object(), run)
        diag = e6.ConnectionDiagnostics(run)
        originals = (adapter._GuardedPsycopg.connect, database.AppPostgresConnection.__exit__)
        with diag.active():
            for _ in range(2):
                guarded.connect("postgresql://x")
            took = diag.take()
        self.assertEqual(calls, ["preflight", "driver", "verify"] * 2)       # nothing skipped
        self.assertEqual(took["connections"], 2)
        self.assertGreaterEqual(took["open_ms"], took["guarded_ms"] + took["verify_ms"] - 0.5)
        self.assertGreaterEqual(took["guarded_ms"], took["driver_ms"])
        self.assertGreater(took["driver_ms"], 0)
        self.assertEqual(diag.take()["connections"], 0)                         # cleared per request
        self.assertEqual((adapter._GuardedPsycopg.connect, database.AppPostgresConnection.__exit__), originals)
        self.assertNotIn("_guarded_connect", vars(run))                          # restored on the run too


if __name__ == "__main__":
    unittest.main()
