// FSRS 복습 회차를 실제 화면에 잇는 순수 도우미 (Gate C-2c).
//
// 계약: docs/plans/srs-improvement/gate-c2/CONTRACT.md v0.2 (1-4, 2-1, 2-4, 4-1~4-4, 9-1, 9-3).
// 큐 요청 경로, 모드 판별 결과, 큐 오류 분류, 큐 항목 → 카드 화면 변환, 화면 문구만 둔다.
// 회차 상태 전이는 studySession.ts가 맡는다. React·fetch·저장소를 쓰지 않는다.
//
// Node 타입 제거 실행 때문에 enum·값 import를 쓰지 않는다(타입 import만).

import type { StudyCardItem, StudyMode, TokenStatus } from "./types";
import type { HaltReason, NewGoalDisplay, Notice } from "./studySession";

export const SHARED_DECK_PREFIX = "shared:";
/** 회차 진행 페이지 크기(CONTRACT 2-1). 커서·prefetch는 쓰지 않는다. */
export const SESSION_PAGE_LIMIT = 10;
/** 연습은 한 번에 받아 화면에서 넘긴다(서버 최대). */
export const PRACTICE_PAGE_LIMIT = 100;
/** mode=selected 한도(CONTRACT 9-3). */
export const MAX_SELECTED_IDS = 200;

export type FetchResult =
  | { kind: "ok"; body: unknown }
  | { kind: "http"; status: number; detail: string | null }
  | { kind: "network" };

type Scope =
  | { scope: "all" }
  | { scope: "personal_deck"; deckId: number }
  | { scope: "subscribed_deck"; deckId: number };

export type QueueTarget =
  | (Scope & { kind: "review"; mode: "today" | "new"; planDailyNew: number | null })
  | (Scope & { kind: "practice"; statuses: TokenStatus[] })
  | { kind: "selected"; cardIds: number[] }
  /** recent 묶음 전체를 연습으로 보기: 서버 큐가 아니라 기존 읽기 전용 목록에서 가져온다. */
  | { kind: "recent_practice"; cardIds: number[] };

const PRACTICE_STATUSES: Partial<Record<StudyMode, TokenStatus[]>> = {
  unknown: ["unknown"],
  uncertain: ["uncertain"],
  all: ["unknown", "uncertain"],
};

function scopeFor(deckId: string): Scope | null {
  if (deckId === "all" || deckId === "") return { scope: "all" };
  const shared = deckId.indexOf(SHARED_DECK_PREFIX) === 0;
  const raw = shared ? deckId.slice(SHARED_DECK_PREFIX.length) : deckId;
  if (!/^[1-9][0-9]{0,9}$/.test(raw)) return null;
  const id = Number(raw);
  return shared ? { scope: "subscribed_deck", deckId: id } : { scope: "personal_deck", deckId: id };
}

/**
 * 복습 탭의 덱·모드 선택을 큐 요청 대상으로 바꾼다.
 * - today·new: 실제 복습(계획 하루량은 덱 범위일 때만).
 * - unknown·uncertain·all: 연습(평가 POST 없음, CONTRACT 4-2).
 * - recent: 방금 담은 개인 단어 묶음(mode=selected, CONTRACT 4-3 R2). 덱 선택은 쓰지 않는다.
 */
export function queueTargetFor(
  deckId: string,
  mode: StudyMode,
  options: { recentIds?: readonly number[]; planDailyNew?: number | null } = {},
): QueueTarget | null {
  if (mode === "recent") {
    const ids = uniquePositiveIds(options.recentIds ?? []);
    if (ids.length === 0) return null;
    // 서버 한도를 넘으면 가장 최근에 담은 쪽을 남긴다.
    return { kind: "selected", cardIds: ids.slice(Math.max(0, ids.length - MAX_SELECTED_IDS)) };
  }
  const scope = scopeFor(deckId);
  if (!scope) return null;
  const statuses = PRACTICE_STATUSES[mode];
  if (statuses) return { ...scope, kind: "practice", statuses };
  if (mode !== "today" && mode !== "new") return null;
  const plan = options.planDailyNew;
  const planDailyNew =
    scope.scope !== "all" && typeof plan === "number" && Number.isInteger(plan) && plan >= 0 && plan <= 500
      ? plan
      : null;
  return { ...scope, kind: "review", mode, planDailyNew };
}

