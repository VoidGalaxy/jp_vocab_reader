"""PG69 완료 결과 재조회 실제 로컬 PostgreSQL 검사 (OPS_MIGRATION_COMPLETED_REPLAY_REAL_PG_PLAN 8절, CR-PG1):
the PG69 target harness and its approval gates only. Run explicitly, never by discovery and never by import:

    python tests/_ops_completed_replay_real.py prepare           # not approved in CR-PG1 (PREPARE_APPROVED)
    python tests/_ops_completed_replay_real.py check-completed   # not approved in CR-PG1 (CHECK_APPROVED / ADMIN_CHANGES_APPROVED)
    python tests/_ops_completed_replay_real.py cleanup           # not approved in CR-PG1 (CLEANUP_APPROVED)

CR-PG1 approves only this code and its PG-free fake checks (8절); every approval constant below is None and
stays None until a later, separately approved change edits this file. No CLI argument or environment value can
turn a phase on, or change the target, roles, databases or check list. The target is the closed
`_ops_real_layout.PG69` object (C:/JV_Tools/pg69, localhost:55532, roles jpvq_*), passed explicitly to every
shared function; the PG68 runner's target-free instrumentation (`LockedRecord`, `HoldPause`, `blocking_events`,
`FinalCleanup`) is reused by import, never its Harness, module globals or checks. P8/P9's own contention
coordinator (`held_admin_action`) is local to this module (9절): it records only fixed stage codes, never an
exception class name, and keeps the admin action synchronous while the read connection is held.

Cards: account a's personal p1 and p2 (convertible). Expected values come from the contract (8절) and the
product read commands (`srs_migrate.read_status` / `judge_status`), never from a run.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import itertools
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
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

import _ops_access_lock_real as ax  # noqa: E402  (target-free instrumentation only, see module docstring)
import _ops_approval as oa  # noqa: E402
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

LAYOUT = lay.PG69
T = LAYOUT.target
TEMPLATE = LAYOUT.template
CHECK_DB = LAYOUT.check_db
READ, WRITE = LAYOUT.read, LAYOUT.write
BUSINESS_ROLES = LAYOUT.business_roles
SYN = lay.SYN
CheckFailed, expect = lay.CheckFailed, lay.expect
RUN_KEY = "completed-replay-1"
CONFLICT_RUN_KEY = "completed-replay-2-conflict"
BLOCKED_RUN_KEY = "completed-replay-2-blocked"
T0 = sigtests.T0
POST = "post_check"
WAIT_LIMIT = lay.WAIT_LIMIT
PLANNED = g.PG69_COMPLETED_REPLAY_CHECK_IDS
EXPECTED_QUALITIES = {"p1": "convertible", "p2": "convertible"}

# CR-PG1 (8절): code-only registration. Every approval constant below is None; None refuses its phase before any
# target-record lookup, folder creation or external work. Only a later, separately approved change to this file
# may set one to True (never an argument or an environment value). `check-completed` also needs the admin
# changes approval (P3/P4/P8/P9/P10 make closed, bound, fully reverted admin changes).
PREPARE_APPROVED: bool | None = None
CHECK_APPROVED: bool | None = None
ADMIN_CHANGES_APPROVED: bool | None = None
CLEANUP_APPROVED: bool | None = None

LockedRecord = ax.LockedRecord
HoldPause = ax.HoldPause
blocking_events = ax.blocking_events
FinalCleanup = ax.FinalCleanup
_bare = ax._bare
DEPLOY_PREFIX = "ops_pg69_deploy_"


# --- PG69-bound helpers (explicit layout, never a module default) ---------------------------------------------

def business_check(kwargs: dict) -> None:
    lay.business_check(LAYOUT, kwargs)


def require_target_bound(rec: g.Record, data: bytes) -> dict:
    return lay.require_target_bound(LAYOUT, rec, data)


def require_ours(target: dict) -> None:
    lay.require_ours(LAYOUT, target)


def post_connect_check(conn: Any, target: dict, user: str) -> None:
    lay.post_connect_check(LAYOUT, conn, target, user)


def admin(db: str, pid: int, autocommit: bool = True):
    return lay.admin(LAYOUT, db, pid, autocommit)


@contextlib.contextmanager
def owned_admin(h: "Harness", db: str, pid: int, autocommit: bool = True):
    """`admin(...)`, registering its SAME connection in `h.connections` before handing it to the caller,
    so an admin action run while a read connection is held (P8/P9) is owned by the harness like any
    other business connection: no second connection, no SQL/data change here."""
    with admin(db, pid, autocommit) as conn:
        h.connections.append(conn)
        yield conn


def expected_profiles(db: str) -> tuple[pv.ExpectedProfile, pv.ExpectedProfile]:
    return lay.expected_profiles(LAYOUT, db)


def contract_grants(db: str) -> list:
    return lay.contract_grants(LAYOUT, db)


class Counts(lay.Counts):
    def __init__(self):
        super().__init__(BUSINESS_ROLES)


ORIGINAL_CONNECTOR = lay.ORIGINAL_CONNECTOR


class RunScopes(lay.RunScopes):
    def __init__(self, real: Callable | None = None):
        super().__init__(LAYOUT, real or ORIGINAL_CONNECTOR)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iso_z(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fixed_clock(instant: datetime) -> Callable[[], datetime]:
    return lambda: instant


def sequence_clock(*instants: datetime) -> Callable[[], datetime]:
    """Each call returns the next instant; a clock-expiry trial reads the admit time, then the connection
    request time, which the product judges separately (C5)."""
    it = iter(instants)

    def clock() -> datetime:
        return next(it)
    return clock


def card_keys(ids: dict) -> list[tuple[str, int, int]]:
    personal = ids.get("personal", {})
    if not all(p in personal for p in ("p1", "p2")):
        raise CheckFailed("harness_defect", "the recorded account lacks personal p1/p2")
    return [("personal", ids["user_id"], personal["p1"]), ("personal", ids["user_id"], personal["p2"])]


def key_text(key: tuple[str, int, int]) -> str:
    return f"{key[0]}:{key[1]}:{key[2]}"


class ReplayCursor(lay.TrackedCursor):
    """lay.TrackedCursor; `fetchone` / `fetchall` call the real cursor FIRST, then run the tracker's
    fetch hooks on the SAME returned object (never a second query), then return that object unchanged
    (plan 9절: the pause point is after the row is materialized, not after `execute`)."""

    def fetchone(self):
        result = self._cursor.fetchone()
        self._tracker.after_fetch("fetchone", result)
        return result

    def fetchall(self):
        result = self._cursor.fetchall()
        self._tracker.after_fetch("fetchall", result)
        return result


class ReplayTracked(lay.Tracked):
    """lay.Tracked; when `rc_variant` is set, the product's own SET TRANSACTION ISOLATION LEVEL
    REPEATABLE READ is rewritten to READ COMMITTED for this ONE connection (P9 control variant only;
    the product never does this itself). `fetch_hooks(role, method, query_template, tracker, result)`
    run AFTER the real `fetchone` / `fetchall` returns, never at `execute` time."""

    _OWN = lay.Tracked._OWN | frozenset({"rc_variant", "fetch_hooks", "last_query"})
    _RR = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    _RC = "SET TRANSACTION ISOLATION LEVEL READ COMMITTED"

    def __init__(self, conn: Any, counts: Counts, role: str, hooks: list, rc_variant: bool = False,
                 fetch_hooks: list | None = None):
        super().__init__(conn, counts, role, hooks)
        object.__setattr__(self, "rc_variant", rc_variant)
        object.__setattr__(self, "fetch_hooks", fetch_hooks if fetch_hooks is not None else [])
        object.__setattr__(self, "last_query", None)

    def execute(self, query, *args, **kwargs):
        if self.rc_variant and isinstance(query, str) and query.strip().upper() == self._RR:
            query = self._RC
        object.__setattr__(self, "last_query", query if isinstance(query, str) else None)
        word = self.note(query)
        object.__setattr__(self, "pending_pid", self._conn.info.backend_pid)
        result = self._conn.execute(query, *args, **kwargs)
        if self.active:
            for hook in list(self._hooks):
                hook(self._role, word, query, self)
        if result is None or isinstance(result, lay.TrackedCursor):
            return result
        return ReplayCursor(result, self)

    def after_fetch(self, method: str, result: Any) -> None:
        if self.active:
            for hook in list(self.fetch_hooks):
                hook(self._role, method, self.last_query, self, result)


# --- prepare / cleanup (CR-PG1: None refuses before any target-record lookup or external work) ----------------

def build_template(pid: int, rec: g.Record) -> dict:
    return lay.build_template(LAYOUT, pid, rec, lambda db, p, autocommit=True: admin(db, p, autocommit))


def prepare() -> None:
    if PREPARE_APPROVED is not True:
        raise CheckFailed("preparation_failure", "PG69 prepare not approved (CR-PG1 8절): nothing runs")
    lay.prepare(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit),
                build_fn=lambda p, rec: build_template(p, rec), grants_fn=lambda db: contract_grants(db))


def cleanup() -> None:
    if CLEANUP_APPROVED is not True:
        raise CheckFailed("preparation_failure", "PG69 cleanup not approved (CR-PG1 8절): nothing runs")
    rec = g.single_run(T)
    blocked = blocking_events(rec.folder / "record.json")
    if blocked:
        raise CheckFailed("harness_defect", f"R2 refused: recorded {sorted(set(blocked))}; nothing deleted")
    lay.cleanup(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit))


# --- fixtures -----------------------------------------------------------------------------------------------

@dataclasses.dataclass
class Case:
    check_id: str
    db: str
    keys: list
    request: Any
    plan: Any
    plan_path: str
    folder: str
    manifest: bytes
    dry_run_inquiry: bytes
    a0: bytes
    first_write: Any
    first_read: Any
    initial_evidence: tuple
    read_expected: Any
    write_expected: Any
    read_profile: str
    write_profile: str
    db_identity: str
    dsn: Callable[[str], str]
    common: dict
    batch_size: int


_RO_COUNTER = itertools.count(1)


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
        self.pauses: list[Any] = []
        self.threads: list[threading.Thread] = []

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

    def close(self) -> "FinalCleanup":
        """Plan 13-3 (same shape as PG68): every step tried in order, none skipped after an error or
        interrupt: release the pauses, bounded-join every owned thread, close each owned connection not
        already confirmed closed, close the test keys, remove this run's deploy folders (then confirm
        they are gone) -- unless an owned thread is still alive, which refuses every folder with a fixed
        reason instead of deleting under it -- then clear the secrets in memory. Never raises."""
        done = FinalCleanup()

        def step(code: str, action: Callable[[], None]) -> None:
            try:
                action()
            except Exception:
                done.failures.append(f"{code}_failed")
            except BaseException as interrupt:
                done.failures.append(f"{code}_interrupted")
                done.interrupts.append(interrupt)
        for pause in list(self.pauses):
            step("pause_release", pause.release.set)
        for thread in list(self.threads):
            if thread.ident is not None:
                step("thread_join", lambda t=thread: t.join(WAIT_LIMIT))

        def close_one(c) -> None:
            def confirmed_closed() -> bool:
                try:
                    return getattr(c, "closed", False) is True
                except Exception:
                    done.failures.append("connection_state_failed")
                except BaseException as interrupt:
                    done.failures.append("connection_state_interrupted")
                    done.interrupts.append(interrupt)
                return False
            if confirmed_closed():
                return
            c.close()
            if not confirmed_closed():
                raise RuntimeError("connection_close_unconfirmed")
        for conn in list(self.connections):
            step("connection_close", lambda c=conn: close_one(c))
        for thread in list(self.threads):
            if thread.ident is not None:
                step("thread_join", lambda t=thread: t.join(WAIT_LIMIT))
        threads_alive = False
        for thread in list(self.threads):
            try:
                alive = thread.is_alive()
            except Exception:
                done.failures.append("thread_state_failed")
                alive = True
            except BaseException as interrupt:
                done.failures.append("thread_state_interrupted")
                done.interrupts.append(interrupt)
                alive = True
            if alive:
                threads_alive = True
        if self.keys is not None:
            step("keys_cleanup", self.keys.close)

        def remove_folder(entry: dict) -> None:
            """9절: recursive delete only after the owned identity recorded at creation (parent folder,
            basename prefix, device/inode, never a symlink / junction) is confirmed; a replaced, moved
            or unknown path is refused and nothing under it is deleted."""
            folder = entry["path"]
            if os.path.dirname(folder) != entry["parent"] or not os.path.basename(folder).startswith(DEPLOY_PREFIX):
                done.failures.append("deploy_folder_identity_mismatch")
                return
            if os.path.islink(folder) or (hasattr(os.path, "isjunction") and os.path.isjunction(folder)):
                done.failures.append("deploy_folder_identity_mismatch")
                return
            try:
                live = os.stat(folder, follow_symlinks=False)
            except OSError:
                done.failures.append("deploy_folder_unconfirmed")
                return
            if (live.st_dev, live.st_ino) != (entry["dev"], entry["ino"]):
                done.failures.append("deploy_folder_identity_mismatch")
                return
            shutil.rmtree(folder)
            if os.path.lexists(folder):
                done.failures.append("deploy_folder_unconfirmed")
        if threads_alive:
            done.failures.append("thread_end_unconfirmed")
            for _entry in list(self.folders):
                done.failures.append("deploy_folder_thread_active")
        else:
            for entry in list(self.folders):
                step("deploy_folder", lambda e=entry: remove_folder(e))
        step("secrets_clear", lambda: setattr(self, "passwords", {}))
        return done

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
        folder = os.path.normpath(tempfile.mkdtemp(prefix=DEPLOY_PREFIX))
        try:
            created = os.stat(folder, follow_symlinks=False)
        except OSError:
            raise CheckFailed("harness_defect", "deploy folder stat failed right after creation")
        self.folders.append({"path": folder, "parent": os.path.dirname(folder), "dev": created.st_dev,
                             "ino": created.st_ino})
        for rel, data in self.files().items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder

    def write_evidence(self, folder: str, name: str, db_identity: str, uid: int, evidence_id: str) -> tuple[str, str]:
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": evidence_id, "purpose": "synthetic",
               "db_identity": db_identity, "account_id": uid, "job_key": RUN_KEY, "backup_id": "synthetic-backup-69",
               "taken_at": "2026-10-21T12:05:00Z", "method": "synthetic", "artifact_sha256": sha(b"synthetic backup"),
               "valid_until": "2026-10-21T12:50:00Z", "attested_by": "synthetic signer", "restore_verified": False}
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        path, sig = os.path.join(folder, name + ".json"), os.path.join(folder, name + ".sig")
        Path(path).write_bytes(data)
        Path(sig).write_bytes(self.sign(data, "backup"))
        return path, sig

    def driver(self, inputs: Any, counts: Counts, trackers: list, hooks: list | None = None,
               rc_variant: bool = False, fetch_hooks: list | None = None):
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder, target=T)

        def connect(**kwargs):
            business_check(kwargs)
            require_ours(self.target)
            conn = guard.driver(**kwargs)
            self.connections.append(conn)
            post_connect_check(conn, self.target, kwargs["user"])
            counts.created[kwargs["user"]] += 1
            tracked = ReplayTracked(conn, counts, kwargs["user"], hooks if hooks is not None else [], rc_variant,
                                    fetch_hooks)
            trackers.append(tracked)
            return tracked
        return connect

    def case(self, check_id: str, *, account: str = "a", batch_size: int = 2, run_key: str | None = None,
             cards: list | None = None) -> Case:
        """Plan, approvals and inputs of one check DB: the REAL CLI dry-run (read pre-check, provider, product)
        writes the plan; the first apply uses `batch_size` cards at once (contract 8절: a completed run, not a
        partial one). I0 / A0 are signed with the temporary test keys."""
        db = CHECK_DB[check_id]
        ids = self.target["synthetic"][account]
        keys = cards if cards is not None else card_keys(ids)
        uid = ids["user_id"]
        req = cli.make_request(uid, run_key or RUN_KEY, [r for k, _, r in keys if k == "personal"], [])
        read_exp, write_exp = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        write_profile = pv.expected_profile_fingerprint(write_exp, role=WRITE, access="write")
        folder = self.deploy()
        manifest = pf.manifest_doc(self.files())
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        suffix = req.run_key[-6:] or "000000"
        read_step = {"command": "dry_run", "access": "read", "role": READ, "profile": read_profile}
        inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": f"inq-pg69-{check_id}-{suffix}",
                       "supersedes": None, "purpose": "synthetic", "alias": "synthetic-primary",
                       "db_identity": db_identity, "manifest": om.manifest_fingerprint(manifest),
                       "tool": "srs_migrate", "steps": [read_step], "accounts": [uid], "max_accounts": 1,
                       "job": {"key": req.run_key, "inputs": cli.job_inputs(req)},
                       "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
                       "approved_by": "synthetic signer"}
        inquiry = json.dumps(inquiry_doc).encode()
        root = os.path.join(folder, "ops", "tls", "root.pem")

        def dsn(role):
            return (f"postgresql://{role}:{self.passwords[role]}@{g.HOST}:{T.port}/{db}?sslmode=verify-full"
                    f"&sslrootcert={quote(root, safe='')}")
        common = dict(mode="synthetic", manifest=manifest, manifest_signature=self.sign(manifest, "manifest"),
                      deploy_root=folder, account_id=uid, job_key=req.run_key, job_inputs=cli.job_inputs(req),
                      target=target_obs, environment={"PATH": "C:/Windows"},
                      trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=T0)
        inquiry_inputs = op.PreflightInput(approval=inquiry, approval_signature=self.sign(inquiry, "approval"),
                                           command="dry_run", args={}, product_fingerprint=None,
                                           connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                           secret_dsn=dsn(READ), **common)
        plan_path = os.path.join(folder, "plan.json")
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            out, code = cli.run_dry_run(req, inputs=inquiry_inputs, expected=read_exp,
                                        driver=self.driver(inquiry_inputs, counts, trackers), out=plan_path)
        expect(code == 0, f"{check_id}: plan dry-run {out.get('code')}", "preparation_failure")
        plan = pfile.read_plan_file(plan_path)
        printed = op.run_synthetic_preflight(dataclasses.replace(
            inquiry_inputs, product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)).job_plan
        ev0 = self.write_evidence(folder, "evidence0", db_identity, uid, f"bkp-pg69-{check_id}-{suffix}")
        # P6 fixture (9절): a0 ALSO carries its own real `status` read step (same READ role, same read
        # access as dry_run), so a genuinely valid, fully preflight-checkable apply approval exists that
        # a status request can be tested against at the KIND gate, not an earlier input-shape refusal.
        status_step = {"command": "status", "access": "read", "role": READ, "profile": read_profile}
        a0_doc = dict(inquiry_doc, kind="apply", approval_id=f"app-pg69-{check_id}-{suffix}", plan={str(uid): printed},
                      based_on={"approval_id": inquiry_doc["approval_id"], "sha256": sha(inquiry)},
                      steps=[read_step, status_step, {"command": "apply", "access": "write", "role": WRITE,
                                                      "profile": write_profile,
                                                      "args": {"batch_size": str(batch_size)}}],
                      format_version=3, backup_evidence={"sha256": sha(Path(ev0[0]).read_bytes())})
        a0 = json.dumps(a0_doc).encode()
        shared = dict(common, approval=a0, approval_signature=self.sign(a0, "approval"), inquiry=inquiry,
                      inquiry_signature=self.sign(inquiry, "approval"), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256)
        first_write = op.PreflightInput(command="apply", args={"batch_size": str(batch_size)}, secret_dsn=dsn(WRITE),
                                        connection=op.ConnectionObservation(profile=write_profile, read_only=False),
                                        **shared)
        first_read = op.PreflightInput(command="dry_run", args={}, secret_dsn=dsn(READ),
                                       connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                       **shared)
        return Case(check_id, db, keys, req, plan, plan_path, folder, manifest, inquiry, a0, first_write, first_read,
                   ev0, read_exp, write_exp, read_profile, write_profile, db_identity, dsn, common, batch_size)

    def first_apply(self, case: Case, *, handover: Callable | None = None) -> tuple[dict, int]:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers, handover=handover):
            return cli.run_apply(case.request, batch_size=case.batch_size, write_inputs=case.first_write,
                                 read_inputs=case.first_read,
                                 scope=cli.ProfileScope(lay.expected_objects(case.db), lay.real.SEARCH_PATH,
                                                        lay.TLS_VERSIONS),
                                 driver=self.driver(case.first_write, counts, trackers), plan_path=case.plan_path,
                                 evidence_path=case.initial_evidence[0],
                                 evidence_signature_path=case.initial_evidence[1], clock=fixed_clock(T0))

    def status_inputs(self, case: Case, *, now: datetime) -> Any:
        """A NEW status/read INQUIRY approval, never the apply approval: no artifact, no prior chain, no
        product fingerprint (contract 8절)."""
        read_step = {"command": "status", "access": "read", "role": READ, "profile": case.read_profile}
        doc = {"format_version": 1, "kind": "inquiry", "approval_id": f"inq-pg69-{case.check_id}-stat01",
               "supersedes": None, "purpose": "synthetic", "alias": "synthetic-primary",
               "db_identity": case.db_identity, "manifest": om.manifest_fingerprint(case.manifest),
               "tool": "srs_migrate", "steps": [read_step], "accounts": [case.request.account_id], "max_accounts": 1,
               "job": {"key": case.request.run_key, "inputs": cli.job_inputs(case.request)},
               "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
               "approved_by": "synthetic signer"}
        data = json.dumps(doc).encode()
        shared = {k: v for k, v in case.common.items() if k != "now"}
        return op.PreflightInput(approval=data, approval_signature=self.sign(data, "approval"), command="status",
                                 args={}, product_fingerprint=None,
                                 connection=op.ConnectionObservation(profile=case.read_profile, read_only=True),
                                 secret_dsn=case.dsn(READ), now=now, **shared)

    def apply_approval_as_status(self, case: Case, *, now: datetime) -> Any:
        """P6 fixture: the job's REAL, fully valid apply approval (it also carries its own `status` read
        step, see `case()`), sent for a `status` request. `product_fingerprint` stays None and
        `artifact_sha256` / `prior_chain` stay at their status-command defaults (None / ()), so this
        input reaches the real preflight pass and is refused only at the kind gate
        (`approval_kind_not_inquiry`), never at the earlier `request_mismatch` input check."""
        shared = dict(case.common, approval=case.a0, approval_signature=self.sign(case.a0, "approval"),
                      inquiry=case.dry_run_inquiry, inquiry_signature=self.sign(case.dry_run_inquiry, "approval"),
                      product_fingerprint=None, now=now)
        return op.PreflightInput(command="status", args={}, secret_dsn=case.dsn(READ),
                                 connection=op.ConnectionObservation(profile=case.read_profile, read_only=True),
                                 **shared)

    def read_only_inputs(self, check_id: str, request: Any, *, now: datetime, tool: str = "srs_migrate",
                         tool_override: str | None = None, step_command: str = "status",
                         approval_kind: str = "inquiry", valid_from: str = "2026-10-21T12:00:00Z",
                         valid_until: str = "2026-10-21T13:00:00Z") -> tuple[Any, Any, Callable[[str], str]]:
        """A standalone status/read inquiry for an arbitrary request (P5/P6/P7: not tied to an existing Case)."""
        db = CHECK_DB[check_id]
        read_exp, _ = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        folder = self.deploy()
        manifest = pf.manifest_doc(self.files())
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        doc = {"format_version": 1, "kind": approval_kind,
               "approval_id": f"inq-pg69-{check_id}-ro{next(_RO_COUNTER):05d}", "supersedes": None,
               "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": db_identity,
               "manifest": om.manifest_fingerprint(manifest), "tool": tool_override or tool,
               "steps": [{"command": step_command, "access": "read", "role": READ, "profile": read_profile}],
               "accounts": [request.account_id], "max_accounts": 1,
               "job": {"key": request.run_key, "inputs": cli.job_inputs(request)},
               "valid_from": valid_from, "valid_until": valid_until, "approved_by": "synthetic signer"}
        data = json.dumps(doc).encode()
        root = os.path.join(folder, "ops", "tls", "root.pem")

        def dsn(role):
            return (f"postgresql://{role}:{self.passwords[role]}@{g.HOST}:{T.port}/{db}?sslmode=verify-full"
                    f"&sslrootcert={quote(root, safe='')}")
        inputs = op.PreflightInput(approval=data, approval_signature=self.sign(data, "approval"), command="status",
                                   args={}, product_fingerprint=None, manifest=manifest,
                                   manifest_signature=self.sign(manifest, "manifest"), deploy_root=folder,
                                   account_id=request.account_id, job_key=request.run_key,
                                   job_inputs=cli.job_inputs(request),
                                   connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                   secret_dsn=dsn(READ), target=target_obs, environment={"PATH": "C:/Windows"},
                                   trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=now,
                                   mode="synthetic")
        return inputs, read_exp, dsn

    def status(self, case: Case, *, clock: Callable[[], Any], hooks: list | None = None, rc_variant: bool = False,
               fetch_hooks: list | None = None, trackers: list | None = None,
               now_for_inputs: datetime | None = None) -> dict:
        counts, trackers = Counts(), (trackers if trackers is not None else [])
        scopes = RunScopes()
        inputs = self.status_inputs(case, now=now_for_inputs or T0)
        with scopes.installed(), scopes.run(counts, trackers):
            out, code = cli.run_status(case.request, inputs=inputs, expected=case.read_expected,
                                       driver=self.driver(inputs, counts, trackers, hooks=hooks,
                                                          rc_variant=rc_variant, fetch_hooks=fetch_hooks),
                                       clock=clock)
        return {"out": out, "code": code, "counts": counts, "trackers": trackers}

    def status_raw(self, request: Any, inputs: Any, read_exp: Any, *, clock: Callable[[], Any],
                   rc_variant: bool = False, hooks: list | None = None, fetch_hooks: list | None = None) -> dict:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            out, code = cli.run_status(request, inputs=inputs, expected=read_exp,
                                       driver=self.driver(inputs, counts, trackers, hooks=hooks,
                                                          rc_variant=rc_variant, fetch_hooks=fetch_hooks),
                                       clock=clock)
        return {"out": out, "code": code, "counts": counts, "trackers": trackers}

    # -- admin facts (read only) ------------------------------------------------------------------------------
    def state_admin(self, case: Case) -> dict:
        with admin(case.db, self.pid) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM srs_migration_runs WHERE run_key = %s", (case.request.run_key,))
                runs = cur.fetchall()
                cur.execute("SELECT * FROM srs_migration_snapshots WHERE run_id = ANY (%s) ORDER BY id",
                           ([r["id"] for r in runs],))
                snaps = cur.fetchall()
        return {"runs": runs, "snapshots": snaps}

    def row_text(self, db: str, table: str, row_id: int) -> dict | None:
        with admin(db, self.pid) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql.SQL("SELECT * FROM public.{} WHERE id = %s").format(sql.Identifier(table)), (row_id,))
                return cur.fetchone()

    def restore_row(self, conn: Any, table: str, row: dict) -> int:
        others = [c for c in row if c != "id"]
        assignments = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in others)
        values = [row[c] for c in others] + [row["id"]]
        cursor = conn.execute(sql.SQL("UPDATE public.{} SET {} WHERE id = %s").format(
            sql.Identifier(table), assignments), values)
        return cursor.rowcount

    def insert_row(self, conn: Any, table: str, row: dict) -> int:
        cols = list(row.keys())
        cursor = conn.execute(sql.SQL("INSERT INTO public.{} ({}) VALUES ({})").format(
            sql.Identifier(table), sql.SQL(", ").join(sql.Identifier(c) for c in cols),
            sql.SQL(", ").join(sql.SQL("%s") for _ in cols)), [row[c] for c in cols])
        return cursor.rowcount

    def sessions(self) -> dict:
        with admin("postgres", self.pid) as conn:
            rows = conn.execute("SELECT usename, state FROM pg_catalog.pg_stat_activity WHERE usename = ANY (%s)",
                                (list(BUSINESS_ROLES),)).fetchall()
        return {"open": len(rows), "idle_in_transaction": sum(1 for r in rows if r[1] == "idle in transaction")}

    def blocking_pids(self, pid: int) -> list:
        with admin("postgres", self.pid) as conn:
            return list(conn.execute("SELECT pg_catalog.pg_blocking_pids(%s)", (pid,)).fetchone()[0] or [])


# --- subcase bookkeeping (own small copy; see module docstring on reuse) ---------------------------------------

def subcase(h: Harness, check_id: str, name: str, ok: bool, **detail: Any) -> None:
    h.rec.event("subcase", check=check_id, name=name, ok=bool(ok), **detail)
    expect(ok, f"{check_id} {name}: {detail}")


def require_subcases(h: Harness, check_id: str, names: tuple[str, ...]) -> list[str]:
    try:
        saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        events = saved["events"]
    except (OSError, ValueError, KeyError, TypeError):
        raise CheckFailed("harness_defect", f"{check_id}: record not readable for subcases") from None
    seen = {e.get("name") for e in events if e.get("kind") == "subcase" and e.get("check") == check_id and e.get("ok")}
    missing = [n for n in names if n not in seen]
    expect(not missing, f"{check_id}: required subcases not recorded {missing}", "harness_defect")
    return list(names)


RUN_ROW_PREFIX = "SELECT id, mode, status, scope_json, config_version, summary_json, started_at, finished_at"
SNAPSHOT_SELECT_PREFIX = "SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots"


def restore_guarded(h: Harness, check_id: str, action: Callable[[], None]) -> None:
    """One admin restoration, attempted even while an original exception / interrupt is already in
    flight (captured BEFORE this function's own try/except touches `sys.exc_info()`). The original is
    always preserved as the SAME object, whatever the restoration (or its own logging) raises or is
    interrupted by: a restore failure here is recorded with a fixed stage code only (never a raw class
    name or secret); with no original in flight, the restoration's own error/interrupt propagates
    instead, with its chain stripped."""
    original_in_flight = sys.exc_info()[1]
    try:
        action()
    except BaseException as restore_error:
        try:
            h.rec.event("admin_restore_failed", check=check_id, stage="restore", confirmed=False)
        except BaseException:
            pass
        if original_in_flight is not None:
            return
        raise _bare(restore_error)


def record_statements(bucket: list) -> Callable[[str, str, Any, Any], None]:
    """Execute-level hook (9절): the exact statement text sent on the business connection, for checking
    the ABSENCE of a row-lock clause or a DML / sequence call -- never a second, separate query."""
    def hook(role: str, word: str, query: Any, tracker: Any) -> None:
        bucket.append(query if isinstance(query, str) else None)
    return hook


def count_fetch(prefix: str, counter: dict, key: str) -> Callable[[str, str, Any, Any, Any], None]:
    """Fetch-level hook: counts how many times a statement matching `prefix` was actually fetched
    (9절: the real delegated statement count, never a second observing query)."""
    def hook(role: str, method: str, query: Any, tracker: Any, result: Any) -> None:
        text = query if isinstance(query, str) else ""
        if text.startswith(prefix):
            counter[key] = counter.get(key, 0) + 1
    return hook


def no_lock_or_dml(statements: list) -> bool:
    texts = [t.upper() for t in statements if t]
    return not any("FOR UPDATE" in t or "FOR SHARE" in t
                  or t.strip().split(None, 1)[0] in ("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "CALL")
                  for t in texts)


ZERO_ROLE = {"created": 0, "handed": 0, "statements": 0, "writes": 0, "commits": 0}
ADMIN_MUTATION_TABLES = frozenset({"srs_migration_runs", "srs_migration_snapshots", "users", "vocab_items",
                                   "account_write_blocks"})


def admin_mutation_guard(check_id: str, table: str, db: str) -> None:
    """Every closed admin mutation helper (P3/P4/P8/P9/P10, the P2 conflict fixture) checks this first:
    the admin-changes approval, a known check id and a table/db from the closed, bound lists only."""
    expect(ADMIN_CHANGES_APPROVED is True, f"{check_id}: admin changes not approved", "harness_defect")
    expect(check_id.split(":")[0] in PLANNED, f"{check_id}: unknown check", "harness_defect")
    expect(table in ADMIN_MUTATION_TABLES, f"{check_id}: table {table} outside the closed admin mutation list",
           "harness_defect")
    expect(db in CHECK_DB.values(), f"{check_id}: db {db} outside the closed check databases", "harness_defect")


def freeze(value: Any) -> Any:
    """A JSON-safe frozen copy of one fetched row / row list: never the live driver object, never a
    class name. A dict-convertible row becomes a plain dict; anything else becomes a fixed label."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [freeze(v) for v in value]
    try:
        return {str(k): v for k, v in dict(value).items()}
    except (TypeError, ValueError):
        return "unconvertible_row"


class FetchPause:
    """Pauses ONE business connection right after a chosen statement's `fetchone` / `fetchall` returns
    the SAME object the driver gave (9절: never at `execute` time, never a second observing query).
    Captures the statement template (no bound values) and a frozen copy of what was actually returned."""

    def __init__(self, role: str, method: str, prefix: str, limit: float = WAIT_LIMIT):
        self.role, self.method, self.prefix, self.limit = role, method, prefix, limit
        self.reached, self.release = threading.Event(), threading.Event()
        self.holder_pid: int | None = None
        self.timed_out = False
        self._lock = threading.Lock()
        self.holding = False
        self.captured: dict = {}

    def hook(self, role: str, method: str, query: Any, tracker: Any, result: Any) -> None:
        text = query if isinstance(query, str) else ""
        if self.reached.is_set() or role != self.role or method != self.method or not text.startswith(self.prefix):
            return
        self.holder_pid = tracker.pending_pid
        self.captured = {"sql_template": text, "row": freeze(result)}
        with self._lock:
            self.holding = True
        self.reached.set()
        released = self.release.wait(self.limit)
        with self._lock:
            self.holding = False
            if not released:
                self.timed_out = True

    def still_held(self) -> bool:
        with self._lock:
            return self.holding and not self.timed_out and not self.release.is_set()


@dataclasses.dataclass
class HeldOutcome:
    status: Any                 # the full h.status(...) result dict of the paused call
    admin: Any                  # the admin_action()'s own return value
    still_held_after_commit: bool
    proof: dict


_TOKENS = itertools.count(1)


def held_admin_action(h: Harness, check_id: str, pause: FetchPause, run_status_fn: Callable[[], dict],
                      admin_action: Callable[[], Any], *, limit: float = WAIT_LIMIT) -> HeldOutcome:
    """9절: the read connection pauses after its row-select fetch returns the real row; the admin action
    runs SYNCHRONOUSLY on this thread while it is held, `still_held()` is read only AFTER the admin
    action returns (so after its own successful COMMIT), and only then is the pause released. Both the
    status thread and the admin thread are owned by `h.threads` from before they start; whatever the
    pause, the admin action or the cleanup itself raises or is interrupted by, every cleanup stage
    (release, bounded join, close only owned connections, bounded rejoin) is still attempted for both.
    The reported error always prefers the status body's own, then the admin body's own, then a
    coordination defect (pause never reached / admin not finished / possible row lock -- a test-only
    bound, never a product policy), then the first cleanup interrupt, then a fixed, uncertain-end
    failure; a thread is never force-killed. Only fixed stage codes are recorded, never an exception
    class name or raw text."""
    token = f"{check_id}:{next(_TOKENS)}"
    h.rec.event("coordination_started", check=check_id, token=token)
    result: dict = {}

    def runner() -> None:
        try:
            result["status"] = ("ok", run_status_fn())
        except BaseException as error:               # carried to this thread, judged below
            result["status"] = ("error", error)
    thread = threading.Thread(target=runner, name=f"{check_id}:status", daemon=True)
    h.threads.append(thread)
    admin_thread: threading.Thread | None = None
    admin_result: Any = None
    admin_error: BaseException | None = None
    coordination_error: BaseException | None = None
    cleanup_interrupt: BaseException | None = None
    still_held_after_commit = False
    stage = "start"

    def admin_runner() -> None:
        nonlocal admin_result, admin_error
        try:
            admin_result = admin_action()
        except BaseException as error:
            admin_error = error
    try:
        thread.start()
        stage = "pause_reached"
        if not pause.reached.wait(limit):
            raise CheckFailed("harness_defect", f"{check_id}: pause not reached")
        stage = "admin_action"
        admin_thread = threading.Thread(target=admin_runner, name=f"{check_id}:admin", daemon=True)
        h.threads.append(admin_thread)
        admin_thread.start()
        admin_thread.join(limit)
        if admin_thread.is_alive():
            raise CheckFailed("harness_defect", f"{check_id}: admin action did not finish (possible row lock)")
        if admin_error is not None:
            raise admin_error
        stage = "still_held_after_commit"
        still_held_after_commit = pause.still_held()
    except BaseException as error:
        if error is not admin_error:
            coordination_error = error
    finally:
        cleanup_failure: BaseException | None = None

        def cleanup_step(action: Callable[[], None]) -> None:
            nonlocal cleanup_interrupt, cleanup_failure
            try:
                action()
            except Exception as failure:
                if cleanup_failure is None:
                    cleanup_failure = failure
            except BaseException as interrupt:
                if cleanup_interrupt is None:
                    cleanup_interrupt = interrupt
        cleanup_step(pause.release.set)
        for owned in (thread, admin_thread):
            if owned is not None and owned.ident is not None:
                cleanup_step(lambda t=owned: t.join(limit))

        def owned_alive() -> bool:
            any_alive = False
            for owned in (thread, admin_thread):
                if owned is None:
                    continue
                try:
                    if owned.is_alive():
                        any_alive = True
                except Exception as failure:
                    any_alive = True
                    nonlocal_cleanup_failure(failure)
                except BaseException as interrupt:
                    any_alive = True
                    nonlocal_cleanup_interrupt(interrupt)
            return any_alive

        def nonlocal_cleanup_failure(failure: Exception) -> None:
            nonlocal cleanup_failure
            if cleanup_failure is None:
                cleanup_failure = failure

        def nonlocal_cleanup_interrupt(interrupt: BaseException) -> None:
            nonlocal cleanup_interrupt
            if cleanup_interrupt is None:
                cleanup_interrupt = interrupt

        if owned_alive():
            def close_owned() -> None:
                for conn in list(h.connections):
                    try:
                        already_closed = getattr(conn, "closed", False)
                    except Exception as failure:
                        nonlocal_cleanup_failure(failure)
                        continue
                    except BaseException as interrupt:
                        nonlocal_cleanup_interrupt(interrupt)
                        continue
                    if already_closed:
                        continue
                    try:
                        conn.close()
                    except Exception as failure:
                        nonlocal_cleanup_failure(failure)
                    except BaseException as interrupt:
                        nonlocal_cleanup_interrupt(interrupt)
            close_owned()
            for owned in (thread, admin_thread):
                if owned is not None:
                    cleanup_step(lambda t=owned: t.join(limit))
    ended_ok = True
    for owned in (thread, admin_thread):
        if owned is None:
            continue
        try:
            if owned.is_alive():
                ended_ok = False
        except BaseException:
            ended_ok = False
    try:
        if ended_ok and cleanup_failure is None:
            h.rec.event("coordination_ended", check=check_id, token=token)
        else:
            h.rec.event("thread_not_ended", check=check_id,
                       threads=[owned.name for owned in (thread, admin_thread)
                               if owned is not None and owned.is_alive()])
            h.rec.event("cleanup_incomplete", check=check_id, reason="thread end not confirmed")
    except BaseException:
        ended_ok = False
    status_kind, status_value = result.get("status", ("error", CheckFailed("harness_defect", "status not run")))
    if status_kind == "error":
        raise _bare(status_value)
    if admin_error is not None:
        raise _bare(admin_error)
    if coordination_error is not None:
        raise _bare(coordination_error)
    if cleanup_interrupt is not None:
        raise _bare(cleanup_interrupt)
    if cleanup_failure is not None:
        raise _bare(cleanup_failure)
    if not ended_ok:
        raise CheckFailed("harness_defect", f"{check_id}: status thread end not confirmed at stage {stage}")
    return HeldOutcome(status_value, admin_result, still_held_after_commit, dict(pause.captured))


# --- gates (recorded, never counted) ----------------------------------------------------------------------------

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
    for check_id in PLANNED:
        grants = contract_grants(CHECK_DB[check_id])
        expect(bool(grants), f"{check_id} contract grants", "preparation_failure")
    ar.fix_app_environment()
    import contextlib
    from app.database import AppPostgresConnection
    from app.srs import migration
    from app.srs.engine import CardKey
    ids = h.target["synthetic"]["a"]
    personal = ids.get("personal", {})
    keys = [CardKey("personal", ids["user_id"], personal[p]) for p in ("p1", "p2")]
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
    qualities = {("p1" if c.key.ref_id == personal["p1"] else "p2"): lay.quality_label(c) for c in candidates}
    expect(qualities == EXPECTED_QUALITIES, f"intended qualities {qualities}", "preparation_failure")
    return {"databases": len(h.target["databases"]), "qualities": qualities}


def g1_build_conflict_blocked(h: Harness, check_id: str) -> dict:
    """P2: a real product conflict (an approved test hook changes a already-dry-run-compared card right
    before the product's own per-card judgement) and a real blocked card (missing id), each its own run."""
    case = h.case(check_id, batch_size=2, run_key=CONFLICT_RUN_KEY)
    h.cases[check_id] = case
    ids = h.target["synthetic"]["a"]
    p1_id = ids["personal"]["p1"]

    def conflict_hook(role, number, tracker):
        if role != WRITE or number != 1:
            return
        admin_mutation_guard(check_id, "vocab_items", case.db)
        with admin(case.db, h.pid) as conn:
            rows = conn.execute("UPDATE vocab_items SET correct_count = correct_count + 1 "
                                "WHERE id = %s AND user_id = %s", (p1_id, ids["user_id"])).rowcount
        expect(rows == 1, f"{check_id}: conflict fixture row", "preparation_failure")
        h.rec.event("fixture_admin_change", check=check_id, name="induce_conflict", rows=rows)

    out, code = h.first_apply(case, handover=conflict_hook)
    expect(code == 5 and out.get("phase") == "completed" and out.get("results") == {"applied": 1, "conflict": 1},
           f"{check_id} conflict fixture {out}", "preparation_failure")
    conflict_base = h.state_admin(case)

    blocked_cards = [("personal", ids["user_id"], ids["personal"]["p1"]), ("personal", ids["user_id"], 2_000_000_000)]
    blocked_case = h.case(check_id, batch_size=2, run_key=BLOCKED_RUN_KEY, cards=blocked_cards)
    h.cases[check_id + ":blocked"] = blocked_case
    out2, code2 = h.first_apply(blocked_case)
    expect(code2 == 5 and out2.get("phase") == "completed" and out2.get("results") == {"applied": 1, "blocked": 1},
           f"{check_id} blocked fixture {out2}", "preparation_failure")
    blocked_base = h.state_admin(blocked_case)
    h.evidence.setdefault("baseline", {})[check_id] = conflict_base
    h.evidence.setdefault("baseline", {})[check_id + ":blocked"] = blocked_base
    return {"conflict": out.get("results"), "blocked": out2.get("results")}


def g1_gate(h: Harness) -> dict:
    """Every check DB except p5 (no run: not_started is tested on an empty run_key / other owner / unparseable
    scope, built inside p5 itself): the REAL plan dry-run and first apply (batch 2: both cards, completed)."""
    made = {}
    for check_id in PLANNED:
        if check_id == "p5":
            continue
        if check_id == "p2":
            made[check_id] = g1_build_conflict_blocked(h, check_id)
            continue
        case = h.case(check_id, batch_size=2)
        h.cases[check_id] = case
        out, code = h.first_apply(case)
        expect(code == 0 and out.get("phase") == "completed" and out.get("results") == {"applied": 2},
               f"{check_id} first apply {out}", "preparation_failure")
        h.evidence.setdefault("baseline", {})[check_id] = h.state_admin(case)
        made[check_id] = {"results": out.get("results")}
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"sessions {sessions}", "preparation_failure")
    return {"databases": len(made), "states": made}


