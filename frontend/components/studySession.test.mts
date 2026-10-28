// FSRS 복습 회차 순수 모듈 테스트 (Gate C-2b). 실행: node --test components/studySession.test.mts
// 시계·ID·응답은 모두 테스트가 넘긴다. 이 테스트 통과는 실제 화면 연결(C-2c)의 보호를 뜻하지 않는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFER_AFTER_SHORT_STEP_RESULTS,
  MAX_EXCLUDED,
  applyQueue,
  applyQueueFailure,
  applyQueueHalt,
  beginAttempt,
  beginQueueFetch,
  cardKey,
  effectiveNewRemaining,
  endSession,
  isActiveSession,
  isSubmitting,
  newGoalDisplay,
  parseQueueResponse,
  presentationKey,
  queueRequestParams,
  replaceGuard,
  resolveAttempt,
  retryAttempt,
  sessionView,
  shouldRefetchOnTimer,
  shouldRefetchOnVisible,
  shouldWarnBeforeUnload,
  startSession,
  waitDelayMs,
} from "./studySession.ts";
import type { NewGoalInfo, QueueCard, QueueSnapshot, StudySession } from "./studySession.ts";

const NOW = Date.parse("2026-10-09T03:00:00+00:00");

function card(id: number, extra: Partial<QueueCard> = {}): QueueCard {
  return {
    kind: "personal", id, version: 3, sharedDeckId: null,
    reviewPath: `/study-items/${id}/review`, practiceOnly: false, isNew: false, ...extra,
  };
}

function lexeme(id: number, extra: Partial<QueueCard> = {}): QueueCard {
  return card(id, { kind: "lexeme", sharedDeckId: 9, reviewPath: `/shared-decks/9/words/${id}/review`, ...extra });
}

function snapshot(items: QueueCard[], extra: Partial<QueueSnapshot> = {}, goal: Partial<QueueSnapshot["newGoal"]> = {}): QueueSnapshot {
  return {
    items, newAvailable: 0, newUnmaterialized: 0, excludedByRequest: 0, notMigrated: 0,
    nextDueAt: null, serverNow: "2026-10-09T03:00:00+00:00", seoulDate: "2026-10-09",
    newGoal: {
      status: "exact", introducedToday: 0, introducedAtLeast: 0, accountRemaining: 20,
      planDailyNew: null, introducedInScope: null, introducedInScopeStatus: null, introducedInScopeAtLeast: null,
      planRemaining: null, blockedReason: null, dailyGoal: 20, ...goal,
    },
    ...extra,
  };
}

const owner = (s: StudySession) => ({ accountEpoch: s.accountEpoch, sessionId: s.sessionId });

/** 조회 시작 → 응답 반영을 한 번에 (가장 최근 조회). */
function fetched(s: StudySession, snap: QueueSnapshot): StudySession {
  const { session, ticket } = beginQueueFetch(s);
  return applyQueue(session, snap, ticket);
}

function fetchFailed(s: StudySession): StudySession {
  const { session, ticket } = beginQueueFetch(s);
  return applyQueueFailure(session, ticket);
}

function success(phase: "learning" | "review" | "relearning" = "review") {
  return { type: "success" as const, body: { srs: { state: { phase } } } };
}

function sessionWith(items: QueueCard[], id = "session-a", epoch = 1): StudySession {
  const s = startSession(epoch, id);
  return fetched(s, snapshot(items));
}

function begin(s: StudySession, requestId = "req-1", rating: "again" | "hard" | "good" | "easy" = "good") {
  const result = beginAttempt(s, { rating, requestId, responseTimeMs: 1200 });
  assert.ok(result.ok);
  return result;
}

// ---- 시도 고정과 결과 적용 ----------------------------------------------------------

test("시도는 epoch·회차·카드·버전·request_id·payload를 고정하고 얼린다", () => {
  const s = sessionWith([card(5, { version: 7 })]);
  const { attempt } = begin(s, "req-x", "hard");
  assert.deepEqual(attempt.card, { kind: "personal", id: 5, sharedDeckId: null });
  assert.deepEqual(attempt.payload, {
    rating: "hard", request_id: "req-x", session_id: "session-a", expected_card_version: 7, response_time_ms: 1200,
  });
  assert.equal(attempt.accountEpoch, 1);
  assert.equal(attempt.sessionId, "session-a");
  assert.ok(Object.isFrozen(attempt) && Object.isFrozen(attempt.payload) && Object.isFrozen(attempt.card));
});

test("미생성 구독 카드는 명시적 null 버전, 응답 시간 없음", () => {
  const s = sessionWith([lexeme(8, { version: null, isNew: true })]);
  const { attempt } = begin(s);
  assert.ok("expected_card_version" in attempt.payload);
  assert.equal(attempt.payload.expected_card_version, null);
  assert.ok(!("response_time_ms" in attempt.payload));
  assert.equal(attempt.path, "/shared-decks/9/words/8/review");
});

test("연타: 진행 중 시도가 있으면 두 번째 시작은 거절", () => {
  const { session } = begin(sessionWith([card(1)]));
  assert.deepEqual(beginAttempt(session, { rating: "good", requestId: "req-2" }), { ok: false, reason: "busy" });
  assert.ok(isSubmitting(session));
});

