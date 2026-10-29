"""LQ1 subscribed-card access lock on a real local PostgreSQL (OPS_MIGRATION_ACCESS_LOCK_REAL_PG_PLAN), run explicitly,
never by discovery and never by import:

    python tests/_ops_access_lock_real.py prepare             # V2: pg68 cluster, TLS, roles, template + check DBs
    python tests/_ops_access_lock_real.py check-access-lock   # V3: G0 + G1 (not counted), 24 checks, post-check
    python tests/_ops_access_lock_real.py cleanup             # V4: R2, refused after an unconfirmed thread end

V1 = this code and its PG-free fake checks only; none of the three phases is approved. The admin row changes,
role settings and privilege changes are closed lists here and stay locked until the V3 decision is written into
LQ4_CHANGES_APPROVED below (never by an argument or an environment value). The command line takes exactly one
of the three phase words: no target, role, database, check subset or repeat count can be chosen.

The target is the closed layout `_ops_real_layout.PG68` (C:/JV_Tools/pg68, localhost:55522, roles jpvk_*), passed
explicitly to every shared function. The PG67 runner and its module values are not imported or replaced; the RS4
runner is used for its target-free instrumentation only. The shared `race` is not used: `coordinate` below adds
the plan 2-5 end check (release, bounded join, close only this check's connections, bounded join again).

Cards: account a's subscribed l1 and l2. The common SEED is unchanged; this runner's own template step adds deck B
(word l2 only) with account a's B subscription INACTIVE, and `prepare` activates it only in the five two-path DBs
(plan 4-0) before G1. Expected values come from the contract (RACE_PLAN 11절) and the plan, never from a run.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
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

LAYOUT = lay.PG68
T = LAYOUT.target
TEMPLATE = LAYOUT.template
CHECK_DB = LAYOUT.check_db
READ, WRITE = LAYOUT.read, LAYOUT.write
BUSINESS_ROLES = LAYOUT.business_roles
SYN = lay.SYN
CheckFailed, expect = lay.CheckFailed, lay.expect
RUN_KEY = "access-lock-1"
T0 = sigtests.T0
POST = "post_check"
NAMES = ("l1", "l2")

# LQ4 (admin row changes, role settings, privilege changes, admin deadlock_timeout): code only in V1. Anything but
# True stops `check-access-lock` before G0 with exit 1. Changed only by editing this value after the V3 decision.
LQ4_CHANGES_APPROVED: bool | None = None

# The fixed checklist (plan 4-2, E4: 24 checks), one database each, in this order.
PLANNED = ("k1", "k2a", "k2b", "k3", "s1", "s2", "s3", "s3b", "s4", "r1", "r2", "r3", "r4a", "r4b", "r5", "r6",
           "c1a", "c1b", "t1", "d1", "w1a", "w1b", "w2a", "w2b")
# Plan 4-0: the DBs whose account-a deck-B subscription is activated in preparation (two l2 paths); all others one.
TWO_PATH = ("r6", "c1a", "c1b", "w1b", "w2b")
OTHER_ACCOUNTS = ("b", "c")
WAIT_LIMIT = lay.WAIT_LIMIT
ACCESS_TABLES = ("user_deck_subscriptions", "shared_deck_words")
SET_PREFIX = "SELECT pg_catalog.set_config('lock_timeout'"
LOCK_PREFIX = "SELECT subscriptions.id AS subscription_id"
CARD_LOCK_PREFIX = "SELECT * FROM user_word_progress WHERE"
SUMMARY_PREFIX = "UPDATE srs_migration_runs SET summary_json"
# Contract (RACE_PLAN 11-1): 5000 ms is set only when the effective value is 0 or longer; then the previous value.
LIMIT_TEXT = "5000ms"
# The previous `current_setting('lock_timeout')` text per check DB (role settings of plan 3절; default 0).
PREVIOUS = {"s2": "10s", "s3": "2s", "s3b": "5s"}
NOT_TIGHTENED = ("s3", "s3b")
SQLSTATE_TIMEOUT, SQLSTATE_DEADLOCK = "55P03", "40P01"


PAUSE_LIMIT = WAIT_LIMIT          # how long a pause holds a business connection at most (then it times out)


class HoldPause(lay.Pause):
    """lay.Pause with an explicit holding state: `holding` is true only while the hook waits for the release; a
    pause that ran out (`timed_out`) or never held is never "still held" (plan 13절 defect 2)."""

    def __init__(self, role: str, word: str, prefix: str, limit: float | None = None):
        super().__init__(role, word, prefix, PAUSE_LIMIT if limit is None else limit)
        self._state = threading.Lock()
        self.holding = False

    def hook(self, role: str, word: str, query: Any, tracker: Any) -> None:
        text = query if isinstance(query, str) else ""
        if self.reached.is_set() or role != self.role or word != self.word or not text.startswith(self.prefix):
            return
        self.holder_pid = tracker.pending_pid
        with self._state:
            self.holding = True
        self.reached.set()
        released = self.release.wait(self.limit)
        with self._state:
            self.holding = False
            if not released:
                self.timed_out = True

    def still_held(self) -> bool:
        with self._state:
            return self.holding and not self.timed_out and not self.release.is_set()


def expected_paths(check_id: str) -> int:
    return 2 if check_id in TWO_PATH else 1


# --- PG68-bound helpers: the shared functions with this runner's layout passed explicitly -------------------

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


class Counts(lay.Counts):
    def __init__(self):
        super().__init__(BUSINESS_ROLES)


ORIGINAL_CONNECTOR = lay.ORIGINAL_CONNECTOR


class RunScopes(lay.RunScopes):
    def __init__(self, real: Callable | None = None):
        super().__init__(LAYOUT, real or ORIGINAL_CONNECTOR)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- preparation: the common template, then this runner's deck B (plan 4-0, E2) ----------------------------

# Deck B holds ONLY the lexeme l2 (the second synthetic lexeme, by base form); account a's subscription is INACTIVE.
DECK_B = [
    "INSERT INTO shared_decks (owner_user_id, title, description, visibility, vocab_count, custom_term_count, "
    f"import_count, created_at, updated_at) SELECT id, 'access lock deck b', '', 'public', 1, 0, 0, {lay.STAMP}, "
    f"{lay.STAMP} FROM users WHERE email = 'dev@example.local'",
    "INSERT INTO shared_deck_words (shared_deck_id, lexeme_id, sort_order, created_at) SELECT s.id, l.id, 1, "
    f"{lay.STAMP} FROM shared_decks s CROSS JOIN lexemes l WHERE s.title = 'access lock deck b' "
    "AND l.source_type = 'synthetic' AND l.base_form = '海'",
    "INSERT INTO user_deck_subscriptions (user_id, shared_deck_id, is_active, imported_at, created_at, updated_at) "
    f"SELECT u.id, s.id, FALSE, {lay.STAMP}, {lay.STAMP}, {lay.STAMP} FROM users u CROSS JOIN shared_decks s "
    "WHERE u.email = 'apply-a@example.test' AND s.title = 'access lock deck b'",
]


def access_ids(conn: Any, ids: dict) -> dict:
    """The access-path row ids of account a (subscription and word rows of decks A and B), by key."""
    uid = ids["a"]["user_id"]
    l1, l2 = ids["a"]["lexeme"]
    decks = dict(conn.execute("SELECT title, id FROM shared_decks WHERE title IN ('apply shared', "
                              "'access lock deck b')").fetchall())
    expect(set(decks) == {"apply shared", "access lock deck b"}, "two decks", "preparation_failure")
    a, b = decks["apply shared"], decks["access lock deck b"]
    subs = dict(conn.execute("SELECT shared_deck_id, id FROM user_deck_subscriptions WHERE user_id = %s",
                             (uid,)).fetchall())
    words = {(d, lx): i for i, d, lx in conn.execute(
        "SELECT id, shared_deck_id, lexeme_id FROM shared_deck_words WHERE shared_deck_id = ANY (%s)",
        ([a, b],)).fetchall()}
    expect(set(subs) == {a, b} and set(words) == {(a, l1), (a, l2), (b, l2)}, "access rows", "preparation_failure")
    return {"deck_a": a, "deck_b": b, "sub_a": subs[a], "sub_b": subs[b], "word_a_l1": words[(a, l1)],
            "word_a_l2": words[(a, l2)], "word_b_l2": words[(b, l2)]}


def build_template(pid: int, rec: g.Record) -> dict:
    ids = lay.build_template(LAYOUT, pid, rec, lambda db, p, autocommit=True: admin(db, p, autocommit))
    raw = admin(TEMPLATE, pid, autocommit=False)
    try:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(LAYOUT.owner)))
        for statement in DECK_B:
            raw.execute(statement)
        raw.execute("RESET ROLE")
        raw.commit()
        ids["access"] = access_ids(raw, ids)
        raw.rollback()
    finally:
        raw.close()
    rec.event("access_paths_seeded", database=TEMPLATE, statements=len(DECK_B), deck_b_subscription="inactive")
    return ids


def two_path_statement() -> str:
    return "UPDATE user_deck_subscriptions SET is_active = TRUE WHERE id = %s AND user_id = %s AND is_active = FALSE"


def prepare() -> None:
    lay.prepare(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit),
                build_fn=lambda p, rec: build_template(p, rec), grants_fn=lambda db: contract_grants(db))
    rec = g.single_run(T)
    target = require_target_bound(rec, (rec.folder / "target.json").read_bytes())
    access, uid = target["synthetic"]["access"], target["synthetic"]["a"]["user_id"]
    for check_id in TWO_PATH:                                  # plan 4-0: before G1, these DBs only
        with admin(CHECK_DB[check_id], target["postmaster_pid"]) as conn:
            changed = conn.execute(two_path_statement(), (access["sub_b"], uid)).rowcount
        expect(changed == 1, f"{check_id}: deck B subscription not activated", "preparation_failure")
        rec.event("second_path_enabled", database=CHECK_DB[check_id], subscription=access["sub_b"])


# --- the run record of this runner: several threads write it (plan 13절 defect 1) -------------------------------

class LockedRecord(g.Record):
    """The shared Record with ONE lock around the whole append: in-memory update, save, and undo on a failed save
    (so an undo can only remove its own entry). Reads of the saved file take the same lock. The shared class and
    its behaviour for other runners are unchanged."""

    def __init__(self, folder: Path):
        super().__init__(folder)
        self._lock = threading.RLock()

    def _append(self, key: str, entry: dict) -> None:
        with self._lock:
            self.doc[key].append(entry)
            try:
                self._save()
            except BaseException:
                self.doc[key].pop()
                raise

    def find(self, kind: str) -> list[dict]:
        with self._lock:
            return [e for e in self.doc["events"] if e["kind"] == kind]

    def read_saved(self) -> dict:
        with self._lock:
            return json.loads(self.path.read_text(encoding="utf-8"))


# --- record facts (plan 2-5 / 13-0): an unconfirmed thread end blocks the destructive R2 ----------------------

BLOCKING_EVENTS = ("thread_not_ended", "cleanup_incomplete")
STARTS = {"coordination_started": ("coordination_ended", "coordination_unconfirmed"),
          "final_cleanup_started": ("final_cleanup_ended", "final_cleanup_unconfirmed")}


def blocking_events(record_file: Path) -> list[str]:
    """Kinds of the recorded events that forbid R2 (read from disk; an unreadable record also forbids it). A
    `coordination_started` without its `coordination_ended` is `coordination_unconfirmed`: it blocks even when
    the failure record itself could not be saved."""
    try:
        events = json.loads(record_file.read_text(encoding="utf-8"))["events"]
    except (OSError, ValueError, KeyError, TypeError):
        return ["record_unreadable"]
    kinds = [e.get("kind") for e in events if e.get("kind") in BLOCKING_EVENTS]
    for start, (end, unconfirmed) in STARTS.items():
        started = {e.get("token") for e in events if e.get("kind") == start}
        ended = {e.get("token") for e in events if e.get("kind") == end}
        if started - ended:
            kinds.append(unconfirmed)
    return kinds


def cleanup() -> None:
    rec = g.single_run(T)
    blocked = blocking_events(rec.folder / "record.json")
    if blocked:
        raise CheckFailed("harness_defect", f"R2 refused: recorded {sorted(set(blocked))}; nothing deleted")
    lay.cleanup(LAYOUT, admin_fn=lambda db, p, autocommit=True: admin(db, p, autocommit))


# --- business connection instrumentation -------------------------------------------------------------------

class AccessTracked(rr.ResumeTracked):
    """ResumeTracked plus, after the hand-over: each `set_config('lock_timeout', ...)` value and its success, the
    SQLSTATE (only) of a failed statement, and any write to the two access tables. The call, its result and its
    exception are passed on unchanged."""

    _OWN = rr.ResumeTracked._OWN | frozenset({"settings", "sqlstates", "access_writes"})

    def __init__(self, conn: Any, counts: Counts, role: str, hooks: list):
        super().__init__(conn, counts, role, hooks)
        object.__setattr__(self, "settings", [])
        object.__setattr__(self, "sqlstates", [])
        object.__setattr__(self, "access_writes", [])

    def execute(self, query, *args, **kwargs):
        text = query if isinstance(query, str) else ""
        setting = None
        if self.active:
            if text.startswith(SET_PREFIX):
                params = args[0] if args else kwargs.get("params")
                setting = {"value": params[0] if params else None, "ok": False}
                self.settings.append(setting)
            if lay.first_word(query) in lay.WRITE_WORDS and re.search(r"\b(%s)\b" % "|".join(ACCESS_TABLES), text):
                self.access_writes.append(lay.first_word(query))
        try:
            result = super().execute(query, *args, **kwargs)
        except BaseException as error:
            state = getattr(error, "sqlstate", None)
            if self.active and isinstance(state, str):
                self.sqlstates.append({"statement": rr.label(query), "sqlstate": state})
            raise
        if setting is not None:
            setting["ok"] = True
        return result


def run_trace(trackers: list) -> dict:
    """The settings, SQLSTATEs and access-table writes of one run's handed connections."""
    return {"settings": [dict(s) for t in trackers for s in t.settings],
            "sqlstates": [dict(s) for t in trackers for s in t.sqlstates],
            "access_writes": [w for t in trackers for w in t.access_writes]}


