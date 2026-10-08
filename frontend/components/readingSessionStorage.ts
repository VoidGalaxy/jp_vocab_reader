// 읽기 원문·상태의 기기 저장 (읽기 저장 경계 Gate B).
// 계약: docs/plans/reading-storage-boundary/PLAN.md, gate-a/REPORT.md, gate-b/CONTRACT.md.
//
// - 키: jp-vocab-reader:reading-session-v3:<api-scope>:user:<id> 또는 …:guest.
//   api-scope는 learningPlanStorageScope(apiBaseUrl)의 결과를 호출자가 넘긴다.
// - 옛 공통 키(reading-session-v1)는 읽기만 한다. 이 모듈은 그 키를 쓰거나
//   지우지 않는다.
// - 쓰기는 Web Locks의 키별 배타 잠금 안에서만 한다. 잠금을 얻은 뒤 작업 문맥
//   (owner·계정 세대 등)이 아직 유효한지 다시 확인하고, 저장된 버전
//   {instanceId, revision}과 목적지 존재 여부를 확인한 다음 쓰고, 다시 읽어
//   확인한다. 잠금 요청이 실패하면 쓰지 않고 lock_failed를 돌려준다.
// - 쓰기 후 확인에 실패하면 unverified: 성공도 이전 값 보존도 단정하지 않고,
//   되돌리지도 않는다. 다시 읽어 버전을 확인하기 전에는 더 쓸 수 없다.
// - 잠금이 없으면(미지원·비보안 컨텍스트) 읽기만 하고 자동 저장·복사는 하지
//   않는다("unsupported").
// - 깨진 자료·owner 불일치·초과 길이·쓰기 실패·충돌 어느 경우에도 기존 값을
//   지우거나 덮어쓰지 않는다. 삭제는 removeReadingSession(사용자 확인 후,
//   버전 일치)만 한다.
// - 이메일·토큰은 저장하지 않는다.
//
// React와 무관한 순수 모듈. Node 타입 제거 실행으로 테스트하므로 값 import와
// 런타임 TS 문법(enum, namespace 등)을 쓰지 않는다.

import type { QualityTag, TokenStatus, TokenWithStatus } from "./types";

export const LEGACY_READING_SESSION_KEY = "jp-vocab-reader:reading-session-v1";
export const READING_SESSION_KEY_PREFIX = "jp-vocab-reader:reading-session-v3:";
export const READING_SESSION_VERSION = 3;
export const READING_LOCK_PREFIX = "jp-vocab-reader:lock:";
// 기존 제한과 같다. 넘으면 쓰기를 거절하고 기존 저장본은 그대로 둔다.
export const MAX_READING_TEXT_LENGTH = 200000;

// ---- 타입 -------------------------------------------------------------------

export type ReadingOwner = { kind: "user"; userId: number } | { kind: "guest" };

/** 읽기 화면 상태 중 기기에 남기는 부분(옛 v1/v2 payload의 데이터와 같다). */
export type ReadingSessionData = {
  originalText: string;
  analyzedText: string;
  deckId: string;
  tokens: TokenWithStatus[];
  selectedTokenKey: string | null;
  message: string;
  isTextCollapsed: boolean;
  recentlySavedVocabItemIds: number[];
  scrollFraction: number | null;
  tabletDocumentScrollFraction: number | null;
};

/**
 * 저장된 세션의 버전. instanceId는 키가 새로 만들어질 때(첫 저장·복사)마다
 * 새로 정한다. 삭제 후 다시 만든 세션은 revision이 1로 같아도 instanceId가
 * 달라 옛 창의 버전과 구별된다.
 */
export type ReadingSessionVersion = { instanceId: string; revision: number };

export type StoredReadingSession = {
  version: 3;
  scope: string;
  owner: ReadingOwner;
  instanceId: string;
  revision: number;
  updatedAt: string;
  session: ReadingSessionData;
};

export type LegacyReadingSession = {
  version: 1 | 2;
  updatedAt: string;
  session: ReadingSessionData;
};

