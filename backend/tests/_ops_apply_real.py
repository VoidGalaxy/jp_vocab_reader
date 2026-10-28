"""C12 first `apply` on a real local PostgreSQL (OPS_APPLY_REAL_PG_PLAN.md), run explicitly, never by
discovery and never by import:

    python tests/_ops_apply_real.py prepare    # C12-2: pg65 cluster, TLS, roles, template + check DBs, data, grants
    python tests/_ops_apply_real.py check      # C12-3: gate G0 (not counted), then the checklist a1..h1
    python tests/_ops_apply_real.py cleanup    # C12-4: R2, record vs live facts, stop, delete this run only

None of the three phases is approved yet (C12-1 = this code and its PG-free fake checks only).

The target is the closed preset `_ops_pg62.PG65_APPLY` (C:/JV_Tools/pg65, localhost:55492, the template
`jp_vocab_test_apply_tpl` and one database per check); no argument or environment value chooses it.
Only this module and `_ops_pg62` call the real driver: business connections through `Harness.driver`
(provider path, read / write roles, check databases only, never the template) and admin connections
through `admin()` (SSPI, harness only, a closed list of statements). The CLI's command-line `apply` and
the provider's default entry point keep refusing; this runner calls `srs_migrate.run_apply` in Python
with its own guarded driver. Expected privileges come from the contract constants
(`srs_migrate.READ_PRIVILEGES` / `WRITE_PRIVILEGES`) and expected objects from the schema source
(`_ops_audit_real.CORE_TABLES` / `SRS_TABLES`); nothing observed is ever turned into an expectation.

Business-path counting (plan 4-0) is per role: (1) connections created by the guarded driver, (2) handed
to the product (the product connector's context entered), (3) business statements on handed-over
connections, classified by their FIRST WORD only, and COMMIT calls / statements. Supported forms:
`execute()` of a connection or of its cursors with a `str` or a `psycopg.sql` object. This is not an SQL
parser: `executemany`, several statements in one string, server-side functions are not looked into.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable
from unittest import mock
from urllib.parse import quote

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(TESTS_DIR.parent) not in sys.path:      # path only: app is imported after the environment pin
    sys.path.append(str(TESTS_DIR.parent))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_approval as oa  # noqa: E402
import _ops_audit_real as real  # noqa: E402  (schema lists, TLS / server steps, commit word check)
import _ops_real_layout as lay  # noqa: E402  (RS4-1: the closed layouts and shared target-bound helpers)
import _ops_audit_run as ar  # noqa: E402
import _ops_backup_evidence as be  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_pg62_real as base  # noqa: E402  (run, sha, CheckFailed, expect)
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (temporary test key helper only)

LAYOUT = lay.PG65                     # the closed PG65 layout object (RS4-1 split); values unchanged
T = LAYOUT.target
TEMPLATE = LAYOUT.template
CHECK_DB = LAYOUT.check_db
BUSINESS_DATABASES = LAYOUT.business_databases                  # never the template
ADMIN_DATABASES = LAYOUT.admin_databases
ADMIN, OWNER = LAYOUT.admin, LAYOUT.owner
READ, WRITE = LAYOUT.read, LAYOUT.write
BUSINESS_ROLES = LAYOUT.business_roles
SYN = lay.SYN
TLS_VERSIONS = lay.TLS_VERSIONS
WAIT_LIMIT = lay.WAIT_LIMIT           # seconds: contention waits, pauses, thread joins
CheckFailed, expect = base.CheckFailed, base.expect
GATE = "g0_gate"
# Checklist order (plan 4절). b1 reads the evidence of a2 and f2, so it runs after f2; h1 reads all.
PLANNED = ("a1", "a2", "a3", "b2", "b3", "c1", "d1", "d2", "e1", "e2", "e3", "f1", "f2", "f3", "f4", "b1",
           "g1", "g2", "g3", "g4", "h1")


# --- target-free helpers (moved verbatim to _ops_real_layout, same names here) ----------------------------

from _ops_real_layout import (  # noqa: E402,F401
    BUSINESS_TABLES, OID_TABLES, POST_CONNECT, WRITE_WORDS, InjectedFault, Pause, Tracked, TrackedCursor,
    attributed_changes, content_hashes, expected_objects, first_word, grant_statements, race, rejection_stage,
    run_facts, run_recorded, wait_blocked)

VARIANTS, VARIANT_DATABASES = LAYOUT.variants, LAYOUT.variant_databases
# The preset still has the `c1p` check DB (presets are not changed); nothing uses it since the direct
# product probe was removed with the sequence USAGE contract change.


# --- PG65-bound helpers: the shared functions with this runner's layout passed explicitly ------------------

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


class Counts(lay.Counts):
    """One run_apply call: per role, the four stages of plan 4-0 (the fourth is measured in the DB)."""

    def __init__(self):
        super().__init__(BUSINESS_ROLES)


ORIGINAL_CONNECTOR = lay.ORIGINAL_CONNECTOR              # fixed at import, before any patch of this runner


def counted_connector(counts: Counts, trackers: list, inject: Callable[[str, int], bool] | None = None,
                      after: Callable[[str, int], None] | None = None, real: Callable | None = None):
    """The shared counted connector for PG65 (role from the closed step sets: `dry_run` read, `apply` write)."""
    return lay.counted_connector(LAYOUT, counts, trackers, inject, after, real or ORIGINAL_CONNECTOR)


class RunScopes(lay.RunScopes):
    def __init__(self, real: Callable | None = None):
        super().__init__(LAYOUT, real or ORIGINAL_CONNECTOR)



# --- prepare (C12-2; not run without approval) ------------------------------------------------------------

def admin(db: str, pid: int, autocommit: bool = True):
    return lay.admin(LAYOUT, db, pid, autocommit)


def hba() -> str:
    return lay.hba(LAYOUT)


def conf() -> str:
    return lay.conf(LAYOUT)


from _ops_real_layout import SEED, STAMP, synthetic_ids  # noqa: E402,F401  (same data for every layout)


def build_template(pid: int, rec: g.Record) -> dict:
    return lay.build_template(LAYOUT, pid, rec, lambda db, p, autocommit=True: admin(db, p, autocommit))


def prepare() -> None:
    lay.prepare(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit),
                build_fn=lambda p, rec: build_template(p, rec), grants_fn=lambda db: contract_grants(db))



# --- check (C12-3; not run without approval) --------------------------------------------------------------

RUN_KEY = "c12-apply-1"
T0 = sigtests.T0


from _ops_real_layout import ticking  # noqa: E402,F401



@dataclasses.dataclass
class Case:
    check_id: str
    db: str
    account: str
    request: Any
    plan: Any
    write: Any
    read: Any
    evidence: tuple[str, str]
    read_expected: Any
    write_expected: Any
    folder: str
    plan_file: str = "plan.json"
    prep: dict = dataclasses.field(default_factory=dict)  # connections of the plan dry-run that built this case


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
        self.evidence: dict = {}                          # facts later checks (b1, h1) read
        self.connections: list[Any] = []

    def start(self) -> None:
        """Temporary test keys and in-memory passwords (C12-3 only; never at import or in fake checks)."""
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
        self.close_connections()
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

    # -- signed inputs -----------------------------------------------------------------------------------
    def sign(self, data: bytes, subject: str) -> bytes:
        return self.keys.sign("signer", oa.signature_namespace("synthetic", subject), data)

    def ca_pem(self) -> bytes:
        return (T.tls / "ca.crt").read_bytes()

    def deploy(self) -> str:
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg65_deploy_"))
        self.folders.append(folder)
        files = {k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"}
        files["ops/tls/root.pem"] = self.ca_pem()
        files[T.target_doc] = self.target_bytes
        for rel, data in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder

    def cards(self, account: str, personal=("p1", "p2", "p3"), lexeme=True) -> tuple[list, list]:
        ids = self.target["synthetic"][account]
        return [ids["personal"][p] for p in personal], (list(ids["lexeme"]) if lexeme else [])

    def case(self, check_id: str, account: str = "a", *, personal=("p1", "p2", "p3"), lexeme=True, batch=None,
             run_key=RUN_KEY, short=None, evidence_changes=None, plan_db_identity: str | None = None) -> Case:
        db = CHECK_DB[check_id]
        uid = self.target["synthetic"][account]["user_id"]
        p_ids, l_ids = self.cards(account, personal, lexeme)
        req = cli.make_request(uid, run_key, p_ids, l_ids)
        batch = batch or len(p_ids) + len(l_ids)
        read_exp, write_exp = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        write_profile = pv.expected_profile_fingerprint(write_exp, role=WRITE, access="write")
        folder = self.deploy()
        manifest = pf.manifest_doc({**{k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"},
                                    "ops/tls/root.pem": self.ca_pem(),
                                    T.target_doc: self.target_bytes})
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        window = short or {}
        read_step = {"command": "dry_run", "access": "read", "role": READ, "profile": read_profile}
        inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000065",
                       "supersedes": None, "purpose": "synthetic", "alias": "synthetic-primary",
                       "db_identity": db_identity, "manifest": pf.om.manifest_fingerprint(manifest),
                       "tool": "srs_migrate", "steps": [read_step], "accounts": [uid], "max_accounts": 1,
                       "job": {"key": run_key, "inputs": cli.job_inputs(req)},
                       "valid_from": "2026-10-21T12:00:00Z", "valid_until": window.get("valid_until",
                                                                                        "2026-10-21T13:00:00Z"),
                       "approved_by": "synthetic signer"}
        inquiry = json.dumps(inquiry_doc).encode()
        root = os.path.join(folder, "ops", "tls", "root.pem")

        def dsn(role):
            return (f"postgresql://{role}:{self.passwords[role]}@{g.HOST}:{T.port}/{db}?sslmode=verify-full"
                    f"&sslrootcert={quote(root, safe='')}")
        common = dict(mode="synthetic", manifest=manifest, manifest_signature=self.sign(manifest, "manifest"),
                      deploy_root=folder, account_id=uid, job_key=run_key, job_inputs=cli.job_inputs(req),
                      target=target_obs, environment={"PATH": "C:/Windows"},
                      trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=T0)
        inquiry_inputs = op.PreflightInput(approval=inquiry, approval_signature=self.sign(inquiry, "approval"),
                                           command="dry_run", args={}, product_fingerprint=pf.PRODUCT,
                                           connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                           secret_dsn=dsn(READ), **common)
        plan_path = os.path.join(folder, "plan.json")
        prep_counts = Counts()
        out, code = cli.run_dry_run(req, inputs=inquiry_inputs, expected=read_exp,
                                    driver=self.driver(inquiry_inputs, prep_counts, []), out=plan_path)
        prep = {"db": db, "read": prep_counts.created[READ], "write": prep_counts.created[WRITE]}
        expect(code == 0, f"{check_id}: plan dry-run {out.get('code')}", "preparation_failure")
        plan = pfile.read_plan_file(plan_path)
        plan_file = "plan.json"
        if plan_db_identity is not None:
            # d1 plan target: the same plan (account, job, cards, config, product) for another DB's identity,
            # in a NEW file whose bytes the apply approval below binds (artifact hash -> job plan, signed).
            other = CHECK_DB[plan_db_identity]
            other_identity = pf.db_identity(op.TargetObservation(
                host=g.HOST, port=T.port, database=other, server_major=18,
                identity_value=self.target["databases"][other]["identity_value"]))
            data = pfile.serialize_plan(db_identity=other_identity, account_id=plan.account_id, job_key=plan.job_key,
                                        config_version=plan.config_version,
                                        product_fingerprint=plan.product_fingerprint,
                                        candidates=pfile.to_candidates(plan))
            plan_file = "plan_target.json"
            pfile.write_plan_file(os.path.join(folder, plan_file), data)
            plan = pfile.read_plan_file(os.path.join(folder, plan_file))
        printed = op.run_synthetic_preflight(dataclasses.replace(
            inquiry_inputs, product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)).job_plan
        apply_doc = dict(inquiry_doc, kind="apply", approval_id="app-0000000000000065", plan={str(uid): printed},
                         based_on={"approval_id": inquiry_doc["approval_id"],
                                   "sha256": hashlib.sha256(inquiry).hexdigest()},
                         steps=[read_step, {"command": "apply", "access": "write", "role": WRITE,
                                            "profile": write_profile, "args": {"batch_size": str(batch)}}])
        approval = json.dumps(apply_doc).encode()
        shared = dict(common, approval=approval, approval_signature=self.sign(approval, "approval"), inquiry=inquiry,
                      inquiry_signature=self.sign(inquiry, "approval"), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256)
        write = op.PreflightInput(command="apply", args={"batch_size": str(batch)}, secret_dsn=dsn(WRITE),
                                  connection=op.ConnectionObservation(profile=write_profile, read_only=False), **shared)
        read = op.PreflightInput(command="dry_run", args={}, secret_dsn=dsn(READ),
                                 connection=op.ConnectionObservation(profile=read_profile, read_only=True), **shared)
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": "bkp-0000000000000065", "purpose": "synthetic",
               "db_identity": db_identity, "account_id": uid, "job_key": run_key, "backup_id": "synthetic-backup-65",
               "taken_at": "2026-10-21T12:05:00Z", "method": "synthetic",
               "artifact_sha256": hashlib.sha256(b"synthetic backup").hexdigest(),
               "valid_until": "2026-10-21T12:50:00Z", "attested_by": "synthetic signer", "restore_verified": False}
        doc.update(evidence_changes or {})
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        ev, ev_sig = os.path.join(folder, "evidence.json"), os.path.join(folder, "evidence.sig")
        Path(ev).write_bytes(data)
        Path(ev_sig).write_bytes(self.sign(data, "backup"))
        return Case(check_id, db, account, req, plan, write, read, (ev, ev_sig), read_exp, write_exp, folder,
                    plan_file, prep)

    # -- guarded business driver ---------------------------------------------------------------------------
    def driver(self, inputs: op.PreflightInput, counts: Counts, trackers: list, hooks: list | None = None):
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder, target=T)

        def connect(**kwargs):
            business_check(kwargs)                       # this run's matrix first, then the shared guard
            require_ours(self.target)
            conn = guard.driver(**kwargs)
            self.connections.append(conn)
            post_connect_check(conn, self.target, kwargs["user"])
            counts.created[kwargs["user"]] += 1
            tracked = Tracked(conn, counts, kwargs["user"], hooks if hooks is not None else [])
            trackers.append(tracked)
            return tracked
        return connect

    def apply(self, case: Case, *, clock=None, hooks=None, inject=None, after=None,
              plan_path=None) -> tuple[dict, int, Counts]:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers, inject=inject, after=after):
            out, code = run_one(self, case, counts, trackers, hooks, clock, plan_path)
        return out, code, counts

    def observe_write(self, case: Case) -> dict:
        """One write connection through the real provider path (observation + judgement against the
        contract profile), handed over and closed without any business statement."""
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            connect = cli._product_connector(dataclasses.replace(case.write, now=ticking(T0)()), case.write_expected,
                                             self.driver(case.write, counts, trackers))
            try:
                with connect(read_only=False):
                    pass
            except cli.pc.OpsProductConnectionError as error:
                return {"observation": error.code, "handed": counts.handed[WRITE], "statements": 0}
        role = counts.role(WRITE)
        return {"observation": "matches_contract", "handed": role["handed"], "statements": role["statements"]}

    def apply_traced(self, case: Case) -> dict:
        """One refused run with a call trace: which CLI checks ran, in order, with their outcome; plus the
        stage counts and product calls. The wrapped functions are the real ones, called unchanged."""
        trace: list = []
        real_pre, real_ev = cli.op.run_synthetic_preflight, cli.be.verify_backup_evidence

        def pre(inputs):
            try:
                result = real_pre(inputs)
            except op.OpsPreflightRefused as error:
                trace.append(["preflight", inputs.command, error.code])
                raise
            trace.append(["preflight", inputs.command, "ok"])
            return result

        def evidence(*args, **kwargs):
            try:
                result = real_ev(*args, **kwargs)
            except be.OpsBackupEvidenceRefused as error:
                trace.append(["evidence", "-", error.code])
                raise
            trace.append(["evidence", "-", "ok"])
            return result
        ar.fix_app_environment()
        from app.srs import migration
        product = {"calls": 0}

        def counted(fn):
            def call(*a, **k):
                product["calls"] += 1
                return fn(*a, **k)
            return call
        with mock.patch.object(cli.op, "run_synthetic_preflight", pre), \
                mock.patch.object(cli.be, "verify_backup_evidence", evidence), \
                mock.patch.object(migration, "dry_run", counted(migration.dry_run)), \
                mock.patch.object(migration, "apply_plan", counted(migration.apply_plan)):
            out, code, counts = self.apply(case)
        return {"code": out.get("code"), "exit": code,
                "connections": {"read": counts.created[READ], "write": counts.created[WRITE]},
                "handed": {"read": counts.handed[READ], "write": counts.handed[WRITE]},
                "product_calls": product["calls"], "trace": trace}

    # -- admin facts -------------------------------------------------------------------------------------------
    def hashes(self, check_id: str) -> dict:
        with admin(CHECK_DB[check_id], self.pid) as conn:
            return content_hashes(conn)

    def facts(self, case: Case) -> dict:
        with admin(case.db, self.pid) as conn:
            cards = {"personal": [ref for kind, ref in case.request.cards if kind == "personal"],
                     "lexeme": [ref for kind, ref in case.request.cards if kind == "lexeme"]}
            return run_facts(conn, case.request.run_key, cards, case.request.account_id)

    def variant(self, name: str, phase: str) -> None:
        for check_id in VARIANT_DATABASES[name]:
            with admin(CHECK_DB[check_id], self.pid) as conn:
                for statement in variant_statements(name, phase):
                    conn.execute(statement)
        self.rec.event("privilege_variant", name=name, phase=phase)

    def with_variant(self, name: str, fn: Callable[[], Any]) -> Any:
        """Apply, run, revert; the revert is verified by a normal provider observation afterwards."""
        self.variant(name, "apply")
        try:
            return fn()
        finally:
            try:
                self.variant(name, "revert")
            except Exception as error:
                raise CheckFailed("harness_defect", f"revert failed: {type(error).__name__}") from None

    def outside(self, check_id: str) -> list:
        """Rows that no run of this checklist may change: account b's cards and account a's p5."""
        ids = self.target["synthetic"]
        with admin(CHECK_DB[check_id], self.pid) as conn:
            personal = conn.execute("SELECT v::text FROM vocab_items AS v WHERE user_id = %s OR id = %s ORDER BY id",
                                    (ids["b"]["user_id"], ids["a"]["personal"]["p5"])).fetchall()
            lexeme = conn.execute("SELECT p::text FROM user_word_progress AS p WHERE user_id = %s ORDER BY id",
                                  (ids["b"]["user_id"],)).fetchall()
        return [r[0] for r in personal + lexeme]

    def sessions(self) -> dict:
        with admin("postgres", self.pid) as conn:
            rows = conn.execute("SELECT usename, state FROM pg_catalog.pg_stat_activity WHERE usename = ANY (%s)",
                                (list(BUSINESS_ROLES),)).fetchall()
        return {"open": len(rows), "idle_in_transaction": sum(1 for r in rows if r[1] == "idle in transaction")}

    def blocking(self, pid: int) -> list:
        with admin("postgres", self.pid) as conn:
            return list(conn.execute("SELECT pg_catalog.pg_blocking_pids(%s)", (pid,)).fetchone()[0] or [])

    def waits(self, pid: int) -> list:
        with admin("postgres", self.pid) as conn:
            return [dict(zip(("locktype", "mode", "granted"), r)) for r in conn.execute(
                "SELECT locktype, mode, granted FROM pg_catalog.pg_locks WHERE pid = %s AND NOT granted", (pid,))]


def run_one(h: Any, case: Any, counts: Counts, trackers: list, hooks: list | None, clock=None, plan_path=None):
    """One CLI run_apply inside the caller's run scope (the scope gives this run its own counting)."""
    return cli.run_apply(case.request, batch_size=int(case.write.args["batch_size"]),
                         write_inputs=case.write, read_inputs=case.read,
                         scope=cli.ProfileScope(expected_objects(case.db), real.SEARCH_PATH, TLS_VERSIONS),
                         driver=h.driver(case.write, counts, trackers, hooks),
                         plan_path=plan_path or os.path.join(case.folder, case.plan_file),
                         evidence_path=case.evidence[0], evidence_signature_path=case.evidence[1],
                         clock=clock or ticking(T0))