# --- checks (P1..P10) --------------------------------------------------------------------------------------------

def p1_repeated_completed_query(h: Harness) -> dict:
    check_id = "p1"
    case = h.cases[check_id]
    base = h.evidence["baseline"][check_id]
    results = []
    for i in range(2):
        statements: list = []
        result = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5 + i)), hooks=[record_statements(statements)])
        result["statements"] = statements
        results.append(result)
    for i, result in enumerate(results):
        out, code = result["out"], result["code"]
        subcase(h, check_id, f"call_{i}_state", (out.get("state"), out.get("results"), code) ==
                ("completed", {"applied": 2}, 0), out=out, code=code)
        read_c, write_c = result["counts"].role(READ), result["counts"].role(WRITE)
        subcase(h, check_id, f"call_{i}_roles", read_c["created"] == 1 and read_c["handed"] == 1
                and write_c == ZERO_ROLE, read=read_c, write=write_c)
        subcase(h, check_id, f"call_{i}_no_row_lock_or_dml", no_lock_or_dml(result["statements"]),
                statements=result["statements"])
    after = h.state_admin(case)
    subcase(h, check_id, "no_reprocessing", after == base)
    require_subcases(h, check_id, ("call_0_state", "call_1_state", "call_0_roles", "call_1_roles",
                                   "call_0_no_row_lock_or_dml", "call_1_no_row_lock_or_dml", "no_reprocessing"))
    return {"calls": 2}


