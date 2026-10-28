// FSRS 화면 지표 테스트 (Gate D-1). 실행: node --test components/srsMetrics.test.mts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  dueNowCount,
  homeReviewView,
  metricsSummary,
  msUntilSeoulMidnight,
  newCandidateCount,
  newGoalText,
  parseQueueCounts,
  planTodayText,
  statusDistribution,
  todayReviewsText,
} from "./srsMetrics.ts";
import type { CategoryCounts, MetricsEntry } from "./srsMetrics.ts";
import type { StudyStats } from "./types.ts";
import type { NewGoalDisplay } from "./studySession.ts";

function counts(extra: Partial<CategoryCounts> = {}): CategoryCounts {
  const base: CategoryCounts = {
    learning_due: 0, relearning_due: 0, review_due: 0, pending_later: 0, new_available: 0, new_unmaterialized: 0,
    paused: 0, not_converted: 0, blocked_history: 0, invalid_state: 0, unsupported_config: 0, missing_due: 0,
    total_in_scope: 0,
  };
  const merged = { ...base, ...extra };
  if (extra.total_in_scope === undefined) {
    merged.total_in_scope = Object.entries(merged).reduce((sum, [key, value]) => (key === "total_in_scope" ? sum : sum + value), 0);
  }
  return merged;
}

const exactGoal = { kind: "exact" as const, basis: "account" as const, introduced: 2, goal: 20, remaining: 18 };

test("counts 엄격 해석: 범주 누락·음수·문자열은 null", () => {
  const ok = parseQueueCounts({ counts: { ...counts({ review_due: 2 }), new_allowed_now: 3, excluded_by_request: 0 } });
  assert.ok(ok);
  assert.equal(ok.review_due, 2);
  const { missing_due: _omit, ...missing } = counts();
  assert.equal(parseQueueCounts({ counts: missing }), null);
  assert.equal(parseQueueCounts({ counts: { ...counts(), paused: -1 } }), null);
  assert.equal(parseQueueCounts({ counts: { ...counts(), paused: "1" } }), null);
  assert.equal(parseQueueCounts(null), null);
});

test("지금 복습 가능은 학습·재학습·장기 due만, 신규 제외", () => {
  const c = counts({ learning_due: 1, relearning_due: 2, review_due: 3, new_available: 9, new_unmaterialized: 4, pending_later: 7 });
  assert.equal(dueNowCount(c), 6);
  assert.equal(newCandidateCount(c), 13);
});

test("상태 분포: 제외 범주를 정상과 합치지 않고, 합계 일치 확인", () => {
  const c = counts({ review_due: 2, not_converted: 3, blocked_history: 1, invalid_state: 1 });
  const d = statusDistribution(c);
  assert.equal(d.consistent, true);
  assert.equal(d.total, 7);
  assert.deepEqual(d.excluded.filter((r) => r.count > 0).map((r) => r.key), ["not_converted", "blocked_history", "invalid_state"]);
  assert.ok(d.normal.every((r) => !["not_converted", "blocked_history", "invalid_state"].includes(r.key)));
  assert.equal(statusDistribution({ ...c, total_in_scope: 99 }).consistent, false);
});

test("신규 목표 줄: 확인 불가는 0이 아님, 기준 표기", () => {
  assert.equal(newGoalText(exactGoal), "오늘 새 단어 2 / 목표 20 · 계정 기준");
  assert.equal(newGoalText({ kind: "unknown", basis: "plan", atLeast: 1, goal: 5 }), "오늘 새 단어: 확인할 수 없음 (적어도 1개) · 학습 계획 기준");
  assert.equal(newGoalText(null), "오늘 새 단어: 확인할 수 없음");
});

const ok = (c: CategoryCounts, goal: NewGoalDisplay = exactGoal, remaining: number | null = 18): MetricsEntry =>
  ({ status: "ok", counts: c, goal, effectiveRemaining: remaining });

test("홈 FSRS: 확인 중·실패·확인 불가·실제 0·있음 구분", () => {
  assert.equal(homeReviewView({ kind: "fsrs", mode: "checking", entry: undefined }).state, "loading");
  assert.equal(homeReviewView({ kind: "fsrs", mode: "fsrs", entry: { status: "loading" } }).value, "확인 중");
  const failed = homeReviewView({ kind: "fsrs", mode: "fsrs", entry: { status: "error" } });
  assert.equal(failed.state, "unknown");
  assert.equal(failed.value, "확인할 수 없음");
  assert.equal(homeReviewView({ kind: "fsrs", mode: "error", entry: undefined }).value, "확인할 수 없음");
  const due = homeReviewView({ kind: "fsrs", mode: "fsrs", entry: ok(counts({ review_due: 3, new_available: 5 })) });
  assert.equal(due.state, "due");
  assert.equal(due.value, "3개");
  assert.equal(due.label, "지금 복습");
  assert.equal(due.note, "오늘 새 단어 2 / 목표 20 · 계정 기준");
  const startNew = homeReviewView({ kind: "fsrs", mode: "fsrs", entry: ok(counts({ new_available: 5 }), exactGoal, 3) });
  assert.equal(startNew.value, "0개");
  assert.equal(startNew.note, "새 단어 3개를 시작할 수 있어요 →");
  assert.equal(startNew.action, "start");
  const reached = homeReviewView({ kind: "fsrs", mode: "fsrs", entry: ok(counts({ new_available: 5 }), exactGoal, 0) });
  assert.equal(reached.note, "오늘 새 단어 목표를 채웠어요");
  const unknown = homeReviewView({ kind: "fsrs", mode: "fsrs",
    entry: ok(counts({ new_available: 5 }), { kind: "unknown", basis: "account", atLeast: 1, goal: 20 }, null) });
  assert.equal(unknown.value, "0개");
  assert.match(unknown.note, /확인할 수 없음 \(적어도 1개\)/);
  const done = homeReviewView({ kind: "fsrs", mode: "fsrs", entry: ok(counts({ pending_later: 2 })) });
  assert.equal(done.note, "지금 할 복습을 마쳤어요");
});