def settings_expected(check_id: str, *, path_judged: bool, failed: bool) -> list[dict]:
    """Contract 11-1: tighten to 5000 ms only when the effective value is 0 or longer, restore the previous value
    after a NORMAL return (also with 0 rows), send nothing after a failed lock statement."""
    if check_id in NOT_TIGHTENED or not path_judged:
        return []
    if failed:
        return [{"value": LIMIT_TEXT, "ok": True}]
    return [{"value": LIMIT_TEXT, "ok": True}, {"value": PREVIOUS.get(check_id, "0"), "ok": True}]


# --- cases --------------------------------------------------------------------------------------------------

@dataclasses.dataclass
class FinalCleanup:
    failures: list = dataclasses.field(default_factory=list)       # fixed step codes only
    interrupts: list = dataclasses.field(default_factory=list)     # in the order they happened


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


def card_keys(ids: dict) -> list[tuple[str, int, int]]:
    lexeme = list(ids.get("lexeme", []))
    if len(lexeme) != 2 or len(set(lexeme)) != 2:
        raise CheckFailed("harness_defect", "the recorded account has not exactly two lexemes")
    return [("lexeme", ids["user_id"], lexeme[0]), ("lexeme", ids["user_id"], lexeme[1])]


def key_text(key: tuple[str, int, int]) -> str:
    return f"{key[0]}:{key[1]}:{key[2]}"


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
        self.pauses: list[lay.Pause] = []
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
        """Plan 13-3: every step tried in order, none skipped after an error or interrupt: release the pauses, close
        each owned connection, close the test keys, remove this run's deploy folders (then confirm they are gone),
        clear the secrets in memory. Never raises: fixed step codes and the interrupts are returned."""
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
        for conn in list(self.connections):
            step("connection_close", conn.close)
        if self.keys is not None:
            step("keys_cleanup", self.keys.close)

        def remove_folder(folder: str) -> None:
            shutil.rmtree(folder)
            if os.path.lexists(folder):
                done.failures.append("deploy_folder_unconfirmed")

        for folder in list(self.folders):
            step("deploy_folder", lambda f=folder: remove_folder(f))
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
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg68_deploy_"))
        self.folders.append(folder)
        for rel, data in self.files().items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder

    def case(self, check_id: str) -> Case:
        """Plan, approvals and inputs of one check DB: the REAL CLI dry-run (read pre-check, provider, product)
        writes the plan; I0 / A0 / E0 / E1 are signed with the temporary test keys."""
        db = CHECK_DB[check_id]
        ids = self.target["synthetic"]["a"]
        keys = card_keys(ids)
        uid = ids["user_id"]
        req = cli.make_request(uid, RUN_KEY, [], [r for _, _, r in keys])
        read_exp, write_exp = expected_profiles(db)
        read_profile = pv.expected_profile_fingerprint(read_exp, role=READ, access="read")
        write_profile = pv.expected_profile_fingerprint(write_exp, role=WRITE, access="write")
        folder = self.deploy()
        manifest = pf.manifest_doc(self.files())
        target_obs = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                          identity_value=self.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target_obs)
        read_step = {"command": "dry_run", "access": "read", "role": READ, "profile": read_profile}
        inquiry_doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000068",
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
        ev0 = self.write_evidence(folder, "evidence0", db_identity, uid, "bkp-0000000000000680")
        ev1 = self.write_evidence(folder, "evidence1", db_identity, uid, "bkp-0000000000000681")
        a0_doc = dict(inquiry_doc, kind="apply", approval_id="app-0000000000000680", plan={str(uid): printed},
                      based_on={"approval_id": inquiry_doc["approval_id"], "sha256": sha(inquiry)},
                      steps=[read_step, {"command": "apply", "access": "write", "role": WRITE, "profile": write_profile,
                                         "args": {"batch_size": "1"}}],
                      format_version=3, backup_evidence={"sha256": sha(Path(ev0[0]).read_bytes())})
        a0 = json.dumps(a0_doc).encode()
        shared = dict(common, approval=a0, approval_signature=self.sign(a0, "approval"), inquiry=inquiry,
                      inquiry_signature=self.sign(inquiry, "approval"), product_fingerprint=plan.product_fingerprint,
                      artifact_sha256=plan.artifact_sha256)
        first_write = op.PreflightInput(command="apply", args={"batch_size": "1"}, secret_dsn=dsn(WRITE),
                                        connection=op.ConnectionObservation(profile=write_profile, read_only=False),
                                        **shared)
        first_read = op.PreflightInput(command="dry_run", args={}, secret_dsn=dsn(READ),
                                       connection=op.ConnectionObservation(profile=read_profile, read_only=True),
                                       **shared)
        return Case(check_id, db, keys, req, plan, plan_path, folder, manifest, inquiry, a0, first_write,
                    first_read, ev0, ev1, read_exp, write_exp, read_profile, write_profile, db_identity, dsn, common)

    def write_evidence(self, folder: str, name: str, db_identity: str, uid: int, evidence_id: str) -> tuple[str, str]:
        doc = {"format": be.FORMAT, "format_version": 1, "evidence_id": evidence_id, "purpose": "synthetic",
               "db_identity": db_identity, "account_id": uid, "job_key": RUN_KEY, "backup_id": "synthetic-backup-68",
               "taken_at": "2026-10-21T12:05:00Z", "method": "synthetic",
               "artifact_sha256": sha(b"synthetic backup"), "valid_until": "2026-10-21T12:50:00Z",
               "attested_by": "synthetic signer", "restore_verified": False}
        data = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
        path, sig = os.path.join(folder, name + ".json"), os.path.join(folder, name + ".sig")
        Path(path).write_bytes(data)
        Path(sig).write_bytes(self.sign(data, "backup"))
        return path, sig

    def resume_inputs(self, case: Case, batch: int, approval_id: str = "app-0000000000000681") -> tuple[Any, Any]:
        doc = json.loads(case.a0)
        doc.pop("backup_evidence", None)
        doc.update(approval_id=approval_id, format_version=3,
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
            tracked = AccessTracked(conn, counts, kwargs["user"], hooks if hooks is not None else [])
            trackers.append(tracked)
            return tracked
        return connect

    def first_apply(self, case: Case) -> tuple[dict, int]:
        counts, trackers = Counts(), []
        scopes = RunScopes()
        with scopes.installed(), scopes.run(counts, trackers):
            return cli.run_apply(case.request, batch_size=1, write_inputs=case.first_write,
                                 read_inputs=case.first_read,
                                 scope=cli.ProfileScope(lay.expected_objects(case.db), lay.real.SEARCH_PATH,
                                                        lay.TLS_VERSIONS),
                                 driver=self.driver(case.first_write, counts, trackers), plan_path=case.plan_path,
                                 evidence_path=case.initial_evidence[0],
                                 evidence_signature_path=case.initial_evidence[1], clock=lay.ticking(T0))

    def resume(self, case: Case, *, hooks: list | None = None, trackers: list | None = None,
               approval_id: str = "app-0000000000000681") -> dict:
        """One explicit `resume` (batch 1: the remaining l2) through the REAL CLI, provider and product. `trackers`
        may be passed in so a coordinator can read the waiting connection while the run is going."""
        counts, trackers = Counts(), (trackers if trackers is not None else [])
        scopes = RunScopes()
        write, read = self.resume_inputs(case, 1, approval_id)
        with scopes.installed(), scopes.run(counts, trackers):
            out, code = cli.run_resume(case.request, batch_size=1, write_inputs=write, read_inputs=read,
                                       scope=cli.ProfileScope(lay.expected_objects(case.db), lay.real.SEARCH_PATH,
                                                              lay.TLS_VERSIONS),
                                       driver=self.driver(write, counts, trackers, hooks), plan_path=case.plan_path,
                                       initial_evidence_path=case.initial_evidence[0],
                                       initial_evidence_signature_path=case.initial_evidence[1],
                                       evidence_path=case.new_evidence[0], evidence_signature_path=case.new_evidence[1],
                                       clock=lay.ticking(T0))
        return {"out": out, "code": code, "counts": counts, "trackers": trackers, "trace": run_trace(trackers)}

    # -- admin facts (read only) ------------------------------------------------------------------------------
    def state(self, case: Case) -> dict:
        """Admin read by key: run row (count, status, cursor, finished, results), both cards (version, engine,
        full row text), every snapshot row of the run."""
        with admin(case.db, self.pid) as conn:
            runs = conn.execute("SELECT status, summary_json, finished_at FROM srs_migration_runs WHERE run_key = %s",
                                (RUN_KEY,)).fetchall()
            cards = {}
            for kind, user, ref in case.keys:
                row = conn.execute("SELECT t.srs_card_version, t.srs_engine, t::text FROM public.user_word_progress "
                                   "AS t WHERE t.user_id = %s AND t.lexeme_id = %s", (user, ref)).fetchone()
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

    def paths(self, check_id: str) -> dict:
        """Account a's ACTIVE access paths (subscription id, word id) per lexeme name, ordered as the contract."""
        ids = self.target["synthetic"]["a"]
        out = {}
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for name, lexeme in zip(NAMES, ids["lexeme"]):
                out[name] = [list(r) for r in conn.execute(
                    "SELECT s.id, w.id FROM user_deck_subscriptions AS s JOIN shared_deck_words AS w "
                    "ON w.shared_deck_id = s.shared_deck_id WHERE s.user_id = %s AND s.is_active = TRUE "
                    "AND w.lexeme_id = %s ORDER BY s.id, w.id", (ids["user_id"], lexeme)).fetchall()]
        return out

    def column_grants(self, check_id: str) -> dict:
        with admin(CHECK_DB[check_id], self.pid) as conn:
            return {f"{t}.{c}": conn.execute("SELECT pg_catalog.has_column_privilege(%s, %s, %s, 'UPDATE')",
                                             (WRITE, f"public.{t}", c)).fetchone()[0]
                    for t, c in (("user_deck_subscriptions", "updated_at"), ("shared_deck_words", "created_at"))}

    def outside(self, check_id: str, case: Case) -> dict:
        """Rows no run may change, by key: accounts b and c (personal cards, progress rows incl. l1 / l2), every
        lexeme log, account a's personal cards. Account ids are bound."""
        ids = self.target["synthetic"]
        lexemes = [r for _, _, r in case.keys]
        out: dict[str, str] = {}
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for account in OTHER_ACCOUNTS + ("a",):
                uid = ids[account]["user_id"]
                for ref, text in conn.execute("SELECT id, v::text FROM vocab_items AS v WHERE user_id = %s "
                                              "ORDER BY id", (uid,)).fetchall():
                    out[f"{account}:personal:{ref}"] = text
                if account in OTHER_ACCOUNTS:
                    for ref, text in conn.execute("SELECT lexeme_id, p::text FROM user_word_progress AS p "
                                                  "WHERE user_id = %s ORDER BY lexeme_id", (uid,)).fetchall():
                        out[f"{account}:lexeme:{ref}"] = text
                    missing = [r for r in lexemes if f"{account}:lexeme:{r}" not in out]
                    expect(not missing, f"{check_id}: account {account} lacks lexemes {missing}", "harness_defect")
            for ref, text in conn.execute("SELECT id, l::text FROM lexeme_review_logs AS l ORDER BY id").fetchall():
                out[f"log:{ref}"] = text
        return out

    def sessions(self) -> dict:
        with admin("postgres", self.pid) as conn:
            rows = conn.execute("SELECT usename, state FROM pg_catalog.pg_stat_activity WHERE usename = ANY (%s)",
                                (list(BUSINESS_ROLES),)).fetchall()
            waiting = conn.execute("SELECT count(*) FROM pg_catalog.pg_locks WHERE NOT granted").fetchone()[0]
        return {"open": len(rows), "idle_in_transaction": sum(1 for r in rows if r[1] == "idle in transaction"),
                "ungranted_locks": waiting}

    # -- probes (separate admin connection, never a business one) ---------------------------------------------
    def blocking_pids(self, pid: int) -> list:
        with admin("postgres", self.pid) as conn:
            return list(conn.execute("SELECT pg_catalog.pg_blocking_pids(%s)", (pid,)).fetchone()[0] or [])

    def lock_rows(self, pid: int) -> list[dict]:
        with admin("postgres", self.pid) as conn:
            return [{"locktype": r[0], "mode": r[1], "transactionid": r[2], "relation": r[3]} for r in conn.execute(
                "SELECT locktype, mode, transactionid::text, relation::regclass::text FROM pg_catalog.pg_locks "
                "WHERE pid = %s AND NOT granted ORDER BY locktype", (pid,)).fetchall()]

    def backend_xid(self, pid: int) -> str | None:
        with admin("postgres", self.pid) as conn:
            row = conn.execute("SELECT backend_xid::text FROM pg_catalog.pg_stat_activity WHERE pid = %s",
                               (pid,)).fetchone()
        return None if row is None else row[0]

    # -- closed changes ---------------------------------------------------------------------------------------
    def approved(self, what: str) -> None:
        expect(LQ4_CHANGES_APPROVED is True, f"{what} not approved (LQ4 / V3)", "harness_defect")

    def variant(self, check_id: str, name: str, phase: str) -> None:
        self.approved("privilege / role-setting changes")
        expect(check_id in LAYOUT.variant_databases[name], "variant outside its check DB", "harness_defect")
        with admin(CHECK_DB[check_id], self.pid) as conn:
            for statement in variant_statements(name, phase):
                conn.execute(statement)
        self.rec.event("privilege_variant", name=name, phase=phase, database=CHECK_DB[check_id])

    def admin_tx(self, check_id: str, owned: list) -> "AdminTx":
        self.approved("admin row changes")
        tx = AdminTx(self, check_id)
        owned.append(tx)
        return tx

    def observe_role(self, case: Case, role: str) -> dict:
        """After a revert: ONE connection of `role` through the real adapter and provider (pre-check, observation,
        judgement, re-judgement), its own counts, taken once and closed with no business context."""
        write, read = self.resume_inputs(case, 1)
        inputs, expected, access = ((read, case.read_expected, "read") if role == READ
                                    else (write, case.write_expected, "write"))
        counts, trackers = Counts(), []
        ar.fix_app_environment()
        try:
            handoff = ad.provide_with_adapter(dataclasses.replace(inputs, now=lay.ticking(T0)()), expected=expected,
                                              driver=self.driver(inputs, counts, trackers))
            raw = handoff.take()
        except pv.OpsProviderRefused as refused:
            for tracked in trackers:
                observation_close(tracked)
            return {"result": refused.code, "counts": counts.role(role)}
        expect(len(trackers) == 1 and raw is trackers[0], "one hand-over must follow exactly one connection",
               "harness_defect")
        raw.activate()
        counts.handed[role] += 1
        result = "matches_contract" if handoff.summary.access == access else "connection_access_mismatch"
        if not observation_close(raw):
            result = "connection_close_unconfirmed"
        return {"result": result, "counts": counts.role(role)}


# --- closed admin row changes (plan 3절): bound keys only, recorded per statement ------------------------------

ADMIN_SQL = {
    "deactivate": "UPDATE user_deck_subscriptions SET is_active = FALSE WHERE id = %s AND user_id = %s "
                  "AND is_active = TRUE",
    "reactivate": "UPDATE user_deck_subscriptions SET is_active = TRUE WHERE id = %s AND user_id = %s "
                  "AND is_active = FALSE",
    "word_read": "SELECT w.id, w.shared_deck_id, w.lexeme_id, w.sort_order, w.created_at, w.display_meaning_ko, "
                 "w.example_sentence, w.context_explanation_ko, w.tags_json, w.published_note, w::text "
                 "FROM shared_deck_words AS w WHERE w.shared_deck_id = %s AND w.lexeme_id = %s",
    "word_delete": "DELETE FROM shared_deck_words WHERE id = %s AND shared_deck_id = %s AND lexeme_id = %s",
    "word_restore": "INSERT INTO shared_deck_words (id, shared_deck_id, lexeme_id, sort_order, created_at, "
                    "display_meaning_ko, example_sentence, context_explanation_ko, tags_json, published_note) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
    "path_hold": "SELECT id FROM user_deck_subscriptions WHERE id = %s AND user_id = %s FOR UPDATE",
    "card_request": "SELECT id FROM user_word_progress WHERE user_id = %s AND lexeme_id = %s FOR UPDATE",
    "deadlock_wait": "SET LOCAL deadlock_timeout = '60s'",                       # E3: this admin transaction only
}


class AdminTx:
    """One admin transaction of one check (autocommit off). Each statement is a closed name with bound keys,
    recorded with its affected rows; the backend PID and transaction id are read on the same connection."""

    def __init__(self, h: Harness, check_id: str):
        self.h, self.check_id = h, check_id
        self.conn = admin(CHECK_DB[check_id], h.pid, autocommit=False)
        h.connections.append(self.conn)
        self.pid = self.conn.execute("SELECT pg_catalog.pg_backend_pid()").fetchone()[0]
        self.sqlstate: str | None = None
        self.ended: str | None = None

    def run(self, name: str, params: tuple = ()) -> Any:
        try:
            cursor = self.conn.execute(ADMIN_SQL[name], params)
        except BaseException as error:
            state = getattr(error, "sqlstate", None)
            self.sqlstate = state if isinstance(state, str) else None
            self.h.rec.event("admin_change", check=self.check_id, name=name, result="error", sqlstate=self.sqlstate)
            raise
        self.h.rec.event("admin_change", check=self.check_id, name=name, rows=cursor.rowcount)
        return cursor

    def xid(self) -> str | None:
        return self.conn.execute("SELECT pg_catalog.pg_current_xact_id_if_assigned()::text").fetchone()[0]

    def commit(self) -> None:
        self.conn.commit()
        self.ended = "commit"
        self.h.rec.event("admin_change", check=self.check_id, name="commit")

    def rollback(self) -> None:
        self.conn.rollback()
        self.ended = "rollback"
        self.h.rec.event("admin_change", check=self.check_id, name="rollback")

    def close(self) -> None:
        self.conn.close()


# --- coordination (plan 2-5): release, bounded join, close owned connections only, bounded join again ----------

@dataclasses.dataclass
class Coordinated:
    results: dict                    # thread name -> ("ok", value) | ("error", exception)
    proof: dict                      # probe results (or {"probe_error": type name})
    cleanup: dict                    # released, joined, closed, still_alive


_TOKENS = itertools.count(1)


def _bare(error: BaseException) -> BaseException:
    """The same object without a chained cause or context (no driver text in a traceback)."""
    error.__cause__ = None
    error.__context__ = None
    error.__suppress_context__ = True
    return error


def coordinate(h: Any, check_id: str, steps: list[tuple[str, Callable[[], Any]]], *, pause: Any = None,
               prove: Callable[[], dict] | None, owned: Callable[[], list], limit: float = WAIT_LIMIT,
               between: Callable[[], None] | None = None, release: tuple = ()) -> Coordinated:
    """Plan 2-5 / 13-0. `coordination_started` is saved first (no thread starts if that fails). Start the threads
    (the first runs until it holds at `pause`, when given), then `prove` (probes on a separate connection) and
    `between` (harness actions). Whatever happens, every cleanup step is tried in order: release the pauses /
    events, join with a limit, if a thread is still alive close ONLY the connections `owned()` returns, join again
    and check `is_alive`; extra errors / interrupts of a step are recorded and the next step still runs.
    `coordination_ended` is saved only for a confirmed end. Then, by priority: a worker's interrupt (same object),
    the harness's own first interrupt (same object), an unconfirmed end, a pause that timed out or never held, a
    record failure, a probe error. A worker's ordinary error is returned for the check to judge."""
    token = f"{check_id}:{next(_TOKENS)}"
    h.rec.event("coordination_started", check=check_id, token=token)
    results: dict = {}

    def runner(name, fn):
        try:
            results[name] = ("ok", fn())
        except BaseException as error:          # carried to the harness thread, judged there
            results[name] = ("error", error)
    threads = [threading.Thread(target=runner, args=(n, fn), name=f"{check_id}:{n}", daemon=True) for n, fn in steps]
    h.threads.extend(threads)
    to_release = ([pause] if pause is not None else []) + list(release)
    pauses = [p for p in to_release if not isinstance(p, threading.Event)]
    h.pauses.extend(pauses)
    proof: dict = {}
    probe_error: BaseException | None = None
    interrupts: list[BaseException] = []           # the harness's own, in order

    def keep(error: BaseException) -> None:
        if not isinstance(error, Exception):
            interrupts.append(error)
    try:
        threads[0].start()
        if pause is not None:
            end = time.monotonic() + limit
            while not pause.reached.wait(0.05) and threads[0].is_alive() and time.monotonic() < end:
                pass
            if not pause.reached.is_set():
                raise CheckFailed("harness_defect", f"{check_id}: the first run did not reach the pause")
        for thread in threads[1:]:
            thread.start()
        if prove is not None:
            proof = prove()
        if between is not None:
            between()
    except Exception as error:                  # probe / harness failure: kept apart, never thrown before the end
        probe_error = error
        proof = {"probe_error": type(error).__name__}
    except BaseException as error:              # the harness's own interrupt: kept, cleanup goes on first
        keep(error)
        proof = {"probe_interrupt": type(error).__name__}
    cleanup: dict = {"released": bool(to_release), "release_errors": [], "joined": False, "closed": None,
                     "still_alive": [], "pauses": []}
    for item in to_release:
        try:
            item.set() if isinstance(item, threading.Event) else item.release.set()
        except BaseException as error:
            cleanup["release_errors"].append(type(error).__name__)
            keep(error)

    def join_all() -> None:
        for thread in threads:
            if thread.ident is not None:
                try:
                    thread.join(limit)
                except BaseException as error:
                    keep(error)
    join_all()
    alive = [t.name for t in threads if t.is_alive()]
    if alive:
        closed: list[str] = []
        try:
            conns = list(owned())
        except BaseException as error:
            conns = []
            closed.append(f"owned_failed:{type(error).__name__}")
            keep(error)
        for conn in conns:
            try:
                conn.close()
                closed.append("closed")
            except Exception as error:
                closed.append(f"close_failed:{type(error).__name__}")
            except BaseException as error:
                closed.append(f"close_interrupted:{type(error).__name__}")
                keep(error)
        cleanup["closed"] = closed
        join_all()
        alive = [t.name for t in threads if t.is_alive()]
    cleanup["still_alive"] = alive
    cleanup["joined"] = not alive
    for item in pauses:
        if getattr(item, "timed_out", False):
            cleanup["pauses"].append("timed_out")
        elif not item.reached.is_set():
            cleanup["pauses"].append("not_reached")
    business = {n: ("ok" if r[0] == "ok" else ("error:" if isinstance(r[1], Exception) else "interrupt:")
                    + type(r[1]).__name__) for n, r in results.items()}
    record_error: BaseException | None = None
    for kind, facts in (("coordination", dict(business=business, probe=proof, cleanup=cleanup)),) + (
            (("thread_not_ended", dict(threads=alive)), ("cleanup_incomplete", dict(reason="thread end not confirmed")))
            if alive else (("coordination_ended", dict(token=token)),)):
        try:
            h.rec.event(kind, check=check_id, **facts)
        except BaseException as error:          # an unsaved failure record never means a safe cleanup
            record_error = record_error or error
            keep(error)
    for name, (kind, value) in results.items():
        if kind == "error" and not isinstance(value, Exception):
            raise _bare(value)                    # 1. a worker's interrupt: the same object
    if interrupts:
        raise _bare(interrupts[0])                # 2. the harness's own first interrupt
    if alive:
        raise CheckFailed("harness_defect", f"{check_id}: thread end not confirmed {alive}")
    if cleanup["pauses"]:
        raise CheckFailed("harness_defect", f"{check_id}: pause {cleanup['pauses']}")
    if record_error is not None:
        raise CheckFailed("harness_defect", f"{check_id}: record failed: {type(record_error).__name__}")
    if probe_error is not None:
        if isinstance(probe_error, CheckFailed):
            raise _bare(probe_error)
        raise CheckFailed("harness_defect", f"{check_id}: probe failed: {type(probe_error).__name__}")
    return Coordinated(results, proof, cleanup)


def prove_wait(h: Any, check_id: str, waiter: Callable[[], int | None], holder: int, holder_xid: Callable[[], Any],
               name: str) -> dict:
    """Plan 5-1: the waiter's PID, pg_blocking_pids containing the holder, the waiter's ungranted lock row(s), the
    holder's transaction id equal to the ungranted transactionid lock. relation may be NULL; never required."""
    pid = lay.wait_blocked(h.blocking_pids, waiter, holder)
    rows = h.lock_rows(pid)
    xid = holder_xid()
    proof = {"waiter": pid, "holder": holder, "holder_xid": xid, "ungranted": rows}
    h.rec.event("lock_wait_proof", check=check_id, name=name, **proof)
    expect(xid is not None and any(r["locktype"] == "transactionid" and r["transactionid"] == xid for r in rows),
           f"{check_id} {name}: the ungranted lock is not the holder's transaction {proof}", "harness_defect")
    return proof


# --- judgement helpers: expectations from the G1 baseline, the plan and the contract only -------------------------

def resume_problems(case: Case, base: dict, now: dict, *, converted: bool, status: str, cursor: int,
                    finished: bool) -> list[str]:
    """Run row, l1 untouched with its snapshot, l2 converted once (plan version + 1, fsrs) or untouched."""
    problems = []
    if (now["runs"], now["status"], now["cursor"], now["finished"]) != (1, status, cursor, finished):
        problems.append(f"run row {(now['runs'], now['status'], now['cursor'], now['finished'])} != "
                        f"{(1, status, cursor, finished)}")
    planned = {key_text(("lexeme", case.plan.account_id, c.ref_id)): c.card_version for c in case.plan.candidates}
    k1, k2 = (key_text(k) for k in case.keys)
    if now["cards"].get(k1) != base["cards"].get(k1):
        problems.append("l1 changed")
    if base["snapshots"].get(k1) is None or now["snapshots"].get(k1) != base["snapshots"].get(k1):
        problems.append("l1 snapshot changed")
    before, after = base["cards"].get(k2), now["cards"].get(k2)
    if converted:
        if after is None or (after["engine"], after["version"]) != ("fsrs", planned[k2] + 1) \
                or after["row"] == before["row"]:
            problems.append("l2 not converted once")
        snap = now["snapshots"].get(k2)
        if snap is None or snap["version_before"] != planned[k2]:
            problems.append("l2 snapshot")
        want = {k1, k2}
    else:
        if after != before:
            problems.append("l2 changed")
        want = {k1}
    if set(now["snapshots"]) != want or now["snapshot_count"] != len(want):
        problems.append(f"snapshot keys {sorted(now['snapshots'])}")
    return problems


def path_problems(h: Any, check_id: str, seen: dict, *, l2_paths: int | None = None) -> list[str]:
    """Account a's active paths against plan 4-0, by row key (l1: deck A; l2: deck A, and deck B in TWO_PATH)."""
    acc = h.target["synthetic"]["access"]
    want = {"l1": [[acc["sub_a"], acc["word_a_l1"]]],
            "l2": [[acc["sub_a"], acc["word_a_l2"]]] + ([[acc["sub_b"], acc["word_b_l2"]]]
                                                       if check_id in TWO_PATH else [])}
    if l2_paths is not None and l2_paths != len(want["l2"]):
        return [f"{check_id}: table value {l2_paths} != {len(want['l2'])}"]
    return [] if seen == want else [f"{check_id}: paths {seen} != {want}"]


def subcase(h: Any, check_id: str, name: str, ok: bool, **detail: Any) -> None:
    h.rec.event("subcase", check=check_id, name=name, ok=bool(ok), **detail)
    expect(ok, f"{check_id} {name}: {detail}")


def require_subcases(h: Any, check_id: str, names: tuple[str, ...]) -> list[str]:
    """Every required subcase of the check saved AND read back from disk as ok (plan 4-2)."""
    try:
        read = getattr(h.rec, "read_saved", None)
        saved = read() if read is not None else json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
        events = saved["events"]
    except (OSError, ValueError, KeyError, TypeError):
        raise CheckFailed("harness_defect", f"{check_id}: record not readable for subcases") from None
    seen = {e.get("name") for e in events if e.get("kind") == "subcase" and e.get("check") == check_id and e.get("ok")}
    missing = [n for n in names if n not in seen]
    expect(not missing, f"{check_id}: required subcases not recorded {missing}", "harness_defect")
    return list(names)


def judge_outcome(h: Any, check_id: str, case: Case, base: dict, result: dict, *, outcome: str,
                  path_judged: bool = True, code: str | None = None) -> dict:
    """The common checks of plan 4-2 as separate subcases: CLI report, admin-read state, settings trace, no write to
    the two access tables, other accounts / out-of-scope rows unchanged."""
    out = result["out"]
    cli_seen = {"status": out.get("status"), "code": out.get("code"), "phase": out.get("phase"),
                "results": out.get("results"), "uncertain": out.get("uncertain"), "next": out.get("next"),
                "exit": result["code"]}
    h.rec.event("check_run", check=check_id, cli=cli_seen)
    if outcome == "applied":
        want_cli = (cli_seen["phase"], cli_seen["exit"], cli_seen["results"]) == \
            ("completed", 0, {"already_applied": 1, "applied": 1})
        state = dict(converted=True, status="completed", cursor=2, finished=True)
    elif outcome == "conflict":
        want_cli = (cli_seen["phase"], cli_seen["exit"], cli_seen["results"]) == \
            ("completed", 5, {"already_applied": 1, "conflict": 1})
        state = dict(converted=False, status="completed", cursor=2, finished=True)
    elif outcome == "failed":
        want_cli = (cli_seen["status"], cli_seen["code"], cli_seen["phase"], cli_seen["uncertain"], cli_seen["next"],
                    cli_seen["exit"]) == ("failed", code, "after_start", True, "status_required", 1)
        state = dict(converted=False, status="failed", cursor=1, finished=False)
    elif outcome == "refused":
        want_cli = (cli_seen["status"], cli_seen["code"], cli_seen["phase"], cli_seen["exit"]) == \
            ("refused", code, "before_first_write", 4)
        state = dict(converted=False, status="started", cursor=1, finished=False)
    else:
        raise CheckFailed("harness_defect", f"unknown outcome {outcome}")
    subcase(h, check_id, "cli", want_cli, cli=cli_seen)
    now = h.state(case)
    problems = resume_problems(case, base, now, **state)
    h.rec.event("check_admin_state", check=check_id, state={k: now[k] for k in ("runs", "status", "cursor", "finished")})
    subcase(h, check_id, "admin_state", not problems, problems=problems)
    trace = result["trace"]
    want = settings_expected(check_id, path_judged=path_judged, failed=outcome == "failed")
    subcase(h, check_id, "settings", trace["settings"] == want, seen=trace["settings"], want=want)
    subcase(h, check_id, "access_writes", trace["access_writes"] == [], seen=trace["access_writes"])
    subcase(h, check_id, "outside", h.outside(check_id, case) == h.evidence["outside"][check_id])
    return {"cli": cli_seen, "settings": trace["settings"], "sqlstates": trace["sqlstates"]}


COMMON = ("cli", "admin_state", "settings", "access_writes", "outside")
REOBSERVED = {"created": 1, "handed": 1, "statements": 0, "writes": 0, "commits": 0}


def observation_close(conn: Any) -> bool:
    try:
        conn.close()
        return conn.closed is True
    except Exception:
        return False


def revert_and_observe(h: Any, check_id: str, case: Case, name: str, role: str) -> dict:
    """The closed revert, then the changed role observed again through the real provider path with its own counts
    (1 / 1 / 0 / 0 / 0). Anything else is a harness defect."""
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
    h.rec.event("revert_observation", check=check_id, role=role, result=seen.get("result"), counts=seen.get("counts"))
    ok = seen.get("result") == "matches_contract" and seen.get("counts") == REOBSERVED
    h.rec.event("subcase", check=check_id, name=f"reobserved_{role}", ok=ok, seen=seen)
    expect(ok, f"{check_id}: after the revert {role} is not the contract profile: {seen}", "harness_defect")
    return seen


def paths_for(h: Any, active: tuple[str, ...]) -> dict:
    """Account a's active paths expected from the RECORDED row keys when the subscriptions in `active` (deck "a",
    deck "b") are on: l1 is in deck A only, l2 in A and B (plan 4-0)."""
    acc_ = h.target["synthetic"]["access"]
    l2 = ([[acc_["sub_a"], acc_["word_a_l2"]]] if "a" in active else []) + \
        ([[acc_["sub_b"], acc_["word_b_l2"]]] if "b" in active else [])
    return {"l1": [[acc_["sub_a"], acc_["word_a_l1"]]] if "a" in active else [], "l2": sorted(l2)}


def admin_change(h: Any, check_id: str, label: str, actions: list[tuple[str, tuple]]) -> list[int]:
    """One committed admin transaction; every statement must affect exactly one row (subcase `<label>_rows`)."""
    tx = h.admin_tx(check_id, [])
    try:
        rows = [tx.run(name, params).rowcount for name, params in actions]
        tx.commit()
    finally:
        if tx.ended is None:
            tx.rollback()
        tx.close()
    subcase(h, check_id, f"{label}_rows", rows == [1] * len(actions) and tx.ended == "commit", rows=rows,
            ended=tx.ended)
    return rows


def restore_paths(h: Any, check_id: str, actions: list[tuple[str, tuple]]) -> None:
    """Reverts of this check's committed admin row changes (one row each), then the paths must equal plan 4-0."""
    admin_change(h, check_id, "revert", actions)
    problems = path_problems(h, check_id, h.paths(check_id))
    subcase(h, check_id, "paths_restored", not problems, problems=problems)


def baseline_of(h: Any, check_id: str) -> tuple[Case, dict]:
    case = h.cases.get(check_id)
    base = (h.evidence.get("baseline") or {}).get(check_id)
    expect(case is not None and base is not None, f"{check_id} needs its G1 baseline", "harness_defect")
    problems = path_problems(h, check_id, h.paths(check_id))
    expect(not problems, f"{check_id} start paths {problems}", "harness_defect")
    return case, base


def acc(h: Any) -> dict:
    return h.target["synthetic"]["access"]


def uid(h: Any) -> int:
    return h.target["synthetic"]["a"]["user_id"]


def l2_id(h: Any) -> int:
    return h.target["synthetic"]["a"]["lexeme"][1]


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
    paths, grants = {}, {}
    for check_id in PLANNED:
        seen = h.paths(check_id)
        problems = path_problems(h, check_id, seen, l2_paths=expected_paths(check_id))
        expect(not problems, f"G0 {problems}", "preparation_failure")
        paths[check_id] = len(seen["l2"])
        grants[check_id] = h.column_grants(check_id)
        expect(all(grants[check_id].values()), f"{check_id} contract column grants {grants[check_id]}",
               "preparation_failure")
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
    return {"databases": len(h.target["databases"]), "qualities": qualities, "l2_paths": paths}


def g1_gate(h: Harness) -> dict:
    """Every check DB: the REAL plan dry-run and first apply (batch 1: l1), then the baseline and the paths again."""
    made = {}
    for check_id in PLANNED:
        case = h.case(check_id)
        h.cases[check_id] = case
        before_outside = h.outside(check_id, case)
        out, code = h.first_apply(case)
        expect(code == 3, f"{check_id} first apply {out.get('code')}/{code}", "preparation_failure")
        base = h.state(case)
        planned = {key_text(("lexeme", case.plan.account_id, c.ref_id)): c.card_version for c in case.plan.candidates}
        k1, k2 = (key_text(k) for k in case.keys)
        expect((base["runs"], base["status"], base["cursor"], base["finished"]) == (1, "started", 1, False)
               and set(base["snapshots"]) == {k1} and base["cards"][k1]["engine"] == "fsrs"
               and base["cards"][k1]["version"] == planned[k1] + 1
               and (base["cards"][k2]["engine"], base["cards"][k2]["version"]) == ("legacy", planned[k2]),
               f"{check_id} initial state", "preparation_failure")
        expect(h.outside(check_id, case) == before_outside, f"{check_id} outside rows", "preparation_failure")
        problems = path_problems(h, check_id, h.paths(check_id), l2_paths=expected_paths(check_id))
        expect(not problems, f"G1 {problems}", "preparation_failure")
        h.evidence.setdefault("outside", {})[check_id] = before_outside
        h.evidence.setdefault("baseline", {})[check_id] = base
        made[check_id] = {"state": "started", "cursor": 1, "l2_paths": expected_paths(check_id)}
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0, "ungranted_locks": 0}, f"sessions {sessions}",
           "preparation_failure")
    return {"databases": len(made), "states": made}


