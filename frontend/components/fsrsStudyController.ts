// FSRS 복습 회차의 화면 연결 컨트롤러 (Gate C-2c 보정).
//
// useFsrsStudy(React 훅)가 하던 일을 React 없이 옮겼다. 훅은 이 컨트롤러를 만들고 다시
// 그리기·타이머·앱 복귀·beforeunload만 잇는다. 그래서 조회 티켓·평가 시도·정답 공개·
// 학습 계획 교체 준비를 Node 테스트에서 가짜 요청으로 그대로 검사할 수 있다.
//
// 상태 전이는 모두 studySession.ts가 판단한다. 이 파일은 그 결과를 저장하고 요청을 보낸다.
// - 큐 조회는 모두 beginQueueFetch 티켓으로 하고, 그 티켓으로만 반영한다. 모듈이 받아들인
//   뒤에만 카드 내용·시각 보정·연습 목록을 저장한다.
// - 평가는 최신 회차 상태에서 시도를 한 번 만들고 그 객체를 그대로 보내고 재시도한다.
// - 정답 공개와 응답 시간 기준은 "출제 차례"(presentationKey)에 묶는다. 같은 카드가 다시
//   나오면 새 차례라 질문부터 시작하고, 같은 시도의 재시도는 차례가 같아 그대로 유지된다.
// - 학습 계획 교체는 새 회차를 따로 준비·검증한 뒤에만 기존 회차와 바꾼다(prepare → adopt).
// - 회차·시도는 메모리에만 있다. 새 저장 키를 만들지 않는다(CONTRACT 1-5).
//
// Node 타입 제거 실행 때문에 값 import를 쓰지 않는다. 모듈 함수는 ops로 받는다.

import type * as SessionModule from "./studySession";
import type * as HelperModule from "./fsrsStudy";
import type { StudyCardItem } from "./types";
import type { Attempt, Rating, ReviewOutcome, SessionView, StudySession } from "./studySession";
import type { FetchResult, QueueTarget } from "./fsrsStudy";

export const AUTO_RETRY_DELAY_MS = 1000;
/** 타이머가 같은 next_due_at으로 다시 조회하는 최대 횟수(시계 차이로 인한 반복 방지). */
export const MAX_TIMER_FIRES_PER_DUE = 2;
export const TIMER_MARGIN_MS = 500;

export type FsrsStudyOps = {
  session: Pick<
    typeof SessionModule,
    | "applyQueue"
    | "applyQueueFailure"
    | "applyQueueHalt"
    | "beginAttempt"
    | "beginQueueFetch"
    | "cardKey"
    | "endSession"
    | "parseQueueResponse"
    | "presentationKey"
    | "queueRequestParams"
    | "replaceGuard"
    | "resolveAttempt"
    | "retryAttempt"
    | "sessionView"
    | "shouldRefetchOnTimer"
    | "shouldRefetchOnVisible"
    | "shouldWarnBeforeUnload"
    | "startSession"
    | "waitDelayMs"
  >;
  helpers: Pick<typeof HelperModule, "pendingLaterCount" | "queueFailureKind" | "queuePath" | "studyCardFromQueueItem">;
};

export type FsrsStudyDeps = {
  getAccountEpoch(): number;
  get(path: string): Promise<FetchResult>;
  post(path: string, body: unknown): Promise<FetchResult>;
  /** recent 묶음 연습용: 기존 읽기 전용 목록에서 지정한 개인 카드만. */
  loadRecentPracticeCards(ids: number[]): Promise<StudyCardItem[]>;
  /** 평가가 저장됐을 때(통계 새로고침 등). */
  onReviewSaved(): void;
  /** 평가·조회 중 계정 모드가 바뀌었을 때(모드 판별부터 다시). */
  onModeChanged(): void;
};

export type FsrsStudyEnv = {
  now(): number;
  newId(): string;
  setTimeout(callback: () => void, ms: number): unknown;
  /** 상태가 바뀌어 다시 그려야 할 때. */
  onChange(): void;
};

type Practice = { items: StudyCardItem[]; order: number[]; index: number };

export type FsrsPrimary = SessionView["primary"] | "practice_done";