def expect_refused(out: dict, code: int, reason: str, counts: Counts, write_stage: str, read_stage: str | None = None):
    expect((out.get("code"), code) == (reason, 4), f"expected {reason}/4, got {out.get('code')}/{code}")
    expect(rejection_stage(counts.role(WRITE)) == write_stage, f"write stage {counts.role(WRITE)}")
    if read_stage is not None:
        expect(rejection_stage(counts.role(READ)) == read_stage, f"read stage {counts.role(READ)}")


def unchanged(h: Harness, check_id: str, before: dict) -> None:
    expect(h.hashes(check_id) == before, "rows changed")


def a1_profiles(h: Harness) -> dict:
    case = h.case("a1", personal=("p1",), lexeme=False)
    out, code, counts = h.apply(case)
    expect((out.get("phase"), code) == ("completed", 0), f"a1 {out.get('code')}/{code}")
    expect(counts.role(READ)["handed"] == 1 and counts.role(WRITE)["handed"] >= 1, "both profiles accepted")
    with admin(case.db, h.pid) as conn:
        usage = {s: conn.execute("SELECT pg_catalog.has_sequence_privilege(%s, %s, 'USAGE')",
                                 (WRITE, f"public.{s}")).fetchone()[0]
                 for s in ("srs_migration_runs_id_seq", "srs_migration_snapshots_id_seq")}
    expect(not any(usage.values()), f"write role sequence USAGE {usage}")
    return {"read": counts.role(READ), "write": counts.role(WRITE), "write_sequence_usage": usage}


