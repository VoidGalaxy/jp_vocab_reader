// FSRS 회차 컨트롤러·학습 계획 실행기 연결 회귀 테스트 (Gate C-2c 보정).
// 실행: node --test components/fsrsStudyController.test.mts
// 실제 studySession·fsrsStudy·planStudyLauncher 모듈을 그대로 쓰고, 요청·시계·타이머만 가짜로 둔다.
// 브라우저 확인은 REPORT에 따로 적는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as studySession from "./studySession.ts";
import { pendingLaterCount, queueFailureKind, queuePath, studyCardFromQueueItem } from "./fsrsStudy.ts";
import type { FetchResult, QueueTarget } from "./fsrsStudy.ts";
import { createFsrsStudyController } from "./fsrsStudyController.ts";
import type { PreparedSession } from "./fsrsStudyController.ts";
import { createPlanStudyLauncher } from "./planStudyLauncher.ts";
import type { PlanStudyTarget, StudySessionSnapshot } from "./planStudyLauncher.ts";

const T0 = Date.parse("2026-10-10T03:00:00+00:00");

type Pending = { path: string; body?: unknown; resolve: (result: FetchResult) => void };

function harness(epochStart = 1) {
  let now = T0;
  let epoch = epochStart;
  let ids = 0;
  const gets: Pending[] = [];
  const posts: Pending[] = [];
  const timers: Array<{ ms: number; fn: () => void }> = [];
  let renders = 0;
  const controller = createFsrsStudyController(
    { session: studySession, helpers: { pendingLaterCount, queueFailureKind, queuePath, studyCardFromQueueItem } },
    {
      getAccountEpoch: () => epoch,
      get: (path) => new Promise((resolve) => gets.push({ path, resolve })),
      post: (path, body) => new Promise((resolve) => posts.push({ path, body, resolve })),
      loadRecentPracticeCards: async () => [],
      onReviewSaved: () => {},
      onModeChanged: () => {},
    },
    {
      now: () => now,
      newId: () => `id-${++ids}`,
      setTimeout: (fn, ms) => timers.push({ ms, fn }),
      onChange: () => { renders += 1; },
    },
  );
  return {
    controller,
    gets,
    posts,
    timers,
    get renders() { return renders; },
    advance(ms: number) { now += ms; },
    now: () => now,
    setEpoch(value: number) { epoch = value; },
  };
}

