"""E-4 counts-only audit: synthetic files only; no default DB / network access."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp
from app.database import get_connection
from app.srs import invariant_audit as audit, migration

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import srs_invariant_audit as cli

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "srs_invariant_audit.py"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e4_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "audit.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.path.as_posix()}"})
        env.start()
        self.addCleanup(env.stop)
        self.sc = cmp.Scenario("sqlite")
        self.sc.__enter__()
        self.addCleanup(self.sc.__exit__, None, None, None)
        self.sc.stage_upgrade()
        self.user = self.sc.user("e4-a")
        self.other = self.sc.user("e4-b")
        self.sc.set_mode(self.user, "fsrs")
        self.card = self.sc.card(self.user, "content-must-not-be-exported")
        self.sc.review(self.user, self.card, "again")
        self.log = self.sc.sql("SELECT id FROM review_logs WHERE user_id = ?", (self.user,))[0]["id"]

    def sql(self, query, params=()):
        return self.sc.sql(query, params)

    def check(self):
        with get_connection(read_only=True) as c, audit.read_snapshot(c):
            return audit.audit(c)

    def snap(self, payload=None, kind="personal", ref=None):
        key = "last_log_id"
        body = payload or {"format": 2, "card": {"id": self.card}, key: self.log}
        run = self.sql("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                       "config_version, started_at) VALUES ('e4', 'apply', 'completed', ?, 'fsrs', '6.3.2', 'c', ?) RETURNING id",
                       (json.dumps({"format": migration.PRUNED_SCOPE_FORMAT, "user_id": self.user, "config_version": "c",
                                    "cards": [{"kind": kind, "ref_id": ref or self.card}], "request_sha256": "a" * 64}),
                        cmp.T0.isoformat()))[0]["id"]
        return self.sql("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, "
                        "card_version_before, legacy_json, created_at) VALUES (?, ?, ?, ?, 0, ?, ?) RETURNING id",
                        (run, self.user, kind, ref or self.card, json.dumps(body), cmp.T0.isoformat()))[0]["id"]

    def test_normal_static_checks_are_partial_not_full_pass(self):
        result = self.check()
        self.assertEqual(result["status"], "partial")
        self.assertEqual([result["checks"][f"I{i}"]["status"] for i in range(1, 6)], ["pass"] * 5)
        self.assertEqual([result["checks"][f"I{i}"]["status"] for i in (6, 7)], ["not_evaluated"] * 2)
        self.assertNotIn("content-must-not-be-exported", json.dumps(result))

    def test_i1_missing_ledger_and_i2_wrong_owner_are_distinct(self):
        self.sql("UPDATE review_logs SET user_id = ? WHERE id = ?", (self.other, self.log))
        self.assertEqual(self.check()["checks"]["I2"]["violations"], 1)
        self.sql("DELETE FROM vocab_items WHERE id = ?", (self.card,))
        self.assertEqual(self.check()["checks"]["I1"]["violations"], 1)
        self.sql("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) VALUES ('personal', ?, ?, ?)",
                 (self.other, self.card, cmp.T0.isoformat()))
        self.assertEqual(self.check()["checks"]["I1"]["status"], "pass")

    def test_i1_does_not_accept_other_account_ledger(self):
        self.sql("DELETE FROM vocab_items WHERE id = ?", (self.card,))
        self.sql("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) VALUES ('personal', ?, ?, ?)",
                 (self.other, self.card, cmp.T0.isoformat()))
        self.assertEqual(self.check()["checks"]["I1"]["violations"], 1)

    def test_i3_sequence_checks_deleted_references_and_never_advances(self):
        self.sql("INSERT INTO meaning_feedback (user_id, vocabulary_id, surface, base_form, reading, "
                 "current_meaning_ko, created_at) VALUES (?, 9999, 'x', 'x', '', '', ?)", (self.user, cmp.T0.isoformat()))
        before = self.path.read_bytes()
        self.assertEqual(self.check()["checks"]["I3"]["status"], "fail")
        self.assertEqual(self.path.read_bytes(), before)

    def test_i3_malformed_scope_is_unknown_not_ignored(self):
        self.snap()
        for raw in ('garbage', '[]', '{"user_id": true}', '[' * 1100 + ']' * 1100):
            with self.subTest(raw_length=len(raw)):
                self.sql("UPDATE srs_migration_runs SET scope_json = ?", (raw,))
                self.assertEqual(self.check()["checks"]["I3"]["status"], "unknown")

    def test_i3_valid_run_summary_references_are_counted(self):
        self.snap()
        self.sql("UPDATE srs_migration_runs SET summary_json = ?", (json.dumps({"cursor": 1, "results": [
            {"kind": "personal", "ref_id": 9000, "result": "missing_or_access_lost"}]}),))
        self.assertEqual(self.check()["checks"]["I3"]["status"], "fail")

    def test_i4_unmarked_finding_then_marked_finding(self):
        self.sql("UPDATE vocab_items SET created_at = ? WHERE id = ?", ((cmp.T0 + timedelta(days=1)).isoformat(), self.card))
        self.assertEqual(self.check()["checks"]["I4"]["violations"], 1)
        self.sql("INSERT INTO srs_card_identity_flags (user_id, card_kind, card_ref, reasons, detected_at) "
                 "VALUES (?, 'personal', ?, '[]', ?)", (self.user, self.card, cmp.T0.isoformat()))
        self.assertEqual(self.check()["checks"]["I4"]["status"], "pass")

    def test_i4_unreadable_creation_is_unknown(self):
        self.sql("UPDATE vocab_items SET created_at = 'garbage' WHERE id = ?", (self.card,))
        self.assertEqual(self.check()["checks"]["I4"]["status"], "unknown")

    def test_i5_receipt_requires_account_card_and_log_kind_match(self):
        self.sql("UPDATE srs_review_receipts SET user_id = ?", (self.other,))
        self.assertEqual(self.check()["checks"]["I5"]["violations"], 1)
        self.sql("UPDATE srs_review_receipts SET user_id = ?, card_kind = 'lexeme'", (self.user,))
        self.assertEqual(self.check()["checks"]["I5"]["violations"], 1)

    def test_i5_snapshot_baseline_restart_and_card_boundary(self):
        self.snap({"card": {"id": self.card, "evidence_from_log_id": 999},
                   "baseline": {"last_log_id": 998}, "restart": {"previous_boundary": 997}})
        self.sql("UPDATE vocab_items SET evidence_from_log_id = 996 WHERE id = ?", (self.card,))
        self.assertEqual(self.check()["checks"]["I5"]["violations"], 4)

    def test_i5_snapshot_malformed_or_missing_pointer_is_unknown(self):
        self.snap()
        for raw in ('[]', 'garbage', '{"card": {}}', '{"card": {}, "last_log_id": true}'):
            self.sql("UPDATE srs_migration_snapshots SET legacy_json = ?", (raw,))
            self.assertEqual(self.check()["checks"]["I5"]["status"], "unknown")

    def test_unsupported_snapshot_does_not_get_a_clean_reference_report(self):
        self.snap({"format": 999, "card": {"id": self.card}, "last_log_id": self.log})
        checks = self.check()["checks"]
        self.assertEqual(checks["I3"]["status"], "unknown")
        self.assertEqual(checks["I5"]["status"], "unknown")

    def test_log_mutation_is_not_fixed_history_even_when_row_counts_match(self):
        result = self.compare_delete(lambda: self.sql("UPDATE review_logs SET rating = 'easy' WHERE id = ?", (self.log,)))
        self.assertEqual(result["checks"]["I6"]["violations"], 1)
        self.assertEqual(result["checks"]["I7"]["status"], "not_evaluated")

    def test_i5_restart_record_references_are_checked(self):
        snap = self.snap()
        self.sql("INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, previous_boundary, "
                 "new_boundary, card_version_before, created_at) VALUES (?, 'personal', ?, ?, ?, 999, 1, ?)",
                 (self.user, self.card, snap, self.log, cmp.T0.isoformat()))
        self.assertEqual(self.check()["checks"]["I5"]["violations"], 1)
        self.sql("UPDATE srs_evidence_restarts SET source_snapshot_id = 999, new_boundary = ?", (self.log,))
        self.assertEqual(self.check()["checks"]["I5"]["violations"], 1)

    def compare_delete(self, action):
        with get_connection() as c:
            with audit.read_snapshot(c):
                baseline = audit.capture_deletion_baseline(c, at=cmp.T0, days=(cmp.T0.date(),))
            action()
            with audit.read_snapshot(c):
                return audit.audit(c, baseline=baseline)

    def test_real_word_deletion_preserves_i6_i7(self):
        def delete():
            response = self.sc.client.delete(f"/vocab-items/{self.card}", headers=self.sc.headers(self.user))
            self.assertEqual(response.status_code, 204)
        result = self.compare_delete(delete)
        self.assertEqual(result["status"], "pass", result)

    def test_real_deck_deletion_preserves_i6_i7(self):
        response = self.sc.client.post("/decks", headers=self.sc.headers(self.user), json={"name": "e4-bulk"})
        self.assertEqual(response.status_code, 200)
        deck = response.json()["id"]
        self.sql("UPDATE vocab_items SET deck_id = ? WHERE id = ?", (deck, self.card))
        def delete():
            response = self.sc.client.delete(f"/decks/{deck}", headers=self.sc.headers(self.user))
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.compare_delete(delete)["status"], "pass")

    def test_unknown_and_past_learning_marks_survive_deletion(self):
        for status, bound in (("unknown", None), ("before_tracking", (cmp.T0 - timedelta(days=3)).date().isoformat())):
            with self.subTest(status=status):
                card = self.sc.card(self.user, status)
                self.sql("UPDATE vocab_items SET history_intro_status = ?, history_intro_known_by = ? WHERE id = ?",
                         (status, bound, card))
                def delete():
                    response = self.sc.client.delete(f"/vocab-items/{card}", headers=self.sc.headers(self.user))
                    self.assertEqual(response.status_code, 204)
                self.assertEqual(self.compare_delete(delete)["status"], "pass")

    def test_corrupt_calendar_time_does_not_claim_i7_pass(self):
        self.sql("UPDATE review_logs SET reviewed_at = 'garbage' WHERE id = ?", (self.log,))
        result = self.compare_delete(lambda: None)
        self.assertEqual(result["checks"]["I6"]["status"], "pass")
        self.assertEqual(result["checks"]["I7"]["status"], "unknown")

    def test_log_loss_is_i6_failure_and_i7_cannot_claim_fixed_history(self):
        result = self.compare_delete(lambda: self.sql("DELETE FROM review_logs WHERE id = ?", (self.log,)))
        self.assertEqual(result["checks"]["I6"]["violations"], 1)
        self.assertEqual(result["checks"]["I7"]["status"], "not_evaluated")

    def test_new_evaluation_is_not_a_deletion_only_rehearsal(self):
        result = self.compare_delete(lambda: self.sc.review(self.user, self.card))
        self.assertEqual(result["checks"]["I6"]["status"], "pass")
        self.assertEqual(result["checks"]["I7"]["status"], "not_evaluated")

    def test_i7_detects_lost_unknown_evidence_even_with_unchanged_logs(self):
        self.sql("UPDATE vocab_items SET history_intro_status = 'unknown' WHERE id = ?", (self.card,))
        result = self.compare_delete(lambda: self.sql("UPDATE vocab_items SET history_intro_status = NULL WHERE id = ?", (self.card,)))
        self.assertEqual(result["checks"]["I6"]["status"], "pass")
        self.assertEqual(result["checks"]["I7"]["violations"], 1)

    def test_baseline_cannot_be_reused_for_another_connection(self):
        with get_connection(read_only=True) as c, audit.read_snapshot(c):
            baseline = audit.capture_deletion_baseline(c, at=cmp.T0, days=(cmp.T0.date(),))
        with get_connection(read_only=True) as c, audit.read_snapshot(c):
            with self.assertRaisesRegex(audit.AuditInputError, "same_connection"):
                audit.audit(c, baseline=baseline)

    def test_audit_requires_read_only_transaction_and_rolls_back(self):
        with get_connection() as c:
            with self.assertRaises(audit.AuditInputError):
                audit.audit(c)
            with audit.read_snapshot(c):
                with self.assertRaises(sqlite3.OperationalError):
                    c.execute("DELETE FROM review_logs")
                with self.assertRaises(audit.AuditInputError):
                    with audit.read_snapshot(c):
                        pass
            self.assertFalse(c.in_transaction)
            self.assertEqual(c.execute("PRAGMA query_only").fetchone()[0], 0)

    def test_cli_read_only_counts_only_and_no_ambient_database_fallback(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        env = dict(os.environ, DATABASE_URL="postgresql://invalid.invalid/never-connect")
        result = subprocess.run([sys.executable, str(SCRIPT), "--sqlite-db", str(self.path)],
                                env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 3, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "partial")
        for secret in (str(self.path), "content-must-not-be-exported", "invalid.invalid", "password", "response_json"):
            self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.path) + "-wal").exists())
        # A fresh process must not open the repository's .env during app imports.
        guarded = ("import sys,runpy; p=sys.argv[1]; sys.argv=sys.argv[1:]; "
                   "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError('env_file_read')) "
                   "if e=='open' and str(a[0]).endswith('.env') else None); runpy.run_path(p,run_name='__main__')")
        checked = subprocess.run([sys.executable, "-c", guarded, str(SCRIPT), "--sqlite-db", str(self.path)],
                                 env=dict(env, PYTHON_DOTENV_DISABLED="0"), capture_output=True, text=True, timeout=20)
        self.assertEqual(checked.returncode, 3, checked.stderr)
        self.assertEqual(json.loads(checked.stdout), report)

    def test_cli_missing_file_does_not_create_and_refuses_unapproved_pg(self):
        missing = self.path.parent / "missing.db"
        commands = (["--sqlite-db", str(missing)], ["--local-test-postgres"])
        for args in commands:
            env = dict(os.environ)
            env.pop("SRS_E_TEST_POSTGRES_OPT_IN", None)
            result = subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "error")
            self.assertEqual(result.stderr, "")
        self.assertFalse(missing.exists())

    def test_cli_error_does_not_expose_malformed_source_or_driver_message(self):
        self.sql("DROP TABLE srs_evidence_restarts")
        result = subprocess.run([sys.executable, str(SCRIPT), "--sqlite-db", str(self.path)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("srs_evidence_restarts", result.stdout)

    def test_cli_rejects_unsafe_postgres_before_connect(self):
        import psycopg
        from _local_postgres_guard import TARGET_ENV_VARS

        cases = (
            ("postgresql://remote.invalid/jp_vocab_test_e", {}),
            ("postgresql://localhost:55432/not_a_test", {}),
            ("postgresql://localhost:55432/jp_vocab_test_e?host=remote.invalid", {}),
            ("postgresql://localhost/jp_vocab_test_e", {}),
            ("postgresql://localhost:55432/jp_vocab_test_e", {"PGHOSTADDR": "127.0.0.1"}),
        )
        for url, extra in cases:
            env = dict(os.environ)
            for key in TARGET_ENV_VARS:
                env.pop(key, None)
            env.update(SRS_E_TEST_POSTGRES_OPT_IN="1", SRS_E_TEST_POSTGRES_URL=url, **extra)
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(psycopg, "connect") as connect, \
                    mock.patch("builtins.print") as printed:
                with self.assertRaises(SystemExit) as error:
                    cli.main(["--local-test-postgres"])
                self.assertEqual(error.exception.code, 2)
                connect.assert_not_called()
                self.assertNotIn("remote.invalid", printed.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