def a2_personal_and_lexeme(h: Harness) -> dict:
    case = h.case("a2")
    outside = h.outside("a2")
    out, code, counts = h.apply(case)
    expect((out.get("phase"), code, out.get("results")) == ("completed", 0, {"applied": 5}), f"a2 {out}")
    facts = h.facts(case)
    expect([r["status"] for r in facts["runs"]] == ["completed"] and facts["snapshots"] == 5, "run row and snapshots")
    # every write connection's first statement is the product lock; a completed run means each returned
    h.evidence["a2"] = {"lock_statements_ok": True, "write": counts.role(WRITE)}
    h.evidence["outside"] = {"a2": h.outside("a2") == outside}
    return {"write": counts.role(WRITE), "read": counts.role(READ)}


def a3_blocked_intro(h: Harness) -> dict:
    case = h.case("a3", personal=("p1", "p4"), lexeme=False)
    out, code, _ = h.apply(case)
    expect((out.get("phase"), code) == ("completed", 5) and out.get("results", {}).get("blocked") == 1, f"a3 {out}")
    with admin(case.db, h.pid) as conn:
        row = conn.execute("SELECT history_intro_status, srs_engine FROM vocab_items WHERE id = %s",
                           (h.target["synthetic"]["a"]["personal"]["p4"],)).fetchone()
    expect(row[0] is not None and row[1] != "fsrs", "blocked card: intro recorded, not converted")
    return {"intro_status": row[0]}


