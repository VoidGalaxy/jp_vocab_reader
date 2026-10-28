"""Gate D-0: independent synthetic comparison of '학습 완료' criteria.

Documentation-only tool. It is not imported by the product and changes nothing:
no database, no network, no settings. It drives the same pinned engine adapter
(`app.srs.engine.review`, fsrs 6.3.2, approved config, fuzz off) read-only, and
re-implements the completion rules locally so alternatives can be compared. The
current rule is cross-checked against `app.srs.completion.evaluate_completion`
on every step.

Everything here is synthetic. Rating patterns and the simulated learner are
assumptions; results describe how the scheduler and the rules behave, NOT
learning effect or recall accuracy.

Usage (from backend/, with the backend venv):
    python ../docs/plans/srs-improvement/gate-d0/completion_sim.py [output.md]
"""

from __future__ import annotations

import random
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

BACKEND = Path(__file__).resolve().parents[4] / "backend"
sys.path.insert(0, str(BACKEND))

from fsrs.scheduler import DEFAULT_PARAMETERS  # noqa: E402

from app.srs.completion import (  # noqa: E402
    CompletionStatus,
    ReviewEvent,
    evaluate_completion,
    seoul_date,
)
from app.srs.engine import DEFAULT_CONFIG, SUCCESS_RATINGS, CardKey, SrsCardState, SrsPhase, review  # noqa: E402

START = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)  # 10:00 KST
KEY = CardKey("lexeme", 1, 1)
MAX_REVIEWS = 60
HORIZON_DAYS = 365
SEED = 20261011


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    min_stability: float
    min_dates: int
    spaced_gap_days: int
    min_spaced: int


VARIANTS = (
    Variant("V1", "현 기준: S≥30, 성공 날짜 2개, 7일 간격 성공 1회", 30.0, 2, 7, 1),
    Variant("V2", "보수안 A: S≥60, 성공 날짜 3개, 14일 간격 성공 1회", 60.0, 3, 14, 1),
    Variant("V3", "보수안 B: S≥30, 성공 날짜 3개, 7일 간격 성공 2회", 30.0, 3, 7, 2),
)


def completed(variant: Variant, state: SrsCardState | None, events: list[ReviewEvent]) -> bool:
    """Complete-evidence rule (same structure as completion.py, parameterised)."""
    if state is None or state.phase is not SrsPhase.REVIEW or state.stability < variant.min_stability:
        return False
    last_again = max((i for i, e in enumerate(events) if e.rating == "again"), default=-1)
    successes = [i for i in range(last_again + 1, len(events)) if events[i].rating in SUCCESS_RATINGS]
    dates = {seoul_date(events[i].reviewed_at) for i in successes}
    gap = timedelta(days=variant.spaced_gap_days)
    spaced = sum(1 for i in successes if i > 0 and events[i].reviewed_at - events[i - 1].reviewed_at >= gap)
    return len(dates) >= variant.min_dates and spaced >= variant.min_spaced


def check_against_product(state: SrsCardState, events: list[ReviewEvent]) -> None:
    product = evaluate_completion(state, events, evidence_complete=True).status is CompletionStatus.COMPLETED
    # Gate D-2 U11: the product rule is now V3 (`meaning-completion-v1`).
    mine = completed(VARIANTS[2], state, events)
    if product != mine:
        raise AssertionError(f"V3 re-implementation differs from completion.py at {events[-1]}")


# ---- deterministic patterns ------------------------------------------------------

Rater = Callable[[int, SrsCardState | None], tuple[str, timedelta]]


@dataclass(frozen=True)
class Pattern:
    name: str
    label: str
    rate: Rater  # (index, state) -> (rating, extra delay after due)


def constant(rating: str, late: timedelta = timedelta(0)) -> Rater:
    return lambda i, s: (rating, late)


