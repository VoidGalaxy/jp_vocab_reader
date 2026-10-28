// FSRS 복습 회차의 순수 상태 모듈 (Gate C-2b).
//
// 계약: docs/plans/srs-improvement/gate-c2/CONTRACT.md v0.2 (1-2~1-6, 2-1~2-4, 4-4, 9-1).
// 이 파일은 React·DOM·fetch·저장소·시계를 직접 쓰지 않는다. 시각·ID·응답·이벤트는
// 모두 호출하는 쪽이 인자로 넘긴다. 아직 page.tsx·StudySection에 연결하지 않았다
// (C-2c에서 page.tsx·useFsrsStudy가 연결). 이 모듈의 테스트 통과만으로 실제 앱 화면이
// 보호된다는 뜻은 아니다.
//
// Node 타입 제거 실행 때문에 enum·값 import를 쓰지 않는다.

export type CardKind = "personal" | "lexeme";
export type Rating = "again" | "hard" | "good" | "easy";
export type SrsPhase = "learning" | "review" | "relearning";

export type QueueCard = {
  kind: CardKind;
  id: number;
  /** null: 진도 행이 없는 구독 단어. 평가 때 명시적 null을 보낸다. */
  version: number | null;
  sharedDeckId: number | null;
  reviewPath: string | null;
  practiceOnly: boolean;
  isNew: boolean;
};

export type NewGoalInfo = {
  status: "exact" | "unknown";
  /** exact일 때만 숫자. unknown이면 null이며 0으로 바꾸지 않는다. */
  introducedToday: number | null;
  introducedAtLeast: number;
  accountRemaining: number | null;
  /** 이 요청에 계획 하루량이 없으면 null(계획 목표 미적용). */
  planDailyNew: number | null;
  introducedInScope: number | null;
  introducedInScopeStatus: "exact" | "unknown" | null;
  introducedInScopeAtLeast: number | null;
  planRemaining: number | null;
  blockedReason: string | null;
  dailyGoal: number;
};

export type QueueSnapshot = {
  items: QueueCard[];
  newAvailable: number;
  newUnmaterialized: number;
  excludedByRequest: number;
  notMigrated: number;
  nextDueAt: string | null;
  serverNow: string;
  seoulDate: string;
  newGoal: NewGoalInfo;
};

export type ReviewPayload = {
  rating: Rating;
  request_id: string;
  session_id: string;
  /** 정수 또는 명시적 null(구독 최초 평가). 재시도 때 그대로 보낸다. */
  expected_card_version: number | null;
  response_time_ms?: number | null;
};

export type Attempt = {
  readonly accountEpoch: number;
  readonly sessionId: string;
  readonly card: { readonly kind: CardKind; readonly id: number; readonly sharedDeckId: number | null };
  readonly requestId: string;
  readonly path: string;
  readonly payload: Readonly<ReviewPayload>;
};

export type AttemptStatus = "sending" | "unknown";

export type HaltReason =
  | "request_id_conflict"
  | "mode_changed"
  | "upgrade_required"
  | "auth"
  | "unexpected"
  | "deferred_limit";

export type Notice =
  | "conflict"
  | "unavailable"
  | "not_found"
  | null;

export type RatingCounts = Record<Rating, number>;