async function flush() {
  for (let i = 0; i < 5; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

function item(kind: "personal" | "lexeme", id: number, version: number | null, isNew = false) {
  return {
    card_kind: kind,
    card_id: id,
    card_version: version,
    materialized: version !== null,
    is_new: isNew,
    practice_only: false,
    status: "unknown",
    source_label: kind === "personal" ? "QA 개인" : "QA 구독 덱",
    review: kind === "personal"
      ? { method: "POST", path: `/study-items/${id}/review`, shared_deck_id: null }
      : { method: "POST", path: `/shared-decks/9/words/${id}/review`, shared_deck_id: 9 },
    content: { surface: `w${id}`, base_form: `w${id}`, reading: "", meaning_ko: `뜻${id}` },
  };
}

function queueBody(items: unknown[], options: { nextDueAt?: string | null; goal?: Record<string, unknown>; counts?: Record<string, number>; serverNow?: number } = {}) {
  return {
    server_now: new Date(options.serverNow ?? T0).toISOString(),
    seoul_date: "2026-10-10",
    next_due_at: options.nextDueAt ?? null,
    items,
    counts: { new_available: 0, new_unmaterialized: 0, excluded_by_request: 0, ...(options.counts ?? {}) },
    new_goal: {
      account_daily_goal: 20, introduced_today: 0, introduced_today_status: "exact", introduced_today_at_least: 0,
      account_remaining: 20, plan_daily_new: null, introduced_today_in_scope: null,
      introduced_today_in_scope_status: null, introduced_today_in_scope_at_least: null, plan_remaining: null,
      new_blocked_reason: null, ...(options.goal ?? {}),
    },
  };
}

const ok = (body: unknown): FetchResult => ({ kind: "ok", body });
const learning = (version: number) => ok({ srs: { state: { phase: "learning" }, card_version: version } });
const TODAY: QueueTarget = { scope: "all", kind: "review", mode: "today", planDailyNew: null };

async function startWith(h: ReturnType<typeof harness>, items: unknown[], target: QueueTarget = TODAY) {
  h.controller.start(target);
  assert.equal(h.gets.length, 1);
  h.gets.shift()!.resolve(ok(queueBody(items)));
  await flush();
}

// ---- 1. 재등장 카드의 정답 공개 초기화 ---------------------------------------------------

for (const [label, first, again] of [
  ["개인 카드", item("personal", 1, 0, true), item("personal", 1, 1)],
  ["미생성 구독 카드", item("lexeme", 8, null, true), item("lexeme", 8, 1)],
] as const) {
  test(`${label}: Again → 대기 → 같은 카드 재등장은 질문부터, 응답 시간 기준 초기화`, async () => {
    const h = harness();
    await startWith(h, [first]);
    h.controller.showAnswer();
    assert.equal(h.controller.snapshot().isAnswerVisible, true);
    h.advance(4000);
    h.controller.rate("again");
    const sent = h.posts.shift()!;
    assert.equal((sent.body as { response_time_ms?: number }).response_time_ms ?? null, first.card_kind === "personal" ? 4000 : null);
    sent.resolve(learning(1));
    await flush();
    // 평가 뒤 조회: 같은 카드가 1분 뒤 돌아온다(대기 화면)
    h.gets.shift()!.resolve(ok(queueBody([], { nextDueAt: new Date(T0 + 64_000).toISOString() })));
    await flush();
    assert.equal(h.controller.snapshot().view?.primary, "soon");
    // 대기 타이머 도래 → 같은 카드 재등장
    const timer = h.controller.waitTimer();
    assert.ok(timer);
    h.advance(timer.delay); // 타이머가 실제로 기다리는 만큼
    timer.fire();
    h.gets.shift()!.resolve(ok(queueBody([again], { serverNow: h.now() })));
    await flush();
    const snap = h.controller.snapshot();
    assert.equal(snap.card?.surface, first.content.surface);
    assert.equal(snap.isAnswerVisible, false, "새 출제 차례는 질문부터");
    // 정답을 다시 보지 않고 평가하면 응답 시간 없음(이전 공개 시각을 쓰지 않음)
    h.advance(10_000);
    h.controller.rate("good");
    const second = h.posts.shift()!;
    assert.equal((second.body as { response_time_ms?: number | null }).response_time_ms ?? null, null);
  });
}

test("새 차례에서 정답을 다시 보면 그 시각부터 응답 시간을 잰다", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 0, true)]);
  h.controller.showAnswer();
  h.advance(9000);
  h.controller.rate("again");
  h.posts.shift()!.resolve(learning(1));
  await flush();
  h.advance(60_000);
  h.gets.shift()!.resolve(ok(queueBody([item("personal", 1, 1)], { serverNow: h.now() })));
  await flush();
  assert.equal(h.controller.snapshot().isAnswerVisible, false);
  h.controller.showAnswer();
  h.advance(2500);
  h.controller.rate("good");
  assert.equal((h.posts.shift()!.body as { response_time_ms: number }).response_time_ms, 2500);
});

test("같은 시도의 네트워크 재시도는 카드·정답·고정 payload를 유지한다", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 0, true)]);
  h.controller.showAnswer();
  h.advance(3000);
  h.controller.rate("hard");
  const first = h.posts.shift()!;
  first.resolve({ kind: "network" });
  await flush();
  let snap = h.controller.snapshot();
  assert.equal(snap.session?.attemptStatus, "unknown");
  assert.equal(snap.isAnswerVisible, true);
  assert.equal(snap.card?.id, 1);
  h.advance(5000);
  assert.equal(h.timers.length, 1);
  h.timers.shift()!.fn(); // 자동 재시도 1회
  const retried = h.posts.shift()!;
  assert.equal(retried.body, first.body, "같은 payload 객체 그대로");
  assert.equal(retried.path, first.path);
  retried.resolve({ kind: "http", status: 503, detail: null });
  await flush();
  snap = h.controller.snapshot();
  assert.equal(snap.isAnswerVisible, true);
  assert.equal(h.timers.length, 0, "자동 재시도는 1회뿐");
  h.controller.retryNow(); // 수동
  const manual = h.posts.shift()!;
  assert.equal(manual.body, first.body);
  assert.equal(h.controller.snapshot().isAnswerVisible, true);
});