PATTERNS = (
    Pattern("easy_always", "매번 due 시각에 쉬움", constant("easy")),
    Pattern("good_always", "매번 due 시각에 보통", constant("good")),
    Pattern("hard_after_review", "보통 2회 뒤 매번 어려움", lambda i, s: ("good" if i < 2 else "hard", timedelta(0))),
    Pattern("again_first_then_good", "첫 평가 다시, 이후 보통", lambda i, s: ("again" if i == 0 else "good", timedelta(0))),
    Pattern("good_with_mid_again", "보통, 4번째만 다시", lambda i, s: ("again" if i == 3 else "good", timedelta(0))),
    Pattern("hard_good_alternate", "어려움·보통 번갈아", lambda i, s: ("hard" if i % 2 == 0 else "good", timedelta(0))),
    Pattern("good_late_3d", "보통, 매번 due보다 3일 늦게", lambda i, s: ("good", timedelta(days=3) if i > 0 else timedelta(0))),
    Pattern("good_late_30d", "보통, 매번 due보다 30일 늦게", lambda i, s: ("good", timedelta(days=30) if i > 0 else timedelta(0))),
)


def run_pattern(pattern: Pattern) -> dict[str, tuple[int, float] | None]:
    state: SrsCardState | None = None
    events: list[ReviewEvent] = []
    at = START
    first: dict[str, tuple[int, float] | None] = {v.name: None for v in VARIANTS}
    for i in range(MAX_REVIEWS):
        rating, late = pattern.rate(i, state)
        if state is not None:
            at = state.due_at + late
        if (at - START).days > HORIZON_DAYS * 2:
            break
        outcome = review(KEY, state, rating, at)
        state = outcome.after
        events.append(ReviewEvent(at, rating))
        check_against_product(state, events)
        for variant in VARIANTS:
            if first[variant.name] is None and completed(variant, state, events):
                first[variant.name] = (i + 1, (at - START).total_seconds() / 86400)
        if all(first.values()):
            break
    return first


def after_completion_failure() -> list[str]:
    """Each variant: complete with Good, then Again at the next due, then Good until re-completion."""
    rows = []
    for variant in VARIANTS:
        state, events, at = None, [], START
        phase, completed_at, failed_at, reached_again = "before", None, None, None
        for i in range(MAX_REVIEWS):
            if state is not None:
                at = state.due_at
            rating = "again" if phase == "fail_next" else "good"
            state = review(KEY, state, rating, at).after
            events.append(ReviewEvent(at, rating))
            done = completed(variant, state, events)
            if phase == "before" and done:
                phase, completed_at = "fail_next", (i + 1, at)
            elif phase == "fail_next":
                phase, failed_at = "after", (i + 1, at)
            elif phase == "after" and done:
                reached_again = (i + 1, at)
                break
        if completed_at and failed_at and reached_again:
            rows.append(
                f"| {variant.name} | {completed_at[0]}번째 ({(completed_at[1] - START).days}일) | "
                f"{failed_at[0]}번째 ({(failed_at[1] - START).days}일) | "
                f"{reached_again[0] - failed_at[0]}회 더, {(reached_again[1] - failed_at[1]).days}일 뒤 |"
            )
        else:
            rows.append(f"| {variant.name} | 관측 한도 안에서 재완료 없음 | - | - |")
    return rows


# ---- simulated learner (assumption, not data) --------------------------------------

DECAY = -DEFAULT_PARAMETERS[20]
FACTOR = 0.9 ** (1 / DECAY) - 1


def recall_probability(elapsed_days: float, true_stability: float) -> float:
    """FSRS-6 forgetting-curve shape, evaluated with the learner's *assumed* true stability."""
    return (1 + FACTOR * max(elapsed_days, 0.0) / max(true_stability, 1e-6)) ** DECAY


@dataclass(frozen=True)
class Learner:
    name: str
    label: str
    true_ratio: float  # learner's true stability / model stability


LEARNERS = (
    Learner("calibrated", "모델 안정도와 같은 기억(가정)", 1.0),
    Learner("weaker", "모델 안정도의 0.5배 기억(가정)", 0.5),
)
CARDS_PER_LEARNER = 800