def p2_conflict_and_blocked(h: Harness) -> dict:
    check_id = "p2"
    allowed_keys = {"status", "command", "state", "results", "cursor", "card_count", "finished", "window"}
    for label, case, want in (("conflict", h.cases[check_id], {"applied": 1, "conflict": 1}),
                              ("blocked", h.cases[check_id + ":blocked"], {"applied": 1, "blocked": 1})):
        result = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)))
        out, code = result["out"], result["code"]
        subcase(h, check_id, f"{label}_state", (out.get("state"), out.get("results"), code) == ("completed", want, 5),
                out=out, code=code)
        subcase(h, check_id, f"{label}_no_new_fields", set(out) <= allowed_keys, out=out)
    require_subcases(h, check_id, ("conflict_state", "conflict_no_new_fields", "blocked_state",
                                   "blocked_no_new_fields"))
    return {}


def p3_admin_cursor_end(h: Harness) -> dict:
    check_id = "p3"
    case = h.cases[check_id]
    run_id = h.evidence["baseline"][check_id]["runs"][0]["id"]
    original = h.row_text(case.db, "srs_migration_runs", run_id)
    try:
        admin_mutation_guard(check_id, "srs_migration_runs", case.db)
        with admin(case.db, h.pid) as conn:
            rows = conn.execute("UPDATE srs_migration_runs SET status = 'started', finished_at = NULL "
                                "WHERE id = %s AND status = 'completed'", (run_id,)).rowcount
        subcase(h, check_id, "admin_change_rows", rows == 1, rows=rows)
        result = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)))
        out, code = result["out"], result["code"]
        subcase(h, check_id, "cursor_end_state", (out.get("state"), out.get("cursor"), out.get("finished"), code) ==
                ("cursor_end_not_completed", 2, False, 6), out=out, code=code)
        unchanged = h.row_text(case.db, "srs_migration_runs", run_id)
        subcase(h, check_id, "no_auto_complete", unchanged.get("status") == "started"
                and unchanged.get("finished_at") is None, unchanged=unchanged)
    finally:
        def do_restore():
            with admin(case.db, h.pid) as conn:
                h.restore_row(conn, "srs_migration_runs", original)
            subcase(h, check_id, "restored", h.row_text(case.db, "srs_migration_runs", run_id) == original)
        restore_guarded(h, check_id, do_restore)
    require_subcases(h, check_id, ("admin_change_rows", "cursor_end_state", "no_auto_complete", "restored"))
    return {}


