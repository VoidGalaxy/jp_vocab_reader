from __future__ import annotations

from typing import Any

from app.database import (
    DEV_USER_EMAIL,
    ensure_dev_user,
    get_connection,
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
    normalized_email = email.strip().lower()
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