def b2_lock_privilege_missing(h: Harness) -> dict:
    case = h.case("b2")
    before = h.hashes("b2")

    def run():
        out, code, counts = h.apply(case)
        probe = lock_probe(h, case)
        return out, code, counts, probe
    out, code, counts, probe = h.with_variant("b2_lock_column", run)
    expect_refused(out, code, "observed_privileges_missing", counts, "after_observation")
    expect(probe == "42501", f"direct lock probe {probe}")
    unchanged(h, "b2", before)
    return {"write": counts.role(WRITE), "probe": probe}


def lock_probe(h: Harness, case: Case) -> str:
    """Harness-only direct execution of the product's lock statement as the write role (not the CLI path)."""
    kwargs = {"host": g.HOST, "port": str(T.port), "dbname": case.db, "user": WRITE, "password": h.passwords[WRITE],
              "sslmode": "verify-full", "sslrootcert": str(T.tls / "ca.crt"), "gssencmode": "disable"}
    business_check(kwargs)
    require_ours(h.target)
    with psycopg.connect(**kwargs) as conn:
        post_connect_check(conn, h.target, WRITE)
        try:
            conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (case.request.account_id,))
            conn.rollback()
            return "ok"
        except psycopg.Error as error:
            conn.rollback()
            return error.sqlstate or "unknown"


