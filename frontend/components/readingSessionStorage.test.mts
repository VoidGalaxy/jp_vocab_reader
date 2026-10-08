// 읽기 기기 저장 테스트. 실행: node --test components/readingSessionStorage.test.mts
// 합성 원문·메모리 저장소·가짜 잠금만 쓴다. 실제 브라우저 저장소·서버에 닿지 않는다.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LEGACY_READING_SESSION_KEY,
  MAX_READING_TEXT_LENGTH,
  copyToEmptyReadingSession,
  detachServerLinks,
  originalTextDownload,
  parseLegacyReadingSession,
  rawBackupDownload,
  readLegacyReadingSession,
  readLegacyReadingSessionRaw,
  readReadingSession,
  readingSessionKey,
  readingStorageCapability,
  removeReadingSession,
  saveReadingSession,
} from "./readingSessionStorage.ts";
import type {
  LockManagerLike,
  ReadingOwner,
  ReadingSessionData,
  ReadingSessionVersion,
  ReadingStorageEnv,
} from "./readingSessionStorage.ts";

// ---- 가짜 환경 ----------------------------------------------------------------

function memoryStorage(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  const faults = {
    setError: null as null | string,
    getError: null as null | string,
    removeError: null as null | string,
    dropWrites: false,
    // 다음 쓰기/삭제가 끝난 뒤부터 getItem이 실패(쓰기 후 확인 불가 흉내).
    failGetAfterWrite: false,
    // 쓰기는 되지만 다른 값이 남는 저장소(확인 불일치 흉내).
    mangleWrites: false,
  };
  const writes: string[] = [];
  const afterWrite = () => {
    if (faults.failGetAfterWrite) faults.getError = "SecurityError";
  };
  return {
    data,
    faults,
    writes,
    getItem(k: string) {
      if (faults.getError) throw new DOMException("injected", faults.getError);
      return data.has(k) ? (data.get(k) as string) : null;
    },
    setItem(k: string, v: string) {
      if (faults.setError) throw new DOMException("injected", faults.setError);
      writes.push(k);
      if (!faults.dropWrites) data.set(k, faults.mangleWrites ? `${v} ` : v);
      afterWrite();
    },
    removeItem(k: string) {
      if (faults.removeError) throw new DOMException("injected", faults.removeError);
      writes.push(`remove:${k}`);
      data.delete(k);
      afterWrite();
    },
  };
}

/** 이름별 배타 잠금. 대기 중 signal abort를 지원하고, 다른 "창"이 잡고 있게 할 수 있다. */
function fakeLocks() {
  const tails = new Map<string, Promise<void>>();
  const locks: LockManagerLike & { hold(name: string): () => void } = {
    request(name, options, callback) {
      const prev = tails.get(name) ?? Promise.resolve();
      let release!: () => void;
      const mine = new Promise<void>((r) => { release = r; });
      tails.set(name, prev.then(() => mine));
      return new Promise((resolve, reject) => {
        let started = false;
        const onAbort = () => {
          if (started) return;
          release();
          reject(new DOMException("aborted", "AbortError"));
        };
        if (options.signal?.aborted) { onAbort(); return; }
        options.signal?.addEventListener("abort", onAbort, { once: true });
        prev.then(async () => {
          if (options.signal?.aborted) return;
          started = true;
          options.signal?.removeEventListener("abort", onAbort);
          try { resolve(await callback({ name })); } catch (e) { reject(e); } finally { release(); }
        });
      });
    },
    hold(name) {
      let release!: () => void;
      const held = new Promise<void>((r) => { release = r; });
      const prev = tails.get(name) ?? Promise.resolve();
      tails.set(name, prev.then(() => held));
      return release;
    },
  };
  return locks;
}

function env(storage = memoryStorage(), locks: ReturnType<typeof fakeLocks> | null = fakeLocks()) {
  return { storage, locks, env: { storage, locks } as ReadingStorageEnv };
}

const tick = () => new Promise((r) => setTimeout(r, 5));

// ---- 합성 자료 ----------------------------------------------------------------

const SCOPE = encodeURIComponent("http://127.0.0.1:8000");
const OTHER_SCOPE = encodeURIComponent("https://api.example.test");
const A: ReadingOwner = { kind: "user", userId: 7 };
const B: ReadingOwner = { kind: "user", userId: 8 };
const G: ReadingOwner = { kind: "guest" };
const NOW = new Date("2026-10-08T03:00:00Z");
const current = { isCurrent: () => true };

