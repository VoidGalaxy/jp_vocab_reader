// 읽기 흐름 규칙 테스트(Gate D 회귀). 실행: node --test components/readingSessionFlow.test.mts
// page.tsx와 같은 배선을 가짜 상태로 재현한다. 합성 자료만 쓴다.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  captureReadingContext,
  createRequestSequence,
  recheckAfterUnverified,
  requiresDeckConfirmation,
} from "./readingSessionFlow.ts";
import type { ReadingSessionData } from "./readingSessionStorage.ts";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

/** page.tsx 읽기 상태의 축소판: 작업 교체(초기화·새 분석·복원), 덱 선택, 계정 경계. */
function readingPage() {
  const state = {
    ownerKey: "k:user:7" as string | null,
    epoch: 1,
    workId: 0,
    deckId: "X",
    tokens: [] as string[],
    savedIds: [] as number[],
    message: "",
    deckConfirmRequired: false,
    busy: false,
  };
  const deckSeq = createRequestSequence();
  const ctx = () =>
    captureReadingContext({
      ownerKey: () => state.ownerKey,
      accountEpoch: () => state.epoch,
      workId: () => state.workId,
      deckId: () => state.deckId,
    });
  return {
    state,
    deckSeq,
    ctx,
    /** 새 원문(초기화)·원문 교체·새 분석 시작·복원 = 작업 교체. */
    replaceWork() {
      state.workId += 1;
      deckSeq.invalidate();
      state.tokens = [];
      state.savedIds = [];
      state.message = "";
      state.busy = false;
    },
    /** 지연되는 분석: 끝나면 문맥이 그대로일 때만 결과를 적용. */
    async analyze(result: ReturnType<typeof deferred<string[]>>) {
      this.replaceWork();
      const c = ctx();
      const tokens = await result.promise;
      if (!c.isCurrent()) return "stale";
      if (!c.isCurrentForDeck()) return "deckChanged";
      state.tokens = tokens;
      state.message = "분석 완료";
      return "applied";
    },
    /** 지연되는 상태 저장: 서버 응답(저장 ID)은 문맥·덱이 그대로일 때만 화면에. */
    async saveStatus(response: ReturnType<typeof deferred<number>>) {
      const c = ctx();
      const id = await response.promise;
      if (!c.isCurrentForDeck()) return "stale";
      state.savedIds.push(id);
      state.message = "저장했습니다";
      return "applied";
    },
    /** 덱 확인·재조회: 요청 당시 덱·순서·문맥이 그대로일 때만 적용, 마지막 요청만 진행 표시 끔. */
    async confirmDeck(response: ReturnType<typeof deferred<number[]>>) {
      const c = ctx();
      const seq = deckSeq.start();
      state.busy = true;
      try {
        const ids = await response.promise;
        if (!c.isCurrentForDeck() || !deckSeq.isLatest(seq)) return "stale";
        state.savedIds = ids;
        state.deckConfirmRequired = false;
        return "applied";
      } finally {
        if (deckSeq.isLatest(seq)) state.busy = false;
      }
    },
  };
}

test("[결함1] 분석 지연 중 '새 원문' 초기화: 늦은 분석이 토큰·메시지를 다시 붙이지 않음", async () => {
  const page = readingPage();
  const late = deferred<string[]>();
  const pending = page.analyze(late);
  page.replaceWork(); // 새 원문
  late.resolve(["猫", "犬"]);
  assert.equal(await pending, "stale");
  assert.deepEqual(page.state.tokens, []);
  assert.equal(page.state.message, "");
});

test("[결함1] 상태 저장 지연 중 초기화·새 분석: 늦은 저장 ID가 새 작업에 붙지 않음", async () => {
  const page = readingPage();
  const save = deferred<number>();
  const pendingSave = page.saveStatus(save);
  const fresh = deferred<string[]>();
  const pendingAnalyze = page.analyze(fresh); // 새 분석 = 작업 교체
  save.resolve(41);
  assert.equal(await pendingSave, "stale");
  fresh.resolve(["山"]);
  assert.equal(await pendingAnalyze, "applied");
  assert.deepEqual(page.state.savedIds, []);
  assert.deepEqual(page.state.tokens, ["山"]);
});

test("[결함1] 같은 작업 안의 정상 응답은 그대로 적용", async () => {
  const page = readingPage();
  const save = deferred<number>();
  const pending = page.saveStatus(save);
  save.resolve(5);
  assert.equal(await pending, "applied");
  assert.deepEqual(page.state.savedIds, [5]);
});

test("[결함3] 덱 X 확인 응답 지연 중 덱 Y로 변경: X 응답이 Y에 적용되지 않고, 오래된 finally가 Y의 진행 표시를 끄지 않음", async () => {
  const page = readingPage();
  page.state.deckConfirmRequired = true;
  const x = deferred<number[]>();
  const pendingX = page.confirmDeck(x);
  page.state.deckId = "Y";
  const y = deferred<number[]>();
  const pendingY = page.confirmDeck(y);
  x.resolve([1, 2]);
  assert.equal(await pendingX, "stale");
  assert.equal(page.state.busy, true); // Y가 아직 진행 중
  assert.deepEqual(page.state.savedIds, []);
  assert.equal(page.state.deckConfirmRequired, true);
  y.resolve([9]);
  assert.equal(await pendingY, "applied");
  assert.deepEqual(page.state.savedIds, [9]);
  assert.equal(page.state.busy, false);
});

