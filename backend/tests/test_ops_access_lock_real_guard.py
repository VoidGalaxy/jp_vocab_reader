"""Fake-only checks for the LQ1 access-lock real-PG runner (tests/_ops_access_lock_real.py, plan V1).
No database, cluster, certificate, listener or admin connection: connect entry points, `subprocess`, key creation
and process facts are blocked; only temporary synthetic files are written. The runner's real prepare /
check-access-lock / cleanup never run against anything, and nothing here is PostgreSQL evidence.

Separately allowed: new Python processes for the import / entry-point checks (`Processes`), and the test-only
temporary OpenSSH keys of the real signing path (`CasePath`, real ssh-keygen; nothing else may start a process).
Where a check replaces signature verification it says so; such a check is not cryptographic evidence.

Run directly:      python tests/test_ops_access_lock_real_guard.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_access_lock_real_guard.py
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_access_lock_real as ax  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_real_layout as lay  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only: the plan fixture's product hash)

T = g.PG68_LEXEME_ACCESS_LOCK
PID = 6868
# Fixed from the plan (1절 / 4-0 / 4-2 / 11절), never read back from the code under test.
PLAN_CHECKS = ("k1", "k2a", "k2b", "k3", "s1", "s2", "s3", "s3b", "s4", "r1", "r2", "r3", "r4a", "r4b", "r5", "r6",
               "c1a", "c1b", "t1", "d1", "w1a", "w1b", "w2a", "w2b")
PLAN_TWO_PATH = {"r6", "c1a", "c1b", "w1b", "w2b"}


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


REAL_RUN = subprocess.run                     # fixed before any patch: new processes only where a check says so


BLOCKS = lambda: (mock.patch.object(psycopg, "connect", forbidden),  # noqa: E731
                  mock.patch.object(subprocess, "Popen", forbidden), mock.patch.object(subprocess, "run", forbidden),
                  mock.patch.object(ax.sigtests, "Keys", forbidden), mock.patch.object(g, "listener_pids", forbidden),
                  mock.patch.object(g, "admin_connect", forbidden), mock.patch.object(g, "postmaster_pid", forbidden),
                  mock.patch.object(lay.real, "make_tls", forbidden), mock.patch.object(lay.base, "run", forbidden),
                  mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                  mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                               if not k.upper().startswith("PG")}, clear=True))


class Blocked(unittest.TestCase):
    def setUp(self):
        for patch in BLOCKS():
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_access_lock_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def record(self, name="20261029T050000"):
        run = self.folder / name
        run.mkdir(exist_ok=True)
        return g.Record(run)


# --- 1. target, registration, matrix ------------------------------------------------------------------------

class Target(Blocked):
    def test_closed_values_and_identity(self):
        self.assertIs(ax.LAYOUT, lay.PG68)
        self.assertIs(ax.T, T)
        self.assertEqual((T.root, T.port, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg68"), 55522, "jpvk_admin", ("jpvk_read", "jpvk_write")))
        self.assertEqual(T.databases, ("jp_vocab_test_access_lock_tpl",)
                         + tuple(f"jp_vocab_test_access_lock_{c}" for c in PLAN_CHECKS))
        self.assertEqual((lay.PG68.owner, lay.PG68.read, lay.PG68.write), ("jpvk_owner", "jpvk_read", "jpvk_write"))
        self.assertIs(g.PRESETS[6], T)                      # PG68's own position, unmoved by PG69's append
        self.assertIs(g.PRESETS[-1], g.PG69_COMPLETED_REPLAY)
        self.assertIs(lay.LAYOUTS[3], lay.PG68)
        self.assertIs(lay.LAYOUTS[-1], lay.PG69)
        copy = dataclasses.replace(T)
        with self.assertRaises(g.Pg62Refused):
            g.preset(copy)
        layout_copy = dataclasses.replace(lay.PG68)
        for call in (lambda: lay.layout(layout_copy), lambda: lay.contract_grants(layout_copy, layout_copy.check_db["k1"]),
                     lambda: lay.Layout("pg68", copy, lay.PG68.check_ids, "jpvk_owner", {}, {})):
            with self.subTest(call=call), self.assertRaises(g.Pg62Refused):
                obj = call()
                lay.layout(obj)

    def test_names_are_separate_from_every_other_target(self):
        others = [p for p in g.PRESETS if p is not T]
        self.assertNotIn(T.port, {p.port for p in others})
        self.assertNotIn(T.root, {p.root for p in others})
        self.assertFalse(set(T.databases) & {d for p in others for d in p.databases})
        self.assertFalse(set(T.provider_roles + (T.admin, "jpvk_owner"))
                         & {r for p in others for r in p.provider_roles + (p.admin,)})

    def test_business_matrix_admin_limits_and_post_connect_recheck(self):
        ok = {"host": g.HOST, "port": "55522", "dbname": ax.CHECK_DB["k1"], "user": "jpvk_write", "sslmode": "verify-full"}
        ax.business_check(ok)
        for key, value in (("port", "55512"), ("dbname", ax.TEMPLATE), ("dbname", "jp_vocab_test_resume_lex_l1"),
                           ("user", "jpvk_admin"), ("user", "jpvl_write"), ("sslmode", "require")):
            with self.subTest(key=key, value=value), self.assertRaises(g.Pg62Refused):
                ax.business_check(dict(ok, **{key: value}))
        seen = []
        with mock.patch.object(g, "admin_connect", lambda db, **k: seen.append(k["target"]) or "conn"):
            self.assertEqual(ax.admin(ax.CHECK_DB["w2b"], PID), "conn")
            for db in ("jp_vocab_test_resume_lex_l1", "jp_vocab_test_apply_a1", "template1"):
                with self.subTest(db=db), self.assertRaises(g.Pg62Refused):
                    ax.admin(db, PID)
        self.assertTrue(all(t is T for t in seen))
        target = {"databases": {ax.CHECK_DB["k1"]: {"oid": 501, "identity_value": "x",
                                                    "objects": {t: 900 + i for i, t in enumerate(sorted(lay.OID_TABLES))}}},
                  "roles": {"jpvk_write": 102}, "server_version_num": "180006"}
        good = {"server_addr": "127.0.0.1", "server_port": 55522, "version": "180006", "dbname": ax.CHECK_DB["k1"],
                "db_oid": 501, "role_oid": 102, "object_oids": [900 + i for i in range(len(lay.OID_TABLES))],
                "identity": ["x"]}
        for change in ({}, {"server_port": 55512}, {"role_oid": 999}, {"identity": ["y"]}):
            conn = FactsConn(dict(good, **change))
            with self.subTest(change=change):
                if change:
                    with self.assertRaises(g.Pg62Refused):
                        ax.post_connect_check(conn, target, "jpvk_write")
                    self.assertTrue(conn.closed)
                else:
                    ax.post_connect_check(conn, target, "jpvk_write")

    def test_contract_grants_and_closed_variants(self):
        grants = [s.as_string(None) for s in ax.contract_grants(ax.CHECK_DB["k1"])]
        self.assertIn('GRANT UPDATE ("updated_at") ON "public"."user_deck_subscriptions" TO "jpvk_write"', grants)
        self.assertIn('GRANT UPDATE ("created_at") ON "public"."shared_deck_words" TO "jpvk_write"', grants)
        self.assertFalse([s for s in grants if s.startswith('GRANT UPDATE ON "public"."user_deck_subscriptions"')])
        self.assertEqual(set(lay.PG68.variant_databases), set(lay.PG68.variants))
        self.assertEqual(lay.PG68.variant_databases, {"k2a_subscriptions_column": ("k2a",),
                                                     "k2b_words_column": ("k2b",), "k3_subscriptions_table": ("k3",),
                                                     "s2_lock_timeout_10s": ("s2",), "s3_lock_timeout_2s": ("s3",),
                                                     "s3b_lock_timeout_5s": ("s3b",)})
        revert = [s.as_string(None) for s in ax.variant_statements("k3_subscriptions_table", "revert")]
        self.assertEqual(revert, ['REVOKE UPDATE ON public.user_deck_subscriptions FROM "jpvk_write"',
                                  'GRANT UPDATE (updated_at) ON public.user_deck_subscriptions TO "jpvk_write"'])
        for name, value in (("s2_lock_timeout_10s", "10s"), ("s3_lock_timeout_2s", "2s"), ("s3b_lock_timeout_5s", "5s")):
            apply = [s.as_string(None) for s in ax.variant_statements(name, "apply")]
            self.assertEqual(apply, [f'ALTER ROLE "jpvk_write" IN DATABASE {ax.CHECK_DB[name.split("_")[0]]} '
                                     f"SET lock_timeout = '{value}'"])

    def test_changes_locked_until_v3(self):
        h = SimpleNamespace(rec=SimpleNamespace(event=forbidden))
        h.approved = lambda what: ax.Harness.approved(h, what)
        for decision in (None, False):
            with self.subTest(decision=decision), mock.patch.object(ax, "LQ4_CHANGES_APPROVED", decision):
                for call in (lambda: ax.Harness.variant(h, "k2a", "k2a_subscriptions_column", "apply"),
                             lambda: ax.Harness.admin_tx(h, "s4", []), lambda: ax.Harness.approved(h, "x")):
                    with self.assertRaises(lay.CheckFailed):
                        call()
                with mock.patch.object(g, "single_run", forbidden), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(ax.main(["check-access-lock"]), 1)
                self.assertIn("LQ4", out.getvalue())
        # V2~V4 were approved and completed (plan 14); the unapproved branches above remain explicit.
        self.assertIs(ax.LQ4_CHANGES_APPROVED, True)

    def test_command_line_takes_only_the_three_phases(self):
        for argv in ([], ["check-access-lock", "k1"], ["check"], ["prepare", "--port", "55522"], ["cleanup", "x"]):
            with self.subTest(argv=argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ax.main(argv), 2)
        self.assertEqual(ax.PHASES, ("prepare", "check-access-lock", "cleanup"))


class FactsConn:
    def __init__(self, facts):
        self.facts, self.closed = facts, False

    def cursor(self, row_factory=None):
        conn = self

        class C:
            def __enter__(self_):
                return self_

            def __exit__(self_, *a):
                return False

            def execute(self_, *a):
                pass

            def fetchone(self_):
                return dict(conn.facts)
        return C()

    def rollback(self):
        pass

    def close(self):
        self.closed = True


# --- 2. plan values: 24 checks, paths, settings --------------------------------------------------------------

class PlanValues(unittest.TestCase):
    def test_24_checks_in_order_one_db_each(self):
        self.assertEqual(ax.PLANNED, PLAN_CHECKS)
        self.assertEqual(tuple(n for n, _ in ax.CHECKS), PLAN_CHECKS)
        self.assertEqual(tuple(ax.CHECK_DB), PLAN_CHECKS)
        self.assertEqual(set(ax.TWO_PATH), PLAN_TWO_PATH)
        self.assertEqual({c: ax.expected_paths(c) for c in PLAN_CHECKS},
                         {c: 2 if c in PLAN_TWO_PATH else 1 for c in PLAN_CHECKS})

    def test_settings_contract(self):
        normal = [{"value": "5000ms", "ok": True}, {"value": "0", "ok": True}]
        self.assertEqual(ax.settings_expected("k1", path_judged=True, failed=False), normal)
        self.assertEqual(ax.settings_expected("s2", path_judged=True, failed=False),
                         [{"value": "5000ms", "ok": True}, {"value": "10s", "ok": True}])
        for check_id in ("s3", "s3b"):                                     # 2s and exactly 5s: never relaxed
            self.assertEqual(ax.settings_expected(check_id, path_judged=True, failed=False), [])
        self.assertEqual(ax.settings_expected("t1", path_judged=True, failed=True), [{"value": "5000ms", "ok": True}])
        self.assertEqual(ax.settings_expected("k2a", path_judged=False, failed=False), [])

    def test_path_problems_by_row_key(self):
        h = SimpleNamespace(target=TARGET)
        one = {"l1": [[200, 300]], "l2": [[200, 301]]}
        two = {"l1": [[200, 300]], "l2": [[200, 301], [201, 302]]}
        self.assertEqual(ax.path_problems(h, "k1", one, l2_paths=1), [])
        self.assertEqual(ax.path_problems(h, "r6", two, l2_paths=2), [])
        self.assertTrue(ax.path_problems(h, "k1", two))                   # B active where it must not be
        self.assertTrue(ax.path_problems(h, "r6", one))                   # B missing where it must be
        self.assertTrue(ax.path_problems(h, "k1", {"l1": [[200, 300]], "l2": [[200, 999]]}))   # same count, wrong key
        self.assertTrue(ax.path_problems(h, "k1", one, l2_paths=2))       # table value differs from 4-0


# --- 3. gates and counting: first failure stops; gates / post never counted -------------------------------------

ACCESS = {"deck_a": 100, "deck_b": 101, "sub_a": 200, "sub_b": 201, "word_a_l1": 300, "word_a_l2": 301,
          "word_b_l2": 302}
U, L1, L2 = 9, 40, 41
TARGET = {"synthetic": {"a": {"user_id": U, "lexeme": [L1, L2], "personal": {}}, "access": ACCESS,
                        "b": {"user_id": 10, "lexeme": [L1, L2], "personal": {}},
                        "c": {"user_id": 11, "lexeme": [L1, L2], "personal": {}}}}


class Counting(Blocked):
    def run_check(self, checks, *, gate_fail=None, record_fail=None):
        rec = self.record()
        rec.event("server_started", pid=PID)                     # a prepared run has its record on disk
        h = SimpleNamespace(start=lambda: None, close=lambda: ax.FinalCleanup())

        def result(self_, check, status, details=None, **facts):    # the runner's own record class
            if check == record_fail and status == "pass":
                raise OSError("synthetic record failure")
            return g.Record.result(self_, check, status, details, **facts)
        failing = mock.patch.object(ax.LockedRecord, "result", result)
        failing.start()
        self.addCleanup(failing.stop)

        def gate(name):
            def fn(h_):
                if name == gate_fail:
                    raise lay.CheckFailed("preparation_failure", f"{name} synthetic")
                return {}
            return fn
        with mock.patch.object(ax, "LQ4_CHANGES_APPROVED", True), mock.patch.object(g, "single_run", lambda t=None: rec), \
                mock.patch.object(ax, "Harness", lambda r: h), mock.patch.object(ax, "g0_gate", gate("g0_gate")), \
                mock.patch.object(ax, "g1_gate", gate("g1_gate")), mock.patch.object(ax, "post_check", lambda h_: {}), \
                mock.patch.object(ax, "CHECKS", checks), contextlib.redirect_stdout(io.StringIO()):
            passed, summary = ax.check_access_lock()
        saved = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))
        shutil.rmtree(rec.folder)
        return passed, summary, saved

    def checks(self, fail=None):
        def fn(name):
            def run(h):
                if name == fail:
                    raise lay.CheckFailed("mismatch", f"{name} synthetic")
                return {}
            return run
        return [(n, fn(n)) for n in PLAN_CHECKS]

    def test_all_pass_is_24_and_gates_and_post_not_counted(self):
        passed, summary, saved = self.run_check(self.checks())
        self.assertEqual((passed, summary), (24, {"failed": None, "not_run": []}))
        self.assertEqual([r["check"] for r in saved["results"]], ["g0_gate", "g1_gate", *PLAN_CHECKS, "post_check"])
        with mock.patch.object(ax, "check_access_lock", lambda: (24, {"failed": None, "not_run": []})), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ax.main(["check-access-lock"]), 0)
        with mock.patch.object(ax, "check_access_lock", lambda: (23, {"failed": None, "not_run": []})), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ax.main(["check-access-lock"]), 1)              # incomplete: never 0

    def test_first_failure_stops_and_records_not_run(self):
        passed, summary, saved = self.run_check(self.checks(fail="r1"))
        index = PLAN_CHECKS.index("r1")
        self.assertEqual((passed, summary["failed"], summary["not_run"]), (index, "r1", list(PLAN_CHECKS[index + 1:])))
        self.assertEqual(saved["events"][-1], {"kind": "not_run", "after": "r1", "checks": list(PLAN_CHECKS[index + 1:])})
        with mock.patch.object(ax, "check_access_lock", lambda: (passed, summary)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ax.main(["check-access-lock"]), 1)

    def test_a_gate_failure_runs_no_check(self):
        for gate in ("g0_gate", "g1_gate"):
            with self.subTest(gate=gate):
                passed, summary, saved = self.run_check(self.checks(), gate_fail=gate)
                self.assertEqual((passed, summary["failed"], summary["not_run"]), (0, gate, list(PLAN_CHECKS)))
                self.assertFalse([r for r in saved["results"] if r["check"] in PLAN_CHECKS])

    def test_a_record_failure_is_not_a_pass(self):
        passed, summary, _ = self.run_check(self.checks(), record_fail="k3")
        self.assertEqual((passed, summary["failed"]), (3, "k3"))

    def test_a_recorded_unconfirmed_end_blocks_checks_and_cleanup(self):
        rec = self.record()
        rec.event("thread_not_ended", check="r2", threads=["r2:admin"])
        with mock.patch.object(ax, "LQ4_CHANGES_APPROVED", True), mock.patch.object(g, "single_run", lambda t=None: rec), \
                mock.patch.object(ax, "Harness", forbidden), self.assertRaises(lay.CheckFailed):
            ax.check_access_lock()
        with mock.patch.object(g, "single_run", lambda t=None: rec), mock.patch.object(lay, "cleanup", forbidden), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ax.main(["cleanup"]), 1)
        self.assertIn("R2 refused", out.getvalue())
        (rec.folder / "record.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(ax.blocking_events(rec.folder / "record.json"), ["record_unreadable"])


class G0Paths(Blocked):
    """The REAL g0_gate with fake admin reads: a path count or row key that differs from plan 4-0 stops the gate
    before any check (and before the quality read)."""

    def test_wrong_paths_stop_g0(self):
        dbs = {db: {"oid": 500 + i, "identity_value": f"pg68-{i}"} for i, db in enumerate(T.databases)}

        class Conn:
            def __init__(self, db):
                self.db = db

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, query, params=()):
                q = query if isinstance(query, str) else query.as_string(None)
                if "pg_database" in q:
                    return SimpleNamespace(fetchone=lambda: (dbs[params[0]]["oid"],))
                if "db_identity" in q:
                    return SimpleNamespace(fetchall=lambda: [(dbs[self.db]["identity_value"],)])
                raise AssertionError(q)
        good = {c: {"l1": [[200, 300]], "l2": [[200, 301]] + ([[201, 302]] if c in PLAN_TWO_PATH else [])}
                for c in PLAN_CHECKS}
        for label, bad in (("r6 single", {"r6": {"l1": [[200, 300]], "l2": [[200, 301]]}}),
                           ("k1 two", {"k1": good["r6"]}), ("w1a other key", {"w1a": {"l1": [[200, 300]],
                                                                                     "l2": [[200, 777]]}})):
            with self.subTest(case=label):
                seen = dict(good, **bad)
                h = SimpleNamespace(target=dict(TARGET, databases=dbs, postmaster_pid=PID), pid=PID,
                                    paths=lambda c: seen[c], column_grants=lambda c: {"x": True})
                with mock.patch.object(ax, "require_ours", lambda t: None), \
                        mock.patch.object(ax, "admin", lambda db, pid, autocommit=True: Conn(db)), \
                        mock.patch.object(ax.lay, "quality_names", forbidden), self.assertRaises(lay.CheckFailed) as c:
                    ax.g0_gate(h)
                self.assertEqual(c.exception.kind, "preparation_failure")


# --- 4. counts: business / admin / probes / re-observation kept apart ----------------------------------------

class TraceConn:
    """FAKE raw connection under the tracker: records statements, raises a SQLSTATE error on demand."""

    def __init__(self, fail=None):
        self.fail, self.log = fail, []
        self.info = SimpleNamespace(backend_pid=4242)

    def execute(self, query, params=()):
        self.log.append(query)
        if self.fail and query.startswith(self.fail[0]):
            error = psycopg.errors.LockNotAvailable("Driver-Text") if self.fail[1] == "55P03" else RuntimeError("x")
            raise error
        return SimpleNamespace()

    def commit(self):
        self.log.append("COMMIT")


class Counts(unittest.TestCase):
    def tracker(self, conn):
        counts = ax.Counts()
        return ax.AccessTracked(conn, counts, ax.WRITE, []), counts

    def test_only_handed_statements_are_traced_and_counted(self):
        conn = TraceConn()
        t, counts = self.tracker(conn)
        t.execute(ax.SET_PREFIX + ", %s, true)", ("5000ms",))                 # observation: before the hand-over
        t.execute("UPDATE shared_deck_words SET created_at = %s", ("x",))
        self.assertEqual((t.settings, t.access_writes, counts.role(ax.WRITE)["statements"]), ([], [], 0))
        t.activate()
        t.execute(ax.SET_PREFIX + ", %s, true)", ("5000ms",))
        t.execute("SELECT subscriptions.id AS subscription_id FROM x", (1, 2))
        t.execute("UPDATE user_word_progress SET srs_state = %s", (1,))
        self.assertEqual(t.settings, [{"value": "5000ms", "ok": True}])
        self.assertEqual(t.access_writes, [])
        t.execute("DELETE FROM shared_deck_words WHERE id = %s", (1,))
        self.assertEqual(t.access_writes, ["DELETE"])
        self.assertEqual(counts.role(ax.WRITE)["writes"], 2)

    def test_sqlstate_only_and_the_error_passes_unchanged(self):
        conn = TraceConn(fail=(ax.LOCK_PREFIX, "55P03"))
        t, _ = self.tracker(conn)
        t.activate()
        t.execute(ax.SET_PREFIX + ", %s, true)", ("5000ms",))
        with self.assertRaises(psycopg.errors.LockNotAvailable) as caught:
            t.execute(ax.LOCK_PREFIX + " FROM x", (1, 2))
        self.assertEqual(caught.exception.sqlstate, "55P03")
        self.assertEqual(t.sqlstates, [{"statement": "SELECT", "sqlstate": "55P03"}])
        self.assertNotIn("Driver-Text", json.dumps(ax.run_trace([t])))
        failing = TraceConn(fail=(ax.SET_PREFIX, "other"))
        t2, _ = self.tracker(failing)
        t2.activate()
        with self.assertRaises(RuntimeError):
            t2.execute(ax.SET_PREFIX + ", %s, true)", ("5000ms",))
        self.assertEqual(t2.settings, [{"value": "5000ms", "ok": False}])          # a failed set is never "sent ok"

    def test_reobserved_counts_and_separate_events(self):
        rec = g.Record(Path(tempfile.mkdtemp(prefix="ops_access_lock_test_")))
        self.addCleanup(shutil.rmtree, rec.folder, True)
        calls = []
        for role in (ax.READ, ax.WRITE):
            h = SimpleNamespace(rec=rec, variant=lambda c, n, p: calls.append((c, n, p)),
                                observe_role=lambda case, r: {"result": "matches_contract", "counts": ax.REOBSERVED})
            self.assertEqual(ax.revert_and_observe(h, "k2a", None, "k2a_subscriptions_column", role)["counts"],
                             {"created": 1, "handed": 1, "statements": 0, "writes": 0, "commits": 0})
        for bad in ({"result": "matches_contract", "counts": dict(ax.REOBSERVED, commits=1)},
                    {"result": "observed_privileges_missing", "counts": dict(ax.REOBSERVED, handed=0)}, None):
            h = SimpleNamespace(rec=rec, variant=lambda c, n, p: None, observe_role=lambda case, r: bad)
            with self.subTest(bad=bad), self.assertRaises(lay.CheckFailed) as caught:
                ax.revert_and_observe(h, "k2a", None, "k2a_subscriptions_column", ax.WRITE)
            self.assertEqual(caught.exception.kind, "harness_defect")
        kinds = {e["kind"] for e in rec.doc["events"]}
        self.assertEqual(kinds, {"revert_observation", "subcase"})                # apart from check_run / admin_change


# --- 5. coordination (plan 2-5): release, bounded join, own connections only, join again ----------------------

class OwnConn:
    def __init__(self, on_close=None, fail=False):
        self.on_close, self.fail, self.closed = on_close, fail, False

    def close(self):
        if self.fail:
            raise OSError("synthetic close failure")
        self.closed = True
        if self.on_close:
            self.on_close()


class Coordinate(unittest.TestCase):
    def setUp(self):
        self.rec = g.Record(Path(tempfile.mkdtemp(prefix="ops_access_lock_test_")))
        self.addCleanup(shutil.rmtree, self.rec.folder, True)
        self.h = SimpleNamespace(rec=self.rec, threads=[], pauses=[])

    def kinds(self):
        return [e["kind"] for e in self.rec.doc["events"]]

    def held(self, pause):
        def run():
            pause.hook(ax.WRITE, "SELECT", ax.LOCK_PREFIX + " x", SimpleNamespace(pending_pid=1))
            return "product"
        return run

    def test_normal_end(self):
        pause = lay.Pause(ax.WRITE, "SELECT", ax.LOCK_PREFIX)
        co = ax.coordinate(self.h, "r2", [("product", self.held(pause)), ("admin", lambda: "admin")], pause=pause,
                           prove=lambda: {"ok": True}, owned=lambda: [], limit=2)
        self.assertEqual({k: v[0] for k, v in co.results.items()}, {"product": "ok", "admin": "ok"})
        self.assertEqual(co.cleanup, {"released": True, "release_errors": [], "joined": True, "closed": None,
                                      "still_alive": [], "pauses": []})
        self.assertEqual(ax.blocking_events(self.rec.path), [])
        self.assertTrue(pause.release.is_set())
        self.assertEqual(self.kinds(), ["coordination_started", "coordination", "coordination_ended"])

    def test_probe_failure_still_releases_joins_and_keeps_the_business_result(self):
        pause = lay.Pause(ax.WRITE, "SELECT", ax.LOCK_PREFIX)

        def prove():
            raise RuntimeError("probe")
        with self.assertRaises(lay.CheckFailed) as caught:
            ax.coordinate(self.h, "r2", [("product", self.held(pause))], pause=pause, prove=prove, owned=lambda: [],
                          limit=2)
        self.assertIn("probe failed", caught.exception.what)
        event = self.rec.find("coordination")[0]
        self.assertEqual((event["business"], event["probe"], event["cleanup"]["joined"]),
                         ({"product": "ok"}, {"probe_error": "RuntimeError"}, True))
        self.assertTrue(pause.release.is_set())

    def test_business_error_and_interrupt_are_kept_apart(self):
        def fails():
            raise ValueError("business")
        co = ax.coordinate(self.h, "r1", [("product", fails)], pause=None, prove=None, owned=lambda: [], limit=2)
        self.assertIsInstance(co.results["product"][1], ValueError)               # judged by the check, not lost
        self.assertEqual(self.rec.find("coordination")[-1]["business"], {"product": "error:ValueError"})

        def interrupted():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            ax.coordinate(self.h, "r1", [("product", interrupted)], pause=None, prove=None, owned=lambda: [], limit=2)

    def test_closing_own_connections_ends_the_thread(self):
        stop = threading.Event()
        conn = OwnConn(on_close=stop.set)
        co = ax.coordinate(self.h, "t1", [("product", lambda: stop.wait(10) and "ended")], pause=None, prove=None,
                           owned=lambda: [conn], limit=0.3)
        self.assertEqual(co.cleanup["closed"], ["closed"])
        self.assertEqual((co.cleanup["joined"], co.cleanup["still_alive"]), (True, []))
        self.assertNotIn("thread_not_ended", self.kinds())

    def test_an_unconfirmed_end_is_recorded_and_never_a_pass(self):
        stop = threading.Event()
        self.addCleanup(stop.set)
        conns = [OwnConn(fail=True), OwnConn()]
        with self.assertRaises(lay.CheckFailed) as caught:
            ax.coordinate(self.h, "d1", [("product", lambda: stop.wait(10))], pause=None, prove=None,
                          owned=lambda: conns, limit=0.2)
        self.assertEqual(caught.exception.kind, "harness_defect")
        event = self.rec.find("coordination")[-1]
        self.assertEqual(event["cleanup"]["closed"], ["close_failed:OSError", "closed"])
        self.assertEqual(event["cleanup"]["still_alive"], ["d1:product"])
        self.assertIn("thread_not_ended", self.kinds())
        self.assertIn("cleanup_incomplete", self.kinds())
        self.assertEqual(ax.blocking_events(self.rec.path), ["thread_not_ended", "cleanup_incomplete",
                                                             "coordination_unconfirmed"])

    def test_the_cleanup_process_reads_the_record_and_refuses(self):
        self.rec.event("thread_not_ended", check="c1b", threads=["c1b:admin_b"])
        script = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);"
                  "from pathlib import Path; from unittest import mock; import _ops_pg62 as g; "
                  "import _ops_real_layout as lay; import _ops_access_lock_real as ax;"
                  "rec = g.Record(Path(sys.argv[3]));"
                  "boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError('destructive cleanup called'));"
                  "p1 = mock.patch.object(g, 'single_run', lambda t=None: rec); p2 = mock.patch.object(lay, 'cleanup', boom);"
                  "p1.start(); p2.start(); sys.exit(ax.main(['cleanup']))")
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
        env.update(APP_ENV="test", DATABASE_URL="sqlite:///:memory:", PYTHON_DOTENV_DISABLED="1")
        env.pop("PYTHONPATH", None)
        done = subprocess.run([sys.executable, "-c", script, str(TESTS_DIR), str(BACKEND / "scripts"),
                               str(self.rec.folder)], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("R2 refused", done.stdout)


# --- 6. checks on a fake harness: W subcases, D1 branches, T1 origins -----------------------------------------
# Fakes only: every value below stands in for an admin read or a CLI result; none is PostgreSQL evidence. Expected
# values (versions, cursor, snapshot set) are fixed from the G1 baseline + plan + contract.

K1, K2 = "lexeme:9:40", "lexeme:9:41"
PLAN = SimpleNamespace(account_id=U, candidates=(SimpleNamespace(kind="lexeme", ref_id=L1, card_version=3),
                                                 SimpleNamespace(kind="lexeme", ref_id=L2, card_version=5)))


def base_state():
    return {"runs": 1, "status": "started", "cursor": 1, "finished": False, "results": [("lexeme", L1, "applied")],
            "cards": {K1: {"version": 4, "engine": "fsrs", "row": "l1-first"},
                      K2: {"version": 5, "engine": "legacy", "row": "l2-orig"}},
            "snapshots": {K1: {"version_before": 3, "row": "snap-l1"}}, "snapshot_count": 1}


def state_after(outcome):
    s = base_state()
    if outcome == "applied":
        s.update(status="completed", cursor=2, finished=True)
        s["cards"][K2] = {"version": 6, "engine": "fsrs", "row": "l2-new"}
        s["snapshots"][K2] = {"version_before": 5, "row": "snap-l2"}
        s["snapshot_count"] = 2
    elif outcome == "conflict":
        s.update(status="completed", cursor=2, finished=True)
    elif outcome == "failed":
        s.update(status="failed")
    return s


CLI = {"applied": ({"status": "ok", "phase": "completed", "results": {"already_applied": 1, "applied": 1}}, 0),
       "conflict": ({"status": "ok", "phase": "completed", "results": {"already_applied": 1, "conflict": 1}}, 5)}


def failed_cli(code):
    return {"status": "failed", "code": code, "phase": "after_start", "uncertain": True, "next": "status_required"}, 1


class FakeTx:
    def __init__(self, run, check_id):
        self.run_, self.check_id = run, check_id
        run.tx_count += 1
        self.pid, self.sqlstate, self.ended, self.pending = 7000 + run.tx_count, None, None, []
        self.conn = OwnConn()
        run.txs.append(self)

    def run(self, name, params=()):
        r = self.run_
        rows = r.scenario.get("rows", {}).get(name, 1)
        r.rec.event("admin_change", check=self.check_id, name=name, rows=rows)
        locked = name == "word_delete" or (name == "deactivate" and params[0] in r.scenario.get("product_locks", ()))
        if locked and r.product_locked.is_set() and not r.product_done.is_set():
            r.waiting[self.pid] = r.PRODUCT_PID                   # the product holds the share lock: wait
            r.product_done.wait(5)
            r.waiting.pop(self.pid, None)
        if rows:
            self.pending.append((name, params))
        return SimpleNamespace(rowcount=rows)

    def xid(self):
        return f"9{self.pid}"

    def commit(self):
        self.ended = "commit"
        for name, params in self.pending:
            self.run_.apply(name, params)
        self.run_.admin_end.set()

    def rollback(self):
        self.ended = "rollback"
        self.run_.admin_end.set()

    def close(self):
        pass


class FakeRun:
    """The harness of ONE W / T1 / D1 check: paths and word rows in memory, the product simulated by its CLI result,
    the waits by fake pg_blocking_pids answers. The REAL check functions, coordinate and judgement run on it."""

    PRODUCT_PID = 4242

    def __init__(self, rec, check_id, scenario):
        self.rec, self.check_id, self.scenario = rec, check_id, scenario
        self.target = TARGET
        self.pid = PID
        self.case = SimpleNamespace(check_id=check_id, keys=[("lexeme", U, L1), ("lexeme", U, L2)], plan=PLAN,
                                    db="fake", request=SimpleNamespace(account_id=U))
        self.cases = {check_id: self.case}
        self.evidence = {"baseline": {check_id: base_state()}, "outside": {check_id: {"b:lexeme:40": "b"}}}
        self.threads, self.pauses, self.txs, self.tx_count = [], [], [], 0
        self.subs = {200: True, 201: check_id in PLAN_TWO_PATH}
        self.words = {300: (100, L1), 301: (100, L2), 302: (101, L2)}
        self.word_text = {301: "w-a-l2"}
        self.now = None
        self.waiting: dict = {}
        self.product_locked, self.product_done, self.admin_end = threading.Event(), threading.Event(), threading.Event()
        self.resumes = 0

    def apply(self, name, params):
        if self.scenario.get("no_effect"):
            return                                                  # the statement "ran" but nothing changed
        if self.scenario.get("wrong_row") and name in ("deactivate", "reactivate"):
            params = (201 if params[0] == 200 else 200,) + tuple(params[1:])
        if name == "deactivate":
            self.subs[params[0]] = False
        elif name == "reactivate":
            self.subs[params[0]] = True
        elif name == "word_delete":
            self.words.pop(params[0], None)
        elif name == "word_restore":
            self.words[params[0]] = (params[1], params[2])
            self.word_text[params[0]] = self.scenario.get("restored_text", "w-a-l2")

    def paths(self, check_id):
        deck_sub = {100: 200, 101: 201}
        out = {}
        for name, lexeme in (("l1", L1), ("l2", L2)):
            out[name] = sorted([[deck_sub[d], w] for w, (d, lx) in self.words.items()
                                if lx == lexeme and self.subs[deck_sub[d]]])
        return out

    def state(self, case):
        return self.now or base_state()

    def outside(self, check_id, case):
        return {"b:lexeme:40": "b"}

    def admin_tx(self, check_id, owned):
        tx = FakeTx(self, check_id)
        owned.append(tx)
        return tx

    def blocking_pids(self, pid):
        if pid == self.PRODUCT_PID and self.waiting.get(pid):
            return [self.waiting[pid]]
        return [self.waiting[pid]] if pid in self.waiting else []

    def lock_rows(self, pid):
        if pid not in self.waiting:
            return []
        holder = self.waiting.get(pid)
        xid = self.backend_xid(holder) if holder == self.PRODUCT_PID else f"9{holder}"
        return [{"locktype": "transactionid", "mode": "ShareLock", "transactionid": xid, "relation": None}]

    def backend_xid(self, pid):
        return "777"

    def resume(self, case, *, hooks=None, trackers=None, approval_id=None):
        self.resumes += 1
        tracker = SimpleNamespace(pending_pid=self.PRODUCT_PID)
        if trackers is not None:
            trackers.append(tracker)
        if self.resumes > 1:                                    # T1's explicit resume
            self.now = state_after("applied")
            return self.result("applied")
        held = [tx for tx in self.txs if tx.ended is None and tx.pending]
        if held and not hooks:                                  # the admin holds first: the product waits on it
            self.waiting[self.PRODUCT_PID] = held[0].pid
            self.admin_end.wait(self.scenario.get("hold", 5))
            self.waiting.pop(self.PRODUCT_PID, None)
        if hooks:
            self.product_locked.set()
            for hook in hooks:
                hook(ax.WRITE, "SELECT", ax.LOCK_PREFIX + " x", tracker)
        outcome = self.scenario["outcome"](self)
        self.now = state_after(outcome)
        self.product_done.set()
        return self.result(outcome)

    def result(self, outcome):
        if outcome == "failed":
            out, code = failed_cli(self.scenario["code"])
            trace = {"settings": [{"value": "5000ms", "ok": True}], "sqlstates": self.scenario["sqlstates"],
                     "access_writes": []}
        else:
            out, code = CLI[outcome]
            trace = {"settings": [{"value": "5000ms", "ok": True}, {"value": "0", "ok": True}], "sqlstates": [],
                     "access_writes": []}
        return {"out": out, "code": code, "counts": None, "trackers": [], "trace": trace}


class FakeAdmin:
    """FAKE admin connection for the word-row read / check of the W checks (module `admin`)."""

    def __init__(self, run):
        self.run = run

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=()):
        r = self.run
        if query == ax.ADMIN_SQL["word_read"]:
            row = [301, 100, L2, 1, "c", None, None, None, None, None, r.word_text[301]] if 301 in r.words else None
            return SimpleNamespace(fetchone=lambda: row)
        if query.startswith("SELECT w::text FROM shared_deck_words"):
            return SimpleNamespace(fetchall=lambda: [(r.word_text[301],)] if 301 in r.words else [])
        raise AssertionError(query)


class FakeChecks(Blocked):
    def run_fake(self, check_id, fn, scenario):
        rec = self.record(f"20261029T05{len(os.listdir(self.folder)):04d}")
        run = FakeRun(rec, check_id, scenario)
        with mock.patch.object(ax, "admin", lambda db, pid, autocommit=True: FakeAdmin(run)), \
                mock.patch.object(lay, "WAIT_LIMIT", 5):
            details = fn(run)
        return run, details, json.loads(rec.path.read_text(encoding="utf-8"))

    @staticmethod
    def by_paths(run):
        return "applied" if run.paths("x")["l2"] or run.scenario.get("locked_first") else "conflict"

    def test_w_checks_pass_with_every_required_subcase_recorded(self):
        for check_id, fn, want in (("w1a", lambda h: ax.w1_locked_then_deleted(h, "w1a"), "applied"),
                                   ("w1b", lambda h: ax.w1_locked_then_deleted(h, "w1b"), "applied"),
                                   ("w2a", lambda h: ax.w2_deleted_first(h, "w2a", "conflict"), "conflict"),
                                   ("w2b", lambda h: ax.w2_deleted_first(h, "w2b", "applied"), "applied")):
            with self.subTest(check=check_id):
                locked_first = check_id.startswith("w1")
                run, details, saved = self.run_fake(check_id, fn, {"outcome": self.by_paths, "locked_first": locked_first})
                self.assertEqual(details["cli"]["results"], CLI[want][0]["results"])
                names = {e["name"] for e in saved["events"] if e["kind"] == "subcase" and e["ok"]}
                required = set(ax.COMMON) | {"admin_attribution", "word_restored", "paths_restored"} | (
                    {"admin_waited", "paths_after_delete"} if locked_first else {"product_waited"})
                self.assertTrue(required <= names, required - names)
                proofs = [e for e in saved["events"] if e["kind"] == "lock_wait_proof"]
                self.assertEqual(len(proofs), 1)
                self.assertTrue(any(r["transactionid"] == proofs[0]["holder_xid"] and r["relation"] is None
                                    for r in proofs[0]["ungranted"]))
                self.assertEqual(ax.path_problems(run, check_id, run.paths(check_id)), [])     # restored as 4-0

    def test_a_missing_or_failed_restore_fails_the_w_check(self):
        with self.assertRaises(lay.CheckFailed) as caught:
            self.run_fake("w2a", lambda h: ax.w2_deleted_first(h, "w2a", "conflict"),
                          {"outcome": self.by_paths, "restored_text": "w-a-l2-other"})
        self.assertIn("word_restored", caught.exception.what)
        rec = self.record("20261029T059999")
        rec.event("subcase", check="w1a", name="cli", ok=True)
        with self.assertRaises(lay.CheckFailed) as caught:
            ax.require_subcases(SimpleNamespace(rec=rec), "w1a", ("cli", "word_restored"))
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_t1_keeps_server_sqlstate_product_code_and_cli_apart(self):
        run, details, saved = self.run_fake("t1", ax.t1_lock_timeout, {"outcome": lambda r: "failed", "hold": 1.5,
                                                                        "code": "migration_access_lock_timeout",
                                                                        "sqlstates": [{"statement": "SELECT",
                                                                                       "sqlstate": "55P03"}]})
        self.assertEqual(details["origin"], {"server": ["55P03"], "product_code": "migration_access_lock_timeout"})
        self.assertEqual(details["cli"]["exit"], 1)
        self.assertEqual(run.resumes, 2)                                        # one run, one EXPLICIT resume
        names = {e["name"] for e in saved["events"] if e["kind"] == "subcase"}
        self.assertTrue({"server_sqlstate", "explicit_resume", "resumed_state", "product_waited"} <= names)
        with self.assertRaises(lay.CheckFailed):                               # a product code without the server's
            self.run_fake("t1", ax.t1_lock_timeout, {"outcome": lambda r: "failed", "hold": 1.5,
                                                     "code": "migration_access_lock_timeout", "sqlstates": []})

    def test_deadlock_branches(self):
        p_cli = {"code": "migration_access_deadlock", "results": None}
        a_cli = {"code": None, "results": {"already_applied": 1, "applied": 1}}
        self.assertEqual(ax.deadlock_branch(p_cli, ["40P01"], None, True), "P")
        self.assertEqual(ax.deadlock_branch(a_cli, [], "40P01", False), "A")
        for args in ((p_cli, ["55P03"], None, True), (p_cli, ["40P01"], "40P01", True), (a_cli, [], None, True),
                     ({"code": "migration_access_lock_timeout"}, ["55P03"], None, True)):
            with self.subTest(args=args):
                self.assertIsNone(ax.deadlock_branch(*args))

    def test_d1_records_whether_the_product_40p01_was_verified(self):
        def admin_victim(run):
            run.txs[0].sqlstate = "40P01"
            return "applied"
        for label, scenario, branch in (
                ("P", {"outcome": lambda r: "failed", "code": "migration_access_deadlock",
                       "sqlstates": [{"statement": "SELECT", "sqlstate": "40P01"}]}, "P"),
                ("A", {"outcome": admin_victim}, "A")):
            with self.subTest(branch=label):
                original = FakeTx.run

                def run_admin(tx, name, params=()):
                    if name == "card_request" and label == "A":
                        tx.sqlstate = "40P01"
                        raise psycopg.errors.DeadlockDetected("Driver-Text")
                    return original(tx, name, params)
                with mock.patch.object(FakeTx, "run", run_admin):
                    run, details, saved = self.run_fake("d1", ax.d1_deadlock, scenario)
                self.assertEqual((details["branch"], details["product_40p01_verified"]), (branch, branch == "P"))
                event = [e for e in saved["events"] if e["kind"] == "deadlock_branch"][-1]
                self.assertEqual(event["product_40p01_verified"], branch == "P")


# --- 6b. V1 review defects (regressions) ------------------------------------------------------------------------

class ConcurrentRecord(unittest.TestCase):
    """Defect 1: two writers of one record. The first writer is held between its in-memory update and its save
    until the second has saved (or a short limit); the record must keep both on disk, valid JSON, and a failed save
    removes only its own entry."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ops_access_lock_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def race(self, rec):
        first_in, second_done = threading.Event(), threading.Event()
        real_dumps = g.json.dumps

        def dumps(doc, *a, **k):
            if threading.current_thread().name == "writer-1" and not first_in.is_set():
                text = real_dumps(doc, *a, **k)                     # writer 1 has its text, not yet on disk
                first_in.set()
                second_done.wait(1.0)                               # let writer 2 save first (if it can)
                return text
            return real_dumps(doc, *a, **k)

        def second():
            first_in.wait(5)
            rec.event("second")
            second_done.set()
        threads = [threading.Thread(target=lambda: rec.event("first"), name="writer-1"),
                   threading.Thread(target=second, name="writer-2")]
        with mock.patch.object(g.json, "dumps", dumps):
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
        return json.loads(rec.path.read_text(encoding="utf-8"))

    def test_the_shared_record_loses_an_event_without_the_runner_lock(self):
        base = g.Record(self.folder)
        saved = self.race(base)
        self.assertEqual([e["kind"] for e in base.doc["events"]], ["first", "second"])
        self.assertEqual([e["kind"] for e in saved["events"]], ["first"])      # the defect, kept as evidence

    def test_the_runner_record_keeps_both_events_on_disk(self):
        rec = ax.LockedRecord(self.folder)
        saved = self.race(rec)
        self.assertEqual([e["kind"] for e in saved["events"]], ["first", "second"])
        self.assertEqual(saved["events"], rec.doc["events"])
        self.assertEqual(ax.LockedRecord(self.folder).read_saved()["events"], saved["events"])

    def test_a_failed_save_removes_only_its_own_entry(self):
        rec = ax.LockedRecord(self.folder)
        rec.event("kept")
        with self.assertRaises(TypeError):
            rec.event("broken", value=object())                     # cannot be serialized: nothing written
        rec.result("k1", "pass", details={})
        saved = json.loads(rec.path.read_text(encoding="utf-8"))
        self.assertEqual(([e["kind"] for e in saved["events"]], [r["check"] for r in saved["results"]]),
                         (["kept"], ["k1"]))
        self.assertEqual(saved["events"], rec.doc["events"])

    def test_check_access_lock_uses_the_runner_record(self):
        run = self.folder / "20261029T070000"
        run.mkdir()
        g.Record(run).event("server_started", pid=PID)
        seen = []

        class Stop(Exception):
            pass

        def harness(rec):
            seen.append(rec)
            raise Stop()
        with mock.patch.object(ax, "LQ4_CHANGES_APPROVED", True), \
                mock.patch.object(g, "single_run", lambda t=None: g.Record(run)), \
                mock.patch.object(ax, "Harness", harness), self.assertRaises(Stop):
            ax.check_access_lock()
        self.assertIsInstance(seen[0], ax.LockedRecord)


