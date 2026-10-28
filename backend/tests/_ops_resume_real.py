"""RS4 CLI `resume` on a real local PostgreSQL (OPS_MIGRATION_RESUME_REAL_PG_PLAN.md), run explicitly, never by
discovery and never by import:

    python tests/_ops_resume_real.py prepare    # RS4-2: pg66 cluster, TLS, roles, template + check DBs, data, grants
    python tests/_ops_resume_real.py check      # RS4-3: gates G0 + G1 (not counted), then the checklist
    python tests/_ops_resume_real.py check-values  # plan 13-1: G0, G1 (r1 / r2), r1, r2, r3, post (supplement)
    python tests/_ops_resume_real.py cleanup    # RS4-4: R2, record vs live facts, stop, delete this run only

None of the three phases is approved (RS4-1 = this code and its PG-free fake checks only). The checks that
change application rows as the admin (plan Q2) stay closed until that decision is written into this file.

The target is the closed layout `_ops_real_layout.PG66` (C:/JV_Tools/pg66, localhost:55502, the template
`jp_vocab_test_resume_tpl` and one database per check, roles jpvr_*); no argument or environment value chooses
it or the checks. Only this runner (through `_ops_real_layout` / `_ops_pg62`) calls the real driver. The CLI's
command-line `resume` keeps refusing (`connection_not_available`); this runner calls `srs_migrate.run_resume`
in Python with its own guarded driver. Expected privileges are the contract constants (no sequence USAGE) and
expected objects the schema source; nothing observed becomes an expectation.

G1 makes every check DB's incomplete run with the REAL first `apply` (C12 path) under a v3 first approval A0
bound to the first evidence E0, inside the same `check` run as the resume (the test keys exist per run only).
The synthetic cards are account a's personal p1, p2, p3 (product order = ref order); after a 1-card first run
the resume handles p2 and p3 (personal cards only; lexeme cards are not part of the RS4 resume runs).

Counting (plan 5-0): per role, (1) connections created, (2) handed to the product, (3) business statements and
COMMITs, (4) committed row changes on an admin connection. Instrumentation wrappers call the original functions
and return their original objects; pause points block a thread, never change a statement.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
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
from psycopg.rows import dict_row, tuple_row  # noqa: E402

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
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (temporary test key helper only)

LAYOUT = lay.PG66
T = LAYOUT.target
TEMPLATE = LAYOUT.template
CHECK_DB = LAYOUT.check_db
BUSINESS_DATABASES = LAYOUT.business_databases
READ, WRITE = LAYOUT.read, LAYOUT.write
BUSINESS_ROLES = LAYOUT.business_roles
SYN = lay.SYN
CheckFailed, expect = lay.CheckFailed, lay.expect
WAIT_LIMIT = lay.WAIT_LIMIT
RUN_KEY = "rs4-resume-1"
T0 = sigtests.T0
GATES = ("g0_gate", "g1_gate")
POST = "post_check"
LOCK_PREFIX = "SELECT id FROM users WHERE id = "
RUN_ROW_PREFIX = "SELECT * FROM srs_migration_runs WHERE run_key = "
SHORT_UNTIL = "2026-10-21T12:40:00Z"                        # An with a short validity (r8)

# Plan Q2 (admin changes of application rows to make a state): APPROVED on 2026-10-28 for the closed ADMIN_DATA
# list only. Any value other than True makes `check` stop before G0 with exit 1; the decision is changed only by
# editing this value after the user's answer, never by an argument or an environment value.
Q2_ADMIN_DATA_CHANGES: bool | None = True        # 2026-10-28 user approval: the closed ADMIN_DATA list only
ADMIN_DATA_CHECKS = ("r4a", "r4b", "r7b", "r7c", "r7d", "r8")

# Checklist order (plan 5-1 / 5-2 / 5-3). r0 and r3 judge the evidence of r1 / r2, so they follow them.
PLANNED = ("r1", "r0", "r2", "r3", "r4a", "r4b", "r4c", "r5", "r6", "r6b", "r7a", "r7b", "r7c", "r7d", "r7e",
           "r8", "r9a", "r9b", "r9c", "c1", "c2", "c2s", "c3", "c3r", "c3c")

# The initial state G1 makes in each check DB with the REAL first apply (plan 4-2 step 6).
#   ("started", cursor, batch)  ("failed", 1, 3, inject at write n=3)  ("completed",)  ("other_account",)
#   ("v1_a0",): started 1/3 under a first approval WITHOUT the evidence binding (r6b)
INITIAL = {"r1": ("started", 1), "r2": ("failed", 1), "r4a": ("started", 1), "r4b": ("started", 1),
           "r4c": ("started", 1), "r5": ("started", 1), "r6": ("started", 1), "r6b": ("v1_a0", 1),
           "r7a": ("completed", 3), "r7b": ("started", 1), "r7c": ("started", 1), "r7d": ("started", 1),
           "r7e": ("other_account", 1), "r8": ("started", 1), "r9a": ("started", 1), "r9b": ("started", 1),
           "r9c": ("started", 1), "c1": ("started", 1), "c2": ("started", 1), "c2s": ("started", 1),
           "c3": ("started", 2), "c3r": ("started", 2), "c3c": ("started", 2)}
CARDS = ("p1", "p2", "p3")                                     # account a, personal; all convertible (G0)


# --- PG66-bound helpers: the shared functions with this runner's layout passed explicitly ----------------

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
    """R2: record vs live facts first; any difference stops before deleting anything (separate command)."""
    lay.cleanup(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- statement trace and under-lock reads (instrumentation; originals returned unchanged) -----------------

LABELS = (("SET TRANSACTION READ ONLY", "set_read_only"),
          ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", "set_repeatable_read"),
          ("SELECT id, mode, status, scope_json, config_version, summary_json, started_at, finished_at", "status_run_row"),
          ("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots", "status_snapshots"),
          (RUN_ROW_PREFIX, "lock_run_row"), (LOCK_PREFIX, "account_lock"))


def label(query: Any) -> str:
    """A fixed label for the statements this plan names; anything else is its first word only (no SQL text)."""
    text = query if isinstance(query, str) else ""
    for prefix, name in LABELS:
        if text.startswith(prefix):
            return name
    return lay.first_word(query)


def summary_facts(row: Any) -> dict:
    """Status, finished flag, summary hash and cursor of one run row as the product read it (no row text)."""
    try:
        status, finished, summary = row["status"], row["finished_at"], row["summary_json"]
    except (TypeError, KeyError, IndexError):
        return {"unreadable": True}
    try:
        cursor = json.loads(summary)["cursor"] if summary else 0
    except (TypeError, ValueError, KeyError):
        cursor = None
    return {"status": status, "finished": finished is not None,
            "summary_sha256": None if summary is None else sha(str(summary).encode("utf-8")), "cursor": cursor}


class ReadCursor(lay.TrackedCursor):
    """Records what the product read from the run-row query under the lock; returns the same row object."""

    def fetchone(self):
        row = self._cursor.fetchone()
        self._tracker.reads.append(summary_facts(row))
        return row


class ResumeTracked(lay.Tracked):
    """C12 Tracked plus a statement label trace (observation included, flagged) and the run-row reads."""

    _OWN = lay.Tracked._OWN | frozenset({"trace", "reads"})

    def __init__(self, conn: Any, counts: Counts, role: str, hooks: list):
        super().__init__(conn, counts, role, hooks)
        object.__setattr__(self, "trace", [])
        object.__setattr__(self, "reads", [])

    def run(self, query: Any, call: Callable[[], Any]) -> Any:
        self.trace.append((label(query), self.active))
        return super().run(query, call)

    def execute(self, query, *args, **kwargs):
        result = super().execute(query, *args, **kwargs)
        if self.active and isinstance(query, str) and query.startswith(RUN_ROW_PREFIX) \
                and isinstance(result, lay.TrackedCursor):
            return ReadCursor(result._cursor, self)
        return result


class Values:
    """Per-run records of the nine fixed values: the CLI pre-read (`progress_values`) and the product's
    under-lock read (`run_progress_values`). The wrapped functions are the originals, results returned as is."""

    local = threading.local()

    def __init__(self):
        self.runs: dict[str, dict] = {}

    @contextlib.contextmanager
    def installed(self):
        ar.fix_app_environment()
        from app.srs import migration
        real_pre, real_lock = cli.progress_values, migration.run_progress_values

        def pre(row, snapshots):
            result = real_pre(row, snapshots)
            self.slot()["pre_read"] = dict(result)
            return result

        def under_lock(connection, run_id):
            result = real_lock(connection, run_id)
            self.slot()["under_lock"] = dict(result) if isinstance(result, dict) else result
            return result
        with mock.patch.object(cli, "progress_values", pre), mock.patch.object(migration, "run_progress_values",
                                                                                under_lock):
            yield self

    def slot(self) -> dict:
        name = getattr(Values.local, "run", None) or "unnamed"
        return self.runs.setdefault(name, {})

    @contextlib.contextmanager
    def named(self, name: str):
        Values.local.run = name
        try:
            yield
        finally:
            Values.local.run = None


# --- pause points (plan 5-2) --------------------------------------------------------------------------------

class LockPause:
    """Holds ONE run's n-th account-lock statement of the write role (the lock is held while waiting)."""

    def __init__(self, nth: int, limit: float = WAIT_LIMIT):
        self.nth, self.limit, self.seen = nth, limit, 0
        self.reached, self.release = threading.Event(), threading.Event()
        self.holder_pid: int | None = None
        self.timed_out = False

    def hook(self, role: str, word: str, query: Any, tracker: Any) -> None:
        if role != WRITE or not (isinstance(query, str) and query.startswith(LOCK_PREFIX)):
            return
        self.seen += 1
        if self.seen != self.nth:
            return
        self.holder_pid = tracker.pending_pid
        self.reached.set()
        if not self.release.wait(self.limit):
            self.timed_out = True


