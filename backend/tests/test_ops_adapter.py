"""Connection provider unit 6-1d (scripts/_ops_adapter.py): the adapter that joins the 6-1a
provider, the 6-1b verified certificate copy and the 6-1c observer.

REAL here: the unit 5 pre-check with real test-key signatures, the synthetic files under a
temporary deployment root, the verified copy written to and removed from disk. FAKE here: the
driver function (it records its keyword arguments and reads the copy at call time), the
connection and the cursor rows (from test_ops_observer). Nothing proves that a real driver
applies TLS, authentication or server `options`; psycopg / libpq connect entry points stay
patched to fail.

Run directly:      python tests/test_ops_adapter.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg import errors as pg_errors  # noqa: E402

import _ops_adapter as ad  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_tlsroot as tr  # noqa: E402
import test_ops_observer as to  # noqa: E402  (module only: its tests are not re-run here)
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_ops_provider as pt  # noqa: E402  (module only)

SECRET = pf.SECRET
ROOT_BYTES = pf.FILES["ops/tls/root.pem"]
REAL_RMDIR, REAL_MKDTEMP = os.rmdir, tr.tempfile.mkdtemp


def copy_rmdir_fails():
    """Fail only the copy folder's removal (signature checks also use temporary folders)."""
    def rmdir(path, *args, **kwargs):
        if os.path.basename(str(path)).startswith("ops_tls_"):
            raise OSError(5, SECRET)
        return REAL_RMDIR(path, *args, **kwargs)
    return mock.patch.object(tr.os, "rmdir", rmdir)


def copy_mkdtemp_fails():
    def mkdtemp(*args, **kwargs):
        if kwargs.get("prefix") == "ops_tls_":
            raise OSError(5, SECRET)
        return REAL_MKDTEMP(*args, **kwargs)
    return mock.patch.object(tr.tempfile, "mkdtemp", mkdtemp)


class FakeDriver:
    """FAKE driver function: records keyword arguments and reads the certificate path it was given
    while the call is in progress (what a driver would read). Returns prepared fake connections."""

    def __init__(self, *connections, error=None):
        self.connections = list(connections)
        self.error = error
        self.calls: list[dict] = []
        self.seen: list[tuple[str, bytes | None, bool]] = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        path = kwargs.get("sslrootcert", "")
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            data = None
        self.seen.append((path, data, os.path.isdir(os.path.dirname(path))))
        if self.error is not None:
            raise self.error
        return self.connections.pop(0)


class Base(pt.Base):
    def read_profile(self):
        return pv.expected_profile_fingerprint(to.READ_EXPECTED, role="ops_read", access="read")

    def write_profile(self):
        return pv.expected_profile_fingerprint(to.WRITE_EXPECTED, role="ops_write_prb", access="write")

    def provide(self, driver, inputs=None, expected=to.READ_EXPECTED):
        return ad.provide_with_adapter(inputs or self.read_inputs(), expected=expected, driver=driver)

    def refused(self, code, driver, *, inputs=None, expected=to.READ_EXPECTED, also=None):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.provide(driver, inputs, expected)
        error = caught.exception
        self.assertEqual(error.code, code)
        if also is not None:
            self.assertEqual(error.also, also)
        self.assertNotIn(SECRET, repr(error) + str(error) + repr(error.also))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error

    def assert_copy_gone(self, driver):
        for path, _, _ in driver.seen:
            self.assertFalse(os.path.lexists(path))
            self.assertFalse(os.path.lexists(os.path.dirname(path)))