function uniquePositiveIds(ids: readonly number[]): number[] {
  const seen: Record<string, true> = {};
  const out: number[] = [];
  for (let i = 0; i < ids.length; i += 1) {
    const id = ids[i];
    if (!Number.isSafeInteger(id) || id <= 0 || seen[String(id)]) continue;
    seen[String(id)] = true;
    out.push(id);
  }
  return out;
}

/** GET /study-queue 경로. 회차 진행은 매번 첫 페이지(커서 없음)다. */
export function queuePath(
  target: QueueTarget,
  excludeParams: ReadonlyArray<readonly [string, string]>,
  options: { limit?: number } = {},
): string {
  const params: Array<[string, string]> = [];
  // 지표 조회(Gate D-1)는 카드가 필요 없어 limit=1로 집계만 받는다.
  const pageLimit = options.limit ?? SESSION_PAGE_LIMIT;
  if (target.kind === "selected" || target.kind === "recent_practice") {
    params.push(["mode", "selected"]);
    for (let i = 0; i < target.cardIds.length; i += 1) params.push(["card_id", String(target.cardIds[i])]);
    params.push(["limit", String(pageLimit)]);
  } else {
    params.push(["scope", target.scope]);
    if (target.scope !== "all") params.push(["deck_id", String(target.deckId)]);
    if (target.kind === "practice") {
      params.push(["mode", "practice"]);
      for (let i = 0; i < target.statuses.length; i += 1) params.push(["status", target.statuses[i]]);
      params.push(["limit", String(PRACTICE_PAGE_LIMIT)]);
    } else {
      params.push(["mode", target.mode]);
      params.push(["limit", String(pageLimit)]);
      if (target.planDailyNew !== null) params.push(["plan_daily_new", String(target.planDailyNew)]);
    }
  }
  for (let i = 0; i < excludeParams.length; i += 1) params.push([excludeParams[i][0], excludeParams[i][1]]);
  return `/study-queue?${params.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&")}`;
}

/** 모드 판별 요청(CONTRACT 4-1). */
export const MODE_PROBE_PATH = "/study-queue?limit=1";

/** 409 srs_mode_not_fsrs만 legacy. 200은 FSRS. 그 밖은 오류(legacy로 바꾸지 않는다). */
export function probeOutcome(result: FetchResult): "fsrs" | "legacy" | "error" {
  if (result.kind === "ok") return "fsrs";
  if (result.kind === "http" && result.status === 409 && result.detail === "srs_mode_not_fsrs") return "legacy";
  return "error";
}