class HandoverPause:
    """Holds ONE run's n-th write connection at the hand-over, before any business statement (no lock held)."""

    def __init__(self, nth: int, limit: float = WAIT_LIMIT):
        self.nth, self.limit = nth, limit
        self.reached, self.release = threading.Event(), threading.Event()
        self.pid: int | None = None
        self.timed_out = False

    def hook(self, role: str, number: int, tracker: Any) -> None:
        if role != WRITE or number != self.nth:
            return
        self.pid = tracker._conn.info.backend_pid
        self.reached.set()
        if not self.release.wait(self.limit):
            self.timed_out = True


# --- r0 probe (plan 5-1-1) ----------------------------------------------------------------------------------

PROBE_SQL = "SELECT pg_catalog.current_setting('transaction_isolation'), pg_catalog.current_setting('transaction_read_only')"


def _bare(interrupt: BaseException) -> BaseException:
    """The kept interrupt itself (same object, same SystemExit value) without any chained cause or context."""
    interrupt.__cause__ = None
    interrupt.__context__ = None
    interrupt.__suppress_context__ = True
    return interrupt


def make_probe(store: dict) -> Callable[[str, int, Any], None]:
    """Runs on the FIRST read connection after the product's body ended normally and before the original exit
    (commit / close): a NEW cursor, inside a savepoint, on the raw connection (not counted, not traced as a
    business statement). Only fixed stage codes are recorded, never error text. An ordinary error is recorded
    and not raised. An interrupt (probe or savepoint restore) is kept, the restore is still tried, and the
    FIRST kept interrupt is raised bare; the caller runs the original exit once before raising it."""

    def probe(role: str, number: int, tracker: Any) -> None:
        if role != READ or number != 1 or "probe" in store:
            return
        raw = tracker._conn
        store["probe_after"] = [name for name, _ in tracker.trace]
        kept: BaseException | None = None
        try:
            with raw.cursor(row_factory=tuple_row) as cursor:
                cursor.execute("SAVEPOINT rs4_probe")
                cursor.execute(PROBE_SQL)
                isolation, read_only = cursor.fetchone()
                cursor.execute("RELEASE SAVEPOINT rs4_probe")
            store["probe"] = {"transaction_isolation": isolation, "transaction_read_only": read_only}
            return
        except Exception:
            store["probe"] = {"probe_error": "probe_failed"}
        except BaseException as interrupt:                       # KeyboardInterrupt, SystemExit, ...
            store["probe"] = {"probe_error": "probe_interrupted"}
            kept = interrupt
        # the restore runs OUTSIDE the handlers above, so nothing it raises is chained to the probe's error
        try:
            with raw.cursor() as cursor:
                cursor.execute("ROLLBACK TO SAVEPOINT rs4_probe")
            store["probe"]["rollback"] = "rolled_back_to_savepoint"
        except Exception:
            store["probe"]["rollback"] = "rollback_to_savepoint_failed"
        except BaseException as interrupt:
            store["probe"]["rollback"] = "rollback_to_savepoint_interrupted"
            kept = kept if kept is not None else interrupt
        if kept is not None:
            raise _bare(kept)
    return probe


