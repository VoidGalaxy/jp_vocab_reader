"""Subscribed-card (lexeme) CLI `resume` on a real local PostgreSQL (OPS_MIGRATION_RESUME_LEXEME_PLAN), run explicitly,
never by discovery and never by import:

    python tests/_ops_resume_lexeme_real.py prepare        # L-2: pg67 cluster, TLS, roles, template + check DBs, grants
    python tests/_ops_resume_lexeme_real.py check-lexeme   # L-2: G0 + G1 (not counted), L1..L9, post-check
    python tests/_ops_resume_lexeme_real.py cleanup        # L-2: R2, record vs live facts, stop, delete this run only

L-1 = this code and its PG-free fake checks only; none of the three phases is approved. The admin row changes
(L6 / L7) and privilege changes (L8 / L9) are closed lists here and stay locked until the L-2 decision is written
into LQ3_CHANGES_APPROVED below (never by an argument or an environment value).

The target is the closed layout `_ops_real_layout.PG67` (C:/JV_Tools/pg67, localhost:55512, roles jpvl_*), passed
explicitly to every shared function; the C12 / RS4 runners and their globals are not touched. Only the target-free
instrumentation of the RS4 runner is reused (statement trace, under-lock reads, nine-value wrappers).

Cards (keys, never positions): account a's subscribed l1, l2 and personal p1 of the shared synthetic data. Expected
values are the plan's (2절 / 7-4절). The personal-card RS4 results are not counted for these cards.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(TESTS_DIR.parent) not in sys.path:      # path only: app is imported after the environment pin
    sys.path.append(str(TESTS_DIR.parent))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_adapter as ad  # noqa: E402
import _ops_approval as oa  # noqa: E402
import _ops_audit_real as real  # noqa: E402
import _ops_audit_run as ar  # noqa: E402
import _ops_backup_evidence as be  # noqa: E402
import _ops_manifest as om  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_real_layout as lay  # noqa: E402
import _ops_resume_real as rr  # noqa: E402  (target-free instrumentation only)
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (temporary test key helper only)

LAYOUT = lay.PG67
T = LAYOUT.target
TEMPLATE = LAYOUT.template
CHECK_DB = LAYOUT.check_db
READ, WRITE = LAYOUT.read, LAYOUT.write
BUSINESS_ROLES = LAYOUT.business_roles
SYN = lay.SYN
CheckFailed, expect = lay.CheckFailed, lay.expect
RUN_KEY = "lex-resume-1"
T0 = sigtests.T0
POST = "post_check"

# LQ3 (admin row changes L6 / L7, privilege changes L8 / L9): code only in L-1. Anything but True stops
# `check-lexeme` before G0 with exit 1. Changed only by editing this value after the user's L-2 decision.
LQ3_CHANGES_APPROVED: bool | None = True

# Fixed card sets (plan 2절). Names map to keys through the recorded synthetic ids, never through positions.
LEXEME_ONLY = ("l1", "l2")
MIXED = ("l1", "l2", "p1")
# check DB -> (card set, initial state, first-apply batch, initial cursor)
INITIAL = {"l1": (LEXEME_ONLY, "started", 1, 1), "l2": (LEXEME_ONLY, "failed", 2, 1),
           "l3": (MIXED, "started", 1, 1), "l6": (LEXEME_ONLY, "started", 1, 1), "l7": (LEXEME_ONLY, "started", 1, 1),
           "l8": (MIXED, "started", 1, 1), "l9": (LEXEME_ONLY, "started", 1, 1)}
# Checklist order (plan 2절, 7-4절). L4 and L5 judge the evidence of L1 / L2 / L3, so they follow them.
PLANNED = ("l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9")
# The recorded accounts other than the run's own (a): their rows for the SAME lexemes must never change.
OTHER_ACCOUNTS = ("b", "c")


# --- PG67-bound helpers: the shared functions with this runner's layout passed explicitly -------------------

def expected_profiles(db: str) -> tuple[pv.ExpectedProfile, pv.ExpectedProfile]:
    return lay.expected_profiles(LAYOUT, db)


def contract_grants(db: str) -> list[sql.Composed]:
    return lay.contract_grants(LAYOUT, db)


def variant_statements(name: str, phase: str) -> list[sql.Composed]:
    return lay.variant_statements(LAYOUT, name, phase)


def require_target_bound(rec: g.Record, data: bytes) -> dict:
    return lay.require_target_bound(LAYOUT, rec, data)


def require_ours(target: dict) -> None:
    lay.require_ours(LAYOUT, target)


def business_check(kwargs: dict) -> None:
    lay.business_check(LAYOUT, kwargs)


def post_connect_check(conn: Any, target: dict, user: str) -> None:
    lay.post_connect_check(LAYOUT, conn, target, user)


def admin(db: str, pid: int, autocommit: bool = True):
    return lay.admin(LAYOUT, db, pid, autocommit)


def hba() -> str:
    return lay.hba(LAYOUT)


def conf() -> str:
    return lay.conf(LAYOUT)


class Counts(lay.Counts):
    def __init__(self):
        super().__init__(BUSINESS_ROLES)


ORIGINAL_CONNECTOR = lay.ORIGINAL_CONNECTOR


class RunScopes(lay.RunScopes):
    def __init__(self, real: Callable | None = None):
        super().__init__(LAYOUT, real or ORIGINAL_CONNECTOR)


def build_template(pid: int, rec: g.Record) -> dict:
    return lay.build_template(LAYOUT, pid, rec, lambda db, p, autocommit=True: admin(db, p, autocommit))


def prepare() -> None:
    lay.prepare(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit),
                build_fn=lambda p, rec: build_template(p, rec), grants_fn=lambda db: contract_grants(db))


def cleanup() -> None:
    lay.cleanup(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def card_keys(ids: dict, names: tuple[str, ...]) -> list[tuple[str, int, int]]:
    """(kind, user_id, ref_id) for each card NAME from the recorded ids of one account (l1 / l2 = the account's
    lexeme ids in recorded order, as G0's names; p1..p5 by their recorded names). Unknown names are refused."""
    lexeme = list(ids.get("lexeme", []))
    personal = ids.get("personal", {})
    out = []
    for name in names:
        if name in ("l1", "l2") and len(lexeme) == 2:
            out.append(("lexeme", ids["user_id"], lexeme[0 if name == "l1" else 1]))
        elif name in personal and name.startswith("p"):
            out.append(("personal", ids["user_id"], personal[name]))
        else:
            raise CheckFailed("harness_defect", f"card name not in the recorded ids: {name}")
    if len(set(out)) != len(out):
        raise CheckFailed("harness_defect", "card names map to repeated keys")
    return out


def key_text(key: tuple[str, int, int]) -> str:
    return f"{key[0]}:{key[1]}:{key[2]}"


def plan_versions(case: Any) -> dict[str, int | None]:
    """Each planned card's version as the INITIAL plan recorded it (before the first apply), by key."""
    return {key_text((c.kind, case.plan.account_id, c.ref_id)): c.card_version for c in case.plan.candidates}


def baseline_problems(case: Any, base: dict, done: int) -> list[str]:
    """The G1 baseline against the initial plan and the contract: the first `done` cards converted once (plan
    version + 1, fsrs) with exactly their snapshots, the rest still at the plan's version (legacy)."""
    planned, problems = plan_versions(case), []
    if len(case.plan.candidates) != len(case.keys) or set(planned) != {key_text(k) for k in case.keys}:
        problems.append("plan cards differ from the case cards")
        return problems
    for i, key in enumerate(case.keys):
        k, now = key_text(key), base["cards"].get(key_text(key))
        if not isinstance(planned[k], int):
            problems.append(f"plan {k}: no card version")
            continue
        want =(planned[k] + 1, "fsrs") if i < done else (planned[k], "legacy")
        if now is None or (now["version"], now["engine"]) != want:
            problems.append(f"baseline {k}: {None if now is None else (now['version'], now['engine'])} != {want}")
    first = {key_text(k) for k in case.keys[:done]}
    if set(base["snapshots"]) != first or base["snapshot_count"] != len(first):
        problems.append(f"baseline snapshots {sorted(base['snapshots'])}")
    return problems


def resume_problems(case: Any, base: dict, now: dict, *, newly: tuple[str, ...], status: str, cursor: int,
                    finished: bool) -> list[str]:
    """Problems of the admin-read state after a resume (empty = as the contract says). Expected values come from
    the G1 baseline, the initial plan and the contract only, never from the run's own output:
    run row: one, `status`, summary cursor `cursor`, finished as given;
    `newly` cards: fsrs, version = plan version + 1, snapshot with card_version_before = plan version;
    every other card: identical to the baseline (version, engine, full row);
    snapshots: the baseline rows unchanged, plus exactly the `newly` keys."""
    keys = dict(zip(case.names, case.keys))
    planned, problems = plan_versions(case), []
    run = (now["runs"], now["status"], now["cursor"], now["finished"])
    if run != (1, status, cursor, finished):
        problems.append(f"run row {run} != {(1, status, cursor, finished)}")
    for name, key in keys.items():
        k = key_text(key)
        before, after = base["cards"].get(k), now["cards"].get(k)
        if before is None or after is None:
            problems.append(f"{name}: card row missing")
        elif name in newly:
            if (after["engine"], after["version"]) != ("fsrs", planned[k] + 1) or after["row"] == before["row"]:
                problems.append(f"{name}: not converted once ({before['version']} -> {after['version']}, "
                                f"{after['engine']})")
        elif after != before:
            problems.append(f"{name}: changed")
    want = set(base["snapshots"]) | {key_text(keys[n]) for n in newly}
    if set(now["snapshots"]) != want or now["snapshot_count"] != len(want):
        problems.append(f"snapshot keys {sorted(now['snapshots'])} ({now['snapshot_count']}) != {sorted(want)}")
    for k, row in base["snapshots"].items():
        if now["snapshots"].get(k) != row:
            problems.append(f"snapshot {k} changed")
    for name in newly:
        k = key_text(keys[name])
        snap = now["snapshots"].get(k)
        if snap is not None and snap["version_before"] != planned[k]:
            problems.append(f"snapshot {k} version_before {snap['version_before']} != {planned[k]}")
    return problems


# --- cases --------------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Case:
    check_id: str
    db: str
    names: tuple[str, ...]
    keys: list
    request: Any
    plan: Any
    plan_path: str
    folder: str
    manifest: bytes
    inquiry: bytes
    a0: bytes
    first_write: Any
    first_read: Any
    initial_evidence: tuple[str, str]
    new_evidence: tuple[str, str]
    read_expected: Any
    write_expected: Any
    read_profile: str
    write_profile: str
    db_identity: str
    dsn: Callable[[str], str]
    common: dict


class Harness:
    def __init__(self, rec: g.Record):
        self.rec = rec
        self.target_bytes = (rec.folder / "target.json").read_bytes()
        self.target = require_target_bound(rec, self.target_bytes)
        self.pid = self.target["postmaster_pid"]
        require_ours(self.target)
        self.keys = None
        self.allowed = None
        self.passwords: dict[str, str] = {}
        self.folders: list[str] = []
        self.evidence: dict = {}
        self.connections: list[Any] = []
        self.cases: dict[str, Case] = {}

    def start(self) -> None:
        self.keys = sigtests.Keys()
        self.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        with admin("postgres", self.pid) as conn:
            for role in BUSINESS_ROLES:
                password = g.new_password()
                conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role),
                                                                        sql.Literal(g.scram_verifier(password))))
                self.passwords[role] = password
        self.rec.event("passwords_rotated_in_memory", roles=list(BUSINESS_ROLES))

    def close(self) -> None:
        for conn in self.connections:
            try:
                conn.close()
            except psycopg.Error:
                pass
        if self.keys is not None:
            self.keys.close()
        for folder in self.folders:
            shutil.rmtree(folder, ignore_errors=True)
        self.passwords = {}

    def close_connections(self) -> None:
        for conn in self.connections:
            try:
                conn.close()
            except psycopg.Error:
                pass

    def sign(self, data: bytes, subject: str) -> bytes:
        return self.keys.sign("signer", oa.signature_namespace("synthetic", subject), data)

    def ca_pem(self) -> bytes:
        return (T.tls / "ca.crt").read_bytes()

    def files(self) -> dict:
        files = {k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"}
        files["ops/tls/root.pem"] = self.ca_pem()
        files[T.target_doc] = self.target_bytes
        return files

    def deploy(self) -> str:
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg67_deploy_"))
        self.folders.append(folder)
        for rel, data in self.files().items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder

    def case(self, check_id: str, names: tuple[str, ...], *, batch: int = 1, account: str = "a") -> Case:
        db = CHECK_DB[check_id]
        ids = self.target["synthetic"][account]
        keys = card_keys(ids, names)
        uid = ids["user_id"]
        req = cli.make_request(uid, RUN_KEY, [r for k, _, r in keys if k == "personal"],
                               [r for k, _, r in keys if k == "lexeme"])
        read_exp, write_exp = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        write_profile = pv.expected_profile_fingerprint(write_exp, role=WRITE, access="write")
        folder = self.deploy()
        manifest = pf.manifest_doc(self.files())                     # one manifest for the first apply AND resume
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        read_step = {"command": "dry_run", "access": "read", "role": READ, "profile": read_profile}
        inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000067",
                       "supersedes": None, "purpose": "synthetic", "alias": "synthetic-primary",
                       "db_identity": db_identity, "manifest": om.manifest_fingerprint(manifest),
                       "tool": "srs_migrate", "steps": [read_step], "accounts": [uid], "max_accounts": 1,
                       "job": {"key": RUN_KEY, "inputs": cli.job_inputs(req)},
                       "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
                       "approved_by": "synthetic signer"}
        inquiry = json.dumps(inquiry_doc).encode()
        root = os.path.join(folder, "ops", "tls", "root.pem")

        def dsn(role):
            return (f"postgresql://{role}:{self.passwords[role]}@{g.HOST}:{T.port}/{db}?sslmode=verify-full"
                    f"&sslrootcert={quote(root, safe='')}")
        common = dict(mode="synthetic", manifest=manifest, manifest_signature=self.sign(manifest, "manifest"),
                      deploy_root=folder, account_id=uid, job_key=RUN_KEY, job_inputs=cli.job_inputs(req),
                      target=target_obs, environment={"PATH": "C:/Windows"},
                      trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=T0)
        inquiry_inputs = op.PreflightInput(approval=inquiry, approval_signature=self.sign(inquiry, "approval"),
                                           command="dry_run", args={}, product_fingerprint=pf.PRODUCT,
                                           connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                           secret_dsn=dsn(READ), **common)
        plan_path = os.path.join(folder, "plan.json")
        counts, trackers = Counts(), []                     # ONE list: the run scope and the driver share it
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            out, code = cli.run_dry_run(req, inputs=inquiry_inputs, expected=read_exp,
                                        driver=self.driver(inquiry_inputs, counts, trackers), out=plan_path)
        expect(code == 0, f"{check_id}: plan dry-run {out.get('code')}", "preparation_failure")
        plan = pfile.read_plan_file(plan_path)
        printed = op.run_synthetic_preflight(dataclasses.replace(
            inquiry_inputs, product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)).job_plan
        ev0 = self.write_evidence(folder, "evidence0", db_identity, uid, "bkp-0000000000000670")
        ev1 = self.write_evidence(folder, "evidence1", db_identity, uid, "bkp-0000000000000671")
        a0_doc = dict(inquiry_doc, kind="apply", approval_id="app-0000000000000670", plan={str(uid): printed},
                      based_on={"approval_id": inquiry_doc["approval_id"], "sha256": sha(inquiry)},
                      steps=[read_step, {"command": "apply", "access": "write", "role": WRITE, "profile": write_profile,
                                         "args": {"batch_size": str(batch)}}],
                      format_version=3, backup_evidence={"sha256": sha(Path(ev0[0]).read_bytes())})
        a0 = json.dumps(a0_doc).encode()
        shared = dict(common, approval=a0, approval_signature=self.sign(a0, "approval"), inquiry=inquiry,
                      inquiry_signature=self.sign(inquiry, "approval"), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256)
        first_write = op.PreflightInput(command="apply", args={"batch_size": str(batch)}, secret_dsn=dsn(WRITE),
                                        connection=op.ConnectionObservation(profile=write_profile, read_only=False),
                                        **shared)
        first_read = op.PreflightInput(command="dry_run", args={}, secret_dsn=dsn(READ),
                                       connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                       **shared)
        return Case(check_id, db, names, keys, req, plan, plan_path, folder, manifest, inquiry, a0, first_write,
                    first_read, ev0, ev1, read_exp, write_exp, read_profile, write_profile, db_identity, dsn, common)

    def write_evidence(self, folder: str, name: str, db_identity: str, uid: int, evidence_id: str) -> tuple[str, str]:
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": evidence_id, "purpose": "synthetic",
               "db_identity": db_identity, "account_id": uid, "job_key": RUN_KEY, "backup_id": "synthetic-backup-67",
               "taken_at": "2026-10-21T12:05:00Z", "method": "synthetic",
               "artifact_sha256": sha(b"synthetic backup"), "valid_until": "2026-10-21T12:50:00Z",
               "attested_by": "synthetic signer", "restore_verified": False}
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        path, sig = os.path.join(folder, name + ".json"), os.path.join(folder, name + ".sig")
        Path(path).write_bytes(data)
        Path(sig).write_bytes(self.sign(data, "backup"))
        return path, sig

    def resume_inputs(self, case: Case, batch: int) -> tuple[Any, Any]:
        doc = json.loads(case.a0)
        doc.pop("backup_evidence", None)
        doc.update(approval_id="app-0000000000000671", format_version=3,
                   supersedes={"approval_id": json.loads(case.a0)["approval_id"], "sha256": sha(case.a0)},
                   steps=[{"command": "status", "access": "read", "role": READ, "profile": case.read_profile},
                          {"command": "resume", "access": "write", "role": WRITE, "profile": case.write_profile,
                           "args": {"batch_size": str(batch)}}])
        an = json.dumps(doc).encode()
        link = op.ChainLink(case.a0, self.sign(case.a0, "approval"), case.inquiry, self.sign(case.inquiry, "approval"))
        shared = dict(case.common, approval=an, approval_signature=self.sign(an, "approval"), inquiry=case.inquiry,
                      inquiry_signature=self.sign(case.inquiry, "approval"),
                      product_fingerprint=case.plan.product_fingerprint, artifact_sha256=case.plan.artifact_sha256,
                      prior_chain=(link,))
        write = op.PreflightInput(command="resume", args={"batch_size": str(batch)}, secret_dsn=case.dsn(WRITE),
                                  connection=op.ConnectionObservation(profile=case.write_profile, read_only=False),
                                  **shared)
        read = op.PreflightInput(command="status", args={}, secret_dsn=case.dsn(READ),
                                 connection=op.ConnectionObservation(profile=case.read_profile, read_only=True), **shared)
        return write, read

    def driver(self, inputs: op.PreflightInput, counts: Counts, trackers: list, hooks: list | None = None):
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder, target=T)

        def connect(**kwargs):
            business_check(kwargs)
            require_ours(self.target)
            conn = guard.driver(**kwargs)
            self.connections.append(conn)
            post_connect_check(conn, self.target, kwargs["user"])
            counts.created[kwargs["user"]] += 1
            tracked = rr.ResumeTracked(conn, counts, kwargs["user"], hooks if hooks is not None else [])
            trackers.append(tracked)
            return tracked
        return connect

    def first_apply(self, case: Case, *, inject=None) -> tuple[dict, int]:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers, inject=inject):
            return cli.run_apply(case.request, batch_size=int(case.first_write.args["batch_size"]),
                                 write_inputs=case.first_write, read_inputs=case.first_read,
                                 scope=cli.ProfileScope(lay.expected_objects(case.db), real.SEARCH_PATH,
                                                        lay.TLS_VERSIONS),
                                 driver=self.driver(case.first_write, counts, trackers), plan_path=case.plan_path,
                                 evidence_path=case.initial_evidence[0],
                                 evidence_signature_path=case.initial_evidence[1], clock=lay.ticking(T0))

    def resume(self, case: Case, batch: int, *, after=None) -> dict:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        values = rr.Values()
        write, read = self.resume_inputs(case, batch)
        with values.installed(), values.named("A"), scopes.installed(), scopes.run(counts, trackers, after=after):
            out, code = cli.run_resume(case.request, batch_size=batch, write_inputs=write, read_inputs=read,
                                       scope=cli.ProfileScope(lay.expected_objects(case.db), real.SEARCH_PATH,
                                                              lay.TLS_VERSIONS),
                                       driver=self.driver(write, counts, trackers), plan_path=case.plan_path,
                                       initial_evidence_path=case.initial_evidence[0],
                                       initial_evidence_signature_path=case.initial_evidence[1],
                                       evidence_path=case.new_evidence[0], evidence_signature_path=case.new_evidence[1],
                                       clock=lay.ticking(T0))
        return {"out": out, "code": code, "counts": counts, "trackers": trackers, "values": values.runs.get("A", {})}

    # -- admin facts (read only) ------------------------------------------------------------------------------
    def facts(self, case: Case) -> dict:
        cards = {"personal": [r for k, _, r in case.keys if k == "personal"],
                 "lexeme": [r for k, _, r in case.keys if k == "lexeme"]}
        with admin(case.db, self.pid) as conn:
            facts = lay.run_facts(conn, RUN_KEY, cards, case.request.account_id)
            row = conn.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = %s",
                               (RUN_KEY,)).fetchone()
            snaps = conn.execute("SELECT s.user_id, s.card_kind, s.card_ref FROM srs_migration_snapshots AS s "
                                 "JOIN srs_migration_runs AS r ON r.id = s.run_id WHERE r.run_key = %s ORDER BY s.id",
                                 (RUN_KEY,)).fetchall()
        facts["summary"] = None if row is None else rr.summary_facts(
            {"status": row[0], "summary_json": row[1], "finished_at": row[2]})
        facts["summary_results"] = [] if row is None or row[1] is None else [
            (r["kind"], r["ref_id"], r["result"]) for r in json.loads(row[1])["results"]]
        facts["snapshot_keys"] = [(kind, user, ref) for user, kind, ref in snaps]
        return facts

    def state(self, case: Case) -> dict:
        """Admin read of one case, by key: the run row (count, status, summary cursor, finished, results), every
        case card's version / engine / full row text and every snapshot row of the run. Values are bound."""
        with admin(case.db, self.pid) as conn:
            runs = conn.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = %s",
                                (RUN_KEY,)).fetchall()
            cards = {}
            for kind, user, ref in case.keys:
                table, column = ("user_word_progress", "lexeme_id") if kind == "lexeme" else ("vocab_items", "id")
                row = conn.execute(sql.SQL(
                    "SELECT t.srs_card_version, t.srs_engine, t::text FROM public.{} AS t "
                    "WHERE t.user_id = %s AND t.{} = %s").format(sql.Identifier(table), sql.Identifier(column)),
                    (user, ref)).fetchone()
                cards[key_text((kind, user, ref))] = None if row is None else {
                    "version": row[0], "engine": row[1], "row": row[2]}
            snaps = conn.execute("SELECT s.card_kind, s.user_id, s.card_ref, s.card_version_before, s::text "
                                 "FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
                                 "WHERE r.run_key = %s ORDER BY s.id", (RUN_KEY,)).fetchall()
        run = rr.summary_facts({"status": runs[0][0], "summary_json": runs[0][1], "finished_at": runs[0][2]}) \
            if len(runs) == 1 else {}
        results = [] if len(runs) != 1 or runs[0][1] is None else [
            (r["kind"], r["ref_id"], r["result"]) for r in json.loads(runs[0][1])["results"]]
        return {"runs": len(runs), "status": run.get("status"), "cursor": run.get("cursor"),
                "finished": run.get("finished"), "results": results, "cards": cards,
                "snapshots": {key_text((k, u, r)): {"version_before": v, "row": text} for k, u, r, v, text in snaps},
                "snapshot_count": len(snaps)}

    def observe_role(self, case: Case, role: str) -> dict:
        """After a revert: ONE connection of `role` through the real adapter and provider (pre-check with
        signatures, observation, judgement, post-connect re-judgement), with its own counts; taken once through the
        public hand-over and closed with no business context. Not the product connector: its normal end commits
        (contract 6-2), and an observation sends no statement and no commit. Never part of the check's run counts."""
        write, read = self.resume_inputs(case, 1)
        inputs, expected, access = ((read, case.read_expected, "read") if role == READ
                                    else (write, case.write_expected, "write"))
        counts, trackers = Counts(), []
        ar.fix_app_environment()                                   # environment only, as the product connector does
        try:
            handoff = ad.provide_with_adapter(dataclasses.replace(inputs, now=lay.ticking(T0)()), expected=expected,
                                              driver=self.driver(inputs, counts, trackers))
            raw = handoff.take()
        except pv.OpsProviderRefused as refused:
            for tracked in trackers:                               # a connection never taken is still closed
                observation_close(tracked)
            return {"result": refused.code, "counts": counts.role(role)}
        expect(len(trackers) == 1 and raw is trackers[0], "one hand-over must follow exactly one connection",
               "harness_defect")
        raw.activate()                                             # from here every statement / commit is counted
        counts.handed[role] += 1
        result = "matches_contract" if handoff.summary.access == access else "connection_access_mismatch"
        if not observation_close(raw):
            result = "connection_close_unconfirmed"
        return {"result": result, "counts": counts.role(role)}

    def card_rows(self, case: Case) -> dict:
        """Each case card's full row text (kind, user, ref -> text)."""
        out = {}
        with admin(case.db, self.pid) as conn:
            for kind, user, ref in case.keys:
                table, column = ("user_word_progress", "lexeme_id") if kind == "lexeme" else ("vocab_items", "id")
                row = conn.execute(sql.SQL("SELECT t::text FROM public.{} AS t WHERE user_id = %s AND {} = %s").format(
                    sql.Identifier(table), sql.Identifier(column)), (user, ref)).fetchone()
                out[f"{kind}:{ref}"] = row[0] if row else None
        return out

    def fixed_values(self, case: Case) -> dict | None:
        """The nine values computed independently on THIS runner's admin connection (contract 9-2)."""
        with admin(case.db, self.pid) as conn:
            row = conn.execute(
                "SELECT id, status, mode, config_version, started_at, finished_at, "
                "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(scope_json, 'UTF8')), 'hex'), "
                "CASE WHEN summary_json IS NULL THEN NULL ELSE "
                "pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(summary_json, 'UTF8')), 'hex') END "
                "FROM srs_migration_runs WHERE run_key = %s", (RUN_KEY,)).fetchone()
            if row is None:
                return None
            snaps = conn.execute("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots "
                                 "WHERE run_id = %s ORDER BY id", (row[0],)).fetchall()
        listed = json.dumps([list(s) for s in snaps], separators=(",", ":"), ensure_ascii=True)
        return {"run_id": row[0], "status": row[1], "mode": row[2], "config_version": row[3], "started_at": row[4],
                "finished_at": row[5], "scope_sha256": row[6], "summary_sha256": row[7],
                "snapshots_sha256": sha(listed.encode("utf-8"))}

    def outside(self, check_id: str, case: Case) -> dict:
        """Rows no run may change, by key: accounts b AND c (every personal card and every progress row, which
        must include their rows for the case's lexemes), every lexeme log, and account a's cards outside the
        case. Account ids are bound, never formatted into the statement."""
        ids = self.target["synthetic"]
        inside = {(k, r) for k, _, r in case.keys}
        case_lexemes = [r for k, _, r in case.keys if k == "lexeme"]
        a_personal = [i for i in ids["a"]["personal"].values() if ("personal", i) not in inside]
        a_lexeme = [i for i in ids["a"]["lexeme"] if ("lexeme", i) not in inside]
        out: dict[str, str] = {}
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for account in OTHER_ACCOUNTS:
                uid = ids[account]["user_id"]
                for ref, text in conn.execute("SELECT id, v::text FROM vocab_items AS v WHERE user_id = %s "
                                              "ORDER BY id", (uid,)).fetchall():
                    out[f"{account}:personal:{ref}"] = text
                for ref, text in conn.execute("SELECT lexeme_id, p::text FROM user_word_progress AS p "
                                              "WHERE user_id = %s ORDER BY lexeme_id", (uid,)).fetchall():
                    out[f"{account}:lexeme:{ref}"] = text
                missing = [r for r in case_lexemes if f"{account}:lexeme:{r}" not in out]
                expect(not missing, f"{check_id}: account {account} has no progress row for lexemes {missing}",
                       "harness_defect")
            uid = ids["a"]["user_id"]
            for ref, text in conn.execute("SELECT id, v::text FROM vocab_items AS v WHERE user_id = %s "
                                          "AND id = ANY (%s) ORDER BY id", (uid, a_personal)).fetchall():
                out[f"a:personal:{ref}"] = text
            for ref, text in conn.execute("SELECT lexeme_id, p::text FROM user_word_progress AS p WHERE user_id = %s "
                                          "AND lexeme_id = ANY (%s) ORDER BY lexeme_id", (uid, a_lexeme)).fetchall():
                out[f"a:lexeme:{ref}"] = text
            for ref, text in conn.execute("SELECT id, l::text FROM lexeme_review_logs AS l ORDER BY id").fetchall():
                out[f"log:{ref}"] = text
        return out

    def sessions(self) -> dict:
        with admin("postgres", self.pid) as conn:
            rows = conn.execute("SELECT usename, state FROM pg_catalog.pg_stat_activity WHERE usename = ANY (%s)",
                                (list(BUSINESS_ROLES),)).fetchall()
        return {"open": len(rows), "idle_in_transaction": sum(1 for r in rows if r[1] == "idle in transaction")}

    def variant(self, check_id: str, name: str, phase: str) -> None:
        expect(LQ3_CHANGES_APPROVED is True, "privilege changes are not approved (LQ3 / L-2)", "harness_defect")
        expect(check_id in LAYOUT.variant_databases[name], "variant outside its check DB", "harness_defect")
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for statement in variant_statements(name, phase):
                conn.execute(statement)
        self.rec.event("privilege_variant", name=name, phase=phase, database=CHECK_DB[check_id])

    def admin_data_change(self, check_id: str, name: str, case: Case) -> None:
        expect(LQ3_CHANGES_APPROVED is True, "admin data changes are not approved (LQ3 / L-2)", "harness_defect")
        statements = ADMIN_DATA[name](self, case)
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for statement, params in statements:
                conn.execute(statement, params)
        self.rec.event("admin_data_change", name=name, database=CHECK_DB[check_id])