test("연습 카드·카드 없음·잘못된 id는 시도를 만들지 않는다", () => {
  assert.equal(beginAttempt(sessionWith([card(1, { practiceOnly: true, reviewPath: null })]), { rating: "good", requestId: "r" }).ok, false);
  assert.equal(beginAttempt(startSession(1, "s"), { rating: "good", requestId: "r" }).ok, false);
  assert.equal(beginAttempt(sessionWith([card(1)]), { rating: "good", requestId: "bad id!" }).ok, false);
  assert.throws(() => startSession(1, "space not allowed"));
});

test("성공은 진행 수·등급을 반영하고 다음 경계(재조회)로", () => {
  const s0 = sessionWith([card(1)]);
  const { session, attempt } = begin(s0);
  const r = resolveAttempt(session, attempt, success(), owner(session));
  assert.equal(r.effect, "refetch");
  assert.equal(r.session.reviewed, 1);
  assert.equal(r.session.ratings.good, 1);
  assert.equal(r.session.current, null);
  assert.equal(r.session.attempt, null);
});

test("늦은 성공: 계정 전환 뒤 도착하면 새 계정 회차를 바꾸지 않음 (P1)", () => {
  const a = sessionWith([card(1)], "session-a", 1);
  const { attempt } = begin(a);
  const b = sessionWith([card(50)], "session-b", 2); // 계정 전환 → 새 회차
  const r = resolveAttempt(b, attempt, success(), owner(b));
  assert.equal(r.effect, "ignored");
  assert.equal(r.session, b);
  assert.equal(b.current?.id, 50);
  assert.equal(b.reviewed, 0);
});

test("늦은 실패·네트워크 오류도 새 회차를 바꾸지 않음 (P2, P3)", () => {
  const a = sessionWith([card(1)], "session-a");
  const { attempt } = begin(a);
  const replaced = sessionWith([card(2)], "session-c");
  for (const outcome of [{ type: "network" as const }, { type: "http" as const, status: 409, detail: "card_version_conflict" },
    { type: "http" as const, status: 500, detail: null }]) {
    const r = resolveAttempt(replaced, attempt, outcome, owner(replaced));
    assert.equal(r.effect, "ignored");
    assert.equal(r.session, replaced);
    assert.equal(isSubmitting(r.session), false);
  }
});

test("같은 회차라도 카드가 다르면 무시", () => {
  const s = sessionWith([card(1)]);
  const { session, attempt } = begin(s);
  const moved = { ...session, current: card(2) };
  assert.equal(resolveAttempt(moved, attempt, success(), owner(moved)).effect, "ignored");
});

test("결과 미확정: 같은 시도 그대로, 자동 재시도는 1회만 (P4, P5)", () => {
  const { session, attempt } = begin(sessionWith([card(1)]));
  const first = resolveAttempt(session, attempt, { type: "network" }, owner(session));
  assert.equal(first.effect, "auto_retry");
  assert.equal(first.session.attemptStatus, "unknown");
  assert.equal(first.session.current?.id, 1);
  const retried = retryAttempt(first.session, attempt, owner(session), true);
  assert.ok(retried.ok);
  assert.equal(retried.attempt, attempt); // 같은 객체: 같은 request_id·payload
  const second = resolveAttempt(retried.session, attempt, { type: "http", status: 503, detail: null }, owner(session));
  assert.equal(second.effect, "show_retry");
  assert.equal(retryAttempt(second.session, attempt, owner(session), true).ok, false); // 자동은 더 없음
  const manual = retryAttempt(second.session, attempt, owner(session), false);
  assert.ok(manual.ok);
  assert.equal(manual.attempt.payload, attempt.payload);
  const done = resolveAttempt(manual.session, attempt, success(), owner(session));
  assert.equal(done.session.reviewed, 1);
});

test("중복 성공 응답은 진행 수·등급·미루기 집계를 한 번만", () => {
  const { session, attempt } = begin(sessionWith([card(1)]), "dup", "again");
  const once = resolveAttempt(session, attempt, success("learning"), owner(session));
  const twice = resolveAttempt(once.session, attempt, success("learning"), owner(session));
  assert.equal(twice.effect, "ignored");
  assert.equal(twice.session.reviewed, 1);
  assert.equal(twice.session.ratings.again, 1);
  assert.equal(twice.session.shortStepCounts["personal:1"], 1);
  // 같은 request_id가 어떤 이유로 다시 활성 시도가 되어도 한 번만 반영
  const forced = { ...once.session, current: card(1), attempt, attemptStatus: "sending" as const };
  assert.equal(resolveAttempt(forced, attempt, success("learning"), owner(forced)).effect, "ignored");
});

test("409 버전 충돌은 자동 재평가 없이 재조회 (P6)", () => {
  const { session, attempt } = begin(sessionWith([card(1)]));
  const r = resolveAttempt(session, attempt, { type: "http", status: 409, detail: "card_version_conflict" }, owner(session));
  assert.equal(r.effect, "refetch");
  assert.equal(r.session.attempt, null);
  assert.equal(r.session.current, null);
  assert.equal(r.session.notice, "conflict");
  assert.equal(r.session.reviewed, 0);
});

