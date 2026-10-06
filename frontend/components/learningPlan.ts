// 학습 계획(C 패드) 전용 타입과 순수 계산.
//
// UI와 분리된 계산만 둔다. 저장·조회·학습 실행은 여기서 하지 않는다.
// 진도/일정은 "첫 학습 기준"의 임시 참고 지표다. 기억 완성이나 SRS 숙련
// 완료를 뜻하지 않는다 (references/plans/learning-plan-tab/handoff-c/
// DATA_CONTRACT.md "계산 계약").
//
// 날짜는 모두 서울 달력 날짜 문자열(YYYY-MM-DD)이고, 달력 연산은 UTC 자정
// 기준 정수 일수로만 한다. 로컬 시간대/DST를 섞지 않는다.
//
// 이 파일은 Node의 타입 제거 실행으로도 테스트되므로 enum/namespace 같은
// 런타임 TS 문법과 다른 모듈 import를 쓰지 않는다.

export type PlanDeckRef = { kind: "personal" | "subscribed"; id: number };

export type PlanDeckOption = { ref: PlanDeckRef; name: string };

export type PlanDraft = {
  deck: PlanDeckRef | null;
  startDate: string;
  targetDate: string;
  // null = 입력이 비었거나 정수 0~500이 아님 (조용히 0이나 기본값으로 바꾸지 않는다).
  dailyWords: number | null;
};

// deck_cards: 개인 덱 자신의 카드(복사한 덱은 이력 없이 시작).
// account_shared: 구독 덱, 다른 덱에서 학습한 같은 단어도 포함하는 계정 공유 진도.
export type PlanProgressScope = "deck_cards" | "account_shared";

export type PlanProgress =
  | {
      state: "ready";
      deck: PlanDeckRef;
      total: number;
      seen: number;
      scope: PlanProgressScope;
      metricVersion: string;
      asOf: string;
    }
  // missing: 덱이 없거나 구독이 해제됨(404). error: 그 밖의 조회 실패.
  // unavailable: 조회 경로 없음(로그인 전 등).
  | { state: "loading" | "error" | "missing" | "unavailable"; deck: PlanDeckRef | null };

// draft: 작성 중(저장 전 / 저장본과 다름), saved: 저장본과 같음,
// saveError: 마지막 저장 실패(기존 계획은 부모가 보존).
export type PlanSaveState = "draft" | "saved" | "saveError";

export type PlanStatus =
  | "unknown" // 진도 미확인(로딩/오류/미연결/불일치)
  | "invalid" // 날짜·하루량 입력 확인 필요
  | "emptyDeck" // 확인된 전체 0개
  | "expired" // 남은 기간 0일 이하
  | "allSeen" // 남은 0개 (첫 학습 기준, 기억 완료 아님)
  | "paused" // 하루량 0 = 계획 일시 중지
  | "ahead"
  | "onTime"
  | "late";

export const DAILY_WORDS_MIN = 0;
export const DAILY_WORDS_MAX = 500;
export const DURATION_PRESETS = [14, 30, 60] as const;

const DAY_MS = 86_400_000;
const SEOUL_OFFSET_MS = 9 * 60 * 60 * 1000; // 1988년 이후 서울은 DST 없음
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

// ---- 날짜 -----------------------------------------------------------------

/** 실제로 존재하는 YYYY-MM-DD면 1970-01-01부터의 정수 일수, 아니면 null. */
export function toDayNumber(value: string): number | null {
  if (!ISO_DATE.test(value)) return null;
  const ms = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(ms)) return null;
  // 2026-02-30 같은 값은 Date가 다음 달로 넘기므로 왕복 비교로 거른다.
  if (new Date(ms).toISOString().slice(0, 10) !== value) return null;
  return Math.round(ms / DAY_MS);
}

export function fromDayNumber(day: number): string {
  return new Date(day * DAY_MS).toISOString().slice(0, 10);
}

