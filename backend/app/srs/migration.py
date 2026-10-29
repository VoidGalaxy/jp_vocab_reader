"""Explicit, resumable SRS migration. No startup calls or automatic enablement.

Incomplete legacy histories remain legacy until initialization is approved.
Dry runs are read-only; apply/rollback require their caller's explicit scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Sequence

from app.database import compute_review_schedule, get_connection, is_postgres_connection, now_utc
from app.srs.completion import COMPLETION_HISTORY_COLUMNS, ReviewEvent, replay_with_completion
from app.srs.goals import read_utc
from app.srs.history_intro import INTRO_COLUMNS, record_intro
from app.srs.identity import is_identity_unknown
from app.srs.engine import (
    DEFAULT_CONFIG, PINNED_LIBRARY_VERSION, RATINGS, CardKey, SrsEngineError,
    review, state_from_json, state_to_json, to_utc,
)
from app.srs.readability import history_unreadable
from app.srs.reviews import ensure_config
from app.srs.storage import (
    SrsWriteError, begin_card_write, card_fingerprint, load_card, load_logs, load_state,
    state_columns, update_card,
)


# Columns a rollback must never restore from a snapshot, whatever their name.
ROLLBACK_PRESERVED = INTRO_COLUMNS + ("evidence_from_log_id",) + COMPLETION_HISTORY_COLUMNS


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True)
class MigrationCandidate:
    key: CardKey
    card_fingerprint: str | None
    logs_fingerprint: str
    card_version: int | None
    quality: str
    flags: tuple[str, ...]
    values_json: str | None
    last_log_id: int
    # Gate D-2 U8: how a previously converted, rolled-back card is re-converted
    # ("restored", "state_none" or "state_none_restart"); None for a first conversion.
    reconversion: str | None = None
    # Gate D-2 U8 plan B: {"previous_boundary", "rollback_record_id"} written into the
    # re-conversion snapshot; it is the only permission for the card's first review to
    # start a new evidence window (reviews / restoration.restart_permission).
    restart_json: str | None = None


# LQ1 (OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN 10-1 / 11-1): the WRITE path's access check on PostgreSQL locks one
# valid access path until the card commits, as the review path does. Lock waits for THIS statement only are
# capped (never relaxed); its lock timeout / deadlock get fixed codes, any other error passes unchanged.
ACCESS_LOCK_TIMEOUT_MS = 5000
ACCESS_LOCK_ERRORS = {"55P03": "migration_access_lock_timeout", "40P01": "migration_access_deadlock"}


def _locked_access(connection: Any, key: CardKey) -> bool:
    setting = connection.execute(
        "SELECT current_setting('lock_timeout') AS previous, "
        "(SELECT setting FROM pg_catalog.pg_settings WHERE name = 'lock_timeout') AS setting_ms"
    ).fetchone()
    milliseconds = int(setting["setting_ms"])
    tighten = milliseconds == 0 or milliseconds > ACCESS_LOCK_TIMEOUT_MS
    if tighten:   # transaction-local: a failed statement leaves it to the rollback, no restore SQL is sent
        connection.execute("SELECT pg_catalog.set_config('lock_timeout', ?, true)", (f"{ACCESS_LOCK_TIMEOUT_MS}ms",))
    try:
        row = connection.execute(
            "SELECT subscriptions.id AS subscription_id, words.id AS word_id "
            "FROM user_deck_subscriptions AS subscriptions "
            "JOIN shared_deck_words AS words ON words.shared_deck_id = subscriptions.shared_deck_id "
            "WHERE subscriptions.user_id = ? AND subscriptions.is_active = TRUE AND words.lexeme_id = ? "
            "ORDER BY subscriptions.id, words.id LIMIT 1 FOR SHARE OF subscriptions, words",
            (key.user_id, key.ref_id),
        ).fetchone()
    except Exception as error:
        code = ACCESS_LOCK_ERRORS.get(getattr(error, "sqlstate", None))
        if code is None:
            raise
        raise SrsWriteError(code) from None
    if tighten:
        connection.execute("SELECT pg_catalog.set_config('lock_timeout', ?, true)", (setting["previous"],))
    return row is not None


def _authorized(connection: Any, key: CardKey, *, lock: bool = False) -> bool:
    if key.kind == "personal":
        return load_card(connection, key) is not None
    if lock and is_postgres_connection(connection):
        return _locked_access(connection, key)
    row = connection.execute(
        "SELECT words.lexeme_id FROM shared_deck_words AS words "
        "JOIN user_deck_subscriptions AS subscriptions ON subscriptions.shared_deck_id = words.shared_deck_id "
        "WHERE subscriptions.user_id = ? AND subscriptions.is_active = TRUE AND words.lexeme_id = ? LIMIT 1",
        (key.user_id, key.ref_id),
    ).fetchone()
    return row is not None


def _history(card: dict[str, Any], logs: list[dict[str, Any]], key: CardKey) -> tuple[str, tuple[str, ...], list[ReviewEvent]]:
    flags: list[str] = []
    events: list[ReviewEvent] = []
    if not logs:
        if card["last_reviewed_at"] is None and card["correct_count"] == card["wrong_count"] == 0:
            return "fresh", (), []
        return "incomplete", ("missing_history",), []
    count = card["correct_count"] + card["wrong_count"]
    if count != len(logs):
        flags.append("counter_log_mismatch")
    if card["correct_count"] != sum(log["rating"] in ("hard", "good", "easy") for log in logs):
        flags.append("rating_counter_mismatch")
    previous_level, previous_due = 0, None
    engine_state, last_recorded_due = None, None
    next_level = "next_review_level" if key.kind == "personal" else "new_review_level"
    next_due = "next_review_at" if key.kind == "personal" else "new_next_review_at"
    try:
        ordered = sorted(logs, key=lambda log: (to_utc(datetime.fromisoformat(log["event_at"])), log["id"]))
        for log in ordered:
            at = to_utc(datetime.fromisoformat(log["event_at"]))
            if log["rating"] not in RATINGS:
                flags.append("invalid_rating")
                break
            if events:
                gap = (at - events[-1].reviewed_at).total_seconds()
                if gap == 0:
                    flags.append("ambiguous_same_time")
                if gap < 60 and log["rating"] == events[-1].rating:
                    flags.append("short_interval_repeat")
            outcome = review(key, engine_state, log["rating"], at)
            allowed_previous_dues = (previous_due, last_recorded_due) if log["srs_engine"] == "fsrs" else (previous_due,)
            if log["previous_review_level"] != previous_level or log["previous_next_review_at"] not in allowed_previous_dues:
                flags.append("broken_log_chain")
            expected_level, expected_due = compute_review_schedule(log["rating"], previous_level, at)
            if log["srs_engine"] == "fsrs":
                # A rollback retains FSRS logs. Verify their full engine
                # snapshots while independently rebuilding the legacy projection.
                if (log["srs_config_version"] != DEFAULT_CONFIG.config_version
                        or state_from_json(log["srs_before_json"]) != engine_state
                        or state_from_json(log["srs_after_json"]) != outcome.after
                        or log[next_due] != outcome.after.due_at.isoformat()):
                    flags.append("fsrs_snapshot_mismatch")
            elif log[next_due] != expected_due:
                flags.append("legacy_projection_mismatch")
            if log[next_level] != expected_level:
                flags.append("legacy_projection_mismatch")
            events.append(ReviewEvent(at, log["rating"]))
            previous_level, previous_due = expected_level, expected_due
            last_recorded_due, engine_state = log[next_due], outcome.after
        if events and (to_utc(datetime.fromisoformat(card["last_reviewed_at"])) != events[-1].reviewed_at
                       or card["review_level"] != previous_level or card["next_review_at"] != previous_due):
            flags.append("card_log_mismatch")
    except (TypeError, ValueError):
        flags.append("invalid_history_time")
    blocking = set(flags) - {"short_interval_repeat"}
    return ("incomplete" if blocking else "complete"), tuple(sorted(set(flags))), events


def _card_print(card: dict[str, Any]) -> str:
    # The past-learning mark is written by apply itself (U4), so it is not part of
    # the preview/apply conflict comparison (nor of the U8 rollback baseline).
    # U11 B: the completion history columns are left out too, so a fingerprint taken
    # before they existed (rollback baseline, run scope) still matches an unchanged card.
    return card_fingerprint({k: v for k, v in card.items() if k not in INTRO_COLUMNS + COMPLETION_HISTORY_COLUMNS})


def inspect_card(connection: Any, key: CardKey, *, for_update: bool = False) -> MigrationCandidate:
    card = load_card(connection, key, for_update=for_update)
    logs = load_logs(connection, key)
    common = dict(key=key, card_fingerprint=_card_print(card) if card else None,
                  logs_fingerprint=_digest(logs), card_version=card["srs_card_version"] if card else None,
                  last_log_id=max((log["id"] for log in logs), default=0))
    if card is None or not _authorized(connection, key, lock=for_update):
        return MigrationCandidate(**common, quality="unavailable", flags=("card_or_access_missing",), values_json=None)
    if card["srs_engine"] != "legacy":
        return MigrationCandidate(**common, quality="already_fsrs", flags=(), values_json=None)
    if is_identity_unknown(connection, key.user_id, key.kind, key.ref_id):
        # Gate D-2 U3: stored history may belong to another card with this id.
        return MigrationCandidate(**common, quality="identity_unknown", flags=("identity_unknown",), values_json=None)
    if _was_converted(connection, key):
        # Gate D-2 U8: a card that was converted and rolled back is re-converted only
        # by the rollback's own record, never by a fresh replay of its history.
        return _reconvert_candidate(connection, key, card, logs, common)
    quality, flags, events = _history(card, logs, key)
    if quality == "incomplete":
        return _incomplete_candidate(card, common, flags)
    steps = replay_with_completion(key, events)
    state = steps[-1].outcome.after if steps else None
    values = state_columns(state)
    values.update(srs_engine="fsrs", srs_config_version=DEFAULT_CONFIG.config_version,
                  srs_effective_due_at=card["next_review_at"],
                  srs_participation="paused" if card["status"] == "known" else "active",
                  srs_pause_reason="legacy_known" if card["status"] == "known" else None,
                  srs_history_quality=quality, srs_history_flags=_json(flags))
    # Legacy scheduling fields, status and counters are not in this write. Gate D-2 U11:
    # neither are completion values -- a conversion never creates a completion from
    # replayed legacy history; the card's existing completion history stays as it is.
    return MigrationCandidate(**common, quality=quality, flags=flags, values_json=_json(values))


# Gate D-2 U5: incomplete-history flags whose cards may be converted (history gaps,
# unknown order, card values that disagree with the logs). Anything else keeps the
# card blocked: an unreadable log time (D-H6), an invalid rating or a mismatching
# FSRS snapshot have no approved handling yet. short_interval_repeat alone never
# makes a card incomplete (it is a suspicion marker only).
CONVERTIBLE_INCOMPLETE_FLAGS = frozenset({
    "missing_history", "broken_log_chain", "counter_log_mismatch", "rating_counter_mismatch",
    "ambiguous_same_time", "card_log_mismatch", "legacy_projection_mismatch", "short_interval_repeat",
    "changed_since_rollback", "evidence_restart",
})


def _incomplete_candidate(card: dict[str, Any], common: dict[str, Any], flags: tuple[str, ...]) -> MigrationCandidate:
    """Gate D-2 U5 (D-H1): an incomplete card is converted with NO engine state.

    - engine fields (phase, step, stability, difficulty, due, last review): NULL --
      no value is derived from legacy levels, logs or elapsed time;
    - srs_effective_due_at = the card's existing next_review_at, verbatim (the
      first schedule stays the one the learner already has). A missing or
      unreadable schedule blocks the card instead of being filled with "now";
    - quality 'incomplete' with its flags; known -> paused (approval 3);
    - not written: next_review_at, review_level, status, counters,
      last_reviewed_at, logs, ids, and the completion fields (no new completion
      evidence; an existing first completion record is kept as it is).
    The card's past-learning mark (U4) is recorded by apply_plan, not here."""
    blocking = tuple(flag for flag in flags if flag not in CONVERTIBLE_INCOMPLETE_FLAGS)
    if blocking:
        return MigrationCandidate(**common, quality="incomplete", flags=flags, values_json=None)
    raw_due = card["next_review_at"]
    if raw_due is None:
        return MigrationCandidate(**common, quality="incomplete", flags=flags + ("schedule_missing",), values_json=None)
    if read_utc(raw_due) is None:
        return MigrationCandidate(**common, quality="incomplete", flags=flags + ("schedule_unreadable",), values_json=None)
    values = state_columns(None)
    known = card["status"] == "known"
    values.update(srs_engine="fsrs", srs_config_version=DEFAULT_CONFIG.config_version,
                  srs_effective_due_at=raw_due,
                  srs_participation="paused" if known else "active",
                  srs_pause_reason="legacy_known" if known else None,
                  srs_history_quality="incomplete", srs_history_flags=_json(flags))
    return MigrationCandidate(**common, quality="incomplete", flags=flags, values_json=_json(values))


