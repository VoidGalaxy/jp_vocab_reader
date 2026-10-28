"""Read-only audit over the connection provider, synthetic mode (scripts/_ops_audit_run.py).

Two kinds of tests, kept apart:
- ScopeUnit: `check_scope` on parsed approvals only (returned values; no pre-check, no provider).
- Integration: the REAL unit 5 pre-check (real test-key signatures, synthetic files), the REAL
  6-1a provider, 6-1b copy, 6-1c observer and 6-1d adapter, and the REAL `read_snapshot` /
  `_require_snapshot` of app/srs/invariant_audit.py, on a FAKE driver and FAKE connection.
  `audit()` itself is replaced by a fake that calls the real `_require_snapshot` and returns a
  prepared report: no real audit SQL runs, and nothing here is a real PostgreSQL audit.
psycopg / libpq connect entry points stay patched to fail.

Run directly:      python tests/test_ops_audit_run.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

from psycopg.pq import TransactionStatus  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_audit_run as ar  # noqa: E402
import _ops_approval as oa  # noqa: E402
import _ops_provider as pv  # noqa: E402
import test_ops_adapter as ta  # noqa: E402  (module only)
import test_ops_observer as to  # noqa: E402  (module only)
import test_ops_preflight as pf  # noqa: E402  (module only)

SECRET = pf.SECRET
JOB_KEY = "audit-synthetic-1"
ALLOWED = re.compile(r"(SET TRANSACTION |SET LOCAL (statement_timeout|lock_timeout) |SELECT |SHOW )")
PASS = {"audit_version": 1, "status": "pass",
        "checks": {**{f"I{i}": {"status": "pass", "violations": 0, "unknown": 0} for i in range(1, 6)},
                   "I6": {"status": "not_evaluated", "reason": "deletion_baseline_required"},
                   "I7": {"status": "not_evaluated", "reason": "deletion_baseline_required"}}}


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class AuditConn(to.ObsConn):
    """FAKE: the provider-test connection plus the few statements of the audit transaction.
    Records every statement after the handover (the SQL trace)."""

    def __init__(self, cat=None, *, recheck=None, identity=None, opens_on_row_factory=False,
                 snapshot_rollback_error=None, **kwargs):
        super().__init__(cat, **kwargs)
        self.snapshot_rollback_error = snapshot_rollback_error   # only the audit's rollback fails
        self.trace: list[str] = []
        self.row_factory_seen: list = []
        self.recheck = recheck
        self.identity = identity
        self.opens_on_row_factory = opens_on_row_factory
        self.snapshot = None
        self._row_factory = None
        self.handed = False

    @property
    def row_factory(self):
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._row_factory = value
        if self.opens_on_row_factory:
            self.status = TransactionStatus.INTRANS          # something left a transaction open

    def execute(self, sql, params=None):
        if not self.handed:                                  # provider's observation statements
            return super().execute(sql)
        self.trace.append(sql)
        self.row_factory_seen.append(self._row_factory)
        super().execute(sql)
        if sql.startswith("SET TRANSACTION"):
            self.snapshot = sql
            return FakeResult([])
        if sql.startswith("SET LOCAL"):
            return FakeResult([])
        if sql == ar.RECHECK:
            row = {"dbname": pf.TARGET.database, "port": pf.TARGET.port, "version": f"{pf.TARGET.server_major}0006"}
            return FakeResult([{**row, **(self.recheck or {})}])
        if sql == ar.IDENTITY:
            return FakeResult(self.identity if self.identity is not None
                              else [{"identity_value": pf.TARGET.identity_value}])
        if "current_setting('transaction_read_only')" in sql:          # the real _require_snapshot
            ok = self.snapshot == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            return FakeResult([{"ro": "on" if ok else "off", "isolation": "repeatable read" if ok else "read committed"}])
        raise AssertionError("statement outside the fake audit transaction")

    def rollback(self):
        if self.handed and self.snapshot_rollback_error is not None:
            self.trace.append("ROLLBACK")
            raise self.snapshot_rollback_error
        super().rollback()
        if self.handed:
            self.trace.append("ROLLBACK")
        self.handed = True                                   # the provider's rollback ends observation


def fake_audit(result=PASS, calls=None):
    from app.srs import invariant_audit as ia

    def audit(connection, *, baseline=None):
        ia._require_snapshot(connection)                     # the REAL snapshot requirement
        if calls is not None:
            calls.append(connection)
        return json.loads(json.dumps(result))
    return audit


class Base(ta.Base):
    def setUp(self):
        super().setUp()
        for patch in (mock.patch.dict(os.environ, dict(os.environ)),):
            patch.start()
            self.addCleanup(patch.stop)
        from app import database
        for name in ("get_connection", "init_db", "initialize_database"):
            if hasattr(database, name):
                patch = mock.patch.object(database, name, side_effect=AssertionError(f"{name} called"))
                patch.start()
                self.addCleanup(patch.stop)

    def scope(self, **changes):
        inputs = {"audit_scope": "database_all", "audit_db_identity": pf.db_identity()}
        inputs.update(changes)
        return {k: v for k, v in inputs.items() if v is not None}

    def approval(self, *, job_inputs=None, **changes) -> bytes:
        doc = dict(tool="srs_invariant_audit",
                   steps=[{"command": "audit", "access": "read", "role": "ops_read", "profile": self.read_profile()}],
                   job={"key": JOB_KEY, "inputs": job_inputs if job_inputs is not None else self.scope()})
        doc.update(changes)
        return self.inquiry(**doc)

    def audit_inputs(self, approval=None, **changes):
        approval = approval if approval is not None else self.approval()
        values = dict(command="audit", job_key=JOB_KEY, job_inputs=self.scope(),
                      connection=pf.op.ConnectionObservation(profile=self.read_profile(), read_only=True))
        values.update(changes)
        return self.inputs(approval, **values)

    def run_audit(self, inputs=None, conn=None, *, result=PASS, driver=None):
        calls = []
        conn = conn if conn is not None else AuditConn()
        driver = driver if driver is not None else ta.FakeDriver(conn)
        from app.srs import invariant_audit as ia
        with mock.patch.object(ia, "audit", fake_audit(result, calls)):
            out, code = ar.run_synthetic_audit(inputs or self.audit_inputs(), expected=to.READ_EXPECTED, driver=driver)
        text = json.dumps(out)
        for leak in (SECRET, pf.TARGET.host, "5432", "postgresql://", "sslrootcert"):
            self.assertNotIn(leak, text)
        return out, code, conn, driver, calls

    def refused_before_connect(self, code, inputs, *, preflight_calls=None):
        spy = mock.Mock(wraps=pf.op.run_synthetic_preflight)
        driver = ta.FakeDriver(AuditConn())
        with mock.patch.object(pv.op, "run_synthetic_preflight", spy):
            out, status, _, driver, calls = self.run_audit(inputs, driver=driver)
        self.assertEqual((out["status"], out["reason"], status), ("error", code, 2))
        self.assertEqual((driver.calls, calls), ([], []))
        if preflight_calls is not None:
            self.assertEqual(spy.call_count, preflight_calls)
        return out


class ScopeUnit(Base):
    """check_scope on parsed approvals only (returned values)."""

    def test_valid_scope_returns_the_approval(self):
        approval = ar.check_scope(self.audit_inputs())
        self.assertEqual((approval.tool, approval.kind, dict(approval.job_inputs)["audit_scope"]),
                         ("srs_invariant_audit", "inquiry", "database_all"))

    def test_scope_refusals(self):
        other = pf.db_identity(replace(pf.TARGET, identity_value="restored-copy"))
        cases = [
            ("audit_scope_missing", dict(job_inputs={})),
            ("audit_scope_missing", dict(job_inputs={"audit_scope": "database_all"})),
            ("audit_scope_missing", dict(job_inputs={**self.scope(), "account": 7})),
            ("audit_scope_not_database", dict(job_inputs=self.scope(audit_scope="account"))),
            ("audit_scope_not_database", dict(job_inputs=self.scope(audit_scope=True))),
            ("audit_scope_db_mismatch", dict(job_inputs=self.scope(audit_db_identity=other))),
            ("audit_approval_shape_invalid", dict(accounts=[7, 8], max_accounts=2)),
            ("audit_approval_shape_invalid", dict(max_accounts=2)),
            ("audit_approval_shape_invalid", dict(tool="prb_recover",
                                                  steps=[{"command": "preview", "access": "read", "role": "ops_read",
                                                          "profile": self.read_profile()}])),
            ("audit_approval_shape_invalid", dict(steps=[{"command": "audit", "access": "read", "role": "ops_read",
                                                          "profile": self.read_profile(), "args": {"x": "y"}}])),
        ]
        for code, change in cases:
            with self.subTest(code=code, change=sorted(change)):
                inputs = self.audit_inputs(self.approval(**change),
                                           job_inputs=change.get("job_inputs", self.scope()))
                with self.assertRaises(pv.OpsProviderRefused) as caught:
                    ar.check_scope(inputs)
                self.assertEqual(caught.exception.code, code)

    def test_caller_inputs_are_compared_not_overwritten(self):
        for given in ({}, self.scope(audit_scope="account"), {**self.scope(), "extra": "x"},
                      self.scope(audit_db_identity="0" * 64)):
            with self.subTest(given=sorted(given)):
                with self.assertRaises(pv.OpsProviderRefused) as caught:
                    ar.check_scope(self.audit_inputs(job_inputs=given))
                self.assertEqual(caught.exception.code, "audit_job_inputs_mismatch")
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            ar.check_scope(self.audit_inputs(account_id=8))
        self.assertEqual(caught.exception.code, "audit_approval_shape_invalid")


class Integration(Base):
    """Real pre-check / provider / adapter / observer / read_snapshot; fake driver, connection, audit()."""

    def test_01_normal_flow_order_and_output(self):
        out, code, conn, driver, calls = self.run_audit()
        self.assertEqual(code, 0)
        self.assertEqual(set(out), {"audit_version", "status", "checks", "scope", "target"})
        self.assertEqual(out["scope"], "database_all")
        self.assertEqual(out["target"], {"alias": "synthetic-primary", "db_identity": pf.db_identity(),
                                         "manifest": pf.om.manifest_fingerprint(self.manifest),
                                         "approval_id": "inq-0000000000000001", "tool": "srs_invariant_audit",
                                         "command": "audit"})
        self.assertEqual(out["checks"]["I6"]["status"], "not_evaluated")
        self.assertEqual(len(driver.calls), 1)
        self.assertEqual(conn.log[:4], list(pv.OBSERVATION_START) + ["ROLLBACK"])
        self.assertEqual(conn.trace, ["SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
                                      "SET LOCAL statement_timeout = '15s'", "SET LOCAL lock_timeout = '5s'",
                                      ar.RECHECK, ar.IDENTITY, conn.trace[5], "ROLLBACK"])
        self.assertIn("current_setting('transaction_read_only')", conn.trace[5])
        self.assertTrue(all(f is dict_row for f in conn.row_factory_seen))
        self.assertEqual((conn.commits, conn.close_calls, conn.closed, len(calls)), (0, 1, True, 1))

    def test_02_statuses_and_exit_codes_kept(self):
        for status, code in (("fail", 1), ("unknown", 2), ("partial", 3)):
            with self.subTest(status=status):
                out, exit_code, *_ = self.run_audit(result={**PASS, "status": status})
                self.assertEqual((out["status"], exit_code), (status, code))
                self.assertEqual(out["checks"]["I7"]["status"], "not_evaluated")

    def test_03_refused_before_any_connection(self):
        apply = json.loads(self.approval())
        apply.update(kind="apply")
        self.refused_before_connect("audit_approval_shape_invalid", self.audit_inputs(json.dumps(apply).encode()),
                                    preflight_calls=0)
        write_step = self.approval(steps=[{"command": "audit", "access": "write", "role": "ops_read",
                                           "profile": self.read_profile()}])
        self.refused_before_connect("audit_approval_shape_invalid", self.audit_inputs(write_step), preflight_calls=0)
        self.refused_before_connect("mode_not_synthetic", self.audit_inputs(mode="ops"), preflight_calls=0)
        out, code = ar.run_synthetic_audit(self.audit_inputs(), expected=to.READ_EXPECTED)
        self.assertEqual((out["reason"], code), ("connection_factory_not_implemented", 2))

    def test_04_provider_refusal_skips_the_audit(self):
        conn = AuditConn(to.changed(ownership={**to.catalog()["ownership"], "relations": 1}))
        out, code, conn, driver, calls = self.run_audit(conn=conn)
        self.assertEqual((out["reason"], code, calls, conn.closed, conn.trace), ("observed_ownership", 2, [], True, []))

    def test_05_open_transaction_after_handover(self):
        out, code, conn, _, calls = self.run_audit(conn=AuditConn(opens_on_row_factory=True))
        self.assertEqual((out["reason"], code, calls, conn.closed), ("transaction_already_open", 2, [], True))

    def test_06_sql_trace_has_no_write(self):
        _, _, conn, _, _ = self.run_audit()
        self.assertTrue(all(s == "ROLLBACK" or ALLOWED.match(s) for s in conn.trace))
        self.assertEqual((conn.commits, conn.trace.count("ROLLBACK"), conn.close_calls), (0, 1, 1))

    def test_07_close_failure_is_not_success(self):
        out, code, conn, _, calls = self.run_audit(conn=AuditConn(close_error=OSError(5, SECRET)))
        self.assertEqual((out["status"], out["reason"], code, len(calls)), ("error", "audit_close_failed", 2, 1))
        self.assertNotIn("checks", out)

    def test_08_errors_carry_no_secret(self):
        from psycopg import errors as pg_errors
        conn = AuditConn()
        from app.srs import invariant_audit as ia

        def broken(connection, *, baseline=None):
            raise pg_errors.InsufficientPrivilege(f"{SECRET} SELECT email FROM users")
        with mock.patch.object(ia, "audit", broken):
            out, code = ar.run_synthetic_audit(self.audit_inputs(), expected=to.READ_EXPECTED,
                                               driver=ta.FakeDriver(conn))
        self.assertEqual((out["reason"], code), ("audit_refused_or_unreadable", 2))
        self.assertNotIn(SECRET, json.dumps(out))
        self.assertNotIn("email", json.dumps(out))

    def test_09_app_environment_fixed_and_no_app_connection(self):
        os.environ["DATABASE_URL"] = "postgresql://elsewhere/production"
        os.environ.pop("PYTHON_DOTENV_DISABLED", None)
        _, code, *_ = self.run_audit()
        self.assertEqual(code, 0)
        self.assertEqual((os.environ["APP_ENV"], os.environ["DATABASE_URL"], os.environ["PYTHON_DOTENV_DISABLED"]),
                         ("test", "sqlite:///:memory:", "1"))
        source = (TESTS_DIR.parent / "scripts" / "_ops_audit_run.py").read_text(encoding="utf-8")
        body = source[source.index("def run_synthetic_audit"):]
        self.assertLess(body.index("fix_app_environment()"), body.index("from app."))
        for forbidden in ("get_connection", "init_db", "get_database_url", "load_dotenv", "psycopg.connect"):
            self.assertNotIn(forbidden, re.sub(r'"""[\s\S]*?"""', "", source))

    def test_11_12_account_scoped_or_missing_scope(self):
        for job_inputs, code in (({}, "audit_scope_missing"), (self.scope(audit_scope="account"), "audit_scope_not_database"),
                                 ({"audit_scope": "database_all"}, "audit_scope_missing"),
                                 ({**self.scope(), "account": 7}, "audit_scope_missing")):
            with self.subTest(code=code, keys=sorted(job_inputs)):
                self.refused_before_connect(code, self.audit_inputs(self.approval(job_inputs=job_inputs),
                                                                    job_inputs=job_inputs), preflight_calls=0)

    def test_13_scope_changed_after_signing(self):
        signed = self.approval()
        tampered = json.loads(signed)
        tampered["job"]["inputs"]["audit_scope"] = "database_all"            # same value, different bytes
        tampered["job"]["key"] = JOB_KEY
        tampered_bytes = json.dumps(tampered, indent=1).encode()
        inputs = replace(self.audit_inputs(signed), approval=tampered_bytes)   # old signature kept
        self.assertNotEqual(tampered_bytes, signed)
        self.refused_before_connect("preflight_approval_signature_invalid", inputs, preflight_calls=1)

    def test_14_caller_inputs_mismatch(self):
        self.refused_before_connect("audit_job_inputs_mismatch",
                                    self.audit_inputs(job_inputs=self.scope(audit_db_identity="0" * 64)),
                                    preflight_calls=0)

    def test_15_other_db_scope(self):
        other = pf.db_identity(replace(pf.TARGET, identity_value="restored-copy"))
        approval = self.approval(job_inputs=self.scope(audit_db_identity=other))
        self.refused_before_connect("audit_scope_db_mismatch",
                                    self.audit_inputs(approval, job_inputs=self.scope(audit_db_identity=other)),
                                    preflight_calls=0)

    def test_16_scope_for_another_db_meets_this_db(self):
        target = replace(pf.TARGET, identity_value="restored-copy")
        other = pf.db_identity(target)
        approval = self.approval(db_identity=other, job_inputs=self.scope(audit_db_identity=other))
        out, code, conn, driver, calls = self.run_audit(
            self.audit_inputs(approval, target=target, job_inputs=self.scope(audit_db_identity=other)))
        self.assertEqual((out["reason"], code, calls, conn.closed), ("observed_identity_mismatch", 2, [], True))

    def test_17_job_slot_shape(self):
        self.refused_before_connect("audit_approval_shape_invalid",
                                    self.audit_inputs(self.approval(accounts=[7, 8], max_accounts=2)), preflight_calls=0)
        self.refused_before_connect("audit_approval_shape_invalid", self.audit_inputs(account_id=8), preflight_calls=0)

    def test_19_target_recheck_inside_the_snapshot(self):
        for conn in (AuditConn(recheck={"dbname": "jp_vocab_copy"}), AuditConn(recheck={"port": 5433}),
                     AuditConn(identity=[{"identity_value": "restored-copy"}]),
                     AuditConn(identity=[{"identity_value": pf.TARGET.identity_value}] * 2)):
            with self.subTest():
                out, code, conn, _, calls = self.run_audit(conn=conn)
                self.assertEqual((out["reason"], code, calls, conn.trace[-1], conn.closed),
                                 ("audit_target_recheck_failed", 2, [], "ROLLBACK", True))

    def test_20_unknown_status_from_audit_is_not_passed(self):
        out, code, *_ = self.run_audit(result={"audit_version": 1, "status": "maybe"})
        self.assertEqual((out["status"], out["reason"], code), ("error", "audit_result_invalid", 2))


class ImportOrder(unittest.TestCase):
    """Fresh process with an import watcher (tests/_ops_audit_import_probe.py): app modules are
    imported only after the real pre-check passed, never on a signature / manifest refusal."""

    @classmethod
    def setUpClass(cls):
        import subprocess
        cls.output, cls.cases = "", {}
        for name in ("test_bad_approval_signature", "test_bad_manifest_signature", "test_normal_order"):
            done = subprocess.run([sys.executable, "-m", "unittest", f"_ops_audit_import_probe.Probe.{name}"],
                                  cwd=str(TESTS_DIR), capture_output=True, text=True, timeout=300)   # one process each
            cls.output += done.stdout + done.stderr
            cls.cases.update({c["case"]: c for c in (json.loads(line[6:]) for line in done.stdout.splitlines()
                                                     if line.startswith("PROBE "))})

    def test_refused_signature_or_manifest_imports_no_app(self):
        for name, reason in (("bad_signature", "preflight_approval_signature_invalid"),
                             ("bad_manifest", "preflight_manifest_signature_invalid")):
            with self.subTest(case=name):
                case = self.cases.get(name)
                self.assertIsNotNone(case, self.output[-800:])
                self.assertEqual((case["reason"], case["code"]), (reason, 2))
                self.assertFalse([e for e in case["events"] if e.startswith("import:")])
                self.assertNotIn("connect", case["events"])
        self.assertNotIn(SECRET, self.output)

    def test_normal_path_order(self):
        events = self.cases["normal"]["events"]
        imports = [i for i, e in enumerate(events) if e.startswith("import:")]
        first_pass = events.index("preflight:passed")
        self.assertTrue(imports and first_pass < imports[0] < events.index("connect"), events)
        self.assertTrue(any("transaction_read_only" in s for s in self.cases["normal"]["trace"]))   # audit reached


class Interrupts(Base):
    """Connection cleanup after the handover, including KeyboardInterrupt / SystemExit (fake)."""

    def interrupted(self, error, conn):
        from app.srs import invariant_audit as ia

        def audit(connection, *, baseline=None):
            raise error
        with mock.patch.object(ia, "audit", audit), self.assertRaises(type(error)) as caught:
            ar.run_synthetic_audit(self.audit_inputs(), expected=to.READ_EXPECTED, driver=ta.FakeDriver(conn))
        self.assertNotIn(SECRET, repr(caught.exception))
        return conn

    def test_interrupt_during_audit_rolls_back_and_closes_once(self):
        for error in (KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(error=type(error).__name__):
                conn = self.interrupted(error, AuditConn())
                self.assertEqual((conn.trace[-1], conn.close_calls, conn.closed, conn.commits), ("ROLLBACK", 1, True, 0))

    def test_interrupt_with_close_failure_still_propagates(self):
        conn = self.interrupted(KeyboardInterrupt(), AuditConn(close_error=OSError(5, SECRET)))
        self.assertEqual((conn.close_calls, conn.closed), (1, False))

    def test_preparation_errors_after_the_handover(self):
        class Breaks(AuditConn):
            def __init__(self, error, **kwargs):
                super().__init__(**kwargs)
                self.error = error

            @AuditConn.row_factory.setter
            def row_factory(self, value):
                raise self.error
        conn = Breaks(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):
            ar.run_synthetic_audit(self.audit_inputs(), expected=to.READ_EXPECTED, driver=ta.FakeDriver(conn))
        self.assertEqual((conn.close_calls, conn.closed), (1, True))
        out, code, conn, _, calls = self.run_audit(conn=Breaks(RuntimeError(SECRET)))
        self.assertEqual((out["reason"], code, calls, conn.close_calls), ("audit_refused_or_unreadable", 2, [], 1))
        from app import database
        with mock.patch.object(database, "AppPostgresConnection", side_effect=RuntimeError(SECRET)):
            out, code, conn, _, calls = self.run_audit()
        self.assertEqual((out["reason"], code, conn.close_calls, conn.closed), ("audit_refused_or_unreadable", 2, 1, True))


class InterruptAndRollbackFailure(Base):
    """An interrupt during the audit followed by a failing audit rollback (FAKE failures; the
    provider's observation rollback passes)."""

    def run_interrupted(self, error, conn):
        import traceback
        from app.srs import invariant_audit as ia

        def audit(connection, *, baseline=None):
            raise error
        with mock.patch.object(ia, "audit", audit), self.assertRaises(type(error)) as caught:
            ar.run_synthetic_audit(self.audit_inputs(), expected=to.READ_EXPECTED, driver=ta.FakeDriver(conn))
        raised = caught.exception
        self.assertIs(raised, error)                                     # the original interrupt, not a copy
        shown = "".join(traceback.format_exception(raised))
        self.assertNotIn(SECRET, shown + repr(raised))
        self.assertIsNone(raised.__cause__)
        self.assertTrue(raised.__context__ is None or raised.__suppress_context__)
        self.assertEqual((conn.trace[-1], conn.close_calls), ("ROLLBACK", 1))
        return raised

    def test_keyboard_interrupt_with_rollback_failure(self):
        from psycopg import errors as pg_errors
        conn = AuditConn(snapshot_rollback_error=pg_errors.OperationalError(SECRET))
        self.run_interrupted(KeyboardInterrupt(), conn)
        self.assertTrue(conn.closed)

    def test_system_exit_keeps_its_code(self):
        from psycopg import errors as pg_errors
        raised = self.run_interrupted(SystemExit(9), AuditConn(snapshot_rollback_error=pg_errors.OperationalError(SECRET)))
        self.assertEqual(raised.code, 9)

    def test_interrupt_rollback_and_close_failures(self):
        from psycopg import errors as pg_errors
        for error in (KeyboardInterrupt(), SystemExit(9)):
            with self.subTest(error=type(error).__name__):
                conn = AuditConn(snapshot_rollback_error=pg_errors.OperationalError(SECRET),
                                 close_error=OSError(5, SECRET))
                self.run_interrupted(error, conn)
                self.assertFalse(conn.closed)

    def test_rollback_failure_without_interrupt_keeps_the_fixed_code(self):
        from psycopg import errors as pg_errors
        out, code, conn, _, calls = self.run_audit(
            conn=AuditConn(snapshot_rollback_error=pg_errors.OperationalError(SECRET)))
        self.assertEqual((out["status"], out["reason"], code, conn.close_calls, len(calls)),
                         ("error", "audit_refused_or_unreadable", 2, 1, 1))
        out, code, conn, _, _ = self.run_audit(
            conn=AuditConn(snapshot_rollback_error=pg_errors.OperationalError(SECRET), close_error=OSError(5, SECRET)))
        self.assertEqual((out["reason"], code), ("audit_close_failed", 2))


if __name__ == "__main__":
    unittest.main()
