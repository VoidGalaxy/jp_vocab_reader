"""Connection provider unit 6-1a (scripts/_ops_provider.py): lifecycle and observation
judgement with FAKE connections and FAKE observers.

The pre-check underneath is the real unit 5 flow (real test-key signatures, synthetic files).
Everything after it uses fakes: the fake connection imitates only the transaction-status
bookkeeping this unit relies on and does not prove real PostgreSQL transaction semantics. No
database, no real connection (psycopg / libpq connect entry points stay patched to fail).

Run directly:      python tests/test_ops_provider.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
import psycopg.conninfo  # noqa: E402
from psycopg import errors as pg_errors  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only: its tests are not re-run here)

SECRET = pf.SECRET
OBJECTS = frozenset({("database", "", "jp_vocab"), ("schema", "", "public"), ("table", "public", "vocab_items"),
                     ("table", "public", "users")})
READ_PRIVS = frozenset({("database", "", "jp_vocab", "", "CONNECT"), ("schema", "", "public", "", "USAGE"),
                        ("table", "public", "vocab_items", "", "SELECT"), ("table", "public", "users", "", "SELECT")})
WRITE_PRIVS = READ_PRIVS | {("table", "public", "vocab_items", "", "UPDATE")}
READ_EXPECTED = pv.ExpectedProfile(OBJECTS, READ_PRIVS, "public, pg_catalog", frozenset({"TLSv1.3"}))
WRITE_EXPECTED = pv.ExpectedProfile(OBJECTS, WRITE_PRIVS, "public, pg_catalog", frozenset({"TLSv1.3"}))
BUSINESS_FIRST = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"


class FakeInfo:
    def __init__(self, conn):
        self._conn = conn

    @property
    def transaction_status(self):
        return self._conn.status


class FakeConn:
    """FAKE: transaction-status bookkeeping only."""

    def __init__(self, *, rollback_error=None, close_error=None, status_after_rollback=TransactionStatus.IDLE,
                 broken_after=False, read_only=None, isolation_level=None, execute_error=None):
        self.log: list[str] = []
        self.status = TransactionStatus.IDLE
        self.statements_in_txn = 0
        self.closed = False
        self.broken = False
        self.read_only = read_only
        self.isolation_level = isolation_level
        self.close_calls = 0
        self.rollback_error, self.close_error, self.execute_error = rollback_error, close_error, execute_error
        self.status_after_rollback, self.broken_after = status_after_rollback, broken_after
        self.info = FakeInfo(self)

    def execute(self, sql):
        if self.closed:
            raise pg_errors.OperationalError("closed")
        if sql.startswith("SET TRANSACTION") and self.statements_in_txn:
            raise pg_errors.ActiveSqlTransaction("SET TRANSACTION must be first")
        self.log.append(sql)
        if self.execute_error is not None:
            raise self.execute_error
        self.status = TransactionStatus.INTRANS
        self.statements_in_txn += 1

    def rollback(self):
        self.log.append("ROLLBACK")
        if self.rollback_error is not None:
            raise self.rollback_error
        self.status, self.statements_in_txn = self.status_after_rollback, 0
        self.broken = self.broken_after

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class FakeFactory:
    def __init__(self, *connections, error=None):
        self.connections = list(connections)
        self.error = error
        self.requests = []

    def open(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.connections.pop(0)


class FakeObserver:
    def __init__(self, observation=None, error=None):
        self.observation, self.error = observation, error
        self.calls = 0
        self.seen_log = None

    def observe(self, connection):
        self.calls += 1
        self.seen_log = list(connection.log)
        if self.error is not None:
            raise self.error
        return self.observation


def observation(access="read", **changes) -> pv.Observation:
    values = dict(host=pf.TARGET.host, port=pf.TARGET.port, dbname=pf.TARGET.database,
                  server_major=pf.TARGET.server_major, identity_value=pf.TARGET.identity_value,
                  current_user="ops_read" if access == "read" else "ops_write_prb",
                  session_user="ops_read" if access == "read" else "ops_write_prb",
                  role_attributes=tuple((k, k == "inherit") for k in pv.ROLE_ATTRIBUTES), memberships=(),
                  owned_count=0, objects=tuple(sorted(OBJECTS)),
                  privileges=tuple(sorted(READ_PRIVS if access == "read" else WRITE_PRIVS)),
                  search_path="public, pg_catalog", observation_read_only=True,
                  default_read_only=access == "read", default_isolation="read committed", tls_in_use=True,
                  tls_server_ssl=True, tls_version="TLSv1.3")
    values.update(changes)
    return pv.Observation(**values)


class Base(pf.Base):
    def read_profile(self):
        return pv.expected_profile_fingerprint(READ_EXPECTED, role="ops_read", access="read")

    def write_profile(self):
        return pv.expected_profile_fingerprint(WRITE_EXPECTED, role="ops_write_prb", access="write")

    def read_inputs(self, **changes):
        approval = self.inquiry(steps=[{"command": "preview", "access": "read", "role": "ops_read",
                                         "profile": self.read_profile()}])
        values = dict(connection=op.ConnectionObservation(profile=self.read_profile(), read_only=True))
        values.update(changes)
        return self.inputs(approval, **values)

    def write_inputs(self, **changes):
        inquiry = self.inquiry(steps=[{"command": "preview", "access": "read", "role": "ops_read",
                                        "profile": self.read_profile()}])
        plan = op.run_synthetic_preflight(self.inputs(inquiry, connection=op.ConnectionObservation(
            profile=self.read_profile(), read_only=True))).job_plan
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001", based_on={
            "approval_id": doc["approval_id"], "sha256": pf.hashlib.sha256(inquiry).hexdigest()},
            steps=[{"command": "prepare", "access": "write", "role": "ops_write_prb", "profile": self.write_profile()}],
            plan={"7": plan})
        apply = json.dumps(doc).encode()
        values = dict(inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"), command="prepare",
                      secret_dsn=self.dsn(role="ops_write_prb"),
                      connection=op.ConnectionObservation(profile=self.write_profile(), read_only=False))
        values.update(changes)
        return self.inputs(apply, **values)

    def provide(self, inputs, conn=None, obs=None, *, expected=READ_EXPECTED, factory=None, observer=None):
        conn = conn if conn is not None else FakeConn()
        factory = factory or FakeFactory(conn)
        observer = observer or FakeObserver(obs if obs is not None else observation())
        return pv.provide_synthetic_connection(inputs, expected=expected, factory=factory, observer=observer)

    def refused(self, code, inputs, conn=None, obs=None, *, expected=READ_EXPECTED, also=None, **kwargs):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.provide(inputs, conn, obs, expected=expected, **kwargs)
        error = caught.exception
        self.assertEqual(error.code, code)
        if also is not None:
            self.assertEqual(error.also, also)
        self.assertNotIn(SECRET, repr(error) + str(error) + repr(error.also))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Flow(Base):
    """FAKE connection / observer after the real unit 5 pre-check."""

    def test_precheck_refusal_opens_nothing(self):
        factory = FakeFactory(FakeConn())
        inputs = self.read_inputs(approval_signature=b"bad")
        self.refused("preflight_approval_signature_invalid", inputs, factory=factory)
        self.assertEqual(factory.requests, [])

    def test_read_flow_order_and_handover(self):
        conn, observer = FakeConn(), FakeObserver(observation())
        factory = FakeFactory(conn)
        handoff = pv.provide_synthetic_connection(self.read_inputs(), expected=READ_EXPECTED, factory=factory,
                                                  observer=observer)
        self.assertEqual(observer.seen_log, list(pv.OBSERVATION_START))
        self.assertEqual(conn.log, list(pv.OBSERVATION_START) + ["ROLLBACK"])        # no SQL after rollback
        self.assertEqual(conn.status, TransactionStatus.IDLE)
        fixed = dict(factory.requests[0].fixed)
        self.assertEqual((fixed["application_name"], fixed["connect_timeout"]), ("jp_vocab_ops_synthetic", "10"))
        self.assertIn("default_transaction_read_only=on", fixed["options"])
        # review fix: the old expectation used shell-style quotes, which the server would split into
        # two arguments; the value now uses the documented backslash escape (see ReviewFixes)
        self.assertIn("-c default_transaction_isolation=read\\ committed", fixed["options"])
        self.assertNotIn(SECRET, repr(factory.requests[0]) + repr(handoff) + repr(handoff.summary))
        taken = handoff.take()
        self.assertIs(taken, conn)
        taken.execute(BUSINESS_FIRST)                          # business may set its first transaction
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            handoff.take()
        self.assertEqual(caught.exception.code, "handoff_already_taken")
        self.assertEqual(conn.close_calls, 0)

    def test_write_flow_not_refused_by_read_only_observation(self):
        conn = FakeConn()
        factory = FakeFactory(conn)
        handoff = pv.provide_synthetic_connection(self.write_inputs(), expected=WRITE_EXPECTED, factory=factory,
                                                  observer=FakeObserver(observation("write")))
        self.assertEqual(conn.log[0], "SET TRANSACTION READ ONLY")
        self.assertIn("default_transaction_read_only=off", dict(factory.requests[0].fixed)["options"])
        self.assertEqual((handoff.summary.access, handoff.summary.role), ("write", "ops_write_prb"))
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_observation_and_business_settings_are_separate(self):
        self.refused("observed_business_defaults_mismatch", self.write_inputs(), FakeConn(),
                     observation("write", default_read_only=True), expected=WRITE_EXPECTED)
        self.refused("observation_not_read_only", self.read_inputs(), FakeConn(),
                     observation(observation_read_only=False))
        self.refused("observed_business_defaults_mismatch", self.read_inputs(), FakeConn(),
                     observation(default_isolation="repeatable read"))
        self.refused("observed_business_defaults_mismatch", self.read_inputs(), FakeConn(),
                     observation(default_read_only=False))

    def test_objects_and_privileges(self):
        extra_table = tuple(sorted(OBJECTS | {("table", "public", "new_table")}))
        cases = [
            ("observed_objects_mismatch", dict(objects=extra_table)),  # new object, no privileges at all
            ("observed_privileges_excess", dict(privileges=tuple(sorted(READ_PRIVS | {("table", "public", "users", "", "UPDATE")})))),
            ("observed_privileges_excess", dict(privileges=tuple(sorted(READ_PRIVS | {("table", "public", "users", "email", "UPDATE")})))),
            ("observed_privileges_excess", dict(privileges=tuple(sorted(READ_PRIVS | {("database", "", "jp_vocab", "", "TEMPORARY")})))),
            ("observed_privileges_missing", dict(privileges=tuple(sorted(READ_PRIVS - {("table", "public", "users", "", "SELECT")})))),
            ("privilege_scope_unknown", dict(unresolved=("acl_unparsed",))),
            ("privilege_scope_unknown", dict(objects=tuple(sorted(OBJECTS | {("type", "public", "mood")})))),
            ("privilege_scope_unknown", dict(privileges=tuple(sorted(READ_PRIVS | {("table", "public", "ghost", "", "SELECT")})))),
            ("observed_memberships", dict(memberships=("pg_write_all_data",))),
            ("observed_ownership", dict(owned_count=1)),
            ("observed_role_attributes", dict(role_attributes=tuple((k, k in ("inherit", "bypassrls")) for k in pv.ROLE_ATTRIBUTES))),
            ("observed_search_path_mismatch", dict(search_path="evil, public")),
        ]
        for code, change in cases:
            with self.subTest(code=code, change=sorted(change)):
                conn = FakeConn()
                self.refused(code, self.read_inputs(), conn, observation(**change))
                self.assertTrue(conn.closed)

    def test_target_role_and_tls(self):
        cases = [("observed_target_mismatch", dict(host="db2.synthetic.test")),
                 ("observed_target_mismatch", dict(dbname="jp_vocab_copy")),
                 ("observed_identity_mismatch", dict(identity_value="restored-copy")),
                 ("observed_identity_mismatch", dict(server_major=17)),
                 ("observed_role_mismatch", dict(current_user="ops_write_prb")),
                 ("observed_role_mismatch", dict(session_user="postgres")),
                 ("observed_tls_not_in_use", dict(tls_in_use=False)),
                 ("observed_tls_not_in_use", dict(tls_server_ssl=False)),
                 ("observed_tls_not_in_use", dict(tls_version="TLSv1.2"))]
        for code, change in cases:
            with self.subTest(code=code):
                self.refused(code, self.read_inputs(), FakeConn(), observation(**change))

    def test_observation_types_are_strict(self):
        for change in (dict(port="5432"), dict(port=True), dict(server_major=18.0), dict(default_read_only=1),
                       dict(role_attributes=tuple((k, False) for k in reversed(pv.ROLE_ATTRIBUTES))),
                       dict(host=""), dict(objects=[("table", "public", "users")]), dict(unresolved=("x", 1))):
            with self.subTest(change=sorted(change)):
                self.refused("observation_invalid", self.read_inputs(), FakeConn(), observation(**change))
        self.refused("observation_invalid", self.read_inputs(), FakeConn(), observer=FakeObserver({"host": "x"}),
                     factory=None)


class Failures(Base):
    """FAKE failure injection: these are scripted, not real driver or OS failures."""

    def test_rollback_and_state_failures(self):
        for conn in (FakeConn(rollback_error=pg_errors.OperationalError(SECRET)),
                     FakeConn(status_after_rollback=TransactionStatus.INTRANS),
                     FakeConn(status_after_rollback=TransactionStatus.INERROR),
                     FakeConn(broken_after=True), FakeConn(read_only=True),
                     FakeConn(isolation_level=psycopg.IsolationLevel.SERIALIZABLE)):
            with self.subTest(case=conn.status_after_rollback.name):
                self.refused("observation_rollback_failed", self.read_inputs(), conn, observation())
                self.assertEqual((conn.closed, conn.close_calls), (True, 1))

    def test_error_priority(self):
        conn = FakeConn(close_error=OSError(5, SECRET))
        self.refused("connection_close_unconfirmed", self.read_inputs(), conn, observation(host="db2.synthetic.test"),
                     also=("observed_target_mismatch",))
        self.assertEqual((conn.closed, conn.close_calls), (False, 1))     # never treated as cleaned up, no retry
        conn = FakeConn(rollback_error=pg_errors.OperationalError(SECRET), close_error=OSError(5, SECRET))
        self.refused("connection_close_unconfirmed", self.read_inputs(), conn, observation(owned_count=1),
                     also=("observation_rollback_failed", "observed_ownership"))
        conn = FakeConn(rollback_error=pg_errors.OperationalError(SECRET))
        self.refused("observation_rollback_failed", self.read_inputs(), conn, observation(owned_count=1),
                     also=("observed_ownership",))

    def test_connect_and_observation_driver_errors(self):
        factory = FakeFactory(error=pg_errors.OperationalError(SECRET))
        self.refused("connect_failed", self.read_inputs(), factory=factory)
        factory = FakeFactory(error=pg_errors.ConnectionTimeout(SECRET))
        self.refused("connect_timeout", self.read_inputs(), factory=factory)
        factory = FakeFactory(error=OSError(10060, SECRET))
        self.refused("connect_failed", self.read_inputs(), factory=factory)
        for error, code in ((pg_errors.QueryCanceled(SECRET), "observation_timeout"),
                            (pg_errors.LockNotAvailable(SECRET), "observation_lock_timeout"),
                            (pg_errors.InsufficientPrivilege(SECRET), "observation_failed")):
            with self.subTest(code=code):
                conn = FakeConn()
                self.refused(code, self.read_inputs(), conn, observer=FakeObserver(error=error))
                self.assertTrue(conn.closed)
        conn = FakeConn(execute_error=pg_errors.QueryCanceled(SECRET))
        self.refused("observation_timeout", self.read_inputs(), conn, observation())
        self.assertTrue(conn.closed)

    def test_unexpected_error_still_closes(self):
        conn = FakeConn()
        with self.assertRaises(RuntimeError):
            pv.provide_synthetic_connection(self.read_inputs(), expected=READ_EXPECTED, factory=FakeFactory(conn),
                                            observer=FakeObserver(error=RuntimeError("bug")))
        self.assertTrue(conn.closed)

    def test_reconnect_rechecks_everything(self):
        spy = mock.Mock(wraps=op.run_synthetic_preflight)
        first, second = FakeConn(), FakeConn()
        factory = FakeFactory(first, second)
        with mock.patch.object(pv.op, "run_synthetic_preflight", spy):
            pv.provide_synthetic_connection(self.read_inputs(), expected=READ_EXPECTED, factory=factory,
                                            observer=FakeObserver(observation()))
            with self.assertRaises(pv.OpsProviderRefused) as caught:
                pv.provide_synthetic_connection(self.read_inputs(), expected=READ_EXPECTED, factory=factory,
                                                observer=FakeObserver(observation(owned_count=1)))
        self.assertEqual(caught.exception.code, "observed_ownership")
        self.assertEqual((spy.call_count, len(factory.requests)), (2, 2))
        self.assertTrue(second.closed)
        self.assertFalse(first.closed)


class Boundaries(Base):
    def test_production_and_unimplemented_defaults(self):
        factory = FakeFactory(FakeConn())
        self.refused("mode_not_synthetic", self.read_inputs(mode="ops"), factory=factory)
        self.assertEqual(factory.requests, [])
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_connection(self.read_inputs(), expected=READ_EXPECTED)
        self.assertEqual(caught.exception.code, "connection_factory_not_implemented")
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_synthetic_connection(self.read_inputs(), expected=READ_EXPECTED, factory=FakeFactory(FakeConn()))
        self.assertEqual(caught.exception.code, "observer_not_implemented")

    def test_expected_profile_must_be_the_approved_one(self):
        factory = FakeFactory(FakeConn())
        other = replace(READ_EXPECTED, privileges=READ_PRIVS | {("table", "public", "users", "", "UPDATE")})
        self.refused("expected_profile_not_approved", self.read_inputs(), expected=other, factory=factory)
        self.assertEqual(factory.requests, [])

    def test_module_never_connects_by_itself(self):
        source = (TESTS_DIR.parent / "scripts" / "_ops_provider.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"psycopg\.connect|\.connect\(|Connection\.connect", source))
        for forbidden in ("import_module", "__import__", "exec(", "eval(", "os.environ", "getenv", "subprocess",
                          "from app", "import app"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


def split_server_options(value: str) -> list[str]:
    """The server's split rule for the libpq `options` value (PostgreSQL 18 docs, libpq-connect
    `options`: spaces in a value are escaped with a backslash, `\\` is a literal backslash).
    Written here from the documented rule; it is not the server's own code."""
    args, current, escaped, started = [], [], False, False
    for ch in value:
        if escaped:
            current.append(ch)
            escaped, started = False, True
        elif ch == "\\":
            escaped, started = True, True
        elif ch.isspace():
            if started:
                args.append("".join(current))
                current, started = [], False
        else:
            current.append(ch)
            started = True
    if started:
        args.append("".join(current))
    return args