/** 큐 조회 오류의 처리: 회차 정지 또는 조회 실패(다시 불러오기). */
export function queueFailureKind(result: FetchResult): { halt: HaltReason } | { failure: true } {
  if (result.kind === "http") {
    if (result.status === 409 && result.detail === "srs_mode_not_fsrs") return { halt: "mode_changed" };
    if (result.status === 401) return { halt: "auth" };
    // 방어용(CONTRACT 9-1): 클라이언트는 100개를 넘겨 보내지 않는다.
    if (result.status === 400 && result.detail === "too_many_excluded_cards") return { halt: "deferred_limit" };
  }
  return { failure: true };
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const TOKEN_STATUSES: TokenStatus[] = ["unclassified", "known", "uncertain", "unknown"];

/**
 * 큐 항목의 표시 내용 → 복습 책 지면이 그리는 카드 모양. 형식이 틀리면 null.
 * 평가 정체성(종류·id·버전·경로)은 studySession의 QueueCard가 따로 가진다.
 */
export function studyCardFromQueueItem(raw: unknown): StudyCardItem | null {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return null;
  const item = raw as Record<string, unknown>;
  const kind = item.card_kind;
  const id = item.card_id;
  if ((kind !== "personal" && kind !== "lexeme") || typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0) {
    return null;
  }
  const content = item.content;
  if (typeof content !== "object" || content === null) return null;
  const c = content as Record<string, unknown>;
  const review = (typeof item.review === "object" && item.review !== null ? item.review : {}) as Record<string, unknown>;
  const sharedDeckId = typeof review.shared_deck_id === "number" ? review.shared_deck_id : null;
  const status = TOKEN_STATUSES.indexOf(item.status as TokenStatus) !== -1 ? (item.status as TokenStatus) : "unclassified";
  const sourceLabel = asText(item.source_label) || (kind === "personal" ? "내 단어장" : "가져온 덱");
  const surface = asText(c.surface);
  return {
    id: kind === "personal" ? id : -id,
    deck_id: kind === "personal" ? 0 : sharedDeckId ?? 0,
    deck_name: sourceLabel,
    surface,
    base_form: asText(c.base_form),
    reading: asText(c.reading),
    part_of_speech: asText(c.part_of_speech),
    normalized_form: asText(c.base_form) || surface,
    meaning_ko: asText(c.meaning_ko),
    dictionary_gloss: asText(c.dictionary_gloss),
    quality_tag: "normal",
    example_sentence: asText(c.example_sentence),
    is_custom_term: false,
    occurrence_count: 1,
    jlpt_level: typeof c.jlpt_level === "string" ? c.jlpt_level : null,
    status,
    context_explanation_ko: asText(c.context_explanation_ko),
    correct_count: 0,
    wrong_count: 0,
    last_reviewed_at: null,
    review_level: 0,
    next_review_at: null,
    created_at: "",
    updated_at: "",
    item_type: kind === "personal" ? "vocab" : "lexeme",
    vocab_item_id: kind === "personal" ? id : null,
    lexeme_id: kind === "lexeme" ? id : null,
    shared_deck_id: kind === "lexeme" ? sharedDeckId : null,
    source_label: sourceLabel,
  };
}

/** 큐 응답의 미래 대기 수(recent 묶음의 "남은 단어 연습하기" 안내용). 없거나 틀리면 0. */
export function pendingLaterCount(raw: unknown): number {
  if (typeof raw !== "object" || raw === null) return 0;
  const counts = (raw as Record<string, unknown>).counts;
  if (typeof counts !== "object" || counts === null) return 0;
  const value = (counts as Record<string, unknown>).pending_later;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : 0;
}

/** 신규 목표 줄(CONTRACT 4-4). 확인 불가를 0으로 쓰지 않고, 계정/학습 계획 기준을 밝힌다. */
export function newGoalLine(display: NewGoalDisplay | null): string | null {
  if (!display) return null;
  const basis = display.basis === "plan" ? "학습 계획 기준" : "계정 기준";
  if (display.kind === "unknown") {
    return `오늘 새 단어: 확인할 수 없음 (적어도 ${display.atLeast}개) · 목표 ${display.goal}개 · ${basis}`;
  }
  return `오늘 새 단어 ${display.introduced}개 / 목표 ${display.goal}개 · ${basis}`;
}

/** 목표 달성 문구에 쓸 목표 수. 확인 불가면 null. */
export function goalReachedText(display: NewGoalDisplay | null): string {
  if (display && display.kind === "exact") {
    const basis = display.basis === "plan" ? "학습 계획의 " : "";
    return `오늘 ${basis}새 단어 목표 ${display.goal}개를 채웠어요`;
  }
  return "오늘 새 단어 목표를 채웠어요";
}

export function haltText(reason: HaltReason): string {
  switch (reason) {
    case "deferred_limit":
      return "이번 회차에서 미룬 단어가 많아 여기서 회차를 마칠게요";
    case "mode_changed":
      return "복습 방식이 바뀌어 회차를 멈췄어요. 다시 확인할게요.";
    case "upgrade_required":
      return "앱이 새 버전으로 바뀌었어요. 페이지를 새로고침한 뒤 다시 시작해 주세요.";
    case "auth":
      return "로그인이 만료되었어요. 다시 로그인한 뒤 시작해 주세요.";
    case "request_id_conflict":
    case "unexpected":
      return "평가를 처리하지 못해 이번 회차를 멈췄어요. 회차를 마친 뒤 다시 시작해 주세요.";
  }
}

export function noticeText(notice: Notice): string {
  switch (notice) {
    case "conflict":
      return "다른 창이나 기기에서 먼저 평가한 카드예요. 최신 상태로 다시 불러왔어요.";
    case "unavailable":
      return "지금은 평가할 수 없는 카드라 다음 카드로 넘어갔어요.";
    case "not_found":
      return "카드를 찾을 수 없어 다음 카드로 넘어갔어요.";
    default:
      return "";
  }
}

/** 서버 시각 기준 HH:MM (서울). */
export function formatSeoulTime(iso: string | null): string {
  if (!iso) return "";
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return "";
  const seoul = new Date(ms + 9 * 60 * 60 * 1000);
  const hh = String(seoul.getUTCHours()).padStart(2, "0");
  const mm = String(seoul.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}