export type StudySession = {
  readonly accountEpoch: number;
  readonly sessionId: string;
  readonly status: "active" | "ended";
  readonly current: QueueCard | null;
  readonly attempt: Attempt | null;
  readonly attemptStatus: AttemptStatus | null;
  readonly autoRetriesUsed: number;
  readonly queue: QueueSnapshot | null;
  readonly queueError: boolean;
  /** 마지막으로 시작한 큐 조회 순번. 이보다 앞선 조회의 응답은 버린다. */
  readonly queueSeq: number;
  /** 최신 조회의 결과가 아직 오지 않았다. 이 동안 빈 큐를 "복습 끝"으로 보이지 않는다. */
  readonly queuePending: boolean;
  /**
   * 카드 출제 차례 번호. 비어 있던 자리에 카드가 새로 놓일 때마다 1 오른다. 같은 카드가
   * 다시 나와도(Again 뒤 재등장) 새 차례이므로 질문부터 시작한다. 같은 시도의 재시도는
   * 카드를 바꾸지 않으므로 차례도 그대로다.
   */
  readonly presentation: number;
  readonly halted: HaltReason | null;
  readonly notice: Notice;
  readonly ratings: RatingCounts;
  readonly reviewed: number;
  readonly firstReviewsThisSession: number;
  /** "kind:id" → 이번 회차에서 결과가 학습·재학습 단계로 남은 성공 평가 수 */
  readonly shortStepCounts: Readonly<Record<string, number>>;
  /** 이번 회차에서 미룬 카드 키 ("kind:id"), 최대 MAX_EXCLUDED */
  readonly excluded: readonly string[];
  /** 이미 반영한 성공 응답의 request_id (중복 반영 방지) */
  readonly acceptedRequestIds: readonly string[];
};

export const MAX_EXCLUDED = 100;
export const DEFER_AFTER_SHORT_STEP_RESULTS = 3;
export const MAX_AUTO_RETRIES = 1;
export const SOON_WINDOW_MS = 15 * 60 * 1000;
const SERVER_ID = /^[A-Za-z0-9_.:-]{1,128}$/;

export function cardKey(card: { kind: CardKind; id: number }): string {
  return `${card.kind}:${card.id}`;
}

function emptyRatings(): RatingCounts {
  return { again: 0, hard: 0, good: 0, easy: 0 };
}

/** 회차 시작·교체·초기화마다 새로 만든다. sessionId는 호출하는 쪽이 만든다. */
export function startSession(accountEpoch: number, sessionId: string): StudySession {
  if (!SERVER_ID.test(sessionId)) {
    throw new Error("sessionId must match the server id syntax");
  }
  return {
    accountEpoch,
    sessionId,
    status: "active",
    current: null,
    attempt: null,
    attemptStatus: null,
    autoRetriesUsed: 0,
    queue: null,
    queueError: false,
    queueSeq: 0,
    queuePending: false,
    presentation: 0,
    halted: null,
    notice: null,
    ratings: emptyRatings(),
    reviewed: 0,
    firstReviewsThisSession: 0,
    shortStepCounts: {},
    excluded: [],
    acceptedRequestIds: [],
  };
}

export function endSession(session: StudySession): StudySession {
  return { ...session, status: "ended", current: null };
}

/** 활성 회차: 시작 뒤 마치기 전까지. 대기·미룸·결과 미확정 화면도 포함한다. */
export function isActiveSession(session: StudySession | null): boolean {
  return session !== null && session.status === "active";
}

export function isSubmitting(session: StudySession): boolean {
  return session.attempt !== null && session.attemptStatus === "sending";
}

// ---- 큐 응답 -----------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isPositiveId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

class ParseFailure extends Error {}

function fail(): never {
  throw new ParseFailure("invalid queue response");
}

/** 없으면 fallback, 있으면 0 이상 정수여야 한다. */
function optionalCount(source: Record<string, unknown>, name: string, fallback: number): number {
  if (!(name in source) || source[name] === undefined) return fallback;
  const value = source[name];
  if (!isCount(value)) fail();
  return value;
}

/** 키가 있어야 하고, 0 이상 정수 또는 null이어야 한다. */
function countOrNull(source: Record<string, unknown>, name: string): number | null {
  const value = source[name];
  if (value === null || value === undefined) return null;
  if (!isCount(value)) fail();
  return value;
}