def p4_duplicate_and_snapshot_mismatch(h: Harness) -> dict:
    check_id = "p4"
    case = h.cases[check_id]
    run_id = h.evidence["baseline"][check_id]["runs"][0]["id"]
    original = h.row_text(case.db, "srs_migration_runs", run_id)
    duplicated = original["summary_json"].replace('"cursor":2', '"cursor":2,"cursor":1', 1)
    expect(duplicated != original["summary_json"], f"{check_id}: fixture summary has no cursor key", "harness_defect")
    try:
        admin_mutation_guard(check_id, "srs_migration_runs", case.db)
        with admin(case.db, h.pid) as conn:
            rows = conn.execute("UPDATE srs_migration_runs SET summary_json = %s WHERE id = %s",
                                (duplicated, run_id)).rowcount
        subcase(h, check_id, "duplicate_change_rows", rows == 1, rows=rows)
        result = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)))
        out, code = result["out"], result["code"]
        subcase(h, check_id, "duplicate_state", (out.get("state"), out.get("reason"), code) ==
                ("inconsistent", "summary_unreadable", 6), out=out, code=code)
    finally:
        def restore_run():
            with admin(case.db, h.pid) as conn:
                h.restore_row(conn, "srs_migration_runs", original)
            subcase(h, check_id, "duplicate_restored", h.row_text(case.db, "srs_migration_runs", run_id) == original)
        restore_guarded(h, check_id, restore_run)
    snaps = h.evidence["baseline"][check_id]["snapshots"]
    first_snapshot = snaps[0]
    deleted_text = None
    try:
        admin_mutation_guard(check_id, "srs_migration_snapshots", case.db)
        with admin(case.db, h.pid) as conn:
            deleted_text = h.row_text(case.db, "srs_migration_snapshots", first_snapshot["id"])
            rows2 = conn.execute("DELETE FROM srs_migration_snapshots WHERE id = %s", (first_snapshot["id"],)).rowcount
        subcase(h, check_id, "snapshot_delete_rows", rows2 == 1, rows=rows2)
        result2 = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)))
        out2, code2 = result2["out"], result2["code"]
        subcase(h, check_id, "snapshot_mismatch_state", (out2.get("state"), out2.get("reason"), code2) ==
                ("inconsistent", "snapshot_mismatch", 6), out=out2, code=code2)
    finally:
        def restore_snapshot():
            if deleted_text is not None:
                with admin(case.db, h.pid) as conn:
                    h.insert_row(conn, "srs_migration_snapshots", deleted_text)
            subcase(h, check_id, "snapshot_restored",
                    h.row_text(case.db, "srs_migration_snapshots", first_snapshot["id"]) == deleted_text)
        restore_guarded(h, check_id, restore_snapshot)
    require_subcases(h, check_id, ("duplicate_change_rows", "duplicate_state", "duplicate_restored",
                                   "snapshot_delete_rows", "snapshot_mismatch_state", "snapshot_restored"))
    return {}


