"""Regression tests for the opt-in PostgreSQL guard
(tests/_local_postgres_guard.py) used by test_learning_plan_progress.py.

Pure parsing, fakes and mocks: no test reaches any server. psycopg.connect is
patched in every test; it may only be called by the read-only emptiness check
(through a fake connection), never by URL validation, and init_db() or the
app's own get_connection() must never run on a refused target.

Run directly:      python tests/test_local_postgres_guard.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import runpy
import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

import psycopg  # noqa: E402

import app.database  # noqa: E402  (no connection on import)
from _local_postgres_guard import (  # noqa: E402
    INSPECT_COLUMNS,
    TARGET_ENV_VARS,
    UnsafePostgresTarget,
    assert_empty_postgres_test_database,
    validate_local_postgres_test_url,
)

SECRET = "s3cr3t-pw"
CLEAN_ENV: dict[str, str] = {}
GOOD_URL = f"postgresql://plan:{SECRET}@localhost:5432/jp_vocab_test_plan"

ACCEPTED = [
    GOOD_URL,
    f"postgres://plan:{SECRET}@127.0.0.1/jp_vocab_test",
    f"postgresql://plan:{SECRET}@[::1]:5432/jp_vocab_test_plan",
    f"postgresql://plan:{SECRET}@localhost/jp_vocab_test_plan_2?hostaddr=127.0.0.1&sslmode=disable",
]

REJECTED = {
    "query host overrides localhost": f"postgresql://plan:{SECRET}@localhost:5432/jp_vocab_test?host=example.invalid",
    "remote hostaddr": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?hostaddr=203.0.113.5",
    "private hostaddr": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?hostaddr=10.0.0.1",
    "hostaddr as name": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?hostaddr=localhost",
    "remote host": f"postgresql://plan:{SECRET}@example.invalid:5432/jp_vocab_test",
    "multiple hosts": f"postgresql://plan:{SECRET}@localhost,example.invalid/jp_vocab_test",
    "multiple local hosts": f"postgresql://plan:{SECRET}@localhost:5432,127.0.0.1:5433/jp_vocab_test",
    "socket path": "postgresql:///jp_vocab_test?host=/tmp",
    "socket path in netloc": "postgresql://%2Ftmp/jp_vocab_test",
    "no host": "postgresql:///jp_vocab_test",
    "service": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?service=prod",
    "unknown option": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?options=-c%20search_path%3Dx",
    "bad port": f"postgresql://plan:{SECRET}@localhost:abc/jp_vocab_test",
    "keyword form": f"host=localhost dbname=jp_vocab_test password={SECRET}",
    "sqlite url": "sqlite:///./vocab.db",
    "other scheme": f"mysql://plan:{SECRET}@localhost/jp_vocab_test",
    "empty": "",
    "malformed": f"postgresql://plan:{SECRET}@localhost/jp_vocab_test?host",
}

# Local and well-formed, but not an obviously throwaway test database.
FORBIDDEN_DBNAMES = [
    "", "postgres", "template0", "template1", "vocab", "jp_vocab", "jp_vocab_reader",
    "jp_vocab_prod", "neondb", "jp_vocab_test-plan", "JP_VOCAB_TEST", "my_jp_vocab_test",
    "jp_vocab_test_", "jp_vocab_testing",
]


class FakeConnection:
    """Records what the emptiness check does. Only a SELECT may be executed,
    and only after the transaction was made read-only."""

    def __init__(self, row=None, execute_error=None):
        self.row = row
        self.execute_error = execute_error
        self.read_only = False
        self.statements: list[str] = []
        self.read_only_at_execute: list[bool] = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.read_only_at_execute.append(self.read_only)
        self.statements.append(sql)
        if self.execute_error:
            raise self.execute_error

    def fetchone(self):
        return self.row

    def rollback(self):
        pass

    def commit(self):
        self.commits += 1


def row(dbname="jp_vocab_test_plan", **counts):
    return (dbname, *(counts.get(name, 0) for name in INSPECT_COLUMNS))


class GuardTestCase(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(psycopg, "connect", side_effect=AssertionError("must not connect"))
        self.connect = patcher.start()
        self.addCleanup(patcher.stop)

    def assert_quiet(self, message: str) -> None:
        for secret in (SECRET, "example.invalid", "203.0.113.5", "10.0.0.1"):
            self.assertNotIn(secret, message)


class UrlValidationTest(GuardTestCase):
    def tearDown(self) -> None:
        self.connect.assert_not_called()

    def test_local_targets_are_accepted(self) -> None:
        for url in ACCEPTED:
            with self.subTest(url=url.replace(SECRET, "***")):
                self.assertEqual(validate_local_postgres_test_url(url, CLEAN_ENV), url)

    def test_unverified_targets_are_refused(self) -> None:
        for label, url in REJECTED.items():
            with self.subTest(label):
                with self.assertRaises(UnsafePostgresTarget) as caught:
                    validate_local_postgres_test_url(url, CLEAN_ENV)
                self.assert_quiet(str(caught.exception))

    def test_non_test_database_names_are_refused(self) -> None:
        for dbname in FORBIDDEN_DBNAMES:
            with self.subTest(dbname=dbname):
                with self.assertRaises(UnsafePostgresTarget) as caught:
                    validate_local_postgres_test_url(f"postgresql://plan:{SECRET}@localhost/{dbname}", CLEAN_ENV)
                self.assertIn("dbname", str(caught.exception))
                self.assert_quiet(str(caught.exception))

    def test_target_environment_variables_are_refused(self) -> None:
        for name, value in (
            ("PGHOSTADDR", "203.0.113.5"),
            ("PGHOST", "example.invalid"),
            ("PGSERVICE", "prod"),
            ("PGSERVICEFILE", "/etc/pg_service.conf"),
            ("PGSYSCONFDIR", "/etc"),
        ):
            with self.subTest(name):
                with self.assertRaises(UnsafePostgresTarget) as caught:
                    validate_local_postgres_test_url(GOOD_URL, {name: value})
                self.assertIn(name, str(caught.exception))
                self.assertNotIn(value, str(caught.exception))
        self.assertEqual(set(TARGET_ENV_VARS), {"PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR"})


class EmptinessCheckTest(GuardTestCase):
    def check(self, fake: FakeConnection) -> None:
        assert_empty_postgres_test_database(GOOD_URL, connect=lambda *a, **k: fake)

    def assert_read_only_select(self, fake: FakeConnection) -> None:
        self.assertEqual(len(fake.statements), 1)
        self.assertTrue(fake.statements[0].lstrip().upper().startswith("SELECT"))
        for word in ("CREATE", "DROP", "TRUNCATE", "DELETE", "INSERT", "UPDATE", "ALTER", "GRANT"):
            self.assertNotIn(word, fake.statements[0].upper())
        self.assertEqual(fake.read_only_at_execute, [True])
        self.assertEqual(fake.commits, 0)

    def test_empty_test_database_passes(self) -> None:
        fake = FakeConnection(row())
        self.check(fake)
        self.assert_read_only_select(fake)

    def test_existing_objects_stop_the_run(self) -> None:
        cases = {
            "table with zero rows (any relation)": {"relations": 1},
            "object in another schema": {"schemas": 1, "relations": 2},
            "function": {"routines": 1},
            "user type": {"types": 1},
            "extension": {"extensions": 1},
        }
        for label, counts in cases.items():
            with self.subTest(label):
                fake = FakeConnection(row(**counts))
                with self.assertRaises(UnsafePostgresTarget) as caught:
                    self.check(fake)
                self.assertIn("not empty", str(caught.exception))
                self.assert_read_only_select(fake)

    def test_different_database_stops_the_run(self) -> None:
        for dbname in ("postgres", "jp_vocab_test_other"):
            with self.subTest(dbname):
                with self.assertRaises(UnsafePostgresTarget):
                    self.check(FakeConnection(row(dbname=dbname)))

    def test_inspection_failures_stop_the_run(self) -> None:
        def refuse_connect(*args, **kwargs):
            raise psycopg.OperationalError(f"connection to example.invalid failed for {SECRET}")

        failures = {
            "permission denied": FakeConnection(execute_error=psycopg.errors.InsufficientPrivilege("permission denied")),
            "no row": FakeConnection(None),
            "short row": FakeConnection(("jp_vocab_test_plan", 0)),
            "non-numeric count": FakeConnection(("jp_vocab_test_plan", "x", 0, 0, 0, 0)),
        }
        for label, fake in failures.items():
            with self.subTest(label):
                with self.assertRaises(UnsafePostgresTarget):
                    self.check(fake)
        with self.assertRaises(UnsafePostgresTarget) as caught:
            assert_empty_postgres_test_database(GOOD_URL, connect=refuse_connect)
        self.assertIn("OperationalError", str(caught.exception))
        self.assert_quiet(str(caught.exception))


class LearningPlanModuleWiringTest(GuardTestCase):
    """Runs the real test module's import-time setup with psycopg.connect
    faked, and checks that a refused target never reaches init_db(), the
    app's get_connection() or DATABASE_URL."""

    def run_module(self, url: str):
        env = {k: v for k, v in os.environ.items() if k not in TARGET_ENV_VARS}
        env["LEARNING_PLAN_TEST_POSTGRES_URL"] = url
        env["DATABASE_URL"] = "sqlite:///untouched.db"
        with mock.patch.dict(os.environ, env, clear=True), \
             mock.patch.object(app.database, "init_db") as init_db, \
             mock.patch.object(app.database, "get_connection") as get_connection:
            try:
                runpy.run_path(str(TESTS_DIR / "test_learning_plan_progress.py"), run_name="guard_check")
                exit_message = None
            except SystemExit as stop:
                exit_message = str(stop.code)
            database_url = os.environ["DATABASE_URL"]
        init_db.assert_not_called()
        get_connection.assert_not_called()
        return exit_message, database_url

    def test_refused_url_stops_before_any_connection(self) -> None:
        message, database_url = self.run_module(REJECTED["query host overrides localhost"])
        self.connect.assert_not_called()
        self.assertIn("refused", message)
        self.assert_quiet(message)
        self.assertEqual(database_url, "sqlite:///untouched.db")

    def test_non_empty_database_stops_before_init(self) -> None:
        for label, fake in {
            "existing table": FakeConnection(row(relations=3)),
            "other schema": FakeConnection(row(schemas=1)),
            "permission denied": FakeConnection(execute_error=psycopg.errors.InsufficientPrivilege("denied")),
        }.items():
            with self.subTest(label):
                self.connect.reset_mock()
                self.connect.side_effect = lambda *a, **k: fake
                message, database_url = self.run_module(GOOD_URL)
                self.assertEqual(self.connect.call_count, 1)
                self.assertIn("refused", message)
                self.assert_quiet(message)
                self.assertEqual(database_url, "sqlite:///untouched.db")
                self.assertEqual(fake.read_only_at_execute, [True])

    def test_empty_database_is_checked_once_then_used(self) -> None:
        fake = FakeConnection(row())
        self.connect.side_effect = lambda *a, **k: fake
        message, database_url = self.run_module(GOOD_URL)
        self.assertIsNone(message)
        self.assertEqual(self.connect.call_count, 1)
        self.assertEqual(database_url, GOOD_URL)


