"""Operations tool safety contract, unit 1: approval / fingerprint / command judgement
(docs/plans/srs-improvement/gate-e/OPS_TOOL_SAFETY_CONTRACT.md 3·4절).

Pure logic only. Every input (the clock instant, approval bytes and signatures, the manifest
fingerprint, the observed connection values) is an argument. Nothing here reads a database,
the environment, the clock, a file or the network, and nothing imports the app. The observed
role / profile values are whatever the caller passes in: this module never queries a role or
a privilege and cannot tell whether they are real.

Signatures: the signing tool is not decided (contract 12-2). `SignatureVerifier` is only the
interface. There is no default verifier, no skip flag and no success path without one:
`production_verifier()` refuses, so `run_authorized` refuses before calling the action
(connection or business work). A fake verifier is injected by the tests only.

Every refusal is `OpsApprovalRefused(code)` with a fixed code; no value from the input
(approval text, host, role, token, connection data) is carried in it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol

FORMAT_VERSIONS = (1, 2, 3)  # contract 4-6-5: 2 binds `supersedes` to the prior approval's bytes;
                             # 3 = 2 + the optional `backup_evidence` of an apply approval (RESUME_PLAN 9-3)
MAX_APPROVAL_BYTES = 65536
MAX_CHAIN_LINKS = 8              # contract 4-6-6: prior apply approvals given with one command
MAX_CHAIN_BYTES = 1024 * 1024   # contract 4-6-6: all chain bytes (approvals, bases, signatures)
MAX_VALIDITY = timedelta(hours=24)  # contract 4-1 (user direction)
MODES = ("ops", "synthetic")
KINDS = ("inquiry", "apply")
ACCESS = ("read", "write")
ID_MAX = 2 ** 63 - 1

# The existing operator CLIs (contract 10) and whether each command only reads.
TOOLS: dict[str, dict[str, str]] = {
    "prb_recover": {"preview": "read", "status": "read", "prepare": "write", "recover": "write",
                    "verify": "write", "release": "write"},
    "srs_invariant_audit": {"audit": "read"},
    "d2_receipt_minimize": {"dry_run": "read", "apply": "write"},
    "d2_snapshot_minimize": {"dry_run": "read", "apply": "write"},
    "d2_snapshot_prune": {"dry_run": "read", "apply": "write"},
    "delete_account": {"preview": "read", "apply": "write"},
    "srs_migrate": {"dry_run": "read", "status": "read", "apply": "write",   # OPS_MIGRATION_CLI_PLAN 1-1/4-3/4-4-8
                    "resume": "write"},                                      # OPS_MIGRATION_RESUME_PLAN 9-4
}

_COMMON = {"format_version", "kind", "approval_id", "supersedes", "purpose", "alias", "db_identity",
           "manifest", "tool", "steps", "accounts", "max_accounts", "job", "valid_from", "valid_until",
           "approved_by"}
FIELDS = {"inquiry": frozenset(_COMMON), "apply": frozenset(_COMMON | {"based_on", "plan"})}
BACKUP_EVIDENCE_VERSION = 3      # the first format that may carry `backup_evidence` (apply approvals only)

_APPROVAL_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")
_ALIAS = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_JOB_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")  # same shape as recovery_key / run_key
_NAME = re.compile(r"[a-z_][a-z0-9_]{0,62}")      # role and input names
_ARG_VALUE = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_INSTANT = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z")
_ACCOUNT_KEY = re.compile(r"[1-9][0-9]{0,18}")
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*")


class OpsApprovalRefused(Exception):
    """`code` is a fixed reason; nothing from the input is carried."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> OpsApprovalRefused:
    return OpsApprovalRefused(code)


class SignatureVerifier(Protocol):
    """Interface only (contract 4-2 D). Must return exactly True for a valid detached
    signature by a trusted key for `namespace`; anything else is a refusal."""

    def verify(self, *, namespace: str, message: bytes, signature: bytes) -> bool: ...


def production_verifier() -> SignatureVerifier:
    """No signing tool is decided or implemented: always refuses."""
    raise _refuse("signature_verifier_not_implemented")


SUBJECTS = ("approval", "manifest", "backup")   # backup: OPS_MIGRATION_CLI_PLAN 4-4-7 C10


def signature_namespace(purpose: str, subject: str = "approval") -> str:
    """One namespace per mode x signed subject (contract 4-2-1); a valid signature made for
    one cannot be reused for another."""
    if purpose not in MODES or subject not in SUBJECTS:
        raise _refuse("signature_namespace_invalid")
    return f"jp-vocab-ops/v1/{purpose}/{subject}"