test("409 충돌 뒤 재조회로 같은 카드가 와도 질문부터", async () => {
  const h = harness();
  await startWith(h, [item("lexeme", 8, null, true)]);
  h.controller.showAnswer();
  h.controller.rate("good");
  h.posts.shift()!.resolve({ kind: "http", status: 409, detail: "card_version_conflict" });
  await flush();
  assert.equal(h.posts.length, 0, "자동 재평가 없음");
  h.gets.shift()!.resolve(ok(queueBody([item("lexeme", 8, 1)])));
  await flush();
  const snap = h.controller.snapshot();
  assert.equal(snap.card?.lexeme_id, 8);
  assert.equal(snap.isAnswerVisible, false);
  assert.equal(snap.session?.notice, "conflict");
});

// ---- 2. 학습 계획 교체: 준비 → 검증 → 교체 ---------------------------------------------

const PLAN: QueueTarget = { scope: "personal_deck", deckId: 9, kind: "review", mode: "new", planDailyNew: 2 };

test("준비는 새 회차 티켓으로 따로 받고, 교체 전까지 기존 회차를 건드리지 않는다", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3)]);
  const before = h.controller.getSession();
  const preparing = h.controller.prepare(PLAN);
  assert.equal(h.gets.length, 1);
  assert.ok(h.gets[0].path.includes("plan_daily_new=2"));
  h.gets.shift()!.resolve(ok(queueBody([item("personal", 20, 0, true), item("personal", 21, 0, true)],
    { goal: { plan_daily_new: 2, introduced_today_in_scope: 0, introduced_today_in_scope_status: "exact",
      introduced_today_in_scope_at_least: 0, plan_remaining: 2 }, counts: { new_available: 2 } })));
  const prepared = await preparing;
  assert.ok(prepared);
  assert.equal(h.controller.getSession(), before, "기존 회차 그대로");
  assert.equal(h.controller.snapshot().card?.id, 1);
  assert.notEqual(prepared.session.sessionId, before?.sessionId);
  assert.equal(prepared.session.current?.id, 20);
  assert.deepEqual(prepared.session.excluded, []);
  assert.equal(prepared.session.queue?.newGoal.planRemaining, 2);
  assert.equal(h.controller.emptyReason(prepared), null);
  assert.equal(h.controller.adopt(prepared), true);
  const snap = h.controller.snapshot();
  assert.equal(snap.card?.id, 20);
  assert.equal(snap.card?.meaning_ko, "뜻20");
  assert.equal(snap.isAnswerVisible, false);
  assert.equal(snap.view?.newGoal?.basis, "plan");
  assert.equal(h.gets.length, 0, "교체 뒤 다시 조회하지 않는다");
});

test("준비 실패·해석 실패는 null, 기존 회차 보존", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3)]);
  const before = h.controller.getSession();
  for (const result of [{ kind: "http", status: 503, detail: null } as FetchResult, { kind: "network" } as FetchResult,
    ok({ items: [null] }), ok(queueBody([{ ...item("personal", 5, 0), content: null }]))]) {
    const preparing = h.controller.prepare(PLAN);
    h.gets.shift()!.resolve(result);
    assert.equal(await preparing, null, JSON.stringify(result).slice(0, 60));
    assert.equal(h.controller.getSession(), before);
  }
});

test("빈 준비 회차의 원인: 목표 달성·신규 확인 불가·카드 없음", async () => {
  const h = harness();
  const cases: Array<[Record<string, unknown>, Record<string, number>, string]> = [
    [{ plan_daily_new: 2, introduced_today_in_scope: 2, introduced_today_in_scope_status: "exact",
      introduced_today_in_scope_at_least: 2, plan_remaining: 0 }, { new_available: 3 }, "goal_reached"],
    [{ introduced_today: null, introduced_today_status: "unknown", account_remaining: null,
      new_blocked_reason: "review_time_unreadable" }, { new_available: 3 }, "new_unknown"],
    [{}, {}, "no_cards"],
  ];
  for (const [goal, counts, reason] of cases) {
    const preparing = h.controller.prepare(PLAN);
    h.gets.shift()!.resolve(ok(queueBody([], { goal, counts })));
    const prepared = await preparing;
    assert.ok(prepared);
    assert.equal(h.controller.emptyReason(prepared), reason);
  }
});