function token(base: string, extra: Record<string, unknown> = {}) {
  return {
    surface: base, base_form: base, reading: base, part_of_speech: "名詞", normalized_form: base,
    meaning_ko: `뜻-${base}`, dictionary_gloss: "", quality_tag: "normal", example_sentence: `${base}の例文。`,
    is_custom_term: false, occurrence_count: 1, status: "unknown", isClassified: true, ...extra,
  };
}

function session(marker: string, extra: Partial<ReadingSessionData> = {}): ReadingSessionData {
  return {
    originalText: `〔${marker}〕合成の原文です。`,
    analyzedText: `〔${marker}〕合成の原文です。`,
    deckId: "12",
    tokens: [token("合成") as never],
    selectedTokenKey: "合成",
    message: "",
    isTextCollapsed: true,
    recentlySavedVocabItemIds: [],
    scrollFraction: 0.4,
    tabletDocumentScrollFraction: null,
    ...extra,
  };
}

function legacyRaw(version: 1 | 2 = 2) {
  return JSON.stringify({
    version,
    originalText: "〔LEGACY〕古い共通の原文。",
    analyzedText: "〔LEGACY〕古い共通の原文。",
    deckId: "3",
    tokens: [token("古い", { savedVocabItemId: 41, savedExampleSentence: "保存済み例文", savedMeaningKo: "저장된 뜻" })],
    selectedTokenKey: "古い",
    message: "선택한 단어 1개를 저장했습니다.",
    isTextCollapsed: true,
    recentlySavedVocabItemIds: [41],
    scrollFraction: 0.5,
    tabletDocumentScrollFraction: 0.25,
    updatedAt: "2026-10-01T00:00:00Z",
  });
}

async function save(
  e: ReadingStorageEnv,
  owner: ReadingOwner,
  base: ReadingSessionVersion | null,
  s: ReadingSessionData,
  ctx: { isCurrent: () => boolean; signal?: AbortSignal } = current,
  scope = SCOPE,
) {
  return saveReadingSession(e, { scope, owner, base, session: s, now: NOW, ...ctx });
}

/** 현재 저장된 버전(테스트에서 "창이 마지막으로 확인한 버전"을 만들 때). */
function ver(e: ReadingStorageEnv, owner: ReadingOwner, scope = SCOPE): ReadingSessionVersion | null {
  const r = readReadingSession(e, scope, owner);
  return r.kind === "ok" ? { instanceId: r.value.instanceId, revision: r.value.revision } : null;
}

function text(e: ReadingStorageEnv, owner: ReadingOwner): string | null {
  const r = readReadingSession(e, SCOPE, owner);
  return r.kind === "ok" ? r.value.session.originalText : null;
}

function okVersion(r: { kind: string; version?: ReadingSessionVersion }, revision: number): ReadingSessionVersion {
  assert.equal(r.kind, "ok");
  assert.equal(r.version!.revision, revision);
  assert.ok(r.version!.instanceId.length > 0);
  return r.version!;
}

// ---- 키·격리 --------------------------------------------------------------------

test("키: 환경·계정·방문자마다 다르고 옛 공통 키와도 다름", () => {
  const keys = [
    readingSessionKey(SCOPE, A), readingSessionKey(SCOPE, B), readingSessionKey(SCOPE, G),
    readingSessionKey(OTHER_SCOPE, A), readingSessionKey(OTHER_SCOPE, G), LEGACY_READING_SESSION_KEY,
  ];
  assert.equal(new Set(keys).size, keys.length);
  assert.equal(readingSessionKey(SCOPE, A), `jp-vocab-reader:reading-session-v3:${SCOPE}:user:7`);
  assert.equal(readingSessionKey(SCOPE, G), `jp-vocab-reader:reading-session-v3:${SCOPE}:guest`);
  assert.throws(() => readingSessionKey("a:b", A));
  assert.throws(() => readingSessionKey("", A));
  assert.throws(() => readingSessionKey(SCOPE, { kind: "user", userId: 0 }));
  assert.throws(() => readingSessionKey(SCOPE, { kind: "user", userId: 1.5 }));
});