# --- Gate D-2 U8: re-conversion after rollback --------------------------------
#
# A rollback records, per rolled-back card (one srs_migration_snapshots row under the
# rollback run, in the rollback's transaction):
#   srs_before_json  the card's last FSRS projection just before the rollback (every
#                    srs_* column except the CAS version and ROLLBACK_PRESERVED);
#   legacy_json      {"card": the card just after the rollback,
#                     "baseline": {card_version, card_fingerprint, logs_fingerprint,
#                                  last_log_id}} -- the comparison point.
# Re-conversion restores srs_before_json only when the card, its logs and the engine
# config are exactly as the rollback left them. A card that changed since then gets
# no engine state (U5 rules, no replay). Without a readable record nothing is
# written: the fallback for a missing/expired/damaged record is not approved.

RESTORE_REQUIRED = ("srs_engine", "srs_config_version", "srs_state", "srs_step", "srs_stability",
                    "srs_difficulty", "srs_due_at", "srs_last_review_at", "srs_effective_due_at",
                    "srs_participation", "srs_pause_reason", "srs_history_quality", "srs_history_flags")
BASELINE_KEYS = ("card_version", "card_fingerprint", "logs_fingerprint", "last_log_id")

# --- Gate D-2 U10-a: snapshot record format 2 ----------------------------------
# Records name the card fields they keep instead of copying the card row (format 1,
# still read). No surface, reading, meaning, example, context, deck or source text.
# Fingerprints stay computed from the full card row, as before.
SNAPSHOT_FORMAT = 2
_ROLLBACK_INPUT = ("review_level", "next_review_at", "completion_metric_version", "first_completed_at")
APPLY_CARD_FIELDS = {
    # id / created_at: personal id reference and identity scan (identity.py);
    # srs_card_version + srs_engine: version-gap proof (restoration.proven_jump);
    # the rest: what rollback_plan restores and recomputes from.
    "personal": ("id", "created_at", "srs_card_version") + _ROLLBACK_INPUT + RESTORE_REQUIRED,
    "lexeme": ("id", "lexeme_id", "created_at", "srs_card_version") + _ROLLBACK_INPUT + RESTORE_REQUIRED,
}
ROLLBACK_CARD_FIELDS = {"personal": ("id", "created_at"), "lexeme": ("id", "lexeme_id", "created_at")}

# --- Gate D-2 U10-e: an apply record after its run's rollback window (format 3) -------
# Only what outlives rollback stays: identity (id / lexeme_id / created_at) and the
# version-gap proof inputs (srs_card_version, srs_engine), plus last_log_id / restart.
# The rollback-only values (U10_CONTRACT 9-3 / 12-2, an explicit list) are removed.
PRUNED_FORMAT = 3
PRUNED_APPLY_CARD_FIELDS = {
    "personal": ("id", "created_at", "srs_card_version", "srs_engine"),
    "lexeme": ("id", "lexeme_id", "created_at", "srs_card_version", "srs_engine"),
}
PRUNED_AWAY = _ROLLBACK_INPUT + tuple(name for name in RESTORE_REQUIRED if name != "srs_engine")
assert all(set(APPLY_CARD_FIELDS[k]) == set(PRUNED_APPLY_CARD_FIELDS[k]) | set(PRUNED_AWAY) for k in APPLY_CARD_FIELDS)
# A run's scope_json after the window: the request is kept as a hash of the original text.
PRUNED_SCOPE_FORMAT = 2
_SCOPE_CARD_KEYS = frozenset({"kind", "ref_id", "card", "logs", "version", "quality", "values", "flags", "last_log_id"})


