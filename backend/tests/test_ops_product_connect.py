"""OPS_MIGRATION_CLI_PLAN 6-2: the synthetic provider connection as the product's connection context.

Real synthetic approvals, signatures (test-only temporary keys) and pre-check; FAKE driver,
connection and observation. The fake's call order shows what the helper asks for; it does NOT
prove PostgreSQL commit / rollback semantics.

Run directly:      python tests/test_ops_product_connect.py
"""

from __future__ import annotations

import subprocess
import sys
import traceback
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location: the app is imported by the
    sys.path.append(str(BACKEND))     # helper after its pre-check, never here

from psycopg import errors as pg_errors  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_product_connect as pc  # noqa: E402
import _ops_provider as pv  # noqa: E402
import test_ops_adapter as ta  # noqa: E402  (module only)
import test_ops_observer as to  # noqa: E402  (module only)

SECRET = ta.SECRET
BUSINESS_FIRST = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"


class BizConn(to.ObsConn):
    """FAKE: observation connection that also takes business statements with parameters."""

    def __init__(self, cat=None, *, commit_error=None, row_factory_error=None, **kwargs):
        super().__init__(cat, **kwargs)
        self.commit_error, self.row_factory_error = commit_error, row_factory_error
        self.params: list = []
        self._row_factory = None

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        if self.row_factory_error is not None:
            raise self.row_factory_error
        self._row_factory = value

    def execute(self, sql, params=None):
        if params is not None:
            self.params.append(params)
        return super().execute(sql)

    def commit(self):
        self.commits += 1
        self.log.append("COMMIT")
        if self.commit_error is not None:
            raise self.commit_error
        self.status, self.statements_in_txn = TransactionStatus.IDLE, 0


