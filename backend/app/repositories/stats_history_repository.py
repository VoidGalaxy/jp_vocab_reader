"""Read-only, date-by-date study history for the Stats tab (학습 기록).

Approved contract (references/mockups/stats-two-view-three/handoff/
DATA_CONTRACT.md, Gate C):

- Dates are Asia/Seoul calendar days. Seoul has had no DST since 1988, so a
  fixed +09:00 offset is exact and avoids a tzdata dependency.
- A review is one row in either log: personal `review_logs` or subscribed
  `lexeme_review_logs`. Rows are never joined to the current vocab/lexeme
  tables, so reviews of words deleted since still count.
- "Saved words" are the user's *current* personal vocab_items by
  created_at. Deleted words and subscribed decks are not included; the
  response says so in `saved_words_scope`.
- The streak counts consecutive Seoul days with at least one review,
  starting today if there is a review today, otherwise yesterday.

Nothing here writes, and no schema or SRS logic changes. Stored timestamps
are ISO strings (UTC today). Queries use a padded string range on the
indexed column and then parse each value with the standard ISO parser, so a
row is never assigned to a day by slicing its text.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from app.database import get_connection, now_utc

TIMEZONE_NAME = "Asia/Seoul"
SEOUL = timezone(timedelta(hours=9), TIMEZONE_NAME)
RATINGS = ("again", "hard", "good", "easy")
REVIEW_SOURCES = ["personal", "subscribed"]
SAVED_WORDS_SCOPE = "current_personal_words"
STREAK_DEFINITION = (
    "Consecutive Asia/Seoul days with at least one personal or subscribed "
    "review, counted from today if reviewed today, otherwise from yesterday."
)
# Guard band around each UTC range for rows stored with a different offset
# or without one; every row is still filtered exactly after parsing.
QUERY_PADDING = timedelta(days=1)
STREAK_WINDOW_DAYS = 35
STREAK_MAX_DAYS = 400
EARLIEST_MONTH = date(2000, 1, 1)
MAX_DAY_WORD_LIMIT = 20


class HistoryRangeError(ValueError):
    """The requested month/date is malformed, too early, or in the future."""


def seoul_today(now: datetime | None = None) -> date:
    return (now or now_utc()).astimezone(SEOUL).date()


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        # Everything this app writes is UTC (database.now_iso()).
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def local_date(value: Any) -> date | None:
    parsed = parse_timestamp(value)
    return parsed.astimezone(SEOUL).date() if parsed else None


def _utc_bounds(start: date, end: date) -> tuple[str, str]:
    """Padded ISO bounds for local days [start, end)."""
    start_utc = datetime.combine(start, time(), SEOUL).astimezone(timezone.utc)
    end_utc = datetime.combine(end, time(), SEOUL).astimezone(timezone.utc)
    return (
        (start_utc - QUERY_PADDING).isoformat(),
        (end_utc + QUERY_PADDING).isoformat(),
    )


def _review_rows(connection, user_id: int, start: date, end: date) -> list[tuple[date, str]]:
    """(local date, rating) for every review event on local days [start, end)."""
    lower, upper = _utc_bounds(start, end)
    personal = connection.execute(
        """
        SELECT rating, reviewed_at AS at
        FROM review_logs
        WHERE user_id = ?
          AND reviewed_at >= ?
          AND reviewed_at < ?
        """,
        (user_id, lower, upper),
    ).fetchall()
    subscribed = connection.execute(
        """
        SELECT rating, created_at AS at
        FROM lexeme_review_logs
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at < ?
        """,
        (user_id, lower, upper),
    ).fetchall()
    events: list[tuple[date, str]] = []
    for row in [*personal, *subscribed]:
        day = local_date(row["at"])
        if day is not None and start <= day < end:
            events.append((day, row["rating"]))
    return events


def _saved_word_rows(connection, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
    lower, upper = _utc_bounds(start, end)
    rows = connection.execute(
        """
        SELECT id, surface, reading, meaning_ko, created_at
        FROM vocab_items
        WHERE user_id = ?
          AND created_at >= ?
          AND created_at < ?
        """,
        (user_id, lower, upper),
    ).fetchall()
    words = []
    for row in rows:
        created = parse_timestamp(row["created_at"])
        if created is None:
            continue
        day = created.astimezone(SEOUL).date()
        if start <= day < end:
            words.append(
                {
                    "id": int(row["id"]),
                    "surface": row["surface"] or "",
                    "reading": row["reading"] or "",
                    "meaning_ko": row["meaning_ko"] or "",
                    "created": created,
                    "date": day,
                }
            )
    return words


def _empty_ratings() -> dict[str, int]:
    return {rating: 0 for rating in RATINGS}


def _compute_streak(connection, user_id: int, today: date) -> dict[str, Any]:
    """At most STREAK_MAX_DAYS days, counted back from the anchor (inclusive).

    `capped` is true only when the day before the oldest counted day was also
    a review day, i.e. the real streak is longer than what is returned.
    """
    reviewed: set[date] = set()
    window_start = today + timedelta(days=1)
    # The anchor may be yesterday, so the oldest day ever needed is the day
    # just before a full-length streak ending yesterday.
    oldest_needed = today - timedelta(days=STREAK_MAX_DAYS + 1)

    def load_until(day: date) -> None:
        nonlocal window_start
        while day < window_start and window_start > oldest_needed:
            new_start = max(window_start - timedelta(days=STREAK_WINDOW_DAYS), oldest_needed)
            reviewed.update(d for d, _ in _review_rows(connection, user_id, new_start, window_start))
            window_start = new_start

    load_until(today - timedelta(days=1))
    anchor = today if today in reviewed else today - timedelta(days=1)
    cursor = anchor
    days = 0
    while days < STREAK_MAX_DAYS:
        load_until(cursor)
        if cursor not in reviewed:
            break
        days += 1
        cursor -= timedelta(days=1)
    capped = False
    if days == STREAK_MAX_DAYS:
        load_until(cursor)
        capped = cursor in reviewed
    return {
        "days": days,
        "starts_on": (cursor + timedelta(days=1)).isoformat() if days else None,
        "ends_on": anchor.isoformat() if days else None,
        "capped": capped,
        "definition": STREAK_DEFINITION,
    }


def parse_month(month: str, today: date) -> date:
    try:
        first = datetime.strptime(month, "%Y-%m").date()
    except ValueError as error:
        raise HistoryRangeError("month must be YYYY-MM") from error
    if first < EARLIEST_MONTH:
        raise HistoryRangeError("month is too early")
    if first > today.replace(day=1):
        raise HistoryRangeError("month is in the future")
    return first


def parse_day(value: str, today: date) -> date:
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise HistoryRangeError("date must be YYYY-MM-DD") from error
    if day < EARLIEST_MONTH:
        raise HistoryRangeError("date is too early")
    if day > today:
        raise HistoryRangeError("date is in the future")
    return day


def build_history_month(user_id: int, month: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or now_utc()
    today = seoul_today(now)
    first = parse_month(month, today)
    next_first = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    # Days after today are not reported at all (not as zeros).
    last_reported = min(next_first - timedelta(days=1), today)

    with get_connection() as connection:
        events = _review_rows(connection, user_id, first, next_first)
        words = _saved_word_rows(connection, user_id, first, next_first)
        streak = _compute_streak(connection, user_id, today)

    by_day: dict[date, dict[str, Any]] = {}
    cursor = first
    while cursor <= last_reported:
        by_day[cursor] = {"review_count": 0, "ratings": _empty_ratings(), "saved_word_count": 0}
        cursor += timedelta(days=1)
    for day, rating in events:
        entry = by_day.get(day)
        if entry is None:
            continue
        entry["review_count"] += 1
        if rating in entry["ratings"]:
            entry["ratings"][rating] += 1
    for word in words:
        entry = by_day.get(word["date"])
        if entry is not None:
            entry["saved_word_count"] += 1

    days = [{"date": day.isoformat(), **entry} for day, entry in sorted(by_day.items())]
    return {
        "month": first.strftime("%Y-%m"),
        "timezone": TIMEZONE_NAME,
        "today": today.isoformat(),
        "as_of": now.isoformat(),
        "review_sources": REVIEW_SOURCES,
        "saved_words_scope": SAVED_WORDS_SCOPE,
        "days": days,
        "summary": {
            "review_count": sum(d["review_count"] for d in days),
            "saved_word_count": sum(d["saved_word_count"] for d in days),
            "active_days": sum(1 for d in days if d["review_count"] > 0),
        },
        "current_streak": streak,
    }


def build_history_day(
    user_id: int, value: str, limit: int = 5, now: datetime | None = None
) -> dict[str, Any]:
    now = now or now_utc()
    today = seoul_today(now)
    day = parse_day(value, today)
    limit = max(1, min(int(limit), MAX_DAY_WORD_LIMIT))
    next_day = day + timedelta(days=1)

    with get_connection() as connection:
        events = _review_rows(connection, user_id, day, next_day)
        words = _saved_word_rows(connection, user_id, day, next_day)

    ratings = _empty_ratings()
    for _, rating in events:
        if rating in ratings:
            ratings[rating] += 1
    words.sort(key=lambda word: (word["created"], word["id"]), reverse=True)
    return {
        "date": day.isoformat(),
        "timezone": TIMEZONE_NAME,
        "review_sources": REVIEW_SOURCES,
        "saved_words_scope": SAVED_WORDS_SCOPE,
        "review_count": len(events),
        "ratings": ratings,
        "saved_word_count": len(words),
        "saved_words": [
            {
                "id": word["id"],
                "surface": word["surface"],
                "reading": word["reading"],
                "meaning_ko": word["meaning_ko"],
            }
            for word in words[:limit]
        ],
        "has_more_saved_words": len(words) > limit,
    }
