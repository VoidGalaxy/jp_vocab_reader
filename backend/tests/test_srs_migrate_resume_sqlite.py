"""OPS_MIGRATION_RESUME_PLAN 9-4 (RS3): CLI `resume` with the REAL product apply_plan on a synthetic SQLite
file made by the test.

REAL: approvals (format v3, the prior chain, the basis inquiry), signatures (test-only temporary keys), the
pre-check, the backup evidence checks, the plan file, `read_status` / `judge_status` and the product
functions. TEST INJECTION: the connection source (`srs_migrate._product_connector` replaced by the app's
own SQLite connections to the test file; the provider's observation path is not exercised here) and, where
named, failures around real connections. No PostgreSQL, Neon or backend/vocab.db; nothing here is
PostgreSQL lock or transaction evidence.

Run directly:      python tests/test_srs_migrate_resume_sqlite.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import contextlib  # noqa: E402
import dataclasses  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_approval as oa  # noqa: E402
import _ops_manifest as om  # noqa: E402
import _ops_preflight as op  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only)
import test_srs_migrate_apply_sqlite as sq  # noqa: E402  (module only: the SQLite base)

from app.srs import migration  # noqa: E402

RUN_KEY = flow.RUN_KEY


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_file(path) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


class ResumeBase(sq.Base):
    def setUp(self):
        super().setUp()
        self.log: list = []

    # -- the first apply (C11 path), with A0 binding the first evidence ---------------------------------------
    def source(self, write_connect=None, hook=None):
        def factory(inputs, expected, driver):
            step = inputs.command

            def connect(*, read_only=False):
                self.log.append((step, read_only, inputs.now))
                if hook is not None:
                    hook(step, inputs)
                if step in ("apply", "resume") and write_connect is not None:
                    index = sum(1 for s, r, _ in self.log if s == step)
                    return write_connect(read_only=read_only, index=index)
                return self.connect(read_only=read_only)
            return connect
        return factory

    def first(self, batch=1, v3=True, write_connect=None, clock=None):
        changes = {"format_version": 3, "backup_evidence": {"sha256": sha(read_file(self.ev))}} if v3 else None
        self.inq, self.a0 = self.approvals(self.req, self.plan, batch, pf.READ_PROFILE, pf.WRITE_PROFILE,
                                           apply_changes=changes)
        write, read = self.step_inputs(self.req, self.plan, self.inq, self.a0, batch, pf.READ_PROFILE, pf.WRITE_PROFILE)
        with mock.patch.object(cli, "_product_connector", self.source(write_connect)), mock.patch.dict(os.environ):
            out, code = cli.run_apply(self.req, batch_size=batch, write_inputs=write, read_inputs=read,
                                      scope=flow.SCOPE, driver=lambda **k: None, plan_path=self.path("plan.json"),
                                      evidence_path=self.ev, evidence_signature_path=self.ev_sig,
                                      clock=clock or (lambda: flow.T0))
        self.log.clear()
        return out, code

    # -- the resume approval An and its two step inputs -------------------------------------------------------
    def resume_inputs(self, batch=3, *, plan=None, approval_changes=None, chain=None, evidence_hash=None,
                      write_changes=None):
        plan = plan or self.plan
        doc = json.loads(self.a0)
        doc.pop("backup_evidence", None)
        doc.update(approval_id="app-0000000000000002", format_version=3,
                   supersedes={"approval_id": json.loads(self.a0)["approval_id"], "sha256": sha(self.a0)},
                   steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": pf.READ_PROFILE},
                          {"command": "resume", "access": "write", "role": "ops_write_prb", "profile": pf.WRITE_PROFILE,
                           "args": {"batch_size": str(batch)}}])
        if plan is not self.plan:
            doc["plan"] = {str(self.user): oa.job_plan_fingerprint(
                db_identity=pf.db_identity(), manifest=om.manifest_fingerprint(self.manifest), tool="srs_migrate",
                account_id=self.user, job_key=RUN_KEY, job_inputs=cli.job_inputs(self.req),
                product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)}
        if evidence_hash is not None:
            doc["backup_evidence"] = {"sha256": evidence_hash}
        doc.update(approval_changes or {})
        an = json.dumps(doc).encode()
        link = op.ChainLink(self.a0, self.sign(self.a0, "approval"), self.inq, self.sign(self.inq, "approval"))
        common = dict(inquiry=self.inq, inquiry_signature=self.sign(self.inq, "approval"), account_id=self.user,
                      job_key=RUN_KEY, job_inputs=cli.job_inputs(self.req), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256, prior_chain=(link,) if chain is None else chain)
        write = self.inputs(an, command="resume", args={"batch_size": str(batch)}, secret_dsn=self.dsn(role="ops_write_prb"),
                            connection=op.ConnectionObservation(profile=pf.WRITE_PROFILE, read_only=False), **common)
        read = self.inputs(an, command="status", args={}, secret_dsn=self.dsn(role="ops_read"),
                           connection=op.ConnectionObservation(profile=pf.READ_PROFILE, read_only=True), **common)
        if write_changes:
            write = dataclasses.replace(write, **write_changes)
        return write, read

    def resume(self, batch=3, *, inputs=None, plan_path=None, initial=None, new=None, clock=None, write_connect=None,
               hook=None, **kwargs):
        write, read = inputs or self.resume_inputs(batch, **kwargs)
        new = new or self.evidence(self.user, name="evidence2", evidence_id="bkp-0000000000000002")
        initial = initial or (self.ev, self.ev_sig)
        with mock.patch.object(cli, "_product_connector", self.source(write_connect, hook)), mock.patch.dict(os.environ):
            return cli.run_resume(self.req, batch_size=batch, write_inputs=write, read_inputs=read, scope=flow.SCOPE,
                                  driver=lambda **k: None, plan_path=plan_path or self.path("plan.json"),
                                  initial_evidence_path=initial[0], initial_evidence_signature_path=initial[1],
                                  evidence_path=new[0], evidence_signature_path=new[1],
                                  clock=clock or (lambda: flow.T0))

    def writes(self):
        return [entry for entry in self.log if entry[0] == "resume"]

    def run_state(self):
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = ?",
                                     (RUN_KEY,)).fetchone()
        finally:
            connection.close()
        return row[0], (json.loads(row[1])["cursor"] if row[1] else 0)

    def sql(self, query, params=()):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(query, params)
            connection.commit()
        finally:
            connection.close()

    def refused_without_writes(self, code, exit_code=4, **kwargs):
        before = self.dump()
        out, status = self.resume(**kwargs)
        self.assertEqual((out.get("code"), status), (code, exit_code), out)
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.writes(), [])
        return out


class Resumes(ResumeBase):
    def test_partial_run_resumes_and_keeps_committed_cards(self):
        self.assertEqual(self.first(batch=1)[1], 3)
        first_card, untouched = self.rows([self.cards[0]]), self.rows([self.other_card, self.outside])
        first_snapshot = self.snapshot_ids()
        out, code = self.resume(batch=3)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 0, {"already_applied": 1, "applied": 2}))
        self.assertEqual(self.rows([self.cards[0]]), first_card)                  # committed card kept
        self.assertEqual(self.snapshot_ids()[:1], first_snapshot)                  # and its snapshot
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs"] * 3)
        self.assertEqual(self.rows([self.other_card, self.outside]), untouched)    # other account / outside
        self.assertEqual(self.run_state(), ("completed", 3))
        self.assertEqual((out["restore_verified"], out["backup_artifact_checked"]), (False, False))
        self.assertEqual([s for s, _, _ in self.log][:2], ["status", "resume"])

    def test_failed_run_resumes(self):
        def fail_second_card(*, read_only, index):
            if index == 3:
                raise cli.pc.OpsProductConnectionError("synthetic_connection_failure")
            return self.connect(read_only=read_only)
        out, code = self.first(batch=3, write_connect=fail_second_card)
        self.assertEqual(code, 1)
        self.assertEqual(self.run_state()[0], "failed")
        out, code = self.resume(batch=3)
        self.assertEqual((out["phase"], code), ("completed", 0))
        self.assertEqual(self.run_state(), ("completed", 3))

    def test_batch_partial_resume_reports_3(self):
        self.first(batch=1)
        out, code = self.resume(batch=1)
        self.assertEqual((out["phase"], out["cursor"], code), ("partial", 2, 3))

    def test_every_connection_gets_its_own_time(self):
        self.first(batch=1)
        ticks = iter(flow.T0 + timedelta(seconds=i) for i in range(1, 200))
        self.resume(batch=3, clock=lambda: next(ticks))
        times = [t for _, _, t in self.log]
        self.assertEqual(len(set(times)), len(times))
        self.assertEqual(times, sorted(times))

    def snapshot_ids(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute("SELECT * FROM srs_migration_snapshots ORDER BY id").fetchall()
        finally:
            connection.close()


class LockedComparison(ResumeBase):
    """Changes made between the CLI pre-read and the product call (hooked at the evidence recheck)."""

    def changed(self, change):
        self.first(batch=1)
        real = cli.be.recheck
        state = {}

        def recheck_then_change(evidence, now):
            real(evidence, now)
            change()
            state["after"] = self.dump()
        with mock.patch.object(cli.be, "recheck", recheck_then_change):
            out, code = self.resume(batch=3)
        self.assertEqual((out["code"], out["phase"], code), ("migration_run_changed", "before_first_write", 4))
        self.assertEqual(self.dump(), state["after"])                              # the resume wrote nothing
        self.assertEqual(len(self.writes()), 1)                                    # one first connection, rolled back

    def test_summary_change(self):
        self.changed(lambda: self.sql("UPDATE srs_migration_runs SET summary_json = summary_json || ' '"))

    def test_snapshot_added(self):
        self.changed(lambda: self.sql(
            "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
            "legacy_json, created_at) SELECT run_id, user_id, card_kind, card_ref + 1000, card_version_before, "
            "legacy_json, created_at FROM srs_migration_snapshots"))

    def test_normal_cursor_advance(self):
        self.changed(lambda: migration.apply_plan(self.planned, RUN_KEY, approved=True, batch_size=1,
                                                  connect=self.connect))


class Bindings(ResumeBase):
    def test_plan_not_initial(self):
        self.first(batch=1)
        other = [dataclasses.replace(c, reconversion="restored") if i == 0 else c for i, c in enumerate(self.planned)]
        changed = self.write_plan(other, self.user, name="plan2.json")
        self.assertEqual(changed.product_fingerprint, self.plan.product_fingerprint)   # same product fingerprint
        self.assertNotEqual(changed.artifact_sha256, self.plan.artifact_sha256)
        self.refused_without_writes("resume_plan_not_initial", plan=changed, plan_path=self.path("plan2.json"))

    def test_initial_evidence_binding(self):
        self.first(batch=1, v3=False)                                            # A0 without backup_evidence
        self.refused_without_writes("resume_backup_binding_missing")

    def test_initial_evidence_hash_and_fields(self):
        self.first(batch=1)
        other = self.evidence(self.user, name="other", evidence_id="bkp-0000000000000003")
        self.refused_without_writes("resume_initial_evidence_mismatch", initial=other)
        moved = self.evidence(self.user, name="moved", evidence_id="bkp-0000000000000004", backup_id="synthetic-backup-9")
        self.refused_without_writes("resume_backup_evidence_mismatch", new=moved)
        self.refused_without_writes("resume_backup_evidence_mismatch", new=(self.ev, self.ev_sig))   # same evidence_id

    def test_current_approval_binding(self):
        self.first(batch=1)
        self.refused_without_writes("backup_evidence_binding_mismatch", evidence_hash=sha(b"another document"))
        new = self.evidence(self.user, name="bound", evidence_id="bkp-0000000000000005")
        out, code = self.resume(batch=3, new=new, evidence_hash=sha(read_file(new[0])))
        self.assertEqual(code, 0)

    def test_expired_first_evidence_is_a_record_only(self):
        self.ev, self.ev_sig = self.evidence(self.user, name="short", valid_until=flow.stamp(flow.BASIS + timedelta(minutes=20)))
        self.first(batch=1, clock=lambda: flow.BASIS + timedelta(minutes=15))
        out, code = self.resume(batch=3)                                           # at 12:30: first one expired
        self.assertEqual((out["phase"], code), ("completed", 0))

    def test_chain_steps_role_batch_and_format(self):
        self.first(batch=1)
        self.refused_without_writes("resume_chain_required", chain=())
        write, read = self.resume_inputs(3)                     # signed batch 3, run with batch 2
        self.refused_without_writes("preflight_command_args_not_approved", batch=2,
                                    inputs=(dataclasses.replace(write, args={"batch_size": "2"}), read))
        self.refused_without_writes("mode_not_synthetic", inputs=(dataclasses.replace(write, mode="ops"), read))
        self.refused_without_writes("approval_format_not_v3", approval_changes={"format_version": 2})
        self.refused_without_writes("request_mismatch", inputs=self.resume_inputs(3, write_changes={"command": "apply"}))
        mixed = [{"command": "status", "access": "read", "role": "ops_write_prb", "profile": pf.READ_PROFILE},
                 {"command": "resume", "access": "write", "role": "ops_write_prb", "profile": pf.WRITE_PROFILE,
                  "args": {"batch_size": "3"}}]
        out = self.refused_without_writes("preflight_approval_role_access_mixed", approval_changes={"steps": mixed})
        self.assertEqual(out["phase"], "before_first_write")



class States(ResumeBase):
    def test_states_that_never_write(self):
        cases = [
            ("completed", lambda: None, "migration_run_completed", 4, 3),
            ("cursor end", lambda: self.sql("UPDATE srs_migration_runs SET status = 'started', finished_at = NULL"),
             "cursor_end_not_completed", 6, 3),
            ("closed", lambda: self.sql("UPDATE srs_migration_runs SET status = 'aborted'"), "migration_run_closed", 4, 1),
            ("damaged", lambda: self.sql("UPDATE srs_migration_runs SET summary_json = '{'"), "summary_unreadable", 6, 1),
            ("owner unknown", lambda: self.sql("UPDATE srs_migration_runs SET scope_json = '{}'"),
             "resume_target_not_found", 4, 1),
        ]
        for label, change, code, exit_code, batch in cases:
            with self.subTest(state=label):
                self.reset()
                self.first(batch=batch)
                change()
                self.refused_without_writes(code, exit_code)

    def test_window_boundary(self):
        self.first(batch=1)
        connection = sqlite3.connect(self.db_path)
        try:
            started = connection.execute("SELECT started_at FROM srs_migration_runs").fetchone()[0]
        finally:
            connection.close()
        start = migration.read_utc(started)
        with mock.patch.object(migration, "now_utc", lambda: start + timedelta(days=30)):
            self.refused_without_writes("migration_resume_window_closed")
        with mock.patch.object(migration, "now_utc", lambda: start + timedelta(days=30) - timedelta(seconds=1)):
            out, code = self.resume(batch=3)
        self.assertEqual((out["phase"], code), ("completed", 0))

    def reset(self):
        self.tearDown()
        self.doCleanups()
        self.setUp()


class AfterStart(ResumeBase):
    def assert_after_start(self, out, code):
        self.assertEqual((out["phase"], out["uncertain"], out["next"], out["confirmed"], code),
                         ("after_start", True, "status_required", "unknown", 1), out)
        self.assertNotIn("changes", out)

    def test_expiry_after_a_card(self):
        self.first(batch=1)
        state = {"now": flow.T0, "writes": 0}

        def hook(step, inputs):
            try:
                op.run_synthetic_preflight(inputs)                     # the provider's pre-check, at this time
            except op.OpsPreflightRefused as error:
                raise cli.pc.OpsProductConnectionError(f"preflight_{error.code}") from None
            if step == "resume":
                state["writes"] += 1
                if state["writes"] == 2:                               # after card b's connection
                    state["now"] = flow.T0 + timedelta(minutes=30)     # 13:00: the approvals end
        out, code = self.resume(batch=3, hook=hook, clock=lambda: state["now"])
        self.assert_after_start(out, code)
        self.assertEqual(out["code"], "preflight_approval_expired")
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs", "fsrs", "legacy"])
        self.assertEqual(self.writes()[-1][2], flow.T0 + timedelta(minutes=30))

    def test_card_and_finish_failures(self):
        for label, failing in (("card", 3), ("finish", 4)):
            with self.subTest(failure=label):
                if label == "finish":
                    self.tearDown()
                    self.doCleanups()
                    self.setUp()
                self.first(batch=1)

                def fail(*, read_only, index, failing=failing):
                    if index == failing:
                        raise cli.pc.OpsProductConnectionError("synthetic_connection_failure")
                    return self.connect(read_only=read_only)
                out, code = self.resume(batch=3, write_connect=fail)
                self.assert_after_start(out, code)
                self.assertEqual(self.engine(self.cards[0]), "fsrs")             # the earlier commit is kept


class CommandLine(unittest.TestCase):
    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, json.loads(out.getvalue())["code"]

    def test_resume_has_no_connection_path_and_strict_arguments(self):
        full = ["resume", "--account", "7", "--run-key", "mig-1", "--personal-id", "1", "--batch-size", "2",
                "--plan", "p", "--initial-evidence", "e0", "--initial-evidence-signature", "s0",
                "--backup-evidence", "e1", "--backup-signature", "s1"]
        self.assertEqual(self.run_main(full), (4, "connection_not_available"))
        self.assertEqual(self.run_main([a for a in full if a not in ("--initial-evidence", "e0")]), (2, "usage"))
        self.assertEqual(self.run_main(["apply"] + full[1:]), (2, "usage"))       # apply refuses resume inputs
        self.assertEqual(self.run_main(full[:9] + ["--batch-size", "02"] + full[11:]), (2, "usage"))

    def test_resume_tool_entry(self):
        self.assertEqual(oa.TOOLS["srs_migrate"], {"dry_run": "read", "status": "read", "apply": "write",
                                                   "resume": "write"})


if __name__ == "__main__":
    unittest.main()
