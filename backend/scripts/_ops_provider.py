"""Operations tool safety contract, connection provider unit 6-1a: connection lifecycle and the
judgement of post-connect observations (OPS_CONNECTION_PROVIDER_CONTRACT.md 1-3·9절).

Synthetic scope. Opening a connection (`ConnectionFactory`) and reading the server
(`Observer`) are interfaces with no real implementation yet: the default entry point refuses
before connecting. Tests inject fakes; fake observations are not server values and give no
production permission. Production mode is refused.

Order: synthetic pre-check (unit 5) -> open -> observation transaction (READ ONLY, local
timeouts) -> observe -> compare with the approval and the expected profile -> rollback ->
IDLE / healthy / driver settings unset -> hand over. Any failure closes the connection once and
never returns it. A reconnect is a new call: everything is checked again.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import psycopg
from psycopg import errors as pg_errors
from psycopg.pq import TransactionStatus

import _ops_approval as oa
import _ops_preflight as op

# Synthetic test settings fixed by the user for this unit (contract 9절): not production policy.
CONNECT_TIMEOUT = 10
OBSERVE_STATEMENT_TIMEOUT = "5s"
OBSERVE_LOCK_TIMEOUT = "2s"
IDLE_IN_TRANSACTION_TIMEOUT = "60s"
BUSINESS_ISOLATION = "read committed"
APPLICATION_NAME = "jp_vocab_ops_synthetic"
OBSERVATION_START = ("SET TRANSACTION READ ONLY",
                     f"SET LOCAL statement_timeout = '{OBSERVE_STATEMENT_TIMEOUT}'",
                     f"SET LOCAL lock_timeout = '{OBSERVE_LOCK_TIMEOUT}'")
PROFILE_VERSION = "jp-vocab-ops/profile/v2"     # v2 adds the TLS allow-list; v1 approvals are not converted
ROLE_ATTRIBUTES = ("superuser", "createrole", "createdb", "replication", "bypassrls", "inherit")
_FORBIDDEN_ATTRIBUTES = ("superuser", "createrole", "createdb", "replication", "bypassrls")
OBJECT_KINDS = ("table", "partitioned_table", "view", "materialized_view", "foreign_table", "sequence", "schema",
                "database", "tablespace", "security_definer_routine", "default_acl", "parameter_acl",
                "large_object")
_NAME = re.compile(r"[A-Za-z0-9_.$-]{1,128}")
_PRIV = re.compile(r"[A-Z_]{1,32}")
_TLS_VERSION = re.compile(r"TLSv1\.[0-9]")


class OpsProviderRefused(Exception):
    """`code` is the leading fixed code; `also` holds the other fixed codes (contract priority)."""

    def __init__(self, code: str, also: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.also = also


# --- interfaces -----------------------------------------------------------------------------

@dataclass(frozen=True)
class ConnectRequest:
    """What the factory gets: the checked secret string plus provider-fixed parameters."""
    secret_dsn: str = field(repr=False)
    fixed: tuple[tuple[str, str], ...]


class ConnectionFactory(Protocol):
    def open(self, request: ConnectRequest) -> Any: ...


class Observer(Protocol):
    def observe(self, connection: Any) -> "Observation": ...


class _NotImplementedFactory:
    def open(self, request: ConnectRequest) -> Any:
        raise OpsProviderRefused("connection_factory_not_implemented")


class _NotImplementedObserver:
    def observe(self, connection: Any) -> "Observation":
        raise OpsProviderRefused("observer_not_implemented")


def fixed_parameters(access: str) -> tuple[tuple[str, str], ...]:
    """Provider-fixed values (contract 1·9절); a user string may still not carry any of them."""
    read_only = "on" if access == "read" else "off"
    settings = (("default_transaction_read_only", read_only), ("default_transaction_isolation", BUSINESS_ISOLATION),
                ("idle_in_transaction_session_timeout", IDLE_IN_TRANSACTION_TIMEOUT))
    options = " ".join(f"-c {_option_escape(name)}={_option_escape(value)}" for name, value in settings)
    return (("application_name", APPLICATION_NAME), ("connect_timeout", str(CONNECT_TIMEOUT)),
            ("gssencmode", "disable"), ("options", options), ("sslcertmode", "disable"))


def _option_escape(value: str) -> str:
    """libpq `options` value rule (PostgreSQL 18 libpq-connect, `options`): whitespace inside a
    value is escaped with a backslash and a literal backslash is doubled. Not shell quoting."""
    return "".join("\\" + ch if ch == "\\" or ch.isspace() else ch for ch in value)


# --- observation ------------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    host: str
    port: int
    dbname: str
    server_major: int
    identity_value: str
    current_user: str
    session_user: str
    role_attributes: tuple[tuple[str, bool], ...]
    memberships: tuple[str, ...]
    owned_count: int
    objects: tuple[tuple[str, str, str], ...]                 # (kind, schema, name)
    privileges: tuple[tuple[str, str, str, str, str], ...]    # (kind, schema, name, column, privilege)
    search_path: str
    observation_read_only: bool                               # inside the observation transaction
    default_read_only: bool                                   # business default for new transactions
    default_isolation: str
    tls_in_use: bool                                          # driver
    tls_server_ssl: bool                                      # server view of this backend
    tls_version: str
    unresolved: tuple[str, ...] = ()                          # fixed codes of things that could not be judged


@dataclass(frozen=True)
class ExpectedProfile:
    """Synthetic expected profile, fixed by the caller for this unit (no ops/profiles file)."""
    objects: frozenset[tuple[str, str, str]]
    privileges: frozenset[tuple[str, str, str, str, str]]
    search_path: str
    tls_versions: frozenset[str]


def _text(value: Any) -> bool:
    return type(value) is str and 0 < len(value) <= 256 and value.isascii() and value.isprintable()


def _check_observation(value: Any) -> Observation:
    if not isinstance(value, Observation):
        raise OpsProviderRefused("observation_invalid")
    o = value
    ints = (o.port, o.server_major, o.owned_count)
    bools = (o.observation_read_only, o.default_read_only, o.tls_in_use, o.tls_server_ssl)
    texts = (o.host, o.dbname, o.identity_value, o.current_user, o.session_user, o.search_path,
             o.default_isolation, o.tls_version)
    if not all(type(v) is int for v in ints) or not all(type(v) is bool for v in bools) \
            or not all(_text(v) for v in texts) or o.port <= 0 or o.server_major <= 0 or o.owned_count < 0:
        raise OpsProviderRefused("observation_invalid")
    # shapes before any unpacking, set or sort (review fix): exact tuple lengths and element types
    if not _tuple_of(o.role_attributes, 2, (str, bool)) \
            or [item[0] for item in o.role_attributes] != list(ROLE_ATTRIBUTES):
        raise OpsProviderRefused("observation_invalid")
    if not _tuple_of(o.objects, 3, (str,) * 3) or not _tuple_of(o.privileges, 5, (str,) * 5):
        raise OpsProviderRefused("observation_invalid")
    if not isinstance(o.memberships, tuple) or not all(_text(m) for m in o.memberships):
        raise OpsProviderRefused("observation_invalid")
    if not isinstance(o.unresolved, tuple) or not all(type(c) is str for c in o.unresolved):
        raise OpsProviderRefused("observation_invalid")
    for kind, schema, name in o.objects:
        if kind not in OBJECT_KINDS or type(schema) is not str or not _NAME.fullmatch(name or "") \
                or (schema and not _NAME.fullmatch(schema)):
            raise OpsProviderRefused("privilege_scope_unknown")
    for kind, schema, name, column, privilege in o.privileges:
        if (kind, schema, name) not in set(o.objects) or type(column) is not str \
                or (column and not _NAME.fullmatch(column)) or type(privilege) is not str \
                or not _PRIV.fullmatch(privilege):
            raise OpsProviderRefused("privilege_scope_unknown")
    if len(set(o.objects)) != len(o.objects) or len(set(o.privileges)) != len(o.privileges):
        raise OpsProviderRefused("observation_invalid")
    return o


def _tuple_of(value: Any, length: int, types: tuple[type, ...]) -> bool:
    """A tuple of tuples, each exactly `length` long with exactly these element types."""
    return isinstance(value, tuple) and all(
        type(item) is tuple and len(item) == length and all(type(x) is t for x, t in zip(item, types))
        for item in value)


def tls_allow_list(value: Any) -> tuple[str, ...]:
    """Normalized TLS allow-list: sorted, non-empty, no duplicates, known version shape."""
    if type(value) not in (frozenset, tuple):
        raise OpsProviderRefused("expected_profile_invalid")
    items = list(value)
    if not items or not all(type(x) is str and _TLS_VERSION.fullmatch(x) for x in items) \
            or len(set(items)) != len(items):
        raise OpsProviderRefused("expected_profile_invalid")
    return tuple(sorted(items))


def _check_expected(expected: Any) -> "ExpectedProfile":
    if not isinstance(expected, ExpectedProfile) or type(expected.objects) is not frozenset \
            or type(expected.privileges) is not frozenset or not _text(expected.search_path) \
            or not _tuple_of(tuple(expected.objects), 3, (str,) * 3) \
            or not _tuple_of(tuple(expected.privileges), 5, (str,) * 5):
        raise OpsProviderRefused("expected_profile_invalid")
    tls_allow_list(expected.tls_versions)
    return expected


def profile_fingerprint(*, role: str, objects, privileges, search_path: str, default_read_only: bool,
                        default_isolation: str, tls_in_use: bool, tls_versions) -> str:
    """Normalized connection / permission fingerprint (contract 2·2-1·2-2). Object list and
    effective privileges are separate parts; the observation transaction's read-only state is
    not in it."""
    doc = {"version": PROFILE_VERSION, "role": role, "memberships": [], "owned": 0,
           "objects": sorted(list(o) for o in objects), "privileges": sorted(list(p) for p in privileges),
           "search_path": search_path, "default_read_only": default_read_only,
           "default_isolation": default_isolation, "tls_in_use": tls_in_use,
           "tls_versions": list(tls_allow_list(tls_versions))}
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expected_profile_fingerprint(expected: ExpectedProfile, *, role: str, access: str) -> str:
    expected = _check_expected(expected)
    return profile_fingerprint(role=role, objects=expected.objects, privileges=expected.privileges,
                               search_path=expected.search_path, default_read_only=access == "read",
                               default_isolation=BUSINESS_ISOLATION, tls_in_use=True,
                               tls_versions=expected.tls_versions)


def judge_observation(o: Observation, *, expected: ExpectedProfile, preflight: op.SyntheticPreflightMatched,
                      approval: oa.Approval, access: str) -> str:
    """Compare a checked observation with the pre-check result, the approval and the expected
    profile. Returns the observed profile fingerprint."""
    if o.unresolved:
        raise OpsProviderRefused("privilege_scope_unknown")
    if o.observation_read_only is not True:
        raise OpsProviderRefused("observation_not_read_only")
    if (o.host, o.port, o.dbname) != (preflight.host, preflight.port, preflight.dbname):
        raise OpsProviderRefused("observed_target_mismatch")
    db_identity = oa.db_identity_fingerprint(alias=approval.alias, host=o.host, port=o.port, database=o.dbname,
                                             server_major=o.server_major, identity_value=o.identity_value)
    if db_identity != approval.db_identity:
        raise OpsProviderRefused("observed_identity_mismatch")
    if o.current_user != preflight.role or o.session_user != preflight.role:
        raise OpsProviderRefused("observed_role_mismatch")
    if any(value for key, value in o.role_attributes if key in _FORBIDDEN_ATTRIBUTES):
        raise OpsProviderRefused("observed_role_attributes")
    if o.memberships:
        raise OpsProviderRefused("observed_memberships")                    # synthetic standard: none
    if o.owned_count != 0:
        raise OpsProviderRefused("observed_ownership")
    if not (o.tls_in_use and o.tls_server_ssl) or o.tls_version not in expected.tls_versions:
        raise OpsProviderRefused("observed_tls_not_in_use")
    if o.default_read_only != (access == "read") or o.default_isolation != BUSINESS_ISOLATION:
        raise OpsProviderRefused("observed_business_defaults_mismatch")
    if o.search_path != expected.search_path:
        raise OpsProviderRefused("observed_search_path_mismatch")
    if frozenset(o.objects) != expected.objects:
        raise OpsProviderRefused("observed_objects_mismatch")
    observed = frozenset(o.privileges)
    if observed - expected.privileges:
        raise OpsProviderRefused("observed_privileges_excess")
    if expected.privileges - observed:
        raise OpsProviderRefused("observed_privileges_missing")
    return profile_fingerprint(role=o.current_user, objects=o.objects, privileges=o.privileges,
                               search_path=o.search_path, default_read_only=o.default_read_only,
                               default_isolation=o.default_isolation, tls_in_use=o.tls_in_use,
                               tls_versions=expected.tls_versions)


# --- lifecycle -----------------------------------------------------------------------------------

class Handoff:
    """A checked connection, handed over once. Not a production permission."""

    def __init__(self, connection: Any, summary: op.SyntheticPreflightMatched, profile: str):
        self._connection = connection
        self.summary = summary
        self.profile = profile

    def __repr__(self) -> str:
        return "Handoff()"

    def take(self) -> Any:
        if self._connection is None:
            raise OpsProviderRefused("handoff_already_taken")
        connection, self._connection = self._connection, None
        return connection


def _driver_error(error: BaseException, timeout_code: str, default: str) -> str:
    if isinstance(error, (pg_errors.ConnectionTimeout, pg_errors.QueryCanceled)):
        return timeout_code
    if isinstance(error, pg_errors.LockNotAvailable):
        return "observation_lock_timeout"
    return default


def _settle(connection: Any, primary: str | None) -> tuple[bool, list[str]]:
    """Rollback once, check the state without sending SQL. Returns (ready, failure codes)."""
    failures: list[str] = []
    try:
        connection.rollback()
    except (psycopg.Error, OSError):
        failures.append("observation_rollback_failed")
        return False, failures
    try:
        healthy = (not connection.broken and not connection.closed
                   and connection.info.transaction_status == TransactionStatus.IDLE
                   and connection.read_only is None and connection.isolation_level is None)
    except (psycopg.Error, OSError, AttributeError):
        healthy = False
    if not healthy:
        failures.append("observation_rollback_failed")
    return healthy and primary is None, failures


def _close(connection: Any) -> bool:
    """Close once; True only if the driver reports the connection closed."""
    try:
        connection.close()
    except (psycopg.Error, OSError):
        return False
    try:
        return connection.closed is True
    except AttributeError:
        return False


def _verified(preflight: Any, inputs: op.PreflightInput) -> tuple[oa.Approval, oa.Approval | None, oa.Approval | None]:
    """The approvals the pre-check of THIS call verified, tied to the same fixed input bytes."""
    verified = getattr(preflight, "verified", None)
    if not isinstance(verified, op._Verified) or not isinstance(verified.approval, oa.Approval) \
            or not verified.approval.verified:
        raise OpsProviderRefused("preflight_result_mismatch")
    approval, inquiry, prior = verified.approval, verified.inquiry, verified.prior
    expected = [(approval, inputs.approval)]
    expected.append((inquiry, inputs.inquiry if approval.kind == "apply" else None))
    expected.append((prior, inputs.prior_chain[-1].approval if inputs.prior_chain else None))
    for item, data in expected:
        if (item is None) != (data is None):
            raise OpsProviderRefused("preflight_result_mismatch")
        if item is not None and (not item.verified or item.sha256 != hashlib.sha256(data).hexdigest()):
            raise OpsProviderRefused("preflight_result_mismatch")
    return approval, inquiry, prior


def provide_synthetic_connection(inputs: op.PreflightInput, *, expected: ExpectedProfile,
                                 factory: ConnectionFactory | None = None,
                                 observer: Observer | None = None) -> Handoff:
    """Every call checks everything again (a reconnect is a new call). Default factory and
    observer are not implemented and refuse before any connection."""
    if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
        raise OpsProviderRefused("mode_not_synthetic")
    factory = factory or _NotImplementedFactory()
    observer = observer or _NotImplementedObserver()
    if isinstance(factory, _NotImplementedFactory):
        raise OpsProviderRefused("connection_factory_not_implemented")
    if isinstance(observer, _NotImplementedObserver):
        raise OpsProviderRefused("observer_not_implemented")
    if not isinstance(expected, ExpectedProfile):
        raise OpsProviderRefused("expected_profile_invalid")
    try:
        preflight = op.run_synthetic_preflight(inputs)                         # unit 5, signatures included
    except op.OpsPreflightRefused as error:
        raise OpsProviderRefused(f"preflight_{error.code}") from None
    approval, inquiry, prior = _verified(preflight, inputs)                  # contract 4-6-6
    step = next(s for s in approval.steps if s.command == inputs.command)
    if expected_profile_fingerprint(expected, role=step.role, access=step.access) != step.profile:
        raise OpsProviderRefused("expected_profile_not_approved")              # the expected data is the approved one
    try:
        connection = factory.open(ConnectRequest(inputs.secret_dsn, fixed_parameters(step.access)))
    except (psycopg.Error, OSError) as error:
        raise OpsProviderRefused(_driver_error(error, "connect_timeout", "connect_failed")) from None
    primary: str | None = None
    profile = ""
    try:
        try:
            for statement in OBSERVATION_START:
                connection.execute(statement)
            observation = _check_observation(observer.observe(connection))
        except (psycopg.Error, OSError) as error:
            raise OpsProviderRefused(_driver_error(error, "observation_timeout", "observation_failed")) from None
        profile = judge_observation(observation, expected=expected, preflight=preflight, approval=approval,
                                    access=step.access)
        try:
            oa.authorize_command(
                approval, now=inputs.now, command=inputs.command, args=inputs.args, account_id=inputs.account_id,
                job_key=inputs.job_key, job_inputs=inputs.job_inputs, product_fingerprint=inputs.product_fingerprint,
                observed=oa.Observed(db_identity=preflight.db_identity, manifest=preflight.manifest_sha256,
                                     role=observation.current_user, profile=profile,
                                     read_only=observation.default_read_only),
                inquiry=inquiry, prior=prior, artifact_sha256=inputs.artifact_sha256)   # 3-3-1, 4-6-6
        except oa.OpsApprovalRefused as error:
            raise OpsProviderRefused(f"observed_{error.code}") from None
    except OpsProviderRefused as refused:
        primary = refused.code
    except BaseException:
        _close(connection)            # an unexpected error never leaves the connection behind
        raise
    ready, failures = _settle(connection, primary)
    if ready:
        return Handoff(connection, preflight, profile)
    codes = ([primary] if primary else []) + failures
    if not _close(connection):
        codes.insert(0, "connection_close_unconfirmed")
    ranked = sorted(dict.fromkeys(codes), key=lambda c: 0 if c == "connection_close_unconfirmed"
                    else 1 if c == "observation_rollback_failed" else 2)
    raise OpsProviderRefused(ranked[0], tuple(ranked[1:]))


def provide_connection(inputs: Any, *, expected: Any) -> Handoff:
    """Default entry point: no real factory or observer exists yet, so it always refuses."""
    if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
        raise OpsProviderRefused("mode_not_synthetic")
    return provide_synthetic_connection(inputs, expected=expected)
