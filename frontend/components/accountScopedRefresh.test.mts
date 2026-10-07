// 계정 범위 전체 갱신 테스트. 실행: node --test components/accountScopedRefresh.test.mts
import { test } from "node:test";
import assert from "node:assert/strict";
import { runAccountScopedRefresh } from "./accountScopedRefresh.ts";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((res) => { resolve = res; });
  return { promise, resolve };
}

// page.tsx와 같은 배선: 계정 경계는 epoch을 올리고 세션을 동기로 초기화하며,
// 전체 갱신은 덱 → 통계 → 공유 덱 순으로 기다린다. 덱 조회만 늦출 수 있다.
function app() {
  const state = { epoch: 0, session: 0, sessionOwner: "", calls: [] as string[] };
  const slowDecks: Array<ReturnType<typeof deferred>> = [];
  const boundary = () => {
    state.epoch += 1;
    state.session += 1;
    state.sessionOwner = "";
  };
  const startStudy = (owner: string) => {
    state.session += 1;
    state.sessionOwner = owner;
  };
  const refresh = (label: string, delayDecks = false) =>
    runAccountScopedRefresh(() => state.epoch, [
      async () => {
        state.calls.push(`${label}:decks`);
        if (delayDecks) {
          const d = deferred();
          slowDecks.push(d);
          await d.promise;
        }
      },
      async () => void state.calls.push(`${label}:stats`),
      async () => void state.calls.push(`${label}:shared`),
    ]);
  return { state, boundary, startStudy, refresh, slowDecks };
}

test("A→B 전환 뒤 B 복습 시작: 늦은 A 갱신은 멈추고 B 세션은 유지", async () => {
  const a = app();
  a.boundary(); // A 로그인
  const refreshA = a.refresh("A", true);
  a.boundary(); // B 로그인
  assert.equal(await a.refresh("B"), true);
  a.startStudy("B");
  const sessionB = a.state.session;
  a.slowDecks[0].resolve();
  assert.equal(await refreshA, false);
  assert.deepEqual(a.state.calls, ["A:decks", "B:decks", "B:stats", "B:shared"]);
  assert.equal(a.state.session, sessionB);
  assert.equal(a.state.sessionOwner, "B");
});

test("만료 뒤 재로그인: 만료 쪽 늦은 갱신이 새 로그인 세션을 지우지 않음", async () => {
  const a = app();
  a.boundary(); // 만료
  const refreshExpired = a.refresh("expired", true);
  a.boundary(); // 재로그인
  const refreshLogin = a.refresh("login");
  a.startStudy("login");
  const session = a.state.session;
  a.slowDecks[0].resolve();
  assert.equal(await refreshExpired, false);
  assert.equal(await refreshLogin, true);
  assert.equal(a.state.calls.filter((c) => c.startsWith("expired")).length, 1);
  assert.equal(a.state.session, session);
  assert.equal(a.state.sessionOwner, "login");
});

test("같은 계정: 갱신 중 시작한 새 학습은 갱신이 끝나도 유지", async () => {
  const a = app();
  a.boundary();
  const refresh = a.refresh("A", true);
  a.startStudy("A");
  const session = a.state.session;
  a.slowDecks[0].resolve();
  assert.equal(await refresh, true);
  assert.deepEqual(a.state.calls, ["A:decks", "A:stats", "A:shared"]);
  assert.equal(a.state.session, session);
  assert.equal(a.state.sessionOwner, "A");
});

test("단계 실패는 그대로 올라가고 남은 단계는 실행하지 않음", async () => {
  const calls: string[] = [];
  await assert.rejects(
    runAccountScopedRefresh(() => 0, [
      async () => { throw new Error("boom"); },
      async () => void calls.push("after"),
    ]),
    /boom/,
  );
  assert.deepEqual(calls, []);
});
