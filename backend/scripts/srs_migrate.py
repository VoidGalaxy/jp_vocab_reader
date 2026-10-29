"""Explicit SRS migration CLI -- `dry-run` with the plan file (OPS_MIGRATION_CLI_PLAN 1-1), the
read-only `status` (4-3) and the FIRST `apply` of a job (4-4-8).

    python scripts/srs_migrate.py [dry-run] --account N --run-key KEY --personal-id N ... --lexeme-id N ... --out FILE
    python scripts/srs_migrate.py status --account N --run-key KEY --personal-id N ... --lexeme-id N ...
    python scripts/srs_migrate.py apply --account N --run-key KEY --personal-id N ... --batch-size N
        --plan FILE --backup-evidence FILE --backup-signature FILE

`dry-run` / `status` are the approval steps `dry_run` / `status` (read, inquiry approvals only). `apply`
needs an apply approval with a `dry_run` read step and an `apply` write step; it calls the product
`apply_plan` exactly once (no resume, no retry). There is no default real driver: the command line cannot open a real
connection, so a `dry-run` from the command line ends with `connection_not_available`. A normal run
exists only where test code injects synthetic pre-check inputs and a fake driver through
`run_dry_run` (Python, not an argument or an environment variable).

Output is one JSON object with fixed fields only (no candidate JSON, words, meanings, connection
secrets, driver text or paths). Exit codes: 0 ok, 2 usage, 4 approval / input refused, 1 run or
plan-file failure. The app is imported only after the real pre-check has passed.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SCRIPTS.parent) not in sys.path:      # path only: the app is imported after the pre-check
    sys.path.append(str(SCRIPTS.parent))

import _ops_approval as oa  # noqa: E402
import _ops_audit_run as ar  # noqa: E402
import _ops_backup_evidence as be  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_product_connect as pc  # noqa: E402
import _ops_provider as pv  # noqa: E402

TOOL = "srs_migrate"
COMMAND = "dry_run"
STATUS_COMMAND = "status"
CARDS_DOMAIN = b"jp-vocab-ops/migration-cards/v1\n"
MAX_CARDS = pfile.MAX_CANDIDATES
ID_MAX = 2 ** 63 - 1
_RUN_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
EXIT = {"ok": 0, "usage": 2, "refused": 4, "failed": 1}


class Refused(Exception):
    def __init__(self, status: str, code: str):
        super().__init__(code)
        self.status, self.code = status, code


@dataclass(frozen=True)
class Request:
    account_id: int
    run_key: str
    cards: tuple[tuple[str, int], ...]          # canonical order (kind, ref_id), no duplicates


def cards_bytes(cards: tuple[tuple[str, int], ...]) -> bytes:
    return json.dumps([[kind, ref] for kind, ref in cards], separators=(",", ":")).encode("ascii")


def job_inputs(request: Request) -> dict:
    """The approval `job.inputs` for this request (contract 1-1)."""
    return {"account_id": request.account_id,
            "cards_sha256": hashlib.sha256(CARDS_DOMAIN + cards_bytes(request.cards)).hexdigest(),
            "card_count": len(request.cards)}


def make_request(account_id: Any, run_key: Any, personal: Any, lexeme: Any) -> Request:
    def ok_id(value: Any) -> bool:
        return type(value) is int and 0 < value <= ID_MAX
    if not ok_id(account_id) or type(run_key) is not str or not run_key.isascii() or not _RUN_KEY.fullmatch(run_key):
        raise Refused("usage", "request_invalid")
    cards = [("personal", ref) for ref in personal] + [("lexeme", ref) for ref in lexeme]
    if not cards or len(cards) > MAX_CARDS or not all(ok_id(ref) for _, ref in cards):
        raise Refused("usage", "request_invalid")
    if len(set(cards)) != len(cards):
        raise Refused("usage", "duplicate_card")              # never merged silently
    return Request(account_id, run_key, tuple(sorted(cards)))


def _result(status: str, code: str | None = None, command: str = "dry-run", **values: Any) -> tuple[dict, int]:
    out = {"status": status, "command": command}
    if code is not None:
        out["code"] = code
    out.update(values)
    return out, EXIT[status]


def _admit(request: Request, inputs: Any, driver: Any, step: str, command: str) -> Any:
    """Shared gate of the read commands: request = run inputs, real pre-check, then (contract 1-1 / 4-3)
    only a signed srs_migrate INQUIRY approval whose current step is `step` (read). Judged on the
    approval the pre-check verified itself, before any app import, connection or file. Returns the
    pre-check result, or an (output, exit code) refusal."""
    if not isinstance(inputs, op.PreflightInput) or inputs.mode != op.MODE:
        return _result("refused", "mode_not_synthetic", command)
    if driver is None or not callable(driver):
        return _result("refused", "connection_not_available", command)
    wanted = job_inputs(request)
    if (inputs.command, inputs.account_id, inputs.job_key) != (step, request.account_id, request.run_key) \
            or not isinstance(inputs.job_inputs, dict) or inputs.job_inputs != wanted \
            or any(type(inputs.job_inputs[k]) is not type(v) for k, v in wanted.items()) \
            or inputs.artifact_sha256 is not None or inputs.prior_chain:
        return _result("refused", "request_mismatch", command)
    ar.fix_app_environment()                                 # environment only; nothing from app yet
    try:
        matched = op.run_synthetic_preflight(inputs)         # signatures, manifest, target, step, job inputs
    except op.OpsPreflightRefused as error:
        return _result("refused", f"preflight_{error.code}", command)
    approval = getattr(getattr(matched, "verified", None), "approval", None)
    if not isinstance(approval, oa.Approval) or not approval.verified:
        return _result("refused", "approval_unverified", command)
    if approval.tool != TOOL:
        return _result("refused", "approval_tool_not_srs_migrate", command)
    if approval.kind != "inquiry" or matched.kind != "inquiry":
        return _result("refused", "approval_kind_not_inquiry", command)
    if (matched.command, matched.access) != (step, "read"):
        return _result("refused", f"{step}_not_read", command)
    return matched


def _product_connector(inputs: op.PreflightInput, expected: Any, driver: Any) -> Any:
    """The only connection source: the synthetic provider path (no default driver)."""
    return pc.ProductConnector(inputs, expected=expected, driver=driver)


def _connection_status(code: str) -> str:
    """Approval / input refusals (pre-check, approval judgement after connect) are 4; the rest is 1."""
    refused_prefixes = ("preflight_", "observed_", "approval_", "connection_access_", "mode_",
                        "connection_factory_", "read_only_", "expected_profile_")
    return "refused" if code.startswith(refused_prefixes) else "failed"


def run_dry_run(request: Request, *, inputs: Any, expected: Any, driver: Any, out: str) -> tuple[dict, int]:
    """Synthetic only. Real pre-check, then the product dry_run through the provider connection,
    then a NEW plan file. Returns (output, exit code)."""
    matched = _admit(request, inputs, driver, COMMAND, "dry-run")
    if isinstance(matched, tuple):
        return matched
    wanted = job_inputs(request)
    try:
        from app.srs import migration                        # only after the pre-check passed
        from app.srs.engine import DEFAULT_CONFIG, CardKey
    except ImportError:
        return _result("failed", "product_import_failed")
    connect = _product_connector(inputs, expected, driver)
    keys = [CardKey(kind, request.account_id, ref) for kind, ref in request.cards]
    try:
        candidates = migration.dry_run(keys, connect=connect)
    except pc.OpsProductConnectionError as error:
        return _result(_connection_status(error.code), error.code)
    except Exception:
        return _result("failed", "dry_run_failed")
    if tuple((c.key.kind, c.key.ref_id) for c in candidates) != request.cards \
            or any(c.key.user_id != request.account_id for c in candidates):
        return _result("refused", "card_scope_mismatch")
    product = hashlib.sha256(migration._plan_json(candidates).encode()).hexdigest()
    try:
        data = pfile.serialize_plan(db_identity=matched.db_identity, account_id=request.account_id,
                                    job_key=request.run_key, config_version=DEFAULT_CONFIG.config_version,
                                    product_fingerprint=product, candidates=candidates)
        artifact = pfile.write_plan_file(out, data)
        written = pfile.read_plan_file(out)
        if written.artifact_sha256 != artifact or pfile.to_candidates(written) != tuple(candidates):
            raise pfile.OpsPlanFileError("plan_file_write_failed")
    except pfile.OpsPlanFileError as error:
        return _result("failed", error.code)
    plan = oa.job_plan_fingerprint(db_identity=matched.db_identity, manifest=matched.manifest_sha256, tool=TOOL,
                                   account_id=request.account_id, job_key=request.run_key, job_inputs=wanted,
                                   product_fingerprint=product, artifact_sha256=artifact)
    qualities = dict(sorted(Counter(c.quality for c in candidates).items()))
    return _result("ok", None, db_identity=matched.db_identity, account_id=request.account_id,
                   job_key=request.run_key, card_count=len(candidates), qualities=qualities,
                   product_fingerprint=product, artifact_sha256=artifact, job_plan=plan)


# --- status (contract 4-3) --------------------------------------------------------------------------

RESULT_KINDS = ("applied", "already_applied", "conflict", "blocked")
SNAPSHOT_RESULTS = ("applied", "already_applied")
STATE_EXIT = {"not_started": 0, "incomplete": 3, "failed_at_cursor": 3, "completed": 0,
              "cursor_end_not_completed": 6, "closed": 0, "conflict": 6, "inconsistent": 6}


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError                                   # never pick the first or the last value
        result[key] = value
    return result


def _strict_json(text: Any) -> Any:
    """Stored JSON read for status: a duplicate key at ANY depth makes it unreadable (contract 4-3)."""
    return json.loads(text, object_pairs_hook=_no_duplicate_keys)


def _scope_cards(row: dict, migration: Any) -> tuple[Any, tuple[tuple[str, int], ...]] | None:
    """(owner, cards) from the run's scope_json in its original or pruned form (existing checks), or
    None when the owner cannot be established. Nothing is repaired."""
    try:
        scope = _strict_json(row["scope_json"])               # duplicates: owner unknown (= missing key)
    except (TypeError, ValueError, RecursionError):
        return None
    try:
        if not (migration._full_scope(scope, row["config_version"])
                or migration._reduced_scope(scope, row["config_version"])):
            return None
    except Exception:
        return None
    return scope["user_id"], tuple((c["kind"], c["ref_id"]) for c in scope["cards"])


def read_status(connect: Any, request: Request, migration: Any) -> tuple[dict, tuple, list] | None:
    """One read connection, one consistent read transaction; no lock, no update. None when there is
    no run of this account to show (missing key, other account, owner not established)."""
    from app.database import is_postgres_connection
    with connect(read_only=True) as connection:
        if is_postgres_connection(connection):
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        else:
            connection.execute("BEGIN")
        row = connection.execute(
            "SELECT id, mode, status, scope_json, config_version, summary_json, started_at, finished_at "
            "FROM srs_migration_runs WHERE run_key = ?", (request.run_key,)).fetchone()
        if row is None:
            return None
        row = dict(row)
        scoped = _scope_cards(row, migration)
        if scoped is None or type(scoped[0]) is not int or scoped[0] != request.account_id:
            return None                                        # the same answer as a missing key
        snapshots = [dict(r) for r in connection.execute(
            "SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots WHERE run_id = ?",
            (row["id"],)).fetchall()]
    return row, scoped[1], snapshots


def _progress(summary: Any, cards: tuple, n: int) -> Any:
    """(cursor, results) or an inconsistency reason."""
    if summary is None:
        return 0, []
    try:
        value = _strict_json(summary)                         # duplicates: unreadable, never guessed
    except (TypeError, ValueError, RecursionError):
        return "summary_unreadable"
    if not isinstance(value, dict) or set(value) != {"cursor", "results"}:
        return "summary_unreadable"
    cursor, results = value["cursor"], value["results"]
    if type(cursor) is not int or not 0 <= cursor <= n:
        return "cursor_invalid"
    if not isinstance(results, list) or len(results) != cursor:
        return "results_invalid"
    for index, result in enumerate(results):
        if not isinstance(result, dict) or (result.get("kind"), result.get("ref_id")) != cards[index] \
                or type(result.get("ref_id")) is not int or result.get("result") not in RESULT_KINDS:
            return "results_invalid"
    return cursor, results


def judge_status(row: dict, cards: tuple, snapshots: list, request: Request, config_version: str) -> dict:
    """State of an apply run of THIS account (contract 4-3). No value is repaired or guessed."""
    n = len(request.cards)
    if row["mode"] != "apply":
        return {"state": "conflict", "reason": "mode"}
    if row["config_version"] != config_version:
        return {"state": "conflict", "reason": "config"}
    if tuple(cards) != request.cards:
        return {"state": "conflict", "reason": "cards"}
    status = row["status"]
    if status == "aborted":
        return {"state": "closed", "finished": row["finished_at"] is not None}
    progress = _progress(row["summary_json"], cards, n)
    if isinstance(progress, str):
        return {"state": "inconsistent", "reason": progress}
    cursor, results = progress
    counts = dict(sorted(Counter(r["result"] for r in results).items()))
    detail = {"cursor": cursor, "card_count": n, "results": counts, "finished": row["finished_at"] is not None}
    expected = {cards[i] for i, r in enumerate(results) if r["result"] in SNAPSHOT_RESULTS}
    seen = [(s["user_id"], s["card_kind"], s["card_ref"]) for s in snapshots]
    if len(set(seen)) != len(seen) or any(user != request.account_id for user, _, _ in seen) \
            or {(kind, ref) for _, kind, ref in seen} != expected:
        return dict(detail, state="inconsistent", reason="snapshot_mismatch")
    if (status == "completed") != (row["finished_at"] is not None):
        return dict(detail, state="inconsistent", reason="finished_at_mismatch")
    if status == "completed":
        state, reason = ("completed" if cursor == n else None), "completed_short"
    elif status == "started":
        state, reason = ("cursor_end_not_completed" if cursor == n else "incomplete"), None
    elif status == "failed":
        state, reason = ("failed_at_cursor" if cursor < n else None), "failed_at_end"
    else:
        state, reason = None, "status_unknown"
    if state is None:
        return dict(detail, state="inconsistent", reason=reason)
    return dict(detail, state=state)


def run_status(request: Request, *, inputs: Any, expected: Any, driver: Any) -> tuple[dict, int]:
    """Synthetic only. Report of the current record; not a resume permission (contract 4-3)."""
    matched = _admit(request, inputs, driver, STATUS_COMMAND, "status")
    if isinstance(matched, tuple):
        return matched
    try:
        from app.srs import migration                        # only after the pre-check passed
        from app.srs.engine import DEFAULT_CONFIG
    except ImportError:
        return _result("failed", "product_import_failed", "status")
    connect = _product_connector(inputs, expected, driver)
    try:
        found = read_status(connect, request, migration)
    except pc.OpsProductConnectionError as error:
        return _result(_connection_status(error.code), error.code, "status")
    except Exception:
        return _result("failed", "status_read_failed", "status")
    if found is None:
        out, _ = _result("ok", None, "status", state="not_started")
        return out, STATE_EXIT["not_started"]
    row, cards, snapshots = found
    report = judge_status(row, cards, snapshots, request, DEFAULT_CONFIG.config_version)
    report["window"] = migration.rollback_window(row["started_at"], migration.now_utc())
    out, _ = _result("ok", None, "status", **report)
    code = STATE_EXIT[report["state"]]
    if report["state"] == "completed" and (report["results"].get("conflict") or report["results"].get("blocked")):
        code = 5
    return out, code


# --- first apply (contract 4-4-8) -------------------------------------------------------------------

APPLY_COMMAND = "apply"
MAX_BATCH = 2000
_BATCH_TEXT = re.compile(r"[1-9][0-9]{0,3}")
MAX_SIGNATURE_BYTES = 64 * 1024
IDENTITY_SCHEMA, IDENTITY_TABLE = "jp_vocab_ops_synthetic", "db_identity"

# Contract privilege table (4-4-4), never taken from an observation. (kind, schema, object, column, privilege);
# column "" is the whole table. The database name is the observed target's and is filled in at use.
READ_TABLES = ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "shared_deck_words",
               "user_deck_subscriptions", "srs_card_identity_flags", "srs_card_deletions", "srs_migration_runs",
               "srs_migration_snapshots")
CARD_UPDATE_COLUMNS = ("completion_metric_version", "first_completed_at", "history_intro_known_by",
                       "history_intro_status", "srs_card_version", "srs_config_version", "srs_difficulty",
                       "srs_due_at", "srs_effective_due_at", "srs_engine", "srs_history_flags",
                       "srs_history_quality", "srs_last_review_at", "srs_participation", "srs_pause_reason",
                       "srs_stability", "srs_state", "srs_step")
_INFRA = frozenset({("schema", "", "public", "", "USAGE"), ("schema", "", IDENTITY_SCHEMA, "", "USAGE"),
                    ("table", IDENTITY_SCHEMA, IDENTITY_TABLE, "", "SELECT")})
READ_PRIVILEGES = _INFRA | {("table", "public", t, "", "SELECT") for t in READ_TABLES}
WRITE_PRIVILEGES = (READ_PRIVILEGES
                    | {("table", "public", "users", "id", "SELECT"),          # D12: lock row only
                       ("table", "public", "users", "updated_at", "UPDATE"),  # D12: FOR UPDATE needs one column
                       ("table", "public", "account_write_blocks", "", "SELECT"),
                       ("table", "public", "srs_migration_runs", "", "INSERT"),
                       ("table", "public", "srs_migration_snapshots", "", "INSERT"),
                       ("table", "public", "srs_config_versions", "", "SELECT"),
                       ("table", "public", "srs_config_versions", "", "INSERT"),
                       # LQ1 (RACE_PLAN 11-1): FOR SHARE of the access path needs one UPDATE column per table;
                       # the product never updates these tables, but the role CAN change these two columns.
                       ("table", "public", "user_deck_subscriptions", "updated_at", "UPDATE"),
                       ("table", "public", "shared_deck_words", "created_at", "UPDATE")}
                    # No sequence USAGE (OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN S1, 2026-10-27): both ids are
                    # identity columns filled by default; the first apply path calls no sequence function.
                    | {("table", "public", "srs_migration_runs", c, "UPDATE")
                       for c in ("finished_at", "status", "summary_json")}
                    | {("table", "public", t, c, "UPDATE") for t in ("vocab_items", "user_word_progress")
                       for c in CARD_UPDATE_COLUMNS})


@dataclass(frozen=True)
class ProfileScope:
    """Environment facts for the expected profiles (what exists, not what is allowed)."""
    objects: frozenset
    search_path: str
    tls_versions: frozenset


def contract_profiles(scope: ProfileScope, database: str) -> tuple[Any, Any]:
    """(read, write) expected profiles: privileges from the contract table only."""
    db = {("database", "", database, "", "CONNECT")}
    return (pv.ExpectedProfile(scope.objects, frozenset(READ_PRIVILEGES | db), scope.search_path, scope.tls_versions),
            pv.ExpectedProfile(scope.objects, frozenset(WRITE_PRIVILEGES | db), scope.search_path,
                               scope.tls_versions))


def batch_from_text(text: Any) -> int:
    """Command-line `--batch-size`: ASCII canonical decimal 1..2000 only (no zero padding, sign, space)."""
    if type(text) is not str or not text.isascii() or not _BATCH_TEXT.fullmatch(text) or int(text) > MAX_BATCH:
        raise Refused("usage", "batch_size_invalid")
    return int(text)


def _read_fixed(path: Any, limit: int, code: str) -> bytes:
    """Read once into fixed bytes; any read problem is the same fixed code (no path or OS text)."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(limit + 1)
    except (OSError, TypeError, ValueError):
        raise Refused("refused", code) from None
    if not data or len(data) > limit:
        raise Refused("refused", code)
    return data


