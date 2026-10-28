"""Signed backup evidence for a migration apply (OPS_MIGRATION_CLI_PLAN 4-4-7 D10 / C10). Synthetic scope.

Input is what the caller fixed: the evidence bytes, its detached signature, the expected target
(DB identity, account, job key, basis time = the basis inquiry's `valid_from`), the synthetic trust
set and the current time (injected). No file is read, no database is opened and nothing from the
app is imported.

What a passed check means, and what it does not:
- the signature shows that a trusted signer stated this content (`attested_by` is a signed display
  string, not the verified signer identity);
- `artifact_sha256` is the stated hash of the backup artifact; the artifact is not read here, so
  `artifact_checked` is always False;
- nothing here shows that the backup can be restored; `restore_verified` must be False.
Refusals carry fixed codes only (no input value, no tool output, no chained exception).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import _ops_approval as oa
import _ops_signature as osig

FORMAT = "jp-vocab-ops/backup-evidence"
FORMAT_VERSION = 1
MAX_EVIDENCE_BYTES = 16 * 1024
FIELDS = frozenset({"format", "format_version", "evidence_id", "purpose", "db_identity", "account_id", "job_key",
                    "backup_id", "taken_at", "method", "artifact_sha256", "valid_until", "attested_by",
                    "restore_verified"})
METHODS = {"synthetic": ("synthetic",)}           # per mode; the operations method is not decided
SUBJECT = "backup"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_APPROVAL_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
_JOB_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_BACKUP_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_INSTANT = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z")
ID_MAX = 2 ** 63 - 1


class OpsBackupEvidenceRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> OpsBackupEvidenceRefused:
    return OpsBackupEvidenceRefused(code)


@dataclass(frozen=True)
class Expected:
    """What the evidence must be about (from the verified apply approval / plan file)."""
    db_identity: str
    account_id: int
    job_key: str
    basis_from: datetime                       # the basis inquiry approval's valid_from


@dataclass(frozen=True)
class BackupEvidence:
    raw: bytes = field(repr=False)             # the fixed bytes everything below came from
    evidence_sha256: str                       # hash of the evidence document itself
    evidence_id: str
    purpose: str
    db_identity: str
    account_id: int
    job_key: str
    backup_id: str
    method: str
    artifact_sha256_claimed: str               # stated, not checked (see artifact_checked)
    attested_by: str                           # signed display text, not the verified signer
    taken_at: datetime
    valid_until: datetime
    restore_verified: bool = False
    artifact_checked: bool = False


def _text(value: Any, pattern: re.Pattern) -> bool:
    return type(value) is str and value.isascii() and pattern.fullmatch(value) is not None


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject(_: str) -> Any:
    raise ValueError


def _instant(value: Any) -> datetime:
    if not _text(value, _INSTANT):
        raise _refuse("backup_evidence_value_invalid")
    try:
        return datetime(*(int(part) for part in _INSTANT.fullmatch(value).groups()), tzinfo=timezone.utc)
    except ValueError:
        raise _refuse("backup_evidence_value_invalid") from None


def _utc(value: Any, code: str) -> datetime:
    """A time-zoned datetime converted to UTC; a naive value or one outside the UTC range is refused
    with `code`. Only the offset / conversion errors are handled here."""
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _refuse(code)
    try:
        if value.utcoffset() is None:
            raise _refuse(code)
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise _refuse(code) from None


def _now(value: Any) -> datetime:
    return _utc(value, "backup_evidence_time_input_invalid")


def _expected(value: Any) -> tuple[str, int, str, datetime]:
    """Every expected value checked before any comparison, conversion or signature check (no 7.0 for 7)."""
    code = "backup_evidence_expected_invalid"
    if not isinstance(value, Expected):
        raise _refuse(code)
    if not (_text(value.db_identity, _HEX64) and type(value.account_id) is int and 0 < value.account_id <= ID_MAX
            and _text(value.job_key, _JOB_KEY)):
        raise _refuse(code)
    return value.db_identity, value.account_id, value.job_key, _utc(value.basis_from, code)


def _parse(data: Any, mode: str) -> dict:
    """Strict format check of the fixed bytes; returns the checked values."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_EVIDENCE_BYTES or data.startswith(b"\xef\xbb\xbf"):
        raise _refuse("backup_evidence_format_invalid")
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_float=_reject,
                         parse_constant=_reject)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _refuse("backup_evidence_format_invalid") from None
    if not isinstance(raw, dict) or any(isinstance(v, (dict, list)) for v in raw.values()):
        raise _refuse("backup_evidence_format_invalid")            # one flat object (depth 1)
    if set(raw) != FIELDS:
        raise _refuse("backup_evidence_fields_invalid")
    if raw["format"] != FORMAT or type(raw["format"]) is not str:
        raise _refuse("backup_evidence_fields_invalid")
    if type(raw["format_version"]) is not int or raw["format_version"] != FORMAT_VERSION:
        raise _refuse("backup_evidence_version_unsupported")
    label = raw["attested_by"]
    if not (_text(raw["evidence_id"], _APPROVAL_ID) and type(raw["purpose"]) is str and raw["purpose"] in oa.MODES
            and _text(raw["db_identity"], _HEX64) and type(raw["account_id"]) is int
            and 0 < raw["account_id"] <= ID_MAX and _text(raw["job_key"], _JOB_KEY)
            and _text(raw["backup_id"], _BACKUP_ID) and type(raw["method"]) is str
            and raw["method"] in METHODS.get(mode, ()) and _text(raw["artifact_sha256"], _HEX64)
            and type(label) is str and label.isascii() and label.isprintable() and 0 < len(label) <= 128
            and type(raw["restore_verified"]) is bool):
        raise _refuse("backup_evidence_value_invalid")
    values = dict(raw)
    values["taken_at"] = _instant(raw["taken_at"])
    values["valid_until"] = _instant(raw["valid_until"])
    if not values["taken_at"] < values["valid_until"]:
        raise _refuse("backup_evidence_value_invalid")
    return values


