from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import VocabItemCreate


DB_PATH = Path(__file__).resolve().parents[1] / "vocab.db"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab_items (
                id INTEGER PRIMARY KEY,
                surface TEXT NOT NULL,
                base_form TEXT NOT NULL,
                reading TEXT NOT NULL,
                part_of_speech TEXT NOT NULL,
                normalized_form TEXT NOT NULL,
                meaning_ko TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE(base_form, reading)
            )
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_vocab_items() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, status, created_at, updated_at
            FROM vocab_items
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_vocab_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, status, created_at, updated_at
            FROM vocab_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_vocab_item(item: VocabItemCreate) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, status, created_at, updated_at
            FROM vocab_items
            WHERE base_form = ? AND reading = ?
            """,
            (item.base_form, item.reading),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO vocab_items (
                surface, base_form, reading, part_of_speech, normalized_form,
                meaning_ko, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.surface,
                item.base_form,
                item.reading,
                item.part_of_speech,
                item.normalized_form,
                item.meaning_ko,
                item.status,
                timestamp,
                timestamp,
            ),
        )
        if cursor.rowcount == 0:
            existing = connection.execute(
                """
                SELECT id, surface, base_form, reading, part_of_speech,
                       normalized_form, meaning_ko, status, created_at, updated_at
                FROM vocab_items
                WHERE base_form = ? AND reading = ?
                """,
                (item.base_form, item.reading),
            ).fetchone()
            return row_to_dict(existing), False

        row = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, status, created_at, updated_at
            FROM vocab_items
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_vocab_item_status(item_id: int, status: str) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE vocab_items
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, timestamp, item_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, status, created_at, updated_at
            FROM vocab_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row)


def delete_vocab_item(item_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM vocab_items WHERE id = ?", (item_id,))
    return cursor.rowcount > 0
