"""Gate E-2c: the cleanup CLIs' local-test-PostgreSQL target (scripts/_local_test_postgres.py)
and target selection -- no database here. A fake psycopg answers the connected-target
queries, so every refusal path is exercised; no refusal may carry the URL, the role, SQL or a
raw driver message. The real runs are in test_srs_e2c_cli_real (opt-in) and in the existing
tool tests run on PostgreSQL through _srs_pg_suite.py.
"""

from __future__ import annotations

import io
import os
import sys
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND))

import _local_test_postgres as local_pg  # noqa: E402
import d2_receipt_minimize  # noqa: E402
import d2_snapshot_minimize  # noqa: E402
import d2_snapshot_prune  # noqa: E402

URL = "postgresql://jp_vocab_e2@localhost:55432/jp_vocab_test_e"
EXPECTED_NONCE = "a" * 32
EXPECTED_OID = 1234
CLEAN_ENV = {"SRS_E_TEST_POSTGRES_URL": URL, "SRS_E_TEST_POSTGRES_OPT_IN": "1",
             "SRS_E_TEST_POSTGRES_MARKER_NONCE": EXPECTED_NONCE, "SRS_E_TEST_POSTGRES_MARKER_OID": str(EXPECTED_OID)}
TARGET_VARS = ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR")


class FakeRaw:
    def __init__(self, answers):
        self.answers, self.closed, self.rolled_back = answers, False, False
        self.catalog_reads = self.close_attempts = 0
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(sql)
        if "current_database()" in sql:
            row = self.answers["target"]
        elif "pg_class" in sql:
            self.catalog_reads += 1
            oid = self.answers.get("marker_oid", EXPECTED_OID)
            if self.answers.get("replace_on_read") and self.catalog_reads > 1:
                oid += 1
            row = {"oid": oid, "kind": self.answers.get("marker_kind", "r"),
                   "owned": self.answers.get("marker_owned", True)}
        elif "SELECT nonce" in sql:
            if self.answers.get("read_error"):
                raise RuntimeError("synthetic raw driver detail")
            rows = [{"nonce": self.answers.get("nonce", EXPECTED_NONCE)}] * self.answers.get("marker_rows", 1)
            return types.SimpleNamespace(fetchall=lambda: rows)
        elif "count(*)" in sql:
            row = {"n": self.answers.get("marker_rows", 1)}
        else:
            row = {"present": params[0].split(".", 1)[1] not in self.answers.get("missing", ())}
        return types.SimpleNamespace(fetchone=lambda: row)

    def rollback(self):
        if self.answers.get("rollback_error"):
            raise RuntimeError("synthetic raw rollback detail")
        self.rolled_back = True

    def close(self):
        self.close_attempts += 1
        if self.answers.get("close_error"):
            raise RuntimeError("synthetic raw close detail")
        self.closed = True


def good_target(**change):
    target = {"db": "jp_vocab_test_e", "address": "::1", "port": 55432, "privileged": False, "marked": True}
    target.update(change)
    return target


class ConnectRefusals(unittest.TestCase):
    def connect(self, env, answers=None, connect_error=None):
        made = []

        def fake_connect(url, **kwargs):
            if connect_error is not None:
                raise connect_error
            raw = FakeRaw(answers or {"target": good_target()})
            raw.kwargs = kwargs
            made.append(raw)
            return raw

        environ = {k: v for k, v in os.environ.items() if k not in TARGET_VARS and not k.startswith("SRS_E_TEST")}
        environ.update(env)
        with mock.patch.dict(os.environ, environ, clear=True), mock.patch("psycopg.connect", fake_connect):
            try:
                return local_pg.connect(read_only=True), made
            except local_pg.LocalTestPostgresRefused as refused:
                return refused, made

    def assert_refused(self, result, code):
        refused, made = result
        self.assertIsInstance(refused, local_pg.LocalTestPostgresRefused)
        self.assertEqual(refused.code, code)
        self.assertEqual(str(refused), code)            # nothing else is carried
        self.assertTrue(all(raw.closed for raw in made))  # a checked-and-refused connection is closed

    def test_opt_in_and_url_rules(self):
        self.assert_refused(self.connect({"SRS_E_TEST_POSTGRES_URL": URL}), "local_postgres_opt_in_required")
        self.assert_refused(self.connect({"SRS_E_TEST_POSTGRES_URL": URL, "SRS_E_TEST_POSTGRES_OPT_IN": "yes"}),
                            "local_postgres_opt_in_required")
        for url in ("postgresql://jp_vocab_e2@db.example.com:5432/jp_vocab_test_e",   # remote
                    "postgresql://jp_vocab_e2@localhost:55432/jp_vocab",              # not a test name
                    "", "sqlite:///x.db"):
            with self.subTest(url=url):
                self.assert_refused(self.connect({"SRS_E_TEST_POSTGRES_URL": url, "SRS_E_TEST_POSTGRES_OPT_IN": "1"}),
                                    "local_postgres_url_refused")
        self.assert_refused(self.connect({**CLEAN_ENV, "PGHOST": "elsewhere"}), "local_postgres_url_refused")
        self.assert_refused(self.connect({**CLEAN_ENV, "SRS_E_TEST_POSTGRES_URL":
                                          "postgresql://jp_vocab_e2@localhost/jp_vocab_test_e"}),
                            "explicit_test_port_and_database_required")

    def test_driver_failure_is_a_fixed_code(self):
        result = self.connect(CLEAN_ENV, connect_error=RuntimeError(f"could not connect to {URL} password=secret"))
        self.assert_refused(result, "local_postgres_connect_failed")

    def test_the_connected_target_must_be_the_checked_one(self):
        for name, target, code in (
                ("database", good_target(db="jp_vocab_test_other"), "connected_target_mismatch"),
                ("port", good_target(port=5432), "connected_target_mismatch"),
                ("address", good_target(address="10.0.0.5"), "connected_target_mismatch"),
                ("no address", good_target(address=None), "connected_target_mismatch"),
                ("privileged role", good_target(privileged=True), "connected_target_mismatch"),
                ("unknown role rights", good_target(privileged=None), "connected_target_mismatch"),
                ("no run marker", good_target(marked=False), "run_marker_missing")):
            with self.subTest(name):
                self.assert_refused(self.connect(CLEAN_ENV, {"target": target}), code)
        self.assert_refused(self.connect(CLEAN_ENV, {"target": good_target(), "marker_rows": 2}), "run_marker_missing")
        self.assert_refused(self.connect(CLEAN_ENV, {"target": good_target(), "missing": ("srs_review_receipts",)}),
                            "srs_tables_missing")

    def test_a_checked_target_is_handed_over_read_only_for_a_dry_run(self):
        connection, made = self.connect(CLEAN_ENV)
        from app.database import AppPostgresConnection

        self.assertIsInstance(connection, AppPostgresConnection)
        self.assertTrue(made[0].rolled_back)                              # no check transaction left open
        self.assertIn("default_transaction_read_only=on", made[0].kwargs["options"])
        self.assertFalse(made[0].closed)