test("오류별 처리: 정지·재조회 (P7–P10)", () => {
  const cases: Array<[number, string | null, string, string | null]> = [
    [409, "request_id_conflict", "halt", "request_id_conflict"],
    [409, "srs_mode_not_fsrs", "halt", "mode_changed"],
    [409, "card_paused", "refetch", null],
    [409, "review_history_unreadable", "refetch", null],
    [409, "invalid_engine_state", "refetch", null],
    [409, "history_initialization_requires_approval", "refetch", null],
    [409, "card_identity_unknown", "refetch", null],
    [404, "word not found", "refetch", null],
    [422, "review_upgrade_required", "halt", "upgrade_required"],
    [401, "invalid token", "halt", "auth"],
    [400, "invalid review rating", "halt", "unexpected"],
  ];
  for (const [status, detail, effect, halted] of cases) {
    const { session, attempt } = begin(sessionWith([card(1)]));
    const r = resolveAttempt(session, attempt, { type: "http", status, detail }, owner(session));
    assert.equal(r.effect, effect, `${status} ${detail}`);
    assert.equal(r.session.halted, halted, `${status} ${detail}`);
    assert.equal(r.session.attempt, null);
    assert.equal(r.session.reviewed, 0);
  }
});

// ---- 큐와 카드 교체 ---------------------------------------------------------------

test("카드 표시 중에는 조회 결과로 카드를 바꾸지 않는다 (Q2)", () => {
  const s = sessionWith([card(1)]);
  const updated = fetched(s, snapshot([card(9), card(1)]));
  assert.equal(updated.current?.id, 1);
  assert.equal(updated.queue?.items[0].id, 9);
});

test("다른 회차·계정을 위해 요청한 큐 결과는 버린다", () => {
  const { session: s, ticket } = beginQueueFetch(startSession(1, "session-a"));
  assert.equal(applyQueue(s, snapshot([card(1)]), { ...ticket, sessionId: "old" }), s);
  assert.equal(applyQueue(s, snapshot([card(1)]), { ...ticket, accountEpoch: 0 }), s);
  assert.equal(applyQueueFailure(s, { ...ticket, sessionId: "old" }), s);
});

test("조회 실패는 '할 카드 없음'으로 바꾸지 않는다 (Q5)", () => {
  const s = sessionWith([card(1)]);
  const failed = fetchFailed(s);
  assert.equal(failed.current?.id, 1);
  assert.equal(sessionView(failed, NOW).primary, "card");
  const empty = fetchFailed(startSession(1, "x"));
  assert.equal(sessionView(empty, NOW).primary, "error");
});

// ---- 오래된 큐 응답 차단 (C-2b 보정 1) ------------------------------------------------

test("같은 회차 조회 두 개의 응답이 역전되면 옛 응답은 버린다", () => {
  const s0 = startSession(1, "race");
  const first = beginQueueFetch(s0);
  const second = beginQueueFetch(first.session);
  const newer = applyQueue(second.session, snapshot([], { nextDueAt: "2026-10-09T05:00:00+00:00" }), second.ticket);
  const stale = applyQueue(newer, snapshot([card(1)]), first.ticket); // 옛 조회가 늦게 도착
  assert.equal(stale, newer);
  assert.equal(stale.current, null);
  assert.equal(stale.queue?.nextDueAt, "2026-10-09T05:00:00+00:00");
  assert.equal(sessionView(stale, NOW).primary, "done");
});

test("평가 확정 뒤 도착한 옛 조회는 카드를 되살리지 않는다", () => {
  const s0 = sessionWith([card(1)]);
  const inflight = beginQueueFetch(s0); // 평가 전에 시작한 조회
  const { session, attempt } = begin(inflight.session);
  const rated = resolveAttempt(session, attempt, success(), owner(session));
  assert.equal(rated.session.current, null);
  const stale = applyQueue(rated.session, snapshot([card(1)]), inflight.ticket);
  assert.equal(stale, rated.session);
  assert.equal(stale.current, null);
  assert.equal(applyQueueFailure(rated.session, inflight.ticket), rated.session);
  // 확정 뒤 새로 시작한 조회는 반영된다
  const next = fetched(rated.session, snapshot([card(2)]));
  assert.equal(next.current?.id, 2);
});

test("충돌·정지로 끝난 평가도 이전 조회를 무효로 만든다", () => {
  for (const detail of ["card_version_conflict", "request_id_conflict"]) {
    const s0 = sessionWith([card(1)]);
    const inflight = beginQueueFetch(s0);
    const { session, attempt } = begin(inflight.session);
    const r = resolveAttempt(session, attempt, { type: "http", status: 409, detail }, owner(session));
    assert.equal(applyQueue(r.session, snapshot([card(1)]), inflight.ticket), r.session, detail);
  }
});

test("결과 미확정(네트워크)은 경계가 아니므로 조회 순번을 바꾸지 않는다", () => {
  const { session, attempt } = begin(sessionWith([card(1)]));
  const lost = resolveAttempt(session, attempt, { type: "network" }, owner(session));
  assert.equal(lost.session.queueSeq, session.queueSeq);
});