# --- cases ---------------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Case:
    check_id: str
    db: str
    account: str
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
        """Temporary test keys and in-memory passwords (RS4-3 only; never at import or in fake checks)."""
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
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg66_deploy_"))
        self.folders.append(folder)
        for rel, data in self.files().items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder

    # -- the first apply inputs (plan 4-2 steps 1..5) -----------------------------------------------------------
    def case(self, check_id: str, account: str = "a", *, batch: int = 1, v3: bool = True) -> Case:
        db = CHECK_DB[check_id]
        ids = self.target["synthetic"][account]
        uid = ids["user_id"]
        req = cli.make_request(uid, RUN_KEY, [ids["personal"][p] for p in CARDS], [])
        read_exp, write_exp = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        write_profile = pv.expected_profile_fingerprint(write_exp, role=WRITE, access="write")
        folder = self.deploy()
        manifest = pf.manifest_doc(self.files())                     # one manifest for the first apply AND resume
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        read_step = {"command": "dry_run", "access": "read", "role": READ, "profile": read_profile}
        inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000066",
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
        ev0 = self.write_evidence(folder, "evidence0", db_identity, uid, "bkp-0000000000000660")
        ev1 = self.write_evidence(folder, "evidence1", db_identity, uid, "bkp-0000000000000661")
        a0_doc = dict(inquiry_doc, kind="apply", approval_id="app-0000000000000660", plan={str(uid): printed},
                      based_on={"approval_id": inquiry_doc["approval_id"], "sha256": sha(inquiry)},
                      steps=[read_step, {"command": "apply", "access": "write", "role": WRITE, "profile": write_profile,
                                         "args": {"batch_size": str(batch)}}])
        if v3:
            a0_doc.update(format_version=3, backup_evidence={"sha256": sha(Path(ev0[0]).read_bytes())})
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
        return Case(check_id, db, account, req, plan, plan_path, folder, manifest, inquiry, a0, first_write,
                    first_read, ev0, ev1, read_exp, write_exp, read_profile, write_profile, db_identity, dsn, common)

    def write_evidence(self, folder: str, name: str, db_identity: str, uid: int, evidence_id: str,
                       **changes) -> tuple[str, str]:
        """Synthetic C10 statement (restore_verified false); E0 and E1 differ only in evidence_id."""
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": evidence_id, "purpose": "synthetic",
               "db_identity": db_identity, "account_id": uid, "job_key": RUN_KEY, "backup_id": "synthetic-backup-66",
               "taken_at": "2026-10-21T12:05:00Z", "method": "synthetic",
               "artifact_sha256": sha(b"synthetic backup"), "valid_until": "2026-10-21T12:50:00Z",
               "attested_by": "synthetic signer", "restore_verified": False}
        doc.update(changes)
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        path, sig = os.path.join(folder, name + ".json"), os.path.join(folder, name + ".sig")
        Path(path).write_bytes(data)
        Path(sig).write_bytes(self.sign(data, "backup"))
        return path, sig

    # -- the resume approval An and its step inputs (plan 4-2 step 7) -------------------------------------------
    def resume_inputs(self, case: Case, batch: int, *, approval_changes: dict | None = None, chain: Any = None,
                      plan: Any = None, a0_signature: bytes | None = None) -> tuple[Any, Any]:
        plan = plan or case.plan
        doc = json.loads(case.a0)
        doc.pop("backup_evidence", None)
        doc.update(approval_id="app-0000000000000661", format_version=3,
                   supersedes={"approval_id": json.loads(case.a0)["approval_id"], "sha256": sha(case.a0)},
                   steps=[{"command": "status", "access": "read", "role": READ, "profile": case.read_profile},
                          {"command": "resume", "access": "write", "role": WRITE, "profile": case.write_profile,
                           "args": {"batch_size": str(batch)}}])
        if plan is not case.plan:
            doc["plan"] = {str(case.request.account_id): oa.job_plan_fingerprint(
                db_identity=case.db_identity, manifest=om.manifest_fingerprint(case.manifest), tool="srs_migrate",
                account_id=case.request.account_id, job_key=RUN_KEY, job_inputs=cli.job_inputs(case.request),
                product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)}
        doc.update(approval_changes or {})
        an = json.dumps(doc).encode()
        link = op.ChainLink(case.a0, a0_signature if a0_signature is not None else self.sign(case.a0, "approval"),
                            case.inquiry, self.sign(case.inquiry, "approval"))
        shared = dict(case.common, approval=an, approval_signature=self.sign(an, "approval"), inquiry=case.inquiry,
                      inquiry_signature=self.sign(case.inquiry, "approval"),
                      product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256,
                      prior_chain=(link,) if chain is None else chain)
        write = op.PreflightInput(command="resume", args={"batch_size": str(batch)}, secret_dsn=case.dsn(WRITE),
                                  connection=op.ConnectionObservation(profile=case.write_profile, read_only=False),
                                  **shared)
        read = op.PreflightInput(command="status", args={}, secret_dsn=case.dsn(READ),
                                 connection=op.ConnectionObservation(profile=case.read_profile, read_only=True), **shared)
        return write, read

    # -- guarded business driver --------------------------------------------------------------------------------
    def driver(self, inputs: op.PreflightInput, counts: Counts, trackers: list, hooks: list | None = None):
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder, target=T)

        def connect(**kwargs):
            business_check(kwargs)                       # this run's matrix first, then the shared guard
            require_ours(self.target)
            conn = guard.driver(**kwargs)
            self.connections.append(conn)
            post_connect_check(conn, self.target, kwargs["user"])
            counts.created[kwargs["user"]] += 1
            tracked = ResumeTracked(conn, counts, kwargs["user"], hooks if hooks is not None else [])
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

    def resume_call(self, case: Case, inputs: tuple, counts: Counts, trackers: list, *, hooks=None, clock=None,
                    plan_path=None, initial=None, new=None) -> tuple[dict, int]:
        write, read = inputs
        return cli.run_resume(case.request, batch_size=int(write.args["batch_size"]), write_inputs=write,
                              read_inputs=read,
                              scope=cli.ProfileScope(lay.expected_objects(case.db), real.SEARCH_PATH, lay.TLS_VERSIONS),
                              driver=self.driver(write, counts, trackers, hooks), plan_path=plan_path or case.plan_path,
                              initial_evidence_path=(initial or case.initial_evidence)[0],
                              initial_evidence_signature_path=(initial or case.initial_evidence)[1],
                              evidence_path=(new or case.new_evidence)[0],
                              evidence_signature_path=(new or case.new_evidence)[1], clock=clock or lay.ticking(T0))

    def resume(self, case: Case, batch: int = 3, *, inputs: tuple | None = None, clock=None, inject=None,
               after=None, handover=None, before_exit=None, hooks=None, values: Values | None = None,
               plan_path=None, initial=None, new=None) -> dict:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        values = values or Values()
        with values.installed(), values.named("A"), scopes.installed(), \
                scopes.run(counts, trackers, inject=inject, after=after, handover=handover, before_exit=before_exit):
            out, code = self.resume_call(case, inputs or self.resume_inputs(case, batch), counts, trackers,
                                         hooks=hooks, clock=clock, plan_path=plan_path, initial=initial, new=new)
        return {"out": out, "code": code, "counts": counts, "trackers": trackers, "values": values.runs.get("A", {})}

    # -- admin facts --------------------------------------------------------------------------------------------
    def facts(self, case: Case) -> dict:
        with admin(case.db, self.pid) as conn:
            cards = {"personal": [ref for kind, ref in case.request.cards if kind == "personal"]}
            facts = lay.run_facts(conn, RUN_KEY, cards, case.request.account_id)
            row = conn.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = %s",
                               (RUN_KEY,)).fetchone()
        facts["summary"] = None if row is None else summary_facts(
            {"status": row[0], "summary_json": row[1], "finished_at": row[2]})
        return facts

    def fixed_values(self, case: Case) -> dict | None:
        """The nine values computed independently on an admin connection (contract 9-2), for comparison."""
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

    def hashes(self, check_id: str) -> dict:
        with admin(CHECK_DB[check_id], self.pid) as conn:
            return lay.content_hashes(conn)

    def outside(self, check_id: str) -> list:
        """Rows no run may change: account b's cards (except where b owns the run, r7e) and a's p4 / p5."""
        ids = self.target["synthetic"]
        with admin(CHECK_DB[check_id], self.pid) as conn:
            personal = conn.execute("SELECT v::text FROM vocab_items AS v WHERE user_id = %s OR id = ANY (%s) "
                                    "ORDER BY id", (ids["b"]["user_id"],
                                                    [ids["a"]["personal"]["p4"], ids["a"]["personal"]["p5"]])).fetchall()
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

    def locks(self, pid: int) -> list:
        with admin("postgres", self.pid) as conn:
            return [dict(zip(("locktype", "mode", "granted"), r)) for r in conn.execute(
                "SELECT locktype, mode, granted FROM pg_catalog.pg_locks WHERE pid = %s ORDER BY granted, locktype",
                (pid,))]

    def variant(self, check_id: str, name: str, phase: str) -> None:
        expect(check_id in LAYOUT.variant_databases[name], "variant outside its check DB", "harness_defect")
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for statement in variant_statements(name, phase):
                conn.execute(statement)
        self.rec.event("privilege_variant", name=name, phase=phase, database=CHECK_DB[check_id])

    def admin_data_change(self, check_id: str, name: str, case: Case) -> None:
        """Plan Q2: closed list of admin row changes; refused while the decision is open."""
        expect(Q2_ADMIN_DATA_CHANGES is True, "admin data changes are not approved (Q2)", "harness_defect")
        statements = ADMIN_DATA[name](self, case)
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for statement, params in statements:
                conn.execute(statement, params)
        self.rec.event("admin_data_change", name=name, database=CHECK_DB[check_id])


def _summary_reserialized(h: Harness, case: Case) -> list:
    with admin(case.db, h.pid) as conn:
        text = conn.execute("SELECT summary_json FROM srs_migration_runs WHERE run_key = %s", (RUN_KEY,)).fetchone()[0]
    return [("UPDATE srs_migration_runs SET summary_json = %s WHERE run_key = %s",
             (json.dumps(json.loads(text), indent=1), RUN_KEY))]                 # same content, other bytes


def _snapshot_added(h: Harness, case: Case) -> list:
    p3 = h.target["synthetic"]["a"]["personal"]["p3"]
    return [("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
             "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
             "SELECT run_id, user_id, card_kind, %s, card_version_before, legacy_json, srs_before_json, srs_after_json, "
             "history_quality, history_flags, created_at FROM srs_migration_snapshots WHERE run_id = "
             "(SELECT id FROM srs_migration_runs WHERE run_key = %s) ORDER BY id LIMIT 1", (p3, RUN_KEY))]


def _cursor_end(h: Harness, case: Case) -> list:
    """r7b: summary says every card is done while the status stays `started` (cursor_end_not_completed)."""
    with admin(case.db, h.pid) as conn:
        text = conn.execute("SELECT summary_json FROM srs_migration_runs WHERE run_key = %s", (RUN_KEY,)).fetchone()[0]
    summary = json.loads(text)
    ids = h.target["synthetic"]["a"]["personal"]
    results = summary["results"] + [{"kind": "personal", "ref_id": ids[p], "result": "conflict"} for p in CARDS[1:]]
    return [("UPDATE srs_migration_runs SET summary_json = %s WHERE run_key = %s",
             (json.dumps({"cursor": len(CARDS), "results": results}), RUN_KEY))]