class Base(ta.Base):
    def connector(self, conn=None, inputs=None, expected=to.READ_EXPECTED, driver=None):
        self.conn = conn if conn is not None else BizConn()
        self.driver = driver or ta.FakeDriver(self.conn)
        return pc.ProductConnector(inputs or self.read_inputs(), expected=expected, driver=self.driver)

    def writer(self, conn=None, driver=None):
        return self.connector(conn if conn is not None else BizConn(to.catalog("write")), self.write_inputs(),
                              to.WRITE_EXPECTED, driver)

    def after_handover(self) -> list[str]:
        log = self.conn.log
        return log[log.index("ROLLBACK") + 1:]                  # the provider's observation ends in ROLLBACK

    def refused(self, code, fn, *args, also=None, **kwargs):
        with self.assertRaises(pc.OpsProductConnectionError) as caught:
            fn(*args, **kwargs)
        error = caught.exception
        self.assertEqual(error.code, code)
        if also is not None:
            self.assertEqual(error.also, also)
        self.assertEqual(error.args, (code,))
        self.assertNotIn(SECRET, repr(error) + str(error) + repr(error.also))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Flow(Base):
    def test_write_connection(self):
        connect = self.writer()
        context = connect(read_only=False)
        with context as c:
            from app.database import AppPostgresConnection
            self.assertIsInstance(c, AppPostgresConnection)
            self.assertIs(self.conn.row_factory, dict_row)
            c.execute(BUSINESS_FIRST)                              # the business sets its first transaction
            c.execute("UPDATE vocab_items SET srs_engine = ? WHERE id = ?", ("fsrs", 7))
        self.assertEqual(self.after_handover(), [BUSINESS_FIRST, "UPDATE vocab_items SET srs_engine = %s WHERE id = %s",
                                                 "COMMIT"])
        self.assertEqual(self.conn.params, [(), ("fsrs", 7)])
        self.assertEqual((self.conn.close_calls, self.conn.closed, len(self.driver.calls)), (1, True, 1))
        self.assertEqual(connect.failures, [])

    def test_read_connection_matches_get_connection(self):
        connect = self.connector()
        with connect(read_only=True) as c:
            c.execute("SELECT 1")
        self.assertEqual(self.after_handover(), ["SET TRANSACTION READ ONLY", "SELECT 1", "COMMIT"])
        self.assertEqual(self.conn.close_calls, 1)

    def test_request_and_approved_step_must_match(self):
        for make, read_only in ((self.connector, False), (self.writer, True)):
            with self.subTest(read_only=read_only):
                connect = make()
                self.refused("connection_access_mismatch", connect, read_only=read_only)
                self.assertEqual(self.driver.calls, [])
        connect = self.connector()
        for value in (1, "true", None):
            with self.subTest(value=value):
                self.refused("read_only_invalid", connect, read_only=value)
        self.assertEqual(self.driver.calls, [])

    def test_every_call_is_new_and_single_use(self):
        first, second = BizConn(), BizConn()
        driver = ta.FakeDriver(first, second)
        spy = mock.Mock(wraps=pv.op.run_synthetic_preflight)
        connect = self.connector(first, driver=driver)
        with mock.patch.object(pv.op, "run_synthetic_preflight", spy):
            a, b = connect(read_only=True), connect(read_only=True)
        self.assertEqual((spy.call_count, len(driver.calls)), (2, 2))
        self.assertTrue(first.queries and second.queries)           # each connection observed itself
        with a:
            pass
        self.refused("connection_already_used", a.__enter__)
        with b:
            pass
        self.assertEqual((first.close_calls, second.close_calls), (1, 1))

    def test_refusals_open_nothing_and_never_retry(self):
        connect = pc.ProductConnector(self.read_inputs(approval_signature=b"bad"), expected=to.READ_EXPECTED,
                                      driver=ta.FakeDriver(BizConn()))
        self.refused("preflight_approval_signature_invalid", connect, read_only=True)
        failing = ta.FakeDriver(error=pg_errors.OperationalError(f"password={SECRET}"))
        connect = pc.ProductConnector(self.read_inputs(), expected=to.READ_EXPECTED, driver=failing)
        error = self.refused("connect_failed", connect, read_only=True)
        self.assertEqual(len(failing.calls), 1)                        # no automatic retry
        self.assertNotIn(SECRET, repr(error))

    def test_production_and_missing_driver(self):
        from dataclasses import replace
        self.refused("mode_not_synthetic", pc.ProductConnector, replace(self.read_inputs(), mode="ops"),
                     expected=to.READ_EXPECTED, driver=ta.FakeDriver())
        self.refused("connection_factory_not_implemented", pc.ProductConnector, self.read_inputs(),
                     expected=to.READ_EXPECTED, driver=None)

    def test_import_order(self):
        code = (f"import sys; sys.path[:0] = [{str(BACKEND / 'scripts')!r}]\n"
                "import _ops_product_connect\n"
                "print('APP', any(m == 'app' or m.startswith('app.') for m in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR))
        self.assertIn("APP False", done.stdout, done.stderr[-500:])


class Cleanup(Base):
    def test_business_error_rolls_back_closes_once_and_propagates(self):
        connect = self.writer()
        boom = ValueError("business")
        with self.assertRaises(ValueError) as caught:
            with connect(read_only=False) as c:
                c.execute("UPDATE x SET y = ?", (1,))
                raise boom
        self.assertIs(caught.exception, boom)
        self.assertEqual(self.after_handover(), ["UPDATE x SET y = %s", "ROLLBACK"])
        self.assertEqual((self.conn.commits, self.conn.close_calls), (0, 1))

    def test_interrupt_inside_business_is_kept(self):
        connect = self.writer()
        stop = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt) as caught:
            with connect(read_only=False):
                raise stop
        self.assertIs(caught.exception, stop)
        self.assertEqual((self.after_handover(), self.conn.close_calls), (["ROLLBACK"], 1))

    def test_commit_failure_code_and_rollback(self):
        connect = self.writer(BizConn(to.catalog("write"), commit_error=pg_errors.OperationalError(SECRET)))
        context = connect(read_only=False)

        def run():
            with context as c:
                c.execute("UPDATE x SET y = 1")
        self.refused("commit_failed_result_unconfirmed", run, also=())
        self.assertEqual(self.after_handover(), ["UPDATE x SET y = 1", "COMMIT", "ROLLBACK"])
        self.assertEqual(self.conn.close_calls, 1)

    def test_failure_priority(self):
        cases = (
            (dict(commit_error=pg_errors.OperationalError(SECRET), rollback_error=pg_errors.OperationalError(SECRET),
                  close_error=OSError(SECRET)),
             "connection_close_unconfirmed", ("commit_failed_result_unconfirmed", "rollback_failed")),
            (dict(commit_error=pg_errors.OperationalError(SECRET), rollback_error=pg_errors.OperationalError(SECRET)),
             "commit_failed_result_unconfirmed", ("rollback_failed",)),
            (dict(close_error=OSError(SECRET)), "connection_close_unconfirmed", ()),
        )
        for kwargs, code, also in cases:
            with self.subTest(code=code, also=also):
                connect = self.writer()
                context = connect(read_only=False)
                for name, value in kwargs.items():               # armed after the hand-over only
                    setattr(self.conn, name, value)

                def run():
                    with context:
                        pass
                self.refused(code, run, also=also)
                self.assertEqual(self.conn.close_calls, 1)

    def test_business_error_keeps_priority_over_cleanup_failures(self):
        connect = self.writer()
        context = connect(read_only=False)
        self.conn.rollback_error, self.conn.close_error = pg_errors.OperationalError(SECRET), OSError(SECRET)
        boom = ValueError("business")
        with self.assertRaises(ValueError) as caught:
            with context:
                raise boom
        self.assertIs(caught.exception, boom)
        self.assertEqual(connect.failures, ["connection_close_unconfirmed", "rollback_failed"])
        self.assertEqual(self.conn.close_calls, 1)

    def test_interrupt_during_commit_is_raised_after_cleanup(self):
        stop = KeyboardInterrupt()
        connect = self.writer(BizConn(to.catalog("write"), commit_error=stop))
        with self.assertRaises(KeyboardInterrupt) as caught:
            with connect(read_only=False):
                pass
        self.assertIs(caught.exception, stop)
        self.assertEqual((self.after_handover(), self.conn.close_calls), (["COMMIT", "ROLLBACK"], 1))
        self.assertEqual(connect.failures, ["commit_failed_result_unconfirmed"])

    def test_preparation_failure_returns_no_connection(self):
        for close_error, code, also in ((None, "connection_prepare_failed", ()),
                                        (OSError(SECRET), "connection_close_unconfirmed", ("connection_prepare_failed",))):
            with self.subTest(close_error=bool(close_error)):
                conn = BizConn(row_factory_error=RuntimeError(SECRET), close_error=close_error)
                connect = self.connector(conn)
                self.refused(code, connect, read_only=True, also=also)
                self.assertEqual((conn.close_calls, len(self.driver.calls)), (1, 1))
        conn = BizConn(row_factory_error=KeyboardInterrupt())
        connect = self.connector(conn)
        with self.assertRaises(KeyboardInterrupt):
            connect(read_only=True)
        self.assertEqual(conn.close_calls, 1)



