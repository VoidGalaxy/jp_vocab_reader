// FSRS 계정의 화면 지표 (Gate D-1). 계약: docs/plans/srs-improvement/gate-d0/CONTRACT.md 1절.
//
// 지표는 `/study-queue` 응답의 범주 집계(counts)와 신규 목표(new_goal)에서 나온다. 회차 큐와 같은
// 서버 함수라 복습 탭 회차와 숫자가 어긋나지 않는다. 이 모듈은 해석과 표시 문구만 맡는다.
// - 지금 복습 가능 = learning_due + relearning_due + review_due. 신규는 넣지 않는다.
// - 확인 중·실패·확인 불가는 0으로 표시하지 않는다. 실제 0만 0이다.
// - 학습 완료 수치·완료 예상일은 다루지 않는다(D-C2: 기준 승인 전 비노출).
//
// Node 타입 제거 실행 때문에 값 import를 쓰지 않는다(타입 import만).

import type { NewGoalDisplay } from "./studySession";
import type { StudyStats } from "./types";

export const NORMAL_CATEGORIES = [
  "learning_due",
  "relearning_due",
  "review_due",
  "pending_later",
  "new_available",
  "new_unmaterialized",
  "paused",
] as const;

/** 출제 대상이 아닌 범주. 정상 상태와 합치거나 조용히 빼지 않는다. */
export const EXCLUDED_CATEGORIES = [
  "not_converted",
  "blocked_history",
  "invalid_state",
  "unsupported_config",
  "missing_due",
] as const;

type CategoryKey = (typeof NORMAL_CATEGORIES)[number] | (typeof EXCLUDED_CATEGORIES)[number];

export type CategoryCounts = Record<CategoryKey, number> & { total_in_scope: number };

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/** 응답의 counts를 엄격하게 읽는다. 범주 하나라도 없거나 틀리면 null(조회 실패로 다룸). */
export function parseQueueCounts(raw: unknown): CategoryCounts | null {
  if (typeof raw !== "object" || raw === null) return null;
  const counts = (raw as Record<string, unknown>).counts;
  if (typeof counts !== "object" || counts === null) return null;
  const source = counts as Record<string, unknown>;
  const out: Partial<CategoryCounts> = {};
  const keys: string[] = [...NORMAL_CATEGORIES, ...EXCLUDED_CATEGORIES, "total_in_scope"];
  for (let i = 0; i < keys.length; i += 1) {
    const value = source[keys[i]];
    if (!isCount(value)) return null;
    (out as Record<string, number>)[keys[i]] = value;
  }
  return out as CategoryCounts;
}

/** 지금 복습 가능(학습·재학습·장기 due). 신규는 제외. */
export function dueNowCount(counts: CategoryCounts): number {
  return counts.learning_due + counts.relearning_due + counts.review_due;
}

export function newCandidateCount(counts: CategoryCounts): number {
  return counts.new_available + counts.new_unmaterialized;
}

// ---- 학습 상태 분포 (통계 탭의 legacy 단계 막대를 대체) -----------------------------------

export type DistributionRow = { key: string; label: string; count: number };

export type StatusDistribution = {
  normal: DistributionRow[];
  excluded: DistributionRow[];
  total: number;
  /** 범주 합 = total_in_scope. 아니면 화면에 확인 불가로 알린다. */
  consistent: boolean;
};

const LABELS: Record<CategoryKey, string> = {
  learning_due: "지금 복습 · 학습 단계",
  relearning_due: "지금 복습 · 재학습",
  review_due: "지금 복습 · 장기 복습",
  pending_later: "나중에 복습",
  new_available: "새 단어",
  new_unmaterialized: "새 단어 · 구독 덱 시작 전",
  paused: "복습 보류",
  not_converted: "아직 새 복습 방식으로 옮기지 않음",
  blocked_history: "이력 확인 필요",
  invalid_state: "기억 상태 확인 필요",
  unsupported_config: "복습 설정 확인 필요",
  missing_due: "예약 시각 확인 필요",
};