def b3_excess(h: Harness) -> dict:
    before = h.hashes("b3")
    seen = {}
    for name in ("b3_users_table", "b3_users_email", "b3_card_column"):
        case = h.case("b3")
        out, code, counts = h.with_variant(name, lambda: h.apply(case))
        expect_refused(out, code, "observed_privileges_excess", counts, "after_observation")
        seen[name] = counts.role(WRITE)
    unchanged(h, "b3", before)
    return seen


def c1_sequences(h: Harness) -> dict:
    """Full check c1 and check-seq s1 (one judgement): with both sequence USAGE privileges granted for a
    moment, the write connection must be refused exactly as excess after its observation (no hand-over,
    no business statement, rows unchanged); after the revoke, a write observation must match the contract."""
    case = h.case("c1")
    before = h.hashes("c1")
    with admin(case.db, h.pid) as conn:
        identity = {t: conn.execute("SELECT attidentity FROM pg_catalog.pg_attribute WHERE attrelid = %s::regclass "
                                    "AND attname = 'id'", (f"public.{t}",)).fetchone()[0]
                    for t in ("srs_migration_runs", "srs_migration_snapshots")}
    out, code, counts = h.with_variant("c1_sequences", lambda: h.apply(case))
    write = counts.role(WRITE)
    expect((out.get("code"), code) == ("observed_privileges_excess", 4),
           f"granted sequence USAGE: expected observed_privileges_excess/4, got {out.get('code')}/{code}")
    expect(rejection_stage(write) == "after_observation" and write["statements"] == 0,
           f"granted sequence USAGE: write {write}")
    unchanged(h, "c1", before)
    revert = h.observe_write(case)
    expect(revert == {"observation": "matches_contract", "handed": 1, "statements": 0},
           f"after the revoke: {revert}", "harness_defect")
    return {"attidentity": identity,
            "granted_usage": {"code": out.get("code"), "exit": code, "write": write, "read": counts.role(READ)},
            "revert": revert}


def tampered_case(case: Case) -> Case:
    """The SAME changed approval bytes on both inputs (so the inputs still agree), original signatures kept."""
    changed = case.write.approval + b" "
    return dataclasses.replace(case, write=dataclasses.replace(case.write, approval=changed),
                               read=dataclasses.replace(case.read, approval=changed))


PRE_OK = [["preflight", "apply", "ok"], ["preflight", "dry_run", "ok"]]


def expect_d1(name: str, sub: dict, code: str, trace: list) -> None:
    """Exactly this refusal, reached through exactly these checks; nothing connected or called."""
    expect(sub["code"] == code, f"d1 {name}: expected {code}, got {sub['code']}")
    expect(sub["trace"] == trace, f"d1 {name}: checks run {sub['trace']}")
    expect((sub["exit"], sub["connections"], sub["handed"], sub["product_calls"])
           == (4, {"read": 0, "write": 0}, {"read": 0, "write": 0}, 0), f"d1 {name}: {sub}")


def d1_mismatches(h: Harness) -> dict:
    """CLI judgements before any connection. Each case must pass the checks before its target and stop
    exactly there (call trace); an earlier or other refusal fails d1."""
    before = h.hashes("d1")
    h.evidence["d1_before"] = before
    seen = {}
    other = retarget(h.case("d2"), "d1")          # plan + approvals built on d2 (one read there), aimed at d1
    seen["other_db_approval"] = dict(h.apply_traced(other), prep=other.prep)
    expect_d1("other_db_approval", seen["other_db_approval"], "preflight_db_identity_not_approved",
              [["preflight", "apply", "db_identity_not_approved"]])
    tampered = tampered_case(h.case("d1"))
    seen["tampered"] = dict(h.apply_traced(tampered), prep=tampered.prep)
    expect_d1("tampered", seen["tampered"], "preflight_approval_signature_invalid",
              [["preflight", "apply", "approval_signature_invalid"]])
    target = h.case("d1", plan_db_identity="d2")   # valid approvals; plan file with d2's identity (no d2 read)
    seen["plan_target"] = dict(h.apply_traced(target), prep=target.prep)
    expect_d1("plan_target", seen["plan_target"], "plan_file_target_mismatch", PRE_OK)
    wrong = h.case("d1", evidence_changes={"account_id": h.target["synthetic"]["b"]["user_id"]})
    seen["evidence_account"] = dict(h.apply_traced(wrong), prep=wrong.prep)
    expect_d1("evidence_account", seen["evidence_account"], "backup_evidence_account_mismatch",
              PRE_OK + [["evidence", "-", "backup_evidence_account_mismatch"]])
    unchanged(h, "d1", before)
    return seen


def retarget(case: Case, check_id: str) -> Case:
    """The same signed inputs, aimed at another check DB (connection string and target observation only)."""
    db = CHECK_DB[check_id]

    def move(inputs):
        return dataclasses.replace(inputs, secret_dsn=inputs.secret_dsn.replace(f"/{case.db}?", f"/{db}?"),
                                   target=dataclasses.replace(inputs.target, database=db))
    return dataclasses.replace(case, db=db, write=move(case.write), read=move(case.read))


def d2_plan_changed(h: Harness) -> dict:
    case = h.case("d2")
    with admin(case.db, h.pid) as conn:                                # the approved admin change, recorded
        conn.execute("UPDATE vocab_items SET correct_count = correct_count + 1 WHERE id = %s",
                     (h.target["synthetic"]["a"]["personal"]["p2"],))
    h.rec.event("admin_change", check="d2", what="vocab_items.correct_count +1 on card p2")
    before = h.hashes("d2")                                            # baseline after the admin change
    out, code, counts = h.apply(case)
    expect_refused(out, code, "plan_changed", counts, "before_connect")
    expect(counts.role(READ)["handed"] == 1, "one read hand-over")
    unchanged(h, "d2", before)
    return {"read": counts.role(READ)}


SHORT = {"valid_until": "2026-10-21T12:40:00Z"}