test("최신 성공 뒤 도착한 옛 실패는 오류 상태를 만들지 않는다", () => {
  const s0 = startSession(1, "fail-race");
  const first = beginQueueFetch(s0);
  const second = beginQueueFetch(first.session);
  const ok = applyQueue(second.session, snapshot([card(4)]), second.ticket);
  const late = applyQueueFailure(ok, first.ticket);
  assert.equal(late, ok);
  assert.equal(late.queueError, false);
  assert.equal(sessionView(late, NOW).primary, "card");
  // 반대로 최신 실패 뒤의 옛 성공도 집계·카드를 덮지 않는다
  const failed = applyQueueFailure(second.session, second.ticket);
  assert.equal(applyQueue(failed, snapshot([card(9)]), first.ticket), failed);
});

test("타이머·앱 복귀는 카드·시도가 있으면 조회하지 않는다 (Q2–Q4)", () => {
  const due = "2026-10-09T03:05:00+00:00";
  const showing = fetched(startSession(1, "s"), snapshot([card(1)], { nextDueAt: due }));
  assert.equal(shouldRefetchOnTimer(showing, Date.parse(due) + 1), false);
  assert.equal(shouldRefetchOnVisible(showing), false);
  assert.equal(waitDelayMs(showing, NOW), null);
  const waiting = fetched(startSession(1, "w"), snapshot([], { nextDueAt: due }));
  assert.equal(shouldRefetchOnTimer(waiting, Date.parse(due) - 1), false);
  assert.equal(shouldRefetchOnTimer(waiting, Date.parse(due)), true);
  assert.equal(waitDelayMs(waiting, NOW), 5 * 60 * 1000);
  assert.equal(shouldRefetchOnVisible(waiting), true);
});

// ---- 회차 미루기 ---------------------------------------------------------------

function rateCard(s: StudySession, c: QueueCard, id: string, phase: "learning" | "review" | "relearning") {
  const withCard = fetched({ ...s, current: null }, snapshot([c]));
  const { session, attempt } = begin(withCard, id, "again");
  return resolveAttempt(session, attempt, success(phase), owner(session));
}

test("학습·재학습 결과 3회 뒤 제외, Review 결과는 세지 않음 (D1, D4)", () => {
  let s = startSession(1, "defer");
  const c = card(7);
  s = rateCard(s, c, "a1", "learning").session;
  s = rateCard(s, c, "a2", "review").session; // 세지 않음
  s = rateCard(s, c, "a3", "relearning").session;
  assert.deepEqual(s.excluded, []);
  s = rateCard(s, c, "a4", "learning").session;
  assert.equal(DEFER_AFTER_SHORT_STEP_RESULTS, 3);
  assert.deepEqual(s.excluded, ["personal:7"]);
  assert.deepEqual(queueRequestParams(s), [["exclude_card", "personal:7"]]);
});

test("재시도·오류·조회·재렌더는 미루기 횟수를 늘리지 않음 (D2, D3)", () => {
  const s0 = sessionWith([card(3)]);
  const { session, attempt } = begin(s0, "only", "again");
  const lost = resolveAttempt(session, attempt, { type: "network" }, owner(session));
  const retried = retryAttempt(lost.session, attempt, owner(session), true);
  assert.ok(retried.ok);
  const ok = resolveAttempt(retried.session, attempt, success("learning"), owner(session));
  assert.equal(ok.session.shortStepCounts["personal:3"], 1);
  const refreshed = fetched(ok.session, snapshot([card(3)]));
  sessionView(refreshed, NOW);
  sessionView(refreshed, NOW);
  assert.equal(refreshed.shortStepCounts["personal:3"], 1);
  const conflict = begin(refreshed, "c2");
  const c = resolveAttempt(conflict.session, conflict.attempt, { type: "http", status: 409, detail: "card_version_conflict" }, owner(refreshed));
  assert.equal(c.session.shortStepCounts["personal:3"], 1);
});

test("새 회차는 미루기 집계·제외 목록을 초기화 (D5)", () => {
  let s = startSession(1, "old");
  for (const id of ["x1", "x2", "x3"]) s = rateCard(s, card(4), id, "learning").session;
  assert.deepEqual(s.excluded, ["personal:4"]);
  const fresh = startSession(1, "new");
  assert.deepEqual(fresh.excluded, []);
  assert.deepEqual(fresh.shortStepCounts, {});
});

test("100개에서 회차 정지, 기존 항목을 버리지 않음 (9-1)", () => {
  let s = startSession(1, "limit");
  const full = Array.from({ length: MAX_EXCLUDED }, (_, i) => `personal:${1000 + i}`);
  s = { ...s, excluded: full, shortStepCounts: { "lexeme:5": 2 } };
  const r = rateCard(s, lexeme(5), "over", "learning");
  assert.equal(r.effect, "halt");
  assert.equal(r.session.halted, "deferred_limit");
  assert.deepEqual(r.session.excluded, full);
  assert.equal(sessionView(r.session, NOW).primary, "deferred_limit");
  assert.equal(beginAttempt(r.session, { rating: "good", requestId: "after" }).ok, false);
});