def check_signature(data: bytes, signature: bytes, *, mode: str, subject: str,
                    verifier: SignatureVerifier | None) -> None:
    """Require `verifier` to accept a detached signature over exactly `data` for this mode and
    subject. Any verifier error or non-True result is the same fixed refusal."""
    if mode not in MODES:
        raise _refuse("mode_invalid")
    if verifier is None:
        raise _refuse("signature_verifier_unavailable")
    namespace = signature_namespace(mode, subject)
    if type(data) is not bytes or type(signature) is not bytes or not signature:
        raise _refuse(f"{subject}_signature_invalid")
    try:
        ok = verifier.verify(namespace=namespace, message=data, signature=signature)
    except Exception:
        raise _refuse(f"{subject}_signature_invalid") from None
    if ok is not True:
        raise _refuse(f"{subject}_signature_invalid")


# --- values -----------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return type(value) is int  # bool and str are not numbers here


def _id(value: Any) -> bool:
    return _is_int(value) and 0 < value <= ID_MAX


def _text(value: Any, pattern: re.Pattern) -> bool:
    return type(value) is str and value.isascii() and pattern.fullmatch(value) is not None


def _instant(value: Any) -> datetime:
    if type(value) is not str or not _INSTANT.fullmatch(value):
        raise _refuse("approval_time_invalid")
    try:
        return datetime(*(int(part) for part in _INSTANT.fullmatch(value).groups()), tzinfo=timezone.utc)
    except ValueError:
        raise _refuse("approval_time_invalid") from None


def _now(value: Any) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0)):
        raise _refuse("clock_value_invalid")
    return value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _digest(domain: str, value: Any) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\n" + _canonical(value)).hexdigest()


def _reject_constant(_: str) -> Any:
    raise ValueError


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _decode(data: Any) -> dict[str, Any]:
    if type(data) is not bytes or not 0 < len(data) <= MAX_APPROVAL_BYTES or data.startswith(b"\xef\xbb\xbf"):
        raise _refuse("approval_format_invalid")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_reject_constant,
                           parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _refuse("approval_format_invalid") from None
    if not isinstance(value, dict):
        raise _refuse("approval_format_invalid")
    return value


# --- approval -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Step:
    command: str
    access: str
    role: str
    profile: str
    args: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Approval:
    kind: str
    approval_id: str
    supersedes: tuple[str, str] | None     # (approval_id, sha256 of the prior approval bytes)
    purpose: str
    alias: str
    db_identity: str
    manifest: str
    tool: str
    steps: tuple[Step, ...]
    accounts: frozenset[int]
    max_accounts: int
    job_key: str
    job_inputs: tuple[tuple[str, Any], ...]
    valid_from: datetime
    valid_until: datetime
    based_on: tuple[str, str] | None
    plan: tuple[tuple[int, str], ...]
    sha256: str
    format_version: int = 1
    verified: bool = False       # set only by verify_signed, after the signature check
    backup_evidence_sha256: str | None = None    # v3 apply only: the bound evidence document hash

    def plan_for(self, account_id: int) -> str | None:
        return dict(self.plan).get(account_id)


def _steps(value: Any, tool: str, kind: str) -> tuple[Step, ...]:
    if not isinstance(value, list) or not value:
        raise _refuse("approval_steps_invalid")
    steps, commands, role_access = [], set(), {}
    for item in value:
        if not isinstance(item, dict) or not set(item) <= {"command", "access", "role", "profile", "args"} \
                or not {"command", "access", "role", "profile"} <= set(item):
            raise _refuse("approval_steps_invalid")
        command, access, role, profile = item["command"], item["access"], item["role"], item["profile"]
        args = item.get("args", {})
        if type(command) is not str or command not in TOOLS[tool] or access not in ACCESS \
                or TOOLS[tool][command] != access or not _text(role, _NAME) or not _text(profile, _HEX64):
            raise _refuse("approval_steps_invalid")
        if not isinstance(args, dict) or not all(_text(k, _NAME) and _text(v, _ARG_VALUE) for k, v in args.items()):
            raise _refuse("approval_steps_invalid")
        if command in commands:
            raise _refuse("approval_steps_invalid")
        if role_access.setdefault(role, access) != access:
            raise _refuse("approval_role_access_mixed")      # one role is read OR write (contract 8)
        if kind == "inquiry" and access != "read":
            raise _refuse("inquiry_write_step_not_allowed")  # contract 4-6-1
        commands.add(command)
        steps.append(Step(command, access, role, profile, tuple(sorted(args.items()))))
    return tuple(steps)


