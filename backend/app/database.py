from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.schemas import (
    CustomTermCreate,
    CustomTermUpdate,
    DeckCreate,
    DeckPackage,
    DeckUpdate,
    VocabItemCreate,
    VocabItemUpdate,
)
from app.settings import DEFAULT_SQLITE_DB_PATH, get_database_url

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional until PostgreSQL is configured.
    psycopg = None
    dict_row = None


DB_PATH = DEFAULT_SQLITE_DB_PATH
SQLITE_URL_PREFIX = "sqlite:///"
POSTGRES_URL_PREFIXES = ("postgresql://", "postgres://")
SQLITE_CONNECTION_TIMEOUT_SECONDS = 10
DEFAULT_DECK_NAME = "기본 단어장"
DEV_USER_EMAIL = "dev@example.local"
DEV_USER_DISPLAY_NAME = "개발 사용자"
DEV_USER_AUTH_PROVIDER = "dev"
VOCAB_ITEM_FIELDS = """
    vocab_items.id, vocab_items.deck_id, decks.name AS deck_name,
    vocab_items.surface, vocab_items.base_form, vocab_items.reading,
    vocab_items.part_of_speech, vocab_items.normalized_form,
    vocab_items.meaning_ko, vocab_items.dictionary_gloss,
    vocab_items.quality_tag,
    vocab_items.context_explanation_ko,
    vocab_items.example_sentence, vocab_items.status,
    vocab_items.correct_count, vocab_items.wrong_count,
    vocab_items.last_reviewed_at, vocab_items.review_level,
    vocab_items.next_review_at, vocab_items.created_at, vocab_items.updated_at
"""
CUSTOM_TERM_FIELDS = """
    custom_terms.id, custom_terms.term, custom_terms.reading,
    custom_terms.part_of_speech, custom_terms.meaning_ko,
    custom_terms.description, custom_terms.deck_id,
    decks.name AS deck_name,
    custom_terms.created_at, custom_terms.updated_at
"""


class AppSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class AppPostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor
        self._lastrowid: int | None = None
        self._lastrowid_loaded = False

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount)

    @property
    def lastrowid(self) -> int | None:
        if self._lastrowid_loaded:
            return self._lastrowid
        self._lastrowid_loaded = True
        try:
            row = self._cursor.fetchone()
        except Exception:
            row = None
        if row and "id" in row:
            self._lastrowid = int(row["id"])
        return self._lastrowid

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self._cursor.fetchall()


class AppPostgresConnection:
    is_postgres = True

    def __init__(self, raw_connection: Any):
        self._connection = raw_connection

    def __enter__(self) -> "AppPostgresConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return bool(self._connection.__exit__(exc_type, exc_value, traceback))
        finally:
            self._connection.close()

    def close(self) -> None:
        self._connection.close()

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()) -> AppPostgresCursor:
        adapted_query = adapt_query(query, is_postgres=True)
        cursor = self._connection.execute(adapted_query, tuple(params))
        return AppPostgresCursor(cursor)


def is_postgres_connection(connection: Any) -> bool:
    return bool(getattr(connection, "is_postgres", False))


def get_database_engine() -> str:
    database_url = get_database_url()
    if database_url.startswith(POSTGRES_URL_PREFIXES):
        return "postgresql"
    return "sqlite"


def adapt_query(query: str, is_postgres: bool = False) -> str:
    if not is_postgres:
        return query
    adapted = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    adapted = adapted.replace("?", "%s")
    normalized_original = _strip_leading_sql_comments(query)
    if normalized_original.upper().startswith("INSERT OR IGNORE INTO"):
        adapted = f"{adapted.rstrip()} ON CONFLICT DO NOTHING"
    if _is_insert_with_id(adapted) and " RETURNING " not in adapted.upper():
        adapted = f"{adapted.rstrip()} RETURNING id"
    return adapted


def _strip_leading_sql_comments(query: str) -> str:
    lines = query.lstrip().splitlines()
    while lines and lines[0].lstrip().startswith("--"):
        lines.pop(0)
    return "\n".join(lines).lstrip()


def _is_insert_with_id(query: str) -> bool:
    stripped = _strip_leading_sql_comments(query)
    if not stripped.upper().startswith("INSERT INTO"):
        return False
    match = re.match(r"INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", stripped, re.I)
    if not match:
        return False
    return match.group(1) in {
        "users",
        "decks",
        "vocab_items",
        "custom_terms",
        "shared_decks",
        "shared_deck_items",
        "shared_deck_terms",
        "shared_deck_imports",
    }


def get_sqlite_database_path() -> str:
    database_url = get_database_url()
    if not database_url:
        return str(DEFAULT_SQLITE_DB_PATH)
    if database_url.startswith(SQLITE_URL_PREFIX):
        raw_path = database_url.removeprefix(SQLITE_URL_PREFIX)
        if not raw_path:
            return str(DEFAULT_SQLITE_DB_PATH)
        if raw_path == ":memory:":
            return raw_path
        return str(Path(raw_path).expanduser())
    if database_url.startswith(POSTGRES_URL_PREFIXES):
        raise ValueError("PostgreSQL DATABASE_URL cannot be used as a SQLite path.")
    raise ValueError(
        "Unsupported DATABASE_URL. Use sqlite:///./vocab.db or leave it unset."
    )


def get_connection() -> sqlite3.Connection | AppPostgresConnection:
    database_url = get_database_url()
    if database_url.startswith(POSTGRES_URL_PREFIXES):
        if psycopg is None or dict_row is None:
            raise RuntimeError(
                "PostgreSQL DATABASE_URL is set, but psycopg is not installed. "
                "Install backend requirements first."
            )
        raw_connection = psycopg.connect(database_url, row_factory=dict_row)
        return AppPostgresConnection(raw_connection)

    connection = sqlite3.connect(
        get_sqlite_database_path(),
        timeout=SQLITE_CONNECTION_TIMEOUT_SECONDS,
        factory=AppSQLiteConnection,
    )
    connection.row_factory = sqlite3.Row
    # TODO(postgres): PRAGMA is SQLite-specific and should move behind adapter setup.
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    initialize_database()


def initialize_database() -> None:
    with get_connection() as connection:
        ensure_schema(connection)


