"""Daily new-word goal: one definition shared by reviews and the study queue.

A card is "introduced" on the Asia/Seoul date of its first original review
log, whatever the rating (a first Again counts). Further ratings, retries
(which add no log) and migrations (which add no events) never count again.
Personal cards count per vocab_item, subscribed cards per account + lexeme.
Legacy logs are included; on SQLite the logs of deleted cards remain and
still count (PostgreSQL currently cascades them away -- unresolved, see
gate-b2/POSTGRES_HISTORY_PROPOSAL.md).

Unreadable review times (CORRUPT_REVIEW_TIME_PROPOSAL.md, approved
2026-10-09): every log time is parsed and compared as a real UTC instant --
never by string MIN. If any log time of a card cannot be read, that card's
first-review date is unknown: the unreadable log might be its real first
review, so no other log stands in for it and nothing is skipped or treated
as zero. Logs are only read, never changed. A count that depends on an
unknown card is reported as unknown with a verified lower bound.

Read-only. The goal is a target, not a strict limit (APPROVAL item 5).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from app.srs.completion import seoul_date

DEFAULT_DAILY_NEW_GOAL = 20
EXACT, UNKNOWN = "exact", "unknown"
MAX_TIME_TEXT = 64


def read_utc(value: Any) -> datetime | None:
    """A stored review time as a UTC instant, or None when it cannot be read.

    Accepted: ISO 8601 text with a time zone (`+00:00`, `Z`, any other offset),
    compared after conversion to UTC. Rejected: empty, no time zone, not text,
    unparsable, or not convertible to UTC. The stored text is never changed."""
    if not isinstance(value, str) or not value or len(value) > MAX_TIME_TEXT:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class IntroductionCount:
    status: str  # "exact" | "unknown"
    count: int | None  # exact count, None when unknown
    at_least: int  # cards verified as introduced on that date
    unreadable_cards: int  # cards in the counted set whose first-review date is unknown
    identity_unknown_cards: int = 0  # Gate D-2 U3: flagged ids with a log on that date
    history_unknown_cards: int = 0  # Gate D-2 U4: past-learning marks that leave that date open

    def as_dict(self, prefix: str = "introduced_today") -> dict[str, Any]:
        return {prefix: self.count, f"{prefix}_status": self.status, f"{prefix}_at_least": self.at_least}


_NO_LOG: Any = object()  # a key with a past-learning mark but no log


def first_review_dates(connection: Any, user_id: int) -> dict[tuple[str, int], datetime | None]:
    """(kind, ref_id) -> first review instant, or None when any of that card's
    log times is unreadable. Covers every card of the account with logs,
    including cards that were deleted (where the logs remain)."""
    rows = connection.execute(
        "SELECT 'personal' AS kind, vocab_item_id AS ref_id, reviewed_at AS event_at "
        "FROM review_logs WHERE user_id = ? "
        "UNION ALL SELECT 'lexeme' AS kind, lexeme_id AS ref_id, created_at AS event_at "
        "FROM lexeme_review_logs WHERE user_id = ?",
        (user_id, user_id),
    ).fetchall()
    first: dict[tuple[str, int], datetime | None] = {}
    for row in rows:
        key = (row["kind"], int(row["ref_id"]))
        at = read_utc(row["event_at"])
        if key in first and first[key] is None:
            continue
        if at is None:
            first[key] = None
        elif key not in first or at < first[key]:
            first[key] = at
    return first


def count_introduced(
    dates: dict[tuple[str, int], datetime | None],
    at: datetime,
    scope: Collection[tuple[str, int]] | None = None,
    identity_days: Mapping[tuple[str, int], Collection[date]] | None = None,
    intro_evidence: Mapping[tuple[str, int], tuple[str, date | None]] | None = None,
) -> IntroductionCount:
    """Cards first reviewed on the Seoul date of `at`, limited to `scope`
    (None = the whole account, deleted cards included).

    `identity_days` (Gate D-2 U3, D-P6c): ids flagged "identity unknown" whose
    log times are all readable, with the Seoul dates of their logs. More than one
    card may stand behind such an id, so its first-review date cannot be told:
    the count is unknown on those dates and the id adds nothing on other dates.
    An id with an unreadable time is not in `identity_days`; its None first date
    keeps the unknown-on-every-date rule above.

    `intro_evidence` (Gate D-2 U4, D-H7; app/srs/history_intro.py): past-learning
    marks. 'before_tracking' with bound K: not new on any day after K (also when a
    later log falls on that day); unknown on K and before. 'unknown': unknown on
    every day. Marks also cover cards with no log at all. Unreadable log times and
    identity-unknown ids are decided first and are never weakened by a mark."""
    day = seoul_date(at)
    verified = unreadable = identity = history = 0
    evidence = intro_evidence or {}
    for key in set(dates) | set(evidence):
        if scope is not None and key not in scope:
            continue
        first = dates.get(key, _NO_LOG)
        mark = evidence.get(key)
        if first is None:
            unreadable += 1
        elif identity_days is not None and key in identity_days:
            identity += day in identity_days[key]
        elif mark is not None and mark[0] == "before_tracking" and mark[1] is not None:
            history += day <= mark[1]
        elif mark is not None and mark[0] in ("before_tracking", "unknown"):
            history += 1
        elif first is not _NO_LOG and seoul_date(first) == day:
            verified += 1
    if unreadable or identity or history:
        return IntroductionCount(UNKNOWN, None, verified, unreadable, identity, history)
    return IntroductionCount(EXACT, verified, verified, 0)


def introduction_count(
    connection: Any,
    user_id: int,
    at: datetime,
    scope: Collection[tuple[str, int]] | None = None,
) -> IntroductionCount:
    from app.srs.history_intro import intro_evidence
    from app.srs.identity import identity_unknown_days

    return count_introduced(first_review_dates(connection, user_id), at, scope,
                            identity_unknown_days(connection, user_id), intro_evidence(connection, user_id))


def account_goal(connection: Any, user_id: int) -> dict[str, Any] | None:
    """The stored settings row, or None when the account has none (legacy)."""
    row = connection.execute(
        "SELECT srs_mode, daily_new_goal, settings_version FROM srs_user_settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row is not None else None