def _l2_key(h: Harness, case: Case) -> tuple[str, int, int]:
    return card_keys(h.target["synthetic"]["a"], ("l2",))[0]


# The closed admin row changes (plan 7-3 LQ3): account a loses access to l2 before the resume.
ADMIN_DATA: dict[str, Callable[[Harness, Case], list]] = {
    "subscription_deactivated": lambda h, case: [(
        "UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = %s AND shared_deck_id IN "
        "(SELECT shared_deck_id FROM shared_deck_words WHERE lexeme_id = %s)",
        (case.request.account_id, _l2_key(h, case)[2]))],
    "deck_word_removed": lambda h, case: [(
        "DELETE FROM shared_deck_words WHERE lexeme_id = %s AND shared_deck_id IN (SELECT shared_deck_id FROM "
        "user_deck_subscriptions WHERE user_id = %s)", (_l2_key(h, case)[2], case.request.account_id))],
}


# --- gates (recorded, never counted) --------------------------------------------------------------------------

def g0_gate(h: Harness) -> dict:
    require_ours(h.target)
    with admin("postgres", h.pid) as conn:
        for db, facts in h.target["databases"].items():
            row = conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (db,)).fetchone()
            expect(row is not None and row[0] == facts["oid"], f"{db} OID", "preparation_failure")
    for db, facts in h.target["databases"].items():
        with admin(db, h.pid) as conn:
            ident = [r[0] for r in conn.execute(sql.SQL("SELECT identity_value FROM {}.db_identity").format(
                sql.Identifier(SYN))).fetchall()]
            expect(ident == [facts["identity_value"]], f"{db} identity", "preparation_failure")
    ar.fix_app_environment()
    from app.database import AppPostgresConnection
    from app.srs import migration
    from app.srs.engine import CardKey
    import contextlib
    names = lay.quality_names(h.target["synthetic"]["a"])
    raw = admin(TEMPLATE, h.pid, autocommit=False)
    try:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(LAYOUT.owner)))
        raw.row_factory = dict_row
        app = AppPostgresConnection(raw)

        class Once:
            def __call__(self, *, read_only=False):
                return contextlib.nullcontext(app)
        candidates = migration.dry_run([CardKey(*k) for k in names], connect=Once())
    finally:
        raw.rollback()
        raw.close()
    qualities = lay.name_qualities(candidates, names)
    expect(qualities == lay.EXPECTED_QUALITIES, f"intended qualities {qualities}", "preparation_failure")
    return {"databases": len(h.target["databases"]), "qualities": qualities}


