"""Fake-only checks for the PG69 completed-result requery real-PG runner (tests/_ops_completed_replay_real.py,
CR-PG1). No database, cluster, certificate, listener or admin connection: connect entry points, `subprocess`,
process facts and (outside `ApprovalPaths`) key creation are blocked. The runner's real `prepare` /
`check-completed` / `cleanup` never run against anything here; nothing in this file is PostgreSQL evidence.

Separately allowed: new Python processes for the import / entry-point smoke checks (`Imports`); no process here
ever reaches a real connection, driver or key. `ApprovalPaths` (section 8) is the one exception that allows real
temporary OpenSSH test keys (`test_ops_signature.Keys`, via `cr.sigtests.Keys`) for real approval signing; every
PostgreSQL, admin, process and TLS entry point stays forbidden there too.

Run directly:      python tests/test_ops_completed_replay_real_guard.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_completed_replay_real_guard.py
"""

from __future__ import annotations

import contextlib
import dataclasses
import inspect
import io
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


if __name__ == "__main__":
    unittest.main()