class PauseHolding(Blocked):
    """Defect 2: a pause that timed out (the product went on by itself) is never "still held"."""

    def test_c1a_passes_when_only_the_returned_path_is_locked(self):
        rec = self.record("20261029T071000")
        run = FakeRun(rec, "c1a", {"outcome": lambda r: "applied", "product_locks": (200,)})
        with mock.patch.object(ax, "admin", lambda db, pid, autocommit=True: FakeAdmin(run)):
            details = ax.c1a_only_returned_path(run)
        self.assertEqual(details["cli"]["exit"], 0)

    def test_c1a_fails_when_b_is_also_blocked_until_the_pause_times_out(self):
        rec = self.record("20261029T071100")
        run = FakeRun(rec, "c1a", {"outcome": lambda r: "applied", "product_locks": (200, 201)})
        with mock.patch.object(ax, "admin", lambda db, pid, autocommit=True: FakeAdmin(run)), \
                mock.patch.object(ax, "PAUSE_LIMIT", 0.5), self.assertRaises(lay.CheckFailed):
            ax.c1a_only_returned_path(run)

    def test_a_timed_out_or_unreached_pause_is_a_harness_defect(self):
        h = SimpleNamespace(rec=self.record("20261029T071200"), threads=[], pauses=[])
        pause = ax.HoldPause(ax.WRITE, "SELECT", ax.LOCK_PREFIX, limit=0.2)

        def held():
            pause.hook(ax.WRITE, "SELECT", ax.LOCK_PREFIX + " x", SimpleNamespace(pending_pid=1))
            return "product"
        with self.assertRaises(lay.CheckFailed) as caught:
            ax.coordinate(h, "r2", [("product", held)], pause=pause, prove=lambda: time.sleep(0.5) or {},
                          owned=lambda: [], limit=2)
        self.assertIn("pause", caught.exception.what)
        unreached = ax.HoldPause(ax.WRITE, "SELECT", ax.LOCK_PREFIX)
        with self.assertRaises(lay.CheckFailed) as caught:
            ax.coordinate(h, "c1b", [("product", lambda: "ended early")], pause=None, prove=None, owned=lambda: [],
                          limit=2, release=(unreached,))
        self.assertIn("pause", caught.exception.what)