def e1_expiries(h: Harness) -> dict:
    from datetime import datetime, timezone
    expired = datetime(2026, 10, 21, 12, 40, tzinfo=timezone.utc)
    before = h.hashes("e1")
    case = h.case("e1", short=SHORT)
    out, code, counts = h.apply(case, clock=lambda: expired)
    expect_refused(out, code, "preflight_approval_expired", counts, "before_connect", "before_connect")
    first = counts.role(READ)
    case = h.case("e1", short=SHORT)
    with after_dry_run(expired) as clock:
        out, code, counts = h.apply(case, clock=clock)
    expect_refused(out, code, "preflight_approval_expired", counts, "before_connect")
    expect(counts.role(READ)["handed"] == 1, "approval expired after the real dry_run")
    evidence_end = datetime(2026, 10, 21, 12, 50, tzinfo=timezone.utc)   # approval (13:00) still valid
    case = h.case("e1")
    with after_dry_run(evidence_end) as clock:
        out, code, counts = h.apply(case, clock=clock)
    expect_refused(out, code, "backup_evidence_expired", counts, "before_connect")
    unchanged(h, "e1", before)
    return {"before_start": first}


@contextlib.contextmanager
def after_dry_run(later):
    """A clock at T0 until the REAL product dry_run has returned, then `later` (the product result is
    passed through unchanged; only its completion is noted)."""
    ar.fix_app_environment()
    from app.srs import migration
    real_dry_run, state = migration.dry_run, {"done": 0}

    def wrapped(*args, **kwargs):
        result = real_dry_run(*args, **kwargs)
        state["done"] += 1
        return result
    with mock.patch.object(migration, "dry_run", wrapped):
        yield lambda: later if state["done"] else T0


def e2_times(h: Harness) -> dict:
    seen = []
    real_pre = pv.op.run_synthetic_preflight

    def spy(inputs):
        seen.append(inputs.now)
        return real_pre(inputs)
    case = h.case("e2")                                               # its own plan dry-run is not counted
    with mock.patch.object(pv.op, "run_synthetic_preflight", spy):
        out, code, counts = h.apply(case, clock=ticking(T0))
    expect((out.get("phase"), code) == ("completed", 0), f"e2 {out.get('code')}")
    connections = counts.role(READ)["created"] + counts.role(WRITE)["created"]
    provider = seen[-connections:] if connections else []
    expect(len(set(provider)) == len(provider) == connections and provider == sorted(provider)
           and all(t > T0 for t in seen), "a new, increasing time per connection request")
    return {"connections": connections}


def e3_expiry_after_start(h: Harness) -> dict:
    from datetime import datetime, timezone
    expired = datetime(2026, 10, 21, 12, 40, tzinfo=timezone.utc)
    case = h.case("e3", short=SHORT)
    state = {"now": T0}

    def after(role, n):                     # not a fault: card 1's connection ended; card 2's request is next
        if role == WRITE and n == 2:
            state["now"] = expired
    out, code, _ = h.apply(case, clock=lambda: state["now"], after=after)
    expect((out.get("code"), out.get("phase"), out.get("uncertain"), code)
           == ("preflight_approval_expired", "after_start", True, 1), f"e3 {out}")
    facts = h.facts(case)
    expect(facts["snapshots"] == 1, "card 1 stays committed, card 2 refused")
    return {"snapshots": facts["snapshots"]}


def f1_existing_key(h: Harness) -> dict:
    other = h.case("f1", personal=("p3",), lexeme=False)
    out, code, _ = h.apply(other)
    expect(code == 0, "first run with the key")
    case = h.case("f1", personal=("p1", "p2"), lexeme=False)
    before = h.hashes("f1")
    out, code, counts = h.apply(case)
    expect_refused(out, code, "migration_run_exists", counts, "under_product_lock")
    unchanged(h, "f1", before)
    return {"write": counts.role(WRITE)}


LOCK_PREFIX = "SELECT id FROM users WHERE id = "
RUN_INSERT_PREFIX = "INSERT INTO srs_migration_runs "


def contention(h: Harness, check_id: str, first: Case, second: Case, pause: Pause) -> tuple:
    trackers_b: list = []
    counts_a, counts_b = Counts(), Counts()

    scopes = RunScopes()                     # installed once for the whole race; one run scope per thread

    def run(case, counts, trackers, hooks):
        with scopes.run(counts, trackers):
            return run_one(h, case, counts, trackers, hooks)

    def prove():
        waiter = wait_blocked(h.blocking, lambda: trackers_b[-1].pending_pid if trackers_b else None, pause.holder_pid)
        return {"holder": "A", "waiter": "B", "blocking_contains_holder": True, "waits": h.waits(waiter)}
    before = (h.facts(first), h.facts(second))
    with scopes.installed():
        a, b, proof = race(lambda: run(first, counts_a, [], [pause.hook]),
                           lambda: run(second, counts_b, trackers_b, []), pause, prove, h.close_connections)
    return a, b, proof, counts_a, counts_b, before


def expected_scope_md5(plan: Any) -> str:
    """What the product will store as the run's scope_json for this plan file (`apply_plan` stores
    `_plan_json(plan)`), hashed as PostgreSQL `md5(text)` hashes it (UTF-8). Computed BEFORE the run."""
    ar.fix_app_environment()
    from app.srs import migration
    return hashlib.md5(migration._plan_json(list(pfile.to_candidates(plan))).encode("utf-8")).hexdigest()


def f2_same_account(h: Harness) -> dict:
    first, second = h.case("f2"), h.case("f2")
    scope = expected_scope_md5(first.plan)                # A's original plan, fixed before the race
    pause = Pause(WRITE, "SELECT", LOCK_PREFIX)
    (out_a, code_a), (out_b, code_b), proof, counts_a, counts_b, (before, _) = contention(h, "f2", first, second,
                                                                                            pause)
    expect(code_a == 0, f"A {out_a.get('code')}")
    expect((out_b.get("code"), code_b) == ("migration_run_exists", 4), f"B {out_b.get('code')}/{code_b}")
    expect(rejection_stage(counts_b.role(WRITE)) == "under_product_lock", f"B stage {counts_b.role(WRITE)}")
    after = h.facts(first)
    problems = attributed_changes(before, after, winner_applied=out_a["results"].get("applied", 0),
                                  winner_scope=scope,
                                  refused_commits=counts_b.role(WRITE)["commits"])
    expect(problems == [], f"changes attributed to B: {problems}")
    h.evidence["f2"] = proof
    return {"proof": proof, "b_write": counts_b.role(WRITE)}


