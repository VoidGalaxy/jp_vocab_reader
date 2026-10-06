"""Read-only first-review progress for one deck (학습 계획 탭).

Contract: references/plans/learning-plan-tab/gate-c0/CONTRACT_REVIEW.md, as
approved for Gate C-1a.

- metric_version "first-review-v1": a word counts as seen once its card has a
  `last_reviewed_at`. Every successful rating (again/hard/good/easy) sets it in
  the same transaction as its review log; status-only changes never do. So
  repeated ratings and a first "again" still count the word exactly once, and
  a failed rating request counts nothing.
- personal deck: the deck's current `vocab_items` rows. Copied/imported decks
  start without history (both import paths insert `last_reviewed_at = NULL`),
  so their progress is this deck's own cards only -> progress_scope
  "deck_cards".
- subscribed deck: the deck's current distinct lexemes, overlaid with the
  account-wide `user_word_progress` row (one per user+lexeme, shared by every
  deck containing that lexeme). A lexeme first studied through another deck
  is already seen here -> progress_scope "account_shared".
- Only the current deck contents count: deleted words leave both numbers,
  moved personal cards keep their history.

Nothing here writes. No schema or SRS change.
"""

from __future__ import annotations

from datetime import timedelta, timezone
from typing import Any, Literal

from app.database import get_connection, now_utc

METRIC_VERSION = "first-review-v1"
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")

DeckKind = Literal["personal", "subscribed"]


def get_plan_progress(user_id: int, deck_kind: DeckKind, deck_id: int) -> dict[str, Any] | None:
    """Returns None when the deck is not the user's (personal) or not an
    active subscription (subscribed). Callers answer 404 for both, so a
    foreign deck is indistinguishable from a missing one."""
    as_of = now_utc()
    with get_connection() as connection:
        if deck_kind == "personal":
            owned = connection.execute(
                "SELECT 1 FROM decks WHERE id = ? AND user_id = ?",
                (deck_id, user_id),
            ).fetchone()
            if not owned:
                return None
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN last_reviewed_at IS NOT NULL THEN 1 ELSE 0 END), 0) AS seen
                FROM vocab_items
                WHERE user_id = ?
                  AND deck_id = ?
                """,
                (user_id, deck_id),
            ).fetchone()
            scope = "deck_cards"
        else:
            subscribed = connection.execute(
                """
                SELECT 1
                FROM user_deck_subscriptions
                WHERE user_id = ?
                  AND shared_deck_id = ?
                  AND is_active = TRUE
                """,
                (user_id, deck_id),
            ).fetchone()
            if not subscribed:
                return None
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(
                        CASE WHEN user_word_progress.last_reviewed_at IS NOT NULL THEN 1 ELSE 0 END
                    ), 0) AS seen
                FROM (
                    SELECT DISTINCT lexeme_id
                    FROM shared_deck_words
                    WHERE shared_deck_id = ?
                ) AS deck_lexemes
                LEFT JOIN user_word_progress
                  ON user_word_progress.lexeme_id = deck_lexemes.lexeme_id
                 AND user_word_progress.user_id = ?
                """,
                (deck_id, user_id),
            ).fetchone()
            scope = "account_shared"

    total = int(row["total"] or 0)
    seen = int(row["seen"] or 0)
    return {
        "deck_kind": deck_kind,
        "deck_id": deck_id,
        "total": total,
        "seen": seen,
        "progress_scope": scope,
        "metric_version": METRIC_VERSION,
        "today": as_of.astimezone(SEOUL).date().isoformat(),
        "as_of": as_of.isoformat(),
    }