class InterruptCombinations(Base):
    """Contract 6-2 (review fix): the first business exception / interrupt is kept, cleanup interrupts
    never replace it, close is tried once, codes are recorded, no raw text in the traceback."""

    def armed_writer(self, **errors):
        connect = self.writer()
        context = connect(read_only=False)
        for name, value in errors.items():                   # after the hand-over only
            setattr(self.conn, name, value)
        return connect, context

    def test_preparation_error_then_close_interrupt(self):
        for stop in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(stop=type(stop).__name__):
                conn = BizConn(row_factory_error=RuntimeError(SECRET), close_error=stop)
                connect = self.connector(conn)
                with self.assertRaises(BaseException) as caught:
                    connect(read_only=True)
                self.assertIs(caught.exception, stop)
                if isinstance(stop, SystemExit):
                    self.assertEqual(caught.exception.code, 7)
                self.assertIsNone(caught.exception.__context__)
                self.assertNotIn(SECRET, "".join(traceback.format_exception(caught.exception)))
                self.assertEqual(conn.close_calls, 1)
                self.assertEqual(connect.failures, ["connection_close_unconfirmed", "connection_prepare_failed"])

    def test_business_interrupt_then_rollback_interrupt(self):
        first, other = KeyboardInterrupt(), SystemExit(9)
        connect, context = self.armed_writer(rollback_error=other)
        with self.assertRaises(BaseException) as caught:
            with context:
                raise first
        self.assertIs(caught.exception, first)
        self.assertEqual(self.conn.close_calls, 1)
        self.assertEqual(connect.failures, ["rollback_failed", "cleanup_interrupted"])

    def test_business_interrupt_then_close_interrupt(self):
        first, other = SystemExit(3), KeyboardInterrupt()
        connect, context = self.armed_writer(close_error=other)
        with self.assertRaises(BaseException) as caught:
            with context:
                raise first
        self.assertIs(caught.exception, first)
        self.assertEqual(caught.exception.code, 3)
        self.assertEqual(self.conn.close_calls, 1)
        self.assertEqual(connect.failures, ["connection_close_unconfirmed", "cleanup_interrupted"])

    def test_commit_interrupt_then_rollback_and_close_interrupts(self):
        first = KeyboardInterrupt()
        connect, context = self.armed_writer(commit_error=first, rollback_error=SystemExit(1),
                                             close_error=KeyboardInterrupt())
        with self.assertRaises(BaseException) as caught:
            with context:
                pass
        self.assertIs(caught.exception, first)
        self.assertIsNone(caught.exception.__context__)
        self.assertEqual(self.after_handover(), ["COMMIT", "ROLLBACK"])
        self.assertEqual(self.conn.close_calls, 1)
        self.assertEqual(connect.failures, ["connection_close_unconfirmed", "commit_failed_result_unconfirmed",
                                            "rollback_failed"])

    def test_business_error_then_cleanup_interrupt(self):
        for errors in (dict(rollback_error=KeyboardInterrupt()), dict(close_error=SystemExit(2)),
                       dict(rollback_error=SystemExit(4), close_error=KeyboardInterrupt())):
            with self.subTest(errors=sorted(errors)):
                boom = ValueError("business")
                connect, context = self.armed_writer(**errors)
                with self.assertRaises(BaseException) as caught:
                    with context:
                        raise boom
                self.assertIs(caught.exception, boom)
                self.assertEqual(self.conn.close_calls, 1)
                self.assertIn("cleanup_interrupted", connect.failures)
                if "rollback_error" in errors:
                    self.assertIn("rollback_failed", connect.failures)
                if "close_error" in errors:
                    self.assertIn("connection_close_unconfirmed", connect.failures)