function parseCard(entry: unknown): QueueCard {
  if (!isRecord(entry)) fail();
  const kind = entry.card_kind;
  if (kind !== "personal" && kind !== "lexeme") fail();
  if (!isPositiveId(entry.card_id)) fail();
  // 버전: 0 이상 정수, 또는 미생성 구독 카드의 명시적 null만 허용한다.
  // 잘못된 값을 null로 바꾸면 구독 최초 평가로 오인되므로 해석 실패로 돌려준다.
  if (!("card_version" in entry)) fail();
  const rawVersion = entry.card_version;
  let version: number | null;
  if (rawVersion === null) {
    if (kind !== "lexeme" || entry.materialized !== false) fail();
    version = null;
  } else if (isCount(rawVersion)) {
    if (entry.materialized === false) fail();
    version = rawVersion;
  } else {
    fail();
  }
  const practiceOnly = entry.practice_only === true;
  if ("practice_only" in entry && typeof entry.practice_only !== "boolean") fail();
  const review = entry.review;
  let reviewPath: string | null = null;
  let sharedDeckId: number | null = null;
  if (review === null || review === undefined) {
    if (!practiceOnly) fail();
  } else {
    if (!isRecord(review) || typeof review.path !== "string" || review.path.charAt(0) !== "/") fail();
    reviewPath = review.path;
    if (kind === "lexeme") {
      if (!isPositiveId(review.shared_deck_id)) fail();
      sharedDeckId = review.shared_deck_id;
    } else if (review.shared_deck_id !== null && review.shared_deck_id !== undefined) {
      fail();
    }
  }
  if ("is_new" in entry && typeof entry.is_new !== "boolean") fail();
  return { kind, id: entry.card_id, version, sharedDeckId, reviewPath, practiceOnly, isNew: entry.is_new === true };
}

function parseStatus(value: unknown, allowNull: boolean): "exact" | "unknown" | null {
  if (value === "exact" || value === "unknown") return value;
  if (allowNull && (value === null || value === undefined)) return null;
  return fail();
}

function parseGoal(goal: unknown): NewGoalInfo {
  if (!isRecord(goal)) fail();
  const status = parseStatus(goal.introduced_today_status, false) as "exact" | "unknown";
  const introducedToday = countOrNull(goal, "introduced_today");
  // exact이면 숫자, unknown이면 null. 서로 어긋나면 해석 실패(0으로 메우지 않는다).
  if ((status === "exact") !== (introducedToday !== null)) fail();
  const planDailyNew = countOrNull(goal, "plan_daily_new");
  const scopeStatus = parseStatus(goal.introduced_today_in_scope_status, true);
  const introducedInScope = countOrNull(goal, "introduced_today_in_scope");
  if (scopeStatus === "exact" && introducedInScope === null) fail();
  if (scopeStatus !== "exact" && introducedInScope !== null) fail();
  if (typeof goal.new_blocked_reason !== "string" && goal.new_blocked_reason !== null
      && goal.new_blocked_reason !== undefined) fail();
  const dailyGoal = goal.account_daily_goal;
  if (!isCount(dailyGoal)) fail();
  return {
    status,
    introducedToday,
    introducedAtLeast: optionalCount(goal, "introduced_today_at_least", introducedToday ?? 0),
    accountRemaining: countOrNull(goal, "account_remaining"),
    planDailyNew,
    introducedInScope,
    introducedInScopeStatus: scopeStatus,
    introducedInScopeAtLeast: countOrNull(goal, "introduced_today_in_scope_at_least"),
    planRemaining: countOrNull(goal, "plan_remaining"),
    blockedReason: typeof goal.new_blocked_reason === "string" ? goal.new_blocked_reason : null,
    dailyGoal,
  };
}