test("격리: A의 저장은 B·방문자·다른 환경에서 보이지 않음, 이메일·토큰 없음", async () => {
  const { env: e, storage } = env();
  okVersion(await save(e, A, null, session("A1")), 1);
  assert.equal(readReadingSession(e, SCOPE, B).kind, "empty");
  assert.equal(readReadingSession(e, SCOPE, G).kind, "empty");
  assert.equal(readReadingSession(e, OTHER_SCOPE, A).kind, "empty");
  const got = readReadingSession(e, SCOPE, A);
  assert.equal(got.kind, "ok");
  if (got.kind === "ok") {
    assert.equal(got.value.revision, 1);
    assert.deepEqual(got.value.owner, A);
    assert.match(got.value.session.originalText, /A1/);
  }
  const raw = storage.data.get(readingSessionKey(SCOPE, A)) as string;
  assert.doesNotMatch(raw, /email|token"|password|@/i);
  assert.deepEqual([...storage.data.keys()], [readingSessionKey(SCOPE, A)]);
});

test("owner 불일치: A 자료가 B 키에 있으면 복원·덮어쓰기 모두 거부, 원값 그대로", async () => {
  const { env: e, storage } = env();
  await save(e, A, null, session("A1"));
  const aRaw = storage.data.get(readingSessionKey(SCOPE, A)) as string;
  storage.data.set(readingSessionKey(SCOPE, B), aRaw);
  assert.deepEqual(readReadingSession(e, SCOPE, B), { kind: "corrupt", reason: "owner_mismatch" });
  const r = await save(e, B, null, session("B1"));
  assert.deepEqual(r, { kind: "corrupt", reason: "owner_mismatch", previous: "kept" });
  assert.equal(storage.data.get(readingSessionKey(SCOPE, B)), aRaw);
  storage.data.set(readingSessionKey(OTHER_SCOPE, A), aRaw);
  assert.deepEqual(readReadingSession(e, OTHER_SCOPE, A), { kind: "corrupt", reason: "owner_mismatch" });
});

// ---- 옛 공통 키 ----------------------------------------------------------------

test("옛 키: v1/v2 읽기 호환, 깨진/미지원 구분, 어떤 동작에도 원값 그대로", async () => {
  for (const v of [1, 2] as const) {
    const parsed = parseLegacyReadingSession(legacyRaw(v));
    assert.equal(parsed.kind, "ok");
    if (parsed.kind === "ok") assert.equal(parsed.value.version, v);
  }
  assert.deepEqual(parseLegacyReadingSession("{oops"), { kind: "corrupt", reason: "invalid_json" });
  assert.deepEqual(parseLegacyReadingSession(JSON.stringify({ version: 3 })), { kind: "corrupt", reason: "unsupported_version" });
  assert.deepEqual(parseLegacyReadingSession(JSON.stringify({ version: 2, originalText: 1 })), { kind: "corrupt", reason: "invalid_fields" });
  assert.deepEqual(parseLegacyReadingSession(null), { kind: "empty" });

  const raw = legacyRaw();
  const { env: e, storage } = env(memoryStorage({ [LEGACY_READING_SESSION_KEY]: raw }));
  const legacy = readLegacyReadingSession(e);
  assert.equal(legacy.kind, "ok");
  await save(e, A, null, session("A1"));
  if (legacy.kind === "ok") {
    await copyToEmptyReadingSession(e, { scope: SCOPE, owner: B, source: legacy.value.session, mode: "full", ...current });
    await copyToEmptyReadingSession(e, { scope: SCOPE, owner: G, source: legacy.value.session, mode: "textOnly", ...current });
  }
  await removeReadingSession(e, { scope: SCOPE, owner: A, expected: ver(e, A)!, ...current });
  assert.equal(storage.data.get(LEGACY_READING_SESSION_KEY), raw);
  assert.ok(!storage.writes.some((w) => w.endsWith(LEGACY_READING_SESSION_KEY)));
  assert.equal(readLegacyReadingSessionRaw(e), raw);
  const broken = env(memoryStorage({ [LEGACY_READING_SESSION_KEY]: "{broken" }));
  assert.deepEqual(readLegacyReadingSession(broken.env), { kind: "corrupt", reason: "invalid_json" });
  assert.equal(broken.storage.data.get(LEGACY_READING_SESSION_KEY), "{broken");
});

// ---- 복구 사본 -------------------------------------------------------------------

test("원문만 복사(기본): 빈 목적지에 원문 하나만, 서버 요청 재료 없음", async () => {
  const raw = legacyRaw();
  const { env: e, storage } = env(memoryStorage({ [LEGACY_READING_SESSION_KEY]: raw }));
  const legacy = readLegacyReadingSession(e);
  if (legacy.kind !== "ok") return assert.fail("legacy should parse");
  const r = await copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: legacy.value.session, mode: "textOnly", now: NOW, ...current });
  okVersion(r, 1);
  const got = readReadingSession(e, SCOPE, A);
  if (got.kind !== "ok") return assert.fail("copy should be readable");
  const s = got.value.session;
  assert.equal(s.originalText, "〔LEGACY〕古い共通の原文。");
  assert.deepEqual([s.analyzedText, s.deckId, s.tokens, s.selectedTokenKey, s.message, s.recentlySavedVocabItemIds, s.scrollFraction],
    ["", "", [], null, "", [], null]);
  assert.equal(storage.data.get(LEGACY_READING_SESSION_KEY), raw);
});

