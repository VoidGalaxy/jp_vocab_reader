"""Fake-only checks for the PG69 completed-result requery real-PG runner (tests/_ops_completed_replay_real.py,
CR-PG1). No database, cluster, certificate, listener or admin connection: connect entry points, `subprocess`,
process facts and (outside `ApprovalPaths`) key creation are blocked. The runner's real `prepare` /
`check-completed` / `cleanup` never run against anything here; nothing in this file is PostgreSQL evidence.

Separately allowed: new Python processes for the import / entry-point smoke checks (`Imports`); no process here
ever reaches a real connection, driver or key. `ApprovalPaths` (section 8) is the one exception that allows real
temporary OpenSSH test keys (`test_ops_signature.Keys`, via `cr.sigtests.Keys`) for real approval signing; every
PostgreSQL, admin, process and TLS entry point stays forbidden there too.

`G1FixturesAndBaseline` (section 9) exercises the REAL `cr.g1_gate` / `cr.g1_build_p5_fixtures` /
`cr.g1_build_p10_block` / `cr.post_check` / `cr.p5_not_started_variants` / `cr.p10_active_write_block_ignored`
control flow end to end, on a fake `h` whose faked pieces are `case` / `first_apply` / `state_admin` /
`database_facts` / `row_text` / `restore_row` / `sessions` / `read_only_inputs`, plus `cr.admin` (a strict
in-memory fake dispatcher over a shared model, never psycopg) and `cr.ADMIN_CHANGES_APPROVED` (patched to
`True` only inside this class, restored by `addCleanup` -- `cr.admin_mutation_guard` itself is the REAL
function). `h.status`/`h.status_raw` DO exercise the real `cli.run_status` -> `cli.read_status` ->
`migration._scope_cards` -> `judge_status` chain (section 10's `real_run_status`/`FakeStatusConnection`
bounded adapter, reused here against the SAME model rows G1 built; only `cli._admit`/`cli._timed_connector`
are stubbed, never preflight/signing/provider machinery): no real PostgreSQL, admin connection, TLS or
process is reached either way (`Blocked`, inherited). The REAL-PG runner's own `Harness.status`/`status_raw`
(in `_ops_completed_replay_real.py`) still use the unmodified real connector/preflight plumbing against an
actual PostgreSQL connection; nothing here replaces that.

Run directly:      python tests/test_ops_completed_replay_real_guard.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_completed_replay_real_guard.py
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import hashlib  # noqa: E402

import psycopg  # noqa: E402

import _ops_completed_replay_real as cr  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_real_layout as lay  # noqa: E402

MODULE_PATH = TESTS_DIR / "_ops_completed_replay_real.py"


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


class Blocked(unittest.TestCase):
    """Every real connection, process, key creation and listener lookup fails the test if reached."""

    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden), mock.patch.object(cr.sigtests, "Keys", forbidden),
                      mock.patch.object(g, "listener_pids", forbidden), mock.patch.object(g, "admin_connect", forbidden),
                      mock.patch.object(g, "postmaster_pid", forbidden), mock.patch.object(g, "single_run", forbidden),
                      mock.patch.object(lay.real, "make_tls", forbidden), mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)


# --- 1. target, registration, matrix --------------------------------------------------------------------------

class Target(Blocked):
    def test_closed_values_and_identity(self):
        self.assertIs(cr.LAYOUT, lay.PG69)
        self.assertIs(cr.T, g.PG69_COMPLETED_REPLAY)
        self.assertEqual((cr.T.root, cr.T.port, cr.T.admin, cr.T.provider_roles),
                         (Path("C:/JV_Tools/pg69"), 55532, "jpvq_admin", ("jpvq_read", "jpvq_write")))
        self.assertEqual(cr.T.databases, ("jp_vocab_test_completed_template",)
                         + tuple(f"jp_vocab_test_completed_{c}" for c in cr.PLANNED))
        self.assertEqual(cr.PLANNED, ("p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10"))
        self.assertEqual((lay.PG69.owner, lay.PG69.read, lay.PG69.write), ("jpvq_owner", "jpvq_read", "jpvq_write"))
        self.assertEqual(lay.PG69.variants, {})
        self.assertEqual(lay.PG69.variant_databases, {})
        self.assertIs(g.PRESETS[-1], cr.T)
        self.assertIs(lay.LAYOUTS[-1], lay.PG69)
        copy = dataclasses.replace(cr.T)
        with self.assertRaises(g.Pg62Refused):
            g.preset(copy)
        layout_copy = dataclasses.replace(lay.PG69)
        with self.assertRaises(g.Pg62Refused):
            lay.layout(layout_copy)

    def test_names_are_separate_from_every_other_target(self):
        others = [p for p in g.PRESETS if p is not cr.T]
        self.assertNotIn(cr.T.port, {p.port for p in others})
        self.assertNotIn(cr.T.root, {p.root for p in others})
        self.assertFalse(set(cr.T.databases) & {d for p in others for d in p.databases})
        self.assertFalse(set(cr.T.provider_roles + (cr.T.admin, "jpvq_owner"))
                         & {r for p in others for r in p.provider_roles + (p.admin,)})

    def test_business_matrix(self):
        ok = {"host": g.HOST, "port": "55532", "dbname": cr.CHECK_DB["p1"], "user": "jpvq_write",
              "sslmode": "verify-full"}
        cr.business_check(ok)
        for key, value in (("port", "55522"), ("dbname", cr.TEMPLATE), ("dbname", "jp_vocab_test_access_lock_k1"),
                           ("user", "jpvq_admin"), ("user", "jpvk_write"), ("sslmode", "require")):
            with self.subTest(key=key, value=value), self.assertRaises(g.Pg62Refused):
                cr.business_check(dict(ok, **{key: value}))

    def test_runner_has_no_target_or_approval_override_inputs(self):
        source = re.sub(r'"""[\s\S]*?"""', "", MODULE_PATH.read_text(encoding="utf-8"))
        body = source.split("def main(")[0]
        for forbidden_text in ("argparse", "os.environ.get(", "getenv(", "DATABASE_URL", "sys.argv"):
            with self.subTest(text=forbidden_text):
                self.assertNotIn(forbidden_text, body)
        self.assertIn("LAYOUT = lay.PG69", source)


# --- 2. approvals: None refuses every phase before any target lookup or external work --------------------------

class Approvals(Blocked):
    def test_approval_constants_are_none(self):
        self.assertIsNone(cr.PREPARE_APPROVED)
        self.assertIsNone(cr.CHECK_APPROVED)
        self.assertIsNone(cr.ADMIN_CHANGES_APPROVED)
        self.assertIsNone(cr.CLEANUP_APPROVED)

    def test_prepare_refuses_before_any_target_lookup(self):
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.prepare()
        self.assertEqual(caught.exception.kind, "preparation_failure")

    def test_cleanup_refuses_before_any_target_lookup(self):
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.cleanup()
        self.assertEqual(caught.exception.kind, "preparation_failure")

    def test_check_completed_refuses_before_any_target_lookup(self):
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.check_completed()
        self.assertEqual(caught.exception.kind, "preparation_failure")

    def test_check_completed_needs_both_check_and_admin_approval(self):
        with mock.patch.object(cr, "CHECK_APPROVED", True), mock.patch.object(cr, "ADMIN_CHANGES_APPROVED", None):
            with self.assertRaises(cr.CheckFailed) as caught:
                cr.check_completed()
            self.assertEqual(caught.exception.kind, "preparation_failure")
        with mock.patch.object(cr, "CHECK_APPROVED", None), mock.patch.object(cr, "ADMIN_CHANGES_APPROVED", True):
            with self.assertRaises(cr.CheckFailed) as caught:
                cr.check_completed()
            self.assertEqual(caught.exception.kind, "preparation_failure")

    def test_other_values_do_not_approve_anything(self):
        for value in (False, 0, 1, "True", "true", [], object()):
            with self.subTest(value=repr(value)):
                with mock.patch.object(cr, "PREPARE_APPROVED", value), self.assertRaises(cr.CheckFailed):
                    cr.prepare()
                with mock.patch.object(cr, "CLEANUP_APPROVED", value), self.assertRaises(cr.CheckFailed):
                    cr.cleanup()
                with mock.patch.object(cr, "CHECK_APPROVED", value), \
                        mock.patch.object(cr, "ADMIN_CHANGES_APPROVED", value), self.assertRaises(cr.CheckFailed):
                    cr.check_completed()


# --- 3. CLI: fixed commands only, extra / unknown arguments refused --------------------------------------------

class CLI(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(cr, "prepare", forbidden), mock.patch.object(cr, "cleanup", forbidden),
                      mock.patch.object(cr, "check_completed", forbidden)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_no_args_is_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cr.main([]), 2)
        self.assertIn("usage", out.getvalue())

    def test_unknown_or_extra_arguments_are_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cr.main(["check-access-lock"]), 2)
            self.assertEqual(cr.main(["prepare", "--port", "55432"]), 2)
            self.assertEqual(cr.main(["prepare", "extra"]), 2)
            self.assertEqual(cr.main(["check-completed", "--approve"]), 2)
            self.assertEqual(cr.main(["cleanup", ""]), 2)

    def test_each_phase_reaches_only_its_own_function(self):
        for phase in cr.PHASES:
            with self.subTest(phase=phase):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), self.assertRaises(AssertionError):
                    cr.main([phase])

    def test_phases_are_closed(self):
        self.assertEqual(cr.PHASES, ("prepare", "check-completed", "cleanup"))


# --- 4. ReplayTracked: the RC-variant rewrite is scoped to the product's own SET TRANSACTION statement ---------

class FakeConn:
    def __init__(self):
        self.info = SimpleNamespace(backend_pid=1)
        self.sent: list = []

    def execute(self, query, *a, **k):
        self.sent.append(query)
        return FakeFetchCursor([{"id": 1, "status": "completed"}])


class FakeFetchCursor:
    """A minimal cursor stand-in: `fetchone` / `fetchall` return a frozen row (no real driver, no
    network); exercises `ReplayCursor` through the real `ReplayTracked.execute` return path."""

    def __init__(self, rows: list):
        self._rows = list(rows)
        self.rowcount = len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def fake_harness():
    """A minimal `h`-shaped object for `held_admin_action`: a real on-disk `g.Record` (so `rec.event`
    really saves JSON) and the plain lists the real function reads/appends."""
    class H:
        pass
    folder = Path(tempfile.mkdtemp(prefix="pg69_fake_harness_"))
    obj = H()
    obj.rec = g.Record(folder)
    obj.threads = []
    obj.connections = []
    return obj


class Tracker(unittest.TestCase):
    def test_rc_variant_rewrites_only_the_products_own_set_transaction(self):
        counts = cr.Counts()
        tracked = cr.ReplayTracked(FakeConn(), counts, cr.READ, [], rc_variant=True)
        tracked.activate()
        tracked.execute(cr.ReplayTracked._RR)
        tracked.execute("SELECT 1")
        self.assertEqual(tracked._conn.sent, [cr.ReplayTracked._RC, "SELECT 1"])

    def test_without_rc_variant_nothing_is_rewritten(self):
        counts = cr.Counts()
        normal = cr.ReplayTracked(FakeConn(), counts, cr.READ, [], rc_variant=False)
        normal.activate()
        normal.execute(cr.ReplayTracked._RR)
        self.assertEqual(normal._conn.sent, [cr.ReplayTracked._RR])


# --- 4b. FetchPause / held_admin_action: the real P8/P9 ordering mechanism, fake connection only ----------------

class FetchPauseMechanics(unittest.TestCase):
    """Exercises the ACTUAL `cr.FetchPause` / `cr.held_admin_action` / `cr.ReplayTracked` /
    `cr.ReplayCursor` code paths with a fake, network-free connection -- not a re-implementation, not a
    hand-built false condition fed to `expect`. Models the pause point and the admin ordering; proves
    nothing about real PostgreSQL row visibility or locking."""

    def test_pause_fires_after_fetchone_returns_the_same_object_never_a_second_query(self):
        pause = cr.FetchPause(cr.READ, "fetchone", cr.RUN_ROW_PREFIX, limit=2)
        seen: dict = {}

        def capturing_hook(role, method, query, tracker, result):
            seen["hook_saw"] = result
            pause.hook(role, method, query, tracker, result)
        tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[capturing_hook])
        tracked.activate()

        def run():
            cursor = tracked.execute(cr.RUN_ROW_PREFIX + " WHERE run_key = %s")
            seen["returned"] = cursor.fetchone()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self.assertTrue(pause.reached.wait(2))
        self.assertTrue(pause.still_held())
        self.assertIsNotNone(pause.captured.get("row"))
        self.assertTrue(pause.captured.get("sql_template", "").startswith(cr.RUN_ROW_PREFIX))
        pause.release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIs(seen["hook_saw"], seen["returned"])     # the SAME object; no second observing query
        self.assertFalse(pause.still_held())

    def test_held_admin_action_orders_admin_before_release_and_checks_still_held_after_commit(self):
        h = fake_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)
        order: list = []

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            order.append("status_resumed_after_release")
            return {"out": {"state": "completed"}, "code": 0}

        def admin_action():
            order.append("admin_committed")
            return {"committed": True}
        outcome = cr.held_admin_action(h, "pX", pause, run_status_fn, admin_action, limit=2)
        self.assertEqual(order, ["admin_committed", "status_resumed_after_release"])
        self.assertTrue(outcome.still_held_after_commit)
        self.assertEqual(outcome.status["code"], 0)
        self.assertEqual(outcome.admin, {"committed": True})

    def test_admin_action_timeout_is_a_bounded_harness_defect_never_a_hang(self):
        h = fake_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            return {"out": {}, "code": 0}

        def hanging_admin():
            time.sleep(5)             # models an unwanted row lock the admin transaction waits on
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, hanging_admin, limit=0.3)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_pause_never_reached_is_a_harness_defect(self):
        h = fake_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT NEVER SENT", limit=0.2)
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.held_admin_action(h, "pX", pause, lambda: {"out": {}, "code": 0}, lambda: {"ok": True}, limit=0.2)
        self.assertEqual(caught.exception.kind, "harness_defect")
        pause.release.set()           # nothing waiting; defensive cleanup only


# --- 5. import / entry-point safety (new processes only) -------------------------------------------------------

class Imports(unittest.TestCase):
    def test_module_import_has_no_effect_in_a_new_process(self):
        code = ("import sys, os, subprocess, tempfile, psycopg\n"
                f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "def bad(*a, **k): raise SystemExit('EXTERNAL')\n"
                "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad; tempfile.mkdtemp = bad\n"
                "import _ops_completed_replay_real\n"
                "loaded = sorted(m for m in sys.modules if m == 'app' or m.startswith('app.'))\n"
                "print('LOADED', loaded)\n")
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "APP_ENV", "DATABASE_URL")}
        for name in list(env):
            if name.upper().startswith(("PG", "POSTGRES")):
                del env[name]
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
        self.assertIn("LOADED []", done.stdout, done.stderr[-600:])

    def test_main_guard_subprocess_usage_exit_two(self):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        for name in list(env):
            if name.upper().startswith(("PG", "POSTGRES")):
                del env[name]
        env.update(APP_ENV="test", DATABASE_URL="sqlite:///:memory:", PYTHON_DOTENV_DISABLED="1")
        done = subprocess.run([sys.executable, str(MODULE_PATH)], capture_output=True, text=True, timeout=120,
                              env=env)
        self.assertEqual(done.returncode, 2, done.stderr[-600:])
        self.assertIn("usage:", done.stdout)

    def test_module_not_part_of_default_discovery(self):
        # _ops_*.py modules are never collected by `python -m unittest discover`: no TestCase subclass here.
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("unittest.TestCase", source)
        self.assertNotIn("import unittest", source)


# --- 5b. check_completed(): order, gates, first-failure, not_run -- real control flow, fake Harness/checks -------

class FakeHarness:
    def __init__(self, rec):
        self.rec = rec
        self.threads: list = []
        self.pauses: list = []

    def start(self):
        pass

    def close(self):
        return cr.FinalCleanup()


class CheckCompletedOrdering(unittest.TestCase):
    """The REAL `cr.check_completed` control flow (gates, 10-check order, first-failure-stops-the-rest,
    `not_run`, record save + readback via the real `lay.run_recorded`): only `Harness`, the gates, the
    check list and `post_check` are faked, so this never touches PostgreSQL."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pg69_check_completed_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "record.json").write_text(
            json.dumps({"run_id": self.folder.name, "events": [], "results": []}), encoding="utf-8")

    def run_with(self, checks, g0=lambda h: {}, g1=lambda h: {}, post=lambda h: {}):
        patches = (mock.patch.object(cr, "CHECK_APPROVED", True), mock.patch.object(cr, "ADMIN_CHANGES_APPROVED", True),
                  mock.patch.object(g, "pg_environment_present", lambda: False),
                  mock.patch.object(g, "single_run", lambda target: g.Record(self.folder)),
                  mock.patch.object(cr, "Harness", FakeHarness), mock.patch.object(cr, "g0_gate", g0),
                  mock.patch.object(cr, "g1_gate", g1), mock.patch.object(cr, "post_check", post),
                  mock.patch.object(cr, "CHECKS", checks))
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return cr.check_completed()

    def test_all_pass_in_fixed_order(self):
        order = []
        checks = [(n, (lambda h, n=n: order.append(n) or {})) for n in ("p1", "p2", "p3")]
        passed, summary = self.run_with(checks)
        self.assertEqual((passed, summary["failed"], summary["not_run"], order), (3, None, [], ["p1", "p2", "p3"]))

    def test_first_failure_stops_the_rest_and_records_not_run(self):
        order = []

        def fail(h):
            raise cr.CheckFailed("harness_defect", "boom")
        checks = [("p1", lambda h: order.append("p1") or {}), ("p2", fail),
                 ("p3", lambda h: order.append("p3") or {})]
        passed, summary = self.run_with(checks)
        self.assertEqual((passed, summary["failed"], summary["not_run"], order), (1, "p2", ["p3"], ["p1"]))

    def test_g0_gate_failure_stops_before_any_check(self):
        def fail_g0(h):
            raise cr.CheckFailed("preparation_failure", "boom")
        passed, summary = self.run_with([("p1", lambda h: {"ok": 1})], g0=fail_g0)
        self.assertEqual((passed, summary["failed"], summary["not_run"]), (0, "g0_gate", ["p1"]))

    def test_g1_gate_failure_stops_before_any_check(self):
        def fail_g1(h):
            raise cr.CheckFailed("preparation_failure", "boom")
        passed, summary = self.run_with([("p1", lambda h: {"ok": 1})], g1=fail_g1)
        self.assertEqual((passed, summary["failed"], summary["not_run"]), (0, "g1_gate", ["p1"]))

    def test_post_check_failure_after_every_check_passed(self):
        def fail_post(h):
            raise cr.CheckFailed("harness_defect", "boom")
        passed, summary = self.run_with([("p1", lambda h: {"ok": 1})], post=fail_post)
        self.assertEqual((passed, summary["failed"]), (1, "post_check"))

    def test_gates_and_post_are_recorded_but_never_counted_in_passed(self):
        passed, summary = self.run_with([("p1", lambda h: {"ok": 1}), ("p2", lambda h: {"ok": 1})])
        saved = json.loads((self.folder / "record.json").read_text(encoding="utf-8"))
        names = [r["check"] for r in saved["results"]]
        self.assertEqual(names, ["g0_gate", "g1_gate", "p1", "p2", "post_check"])
        self.assertEqual(passed, 2)

    def test_approvals_stay_none_after_this_test(self):
        self.assertIsNone(cr.CHECK_APPROVED)
        self.assertIsNone(cr.ADMIN_CHANGES_APPROVED)