class Integration(Base):
    def test_read_handover_passes_copy_and_fixed_values(self):
        conn = to.ObsConn()
        driver = FakeDriver(conn)
        handoff = self.provide(driver)
        kwargs = driver.calls[0]
        self.assertEqual(set(kwargs), ad.DSN_KEYS | ad.FIXED_KEYS)
        self.assertEqual((kwargs["user"], kwargs["password"], kwargs["host"], kwargs["port"], kwargs["dbname"]),
                         ("ops_read", SECRET, "db.synthetic.test", "5432", "jp_vocab"))
        self.assertEqual(kwargs["sslmode"], "verify-full")
        path, data, _ = driver.seen[0]
        self.assertNotEqual(os.path.normcase(path), os.path.normcase(self.root_pem()))   # the copy, not the original
        self.assertFalse(os.path.normcase(path).startswith(os.path.normcase(self.root)))
        self.assertEqual(data, ROOT_BYTES)                       # exact bytes readable during the call
        self.assertEqual({k: kwargs[k] for k in ad.FIXED_KEYS}, dict(pv.fixed_parameters("read")))
        self.assertIn("-c default_transaction_isolation=read\\ committed", kwargs["options"])
        self.assertIn("-c default_transaction_read_only=on", kwargs["options"])
        self.assert_copy_gone(driver)                            # removed after the call, before handover
        self.assertEqual(conn.log, list(pv.OBSERVATION_START) + ["ROLLBACK"])
        self.assertEqual([n for n, _ in conn.queries], list(to.QUERY_ORDER))
        self.assertNotIn(SECRET, repr(handoff) + repr(handoff.summary))
        handoff.take().execute(pt.BUSINESS_FIRST)

    def test_write_handover(self):
        conn = to.ObsConn(to.catalog("write"))
        driver = FakeDriver(conn)
        handoff = self.provide(driver, self.write_inputs(), to.WRITE_EXPECTED)
        self.assertEqual(driver.calls[0]["user"], "ops_write_prb")
        self.assertIn("-c default_transaction_read_only=off", driver.calls[0]["options"])
        self.assertEqual(driver.seen[0][1], ROOT_BYTES)
        self.assert_copy_gone(driver)
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_connect_failures_remove_the_copy(self):
        for error, code in ((pg_errors.OperationalError(SECRET), "connect_failed"),
                            (pg_errors.ConnectionTimeout(SECRET), "connect_timeout"),
                            (OSError(10060, SECRET), "connect_failed")):
            with self.subTest(code=code):
                driver = FakeDriver(error=error)
                self.refused(code, driver, also=())
                self.assertEqual(driver.seen[0][1], ROOT_BYTES)       # the copy existed during the call
                self.assert_copy_gone(driver)

    def test_copy_failures_block_the_driver(self):
        real = pv.op.run_synthetic_preflight

        def preflight_then_tamper(inputs):
            result = real(inputs)
            with open(self.root_pem(), "ab") as handle:          # changed after the pre-check (real file)
                handle.write(b"tampered\n")
            return result

        driver = FakeDriver(to.ObsConn())
        with mock.patch.object(pv.op, "run_synthetic_preflight", preflight_then_tamper):
            with self.assertRaises(pv.OpsProviderRefused) as caught:
                self.provide(driver)
        self.assertTrue(caught.exception.code.startswith("manifest_"))
        self.assertNotIn(SECRET, repr(caught.exception))
        self.assertEqual(driver.calls, [])
        self.write_files(pf.FILES)
        for patch, code in ((copy_mkdtemp_fails(), "tls_copy_tempdir_failed"),
                            (mock.patch.object(tr, "_read_back", side_effect=tr.OpsTlsRootRefused("tls_copy_mismatch")),
                             "tls_copy_mismatch")):
            with self.subTest(code=code):
                driver = FakeDriver(to.ObsConn())
                with patch:
                    self.refused(code, driver)
                self.assertEqual(driver.calls, [])

    def test_copy_cleanup_failure_after_connect_is_not_handed_over(self):
        for close_error, code, also in (
                (None, "tls_copy_cleanup_unconfirmed", ("tls_copy_folder_remove_failed",)),
                (OSError(5, SECRET), "connection_close_unconfirmed",
                 ("tls_copy_cleanup_unconfirmed", "tls_copy_folder_remove_failed"))):
            with self.subTest(code=code):
                conn = to.ObsConn(close_error=close_error)
                driver = FakeDriver(conn)
                with copy_rmdir_fails():
                    self.refused(code, driver, also=also)
                self.assertEqual((conn.close_calls, conn.log, conn.queries), (1, [], []))   # never observed
                folder = os.path.dirname(driver.seen[0][0])
                self.assertTrue(os.path.isdir(folder))           # reported unconfirmed, really left behind
                REAL_RMDIR(folder)

    def test_copy_cleanup_failure_with_connect_failure(self):
        driver = FakeDriver(error=pg_errors.OperationalError(SECRET))
        with copy_rmdir_fails():
            self.refused("tls_copy_cleanup_unconfirmed", driver,
                         also=("connect_failed", "tls_copy_folder_remove_failed"))
        REAL_RMDIR(os.path.dirname(driver.seen[0][0]))

    def test_failures_after_connect(self):
        cases = [
            ("observed_ownership", dict(cat=to.changed(ownership={**to.catalog()["ownership"], "relations": 1})), ()),
            ("observation_rollback_failed",
             dict(rollback_error=pg_errors.OperationalError(SECRET)), ()),
            ("connection_close_unconfirmed",
             dict(cat=to.changed(ownership={**to.catalog()["ownership"], "relations": 1}),
                  close_error=OSError(5, SECRET)), ("observed_ownership",)),
            ("connection_close_unconfirmed",
             dict(rollback_error=pg_errors.OperationalError(SECRET), close_error=OSError(5, SECRET)),
             ("observation_rollback_failed",)),
            ("observation_timeout", dict(cat=dict(to.catalog(), override={"tls": pg_errors.QueryCanceled(SECRET)})), ()),
        ]
        for code, kwargs, also in cases:
            with self.subTest(code=code, also=also):
                conn = to.ObsConn(kwargs.pop("cat", None), **kwargs)
                driver = FakeDriver(conn)
                self.refused(code, driver, also=also)
                self.assertEqual(conn.close_calls, 1)
                self.assert_copy_gone(driver)

    def test_reconnect_makes_everything_new(self):
        spy = mock.Mock(wraps=pv.op.run_synthetic_preflight)
        first, second = to.ObsConn(), to.ObsConn()
        driver = FakeDriver(first, second)
        observers = []
        real_observer = ad.ob.CatalogObserver

        def counting_observer():
            observers.append(real_observer())
            return observers[-1]

        with mock.patch.object(pv.op, "run_synthetic_preflight", spy), \
                mock.patch.object(ad.ob, "CatalogObserver", counting_observer):
            self.provide(driver)
            self.provide(driver)
        self.assertEqual((spy.call_count, len(driver.calls), len(observers)), (2, 2, 2))
        self.assertIsNot(observers[0], observers[1])
        self.assertNotEqual(driver.seen[0][0], driver.seen[1][0])     # a new copy path each time
        self.assertTrue(all(seen[1] == ROOT_BYTES for seen in driver.seen))
        self.assertEqual([len(c.queries) for c in (first, second)], [len(to.QUERY_ORDER)] * 2)
        self.assert_copy_gone(driver)