test("전체 사본(보조): 옛 서버 ID·저장 완료·서버 뜻/예문 제거, 로컬 분류·선택·위치 유지, 원본 보존", async () => {
  const raw = legacyRaw();
  const { env: e, storage } = env(memoryStorage({ [LEGACY_READING_SESSION_KEY]: raw }));
  const legacy = readLegacyReadingSession(e);
  if (legacy.kind !== "ok") return assert.fail("legacy should parse");
  const sourceBefore = JSON.stringify(legacy.value.session);
  okVersion(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: legacy.value.session, mode: "full", now: NOW, ...current }), 1);
  const got = readReadingSession(e, SCOPE, A);
  if (got.kind !== "ok") return assert.fail("copy should be readable");
  const s = got.value.session;
  assert.equal(s.deckId, "");
  assert.equal(s.message, "");
  assert.deepEqual(s.recentlySavedVocabItemIds, []);
  assert.equal(s.tokens[0].savedVocabItemId, null);
  assert.equal(s.tokens[0].savedExampleSentence, null);
  assert.equal(s.tokens[0].savedMeaningKo, null);
  assert.equal(s.tokens[0].status, "unknown");
  assert.equal(s.tokens[0].meaning_ko, "뜻-古い");
  assert.equal(s.tokens[0].example_sentence, "古いの例文。");
  assert.equal(s.selectedTokenKey, "古い");
  assert.equal(s.scrollFraction, 0.5);
  assert.equal(s.tabletDocumentScrollFraction, 0.25);
  // instanceId(무작위)에는 숫자가 섞일 수 있으므로 세션 부분만 검사한다.
  const storedSession = JSON.stringify(JSON.parse(storage.data.get(readingSessionKey(SCOPE, A)) as string).session);
  assert.doesNotMatch(storedSession, /41|저장된 뜻|保存済み例文|저장했습니다/);
  assert.equal(JSON.stringify(legacy.value.session), sourceBefore);
  assert.equal(storage.data.get(LEGACY_READING_SESSION_KEY), raw);
  assert.equal(detachServerLinks(legacy.value.session).tokens[0].savedVocabItemId, null);
  assert.equal(legacy.value.session.tokens[0].savedVocabItemId, 41);
});

test("목적지에 키가 있으면(빈 세션·깨진 자료 포함) 복사하지 않고 그대로 둠", async () => {
  const src = session("SRC");
  const { env: e, storage } = env();
  await save(e, A, null, { ...session("EMPTY"), originalText: "", analyzedText: "", tokens: [] });
  const emptyRaw = storage.data.get(readingSessionKey(SCOPE, A));
  assert.deepEqual(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: src, mode: "textOnly", ...current }), { kind: "destinationExists" });
  assert.equal(storage.data.get(readingSessionKey(SCOPE, A)), emptyRaw);
  storage.data.set(readingSessionKey(SCOPE, B), "{corrupt");
  assert.deepEqual(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: B, source: src, mode: "full", ...current }), { kind: "destinationExists" });
  assert.equal(storage.data.get(readingSessionKey(SCOPE, B)), "{corrupt");
});

// ---- 저장 계약 -----------------------------------------------------------------

test("빈 세션 저장도 키를 지우지 않고 revision만 올림(같은 instanceId)", async () => {
  const { env: e, storage } = env();
  const v1 = okVersion(await save(e, G, null, session("G1")), 1);
  const v2 = okVersion(await save(e, G, v1, { ...session("G1"), originalText: "", analyzedText: "", tokens: [] }), 2);
  assert.equal(v2.instanceId, v1.instanceId);
  assert.ok(storage.data.has(readingSessionKey(SCOPE, G)));
  assert.ok(!storage.writes.some((w) => w.startsWith("remove:")));
});

test("깨진 기존 값·미지원 버전·instanceId 없는 v3는 덮어쓰지 않음", async () => {
  const noInstance = JSON.stringify({ version: 3, scope: SCOPE, owner: A, revision: 1, updatedAt: "x", session: session("S") });
  for (const bad of ["{x", JSON.stringify({ version: 4 }), JSON.stringify({ version: 3, scope: SCOPE }), noInstance]) {
    const { env: e, storage } = env(memoryStorage({ [readingSessionKey(SCOPE, A)]: bad }));
    const r = await save(e, A, null, session("A1"));
    assert.equal(r.kind, "corrupt");
    assert.equal(storage.data.get(readingSessionKey(SCOPE, A)), bad);
  }
});