def _times(taken_at: datetime, valid_until: datetime, now: datetime) -> None:
    """Valid while taken_at <= now < valid_until (valid_until itself is expired)."""
    if taken_at > now:
        raise _refuse("backup_evidence_from_future")
    if not now < valid_until:
        raise _refuse("backup_evidence_expired")


@dataclass(frozen=True)
class BackupEvidenceRecord:
    """A PAST evidence document checked as a record (RESUME_PLAN 9-3): same fields as BackupEvidence, but
    not current (its valid_until may be over), never a write permission and never usable by `recheck`."""
    raw: bytes = field(repr=False)
    evidence_sha256: str
    evidence_id: str
    purpose: str
    db_identity: str
    account_id: int
    job_key: str
    backup_id: str
    method: str
    artifact_sha256_claimed: str
    attested_by: str
    taken_at: datetime
    valid_until: datetime
    restore_verified: bool = False
    artifact_checked: bool = False


def verify_backup_evidence_record(data: bytes, signature: bytes, *, mode: str, expected: Expected,
                                  trust: Any, now: datetime) -> BackupEvidenceRecord:
    """The checks of `verify_backup_evidence` with the signature judged at `now` (current trust and
    revocation), except that `now < valid_until` is not required. `taken_at` must still be within the
    document (before valid_until), not before the basis time and not in the future."""
    values = _checked(data, signature, mode=mode, expected=expected, trust=trust, now=now)
    if values["taken_at"] > _now(now):
        raise _refuse("backup_evidence_from_future")
    return BackupEvidenceRecord(data, hashlib.sha256(data).hexdigest(), values["evidence_id"], values["purpose"],
                                values["db_identity"], values["account_id"], values["job_key"],
                                values["backup_id"], values["method"], values["artifact_sha256"],
                                values["attested_by"], values["taken_at"], values["valid_until"])


def verify_backup_evidence(data: bytes, signature: bytes, *, mode: str, expected: Expected,
                           trust: Any, now: datetime) -> BackupEvidence:
    """Format -> signature (`backup` subject) -> mode -> target / account / job -> restore claim -> time."""
    values = _checked(data, signature, mode=mode, expected=expected, trust=trust, now=now)
    _times(values["taken_at"], values["valid_until"], _now(now))
    return BackupEvidence(data, hashlib.sha256(data).hexdigest(), values["evidence_id"], values["purpose"],
                          values["db_identity"], values["account_id"], values["job_key"], values["backup_id"],
                          values["method"], values["artifact_sha256"], values["attested_by"],
                          values["taken_at"], values["valid_until"])


def _checked(data: bytes, signature: bytes, *, mode: str, expected: Expected, trust: Any, now: datetime) -> dict:
    """Shared order (unchanged): mode -> time input -> expected -> format -> signature -> purpose -> target /
    account / job -> restore claim -> basis time. The validity window is judged by the callers."""
    if mode != "synthetic":
        raise _refuse("mode_not_synthetic")              # no operations verifier exists; refused first
    current = _now(now)
    db_identity, account_id, job_key, basis_from = _expected(expected)
    values = _parse(data, mode)
    if trust is None or not all(hasattr(trust, name) for name in ("allowed_signers", "revoked_keys", "principal")):
        raise _refuse("backup_signature_invalid")
    try:
        verifier = osig.SyntheticOpenSSHVerifier(allowed_signers=trust.allowed_signers,
                                                 revoked_keys=trust.revoked_keys, principal=trust.principal,
                                                 verify_time=current)
        oa.check_signature(data, signature, mode=mode, subject=SUBJECT, verifier=verifier)
    except (oa.OpsApprovalRefused, osig.OpsSignatureRefused):
        raise _refuse("backup_signature_invalid") from None
    if values["purpose"] != mode:
        raise _refuse("backup_evidence_purpose_mismatch")
    if values["db_identity"] != db_identity:
        raise _refuse("backup_evidence_target_mismatch")
    if values["account_id"] != account_id:
        raise _refuse("backup_evidence_account_mismatch")
    if values["job_key"] != job_key:
        raise _refuse("backup_evidence_job_mismatch")
    if values["restore_verified"] is not False:
        raise _refuse("backup_evidence_restore_claim_invalid")   # a signature never proves a restore
    if values["taken_at"] < basis_from:
        raise _refuse("backup_evidence_too_old")
    return values


def recheck(evidence: Any, now: datetime) -> None:
    """Right before the first write connection: the same fixed bytes, the time of THIS call."""
    if not isinstance(evidence, BackupEvidence) or type(evidence.raw) is not bytes \
            or hashlib.sha256(evidence.raw).hexdigest() != evidence.evidence_sha256:
        raise _refuse("backup_evidence_value_invalid")
    current = _now(now)                                # the same time-input check as verify
    values = _parse(evidence.raw, evidence.purpose if evidence.purpose in oa.MODES else "")
    _times(values["taken_at"], values["valid_until"], current)
