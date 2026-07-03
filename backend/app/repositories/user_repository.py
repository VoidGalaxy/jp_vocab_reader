from __future__ import annotations

from typing import Any

from app.database import (
    DEV_USER_EMAIL,
    DEFAULT_DECK_NAME,
    ensure_dev_user,
    get_connection,
    now_iso,
    row_to_dict,
)

USER_FIELDS = """
    id, email, display_name, password_hash, auth_provider, created_at, updated_at
"""


def get_or_create_dev_user() -> dict[str, Any]:
    # TODO: Replace dev user lookup with real authentication user provisioning later.
    with get_connection() as connection:
        user_id = ensure_dev_user(connection)
        row = connection.execute(
            f"""
            SELECT {USER_FIELDS}
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(
    email: str,
    display_name: str,
    password_hash: str,
    auth_provider: str = "local",
) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    normalized_display_name = display_name.strip() or normalized_email.split("@")[0]
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO users (
                email, display_name, password_hash, auth_provider, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_email,
                normalized_display_name,
                password_hash,
                auth_provider,
                timestamp,
                timestamp,
            ),
        )
        user_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            SELECT ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM decks WHERE user_id = ? AND name = ?
            )
            """,
            (
                user_id,
                DEFAULT_DECK_NAME,
                "기존 단어와 기본 저장 대상",
                timestamp,
                timestamp,
                user_id,
                DEFAULT_DECK_NAME,
            ),
        )
        row = connection.execute(
            f"""
            SELECT {USER_FIELDS}
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    # TODO: Add authorization checks when authentication is introduced.
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {USER_FIELDS}
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def get_user_by_email(email: str) -> dict[str, Any] | None:
    # TODO: Use this for login lookup when authentication is introduced.
    normalized_email = normalize_email(email)
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {USER_FIELDS}
            FROM users
            WHERE email = ?
            """,
            (normalized_email,),
        ).fetchone()
    return row_to_dict(row) if row else None


def get_dev_user_by_email() -> dict[str, Any] | None:
    return get_user_by_email(DEV_USER_EMAIL)


def email_exists(email: str) -> bool:
    return get_user_by_email(email) is not None