test("초과 길이: 쓰기 거절, 이전 저장본 유무를 구분해 알려 주고 그대로 둠", async () => {
  const big = { ...session("BIG"), originalText: "あ".repeat(MAX_READING_TEXT_LENGTH + 1) };
  const fresh = env();
  assert.deepEqual(await save(fresh.env, A, null, big), { kind: "tooLarge", previous: "none" });
  assert.equal(fresh.storage.data.size, 0);
  const kept = env();
  await save(kept.env, A, null, session("A1"));
  const before = kept.storage.data.get(readingSessionKey(SCOPE, A));
  assert.deepEqual(await save(kept.env, A, ver(kept.env, A), big), { kind: "tooLarge", previous: "kept" });
  assert.equal(kept.storage.data.get(readingSessionKey(SCOPE, A)), before);
  assert.deepEqual(await copyToEmptyReadingSession(fresh.env, { scope: SCOPE, owner: B, source: big, mode: "textOnly", ...current }), { kind: "tooLarge" });
  assert.equal(fresh.storage.data.size, 0);
});

test("쓰기 자체 실패: 원인과 이전 저장본 유무를 구분, 기존 값 그대로, 같은 base로 재시도 가능", async () => {
  const { env: e, storage } = env();
  storage.faults.setError = "QuotaExceededError";
  assert.deepEqual(await save(e, A, null, session("A1")), { kind: "error", reason: "quota", previous: "none" });
  storage.faults.setError = null;
  const v1 = okVersion(await save(e, A, null, session("A1")), 1);
  const before = storage.data.get(readingSessionKey(SCOPE, A));
  storage.faults.setError = "QuotaExceededError";
  assert.deepEqual(await save(e, A, v1, session("A2")), { kind: "error", reason: "quota", previous: "kept" });
  storage.faults.setError = "SecurityError";
  assert.deepEqual(await save(e, A, v1, session("A2")), { kind: "error", reason: "denied", previous: "kept" });
  storage.faults.setError = null;
  storage.faults.dropWrites = true; // setItem은 끝나지만 반영 안 됨 → 다시 읽은 값이 이전 값 그대로
  assert.deepEqual(await save(e, A, v1, session("A2")), { kind: "error", reason: "not_persisted", previous: "kept" });
  storage.faults.dropWrites = false;
  assert.equal(storage.data.get(readingSessionKey(SCOPE, A)), before);
  okVersion(await save(e, A, v1, session("A2")), 2);
  // 쓰기 전 현재 값을 읽지 못하면 쓰지 않는다.
  const v2 = ver(e, A);
  const writes = storage.writes.length;
  storage.faults.getError = "SecurityError";
  assert.deepEqual(readReadingSession(e, SCOPE, A), { kind: "unavailable" });
  assert.deepEqual(await save(e, A, v2, session("A3")), { kind: "error", reason: "unavailable", previous: "unknown" });
  assert.deepEqual(readLegacyReadingSession(e), { kind: "unavailable" });
  assert.equal(storage.writes.length, writes);
});

// ---- 보정 1: 삭제·재생성 구별 ------------------------------------------------------

test("[보정1] 저장→삭제→새 사본(revision 1): 옛 창의 revision 1 저장은 conflict, 새 사본 보존", async () => {
  const { env: e } = env();
  const oldWindow = okVersion(await save(e, A, null, session("OLD")), 1);
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: oldWindow, ...current }), { kind: "ok" });
  const fresh = okVersion(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: session("NEW"), mode: "textOnly", ...current }), 1);
  assert.notEqual(fresh.instanceId, oldWindow.instanceId);
  const r = await save(e, A, oldWindow, session("STALE"));
  assert.deepEqual(r, { kind: "conflict", stored: fresh, previous: "kept" });
  assert.match(text(e, A)!, /NEW/);
});

test("[보정1] 삭제 후 다시 첫 저장한 세션도 새 instanceId라 옛 창 저장·삭제가 적용되지 않음", async () => {
  const { env: e } = env();
  const oldWindow = okVersion(await save(e, A, null, session("OLD")), 1);
  await removeReadingSession(e, { scope: SCOPE, owner: A, expected: oldWindow, ...current });
  const recreated = okVersion(await save(e, A, null, session("RECREATED")), 1);
  assert.notEqual(recreated.instanceId, oldWindow.instanceId);
  assert.deepEqual(await save(e, A, oldWindow, session("STALE")), { kind: "conflict", stored: recreated, previous: "kept" });
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: oldWindow, ...current }), { kind: "conflict", stored: recreated });
  assert.match(text(e, A)!, /RECREATED/);
});