# --- checks ---------------------------------------------------------------------------------------------------

def plain(h: Harness, check_id: str, outcome: str = "applied", *, path_judged: bool = True) -> dict:
    case, base = baseline_of(h, check_id)
    result = h.resume(case)
    details = judge_outcome(h, check_id, case, base, result, outcome=outcome, path_judged=path_judged)
    require_subcases(h, check_id, COMMON)
    return details


def k1_minimal_profile(h: Harness) -> dict:
    return plain(h, "k1")


def privilege_refused(h: Harness, check_id: str, variant: str, code: str) -> dict:
    case, base = baseline_of(h, check_id)
    h.variant(check_id, variant, "apply")
    try:
        result = h.resume(case)
    finally:
        revert_and_observe(h, check_id, case, variant, WRITE)
    details = judge_outcome(h, check_id, case, base, result, outcome="refused", path_judged=False, code=code)
    write = result["counts"].role(WRITE)
    subcase(h, check_id, "write_stage", (write["created"], write["handed"]) == (1, 0), write=write)
    require_subcases(h, check_id, COMMON + ("write_stage", f"reobserved_{WRITE}"))
    return details


def k2a_column_missing(h: Harness) -> dict:
    return privilege_refused(h, "k2a", "k2a_subscriptions_column", "observed_privileges_missing")


