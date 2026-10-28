"""Pure adapter around the pinned `fsrs` library (py-fsrs).

No database access, no clock reads, no randomness: every call receives the
UTC review time and the card's current state explicitly and returns new
values. The memory model (stability/difficulty/retrievability, learning
steps, intervals) is computed by the library only -- this module never
re-implements or adjusts its formulas.

Product rules that are *not* the engine's job live elsewhere:
- "unreviewed" (no valid first review yet) is represented as state=None here.
  The library has no New state; a fresh library Card is Learning/step 0 and
  due immediately, which the product must not count as a due review.
- completion ('학습 완료'), participation, daily new goals: see completion.py
  and later gates.

Card identity is (kind, user_id, ref_id). The library's integer card_id is
only a label on its ReviewLog; two cards that happen to share a numeric ref
(a personal vocab_item 5 and a lexeme 5) never share state through it.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.metadata
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping

from fsrs import Card, Rating, Scheduler, State
from fsrs.scheduler import DEFAULT_PARAMETERS

LIBRARY_NAME = "fsrs"
PINNED_LIBRARY_VERSION = "6.3.2"
ADAPTER_VERSION = "1"
ENGINE_NAME = "fsrs"

RATINGS: dict[str, Rating] = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}
SUCCESS_RATINGS = frozenset({"hard", "good", "easy"})

STABILITY_MIN = 0.001
DIFFICULTY_MIN = 1.0
DIFFICULTY_MAX = 10.0


class SrsEngineError(ValueError):
    """Invalid input/state for the engine adapter. Nothing was computed."""


class SrsPhase(str, Enum):
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


_PHASE_TO_STATE = {
    SrsPhase.LEARNING: State.Learning,
    SrsPhase.REVIEW: State.Review,
    SrsPhase.RELEARNING: State.Relearning,
}
_STATE_TO_PHASE = {value: key for key, value in _PHASE_TO_STATE.items()}
# Integer codes stored in the srs_state column -- the library's IntEnum values.
PHASE_CODES = {phase: int(state) for phase, state in _PHASE_TO_STATE.items()}
CODE_PHASES = {code: phase for phase, code in PHASE_CODES.items()}


@dataclass(frozen=True)
class SrsConfig:
    """Everything that changes scheduling. Stored by config_version so a
    card's state can be recomputed with exactly the settings it was made with."""

    parameters: tuple[float, ...]
    desired_retention: float
    learning_steps_seconds: tuple[int, ...]
    relearning_steps_seconds: tuple[int, ...]
    maximum_interval_days: int
    enable_fuzzing: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "library": LIBRARY_NAME,
            "library_version": PINNED_LIBRARY_VERSION,
            "adapter_version": ADAPTER_VERSION,
            "parameters": list(self.parameters),
            "desired_retention": self.desired_retention,
            "learning_steps_seconds": list(self.learning_steps_seconds),
            "relearning_steps_seconds": list(self.relearning_steps_seconds),
            "maximum_interval_days": self.maximum_interval_days,
            "enable_fuzzing": self.enable_fuzzing,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @property
    def config_version(self) -> str:
        digest = hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:12]
        return f"fsrs-{PINNED_LIBRARY_VERSION}-a{ADAPTER_VERSION}-{digest}"


# Approved 2026-10-09 (docs/plans/srs-improvement/APPROVAL_2026-10-09.md):
# library default parameters, retention 0.90, learning (1m, 10m),
# relearning (10m,), maximum interval 365 days, no fuzz.
DEFAULT_CONFIG = SrsConfig(
    parameters=tuple(float(value) for value in DEFAULT_PARAMETERS),
    desired_retention=0.90,
    learning_steps_seconds=(60, 600),
    relearning_steps_seconds=(600,),
    maximum_interval_days=365,
    enable_fuzzing=False,
)


