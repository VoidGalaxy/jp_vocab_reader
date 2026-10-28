"""Fake-only checks for the RS4 resume real-PG runner (tests/_ops_resume_real.py). No database, cluster, key or
certificate: connect entry points, `subprocess`, key creation and process facts are patched; only temporary
synthetic files are written. The runner's real prepare / check / cleanup are never run against anything.

Run directly:      python tests/test_ops_resume_real_guard.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_resume_real_guard.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
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

import _ops_pg62 as g  # noqa: E402
import _ops_real_layout as lay  # noqa: E402
import _ops_resume_real as rr  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only: the plan fixture's product hash)

T = g.PG66_RESUME
PID = 6666
# Fixed from the plan (OPS_MIGRATION_RESUME_REAL_PG_PLAN 5-3), never from the code under test.
PLAN_DBS = ("r1", "r2", "r4a", "r4b", "r4c", "r5", "r6", "r6b", "r7a", "r7b", "r7c", "r7d", "r7e", "r8", "r9a", "r9b",
            "r9c", "c1", "c2", "c2s", "c3", "c3r", "c3c")


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


class Blocked(unittest.TestCase):
    """Every real connection, process, key creation and listener lookup fails the test if reached."""

    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden), mock.patch.object(rr.sigtests, "Keys", forbidden),
                      mock.patch.object(g, "listener_pids", forbidden), mock.patch.object(g, "admin_connect", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_resume_real_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def record(self, **changes):
        run = self.folder / "20261028T020000"
        run.mkdir(exist_ok=True)
        target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                  "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                  "system_identifier": "1", "provider_roles": ["jpvr_read", "jpvr_write"], "admin_role": "jpvr_admin",
                  "roles": {"jpvr_read": 101, "jpvr_write": 102},
                  "databases": {db: {"oid": 500 + i, "identity_value": f"pg66-{i}-n",
                                     "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                for i, db in enumerate(rr.BUSINESS_DATABASES)}}
        target.update(changes)
        data = json.dumps(target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        return rec, target


# --- 1. closed target, matrix, admin limits ---------------------------------------------------------------------

class Target(Blocked):
    def test_preset_and_databases_from_the_plan(self):
        self.assertIs(rr.LAYOUT, lay.PG66)
        self.assertEqual(tuple(rr.CHECK_DB), PLAN_DBS)
        self.assertEqual(rr.TEMPLATE, "jp_vocab_test_resume_tpl")
        self.assertEqual(rr.CHECK_DB["c3c"], "jp_vocab_test_resume_c3c")
        self.assertEqual((T.root, T.port, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg66"), 55502, "jpvr_admin", ("jpvr_read", "jpvr_write")))
        self.assertEqual(set(rr.INITIAL), set(PLAN_DBS))                       # every check DB gets a G1 state
        self.assertEqual(set(rr.PLANNED) - set(PLAN_DBS), {"r0", "r3"})         # judged on r1 / r2 evidence

    def test_business_matrix(self):
        ok = {"host": g.HOST, "port": "55502", "dbname": rr.CHECK_DB["r1"], "user": "jpvr_write", "sslmode": "verify-full"}
        rr.business_check(ok)
        for key, value, code in (("port", "55492", "pg62_port_refused"), ("dbname", rr.TEMPLATE, "pg62_database_refused"),
                                 ("dbname", "jp_vocab_test_apply_a1", "pg62_database_refused"),
                                 ("dbname", "postgres", "pg62_database_refused"),
                                 ("user", "jpvr_admin", "pg62_role_refused"), ("user", "jpvm_write", "pg62_role_refused"),
                                 ("sslmode", "require", "pg62_tls_mode_refused"), ("host", "127.0.0.2", "pg62_host_refused")):
            with self.subTest(key=key, value=value), self.assertRaises(g.Pg62Refused) as caught:
                rr.business_check(dict(ok, **{key: value}))
            self.assertEqual(caught.exception.code, code)
        with mock.patch.dict(os.environ, {"PGHOST": "x"}), self.assertRaises(g.Pg62Refused):
            rr.business_check(ok)

    def test_admin_connection_limits(self):
        seen = []
        with mock.patch.object(g, "admin_connect", lambda db, **k: seen.append((db, k["target"])) or "conn"):
            for db in ("postgres", rr.TEMPLATE, rr.CHECK_DB["c1"]):
                self.assertEqual(rr.admin(db, PID), "conn")
            for db in ("jp_vocab_test_apply_a1", "template1", "jp_vocab"):
                with self.subTest(db=db), self.assertRaises(g.Pg62Refused):
                    rr.admin(db, PID)
        self.assertTrue(all(t is T for _, t in seen))

    def test_record_binding_and_liveness(self):
        rec, target = self.record()
        self.assertEqual(rr.require_target_bound(rec, (rec.folder / "target.json").read_bytes())["port"], 55502)
        for change in (dict(port=55492), dict(data="C:/JV_Tools/pg65/data"), dict(provider_roles=["jpvm_read", "jpvm_write"]),
                       dict(databases={})):
            with self.subTest(change=change):
                rec2, _ = self.record(**change)
                with self.assertRaises(g.Pg62Refused) as caught:
                    rr.require_target_bound(rec2, (rec2.folder / "target.json").read_bytes())
                self.assertEqual(caught.exception.code, "pg66_target_record_mismatch")
        with self.assertRaises(g.Pg62Refused):
            rr.require_target_bound(rec, (rec.folder / "target.json").read_bytes() + b" ")      # hash differs
        rr.require_ours({"postmaster_pid": PID})
        with self.assertRaises(g.Pg62Refused):
            rr.require_ours({"postmaster_pid": PID + 1})

    def test_post_connect_mismatch_closes(self):
        rec, target = self.record()
        db = rr.CHECK_DB["r1"]
        good = {"server_addr": "127.0.0.1", "server_port": 55502, "version": "180006", "dbname": db,
                "db_oid": target["databases"][db]["oid"], "role_oid": 102,
                "object_oids": [target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                "identity": [target["databases"][db]["identity_value"]]}

        class Conn:
            def __init__(self, facts):
                self.facts, self.closed = facts, False

            def cursor(self, row_factory=None):
                facts = self.facts

                class C:
                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                    def execute(self, *a):
                        pass

                    def fetchone(self):
                        return facts
                return C()

            def rollback(self):
                pass

            def close(self):
                self.closed = True
        rr.post_connect_check(Conn(good), target, "jpvr_write")
        for key, value in (("server_port", 55492), ("db_oid", 1), ("role_oid", 101), ("identity", ["other"])):
            conn = Conn(dict(good, **{key: value}))
            with self.subTest(key=key), self.assertRaises(g.Pg62Refused):
                rr.post_connect_check(conn, target, "jpvr_write")
            self.assertTrue(conn.closed)


# --- 2. expectations from the contract ----------------------------------------------------------------------------

class Contract(Blocked):
    def test_grants_are_the_contract_tuples_without_sequence_usage(self):
        db = rr.CHECK_DB["r1"]
        read, write = rr.expected_profiles(db)
        self.assertTrue(cli.READ_PRIVILEGES <= read.privileges and cli.WRITE_PRIVILEGES <= write.privileges)
        self.assertEqual({p[0] for p in (read.privileges - cli.READ_PRIVILEGES) | (write.privileges - cli.WRITE_PRIVILEGES)}
                         - {"database"}, set())                       # only this DB's CONNECT is added
        grants = [s.as_string(None) for s in rr.contract_grants(db)]
        self.assertEqual(len(grants), len(read.privileges) + len(write.privileges))
        self.assertFalse([s for s in grants if "SEQUENCE" in s])
        self.assertTrue(all(s.endswith('TO "jpvr_read"') or s.endswith('TO "jpvr_write"') for s in grants))
        self.assertFalse({p for p in cli.WRITE_PRIVILEGES if p[0] == "sequence"})

    def test_variants_have_reverts_and_the_right_role(self):
        names = set(lay.PG66.variants)
        self.assertEqual(names, {"r5_read_missing", "r5_read_excess", "r5_write_missing", "r5_write_excess",
                                 "r5_write_sequences", "r9a_card_column"})
        for name in names:
            apply = [s.as_string(None) for s in rr.variant_statements(name, "apply")]
            revert = [s.as_string(None) for s in rr.variant_statements(name, "revert")]
            self.assertTrue(apply and revert)
            role = '"jpvr_read"' if name.startswith("r5_read") else '"jpvr_write"'
            self.assertTrue(all(role in s for s in apply + revert), name)
        self.assertIn("USAGE ON SEQUENCE", " ".join(s.as_string(None) for s in rr.variant_statements("r5_write_sequences",
                                                                                                    "apply")))
        with self.assertRaises(lay.CheckFailed):
            rr.variant_statements("b2_lock_column", "apply")                      # a PG65 variant is not ours

    def test_expected_codes_are_fixed(self):
        self.assertEqual({n: c for n, c, _, _ in rr.R5},
                         {"r5_read_missing": "observed_privileges_missing", "r5_read_excess": "observed_privileges_excess",
                          "r5_write_missing": "observed_privileges_missing", "r5_write_excess": "observed_privileges_excess",
                          "r5_write_sequences": "observed_privileges_excess"})
        self.assertEqual(rr.INITIAL["r2"][0], "failed")
        self.assertEqual(rr.INITIAL["r7a"], ("completed", 3))
        self.assertEqual({k for k, v in rr.INITIAL.items() if v[1] == 2}, {"c3", "c3r", "c3c"})
        self.assertEqual(rr.ADMIN_DATA_CHECKS, ("r4a", "r4b", "r7b", "r7c", "r7d", "r8"))
        self.assertEqual(rr.CARDS, ("p1", "p2", "p3"))

    def test_hba_and_conf(self):
        text = rr.hba()
        self.assertIn("map=pg66", text)
        self.assertNotIn("pg65", text)
        self.assertIn("jpvr_read,jpvr_write", text)
        self.assertNotIn(rr.TEMPLATE + " jpvr_read", text)
        self.assertIn("port = 55502", rr.conf())


# --- 3. stop rules, counting of results, not-run items ------------------------------------------------------------

class StopRules(Blocked):
    def run_check(self, gates=None, checks=None, post=None, readback_fail=None):
        rec, _ = self.record()
        calls = []

        def make(name, ok=True):
            def fn(h):
                calls.append(name)
                if not ok:
                    raise lay.CheckFailed("product_defect", name)
                return {"ok": name}
            return fn
        gates = gates or {}
        fakes = [(n, make(n, ok)) for n, ok in (checks or [(n, True) for n in rr.PLANNED])]
        real_recorded = lay.run_recorded

        def recorded(rec_, name, fn, h):
            if name == readback_fail:
                ok = real_recorded(rec_, name, fn, h)
                rec_.result(name, "error", kind="harness_defect", stage="record_readback")
                return False if ok else ok
            return real_recorded(rec_, name, fn, h)
        harness = SimpleNamespace(start=lambda: None, close=lambda: calls.append("closed"))
        with mock.patch.object(rr, "Q2_ADMIN_DATA_CHANGES", True), \
                mock.patch.object(g, "single_run", lambda target=None: rec), \
                mock.patch.object(rr, "Harness", lambda r: harness), \
                mock.patch.object(rr, "g0_gate", make("g0_gate", gates.get("g0_gate", True))), \
                mock.patch.object(rr, "g1_gate", make("g1_gate", gates.get("g1_gate", True))), \
                mock.patch.object(rr, "post_check", make(rr.POST, post is not False)), \
                mock.patch.object(rr, "CHECKS", fakes), mock.patch.object(lay, "run_recorded", recorded), \
                contextlib.redirect_stdout(io.StringIO()):
            code = rr.main(["check"])
        saved = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))
        return code, calls, saved

    def test_all_pass_is_0_and_gates_not_counted(self):
        code, calls, saved = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(calls[:2], ["g0_gate", "g1_gate"])
        self.assertEqual([r["check"] for r in saved["results"]], ["g0_gate", "g1_gate"] + list(rr.PLANNED) + [rr.POST])

    def test_g1_failure_runs_nothing(self):
        code, calls, saved = self.run_check(gates={"g1_gate": False})
        self.assertEqual(code, 1)
        self.assertEqual([c for c in calls if c != "closed"], ["g0_gate", "g1_gate"])
        not_run = [e for e in saved["events"] if e["kind"] == "not_run"][0]
        self.assertEqual(not_run["checks"], list(rr.PLANNED))

    def test_product_defect_candidate_stops_the_rest(self):
        checks = [(n, n != "r4c") for n in rr.PLANNED]
        code, calls, saved = self.run_check(checks=checks)
        self.assertEqual(code, 1)
        self.assertEqual([c for c in calls if c.startswith(("r", "c")) and c != "closed"],
                         list(rr.PLANNED[:rr.PLANNED.index("r4c") + 1]))
        not_run = [e for e in saved["events"] if e["kind"] == "not_run"][0]
        self.assertEqual(not_run["checks"], list(rr.PLANNED[rr.PLANNED.index("r4c") + 1:]))
        self.assertIn("closed", calls)

    def test_record_readback_failure_and_post_failure_are_1(self):
        code, calls, _ = self.run_check(readback_fail="r2")
        self.assertEqual(code, 1)
        self.assertNotIn("r3", calls)
        code, _, _ = self.run_check(post=False)
        self.assertEqual(code, 1)

    def test_q2_undecided_stops_before_anything(self):
        self.assertIs(rr.Q2_ADMIN_DATA_CHANGES, True)                   # approved 2026-10-28 (closed list)
        # the lock itself is still checked: any other value stops before anything (the module value is replaced
        # here only to exercise that branch)
        with mock.patch.object(rr, "Q2_ADMIN_DATA_CHANGES", None), mock.patch.object(g, "single_run", forbidden), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rr.main(["check"]), 1)
            with self.assertRaises(lay.CheckFailed):
                rr.Harness.admin_data_change(SimpleNamespace(), "r4a", "summary_reserialized", None)
        self.assertIn("Q2", out.getvalue())

    def test_usage_and_cleanup_mismatch_deletes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rr.main([]), 2)
            self.assertEqual(rr.main(["check", "r1"]), 2)
            self.assertEqual(rr.main(["resume"]), 2)
        rec, _ = self.record(port=55492)                                  # the record is not as prepared
        with mock.patch.object(g, "single_run", lambda target=None: rec), mock.patch.object(shutil, "rmtree", forbidden), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rr.main(["cleanup"]), 1)
        shutil.rmtree(rec.folder)                                             # a fresh record for the next case
        rec, _ = self.record()
        with mock.patch.object(g, "single_run", lambda target=None: rec), mock.patch.object(shutil, "rmtree", forbidden),                 mock.patch.object(g, "postmaster_pid", lambda target=None: PID),                 mock.patch.object(g, "server_is_ours", lambda pid, target=None: False),                 mock.patch.object(lay.base, "run", forbidden), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rr.main(["cleanup"]), 1)
        self.assertIn("live server matches the record", out.getvalue())


class GateG1(Blocked):
    """G1 with a fake harness: each DB's initial state is compared with the plan's fixed expectation."""

    def harness(self, wrong=None):
        made = []

        def case(check_id, account="a", *, batch=1, v3=True):
            made.append((check_id, account, batch, v3))
            return SimpleNamespace(check_id=check_id, plan="plan", account=account, batch=batch)

        def first_apply(case, inject=None):
            state = rr.INITIAL[case.check_id][0]
            made.append(("inject", case.check_id, inject is not None and inject("jpvr_write", 3)
                         and not inject("jpvr_write", 2) and not inject("jpvr_read", 3)))
            out = {"phase": "partial"} if state in ("started", "v1_a0", "other_account") else {}
            return out, {"started": 3, "v1_a0": 3, "other_account": 3, "completed": 0, "failed": 1}[state]

        def facts(case):
            state, cursor = rr.INITIAL[case.check_id]
            status = {"failed": "failed", "completed": "completed"}.get(state, "started")
            if case.check_id == wrong:
                status = "completed"
            return {"runs": [{"status": status, "scope_md5": "scope"}], "snapshots": cursor,
                    "summary": {"cursor": cursor}, "versions": {}}
        return SimpleNamespace(case=case, first_apply=first_apply, facts=facts, outside=lambda cid: ["same"],
                               sessions=lambda: {"open": 0, "idle_in_transaction": 0}, cases={}, evidence={},
                               made=made)

    def test_states_and_injection_as_planned(self):
        h = self.harness()
        with mock.patch.object(rr, "expected_scope_md5", lambda plan: "scope"):
            out = rr.g1_gate(h)
        self.assertEqual(out["databases"], len(PLAN_DBS))
        injected = {cid for kind, cid, flag in [m for m in h.made if m[0] == "inject"] if flag}
        self.assertEqual(injected, {"r2"})                                       # only r2 is made by injection
        self.assertIn(("r7e", "b", 1, True), h.made)                             # b owns r7e's run
        self.assertIn(("r6b", "a", 1, False), h.made)                            # A0 without the binding
        self.assertIn(("r7a", "a", 3, True), h.made)
        self.assertEqual(set(h.cases), set(PLAN_DBS))

    def test_a_wrong_initial_state_is_a_preparation_failure(self):
        h = self.harness(wrong="c3")
        with mock.patch.object(rr, "expected_scope_md5", lambda plan: "scope"), self.assertRaises(lay.CheckFailed) as caught:
            rr.g1_gate(h)
        self.assertEqual(caught.exception.kind, "preparation_failure")


# --- 4. instrumentation keeps the originals ----------------------------------------------------------------------

class FakeRaw:
    def __init__(self, fail_select=False, fail_rollback=False):
        self.statements, self.fail_select, self.fail_rollback = [], fail_select, fail_rollback
        self.info = SimpleNamespace(backend_pid=1234)

    def cursor(self, row_factory=None):
        raw = self

        class C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, query, *a):
                raw.statements.append(query)
                if query == rr.PROBE_SQL and raw.fail_select:
                    raise psycopg.errors.InFailedSqlTransaction("x")
                if query.startswith("ROLLBACK TO") and raw.fail_rollback:
                    raise psycopg.OperationalError("y")

            def fetchone(self):
                return ("repeatable read", "on")
        return C()


class Instruments(Blocked):
    def tracker(self, raw, role="jpvr_read"):
        t = rr.ResumeTracked(raw, rr.Counts(), role, [])
        t.trace.extend([("set_read_only", False), ("set_repeatable_read", True), ("status_run_row", True),
                        ("status_snapshots", True)])
        return t

    def test_probe_new_cursor_in_a_savepoint_only_on_the_first_read(self):
        store: dict = {}
        raw = FakeRaw()
        probe = rr.make_probe(store)
        probe("jpvr_write", 1, self.tracker(raw, "jpvr_write"))
        probe("jpvr_read", 2, self.tracker(raw))
        self.assertEqual(raw.statements, [])
        probe("jpvr_read", 1, self.tracker(raw))
        self.assertEqual(raw.statements, ["SAVEPOINT rs4_probe", rr.PROBE_SQL, "RELEASE SAVEPOINT rs4_probe"])
        self.assertEqual(store["probe"], {"transaction_isolation": "repeatable read", "transaction_read_only": "on"})
        self.assertEqual(store["probe_after"], ["set_read_only", "set_repeatable_read", "status_run_row",
                                                "status_snapshots"])

    def test_probe_failure_is_recorded_not_raised(self):
        for fail_rollback in (False, True):
            store: dict = {}
            raw = FakeRaw(fail_select=True, fail_rollback=fail_rollback)
            rr.make_probe(store)("jpvr_read", 1, self.tracker(raw))           # never raises
            self.assertEqual(store["probe"]["probe_error"], "probe_failed")   # fixed stage code (RS4-1 fix), no text
            self.assertIn("ROLLBACK TO SAVEPOINT rs4_probe", raw.statements)
            self.assertEqual(store["probe"]["rollback"], "rollback_to_savepoint_failed" if fail_rollback
                             else "rolled_back_to_savepoint")
        h = SimpleNamespace(evidence={"r1": {"trace": self.tracker(FakeRaw()).trace,
                                             "probe": {"probe": {"probe_error": "X"}, "probe_after": []}}})
        with self.assertRaises(lay.CheckFailed) as caught:
            rr.r0_status_session(h)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_r0_judgement(self):
        trace = [("set_read_only", False), ("SET", False), ("SELECT", False)] + self.tracker(FakeRaw()).trace
        names = [n for n, _ in trace]
        ok = {"probe": {"transaction_isolation": "repeatable read", "transaction_read_only": "on"}, "probe_after": names}
        self.assertEqual(rr.r0_status_session(SimpleNamespace(evidence={"r1": {"trace": trace, "probe": ok}}))["order"],
                         ["set_read_only", "set_repeatable_read", "status_run_row", "status_snapshots"])
        swapped = trace[:-2] + [trace[-1], trace[-2]]
        with self.assertRaises(lay.CheckFailed):
            rr.r0_status_session(SimpleNamespace(evidence={"r1": {"trace": swapped,
                                                                   "probe": dict(ok, probe_after=[n for n, _ in swapped])}}))
        wrong = dict(ok, probe={"transaction_isolation": "read committed", "transaction_read_only": "on"})
        with self.assertRaises(lay.CheckFailed) as caught:
            rr.r0_status_session(SimpleNamespace(evidence={"r1": {"trace": trace, "probe": wrong}}))
        self.assertEqual(caught.exception.kind, "product_defect")

    def test_under_lock_read_returns_the_same_row(self):
        row = {"status": "started", "finished_at": None, "summary_json": json.dumps({"cursor": 2, "results": []})}

        class Cursor:
            def fetchone(self):
                return row
        t = rr.ResumeTracked(FakeRaw(), rr.Counts(), "jpvr_write", [])
        cursor = rr.ReadCursor(Cursor(), t)
        self.assertIs(cursor.fetchone(), row)
        self.assertEqual(t.reads, [{"status": "started", "finished": False, "cursor": 2,
                                    "summary_sha256": hashlib.sha256(row["summary_json"].encode()).hexdigest()}])
        self.assertEqual(rr.label("SELECT * FROM srs_migration_runs WHERE run_key = %s"), "lock_run_row")
        self.assertEqual(rr.label("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"), "set_repeatable_read")
        self.assertEqual(rr.label("UPDATE x SET y = 1"), "UPDATE")

    def test_value_wrappers_return_the_originals(self):
        values = rr.Values()
        rr.ar.fix_app_environment()
        from app.srs import migration
        sentinel_pre, sentinel_lock = {"pre": 1}, {"lock": 2}
        with mock.patch.object(cli, "progress_values", lambda row, snaps: sentinel_pre), \
                mock.patch.object(migration, "run_progress_values", lambda conn, run_id: sentinel_lock):
            with values.installed(), values.named("B"):
                self.assertIs(cli.progress_values(None, []), sentinel_pre)
                self.assertIs(migration.run_progress_values(None, 1), sentinel_lock)
            self.assertIs(cli.progress_values(None, []), sentinel_pre)          # restored
        self.assertEqual(values.runs, {"B": {"pre_read": {"pre": 1}, "under_lock": {"lock": 2}}})

    def test_attribution(self):
        before = {"runs": [{"id": 1, "mode": "apply", "status": "started", "scope_md5": "s"}], "snapshots": 1,
                  "versions": {"personal:1": 2, "personal:2": 1, "personal:3": 1}}
        after = {"runs": [{"id": 1, "mode": "apply", "status": "completed", "scope_md5": "s"}], "snapshots": 3,
                 "versions": {"personal:1": 2, "personal:2": 2, "personal:3": 2}}
        self.assertEqual(rr.resume_attribution(before, after, scope="s", applied=2, refused_commits=0), [])
        self.assertEqual(rr.resume_attribution(before, after, scope="s", applied=2, refused_commits=1), ["refused_commits"])
        double = dict(after, versions={"personal:1": 2, "personal:2": 3, "personal:3": 1})
        self.assertIn("card_versions", rr.resume_attribution(before, double, scope="s", applied=2, refused_commits=0))
        self.assertIn("run_row", rr.resume_attribution(before, after, scope="t", applied=2, refused_commits=0))


SECRET = "Synth3tic-Probe-Secret-41c7"


class ScriptedRaw:
    """FAKE raw connection: each probe statement may raise a prepared error or interrupt (object kept)."""

    def __init__(self, select=None, rollback=None):
        self.select, self.rollback, self.statements = select, rollback, []
        self.info = SimpleNamespace(backend_pid=1)

    def cursor(self, row_factory=None):
        raw = self

        class C:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, query, *a):
                raw.statements.append(query)
                if query == rr.PROBE_SQL and raw.select is not None:
                    raise raw.select
                if query.startswith("ROLLBACK TO") and raw.rollback is not None:
                    raise raw.rollback

            def fetchone(self):
                return ("repeatable read", "on")
        return C()


class ExitProduct:
    def __init__(self, error=None):
        self.exits, self.args, self.error = 0, None, error

    def __enter__(self):
        return "app"

    def __exit__(self, *exc):
        self.exits += 1
        self.args = exc
        if self.error is not None:
            raise self.error
        return False


class ProbeInterrupts(Blocked):
    """The REAL make_probe on the REAL counted_connector exit path, with scripted (synthetic) failures. These are
    injected objects, not OS or PostgreSQL evidence."""

    def run_probe(self, raw, product, body=None):
        store: dict = {}
        counts, trackers = rr.Counts(), []

        def real(inputs, expected, driver):
            def connector(read_only=False):
                tracker = rr.ResumeTracked(raw, counts, "jpvr_read", [])
                trackers.append(tracker)
                counts.created["jpvr_read"] += 1
                return product
            return connector
        connect = lay.counted_connector(lay.PG66, counts, trackers, real=real,
                                        before_exit=rr.make_probe(store))(SimpleNamespace(command="status"), None, None)
        caught = None
        try:
            with connect(read_only=True):
                if body is not None:
                    raise body
        except BaseException as error:                     # the test inspects exactly what came out
            caught = error
        return store, caught

    def assert_clean(self, error, store):
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        shown = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        self.assertNotIn(SECRET, shown)
        self.assertNotIn(SECRET, json.dumps(store))

    def test_rollback_interrupt_after_a_probe_error(self):
        interrupt = KeyboardInterrupt()
        product = ExitProduct()
        store, caught = self.run_probe(ScriptedRaw(select=OSError(f"disk {SECRET}"), rollback=interrupt), product)
        self.assertIs(caught, interrupt)                                  # the same object
        self.assertEqual((product.exits, product.args[0]), (1, None))       # original exit once, normal end
        self.assertEqual(store["probe"], {"probe_error": "probe_failed",
                                          "rollback": "rollback_to_savepoint_interrupted"})
        self.assert_clean(caught, store)

    def test_rollback_system_exit_keeps_its_value(self):
        stop = SystemExit(9)
        product = ExitProduct()
        store, caught = self.run_probe(ScriptedRaw(select=OSError(f"disk {SECRET}"), rollback=stop), product)
        self.assertIs(caught, stop)
        self.assertEqual((caught.code, product.exits), (9, 1))
        self.assert_clean(caught, store)

    def test_probe_interrupt_itself(self):
        interrupt = KeyboardInterrupt()
        product = ExitProduct()
        raw = ScriptedRaw(select=interrupt)
        store, caught = self.run_probe(raw, product)
        self.assertIs(caught, interrupt)
        self.assertEqual(product.exits, 1)
        self.assertEqual(store["probe"], {"probe_error": "probe_interrupted", "rollback": "rolled_back_to_savepoint"})
        self.assertIn("ROLLBACK TO SAVEPOINT rs4_probe", raw.statements)
        self.assert_clean(caught, store)

    def test_rollback_ordinary_error_is_recorded_only(self):
        product = ExitProduct()
        store, caught = self.run_probe(ScriptedRaw(select=OSError(f"disk {SECRET}"),
                                                   rollback=OSError(f"again {SECRET}")), product)
        self.assertIsNone(caught)
        self.assertEqual(product.exits, 1)
        self.assertEqual(store["probe"], {"probe_error": "probe_failed", "rollback": "rollback_to_savepoint_failed"})
        self.assertNotIn(SECRET, json.dumps(store))

    def test_original_exit_error_or_interrupt_wins(self):
        for exit_error in (psycopg.OperationalError("commit failed"), SystemExit(3), KeyboardInterrupt()):
            with self.subTest(exit_error=type(exit_error).__name__):
                product = ExitProduct(error=exit_error)
                store, caught = self.run_probe(ScriptedRaw(select=OSError(f"disk {SECRET}"),
                                                           rollback=KeyboardInterrupt()), product)
                self.assertIs(caught, exit_error)
                self.assertEqual(product.exits, 1)
                shown = "".join(traceback.format_exception(type(caught), caught, caught.__traceback__))
                self.assertNotIn(SECRET, shown)
                self.assertNotIn(SECRET, json.dumps(store))

    def test_normal_probe_and_product_error_unchanged(self):
        product = ExitProduct()
        raw = ScriptedRaw()
        store, caught = self.run_probe(raw, product)
        self.assertIsNone(caught)
        self.assertEqual(store["probe"], {"transaction_isolation": "repeatable read", "transaction_read_only": "on"})
        self.assertEqual(raw.statements, ["SAVEPOINT rs4_probe", rr.PROBE_SQL, "RELEASE SAVEPOINT rs4_probe"])
        product = ExitProduct()
        raw = ScriptedRaw()
        body = ValueError("product")
        store, caught = self.run_probe(raw, product, body=body)
        self.assertIs(caught, body)
        self.assertEqual((store, raw.statements, product.exits, product.args[0]), ({}, [], 1, ValueError))


class CasePath(unittest.TestCase):
    """The REAL `Harness.case` (Harness init and target binding, deploy folder, manifest, I0, the CLI `run_dry_run`
    with its real pre-check and signatures, the real counted connector, `Harness.driver` with the real business
    matrix / liveness / post-connect checks, the plan file, `run_synthetic_preflight`, E0 / E1, A0).
    REPLACED: the guard's real connect (`g.Guard`), the connection and cursor (fake), the provider path behind the
    CLI product connector (`ORIGINAL_CONNECTOR`: a fake that calls the given driver once, as the adapter does, and
    hands the raw connection over) and the product dry_run body (a stub that enters the handed connection once and
    returns real plan candidates). The certificate file is fake bytes. Signatures use the existing synthetic
    test-only temporary OS ssh-keygen keys; nothing else may start a process."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(rr.op.osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = rr.sigtests.Keys()

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()

    def setUp(self):
        real_popen = subprocess.Popen

        def only_keygen(args, *a, **k):                    # the test keys only; any other process fails
            if os.path.normcase(str(args[0])) != os.path.normcase(rr.op.osig.SSH_KEYGEN):
                raise AssertionError("an external entry point was called")
            return real_popen(args, *a, **k)
        self.guards: list = []
        self.real_case = rr.Harness.case                              # the real method, fixed before any patch
        test = self

        class FakeGuard:
            def __init__(self, manifest, deploy_root, folder, target=None):
                test.assertIs(target, T)

            def driver(self, **kwargs):
                test.guards.append(dict(kwargs))
                return test.conn()
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", only_keygen),
                      mock.patch.object(g, "listener_pids", forbidden),
                      mock.patch.object(g, "admin_connect", forbidden), mock.patch.object(g, "postmaster_pid", forbidden),
                      mock.patch.object(lay.real, "make_tls", forbidden),
                      mock.patch.object(lay.real, "start_server", forbidden),
                      mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.object(g, "Guard", FakeGuard),
                      mock.patch.object(rr.Harness, "ca_pem", lambda self: b"-----synthetic ca-----\n"),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_resume_case_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        run = self.folder / "20261028T030000"
        run.mkdir()
        self.db = rr.CHECK_DB["r1"]
        self.target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                       "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                       "system_identifier": "1", "provider_roles": ["jpvr_read", "jpvr_write"],
                       "admin_role": "jpvr_admin", "roles": {"jpvr_read": 101, "jpvr_write": 102},
                       "databases": {d: {"oid": 500 + i, "identity_value": f"pg66-{i}-n",
                                         "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                     for i, d in enumerate(rr.BUSINESS_DATABASES)},
                       "synthetic": {"a": {"user_id": 2, "personal": {"p1": 11, "p2": 12, "p3": 13, "p4": 14,
                                                                      "p5": 15}, "lexeme": [1, 2]}}}
        data = json.dumps(self.target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        self.h = rr.Harness(rec)                                      # real init: record binding, liveness
        self.h.keys = self.keys
        self.h.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.h.passwords = {"jpvr_read": "synthetic-password-r", "jpvr_write": "synthetic-password-w"}
        self.addCleanup(lambda: [shutil.rmtree(f, True) for f in self.h.folders])
        self.counts: list = []
        self.scope_lists: list = []
        self.driver_lists: list = []
        self.handed_errors: list = []

    def conn(self):
        target, db = self.target, self.db
        facts = {"server_addr": "127.0.0.1", "server_port": T.port, "version": "180006", "dbname": db,
                 "db_oid": target["databases"][db]["oid"], "role_oid": 101,
                 "object_oids": [target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                 "identity": [target["databases"][db]["identity_value"]]}

        class Conn:
            closed = False
            info = SimpleNamespace(backend_pid=4242)

            def cursor(self, row_factory=None):
                class C:
                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                    def execute(self, *a):
                        pass

                    def fetchone(self):
                        return facts
                return C()

            def rollback(self):
                pass

            def close(self):
                self.closed = True
        return Conn()

    def candidates(self):
        """Real plan candidates (the plan-file module's own type) for account a's p1..p3."""
        rr.ar.fix_app_environment()
        from app.srs.engine import DEFAULT_CONFIG
        digest = hashlib.sha256(b"[]").hexdigest()
        items = [SimpleNamespace(key=SimpleNamespace(kind="personal", user_id=2, ref_id=r), card_fingerprint=None,
                                 logs_fingerprint=digest, card_version=None, quality="unavailable",
                                 flags=("card_or_access_missing",), values_json=None, last_log_id=0, reconversion=None,
                                 restart_json=None) for r in (11, 12, 13)]
        data = rr.pfile.serialize_plan(db_identity=rr.pf.db_identity(), account_id=2, job_key=rr.RUN_KEY,
                                       config_version=DEFAULT_CONFIG.config_version,
                                       product_fingerprint=flow.FlowBase.product(
                                           SimpleNamespace(config_version=lambda: DEFAULT_CONFIG.config_version), items),
                                       candidates=items)
        path = self.folder / "seed_plan.json"
        rr.pfile.write_plan_file(str(path), data)
        return rr.pfile.to_candidates(rr.pfile.read_plan_file(str(path)))

    def run_case(self, dry_run_body=None):
        test = self
        candidates = self.candidates()

        def fake_product(inputs, expected, driver):                  # replaces adapter + provider + observer
            def connector(read_only=False):
                raw = driver(host=g.HOST, port=str(T.port), dbname=inputs.target.database, user=rr.READ,
                             sslmode="verify-full")

                class Handed:
                    def __enter__(self):
                        return raw

                    def __exit__(self, *exc):
                        raw.close()
                        return False
                return Handed()
            return connector

        def dry_run(keys, *, connect=None):                          # the product body stub: one connection
            try:
                with connect(read_only=True):
                    pass
            except lay.CheckFailed as error:
                test.handed_errors.append((error.kind, error.what))
                raise
            if dry_run_body is not None:
                dry_run_body()
            return candidates

        class SpyCounts(rr.Counts):
            def __init__(self):
                super().__init__()
                test.counts.append(self)
        real_run, real_driver = rr.RunScopes.run, rr.Harness.driver

        def scope_run(self_, counts, trackers, **kw):
            test.scope_lists.append(trackers)
            return real_run(self_, counts, trackers, **kw)

        def driver(self_, inputs, counts, trackers, hooks=None):
            test.driver_lists.append(trackers)
            return real_driver(self_, inputs, counts, trackers, hooks)
        rr.ar.fix_app_environment()
        from app.srs import migration
        with mock.patch.object(rr, "ORIGINAL_CONNECTOR", fake_product), mock.patch.object(rr, "Counts", SpyCounts), \
                mock.patch.object(rr.RunScopes, "run", scope_run), mock.patch.object(rr.Harness, "driver", driver), \
                mock.patch.object(migration, "dry_run", dry_run):
            return self.real_case(self.h, "r1", batch=1)

    def test_plan_dry_run_shares_one_list_and_binds_the_plan_and_evidence(self):
        case = self.run_case()
        self.assertEqual(len(self.scope_lists), 1)
        self.assertIs(self.scope_lists[0], self.driver_lists[0])               # one list object for both
        counts = self.counts[0]
        self.assertEqual((counts.created, counts.handed), ({"jpvr_read": 1, "jpvr_write": 0},
                                                           {"jpvr_read": 1, "jpvr_write": 0}))
        self.assertEqual(len(self.scope_lists[0]), 1)                          # the one tracked connection
        self.assertEqual([k["user"] for k in self.guards], ["jpvr_read"])
        self.assertEqual(self.handed_errors, [])
        data = Path(case.plan_path).read_bytes()
        self.assertEqual(case.plan.artifact_sha256, hashlib.sha256(data).hexdigest())
        rr.ar.fix_app_environment()
        from app.srs import migration
        product = hashlib.sha256(migration._plan_json(list(rr.pfile.to_candidates(case.plan))).encode()).hexdigest()
        self.assertEqual(case.plan.product_fingerprint, product)
        a0 = json.loads(case.a0)
        self.assertEqual((a0["format_version"], a0["kind"]), (3, "apply"))
        self.assertEqual(a0["backup_evidence"],
                         {"sha256": hashlib.sha256(Path(case.initial_evidence[0]).read_bytes()).hexdigest()})
        self.assertEqual(a0["based_on"]["sha256"], hashlib.sha256(case.inquiry).hexdigest())
        self.assertIs(case.first_write.approval, case.a0)
        self.assertEqual((case.first_write.artifact_sha256, case.first_write.product_fingerprint),
                         (case.plan.artifact_sha256, case.plan.product_fingerprint))
        e0, e1 = (json.loads(Path(p[0]).read_bytes()) for p in (case.initial_evidence, case.new_evidence))
        self.assertEqual({k: v for k, v in e0.items() if k != "evidence_id"},
                         {k: v for k, v in e1.items() if k != "evidence_id"})
        self.assertNotEqual(e0["evidence_id"], e1["evidence_id"])

    def test_a_failed_plan_dry_run_stops_g1_before_any_first_apply(self):
        def fail():
            raise ValueError("synthetic product failure")
        case_calls = []
        real_case = rr.Harness.case

        def case(self_, *a, **k):                                   # the REAL case, with the failing product stub
            case_calls.append(a)
            return test_case.run_case(fail)
        test_case = self
        with mock.patch.object(rr.Harness, "first_apply", forbidden), mock.patch.object(rr, "PLANNED", ("r1", "r2")), \
                mock.patch.object(rr.Harness, "outside", lambda self_, check_id: ["rows"]), \
                mock.patch.object(rr.Harness, "case", case), self.assertRaises(lay.CheckFailed) as caught:
            rr.g1_gate(self.h)
        self.assertIs(rr.Harness.case, real_case)
        self.assertEqual(len(case_calls), 1)                                  # r2 was never prepared
        self.assertEqual((caught.exception.kind, caught.exception.what),
                         ("preparation_failure", "r1: plan dry-run dry_run_failed"))


NINE = ("run_id", "status", "mode", "config_version", "started_at", "finished_at", "scope_sha256", "summary_sha256",
        "snapshots_sha256")


def values9(**changes) -> dict:
    """Synthetic nine values (fake: NOT evidence that the three real values were equal)."""
    value = {"run_id": 41, "status": "started", "mode": "apply", "config_version": "fsrs-v1",
             "started_at": "2026-10-28T03:00:00+00:00", "finished_at": None, "scope_sha256": "a" * 64,
             "summary_sha256": "b" * 64, "snapshots_sha256": "c" * 64}
    value.update(changes)
    return value


class R3Record(Blocked):
    """The REAL r3_fixed_values through the REAL record save / read-back path (lay.run_recorded, g.Record)."""

    def harness(self, **override):
        evidence = {}
        for name in ("r1", "r2"):
            pre, lock_read, admin_values = values9(run_id=1 if name == "r1" else 2), \
                values9(run_id=1 if name == "r1" else 2), values9(run_id=1 if name == "r1" else 2)
            ev = {"values": {"pre_read": pre, "under_lock": lock_read}, "admin_values": admin_values}
            ev.update(override.get(name, {}))
            evidence[name] = ev
        return SimpleNamespace(evidence=evidence)

    def saved(self, rec):
        return json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))["results"][-1]

    def test_three_dicts_of_nine_values_are_kept_per_run(self):
        rec, _ = self.record()
        h = self.harness()
        originals = {n: (h.evidence[n]["values"]["pre_read"], h.evidence[n]["values"]["under_lock"],
                         h.evidence[n]["admin_values"]) for n in ("r1", "r2")}
        before = json.dumps({n: [dict(x) for x in v] for n, v in originals.items()}, sort_keys=True)
        self.assertTrue(lay.run_recorded(rec, "r3", rr.r3_fixed_values, h))
        last = self.saved(rec)
        self.assertEqual((last["check"], last["status"]), ("r3", "pass"))
        details = last["details"]
        self.assertEqual(details["compared"], ["r1", "r2"])
        self.assertEqual(set(details["values"]), {"r1", "r2"})
        for name in ("r1", "r2"):
            entry = details["values"][name]
            self.assertEqual(set(entry), {"pre_read", "under_lock", "admin_values"})
            for key in ("pre_read", "under_lock", "admin_values"):
                self.assertEqual(set(entry[key]), set(NINE), (name, key))
                self.assertEqual(entry[key], values9(run_id=1 if name == "r1" else 2))
        after = json.dumps({n: [dict(x) for x in v] for n, v in originals.items()}, sort_keys=True)
        self.assertEqual(before, after)                                  # originals untouched
        out = rr.r3_fixed_values(h)
        self.assertIsNot(out["values"]["r1"]["pre_read"], h.evidence["r1"]["values"]["pre_read"])   # a copy
        out["values"]["r1"]["pre_read"]["status"] = "changed"
        self.assertEqual(h.evidence["r1"]["values"]["pre_read"]["status"], "started")

    def test_missing_or_wrong_keys_are_harness_defects(self):
        cases = {"no under_lock": {"r2": {"values": {"pre_read": values9(run_id=2)}}},
                 "no admin": {"r1": {"admin_values": None}},
                 "extra key": {"r1": {"admin_values": dict(values9(run_id=1), extra=1)}},
                 "missing key": {"r2": {"values": {"pre_read": {k: v for k, v in values9(run_id=2).items()
                                                                 if k != "mode"},
                                                    "under_lock": values9(run_id=2)}}}}
        for label, override in cases.items():
            with self.subTest(case=label):
                rec, _ = self.record()
                self.assertFalse(lay.run_recorded(rec, "r3", rr.r3_fixed_values, self.harness(**override)))
                last = self.saved(rec)
                self.assertEqual((last["status"], last.get("kind")), ("fail", "harness_defect"))
                shutil.rmtree(rec.folder)

    def test_different_values_fail(self):
        rec, _ = self.record()
        h = self.harness(r2={"admin_values": values9(run_id=2, summary_sha256="d" * 64)})
        self.assertFalse(lay.run_recorded(rec, "r3", rr.r3_fixed_values, h))
        self.assertEqual(self.saved(rec)["status"], "fail")

    def test_record_or_read_back_failure_is_not_a_pass(self):
        rec, _ = self.record()
        real_append = rec._append

        def append(key, entry):
            if key == "results" and entry.get("status") == "pass":
                raise OSError("disk")
            return real_append(key, entry)
        with mock.patch.object(rec, "_append", append), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(lay.run_recorded(rec, "r3", rr.r3_fixed_values, self.harness()))
        shutil.rmtree(rec.folder)
        rec, _ = self.record()
        real_loads = lay.json.loads

        def loads(text, *a, **k):
            value = real_loads(text, *a, **k)
            if isinstance(value, dict) and "results" in value:
                value["results"][-1]["status"] = "lost"
            return value
        with mock.patch.object(lay.json, "loads", loads), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(lay.run_recorded(rec, "r3", rr.r3_fixed_values, self.harness()))


class CheckValues(Blocked):
    """The REAL check_values orchestration and main(["check-values"]); the gate / check bodies are fakes."""

    def run_values(self, fail=None):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h, *args):
                calls.append((name, args))
                if name == fail:
                    raise lay.CheckFailed("product_defect", name)
                return {"ok": name}
            return fn
        harness = SimpleNamespace(start=lambda: None, close=lambda: calls.append(("closed", ())))
        with mock.patch.object(g, "single_run", lambda target=None: rec), \
                mock.patch.object(rr, "Harness", lambda r: harness), \
                mock.patch.object(rr, "g0_gate", make("g0_gate")), mock.patch.object(rr, "g1_gate", make("g1_gate")), \
                mock.patch.object(rr, "r1_partial_resumed", make("r1")), \
                mock.patch.object(rr, "r2_failed_resumed", make("r2")), mock.patch.object(rr, "r3_fixed_values", make("r3")), \
                mock.patch.object(rr, "values_post", make(rr.VALUES_POST)), mock.patch.object(rr, "check", forbidden), \
                contextlib.redirect_stdout(io.StringIO()):
            code = rr.main(["check-values"])
        saved = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))
        return code, calls, saved

    def test_fixed_order_scope_and_count(self):
        code, calls, saved = self.run_values()
        self.assertEqual(code, 0)
        self.assertEqual([c for c, _ in calls], ["g0_gate", "g1_gate", "r1", "r2", "r3", rr.VALUES_POST, "closed"])
        self.assertEqual(dict(calls)["g1_gate"], (("r1", "r2"),))            # only r1 / r2 prepared
        self.assertEqual([r["check"] for r in saved["results"]],
                         ["g0_gate", "g1_gate", "r1", "r2", "r3", rr.VALUES_POST])
        started = [e for e in saved["events"] if e["kind"] == "check_phase_started"][0]
        self.assertEqual((started["phase"], started["checks"]), ("supplement_values", ["r1", "r2", "r3"]))
        self.assertIn("25/25", started["note"])
        self.assertEqual(rr.VALUES_PLANNED, ("r1", "r2", "r3"))
        self.assertEqual(len(rr.PLANNED), 25)                               # the full check is unchanged

    def test_first_failure_stops_and_is_1(self):
        for fail, ran, not_run in (("g1_gate", ["g0_gate", "g1_gate"], ["r1", "r2", "r3"]),
                                   ("r2", ["g0_gate", "g1_gate", "r1", "r2"], ["r3"]),
                                   ("r3", ["g0_gate", "g1_gate", "r1", "r2", "r3"], []),
                                   (rr.VALUES_POST, ["g0_gate", "g1_gate", "r1", "r2", "r3", rr.VALUES_POST], [])):
            with self.subTest(fail=fail):
                code, calls, saved = self.run_values(fail)
                self.assertEqual(code, 1)
                self.assertEqual([c for c, _ in calls if c != "closed"], ran)
                events = [e for e in saved["events"] if e["kind"] == "not_run"]
                self.assertEqual(events[0]["checks"] if events else [], not_run)
                shutil.rmtree(sorted(self.folder.iterdir())[0])

    def test_post_check_requirements(self):
        ok = {"r1": {"probe": {"probe": {"transaction_isolation": "repeatable read", "transaction_read_only": "on"}}},
              "outside": {"r1": ["a"], "r2": ["b"]}}

        def h(evidence, outside=None, sessions=None):
            return SimpleNamespace(evidence=evidence, outside=lambda cid: (outside or {"r1": ["a"], "r2": ["b"]})[cid],
                                   sessions=lambda: sessions or {"open": 0, "idle_in_transaction": 0})
        self.assertEqual(rr.values_post(h(ok))["sessions"], {"open": 0, "idle_in_transaction": 0})
        bad_probe = dict(ok, r1={"probe": {"probe": {"probe_error": "probe_failed"}}})
        for label, harness in (("other rows changed", h(ok, outside={"r1": ["a"], "r2": ["changed"]})),
                               ("probe failed", h(bad_probe)),
                               ("session left", h(ok, sessions={"open": 1, "idle_in_transaction": 1})),
                               ("no G1 record", h({"r1": ok["r1"]}))):
            with self.subTest(case=label), self.assertRaises(lay.CheckFailed):
                rr.values_post(harness)

    def test_g1_scope_argument(self):
        made = []
        h = SimpleNamespace(case=lambda cid, account="a", **k: made.append(cid) or SimpleNamespace(check_id=cid, plan="p"),
                            first_apply=lambda case, inject=None: ({"phase": "partial"}, 3) if case.check_id == "r1"
                            else ({}, 1),
                            facts=lambda case: {"runs": [{"status": "started" if case.check_id == "r1" else "failed",
                                                          "scope_md5": "s"}], "snapshots": 1, "summary": {"cursor": 1}},
                            outside=lambda cid: ["rows"], sessions=lambda: {"open": 0, "idle_in_transaction": 0},
                            cases={}, evidence={})
        with mock.patch.object(rr, "expected_scope_md5", lambda plan: "s"):
            out = rr.g1_gate(h, ("r1", "r2"))
        self.assertEqual((made, out["databases"]), (["r1", "r2"], 2))
        self.assertEqual(h.evidence["outside"], {"r1": ["rows"], "r2": ["rows"]})


