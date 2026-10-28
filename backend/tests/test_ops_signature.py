"""Operations tool safety contract unit 4 (scripts/_ops_signature.py): OS OpenSSH detached
signature verification, synthetic scope.

Real signatures: test-only ed25519 keys are created and used to sign inside a temporary folder
this test makes and removes (key generation and signing live here, never in product code).
The user's .ssh, ssh-agent, private keys, secret stores and any production trust root are not
read or changed. Process failures and the timeout are MOCKED and kept in their own class.

Run directly:      python tests/test_ops_signature.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _ops_approval as oa  # noqa: E402
import _ops_manifest as om  # noqa: E402
import _ops_signature as osig  # noqa: E402

SECRET = "Synth3tic-Signature-Secret-5d0e"
T0 = datetime(2026, 10, 21, 12, 30, 0, tzinfo=timezone.utc)
NS = osig.NAMESPACES
PRINCIPAL = "signer@synthetic.test"
WINDOW = 'valid-after="20261021120000Z",valid-before="20261021130000Z"'


def _keygen(*args: str, data: bytes | None = None, cwd: str) -> int:
    run = subprocess.run([osig.SSH_KEYGEN, *args], input=data, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, env=dict(osig.CHILD_ENV), cwd=cwd, timeout=20, shell=False)
    return run.returncode


class Keys:
    """Throwaway synthetic keys in one temporary folder (test only)."""

    def __init__(self):
        self.folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_sig_test_keys_"))
        self.pub = {}
        for name in ("signer", "stranger", "revoked"):
            path = os.path.join(self.folder, name)
            if _keygen("-q", "-t", "ed25519", "-N", "", "-C", f"synthetic-{name}", "-f", path, cwd=self.folder) != 0:
                raise RuntimeError("test key generation failed")
            with open(path + ".pub", "rb") as handle:
                self.pub[name] = handle.read().strip()

    def sign(self, name: str, namespace: str, data: bytes) -> bytes:
        message = os.path.join(self.folder, "message.bin")
        with open(message, "wb") as handle:
            handle.write(data)
        if _keygen("-Y", "sign", "-f", os.path.join(self.folder, name), "-n", namespace, message,
                   cwd=self.folder) != 0:
            raise RuntimeError("test signing failed")
        with open(message + ".sig", "rb") as handle:
            signature = handle.read()
        os.remove(message + ".sig")
        os.remove(message)
        return signature

    def allowed(self, *, namespaces="jp-vocab-ops/v1/synthetic/*,jp-vocab-ops/v1/ops/*", key="signer",
                principal=PRINCIPAL, window=WINDOW) -> bytes:
        options = f'namespaces="{namespaces}"' + (f",{window}" if window else "")
        return f"{principal} {options} ".encode() + self.pub[key] + b"\n"

    def close(self):
        shutil.rmtree(self.folder)


def approval_bytes() -> bytes:
    h = {n: __import__("hashlib").sha256(n.encode()).hexdigest() for n in ("db", "m", "p")}
    doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000001", "supersedes": None,
           "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": h["db"], "manifest": h["m"],
           "tool": "prb_recover", "steps": [{"command": "preview", "access": "read", "role": "ops_read",
                                              "profile": h["p"]}],
           "accounts": [7], "max_accounts": 1, "job": {"key": "prb-1", "inputs": {}},
           "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z", "approved_by": "synthetic"}
    return json.dumps(doc).encode()


def manifest_bytes() -> bytes:
    return json.dumps({"format_version": 1, "kind": "ops_manifest",
                       "files": [{"path": "backend/app/x.py", "size": 0, "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}]}).encode()


def module_temp_dirs() -> set[str]:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "ops_sig_*"))) - \
        set(glob.glob(os.path.join(tempfile.gettempdir(), "ops_sig_test_*")))


class RealBase(unittest.TestCase):
    keys: Keys

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = Keys()

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()

    def setUp(self):
        self.before = module_temp_dirs()
        self.addCleanup(lambda: self.assertEqual(module_temp_dirs() - self.before, set()))

    def verify(self, namespace, message, signature, *, allowed=None, revoked=b"", principal=PRINCIPAL, when=T0):
        osig.verify_detached(namespace=namespace, message=message, signature=signature,
                             allowed_signers=allowed if allowed is not None else self.keys.allowed(),
                             revoked_keys=revoked, principal=principal, verify_time=when)

    def refused(self, code, *args, **kwargs):
        with self.assertRaises(osig.OpsSignatureRefused) as caught:
            self.verify(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(caught.exception.args, (code,))
        return caught.exception


class RealSignatures(RealBase):
    """Real ssh-keygen sign / verify with synthetic keys."""

    def test_valid_synthetic_approval_and_manifest(self):
        for subject, data in (("approval", approval_bytes()), ("manifest", manifest_bytes())):
            with self.subTest(subject=subject):
                ns = NS[("synthetic", subject)]
                self.verify(ns, data, self.keys.sign("signer", ns, data))
        verifier = osig.SyntheticOpenSSHVerifier(allowed_signers=self.keys.allowed(), revoked_keys=b"",
                                                 principal=PRINCIPAL, verify_time=T0)
        data = approval_bytes()
        approval = oa.verify_signed(data, self.keys.sign("signer", NS[("synthetic", "approval")], data),
                                    mode="synthetic", verifier=verifier)
        self.assertEqual(approval.approval_id, "inq-0000000000000001")
        manifest = manifest_bytes()
        fingerprint = om.verify_manifest_signed(manifest, self.keys.sign("signer", NS[("synthetic", "manifest")],
                                                                           manifest), mode="synthetic", verifier=verifier)
        self.assertEqual(fingerprint, om.manifest_fingerprint(manifest))

    def test_tampered_message_damaged_signature_unregistered_key(self):
        ns, data = NS[("synthetic", "approval")], approval_bytes()
        signature = self.keys.sign("signer", ns, data)
        tampered = bytearray(data)
        tampered[10] ^= 0x01
        self.refused("signature_invalid", ns, bytes(tampered), signature)
        lines = signature.splitlines()
        body = bytearray(lines[2])
        body[5] = ord("A") if body[5] != ord("A") else ord("B")
        damaged = b"\n".join(lines[:2] + [bytes(body)] + lines[3:]) + b"\n"
        self.refused("signature_invalid", ns, data, damaged)
        self.refused("signature_invalid", ns, data, b"-----BEGIN SSH SIGNATURE-----\nnot base64\n-----END SSH SIGNATURE-----\n")
        self.refused("signature_invalid", ns, data, self.keys.sign("stranger", ns, data))

    def test_approval_and_manifest_namespaces_do_not_cross(self):
        data = approval_bytes()
        for sign_subject, verify_subject in (("approval", "manifest"), ("manifest", "approval")):
            with self.subTest(signed=sign_subject):
                signature = self.keys.sign("signer", NS[("synthetic", sign_subject)], data)
                self.refused("signature_invalid", NS[("synthetic", verify_subject)], data, signature)

    def test_ops_and_synthetic_namespaces_do_not_cross(self):
        data = manifest_bytes()
        for sign_mode, verify_mode in (("synthetic", "ops"), ("ops", "synthetic")):
            for subject in ("approval", "manifest"):
                with self.subTest(signed=sign_mode, subject=subject):
                    signature = self.keys.sign("signer", NS[(sign_mode, subject)], data)
                    self.refused("signature_invalid", NS[(verify_mode, subject)], data, signature)
        # the cryptographic check alone accepts a test-key ops-namespace signature: that is the
        # namespace separation test, not production mode (see OpsModeStaysClosed)
        signature = self.keys.sign("signer", NS[("ops", "approval")], data)
        self.verify(NS[("ops", "approval")], data, signature)

    def test_principal_and_namespace_restrictions(self):
        ns, data = NS[("synthetic", "manifest")], manifest_bytes()
        signature = self.keys.sign("signer", ns, data)
        self.refused("signature_invalid", ns, data, signature, principal="someone-else@synthetic.test")
        only_approval = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/approval")
        self.refused("signature_invalid", ns, data, signature, allowed=only_approval)
        only_synthetic = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        ops_ns = NS[("ops", "manifest")]
        self.refused("signature_invalid", ops_ns, data, self.keys.sign("signer", ops_ns, data), allowed=only_synthetic)
        self.verify(ns, data, signature, allowed=only_synthetic)

    def test_key_validity_boundaries(self):
        ns, data = NS[("synthetic", "approval")], approval_bytes()
        signature = self.keys.sign("signer", ns, data)
        start = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 10, 21, 13, 0, 0, tzinfo=timezone.utc)
        second = timedelta(seconds=1)
        self.refused("signature_invalid", ns, data, signature, when=start - second)
        self.verify(ns, data, signature, when=start)
        self.verify(ns, data, signature, when=end - second)
        self.verify(ns, data, signature, when=end)
        self.refused("signature_invalid", ns, data, signature, when=end + second)

    def test_revoked_key(self):
        ns, data = NS[("synthetic", "approval")], approval_bytes()
        allowed = self.keys.allowed(key="revoked")
        signature = self.keys.sign("revoked", ns, data)
        self.verify(ns, data, signature, allowed=allowed)
        self.refused("signature_invalid", ns, data, signature, allowed=allowed, revoked=self.keys.pub["revoked"] + b"\n")
        self.verify(ns, data, self.keys.sign("signer", ns, data), revoked=self.keys.pub["revoked"] + b"\n")

    def test_fixed_bytes_are_used_after_files_change(self):
        ns, data = NS[("synthetic", "approval")], approval_bytes()
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_sig_test_inputs_"))
        self.addCleanup(shutil.rmtree, folder)
        paths = {}
        for name, value in (("approval.json", data), ("approval.sig", self.keys.sign("signer", ns, data)),
                            ("allowed", self.keys.allowed())):
            paths[name] = os.path.join(folder, name)
            with open(paths[name], "wb") as handle:
                handle.write(value)
        fixed = {name: Path(path).read_bytes() for name, path in paths.items()}
        for path in paths.values():
            with open(path, "wb") as handle:
                handle.write(b"changed after start " + SECRET.encode())
        self.verify(ns, fixed["approval.json"], fixed["approval.sig"], allowed=fixed["allowed"])


class OpsModeStaysClosed(RealBase):
    def test_production_entry_still_refuses(self):
        called = []
        data = approval_bytes().replace(b'"synthetic"', b'"ops"', 1)
        signature = self.keys.sign("signer", NS[("ops", "approval")], data)
        with self.assertRaises(oa.OpsApprovalRefused) as caught:
            oa.run_authorized(called.append, mode="ops", approval_bytes=data, approval_signature=signature)
        self.assertEqual(caught.exception.code, "signature_verifier_not_implemented")
        self.assertEqual(called, [])

    def test_synthetic_verifier_refuses_ops_namespace_without_running(self):
        verifier = osig.SyntheticOpenSSHVerifier(allowed_signers=self.keys.allowed(), revoked_keys=b"",
                                                 principal=PRINCIPAL, verify_time=T0)
        data = approval_bytes().replace(b'"synthetic"', b'"ops"', 1)
        signature = self.keys.sign("signer", NS[("ops", "approval")], data)
        with mock.patch.object(osig.subprocess, "Popen", side_effect=AssertionError("must not run")):
            with self.assertRaises(osig.OpsSignatureRefused) as caught:
                verifier.verify(namespace=NS[("ops", "approval")], message=data, signature=signature)
            self.assertEqual(caught.exception.code, "signature_scope_not_synthetic")
            with self.assertRaises(oa.OpsApprovalRefused) as caught:
                oa.verify_signed(data, signature, mode="ops", verifier=verifier)
            self.assertEqual(caught.exception.code, "approval_signature_invalid")
            with self.assertRaises(oa.OpsApprovalRefused):
                om.verify_manifest_signed(manifest_bytes(), signature, mode="ops", verifier=verifier)
        self.assertNotIn("allowed", repr(verifier).lower().replace("syntheticopensshverifier", ""))


class FakeProcess:
    def __init__(self, *, returncode=0, raise_on_communicate=None):
        self.returncode = None
        self._final = returncode
        self._raise = raise_on_communicate
        self.killed = False
        self.waited = False
        self.input = None

    def communicate(self, input=None, timeout=None):
        self.input = input
        self.timeout = timeout
        if self._raise is not None:
            raise self._raise
        self.returncode = self._final
        return None, None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        self.returncode = -9
        return self.returncode


class Mocked(unittest.TestCase):
    """MOCKED process outcomes: no real ssh-keygen run here."""

    def setUp(self):
        self.before = module_temp_dirs()
        self.addCleanup(lambda: self.assertEqual(module_temp_dirs() - self.before, set()))
        self.kwargs = dict(namespace=NS[("synthetic", "approval")], message=b"m", signature=b"sig",
                           allowed_signers=b"signer@synthetic.test ssh-ed25519 AAAA\n", revoked_keys=b"",
                           principal=PRINCIPAL, verify_time=T0)

    def run_with(self, process=None, side_effect=None):
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            if side_effect is not None:
                raise side_effect
            return process

        with mock.patch.object(osig.subprocess, "Popen", popen), mock.patch.object(osig, "_check_executable"):
            try:
                osig.verify_detached(**self.kwargs)
                return None, calls
            except osig.OpsSignatureRefused as error:
                self.assertEqual(error.args, (error.code,))
                return error.code, calls

    def test_success_call_shape(self):
        process = FakeProcess(returncode=0)
        code, calls = self.run_with(process)
        self.assertIsNone(code)
        args, kwargs = calls[0]
        self.assertEqual(args[0], osig.SSH_KEYGEN)
        self.assertEqual(args[1:3], ["-Y", "verify"])
        self.assertIn("verify-time=20261021123000Z", args)
        self.assertEqual(args[args.index("-n") + 1], NS[("synthetic", "approval")])
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["env"], osig.CHILD_ENV)
        self.assertEqual((kwargs["stdout"], kwargs["stderr"]), (subprocess.DEVNULL, subprocess.DEVNULL))
        self.assertEqual((process.input, process.timeout), (b"m", 10))

    def test_nonzero_exit(self):
        for returncode in (1, 255, -1, 4294967295):
            with self.subTest(returncode=returncode):
                self.assertEqual(self.run_with(FakeProcess(returncode=returncode))[0], "signature_invalid")

    def test_start_failure(self):
        error = OSError(2, "synthetic start failure " + SECRET)
        self.assertEqual(self.run_with(side_effect=error)[0], "signature_verifier_unavailable")

    def test_timeout_kills_and_reaps_the_child(self):
        process = FakeProcess(raise_on_communicate=subprocess.TimeoutExpired(cmd="x", timeout=10))
        code, _ = self.run_with(process)
        self.assertEqual(code, "signature_verifier_timeout")
        self.assertTrue(process.killed and process.waited)

    def test_cleanup_failure(self):
        created = []
        real_mkdtemp = tempfile.mkdtemp

        def mkdtemp(*args, **kwargs):
            created.append(real_mkdtemp(*args, **kwargs))
            return created[-1]

        def failing_rmtree(path):
            raise OSError(13, "synthetic cleanup failure " + SECRET, path)

        with mock.patch.object(osig.tempfile, "mkdtemp", mkdtemp), \
                mock.patch.object(osig.shutil, "rmtree", failing_rmtree):
            code, _ = self.run_with(FakeProcess(returncode=0))
        for path in created:
            shutil.rmtree(path)  # the test removes what the injected failure left behind
        self.assertEqual(code, "signature_tempfile_cleanup_failed")
        with mock.patch.object(osig.tempfile, "mkdtemp", mkdtemp), \
                mock.patch.object(osig.shutil, "rmtree", failing_rmtree):
            code, _ = self.run_with(FakeProcess(returncode=1))
        for path in created[1:]:
            shutil.rmtree(path)
        self.assertEqual(code, "signature_invalid")  # the verification failure wins over cleanup

    def test_executable_must_be_the_fixed_regular_file(self):
        with mock.patch.object(osig, "SSH_KEYGEN", r"C:\nonexistent\ssh-keygen.exe"), \
                mock.patch.object(osig.subprocess, "Popen", side_effect=AssertionError("must not run")):
            with self.assertRaises(osig.OpsSignatureRefused) as caught:
                osig.verify_detached(**self.kwargs)
        self.assertEqual(caught.exception.code, "signature_verifier_unavailable")

    def test_input_validation(self):
        cases = [("signature_namespace_invalid", dict(namespace="jp-vocab-ops-approval:synthetic")),
                 ("signature_namespace_invalid", dict(namespace=None)),
                 ("signature_input_invalid", dict(message="m")), ("signature_input_invalid", dict(signature=b"")),
                 ("signature_input_invalid", dict(allowed_signers=b"")),
                 ("signature_input_invalid", dict(revoked_keys=None)),
                 ("signature_input_invalid", dict(principal="a b")), ("signature_input_invalid", dict(principal=None)),
                 ("signature_input_invalid", dict(signature=b"x" * (osig.MAX_SMALL + 1))),
                 ("signature_time_invalid", dict(verify_time=T0.replace(tzinfo=None))),
                 ("signature_time_invalid", dict(verify_time="20261021123000Z"))]
        for code, change in cases:
            with self.subTest(code=code, change=sorted(change)):
                with mock.patch.object(osig.subprocess, "Popen", side_effect=AssertionError("must not run")):
                    with self.assertRaises(osig.OpsSignatureRefused) as caught:
                        osig.verify_detached(**{**self.kwargs, **change})
                self.assertEqual(caught.exception.code, code)

    def test_module_never_signs_or_reads_user_material(self):
        source = (SCRIPTS_DIR / "_ops_signature.py").read_text(encoding="utf-8")
        for forbidden in ('"sign"', '"-t"', "ssh-agent", "SSH_AUTH_SOCK", ".ssh", "environ", "getenv",
                          "shell=True", "os.system", "USERPROFILE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.replace("ssh-keygen", "").replace("-Y verify", ""))


class FakeChild:
    """MOCKED child: scripted communicate / kill / wait outcomes. No real process exists."""

    def __init__(self, *, communicate_error=None, kill_error=None, wait_results=()):
        self.returncode = None
        self.communicate_error = communicate_error
        self.kill_error = kill_error
        self.wait_results = list(wait_results)   # each: None (exited) or an exception to raise
        self.kills = 0
        self.wait_timeouts: list[float | None] = []

    def communicate(self, input=None, timeout=None):
        raise self.communicate_error

    def kill(self):
        self.kills += 1
        if self.kill_error is not None:
            raise self.kill_error

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        outcome = self.wait_results.pop(0) if self.wait_results else None
        if outcome is not None:
            raise outcome
        self.returncode = 1
        return 1


class ChildCleanup(unittest.TestCase):
    """MOCKED stop / reap failures after a timeout or a communication error (review fix). These
    are scripted outcomes, not real OS failures; no real child or temporary data is left."""

    TIMEOUT = subprocess.TimeoutExpired(cmd="x", timeout=10)

    def setUp(self):
        self.before = module_temp_dirs()
        self.addCleanup(lambda: self.assertEqual(module_temp_dirs() - self.before, set()))
        self.kwargs = dict(namespace=NS[("synthetic", "approval")], message=SECRET.encode(), signature=b"sig",
                           allowed_signers=b"signer@synthetic.test ssh-ed25519 AAAA\n", revoked_keys=b"",
                           principal=PRINCIPAL, verify_time=T0)

    def oserror(self, what: str) -> OSError:
        return OSError(5, f"synthetic {what} failure {SECRET}", tempfile.gettempdir())

    def run_child(self, child: FakeChild, *, clock=None, rmtree=None):
        patches = [mock.patch.object(osig.subprocess, "Popen", lambda *a, **k: child),
                   mock.patch.object(osig, "_check_executable")]
        if clock is not None:
            patches.append(mock.patch.object(osig.time, "monotonic", clock))
        if rmtree is not None:
            patches.append(mock.patch.object(osig.shutil, "rmtree", rmtree))
        for patch in patches:
            patch.start()
        try:
            with self.assertRaises(osig.OpsSignatureRefused) as caught:
                osig.verify_detached(**self.kwargs)
        finally:
            for patch in reversed(patches):
                patch.stop()
        error = caught.exception
        self.assertEqual(error.args, (error.code,))
        self.assertNotIn(SECRET, repr(error) + str(error))
        self.assertNotIn(tempfile.gettempdir(), repr(error))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error.code

    def test_kill_error_after_timeout_but_exit_confirmed(self):
        child = FakeChild(communicate_error=self.TIMEOUT, kill_error=self.oserror("kill"))
        self.assertEqual(self.run_child(child), "signature_verifier_timeout")
        self.assertEqual((child.kills, len(child.wait_timeouts)), (1, 1))

    def test_kill_error_and_no_exit_is_unconfirmed(self):
        child = FakeChild(communicate_error=self.TIMEOUT, kill_error=self.oserror("kill"),
                          wait_results=[subprocess.TimeoutExpired(cmd="x", timeout=5)])
        self.assertEqual(self.run_child(child), "signature_verifier_child_unconfirmed")

    def test_wait_error_after_timeout(self):
        child = FakeChild(communicate_error=self.TIMEOUT, wait_results=[self.oserror("wait")])
        self.assertEqual(self.run_child(child), "signature_verifier_child_unconfirmed")
        self.assertEqual((child.kills, len(child.wait_timeouts)), (1, 1))  # no retry

    def test_reap_does_not_finish_within_the_budget(self):
        child = FakeChild(communicate_error=self.TIMEOUT, wait_results=[subprocess.TimeoutExpired(cmd="x", timeout=5)])
        self.assertEqual(self.run_child(child), "signature_verifier_child_unconfirmed")
        self.assertEqual(len(child.wait_timeouts), 1)
        self.assertLessEqual(child.wait_timeouts[0], osig.CLEANUP_SECONDS)
        self.assertGreater(child.wait_timeouts[0], 0)

    def test_communication_error_then_stop_errors(self):
        child = FakeChild(communicate_error=self.oserror("pipe"), kill_error=self.oserror("kill"),
                          wait_results=[self.oserror("wait")])
        self.assertEqual(self.run_child(child), "signature_verifier_child_unconfirmed")
        child = FakeChild(communicate_error=self.oserror("pipe"))
        self.assertEqual(self.run_child(child), "signature_verifier_unavailable")

    def test_one_budget_shared_by_kill_and_wait(self):
        ticks = iter([100.0, 104.5, 104.5])  # budget start, after kill, (spare)
        child = FakeChild(communicate_error=self.TIMEOUT)
        self.assertEqual(self.run_child(child, clock=lambda: next(ticks)), "signature_verifier_timeout")
        self.assertAlmostEqual(child.wait_timeouts[0], 0.5)
        ticks = iter([100.0, 107.0, 107.0])  # kill alone used up the budget
        child = FakeChild(communicate_error=self.TIMEOUT, wait_results=[subprocess.TimeoutExpired(cmd="x", timeout=0)])
        self.assertEqual(self.run_child(child, clock=lambda: next(ticks)), "signature_verifier_child_unconfirmed")
        self.assertEqual(child.wait_timeouts, [0])

    def test_priority_with_temporary_data_cleanup(self):
        created = []
        real_mkdtemp = tempfile.mkdtemp

        def mkdtemp(*args, **kwargs):
            created.append(real_mkdtemp(*args, **kwargs))
            return created[-1]

        def failing_rmtree(path):
            raise self.oserror("rmtree")

        with mock.patch.object(osig.tempfile, "mkdtemp", mkdtemp):
            unconfirmed = FakeChild(communicate_error=self.TIMEOUT, wait_results=[self.oserror("wait")])
            self.assertEqual(self.run_child(unconfirmed, rmtree=failing_rmtree), "signature_verifier_child_unconfirmed")
            confirmed = FakeChild(communicate_error=self.TIMEOUT)
            self.assertEqual(self.run_child(confirmed, rmtree=failing_rmtree), "signature_verifier_timeout")
        for path in created:
            shutil.rmtree(path)  # the test removes what the injected failures left behind

    def test_only_its_own_child_handle(self):
        source = (SCRIPTS_DIR / "_ops_signature.py").read_text(encoding="utf-8")
        for forbidden in ("taskkill", "os.kill(", "psutil", "/IM", "pid", "killpg", "CreateToolhelp32Snapshot"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