def g1_gate(h: Harness) -> dict:
    """Every check DB's incomplete run made by the REAL first apply (r2-style failure INJECTED for l2)."""
    made = {}
    for check_id, (names, state, batch, cursor) in INITIAL.items():
        case = h.case(check_id, names, batch=batch)
        h.cases[check_id] = case
        before_outside = h.outside(check_id, case)
        scope = rr.expected_scope_md5(case.plan)
        inject = (lambda role, n: role == WRITE and n == 3) if state == "failed" else None
        out, code = h.first_apply(case, inject=inject)
        expect(code == {"started": 3, "failed": 1}[state], f"{check_id} first apply {out.get('code')}/{code}",
               "preparation_failure")
        facts = h.facts(case)
        expect(len(facts["runs"]) == 1 and facts["runs"][0]["status"] == state
               and facts["runs"][0]["scope_md5"] == scope and facts["snapshots"] == cursor
               and facts["summary"]["cursor"] == cursor and facts["snapshot_keys"] == [case.keys[0]],
               f"{check_id} initial state {facts}", "preparation_failure")
        expect(h.outside(check_id, case) == before_outside, f"{check_id} outside rows", "preparation_failure")
        h.evidence.setdefault("outside", {})[check_id] = before_outside
        base = h.state(case)                     # the baseline every later expectation is computed from
        problems = baseline_problems(case, base, cursor)
        expect(not problems and (base["runs"], base["status"], base["cursor"]) == (1, state, cursor),
               f"{check_id} baseline {problems}", "preparation_failure")
        h.evidence.setdefault("baseline", {})[check_id] = base
        made[check_id] = {"state": state, "cursor": cursor, "cards": list(names), "injected": state == "failed"}
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}", "preparation_failure")
    return {"databases": len(made), "states": made}