class TargetSelection(unittest.TestCase):
    def run_main(self, module, argv):
        err = io.StringIO()
        with redirect_stderr(err), mock.patch.dict(os.environ, {}), self.assertRaises(SystemExit) as stop:
            module.main(argv)
        return stop.exception.code, err.getvalue()

    def test_exactly_one_target_and_explicit_confirmation(self):
        for module in (d2_receipt_minimize, d2_snapshot_minimize, d2_snapshot_prune):
            with self.subTest(module.__name__):
                code, err = self.run_main(module, ["--user-id", "1"])
                self.assertEqual(code, 2)                                                # neither target
                code, err = self.run_main(module, ["--sqlite-db", "x.db", "--local-test-postgres", "--user-id", "1"])
                self.assertEqual(code, 2)
                self.assertIn("not allowed with argument", err)                         # both targets
                code, err = self.run_main(module, ["--local-test-postgres", "--user-id", "1", "--apply"])
                self.assertEqual(code, 2)
                self.assertIn("--confirm-user-id", err)                                 # no confirmation
                code, err = self.run_main(module, ["--local-test-postgres", "--user-id", "1", "--apply",
                                                   "--confirm-user-id", "2"])
                self.assertEqual(code, 2)                                                # wrong confirmation

    def test_refusal_message_holds_only_the_code(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SRS_E_TEST")}
        env["SRS_E_TEST_POSTGRES_URL"] = "postgresql://jp_vocab_e2@db.example.com:5432/jp_vocab_test_e"
        env["SRS_E_TEST_POSTGRES_OPT_IN"] = "1"
        for module in (d2_receipt_minimize, d2_snapshot_minimize, d2_snapshot_prune):
            with self.subTest(module.__name__), mock.patch.dict(os.environ, env, clear=True):
                code, err = self.run_main(module, ["--local-test-postgres", "--user-id", "1"])
                self.assertEqual(code, 2)
                self.assertIn("local test PostgreSQL refused: local_postgres_url_refused", err)
                self.assertNotIn("example.com", err)
                self.assertNotIn("jp_vocab_e2", err)


class ReceiptFailureOnPostgres(unittest.TestCase):
    """The receipt CLI fails with an exception on both targets (existing contract). On the
    PostgreSQL target the batch is rolled back first, and a driver error -- whose message may
    quote stored values -- is re-raised as its type name only."""

    def run_with(self, error):
        class Conn:
            def __init__(self):
                self.rolled_back = False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def rollback(self):
                self.rolled_back = True

        conn = Conn()
        with mock.patch.dict(os.environ, {}), mock.patch.object(local_pg, "connect", return_value=conn),                 mock.patch("app.srs.receipts.minimize_receipts", side_effect=error),                 mock.patch.object(d2_receipt_minimize, "print"):
            with self.assertRaises(Exception) as raised:
                d2_receipt_minimize.main(["--local-test-postgres", "--user-id", "1", "--apply", "--confirm-user-id", "1"])
        return raised.exception, conn

    def test_driver_error_is_masked_after_rollback(self):
        import psycopg

        error, conn = self.run_with(psycopg.errors.CheckViolation("DETAIL: Failing row contains (secret-value)"))
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "database error: CheckViolation")
        self.assertIsNone(error.__cause__)
        self.assertTrue(error.__suppress_context__)
        self.assertTrue(conn.rolled_back)

    def test_other_errors_propagate_unchanged_after_rollback(self):
        failure = RuntimeError("synthetic failure")
        error, conn = self.run_with(failure)
        self.assertIs(error, failure)
        self.assertTrue(conn.rolled_back)


if __name__ == "__main__":
    unittest.main()
