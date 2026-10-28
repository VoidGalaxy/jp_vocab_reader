"""Synthetic completion-timing simulation for the Gate B-1 report.

Runs the real pinned fsrs library through app.srs.engine with the approved
config and evaluates the '학습 완료' draft after every review. No database,
no network, no randomness (fuzz off). The rating patterns are invented;
results describe what the scheduler + draft rules do, not learning effect.

Usage (from backend/):
    python scripts/simulate_srs_completion.py [output.md]
Prints a markdown report; with a path, also writes it there.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.srs.completion import (  # noqa: E402
    MIN_SPACED_SUCCESS,
    MIN_SPACED_SUCCESSES,
    MIN_STABILITY_DAYS,
    MIN_SUCCESS_DATES,
    CompletionStatus,
    ReviewEvent,
    evaluate_completion,
)
from app.srs.engine import DEFAULT_CONFIG, CardKey, SrsCardState, review  # noqa: E402

START = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)  # 10:00 KST
KEY = CardKey("lexeme", 1, 1)
MAX_REVIEWS = 40
MAX_DAYS = 730


@dataclass
class Scenario:
    name: str
    description: str
    # (review number starting at 1, state before) -> rating
    rate: Callable[[int, SrsCardState | None], str]
    # (state after, review time) -> next review time
    next_time: Callable[[SrsCardState, datetime], datetime] = lambda state, at: state.due_at
    stop_after_completions: int = 1


def same_day_then_stop(state, at):
    return at + timedelta(minutes=10)


SCENARIOS = [
    Scenario("good_always", "매번 due 시각에 보통", lambda n, s: "good"),
    Scenario("easy_always", "매번 due 시각에 쉬움", lambda n, s: "easy"),
    Scenario("hard_always", "첫 평가부터 매번 due 시각에 어려움", lambda n, s: "hard"),
    Scenario("hard_after_review", "보통 2회로 Review 진입 후 매번 어려움", lambda n, s: "good" if n <= 2 else "hard"),
    Scenario("again_first_then_good", "첫 평가 다시, 이후 보통", lambda n, s: "again" if n == 1 else "good"),
    Scenario("good_with_mid_again", "보통, 4번째 평가만 다시, 이후 보통", lambda n, s: "again" if n == 4 else "good"),
    Scenario("again_after_completion", "보통으로 완료(4번째) 직후 5번째 다시, 이후 보통으로 재완료까지",
             lambda n, s: "again" if n == 5 else "good", stop_after_completions=2),
    Scenario("hard_good_alternate", "어려움·보통 번갈아", lambda n, s: "hard" if n % 2 else "good"),
    Scenario("good_late_3d", "보통, 매번 due보다 3일 늦게", lambda n, s: "good",
             lambda state, at: state.due_at + timedelta(days=3)),
    Scenario("same_day_repeat", "같은 날 10분마다 보통 20회 (그 뒤 관측 종료)", lambda n, s: "good", same_day_then_stop),
]


def run(scenario: Scenario):
    state: SrsCardState | None = None
    at = START
    events: list[ReviewEvent] = []
    rows = []
    completed_at_review = None
    completions = 0
    previous_completed = False
    limit = 20 if scenario.name == "same_day_repeat" else MAX_REVIEWS
    for n in range(1, limit + 1):
        if at - START > timedelta(days=MAX_DAYS):
            break
        rating = scenario.rate(n, state)
        outcome = review(KEY, state, rating, at, DEFAULT_CONFIG)
        state = outcome.after
        events.append(ReviewEvent(at, rating))
        check = evaluate_completion(state, events, evidence_complete=True)
        rows.append((n, at, rating, state, check))
        is_completed = check.status is CompletionStatus.COMPLETED
        if is_completed and not previous_completed:
            completions += 1
            completed_at_review = completed_at_review or n
            if completions >= scenario.stop_after_completions:
                break
        previous_completed = is_completed
        at = scenario.next_time(state, at)
    return rows, completed_at_review


def fmt_interval(delta: timedelta) -> str:
    seconds = delta.total_seconds()
    if seconds < 3600:
        return f"{seconds / 60:.0f}분"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}시간"
    return f"{seconds / 86400:.0f}일"


def report() -> str:
    lines = [
        "# 합성 시뮬레이션: 학습 완료(V3 meaning-completion-v1) 도달 시점",
        "",
        f"엔진: fsrs 6.3.2 실제 실행, 설정 `{DEFAULT_CONFIG.config_version}` "
        "(기본 파라미터, 유지율 0.90, 학습 1분·10분, 재학습 10분, 최대 365일, fuzz 끔).",
        f"완료 기준 V3: Review + S>={MIN_STABILITY_DAYS:.0f}일 + 마지막 다시 이후 서울 날짜 {MIN_SUCCESS_DATES}개 성공 + "
        f"직전 평가와 {MIN_SPACED_SUCCESS.days}일 이상 간격 성공 {MIN_SPACED_SUCCESSES}회.",
        f"시작 {START.isoformat()} (10:00 KST). 관측 한도: 평가 {MAX_REVIEWS}회 또는 {MAX_DAYS}일.",
        "평가 패턴은 가상이다. 결과는 스케줄러와 완료 규칙의 동작이며 학습 효과가 아니다.",
        "",
        "## 요약",
        "",
        "| 시나리오 | 패턴 | 결과 | 평가 수 | 첫 평가부터 경과 | 그때 S(일) | 마지막 다음 간격 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    details = []
    for scenario in SCENARIOS:
        rows, done = run(scenario)
        n, at, rating, state, check = rows[-1]
        elapsed = at - START
        result = (f"도달 ({done}번째)" + (", 실패 후 재도달" if scenario.stop_after_completions > 1 and rows[-1][4].status is CompletionStatus.COMPLETED else "")) if done else "미도달 (관측 종료)"
        lines.append(
            f"| {scenario.name} | {scenario.description} | {result} | {n} | "
            f"{elapsed.total_seconds() / 86400:.1f}일 | {state.stability:.1f} | {fmt_interval(state.due_at - at)} |"
        )
        details += [
            "",
            f"### {scenario.name}: {scenario.description}",
            "",
            "| # | 평가 시각(UTC) | 평가 | 단계 | S(일) | D | 다음 간격 | 완료 판정 | 미충족 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for n, at, rating, state, check in rows:
            details.append(
                f"| {n} | {at.strftime('%Y-%m-%d %H:%M')} | {rating} | {state.phase.value}"
                f"{'' if state.step is None else f'/{state.step}'} | {state.stability:.2f} | {state.difficulty:.2f} | "
                f"{fmt_interval(state.due_at - at)} | {check.status.value} | {', '.join(check.reasons) or '-'} |"
            )
    return "\n".join(lines + details) + "\n"


def main() -> None:
    text = report()
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_bytes(text.encode("utf-8"))
    sys.stdout.buffer.write(text.encode("utf-8"))


if __name__ == "__main__":
    main()