class Arguments(Base):
    def factory(self, driver=None):
        return ad.CopyingFactory(self.manifest, self.root, driver or FakeDriver(to.ObsConn()))

    def request(self, dsn=None, fixed=None):
        return pv.ConnectRequest(dsn or self.dsn(), fixed if fixed is not None else pv.fixed_parameters("read"))

    def code(self, expected, factory, request):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            factory.open(request)
        self.assertEqual(caught.exception.code, expected)
        self.assertNotIn(SECRET, repr(caught.exception) + repr(caught.exception.also))
        self.assertTrue(caught.exception.__suppress_context__ or caught.exception.__context__ is None)

    def test_fixed_values_cannot_be_extended_or_overridden(self):
        fixed = pv.fixed_parameters("read")
        for bad in (fixed + (("target_session_attrs", "any"),), fixed + (("host", "evil.test"),),
                    fixed + (("password", "x"),), fixed[1:], fixed + fixed[:1], (("options", 1),) + fixed[1:],
                    list(fixed)):
            with self.subTest(bad=repr(bad)[:40]):
                driver = FakeDriver(to.ObsConn())
                self.code("connect_arguments_conflict", self.factory(driver), self.request(fixed=bad))
                self.assertEqual(driver.calls, [])

    def test_dsn_must_be_the_checked_shape(self):
        other = os.path.join(self.root, "other.pem")
        for dsn in (self.dsn(root=other), self.dsn(sslmode="require"), self.dsn() + "&application_name=x",
                    f"host=db.synthetic.test password={SECRET} '", "not a dsn = = '"):
            with self.subTest(dsn=dsn.replace(SECRET, "*")[:30]):
                driver = FakeDriver(to.ObsConn())
                self.code("connect_arguments_invalid", self.factory(driver), self.request(dsn=dsn))
                self.assertEqual(driver.calls, [])

    def test_factory_is_single_use(self):
        driver = FakeDriver(to.ObsConn(), to.ObsConn())
        factory = self.factory(driver)
        factory.open(self.request())
        self.code("adapter_already_used", factory, self.request())
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(repr(factory), "CopyingFactory()")
        self.assert_copy_gone(driver)