test("[결함3] 덱 X 요청 후 Y로 바꿨다가 다시 X로 돌아와도, 그 사이 새 요청이 있었으면 옛 X 응답은 버림", async () => {
  const page = readingPage();
  const first = deferred<number[]>();
  const pendingFirst = page.confirmDeck(first);
  page.state.deckId = "Y";
  page.state.deckId = "X";
  const second = deferred<number[]>();
  const pendingSecond = page.confirmDeck(second);
  first.resolve([1]);
  assert.equal(await pendingFirst, "stale");
  second.resolve([2]);
  assert.equal(await pendingSecond, "applied");
  assert.deepEqual(page.state.savedIds, [2]);
});

test("[결함3] 분석 중 덱 변경: 결과를 적용하지 않음(deckChanged)", async () => {
  const page = readingPage();
  const late = deferred<string[]>();
  const pending = page.analyze(late);
  page.state.deckId = "Y";
  late.resolve(["猫"]);
  assert.equal(await pending, "deckChanged");
  assert.deepEqual(page.state.tokens, []);
});

test("계정 경계·owner 변경도 모든 요청을 무효화", async () => {
  const page = readingPage();
  const save = deferred<number>();
  const pending = page.saveStatus(save);
  page.state.epoch += 1;
  page.state.ownerKey = "k:user:8";
  save.resolve(3);
  assert.equal(await pending, "stale");
  const c = page.ctx();
  page.state.ownerKey = null;
  assert.equal(c.isCurrent(), false);
});

// ---- 결함 2: 모든 복원 경로에서 같은 덱 확인 규칙 -------------------------------

const base = (extra: Partial<ReadingSessionData>): ReadingSessionData => ({
  originalText: "〔S〕合成",
  analyzedText: "〔S〕合成",
  deckId: "",
  tokens: [],
  selectedTokenKey: null,
  message: "",
  isTextCollapsed: true,
  recentlySavedVocabItemIds: [],
  scrollFraction: null,
  tabletDocumentScrollFraction: null,
  ...extra,
});
const tok = { surface: "猫" } as never;

test("[결함2] 덱 연결 없이 토큰만 있는 세션은 어느 경로로 열든 덱 확인 요구", () => {
  // 최초 복원·다른 창 내용 불러오기·복사·미저장 사본 되살리기 모두 이 규칙을 쓴다.
  assert.equal(requiresDeckConfirmation(base({ tokens: [tok] })), true);
  assert.equal(requiresDeckConfirmation(base({ tokens: [tok], deckId: "4" })), false);
  assert.equal(requiresDeckConfirmation(base({ tokens: [] })), false); // 원문만 사본
  assert.equal(requiresDeckConfirmation(base({ tokens: [], deckId: "4" })), false);
});

test("[결함2] 확인 전 화면 스냅샷은 덱을 비워 두므로 되살려도 다시 확인 요구", () => {
  // page.tsx: 덱 확인 전에는 저장용 스냅샷의 deckId를 ""로 둔다.
  const confirmRequired = true;
  const selectedDeck = "4";
  const snapshot = base({ tokens: [tok], deckId: confirmRequired ? "" : selectedDeck });
  assert.equal(requiresDeckConfirmation(snapshot), true);
});

// ---- 결함 4: 확인 실패 재확인 ------------------------------------------------------

const json = (s: ReadingSessionData) => JSON.stringify(s);
const stored = (s: ReadingSessionData) =>
  ({
    kind: "ok",
    value: { version: 3, scope: "s", owner: { kind: "guest" }, instanceId: "i1", revision: 4, updatedAt: "t", session: s },
  }) as const;

test("[결함4] 삭제 후 확인 실패: 키가 없을 때만 '지워짐'으로 채택, 남아 있으면 충돌(성공·보존 단정 없음)", () => {
  assert.deepEqual(recheckAfterUnverified({ kind: "empty" }, { kind: "remove" }, json), { kind: "adoptEmpty" });
  assert.deepEqual(recheckAfterUnverified(stored(base({})), { kind: "remove" }, json), { kind: "conflict" });
  assert.deepEqual(recheckAfterUnverified({ kind: "corrupt", reason: "invalid_json" }, { kind: "remove" }, json), { kind: "conflict" });
  assert.deepEqual(recheckAfterUnverified({ kind: "unavailable" }, { kind: "remove" }, json), { kind: "unavailable" });
});

test("[결함4] 저장 후 확인 실패: 저장값이 시도한 내용과 같을 때만 채택", () => {
  const mine = base({ originalText: "〔MINE〕" });
  const other = base({ originalText: "〔OTHER〕" });
  assert.deepEqual(recheckAfterUnverified(stored(mine), { kind: "save", json: json(mine) }, json), {
    kind: "adopt",
    instanceId: "i1",
    revision: 4,
    json: json(mine),
  });
  assert.deepEqual(recheckAfterUnverified(stored(other), { kind: "save", json: json(mine) }, json), { kind: "conflict" });
  assert.deepEqual(recheckAfterUnverified({ kind: "empty" }, { kind: "save", json: json(mine) }, json), { kind: "conflict" });
  assert.deepEqual(recheckAfterUnverified(stored(mine), null, json), { kind: "conflict" });
});

test("요청 순서: 마지막 요청만 최신, invalidate는 진행 중 요청을 모두 오래된 것으로", () => {
  const seq = createRequestSequence();
  const a = seq.start();
  const b = seq.start();
  assert.equal(seq.isLatest(a), false);
  assert.equal(seq.isLatest(b), true);
  seq.invalidate();
  assert.equal(seq.isLatest(b), false);
});
