"""OPS_MIGRATION_RESUME_PLAN 9-3 (RS2b): approval format v3 `backup_evidence`, the first apply's evidence
binding, the record check of a past evidence document, and the verified A0 / I0 of a pre-check.

Synthetic only: the approval-format checks use the existing fake verifier; the record check, the pre-check
chain and the first-apply flow use the existing synthetic OpenSSH test keys made by those test classes.
No PostgreSQL, no real data, no operation mode. Run directly: python tests/test_ops_resume_binding.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import _ops_approval as ops  # noqa: E402
import _ops_backup_evidence as be  # noqa: E402
import _ops_preflight as op  # noqa: E402
import test_ops_approval as ta  # noqa: E402  (helpers)
import test_ops_backup_evidence as tb  # noqa: E402  (helpers)
import test_ops_preflight as tp  # noqa: E402  (helpers)
import test_srs_migrate_apply_flow as tf  # noqa: E402  (helpers)

DIGEST = hashlib.sha256(b"evidence document").hexdigest()


# --- 1. approval format v3 ------------------------------------------------------------------------------

class FormatV3(ta.Base):
    def apply_doc(self, version, **extra):
        inquiry_bytes, inquiry = self.signed(ta.inquiry_doc(format_version=version))
        doc = ta.inquiry_doc(kind="apply", approval_id="app-0000000000000001", format_version=version,
                             steps=[ta._read("status"), ta._write("prepare")],
                             based_on={"approval_id": inquiry.approval_id,
                                       "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                             plan={"7": ta.plan_for(7), "8": ta.plan_for(8)})
        doc.update(extra)
        return doc

    def test_v3_apply_binds_the_evidence_hash(self):
        data, approval = self.signed(self.apply_doc(3, backup_evidence={"sha256": DIGEST}))
        self.assertEqual((approval.format_version, approval.backup_evidence_sha256), (3, DIGEST))
        self.assertEqual(approval.sha256, hashlib.sha256(data).hexdigest())      # bound by the signed bytes
        _, plain = self.signed(self.apply_doc(3))
        self.assertIsNone(plain.backup_evidence_sha256)                        # optional, absent = None

    def test_v1_v2_and_inquiries_keep_their_rules(self):
        for version in (1, 2):
            with self.subTest(version=version):
                data, approval = self.signed(self.apply_doc(version))
                self.assertIsNone(approval.backup_evidence_sha256)
                self.assertEqual(approval.sha256, hashlib.sha256(data).hexdigest())
                self.refused("approval_fields_invalid", ops.parse_approval,
                             ta.encode(self.apply_doc(version, backup_evidence={"sha256": DIGEST})))
        for version in (1, 2, 3):
            with self.subTest(inquiry=version):
                self.refused("approval_fields_invalid", ops.parse_approval,
                             ta.encode(ta.inquiry_doc(format_version=version, backup_evidence={"sha256": DIGEST})))

    def test_job_plan_fingerprint_has_no_new_input(self):
        self.assertEqual(ta.plan_for(7), ops.job_plan_fingerprint(
            db_identity=ta.H["db"], manifest=ta.H["manifest"], tool="prb_recover", account_id=7,
            job_key=ta.JOB["key"], job_inputs=ta.JOB["inputs"], product_fingerprint=ta.H["product"]))

    def test_malformed_field_is_refused(self):
        for value in (None, {}, {"sha256": DIGEST.upper()}, {"sha256": "x"}, {"sha256": DIGEST, "extra": 1},
                      [DIGEST], DIGEST, {"sha256": None}):
            with self.subTest(value=repr(value)[:40]):
                self.refused("approval_backup_evidence_invalid", ops.parse_approval,
                             ta.encode(self.apply_doc(3, backup_evidence=value)))

    def test_changing_the_field_after_signing_breaks_the_signature(self):
        data = ta.encode(self.apply_doc(3, backup_evidence={"sha256": DIGEST}))
        signature = self.verifier.sign(data)
        tampered = data.replace(DIGEST.encode(), hashlib.sha256(b"other").hexdigest().encode())
        self.refused("approval_signature_invalid", ops.verify_signed, tampered, signature, mode="synthetic",
                     verifier=self.verifier)


# --- 2. the record check of a past evidence document --------------------------------------------------------

LATER = tb.BASIS + timedelta(days=3)                 # long after the document's valid_until


class EvidenceRecord(tb.Base):
    def record(self, data=None, signature=None, *, now=LATER, expected=None, trust=None, mode="synthetic"):
        data = data if data is not None else tb.encode(tb.doc())
        signature = signature if signature is not None else self.sign(data)
        return be.verify_backup_evidence_record(data, signature, mode=mode, expected=expected or self.expected(),
                                                trust=trust or self.trust, now=now)

    def test_expired_document_passes_as_a_record_only(self):
        self.refused("backup_evidence_expired", self.verify, now=LATER)       # current check: unchanged
        record = self.record()
        self.assertIsInstance(record, be.BackupEvidenceRecord)
        self.assertNotIsInstance(record, be.BackupEvidence)
        self.assertEqual((record.restore_verified, record.artifact_checked), (False, False))
        self.refused("backup_evidence_value_invalid", be.recheck, record, tb.NOW)   # never a current evidence

    def test_record_keeps_every_other_check(self):
        data = tb.encode(tb.doc())
        revoked_trust = op.SyntheticTrust(self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*", window=None,
                                                            key="revoked"), self.keys.pub["revoked"] + b"\n",
                                          tb.sigtests.PRINCIPAL)
        cases = [
            ("backup_signature_invalid", dict(data=tb.encode(tb.doc(backup_id="other-1")), signature=self.sign(data))),
            ("backup_signature_invalid", dict(data=data, signature=self.sign(data, key="stranger"))),
            ("backup_signature_invalid", dict(data=data, signature=self.sign(data, key="revoked"),
                                              trust=revoked_trust)),
            ("backup_signature_invalid", dict(data=data, signature=self.sign(data, subject="approval"))),
            ("mode_not_synthetic", dict(mode="ops")),
            ("backup_evidence_target_mismatch", dict(expected=self.expected(db_identity="0" * 64))),
            ("backup_evidence_account_mismatch", dict(expected=self.expected(account_id=8))),
            ("backup_evidence_job_mismatch", dict(expected=self.expected(job_key="mig-other"))),
            ("backup_evidence_too_old", dict(expected=self.expected(basis_from=tb.BASIS + timedelta(hours=1)))),
            ("backup_evidence_from_future", dict(now=tb.BASIS + timedelta(minutes=5))),
        ]
        for code, kwargs in cases:
            with self.subTest(code=code, case=sorted(kwargs)):
                self.refused(code, self.record, **kwargs)
        for change, code in (({"restore_verified": True}, "backup_evidence_restore_claim_invalid"),
                             ({"purpose": "ops"}, "backup_evidence_purpose_mismatch"),
                             ({"taken_at": tb.stamp(tb.BASIS + timedelta(minutes=60))}, "backup_evidence_value_invalid")):
            with self.subTest(change=change):
                bad = tb.encode(tb.doc(**change))
                self.refused(code, self.record, bad, self.sign(bad))


# --- 3. verified A0 / I0 from the real pre-check ------------------------------------------------------------

class InitialApprovals(tp.ApplyChain):
    def chain_run(self):
        first = self.doc("app-0000000000000001")
        current = self.doc("app-0000000000000002", supersedes=self.ref(first))
        inputs = self.run_inputs(current, [self.link(first)])
        return first, inputs, op.run_synthetic_preflight(inputs)

    def test_verified_first_pair(self):
        first, inputs, result = self.chain_run()
        a0, i0 = op.initial_apply_approvals(result, inputs)
        self.assertEqual((a0.sha256, i0.sha256), (hashlib.sha256(first).hexdigest(), hashlib.sha256(self.inq).hexdigest()))
        self.assertTrue(a0.verified and i0.verified)
        self.assertNotIn("app-0000000000000001", repr(result))                # the public result shows nothing
        self.assertNotIn("first_apply", repr(result.verified))                  # the new fields are never printed
        self.assertNotIn("first_inquiry", repr(result.verified))

    def test_empty_chain_and_forged_results(self):
        inputs = self.run_inputs(self.doc("app-0000000000000001"), [])
        result = op.run_synthetic_preflight(inputs)
        with self.assertRaises(op.OpsPreflightRefused) as caught:
            op.initial_apply_approvals(result, inputs)
        self.assertEqual(caught.exception.code, "approval_chain_first_missing")
        first, inputs, result = self.chain_run()
        a0, i0 = result.verified.first_apply, result.verified.first_inquiry
        forged = [
            ("not a result", object(), inputs),
            ("unverified A0", replace(result, verified=replace(result.verified, first_apply=replace(a0, verified=False))), inputs),
            ("other bytes", result, replace(inputs, prior_chain=(self.link(self.doc("app-0000000000000009")),))),
            ("I0 swapped", replace(result, verified=replace(result.verified, first_inquiry=a0)), inputs),
            ("no verified part", replace(result, verified=None), inputs),
        ]
        for label, res, inp in forged:
            with self.subTest(case=label):
                with self.assertRaises(op.OpsPreflightRefused) as caught:
                    op.initial_apply_approvals(res, inp)
                self.assertEqual(caught.exception.code, "preflight_result_mismatch")

    def test_prior_chain_shape_is_checked_before_the_first_item(self):
        """RS2b review fix: the same tuple / ChainLink / bytes / limit rules as the pre-check, before index 0."""
        first, inputs, result = self.chain_run()
        good = inputs.prior_chain[0]
        cases = [
            ("int", 1, "approval_chain_invalid"),
            ("dict", {"0": good}, "approval_chain_invalid"),
            ("list of a valid link", [good], "approval_chain_invalid"),
            ("None", None, "approval_chain_invalid"),
            ("bool", True, "approval_chain_invalid"),
            ("tuple with a non-link", (good, "x"), "approval_chain_invalid"),
            ("tuple with a str field", (replace(good, approval=good.approval.decode()),), "approval_chain_invalid"),
            ("too long", (good,) * (op.oa.MAX_CHAIN_LINKS + 1), "approval_chain_too_long"),
            ("empty tuple", (), "approval_chain_first_missing"),
        ]
        for label, chain, code in cases:
            with self.subTest(case=label):
                bad = object.__new__(op.PreflightInput)
                for name in op.PreflightInput.__dataclass_fields__:
                    object.__setattr__(bad, name, getattr(inputs, name))
                object.__setattr__(bad, "prior_chain", chain)
                with self.assertRaises(op.OpsPreflightRefused) as caught:
                    op.initial_apply_approvals(result, bad)
                error = caught.exception
                self.assertEqual(error.code, code)
                self.assertTrue(error.__suppress_context__ or error.__context__ is None)
                self.assertNotIn(good.approval.decode()[:40], str(error) + repr(error))
        a0, i0 = op.initial_apply_approvals(result, inputs)                 # the normal tuple path is unchanged
        self.assertEqual(a0.sha256, hashlib.sha256(first).hexdigest())

    def test_past_permissions_are_not_merged(self):
        first = self.doc("app-0000000000000001")
        current = self.doc("app-0000000000000002", supersedes=self.ref(first),
                           steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": tp.READ_PROFILE}])
        inputs = self.run_inputs(current, [self.link(first)])                 # A0 had "prepare"; current does not
        with self.assertRaises(op.OpsPreflightRefused) as caught:
            op.run_synthetic_preflight(inputs)
        self.assertEqual(caught.exception.code, "command_not_approved")

    def test_operation_mode_stays_closed(self):
        _, inputs, _ = self.chain_run()
        with self.assertRaises(op.OpsPreflightRefused) as caught:
            op.run_synthetic_preflight(replace(inputs, mode="ops"))
        self.assertEqual(caught.exception.code, "mode_not_synthetic")


# --- 4. the first apply: the bound evidence hash ---------------------------------------------------------

class FirstApplyBinding(tf.FlowBase):
    def bound(self, digest):
        return self.build(apply_changes={"format_version": 3, "backup_evidence": {"sha256": digest}})

    def evidence_hash(self):
        with open(self.ev, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()

    def test_matching_hash_runs_as_before(self):
        write, read = self.bound(self.evidence_hash())
        out, code = self.apply_run(write=write, read=read)
        self.assertEqual((out["phase"], code), ("completed", 5))
        self.assertEqual(self.calls["apply_plan"], [(tf.RUN_KEY, True, 2, True)])

    def test_mismatch_stops_before_import_connection_and_product(self):
        write, read = self.bound(hashlib.sha256(b"another document").hexdigest())
        out, code = self.apply_run(write=write, read=read)
        self.assertEqual((out["code"], code), ("backup_evidence_binding_mismatch", 4))
        self.assertEqual((self.driver.calls, self.calls["dry_run"], self.calls["apply_plan"]), ([], 0, []))

    def test_matching_hash_still_runs_the_c10_checks(self):
        write, read = self.bound(self.evidence_hash())
        out, code = self.apply_run(write=write, read=read, clock=lambda: tf.BASIS + timedelta(minutes=50))
        self.assertIn(out["code"], ("backup_evidence_expired", "preflight_approval_expired"))
        self.assertEqual((code, self.driver.calls), (4, []))

    def test_mismatch_imports_no_app_code(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import hashlib, test_ops_resume_binding as t, test_srs_migrate_apply_flow as f, srs_migrate as cli\n"
                "f.FlowBase.setUpClass()\n"
                "case = t.FirstApplyBinding('test_matching_hash_runs_as_before'); case.setUp()\n"
                "import sys as s\n"
                "for m in [m for m in s.modules if m == 'app' or m.startswith('app.')]: del s.modules[m]\n"
                "write, read = case.bound(hashlib.sha256(b'another').hexdigest())\n"
                "out, status = cli.run_apply(case.req, batch_size=2, write_inputs=write, read_inputs=read,"
                " scope=f.SCOPE, driver=f.ta.FakeDriver(), plan_path=case.path('plan.json'), evidence_path=case.ev,"
                " evidence_signature_path=case.ev_sig, clock=lambda: f.T0)\n"
                "app = any(m == 'app' or m.startswith('app.') for m in s.modules)\n"
                "case.doCleanups(); f.FlowBase.tearDownClass()\n"
                "print('RESULT', out['code'], status, app)\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              cwd=str(TESTS_DIR),
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT backup_evidence_binding_mismatch 4 False", done.stdout, done.stderr[-800:])


if __name__ == "__main__":
    unittest.main()