_SHARED = ("mode", "approval", "approval_signature", "manifest", "manifest_signature", "deploy_root", "account_id",
           "job_key", "job_inputs", "product_fingerprint", "target", "trust", "inquiry", "inquiry_signature",
           "artifact_sha256", "prior_chain")


def _args_ok(args: Any) -> bool:
    """The approval contract's step-argument shape, checked before any conversion (nothing normalised)."""
    return type(args) is dict and all(oa._text(k, oa._NAME) and oa._text(v, oa._ARG_VALUE) for k, v in args.items())


class _ClockInvalid(Exception):
    pass


def _clock_now(clock: Any) -> datetime:
    """The time of THIS judgement: a fresh, time-zoned, UTC-convertible value from the clock."""
    value = clock()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _ClockInvalid
    try:
        if value.utcoffset() is None:
            raise _ClockInvalid
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise _ClockInvalid from None


def _timed_connector(inputs: op.PreflightInput, expected: Any, driver: Any, clock: Any) -> Any:
    """Contract 4-4-8 (review fix): every connection request is judged at its own time. The fixed bytes stay;
    only `now` is replaced, and the whole existing provider path (pre-check, connect, observation,
    re-judgement) runs again with it."""
    def connect(*, read_only: bool = False) -> Any:
        try:
            now = _clock_now(clock)
        except _ClockInvalid:
            raise pc.OpsProductConnectionError("clock_invalid") from None
        return _product_connector(dataclasses.replace(inputs, now=now), expected, driver)(read_only=read_only)
    return connect


