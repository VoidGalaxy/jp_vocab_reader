"""Operations tool safety contract, unit 5: synthetic integrated pre-check
(OPS_TOOL_SAFETY_CONTRACT.md 7-1).

A thin layer over units 1-4 that runs them in one fixed order on one set of inputs fixed at
start, so the parts cannot each pass on different targets. Synthetic mode only; production
mode is refused before any check. A pass means only "the synthetic pre-check matched": it is
not permission to connect to a database or to run any work, and nothing here connects,
imports, compiles or runs the listed files.

Caller-provided observations (server major version, identity row value, connection profile,
read-only state) are taken as given; this layer does not query a server.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

import _ops_approval as oa
import _ops_manifest as om
import _ops_signature as osig
import _ops_target as ot

MODE = "synthetic"


class OpsPreflightRefused(Exception):
    """`stage` and `code` are fixed strings from the failing step; nothing else is carried."""

    def __init__(self, stage: str, code: str):
        super().__init__(f"{stage}:{code}")
        self.stage = stage
        self.code = code


@dataclass(frozen=True)
class TargetObservation:
    """Caller-provided values (not read from a server here)."""
    host: str
    port: int
    database: str
    server_major: int
    identity_value: str


@dataclass(frozen=True)
class ConnectionObservation:
    """Caller-provided connection profile values (not queried here)."""
    profile: str
    read_only: bool


@dataclass(frozen=True)
class SyntheticTrust:
    allowed_signers: bytes
    revoked_keys: bytes
    principal: str

    def __repr__(self) -> str:
        return "SyntheticTrust()"


@dataclass(frozen=True)
class ChainLink:
    """Contract 4-6-6: one prior apply approval and its basis inquiry, as bytes only."""
    approval: bytes = field(repr=False)
    approval_signature: bytes = field(repr=False)
    inquiry: bytes = field(repr=False)
    inquiry_signature: bytes = field(repr=False)


@dataclass(frozen=True)
class _Verified:
    """Approvals this pre-check verified itself, for the provider's re-judgement (never an input)."""
    approval: oa.Approval
    inquiry: oa.Approval | None
    prior: oa.Approval | None
    # RESUME_PLAN 9-3: the first link of the verified prior chain (the job's first apply approval A0 and
    # its basis inquiry I0); None for an empty chain. Never printed.
    first_apply: oa.Approval | None = field(default=None, repr=False)
    first_inquiry: oa.Approval | None = field(default=None, repr=False)


@dataclass(frozen=True)
class PreflightInput:
    mode: str
    approval: bytes
    approval_signature: bytes
    manifest: bytes
    manifest_signature: bytes
    deploy_root: str
    command: str
    args: Mapping[str, str]
    account_id: int
    job_key: str
    job_inputs: Mapping[str, Any]
    product_fingerprint: str | None
    target: TargetObservation
    connection: ConnectionObservation
    secret_dsn: str = field(repr=False)
    environment: Mapping[str, str] = field(repr=False)
    trust: SyntheticTrust = field(repr=False)
    now: datetime
    inquiry: bytes | None = None
    inquiry_signature: bytes | None = None
    artifact_sha256: str | None = None          # contract 3-3-1: plan artifact digest, judged with the plan
    prior_chain: tuple = ()                     # contract 4-6-6: ChainLink items, first apply approval first


@dataclass(frozen=True)
class SyntheticPreflightMatched:
    """Public result. Not a connection or execution permission."""
    kind: str
    command: str
    access: str
    account_id: int
    job_plan: str
    db_identity: str
    manifest_sha256: str
    file_count: int
    host: str
    port: int
    dbname: str
    role: str
    sslrootcert: str
    connection_allowed: bool = False
    caller_provided: tuple[str, ...] = ("server_major", "identity_value", "connection_profile", "read_only")
    verified: Any = field(default=None, repr=False, compare=False)   # internal: see _Verified


def _stage(stage: str, error: Exception) -> OpsPreflightRefused:
    return OpsPreflightRefused(stage, getattr(error, "code", "refused"))


_REFUSALS = (oa.OpsApprovalRefused, om.OpsManifestRefused, osig.OpsSignatureRefused, ot.OpsTargetRefused)


def _chain_links(chain: Any) -> tuple[ChainLink, ...]:
    """Contract 4-6-6 limits, before any signature is checked."""
    if type(chain) is not tuple or not all(type(link) is ChainLink for link in chain) \
            or not all(type(value) is bytes for link in chain for value in (
                link.approval, link.approval_signature, link.inquiry, link.inquiry_signature)):
        raise OpsPreflightRefused("approval", "approval_chain_invalid")
    if len(chain) > oa.MAX_CHAIN_LINKS:
        raise OpsPreflightRefused("approval", "approval_chain_too_long")
    if sum(len(link.approval) + len(link.approval_signature) + len(link.inquiry) + len(link.inquiry_signature)
           for link in chain) > oa.MAX_CHAIN_BYTES:
        raise OpsPreflightRefused("approval", "approval_chain_too_large")
    return chain


