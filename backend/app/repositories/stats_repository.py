from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.database import get_connection, now_iso, now_utc, row_to_dict

# How far back to look when computing a daily study streak. A user with an
# unbroken streak longer than this is undercounted, which is an acceptable
# trade-off for keeping the query a single bounded SELECT.
STREAK_LOOKBACK_DAYS = 400


def build_stats(user_id: int, deck_id: int | None = None) -> dict[str, Any]:
    timestamp = now_iso()
    now = now_utc()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    params: list[Any] = [timestamp, user_id]
    where_clause = "WHERE vocab_items.user_id = ?"
    if deck_id is not None:
        where_clause += " AND vocab_items.deck_id = ?"
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
                SUM(CASE WHEN last_reviewed_at IS NULL THEN 1 ELSE 0 END) AS new_count,
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
                """
                SELECT id, name
                FROM decks
                WHERE id = ?
                  AND user_id = ?
                """,
                (deck_id, user_id),
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
                LEFT JOIN vocab_items
                  ON vocab_items.deck_id = decks.id
                 AND vocab_items.user_id = decks.user_id
                WHERE decks.user_id = ?
                GROUP BY decks.id, decks.name
                ORDER BY decks.id ASC
                """,
                (timestamp, user_id),
            ).fetchall()
            deck_stats = [build_deck_stats(row_to_dict(row)) for row in deck_rows]

        review_log_params: list[Any] = [user_id, today_start]
        review_log_deck_clause = ""
        if deck_id is not None:
            review_log_deck_clause = "AND deck_id = ?"
            review_log_params.append(deck_id)
        rating_rows = connection.execute(
            f"""
            SELECT rating, COUNT(*) AS count
            FROM review_logs
            WHERE user_id = ?
              AND reviewed_at >= ?
              {review_log_deck_clause}
            GROUP BY rating
            """,
            tuple(review_log_params),
        ).fetchall()

        streak_rows = connection.execute(
            """
            SELECT reviewed_at
            FROM review_logs
            WHERE user_id = ?
            ORDER BY reviewed_at DESC
            LIMIT ?
            """,
            (user_id, STREAK_LOOKBACK_DAYS),
        ).fetchall()

    today_rating_counts = {
        row["rating"]: int(row["count"] or 0) for row in rating_rows
    }
    streak_days = compute_streak_days(
        [row["reviewed_at"] for row in streak_rows], now
    )

    stats = row_to_dict(summary)
    total_count = int(stats.get("total_count") or 0)
    known_count = int(stats.get("known_count") or 0)
    uncertain_count = int(stats.get("uncertain_count") or 0)
    scope = "deck" if deck_id is not None else "all"
    return {
        "scope": scope,
        "deck_id": deck_id,
        "deck_name": deck_row["name"] if deck_row else None,
        "total_count": total_count,
        "total_vocab_count": total_count,
        "known_count": known_count,
        "uncertain_count": uncertain_count,
        "unknown_count": int(stats.get("unknown_count") or 0),
        "unclassified_count": int(stats.get("unclassified_count") or 0),
        "due_today_count": int(stats.get("due_today_count") or 0),
        "total_correct_count": int(stats.get("total_correct_count") or 0),
        "total_wrong_count": int(stats.get("total_wrong_count") or 0),
        "average_review_level": round(float(stats.get("average_review_level") or 0), 2),
        "learned_rate": learned_rate(known_count, total_count),
        "deck_stats": deck_stats,
        "new_count": int(stats.get("new_count") or 0),
        # No standalone "difficulty" flag is persisted per vocab item yet, so
        # "어려운 단어" reuses the existing uncertain classification for now.
        "hard_count": uncertain_count,
        "reviewed_today_count": sum(today_rating_counts.values()),
        "today_again_count": today_rating_counts.get("again", 0),
        "today_hard_count": today_rating_counts.get("hard", 0),
        "today_good_count": today_rating_counts.get("good", 0),
        "today_easy_count": today_rating_counts.get("easy", 0),
        "streak_days": streak_days,
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


def compute_streak_days(reviewed_at_values: list[str], now) -> int:
    reviewed_dates = {value[:10] for value in reviewed_at_values if value}
    streak = 0
    cursor = now.date()
    while cursor.isoformat() in reviewed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