def simulate_learner(learner: Learner, rng: random.Random) -> dict[str, dict[str, float]]:
    stats = {v.name: {"reached": 0, "reviews": [], "days": [], "observed_next": 0, "fail_next": 0,
                      "relapses": 0, "exposure_days": 0.0, "completed_end": 0}
             for v in VARIANTS}
    for _ in range(CARDS_PER_LEARNER):
        state: SrsCardState | None = None
        events: list[ReviewEvent] = []
        at = START
        first_done: dict[str, int | None] = {v.name: None for v in VARIANTS}
        next_after: dict[str, bool] = {v.name: False for v in VARIANTS}
        for i in range(MAX_REVIEWS * 2):
            if state is not None:
                at = state.due_at
            if (at - START).days > HORIZON_DAYS:
                break
            if state is None:
                rating = "good" if rng.random() < 0.7 else "again"  # first sight: 70% known (assumption)
            else:
                elapsed = (at - state.last_review_at).total_seconds() / 86400
                p = recall_probability(elapsed, state.stability * learner.true_ratio)
                rating = "good" if rng.random() < p else "again"
            before = state
            state = review(KEY, state, rating, at).after
            events.append(ReviewEvent(at, rating))
            for variant in VARIANTS:
                name = variant.name
                if next_after[name]:
                    # 완료 뒤 다음 평가가 관측 기간 안에서 실제로 일어났다.
                    next_after[name] = False
                    stats[name]["observed_next"] += 1
                    if rating == "again":
                        stats[name]["fail_next"] += 1
                if first_done[name] is not None and rating == "again" and before is not None \
                        and before.phase is SrsPhase.REVIEW:
                    stats[name]["relapses"] += 1
                if first_done[name] is None and completed(variant, state, events):
                    first_done[name] = i + 1
                    next_after[name] = True
                    stats[name]["reached"] += 1
                    stats[name]["reviews"].append(i + 1)
                    stats[name]["days"].append((at - START).total_seconds() / 86400)
                    # 완료 뒤 관측 기간(이 카드가 완료 상태로 지켜본 날 수): 기준마다 다르다.
                    stats[name]["exposure_days"] += HORIZON_DAYS - (at - START).total_seconds() / 86400
        for variant in VARIANTS:
            if state is not None and completed(variant, state, events):
                stats[variant.name]["completed_end"] += 1
    return stats


def pct(n: float, d: float) -> str:
    return "-" if d == 0 else f"{100 * n / d:.1f}%"


def med(values: list[float]) -> str:
    return "-" if not values else f"{statistics.median(values):.0f}"


