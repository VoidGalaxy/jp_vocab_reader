"""Gate E-2c: the app's PostgreSQL connection wrapper ends its transaction through the
driver (commit / rollback), as sqlite3 connections do -- needed by the batched cleanup tools
(receipt minimize / purge, snapshot minimize, expired-run prune). No database here: a fake
driver connection records the calls.

The E-1 managed schema connection must keep refusing: under the wrapper, a commit, rollback
or close by app code still raises StepBoundaryViolation and nothing reaches the driver.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_adapter as adapter  # noqa: E402

from app.database import AppPostgresConnection  # noqa: E402


class FakeDriverConnection:
    def __init__(self):
        self.calls = []

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")

    def close(self):
        self.calls.append("close")

    def cursor(self):
        raise AssertionError("no statement expected")


class WrapperTransactionEndTests(unittest.TestCase):
    def test_commit_and_rollback_go_to_the_driver_once(self):
        raw = FakeDriverConnection()
        connection = AppPostgresConnection(raw)
        self.assertIsNone(connection.commit())
        self.assertIsNone(connection.rollback())
        self.assertEqual(raw.calls, ["commit", "rollback"])

    def test_driver_errors_are_not_hidden(self):
        class Failing(FakeDriverConnection):
            def commit(self):
                raise RuntimeError("commit failed")

            def rollback(self):
                raise RuntimeError("rollback failed")

        connection = AppPostgresConnection(Failing())
        with self.assertRaisesRegex(RuntimeError, "commit failed"):
            connection.commit()
        with self.assertRaisesRegex(RuntimeError, "rollback failed"):
            connection.rollback()

    def test_managed_step_connection_still_refuses_every_transaction_end(self):
        raw = FakeDriverConnection()
        connection = AppPostgresConnection(adapter.StepConnection(raw))
        for end in (connection.commit, connection.rollback, connection.close):
            with self.subTest(end.__name__), self.assertRaises(adapter.StepBoundaryViolation):
                end()
        self.assertEqual(raw.calls, [])  # nothing reached the managed connection


if __name__ == "__main__":
    unittest.main()
