from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


APP_NAME = "jp-vocab-reader"
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_DB_PATH = BACKEND_DIR / "vocab.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_DB_PATH}"
DEFAULT_CORS_ALLOW_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7
DEV_JWT_SECRET_KEY = "dev-only-jwt-secret-change-me"


load_dotenv(BACKEND_DIR / ".env")


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def get_jwt_secret_key() -> str:
    # TODO: Set JWT_SECRET_KEY in production; the fallback is for local dev only.
    return os.getenv("JWT_SECRET_KEY") or DEV_JWT_SECRET_KEY


def get_access_token_expire_minutes() -> int:
    raw_value = os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
    if not raw_value:
        return DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    try:
        return int(raw_value)
    except ValueError:
        return DEFAULT_JWT_ACCESS_TOKEN_EXPIRE_MINUTES


def get_openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.2").strip() or "gpt-5.2"


def get_cors_allow_origins() -> list[str]:
    raw_value = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw_value:
        return DEFAULT_CORS_ALLOW_ORIGINS
    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    # Use "*" only for local development. Production should list exact frontend origins.
    return origins or DEFAULT_CORS_ALLOW_ORIGINS