def k2b_column_missing(h: Harness) -> dict:
    return privilege_refused(h, "k2b", "k2b_words_column", "observed_privileges_missing")


def k3_table_excess(h: Harness) -> dict:
    return privilege_refused(h, "k3", "k3_subscriptions_table", "observed_privileges_excess")


def s1_default(h: Harness) -> dict:
    return plain(h, "s1")


def role_setting(h: Harness, check_id: str, variant: str) -> dict:
    case, base = baseline_of(h, check_id)
    h.variant(check_id, variant, "apply")
    try:
        result = h.resume(case)
    finally:
        revert_and_observe(h, check_id, case, variant, WRITE)
    details = judge_outcome(h, check_id, case, base, result, outcome="applied")
    require_subcases(h, check_id, COMMON + (f"reobserved_{WRITE}",))
    return details


def s2_longer(h: Harness) -> dict:
    return role_setting(h, "s2", "s2_lock_timeout_10s")


def s3_shorter(h: Harness) -> dict:
    return role_setting(h, "s3", "s3_lock_timeout_2s")


def s3b_exactly_5s(h: Harness) -> dict:
    return role_setting(h, "s3b", "s3b_lock_timeout_5s")


def s4_no_row(h: Harness) -> dict:
    case, base = baseline_of(h, "s4")
    admin_change(h, "s4", "loss", [("deactivate", (acc(h)["sub_a"], uid(h)))])
    seen = h.paths("s4")
    subcase(h, "s4", "loss_paths", seen == paths_for(h, ()), seen=seen)
    result = h.resume(case)
    details = judge_outcome(h, "s4", case, base, result, outcome="conflict")
    restore_paths(h, "s4", [("reactivate", (acc(h)["sub_a"], uid(h)))])
    require_subcases(h, "s4", COMMON + ("loss_rows", "loss_paths", "revert_rows", "paths_restored"))
    return details


