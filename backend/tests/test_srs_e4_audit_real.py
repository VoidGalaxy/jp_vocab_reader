"""E-4 on the opt-in protected local PostgreSQL DB. No opt-in means NOT RUN."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp
from test_srs_e3_delete import DeleteScenario, TODAY, EARLIER
from test_srs_e3_fk_real import RealCase, _opt_in, WAIT
from app.database import get_connection
from app.srs import invariant_audit as audit

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "srs_invariant_audit.py"


@unittest.skipUnless(_opt_in(), "Real PG E-4 audit NOT RUN (opt-in not set)")
class PgAuditTests(RealCase):
    def setUp(self):
        super().setUp()
        self.create()
        self.sc = cmp.Scenario("postgresql", self.run)
        self.sc.__enter__()
        self.addCleanup(self.sc.__exit__, None, None, None)
        self.fixture = DeleteScenario(self.sc)
        self.fixture.build()

    def check(self):
        with get_connection() as c, audit.read_snapshot(c):
            return audit.audit(c)

    def test_static_checks_cli_and_read_only_enforcement_leave_rows_and_sequence_unchanged(self):
        before = self.checksums()
        seq_before = self.sql("SELECT last_value, is_called FROM vocab_items_id_seq")
        report = self.check()
        self.assertEqual(report["status"], "partial", report)
        self.assertEqual([report["checks"][f"I{i}"]["status"] for i in range(1, 6)], ["pass"] * 5)
        result = subprocess.run([sys.executable, str(SCRIPT), "--local-test-postgres"],
                                env=dict(os.environ), capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads(result.stdout), report)
        self.assertEqual(result.stderr, "")
        with get_connection() as c:
            with self.assertRaises(audit.AuditInputError):
                audit.audit(c)
            c._connection.rollback()
            with audit.read_snapshot(c):
                with self.assertRaises(Exception) as rejected:
                    c.execute("DELETE FROM review_logs")
                self.assertEqual(getattr(rejected.exception, "sqlstate", None), "25006")
        self.assertEqual(self.checksums(), before)
        self.assertEqual(self.sql("SELECT last_value, is_called FROM vocab_items_id_seq"), seq_before)

    def test_word_and_deck_deletions_preserve_baseline_across_real_app_paths(self):
        sc, fixture = self.sc, self.fixture
        with get_connection() as c:
            with audit.read_snapshot(c):
                baseline = audit.capture_deletion_baseline(c, at=TODAY, days=(TODAY.date(), EARLIER.date()))
            for label in ("n1", "h1", "m1"):
                response = sc.client.delete(f"/vocab-items/{fixture.ids[label]}", headers=sc.headers(fixture.A))
                self.assertEqual(response.status_code, 204)
                with audit.read_snapshot(c):
                    report = audit.audit(c, baseline=baseline)
                    self.assertEqual(report["status"], "pass", report)
            response = sc.client.delete(f"/decks/{fixture.decks['bulk']}", headers=sc.headers(fixture.A))
            self.assertEqual(response.status_code, 200)
            with audit.read_snapshot(c):
                self.assertEqual(audit.audit(c, baseline=baseline)["status"], "pass")

    def test_corrupt_reference_scope_and_sequence_are_not_silently_accepted(self):
        self.sql("UPDATE srs_review_receipts SET review_log_id = 999999 WHERE card_kind = 'personal'")
        self.sql("UPDATE srs_migration_runs SET scope_json = 'garbage'")
        report = self.check()
        self.assertEqual(report["checks"]["I5"]["status"], "fail")
        self.assertEqual(report["checks"]["I3"]["status"], "unknown")
        self.sql("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) "
                 "VALUES ('personal', ?, 999999, ?)", (self.fixture.A, TODAY.isoformat()))
        self.assertEqual(self.check()["checks"]["I3"]["status"], "fail")

    def test_repeatable_read_stays_consistent_while_review_commits(self):
        started, finished = threading.Event(), threading.Event()
        results = []

        def worker():
            started.set()
            try:
                self.sc.review(self.fixture.A, self.fixture.ids["n1"], "good")
                results.append("ok")
            except BaseException as error:
                results.append(error)
            finally:
                finished.set()

        with get_connection() as c:
            with audit.read_snapshot(c):
                before = audit.capture_deletion_baseline(c, at=TODAY, days=(TODAY.date(),))
                thread = threading.Thread(target=worker)
                thread.start()
                try:
                    self.assertTrue(started.wait(WAIT))
                    self.assertTrue(finished.wait(WAIT))
                finally:
                    thread.join(WAIT)
                self.assertFalse(thread.is_alive())
                self.assertEqual(results, ["ok"])
                # The writer completed, but this existing read snapshot still sees the old logs.
                self.assertEqual(audit.audit(c, baseline=before)["checks"]["I7"]["status"], "pass")
            with audit.read_snapshot(c):
                report = audit.audit(c, baseline=before)
                self.assertEqual(report["checks"]["I6"]["status"], "pass")
                self.assertEqual(report["checks"]["I7"]["status"], "not_evaluated")


if __name__ == "__main__":
    unittest.main()