def p5_not_started_variants(h: Harness) -> dict:
    check_id = "p5"
    want = {"status": "ok", "command": "status", "state": "not_started"}
    now = T0 + timedelta(minutes=5)
    ids_a = h.target["synthetic"]["a"]

    # 1. missing key: no run of this key exists at all
    req_missing = cli.make_request(ids_a["user_id"], "completed-replay-p5-missing",
                                   [ids_a["personal"]["p1"], ids_a["personal"]["p2"]], [])
    inputs1, exp1, _ = h.read_only_inputs(check_id, req_missing, now=now)
    seen1: dict = {}
    r1 = h.status_raw(req_missing, inputs1, exp1, clock=fixed_clock(now),
                      fetch_hooks=[count_fetch(SNAPSHOT_SELECT_PREFIX, seen1, "n")])
    subcase(h, check_id, "missing_key", (r1["out"], r1["code"]) == (want, 0), out=r1["out"])
    subcase(h, check_id, "missing_key_no_snapshot_select", seen1.get("n", 0) == 0, seen=seen1)

    # 2. other owner: a real completed run of account b, under the SAME key account a asks about
    b_case = h.case(check_id, account="b", run_key="completed-replay-p5-other", batch_size=2)
    h.cases[check_id + ":other"] = b_case
    out_b, code_b = h.first_apply(b_case)
    expect(code_b == 0 and out_b.get("results") == {"applied": 2}, f"{check_id} other-owner fixture {out_b}",
           "preparation_failure")
    req_a_same_key = cli.make_request(ids_a["user_id"], "completed-replay-p5-other",
                                      [ids_a["personal"]["p1"], ids_a["personal"]["p2"]], [])
    inputs2, exp2, _ = h.read_only_inputs(check_id, req_a_same_key, now=now)
    seen2: dict = {}
    r2 = h.status_raw(req_a_same_key, inputs2, exp2, clock=fixed_clock(now),
                      fetch_hooks=[count_fetch(SNAPSHOT_SELECT_PREFIX, seen2, "n")])
    subcase(h, check_id, "other_owner", (r2["out"], r2["code"]) == (want, 0), out=r2["out"])
    subcase(h, check_id, "other_owner_no_snapshot_select", seen2.get("n", 0) == 0, seen=seen2)

    # 3. owner unreadable: account a's own run, scope_json corrupted with a duplicate key
    a_case = h.case(check_id, account="a", run_key="completed-replay-p5-corrupt", batch_size=2)
    h.cases[check_id + ":corrupt"] = a_case
    out_a, code_a = h.first_apply(a_case)
    expect(code_a == 0 and out_a.get("results") == {"applied": 2}, f"{check_id} corrupt fixture {out_a}",
           "preparation_failure")
    run_id = h.state_admin(a_case)["runs"][0]["id"]
    original = h.row_text(a_case.db, "srs_migration_runs", run_id)
    import re
    match = re.search(r'"user_id"\s*:\s*-?\d+', original["scope_json"])
    expect(match is not None, f"{check_id}: fixture scope has no user_id key", "harness_defect")
    duplicated = original["scope_json"][:match.end()] + ", " + match.group(0) + original["scope_json"][match.end():]
    try:
        admin_mutation_guard(check_id, "srs_migration_runs", a_case.db)
        with admin(a_case.db, h.pid) as conn:
            rows = conn.execute("UPDATE srs_migration_runs SET scope_json = %s WHERE id = %s",
                                (duplicated, run_id)).rowcount
        subcase(h, check_id, "owner_unreadable_change_rows", rows == 1, rows=rows)
        req_corrupt = cli.make_request(ids_a["user_id"], "completed-replay-p5-corrupt",
                                       [ids_a["personal"]["p1"], ids_a["personal"]["p2"]], [])
        inputs3, exp3, _ = h.read_only_inputs(check_id, req_corrupt, now=now)
        seen3: dict = {}
        r3 = h.status_raw(req_corrupt, inputs3, exp3, clock=fixed_clock(now),
                          fetch_hooks=[count_fetch(SNAPSHOT_SELECT_PREFIX, seen3, "n")])
        subcase(h, check_id, "owner_unreadable", (r3["out"], r3["code"]) == (want, 0), out=r3["out"])
        subcase(h, check_id, "owner_unreadable_no_snapshot_select", seen3.get("n", 0) == 0, seen=seen3)
    finally:
        def restore_scope():
            with admin(a_case.db, h.pid) as conn:
                h.restore_row(conn, "srs_migration_runs", original)
            subcase(h, check_id, "owner_unreadable_restored",
                    h.row_text(a_case.db, "srs_migration_runs", run_id) == original)
        restore_guarded(h, check_id, restore_scope)
    require_subcases(h, check_id, ("missing_key", "missing_key_no_snapshot_select", "other_owner",
                                   "other_owner_no_snapshot_select", "owner_unreadable_change_rows",
                                   "owner_unreadable", "owner_unreadable_no_snapshot_select",
                                   "owner_unreadable_restored"))
    return {}