# --- checks ---------------------------------------------------------------------------------------------------

def outside_kept(h: Harness, check_id: str) -> bool:
    return h.outside(check_id, h.cases[check_id]) == h.evidence["outside"][check_id]


def baseline_of(h: Harness, check_id: str) -> tuple[Case, dict, int]:
    """The case, its G1 baseline (re-checked against the initial plan) and the initial cursor."""
    case = h.cases[check_id]
    base = (h.evidence.get("baseline") or {}).get(check_id)
    expect(base is not None, f"{check_id} needs its G1 baseline", "harness_defect")
    cursor = INITIAL[check_id][3]
    problems = baseline_problems(case, base, cursor)
    expect(not problems, f"{check_id} baseline {problems}", "harness_defect")
    return case, base, cursor


def resumed(h: Harness, check_id: str, batch: int, want_results: dict, want_order: list) -> dict:
    """The CLI result AND the admin-read DB state: run completed / finished / cursor = planned cards, remaining
    cards converted once, the earlier card and its snapshot untouched, new snapshots only for the remaining keys."""
    case, base, cursor = baseline_of(h, check_id)
    admin_values = h.fixed_values(case)
    result = h.resume(case, batch)
    out = result["out"]
    expect((out.get("phase"), result["code"], out.get("results")) == ("completed", 0, want_results), f"{check_id} {out}")
    now = h.state(case)
    keys = dict(zip(case.names, case.keys))
    expect(now["results"] == [(keys[n][0], keys[n][2], res) for n, res in want_order],
           f"{check_id} result order {now['results']}")
    problems = resume_problems(case, base, now, newly=case.names[cursor:], status="completed",
                               cursor=len(case.plan.candidates), finished=True)
    expect(not problems, f"{check_id}: {problems}")
    ok = outside_kept(h, check_id)
    h.evidence.setdefault("outside_ok", {})[check_id] = ok
    expect(ok, f"{check_id}: other-account / out-of-scope rows changed")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"{check_id} sessions {sessions}")
    h.evidence[check_id] = {"values": result["values"], "admin_values": admin_values}
    return {"results": out.get("results"), "read": result["counts"].role(READ), "write": result["counts"].role(WRITE)}