def _job(value: Any) -> tuple[str, tuple[tuple[str, Any], ...]]:
    if not isinstance(value, dict) or set(value) != {"key", "inputs"} or not _text(value["key"], _JOB_KEY) \
            or not isinstance(value["inputs"], dict):
        raise _refuse("approval_job_invalid")
    for name, item in value["inputs"].items():
        if not _text(name, _NAME) or not (item is None or type(item) in (str, bool)
                                          or (_is_int(item) and abs(item) <= ID_MAX)):
            raise _refuse("approval_job_invalid")
        if type(item) is str and (not item.isascii() or len(item) > 256):
            raise _refuse("approval_job_invalid")
    return value["key"], tuple(sorted(value["inputs"].items()))


def _supersedes(value: Any, version: int, own_id: str) -> tuple[str, str] | None:
    """Contract 4-6-5. Version 1 keeps only its first approvals; a version 1 link is never converted."""
    if value is None:
        return None
    if version == 1:
        raise _refuse("approval_supersedes_resign_required")
    if not isinstance(value, dict) or set(value) != {"approval_id", "sha256"}             or not _text(value["approval_id"], _APPROVAL_ID) or not _text(value["sha256"], _HEX64)             or value["approval_id"] == own_id:
        raise _refuse("approval_supersedes_invalid")
    return value["approval_id"], value["sha256"]


def parse_approval(data: bytes) -> Approval:
    """Format and value checks only (no signature, no clock)."""
    raw = _decode(data)
    kind = raw.get("kind")
    if kind not in KINDS:
        raise _refuse("approval_kind_invalid")
    allowed = FIELDS[kind]
    if kind == "apply" and "backup_evidence" in raw and _is_int(raw.get("format_version")) \
            and raw.get("format_version") >= BACKUP_EVIDENCE_VERSION:
        allowed = allowed | {"backup_evidence"}         # never accepted (or converted) for v1 / v2 or inquiries
    if set(raw) != allowed:
        raise _refuse("approval_fields_invalid")
    version = raw["format_version"]
    if not _is_int(version) or version not in FORMAT_VERSIONS:
        raise _refuse("approval_format_version")
    if not _text(raw["approval_id"], _APPROVAL_ID):
        raise _refuse("approval_id_invalid")
    supersedes = _supersedes(raw["supersedes"], version, raw["approval_id"])
    if raw["purpose"] not in MODES:
        raise _refuse("approval_purpose_invalid")
    if not _text(raw["alias"], _ALIAS):
        raise _refuse("approval_alias_invalid")
    if not _text(raw["db_identity"], _HEX64) or not _text(raw["manifest"], _HEX64):
        raise _refuse("approval_fingerprint_invalid")
    tool = raw["tool"]
    if type(tool) is not str or tool not in TOOLS:
        raise _refuse("approval_tool_invalid")
    steps = _steps(raw["steps"], tool, kind)
    accounts, maximum = raw["accounts"], raw["max_accounts"]
    if not _id(maximum) or not isinstance(accounts, list) or not accounts or not all(_id(a) for a in accounts) \
            or len(set(accounts)) != len(accounts) or len(accounts) > maximum:
        raise _refuse("approval_accounts_invalid")
    job_key, job_inputs = _job(raw["job"])
    start, end = _instant(raw["valid_from"]), _instant(raw["valid_until"])
    if not start < end:
        raise _refuse("approval_time_invalid")
    if end - start > MAX_VALIDITY:
        raise _refuse("approval_validity_too_long")
    if type(raw["approved_by"]) is not str or not raw["approved_by"].isascii() \
            or not 0 < len(raw["approved_by"]) <= 128 or not raw["approved_by"].isprintable():
        raise _refuse("approval_signer_label_invalid")
    based_on, plan = None, ()
    if kind == "apply":
        ref = raw["based_on"]
        if not isinstance(ref, dict) or set(ref) != {"approval_id", "sha256"} \
                or not _text(ref["approval_id"], _APPROVAL_ID) or not _text(ref["sha256"], _HEX64):
            raise _refuse("apply_based_on_invalid")
        based_on = (ref["approval_id"], ref["sha256"])
        plans = raw["plan"]
        if not isinstance(plans, dict) or not all(_text(k, _ACCOUNT_KEY) and int(k) <= ID_MAX
                                                  and _text(v, _HEX64) for k, v in plans.items()) \
                or {int(k) for k in plans} != set(accounts):
            raise _refuse("apply_plan_invalid")
        plan = tuple(sorted((int(k), v) for k, v in plans.items()))
    evidence = None
    if "backup_evidence" in raw:
        value = raw["backup_evidence"]
        if not isinstance(value, dict) or set(value) != {"sha256"} or not _text(value["sha256"], _HEX64):
            raise _refuse("approval_backup_evidence_invalid")
        evidence = value["sha256"]
    return Approval(kind, raw["approval_id"], supersedes, raw["purpose"], raw["alias"], raw["db_identity"],
                    raw["manifest"], tool, steps, frozenset(accounts), maximum, job_key, job_inputs, start, end,
                    based_on, plan, hashlib.sha256(data).hexdigest(), version, backup_evidence_sha256=evidence)


