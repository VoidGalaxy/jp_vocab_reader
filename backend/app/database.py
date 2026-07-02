from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import VocabItemCreate


DB_PATH = Path(__file__).resolve().parents[1] / "vocab.db"
VOCAB_ITEM_FIELDS = """
    id, surface, base_form, reading, part_of_speech, normalized_form,
    meaning_ko, status, correct_count, wrong_count, last_reviewed_at,
    created_at, updated_at
"""


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
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                last_reviewed_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE(base_form, reading)
            )
            """
        )
        ensure_column(connection, "correct_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "wrong_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "last_reviewed_at", "DATETIME")


def ensure_column(
    connection: sqlite3.Connection, column_name: str, column_definition: str
) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(vocab_items)").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE vocab_items ADD COLUMN {column_name} {column_definition}"
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_vocab_items() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_vocab_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
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
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
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
                f"""
                SELECT {VOCAB_ITEM_FIELDS}
                FROM vocab_items
                WHERE base_form = ? AND reading = ?
                """,
                (item.base_form, item.reading),
            ).fetchone()
            return row_to_dict(existing), False

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
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
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
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


def list_study_items() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            WHERE status = 'unknown'
            ORDER BY
                wrong_count DESC,
                CASE WHEN last_reviewed_at IS NULL THEN 0 ELSE 1 END ASC,
                last_reviewed_at ASC,
                created_at ASC,
                id ASC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def record_study_review(item_id: int, result: str) -> dict[str, Any] | None:
    timestamp = now_iso()
    count_column = "correct_count" if result == "correct" else "wrong_count"
    with get_connection() as connection:
        cursor = connection.execute(
            f"""
            UPDATE vocab_items
            SET {count_column} = {count_column} + 1,
                last_reviewed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (timestamp, timestamp, item_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            WHERE id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row)