ADMIN_DATA: dict[str, Callable[[Harness, Case], list]] = {
    "summary_reserialized": _summary_reserialized,
    "snapshot_added": _snapshot_added,
    "cursor_end": _cursor_end,
    "aborted": lambda h, case: [("UPDATE srs_migration_runs SET status = 'aborted' WHERE run_key = %s", (RUN_KEY,))],
    "summary_corrupt": lambda h, case: [("UPDATE srs_migration_runs SET summary_json = %s WHERE run_key = %s",
                                         ('{"cursor": 1}', RUN_KEY))],
    "started_31_days_ago": lambda h, case: [("UPDATE srs_migration_runs SET started_at = %s WHERE run_key = %s",
                                             (_days_ago(31), RUN_KEY))],
}


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# --- gates (recorded, never counted) --------------------------------------------------------------------------

def g0_gate(h: Harness) -> dict:
    """Live facts, every check DB's OID / identity, the intended qualities of p1..p4 / l1 / l2 on the template."""
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
    expect(qualities == lay.EXPECTED_QUALITIES, f"intended qualities {qualities}", "preparation_failure")
    return {"databases": len(h.target["databases"]), "qualities": qualities}


def template_qualities(h: Harness) -> dict:
    """The product dry_run on the template as the owner role (admin connection, read only)."""
    ar.fix_app_environment()
    from app.database import AppPostgresConnection
    from app.srs import migration
    from app.srs.engine import CardKey
    names = lay.quality_names(h.target["synthetic"]["a"])
    keys = [CardKey(kind, user, ref) for kind, user, ref in names]
    raw = admin(TEMPLATE, h.pid, autocommit=False)
    try:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(LAYOUT.owner)))
        raw.row_factory = dict_row
        app = AppPostgresConnection(raw)

        class Once:
            def __call__(self, *, read_only=False):
                return contextlib.nullcontext(app)
        candidates = migration.dry_run(keys, connect=Once())
    finally:
        raw.rollback()
        raw.close()
    return lay.name_qualities(candidates, names)


def expected_initial(state: str, cursor: int) -> dict:
    """What G1 must find (fixed from the plan, before any run): status, cursor, snapshot count."""
    return {"started": {"status": "started", "cursor": cursor, "snapshots": cursor},
            "failed": {"status": "failed", "cursor": cursor, "snapshots": cursor},
            "v1_a0": {"status": "started", "cursor": cursor, "snapshots": cursor},
            "other_account": {"status": "started", "cursor": cursor, "snapshots": cursor},
            "completed": {"status": "completed", "cursor": cursor, "snapshots": cursor}}[state]


def expected_scope_md5(plan: Any) -> str:
    ar.fix_app_environment()
    from app.srs import migration
    return hashlib.md5(migration._plan_json(list(pfile.to_candidates(plan))).encode("utf-8")).hexdigest()


def g1_gate(h: Harness, checks: tuple[str, ...] | None = None) -> dict:
    """Plan 4-2: every check DB's incomplete run made by the REAL first apply, then read back on an admin
    connection. Any difference is a preparation failure (no check runs, exit 1). `checks` is only ever the fixed
    VALUES_PLANNED of `check-values` (plan 13-1); the full check passes nothing (= every planned DB)."""
    made = {}
    for check_id in (PLANNED if checks is None else checks):
        if check_id not in INITIAL:
            continue
        state, cursor = INITIAL[check_id]
        before_outside = h.outside(check_id)
        if state == "other_account":
            owner_case = h.case(check_id, "b", batch=1)
            out, code = h.first_apply(owner_case)
            expect((out.get("phase"), code) == ("partial", 3), f"{check_id} b first apply {out.get('code')}/{code}",
                   "preparation_failure")
            case = h.case(check_id, "a", batch=1)             # a's own I0 / A0 / plan; a never applied here
            h.cases[check_id] = case
            facts = h.facts(owner_case)
            expect(len(facts["runs"]) == 1 and facts["runs"][0]["status"] == "started", f"{check_id} rows",
                   "preparation_failure")
            made[check_id] = {"owner": "b", "facts": facts}
            continue
        batch = {"started": cursor, "v1_a0": cursor, "completed": 3, "failed": 3}[state]
        case = h.case(check_id, batch=batch, v3=state != "v1_a0")
        h.cases[check_id] = case
        scope = expected_scope_md5(case.plan)
        inject = (lambda role, n: role == WRITE and n == 3) if state == "failed" else None   # injected (plan 4-2)
        out, code = h.first_apply(case, inject=inject)
        wanted = {"started": 3, "v1_a0": 3, "completed": 0, "failed": 1}[state]
        expect(code == wanted, f"{check_id} first apply {out.get('code')}/{code}", "preparation_failure")
        facts = h.facts(case)
        want = expected_initial(state, cursor)
        expect(len(facts["runs"]) == 1 and facts["runs"][0]["status"] == want["status"]
               and facts["runs"][0]["scope_md5"] == scope and facts["snapshots"] == want["snapshots"]
               and facts["summary"]["cursor"] == want["cursor"], f"{check_id} initial state {facts}",
               "preparation_failure")
        expect(h.outside(check_id) == before_outside, f"{check_id} outside rows", "preparation_failure")
        h.evidence.setdefault("outside", {})[check_id] = before_outside       # the post-checks compare with this
        made[check_id] = {"state": state, "facts": facts, "injected": state == "failed"}
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}", "preparation_failure")
    h.evidence["g1"] = made
    return {"databases": len(made), "states": {k: v.get("state", "other_account") for k, v in made.items()}}


# --- checks ---------------------------------------------------------------------------------------------------

def stage(result: dict, role: str) -> str:
    return lay.rejection_stage(result["counts"].role(role))


def clean_after(h: Harness, check_id: str, outside: list) -> None:
    expect(h.outside(check_id) == outside, f"{check_id}: other-account / out-of-scope rows changed")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"{check_id}: sessions {sessions}")


def refused_unchanged(h: Harness, check_id: str, result: dict, code: str, *, read: str, write: str,
                      exit_code: int = 4, before: dict | None = None, changed: dict | None = None) -> dict:
    """An expected (negative) result: exact code / exit / refusal stage per role and no committed change."""
    out = result["out"]
    expect((out.get("code"), result["code"]) == (code, exit_code), f"{check_id}: {out.get('code')}/{result['code']}")
    expect(stage(result, READ) == read and stage(result, WRITE) == write,
           f"{check_id}: stages {result['counts'].role(READ)} {result['counts'].role(WRITE)}")
    if before is not None:
        after = h.hashes(check_id)
        allowed = changed or {}
        expect({t: v for t, v in after.items() if t not in allowed} == {t: v for t, v in before.items()
                                                                        if t not in allowed},
               f"{check_id}: rows changed by a refused run")
    expect((out.get("restore_verified"), out.get("backup_artifact_checked")) in ((False, False), (None, None)),
           f"{check_id}: backup flags")
    return {"code": code, "read": result["counts"].role(READ), "write": result["counts"].role(WRITE)}


def r1_partial_resumed(h: Harness) -> dict:
    case = h.cases["r1"]
    outside, before = h.outside("r1"), h.facts(case)
    admin_values = h.fixed_values(case)
    store: dict = {}
    result = h.resume(case, 3, before_exit=make_probe(store))
    out = result["out"]
    expect((out.get("phase"), result["code"], out.get("results")) == ("completed", 0,
                                                                      {"already_applied": 1, "applied": 2}), f"r1 {out}")
    expect((out.get("restore_verified"), out.get("backup_artifact_checked")) == (False, False), "r1 backup flags")
    after = h.facts(case)
    ids = h.target["synthetic"]["a"]["personal"]
    bumps = {k: (after["versions"][k] or 0) - (before["versions"][k] or 0) for k in before["versions"]}
    expect(bumps == {f"personal:{ids['p1']}": 0, f"personal:{ids['p2']}": 1, f"personal:{ids['p3']}": 1},
           f"r1 card versions {bumps}")
    expect(after["snapshots"] == 3 and after["runs"][0]["status"] == "completed" and after["summary"]["cursor"] == 3,
           "r1 run row")
    read, write = result["counts"].role(READ), result["counts"].role(WRITE)
    expect((read["created"], read["handed"], read["writes"], write["created"], write["handed"]) == (1, 1, 0, 4, 4),
           f"r1 counts {read} {write}")
    clean_after(h, "r1", outside)
    read_trace = [t for t in result["trackers"] if t._role == READ][0].trace
    h.evidence["r1"] = {"trace": read_trace, "probe": store, "values": result["values"], "admin_values": admin_values}
    return {"read": read, "write": write, "versions": bumps}