def verify_signed(data: bytes, signature: bytes, *, mode: str, verifier: SignatureVerifier | None) -> Approval:
    """Parse, then require a valid signature for this mode's namespace and a matching purpose."""
    if mode not in MODES:
        raise _refuse("mode_invalid")
    if verifier is None:
        raise _refuse("signature_verifier_unavailable")
    approval = parse_approval(data)
    if approval.purpose != mode:
        raise _refuse("approval_purpose_mismatch")       # contract 4-5
    check_signature(data, signature, mode=mode, subject="approval", verifier=verifier)
    return replace(approval, verified=True)


def check_validity(approval: Approval, now: datetime) -> None:
    instant = _now(now)
    if instant < approval.valid_from:
        raise _refuse("approval_not_yet_valid")
    if instant >= approval.valid_until:
        raise _refuse("approval_expired")


def check_based_on(apply: Approval, inquiry: Approval) -> None:
    """Contract 4-6-2. The inquiry's own validity is not required (basis, not permission)."""
    if apply.kind != "apply" or apply.based_on is None:
        raise _refuse("apply_based_on_invalid")
    if inquiry.kind != "inquiry":
        raise _refuse("apply_based_on_kind_mismatch")
    if apply.based_on[0] != inquiry.approval_id or not hmac.compare_digest(apply.based_on[1], inquiry.sha256):
        raise _refuse("apply_based_on_mismatch")
    if (apply.purpose, apply.alias, apply.db_identity, apply.manifest, apply.tool, apply.job_key) \
            != (inquiry.purpose, inquiry.alias, inquiry.db_identity, inquiry.manifest, inquiry.tool, inquiry.job_key) \
            or _canonical(dict(apply.job_inputs)) != _canonical(dict(inquiry.job_inputs)):  # True is not 1
        raise _refuse("apply_basis_field_mismatch")
    if not apply.accounts <= inquiry.accounts:
        raise _refuse("apply_accounts_outside_inquiry")


def check_succession(current: Approval, prior: Approval | None) -> None:
    """Contract 4-6-4 / 4-6-5. `prior` is the previous approval of this job of the SAME kind, or
    None at the job's first approval of that kind. A link needs a signature-verified prior and
    both its id and the SHA-256 of its signed bytes."""
    if prior is None:
        if current.supersedes is not None:
            raise _refuse("approval_supersedes_unknown")
        return
    if prior.kind != current.kind:
        raise _refuse("approval_supersedes_kind_mismatch")
    if (prior.job_key, prior.tool, prior.purpose) != (current.job_key, current.tool, current.purpose):
        raise _refuse("approval_job_mismatch")
    if current.approval_id == prior.approval_id:
        if current.sha256 != prior.sha256:
            raise _refuse("approval_id_reused")
        return
    if not prior.verified:
        raise _refuse("approval_prior_unverified")
    if current.supersedes is None or current.supersedes[0] != prior.approval_id             or not hmac.compare_digest(current.supersedes[1], prior.sha256):
        raise _refuse("approval_supersedes_mismatch")



