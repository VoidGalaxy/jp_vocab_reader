"""Synthetic only: a provider connection handed to the product as its connection context
(OPS_MIGRATION_CLI_PLAN 6-1 / 6-2). `ProductConnector(...)` is a `connect(*, read_only=False)`
function for `dry_run` / `apply_plan(connect=...)`.

Every call runs the whole existing provider path again (pre-check with signatures, target, TLS,
connection, observation, re-judgement) and takes the hand-over once; nothing is reused or retried.
The read / write request must match the access of the approved step; nothing is changed to make
them match. The app is imported only after a pre-check has passed, with its environment fixed
before. The returned context keeps the product's transaction contract: commit on a normal end,
rollback on an error or interrupt, then one close. A failed commit is reported as unconfirmed,
never as "not committed". Refusals carry fixed codes only (no driver text, no secret, no chaining).
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

import _ops_adapter as ad
import _ops_approval as oa
import _ops_audit_run as ar
import _ops_preflight as op
import _ops_provider as pv

# Cleanup failures raised on a normal end, first is the code (contract 6-2).
CLEANUP_ORDER = ("connection_close_unconfirmed", "commit_failed_result_unconfirmed", "rollback_failed")


class OpsProductConnectionError(Exception):
    def __init__(self, code: str, also: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.also = tuple(also)


def _refuse(code: str, also: tuple[str, ...] = ()) -> OpsProductConnectionError:
    return OpsProductConnectionError(code, also)


def _ranked(codes: list[str]) -> OpsProductConnectionError:
    ordered = sorted(dict.fromkeys(codes), key=CLEANUP_ORDER.index)
    return _refuse(ordered[0], tuple(ordered[1:]))


def _attempt(step: Any) -> tuple[bool, BaseException | None]:
    """One cleanup step, tried once. Returns (succeeded, interrupt). An ordinary error is a failure;
    an interrupt is handed back to be kept (never swallowed, never raised here)."""
    try:
        step()
        return True, None
    except Exception:
        return False, None
    except BaseException as interrupt:                  # KeyboardInterrupt, SystemExit, ...
        return False, interrupt


def _close(raw: Any) -> tuple[bool, BaseException | None]:
    """One close call, never retried. Closed only when it returned AND reading the closed state
    reports True; a failed or interrupted state read is "close unconfirmed" like a failed close."""
    done, interrupt = _attempt(raw.close)
    if not done:
        return False, interrupt
    state: list[bool] = []
    done, interrupt = _attempt(lambda: state.append(raw.closed is True))
    return done and state == [True], interrupt


def _bare(interrupt: BaseException) -> BaseException:
    """The kept interrupt itself, without any chained cause or context (no raw text in a traceback)."""
    interrupt.__cause__ = None
    interrupt.__context__ = None
    interrupt.__suppress_context__ = True
    return interrupt


def _step_access(inputs: op.PreflightInput) -> str:
    """Format-only read of the approval, used to REFUSE early; the provider verifies everything."""
    try:
        approval = oa.parse_approval(inputs.approval)
    except oa.OpsApprovalRefused:
        raise _refuse("connection_access_unknown") from None
    step = next((s for s in approval.steps if s.command == inputs.command), None) \
        if type(inputs.command) is str else None
    if step is None:
        raise _refuse("connection_access_unknown")
    return step.access


class ProductConnection:
    """Single-use context: `with` gives the app connection; the exit ends the transaction and closes."""

    def __init__(self, raw: Any, app: Any, failures: list[str]):
        self._raw, self._app, self._failures = raw, app, failures
        self._state = "ready"

    def __repr__(self) -> str:
        return f"ProductConnection(state={self._state})"

    def __enter__(self) -> Any:
        if self._state != "ready":
            raise _refuse("connection_already_used")
        self._state = "entered"
        return self._app

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._state != "entered":
            return False
        self._state = "done"
        business = exc_type is not None                 # the business's first error / interrupt: kept as is
        failures: list[str] = []
        interrupts: list[BaseException] = []            # this helper's own, in the order they happened
        if not business:
            done, interrupt = _attempt(self._raw.commit)
            if not done:
                failures.append("commit_failed_result_unconfirmed")   # never read as "not committed"
                interrupts += [interrupt] if interrupt is not None else []
        if business or failures:
            done, interrupt = _attempt(self._raw.rollback)
            if not done:
                failures.append("rollback_failed")
                interrupts += [interrupt] if interrupt is not None else []
        closed, interrupt = _close(self._raw)           # tried once, also after an interrupt
        if not closed:
            failures.insert(0, "connection_close_unconfirmed")
            interrupts += [interrupt] if interrupt is not None else []
        if business and interrupts:
            failures.append("cleanup_interrupted")      # recorded; it never replaces the business's own
        self._failures.extend(failures)                 # codes only, for the caller's record
        if business:
            return False                                # the business error / interrupt goes on unchanged
        if interrupts:
            raise _bare(interrupts[0])                  # the first one: commit > rollback > close
        if failures:
            raise _ranked(failures)
        return False


class ProductConnector:
    """`connect(*, read_only=False)` over the synthetic provider. Synthetic mode and an explicit
    driver function are required; there is no default and no real connection here."""

    def __init__(self, inputs: Any, *, expected: Any, driver: Any):
        if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
            raise _refuse("mode_not_synthetic")
        if driver is None or not callable(driver):
            raise _refuse("connection_factory_not_implemented")
        self._inputs, self._expected, self._driver = inputs, expected, driver
        self.failures: list[str] = []                   # cleanup codes from business-error exits

    def __repr__(self) -> str:
        return "ProductConnector(<synthetic>)"

    def __call__(self, *, read_only: bool = False) -> ProductConnection:
        if type(read_only) is not bool:
            raise _refuse("read_only_invalid")
        if (_step_access(self._inputs) == "read") != read_only:
            raise _refuse("connection_access_mismatch")         # before any connection; nothing adjusted
        ar.fix_app_environment()                                 # environment only; nothing from app yet
        try:
            handoff = ad.provide_with_adapter(self._inputs, expected=self._expected, driver=self._driver)
        except pv.OpsProviderRefused as refused:
            raise _refuse(refused.code, refused.also) from None
        raw = handoff.take()
        return self._prepare(raw, handoff.summary, read_only)

    def _prepare(self, raw: Any, summary: Any, read_only: bool) -> ProductConnection:
        code = "connection_prepare_failed"
        interrupts: list[BaseException] = []
        try:
            if (summary.access == "read") != read_only:
                code = "connection_access_mismatch"
                raise _refuse(code)
            raw.row_factory = dict_row                           # no SQL
            try:
                from app.database import AppPostgresConnection   # only after the pre-check passed
            except ImportError:
                code = "product_import_failed"
                raise _refuse(code) from None
            app = AppPostgresConnection(raw)
            if read_only:
                raw.execute("SET TRANSACTION READ ONLY")         # the same first statement as get_connection
            return ProductConnection(raw, app, self.failures)
        except Exception:
            pass                                                  # a fixed code below, no raw text kept
        except BaseException as interrupt:
            interrupts.append(interrupt)                          # kept; cleanup goes on first
        closed, interrupt = _close(raw)                           # never handed out, closed once
        codes = [code] if closed else ["connection_close_unconfirmed", code]
        if interrupt is not None:
            interrupts.append(interrupt)
        if interrupts:
            self.failures.extend(codes)
            raise _bare(interrupts[0])                            # preparation interrupt > close interrupt
        raise _refuse(codes[0], tuple(codes[1:]))