def r0_status_session(h: Harness) -> dict:
    """Judges r1's read connection: statement order after the provider's observation, and the probe."""
    ev = h.evidence.get("r1")
    expect(ev is not None, "r0 needs r1's evidence", "harness_defect")
    names = [name for name, _ in ev["trace"]]
    last = len(names) - 1 - names[::-1].index("set_read_only")
    tail = ev["trace"][last:]
    expect([n for n, _ in tail] == ["set_read_only", "set_repeatable_read", "status_run_row", "status_snapshots"],
           f"r0 order {[n for n, _ in tail]}")
    expect([active for _, active in tail] == [False, True, True, True], "r0 hand-over point")
    probe = ev["probe"].get("probe", {})
    expect("probe_error" not in probe, f"r0 probe failed: {probe}", "harness_defect")
    expect(ev["probe"].get("probe_after") == names, "r0 probe was not after every business statement",
           "harness_defect")
    expect(probe == {"transaction_isolation": "repeatable read", "transaction_read_only": "on"}, f"r0 probe {probe}")
    return {"order": [n for n, _ in tail], "probe": probe}


def r2_failed_resumed(h: Harness) -> dict:
    case = h.cases["r2"]
    outside = h.outside("r2")
    admin_values = h.fixed_values(case)
    result = h.resume(case, 3)
    out = result["out"]
    expect((out.get("phase"), result["code"]) == ("completed", 0), f"r2 {out}")
    after = h.facts(case)
    expect(after["runs"][0]["status"] == "completed" and after["snapshots"] == 3, "r2 run row")
    clean_after(h, "r2", outside)
    h.evidence["r2"] = {"values": result["values"], "admin_values": admin_values}
    return {"results": out.get("results")}


NINE_VALUES = frozenset({"run_id", "status", "mode", "config_version", "started_at", "finished_at", "scope_sha256",
                         "summary_sha256", "snapshots_sha256"})


def r3_fixed_values(h: Harness) -> dict:
    """Plan 13-1: per run (r1, r2) the three nine-value records must exist with exactly the nine keys (else a
    harness defect) and be equal (else a failure). The result keeps FIXED COPIES of all three (never the
    originals) in the format fixed by the plan before this code."""
    kept: dict = {}
    for name in ("r1", "r2"):
        ev = h.evidence.get(name)
        expect(ev is not None, f"r3 needs {name}'s evidence", "harness_defect")
        values = ev.get("values") or {}
        three = {"pre_read": values.get("pre_read"), "under_lock": values.get("under_lock"),
                 "admin_values": ev.get("admin_values")}
        for key, value in three.items():
            expect(isinstance(value, dict), f"r3 {name} {key} missing", "harness_defect")
            expect(set(value) == NINE_VALUES, f"r3 {name} {key} keys {sorted(value)}", "harness_defect")
        kept[name] = {key: json.loads(json.dumps(value)) for key, value in three.items()}     # fixed copies
        expect(three["pre_read"] == three["under_lock"] == three["admin_values"],
               f"r3 {name}: pre-read / under-lock / admin values differ")
    return {"compared": ["r1", "r2"], "values": kept}


def changed_after_pre_read(h: Harness, check_id: str, change: Callable[[Case], dict]) -> dict:
    """r4a / r4b / r4c: a change between the status read and the first write request (after hook)."""
    case = h.cases[check_id]
    outside, before = h.outside(check_id), h.hashes(check_id)
    done: dict = {}

    def after(role, n):
        if role == READ and n == 1 and not done:
            done.update(change(case) or {"changed": True})
    result = h.resume(case, 3, after=after)
    expect(bool(done), f"{check_id}: the change did not run", "harness_defect")
    expect((result["out"].get("code"), result["code"]) == ("migration_run_changed", 4), f"{check_id} {result['out']}")
    write = result["counts"].role(WRITE)
    expect(stage(result, WRITE) == "under_product_lock" and write["handed"] == 1 and write["commits"] == 0,
           f"{check_id} write {write}")
    clean_after(h, check_id, outside)
    return {"change": done, "write": write, "values": result["values"], "rows_before": before}


def r4a_summary_changed(h: Harness) -> dict:
    return changed_after_pre_read(h, "r4a", lambda case: (h.admin_data_change("r4a", "summary_reserialized", case),
                                                          {"admin": "summary_reserialized"})[1])


def r4b_snapshot_added(h: Harness) -> dict:
    return changed_after_pre_read(h, "r4b", lambda case: (h.admin_data_change("r4b", "snapshot_added", case),
                                                          {"admin": "snapshot_added"})[1])


def r4c_cursor_advanced(h: Harness) -> dict:
    """A normal resume B (batch 1, its own thread and run scope) runs between A's pre-read and A's first write."""
    holder: dict = {}

    def run_b(case):
        def target():
            try:
                holder["b"] = h.resume(case, 1)
            except BaseException as error:
                holder["error"] = error
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(WAIT_LIMIT * 3)
        expect(not thread.is_alive(), "r4c: run B did not end", "harness_defect")
        if "error" in holder:
            raise CheckFailed("harness_defect", f"r4c run B raised {type(holder['error']).__name__}")
        b = holder["b"]
        expect((b["out"].get("phase"), b["code"]) == ("partial", 3), f"r4c B {b['out']}")
        return {"b": "partial"}
    out = changed_after_pre_read(h, "r4c", run_b)
    facts = h.facts(h.cases["r4c"])
    expect(facts["summary"]["cursor"] == 2 and facts["snapshots"] == 2, f"r4c rows {facts}")   # B's change only
    return out


# r5: privilege variants (each applied, run, reverted, then the observation re-checked against the contract)
R5 = (("r5_read_missing", "observed_privileges_missing", "after_observation", "before_connect"),
      ("r5_read_excess", "observed_privileges_excess", "after_observation", "before_connect"),
      ("r5_write_missing", "observed_privileges_missing", "committed", "after_observation"),
      ("r5_write_excess", "observed_privileges_excess", "committed", "after_observation"),
      ("r5_write_sequences", "observed_privileges_excess", "committed", "after_observation"))


def r5_privileges(h: Harness) -> dict:
    case = h.cases["r5"]
    outside, before = h.outside("r5"), h.hashes("r5")
    seen = {}
    for name, code, read_stage, write_stage in R5:
        h.variant("r5", name, "apply")
        try:
            result = h.resume(case, 3)
        finally:
            try:
                h.variant("r5", name, "revert")
            except Exception as error:
                raise CheckFailed("harness_defect", f"revert failed: {type(error).__name__}") from None
        seen[name] = refused_unchanged(h, "r5", result, code, read=read_stage, write=write_stage, before=before)
        observed = observe_both(h, case)
        expect(observed == {"read": "matches_contract", "write": "matches_contract"}, f"r5 revert {observed}",
               "harness_defect")
    # role mismatch: the write step's DSN with the read role is refused by the pre-check (code fixed from
    # _ops_target.check_preconnect -> _ops_preflight stage "connection"), before any connection
    write, read = h.resume_inputs(case, 3)
    wrong = (dataclasses.replace(write, secret_dsn=case.dsn(READ)), read)
    result = h.resume(case, 3, inputs=wrong)
    seen["role_mismatch"] = refused_unchanged(h, "r5", result, "preflight_role_mismatch", read="before_connect",
                                              write="before_connect", before=before)
    clean_after(h, "r5", outside)
    return seen


def observe_both(h: Harness, case: Case) -> dict:
    """One read and one write connection through the real provider path, handed over and closed unused."""
    out = {}
    write, read = h.resume_inputs(case, 3)
    for role, inputs, expected, read_only in ((READ, read, case.read_expected, True),
                                              (WRITE, write, case.write_expected, False)):
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            connect = cli._product_connector(dataclasses.replace(inputs, now=lay.ticking(T0)()), expected,
                                             h.driver(inputs, counts, trackers))
            try:
                with connect(read_only=read_only):
                    pass
                out["read" if role == READ else "write"] = "matches_contract"
            except cli.pc.OpsProductConnectionError as error:
                out["read" if role == READ else "write"] = error.code
    return out