def main() -> str:
    lines = [
        "# Gate D-0 학습 완료 기준 비교 (합성 시뮬레이션)",
        "",
        f"엔진: `app.srs.engine.review` 읽기 전용 사용, 설정 `{DEFAULT_CONFIG.config_version}` (fsrs 6.3.2, 유지율 0.90, 학습 1분·10분, 재학습 10분, 최대 365일, fuzz 끔).",
        f"시작 {START.isoformat()} (10:00 KST). V1은 매 단계 `completion.py`의 실제 판정과 대조해 일치를 확인했다.",
        "**이 결과는 스케줄러와 완료 규칙의 동작 확인이다. 학습 효과·실제 기억률의 증명이 아니다.** 3절의 학습자는 엔진과 같은 "
        "망각 곡선 모양을 가정했으므로, 완료 뒤 실패율이 기준 사이에서 비슷하게 나오는 것은 그 가정의 결과이며 기준들의 효과가 "
        "같다는 증거가 아니다.",
        "",
        "## 비교한 기준",
        "",
        "| 이름 | 기준 |",
        "| --- | --- |",
    ]
    lines += [f"| {v.name} | {v.label} (모두 Review 단계, 마지막 다시 이후 성공만 셈, 간격은 직전 평가와의 실제 경과) |" for v in VARIANTS]
    lines += ["", "## 1. 고정 평가 패턴: 첫 완료까지 (평가 수 / 첫 평가부터 경과일)", "",
              "| 패턴 | " + " | ".join(v.name for v in VARIANTS) + " |",
              "| --- | " + " | ".join("---" for _ in VARIANTS) + " |"]
    for pattern in PATTERNS:
        result = run_pattern(pattern)
        cells = [f"{r[0]}회 / {r[1]:.1f}일" if r else "관측 한도 안 미도달" for r in (result[v.name] for v in VARIANTS)]
        lines.append(f"| {pattern.label} | " + " | ".join(cells) + " |")
    lines += ["", "## 2. 완료 직후 실패와 재완료 (보통으로 완료 → 다음 due에 다시 → 이후 보통)", "",
              "| 기준 | 첫 완료 | 실패(다시) | 재완료까지 |", "| --- | --- | --- | --- |"]
    lines += after_completion_failure()
    rng = random.Random(SEED)
    lines += ["", f"## 3. 가정한 학습자 {CARDS_PER_LEARNER}장 × 2종, {HORIZON_DAYS}일 관측 (seed {SEED})", "",
              "학습자 모델(가정): 첫 평가 70% 보통·30% 다시. 이후 매번 due 시각에 평가하고, 성공 확률은 FSRS-6 망각 곡선 모양에 "
              "'학습자의 실제 안정도 = 모델 안정도 × 배율'을 넣어 계산한다. 성공은 보통, 실패는 다시로만 평가한다.",
              "배율 1.0은 모델이 맞는 경우, 0.5는 모델이 기억을 과대평가하는 경우를 흉내 낸 것이다. 둘 다 실제 자료가 아니다.", ""]
    for learner in LEARNERS:
        stats = simulate_learner(learner, rng)
        lines += [f"### {learner.label}", "",
                  "| 기준 | 첫 완료 카드 | 평가 수 중앙값 | 경과일 중앙값 | 완료 뒤 다음 평가 관측 | 미관측(365일 넘김) | 그중 실패 | 실패율(실패/관측) | 365일 시점 완료 상태 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for variant in VARIANTS:
            s = stats[variant.name]
            reached, observed = s["reached"], s["observed_next"]
            lines.append(
                f"| {variant.name} | {reached}/{CARDS_PER_LEARNER} | {med(s['reviews'])} | {med(s['days'])} | "
                f"{observed} | {reached - observed} | {s['fail_next']} | {pct(s['fail_next'], observed)} | "
                f"{pct(s['completed_end'], CARDS_PER_LEARNER)} |"
            )
        lines += ["", "완료 뒤 재학습 진입(Review에서 다시)은 완료 시점부터 365일까지의 관측 기간이 기준마다 다르므로 장당이 아니라 "
                  "관측 카드-일 기준으로 적는다.", "",
                  "| 기준 | 완료 뒤 관측 카드-일 합계 | 완료 카드당 평균 관측 일수 | 재학습 진입 수 | 1,000 카드-일당 |",
                  "| --- | --- | --- | --- | --- |"]
        for variant in VARIANTS:
            s = stats[variant.name]
            reached, exposure = s["reached"], s["exposure_days"]
            rate = "-" if exposure == 0 else f"{1000 * s['relapses'] / exposure:.2f}"
            mean_days = "-" if not reached else f"{exposure / reached:.0f}"
            lines.append(f"| {variant.name} | {exposure:.0f} | {mean_days} | {s['relapses']} | {rate} |")
        lines.append("")
    lines += [
        "## 4. 불완전 이력의 확인 불가",
        "",
        "세 기준 모두 C3·C4(성공 날짜·간격 성공)는 마지막 다시 이후 모든 평가가 있어야 증명된다. 따라서 이력이 불완전한 카드는 "
        "어느 기준에서도 현재 상태가 C1·C2를 못 넘으면 '미완료', 넘으면 '확인 불가'이며 '완료'가 되지 않는다(`completion.py`의 "
        "`incomplete_evidence` 처리와 같다). 기준을 바꿔도 이 처리는 같다.",
        "증거 구간을 '초기화 뒤 첫 실제 평가부터'로 정하면, 그 카드의 완료까지 걸리는 평가 수·경과일은 1절의 같은 패턴 결과와 같다"
        "(초기 상태를 신규로 볼 때. 초기 상태 자체는 미결정).",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    report = main()
    print(report)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(report + "\n", encoding="utf-8")