test("홈 legacy: 조회 실패는 0이 아니고, 실제 0과 로딩을 구분", () => {
  const stats = { due_today_count: 0 } as StudyStats;
  assert.equal(homeReviewView({ kind: "legacy", stats, loading: false, failed: false }).value, "0개");
  assert.equal(homeReviewView({ kind: "legacy", stats: { due_today_count: 4 } as StudyStats, loading: false, failed: false }).action, "start");
  const failed = homeReviewView({ kind: "legacy", stats: null, loading: false, failed: true });
  assert.equal(failed.state, "unknown");
  assert.equal(failed.value, "확인할 수 없음");
  assert.equal(homeReviewView({ kind: "legacy", stats: null, loading: true, failed: false }).state, "loading");
  assert.equal(homeReviewView({ kind: "legacy", stats: null, loading: false, failed: false }).state, "loading");
  assert.equal(homeReviewView({ kind: "guest" }).action, "account");
});

test("홈 legacy 재조회 실패: 캐시 없음·0·양수 모두 실패를 우선, 복구되면 새 값", () => {
  const caches: Array<StudyStats | null> = [null, { due_today_count: 0 } as StudyStats, { due_today_count: 5 } as StudyStats];
  for (const stats of caches) {
    const label = `cache=${stats ? stats.due_today_count : "none"}`;
    const failed = homeReviewView({ kind: "legacy", stats, loading: false, failed: true });
    assert.equal(failed.state, "unknown", label);
    assert.equal(failed.value, "확인할 수 없음", label);
    assert.notEqual(failed.note, "오늘은 모두 끝냈어요", label);
    assert.equal(failed.action, "study", label);
    // 실패 뒤 다시 조회하는 동안은 확인 중(이전 캐시를 사실처럼 보이지 않음).
    assert.equal(homeReviewView({ kind: "legacy", stats, loading: true, failed: true }).state, "loading", label);
    // 실패 이력 없이 다시 읽는 중이면 캐시를 유지(깜빡임 없음), 캐시 없으면 확인 중.
    const refreshing = homeReviewView({ kind: "legacy", stats, loading: true, failed: false });
    assert.equal(refreshing.state, stats ? (stats.due_today_count > 0 ? "due" : "zero") : "loading", label);
  }
  // 복구: 성공 응답(failed=false)이면 새 값.
  const recovered = homeReviewView({ kind: "legacy", stats: { due_today_count: 2 } as StudyStats, loading: false, failed: false });
  assert.equal(recovered.value, "2개");
  assert.equal(recovered.action, "start");
});

test("요약 줄: 확인 중·실패는 숫자 없음", () => {
  assert.equal(metricsSummary(undefined, "checking"), "복습 수 확인 중");
  assert.equal(metricsSummary({ status: "error" }, "fsrs"), "복습 수를 확인할 수 없어요");
  assert.equal(metricsSummary(ok(counts({ learning_due: 1 })), "fsrs"), "지금 복습 1개 · 오늘 새 단어 2 / 목표 20 · 계정 기준");
});

test("서울 자정까지 남은 시간", () => {
  // 2026-10-10 14:59:00 UTC = 23:59 KST → 1분
  assert.equal(msUntilSeoulMidnight(Date.parse("2026-10-10T14:59:00Z")), 60_000);
  // 2026-10-10 15:00:00 UTC = 00:00 KST → 하루
  assert.equal(msUntilSeoulMidnight(Date.parse("2026-10-10T15:00:00Z")), 24 * 60 * 60 * 1000);
});

test("계획 범위 오늘 새 단어와 서울 오늘 평가 문구", () => {
  assert.equal(planTodayText({ planDailyNew: 5, introducedInScope: 2, introducedInScopeStatus: "exact", introducedInScopeAtLeast: 2 }),
    "오늘 이 덱 새 단어 2 / 계획 5개");
  assert.equal(planTodayText({ planDailyNew: 5, introducedInScope: null, introducedInScopeStatus: "unknown", introducedInScopeAtLeast: 1 }),
    "오늘 이 덱 새 단어: 확인할 수 없음 (적어도 1개)");
  assert.equal(todayReviewsText({ date: "2026-10-10", reviews: { status: "exact", total: 0, at_least: 0 } }), "0회");
  assert.equal(todayReviewsText({ date: "2026-10-10", reviews: { status: "unknown", total: null, at_least: 3 } }), "확인할 수 없음 (적어도 3회)");
  assert.equal(todayReviewsText(undefined), "-");
});
