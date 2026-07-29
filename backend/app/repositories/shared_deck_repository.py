from __future__ import annotations

import sqlite3
from typing import Any

from app.database import get_connection, now_iso, row_to_dict
from app.repositories.lexeme_repository import (
    add_word_to_shared_deck,
    count_shared_deck_words,
    get_or_create_subscription,
    is_lexeme_deck,
    is_lexeme_deck_in_connection,
    list_lexeme_deck_ids,
    list_shared_deck_words_with_progress,
    upsert_lexeme,
)


def shared_deck_exists(shared_deck_id: int) -> bool:
    """Cheap existence check -- does not build the full word-list overlay,
    unlike get_shared_deck(). Used for surfaces that must stay closed to
    everyone once a deck is unpublished (new import/list/detail) -- see
    shared_deck_word_access_allowed() below for the write-endpoint guard,
    which is deliberately NOT this function.
    """
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM shared_decks WHERE id = ? AND visibility = 'public'",
            (shared_deck_id,),
        ).fetchone()
    return row is not None


def shared_deck_word_access_allowed(
    shared_deck_id: int, user_id: int, lexeme_id: int
) -> bool:
    """Write-endpoint guard for a lexeme-mode shared deck's per-word
    review/status endpoints (see docs/architecture/shared-lexeme-progress-storage.md
    -- "owner unpublish" policy). A still-public deck is open to anyone; once
    the owner unpublishes it (visibility flips away from 'public', see
    delete_shared_deck() below -- the row is never hard-deleted), it only
    stays writable for a user who already holds an active
    user_deck_subscriptions row. A brand new user can never reach this
    allowance since import_shared_deck()/get_shared_deck() keep requiring
    visibility='public', so unpublish still fully blocks new adoption --
    only existing subscribers keep their reference-based (no bulk copy)
    review/status access. The lexeme must also belong to this shared deck:
    owning/subscribing to one deck must not become a generic permission to
    mutate progress for an unrelated shared word.
    """
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT shared_decks.visibility
            FROM shared_decks
            JOIN shared_deck_words
              ON shared_deck_words.shared_deck_id = shared_decks.id
            WHERE shared_decks.id = ?
              AND shared_deck_words.lexeme_id = ?
            """,
            (shared_deck_id, lexeme_id),
        ).fetchone()
        if not row:
            return False
        if row["visibility"] == "public":
            return True
        subscription = connection.execute(
            """
            SELECT 1 FROM user_deck_subscriptions
            WHERE user_id = ? AND shared_deck_id = ? AND is_active = TRUE
            """,
            (user_id, shared_deck_id),
        ).fetchone()
        return subscription is not None


def publish_deck(
    user_id: int, deck_id: int, title: str, description: str
) -> dict[str, Any] | None:
    """Publishes a personal deck as a new shared deck.

    Default (and only) behavior as of the lexeme-mode publish change (see
    docs/architecture/shared-lexeme-progress-storage.md "User-published
    shared decks"): every word -- both vocab_items and custom_terms -- is
    upserted into the shared `lexemes` table and linked via
    `shared_deck_words`, exactly like a JLPT-registered deck. Nothing is
    written to the legacy `shared_deck_items`/`shared_deck_terms` tables for
    a *new* publish; those tables and any shared deck published before this
    change are left completely alone (read/import compatibility is
    unaffected -- see is_lexeme_deck()/get_shared_deck()/import_shared_deck()
    below, which still serve legacy decks from those tables).

    vocab_count/custom_term_count on the returned dict (and on the
    shared_decks row) keep their original meaning -- counts of the
    publisher's source vocab_items/custom_terms -- so the response shape
    and any "N\uac1c \ub2e8\uc5b4 + M\uac1c \ucee4\uc2a4\ud140 \uc6a9\uc5b4" style label stay unchanged even
    though both now live in the same underlying shared_deck_words list.
    """
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

    # upsert_lexeme/add_word_to_shared_deck open their own connections (see
    # lexeme_repository.py) so this runs after the `with` block above closes
    # the first connection/transaction.
    sort_order = 0
    for row in vocab_rows:
        surface = row["surface"] or row["base_form"] or ""
        base_form = row["base_form"] or row["surface"] or ""
        lexeme_id = upsert_lexeme(
            surface=surface,
            base_form=base_form,
            reading=row["reading"] or "",
            part_of_speech=row["part_of_speech"] or "",
            meaning_ko=row["meaning_ko"] or "",
            dictionary_gloss=row["dictionary_gloss"] or "",
            source_type="user_published_deck",
            # A publisher must never clobber an existing shared word's
            # common meaning with their own personal wording -- see
            # upsert_lexeme()'s docstring.
            refresh_shared_fields=False,
        )
        add_word_to_shared_deck(
            shared_deck_id,
            lexeme_id,
            sort_order,
            # Always snapshot the publisher's own wording for *this* deck so
            # it's shown even when the shared lexeme keeps a different,
            # earlier meaning_ko (nothing the publisher shared is lost).
            display_meaning_ko=row["meaning_ko"] or None,
            example_sentence=row["example_sentence"] or None,
            context_explanation_ko=row["context_explanation_ko"] or None,
        )
        sort_order += 1

    for row in term_rows:
        lexeme_id = upsert_lexeme(
            surface=row["term"],
            base_form=row["term"],
            reading=row["reading"] or "",
            part_of_speech=row["part_of_speech"] or "",
            meaning_ko=row["meaning_ko"] or "",
            source_type="user_published_custom_term",
            refresh_shared_fields=False,
        )
        add_word_to_shared_deck(
            shared_deck_id,
            lexeme_id,
            sort_order,
            display_meaning_ko=row["meaning_ko"] or None,
            # custom_terms has no example_sentence field; its `description`
            # is the closest equivalent to a short deck-specific note, so it
            # maps to the context_explanation_ko snapshot slot instead of
            # being dropped.
            context_explanation_ko=row["description"] or None,
        )
        sort_order += 1

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
    #
    # Phase 7 Round 1 (see docs/architecture/shared-lexeme-progress-storage.md
    # "Owner unpublish policy" update): the WHERE clause below is no longer
    # unconditionally `visibility = 'public'`. A logged-in owner/subscriber
    # now also matches on `owner_user_id = ?` / an active
    # user_deck_subscriptions row, so an unpublished deck reappears on their
    # own list. When user_id is None, both of those extra params bind to
    # NULL, `owner_user_id = NULL` and `user_id = NULL` in the EXISTS
    # subquery are never true in SQLite/PostgreSQL, so the clause collapses
    # back to the original public-only behavior -- no separate code path
    # needed for the logged-out case.
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   shared_decks.owner_user_id, users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at,
                   shared_decks.visibility,
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
                             AND user_deck_subscriptions.is_active = TRUE
                       )
                   ) AS imported_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.visibility = 'public'
               OR shared_decks.owner_user_id = ?
               OR EXISTS (
                   SELECT 1 FROM user_deck_subscriptions
                   WHERE user_deck_subscriptions.shared_deck_id = shared_decks.id
                     AND user_deck_subscriptions.user_id = ?
                     AND user_deck_subscriptions.is_active = TRUE
               )
            ORDER BY shared_decks.created_at DESC, shared_decks.id DESC
            """,
            (user_id, user_id, user_id, user_id),
        ).fetchall()
    results = [row_to_dict(row) for row in rows]
    lexeme_deck_ids = list_lexeme_deck_ids()
    for result in results:
        result["is_owner"] = user_id is not None and result["owner_user_id"] == user_id
        result["mode"] = "subscribed" if result["id"] in lexeme_deck_ids else "copied"
        result["is_published"] = result.pop("visibility") == "public"
    return results