@dataclass(frozen=True)
class CardKey:
    kind: str  # "personal" (vocab_items.id) or "lexeme" (user_word_progress by lexeme_id)
    user_id: int
    ref_id: int

    def __post_init__(self) -> None:
        if self.kind not in ("personal", "lexeme"):
            raise SrsEngineError(f"unknown card kind: {self.kind!r}")
        for name in ("user_id", "ref_id"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SrsEngineError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class SrsCardState:
    """Engine state of a reviewed card. Unreviewed cards are `None`."""

    phase: SrsPhase
    step: int | None
    stability: float
    difficulty: float
    due_at: datetime
    last_review_at: datetime

    def __post_init__(self) -> None:
        validate_state(self)


@dataclass(frozen=True)
class ReviewOutcome:
    key: CardKey
    rating: str
    reviewed_at: datetime
    before: SrsCardState | None
    after: SrsCardState
    elapsed_seconds: float | None
    config_version: str
    is_first_review: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_first_review", self.before is None)


def installed_library_version() -> str:
    return importlib.metadata.version(LIBRARY_NAME)


def assert_pinned_library() -> None:
    installed = installed_library_version()
    if installed != PINNED_LIBRARY_VERSION:
        raise SrsEngineError(
            f"fsrs {PINNED_LIBRARY_VERSION} is required, found {installed}"
        )


def build_scheduler(config: SrsConfig = DEFAULT_CONFIG) -> Scheduler:
    """A new library Scheduler for `config`, after the version and policy
    checks. Callers outside this module only inspect it; reviews always go
    through review(), which builds its own scheduler from the same config it
    records, so a scheduler can never be paired with another config."""
    if not isinstance(config, SrsConfig):
        raise SrsEngineError("config must be an SrsConfig")
    assert_pinned_library()
    if config.enable_fuzzing:
        # fuzz draws from the global random(); results could not be replayed
        # or retried identically. Policy: off (APPROVAL_2026-10-09 item 1).
        raise SrsEngineError("fuzzing is not allowed")
    scheduler = Scheduler(
        parameters=config.parameters,
        desired_retention=config.desired_retention,
        learning_steps=tuple(timedelta(seconds=s) for s in config.learning_steps_seconds),
        relearning_steps=tuple(timedelta(seconds=s) for s in config.relearning_steps_seconds),
        maximum_interval=config.maximum_interval_days,
        enable_fuzzing=config.enable_fuzzing,
    )
    if _scheduler_settings(scheduler) != _config_settings(config):
        raise SrsEngineError("scheduler settings do not match the config")
    return scheduler


def _config_settings(config: SrsConfig) -> dict[str, Any]:
    return {
        "parameters": [float(value) for value in config.parameters],
        "desired_retention": float(config.desired_retention),
        "learning_steps": [int(s) for s in config.learning_steps_seconds],
        "relearning_steps": [int(s) for s in config.relearning_steps_seconds],
        "maximum_interval": int(config.maximum_interval_days),
        "enable_fuzzing": bool(config.enable_fuzzing),
    }


def _scheduler_settings(scheduler: Scheduler) -> dict[str, Any]:
    data = scheduler.to_dict()
    return {
        "parameters": [float(value) for value in data["parameters"]],
        "desired_retention": float(data["desired_retention"]),
        "learning_steps": [int(s) for s in data["learning_steps"]],
        "relearning_steps": [int(s) for s in data["relearning_steps"]],
        "maximum_interval": int(data["maximum_interval"]),
        "enable_fuzzing": bool(data["enable_fuzzing"]),
    }


@functools.lru_cache(maxsize=8)
def _scheduler_for(config: SrsConfig) -> Scheduler:
    # Private and keyed by the (frozen, hashable) config itself, so the
    # scheduler used for a review is always the one built from the config
    # whose config_version is recorded. Never handed out to callers.
    return build_scheduler(config)


def to_utc(value: datetime, name: str = "datetime") -> datetime:
    """Accepts only timezone-aware datetimes; returns the same instant with
    tzinfo exactly timezone.utc (the library rejects any other tzinfo)."""
    if not isinstance(value, datetime):
        raise SrsEngineError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SrsEngineError(f"{name} must be timezone-aware")
    try:
        return value.astimezone(timezone.utc)
    except OverflowError:  # e.g. 0001-01-01 with a positive offset: no UTC instant
        raise SrsEngineError(f"{name} is outside the supported range") from None


def validate_state(state: SrsCardState) -> None:
    if not isinstance(state.phase, SrsPhase):
        raise SrsEngineError("phase must be an SrsPhase")
    if state.phase is SrsPhase.REVIEW:
        if state.step is not None:
            raise SrsEngineError("review state must not have a step")
    elif isinstance(state.step, bool) or not isinstance(state.step, int) or state.step < 0:
        raise SrsEngineError("learning/relearning state needs a step >= 0")
    for name, low, high in (
        ("stability", STABILITY_MIN, math.inf),
        ("difficulty", DIFFICULTY_MIN, DIFFICULTY_MAX),
    ):
        value = getattr(state, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SrsEngineError(f"{name} must be a finite number")
        try:
            finite = math.isfinite(value)
        except OverflowError:  # an int too large for a float (e.g. 10**400): not a valid state
            finite = False
        if not finite:
            raise SrsEngineError(f"{name} must be a finite number")
        if not low <= value <= high:
            raise SrsEngineError(f"{name} out of range")
    for name in ("due_at", "last_review_at"):
        value = getattr(state, name)
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise SrsEngineError(f"{name} must be a UTC datetime")
    if state.due_at < state.last_review_at:
        raise SrsEngineError("due_at is before last_review_at")


def validate_state_for_config(state: SrsCardState, config: SrsConfig) -> None:
    """A Learning/Relearning step must exist in the config the card is scheduled
    with. The library treats step >= len(steps) as "past the last step" and
    promotes the card to Review, so an out-of-range stored step would silently
    skip learning. Never repaired here: the card is rejected as invalid."""
    if state.phase is SrsPhase.LEARNING:
        steps = config.learning_steps_seconds
    elif state.phase is SrsPhase.RELEARNING:
        steps = config.relearning_steps_seconds
    else:
        return
    if not 0 <= state.step < len(steps):
        raise SrsEngineError("step outside the configured learning steps")


# Configs a stored card may reference. Cards with any other version are
# unsupported (queue: unsupported_config; reviews: unsupported_config_version).
CONFIGS_BY_VERSION = {DEFAULT_CONFIG.config_version: DEFAULT_CONFIG}


def _to_library_card(card_id: int, state: SrsCardState | None, at: datetime) -> Card:
    if state is None:
        return Card(card_id=card_id, state=State.Learning, step=0, due=at, last_review=None)
    return Card(
        card_id=card_id,
        state=_PHASE_TO_STATE[state.phase],
        step=state.step,
        stability=float(state.stability),
        difficulty=float(state.difficulty),
        due=state.due_at,
        last_review=state.last_review_at,
    )


def _from_library_card(card: Card) -> SrsCardState:
    if card.stability is None or card.difficulty is None or card.last_review is None:
        raise SrsEngineError("library returned an incomplete card")
    return SrsCardState(
        phase=_STATE_TO_PHASE[State(card.state)],
        step=card.step,
        stability=float(card.stability),
        difficulty=float(card.difficulty),
        due_at=to_utc(card.due, "due"),
        last_review_at=to_utc(card.last_review, "last_review"),
    )


def review(
    key: CardKey,
    state: SrsCardState | None,
    rating: str,
    reviewed_at: datetime,
    config: SrsConfig = DEFAULT_CONFIG,
) -> ReviewOutcome:
    """One rating at an explicit UTC time. Pure: same inputs, same result.
    The schedule is computed and recorded from the same `config`."""
    if not isinstance(key, CardKey):
        raise SrsEngineError("key must be a CardKey")
    if rating not in RATINGS:
        raise SrsEngineError(f"unknown rating: {rating!r}")
    at = to_utc(reviewed_at, "reviewed_at")
    if state is not None:
        validate_state(state)
        validate_state_for_config(state, config)
        if at < state.last_review_at:
            raise SrsEngineError("reviewed_at is earlier than the card's last review")
    scheduler = _scheduler_for(config)
    card, _log = scheduler.review_card(
        _to_library_card(key.ref_id, state, at), RATINGS[rating], review_datetime=at
    )
    after = _from_library_card(card)
    elapsed = None if state is None else (at - state.last_review_at).total_seconds()
    return ReviewOutcome(
        key=key,
        rating=rating,
        reviewed_at=at,
        before=state,
        after=after,
        elapsed_seconds=elapsed,
        config_version=config.config_version,
    )


def preview_due(
    key: CardKey,
    state: SrsCardState | None,
    at: datetime,
    config: SrsConfig = DEFAULT_CONFIG,
) -> dict[str, datetime]:
    """Next due per rating if the card were rated at `at`. Read-only estimate."""
    return {
        rating: review(key, state, rating, at, config).after.due_at
        for rating in RATINGS
    }


def retrievability(state: SrsCardState | None, at: datetime, config: SrsConfig = DEFAULT_CONFIG) -> float | None:
    if state is None:
        return None
    at = to_utc(at)
    scheduler = _scheduler_for(config)
    # card_id is only a label for the library; identity stays with CardKey.
    return float(scheduler.get_card_retrievability(_to_library_card(1, state, at), at))


# --- serialization ---------------------------------------------------------

STATE_KEYS = ("phase", "step", "stability", "difficulty", "due_at", "last_review_at")


def state_to_dict(state: SrsCardState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "phase": state.phase.value,
        "step": state.step,
        "stability": state.stability,
        "difficulty": state.difficulty,
        "due_at": state.due_at.isoformat(),
        "last_review_at": state.last_review_at.isoformat(),
    }


def state_from_dict(data: Mapping[str, Any] | None) -> SrsCardState | None:
    if data is None:
        return None
    if not isinstance(data, Mapping) or set(data) != set(STATE_KEYS):
        raise SrsEngineError("state dict must have exactly the known keys")
    try:
        phase = SrsPhase(data["phase"])
        due_at = to_utc(datetime.fromisoformat(data["due_at"]), "due_at")
        last_review_at = to_utc(datetime.fromisoformat(data["last_review_at"]), "last_review_at")
    except (TypeError, ValueError) as error:
        if isinstance(error, SrsEngineError):
            raise
        raise SrsEngineError("invalid state dict value") from None
    return SrsCardState(
        phase=phase,
        step=data["step"],
        stability=data["stability"],
        difficulty=data["difficulty"],
        due_at=due_at,
        last_review_at=last_review_at,
    )


def state_to_json(state: SrsCardState | None) -> str:
    return json.dumps(state_to_dict(state), sort_keys=True, separators=(",", ":"))


def state_from_json(text: str) -> SrsCardState | None:
    try:
        data = json.loads(text)
    except (TypeError, ValueError, RecursionError):  # RecursionError: nesting too deep
        raise SrsEngineError("invalid state json") from None
    return state_from_dict(data)