class Interrupts(Blocked):
    """Defect 3: the business interrupt is the SAME object after every cleanup step was tried; cleanup and probe
    failures are recorded apart; an unconfirmed end stays blocking on disk."""

    def h(self):
        rec = ax.LockedRecord(self.record(f"20261029T0720{len(os.listdir(self.folder)):02d}").folder)
        return SimpleNamespace(rec=rec, threads=[], pauses=[])

    def test_business_exit_survives_an_interrupt_while_closing(self):
        h = self.h()
        stop = threading.Event()
        exit9 = SystemExit(9)

        def worker():
            stop.wait(10)
            raise exit9

        class Interrupting:
            def close(self):
                stop.set()
                raise KeyboardInterrupt()
        other = OwnConn()
        with self.assertRaises(SystemExit) as caught:
            ax.coordinate(h, "r2", [("product", worker)], pause=None, prove=None,
                          owned=lambda: [Interrupting(), other], limit=0.3)
        self.assertIs(caught.exception, exit9)
        self.assertEqual(caught.exception.code, 9)
        self.assertIsNone(caught.exception.__context__)
        self.assertTrue(other.closed)                                   # the remaining cleanup was tried
        event = h.rec.find("coordination")[-1]
        self.assertEqual(event["cleanup"]["closed"], ["close_interrupted:KeyboardInterrupt", "closed"])
        self.assertEqual((event["cleanup"]["joined"], event["business"]), (True, {"product": "interrupt:SystemExit"}))
        self.assertEqual(ax.blocking_events(h.rec.path), [])                 # end confirmed: not blocking

    def test_business_exit_survives_a_probe_error(self):
        h = self.h()
        exit9 = SystemExit(9)

        def worker():
            raise exit9

        def prove():
            time.sleep(0.1)
            raise RuntimeError("probe Driver-Text")
        with self.assertRaises(SystemExit) as caught:
            ax.coordinate(h, "r2", [("product", worker)], pause=None, prove=prove, owned=lambda: [], limit=2)
        self.assertIs(caught.exception, exit9)
        event = h.rec.find("coordination")[-1]
        self.assertEqual(event["probe"], {"probe_error": "RuntimeError"})
        self.assertNotIn("Driver-Text", h.rec.path.read_text(encoding="utf-8"))

    def test_an_unconfirmed_end_blocks_even_if_the_failure_record_cannot_be_saved(self):
        h = self.h()
        stop = threading.Event()
        self.addCleanup(stop.set)
        real_event = h.rec.event

        def failing(kind, **facts):
            if kind != "coordination_started":
                raise OSError("disk")
            return real_event(kind, **facts)
        h.rec.event = failing
        with self.assertRaises(BaseException):
            ax.coordinate(h, "d1", [("product", lambda: stop.wait(10))], pause=None, prove=None, owned=lambda: [],
                          limit=0.2)
        self.assertEqual(ax.blocking_events(h.rec.path), ["coordination_unconfirmed"])

    def test_an_interrupt_in_a_check_stops_the_rest_with_its_own_exit_code(self):
        rec = self.record("20261029T072900")
        rec.event("server_started", pid=PID)
        exit9 = SystemExit(9)

        def check(name):
            def run(h_):
                if name == "k3":
                    raise exit9
                return {}
            return run
        checks = [(n, check(n)) for n in PLAN_CHECKS]
        with mock.patch.object(ax, "LQ4_CHANGES_APPROVED", True), mock.patch.object(g, "single_run", lambda t=None: rec), \
                mock.patch.object(ax, "Harness", lambda r: SimpleNamespace(start=lambda: None, close=lambda: ax.FinalCleanup())), \
                mock.patch.object(ax, "g0_gate", lambda h_: {}), mock.patch.object(ax, "g1_gate", lambda h_: {}), \
                mock.patch.object(ax, "CHECKS", checks), contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit) as caught:
            ax.main(["check-access-lock"])
        self.assertIs(caught.exception, exit9)
        saved = json.loads(rec.path.read_text(encoding="utf-8"))
        not_run = [e for e in saved["events"] if e["kind"] == "not_run"]     # the final cleanup record follows it
        self.assertEqual(saved["events"][-1]["kind"], "final_cleanup_ended")
        self.assertEqual(not_run[-1], {"kind": "not_run", "after": "k3", "interrupted": "SystemExit",
                                               "checks": list(PLAN_CHECKS[PLAN_CHECKS.index("k3") + 1:])})
        self.assertFalse([r for r in saved["results"] if r["check"] in PLAN_CHECKS[PLAN_CHECKS.index("k3"):]])