def l1_partial(h: Harness) -> dict:
    return resumed(h, "l1", 2, {"already_applied": 1, "applied": 1},
                   [("l1", "already_applied"), ("l2", "applied")])


def l2_failed(h: Harness) -> dict:
    return resumed(h, "l2", 2, {"already_applied": 1, "applied": 1},
                   [("l1", "already_applied"), ("l2", "applied")])


def l3_mixed(h: Harness) -> dict:
    return resumed(h, "l3", 3, {"already_applied": 1, "applied": 2},
                   [("l1", "already_applied"), ("l2", "applied"), ("p1", "applied")])


def l4_other_accounts(h: Harness) -> dict:
    """Judges the records of L1 / L2 / L3: the other account's rows for the SAME lexemes, every lexeme log and the
    out-of-scope cards stayed as right after G1."""
    seen = h.evidence.get("outside_ok") or {}
    expect(set(seen) == {"l1", "l2", "l3"}, f"l4 needs L1-L3 records {sorted(seen)}", "harness_defect")
    expect(all(seen.values()), f"l4 {seen}")
    return {"checked": sorted(seen)}


def l5_fixed_values(h: Harness) -> dict:
    """Plan 7-4: the three nine-value records of L1 and L2, kept as fixed copies (same format as RS4 r3)."""
    kept: dict = {}
    for name in ("l1", "l2"):
        ev = h.evidence.get(name)
        expect(ev is not None, f"l5 needs {name}'s evidence", "harness_defect")
        values = ev.get("values") or {}
        three = {"pre_read": values.get("pre_read"), "under_lock": values.get("under_lock"),
                 "admin_values": ev.get("admin_values")}
        for key, value in three.items():
            expect(isinstance(value, dict), f"l5 {name} {key} missing", "harness_defect")
            expect(set(value) == rr.NINE_VALUES, f"l5 {name} {key} keys {sorted(value)}", "harness_defect")
        kept[name] = {key: json.loads(json.dumps(value)) for key, value in three.items()}
        expect(three["pre_read"] == three["under_lock"] == three["admin_values"], f"l5 {name}: values differ")
    return {"compared": ["l1", "l2"], "values": kept}