/** GET /study-queue 응답에서 이 모듈이 쓰는 값만 꺼낸다. 형식이 하나라도 틀리면 예외 없이 null. */
export function parseQueueResponse(raw: unknown): QueueSnapshot | null {
  try {
    if (!isRecord(raw)) return null;
    const counts = raw.counts;
    if (!Array.isArray(raw.items) || !isRecord(counts)) return null;
    if (typeof raw.server_now !== "string" || typeof raw.seoul_date !== "string") return null;
    if (raw.next_due_at !== null && raw.next_due_at !== undefined && typeof raw.next_due_at !== "string") return null;
    const items = (raw.items as unknown[]).map(parseCard);
    return {
      items,
      newAvailable: optionalCount(counts, "new_available", 0),
      newUnmaterialized: optionalCount(counts, "new_unmaterialized", 0),
      excludedByRequest: optionalCount(counts, "excluded_by_request", 0),
      notMigrated:
        optionalCount(counts, "not_converted", 0) + optionalCount(counts, "blocked_history", 0)
        + optionalCount(counts, "invalid_state", 0) + optionalCount(counts, "unsupported_config", 0),
      nextDueAt: typeof raw.next_due_at === "string" ? raw.next_due_at : null,
      serverNow: raw.server_now,
      seoulDate: raw.seoul_date,
      newGoal: parseGoal(raw.new_goal),
    };
  } catch (error) {
    if (error instanceof ParseFailure) return null;
    throw error;
  }
}

/** 다음 큐 조회에 붙일 매개변수. 회차 진행은 커서를 쓰지 않는다. */
export function queueRequestParams(session: StudySession): Array<[string, string]> {
  return session.excluded.map((key) => ["exclude_card", key] as [string, string]);
}

export type QueueTicket = { readonly accountEpoch: number; readonly sessionId: string; readonly seq: number };

/**
 * 큐 조회를 시작할 때 부른다. 이 티켓의 조회만 결과를 반영할 수 있다.
 * 새 조회를 시작하거나 평가가 확정되면 순번이 올라가 이전 조회의 성공·실패는 무효가 된다.
 */
export function beginQueueFetch(session: StudySession): { session: StudySession; ticket: QueueTicket } {
  const seq = session.queueSeq + 1;
  return {
    session: { ...session, queueSeq: seq, queuePending: true },
    ticket: Object.freeze({ accountEpoch: session.accountEpoch, sessionId: session.sessionId, seq }),
  };
}

function isLatestFetch(session: StudySession, ticket: QueueTicket): boolean {
  return session.accountEpoch === ticket.accountEpoch
    && session.sessionId === ticket.sessionId
    && session.queueSeq === ticket.seq;
}

/**
 * 큐 조회 결과 반영. 계정·회차가 다르거나, 이 조회 뒤에 새 조회·평가 확정이 있었으면 버린다.
 * 카드가 표시 중이면 그 카드를 바꾸지 않고 집계만 갱신한다.
 */
export function applyQueue(
  session: StudySession,
  snapshot: QueueSnapshot,
  ticket: QueueTicket,
): StudySession {
  if (!isLatestFetch(session, ticket)) return session;
  if (session.status !== "active" || session.halted) return { ...session, queuePending: false };
  if (session.current) {
    return { ...session, queue: snapshot, queueError: false, queuePending: false };
  }
  const excluded = session.excluded;
  const next = snapshot.items.find((item) => excluded.indexOf(cardKey(item)) === -1) ?? null;
  return {
    ...session,
    queue: snapshot,
    queueError: false,
    queuePending: false,
    current: next,
    presentation: next ? session.presentation + 1 : session.presentation,
  };
}

/**
 * 지금 보이는 카드의 출제 차례 식별자(정답 공개·응답 시간 기준은 이 값에 묶는다).
 * 카드가 없으면 null.
 */
export function presentationKey(session: StudySession | null): string | null {
  if (!session || !session.current) return null;
  return `${session.sessionId}#${session.presentation}#${cardKey(session.current)}`;
}

export function applyQueueFailure(session: StudySession, ticket: QueueTicket): StudySession {
  if (!isLatestFetch(session, ticket)) return session;
  // 실패를 "할 카드 없음"으로 바꾸지 않는다. 현재 카드와 이전 큐는 그대로 둔다.
  return { ...session, queueError: true, queuePending: false };
}

/**
 * 큐 조회가 회차를 멈춰야 하는 오류로 끝났을 때(모드 변경 409, 401, 제외 한도 400).
 * 최신 조회일 때만 반영한다.
 */
