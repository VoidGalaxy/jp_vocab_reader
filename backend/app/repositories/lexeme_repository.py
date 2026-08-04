from __future__ import annotations

from typing import Any

from app.database import (
    compute_review_schedule,
    get_connection,
    now_iso,
    now_utc,
    row_to_dict,
)
from app.schemas import VALID_STATUSES

_PROGRESS_FIELDS = """
    id, user_id, lexeme_id, status, review_level, next_review_at,
    correct_count, wrong_count, last_reviewed_at, created_at, updated_at
"""


def is_lexeme_deck(shared_deck_id: int) -> bool:
    """A shared deck is "lexeme-based" once it has at least one
    shared_deck_words row -- legacy decks (published from a personal deck
    the old way) never get one, so they keep using the existing
    shared_deck_items/vocab_items copy path untouched.
    """
    with get_connection() as connection:
        return is_lexeme_deck_in_connection(connection, shared_deck_id)


def is_lexeme_deck_in_connection(connection: Any, shared_deck_id: int) -> bool:
    row = connection.execute(
        "SELECT 1 FROM shared_deck_words WHERE shared_deck_id = ? LIMIT 1",
        (shared_deck_id,),
    ).fetchone()
    return row is not None


def list_lexeme_deck_ids() -> set[int]:
    """All shared_deck_ids that are lexeme-mode -- one query, so
    list_shared_decks() can tag every row's `mode` without an N+1 check
    per deck.
    """
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT shared_deck_id FROM shared_deck_words"
        ).fetchall()
    return {int(row["shared_deck_id"]) for row in rows}


def upsert_lexeme(
    surface: str,
    base_form: str,
    reading: str = "",
    part_of_speech: str = "",
    meaning_ko: str = "",
    dictionary_gloss: str = "",
    jlpt_level: str | None = None,
    source_type: str = "shared_deck",
    refresh_shared_fields: bool = True,
) -> int:
    """Find-or-create a lexeme keyed by (base_form, reading, part_of_speech).

    This is the one place a shared word's *common* fields (meaning_ko,
    dictionary_gloss, jlpt_level) are written -- re-running a JLPT package
    registration refreshes them here (refresh_shared_fields=True, the
    default, matches JLPT-script/curated callers). Never call this to store
    a user's personal meaning edit; that stays on vocab_items as it always
    has.

    A publisher of their own shared deck must NOT be able to clobber this
    shared row's meaning_ko/dictionary_gloss just because their personal
    vocab_item had different wording -- pass refresh_shared_fields=False
    (see publish_deck() in shared_deck_repository.py) so an existing match
    is reused as-is (only jlpt_level is opportunistically filled in if it
    was previously unset). The publisher's own wording is preserved
    separately as a deck-specific snapshot on shared_deck_words, not lost.
    """
    timestamp = now_iso()
    base_form = (base_form or surface or "").strip() or surface.strip()
    surface = surface.strip() or base_form
    reading = (reading or "").strip()
    part_of_speech = (part_of_speech or "").strip()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id FROM lexemes
            WHERE base_form = ? AND reading = ? AND part_of_speech = ?
            """,
            (base_form, reading, part_of_speech),
        ).fetchone()
        if existing:
            lexeme_id = int(existing["id"])
            if refresh_shared_fields:
                connection.execute(
                    """
                    UPDATE lexemes
                    SET surface = ?,
                        meaning_ko = ?,
                        dictionary_gloss = ?,
                        jlpt_level = COALESCE(?, jlpt_level),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        surface,
                        meaning_ko.strip(),
                        dictionary_gloss.strip(),
                        jlpt_level,
                        timestamp,
                        lexeme_id,
                    ),
                )
            else:
                connection.execute(
                    """
                    UPDATE lexemes
                    SET jlpt_level = COALESCE(jlpt_level, ?),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (jlpt_level, timestamp, lexeme_id),
                )
            return lexeme_id

        cursor = connection.execute(
            """
            INSERT INTO lexemes (
                surface, base_form, reading, part_of_speech, meaning_ko,
                dictionary_gloss, jlpt_level, source_type, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                surface,
                base_form,
                reading,
                part_of_speech,
                meaning_ko.strip(),
                dictionary_gloss.strip(),
                jlpt_level,
                source_type,
                timestamp,
                timestamp,
            ),
        )
        return int(cursor.lastrowid)