def r6_bindings(h: Harness) -> dict:
    """Refused before any connection (both roles: 0 created), whole DB unchanged."""
    case = h.cases["r6"]
    outside, before = h.outside("r6"), h.hashes("r6")
    folder = case.folder
    ar.fix_app_environment()
    planned = list(pfile.to_candidates(case.plan))
    other = [dataclasses.replace(c, reconversion="restored") if i == 0 else c for i, c in enumerate(planned)]
    data = pfile.serialize_plan(db_identity=case.plan.db_identity, account_id=case.plan.account_id,
                                job_key=case.plan.job_key, config_version=case.plan.config_version,
                                product_fingerprint=case.plan.product_fingerprint, candidates=other)
    pfile.write_plan_file(os.path.join(folder, "plan_other.json"), data)
    plan_other = pfile.read_plan_file(os.path.join(folder, "plan_other.json"))
    expect(plan_other.product_fingerprint == case.plan.product_fingerprint
           and plan_other.artifact_sha256 != case.plan.artifact_sha256, "r6 other plan", "harness_defect")
    uid = case.request.account_id
    other_initial = h.write_evidence(folder, "evidence_other", case.db_identity, uid, "bkp-0000000000000662")
    moved = h.write_evidence(folder, "evidence_moved", case.db_identity, uid, "bkp-0000000000000663",
                             backup_id="synthetic-backup-67")
    tampered_a0 = h.sign(case.a0 + b" ", "approval")             # a signature over other bytes
    subcases = {
        "plan_not_initial": (dict(inputs=h.resume_inputs(case, 3, plan=plan_other),
                                  plan_path=os.path.join(folder, "plan_other.json")), "resume_plan_not_initial"),
        "chain_missing": (dict(inputs=h.resume_inputs(case, 3, chain=())), "resume_chain_required"),
        "a0_signature": (dict(inputs=h.resume_inputs(case, 3, a0_signature=tampered_a0)),
                         "preflight_approval_signature_invalid"),
        "initial_evidence_hash": (dict(initial=other_initial), "resume_initial_evidence_mismatch"),
        "new_evidence_fields": (dict(new=moved), "resume_backup_evidence_mismatch"),
        "same_evidence_id": (dict(new=case.initial_evidence), "resume_backup_evidence_mismatch"),
        "an_v2": (dict(inputs=h.resume_inputs(case, 3, approval_changes={"format_version": 2})),
                  "approval_format_not_v3"),
    }
    seen = {}
    for name, (kwargs, code) in subcases.items():
        result = h.resume(case, 3, **kwargs)
        seen[name] = refused_unchanged(h, "r6", result, code, read="before_connect", write="before_connect",
                                       before=before)
    clean_after(h, "r6", outside)
    return seen


def r6b_binding_missing(h: Harness) -> dict:
    case = h.cases["r6b"]
    outside, before = h.outside("r6b"), h.hashes("r6b")
    result = h.resume(case, 3)
    out = refused_unchanged(h, "r6b", result, "resume_backup_binding_missing", read="before_connect",
                            write="before_connect", before=before)
    clean_after(h, "r6b", outside)
    return out


def state_refusal(h: Harness, check_id: str, code: str, exit_code: int, change: str | None = None) -> dict:
    """r7*: the pre-read judges the state; no write connection is created."""
    case = h.cases[check_id]
    if change is not None:
        h.admin_data_change(check_id, change, case)
    outside, before = h.outside(check_id), h.hashes(check_id)
    result = h.resume(case, 3)
    out = refused_unchanged(h, check_id, result, code, exit_code=exit_code, read="committed",
                            write="before_connect", before=before)
    expect(result["counts"].role(READ)["writes"] == 0, f"{check_id} read writes")
    clean_after(h, check_id, outside)
    return out


def r7a_completed(h: Harness) -> dict:
    return state_refusal(h, "r7a", "migration_run_completed", 4)


def r7b_cursor_end(h: Harness) -> dict:
    return state_refusal(h, "r7b", "cursor_end_not_completed", 6, "cursor_end")


def r7c_closed(h: Harness) -> dict:
    return state_refusal(h, "r7c", "migration_run_closed", 4, "aborted")


def r7d_corrupt(h: Harness) -> dict:
    return state_refusal(h, "r7d", "summary_unreadable", 6, "summary_corrupt")  # judge_status reason, fixed


def r7e_other_owner(h: Harness) -> dict:
    case = h.cases["r7e"]
    before = h.hashes("r7e")
    result = h.resume(case, 3)
    out = refused_unchanged(h, "r7e", result, "resume_target_not_found", read="committed", write="before_connect",
                            before=before)
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"r7e sessions {sessions}")
    return out


def r8_times(h: Harness) -> dict:
    from datetime import datetime, timezone
    case = h.cases["r8"]
    outside, before = h.outside("r8"), h.hashes("r8")
    expiry = datetime(2026, 10, 21, 12, 40, 0, tzinfo=timezone.utc)
    short = h.resume_inputs(case, 3, approval_changes={"valid_until": SHORT_UNTIL})
    seen = {}
    # (1) approval expired before anything
    seen["before_start"] = refused_unchanged(h, "r8", h.resume(case, 3, inputs=short, clock=lambda: expiry),
                                             "preflight_approval_expired", read="before_connect",
                                             write="before_connect", before=before)
    # (2) expired after the status read, before the first write request
    state = {"now": T0}

    def after(role, n):
        if role == READ and n == 1:
            state["now"] = expiry
    seen["after_status"] = refused_unchanged(h, "r8", h.resume(case, 3, inputs=short, clock=lambda: state["now"],
                                                               after=after),
                                             "preflight_approval_expired", read="committed", write="before_connect",
                                             before=before)
    # (4) only the new evidence expires, at the recheck right before the first write (4 clock reads before it)
    calls = {"n": 0}
    evidence_until = datetime(2026, 10, 21, 12, 50, 0, tzinfo=timezone.utc)

    def clock():
        calls["n"] += 1
        return T0 if calls["n"] < 4 else evidence_until
    seen["evidence"] = refused_unchanged(h, "r8", h.resume(case, 3, clock=clock), "backup_evidence_expired",
                                         read="committed", write="before_connect", before=before)
    # (3) the 30-day window, judged by the CLI pre-read with the app process time (admin change, plan Q2)
    h.admin_data_change("r8", "started_31_days_ago", case)
    changed = h.hashes("r8")
    seen["window"] = refused_unchanged(h, "r8", h.resume(case, 3), "migration_resume_window_closed",
                                       read="committed", write="before_connect", before=changed)
    clean_after(h, "r8", outside)
    return seen


def r9a_revoked_between_cards(h: Harness) -> dict:
    case = h.cases["r9a"]
    outside = h.outside("r9a")
    applied = {"done": False}

    def after(role, n):
        if role == WRITE and n == 2 and not applied["done"]:           # after the first remaining card committed
            h.variant("r9a", "r9a_card_column", "apply")
            applied["done"] = True
    try:
        result = h.resume(case, 2, after=after)
    finally:
        if applied["done"]:
            try:
                h.variant("r9a", "r9a_card_column", "revert")
            except Exception as error:
                raise CheckFailed("harness_defect", f"revert failed: {type(error).__name__}") from None
    out = result["out"]
    expect((out.get("phase"), out.get("uncertain"), out.get("next"), result["code"])
           == ("after_start", True, "status_required", 1), f"r9a {out}")
    facts = h.facts(case)
    expect(facts["summary"]["cursor"] == 2 and facts["snapshots"] == 2, f"r9a rows {facts}")
    observed = observe_both(h, case)
    expect(observed == {"read": "matches_contract", "write": "matches_contract"}, f"r9a revert {observed}",
           "harness_defect")
    clean_after(h, "r9a", outside)
    return {"code": out.get("code"), "write": result["counts"].role(WRITE)}


def r9b_injected_card_failure(h: Harness) -> dict:
    case = h.cases["r9b"]
    outside = h.outside("r9b")
    result = h.resume(case, 3, inject=lambda role, n: role == WRITE and n == 3)       # INJECTED, not an outage
    out = result["out"]
    expect((out.get("phase"), out.get("uncertain"), result["code"]) == ("after_start", True, 1), f"r9b {out}")
    facts = h.facts(case)
    expect(facts["summary"]["cursor"] == 2 and facts["runs"][0]["status"] == "failed", f"r9b rows {facts}")
    clean_after(h, "r9b", outside)
    return {"injected": True}