export type CorruptReason = "invalid_json" | "unsupported_version" | "invalid_fields" | "owner_mismatch";

export type ReadResult<T> =
  | { kind: "empty" }
  | { kind: "ok"; value: T }
  | { kind: "corrupt"; reason: CorruptReason }
  | { kind: "unavailable" };

/**
 * 실패 결과의 previous: 이 호출이 이 키를 바꾸지 않았고, 이전 저장본이
 * 있으면 그대로 남아 있음(kept) / 원래 없었음(none) / 알 수 없음(unknown).
 * 쓰기 후 확인에 실패한 경우는 error가 아니라 unverified로 따로 돌려준다.
 */
export type PreviousState = "kept" | "none" | "unknown";

/**
 * 쓰기 자체가 실패한 원인. 이 경우 저장소의 값은 바뀌지 않았다.
 * - quota/denied/unknown: setItem 예외
 * - unavailable: 쓰기 전 현재 값을 읽지 못함(쓰지 않음)
 * - not_persisted: setItem은 끝났지만 다시 읽은 값이 이전 값 그대로
 * - lock_failed: 잠금 요청 실패(SecurityError 등). 잠금 없이 쓰지 않는다
 */
export type WriteFailureReason = "quota" | "denied" | "unavailable" | "not_persisted" | "lock_failed" | "unknown";

/**
 * 쓰기(또는 삭제) 호출은 끝났지만 결과를 확인하지 못함. 값이 바뀌었을 수도,
 * 아닐 수도 있다. 이전 값으로 되돌리지 않는다. 호출자는 다시 읽어 확인하기
 * 전까지 저장 성공·이전 값 보존 어느 쪽도 단정하지 않는다.
 */
export type UnverifiedReason = "read_back_failed" | "read_back_mismatch";

export type SaveResult =
  | { kind: "ok"; version: ReadingSessionVersion }
  | { kind: "conflict"; stored: ReadingSessionVersion | null; previous: "kept" | "none" }
  | { kind: "corrupt"; reason: CorruptReason; previous: "kept" }
  | { kind: "tooLarge"; previous: "kept" | "none" }
  | { kind: "error"; reason: WriteFailureReason; previous: PreviousState }
  | { kind: "unverified"; reason: UnverifiedReason }
  | { kind: "cancelled" }
  | { kind: "unsupported" };

export type CopyResult =
  | { kind: "ok"; version: ReadingSessionVersion }
  | { kind: "destinationExists" }
  | { kind: "tooLarge" }
  | { kind: "error"; reason: WriteFailureReason }
  | { kind: "unverified"; reason: UnverifiedReason }
  | { kind: "cancelled" }
  | { kind: "unsupported" };

export type RemoveResult =
  | { kind: "ok" }
  | { kind: "conflict"; stored: ReadingSessionVersion | "corrupt" }
  | { kind: "error"; reason: WriteFailureReason }
  | { kind: "unverified"; reason: UnverifiedReason }
  | { kind: "cancelled" }
  | { kind: "unsupported" };

export type CopyMode = "textOnly" | "full";

/** 브라우저가 실제로 허용하는 범위. readOnly = 잠금 미지원(A안: 읽기·다운로드만). */
export type ReadingStorageCapability = "full" | "readOnly" | "unavailable";

export type StorageLike = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export type LockManagerLike = {
  request<T>(
    name: string,
    options: { mode?: "exclusive" | "shared"; signal?: AbortSignal },
    callback: (lock: unknown) => Promise<T> | T,
  ): Promise<T>;
};

export type ReadingStorageEnv = {
  storage: StorageLike | null;
  locks: LockManagerLike | null;
};

/** 쓰기 문맥. isCurrent는 잠금을 얻은 뒤와 실제 쓰기 직전에 다시 확인한다. */
export type WriteContext = {
  isCurrent: () => boolean;
  signal?: AbortSignal;
};

// ---- 키 ---------------------------------------------------------------------

function assertScope(scope: string): void {
  // learningPlanStorageScope는 encodeURIComponent 결과라 ':'가 없다.
  if (!scope || scope.includes(":")) {
    throw new Error("invalid reading storage scope");
  }
}

