from __future__ import annotations

from typing import Any

from app.database import (
    DEFAULT_DECK_NAME,
    ensure_default_deck,
    get_connection,
    now_iso,
    row_to_dict,
)
from app.schemas import DeckCreate, DeckUpdate


def list_decks() -> list[dict[str, Any]]:
    # TODO: Add user_id filtering when authentication is introduced.
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            ORDER BY id ASC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_deck(deck_id: int) -> dict[str, Any] | None:
    # TODO: Add user_id filtering when authentication is introduced.
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (deck_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_deck(deck: DeckCreate) -> tuple[dict[str, Any], bool]:
    # TODO: Add user_id ownership when authentication is introduced.
    timestamp = now_iso()
    name = deck.name.strip()
    description = deck.description.strip()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False
        cursor = connection.execute(
            """
            INSERT INTO decks (name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, description, timestamp, timestamp),
        )
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_deck(deck_id: int, deck: DeckUpdate) -> dict[str, Any] | None:
    # TODO: Add user_id ownership checks when authentication is introduced.
    existing = get_deck(deck_id)
    if not existing:
        return None

    timestamp = now_iso()
    name = deck.name.strip() if deck.name is not None else existing["name"]
    description = (
        deck.description.strip()
        if deck.description is not None
        else existing["description"]
    )
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE decks
            SET name = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, description, timestamp, deck_id),
        )
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (deck_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def delete_deck_with_items(deck_id: int) -> dict[str, int] | bool | None:
    # TODO: Add user_id ownership checks when authentication is introduced.
    with get_connection() as connection:
        default_deck_id = ensure_default_deck(connection)
        if deck_id == default_deck_id:
            return None

        existing = connection.execute(
            "SELECT id FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        if not existing:
            return False

        vocab_cursor = connection.execute(
            "DELETE FROM vocab_items WHERE deck_id = ?",
            (deck_id,),
        )
        connection.execute(
            "DELETE FROM custom_terms WHERE deck_id = ?",
            (deck_id,),
        )
        deck_cursor = connection.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
    return {
        "deleted_deck_id": deck_id,
        "deleted_vocab_count": vocab_cursor.rowcount,
        "deleted_deck_count": deck_cursor.rowcount,
    }


def get_default_deck_id() -> int:
    # TODO: Scope default decks per user when authentication is introduced.
    with get_connection() as connection:
        return ensure_default_deck(connection)