test("[보정1] 키가 없다고 보고(base null) 잠금을 기다리던 저장·복사는, 그 사이 다른 창이 만든 세션을 덮지 않음", async () => {
  const shared = memoryStorage();
  const thisWindow = env(shared);
  const release = thisWindow.locks!.hold(`jp-vocab-reader:lock:${readingSessionKey(SCOPE, A)}`);
  const waitingSave = save(thisWindow.env, A, null, session("WAITING"));
  const waitingCopy = copyToEmptyReadingSession(thisWindow.env, { scope: SCOPE, owner: A, source: session("COPY"), mode: "textOnly", ...current });
  await tick();
  // 잠금을 잡고 있던 다른 창이 그동안 세션을 만든다(그 창의 잠금 안에서의 쓰기를 흉내).
  const otherWindow = env(shared);
  const created = okVersion(await save(otherWindow.env, A, null, session("CREATED")), 1);
  release();
  assert.deepEqual(await waitingSave, { kind: "conflict", stored: created, previous: "kept" });
  assert.deepEqual(await waitingCopy, { kind: "destinationExists" });
  assert.match(text(thisWindow.env, A)!, /CREATED/);
  assert.deepEqual(ver(thisWindow.env, A), created);
});

// ---- 보정 2: 쓰기 후 확인 실패 ------------------------------------------------------

test("[보정2] 쓰기 후 다시 읽기 실패: unverified(이전 값 보존·성공 단정 없음), 되돌리지 않음", async () => {
  const { env: e, storage } = env();
  const v1 = okVersion(await save(e, A, null, session("V1")), 1);
  storage.faults.failGetAfterWrite = true;
  const r = await save(e, A, v1, session("V2"));
  assert.deepEqual(r, { kind: "unverified", reason: "read_back_failed" });
  assert.ok(!("previous" in r) && !("version" in r));
  storage.faults.failGetAfterWrite = false;
  storage.faults.getError = null;
  // 실제 값은 새 내용으로 바뀌어 있고, 이전 값으로 되돌리지 않았다.
  assert.match(text(e, A)!, /V2/);
  // 다시 읽어 확인하기 전(옛 base)에는 더 쓸 수 없다.
  const stale = await save(e, A, v1, session("V3"));
  assert.equal(stale.kind, "conflict");
  assert.match(text(e, A)!, /V2/);
  // 다시 읽어 얻은 base로는 저장된다.
  okVersion(await save(e, A, ver(e, A), session("V3")), 3);
});

test("[보정2] 다시 읽은 값이 다른 값이면 unverified(read_back_mismatch), 이전 값과 같으면 not_persisted", async () => {
  const { env: e, storage } = env();
  const v1 = okVersion(await save(e, A, null, session("V1")), 1);
  storage.faults.mangleWrites = true;
  assert.deepEqual(await save(e, A, v1, session("V2")), { kind: "unverified", reason: "read_back_mismatch" });
  storage.faults.mangleWrites = false;
  const fresh = env();
  fresh.storage.faults.dropWrites = true;
  assert.deepEqual(await save(fresh.env, A, null, session("X")), { kind: "error", reason: "not_persisted", previous: "none" });
});

test("[보정2] 복사·삭제도 확인 실패를 unverified로 구분", async () => {
  const c = env();
  c.storage.faults.failGetAfterWrite = true;
  assert.deepEqual(
    await copyToEmptyReadingSession(c.env, { scope: SCOPE, owner: A, source: session("C"), mode: "textOnly", ...current }),
    { kind: "unverified", reason: "read_back_failed" },
  );
  const d = env();
  const v = okVersion(await save(d.env, A, null, session("D")), 1);
  d.storage.faults.failGetAfterWrite = true;
  assert.deepEqual(await removeReadingSession(d.env, { scope: SCOPE, owner: A, expected: v, ...current }), { kind: "unverified", reason: "read_back_failed" });
  d.storage.faults.failGetAfterWrite = false;
  d.storage.faults.getError = null;
  d.storage.faults.removeError = "SecurityError";
  await save(d.env, A, null, session("D2"));
  assert.deepEqual(await removeReadingSession(d.env, { scope: SCOPE, owner: A, expected: ver(d.env, A)!, ...current }), { kind: "error", reason: "denied" });
  assert.match(text(d.env, A)!, /D2/);
});

// ---- 보정 3: 잠금 요청 실패 ----------------------------------------------------------

