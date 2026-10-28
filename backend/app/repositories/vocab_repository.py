from __future__ import annotations

from typing import Any

from app.account_write import begin_account_write
from app.database import (
    DEFAULT_DECK_NAME,
    VOCAB_ITEM_FIELDS,
    compute_review_schedule,
    get_connection,
    is_postgres_connection,
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


def _is_fsrs_account(user_id: int) -> bool:
    """Read-only: the account's SRS mode is explicitly 'fsrs' (Gate D-1 filter only)."""
    from app.srs.goals import account_goal

    with get_connection() as connection:
        settings = account_goal(connection, user_id)
    return settings is not None and settings["srs_mode"] == "fsrs"


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
    # Gate D-1 correction: an FSRS account's "지금 복습" filter is the study
    # queue's own decision (app/srs/queue.py classify -> learning/relearning/
    # review due), applied after the SQL conditions below; the legacy rule is
    # untouched.
    fsrs_due = due_only and _is_fsrs_account(user_id)
    if due_only and not fsrs_due:
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
        due_ids = None
        if fsrs_due:
            from app.srs import queue

            # One read view and the queue's clock for both the decision and the
            # list, so the count chip (/study-queue) and this list agree.
            queue._begin_snapshot(connection)
            due_ids = queue.personal_due_now_ids(connection, user_id, deck_id, queue._now())
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
    items = [row_to_dict(row) for row in rows]
    if due_ids is not None:
        items = [item for item in items if item["id"] in due_ids]
    return items


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


def _fill_blank_example_sentence(
    connection,
    user_id: int,
    existing_row,
    incoming_example_sentence: str,
    timestamp: str,
) -> dict[str, Any]:
    existing = row_to_dict(existing_row)
    # A word can be re-saved from a different passage than the one it was
    # first added from. Never overwrite an example_sentence the user (or an
    # earlier save) already has -- only fill it in if it's still blank.
    if (existing.get("example_sentence") or "").strip():
        return existing
    if not (incoming_example_sentence or "").strip():
        return existing

    connection.execute(
        """
        UPDATE vocab_items
        SET example_sentence = ?, updated_at = ?
        WHERE id = ?
          AND user_id = ?
        """,
        (incoming_example_sentence, timestamp, existing["id"], user_id),
    )
    row = connection.execute(
        f"""
        SELECT {VOCAB_ITEM_FIELDS}
        FROM vocab_items
        LEFT JOIN decks ON decks.id = vocab_items.deck_id
        WHERE vocab_items.id = ?
        """,
        (existing["id"],),
    ).fetchone()
    return row_to_dict(row)


def create_or_update_vocab_item(
    user_id: int, item: VocabItemCreate
) -> tuple[dict[str, Any], bool]:
    timestamp = now_iso()
    normalized = normalize_vocab_create(item)
    with get_connection() as connection:
        begin_account_write(connection, user_id)
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
            return (
                _fill_blank_example_sentence(
                    connection,
                    user_id,
                    existing,
                    normalized["example_sentence"],
                    timestamp,
                ),
                False,
            )

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
            return (
                _fill_blank_example_sentence(
                    connection,
                    user_id,
                    existing,
                    normalized["example_sentence"],
                    timestamp,
                ),
                False,
            )

        new_item_id = cursor.lastrowid
        # Gate C-2a: a newly inserted card in an FSRS-mode account starts as a
        # fresh FSRS card (same transaction). The update-existing path above
        # never reaches here, so it keeps its SRS columns.
        from app.srs.storage import initialize_new_personal_cards
        initialize_new_personal_cards(connection, user_id, item_id=new_item_id)
        row = connection.execute(
            f"""
            SELECT {VOCAB_ITEM_FIELDS}
            FROM vocab_items
            LEFT JOIN decks ON decks.id = vocab_items.deck_id
            WHERE vocab_items.id = ?
              AND vocab_items.user_id = ?
            """,
            (new_item_id, user_id),
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
        begin_account_write(connection, user_id)
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
        begin_account_write(connection, user_id)
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
    from app.srs.identity import record_personal_deletions
    from app.srs.storage import begin_card_write

    with get_connection() as connection:
        # Gate D-2 U4 follow-up (E4): the account write lock first, as reviews and
        # migration apply take it, then the ledger row (with the card's past-learning
        # mark) and the delete in one transaction.
        begin_card_write(connection, user_id)
        # Gate D-2 U9 review fix: this card's pre-U9 receipts lose their content copy
        # in the same transaction (only its own, only content fields).
        from app.srs import receipts
        if connection.execute("SELECT 1 FROM vocab_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone():
            receipts.strip_card_receipts(connection, user_id, [item_id])
            # Gate D-2 U10-a: the card's snapshot records lose their content copy too.
            from app.srs.migration import strip_card_snapshots
            strip_card_snapshots(connection, user_id, [item_id])
        record_personal_deletions(connection, "id = ? AND user_id = ?", (item_id, user_id))
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
    *,
    request_id: str | None = None,
    expected_card_version: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any] | None:
    from app.srs.engine import CardKey
    from app.srs.reviews import find_receipt, record_fsrs_review
    from app.srs.storage import begin_card_write

    reviewed_at = now_utc()
    timestamp = reviewed_at.isoformat()
    with get_connection() as connection:
        begin_card_write(connection, user_id)
        row_lock = " FOR UPDATE" if is_postgres_connection(connection) else ""
        existing = connection.execute(
            """
            SELECT *
            FROM vocab_items
            WHERE id = ?
              AND user_id = ?
            """ + row_lock,
            (item_id, user_id),
        ).fetchone()
        if not existing:
            return None

        key = CardKey("personal", user_id, item_id)
        receipt = find_receipt(connection, key, rating, request_id, expected_card_version,
                               session_id, None, response_time_ms)
        if receipt is not None:
            return receipt
        # Gate D-2 U12 (approved 2026-10-18): a card flagged identity unknown takes no new
        # review, whatever its engine or the account mode and with or without a
        # request_id. Checked under the account write lock (the flag takes the same lock),
        # after ownership (404 above) and the stored-answer rules, before any write. A
        # database without the SRS columns has no flag table either (same schema step).
        from app.srs.identity import is_identity_unknown
        from app.srs.storage import SrsWriteError
        if "srs_engine" in existing.keys() and is_identity_unknown(connection, user_id, "personal", item_id):
            raise SrsWriteError("card_identity_unknown")
        if dict(existing).get("srs_engine", "legacy") == "fsrs":
            return record_fsrs_review(connection, key, dict(existing), rating, request_id,
                                      expected_card_version, session_id, response_time_ms=response_time_ms)
        if expected_card_version is not None and existing["srs_card_version"] != expected_card_version:
            # Gate D-2 U8: a versioned (FSRS-client) request made before this card was
            # rolled back to legacy is stale; it is not recorded as a legacy review.
            from app.srs.storage import SrsWriteError
            raise SrsWriteError("card_version_conflict")

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
        version_update = "srs_card_version = srs_card_version + 1," if "srs_card_version" in existing.keys() else ""
        connection.execute(
            f"""
            UPDATE vocab_items
            SET {count_column} = {count_column} + 1,
                review_level = ?,
                next_review_at = ?,
                last_reviewed_at = ?,
                {version_update}
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