class ReviewFixes(Base):
    """Review fixes: TLS allow-list bound to the approval, nested observation shapes, options
    encoding. Pre-check is real (test-key signatures); connections and observers are FAKE."""

    def test_tls_allow_list_is_part_of_the_approved_profile(self):
        # the approval stays signed for TLSv1.3 only; the caller widens its expected list
        widened = replace(READ_EXPECTED, tls_versions=frozenset({"TLSv1.3", "TLSv1.2"}))
        factory = FakeFactory(FakeConn())
        self.refused("expected_profile_not_approved", self.read_inputs(), FakeConn(),
                     observation(tls_version="TLSv1.2"), expected=widened, factory=factory)
        self.assertEqual(factory.requests, [])

    def test_tls_allow_list_normalisation(self):
        a = replace(READ_EXPECTED, tls_versions=frozenset({"TLSv1.2", "TLSv1.3"}))
        b = replace(READ_EXPECTED, tls_versions=("TLSv1.3", "TLSv1.2"))
        c = replace(READ_EXPECTED, tls_versions=frozenset({"TLSv1.3"}))
        fp = lambda e: pv.expected_profile_fingerprint(e, role="ops_read", access="read")  # noqa: E731
        self.assertEqual(fp(a), fp(b))
        self.assertNotEqual(fp(a), fp(c))
        for bad in (frozenset(), (), ("TLSv1.3", "TLSv1.3"), ("TLSv1.3", ""), ("TLSv1.3", 1), ("TLSv1.3", None),
                    ("TLSv1.3", True), "TLSv1.3", ["TLSv1.3"], ("tls 1.3",), ("TLSv1.3", ("TLSv1.2",))):
            with self.subTest(bad=repr(bad)[:30]):
                with self.assertRaises(pv.OpsProviderRefused) as caught:
                    fp(replace(READ_EXPECTED, tls_versions=bad))
                self.assertEqual(caught.exception.code, "expected_profile_invalid")
        # a newly signed approval for the widened list works, and the observed version must be in it
        approval = self.inquiry(steps=[{"command": "preview", "access": "read", "role": "ops_read", "profile": fp(a)}])
        inputs = self.inputs(approval, connection=op.ConnectionObservation(profile=fp(a), read_only=True))
        self.assertEqual(self.provide(inputs, FakeConn(), observation(tls_version="TLSv1.2"), expected=a).profile
                         != "", True)
        self.refused("observed_tls_not_in_use", inputs, FakeConn(), observation(tls_version="TLSv1.1"), expected=a)

    def test_nested_observation_shapes(self):
        attrs = tuple((k, k == "inherit") for k in pv.ROLE_ATTRIBUTES)
        cases = [
            dict(role_attributes=attrs[:-1] + (("inherit",),)),
            dict(role_attributes=attrs[:-1] + (("inherit", True, 1),)),
            dict(role_attributes=attrs[:-1] + (["inherit", True],)),
            dict(role_attributes=attrs[:-1] + (None,)),
            dict(role_attributes=attrs[:-1] + ("inherit",)),
            dict(objects=(("table", "public"),) + tuple(sorted(OBJECTS))),
            dict(objects=(("table", "public", "users", "x"),)),
            dict(objects=(None,)), dict(objects=("table",)), dict(objects=(["table", "public", "users"],)),
            dict(objects=(("table", ["public"], "users"),)), dict(objects=(("table", {"s": 1}, "users"),)),
            dict(objects=(("table", "public", True),)), dict(objects=(("table", "public", 7),)),
            dict(privileges=(("table", "public", "users", "SELECT"),)),
            dict(privileges=(("table", "public", "users", "", "SELECT", "x"),)),
            dict(privileges=(("table", "public", "users", ["c"], "SELECT"),)),
            dict(privileges=(("table", "public", "users", "", None),)),
            dict(privileges=(("table", "public", "users", "", {"p": 1}),)),
            dict(memberships=(["x"],)), dict(memberships=(None,)), dict(unresolved=(["x"],)),
        ]
        for change in cases:
            with self.subTest(change=repr(change)[:60]):
                conn = FakeConn()
                self.refused("observation_invalid", self.read_inputs(), conn, observation(**change))
                self.assertEqual((conn.closed, conn.close_calls), (True, 1))
                self.assertIn("ROLLBACK", conn.log)

    def test_options_value_keeps_the_isolation_setting_as_one_argument(self):
        for access, read_only in (("read", "on"), ("write", "off")):
            with self.subTest(access=access):
                options = dict(pv.fixed_parameters(access))["options"]
                self.assertEqual(split_server_options(options), [
                    "-c", f"default_transaction_read_only={read_only}",
                    "-c", "default_transaction_isolation=read committed",
                    "-c", "idle_in_transaction_session_timeout=60s"])
                # driver conninfo parsing only: the value survives libpq's own conninfo parse unchanged
                parsed = psycopg.conninfo.conninfo_to_dict(psycopg.conninfo.make_conninfo("", options=options))
                self.assertEqual(parsed["options"], options)
        self.assertEqual(split_server_options(r"-c a=b\ c\\d"), ["-c", "a=b c\\d"])



