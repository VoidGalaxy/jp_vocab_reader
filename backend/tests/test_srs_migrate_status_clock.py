"""OPS_MIGRATION_COMPLETED_REPLAY_PLAN 3-7 / 8 (C5): `srs_migrate.py status`'s own fresh-time
behaviour -- a missing clock is the real current UTC (never `inputs.now`), and the pre-check
(`_admit`) and the read connection request (`_timed_connector`) each read a fresh time of their
own, so a caller cannot keep an expired approval alive with a stale `inputs.now` and a connection
that was valid at admission can still be refused as expired at the connection request.

REAL here: admission / signature verification / the unit-5 pre-check, `ProductConnector`, the
6-1d adapter, the 6-1a provider and its post-connect re-authorization (the same path `apply` /
`resume` use through `_timed_connector`). FAKE here (see `test_srs_migrate_cli.FlowBase`): the
driver, the connection (`BizConn`) and the observation catalog it answers with. The product
`read_status` is replaced by a STUB reader (the fake connection cannot run product SQL); it only
records whether a business connection was entered and a SELECT was sent, never real rows.

Run directly:      python tests/test_srs_migrate_status_clock.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_preflight as op  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_observer as to  # noqa: E402  (module only)
import test_ops_signature as sigtests  # noqa: E402  (module only)
import test_srs_migrate_cli as tcli  # noqa: E402  (fixture base only; its own tests are not re-run here)

# The suite's synthetic signer key is only trusted (by the fixed allowed_signers entry every
# `pf.Base` test uses) for `ssh-keygen -Y verify -O verify-time=...` inside this fixed historical
# window -- independent of any approval's own `valid_from` / `valid_until`. Every clock value below
# that reaches real signature verification must stay inside it.
WINDOW_START = datetime(2026, 10, 21, 12, 10, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 10, 21, 12, 20, 0, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _ThenReturn:
    """A clock: the first call answers `first`; every later call answers `rest` (sequential, not
    reused -- proves the two fresh-time reads are independent calls)."""

    def __init__(self, first, rest=None):
        self.values = [first, rest if rest is not None else first]
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.values[min(self.calls, len(self.values)) - 1]


class _ThenRaise:
    """A clock: the first call answers `first`; every later call raises `exc` (same instance)."""

    def __init__(self, first, exc):
        self.first, self.exc, self.calls = first, exc, 0

    def __call__(self):
        self.calls += 1
        if self.calls == 1:
            return self.first
        raise self.exc


class _Raise:
    """A clock that always raises `exc` (never returns a time)."""

    def __init__(self, exc):
        self.exc = exc

    def __call__(self):
        raise self.exc


class _CustomInterrupt(BaseException):
    """Neither KeyboardInterrupt nor SystemExit: a plain direct BaseException, like a cancellation
    signal (review correction 1, bug 2) -- must propagate exactly as `asyncio.CancelledError` does,
    not be caught by a two-name exception list."""


class _ArmableAfterAdmit:
    """Review correction 1 (point 3): the first call answers `first` (admission). Once `arm(value)`
    has been called -- by a wrapper that runs the REAL `_admit` and inspects its own genuine
    result -- every later call answers `value`, the approval's OWN `valid_until`. This proves the
    behavioural outcome (was the connection actually allowed past real expiry?), not a call count."""

    def __init__(self, first):
        self.first = first
        self.armed = None
        self.calls = 0

    def arm(self, value):
        self.armed = value

    def __call__(self):
        self.calls += 1
        if self.armed is None:
            return self.first
        return self.armed


class ClockBase(tcli.FlowBase):
    """Fixtures only (see the module docstring for what is real and what is fake); no test methods."""

    def status_approval(self, *, valid_from, valid_until, **changes):
        values = dict(tool="srs_migrate", accounts=[self.req.account_id], max_accounts=1,
                      steps=[{"command": "status", "access": "read", "role": "ops_read",
                              "profile": self.read_profile()}],
                      job={"key": self.req.run_key, "inputs": cli.job_inputs(self.req)},
                      valid_from=_iso(valid_from), valid_until=_iso(valid_until))
        values.update(changes)
        return self.inquiry(**values)

    def status_inputs(self, approval, **changes):
        values = dict(command="status", account_id=self.req.account_id, job_key=self.req.run_key,
                      job_inputs=cli.job_inputs(self.req), product_fingerprint=None,
                      connection=op.ConnectionObservation(profile=self.read_profile(), read_only=True))
        values.update(changes)
        return self.inputs(approval, **values)

    def unrestricted_trust(self):
        """TEST ONLY, for the "omitted clock" case below: the SAME synthetic test key, but the
        allowed_signers entry carries no `valid-after` / `valid-before` restriction (unlike every
        other fixture in this suite, which reuses the fixed historical window). A real
        `ssh-keygen -Y verify` still runs over the same synthetic key; this is never a production
        trust root and never a user key."""
        allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*", window="")
        return op.SyntheticTrust(allowed, b"", sigtests.PRINCIPAL)

    def run_status(self, inputs, *, clock, driver="default"):
        calls: list[str] = []

        def reader(connect, request, migration):
            with connect(read_only=True) as c:
                calls.append("connected")
                c.execute("SELECT 1")
            return None
        with mock.patch.object(cli, "read_status", reader):
            out, code = cli.run_status(self.req, inputs=inputs, expected=to.READ_EXPECTED,
                                       driver=self.driver if driver == "default" else driver, clock=clock)
        return out, code, calls


class ClockFlow(ClockBase):
    """C5 fresh-time checks. One `self.driver` (one fake connection) per test method: every case
    below either refuses before any connection or makes exactly one successful one."""

    def approval(self):
        return self.status_approval(valid_from=WINDOW_START, valid_until=WINDOW_END)

    def test_expires_after_admit_before_connection(self):
        # Review correction 1 (point 3): the ORIGINAL inputs.now is itself a valid earlier instant
        # (never the one judged -- `_admit` always replaces it -- but fixed here so a stray read of
        # it could not accidentally produce the expected refusal for an unrelated reason). A wrapper
        # runs the REAL, unmodified `_admit` and arms the clock with the approval's OWN `valid_until`
        # only once admission has genuinely matched, so the connection-time expiry is the real
        # boundary, not a guessed instant.
        valid_entry = WINDOW_START + timedelta(seconds=1)
        inputs = self.status_inputs(self.approval(), now=valid_entry)
        clock = _ArmableAfterAdmit(valid_entry)
        real_admit = cli._admit

        def armed_admit(*args, **kwargs):
            result = real_admit(*args, **kwargs)                 # the exact, unmodified result
            if not isinstance(result, tuple):                    # admission matched: now expire it for real
                clock.arm(result.verified.approval.valid_until)
            return result
        with mock.patch.object(cli, "_admit", armed_admit):
            out, code, calls = self.run_status(inputs, clock=clock)
        # Behavioural evidence: the expired connection must be REFUSED, with no driver connection and
        # no business SELECT -- not merely a different clock call count (a frozen connector that
        # reuses the admission-time instant would instead let this succeed with code 0).
        self.assertEqual((out.get("status"), out.get("code"), code), ("refused", "preflight_approval_expired", 4))
        self.assertEqual(calls, [])                      # no business SELECT
        self.assertEqual(self.driver.calls, [])           # no driver connection

    def test_admit_rejects_at_exact_expiry_and_accepts_one_second_before(self):
        inputs = self.status_inputs(self.approval())
        out, code, calls = self.run_status(inputs, clock=lambda: WINDOW_END - timedelta(seconds=1))
        self.assertEqual((out["state"], code, calls), ("not_started", 0, ["connected"]))
        self.assertEqual(len(self.driver.calls), 1)
        out, code, calls = self.run_status(inputs, clock=lambda: WINDOW_END)
        self.assertEqual((out["code"], code, calls), ("preflight_approval_expired", 4, []))
        self.assertEqual(len(self.driver.calls), 1)       # the refusal opened no second connection

    def test_expired_at_entry_is_refused_before_any_connection(self):
        inputs = self.status_inputs(self.approval())
        out, code, calls = self.run_status(inputs, clock=lambda: WINDOW_END + timedelta(seconds=1))
        self.assertEqual((out["code"], code, calls), ("preflight_approval_expired", 4, []))
        self.assertEqual(self.driver.calls, [])

    def test_stale_caller_now_cannot_bypass_expiry(self):
        valid_looking_now = WINDOW_START + timedelta(seconds=2)
        inputs = self.status_inputs(self.approval(), now=valid_looking_now)
        clock = _ThenReturn(WINDOW_END, WINDOW_END)       # both fresh reads are expired, now the stale field is not
        out, code, calls = self.run_status(inputs, clock=clock)
        self.assertEqual((out["code"], code, calls), ("preflight_approval_expired", 4, []))
        self.assertEqual(self.driver.calls, [])

    def test_fresh_entry_and_connection_times_with_the_same_fixed_bytes(self):
        inputs = self.status_inputs(self.approval())
        clock = _ThenReturn(WINDOW_START + timedelta(seconds=1), WINDOW_START + timedelta(seconds=2))
        out, code, calls = self.run_status(inputs, clock=clock)
        self.assertEqual((out["state"], code, calls), ("not_started", 0, ["connected"]))
        self.assertEqual(clock.calls, 2)                  # two independent fresh reads, not one reused
        self.assertEqual(len(self.driver.calls), 1)

    def test_non_utc_clock_time_converts_correctly(self):
        jst = timezone(timedelta(hours=9))
        instant = (WINDOW_START + timedelta(seconds=1)).astimezone(jst)
        inputs = self.status_inputs(self.approval())
        out, code, calls = self.run_status(inputs, clock=lambda: instant)
        self.assertEqual((out["state"], code, calls), ("not_started", 0, ["connected"]))

    def test_omitted_clock_uses_real_current_time_not_inputs_now(self):
        now = datetime.now(timezone.utc)
        approval = self.status_approval(valid_from=now - timedelta(hours=1), valid_until=now + timedelta(hours=1))
        inputs = self.status_inputs(approval, now=datetime(2000, 1, 1, tzinfo=timezone.utc),   # stale, must be ignored
                                    trust=self.unrestricted_trust())
        calls: list[str] = []

        def reader(connect, request, migration):
            with connect(read_only=True) as c:
                calls.append("connected")
                c.execute("SELECT 1")
            return None
        with mock.patch.object(cli, "read_status", reader):
            out, code = cli.run_status(self.req, inputs=inputs, expected=to.READ_EXPECTED, driver=self.driver)
        self.assertEqual((out["state"], code, calls), ("not_started", 0, ["connected"]))

    def test_falsy_explicit_clock_values_are_not_silently_replaced(self):
        # Review correction 1 (bug 1): `clock or default` treats any falsy clock (False, 0, "", [],
        # {}) as "omitted" and silently substitutes the real current time -- even though the caller
        # explicitly passed something. Only `clock=None` may select the default. A currently-valid
        # approval + unrestricted-time trust means the bug, if present, actually SUCCEEDS (opens a
        # connection); the fix must instead refuse clock_invalid (none of these values are callable).
        now = datetime.now(timezone.utc)
        approval = self.status_approval(valid_from=now - timedelta(hours=1), valid_until=now + timedelta(hours=1))
        inputs = self.status_inputs(approval, trust=self.unrestricted_trust())
        values = (False, 0, "", [], {})
        # A fresh fake connection per case: if the bug is present, EVERY one of these falsy values
        # is silently replaced and actually succeeds, so a single shared connection (exhausted by
        # the first case) would hide the later cases behind an unrelated IndexError instead of
        # showing the real (wrong) "ok" result.
        driver = tcli.ta.FakeDriver(*(tcli.tpc.BizConn() for _ in values))
        for value in values:
            with self.subTest(clock=repr(value)):
                out, code, calls = self.run_status(inputs, clock=value, driver=driver)
                self.assertEqual((out.get("status"), out.get("code"), code, calls),
                                 ("refused", "clock_invalid", 4, []))
        self.assertEqual(driver.calls, [])

    def test_invalid_clocks_at_entry_are_sanitized_without_connecting(self):
        inputs = self.status_inputs(self.approval())
        cases = {
            "not callable": 123,
            "raises an ordinary error": _Raise(RuntimeError("synthetic clock failure 93f1a2")),
            "returns a plain string": lambda: "not a time",
            "returns a naive datetime": lambda: datetime(2027, 6, 1, 0, 0, 1),
            "underflows converting to utc": lambda: datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            "overflows converting to utc": lambda: datetime(9999, 12, 31, 23, 59, 59,
                                                            tzinfo=timezone(timedelta(hours=-1))),
        }
        for label, clock in cases.items():
            with self.subTest(case=label):
                out, code, calls = self.run_status(inputs, clock=clock)
                self.assertEqual((out, code, calls), ({"status": "refused", "command": "status",
                                                        "code": "clock_invalid"}, 4, []))
                self.assertNotIn("93f1a2", json.dumps(out))
        self.assertEqual(self.driver.calls, [])

    def test_invalid_clocks_at_connection_are_sanitized_without_connecting(self):
        inputs = self.status_inputs(self.approval())
        valid_entry = WINDOW_START + timedelta(seconds=1)
        cases = {
            "raises an ordinary error": _ThenRaise(valid_entry, RuntimeError("synthetic clock failure 7a2c9e")),
            "returns a naive datetime": _ThenReturn(valid_entry, datetime(2027, 6, 1, 0, 0, 2)),
            "underflows converting to utc": _ThenReturn(valid_entry, datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1)))),
            "overflows converting to utc": _ThenReturn(valid_entry, datetime(9999, 12, 31, 23, 59, 59,
                                                                            tzinfo=timezone(timedelta(hours=-1)))),
        }
        for label, clock in cases.items():
            with self.subTest(case=label):
                out, code, calls = self.run_status(inputs, clock=clock)
                self.assertEqual((out, code, calls), ({"status": "refused", "command": "status",
                                                        "code": "clock_invalid"}, 4, []))
                self.assertNotIn("7a2c9e", json.dumps(out))
        self.assertEqual(self.driver.calls, [])

    def test_all_baseexceptions_from_the_clock_propagate_unchanged(self):
        # Review correction 1 (bug 2): _sanitized_clock must only sanitize ordinary Exception, never
        # any BaseException -- not just the two named KeyboardInterrupt / SystemExit. Covered here:
        # KeyboardInterrupt, SystemExit(9) (with its value), asyncio.CancelledError (a BaseException
        # since Python 3.8, easily missed by a two-name except list) and a plain custom
        # BaseException. Each must be the SAME object, not a class-equal stand-in, and open no
        # connection.
        inputs = self.status_inputs(self.approval())
        valid_entry = WINDOW_START + timedelta(seconds=1)
        makers = (lambda: KeyboardInterrupt(), lambda: SystemExit(9), lambda: asyncio.CancelledError(),
                 lambda: _CustomInterrupt())
        for make in makers:
            original = make()
            with self.subTest(case=f"{type(original).__name__} at entry"):
                with self.assertRaises(type(original)) as caught:
                    self.run_status(inputs, clock=_Raise(original))
                self.assertIs(caught.exception, original)
                if isinstance(original, SystemExit):
                    self.assertEqual(caught.exception.code, 9)
            original = make()
            with self.subTest(case=f"{type(original).__name__} at connection"):
                with self.assertRaises(type(original)) as caught:
                    self.run_status(inputs, clock=_ThenRaise(valid_entry, original))
                self.assertIs(caught.exception, original)
                if isinstance(original, SystemExit):
                    self.assertEqual(caught.exception.code, 9)
        self.assertEqual(self.driver.calls, [])


class CommandLine(unittest.TestCase):
    """A fresh process; the initial clock refusal must never import the app."""

    def test_invalid_clock_is_refused_before_app_import(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import test_srs_migrate_status_clock as t\n"
                "t.ClockFlow.setUpClass()\n"
                "case = t.ClockFlow('test_expires_after_admit_before_connection'); case.setUp()\n"
                "import srs_migrate as cli\n"
                "inputs = case.status_inputs(case.approval())\n"
                "out, status = cli.run_status(case.req, inputs=inputs, expected=t.to.READ_EXPECTED,"
                " driver=case.driver, clock=123)\n"
                "app = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "print('RESULT', out['code'], status, app, len(case.driver.calls))\n"
                "case.doCleanups(); t.ClockFlow.tearDownClass()\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT clock_invalid 4 False 0", done.stdout, done.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
