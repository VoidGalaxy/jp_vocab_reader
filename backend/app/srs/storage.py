"""Shared transactional card access for reviews and explicit migrations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.database import is_postgres_connection
from app.account_write import AccountWriteError, begin_account_write
from app.srs.engine import (
    CODE_PHASES, CONFIGS_BY_VERSION, PHASE_CODES, CardKey, SrsCardState, state_from_dict, validate_state_for_config,
)


ENGINE_STATE_COLUMNS = ("srs_state", "srs_step", "srs_stability", "srs_difficulty", "srs_due_at", "srs_last_review_at")


def is_converted_incomplete(card: dict[str, Any]) -> bool:
    """Gate D-2 U6/U7: a card converted by the U5 migration path and not yet
    initialised by a first FSRS review. One predicate for the queue (serving) and
    reviews (first rating): FSRS engine, current config, valid participation and
    card version, quality 'incomplete' (written only by
    migration._incomplete_candidate; new FSRS cards are 'fresh'), and no engine
    state. Past logs or "no state" alone never qualify a card."""
    from app.srs.engine import DEFAULT_CONFIG

    version = card.get("srs_card_version")
    return (card.get("srs_engine") == "fsrs"
            and card.get("srs_config_version") == DEFAULT_CONFIG.config_version
            and card.get("srs_participation") in ("active", "paused")
            and isinstance(version, int) and not isinstance(version, bool) and version >= 0
            and card.get("srs_history_quality") == "incomplete"
            and all(card.get(name) is None for name in ENGINE_STATE_COLUMNS))


class SrsWriteError(AccountWriteError):
    def __init__(self, code: str, status_code: int = 409):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


def begin_card_write(connection: Any, user_id: int, *, recovery: Any = None) -> None:
    # Serialize the account's receipts as well as its card writes. A process
    # mutex would not protect a second worker/server. Context managers commit.
    # `recovery` (P-RB): only the recovery functions pass a grant; ordinary paths never do.
    try:
        if recovery is None:
            begin_account_write(connection, user_id)
        else:
            begin_account_write(connection, user_id, recovery=recovery)
    except AccountWriteError as error:
        raise SrsWriteError(error.code, error.status_code) from None


def card_location(key: CardKey) -> tuple[str, str, tuple[int, ...]]:
    if key.kind == "personal":
        return "vocab_items", "user_id = ? AND id = ?", (key.user_id, key.ref_id)
    return "user_word_progress", "user_id = ? AND lexeme_id = ?", (key.user_id, key.ref_id)


def load_card(connection: Any, key: CardKey, *, for_update: bool = False) -> dict[str, Any] | None:
    table, where, params = card_location(key)
    lock = " FOR UPDATE" if for_update and is_postgres_connection(connection) else ""
    row = connection.execute(f"SELECT * FROM {table} WHERE {where}" + lock, params).fetchone()
    return dict(row) if row is not None else None


def card_fingerprint(card: dict[str, Any]) -> str:
    # Includes legacy evaluations and edits, not just the new CAS version.
    return hashlib.sha256(json.dumps(card, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_state(card: dict[str, Any]) -> SrsCardState | None:
    if card["srs_state"] is None:
        if any(card[name] is not None for name in (
            "srs_step", "srs_stability", "srs_difficulty", "srs_due_at", "srs_last_review_at"
        )):
            raise SrsWriteError("incomplete_engine_state")
        return None
    try:
        state = state_from_dict({
            "phase": CODE_PHASES[card["srs_state"]].value,
            "step": card["srs_step"], "stability": card["srs_stability"],
            "difficulty": card["srs_difficulty"], "due_at": card["srs_due_at"],
            "last_review_at": card["srs_last_review_at"],
        })
        # Same rule the engine applies before reviewing (Gate C-1 correction):
        # the step must exist in the card's own config. Unknown configs are
        # rejected separately by every caller.
        config = CONFIGS_BY_VERSION.get(card.get("srs_config_version"))
        if state is not None and config is not None:
            validate_state_for_config(state, config)
        return state
    except (ValueError, KeyError, TypeError):
        raise SrsWriteError("invalid_engine_state") from None


def state_columns(state: SrsCardState | None) -> dict[str, Any]:
    return {
        "srs_state": None if state is None else PHASE_CODES[state.phase],
        "srs_step": None if state is None else state.step,
        "srs_stability": None if state is None else state.stability,
        "srs_difficulty": None if state is None else state.difficulty,
        "srs_due_at": None if state is None else state.due_at.isoformat(),
        "srs_last_review_at": None if state is None else state.last_review_at.isoformat(),
    }


def update_card(connection: Any, key: CardKey, version: int, values: dict[str, Any]) -> None:
    table, where, params = card_location(key)
    cursor = connection.execute(
        f"UPDATE {table} SET " + ", ".join(f"{name} = ?" for name in values)
        + f", srs_card_version = srs_card_version + 1 WHERE {where} AND srs_card_version = ?",
        (*values.values(), *params, version),
    )
    if cursor.rowcount != 1:
        raise SrsWriteError("card_version_conflict")


def load_logs(connection: Any, key: CardKey) -> list[dict[str, Any]]:
    table, ref, time = (
        ("review_logs", "vocab_item_id", "reviewed_at") if key.kind == "personal"
        else ("lexeme_review_logs", "lexeme_id", "created_at")
    )
    return [dict(row) for row in connection.execute(
        f"SELECT *, {time} AS event_at FROM {table} WHERE user_id = ? AND {ref} = ? ORDER BY {time}, id",
        (key.user_id, key.ref_id),
    ).fetchall()]


def require_subscription(connection: Any, key: CardKey, shared_deck_id: int | None) -> None:
    if shared_deck_id is None:
        raise SrsWriteError("subscription_required", 404)
    # Lock the subscription and membership on PostgreSQL for the whole write,
    # so revocation/removal cannot slip between the permission check and commit.
    lock = " FOR SHARE OF subscriptions, words" if is_postgres_connection(connection) else ""
    row = connection.execute(
        "SELECT subscriptions.id FROM user_deck_subscriptions AS subscriptions "
        "JOIN shared_deck_words AS words ON words.shared_deck_id = subscriptions.shared_deck_id "
        "WHERE subscriptions.user_id = ? AND subscriptions.shared_deck_id = ? "
        "AND subscriptions.is_active = TRUE AND words.lexeme_id = ?" + lock,
        (key.user_id, shared_deck_id, key.ref_id),
    ).fetchone()
    if row is None:
        raise SrsWriteError("subscription_required", 404)


# --- Gate C-2a: new cards in FSRS-mode accounts -------------------------------

def account_uses_fsrs(connection: Any, user_id: int) -> bool:
    row = connection.execute("SELECT srs_mode FROM srs_user_settings WHERE user_id = ?", (user_id,)).fetchone()
    return row is not None and row["srs_mode"] == "fsrs"


def fresh_fsrs_values() -> dict[str, Any]:
    """Initial SRS columns of a card created in an FSRS-mode account
    (gate-c2 CONTRACT 3-1): unreviewed, active (also when classified known),
    fresh history, version 0. Self-classification is not touched."""
    from app.srs.engine import DEFAULT_CONFIG

    return {
        "srs_engine": "fsrs", "srs_config_version": DEFAULT_CONFIG.config_version,
        "srs_participation": "active", "srs_pause_reason": None,
        "srs_state": None, "srs_step": None, "srs_stability": None, "srs_difficulty": None,
        "srs_due_at": None, "srs_effective_due_at": None, "srs_last_review_at": None,
        "srs_card_version": 0, "srs_history_quality": "fresh", "srs_history_flags": None,
        "completion_metric_version": None, "first_completed_at": None,
    }


def initialize_new_personal_cards(connection: Any, user_id: int, *, item_id: int | None = None,
                                  deck_id: int | None = None) -> int:
    """Called in the same transaction right after new vocab_items rows were
    inserted. Only for FSRS-mode accounts; legacy/shadow accounts keep the
    legacy defaults. Only rows that are still untouched legacy defaults are
    initialized, so an existing or reviewed card can never be rewritten."""
    if not account_uses_fsrs(connection, user_id):
        return 0
    values = fresh_fsrs_values()
    target = ("id = ?", item_id) if item_id is not None else ("deck_id = ?", deck_id)
    cursor = connection.execute(
        "UPDATE vocab_items SET " + ", ".join(f"{name} = ?" for name in values)
        + f" WHERE user_id = ? AND {target[0]} AND srs_engine = 'legacy' AND srs_card_version = 0"
        " AND last_reviewed_at IS NULL AND review_level = 0 AND correct_count = 0 AND wrong_count = 0",
        (*values.values(), user_id, target[1]),
    )
    return int(cursor.rowcount)