def r9c_injected_final_failure(h: Harness) -> dict:
    case = h.cases["r9c"]
    outside = h.outside("r9c")
    result = h.resume(case, 3, inject=lambda role, n: role == WRITE and n == 4)       # the finish connection
    out = result["out"]
    expect((out.get("uncertain"), result["code"]) == (True, 1), f"r9c {out}")
    facts = h.facts(case)
    expect(facts["summary"]["cursor"] == 3 and facts["runs"][0]["status"] == "started", f"r9c rows {facts}")
    clean_after(h, "r9c", outside)
    return {"injected": True}


# --- contention (plan 5-2): fixed pause points and release order, one expected result each ------------------

class Runs:
    """Two runs in their own threads, each with its own run scope (one wrapper installed for the whole race)."""

    def __init__(self, h: Harness):
        self.h, self.scopes, self.values = h, RunScopes(), Values()
        self.threads: dict[str, threading.Thread] = {}
        self.results: dict[str, Any] = {}
        self.trackers: dict[str, list] = {"A": [], "B": []}
        self.counts = {"A": Counts(), "B": Counts()}
        self.pauses: list = []
        self.order: list = []

    def start(self, name: str, case: Case, batch: int, *, hooks=None, handover=None) -> None:
        def target():
            try:
                with self.values.named(name), self.scopes.run(self.counts[name], self.trackers[name],
                                                               handover=handover):
                    self.results[name] = ("ok", self.h.resume_call(case, self.h.resume_inputs(case, batch),
                                                                   self.counts[name], self.trackers[name],
                                                                   hooks=hooks))
            except BaseException as error:
                self.results[name] = ("error", error)
        thread = threading.Thread(target=target, daemon=True, name=f"rs4-{name}")
        self.threads[name] = thread
        thread.start()

    def wait(self, event: threading.Event, what: str) -> None:
        end = time.monotonic() + WAIT_LIMIT
        while not event.wait(0.05):
            if time.monotonic() > end or not any(t.is_alive() for t in self.threads.values()):
                raise CheckFailed("harness_defect", f"pause not reached: {what}")
        self.order.append(f"reached:{what}")

    def release(self, pause: Any, what: str) -> None:
        pause.release.set()
        self.order.append(f"released:{what}")

    def join(self, name: str) -> tuple[dict, int]:
        self.threads[name].join(WAIT_LIMIT * 3)
        expect(not self.threads[name].is_alive(), f"run {name} did not end", "harness_defect")
        kind, value = self.results.get(name, ("error", None))
        if kind == "error":
            if isinstance(value, CheckFailed):
                raise value
            raise CheckFailed("harness_defect", f"run {name} raised {type(value).__name__ if value else 'nothing'}")
        self.order.append(f"ended:{name}")
        return value

    def stop(self) -> None:
        """Every pause released and every thread ended, whatever happened (plan 7절)."""
        for pause in self.pauses:
            pause.release.set()
        for thread in self.threads.values():
            thread.join(WAIT_LIMIT * 3)
        if any(t.is_alive() for t in self.threads.values()):
            self.h.close_connections()
            raise CheckFailed("harness_defect", "a contention thread did not end")

    def b_waiting(self, holder: int | None) -> dict:
        trackers = self.trackers["B"]
        waiter = lay.wait_blocked(self.h.blocking, lambda: trackers[-1].pending_pid if trackers else None, holder)
        return {"waiter_pid": waiter, "holder_pid": holder, "blocking_pids": self.h.blocking(waiter),
                "waiter_locks": self.h.locks(waiter), "holder_locks": self.h.locks(holder)}

    def under_lock(self, name: str) -> list:
        writes = [t for t in self.trackers[name] if t._role == WRITE]
        return writes[0].reads if writes else []


def resume_attribution(before: dict, after: dict, *, scope: str, applied: int, refused_commits: int) -> list[str]:
    """Plan 5-2 ⓐ~ⓓ for a resume race: one run row with the original scope, snapshots = cards applied so far,
    each card bumped at most once, no COMMIT on the refused run's handed connections."""
    problems = []
    if len(after["runs"]) != 1 or after["runs"][0]["scope_md5"] != scope or after["runs"][0]["mode"] != "apply":
        problems.append("run_row")
    if after["snapshots"] != before["snapshots"] + applied:
        problems.append("snapshots")
    bumps = [(after["versions"].get(k) or 0) - (v or 0) for k, v in before["versions"].items()]
    if any(b not in (0, 1) for b in bumps) or sum(bumps) != applied:
        problems.append("card_versions")
    if refused_commits != 0:
        problems.append("refused_commits")
    return problems


def race_same_start(h: Harness, check_id: str, lock_nth: int, handover_nth: int, want_cursor: int) -> dict:
    """c1 / c2: A holds the lock in its card connection (lock_nth); B pre-reads, then waits for the lock
    (proved); A commits that card and stops at its next hand-over (handover_nth); B gets the lock first."""
    case = h.cases[check_id]
    scope = expected_scope_md5(case.plan)
    outside, before = h.outside(check_id), h.facts(case)
    runs = Runs(h)
    p1, p2 = LockPause(lock_nth), HandoverPause(handover_nth)
    runs.pauses += [p1, p2]
    try:
        with runs.values.installed(), runs.scopes.installed():
            runs.start("A", case, 3, hooks=[p1.hook], handover=p2.hook)
            runs.wait(p1.reached, "P1")
            runs.start("B", case, 3)
            proof = runs.b_waiting(p1.holder_pid)
            runs.release(p1, "P1")
            runs.wait(p2.reached, "P2")
            out_b, code_b = runs.join("B")
            committed = h.facts(case)                                    # A's card committed, B ended
            runs.release(p2, "P2")
            out_a, code_a = runs.join("A")
    finally:
        runs.stop()
    expect(not p1.timed_out and not p2.timed_out, "a pause timed out", "harness_defect")
    expect((out_b.get("code"), code_b) == ("migration_run_changed", 4), f"{check_id} B {out_b.get('code')}/{code_b}")
    reads = runs.under_lock("B")
    expect(len(reads) >= 1 and reads[0].get("status") == "started" and reads[0].get("cursor") == want_cursor
           and reads[0].get("summary_sha256") == committed["summary"]["summary_sha256"],
           f"{check_id} B under-lock read {reads}")
    expect(code_a == 0, f"{check_id} A {out_a.get('code')}/{code_a}")
    after = h.facts(case)
    problems = resume_attribution(before, after, scope=scope, applied=out_a["results"].get("applied", 0),
                                  refused_commits=runs.counts["B"].role(WRITE)["commits"])
    expect(problems == [], f"{check_id} changes attributed to B: {problems}")
    clean_after(h, check_id, outside)
    return {"blocking": proof, "b_under_lock": reads[0], "order": runs.order, "values": runs.values.runs,
            "b_write": runs.counts["B"].role(WRITE)}


def c1_same_start_cursor(h: Harness) -> dict:
    return race_same_start(h, "c1", lock_nth=2, handover_nth=3, want_cursor=2)


def c2_advanced_then_more(h: Harness) -> dict:
    return race_same_start(h, "c2", lock_nth=3, handover_nth=4, want_cursor=3)


def c2s_sequential(h: Harness) -> dict:
    case = h.cases["c2s"]
    outside = h.outside("c2s")
    first = h.resume(case, 1)
    expect((first["out"].get("phase"), first["code"]) == ("partial", 3), f"c2s A {first['out']}")
    second = h.resume(case, 3)
    expect((second["out"].get("phase"), second["code"], second["out"].get("results"))
           == ("completed", 0, {"already_applied": 2, "applied": 1}), f"c2s B {second['out']}")
    reads = [t for t in second["trackers"] if t._role == WRITE][0].reads
    expect(reads and reads[0].get("cursor") == 2 and reads[0].get("status") == "started", f"c2s B read {reads}")
    clean_after(h, "c2s", outside)
    return {"b_under_lock": reads[0]}