function isValidUserId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function readingSessionKey(scope: string, owner: ReadingOwner): string {
  assertScope(scope);
  if (owner.kind === "guest") return `${READING_SESSION_KEY_PREFIX}${scope}:guest`;
  if (!isValidUserId(owner.userId)) throw new Error("invalid reading storage owner");
  return `${READING_SESSION_KEY_PREFIX}${scope}:user:${owner.userId}`;
}

export function readingSessionLockName(key: string): string {
  return `${READING_LOCK_PREFIX}${key}`;
}

export function readingStorageCapability(env: ReadingStorageEnv): ReadingStorageCapability {
  if (!env.storage) return "unavailable";
  if (!env.locks || typeof env.locks.request !== "function") return "readOnly";
  return "full";
}

// ---- 검증 -------------------------------------------------------------------

const TOKEN_STATUSES: readonly TokenStatus[] = ["unclassified", "known", "uncertain", "unknown"];
const QUALITY_TAGS: readonly QualityTag[] = [
  "normal",
  "custom_term",
  "compound_verb",
  "noun_phrase_candidate",
  "known_phrase",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function clampFraction(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? Math.min(Math.max(value, 0), 1) : null;
}

function parseToken(value: unknown): TokenWithStatus | null {
  if (!isRecord(value)) return null;
  const t = value;
  if (
    typeof t.surface !== "string" ||
    typeof t.base_form !== "string" ||
    typeof t.reading !== "string" ||
    typeof t.part_of_speech !== "string" ||
    typeof t.normalized_form !== "string" ||
    typeof t.meaning_ko !== "string" ||
    typeof t.example_sentence !== "string" ||
    !TOKEN_STATUSES.includes(t.status as TokenStatus)
  ) {
    return null;
  }
  const isCustom = typeof t.is_custom_term === "boolean" ? t.is_custom_term : false;
  const token: TokenWithStatus = {
    surface: t.surface,
    base_form: t.base_form,
    reading: t.reading,
    part_of_speech: t.part_of_speech,
    normalized_form: t.normalized_form,
    meaning_ko: t.meaning_ko,
    dictionary_gloss: typeof t.dictionary_gloss === "string" ? t.dictionary_gloss : "",
    quality_tag: QUALITY_TAGS.includes(t.quality_tag as QualityTag)
      ? (t.quality_tag as QualityTag)
      : isCustom
        ? "custom_term"
        : "normal",
    example_sentence: t.example_sentence,
    is_custom_term: isCustom,
    occurrence_count: typeof t.occurrence_count === "number" ? t.occurrence_count : 1,
    status: t.status as TokenStatus,
    isClassified: typeof t.isClassified === "boolean" ? t.isClassified : t.status !== "unclassified",
  };
  if (typeof t.jlpt_level === "string" || t.jlpt_level === null) token.jlpt_level = t.jlpt_level;
  if (typeof t.savedExampleSentence === "string" || t.savedExampleSentence === null) {
    token.savedExampleSentence = t.savedExampleSentence;
  } else {
    token.savedExampleSentence = null;
  }
  if (typeof t.savedMeaningKo === "string" || t.savedMeaningKo === null) token.savedMeaningKo = t.savedMeaningKo;
  if (isValidUserId(t.savedVocabItemId) || t.savedVocabItemId === null) {
    token.savedVocabItemId = t.savedVocabItemId as number | null;
  }
  return token;
}

/** 세션 데이터 필드 검증(옛 v1/v2와 v3 공통). 하나라도 어긋나면 null. */
function parseSessionData(v: Record<string, unknown>): ReadingSessionData | null {
  if (
    typeof v.originalText !== "string" ||
    typeof v.analyzedText !== "string" ||
    typeof v.deckId !== "string" ||
    !Array.isArray(v.tokens) ||
    typeof v.message !== "string" ||
    typeof v.isTextCollapsed !== "boolean" ||
    !Array.isArray(v.recentlySavedVocabItemIds)
  ) {
    return null;
  }
  const tokens: TokenWithStatus[] = [];
  for (const raw of v.tokens) {
    const token = parseToken(raw);
    if (!token) return null;
    tokens.push(token);
  }
  return {
    originalText: v.originalText,
    analyzedText: v.analyzedText,
    deckId: v.deckId,
    tokens,
    selectedTokenKey: typeof v.selectedTokenKey === "string" ? v.selectedTokenKey : null,
    message: v.message,
    isTextCollapsed: v.isTextCollapsed,
    recentlySavedVocabItemIds: v.recentlySavedVocabItemIds.filter(isValidUserId),
    scrollFraction: clampFraction(v.scrollFraction),
    tabletDocumentScrollFraction: clampFraction(v.tabletDocumentScrollFraction),
  };
}

function parseJson(raw: string): { ok: true; value: unknown } | { ok: false } {
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false };
  }
}