def add_word_to_shared_deck(
    shared_deck_id: int,
    lexeme_id: int,
    sort_order: int,
    *,
    display_meaning_ko: str | None = None,
    example_sentence: str | None = None,
    context_explanation_ko: str | None = None,
    tags_json: str | None = None,
    published_note: str | None = None,
) -> None:
    """Idempotent upsert on (shared_deck_id, lexeme_id): republishing/
    re-registering the same deck refreshes sort_order and the deck-specific
    snapshot fields in place rather than creating a duplicate
    shared_deck_words row (the UNIQUE(shared_deck_id, lexeme_id) constraint
    plus ON CONFLICT DO UPDATE below is what guarantees that).
    """
    timestamp = now_iso()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO shared_deck_words (
                shared_deck_id, lexeme_id, sort_order, created_at,
                display_meaning_ko, example_sentence, context_explanation_ko,
                tags_json, published_note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (shared_deck_id, lexeme_id) DO UPDATE SET
                sort_order = excluded.sort_order,
                display_meaning_ko = excluded.display_meaning_ko,
                example_sentence = excluded.example_sentence,
                context_explanation_ko = excluded.context_explanation_ko,
                tags_json = excluded.tags_json,
                published_note = excluded.published_note
            """,
            (
                shared_deck_id,
                lexeme_id,
                sort_order,
                timestamp,
                display_meaning_ko,
                example_sentence,
                context_explanation_ko,
                tags_json,
                published_note,
            ),
        )


def count_shared_deck_words(shared_deck_id: int) -> int:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM shared_deck_words WHERE shared_deck_id = ?",
            (shared_deck_id,),
        ).fetchone()
    return int(row["count"]) if row else 0


def get_or_create_subscription(
    user_id: int, shared_deck_id: int
) -> tuple[dict[str, Any], bool]:
    """Returns (subscription, created). Re-importing an already-subscribed
    deck is idempotent: no duplicate row, existing row just gets
    reactivated if it had been unsubscribed.
    """
    timestamp = now_iso()
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id, user_id, shared_deck_id, is_active, imported_at,
                   created_at, updated_at
            FROM user_deck_subscriptions
            WHERE user_id = ? AND shared_deck_id = ?
            """,
            (user_id, shared_deck_id),
        ).fetchone()
        if existing:
            if not existing["is_active"]:
                connection.execute(
                    """
                    UPDATE user_deck_subscriptions
                    SET is_active = TRUE, updated_at = ?
                    WHERE id = ?
                    """,
                    (timestamp, existing["id"]),
                )
            return row_to_dict(existing), False

        cursor = connection.execute(
            """
            INSERT INTO user_deck_subscriptions (
                user_id, shared_deck_id, is_active, imported_at, created_at, updated_at
            )
            VALUES (?, ?, TRUE, ?, ?, ?)
            """,
            (user_id, shared_deck_id, timestamp, timestamp, timestamp),
        )
        row = connection.execute(
            """
            SELECT id, user_id, shared_deck_id, is_active, imported_at,
                   created_at, updated_at
            FROM user_deck_subscriptions
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return row_to_dict(row), True


def list_subscribed_shared_deck_ids(user_id: int) -> set[int]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT shared_deck_id
            FROM user_deck_subscriptions
            WHERE user_id = ? AND is_active = TRUE
            """,
            (user_id,),
        ).fetchall()
    return {int(row["shared_deck_id"]) for row in rows}


def _normalize_progress_overlay(item: dict[str, Any]) -> dict[str, Any]:
    item["status"] = item.get("status") or "unclassified"
    item["review_level"] = item.get("review_level") or 0
    item["correct_count"] = item.get("correct_count") or 0
    item["wrong_count"] = item.get("wrong_count") or 0
    # Deck-specific published snapshot wins over the shared lexeme's common
    # meaning -- lets a publisher's own wording show in their deck without
    # ever overwriting lexemes.meaning_ko, which other decks/users share
    # (see docs/architecture/shared-lexeme-progress-storage.md).
    lexeme_meaning_ko = item.pop("lexeme_meaning_ko", None)
    display_meaning_ko = item.pop("display_meaning_ko", None)
    item["meaning_ko"] = display_meaning_ko or lexeme_meaning_ko or ""
    return item


