from __future__ import annotations

from typing import Any

from app.repositories.user_repository import get_or_create_dev_user


def get_current_user_dev() -> dict[str, Any]:
    # TODO: Replace with real authentication later.
    return get_or_create_dev_user()