test("[보정3] 잠금 요청 실패(SecurityError, 동기·비동기 모두)는 lock_failed 결과, 잠금 없이 쓰지 않음", async () => {
  const storage = memoryStorage({ [LEGACY_READING_SESSION_KEY]: legacyRaw() });
  const seeded = env(storage);
  const v = okVersion(await save(seeded.env, A, null, session("A1")), 1);
  const snapshot = new Map(storage.data);
  const writes = storage.writes.length;
  const failing: LockManagerLike[] = [
    { request: async () => { throw new DOMException("denied", "SecurityError"); } },
    { request: () => { throw new DOMException("denied", "SecurityError"); } },
    { request: async () => { throw new TypeError("weird"); } },
  ];
  for (const locks of failing) {
    const e: ReadingStorageEnv = { storage, locks };
    assert.deepEqual(await save(e, A, v, session("A2")), { kind: "error", reason: "lock_failed", previous: "unknown" });
    assert.deepEqual(
      await copyToEmptyReadingSession(e, { scope: SCOPE, owner: B, source: session("B"), mode: "textOnly", ...current }),
      { kind: "error", reason: "lock_failed" },
    );
    assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: v, ...current }), { kind: "error", reason: "lock_failed" });
  }
  assert.equal(storage.writes.length, writes);
  assert.deepEqual(storage.data, snapshot);
});

test("[보정3] 잠금 요청의 AbortError는 계속 cancelled", async () => {
  const { storage } = env();
  const e: ReadingStorageEnv = { storage, locks: { request: async () => { throw new DOMException("aborted", "AbortError"); } } };
  assert.deepEqual(await save(e, A, null, session("A")), { kind: "cancelled" });
  assert.deepEqual(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: session("A"), mode: "full", ...current }), { kind: "cancelled" });
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: "corrupt", ...current }), { kind: "cancelled" });
  assert.equal(storage.writes.length, 0);
});

// ---- 동시 쓰기 -----------------------------------------------------------------

test("두 창이 같은 버전에서 동시에 저장: 하나만 성공, 다른 쪽은 conflict(덮어쓰기 없음)", async () => {
  const { env: e } = env();
  const v1 = okVersion(await save(e, A, null, session("A0")), 1);
  const [w1, w2] = await Promise.all([save(e, A, v1, session("W1")), save(e, A, v1, session("W2"))]);
  const v2 = okVersion(w1, 2);
  assert.deepEqual(w2, { kind: "conflict", stored: v2, previous: "kept" });
  assert.match(text(e, A)!, /W1/);
});

test("두 창이 같은 빈 목적지로 동시에 복사: 하나만 성공", async () => {
  const { env: e } = env();
  const results = await Promise.all([
    copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: session("C1"), mode: "textOnly", ...current }),
    copyToEmptyReadingSession(e, { scope: SCOPE, owner: A, source: session("C2"), mode: "full", ...current }),
  ]);
  assert.deepEqual(results.map((r) => r.kind).sort(), ["destinationExists", "ok"]);
  assert.match(text(e, A)!, /C1/);
});

// ---- 대기 중 취소·계정 변경 --------------------------------------------------------

test("잠금 대기 중 계정이 바뀌면 저장·복사·삭제 모두 실행하지 않음", async () => {
  const { env: e, storage, locks } = env();
  const v1 = okVersion(await save(e, A, null, session("A0")), 1);
  const before = storage.data.get(readingSessionKey(SCOPE, A));
  let owner = "A";
  const ctx = { isCurrent: () => owner === "A" };
  const release = locks!.hold(`jp-vocab-reader:lock:${readingSessionKey(SCOPE, A)}`);
  const pending = save(e, A, v1, session("LATE"), ctx);
  const pendingRemove = removeReadingSession(e, { scope: SCOPE, owner: A, expected: v1, ...ctx });
  const releaseB = locks!.hold(`jp-vocab-reader:lock:${readingSessionKey(SCOPE, B)}`);
  const pendingCopy = copyToEmptyReadingSession(e, { scope: SCOPE, owner: B, source: session("LATE"), mode: "textOnly", ...ctx });
  await tick();
  owner = "B";
  release();
  releaseB();
  assert.deepEqual(await pending, { kind: "cancelled" });
  assert.deepEqual(await pendingRemove, { kind: "cancelled" });
  assert.deepEqual(await pendingCopy, { kind: "cancelled" });
  assert.equal(storage.data.get(readingSessionKey(SCOPE, A)), before);
  assert.ok(!storage.data.has(readingSessionKey(SCOPE, B)));
});

test("잠금 대기 중 취소(AbortSignal)면 대기열에서 빠지고 쓰지 않음", async () => {
  const { env: e, storage, locks } = env();
  const release = locks!.hold(`jp-vocab-reader:lock:${readingSessionKey(SCOPE, A)}`);
  const controller = new AbortController();
  const pending = save(e, A, null, session("A1"), { isCurrent: () => true, signal: controller.signal });
  await tick();
  controller.abort();
  assert.deepEqual(await pending, { kind: "cancelled" });
  release();
  await tick();
  assert.equal(storage.data.size, 0);
  assert.deepEqual(await save(e, A, null, session("A1"), { isCurrent: () => true, signal: controller.signal }), { kind: "cancelled" });
  okVersion(await save(e, A, null, session("A1")), 1);
});

