"""Opt-in FSRS rating transactions. Legacy scheduling remains separate."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.database import VOCAB_ITEM_FIELDS, compute_review_schedule, now_utc
from app.srs import goals, identity, readability, receipts, restoration
from app.srs.completion import CompletionStatus, ReviewEvent, completion_update, evaluate_completion, seoul_date
from app.srs.engine import (
    ADAPTER_VERSION, DEFAULT_CONFIG, LIBRARY_NAME, PINNED_LIBRARY_VERSION,
    RATINGS, CardKey, SrsEngineError, review, state_from_json, state_to_dict, state_to_json, to_utc,
)
from app.srs.storage import (
    SrsWriteError, card_location, is_converted_incomplete, load_logs, load_state, require_subscription,
    state_columns, update_card,
)

_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def validate_request(request_id: str | None, expected_card_version: int | None, session_id: str | None) -> None:
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
        raise SrsWriteError("review_upgrade_required", 422)
    if not isinstance(session_id, str) or not _ID.fullmatch(session_id):
        raise SrsWriteError("review_upgrade_required", 422)
    if isinstance(expected_card_version, bool) or not isinstance(expected_card_version, int) or expected_card_version < 0:
        raise SrsWriteError("review_upgrade_required", 422)


def validate_first_review_request(request_id: str | None, session_id: str | None) -> None:
    """Explicit `expected_card_version: null` (gate-c2 3-2): ids are still required."""
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
        raise SrsWriteError("review_upgrade_required", 422)
    if not isinstance(session_id, str) or not _ID.fullmatch(session_id):
        raise SrsWriteError("review_upgrade_required", 422)


def request_hash(key: CardKey, rating: str, request_id: str, expected_card_version: int,
                 session_id: str, shared_deck_id: int | None, response_time_ms: int | None) -> str:
    payload = dict(kind=key.kind, user_id=key.user_id, ref_id=key.ref_id, rating=rating,
                   request_id=request_id, expected_card_version=expected_card_version,
                   session_id=session_id, shared_deck_id=shared_deck_id, response_time_ms=response_time_ms)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def find_receipt(connection: Any, key: CardKey, rating: str, request_id: str | None,
                 expected_card_version: int | None, session_id: str | None,
                 shared_deck_id: int | None, response_time_ms: int | None,
                 *, first_review: bool = False) -> dict[str, Any] | None:
    if request_id is None:
        return None
    row = connection.execute(
        "SELECT request_hash, response_json, card_kind, card_ref, created_at FROM srs_review_receipts "
        "WHERE user_id = ? AND request_id = ?",
        (key.user_id, request_id),
    ).fetchone()
    if row is None:
        return None
    # Gate D-2 U9: 7-day logical expiry (server clock). An expired receipt is never
    # replayed: the request then meets the card CAS / subscription / first-review
    # rules (409/404), and a receipt-key collision is a request_id_conflict. An
    # unreadable or future created_at is neither replayed nor treated as expired.
    age = receipts.receipt_age_status(row["created_at"], to_utc(now_utc()))
    if age == "expired":
        return None
    if age == "unreadable":
        raise SrsWriteError("card_version_conflict")
    if row["card_kind"] == key.kind and int(row["card_ref"]) == key.ref_id             and identity.receipt_may_be_other_card(connection, key.user_id, key.kind, key.ref_id, row["created_at"]):
        # Gate D-2 U3: this id may now belong to a different card than the one the
        # receipt was written for. Never replay it (its result or stored content)
        # onto the current card, and add nothing: the client refetches.
        raise SrsWriteError("card_version_conflict")
    if first_review:
        validate_first_review_request(request_id, session_id)
    else:
        validate_request(request_id, expected_card_version, session_id)
    if row["request_hash"] != request_hash(key, rating, request_id, expected_card_version, session_id,
                                          shared_deck_id, response_time_ms):
        raise SrsWriteError("request_id_conflict")
    return json.loads(row["response_json"])


def ensure_config(connection: Any, timestamp: str) -> None:
    connection.execute(
        "INSERT INTO srs_config_versions (config_version, engine, library_version, adapter_version, config_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (config_version) DO NOTHING",
        (DEFAULT_CONFIG.config_version, LIBRARY_NAME, PINNED_LIBRARY_VERSION, ADAPTER_VERSION,
         DEFAULT_CONFIG.canonical_json(), timestamp),
    )
    row = connection.execute("SELECT config_json FROM srs_config_versions WHERE config_version = ?",
                             (DEFAULT_CONFIG.config_version,)).fetchone()
    if row["config_json"] != DEFAULT_CONFIG.canonical_json():
        raise SrsWriteError("config_version_conflict")


def introduced_on(connection: Any, user_id: int, at: datetime) -> goals.IntroductionCount:
    # Retains legacy first reviews, including deleted cards. Replay never
    # inserts events, so it cannot consume today's goal a second time.
    # One definition with the study queue (Gate C-1): app/srs/goals.py.
    # Another card's unreadable log time makes the count unknown, never a
    # failed review and never a guessed exact number.
    return goals.introduction_count(connection, user_id, at)


def record_fsrs_review(connection: Any, key: CardKey, card: dict[str, Any], rating: str,
                       request_id: str | None, expected_card_version: int | None, session_id: str | None,
                       shared_deck_id: int | None = None, response_time_ms: int | None = None,
                       *, receipt_version: Any = None, receipt_version_given: bool = False) -> dict[str, Any]:
    """`expected_card_version` is the CAS value against the stored card. A
    subscribed first review (gate-c2 3-2) passes CAS 0 for the row it just
    created, while its receipt keeps the client's original null
    (`receipt_version_given=True, receipt_version=None`)."""
    hashed_version = receipt_version if receipt_version_given else expected_card_version
    if rating not in RATINGS:
        raise SrsWriteError("invalid_review_rating", 400)
    if key.kind == "lexeme":
        require_subscription(connection, key, shared_deck_id)
    receipt = find_receipt(connection, key, rating, request_id, expected_card_version, session_id,
                           shared_deck_id, response_time_ms)
    if receipt is not None:
        return receipt
    if identity.is_identity_unknown(connection, key.user_id, key.kind, key.ref_id):
        # Gate D-2 U3 correction: the id is isolated (its history may belong to another
        # card). Refuse before the engine and before any write, including for a card
        # the client fetched before the flag. Callers hold the account write lock
        # (begin_card_write), and flagging takes the same lock, so the two serialize.
        raise SrsWriteError("card_identity_unknown")
    validate_request(request_id, expected_card_version, session_id)
    if card["srs_card_version"] != expected_card_version:
        raise SrsWriteError("card_version_conflict")
    if card["srs_participation"] != "active":
        raise SrsWriteError("card_paused")
    if card["srs_config_version"] != DEFAULT_CONFIG.config_version:
        raise SrsWriteError("unsupported_config_version")
    state = load_state(card)
    logs = load_logs(connection, key)
    # This card's own history must be readable: completion evidence and the
    # first-review date depend on it. One rule shared with the study queue
    # (app/srs/readability.py: log times, ratings, evidence-window snapshots), checked
    # before the engine and any write. The queue does not serve such a card.
    boundary = card.get("evidence_from_log_id")
    if readability.history_unreadable(logs, boundary):
        raise SrsWriteError("review_history_unreadable")
    times = [goals.read_utc(log["event_at"]) for log in logs]
    window = [log for log in logs if boundary is not None and log["id"] >= boundary]
    window_states = _read_window_states(window)
    # Gate D-2 U7: only a card converted by the approved U5 path (same predicate the
    # U6 queue serves with) may take its first FSRS review without an engine state.
    # Everything else with history but no state stays refused (fail closed).
    converted = state is None and is_converted_incomplete(card)
    # Gate D-2 U8 plan B: a converted card that still carries an old boundary may only
    # take its first review under a valid restart permission (re-conversion snapshot).
    restart = None
    if converted and boundary is not None:
        restart = restoration.restart_permission(connection, key, card, logs)
        if restart is None:
            raise SrsWriteError("evidence_restart_not_permitted")
    if state is None and not converted and (card["last_reviewed_at"] is not None or logs
                                            or card.get("srs_history_quality") == "incomplete"):
        raise SrsWriteError("history_initialization_requires_approval")
    at = to_utc(now_utc())
    if state is not None and at < state.last_review_at:
        raise SrsWriteError("server_clock_before_last_review")
    timestamp = at.isoformat()
    ensure_config(connection, timestamp)
    # H3-a: a converted card enters the fixed engine with no state, so the library's
    # own first review applies (no stability from legacy levels or elapsed time).
    outcome = review(key, state, rating, at)
    if restart is not None:
        # New window: this review is its only evidence. The old window, legacy reviews
        # after the rollback and the old state are never handed to the completion check.
        complete, events = True, []
    elif converted or boundary is not None:
        # Gate D-2 U7 (D-H4): completion evidence of a converted card starts at its
        # first real FSRS review. Legacy logs before it never count (success dates,
        # gaps, Again), and the window's own history must be a verified chain whose
        # every log is explained by the fixed engine (U7 fix P1).
        complete = _evidence_window_consistent(key, window, window_states, boundary, state, connection,
                                               card["srs_card_version"])
        # An inconsistent window is incomplete evidence: its records are not handed to
        # the completion function (no proof is drawn from them, and their order is not
        # trusted); only this review's own event is.
        events = ([ReviewEvent(goals.read_utc(log["event_at"]), log["rating"])
                   for log in sorted(window, key=lambda log: log["id"])] if complete else [])
    else:
        # Gate D-2 U11 fix: a card with no evidence boundary (FSRS from its first review,
        # or converted from a complete legacy history) is complete evidence only when its
        # own logs are a verified chain from its start to the version reviewed now. The
        # 'fresh' / 'complete' mark alone never is.
        complete = card["srs_history_quality"] in ("complete", "fresh") and _plain_history_consistent(
            key, card, state, logs, times, connection)
        # Real chronological order (UTC instants, then log id), not string order.
        ordered = sorted(zip(times, logs), key=lambda pair: (pair[0], pair[1]["id"]))
        events = [ReviewEvent(time, log["rating"]) for time, log in ordered] if complete else []
    events.append(ReviewEvent(at, rating))
    check = evaluate_completion(outcome.after, events, evidence_complete=complete)
    # Gate D-2 U11 B: current judgement, first completion of any version (+ its source,
    # fixed once) and this version's first completion; no stored time is parsed to
    # decide, so a damaged old value never fails the review.
    record = completion_update(card, check, at)
    level, legacy_due = compute_review_schedule(rating, int(card["review_level"]), at)
    due = outcome.after.due_at.isoformat()
    values = state_columns(outcome.after)
    values.update(srs_config_version=outcome.config_version, srs_effective_due_at=due,
                  next_review_at=due, last_reviewed_at=timestamp, updated_at=timestamp,
                  review_level=level, correct_count=card["correct_count"] + (rating != "again"),
                  wrong_count=card["wrong_count"] + (rating == "again"), **record.values)
    update_card(connection, key, expected_card_version, values)
    shared = (key.user_id, key.ref_id, shared_deck_id, rating, card["review_level"], level,
              card["next_review_at"], due, card["status"], card["status"], timestamp)
    metadata = (request_id, "fsrs", outcome.config_version, expected_card_version,
                state_to_json(state), state_to_json(outcome.after), seoul_date(at).isoformat(), int(state is None))
    if key.kind == "personal":
        cursor = connection.execute(
            "INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, previous_review_level, "
            "next_review_level, previous_next_review_at, next_review_at, response_time_ms, request_id, srs_engine, "
            "srs_config_version, card_version_before, srs_before_json, srs_after_json, seoul_date, is_first_review) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (key.user_id, key.ref_id, card["deck_id"], rating, timestamp, card["review_level"], level,
             card["next_review_at"], due, response_time_ms, *metadata),
        )
    else:
        cursor = connection.execute(
            "INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
            "new_review_level, previous_next_review_at, new_next_review_at, previous_status, new_status, created_at, "
            "request_id, srs_engine, srs_config_version, card_version_before, srs_before_json, srs_after_json, "
            "seoul_date, is_first_review) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (*shared, *metadata),
        )
    log_id = cursor.fetchone()["id"]
    if restart is not None:
        _restart_evidence_boundary(connection, key, log_id, restart, expected_card_version, timestamp)
    elif converted:
        _record_evidence_boundary(connection, key, log_id)
    introduced = introduced_on(connection, key.user_id, at)
    # Gate D-2 U9 (D-P3a): the response is built field by field from this review's
    # results -- no card or progress row is copied, so no surface, reading, meaning,
    # example, context, source text, deck name or classification is in it.
    result = dict(card_kind=key.kind, card_id=key.ref_id, rating=rating,
                  correct_count=values["correct_count"], wrong_count=values["wrong_count"],
                  review_level=level, next_review_at=due, last_reviewed_at=timestamp)
    result.update(request_id=request_id, accepted_at=timestamp, server_now=timestamp,
                  completed=(None if check.status is CompletionStatus.UNKNOWN else check.status is CompletionStatus.COMPLETED),
                  completion_metric_version=check.metric_version,
                  srs={"state": state_to_dict(outcome.after), "card_version": expected_card_version + 1,
                       "config_version": outcome.config_version, "effective_due_at": due,
                       "completion_status": check.status.value, "needs_relearning": record.needs_relearning,
                       "first_completed_at": record.current_first_completed_at, **introduced.as_dict(),
                       "legacy_projection_due_at": legacy_due})
    if connection.execute("SELECT 1 FROM srs_review_receipts WHERE user_id = ? AND request_id = ?",
                          (key.user_id, request_id)).fetchone() is not None:
        # An expired receipt still holds this request id: a different request reusing it
        # (it passed the card checks) is a conflict, never a second receipt. Raising
        # rolls back the whole review.
        raise SrsWriteError("request_id_conflict")
    connection.execute(
        "INSERT INTO srs_review_receipts (user_id, request_id, card_kind, card_ref, request_hash, response_json, "
        "review_log_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key.user_id, request_id, key.kind, key.ref_id,
         request_hash(key, rating, request_id, hashed_version, session_id, shared_deck_id, response_time_ms),
         receipts.canonical_json(result), log_id, timestamp),
    )
    return result


def _read_window_states(window: list[dict[str, Any]]) -> dict[int, tuple[Any, Any]]:
    """Parses the engine snapshots of the evidence-window FSRS logs. Callers check
    readability.history_unreadable first, so every snapshot here parses; the 409 below
    is only a guard. (Readable but disagreeing records are judged later as incomplete
    evidence.)"""
    states: dict[int, tuple[Any, Any]] = {}
    for log in window:
        if log["srs_engine"] != "fsrs":
            continue  # a legacy log has no snapshot; its presence makes the window inconsistent
        try:
            states[log["id"]] = (state_from_json(log["srs_before_json"]), state_from_json(log["srs_after_json"]))
        except SrsEngineError:
            raise SrsWriteError("review_history_unreadable") from None
    return states


def _evidence_window_consistent(key: CardKey, window: list[dict[str, Any]],
                                states: dict[int, tuple[Any, Any]], boundary: int | None, state: Any,
                                connection: Any, card_version: int) -> bool:
    """True only when the logs since the evidence boundary are exactly the FSRS
    reviews that produced the card's current state:

    - the first is the boundary log and started from no state;
    - every log is an FSRS log under the current config, in time order, and each next
      one starts from the previous one's result with the next card version;
    - every log is explained by the fixed engine (U7 fix P1): its own time equals the
      last-review time of its stored result (same UTC instant; spelling may differ),
      and re-running the engine on (stored before-state, rating, time) gives exactly
      the stored after-state;
    - the last result is the card's current state.

    The only allowed gap in card versions between two window logs (U8 fix P1) is one
    that this card's own completed rollback record and restoring re-conversion
    snapshot prove, step by step (restoration.proven_jump). Any other gap is
    incomplete evidence; versions in the logs are never rewritten.

    The same applies after the last log (U8 remaining P1): the version that last log
    left (its card_version_before + 1) must be the card version this review is made
    against, or the difference must be proven by the same rule. With no log yet (the
    U7 first review) there is no last log and nothing to compare.

    Anything else -> incomplete evidence (never a completion). Nothing is repaired. A
    first review (no boundary yet) has an empty, valid window."""
    if boundary is None:
        return not window and state is None
    window = sorted(window, key=lambda log: log["id"])
    if not window or window[0]["id"] != boundary:
        return False
    previous_after, previous_version, previous_at, previous_id = None, None, None, None
    for index, log in enumerate(window):
        at = goals.read_utc(log["event_at"])
        version = log["card_version_before"]
        if (log["srs_engine"] != "fsrs" or log["srs_config_version"] != DEFAULT_CONFIG.config_version
                or at is None or (previous_at is not None and at < previous_at)
                or not isinstance(version, int) or isinstance(version, bool)):
            return False
        before, after = states[log["id"]]  # FSRS logs only (checked above)
        if index == 0:
            if before is not None:
                return False
        elif before != previous_after:
            return False
        elif version != previous_version + 1 and not restoration.proven_jump(
                connection, key, previous_id, previous_after, previous_version + 1, version):
            return False
        if after is None or after.last_review_at != at:
            return False
        try:
            replayed = review(key, before, log["rating"], at).after
        except SrsEngineError:
            return False  # readable record the engine rejects: not an explained transition
        if replayed != after:
            return False
        previous_after, previous_version, previous_at, previous_id = after, version, at, log["id"]
    if previous_after != state:
        return False
    # The tail: from the version the last log left to the version being reviewed now.
    return card_version == previous_version + 1 or restoration.proven_jump(
        connection, key, previous_id, previous_after, previous_version + 1, card_version)


def _parsed_states(log: dict[str, Any]) -> tuple[Any, Any] | None:
    """A log's engine snapshots, or None when they cannot be parsed (outside an evidence
    window that is incomplete evidence, never a refusal: readability is unchanged)."""
    try:
        return state_from_json(log["srs_before_json"]), state_from_json(log["srs_after_json"])
    except SrsEngineError:
        return None


def _conversion_start(connection: Any, key: CardKey) -> tuple[Any, int, int] | None:
    """The start of a card converted from a complete history: the card's FIRST apply
    record. Returns (engine state it wrote, card version it left, last log id it was
    computed from), or None when that record cannot serve as a start."""
    row = connection.execute(
        "SELECT s.card_version_before, s.legacy_json, s.srs_after_json FROM srs_migration_snapshots AS s "
        "JOIN srs_migration_runs AS r ON r.id = s.run_id WHERE r.mode = 'apply' AND s.user_id = ? "
        "AND s.card_kind = ? AND s.card_ref = ? ORDER BY s.id LIMIT 1", (key.user_id, key.kind, key.ref_id),
    ).fetchone()
    if row is None:
        return None
    try:
        payload, values = json.loads(row["legacy_json"]), json.loads(row["srs_after_json"])
        if (not isinstance(payload, dict) or not isinstance(values, dict) or values.get("srs_engine") != "fsrs"
                or values.get("srs_config_version") != DEFAULT_CONFIG.config_version
                or values.get("srs_history_quality") not in ("complete", "fresh")):
            return None
        last_log_id, version = payload.get("last_log_id"), row["card_version_before"]
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in (last_log_id, version)):
            return None
        return load_state(values), version + 1, last_log_id
    except (TypeError, ValueError, KeyError, RecursionError, SrsWriteError, SrsEngineError):
        return None


def _plain_history_consistent(key: CardKey, card: dict[str, Any], state: Any, logs: list[dict[str, Any]],
                              times: list[Any], connection: Any) -> bool:
    """Gate D-2 U11 fix: may a card WITHOUT an evidence boundary hand its whole history
    to the completion check? Only when it is explained from the card's own start:

    - FSRS from its first review (a new personal card in an FSRS account, or a
      subscribed word whose progress row its first review created): starts with no
      state at card version 0, and every log is an FSRS log;
    - converted from a complete (or fresh) legacy history: starts at its first apply
      record. The logs that record was computed from (id <= its last_log_id) must
      still replay through the fixed engine to exactly the state it wrote, and every
      later log is an FSRS log.
    From the start, the FSRS logs must form the same verified chain as an evidence
    window (_fsrs_chain_consistent), up to the card version reviewed now. A version
    jump counts only when restoration.proven_jump proves it. Anything else is
    incomplete evidence; nothing is repaired or re-based, and the review is recorded."""
    by_id = sorted(logs, key=lambda log: log["id"])
    born_fsrs = all(log["srs_engine"] == "fsrs" for log in by_id) and (
        (state is None and card["srs_card_version"] == 0) if not by_id else
        (by_id[0]["card_version_before"] == 0 and (_parsed_states(by_id[0]) or (0, 0))[0] is None))
    if born_fsrs:
        # Versions only grow and a conversion leaves version >= 1, so a chain that starts
        # at version 0 with no state has no conversion start to look up.
        return _fsrs_chain_consistent(key, by_id, None, 0, 0, state, connection, card["srs_card_version"])
    start = _conversion_start(connection, key)
    if start is None:
        return False
    start_state, start_version, last_log_id = start
    history = [(time, log) for time, log in zip(times, logs) if log["id"] <= last_log_id]
    replayed = None
    try:
        for time, log in sorted(history, key=lambda pair: (pair[0], pair[1]["id"])):
            replayed = review(key, replayed, log["rating"], time).after
    except SrsEngineError:
        return False
    if replayed != start_state:
        return False
    return _fsrs_chain_consistent(key, [log for log in by_id if log["id"] > last_log_id], start_state, start_version,
                                  last_log_id, state, connection, card["srs_card_version"])


def _fsrs_chain_consistent(key: CardKey, chain: list[dict[str, Any]], start_state: Any, start_version: int,
                           start_log_id: int, state: Any, connection: Any, card_version: int) -> bool:
    """The FSRS logs after a known start (state, the card version it left, the last log
    id before it), in id order: each is an FSRS log under the current config, in time
    order, starts from the previous result at the next card version (or a jump
    restoration.proven_jump proves), and is explained by the fixed engine; the last
    result is the card's state, and the card version reviewed now follows the last log
    (or a proven jump). Log ids are per table, shared by every card: only order is used."""
    previous_after, version_left, previous_at, previous_id = start_state, start_version, None, start_log_id
    for log in chain:
        at = goals.read_utc(log["event_at"])
        version = log["card_version_before"]
        states = _parsed_states(log)
        if (log["srs_engine"] != "fsrs" or log["srs_config_version"] != DEFAULT_CONFIG.config_version
                or at is None or (previous_at is not None and at < previous_at) or states is None
                or not isinstance(version, int) or isinstance(version, bool)):
            return False
        before, after = states
        if before != previous_after:
            return False
        if version != version_left and not restoration.proven_jump(
                connection, key, previous_id, previous_after, version_left, version):
            return False
        if after is None or after.last_review_at != at:
            return False
        try:
            replayed = review(key, before, log["rating"], at).after
        except SrsEngineError:
            return False
        if replayed != after:
            return False
        previous_after, version_left, previous_at, previous_id = after, version + 1, at, log["id"]
    if previous_after != state:
        return False
    return card_version == version_left or restoration.proven_jump(
        connection, key, previous_id, previous_after, version_left, card_version)


def _check_own_log(connection: Any, key: CardKey, log_id: int) -> None:
    table, ref = ("review_logs", "vocab_item_id") if key.kind == "personal" else ("lexeme_review_logs", "lexeme_id")
    row = connection.execute(f"SELECT user_id, {ref} AS ref FROM {table} WHERE id = ?", (log_id,)).fetchone()
    if row is None or int(row["user_id"]) != key.user_id or int(row["ref"]) != key.ref_id:
        raise SrsWriteError("evidence_boundary_mismatch")


def _restart_evidence_boundary(connection: Any, key: CardKey, log_id: int, restart: dict[str, Any],
                               card_version_before: int, timestamp: str) -> None:
    """Gate D-2 U8 plan B, in the review's transaction: the boundary moves from the old
    value to this review's own log by CAS on the old value, and the move is recorded
    once per permission (source_snapshot_id UNIQUE). Any failure aborts the review."""
    _check_own_log(connection, key, log_id)
    card_table, where, params = card_location(key)
    cursor = connection.execute(
        f"UPDATE {card_table} SET evidence_from_log_id = ? WHERE {where} AND evidence_from_log_id = ?",
        (log_id, *params, restart["previous_boundary"]))
    if cursor.rowcount != 1:
        raise SrsWriteError("evidence_boundary_conflict")
    if connection.execute("SELECT 1 FROM srs_evidence_restarts WHERE source_snapshot_id = ?",
                          (restart["snapshot_id"],)).fetchone() is not None:
        raise SrsWriteError("evidence_restart_not_permitted")
    connection.execute(
        "INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, previous_boundary, "
        "new_boundary, card_version_before, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (key.user_id, key.kind, key.ref_id, restart["snapshot_id"], restart["previous_boundary"], log_id,
         card_version_before, timestamp))


def _record_evidence_boundary(connection: Any, key: CardKey, log_id: int) -> None:
    """Stores the first real FSRS review log of a converted card as the start of its
    completion evidence, in the review's transaction. Checks the log is this card's
    (same account and card) and never overwrites an existing boundary."""
    table, ref = ("review_logs", "vocab_item_id") if key.kind == "personal" else ("lexeme_review_logs", "lexeme_id")
    row = connection.execute(f"SELECT user_id, {ref} AS ref FROM {table} WHERE id = ?", (log_id,)).fetchone()
    if row is None or int(row["user_id"]) != key.user_id or int(row["ref"]) != key.ref_id:
        raise SrsWriteError("evidence_boundary_mismatch")
    card_table, where, params = card_location(key)
    cursor = connection.execute(
        f"UPDATE {card_table} SET evidence_from_log_id = ? WHERE {where} AND evidence_from_log_id IS NULL",
        (log_id, *params))
    if cursor.rowcount != 1:
        raise SrsWriteError("evidence_boundary_conflict")


def record_first_lexeme_review(connection: Any, key: CardKey, rating: str, request_id: str | None,
                               session_id: str | None, shared_deck_id: int | None) -> dict[str, Any]:
    """Subscribed word without a progress row, rated with an explicit
    `expected_card_version: null` (gate-c2 CONTRACT 3-2). Runs inside the
    caller's account-locked transaction, before any legacy lazy creation.

    Order: rating -> current access -> receipt (original null payload) ->
    account mode -> row absent -> create fresh FSRS progress -> FSRS review
    with internal CAS 0. Any failure rolls back the created row as well."""
    from app.srs.storage import account_uses_fsrs, fresh_fsrs_values, load_card

    if rating not in RATINGS:
        raise SrsWriteError("invalid_review_rating", 400)
    require_subscription(connection, key, shared_deck_id)
    validate_first_review_request(request_id, session_id)
    receipt = find_receipt(connection, key, rating, request_id, None, session_id, shared_deck_id, None,
                           first_review=True)
    if receipt is not None:
        return receipt
    if not account_uses_fsrs(connection, key.user_id):
        raise SrsWriteError("srs_mode_not_fsrs", 409)
    if load_card(connection, key) is not None:
        # Another window created it first, or a legacy row exists. Never re-rate.
        raise SrsWriteError("card_version_conflict")
    timestamp = to_utc(now_utc()).isoformat()
    values = fresh_fsrs_values()
    columns = ["user_id", "lexeme_id", "status", "review_level", "correct_count", "wrong_count",
               "created_at", "updated_at", *values]
    connection.execute(
        f"INSERT INTO user_word_progress ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        (key.user_id, key.ref_id, "unclassified", 0, 0, 0, timestamp, timestamp, *values.values()),
    )
    card = load_card(connection, key, for_update=True)
    return record_fsrs_review(connection, key, card, rating, request_id, 0, session_id, shared_deck_id,
                              receipt_version=None, receipt_version_given=True)