export function addDays(value: string, days: number): string | null {
  const day = toDayNumber(value);
  return day === null ? null : fromDayNumber(day + days);
}

/** 시작일과 목표일을 모두 포함하는 일수. 순서가 틀리거나 날짜가 아니면 null. */
export function inclusiveSpan(startDate: string, targetDate: string): number | null {
  const s = toDayNumber(startDate);
  const t = toDayNumber(targetDate);
  if (s === null || t === null || t < s) return null;
  return t - s + 1;
}

/** 기기 시간대와 무관한 서울 오늘 날짜. 통계 일별 기록과 같은 고정 +09:00 정의. */
export function seoulToday(now: Date): string {
  return new Date(now.getTime() + SEOUL_OFFSET_MS).toISOString().slice(0, 10);
}

export function formatShortDate(value: string): string {
  const day = toDayNumber(value);
  if (day === null) return "—";
  const d = new Date(day * DAY_MS);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

export function formatLongDate(value: string): string {
  const day = toDayNumber(value);
  if (day === null) return "—";
  const d = new Date(day * DAY_MS);
  return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일 ${WEEKDAYS[d.getUTCDay()]}요일`;
}

// ---- 입력 -----------------------------------------------------------------

/** 하루량 입력 문자열 → 정수 0~500 또는 null(빈 값/소수/음수/문자/범위 밖). */
export function parseDailyWords(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value) || value < DAILY_WORDS_MIN || value > DAILY_WORDS_MAX) {
    return null;
  }
  return value;
}

export function stepDailyWords(current: number | null, delta: number): number | null {
  if (current === null) return null;
  return Math.min(DAILY_WORDS_MAX, Math.max(DAILY_WORDS_MIN, current + delta));
}

/** 기간 프리셋: 시작일 포함 n일이 되도록 목표일을 정한다. */
export function targetForPreset(startDate: string, days: number): string | null {
  if (!Number.isInteger(days) || days < 1) return null;
  return addDays(startDate, days - 1);
}

export function matchingPreset(startDate: string, targetDate: string): number | null {
  const span = inclusiveSpan(startDate, targetDate);
  return span !== null && (DURATION_PRESETS as readonly number[]).includes(span) ? span : null;
}

export function sameDeck(a: PlanDeckRef | null, b: PlanDeckRef | null): boolean {
  return a !== null && b !== null && a.kind === b.kind && a.id === b.id;
}

export function deckKey(ref: PlanDeckRef): string {
  return `${ref.kind}:${ref.id}`;
}

export function sameDraft(a: PlanDraft, b: PlanDraft): boolean {
  return (
    (a.deck === null ? b.deck === null : sameDeck(a.deck, b.deck)) &&
    a.startDate === b.startDate &&
    a.targetDate === b.targetDate &&
    a.dailyWords === b.dailyWords
  );
}

// ---- 계획 계산 ---------------------------------------------------------------

export type PlanComputation = {
  status: PlanStatus;
  dateValid: boolean;
  dailyValid: boolean;
  /** 시작~목표 전체 일수(시작일 포함). 날짜가 틀리면 null. */
  span: number | null;
  /** 계산 기준일 B = max(S, 서울 오늘). 저장 전후 같은 규칙. */
  baseDate: string | null;
  /** B~T 남은 일수 D. */
  daysLeft: number | null;
  /** 확인된 진도. 미확인이면 모두 null (0과 구분). */
  total: number | null;
  seen: number | null;
  remaining: number | null;
  /** 0~1 진도 비율. 빈 덱/미확인은 null. */
  progressRatio: number | null;
  /** 배정 가능량 C = D × Q. 실제 추가 배정이 아니다. */
  capacity: number | null;
  daysNeeded: number | null;
  predictedDate: string | null;
  /** 여유(+)/초과(−) 일수 M = D − L. */
  margin: number | null;
  /** 기간 안에 끝나는 최소 하루량 ceil(R/D). 500 초과면 null. */
  minDaily: number | null;
  /** 남음/계획 두 막대의 공통 축 max(R, C, 1) 기준 비율. */
  remainingBar: number;
  capacityBar: number;
};

export type ComputeInput = {
  draft: PlanDraft;
  progress: PlanProgress;
  today: string;
};

/** 응답이 이 계획 덱의 유효한 진도인지. 0 ≤ V ≤ N 정수가 아니면 숨겨 clamp하지 않고 미확인 처리. */
export function readyProgress(
  progress: PlanProgress,
  deck: PlanDeckRef | null,
): { total: number; seen: number } | null {
  if (progress.state !== "ready" || !sameDeck(progress.deck, deck)) return null;
  const { total, seen } = progress;
  if (!Number.isSafeInteger(total) || !Number.isSafeInteger(seen)) return null;
  if (total < 0 || seen < 0 || seen > total) return null;
  return { total, seen };
}

export function computePlan({ draft, progress, today }: ComputeInput): PlanComputation {
  const span = inclusiveSpan(draft.startDate, draft.targetDate);
  const dateValid = span !== null;
  const q = draft.dailyWords;
  const dailyValid =
    q !== null && Number.isInteger(q) && q >= DAILY_WORDS_MIN && q <= DAILY_WORDS_MAX;

  const known = readyProgress(progress, draft.deck);
  const total = known ? known.total : null;
  const seen = known ? known.seen : null;
  const remaining = known ? known.total - known.seen : null;
  const progressRatio = known && known.total > 0 ? known.seen / known.total : null;

  let baseDate: string | null = null;
  let daysLeft: number | null = null;
  if (dateValid) {
    const s = toDayNumber(draft.startDate) as number;
    const t = toDayNumber(draft.targetDate) as number;
    // 저장 여부와 무관하게 B = max(S, 서울 오늘). 지난 날짜를 남은 기간에
    // 넣지 않아 저장 버튼만으로 예상일이 바뀌지 않는다(Gate C-0 결정 10).
    // 잔량은 현재 total − seen 그대로다(오늘 학습분 보정은 하지 않음).
    const todayDay = toDayNumber(today);
    const b = todayDay !== null ? Math.max(s, todayDay) : s;
    baseDate = fromDayNumber(b);
    daysLeft = t - b + 1;
  }

  const base: PlanComputation = {
    status: "unknown",
    dateValid,
    dailyValid,
    span,
    baseDate,
    daysLeft,
    total,
    seen,
    remaining,
    progressRatio,
    capacity: null,
    daysNeeded: null,
    predictedDate: null,
    margin: null,
    minDaily: null,
    remainingBar: 0,
    capacityBar: 0,
  };

  if (!known) return base;
  if (!dateValid || !dailyValid) return { ...base, status: "invalid" };
  if (known.total === 0) return { ...base, status: "emptyDeck" };

  const d = daysLeft as number;
  if (d <= 0) return { ...base, status: "expired" };

  const r = remaining as number;
  const qq = q as number;
  const capacity = d * qq;
  const axis = Math.max(r, capacity, 1);
  const withBars = {
    ...base,
    capacity,
    remainingBar: r / axis,
    capacityBar: capacity / axis,
  };
  const minDaily = Math.ceil(r / d);
  const minDailyOrNull = minDaily <= DAILY_WORDS_MAX ? minDaily : null;

  if (r === 0) return { ...withBars, status: "allSeen" };
  if (qq === 0) return { ...withBars, status: "paused", minDaily: minDailyOrNull };

  const daysNeeded = Math.ceil(r / qq);
  const predictedDate = addDays(baseDate as string, daysNeeded - 1);
  const margin = d - daysNeeded;
  return {
    ...withBars,
    status: margin < 0 ? "late" : margin === 0 ? "onTime" : "ahead",
    daysNeeded,
    predictedDate,
    margin,
    minDaily: minDailyOrNull,
  };
}