def lost_access(h: Harness, check_id: str, change: str) -> dict:
    """L6 / L7: the l2 CARD is not written at all; the run summary / cursor / completion are written normally."""
    case = h.cases[check_id]
    h.admin_data_change(check_id, change, case)
    before = h.card_rows(case)
    result = h.resume(case, 2)
    out = result["out"]
    expect((out.get("phase"), result["code"], out.get("results"))
           == ("completed", 5, {"already_applied": 1, "conflict": 1}), f"{check_id} {out}")
    expect(h.card_rows(case) == before, f"{check_id}: a card row changed")
    facts = h.facts(case)
    keys = dict(zip(case.names, case.keys))
    expect(facts["snapshot_keys"] == [keys["l1"]], f"{check_id} snapshots {facts['snapshot_keys']}")
    expect([res for _, _, res in facts["summary_results"]] == ["already_applied", "conflict"], f"{check_id} summary")
    expect(facts["runs"][0]["status"] == "completed" and facts["summary"]["cursor"] == 2, f"{check_id} run row")
    expect(outside_kept(h, check_id), f"{check_id}: other-account / out-of-scope rows changed")
    return {"change": change, "write": result["counts"].role(WRITE)}


def l6_subscription_lost(h: Harness) -> dict:
    return lost_access(h, "l6", "subscription_deactivated")