ARTIFACT = pf.hashlib.sha256(b"plan file").hexdigest()


class ArtifactAfterConnect(Base):
    """Contract 3-3-1: the same value reaches the re-judgement after connect (fake connection)."""

    def artifact_write_inputs(self, given=ARTIFACT, bound=ARTIFACT):
        inquiry = self.inquiry(steps=[{"command": "preview", "access": "read", "role": "ops_read",
                                        "profile": self.read_profile()}])
        plan = op.run_synthetic_preflight(self.inputs(inquiry, artifact_sha256=bound, connection=op.ConnectionObservation(
            profile=self.read_profile(), read_only=True))).job_plan
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001", based_on={
            "approval_id": doc["approval_id"], "sha256": pf.hashlib.sha256(inquiry).hexdigest()},
            steps=[{"command": "prepare", "access": "write", "role": "ops_write_prb", "profile": self.write_profile()}],
            plan={"7": plan})
        apply = json.dumps(doc).encode()
        return self.inputs(apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"),
                           command="prepare", secret_dsn=self.dsn(role="ops_write_prb"), artifact_sha256=given,
                           connection=op.ConnectionObservation(profile=self.write_profile(), read_only=False)), plan

    def test_value_reaches_both_judgements(self):
        inputs, plan = self.artifact_write_inputs()
        seen = []
        real = op.oa.authorize_command

        def spy(*args, **kwargs):
            seen.append(kwargs.get("artifact_sha256", "<missing>"))
            return real(*args, **kwargs)
        with mock.patch.object(op.oa, "authorize_command", spy):
            handoff = self.provide(inputs, obs=observation("write"), expected=WRITE_EXPECTED)
        self.assertEqual(seen, [ARTIFACT, ARTIFACT])                  # pre-check, then after connect
        self.assertEqual(handoff.summary.job_plan, plan)
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_wrong_or_missing_value_is_refused_before_connect(self):
        for given in (None, pf.hashlib.sha256(b"other").hexdigest()):
            with self.subTest(given=given):
                factory = FakeFactory(FakeConn())
                inputs, _ = self.artifact_write_inputs(given=given)
                self.refused("preflight_job_plan_mismatch", inputs, obs=observation("write"), expected=WRITE_EXPECTED,
                             factory=factory)
                self.assertEqual(factory.requests, [])

    def test_lost_or_changed_after_connect_closes_and_hands_nothing(self):
        for change in ("drop", "other"):
            with self.subTest(change=change):
                inputs, _ = self.artifact_write_inputs()
                conn = FakeConn()
                calls = []
                real = op.oa.authorize_command

                def tamper(*args, **kwargs):
                    calls.append(1)
                    if len(calls) == 2:                               # the provider's re-judgement only
                        if change == "drop":
                            kwargs.pop("artifact_sha256", None)
                        else:
                            kwargs["artifact_sha256"] = pf.hashlib.sha256(b"other").hexdigest()
                    return real(*args, **kwargs)
                with mock.patch.object(op.oa, "authorize_command", tamper):
                    self.refused("observed_job_plan_mismatch", inputs, conn, observation("write"),
                                 expected=WRITE_EXPECTED)
                self.assertEqual(len(calls), 2)
                self.assertEqual(conn.close_calls, 1)
                self.assertEqual(conn.log[-1], "ROLLBACK")

    def test_reconnect_judges_again(self):
        inputs, _ = self.artifact_write_inputs()
        for _ in range(2):
            self.provide(inputs, obs=observation("write"), expected=WRITE_EXPECTED).take()
        later = replace(inputs, now=inputs.now.replace(hour=inputs.now.hour + 2))   # past valid_until
        factory = FakeFactory(FakeConn())
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.provide(inputs=later, obs=observation("write"), expected=WRITE_EXPECTED, factory=factory)
        self.assertTrue(caught.exception.code.startswith("preflight_"))
        self.assertEqual(factory.requests, [])