/** 옛 공통 키 payload(v1/v2). 순수 함수: 저장소를 건드리지 않는다. */
export function parseLegacyReadingSession(raw: string | null): ReadResult<LegacyReadingSession> {
  if (raw === null) return { kind: "empty" };
  const parsed = parseJson(raw);
  if (!parsed.ok) return { kind: "corrupt", reason: "invalid_json" };
  if (!isRecord(parsed.value)) return { kind: "corrupt", reason: "invalid_fields" };
  const v = parsed.value;
  if (v.version !== 1 && v.version !== 2) return { kind: "corrupt", reason: "unsupported_version" };
  if (typeof v.updatedAt !== "string") return { kind: "corrupt", reason: "invalid_fields" };
  const session = parseSessionData(v);
  if (!session) return { kind: "corrupt", reason: "invalid_fields" };
  return { kind: "ok", value: { version: v.version, updatedAt: v.updatedAt, session } };
}

function sameOwner(a: ReadingOwner, b: ReadingOwner): boolean {
  return a.kind === b.kind && (a.kind === "guest" || a.userId === (b as { userId: number }).userId);
}

function parseOwner(value: unknown): ReadingOwner | null {
  if (!isRecord(value)) return null;
  if (value.kind === "guest") return { kind: "guest" };
  if (value.kind === "user" && isValidUserId(value.userId)) return { kind: "user", userId: value.userId };
  return null;
}

/** v3 payload. 키의 scope·owner와 payload가 다르면 owner_mismatch(복원하지 않음). */
export function parseStoredReadingSession(
  raw: string | null,
  expected: { scope: string; owner: ReadingOwner },
): ReadResult<StoredReadingSession> {
  if (raw === null) return { kind: "empty" };
  const parsed = parseJson(raw);
  if (!parsed.ok) return { kind: "corrupt", reason: "invalid_json" };
  if (!isRecord(parsed.value)) return { kind: "corrupt", reason: "invalid_fields" };
  const v = parsed.value;
  if (v.version !== READING_SESSION_VERSION) return { kind: "corrupt", reason: "unsupported_version" };
  const owner = parseOwner(v.owner);
  if (
    typeof v.scope !== "string" ||
    !owner ||
    typeof v.instanceId !== "string" ||
    v.instanceId.length === 0 ||
    v.instanceId.length > 100 ||
    !isValidUserId(v.revision) ||
    typeof v.updatedAt !== "string" ||
    !isRecord(v.session)
  ) {
    return { kind: "corrupt", reason: "invalid_fields" };
  }
  if (v.scope !== expected.scope || !sameOwner(owner, expected.owner)) {
    return { kind: "corrupt", reason: "owner_mismatch" };
  }
  const session = parseSessionData(v.session);
  if (!session) return { kind: "corrupt", reason: "invalid_fields" };
  return {
    kind: "ok",
    value: {
      version: 3,
      scope: v.scope,
      owner,
      instanceId: v.instanceId,
      revision: v.revision,
      updatedAt: v.updatedAt,
      session,
    },
  };
}

// ---- 읽기 -------------------------------------------------------------------

