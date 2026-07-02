from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.schemas import (
    CustomTermCreate,
    CustomTermUpdate,
    DeckCreate,
    DeckUpdate,
    VocabItemCreate,
    VocabItemUpdate,
)


DB_PATH = Path(__file__).resolve().parents[1] / "vocab.db"
DEFAULT_DECK_NAME = "기본 단어장"
VOCAB_ITEM_FIELDS = """
    vocab_items.id, vocab_items.deck_id, decks.name AS deck_name,
    vocab_items.surface, vocab_items.base_form, vocab_items.reading,
    vocab_items.part_of_speech, vocab_items.normalized_form,
    vocab_items.meaning_ko, vocab_items.context_explanation_ko,
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


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decks (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        default_deck_id = ensure_default_deck(connection)
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
        ensure_column(connection, "deck_id", "INTEGER")
        ensure_column(connection, "correct_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "wrong_count", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "last_reviewed_at", "DATETIME")
        ensure_column(connection, "review_level", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "next_review_at", "DATETIME")
        ensure_column(connection, "example_sentence", "TEXT NOT NULL DEFAULT ''")
        ensure_column(
            connection, "context_explanation_ko", "TEXT NOT NULL DEFAULT ''"
        )
        migrate_vocab_unique_constraint(connection)
        connection.execute(
            """
            UPDATE vocab_items
            SET deck_id = ?
            WHERE deck_id IS NULL
               OR deck_id NOT IN (SELECT id FROM decks)
            """,
            (default_deck_id,),
        )


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
            deck_id INTEGER,
            surface TEXT NOT NULL,
            base_form TEXT NOT NULL,
            reading TEXT NOT NULL,
            part_of_speech TEXT NOT NULL,
            normalized_form TEXT NOT NULL,
            meaning_ko TEXT NOT NULL DEFAULT '',
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
    context_expr = (
        "context_explanation_ko" if "context_explanation_ko" in columns else "''"
    )
    example_expr = "example_sentence" if "example_sentence" in columns else "''"
    correct_expr = "correct_count" if "correct_count" in columns else "0"
    wrong_expr = "wrong_count" if "wrong_count" in columns else "0"
    last_expr = "last_reviewed_at" if "last_reviewed_at" in columns else "NULL"
    level_expr = "review_level" if "review_level" in columns else "0"
    next_expr = "next_review_at" if "next_review_at" in columns else "NULL"
    connection.execute(
        f"""
        INSERT INTO vocab_items_new (
            id, deck_id, surface, base_form, reading, part_of_speech,
            normalized_form, meaning_ko, context_explanation_ko,
            example_sentence, status, correct_count, wrong_count,
            last_reviewed_at, review_level, next_review_at,
            created_at, updated_at
        )
        SELECT
            id, COALESCE({deck_expr}, ?), surface, base_form, reading,
            part_of_speech, normalized_form, meaning_ko, {context_expr},
            {example_expr}, status, {correct_expr}, {wrong_expr},
            {last_expr}, {level_expr}, {next_expr}, created_at, updated_at
        FROM vocab_items
        """,
        (default_deck_id,),
    )
    connection.execute("DROP TABLE vocab_items")
    connection.execute("ALTER TABLE vocab_items_new RENAME TO vocab_items")


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
            "LOWER(COALESCE(vocab_items.example_sentence, '')) LIKE ? OR "
            "LOWER(COALESCE(vocab_items.context_explanation_ko, '')) LIKE ?"
            ")"
        )
        params.extend([term] * 6)

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
                normalized_form, meaning_ko, context_explanation_ko,
                example_sentence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deck_id,
                normalized["surface"],
                normalized["base_form"],
                normalized["reading"],
                normalized["part_of_speech"],
                normalized["normalized_form"],
                normalized["meaning_ko"],
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
