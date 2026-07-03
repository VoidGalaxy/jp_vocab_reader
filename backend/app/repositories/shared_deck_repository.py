from __future__ import annotations

import sqlite3
from typing import Any

from app.database import get_connection, now_iso, row_to_dict


def publish_deck(
    user_id: int, deck_id: int, title: str, description: str
) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT id, name, description
            FROM decks
            WHERE id = ?
              AND user_id = ?
            """,
            (deck_id, user_id),
        ).fetchone()
        if not deck:
            return None

        shared_title = title.strip() or deck["name"]
        shared_description = description.strip()
        vocab_rows = connection.execute(
            """
            SELECT surface, base_form, reading, part_of_speech, normalized_form,
                   meaning_ko, dictionary_gloss, context_explanation_ko,
                   example_sentence, quality_tag
            FROM vocab_items
            WHERE user_id = ?
              AND deck_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, deck_id),
        ).fetchall()
        term_rows = connection.execute(
            """
            SELECT term, reading, part_of_speech, meaning_ko, description
            FROM custom_terms
            WHERE user_id = ?
              AND deck_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id, deck_id),
        ).fetchall()

        cursor = connection.execute(
            """
            INSERT INTO shared_decks (
                owner_user_id, title, description, source_deck_id, visibility,
                vocab_count, custom_term_count, import_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'public', ?, ?, 0, ?, ?)
            """,
            (
                user_id,
                shared_title,
                shared_description,
                deck_id,
                len(vocab_rows),
                len(term_rows),
                timestamp,
                timestamp,
            ),
        )
        shared_deck_id = int(cursor.lastrowid)

        for row in vocab_rows:
            connection.execute(
                """
                INSERT INTO shared_deck_items (
                    shared_deck_id, surface, base_form, reading, part_of_speech,
                    normalized_form, meaning_ko, dictionary_gloss,
                    context_explanation_ko, example_sentence, quality_tag, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shared_deck_id,
                    row["surface"],
                    row["base_form"],
                    row["reading"],
                    row["part_of_speech"],
                    row["normalized_form"],
                    row["meaning_ko"],
                    row["dictionary_gloss"],
                    row["context_explanation_ko"],
                    row["example_sentence"],
                    row["quality_tag"],
                    timestamp,
                ),
            )

        for row in term_rows:
            connection.execute(
                """
                INSERT INTO shared_deck_terms (
                    shared_deck_id, term, reading, part_of_speech,
                    meaning_ko, description, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shared_deck_id,
                    row["term"],
                    row["reading"],
                    row["part_of_speech"],
                    row["meaning_ko"],
                    row["description"],
                    timestamp,
                ),
            )

    return {
        "shared_deck_id": shared_deck_id,
        "title": shared_title,
        "vocab_count": len(vocab_rows),
        "custom_term_count": len(term_rows),
        "message": "\uacf5\uc720 \ub371\uc73c\ub85c \ub4f1\ub85d\ud588\uc2b5\ub2c8\ub2e4.",
    }


def list_shared_decks() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.visibility = 'public'
            ORDER BY shared_decks.created_at DESC, shared_decks.id DESC
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_shared_deck(shared_deck_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at,
                   shared_decks.updated_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.id = ?
              AND shared_decks.visibility = 'public'
            """,
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return None
        item_rows = connection.execute(
            """
            SELECT id, surface, base_form, reading, part_of_speech,
                   normalized_form, meaning_ko, dictionary_gloss,
                   context_explanation_ko, example_sentence, quality_tag, created_at
            FROM shared_deck_items
            WHERE shared_deck_id = ?
            ORDER BY id ASC
            """,
            (shared_deck_id,),
        ).fetchall()
        term_rows = connection.execute(
            """
            SELECT id, term, reading, part_of_speech, meaning_ko, description, created_at
            FROM shared_deck_terms
            WHERE shared_deck_id = ?
            ORDER BY id ASC
            """,
            (shared_deck_id,),
        ).fetchall()

    result = row_to_dict(deck)
    result["items"] = [row_to_dict(row) for row in item_rows]
    result["custom_terms"] = [row_to_dict(row) for row in term_rows]
    return result


def import_shared_deck(user_id: int, shared_deck_id: int) -> dict[str, Any] | None:
    timestamp = now_iso()
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT id, title, description
            FROM shared_decks
            WHERE id = ?
              AND visibility = 'public'
            """,
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return None

        deck_name = get_unique_imported_deck_name(connection, user_id, deck["title"])
        cursor = connection.execute(
            """
            INSERT INTO decks (user_id, name, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, deck_name, deck["description"] or "", timestamp, timestamp),
        )
        imported_deck_id = int(cursor.lastrowid)

        item_rows = connection.execute(
            """
            SELECT surface, base_form, reading, part_of_speech, normalized_form,
                   meaning_ko, dictionary_gloss, context_explanation_ko,
                   example_sentence, quality_tag
            FROM shared_deck_items
            WHERE shared_deck_id = ?
            ORDER BY id ASC
            """,
            (shared_deck_id,),
        ).fetchall()
        term_rows = connection.execute(
            """
            SELECT term, reading, part_of_speech, meaning_ko, description
            FROM shared_deck_terms
            WHERE shared_deck_id = ?
            ORDER BY id ASC
            """,
            (shared_deck_id,),
        ).fetchall()

        for row in item_rows:
            connection.execute(
                """
                INSERT INTO vocab_items (
                    user_id, deck_id, surface, base_form, reading, part_of_speech,
                    normalized_form, meaning_ko, dictionary_gloss, quality_tag,
                    context_explanation_ko, example_sentence, status,
                    correct_count, wrong_count, last_reviewed_at, review_level,
                    next_review_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unknown', 0, 0, NULL, 0, NULL, ?, ?)
                """,
                (
                    user_id,
                    imported_deck_id,
                    row["surface"] or row["base_form"] or "",
                    row["base_form"] or row["surface"] or "",
                    row["reading"] or "",
                    row["part_of_speech"] or "",
                    row["normalized_form"] or row["base_form"] or row["surface"] or "",
                    row["meaning_ko"] or "",
                    row["dictionary_gloss"] or "",
                    row["quality_tag"] or "normal",
                    row["context_explanation_ko"] or "",
                    row["example_sentence"] or "",
                    timestamp,
                    timestamp,
                ),
            )

        for row in term_rows:
            connection.execute(
                """
                INSERT INTO custom_terms (
                    user_id, term, reading, part_of_speech, meaning_ko,
                    description, deck_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    row["term"],
                    row["reading"] or "",
                    row["part_of_speech"] or "\uba85\uc0ac",
                    row["meaning_ko"] or "",
                    row["description"] or "",
                    imported_deck_id,
                    timestamp,
                    timestamp,
                ),
            )

        connection.execute(
            """
            UPDATE shared_decks
            SET import_count = import_count + 1, updated_at = ?
            WHERE id = ?
            """,
            (timestamp, shared_deck_id),
        )
        connection.execute(
            """
            INSERT INTO shared_deck_imports (
                shared_deck_id, user_id, imported_deck_id, imported_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (shared_deck_id, user_id, imported_deck_id, timestamp),
        )

    return {
        "deck_id": imported_deck_id,
        "deck_name": deck_name,
        "imported_vocab_count": len(item_rows),
        "imported_custom_term_count": len(term_rows),
        "message": "\uacf5\uc720 \ub371\uc744 \ub0b4 \ub2e8\uc5b4\uc7a5\uc73c\ub85c \uac00\uc838\uc654\uc2b5\ub2c8\ub2e4.",
    }


def get_unique_imported_deck_name(
    connection: sqlite3.Connection, user_id: int, original_name: str
) -> str:
    base_name = original_name.strip() or "\uac00\uc838\uc628 \ub371"
    existing_names = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM decks WHERE user_id = ?", (user_id,)
        ).fetchall()
    }
    if base_name not in existing_names:
        return base_name

    first_candidate = f"{base_name} (\uac00\uc838\uc634)"
    if first_candidate not in existing_names:
        return first_candidate

    suffix = 2
    while True:
        candidate = f"{base_name} (\uac00\uc838\uc634 {suffix})"
        if candidate not in existing_names:
            return candidate
        suffix += 1