function safeGet(storage: StorageLike | null, key: string): { ok: true; raw: string | null } | { ok: false } {
  if (!storage) return { ok: false };
  try {
    return { ok: true, raw: storage.getItem(key) };
  } catch {
    return { ok: false };
  }
}

/** 현재 owner의 v3 세션 읽기. 잠금 없이도 가능(A안의 읽기). 아무것도 쓰지 않는다. */
export function readReadingSession(
  env: ReadingStorageEnv,
  scope: string,
  owner: ReadingOwner,
): ReadResult<StoredReadingSession> {
  const got = safeGet(env.storage, readingSessionKey(scope, owner));
  if (!got.ok) return { kind: "unavailable" };
  return parseStoredReadingSession(got.raw, { scope, owner });
}

/** 옛 공통 키 읽기. 아무것도 쓰거나 지우지 않는다. */
export function readLegacyReadingSession(env: ReadingStorageEnv): ReadResult<LegacyReadingSession> {
  const got = safeGet(env.storage, LEGACY_READING_SESSION_KEY);
  if (!got.ok) return { kind: "unavailable" };
  return parseLegacyReadingSession(got.raw);
}

/** 옛 공통 키의 원문자열 그대로(다운로드용). 없거나 읽을 수 없으면 null. */
export function readLegacyReadingSessionRaw(env: ReadingStorageEnv): string | null {
  const got = safeGet(env.storage, LEGACY_READING_SESSION_KEY);
  return got.ok ? got.raw : null;
}

// ---- 사본 만들기 ------------------------------------------------------------

/**
 * 전체 로컬 사본: 서버와 이어진 정보를 뗀다. 옛 덱 ID, 저장된 단어 ID,
 * 저장 완료 안내, 최근 저장 IDs, 서버에 저장된 뜻/예문을 지운다. 로컬 분류
 * 상태·선택·위치·분석 결과(사전 뜻·분석 예문)는 남긴다. 입력은 바꾸지 않는다.
 */
export function detachServerLinks(session: ReadingSessionData): ReadingSessionData {
  return {
    ...session,
    deckId: "",
    message: "",
    recentlySavedVocabItemIds: [],
    tokens: session.tokens.map((token) => ({
      ...token,
      savedVocabItemId: null,
      savedExampleSentence: null,
      savedMeaningKo: null,
    })),
  };
}

/** 원문만: 입력칸에 넣을 원문 하나만 남긴 새 세션. */
export function textOnlySession(session: ReadingSessionData): ReadingSessionData {
  return {
    originalText: session.originalText || session.analyzedText,
    analyzedText: "",
    deckId: "",
    tokens: [],
    selectedTokenKey: null,
    message: "",
    isTextCollapsed: false,
    recentlySavedVocabItemIds: [],
    scrollFraction: null,
    tabletDocumentScrollFraction: null,
  };
}

export function buildCopySession(source: ReadingSessionData, mode: CopyMode): ReadingSessionData {
  return mode === "textOnly" ? textOnlySession(source) : detachServerLinks(source);
}

export function isTooLarge(session: ReadingSessionData): boolean {
  return (
    session.originalText.length > MAX_READING_TEXT_LENGTH ||
    session.analyzedText.length > MAX_READING_TEXT_LENGTH
  );
}

// ---- 쓰기 -------------------------------------------------------------------

function errorName(error: unknown): string {
  return error && typeof error === "object" ? String((error as { name?: unknown }).name ?? "") : "";
}

function failureReason(error: unknown): WriteFailureReason {
  const name = errorName(error);
  if (name === "QuotaExceededError" || name === "NS_ERROR_DOM_QUOTA_REACHED") return "quota";
  if (name === "SecurityError") return "denied";
  return "unknown";
}

function isAbort(error: unknown): boolean {
  return errorName(error) === "AbortError";
}

type LockOutcome<T> = T | { kind: "cancelled" } | { kind: "unsupported" } | { kind: "lockFailed" };