test("미룬 카드는 큐에 다시 와도 출제하지 않음", () => {
  const s = { ...startSession(1, "skip"), excluded: ["personal:1"] };
  const applied = fetched(s, snapshot([card(1), card(2)]));
  assert.equal(applied.current?.id, 2);
});

/** 계획 목표가 적용된 정확한 범위 집계. */
function plan(daily: number, introduced: number): Partial<NewGoalInfo> {
  return {
    planDailyNew: daily, introducedInScope: introduced, introducedInScopeStatus: "exact",
    introducedInScopeAtLeast: introduced, planRemaining: Math.max(0, daily - introduced),
  };
}

// ---- 주 상태 우선순위 -------------------------------------------------------------

function view(items: QueueCard[], extra: Partial<QueueSnapshot> = {}, goal: Partial<QueueSnapshot["newGoal"]> = {}) {
  const s = startSession(1, "v");
  return sessionView(fetched(s, snapshot(items, extra, goal)), NOW);
}

test("우선순위: 카드 > 곧 돌아옴 > 미룬 카드만 > 신규 확인 불가 > 목표 달성 > 복습 끝", () => {
  assert.equal(view([card(1)], { nextDueAt: "2026-10-09T03:01:00+00:00", excludedByRequest: 3 }).primary, "card");
  assert.equal(view([], { nextDueAt: "2026-10-09T03:10:00+00:00", excludedByRequest: 3 }).primary, "soon"); // H3
  assert.equal(view([], { nextDueAt: "2026-10-09T05:00:00+00:00", excludedByRequest: 3 }).primary, "deferred_only"); // H2
  assert.equal(view([], { newAvailable: 4 }, { blockedReason: "review_time_unreadable", status: "unknown",
    introducedToday: null, accountRemaining: null }).primary, "new_unknown"); // H4
  assert.equal(view([], { newAvailable: 4 }, { accountRemaining: 0 }).primary, "goal_reached"); // H5
  assert.equal(view([], { newUnmaterialized: 2 }, { accountRemaining: 0 }).primary, "goal_reached");
  assert.equal(view([], { newAvailable: 4 }, { accountRemaining: 20, ...plan(5, 5) }).primary, "goal_reached");
  assert.equal(view([]).primary, "done"); // H6
  assert.equal(view([], { nextDueAt: "2026-10-09T03:16:00+00:00" }).primary, "done"); // 15분 밖
});

test("오류가 가장 먼저, 종료 회차는 ended", () => {
  const s = startSession(1, "e");
  assert.equal(sessionView({ ...s, halted: "auth" }, NOW).primary, "error");
  assert.equal(sessionView(endSession(s), NOW).primary, "ended");
  assert.equal(sessionView(s, NOW).primary, "loading");
});

test("보조 줄: 옮겨지지 않은 단어 안내", () => {
  assert.equal(view([], { notMigrated: 2 }).notMigratedNote, true);
  assert.equal(view([]).notMigratedNote, false);
});

test("상태 이름에 학습 완료가 없다 (H7)", () => {
  const states = ["error", "card", "soon", "deferred_only", "deferred_limit", "new_unknown", "goal_reached", "done", "loading", "ended"];
  for (const name of states) assert.ok(!/complete|mastered|학습 완료/.test(name));
});

// ---- 활성 회차와 교체 보호 ---------------------------------------------------------

test("대기 중 회차도 활성, 종료한 회차만 비활성 (L1–L3)", () => {
  const waiting = fetched(startSession(1, "w"), snapshot([], { nextDueAt: "2026-10-09T03:05:00+00:00" }));
  assert.equal(isActiveSession(waiting), true);
  assert.equal(replaceGuard(waiting), "confirm");
  const deferred = { ...waiting, halted: "deferred_limit" as const };
  assert.equal(isActiveSession(deferred), true);
  assert.equal(isActiveSession(endSession(waiting)), false);
  assert.equal(replaceGuard(endSession(waiting)), "free");
  assert.equal(replaceGuard(null), "free");
});

test("교체 보호: 전송 중 대기, 결과 미확정은 경고와 함께 확인 (L4, P2)", () => {
  const { session, attempt } = begin(sessionWith([card(1)]));
  assert.equal(replaceGuard(session), "wait");
  const unknown = resolveAttempt(session, attempt, { type: "network" }, owner(session)).session;
  assert.equal(replaceGuard(unknown), "confirm_unsaved");
});

test("beforeunload는 전송 중·결과 미확정일 때만 (P12)", () => {
  const s = sessionWith([card(1)]);
  assert.equal(shouldWarnBeforeUnload(s), false);
  const { session, attempt } = begin(s);
  assert.equal(shouldWarnBeforeUnload(session), true);
  const unknown = resolveAttempt(session, attempt, { type: "network" }, owner(session)).session;
  assert.equal(shouldWarnBeforeUnload(unknown), true);
  const done = resolveAttempt(unknown, attempt, success(), owner(session)).session;
  assert.equal(shouldWarnBeforeUnload(done), false);
});

// ---- 신규 수 표시 -----------------------------------------------------------------

function goalInfo(extra: Partial<NewGoalInfo>): NewGoalInfo {
  return snapshot([], {}, extra).newGoal;
}