export function applyQueueHalt(session: StudySession, ticket: QueueTicket, reason: HaltReason): StudySession {
  if (!isLatestFetch(session, ticket)) return session;
  if (session.status !== "active") return { ...session, queuePending: false };
  return { ...session, halted: session.halted ?? reason, queuePending: false };
}

// ---- 평가 시도 -----------------------------------------------------------------

export type BeginResult =
  | { ok: true; session: StudySession; attempt: Attempt }
  | { ok: false; reason: "no_card" | "busy" | "practice" | "inactive" | "invalid_id" | "invalid_card" };

/** 버튼을 누른 순간 한 번 호출한다. 결과 시도 객체를 그대로 보내고 재시도한다. */
export function beginAttempt(
  session: StudySession,
  input: { rating: Rating; requestId: string; responseTimeMs?: number | null },
): BeginResult {
  if (session.status !== "active" || session.halted) return { ok: false, reason: "inactive" };
  if (session.attempt) return { ok: false, reason: "busy" };
  const card = session.current;
  if (!card) return { ok: false, reason: "no_card" };
  if (card.practiceOnly || !card.reviewPath) return { ok: false, reason: "practice" };
  if (!SERVER_ID.test(input.requestId)) return { ok: false, reason: "invalid_id" };
  if (card.kind === "personal" && card.version === null) return { ok: false, reason: "invalid_card" };
  const payload: ReviewPayload = {
    rating: input.rating,
    request_id: input.requestId,
    session_id: session.sessionId,
    expected_card_version: card.version,
  };
  if (card.kind === "personal") payload.response_time_ms = input.responseTimeMs ?? null;
  const attempt: Attempt = Object.freeze({
    accountEpoch: session.accountEpoch,
    sessionId: session.sessionId,
    card: Object.freeze({ kind: card.kind, id: card.id, sharedDeckId: card.sharedDeckId }),
    requestId: input.requestId,
    path: card.reviewPath,
    payload: Object.freeze(payload),
  });
  return {
    ok: true,
    attempt,
    session: { ...session, attempt, attemptStatus: "sending", autoRetriesUsed: 0, notice: null },
  };
}

export type ReviewOutcome =
  | { type: "success"; body: unknown }
  | { type: "http"; status: number; detail: string | null }
  | { type: "network" };

export type ResolveEffect =
  | "ignored"
  | "refetch"
  | "auto_retry"
  | "show_retry"
  | "halt";

/** 결과 적용 4조건 (CONTRACT 1-3). */
export function isAttemptCurrent(session: StudySession, attempt: Attempt, now: { accountEpoch: number; sessionId: string }): boolean {
  return (
    attempt.accountEpoch === now.accountEpoch
    && attempt.sessionId === now.sessionId
    && session.accountEpoch === now.accountEpoch
    && session.sessionId === now.sessionId
    && session.attempt === attempt
    && session.current !== null
    && session.current.kind === attempt.card.kind
    && session.current.id === attempt.card.id
  );
}

const UNAVAILABLE_DETAILS = [
  "card_paused",
  "invalid_engine_state",
  "review_history_unreadable",
  "history_initialization_requires_approval",
  "unsupported_config_version",
  // Gate D-2: 카드 식별 불가로 격리됨. 다시 평가하지 않고 큐를 다시 받는다(그 카드는 큐에서 빠져 있다).
  "card_identity_unknown",
];

function successPhase(body: unknown): SrsPhase | null {
  const srs = body && typeof body === "object" ? (body as Record<string, unknown>).srs : null;
  const state = srs && typeof srs === "object" ? (srs as Record<string, unknown>).state : null;
  const phase = state && typeof state === "object" ? (state as Record<string, unknown>).phase : null;
  return phase === "learning" || phase === "review" || phase === "relearning" ? phase : null;
}

/**
 * 응답·오류를 반영한다. `now`는 응답을 받은 순간의 계정 epoch·회차 sessionId다.
 * 지금 회차의 진행 중 시도가 아니면 아무것도 바꾸지 않는다("ignored").
 */