def check_apply_chain(current: Approval, chain: Any) -> Approval | None:
    """Contract 4-6-6. `chain` holds signature-verified (apply approval, its basis inquiry) pairs from
    the job's first apply approval to the one right before `current`. Returns the prior (the last apply
    approval) or None for an empty chain. Validity periods of the past approvals are not required (they
    are evidence, not permission). This shows only that the presented chain is consistent; it does not
    show that it is the latest one. No permission of a past approval is used."""
    if not isinstance(chain, tuple):
        raise _refuse("approval_chain_invalid")
    if not chain:
        return None
    if not isinstance(current, Approval) or current.kind != "apply":
        raise _refuse("approval_chain_kind_unsupported")
    if len(chain) > MAX_CHAIN_LINKS:
        raise _refuse("approval_chain_too_long")
    ids, hashes = {current.approval_id}, {current.sha256}
    previous: Approval | None = None
    for pair in chain:
        if not isinstance(pair, tuple) or len(pair) != 2 \
                or not all(isinstance(item, Approval) for item in pair):
            raise _refuse("approval_chain_invalid")
        apply, inquiry = pair
        if not apply.verified or not inquiry.verified:
            raise _refuse("approval_prior_unverified")
        if apply.kind != "apply":
            raise _refuse("approval_supersedes_kind_mismatch")
        check_based_on(apply, inquiry)
        if apply.approval_id in ids or apply.sha256 in hashes:
            raise _refuse("approval_chain_duplicate")
        ids.add(apply.approval_id)
        hashes.add(apply.sha256)
        if previous is None:
            if apply.supersedes is not None:
                raise _refuse("approval_chain_first_linked")
        else:
            check_succession(apply, previous)
        previous = apply
    check_succession(current, previous)
    return previous


# --- fingerprints (contract 3-1, 3-3) -----------------------------------------------------

def db_identity_fingerprint(*, alias: str, host: str, port: int, database: str, server_major: int,
                            identity_value: str) -> str:
    """From values the caller observed on one connection (contract 3-1). Role, privileges and
    TLS are deliberately not part of it."""
    if not _text(alias, _ALIAS) or type(host) is not str or not host.isascii() or not _HOST.fullmatch(host.lower()) \
            or not _is_int(port) or not 0 < port < 65536 or type(database) is not str or not database.isascii() \
            or not 0 < len(database) <= 63 or not _is_int(server_major) or not 0 < server_major < 1000 \
            or type(identity_value) is not str or not identity_value.isascii() or not 0 < len(identity_value) <= 128:
        raise _refuse("db_identity_value_invalid")
    return _digest("jp-vocab-ops/db-identity/v1", {"alias": alias, "host": host.lower(), "port": port,
                                                    "database": database, "server_major": server_major,
                                                    "identity": identity_value})


def _check_artifact(artifact_sha256: Any) -> None:
    """Contract 3-3-1: None or 64 lowercase hex characters; nothing is converted."""
    if artifact_sha256 is not None and not _text(artifact_sha256, _HEX64):
        raise _refuse("artifact_sha256_invalid")


def job_plan_fingerprint(*, db_identity: str, manifest: str, tool: str, account_id: int, job_key: str,
                         job_inputs: Mapping[str, Any], product_fingerprint: str | None,
                         artifact_sha256: str | None = None) -> str:
    """Contract 3-3: no subcommand, role or connection profile in it. Contract 3-3-1: a plan
    artifact digest is part of it only when given; without one the key is absent, so every
    existing fingerprint keeps its value."""
    _check_artifact(artifact_sha256)
    if not _text(db_identity, _HEX64) or not _text(manifest, _HEX64):
        raise _refuse("plan_value_invalid")
    if type(tool) is not str or tool not in TOOLS or not _id(account_id):
        raise _refuse("plan_value_invalid")
    if product_fingerprint is not None and not _text(product_fingerprint, _HEX64):
        raise _refuse("plan_value_invalid")
    if not isinstance(job_inputs, Mapping):
        raise _refuse("plan_value_invalid")
    try:
        key, inputs = _job({"key": job_key, "inputs": dict(job_inputs)})
    except OpsApprovalRefused:
        raise _refuse("plan_value_invalid") from None
    value = {"db_identity": db_identity, "manifest": manifest, "tool": tool, "account": account_id, "job_key": key,
             "job_inputs": dict(inputs), "product": product_fingerprint}
    if artifact_sha256 is not None:
        value["artifact"] = artifact_sha256
    return _digest("jp-vocab-ops/job-plan/v1", value)


# --- command judgement (contract 3-5) ------------------------------------------------------

@dataclass(frozen=True)
class Observed:
    """Values measured by the caller (next unit) on the connection about to be used."""
    db_identity: str
    manifest: str
    role: str
    profile: str
    read_only: bool


@dataclass(frozen=True)
class Decision:
    kind: str
    command: str
    access: str
    account_id: int
    job_plan: str


