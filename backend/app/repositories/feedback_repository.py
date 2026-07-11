from __future__ import annotations

from typing import Any

from app.database import get_connection, now_iso, row_to_dict


def create_meaning_feedback(
    *,
    user_id: int,
    vocabulary_id: int | None,
    surface: str,
    base_form: str,
    reading: str,
    current_meaning_ko: str,
    suggested_meaning_ko: str,
    reason: str,
    source: str,
) -> None:
    timestamp = now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO meaning_feedback (
                user_id, vocabulary_id, surface, base_form, reading,
                current_meaning_ko, suggested_meaning_ko, reason, source,
                status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                user_id,
                vocabulary_id,
                surface,
                base_form,
                reading,
                current_meaning_ko,
                suggested_meaning_ko,
                reason,
                source,
                timestamp,
            ),
        )


def list_meaning_feedback(limit: int = 200) -> list[dict[str, Any]]:
    """Read-only helper for the operator-facing listing script -- not
    exposed via any API endpoint."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, vocabulary_id, surface, base_form, reading,
                   current_meaning_ko, suggested_meaning_ko, reason, source,
                   status, created_at
            FROM meaning_feedback
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_app_feedback(
    *,
    user_id: int | None,
    category: str,
    message: str,
    screen: str,
    path: str,
) -> None:
    timestamp = now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO app_feedback (
                user_id, category, message, screen, path, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'open', ?)
            """,
            (user_id, category, message, screen, path, timestamp),
        )


def list_app_feedback(limit: int = 200) -> list[dict[str, Any]]:
    """Read-only helper for the operator-facing listing script -- not
    exposed via any API endpoint."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, user_id, category, message, screen, path, status,
                   created_at
            FROM app_feedback
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]