export function resolveAttempt(
  session: StudySession,
  attempt: Attempt,
  outcome: ReviewOutcome,
  now: { accountEpoch: number; sessionId: string },
): { session: StudySession; effect: ResolveEffect } {
  if (!isAttemptCurrent(session, attempt, now)) return { session, effect: "ignored" };

  if (outcome.type === "success") {
    if (session.acceptedRequestIds.indexOf(attempt.requestId) !== -1) {
      return { session, effect: "ignored" };
    }
    const key = cardKey(attempt.card);
    const phase = successPhase(outcome.body);
    const ratings = { ...session.ratings, [attempt.payload.rating]: session.ratings[attempt.payload.rating] + 1 };
    let shortStepCounts = session.shortStepCounts;
    let excluded = session.excluded;
    let halted: HaltReason | null = null;
    if (phase === "learning" || phase === "relearning") {
      const count = (shortStepCounts[key] ?? 0) + 1;
      shortStepCounts = { ...shortStepCounts, [key]: count };
      if (count >= DEFER_AFTER_SHORT_STEP_RESULTS && excluded.indexOf(key) === -1) {
        if (excluded.length >= MAX_EXCLUDED) {
          halted = "deferred_limit"; // 기존 항목을 버리지 않는다. 회차를 멈춘다.
        } else {
          excluded = excluded.concat([key]);
        }
      }
    }
    const next: StudySession = {
      ...session,
      queueSeq: session.queueSeq + 1, // 평가 확정: 그 전에 시작한 조회는 무효
      queuePending: false,
      attempt: null,
      attemptStatus: null,
      autoRetriesUsed: 0,
      current: null,
      ratings,
      reviewed: session.reviewed + 1,
      firstReviewsThisSession: session.firstReviewsThisSession + (session.current?.isNew ? 1 : 0),
      shortStepCounts,
      excluded,
      halted,
      acceptedRequestIds: session.acceptedRequestIds.concat([attempt.requestId]),
      notice: null,
    };
    return { session: next, effect: halted ? "halt" : "refetch" };
  }

  if (outcome.type === "network" || (outcome.type === "http" && outcome.status >= 500)) {
    const canAuto = session.autoRetriesUsed < MAX_AUTO_RETRIES;
    return {
      session: { ...session, attemptStatus: "unknown" },
      effect: canAuto ? "auto_retry" : "show_retry",
    };
  }

  const { status, detail } = outcome;
  // 평가가 확정된 결과(충돌·거절 포함)도 그 전에 시작한 조회를 무효로 만든다.
  const cleared = {
    ...session, attempt: null, attemptStatus: null as AttemptStatus | null, autoRetriesUsed: 0,
    queueSeq: session.queueSeq + 1, queuePending: false,
  };
  if (status === 409 && detail === "card_version_conflict") {
    // 자동 재평가하지 않는다. 큐를 다시 받아 서버 상태를 따른다.
    return { session: { ...cleared, current: null, notice: "conflict" }, effect: "refetch" };
  }
  if (status === 409 && detail === "request_id_conflict") {
    return { session: { ...cleared, halted: "request_id_conflict" }, effect: "halt" };
  }
  if (status === 409 && detail === "srs_mode_not_fsrs") {
    return { session: { ...cleared, halted: "mode_changed" }, effect: "halt" };
  }
  if (status === 409 && detail !== null && UNAVAILABLE_DETAILS.indexOf(detail) !== -1) {
    return { session: { ...cleared, current: null, notice: "unavailable" }, effect: "refetch" };
  }
  if (status === 404) {
    return { session: { ...cleared, current: null, notice: "not_found" }, effect: "refetch" };
  }
  if (status === 422) {
    return { session: { ...cleared, halted: "upgrade_required" }, effect: "halt" };
  }
  if (status === 401) {
    return { session: { ...cleared, halted: "auth" }, effect: "halt" };
  }
  return { session: { ...cleared, halted: "unexpected" }, effect: "halt" };
}