# --- 6. Mutations: 5 meaningful in-memory mutants, each rejected for its own cause ------------------------------

class Mutations(unittest.TestCase):
    """Every mutant lives only inside this test; the on-disk module under test is never changed."""

    def test_p9_rc_detection_mutant_is_rejected(self):
        counts = cr.Counts()
        real_tracked = cr.ReplayTracked(FakeConn(), counts, cr.READ, [], rc_variant=True)
        real_tracked.activate()
        real_tracked.execute(cr.ReplayTracked._RR)
        self.assertEqual(real_tracked._conn.sent, [cr.ReplayTracked._RC])
        # Mutant: the RC-variant wiring is skipped (rc_variant lost / forgotten on the tracker).
        mutant_tracked = cr.ReplayTracked(FakeConn(), counts, cr.READ, [], rc_variant=False)
        mutant_tracked.activate()
        mutant_tracked.execute(cr.ReplayTracked._RR)
        with self.assertRaises(AssertionError):
            self.assertEqual(mutant_tracked._conn.sent, [cr.ReplayTracked._RC])

    def test_premature_pause_release_mutant_is_rejected(self):
        """The ACTUAL `held_admin_action` path: a mutant admin action releases the pause itself (as if
        the holder let go before its own commit finished / was observed). The real function's
        `still_held_after_commit` must be False, which is exactly what the real P8/P9 subcase checks."""
        h = fake_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            return {"out": {"state": "completed"}, "code": 0}

        def mutant_admin_action():
            pause.release.set()           # mutant: released before this action's own "commit" completes
            return {"committed": True}
        outcome = cr.held_admin_action(h, "pX", pause, run_status_fn, mutant_admin_action, limit=2)
        self.assertFalse(outcome.still_held_after_commit)

    def test_omitted_final_rejoin_mutant_is_rejected(self):
        """The ACTUAL `held_admin_action` path: the status call never ends (mutant: the second, bounded
        rejoin after release is skipped elsewhere and nobody notices). The real function must refuse."""
        h = fake_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=0.2)

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            time.sleep(5)              # mutant: the status thread never ends promptly even after release
            return {"out": {}, "code": 0}
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, lambda: {"ok": True}, limit=0.3)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_unmatched_cleanup_start_mutant_is_rejected(self):
        folder = Path(tempfile.mkdtemp(prefix="pg69_mutation_test_"))
        try:
            record = {"run_id": "x", "events": [{"kind": "final_cleanup_started", "token": "final:1"}],
                      "results": []}
            path = folder / "record.json"
            path.write_text(json.dumps(record), encoding="utf-8")

            def mutant_blocking_events(record_file):
                # Mutant: only looks for thread_not_ended / cleanup_incomplete, ignores unmatched starts.
                events = json.loads(record_file.read_text(encoding="utf-8"))["events"]
                return [e.get("kind") for e in events if e.get("kind") in ("thread_not_ended", "cleanup_incomplete")]
            self.assertEqual(mutant_blocking_events(path), [])
            self.assertEqual(cr.blocking_events(path), ["final_cleanup_unconfirmed"])
            with self.assertRaises(cr.CheckFailed) as caught:
                blocked = cr.blocking_events(path)
                if blocked:
                    raise cr.CheckFailed("harness_defect", f"R2 refused: recorded {sorted(set(blocked))}")
            self.assertEqual(caught.exception.kind, "harness_defect")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_omitted_required_subcase_mutant_is_rejected(self):
        folder = Path(tempfile.mkdtemp(prefix="pg69_mutation_test_"))
        try:
            rec = g.Record(folder)
            rec.event("subcase", check="p1", name="call_0_state", ok=True)
            # "call_1_state" is never recorded: the mutant forgot a required subcase.

            class H:
                pass
            h = H()
            h.rec = rec
            with self.assertRaises(cr.CheckFailed) as caught:
                cr.require_subcases(h, "p1", ("call_0_state", "call_1_state"))
            self.assertEqual(caught.exception.kind, "harness_defect")
            # The mutant's narrower required-list wrongly passes: proof that omitting the name is the cause.
            self.assertEqual(cr.require_subcases(h, "p1", ("call_0_state",)), ["call_0_state"])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


# --- 7. Lifecycle: restore_guarded error priority, held_admin_action ownership/cleanup, Harness.close ------------

class InterruptingEvent(threading.Event):
    """A real `threading.Event`: the FIRST `set()` actually sets it (so anything waiting really wakes up),
    then raises, modeling an interrupt landing inside a cleanup stage without silently losing the release."""

    def __init__(self):
        super().__init__()
        self.set_calls = 0

    def set(self):
        self.set_calls += 1
        super().set()
        if self.set_calls == 1:
            raise KeyboardInterrupt("cleanup interrupt")


class FakeCloseObj:
    """The plain attributes `cr.Harness.close` reads/writes, with no real target, record or connection."""

    def __init__(self):
        self.pauses: list = []
        self.threads: list = []
        self.connections: list = []
        self.keys = None
        self.folders: list = []
        self.passwords = {"jpvq_write": "secret"}


class FakeKey:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Lifecycle(unittest.TestCase):
    """Composition only (plain `unittest.TestCase`, no shared test-bearing base): every case calls the
    ACTUAL `cr.restore_guarded` / `cr.held_admin_action` / `cr.Harness.close` code, never a reimplementation."""

    def owned_harness(self):
        h = fake_harness()
        self.addCleanup(shutil.rmtree, h.rec.folder, True)
        return h

    # -- restore_guarded: the original in-flight body error/interrupt always wins, same object -----------------

    def test_original_system_exit_wins_over_restore_keyboard_interrupt_and_log_failure(self):
        h = self.owned_harness()
        h.rec.event = mock.Mock(side_effect=RuntimeError("log boom"))
        original = SystemExit(9)

        def action():
            raise KeyboardInterrupt("restore interrupt")
        try:
            try:
                raise original
            finally:
                cr.restore_guarded(h, "pX", action)
        except SystemExit as caught:
            self.assertIs(caught, original)
            self.assertEqual(caught.code, 9)
        else:
            self.fail("original SystemExit was not propagated")

    def test_original_body_exception_wins_over_restore_interrupt(self):
        h = self.owned_harness()
        original = ValueError("body boom")

        def action():
            raise KeyboardInterrupt("restore interrupt")
        try:
            try:
                raise original
            finally:
                cr.restore_guarded(h, "pX", action)
        except ValueError as caught:
            self.assertIs(caught, original)
        else:
            self.fail("original ValueError was not propagated")

    def test_no_original_restore_interrupt_propagates_with_chain_stripped_despite_log_failure(self):
        h = self.owned_harness()
        h.rec.event = mock.Mock(side_effect=RuntimeError("log boom"))
        restore_error = KeyboardInterrupt("restore interrupt")

        def action():
            raise restore_error
        with self.assertRaises(KeyboardInterrupt) as caught:
            cr.restore_guarded(h, "pX", action)
        self.assertIs(caught.exception, restore_error)
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_original_system_exit_with_synthetic_secret_context_preserved_cause_context_none(self):
        h = self.owned_harness()
        synthetic_secret = RuntimeError("synthetic-secret-token-xyz")
        original = SystemExit(9)

        def action():
            raise KeyboardInterrupt("cleanup interrupt")
        try:
            try:
                try:
                    raise synthetic_secret
                except RuntimeError:
                    raise original
            finally:
                cr.restore_guarded(h, "pX", action)
        except SystemExit as caught:
            self.assertIs(caught, original)
            self.assertEqual(caught.code, 9)
        else:
            self.fail("original SystemExit was not propagated")
        self.assertIsNone(original.__cause__)
        self.assertIsNot(original.__context__, None)
        self.assertNotIsInstance(original.__context__, KeyboardInterrupt)

    # -- held_admin_action: ownership of both threads, bounded cleanup, fixed error priority --------------------

    def test_normal_run_registers_both_threads_and_confirms_cleanup(self):
        h = self.owned_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)
        order: list = []

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            order.append("status_resumed")
            return {"out": {"state": "completed"}, "code": 0}

        def admin_action():
            order.append("admin_committed")
            return {"committed": True}
        outcome = cr.held_admin_action(h, "pX", pause, run_status_fn, admin_action, limit=2)
        self.assertEqual(order, ["admin_committed", "status_resumed"])
        self.assertTrue(outcome.still_held_after_commit)
        self.assertEqual({t.name.rsplit(":", 1)[-1] for t in h.threads}, {"status", "admin"})
        self.assertTrue(all(not t.is_alive() for t in h.threads))
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        kinds = [e["kind"] for e in saved["events"]]
        self.assertEqual((kinds.count("coordination_started"), kinds.count("coordination_ended")), (1, 1))

    def test_admin_timeout_ends_only_after_owned_connection_close_and_rejoin(self):
        h = self.owned_harness()

        class OwnedConnStub:
            def __init__(self):
                self.closed = False
                self.close_event = threading.Event()

            def close(self):
                self.closed = True
                self.close_event.set()
        conn = OwnedConnStub()
        h.connections.append(conn)
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            return {"out": {}, "code": 0}

        def hanging_until_closed():
            conn.close_event.wait(5)          # ends only once the harness closes its owned connection
            return {"ok": True}
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, hanging_until_closed, limit=0.3)
        self.assertEqual(caught.exception.kind, "harness_defect")
        self.assertTrue(conn.closed)
        admin_threads = [t for t in h.threads if t.name.endswith(":admin")]
        self.assertEqual(len(admin_threads), 1)
        admin_threads[0].join(2)
        self.assertFalse(admin_threads[0].is_alive())

    def test_never_ending_status_actor_raises_and_records_blocker(self):
        h = self.owned_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=0.2)

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            time.sleep(5)          # never ends promptly even after release: a harness defect, not a hang
            return {"out": {}, "code": 0}
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, lambda: {"ok": True}, limit=0.3)
        self.assertEqual(caught.exception.kind, "harness_defect")
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        kinds = [e["kind"] for e in saved["events"]]
        self.assertIn("thread_not_ended", kinds)
        self.assertIn("cleanup_incomplete", kinds)

    def test_status_body_interrupt_wins_over_a_cleanup_interrupt(self):
        h = self.owned_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)
        pause.release = InterruptingEvent()
        body_interrupt = KeyboardInterrupt("status body interrupt")

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            raise body_interrupt
        with self.assertRaises(KeyboardInterrupt) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, lambda: {"ok": True}, limit=2)
        self.assertIs(caught.exception, body_interrupt)

    def test_cleanup_interrupt_during_release_still_runs_later_cleanup_stages(self):
        h = self.owned_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)
        pause.release = InterruptingEvent()

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            return {"out": {"state": "completed"}, "code": 0}
        with self.assertRaises(KeyboardInterrupt):
            cr.held_admin_action(h, "pX", pause, run_status_fn, lambda: {"committed": True}, limit=2)
        self.assertTrue(all(not t.is_alive() for t in h.threads))        # bounded rejoin still ran
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        kinds = [e["kind"] for e in saved["events"]]
        self.assertIn("coordination_ended", kinds)        # the end was still confirmed and recorded

    def test_ordinary_release_error_does_not_record_coordination_ended(self):
        h = self.owned_harness()
        pause = cr.FetchPause(cr.READ, "fetchone", "SELECT A", limit=2)

        class RaisingEvent:
            def set(self):
                raise RuntimeError("release boom")

            def wait(self, timeout=None):
                return real_release.wait(timeout)
        real_release = pause.release
        pause.release = RaisingEvent()

        def run_status_fn():
            tracked = cr.ReplayTracked(FakeConn(), cr.Counts(), cr.READ, [], fetch_hooks=[pause.hook])
            tracked.activate()
            tracked.execute("SELECT A WHERE 1 = 1").fetchone()
            return {"out": {"state": "completed"}, "code": 0}

        def admin_action():
            real_release.set()
            return {"committed": True}
        with self.assertRaises(RuntimeError) as caught:
            cr.held_admin_action(h, "pX", pause, run_status_fn, admin_action, limit=2)
        self.assertEqual(str(caught.exception), "release boom")
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        kinds = [e["kind"] for e in saved["events"]]
        self.assertNotIn("coordination_ended", kinds)

    # -- Harness.close: all owned threads/connections, every stage attempted, no active-thread deletion ----------

    def test_close_never_deletes_a_deploy_folder_while_a_thread_is_alive(self):
        obj = FakeCloseObj()
        blocker = threading.Event()
        self.addCleanup(blocker.set)
        thread = threading.Thread(target=blocker.wait, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        obj.threads.append(thread)
        folder = Path(tempfile.mkdtemp(prefix=cr.DEPLOY_PREFIX))
        self.addCleanup(shutil.rmtree, folder, True)
        created = os.stat(folder, follow_symlinks=False)
        obj.folders.append({"path": str(folder), "parent": os.path.dirname(str(folder)),
                           "dev": created.st_dev, "ino": created.st_ino})
        obj.keys = FakeKey()
        with mock.patch.object(cr, "WAIT_LIMIT", 0.3):
            done = cr.Harness.close(obj)
        self.assertTrue(os.path.exists(folder))
        self.assertIn("deploy_folder_thread_active", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})
        blocker.set()

    def test_close_skips_already_closed_connections_and_closes_the_rest(self):
        obj = FakeCloseObj()

        class Conn:
            def __init__(self, closed):
                self.closed = closed
                self.close_called = False

            def close(self):
                self.close_called = True
                self.closed = True
        closed_conn, open_conn = Conn(True), Conn(False)
        obj.connections = [closed_conn, open_conn]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertFalse(closed_conn.close_called)
        self.assertTrue(open_conn.close_called)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})
        self.assertEqual(done.failures, [])

    def test_close_attempts_keys_folder_and_secrets_despite_a_connection_close_failure(self):
        obj = FakeCloseObj()

        class FailingConn:
            closed = False

            def close(self):
                raise RuntimeError("close boom")
        obj.connections = [FailingConn()]
        obj.keys = FakeKey()
        folder = Path(tempfile.mkdtemp(prefix=cr.DEPLOY_PREFIX))
        self.addCleanup(shutil.rmtree, folder, True)
        created = os.stat(folder, follow_symlinks=False)
        obj.folders.append({"path": str(folder), "parent": os.path.dirname(str(folder)),
                           "dev": created.st_dev, "ino": created.st_ino})
        done = cr.Harness.close(obj)
        self.assertIn("connection_close_failed", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertFalse(os.path.exists(folder))          # no alive thread: folder deletion still proceeds
        self.assertEqual(obj.passwords, {})

    def test_close_attempts_keys_folder_and_secrets_despite_closed_getter_error_and_interrupt(self):
        obj = FakeCloseObj()

        class RaisingClosedConn:
            def close(self):
                self.closed_after = True

            @property
            def closed(self):
                raise KeyboardInterrupt("closed getter interrupt")
        obj.connections = [RaisingClosedConn()]
        obj.keys = FakeKey()
        folder = Path(tempfile.mkdtemp(prefix=cr.DEPLOY_PREFIX))
        self.addCleanup(shutil.rmtree, folder, True)
        created = os.stat(folder, follow_symlinks=False)
        obj.folders.append({"path": str(folder), "parent": os.path.dirname(str(folder)),
                           "dev": created.st_dev, "ino": created.st_ino})
        done = cr.Harness.close(obj)
        self.assertTrue(obj.keys.closed)
        self.assertFalse(os.path.exists(folder))
        self.assertEqual(obj.passwords, {})
        self.assertTrue(any(f.startswith("connection_close_") for f in done.failures))

    def test_close_attempts_second_connection_after_first_close_fails(self):
        obj = FakeCloseObj()

        class FailingConn:
            closed = False

            def close(self):
                raise RuntimeError("close boom")

        class OkConn:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True
        failing, ok = FailingConn(), OkConn()
        obj.connections = [failing, ok]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertTrue(ok.closed)
        self.assertIn("connection_close_failed", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})

    def test_close_records_failure_when_close_does_not_confirm_closed(self):
        obj = FakeCloseObj()

        class UnconfirmedConn:
            closed = False

            def close(self):
                pass            # never flips closed -> can't be confirmed
        obj.connections = [UnconfirmedConn()]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertIn("connection_close_failed", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})

    def test_close_releases_blocked_thread_then_rejoin_confirms_end(self):
        obj = FakeCloseObj()
        blocker = threading.Event()
        self.addCleanup(blocker.set)

        class ConnBlockingThread:
            def __init__(self, blocker):
                self.closed = False
                self.blocker = blocker

            def close(self):
                self.closed = True
                self.blocker.set()
        conn = ConnBlockingThread(blocker)
        obj.connections.append(conn)

        def wait_for_close():
            blocker.wait(5)
        thread = threading.Thread(target=wait_for_close, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        obj.threads.append(thread)
        folder = Path(tempfile.mkdtemp(prefix=cr.DEPLOY_PREFIX))
        self.addCleanup(shutil.rmtree, folder, True)
        created = os.stat(folder, follow_symlinks=False)
        obj.folders.append({"path": str(folder), "parent": os.path.dirname(str(folder)),
                           "dev": created.st_dev, "ino": created.st_ino})
        obj.keys = FakeKey()
        with mock.patch.object(cr, "WAIT_LIMIT", 0.5):
            done = cr.Harness.close(obj)
        self.assertTrue(conn.closed)
        self.assertFalse(thread.is_alive())
        self.assertFalse(os.path.exists(folder))
        self.assertNotIn("deploy_folder_thread_active", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})

    def test_close_preserves_keyboard_interrupt_from_closed_getter_when_later_checks_succeed(self):
        obj = FakeCloseObj()

        class OnceRaisingClosedConn:
            def __init__(self):
                self.raised = False
                self.close_called = False

            def close(self):
                self.close_called = True

            @property
            def closed(self):
                if not self.raised:
                    self.raised = True
                    raise KeyboardInterrupt("closed getter interrupt")
                return True
        conn = OnceRaisingClosedConn()
        obj.connections = [conn]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertTrue(conn.close_called)
        self.assertEqual(len(done.interrupts), 1)
        self.assertIsInstance(done.interrupts[0], KeyboardInterrupt)
        self.assertTrue(any(f.startswith("connection_state_") for f in done.failures))
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})

    def test_close_reports_thread_end_unconfirmed_even_with_no_folders(self):
        obj = FakeCloseObj()
        blocker = threading.Event()
        self.addCleanup(blocker.set)
        thread = threading.Thread(target=blocker.wait, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        obj.threads.append(thread)
        obj.folders = []
        obj.keys = FakeKey()
        with mock.patch.object(cr, "WAIT_LIMIT", 0.3):
            done = cr.Harness.close(obj)
        self.assertTrue(any(f.startswith("thread_end_unconfirmed") for f in done.failures))
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})
        blocker.set()

    def test_close_reports_fixed_failure_when_closed_getter_raises_oserror_once(self):
        obj = FakeCloseObj()

        class OnceRaisingOSErrorConn:
            def __init__(self):
                self.raised = False
                self.close_called = False

            def close(self):
                self.close_called = True

            @property
            def closed(self):
                if not self.raised:
                    self.raised = True
                    raise OSError("closed getter failure")
                return True
        conn = OnceRaisingOSErrorConn()
        obj.connections = [conn]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertTrue(conn.close_called)
        self.assertEqual(done.interrupts, [])
        self.assertIn("connection_state_failed", done.failures)
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})

    def test_close_preserves_first_keyboard_interrupt_when_close_also_raises_system_exit(self):
        obj = FakeCloseObj()

        class RaisingGetterAndCloseConn:
            @property
            def closed(self):
                raise KeyboardInterrupt("closed getter interrupt")

            def close(self):
                raise SystemExit("close interrupt")
        conn = RaisingGetterAndCloseConn()
        obj.connections = [conn]
        obj.keys = FakeKey()
        done = cr.Harness.close(obj)
        self.assertEqual(len(done.interrupts), 2)
        self.assertIsInstance(done.interrupts[0], KeyboardInterrupt)
        self.assertIsInstance(done.interrupts[1], SystemExit)
        self.assertTrue(any(f.startswith("connection_state_interrupted") for f in done.failures))
        self.assertTrue(any(f.startswith("connection_close_interrupted") for f in done.failures))
        self.assertTrue(obj.keys.closed)
        self.assertEqual(obj.passwords, {})


