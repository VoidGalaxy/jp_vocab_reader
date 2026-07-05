from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import (  # noqa: E402
    AppPostgresConnection,
    POSTGRES_URL_PREFIXES,
    create_postgres_tables,
)

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - handled at runtime.
    psycopg = None
    dict_row = None


ALLOW_OVERWRITE_DEFAULT = False

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "users": (
        "id",
        "email",
        "display_name",
        "password_hash",
        "auth_provider",
        "created_at",
        "updated_at",
    ),
    "decks": (
        "id",
        "user_id",
        "name",
        "description",
        "created_at",
        "updated_at",
    ),
    "vocab_items": (
        "id",
        "user_id",
        "deck_id",
        "surface",
        "base_form",
        "reading",
        "part_of_speech",
        "normalized_form",
        "meaning_ko",
        "dictionary_gloss",
        "quality_tag",
        "context_explanation_ko",
        "example_sentence",
        "status",
        "correct_count",
        "wrong_count",
        "last_reviewed_at",
        "review_level",
        "next_review_at",
        "created_at",
        "updated_at",
    ),
    "custom_terms": (
        "id",
        "user_id",
        "term",
        "reading",
        "part_of_speech",
        "meaning_ko",
        "description",
        "deck_id",
        "created_at",
        "updated_at",
    ),
    "shared_decks": (
        "id",
        "owner_user_id",
        "title",
        "description",
        "source_deck_id",
        "visibility",
        "vocab_count",
        "custom_term_count",
        "import_count",
        "created_at",
        "updated_at",
    ),
    "shared_deck_items": (
        "id",
        "shared_deck_id",
        "surface",
        "base_form",
        "reading",
        "part_of_speech",
        "normalized_form",
        "meaning_ko",
        "dictionary_gloss",
        "context_explanation_ko",
        "example_sentence",
        "quality_tag",
        "created_at",
    ),
    "shared_deck_terms": (
        "id",
        "shared_deck_id",
        "term",
        "reading",
        "part_of_speech",
        "meaning_ko",
        "description",
        "created_at",
    ),
    "shared_deck_imports": (
        "id",
        "shared_deck_id",
        "user_id",
        "imported_deck_id",
        "imported_at",
    ),
}

TABLES = tuple(TABLE_COLUMNS.keys())


def masked_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    username = parsed.username or ""
    auth = f"{username}:***@" if username else ""
    netloc = f"{auth}{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum():
        raise ValueError(f"unsafe SQL identifier: {identifier}")
    return f'"{identifier}"'


def sqlite_table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def sqlite_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    if not sqlite_table_exists(connection, table_name):
        return set()
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
    }


def sqlite_count(connection: sqlite3.Connection, table_name: str) -> int:
    if not sqlite_table_exists(connection, table_name):
        return 0
    row = connection.execute(
        f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}"
    ).fetchone()
    return int(row["row_count"])


def postgres_count(connection: Any, table_name: str) -> int:
    row = connection.execute(
        f"SELECT COUNT(*) AS row_count FROM {quote_identifier(table_name)}"
    ).fetchone()
    return int(row["row_count"])


def print_counts(label: str, counts: dict[str, int]) -> None:
    print(label)
    for table_name in TABLES:
        print(f"- {table_name}: {counts.get(table_name, 0)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy backend/vocab.db SQLite data into PostgreSQL."
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        default=ALLOW_OVERWRITE_DEFAULT,
        help="Dangerous: truncate target PostgreSQL tables before migration.",
    )
    return parser.parse_args()


def reset_target(connection: Any) -> None:
    table_list = ", ".join(quote_identifier(table_name) for table_name in TABLES)
    connection.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE")