def product_run(h: Harness, case: Case, trackers: list, hooks: list) -> Callable[[], dict]:
    return lambda: h.resume(case, hooks=hooks, trackers=trackers)


def waiter_of(trackers: list) -> Callable[[], int | None]:
    return lambda: trackers[-1].pending_pid if trackers else None


def owned_of(trackers: list, txs: list) -> Callable[[], list]:
    return lambda: list(trackers) + [tx.conn for tx in txs]


def worker_result(h: Harness, check_id: str, co: Coordinated, name: str) -> Any:
    kind, value = co.results.get(name, ("error", None))
    if kind != "ok":
        state = getattr(value, "sqlstate", None)
        raise CheckFailed("harness_defect", f"{check_id}: {name} raised {type(value).__name__} ({state})")
    return value


def r1_before_check(h: Harness) -> dict:
    """Pause after the card FOR UPDATE (before the access check); the admin deactivation commits without waiting."""
    case, base = baseline_of(h, "r1")
    trackers, txs = [], []
    pause = HoldPause(WRITE, "SELECT", CARD_LOCK_PREFIX)
    done = threading.Event()
    seen: dict = {}

    def change():
        tx = h.admin_tx("r1", txs)
        seen["rows"] = tx.run("deactivate", (acc(h)["sub_a"], uid(h))).rowcount
        tx.commit()
        seen["held_at_commit"] = pause.still_held()          # the product still held when the commit returned
        done.set()
        return "committed"
    co = coordinate(h, "r1", [("product", product_run(h, case, trackers, [pause.hook])), ("admin", change)],
                    pause=pause, prove=lambda: {"admin_committed_while_paused": done.wait(WAIT_LIMIT)
                                                and seen.get("held_at_commit") is True and seen.get("rows") == 1},
                    owned=owned_of(trackers, txs))
    subcase(h, "r1", "admin_not_blocked", co.proof.get("admin_committed_while_paused") is True, proof=co.proof)
    details = judge_outcome(h, "r1", case, base, worker_result(h, "r1", co, "product"), outcome="conflict")
    restore_paths(h, "r1", [("reactivate", (acc(h)["sub_a"], uid(h)))])
    require_subcases(h, "r1", COMMON + ("admin_not_blocked", "paths_restored"))
    return details