/**
 * 결과 미확정 시도를 다시 보낸다. 반환한 시도는 처음 객체 그대로다(같은 request_id·payload).
 * auto=true는 자동 재시도(최대 MAX_AUTO_RETRIES회).
 */
export function retryAttempt(
  session: StudySession,
  attempt: Attempt,
  now: { accountEpoch: number; sessionId: string },
  auto: boolean,
): { ok: true; session: StudySession; attempt: Attempt } | { ok: false } {
  if (!isAttemptCurrent(session, attempt, now) || session.attemptStatus !== "unknown") return { ok: false };
  if (auto && session.autoRetriesUsed >= MAX_AUTO_RETRIES) return { ok: false };
  return {
    ok: true,
    attempt,
    session: {
      ...session,
      attemptStatus: "sending",
      autoRetriesUsed: session.autoRetriesUsed + (auto ? 1 : 0),
    },
  };
}

// ---- 교체·이동 보호 ---------------------------------------------------------------

/** 회차를 바꾸거나 다른 계획을 시작하려 할 때 (CONTRACT 1-5, 1-6). */
export function replaceGuard(session: StudySession | null): "free" | "confirm" | "confirm_unsaved" | "wait" {
  if (!isActiveSession(session)) return "free";
  const active = session as StudySession;
  if (active.attempt && active.attemptStatus === "sending") return "wait";
  if (active.attempt && active.attemptStatus === "unknown") return "confirm_unsaved";
  return "confirm";
}

/** beforeunload를 등록할지. 전달·저장 보장 수단이 아니다. */
export function shouldWarnBeforeUnload(session: StudySession | null): boolean {
  return session !== null && session.attempt !== null;
}

// ---- 화면 상태 -----------------------------------------------------------------

export type PrimaryState =
  | "error"
  | "card"
  | "soon"
  | "deferred_only"
  | "deferred_limit"
  | "new_unknown"
  | "goal_reached"
  | "done"
  | "loading"
  | "ended";

export type SessionView = {
  primary: PrimaryState;
  card: QueueCard | null;
  nextDueAt: string | null;
  notMigratedNote: boolean;
  newGoal: NewGoalDisplay | null;
};

export type NewGoalDisplay =
  | { kind: "exact"; basis: "account" | "plan"; introduced: number; goal: number; remaining: number }
  | { kind: "unknown"; basis: "account" | "plan"; atLeast: number; goal: number };

/**
 * 실제 신규 허용 잔여: 계정 잔여와 (계획이 있으면) 계획 잔여 중 작은 값.
 * 둘 중 하나라도 확인 불가면 null(=확인 불가). 0으로 바꾸지 않는다.
 */
export function effectiveNewRemaining(goal: NewGoalInfo): number | null {
  if (goal.status === "unknown" || goal.accountRemaining === null) return null;
  if (goal.planDailyNew === null) return goal.accountRemaining;
  if (goal.introducedInScopeStatus !== "exact" || goal.planRemaining === null) return null;
  return Math.min(goal.accountRemaining, goal.planRemaining);
}

/**
 * 표시용 목표. 실제로 신규를 막는 쪽(잔여가 작은 쪽, 같으면 계정)을 기준으로
 * 목표·실적·잔여를 같은 기준에서 함께 보여 준다. null·unknown은 0으로 바꾸지 않는다.
 */
export function newGoalDisplay(goal: NewGoalInfo | null): NewGoalDisplay | null {
  if (!goal) return null;
  if (goal.status === "unknown" || goal.introducedToday === null || goal.accountRemaining === null) {
    return { kind: "unknown", basis: "account", atLeast: goal.introducedAtLeast, goal: goal.dailyGoal };
  }
  if (goal.planDailyNew !== null) {
    if (goal.introducedInScopeStatus !== "exact" || goal.introducedInScope === null || goal.planRemaining === null) {
      return { kind: "unknown", basis: "plan", atLeast: goal.introducedInScopeAtLeast ?? 0, goal: goal.planDailyNew };
    }
    if (goal.planRemaining < goal.accountRemaining) {
      return { kind: "exact", basis: "plan", introduced: goal.introducedInScope, goal: goal.planDailyNew,
        remaining: goal.planRemaining };
    }
  }
  return { kind: "exact", basis: "account", introduced: goal.introducedToday, goal: goal.dailyGoal,
    remaining: goal.accountRemaining };
}