def f3_preliminary(h: Harness) -> dict:
    first = h.case("f3")
    second = h.case("f3", run_key="c12-apply-2")       # B's plan file and approvals, made BEFORE A writes
    out, code, _ = h.apply(first)
    expect(code == 0, "A applied")
    out, code, counts = h.apply(second)                 # B's original (now stale) plan, never rebuilt
    expect_refused(out, code, "plan_changed", counts, "before_connect")
    return {"b_write": counts.role(WRITE)}


def f4_other_account(h: Harness) -> dict:
    first, second = h.case("f4", "a"), h.case("f4", "c")
    pause = Pause(WRITE, "INSERT", RUN_INSERT_PREFIX)
    (out_a, code_a), (out_c, code_c), proof, counts_a, counts_c, (_, before_c) = contention(h, "f4", first, second,
                                                                                               pause)
    expect(code_a == 0, f"A {out_a.get('code')}")
    expect((out_c.get("code"), out_c.get("phase"), out_c.get("uncertain"), code_c)
           == ("apply_failed", "first_connection", True, 1), f"C {out_c}")
    expect(rejection_stage(counts_c.role(WRITE)) == "rolled_back_after_write", f"C stage {counts_c.role(WRITE)}")
    c_after = h.facts(second)
    expect(c_after["versions"] == before_c["versions"], "C's cards unchanged")
    expect(len(c_after["runs"]) == 1 and counts_c.role(WRITE)["commits"] == 0, "the one run row is A's; C committed 0")
    return {"proof": proof, "c_write": counts_c.role(WRITE)}


def b1_lock_sufficient(h: Harness) -> dict:
    expect("a2" in h.evidence and "f2" in h.evidence, "a2 and f2 evidence present", "harness_defect")
    return {"lock_with_contract_privileges": h.evidence["a2"]["lock_statements_ok"], "wait_proof": h.evidence["f2"]}


def g1_partial(h: Harness) -> dict:
    case = h.case("g1", lexeme=False, batch=1)
    out, code, _ = h.apply(case)
    expect((out.get("phase"), out.get("cursor"), code) == ("partial", 1, 3), f"g1 {out}")
    facts = h.facts(case)
    expect([r["status"] for r in facts["runs"]] == ["started"] and facts["snapshots"] == 1, "g1 rows")
    return {"cursor": 1}


def g2_revoked_between_cards(h: Harness) -> dict:
    case = h.case("g2", lexeme=False)
    state = {"done": False}

    def after(role, n):                      # a REAL privilege change once card 1's connection ended
        if role == WRITE and n == 2 and not state["done"]:
            h.variant("g2_card_column", "apply")
            state["done"] = True
    try:
        out, code, _ = h.apply(case, after=after)
    finally:
        if state["done"]:
            h.variant("g2_card_column", "revert")
    expect((out.get("phase"), code) == ("after_start", 1), f"g2 {out}")
    expect(h.facts(case)["snapshots"] == 1, "card 1 stays committed, card 2 refused")
    return {"code": out.get("code")}


def g3_injected_card_failure(h: Harness) -> dict:
    case = h.case("g3", lexeme=False)
    outside = h.outside("g3")
    out, code, _ = h.apply(case, inject=lambda role, n: role == WRITE and n == 3)
    h.evidence.setdefault("outside", {})["g3"] = h.outside("g3") == outside
    expect((out.get("phase"), out.get("uncertain"), code) == ("after_start", True, 1), f"g3 {out}")
    facts = h.facts(case)
    expect(facts["snapshots"] == 1 and [r["status"] for r in facts["runs"]] == ["failed"], "g3 rows")
    return {"injected": True}


def g4_injected_final_failure(h: Harness) -> dict:
    case = h.case("g4", lexeme=False)
    out, code, _ = h.apply(case, inject=lambda role, n: role == WRITE and n == 5)
    expect((out.get("uncertain"), code) == (True, 1), f"g4 {out}")
    facts = h.facts(case)
    expect(facts["snapshots"] == 3 and [r["status"] for r in facts["runs"]] == ["started"], "g4 rows")
    return {"injected": True}


def h1_untouched_and_sessions(h: Harness) -> dict:
    outside = h.evidence.get("outside", {})
    expect(set(outside) == {"a2", "g3"} and all(outside.values()), f"outside rows {outside}")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}")
    return {"outside": outside, **sessions}


CHECKS: list[tuple[str, Callable[[Harness], dict]]] = [
    ("a1", a1_profiles), ("a2", a2_personal_and_lexeme), ("a3", a3_blocked_intro), ("b2", b2_lock_privilege_missing),
    ("b3", b3_excess), ("c1", c1_sequences), ("d1", d1_mismatches), ("d2", d2_plan_changed), ("e1", e1_expiries),
    ("e2", e2_times), ("e3", e3_expiry_after_start), ("f1", f1_existing_key), ("f2", f2_same_account),
    ("f3", f3_preliminary), ("f4", f4_other_account), ("b1", b1_lock_sufficient), ("g1", g1_partial),
    ("g2", g2_revoked_between_cards), ("g3", g3_injected_card_failure), ("g4", g4_injected_final_failure),
    ("h1", h1_untouched_and_sessions)]


def g0_gate(h: Harness) -> dict:
    """Preparation gate (not counted): live facts, every check DB's OID / identity, intended qualities."""
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
    qualities = template_qualities(h)
    expect(qualities == EXPECTED_QUALITIES, f"intended qualities {qualities}", "preparation_failure")
    return {"databases": len(h.target["databases"]), "qualities": qualities}


from _ops_real_layout import EXPECTED_QUALITIES, name_qualities, quality_label, quality_names  # noqa: E402,F401



def template_qualities(h: Harness) -> dict:
    """The product dry_run on the template as the owner role (admin connection, read only)."""
    ar.fix_app_environment()
    from app.database import AppPostgresConnection
    from app.srs import migration
    from app.srs.engine import CardKey
    names = quality_names(h.target["synthetic"]["a"])
    keys = [CardKey(kind, user, ref) for kind, user, ref in names]
    raw = admin(TEMPLATE, h.pid, autocommit=False)
    try:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        raw.row_factory = dict_row
        app = AppPostgresConnection(raw)

        class Once:
            def __call__(self, *, read_only=False):
                return _Borrowed(app)
        candidates = migration.dry_run(keys, connect=Once())
    finally:
        raw.rollback()
        raw.close()
    return name_qualities(candidates, names)