class UnmatchedStartProcess(unittest.TestCase):
    """A separate cleanup PROCESS reads an unmatched `coordination_started` from disk and refuses R2 (new process
    allowed for this check only; R2 itself is replaced by a function that fails if called)."""

    def test_the_cleanup_process_refuses_an_unmatched_start(self):
        folder = Path(tempfile.mkdtemp(prefix="ops_access_lock_test_"))
        self.addCleanup(shutil.rmtree, folder, True)
        rec = g.Record(folder)
        rec.event("coordination_started", check="r2", token="r2:1")
        script = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2]);"
                  "from pathlib import Path; from unittest import mock; import _ops_pg62 as g; "
                  "import _ops_real_layout as lay; import _ops_access_lock_real as ax;"
                  "rec = g.Record(Path(sys.argv[3]));"
                  "boom = lambda *a, **k: (_ for _ in ()).throw(AssertionError('destructive cleanup called'));"
                  "p1 = mock.patch.object(g, 'single_run', lambda t=None: rec); p2 = mock.patch.object(lay, 'cleanup', boom);"
                  "p1.start(); p2.start(); sys.exit(ax.main(['cleanup']))")
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
        env.update(APP_ENV="test", DATABASE_URL="sqlite:///:memory:", PYTHON_DOTENV_DISABLED="1")
        env.pop("PYTHONPATH", None)
        done = REAL_RUN([sys.executable, "-c", script, str(TESTS_DIR), str(BACKEND / "scripts"), str(rec.folder)],
                        capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("coordination_unconfirmed", done.stdout)


class AdminChanges(Blocked):
    """Defect 4: R5 / R6 need the admin change of exactly one row, committed, and the paths right after it as the
    record and contract say (R5: none; R6: B only); the revert likewise."""

    def run_fake(self, check_id, fn, **scenario):
        rec = self.record(f"20261029T0740{len(os.listdir(self.folder)):02d}")
        run = FakeRun(rec, check_id, dict({"outcome": lambda r: "applied"}, **scenario))
        with mock.patch.object(ax, "admin", lambda db, pid, autocommit=True: FakeAdmin(run)):
            return fn(run)

    def test_r5_and_r6_pass_with_real_changes(self):
        self.assertEqual(self.run_fake("r5", ax.r5_after_commit)["cli"]["exit"], 0)
        self.assertEqual(self.run_fake("r6", ax.r6_two_paths)["cli"]["exit"], 0)

    def test_zero_rows_wrong_row_or_no_loss_fail(self):
        for check_id, fn in (("r5", ax.r5_after_commit), ("r6", ax.r6_two_paths)):
            for label, scenario in (("zero rows", {"rows": {"deactivate": 0}}),
                                    ("zero rows on revert", {"rows": {"reactivate": 0}}),
                                    ("other row", {"wrong_row": True}), ("no loss", {"no_effect": True})):
                with self.subTest(check=check_id, case=label), self.assertRaises(lay.CheckFailed):
                    self.run_fake(check_id, fn, **scenario)


# --- 6c. the final harness close (plan 13-3): the REAL main -> check_access_lock -> Harness.close ----------------
# REPLACED: only `Harness.start` (it would rotate passwords on a real server and make keys) installs fake
# connections, a fake key holder and one temporary deploy folder; checks / gates are stubs. `Harness.close` and the
# end of `check_access_lock` / `main` are the REAL ones.

SECRET = "synthetic-secret-final-close"


class CloseConn:
    def __init__(self, log, name, error=None):
        self.log, self.name, self.error = log, name, error

    def close(self):
        self.log.append(self.name)
        if self.error is not None:
            raise self.error


class FakeKeys:
    def __init__(self, log, error=None):
        self.log, self.error = log, error

    def close(self):
        self.log.append("keys")
        if self.error is not None:
            raise self.error


class FinalClose(Blocked):
    def prepared(self):
        run = self.folder / f"20261029T08{len(os.listdir(self.folder)):04d}"
        run.mkdir()
        target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                  "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "provider_roles": ["jpvk_read", "jpvk_write"],
                  "databases": {d: {} for d in lay.PG68.business_databases}, "synthetic": TARGET["synthetic"]}
        data = json.dumps(target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        return run

    def run_main(self, *, raise_in=None, error=None, first=None, keys=None, start_error=None, rmtree=None):
        run = self.prepared()
        log: list = []
        deploy = Path(tempfile.mkdtemp(prefix="ops_pg68_deploy_"))
        self.addCleanup(shutil.rmtree, deploy, True)
        seen: dict = {}

        def start(h):
            seen["h"] = h
            h.connections = [CloseConn(log, "conn1", first), CloseConn(log, "conn2")]
            h.keys = FakeKeys(log, keys)
            h.folders = [str(deploy)]
            h.passwords = {"jpvk_read": SECRET, "jpvk_write": SECRET}
            if start_error is not None:
                raise start_error

        def check(name):
            def fn(h_):
                if name == raise_in:
                    raise error
                return {}
            return fn
        out = io.StringIO()
        patches = [mock.patch.object(ax, "LQ4_CHANGES_APPROVED", True),
                   mock.patch.object(g, "single_run", lambda t=None: g.Record(run)),
                   mock.patch.object(ax.Harness, "start", start), mock.patch.object(ax, "g0_gate", lambda h_: {}),
                   mock.patch.object(ax, "g1_gate", lambda h_: {}), mock.patch.object(ax, "post_check", lambda h_: {}),
                   mock.patch.object(ax, "CHECKS", [(n, check(n)) for n in PLAN_CHECKS]),
                   contextlib.redirect_stdout(out)]
        if rmtree is not None:
            patches.append(mock.patch.object(ax.shutil, "rmtree", rmtree))
        caught = None
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            try:
                code = ax.main(["check-access-lock"])
            except BaseException as raised:            # the outcome under test, kept for the assertions
                caught, code = raised, None
        saved = json.loads((run / "record.json").read_text(encoding="utf-8"))
        text = out.getvalue() + ("".join(traceback.format_exception(caught)) if caught is not None else "")
        return SimpleNamespace(caught=caught, code=code, log=log, h=seen.get("h"), deploy=deploy, saved=saved,
                               text=text, run=run)

    def assert_all_tried(self, r):
        self.assertEqual(r.log, ["conn1", "conn2", "keys"])                     # every step, in order
        self.assertFalse(r.deploy.exists())                                      # this run's deploy folder
        self.assertEqual(r.h.passwords, {})                                      # memory secrets cleared
        self.assertNotIn(SECRET, r.text)
        self.assertNotIn("Driver-Text", r.text)

    def kinds(self, r):
        return [e["kind"] for e in r.saved["events"]]

    def test_business_exit_kept_over_a_close_interrupt_and_every_step_tried(self):
        exit9 = SystemExit(9)
        r = self.run_main(raise_in="k1", error=exit9, first=KeyboardInterrupt("Driver-Text"))
        self.assertIs(r.caught, exit9)
        self.assertEqual(r.caught.code, 9)
        self.assertIsNone(r.caught.__context__)
        self.assert_all_tried(r)
        final = [e for e in r.saved["events"] if e["kind"] == "final_cleanup"][-1]
        self.assertEqual(final["failures"], ["connection_close_interrupted"])
        self.assertIn("cleanup_incomplete", self.kinds(r))
        self.assertIn("final_cleanup_unconfirmed", ax.blocking_events(r.run / "record.json"))
        not_run = [e for e in r.saved["events"] if e["kind"] == "not_run"][-1]
        self.assertEqual((not_run["after"], not_run["interrupted"], not_run["checks"]), ("k1", "SystemExit",
                                                                                         list(PLAN_CHECKS[1:])))

    def test_keyboard_interrupt_kept_over_a_cleanup_exit(self):
        interrupt = KeyboardInterrupt()
        r = self.run_main(raise_in="k2a", error=interrupt, keys=SystemExit(3))
        self.assertIs(r.caught, interrupt)
        self.assert_all_tried(r)

    def test_an_ordinary_error_in_flight_is_kept_over_cleanup_errors_and_interrupts(self):
        error = RuntimeError("Driver-Text start")
        r = self.run_main(start_error=error, first=KeyboardInterrupt(), keys=OSError("Driver-Text"))
        self.assertIs(r.caught, error)
        self.assertIsNone(r.caught.__context__)
        self.assertEqual(r.log, ["conn1", "conn2", "keys"])
        self.assertFalse(r.deploy.exists())
        final = [e for e in r.saved["events"] if e["kind"] == "final_cleanup"][-1]
        self.assertEqual(final["failures"], ["connection_close_interrupted", "keys_cleanup_failed"])

    def test_close_and_key_failures_never_skip_the_rest(self):
        for keys in (OSError("Driver-Text"), KeyboardInterrupt()):
            with self.subTest(keys=type(keys).__name__):
                r = self.run_main(first=OSError("Driver-Text"), keys=keys)
                self.assert_all_tried(r)
                if isinstance(keys, KeyboardInterrupt):
                    self.assertIs(r.caught, keys)                           # no error in flight: the interrupt
                else:
                    self.assertEqual(r.code, 1)                              # never "cleaned" while failing
                    self.assertIn("final cleanup", r.text)
                final = [e for e in r.saved["events"] if e["kind"] == "final_cleanup"][-1]
                self.assertEqual(final["failures"][0], "connection_close_failed")
                self.assertNotIn("final_cleanup_ended", self.kinds(r))

    def test_a_deploy_folder_that_stays_is_a_failure(self):
        r = self.run_main(rmtree=lambda path, *a, **k: None)                    # removal "returned", folder stays
        self.assertEqual(r.code, 1)
        final = [e for e in r.saved["events"] if e["kind"] == "final_cleanup"][-1]
        self.assertEqual(final["failures"], ["deploy_folder_unconfirmed"])
        self.assertEqual(r.h.passwords, {})

    def test_deploy_absence_check_is_protected_and_secrets_are_always_cleared(self):
        actual_exists, actual_remove = ax.os.path.lexists, ax.shutil.rmtree
        for primary, failure in ((SystemExit(9), KeyboardInterrupt("Driver-Text")),
                                 (None, SystemExit(3)), (None, OSError(SECRET))):
            with self.subTest(primary=type(primary).__name__, failure=type(failure).__name__):
                removed = set()

                def remove(path, *args, **kwargs):
                    actual_remove(path, *args, **kwargs)
                    removed.add(os.fspath(path))

                def exists(path):
                    if os.fspath(path) in removed:
                        raise failure
                    return actual_exists(path)

                with mock.patch.object(ax.os.path, "lexists", exists):
                    r = self.run_main(raise_in="k1" if primary is not None else None,
                                      error=primary, rmtree=remove)
                self.assert_all_tried(r)
                if primary is not None:
                    self.assertIs(r.caught, primary)
                    self.assertEqual(r.caught.code, 9)
                elif isinstance(failure, Exception):
                    self.assertEqual(r.code, 1)
                    self.assertIsNone(r.caught)
                else:
                    self.assertIs(r.caught, failure)
                    self.assertEqual(r.caught.code, 3)
                if r.caught is not None:
                    self.assertIsNone(r.caught.__context__)
                    self.assertIsNone(r.caught.__cause__)
                final = [e for e in r.saved["events"] if e["kind"] == "final_cleanup"][-1]
                self.assertEqual(final["failures"], ["deploy_folder_failed" if isinstance(failure, Exception)
                                                    else "deploy_folder_interrupted"])
                self.assertNotIn("final_cleanup_ended", self.kinds(r))
                self.assertIn("final_cleanup_unconfirmed", ax.blocking_events(r.run / "record.json"))

    def test_a_clean_end_is_confirmed_on_disk(self):
        r = self.run_main()
        self.assertEqual(r.code, 0)
        self.assert_all_tried(r)
        self.assertIn("final_cleanup_ended", self.kinds(r))
        self.assertEqual(ax.blocking_events(r.run / "record.json"), [])

    def test_an_unsaved_failure_record_still_blocks(self):
        run = None
        real_event = ax.LockedRecord.event

        def event(self_, kind, **facts):
            if kind in ("final_cleanup", "cleanup_incomplete", "final_cleanup_ended"):
                raise OSError("disk")
            return real_event(self_, kind, **facts)
        with mock.patch.object(ax.LockedRecord, "event", event):
            r = self.run_main(first=OSError("x"))
        self.assertEqual(r.code, 1)
        self.assertEqual(ax.blocking_events(r.run / "record.json"), ["final_cleanup_unconfirmed"])


# --- 7. the REAL Harness.case wiring and the REAL observation path -------------------------------------------------

class CasePath(unittest.TestCase):
    """The REAL `Harness` init (record binding, liveness), `Harness.case` (deploy folder, manifest, I0 / A0 / E0 / E1
    signed with the test-only temporary OpenSSH keys, the CLI `run_dry_run` with its REAL pre-check, the REAL
    counted connector and `Harness.driver` with the REAL business matrix / post-connect check) and `observe_role`
    through the REAL adapter and provider. REPLACED: the guarded driver's connection (fake), the provider path
    behind the CLI product connector for the plan dry-run (calls the given driver once and hands the connection
    over), and the product dry_run body (returns real plan candidates). The certificate is fake bytes."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(ax.op.osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = ax.sigtests.Keys()

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()

    def setUp(self):
        real_popen = subprocess.Popen

        def only_keygen(args, *a, **k):
            if os.path.normcase(str(args[0])) != os.path.normcase(ax.op.osig.SSH_KEYGEN):
                raise AssertionError("an external entry point was called")
            return real_popen(args, *a, **k)
        self.guards: list = []
        test = self

        class FakeGuard:
            def __init__(self, manifest, deploy_root, folder, target=None):
                test.assertIs(target, T)

            def driver(self, **kwargs):
                test.guards.append(dict(kwargs))
                return test.conn(kwargs["user"])
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", only_keygen),
                      mock.patch.object(g, "listener_pids", forbidden), mock.patch.object(g, "admin_connect", forbidden),
                      mock.patch.object(g, "postmaster_pid", forbidden), mock.patch.object(lay.real, "make_tls", forbidden),
                      mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.object(g, "Guard", FakeGuard),
                      mock.patch.object(ax.Harness, "ca_pem", lambda self: b"-----synthetic ca-----\n"),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_access_lock_case_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        run = self.folder / "20261029T060000"
        run.mkdir()
        self.db = ax.CHECK_DB["r2"]
        self.target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                       "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                       "system_identifier": "1", "provider_roles": ["jpvk_read", "jpvk_write"],
                       "admin_role": "jpvk_admin", "roles": {"jpvk_read": 101, "jpvk_write": 102},
                       "databases": {d: {"oid": 500 + i, "identity_value": f"pg68-{i}-n",
                                         "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                     for i, d in enumerate(lay.PG68.business_databases)},
                       "synthetic": {"a": {"user_id": 2, "personal": {}, "lexeme": [1, 2]}, "access": ACCESS}}
        data = json.dumps(self.target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        self.h = ax.Harness(rec)
        self.h.keys = self.keys
        self.h.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.h.passwords = {"jpvk_read": "synthetic-password-r", "jpvk_write": "synthetic-password-w"}
        self.addCleanup(lambda: [shutil.rmtree(f, True) for f in self.h.folders])
        self.observing, self.servers, self.options = False, [], {}

    def conn(self, user):
        if self.observing:
            server = ObservationServer(self, user, **self.options.get(user, {}))
            self.servers.append(server)
            return server
        return CaseConn(self, user)

    def candidates(self):
        ax.ar.fix_app_environment()
        from app.srs.engine import DEFAULT_CONFIG
        digest = hashlib.sha256(b"[]").hexdigest()
        items = [SimpleNamespace(key=SimpleNamespace(kind="lexeme", user_id=2, ref_id=r), card_fingerprint=None,
                                 logs_fingerprint=digest, card_version=None, quality="unavailable",
                                 flags=("card_or_access_missing",), values_json=None, last_log_id=0, reconversion=None,
                                 restart_json=None) for r in (1, 2)]
        data = ax.pfile.serialize_plan(db_identity=ax.pf.db_identity(), account_id=2, job_key=ax.RUN_KEY,
                                       config_version=DEFAULT_CONFIG.config_version,
                                       product_fingerprint=flow.FlowBase.product(
                                           SimpleNamespace(config_version=lambda: DEFAULT_CONFIG.config_version), items),
                                       candidates=items)
        path = self.folder / "seed_plan.json"
        ax.pfile.write_plan_file(str(path), data)
        return ax.pfile.to_candidates(ax.pfile.read_plan_file(str(path)))

    def run_case(self):
        candidates = self.candidates()
        lists: list = []

        def fake_product(inputs, expected, driver):
            def connector(read_only=False):
                raw = driver(host=g.HOST, port=str(T.port), dbname=inputs.target.database, user=ax.READ,
                             sslmode="verify-full")

                class Handed:
                    def __enter__(self):
                        return raw

                    def __exit__(self, *exc):
                        raw.close()
                        return False
                return Handed()
            return connector

        def dry_run(keys, *, connect=None):
            with connect(read_only=True):
                pass
            return candidates
        real_run = ax.RunScopes.run

        def scope_run(self_, counts, trackers, **kw):
            lists.append(("scope", trackers))
            return real_run(self_, counts, trackers, **kw)
        real_driver = ax.Harness.driver

        def driver(self_, inputs, counts, trackers, hooks=None):
            lists.append(("driver", trackers))
            return real_driver(self_, inputs, counts, trackers, hooks)
        ax.ar.fix_app_environment()
        from app.srs import migration
        with mock.patch.object(ax, "ORIGINAL_CONNECTOR", fake_product), mock.patch.object(ax.RunScopes, "run", scope_run), \
                mock.patch.object(ax.Harness, "driver", driver), mock.patch.object(migration, "dry_run", dry_run):
            case = self.h.case("r2")
        return case, lists

    def test_case_binds_target_inputs_plan_and_one_counted_list(self):
        case, lists = self.run_case()
        (s, scope_list), (d, driver_list) = lists
        self.assertEqual((s, d), ("scope", "driver"))
        self.assertIs(scope_list, driver_list)                                   # one list for scope and driver
        self.assertEqual(len(scope_list), 1)
        self.assertIsInstance(scope_list[0], ax.AccessTracked)
        self.assertEqual([k["user"] for k in self.guards], ["jpvk_read"])
        self.assertEqual(self.guards[0]["dbname"], self.db)
        self.assertEqual((case.db, case.keys), (self.db, [("lexeme", 2, 1), ("lexeme", 2, 2)]))
        data = Path(case.plan_path).read_bytes()
        self.assertEqual(case.plan.artifact_sha256, hashlib.sha256(data).hexdigest())
        a0 = json.loads(case.a0)
        self.assertEqual((a0["format_version"], a0["kind"], a0["steps"][1]["args"]), (3, "apply", {"batch_size": "1"}))
        self.assertEqual(a0["steps"][1]["profile"], ax.pv.expected_profile_fingerprint(
            ax.expected_profiles(self.db)[1], role="jpvk_write", access="write"))
        write, read = self.h.resume_inputs(case, 1, "app-0000000000000682")
        an = json.loads(write.approval)
        self.assertEqual((an["approval_id"], an["steps"][1]["command"], an["supersedes"]["approval_id"]),
                         ("app-0000000000000682", "resume", "app-0000000000000680"))
        self.assertEqual((write.target.database, read.target.database), (self.db, self.db))

    def observe(self, case, role, **options):
        self.observing, self.servers, self.options = True, [], {role: options}
        self.guards.clear()
        try:
            return self.h.observe_role(case, role)
        finally:
            self.observing, self.options = False, {}

    def test_reobservation_is_1_1_0_0_0_for_both_roles_and_refuses_missing_or_excess(self):
        case, _ = self.run_case()
        for role in (ax.READ, ax.WRITE):
            with self.subTest(role=role):
                seen = self.observe(case, role)
                self.assertEqual(seen, {"result": "matches_contract", "counts": ax.REOBSERVED})
                self.assertEqual(self.servers[0].commits, 0)
                self.assertTrue(self.servers[0].queries)                         # the real observer read the catalog
        missing = ("table", "public", "user_deck_subscriptions", "updated_at", "UPDATE")
        for options, code in (({"missing": (missing,)}, "observed_privileges_missing"),
                              ({"extra": (("table", "public", "user_deck_subscriptions", "", "UPDATE"),)},
                               "observed_privileges_excess")):
            with self.subTest(code=code):
                seen = self.observe(case, ax.WRITE, **options)
                self.assertEqual((seen["result"], seen["counts"]["handed"]), (code, 0))


class CaseConn:
    def __init__(self, test, user):
        target, db = test.target, test.db
        self.facts = {"server_addr": "127.0.0.1", "server_port": T.port, "version": "180006", "dbname": db,
                      "db_oid": target["databases"][db]["oid"], "role_oid": target["roles"][user],
                      "object_oids": [target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                      "identity": [target["databases"][db]["identity_value"]]}
        self.closed = False
        self.info = SimpleNamespace(backend_pid=4242)

    def cursor(self, row_factory=None):
        return FactsConn(self.facts).cursor()

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class ObservationServer:
    """FAKE server of ONE connection behind the real adapter and provider (as in the PG67 guard, bound to PG68):
    the guard's post-connect facts, the observer's catalog built from the CONTRACT profile, a commit counter."""

    def __init__(self, test, user, *, extra=(), missing=()):
        import test_ops_observer as to
        self.to = to
        target, db = test.target, test.db
        access = "read" if user == ax.READ else "write"
        expected = ax.expected_profiles(db)[0 if access == "read" else 1]
        relations, columns, oids, oid = [], {}, {}, 30000
        for kind, schema, name in sorted(expected.objects):
            if kind in ("table", "sequence"):
                oid += 1
                oids[(kind, schema, name)] = oid
                relations.append((oid, "r" if kind == "table" else "S", schema, name))
                if kind == "table":
                    columns[oid] = ["id"]
        privileges = (set(expected.privileges) | set(extra)) - set(missing)
        for kind, schema, name, column, _ in sorted(expected.privileges | set(extra)):
            if column and column not in columns[oids[(kind, schema, name)]]:
                columns[oids[(kind, schema, name)]].append(column)
        schemas = {"public": 2200, lay.real.SYN: 16400}
        grants = set()
        for kind, schema, name, column, privilege in privileges:
            if kind == "database":
                grants.add(("database", 16384, privilege))
            elif kind == "schema":
                grants.add(("schema", schemas[name], privilege))
            elif kind == "sequence":
                grants.add(("sequence", oids[(kind, schema, name)], privilege))
            elif column:
                grants.add(("column", (oids[(kind, schema, name)], column), privilege))
            else:
                grants.add(("relation", oids[(kind, schema, name)], privilege))
        cat = to.catalog(access)
        cat.update(relations=relations, columns=columns, grants=grants,
                   schemas=sorted((o, n) for n, o in schemas.items()), database=[(16384, db)],
                   identity=[target["databases"][db]["identity_value"]])
        cat["session"].update(dbname=db, server_version_num=target["server_version_num"], current_user_name=user,
                              session_user_name=user, search_path=lay.real.SEARCH_PATH)
        self.catalog = cat
        self.facts = CaseConn(test, user).facts
        self.log, self.queries, self.cursors, self.commits = [], [], [], 0
        self.status = TransactionStatus.IDLE
        self.closed = self.broken = False
        self.read_only = self.isolation_level = None
        server = self

        class Info:
            host, port, dbname, backend_pid = g.HOST, T.port, db, 4242
            server_version = int(target["server_version_num"])

            @property
            def transaction_status(self_):
                return server.status
        self.info = Info()
        self.pgconn = SimpleNamespace(ssl_in_use=True)

    def cursor(self, row_factory=None):
        if "POST_CONNECT" in self.log:
            return self.to.FakeCursor(self)
        self.log.append("POST_CONNECT")
        return FactsConn(self.facts).cursor()

    def execute(self, query, params=None):
        self.log.append(query if isinstance(query, str) else "SQL")
        self.status = TransactionStatus.INTRANS

    def rollback(self):
        self.log.append("ROLLBACK")
        self.status = TransactionStatus.IDLE

    def commit(self):
        self.commits += 1
        self.status = TransactionStatus.IDLE

    def close(self):
        self.closed = True


# --- 8. processes: import does nothing; the entry point stops before G0 ------------------------------------------

class Processes(unittest.TestCase):
    def env(self):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
        env.update(APP_ENV="test", DATABASE_URL="sqlite:///:memory:", PYTHON_DOTENV_DISABLED="1")
        env.pop("PYTHONPATH", None)
        return env

    def test_import_does_nothing(self):
        script = ("import sys, os; sys.path.insert(0, sys.argv[1]); before = set(os.listdir(sys.argv[2]));"
                  "import _ops_access_lock_real as ax;"
                  "assert not [m for m in sys.modules if m == 'app' or m.startswith('app.')], 'app imported';"
                  "assert set(os.listdir(sys.argv[2])) == before; print('ok', len(ax.PLANNED))")
        done = subprocess.run([sys.executable, "-c", script, str(TESTS_DIR), str(TESTS_DIR)], capture_output=True,
                              text=True, env=self.env(), timeout=120)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "ok 24"), done.stderr)
        self.assertFalse(T.root.exists())

    def test_entry_point_exit_codes(self):
        # Exercise the real __main__ path with the unapproved state explicitly set in the child.
        # The checked-in value is True after V2~V4; no target lookup or PG work belongs in this guard.
        script = ("import sys, runpy; sys.path.insert(0, " + repr(str(TESTS_DIR)) + ");"
                  "import _ops_access_lock_real as ax; ax.LQ4_CHANGES_APPROVED = None;"
                  "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')")
        for argv, code, text in ((["check-access-lock"], 1, "LQ4"), ([], 2, "usage"), (["check-access-lock", "k1"], 2,
                                                                                         "usage")):
            with self.subTest(argv=argv):
                done = subprocess.run([sys.executable, "-c", script, str(TESTS_DIR / "_ops_access_lock_real.py"), *argv],
                                      capture_output=True, text=True, env=self.env(), timeout=120)
                self.assertEqual(done.returncode, code, done.stderr)
                self.assertIn(text, done.stdout)
        self.assertFalse(T.root.exists())


if __name__ == "__main__":
    unittest.main()
