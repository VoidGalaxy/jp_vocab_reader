from __future__ import annotations

from typing import Any

from app.account_write import begin_account_write
from app.database import (
    DEFAULT_DECK_NAME,
    get_connection,
    now_iso,
    row_to_dict,
)
from app.schemas import DeckCreate, DeckUpdate


DECK_FIELDS = "id, name, description, created_at, updated_at"


def list_decks(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {DECK_FIELDS}
            FROM decks
            WHERE user_id = ?
            ORDER BY id ASC
            """,
            (user_id,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_deck_by_id(user_id: int, deck_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {DECK_FIELDS}
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        ).fetchone()
    return row_to_dict(row) if row else None


def get_or_create_default_deck_id(user_id: int) -> int:
    timestamp = now_iso()
    with get_connection() as connection:
        begin_account_write(connection, user_id)
        row = connection.execute(
            """
            SELECT id
            FROM decks
            WHERE user_id = ?
              AND name = ?
            """,
            (user_id, DEFAULT_DECK_NAME),
        ).fetchone()
        if row:
            return int(row["id"])

        cursor = connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                DEFAULT_DECK_NAME,
                "기존 단어와 기본 저장 대상",
                timestamp,
                timestamp,
            ),
        )
    return int(cursor.lastrowid)


def create_deck(user_id: int, deck: DeckCreate) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    name = deck.name.strip()
    description = deck.description.strip()
    with get_connection() as connection:
        begin_account_write(connection, user_id)
        existing = connection.execute(
            f"""
            SELECT {DECK_FIELDS}
            FROM decks
            WHERE user_id = ?
              AND name = ?
            """,
            (user_id, name),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False
        cursor = connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, name, description, timestamp, timestamp),
        )
        row = connection.execute(
            f"""
            SELECT {DECK_FIELDS}
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (cursor.lastrowid, user_id),
        ).fetchone()
    return row_to_dict(row), True


def update_deck(
    user_id: int, deck_id: int, deck: DeckUpdate
) -> dict[str, Any] | None:
    existing = get_deck_by_id(user_id, deck_id)
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
        begin_account_write(connection, user_id)
        connection.execute(
            """
            UPDATE decks
            SET name = ?, description = ?, updated_at = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (name, description, timestamp, deck_id, user_id),
        )
        row = connection.execute(
            f"""
            SELECT {DECK_FIELDS}
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        ).fetchone()
    return row_to_dict(row) if row else None


def delete_deck_with_items(user_id: int, deck_id: int) -> dict[str, int] | bool | None:
    from app.srs.storage import begin_card_write

    with get_connection() as connection:
        # Gate D-2 U4 follow-up (E4): account write lock before reading or deleting.
        begin_card_write(connection, user_id)
        default_deck = connection.execute(
            """
            SELECT id
            FROM decks
            WHERE user_id = ?
              AND name = ?
            """,
            (user_id, DEFAULT_DECK_NAME),
        ).fetchone()
        if default_deck and deck_id == int(default_deck["id"]):
            return None

        existing = connection.execute(
            """
            SELECT id
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        ).fetchone()
        if not existing:
            return False

        from app.srs.identity import record_personal_deletions

        # Gate D-2 U9 review fix: the deck's cards' pre-U9 receipts lose their content
        # copy in this transaction, before the ledger rows and the delete.
        from app.srs import receipts
        card_ids = [int(r["id"]) for r in connection.execute(
            "SELECT id FROM vocab_items WHERE deck_id = ? AND user_id = ?", (deck_id, user_id)).fetchall()]
        receipts.strip_card_receipts(connection, user_id, card_ids)
        # Gate D-2 U10-a: and their snapshot records' content copy.
        from app.srs.migration import strip_card_snapshots
        strip_card_snapshots(connection, user_id, card_ids)
        # Gate D-2 U3: ledger rows for every card of the deck, same transaction.
        record_personal_deletions(connection, "deck_id = ? AND user_id = ?", (deck_id, user_id))
        vocab_cursor = connection.execute(
            """
            DELETE FROM vocab_items
            WHERE deck_id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        )
        connection.execute(
            """
            DELETE FROM custom_terms
            WHERE deck_id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        )
        deck_cursor = connection.execute(
            """
            DELETE FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        )
    return {
        "deleted_deck_id": deck_id,
        "deleted_vocab_count": vocab_cursor.rowcount,
        "deleted_deck_count": deck_cursor.rowcount,
    }
