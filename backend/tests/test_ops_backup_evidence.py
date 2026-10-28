"""OPS_MIGRATION_CLI_PLAN 4-4-7 D10 / C10: signed backup evidence (synthetic).

REAL detached signatures made by the OS OpenSSH `ssh-keygen` with test-only temporary keys (created
in a temporary folder by `test_ops_signature.Keys` and removed afterwards; no user key, .ssh,
ssh-agent or operations trust root is used). The current time is an argument; nothing waits. No
file is read by the module under test, no database is opened and nothing from the app is imported.

Run directly:      python tests/test_ops_backup_evidence.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import traceback
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import _ops_approval as oa  # noqa: E402
import _ops_backup_evidence as be  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_signature as osig  # noqa: E402
import test_ops_signature as sigtests  # noqa: E402  (module only: its tests are not re-run here)

SECRET = "s3cr3t-Backup-Evidence-7c2e"
BASIS = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 21, 12, 30, 0, tzinfo=timezone.utc)
DB = hashlib.sha256(b"db").hexdigest()


def stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def doc(**changes) -> dict:
    value = {"format": be.FORMAT, "format_version": 1, "evidence_id": "bkp-0000000000000001", "purpose": "synthetic",
             "db_identity": DB, "account_id": 7, "job_key": "mig-2026-10-27-a", "backup_id": "synthetic-backup-1",
             "taken_at": stamp(BASIS + timedelta(minutes=10)), "method": "synthetic",
             "artifact_sha256": hashlib.sha256(b"backup artifact").hexdigest(),
             "valid_until": stamp(BASIS + timedelta(minutes=50)), "attested_by": "synthetic signer",
             "restore_verified": False}
    value.update(changes)
    return value


def encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


class Base(unittest.TestCase):
    keys: sigtests.Keys

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = sigtests.Keys()
        cls.trust = op.SyntheticTrust(cls.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*", window=None), b"",
                                      sigtests.PRINCIPAL)

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()                                         # only the keys this test made

    def expected(self, **changes) -> be.Expected:
        values = dict(db_identity=DB, account_id=7, job_key="mig-2026-10-27-a", basis_from=BASIS)
        values.update(changes)
        return be.Expected(**values)

    def sign(self, data, subject="backup", mode="synthetic", key="signer") -> bytes:
        return self.keys.sign(key, osig.NAMESPACES[(mode, subject)], data)

    def verify(self, data=None, signature=None, *, now=NOW, expected=None, trust=None, mode="synthetic"):
        data = data if data is not None else encode(doc())
        signature = signature if signature is not None else self.sign(data)
        return be.verify_backup_evidence(data, signature, mode=mode, expected=expected or self.expected(),
                                         trust=trust or self.trust, now=now)

    def refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(be.OpsBackupEvidenceRefused) as caught:
            fn(*args, **kwargs)
        error = caught.exception
        self.assertEqual((error.code, error.args), (code, (code,)))
        text = "".join(traceback.format_exception(error))
        self.assertNotIn(SECRET, text)
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Valid(Base):
    def test_valid_evidence_and_what_it_does_not_mean(self):
        data = encode(doc())
        evidence = self.verify(data)
        self.assertIs(evidence.raw, data)
        self.assertEqual(evidence.evidence_sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(evidence.artifact_sha256_claimed, hashlib.sha256(b"backup artifact").hexdigest())
        self.assertNotEqual(evidence.evidence_sha256, evidence.artifact_sha256_claimed)   # two different hashes
        self.assertEqual((evidence.artifact_checked, evidence.restore_verified), (False, False))
        self.assertEqual(evidence.attested_by, "synthetic signer")                       # display text only
        self.assertNotIn("raw", repr(evidence).split("evidence_sha256")[0])

    def test_namespace_is_its_own(self):
        self.assertEqual(oa.signature_namespace("synthetic", "backup"), "jp-vocab-ops/v1/synthetic/backup")
        self.assertEqual(osig.NAMESPACES[("synthetic", "backup")], "jp-vocab-ops/v1/synthetic/backup")


class Signatures(Base):
    def test_tampered_other_key_other_subject_and_mode_are_refused(self):
        data = encode(doc())
        tampered = encode(doc(backup_id="synthetic-backup-2"))
        revoked_trust = op.SyntheticTrust(self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*", window=None,
                                                            key="revoked"), self.keys.pub["revoked"] + b"\n",
                                          sigtests.PRINCIPAL)
        cases = {
            "tampered after signing": dict(data=tampered, signature=self.sign(data)),
            "stranger key": dict(data=data, signature=self.sign(data, key="stranger")),
            "approval subject": dict(data=data, signature=self.sign(data, subject="approval")),
            "manifest subject": dict(data=data, signature=self.sign(data, subject="manifest")),
            "ops namespace": dict(data=data, signature=self.sign(data, mode="ops")),
            "revoked key": dict(data=data, signature=self.sign(data, key="revoked"), trust=revoked_trust),
            "empty signature": dict(data=data, signature=b""),
        }
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                self.refused("backup_signature_invalid", self.verify, **kwargs)
        self.refused("mode_not_synthetic", self.verify, data, self.sign(data), mode="ops")

    def test_existing_approval_and_manifest_signatures_still_work(self):
        approval = sigtests.approval_bytes() if hasattr(sigtests, "approval_bytes") else b"approval bytes"
        verifier = osig.SyntheticOpenSSHVerifier(allowed_signers=self.trust.allowed_signers, revoked_keys=b"",
                                                 principal=sigtests.PRINCIPAL, verify_time=NOW)
        for subject in ("approval", "manifest"):
            with self.subTest(subject=subject):
                oa.check_signature(approval, self.sign(approval, subject=subject), mode="synthetic",
                                   subject=subject, verifier=verifier)
        with self.assertRaises(oa.OpsApprovalRefused):
            oa.check_signature(approval, self.sign(approval, subject="backup"), mode="synthetic", subject="approval",
                               verifier=verifier)
        with self.assertRaises(oa.OpsApprovalRefused) as caught:                       # production stays closed
            oa.check_signature(approval, b"sig", mode="ops", subject="backup", verifier=oa.production_verifier())
        self.assertTrue(caught.exception.code)
        with self.assertRaises(osig.OpsSignatureRefused):
            verifier.verify(namespace=osig.NAMESPACES[("ops", "backup")], message=approval, signature=b"x")


class Targets(Base):
    def test_db_account_job_mismatch(self):
        for changes, code in ((dict(db_identity=hashlib.sha256(b"other").hexdigest()), "backup_evidence_target_mismatch"),
                              (dict(account_id=8), "backup_evidence_account_mismatch"),
                              (dict(job_key="mig-other"), "backup_evidence_job_mismatch")):
            with self.subTest(code=code):
                self.refused(code, self.verify, expected=self.expected(**changes))

    def test_restore_claim_and_purpose(self):
        self.refused("backup_evidence_restore_claim_invalid", self.verify, encode(doc(restore_verified=True)))
        self.refused("backup_evidence_purpose_mismatch", self.verify, encode(doc(purpose="ops")))


class Formats(Base):
    def test_format_errors_are_refused_before_the_signature(self):
        good = encode(doc())
        cases = {
            "duplicate key": (good.replace(b'"account_id":7', b'"account_id":7,"account_id":8', 1), "backup_evidence_format_invalid"),
            "float": (good.replace(b'"account_id":7', b'"account_id":7.0', 1), "backup_evidence_format_invalid"),
            "NaN": (good.replace(b'"account_id":7', b'"account_id":NaN', 1), "backup_evidence_format_invalid"),
            "nested object": (encode(doc(backup_id={"id": SECRET})), "backup_evidence_format_invalid"),
            "nested list": (encode(doc(attested_by=[SECRET])), "backup_evidence_format_invalid"),
            "too large": (b" " * (be.MAX_EVIDENCE_BYTES + 1), "backup_evidence_format_invalid"),
            "empty": (b"", "backup_evidence_format_invalid"),
            "bom": (b"\xef\xbb\xbf" + good, "backup_evidence_format_invalid"),
            "not utf-8": (good.replace(b"synthetic signer", b"synthetic \xff", 1), "backup_evidence_format_invalid"),
            "deep": (b"[" * 5000 + b"]" * 5000, "backup_evidence_format_invalid"),
            "not an object": (b"[1]", "backup_evidence_format_invalid"),
            "missing field": (encode({k: v for k, v in doc().items() if k != "method"}), "backup_evidence_fields_invalid"),
            "extra field": (encode(doc(note=SECRET)), "backup_evidence_fields_invalid"),
            "other format": (encode(doc(format="other")), "backup_evidence_fields_invalid"),
            "version 2": (encode(doc(format_version=2)), "backup_evidence_version_unsupported"),
            "version text": (encode(doc(format_version="1")), "backup_evidence_version_unsupported"),
            "version bool": (encode(doc(format_version=True)), "backup_evidence_version_unsupported"),
        }
        for label, (data, code) in cases.items():
            with self.subTest(case=label):
                self.refused(code, self.verify, data, b"not checked")

    def test_values(self):
        cases = {"account text": dict(account_id="7"), "account bool": dict(account_id=True),
                 "account zero": dict(account_id=0), "db upper": dict(db_identity=DB.upper()),
                 "job key space": dict(job_key="bad key"), "evidence id short": dict(evidence_id="x"),
                 "backup id": dict(backup_id=SECRET + " !"), "method": dict(method="pg_dump"),
                 "artifact": dict(artifact_sha256=SECRET), "attested empty": dict(attested_by=""),
                 "attested control": dict(attested_by="a\nb"), "restore text": dict(restore_verified="false"),
                 "restore null": dict(restore_verified=None), "purpose other": dict(purpose="test"),
                 "taken_at form": dict(taken_at="2026-10-21 12:10:00"), "valid_until form": dict(valid_until="tomorrow"),
                 "impossible date": dict(taken_at="2026-02-30T12:00:00Z"),
                 "valid_until before taken_at": dict(valid_until=stamp(BASIS + timedelta(minutes=5)))}
        for label, changes in cases.items():
            with self.subTest(case=label):
                self.refused("backup_evidence_value_invalid", self.verify, encode(doc(**changes)), b"not checked")


class Times(Base):
    def test_future_old_and_expiry_boundary(self):
        self.refused("backup_evidence_from_future", self.verify,
                     encode(doc(taken_at=stamp(NOW + timedelta(seconds=1)))))
        self.verify(encode(doc(taken_at=stamp(NOW))))                         # taken_at == now is allowed
        self.refused("backup_evidence_too_old", self.verify, encode(doc(taken_at=stamp(BASIS - timedelta(seconds=1)))))
        self.verify(encode(doc(taken_at=stamp(BASIS))))                       # exactly the basis time is allowed
        until = BASIS + timedelta(minutes=50)
        self.verify(now=until - timedelta(seconds=1))
        self.refused("backup_evidence_expired", self.verify, now=until)       # now == valid_until is expired

    def test_valid_at_first_expired_at_recheck(self):
        evidence = self.verify(now=NOW)
        until = BASIS + timedelta(minutes=50)
        be.recheck(evidence, until - timedelta(seconds=1))                    # still valid: the time of THIS call
        self.refused("backup_evidence_expired", be.recheck, evidence, until)
        self.refused("backup_evidence_expired", be.recheck, evidence, until + timedelta(days=1))

    def test_recheck_uses_the_fixed_bytes(self):
        from dataclasses import replace
        evidence = self.verify()
        moved = replace(evidence, valid_until=evidence.valid_until + timedelta(days=30))   # object field changed
        self.refused("backup_evidence_expired", be.recheck, moved, BASIS + timedelta(minutes=50))
        forged = replace(evidence, raw=encode(doc(valid_until=stamp(BASIS + timedelta(days=30)))))
        self.refused("backup_evidence_value_invalid", be.recheck, forged, NOW)
        for bad_now in (datetime(2026, 10, 21, 12, 30), "2026-10-21T12:30:00Z", None):
            with self.subTest(now=repr(bad_now)):
                self.refused("backup_evidence_time_input_invalid", be.recheck, evidence, bad_now)
                self.refused("backup_evidence_time_input_invalid", self.verify, now=bad_now)



FAR_PAST = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1)))       # cannot be converted to UTC


class ExpectedAndTimeInputs(Base):
    """C10 review fix: every expected value and time input is checked before any comparison, conversion
    or signature check; nothing is converted (7.0 is not 7)."""

    def no_signature_check(self, code, **kwargs):
        calls = []
        real = osig.SyntheticOpenSSHVerifier

        def counting(*args, **kw):
            calls.append(1)
            return real(*args, **kw)
        from unittest import mock
        with mock.patch.object(be.osig, "SyntheticOpenSSHVerifier", counting):
            error = self.refused(code, self.verify, **kwargs)
        self.assertEqual(calls, [])
        return error

    def test_expected_values_are_strict(self):
        cases = {"account float": dict(account_id=7.0), "account bool": dict(account_id=True),
                 "account text": dict(account_id="7"), "account zero": dict(account_id=0),
                 "account negative": dict(account_id=-7), "account too big": dict(account_id=2 ** 63),
                 "db upper": dict(db_identity=DB.upper()), "db short": dict(db_identity=DB[:-1]),
                 "db bytes": dict(db_identity=DB.encode()), "db secret": dict(db_identity=SECRET),
                 "job space": dict(job_key="bad key"), "job long": dict(job_key="k" * 129),
                 "job none": dict(job_key=None), "basis naive": dict(basis_from=datetime(2026, 10, 21, 12, 0)),
                 "basis text": dict(basis_from="2026-10-21T12:00:00Z"), "basis far past": dict(basis_from=FAR_PAST)}
        for label, changes in cases.items():
            with self.subTest(case=label):
                self.no_signature_check("backup_evidence_expected_invalid", expected=self.expected(**changes))
        with self.subTest(case="not an Expected"):
            self.no_signature_check("backup_evidence_expected_invalid", expected=object())

    def test_now_out_of_range_and_naive(self):
        for now in (FAR_PAST, datetime(2026, 10, 21, 12, 30), "2026-10-21T12:30:00Z"):
            with self.subTest(now=repr(now)[:40]):
                self.no_signature_check("backup_evidence_time_input_invalid", now=now)
        evidence = self.verify()
        for now in (FAR_PAST, datetime(2026, 10, 21, 12, 30)):
            with self.subTest(recheck=repr(now)[:40]):
                self.refused("backup_evidence_time_input_invalid", be.recheck, evidence, now)

    def test_valid_non_utc_times_are_converted_not_refused(self):
        seoul = timezone(timedelta(hours=9))
        evidence = self.verify(now=NOW.astimezone(seoul), expected=self.expected(basis_from=BASIS.astimezone(seoul)))
        until = BASIS + timedelta(minutes=50)
        be.recheck(evidence, (until - timedelta(seconds=1)).astimezone(seoul))
        self.refused("backup_evidence_expired", be.recheck, evidence, until.astimezone(seoul))

class Boundaries(unittest.TestCase):
    def test_module_imports_no_app_and_opens_nothing(self):
        code = (f"import sys; sys.path[:0] = [{str(BACKEND / 'scripts')!r}]\n"
                "import builtins, psycopg\n"
                "psycopg.connect = lambda *a, **k: (_ for _ in ()).throw(AssertionError('connect'))\n"
                "import _ops_backup_evidence\n"
                "print('APP', any(m == 'app' or m.startswith('app.') for m in sys.modules))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("APP False", done.stdout, done.stderr[-500:])
        source = (BACKEND / "scripts" / "_ops_backup_evidence.py").read_text(encoding="utf-8")
        for text in ("open(", "psycopg", "sqlite3", "from app", "import app", "os.environ"):
            self.assertNotIn(text, source)


if __name__ == "__main__":
    unittest.main()