export function statusDistribution(counts: CategoryCounts): StatusDistribution {
  const normal = NORMAL_CATEGORIES.map((key) => ({ key, label: LABELS[key], count: counts[key] }));
  const excluded = EXCLUDED_CATEGORIES.map((key) => ({ key, label: LABELS[key], count: counts[key] }));
  const sum = [...normal, ...excluded].reduce((total, row) => total + row.count, 0);
  return { normal, excluded, total: counts.total_in_scope, consistent: sum === counts.total_in_scope };
}

// ---- 문구 ------------------------------------------------------------------------

export type MetricsEntry =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ok"; counts: CategoryCounts; goal: NewGoalDisplay | null; effectiveRemaining: number | null };

/** 신규 목표 줄. 확인 불가를 0으로 쓰지 않는다. */
export function newGoalText(goal: NewGoalDisplay | null): string {
  if (!goal) return "오늘 새 단어: 확인할 수 없음";
  const basis = goal.basis === "plan" ? "학습 계획 기준" : "계정 기준";
  if (goal.kind === "unknown") return `오늘 새 단어: 확인할 수 없음 (적어도 ${goal.atLeast}개) · ${basis}`;
  return `오늘 새 단어 ${goal.introduced} / 목표 ${goal.goal} · ${basis}`;
}

/** 복습 준비 화면·학습 현황 등의 한 줄 요약. */
export function metricsSummary(entry: MetricsEntry | undefined, mode: "checking" | "fsrs" | "error"): string {
  if (mode === "checking" || !entry || entry.status === "loading") return "복습 수 확인 중";
  if (mode === "error" || entry.status === "error") return "복습 수를 확인할 수 없어요";
  return `지금 복습 ${dueNowCount(entry.counts)}개 · ${newGoalText(entry.goal)}`;
}

export type HomeReviewState = "login" | "loading" | "unknown" | "zero" | "due";

export type HomeReviewView = {
  state: HomeReviewState;
  label: string;
  value: string;
  note: string;
  aria: string;
  /** start: 복습 시작, study: 복습 탭으로, account: 계정 메뉴, none: 누를 수 없음 */
  action: "start" | "study" | "account" | "none";
};

export type HomeReviewInput =
  | { kind: "guest" }
  | { kind: "legacy"; stats: StudyStats | null; loading: boolean; failed: boolean }
  | { kind: "fsrs"; mode: "checking" | "fsrs" | "error"; entry: MetricsEntry | undefined };