test("잠금을 얻은 뒤 쓰기 직전에 계정이 바뀌어도 쓰지 않음", async () => {
  const { env: e, storage } = env();
  let calls = 0;
  const ctx = { isCurrent: () => (calls += 1) < 3 }; // 시작 전, 잠금 직후는 유효, 쓰기 직전에 무효
  assert.deepEqual(await save(e, A, null, session("A1"), ctx), { kind: "cancelled" });
  assert.equal(storage.data.size, 0);
});

// ---- 미지원 환경(A안) ------------------------------------------------------------

test("Web Locks 미지원: 읽기만 가능, 자동 저장·복사·삭제는 unsupported, 저장소 무변경", async () => {
  const raw = legacyRaw();
  const storage = memoryStorage({ [LEGACY_READING_SESSION_KEY]: raw });
  const withLocks = env(storage);
  const v = okVersion(await save(withLocks.env, A, null, session("A1")), 1);
  const snapshot = new Map(storage.data);
  const writesBefore = storage.writes.length;
  const e: ReadingStorageEnv = { storage, locks: null };
  assert.equal(readingStorageCapability(e), "readOnly");
  assert.equal(readReadingSession(e, SCOPE, A).kind, "ok");
  assert.equal(readLegacyReadingSession(e).kind, "ok");
  assert.deepEqual(await save(e, A, v, session("A2")), { kind: "unsupported" });
  assert.deepEqual(await copyToEmptyReadingSession(e, { scope: SCOPE, owner: B, source: session("X"), mode: "textOnly", ...current }), { kind: "unsupported" });
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: v, ...current }), { kind: "unsupported" });
  assert.equal(storage.writes.length, writesBefore);
  assert.deepEqual(storage.data, snapshot);
  assert.equal(originalTextDownload(session("A2"), NOW).content, "〔A2〕合成の原文です。");
  assert.equal(rawBackupDownload(raw, NOW).content, raw);
  assert.equal(readingStorageCapability({ storage: null, locks: null }), "unavailable");
  assert.equal(readingStorageCapability({ storage, locks: { request: undefined } as never }), "readOnly");
});

// ---- 삭제(사용자 확인 후) ---------------------------------------------------------

test("삭제: 현재 owner 키 하나만, 버전이 정확히 맞을 때만", async () => {
  const raw = legacyRaw();
  const { env: e, storage } = env(memoryStorage({ [LEGACY_READING_SESSION_KEY]: raw }));
  const v1 = okVersion(await save(e, A, null, session("A1")), 1);
  await save(e, B, null, session("B1"));
  const v2 = okVersion(await save(e, A, v1, session("A2")), 2);
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: v1, ...current }), { kind: "conflict", stored: v2 });
  assert.deepEqual(
    await removeReadingSession(e, { scope: SCOPE, owner: A, expected: { instanceId: "other", revision: 2 }, ...current }),
    { kind: "conflict", stored: v2 },
  );
  assert.ok(storage.data.has(readingSessionKey(SCOPE, A)));
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: A, expected: v2, ...current }), { kind: "ok" });
  assert.ok(!storage.data.has(readingSessionKey(SCOPE, A)));
  assert.ok(storage.data.has(readingSessionKey(SCOPE, B)));
  assert.equal(storage.data.get(LEGACY_READING_SESSION_KEY), raw);
  storage.data.set(readingSessionKey(SCOPE, G), "{x");
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: G, expected: v2, ...current }), { kind: "conflict", stored: "corrupt" });
  assert.equal(storage.data.get(readingSessionKey(SCOPE, G)), "{x");
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: G, expected: "corrupt", ...current }), { kind: "ok" });
  // 정상 세션은 "corrupt" 지정으로 지울 수 없다.
  const vb = ver(e, B)!;
  assert.deepEqual(await removeReadingSession(e, { scope: SCOPE, owner: B, expected: "corrupt", ...current }), { kind: "conflict", stored: vb });
});

test("다운로드는 원자료를 바꾸지 않은 그대로, 파일 이름에 원문 없음", () => {
  const raw = legacyRaw();
  const d = rawBackupDownload(raw, NOW);
  assert.equal(d.content, raw);
  assert.equal(d.mimeType, "application/json");
  assert.equal(d.fileName, "reading-session-backup-20261008030000.json");
  const t = originalTextDownload(session("T"), NOW);
  assert.equal(t.fileName, "reading-text-20261008030000.txt");
  assert.doesNotMatch(t.fileName + d.fileName, /〔|原文/);
});