def get_shared_deck(
    shared_deck_id: int, user_id: int | None = None, due_only: bool = False
) -> dict[str, Any] | None:
    # Phase 7 Round 1: same access widening as list_shared_decks() above --
    # owner/active-subscriber can still reach detail after unpublish, a new
    # or logged-out user (user_id=None) still gets the public-only behavior
    # (extra params bind to NULL and the OR branches never match).
    with get_connection() as connection:
        deck = connection.execute(
            """
            SELECT shared_decks.id, shared_decks.title, shared_decks.description,
                   shared_decks.owner_user_id, users.display_name AS owner_display_name,
                   shared_decks.vocab_count, shared_decks.custom_term_count,
                   shared_decks.import_count, shared_decks.created_at,
                   shared_decks.updated_at, shared_decks.visibility,
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
                             AND user_deck_subscriptions.is_active = TRUE
                       )
                   ) AS imported_at
            FROM shared_decks
            LEFT JOIN users ON users.id = shared_decks.owner_user_id
            WHERE shared_decks.id = ?
              AND (
                  shared_decks.visibility = 'public'
                  OR shared_decks.owner_user_id = ?
                  OR EXISTS (
                      SELECT 1 FROM user_deck_subscriptions
                      WHERE user_deck_subscriptions.shared_deck_id = shared_decks.id
                        AND user_deck_subscriptions.user_id = ?
                        AND user_deck_subscriptions.is_active = TRUE
                  )
              )
            """,
            (user_id, user_id, shared_deck_id, user_id, user_id),
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
    result["mode"] = "subscribed" if lexeme_mode else "copied"
    result["is_published"] = result.pop("visibility") == "public"
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
    """Unpublish a shared deck: soft-unpublish only (see
    docs/architecture/shared-lexeme-progress-storage.md -- "owner unpublish
    policy"). Flips shared_decks.visibility away from 'public' so the deck
    disappears from public list/detail/import for everyone new -- it never
    hard-deletes the shared_decks row (or shared_deck_items/terms/imports/
    shared_deck_words/user_deck_subscriptions/user_word_progress). That is
    what lets an existing subscriber keep reviewing the deck's words through
    their own subscription/progress rows afterwards (see
    shared_deck_word_access_allowed() above) without any bulk copy into
    their personal vocab_items -- exactly the same reference-based storage
    the deck used while it was public. Never touches personal
    decks/vocab_items, including copies other users already imported from
    this shared deck.
    """
    with get_connection() as connection:
        deck = connection.execute(
            "SELECT id, owner_user_id, title, visibility FROM shared_decks WHERE id = ?",
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return "not_found"
        if int(deck["owner_user_id"]) != user_id:
            return "forbidden"

        title = deck["title"]
        if deck["visibility"] == "public":
            connection.execute(
                "UPDATE shared_decks SET visibility = 'unpublished', updated_at = ? WHERE id = ?",
                (now_iso(), shared_deck_id),
            )

    return {
        "shared_deck_id": shared_deck_id,
        "title": title,
        "message": "공유를 취소했습니다. 이미 가져간 개인 덱은 유지됩니다.",
    }


def republish_shared_deck(user_id: int, shared_deck_id: int) -> dict[str, Any] | str:
    """Owner-only reversal of delete_shared_deck() above (see
    docs/architecture/shared-lexeme-progress-storage.md -- "Owner unpublish
    policy", Phase 7 Round 5 republish decision). Only flips
    shared_decks.visibility back to 'public' when it isn't already --
    never touches shared_deck_items/terms/imports/shared_deck_words/
    user_deck_subscriptions/user_word_progress, so an existing subscriber's
    progress is untouched (nothing was touched by unpublish either) and no
    bulk copy is ever introduced. Once visibility is back to 'public',
    list_shared_decks()/get_shared_deck()/import_shared_deck() all pick the
    deck back up for a brand new user automatically, since they already
    gate on visibility='public' -- no separate re-enable logic needed
    there. Deliberately does not touch title/description: there is no
    shared-deck-detail edit surface today, so republish is a pure
    visibility flip, nothing more.
    """
    with get_connection() as connection:
        deck = connection.execute(
            "SELECT id, owner_user_id, title, visibility FROM shared_decks WHERE id = ?",
            (shared_deck_id,),
        ).fetchone()
        if not deck:
            return "not_found"
        if int(deck["owner_user_id"]) != user_id:
            return "forbidden"

        title = deck["title"]
        if deck["visibility"] != "public":
            connection.execute(
                "UPDATE shared_decks SET visibility = 'public', updated_at = ? WHERE id = ?",
                (now_iso(), shared_deck_id),
            )

    return {
        "shared_deck_id": shared_deck_id,
        "title": title,
        "message": "다시 공유했습니다. 새 사용자도 이제 가져올 수 있어요.",
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
