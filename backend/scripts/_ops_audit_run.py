"""Read-only SRS invariant audit over the operations connection provider, synthetic mode only
(OPS_AUDIT_SYNTHETIC_CONNECTION_CONTRACT.md).

Order: synthetic mode and an explicit driver -> the signed whole-database scope of the inquiry
approval, checked before any connection -> fix the app environment before any app import ->
6-1a/b/c/d provider path (pre-check, verified certificate copy, observation, judgement, handover)
-> `dict_row` -> `AppPostgresConnection` -> `read_snapshot` (REPEATABLE READ, READ ONLY) with
15s / 5s local timeouts -> target re-check -> the existing `audit()` -> rollback -> close once.

There is no default driver and no production mode: the existing CLI is not wired to this path.
The audit reads the WHOLE designated database (all accounts); `accounts` / `account_id` are only
the job slot the approval format requires and never grant that scope. Output carries the audit
result, fixed reason codes, approval / target fingerprints and the scope; never a DSN, host or
port text, password, card content, e-mail or token.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

import _ops_adapter as ad
import _ops_approval as oa
import _ops_manifest as om
import _ops_preflight as op
import _ops_provider as pv

TOOL, COMMAND = "srs_invariant_audit", "audit"
SCOPE = "database_all"
SCOPE_KEYS = frozenset({"audit_scope", "audit_db_identity"})
STATEMENT_TIMEOUT, LOCK_TIMEOUT = "15s", "5s"            # fixed by the user (contract 7절)
EXIT = {"pass": 0, "fail": 1, "error": 2, "unknown": 2, "partial": 3}   # same as srs_invariant_audit.py
_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
RECHECK = ("SELECT pg_catalog.current_database()::pg_catalog.text AS dbname, "
           "pg_catalog.inet_server_port() AS port, "
           "pg_catalog.current_setting('server_version_num') AS version")
IDENTITY = "SELECT t.identity_value AS identity_value FROM jp_vocab_ops_synthetic.db_identity AS t LIMIT 2"


def _refuse(code: str) -> pv.OpsProviderRefused:
    return pv.OpsProviderRefused(code)


def check_scope(inputs: op.PreflightInput) -> oa.Approval:
    """Contract 1-1절, before any connection. Format only here; the provider's pre-check then
    verifies the signature and compares the run inputs again."""
    try:
        approval = oa.parse_approval(inputs.approval)
    except oa.OpsApprovalRefused:
        raise _refuse("audit_approval_shape_invalid") from None
    step = approval.steps[0] if len(approval.steps) == 1 else None
    if approval.tool != TOOL or approval.kind != "inquiry" or step is None or step.command != COMMAND \
            or step.access != "read" or step.args or inputs.command != COMMAND or dict(inputs.args or {}):
        raise _refuse("audit_approval_shape_invalid")
    signed = dict(approval.job_inputs)
    if set(signed) != SCOPE_KEYS:
        raise _refuse("audit_scope_missing")
    if type(signed["audit_scope"]) is not str or signed["audit_scope"] != SCOPE:
        raise _refuse("audit_scope_not_database")
    if type(signed["audit_db_identity"]) is not str or signed["audit_db_identity"] != approval.db_identity:
        raise _refuse("audit_scope_db_mismatch")
    # the job slot: exactly one, and the run's account is that slot (not a scope)
    if len(approval.accounts) != 1 or approval.max_accounts != 1 or type(inputs.account_id) is not int \
            or inputs.account_id not in approval.accounts:
        raise _refuse("audit_approval_shape_invalid")
    required = {"audit_scope": SCOPE, "audit_db_identity": approval.db_identity}
    given = dict(inputs.job_inputs) if hasattr(inputs.job_inputs, "items") else None
    if given is None or set(given) != SCOPE_KEYS or any(type(given[k]) is not str or given[k] != v
                                                         for k, v in required.items()):
        raise _refuse("audit_job_inputs_mismatch")       # refused, never overwritten with the signed values
    return approval


def fix_app_environment() -> None:
    """Before ANY app import: the app must not pick a database from the environment or .env."""
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def _identifiers(approval: oa.Approval) -> dict:
    return {"alias": approval.alias, "db_identity": approval.db_identity,
            "manifest": approval.manifest, "approval_id": approval.approval_id, "tool": TOOL, "command": COMMAND}


def _output(report: dict, target: dict | None) -> tuple[dict, int]:
    """Only the allowed fields (contract 5절)."""
    status = report.get("status")
    if status not in EXIT:
        report, status = {"audit_version": 1, "status": "error", "reason": "audit_result_invalid"}, "error"
    out = {key: report[key] for key in ("audit_version", "status", "checks", "reason") if key in report}
    out["scope"] = SCOPE
    if target is not None:
        out["target"] = dict(target)
    return out, EXIT[status]


def _error(code: str) -> dict:
    return {"audit_version": 1, "status": "error", "reason": code if _CODE.fullmatch(code) else "audit_refused"}


def _recheck(app_conn: Any, summary: op.SyntheticPreflightMatched, approval: oa.Approval) -> None:
    """Inside the audit snapshot: the connected target is still the approved one."""
    row = app_conn.execute(RECHECK).fetchone()
    rows = app_conn.execute(IDENTITY).fetchall()
    if row is None or row["dbname"] != summary.dbname or row["port"] != summary.port \
            or type(row["version"]) is not str or not row["version"].isdigit() or len(rows) != 1:
        raise _refuse("audit_target_recheck_failed")
    identity = oa.db_identity_fingerprint(alias=approval.alias, host=summary.host, port=summary.port,
                                          database=row["dbname"], server_major=int(row["version"]) // 10000,
                                          identity_value=rows[0]["identity_value"])
    if identity != approval.db_identity or identity != summary.db_identity:
        raise _refuse("audit_target_recheck_failed")


def run_synthetic_audit(inputs: Any, *, expected: Any, driver: Any = None) -> tuple[dict, int]:
    """Returns (output, exit code). No default driver; production mode refused.

    App modules are imported only after the real pre-check (approval and manifest signatures,
    deployed file hashes, target and command) has passed here; the provider then runs the same
    pre-check again before connecting. This orders the import after the check; it does not bind
    the checked bytes to what Python imports (still unverified). After the handover the connection
    is closed exactly once on every path, including KeyboardInterrupt / SystemExit, which are
    re-raised after the cleanup and never turned into a result."""
    target = None
    try:
        if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
            raise _refuse("mode_not_synthetic")
        if driver is None or not callable(driver):
            raise _refuse("connection_factory_not_implemented")
        approval = check_scope(inputs)                        # scope and shape: before any connection
        target = _identifiers(approval)
        fix_app_environment()                                 # environment only; nothing from app yet
        try:
            op.run_synthetic_preflight(inputs)                # the full real pre-check, no caller "done" flag
        except op.OpsPreflightRefused as error:
            raise _refuse(f"preflight_{error.code}") from None
    except pv.OpsProviderRefused as refused:
        return _output(_error(refused.code), target)
    backend = str(Path(__file__).resolve().parents[1])
    if backend not in sys.path:
        sys.path.insert(0, backend)
    try:
        from app.database import AppPostgresConnection          # only after the pre-check passed
        from app.srs.invariant_audit import AuditInputError, audit, read_snapshot
    except ImportError:
        return _output(_error("audit_import_failed"), target)
    try:
        handoff = ad.provide_with_adapter(inputs, expected=expected, driver=driver)
    except pv.OpsProviderRefused as refused:
        return _output(_error(refused.code), target)
    except om.OpsManifestRefused:
        return _output(_error("audit_refused"), target)
    connection = handoff.take()
    report: dict = _error("audit_refused_or_unreadable")
    closed = False
    stop: BaseException | None = None       # the FIRST interrupt (KeyboardInterrupt, SystemExit, ...), kept as is
    try:
        try:
            connection.row_factory = dict_row                 # no SQL: rows by column name, as the audit expects
            app_conn = AppPostgresConnection(connection)
            with read_snapshot(app_conn):                     # REPEATABLE READ, READ ONLY; rolled back on exit
                try:
                    app_conn.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")
                    app_conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                    _recheck(app_conn, handoff.summary, approval)
                    report = audit(app_conn)
                except BaseException as error:
                    if not isinstance(error, Exception):
                        stop = error                          # recorded before read_snapshot's rollback can mask it
                    raise
        except BaseException as error:
            if stop is None and not isinstance(error, Exception):
                stop = error
            if stop is None:                                  # ordinary errors: the existing fixed codes
                if isinstance(error, pv.OpsProviderRefused):
                    report = _error(error.code)
                elif isinstance(error, AuditInputError):      # fixed reason codes of the audit module
                    report = _error(str(error.args[0]) if error.args and isinstance(error.args[0], str)
                                    else "audit_refused")
                else:                                         # driver text may hold SQL or content
                    report = _error("audit_refused_or_unreadable")
    finally:                                                  # every path, interrupts included: close once
        try:
            connection.close()
            closed = connection.closed is True
        except Exception:
            closed = False
    if stop is not None:
        # re-raised outside any handler, without the rollback / close errors chained to it
        stop.__cause__ = None
        stop.__context__ = None
        stop.__suppress_context__ = True
        raise stop
    if not closed:
        report = _error("audit_close_failed")                 # never reported as a success
    return _output(report, target)
