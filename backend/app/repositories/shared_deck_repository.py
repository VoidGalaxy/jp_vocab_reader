from __future__ import annotations

import sqlite3
from typing import Any

from app.database import get_connection, now_iso, row_to_dict
from app.repositories.lexeme_repository import (
    count_shared_deck_words,
    get_or_create_subscription,
    is_lexeme_deck,
    is_lexeme_deck_in_connection,
    list_shared_deck_words_with_progress,
)


def shared_deck_exists(shared_deck_id: int) -> bool:
    """Cheap existence check -- does not build the full word-list overlay,
    unlike get_shared_deck(). Used by the word-progress/review endpoints,
    which only need a 404 guard, not the whole deck detail payload.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM shared_decks WHERE id = ? AND visibility = 'public'",
            (shared_deck_id,),
        ).fetchone()
    return row is not None


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


def list_shared_decks(user_id: int | None = None) -> list[dict[str, Any]]:
    # COALESCE covers both import paths: the legacy shared_deck_imports row
    # (personal deck was copied) and the new user_deck_subscriptions row
    # (lexeme-mode deck, nothing copied) -- whichever one exists for this
    # deck/user is what "가져옴" should reflect.
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   shared_decks.owner_user_id, users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at,
                   COALESCE(
                       (
                           SELECT MAX(shared_deck_imports.imported_at)
                           FROM shared_deck_imports
                           WHERE shared_deck_imports.shared_deck_id = shared_decks.id
                             AND shared_deck_imports.user_id = ?
                       ),
                       (
                           SELECT MAX(user_deck_subscriptions.imported_at)
                           FROM user_deck_subscriptions
                           WHERE user_deck_subscriptions.shared_deck_id = shared_decks.id
                             AND user_deck_subscriptions.user_id = ?
                             AND user_deck_subscriptions.is_active = 1
                       )
                   ) AS imported_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.visibility = 'public'
            ORDER BY shared_decks.created_at DESC, shared_decks.id DESC
            """,
            (user_id, user_id),
        ).fetchall()
    results = [row_to_dict(row) for row in rows]
    for result in results:
        result["is_owner"] = user_id is not None and result["owner_user_id"] == user_id
    return results


def get_shared_deck(
    shared_deck_id: int, user_id: int | None = None, due_only: bool = False
) -> dict[str, Any] | None:
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   shared_decks.owner_user_id, users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at,
                   shared_decks.updated_at,
                   COALESCE(
                       (
                           SELECT MAX(shared_deck_imports.imported_at)
                           FROM shared_deck_imports
                           WHERE shared_deck_imports.shared_deck_id = shared_decks.id
                             AND shared_deck_imports.user_id = ?
                       ),
                       (
                           SELECT MAX(user_deck_subscriptions.imported_at)
                           FROM user_deck_subscriptions
                           WHERE user_deck_subscriptions.shared_deck_id = shared_decks.id
                             AND user_deck_subscriptions.user_id = ?
                             AND user_deck_subscriptions.is_active = 1
                       )
                   ) AS imported_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.id = ?
              AND shared_decks.visibility = 'public'
            """,
            (user_id, user_id, shared_deck_id),
        ).fetchone()
        if not deck:
            return None
        lexeme_mode = is_lexeme_deck_in_connection(connection, shared_deck_id)
        item_rows = []
        term_rows = []
        if not lexeme_mode:
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
    result["is_owner"] = user_id is not None and result["owner_user_id"] == user_id
    if lexeme_mode:
        # Word data lives in lexemes/shared_deck_words, overlaid with this
        # user's progress (see docs/architecture/shared-lexeme-progress-storage.md)
        # -- a word with no progress row still appears, just as unclassified.
        words = list_shared_deck_words_with_progress(
            shared_deck_id, user_id, due_only=due_only
        )
        result["items"] = [{**word, "id": word["lexeme_id"]} for word in words]
        result["custom_terms"] = []
    else:
        result["items"] = [row_to_dict(row) for row in item_rows]
        result["custom_terms"] = [row_to_dict(row) for row in term_rows]
    return result


def delete_shared_deck(user_id: int, shared_deck_id: int) -> dict[str, Any] | str:
    """Unpublish a shared deck: removes the shared_decks row and its
    shared_deck_items/shared_deck_terms/shared_deck_imports rows only.
    Never touches personal decks/vocab_items, including copies other
    users already imported from this shared deck.
    """
    with get_connection() as connection:
        deck = connection.execute(
            "SELECT id, owner_user_id, title FROM shared_decks WHERE id = ?",
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return "not_found"
        if int(deck["owner_user_id"]) != user_id:
            return "forbidden"

        title = deck["title"]
        connection.execute(
            "DELETE FROM shared_deck_items WHERE shared_deck_id = ?", (shared_deck_id,)
        )
        connection.execute(
            "DELETE FROM shared_deck_terms WHERE shared_deck_id = ?", (shared_deck_id,)
        )
        connection.execute(
            "DELETE FROM shared_deck_imports WHERE shared_deck_id = ?", (shared_deck_id,)
        )
        connection.execute("DELETE FROM shared_decks WHERE id = ?", (shared_deck_id,))

    return {
        "shared_deck_id": shared_deck_id,
        "title": title,
        "message": "공유를 취소했습니다. 이미 가져간 개인 덱은 유지됩니다.",
    }


def import_shared_deck(user_id: int, shared_deck_id: int) -> dict[str, Any] | None:
    """Dispatches on how this shared deck's words are stored:

    - lexeme-mode deck (has shared_deck_words rows, e.g. anything the JLPT
      register script creates from now on): only a user_deck_subscriptions
      row is written. No vocab_items are copied, so importing the same
      recommended deck for 10,000 users no longer means 10,000x the word
      rows -- see docs/architecture/shared-lexeme-progress-storage.md.
    - legacy deck (shared_deck_items only, e.g. anything published from a
      personal deck before this change): unchanged copy-into-vocab_items
      behavior, so existing shared decks keep working exactly as before.
    """
    if is_lexeme_deck(shared_deck_id):
        return _import_lexeme_shared_deck(user_id, shared_deck_id)
    return _import_shared_deck_legacy(user_id, shared_deck_id)


def _import_lexeme_shared_deck(
    user_id: int, shared_deck_id: int
) -> dict[str, Any] | None:
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT id, title
            FROM shared_decks
            WHERE id = ?
              AND visibility = 'public'
            """,
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return None

    word_count = count_shared_deck_words(shared_deck_id)
    _subscription, created = get_or_create_subscription(user_id, shared_deck_id)

    if created:
        timestamp = now_iso()
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE shared_decks
                SET import_count = import_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, shared_deck_id),
            )
        message = "추천 어휘 덱을 내 학습 목록에 추가했어요."
    else:
        message = "이미 내 학습 목록에 있는 추천 어휘 덱이에요."

    return {
        "success": True,
        "mode": "subscribed",
        "subscribed": True,
        "shared_deck_id": shared_deck_id,
        "word_count": word_count,
        # Kept populated (not null) for any older client code that still
        # reads these -- no personal deck exists for a lexeme-mode import,
        # so deck_id is the shared deck itself and nothing was "copied".
        "deck_id": shared_deck_id,
        "deck_name": deck["title"],
        "imported_vocab_count": word_count,
        "imported_custom_term_count": 0,
        "message": message,
    }


def _import_shared_deck_legacy(
    user_id: int, shared_deck_id: int
) -> dict[str, Any] | None:
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
        "success": True,
        "mode": "copied",
        "subscribed": False,
        "shared_deck_id": shared_deck_id,
        "word_count": len(item_rows),
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