def ensure_schema(connection: sqlite3.Connection) -> None:
    if is_postgres_connection(connection):
        create_postgres_tables(connection)
        dev_user_id = seed_dev_user(connection)
        backfill_existing_data_to_dev_user(connection, dev_user_id)
        ensure_default_decks_for_users(connection)
        return

    create_core_tables(connection)
    create_shared_deck_tables(connection)
    create_review_log_table(connection)
    create_meaning_feedback_table(connection)
    create_app_feedback_table(connection)
    apply_sqlite_migrations(connection)
    dev_user_id = seed_dev_user(connection)
    backfill_existing_data_to_dev_user(connection, dev_user_id)
    migrate_deck_unique_constraint(connection)
    migrate_vocab_unique_constraint(connection)
    apply_sqlite_migrations(connection)
    backfill_existing_data_to_dev_user(connection, dev_user_id)
    ensure_default_decks_for_users(connection)
    backfill_vocab_items_to_default_decks(connection, dev_user_id)


def create_core_tables(connection: sqlite3.Connection) -> None:
    ensure_users_table(connection)
    ensure_core_schema(connection)


def apply_sqlite_migrations(connection: sqlite3.Connection) -> None:
    ensure_vocab_item_columns(connection)
    ensure_user_scoped_columns(connection)


def seed_dev_user(connection: sqlite3.Connection) -> int:
    return ensure_dev_user(connection)


def backfill_existing_data_to_dev_user(
    connection: sqlite3.Connection, dev_user_id: int
) -> None:
    migrate_existing_data_to_dev_user(connection, dev_user_id)


def ensure_auth_schema(connection: sqlite3.Connection) -> None:
    ensure_users_table(connection)


def ensure_core_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab_items (
            id INTEGER PRIMARY KEY,
            deck_id INTEGER,
            surface TEXT NOT NULL,
            base_form TEXT NOT NULL,
            reading TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            normalized_form TEXT NOT NULL,
            meaning_ko TEXT NOT NULL DEFAULT '',
            dictionary_gloss TEXT NOT NULL DEFAULT '',
            quality_tag TEXT NOT NULL DEFAULT 'normal',
            context_explanation_ko TEXT NOT NULL DEFAULT '',
            example_sentence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            last_reviewed_at DATETIME,
            review_level INTEGER NOT NULL DEFAULT 0,
            next_review_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_terms (
            id INTEGER PRIMARY KEY,
            term TEXT NOT NULL,
            reading TEXT NOT NULL DEFAULT '',
            part_of_speech TEXT NOT NULL DEFAULT '명사',
            meaning_ko TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            deck_id INTEGER,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )


def ensure_shared_deck_schema(connection: sqlite3.Connection) -> None:
    create_shared_deck_tables(connection)


def ensure_vocab_item_columns(connection: sqlite3.Connection) -> None:
    add_column_if_missing(connection, "vocab_items", "deck_id INTEGER")
    add_column_if_missing(
        connection, "vocab_items", "correct_count INTEGER NOT NULL DEFAULT 0"
    )
    add_column_if_missing(
        connection, "vocab_items", "wrong_count INTEGER NOT NULL DEFAULT 0"
    )
    add_column_if_missing(connection, "vocab_items", "last_reviewed_at DATETIME")
    add_column_if_missing(
        connection, "vocab_items", "review_level INTEGER NOT NULL DEFAULT 0"
    )
    add_column_if_missing(connection, "vocab_items", "next_review_at DATETIME")
    add_column_if_missing(
        connection, "vocab_items", "example_sentence TEXT NOT NULL DEFAULT ''"
    )
    add_column_if_missing(
        connection, "vocab_items", "dictionary_gloss TEXT NOT NULL DEFAULT ''"
    )
    add_column_if_missing(
        connection, "vocab_items", "quality_tag TEXT NOT NULL DEFAULT 'normal'"
    )
    add_column_if_missing(
        connection, "vocab_items", "context_explanation_ko TEXT NOT NULL DEFAULT ''"
    )


def ensure_users_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            display_name TEXT,
            password_hash TEXT,
            auth_provider TEXT NOT NULL DEFAULT 'local',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def create_shared_deck_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            source_deck_id INTEGER,
            visibility TEXT NOT NULL DEFAULT 'public',
            vocab_count INTEGER NOT NULL DEFAULT 0,
            custom_term_count INTEGER NOT NULL DEFAULT 0,
            import_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shared_deck_id INTEGER NOT NULL,
            surface TEXT,
            base_form TEXT,
            reading TEXT,
            part_of_speech TEXT,
            normalized_form TEXT,
            meaning_ko TEXT,
            dictionary_gloss TEXT,
            context_explanation_ko TEXT,
            example_sentence TEXT,
            quality_tag TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_terms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shared_deck_id INTEGER NOT NULL,
            term TEXT NOT NULL,
            reading TEXT,
            part_of_speech TEXT,
            meaning_ko TEXT,
            description TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shared_deck_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            imported_deck_id INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )


def create_review_log_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vocab_item_id INTEGER NOT NULL,
            deck_id INTEGER,
            rating TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            previous_review_level INTEGER NOT NULL,
            next_review_level INTEGER NOT NULL,
            previous_next_review_at TEXT,
            next_review_at TEXT NOT NULL,
            response_time_ms INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_logs_user_reviewed
        ON review_logs(user_id, reviewed_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_logs_item
        ON review_logs(vocab_item_id)
        """
    )


def create_meaning_feedback_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS meaning_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            vocabulary_id INTEGER,
            surface TEXT,
            base_form TEXT,
            reading TEXT,
            current_meaning_ko TEXT,
            suggested_meaning_ko TEXT,
            reason TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meaning_feedback_user
        ON meaning_feedback(user_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meaning_feedback_status
        ON meaning_feedback(status)
        """
    )


