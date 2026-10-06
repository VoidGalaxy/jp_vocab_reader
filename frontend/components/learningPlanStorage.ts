// 학습 계획 기기 저장 (Gate C-1a). 로그인 계정별로 이 브라우저에 활성 계획
// 하나만 둔다. 서버 동기화가 아니다.
//
// - 키: jp-vocab-reader:learning-plan-v1:<backend-scope>:<user-id>.
//   다른 키(access-token, reading-session-v1, classification-draft)는 읽지도
//   쓰지도 지우지도 않는다.
// - 값: 설정만 저장한다. 진도·원문·토큰·이메일은 넣지 않는다.
// - 읽기 실패(깨진 JSON/버전/필드)는 "corrupt"로 돌려주고 원자료를 지우지
//   않는다. 지우기는 사용자가 명시적으로 요청할 때 그 키 하나만.
// - 쓰기 실패(용량/접근 거부)는 예외를 삼키고 "error"를 돌려준다.
//
// Node 타입 제거 실행으로 테스트하므로 런타임 TS 문법을 쓰지 않는다.

// 타입만 가져온다(Node 타입 제거 실행에서 값 import는 확장자가 필요해
// tsconfig와 충돌한다). 범위·날짜 검증은 learningPlan.ts와 같은 규칙.
import type { PlanDeckRef, PlanDraft } from "./learningPlan";

const DAILY_WORDS_MIN = 0;
const DAILY_WORDS_MAX = 500;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function isRealDate(value: string): boolean {
  if (!ISO_DATE.test(value)) return false;
  const ms = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === value;
}

/** 시작일 ≤ 목표일인 실제 날짜 쌍인지. */
function isValidRange(startDate: string, targetDate: string): boolean {
  return isRealDate(startDate) && isRealDate(targetDate) && startDate <= targetDate;
}

export const LEARNING_PLAN_KEY_PREFIX = "jp-vocab-reader:learning-plan-v1:";
export const LEARNING_PLAN_STORAGE_VERSION = 1;
export const LEARNING_PLAN_METRIC_VERSION = "first-review-v1";

export type StoredPlan = {
  version: 1;
  metricVersion: string;
  deck: PlanDeckRef;
  startDate: string;
  targetDate: string;
  dailyWords: number;
  savedAt: string;
};

export type ReadResult =
  | { kind: "empty" }
  | { kind: "ok"; plan: StoredPlan }
  | { kind: "corrupt" }
  | { kind: "unavailable" };

export type WriteResult = { kind: "ok"; plan: StoredPlan } | { kind: "error" };

type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** API 환경 구분값: 정규화한 origin + base path. 같은 user-id라도 다른 백엔드면 다른 키. */
export function learningPlanStorageScope(apiBaseUrl: string): string {
  let normalized = apiBaseUrl.trim();
  try {
    const url = new URL(normalized);
    const path = url.pathname.replace(/\/+$/, "");
    normalized = `${url.protocol}//${url.host.toLowerCase()}${path}`;
  } catch {
    normalized = normalized.replace(/\/+$/, "").toLowerCase();
  }
  return encodeURIComponent(normalized);
}

export function learningPlanStorageKey(scope: string, userId: number): string {
  return `${LEARNING_PLAN_KEY_PREFIX}${scope}:${userId}`;
}

function isDeckRef(value: unknown): value is PlanDeckRef {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    (v.kind === "personal" || v.kind === "subscribed") &&
    typeof v.id === "number" &&
    Number.isSafeInteger(v.id) &&
    v.id > 0
  );
}

/** 저장 값 검증. 하나라도 어긋나면 null(깨진 데이터). */
export function parseStoredPlan(raw: string | null): StoredPlan | null | "empty" {
  if (raw === null) return "empty";
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object") return null;
  const v = value as Record<string, unknown>;
  if (v.version !== LEARNING_PLAN_STORAGE_VERSION) return null;
  if (typeof v.metricVersion !== "string" || v.metricVersion.length === 0) return null;
  if (!isDeckRef(v.deck)) return null;
  if (typeof v.startDate !== "string" || typeof v.targetDate !== "string") return null;
  if (!isValidRange(v.startDate, v.targetDate)) return null;
  if (
    typeof v.dailyWords !== "number" ||
    !Number.isInteger(v.dailyWords) ||
    v.dailyWords < DAILY_WORDS_MIN ||
    v.dailyWords > DAILY_WORDS_MAX
  ) {
    return null;
  }
  if (typeof v.savedAt !== "string" || !Number.isFinite(Date.parse(v.savedAt))) return null;
  return {
    version: 1,
    metricVersion: v.metricVersion,
    deck: { kind: v.deck.kind, id: v.deck.id },
    startDate: v.startDate,
    targetDate: v.targetDate,
    dailyWords: v.dailyWords,
    savedAt: v.savedAt,
  };
}

export function readStoredPlan(storage: StorageLike | null, key: string): ReadResult {
  if (!storage) return { kind: "unavailable" };
  let raw: string | null;
  try {
    raw = storage.getItem(key);
  } catch {
    return { kind: "unavailable" };
  }
  const parsed = parseStoredPlan(raw);
  if (parsed === "empty") return { kind: "empty" };
  if (parsed === null) return { kind: "corrupt" };
  return { kind: "ok", plan: parsed };
}

/** 저장 가능한 초안인지(덱·날짜·하루량 유효). */
export function toStoredPlan(draft: PlanDraft, now: Date): StoredPlan | null {
  if (!draft.deck || draft.dailyWords === null) return null;
  if (!isValidRange(draft.startDate, draft.targetDate)) return null;
  if (
    !Number.isInteger(draft.dailyWords) ||
    draft.dailyWords < DAILY_WORDS_MIN ||
    draft.dailyWords > DAILY_WORDS_MAX
  ) {
    return null;
  }
  return {
    version: 1,
    metricVersion: LEARNING_PLAN_METRIC_VERSION,
    deck: { kind: draft.deck.kind, id: draft.deck.id },
    startDate: draft.startDate,
    targetDate: draft.targetDate,
    dailyWords: draft.dailyWords,
    savedAt: now.toISOString(),
  };
}

export function writeStoredPlan(
  storage: StorageLike | null,
  key: string,
  draft: PlanDraft,
  now: Date,
): WriteResult {
  const plan = toStoredPlan(draft, now);
  if (!storage || !plan) return { kind: "error" };
  try {
    storage.setItem(key, JSON.stringify(plan));
    return { kind: "ok", plan };
  } catch {
    return { kind: "error" };
  }
}

/** 사용자가 확인한 뒤에만: 이 계획 키 하나만 지운다. */
export function removeStoredPlan(storage: StorageLike | null, key: string): boolean {
  if (!storage) return false;
  try {
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function draftFromStored(plan: StoredPlan): PlanDraft {
  return {
    deck: { kind: plan.deck.kind, id: plan.deck.id },
    startDate: plan.startDate,
    targetDate: plan.targetDate,
    dailyWords: plan.dailyWords,
  };
}
