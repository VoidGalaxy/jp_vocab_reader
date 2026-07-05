from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import POSTGRES_URL_PREFIXES  # noqa: E402

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - handled at runtime.
    psycopg = None
    dict_row = None


TABLES = (
    "users",
    "decks",
    "vocab_items",
    "custom_terms",
    "shared_decks",
    "shared_deck_items",
    "shared_deck_terms",
    "shared_deck_imports",
)


def masked_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    username = parsed.username or ""
    auth = f"{username}:***@" if username else ""
    netloc = f"{auth}{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL이 설정되지 않았습니다.")
        print("PostgreSQL 연결을 확인하려면 DATABASE_URL을 postgresql:// URL로 설정하세요.")
        return 1

    if not database_url.startswith(POSTGRES_URL_PREFIXES):
        print("DATABASE_URL이 PostgreSQL URL이 아닙니다.")
        print("현재 값:", masked_database_url(database_url))
        return 1

    if psycopg is None or dict_row is None:
        print("psycopg가 설치되어 있지 않습니다. backend requirements를 설치하세요.")
        return 1

    print("PostgreSQL 연결 확인을 시작합니다.")
    print("대상:", masked_database_url(database_url))

    try:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            version_row = connection.execute("SELECT version() AS version").fetchone()
            db_row = connection.execute(
                "SELECT current_database() AS database_name"
            ).fetchone()
            table_rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                ORDER BY table_name
                """,
                (list(TABLES),),
            ).fetchall()
    except Exception as exc:
        print("PostgreSQL 연결에 실패했습니다.")
        print(f"오류: {exc.__class__.__name__}: {exc}")
        return 1

    existing_tables = {row["table_name"] for row in table_rows}
    print("DB 엔진: postgresql")
    print("DB 이름:", db_row["database_name"])
    print("DB 버전:", version_row["version"].splitlines()[0])
    print("주요 테이블:")
    for table_name in TABLES:
        status = "exists" if table_name in existing_tables else "missing"
        print(f"- {table_name}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