# P6: exact pre-check refusal codes (contract 9절), fixed from `srs_migrate._admit` / `_ops_preflight` /
# `_ops_approval` (not observed at run time). `apply_approval_given` is an INDEPENDENTLY VALID, fully signed
# apply approval carrying its own `status` read step (see `Harness.case` / `apply_approval_as_status`): the
# real preflight pass succeeds and the CLI's own kind gate (`approval.kind != "inquiry"`) refuses it, never
# the earlier `request_mismatch` input check (that would be a false negative, not this gate's evidence).
P6_CASES = (("apply_approval_given", "approval_kind_not_inquiry"),
           ("wrong_tool", "approval_tool_not_srs_migrate"),
           ("wrong_step", "preflight_command_not_approved"),
           ("tampered_signature", "preflight_approval_signature_invalid"),
           ("manifest_mismatch", "preflight_manifest_not_approved"))


def p6_fixed_refusal_codes(h: Harness) -> dict:
    check_id = "p6"
    case = h.cases[check_id]
    now = T0 + timedelta(minutes=5)
    before = h.state_admin(case)                        # captured BEFORE any trial (9절)

    trials = {"apply_approval_given": h.status_raw(case.request, h.apply_approval_as_status(case, now=now),
                                                   case.read_expected, clock=fixed_clock(now))}
    inputs, read_exp, _ = h.read_only_inputs(check_id, case.request, now=now, tool_override="prb_recover")
    trials["wrong_tool"] = h.status_raw(case.request, inputs, read_exp, clock=fixed_clock(now))
    inputs, read_exp, _ = h.read_only_inputs(check_id, case.request, now=now, step_command="dry_run")
    trials["wrong_step"] = h.status_raw(case.request, inputs, read_exp, clock=fixed_clock(now))
    inputs, read_exp, _ = h.read_only_inputs(check_id, case.request, now=now)
    tampered = dataclasses.replace(inputs, approval_signature=bytes(b ^ 1 for b in inputs.approval_signature))
    trials["tampered_signature"] = h.status_raw(case.request, tampered, read_exp, clock=fixed_clock(now))
    inputs, read_exp, _ = h.read_only_inputs(check_id, case.request, now=now)
    tampered_manifest = dataclasses.replace(inputs, manifest=inputs.manifest + b" ")
    trials["manifest_mismatch"] = h.status_raw(case.request, tampered_manifest, read_exp, clock=fixed_clock(now))

    for label, expected_code in P6_CASES:
        result = trials[label]
        subcase(h, check_id, label, (result["out"].get("status"), result["out"].get("code"), result["code"]) ==
                ("refused", expected_code, 4), out=result["out"])
        counted_read, counted_write = result["counts"].role(READ), result["counts"].role(WRITE)
        subcase(h, check_id, f"{label}_no_connection", counted_read["created"] == 0 and counted_write["created"] == 0,
                read=counted_read, write=counted_write)
    after = h.state_admin(case)
    subcase(h, check_id, "unchanged", before == after)
    require_subcases(h, check_id, tuple(n for label, _ in P6_CASES for n in (label, f"{label}_no_connection")) +
                     ("unchanged",))
    return {}


