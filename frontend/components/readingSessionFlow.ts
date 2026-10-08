// 읽기 흐름의 순수 규칙(읽기 저장 경계 Gate D). page.tsx가 쓰고, 테스트는
// 가짜 상태로 돌린다. React·저장소·네트워크와 무관하다.
//
// - 작업 문맥 가드: 요청을 시작할 때의 owner 키·account epoch·읽기 작업 ID
//   (그리고 필요하면 덱)를 잡아 두고, 응답·catch·finally를 적용하기 전에 그대로인지
//   본다. 계정 경계·새 원문(초기화)·원문 교체·새 분석·복원은 작업 ID를 바꾼다.
// - 요청 순서: 같은 종류의 요청이 겹칠 때 마지막 요청만 결과와 진행 표시를 바꾼다.
// - 덱 확인: 덱 연결 없이 토큰만 있는 세션(전체 사본)은 어느 경로로 열든
//   덱을 확인하기 전에는 서버에 저장하지 않는다.
// - 확인 실패 재확인: 저장소 값이 이 창이 마지막으로 시도한 결과와 같을 때만
//   채택한다.
//
// Node 타입 제거 실행으로 테스트하므로 값 import와 런타임 TS 문법을 쓰지 않는다.

import type { ReadResult, ReadingSessionData, StoredReadingSession } from "./readingSessionStorage";

export type ReadingContextSource = {
  ownerKey: () => string | null;
  accountEpoch: () => number;
  workId: () => number;
  deckId: () => string;
};

export type ReadingContext = {
  ownerKey: string | null;
  deckId: string;
  /** 계정·작업이 그대로인지(덱은 보지 않음). */
  isCurrent: () => boolean;
  /** 계정·작업에 더해, 요청 당시 덱이 지금도 선택돼 있는지. */
  isCurrentForDeck: () => boolean;
};

export function captureReadingContext(source: ReadingContextSource): ReadingContext {
  const ownerKey = source.ownerKey();
  const epoch = source.accountEpoch();
  const work = source.workId();
  const deckId = source.deckId();
  const isCurrent = () =>
    ownerKey !== null &&
    source.ownerKey() === ownerKey &&
    source.accountEpoch() === epoch &&
    source.workId() === work;
  return {
    ownerKey,
    deckId,
    isCurrent,
    isCurrentForDeck: () => isCurrent() && source.deckId() === deckId,
  };
}

/** 같은 종류 요청의 순서. start()가 준 번호가 마지막일 때만 결과·진행 표시를 바꾼다. */
export function createRequestSequence() {
  let latest = 0;
  return {
    start(): number {
      latest += 1;
      return latest;
    },
    isLatest(id: number): boolean {
      return id === latest;
    },
    /** 진행 중인 요청을 모두 오래된 것으로 만든다. */
    invalidate(): void {
      latest += 1;
    },
  };
}

/** 덱 연결 없이 토큰만 있는 세션은 덱을 확인해야 서버에 저장할 수 있다. */
export function requiresDeckConfirmation(session: Pick<ReadingSessionData, "deckId" | "tokens">): boolean {
  return !session.deckId && session.tokens.length > 0;
}

export type LastStorageAttempt = { kind: "save"; json: string } | { kind: "remove" } | null;

export type RecheckOutcome =
  | { kind: "adopt"; instanceId: string; revision: number; json: string }
  | { kind: "adoptEmpty" }
  | { kind: "conflict" }
  | { kind: "unavailable" };

/**
 * 쓰기·삭제 뒤 확인하지 못한 상태(unverified)에서 다시 읽은 결과의 판단.
 * - 저장을 시도했다면: 저장값이 시도한 내용과 같을 때만 그 버전을 채택.
 * - 삭제를 시도했다면: 키가 없을 때만 빈 상태로 채택.
 * - 그 밖(다른 내용·깨짐)은 다른 창 자료일 수 있으므로 충돌.
 */
export function recheckAfterUnverified(
  stored: ReadResult<StoredReadingSession>,
  last: LastStorageAttempt,
  toJson: (session: ReadingSessionData) => string,
): RecheckOutcome {
  if (stored.kind === "unavailable") return { kind: "unavailable" };
  if (last?.kind === "remove") {
    return stored.kind === "empty" ? { kind: "adoptEmpty" } : { kind: "conflict" };
  }
  if (last?.kind === "save" && stored.kind === "ok") {
    const json = toJson(stored.value.session);
    if (json === last.json) {
      return { kind: "adopt", instanceId: stored.value.instanceId, revision: stored.value.revision, json };
    }
  }
  return { kind: "conflict" };
}