def l7_deck_word_removed(h: Harness) -> dict:
    return lost_access(h, "l7", "deck_word_removed")


def run_outcome(h: Harness, check_id: str, result: dict) -> dict:
    """The CLI's own report of one run, recorded as it was (apart from the admin-read state and the revert)."""
    out = result["out"]
    cli_seen = {"code": out.get("code"), "phase": out.get("phase"), "uncertain": out.get("uncertain"),
                "next": out.get("next"), "exit": result["code"]}
    h.rec.event("check_run", check=check_id, cli=cli_seen)
    return cli_seen


# One provider connection, handed over and closed unused: no product statement, write or commit.
REOBSERVED = {"created": 1, "handed": 1, "statements": 0, "writes": 0, "commits": 0}


def observation_close(conn: Any) -> bool:
    """One close, never retried, no commit or rollback first; closed only when it returned AND the driver
    reports the connection closed. Any failure is "close unconfirmed", never a match."""
    try:
        conn.close()
        return conn.closed is True
    except Exception:
        return False


def revert_and_observe(h: Harness, check_id: str, case: Case, name: str, role: str) -> dict:
    """The closed revert SQL, then the changed role observed AGAIN through the real provider path with its own
    counts. Recorded apart from the check's run; a failed revert, a failed observation or anything but the
    contract profile with no product call / business write is a harness defect (the later checks stop). A
    successful GRANT or a written event alone never counts as a revert."""
    try:
        h.variant(check_id, name, "revert")
    except Exception as error:
        h.rec.event("revert_observation", check=check_id, role=role, result="revert_failed", counts=None)
        raise CheckFailed("harness_defect", f"{check_id}: revert failed: {type(error).__name__}") from None
    try:
        seen = h.observe_role(case, role)
    except Exception as error:
        seen = {"result": f"observation_failed:{type(error).__name__}", "counts": None}
    if not isinstance(seen, dict):
        seen = {"result": "not_observed", "counts": None}
    h.evidence.setdefault("revert_observation", {})[check_id] = seen
    h.rec.event("revert_observation", check=check_id, role=role, result=seen.get("result"),
                counts=seen.get("counts"))
    expect(seen.get("result") == "matches_contract" and seen.get("counts") == REOBSERVED,
           f"{check_id}: after the revert {role} is not the contract profile: {seen}", "harness_defect")
    return seen