def list_shared_deck_words_with_progress(
    shared_deck_id: int,
    user_id: int,
    due_only: bool = False,
    limit: int | None = None,
    exclude_known: bool = False,
) -> list[dict[str, Any]]:
    """shared_deck_words + lexemes, left-joined with this user's
    user_word_progress. A word with no progress row still comes back (as
    unclassified/level 0/no dates) when due_only is False -- it must never
    be dropped just because the user hasn't touched it yet.

    due_only's "due" definition is deliberately kept identical to
    get_subscribed_lexeme_stats_summary()'s due_count (Phase 20 Round 1, see
    docs/architecture/shared-lexeme-progress-storage.md): a lexeme with no
    user_word_progress row yet, or with status still 'unclassified', is
    "new", not "due" -- it belongs in the new/unclassified study path, not
    the due-today one. Before this change due_only also matched
    progress-less/unclassified rows, so subscribing to a large lexeme deck
    (e.g. JLPT N1) flooded the due-today queue with every never-reviewed
    word at once, even though /stats reported 0 due for the same lexemes.

    limit (Phase 21 Round 1): pushed down as a real SQL LIMIT, not a
    post-fetch Python slice -- safe to do exactly here because
    shared_deck_words has a UNIQUE(shared_deck_id, lexeme_id) constraint, so
    within one deck there is no cross-row duplication to worry about; the
    ORDER BY (backed by the existing idx_shared_deck_words_deck(shared_deck_id,
    sort_order) index) still fully determines which rows the database
    returns first. `?` placeholders are adapted to `%s` for PostgreSQL by
    the existing adapt_query() in app/database.py the same way every other
    placeholder in this query already is, so plain `LIMIT ?` needs no
    engine-specific handling. Omitting limit (None) keeps the previous
    full-scan behavior unchanged -- only list_subscribed_lexeme_study_items'
    single-shared_deck_id path passes it through; the multi-deck "all mode"
    merge still fetches full per-deck results and slices in Python, because
    a lexeme can appear in more than one subscribed deck, which a per-deck
    SQL LIMIT could under-fill after cross-deck dedup (see Round 0 writeup
    in docs/architecture/shared-lexeme-progress-storage.md).

    exclude_known (Phase 22 Round 1): drops rows whose progress status is
    exactly 'known', applied in the WHERE clause -- i.e. before ORDER BY and
    before limit -- so a caller combining exclude_known=True with limit gets
    up to `limit` non-known rows, not "up to `limit` rows, then whatever's
    left after a caller-side known filter" (which is what
    list_subscribed_lexeme_study_items + GET /study-items/lexemes used to
    do: the limit was applied first, known was filtered out of that already-
    limited slice afterwards in main.py, so a deck with known words sorted
    early could return fewer than `limit` items even though enough
    non-known words existed further down the deck). A progress-less row
    (status IS NULL, i.e. "new") is never dropped by this -- only an actual
    'known' status is. Combining this with due_only=True is redundant but
    harmless: due_only's own clause already restricts to
    status IN ('unknown', 'uncertain'), which can never include 'known', so
    the two conditions never disagree. Defaults to False so the deck-detail
    caller (get_shared_deck_data() in shared_deck_repository.py) keeps
    showing known words unchanged -- only list_subscribed_lexeme_study_items
    (the study-queue path behind GET /study-items/lexemes, which never wants
    known words back regardless of due_only/limit) passes True.
    """
    params: list[Any] = [user_id, shared_deck_id]
    due_clause = ""
    if due_only:
        due_clause = """
              AND user_word_progress.status IN ('unknown', 'uncertain')
              AND (
                  user_word_progress.next_review_at IS NULL
                  OR user_word_progress.next_review_at <= ?
              )
        """
        params.append(now_iso())

    exclude_known_clause = ""
    if exclude_known:
        exclude_known_clause = """
              AND (
                  user_word_progress.status IS NULL
                  OR user_word_progress.status != 'known'
              )
        """

    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)

    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                lexemes.id AS lexeme_id,
                lexemes.surface, lexemes.base_form, lexemes.reading,
                lexemes.part_of_speech,
                lexemes.meaning_ko AS lexeme_meaning_ko,
                lexemes.dictionary_gloss, lexemes.jlpt_level,
                shared_deck_words.sort_order,
                shared_deck_words.created_at,
                shared_deck_words.display_meaning_ko,
                shared_deck_words.example_sentence,
                shared_deck_words.context_explanation_ko,
                user_word_progress.status,
                user_word_progress.review_level,
                user_word_progress.next_review_at,
                user_word_progress.correct_count,
                user_word_progress.wrong_count
            FROM shared_deck_words
            JOIN lexemes ON lexemes.id = shared_deck_words.lexeme_id
            LEFT JOIN user_word_progress
                ON user_word_progress.lexeme_id = lexemes.id
               AND user_word_progress.user_id = ?
            WHERE shared_deck_words.shared_deck_id = ?
            {due_clause}
            {exclude_known_clause}
            ORDER BY shared_deck_words.sort_order ASC, shared_deck_words.id ASC
            {limit_clause}
            """,
            tuple(params),
        ).fetchall()
    return [_normalize_progress_overlay(row_to_dict(row)) for row in rows]


def _get_progress_row(connection: Any, user_id: int, lexeme_id: int) -> Any:
    return connection.execute(
        f"SELECT {_PROGRESS_FIELDS} FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
        (user_id, lexeme_id),
    ).fetchone()


def get_or_create_progress(
    connection: Any, user_id: int, lexeme_id: int
) -> dict[str, Any]:
    """Lazy create: only ever called from an endpoint that represents a real
    user action (status change, review rating) -- never from deck import or
    deck listing, which is the whole point of this table.
    """
    row = _get_progress_row(connection, user_id, lexeme_id)
    if row:
        return row_to_dict(row)

    timestamp = now_iso()
    connection.execute(
        """
        -- TODO(postgres): INSERT OR IGNORE is SQLite-specific; adapt_query()
        -- rewrites this to ON CONFLICT DO NOTHING for PostgreSQL.
        INSERT OR IGNORE INTO user_word_progress (
            user_id, lexeme_id, status, review_level, correct_count,
            wrong_count, created_at, updated_at
        )
        VALUES (?, ?, 'unclassified', 0, 0, 0, ?, ?)
        """,
        (user_id, lexeme_id, timestamp, timestamp),
    )
    row = _get_progress_row(connection, user_id, lexeme_id)
    return row_to_dict(row)


def update_word_status(
    user_id: int, lexeme_id: int, new_status: str
) -> dict[str, Any] | None:
    if new_status not in VALID_STATUSES:
        raise ValueError(f"invalid status: {new_status}")

    timestamp = now_iso()
    with get_connection() as connection:
        lexeme = connection.execute(
            "SELECT id FROM lexemes WHERE id = ?", (lexeme_id,)
        ).fetchone()
        if not lexeme:
            return None

        get_or_create_progress(connection, user_id, lexeme_id)
        connection.execute(
            """
            UPDATE user_word_progress
            SET status = ?, updated_at = ?
            WHERE user_id = ? AND lexeme_id = ?
            """,
            (new_status, timestamp, user_id, lexeme_id),
        )
        row = _get_progress_row(connection, user_id, lexeme_id)
    return row_to_dict(row)


# Phase 6 (see docs/architecture/shared-lexeme-progress-storage.md --
# "Phase 6: lexeme SRS status policy"): a lazily-created user_word_progress
# row defaults to status='unclassified' (get_or_create_progress), and rating
# alone never used to change it -- so a lexeme rated "good"/"hard"/"again"
# advanced its review_level but stayed 'unclassified' forever, which drops
# it out of new_count (review_level > 0) without ever qualifying for
# due_count/hard_count (both require status IN ('unknown','uncertain')).
# This mapping is the one-time auto-correction applied on a word's FIRST
# rating only (see record_lexeme_review below) -- never applied again once
# a real status exists (user-set or previously auto-corrected).
_RATING_TO_AUTO_STATUS = {
    "again": "unknown",
    "hard": "uncertain",
    "good": "uncertain",
    "easy": "known",
}


def record_lexeme_review(
    user_id: int, lexeme_id: int, rating: str, shared_deck_id: int | None = None
) -> dict[str, Any] | None:
    """Same fixed-step SRS ladder as vocab_items (compute_review_schedule),
    applied to a lazily-created user_word_progress row instead.

    Phase 4 (see docs/architecture/shared-lexeme-progress-storage.md --
    "Phase 4: lexeme review logs"): also writes one row to the additive
    `lexeme_review_logs` table, in the same call that updates
    user_word_progress -- never on its own. review_logs (vocab_items'
    review history) is completely untouched by this function; its
    vocab_item_id NOT NULL FK has no room for a lexeme-keyed review, which
    is exactly why lexeme_review_logs is a separate table instead of trying
    to retrofit that one. `shared_deck_id` is optional context (which deck
    the rating was made through) -- a caller that only has a lexeme_id
    (no deck context) can still log by passing None.

    Phase 6: also corrects `status` away from 'unclassified' on a word's
    first rating, via `_RATING_TO_AUTO_STATUS` above -- but ONLY when the
    current status is still 'unclassified' (or, defensively, missing
    entirely). A status the user already set explicitly (via
    update_word_status(), or a previous auto-correction) is never
    overwritten by a later rating -- vocab_items' own record_review() never
    touches status either way, and this function still doesn't touch
    vocab_items/review_logs at all.
    """
    reviewed_at = now_utc()
    timestamp = reviewed_at.isoformat()
    with get_connection() as connection:
        lexeme = connection.execute(
            "SELECT id FROM lexemes WHERE id = ?", (lexeme_id,)
        ).fetchone()
        if not lexeme:
            return None

        progress = get_or_create_progress(connection, user_id, lexeme_id)
        previous_review_level = int(progress["review_level"] or 0)
        previous_next_review_at = progress["next_review_at"]
        previous_status = progress["status"]
        next_level, next_review_at = compute_review_schedule(
            rating, previous_review_level, reviewed_at
        )
        if previous_status is None or previous_status == "unclassified":
            corrected_status = _RATING_TO_AUTO_STATUS.get(rating, previous_status)
        else:
            corrected_status = previous_status
        count_column = "wrong_count" if rating == "again" else "correct_count"
        connection.execute(
            f"""
            UPDATE user_word_progress
            SET {count_column} = {count_column} + 1,
                review_level = ?,
                next_review_at = ?,
                last_reviewed_at = ?,
                status = ?,
                updated_at = ?
            WHERE user_id = ? AND lexeme_id = ?
            """,
            (
                next_level,
                next_review_at,
                timestamp,
                corrected_status,
                timestamp,
                user_id,
                lexeme_id,
            ),
        )
        row = _get_progress_row(connection, user_id, lexeme_id)
        new_status = row["status"]

        connection.execute(
            """
            INSERT INTO lexeme_review_logs (
                user_id, lexeme_id, shared_deck_id, rating,
                previous_review_level, new_review_level,
                previous_next_review_at, new_next_review_at,
                previous_status, new_status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                lexeme_id,
                shared_deck_id,
                rating,
                previous_review_level,
                next_level,
                previous_next_review_at,
                next_review_at,
                previous_status,
                new_status,
                timestamp,
            ),
        )
    return row_to_dict(row)