def c3_after_completion(h: Harness) -> dict:
    """A holds its last card connection's lock; B pre-reads cursor 2 and stops at its first hand-over (no lock);
    A finishes completely; B is released and reads `completed` under the lock."""
    case = h.cases["c3"]
    outside = h.outside("c3")
    runs = Runs(h)
    p1, q1 = LockPause(2), HandoverPause(1)
    runs.pauses += [p1, q1]
    try:
        with runs.values.installed(), runs.scopes.installed():
            runs.start("A", case, 3, hooks=[p1.hook])
            runs.wait(p1.reached, "P1")
            runs.start("B", case, 3, handover=q1.hook)
            runs.wait(q1.reached, "Q1")
            runs.release(p1, "P1")
            out_a, code_a = runs.join("A")
            sessions = h.sessions()
            expect(sessions["open"] == 1, f"c3 only B's held connection open: {sessions}", "harness_defect")
            completed = h.facts(case)
            runs.release(q1, "Q1")
            out_b, code_b = runs.join("B")
    finally:
        runs.stop()
    expect(code_a == 0 and completed["runs"][0]["status"] == "completed", f"c3 A {out_a.get('code')}/{code_a}")
    expect((out_b.get("code"), code_b) == ("migration_run_not_resumable", 4), f"c3 B {out_b.get('code')}/{code_b}")
    expect(runs.values.runs.get("B", {}).get("pre_read", {}).get("status") == "started", "c3 B pre-read")
    reads = runs.under_lock("B")
    expect(reads and reads[0].get("status") == "completed" and reads[0].get("finished") is True,
           f"c3 B under-lock read {reads}")
    expect("under_lock" not in runs.values.runs.get("B", {}), "c3 B reached the value comparison")
    expect(runs.counts["B"].role(WRITE)["commits"] == 0, "c3 B commits")
    clean_after(h, "c3", outside)
    return {"b_under_lock": reads[0], "order": runs.order}


def c3r_pre_read_before_finish(h: Harness) -> dict:
    case = h.cases["c3r"]
    outside = h.outside("c3r")
    runs = Runs(h)
    p1 = LockPause(3)                                                  # A's finish connection lock
    runs.pauses.append(p1)
    try:
        with runs.values.installed(), runs.scopes.installed():
            runs.start("A", case, 3, hooks=[p1.hook])
            runs.wait(p1.reached, "P1")
            runs.start("B", case, 3)
            out_b, code_b = runs.join("B")
            runs.release(p1, "P1")
            out_a, code_a = runs.join("A")
    finally:
        runs.stop()
    expect((out_b.get("code"), code_b) == ("cursor_end_not_completed", 6), f"c3r B {out_b.get('code')}/{code_b}")
    expect(runs.counts["B"].role(WRITE)["created"] == 0, "c3r B write connections")
    expect(code_a == 0, f"c3r A {out_a.get('code')}/{code_a}")
    clean_after(h, "c3r", outside)
    return {"order": runs.order}


def c3c_started_after_completion(h: Harness) -> dict:
    case = h.cases["c3c"]
    outside = h.outside("c3c")
    first = h.resume(case, 3)
    expect(first["code"] == 0, f"c3c A {first['out']}")
    before = h.hashes("c3c")
    second = h.resume(case, 3)
    out = refused_unchanged(h, "c3c", second, "migration_run_completed", read="committed", write="before_connect",
                            before=before)
    clean_after(h, "c3c", outside)
    return out


CHECKS: list[tuple[str, Callable[[Harness], dict]]] = [
    ("r1", r1_partial_resumed), ("r0", r0_status_session), ("r2", r2_failed_resumed), ("r3", r3_fixed_values),
    ("r4a", r4a_summary_changed), ("r4b", r4b_snapshot_added), ("r4c", r4c_cursor_advanced), ("r5", r5_privileges),
    ("r6", r6_bindings), ("r6b", r6b_binding_missing), ("r7a", r7a_completed), ("r7b", r7b_cursor_end),
    ("r7c", r7c_closed), ("r7d", r7d_corrupt), ("r7e", r7e_other_owner), ("r8", r8_times),
    ("r9a", r9a_revoked_between_cards), ("r9b", r9b_injected_card_failure), ("r9c", r9c_injected_final_failure),
    ("c1", c1_same_start_cursor), ("c2", c2_advanced_then_more), ("c2s", c2s_sequential),
    ("c3", c3_after_completion), ("c3r", c3r_pre_read_before_finish), ("c3c", c3c_started_after_completion),
]


def post_check(h: Harness) -> dict:
    """Recorded, never counted: no business session left and every privilege as the contract after the run."""
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"post sessions {sessions}")
    return {"sessions": sessions}


def check() -> tuple[int, dict]:
    """Returns (passed and recorded, summary). Gates and the post-check are never counted; the first failure
    stops everything after it (those items are recorded as not run)."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if Q2_ADMIN_DATA_CHANGES is not True:
        raise CheckFailed("preparation_failure", "plan Q2 (admin data changes) is undecided: nothing runs")
    rec = g.single_run(T)
    h = Harness(rec)
    names = [n for n, _ in CHECKS]
    passed, failed = 0, None
    try:
        h.start()
        rec.event("check_phase_started", gates=list(GATES), checks=names, post=POST,
                  note="gates and post-check are not counted")
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
        if failed is None:
            post = lay.run_recorded(rec, POST, post_check, h)
            if not post:
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


# --- fixed supplement run (plan 13-1; not run without approval) ------------------------------------------------
# G0 -> G1 (r1 / r2 only) -> r1 -> r2 -> r3 -> values_post. Only r1, r2, r3 count. Nothing is selectable from the
# command line or the environment; the full `check` (25 items) is unchanged.
VALUES_KIND = "supplement_values"
VALUES_PLANNED = ("r1", "r2", "r3")
VALUES_POST = "values_post"


def values_post(h: Harness) -> dict:
    """Recorded, never counted: r1 / r2 DBs' other-account and out-of-scope rows as right after G1, the r1 probe
    without failure, no business session and no idle-in-transaction session."""
    before = h.evidence.get("outside") or {}
    for check_id in ("r1", "r2"):
        expect(check_id in before, f"no G1 record of {check_id}'s outside rows", "harness_defect")
        expect(h.outside(check_id) == before[check_id], f"{check_id}: other-account / out-of-scope rows changed")
    probe = ((h.evidence.get("r1") or {}).get("probe") or {}).get("probe") or {}
    expect(probe and "probe_error" not in probe, f"r1 probe {probe}", "harness_defect")
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"post sessions {sessions}")
    return {"sessions": sessions, "outside_unchanged": ["r1", "r2"], "probe": probe}


def check_values() -> tuple[int, dict]:
    """Returns (passed and recorded among r1 / r2 / r3, summary). The first failure stops everything after it."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    h = Harness(rec)
    steps = [("g0_gate", lambda h_: g0_gate(h_)), ("g1_gate", lambda h_: g1_gate(h_, ("r1", "r2"))),
             ("r1", lambda h_: r1_partial_resumed(h_)), ("r2", lambda h_: r2_failed_resumed(h_)),
             ("r3", lambda h_: r3_fixed_values(h_)), (VALUES_POST, lambda h_: values_post(h_))]
    passed, failed = 0, None
    try:
        h.start()
        rec.event("check_phase_started", phase=VALUES_KIND, gates=list(GATES), checks=list(VALUES_PLANNED),
                  post=VALUES_POST, note="supplement run: not added to the earlier 25/25 result; gates and post-check "
                                         "are not counted")
        for name, fn in steps:
            if not lay.run_recorded(rec, name, fn, h):
                failed = name
                break
            if name in VALUES_PLANNED:
                passed += 1
    finally:
        h.close()
    not_run = []
    if failed is not None:
        done = [n for n, _ in steps][:[n for n, _ in steps].index(failed) + 1]
        not_run = [n for n in VALUES_PLANNED if n not in done]
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
        elif phase == "check":
            available = tuple(n for n, _ in CHECKS)
            passed, summary = check()
            print(f"passed {passed} / {len(PLANNED)}")
            if available != PLANNED or passed != len(PLANNED) or summary["failed"] is not None:
                print(f"STOP: not all planned checks passed and were recorded (failed: {summary['failed']}, "
                      f"not run: {len(summary['not_run'])})")
                return 1
        elif phase == "check-values":
            passed, summary = check_values()
            print(f"supplement values: passed {passed} / {len(VALUES_PLANNED)}")
            if passed != len(VALUES_PLANNED) or summary["failed"] is not None:
                print(f"STOP: not all supplement checks and the post-check passed and were recorded "
                      f"(failed: {summary['failed']}, not run: {len(summary['not_run'])})")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check | check-values | cleanup")
            return 2
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        return 1
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    return 0


if __name__ == "__main__":
    import _ops_resume_real as runner                      # the one module object (fake checks can reach it)
    sys.exit(runner.main(sys.argv[1:]))