class LinkedApprovalStillRefused(Base):
    """Contract 4-6-5: no prior approval reaches the provider yet, so a linked approval opens nothing."""

    def test_version_2_link_is_refused_before_connect(self):
        prior = self.inquiry()
        approval = self.inquiry(approval_id="inq-0000000000000002", format_version=2, supersedes={
            "approval_id": "inq-0000000000000001", "sha256": pf.hashlib.sha256(prior).hexdigest()},
            steps=[{"command": "preview", "access": "read", "role": "ops_read", "profile": self.read_profile()}])
        factory = FakeFactory(FakeConn())
        inputs = self.inputs(approval, connection=op.ConnectionObservation(profile=self.read_profile(), read_only=True))
        self.refused("preflight_approval_supersedes_unknown", inputs, factory=factory)
        self.assertEqual(factory.requests, [])


PAST = {"valid_from": "2026-10-21T08:00:00Z", "valid_until": "2026-10-21T09:00:00Z"}


class ApplyChainAfterConnect(Base):
    """Contract 4-6-6: verified prior and artifact reach the re-judgement (fake connection)."""

    def chain_inputs(self, artifact=ARTIFACT):
        inquiry = self.inquiry(steps=[{"command": "preview", "access": "read", "role": "ops_read",
                                        "profile": self.read_profile()}])
        plan = op.run_synthetic_preflight(self.inputs(inquiry, artifact_sha256=artifact, connection=op.ConnectionObservation(
            profile=self.read_profile(), read_only=True))).job_plan
        base = json.loads(inquiry)

        def apply(approval_id, version, supersedes, **changes):
            doc = dict(base, kind="apply", approval_id=approval_id, format_version=version, supersedes=supersedes,
                       based_on={"approval_id": base["approval_id"], "sha256": pf.hashlib.sha256(inquiry).hexdigest()},
                       steps=[{"command": "prepare", "access": "write", "role": "ops_write_prb",
                               "profile": self.write_profile()}], plan={"7": plan})
            doc.update(changes)
            return json.dumps(doc).encode()
        first = apply("app-0000000000000001", 1, None, **PAST)
        current = apply("app-0000000000000002", 2, {"approval_id": "app-0000000000000001",
                                                    "sha256": pf.hashlib.sha256(first).hexdigest()})
        link = op.ChainLink(first, self.sign(first, "approval"), inquiry, self.sign(inquiry, "approval"))
        return self.inputs(current, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"),
                           command="prepare", secret_dsn=self.dsn(role="ops_write_prb"), artifact_sha256=artifact,
                           prior_chain=(link,),
                           connection=op.ConnectionObservation(profile=self.write_profile(), read_only=False)), plan

    def provide_write(self, inputs, conn=None, **kwargs):
        return self.provide(inputs, conn, observation("write"), expected=WRITE_EXPECTED, **kwargs)

    def test_prior_and_artifact_reach_both_judgements(self):
        inputs, plan = self.chain_inputs()
        seen = []
        real = op.oa.authorize_command

        def spy(*args, **kwargs):
            prior = kwargs.get("prior")
            seen.append((getattr(prior, "approval_id", None), getattr(prior, "verified", None),
                         kwargs.get("artifact_sha256")))
            return real(*args, **kwargs)
        with mock.patch.object(op.oa, "authorize_command", spy):
            handoff = self.provide_write(inputs)
        self.assertEqual(seen, [("app-0000000000000001", True, ARTIFACT)] * 2)
        self.assertEqual(handoff.summary.job_plan, plan)
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_precheck_refusal_opens_nothing(self):
        inputs, _ = self.chain_inputs()
        broken = replace(inputs, prior_chain=(replace(inputs.prior_chain[0], approval_signature=b"bad"),))
        factory = FakeFactory(FakeConn())
        self.refused("preflight_approval_signature_invalid", broken, obs=observation("write"), expected=WRITE_EXPECTED,
                     factory=factory)
        self.assertEqual(factory.requests, [])

    def test_lost_or_changed_after_connect_closes_and_hands_nothing(self):
        other = pf.hashlib.sha256(b"other").hexdigest()
        for label, change, code in (("prior dropped", lambda kw: kw.pop("prior", None),
                                     "observed_approval_supersedes_unknown"),
                                    ("artifact changed", lambda kw: kw.update(artifact_sha256=other),
                                     "observed_job_plan_mismatch")):
            with self.subTest(case=label):
                inputs, _ = self.chain_inputs()
                conn, calls = FakeConn(), []
                real = op.oa.authorize_command

                def tamper(*args, **kwargs):
                    calls.append(1)
                    if len(calls) == 2:
                        change(kwargs)
                    return real(*args, **kwargs)
                with mock.patch.object(op.oa, "authorize_command", tamper):
                    self.refused(code, inputs, conn, observation("write"), expected=WRITE_EXPECTED)
                self.assertEqual((len(calls), conn.close_calls, conn.log[-1]), (2, 1, "ROLLBACK"))

    def test_precheck_result_must_match_the_same_input_bytes(self):
        inputs, _ = self.chain_inputs()
        real = op.run_synthetic_preflight
        other, _ = self.write_inputs(), None
        for label, forged in (("no verified part", lambda r: replace(r, verified=None)),
                              ("other approvals", lambda r: replace(r, verified=real(other).verified))):
            with self.subTest(case=label):
                factory = FakeFactory(FakeConn())
                with mock.patch.object(pv.op, "run_synthetic_preflight", lambda i, f=forged: f(real(i))):
                    self.refused("preflight_result_mismatch", inputs, obs=observation("write"),
                                 expected=WRITE_EXPECTED, factory=factory)
                self.assertEqual(factory.requests, [])

    def test_reconnect_verifies_the_chain_again(self):
        inputs, _ = self.chain_inputs()
        spy = mock.Mock(wraps=op.run_synthetic_preflight)
        verify = mock.Mock(wraps=op.oa.verify_signed)
        with mock.patch.object(pv.op, "run_synthetic_preflight", spy), mock.patch.object(op.oa, "verify_signed", verify):
            for _ in range(2):
                self.provide_write(inputs).take()
        self.assertEqual(spy.call_count, 2)
        self.assertEqual(verify.call_count, 2 * 4)        # current, basis, prior, prior's basis, per connection

if __name__ == "__main__":
    unittest.main()
