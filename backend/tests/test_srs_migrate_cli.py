"""OPS_MIGRATION_CLI_PLAN 1-1: `srs_migrate.py dry-run` -- request rules, the FAKE connection flow and
the command-line process.

FAKE parts (said so in each class): driver, connection and observation are fakes, and in `FakeFlow`
the product `dry_run` is replaced by a stub that opens the injected read connection, because the fake
connection cannot run product SQL. The real product query on a synthetic SQLite file is in
`test_srs_migrate_sqlite.py`. Approvals, signatures (test-only temporary keys) and the pre-check are
real. This module imports no app code at import time.

Run directly:      python tests/test_srs_migrate_cli.py
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
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_approval as oa  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_adapter as ta  # noqa: E402  (module only)
import test_ops_observer as to  # noqa: E402  (module only)
import test_ops_product_connect as tpc  # noqa: E402  (module only)

SCRIPT = BACKEND / "scripts" / "srs_migrate.py"
SECRET = ta.SECRET


def request(account=7, run_key="mig-2026-10-26-a", personal=(3, 1), lexeme=(9,)):
    return cli.make_request(account, run_key, list(personal), list(lexeme))


class Requests(unittest.TestCase):
    def test_canonical_cards_and_job_inputs(self):
        a = request(personal=(3, 1), lexeme=(9,))
        b = cli.make_request(7, "mig-2026-10-26-a", [1, 3], [9])
        self.assertEqual(a.cards, (("lexeme", 9), ("personal", 1), ("personal", 3)))
        self.assertEqual(cli.cards_bytes(a.cards), b'[["lexeme",9],["personal",1],["personal",3]]')
        inputs = cli.job_inputs(a)
        self.assertEqual(inputs, cli.job_inputs(b))                       # order of arguments does not matter
        self.assertEqual(inputs["cards_sha256"], hashlib.sha256(
            b"jp-vocab-ops/migration-cards/v1\n" + b'[["lexeme",9],["personal",1],["personal",3]]').hexdigest())
        self.assertEqual((inputs["account_id"], inputs["card_count"]), (7, 3))
        for other in (request(personal=(3,)), request(lexeme=(8,)), request(account=8)):
            self.assertNotEqual(cli.job_inputs(other), inputs)

    def test_invalid_requests(self):
        for args, code in (((7, "k", [1, 1], []), "duplicate_card"), ((0, "k", [1], []), "request_invalid"),
                           ((True, "k", [1], []), "request_invalid"), ((7, "bad key", [1], []), "request_invalid"),
                           ((7, "k", [], []), "request_invalid"), ((7, "k", [0], []), "request_invalid"),
                           ((7, "k", [True], []), "request_invalid"),
                           ((7, "k", list(range(1, cli.MAX_CARDS + 2)), []), "request_invalid")):
            with self.subTest(code=code, args=repr(args)[:40]):
                with self.assertRaises(cli.Refused) as caught:
                    cli.make_request(*args)
                self.assertEqual((caught.exception.status, caught.exception.code), ("usage", code))

    def test_tools_steps(self):
        # contract 4-4-8 (C11) added the apply write step, RESUME_PLAN 9-4 (RS3) the resume write step;
        # dry_run and status stay read steps
        self.assertEqual(oa.TOOLS["srs_migrate"], {"dry_run": "read", "status": "read", "apply": "write",
                                                   "resume": "write"})


class FlowBase(ta.Base):
    """REAL approvals / signatures / pre-check; FAKE driver, connection, observation and a STUB product
    dry_run (it opens the injected read connection and returns synthetic candidates). Helpers only."""

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="srs_migrate_cli_test_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.out = os.path.join(self.folder, "plan.json")
        self.req = request()
        self.conn = tpc.BizConn()
        self.driver = ta.FakeDriver(self.conn)

    def approval(self, **changes) -> bytes:
        values = dict(tool="srs_migrate", accounts=[7], max_accounts=1,
                      steps=[{"command": "dry_run", "access": "read", "role": "ops_read",
                              "profile": self.read_profile()}],
                      job={"key": self.req.run_key, "inputs": cli.job_inputs(self.req)})
        values.update(changes)
        return self.inquiry(**values)

    def flow_inputs(self, approval=None, **changes) -> op.PreflightInput:
        values = dict(command="dry_run", account_id=7, job_key=self.req.run_key, job_inputs=cli.job_inputs(self.req),
                      product_fingerprint=None,
                      connection=op.ConnectionObservation(profile=self.read_profile(), read_only=True))
        values.update(changes)
        return self.inputs(approval or self.approval(), **values)

    def stub(self):
        calls = []

        def dry_run(keys, *, connect=None):
            from app.srs import migration
            calls.append(len(keys))
            with connect(read_only=True) as c:                       # the injected read connection
                c.execute("SELECT 1")
            return tuple(migration.MigrationCandidate(
                key=k, card_fingerprint=None, logs_fingerprint=migration._digest([]), card_version=None,
                quality="unavailable", flags=("card_or_access_missing",), values_json=None, last_log_id=0)
                for k in keys)
        return dry_run, calls

    def run_flow(self, inputs=None, request_=None, driver="default"):
        dry_run, calls = self.stub()
        from app.srs import migration
        with mock.patch.object(migration, "dry_run", dry_run):
            out, code = cli.run_dry_run(request_ or self.req, inputs=inputs or self.flow_inputs(),
                                        expected=to.READ_EXPECTED,
                                        driver=self.driver if driver == "default" else driver, out=self.out)
        return out, code, calls



class FakeFlow(FlowBase):
    """The flow's own checks (see FlowBase for what is real and what is fake)."""

    def test_ok_binds_candidates_file_and_fingerprints(self):
        out, code, calls = self.run_flow()
        self.assertEqual((out["status"], code, calls), ("ok", 0, [3]))
        self.assertEqual(set(out), {"status", "command", "db_identity", "account_id", "job_key", "card_count",
                                    "qualities", "product_fingerprint", "artifact_sha256", "job_plan"})
        self.assertEqual((out["card_count"], out["qualities"]), (3, {"unavailable": 3}))
        plan = pfile.read_plan_file(self.out)
        self.assertEqual(out["artifact_sha256"], plan.artifact_sha256)
        self.assertEqual(out["product_fingerprint"], plan.product_fingerprint)
        self.assertEqual([(c.kind, c.ref_id) for c in plan.candidates], list(self.req.cards))
        expected_plan = oa.job_plan_fingerprint(
            db_identity=out["db_identity"], manifest=op.om.manifest_fingerprint(self.manifest), tool="srs_migrate",
            account_id=7, job_key=self.req.run_key, job_inputs=cli.job_inputs(self.req),
            product_fingerprint=out["product_fingerprint"], artifact_sha256=out["artifact_sha256"])
        self.assertEqual(out["job_plan"], expected_plan)
        self.assertNotEqual(out["job_plan"], oa.job_plan_fingerprint(
            db_identity=out["db_identity"], manifest=op.om.manifest_fingerprint(self.manifest), tool="srs_migrate",
            account_id=7, job_key=self.req.run_key, job_inputs=cli.job_inputs(self.req),
            product_fingerprint=out["product_fingerprint"]))                    # the artifact is in it
        self.assertEqual(len(self.driver.calls), 1)                             # one read connection
        self.assertEqual(self.conn.log[-2:], ["SELECT 1", "COMMIT"])
        self.assertNotIn(SECRET, json.dumps(out))

    def test_request_and_approval_must_match(self):
        other = request(personal=(3,))
        cases = {
            "request cards differ": dict(request_=other),
            "inputs cards differ": dict(inputs=self.flow_inputs(job_inputs=cli.job_inputs(other))),
            "inputs account differ": dict(inputs=self.flow_inputs(account_id=8)),
            "inputs run key differ": dict(inputs=self.flow_inputs(job_key="other-key")),
            "count as text": dict(inputs=self.flow_inputs(job_inputs={**cli.job_inputs(self.req), "card_count": "3"})),
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                out, code, calls = self.run_flow(**kwargs)
                self.assertEqual((out, code, calls), ({"status": "refused", "command": "dry-run",
                                                       "code": "request_mismatch"}, 4, []))
        self.assertEqual(self.driver.calls, [])
        self.assertFalse(os.path.exists(self.out))

    def test_approval_scope_is_checked_by_the_precheck(self):
        other = request(personal=(3,))
        wrong_job = self.approval(job={"key": self.req.run_key, "inputs": cli.job_inputs(other)})
        cases = {
            "approval for other cards": (self.flow_inputs(wrong_job), "preflight_job_input_mismatch"),
            "approval for other account": (self.flow_inputs(self.approval(accounts=[8])), "preflight_account_not_approved"),
            "bad signature": (self.flow_inputs(approval_signature=b"bad"), "preflight_approval_signature_invalid"),
            "manifest not approved": (self.flow_inputs(self.approval(manifest=hashlib.sha256(b"m").hexdigest())),
                                      "preflight_manifest_not_approved"),
            "other target": (self.flow_inputs(target=replace(pf_target(), database="other_db")),
                             "preflight_db_identity_not_approved"),
        }
        for label, (inputs, code) in cases.items():
            with self.subTest(case=label):
                out, status, calls = self.run_flow(inputs=inputs)
                self.assertEqual((out["code"], status, calls), (code, 4, []))
        self.assertEqual(self.driver.calls, [])
        self.assertFalse(os.path.exists(self.out))

    def test_read_role_mismatch_after_connect_is_refused(self):
        conn = tpc.BizConn(to.changed("read", current_user_name="ops_write_prb", session_user_name="ops_write_prb"))
        out, code, _ = self.run_flow(driver=ta.FakeDriver(conn))
        self.assertEqual((out["status"], code), ("refused", 4))
        self.assertTrue(out["code"].startswith("observed_"))
        self.assertFalse(os.path.exists(self.out))

    def test_no_driver_or_production_mode(self):
        out, code, calls = self.run_flow(driver=None)
        self.assertEqual((out["code"], code, calls), ("connection_not_available", 4, []))
        out, code, _ = self.run_flow(inputs=replace(self.flow_inputs(), mode="ops"))
        self.assertEqual((out["code"], code), ("mode_not_synthetic", 4))

    def test_plan_file_conflict_or_write_failure_is_no_success(self):
        with open(self.out, "wb") as handle:
            handle.write(b"existing")
        out, code, _ = self.run_flow()
        self.assertEqual((out["status"], out["code"], code), ("failed", "plan_file_exists", 1))
        with open(self.out, "rb") as handle:
            self.assertEqual(handle.read(), b"existing")
        os.remove(self.out)
        self.driver = ta.FakeDriver(tpc.BizConn())
        with mock.patch.object(os, "link", side_effect=OSError(5, SECRET)):        # MOCKED write failure
            out, code, _ = self.run_flow()
        self.assertEqual((out["status"], out["code"], code), ("failed", "plan_file_write_failed", 1))
        self.assertEqual(os.listdir(self.folder), [])

    def test_refusal_imports_no_app_code(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import unittest, test_srs_migrate_cli as t\n"
                "t.FakeFlow.setUpClass()\n"
                "case = t.FakeFlow('test_ok_binds_candidates_file_and_fingerprints'); case.setUp()\n"
                "before = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "import srs_migrate as cli\n"
                "out, status = cli.run_dry_run(case.req, inputs=case.flow_inputs(approval_signature=b'bad'),"
                " expected=t.to.READ_EXPECTED, driver=case.driver, out=case.out)\n"
                "after = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "print('RESULT', out['code'], status, before, after, len(case.driver.calls))\n"
                "case.doCleanups(); t.FakeFlow.tearDownClass()\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT preflight_approval_signature_invalid 4 False False 0", done.stdout, done.stderr[-800:])



class ApprovalShape(FlowBase):
    """Only a signed srs_migrate INQUIRY approval with a dry_run read step runs (contract 1-1 fix).
    REAL signatures / pre-check; FAKE connection; STUB product dry_run (see FakeFlow)."""

    def other_tool(self, tool):
        return self.flow_inputs(self.approval(tool=tool))

    def apply_shaped(self):
        inquiry = self.approval()
        printed = op.run_synthetic_preflight(self.flow_inputs(inquiry)).job_plan
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001", plan={"7": printed},
                   based_on={"approval_id": doc["approval_id"], "sha256": hashlib.sha256(inquiry).hexdigest()})
        apply = json.dumps(doc).encode()
        return self.flow_inputs(apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"))

    def test_other_tools_and_apply_shape_are_refused_before_anything(self):
        cases = {"d2_snapshot_prune": (self.other_tool("d2_snapshot_prune"), "approval_tool_not_srs_migrate"),
                 "d2_receipt_minimize": (self.other_tool("d2_receipt_minimize"), "approval_tool_not_srs_migrate"),
                 "d2_snapshot_minimize": (self.other_tool("d2_snapshot_minimize"), "approval_tool_not_srs_migrate"),
                 "srs_migrate apply": (self.apply_shaped(), "approval_kind_not_inquiry")}
        for label, (inputs, code) in cases.items():
            with self.subTest(case=label):
                op.run_synthetic_preflight(inputs)          # each is a valid signed approval on its own
                out, status, calls = self.run_flow(inputs=inputs)
                self.assertEqual((out["status"], out.get("code"), status, calls), ("refused", code, 4, []))
                self.assertEqual(self.driver.calls, [])
                self.assertFalse(os.path.exists(self.out))

    def test_right_tool_still_needs_every_check(self):
        out, status, _ = self.run_flow()
        self.assertEqual((out["status"], status), ("ok", 0))
        os.remove(self.out)
        for inputs, code in ((self.flow_inputs(approval_signature=b"bad"), "preflight_approval_signature_invalid"),
                             (self.flow_inputs(self.approval(accounts=[8])), "preflight_account_not_approved")):
            out, status, calls = self.run_flow(inputs=inputs)
            self.assertEqual((out["code"], status, calls), (code, 4, []))

    def test_other_tool_imports_no_app_code(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import test_srs_migrate_cli as t\n"
                "t.ApprovalShape.setUpClass()\n"
                "case = t.ApprovalShape('test_right_tool_still_needs_every_check'); case.setUp()\n"
                "import srs_migrate as cli\n"
                "results = []\n"
                "for inputs in (case.other_tool('d2_snapshot_prune'), case.apply_shaped()):\n"
                "    out, status = cli.run_dry_run(case.req, inputs=inputs, expected=t.to.READ_EXPECTED,"
                " driver=case.driver, out=case.out)\n"
                "    results.append((out['code'], status))\n"
                "app = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "import os\n"
                "print('RESULT', results, app, len(case.driver.calls), os.path.exists(case.out))\n"
                "case.doCleanups(); t.ApprovalShape.tearDownClass()\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT [('approval_tool_not_srs_migrate', 4), ('approval_kind_not_inquiry', 4)] False 0 False",
                      done.stdout, done.stderr[-800:])

def pf_target():
    return ta.pt.pf.TARGET


class CommandLine(unittest.TestCase):
    """New processes; the command line has no real connection path."""

    def run_cli(self, *args, env_extra=None):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        env.update(env_extra or {})
        folder = tempfile.mkdtemp(prefix="srs_migrate_cli_proc_")
        self.addCleanup(shutil.rmtree, folder, True)
        done = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=120,
                              cwd=folder, env=env)
        return done.returncode, json.loads(done.stdout), os.listdir(folder)

    def test_exit_codes_and_no_files(self):
        base = ["--account", "7", "--run-key", "mig-a", "--personal-id", "1", "--out", "plan.json"]
        cases = [((), 2, "usage"), (("dry-run",), 2, "usage"), (("bogus",), 2, "usage"),
                 (("dry-run", *base, "--connect", "x"), 2, "usage"),
                 (("dry-run", *base, "--personal-id", "1"), 2, "duplicate_card"),
                 # contract 4-4-8: apply is implemented; it refuses --out and needs its own arguments (usage)
                 (("apply", *base), 2, "usage"),
                 # contract 4-3: status is implemented now; it refuses --out (usage) and, like dry-run,
                 # has no real connection path on the command line
                 (("status", *base), 2, "usage"), (("status", *base[:-2]), 4, "connection_not_available"),
                 (("dry-run", *base), 4, "connection_not_available"), (tuple(base), 4, "connection_not_available")]
        for args, status, code in cases:
            with self.subTest(args=args[:2]):
                rc, out, files = self.run_cli(*args)
                self.assertEqual((rc, out["code"], files), (status, code, []))
        rc, out, _ = self.run_cli("dry-run", *base, env_extra={"SRS_MIGRATE_DRIVER": "psycopg",
                                                               "DATABASE_URL": "postgresql://x@y/z"})
        self.assertEqual((rc, out["code"]), (4, "connection_not_available"))     # no environment switch

    def test_command_line_never_connects_or_imports_the_app(self):
        code = (f"import sys; sys.path[:0] = [{str(BACKEND / 'scripts')!r}]\n"
                "import psycopg\n"
                "def forbidden(*a, **k): raise AssertionError('connect')\n"
                "psycopg.connect = forbidden\n"
                "import srs_migrate\n"
                "rc = srs_migrate.main(['dry-run', '--account', '7', '--run-key', 'k', '--lexeme-id', '2', '--out', 'p.json'])\n"
                "print('RC', rc, any(m == 'app' or m.startswith('app.') for m in sys.modules))\n")
        folder = tempfile.mkdtemp(prefix="srs_migrate_cli_proc_")
        self.addCleanup(shutil.rmtree, folder, True)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=folder)
        self.assertIn("RC 4 False", done.stdout, done.stderr[-500:])
        self.assertEqual(os.listdir(folder), [])


if __name__ == "__main__":
    unittest.main()