class OverriddenTargetTest(GuardTestCase):
    """PostgreSQL mode passed the guard, then something else in the same run
    (e.g. another test module under discovery) changed DATABASE_URL. Every
    test class must fail before init_db() or any write -- never fall back to
    SQLite and report a PostgreSQL pass."""

    def test_overridden_database_url_fails_without_init_or_writes(self) -> None:
        overrides = {
            "another module's sqlite file": "sqlite:///other_module.db",
            "a different postgres url": "postgresql://plan@localhost/jp_vocab_test_other",
            "removed": None,
        }
        for label, override in overrides.items():
            with self.subTest(label):
                fake = FakeConnection(row())
                self.connect.reset_mock()
                self.connect.side_effect = lambda *a, **k: fake
                env = {k: v for k, v in os.environ.items() if k not in TARGET_ENV_VARS}
                env["LEARNING_PLAN_TEST_POSTGRES_URL"] = GOOD_URL
                with mock.patch.dict(os.environ, env, clear=True), \
                     mock.patch.object(app.database, "init_db") as init_db, \
                     mock.patch.object(app.database, "get_connection") as get_connection, \
                     mock.patch("sqlite3.connect", side_effect=AssertionError("must not open sqlite")) as sqlite_connect:
                    module = runpy.run_path(str(TESTS_DIR / "test_learning_plan_progress.py"), run_name="guard_check")
                    self.assertEqual(os.environ["DATABASE_URL"], GOOD_URL)
                    self.connect.side_effect = AssertionError("must not connect after the check")
                    if override is None:
                        del os.environ["DATABASE_URL"]
                    else:
                        os.environ["DATABASE_URL"] = override

                    suite = unittest.TestSuite()
                    loader = unittest.TestLoader()
                    for name in ("LearningPlanProgressTest", "LearningPlanProgressEndpointTest", "FirstReviewQueueTest"):
                        suite.addTests(loader.loadTestsFromTestCase(module[name]))
                    result = unittest.TestResult()
                    suite.run(result)

                self.assertFalse(result.wasSuccessful())
                self.assertEqual(result.testsRun, 0)  # every class stopped in setUpClass
                self.assertEqual(len(result.errors), 3)
                for _, trace in result.errors:
                    self.assertIn("no longer points at the checked PostgreSQL test database", trace)
                    self.assert_quiet(trace)
                init_db.assert_not_called()
                get_connection.assert_not_called()
                sqlite_connect.assert_not_called()
                self.assertEqual(self.connect.call_count, 1)  # the read-only emptiness check only


if __name__ == "__main__":
    unittest.main()
