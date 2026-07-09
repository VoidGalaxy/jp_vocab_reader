from __future__ import annotations

from typing import Any

from app.database import (
    DEFAULT_DECK_NAME,
    VOCAB_ITEM_FIELDS,
    compute_review_schedule,
    get_connection,
    now_iso,
    now_utc,
    row_to_dict,
)
from app.schemas import VocabItemCreate, VocabItemUpdate


def get_or_create_default_deck_id(connection, user_id: int) -> int:
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
        (
            user_id,
            DEFAULT_DECK_NAME,
            "기존 단어와 기본 저장 대상",
            timestamp,
            timestamp,
        ),
    )
    return int(cursor.lastrowid)


def resolve_deck_id(connection, user_id: int, deck_id: int | None) -> int:
    default_deck_id = get_or_create_default_deck_id(connection, user_id)
    if deck_id is None:
        return default_deck_id

    row = connection.execute(
        """
        SELECT id
        FROM decks
        WHERE id = ?
          AND user_id = ?
        """,
        (deck_id, user_id),
    ).fetchone()
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
    user_id: int,
    deck_id: int | None = None,
    status: str | None = None,
    q: str | None = None,
    due_only: bool = False,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [user_id]
    where_clauses = ["vocab_items.user_id = ?"]
    if deck_id is not None:
        where_clauses.append("vocab_items.deck_id = ?")
        params.append(deck_id)
    if status is not None:
        where_clauses.append("vocab_items.status = ?")
        params.append(status)
    if due_only:
        # TODO(postgres): ISO datetime string comparison works in SQLite here;
        # revisit with TIMESTAMPTZ and explicit timezone semantics.
        where_clauses.append(
            "(vocab_items.next_review_at IS NULL OR vocab_items.next_review_at <= ?)"
        )
        params.append(now_iso())
    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        # TODO(postgres): Revisit LIKE/LOWER behavior for collation and indexing.
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

    where_clause = f"WHERE {' AND '.join(where_clauses)}"
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


def list_known_vocab_keys(user_id: int, deck_id: int | None = None) -> set[tuple[str, str]]:
    params: list[Any] = [user_id]
    deck_clause = ""
    if deck_id is not None:
        deck_clause = "AND deck_id = ?"
        params.append(deck_id)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT base_form, reading
            FROM vocab_items
            WHERE user_id = ?
              AND status = 'known'
              {deck_clause}
            """,
            tuple(params),
        ).fetchall()
    return {(row["base_form"], row["reading"]) for row in rows}


def get_vocab_item(user_id: int, item_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
              AND vocab_items.user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()
    return row_to_dict(row) if row else None


def create_or_update_vocab_item(
    user_id: int, item: VocabItemCreate
) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    normalized = normalize_vocab_create(item)
    with get_connection() as connection:
        deck_id = resolve_deck_id(connection, user_id, normalized["deck_id"])
        existing = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.user_id = ?
              AND vocab_items.base_form = ?
              AND vocab_items.reading = ?
              AND vocab_items.deck_id = ?
            """,
            (user_id, normalized["base_form"], normalized["reading"], deck_id),
        ).fetchone()
        if existing:
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            -- TODO(postgres): INSERT OR IGNORE is SQLite-specific.
            INSERT OR IGNORE INTO vocab_items (
                user_id, deck_id, surface, base_form, reading, part_of_speech,
                normalized_form, meaning_ko, dictionary_gloss, quality_tag, context_explanation_ko,
                example_sentence, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
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
                WHERE vocab_items.user_id = ?
                  AND vocab_items.base_form = ?
                  AND vocab_items.reading = ?
                  AND vocab_items.deck_id = ?
                """,
                (user_id, normalized["base_form"], normalized["reading"], deck_id),
            ).fetchone()
            return row_to_dict(existing), False

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
              AND vocab_items.user_id = ?
            """,
            (cursor.lastrowid, user_id),
        ).fetchone()
    return row_to_dict(row), True


def update_vocab_item(
    user_id: int, item_id: int, item: VocabItemUpdate
) -> dict[str, Any] | None:
    existing = get_vocab_item(user_id, item_id)
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
        values["deck_id"] = resolve_deck_id(connection, user_id, values["deck_id"])
        columns = ", ".join(f"{column} = ?" for column in values)
        params = [*values.values(), item_id, user_id]
        cursor = connection.execute(
            f"""
            UPDATE vocab_items
            SET {columns}
            WHERE id = ?
              AND user_id = ?
            """,
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
              AND vocab_items.user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()
    return row_to_dict(row)


def update_context_explanation(
    user_id: int, item_id: int, context_explanation_ko: str
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE vocab_items
            SET context_explanation_ko = ?, updated_at = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (context_explanation_ko, timestamp, item_id, user_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
              AND vocab_items.user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()
    return row_to_dict(row)


def delete_vocab_item(user_id: int, item_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM vocab_items
            WHERE id = ?
              AND user_id = ?
            """,
            (item_id, user_id),
        )
    return cursor.rowcount > 0


def list_study_items(user_id: int, deck_id: int | None = None) -> list[dict[str, Any]]:
    timestamp = now_iso()
    params: list[Any] = [user_id, timestamp]
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
            WHERE vocab_items.user_id = ?
              AND vocab_items.status IN ('unknown', 'uncertain')
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


def record_review(
    user_id: int,
    item_id: int,
    rating: str,
    response_time_ms: int | None = None,
) -> dict[str, Any] | None:
    reviewed_at = now_utc()
    timestamp = reviewed_at.isoformat()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT review_level, next_review_at, deck_id
            FROM vocab_items
            WHERE id = ?
              AND user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()
        if not existing:
            return None

        current_level = int(existing["review_level"])
        previous_next_review_at = existing["next_review_at"]
        deck_id = existing["deck_id"]

        next_level, next_review_at = compute_review_schedule(
            rating, current_level, reviewed_at
        )
        # "again" is the only rating that represents a failed recall; hard/good/easy
        # all mean the word was remembered (just with varying ease), so they all
        # count toward correct_count to keep that legacy counter meaningful.
        count_column = "wrong_count" if rating == "again" else "correct_count"
        connection.execute(
            f"""
            UPDATE vocab_items
            SET {count_column} = {count_column} + 1,
                review_level = ?,
                next_review_at = ?,
                last_reviewed_at = ?,
                updated_at = ?
            WHERE id = ?
              AND user_id = ?
            """,
            (next_level, next_review_at, timestamp, timestamp, item_id, user_id),
        )

        connection.execute(
            """
            INSERT INTO review_logs (
                user_id, vocab_item_id, deck_id, rating, reviewed_at,
                previous_review_level, next_review_level,
                previous_next_review_at, next_review_at, response_time_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                item_id,
                deck_id,
                rating,
                timestamp,
                current_level,
                next_level,
                previous_next_review_at,
                next_review_at,
                response_time_ms,
            ),
        )

        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
              AND vocab_items.user_id = ?
            """,
            (item_id, user_id),
        ).fetchone()
    return row_to_dict(row)
