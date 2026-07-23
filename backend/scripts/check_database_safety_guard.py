"""Tests for the DB safety guard (see docs/operations/database-safety.md).

Exercises assert_safe_database_url()/is_neon_database_url()/
normalize_app_env() in app/database.py purely as string-in/string-out
functions -- never opens a real database connection (SQLite or
PostgreSQL), never touches a real Neon database, and uses only a fake,
non-functional Neon-shaped hostname (never a real credential):

    postgresql://user:pass@ep-test.neon.tech/db

Usage:
    cd backend
    .venv\\Scripts\\Activate.ps1   (or source .venv/bin/activate)
    python scripts/check_database_safety_guard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import (  # noqa: E402
    assert_safe_database_url,
    is_neon_database_url,
    normalize_app_env,
)

FAKE_NEON_URL = "postgresql://user:pass@ep-test.neon.tech/db"
FAKE_SQLITE_URL = "sqlite:///./tmp.db"

FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def expect_blocked(label: str, database_url: str, app_env: str | None) -> None:
    try:
        assert_safe_database_url(database_url, app_env)
    except RuntimeError:
        check(label, True)
        return
    check(f"{label} (expected RuntimeError, none raised)", False)


def expect_allowed(label: str, database_url: str, app_env: str | None) -> None:
    try:
        assert_safe_database_url(database_url, app_env)
        check(label, True)
    except RuntimeError as exc:
        check(f"{label} (expected no error, got: {exc})", False)


def main() -> int:
    check("is_neon_database_url detects a Neon host", is_neon_database_url(FAKE_NEON_URL))
    check(
        "is_neon_database_url does not flag a SQLite URL",
        not is_neon_database_url(FAKE_SQLITE_URL),
    )
    check("is_neon_database_url does not flag an empty URL", not is_neon_database_url(""))

    check("normalize_app_env(None) -> development", normalize_app_env(None) == "development")
    check("normalize_app_env('') -> development", normalize_app_env("") == "development")
    check("normalize_app_env('  ') -> development", normalize_app_env("   ") == "development")
    check(
        "normalize_app_env is case-insensitive",
        normalize_app_env("PRODUCTION") == "production",
    )

    # --- Neon URL + non-production APP_ENV must all be BLOCKED -------------
    expect_blocked("1. APP_ENV=development + Neon URL is blocked", FAKE_NEON_URL, "development")
    expect_blocked("2. APP_ENV=local + Neon URL is blocked", FAKE_NEON_URL, "local")
    expect_blocked("3. APP_ENV=test + Neon URL is blocked", FAKE_NEON_URL, "test")
    expect_blocked("4. APP_ENV unset + Neon URL is blocked", FAKE_NEON_URL, None)
    expect_blocked("4b. APP_ENV='' + Neon URL is blocked", FAKE_NEON_URL, "")

    # --- Neon URL + APP_ENV=production must be ALLOWED ---------------------
    expect_allowed("5. APP_ENV=production + Neon URL is allowed", FAKE_NEON_URL, "production")
    expect_allowed(
        "5b. APP_ENV=Production (mixed case) + Neon URL is allowed",
        FAKE_NEON_URL,
        "Production",
    )

    # --- SQLite URL must always be ALLOWED regardless of APP_ENV -----------
    expect_allowed("6. APP_ENV=development + SQLite URL is allowed", FAKE_SQLITE_URL, "development")
    expect_allowed("7. APP_ENV=test + SQLite URL is allowed", FAKE_SQLITE_URL, "test")
    expect_allowed("7b. APP_ENV unset + SQLite URL is allowed", FAKE_SQLITE_URL, None)
    expect_allowed("7c. APP_ENV=production + SQLite URL is allowed", FAKE_SQLITE_URL, "production")
    expect_allowed("7d. empty DATABASE_URL + APP_ENV unset is allowed", "", None)
    expect_allowed("7e. empty DATABASE_URL + APP_ENV=development is allowed", "", "development")

    # --- error message never leaks the URL itself ---------------------------
    try:
        assert_safe_database_url(FAKE_NEON_URL, "development")
        check("error message check (no error raised)", False)
    except RuntimeError as exc:
        message = str(exc)
        check("error message does not contain the raw DATABASE_URL", FAKE_NEON_URL not in message)
        check("error message does not contain the fake credential", "user:pass" not in message)
        check("error message mentions Neon", "neon" in message.lower())
        check("error message mentions APP_ENV/production", "production" in message.lower())

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED:")
        for label in FAILURES:
            print(f"  - {label}")
        return 1
    print("Database safety guard checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