/** 책상(홈) 복습 카드. 확인 중·실패·확인 불가·실제 0을 구별한다. */
export function homeReviewView(input: HomeReviewInput): HomeReviewView {
  if (input.kind === "guest") {
    return { state: "login", label: "오늘 복습", value: "로그인 필요", note: "로그인하고 기록 남기기 →",
      aria: "로그인하고 복습 기록 남기기", action: "account" };
  }
  const loading = (label: string): HomeReviewView =>
    ({ state: "loading", label, value: "확인 중", note: "잠시만요", aria: `${label} 수 확인 중`, action: "none" });
  if (input.kind === "legacy") {
    // failed = 가장 최근 조회가 실패했고 아직 성공한 적이 없음. 이전 숫자(캐시)가 있어도 실패를 먼저
    // 보인다(Gate D-1 보정). 실패 뒤 다시 조회하는 중이면 확인 중, 실패 이력 없이 다시 읽는 중이면 캐시 유지.
    if (input.failed) {
      return input.loading
        ? loading("오늘 복습")
        : { state: "unknown", label: "오늘 복습", value: "확인할 수 없음", note: "복습 탭에서 다시 확인 →",
            aria: "오늘 복습 수를 확인할 수 없음, 복습 탭으로 이동", action: "study" };
    }
    if (input.stats) {
      const due = input.stats.due_today_count;
      return due > 0
        ? { state: "due", label: "오늘 복습", value: `${due}개`, note: "복습 시작 →", aria: `오늘 복습 ${due}개 시작하기`, action: "start" }
        : { state: "zero", label: "오늘 복습", value: "0개", note: "오늘은 모두 끝냈어요", aria: "오늘 복습 0개, 복습 탭으로 이동", action: "study" };
    }
    return loading("오늘 복습");
  }
  const label = "지금 복습";
  if (input.mode === "checking") return loading(label);
  if (input.mode === "error") {
    return { state: "unknown", label, value: "확인할 수 없음", note: "복습 방식을 다시 확인해 주세요 →",
      aria: "복습 방식을 확인할 수 없음, 복습 탭으로 이동", action: "study" };
  }
  const entry = input.entry;
  if (!entry || entry.status === "loading") return loading(label);
  if (entry.status === "error") {
    return { state: "unknown", label, value: "확인할 수 없음", note: "복습 탭에서 다시 확인 →",
      aria: "지금 복습 수를 확인할 수 없음, 복습 탭으로 이동", action: "study" };
  }
  const due = dueNowCount(entry.counts);
  const goalLine = newGoalText(entry.goal);
  if (due > 0) {
    return { state: "due", label, value: `${due}개`, note: goalLine, aria: `지금 복습 ${due}개 시작하기. ${goalLine}`, action: "start" };
  }
  const candidates = newCandidateCount(entry.counts);
  let note: string;
  let action: HomeReviewView["action"] = "study";
  if (entry.goal && entry.goal.kind === "unknown") {
    note = goalLine;
  } else if (candidates > 0 && entry.effectiveRemaining !== null && entry.effectiveRemaining > 0) {
    note = `새 단어 ${Math.min(candidates, entry.effectiveRemaining)}개를 시작할 수 있어요 →`;
    action = "start";
  } else if (candidates > 0 && entry.effectiveRemaining === 0) {
    note = "오늘 새 단어 목표를 채웠어요";
  } else {
    note = "지금 할 복습을 마쳤어요";
  }
  return { state: "zero", label, value: "0개", note, aria: `지금 복습 0개. ${note}`, action };
}

/** 다음 서울 자정까지 남은 밀리초(지표 갱신 타이머). */
export function msUntilSeoulMidnight(nowMs: number): number {
  const KST = 9 * 60 * 60 * 1000;
  const DAY = 24 * 60 * 60 * 1000;
  const seoulMs = nowMs + KST;
  const next = Math.floor(seoulMs / DAY) * DAY + DAY;
  return next - seoulMs;
}

/** 학습 계획: 계획 덱 범위의 오늘 새 단어(계획 하루량 기준). 확인 불가는 하한만. */
export function planTodayText(info: {
  planDailyNew: number | null;
  introducedInScope: number | null;
  introducedInScopeStatus: "exact" | "unknown" | null;
  introducedInScopeAtLeast: number | null;
}): string {
  if (info.introducedInScopeStatus === "exact" && info.introducedInScope !== null) {
    return info.planDailyNew !== null
      ? `오늘 이 덱 새 단어 ${info.introducedInScope} / 계획 ${info.planDailyNew}개`
      : `오늘 이 덱 새 단어 ${info.introducedInScope}개`;
  }
  return `오늘 이 덱 새 단어: 확인할 수 없음 (적어도 ${info.introducedInScopeAtLeast ?? 0}개)`;
}

export type TodaySeoul = {
  date: string;
  reviews: { status: string; total: number | null; at_least: number };
};

/** `/stats`의 today_seoul 평가 횟수(서울 기준). 없으면 "-", 확인 불가는 하한만. */
export function todayReviewsText(today: TodaySeoul | null | undefined): string {
  if (!today || !today.reviews) return "-";
  if (today.reviews.status === "exact" && typeof today.reviews.total === "number") return `${today.reviews.total}회`;
  return `확인할 수 없음 (적어도 ${today.reviews.at_least}회)`;
}