/** 주 상태 우선순위 (CONTRACT 2-4, 9-1). nowMs는 서버 시각 기준으로 보정된 현재 시각. */
export function sessionView(session: StudySession, nowMs: number): SessionView {
  const queue = session.queue;
  const base = {
    card: null as QueueCard | null,
    nextDueAt: queue ? queue.nextDueAt : null,
    notMigratedNote: queue ? queue.notMigrated > 0 : false,
    newGoal: newGoalDisplay(queue ? queue.newGoal : null),
  };
  if (session.status === "ended") return { ...base, primary: "ended" };
  if (session.halted === "deferred_limit") return { ...base, primary: "deferred_limit" };
  if (session.halted) return { ...base, primary: "error" };
  // 조회 실패라도 보고 있던 카드는 그대로 보여 준다.
  if (session.current) return { ...base, primary: "card", card: session.current };
  // 다음 카드를 받는 중에는 이전 큐로 "복습 끝"·대기를 판정하지 않는다.
  if (session.queuePending) return { ...base, primary: "loading" };
  if (session.queueError) return { ...base, primary: "error" };
  if (!queue) return { ...base, primary: "loading" };
  if (queue.nextDueAt !== null) {
    const due = Date.parse(queue.nextDueAt);
    if (Number.isFinite(due) && due - nowMs <= SOON_WINDOW_MS) return { ...base, primary: "soon" };
  }
  // 남은 출제 후보가 이번 회차에서 미룬 카드뿐: 무한 대기·"학습 완료" 대신 이 상태.
  if (queue.excludedByRequest > 0) return { ...base, primary: "deferred_only" };
  if (queue.newGoal.blockedReason === "review_time_unreadable") return { ...base, primary: "new_unknown" };
  const newCandidates = queue.newAvailable + queue.newUnmaterialized;
  // 계정·계획 중 하나라도 잔여 0이면 목표 달성(실제 허용량 = 둘 중 작은 값).
  if (newCandidates > 0 && effectiveNewRemaining(queue.newGoal) === 0) return { ...base, primary: "goal_reached" };
  return { ...base, primary: "done" };
}

// ---- 타이머·앱 복귀 ---------------------------------------------------------------

/** 대기 화면에서만 다시 조회한다. 카드가 보이는 중이면 false. */
export function shouldRefetchOnTimer(session: StudySession, nowMs: number): boolean {
  // 조회 실패 뒤에는 타이머로 다시 조회하지 않는다(실패 반복 루프 방지). 다시 불러오기는 사용자가 누른다.
  if (session.status !== "active" || session.halted || session.current || session.attempt) return false;
  if (session.queueError || session.queuePending) return false;
  const queue = session.queue;
  if (!queue || queue.nextDueAt === null) return false;
  const due = Date.parse(queue.nextDueAt);
  return Number.isFinite(due) && nowMs >= due;
}

/** 앱 복귀 때 다시 조회할지. 카드·시도가 있으면 다음 경계까지 기다린다. */
export function shouldRefetchOnVisible(session: StudySession): boolean {
  return session.status === "active" && !session.halted && !session.current && !session.attempt;
}

/** 다음 대기 타이머까지 남은 밀리초(대기 화면이 아니면 null). */
export function waitDelayMs(session: StudySession, nowMs: number): number | null {
  if (session.current || session.attempt || session.status !== "active" || session.halted) return null;
  if (session.queueError || session.queuePending) return null;
  const queue = session.queue;
  if (!queue || queue.nextDueAt === null) return null;
  const due = Date.parse(queue.nextDueAt);
  if (!Number.isFinite(due)) return null;
  return Math.max(0, due - nowMs);
}