def create_app_feedback_table(connection: sqlite3.Connection) -> None:
    # user_id is nullable (unlike meaning_feedback) so this table can also
    # accept feedback from a request with no resolvable user in the future;
    # today current_user_id() always resolves to a real row (a logged-in
    # user or the shared dev user), so it is in practice always populated.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            screen TEXT,
            path TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_feedback_user
        ON app_feedback(user_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_feedback_status
        ON app_feedback(status)
        """
    )


def create_postgres_tables(connection: AppPostgresConnection) -> None:
    # TODO(postgres): created_at/updated_at/next_review_at are kept as ISO TEXT
    # for compatibility. Move to TIMESTAMPTZ in a later migration.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            email TEXT UNIQUE,
            display_name TEXT,
            password_hash TEXT,
            auth_provider TEXT NOT NULL DEFAULT 'local',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decks (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab_items (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            deck_id INTEGER REFERENCES decks(id) ON DELETE CASCADE,
            surface TEXT NOT NULL,
            base_form TEXT NOT NULL,
            reading TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            normalized_form TEXT NOT NULL,
            meaning_ko TEXT NOT NULL DEFAULT '',
            dictionary_gloss TEXT NOT NULL DEFAULT '',
            quality_tag TEXT NOT NULL DEFAULT 'normal',
            context_explanation_ko TEXT NOT NULL DEFAULT '',
            example_sentence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            last_reviewed_at TEXT,
            review_level INTEGER NOT NULL DEFAULT 0,
            next_review_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, deck_id, base_form, reading)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_terms (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            term TEXT NOT NULL,
            reading TEXT NOT NULL DEFAULT '',
            part_of_speech TEXT NOT NULL DEFAULT '명사',
            meaning_ko TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            deck_id INTEGER REFERENCES decks(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, deck_id, term)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_decks (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            source_deck_id INTEGER,
            visibility TEXT NOT NULL DEFAULT 'public',
            vocab_count INTEGER NOT NULL DEFAULT 0,
            custom_term_count INTEGER NOT NULL DEFAULT 0,
            import_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_items (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            shared_deck_id INTEGER NOT NULL REFERENCES shared_decks(id) ON DELETE CASCADE,
            surface TEXT,
            base_form TEXT,
            reading TEXT,
            part_of_speech TEXT,
            normalized_form TEXT,
            meaning_ko TEXT,
            dictionary_gloss TEXT,
            context_explanation_ko TEXT,
            example_sentence TEXT,
            quality_tag TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_terms (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            shared_deck_id INTEGER NOT NULL REFERENCES shared_decks(id) ON DELETE CASCADE,
            term TEXT NOT NULL,
            reading TEXT,
            part_of_speech TEXT,
            meaning_ko TEXT,
            description TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS shared_deck_imports (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            shared_deck_id INTEGER NOT NULL REFERENCES shared_decks(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            imported_deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
            imported_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_logs (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocab_item_id INTEGER NOT NULL REFERENCES vocab_items(id) ON DELETE CASCADE,
            deck_id INTEGER,
            rating TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            previous_review_level INTEGER NOT NULL,
            next_review_level INTEGER NOT NULL,
            previous_next_review_at TEXT,
            next_review_at TEXT NOT NULL,
            response_time_ms INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS meaning_feedback (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vocabulary_id INTEGER REFERENCES vocab_items(id) ON DELETE SET NULL,
            surface TEXT,
            base_form TEXT,
            reading TEXT,
            current_meaning_ko TEXT,
            suggested_meaning_ko TEXT,
            reason TEXT,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS app_feedback (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            screen TEXT,
            path TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vocab_items_user_deck
        ON vocab_items(user_id, deck_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_shared_decks_visibility
        ON shared_decks(visibility, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_logs_user_reviewed
        ON review_logs(user_id, reviewed_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_logs_item
        ON review_logs(vocab_item_id)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meaning_feedback_user
        ON meaning_feedback(user_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_meaning_feedback_status
        ON meaning_feedback(status)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_feedback_user
        ON app_feedback(user_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_app_feedback_status
        ON app_feedback(status)
        """
    )


def ensure_shared_deck_tables(connection: sqlite3.Connection) -> None:
    create_shared_deck_tables(connection)


def ensure_dev_user(connection: sqlite3.Connection) -> int:
    if not is_postgres_connection(connection):
        ensure_users_table(connection)
    timestamp = now_iso()
    row = connection.execute(
        "SELECT id FROM users WHERE email = ?", (DEV_USER_EMAIL,)
    ).fetchone()
    if row:
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO users (
            email, display_name, password_hash, auth_provider, created_at, updated_at
        )
        VALUES (?, ?, NULL, ?, ?, ?)
        """,
        (
            DEV_USER_EMAIL,
            DEV_USER_DISPLAY_NAME,
            DEV_USER_AUTH_PROVIDER,
            timestamp,
            timestamp,
        ),
    )
    return int(cursor.lastrowid)


def ensure_default_deck(connection: sqlite3.Connection) -> int:
    timestamp = now_iso()
    row = connection.execute(
        "SELECT id FROM decks WHERE name = ?", (DEFAULT_DECK_NAME,)
    ).fetchone()
    if row:
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO decks (name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (DEFAULT_DECK_NAME, "기존 단어와 기본 저장 대상", timestamp, timestamp),
    )
    return int(cursor.lastrowid)


def ensure_default_deck_for_user(connection: sqlite3.Connection, user_id: int) -> int:
    timestamp = now_iso()
    row = connection.execute(
        """
        SELECT id
        FROM decks
        WHERE user_id = ?
          AND name = ?
        """,
        (user_id, DEFAULT_DECK_NAME),
    ).fetchone()
    if row:
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO decks (user_id, name, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, DEFAULT_DECK_NAME, "", timestamp, timestamp),
    )
    return int(cursor.lastrowid)


def ensure_default_decks_for_users(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT id FROM users ORDER BY id ASC").fetchall()
    for row in rows:
        ensure_default_deck_for_user(connection, int(row["id"]))


def backfill_vocab_items_to_default_decks(
    connection: sqlite3.Connection, fallback_user_id: int
) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT COALESCE(user_id, ?) AS user_id
        FROM vocab_items
        WHERE deck_id IS NULL
           OR deck_id NOT IN (SELECT id FROM decks)
        """,
        (fallback_user_id,),
    ).fetchall()
    for row in rows:
        user_id = int(row["user_id"])
        default_deck_id = ensure_default_deck_for_user(connection, user_id)
        connection.execute(
            """
            UPDATE vocab_items
            SET deck_id = ?
            WHERE COALESCE(user_id, ?) = ?
              AND (
                  deck_id IS NULL
                  OR deck_id NOT IN (SELECT id FROM decks)
              )
            """,
            (default_deck_id, fallback_user_id, user_id),
        )