# --- 5. pause points and release order -----------------------------------------------------------------------------

class Pauses(Blocked):
    def test_lock_pause_holds_only_the_nth_write_lock(self):
        pause = rr.LockPause(2, limit=2)
        tracker = SimpleNamespace(pending_pid=55)
        pause.hook("jpvr_read", "SELECT", rr.LOCK_PREFIX + "%s FOR UPDATE", tracker)
        pause.hook("jpvr_write", "SELECT", "SELECT 1", tracker)
        pause.hook("jpvr_write", "SELECT", rr.LOCK_PREFIX + "%s FOR UPDATE", tracker)
        self.assertFalse(pause.reached.is_set())
        pause.release.set()
        pause.hook("jpvr_write", "SELECT", rr.LOCK_PREFIX + "%s FOR UPDATE", tracker)
        self.assertTrue(pause.reached.is_set())
        self.assertEqual(pause.holder_pid, 55)
        self.assertFalse(pause.timed_out)

    def test_handover_pause_nth_write_only(self):
        pause = rr.HandoverPause(3, limit=0.01)
        tracker = SimpleNamespace(_conn=SimpleNamespace(info=SimpleNamespace(backend_pid=9)))
        pause.hook("jpvr_read", 3, tracker)
        pause.hook("jpvr_write", 2, tracker)
        self.assertFalse(pause.reached.is_set())
        pause.hook("jpvr_write", 3, tracker)
        self.assertTrue(pause.reached.is_set() and pause.timed_out)

    def test_contention_wiring_is_fixed(self):
        seen = []
        with mock.patch.object(rr, "race_same_start", lambda h, cid, lock_nth, handover_nth, want_cursor:
                               seen.append((cid, lock_nth, handover_nth, want_cursor)) or {}):
            rr.c1_same_start_cursor(None)
            rr.c2_advanced_then_more(None)
        self.assertEqual(seen, [("c1", 2, 3, 2), ("c2", 3, 4, 3)])

    def test_stop_releases_every_pause_and_joins(self):
        runs = rr.Runs(SimpleNamespace(close_connections=forbidden))
        p1, p2 = rr.LockPause(1, limit=5), rr.HandoverPause(1, limit=5)
        runs.pauses += [p1, p2]
        waiting = threading.Thread(target=lambda: p2.release.wait(5), daemon=True)
        runs.threads["A"] = waiting
        waiting.start()
        runs.stop()
        self.assertTrue(p1.release.is_set() and p2.release.is_set())
        self.assertFalse(waiting.is_alive())

    def test_wait_fails_when_no_thread_is_alive(self):
        runs = rr.Runs(SimpleNamespace())
        dead = threading.Thread(target=lambda: None)
        dead.start()
        dead.join()
        runs.threads["A"] = dead
        with self.assertRaises(lay.CheckFailed) as caught:
            runs.wait(threading.Event(), "P1")
        self.assertEqual(caught.exception.kind, "harness_defect")