class _Tracked:
    """Wraps the write connection function: counts connections and whether the FIRST one committed."""

    def __init__(self, connect: Any):
        self._connect, self.opened, self.first_committed, self.first_uncertain = connect, 0, False, False

    def __call__(self, *, read_only: bool = False) -> Any:
        context = self._connect(read_only=read_only)
        self.opened += 1
        index, tracker = self.opened, self

        class Tracked:
            def __enter__(self):
                return context.__enter__()

            def __exit__(self, exc_type, exc, tb):
                try:
                    result = context.__exit__(exc_type, exc, tb)
                except BaseException:
                    if index == 1 and exc_type is None:
                        tracker.first_uncertain = True          # the commit itself failed: result unknown
                    raise
                if index == 1 and exc_type is None:
                    tracker.first_committed = True
                return result
        return Tracked()


def _apply_result(status: str, code: str | None = None, **values: Any) -> tuple[dict, int]:
    return _result(status, code, "apply", **values)


def run_apply(request: Request, *, batch_size: Any, write_inputs: Any, read_inputs: Any, scope: Any, driver: Any,
              plan_path: Any, evidence_path: Any, evidence_signature_path: Any,
              clock: Any = None) -> tuple[dict, int]:
    """Synthetic only. Contract 4-4-8: checks 1..11, then the product apply_plan exactly once."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        # 1 inputs
        if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH:
            raise Refused("refused", "batch_size_invalid")
        if not all(isinstance(i, op.PreflightInput) and i.mode == op.MODE for i in (write_inputs, read_inputs)):
            raise Refused("refused", "mode_not_synthetic")
        if driver is None or not callable(driver) or not isinstance(scope, ProfileScope):
            raise Refused("refused", "connection_not_available")
        if not _args_ok(write_inputs.args) or not _args_ok(read_inputs.args):
            raise Refused("refused", "args_invalid")
        wanted = job_inputs(request)
        if (write_inputs.command, read_inputs.command) != (APPLY_COMMAND, COMMAND) \
                or write_inputs.args != {"batch_size": str(batch_size)} or read_inputs.args != {} \
                or any(getattr(write_inputs, f) != getattr(read_inputs, f) for f in _SHARED) \
                or (write_inputs.account_id, write_inputs.job_key) != (request.account_id, request.run_key) \
                or not isinstance(write_inputs.job_inputs, dict) or write_inputs.job_inputs != wanted \
                or any(type(write_inputs.job_inputs[k]) is not type(v) for k, v in wanted.items()) \
                or write_inputs.prior_chain or write_inputs.artifact_sha256 is None \
                or write_inputs.product_fingerprint is None:
            raise Refused("refused", "request_mismatch")
        # 2 fixed reads
        try:
            plan = pfile.read_plan_file(plan_path)
        except pfile.OpsPlanFileError as error:
            raise Refused("refused", error.code) from None
        evidence_bytes = _read_fixed(evidence_path, be.MAX_EVIDENCE_BYTES, "backup_evidence_unreadable")
        evidence_signature = _read_fixed(evidence_signature_path, MAX_SIGNATURE_BYTES, "backup_signature_unreadable")
        # 3 plan file = request and run inputs
        if (plan.account_id, plan.job_key) != (request.account_id, request.run_key) \
                or tuple((c.kind, c.ref_id) for c in plan.candidates) != request.cards \
                or (plan.artifact_sha256, plan.product_fingerprint) != (write_inputs.artifact_sha256,
                                                                       write_inputs.product_fingerprint):
            raise Refused("refused", "plan_file_request_mismatch")
        # 4 real pre-checks of both steps
        ar.fix_app_environment()                                 # environment only; nothing from app yet
        try:
            now = _clock_now(clock)                              # the judgement time is the clock's, not inputs.now
        except _ClockInvalid:
            raise Refused("refused", "clock_invalid") from None
        try:
            written = op.run_synthetic_preflight(dataclasses.replace(write_inputs, now=now))
            readable = op.run_synthetic_preflight(dataclasses.replace(read_inputs, now=now))
        except op.OpsPreflightRefused as error:
            raise Refused("refused", f"preflight_{error.code}") from None
        # 5 approval shape, judged on what the pre-check verified itself
        verified = getattr(written, "verified", None)
        approval, inquiry = getattr(verified, "approval", None), getattr(verified, "inquiry", None)
        if not isinstance(approval, oa.Approval) or not approval.verified or not isinstance(inquiry, oa.Approval) \
                or not inquiry.verified:
            raise Refused("refused", "approval_unverified")
        if approval.tool != TOOL or inquiry.tool != TOOL:
            raise Refused("refused", "approval_tool_not_srs_migrate")
        if approval.kind != "apply" or written.kind != "apply" or inquiry.kind != "inquiry":
            raise Refused("refused", "approval_kind_not_apply")
        if approval.supersedes is not None:
            raise Refused("refused", "approval_not_first")
        if (written.command, written.access, readable.command, readable.access) != (APPLY_COMMAND, "write",
                                                                                   COMMAND, "read") \
                or getattr(getattr(readable, "verified", None), "approval", None) is None \
                or readable.verified.approval.sha256 != approval.sha256:
            raise Refused("refused", "approval_steps_mismatch")
        # 5-1 (RESUME_PLAN 9-3): a v3 apply approval may bind the evidence document; the fixed bytes must
        # be that document. The C10 checks below still run in full.
        if approval.backup_evidence_sha256 is not None \
                and hashlib.sha256(evidence_bytes).hexdigest() != approval.backup_evidence_sha256:
            raise Refused("refused", "backup_evidence_binding_mismatch")
        # 6 plan target
        if plan.db_identity != written.db_identity:
            raise Refused("refused", "plan_file_target_mismatch")
        # 7 backup evidence: expected values only from the verified approval and the observed target
        try:
            evidence_now = _clock_now(clock)
        except _ClockInvalid:
            raise Refused("refused", "clock_invalid") from None
        try:
            evidence = be.verify_backup_evidence(
                evidence_bytes, evidence_signature, mode=op.MODE, trust=write_inputs.trust, now=evidence_now,
                expected=be.Expected(db_identity=written.db_identity, account_id=written.account_id,
                                     job_key=approval.job_key, basis_from=inquiry.valid_from))
        except be.OpsBackupEvidenceRefused as error:
            raise Refused("refused", error.code) from None
    except Refused as refused:
        return _apply_result(refused.status, refused.code, phase="before_first_write", changes="none")
    # 8 app import, only now
    try:
        from app.srs import migration
        from app.srs.engine import DEFAULT_CONFIG, CardKey
        from app.srs.storage import SrsWriteError
    except ImportError:
        return _apply_result("failed", "product_import_failed", phase="before_first_write", changes="none")
    base = dict(phase="before_first_write", changes="none")
    # 9 plan candidates through the existing product rules
    if plan.config_version != DEFAULT_CONFIG.config_version:
        return _apply_result("refused", "plan_file_config_mismatch", **base)
    try:
        planned = pfile.to_candidates(plan)
    except pfile.OpsPlanFileError as error:
        return _apply_result("refused", error.code, **base)
    read_expected, write_expected = contract_profiles(scope, write_inputs.target.database)
    # 10 fresh dry_run on the read step
    keys = [CardKey(kind, request.account_id, ref) for kind, ref in request.cards]
    try:
        fresh = migration.dry_run(keys, connect=_timed_connector(read_inputs, read_expected, driver, clock))
    except pc.OpsProductConnectionError as error:
        return _apply_result(_connection_status(error.code), error.code, **base)
    except Exception:
        return _apply_result("failed", "dry_run_failed", **base)
    if tuple(fresh) != tuple(planned):
        return _apply_result("refused", "plan_changed", **base)
    # 11 the evidence again, at the time of THIS moment, right before the first write connection
    try:
        be.recheck(evidence, _clock_now(clock))
    except be.OpsBackupEvidenceRefused as error:
        return _apply_result("refused", error.code, **base)
    except _ClockInvalid:
        return _apply_result("refused", "clock_invalid", **base)
    # 12 exactly one apply_plan call
    tracked = _Tracked(_timed_connector(write_inputs, write_expected, driver, clock))
    facts = dict(card_count=len(planned), artifact_sha256=plan.artifact_sha256,
                 evidence_sha256=evidence.evidence_sha256, restore_verified=False, backup_artifact_checked=False)
    try:
        results = migration.apply_plan(planned, request.run_key, approved=True, batch_size=batch_size,
                                       connect=tracked, new_run_only=True)
    except Exception as error:
        code = getattr(error, "code", None) if isinstance(error, (SrsWriteError, pc.OpsProductConnectionError)) \
            else None
        started = tracked.first_committed or tracked.first_uncertain or tracked.opened > 1
        if not started and isinstance(error, SrsWriteError):
            return _apply_result("refused", code, **base, **facts)
        if not started and isinstance(error, pc.OpsProductConnectionError) and tracked.opened == 0:
            return _apply_result(_connection_status(code), code, **base, **facts)
        return _apply_result("failed", code or "apply_failed", phase="after_start" if started else "first_connection",
                             confirmed="unknown", uncertain=True, next="status_required", **facts)
    counts = dict(sorted(Counter(r["result"] for r in results).items()))
    if len(results) < len(planned):
        out, _ = _apply_result("ok", None, phase="partial", cursor=len(results), results=counts,
                               resume="not_implemented", next="status", **facts)
        return out, 3
    out, _ = _apply_result("ok", None, phase="completed", cursor=len(results), results=counts, **facts)
    return out, 5 if counts.get("conflict") or counts.get("blocked") else 0


# --- resume (OPS_MIGRATION_RESUME_PLAN 9-4) ----------------------------------------------------------------

RESUME_COMMAND = "resume"
RESUME_READ_COMMAND = STATUS_COMMAND
EVIDENCE_MATCH_FIELDS = ("backup_id", "db_identity", "account_id", "job_key", "method", "artifact_sha256_claimed",
                         "taken_at")


def _resume_result(status: str, code: str | None = None, **values: Any) -> tuple[dict, int]:
    return _result(status, code, RESUME_COMMAND, **values)


def _text_sha256(text: Any) -> str | None:
    return None if text is None else hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def progress_values(row: dict, snapshots: list) -> dict:
    """RESUME_PLAN 9-2: the nine fixed values from the row and snapshots of ONE read transaction
    (no second read). Hashes of the stored texts; SQL NULL is None; snapshots sorted by id."""
    listed = json.dumps([[s["id"], s["user_id"], s["card_kind"], s["card_ref"]]
                         for s in sorted(snapshots, key=lambda s: s["id"])], separators=(",", ":"), ensure_ascii=True)
    return {"run_id": row["id"], "status": row["status"], "mode": row["mode"],
            "config_version": row["config_version"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "scope_sha256": _text_sha256(row["scope_json"]),
            "summary_sha256": _text_sha256(row["summary_json"]),
            "snapshots_sha256": hashlib.sha256(listed.encode("utf-8")).hexdigest()}


_STATE_REFUSALS = {"completed": ("refused", "migration_run_completed", 4), "closed": ("refused", "migration_run_closed", 4),
                   "cursor_end_not_completed": ("report", "cursor_end_not_completed", 6),
                   "conflict": ("report", "migration_run_conflict", 6), "inconsistent": ("report", None, 6)}


def run_resume(request: Request, *, batch_size: Any, write_inputs: Any, read_inputs: Any, scope: Any, driver: Any,
               plan_path: Any, initial_evidence_path: Any, initial_evidence_signature_path: Any,
               evidence_path: Any, evidence_signature_path: Any, clock: Any = None) -> tuple[dict, int]:
    """Synthetic only. RESUME_PLAN 9-4: checks 1..12, then the product apply_plan exactly once with
    existing_run_only and the pre-read values."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    base = dict(phase="before_first_write", changes="none")
    try:
        # 1 inputs
        if type(batch_size) is not int or not 1 <= batch_size <= MAX_BATCH:
            raise Refused("refused", "batch_size_invalid")
        if not all(isinstance(i, op.PreflightInput) and i.mode == op.MODE for i in (write_inputs, read_inputs)):
            raise Refused("refused", "mode_not_synthetic")
        if driver is None or not callable(driver) or not isinstance(scope, ProfileScope):
            raise Refused("refused", "connection_not_available")
        if not _args_ok(write_inputs.args) or not _args_ok(read_inputs.args):
            raise Refused("refused", "args_invalid")
        wanted = job_inputs(request)
        if (write_inputs.command, read_inputs.command) != (RESUME_COMMAND, RESUME_READ_COMMAND) \
                or write_inputs.args != {"batch_size": str(batch_size)} or read_inputs.args != {} \
                or any(getattr(write_inputs, f) != getattr(read_inputs, f) for f in _SHARED) \
                or (write_inputs.account_id, write_inputs.job_key) != (request.account_id, request.run_key) \
                or not isinstance(write_inputs.job_inputs, dict) or write_inputs.job_inputs != wanted \
                or any(type(write_inputs.job_inputs[k]) is not type(v) for k, v in wanted.items()) \
                or write_inputs.artifact_sha256 is None or write_inputs.product_fingerprint is None:
            raise Refused("refused", "request_mismatch")
        if type(write_inputs.prior_chain) is not tuple or not write_inputs.prior_chain:
            raise Refused("refused", "resume_chain_required")
        # 2 fixed reads
        try:
            plan = pfile.read_plan_file(plan_path)
        except pfile.OpsPlanFileError as error:
            raise Refused("refused", error.code) from None
        initial_bytes = _read_fixed(initial_evidence_path, be.MAX_EVIDENCE_BYTES, "initial_evidence_unreadable")
        initial_signature = _read_fixed(initial_evidence_signature_path, MAX_SIGNATURE_BYTES,
                                        "initial_evidence_signature_unreadable")
        evidence_bytes = _read_fixed(evidence_path, be.MAX_EVIDENCE_BYTES, "backup_evidence_unreadable")
        evidence_signature = _read_fixed(evidence_signature_path, MAX_SIGNATURE_BYTES, "backup_signature_unreadable")
        # 3 plan file = request and run inputs
        if (plan.account_id, plan.job_key) != (request.account_id, request.run_key) \
                or tuple((c.kind, c.ref_id) for c in plan.candidates) != request.cards \
                or (plan.artifact_sha256, plan.product_fingerprint) != (write_inputs.artifact_sha256,
                                                                       write_inputs.product_fingerprint):
            raise Refused("refused", "plan_file_request_mismatch")
        # 4 real pre-checks of both steps (signatures of An, I0 and the whole prior chain)
        ar.fix_app_environment()                                 # environment only; nothing from app yet
        try:
            now = _clock_now(clock)
        except _ClockInvalid:
            raise Refused("refused", "clock_invalid") from None
        try:
            written = op.run_synthetic_preflight(dataclasses.replace(write_inputs, now=now))
            readable = op.run_synthetic_preflight(dataclasses.replace(read_inputs, now=now))
        except op.OpsPreflightRefused as error:
            raise Refused("refused", f"preflight_{error.code}") from None
        # 5 approval shape, from what the pre-check verified itself
        approval = getattr(getattr(written, "verified", None), "approval", None)
        inquiry = getattr(getattr(written, "verified", None), "inquiry", None)
        if not isinstance(approval, oa.Approval) or not approval.verified or not isinstance(inquiry, oa.Approval) \
                or not inquiry.verified:
            raise Refused("refused", "approval_unverified")
        if approval.tool != TOOL or inquiry.tool != TOOL:
            raise Refused("refused", "approval_tool_not_srs_migrate")
        if approval.kind != "apply" or written.kind != "apply" or inquiry.kind != "inquiry":
            raise Refused("refused", "approval_kind_not_apply")
        if approval.format_version != oa.BACKUP_EVIDENCE_VERSION:
            raise Refused("refused", "approval_format_not_v3")
        if approval.supersedes is None:
            raise Refused("refused", "approval_not_a_resume")
        if (written.command, written.access, readable.command, readable.access) != (RESUME_COMMAND, "write",
                                                                                   RESUME_READ_COMMAND, "read") \
                or getattr(getattr(readable, "verified", None), "approval", None) is None \
                or readable.verified.approval.sha256 != approval.sha256:
            raise Refused("refused", "approval_steps_mismatch")
        # 6 the job's first apply approval A0 and its basis I0, as verified by THIS pre-check
        try:
            first, basis = op.initial_apply_approvals(written, dataclasses.replace(write_inputs, now=now))
        except op.OpsPreflightRefused as error:
            raise Refused("refused", f"preflight_{error.code}") from None
        if approval.based_on != (basis.approval_id, basis.sha256) or inquiry.sha256 != basis.sha256:
            raise Refused("refused", "resume_basis_not_initial_inquiry")
        if (first.db_identity, first.tool, first.job_key, first.job_inputs, first.manifest) \
                != (approval.db_identity, approval.tool, approval.job_key, approval.job_inputs, approval.manifest) \
                or request.account_id not in first.accounts:
            raise Refused("refused", "resume_initial_approval_mismatch")
        # 7 plan target and the binding to A0 (pure file values, A0's signed fields)
        if plan.db_identity != written.db_identity:
            raise Refused("refused", "plan_file_target_mismatch")
        try:
            initial_plan = oa.job_plan_fingerprint(
                db_identity=first.db_identity, manifest=first.manifest, tool=first.tool,
                account_id=request.account_id, job_key=first.job_key, job_inputs=dict(first.job_inputs),
                product_fingerprint=plan.product_fingerprint, artifact_sha256=plan.artifact_sha256)
        except oa.OpsApprovalRefused:
            raise Refused("refused", "resume_plan_not_initial") from None
        if first.plan_for(request.account_id) != initial_plan:
            raise Refused("refused", "resume_plan_not_initial")
        # 8 backup evidence: the initial one bound by A0 (record check), the new one (current check)
        if first.backup_evidence_sha256 is None:
            raise Refused("refused", "resume_backup_binding_missing")
        if hashlib.sha256(initial_bytes).hexdigest() != first.backup_evidence_sha256:
            raise Refused("refused", "resume_initial_evidence_mismatch")
        if approval.backup_evidence_sha256 is not None \
                and hashlib.sha256(evidence_bytes).hexdigest() != approval.backup_evidence_sha256:
            raise Refused("refused", "backup_evidence_binding_mismatch")
        expected_target = be.Expected(db_identity=written.db_identity, account_id=written.account_id,
                                      job_key=approval.job_key, basis_from=basis.valid_from)
        try:
            evidence_now = _clock_now(clock)
        except _ClockInvalid:
            raise Refused("refused", "clock_invalid") from None
        try:
            initial = be.verify_backup_evidence_record(initial_bytes, initial_signature, mode=op.MODE,
                                                       trust=write_inputs.trust, now=evidence_now,
                                                       expected=expected_target)
            evidence = be.verify_backup_evidence(evidence_bytes, evidence_signature, mode=op.MODE,
                                                 trust=write_inputs.trust, now=evidence_now, expected=expected_target)
        except be.OpsBackupEvidenceRefused as error:
            raise Refused("refused", error.code) from None
        if any(getattr(initial, f) != getattr(evidence, f) for f in EVIDENCE_MATCH_FIELDS) \
                or initial.evidence_id == evidence.evidence_id:
            raise Refused("refused", "resume_backup_evidence_mismatch")
    except Refused as refused:
        return _resume_result(refused.status, refused.code, **base)
    # 9 app import, only now
    try:
        from app.srs import migration
        from app.srs.engine import DEFAULT_CONFIG
        from app.srs.storage import SrsWriteError
    except ImportError:
        return _resume_result("failed", "product_import_failed", **base)
    # 10 the plan through the product rules (candidates, product fingerprint) -- before any connection
    if plan.config_version != DEFAULT_CONFIG.config_version:
        return _resume_result("refused", "plan_file_config_mismatch", **base)
    try:
        planned = pfile.to_candidates(plan)
    except pfile.OpsPlanFileError as error:
        return _resume_result("refused", error.code, **base)
    read_expected, write_expected = contract_profiles(scope, write_inputs.target.database)
    # 11 state pre-read on the status step (one read transaction; the nine values from the same rows)
    try:
        found = read_status(_timed_connector(read_inputs, read_expected, driver, clock), request, migration)
    except pc.OpsProductConnectionError as error:
        return _resume_result(_connection_status(error.code), error.code, **base)
    except Exception:
        return _resume_result("failed", "status_read_failed", **base)
    if found is None:
        return _resume_result("refused", "resume_target_not_found", **base)   # never a first apply / new key
    row, cards, snapshots = found
    report = judge_status(row, cards, snapshots, request, DEFAULT_CONFIG.config_version)
    state = report["state"]
    if state in _STATE_REFUSALS:
        status, code, exit_code = _STATE_REFUSALS[state]
        out, _ = _resume_result("refused" if status == "refused" else "ok", code or report.get("reason"),
                                state=state, **base)
        return out, exit_code
    window = migration.rollback_window(row["started_at"], migration.now_utc())
    if window != "open":
        return _resume_result("refused", "migration_resume_window_closed" if window == "expired"
                              else "migration_resume_window_unverifiable", **base)
    expected_progress = progress_values(row, snapshots)
    # 12 the new evidence again, right before the first write connection
    try:
        be.recheck(evidence, _clock_now(clock))
    except be.OpsBackupEvidenceRefused as error:
        return _resume_result("refused", error.code, **base)
    except _ClockInvalid:
        return _resume_result("refused", "clock_invalid", **base)
    # 13 exactly one apply_plan call
    tracked = _Tracked(_timed_connector(write_inputs, write_expected, driver, clock))
    facts = dict(card_count=len(planned), cursor_before=report["cursor"], artifact_sha256=plan.artifact_sha256,
                 evidence_sha256=evidence.evidence_sha256, initial_evidence_sha256=initial.evidence_sha256,
                 restore_verified=False, backup_artifact_checked=False)
    try:
        results = migration.apply_plan(planned, request.run_key, approved=True, batch_size=batch_size,
                                       connect=tracked, new_run_only=False, existing_run_only=True,
                                       expected_progress=expected_progress)
    except Exception as error:
        code = getattr(error, "code", None) if isinstance(error, (SrsWriteError, pc.OpsProductConnectionError)) \
            else None
        started = tracked.first_committed or tracked.first_uncertain or tracked.opened > 1
        if not started and isinstance(error, SrsWriteError):
            return _resume_result("refused", code, **base, **facts)        # P2 / window under the lock: no write
        if not started and isinstance(error, pc.OpsProductConnectionError) and tracked.opened == 0:
            return _resume_result(_connection_status(code), code, **base, **facts)
        return _resume_result("failed", code or "resume_failed",
                              phase="after_start" if started else "first_connection", confirmed="unknown",
                              uncertain=True, next="status_required", **facts)
    counts = dict(sorted(Counter(r["result"] for r in results).items()))
    if len(results) < len(planned):
        out, _ = _resume_result("ok", None, phase="partial", cursor=len(results), results=counts, next="status",
                                **facts)
        return out, 3
    out, _ = _resume_result("ok", None, phase="completed", cursor=len(results), results=counts, **facts)
    return out, 5 if counts.get("conflict") or counts.get("blocked") else 0


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:                  # usage errors: fixed output, exit 2
        raise Refused("usage", "usage")