/**
 * 잠금 안에서 fn 실행. 잠금 대기 중 abort되거나, 얻은 뒤 문맥이 무효면
 * cancelled. 잠금 요청 자체가 실패하면(SecurityError 등) lockFailed — 잠금
 * 없이 쓰는 우회 경로는 없다.
 */
async function withKeyLock<T>(
  env: ReadingStorageEnv,
  key: string,
  context: WriteContext,
  fn: () => T,
): Promise<LockOutcome<T>> {
  if (readingStorageCapability(env) !== "full") return { kind: "unsupported" };
  if (context.signal?.aborted || !context.isCurrent()) return { kind: "cancelled" };
  try {
    return await env.locks!.request(
      readingSessionLockName(key),
      { mode: "exclusive", signal: context.signal },
      async () => {
        if (context.signal?.aborted || !context.isCurrent()) return { kind: "cancelled" as const };
        return fn();
      },
    );
  } catch (error) {
    if (isAbort(error) || context.signal?.aborted) return { kind: "cancelled" };
    // fn은 자기 예외를 결과로 바꾸므로, 여기까지 오면 잠금 요청 실패다.
    return { kind: "lockFailed" };
  }
}

function newInstanceId(): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

function serialize(
  scope: string,
  owner: ReadingOwner,
  version: ReadingSessionVersion,
  session: ReadingSessionData,
  now: Date,
) {
  const payload: StoredReadingSession = {
    version: 3,
    scope,
    owner: owner.kind === "guest" ? { kind: "guest" } : { kind: "user", userId: owner.userId },
    instanceId: version.instanceId,
    revision: version.revision,
    updatedAt: now.toISOString(),
    session,
  };
  return JSON.stringify(payload);
}

function sameVersion(a: ReadingSessionVersion | null, b: ReadingSessionVersion | null): boolean {
  if (a === null || b === null) return a === b;
  return a.instanceId === b.instanceId && a.revision === b.revision;
}

type CurrentState =
  | { ok: true; raw: string | null; version: ReadingSessionVersion | null }
  | { ok: false; result: { kind: "corrupt"; reason: CorruptReason } | { kind: "unavailable" } };

/** 잠금 안의 현재 값: 없음(null) / 버전 / 깨짐 / 읽기 실패. */
function readCurrent(storage: StorageLike, key: string, expected: { scope: string; owner: ReadingOwner }): CurrentState {
  const got = safeGet(storage, key);
  if (!got.ok) return { ok: false, result: { kind: "unavailable" } };
  if (got.raw === null) return { ok: true, raw: null, version: null };
  const parsed = parseStoredReadingSession(got.raw, expected);
  if (parsed.kind === "ok") {
    return { ok: true, raw: got.raw, version: { instanceId: parsed.value.instanceId, revision: parsed.value.revision } };
  }
  if (parsed.kind === "corrupt") return { ok: false, result: { kind: "corrupt", reason: parsed.reason } };
  return { ok: false, result: { kind: "unavailable" } };
}

type WriteOutcome =
  | { kind: "ok" }
  // setItem이 예외로 실패: 브라우저 저장소는 이전 값을 그대로 둔다.
  | { kind: "writeFailed"; reason: WriteFailureReason }
  // setItem은 끝났지만 다시 읽은 값이 이전 값 그대로: 반영되지 않았다.
  | { kind: "notPersisted" }
  // setItem은 끝났지만 확인할 수 없음(다시 읽기 실패·다른 값): 상태 불명.
  | { kind: "unverified"; reason: UnverifiedReason };

/** 쓰고 다시 읽어 확인. 실패해도 이전 값으로 되돌리지 않는다. */
function writeAndVerify(storage: StorageLike, key: string, value: string, previousRaw: string | null): WriteOutcome {
  try {
    storage.setItem(key, value);
  } catch (error) {
    return { kind: "writeFailed", reason: failureReason(error) };
  }
  const back = safeGet(storage, key);
  if (!back.ok) return { kind: "unverified", reason: "read_back_failed" };
  if (back.raw === value) return { kind: "ok" };
  if (back.raw === previousRaw) return { kind: "notPersisted" };
  return { kind: "unverified", reason: "read_back_mismatch" };
}