class _Borrowed:
    def __init__(self, app):
        self.app = app

    def __enter__(self):
        return self.app

    def __exit__(self, *_):
        return False


def check() -> int:
    """Returns the number of checks that passed and were recorded; the gate is never counted."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    h = Harness(rec)
    passed = 0
    try:
        h.start()
        rec.event("check_phase_started", gate=GATE, checks=[n for n, _ in CHECKS])
        if not run_recorded(rec, GATE, g0_gate, h):
            return 0
        for name, fn in CHECKS:
            if not run_recorded(rec, name, fn, h):
                return passed                                  # nothing after a failure runs
            passed += 1
    finally:
        h.close()
    return passed


# --- d1 supplement run (fixed scope; not run without approval) ---------------------------------------------
# G0 -> a2 (representative normal first apply) -> d1 (four refusal paths) -> d1_post. Only a2 and d1 count.
# Nothing here is selectable from the command line or the environment.

SUPPLEMENT_KIND = "supplement_d1"
SUPPLEMENT_PLANNED = ("a2", "d1")
SUPPLEMENT_POST = "d1_post"


def supplement_checks() -> list:
    return [("a2", a2_personal_and_lexeme), ("d1", d1_mismatches)]   # looked up at call time, order fixed


def d1_post(h: Harness) -> dict:
    """Required after the supplement (recorded, never counted): a2 left other accounts' / out-of-scope rows
    alone, d1's database is exactly as before d1, no business session is left open or idle in a transaction.
    h1 of the full checklist keeps its own, stricter expectation."""
    outside = h.evidence.get("outside", {})
    expect(outside.get("a2") is True, f"outside rows after a2 {outside}")
    expect("d1_before" in h.evidence, "d1 baseline present", "harness_defect")
    expect(h.hashes("d1") == h.evidence["d1_before"], "d1 database changed")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}")
    return {"outside_a2": True, "d1_unchanged": True, **sessions}


def check_d1() -> tuple[int, bool]:
    """(checks passed and recorded, post-check passed and recorded). The gate is never counted."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    h = Harness(rec)
    passed = 0
    try:
        h.start()
        rec.event("check_phase_started", phase=SUPPLEMENT_KIND, gate=GATE, checks=list(SUPPLEMENT_PLANNED),
                  post=SUPPLEMENT_POST, note="supplement run: not added to any earlier 21/21 result")
        if not run_recorded(rec, GATE, g0_gate, h):
            return 0, False
        for name, fn in supplement_checks():
            if not run_recorded(rec, name, fn, h):
                return passed, False                           # nothing after a failure runs
            passed += 1
        return passed, run_recorded(rec, SUPPLEMENT_POST, d1_post, h)
    finally:
        h.close()


# --- sequence USAGE re-check (fixed scope; not run without approval) ------------------------------------
# G0 -> a1 (both roles observed exactly as the contract; no sequence USAGE for the write role) -> a2
# (representative first apply) -> s1 (= full-check c1) -> seq_post. Only a1, a2 and s1 count.

SEQ_KIND = "sequence_usage_recheck"
SEQ_PLANNED = ("a1", "a2", "s1")
SEQ_POST = "seq_post"


def seq_checks() -> list:
    return [("a1", a1_profiles), ("a2", a2_personal_and_lexeme), ("s1", c1_sequences)]   # order fixed


def seq_post(h: Harness) -> dict:
    """Required after check-seq (recorded, never counted): a2 left other accounts' / out-of-scope rows
    alone, no business session is open or idle in a transaction."""
    outside = h.evidence.get("outside", {})
    expect(outside.get("a2") is True, f"outside rows after a2 {outside}")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}")
    return {"outside_a2": True, **sessions}


def run_fixed(kind: str, planned: tuple, checks: list, post_name: str, post: Callable) -> tuple[int, bool]:
    """Gate, the fixed checks in order, then the required post-check. (passed and recorded, post passed)."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    h = Harness(rec)
    passed = 0
    try:
        h.start()
        rec.event("check_phase_started", phase=kind, gate=GATE, checks=list(planned), post=post_name,
                  note="fixed partial run: not added to any earlier result")
        if not run_recorded(rec, GATE, g0_gate, h):
            return 0, False
        for name, fn in checks:
            if not run_recorded(rec, name, fn, h):
                return passed, False                           # nothing after a failure runs
            passed += 1
        return passed, run_recorded(rec, post_name, post, h)
    finally:
        h.close()


def check_seq() -> tuple[int, bool]:
    return run_fixed(SEQ_KIND, SEQ_PLANNED, seq_checks(), SEQ_POST, seq_post)


# --- cleanup (C12-4; not run without approval) ------------------------------------------------------------

def cleanup() -> None:
    """R2 (shared layout function): only what this run recorded; any difference stops before deleting."""
    lay.cleanup(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit))



def main(argv: list[str]) -> int:
    phase = argv[0] if len(argv) == 1 else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase == "check":
            available = [n for n, _ in CHECKS]
            passed = check()
            print(f"passed {passed} / {len(PLANNED)}")
            if available != list(PLANNED) or passed != len(PLANNED):
                print("STOP: not all planned checks passed and were recorded")
                return 1
        elif phase == "check-d1":
            available = tuple(n for n, _ in supplement_checks())
            passed, post = check_d1()
            print(f"supplement d1: passed {passed} / {len(SUPPLEMENT_PLANNED)}, post-check {'pass' if post else 'not passed'}")
            if available != SUPPLEMENT_PLANNED or passed != len(SUPPLEMENT_PLANNED) or not post:
                print("STOP: not all supplement checks and the post-check passed and were recorded")
                return 1
        elif phase == "check-seq":
            available = tuple(n for n, _ in seq_checks())
            passed, post = check_seq()
            print(f"sequence re-check: passed {passed} / {len(SEQ_PLANNED)}, post-check {'pass' if post else 'not passed'}")
            if available != SEQ_PLANNED or passed != len(SEQ_PLANNED) or not post:
                print("STOP: not all sequence re-check checks and the post-check passed and were recorded")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check | check-d1 | check-seq | cleanup")
            return 2
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        return 1
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    return 0


if __name__ == "__main__":
    import _ops_apply_real as runner                      # the one module object (fake checks can reach it)
    sys.exit(runner.main(sys.argv[1:]))
