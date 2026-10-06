// 학습 계획 기기 저장 테스트. 실행: node --test components/learningPlanStorage.test.mts
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  draftFromStored,
  learningPlanStorageKey,
  learningPlanStorageScope,
  parseStoredPlan,
  readStoredPlan,
  removeStoredPlan,
  writeStoredPlan,
} from "./learningPlanStorage.ts";

function memoryStorage(seed: Record<string, string> = {}) {
  const data = new Map(Object.entries(seed));
  return {
    data,
    getItem: (k: string) => (data.has(k) ? (data.get(k) as string) : null),
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
  };
}

const NOW = new Date("2026-10-05T04:00:00Z");
const draft = {
  deck: { kind: "subscribed" as const, id: 4 },
  startDate: "2026-10-05",
  targetDate: "2026-11-03",
  dailyWords: 10,
};

test("키는 백엔드 환경과 계정별로 다르다", () => {
  const local = learningPlanStorageScope("http://127.0.0.1:8000/");
  const prod = learningPlanStorageScope("https://API.example.com/v1/");
  assert.equal(local, learningPlanStorageScope("http://127.0.0.1:8000"));
  assert.notEqual(local, prod);
  assert.equal(prod, encodeURIComponent("https://api.example.com/v1"));
  assert.notEqual(learningPlanStorageKey(local, 1), learningPlanStorageKey(local, 2));
  assert.notEqual(learningPlanStorageKey(local, 1), learningPlanStorageKey(prod, 1));
  assert.ok(learningPlanStorageKey(local, 1).startsWith("jp-vocab-reader:learning-plan-v1:"));
});

test("저장 → 읽기 왕복, 설정만 저장", () => {
  const storage = memoryStorage();
  const key = learningPlanStorageKey("s", 7);
  const written = writeStoredPlan(storage, key, draft, NOW);
  assert.equal(written.kind, "ok");
  assert.deepEqual(Object.keys(JSON.parse(storage.data.get(key) as string)).sort(), [
    "dailyWords", "deck", "metricVersion", "savedAt", "startDate", "targetDate", "version",
  ]);
  const read = readStoredPlan(storage, key);
  assert.equal(read.kind, "ok");
  if (read.kind === "ok") assert.deepEqual(draftFromStored(read.plan), draft);
});

test("없는 키는 empty, 다른 키는 건드리지 않음", () => {
  const storage = memoryStorage({ "jp-vocab-reader:access-token": "t", "jp-vocab-reader:reading-session-v1": "{}" });
  assert.deepEqual(readStoredPlan(storage, learningPlanStorageKey("s", 1)), { kind: "empty" });
  writeStoredPlan(storage, learningPlanStorageKey("s", 1), draft, NOW);
  removeStoredPlan(storage, learningPlanStorageKey("s", 1));
  assert.equal(storage.data.get("jp-vocab-reader:access-token"), "t");
  assert.equal(storage.data.get("jp-vocab-reader:reading-session-v1"), "{}");
  assert.equal(storage.data.size, 2);
});

test("깨진 데이터는 corrupt이며 원자료를 지우지 않는다", () => {
  const key = learningPlanStorageKey("s", 1);
  const good = JSON.stringify({ version: 1, metricVersion: "first-review-v1", ...draft, savedAt: NOW.toISOString() });
  const bad = [
    "{not json",
    "null",
    "[]",
    JSON.stringify({ ...JSON.parse(good), version: 2 }),
    JSON.stringify({ ...JSON.parse(good), deck: { kind: "all", id: 1 } }),
    JSON.stringify({ ...JSON.parse(good), deck: { kind: "personal", id: 0 } }),
    JSON.stringify({ ...JSON.parse(good), targetDate: "2026-10-04" }),
    JSON.stringify({ ...JSON.parse(good), startDate: "2026-02-30" }),
    JSON.stringify({ ...JSON.parse(good), dailyWords: 1.5 }),
    JSON.stringify({ ...JSON.parse(good), dailyWords: 501 }),
    JSON.stringify({ ...JSON.parse(good), dailyWords: "10" }),
    JSON.stringify({ ...JSON.parse(good), savedAt: "yesterday" }),
  ];
  assert.notEqual(parseStoredPlan(good), null);
  for (const raw of bad) {
    const storage = memoryStorage({ [key]: raw });
    assert.deepEqual(readStoredPlan(storage, key), { kind: "corrupt" }, raw);
    assert.equal(storage.data.get(key), raw);
  }
});

test("쓰기 실패와 접근 거부는 error/unavailable, 예외를 밖으로 던지지 않음", () => {
  const key = learningPlanStorageKey("s", 1);
  const full = { getItem: () => null, setItem: () => { throw new Error("QuotaExceededError"); }, removeItem: () => undefined };
  assert.deepEqual(writeStoredPlan(full, key, draft, NOW), { kind: "error" });
  const denied = { getItem: () => { throw new Error("SecurityError"); }, setItem: () => undefined, removeItem: () => undefined };
  assert.deepEqual(readStoredPlan(denied, key), { kind: "unavailable" });
  assert.deepEqual(readStoredPlan(null, key), { kind: "unavailable" });
});

test("저장할 수 없는 초안은 쓰지 않는다", () => {
  const storage = memoryStorage();
  const key = learningPlanStorageKey("s", 1);
  for (const bad of [
    { ...draft, deck: null },
    { ...draft, dailyWords: null },
    { ...draft, targetDate: "2026-10-01" },
  ]) {
    assert.deepEqual(writeStoredPlan(storage, key, bad, NOW), { kind: "error" });
  }
  assert.equal(storage.data.size, 0);
});
