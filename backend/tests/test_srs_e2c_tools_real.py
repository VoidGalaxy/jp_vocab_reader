"""Gate E-2c: the three approved cleanup functions on REAL PostgreSQL (E-1 harness, E-2
adapter, limited role, opt-in only).

Before E-2c (REPORT 16-5, reproduced again at the start of E-2c): minimize_receipts raised
AttributeError (no commit on the PostgreSQL wrapper); minimize_snapshots and
prune_expired_runs raised KeyError: 0 (positional read of a dict row). These checks pin the
repaired behaviour:
- each function runs in dry-run and apply mode on a real account (receipts and snapshots
  written by the app's own review / migration paths) and returns its report;
- a commit failure is raised, never turned into a result; the batch rolls back and the
  reported cursor stays at the last committed position;
- the managed schema connection still refuses commit / rollback / close from app code
  under the wrapper (nothing created, run not stopped).
The behaviour of the batches themselves (CAS, preservation, resume, races) is covered by
the existing tool tests run on PostgreSQL through _srs_pg_suite.py and test_srs_e2c_cli_real.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
from test_srs_e3_fk_real import RealCase, _opt_in  # noqa: E402

DAY = timedelta(days=1)


class CommitFailed(RuntimeError):
    pass


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-2c tool checks NOT RUN (opt-in not set)")
class CleanupFunctionsOnPostgres(RealCase):
    def account_with_receipts_and_snapshots(self, sc):
        from app.srs import migration
        from app.srs.engine import CardKey

        sc.clock = cmp.T0 - 60 * DAY
        user = sc.user("tools")
        sc.set_mode(user, "legacy")
        card = sc.card(user, "t1")
        sc.clock = cmp.T0 - 50 * DAY
        assert sc.review(user, card, "good", legacy=True)["status"] == 200
        sc.clock = cmp.T0
        sc.set_mode(user, "fsrs")
        plan = migration.dry_run([CardKey("personal", user, card)])
        migration.apply_plan(plan, "e2c-run", approved=True)
        sc.clock = cmp.T0 + DAY
        assert sc.review(user, card, "good")["status"] == 200   # a receipt
        self.assertEqual(sc.count("srs_review_receipts"), 1)
        self.assertEqual(sc.count("srs_migration_snapshots"), 1)
        return user

    def calls(self, user, sc):
        from app.srs import migration, receipts
        from app.srs.engine import to_utc
        from app.srs.storage import begin_card_write

        def lock(apply):
            return begin_card_write if apply else None
        return {
            "receipts": lambda c, apply: receipts.minimize_receipts(
                c, user, to_utc(sc.clock), apply=apply, purge_expired=apply, lock=lock(apply)),
            "snapshots": lambda c, apply: migration.minimize_snapshots(c, user, apply=apply, lock=lock(apply)),
            "prune": lambda c, apply: migration.prune_expired_runs(c, user, apply=apply, lock=lock(apply)),
        }

    def test_each_function_runs_dry_and_applied_on_postgres(self):
        from app.database import get_connection

        self.create()
        with cmp.Scenario("postgresql", self.run) as sc:
            user = self.account_with_receipts_and_snapshots(sc)
            before = {t: sc.count(t) for t in ("srs_review_receipts", "srs_migration_snapshots", "srs_migration_runs")}
            reports = {}
            for name, call in self.calls(user, sc).items():
                for apply in (False, True):
                    with get_connection(read_only=not apply) as connection:
                        reports[(name, apply)] = call(connection, apply)
            # fresh receipts / format-2 records / an open window: nothing to change, all reported
            self.assertEqual(reports[("receipts", True)]["already_minimal"], 1)
            self.assertEqual((reports[("receipts", True)]["purged"], reports[("receipts", True)]["stripped"]), ([], []))
            self.assertEqual(reports[("snapshots", True)]["already_minimal"], 1)
            self.assertEqual(reports[("prune", True)]["runs"]["open"], 1)
            for (name, apply), report in reports.items():
                self.assertEqual(report["applied"], apply, name)
            self.assertEqual({t: sc.count(t) for t in before}, before)

    def test_a_failed_commit_is_raised_and_the_cursor_stays(self):
        import app.database as database
        from app.database import get_connection

        self.create()
        with cmp.Scenario("postgresql", self.run) as sc:
            user = self.account_with_receipts_and_snapshots(sc)
            calls = self.calls(user, sc)
            real_commit = database.AppPostgresConnection.commit

            def failing(self_):
                raise CommitFailed("injected commit failure")

            for name in ("receipts", "snapshots", "prune"):
                with self.subTest(name):
                    if name == "prune":  # a closed window, so the batch has work before its commit
                        sc.clock = cmp.T0 + 31 * DAY
                    with mock.patch.object(database.AppPostgresConnection, "commit", failing), \
                            self.assertRaises(CommitFailed):
                        with get_connection() as connection:
                            calls[name](connection, True)
                    self.assertIs(database.AppPostgresConnection.commit, real_commit)
            from app.srs import migration
            from app.srs.storage import begin_card_write

            progress = {}
            with mock.patch.object(database.AppPostgresConnection, "commit", failing), self.assertRaises(CommitFailed):
                with get_connection() as connection:
                    migration.prune_expired_runs(connection, user, apply=True, lock=begin_card_write, progress=progress)
            self.assertEqual(progress["cursor"], 0)            # never ahead of what was committed
            self.assertEqual(progress["runs"]["pruned"], [])   # the failed batch is not reported as done
            run = sc.sql("SELECT scope_json FROM srs_migration_runs WHERE run_key = 'e2c-run'")[0]
            self.assertNotIn('"format"', run["scope_json"])    # rolled back: the scope was not reduced

    def test_managed_schema_connection_refuses_transaction_ends(self):
        import _srs_e2_adapter as adapter

        self.create()
        catalog = self.catalog()
        for end in ("commit", "rollback", "close"):
            with self.subTest(end), self.assertRaises(adapter.StepBoundaryViolation):
                self.run.track_creation(adapter.schema_step(lambda c, end=end: getattr(c, end)()), expected=set())
            self.assertFalse(self.run.stopped)
        self.assertEqual(self.catalog(), catalog)


if __name__ == "__main__":
    unittest.main()