def p7_clock_and_validity(h: Harness) -> dict:
    check_id = "p7"
    case = h.cases[check_id]
    valid_from, valid_until = "2026-10-21T12:00:00Z", "2026-10-21T13:00:00Z"
    until = datetime(2026, 10, 21, 13, 0, 0, tzinfo=timezone.utc)

    def inputs_at(now):
        return h.read_only_inputs(check_id, case.request, now=now, valid_from=valid_from, valid_until=valid_until)

    trials = {}
    inputs, exp, _ = inputs_at(until - timedelta(seconds=30))
    trials["valid"] = h.status_raw(case.request, inputs, exp, clock=fixed_clock(until - timedelta(seconds=30)))
    inputs, exp, _ = inputs_at(until - timedelta(seconds=1))
    trials["one_second_before"] = h.status_raw(case.request, inputs, exp,
                                               clock=fixed_clock(until - timedelta(seconds=1)))
    inputs, exp, _ = inputs_at(until)
    trials["exactly_expired"] = h.status_raw(case.request, inputs, exp, clock=fixed_clock(until))
    # Arms the clock only after the ORIGINAL _admit call consumes the first value: the admit judgement reads a
    # valid instant and returns its real matched result; only the later connection-request read (inside
    # _timed_connector) sees the expired boundary. The original approval / manifest bytes are never changed.
    inputs, exp, _ = inputs_at(until - timedelta(seconds=10))
    trials["expires_before_connection"] = h.status_raw(
        case.request, inputs, exp, clock=sequence_clock(until - timedelta(seconds=10), until + timedelta(seconds=1)))
    inputs, exp, _ = inputs_at(until - timedelta(seconds=10))
    trials["invalid_clock"] = h.status_raw(case.request, inputs, exp, clock=lambda: "not a time")
    # A caller-supplied stale `inputs.now` must never be judged: the clock argument always wins.
    inputs, exp, _ = inputs_at(until - timedelta(seconds=10))
    stale_inputs = dataclasses.replace(inputs, now=until + timedelta(days=1))
    trials["stale_input_now_ignored"] = h.status_raw(case.request, stale_inputs, exp,
                                                     clock=fixed_clock(until - timedelta(seconds=10)))

    def zero_both_roles(result: dict) -> bool:
        return result["counts"].role(READ)["created"] == 0 and result["counts"].role(WRITE)["created"] == 0

    subcase(h, check_id, "valid", (trials["valid"]["out"].get("state"), trials["valid"]["code"]) == ("completed", 0))
    subcase(h, check_id, "one_second_before",
            (trials["one_second_before"]["out"].get("state"), trials["one_second_before"]["code"]) == ("completed", 0))
    exactly = trials["exactly_expired"]
    subcase(h, check_id, "exactly_expired", (exactly["out"].get("code"), exactly["code"]) ==
            ("preflight_approval_expired", 4) and zero_both_roles(exactly), out=exactly["out"])
    before_conn = trials["expires_before_connection"]
    subcase(h, check_id, "expires_before_connection", (before_conn["out"].get("code"), before_conn["code"]) ==
            ("preflight_approval_expired", 4) and zero_both_roles(before_conn), out=before_conn["out"])
    invalid = trials["invalid_clock"]
    subcase(h, check_id, "invalid_clock", (invalid["out"].get("code"), invalid["code"]) == ("clock_invalid", 4)
            and zero_both_roles(invalid), out=invalid["out"])
    stale = trials["stale_input_now_ignored"]
    subcase(h, check_id, "stale_input_now_ignored", (stale["out"].get("state"), stale["code"]) == ("completed", 0),
            out=stale["out"])
    require_subcases(h, check_id, ("valid", "one_second_before", "exactly_expired", "expires_before_connection",
                                   "invalid_clock", "stale_input_now_ignored"))
    return {}


def p8_admin_noop_update_while_held(h: Harness) -> dict:
    check_id = "p8"
    case = h.cases[check_id]
    baseline = h.evidence["baseline"][check_id]
    run_id = baseline["runs"][0]["id"]
    snap_id = baseline["snapshots"][0]["id"]
    uid = case.request.account_id
    pause = FetchPause(READ, "fetchone", RUN_ROW_PREFIX)

    def admin_updates() -> dict:
        admin_mutation_guard(check_id, "users", case.db)
        admin_mutation_guard(check_id, "srs_migration_runs", case.db)
        admin_mutation_guard(check_id, "srs_migration_snapshots", case.db)
        with owned_admin(h, case.db, h.pid, autocommit=False) as conn:
            pid = conn.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()[0]
            rows_users = conn.execute("UPDATE users SET updated_at = updated_at WHERE id = %s", (uid,)).rowcount
            rows_runs = conn.execute("UPDATE srs_migration_runs SET status = status WHERE id = %s", (run_id,)).rowcount
            rows_snaps = conn.execute("UPDATE srs_migration_snapshots SET card_version_before = card_version_before "
                                      "WHERE id = %s", (snap_id,)).rowcount
            conn.commit()                                 # still_held is read by the caller AFTER this returns
        return {"pid": pid, "rows": [rows_users, rows_runs, rows_snaps], "commit_complete": True}

    outcome = held_admin_action(h, check_id, pause,
                                lambda: h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)),
                                                 fetch_hooks=[pause.hook]), admin_updates)
    status_result = outcome.status
    subcase(h, check_id, "admin_rows", outcome.admin["rows"] == [1, 1, 1], rows=outcome.admin["rows"])
    subcase(h, check_id, "admin_committed_while_held", outcome.still_held_after_commit is True)
    subcase(h, check_id, "status_unaffected", (status_result["out"].get("state"), status_result["code"]) ==
            ("completed", 0), out=status_result["out"])
    subcase(h, check_id, "captured_row_after_fetch", outcome.proof.get("row") is not None
            and str(outcome.proof.get("sql_template", "")).startswith(RUN_ROW_PREFIX), proof=outcome.proof)
    require_subcases(h, check_id, ("admin_rows", "admin_committed_while_held", "status_unaffected",
                                   "captured_row_after_fetch"))
    return {"admin_pid": outcome.admin["pid"]}