def initial_apply_approvals(result: Any, inputs: Any) -> tuple[oa.Approval, oa.Approval]:
    """RESUME_PLAN 9-3: the job's first apply approval A0 and its basis inquiry I0 as THIS pre-check
    verified them, tied to the first link of the same input bytes. No caller-made approval or "verified"
    flag is accepted. The chain being consistent does not prove it is the latest one; A0 grants nothing."""
    verified = getattr(result, "verified", None)
    if not isinstance(result, SyntheticPreflightMatched) or not isinstance(verified, _Verified) \
            or not isinstance(inputs, PreflightInput):
        raise OpsPreflightRefused("approval", "preflight_result_mismatch")
    chain = _chain_links(inputs.prior_chain)       # the pre-check's own tuple / ChainLink / bytes / limit rules
    if not chain:
        raise OpsPreflightRefused("approval", "approval_chain_first_missing")
    first, basis = verified.first_apply, verified.first_inquiry
    link = chain[0]
    if not isinstance(first, oa.Approval) or not isinstance(basis, oa.Approval) or not first.verified \
            or not basis.verified or type(link) is not ChainLink \
            or first.sha256 != hashlib.sha256(link.approval).hexdigest() \
            or basis.sha256 != hashlib.sha256(link.inquiry).hexdigest() \
            or first.kind != "apply" or basis.kind != "inquiry" or first.supersedes is not None \
            or first.based_on != (basis.approval_id, basis.sha256):
        raise OpsPreflightRefused("approval", "preflight_result_mismatch")
    return first, basis


def run_synthetic_preflight(inputs: PreflightInput) -> SyntheticPreflightMatched:
    """Run the fixed order of contract 7-1; the first refusal stops everything after it."""
    if not isinstance(inputs, PreflightInput):
        raise OpsPreflightRefused("input", "preflight_input_invalid")
    if inputs.mode != MODE:
        raise OpsPreflightRefused("mode", "mode_not_synthetic")       # (1) before any check
    data = inputs
    links = _chain_links(data.prior_chain)                                                            # 4-6-6 (1)
    try:
        verifier = osig.SyntheticOpenSSHVerifier(allowed_signers=data.trust.allowed_signers,
                                                 revoked_keys=data.trust.revoked_keys,
                                                 principal=data.trust.principal, verify_time=data.now)
        approval = oa.verify_signed(data.approval, data.approval_signature, mode=MODE, verifier=verifier)  # (2)
        inquiry = None
        if approval.kind == "apply":
            if data.inquiry is None or data.inquiry_signature is None:
                raise OpsPreflightRefused("approval", "apply_based_on_missing")
            inquiry = oa.verify_signed(data.inquiry, data.inquiry_signature, mode=MODE, verifier=verifier)
        pairs = tuple((oa.verify_signed(link.approval, link.approval_signature, mode=MODE, verifier=verifier),
                       oa.verify_signed(link.inquiry, link.inquiry_signature, mode=MODE, verifier=verifier))
                      for link in links)
        prior = oa.check_apply_chain(approval, pairs)
    except _REFUSALS as error:
        raise _stage("approval", error) from None
    try:
        if om.manifest_fingerprint(data.manifest) != approval.manifest:                                # (3)
            raise OpsPreflightRefused("manifest", "manifest_not_approved")
        manifest_sha = om.verify_manifest_signed(data.manifest, data.manifest_signature, mode=MODE,
                                                 verifier=verifier)                                     # (4)
        _, entries = om.parse_manifest(data.manifest)
    except _REFUSALS as error:
        raise _stage("manifest", error) from None
    try:
        target = data.target
        if not isinstance(target, TargetObservation):
            raise OpsPreflightRefused("target", "target_observation_invalid")
        db_identity = oa.db_identity_fingerprint(alias=approval.alias, host=target.host, port=target.port,
                                                 database=target.database, server_major=target.server_major,
                                                 identity_value=target.identity_value)
        if db_identity != approval.db_identity:                                                         # (5)
            raise OpsPreflightRefused("target", "db_identity_not_approved")
    except _REFUSALS as error:
        raise _stage("target", error) from None
    step = next((s for s in approval.steps if s.command == data.command), None) \
        if type(data.command) is str else None                                                          # (6)
    if step is None:
        raise OpsPreflightRefused("command", "command_not_approved")
    tls_entries = [e for e in entries if e.parts[:2] == ("ops", "tls")]
    if len(tls_entries) != 1:
        raise OpsPreflightRefused("tls", "tls_root_not_bound")      # which root was approved is unprovable
    sslrootcert = os.path.join(data.deploy_root, *tls_entries[0].parts) if type(data.deploy_root) is str else ""
    try:
        connection = ot.check_preconnect(data.secret_dsn, ot.ApprovedTarget(
            host=target.host, port=target.port, dbname=target.database, role=step.role,
            sslmode=ot.REQUIRED_SSLMODE, sslrootcert=sslrootcert), data.environment)                    # (7)
    except _REFUSALS as error:
        raise _stage("connection", error) from None
    try:
        observed = data.connection
        if not isinstance(observed, ConnectionObservation):
            raise OpsPreflightRefused("command", "connection_observation_invalid")
        decision = oa.authorize_command(
            approval, now=data.now, command=data.command, args=data.args, account_id=data.account_id,
            job_key=data.job_key, job_inputs=data.job_inputs, product_fingerprint=data.product_fingerprint,
            observed=oa.Observed(db_identity=db_identity, manifest=manifest_sha, role=connection.role,
                                 profile=observed.profile, read_only=observed.read_only),
            inquiry=inquiry, prior=prior, artifact_sha256=data.artifact_sha256)                         # (8)
    except _REFUSALS as error:
        raise _stage("command", error) from None
    if connection.sslrootcert != sslrootcert:                                                           # (9)
        raise OpsPreflightRefused("tls", "tls_root_not_bound")
    try:
        files = om.check_manifest_files(data.manifest, data.deploy_root)                                # (10)
    except _REFUSALS as error:
        raise _stage("files", error) from None
    if files.manifest_sha256 != manifest_sha:
        raise OpsPreflightRefused("files", "manifest_changed")
    return SyntheticPreflightMatched(decision.kind, decision.command, decision.access, decision.account_id,
                                     decision.job_plan, db_identity, manifest_sha, files.file_count,
                                     connection.host, connection.port, connection.dbname, connection.role,
                                     connection.sslrootcert, verified=_Verified(approval, inquiry, prior, *(pairs[0] if pairs else (None, None))))
