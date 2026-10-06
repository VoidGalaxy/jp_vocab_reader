// 학습 계획 실행·세션 보호 테스트. 실행: node --test components/planStudyLauncher.test.mts
import { test } from "node:test";
import assert from "node:assert/strict";
import { createPlanStudyLauncher } from "./planStudyLauncher.ts";
import type { PlanStudyTarget, StudySessionSnapshot } from "./planStudyLauncher.ts";

const target: PlanStudyTarget = { deck: { kind: "subscribed", id: 4 }, mode: "new" };

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function harness(initial: Partial<StudySessionSnapshot> = {}) {
  const state = {
    session: { id: 1, position: 0, inProgress: false, remaining: 0, ...initial } as StudySessionSnapshot,
    epoch: 0,
    fetches: 0,
    replaced: [] as Array<{ target: PlanStudyTarget; items: string[] }>,
    resumed: 0,
    next: null as null | ReturnType<typeof deferred<string[]>>,
  };
  const launcher = createPlanStudyLauncher<string>({
    getSession: () => ({ ...state.session }),
    getAccountEpoch: () => state.epoch,
    fetchQueue: () => {
      state.fetches += 1;
      state.next = deferred<string[]>();
      return state.next.promise;
    },
    replaceSession: (t, items) => {
      state.replaced.push({ target: t, items });
      state.session = { id: state.session.id + 1, position: 0, inProgress: true, remaining: items.length };
    },
    resumeSession: () => { state.resumed += 1; },
  });
  return { state, launcher };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

test("세션이 없으면 바로 조회 후 시작", async () => {
  const { state, launcher } = harness();
  const p = launcher.start(target);
  await flush();
  state.next!.resolve(["a", "b"]);
  assert.deepEqual(await p, { kind: "started", count: 2 });
  assert.equal(state.replaced.length, 1);
});

test("진행 중이면 확인을 요구하고 아무것도 조회하지 않음", async () => {
  const { state, launcher } = harness({ inProgress: true, remaining: 5 });
  const r = await launcher.start(target);
  assert.equal(r.kind, "needsConfirm");
  assert.equal(state.fetches, 0);
  assert.equal(state.replaced.length, 0);
});

test("이어하기는 세션을 건드리지 않고 이동만", async () => {
  const { state, launcher } = harness({ inProgress: true, remaining: 5 });
  await launcher.start(target);
  assert.deepEqual(launcher.resume(), { kind: "resumed" });
  assert.equal(state.resumed, 1);
  assert.equal(state.replaced.length, 0);
});

test("교체: 성공·비어 있지 않을 때만", async () => {
  const { state, launcher } = harness({ inProgress: true, remaining: 5 });
  const ask = await launcher.start(target);
  assert.equal(ask.kind, "needsConfirm");
  const expected = (ask as { session: StudySessionSnapshot }).session;

  let p = launcher.replace(target, expected);
  await flush();
  state.next!.reject(new Error("network"));
  assert.deepEqual(await p, { kind: "failed" });
  assert.equal(state.replaced.length, 0);

  p = launcher.replace(target, expected);
  await flush();
  state.next!.resolve([]);
  assert.deepEqual(await p, { kind: "empty" });
  assert.equal(state.replaced.length, 0);

  p = launcher.replace(target, expected);
  await flush();
  state.next!.resolve(["x"]);
  assert.deepEqual(await p, { kind: "started", count: 1 });
  assert.equal(state.replaced.length, 1);
});

test("조회 중 기존 세션이 진행되면 덮어쓰지 않음", async () => {
  const { state, launcher } = harness({ inProgress: true, remaining: 5 });
  const ask = (await launcher.start(target)) as { session: StudySessionSnapshot };
  const p = launcher.replace(target, ask.session);
  await flush();
  state.session = { ...state.session, position: 1, remaining: 4 }; // 그사이 한 장 평가
  state.next!.resolve(["x"]);
  assert.deepEqual(await p, { kind: "sessionChanged" });
  assert.equal(state.replaced.length, 0);
});

test("조회 중 다른 경로로 새 세션이 시작돼도 덮어쓰지 않음", async () => {
  const { state, launcher } = harness();
  const p = launcher.start(target);
  await flush();
  state.session = { id: 9, position: 0, inProgress: true, remaining: 3 };
  state.next!.resolve(["x"]);
  assert.deepEqual(await p, { kind: "sessionChanged" });
  assert.equal(state.replaced.length, 0);
});

test("중복 클릭은 요청 1건", async () => {
  const { state, launcher } = harness();
  const first = launcher.start(target);
  const second = await launcher.start(target);
  assert.deepEqual(second, { kind: "busy" });
  await flush();
  state.next!.resolve(["a"]);
  await first;
  assert.equal(state.fetches, 1);
  assert.equal(state.replaced.length, 1);
});

test("취소하면 늦은 응답을 버림", async () => {
  const { state, launcher } = harness({ inProgress: true, remaining: 2 });
  const ask = (await launcher.start(target)) as { session: StudySessionSnapshot };
  const p = launcher.replace(target, ask.session);
  await flush();
  launcher.cancel();
  state.next!.resolve(["late"]);
  assert.deepEqual(await p, { kind: "cancelled" });
  assert.equal(state.replaced.length, 0);
  assert.equal(launcher.isBusy(), false);
});

test("계정이 바뀌면 늦은 응답을 버림", async () => {
  const { state, launcher } = harness();
  const p = launcher.start(target);
  await flush();
  state.epoch += 1;
  state.next!.resolve(["a"]);
  assert.deepEqual(await p, { kind: "stale" });
  assert.equal(state.replaced.length, 0);
});

test("큐를 하루량으로 자르지 않음: 받은 그대로 교체", async () => {
  const { state, launcher } = harness();
  const p = launcher.start(target);
  await flush();
  const thirty = Array.from({ length: 30 }, (_, i) => `w${i}`);
  state.next!.resolve(thirty);
  await p;
  assert.equal(state.replaced[0].items.length, 30);
});