test("신규 수 null·unknown을 0으로 바꾸지 않음 (M10)", () => {
  const unknown = newGoalDisplay(goalInfo({ status: "unknown", introducedToday: null, introducedAtLeast: 4,
    accountRemaining: null, blockedReason: "review_time_unreadable" }));
  assert.deepEqual(unknown, { kind: "unknown", basis: "account", atLeast: 4, goal: 20 });
  const exact = newGoalDisplay(goalInfo({}));
  assert.deepEqual(exact, { kind: "exact", basis: "account", introduced: 0, goal: 20, remaining: 20 });
});

// ---- 실제 신규 허용량 = min(계정 잔여, 계획 잔여) (C-2b 보정 2) -------------------------

test("계정 잔여 0 / 계획 잔여 5: 목표 달성, 표시는 계정 기준", () => {
  const goal = { introducedToday: 20, introducedAtLeast: 20, accountRemaining: 0, ...plan(5, 0) };
  assert.equal(effectiveNewRemaining(goalInfo(goal)), 0);
  assert.equal(view([], { newAvailable: 4 }, goal).primary, "goal_reached");
  assert.deepEqual(newGoalDisplay(goalInfo(goal)), { kind: "exact", basis: "account", introduced: 20, goal: 20, remaining: 0 });
});

test("계정 잔여 5 / 계획 잔여 0: 목표 달성, 표시는 계획 기준", () => {
  const goal = { introducedToday: 15, introducedAtLeast: 15, accountRemaining: 5, ...plan(6, 6) };
  assert.equal(effectiveNewRemaining(goalInfo(goal)), 0);
  assert.equal(view([], { newUnmaterialized: 2 }, goal).primary, "goal_reached");
  assert.deepEqual(newGoalDisplay(goalInfo(goal)), { kind: "exact", basis: "plan", introduced: 6, goal: 6, remaining: 0 });
});

test("계정 잔여 3 / 계획 잔여 7: 실제 허용 3, 표시는 계정 기준으로 일치", () => {
  const goal = { introducedToday: 17, introducedAtLeast: 17, accountRemaining: 3, ...plan(10, 3) };
  assert.equal(effectiveNewRemaining(goalInfo(goal)), 3);
  assert.equal(view([], { newAvailable: 4 }, goal).primary, "done");
  const shown = newGoalDisplay(goalInfo(goal));
  assert.deepEqual(shown, { kind: "exact", basis: "account", introduced: 17, goal: 20, remaining: 3 });
  // 표시한 목표·실적·잔여가 서로 맞는다
  assert.ok(shown && shown.kind === "exact" && shown.goal - shown.introduced === shown.remaining);
});

test("계획 없음이면 계정 잔여만, 신규 후보가 없으면 목표 달성이 아님", () => {
  assert.equal(effectiveNewRemaining(goalInfo({ accountRemaining: 4 })), 4);
  assert.equal(view([], {}, { accountRemaining: 0 }).primary, "done");
});

test("확인 불가는 null로 남고 목표 달성으로 바꾸지 않는다", () => {
  const accountUnknown = { status: "unknown" as const, introducedToday: null, introducedAtLeast: 2,
    accountRemaining: null, blockedReason: "review_time_unreadable", ...plan(5, 0) };
  assert.equal(effectiveNewRemaining(goalInfo(accountUnknown)), null);
  assert.deepEqual(newGoalDisplay(goalInfo(accountUnknown)), { kind: "unknown", basis: "account", atLeast: 2, goal: 20 });
  const scopeUnknown = { accountRemaining: 0, planDailyNew: 5, introducedInScope: null,
    introducedInScopeStatus: "unknown" as const, introducedInScopeAtLeast: 1, planRemaining: null,
    blockedReason: "review_time_unreadable" };
  assert.equal(effectiveNewRemaining(goalInfo(scopeUnknown)), null);
  assert.deepEqual(newGoalDisplay(goalInfo(scopeUnknown)), { kind: "unknown", basis: "plan", atLeast: 1, goal: 5 });
  assert.equal(view([], { newAvailable: 3 }, scopeUnknown).primary, "new_unknown");
});

test("응답 해석: null 신규 수와 null 카드 버전을 유지", () => {
  const parsed = parseQueueResponse({
    server_now: "2026-10-09T03:00:00+00:00", seoul_date: "2026-10-09", next_due_at: null,
    items: [{ card_kind: "lexeme", card_id: 8, card_version: null, materialized: false, is_new: true, practice_only: false,
      review: { method: "POST", path: "/shared-decks/9/words/8/review", shared_deck_id: 9 } }],
    counts: { new_available: 1, new_unmaterialized: 1, excluded_by_request: 0, not_converted: 2, invalid_state: 1 },
    new_goal: { introduced_today: null, introduced_today_status: "unknown", introduced_today_at_least: 3,
      account_remaining: null, plan_remaining: null, new_blocked_reason: "review_time_unreadable", account_daily_goal: 20 },
  });
  assert.ok(parsed);
  assert.equal(parsed.items[0].version, null);
  assert.equal(parsed.items[0].sharedDeckId, 9);
  assert.equal(parsed.newGoal.introducedToday, null);
  assert.equal(parsed.newGoal.accountRemaining, null);
  assert.equal(parsed.notMigrated, 3);
  assert.equal(parseQueueResponse({ items: "x" }), null);
  assert.equal(cardKey(parsed.items[0]), "lexeme:8");
});

