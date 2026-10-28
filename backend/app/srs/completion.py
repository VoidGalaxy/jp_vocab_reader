"""'학습 완료' (meaning-completion) evaluation, V3 `meaning-completion-v1`.

Approved 2026-10-17 (Gate D-2 U11, D-C1/D-C3): judged by the server on a new real
FSRS review only, never shown on screen. Product policy, not part of FSRS; FSRS has
no "completed" state and completion never ends maintenance review. The earlier
simulation draft `meaning-completion-v1-draft` (2 dates, 1 spaced success) is no
longer evaluated; its stored first completions are kept with their source
(U11_DESIGN_B section 8).

A card counts as completed when all of these hold:
  C1 current FSRS phase is Review
  C2 model stability S >= 30 days
  C3 after the last Again, successful ratings (hard/good/easy) on >= 3
     distinct Asia/Seoul calendar dates (same-day repeats count once)
  C4 at least 2 of those successes came >= 7*24h (UTC elapsed) after the
     immediately preceding review of the card (any rating), not after the
     previous success and not by calendar days

Evidence handling:
- complete evidence: the result is COMPLETED or NOT_COMPLETED.
- incomplete evidence (history we could not fully trust): C3/C4 are never
  treated as proven, because a missing review could hide an Again, a success
  date or a shorter gap. NOT_COMPLETED only when the trusted current state
  already fails C1/C2; otherwise UNKNOWN, never COMPLETED and never a silent 0.
- a history whose last review is not the state's last review: UNKNOWN.
- first_completed_at is history and is never cleared by a later failure,
  pause or resume. Paused cards keep it but do not count toward progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Sequence

from app.srs.engine import (
    DEFAULT_CONFIG,
    RATINGS,
    SUCCESS_RATINGS,
    CardKey,
    ReviewOutcome,
    SrsCardState,
    SrsConfig,
    SrsEngineError,
    SrsPhase,
    review,
    to_utc,
)

METRIC_VERSION = "meaning-completion-v1"
DRAFT_METRIC_VERSION = "meaning-completion-v1-draft"  # earlier draft: stored history only
MIN_STABILITY_DAYS = 30.0
MIN_SUCCESS_DATES = 3
MIN_SPACED_SUCCESS = timedelta(days=7)
MIN_SPACED_SUCCESSES = 2
# U11 B: where a card's completion history lives besides completion_metric_version
# (the current judgement's version) and first_completed_at (the first completion of
# any version). Excluded from the migration card fingerprint and never restored by a
# rollback (U11_DESIGN_B 8-2).
FIRST_SOURCE_MISSING = "source_missing"
FIRST_SOURCE_UNKNOWN = "source_unknown"
COMPLETION_HISTORY_COLUMNS = ("first_completed_source", "version_first_completed_at", "version_first_completed_version")
# Same fixed offset the stats/learning-plan code uses (no DST since 1988).
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")


class CompletionStatus(str, Enum):
    COMPLETED = "completed"
    NOT_COMPLETED = "not_completed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReviewEvent:
    reviewed_at: datetime
    rating: str


@dataclass(frozen=True)
class CompletionCheck:
    status: CompletionStatus
    metric_version: str
    # True / False, or None when it could not be decided from the evidence.
    review_phase: bool | None
    stability_ok: bool | None
    success_dates_ok: bool | None
    spaced_success_ok: bool | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CompletionRecord:
    current: CompletionCheck
    first_completed_at: datetime | None
    needs_relearning: bool
    counts_toward_progress: bool


def seoul_date(value: datetime) -> date:
    return to_utc(value).astimezone(SEOUL).date()


def _validate_events(events: Sequence[ReviewEvent]) -> list[ReviewEvent]:
    checked: list[ReviewEvent] = []
    previous: datetime | None = None
    for event in events:
        if event.rating not in RATINGS:
            raise SrsEngineError(f"unknown rating: {event.rating!r}")
        at = to_utc(event.reviewed_at, "reviewed_at")
        if previous is not None and at < previous:
            raise SrsEngineError("events must be in chronological order")
        checked.append(ReviewEvent(reviewed_at=at, rating=event.rating))
        previous = at
    return checked


def evaluate_completion(
    state: SrsCardState | None,
    events: Sequence[ReviewEvent],
    *,
    evidence_complete: bool,
) -> CompletionCheck:
    """`events` are the card's reviews that produced `state`, oldest first.

    Only a complete history whose last review is the state's last review can
    prove C3/C4. With incomplete history a missing review could hide an Again,
    a success date or a shorter gap before a success, so C3/C4 are never
    taken as proven: the result is NOT_COMPLETED when the trusted current
    state already fails C1 or C2, otherwise UNKNOWN. A history whose last
    review does not match the state is treated the same way as UNKNOWN; it is
    never COMPLETED.
    """
    events = _validate_events(events)

    if state is None:
        if evidence_complete and not events:
            return CompletionCheck(
                CompletionStatus.NOT_COMPLETED, METRIC_VERSION, False, False, False, False, ("unreviewed",)
            )
        return CompletionCheck(
            CompletionStatus.UNKNOWN, METRIC_VERSION, None, None, None, None, ("no_engine_state",)
        )

    if evidence_complete and (not events or events[-1].reviewed_at != state.last_review_at):
        # The evidence does not describe this state; do not guess either way.
        return CompletionCheck(
            CompletionStatus.UNKNOWN, METRIC_VERSION, None, None, None, None, ("state_event_mismatch",)
        )

    reasons: list[str] = []
    review_phase = state.phase is SrsPhase.REVIEW
    stability_ok = state.stability >= MIN_STABILITY_DAYS
    if not review_phase:
        reasons.append("not_review_phase")
    if not stability_ok:
        reasons.append("stability_below_threshold")
    state_fails = not (review_phase and stability_ok)

    if not evidence_complete:
        # C3/C4 depend on every review since the last Again; unprovable here.
        reasons.append("incomplete_evidence")
        status = CompletionStatus.NOT_COMPLETED if state_fails else CompletionStatus.UNKNOWN
        return CompletionCheck(status, METRIC_VERSION, review_phase, stability_ok, None, None, tuple(reasons))

    last_again = max((i for i, e in enumerate(events) if e.rating == "again"), default=-1)
    success_indexes = [
        i for i in range(last_again + 1, len(events)) if events[i].rating in SUCCESS_RATINGS
    ]
    dates = {seoul_date(events[i].reviewed_at) for i in success_indexes}
    success_dates_ok = len(dates) >= MIN_SUCCESS_DATES
    spaced_success_ok = sum(
        1 for i in success_indexes
        if i > 0 and events[i].reviewed_at - events[i - 1].reviewed_at >= MIN_SPACED_SUCCESS
    ) >= MIN_SPACED_SUCCESSES
    if not success_dates_ok:
        reasons.append("fewer_success_dates")
    if not spaced_success_ok:
        reasons.append("no_spaced_success")

    completed = not state_fails and success_dates_ok and spaced_success_ok
    status = CompletionStatus.COMPLETED if completed else CompletionStatus.NOT_COMPLETED
    return CompletionCheck(
        status, METRIC_VERSION, review_phase, stability_ok, success_dates_ok, spaced_success_ok, tuple(reasons)
    )


def summarize_completion(
    current: CompletionCheck,
    *,
    participation: str,
    previous_first_completed_at: datetime | None,
    evaluated_at: datetime,
) -> CompletionRecord:
    """Combines the current check with stored history and participation.
    `evaluated_at` is the review time that produced the current check."""
    if participation not in ("active", "paused"):
        raise SrsEngineError(f"unknown participation: {participation!r}")
    first = previous_first_completed_at
    if first is None and current.status is CompletionStatus.COMPLETED:
        first = to_utc(evaluated_at, "evaluated_at")
    return CompletionRecord(
        current=current,
        first_completed_at=first,
        needs_relearning=first is not None and current.status is CompletionStatus.NOT_COMPLETED,
        counts_toward_progress=participation == "active" and current.status is CompletionStatus.COMPLETED,
    )


def _instant(value: object) -> bool:
    from app.srs.goals import read_utc  # goals imports this module

    return read_utc(value) is not None


def _first_source(card: dict) -> str:
    """U11_DESIGN_B 3-2: the source of a stored first completion, from the values
    as they were before this review (nothing is guessed or repaired)."""
    if not _instant(card.get("first_completed_at")):
        return FIRST_SOURCE_UNKNOWN
    version = card.get("completion_metric_version")
    if version == DRAFT_METRIC_VERSION:
        return DRAFT_METRIC_VERSION
    return FIRST_SOURCE_MISSING if version is None else FIRST_SOURCE_UNKNOWN


def version_first_state(card: dict) -> str:
    """'none' (both NULL), 'valid' (a readable time + this version) or 'kept' (one
    NULL, an unreadable time or another version: left as stored, never used)."""
    at, version = card.get("version_first_completed_at"), card.get("version_first_completed_version")
    if at is None and version is None:
        return "none"
    if version == METRIC_VERSION and isinstance(at, str) and _instant(at):
        return "valid"
    return "kept"


@dataclass(frozen=True)
class CompletionUpdate:
    values: dict  # card columns this review writes
    current_first_completed_at: str | None  # this version's first completion (response)
    needs_relearning: bool


def completion_update(card: dict, check: CompletionCheck, evaluated_at: datetime) -> CompletionUpdate:
    """Gate D-2 U11 B (U11_DESIGN_B 3-1, 8): the completion columns one real FSRS
    review writes, given the card row read under the account write lock."""
    values: dict = {"completion_metric_version": check.metric_version}
    first, source = card.get("first_completed_at"), card.get("first_completed_source")
    if first is not None and source is None:
        # Fixed once, before completion_metric_version is overwritten below.
        values["first_completed_source"] = _first_source(card)
    completed = check.status is CompletionStatus.COMPLETED
    at = to_utc(evaluated_at, "evaluated_at").isoformat()
    if completed and first is None and source is None:
        values.update(first_completed_at=at, first_completed_source=check.metric_version)
    state = version_first_state(card)
    current = card.get("version_first_completed_at") if state == "valid" else None
    if completed and state == "none":
        values.update(version_first_completed_at=at, version_first_completed_version=check.metric_version)
        current = at
    return CompletionUpdate(values, current,
                            current is not None and check.status is CompletionStatus.NOT_COMPLETED)


@dataclass(frozen=True)
class ReplayStep:
    outcome: ReviewOutcome
    check: CompletionCheck
    first_completed_at: datetime | None


def replay_with_completion(
    key: CardKey,
    events: Sequence[ReviewEvent],
    config: SrsConfig = DEFAULT_CONFIG,
) -> list[ReplayStep]:
    """Applies `events` from an unreviewed card through the engine and
    evaluates completion after every review. For tests and simulations only;
    it reads and writes nothing."""
    events = _validate_events(events)
    state: SrsCardState | None = None
    first: datetime | None = None
    steps: list[ReplayStep] = []
    for index, event in enumerate(events):
        outcome = review(key, state, event.rating, event.reviewed_at, config)
        state = outcome.after
        check = evaluate_completion(state, events[: index + 1], evidence_complete=True)
        if first is None and check.status is CompletionStatus.COMPLETED:
            first = outcome.reviewed_at
        steps.append(ReplayStep(outcome=outcome, check=check, first_completed_at=first))
    return steps