def locked_then_changed(h: Harness, check_id: str, prefix: str, word: str, change_name: str,
                        params: Callable[[], tuple], restore: list) -> dict:
    """The product holds at a pause AFTER it locked the path; the admin change (other thread) must wait for it
    (proved), then goes on after the product's commit."""
    case, base = baseline_of(h, check_id)
    trackers, txs = [], []
    pause = HoldPause(WRITE, word, prefix)
    holder: dict = {}

    def change():
        tx = h.admin_tx(check_id, txs)
        holder["pid"] = tx.pid
        tx.run(change_name, params())
        tx.commit()
        return "committed"

    def prove():
        return prove_wait(h, check_id, lambda: holder.get("pid"), pause.holder_pid,
                          lambda: h.backend_xid(pause.holder_pid), "admin_waits_for_product")
    co = coordinate(h, check_id, [("product", product_run(h, case, trackers, [pause.hook])), ("admin", change)],
                    pause=pause, prove=prove, owned=owned_of(trackers, txs))
    subcase(h, check_id, "admin_waited", co.proof.get("waiter") == holder.get("pid"), proof=co.proof)
    worker_result(h, check_id, co, "admin")
    details = judge_outcome(h, check_id, case, base, worker_result(h, check_id, co, "product"), outcome="applied")
    restore_paths(h, check_id, restore)
    require_subcases(h, check_id, COMMON + ("admin_waited", "paths_restored"))
    return details


def r2_after_check(h: Harness) -> dict:
    return locked_then_changed(h, "r2", LOCK_PREFIX, "SELECT", "deactivate", lambda: (acc(h)["sub_a"], uid(h)),
                               [("reactivate", (acc(h)["sub_a"], uid(h)))])


def r3_before_commit(h: Harness) -> dict:
    return locked_then_changed(h, "r3", SUMMARY_PREFIX, "UPDATE", "deactivate", lambda: (acc(h)["sub_a"], uid(h)),
                               [("reactivate", (acc(h)["sub_a"], uid(h)))])


def held_first(h: Harness, check_id: str, hold: list[tuple[str, Callable[[], tuple]]], end: str, outcome: str,
               restore: list | None, *, extra: tuple[str, ...] = ()) -> tuple[dict, Coordinated]:
    """The admin change is held uncommitted FIRST; the product's access lock waits for it (proved); then the admin
    commits or rolls back and the product re-evaluates."""
    case, base = baseline_of(h, check_id)
    trackers, txs = [], []
    tx = h.admin_tx(check_id, txs)
    for name, params in hold:
        tx.run(name, params())
    xid = tx.xid()

    def prove():
        return prove_wait(h, check_id, waiter_of(trackers), tx.pid, lambda: xid, "product_waits_for_admin")

    def between():
        (tx.commit if end == "commit" else tx.rollback)()
    try:
        co = coordinate(h, check_id, [("product", product_run(h, case, trackers, []))], pause=None, prove=prove,
                        between=between, owned=owned_of(trackers, txs))
    finally:
        if tx.ended is None:
            tx.rollback()
        tx.close()
    subcase(h, check_id, "product_waited", co.proof.get("holder") == tx.pid, proof=co.proof)
    details = judge_outcome(h, check_id, case, base, worker_result(h, check_id, co, "product"), outcome=outcome)
    if restore:
        restore_paths(h, check_id, restore)
    require_subcases(h, check_id, COMMON + ("product_waited",) + (("paths_restored",) if restore else ()) + extra)
    return details, co


def r4a_held_committed(h: Harness) -> dict:
    return held_first(h, "r4a", [("deactivate", lambda: (acc(h)["sub_a"], uid(h)))], "commit", "conflict",
                      [("reactivate", (acc(h)["sub_a"], uid(h)))])[0]


def r4b_held_rolled_back(h: Harness) -> dict:
    return held_first(h, "r4b", [("deactivate", lambda: (acc(h)["sub_a"], uid(h)))], "rollback", "applied", None)[0]