// ---- 응답 해석 방어 (C-2b 보정 3) -----------------------------------------------------

function rawItem(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    card_kind: "personal", card_id: 5, card_version: 3, materialized: true, is_new: false, practice_only: false,
    review: { method: "POST", path: "/study-items/5/review", shared_deck_id: null }, ...extra,
  };
}

function rawResponse(items: unknown[], extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    server_now: "2026-10-09T03:00:00+00:00", seoul_date: "2026-10-09", next_due_at: null, items,
    counts: { new_available: 0, new_unmaterialized: 0, excluded_by_request: 0 },
    new_goal: { account_daily_goal: 20, introduced_today: 0, introduced_today_status: "exact",
      introduced_today_at_least: 0, account_remaining: 20, plan_daily_new: null, introduced_today_in_scope: null,
      introduced_today_in_scope_status: null, introduced_today_in_scope_at_least: null, plan_remaining: null,
      new_blocked_reason: null },
    ...extra,
  };
}

const LEXEME_REVIEW = { method: "POST", path: "/shared-decks/9/words/8/review", shared_deck_id: 9 };

test("U6: 엔진 상태 없는 불완전 이력 복습 카드는 신규·미생성 카드가 아닌 복습 카드로 해석", () => {
  // backend/app/srs/queue.py _item()이 U5 전환 카드에 내보내는 모양 그대로(test_srs_d2_serve.py와 같은 필드).
  const personal = rawItem({
    card_id: 7, card_version: 1, bucket: "review_due", srs: null, config_version: "fsrs-6.3.2-a1-362bc5407f76",
    participation: "active", sort_key: [1, "2026-10-09T02:00:00+00:00", 0, 0, 7],
    review: { method: "POST", path: "/study-items/7/review", shared_deck_id: null },
  });
  const lexeme = rawItem({
    card_kind: "lexeme", card_id: 8, card_version: 1, bucket: "review_due", srs: null,
    review: LEXEME_REVIEW, participation: "active",
  });
  const parsed = parseQueueResponse(rawResponse([personal, lexeme]));
  assert.ok(parsed);
  for (const item of parsed.items) {
    assert.equal(item.isNew, false);
    assert.equal(item.version, 1); // 미생성 구독 카드(null)가 아님
    assert.ok(item.reviewPath);
    assert.equal(item.practiceOnly, false);
  }
});

test("정상 응답과 계획 집계 해석", () => {
  const parsed = parseQueueResponse(rawResponse([rawItem()]));
  assert.ok(parsed);
  assert.equal(parsed.items[0].version, 3);
  const withPlan = rawResponse([], { new_goal: { ...(rawResponse([]).new_goal as object), plan_daily_new: 5,
    introduced_today_in_scope: 2, introduced_today_in_scope_status: "exact", introduced_today_in_scope_at_least: 2,
    plan_remaining: 3 } });
  const goal = parseQueueResponse(withPlan)?.newGoal;
  assert.equal(goal?.planDailyNew, 5);
  assert.equal(goal?.introducedInScope, 2);
  assert.equal(goal?.planRemaining, 3);
});

test("null·원시값 항목은 예외 없이 해석 실패", () => {
  for (const bad of [null, 7, "x", true, [], undefined]) {
    assert.doesNotThrow(() => parseQueueResponse(rawResponse([bad])));
    assert.equal(parseQueueResponse(rawResponse([bad])), null, String(bad));
  }
  for (const raw of [null, 3, "x", [], {}]) assert.equal(parseQueueResponse(raw), null);
});