function previousOf(raw: string | null): "kept" | "none" {
  return raw === null ? "none" : "kept";
}

/**
 * 현재 owner 키에 세션을 저장한다(자동 저장·사용자 편집 공통).
 *
 * base: 이 창이 마지막으로 읽었거나 썼다고 확인한 버전. 키가 없다고 확인했으면
 * null. 저장된 값의 {instanceId, revision}이 base와 정확히 같을 때만 쓴다.
 * 다르면(다른 창이 저장·삭제·재생성) conflict이고 덮어쓰지 않는다.
 * instanceId는 키가 새로 만들어질 때마다 새로 정하므로, 삭제 후 다시 만든
 * 세션의 revision이 1로 같아도 옛 창의 base와 맞지 않는다.
 *
 * unverified(쓰기 후 확인 불가)면 새 버전을 돌려주지 않는다. 호출자는
 * readReadingSession으로 다시 확인해 새 base를 얻기 전에는 저장할 수 없다
 * (옛 base로 저장하면 값이 바뀐 경우 conflict가 된다).
 */
export async function saveReadingSession(
  env: ReadingStorageEnv,
  args: {
    scope: string;
    owner: ReadingOwner;
    base: ReadingSessionVersion | null;
    session: ReadingSessionData;
    now?: Date;
  } & WriteContext,
): Promise<SaveResult> {
  const key = readingSessionKey(args.scope, args.owner);
  const expected = { scope: args.scope, owner: args.owner };
  const result = await withKeyLock<SaveResult>(env, key, args, () => {
    try {
      const storage = env.storage!;
      const current = readCurrent(storage, key, expected);
      if (!current.ok) {
        return current.result.kind === "corrupt"
          ? { kind: "corrupt", reason: current.result.reason, previous: "kept" }
          : { kind: "error", reason: "unavailable", previous: "unknown" };
      }
      if (!sameVersion(current.version, args.base)) {
        return { kind: "conflict", stored: current.version, previous: previousOf(current.raw) };
      }
      const previous = previousOf(current.raw);
      if (isTooLarge(args.session)) return { kind: "tooLarge", previous };
      // 쓰기 직전 한 번 더: 위 확인 사이에 계정이 바뀌었으면 쓰지 않는다.
      if (!args.isCurrent()) return { kind: "cancelled" };

      const next: ReadingSessionVersion = current.version
        ? { instanceId: current.version.instanceId, revision: current.version.revision + 1 }
        : { instanceId: newInstanceId(), revision: 1 };
      const outcome = writeAndVerify(
        storage,
        key,
        serialize(args.scope, args.owner, next, args.session, args.now ?? new Date()),
        current.raw,
      );
      if (outcome.kind === "ok") return { kind: "ok", version: next };
      if (outcome.kind === "writeFailed") return { kind: "error", reason: outcome.reason, previous };
      if (outcome.kind === "notPersisted") return { kind: "error", reason: "not_persisted", previous };
      return { kind: "unverified", reason: outcome.reason };
    } catch {
      return { kind: "error", reason: "unknown", previous: "unknown" };
    }
  });
  if (result.kind === "lockFailed") return { kind: "error", reason: "lock_failed", previous: "unknown" };
  return result as SaveResult;
}

/**
 * 사용자가 본인 자료임을 확인한 뒤, 빈 목적지(키 자체가 없음)에만 복사한다.
 * 키가 있으면 내용이 비었거나 깨졌어도 destinationExists. 원본은 읽기만 한다.
 * 새 instanceId로 revision 1을 만든다.
 */
