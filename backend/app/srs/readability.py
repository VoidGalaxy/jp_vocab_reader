"""Whether a card's own review history can be read at all (U7 follow-up).

One definition for the review path (which refuses with 409
`review_history_unreadable`) and the study queue (which then does not serve the
card, classifying it `invalid_state`, so a refused card cannot sit at the head of a
session). Read-only; nothing is repaired, flagged or replayed.

A history is unreadable when any of these cannot be interpreted:
- the time of any of the card's own logs (goals.read_utc: any UTC offset is fine);
- the rating of any of the card's own logs (not one of again/hard/good/easy);
- the before/after engine snapshot of an FSRS log inside the card's completion
  evidence window (id >= the card's `evidence_from_log_id`). Snapshots of older
  logs, or of legacy logs (which have none), are not examined.

Readable records that disagree (wrong config, a transition the engine does not
explain, a time that is not the snapshot's) are NOT unreadable: they only make the
completion evidence incomplete, and the card keeps being served and rated. That
replay lives in the review path only (reviews._evidence_window_consistent).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.srs.engine import RATINGS, SrsEngineError, state_from_json
from app.srs.goals import read_utc


def snapshot_unreadable(log: dict[str, Any]) -> bool:
    """An evidence-window FSRS log whose engine snapshots cannot be parsed."""
    try:
        state_from_json(log["srs_before_json"])
        state_from_json(log["srs_after_json"])
    except SrsEngineError:
        return True
    return False


def history_unreadable(logs: Iterable[dict[str, Any]], boundary: int | None) -> bool:
    """One card: `logs` are its own logs (with `event_at`, `rating`, `id`,
    `srs_engine` and the two snapshot columns), `boundary` its evidence_from_log_id."""
    for log in logs:
        if read_utc(log["event_at"]) is None or log["rating"] not in RATINGS:
            return True
        if (boundary is not None and log["id"] >= boundary and log["srs_engine"] == "fsrs"
                and snapshot_unreadable(log)):
            return True
    return False


def unreadable_history_keys(connection: Any, user_id: int) -> set[tuple[str, int]]:
    """The same rule for every card of one account, in a few account-wide queries
    (no per-card query, no engine replay): (kind, ref_id) of cards with an unreadable
    log time, an unknown rating, or an unparseable evidence-window FSRS snapshot.
    Run it inside the caller's read transaction so it sees the same state."""
    keys: set[tuple[str, int]] = set()
    for kind, table, ref, time in (("personal", "review_logs", "vocab_item_id", "reviewed_at"),
                                   ("lexeme", "lexeme_review_logs", "lexeme_id", "created_at")):
        for row in connection.execute(
            f"SELECT {ref} AS ref, {time} AS event_at, rating FROM {table} WHERE user_id = ?", (user_id,)
        ).fetchall():
            if read_utc(row["event_at"]) is None or row["rating"] not in RATINGS:
                keys.add((kind, int(row["ref"])))
    for kind, sql in (
        ("personal", "SELECT l.vocab_item_id AS ref, l.srs_before_json, l.srs_after_json FROM review_logs l "
                     "JOIN vocab_items c ON c.user_id = l.user_id AND c.id = l.vocab_item_id "
                     "WHERE l.user_id = ? AND c.evidence_from_log_id IS NOT NULL AND l.id >= c.evidence_from_log_id "
                     "AND l.srs_engine = 'fsrs'"),
        ("lexeme", "SELECT l.lexeme_id AS ref, l.srs_before_json, l.srs_after_json FROM lexeme_review_logs l "
                   "JOIN user_word_progress c ON c.user_id = l.user_id AND c.lexeme_id = l.lexeme_id "
                   "WHERE l.user_id = ? AND c.evidence_from_log_id IS NOT NULL AND l.id >= c.evidence_from_log_id "
                   "AND l.srs_engine = 'fsrs'"),
    ):
        for row in connection.execute(sql, (user_id,)).fetchall():
            if snapshot_unreadable(row):
                keys.add((kind, int(row["ref"])))
    return keys