def copy_table(
    sqlite_connection: sqlite3.Connection,
    postgres_connection: Any,
    table_name: str,
) -> None:
    available_columns = sqlite_columns(sqlite_connection, table_name)
    if not available_columns:
        print(f"{table_name}: SQLite 테이블이 없어 건너뜁니다.")
        return

    columns = [column for column in TABLE_COLUMNS[table_name] if column in available_columns]
    if not columns:
        print(f"{table_name}: 복사할 공통 컬럼이 없어 건너뜁니다.")
        return

    missing_required = [
        column for column in TABLE_COLUMNS[table_name] if column not in available_columns
    ]
    if missing_required:
        print(
            f"{table_name}: SQLite에 없는 컬럼은 PostgreSQL 기본값을 사용합니다: "
            + ", ".join(missing_required)
        )

    column_sql = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    rows = sqlite_connection.execute(
        f"SELECT {column_sql} FROM {quote_identifier(table_name)} ORDER BY id ASC"
    ).fetchall()
    if not rows:
        return

    values = [tuple(row[column] for column in columns) for row in rows]
    postgres_connection.executemany(
        f"INSERT INTO {quote_identifier(table_name)} ({column_sql}) VALUES ({placeholders})",
        values,
    )


def sync_identity_sequence(connection: Any, table_name: str) -> None:
    sequence_row = connection.execute(
        "SELECT pg_get_serial_sequence(%s, 'id') AS sequence_name",
        (table_name,),
    ).fetchone()
    sequence_name = sequence_row["sequence_name"] if sequence_row else None
    if not sequence_name:
        return
    max_row = connection.execute(
        f"SELECT MAX(id) AS max_id FROM {quote_identifier(table_name)}"
    ).fetchone()
    max_id = max_row["max_id"] if max_row else None
    if max_id is not None:
        connection.execute("SELECT setval(%s, %s, true)", (sequence_name, max_id))


def main() -> int:
    args = parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL이 설정되지 않았습니다.")
        print("대상 PostgreSQL DATABASE_URL을 설정한 뒤 다시 실행하세요.")
        return 1
    if not database_url.startswith(POSTGRES_URL_PREFIXES):
        print("DATABASE_URL이 PostgreSQL URL이 아닙니다.")
        print("현재 값:", masked_database_url(database_url))
        return 1
    if psycopg is None or dict_row is None:
        print("psycopg가 설치되어 있지 않습니다. backend requirements를 설치하세요.")
        return 1

    sqlite_path = Path(
        os.getenv("SQLITE_DB_PATH", str(BACKEND_DIR / "vocab.db")).strip()
    ).expanduser()
    if not sqlite_path.exists():
        print(f"SQLite DB 파일을 찾을 수 없습니다: {sqlite_path}")
        return 1

    print("SQLite -> PostgreSQL 데이터 이전을 시작합니다.")
    print("SQLite:", sqlite_path)
    print("PostgreSQL:", masked_database_url(database_url))
    print("allow_overwrite:", args.allow_overwrite)

    sqlite_connection = sqlite3.connect(sqlite_path)
    sqlite_connection.row_factory = sqlite3.Row

    try:
        source_counts = {
            table_name: sqlite_count(sqlite_connection, table_name)
            for table_name in TABLES
        }
        print_counts("마이그레이션 전 SQLite row count:", source_counts)

        with psycopg.connect(database_url, row_factory=dict_row) as raw_connection:
            create_postgres_tables(AppPostgresConnection(raw_connection))
            target_counts_before = {
                table_name: postgres_count(raw_connection, table_name)
                for table_name in TABLES
            }
            print_counts("마이그레이션 전 PostgreSQL row count:", target_counts_before)

            if any(target_counts_before.values()):
                if not args.allow_overwrite:
                    print("PostgreSQL 대상 DB에 이미 데이터가 있어 중단합니다.")
                    print("정말 덮어써야 할 때만 --allow-overwrite 옵션을 사용하세요.")
                    return 1
                print("경고: PostgreSQL 대상 테이블을 비우고 다시 복사합니다.")
                reset_target(raw_connection)

            for table_name in TABLES:
                try:
                    copy_table(sqlite_connection, raw_connection, table_name)
                    sync_identity_sequence(raw_connection, table_name)
                except Exception as exc:
                    print(f"{table_name} 마이그레이션 중 실패했습니다.")
                    print(f"오류: {exc.__class__.__name__}: {exc}")
                    raise

            target_counts_after = {
                table_name: postgres_count(raw_connection, table_name)
                for table_name in TABLES
            }
            print_counts("마이그레이션 후 PostgreSQL row count:", target_counts_after)
    finally:
        sqlite_connection.close()

    print("SQLite -> PostgreSQL 데이터 이전이 완료되었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
