"""Past-learning evidence for the daily new-word count (Gate D-2 U4, D-H7).

Contract: docs/plans/srs-improvement/gate-d0/CONTRACT.md 3-3 (cases C1~C7) and
gate-d2/APPROVAL_REQUEST.md D-H7.

A card with past study but no review log has no first-review date. Without a
mark, its first FSRS log would become its first review and use up that day's
new-word goal again (CONTRACT F16). Each card stores, once:

  history_intro_status    'logged' | 'before_tracking' | 'unknown' | NULL
  history_intro_known_by  Seoul date (YYYY-MM-DD) for 'before_tracking', else NULL

Decision (`classify_intro`, from the card row and its own logs only):

- 'logged': the card has at least one own review log. Its first-review date
  comes from the logs, exactly as before (goals.first_review_dates).
- 'before_tracking': no log, and `last_reviewed_at` is a readable instant (any
  UTC offset, converted to UTC). `last_reviewed_at` is an UPPER BOUND -- the
  card was studied on that Seoul date or earlier -- not the first study date.
  known_by = its Seoul date.
- 'unknown': no log, and either `last_reviewed_at` is present but unreadable
  (no time zone, not ISO, empty), or it is missing while the counters show
  ratings (correct_count + wrong_count > 0). Studied, with no usable bound.
- NULL (nothing recorded): no log, no `last_reviewed_at`, no ratings -- never
  studied, whatever its self-classification. A card marked `known` with no
  rating is NOT treated as reviewed.

Counting (goals.count_introduced): for a day D,
- before_tracking: D > known_by -> not new on D (exact, even when a later log
  falls on D); D <= known_by -> unknown, verified lower bound kept;
- unknown: unknown on every date (no narrowing);
- logged / NULL: unchanged rule (first own log's Seoul date).
Unreadable own log times and identity-unknown ids keep their own rules first.

Writes: only `record_intro`, called from the explicit migration apply path.
It fills NULL only; an existing mark is never overwritten, narrowed or cleared
(reruns, rollback and re-conversion keep it). Reads, app start and dry-run never
write. No date is estimated and no log is created.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.srs.completion import seoul_date
from app.srs.goals import read_utc

LOGGED, BEFORE_TRACKING, UNKNOWN = "logged", "before_tracking", "unknown"
STATUSES = (LOGGED, BEFORE_TRACKING, UNKNOWN)
INTRO_COLUMNS = ("history_intro_status", "history_intro_known_by")


def classify_intro(card: dict[str, Any], logs: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """(status, known_by) from the card row and its own logs; see module doc."""
    if logs:
        return LOGGED, None
    raw = card.get("last_reviewed_at")
    if raw is not None:
        at = read_utc(raw)
        if at is None:
            return UNKNOWN, None
        return BEFORE_TRACKING, seoul_date(at).isoformat()
    if (card.get("correct_count") or 0) + (card.get("wrong_count") or 0) > 0:
        return UNKNOWN, None
    return None, None


def record_intro(connection: Any, kind: str, user_id: int, ref_id: int,
                 card: dict[str, Any], logs: list[dict[str, Any]]) -> str:
    """Fills the mark when it is still NULL. Returns 'recorded', 'kept_existing' or
    'no_history'. Never changes an existing mark and never touches card versions,
    engine state, schedule, counters, classification or logs."""
    if card.get("history_intro_status") is not None:
        return "kept_existing"
    status, known_by = classify_intro(card, logs)
    if status is None:
        return "no_history"
    table, where, params = (("vocab_items", "user_id = ? AND id = ?", (user_id, ref_id)) if kind == "personal"
                            else ("user_word_progress", "user_id = ? AND lexeme_id = ?", (user_id, ref_id)))
    cursor = connection.execute(
        f"UPDATE {table} SET history_intro_status = ?, history_intro_known_by = ? "
        f"WHERE {where} AND history_intro_status IS NULL",
        (status, known_by, *params),
    )
    return "recorded" if cursor.rowcount else "kept_existing"


def _rank(status: str, known_by: date | None) -> tuple[int, date]:
    """Higher = more uncertain. unknown > before_tracking (later bound wider) > logged."""
    order = {LOGGED: 0, BEFORE_TRACKING: 1, UNKNOWN: 2}[status]
    return order, known_by or date.min


def _parse(status: str, raw: Any) -> tuple[str, date | None]:
    if status == BEFORE_TRACKING:
        try:
            return status, date.fromisoformat(raw)
        except (TypeError, ValueError):
            return UNKNOWN, None  # a damaged bound never narrows the range
    return status, None


def intro_evidence(connection: Any, user_id: int) -> dict[tuple[str, int], tuple[str, date | None]]:
    """(kind, ref_id) -> (status, known_by date) for this account, read once per
    account (no per-card query):

    - marks on the account's existing cards, and
    - Gate D-2 U4 follow-up (E1~E3): marks copied into the deletion ledger when a
      card was deleted, so deleting a card neither re-consumes a day's goal nor
      turns an unknown count exact.

    Several sources for one (kind, id) -- several ledger rows, or a ledger row and
    a live card (only possible for an id reused before the U2 rebuild) -- become
    ONE card with the most uncertain value (unknown > before_tracking with the
    later bound > logged); nothing is merged into a narrower range. A ledger row
    with NULL mark (deleted before this rule, or no mark at deletion) contributes
    nothing and is never read as "never studied": that id follows its log rule."""
    evidence: dict[tuple[str, int], tuple[str, date | None]] = {}
    rows = connection.execute(
        "SELECT 'personal' AS kind, id AS ref_id, history_intro_status, history_intro_known_by FROM vocab_items "
        "WHERE user_id = ? AND history_intro_status IS NOT NULL "
        "UNION ALL SELECT 'lexeme' AS kind, lexeme_id AS ref_id, history_intro_status, history_intro_known_by "
        "FROM user_word_progress WHERE user_id = ? AND history_intro_status IS NOT NULL "
        "UNION ALL SELECT card_kind AS kind, card_ref AS ref_id, history_intro_status, history_intro_known_by "
        "FROM srs_card_deletions WHERE user_id = ? AND history_intro_status IS NOT NULL",
        (user_id, user_id, user_id),
    ).fetchall()
    for row in rows:
        key = (row["kind"], int(row["ref_id"]))
        value = _parse(row["history_intro_status"], row["history_intro_known_by"])
        current = evidence.get(key)
        if current is None or _rank(*value) > _rank(*current):
            evidence[key] = value
    return evidence
