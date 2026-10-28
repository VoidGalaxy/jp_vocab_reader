"""E-2c review regressions. Fake connections only; real connect is patched out."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _local_test_postgres as local_pg
import test_srs_e2c_cli as fixtures
import test_srs_pg_harness as harness_fixtures
import _srs_pg_suite as suite

CLEAN_ENV = fixtures.CLEAN_ENV
EXPECTED_OID = fixtures.EXPECTED_OID

NONCE_VAR = "SRS_E_TEST_POSTGRES_MARKER_NONCE"
OID_VAR = "SRS_E_TEST_POSTGRES_MARKER_OID"


class MarkerIdentityTests(unittest.TestCase):
    def connect(self, *, env=None, **answers):
        return fixtures.ConnectRefusals().connect(CLEAN_ENV if env is None else env,
                                                  {"target": fixtures.good_target(), **answers})

    def refused(self, result, code):
        error, made = result
        self.assertIsInstance(error, local_pg.LocalTestPostgresRefused)
        self.assertEqual(str(error), code)
        self.assertIsNone(error.__cause__)
        if error.__context__ is not None:
            self.assertTrue(error.__suppress_context__)
        self.assertTrue(all(raw.close_attempts == 1 for raw in made))
        return made

    def test_missing_or_invalid_expectation_refuses_before_connect(self):
        for name in (NONCE_VAR, OID_VAR):
            env = dict(CLEAN_ENV)
            del env[name]
            made = self.refused(self.connect(env=env), "run_marker_expectation_required")
            self.assertEqual(made, [])
        cases = ((NONCE_VAR, "not-a-nonce"), (NONCE_VAR, "a" * 31), (NONCE_VAR, "A" * 32),
                 (OID_VAR, "0"), (OID_VAR, "-1"), (OID_VAR, "1.0"), (OID_VAR, "true"),
                 (OID_VAR, "4294967296"), (OID_VAR, "1" * 5000))
        for name, value in cases:
            with self.subTest(name=name, length=len(value)):
                made = self.refused(self.connect(env={**CLEAN_ENV, name: value}), "run_marker_expectation_invalid")
                self.assertEqual(made, [])

    def test_same_oid_but_other_execution_nonce_is_refused(self):
        self.refused(self.connect(nonce="b" * 32), "run_marker_mismatch")

    def test_same_nonce_but_replaced_oid_is_refused(self):
        self.refused(self.connect(marker_oid=EXPECTED_OID + 1), "run_marker_mismatch")

    def test_non_table_or_foreign_owner_marker_is_refused(self):
        for changes in ({"marker_kind": "v"}, {"marker_kind": "m"}, {"marker_owned": False}):
            with self.subTest(changes=changes):
                self.refused(self.connect(**changes), "run_marker_mismatch")

    def test_replacement_between_catalog_and_nonce_read_is_refused(self):
        self.refused(self.connect(replace_on_read=True), "run_marker_mismatch")

    def test_zero_two_or_malformed_nonce_rows_are_refused(self):
        for count in (0, 2):
            self.refused(self.connect(marker_rows=count), "run_marker_missing")
        for nonce in (None, "", 123, "\uD55C" * 32):
            self.refused(self.connect(nonce=nonce), "run_marker_mismatch")

    def test_verification_and_rollback_failures_never_return_connection(self):
        for answers in ({"read_error": True}, {"rollback_error": True}):
            self.refused(self.connect(**answers), "connected_target_unverifiable")

    def test_close_failure_after_refusal_or_check_failure_is_fixed_code(self):
        for answers in ({"target": fixtures.good_target(db="jp_vocab_test_other")},
                        {"nonce": "b" * 32}, {"read_error": True}, {"rollback_error": True}):
            with self.subTest(answers=answers):
                made = self.refused(self.connect(close_error=True, **answers), "local_postgres_close_failed")
                self.assertFalse(made[0].closed)  # failed close is NOT reported as successful

    def test_good_identity_is_checked_before_clean_handoff(self):
        connection, made = self.connect()
        self.assertNotIsInstance(connection, local_pg.LocalTestPostgresRefused)
        raw = made[0]
        self.assertGreaterEqual(raw.catalog_reads, 2)
        self.assertTrue(raw.rolled_back)
        self.assertFalse(raw.closed)
        self.assertTrue(any("SELECT nonce" in query for query in raw.queries))
        self.assertFalse(any(query.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "DROP"))
                             for query in raw.queries))

    def test_all_cli_refusals_mask_close_failure_and_never_call_tools(self):
        import psycopg

        targets = ((fixtures.d2_receipt_minimize, "app.srs.receipts.minimize_receipts"),
                   (fixtures.d2_snapshot_minimize, "app.srs.migration.minimize_snapshots"),
                   (fixtures.d2_snapshot_prune, "app.srs.migration.prune_expired_runs"))
        for module, target in targets:
            raw = fixtures.FakeRaw({"target": fixtures.good_target(), "nonce": "b" * 32, "close_error": True})
            stdout, stderr = io.StringIO(), io.StringIO()
            with mock.patch.dict(os.environ, CLEAN_ENV), mock.patch.object(psycopg, "connect", return_value=raw), \
                    mock.patch(target) as operation, redirect_stderr(stderr), redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as error:
                    module.main(["--local-test-postgres", "--user-id", "1", "--apply", "--confirm-user-id", "1"])
            self.assertEqual(error.exception.code, 2)
            operation.assert_not_called()
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("local_postgres_close_failed", stderr.getvalue())
            self.assertNotIn("synthetic raw", stderr.getvalue())
            self.assertNotIn(fixtures.EXPECTED_NONCE, stderr.getvalue())


class ParentProofTests(harness_fixtures.Base):
    def test_only_a_started_run_exports_its_own_identity_without_database_access(self):
        run = self.run_()
        with self.assertRaises(harness_fixtures.harness.HarnessStopped):
            run.cli_marker_environment()
        run.start()
        calls = self.server.calls
        expected = run.cli_marker_environment()
        self.assertEqual(expected, {NONCE_VAR: run._nonce, OID_VAR: str(run._marker_oid)})
        self.assertEqual(self.server.calls, calls)
        run.teardown()
        with self.assertRaises(harness_fixtures.harness.HarnessStopped):
            run.cli_marker_environment()

    def test_stopped_run_cannot_export_a_permission(self):
        run = self.started()
        run.stopped = True
        calls = self.server.calls
        with self.assertRaises(harness_fixtures.harness.HarnessStopped):
            run.cli_marker_environment()
        self.assertEqual(self.server.calls, calls)


class ProofTransportTests(unittest.TestCase):
    def test_child_proof_is_scrubbed_except_for_the_authorized_cleanup_cli(self):
        captured = []
        trusted = {NONCE_VAR: fixtures.EXPECTED_NONCE, OID_VAR: str(EXPECTED_OID)}
        parent = types.SimpleNamespace(cli_marker_environment=lambda: trusted)
        fake_path = Path(__file__).resolve().parents[1] / "jp_vocab_proof_transport" / "missing.db"
        cleanup = ["python", "d2_snapshot_minimize.py", "--sqlite-db", str(fake_path)]
        ambient = {**CLEAN_ENV, NONCE_VAR: "stale", OID_VAR: "999", "DATABASE_URL": fixtures.URL}

        def capture(instance, *args, **kwargs):
            captured.append((args[0], kwargs["env"]))

        with mock.patch.object(suite, "CURRENT_RUN", parent), mock.patch.dict(suite.CLI_CALLS), \
                mock.patch.object(subprocess.Popen, "__init__", capture):
            with suite._scrub_child_env(fixtures.URL):
                subprocess.Popen.__init__(object(), ["python", "other.py"], env=ambient)
                subprocess.Popen.__init__(object(), cleanup, env=ambient)
        for name in (NONCE_VAR, OID_VAR, "SRS_E_TEST_POSTGRES_URL", "SRS_E_TEST_POSTGRES_OPT_IN", "DATABASE_URL"):
            self.assertNotIn(name, captured[0][1])
        self.assertIn("--local-test-postgres", captured[1][0])
        self.assertEqual({k: captured[1][1][k] for k in trusted}, trusted)

    def test_in_process_proof_is_from_parent_and_environment_is_restored_on_failure(self):
        trusted = {NONCE_VAR: fixtures.EXPECTED_NONCE, OID_VAR: str(EXPECTED_OID)}
        parent = types.SimpleNamespace(cli_marker_environment=lambda: trusted)
        seen = []
        fake_path = Path(__file__).resolve().parents[1] / "jp_vocab_proof_transport" / "missing.db"

        def fail(argv):
            seen.append({k: os.environ[k] for k in trusted})
            raise RuntimeError("synthetic test failure")

        with mock.patch.object(suite, "CURRENT_RUN", parent), mock.patch.dict(suite.CLI_CALLS), \
                mock.patch.dict(os.environ, {NONCE_VAR: "stale", OID_VAR: "999"}), \
                mock.patch.object(fixtures.d2_snapshot_minimize, "main", fail):
            before = dict(os.environ)
            with suite.cleanup_cli_shim():
                with self.assertRaisesRegex(RuntimeError, "synthetic test failure"):
                    fixtures.d2_snapshot_minimize.main(["--sqlite-db", str(fake_path)])
            self.assertEqual(dict(os.environ), before)
        self.assertEqual(seen, [trusted])


if __name__ == "__main__":
    unittest.main()