class Boundaries(Base):
    def test_default_entry_production_and_no_driver(self):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_connection(self.read_inputs(), expected=to.READ_EXPECTED)
        self.assertEqual(caught.exception.code, "connection_factory_not_implemented")
        driver = FakeDriver(to.ObsConn())
        self.refused("mode_not_synthetic", driver, inputs=self.read_inputs(mode="ops"))
        for missing in (None, "psycopg.connect"):
            with self.assertRaises(pv.OpsProviderRefused) as caught:
                ad.provide_with_adapter(self.read_inputs(), expected=to.READ_EXPECTED, driver=missing)
            self.assertEqual(caught.exception.code, "connection_factory_not_implemented")
        self.assertEqual(driver.calls, [])

    def test_real_connect_entry_points_fail_the_test(self):
        """The real driver, if passed, hits the patched entry point and fails at once."""
        with self.assertRaises(AssertionError):
            self.provide(psycopg.connect)

    def test_module_static_rules(self):
        source = (TESTS_DIR.parent / "scripts" / "_ops_adapter.py").read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', "", source)
        self.assertIsNone(re.search(r"psycopg\.connect|\.connect\(|Connection\.connect|pq\.PGconn", code))
        for forbidden in ("os.environ", "getenv", "argparse", "sys.argv", "subprocess", "import_module",
                          "__import__", "exec(", "eval(", "from app", "import app", "socket", "print("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code)



ARTIFACT = pt.pf.hashlib.sha256(b"plan file").hexdigest()


class ArtifactThroughAdapter(Base):
    """Contract 3-3-1: the adapter hands the same input object on (fake driver, no real connect)."""

    def test_value_is_passed_unchanged(self):
        inputs, plan = pt.ArtifactAfterConnect.artifact_write_inputs(self)
        seen = []
        real = pv.provide_synthetic_connection

        def spy(given, **kwargs):
            seen.append(given)
            return real(given, **kwargs)
        with mock.patch.object(pv, "provide_synthetic_connection", spy):
            handoff = self.provide(FakeDriver(to.ObsConn(to.catalog("write"))), inputs, to.WRITE_EXPECTED)
        self.assertIs(seen[0], inputs)
        self.assertEqual(seen[0].artifact_sha256, ARTIFACT)
        self.assertEqual(handoff.summary.job_plan, plan)
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_audit_style_inputs_need_no_artifact(self):
        handoff = self.provide(FakeDriver(to.ObsConn()))
        self.assertEqual(handoff.summary.job_plan, pt.op.run_synthetic_preflight(self.read_inputs()).job_plan)
        handoff.take().execute(pt.BUSINESS_FIRST)

if __name__ == "__main__":
    unittest.main()
