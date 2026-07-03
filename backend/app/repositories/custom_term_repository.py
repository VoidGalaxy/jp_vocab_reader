from __future__ import annotations

import sqlite3
from typing import Any

from app.database import CUSTOM_TERM_FIELDS, get_connection, now_iso, row_to_dict
from app.schemas import CustomTermCreate, CustomTermUpdate


def normalize_custom_term_data(
    term: CustomTermCreate | CustomTermUpdate,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if hasattr(term, "model_dump"):
        raw_values = term.model_dump(exclude_unset=True)
    else:
        raw_values = term.dict(exclude_unset=True)

    for key, value in raw_values.items():
        values[key] = value.strip() if isinstance(value, str) else value

    if existing:
        merged = {**existing, **values}
    else:
        merged = values

    merged["term"] = merged.get("term", "").strip()
    merged["reading"] = merged.get("reading", "").strip()
    merged["part_of_speech"] = merged.get("part_of_speech", "").strip() or "명사"
    merged["meaning_ko"] = merged.get("meaning_ko", "").strip()
    merged["description"] = merged.get("description", "").strip()
    merged["deck_id"] = merged.get("deck_id")
    return merged


def get_existing_custom_term(
    connection: sqlite3.Connection,
    term: str,
    deck_id: int | None,
    exclude_id: int | None = None,
) -> sqlite3.Row | None:
    params: list[Any] = [term]
    deck_clause = "custom_terms.deck_id IS NULL"
    if deck_id is not None:
        deck_clause = "custom_terms.deck_id = ?"
        params.append(deck_id)
    exclude_clause = ""
    if exclude_id is not None:
        exclude_clause = "AND custom_terms.id != ?"
        params.append(exclude_id)

    return connection.execute(
        f"""
        SELECT {CUSTOM_TERM_FIELDS}
        FROM custom_terms
        LEFT JOIN decks ON decks.id = custom_terms.deck_id
        WHERE custom_terms.term = ?
          AND {deck_clause}
          {exclude_clause}
        """,
        tuple(params),
    ).fetchone()


def list_custom_terms(deck_id: int | None = None) -> list[dict[str, Any]]:
    # TODO: Add user_id filtering when authentication is introduced.
    params: list[Any] = []
    where_clause = ""
    if deck_id is not None:
        where_clause = "WHERE custom_terms.deck_id = ? OR custom_terms.deck_id IS NULL"
        params.append(deck_id)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            {where_clause}
            ORDER BY LENGTH(custom_terms.term) DESC, custom_terms.created_at DESC, custom_terms.id DESC
            """,
            tuple(params),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_custom_term(term_id: int) -> dict[str, Any] | None:
    # TODO: Add user_id filtering when authentication is introduced.
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (term_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_custom_term(term: CustomTermCreate) -> tuple[dict[str, Any], bool]:
    # TODO: Add user_id ownership when authentication is introduced.
    timestamp = now_iso()
    normalized = normalize_custom_term_data(term)
    with get_connection() as connection:
        deck_id = normalized["deck_id"]
        if deck_id is not None:
            deck = connection.execute(
                "SELECT id FROM decks WHERE id = ?", (deck_id,)
            ).fetchone()
            if not deck:
                deck_id = None
        existing = get_existing_custom_term(
            connection, normalized["term"], deck_id
        )
        if existing:
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            INSERT INTO custom_terms (
                term, reading, part_of_speech, meaning_ko, description,
                deck_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["term"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["meaning_ko"],
                normalized["description"],
                deck_id,
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_custom_term(
    term_id: int, term: CustomTermUpdate
) -> dict[str, Any] | None:
    # TODO: Add user_id ownership checks when authentication is introduced.
    existing = get_custom_term(term_id)
    if not existing:
        return None

    timestamp = now_iso()
    normalized = normalize_custom_term_data(term, existing)
    with get_connection() as connection:
        deck_id = normalized["deck_id"]
        if deck_id is not None:
            deck = connection.execute(
                "SELECT id FROM decks WHERE id = ?", (deck_id,)
            ).fetchone()
            if not deck:
                deck_id = None
        duplicate = get_existing_custom_term(
            connection, normalized["term"], deck_id, exclude_id=term_id
        )
        if duplicate:
            return row_to_dict(duplicate)

        connection.execute(
            """
            UPDATE custom_terms
            SET term = ?, reading = ?, part_of_speech = ?, meaning_ko = ?,
                description = ?, deck_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["term"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["meaning_ko"],
                normalized["description"],
                deck_id,
                timestamp,
                term_id,
            ),
        )
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (term_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def delete_custom_term(term_id: int) -> bool:
    # TODO: Add user_id ownership checks when authentication is introduced.
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM custom_terms WHERE id = ?", (term_id,))
    return cursor.rowcount > 0