# --- 6. P1 setting probe + whole logical DB comparison (plan 12절): fake PG/settings model only -----------------

class FakeProbeCursor:
    """Fake cursor stand-in for `make_status_probe`'s raw savepoint/probe/rollback statements: a fixed
    (fake) transaction-isolation / read-only pair, never a real connection."""

    def __init__(self, conn):
        self.conn = conn
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, *a):
        self.conn.sent.append(query)
        if self.conn.fail_on == query:
            raise RuntimeError("fake probe statement failure")
        if self.conn.interrupt_on == query:
            raise KeyboardInterrupt("fake probe interrupt")
        if query == cr.STATUS_PROBE_SQL:
            self._row = (self.conn.isolation, self.conn.read_only)
        return self

    def fetchone(self):
        return self._row


class FakeProbeConn:
    def __init__(self, isolation="repeatable read", read_only="on", fail_on=None, interrupt_on=None):
        self.sent: list = []
        self.isolation, self.read_only = isolation, read_only
        self.fail_on, self.interrupt_on = fail_on, interrupt_on

    def cursor(self, row_factory=None):
        return FakeProbeCursor(self)


class FakeProbeTracker:
    def __init__(self, conn):
        self._conn = conn

    def activate(self):
        pass


class StatusProbeMixin:
    """`cr.make_status_probe` on a fake, network-free raw connection only -- not real PostgreSQL."""

    def test_records_isolation_and_read_only_then_releases_savepoint(self):
        store: dict = {}
        conn = FakeProbeConn()
        cr.make_status_probe(store)(cr.READ, 1, FakeProbeTracker(conn))
        self.assertEqual(store["probe"], {"transaction_isolation": "repeatable read", "transaction_read_only": "on"})
        self.assertEqual(conn.sent, ["SAVEPOINT pg69_status_probe", cr.STATUS_PROBE_SQL,
                                     "RELEASE SAVEPOINT pg69_status_probe"])

    def test_skips_write_role_later_connection_numbers_and_a_second_call(self):
        store: dict = {}
        conn = FakeProbeConn()
        probe = cr.make_status_probe(store)
        probe(cr.WRITE, 1, FakeProbeTracker(conn))
        probe(cr.READ, 2, FakeProbeTracker(conn))
        self.assertEqual(conn.sent, [])
        probe(cr.READ, 1, FakeProbeTracker(conn))
        self.assertIn("probe", store)
        conn2 = FakeProbeConn()
        probe(cr.READ, 1, FakeProbeTracker(conn2))         # "probe" already in store: second call is a no-op
        self.assertEqual(conn2.sent, [])

    def test_ordinary_probe_error_is_recorded_not_raised_and_rollback_is_attempted(self):
        store: dict = {}
        conn = FakeProbeConn(fail_on=cr.STATUS_PROBE_SQL)
        cr.make_status_probe(store)(cr.READ, 1, FakeProbeTracker(conn))
        self.assertEqual(store["probe"], {"probe_error": "probe_failed", "rollback": "rolled_back_to_savepoint"})
        self.assertIn("ROLLBACK TO SAVEPOINT pg69_status_probe", conn.sent)

    def test_probe_interrupt_is_kept_and_raised_bare_after_the_rollback_is_tried(self):
        store: dict = {}
        conn = FakeProbeConn(interrupt_on=cr.STATUS_PROBE_SQL)
        with self.assertRaises(KeyboardInterrupt) as caught:
            cr.make_status_probe(store)(cr.READ, 1, FakeProbeTracker(conn))
        self.assertIsNone(caught.exception.__cause__)
        self.assertEqual(store["probe"]["probe_error"], "probe_interrupted")
        self.assertEqual(store["probe"]["rollback"], "rolled_back_to_savepoint")
        self.assertIn("ROLLBACK TO SAVEPOINT pg69_status_probe", conn.sent)


class HandOverOrderMixin:
    """The probe through the SAME `counted_connector`/`RunScopes` machinery the real run uses, with a
    fake `real` connector and a fake tracked connection -- never a real PostgreSQL connection."""

    def test_event_order_is_body_then_probe_then_one_original_exit(self):
        order: list = []
        store: dict = {}
        probe_conn = FakeProbeConn()
        probe_tracker = FakeProbeTracker(probe_conn)
        trackers: list = []

        def real(inputs, expected, driver):
            def connector(*, read_only=False):
                trackers.append(probe_tracker)

                class Ctx:
                    def __enter__(self):
                        order.append("body_begin")
                        return "product"

                    def __exit__(self, *exc):
                        order.append(f"original_exit(probe_ran={'probe' in store})")
                        return False
                return Ctx()
            return connector

        counts = cr.Counts()
        before_exit = cr.make_status_probe(store)
        factory = lay.counted_connector(cr.LAYOUT, counts, trackers, None, None, real, None, before_exit)
        connect = factory(SimpleNamespace(command="status"), None, None)
        with connect(read_only=True) as product:
            order.append("product_body")
            self.assertEqual(product, "product")
        self.assertEqual(order, ["body_begin", "product_body", "original_exit(probe_ran=True)"])
        self.assertIn("probe", store)


# --- database_facts: fake admin connection, real `lay.content_hashes` -------------------------------------------