def main(argv: list[str]) -> int:
    parser = _Parser(prog="srs_migrate.py", add_help=False)
    parser.add_argument("command", nargs="?", default="dry-run")
    parser.add_argument("--account", type=int)
    parser.add_argument("--run-key")
    parser.add_argument("--personal-id", type=int, action="append", default=[])
    parser.add_argument("--lexeme-id", type=int, action="append", default=[])
    parser.add_argument("--out")
    parser.add_argument("--batch-size")
    parser.add_argument("--plan")
    parser.add_argument("--backup-evidence")
    parser.add_argument("--backup-signature")
    parser.add_argument("--initial-evidence")
    parser.add_argument("--initial-evidence-signature")
    try:
        args = parser.parse_args(argv)
        apply_only = (args.batch_size, args.plan, args.backup_evidence, args.backup_signature)
        resume_only = (args.initial_evidence, args.initial_evidence_signature)
        if args.command == "apply":
            if args.out or not all(v is not None for v in apply_only) or any(v is not None for v in resume_only):
                raise Refused("usage", "usage")
            batch_from_text(args.batch_size)
        elif args.command == RESUME_COMMAND:
            if args.out or not all(v is not None for v in apply_only + resume_only):
                raise Refused("usage", "usage")
            batch_from_text(args.batch_size)
        elif args.command not in ("dry-run", "status") or (args.command == "dry-run") != bool(args.out) \
                or any(v is not None for v in apply_only + resume_only):
            raise Refused("usage", "usage")                    # dry-run needs --out, status refuses it
        make_request(args.account, args.run_key, args.personal_id, args.lexeme_id)
        # No real driver or connection path exists in this unit: the command line stops here.
        raise Refused("refused", "connection_not_available")
    except Refused as refused:
        out, code = {"status": refused.status, "code": refused.code}, EXIT[refused.status]
    print(json.dumps(out, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