def r5_after_commit(h: Harness) -> dict:
    """l2 applied; then account a loses its only path (one row, committed): no path left, the converted card and
    the run row unchanged (LQ1-b: no rollback, no repair); then the revert (one row) and the 4-0 paths again."""
    case, base = baseline_of(h, "r5")
    result = h.resume(case)
    details = judge_outcome(h, "r5", case, base, result, outcome="applied")
    after = h.state(case)
    admin_change(h, "r5", "loss", [("deactivate", (acc(h)["sub_a"], uid(h)))])
    seen = h.paths("r5")
    subcase(h, "r5", "loss_paths", seen == paths_for(h, ()), seen=seen)
    subcase(h, "r5", "kept_after_loss", h.state(case) == after)
    restore_paths(h, "r5", [("reactivate", (acc(h)["sub_a"], uid(h)))])
    require_subcases(h, "r5", COMMON + ("loss_rows", "loss_paths", "kept_after_loss", "revert_rows",
                                        "paths_restored"))
    return details


def r6_two_paths(h: Harness) -> dict:
    """Two paths; A removed before the run (one row, committed) leaves exactly B; the product applies through B."""
    case, base = baseline_of(h, "r6")
    admin_change(h, "r6", "loss", [("deactivate", (acc(h)["sub_a"], uid(h)))])
    seen = h.paths("r6")
    subcase(h, "r6", "loss_paths", seen == paths_for(h, ("b",)), seen=seen)
    details = judge_outcome(h, "r6", case, base, h.resume(case), outcome="applied")
    restore_paths(h, "r6", [("reactivate", (acc(h)["sub_a"], uid(h)))])
    require_subcases(h, "r6", COMMON + ("loss_rows", "loss_paths", "revert_rows", "paths_restored"))
    return details


def c1a_only_returned_path(h: Harness) -> dict:
    """Two paths; the product holds after locking path A (lowest subscription id). A change of A waits; a change
    of B commits while the product still holds."""
    case, base = baseline_of(h, "c1a")
    trackers, txs = [], []
    pause = HoldPause(WRITE, "SELECT", LOCK_PREFIX)
    holder: dict = {}

    def change_a():
        tx = h.admin_tx("c1a", txs)
        holder["pid"] = tx.pid
        tx.run("deactivate", (acc(h)["sub_a"], uid(h)))
        tx.commit()
        return "committed"

    def prove():
        proof = prove_wait(h, "c1a", lambda: holder.get("pid"), pause.holder_pid,
                           lambda: h.backend_xid(pause.holder_pid), "a_waits")
        tx = h.admin_tx("c1a", txs)
        try:
            rows = tx.run("deactivate", (acc(h)["sub_b"], uid(h))).rowcount
            ungranted = h.lock_rows(tx.pid)
            tx.commit()
            held = pause.still_held()                       # explicit state, not "release not set"
        finally:
            if tx.ended is None:
                tx.rollback()
            tx.close()
        proof["b_ungranted"] = ungranted
        proof["b_committed_while_paused"] = held and rows == 1 and tx.ended == "commit"
        return proof
    co = coordinate(h, "c1a", [("product", product_run(h, case, trackers, [pause.hook])), ("admin_a", change_a)],
                    pause=pause, prove=prove, owned=owned_of(trackers, txs))
    subcase(h, "c1a", "a_waited", co.proof.get("waiter") == holder.get("pid"), proof=co.proof)
    subcase(h, "c1a", "b_not_blocked", co.proof.get("b_ungranted") == [] and co.proof.get("b_committed_while_paused"))
    worker_result(h, "c1a", co, "admin_a")
    details = judge_outcome(h, "c1a", case, base, worker_result(h, "c1a", co, "product"), outcome="applied")
    restore_paths(h, "c1a", [("reactivate", (acc(h)["sub_a"], uid(h))), ("reactivate", (acc(h)["sub_b"], uid(h)))])
    require_subcases(h, "c1a", COMMON + ("a_waited", "b_not_blocked", "paths_restored"))
    return details


def c1b_first_path_dropped(h: Harness) -> dict:
    """Two paths; A's deactivation held first; the product waits on A; after the commit it re-evaluates to B and
    holds after the lock; a change of B then waits for the product (B is the locked path)."""
    case, base = baseline_of(h, "c1b")
    trackers, txs = [], []
    pause = HoldPause(WRITE, "SELECT", LOCK_PREFIX)
    go_b = threading.Event()
    tx = h.admin_tx("c1b", txs)
    tx.run("deactivate", (acc(h)["sub_a"], uid(h)))
    xid = tx.xid()
    holder: dict = {}

    def change_b():
        if not go_b.wait(WAIT_LIMIT):
            return "not_started"
        btx = h.admin_tx("c1b", txs)
        holder["pid"] = btx.pid
        btx.run("deactivate", (acc(h)["sub_b"], uid(h)))
        btx.commit()
        return "committed"

    def prove():
        first = prove_wait(h, "c1b", waiter_of(trackers), tx.pid, lambda: xid, "product_waits_for_a")
        tx.commit()
        expect(pause.reached.wait(WAIT_LIMIT), "c1b: the product did not lock B", "harness_defect")
        go_b.set()
        second = prove_wait(h, "c1b", lambda: holder.get("pid"), pause.holder_pid,
                            lambda: h.backend_xid(pause.holder_pid), "b_waits_for_product")
        return {"first": first, "second": second}
    try:
        co = coordinate(h, "c1b", [("product", product_run(h, case, trackers, [pause.hook])), ("admin_b", change_b)],
                        pause=None, prove=prove, owned=owned_of(trackers, txs), release=(pause, go_b))
    finally:
        if tx.ended is None:
            tx.rollback()
        tx.close()
    subcase(h, "c1b", "waited_on_a", co.proof["first"]["holder"] == tx.pid, proof=co.proof["first"])
    subcase(h, "c1b", "b_locked", co.proof["second"]["waiter"] == holder.get("pid"), proof=co.proof["second"])
    expect(worker_result(h, "c1b", co, "admin_b") == "committed", "c1b: admin B change did not run", "harness_defect")
    details = judge_outcome(h, "c1b", case, base, worker_result(h, "c1b", co, "product"), outcome="applied")
    restore_paths(h, "c1b", [("reactivate", (acc(h)["sub_a"], uid(h))), ("reactivate", (acc(h)["sub_b"], uid(h)))])
    require_subcases(h, "c1b", COMMON + ("waited_on_a", "b_locked", "paths_restored"))
    return details


def t1_lock_timeout(h: Harness) -> dict:
    """The admin holds path A's subscription row; the product's access lock waits (proved), the server cancels it
    after the 5 s limit (55P03), the product reports `migration_access_lock_timeout`; then an explicit resume."""
    case, base = baseline_of(h, "t1")
    trackers, txs = [], []
    tx = h.admin_tx("t1", txs)
    tx.run("path_hold", (acc(h)["sub_a"], uid(h)))
    xid = tx.xid() or tx.conn.execute("SELECT pg_catalog.pg_current_xact_id()::text").fetchone()[0]
    try:
        co = coordinate(h, "t1", [("product", product_run(h, case, trackers, []))], pause=None,
                        prove=lambda: prove_wait(h, "t1", waiter_of(trackers), tx.pid, lambda: xid,
                                                 "product_waits_for_admin"),
                        owned=owned_of(trackers, txs))
    finally:
        tx.rollback()
        tx.close()
    result = worker_result(h, "t1", co, "product")
    subcase(h, "t1", "product_waited", co.proof.get("holder") == tx.pid, proof=co.proof)
    server = [s["sqlstate"] for s in result["trace"]["sqlstates"]]
    subcase(h, "t1", "server_sqlstate", server == [SQLSTATE_TIMEOUT], seen=server)
    details = judge_outcome(h, "t1", case, base, result, outcome="failed", code="migration_access_lock_timeout")
    again = h.resume(case, approval_id="app-0000000000000682")             # the explicit resume, no retry by itself
    out = again["out"]
    subcase(h, "t1", "explicit_resume", (out.get("phase"), again["code"], out.get("results"))
            == ("completed", 0, {"already_applied": 1, "applied": 1}), cli=out.get("results"))
    now = h.state(case)
    subcase(h, "t1", "resumed_state", not resume_problems(case, base, now, converted=True, status="completed",
                                                          cursor=2, finished=True))
    require_subcases(h, "t1", COMMON + ("product_waited", "server_sqlstate", "explicit_resume", "resumed_state"))
    return dict(details, origin={"server": server, "product_code": details["cli"]["code"]})


def deadlock_branch(product_cli: dict, product_states: list[str], admin_state: str | None,
                    admin_completed: bool) -> str | None:
    """Plan 5-2: P = the server chose the product (40P01 seen on its access statement, fixed code reported, the admin
    then got its row); A = the server chose the admin (40P01 on the admin connection; the product went on and
    applied). Anything else is no branch."""
    if product_states == [SQLSTATE_DEADLOCK] and admin_state is None and admin_completed \
            and product_cli.get("code") == "migration_access_deadlock":
        return "P"
    if admin_state == SQLSTATE_DEADLOCK and product_states == [] and product_cli.get("results") == \
            {"already_applied": 1, "applied": 1}:
        return "A"
    return None


def d1_deadlock(h: Harness) -> dict:
    """E3: the admin transaction (deadlock_timeout 60s, this transaction only) updates path A, the product waits on
    it (proved), then the admin asks for the product's l2 card row. The victim is not assumed."""
    case, base = baseline_of(h, "d1")
    trackers, txs = [], []
    tx = h.admin_tx("d1", txs)
    tx.run("deadlock_wait")
    tx.run("deactivate", (acc(h)["sub_a"], uid(h)))
    xid = tx.xid()
    admin_done: dict = {}

    def request_card():                       # after the product's wait is proved: the cycle (victim not assumed)
        try:
            tx.run("card_request", (uid(h), l2_id(h)))
            admin_done["ok"] = True
        except psycopg.Error:
            admin_done["ok"] = False
        finally:
            if tx.ended is None:
                tx.rollback()
    try:
        co = coordinate(h, "d1", [("product", product_run(h, case, trackers, []))], pause=None,
                        prove=lambda: prove_wait(h, "d1", waiter_of(trackers), tx.pid, lambda: xid,
                                                 "product_waits_for_admin"),
                        between=request_card, owned=owned_of(trackers, txs))
    finally:
        if tx.ended is None:
            tx.rollback()
        tx.close()
    result = worker_result(h, "d1", co, "product")
    subcase(h, "d1", "product_waited", co.proof.get("holder") == tx.pid, proof=co.proof)
    product_states = [s["sqlstate"] for s in result["trace"]["sqlstates"]]
    cli_seen = {"code": result["out"].get("code"), "results": result["out"].get("results")}
    branch = deadlock_branch(cli_seen, product_states, tx.sqlstate, admin_done.get("ok") is True)
    h.rec.event("deadlock_branch", check="d1", branch=branch, product_sqlstates=product_states,
                admin_sqlstate=tx.sqlstate, product_40p01_verified=branch == "P")
    subcase(h, "d1", "branch", branch in ("P", "A"), branch=branch)
    if branch == "P":
        details = judge_outcome(h, "d1", case, base, result, outcome="failed", code="migration_access_deadlock")
    else:
        details = judge_outcome(h, "d1", case, base, result, outcome="applied")
    require_subcases(h, "d1", COMMON + ("product_waited", "branch"))
    return dict(details, branch=branch, product_40p01_verified=branch == "P")