def authorize_command(approval: Approval, *, now: datetime, command: str, args: Mapping[str, str],
                      account_id: int, job_key: str, job_inputs: Mapping[str, Any],
                      product_fingerprint: str | None, observed: Observed,
                      inquiry: Approval | None = None, prior: Approval | None = None,
                      artifact_sha256: str | None = None) -> Decision:
    """Judge one command under one (already signature-verified) approval. For an apply
    approval `inquiry` is its verified basis. Returns the job plan fingerprint (for an inquiry
    approval: to print; for an apply approval: already matched)."""
    check_validity(approval, now)
    check_succession(approval, prior)
    if approval.kind == "apply":
        if inquiry is None:
            raise _refuse("apply_based_on_missing")
        check_based_on(approval, inquiry)
    elif inquiry is not None:
        raise _refuse("inquiry_based_on_not_allowed")
    # Input contract before any comparison or sorting (review fix: no TypeError escapes).
    _check_artifact(artifact_sha256)
    step = next((s for s in approval.steps if s.command == command), None) if type(command) is str else None
    if step is None:
        raise _refuse("command_not_approved")
    if not isinstance(args, Mapping) or not all(_text(k, _NAME) and _text(v, _ARG_VALUE) for k, v in args.items()) \
            or tuple(sorted(args.items())) != step.args:
        raise _refuse("command_args_not_approved")
    if approval.kind == "inquiry" and step.access != "read":
        raise _refuse("inquiry_write_step_not_allowed")
    if not _id(account_id) or account_id not in approval.accounts:
        raise _refuse("account_not_approved")
    if job_key != approval.job_key or not isinstance(job_inputs, Mapping):
        raise _refuse("job_input_mismatch")
    try:
        inputs = _job({"key": job_key, "inputs": dict(job_inputs)})[1]
    except OpsApprovalRefused:
        raise _refuse("job_input_mismatch") from None
    if _canonical(dict(inputs)) != _canonical(dict(approval.job_inputs)):  # True is not 1
        raise _refuse("job_input_mismatch")
    if not isinstance(observed, Observed) or type(observed.read_only) is not bool \
            or not all(_text(v, _HEX64) for v in (observed.db_identity, observed.manifest, observed.profile)) \
            or not _text(observed.role, _NAME):
        raise _refuse("observed_value_invalid")
    if not hmac.compare_digest(observed.db_identity, approval.db_identity):
        raise _refuse("db_identity_mismatch")
    if not hmac.compare_digest(observed.manifest, approval.manifest):
        raise _refuse("manifest_mismatch")
    if observed.role != step.role or not hmac.compare_digest(observed.profile, step.profile):
        raise _refuse("connection_profile_mismatch")
    if step.access == "read" and observed.read_only is not True:
        raise _refuse("read_step_not_read_only")
    if step.access == "write" and observed.read_only is not False:
        raise _refuse("write_step_read_only")
    plan = job_plan_fingerprint(db_identity=observed.db_identity, manifest=observed.manifest, tool=approval.tool,
                                account_id=account_id, job_key=job_key, job_inputs=job_inputs,
                                product_fingerprint=product_fingerprint, artifact_sha256=artifact_sha256)
    if approval.kind == "apply":
        expected = approval.plan_for(account_id)
        if expected is None or not hmac.compare_digest(plan, expected):
            raise _refuse("job_plan_mismatch")
    return Decision(approval.kind, command, step.access, account_id, plan)


def run_authorized(action: Callable[[Decision], Any], *, mode: str, approval_bytes: bytes,
                   approval_signature: bytes, inquiry_bytes: bytes | None = None,
                   inquiry_signature: bytes | None = None,
                   verifier_factory: Callable[[], SignatureVerifier] = production_verifier,
                   **judge: Any) -> Any:
    """Entry shape for the later tool wiring: verify signatures, judge the command, and only
    then call `action`. With the default factory it refuses before `action` runs."""
    verifier = verifier_factory()
    approval = verify_signed(approval_bytes, approval_signature, mode=mode, verifier=verifier)
    inquiry = None
    if approval.kind == "apply":
        if inquiry_bytes is None or inquiry_signature is None:
            raise _refuse("apply_based_on_missing")
        inquiry = verify_signed(inquiry_bytes, inquiry_signature, mode=mode, verifier=verifier)
    decision = authorize_command(approval, inquiry=inquiry, **judge)
    return action(decision)
