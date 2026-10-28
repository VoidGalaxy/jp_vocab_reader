"""P-RB recovery tool, unit 1: precheck, plan fingerprint, preview, step A and resume status
(P_RB_TOOL_CONTRACT.md). Operator paths only -- no HTTP route.

- `preview` reads only (one read-only snapshot transaction).
- `prepare` (step A) runs on ONE connection and ONE transaction under the account lock:
  set (or re-call) the account's write block -> judge again -> compare the plan fingerprint ->
  baseline -> progress record `prepared`. Any refusal or failure rolls the whole transaction
  back: a block created by this call disappears with it; a block that already existed is not
  touched. Step A changes no recovery data (cards, logs, runs, settings).
- `resume_status` reads only and names the next step. It never runs it.

Not in this unit: the recovery itself (step B), the mode switch, verify, completed release.
The secret token arrives as an argument from the caller's hidden input; it is hashed, never
stored, printed or logged."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from app.account_blocks import _check_key, active_recovery_record, set_block_locked
from app.account_write import active_block, lock_account, token_hash
from app.database import get_connection, is_postgres_connection, now_utc
from app.srs import goals, migration
from app.srs.completion import SEOUL
from app.srs.engine import CardKey
from app.srs.identity import is_identity_unknown
from app.srs.storage import load_card

MARGIN = timedelta(hours=24)        # contract 3-4: a WARNING below this, never a refusal
_PLAN = re.compile(r"^[0-9a-f]{64}$")
CARD_TABLES = (("personal", "vocab_items", "id"), ("lexeme", "user_word_progress", "lexeme_id"))
LOG_TABLES = (("personal", "review_logs", "vocab_item_id", "reviewed_at"),
              ("lexeme", "lexeme_review_logs", "lexeme_id", "created_at"))


class RecoveryRefused(RuntimeError):
    """A refusal with fixed reason codes; the transaction (if any) was rolled back."""

    def __init__(self, code: str, reasons: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.reasons = list(reasons or [])


def rollback_key_for(recovery_key: str, source_run_id: int) -> str:
    """Contract 2-3: the deterministic rollback key of step B for one source run."""
    return f"prb:{recovery_key}:{int(source_run_id)}"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


# ---- the account's conversion history (contract 3-1) -----------------------------------------
def _account_runs(connection: Any, user_id: int) -> tuple[dict[int, dict], bool]:
    """(this account's apply / rollback runs by id, every scope readable)."""
    runs, readable = {}, True
    for row in connection.execute("SELECT * FROM srs_migration_runs WHERE mode IN ('apply', 'rollback') "
                                  "ORDER BY id").fetchall():
        try:
            scope = json.loads(row["scope_json"])
            owner = scope.get("user_id") if isinstance(scope, dict) else None
        except (TypeError, ValueError):
            readable = False
            continue
        if owner == user_id:
            runs[int(row["id"])] = dict(row, scope=scope)
    return runs, readable


def _rollback_results(run: dict) -> list | None:
    try:
        results = json.loads(run["summary_json"] or "null")
    except (TypeError, ValueError):
        return None
    return results if isinstance(results, list) else None


def _classify_history(connection: Any, user_id: int, runs: dict[int, dict], reasons: set[str]) -> dict:
    """Targets and per-card chains. A chain is the card's apply / rollback records in id
    order; it must alternate apply -> rollback(of that apply) -> apply ..., with card versions
    never going back. The last record decides: an apply of a `completed` run makes the card a
    target; a rollback makes it a card that must be legacy now. Anything else is refused,
    never guessed."""
    applies = {rid: run for rid, run in runs.items() if run["mode"] == "apply"}
    rollbacks = {rid: run for rid, run in runs.items() if run["mode"] == "rollback"}
    by_source: dict[int, list[dict]] = {}
    for run in rollbacks.values():
        source = run["scope"].get("source_run_id")
        if isinstance(source, int):
            by_source.setdefault(source, []).append(run)
    prior: dict[int, str] = {}
    proven_deleted: set[tuple[int, str, int]] = set()
    for rid, run in applies.items():
        if run["status"] == "started":
            reasons.add("migration_run_in_progress")
        elif run["status"] == "failed":
            reasons.add("migration_run_failed")
        elif run["status"] == "aborted":
            linked = [r for r in by_source.get(rid, []) if r["status"] == "completed"]
            results = _rollback_results(linked[0]) if len(linked) == 1 else None
            if results is None or not results:
                reasons.add("prior_rollback_unverifiable")
                prior[rid] = "unverifiable"
            elif any(not isinstance(r, dict) or r.get("result") not in PROVEN_RESULTS for r in results):
                reasons.add("prior_partial_rollback")
                prior[rid] = "partial"
            elif not _rollback_proven(connection, user_id, rid, linked[0], results):
                reasons.add("prior_rollback_record_invalid")
                prior[rid] = "invalid"
            else:
                prior[rid] = "rolled_back"
                for entry in results:
                    if entry["result"] == "deleted_proven":
                        proven_deleted.add((rid, entry["kind"], entry["ref_id"]))
    rollback_of = {r["id"]: r["scope"].get("source_run_id") for r in rollbacks.values()}
    records: dict[tuple[str, int], list[dict]] = {}
    for row in connection.execute("SELECT * FROM srs_migration_snapshots WHERE user_id = ? ORDER BY id",
                                  (user_id,)).fetchall():
        if int(row["run_id"]) in runs:
            records.setdefault((row["card_kind"], int(row["card_ref"])), []).append(dict(row))
        else:
            reasons.add("card_history_ambiguous")            # a snapshot of a run not of this account
    targets: dict[int, list[dict]] = {}
    legacy_now: list[tuple[str, int, int]] = []
    for key, chain in records.items():
        previous_apply, version_floor, ok = None, -1, True
        for index, record in enumerate(chain):
            run = runs[int(record["run_id"])]
            if int(record["card_version_before"]) < version_floor:
                ok = False
                break
            if run["mode"] == "apply":
                if previous_apply is not None:
                    ok = False                                # two conversions without a rollback between
                    reasons.add("overlapping_source_runs")
                    break
                previous_apply = record
            else:
                if previous_apply is None or rollback_of.get(run["id"]) != int(previous_apply["run_id"]):
                    ok = False
                    break
                previous_apply = None
            version_floor = int(record["card_version_before"]) + 1
        if not ok:
            reasons.add("card_history_ambiguous")
            continue
        last = chain[-1]
        last_run = runs[int(last["run_id"])]
        if last_run["mode"] == "apply":
            if last_run["status"] == "completed":
                targets.setdefault(int(last_run["id"]), []).append(last)
            elif last_run["status"] == "aborted" and (int(last_run["id"]), key[0], key[1]) not in proven_deleted:
                reasons.add("prior_partial_rollback")         # its rollback left this card converted
        else:
            legacy_now.append((key[0], key[1], version_floor))
    return {"targets": targets, "legacy_now": legacy_now, "prior": prior}


_SUMMARY_KEYS = {"kind", "ref_id", "result", "preserved_reviews"}
_DELETED_KEYS = {"kind", "ref_id", "result"}
PROVEN_RESULTS = ("rolled_back", "deleted_proven")


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _rollback_proven(connection: Any, user_id: int, apply_id: int, rollback_run: dict, results: list) -> bool:
    """Contract 3-1 (1), third pass: a past rollback counts only when its summary and its
    records prove it card by card -- not because runs and versions line up. Every apply card
    has exactly one `rolled_back` summary entry and exactly one rollback record, nothing more;
    each record has the rollback shape for that very card (identity included), a readable
    baseline and restore projection, and the versions the rollback rule gives. Read only."""
    applied = {(r["card_kind"], int(r["card_ref"])): dict(r) for r in connection.execute(
        "SELECT * FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ?", (apply_id, user_id)).fetchall()}
    rows = [dict(r) for r in connection.execute(
        "SELECT * FROM srs_migration_snapshots WHERE run_id = ?", (rollback_run["id"],)).fetchall()]
    entries, deleted = {}, set()
    for entry in results:
        if not isinstance(entry, dict):
            return False
        if entry.get("result") == "deleted_proven":
            # written by recovery step B for a card whose deletion the ledger proves (contract 12)
            if set(entry) != _DELETED_KEYS or entry["kind"] != "personal" or not _int(entry["ref_id"]):
                return False
            key = (entry["kind"], entry["ref_id"])
            if key in entries or key in deleted:
                return False
            deleted.add(key)
            continue
        if (set(entry) != _SUMMARY_KEYS or entry["kind"] not in ("personal", "lexeme") or not _int(entry["ref_id"])
                or not _int(entry["preserved_reviews"]) or entry["preserved_reviews"] < 0):
            return False
        key = (entry["kind"], entry["ref_id"])
        if key in entries or key in deleted:
            return False                                      # duplicate entry
        entries[key] = entry
    source = connection.execute("SELECT started_at FROM srs_migration_runs WHERE id = ?", (apply_id,)).fetchone()
    for key in deleted:
        if key in {(r["card_kind"], int(r["card_ref"])) for r in rows} or source is None \
                or not _deletion_proven(connection, CardKey(key[0], user_id, key[1]), source["started_at"]):
            return False
    records = {}
    for row in rows:
        key = (row["card_kind"], int(row["card_ref"]))
        if row["user_id"] != user_id or key in records:
            return False                                      # another account's, or a duplicate
        records[key] = row
    if not applied or set(entries) | deleted != set(applied) or set(records) != set(entries):
        return False                                          # missing or unknown cards
    for key, record in records.items():
        try:
            shape = migration._record_shape("rollback", key[0], key[1], json.loads(record["legacy_json"]),
                                            migration._card_columns(connection, key[0]))
        except (TypeError, ValueError):
            return False
        read = migration._read_rollback_record(record)
        if shape is None or read is None:
            return False
        baseline_values, _restore = read
        expected = int(applied[key]["card_version_before"]) + 1 + entries[key]["preserved_reviews"]
        if int(record["card_version_before"]) != expected or baseline_values["card_version"] != expected + 1:
            return False
    return True


# ---- deletion proof (contract 3-2) -------------------------------------------------------------
def _deletion_proven(connection: Any, key: CardKey, source_started: Any) -> bool:
    if key.kind != "personal":
        return False                                          # no deletion ledger for subscribed rows
    if connection.execute("SELECT 1 FROM vocab_items WHERE id = ?", (key.ref_id,)).fetchone() is not None:
        return False
    started = goals.read_utc(source_started)
    rows = connection.execute("SELECT deleted_at FROM srs_card_deletions WHERE user_id = ? AND "
                              "card_kind = 'personal' AND card_ref = ?", (key.user_id, key.ref_id)).fetchall()
    if not rows or started is None:
        return False
    times = [goals.read_utc(r["deleted_at"]) for r in rows]
    if any(t is None for t in times) or not any(t >= started for t in times):
        return False
    return not is_identity_unknown(connection, key.user_id, "personal", key.ref_id)


# ---- the whole judgement -----------------------------------------------------------------------
# Gate E F-1: every release gate check whose inputs step B does not repair is also judged before
# any recovery write, by the SAME functions as verify: the target's logs, progress rows, ledger,
# identity flags and log references (I1a, I2a, I4a, I5a -- B keeps evidence_from_log_id, it is
# in migration.ROLLBACK_PRESERVED, and adds only rollback runs / snapshots, never a receipt or a
# card), other accounts' references into it (N) and the global personal card id sequence (S --
# B inserts no card, so it never moves that sequence). Anything but "pass" (fail, unknown,
# not_evaluated) blocks. The post-conditions (FSRS rows 0, legacy mode, recovery result,
# baseline comparisons) are not preconditions.
PRECONDITION_CHECKS = ("I1a", "I2a", "I4a", "I5a", "N", "S")


def gate_preconditions(connection: Any, user_id: int) -> dict:
    from app.srs import recovery_scope

    target = recovery_scope.account(connection, user_id)
    checks = {name: target[name] for name in ("I1a", "I2a", "I4a", "I5a")}
    checks["N"] = recovery_scope.inflow(connection, user_id)
    checks["S"] = recovery_scope.sequence(connection)
    return checks


def assess(connection: Any, user_id: int, recovery_key: str | None = None, *, at: datetime | None = None) -> dict:
    """Read only, on the caller's connection (a read-only snapshot for preview; the locked
    transaction of step A). Returns the report and the fingerprinted plan material."""
    at = at or now_utc()
    reasons: set[str] = set()
    warnings: set[str] = set()
    if connection.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        raise RecoveryRefused("account_not_found")
    runs, readable = _account_runs(connection, user_id)
    if not readable:
        reasons.add("run_scope_unverifiable")
    history = _classify_history(connection, user_id, runs, reasons)
    setting = connection.execute("SELECT srs_mode, settings_version FROM srs_user_settings WHERE user_id = ?",
                                 (user_id,)).fetchone()
    mode = setting["srs_mode"] if setting else None
    if mode not in ("fsrs", "shadow"):
        reasons.add("srs_mode_unexpected")
    block = active_block(connection, user_id)
    if block is not None and (not block["consistent"] or (recovery_key is not None
                                                           and block["recovery_key"] != recovery_key)):
        reasons.add("recovery_block_conflict")
    record = active_recovery_record(connection, user_id)
    if record is not None and (not record["consistent"] or (recovery_key is not None
                                                             and record["recovery_key"] != recovery_key)):
        reasons.add("recovery_in_progress")
    target_keys: set[tuple[str, int]] = set()
    cards, deleted = [], []
    windows = []
    for run_id in sorted(history["targets"], reverse=True):                 # newest conversion first
        run = runs[run_id]
        state = migration.rollback_window(run["started_at"], at)
        if state == "expired":
            reasons.add("rollback_window_closed")
        elif state == "unverifiable":
            reasons.add("rollback_window_unverifiable")
        else:
            started = goals.read_utc(run["started_at"])
            if started + migration.ROLLBACK_WINDOW - at < MARGIN:
                warnings.add("rollback_window_margin")
        windows.append(state)
        for record_row in history["targets"][run_id]:
            key = CardKey(record_row["card_kind"], user_id, int(record_row["card_ref"]))
            target_keys.add((key.kind, key.ref_id))
            judged = migration.judge_rollback_card(connection, key, record_row, run)
            verdict = judged["verdict"]
            if verdict == "rollback":
                card = judged["card"]
                cards.append([run_id, key.kind, key.ref_id, int(record_row["id"]), int(card["srs_card_version"]),
                              len(judged["later"])])
            elif verdict == "missing" and _deletion_proven(connection, key, run["started_at"]):
                deleted.append([run_id, key.kind, key.ref_id, int(record_row["id"])])
            elif verdict == "missing":
                reasons.add("card_missing_unproven")
            else:
                reasons.add({"access_lost": "access_lost", "identity_unknown": "card_identity_unknown",
                             "snapshot_incomplete": "snapshot_incomplete", "conflict": "card_conflict",
                             "unreadable": "review_history_unreadable",
                             "history_mismatch": "rollback_history_mismatch"}[verdict])
    for kind, table, ref in CARD_TABLES:
        for row in connection.execute(f"SELECT {ref} AS ref FROM {table} WHERE user_id = ? AND srs_engine = 'fsrs' "
                                      "ORDER BY 1", (user_id,)).fetchall():
            if (kind, int(row["ref"])) not in target_keys:
                reasons.add("fsrs_card_without_snapshot")
    for kind, ref, version_floor in history["legacy_now"]:
        card = load_card(connection, CardKey(kind, user_id, ref))
        if card is not None and (card.get("srs_engine") != "legacy" or int(card["srs_card_version"]) < version_floor):
            reasons.add("card_history_ambiguous")
    for name, check in gate_preconditions(connection, user_id).items():
        if not _passed(check):
            reasons.add(f"gate_precondition_{name}")
    if not history["targets"] and not reasons:
        reasons.add("nothing_to_recover")
    inputs = _plan_inputs(connection, user_id, runs, target_keys)
    material = {
        "user_id": user_id, "mode": mode, "settings_version": setting["settings_version"] if setting else None,
        "targets": [[rid, runs[rid]["run_key"], runs[rid]["started_at"], runs[rid]["config_version"],
                     sorted(int(r["id"]) for r in history["targets"][rid])] for rid in sorted(history["targets"])],
        "cards": sorted(cards), "deleted_proven": sorted(deleted),
        "prior": sorted([rid, state] for rid, state in history["prior"].items()),
        "windows": sorted(set(windows)), "reasons": sorted(reasons), "inputs": inputs,
    }
    report = {
        "status": "blocked" if reasons else "ready", "user_id": user_id,
        "reasons": sorted(reasons), "warnings": sorted(warnings),
        "counts": {"target_runs": len(history["targets"]), "rollback_cards": len(cards),
                   "deleted_proven": len(deleted), "prior_rolled_back_runs":
                       sum(1 for s in history["prior"].values() if s == "rolled_back")},
        "plan": _sha(material),
    }
    return {"report": report, "material": material}


def _rows_digest(connection: Any, query: str, params: tuple) -> str:
    digest = hashlib.sha256()
    for row in connection.execute(query, params).fetchall():
        digest.update(_canonical(dict(row)).encode())
    return digest.hexdigest()


def _plan_inputs(connection: Any, user_id: int, runs: dict[int, dict], target_keys: set) -> dict:
    """Contract 3-5 (third pass): every stored value the judgement or the rollback would read,
    as whole rows (no count or version shortcut), hashed -- never copied or printed. Nothing
    here moves by itself between calls, so an unchanged database gives the same plan."""
    personal = sorted(ref for kind, ref in target_keys if kind == "personal")
    lexemes = sorted(ref for kind, ref in target_keys if kind == "lexeme")

    def each(query: str, refs: list[int]) -> list[str]:
        return [_rows_digest(connection, query, (user_id, ref)) for ref in refs]

    run_ids = sorted(runs)
    return {
        "runs": _sha([[rid, {k: v for k, v in runs[rid].items() if k != "scope"}] for rid in run_ids]),
        "snapshots": _rows_digest(connection, "SELECT * FROM srs_migration_snapshots WHERE user_id = ? ORDER BY id",
                                  (user_id,)),
        "personal_cards": _sha(each("SELECT * FROM vocab_items WHERE user_id = ? AND id = ?", personal)),
        "personal_logs": _sha(each("SELECT * FROM review_logs WHERE user_id = ? AND vocab_item_id = ? ORDER BY id",
                                   personal)),
        "lexeme_cards": _sha(each("SELECT * FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", lexemes)),
        "lexeme_logs": _sha(each("SELECT * FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ? ORDER BY id",
                                 lexemes)),
        "lexeme_access": _sha([_rows_digest(connection, "SELECT w.* FROM shared_deck_words w JOIN user_deck_subscriptions "
                                            "s ON s.shared_deck_id = w.shared_deck_id WHERE s.user_id = ? AND "
                                            "w.lexeme_id = ? ORDER BY w.shared_deck_id", (user_id, ref))
                               for ref in lexemes]),
        "subscriptions": _rows_digest(connection, "SELECT * FROM user_deck_subscriptions WHERE user_id = ? ORDER BY 1",
                                      (user_id,)),
        "settings": _rows_digest(connection, "SELECT * FROM srs_user_settings WHERE user_id = ?", (user_id,)),
        "identity_flags": _rows_digest(connection, "SELECT * FROM srs_card_identity_flags WHERE user_id = ? ORDER BY id",
                                       (user_id,)),
        "deletions": _rows_digest(connection, "SELECT * FROM srs_card_deletions WHERE user_id = ? ORDER BY id",
                                  (user_id,)),
        "evidence_restarts": _rows_digest(connection, "SELECT * FROM srs_evidence_restarts WHERE user_id = ? ORDER BY id",
                                          (user_id,)),
    }


# ---- baseline (contract 4-2) ----------------------------------------------------------------
def baseline(connection: Any, user_id: int, material: dict, at: datetime) -> dict:
    """Hashes and counts only. The reference instant and the date list are STORED, so the
    later comparison does not move at midnight."""
    count, digest, log_days = _log_state(connection, user_id)
    days = sorted(log_days | {at.astimezone(SEOUL).date()})
    cards = [[c[1], c[2], c[4]] for c in material["cards"]]
    return {"at": at.isoformat(), "days": [d.isoformat() for d in days],
            "logs": {"count": count, "digest": digest},
            "preserved": {"count": len(cards), "digest": _preserved_digest(connection, user_id, cards)},
            "metrics_digest": _metrics_digest(connection, user_id, days), "cards": cards}


def _log_state(connection: Any, user_id: int) -> tuple[int, str, set[date]]:
    """(count, digest of every log row of the account, Seoul dates of readable log times)."""
    digest, count, days = hashlib.sha256(), 0, set()
    for kind, table, _ref, stamp in LOG_TABLES:
        for row in connection.execute(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY id", (user_id,)).fetchall():
            row = dict(row)
            digest.update(_canonical([kind, row]).encode())
            count += 1
            when = goals.read_utc(row[stamp])
            if when is not None:
                days.add(when.astimezone(SEOUL).date())
    return count, digest.hexdigest(), days


def _preserved_digest(connection: Any, user_id: int, cards: list) -> str:
    """The never-restored columns (completion history, past-learning mark, evidence
    boundary) of the given [kind, ref, version] cards, in that order."""
    digest = hashlib.sha256()
    for kind, ref, _version in cards:
        card = load_card(connection, CardKey(kind, user_id, ref)) or {}
        digest.update(_canonical([kind, ref, {n: card.get(n) for n in migration.ROLLBACK_PRESERVED}]).encode())
    return digest.hexdigest()


def _metrics_digest(connection: Any, user_id: int, days: list[date]) -> str:
    """I7 figures per stored day (noon Seoul): introduced count / status / lower bound, the
    calendar's review count and the daily goal -- the E-4 deletion-baseline figures."""
    from app.repositories import stats_history_repository

    setting = goals.account_goal(connection, user_id)
    target = setting["daily_new_goal"] if setting else goals.DEFAULT_DAILY_NEW_GOAL
    metrics = []
    for day in days:
        stamp = datetime.combine(day, time(12), SEOUL)
        counted = goals.introduction_count(connection, user_id, stamp)
        calendar = len(stats_history_repository._review_rows(connection, user_id, day, day + timedelta(days=1)))
        metrics.append([day.isoformat(), counted.status, counted.count, counted.at_least, calendar, target])
    return _sha(metrics)


# ---- entry points ------------------------------------------------------------------------------
def preview(user_id: int, recovery_key: str | None = None) -> dict:
    """Read only (contract 1): one read-only snapshot transaction, no write of any kind."""
    from app.srs.invariant_audit import read_snapshot

    if recovery_key is not None:
        _check_key(recovery_key)
    with get_connection() as connection:
        with read_snapshot(connection):
            return assess(connection, user_id, recovery_key)["report"]


def prepare(user_id: int, recovery_key: str, token: str, plan: str) -> dict:
    """Step A (contract 2-2). One connection, one transaction, the account lock first."""
    _check_key(recovery_key)
    digest = token_hash(token)
    if not isinstance(plan, str) or not _PLAN.fullmatch(plan):
        raise RecoveryRefused("plan_required")
    with get_connection() as connection:
        lock_account(connection, user_id)
        record = active_recovery_record(connection, user_id)
        if record is not None:
            if not record["consistent"] or record["recovery_key"] != recovery_key:
                raise RecoveryRefused("recovery_in_progress")
        block = set_block_locked(connection, user_id, recovery_key, digest)   # new, or the same key + token
        if record is not None:
            # a re-call of the same step A: nothing is written again
            if record["plan_fingerprint"] != plan or record["block_id"] != block["block_id"]:
                raise RecoveryRefused("recovery_plan_mismatch")
            return {"status": record["state"], "created": False, "block_id": block["block_id"],
                    "record_id": int(record["id"])}
        at = now_utc()
        judged = assess(connection, user_id, recovery_key, at=at)
        report = judged["report"]
        if report["status"] != "ready":
            raise RecoveryRefused("recovery_blocked", report["reasons"])
        if report["plan"] != plan:
            raise RecoveryRefused("plan_changed")
        material = judged["material"]
        base = baseline(connection, user_id, material, at)
        sources = [{"run_id": t[0], "rollback_key": rollback_key_for(recovery_key, t[0])} for t in material["targets"]]
        row = connection.execute(
            "INSERT INTO account_recovery_runs (user_id, block_id, recovery_key, plan_fingerprint, state, "
            "active_user_id, source_runs_json, baseline_json, prepared_at) VALUES (?, ?, ?, ?, 'prepared', ?, ?, ?, ?) "
            "RETURNING id",
            (user_id, block["block_id"], recovery_key, plan, user_id, _canonical(sources), _canonical(base),
             at.isoformat()),
        ).fetchone()
        return {"status": "prepared", "created": True, "block_id": block["block_id"], "record_id": int(row["id"]),
                "warnings": report["warnings"], "counts": report["counts"]}


_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_BASELINE_KEYS = {"at", "days", "logs", "preserved", "metrics_digest", "cards"}


def _instant(value: Any) -> datetime | None:
    return goals.read_utc(value) if isinstance(value, str) else None


def _digest_pair(value: Any) -> bool:
    return (isinstance(value, dict) and set(value) == {"count", "digest"} and _int(value["count"])
            and value["count"] >= 0 and isinstance(value["digest"], str) and bool(_HEX64.fullmatch(value["digest"])))


def _stored_sources(connection: Any, user_id: int, recovery_key: str, record: dict) -> list[dict] | None:
    """Contract 2-3: the stored source list, or None. A non-empty JSON list of
    {run_id, rollback_key} only; run ids unique, of this account's APPLY runs, each with its
    deterministic rollback key."""
    sources = json.loads(record["source_runs_json"])
    if not isinstance(sources, list) or not sources:
        return None
    seen = set()
    for source in sources:
        if (not isinstance(source, dict) or set(source) != {"run_id", "rollback_key"} or not _int(source["run_id"])
                or source["run_id"] in seen or source["rollback_key"] != rollback_key_for(recovery_key, source["run_id"])):
            return None
        seen.add(source["run_id"])
        run = connection.execute("SELECT mode, scope_json FROM srs_migration_runs WHERE id = ?",
                                 (source["run_id"],)).fetchone()
        scope = json.loads(run["scope_json"]) if run is not None else None
        if run is None or run["mode"] != "apply" or not isinstance(scope, dict) or scope.get("user_id") != user_id:
            return None
    return sources


def _baseline_ok(connection: Any, user_id: int, record: dict, source_ids: set[int],
                 judged_cards: list | None) -> bool:
    """Contract 4-2 as stored by step A, field by field (no coercion: a bool is not an
    integer, text is not a number). `judged_cards` (only while `prepared`) are the cards a
    fresh judgement would roll back, as [kind, ref, version]."""
    base = json.loads(record["baseline_json"])
    if not isinstance(base, dict) or set(base) != _BASELINE_KEYS:
        return False
    at = _instant(base["at"])
    if at is None or base["at"] != record["prepared_at"]:
        return False
    days = base["days"]
    if not isinstance(days, list) or not days or any(not isinstance(d, str) for d in days):
        return False
    try:
        parsed = [date.fromisoformat(d) for d in days]
    except ValueError:
        return False
    if [d.isoformat() for d in parsed] != days or sorted(set(parsed)) != parsed \
            or at.astimezone(SEOUL).date() not in parsed:
        return False                                            # unique, ascending, and holds A's own day
    if not _digest_pair(base["logs"]) or not _digest_pair(base["preserved"]):
        return False
    if not isinstance(base["metrics_digest"], str) or not _HEX64.fullmatch(base["metrics_digest"]):
        return False
    cards = base["cards"]
    if not isinstance(cards, list) or base["preserved"]["count"] != len(cards):
        return False
    keys = set()
    for card in cards:
        if (not isinstance(card, list) or len(card) != 3 or card[0] not in ("personal", "lexeme")
                or not _int(card[1]) or card[1] <= 0 or not _int(card[2]) or card[2] < 0
                or (card[0], card[1]) in keys):
            return False
        keys.add((card[0], card[1]))
        marks = ", ".join("?" for _ in source_ids)
        if connection.execute(f"SELECT 1 FROM srs_migration_snapshots WHERE run_id IN ({marks}) AND user_id = ? "
                              "AND card_kind = ? AND card_ref = ? LIMIT 1",
                              (*sorted(source_ids), user_id, card[0], card[1])).fetchone() is None:
            return False                                        # not a card of the stored source runs
    return judged_cards is None or cards == judged_cards


def _state_step(record: dict, block: dict, source_status: list, rollback_status: list) -> str | None:
    """Contract 2-3 table: the whole combination, never the state word alone."""
    started = block["changes_started"]
    prepared, applied, verified = (_instant(record["prepared_at"]), _instant(record["applied_at"]),
                                   _instant(record["verified_at"]))
    if prepared is None or started not in (0, 1) or isinstance(started, bool):
        return None
    if record["state"] == "prepared":
        if (started == 0 and record["applied_at"] is None and record["verified_at"] is None
                and record["verification_json"] is None and record["verified_digest"] is None
                and all(s == "completed" for s in source_status) and all(s is None for s in rollback_status)):
            return "run_recovery"
        return None
    if not (started == 1 and applied is not None and applied >= prepared
            and all(s == "aborted" for s in source_status) and all(s == "completed" for s in rollback_status)):
        return None
    if record["state"] == "applied":
        if record["verified_at"] is None and record["verification_json"] is None and record["verified_digest"] is None:
            return "verify"
        return None
    if record["state"] == "verified":
        try:
            checks = json.loads(record["verification_json"]) if isinstance(record["verification_json"], str) else None
        except ValueError:
            checks = None
        if (verified is not None and verified >= applied
                and isinstance(record["verified_digest"], str) and _HEX64.fullmatch(record["verified_digest"])):
            if proof_ok(checks):
                return "await_release"
            if legacy_proof(checks):
                return "verify"                # contract 15-4: an old-shape proof needs an explicit verify
    return None


def resume_status(user_id: int, recovery_key: str) -> dict:
    """Read only (contract 2-3): the next step named from the database alone; never run here.
    Any damaged or inconsistent stored value ends in `report_only` (no exception, no write)."""
    from app.srs.invariant_audit import read_snapshot

    _check_key(recovery_key)
    with get_connection() as connection:
        with read_snapshot(connection):
            block = active_block(connection, user_id)
            record = active_recovery_record(connection, user_id)
            if block is None and record is None:
                closed = connection.execute("SELECT state FROM account_recovery_runs WHERE user_id = ? AND "
                                            "recovery_key = ?", (user_id, recovery_key)).fetchone()
                return {"next": "closed" if closed else "preview"}
            if (block is None or record is None or not block["consistent"] or not record["consistent"]
                    or block["recovery_key"] != recovery_key or record["recovery_key"] != recovery_key
                    or record["block_id"] != block["id"]):
                return {"next": "report_only", "reason": "recovery_state_inconsistent"}
            try:
                sources = _stored_sources(connection, user_id, recovery_key, record)
                source_ids = {source["run_id"] for source in sources} if sources else set()
                judged_cards = None
                if sources and record["state"] == "prepared":
                    # prepared only: nothing may have changed since step A (plan and targets)
                    judged = assess(connection, user_id, recovery_key)
                    targets = {t[0] for t in judged["material"]["targets"]}
                    if (judged["report"]["status"] != "ready" or judged["report"]["plan"] != record["plan_fingerprint"]
                            or targets != source_ids):
                        sources = None
                    judged_cards = [[c[1], c[2], c[4]] for c in judged["material"]["cards"]]
                if sources is not None and not _baseline_ok(connection, user_id, record, source_ids, judged_cards):
                    sources = None
            except Exception:                                  # noqa: BLE001 -- reported, never raised
                sources = None
            if sources is None:
                return {"next": "report_only", "reason": "recovery_record_invalid"}
            runs = {int(r["id"]): dict(r) for r in connection.execute(
                "SELECT id, run_key, mode, status FROM srs_migration_runs").fetchall()}
            keys = {r["run_key"]: r for r in runs.values() if r["mode"] == "rollback"}
            source_status = [runs.get(s["run_id"], {}).get("status") for s in sources]
            rollback_status = [keys.get(s["rollback_key"], {}).get("status") for s in sources]
            step = _state_step(record, block, source_status, rollback_status)
            if step is None:
                return {"next": "report_only", "reason": "recovery_state_inconsistent"}
            if step == "await_release":
                # contract 13: a stored proof is current only if the current data still passes
                # every check AND has the stored D; otherwise it is a past record
                try:
                    checks = _checks(connection, user_id, record, sources)
                    current = verification_digest(connection, user_id, block["id"], record["id"])
                except Exception:                              # noqa: BLE001 -- reported, never raised
                    return {"next": "report_only", "reason": "verification_not_current"}
                if not gate_pass(checks):
                    return {"next": "report_only", "reason": "verification_not_current"}
                if current != record["verified_digest"]:
                    return {"next": "verify"}                  # passes, but the proof must be refreshed
            return {"next": step}


# ---- unit 2: step B (atomic recovery) and verify (contract 12) ------------------------------------
# Contract 15-4, proof version 2: A (the account's own rows; inputs in D or under the account
# lock), N (inflow into the account's identity spaces) and S (the global sequence) are the gate;
# G (the unchanged E-4 I1..I5) is a diagnostic only.
PROOF_VERSION = 2
A_CHECKS = ("I1a", "I2a", "I4a", "I5a", "I6_recovery", "I7_recovery", "completion_history", "recovery_result")
G_CHECKS = ("I1", "I2", "I3", "I4", "I5")
_PROOF_KEYS = {"version", "A", "N", "S", "G"}
# The pre-15-4 shape: nine flat checks. Never released as it is; an explicit verify replaces it.
LEGACY_CHECKS = ("I1", "I2", "I3", "I4", "I5", "I6_recovery", "I7_recovery", "completion_history",
                 "recovery_result")
_BLOCK_D_FIELDS = ("id", "user_id", "recovery_key", "grant_hash", "status", "active_user_id", "run_watermark",
                   "changes_started", "changes_started_at")
_RECORD_D_FIELDS = ("id", "user_id", "block_id", "recovery_key", "plan_fingerprint", "source_runs_json",
                    "baseline_json", "prepared_at", "applied_at")
_ACCOUNT_D_TABLES = ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs",
                     "srs_migration_snapshots", "srs_user_settings", "srs_card_deletions", "srs_card_identity_flags",
                     "srs_evidence_restarts", "srs_review_receipts")


def _checked_block_and_record(connection: Any, user_id: int, recovery_key: str, digest: str) -> tuple[dict, dict]:
    import hmac

    block = active_block(connection, user_id)
    record = active_recovery_record(connection, user_id)
    if (block is None or record is None or not block["consistent"] or not record["consistent"]
            or block["recovery_key"] != recovery_key or record["recovery_key"] != recovery_key
            or record["block_id"] != block["id"]):
        raise RecoveryRefused("recovery_state_inconsistent")
    if not hmac.compare_digest(block["grant_hash"], digest):
        raise RecoveryRefused("recovery_grant_invalid")
    return block, record


def recover(user_id: int, recovery_key: str, token: str, plan: str) -> dict:
    """Step B (contract 12-1). ONE connection, ONE transaction: the grant check under the
    account lock (which also records `changes_started` in this transaction), a fresh
    judgement, every source run rolled back card by card through the shared internal write,
    the success count, FSRS rows 0, the mode CAS to legacy and the record `applied` -- all
    committed together, or nothing (step A's block and `prepared` record stay). A re-call
    after the commit writes nothing again."""
    from app import account_write
    from app.account_write import AccountWriteError, RecoveryGrant

    _check_key(recovery_key)
    digest = token_hash(token)
    if not isinstance(plan, str) or not _PLAN.fullmatch(plan):
        raise RecoveryRefused("plan_required")
    grant = RecoveryGrant(user_id=user_id, recovery_key=recovery_key, action="rollback", token=token)
    with get_connection() as connection:
        try:
            # lock + grant check only; the progress mark is written below, by the first B only
            granted = account_write.authorize_recovery(connection, user_id, grant)
        except AccountWriteError as error:                 # no block / wrong grant
            raise RecoveryRefused(error.code) from None
        block, record = _checked_block_and_record(connection, user_id, recovery_key, digest)
        if record["plan_fingerprint"] != plan:
            raise RecoveryRefused("recovery_plan_mismatch")
        if record["state"] in ("applied", "verified"):
            # contract 13: a re-call of a finished B -- lock and grant checked, nothing written
            return {"status": record["state"], "created": False, "record_id": int(record["id"])}
        if record["state"] != "prepared":
            raise RecoveryRefused("recovery_state_inconsistent")
        sources = _stored_sources(connection, user_id, recovery_key, record)
        if sources is None:
            raise RecoveryRefused("recovery_record_invalid")
        at = now_utc()
        judged = assess(connection, user_id, recovery_key, at=at)
        report, material = judged["report"], judged["material"]
        if report["status"] != "ready":
            raise RecoveryRefused("recovery_blocked", report["reasons"])
        if report["plan"] != plan:
            raise RecoveryRefused("plan_changed")
        source_ids = {s["run_id"] for s in sources}
        if {t[0] for t in material["targets"]} != source_ids or not _baseline_ok(
                connection, user_id, record, source_ids, [[c[1], c[2], c[4]] for c in material["cards"]]):
            raise RecoveryRefused("recovery_record_invalid")
        # the first recovery write: recorded in THIS transaction (rolls back with it)
        account_write.record_recovery_change(connection, user_id, granted)
        rolled = deleted = total = 0
        for source in sorted(sources, key=lambda s: s["run_id"], reverse=True):     # newest conversion first
            rolled_now, deleted_now, total_now = _rollback_source(connection, user_id, source, at)
            rolled, deleted, total = rolled + rolled_now, deleted + deleted_now, total + total_now
        if rolled + deleted != total:                                               # contract 3-3
            raise RecoveryRefused("recovery_count_mismatch")
        if _fsrs_rows(connection, user_id):
            raise RecoveryRefused("fsrs_rows_remain")
        _switch_mode(connection, user_id, material["mode"], material["settings_version"], at)
        _mark_record(connection, record, "prepared", "applied", "applied_at", at)
        return {"status": "applied", "created": True, "record_id": int(record["id"]), "rolled_back": rolled,
                "deleted_proven": deleted, "warnings": report["warnings"]}


def _rollback_source(connection: Any, user_id: int, source: dict, at: datetime) -> tuple[int, int, int]:
    """One source run, strictly: every card `rollback` (written) or `deleted_proven` (nothing
    written, nothing restored); any other verdict raises and the caller's transaction rolls
    back. The deterministic rollback run must not exist yet."""
    run = dict(connection.execute("SELECT * FROM srs_migration_runs WHERE id = ?", (source["run_id"],)).fetchone())
    migration._require_window(run["started_at"], at, "rollback")
    if connection.execute("SELECT 1 FROM srs_migration_runs WHERE run_key = ?", (source["rollback_key"],)).fetchone():
        raise RecoveryRefused("rollback_key_exists")
    scope = migration._json({"user_id": user_id, "source_run_id": run["id"]})
    rollback_id = migration._run_id(connection, source["rollback_key"], "rollback", scope, at)
    results, rolled, deleted = [], 0, 0
    snapshots = [dict(r) for r in connection.execute(
        "SELECT * FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ? ORDER BY id",
        (run["id"], user_id)).fetchall()]
    for snapshot in snapshots:
        key = CardKey(snapshot["card_kind"], user_id, int(snapshot["card_ref"]))
        judged = migration.judge_rollback_card(connection, key, snapshot, run, for_update=True)
        if judged["verdict"] == "rollback":
            results.append(migration.write_card_rollback(connection, key, judged, rollback_id, at))
            rolled += 1
        elif judged["verdict"] == "missing" and _deletion_proven(connection, key, run["started_at"]):
            results.append({"kind": key.kind, "ref_id": key.ref_id, "result": "deleted_proven"})
            deleted += 1
        else:
            raise RecoveryRefused("card_changed", [judged["verdict"]])
    connection.execute("UPDATE srs_migration_runs SET status = 'completed', summary_json = ?, finished_at = ? "
                       "WHERE id = ?", (migration._json(results), at.isoformat(), rollback_id))
    connection.execute("UPDATE srs_migration_runs SET status = 'aborted' WHERE id = ? AND status = 'completed'",
                       (run["id"],))
    return rolled, deleted, len(snapshots)


def _fsrs_rows(connection: Any, user_id: int) -> int:
    return sum(int(connection.execute(f"SELECT count(*) AS n FROM {table} WHERE user_id = ? AND srs_engine = 'fsrs'",
                                      (user_id,)).fetchone()["n"]) for _kind, table, _ref in CARD_TABLES)


def _switch_mode(connection: Any, user_id: int, previous_mode: str, settings_version: int, at: datetime) -> None:
    """Exactly legacy, by compare-and-set on the mode and version the plan judged."""
    cursor = connection.execute(
        "UPDATE srs_user_settings SET srs_mode = 'legacy', settings_version = settings_version + 1, updated_at = ? "
        "WHERE user_id = ? AND srs_mode = ? AND settings_version = ?",
        (at.isoformat(), user_id, previous_mode, settings_version))
    if cursor.rowcount != 1:
        raise RecoveryRefused("mode_changed")


def _mark_record(connection: Any, record: dict, state_from: str, state_to: str, column: str, at: datetime,
                 extra: dict | None = None) -> None:
    sets = ["state = ?", f"{column} = ?"] + [f"{name} = ?" for name in (extra or {})]
    params = [state_to, at.isoformat(), *(extra or {}).values(), record["id"], state_from, record["user_id"]]
    cursor = connection.execute(f"UPDATE account_recovery_runs SET {', '.join(sets)} WHERE id = ? AND state = ? "
                                "AND active_user_id = ?", tuple(params))
    if cursor.rowcount != 1:
        raise RecoveryRefused("recovery_state_inconsistent")


def verification_digest(connection: Any, user_id: int, block_id: int, record_id: int) -> str:
    """Contract 4-3 field list D: the recovery data of the account, the block's progress fields
    and the record WITHOUT its state / verification / closing fields -- so saving `verified`
    leaves D unchanged while any change of recovery data changes it."""
    digest = hashlib.sha256()
    for table in _ACCOUNT_D_TABLES:
        digest.update(table.encode())
        digest.update(_rows_digest(connection, f"SELECT * FROM {table} WHERE user_id = ? ORDER BY 1",
                                   (user_id,)).encode())
    runs, _readable = _account_runs(connection, user_id)
    digest.update(_sha([[rid, {k: v for k, v in run.items() if k != "scope"}]
                        for rid, run in sorted(runs.items())]).encode())
    block = connection.execute(f"SELECT {', '.join(_BLOCK_D_FIELDS)} FROM account_write_blocks WHERE id = ?",
                               (block_id,)).fetchone()
    record = connection.execute(f"SELECT {', '.join(_RECORD_D_FIELDS)} FROM account_recovery_runs WHERE id = ?",
                                (record_id,)).fetchone()
    digest.update(_canonical([dict(block) if block else None, dict(record) if record else None]).encode())
    return digest.hexdigest()


def _checks(connection: Any, user_id: int, record: dict, sources: list[dict], *, diagnostics: bool = True) -> dict:
    """Contract 15-4 (proof version 2): {version, A: {8 checks}, N, S, G}. Each check is
    {status: pass|fail|unknown|not_evaluated, ...counts}. G needs the read-only snapshot, so the
    locked re-check (`diagnostics=False`) leaves it out (None)."""
    from app.srs import recovery_scope

    base = json.loads(record["baseline_json"])
    checks = dict(recovery_scope.account(connection, user_id))
    count, log_digest, _days = _log_state(connection, user_id)
    checks["I6_recovery"] = {"status": "pass" if [count, log_digest] == [base["logs"]["count"], base["logs"]["digest"]]
                             else "fail", "logs": count}
    days = [date.fromisoformat(d) for d in base["days"]]
    checks["I7_recovery"] = {"status": "pass" if _metrics_digest(connection, user_id, days) == base["metrics_digest"]
                             else "fail", "days": len(days)}
    checks["completion_history"] = {"status": "pass" if _preserved_digest(connection, user_id, base["cards"])
                                    == base["preserved"]["digest"] else "fail", "cards": len(base["cards"])}
    runs, _readable = _account_runs(connection, user_id)
    by_key = {run["run_key"]: run for run in runs.values() if run["mode"] == "rollback"}
    ok = _fsrs_rows(connection, user_id) == 0
    setting = connection.execute("SELECT srs_mode FROM srs_user_settings WHERE user_id = ?", (user_id,)).fetchone()
    ok = ok and setting is not None and setting["srs_mode"] == "legacy"
    for source in sources:
        rollback = by_key.get(source["rollback_key"])
        results = _rollback_results(rollback) if rollback else None
        ok = (ok and runs.get(source["run_id"], {}).get("status") == "aborted" and rollback is not None
              and rollback["status"] == "completed" and rollback["scope"].get("source_run_id") == source["run_id"]
              and bool(results) and all(isinstance(r, dict) and r.get("result") in PROVEN_RESULTS for r in results)
              and _rollback_proven(connection, user_id, source["run_id"], rollback, results))
    checks["recovery_result"] = {"status": "pass" if ok else "fail"}
    return {"version": PROOF_VERSION, "A": checks, "N": recovery_scope.inflow(connection, user_id),
            "S": recovery_scope.sequence(connection),
            "G": recovery_scope.diagnostics(connection) if diagnostics else None}


def _between_read_and_save() -> None:
    """Test seam only: nothing happens here."""


def _current_proof(connection: Any, user_id: int, recovery_key: str, block: dict, record: dict) -> tuple:
    """(sources, checks, D) of the CURRENT data for an `applied` or `verified` record, or
    RecoveryRefused when the stored combination is not one of those (contract 11 / 13)."""
    sources = _stored_sources(connection, user_id, recovery_key, record)
    source_ids = {s["run_id"] for s in sources} if sources else set()
    runs, _readable = _account_runs(connection, user_id)
    keys = {run["run_key"]: run for run in runs.values() if run["mode"] == "rollback"}
    # a `verified` record of the old proof shape is re-verifiable (step `verify`), never released
    expected = {"applied": ("verify",), "verified": ("await_release", "verify")}.get(record["state"])
    if (sources is None or expected is None or not _baseline_ok(connection, user_id, record, source_ids, None)
            or _state_step(record, block, [runs.get(s["run_id"], {}).get("status") for s in sources],
                           [keys.get(s["rollback_key"], {}).get("status") for s in sources]) not in expected):
        raise RecoveryRefused("recovery_state_inconsistent")
    return sources, _checks(connection, user_id, record, sources), verification_digest(
        connection, user_id, block["id"], record["id"])


def _passed(check: Any) -> bool:
    return isinstance(check, dict) and check.get("status") == "pass"


def gate_pass(checks: Any) -> bool:
    """The release gate (contract 15-4): exactly the eight A checks, and N and S -- all `pass`.
    G is not part of it."""
    return (isinstance(checks, dict) and isinstance(checks.get("A"), dict) and set(checks["A"]) == set(A_CHECKS)
            and all(_passed(checks["A"][name]) for name in A_CHECKS)
            and _passed(checks.get("N")) and _passed(checks.get("S")))


def proof_ok(value: Any) -> bool:
    """THE stored-proof rule of version 2, shared by verify, resume and release: exactly the five
    keys, version the integer 2, the gate passed, G holding I1..I5 each with a readable status."""
    return (isinstance(value, dict) and set(value) == _PROOF_KEYS
            and type(value["version"]) is int and value["version"] == PROOF_VERSION and gate_pass(value)
            and isinstance(value["G"], dict) and set(value["G"]) == set(G_CHECKS)
            and all(isinstance(value["G"][name], dict) and value["G"][name].get("status") in ("pass", "fail", "unknown")
                    for name in G_CHECKS))


def legacy_proof(value: Any) -> bool:
    """A pre-15-4 `verified` proof: the nine flat checks, all `pass`."""
    return (isinstance(value, dict) and set(value) == set(LEGACY_CHECKS)
            and all(_passed(value[name]) for name in LEGACY_CHECKS))


def _statuses(checks: dict) -> tuple[dict, dict]:
    """(the gate's statuses, flat: the A checks, N, S; the G statuses) for the operator output."""
    gate = {name: (checks.get("A") or {}).get(name, {}).get("status") for name in A_CHECKS}
    gate.update(N=(checks.get("N") or {}).get("status"), S=(checks.get("S") or {}).get("status"))
    return gate, {name: (checks.get("G") or {}).get(name, {}).get("status") for name in G_CHECKS}


def verify(user_id: int, recovery_key: str, token: str) -> dict:
    """Contracts 12-3 and 13. Always checks the CURRENT data (also when already `verified`):
    every required check and D in a read-only snapshot R. Then:
    - a check missing / not `pass`: `not_verified`, nothing written (a stored proof is a past
      record only);
    - `verified` and the same D and checks: nothing written, the stored proof is returned;
    - otherwise, in a separate transaction under the account lock, D is recomputed and must be
      the same as in R: `applied -> verified`, or the `verified` proof refreshed (compare-and-
      set on the stored digest). The baseline is never rewritten; the state never goes back."""
    from app.srs.invariant_audit import read_snapshot

    _check_key(recovery_key)
    digest = token_hash(token)
    with get_connection() as connection:
        with read_snapshot(connection):
            block, record = _checked_block_and_record(connection, user_id, recovery_key, digest)
            _sources, checks, read_digest = _current_proof(connection, user_id, recovery_key, block, record)
    statuses, diagnostics = _statuses(checks)
    if not gate_pass(checks):
        return {"status": "not_verified", "checks": statuses, "diagnostics": diagnostics,
                "stored_state": record["state"]}
    if (record["state"] == "verified" and read_digest == record["verified_digest"]
            and _canonical(checks) == record["verification_json"]):
        return {"status": "verified", "created": False, "record_id": int(record["id"]), "checks": statuses,
                "diagnostics": diagnostics}
    _between_read_and_save()
    with get_connection() as connection:
        lock_account(connection, user_id)
        block, current = _checked_block_and_record(connection, user_id, recovery_key, digest)
        if (current["id"] != record["id"] or any(current[name] != record[name] for name in _PROOF_FIELDS)
                or verification_digest(connection, user_id, block["id"], current["id"]) != read_digest):
            raise RecoveryRefused("verification_stale")
        # contract 15-4: the gate again under the lock (N and S are not covered by D)
        sources = _stored_sources(connection, user_id, recovery_key, current)
        if sources is None or not gate_pass(_checks(connection, user_id, current, sources, diagnostics=False)):
            raise RecoveryRefused("verification_stale")
        at = now_utc()
        if record["state"] == "applied":
            _mark_record(connection, current, "applied", "verified", "verified_at", at,
                         {"verification_json": _canonical(checks), "verified_digest": read_digest})
        else:
            cursor = connection.execute(
                "UPDATE account_recovery_runs SET verification_json = ?, verified_digest = ?, verified_at = ? "
                "WHERE id = ? AND state = 'verified' AND active_user_id = ? AND verified_digest = ? "
                "AND verification_json = ?",
                (_canonical(checks), read_digest, at.isoformat(), current["id"], user_id, record["verified_digest"],
                 record["verification_json"]))
            if cursor.rowcount != 1:
                raise RecoveryRefused("verification_stale")
    return {"status": "verified", "created": True, "refreshed": record["state"] == "verified",
            "record_id": int(record["id"]), "checks": statuses, "diagnostics": diagnostics}


# ---- completed release (tool contract 14) -------------------------------------------------------
def completed_release_replay(user_id: int, recovery_key: str, digest: str, plan: Any) -> dict | None:
    """Read only. A re-call of a FINISHED completed release: the released block of this key
    and token, and its record closed `completed` with the same plan -> the stored result,
    nothing written, nothing re-verified (ordinary writes may have changed the data since).
    None when no finished release of this key exists; refusal on a conflicting input."""
    from app.srs.invariant_audit import read_snapshot

    with get_connection() as connection:
        with read_snapshot(connection):
            return finished_release(connection, user_id, recovery_key, digest, plan)


def finished_release(connection: Any, user_id: int, recovery_key: str, digest: str, plan: Any) -> dict | None:
    """On the caller's connection (the read-only snapshot above, or the release's own locked
    transaction): the stored result of a finished completed release of this key, None when
    there is none, a refusal when the token / record / plan do not match. Reads only."""
    import hmac

    block = connection.execute("SELECT * FROM account_write_blocks WHERE recovery_key = ? AND user_id = ? "
                               "AND status = 'released'", (recovery_key, user_id)).fetchone()
    if block is None or block["release_reason"] != "completed":
        return None
    if not hmac.compare_digest(block["grant_hash"], digest):
        raise RecoveryRefused("recovery_grant_invalid")
    record = connection.execute("SELECT * FROM account_recovery_runs WHERE recovery_key = ? AND user_id = ? "
                                "AND block_id = ?", (recovery_key, user_id, block["id"])).fetchone()
    if record is None or record["state"] != "closed" or record["close_reason"] != "completed":
        raise RecoveryRefused("recovery_state_inconsistent")
    if plan != record["plan_fingerprint"]:
        raise RecoveryRefused("recovery_plan_mismatch")
    return {"block_id": int(block["id"]), "released": True, "reason": "completed", "created": False,
            "recovery_record_closed": True}


def completed_release_proof(user_id: int, recovery_key: str, digest: str, plan: Any) -> dict:
    """Read-only snapshot R: a `verified` record of this block / key / token / plan whose CURRENT
    data passes every required check and still has the stored digest D. Returns what the
    locked confirmation needs. Refuses otherwise (a stale proof: `verification_not_current`)."""
    from app.srs.invariant_audit import read_snapshot

    if not isinstance(plan, str) or not _PLAN.fullmatch(plan):
        raise RecoveryRefused("release_not_allowed")         # no plan: the old completed request stays refused
    with get_connection() as connection:
        with read_snapshot(connection):
            block, record = _checked_block_and_record(connection, user_id, recovery_key, digest)
            if record["plan_fingerprint"] != plan:
                raise RecoveryRefused("recovery_plan_mismatch")
            if record["state"] != "verified":
                raise RecoveryRefused("release_not_allowed")
            try:
                _sources, checks, current = _current_proof(connection, user_id, recovery_key, block, record)
            except RecoveryRefused:
                raise RecoveryRefused("release_not_allowed") from None
            if not _stored_proof_ok(record):
                raise RecoveryRefused("verification_not_current")     # an old-shape proof: verify first
            if not gate_pass(checks):
                raise RecoveryRefused("release_not_allowed")
            if current != record["verified_digest"]:
                raise RecoveryRefused("verification_not_current")     # verify first, explicitly
            # the stored proof as read here: the locked transaction compares it field by field
            return {"block_id": int(block["id"]), "record_id": int(record["id"]), "digest": current,
                    "stored": {name: record[name] for name in _PROOF_FIELDS},
                    "diagnostics": _statuses(checks)[1]}


# The verification control fields D leaves out (contract 4-3): compared on their own under the
# lock -- state, the stored checks, the stored digest and the three times of the record.
_PROOF_FIELDS = ("state", "verification_json", "verified_digest", "prepared_at", "applied_at", "verified_at")


def _stored_proof_ok(record: dict) -> bool:
    try:
        checks = json.loads(record["verification_json"]) if isinstance(record["verification_json"], str) else None
    except ValueError:
        return False
    prepared, applied, verified = (_instant(record["prepared_at"]), _instant(record["applied_at"]),
                                   _instant(record["verified_at"]))
    return (proof_ok(checks) and prepared is not None and applied is not None
            and verified is not None and prepared <= applied <= verified
            and isinstance(record["verified_digest"], str) and bool(_HEX64.fullmatch(record["verified_digest"])))


def completed_release_confirm(connection: Any, user_id: int, block: dict, record: dict | None, proof: dict) -> bool:
    """Under the account lock, in the release transaction: the same block and record, still
    `verified`; the stored proof (every control field D leaves out) exactly as R read it and
    still a version-2 pass; the current D equal to the stored digest; no FSRS row; legacy mode;
    and A, N and S computed again here (contract 15-4: R's result is not trusted)."""
    if record is None or not record["consistent"] or proof is None:
        return False
    if (record["id"] != proof["record_id"] or block["id"] != proof["block_id"] or record["block_id"] != block["id"]
            or record["state"] != "verified" or record["verified_digest"] != proof["digest"]):
        return False
    if any(record[name] != proof["stored"][name] for name in _PROOF_FIELDS) or not _stored_proof_ok(record):
        return False
    if verification_digest(connection, user_id, block["id"], record["id"]) != proof["digest"]:
        return False
    setting = connection.execute("SELECT srs_mode FROM srs_user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if _fsrs_rows(connection, user_id) != 0 or setting is None or setting["srs_mode"] != "legacy":
        return False
    sources = _stored_sources(connection, user_id, record["recovery_key"], record)
    return sources is not None and gate_pass(_checks(connection, user_id, record, sources, diagnostics=False))