test("교체 거절: 계정이 바뀌었거나 기존 평가가 전송 중이면 false, 기존 회차 그대로", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3)]);
  const preparing = h.controller.prepare(PLAN);
  h.gets.shift()!.resolve(ok(queueBody([item("personal", 20, 0, true)])));
  const prepared = (await preparing)!;
  h.controller.rate("good"); // 전송 중
  const sending = h.controller.getSession();
  assert.equal(h.controller.adopt(prepared), false);
  assert.equal(h.controller.getSession(), sending);
  h.posts.shift()!.resolve(ok({ srs: { state: { phase: "review" } } }));
  await flush();
  h.setEpoch(2);
  assert.equal(h.controller.adopt(prepared), false, "다른 계정의 준비 회차");
});

// ---- 실행기 연결 ------------------------------------------------------------------

type PlanItem = { fsrsPrepared: PreparedSession };

function fingerprint(session: ReturnType<typeof studySession.startSession> | null): number {
  if (!session) return 0;
  const parts = `${session.sessionId}|${session.status}|${session.reviewed}|${session.presentation}|${session.attempt ? session.attempt.requestId : ""}|${session.attemptStatus ?? ""}`;
  let hash = 5381;
  for (let i = 0; i < parts.length; i += 1) hash = ((hash * 33) ^ parts.charCodeAt(i)) >>> 0;
  return hash;
}

function launcherFor(h: ReturnType<typeof harness>) {
  let epochRef = 1;
  const adapter = {
    getSession: (): StudySessionSnapshot => {
      const guard = h.controller.replaceGuard();
      return { id: 1, position: fingerprint(h.controller.getSession()), inProgress: guard !== "free", remaining: 0,
        guard: guard === "free" ? undefined : guard };
    },
    getAccountEpoch: () => epochRef,
    fetchQueue: async (): Promise<PlanItem[]> => {
      const prepared = await h.controller.prepare(PLAN);
      if (!prepared) throw new Error("failed");
      return [{ fsrsPrepared: prepared }];
    },
    emptyReason: (items: PlanItem[]) => h.controller.emptyReason(items[0].fsrsPrepared),
    replaceSession: (_target: PlanStudyTarget, items: PlanItem[]) => h.controller.adopt(items[0].fsrsPrepared),
    resumeSession: () => {},
  };
  return { launcher: createPlanStudyLauncher<PlanItem>(adapter), bumpEpoch: () => { epochRef += 1; h.setEpoch(epochRef); } };
}

const PLAN_TARGET: PlanStudyTarget = { deck: { kind: "personal", id: 9 }, mode: "new", dailyNew: 2 };

async function confirmAndReplace(h: ReturnType<typeof harness>, launcher: ReturnType<typeof launcherFor>["launcher"],
  respond: ((pending: Pending) => void) | null, between?: () => Promise<void> | void) {
  const first = await launcher.start(PLAN_TARGET);
  assert.equal(first.kind, "needsConfirm");
  const running = launcher.replace(PLAN_TARGET, (first as { session: StudySessionSnapshot }).session);
  await flush();
  if (between) await between();
  if (respond) respond(h.gets.shift()!);
  return running;
}

test("실행기: 교체 성공은 조회 1회, 실제 교체 뒤에만 started", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3)]);
  const { launcher } = launcherFor(h);
  const outcome = await confirmAndReplace(h, launcher, (p) => p.resolve(ok(queueBody([item("personal", 20, 0, true)]))));
  assert.deepEqual(outcome, { kind: "started", count: 1 });
  assert.equal(h.controller.snapshot().card?.id, 20);
  assert.equal(h.gets.length, 0, "검증한 응답을 버리고 다시 조회하지 않는다");
});

test("실행기: 실패·빈 큐(원인 포함)·해석 실패는 기존 회차 보존", async () => {
  for (const [result, kind, reason] of [
    [{ kind: "http", status: 503, detail: null } as FetchResult, "failed", undefined],
    [ok({ items: "x" }), "failed", undefined],
    [ok(queueBody([], { goal: { plan_daily_new: 2, introduced_today_in_scope: 2, introduced_today_in_scope_status: "exact",
      introduced_today_in_scope_at_least: 2, plan_remaining: 0 }, counts: { new_available: 1 } })), "empty", "goal_reached"],
    [ok(queueBody([], { goal: { introduced_today: null, introduced_today_status: "unknown", account_remaining: null,
      new_blocked_reason: "review_time_unreadable" }, counts: { new_available: 1 } })), "empty", "new_unknown"],
    [ok(queueBody([])), "empty", "no_cards"],
  ] as const) {
    const h = harness();
    await startWith(h, [item("personal", 1, 3)]);
    const before = h.controller.getSession();
    const { launcher } = launcherFor(h);
    const outcome = await confirmAndReplace(h, launcher, (p) => p.resolve(result));
    assert.equal(outcome.kind, kind);
    if (reason) assert.equal((outcome as { reason?: string }).reason, reason);
    assert.equal(h.controller.getSession(), before);
    assert.equal(h.controller.snapshot().card?.id, 1);
  }
});