def migrate_vocab_unique_constraint(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'vocab_items'"
    ).fetchone()
    create_sql = row["sql"] if row else ""
    if (
        "UNIQUE(base_form, reading)" not in create_sql
        and "UNIQUE(base_form, reading, deck_id)" not in create_sql
    ):
        return

    default_deck_id = ensure_default_deck(connection)
    connection.execute(
        """
        CREATE TABLE vocab_items_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            deck_id INTEGER,
            surface TEXT NOT NULL,
            base_form TEXT NOT NULL,
            reading TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            normalized_form TEXT NOT NULL,
            meaning_ko TEXT NOT NULL DEFAULT '',
            dictionary_gloss TEXT NOT NULL DEFAULT '',
            quality_tag TEXT NOT NULL DEFAULT 'normal',
            context_explanation_ko TEXT NOT NULL DEFAULT '',
            example_sentence TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            correct_count INTEGER NOT NULL DEFAULT 0,
            wrong_count INTEGER NOT NULL DEFAULT 0,
            last_reviewed_at DATETIME,
            review_level INTEGER NOT NULL DEFAULT 0,
            next_review_at DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(vocab_items)").fetchall()
    }
    deck_expr = "deck_id" if "deck_id" in columns else str(default_deck_id)
    user_expr = "user_id" if "user_id" in columns else "NULL"
    context_expr = (
        "context_explanation_ko" if "context_explanation_ko" in columns else "''"
    )
    gloss_expr = "dictionary_gloss" if "dictionary_gloss" in columns else "''"
    quality_expr = "quality_tag" if "quality_tag" in columns else "'normal'"
    example_expr = "example_sentence" if "example_sentence" in columns else "''"
    correct_expr = "correct_count" if "correct_count" in columns else "0"
    wrong_expr = "wrong_count" if "wrong_count" in columns else "0"
    last_expr = "last_reviewed_at" if "last_reviewed_at" in columns else "NULL"
    level_expr = "review_level" if "review_level" in columns else "0"
    next_expr = "next_review_at" if "next_review_at" in columns else "NULL"
    connection.execute(
        f"""
        INSERT INTO vocab_items_new (
            id, user_id, deck_id, surface, base_form, reading, part_of_speech,
            normalized_form, meaning_ko, dictionary_gloss, quality_tag, context_explanation_ko,
            example_sentence, status, correct_count, wrong_count,
            last_reviewed_at, review_level, next_review_at,
            created_at, updated_at
        )
        SELECT
            id, {user_expr}, COALESCE({deck_expr}, ?), surface, base_form, reading,
            part_of_speech, normalized_form, meaning_ko, {gloss_expr}, {quality_expr}, {context_expr},
            {example_expr}, status, {correct_expr}, {wrong_expr},
            {last_expr}, {level_expr}, {next_expr}, created_at, updated_at
        FROM vocab_items
        """,
        (default_deck_id,),
    )
    connection.execute("DROP TABLE vocab_items")
    connection.execute("ALTER TABLE vocab_items_new RENAME TO vocab_items")


def migrate_deck_unique_constraint(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'decks'"
    ).fetchone()
    create_sql = row["sql"] if row else ""
    if "UNIQUE" not in create_sql.upper():
        return

    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(decks)").fetchall()
    }
    user_expr = "user_id" if "user_id" in columns else "NULL"
    connection.execute(
        """
        CREATE TABLE decks_new (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        INSERT INTO decks_new (
            id, user_id, name, description, created_at, updated_at
        )
        SELECT id, {user_expr}, name, description, created_at, updated_at
        FROM decks
        """
    )
    connection.execute("DROP TABLE decks")
    connection.execute("ALTER TABLE decks_new RENAME TO decks")


def ensure_column(
    connection: sqlite3.Connection, column_name: str, column_definition: str
) -> None:
    add_column_if_missing(
        connection, "vocab_items", f"{column_name} {column_definition}"
    )


def validate_sql_identifier(identifier: str) -> None:
    if not identifier or not identifier.replace("_", "").isalnum():
        raise ValueError(f"unsafe SQL identifier: {identifier}")


def column_exists(
    connection: sqlite3.Connection, table_name: str, column_name: str
) -> bool:
    validate_sql_identifier(table_name)
    validate_sql_identifier(column_name)
    # TODO(postgres): PRAGMA table_info is SQLite-specific schema introspection.
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def add_column_if_missing(
    connection: sqlite3.Connection, table_name: str, column_definition: str
) -> None:
    validate_sql_identifier(table_name)
    column_name = column_definition.strip().split(maxsplit=1)[0]
    validate_sql_identifier(column_name)
    if not column_exists(connection, table_name, column_name):
        # TODO(postgres): Replace ad hoc ALTER TABLE with versioned migrations.
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def ensure_table_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    add_column_if_missing(connection, table_name, f"{column_name} {column_definition}")


def ensure_user_scope_columns(connection: sqlite3.Connection) -> None:
    add_column_if_missing(connection, "decks", "user_id INTEGER")
    add_column_if_missing(connection, "vocab_items", "user_id INTEGER")
    add_column_if_missing(connection, "custom_terms", "user_id INTEGER")


def ensure_user_scoped_columns(connection: sqlite3.Connection) -> None:
    ensure_user_scope_columns(connection)


def migrate_existing_data_to_dev_user(
    connection: sqlite3.Connection, dev_user_id: int
) -> None:
    for table_name in ("decks", "vocab_items", "custom_terms"):
        connection.execute(
            f"""
            UPDATE {table_name}
            SET user_id = ?
            WHERE user_id IS NULL
            """,
            (dev_user_id,),
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def now_iso() -> str:
    # TODO(timezone): Keep UTC ISO strings for now; define a full timezone policy
    # before PostgreSQL TIMESTAMPTZ migration.
    return now_utc().isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def next_review_for_correct(current_level: int, reviewed_at: datetime) -> str:
    if current_level <= 0:
        delay = timedelta(days=1)
    elif current_level == 1:
        delay = timedelta(days=3)
    elif current_level == 2:
        delay = timedelta(days=7)
    else:
        delay = timedelta(days=14)
    return (reviewed_at + delay).isoformat()


# Simple, predictable interval table shared by the "good"/"easy" ratings,
# indexed by review_level. Not FSRS -- a fixed step table meant to be easy to
# reason about now and swappable for a real FSRS scheduler later without
# touching review_logs' shape (each log already records the level/interval
# that was actually used, which is what a future FSRS migration would need).
REVIEW_INTERVAL_DAYS = [1, 3, 7, 14, 30, 45, 60]
MAX_REVIEW_LEVEL = len(REVIEW_INTERVAL_DAYS) - 1


def compute_review_schedule(
    rating: str, current_level: int, reviewed_at: datetime
) -> tuple[int, str]:
    current_level = max(current_level, 0)
    if rating == "again":
        next_level = 0
        next_review_at = reviewed_at
    elif rating == "hard":
        next_level = current_level
        next_review_at = reviewed_at + timedelta(days=1)
    elif rating == "easy":
        next_level = min(current_level + 2, MAX_REVIEW_LEVEL)
        next_review_at = reviewed_at + timedelta(days=REVIEW_INTERVAL_DAYS[next_level])
    else:
        next_level = min(current_level + 1, MAX_REVIEW_LEVEL)
        next_review_at = reviewed_at + timedelta(days=REVIEW_INTERVAL_DAYS[next_level])
    return next_level, next_review_at.isoformat()


def list_decks() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            ORDER BY id ASC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_deck(deck_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (deck_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_deck(deck: DeckCreate) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    name = deck.name.strip()
    description = deck.description.strip()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE name = ?
            """,
            (name,),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False
        cursor = connection.execute(
            """
            INSERT INTO decks (name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, description, timestamp, timestamp),
        )
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_deck(deck_id: int, deck: DeckUpdate) -> dict[str, Any] | None:
    existing = get_deck(deck_id)
    if not existing:
        return None

    timestamp = now_iso()
    name = deck.name.strip() if deck.name is not None else existing["name"]
    description = (
        deck.description.strip()
        if deck.description is not None
        else existing["description"]
    )
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE decks
            SET name = ?, description = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, description, timestamp, deck_id),
        )
        row = connection.execute(
            """
            SELECT id, name, description, created_at, updated_at
            FROM decks
            WHERE id = ?
            """,
            (deck_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def delete_deck(deck_id: int) -> dict[str, int] | bool | None:
    with get_connection() as connection:
        default_deck_id = ensure_default_deck(connection)
        if deck_id == default_deck_id:
            return None

        existing = connection.execute(
            "SELECT id FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        if not existing:
            return False

        vocab_cursor = connection.execute(
            "DELETE FROM vocab_items WHERE deck_id = ?",
            (deck_id,),
        )
        connection.execute(
            "DELETE FROM custom_terms WHERE deck_id = ?",
            (deck_id,),
        )
        deck_cursor = connection.execute("DELETE FROM decks WHERE id = ?", (deck_id,))
    return {
        "deleted_deck_id": deck_id,
        "deleted_vocab_count": vocab_cursor.rowcount,
        "deleted_deck_count": deck_cursor.rowcount,
    }


def get_unique_imported_deck_name(
    connection: sqlite3.Connection, original_name: str
) -> str:
    base_name = original_name.strip() or "가져온 덱"
    existing_names = {
        row["name"]
        for row in connection.execute("SELECT name FROM decks").fetchall()
    }
    if base_name not in existing_names:
        return base_name

    first_candidate = f"{base_name} (가져옴)"
    if first_candidate not in existing_names:
        return first_candidate

    suffix = 2
    while True:
        candidate = f"{base_name} (가져옴 {suffix})"
        if candidate not in existing_names:
            return candidate
        suffix += 1


def build_deck_package(
    deck_id: int, include_common_terms: bool = False
) -> dict[str, Any] | None:
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT id, name, description
            FROM decks
            WHERE id = ?
            """,
            (deck_id,),
        ).fetchone()
        if not deck:
            return None

        vocab_rows = connection.execute(
            """
            SELECT surface, base_form, reading, part_of_speech, normalized_form,
                   meaning_ko, dictionary_gloss, context_explanation_ko,
                   example_sentence, quality_tag
            FROM vocab_items
            WHERE deck_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (deck_id,),
        ).fetchall()

        term_params: tuple[Any, ...] = (deck_id,)
        term_clause = "custom_terms.deck_id = ?"
        if include_common_terms:
            term_clause = "(custom_terms.deck_id = ? OR custom_terms.deck_id IS NULL)"

        term_rows = connection.execute(
            f"""
            SELECT term, reading, part_of_speech, meaning_ko, description
            FROM custom_terms
            WHERE {term_clause}
            ORDER BY created_at ASC, id ASC
            """,
            term_params,
        ).fetchall()

    return {
        "package_type": "jp_vocab_reader_deck",
        "package_version": 1,
        "exported_at": now_iso(),
        "app": {
            "name": "JP Vocab Reader",
            "format": "deck_package",
        },
        "deck": {
            "name": deck["name"],
            "description": deck["description"] or "",
        },
        "vocab_items": [row_to_dict(row) for row in vocab_rows],
        "custom_terms": [row_to_dict(row) for row in term_rows],
    }


def dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def import_deck_package(package: DeckPackage) -> dict[str, Any]:
    timestamp = now_iso()
    deck_payload = dump_model(package.deck)
    vocab_payloads = [dump_model(item) for item in package.vocab_items]
    custom_term_payloads = [dump_model(term) for term in package.custom_terms]

    imported_vocab_count = 0
    skipped_vocab_count = 0
    imported_custom_term_count = 0
    skipped_custom_term_count = 0
    seen_vocab_keys: set[tuple[str, str]] = set()
    seen_custom_terms: set[str] = set()

    with get_connection() as connection:
        deck_name = get_unique_imported_deck_name(
            connection, str(deck_payload.get("name") or "")
        )
        deck_description = str(deck_payload.get("description") or "").strip()
        cursor = connection.execute(
            """
            INSERT INTO decks (name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (deck_name, deck_description, timestamp, timestamp),
        )
        deck_id = int(cursor.lastrowid)

        for raw_item in vocab_payloads:
            values = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in raw_item.items()
            }
            surface = str(values.get("surface") or "").strip()
            base_form = str(values.get("base_form") or "").strip() or surface
            reading = str(values.get("reading") or "").strip()
            if not surface and not base_form:
                skipped_vocab_count += 1
                continue

            key = (base_form, reading)
            if key in seen_vocab_keys:
                skipped_vocab_count += 1
                continue
            seen_vocab_keys.add(key)

            normalized_form = (
                str(values.get("normalized_form") or "").strip() or base_form
            )
            connection.execute(
                """
                INSERT INTO vocab_items (
                    deck_id, surface, base_form, reading, part_of_speech,
                    normalized_form, meaning_ko, dictionary_gloss, quality_tag,
                    context_explanation_ko, example_sentence, status,
                    correct_count, wrong_count, last_reviewed_at, review_level,
                    next_review_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 0, 0, NULL, 0, NULL, ?, ?)
                """,
                (
                    deck_id,
                    surface or base_form,
                    base_form,
                    reading,
                    str(values.get("part_of_speech") or "").strip(),
                    normalized_form,
                    str(values.get("meaning_ko") or "").strip(),
                    str(values.get("dictionary_gloss") or "").strip(),
                    str(values.get("quality_tag") or "").strip() or "normal",
                    str(values.get("context_explanation_ko") or "").strip(),
                    str(values.get("example_sentence") or "").strip(),
                    timestamp,
                    timestamp,
                ),
            )
            imported_vocab_count += 1

        for raw_term in custom_term_payloads:
            values = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in raw_term.items()
            }
            term = str(values.get("term") or "").strip()
            if not term:
                skipped_custom_term_count += 1
                continue
            if term in seen_custom_terms:
                skipped_custom_term_count += 1
                continue
            seen_custom_terms.add(term)

            connection.execute(
                """
                INSERT INTO custom_terms (
                    term, reading, part_of_speech, meaning_ko, description,
                    deck_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    term,
                    str(values.get("reading") or "").strip(),
                    str(values.get("part_of_speech") or "").strip() or "명사",
                    str(values.get("meaning_ko") or "").strip(),
                    str(values.get("description") or "").strip(),
                    deck_id,
                    timestamp,
                    timestamp,
                ),
            )
            imported_custom_term_count += 1

    return {
        "deck_id": deck_id,
        "deck_name": deck_name,
        "imported_vocab_count": imported_vocab_count,
        "skipped_vocab_count": skipped_vocab_count,
        "imported_custom_term_count": imported_custom_term_count,
        "skipped_custom_term_count": skipped_custom_term_count,
        "message": "덱 패키지를 가져왔습니다.",
    }


def normalize_custom_term_data(
    term: CustomTermCreate | CustomTermUpdate,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if hasattr(term, "model_dump"):
        raw_values = term.model_dump(exclude_unset=True)
    else:
        raw_values = term.dict(exclude_unset=True)

    for key, value in raw_values.items():
        values[key] = value.strip() if isinstance(value, str) else value

    if existing:
        merged = {**existing, **values}
    else:
        merged = values

    merged["term"] = merged.get("term", "").strip()
    merged["reading"] = merged.get("reading", "").strip()
    merged["part_of_speech"] = merged.get("part_of_speech", "").strip() or "명사"
    merged["meaning_ko"] = merged.get("meaning_ko", "").strip()
    merged["description"] = merged.get("description", "").strip()
    merged["deck_id"] = merged.get("deck_id")
    return merged


def get_existing_custom_term(
    connection: sqlite3.Connection,
    term: str,
    deck_id: int | None,
    exclude_id: int | None = None,
) -> sqlite3.Row | None:
    params: list[Any] = [term]
    deck_clause = "custom_terms.deck_id IS NULL"
    if deck_id is not None:
        deck_clause = "custom_terms.deck_id = ?"
        params.append(deck_id)
    exclude_clause = ""
    if exclude_id is not None:
        exclude_clause = "AND custom_terms.id != ?"
        params.append(exclude_id)

    return connection.execute(
        f"""
        SELECT {CUSTOM_TERM_FIELDS}
        FROM custom_terms
        LEFT JOIN decks ON decks.id = custom_terms.deck_id
        WHERE custom_terms.term = ?
          AND {deck_clause}
          {exclude_clause}
        """,
        tuple(params),
    ).fetchone()


def list_custom_terms(deck_id: int | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_clause = ""
    if deck_id is not None:
        where_clause = "WHERE custom_terms.deck_id = ? OR custom_terms.deck_id IS NULL"
        params.append(deck_id)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            {where_clause}
            ORDER BY LENGTH(custom_terms.term) DESC, custom_terms.created_at DESC, custom_terms.id DESC
            """,
            tuple(params),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_custom_term(term_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (term_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_custom_term(term: CustomTermCreate) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    normalized = normalize_custom_term_data(term)
    with get_connection() as connection:
        deck_id = normalized["deck_id"]
        if deck_id is not None and not get_deck(deck_id):
            deck_id = None
        existing = get_existing_custom_term(
            connection, normalized["term"], deck_id
        )
        if existing:
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            INSERT INTO custom_terms (
                term, reading, part_of_speech, meaning_ko, description,
                deck_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["term"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["meaning_ko"],
                normalized["description"],
                deck_id,
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_custom_term(
    term_id: int, term: CustomTermUpdate
) -> dict[str, Any] | None:
    existing = get_custom_term(term_id)
    if not existing:
        return None

    timestamp = now_iso()
    normalized = normalize_custom_term_data(term, existing)
    with get_connection() as connection:
        deck_id = normalized["deck_id"]
        if deck_id is not None and not get_deck(deck_id):
            deck_id = None
        duplicate = get_existing_custom_term(
            connection, normalized["term"], deck_id, exclude_id=term_id
        )
        if duplicate:
            return row_to_dict(duplicate)

        connection.execute(
            """
            UPDATE custom_terms
            SET term = ?, reading = ?, part_of_speech = ?, meaning_ko = ?,
                description = ?, deck_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["term"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["meaning_ko"],
                normalized["description"],
                deck_id,
                timestamp,
                term_id,
            ),
        )
        row = connection.execute(
            f"""
            SELECT {CUSTOM_TERM_FIELDS}
            FROM custom_terms
            LEFT JOIN decks ON decks.id = custom_terms.deck_id
            WHERE custom_terms.id = ?
            """,
            (term_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def delete_custom_term(term_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM custom_terms WHERE id = ?", (term_id,))
    return cursor.rowcount > 0


def get_default_deck_id() -> int:
    with get_connection() as connection:
        return ensure_default_deck(connection)


def resolve_deck_id(connection: sqlite3.Connection, deck_id: int | None) -> int:
    default_deck_id = ensure_default_deck(connection)
    if deck_id is None:
        return default_deck_id

    row = connection.execute("SELECT id FROM decks WHERE id = ?", (deck_id,)).fetchone()
    return int(row["id"]) if row else default_deck_id


def normalize_vocab_create(item: VocabItemCreate) -> dict[str, Any]:
    surface = item.surface.strip()
    base_form = item.base_form.strip() or surface
    normalized_form = item.normalized_form.strip() or base_form
    return {
        "surface": surface or base_form,
        "base_form": base_form,
        "reading": item.reading.strip(),
        "part_of_speech": item.part_of_speech.strip(),
        "normalized_form": normalized_form,
        "meaning_ko": item.meaning_ko.strip(),
        "dictionary_gloss": item.dictionary_gloss.strip(),
        "quality_tag": item.quality_tag.strip() or "normal",
        "context_explanation_ko": item.context_explanation_ko.strip(),
        "example_sentence": item.example_sentence.strip(),
        "status": item.status,
        "deck_id": item.deck_id,
    }


def list_vocab_items(
    deck_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    due_only: bool = False,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where_clauses = []
    if deck_id is not None:
        where_clauses.append("vocab_items.deck_id = ?")
        params.append(deck_id)
    if status is not None:
        where_clauses.append("vocab_items.status = ?")
        params.append(status)
    if due_only:
        where_clauses.append(
            "(vocab_items.next_review_at IS NULL OR vocab_items.next_review_at <= ?)"
        )
        params.append(now_iso())
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        where_clauses.append(
            "("
            "LOWER(COALESCE(vocab_items.surface, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.base_form, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.reading, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.meaning_ko, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.dictionary_gloss, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.quality_tag, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.example_sentence, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.context_explanation_ko, '')) LIKE ?"
            ")"
        )
        params.extend([term] * 8)

    where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    order_clause = {
        "created_asc": "vocab_items.created_at ASC, vocab_items.id ASC",
        "wrong_desc": "vocab_items.wrong_count DESC, vocab_items.created_at DESC, vocab_items.id DESC",
        "correct_desc": "vocab_items.correct_count DESC, vocab_items.created_at DESC, vocab_items.id DESC",
        "review_level_asc": "vocab_items.review_level ASC, vocab_items.created_at DESC, vocab_items.id DESC",
        "next_review_asc": "CASE WHEN vocab_items.next_review_at IS NULL THEN 1 ELSE 0 END ASC, vocab_items.next_review_at ASC, vocab_items.created_at DESC, vocab_items.id DESC",
        "created_desc": "vocab_items.created_at DESC, vocab_items.id DESC",
    }.get(sort or "", "vocab_items.created_at DESC, vocab_items.id DESC")

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            {where_clause}
            ORDER BY {order_clause}
            """,
            tuple(params),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def list_known_vocab_keys(deck_id: int | None = None) -> set[tuple[str, str]]:
    params: list[Any] = []
    deck_clause = ""
    if deck_id is not None:
        deck_clause = "AND deck_id = ?"
        params.append(deck_id)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT base_form, reading
            FROM vocab_items
            WHERE status = 'known'
              {deck_clause}
            """,
            tuple(params),
        ).fetchall()
    return {(row["base_form"], row["reading"]) for row in rows}


def get_stats(deck_id: int | None = None) -> dict[str, Any]:
    timestamp = now_iso()
    params: list[Any] = [timestamp]
    where_clause = ""
    if deck_id is not None:
        where_clause = "WHERE vocab_items.deck_id = ?"
        params.append(deck_id)

    with get_connection() as connection:
        summary = connection.execute(
            f"""
            SELECT
                COUNT(*) AS total_count,
                SUM(CASE WHEN status = 'known' THEN 1 ELSE 0 END) AS known_count,
                SUM(CASE WHEN status = 'uncertain' THEN 1 ELSE 0 END) AS uncertain_count,
                SUM(CASE WHEN status = 'unknown' THEN 1 ELSE 0 END) AS unknown_count,
                SUM(CASE WHEN status = 'unclassified' THEN 1 ELSE 0 END) AS unclassified_count,
                SUM(
                    CASE
                        WHEN status IN ('unknown', 'uncertain')
                         AND (next_review_at IS NULL OR next_review_at <= ?)
                        THEN 1 ELSE 0
                    END
                ) AS due_today_count,
                COALESCE(SUM(correct_count), 0) AS total_correct_count,
                COALESCE(SUM(wrong_count), 0) AS total_wrong_count,
                COALESCE(AVG(review_level), 0) AS average_review_level
            FROM vocab_items
            {where_clause}
            """,
            tuple(params),
        ).fetchone()

        level_rows = connection.execute(
            f"""
            SELECT review_level, COUNT(*) AS count
            FROM vocab_items
            {where_clause}
            GROUP BY review_level
            ORDER BY review_level ASC
            """,
            tuple(params[1:]),
        ).fetchall()

        deck_row = None
        deck_stats: list[dict[str, Any]] = []
        if deck_id is not None:
            deck_row = connection.execute(
                "SELECT id, name FROM decks WHERE id = ?", (deck_id,)
            ).fetchone()
        else:
            deck_rows = connection.execute(
                """
                SELECT
                    decks.id AS deck_id,
                    decks.name AS deck_name,
                    COUNT(vocab_items.id) AS total_count,
                    SUM(CASE WHEN vocab_items.status = 'known' THEN 1 ELSE 0 END) AS known_count,
                    SUM(CASE WHEN vocab_items.status = 'uncertain' THEN 1 ELSE 0 END) AS uncertain_count,
                    SUM(CASE WHEN vocab_items.status = 'unknown' THEN 1 ELSE 0 END) AS unknown_count,
                    SUM(CASE WHEN vocab_items.status = 'unclassified' THEN 1 ELSE 0 END) AS unclassified_count,
                    SUM(
                        CASE
                            WHEN vocab_items.status IN ('unknown', 'uncertain')
                             AND (vocab_items.next_review_at IS NULL OR vocab_items.next_review_at <= ?)
                            THEN 1 ELSE 0
                        END
                    ) AS due_today_count
                FROM decks
                LEFT JOIN vocab_items ON vocab_items.deck_id = decks.id
                GROUP BY decks.id, decks.name
                ORDER BY decks.id ASC
                """,
                (timestamp,),
            ).fetchall()
            deck_stats = [build_deck_stats(row_to_dict(row)) for row in deck_rows]

    stats = row_to_dict(summary)
    total_count = int(stats.get("total_count") or 0)
    known_count = int(stats.get("known_count") or 0)
    scope = "deck" if deck_id is not None else "all"
    return {
        "scope": scope,
        "deck_id": deck_id,
        "deck_name": deck_row["name"] if deck_row else None,
        "total_count": total_count,
        "known_count": known_count,
        "uncertain_count": int(stats.get("uncertain_count") or 0),
        "unknown_count": int(stats.get("unknown_count") or 0),
        "unclassified_count": int(stats.get("unclassified_count") or 0),
        "due_today_count": int(stats.get("due_today_count") or 0),
        "total_correct_count": int(stats.get("total_correct_count") or 0),
        "total_wrong_count": int(stats.get("total_wrong_count") or 0),
        "average_review_level": round(float(stats.get("average_review_level") or 0), 2),
        "learned_rate": learned_rate(known_count, total_count),
        "deck_stats": deck_stats,
        "review_level_counts": [
            {
                "review_level": int(row["review_level"] or 0),
                "count": int(row["count"] or 0),
            }
            for row in level_rows
        ],
    }


def build_deck_stats(row: dict[str, Any]) -> dict[str, Any]:
    total_count = int(row.get("total_count") or 0)
    known_count = int(row.get("known_count") or 0)
    return {
        "deck_id": int(row["deck_id"]),
        "deck_name": row["deck_name"],
        "total_count": total_count,
        "known_count": known_count,
        "uncertain_count": int(row.get("uncertain_count") or 0),
        "unknown_count": int(row.get("unknown_count") or 0),
        "unclassified_count": int(row.get("unclassified_count") or 0),
        "due_today_count": int(row.get("due_today_count") or 0),
        "learned_rate": learned_rate(known_count, total_count),
    }


def learned_rate(known_count: int, total_count: int) -> float:
    if total_count <= 0:
        return 0
    return round(known_count / total_count, 4)


def get_vocab_item(item_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_vocab_item(item: VocabItemCreate) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    normalized = normalize_vocab_create(item)
    with get_connection() as connection:
        deck_id = resolve_deck_id(connection, normalized["deck_id"])
        existing = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.base_form = ?
              AND vocab_items.reading = ?
              AND vocab_items.deck_id = ?
            """,
            (normalized["base_form"], normalized["reading"], deck_id),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO vocab_items (
                deck_id, surface, base_form, reading, part_of_speech,
                normalized_form, meaning_ko, dictionary_gloss, quality_tag, context_explanation_ko,
                example_sentence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deck_id,
                normalized["surface"],
                normalized["base_form"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["normalized_form"],
                normalized["meaning_ko"],
                normalized["dictionary_gloss"],
                normalized["quality_tag"],
                normalized["context_explanation_ko"],
                normalized["example_sentence"],
                normalized["status"],
                timestamp,
                timestamp,
            ),
        )
        if cursor.rowcount == 0:
            existing = connection.execute(
                f"""
                SELECT {VOCAB_ITEM_FIELDS}
                FROM vocab_items
                LEFT JOIN decks ON decks.id = vocab_items.deck_id
                WHERE vocab_items.base_form = ?
                  AND vocab_items.reading = ?
                  AND vocab_items.deck_id = ?
                """,
                (normalized["base_form"], normalized["reading"], deck_id),
            ).fetchone()
            return row_to_dict(existing), False

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def update_vocab_item(item_id: int, item: VocabItemUpdate) -> dict[str, Any] | None:
    existing = get_vocab_item(item_id)
    if not existing:
        return None

    timestamp = now_iso()
    if hasattr(item, "model_dump"):
        values = item.model_dump(exclude_unset=True)
    else:
        values = item.dict(exclude_unset=True)
    deck_id = values.pop("deck_id", existing["deck_id"])
    values = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in values.items()
    }

    surface = values.get("surface", existing["surface"])
    base_form = values.get("base_form", existing["base_form"])
    base_form = base_form or surface
    normalized_form = values.get("normalized_form", existing["normalized_form"])
    normalized_form = normalized_form or base_form

    values["surface"] = surface or base_form
    values["base_form"] = base_form
    values["normalized_form"] = normalized_form
    values["deck_id"] = deck_id
    values["updated_at"] = timestamp

    with get_connection() as connection:
        values["deck_id"] = resolve_deck_id(connection, values["deck_id"])
        columns = ", ".join(f"{column} = ?" for column in values)
        params = [*values.values(), item_id]
        cursor = connection.execute(
            f"UPDATE vocab_items SET {columns} WHERE id = ?",
            tuple(params),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row)


def update_context_explanation(
    item_id: int, context_explanation_ko: str
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE vocab_items
            SET context_explanation_ko = ?, updated_at = ?
            WHERE id = ?
            """,
            (context_explanation_ko, timestamp, item_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row)


def delete_vocab_item(item_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM vocab_items WHERE id = ?", (item_id,))
    return cursor.rowcount > 0


def list_study_items(deck_id: int | None = None) -> list[dict[str, Any]]:
    timestamp = now_iso()
    params: list[Any] = [timestamp]
    deck_clause = ""
    if deck_id is not None:
        deck_clause = "AND vocab_items.deck_id = ?"
        params.append(deck_id)
    params.append(timestamp)
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.status IN ('unknown', 'uncertain')
              AND (vocab_items.next_review_at IS NULL OR vocab_items.next_review_at <= ?)
              {deck_clause}
            ORDER BY
                CASE WHEN vocab_items.next_review_at IS NOT NULL AND vocab_items.next_review_at <= ? THEN 0 ELSE 1 END ASC,
                vocab_items.next_review_at ASC,
                vocab_items.wrong_count DESC,
                vocab_items.review_level ASC,
                CASE WHEN vocab_items.last_reviewed_at IS NULL THEN 0 ELSE 1 END ASC,
                vocab_items.created_at ASC,
                vocab_items.id ASC
            """,
            tuple(params),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def record_study_review(item_id: int, result: str) -> dict[str, Any] | None:
    reviewed_at = datetime.now(timezone.utc)
    timestamp = reviewed_at.isoformat()
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT review_level FROM vocab_items WHERE id = ?", (item_id,)
        ).fetchone()
        if not existing:
            return None

        current_level = int(existing["review_level"])
        if result == "correct":
            next_level = min(current_level + 1, 4)
            next_review_at = next_review_for_correct(current_level, reviewed_at)
            connection.execute(
                """
                UPDATE vocab_items
                SET correct_count = correct_count + 1,
                    review_level = ?,
                    next_review_at = ?,
                    last_reviewed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (next_level, next_review_at, timestamp, timestamp, item_id),
            )
        else:
            connection.execute(
                """
                UPDATE vocab_items
                SET wrong_count = wrong_count + 1,
                    review_level = 0,
                    next_review_at = ?,
                    last_reviewed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, timestamp, item_id),
            )

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
            """,
            (item_id,),
        ).fetchone()
    return row_to_dict(row)