def list_subscribed_lexeme_study_items(
    user_id: int,
    shared_deck_id: int | None = None,
    due_only: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Study-queue view over every shared deck the user actively subscribes
    to (Phase 3, see docs/architecture/shared-lexeme-progress-storage.md --
    "SRS card integration"). Read-only: never creates a
    user_deck_subscriptions or user_word_progress row -- lazy progress
    creation only happens in update_word_status()/record_lexeme_review()
    above, when the user actually submits a status change or rating.

    Reuses list_shared_deck_words_with_progress() per subscribed deck
    (already regression-tested for the deck-detail view) instead of a new
    SQL join, so this is additive glue code, not a new query surface:
    fetch each subscribed deck's word+progress overlay, then de-duplicate
    by lexeme_id (the same lexeme can be linked into more than one
    subscribed deck, but a user has at most one user_word_progress row per
    lexeme) -- keeps the first deck it's seen in as that word's
    source_label so it doesn't show up as a duplicate study card.

    If shared_deck_id is given, only that one deck's words are returned --
    but only if the user is actually subscribed to it (never leaks a
    non-subscribed deck's words through this study-queue path).

    limit (Phase 20 Round 2, pushed to SQL for the single-deck case in Phase
    21 Round 1): caps the number of items returned.

    - When shared_deck_id is given (one deck only, so the loop below runs
      exactly once), limit is passed straight through to
      list_shared_deck_words_with_progress() as a real SQL LIMIT --
      shared_deck_words' UNIQUE(shared_deck_id, lexeme_id) constraint means
      a single deck can never contribute a duplicate lexeme_id, so pushing
      the limit into the query for this path is exact, not an
      approximation: the database now reads/returns at most `limit` rows
      instead of the full deck (e.g. all 3,475 N1 words) before Python ever
      sees them.
    - When shared_deck_id is None (the "all subscribed decks" merge), each
      deck is still fetched in full and limit is only applied as a final
      Python slice over the deck-ordered/sort_order-ordered merged+deduped
      list, exactly as before this round. This is deliberate, not an
      oversight: the same lexeme_id can be linked into more than one
      subscribed deck, so pushing a per-deck SQL LIMIT into this branch
      could under-fill the final result after cross-deck dedup (see the
      Phase 21 Round 0 writeup in
      docs/architecture/shared-lexeme-progress-storage.md) -- out of scope
      for this round.

    Either way, omitting limit (None) keeps returning everything, unchanged
    from before this parameter existed. This does not change what counts as
    due/new -- it only trims how many of them come back in one response, so
    it must never be used to make /stats-reported counts (due_count,
    new_count) look smaller than they are; those still read the full
    underlying data untouched.

    known words (Phase 22 Round 1): this study-queue view never wants
    'known' words back, in either the single-deck or the "all decks" path --
    GET /study-items/lexemes (main.py) has always filtered them out of the
    final response regardless of due_only/limit. Previously that filtering
    happened only in main.py, *after* limit had already picked a fixed-size
    slice, so a deck with 'known' words sorted early could return fewer than
    `limit` items even though enough non-known words existed further down.
    Every call to list_shared_deck_words_with_progress() below now passes
    exclude_known=True, so known words are dropped in SQL before ORDER
    BY/LIMIT -- both the single-deck SQL LIMIT path and the all-mode
    Python-slice path now fill up to `limit` from non-known words only. This
    does not change get_shared_deck_data() (deck detail), which never calls
    this function and keeps showing known words unchanged.
    """
    subscribed_ids_set = list_subscribed_shared_deck_ids(user_id)
    if shared_deck_id is not None:
        if shared_deck_id not in subscribed_ids_set:
            return []
        subscribed_ids = [shared_deck_id]
        sql_limit = limit
    else:
        subscribed_ids = sorted(subscribed_ids_set)
        sql_limit = None
    if not subscribed_ids:
        return []

    with get_connection() as connection:
        placeholders = ", ".join("?" for _ in subscribed_ids)
        title_rows = connection.execute(
            f"SELECT id, title FROM shared_decks WHERE id IN ({placeholders})",
            tuple(subscribed_ids),
        ).fetchall()
    titles = {int(row["id"]): row["title"] for row in title_rows}

    seen_lexeme_ids: set[int] = set()
    items: list[dict[str, Any]] = []
    for deck_id in subscribed_ids:
        words = list_shared_deck_words_with_progress(
            deck_id, user_id, due_only=due_only, limit=sql_limit, exclude_known=True
        )
        for word in words:
            lexeme_id = word["lexeme_id"]
            if lexeme_id in seen_lexeme_ids:
                continue
            seen_lexeme_ids.add(lexeme_id)
            items.append(
                {
                    **word,
                    "shared_deck_id": deck_id,
                    "source_label": titles.get(deck_id) or "가져온 덱",
                }
            )
    if limit is not None:
        items = items[:limit]
    return items


def get_subscribed_lexeme_stats_summary(user_id: int) -> dict[str, int]:
    """Phase 5 stats aggregation (see
    docs/architecture/shared-lexeme-progress-storage.md -- "Phase 5:
    stats/dashboard integration"). One row per lexeme reachable through an
    active shared-deck subscription -- the inner `SELECT DISTINCT` is what
    keeps a lexeme linked into more than one subscribed deck from being
    double-counted, same dedup rule the Phase 3 study queue already uses.
    Read-only: never creates a user_word_progress row, just like listing
    the study queue.

    - `new_count`: no progress row yet, or review_level still 0 (mirrors
      vocab_items' "last_reviewed_at IS NULL" -- never actually reviewed).
      A lexeme with no progress row is deliberately excluded from
      `due_count` (see below) and only shows up here.
    - `due_count`: has a progress row with status unknown/uncertain and
      next_review_at null-or-past. Matches vocab_items' own due-today
      condition; progress-less lexemes are excluded automatically since
      SQL `NULL IN (...)` is never true.
    - `hard_count`: status = 'uncertain' only -- mirrors vocab_items'
      hard_count, which reuses only the "uncertain" classification (not
      "unknown" too), per its own comment in stats_repository.py.
    """
    now = now_iso()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_count,
                COALESCE(SUM(
                    CASE WHEN progress_status IS NULL OR progress_review_level = 0
                    THEN 1 ELSE 0 END
                ), 0) AS new_count,
                COALESCE(SUM(
                    CASE
                        WHEN progress_status IN ('unknown', 'uncertain')
                         AND (progress_next_review_at IS NULL OR progress_next_review_at <= ?)
                        THEN 1 ELSE 0
                    END
                ), 0) AS due_count,
                COALESCE(SUM(
                    CASE WHEN progress_status = 'uncertain' THEN 1 ELSE 0 END
                ), 0) AS hard_count
            FROM (
                SELECT
                    subscribed_lexemes.lexeme_id AS lexeme_id,
                    user_word_progress.status AS progress_status,
                    user_word_progress.review_level AS progress_review_level,
                    user_word_progress.next_review_at AS progress_next_review_at
                FROM (
                    SELECT DISTINCT shared_deck_words.lexeme_id AS lexeme_id
                    FROM shared_deck_words
                    JOIN user_deck_subscriptions
                        ON user_deck_subscriptions.shared_deck_id = shared_deck_words.shared_deck_id
                       AND user_deck_subscriptions.user_id = ?
                       AND user_deck_subscriptions.is_active = TRUE
                ) AS subscribed_lexemes
                LEFT JOIN user_word_progress
                    ON user_word_progress.lexeme_id = subscribed_lexemes.lexeme_id
                   AND user_word_progress.user_id = ?
            ) AS overlay
            """,
            (now, user_id, user_id),
        ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0),
        "new_count": int(row["new_count"] or 0),
        "due_count": int(row["due_count"] or 0),
        "hard_count": int(row["hard_count"] or 0),
    }


def get_lexeme_review_rating_counts_since(
    user_id: int, since_iso: str
) -> dict[str, int]:
    """Count of lexeme_review_logs rows (review *events*, not distinct
    words -- same "count log rows" semantics vocab_items' review_logs
    already uses for reviewed_today_count/today_*_count), grouped by
    rating, for this user at/after since_iso. Only ever incremented by an
    actual rating submission (record_lexeme_review()) -- never by import
    or listing the study queue, so this can never show an "completed
    today" count for a word the user only imported or looked at.
    """
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT rating, COUNT(*) AS count
            FROM lexeme_review_logs
            WHERE user_id = ?
              AND created_at >= ?
            GROUP BY rating
            """,
            (user_id, since_iso),
        ).fetchall()
    return {row["rating"]: int(row["count"] or 0) for row in rows}