def word_row(h: Harness, check_id: str) -> list:
    with admin(CHECK_DB[check_id], h.pid) as conn:
        row = conn.execute(ADMIN_SQL["word_read"], (acc(h)["deck_a"], l2_id(h))).fetchone()
    expect(row is not None and row[0] == acc(h)["word_a_l2"], f"{check_id}: word row A-l2", "harness_defect")
    return list(row)


def word_restored(h: Harness, check_id: str, recorded: list) -> None:
    """Plan 3절: the recorded id and values back; exactly one row of the key, the same row text, paths as 4-0."""
    tx = h.admin_tx(check_id, [])
    try:
        tx.run("word_restore", tuple(recorded[:10]))
        tx.commit()
    finally:
        tx.close()
    with admin(CHECK_DB[check_id], h.pid) as conn:
        rows = conn.execute("SELECT w::text FROM shared_deck_words AS w WHERE w.shared_deck_id = %s "
                            "AND w.lexeme_id = %s", (acc(h)["deck_a"], l2_id(h))).fetchall()
    subcase(h, check_id, "word_restored", [r[0] for r in rows] == [recorded[10]], rows=len(rows))
    problems = path_problems(h, check_id, h.paths(check_id))
    subcase(h, check_id, "paths_restored", not problems, problems=problems)


def w1_locked_then_deleted(h: Harness, check_id: str) -> dict:
    case, base = baseline_of(h, check_id)
    recorded = word_row(h, check_id)
    trackers, txs = [], []
    pause = HoldPause(WRITE, "SELECT", LOCK_PREFIX)
    holder: dict = {}

    def delete():
        tx = h.admin_tx(check_id, txs)
        holder["pid"] = tx.pid
        holder["rows"] = tx.run("word_delete", (recorded[0], recorded[1], recorded[2])).rowcount
        tx.commit()
        return "committed"

    def prove():
        return prove_wait(h, check_id, lambda: holder.get("pid"), pause.holder_pid,
                          lambda: h.backend_xid(pause.holder_pid), "delete_waits_for_product")
    co = coordinate(h, check_id, [("product", product_run(h, case, trackers, [pause.hook])), ("admin", delete)],
                    pause=pause, prove=prove, owned=owned_of(trackers, txs))
    subcase(h, check_id, "admin_waited", co.proof.get("waiter") == holder.get("pid"), proof=co.proof)
    worker_result(h, check_id, co, "admin")
    subcase(h, check_id, "admin_attribution", holder.get("rows") == 1, rows=holder.get("rows"))
    details = judge_outcome(h, check_id, case, base, worker_result(h, check_id, co, "product"), outcome="applied")
    left = h.paths(check_id)["l2"]
    want = [[acc(h)["sub_b"], acc(h)["word_b_l2"]]] if check_id in TWO_PATH else []
    subcase(h, check_id, "paths_after_delete", left == want, left=left)
    word_restored(h, check_id, recorded)
    require_subcases(h, check_id, COMMON + ("admin_waited", "admin_attribution", "paths_after_delete",
                                            "word_restored", "paths_restored"))
    return details


def w2_deleted_first(h: Harness, check_id: str, outcome: str) -> dict:
    case, base = baseline_of(h, check_id)
    recorded = word_row(h, check_id)
    trackers, txs = [], []
    tx = h.admin_tx(check_id, txs)
    rows = tx.run("word_delete", (recorded[0], recorded[1], recorded[2])).rowcount
    xid = tx.xid()
    try:
        co = coordinate(h, check_id, [("product", product_run(h, case, trackers, []))], pause=None,
                        prove=lambda: prove_wait(h, check_id, waiter_of(trackers), tx.pid, lambda: xid,
                                                 "product_waits_for_delete"),
                        between=tx.commit, owned=owned_of(trackers, txs))
    finally:
        if tx.ended is None:
            tx.rollback()
        tx.close()
    subcase(h, check_id, "product_waited", co.proof.get("holder") == tx.pid, proof=co.proof)
    subcase(h, check_id, "admin_attribution", rows == 1 and tx.ended == "commit", rows=rows, ended=tx.ended)
    details = judge_outcome(h, check_id, case, base, worker_result(h, check_id, co, "product"), outcome=outcome)
    word_restored(h, check_id, recorded)
    require_subcases(h, check_id, COMMON + ("product_waited", "admin_attribution", "word_restored",
                                            "paths_restored"))
    return details


CHECKS: list[tuple[str, Callable[[Harness], dict]]] = [
    ("k1", k1_minimal_profile), ("k2a", k2a_column_missing), ("k2b", k2b_column_missing), ("k3", k3_table_excess),
    ("s1", s1_default), ("s2", s2_longer), ("s3", s3_shorter), ("s3b", s3b_exactly_5s), ("s4", s4_no_row),
    ("r1", r1_before_check), ("r2", r2_after_check), ("r3", r3_before_commit), ("r4a", r4a_held_committed),
    ("r4b", r4b_held_rolled_back), ("r5", r5_after_commit), ("r6", r6_two_paths),
    ("c1a", c1a_only_returned_path), ("c1b", c1b_first_path_dropped), ("t1", t1_lock_timeout), ("d1", d1_deadlock),
    ("w1a", lambda h: w1_locked_then_deleted(h, "w1a")), ("w1b", lambda h: w1_locked_then_deleted(h, "w1b")),
    ("w2a", lambda h: w2_deleted_first(h, "w2a", "conflict")), ("w2b", lambda h: w2_deleted_first(h, "w2b", "applied")),
]


def post_check(h: Harness) -> dict:
    sessions = h.sessions()
    expect(sessions == {"open": 0, "idle_in_transaction": 0, "ungranted_locks": 0}, f"post sessions {sessions}")
    expect(all(p.release.is_set() for p in h.pauses), "post: a pause was never released")
    alive = [t.name for t in h.threads if t.is_alive()]
    expect(not alive, f"post: threads alive {alive}")
    for check_id in PLANNED:
        problems = path_problems(h, check_id, h.paths(check_id))
        expect(not problems, f"post {problems}")
        expect(h.outside(check_id, h.cases[check_id]) == h.evidence["outside"][check_id], f"post {check_id} outside")
    return {"sessions": sessions, "pauses": len(h.pauses), "threads": len(h.threads)}


def check_access_lock() -> tuple[int, dict]:
    """(passed and recorded, summary). Gates and the post-check are never counted; the first failure stops
    everything after it (recorded as not run)."""
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if LQ4_CHANGES_APPROVED is not True:
        raise CheckFailed("preparation_failure", "LQ4 / V3 (admin, role-setting and privilege changes) not approved: "
                                                 "nothing runs")
    rec = LockedRecord(g.single_run(T).folder)                 # one lock for every writer of this run
    blocked = blocking_events(rec.folder / "record.json")
    if blocked:
        raise CheckFailed("harness_defect", f"recorded {sorted(set(blocked))}: no check runs")
    h = Harness(rec)
    token = f"final:{time.time_ns()}"
    rec.event("final_cleanup_started", token=token)        # nothing starts if this cannot be saved (plan 13-3)
    names = [n for n, _ in CHECKS]
    passed, failed, current = 0, None, None
    original: BaseException | None = None
    try:
        h.start()
        rec.event("check_phase_started", phase="access_lock", gates=["g0_gate", "g1_gate"], checks=names, post=POST,
                  note="gates and post-check are not counted; L-2, RS4 and C12 results are not added")
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
        original = error                              # kept; the final cleanup below never replaces it
        if not isinstance(error, Exception):          # an interrupt: recorded, the rest not run
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
        except BaseException as error:            # an unsaved record never makes the cleanup safe
            saved_ok = False
            if not isinstance(error, Exception):
                closing.interrupts.append(error)
    if original is not None:
        raise _bare(original)                     # 1. the error / interrupt already in flight, same object
    if closing.interrupts:
        raise _bare(closing.interrupts[0])        # 2. the first interrupt of the cleanup
    if closing.failures or not saved_ok:
        raise CheckFailed("harness_defect", f"final cleanup {closing.failures or ['record_failed']}")
    not_run = names[passed + (1 if failed in names else 0):] if failed is not None else []
    if failed is not None:
        try:
            rec.event("not_run", after=failed, checks=not_run)
        except Exception:
            pass
    return passed, {"failed": failed, "not_run": not_run}


PHASES = ("prepare", "check-access-lock", "cleanup")


def main(argv: list[str]) -> int:
    phase = argv[0] if len(argv) == 1 and argv[0] in PHASES else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase == "check-access-lock":
            passed, summary = check_access_lock()
            print(f"passed {passed} / {len(PLANNED)}")
            if tuple(n for n, _ in CHECKS) != PLANNED or passed != len(PLANNED) or summary["failed"] is not None:
                print(f"STOP: not all planned checks passed and were recorded (failed: {summary['failed']}, "
                      f"not run: {len(summary['not_run'])})")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check-access-lock | cleanup")
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
    import _ops_access_lock_real as runner                    # the one module object (fake checks can reach it)
    sys.exit(runner.main(sys.argv[1:]))