def _kept(card: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """Only fields the card really has (no invented ids)."""
    return {name: card[name] for name in fields if name in card}


_CARD_TABLES = {"personal": "vocab_items", "lexeme": "user_word_progress"}
_TOP_LEVEL = {"apply": ({"card", "last_log_id"}, {"restart"}), "rollback": ({"card", "baseline"}, set())}
_RESTART_KEYS = frozenset({"previous_boundary", "rollback_record_id"})
_APPLY_VALUE_KEYS = frozenset(RESTORE_REQUIRED) | {"completion_metric_version", "first_completed_at"}
_ROLLBACK_VALUE_KEYS = frozenset(RESTORE_REQUIRED) | frozenset(_ROLLBACK_INPUT)


def _card_columns(connection: Any, kind: str) -> frozenset[str]:
    """The card table's columns: a format-1 record's card was a copy of one row."""
    cursor = connection.execute(f"SELECT * FROM {_CARD_TABLES[kind]} LIMIT 0")
    return frozenset(column[0] for column in cursor.description)


def _count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _instant(value: Any) -> bool:
    """A real time-zoned instant (Z, +hh:mm and -hh:mm spellings all accepted)."""
    return isinstance(value, str) and read_utc(value) is not None


_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


def _token(value: Any) -> bool:
    """An identifier-like value (config / metric version, pause reason): no free text."""
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _finite(value: Any) -> bool:
    """A real number the engine can hold (a float). Booleans, text, NaN and infinities
    fail; so does an integer too large for a float (U10-b fix: math.isfinite raises
    OverflowError on it). Nothing is converted, cut or defaulted."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def _fingerprint(value: Any) -> bool:
    """Exactly what card_fingerprint / _digest write: SHA-256 hexdigest, 64 lowercase
    hex characters. Nothing is hashed, cut or case-folded to make a value fit."""
    return isinstance(value, str) and _FINGERPRINT.fullmatch(value) is not None


def _flags_text(value: Any) -> bool:
    try:
        parsed = json.loads(value) if isinstance(value, str) else None
    except (ValueError, RecursionError):
        return False
    return isinstance(parsed, list) and all(_token(item) for item in parsed)


# Gate D-2 U10 review fix (remaining P2): the value contract of every field a record
# keeps -- scalar types, ranges, real instants, allowed values. An object or a list
# (or free text) where a scalar belongs makes the record unsupported. Engine meaning
# (legacy before conversion, fsrs in results) is checked per column by the callers.
_FIELD_OK = {
    "id": lambda v: _count(v) and v > 0,
    "lexeme_id": lambda v: _count(v) and v > 0,
    "created_at": _instant,
    "srs_card_version": _count,
    "review_level": _count,
    "next_review_at": lambda v: v is None or _instant(v),
    "completion_metric_version": lambda v: v is None or _token(v),
    "first_completed_at": lambda v: v is None or _instant(v),
    "srs_engine": lambda v: v in ("legacy", "fsrs"),
    "srs_config_version": lambda v: v is None or _token(v),
    "srs_state": lambda v: v is None or (_count(v) and v in (1, 2, 3)),
    "srs_step": lambda v: v is None or _count(v),
    "srs_stability": lambda v: v is None or _finite(v),
    "srs_difficulty": lambda v: v is None or _finite(v),
    "srs_due_at": lambda v: v is None or _instant(v),
    "srs_last_review_at": lambda v: v is None or _instant(v),
    "srs_effective_due_at": lambda v: v is None or _instant(v),
    "srs_participation": lambda v: v in (None, "active", "paused"),
    "srs_pause_reason": lambda v: v is None or _token(v),
    "srs_history_quality": lambda v: v in (None, "complete", "incomplete", "fresh"),
    "srs_history_flags": lambda v: v is None or _flags_text(v),
}


def _fields_ok(values: dict[str, Any], engine: str | None = None) -> bool:
    """Every value has its field's shape; with `engine`, srs_engine must be it."""
    if engine is not None and values.get("srs_engine", engine) != engine:
        return False
    return all(name in _FIELD_OK and _FIELD_OK[name](value) for name, value in values.items())


def _record_shape(mode: str, kind: str, card_ref: int, payload: Any, columns: frozenset[str]) -> dict[str, Any] | None:
    """Gate D-2 U10 fix P2: the whole record judged by type. Returns the format-2
    payload rebuilt from allowed fields only (values kept exactly), or None when
    anything is unsupported: unknown format, unknown top-level key, a card key that
    neither the card table (format 1) nor the format-2 list allows, a card that names
    another card, or a malformed last_log_id / restart / baseline."""
    if not isinstance(payload, dict):
        return None
    if "format" in payload and payload["format"] == PRUNED_FORMAT and not isinstance(payload["format"], bool):
        return _pruned_shape(mode, kind, card_ref, payload)
    if "format" in payload:
        if payload["format"] != SNAPSHOT_FORMAT or isinstance(payload["format"], bool):
            return None
        allowed_card = set((APPLY_CARD_FIELDS if mode == "apply" else ROLLBACK_CARD_FIELDS)[kind])
    else:
        allowed_card = set(columns)
    required, optional = _TOP_LEVEL[mode]
    if not required <= set(payload) or set(payload) - required - optional - {"format"}:
        return None
    card = payload["card"]
    if not isinstance(card, dict) or not set(card) <= allowed_card:
        return None
    identity_key = "id" if kind == "personal" else "lexeme_id"
    if card.get(identity_key) != card_ref or isinstance(card.get(identity_key), bool):
        return None
    fields = (APPLY_CARD_FIELDS if mode == "apply" else ROLLBACK_CARD_FIELDS)[kind]
    rebuilt: dict[str, Any] = {"format": SNAPSHOT_FORMAT, "card": _kept(card, fields)}
    if not _fields_ok(rebuilt["card"], "legacy" if mode == "apply" else None):
        return None  # a kept value of the wrong shape (an object, a list, free text ...)
    if mode == "apply":
        if not _count(payload["last_log_id"]):
            return None
        rebuilt["last_log_id"] = payload["last_log_id"]
        if "restart" in payload:
            if not _restart_ok(payload["restart"]):
                return None
            rebuilt["restart"] = {name: payload["restart"][name] for name in sorted(_RESTART_KEYS)}
    else:
        baseline = payload["baseline"]
        if (not isinstance(baseline, dict) or set(baseline) != set(BASELINE_KEYS)
                or not _count(baseline["card_version"]) or not _count(baseline["last_log_id"])
                or not all(_fingerprint(baseline[name]) for name in ("card_fingerprint", "logs_fingerprint"))):
            return None
        rebuilt["baseline"] = {name: baseline[name] for name in BASELINE_KEYS}
    return rebuilt


def _restart_ok(restart: Any) -> bool:
    return isinstance(restart, dict) and set(restart) == _RESTART_KEYS and all(
        _count(restart[name]) for name in _RESTART_KEYS)


def _pruned_shape(mode: str, kind: str, card_ref: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Gate D-2 U10-e: an apply record in format 3 (after its run's window), judged by
    the same value rules. Every kept field must be there; nothing else may be."""
    if mode != "apply" or set(payload) - {"format", "card", "last_log_id", "restart"} \
            or not {"card", "last_log_id"} <= set(payload):
        return None
    card, fields = payload["card"], PRUNED_APPLY_CARD_FIELDS[kind]
    if not isinstance(card, dict) or set(card) != set(fields):
        return None
    identity_key = "id" if kind == "personal" else "lexeme_id"
    if card[identity_key] != card_ref or isinstance(card[identity_key], bool):
        return None
    if not _fields_ok(card, "legacy") or not _count(payload["last_log_id"]):
        return None
    rebuilt: dict[str, Any] = {"format": PRUNED_FORMAT, "card": {name: card[name] for name in fields},
                               "last_log_id": payload["last_log_id"]}
    if "restart" in payload:
        if not _restart_ok(payload["restart"]):
            return None
        rebuilt["restart"] = {name: payload["restart"][name] for name in sorted(_RESTART_KEYS)}
    return rebuilt


def _srs_columns_shape(mode: str, before_text: Any, after_text: Any) -> bool:
    """The record's SRS JSON columns hold only SRS values of known names."""
    try:
        before, after = json.loads(before_text), json.loads(after_text)
    except (TypeError, ValueError):
        return False
    # Keys AND values: apply's after = the FSRS values it wrote; rollback's before =
    # the card's last FSRS projection, its after = the legacy projection it wrote.
    if mode == "apply":
        return (before is None and isinstance(after, dict) and set(after) <= _APPLY_VALUE_KEYS
                and _fields_ok(after, "fsrs"))
    return (isinstance(before, dict) and set(before) == set(RESTORE_REQUIRED) and _fields_ok(before, "fsrs")
            and isinstance(after, dict) and set(after) <= _ROLLBACK_VALUE_KEYS and _fields_ok(after, "legacy"))


def _restorable(card: dict[str, Any]) -> bool:
    """Gate D-2 U10 fix P1: every value rollback writes back is checked for type,
    range and meaning before any write. NULL passes only where the column allows it;
    nothing is repaired, defaulted or converted. A pre-conversion card is legacy, so
    FSRS-card conditions (a complete engine state) are not required of it."""
    if any(name not in card for name in _ROLLBACK_INPUT + RESTORE_REQUIRED):
        return False

    def number(value: Any) -> bool:
        return value is None or _finite(value)

    def text(value: Any, allow_empty: bool = True) -> bool:
        return value is None or (isinstance(value, str) and (allow_empty or value != ""))

    flags = card["srs_history_flags"]
    if flags is not None:
        try:
            parsed = json.loads(flags) if isinstance(flags, str) else None
        except ValueError:
            parsed = None
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            return False
    return (_count(card["review_level"])
            and (card["next_review_at"] is None or _instant(card["next_review_at"]))
            and text(card["completion_metric_version"], allow_empty=False)
            and (card["first_completed_at"] is None or _instant(card["first_completed_at"]))
            and card["srs_engine"] == "legacy"
            and text(card["srs_config_version"], allow_empty=False)
            and (card["srs_state"] is None or (_count(card["srs_state"]) and card["srs_state"] in (1, 2, 3)))
            and (card["srs_step"] is None or _count(card["srs_step"]))
            and number(card["srs_stability"]) and number(card["srs_difficulty"])
            and all(card[name] is None or _instant(card[name])
                    for name in ("srs_due_at", "srs_last_review_at", "srs_effective_due_at"))
            and card["srs_participation"] in (None, "active", "paused")
            and text(card["srs_pause_reason"])
            and card["srs_history_quality"] in (None, "complete", "incomplete", "fresh")
            and ("srs_card_version" not in card or _count(card["srs_card_version"])))


def _rollback_input(payload: Any, kind: str, card_ref: int, columns: frozenset[str]) -> tuple[dict[str, Any], int] | None:
    """(pre-conversion card values, last_log_id) from an apply snapshot of format 1
    or 2, or None when the record's structure (P2) or any value it would restore (P1)
    is not what it must be. NULL is a valid value where the column allows it; a
    missing key is not."""
    shape = _record_shape("apply", kind, card_ref, payload, columns)
    if shape is None or not _restorable(shape["card"]):
        return None
    return shape["card"], shape["last_log_id"]


def _was_converted(connection: Any, key: CardKey) -> bool:
    return connection.execute(
        "SELECT 1 FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
        "WHERE r.mode = 'apply' AND s.user_id = ? AND s.card_kind = ? AND s.card_ref = ? LIMIT 1",
        (key.user_id, key.kind, key.ref_id),
    ).fetchone() is not None


def _latest_rollback_record(connection: Any, key: CardKey) -> dict[str, Any] | None:
    """The record of the rollback that undid the card's latest conversion, if any."""
    params = (key.user_id, key.kind, key.ref_id)
    latest_apply = connection.execute(
        "SELECT MAX(s.id) AS id FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
        "WHERE r.mode = 'apply' AND s.user_id = ? AND s.card_kind = ? AND s.card_ref = ?", params,
    ).fetchone()["id"]
    row = connection.execute(
        "SELECT s.* FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
        "WHERE r.mode = 'rollback' AND r.status = 'completed' AND s.user_id = ? AND s.card_kind = ? "
        "AND s.card_ref = ? ORDER BY s.id DESC LIMIT 1", params,
    ).fetchone()
    if row is None or (latest_apply is not None and row["id"] < latest_apply):
        return None
    return dict(row)


def _read_rollback_record(record: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """(baseline, restore values), or None when the record cannot be trusted as written."""
    try:
        payload = json.loads(record["legacy_json"])
        restore = json.loads(record["srs_before_json"])
        baseline = payload["baseline"]
        if not isinstance(baseline, dict) or not isinstance(restore, dict):
            return None
        if (any(name not in baseline for name in BASELINE_KEYS)
                or not all(isinstance(baseline[name], int) and not isinstance(baseline[name], bool)
                           for name in ("card_version", "last_log_id"))
                or not all(isinstance(baseline[name], str) for name in ("card_fingerprint", "logs_fingerprint"))):
            return None
        if set(restore) != set(RESTORE_REQUIRED) or set(restore) & set(ROLLBACK_PRESERVED):
            return None
        if (restore["srs_engine"] != "fsrs" or restore["srs_participation"] not in ("active", "paused")
                or restore["srs_history_quality"] not in ("complete", "incomplete", "fresh")
                or not isinstance(json.loads(restore["srs_history_flags"] or "[]"), list)
                or (restore["srs_effective_due_at"] is not None and read_utc(restore["srs_effective_due_at"]) is None)):
            return None
        load_state(restore)  # the engine state must be one this config accepts
    except (TypeError, ValueError, KeyError, AttributeError, SrsWriteError, SrsEngineError):
        return None
    return baseline, restore


def _id_reused(connection: Any, key: CardKey) -> bool:
    # A personal id in the deletion ledger that exists again is not the same card.
    return key.kind == "personal" and connection.execute(
        "SELECT 1 FROM srs_card_deletions WHERE card_kind = 'personal' AND card_ref = ? LIMIT 1", (key.ref_id,),
    ).fetchone() is not None


def _reconvert_candidate(connection: Any, key: CardKey, card: dict[str, Any], logs: list[dict[str, Any]],
                         common: dict[str, Any]) -> MigrationCandidate:
    def blocked(*flags: str) -> MigrationCandidate:
        return MigrationCandidate(**common, quality="reconvert_blocked", flags=flags, values_json=None)

    record = _latest_rollback_record(connection, key)
    if record is None:
        return blocked("rollback_snapshot_missing")
    parsed = _read_rollback_record(record)
    if parsed is None:
        return blocked("rollback_snapshot_unreadable")
    baseline, restore = parsed
    if _id_reused(connection, key):
        return blocked("identity_reused")
    if history_unreadable(logs, card["evidence_from_log_id"]):
        return blocked("history_unreadable")
    unchanged = (card["srs_card_version"] == baseline["card_version"]
                 and common["card_fingerprint"] == baseline["card_fingerprint"]
                 and common["logs_fingerprint"] == baseline["logs_fingerprint"]
                 and common["last_log_id"] == baseline["last_log_id"])
    # The card's last FSRS config must be the current engine config, whether it is
    # restored or (changed) re-converted with no state.
    if restore["srs_config_version"] != DEFAULT_CONFIG.config_version:
        return blocked("config_mismatch")
    if unchanged:
        values = dict(restore)
        if card["status"] == "known" and values["srs_participation"] != "paused":
            values.update(srs_participation="paused", srs_pause_reason="legacy_known")  # never un-pause known
        restart = None
        if restore["srs_state"] is None and card["evidence_from_log_id"] is not None:
            # A plan-B card rolled back again before its first review: restored to "no
            # state" with a NEW permission tied to this snapshot (an older one is never reused).
            restart = _json(dict(previous_boundary=card["evidence_from_log_id"], rollback_record_id=record["id"]))
        return MigrationCandidate(**common, quality=restore["srs_history_quality"],
                                  flags=tuple(json.loads(restore["srs_history_flags"] or "[]")),
                                  values_json=_json(values), reconversion="restored", restart_json=restart)
    if card["evidence_from_log_id"] is not None:
        # Gate D-2 U8 plan B (approved): no engine state (U5 rules); the boundary stays
        # until the first real FSRS review replaces it under this snapshot's permission.
        # The old history is NOT replayed (approved 2026-10-13): it never feeds the new
        # state or evidence, and an earlier "no state" start (U5 conversion, earlier
        # plan B) can never match a full replay. Its safety checks are the ones above:
        # valid rollback record, identity, readable history (shared rule), config.
        candidate = _incomplete_candidate(card, common, ("changed_since_rollback", "evidence_restart"))
        if candidate.values_json is None:
            return candidate
        return replace(candidate, reconversion="state_none_restart", restart_json=_json(dict(
            previous_boundary=card["evidence_from_log_id"], rollback_record_id=record["id"])))
    _, flags, _ = _history(card, logs, key)
    candidate = _incomplete_candidate(card, common, tuple(sorted(set(flags) | {"changed_since_rollback"})))
    return replace(candidate, reconversion="state_none") if candidate.values_json else candidate


def _scope(keys: Sequence[CardKey]) -> tuple[CardKey, ...]:
    if not keys or len({key.user_id for key in keys}) != 1:
        raise SrsWriteError("explicit_single_account_scope_required", 400)
    return tuple(sorted(set(keys), key=lambda key: (key.kind, key.ref_id)))


def _connector(connect: Any) -> Any:
    """OPS_MIGRATION_CLI_PLAN 6-1: an injected connection function, else the module's
    get_connection looked up now. Commit / rollback / close stay the context manager's."""
    if connect is None:
        return get_connection
    if not callable(connect):
        raise SrsWriteError("invalid_connection_factory", 400)
    return connect


def dry_run(keys: Sequence[CardKey], *, connect: Any = None) -> tuple[MigrationCandidate, ...]:
    """No run/config/snapshot rows, progress creation or schema initialization."""
    keys = _scope(keys)
    with _connector(connect)(read_only=True) as connection:
        return tuple(inspect_card(connection, key) for key in keys)


def _plan_json(plan: Sequence[MigrationCandidate]) -> str:
    return _json({"user_id": plan[0].key.user_id, "config_version": DEFAULT_CONFIG.config_version,
                  "cards": [dict(kind=p.key.kind, ref_id=p.key.ref_id, card=p.card_fingerprint,
                                 logs=p.logs_fingerprint, version=p.card_version, quality=p.quality,
                                 values=p.values_json, flags=p.flags, last_log_id=p.last_log_id) for p in plan]})


# Gate D-2 U10-d (A3', approved 2026-10-16): an apply run can be rolled back, or resumed
# under the same key, for 30x24 hours from its first `started_at`. Exactly at the end it is
# closed. Resuming or completing never extends it. See U10_CONTRACT section 11.
ROLLBACK_WINDOW = timedelta(hours=30 * 24)
WINDOW_ERRORS = {
    "rollback": {"expired": "rollback_window_closed", "unverifiable": "rollback_window_unverifiable"},
    "resume": {"expired": "migration_resume_window_closed", "unverifiable": "migration_resume_window_unverifiable"},
}


def rollback_window(started_at: Any, now: datetime) -> str:
    """'open', 'expired' or 'unverifiable' for an apply run started at `started_at`
    (the stored text), judged at the server instant `now`. Only real UTC instants are
    compared; a missing, unreadable, zone-less or future start is 'unverifiable' and is
    never guessed, repaired or treated as expired."""
    started = read_utc(started_at)
    if started is None or started > now:
        return "unverifiable"
    return "open" if now - started < ROLLBACK_WINDOW else "expired"


def _require_window(started_at: Any, now: datetime, action: str) -> None:
    state = rollback_window(started_at, now)
    if state != "open":
        raise SrsWriteError(WINDOW_ERRORS[action][state])


def _window_error(error: BaseException) -> bool:
    return isinstance(error, SrsWriteError) and error.code in WINDOW_ERRORS["resume"].values()


# --- Gate D-2 U10-e review fix: the value contract of an apply run's scope_json ------
# Exactly what `_plan_json` writes from `inspect_card` candidates (U10_CONTRACT 12-7).
# A scope is judged by value, never repaired; nothing here raises on bad input and no
# judgement relies on `assert` (same result under `python -O`).
_HISTORY_QUALITIES = frozenset({"complete", "incomplete", "fresh"})
_NO_VALUE_QUALITIES = frozenset({"unavailable", "already_fsrs", "identity_unknown", "reconvert_blocked"})


def _ref(value: Any) -> bool:
    return _count(value) and value > 0


def _scope_top(value: Any, keys: set[str], config_version: Any) -> bool:
    """Shared top level: account, the run's own config, a non-empty list of cards."""
    return (isinstance(value, dict) and set(value) == keys and _ref(value["user_id"])
            and _token(value["config_version"]) and value["config_version"] == config_version
            and isinstance(value["cards"], list) and len(value["cards"]) > 0
            and all(isinstance(c, dict) and isinstance(c.get("kind"), str) and c["kind"] in _CARD_TABLES
                    and _ref(c.get("ref_id")) for c in value["cards"])
            and len({(c["kind"], c["ref_id"]) for c in value["cards"]}) == len(value["cards"]))


def _scope_values(text: Any, config_version: str) -> bool:
    """A candidate's `values`: NULL, or the JSON text of the FSRS columns it would write
    (the apply srs_after_json contract: known names, fsrs, this config, value rules)."""
    if text is None:
        return True
    if not isinstance(text, str):
        return False
    try:
        values = json.loads(text)
    except (ValueError, RecursionError):
        return False
    return (isinstance(values, dict) and set(values) <= _APPLY_VALUE_KEYS and values.get("srs_engine") == "fsrs"
            and values.get("srs_config_version") == config_version and _fields_ok(values, "fsrs"))


def _scope_card(card: dict[str, Any], config_version: str) -> bool:
    if set(card) != _SCOPE_CARD_KEYS:
        return False
    quality = card["quality"]
    if not isinstance(quality, str) or quality not in _HISTORY_QUALITIES | _NO_VALUE_QUALITIES:
        return False
    missing_card = card["card"] is None
    if missing_card != (card["version"] is None) or (missing_card and quality != "unavailable"):
        return False  # only a missing card has no fingerprint / version
    return ((missing_card or _fingerprint(card["card"])) and (missing_card or _count(card["version"]))
            and _fingerprint(card["logs"]) and _count(card["last_log_id"])
            and isinstance(card["flags"], list) and all(_token(flag) for flag in card["flags"])
            and _scope_values(card["values"], config_version)
            and (card["values"] is None or quality in _HISTORY_QUALITIES))


def _full_scope(value: Any, config_version: Any) -> bool:
    """An apply run's original scope_json, value by value."""
    return (_scope_top(value, {"user_id", "config_version", "cards"}, config_version)
            and all(_scope_card(card, value["config_version"]) for card in value["cards"]))


def _reduced_scope(value: Any, config_version: Any) -> bool:
    """U10-e: an apply run's scope_json after its window (U10_CONTRACT 12-3)."""
    return (_scope_top(value, {"format", "user_id", "config_version", "cards", "request_sha256"}, config_version)
            and value["format"] == PRUNED_SCOPE_FORMAT and not isinstance(value["format"], bool)
            and _fingerprint(value["request_sha256"])
            and all(set(card) == {"kind", "ref_id"} for card in value["cards"]))


def _scope_matches(stored: Any, scope: str, config_version: Any) -> bool:
    """Same request: the stored scope text, or -- after U10-e -- its SHA-256."""
    if stored == scope:
        return True
    try:
        parsed = json.loads(stored)
    except (TypeError, ValueError, RecursionError):
        return False
    return _reduced_scope(parsed, config_version) and hashlib.sha256(scope.encode()).hexdigest() == parsed["request_sha256"]


def _run_id(connection: Any, run_key: str, mode: str, scope: str, at: datetime | None = None,
            new_run_only: bool = False, existing_run_only: bool = False) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run_key):
        raise SrsWriteError("invalid_migration_run_key", 400)
    row = connection.execute("SELECT * FROM srs_migration_runs WHERE run_key = ?", (run_key,)).fetchone()
    if row and new_run_only:
        # OPS_MIGRATION_CLI_PLAN 4-4-2-1 (P1): under the caller's account lock, any existing run with
        # this key (any state, account or scope) refuses a first run; nothing about it is reported.
        raise SrsWriteError("migration_run_exists")
    if not row and existing_run_only:
        # OPS_MIGRATION_RESUME_PLAN 9-2 (P2): a resume never starts a run.
        raise SrsWriteError("migration_run_missing")
    if row:
        if not _scope_matches(row["scope_json"], scope, row["config_version"]) or row["mode"] != mode \
                or row["config_version"] != DEFAULT_CONFIG.config_version:
            raise SrsWriteError("migration_run_conflict")
        if row["status"] == "aborted":
            raise SrsWriteError("migration_run_closed")
        if existing_run_only and row["status"] not in ("started", "failed"):
            raise SrsWriteError("migration_run_not_resumable")
        return row["id"]
    cursor = connection.execute(
        "INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
        "config_version, started_at) VALUES (?, ?, 'started', ?, 'fsrs', ?, ?, ?) RETURNING id",
        (run_key, mode, scope, PINNED_LIBRARY_VERSION, DEFAULT_CONFIG.config_version, (at or now_utc()).isoformat()),
    )
    return cursor.fetchone()["id"]


# --- OPS_MIGRATION_RESUME_PLAN 9-2 (P2): the caller's pre-read values, compared under the lock ------
# Hashes only; no judgement here (the caller judged the pre-read with its own rules).
_PROGRESS_KEYS = frozenset({"run_id", "status", "mode", "config_version", "started_at", "finished_at",
                            "scope_sha256", "summary_sha256", "snapshots_sha256"})


def _short_text(value: Any, limit: int) -> bool:
    return type(value) is str and 0 < len(value) <= limit


def _expected_progress_ok(value: Any) -> bool:
    if type(value) is not dict or set(value) != _PROGRESS_KEYS:
        return False
    return (type(value["run_id"]) is int and value["run_id"] >= 1
            and value["status"] in ("started", "failed") and type(value["status"]) is str
            and value["mode"] == "apply" and type(value["mode"]) is str
            and _short_text(value["config_version"], 128) and _short_text(value["started_at"], 64)
            and (value["finished_at"] is None or _short_text(value["finished_at"], 64))
            and _fingerprint(value["scope_sha256"])
            and (value["summary_sha256"] is None or _fingerprint(value["summary_sha256"]))
            and _fingerprint(value["snapshots_sha256"]))


def _text_sha256(text: Any) -> str | None:
    return None if text is None else hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def run_progress_values(connection: Any, run_id: int) -> dict[str, Any]:
    """The nine fixed values of contract 9-2 for one run, read on `connection` (hashes only)."""
    row = connection.execute("SELECT id, status, mode, config_version, started_at, finished_at, scope_json, "
                             "summary_json FROM srs_migration_runs WHERE id = ?", (run_id,)).fetchone()
    snapshots = [[r["id"], r["user_id"], r["card_kind"], r["card_ref"]] for r in connection.execute(
        "SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots WHERE run_id = ? ORDER BY id",
        (run_id,)).fetchall()]
    listed = json.dumps(snapshots, separators=(",", ":"), ensure_ascii=True)
    return {"run_id": row["id"], "status": row["status"], "mode": row["mode"],
            "config_version": row["config_version"], "started_at": row["started_at"],
            "finished_at": row["finished_at"], "scope_sha256": _text_sha256(row["scope_json"]),
            "summary_sha256": _text_sha256(row["summary_json"]),
            "snapshots_sha256": hashlib.sha256(listed.encode("utf-8")).hexdigest()}


def _resumable_cursor(connection: Any, run_id: int, card_count: int) -> bool:
    """The stored cursor is an int (not bool) with 0 <= cursor < card_count; unreadable means no."""
    text = connection.execute("SELECT summary_json FROM srs_migration_runs WHERE id = ?",
                              (run_id,)).fetchone()["summary_json"]
    if text is None:
        return card_count > 0
    try:
        summary = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        return False
    cursor = summary.get("cursor") if isinstance(summary, dict) else None
    return type(cursor) is int and 0 <= cursor < card_count


def apply_plan(plan: Sequence[MigrationCandidate], run_key: str, *, approved: bool = False,
               batch_size: int = 100, connect: Any = None, new_run_only: bool = False,
               existing_run_only: bool = False, expected_progress: Any = None) -> list[dict[str, Any]]:
    """Explicit application only. Incomplete candidates cannot be applied. With `new_run_only` the
    call may only start a NEW run (OPS_MIGRATION_CLI_PLAN 4-4-2-1); with `existing_run_only` it may only
    continue an existing, resumable run whose pre-read values (`expected_progress`) still hold under the
    account lock (OPS_MIGRATION_RESUME_PLAN 9-2). Without either nothing changes."""
    if not approved:
        raise SrsWriteError("explicit_apply_required", 400)
    _scope([candidate.key for candidate in plan])
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise SrsWriteError("invalid_migration_batch_size", 400)
    if type(new_run_only) is not bool:
        raise SrsWriteError("invalid_new_run_only", 400)
    if type(existing_run_only) is not bool:
        raise SrsWriteError("invalid_existing_run_only", 400)
    if (new_run_only and existing_run_only) or (not existing_run_only and expected_progress is not None):
        raise SrsWriteError("invalid_run_mode", 400)
    if existing_run_only and not _expected_progress_ok(expected_progress):
        raise SrsWriteError("invalid_expected_progress", 400)
    _connector(connect)                    # a bad connection function is refused before any connection
    scope = _plan_json(plan)
    user_id = plan[0].key.user_id
    with _connector(connect)(read_only=False) as connection:
        begin_card_write(connection, user_id)
        at = now_utc()
        run_id = _run_id(connection, run_key, "apply", scope, at, new_run_only,
                         existing_run_only)                                       # first connection only
        if existing_run_only:
            # 9-2 (5)(6): the caller's pre-read must still hold here, before the window, the cursor or
            # any write; then the cursor must point inside the plan.
            if run_progress_values(connection, run_id) != expected_progress:
                raise SrsWriteError("migration_run_changed")
            if not _resumable_cursor(connection, run_id, len(plan)):
                raise SrsWriteError("migration_run_not_resumable")
        saved = connection.execute("SELECT summary_json, started_at FROM srs_migration_runs WHERE id = ?",
                                   (run_id,)).fetchone()
        progress = json.loads(saved["summary_json"]) if saved["summary_json"] else {"cursor": 0, "results": []}
        if progress["cursor"] < len(plan):
            # U10-d: a same-key call that would write (a real resume) needs the run's window.
            # A call with nothing left returns the stored results below without writing.
            _require_window(saved["started_at"], at, "resume")
    start = progress["cursor"]
    results: list[dict[str, Any]] = progress["results"]
    # Snapshot + cursor commit together. A crash resumes at the next card;
    # repeated batches never replay already committed cards.
    for result in results:
        if result["result"] == "applied":
            result["result"] = "already_applied"
    if start >= len(plan):
        return results
    end = min(start + batch_size, len(plan))
    try:
        for index in range(start, end):
            candidate = plan[index]
            key = candidate.key
            with _connector(connect)(read_only=False) as connection:
                begin_card_write(connection, user_id)
                at = now_utc()  # one server instant for this card's check and writes
                run = connection.execute("SELECT status, summary_json, started_at FROM srs_migration_runs WHERE id = ?",
                                         (run_id,)).fetchone()
                stored_cursor = json.loads(run["summary_json"])["cursor"] if run["summary_json"] else 0
                if run["status"] == "aborted" or stored_cursor != index:
                    raise SrsWriteError("migration_cursor_conflict")
                # U10-d: re-checked after the lock for every card; earlier cards stay committed.
                _require_window(run["started_at"], at, "resume")
                snapshot = connection.execute(
                    "SELECT id FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ? AND card_kind = ? AND card_ref = ?",
                    (run_id, user_id, key.kind, key.ref_id),
                ).fetchone()
                if snapshot:
                    results.append(dict(kind=key.kind, ref_id=key.ref_id, result="already_applied"))
                current = inspect_card(connection, key, for_update=True)
                if snapshot:
                    pass
                elif current != candidate:
                    results.append(dict(kind=key.kind, ref_id=key.ref_id, result="conflict"))
                elif candidate.values_json is None:
                    entry = dict(kind=key.kind, ref_id=key.ref_id, result="blocked", quality=candidate.quality)
                    if candidate.quality == "reconvert_blocked":
                        entry["reasons"] = list(candidate.flags)
                    if candidate.quality not in ("identity_unknown", "unavailable", "already_fsrs", "reconvert_blocked"):
                        # Gate D-2 U4: keep the past-learning fact even when the card is not
                        # converted (U5 is separate). Identity-unknown history is not judged.
                        entry["history_intro"] = record_intro(connection, key.kind, key.user_id, key.ref_id,
                                                              load_card(connection, key), load_logs(connection, key))
                    results.append(entry)
                else:
                    card = load_card(connection, key)
                    values = json.loads(current.values_json)
                    # Recompute instead of trusting caller-provided write fields.
                    ensure_config(connection, at.isoformat())
                    update_card(connection, key, card["srs_card_version"], values)
                    connection.execute(
                        "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                        "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (run_id, user_id, key.kind, key.ref_id, card["srs_card_version"],
                         _json({"format": SNAPSHOT_FORMAT, "card": _kept(card, APPLY_CARD_FIELDS[key.kind]),
                                "last_log_id": candidate.last_log_id,
                                **({"restart": json.loads(current.restart_json)} if current.restart_json else {})}),
                         "null", current.values_json,
                         candidate.quality, _json(candidate.flags), at.isoformat()),
                    )
                    entry = dict(kind=key.kind, ref_id=key.ref_id, result="applied",
                                 history_intro=record_intro(connection, key.kind, key.user_id, key.ref_id,
                                                            card, load_logs(connection, key)))
                    if candidate.reconversion:
                        entry["reconversion"] = candidate.reconversion
                    results.append(entry)
                connection.execute("UPDATE srs_migration_runs SET summary_json = ?, status = 'started' WHERE id = ?",
                                   (_json({"cursor": index + 1, "results": results}), run_id))
    except Exception as error:
        if _window_error(error):
            raise  # U10-d: a closed window is not a failure of the run; its status is not changed
        with _connector(connect)(read_only=False) as connection:
            begin_card_write(connection, user_id)
            run = connection.execute("SELECT status, summary_json FROM srs_migration_runs WHERE id = ?", (run_id,)).fetchone()
            cursor = json.loads(run["summary_json"])["cursor"] if run["summary_json"] else 0
            if cursor == index and run["status"] == "started":
                connection.execute("UPDATE srs_migration_runs SET status = 'failed' WHERE id = ?", (run_id,))
        raise
    with _connector(connect)(read_only=False) as connection:
        begin_card_write(connection, user_id)
        if end == len(plan):
            connection.execute("UPDATE srs_migration_runs SET status = 'completed', finished_at = ? "
                               "WHERE id = ? AND status != 'aborted'", (now_utc().isoformat(), run_id))
    return results


class RollbackHistoryUnreadable(SrsWriteError):
    """Gate D-2 U8: evaluations after the conversion that cannot be read. `cards`
    lists each card with the log ids and the cause ("time" or "rating")."""

    def __init__(self, cards: list[dict[str, Any]]):
        super().__init__("rollback_history_unreadable", 409)
        self.cards = cards

    def __str__(self) -> str:
        return f"rollback_history_unreadable: {_json(self.cards)}"


def judge_rollback_card(connection: Any, key: CardKey, snapshot: dict[str, Any], source: Any, *,
                        for_update: bool = False) -> dict[str, Any]:
    """The per-card rollback decision of `rollback_plan`, READ ONLY (P-RB tool contract 3-2):
    shared by the public rollback (which then writes) and the recovery precheck (which never
    writes), so both judge a card the same way.

    verdict: missing | access_lost | identity_unknown | snapshot_incomplete | conflict |
    unreadable (+logs) | history_mismatch | rollback (+card, before, later, level, due)."""
    user_id = key.user_id
    card = load_card(connection, key, for_update=for_update)
    if card is None:
        return {"verdict": "missing"}
    if not _authorized(connection, key):
        return {"verdict": "access_lost"}
    if is_identity_unknown(connection, user_id, key.kind, key.ref_id):
        # Gate D-2 U3: the snapshot may describe a different card with this id.
        return {"verdict": "identity_unknown"}
    # Gate D-2 U10-a: every value rollback writes must be in the record (format 1
    # or 2). A record that lacks one is never half-applied or reported rolled_back.
    try:
        parsed = _rollback_input(json.loads(snapshot["legacy_json"]), key.kind, key.ref_id,
                                 _card_columns(connection, key.kind))
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        return {"verdict": "snapshot_incomplete"}
    before, last_log_id = parsed
    later = [log for log in load_logs(connection, key) if log["id"] > last_log_id]
    if (card["srs_engine"] != "fsrs" or card["srs_config_version"] != source["config_version"]
            or card["srs_card_version"] != snapshot["card_version_before"] + 1 + len(later)
            or any(log["srs_engine"] != "fsrs" for log in later)):
        return {"verdict": "conflict"}
    # Gate D-2 U8: a later evaluation that cannot be read is neither skipped,
    # re-timed nor re-rated. The whole rollback is refused with the cause.
    bad = [dict(log_id=log["id"], cause="time" if read_utc(log["event_at"]) is None else "rating")
           for log in later if read_utc(log["event_at"]) is None or log["rating"] not in RATINGS]
    if bad:
        return {"verdict": "unreadable", "logs": bad}
    # U8 fix P2: the later reviews in real UTC order (log id for the same instant),
    # not in stored-text order. The order must then also be the order of log ids
    # and of card versions; sorting never repairs a real time inversion.
    later.sort(key=lambda log: (read_utc(log["event_at"]), log["id"]))
    level, due = before["review_level"], before["next_review_at"]
    for index, log in enumerate(later):
        if (log["card_version_before"] != snapshot["card_version_before"] + 1 + index
                or (index and log["id"] <= later[index - 1]["id"])):
            return {"verdict": "history_mismatch"}
        level, due = compute_review_schedule(log["rating"], level, read_utc(log["event_at"]))
    return {"verdict": "rollback", "card": card, "before": before, "later": later, "level": level, "due": due}


def write_card_rollback(connection: Any, key: CardKey, judged: dict[str, Any], rollback_id: int,
                        at: datetime) -> dict[str, Any]:
    """The rollback write of ONE card judged `rollback` by `judge_rollback_card`, on the
    caller's connection and transaction (the caller holds the account lock and commits).
    Shared by the public `rollback_plan` and the P-RB recovery step B."""
    user_id = key.user_id
    card, before, later = judged["card"], judged["before"], judged["later"]
    level, due = judged["level"], judged["due"]
    # Engine projection only. Explicitly never restored: the card version (CAS) and
    # the past-learning mark (U4), which outlive any rollback and re-conversion.
    values = {name: before[name] for name in RESTORE_REQUIRED}
    assert not set(values) & set(ROLLBACK_PRESERVED)
    values.update(review_level=level, next_review_at=due,
                  completion_metric_version=card["completion_metric_version"] or before["completion_metric_version"],
                  first_completed_at=card["first_completed_at"] or before["first_completed_at"])
    update_card(connection, key, card["srs_card_version"], values)
    # Gate D-2 U8: keep the last FSRS projection and the post-rollback baseline,
    # in this transaction, so a re-conversion can restore exactly that state.
    restore = {name: card[name] for name in RESTORE_REQUIRED}
    after = load_card(connection, key)
    logs = load_logs(connection, key)
    baseline = dict(card_version=after["srs_card_version"], card_fingerprint=_card_print(after),
                    logs_fingerprint=_digest(logs), last_log_id=max((log["id"] for log in logs), default=0))
    connection.execute(
        "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
        "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rollback_id, user_id, key.kind, key.ref_id, card["srs_card_version"],
         _json({"format": SNAPSHOT_FORMAT, "card": _kept(after, ROLLBACK_CARD_FIELDS[key.kind]),
                "baseline": baseline}), _json(restore), _json(values),
         card["srs_history_quality"], card["srs_history_flags"], at.isoformat()),
    )
    return dict(kind=key.kind, ref_id=key.ref_id, result="rolled_back", preserved_reviews=len(later))


def rollback_plan(run_key: str, rollback_key: str, *, user_id: int, approved: bool = False,
                  recovery: Any = None) -> list[dict[str, Any]]:
    """Restore projections, not history. Preserve post-migration evaluations.

    P-RB: under an active account write block only a recovery grant for this account, that
    block and the `rollback` action passes; the grant also records `changes_started` in
    this same transaction (committed or discarded together with the rollback)."""
    if not approved:
        raise SrsWriteError("explicit_rollback_required", 400)
    if recovery is not None and getattr(recovery, "action", None) != "rollback":
        raise SrsWriteError("recovery_grant_invalid", 409)
    with get_connection() as connection:
        if recovery is None:
            begin_card_write(connection, user_id)
        else:
            begin_card_write(connection, user_id, recovery=recovery)
        source = connection.execute("SELECT * FROM srs_migration_runs WHERE run_key = ? AND mode = 'apply'", (run_key,)).fetchone()
        if source is None or json.loads(source["scope_json"])["user_id"] != user_id:
            raise SrsWriteError("migration_run_not_found", 404)
        snapshots = [dict(row) for row in connection.execute(
            "SELECT * FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ? ORDER BY id", (source["id"], user_id),
        ).fetchall()]
        scope = _json({"user_id": user_id, "source_run_id": source["id"]})
        at = now_utc()  # one server instant for the window check and every write below
        rollback_id = _run_id(connection, rollback_key, "rollback", scope, at)
        rollback = connection.execute("SELECT * FROM srs_migration_runs WHERE id = ?", (rollback_id,)).fetchone()
        if rollback["status"] == "completed":
            return json.loads(rollback["summary_json"])
        # U10-d: a new rollback needs the source run's window. Raising here discards this
        # transaction, including the run row _run_id just inserted.
        _require_window(source["started_at"], at, "rollback")
        results: list[dict[str, Any]] = []
        unreadable: list[dict[str, Any]] = []
        for snapshot in snapshots:
            key = CardKey(snapshot["card_kind"], user_id, snapshot["card_ref"])
            judged = judge_rollback_card(connection, key, snapshot, source, for_update=True)
            verdict = judged["verdict"]
            if verdict in ("missing", "access_lost"):
                results.append(dict(kind=key.kind, ref_id=key.ref_id, result="missing_or_access_lost"))
                continue
            if verdict == "identity_unknown":
                results.append(dict(kind=key.kind, ref_id=key.ref_id, result="skipped", reason="identity_unknown"))
                continue
            if verdict == "snapshot_incomplete":
                results.append(dict(kind=key.kind, ref_id=key.ref_id, result="blocked", reason="snapshot_incomplete"))
                continue
            if verdict == "conflict":
                results.append(dict(kind=key.kind, ref_id=key.ref_id, result="conflict"))
                continue
            if verdict == "unreadable":
                unreadable.append(dict(kind=key.kind, ref_id=key.ref_id, logs=judged["logs"]))
                continue
            if verdict == "history_mismatch":
                raise SrsWriteError("rollback_history_mismatch")
            results.append(write_card_rollback(connection, key, judged, rollback_id, at))
        if unreadable:
            # Raising discards this transaction: no card, record or run row is written.
            raise RollbackHistoryUnreadable(unreadable)
        connection.execute("UPDATE srs_migration_runs SET status = 'completed', summary_json = ?, finished_at = ? WHERE id = ?",
                           (_json(results), at.isoformat(), rollback_id))
        # Do not resume a partially applied source after undoing some cards.
        connection.execute("UPDATE srs_migration_runs SET status = 'aborted' WHERE id = ?", (source["id"],))
    return results


def strip_card_snapshots(connection: Any, user_id: int, card_ids: list[int]) -> dict[str, list[int]]:
    """Gate D-2 U10-a, used ONLY inside an explicit delete of these personal cards (the
    caller holds the account write lock, has checked the cards are this account's and
    owns the transaction that also handles receipts, the ledger and the card rows).

    For this account's snapshot / rollback records of these personal cards:
    - format 1 (card row copied in): rewritten to format 2 -- the card keeps only the
      fields its record type keeps; last_log_id, restart and baseline stay;
    - format 2: untouched;
    - unreadable or unknown shape: the row is deleted (A8, card deletion only; the
      general tools keep and report such rows).
    Every change is a compare-and-set on the text read here; any mismatch raises so
    the whole delete rolls back. Other accounts, other cards, subscribed records and
    review logs are never selected. The SRS value columns hold no content and stay."""
    done: dict[str, list[int]] = {"minimized": [], "deleted": []}
    if not card_ids:
        return done
    marks = ", ".join("?" for _ in card_ids)
    rows = [dict(r) for r in connection.execute(
        f"SELECT s.id, s.card_ref, s.legacy_json, s.srs_before_json, s.srs_after_json, r.mode "
        f"FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r "
        f"ON r.id = s.run_id WHERE s.user_id = ? AND s.card_kind = 'personal' AND s.card_ref IN ({marks}) ORDER BY s.id",
        (user_id, *card_ids)).fetchall()]
    columns = _card_columns(connection, "personal")
    for row in rows:
        try:
            payload = json.loads(row["legacy_json"])
        except (TypeError, ValueError):
            payload = None
        mode = "apply" if row["mode"] == "apply" else "rollback"
        shape = _record_shape(mode, "personal", int(row["card_ref"]), payload, columns)
        if shape is None or not _srs_columns_shape(mode, row["srs_before_json"], row["srs_after_json"]):
            # U10 fix P2 / A8: anything unsupported in the record -> this row goes with the card.
            changed = connection.execute(
                "DELETE FROM srs_migration_snapshots WHERE id = ? AND user_id = ? AND legacy_json = ? "
                "AND COALESCE(srs_after_json, '') = COALESCE(?, '') AND COALESCE(srs_before_json, '') = COALESCE(?, '')",
                (row["id"], user_id, row["legacy_json"], row["srs_after_json"], row["srs_before_json"])).rowcount
            bucket = "deleted"
        elif shape == payload:
            continue  # already exactly the allowed format-2 structure
        else:
            # Rebuilt from allowed fields only; nothing unknown is carried over.
            changed = connection.execute(
                "UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ? AND user_id = ? AND legacy_json = ? "
                "AND COALESCE(srs_after_json, '') = COALESCE(?, '') AND COALESCE(srs_before_json, '') = COALESCE(?, '')",
                (_json(shape), row["id"], user_id, row["legacy_json"], row["srs_after_json"],
                 row["srs_before_json"])).rowcount
            bucket = "minimized"
        if changed != 1:
            raise SrsWriteError("snapshot_content_unverified")
        done[bucket].append(row["id"])
    return done


def minimize_snapshots(connection: Any, user_id: int, *, apply: bool = False, batch_size: int = 200,
                       after_id: int = 0, lock: Any = None, progress: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gate D-2 U10-b: rewrite one account's format-1 snapshot / rollback records
    (card row copied in) to format 2, using the same judgement as the delete path
    (`_record_shape`, `_srs_columns_shape`) -- no separate, looser check.

    - recognised format 1, with every value the record type must keep: rewritten
      from the allowed fields only (values unchanged; last_log_id, restart, baseline,
      card_version_before and both SRS JSON columns untouched);
    - format 2: left as it is;
    - anything unsupported, damaged, or a format-1 record missing a kept value:
      left exactly as it is and reported (never deleted, repaired or guessed -- the
      A8 deletion is only for an explicit card delete).
    Only this account's rows with id <= the largest id seen at the start are visited
    (rows added during the run are left for a later run). With `apply`, each batch
    runs under the account write lock and commits on its own; a row whose JSON
    (legacy_json and both SRS columns) differs from what was judged is reported as a
    conflict and left alone. `cursor` is only advanced after a batch committed.
    Reports hold ids, kinds, modes, field names and counts -- never stored values."""
    # `progress` (when given) is updated in place, so a caller that catches a failure
    # still sees the last committed position.
    report: dict[str, Any] = progress if progress is not None else {}
    report.update({
        "user_id": user_id, "applied": bool(apply), "after_id": after_id, "upper_id": None, "cursor": after_id,
        "minimized": [], "already_minimal": 0, "unsupported": [], "insufficient": [], "conflicts": [],
        "removed_card_fields": [],
    })
    upper = connection.execute("SELECT COALESCE(MAX(id), 0) AS upper FROM srs_migration_snapshots WHERE user_id = ?",
                               (user_id,)).fetchone()["upper"]
    report["upper_id"] = upper
    columns = {kind: _card_columns(connection, kind) for kind in _CARD_TABLES}
    removed: set[str] = set()
    cursor = after_id
    while cursor < upper:
        if apply:
            lock(connection, user_id)
        try:
            rows = [dict(r) for r in connection.execute(
                "SELECT s.id, s.card_kind, s.card_ref, s.legacy_json, s.srs_before_json, s.srs_after_json, r.mode "
                "FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
                "WHERE s.user_id = ? AND s.id > ? AND s.id <= ? ORDER BY s.id LIMIT ?",
                (user_id, cursor, upper, batch_size)).fetchall()]
            if not rows:
                if apply:
                    connection.commit()
                break
            batch: dict[str, list[Any]] = {"minimized": [], "unsupported": [], "insufficient": [], "conflicts": []}
            already = 0
            for row in rows:
                entry = {"id": row["id"], "kind": row["card_kind"], "mode": row["mode"]}
                mode = "apply" if row["mode"] == "apply" else "rollback"
                try:
                    payload = json.loads(row["legacy_json"])
                except (TypeError, ValueError):
                    payload = None
                shape = _record_shape(mode, row["card_kind"], int(row["card_ref"]), payload, columns[row["card_kind"]])
                if shape is None or not _srs_columns_shape(mode, row["srs_before_json"], row["srs_after_json"]):
                    batch["unsupported"].append(dict(entry, reason="unsupported_structure_or_value"))
                    continue
                if "format" in payload:
                    if shape == payload:
                        already += 1
                    else:
                        batch["unsupported"].append(dict(entry, reason="format2_not_minimal"))
                    continue
                fields = (APPLY_CARD_FIELDS if mode == "apply" else ROLLBACK_CARD_FIELDS)[row["card_kind"]]
                missing = sorted(name for name in fields if name not in shape["card"])
                if missing or (mode == "apply" and not _restorable(shape["card"])):
                    batch["insufficient"].append(dict(entry, missing=missing,
                                                      reason="missing_fields" if missing else "unrestorable_value"))
                    continue
                dropped = sorted(set(payload["card"]) - set(shape["card"]))
                if apply:
                    changed = connection.execute(
                        "UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ? AND user_id = ? "
                        "AND legacy_json = ? AND COALESCE(srs_after_json, '') = COALESCE(?, '') "
                        "AND COALESCE(srs_before_json, '') = COALESCE(?, '')",
                        (_json(shape), row["id"], user_id, row["legacy_json"], row["srs_after_json"],
                         row["srs_before_json"])).rowcount
                    if changed != 1:
                        batch["conflicts"].append(entry)
                        continue
                batch["minimized"].append(dict(entry, removed_fields=dropped))
                removed.update(dropped)
            if apply:
                connection.commit()
        except BaseException:
            if apply:
                connection.rollback()
            raise
        # Only after the batch is durable (or, for a dry run, fully judged).
        for name, items in batch.items():
            report[name].extend(items)
        report["already_minimal"] += already
        cursor = rows[-1]["id"]
        report["cursor"] = cursor
        report["removed_card_fields"] = sorted(removed)
    return report


def _unused_permission(connection: Any, snapshot: dict[str, Any], payload: Any) -> bool:
    """The card's LATEST apply record carries a plan-B permission nobody used yet."""
    if not isinstance(payload, dict) or "restart" not in payload:
        return False
    latest = connection.execute(
        "SELECT MAX(s.id) AS latest FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
        "WHERE r.mode = 'apply' AND s.user_id = ? AND s.card_kind = ? AND s.card_ref = ?",
        (snapshot["user_id"], snapshot["card_kind"], snapshot["card_ref"])).fetchone()["latest"]
    return latest == snapshot["id"] and connection.execute(
        "SELECT 1 FROM srs_evidence_restarts WHERE source_snapshot_id = ?", (snapshot["id"],)).fetchone() is None


def prune_expired_runs(connection: Any, user_id: int, *, apply: bool = False, batch_size: int = 50,
                       after_id: int = 0, lock: Any = None, progress: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gate D-2 U10-e: after an apply run's rollback window (U10-d, `rollback_window`)
    has expired, remove the rollback-only values (U10_CONTRACT 12-2, an explicit list)
    from this account's apply records (-> format 3) and the per-card request details
    from the run's scope_json (-> request hash). Everything else is kept; no row is
    deleted and no status or time changes.

    - 'open' runs are skipped; 'unverifiable' runs are left exactly as they are and reported;
    - a card's latest apply record with an unused plan-B permission is left, and so is
      its run's scope_json;
    - damaged / unsupported records, or records missing a kept or rollback value, are left
      and reported (never deleted, repaired or guessed; A8 is only for an explicit delete);
    Apply runs are visited in id order up to the largest id at the start. With `apply`,
    each batch holds the account write lock, re-judges window / protection / targets at
    one server instant, writes with a compare-and-set on every judged value and commits;
    `cursor` moves only after a commit. Reports hold ids, kinds, names, reasons, counts."""
    report: dict[str, Any] = progress if progress is not None else {}
    report.update({
        "user_id": user_id, "applied": bool(apply), "after_id": after_id, "upper_id": None, "cursor": after_id,
        "runs": {"pruned": [], "already_pruned": 0, "open": 0, "unverifiable": [], "protected": [],
                 "unsupported_scope": [], "conflicts": []},
        "snapshots": {"pruned": [], "already_pruned": 0, "protected": [], "unsupported": [], "insufficient": [],
                      "conflicts": []},
        "removed_card_fields": [],
    })
    upper = connection.execute(
        "SELECT COALESCE(MAX(id), 0) AS upper FROM srs_migration_runs WHERE mode = 'apply'").fetchone()["upper"]
    report["upper_id"] = upper
    columns = {kind: _card_columns(connection, kind) for kind in _CARD_TABLES}
    removed: set[str] = set(report["removed_card_fields"])
    cursor = after_id
    while cursor < upper:
        if apply:
            lock(connection, user_id)
        try:
            at = now_utc()  # one server instant for this batch's judgements
            runs = [dict(r) for r in connection.execute(
                "SELECT id, status, started_at, config_version, scope_json FROM srs_migration_runs "
                "WHERE mode = 'apply' AND id > ? AND id <= ? ORDER BY id LIMIT ?", (cursor, upper, batch_size)).fetchall()]
            if not runs:
                if apply:
                    connection.commit()
                break
            batch_runs: dict[str, Any] = {name: [] for name in ("pruned", "unverifiable", "protected", "unsupported_scope",
                                                                "conflicts")}
            batch_snaps: dict[str, Any] = {name: [] for name in ("pruned", "protected", "unsupported", "insufficient",
                                                                 "conflicts")}
            counts = {"runs_already": 0, "runs_open": 0, "snaps_already": 0}
            batch_removed: set[str] = set()
            for run in runs:
                try:
                    scope = json.loads(run["scope_json"])
                except (TypeError, ValueError, RecursionError):
                    scope = None
                owner = scope.get("user_id") if isinstance(scope, dict) else None
                if owner != user_id or isinstance(owner, bool):
                    if connection.execute("SELECT 1 FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ? LIMIT 1",
                                          (run["id"], user_id)).fetchone():
                        # this account's records under a scope that does not name it as a valid id
                        batch_runs["unsupported_scope"].append(dict(id=run["id"], reason="unsupported_scope"))
                    continue
                window = rollback_window(run["started_at"], at)
                if window == "open":
                    counts["runs_open"] += 1
                    continue
                if window == "unverifiable":
                    batch_runs["unverifiable"].append(dict(id=run["id"], reason="started_at_unverifiable"))
                    continue
                # U10-e review fix: the scope is judged by value BEFORE any record of the run
                # is rewritten. A damaged / unsupported scope keeps the scope and every record
                # of the run exactly as stored; the run is only reported.
                reduced: dict[str, Any] | None = None
                already_reduced = _reduced_scope(scope, run["config_version"])
                if not already_reduced:
                    if not _full_scope(scope, run["config_version"]):
                        batch_runs["unsupported_scope"].append(dict(id=run["id"], reason="unsupported_scope"))
                        continue
                    reduced = {"format": PRUNED_SCOPE_FORMAT, "user_id": scope["user_id"],
                               "config_version": scope["config_version"],
                               "cards": [{"kind": c["kind"], "ref_id": c["ref_id"]} for c in scope["cards"]],
                               "request_sha256": hashlib.sha256(run["scope_json"].encode()).hexdigest()}
                    if not (_reduced_scope(reduced, run["config_version"])
                            and _scope_matches(_json(reduced), run["scope_json"], run["config_version"])):
                        batch_runs["unsupported_scope"].append(dict(id=run["id"], reason="reduction_unverified"))
                        continue
                protected_run = False
                for snap in [dict(r) for r in connection.execute(
                        "SELECT id, user_id, card_kind, card_ref, legacy_json, srs_before_json, srs_after_json "
                        "FROM srs_migration_snapshots WHERE run_id = ? AND user_id = ? ORDER BY id",
                        (run["id"], user_id)).fetchall()]:
                    entry = {"id": snap["id"], "kind": snap["card_kind"]}
                    try:
                        payload = json.loads(snap["legacy_json"])
                    except (TypeError, ValueError):
                        payload = None
                    unused = _unused_permission(connection, snap, payload)
                    protected_run = protected_run or unused  # the parent run's scope stays too
                    shape = _record_shape("apply", snap["card_kind"], int(snap["card_ref"]), payload,
                                          columns[snap["card_kind"]])
                    if shape is None or not _srs_columns_shape("apply", snap["srs_before_json"], snap["srs_after_json"]):
                        batch_snaps["unsupported"].append(dict(entry, reason="unsupported_structure_or_value"))
                        continue
                    if shape["format"] == PRUNED_FORMAT:
                        if shape != payload:
                            batch_snaps["unsupported"].append(dict(entry, reason="format3_not_exact"))
                        else:
                            counts["snaps_already"] += 1
                        continue
                    missing = sorted(set(APPLY_CARD_FIELDS[snap["card_kind"]]) - set(shape["card"]))
                    if missing or not _restorable(shape["card"]):
                        batch_snaps["insufficient"].append(
                            dict(entry, missing=missing, reason="missing_fields" if missing else "unrestorable_value"))
                        continue
                    if unused:
                        batch_snaps["protected"].append(dict(entry, reason="unused_restart_permission"))
                        continue
                    pruned = {"format": PRUNED_FORMAT,
                              "card": {name: shape["card"][name] for name in PRUNED_APPLY_CARD_FIELDS[snap["card_kind"]]},
                              "last_log_id": shape["last_log_id"],
                              **({"restart": shape["restart"]} if "restart" in shape else {})}
                    if _record_shape("apply", snap["card_kind"], int(snap["card_ref"]), pruned,
                                     columns[snap["card_kind"]]) != pruned:
                        batch_snaps["unsupported"].append(dict(entry, reason="prune_unverified"))
                        continue
                    dropped = sorted(set(payload["card"]) - set(pruned["card"]))
                    if apply:
                        changed = connection.execute(
                            "UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ? AND user_id = ? "
                            "AND legacy_json = ? AND COALESCE(srs_after_json, '') = COALESCE(?, '') "
                            "AND COALESCE(srs_before_json, '') = COALESCE(?, '') "
                            "AND (SELECT started_at FROM srs_migration_runs WHERE id = ?) = ?",
                            (_json(pruned), snap["id"], user_id, snap["legacy_json"], snap["srs_after_json"],
                             snap["srs_before_json"], run["id"], run["started_at"])).rowcount
                        if changed != 1:
                            batch_snaps["conflicts"].append(entry)
                            continue
                    batch_snaps["pruned"].append(dict(entry, removed_fields=dropped))
                    batch_removed.update(dropped)
                run_entry = {"id": run["id"]}
                if protected_run:
                    batch_runs["protected"].append(dict(run_entry, reason="unused_restart_permission"))
                elif already_reduced:
                    counts["runs_already"] += 1
                else:
                    if apply:
                        changed = connection.execute(
                            "UPDATE srs_migration_runs SET scope_json = ? WHERE id = ? AND mode = 'apply' "
                            "AND scope_json = ? AND started_at = ?",
                            (_json(reduced), run["id"], run["scope_json"], run["started_at"])).rowcount
                        if changed != 1:
                            batch_runs["conflicts"].append(run_entry)
                            continue
                    batch_runs["pruned"].append(dict(run_entry, removed_card_keys=sorted(_SCOPE_CARD_KEYS - {"kind", "ref_id"})))
            if apply:
                connection.commit()
        except BaseException:
            if apply:
                connection.rollback()
            raise
        # Only after the batch is durable (or, for a dry run, fully judged).
        for name, items in batch_runs.items():
            report["runs"][name].extend(items)
        for name, items in batch_snaps.items():
            report["snapshots"][name].extend(items)
        report["runs"]["already_pruned"] += counts["runs_already"]
        report["runs"]["open"] += counts["runs_open"]
        report["snapshots"]["already_pruned"] += counts["snaps_already"]
        removed |= batch_removed
        report["removed_card_fields"] = sorted(removed)
        cursor = runs[-1]["id"]
        report["cursor"] = cursor
    return report