# --- 6. command line and import ----------------------------------------------------------------------------------

class Processes(unittest.TestCase):
    def run_code(self, code):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "APP_ENV", "DATABASE_URL")
               and not k.upper().startswith("PG")}
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180, env=env,
                              cwd=str(TESTS_DIR))

    def test_import_does_nothing(self):
        code = ("import sys, os, subprocess, tempfile, psycopg\n"
                f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "def bad(*a, **k): raise SystemExit('EXTERNAL')\n"
                "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad; tempfile.mkdtemp = bad\n"
                "os.mkdir = bad; os.makedirs = bad\n"
                "import _ops_resume_real as rr\n"
                "app = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "print('RESULT', app, rr.T.root.exists())\n")
        done = self.run_code(code)
        self.assertIn("RESULT False False", done.stdout, done.stderr[-600:])

    def test_main_exit_codes_in_a_new_process(self):
        script = str(TESTS_DIR / "_ops_resume_real.py")
        blocker = ("import sys, runpy, subprocess, psycopg\n"
                   f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                   "def bad(*a, **k): raise SystemExit(99)\n"
                   "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad\n"
                   "import _ops_pg62 as g\n"
                   "g.single_run = bad; g.admin_connect = bad; g.listener_pids = bad\n"
                   "import _ops_resume_real as rr; rr.Q2_ADMIN_DATA_CHANGES = None   # the lock branch: exit 1\n"
                   "sys.argv = [{script!r}] + {args!r}\n"
                   "runpy.run_path({script!r}, run_name='__main__')\n")
        for args, want in (([], 2), (["bogus"], 2), (["check", "r1"], 2), (["check"], 1), (["check-values", "r1"], 2),
                           (["check-values", "--checks=r1"], 2)):
            with self.subTest(args=args):
                done = self.run_code(blocker.format(script=script, args=args))
                self.assertEqual(done.returncode, want, done.stdout + done.stderr[-400:])
        # check-values: a PG environment variable stops it before any record / connection (exit 1); without one it
        # goes on to the record lookup, which is blocked here (99 = it reached g.single_run and nothing earlier ran)
        pg_env = "import os; os.environ['PGHOST'] = 'x'\n" + blocker
        done = self.run_code(pg_env.format(script=script, args=["check-values"]))
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr[-400:])
        done = self.run_code(blocker.format(script=script, args=["check-values"]))
        self.assertEqual(done.returncode, 99, done.stdout + done.stderr[-400:])

    def test_cli_resume_entry_stays_closed(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(["resume", "--account", "7", "--run-key", "k", "--personal-id", "1", "--batch-size", "1",
                             "--plan", "p", "--backup-evidence", "e", "--backup-signature", "s",
                             "--initial-evidence", "i", "--initial-evidence-signature", "j"])
        self.assertEqual(code, 4)
        self.assertIn("connection_not_available", out.getvalue())


if __name__ == "__main__":
    unittest.main()