test("잘못된 카드 ID·종류는 해석 실패", () => {
  for (const id of [0, -1, 1.5, "5", null, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(parseQueueResponse(rawResponse([rawItem({ card_id: id })])), null, String(id));
  }
  assert.equal(parseQueueResponse(rawResponse([rawItem({ card_kind: "deck" })])), null);
});

test("잘못된 버전을 null(구독 최초 평가)로 바꾸지 않는다", () => {
  for (const version of ["7", -1, 1.5, true, {}]) {
    assert.equal(parseQueueResponse(rawResponse([rawItem({ card_version: version })])), null, String(version));
  }
  const missing = rawItem();
  delete missing.card_version;
  assert.equal(parseQueueResponse(rawResponse([missing])), null);
  // 개인 카드의 null, 생성된 구독 카드의 null도 거부
  assert.equal(parseQueueResponse(rawResponse([rawItem({ card_version: null })])), null);
  assert.equal(parseQueueResponse(rawResponse([rawItem({ card_kind: "lexeme", card_id: 8, card_version: null,
    materialized: true, review: LEXEME_REVIEW })])), null);
});

test("정상 미생성 구독 카드의 명시적 null 버전은 유지", () => {
  const parsed = parseQueueResponse(rawResponse([rawItem({ card_kind: "lexeme", card_id: 8, card_version: null,
    materialized: false, is_new: true, review: LEXEME_REVIEW })]));
  assert.ok(parsed);
  assert.equal(parsed.items[0].version, null);
  assert.equal(parsed.items[0].sharedDeckId, 9);
  const started = beginAttempt(fetched(startSession(1, "p"), parsed), { rating: "good", requestId: "r1" });
  assert.ok(started.ok);
  assert.equal(started.attempt.payload.expected_card_version, null);
});

test("잘못된 응답 구조는 해석 실패", () => {
  const goal = rawResponse([]).new_goal as Record<string, unknown>;
  const cases: Array<Record<string, unknown>> = [
    rawResponse([rawItem({ review: null })]), // 연습 아닌데 경로 없음
    rawResponse([rawItem({ review: { path: "study-items/5" } })]),
    rawResponse([rawItem({ card_kind: "lexeme", review: { path: "/shared-decks/9/words/5/review", shared_deck_id: "9" } })]),
    rawResponse([], { counts: { new_available: -1 } }),
    rawResponse([], { counts: null }),
    rawResponse([], { server_now: null }),
    rawResponse([], { new_goal: null }),
    rawResponse([], { new_goal: { ...goal, introduced_today_status: "exact", introduced_today: null } }),
    rawResponse([], { new_goal: { ...goal, account_remaining: "3" } }),
    rawResponse([], { new_goal: { ...goal, plan_remaining: -2 } }),
  ];
  for (const raw of cases) {
    assert.doesNotThrow(() => parseQueueResponse(raw));
    assert.equal(parseQueueResponse(raw), null, JSON.stringify(raw).slice(0, 120));
  }
});

// ---- C-2c 연결용 보강: 조회 대기 표시, 조회 오류 정지, 실패 뒤 타이머 없음 ----------------

test("다음 카드를 받는 동안 이전 큐로 '복습 끝'을 보이지 않는다", () => {
  const { session, attempt } = begin(sessionWith([card(1)]));
  const rated = resolveAttempt(session, attempt, success(), owner(session)).session;
  const pending = beginQueueFetch(rated);
  assert.equal(pending.session.queuePending, true);
  assert.equal(sessionView(pending.session, NOW).primary, "loading");
  const done = applyQueue(pending.session, snapshot([]), pending.ticket);
  assert.equal(done.queuePending, false);
  assert.equal(sessionView(done, NOW).primary, "done");
});

test("평가 확정은 진행 중 조회 대기도 끝낸다(옛 조회 무효)", () => {
  const inflight = beginQueueFetch(sessionWith([card(1)]));
  const { session, attempt } = begin(inflight.session);
  const rated = resolveAttempt(session, attempt, success(), owner(session)).session;
  assert.equal(rated.queuePending, false);
});

test("조회 오류 정지는 최신 티켓만 반영", () => {
  const first = beginQueueFetch(startSession(1, "halt"));
  const second = beginQueueFetch(first.session);
  assert.equal(applyQueueHalt(second.session, first.ticket, "mode_changed"), second.session);
  const halted = applyQueueHalt(second.session, second.ticket, "mode_changed");
  assert.equal(halted.halted, "mode_changed");
  assert.equal(sessionView(halted, NOW).primary, "error");
  const limit = applyQueueHalt(beginQueueFetch(startSession(1, "lim")).session,
    beginQueueFetch(startSession(1, "lim")).ticket, "deferred_limit");
  assert.equal(sessionView(limit, NOW).primary, "deferred_limit");
});

test("조회 실패 뒤에는 타이머로 다시 조회하지 않는다(반복 루프 없음)", () => {
  const due = "2026-10-09T03:05:00+00:00";
  const waiting = fetched(startSession(1, "loop"), snapshot([], { nextDueAt: due }));
  assert.equal(shouldRefetchOnTimer(waiting, Date.parse(due) + 1), true);
  const failed = fetchFailed(waiting);
  assert.equal(shouldRefetchOnTimer(failed, Date.parse(due) + 1), false);
  assert.equal(waitDelayMs(failed, NOW), null);
  const inflight = beginQueueFetch(waiting).session;
  assert.equal(shouldRefetchOnTimer(inflight, Date.parse(due) + 1), false);
});

// ---- C-2c 보정: 출제 차례 ------------------------------------------------------------

test("같은 카드가 다시 놓이면 새 출제 차례, 재시도는 같은 차례", () => {
  const s0 = sessionWith([card(1)]);
  const firstKey = presentationKey(s0);
  assert.ok(firstKey);
  const { session, attempt } = begin(s0, "turn-1", "again");
  const lost = resolveAttempt(session, attempt, { type: "network" }, owner(session));
  assert.equal(presentationKey(lost.session), firstKey, "재시도 중에는 차례 그대로");
  const done = resolveAttempt(lost.session, attempt, success("learning"), owner(session)).session;
  assert.equal(presentationKey(done), null);
  const back = fetched(done, snapshot([card(1, { version: 4 })]));
  assert.equal(back.current?.id, 1);
  assert.notEqual(presentationKey(back), firstKey, "같은 카드여도 새 차례");
  // 카드가 보이는 동안의 조회는 차례를 바꾸지 않는다
  assert.equal(presentationKey(fetched(back, snapshot([card(1, { version: 4 })]))), presentationKey(back));
});