class FakeFactsCursor:
    def __init__(self, rows: list):
        self._rows = list(rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeFactsConn:
    def __init__(self, sequence_names, sequence_values):
        self.sent: list = []
        self.rollback_called = False
        self.sequence_names = list(sequence_names)
        self.sequence_values = dict(sequence_values)

    def execute(self, query, *a):
        text = query.as_string(None) if hasattr(query, "as_string") else query
        self.sent.append(text)
        if text == cr.SEQUENCE_NAME_QUERY:
            return FakeFactsCursor([(n,) for n in self.sequence_names])
        if "last_value" in text:
            name = next(n for n in self.sequence_names if n in text)
            return FakeFactsCursor([self.sequence_values[name]])
        return FakeFactsCursor([(0, "d41d8cd98f00b204e9800998ecf8427e")])

    def rollback(self):
        self.rollback_called = True


class DatabaseFactsMixin:
    """`cr.Harness.database_facts` on a fake admin connection only -- `lay.content_hashes` runs for real."""

    def fake_harness(self, conn):
        return SimpleNamespace(pid=4242)

    def test_reads_isolation_first_then_tables_then_quoted_sequence_identifiers_no_writes(self):
        conn = FakeFactsConn(["srs_migration_runs_id_seq", "users_id_seq"],
                             {"srs_migration_runs_id_seq": (7, True), "users_id_seq": (3, False)})
        h = self.fake_harness(conn)
        with mock.patch.object(cr, "admin", lambda db, pid, autocommit=True: contextlib.nullcontext(conn)):
            facts = cr.Harness.database_facts(h, "p1")
        self.assertEqual(conn.sent[0], "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        self.assertTrue(conn.rollback_called)
        self.assertEqual(facts["sequences"], {"srs_migration_runs_id_seq": [7, True], "users_id_seq": [3, False]})
        self.assertEqual(set(facts["sequence_names"]), {"srs_migration_runs_id_seq", "users_id_seq"})
        self.assertTrue(facts["tables"])
        for text in conn.sent:
            self.assertNotIn("nextval", text.lower())
            self.assertNotIn("setval", text.lower())
        self.assertTrue(any('"srs_migration_runs_id_seq"' in t or "srs_migration_runs_id_seq" in t
                            for t in conn.sent if "last_value" in t))

    def test_refuses_a_check_id_outside_check_db_before_any_admin_connection(self):
        h = self.fake_harness(None)
        with mock.patch.object(cr, "admin", forbidden):
            with self.assertRaises(cr.CheckFailed) as caught:
                cr.Harness.database_facts(h, "not-a-real-check")
            self.assertEqual(caught.exception.kind, "harness_defect")


# --- p1: the ACTUAL check function with a fake Harness model, real record save/reread ---------------------------

def status_result(*, probe=None, out=None, code=0):
    counts = cr.Counts()
    counts.created[cr.READ] = 1
    counts.handed[cr.READ] = 1
    return {"out": out or {"state": "completed", "results": {"applied": 2}}, "code": code, "counts": counts,
           "settings_probe": probe if probe is not None else {"transaction_isolation": "repeatable read",
                                                               "transaction_read_only": "on"}}


class FakeP1Harness:
    """Fake, labelled PG/settings model for `cr.p1_repeated_completed_query`: a real on-disk `g.Record`
    (subcase/record readback is real), fake `status` / `database_facts` / `state_admin`."""

    def __init__(self, folder, *, facts_sequence, status_sequence, state_admin_value, baseline_value):
        self.rec = g.Record(folder)
        self.cases = {"p1": SimpleNamespace()}
        self.evidence = {"baseline": {"p1": baseline_value}}
        self._facts = list(facts_sequence)
        self._statuses = list(status_sequence)
        self._state_admin_value = state_admin_value

    def database_facts(self, check_id):
        return self._facts.pop(0)

    def status(self, case, *, clock, hooks=None, settings_probe=False):
        return self._statuses.pop(0)

    def state_admin(self, case):
        return self._state_admin_value


class P1CheckMixin:
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="pg69_p1_fake_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def facts(self, **over):
        base = {"tables": {"users": [1, "h"]}, "sequences": {"users_id_seq": [1, True]},
               "sequence_names": ["users_id_seq"]}
        base.update(over)
        return base

    def test_normal_pass_records_every_required_subcase(self):
        f = self.facts()
        h = FakeP1Harness(self.folder, facts_sequence=[f, f, f, f],
                          status_sequence=[status_result(), status_result()],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        out = cr.p1_repeated_completed_query(h)
        self.assertEqual(out, {"calls": 2})
        saved = json.loads((self.folder / "record.json").read_text(encoding="utf-8"))
        names = {e["name"] for e in saved["events"] if e.get("kind") == "subcase" and e.get("check") == "p1"}
        self.assertTrue(names.issuperset({"call_0_settings_probe", "call_1_settings_probe",
                                         "call_0_settings_repeatable", "call_1_settings_repeatable",
                                         "call_0_database_unchanged", "call_1_database_unchanged",
                                         "database_unchanged_across_calls", "no_reprocessing"}))

    def test_changed_setting_between_calls_fails(self):
        f = self.facts()
        other_probe = {"transaction_isolation": "read committed", "transaction_read_only": "on"}
        h = FakeP1Harness(self.folder, facts_sequence=[f, f, f, f],
                          status_sequence=[status_result(), status_result(probe=other_probe)],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        with self.assertRaises(cr.CheckFailed):
            cr.p1_repeated_completed_query(h)

    def test_probe_error_or_missing_fails(self):
        f = self.facts()
        h = FakeP1Harness(self.folder, facts_sequence=[f, f, f, f],
                          status_sequence=[status_result(probe={"probe_error": "probe_failed"}), status_result()],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        with self.assertRaises(cr.CheckFailed):
            cr.p1_repeated_completed_query(h)

    def test_table_hash_change_between_before_and_after_fails(self):
        f = self.facts()
        changed = self.facts(tables={"users": [2, "other"]})
        h = FakeP1Harness(self.folder, facts_sequence=[f, changed, f, f],
                          status_sequence=[status_result(), status_result()],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        with self.assertRaises(cr.CheckFailed):
            cr.p1_repeated_completed_query(h)

    def test_sequence_value_advancement_fails(self):
        f = self.facts()
        advanced = self.facts(sequences={"users_id_seq": [2, True]})
        h = FakeP1Harness(self.folder, facts_sequence=[f, f, f, advanced],
                          status_sequence=[status_result(), status_result()],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        with self.assertRaises(cr.CheckFailed):
            cr.p1_repeated_completed_query(h)

    def test_sequence_name_set_change_fails(self):
        f = self.facts()
        renamed = self.facts(sequence_names=["other_id_seq"], sequences={"other_id_seq": [1, True]})
        h = FakeP1Harness(self.folder, facts_sequence=[f, f, renamed, renamed],
                          status_sequence=[status_result(), status_result()],
                          state_admin_value={"runs": []}, baseline_value={"runs": []})
        with self.assertRaises(cr.CheckFailed):
            cr.p1_repeated_completed_query(h)


class NormalRead(StatusProbeMixin, HandOverOrderMixin, DatabaseFactsMixin, P1CheckMixin, unittest.TestCase):
    """PG69 P1 (plan 12절): the setting probe, its integration with the common `before_exit` hook,
    `database_facts` and the ACTUAL `p1_repeated_completed_query` check, composed from the fixture
    mixins above -- one `unittest.TestCase`, no test method duplicated across classes."""


# --- 8. ApprovalPaths: real P6 rejection-path trace through the ACTUAL `cr.Harness` helpers and
# `cr.p6_fixed_refusal_codes` -- real signing (`sigtests.Keys`), real `op.run_synthetic_preflight`, never a
# fake verifier. No PostgreSQL, admin or process access anywhere below: `cr.Harness.__init__`/`start()` are
# never called (the fixture builds the object with `object.__new__` and sets its own synthetic, file-only
# target); `state_admin` is a fake (allowed by the plan); a real product connection would hit the blocked
# `psycopg.connect` and fail the test. ----------------------------------------------------------------------

from datetime import timedelta  # noqa: E402
from urllib.parse import quote  # noqa: E402


SAFE_ENV = ("APP_ENV", "DATABASE_URL", "PYTHON_DOTENV_DISABLED")


def _pin_safe_env(case: unittest.TestCase) -> None:
    """Pinned/restored before any app import can happen (none should here; defensive only): the EXACT
    previous value of each of the three variables is restored, registered BEFORE the override."""
    saved = {k: os.environ.get(k) for k in SAFE_ENV}

    def restore():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    case.addCleanup(restore)
    os.environ.update(APP_ENV="test", DATABASE_URL="sqlite:///:memory:", PYTHON_DOTENV_DISABLED="1")


def _approval_paths_case(h: cr.Harness, check_id: str):
    """A genuine, fully real-signed inquiry + apply approval pair for `check_id`, built the same way as
    `cr.Harness.case()` except that the dry-run PRODUCT read (which needs a real connection) is replaced
    by a fixed synthetic `product_fingerprint` / `artifact_sha256` fed into the SAME real
    `op.run_synthetic_preflight` call `case()` itself uses to print the job plan embedded in the apply
    approval. Never a hand-built plan string, never a fake preflight."""
    db = cr.CHECK_DB[check_id]
    ids = h.target["synthetic"]["a"]
    uid = ids["user_id"]
    keys = cr.card_keys(ids)
    req = cr.cli.make_request(uid, cr.RUN_KEY, [r for k, _, r in keys if k == "personal"], [])
    read_exp, write_exp = cr.expected_profiles(db)
    read_profile = cr.pv.expected_profile_fingerprint(read_exp, role=cr.READ, access="read")
    write_profile = cr.pv.expected_profile_fingerprint(write_exp, role=cr.WRITE, access="write")
    folder = h.deploy()
    manifest = cr.pf.manifest_doc(h.files())
    target_obs = cr.op.TargetObservation(host=cr.g.HOST, port=cr.T.port, database=db, server_major=18,
                                         identity_value=h.target["databases"][db]["identity_value"])
    db_identity = cr.pf.db_identity(target_obs)
    suffix = req.run_key[-6:] or "000000"
    read_step = {"command": "dry_run", "access": "read", "role": cr.READ, "profile": read_profile}
    inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": f"inq-approval-paths-{check_id}-{suffix}",
                   "supersedes": None, "purpose": "synthetic", "alias": "synthetic-primary",
                   "db_identity": db_identity, "manifest": cr.om.manifest_fingerprint(manifest),
                   "tool": "srs_migrate", "steps": [read_step], "accounts": [uid], "max_accounts": 1,
                   "job": {"key": req.run_key, "inputs": cr.cli.job_inputs(req)},
                   "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
                   "approved_by": "synthetic signer"}
    inquiry = json.dumps(inquiry_doc).encode()
    root = os.path.join(folder, "ops", "tls", "root.pem")

    def dsn(role):
        return (f"postgresql://{role}:fixture-only@{cr.g.HOST}:{cr.T.port}/{db}?sslmode=verify-full"
                f"&sslrootcert={quote(root, safe='')}")
    common = dict(mode="synthetic", manifest=manifest, manifest_signature=h.sign(manifest, "manifest"),
                  deploy_root=folder, account_id=uid, job_key=req.run_key, job_inputs=cr.cli.job_inputs(req),
                  target=target_obs, environment={"PATH": "C:/Windows"},
                  trust=cr.op.SyntheticTrust(h.allowed, b"", cr.sigtests.PRINCIPAL), now=cr.T0)
    inquiry_inputs = cr.op.PreflightInput(approval=inquiry, approval_signature=h.sign(inquiry, "approval"),
                                          command="dry_run", args={}, product_fingerprint=None,
                                          connection=cr.op.ConnectionObservation(profile=read_profile, read_only=True),
                                          secret_dsn=dsn(cr.READ), **common)
    # NON-None, like the real dry-run-bound A0 `cr.Harness.case()` builds: this fixture's `a0`/plan must
    # stay fixed and untouched by `apply_approval_as_status` (P6), which now builds its OWN separate
    # plan from its OWN status inquiry -- never this value, never this approval's bytes.
    product_fingerprint = cr.sha(b"approval-paths-synthetic-product")
    artifact_sha256 = cr.sha(b"approval-paths-synthetic-artifact")
    printed = cr.op.run_synthetic_preflight(dataclasses.replace(
        inquiry_inputs, product_fingerprint=product_fingerprint, artifact_sha256=artifact_sha256)).job_plan
    ev0 = h.write_evidence(folder, "evidence0", db_identity, uid, f"bkp-approval-paths-{check_id}-{suffix}")
    status_step = {"command": "status", "access": "read", "role": cr.READ, "profile": read_profile}
    a0_doc = dict(inquiry_doc, kind="apply", approval_id=f"app-approval-paths-{check_id}-{suffix}",
                  plan={str(uid): printed},
                  based_on={"approval_id": inquiry_doc["approval_id"], "sha256": cr.sha(inquiry)},
                  steps=[read_step, status_step, {"command": "apply", "access": "write", "role": cr.WRITE,
                                                  "profile": write_profile, "args": {"batch_size": "2"}}],
                  format_version=3, backup_evidence={"sha256": cr.sha(Path(ev0[0]).read_bytes())})
    a0 = json.dumps(a0_doc).encode()
    case = cr.Case(check_id=check_id, db=db, keys=keys, request=req, plan=None, plan_path="", folder=folder,
                   manifest=manifest, dry_run_inquiry=inquiry, a0=a0, first_write=None, first_read=None,
                   initial_evidence=ev0, read_expected=read_exp, write_expected=write_exp, read_profile=read_profile,
                   write_profile=write_profile, db_identity=db_identity, dsn=dsn, common=common, batch_size=2)
    return case, product_fingerprint, artifact_sha256


class ApprovalPaths(unittest.TestCase):
    """Real `cr.Harness` helpers (`sign`, `deploy`, `write_evidence`, `status_raw`, `apply_approval_as_status`,
    `read_only_inputs`) and the ACTUAL `cr.p6_fixed_refusal_codes`, on a Harness built only from this
    fixture's own synthetic, file-based target (never `Harness.__init__`/`start()`, never a real server).
    `cr.sigtests.Keys` runs for real; every PostgreSQL/admin/process entry point stays blocked."""

    def setUp(self):
        _pin_safe_env(self)
        # `subprocess.Popen`/`.run` stay REAL here: `cr.sigtests.Keys()` needs the real `ssh-keygen` binary
        # (never a fake verifier). Every PostgreSQL/admin/process/TLS/product-read entry point stays
        # blocked -- `cli.read_status` must never be reached by any P6 trial.
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(g, "listener_pids", forbidden),
                      mock.patch.object(g, "admin_connect", forbidden), mock.patch.object(g, "postmaster_pid", forbidden),
                      mock.patch.object(g, "single_run", forbidden), mock.patch.object(lay.real, "make_tls", forbidden),
                      mock.patch.object(lay.base, "run", forbidden), mock.patch.object(cr.cli, "read_status", forbidden)):
            patch.start()
            self.addCleanup(patch.stop)
        # Every owned resource gets its cleanup registered the moment it is created, never after the
        # whole fixture finishes: a later failure in this same `setUp` still cleans up what came before.
        # `h.deploy()` (used by `_approval_paths_case`) makes folders OUTSIDE `folder_root` (runner
        # `Harness.deploy`, 474-486), so cleanup goes through the REAL `Harness.close` (its own
        # identity-checked deletion of exactly the folders it owns, plus keys/secrets), never a new
        # deletion routine -- the outer temp `folder_root` is only removed AFTER `close()` has run.
        self.h = object.__new__(cr.Harness)
        self.h.folder_root = Path(tempfile.mkdtemp(prefix="pg69_approval_paths_"))
        self.addCleanup(shutil.rmtree, self.h.folder_root, True)          # registered first: runs LAST
        self.h.rec = g.Record(self.h.folder_root)
        self.h.target = {"postmaster_pid": 999999,
                         "synthetic": {"a": {"user_id": 1, "personal": {"p1": 101, "p2": 102}}},
                         "databases": {db: {"identity_value": f"synthetic-{db}"} for db in cr.CHECK_DB.values()}}
        self.h.target_bytes = json.dumps(self.h.target).encode()
        (self.h.rec.folder / "target.json").write_bytes(self.h.target_bytes)
        self.h.pid = self.h.target["postmaster_pid"]
        self.h.keys, self.h.allowed = None, None
        self.h.passwords, self.h.folders, self.h.evidence, self.h.connections = {}, [], {}, []
        self.h.cases, self.h.pauses, self.h.threads = {}, [], []
        self.h.ca_pem = lambda: b"fixture-only-not-a-real-ca"   # no real cluster: no real ca.crt on disk

        def close_cleanly():
            done = self.h.close()
            self.assertEqual((done.failures, done.interrupts), ([], []))
        self.addCleanup(close_cleanly)                                    # registered later: runs FIRST
        self.h.keys = cr.sigtests.Keys()                       # Keys close is through `h.close` ONLY (no
                                                                 # duplicate registration); runs even if
                                                                 # later setUp lines below raise.
        self.h.allowed = self.h.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.h.passwords = {role: "fixture-only-password" for role in cr.BUSINESS_ROLES}
        self.case, self.product_fingerprint, self.artifact_sha256 = _approval_paths_case(self.h, "p6")
        self.h.cases["p6"] = self.case
        state_patch = mock.patch.object(self.h, "state_admin", lambda case: {"fixed": True})
        state_patch.start()
        self.addCleanup(state_patch.stop)

    def test_valid_signed_inquiry_control_is_genuinely_preflight_valid(self):
        now = cr.T0 + timedelta(minutes=5)
        inputs, _, _ = self.h.read_only_inputs("p6", self.case.request, now=now)
        matched = cr.op.run_synthetic_preflight(inputs)
        self.assertEqual(matched.kind, "inquiry")
        self.assertEqual(matched.command, "status")

    def test_apply_control_is_independently_preflight_valid(self):
        shared = dict(self.case.common, approval=self.case.a0, approval_signature=self.h.sign(self.case.a0, "approval"),
                      inquiry=self.case.dry_run_inquiry,
                      inquiry_signature=self.h.sign(self.case.dry_run_inquiry, "approval"),
                      product_fingerprint=self.product_fingerprint, artifact_sha256=self.artifact_sha256)
        apply_inputs = cr.op.PreflightInput(command="apply", args={"batch_size": "2"},
                                            secret_dsn=self.case.dsn(cr.WRITE),
                                            connection=cr.op.ConnectionObservation(profile=self.case.write_profile,
                                                                                  read_only=False),
                                            **shared)
        matched = cr.op.run_synthetic_preflight(apply_inputs)
        self.assertEqual((matched.kind, matched.command), ("apply", "apply"))

    def test_p6_fixed_refusal_codes_real_routes_trace_and_zero_counts(self):
        original_a0 = self.case.a0
        cr.p6_fixed_refusal_codes(self.h)
        self.assertEqual(self.case.a0, original_a0)      # the job's real A0 (non-None product/artifact) untouched
        saved = json.loads((self.h.rec.folder / "record.json").read_text(encoding="utf-8"))
        subcases = {(e["check"], e["name"]): e["ok"] for e in saved["events"] if e.get("kind") == "subcase"}
        for label, _ in cr.P6_CASES:
            self.assertTrue(subcases[("p6", label)], label)
            self.assertTrue(subcases[("p6", f"{label}_no_connection")], label)
            self.assertTrue(subcases[("p6", f"{label}_trace")], label)
        self.assertTrue(subcases[("p6", "unchanged")])

    def test_wrong_early_refusal_makes_p6_itself_fail_and_stop(self):
        """Regression: a mismatched `apply_approval_as_status` fixture (so the real preflight stops at
        the earlier `request_mismatch` input check instead of the intended kind gate) must make
        `cr.p6_fixed_refusal_codes` ITSELF raise, and later trials ("wrong_tool" etc.) must never run."""
        real_apply_approval_as_status = self.h.apply_approval_as_status

        def mismatched(case, *, now):
            other_req = cr.cli.make_request(case.request.account_id, case.request.run_key, [9999], [])
            return dataclasses.replace(real_apply_approval_as_status(case, now=now),
                                       job_inputs=cr.cli.job_inputs(other_req))
        patch = mock.patch.object(self.h, "apply_approval_as_status", mismatched)
        patch.start()
        self.addCleanup(patch.stop)
        with self.assertRaises(cr.CheckFailed):
            cr.p6_fixed_refusal_codes(self.h)
        saved = json.loads((self.h.rec.folder / "record.json").read_text(encoding="utf-8"))
        names = {e["name"] for e in saved["events"] if e.get("kind") == "subcase" and e.get("check") == "p6"}
        self.assertNotIn("wrong_tool", names)             # the trial after the broken one never ran

    def test_cleanup_leaves_no_owned_keys_or_deploy_folders(self):
        """Regression: every path this fixture owns (the real temporary OpenSSH key folder, EVERY
        `h.deploy()` folder made outside `folder_root`) is gone once `doCleanups()` runs `h.close()`,
        and the in-memory secrets are cleared -- never a preexisting/unrelated folder."""
        key_folder = Path(self.h.keys.folder)
        deploy_folders = [Path(entry["path"]) for entry in self.h.folders]
        self.assertTrue(key_folder.exists())
        self.assertTrue(deploy_folders)
        self.assertTrue(all(p.exists() for p in deploy_folders))
        self.doCleanups()
        self.assertFalse(key_folder.exists())
        self.assertTrue(all(not p.exists() for p in deploy_folders))
        self.assertEqual(self.h.passwords, {})


# --- 9. G1 fixture move + whole-database baseline (plan 173절): REAL g1_gate / g1_build_p5_fixtures /
# g1_build_p10_block / post_check / p5 / p10 control flow, fake case/first_apply/database_facts/admin only ------

class FakeG1Case:
    def __init__(self, check_id, db, run_key, account_id, account="a"):
        self.check_id, self.db, self.run_key, self.account = check_id, db, run_key, account
        self.request = SimpleNamespace(account_id=account_id, run_key=run_key or cr.RUN_KEY)


class FakeAdminCursorResult:
    def __init__(self, rowcount=1, one=None):
        self.rowcount, self._one = rowcount, one

    def fetchone(self):
        return self._one


class G1FixtureBaselineMixin:
    """A plain mixin (never a `TestCase` itself -- `G1FixturesAndBaseline(G1FixtureBaselineMixin, Blocked)`
    below is the ONLY discoverable class, so every test body here is collected exactly once) driving the
    REAL `cr.g1_gate` / `cr.g1_build_p5_fixtures` / `cr.g1_build_p10_block` / `cr.p5_not_started_variants` /
    `cr.p10_active_write_block_ignored` control flow end to end: fixed fake `case` / `first_apply` /
    `state_admin` / `database_facts` / `row_text` backed by ONE shared in-memory model, a real on-disk
    `g.Record` (event save + readback is real). `cr.admin_mutation_guard` is the REAL function (only
    `cr.ADMIN_CHANGES_APPROVED` is patched to `True`, restored by `addCleanup`, and stays `None` in the
    saved source); `cr.admin` is faked -- a strict dispatcher over the model, validating db/pid/table/SQL/
    params before any mutation, that rejects any unrecognized or malformed request, never a silent no-op.
    `h.status_raw`/`h.status` reuse the REAL `cli.run_status` -> `cli.read_status` bounded adapter
    (`real_run_status`/`FakeStatusConnection`, section 10 below) against the SAME model rows G1 built;
    only `cli._admit`/`cli._timed_connector` stay stubbed there, never preflight/signing/provider
    machinery. `Counts` returned by `h.status`/`h.status_raw` are the SAME object `FakeStatusConnection`/
    `real_run_status` genuinely incremented at construction/connect/execute time, never a value assigned
    after the fact -- this class still reaches no real PostgreSQL, admin connection, TLS or process
    (`Blocked.setUp`, inherited by the concrete `G1FixturesAndBaseline` class)."""

    def setUp(self):
        super().setUp()
        self.folder = Path(tempfile.mkdtemp(prefix="pg69_g1_fixture_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.order: list = []
        self.model = None
        approved = mock.patch.object(cr, "ADMIN_CHANGES_APPROVED", True)
        approved.start()
        self.addCleanup(approved.stop)

        p10_insert = ("INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
                     "active_user_id, run_watermark, changes_started, created_at) VALUES "
                     "(%s, 'srs_recovery', %s, %s, 'active', %s, 0, 0, %s) RETURNING id")
        p2_conflict_update = ("UPDATE vocab_items SET correct_count = correct_count + 1 "
                              "WHERE id = %s AND user_id = %s")
        p5_scope_update = "UPDATE srs_migration_runs SET scope_json = %s WHERE id = %s"

        @contextlib.contextmanager
        def fake_admin(db, pid, autocommit=True):
            self.order.append(("admin", db))
            model = self.model
            if db not in cr.CHECK_DB.values():
                raise AssertionError(f"fake admin reached outside the closed check DBs: {db!r}")
            if pid != 999:
                raise AssertionError(f"fake admin reached with an unexpected pid: {pid!r}")

            class Conn:
                def execute(self2, query, params=None):
                    if isinstance(query, tuple) and query and query[0] == "RESTORE":
                        _, table, row_data = query
                        if db != cr.CHECK_DB["p5"] or table != "srs_migration_runs":
                            raise AssertionError("fake RESTORE reached outside the P5 scope-corruption fixture")
                        bucket = model["runs"].get(db, {})
                        matched = bucket.get("completed-replay-p5-corrupt")
                        if matched is None or matched["id"] != row_data["id"] or set(matched) != set(row_data):
                            return FakeAdminCursorResult(rowcount=0)
                        bucket["completed-replay-p5-corrupt"] = dict(row_data)
                        return FakeAdminCursorResult(rowcount=1)
                    text = query if isinstance(query, str) else str(query)
                    if text == p10_insert:
                        if db != cr.CHECK_DB["p10"]:
                            raise AssertionError("fake P10 block INSERT reached on the wrong db")
                        uid, recovery_key, grant_hash, active_uid, created_at = params
                        expected = (1, "pg69-p10-recovery", hashlib.sha256(b"synthetic-grant").hexdigest(), 1,
                                   "2026-10-30T00:00:00+00:00")
                        if (uid, recovery_key, grant_hash, active_uid, created_at) != expected:
                            raise AssertionError(f"unexpected P10 block INSERT params: {params!r}")
                        existing = model["runs"].get(db, {}).get(cr.RUN_KEY)
                        if existing is None or existing.get("status") != "completed":
                            raise AssertionError("P10 block INSERT reached before its completed run fixture exists")
                        block_id = next(model["_block_seq"])
                        model["blocks"].setdefault(db, {})[block_id] = {
                            "id": block_id, "user_id": uid, "status": "active", "active_user_id": active_uid}
                        return FakeAdminCursorResult(rowcount=1, one=(block_id,))
                    if text == p2_conflict_update:
                        if db != cr.CHECK_DB["p2"]:
                            raise AssertionError("fake P2 conflict UPDATE reached on the wrong db")
                        card_id, user_id = params
                        row = model["vocab_items"].get(db, {}).get(card_id)
                        if row is None or row["user_id"] != user_id:
                            return FakeAdminCursorResult(rowcount=0)
                        row["correct_count"] += 1
                        return FakeAdminCursorResult(rowcount=1)
                    if text == p5_scope_update:
                        if db != cr.CHECK_DB["p5"]:
                            raise AssertionError("fake P5 scope UPDATE reached on the wrong db")
                        new_scope, run_id = params
                        bucket = model["runs"].get(db, {})
                        matched = bucket.get("completed-replay-p5-corrupt")
                        if matched is None or matched["id"] != run_id:
                            return FakeAdminCursorResult(rowcount=0)
                        matched["scope_json"] = new_scope
                        return FakeAdminCursorResult(rowcount=1)
                    raise AssertionError(f"unexpected fake admin SQL (G1 fixture dispatcher): {text!r}")
            yield Conn()
        patch2 = mock.patch.object(cr, "admin", fake_admin)
        patch2.start()
        self.addCleanup(patch2.stop)

    def fake_harness(self):
        class H:
            pass
        h = H()
        h.rec = g.Record(self.folder)
        h.cases, h.evidence, h.pid = {}, {}, 999
        h.target = {"synthetic": {"a": {"user_id": 1, "personal": {"p1": 101, "p2": 102}},
                                  "b": {"user_id": 2, "personal": {"p1": 201, "p2": 202}}}}
        model = {"runs": {}, "snapshots": {}, "blocks": {},
                "vocab_items": {cr.CHECK_DB["p2"]: {101: {"user_id": 1, "correct_count": 2}}},
                "_run_seq": itertools.count(1), "_block_seq": itertools.count(777, 1)}
        self.model = model

        cr.ar.fix_app_environment()
        from app.srs.engine import DEFAULT_CONFIG
        config_version = DEFAULT_CONFIG.config_version

        def reduced_scope(uid, cards):
            request_bytes = json.dumps([[k, r] for k, r in cards], separators=(",", ":")).encode("ascii")
            return json.dumps({"format": 2, "user_id": uid, "config_version": config_version,
                              "cards": [{"kind": k, "ref_id": r} for k, r in cards],
                              "request_sha256": hashlib.sha256(request_bytes).hexdigest()})

        def case(check_id, *, account="a", batch_size=2, run_key=None, cards=None):
            self.order.append(("case", check_id, run_key))
            account_id = h.target["synthetic"][account]["user_id"]
            db = cr.CHECK_DB[check_id]
            c = FakeG1Case(check_id, db=db, run_key=run_key, account_id=account_id, account=account)
            if check_id in ("p5", "p10"):
                personal = h.target["synthetic"][account]["personal"]
                c.request = cr.cli.make_request(account_id, c.request.run_key, [personal["p1"], personal["p2"]], [])
            return c

        def first_apply(case_, *, handover=None):
            self.order.append(("first_apply", case_.check_id, case_.run_key))
            if handover is not None:
                handover(cr.WRITE, 1, SimpleNamespace())
            if case_.run_key == cr.CONFLICT_RUN_KEY:
                return {"phase": "completed", "results": {"applied": 1, "conflict": 1}}, 5
            if case_.run_key == cr.BLOCKED_RUN_KEY:
                return {"phase": "completed", "results": {"applied": 1, "blocked": 1}}, 5
            if case_.check_id in ("p5", "p10"):
                ids = h.target["synthetic"][case_.account]
                run_cards = [("personal", ids["personal"]["p1"]), ("personal", ids["personal"]["p2"])]
                run_id = next(model["_run_seq"])
                scope = reduced_scope(case_.request.account_id, run_cards)
                summary = json.dumps({"cursor": 2, "results": [
                    {"kind": "personal", "ref_id": run_cards[0][1], "result": "applied"},
                    {"kind": "personal", "ref_id": run_cards[1][1], "result": "applied"}]})
                row = {"id": run_id, "mode": "apply", "status": "completed", "scope_json": scope,
                      "config_version": config_version, "summary_json": summary,
                      "started_at": "2026-10-21T12:00:00+00:00", "finished_at": "2026-10-21T12:05:00+00:00"}
                model["runs"].setdefault(case_.db, {})[case_.request.run_key] = row
                snaps = [{"id": next(model["_run_seq"]), "user_id": case_.request.account_id,
                         "card_kind": "personal", "card_ref": run_cards[0][1], "run_id": run_id},
                        {"id": next(model["_run_seq"]), "user_id": case_.request.account_id,
                         "card_kind": "personal", "card_ref": run_cards[1][1], "run_id": run_id}]
                model["snapshots"].setdefault(case_.db, {})[case_.request.run_key] = snaps
            return {"phase": "completed", "results": {"applied": 2}}, 0

        def state_admin(case_):
            if case_.check_id in ("p5", "p10"):
                row = model["runs"].get(case_.db, {}).get(case_.request.run_key)
                snaps = model["snapshots"].get(case_.db, {}).get(case_.request.run_key, [])
                return {"runs": [dict(row)] if row else [], "snapshots": [dict(s) for s in snaps]}
            return {"runs": [{"id": 1}], "snapshots": []}

        def database_facts(check_id):
            self.order.append(("database_facts", check_id))
            db = cr.CHECK_DB[check_id]
            payload = json.dumps({"runs": sorted(model["runs"].get(db, {}).items()),
                                  "snapshots": sorted(model["snapshots"].get(db, {}).items()),
                                  "blocks": sorted(model["blocks"].get(db, {}).items())},
                                 sort_keys=True, default=str).encode()
            digest = hashlib.md5(payload).hexdigest()
            moved = {"srs_migration_runs", "srs_migration_snapshots", "account_write_blocks"}
            empty = hashlib.md5(b"").hexdigest()
            tables = {t: ([1, digest] if t in moved else [0, empty]) for t in lay.BUSINESS_TABLES}
            return {"tables": tables, "sequences": {"users_id_seq": [1, True]},
                   "sequence_names": ["users_id_seq"], "check_id": check_id}

        def row_text(db, table, row_id):
            if table == "account_write_blocks":
                row = model["blocks"].get(db, {}).get(row_id)
                return dict(row) if row else None
            if table == "srs_migration_runs":
                for row in model["runs"].get(db, {}).values():
                    if row["id"] == row_id:
                        return dict(row)
                return None
            return {"id": row_id, "user_id": 1, "status": "active", "active_user_id": 1}

        def restore_row(conn, table, row):
            return conn.execute(("RESTORE", table, dict(row)), None).rowcount

        def sessions():
            return {"open": 0, "idle_in_transaction": 0}

        def connection_for(case_db, request, *, hooks=None, fetch_hooks=None, counts=None):
            row = model["runs"].get(case_db, {}).get(request.run_key)
            snaps = model["snapshots"].get(case_db, {}).get(request.run_key, []) if row else []
            return FakeStatusConnection(request.run_key, row, snaps, hooks=hooks, fetch_hooks=fetch_hooks,
                                        counts=counts)

        def read_only_inputs(check_id, request, *, now, **kwargs):
            """Bounded P5 adapter (real reader only): the real preflight/signing stack never runs here
            (`status_raw` below bypasses it exactly like `real_run_status`), so only a placeholder
            `(inputs, expected, dsn)` triple is needed -- `status_raw` uses `request` itself, not these."""
            return SimpleNamespace(), SimpleNamespace(), (lambda role: "")

        def status_raw(request, inputs, read_exp, *, clock, rc_variant=False, hooks=None, fetch_hooks=None,
                       preflight_trace=None):
            counts = cr.Counts()
            connection = connection_for(cr.CHECK_DB["p5"], request, hooks=hooks, fetch_hooks=fetch_hooks,
                                       counts=counts)
            out, code = real_run_status(request, connection, clock=clock, counts=counts)
            return {"out": out, "code": code, "counts": counts, "trackers": []}

        def status(case_, *, clock, hooks=None, rc_variant=False, fetch_hooks=None, trackers=None,
                   now_for_inputs=None, settings_probe=False):
            counts = cr.Counts()
            connection = connection_for(case_.db, case_.request, hooks=hooks, fetch_hooks=fetch_hooks, counts=counts)
            out, code = real_run_status(case_.request, connection, clock=clock, counts=counts)
            return {"out": out, "code": code, "counts": counts, "trackers": []}

        h.case, h.first_apply, h.state_admin = case, first_apply, state_admin
        h.database_facts, h.row_text, h.sessions = database_facts, row_text, sessions
        h.restore_row, h.status_raw, h.status = restore_row, status_raw, status
        h.read_only_inputs = read_only_inputs
        h.model, h._connection_for = model, connection_for          # test introspection only, never read by cr
        return h

    def test_g1_gate_builds_p5_and_p10_fixtures_before_the_whole_database_baseline(self):
        h = self.fake_harness()
        out = cr.g1_gate(h)
        self.assertEqual(set(h.evidence["db_baseline"]), set(cr.PLANNED))
        self.assertEqual(out["database_baseline_checks"], sorted(cr.PLANNED))
        self.assertIn("p5:other", h.cases)
        self.assertIn("p5:corrupt", h.cases)
        self.assertIn("p10_block", h.evidence)
        self.assertEqual(h.evidence["p10_block"], {"id": 777, "row": {"id": 777, "user_id": 1, "status": "active",
                                                                        "active_user_id": 1}})
        last_fixture_index = max(i for i, e in enumerate(self.order) if e[0] in ("case", "first_apply", "admin"))
        first_facts_index = min(i for i, e in enumerate(self.order) if e[0] == "database_facts")
        self.assertLess(last_fixture_index, first_facts_index)
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        captured = next(e for e in saved["events"] if e.get("kind") == "database_baseline_captured")
        self.assertEqual(set(captured["checks"]), set(cr.PLANNED))

    def test_main_p5_body_never_creates_or_applies_a_run(self):
        """Main P5 only reads the two G1-built fixtures (acceptance 1/4): AT RUNTIME, after `g1_gate`
        already built them, `h.case`/`h.first_apply` are never reached by `cr.p5_not_started_variants`
        itself (never a source-text proxy for this)."""
        h = self.fake_harness()
        cr.g1_gate(h)

        def forbidden_case(*a, **k):
            raise AssertionError("h.case must not be called by main P5")

        def forbidden_first_apply(*a, **k):
            raise AssertionError("h.first_apply must not be called by main P5")
        h.case, h.first_apply = forbidden_case, forbidden_first_apply
        cr.p5_not_started_variants(h)          # completes fully without reaching either

    def test_main_p10_never_inserts_or_deletes_the_block(self):
        """`h.status` here runs the REAL `cli.run_status` -> `cli.read_status` bounded adapter against
        the SAME model row G1 built (never a canned success dict): the main check still makes no
        INSERT/DELETE of its own."""
        h = self.fake_harness()
        cr.g1_gate(h)
        before_admin_calls = len([e for e in self.order if e[0] == "admin"])
        cr.p10_active_write_block_ignored(h)
        after_admin_calls = len([e for e in self.order if e[0] == "admin"])
        self.assertEqual(before_admin_calls, after_admin_calls)      # no INSERT/DELETE in the main check
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        subcases = {e["name"]: e["ok"] for e in saved["events"]
                   if e.get("kind") == "subcase" and e.get("check") == "p10"}
        for name in ("status_unaffected", "block_unchanged", "no_apply_or_account_lock", "no_row_lock_in_sql"):
            self.assertTrue(subcases.get(name), name)

    def test_main_p5_full_variants_pass_through_the_real_reader(self):
        """`cr.p5_not_started_variants(h)` end to end: missing key, other-owner-under-the-same-key and
        owner-unreadable-scope ALL resolve to the real `not_started` contract through the SAME real
        `cli.read_status` bounded adapter the G1-built fixtures feed, with the corruption/restore and
        whole-DB-baseline comparisons genuinely exercised (never a canned/pre-asserted result)."""
        h = self.fake_harness()
        cr.g1_gate(h)
        cr.p5_not_started_variants(h)
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        subcases = {e["name"]: e["ok"] for e in saved["events"]
                   if e.get("kind") == "subcase" and e.get("check") == "p5"}
        for name in ("missing_key", "missing_key_no_snapshot_select", "other_owner",
                    "other_owner_no_snapshot_select", "owner_unreadable", "owner_unreadable_no_snapshot_select",
                    "owner_unreadable_restored", "database_restored_to_baseline"):
            self.assertTrue(subcases.get(name), name)

    def test_real_run_status_counts_are_genuine_not_assigned_after_the_fact(self):
        """Codex-reproduced regression: calling the SAME `real_run_status`/`FakeStatusConnection` pair
        TWICE must genuinely raise `handed` to 2 while `created` stays 1 -- proving the counts
        `h.status`/`h.status_raw` report are the adapter's own real counters, never a canned `1`/`1`
        assigned after `real_run_status` returns."""
        h = self.fake_harness()
        cr.g1_gate(h)
        case = h.cases["p10"]
        counts = cr.Counts()
        connection = h._connection_for(case.db, case.request, counts=counts)
        out1, code1 = real_run_status(case.request, connection, clock=cr.fixed_clock(cr.T0), counts=counts)
        self.assertEqual(counts.created[cr.READ], 1)
        self.assertEqual(counts.handed[cr.READ], 1)
        out2, code2 = real_run_status(case.request, connection, clock=cr.fixed_clock(cr.T0), counts=counts)
        self.assertEqual((out1, code1), (out2, code2))
        self.assertEqual(counts.created[cr.READ], 1)       # the SAME connection object, never re-created
        self.assertEqual(counts.handed[cr.READ], 2)        # genuinely handed out twice

    def test_main_p10_rejects_a_double_real_hand_over_at_no_apply_or_account_lock(self):
        """Codex's exact repro, through the ACTUAL P10 check (not just the helper): a double real
        hand-over on the SAME connection/counts, reached through `cr.p10_active_write_block_ignored`
        itself, must make the REAL `no_apply_or_account_lock` predicate fail specifically -- never an
        earlier result/fixture gate -- protecting that predicate against a future accidental
        removal/weakening."""
        h = self.fake_harness()
        cr.g1_gate(h)
        original = real_run_status
        captured: dict = {}

        def twice(*args, **kwargs):
            original(*args, **kwargs)
            captured["counts"] = kwargs.get("counts")
            return original(*args, **kwargs)
        with mock.patch.object(sys.modules[__name__], "real_run_status", twice):
            with self.assertRaises(cr.CheckFailed):
                cr.p10_active_write_block_ignored(h)
        observed = captured["counts"]
        self.assertIsNotNone(observed)
        self.assertEqual(observed.created[cr.READ], 1)     # one connection object, never re-created
        self.assertEqual(observed.handed[cr.READ], 2)      # genuinely handed out twice by the real call
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        subcases = {e["name"]: e["ok"] for e in saved["events"]
                   if e.get("kind") == "subcase" and e.get("check") == "p10"}
        self.assertTrue(subcases.get("block_fixture_valid_before_status"))
        self.assertTrue(subcases.get("database_matches_baseline_before_status"))
        self.assertTrue(subcases.get("status_unaffected"))
        self.assertTrue(subcases.get("block_unchanged"))
        self.assertTrue(subcases.get("database_matches_baseline_after_status"))
        self.assertFalse(subcases.get("no_apply_or_account_lock"))   # the specific predicate that fails

    def test_fake_admin_rejects_an_unregistered_db_or_wrong_pid_or_unknown_sql(self):
        self.fake_harness()
        with self.assertRaises(AssertionError):
            with cr.admin("outside-registered-check-dbs", -1) as conn:
                conn.execute("UPDATE users SET arbitrary_column = arbitrary_value", ())
        with self.assertRaises(AssertionError):
            with cr.admin(cr.CHECK_DB["p5"], -1) as conn:
                conn.execute("SELECT 1")
        with self.assertRaises(AssertionError):
            with cr.admin(cr.CHECK_DB["p5"], 999) as conn:
                conn.execute("DELETE FROM srs_migration_runs WHERE id = 1")

    def test_fake_admin_rejects_a_known_prefix_with_an_unexpected_suffix(self):
        self.fake_harness()
        with self.assertRaises(AssertionError):
            with cr.admin(cr.CHECK_DB["p5"], 999) as conn:
                conn.execute("UPDATE srs_migration_runs SET scope_json = %s WHERE id = %s; DROP TABLE x",
                            ("x", 1))

    def test_fake_admin_p2_conflict_update_refuses_a_wrong_row_without_silent_success(self):
        self.fake_harness()
        with cr.admin(cr.CHECK_DB["p2"], 999) as conn:
            rowcount = conn.execute("UPDATE vocab_items SET correct_count = correct_count + 1 "
                                    "WHERE id = %s AND user_id = %s", (999999, 1)).rowcount
        self.assertEqual(rowcount, 0)
        with cr.admin(cr.CHECK_DB["p2"], 999) as conn:
            rowcount = conn.execute("UPDATE vocab_items SET correct_count = correct_count + 1 "
                                    "WHERE id = %s AND user_id = %s", (101, 999999)).rowcount
        self.assertEqual(rowcount, 0)

    def test_fake_admin_p10_insert_rejects_wrong_params(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        with self.assertRaises(AssertionError):
            with cr.admin(cr.CHECK_DB["p10"], 999) as conn:
                conn.execute(
                    "INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
                    "active_user_id, run_watermark, changes_started, created_at) VALUES "
                    "(%s, 'srs_recovery', %s, %s, 'active', %s, 0, 0, %s) RETURNING id",
                    (1, "wrong-recovery-key", hashlib.sha256(b"synthetic-grant").hexdigest(), 1,
                     "2026-10-30T00:00:00+00:00"))

    def test_fake_admin_restore_of_a_missing_row_refuses_without_silent_success(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        with cr.admin(cr.CHECK_DB["p5"], 999) as conn:
            rowcount = h.restore_row(conn, "srs_migration_runs", {"id": 999999, "mode": "apply"})
        self.assertEqual(rowcount, 0)

    def test_main_p10_runs_with_apply_and_account_lock_forbidden_and_still_passes(self):
        """A genuine runtime guard (never a source proxy): REAL P10, against its truly present active
        block, must pass with `migration.apply_plan` forbidden, and with the ACTUAL account write lock --
        `app.srs.storage.begin_card_write` (`migration.apply_plan` calls its own module-level imported
        name `migration.begin_card_write`, a separate binding patched too) -- forbidden. `_locked_access`
        is the subscription FOR-SHARE access check, not the account lock, but is forbidden here as well
        for good measure: P10's read path never reaches any of them."""
        h = self.fake_harness()
        cr.g1_gate(h)
        from app.srs import migration, storage

        def forbidden(*a, **k):
            raise AssertionError("P10 must not reach apply/account-lock machinery")
        patches = [mock.patch.object(migration, "_locked_access", forbidden),
                  mock.patch.object(migration, "begin_card_write", forbidden),
                  mock.patch.object(storage, "begin_card_write", forbidden),
                  mock.patch.object(migration, "apply_plan", forbidden)]
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            cr.p10_active_write_block_ignored(h)

    def test_main_p10_rejects_a_block_changed_during_its_own_status_call(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        real_status = h.status
        db = cr.CHECK_DB["p10"]
        block_id = h.evidence["p10_block"]["id"]

        def mutating_status(case_, **kwargs):
            result = real_status(case_, **kwargs)
            self.model["blocks"][db][block_id]["status"] = "removed"
            return result
        h.status = mutating_status
        with self.assertRaises(cr.CheckFailed):
            cr.p10_active_write_block_ignored(h)

    def test_main_p10_rejects_a_database_drift_during_its_own_status_call(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        real_status = h.status
        db = cr.CHECK_DB["p10"]
        run_key = h.cases["p10"].request.run_key

        def drifting_status(case_, **kwargs):
            result = real_status(case_, **kwargs)
            run_id = self.model["runs"][db][run_key]["id"]
            self.model["snapshots"][db][run_key].append(
                {"id": 999999, "user_id": case_.request.account_id, "card_kind": "personal",
                 "card_ref": 999999, "run_id": run_id})
            return result
        h.status = drifting_status
        with self.assertRaises(cr.CheckFailed):
            cr.p10_active_write_block_ignored(h)

    def test_main_p5_stops_at_the_first_wrong_variant_and_never_reaches_the_rest(self):
        """Not a canned success: tampering the REAL reader's own exit code on the FIRST variant must make
        `cr.p5_not_started_variants` fail there, and the later variants must never run."""
        h = self.fake_harness()
        cr.g1_gate(h)
        real_status_raw = h.status_raw
        calls: list = []

        def tampering_status_raw(request, inputs, read_exp, *, clock, **kwargs):
            calls.append(request.run_key)
            result = real_status_raw(request, inputs, read_exp, clock=clock, **kwargs)
            if request.run_key == "completed-replay-p5-missing":
                result = dict(result, code=result["code"] + 1)
            return result
        h.status_raw = tampering_status_raw
        with self.assertRaises(cr.CheckFailed):
            cr.p5_not_started_variants(h)
        self.assertEqual(calls, ["completed-replay-p5-missing"])

    def test_main_p5_fails_when_an_extra_snapshot_select_is_observed(self):
        """An extra, genuinely executed-and-fetched snapshot SELECT (never a directly mutated counter)
        on the missing-key variant's own connection must make P5 fail at its `_no_snapshot_select`
        subcase specifically, and stop there."""
        h = self.fake_harness()
        cr.g1_gate(h)
        real_status_raw = h.status_raw

        def extra_select_status_raw(request, inputs, read_exp, *, clock, fetch_hooks=None, **kwargs):
            if request.run_key == "completed-replay-p5-missing":
                counts = cr.Counts()
                connection = h._connection_for(cr.CHECK_DB["p5"], request, fetch_hooks=fetch_hooks, counts=counts)
                connection.execute("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots "
                                   "WHERE run_id = ?", (0,)).fetchall()
                out, code = real_run_status(request, connection, clock=clock, counts=counts)
                return {"out": out, "code": code, "counts": counts, "trackers": []}
            return real_status_raw(request, inputs, read_exp, clock=clock, fetch_hooks=fetch_hooks, **kwargs)
        h.status_raw = extra_select_status_raw
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.p5_not_started_variants(h)
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        subcases = {e["name"]: e["ok"] for e in saved["events"]
                   if e.get("kind") == "subcase" and e.get("check") == "p5"}
        self.assertFalse(subcases.get("missing_key_no_snapshot_select"))
        self.assertNotIn("other_owner", subcases)              # stopped before the next variant

    def test_main_p5_restores_original_row_and_facts_when_its_own_corrupted_status_raises(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        a_case = h.cases["p5:corrupt"]
        run_id = h.state_admin(a_case)["runs"][0]["id"]
        original_row = h.row_text(a_case.db, "srs_migration_runs", run_id)
        db_base = h.evidence["db_baseline"]["p5"]
        real_status_raw = h.status_raw
        injected = RuntimeError("precreated P5 corruption probe error")
        calls: list = []

        def corrupting_status_raw(request, inputs, read_exp, *, clock, **kwargs):
            calls.append(request.run_key)
            if request.run_key == "completed-replay-p5-corrupt":
                current = h.row_text(a_case.db, "srs_migration_runs", run_id)
                self.assertNotEqual(current, original_row)     # genuinely corrupted by the time this runs
                raise injected
            return real_status_raw(request, inputs, read_exp, clock=clock, **kwargs)
        h.status_raw = corrupting_status_raw
        with self.assertRaises(RuntimeError) as caught:
            cr.p5_not_started_variants(h)
        self.assertIs(caught.exception, injected)
        self.assertEqual(calls, ["completed-replay-p5-missing", "completed-replay-p5-other",
                                "completed-replay-p5-corrupt"])
        self.assertEqual(h.row_text(a_case.db, "srs_migration_runs", run_id), original_row)
        self.assertEqual(h.database_facts("p5"), db_base)

    def test_main_p5_restores_original_row_when_its_own_status_raises_keyboardinterrupt(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        a_case = h.cases["p5:corrupt"]
        run_id = h.state_admin(a_case)["runs"][0]["id"]
        original_row = h.row_text(a_case.db, "srs_migration_runs", run_id)
        db_base = h.evidence["db_baseline"]["p5"]
        real_status_raw = h.status_raw
        injected = KeyboardInterrupt()

        def corrupting_status_raw(request, inputs, read_exp, *, clock, **kwargs):
            if request.run_key == "completed-replay-p5-corrupt":
                raise injected
            return real_status_raw(request, inputs, read_exp, clock=clock, **kwargs)
        h.status_raw = corrupting_status_raw
        with self.assertRaises(KeyboardInterrupt) as caught:
            cr.p5_not_started_variants(h)
        self.assertIs(caught.exception, injected)
        self.assertEqual(h.row_text(a_case.db, "srs_migration_runs", run_id), original_row)
        self.assertEqual(h.database_facts("p5"), db_base)

    def test_main_p5_restoration_failure_still_preserves_the_original_corruption_error(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        real_status_raw = h.status_raw
        injected = RuntimeError("precreated P5 corruption probe error")
        restore_error = RuntimeError("precreated restore failure")

        def corrupting_status_raw(request, inputs, read_exp, *, clock, **kwargs):
            if request.run_key == "completed-replay-p5-corrupt":
                raise injected
            return real_status_raw(request, inputs, read_exp, clock=clock, **kwargs)

        def failing_restore_row(conn, table, row):
            raise restore_error
        h.status_raw = corrupting_status_raw
        h.restore_row = failing_restore_row
        with self.assertRaises(RuntimeError) as caught:
            cr.p5_not_started_variants(h)
        self.assertIs(caught.exception, injected)
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        kinds = [e.get("kind") for e in saved["events"]]
        self.assertIn("admin_restore_failed", kinds)
        subcases = {e["name"] for e in saved["events"] if e.get("kind") == "subcase" and e.get("check") == "p5"}
        self.assertNotIn("owner_unreadable_restored", subcases)

    def test_post_check_compares_against_the_frozen_baseline_not_a_fresh_regeneration(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        frozen = dict(h.evidence["db_baseline"])
        out = cr.post_check(h)
        self.assertEqual(out, {"sessions": {"open": 0, "idle_in_transaction": 0}})
        self.assertEqual(h.evidence["db_baseline"], frozen)          # never overwritten by post_check

    def test_post_check_refuses_a_drifted_table_for_any_planned_db(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        original = h.database_facts

        def drifted(check_id):
            facts = original(check_id)
            if check_id == "p3":
                facts["tables"] = {"other_table": ["changed"]}
            return facts
        h.database_facts = drifted
        with self.assertRaises(cr.CheckFailed):
            cr.post_check(h)

    def test_post_check_refuses_a_missing_baseline(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        del h.evidence["db_baseline"]
        with self.assertRaises(cr.CheckFailed):
            cr.post_check(h)

    def test_post_check_refuses_a_sequence_drift(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        original = h.database_facts

        def drifted(check_id):
            facts = original(check_id)
            if check_id == "p7":
                facts["sequences"]["users_id_seq"] = [2, True]
            return facts
        h.database_facts = drifted
        with self.assertRaises(cr.CheckFailed):
            cr.post_check(h)

    def test_post_check_refuses_a_mutated_in_memory_baseline(self):
        """A baseline changed only in memory (never resaved to the record) must never authorize a drift:
        `post_check` reads the SAVED evidence, not whatever `h.evidence["db_baseline"]` says now."""
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        h.evidence["db_baseline"]["p4"]["tables"]["users"] = [999, "tampered"]
        with self.assertRaises(cr.CheckFailed):
            cr.post_check(h)

    def test_g1_gate_baseline_is_an_independent_deep_copy(self):
        """Mutating the dict a later `database_facts` call happens to reuse must never also mutate the
        frozen baseline already stored: `g1_gate` makes its own JSON deep copy."""
        h = self.fake_harness()
        empty_md5 = hashlib.md5(b"").hexdigest()
        shared_tables = {t: [0, empty_md5] for t in lay.BUSINESS_TABLES}

        def aliasing_facts(check_id):
            self.order.append(("database_facts", check_id))
            return {"tables": shared_tables, "sequences": {"users_id_seq": [1, True]},
                   "sequence_names": ["users_id_seq"], "check_id": check_id}
        h.database_facts = aliasing_facts
        cr.g1_gate(h)
        shared_tables["users"] = [999, hashlib.md5(b"mutated").hexdigest()]
        self.assertEqual(h.evidence["db_baseline"]["p1"]["tables"]["users"], [0, empty_md5])

    def test_defect1_regression_an_intervening_event_cannot_resave_a_mutated_baseline_as_evidence(self):
        """PROVEN defect 1 (Codex-reproduced): `rec.event` used to keep the SAME object `h.evidence`
        held; mutating the in-memory baseline, then causing any LATER `rec.event` call (never the
        baseline's own save), used to resave the mutated values as if they were the original G1
        evidence, and a matching fresh drift then passed `post_check`. With the deep-copy fix the saved
        evidence stays exactly what G1 captured no matter what happens to it afterwards."""
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        h.evidence["db_baseline"]["p4"]["tables"]["users"][0] = 999
        h.rec.event("ordinary_intervening_event")           # must NOT resave the mutated baseline
        original = h.database_facts

        def matching_drift(check_id):
            facts = original(check_id)
            if check_id == "p4":
                facts["tables"]["users"][0] = 999            # the SAME drift as the in-memory mutation
            return facts
        h.database_facts = matching_drift
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.post_check(h)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_defect2_regression_malformed_table_and_sequence_shapes_are_rejected(self):
        """PROVEN defect 2 (Codex-reproduced): a `None` table entry or a non-numeric sequence pair used
        to pass `validate_whole_db_facts` silently."""
        base_tables = {t: [0, hashlib.md5(b"").hexdigest()] for t in lay.BUSINESS_TABLES}
        base = {"tables": dict(base_tables), "sequences": {"users_id_seq": [1, True]},
               "sequence_names": ["users_id_seq"]}
        mutants = [
            dict(base, tables=dict(base_tables, users=None)),
            dict(base, tables=dict(base_tables, users=[0, "too-short"])),
            dict(base, tables=dict(base_tables, users=[True, hashlib.md5(b"").hexdigest()])),
            dict(base, sequences={"users_id_seq": ["invalid", "invalid"]}),
            dict(base, sequences={"users_id_seq": [1, 1]}),            # is_called must be a real bool
            dict(base, sequence_names=["users_id_seq", "users_id_seq"]),
            dict(base, sequence_names=["other_id_seq"]),
            {"tables": dict(base_tables)},                             # missing sequences/sequence_names
            "not-a-dict",
        ]
        for mutant in mutants:
            with self.subTest(mutant=mutant if isinstance(mutant, str) else sorted(mutant)):
                with self.assertRaises(cr.CheckFailed) as caught:
                    cr.validate_whole_db_facts("p1", mutant)
                self.assertEqual(caught.exception.kind, "harness_defect")
        cr.validate_whole_db_facts("p1", base)        # the well-formed baseline itself must still pass

    def test_post_check_rejects_a_duplicate_baseline_event(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        h.pauses, h.threads = [], []
        h.rec.event("database_baseline_captured", checks=sorted(cr.PLANNED),
                    facts=json.loads(json.dumps(h.evidence["db_baseline"])))
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.post_check(h)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_g1_gate_fails_before_baseline_when_first_apply_fails(self):
        h = self.fake_harness()

        def failing_first_apply(case_, *, handover=None):
            raise cr.CheckFailed("preparation_failure", "fixture apply failed")
        h.first_apply = failing_first_apply
        with self.assertRaises(cr.CheckFailed):
            cr.g1_gate(h)
        self.assertNotIn("db_baseline", h.evidence)

    def test_main_p5_refuses_a_missing_fixture_before_any_status_call(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        del h.cases["p5:corrupt"]

        def forbidden_status_raw(*a, **k):
            raise AssertionError("status_raw must not be reached when a G1 fixture is missing")
        h.status_raw = forbidden_status_raw
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.p5_not_started_variants(h)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_main_p10_refuses_a_missing_block_fixture_before_status(self):
        h = self.fake_harness()
        cr.g1_gate(h)
        del h.evidence["p10_block"]

        def forbidden_status(*a, **k):
            raise AssertionError("status must not be reached when the G1 block fixture is missing")
        h.status = forbidden_status
        with self.assertRaises(cr.CheckFailed) as caught:
            cr.p10_active_write_block_ignored(h)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_main_p10_refuses_a_prechanged_block_before_status(self):
        h = self.fake_harness()
        cr.g1_gate(h)

        def changed_row_text(db, table, row_id):
            return {"id": row_id, "user_id": 1, "status": "removed", "active_user_id": 1}
        h.row_text = changed_row_text

        def forbidden_status(*a, **k):
            raise AssertionError("status must not be reached when the block fixture no longer matches G1")
        h.status = forbidden_status
        with self.assertRaises(cr.CheckFailed):
            cr.p10_active_write_block_ignored(h)


class G1FixturesAndBaseline(G1FixtureBaselineMixin, Blocked):
    pass


# --- 10. Bounded real read_status path (final correction, minimal route): REAL `cli.run_status` ->
# `cli.read_status` -> `migration._scope_cards` (real reduced-scope ownership parsing) -> `judge_status`,
# with ONLY `cli._admit` / `cli._timed_connector` replaced by fixed stubs -- never preflight, signing,
# provider or product-connection machinery. NOT wired into `cr.Harness.status_raw`/`status`: the real-PG
# harness's `p5_not_started_variants` / `p10_active_write_block_ignored` still use the existing connector
# plumbing for their actual run against PostgreSQL; this class proves the read/judge boundary on its own,
# fake, non-PostgreSQL connection (strict: any unrecognized SQL raises instead of silently answering). ---

class FakeStatusCursor:
    def __init__(self, rows, *, role=None, sql_text=None, fetch_hooks=None):
        self._rows = list(rows)
        self._role, self._sql_text, self._fetch_hooks = role, sql_text, list(fetch_hooks or [])

    def fetchone(self):
        result = self._rows[0] if self._rows else None
        for hook in self._fetch_hooks:
            hook(self._role, "fetchone", self._sql_text, None, result)
        return result

    def fetchall(self):
        result = list(self._rows)
        for hook in self._fetch_hooks:
            hook(self._role, "fetchall", self._sql_text, None, result)
        return result


class FakeStatusConnection:
    """A minimal, non-PostgreSQL connection for the REAL `cli.read_status` control flow: one fixed run
    row (or none) under its own `run_key`, fixed snapshot rows. Any SQL text outside the two real
    `read_status` statements (plus its `BEGIN`) is an `AssertionError`, never an empty result.

    `hooks` (execute-level, `record_statements`-shaped) and `fetch_hooks` (fetch-level, `count_fetch`-
    shaped) are both OPTIONAL and real-hook-compatible: supplied hooks genuinely run on the statement
    actually sent / the row actually fetched, never a canned, independently-asserted result.

    `counts` (optional, a `cr.Counts`) is genuinely incremented, never assigned after the fact: `created`
    once, right here, when this connection object is BUILT; `handed` once per `real_run_status` call that
    actually hands THIS SAME object out (see `fake_timed_connector.connect` below -- a second call on the
    same connection genuinely raises `handed` to 2, `created` stays 1); each `execute` counts its own
    statement word; a normal (exception-free) `__exit__` counts one modeled read commit."""

    def __init__(self, run_key, run_row, snapshot_rows, *, hooks=None, fetch_hooks=None, counts=None):
        self.run_key, self.run_row, self.snapshot_rows = run_key, run_row, list(snapshot_rows)
        self.statements: list = []
        self.hooks = list(hooks or [])
        self.fetch_hooks = list(fetch_hooks or [])
        self.counts = counts
        if counts is not None:
            counts.created[cr.READ] += 1

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        text = sql.strip()
        for hook in self.hooks:
            hook(cr.READ, "execute", text, None)
        if self.counts is not None:
            word = text.split(None, 1)[0].rstrip(";").upper() if text.strip() else "UNKNOWN"
            words = self.counts.words[cr.READ]
            words[word] = words.get(word, 0) + 1
        if text.startswith("BEGIN"):
            return FakeStatusCursor([], role=cr.READ, sql_text=text, fetch_hooks=self.fetch_hooks)
        if text.startswith("SELECT id, mode, status, scope_json"):
            match = self.run_row is not None and params and params[0] == self.run_key
            return FakeStatusCursor([self.run_row] if match else [], role=cr.READ, sql_text=text,
                                    fetch_hooks=self.fetch_hooks)
        if text.startswith("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots"):
            run_id = params[0]
            return FakeStatusCursor([r for r in self.snapshot_rows if self.run_row and run_id == self.run_row["id"]],
                                    role=cr.READ, sql_text=text, fetch_hooks=self.fetch_hooks)
        raise AssertionError(f"unexpected SQL reached the P5/P10 real-reader fixture: {text!r}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None and self.counts is not None:
            self.counts.commits[cr.READ] += 1
        return False

    def snapshot_select_count(self) -> int:
        return sum(1 for sql, _ in self.statements if "srs_migration_snapshots" in sql)


def real_run_status(request, connection, *, clock, counts=None):
    """Calls the REAL `cr.cli.run_status`: `_admit` and `_timed_connector` are replaced by fixed stubs
    (the plan's minimal bounded route) that hand `connection` straight to the REAL `cli.read_status`;
    every statement it sends, `migration._scope_cards`'s real ownership parsing and the REAL
    `judge_status` run unmodified. No preflight/signature/provider/product-connection code runs.
    `counts.handed[cr.READ]` is bumped HERE, at the actual hand-over -- calling this twice with the SAME
    `connection`/`counts` genuinely raises `handed` to 2 while `created` (bumped once, by the connection's
    own construction) stays 1."""
    stub_matched = SimpleNamespace()

    def fake_admit(req, inputs, driver, step, command, *, clock=None):
        cr.ar.fix_app_environment()
        return stub_matched

    def fake_timed_connector(inputs, expected, driver, clock):
        def connect(*, read_only=False):
            if counts is not None:
                counts.handed[cr.READ] += 1
            return connection
        return connect
    with mock.patch.object(cr.cli, "_admit", fake_admit), \
            mock.patch.object(cr.cli, "_timed_connector", fake_timed_connector):
        return cr.cli.run_status(request, inputs=object(), expected=None, driver=object(), clock=clock)


class RealReadStatusPath(Blocked):
    NOT_STARTED = {"status": "ok", "command": "status", "state": "not_started"}

    def setUp(self):
        super().setUp()
        cr.ar.fix_app_environment()
        from app.srs.engine import DEFAULT_CONFIG
        self.config_version = DEFAULT_CONFIG.config_version

    def reduced_scope(self, uid, cards):
        request_bytes = json.dumps([[k, r] for k, r in cards], separators=(",", ":")).encode("ascii")
        return json.dumps({"format": 2, "user_id": uid, "config_version": self.config_version,
                           "cards": [{"kind": k, "ref_id": r} for k, r in cards],
                           "request_sha256": hashlib.sha256(request_bytes).hexdigest()})

    def test_missing_key_is_actually_not_started_with_zero_snapshot_select(self):
        request = cr.cli.make_request(1, "no-such-run", [101, 102], [])
        connection = FakeStatusConnection("no-such-run", None, [])
        out, code = real_run_status(request, connection, clock=lambda: cr.T0)
        self.assertEqual((out, code), (self.NOT_STARTED, 0))
        self.assertEqual(cr.canonical_json(out), cr.canonical_json(self.NOT_STARTED))
        self.assertEqual(connection.snapshot_select_count(), 0)

    def test_other_owner_under_the_same_key_is_actually_not_started(self):
        request = cr.cli.make_request(1, "shared-key", [101, 102], [])
        run_row = {"id": 1, "mode": "apply", "status": "completed",
                   "scope_json": self.reduced_scope(2, [("personal", 201), ("personal", 202)]),
                   "config_version": self.config_version,
                   "summary_json": json.dumps({"cursor": 2, "results": [
                       {"kind": "personal", "ref_id": 201, "result": "applied"},
                       {"kind": "personal", "ref_id": 202, "result": "applied"}]}),
                   "started_at": "2026-10-21T12:00:00+00:00", "finished_at": "2026-10-21T12:05:00+00:00"}
        connection = FakeStatusConnection("shared-key", run_row, [
            {"id": 1, "user_id": 2, "card_kind": "personal", "card_ref": 201},
            {"id": 2, "user_id": 2, "card_kind": "personal", "card_ref": 202}])
        out, code = real_run_status(request, connection, clock=lambda: cr.T0)
        self.assertEqual((out, code), (self.NOT_STARTED, 0))
        self.assertEqual(connection.snapshot_select_count(), 0)

    def test_duplicate_key_scope_is_actually_not_started_through_real_ownership_parsing(self):
        request = cr.cli.make_request(1, "corrupt-key", [101, 102], [])
        scope_text = self.reduced_scope(1, [("personal", 101), ("personal", 102)])
        duplicated = scope_text[:-1] + ', "user_id": 1}'            # a real duplicate top-level key
        run_row = {"id": 1, "mode": "apply", "status": "completed", "scope_json": duplicated,
                   "config_version": self.config_version,
                   "summary_json": json.dumps({"cursor": 2, "results": []}),
                   "started_at": "2026-10-21T12:00:00+00:00", "finished_at": "2026-10-21T12:05:00+00:00"}
        connection = FakeStatusConnection("corrupt-key", run_row, [])
        out, code = real_run_status(request, connection, clock=lambda: cr.T0)
        self.assertEqual((out, code), (self.NOT_STARTED, 0))
        self.assertEqual(connection.snapshot_select_count(), 0)

    def test_an_unrecognized_query_is_itself_rejected_by_the_fixture(self):
        """Proof the fixture cannot silently pass: an unexpected statement raises immediately."""
        connection = FakeStatusConnection("k", None, [])
        with self.assertRaises(AssertionError):
            connection.execute("SELECT 1 FROM some_other_table WHERE x = ?", (1,))

    def test_active_case_status_through_real_read_status_is_completed_applied_two(self):
        """P10 (bounded): `read_status` never reads `account_write_blocks`; this proves the SAME real
        path reports `completed`/{"applied": 2} for a normal completed run regardless of any write
        block elsewhere in the database (the block itself is validated by the real-PG harness, not
        here -- `read_status` simply has no code path that could reach it)."""
        request = cr.cli.make_request(1, "p10-key", [101, 102], [])
        run_row = {"id": 1, "mode": "apply", "status": "completed",
                   "scope_json": self.reduced_scope(1, [("personal", 101), ("personal", 102)]),
                   "config_version": self.config_version,
                   "summary_json": json.dumps({"cursor": 2, "results": [
                       {"kind": "personal", "ref_id": 101, "result": "applied"},
                       {"kind": "personal", "ref_id": 102, "result": "applied"}]}),
                   "started_at": "2026-10-21T12:00:00+00:00", "finished_at": "2026-10-21T12:05:00+00:00"}
        connection = FakeStatusConnection("p10-key", run_row, [
            {"id": 1, "user_id": 1, "card_kind": "personal", "card_ref": 101},
            {"id": 2, "user_id": 1, "card_kind": "personal", "card_ref": 102}])
        out, code = real_run_status(request, connection, clock=lambda: cr.T0)
        self.assertEqual((out.get("state"), out.get("results"), code), ("completed", {"applied": 2}, 0))
        self.assertTrue(connection.statements[-1][0].startswith("SELECT id, user_id, card_kind, card_ref"))


# --- 11. NormalProviderPath: the REAL CR-PG1 `Harness.__init__`/`case`/`status`/`driver`/`RunScopes`
# through the WHOLE existing provider path -- `cli._product_connector` (`cr.ORIGINAL_CONNECTOR`),
# `_ops_product_connect.ProductConnector`, `_ops_observer.CatalogObserver`, `pv.judge_observation`,
# `oa.authorize_command` -- are never patched here. FAKE: the raw server/cursor the guarded driver
# hands over (a catalog built directly from the REAL `cr.expected_profiles` objects/privileges, never a
# narrower test-only table list, via `test_ops_product_connect.BizConn` /
# `test_srs_migrate_resume_provider.Server` / `test_ops_observer.FakeCursor`), `g.Guard` and its
# liveness lookups, and (P2 only) the state-injected status run/snapshot rows. STUB (business body
# only): the product `migration.dry_run`, which cannot run on a fake connection -- it enters the handed
# connection once, runs one harmless `SELECT 1`, and returns fixed plan candidates. --------------------

import _ops_observer as ob  # noqa: E402  (production module: patch target for the real CatalogObserver)
import test_ops_observer as to  # noqa: E402  (module only)
import test_ops_product_connect as tpc  # noqa: E402  (module only)
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only)
import test_srs_migrate_resume_provider as rprov  # noqa: E402  (module only)

EXCESS_REFUSAL = rprov.CODES["excess"]


def profile_catalog(profile: Any, *, access: str, user: str, db: str, identity_value: str) -> dict:
    """A fake catalog built directly from the REAL expected profile (`cr.expected_profiles`'s own
    objects/privileges), so `judge_observation` compares against exactly the same contract the REAL
    harness uses: the normal path passes, and a deliberately added privilege is the only difference."""
    cat = to.catalog(access)
    oids: dict = {}
    oid = 20000
    schemas: dict = {}
    databases: list = []
    tablespaces: list = []
    relations: list = []
    columns: dict = {}
    for kind, schema, name in sorted(profile.objects):
        oid += 1
        if kind == "table":
            oids[(kind, schema, name)] = oid
            relations.append((oid, "r", schema, name))
            columns[oid] = ["id"]
        elif kind == "sequence":
            oids[(kind, schema, name)] = oid
            relations.append((oid, "S", schema, name))
        elif kind == "schema":
            schemas[name] = oid
        elif kind == "database":
            databases.append((oid, name))
        elif kind == "tablespace":
            tablespaces.append((oid, name))
    grants: set = set()
    for kind, schema, name, column, privilege in profile.privileges:
        if kind == "database":
            grants.add(("database", next(o for o, n in databases if n == name), privilege))
        elif kind == "schema":
            grants.add(("schema", schemas[name], privilege))
        elif kind == "sequence":
            grants.add(("sequence", oids[(kind, schema, name)], privilege))
        elif column:
            columns.setdefault(oids[(kind, schema, name)], ["id"])
            if column not in columns[oids[(kind, schema, name)]]:
                columns[oids[(kind, schema, name)]].append(column)
            grants.add(("column", (oids[(kind, schema, name)], column), privilege))
        else:
            grants.add(("relation", oids[(kind, schema, name)], privilege))
    cat.update(relations=relations, columns=columns, schemas=[(o, n) for n, o in schemas.items()],
              database=databases, tablespaces=tablespaces, grants=grants)
    cat["session"] = dict(cat["session"], dbname=db, current_user_name=user, session_user_name=user,
                          search_path=profile.search_path)
    cat["identity"] = [identity_value]
    return cat


class NPPInfo(to.pt.FakeInfo):
    """FAKE: the connection-info facts `CatalogObserver.observe` reads straight off the connection
    (never derived from the catalog rows) -- host/port/dbname of THIS fake server, plus the backend pid
    `_ops_real_layout.Tracked` needs for its own pending-pid bookkeeping."""

    def __init__(self, conn: Any, host: str, port: int, dbname: str, backend_pid: int = 4242):
        super().__init__(conn)
        self.host, self.port, self.dbname, self.backend_pid = host, port, dbname, backend_pid

    @property
    def server_version(self):
        return self._conn.server_version


class NPPCursor(to.FakeCursor):
    """Extends the existing catalog cursor: ONLY `lay.POST_CONNECT` (the guarded driver's own
    just-connected check, never one of the observer's own queries) gets a fixed, independent answer
    built from this fixture's own coherent fake target.json; every other query still goes through the
    REAL catalog-answer logic above, unchanged -- but its bound parameters must be exactly the
    module's own `ob.PARAMS[name]` constant, checked here BEFORE the inherited response, never
    accepted generically."""

    def execute(self, query, params=None):
        if query == lay.POST_CONNECT:
            expected = (list(lay.OID_TABLES),)
            if params != expected:
                raise AssertionError(f"unexpected lay.POST_CONNECT params: {params!r} (expected {expected!r})")
            self.conn.queries.append(("post_connect", params))
            self.rows = [dict(self.conn.post_connect_facts)]
            return
        names = [n for n, q in ob.QUERIES.items() if q == query]
        if len(names) == 1:
            expected = ob.PARAMS.get(names[0])
            if params != expected:
                raise AssertionError(f"unexpected observer params for {names[0]!r}: {params!r} "
                                     f"(expected {expected!r})")
        super().execute(query, params)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class NPPServer(rprov.Server):
    """FAKE server only (never a real PostgreSQL connection): the REAL provider's own observation SQL
    and the two REAL status SELECTs (`rprov.Server`, here built from the REAL expected profile instead
    of the CLI-test contract subset), plus the ONE extra `lay.POST_CONNECT` answer the guarded driver's
    `post_connect_check` needs before any provider code runs. `execute` accepts ONLY the exact fixed
    statements this fixture's own real callers send (`cr.pv.OBSERVATION_START`, the product's own
    first read statement, `SELECT 1`, `COMMIT`, and the two status SELECTs with their EXACT expected
    params) -- any other SQL, or a wrong/missing/extra parameter on a known statement, is a fixed
    `AssertionError` raised BEFORE the inherited response, never a silent pass-through."""

    _ALLOWED_FIXED = frozenset(cr.pv.OBSERVATION_START) | {
        "SET TRANSACTION READ ONLY", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", "SELECT 1", "COMMIT"}
    _RUN_QUERY = cr.RUN_ROW_PREFIX + " FROM srs_migration_runs WHERE run_key = %s"
    _SNAPSHOT_QUERY = cr.SNAPSHOT_SELECT_PREFIX + " WHERE run_id = %s"

    def __init__(self, cat: dict, post_connect_facts: dict, *, host: str, port: int, dbname: str,
                run: dict | None = None, snapshots: tuple = (), expected_run_key: str | None = None):
        super().__init__(cat, run=run, snapshots=snapshots)
        self.post_connect_facts = post_connect_facts
        self.info = NPPInfo(self, host, port, dbname)
        self.server_version = 18 * 10000 + 6
        self.expected_run_key = expected_run_key if expected_run_key is not None else cr.RUN_KEY

    def execute(self, sql, params=None):
        if isinstance(sql, str) and not self.closed:
            if sql == self._RUN_QUERY:
                if params != (self.expected_run_key,):
                    raise AssertionError(f"unexpected status run-query params: {params!r}")
            elif sql == self._SNAPSHOT_QUERY:
                expected_run_id = self.run["id"] if self.run else None
                if params != (expected_run_id,):
                    raise AssertionError(f"unexpected status snapshot-query params: {params!r}")
            elif sql in self._ALLOWED_FIXED:
                if params not in (None, ()):
                    raise AssertionError(f"unexpected params for {sql!r}: {params!r}")
            else:
                raise AssertionError(f"unexpected business SQL reached the fake server: {sql!r}")
        return super().execute(sql, params)

    def cursor(self, row_factory=None):
        cursor = NPPCursor(self)
        self.cursors.append(cursor)
        return cursor


class NPPKeys(cr.sigtests.Keys):
    """The SAME key generation loop as `cr.sigtests.Keys` (never a new key policy), into a folder
    THIS fixture already owns and has registered for cleanup BEFORE construction starts -- never a
    second, unregistered `ops_sig_test_keys_*` temp folder. `sign`/`allowed`/`close` are inherited
    unchanged."""

    def __init__(self, folder: str):
        self.folder = folder
        self.pub = {}
        for name in ("signer", "stranger", "revoked"):
            path = os.path.join(self.folder, name)
            if cr.sigtests._keygen("-q", "-t", "ed25519", "-N", "", "-C", f"synthetic-{name}", "-f", path,
                                  cwd=self.folder) != 0:
                raise RuntimeError("test key generation failed")
            with open(path + ".pub", "rb") as handle:
                self.pub[name] = handle.read().strip()


class NormalProviderPath(unittest.TestCase):
    """REAL path: `cr.Harness.__init__`/`case`/`driver`/`RunScopes` -> CLI `run_dry_run` ->
    signatures/preflight -> the ACTUAL `ProductConnector`/provider/`CatalogObserver`/
    `judge_observation`/`authorize_command` -> real `h.status`/`read_status`. `_admit`,
    `cr.ORIGINAL_CONNECTOR`, `cli._product_connector`, the observer and judgement results are never
    patched -- passthrough spies around `op.run_synthetic_preflight`, `cr.post_connect_check`,
    `ob.CatalogObserver.observe`, `cr.pv.judge_observation` and `cr.oa.authorize_command` call the
    SAME real functions and only record a fixed `"enter"`/`"pass"`/`"refused:<code>"` label (never a
    DSN, signature or password). FAKE: the driver's raw server/cursor (catalog/target/liveness
    facts, with an EXACT business-SQL/param allowlist -- see `NPPServer`/`NPPCursor`), and (P2 only)
    the state-injected status run/snapshot rows. STUB: the product `migration.dry_run` business BODY
    only, which returns REAL `app.srs.migration.MigrationCandidate` instances built through the
    actual pure `migration._incomplete_candidate` constructor (never a duck-typed `SimpleNamespace`,
    never a seed plan file -- see `fixture_candidates`)."""

    CHECK_ID = "p1"

    def setUp(self):
        _pin_safe_env(self)
        if not os.path.isfile(cr.op.osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        real_popen = subprocess.Popen

        def only_keygen(args, *a, **k):
            if os.path.normcase(str(args[0])) != os.path.normcase(cr.op.osig.SSH_KEYGEN):
                raise AssertionError("an external entry point was called")
            return real_popen(args, *a, **k)
        test = self
        self.conns: list = []
        self.guard_calls: list = []
        self.run_row, self.snapshot_rows = None, ()
        self.bad_read_extra: list = []
        self.preflight_trace, self.post_connect_trace = [], []
        self.observe_trace, self.judge_trace, self.authorize_trace = [], [], []
        self.path_events: list = []            # ONE ordered, shared, cross-phase event list

        class FakeGuard:
            def __init__(self, manifest, deploy_root, folder, target=None):
                test.assertIs(target, cr.T)

            def driver(self, **kwargs):
                test.guard_calls.append(dict(kwargs))
                return test.make_conn(kwargs["user"], kwargs["dbname"])

        def traced(bucket, real, refused_exc, label):
            def wrapper(*args, **kwargs):
                bucket.append("enter")
                test.path_events.append(f"{label}:enter")
                try:
                    result = real(*args, **kwargs)
                except refused_exc as error:
                    bucket.append(f"refused:{getattr(error, 'code', 'unknown')}")
                    test.path_events.append(f"{label}:refused")
                    raise
                bucket.append("pass")
                test.path_events.append(f"{label}:pass")
                return result
            return wrapper
        real_preflight, real_post_connect = cr.op.run_synthetic_preflight, cr.post_connect_check
        real_observe, real_judge = ob.CatalogObserver.observe, cr.pv.judge_observation
        real_authorize = cr.oa.authorize_command
        real_enter = cr.cli.pc.ProductConnection.__enter__

        def entered(self_):
            """PASSTHROUGH spy on the REAL `ProductConnection.__enter__`: the ORIGINAL context entry
            runs first; `'handover'` is appended to `path_events` only AFTER it returns the SAME `app`
            object -- never a success stub, never a replacement of the connector/provider/judgement."""
            result = real_enter(self_)
            test.path_events.append("handover")
            return result
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", only_keygen),
                      mock.patch.object(g, "listener_pids", forbidden), mock.patch.object(g, "admin_connect", forbidden),
                      mock.patch.object(g, "postmaster_pid", forbidden), mock.patch.object(g, "single_run", forbidden),
                      mock.patch.object(lay.real, "make_tls", forbidden), mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == 999999 and target is cr.T),
                      mock.patch.object(g, "Guard", FakeGuard),
                      mock.patch.object(cr.Harness, "ca_pem", lambda self: b"fixture-only-not-a-real-ca"),
                      mock.patch.object(cr.op, "run_synthetic_preflight",
                                        traced(self.preflight_trace, real_preflight, cr.op.OpsPreflightRefused,
                                              "preflight")),
                      mock.patch.object(cr, "post_connect_check",
                                        traced(self.post_connect_trace, real_post_connect, cr.g.Pg62Refused,
                                              "post_connect")),
                      mock.patch.object(ob.CatalogObserver, "observe",
                                        traced(self.observe_trace, real_observe, cr.pv.OpsProviderRefused,
                                              "observe")),
                      mock.patch.object(cr.pv, "judge_observation",
                                        traced(self.judge_trace, real_judge, cr.pv.OpsProviderRefused, "judge")),
                      mock.patch.object(cr.oa, "authorize_command",
                                        traced(self.authorize_trace, real_authorize, Exception, "authorize")),
                      mock.patch.object(cr.cli.pc.ProductConnection, "__enter__", entered),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)

        self.db = cr.CHECK_DB[self.CHECK_ID]
        root_path = os.path.normpath(tempfile.mkdtemp(prefix="pg69_normal_provider_"))
        root_stat = os.stat(root_path, follow_symlinks=False)
        root_identity = {"path": root_path, "parent": os.path.dirname(root_path),
                         "dev": root_stat.st_dev, "ino": root_stat.st_ino}

        def remove_owned_root():
            """Strict owned-root removal (never `ignore_errors=True` as proof): the SAME identity
            (parent, prefix, device/inode, never a symlink/junction) captured right after creation
            must still match before any recursive delete, and the removal itself is confirmed."""
            folder = root_identity["path"]
            if os.path.dirname(folder) != root_identity["parent"] \
                    or not os.path.basename(folder).startswith("pg69_normal_provider_"):
                raise AssertionError("owned root identity mismatch: refusing to delete")
            if os.path.islink(folder) or (hasattr(os.path, "isjunction") and os.path.isjunction(folder)):
                raise AssertionError("owned root identity mismatch: refusing to delete")
            live = os.stat(folder, follow_symlinks=False)
            if (live.st_dev, live.st_ino) != (root_identity["dev"], root_identity["ino"]):
                raise AssertionError("owned root identity mismatch: refusing to delete")
            shutil.rmtree(folder)
            if os.path.lexists(folder):
                raise AssertionError("owned root removal unconfirmed")
        self.addCleanup(remove_owned_root)                         # registered first: runs LAST
        self.folder_root = Path(root_path)
        self.key_folder = os.path.join(root_path, "keys")
        os.makedirs(self.key_folder)
        self.roles_oid = {cr.READ: 101, cr.WRITE: 102}
        self.identity = {db: f"pg69-normal-{i}" for i, db in enumerate(cr.T.databases[1:])}
        self.target = {"postmaster_pid": 999999, "host": g.HOST, "port": cr.T.port, "data": str(cr.T.data),
                       "postgres_exe": str(g.POSTGRES_EXE), "server_version_num": "180006",
                       "provider_roles": list(cr.BUSINESS_ROLES), "roles": dict(self.roles_oid),
                       "synthetic": {"a": {"user_id": 2, "personal": {"p1": 11, "p2": 12}}},
                       "databases": {db: {"identity_value": self.identity[db], "oid": 500 + i,
                                          "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                    for i, db in enumerate(cr.T.databases[1:])}}
        data = json.dumps(self.target, sort_keys=True).encode()
        (self.folder_root / "target.json").write_bytes(data)
        rec = g.Record(self.folder_root)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        self.h = cr.Harness(rec)                                  # real init: record binding, liveness

        def close_cleanly():
            done = self.h.close()
            self.assertEqual((done.failures, done.interrupts), ([], []))
        self.addCleanup(close_cleanly)                             # registered next: runs BEFORE the folder removal
        # `NPPKeys` generates into `self.key_folder`, already inside the owned root registered above:
        # a construction failure here (before this assignment completes) leaves `h.keys` None (no
        # duplicate key-folder registration/cleanup) and its partial files are still removed by the
        # owned-root cleanup, never a second, unregistered `ops_sig_test_keys_*` temp folder.
        self.h.keys = NPPKeys(self.key_folder)                     # owned by h.close ONLY afterwards
        self.h.allowed = self.h.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.h.passwords = {role: "fixture-only-password" for role in cr.BUSINESS_ROLES}

    def make_conn(self, user: str, db: str):
        access = "read" if user == cr.READ else "write"
        read_exp, write_exp = cr.expected_profiles(db)
        profile = read_exp if access == "read" else write_exp
        if access == "read" and self.bad_read_extra:
            profile = dataclasses.replace(profile, privileges=frozenset(profile.privileges) | set(self.bad_read_extra))
        cat = profile_catalog(profile, access=access, user=user, db=db, identity_value=self.identity[db])
        facts = {"server_addr": "127.0.0.1", "server_port": cr.T.port, "version": self.target["server_version_num"],
                "dbname": db, "db_oid": self.target["databases"][db]["oid"], "role_oid": self.roles_oid[user],
                "object_oids": [self.target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                "identity": [self.identity[db]]}
        server = NPPServer(cat, facts, host=g.HOST, port=cr.T.port, dbname=db, run=self.run_row,
                          snapshots=self.snapshot_rows)
        self.conns.append(server)
        return server

    def fixture_candidates(self, uid: int, refs=(11, 12)):
        """REAL `migration.MigrationCandidate` instances, built through the actual pure
        `migration._incomplete_candidate` constructor -- never a duck-typed `SimpleNamespace`, never a
        seed plan file, never a real DB read. A fixed synthetic 'learning' card with a schedule one
        day after `cr.T0` and flags `(\"missing_history\",)` (the same shape `_history` returns for a
        card with no logs) makes a deterministic, typed, convertible-incomplete candidate that
        `pfile.to_candidates`/`migration._plan_json`/`migration._scope` accept and compare like any
        real dry-run result."""
        cr.ar.fix_app_environment()
        from app.srs import migration
        from app.srs.engine import CardKey
        out = []
        for ref in refs:
            key = CardKey("personal", uid, ref)
            card = {"id": ref, "user_id": uid, "status": "learning",
                   "next_review_at": (cr.T0 + timedelta(days=1)).isoformat(), "srs_card_version": 0}
            common = dict(key=key, card_fingerprint=migration._card_print(card),
                         logs_fingerprint=migration._digest([]), card_version=0, last_log_id=0)
            out.append(migration._incomplete_candidate(card, common, ("missing_history",)))
        return tuple(out)

    def reset_trace(self):
        for name in ("preflight_trace", "post_connect_trace", "observe_trace", "judge_trace", "authorize_trace",
                     "path_events"):
            getattr(self, name).clear()

    def assert_post_connect_success_order(self):
        """The REAL post-connect order on the FIRST successful hand-over: `post_connect:pass` ->
        `observe:pass` -> `judge:pass` -> `authorize:enter` -> `authorize:pass` -> `handover`. The
        `authorize:enter`/`:pass` pair is searched starting AFTER `judge:pass`, so an earlier
        authorization inside the pre-check (before any connection) is never mistaken for the
        post-connect reauthorization. No refusal event anywhere in that exact segment."""
        events = self.path_events
        handover_idx = events.index("handover")
        pc_idx = events.index("post_connect:pass")
        obs_idx = events.index("observe:pass", pc_idx)
        judge_idx = events.index("judge:pass", obs_idx)
        auth_enter_idx = events.index("authorize:enter", judge_idx)
        auth_pass_idx = events.index("authorize:pass", auth_enter_idx)
        for earlier, later in ((pc_idx, obs_idx), (obs_idx, judge_idx), (judge_idx, auth_enter_idx),
                               (auth_enter_idx, auth_pass_idx), (auth_pass_idx, handover_idx)):
            self.assertLess(earlier, later)
        self.assertFalse(any(e.endswith(":refused") for e in events[pc_idx:handover_idx + 1]))

    # -- 0. the fixture factory itself: real, typed, deterministic -- no seed plan file ---------------------

    def test_0_fixture_is_coherent_without_seed_file(self):
        cr.ar.fix_app_environment()
        from app.srs import migration
        from app.srs.engine import CardKey, DEFAULT_CONFIG
        uid = self.target["synthetic"]["a"]["user_id"]
        candidates = self.fixture_candidates(uid)
        self.assertEqual(len(candidates), 2)
        for c, ref in zip(candidates, (11, 12)):
            self.assertIsInstance(c, migration.MigrationCandidate)
            self.assertEqual(c.key, CardKey("personal", uid, ref))
            self.assertEqual((c.quality, c.flags), ("incomplete", ("missing_history",)))
            self.assertIsNotNone(c.values_json)
            values = json.loads(c.values_json)
            self.assertEqual(values["srs_config_version"], DEFAULT_CONFIG.config_version)
            self.assertIsNone(values["srs_state"])
        self.assertEqual(migration._scope([c.key for c in candidates]), tuple(c.key for c in candidates))
        scope = migration._plan_json(candidates)
        self.assertTrue(migration._full_scope(json.loads(scope), DEFAULT_CONFIG.config_version))
        product1 = hashlib.sha256(migration._plan_json(candidates).encode()).hexdigest()
        product2 = hashlib.sha256(migration._plan_json(self.fixture_candidates(uid)).encode()).hexdigest()
        self.assertEqual(product1, product2)                      # stable/deterministic, no hidden randomness
        self.assertFalse((self.folder_root / "seed_plan.json").exists())

    def run_case(self):
        """The REAL `cr.Harness.case`, with passthrough spies (never fake verdicts, never a post-hoc
        counter) around `Counts`, `RunScopes.run` and `Harness.driver`."""
        test = self
        real_run, real_driver = cr.RunScopes.run, cr.Harness.driver
        self.scope_lists, self.driver_lists, self.counts_seen = [], [], []

        class SpyCounts(cr.Counts):
            def __init__(self):
                super().__init__()
                test.counts_seen.append(self)

        def scope_run(self_, counts, trackers, **kw):
            test.scope_lists.append(trackers)
            return real_run(self_, counts, trackers, **kw)

        def driver(self_, inputs, counts, trackers, hooks=None, rc_variant=False, fetch_hooks=None):
            test.driver_lists.append(trackers)
            return real_driver(self_, inputs, counts, trackers, hooks=hooks, rc_variant=rc_variant,
                               fetch_hooks=fetch_hooks)
        produced: list = []

        def dry_run(keys, *, connect=None):
            with connect(read_only=True) as c:
                c.execute("SELECT 1")
            candidates = self.fixture_candidates(keys[0].user_id, refs=[k.ref_id for k in keys])
            produced.append(candidates)
            return candidates
        cr.ar.fix_app_environment()
        from app.srs import migration
        with mock.patch.object(cr, "Counts", SpyCounts), mock.patch.object(cr.RunScopes, "run", scope_run), \
                mock.patch.object(cr.Harness, "driver", driver), mock.patch.object(migration, "dry_run", dry_run):
            case = self.h.case(self.CHECK_ID, account="a", batch_size=2)
        return case, produced[0]

    def completed_run_row(self, case: "cr.Case"):
        """State-injected completed run: `scope_json` is the REAL `migration._plan_json` of the SAME
        candidates the real dry-run plan file holds (never a hand-rolled scope shape), so `judge_status`
        sees the identical cards/account/config the case's own A0/plan are bound to."""
        cr.ar.fix_app_environment()
        from app.srs import migration
        from app.srs.engine import DEFAULT_CONFIG
        candidates = cr.pfile.to_candidates(case.plan)
        scope = migration._plan_json(candidates)
        summary = json.dumps({"cursor": len(candidates), "results": [
            {"kind": c.key.kind, "ref_id": c.key.ref_id, "result": "applied"} for c in candidates]})
        run_row = {"id": 1, "mode": "apply", "status": "completed", "scope_json": scope,
                  "config_version": DEFAULT_CONFIG.config_version, "summary_json": summary,
                  "started_at": "2026-10-21T12:00:00+00:00", "finished_at": "2026-10-21T12:05:00+00:00"}
        snapshots = tuple({"id": i + 1, "user_id": case.request.account_id, "card_kind": c.key.kind,
                          "card_ref": c.key.ref_id} for i, c in enumerate(candidates))
        return run_row, snapshots

    # -- 1. the normal dry-run plan, through the whole real provider chain --------------------------------

    def test_1_real_case_writes_plan_through_the_full_provider_chain(self):
        case, candidates = self.run_case()
        self.assert_post_connect_success_order()           # the REAL post-connect order, before anything else
        self.assertEqual(len(self.scope_lists), 1)
        self.assertIs(self.scope_lists[0], self.driver_lists[0])          # ONE list, shared by both
        counts = self.counts_seen[0]
        self.assertEqual((counts.created, counts.handed), ({cr.READ: 1, cr.WRITE: 0}, {cr.READ: 1, cr.WRITE: 0}))
        self.assertEqual([k["user"] for k in self.guard_calls], [cr.READ])
        self.assertEqual({c.key.ref_id for c in candidates}, {11, 12})
        self.assertIs(case.first_write.approval, case.a0)
        a0 = json.loads(case.a0)
        i0 = json.loads(case.dry_run_inquiry)
        self.assertEqual((a0["format_version"], a0["kind"], i0["kind"]), (3, "apply", "inquiry"))

        # -- independent expected values: fixed fixture constants + the REAL production helpers, NEVER
        # a value parsed back out of the case/plan to "verify" itself ------------------------------------
        cr.ar.fix_app_environment()
        from app.srs import migration
        from app.srs.engine import DEFAULT_CONFIG
        target_obs = cr.op.TargetObservation(host=cr.g.HOST, port=cr.T.port, database=self.db, server_major=18,
                                             identity_value=self.identity[self.db])
        expected_db = cr.pf.db_identity(target_obs)
        suffix = cr.RUN_KEY[-6:] or "000000"
        expected_request = cr.cli.make_request(2, cr.RUN_KEY, [11, 12], [])
        expected_candidates = self.fixture_candidates(2, refs=(11, 12))
        self.assertEqual(candidates, expected_candidates)
        expected_product = hashlib.sha256(migration._plan_json(expected_candidates).encode()).hexdigest()
        expected_plan_bytes = cr.pfile.serialize_plan(
            db_identity=expected_db, account_id=2, job_key=cr.RUN_KEY,
            config_version=DEFAULT_CONFIG.config_version, product_fingerprint=expected_product,
            candidates=expected_candidates)
        expected_artifact = hashlib.sha256(expected_plan_bytes).hexdigest()

        self.assertEqual(Path(case.plan_path).read_bytes(), expected_plan_bytes)
        self.assertEqual((case.plan.db_identity, case.plan.account_id, case.plan.job_key,
                         case.plan.config_version, case.plan.product_fingerprint, case.plan.artifact_sha256),
                         (expected_db, 2, cr.RUN_KEY, DEFAULT_CONFIG.config_version, expected_product,
                          expected_artifact))
        self.assertEqual(cr.pfile.to_candidates(case.plan), expected_candidates)

        expected_manifest = cr.om.manifest_fingerprint(cr.pf.manifest_doc(self.h.files()))
        expected_job_plan = cr.oa.job_plan_fingerprint(
            db_identity=expected_db, manifest=expected_manifest, tool="srs_migrate", account_id=2,
            job_key=cr.RUN_KEY, job_inputs=cr.cli.job_inputs(expected_request),
            product_fingerprint=expected_product, artifact_sha256=expected_artifact)

        self.assertEqual(i0["db_identity"], expected_db)
        self.assertEqual(a0["db_identity"], expected_db)
        self.assertEqual(i0["approval_id"], f"inq-pg69-{self.CHECK_ID}-{suffix}")
        self.assertEqual(a0["approval_id"], f"app-pg69-{self.CHECK_ID}-{suffix}")
        expected_i0_sha = hashlib.sha256(case.dry_run_inquiry).hexdigest()
        self.assertEqual(a0["based_on"], {"approval_id": i0["approval_id"], "sha256": expected_i0_sha})
        self.assertEqual(a0["plan"]["2"], expected_job_plan)

        ev_bytes = Path(case.initial_evidence[0]).read_bytes()
        ev_doc = json.loads(ev_bytes)
        self.assertEqual(a0["backup_evidence"], {"sha256": hashlib.sha256(ev_bytes).hexdigest()})
        self.assertEqual((ev_doc["purpose"], ev_doc["restore_verified"], ev_doc["db_identity"],
                         ev_doc["account_id"], ev_doc["evidence_id"]),
                         ("synthetic", False, expected_db, 2, f"bkp-pg69-{self.CHECK_ID}-{suffix}"))
        self.assertEqual((case.first_write.product_fingerprint, case.first_write.artifact_sha256,
                         case.first_write.account_id, case.first_write.job_key,
                         dict(case.first_write.job_inputs)),
                         (expected_product, expected_artifact, 2, cr.RUN_KEY,
                          cr.cli.job_inputs(expected_request)))
        self.assertEqual((case.first_read.product_fingerprint, case.first_read.artifact_sha256),
                         (expected_product, expected_artifact))

        # -- REAL preflight, run again independently on A0/first_write (never a stub, never field presence
        # only): actual verified Approval/Approval objects, their actual signed hashes -------------------
        actual = cr.op.run_synthetic_preflight(case.first_write)
        self.assertEqual((actual.kind, actual.command, actual.db_identity, actual.job_plan),
                         ("apply", "apply", expected_db, expected_job_plan))
        self.assertTrue(actual.verified.approval.verified)
        self.assertTrue(actual.verified.inquiry.verified)
        self.assertEqual(actual.verified.approval.approval_id, f"app-pg69-{self.CHECK_ID}-{suffix}")
        self.assertEqual(actual.verified.inquiry.approval_id, f"inq-pg69-{self.CHECK_ID}-{suffix}")
        self.assertEqual(actual.verified.approval.sha256, hashlib.sha256(case.a0).hexdigest())
        self.assertEqual(actual.verified.inquiry.sha256, expected_i0_sha)
        self.assertEqual(actual.verified.approval.based_on, (i0["approval_id"], expected_i0_sha))
        self.assertEqual(actual.verified.approval.backup_evidence_sha256, hashlib.sha256(ev_bytes).hexdigest())
        self.assertEqual(actual.verified.approval.plan_for(2), expected_job_plan)

    # -- 2. normal completed replay: real status through the full provider chain --------------------------

    def test_2_real_status_through_the_full_provider_reports_completed_applied_two(self):
        case, _ = self.run_case()
        self.reset_trace()                                       # status's OWN trace/path_events, never case's
        original_a0, original_i0 = case.a0, case.dry_run_inquiry
        original_plan_bytes = Path(case.plan_path).read_bytes()
        original_write = (case.first_write.approval, case.first_write.approval_signature, case.first_write.inquiry,
                          case.first_write.inquiry_signature, case.first_write.product_fingerprint,
                          case.first_write.artifact_sha256)
        original_read = (case.first_read.approval, case.first_read.approval_signature, case.first_read.inquiry,
                         case.first_read.inquiry_signature, case.first_read.product_fingerprint,
                         case.first_read.artifact_sha256)
        # the injected run/snapshot rows are STATE-INJECTED test fixtures, never real-apply evidence
        self.run_row, self.snapshot_rows = self.completed_run_row(case)
        cr.ar.fix_app_environment()
        from app.srs import migration
        bucket: list = []
        with mock.patch.object(migration, "apply_plan", forbidden):
            result = self.h.status(case, clock=cr.fixed_clock(cr.T0 + timedelta(minutes=5)),
                                   hooks=[cr.record_statements(bucket)])
        self.assert_post_connect_success_order()                  # status's OWN real post-connect order
        self.assertEqual((case.a0, case.dry_run_inquiry), (original_a0, original_i0))   # A0/I0 untouched
        self.assertEqual(Path(case.plan_path).read_bytes(), original_plan_bytes)        # plan file untouched
        self.assertEqual((case.first_write.approval, case.first_write.approval_signature, case.first_write.inquiry,
                         case.first_write.inquiry_signature, case.first_write.product_fingerprint,
                         case.first_write.artifact_sha256), original_write)
        self.assertEqual((case.first_read.approval, case.first_read.approval_signature, case.first_read.inquiry,
                         case.first_read.inquiry_signature, case.first_read.product_fingerprint,
                         case.first_read.artifact_sha256), original_read)
        self.assertEqual((result["out"].get("state"), result["out"].get("results"), result["code"]),
                         ("completed", {"applied": 2}, 0))
        counts = result["counts"]
        self.assertEqual((counts.created[cr.READ], counts.handed[cr.READ]), (1, 1))
        self.assertEqual(counts.role(cr.WRITE), cr.ZERO_ROLE)
        selects = [s for s in bucket if s and s.upper().startswith("SELECT")]
        self.assertEqual(selects, [cr.RUN_ROW_PREFIX + " FROM srs_migration_runs WHERE run_key = %s",
                                  cr.SNAPSHOT_SELECT_PREFIX + " WHERE run_id = %s"])
        for statement in bucket:
            if statement:
                self.assertNotIn(lay.first_word(statement), lay.WRITE_WORDS)
                self.assertNotIn("FOR UPDATE", statement.upper())
                self.assertNotIn("FOR SHARE", statement.upper())

    # -- 3. a negative catalog (excess users.email UPDATE on the read role) is refused before handover ------

    def test_3_excess_read_privilege_is_refused_before_business_handover(self):
        self.bad_read_extra = [("table", "public", "users", "email", "UPDATE")]
        with self.assertRaises(cr.CheckFailed) as caught:
            self.run_case()
        self.assertEqual(caught.exception.kind, "preparation_failure")
        self.assertIn(EXCESS_REFUSAL, caught.exception.what)
        # preflight and post-connect passed on this SAME connection; only the real judge refused it
        self.assertIn("pass", self.preflight_trace)
        self.assertIn("pass", self.post_connect_trace)
        self.assertIn("pass", self.observe_trace)
        self.assertIn(f"refused:{EXCESS_REFUSAL}", self.judge_trace)
        conn = self.conns[-1]
        self.assertTrue(conn.queries)                           # the observer read the catalog
        self.assertTrue(conn.closed)
        self.assertNotIn("SELECT 1", conn.log)                  # never handed to the business dry_run body
        counts = self.counts_seen[0]
        self.assertEqual(counts.role(cr.READ), {"created": 1, "handed": 0, "statements": 0, "writes": 0,
                                                "commits": 0})
        self.assertEqual(counts.role(cr.WRITE), cr.ZERO_ROLE)

    # -- 4. the real g1_gate stops at the same observation on the very first check (p1) ----------------------

    def test_4_g1_gate_stops_at_p1_preparation_before_first_apply(self):
        self.bad_read_extra = [("table", "public", "users", "email", "UPDATE")]
        attempted: list = []
        real_case = cr.Harness.case

        def spy_case(self_, check_id, *a, **k):
            attempted.append(check_id)
            return real_case(self_, check_id, *a, **k)
        with mock.patch.object(cr.Harness, "case", spy_case), \
                mock.patch.object(cr.Harness, "first_apply", forbidden), \
                mock.patch.object(cr.Harness, "database_facts", forbidden):
            ok = lay.run_recorded(self.h.rec, "g1_gate", cr.g1_gate, self.h)
        self.assertFalse(ok)
        self.assertEqual(attempted, ["p1"])                      # p2.. never attempted
        self.assertEqual(self.h.cases, {})                       # p1 never finished building its case
        saved = json.loads((self.h.rec.folder / "record.json").read_text(encoding="utf-8"))
        last = saved["results"][-1]
        self.assertEqual((last["check"], last["status"], last["kind"]), ("g1_gate", "fail", "preparation_failure"))
        self.assertIn(EXCESS_REFUSAL, last.get("what", ""))
        self.assertIn("pass", self.observe_trace)
        self.assertIn(f"refused:{EXCESS_REFUSAL}", self.judge_trace)

    # -- 5. owned resources (keys, deploy folders) are cleaned on close; approvals stay None -----------------

    def test_5_close_cleans_owned_resources_and_approvals_stay_none(self):
        self.run_case()
        key_folder = Path(self.h.keys.folder)
        root_folder = self.folder_root
        deploy_folders = [Path(entry["path"]) for entry in self.h.folders]
        self.assertTrue(key_folder.exists())
        self.assertTrue(root_folder.exists())
        self.assertTrue(deploy_folders and all(p.exists() for p in deploy_folders))
        self.doCleanups()                                         # runs close_cleanly, then the owned-root removal
        self.assertFalse(key_folder.exists())
        self.assertFalse(root_folder.exists())
        self.assertTrue(all(not p.exists() for p in deploy_folders))
        self.assertEqual(self.h.passwords, {})
        self.assertIsNone(cr.PREPARE_APPROVED)
        self.assertIsNone(cr.CHECK_APPROVED)
        self.assertIsNone(cr.ADMIN_CHANGES_APPROVED)
        self.assertIsNone(cr.CLEANUP_APPROVED)

    # -- 6. a key-construction failure/interrupt is cleaned by the owned root, never a second temp folder ----

    def test_6_key_construction_failure_or_interrupt_cleans_the_owned_root(self):
        for chosen in (RuntimeError("synthetic-keygen-boom"), KeyboardInterrupt("synthetic-interrupt"),
                      SystemExit(23)):
            with self.subTest(exc=type(chosen).__name__):
                nested = NormalProviderPath("test_0_fixture_is_coherent_without_seed_file")
                with mock.patch.object(cr.sigtests, "_keygen", lambda *a, **k: (_ for _ in ()).throw(chosen)):
                    with self.assertRaises(type(chosen)) as caught:
                        nested.setUp()
                self.assertIs(caught.exception, chosen)           # the SAME object, never wrapped/replaced
                if isinstance(chosen, SystemExit):
                    self.assertEqual(caught.exception.code, 23)
                key_folder, root_folder = nested.key_folder, str(nested.folder_root)
                nested.doCleanups()                                # owned-root cleanup still runs (h.keys is None)
                self.assertFalse(os.path.exists(key_folder))
                self.assertFalse(os.path.exists(root_folder))

    # -- 7/8. the fake server's exact business-SQL/param allowlist (never a generic pass-through) -------------

    def test_7_unknown_business_sql_is_rejected_by_the_fake_server(self):
        server = self.make_conn(cr.READ, self.db)
        try:
            with self.assertRaises(AssertionError):
                server.execute("SELECT * FROM users")
        finally:
            server.close()

    def test_8_wrong_status_query_params_are_rejected_by_the_fake_server(self):
        self.run_row = {"id": 777, "mode": "apply", "status": "completed"}
        server = self.make_conn(cr.READ, self.db)
        try:
            with self.assertRaises(AssertionError):
                server.execute(NPPServer._RUN_QUERY, ("wrong-run-key",))
            with self.assertRaises(AssertionError):
                server.execute(NPPServer._SNAPSHOT_QUERY, (99999,))               # wrong run id
            with self.assertRaises(AssertionError):
                server.execute(NPPServer._RUN_QUERY + " LIMIT 1", (cr.RUN_KEY,))  # altered/trailing SQL
            with self.assertRaises(AssertionError):
                server.execute(NPPServer._SNAPSHOT_QUERY, (777, 1))               # extra param
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main()
