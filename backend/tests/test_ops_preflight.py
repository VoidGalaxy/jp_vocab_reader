"""Operations tool safety contract unit 5 (scripts/_ops_preflight.py): synthetic integrated
pre-check over units 1-4.

Real signatures with test-only keys (reusing the unit 4 test key helper) on a synthetic
deployment folder this test creates and removes; connection strings are synthetic and never
connected (every psycopg / libpq connect entry point is patched to fail). Call-order checks
are MOCKED wrappers around the real functions and are kept in their own class.

Run directly:      python tests/test_ops_preflight.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock
from urllib.parse import quote

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TESTS_DIR.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402  (parser only; connect entry points are patched below)
import psycopg.generators  # noqa: E402

import _ops_approval as oa  # noqa: E402
import _ops_manifest as om  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_target as ot  # noqa: E402
import test_ops_signature as sigtests  # noqa: E402  (module only: its test classes are not re-run here)

SECRET = "Synth3tic-Preflight-Secret-8b21"
T0 = sigtests.T0
READ_PROFILE = hashlib.sha256(b"read profile").hexdigest()
WRITE_PROFILE = hashlib.sha256(b"write profile").hexdigest()
PRODUCT = hashlib.sha256(b"product plan").hexdigest()
TARGET = op.TargetObservation(host="db.synthetic.test", port=5432, database="jp_vocab", server_major=18,
                              identity_value="synthetic-identity-row")
FILES = {"backend/scripts/_ops_tool.py": b"print('never executed')\n",
         "docs/plans/srs-improvement/gate-e/OPS_TOOL_SAFETY_CONTRACT.md": b"# synthetic contract\n",
         "ops/tls/root.pem": b"-----BEGIN CERTIFICATE-----\nsynthetic\n"}
JOB = {"key": "prb-synthetic-1", "inputs": {"release_reason": "completed"}}


def db_identity(target=TARGET, alias="synthetic-primary") -> str:
    return oa.db_identity_fingerprint(alias=alias, host=target.host, port=target.port, database=target.database,
                                      server_major=target.server_major, identity_value=target.identity_value)


def manifest_doc(files: dict) -> bytes:
    return json.dumps({"format_version": 1, "kind": "ops_manifest", "files": [
        {"path": p, "size": len(d), "sha256": hashlib.sha256(d).hexdigest()} for p, d in files.items()]}).encode()


class Base(unittest.TestCase):
    keys: sigtests.Keys

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(op.osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = sigtests.Keys()
        cls.allowed = cls.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()

    def setUp(self):
        def forbidden(*_, **__):
            raise AssertionError("a connection function was called")

        for patch in (mock.patch.object(psycopg, "connect", forbidden),
                      mock.patch.object(psycopg.Connection, "connect", forbidden),
                      mock.patch.object(psycopg.pq, "PGconn", type("NoPGconn", (), {
                          "connect": staticmethod(forbidden), "connect_start": staticmethod(forbidden)})),
                      mock.patch.object(psycopg.generators, "connect", forbidden)):
            patch.start()
            self.addCleanup(patch.stop)
        self.root = os.path.normpath(tempfile.mkdtemp(prefix="ops_preflight_test_"))
        self.addCleanup(shutil.rmtree, self.root)
        self.write_files(FILES)
        self.manifest = manifest_doc(FILES)
        self.before_modules = set(sys.modules)

    def tearDown(self):
        self.assertNotIn("_ops_tool", set(sys.modules) - self.before_modules)

    def write_files(self, files: dict) -> None:
        for rel, data in files.items():
            path = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)

    def sign(self, data: bytes, subject: str, mode: str = "synthetic") -> bytes:
        return self.keys.sign("signer", oa.signature_namespace(mode, subject), data)

    def root_pem(self) -> str:
        return os.path.join(self.root, "ops", "tls", "root.pem")

    def dsn(self, role="ops_read", host="db.synthetic.test", root=None, sslmode="verify-full") -> str:
        cert = quote(root if root is not None else self.root_pem(), safe="")
        return f"postgresql://{role}:{SECRET}@{host}:5432/jp_vocab?sslmode={sslmode}&sslrootcert={cert}"

    def inquiry(self, **changes) -> bytes:
        doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000001", "supersedes": None,
               "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": db_identity(),
               "manifest": om.manifest_fingerprint(self.manifest), "tool": "prb_recover",
               "steps": [{"command": "preview", "access": "read", "role": "ops_read", "profile": READ_PROFILE},
                         {"command": "status", "access": "read", "role": "ops_read", "profile": READ_PROFILE}],
               "accounts": [7], "max_accounts": 1, "job": json.loads(json.dumps(JOB)),
               "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
               "approved_by": "synthetic signer"}
        doc.update(changes)
        return json.dumps(doc).encode()

    def apply(self, inquiry: bytes, plan: str, **changes) -> bytes:
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001",
                   steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": READ_PROFILE},
                          {"command": "prepare", "access": "write", "role": "ops_write_prb", "profile": WRITE_PROFILE}],
                   based_on={"approval_id": doc["approval_id"], "sha256": hashlib.sha256(inquiry).hexdigest()},
                   plan={"7": plan})
        doc.update(changes)
        return json.dumps(doc).encode()

    def inputs(self, approval: bytes | None = None, **changes) -> op.PreflightInput:
        approval = approval if approval is not None else self.inquiry()
        values = dict(mode="synthetic", approval=approval, approval_signature=self.sign(approval, "approval"),
                      manifest=self.manifest, manifest_signature=self.sign(self.manifest, "manifest"),
                      deploy_root=self.root, command="preview", args={}, account_id=7, job_key=JOB["key"],
                      job_inputs=JOB["inputs"], product_fingerprint=PRODUCT, target=TARGET,
                      connection=op.ConnectionObservation(profile=READ_PROFILE, read_only=True),
                      secret_dsn=self.dsn(), environment={"PATH": "C:/Windows"},
                      trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=T0)
        values.update(changes)
        return op.PreflightInput(**values)

    def refused(self, stage: str, code: str, inputs: op.PreflightInput):
        with self.assertRaises(op.OpsPreflightRefused) as caught:
            op.run_synthetic_preflight(inputs)
        error = caught.exception
        self.assertEqual((error.stage, error.code), (stage, code))
        self.assertNotIn(SECRET, repr(error) + str(error))
        self.assertNotIn(self.root, repr(error) + str(error))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error

    def preview_plan(self) -> str:
        return op.run_synthetic_preflight(self.inputs()).job_plan


class RealFlow(Base):
    """Real signatures, real synthetic files, synthetic connection strings (never connected)."""

    def test_first_preview_with_inquiry_approval(self):
        result = op.run_synthetic_preflight(self.inputs())
        self.assertEqual((result.kind, result.command, result.access, result.file_count), ("inquiry", "preview", "read", 3))
        self.assertIs(result.connection_allowed, False)
        self.assertEqual(result.db_identity, db_identity())
        self.assertEqual(result.sslrootcert, self.root_pem())
        self.assertEqual(result.job_plan, oa.job_plan_fingerprint(
            db_identity=db_identity(), manifest=om.manifest_fingerprint(self.manifest), tool="prb_recover",
            account_id=7, job_key=JOB["key"], job_inputs=JOB["inputs"], product_fingerprint=PRODUCT))
        self.assertNotIn(SECRET, repr(result) + repr(self.inputs()))

    def test_inquiry_then_apply_write_step(self):
        plan = self.preview_plan()
        inquiry = self.inquiry()
        apply = self.apply(inquiry, plan)
        result = op.run_synthetic_preflight(self.inputs(
            apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"), command="prepare",
            secret_dsn=self.dsn(role="ops_write_prb"),
            connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=False)))
        self.assertEqual((result.kind, result.access, result.role, result.job_plan), ("apply", "write", "ops_write_prb", plan))
        self.refused("approval", "apply_based_on_missing", self.inputs(apply, command="prepare"))
        self.refused("approval", "approval_signature_invalid", self.inputs(
            apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "manifest"), command="prepare",
            secret_dsn=self.dsn(role="ops_write_prb"),
            connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=False)))

    def test_signed_but_different_manifest(self):
        other = manifest_doc({**FILES, "backend/app/extra.py": b""})
        self.refused("manifest", "manifest_not_approved",
                     self.inputs(manifest=other, manifest_signature=self.sign(other, "manifest")))

    def test_signed_but_different_target_account_job_role_plan(self):
        self.refused("target", "db_identity_not_approved", self.inputs(target=replace(TARGET, host="db2.synthetic.test")))
        self.refused("target", "db_identity_not_approved", self.inputs(target=replace(TARGET, server_major=17)))
        self.refused("target", "db_identity_not_approved",
                     self.inputs(target=replace(TARGET, identity_value="restored-copy")))
        self.refused("command", "account_not_approved", self.inputs(account_id=9))
        self.refused("command", "job_input_mismatch", self.inputs(job_key="prb-other"))
        self.refused("command", "job_input_mismatch", self.inputs(job_inputs={"release_reason": "other"}))
        self.refused("connection", "role_mismatch", self.inputs(secret_dsn=self.dsn(role="ops_write_prb")))
        self.refused("command", "command_not_approved", self.inputs(command="prepare"))
        self.refused("command", "connection_profile_mismatch",
                     self.inputs(connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=True)))
        self.refused("command", "read_step_not_read_only",
                     self.inputs(connection=op.ConnectionObservation(profile=READ_PROFILE, read_only=False)))
        plan = self.preview_plan()
        inquiry = self.inquiry()
        apply = self.apply(inquiry, plan)
        self.refused("command", "job_plan_mismatch", self.inputs(
            apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"), command="prepare",
            product_fingerprint=hashlib.sha256(b"other").hexdigest(), secret_dsn=self.dsn(role="ops_write_prb"),
            connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=False)))

    def test_signature_purpose_and_mode_crossing(self):
        approval = self.inquiry()
        self.refused("approval", "approval_signature_invalid",
                     self.inputs(approval, approval_signature=self.sign(approval, "manifest")))
        self.refused("manifest", "manifest_signature_invalid",
                     self.inputs(manifest_signature=self.sign(self.manifest, "approval")))
        ops_approval = self.inquiry(purpose="ops")
        self.refused("approval", "approval_purpose_mismatch",
                     self.inputs(ops_approval, approval_signature=self.sign(ops_approval, "approval", "ops")))
        ops_inputs = self.inputs(mode="ops")
        with mock.patch.object(op.osig.subprocess, "Popen", side_effect=AssertionError("must not run")):
            self.refused("mode", "mode_not_synthetic", ops_inputs)

    def test_file_tamper_and_certificate_binding(self):
        self.write_files({"backend/scripts/_ops_tool.py": b"print('tampered')\n"})
        self.refused("files", "manifest_size_mismatch", self.inputs())
        self.write_files(FILES)
        self.write_files({"ops/tls/root.pem": b"-----BEGIN CERTIFICATE-----\nsynthetiC\n"})
        self.refused("files", "manifest_hash_mismatch", self.inputs())
        self.write_files(FILES)
        self.refused("connection", "tls_root_mismatch",
                     self.inputs(secret_dsn=self.dsn(root=os.path.join(self.root, "ops", "tls", "other.pem"))))
        two = manifest_doc({**FILES, "ops/tls/second.pem": b"x"})
        self.write_files({"ops/tls/second.pem": b"x"})
        approval = self.inquiry(manifest=om.manifest_fingerprint(two))
        self.refused("tls", "tls_root_not_bound", self.inputs(
            approval, manifest=two, manifest_signature=self.sign(two, "manifest")))
        none = manifest_doc({k: v for k, v in FILES.items() if not k.startswith("ops/")})
        approval = self.inquiry(manifest=om.manifest_fingerprint(none))
        self.refused("tls", "tls_root_not_bound", self.inputs(
            approval, manifest=none, manifest_signature=self.sign(none, "manifest")))

    def test_connection_string_target_tls_and_environment(self):
        self.refused("connection", "target_mismatch", self.inputs(secret_dsn=self.dsn(host="db2.synthetic.test")))
        self.refused("connection", "tls_mode_mismatch", self.inputs(secret_dsn=self.dsn(sslmode="require")))
        self.refused("connection", "libpq_environment_present", self.inputs(environment={"PGHOST": "elsewhere"}))
        self.refused("connection", "libpq_environment_present", self.inputs(environment={"PGPASSWORD": SECRET}))

    def test_supersedes_without_run_record_is_refused(self):
        # moved to the version 2 link form (contract 4-6-5); the version 1 form is refused earlier
        prior = self.inquiry()
        approval = self.inquiry(approval_id="inq-0000000000000002", format_version=2, supersedes={
            "approval_id": "inq-0000000000000001", "sha256": hashlib.sha256(prior).hexdigest()})
        self.refused("command", "approval_supersedes_unknown", self.inputs(approval))
        old_form = self.inquiry(approval_id="inq-0000000000000002", supersedes="inq-0000000000000001")
        self.refused("approval", "approval_supersedes_resign_required", self.inputs(old_form))
        self.assertEqual(op.run_synthetic_preflight(self.inputs(self.inquiry(format_version=2))).job_plan,
                         self.preview_plan())


class CallOrder(Base):
    """MOCKED wrappers (they still call the real functions) to show later steps never run."""

    def spies(self):
        names = {"parse": (om, "parse_manifest"), "files": (om, "check_manifest_files"),
                 "preconnect": (ot, "check_preconnect"), "authorize": (oa, "authorize_command"),
                 "manifest_sig": (om, "verify_manifest_signed")}
        spies = {}
        for key, (module, attr) in names.items():
            spy = mock.Mock(wraps=getattr(module, attr))
            patch = mock.patch.object(module, attr, spy)
            patch.start()
            self.addCleanup(patch.stop)
            spies[key] = spy
        return spies

    def test_bad_approval_signature_stops_everything(self):
        spies = self.spies()
        approval = self.inquiry()
        self.refused("approval", "approval_signature_invalid", self.inputs(approval, approval_signature=b"bad"))
        self.assertEqual({k: s.call_count for k, s in spies.items()}, dict.fromkeys(spies, 0))

    def test_unapproved_manifest_stops_before_its_signature_and_files(self):
        spies = self.spies()
        other = manifest_doc({**FILES, "backend/app/extra.py": b""})
        self.refused("manifest", "manifest_not_approved",
                     self.inputs(manifest=other, manifest_signature=self.sign(other, "manifest")))
        self.assertEqual({k: s.call_count for k, s in spies.items()}, dict.fromkeys(spies, 0))

    def test_connection_refusal_stops_before_judgement_and_files(self):
        spies = self.spies()
        self.refused("connection", "target_mismatch", self.inputs(secret_dsn=self.dsn(host="db2.synthetic.test")))
        self.assertEqual((spies["authorize"].call_count, spies["files"].call_count), (0, 0))
        self.assertEqual(spies["preconnect"].call_count, 1)

    def test_files_are_read_last(self):
        spies = self.spies()
        order = []
        for key, spy in spies.items():
            spy.side_effect = (lambda key, real: (lambda *a, **k: (order.append(key), real(*a, **k))[1]))(key, spy._mock_wraps)
        op.run_synthetic_preflight(self.inputs())
        first_file_read = order.index("files")
        self.assertTrue(all(step == "parse" for step in order[first_file_read + 1:]))  # its own internal parse
        self.assertLess(order.index("preconnect"), order.index("authorize"))
        self.assertLess(order.index("authorize"), first_file_read)

    def test_module_never_connects_imports_or_runs_files(self):
        source = (SCRIPTS_DIR / "_ops_preflight.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\bconnect\(", source))  # check_preconnect( only parses
        for forbidden in ("psycopg", "import_module", "__import__", "exec(", "eval(", "runpy",
                          "subprocess", "from app", "import app", "os.environ", "getenv", "skip"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)



ARTIFACT = hashlib.sha256(b"plan file").hexdigest()


class ArtifactPreflight(Base):
    """Contract 3-3-1 in the real signed pre-check (synthetic keys, no connection)."""

    def test_default_is_none_and_keeps_the_plan(self):
        self.assertIsNone(self.inputs().artifact_sha256)
        self.assertEqual(self.preview_plan(), op.run_synthetic_preflight(self.inputs(artifact_sha256=None)).job_plan)

    def test_inquiry_prints_and_apply_checks_the_bound_plan(self):
        inquiry = self.inquiry()
        printed = op.run_synthetic_preflight(self.inputs(inquiry, artifact_sha256=ARTIFACT)).job_plan
        self.assertNotEqual(printed, self.preview_plan())
        apply = self.apply(inquiry, printed)
        values = dict(inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"), command="prepare",
                      secret_dsn=self.dsn(role="ops_write_prb"),
                      connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=False))
        self.assertEqual(op.run_synthetic_preflight(self.inputs(apply, artifact_sha256=ARTIFACT, **values)).job_plan,
                         printed)
        self.refused("command", "job_plan_mismatch", self.inputs(apply, **values))
        self.refused("command", "job_plan_mismatch",
                     self.inputs(apply, artifact_sha256=hashlib.sha256(b"other").hexdigest(), **values))
        self.refused("command", "artifact_sha256_invalid", self.inputs(apply, artifact_sha256=ARTIFACT.upper(),
                                                                       **values))
        self.refused("command", "artifact_sha256_invalid", self.inputs(apply, artifact_sha256=True, **values))

    def test_signature_checks_still_come_first(self):
        self.refused("approval", "approval_signature_invalid",
                     self.inputs(approval_signature=b"bad", artifact_sha256=ARTIFACT))


PAST = {"valid_from": "2026-10-21T08:00:00Z", "valid_until": "2026-10-21T09:00:00Z"}   # before T0


class ApplyChain(Base):
    """Contract 4-6-6 in the real signed pre-check (test-only keys, no connection)."""

    def setUp(self):
        super().setUp()
        self.inq = self.inquiry()
        self.plan = self.preview_plan()

    def doc(self, approval_id, supersedes=None, version=2, inquiry=None, plan=None, **changes) -> bytes:
        doc = json.loads(self.apply(inquiry or self.inq, plan or self.plan, approval_id=approval_id,
                                    format_version=version, supersedes=supersedes))
        doc.update(changes)
        return json.dumps(doc).encode()

    def link(self, data, inquiry=None, **bad) -> op.ChainLink:
        inquiry = inquiry or self.inq
        values = dict(approval=data, approval_signature=self.sign(data, "approval"), inquiry=inquiry,
                      inquiry_signature=self.sign(inquiry, "approval"))
        values.update(bad)
        return op.ChainLink(**values)

    def ref(self, data) -> dict:
        return {"approval_id": json.loads(data)["approval_id"], "sha256": hashlib.sha256(data).hexdigest()}

    def run_inputs(self, current, chain, **changes):
        values = dict(inquiry=self.inq, inquiry_signature=self.sign(self.inq, "approval"), command="prepare",
                      secret_dsn=self.dsn(role="ops_write_prb"), prior_chain=tuple(chain),
                      connection=op.ConnectionObservation(profile=WRITE_PROFILE, read_only=False))
        values.update(changes)
        return self.inputs(current, **values)

    def steps3(self):
        a1 = self.doc("app-0000000000000001", version=1, **PAST)
        a2 = self.doc("app-0000000000000002", supersedes=self.ref(a1), **PAST)
        a3 = self.doc("app-0000000000000003", supersedes=self.ref(a2), **PAST)
        return a1, a2, a3

    def test_single_link_version_1_first_and_expired_past(self):
        first = self.doc("app-0000000000000001", version=1, **PAST)
        current = self.doc("app-0000000000000002", supersedes=self.ref(first))
        result = op.run_synthetic_preflight(self.run_inputs(current, [self.link(first)]))
        self.assertEqual((result.kind, result.command, result.job_plan), ("apply", "prepare", self.plan))
        self.assertEqual(result.verified.prior.approval_id, "app-0000000000000001")
        self.assertTrue(result.verified.prior.verified)
        self.assertNotIn("verified", repr(result))

    def test_multi_link_with_an_expired_basis(self):
        old_inq = self.inquiry(approval_id="inq-0000000000000009", **PAST)
        a1 = self.doc("app-0000000000000001", version=1, inquiry=old_inq, **PAST)
        a2 = self.doc("app-0000000000000002", supersedes=self.ref(a1), **PAST)
        a3 = self.doc("app-0000000000000003", supersedes=self.ref(a2), **PAST)
        current = self.doc("app-0000000000000004", supersedes=self.ref(a3))
        chain = [self.link(a1, old_inq), self.link(a2), self.link(a3)]
        result = op.run_synthetic_preflight(self.run_inputs(current, chain))
        self.assertEqual(result.verified.prior.approval_id, "app-0000000000000003")

    def test_current_approval_must_be_valid_now(self):
        first = self.doc("app-0000000000000001", version=1, **PAST)
        current = self.doc("app-0000000000000002", supersedes=self.ref(first), **PAST)
        self.refused("command", "approval_expired", self.run_inputs(current, [self.link(first)]))

    def test_broken_chains(self):
        a1, a2, a3 = self.steps3()
        current = self.doc("app-0000000000000004", supersedes=self.ref(a3))
        other_inq = self.inquiry(approval_id="inq-0000000000000008")
        cases = {
            "bad approval signature": ([self.link(a1, approval_signature=b"bad"), self.link(a2), self.link(a3)],
                                       "approval_signature_invalid"),
            "bad basis signature": ([self.link(a1, inquiry_signature=b"bad"), self.link(a2), self.link(a3)],
                                    "approval_signature_invalid"),
            "wrong basis": ([self.link(a1, other_inq), self.link(a2), self.link(a3)], "apply_based_on_mismatch"),
            "order": ([self.link(a2), self.link(a1), self.link(a3)], "approval_chain_first_linked"),
            "missing middle": ([self.link(a1), self.link(a3)], "approval_supersedes_mismatch"),
            "missing last": ([self.link(a1), self.link(a2)], "approval_supersedes_mismatch"),
            "duplicate": ([self.link(a1), self.link(a1), self.link(a2), self.link(a3)], "approval_chain_duplicate"),
            "current in chain": ([self.link(a1), self.link(a2), self.link(a3), self.link(current)],
                                 "approval_chain_duplicate"),
            "inquiry as apply": ([self.link(self.inq), self.link(a2), self.link(a3)],
                                 "approval_supersedes_kind_mismatch"),
        }
        for label, (chain, code) in cases.items():
            with self.subTest(case=label):
                self.refused("approval", code, self.run_inputs(current, chain))
        wrong_hash = self.doc("app-0000000000000005", supersedes={**self.ref(a3), "sha256": "0" * 64})
        self.refused("approval", "approval_supersedes_mismatch",
                     self.run_inputs(wrong_hash, [self.link(a1), self.link(a2), self.link(a3)]))
        unlinked = self.doc("app-0000000000000006")
        self.refused("approval", "approval_supersedes_mismatch", self.run_inputs(unlinked, [self.link(a1)]))
        self.refused("command", "approval_supersedes_unknown", self.run_inputs(current, []))

    def test_limits_and_shapes_before_any_signature(self):
        a1 = self.doc("app-0000000000000001", version=1, **PAST)
        current = self.doc("app-0000000000000002", supersedes=self.ref(a1))
        dummy = op.ChainLink(b"x", b"x", b"x", b"x")
        huge = op.ChainLink(b"x" * (op.oa.MAX_CHAIN_BYTES + 1), b"x", b"x", b"x")
        with mock.patch.object(op.osig, "SyntheticOpenSSHVerifier", side_effect=AssertionError("verifier used")):
            self.refused("approval", "approval_chain_too_long",
                         self.run_inputs(current, [dummy] * (op.oa.MAX_CHAIN_LINKS + 1)))
            self.refused("approval", "approval_chain_too_large", self.run_inputs(current, [huge]))
            for bad in ([self.link(a1)], (self.link(a1).approval,), (op.ChainLink("x", b"x", b"x", b"x"),)):
                with self.subTest(bad=type(bad).__name__):
                    self.refused("approval", "approval_chain_invalid", self.run_inputs(current, (), prior_chain=bad))

    def test_purpose_job_and_kind(self):
        a1 = self.doc("app-0000000000000001", version=1, **PAST)
        ops_first = self.doc("app-0000000000000001", version=1, purpose="ops", **PAST)
        current = self.doc("app-0000000000000002", supersedes=self.ref(ops_first))
        self.refused("approval", "approval_purpose_mismatch", self.run_inputs(current, [self.link(ops_first)]))
        other_inq = self.inquiry(approval_id="inq-0000000000000007", job={"key": "prb-other", "inputs": JOB["inputs"]})
        other = self.doc("app-0000000000000001", version=1, inquiry=other_inq, **PAST)
        current = self.doc("app-0000000000000002", supersedes=self.ref(other))
        self.refused("approval", "approval_job_mismatch", self.run_inputs(current, [self.link(other, other_inq)]))
        current = self.doc("app-0000000000000002", supersedes=self.ref(a1))
        inquiry_now = self.inquiry(approval_id="inq-0000000000000003")
        self.refused("approval", "approval_chain_kind_unsupported",
                     self.inputs(inquiry_now, prior_chain=(self.link(a1),)))

    def test_permissions_are_not_merged(self):
        a1 = self.doc("app-0000000000000001", version=1, **PAST)       # has status and prepare
        narrow = self.doc("app-0000000000000002", supersedes=self.ref(a1),
                          steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": READ_PROFILE}])
        self.refused("command", "command_not_approved", self.run_inputs(narrow, [self.link(a1)]))

    def test_plan_and_artifact_stay_bound_to_the_current_approval(self):
        artifact = hashlib.sha256(b"plan file").hexdigest()
        printed = op.run_synthetic_preflight(self.inputs(self.inq, artifact_sha256=artifact)).job_plan
        a1 = self.doc("app-0000000000000001", version=1, **PAST)       # its plan has no artifact
        current = self.doc("app-0000000000000002", supersedes=self.ref(a1), plan=printed)
        result = op.run_synthetic_preflight(self.run_inputs(current, [self.link(a1)], artifact_sha256=artifact))
        self.assertEqual(result.job_plan, printed)
        self.refused("command", "job_plan_mismatch", self.run_inputs(current, [self.link(a1)]))

if __name__ == "__main__":
    unittest.main()
