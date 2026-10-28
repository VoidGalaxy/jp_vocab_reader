"""(Named to sort AFTER test_stats_history: that module and test_learning_plan_progress set
DATABASE_URL when imported, and the existing suite relies on test_stats_history being imported
last. Importing it earlier from here changed the SQLite run; this name keeps the order.)

Gate E-2b: PostgreSQL stand-ins for SQLite-only mechanics in existing tests. Run ONLY
through _srs_pg_suite.py (real PostgreSQL); on SQLite every test here is skipped.

- StatsHistoryOnPostgres: test_stats_history inserts logs / words for accounts 101 and 202,
  deck 1 and lexemes 1 and 7 without creating them -- SQLite's tables there have no FK to
  them; PostgreSQL's do. The same tests run after those referenced rows are created
  (explicit ids; nothing else changes). The stats code is read-only over them.
- QueueOneReadOnPostgres: test_srs_queue checks "list, counts and goal come from one read"
  by showing a concurrent review WAITS for the read -- SQLite's lock. PostgreSQL reads the
  queue in one REPEATABLE READ snapshot instead, so the review is NOT blocked; the contract
  is the consistency itself. Same overlap, same synthetic card and clock; the control (no
  snapshot) must show the inconsistency on PostgreSQL too, so the check is meaningful.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import test_srs_d2_u11_completion as u11_tests  # noqa: E402
import test_srs_queue as queue_tests  # noqa: E402
import test_stats_history as stats_tests  # noqa: E402

from app.database import get_connection, get_database_engine  # noqa: E402


def _postgres() -> bool:
    return get_database_engine() == "postgresql"


def _only_these(cls, keep):
    for name in dir(cls):
        if name.startswith("test") and name not in keep:
            setattr(cls, name, None)
    return cls


class StatsHistoryOnPostgres(stats_tests.StatsHistoryTests):
    def setUp(self):
        if not _postgres():
            self.skipTest("PostgreSQL stand-in (run through _srs_pg_suite.py)")
        stamp = "2026-01-01T00:00:00+00:00"
        with get_connection() as connection:
            for user in (stats_tests.USER, stats_tests.OTHER_USER):
                connection.execute(
                    "INSERT INTO users (id, email, display_name, password_hash, auth_provider, created_at, updated_at) "
                    "VALUES (?, ?, 'synthetic', 'x', 'local', ?, ?) ON CONFLICT (id) DO NOTHING",
                    (user, f"stats-{user}@example.test", stamp, stamp))
            connection.execute("INSERT INTO decks (id, user_id, name, description, created_at, updated_at) "
                               "VALUES (1, ?, 'stats deck', '', ?, ?) ON CONFLICT (id) DO NOTHING",
                               (stats_tests.USER, stamp, stamp))
            for lexeme in (1, 7):
                connection.execute(
                    "INSERT INTO lexemes (id, surface, base_form, reading, part_of_speech, source_type, created_at, "
                    "updated_at) VALUES (?, ?, ?, '', '', 'shared_deck', ?, ?) ON CONFLICT (id) DO NOTHING",
                    (lexeme, f"stats-lx{lexeme}", f"stats-lx{lexeme}", stamp, stamp))
        super().setUp()


class QueueOneReadOnPostgres(queue_tests.QueueUnitConsistencyAndWriteTests):
    def setUp(self):
        if not _postgres():
            self.skipTest("PostgreSQL stand-in (run through _srs_pg_suite.py)")
        super().setUp()

    def test_list_counts_and_goal_come_from_one_read_on_postgres(self):
        item, result, state = self._overlap(snapshot_enabled=True)
        # MVCC: the review is not blocked by the read (the SQLite test asserts it waits)
        self.assertTrue(state["writer_done_during_read"])
        # ...but the read is ONE snapshot: list, counts and goal all from before the review
        self.assertEqual(self.keys(result), [("personal", item)])
        self.assertEqual(result["counts"]["new_available"], 1)
        self.assertEqual(result["new_goal"]["introduced_today"], 0)
        self.assertIsNotNone(state["result"])
        self.assertEqual(self.q()["new_goal"]["introduced_today"], 1)

    def test_control_without_the_snapshot_is_inconsistent_on_postgres(self):
        item, result, state = self._overlap(snapshot_enabled=False)
        self.assertTrue(state["writer_done_during_read"])
        self.assertEqual(self.keys(result), [("personal", item)])     # listed as new...
        self.assertEqual(result["new_goal"]["introduced_today"], 1)   # ...yet already counted


class HalfPairOnPostgres(u11_tests.ReviewPathTests):
    """test_srs_d2_u11_completion expects sqlite3.IntegrityError for a half (time, version)
    pair; on PostgreSQL the same CHECK raises CheckViolation. Both halves, same card."""

    def setUp(self):
        if not _postgres():
            self.skipTest("PostgreSQL stand-in (run through _srs_pg_suite.py)")
        super().setUp()

    def test_half_pair_is_rejected_by_the_database_on_postgres(self):
        import psycopg

        ref, _ = self.subject("personal", "half")
        for values in (dict(version_first_completed_at=u11_tests.iso(u11_tests.NOW)),
                       dict(version_first_completed_version=u11_tests.METRIC_VERSION)):
            with self.subTest(values=values), self.assertRaises(psycopg.errors.CheckViolation):
                self.set_cols("personal", ref, **values)
        with get_connection() as c:
            row = c.execute("SELECT version_first_completed_at, version_first_completed_version FROM vocab_items "
                            "WHERE id = ?", (ref,)).fetchone()
        self.assertEqual((row["version_first_completed_at"], row["version_first_completed_version"]), (None, None))


_only_these(HalfPairOnPostgres, {"test_half_pair_is_rejected_by_the_database_on_postgres"})

_only_these(QueueOneReadOnPostgres, {"test_list_counts_and_goal_come_from_one_read_on_postgres",
                                     "test_control_without_the_snapshot_is_inconsistent_on_postgres"})

if __name__ == "__main__":
    unittest.main()