def p9_atomic_admin_transition_rr_vs_rc(h: Harness) -> dict:
    check_id = "p9"
    case = h.cases[check_id]
    baseline = h.evidence["baseline"][check_id]
    run_id = baseline["runs"][0]["id"]
    original_run = h.row_text(case.db, "srs_migration_runs", run_id)
    keys = card_keys(h.target["synthetic"]["a"])
    second_key = key_text(keys[1])
    snap2 = next(s for s in baseline["snapshots"]
                if key_text(("personal", s["user_id"], s["card_ref"])) == second_key)
    original_snap = h.row_text(case.db, "srs_migration_snapshots", snap2["id"])
    first = original_run["summary_json"].index('"result":"applied"')
    second = original_run["summary_json"].index('"result":"applied"', first + 1)
    new_summary = (original_run["summary_json"][:second] + '"result":"conflict"'
                  + original_run["summary_json"][second + len('"result":"applied"'):])
    expect(new_summary != original_run["summary_json"], f"{check_id}: fixture summary has one applied result only",
           "harness_defect")

    def mutate_once() -> dict:
        admin_mutation_guard(check_id, "srs_migration_runs", case.db)
        admin_mutation_guard(check_id, "srs_migration_snapshots", case.db)
        with owned_admin(h, case.db, h.pid, autocommit=False) as conn:
            rows_run = conn.execute("UPDATE srs_migration_runs SET summary_json = %s WHERE id = %s",
                                    (new_summary, run_id)).rowcount
            rows_snap = conn.execute("DELETE FROM srs_migration_snapshots WHERE id = %s", (snap2["id"],)).rowcount
            conn.commit()
        expect(rows_run == 1 and rows_snap == 1, f"{check_id}: mutation affected {rows_run}/{rows_snap} rows",
               "harness_defect")
        return {"rows": [rows_run, rows_snap], "commit_complete": True}

    def restore_and_verify() -> dict:
        admin_mutation_guard(check_id, "srs_migration_runs", case.db)
        admin_mutation_guard(check_id, "srs_migration_snapshots", case.db)
        with admin(case.db, h.pid, autocommit=False) as conn:
            rows_run = conn.execute("UPDATE srs_migration_runs SET summary_json = %s WHERE id = %s",
                                    (original_run["summary_json"], run_id)).rowcount
            rows_snap = h.insert_row(conn, "srs_migration_snapshots", original_snap)
            conn.commit()
        expect(rows_run == 1 and rows_snap == 1, f"{check_id}: restore affected {rows_run}/{rows_snap} rows",
               "harness_defect")
        return h.state_admin(case)

    # Every RR / RC experiment starts from the SAME restored original, reads the OLD run row, then atomically
    # mutates summary + snapshot EXACTLY ONCE while the read connection is still held (9절: no pre-mutation, no
    # second delete).
    pause_rr = FetchPause(READ, "fetchone", RUN_ROW_PREFIX)
    outcome_rr = held_admin_action(
        h, check_id, pause_rr,
        lambda: h.status(case, clock=fixed_clock(T0 + timedelta(minutes=6)), fetch_hooks=[pause_rr.hook]),
        mutate_once)
    rr_result = outcome_rr.status
    subcase(h, check_id, "rr_admin_committed_while_held", outcome_rr.still_held_after_commit is True)
    subcase(h, check_id, "rr_old_view", (rr_result["out"].get("state"), rr_result["out"].get("results"),
            rr_result["code"]) == ("completed", {"applied": 2}, 0), out=rr_result["out"])

    fresh = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=7)))
    subcase(h, check_id, "new_view", (fresh["out"].get("state"), fresh["out"].get("results"), fresh["code"]) ==
            ("completed", {"applied": 1, "conflict": 1}, 5), out=fresh["out"])

    restored = restore_and_verify()
    subcase(h, check_id, "restored_before_rc", restored == baseline)

    pause_rc = FetchPause(READ, "fetchone", RUN_ROW_PREFIX)
    outcome_rc = held_admin_action(
        h, check_id, pause_rc,
        lambda: h.status(case, clock=fixed_clock(T0 + timedelta(minutes=8)), fetch_hooks=[pause_rc.hook],
                         rc_variant=True),
        mutate_once)
    rc_result = outcome_rc.status
    subcase(h, check_id, "rc_admin_committed_while_held", outcome_rc.still_held_after_commit is True)
    subcase(h, check_id, "rc_mixed_view", (rc_result["out"].get("state"), rc_result["out"].get("reason"),
            rc_result["code"]) == ("inconsistent", "snapshot_mismatch", 6), out=rc_result["out"])

    final = restore_and_verify()
    subcase(h, check_id, "restored_final", final == baseline)
    require_subcases(h, check_id, ("rr_admin_committed_while_held", "rr_old_view", "new_view",
                                   "restored_before_rc", "rc_admin_committed_while_held", "rc_mixed_view",
                                   "restored_final"))
    return {}


def p10_active_write_block_ignored(h: Harness) -> dict:
    check_id = "p10"
    case = h.cases[check_id]
    uid = case.request.account_id
    recovery_key = f"pg69-{check_id}-recovery"
    grant_hash = hashlib.sha256(b"synthetic-grant").hexdigest()
    admin_mutation_guard(check_id, "account_write_blocks", case.db)
    with admin(case.db, h.pid) as conn:
        block_id = conn.execute(
            "INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
            "active_user_id, run_watermark, changes_started, created_at) VALUES "
            "(%s, 'srs_recovery', %s, %s, 'active', %s, 0, 0, %s) RETURNING id",
            (uid, recovery_key, grant_hash, uid, "2026-10-30T00:00:00+00:00")).fetchone()[0]
    before_block = h.row_text(case.db, "account_write_blocks", block_id)
    try:
        statements: list = []
        result = h.status(case, clock=fixed_clock(T0 + timedelta(minutes=5)), hooks=[record_statements(statements)])
        out, code = result["out"], result["code"]
        subcase(h, check_id, "status_unaffected", (out.get("state"), out.get("results"), code) ==
                ("completed", {"applied": 2}, 0), out=out)
        after_block = h.row_text(case.db, "account_write_blocks", block_id)
        subcase(h, check_id, "block_unchanged", after_block == before_block)
        read_c, write_c = result["counts"].role(READ), result["counts"].role(WRITE)
        subcase(h, check_id, "no_apply_or_account_lock", read_c["created"] == 1 and read_c["handed"] == 1
                and write_c == ZERO_ROLE, read=read_c, write=write_c)
        subcase(h, check_id, "no_row_lock_in_sql", no_lock_or_dml(statements), statements=statements)
    finally:
        def remove_block():
            admin_mutation_guard(check_id, "account_write_blocks", case.db)
            with admin(case.db, h.pid) as conn:
                rows = conn.execute("DELETE FROM account_write_blocks WHERE id = %s", (block_id,)).rowcount
            subcase(h, check_id, "block_removed", rows == 1)
        restore_guarded(h, check_id, remove_block)
    require_subcases(h, check_id, ("status_unaffected", "block_unchanged", "no_apply_or_account_lock",
                                   "no_row_lock_in_sql", "block_removed"))
    return {}


def post_check(h: Harness) -> dict:
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0}, f"post sessions {sessions}")
    expect(all(p.release.is_set() for p in h.pauses), "post: a pause was never released")
    alive = [t.name for t in h.threads if t.is_alive()]
    expect(not alive, f"post: threads alive {alive}")
    for check_id in PLANNED:
        case = h.cases.get(check_id)
        base = h.evidence.get("baseline", {}).get(check_id)
        if case is None or base is None:
            continue
        now = h.state_admin(case)
        expect(now == base, f"post {check_id}: baseline drifted")
    return {"sessions": sessions}


CHECKS: list[tuple[str, Callable[[Harness], dict]]] = [
    ("p1", p1_repeated_completed_query), ("p2", p2_conflict_and_blocked), ("p3", p3_admin_cursor_end),
    ("p4", p4_duplicate_and_snapshot_mismatch), ("p5", p5_not_started_variants), ("p6", p6_fixed_refusal_codes),
    ("p7", p7_clock_and_validity), ("p8", p8_admin_noop_update_while_held),
    ("p9", p9_atomic_admin_transition_rr_vs_rc), ("p10", p10_active_write_block_ignored),
]


def check_completed() -> tuple[int, dict]:
    """(passed and recorded, summary). Gates and the post-check are never counted; the first failure stops
    everything after it (recorded as not run)."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if CHECK_APPROVED is not True or ADMIN_CHANGES_APPROVED is not True:
        raise CheckFailed("preparation_failure",
                          "PG69 check-completed / admin changes not approved (CR-PG1 8절): nothing runs")
    rec = LockedRecord(g.single_run(T).folder)
    blocked = blocking_events(rec.folder / "record.json")
    if blocked:
        raise CheckFailed("harness_defect", f"recorded {sorted(set(blocked))}: no check runs")
    h = Harness(rec)
    token = f"final:{time.time_ns()}"
    rec.event("final_cleanup_started", token=token)
    names = [n for n, _ in CHECKS]
    passed, failed, current = 0, None, None
    original: BaseException | None = None
    try:
        h.start()
        rec.event("check_phase_started", phase="completed_replay", gates=["g0_gate", "g1_gate"], checks=names,
                  post=POST, note="gates and post-check are not counted; PG65-68 results are not added")
        for gate, fn in (("g0_gate", g0_gate), ("g1_gate", g1_gate)):
            current = gate
            if not lay.run_recorded(rec, gate, fn, h):
                failed = gate
                break
        if failed is None:
            for name, fn in CHECKS:
                current = name
                if not lay.run_recorded(rec, name, fn, h):
                    failed = name
                    break
                passed += 1
        if failed is None:
            current = POST
            if not lay.run_recorded(rec, POST, post_check, h):
                failed = POST
    except BaseException as error:
        original = error
        if not isinstance(error, Exception):
            rest = names[names.index(current) + 1:] if current in names else ([] if current == POST else names)
            try:
                rec.event("not_run", after=current, interrupted=type(error).__name__, checks=rest)
            except BaseException:
                pass
    closing = h.close()
    if not isinstance(closing, FinalCleanup):
        closing = FinalCleanup(failures=["final_cleanup_unreported"])
    saved_ok = True
    for kind, facts in ((("final_cleanup", dict(failures=list(closing.failures))),
                         ("cleanup_incomplete", dict(reason="final cleanup not confirmed")))
                        if closing.failures else (("final_cleanup_ended", dict(token=token)),)):
        try:
            rec.event(kind, **facts)
        except BaseException as error:
            saved_ok = False
            if not isinstance(error, Exception):
                closing.interrupts.append(error)
    if original is not None:
        raise _bare(original)
    if closing.interrupts:
        raise _bare(closing.interrupts[0])
    if closing.failures or not saved_ok:
        raise CheckFailed("harness_defect", f"final cleanup {closing.failures or ['record_failed']}")
    not_run = names[passed + (1 if failed in names else 0):] if failed is not None else []
    if failed is not None:
        try:
            rec.event("not_run", after=failed, checks=not_run)
        except Exception:
            pass
    return passed, {"failed": failed, "not_run": not_run}


PHASES = ("prepare", "check-completed", "cleanup")


def main(argv: list[str]) -> int:
    phase = argv[0] if len(argv) == 1 and argv[0] in PHASES else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase == "check-completed":
            passed, summary = check_completed()
            print(f"passed {passed} / {len(PLANNED)}")
            if tuple(n for n, _ in CHECKS) != PLANNED or passed != len(PLANNED) or summary["failed"] is not None:
                print(f"STOP: not all planned checks passed and were recorded (failed: {summary['failed']}, "
                      f"not run: {len(summary['not_run'])})")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check-completed | cleanup")
            return 2
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        return 1
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    except g.Pg62Refused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    return 0


if __name__ == "__main__":
    import _ops_completed_replay_real as runner          # the one module object (fake checks can reach it)
    sys.exit(runner.main(sys.argv[1:]))