export async function copyToEmptyReadingSession(
  env: ReadingStorageEnv,
  args: {
    scope: string;
    owner: ReadingOwner;
    source: ReadingSessionData;
    mode: CopyMode;
    now?: Date;
  } & WriteContext,
): Promise<CopyResult> {
  const key = readingSessionKey(args.scope, args.owner);
  const copy = buildCopySession(args.source, args.mode);
  const result = await withKeyLock<CopyResult>(env, key, args, () => {
    try {
      const storage = env.storage!;
      const current = safeGet(storage, key);
      if (!current.ok) return { kind: "error", reason: "unavailable" };
      if (current.raw !== null) return { kind: "destinationExists" };
      if (isTooLarge(copy)) return { kind: "tooLarge" };
      if (!args.isCurrent()) return { kind: "cancelled" };
      const version: ReadingSessionVersion = { instanceId: newInstanceId(), revision: 1 };
      const outcome = writeAndVerify(
        storage,
        key,
        serialize(args.scope, args.owner, version, copy, args.now ?? new Date()),
        null,
      );
      if (outcome.kind === "ok") return { kind: "ok", version };
      if (outcome.kind === "writeFailed") return { kind: "error", reason: outcome.reason };
      if (outcome.kind === "notPersisted") return { kind: "error", reason: "not_persisted" };
      return { kind: "unverified", reason: outcome.reason };
    } catch {
      return { kind: "error", reason: "unknown" };
    }
  });
  if (result.kind === "lockFailed") return { kind: "error", reason: "lock_failed" };
  return result as CopyResult;
}

/**
 * 사용자가 확인한 "현재 읽기 초기화"만 쓰는 삭제. 현재 owner의 키 하나만,
 * 저장된 {instanceId, revision}이 expected와 정확히 같을 때만 지운다. 그래서
 * 옛 창의 삭제는 삭제 후 다시 만든 세션에 적용되지 않는다. 깨진 자료는
 * expected: "corrupt"를 명시해야만 지운다.
 */
export async function removeReadingSession(
  env: ReadingStorageEnv,
  args: { scope: string; owner: ReadingOwner; expected: ReadingSessionVersion | "corrupt" } & WriteContext,
): Promise<RemoveResult> {
  const key = readingSessionKey(args.scope, args.owner);
  const expectedOwner = { scope: args.scope, owner: args.owner };
  const result = await withKeyLock<RemoveResult>(env, key, args, () => {
    try {
      const storage = env.storage!;
      const current = readCurrent(storage, key, expectedOwner);
      if (!current.ok && current.result.kind === "unavailable") return { kind: "error", reason: "unavailable" };
      if (current.ok && current.raw === null) return { kind: "ok" };
      const matches = current.ok
        ? args.expected !== "corrupt" && sameVersion(current.version, args.expected)
        : args.expected === "corrupt";
      if (!matches) return { kind: "conflict", stored: current.ok ? current.version! : "corrupt" };
      if (!args.isCurrent()) return { kind: "cancelled" };
      try {
        storage.removeItem(key);
      } catch (error) {
        return { kind: "error", reason: failureReason(error) };
      }
      const back = safeGet(storage, key);
      if (!back.ok) return { kind: "unverified", reason: "read_back_failed" };
      if (back.raw !== null) return { kind: "unverified", reason: "read_back_mismatch" };
      return { kind: "ok" };
    } catch {
      return { kind: "error", reason: "unknown" };
    }
  });
  if (result.kind === "lockFailed") return { kind: "error", reason: "lock_failed" };
  return result as RemoveResult;
}

// ---- 다운로드 ---------------------------------------------------------------

export type ReadingDownload = { fileName: string; mimeType: string; content: string };

function stamp(now: Date): string {
  return now.toISOString().slice(0, 19).replace(/[-:T]/g, "");
}

/** 저장된 원자료를 바꾸지 않고 그대로 내려받을 파일 내용. 클릭 때만 만든다. */
export function rawBackupDownload(raw: string, now: Date = new Date()): ReadingDownload {
  return { fileName: `reading-session-backup-${stamp(now)}.json`, mimeType: "application/json", content: raw };
}

/** 메모리 편집(저장 실패·잠금 미지원)의 원문 텍스트 다운로드. */
export function originalTextDownload(session: ReadingSessionData, now: Date = new Date()): ReadingDownload {
  return {
    fileName: `reading-text-${stamp(now)}.txt`,
    mimeType: "text/plain;charset=utf-8",
    content: session.originalText || session.analyzedText,
  };
}
