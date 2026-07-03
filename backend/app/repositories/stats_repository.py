from __future__ import annotations

from typing import Any

from app.database import get_connection, now_iso, row_to_dict


def build_stats(user_id: int, deck_id: int | None = None) -> dict[str, Any]:
    timestamp = now_iso()
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