export type FsrsSnapshot = {
  session: StudySession | null;
  target: QueueTarget | null;
  view: (Omit<SessionView, "primary"> & { primary: FsrsPrimary }) | null;
  card: StudyCardItem | null;
  isAnswerVisible: boolean;
  isPractice: boolean;
  /** 서버 연습 목록이 비었음(연습은 예약 상태가 있는 카드만 나온다). recent 묶음 연습은 해당 없음. */
  practiceEmpty: boolean;
  pendingLater: number;
};

/** 학습 계획 교체용으로 따로 준비한 새 회차. 검증을 마친 응답만 담는다. */
export type PreparedSession = {
  readonly session: StudySession;
  readonly target: QueueTarget;
  readonly contents: ReadonlyArray<readonly [string, StudyCardItem]>;
  readonly practice: Practice | null;
  readonly pendingLater: number;
  readonly serverOffset: number;
};

export type PlanEmptyReason = "goal_reached" | "new_unknown" | "no_cards";

function isPracticeTarget(target: QueueTarget | null): boolean {
  return Boolean(target && (target.kind === "practice" || target.kind === "recent_practice"));
}

export function createFsrsStudyController(ops: FsrsStudyOps, deps: FsrsStudyDeps, env: FsrsStudyEnv) {
  const S = ops.session;
  const H = ops.helpers;

  let session: StudySession | null = null;
  let target: QueueTarget | null = null;
  let contents = new Map<string, StudyCardItem>();
  let practice: Practice | null = null;
  let practiceTurn = 0;
  let pendingLater = 0;
  let serverOffset = 0;
  /** 정답을 공개한 출제 차례와 그 시각. 차례가 바뀌면 자동으로 무효다. */
  let reveal: { key: string; shownAt: number } | null = null;
  let timerFires: { key: string; count: number } = { key: "", count: 0 };

  function commit(next: StudySession | null) {
    session = next;
    env.onChange();
  }

  function serverNow() {
    return env.now() + serverOffset;
  }

  function nowFor(current: StudySession) {
    return { accountEpoch: deps.getAccountEpoch(), sessionId: current.sessionId };
  }

  /** 큐 응답을 해석하고 카드 내용까지 읽는다. 하나라도 틀리면 null(조회 실패로 다룸). */
  function readQueue(body: unknown): { snapshot: NonNullable<ReturnType<typeof S.parseQueueResponse>>; cards: StudyCardItem[] } | null {
    const snapshot = S.parseQueueResponse(body);
    if (!snapshot) return null;
    const rawItems = (body as { items: unknown[] }).items;
    const cards: StudyCardItem[] = [];
    for (let i = 0; i < rawItems.length; i += 1) {
      const card = H.studyCardFromQueueItem(rawItems[i]);
      if (!card) return null;
      cards.push(card);
    }
    return { snapshot, cards };
  }

  function offsetFrom(serverNowIso: string): number | null {
    const ms = Date.parse(serverNowIso);
    return Number.isFinite(ms) ? ms - env.now() : null;
  }

  // ---- 큐 조회 ------------------------------------------------------------------

  async function fetchQueue() {
    const start = session;
    const currentTarget = target;
    if (!start || !currentTarget || start.status !== "active" || start.halted) return;
    if (currentTarget.kind === "recent_practice") return;
    const { session: pending, ticket } = S.beginQueueFetch(start);
    commit(pending);
    const result = await deps.get(H.queuePath(currentTarget, S.queueRequestParams(pending)));
    const current = session;
    if (!current) return;
    let next: StudySession;
    if (result.kind === "ok") {
      const read = readQueue(result.body);
      next = read ? S.applyQueue(current, read.snapshot, ticket) : S.applyQueueFailure(current, ticket);
      if (next === current) return; // 오래된 조회: 카드·집계·오류 상태를 건드리지 않는다
      if (read && next.queue === read.snapshot) {
        for (let i = 0; i < read.cards.length; i += 1) contents.set(S.cardKey(read.snapshot.items[i]), read.cards[i]);
        const offset = offsetFrom(read.snapshot.serverNow);
        if (offset !== null) serverOffset = offset;
        pendingLater = H.pendingLaterCount(result.body);
        if (currentTarget.kind === "practice") {
          practice = { items: read.cards, order: read.cards.map((_, index) => index), index: 0 };
        }
      }
    } else {
      const kind = H.queueFailureKind(result);
      next = "halt" in kind ? S.applyQueueHalt(current, ticket, kind.halt) : S.applyQueueFailure(current, ticket);
      if (next === current) return;
    }
    commit(next);
    if (next.halted === "mode_changed") deps.onModeChanged();
  }

  // ---- 평가 ---------------------------------------------------------------------

  async function send(attempt: Attempt) {
    const result = await deps.post(attempt.path, attempt.payload);
    const outcome: ReviewOutcome =
      result.kind === "ok"
        ? { type: "success", body: result.body }
        : result.kind === "http"
          ? { type: "http", status: result.status, detail: result.detail }
          : { type: "network" };
    const current = session;
    if (!current) return; // 계정 경계·초기화 뒤 늦은 응답
    const resolved = S.resolveAttempt(current, attempt, outcome, nowFor(current));
    if (resolved.effect === "ignored") return; // 늦은 응답이 새 카드·버튼을 바꾸지 않는다
    commit(resolved.session);
    if (resolved.effect === "refetch") {
      if (outcome.type === "success") deps.onReviewSaved();
      void fetchQueue();
    } else if (resolved.effect === "auto_retry") {
      env.setTimeout(() => retry(attempt, true), AUTO_RETRY_DELAY_MS);
    } else if (resolved.effect === "halt" && resolved.session.halted === "mode_changed") {
      deps.onModeChanged();
    }
  }

  function retry(attempt: Attempt, auto: boolean) {
    const current = session;
    if (!current) return;
    // 계정·회차·카드·시도가 그대로일 때만. 계정 전환 뒤에는 이전 계정 요청을 보내지 않는다.
    const result = S.retryAttempt(current, attempt, nowFor(current), auto);
    if (!result.ok) return;
    commit(result.session);
    void send(result.attempt);
  }

  function rate(rating: Rating) {
    const current = session;
    if (!current) return;
    const key = S.presentationKey(current);
    // 응답 시간은 이번 출제 차례에서 정답을 공개한 때부터만 잰다.
    const shownAt = key !== null && reveal && reveal.key === key ? reveal.shownAt : null;
    const begun = S.beginAttempt(current, {
      rating,
      requestId: env.newId(),
      responseTimeMs: shownAt === null ? null : Math.max(0, env.now() - shownAt),
    });
    if (!begun.ok) return; // 연타·연습·카드 없음
    commit(begun.session);
    void send(begun.attempt);
  }

  function retryNow() {
    if (session && session.attempt) retry(session.attempt, false);
  }

  // ---- 회차 ---------------------------------------------------------------------

  function resetLocal(nextTarget: QueueTarget | null) {
    target = nextTarget;
    contents = new Map();
    practice = null;
    pendingLater = 0;
    reveal = null;
    timerFires = { key: "", count: 0 };
  }

  function start(nextTarget: QueueTarget) {
    const fresh = S.startSession(deps.getAccountEpoch(), env.newId());
    resetLocal(nextTarget);
    commit(fresh);
    if (nextTarget.kind === "recent_practice") {
      void loadRecentPractice(fresh, nextTarget.cardIds);
    } else {
      void fetchQueue();
    }
  }

  async function loadRecentPractice(owner: StudySession, ids: number[]) {
    let cards: StudyCardItem[] | null;
    try {
      cards = await deps.loadRecentPracticeCards(ids);
    } catch {
      cards = null;
    }
    const current = session;
    if (!current || current.sessionId !== owner.sessionId || current.accountEpoch !== owner.accountEpoch) return;
    if (cards === null) {
      commit({ ...current, queueError: true });
      return;
    }
    practice = { items: cards, order: cards.map((_, index) => index), index: 0 };
    practiceTurn += 1;
    commit({ ...current, queueError: false });
  }

  function end() {
    if (!session || session.attempt) return; // 전송 중·결과 미확정이면 마치지 않는다
    commit(S.endSession(session));
  }

  /** 같은 대상으로 새 회차(새 sessionId: 미루기 집계·제외 목록 초기화). */
  function restart() {
    if (!target || (session && session.attempt)) return;
    start(target);
  }

  function reset() {
    resetLocal(null);
    commit(null);
  }

  function refetch() {
    if (!session || !target) return;
    if (target.kind === "recent_practice") {
      void loadRecentPractice(session, target.cardIds);
      return;
    }
    void fetchQueue();
  }

  // ---- 학습 계획 교체: 준비 → 검증 → 교체 ------------------------------------------

  /**
   * 새 회차를 기존 회차와 따로 만들고, 그 회차의 첫 조회 티켓으로 큐·카드 내용을 받아 검증한다.
   * 기존 회차는 건드리지 않는다. 실패·해석 실패면 null.
   */
  async function prepare(nextTarget: QueueTarget): Promise<PreparedSession | null> {
    if (nextTarget.kind === "recent_practice") return null;
    const fresh = S.startSession(deps.getAccountEpoch(), env.newId());
    const { session: pending, ticket } = S.beginQueueFetch(fresh);
    const result = await deps.get(H.queuePath(nextTarget, S.queueRequestParams(pending)));
    if (result.kind !== "ok") return null;
    const read = readQueue(result.body);
    if (!read) return null;
    const ready = S.applyQueue(pending, read.snapshot, ticket);
    if (ready.queue !== read.snapshot) return null;
    const entries: Array<readonly [string, StudyCardItem]> = read.cards.map(
      (card, i) => [S.cardKey(read.snapshot.items[i]), card] as const,
    );
    const offset = offsetFrom(read.snapshot.serverNow);
    return Object.freeze({
      session: ready,
      target: nextTarget,
      contents: entries,
      practice:
        nextTarget.kind === "practice"
          ? { items: read.cards, order: read.cards.map((_, index) => index), index: 0 }
          : null,
      pendingLater: H.pendingLaterCount(result.body),
      serverOffset: offset === null ? serverOffset : offset,
    });
  }

  /** 준비한 회차가 비었으면 그 원인(목표 달성·신규 확인 불가·카드 없음). 카드가 있으면 null. */
  function emptyReason(prepared: PreparedSession): PlanEmptyReason | null {
    if (prepared.session.current) return null;
    const primary = S.sessionView(prepared.session, env.now() + prepared.serverOffset).primary;
    if (primary === "goal_reached") return "goal_reached";
    if (primary === "new_unknown") return "new_unknown";
    return "no_cards";
  }

  /**
   * 준비한 회차로 실제 교체한다. 계정이 바뀌었거나 기존 회차의 평가가 전송 중이면 바꾸지 않고
   * false. 이때 기존 회차는 그대로다.
   */
  function adopt(prepared: PreparedSession): boolean {
    if (prepared.session.accountEpoch !== deps.getAccountEpoch()) return false;
    if (S.replaceGuard(session) === "wait") return false;
    resetLocal(prepared.target);
    contents = new Map(prepared.contents);
    practice = prepared.practice
      ? { items: prepared.practice.items, order: prepared.practice.order.slice(), index: 0 }
      : null;
    pendingLater = prepared.pendingLater;
    serverOffset = prepared.serverOffset;
    commit(prepared.session);
    return true;
  }

  // ---- 연습 (평가 POST 없음) ------------------------------------------------------

  function practiceNext(again: boolean) {
    if (!practice || practice.index >= practice.order.length) return;
    const order = practice.order.slice();
    if (again) order.push(order[practice.index]); // "다시 볼게요": 뒤에 한 번 더
    practice = { ...practice, order, index: practice.index + 1 };
    env.onChange();
  }

  // ---- 뜻 수정 반영 ---------------------------------------------------------------

  /**
   * 저장된 개인 카드 뜻을 지금 회차의 카드 내용에 반영한다. 요청을 보낸 계정의 회차일 때만.
   * 같은 id의 개인 카드에만 적용하고 다른 카드는 건드리지 않는다.
   */
  function patchPersonalCard(accountEpoch: number, vocabItemId: number, patch: Partial<StudyCardItem>) {
    if (!session || session.accountEpoch !== accountEpoch || accountEpoch !== deps.getAccountEpoch()) return false;
    let changed = false;
    const key = `personal:${vocabItemId}`;
    const card = contents.get(key);
    if (card) {
      contents.set(key, { ...card, ...patch });
      changed = true;
    }
    if (practice) {
      const items = practice.items.map((item) => {
        if (item.item_type === "vocab" && item.id === vocabItemId) {
          changed = true;
          return { ...item, ...patch };
        }
        return item;
      });
      practice = { ...practice, items };
    }
    if (changed) env.onChange();
    return changed;
  }

  // ---- 화면용 계산 ---------------------------------------------------------------

  function currentKey(): string | null {
    if (!session) return null;
    if (isPracticeTarget(target)) {
      if (!practice || practice.index >= practice.order.length) return null;
      return `${session.sessionId}#p${practiceTurn}#${practice.index}`;
    }
    return S.presentationKey(session);
  }

  function showAnswer() {
    const key = currentKey();
    if (!key) return;
    reveal = { key, shownAt: env.now() };
    env.onChange();
  }

  function snapshot(): FsrsSnapshot {
    const isPractice = isPracticeTarget(target);
    if (!session || !target) {
      return { session, target, view: null, card: null, isAnswerVisible: false, isPractice, practiceEmpty: false, pendingLater: 0 };
    }
    const base = S.sessionView(session, serverNow());
    let view: FsrsSnapshot["view"] = base;
    let card: StudyCardItem | null = null;
    if (isPractice && session.status === "active" && !session.halted) {
      if (practice && practice.index < practice.order.length) {
        card = practice.items[practice.order[practice.index]] ?? null;
        view = { ...base, primary: "card", card: null };
      } else if (practice) {
        view = { ...base, primary: "practice_done", card: null };
      } else {
        view = { ...base, primary: session.queueError ? "error" : "loading", card: null };
      }
    } else if (base.primary === "card" && session.current) {
      card = contents.get(S.cardKey(session.current)) ?? null;
    }
    const key = currentKey();
    return {
      session,
      target,
      view,
      card,
      isAnswerVisible: key !== null && reveal !== null && reveal.key === key,
      isPractice,
      practiceEmpty: target.kind === "practice" && practice !== null && practice.items.length === 0,
      pendingLater,
    };
  }

  // ---- 대기 타이머·앱 복귀·beforeunload ---------------------------------------------

  /** 대기 화면(곧 돌아옴)에서만 next_due_at에 맞춰 한 번 다시 조회한다. */
  function waitTimer(): { key: string; delay: number; fire: () => void } | null {
    const current = session;
    if (!current) return null;
    if (S.sessionView(current, serverNow()).primary !== "soon") return null;
    const delay = S.waitDelayMs(current, serverNow());
    if (delay === null) return null;
    const nextDueAt = current.queue ? current.queue.nextDueAt : null;
    const dueKey = `${current.sessionId}|${nextDueAt ?? ""}`;
    const fires = timerFires.key === dueKey ? timerFires.count : 0;
    if (fires >= MAX_TIMER_FIRES_PER_DUE) return null;
    return {
      key: `${dueKey}|${current.queueSeq}`,
      delay: delay + TIMER_MARGIN_MS,
      fire: () => {
        const latest = session;
        if (!latest || latest.sessionId !== current.sessionId) return;
        if (!S.shouldRefetchOnTimer(latest, serverNow())) return;
        timerFires = { key: dueKey, count: fires + 1 };
        void fetchQueue();
      },
    };
  }

  function onVisible() {
    const current = session;
    if (!current || current.queuePending || !S.shouldRefetchOnVisible(current)) return;
    if (!target || isPracticeTarget(target)) return;
    void fetchQueue();
  }

  return {
    snapshot,
    start,
    rate,
    retryNow,
    showAnswer,
    end,
    restart,
    reset,
    refetch,
    practiceNext,
    prepare,
    emptyReason,
    adopt,
    patchPersonalCard,
    waitTimer,
    onVisible,
    shouldWarnBeforeUnload: () => S.shouldWarnBeforeUnload(session),
    replaceGuard: () => S.replaceGuard(session),
    getSession: () => session,
  };
}

export type FsrsStudyController = ReturnType<typeof createFsrsStudyController>;