test("실행기: 준비 중 취소·계정 변경·기존 회차 진행이면 교체하지 않는다", async () => {
  // 취소
  {
    const h = harness();
    await startWith(h, [item("personal", 1, 3)]);
    const before = h.controller.getSession();
    const { launcher } = launcherFor(h);
    const outcome = await confirmAndReplace(h, launcher, (p) => p.resolve(ok(queueBody([item("personal", 20, 0)]))),
      () => { launcher.cancel(); });
    assert.equal(outcome.kind, "cancelled");
    assert.equal(h.controller.getSession(), before);
  }
  // 계정 변경
  {
    const h = harness();
    await startWith(h, [item("personal", 1, 3)]);
    const before = h.controller.getSession();
    const { launcher, bumpEpoch } = launcherFor(h);
    const outcome = await confirmAndReplace(h, launcher, (p) => p.resolve(ok(queueBody([item("personal", 20, 0)]))), bumpEpoch);
    assert.equal(outcome.kind, "stale");
    assert.equal(h.controller.getSession(), before);
  }
  // 준비하는 동안 기존 회차에서 평가 진행
  {
    const h = harness();
    await startWith(h, [item("personal", 1, 3), item("personal", 2, 3)]);
    const { launcher } = launcherFor(h);
    const outcome = await confirmAndReplace(h, launcher, (p) => p.resolve(ok(queueBody([item("personal", 20, 0)]))),
      async () => {
        h.controller.rate("good");
        h.posts.shift()!.resolve(ok({ srs: { state: { phase: "review" } } }));
        await flush();
      });
    assert.equal(outcome.kind, "sessionChanged");
    // 기존 회차는 계속: 평가 뒤 조회가 다음 카드를 가져온다
    h.gets.shift()!.resolve(ok(queueBody([item("personal", 2, 3)])));
    await flush();
    assert.equal(h.controller.snapshot().card?.id, 2);
    assert.equal(h.controller.getSession()?.reviewed, 1);
  }
});

test("실행기: 교체 시점에 평가가 전송 중이면 started 아님, 기존 회차·시도 보존", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3)]);
  const { launcher } = launcherFor(h);
  // 확인창을 띄운 뒤(전송 전) 평가를 시작하고, 준비 응답이 오면 교체 시도
  const first = await launcher.start(PLAN_TARGET);
  assert.equal(first.kind, "needsConfirm");
  const expected = (first as { session: StudySessionSnapshot }).session;
  const running = launcher.replace(PLAN_TARGET, expected);
  await flush();
  h.controller.rate("good");
  h.gets.shift()!.resolve(ok(queueBody([item("personal", 20, 0)])));
  const outcome = await running;
  assert.notEqual(outcome.kind, "started");
  assert.equal(h.controller.getSession()?.attemptStatus, "sending");
  assert.equal(h.controller.snapshot().card?.id, 1);
});

// ---- 3. 뜻 수정 반영 ------------------------------------------------------------------

test("뜻 수정: 같은 계정·같은 id 카드에만 반영, 늦은 응답은 새 계정에 적용하지 않음", async () => {
  const h = harness();
  await startWith(h, [item("personal", 1, 3), item("personal", 2, 3)]);
  assert.equal(h.controller.patchPersonalCard(1, 2, { meaning_ko: "다른 카드" }), true);
  assert.equal(h.controller.snapshot().card?.meaning_ko, "뜻1", "지금 카드는 그대로");
  assert.equal(h.controller.patchPersonalCard(1, 1, { meaning_ko: "새 뜻" }), true);
  assert.equal(h.controller.snapshot().card?.meaning_ko, "새 뜻");
  h.setEpoch(2);
  assert.equal(h.controller.patchPersonalCard(1, 1, { meaning_ko: "늦은 응답" }), false);
  assert.equal(h.controller.snapshot().card?.meaning_ko, "새 뜻");
});
