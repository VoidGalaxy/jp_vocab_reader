"""OPS_MIGRATION_CLI_PLAN 4-4-8 (C11): first `apply` -- the FAKE provider path.

REAL: approvals, signatures (test-only temporary keys), the pre-check, the backup evidence check, the
plan file. FAKE: driver, connections and catalog observation (built from the contract privilege table),
and the product `dry_run` / `apply_plan`, which are STUBS here because a fake connection cannot run
product SQL. The real product apply on a synthetic SQLite file is in test_srs_migrate_apply_sqlite.py.
Nothing here is PostgreSQL transaction evidence. This module imports no app code at import time.

Run directly:      python tests/test_srs_migrate_apply_flow.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_backup_evidence as be  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_adapter as ta  # noqa: E402  (module only)
import test_ops_observer as to  # noqa: E402  (module only)
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_ops_product_connect as tpc  # noqa: E402  (module only)

T0 = pf.T0                                                  # inside the test keys' validity window
BASIS = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)   # the inquiry approval's valid_from
RUN_KEY = "mig-apply-2026-10-27"


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


class ApplyFixtures:
    """Shared builders (approvals, plan file, backup evidence) on top of test_ops_preflight.Base."""

    def make_folder(self):
        self.folder = tempfile.mkdtemp(prefix="srs_migrate_apply_test_")
        self.addCleanup(shutil.rmtree, self.folder, True)

    def path(self, name):
        return os.path.join(self.folder, name)

    def write_plan(self, candidates, account, db_identity=None, name="plan.json", product=None, **changes):
        from_obj = list(candidates)
        values = dict(db_identity=db_identity or pf.db_identity(), account_id=account, job_key=RUN_KEY,
                      config_version=self.config_version(), product_fingerprint=product or self.product(from_obj),
                      candidates=from_obj)
        values.update(changes)
        data = pfile.serialize_plan(**values)
        pfile.write_plan_file(self.path(name), data)
        return pfile.read_plan_file(self.path(name))

    def evidence(self, account, name="evidence", **changes):
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": "bkp-0000000000000001",
               "purpose": "synthetic", "db_identity": pf.db_identity(), "account_id": account, "job_key": RUN_KEY,
               "backup_id": "synthetic-backup-1", "taken_at": stamp(BASIS + timedelta(minutes=5)),
               "method": "synthetic", "artifact_sha256": hashlib.sha256(b"synthetic backup").hexdigest(),
               "valid_until": stamp(BASIS + timedelta(minutes=50)), "attested_by": "synthetic signer",
               "restore_verified": False}
        doc.update(changes)
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        with open(self.path(name + ".json"), "wb") as handle:
            handle.write(data)
        with open(self.path(name + ".sig"), "wb") as handle:
            handle.write(self.sign(data, "backup"))
        return self.path(name + ".json"), self.path(name + ".sig")

    def approvals(self, req, plan, batch, read_profile, write_profile, *, tool="srs_migrate", steps=None,
                  apply_changes=None, inquiry_changes=None):
        inputs = cli.job_inputs(req)
        read_step = {"command": "dry_run", "access": "read", "role": "ops_read", "profile": read_profile}
        inquiry = self.inquiry(tool=tool, accounts=[req.account_id], max_accounts=1, steps=[read_step],
                               job={"key": req.run_key, "inputs": inputs}, **(inquiry_changes or {}))
        printed = op.run_synthetic_preflight(self.inputs(
            inquiry, command="dry_run", account_id=req.account_id, job_key=req.run_key, job_inputs=inputs,
            product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256,
            connection=op.ConnectionObservation(profile=read_profile, read_only=True))).job_plan
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001", plan={str(req.account_id): printed},
                   based_on={"approval_id": doc["approval_id"], "sha256": hashlib.sha256(inquiry).hexdigest()},
                   steps=steps if steps is not None else [
                       read_step, {"command": "apply", "access": "write", "role": "ops_write_prb",
                                   "profile": write_profile, "args": {"batch_size": str(batch)}}])
        doc.update(apply_changes or {})
        return inquiry, json.dumps(doc).encode()

    def step_inputs(self, req, plan, inquiry, apply, batch, read_profile, write_profile, **changes):
        common = dict(inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"), account_id=req.account_id,
                      job_key=req.run_key, job_inputs=cli.job_inputs(req), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256)
        common.update(changes)
        write = self.inputs(apply, command="apply", args={"batch_size": str(batch)},
                            secret_dsn=self.dsn(role="ops_write_prb"),
                            connection=op.ConnectionObservation(profile=write_profile, read_only=False), **common)
        read = self.inputs(apply, command="dry_run", args={}, secret_dsn=self.dsn(role="ops_read"),
                           connection=op.ConnectionObservation(profile=read_profile, read_only=True), **common)
        return write, read


# --- the fake catalog built from the CONTRACT privilege table --------------------------------------------

def contract_catalog(access: str, *, extra=(), missing=(), user=None) -> dict:
    cat = to.catalog(access)
    tables = sorted(set(cli.READ_TABLES) | {"users", "account_write_blocks", "srs_config_versions"})
    relations, columns, oids, oid = [], {}, {}, 20000
    for table in tables:
        oid += 1
        oids[("table", "public", table)] = oid
        relations.append((oid, "r", "public", table))
        cols = ["id"]
        if table == "users":
            cols += ["email", "updated_at"]
        elif table in ("vocab_items", "user_word_progress"):
            cols += list(cli.CARD_UPDATE_COLUMNS)
        elif table == "srs_migration_runs":
            cols += ["scope_json", "status", "summary_json", "finished_at"]
        columns[oid] = cols
    oids[("table", cli.IDENTITY_SCHEMA, cli.IDENTITY_TABLE)] = 16401
    relations.append((16401, "r", cli.IDENTITY_SCHEMA, cli.IDENTITY_TABLE))
    columns[16401] = ["identity_value"]
    for seq in ("srs_migration_runs_id_seq", "srs_migration_snapshots_id_seq"):
        oid += 1
        oids[("sequence", "public", seq)] = oid
        relations.append((oid, "S", "public", seq))
    schemas = {"public": 2200, cli.IDENTITY_SCHEMA: 16400}
    privileges = ((cli.READ_PRIVILEGES if access == "read" else cli.WRITE_PRIVILEGES) | set(extra)) - set(missing)
    grants = {("database", 16384, "CONNECT")}
    for kind, schema, name, column, privilege in privileges:
        if kind == "schema":
            grants.add(("schema", schemas[name], privilege))
        elif kind == "sequence":
            grants.add(("sequence", oids[(kind, schema, name)], privilege))
        elif column:
            grants.add(("column", (oids[(kind, schema, name)], column), privilege))
        else:
            grants.add(("relation", oids[(kind, schema, name)], privilege))
    cat.update(relations=relations, columns=columns, grants=grants)
    if user:
        cat["session"]["current_user_name"] = cat["session"]["session_user_name"] = user
    return cat


def contract_objects() -> frozenset:
    tables = sorted(set(cli.READ_TABLES) | {"users", "account_write_blocks", "srs_config_versions"})
    return frozenset({("database", "", to.T.database), ("schema", "", "public"), ("schema", "", cli.IDENTITY_SCHEMA),
                      ("table", cli.IDENTITY_SCHEMA, cli.IDENTITY_TABLE), ("tablespace", "", "pg_default"),
                      ("tablespace", "", "pg_global")}
                     | {("table", "public", t) for t in tables}
                     | {("sequence", "public", s) for s in ("srs_migration_runs_id_seq", "srs_migration_snapshots_id_seq")})


SCOPE = cli.ProfileScope(contract_objects(), "public, pg_catalog", frozenset({"TLSv1.3"}))


def synthetic_candidates(account: int, refs=(1, 2)):
    """Duck-typed candidates for the plan file (the plan file module does not import the app)."""
    digest = hashlib.sha256(b"[]").hexdigest()
    return [SimpleNamespace(key=SimpleNamespace(kind="personal", user_id=account, ref_id=r), card_fingerprint=None,
                            logs_fingerprint=digest, card_version=None, quality="unavailable",
                            flags=("card_or_access_missing",), values_json=None, last_log_id=0, reconversion=None,
                            restart_json=None) for r in refs]


class FlowBase(ApplyFixtures, ta.Base):
    BATCH = 2

    def config_version(self):
        from app.srs.engine import DEFAULT_CONFIG              # only for building the fixture file
        return DEFAULT_CONFIG.config_version

    def product(self, candidates):
        text = json.dumps({"user_id": candidates[0].key.user_id, "config_version": self.config_version(),
                           "cards": [dict(kind=c.key.kind, ref_id=c.key.ref_id, card=c.card_fingerprint,
                                          logs=c.logs_fingerprint, version=c.card_version, quality=c.quality,
                                          values=c.values_json, flags=list(c.flags), last_log_id=c.last_log_id)
                                     for c in candidates]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode()).hexdigest()

    def setUp(self):
        super().setUp()
        self.make_folder()
        self.req = cli.make_request(7, RUN_KEY, [1, 2], [])
        self.plan = self.write_plan(synthetic_candidates(7), 7)
        read_expected, write_expected = cli.contract_profiles(SCOPE, to.T.database)
        self.read_profile = pv.expected_profile_fingerprint(read_expected, role="ops_read", access="read")
        self.write_profile = pv.expected_profile_fingerprint(write_expected, role="ops_write_prb", access="write")
        self.ev, self.ev_sig = self.evidence(7)
        self.calls = {"dry_run": 0, "apply_plan": []}

    def build(self, batch=None, **kwargs):
        batch = batch or self.BATCH
        inquiry, apply = self.approvals(self.req, self.plan, batch, self.read_profile, self.write_profile, **kwargs)
        return self.step_inputs(self.req, self.plan, inquiry, apply, batch, self.read_profile, self.write_profile)

    def stubs(self):
        def dry_run(keys, *, connect=None):
            self.calls["dry_run"] += 1
            with connect(read_only=True) as c:
                c.execute("SELECT 1")
            return pfile.to_candidates(self.plan)

        def apply_plan(plan, run_key, *, approved, batch_size, connect, new_run_only):
            self.calls["apply_plan"].append((run_key, approved, batch_size, new_run_only))
            for _ in range(1 + len(plan) + 1):                      # start, each card, finish (as the product)
                with connect(read_only=False) as c:
                    c.execute("SELECT 1")
            return [{"kind": c.key.kind, "ref_id": c.key.ref_id, "result": "blocked"} for c in plan]
        return dry_run, apply_plan

    def apply_run(self, write=None, read=None, conns=None, batch=None, clock=None, ev=None):
        if write is None:
            write, read = self.build(batch)
        conns = conns if conns is not None else ([tpc.BizConn(contract_catalog("read"))]
                                                 + [tpc.BizConn(contract_catalog("write")) for _ in range(4)])
        self.driver = ta.FakeDriver(*conns)
        dry_run, apply_plan = self.stubs()
        from app.srs import migration
        with mock.patch.object(migration, "dry_run", dry_run), mock.patch.object(migration, "apply_plan", apply_plan):
            return cli.run_apply(self.req, batch_size=batch or self.BATCH, write_inputs=write, read_inputs=read,
                                 scope=SCOPE, driver=self.driver, plan_path=self.path("plan.json"),
                                 evidence_path=(ev or (self.ev, self.ev_sig))[0],
                                 evidence_signature_path=(ev or (self.ev, self.ev_sig))[1],
                                 clock=clock or (lambda: T0))


class FakeFlow(FlowBase):
    def test_contract_profiles_reach_the_provider(self):
        out, code = self.apply_run()
        self.assertEqual((out["status"], out["phase"], code), ("ok", "completed", 5))        # blocked cards
        self.assertEqual(self.calls["apply_plan"], [(RUN_KEY, True, 2, True)])               # exactly once
        users = [d["user"] for d in self.driver.calls]
        self.assertEqual(users, ["ops_read"] + ["ops_write_prb"] * 4)
        self.assertEqual((out["restore_verified"], out["backup_artifact_checked"]), (False, False))
        self.assertNotIn(pf.SECRET, json.dumps(out))

    def test_d12_is_two_column_privileges(self):
        users = {p for p in cli.WRITE_PRIVILEGES if p[2] == "users"}
        self.assertEqual(users, {("table", "public", "users", "id", "SELECT"),
                                 ("table", "public", "users", "updated_at", "UPDATE")})
        self.assertNotIn(("table", "public", "users", "", "UPDATE"), cli.WRITE_PRIVILEGES)
        self.assertFalse({p for p in cli.READ_PRIVILEGES if p[4] != "SELECT" and p[4] != "USAGE"})

    def test_wrong_role_or_excess_privilege_opens_no_write(self):
        cases = {
            "write step observed as the read role": [tpc.BizConn(contract_catalog("read"))]
            + [tpc.BizConn(contract_catalog("write", user="ops_read"))],
            "table-level UPDATE on users": [tpc.BizConn(contract_catalog("read"))]
            + [tpc.BizConn(contract_catalog("write", extra=[("table", "public", "users", "", "UPDATE")]))],
            "read step observed with write privileges": [tpc.BizConn(contract_catalog("read", extra=[
                ("table", "public", "srs_migration_runs", "", "INSERT")]))],
        }
        for label, conns in cases.items():
            with self.subTest(case=label):
                self.calls = {"dry_run": 0, "apply_plan": []}
                out, code = self.apply_run(conns=conns)
                self.assertEqual((out["status"], out["phase"], code), ("refused", "before_first_write", 4))
                self.assertTrue(out["code"].startswith("observed_"))
                self.assertEqual(out.get("changes"), "none")

    def test_other_tool_inquiry_and_missing_steps(self):
        apply_write = {"command": "apply", "access": "write", "role": "ops_write_prb", "profile": self.write_profile,
                       "args": {"batch_size": "2"}}
        read_step = {"command": "dry_run", "access": "read", "role": "ops_read", "profile": self.read_profile}
        cases = {
            "d2_snapshot_prune approval": (dict(tool="d2_snapshot_prune"), "approval_tool_not_srs_migrate"),
            "no dry_run step": (dict(steps=[apply_write]), "preflight_command_not_approved"),
            "no apply step": (dict(steps=[read_step]), "preflight_command_not_approved"),
            "write role on the read step": (dict(steps=[dict(read_step, role="ops_write_prb"), apply_write]),
                                            "preflight_approval_role_access_mixed"),
        }
        for label, (kwargs, code) in cases.items():
            with self.subTest(case=label):
                try:
                    write, read = self.build(**kwargs)
                except Exception as error:                            # refused while building: parse-level
                    self.assertIn(getattr(error, "code", ""), ("approval_role_access_mixed",))
                    continue
                self.calls = {"dry_run": 0, "apply_plan": []}
                out, status = self.apply_run(write=write, read=read)
                self.assertEqual((out["code"], status, self.calls["dry_run"], self.driver.calls), (code, 4, 0, []))
        inquiry, _ = self.approvals(self.req, self.plan, 2, self.read_profile, self.write_profile)
        write, read = self.step_inputs(self.req, self.plan, inquiry, inquiry, 2, self.read_profile, self.write_profile)
        out, status = self.apply_run(write=write, read=read)                 # an inquiry used for apply
        self.assertEqual((out["code"], status, self.driver.calls), ("preflight_command_not_approved", 4, []))

    def test_signed_batch_size_must_match(self):
        write, read = self.build(batch=2)
        out, code = self.apply_run(write=write, read=read, batch=3)          # inputs say 2, the run says 3
        self.assertEqual((out["code"], code), ("request_mismatch", 4))
        write3 = op.PreflightInput(**{**write.__dict__, "args": {"batch_size": "3"}})
        out, code = self.apply_run(write=write3, read=read, batch=3)         # signed 2, inputs and run 3
        self.assertEqual((out["code"], code, self.driver.calls), ("preflight_command_args_not_approved", 4, []))
        for bad in (0, 2001, True, 2.0, "2"):
            with self.subTest(batch=repr(bad)):
                out, code = cli.run_apply(self.req, batch_size=bad, write_inputs=write, read_inputs=read, scope=SCOPE,
                                          driver=ta.FakeDriver(), plan_path=self.path("plan.json"),
                                          evidence_path=self.ev, evidence_signature_path=self.ev_sig)
                self.assertEqual((out["code"], code), ("batch_size_invalid", 4))

    def test_backup_evidence_problems_open_nothing(self):
        cases = {
            "missing": ((self.path("none.json"), self.ev_sig), "backup_evidence_unreadable"),
            "other job": (self.evidence(7, name="job", job_key="mig-other"), "backup_evidence_job_mismatch"),
            "other account": (self.evidence(7, name="acct", account_id=8), "backup_evidence_account_mismatch"),
            "expired": (self.evidence(7, name="old", valid_until=stamp(BASIS + timedelta(minutes=20))),
                        "backup_evidence_expired"),
        }
        tampered = self.path("tampered.json")
        with open(self.ev, "rb") as src, open(tampered, "wb") as dst:
            dst.write(src.read().replace(b"synthetic-backup-1", b"synthetic-backup-2"))
        cases["tampered"] = ((tampered, self.ev_sig), "backup_signature_invalid")
        for label, (ev, code) in cases.items():
            with self.subTest(case=label):
                self.calls = {"dry_run": 0, "apply_plan": []}
                out, status = self.apply_run(ev=ev)
                self.assertEqual((out["code"], status, self.calls["dry_run"], self.driver.calls), (code, 4, 0, []))

    def test_expiry_during_dry_run_opens_no_write_connection(self):
        # C11 fix: the clock is read at the pre-check, the evidence check, the read connection and the recheck
        times = iter([T0, T0, T0, BASIS + timedelta(minutes=50)])    # valid first, expired at the recheck
        out, code = self.apply_run(clock=lambda: next(times))
        self.assertEqual((out["code"], code, self.calls["dry_run"], self.calls["apply_plan"]),
                         ("backup_evidence_expired", 4, 1, []))
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"])           # read only, no write

    def test_refusal_imports_no_app_code(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import test_srs_migrate_apply_flow as t, srs_migrate as cli\n"
                "t.FlowBase.setUpClass()\n"
                "case = t.FakeFlow('test_contract_profiles_reach_the_provider'); case.setUp()\n"
                "import sys as s\n"
                "for m in [m for m in s.modules if m == 'app' or m.startswith('app.')]: del s.modules[m]\n"
                "write, read = case.build()\n"
                "import dataclasses\n"
                "write = dataclasses.replace(write, approval_signature=b'bad')\n"
                "read = dataclasses.replace(read, approval_signature=b'bad')\n"
                "driver = t.ta.FakeDriver()\n"
                "out, status = cli.run_apply(case.req, batch_size=2, write_inputs=write, read_inputs=read, scope=t.SCOPE,"
                " driver=driver, plan_path=case.path('plan.json'), evidence_path=case.ev,"
                " evidence_signature_path=case.ev_sig, clock=lambda: t.T0)\n"
                "app = any(m == 'app' or m.startswith('app.') for m in s.modules)\n"
                "print('RESULT', out['code'], status, app, len(driver.calls))\n"
                "case.doCleanups(); t.FlowBase.tearDownClass()\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT preflight_approval_signature_invalid 4 False 0", done.stdout, done.stderr[-800:])



SHORT = {"valid_until": "2026-10-21T12:40:00Z"}           # approvals end before the test keys' window does
EXPIRY = datetime(2026, 10, 21, 12, 40, 0, tzinfo=timezone.utc)


class DecisionTime(FlowBase):
    """C11 review fix: the clock, not PreflightInput.now, is the time of every approval judgement.
    REAL approvals / pre-check; FAKE provider connections; STUB product functions (see FlowBase)."""

    def build_short(self):
        return self.build(apply_changes=SHORT, inquiry_changes=SHORT)

    def test_expired_by_the_clock_before_anything(self):
        write, read = self.build_short()                              # inputs.now = T0 (12:30) is still valid
        out, code = self.apply_run(write=write, read=read, clock=lambda: EXPIRY)
        self.assertEqual((out["code"], out["phase"], code, self.driver.calls, self.calls["dry_run"]),
                         ("preflight_approval_expired", "before_first_write", 4, [], 0))

    def test_boundary(self):
        write, read = self.build_short()
        out, code = self.apply_run(write=write, read=read, clock=lambda: EXPIRY - timedelta(seconds=1))
        self.assertEqual((out["phase"], code), ("completed", 5))                    # one second before: allowed

    def test_expired_after_dry_run_before_the_first_write(self):
        write, read = self.build_short()
        state = {"now": T0}

        def dry_run_then_expire(keys, *, connect=None):
            with connect(read_only=True) as c:
                c.execute("SELECT 1")
            state["now"] = EXPIRY                                     # expires while the read step runs
            return pfile.to_candidates(self.plan)
        evidence_until = BASIS + timedelta(minutes=50)                 # the backup evidence is still valid
        self.assertLess(EXPIRY, evidence_until)
        self.driver = ta.FakeDriver(tpc.BizConn(contract_catalog("read")), tpc.BizConn(contract_catalog("write")))
        from app.srs import migration
        _, apply_stub = self.stubs()
        with mock.patch.object(migration, "dry_run", dry_run_then_expire), \
                mock.patch.object(migration, "apply_plan", apply_stub):
            out, code = cli.run_apply(self.req, batch_size=2, write_inputs=write, read_inputs=read, scope=SCOPE,
                                      driver=self.driver, plan_path=self.path("plan.json"), evidence_path=self.ev,
                                      evidence_signature_path=self.ev_sig, clock=lambda: state["now"])
        self.assertEqual((out["code"], out["phase"], code), ("preflight_approval_expired", "before_first_write", 4))
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"])        # no write connection

    def test_every_connection_gets_its_own_time(self):
        ticks = iter(T0 + timedelta(seconds=i) for i in range(1, 100))
        seen = []
        real = pv.op.run_synthetic_preflight

        def spy(inputs):
            seen.append((inputs.command, inputs.now))
            return real(inputs)
        write, read = self.build()
        with mock.patch.object(pv.op, "run_synthetic_preflight", spy):
            out, code = self.apply_run(write=write, read=read, clock=lambda: next(ticks))
        self.assertEqual((out["phase"], code), ("completed", 5))
        initial, provider = seen[:2], seen[2:]
        self.assertEqual([c for c, _ in initial], ["apply", "dry_run"])
        self.assertEqual(initial[0][1], initial[1][1])                 # both steps judged at one time
        self.assertEqual([c for c, _ in provider], ["dry_run"] + ["apply"] * 4)
        times = [t for _, t in provider]
        self.assertEqual(len(set(times)), len(times))                 # a new time for every connection request
        self.assertTrue(all(t > initial[0][1] for t in times))
        self.assertTrue(all(t > T0 for _, t in seen))                  # never the inputs' fixed now

    def test_args_are_checked_before_conversion(self):
        write, read = self.build()
        bad_values = {"int": 1, "none": None, "list": [("batch_size", "2")], "int value": {"batch_size": 2},
                      "bad key": {"Batch": "2"}, "bad value": {"batch_size": "2 "}, "secret value": {"batch_size": pf.SECRET + "!"},
                      "extra key": {"batch_size": "2", "x": "1"}}
        well_formed = {"extra key"}                                   # right shape, wrong value: exact compare
        for which in ("write", "read"):
            for label, value in bad_values.items():
                if which == "read" and label == "extra key":
                    value = {"x": "1"}
                with self.subTest(step=which, case=label):
                    w = op.PreflightInput(**{**write.__dict__, "args": value}) if which == "write" else write
                    r = op.PreflightInput(**{**read.__dict__, "args": value}) if which == "read" else read
                    driver = ta.FakeDriver()
                    out, code = cli.run_apply(self.req, batch_size=2, write_inputs=w, read_inputs=r, scope=SCOPE,
                                              driver=driver, plan_path=self.path("plan.json"), evidence_path=self.ev,
                                              evidence_signature_path=self.ev_sig, clock=lambda: T0)
                    wanted = "request_mismatch" if label in well_formed else "args_invalid"
                    self.assertEqual((out["code"], code, driver.calls), (wanted, 4, []))
                    self.assertNotIn(pf.SECRET, json.dumps(out))

    def test_backup_recheck_still_runs(self):
        state = {"calls": 0}

        def clock():                                                  # pre-check, evidence, read connection: valid
            state["calls"] += 1
            return T0 if state["calls"] < 4 else BASIS + timedelta(minutes=50)
        out, code = self.apply_run(clock=clock)
        self.assertEqual((out["code"], code, self.calls["apply_plan"]), ("backup_evidence_expired", 4, []))
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"])

SEQUENCE_USAGE = frozenset({("sequence", "public", "srs_migration_runs_id_seq", "", "USAGE"),
                            ("sequence", "public", "srs_migration_snapshots_id_seq", "", "USAGE")})


class SequenceContract(FlowBase):
    """OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN S2: the write profile without the two sequence USAGE privileges.
    Fake catalogs and connections; not evidence of PostgreSQL privileges or identity INSERTs."""

    def test_only_the_two_sequence_usage_privileges_are_gone(self):              # s-2
        self.assertFalse(SEQUENCE_USAGE & cli.WRITE_PRIVILEGES)
        self.assertFalse({p for p in cli.READ_PRIVILEGES | cli.WRITE_PRIVILEGES if p[0] == "sequence"})
        self.assertTrue({("sequence", "public", s) for s in ("srs_migration_runs_id_seq",
                                                             "srs_migration_snapshots_id_seq")} <= SCOPE.objects)
        self.assertEqual(pv.PROFILE_VERSION, "jp-vocab-ops/profile/v2")              # same algorithm, new value
        old = cli.WRITE_PRIVILEGES | SEQUENCE_USAGE
        self.assertEqual(old - cli.WRITE_PRIVILEGES, SEQUENCE_USAGE)

    def test_each_sequence_usage_alone_is_excess(self):                            # s-3
        for usage in sorted(SEQUENCE_USAGE):
            with self.subTest(usage=usage[2]):
                self.calls = {"dry_run": 0, "apply_plan": []}
                conns = [tpc.BizConn(contract_catalog("read"))] + [tpc.BizConn(contract_catalog("write", extra=[usage]))]
                out, code = self.apply_run(conns=conns)
                self.assertEqual((out["code"], out["phase"], code), ("observed_privileges_excess", "before_first_write", 4))
                self.assertEqual(out.get("changes"), "none")
                # the stub product asks for its first write connection once; the provider refuses it
                self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read", "ops_write_prb"])

    def old_profile(self):
        _, new = cli.contract_profiles(SCOPE, to.T.database)
        old = pv.ExpectedProfile(new.objects, new.privileges | SEQUENCE_USAGE, new.search_path, new.tls_versions)
        return pv.expected_profile_fingerprint(old, role="ops_write_prb", access="write")

    def test_an_approval_signed_for_the_old_profile_is_refused(self):              # s-4
        old = self.old_profile()
        self.assertNotEqual(old, self.write_profile)
        inquiry, apply = self.approvals(self.req, self.plan, self.BATCH, self.read_profile, old)
        write, read = self.step_inputs(self.req, self.plan, inquiry, apply, self.BATCH, self.read_profile, old)
        for label, extra in (("old privileges observed", sorted(SEQUENCE_USAGE)), ("new privileges observed", [])):
            with self.subTest(case=label):
                self.calls = {"dry_run": 0, "apply_plan": []}
                conns = [tpc.BizConn(contract_catalog("read"))] + [tpc.BizConn(contract_catalog("write", extra=extra))]
                out, code = self.apply_run(write=write, read=read, conns=conns)
                self.assertEqual((out["status"], out["phase"], code), ("refused", "before_first_write", 4), out)
                self.assertEqual(out["code"], "expected_profile_not_approved")    # signed profile != contract
                self.assertEqual(out.get("changes"), "none")
                self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"])   # no write connection opened

    def test_other_required_write_privileges_are_still_required(self):             # s-5
        for missing in (("table", "public", "users", "updated_at", "UPDATE"),
                        ("table", "public", "srs_migration_runs", "", "INSERT"),
                        ("table", "public", "srs_migration_snapshots", "", "INSERT")):
            with self.subTest(missing=missing[2:]):
                self.calls = {"dry_run": 0, "apply_plan": []}
                conns = [tpc.BizConn(contract_catalog("read"))] + [tpc.BizConn(contract_catalog("write", missing=[missing]))]
                out, code = self.apply_run(conns=conns)
                self.assertEqual((out["code"], out["phase"], code), ("observed_privileges_missing", "before_first_write", 4))
                self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read", "ops_write_prb"])



class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        folder = tempfile.mkdtemp(prefix="srs_migrate_apply_cli_")
        self.addCleanup(shutil.rmtree, folder, True)
        done = subprocess.run([sys.executable, str(BACKEND / "scripts" / "srs_migrate.py"), *args], capture_output=True,
                              text=True, timeout=120, cwd=folder,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        return done.returncode, json.loads(done.stdout), os.listdir(folder)

    def test_apply_arguments_and_closed_entry(self):
        base = ["apply", "--account", "7", "--run-key", "k", "--personal-id", "1", "--plan", "p",
                "--backup-evidence", "e", "--backup-signature", "s"]
        rc, out, files = self.run_cli(*base, "--batch-size", "10")
        self.assertEqual((rc, out["code"], files), (4, "connection_not_available", []))
        for bad in ("0", "010", "+5", "2001", "1.0", "true", " 5", "5 ", "-1", "１"):
            with self.subTest(batch=bad):
                rc, out, _ = self.run_cli(*base, "--batch-size", bad)
                self.assertEqual((rc, out["code"]), (2, "batch_size_invalid") if bad not in () else (2, "usage"))
        rc, out, _ = self.run_cli(*base)                               # --batch-size missing
        self.assertEqual((rc, out["code"]), (2, "usage"))
        rc, out, _ = self.run_cli(*base, "--batch-size", "10", "--out", "x")
        self.assertEqual((rc, out["code"]), (2, "usage"))


if __name__ == "__main__":
    unittest.main()