class StatusConn(BizConn):
    """FAKE: close() returns normally, but reading `closed` afterwards can fail once armed."""

    def __init__(self, *args, **kwargs):
        self.closed_error = None
        super().__init__(*args, **kwargs)

    @property
    def closed(self):
        if self.closed_error is not None and self.close_calls:
            raise self.closed_error
        return self._closed

    @closed.setter
    def closed(self, value):
        self._closed = value


class CloseStatusCheck(Base):
    """Contract 6-2 (review fix 2): the closed-state check is part of the protected close step."""

    def armed(self, error):
        connect = self.writer(StatusConn(to.catalog("write")))
        context = connect(read_only=False)
        self.conn.closed_error = error
        return connect, context

    def no_secret(self, error):
        self.assertNotIn(SECRET, "".join(traceback.format_exception(error)))

    def test_normal_end(self):
        connect, context = self.armed(RuntimeError(SECRET))
        with self.assertRaises(pc.OpsProductConnectionError) as caught:
            with context:
                pass
        self.assertEqual((caught.exception.code, caught.exception.also), ("connection_close_unconfirmed", ()))
        self.no_secret(caught.exception)
        self.assertEqual((self.conn.close_calls, self.conn.commits), (1, 1))
        self.assertEqual(connect.failures, ["connection_close_unconfirmed"])
        for stop in (KeyboardInterrupt(), SystemExit(5)):
            with self.subTest(stop=type(stop).__name__):
                connect, context = self.armed(stop)
                with self.assertRaises(BaseException) as caught:
                    with context:
                        pass
                self.assertIs(caught.exception, stop)
                self.assertIsNone(caught.exception.__context__)
                self.assertEqual(self.conn.close_calls, 1)
                self.assertEqual(connect.failures, ["connection_close_unconfirmed"])

    def test_business_error_or_interrupt_is_kept(self):
        for first in (ValueError("business"), KeyboardInterrupt(), SystemExit(6)):
            for status_error in (RuntimeError(SECRET), KeyboardInterrupt(), SystemExit(8)):
                with self.subTest(first=type(first).__name__, status=type(status_error).__name__):
                    connect, context = self.armed(status_error)
                    with self.assertRaises(BaseException) as caught:
                        with context:
                            raise first
                    self.assertIs(caught.exception, first)
                    if isinstance(first, SystemExit):
                        self.assertEqual(caught.exception.code, 6)
                    self.no_secret(caught.exception)
                    self.assertEqual(self.conn.close_calls, 1)
                    expected = ["connection_close_unconfirmed"]
                    if not isinstance(status_error, Exception):
                        expected.append("cleanup_interrupted")
                    self.assertEqual(connect.failures, expected)

if __name__ == "__main__":
    unittest.main()
