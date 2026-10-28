"""Read-only unified study queue: GET /study-queue (Gate C-1, extended in C-2a).

Contracts: docs/plans/srs-improvement/gate-c1/CONTRACT.md v0.2 (+7),
gate-c2/CONTRACT.md v0.2 (exclude_card 2-3, mode=selected 4-3, materialization 3-2).

- FSRS-mode accounts only; everything else keeps the legacy URLs.
- Never writes: no settings, cards, progress, logs, receipts or goal events.
  All reads of one response run in a single read transaction so the list,
  the category counts and the goal numbers come from one database state.
- Authorization, subscription membership and lexeme de-duplication happen in
  SQL; classification, global ordering and LIMIT happen afterwards on the
  whole scope, so a broken card can never shorten a page or hide others.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from app.database import get_connection, is_postgres_connection, now_utc
from app.srs import goals, history_intro, identity, readability
from app.srs import queue_cursor as cursors
from app.srs.completion import seoul_date
from app.srs.goals import read_utc
from app.srs.engine import DEFAULT_CONFIG, ENGINE_NAME, SrsPhase
from app.srs.queue_cursor import canonical_utc
from app.srs.storage import SrsWriteError, is_converted_incomplete, load_state

SCOPES = ("all", "personal_deck", "subscribed_deck")
MODES = ("today", "new", "practice", "selected")
STATUSES = ("known", "uncertain", "unclassified", "unknown")
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_DECK_ID = 2**31 - 1
SINGLE_PARAMS = ("scope", "deck_id", "mode", "limit", "cursor", "plan_daily_new")
MAX_EXCLUDED = 100       # gate-c2 2-3: more is refused, never truncated
MAX_SELECTED = 200       # gate-c2 4-3: recent ids per request
_EXCLUDE_KEY = re.compile(r"^(personal|lexeme):([1-9][0-9]{0,18})$")
# gate-c2 3-2: subscribed words without progress are served as new cards only
# because the atomic first-review path (expected_card_version: null) exists.
SERVE_UNMATERIALIZED = True

# Mutually exclusive; checked in this order (contract section 3).
CATEGORIES = (
    "new_unmaterialized", "not_converted", "unsupported_config", "invalid_state", "paused",
    "blocked_history", "missing_due", "learning_due", "relearning_due", "review_due",
    "pending_later", "new_available",
)
DUE_BUCKET = {"learning_due": 0, "relearning_due": 0, "review_due": 1}
NEW_CATEGORIES = ("new_available", "new_unmaterialized")
# Categories an exclusion can affect (served now or waiting); counted as excluded_by_request.
EXCLUDABLE = ("learning_due", "relearning_due", "review_due", "pending_later") + NEW_CATEGORIES
PRACTICE_CATEGORIES = ("learning_due", "relearning_due", "review_due", "pending_later")
KIND_RANK = {"personal": 0, "lexeme": 1}
BUCKET_NAMES = {0: "short_due", 1: "review_due", 2: "new"}


class QueueError(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class QueueRequest:
    user_id: int
    scope: str
    deck_id: int | None
    mode: str
    statuses: tuple[str, ...]
    limit: int
    plan_daily_new: int | None
    cursor: str | None
    excluded: tuple[tuple[str, int], ...] = ()
    selected: tuple[int, ...] = ()

    @property
    def filters_hash(self) -> str:
        """Binds a cursor to the exact exclusion and selection sets."""
        raw = json.dumps({"excluded": [list(k) for k in self.excluded], "selected": list(self.selected)},
                         separators=(",", ":"))
        return hashlib.sha256(raw.encode("ascii")).hexdigest()[:32]


def _now() -> datetime:
    # One request-time clock read; tests patch this.
    return now_utc()


def _strict_int(raw: str, low: int, high: int, code: str) -> int:
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        raise QueueError(400, code)
    value = int(raw)
    if not low <= value <= high:
        raise QueueError(400, code)
    return value


def parse_request(user_id: int, items: Iterable[tuple[str, str]]) -> QueueRequest:
    """Validates raw query parameters. Unknown parameters are ignored, as
    elsewhere in this API, except extra_new which is refused explicitly."""
    values: dict[str, list[str]] = {}
    for name, value in items:
        values.setdefault(name, []).append(value)
    if "extra_new" in values:
        raise QueueError(400, "unsupported_parameter")
    for name in SINGLE_PARAMS:
        if len(values.get(name, [])) > 1:
            raise QueueError(400, f"duplicate {name}")
    one = {name: values[name][0] for name in SINGLE_PARAMS if name in values}

    scope = one.get("scope", "all")
    if scope not in SCOPES:
        raise QueueError(400, "invalid scope")
    deck_id = None
    if "deck_id" in one:
        if scope == "all":
            raise QueueError(400, "deck_id not allowed for scope all")
        deck_id = _strict_int(one["deck_id"], 1, MAX_DECK_ID, "invalid deck_id")
    elif scope != "all":
        raise QueueError(400, "deck_id required")
    mode = one.get("mode", "today")
    if mode not in MODES:
        raise QueueError(400, "invalid mode")
    raw_status = values.get("status", [])
    if raw_status and mode != "practice":
        raise QueueError(400, "status requires practice")
    if any(status not in STATUSES for status in raw_status) or len(raw_status) > len(STATUSES) * 2:
        raise QueueError(400, "invalid status")
    statuses = tuple(sorted(set(raw_status)))
    limit = _strict_int(one["limit"], 1, MAX_LIMIT, "invalid limit") if "limit" in one else DEFAULT_LIMIT
    plan = None
    if "plan_daily_new" in one:
        if scope == "all":
            raise QueueError(400, "plan_daily_new requires a deck scope")
        if mode == "practice":
            raise QueueError(400, "plan_daily_new not allowed for practice")
        plan = _strict_int(one["plan_daily_new"], 0, 500, "invalid plan_daily_new")
    cursor = one.get("cursor")
    if cursor is not None and cursor == "":
        raise QueueError(400, "invalid_cursor")

    raw_excluded = values.get("exclude_card", [])
    if len(raw_excluded) > MAX_EXCLUDED * 2:
        raise QueueError(400, "too_many_excluded_cards")
    excluded_set: set[tuple[str, int]] = set()
    for raw in raw_excluded:
        match = _EXCLUDE_KEY.fullmatch(raw) if isinstance(raw, str) and raw.isascii() else None
        if match is None or int(match.group(2)) > 2**63 - 1:
            raise QueueError(400, "invalid exclude_card")
        excluded_set.add((match.group(1), int(match.group(2))))
    if len(excluded_set) > MAX_EXCLUDED:
        # Never silently drop exclusions: the session must end instead (gate-c2 2-3).
        raise QueueError(400, "too_many_excluded_cards")
    excluded = tuple(sorted(excluded_set))

    raw_selected = values.get("card_id", [])
    if mode == "selected":
        if scope != "all":
            raise QueueError(400, "selected requires scope all")
        if not raw_selected:
            raise QueueError(400, "card_id required")
        if len(raw_selected) > MAX_SELECTED * 2:
            raise QueueError(400, "too_many_card_ids")
        selected_set = {_strict_int(raw, 1, 2**31 - 1, "invalid card_id") for raw in raw_selected}
        if len(selected_set) > MAX_SELECTED:
            raise QueueError(400, "too_many_card_ids")
        selected = tuple(sorted(selected_set))
    elif raw_selected:
        raise QueueError(400, "card_id requires selected")
    else:
        selected = ()
    return QueueRequest(user_id, scope, deck_id, mode, statuses, limit, plan, cursor, excluded, selected)


def _begin_snapshot(connection: Any) -> None:
    """One consistent read view for every statement of this response.

    SQLite: an explicit deferred BEGIN; the first SELECT takes the read lock /
    snapshot and keeps it until commit, so a concurrent review cannot commit
    in between (rollback journal) or is invisible to us (WAL).
    PostgreSQL: the read-only connection's default READ COMMITTED would give
    every statement its own snapshot, so ask for REPEATABLE READ before the
    first query. NOT executed in this gate (no local PostgreSQL)."""
    if is_postgres_connection(connection):
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    else:
        connection.execute("BEGIN")


_CARD_COLUMNS = (
    "srs_engine, srs_config_version, srs_state, srs_step, srs_stability, srs_difficulty, "
    "srs_due_at, srs_effective_due_at, srs_last_review_at, srs_card_version, srs_participation, "
    "srs_history_quality"
)


def _check_scope(connection: Any, request: QueueRequest) -> None:
    if request.scope == "personal_deck":
        row = connection.execute(
            "SELECT id FROM decks WHERE id = ? AND user_id = ?", (request.deck_id, request.user_id)
        ).fetchone()
    elif request.scope == "subscribed_deck":
        row = connection.execute(
            "SELECT id FROM user_deck_subscriptions WHERE user_id = ? AND shared_deck_id = ? AND is_active = TRUE",
            (request.user_id, request.deck_id),
        ).fetchone()
    else:
        return
    if row is None:
        raise QueueError(404, "deck not found")


def _read_personal(connection: Any, request: QueueRequest) -> list[dict[str, Any]]:
    if request.scope == "subscribed_deck":
        return []
    columns = ", ".join(f"v.{name.strip()}" for name in _CARD_COLUMNS.split(","))
    deck_clause = " AND v.deck_id = ?" if request.scope == "personal_deck" else ""
    params: tuple[Any, ...] = (request.user_id,) + ((request.deck_id,) if deck_clause else ())
    if request.mode == "selected":
        # Only the caller's own cards among the given ids; others are ignored.
        deck_clause += " AND v.id IN (" + ", ".join("?" for _ in request.selected) + ")"
        params += tuple(request.selected)
    rows = connection.execute(
        "SELECT v.id, v.deck_id, d.name AS deck_name, v.surface, v.base_form, v.reading, v.part_of_speech, "
        "v.meaning_ko, v.dictionary_gloss, v.example_sentence, v.context_explanation_ko, v.status, "
        f"v.last_reviewed_at, v.created_at, {columns}, "
        "EXISTS (SELECT 1 FROM review_logs r WHERE r.user_id = v.user_id AND r.vocab_item_id = v.id) AS has_logs "
        "FROM vocab_items v LEFT JOIN decks d ON d.id = v.deck_id "
        f"WHERE v.user_id = ?{deck_clause} ORDER BY v.id",
        params,
    ).fetchall()
    return [dict(row, kind="personal", ref_id=int(row["id"])) for row in rows]


def _read_lexemes(connection: Any, request: QueueRequest) -> list[dict[str, Any]]:
    if request.scope == "personal_deck" or request.mode == "selected":
        return []
    columns = ", ".join(f"p.{name.strip()}" for name in _CARD_COLUMNS.split(","))
    deck_clause = " AND s.shared_deck_id = ?" if request.scope == "subscribed_deck" else ""
    params: tuple[Any, ...] = (request.user_id,) + ((request.deck_id,) if deck_clause else ())
    rows = connection.execute(
        "SELECT w.shared_deck_id, w.sort_order, s.imported_at, sd.title AS deck_title, "
        "l.id AS lexeme_id, l.surface, l.base_form, l.reading, l.part_of_speech, "
        "l.meaning_ko AS lexeme_meaning_ko, l.dictionary_gloss, l.jlpt_level, "
        "w.display_meaning_ko, w.example_sentence, w.context_explanation_ko, "
        f"p.id AS progress_id, p.status, p.last_reviewed_at, {columns}, "
        "EXISTS (SELECT 1 FROM lexeme_review_logs r WHERE r.user_id = s.user_id AND r.lexeme_id = l.id) AS has_logs "
        "FROM user_deck_subscriptions s "
        "JOIN shared_deck_words w ON w.shared_deck_id = s.shared_deck_id "
        "JOIN lexemes l ON l.id = w.lexeme_id "
        "JOIN shared_decks sd ON sd.id = s.shared_deck_id "
        "LEFT JOIN user_word_progress p ON p.user_id = s.user_id AND p.lexeme_id = l.id "
        f"WHERE s.user_id = ? AND s.is_active = TRUE{deck_clause} "
        "ORDER BY l.id, w.shared_deck_id",
        params,
    ).fetchall()
    cards: dict[int, dict[str, Any]] = {}
    for row in rows:
        lexeme_id = int(row["lexeme_id"])
        if lexeme_id in cards:
            continue  # same lexeme in another subscribed deck: one card, smallest deck id is the context
        cards[lexeme_id] = dict(row, kind="lexeme", ref_id=lexeme_id)
    return list(cards.values())


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def classify(card: dict[str, Any], as_of: datetime, unreadable_history: bool = False,
             identity_unknown: bool = False) -> tuple[str, tuple | None, Any]:
    """(category, sort key or None, engine state). Pure; never raises for bad data.
    `unreadable_history`: one of the card's own log times cannot be read, so its
    first-review date and completion evidence are unknown -> invalid_state.
    `identity_unknown` (Gate D-2 U3 correction): the personal card's id is flagged
    because its stored history may belong to another card -> blocked_history,
    whatever its engine state. Never served, never "due now"."""
    kind = card["kind"]
    if identity_unknown and kind == "personal":
        return "blocked_history", None, None
    if kind == "lexeme" and card["progress_id"] is None:
        # Served as a new card (card_version null) only when it has no history
        # and a valid context-deck order; still counted here either way.
        new_time = canonical_utc(card["imported_at"])
        seq = card["sort_order"]
        if (not SERVE_UNMATERIALIZED or unreadable_history or bool(card["has_logs"])
                or new_time is None or not _is_int(seq) or seq < -(2**31)):
            return "new_unmaterialized", None, None
        return "new_unmaterialized", (2, new_time, KIND_RANK[kind], seq, card["ref_id"]), None
    if card["srs_engine"] != "fsrs":
        return "not_converted", None, None
    if card["srs_config_version"] != DEFAULT_CONFIG.config_version:
        return "unsupported_config", None, None
    if unreadable_history or card["srs_participation"] not in ("active", "paused") \
            or not _is_int(card["srs_card_version"]) or card["srs_card_version"] < 0:
        return "invalid_state", None, None
    try:
        state = load_state(card)
    except SrsWriteError:
        return "invalid_state", None, None
    if state is None and is_converted_incomplete(card):
        return _classify_converted_incomplete(card, as_of)
    effective = None
    if state is not None:
        if canonical_utc(card["srs_due_at"]) is None or canonical_utc(card["srs_last_review_at"]) is None:
            return "invalid_state", None, None
        if card["srs_effective_due_at"] is not None:
            effective = canonical_utc(card["srs_effective_due_at"])
            if effective is None:
                return "invalid_state", None, None
        new_time, seq = None, 0
    else:
        new_time = canonical_utc(card["created_at"] if kind == "personal" else card["imported_at"])
        seq = 0 if kind == "personal" else card["sort_order"]
        if new_time is None or not _is_int(seq) or seq < -(2**31):
            return "invalid_state", None, None
    if card["srs_participation"] == "paused":
        return "paused", None, state
    rank, ref = KIND_RANK[kind], card["ref_id"]
    if state is None:
        if card["last_reviewed_at"] is not None or bool(card["has_logs"]):
            return "blocked_history", None, None
        return "new_available", (2, new_time, rank, seq, ref), None
    if effective is None:
        return "missing_due", None, state
    if effective > as_of:
        return "pending_later", (0, effective, rank, 0, ref), state
    category = {SrsPhase.LEARNING: "learning_due", SrsPhase.RELEARNING: "relearning_due",
                SrsPhase.REVIEW: "review_due"}[state.phase]
    return category, (DUE_BUCKET[category], effective, rank, 0, ref), state


def _classify_converted_incomplete(card: dict[str, Any], as_of: datetime) -> tuple[str, tuple | None, Any]:
    """Gate D-2 U6 (D-H2): a card converted by the U5 migration path -- FSRS engine,
    current config, valid participation and card version (checked by the caller),
    no engine state, srs_history_quality 'incomplete' (only migration._incomplete_candidate
    writes that value; new FSRS cards are 'fresh', rollback restores the legacy value).

    It is never new and never counts against the new-word goal. Paused (legacy known)
    stays paused. Its schedule is the existing effective due copied by U5, read as a
    real instant in any UTC offset: before it -> pending_later, from it -> review_due
    (the long-term review bucket). No engine phase, stability or difficulty is assumed;
    a missing due stays missing_due and an unreadable one invalid_state. Rating it is
    still refused until U7 (reviews.history_initialization_requires_approval)."""
    if card["srs_participation"] == "paused":
        return "paused", None, None
    raw = card["srs_effective_due_at"]
    if raw is None:
        return "missing_due", None, None
    effective = read_utc(raw)
    if effective is None:
        return "invalid_state", None, None
    rank, ref = KIND_RANK[card["kind"]], card["ref_id"]
    if effective > as_of:
        return "pending_later", (0, effective, rank, 0, ref), None
    return "review_due", (DUE_BUCKET["review_due"], effective, rank, 0, ref), None


def personal_due_now_ids(connection: Any, user_id: int, deck_id: int | None, as_of: datetime) -> set[int]:
    """Personal cards this queue would serve as due now (learning/relearning/review due),
    by the same classify() and one account-wide log read (Gate D-1 correction: the vocab
    tab's FSRS "지금 복습" filter). Reads only; damaged cards stay where classify() puts them."""
    request = QueueRequest(user_id, "all" if deck_id is None else "personal_deck", deck_id,
                           "today", (), 1, None, None)
    cards = _read_personal(connection, request)
    # Same readability rule as the review path (U7 follow-up): unreadable -> invalid_state.
    unreadable = ({key for key, first in goals.first_review_dates(connection, user_id).items() if first is None}
                  | readability.unreadable_history_keys(connection, user_id))
    flagged = identity.flagged_personal_ids(connection, user_id)
    return {card["ref_id"] for card in cards
            if classify(card, as_of, (card["kind"], card["ref_id"]) in unreadable,
                        card["kind"] == "personal" and card["ref_id"] in flagged)[0] in DUE_BUCKET}


def _key_json(key: tuple) -> list[Any]:
    return [key[0], key[1].isoformat(), key[2], key[3], key[4]]


def _key_from_json(raw: list[Any]) -> tuple:
    return (raw[0], canonical_utc(raw[1]), raw[2], raw[3], raw[4])


def _item(card: dict[str, Any], category: str, key: tuple, state: Any, practice: bool) -> dict[str, Any]:
    personal = card["kind"] == "personal"
    if personal:
        review = {"method": "POST", "path": f"/study-items/{card['ref_id']}/review", "shared_deck_id": None}
        meaning, source = card["meaning_ko"] or "", card["deck_name"] or "단어장"
        jlpt = None
    else:
        deck = int(card["shared_deck_id"])
        review = {"method": "POST", "path": f"/shared-decks/{deck}/words/{card['ref_id']}/review",
                  "shared_deck_id": deck}
        meaning = card["display_meaning_ko"] or card["lexeme_meaning_ko"] or ""
        source, jlpt = card["deck_title"] or "가져온 덱", card["jlpt_level"]
    return {
        "card_kind": card["kind"],
        "card_id": card["ref_id"],
        "card_version": None if category == "new_unmaterialized" else int(card["srs_card_version"]),
        "materialized": category != "new_unmaterialized",
        "bucket": "practice" if practice else BUCKET_NAMES[key[0]],
        "sort_key": _key_json(key),
        "srs": None if state is None else {
            "phase": state.phase.value, "step": state.step, "due_at": card["srs_due_at"],
            "effective_due_at": card["srs_effective_due_at"], "last_review_at": card["srs_last_review_at"],
        },
        "config_version": card["srs_config_version"] if category != "new_unmaterialized" else None,
        "is_new": category in NEW_CATEGORIES,
        "practice_only": practice,
        "status": card["status"] or "unclassified",
        "participation": card["srs_participation"] if category != "new_unmaterialized" else None,
        "review": None if practice else review,
        "content": {
            "surface": card["surface"], "base_form": card["base_form"], "reading": card["reading"],
            "part_of_speech": card["part_of_speech"], "meaning_ko": meaning,
            "dictionary_gloss": card["dictionary_gloss"], "example_sentence": card["example_sentence"],
            "context_explanation_ko": card["context_explanation_ko"], "jlpt_level": jlpt,
        },
        "source_label": source,
    }


def build_queue(request: QueueRequest) -> dict[str, Any]:
    now = _now()
    today = seoul_date(now)
    with get_connection(read_only=True) as connection:
        _begin_snapshot(connection)
        settings = goals.account_goal(connection, request.user_id)
        if settings is None or settings["srs_mode"] != "fsrs":
            raise QueueError(409, "srs_mode_not_fsrs")
        payload = None
        if request.cursor is not None:
            try:
                payload = cursors.decode(request.cursor)
            except cursors.CursorInvalid:
                raise QueueError(400, "invalid_cursor") from None
        _check_scope(connection, request)
        cards = _read_personal(connection, request) + _read_lexemes(connection, request)
        scope_keys = {(card["kind"], card["ref_id"]) for card in cards}

        # New-goal counts from the same read: every log time parsed as a real
        # instant; a card with an unreadable time has an unknown first date.
        dates = goals.first_review_dates(connection, request.user_id)
        # Cards the review path would refuse as unreadable history (log time, rating, or
        # evidence-window snapshot; app/srs/readability.py) are not served: invalid_state,
        # decided here before ordering and LIMIT. New-word counting keeps using `dates`.
        unreadable = ({key for key, first in dates.items() if first is None}
                      | readability.unreadable_history_keys(connection, request.user_id))
        flagged = identity.flagged_personal_ids(connection, request.user_id)
        identity_days = identity.identity_unknown_days(connection, request.user_id)
        evidence = history_intro.intro_evidence(connection, request.user_id)
        account_count = goals.count_introduced(dates, now, identity_days=identity_days, intro_evidence=evidence)
        scope_count = (goals.count_introduced(dates, now, scope_keys, identity_days, evidence)
                       if request.scope != "all" else None)

        goal_basis = {"account_daily_goal": int(settings["daily_new_goal"]),
                      "settings_version": int(settings["settings_version"]),
                      "plan_daily_new": request.plan_daily_new,
                      "account_introduced_status": account_count.status,
                      "scope_introduced_status": scope_count.status if scope_count else None}
        binding = {"uid": request.user_id, "scope": request.scope, "deck_id": request.deck_id,
                   "mode": request.mode, "status": list(request.statuses),
                   "config_version": DEFAULT_CONFIG.config_version, "seoul_date": today.isoformat(),
                   "goal_basis": goal_basis, "filters_hash": request.filters_hash}
        if payload is not None:
            try:
                cursors.check_binding(payload, binding, now)
            except cursors.CursorStale:
                raise QueueError(409, "cursor_stale") from None
        as_of = canonical_utc(payload["server_now0"]) if payload else now

        counts = {name: 0 for name in CATEGORIES}
        due: list[tuple[tuple, dict, str, Any]] = []
        new: list[tuple[tuple, dict, str, Any]] = []
        practice: list[tuple[tuple, dict, str, Any]] = []
        next_due = next_due_excluded = None
        excluded_count = new_candidates = 0
        excluded_keys = set(request.excluded)
        for card in cards:
            category, key, state = classify(card, as_of, (card["kind"], card["ref_id"]) in unreadable,
                                            card["kind"] == "personal" and card["ref_id"] in flagged)
            counts[category] += 1  # categories are server state: exclusions never change them
            is_new_candidate = category in NEW_CATEGORIES and key is not None
            new_candidates += is_new_candidate
            # Request exclusions (session deferrals) apply after classification,
            # before ordering and LIMIT; they create, change or count nothing else.
            if (card["kind"], card["ref_id"]) in excluded_keys:
                if category in EXCLUDABLE:
                    excluded_count += 1
                if category == "pending_later" and (next_due_excluded is None or key[1] < next_due_excluded):
                    next_due_excluded = key[1]
                continue
            if category == "pending_later":
                next_due = key[1] if next_due is None or key[1] < next_due else next_due
            if request.mode == "practice":
                if category in PRACTICE_CATEGORIES and (not request.statuses
                                                        or (card["status"] or "unclassified") in request.statuses):
                    practice.append(((0,) + key[1:], card, category, state))
            elif is_new_candidate:
                if request.mode in ("today", "new", "selected"):
                    new.append((key, card, category, state))
            elif category in DUE_BUCKET and request.mode in ("today", "selected"):
                due.append((key, card, category, state))

    account_unknown = account_count.status == goals.UNKNOWN
    scope_unknown = scope_count is not None and scope_count.status == goals.UNKNOWN
    account_remaining = None if account_unknown else max(0, goal_basis["account_daily_goal"] - account_count.count)
    plan_remaining = None
    if request.plan_daily_new is not None and not scope_unknown:
        plan_remaining = max(0, request.plan_daily_new - scope_count.count)
    # An unknown account count stops new cards even when the scope is exact;
    # an unknown scope count stops them when a plan amount depends on it.
    # Due and relearning cards are unaffected.
    new_blocked = account_unknown or (request.plan_daily_new is not None and scope_unknown)
    if request.mode == "practice" or new_blocked:
        allowed_now = 0
    else:
        # Allowance is computed on all new candidates; exclusions do not change it.
        allowed_now = min(new_candidates, account_remaining,
                          plan_remaining if plan_remaining is not None else 500)
    if payload:
        new_allowed0, new_served = payload["new_allowed0"], payload["new_served"]
        last_key = _key_from_json(payload["last_key"])
        started = payload["server_now0"]
    else:
        new_allowed0, new_served, last_key, started = allowed_now, 0, None, now.isoformat()

    def after(entry: tuple) -> bool:
        return last_key is None or entry[0] > last_key

    limit = request.limit
    if request.mode == "practice":
        pool = sorted((entry for entry in practice if after(entry)), key=lambda entry: entry[0])
        page, more, served_new = pool[:limit], len(pool) > limit, 0
    else:
        due_pool = sorted((entry for entry in due if after(entry)), key=lambda entry: entry[0])
        new_pool = sorted((entry for entry in new if after(entry)), key=lambda entry: entry[0])
        # Keyset first, then the remaining new allowance (contract 2-6-3).
        remaining_new = new_allowed0 - new_served
        new_take = new_pool[:max(0, min(limit, remaining_new))]
        page = sorted(due_pool[:limit] + new_take, key=lambda entry: entry[0])[:limit]
        served_new = sum(1 for entry in page if entry[2] in NEW_CATEGORIES)
        more = len(due_pool) + min(len(new_pool), max(0, remaining_new)) > len(page)

    next_cursor = None
    if more and page:
        next_cursor = cursors.encode({
            **binding, "v": cursors.CURSOR_VERSION, "server_now0": started, "iat": now.isoformat(),
            "new_allowed0": new_allowed0, "new_served": new_served + served_new,
            "last_key": _key_json(page[-1][0]),
        })

    counts["total_in_scope"] = len(cards)
    counts["new_allowed_now"] = allowed_now
    counts["excluded_by_request"] = excluded_count
    return {
        "server_now": now.isoformat(),
        "bucket_as_of": as_of.isoformat(),
        "seoul_date": today.isoformat(),
        "scheduler": {"engine": ENGINE_NAME, "config_version": DEFAULT_CONFIG.config_version},
        "items": [_item(card, category, key, state, request.mode == "practice")
                  for key, card, category, state in page],
        "counts": counts,
        "new_goal": {
            "account_daily_goal": goal_basis["account_daily_goal"],
            "settings_version": goal_basis["settings_version"],
            **account_count.as_dict("introduced_today"),
            "unreadable_review_time_cards": account_count.unreadable_cards,
            "account_remaining": account_remaining,
            "plan_daily_new": request.plan_daily_new,
            **(scope_count.as_dict("introduced_today_in_scope") if scope_count else
               {"introduced_today_in_scope": None, "introduced_today_in_scope_status": None,
                "introduced_today_in_scope_at_least": None}),
            "plan_remaining": plan_remaining,
            "new_blocked_reason": ("review_time_unreadable"
                                   if new_blocked and request.mode != "practice" else None),
            "chain_new_allowed": new_allowed0,
            "chain_new_served": new_served + served_new,
            "is_strict_limit": False,
        },
        "next_due_at": next_due.isoformat() if next_due else None,
        "next_due_at_excluded": next_due_excluded.isoformat() if next_due_excluded else None,
        "next_cursor": next_cursor,
    }