def l8_column_revoked_after_l2(h: Harness) -> dict:
    """① l2 (the first remaining card) commits and stays ② the NEXT product connection (p1) is refused by the
    provider observation: created 1, handed 0. The CLI's unconfirmed report (after_start / uncertain /
    status_required) and the admin-read partial state are judged and recorded apart."""
    case, base, cursor = baseline_of(h, "l8")
    applied = {"done": False}

    def after(role, n):
        if role == WRITE and n == 2 and not applied["done"]:
            h.variant("l8", "l8_lexeme_card_column", "apply")
            applied["done"] = True
    try:
        result = h.resume(case, 3, after=after)
        cli_seen = run_outcome(h, "l8", result)
    finally:
        if applied["done"]:
            revert_and_observe(h, "l8", case, "l8_lexeme_card_column", WRITE)
    expect(applied["done"], "l8: the privilege change never ran", "harness_defect")
    expect((cli_seen["code"], cli_seen["phase"], cli_seen["uncertain"], cli_seen["next"], cli_seen["exit"])
           == ("observed_privileges_missing", "after_start", True, "status_required", 1), f"l8 {cli_seen}")
    now = h.state(case)
    admin_state = {k: now[k] for k in ("runs", "status", "cursor", "finished")}
    h.evidence["l8"] = {"cli": cli_seen, "admin_state": admin_state}
    h.rec.event("check_admin_state", check="l8", state=admin_state)
    # contract: l2 committed (cursor + 1), the p1 card error leaves the run `started`, unfinished (the
    # failure-mark connection is refused by the same observation); l1 and p1 as in the baseline
    problems = resume_problems(case, base, now, newly=("l2",), status="started", cursor=cursor + 1, finished=False)
    expect(not problems, f"l8: {problems}")
    write = result["counts"].role(WRITE)
    # created 4 / handed 2: first and l2 handed; p1's connection observed and refused; the product's failure-mark
    # connection (opened after the card error) is refused by the same observation (code: apply_plan except branch)
    expect((write["created"], write["handed"], write["commits"]) == (4, 2, 2), f"l8 write stages {write}")
    expect(outside_kept(h, "l8"), "l8: other-account / out-of-scope rows changed")
    return {"cli": cli_seen, "admin_state": admin_state, "write": write,
            "revert_observation": h.evidence["revert_observation"]["l8"]}


def l9_subscription_read_missing(h: Harness) -> dict:
    case, base, cursor = baseline_of(h, "l9")
    h.variant("l9", "l9_read_subscriptions", "apply")
    try:
        result = h.resume(case, 2)
        cli_seen = run_outcome(h, "l9", result)
    finally:
        revert_and_observe(h, "l9", case, "l9_read_subscriptions", READ)
    expect((cli_seen["code"], cli_seen["phase"], cli_seen["exit"])
           == ("observed_privileges_missing", "before_first_write", 4), f"l9 {cli_seen}")
    read, write = result["counts"].role(READ), result["counts"].role(WRITE)
    expect((read["created"], read["handed"], write["created"]) == (1, 0, 0), f"l9 stages {read} {write}")
    problems = resume_problems(case, base, h.state(case), newly=(), status=INITIAL["l9"][1], cursor=cursor,
                               finished=False)
    expect(not problems, f"l9: {problems}")
    return {"read": read, "write": write, "revert_observation": h.evidence["revert_observation"]["l9"]}


CHECKS: list[tuple[str, Callable[[Harness], dict]]] = [
    ("l1", l1_partial), ("l2", l2_failed), ("l3", l3_mixed), ("l4", l4_other_accounts), ("l5", l5_fixed_values),
    ("l6", l6_subscription_lost), ("l7", l7_deck_word_removed), ("l8", l8_column_revoked_after_l2),
    ("l9", l9_subscription_read_missing),
]


def post_check(h: Harness) -> dict:
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"post sessions {sessions}")
    return {"sessions": sessions}


def check_lexeme() -> tuple[int, dict]:
    """(passed and recorded, summary). Gates and the post-check are never counted; the first failure stops
    everything after it (recorded as not run)."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if LQ3_CHANGES_APPROVED is not True:
        raise CheckFailed("preparation_failure", "LQ3 / L-2 (admin and privilege changes) not approved: nothing runs")
    rec = g.single_run(T)
    h = Harness(rec)
    names = [n for n, _ in CHECKS]
    passed, failed = 0, None
    try:
        h.start()
        rec.event("check_phase_started", phase="lexeme", gates=["g0_gate", "g1_gate"], checks=names, post=POST,
                  note="gates and post-check are not counted; personal-card RS4 results are not added")
        for gate, fn in (("g0_gate", g0_gate), ("g1_gate", g1_gate)):
            if not lay.run_recorded(rec, gate, fn, h):
                failed = gate
                break
        if failed is None:
            for name, fn in CHECKS:
                if not lay.run_recorded(rec, name, fn, h):
                    failed = name
                    break
                passed += 1
        if failed is None and not lay.run_recorded(rec, POST, post_check, h):
            failed = POST
    finally:
        h.close()
    not_run = names[passed + (1 if failed in names else 0):] if failed is not None else []
    if failed is not None:
        try:
            rec.event("not_run", after=failed, checks=not_run)
        except Exception:
            pass
    return passed, {"failed": failed, "not_run": not_run}


def main(argv: list[str]) -> int:
    phase = argv[0] if len(argv) == 1 else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase == "check-lexeme":
            passed, summary = check_lexeme()
            print(f"passed {passed} / {len(PLANNED)}")
            if tuple(n for n, _ in CHECKS) != PLANNED or passed != len(PLANNED) or summary["failed"] is not None:
                print(f"STOP: not all planned checks passed and were recorded (failed: {summary['failed']}, "
                      f"not run: {len(summary['not_run'])})")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check-lexeme | cleanup")
            return 2
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        return 1
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    return 0


if __name__ == "__main__":
    import _ops_resume_lexeme_real as runner                  # the one module object (fake checks can reach it)
    sys.exit(runner.main(sys.argv[1:]))
