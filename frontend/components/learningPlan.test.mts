// 학습 계획 순수 계산 테스트. 실행: node --test components/learningPlan.test.mts
// (Node 22.18+/24의 타입 제거 실행. 앱 빌드/tsconfig 포함 대상이 아니다.)
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  addDays,
  computePlan,
  formatLongDate,
  inclusiveSpan,
  matchingPreset,
  parseDailyWords,
  readyProgress,
  seoulToday,
  stepDailyWords,
  targetForPreset,
  toDayNumber,
} from "./learningPlan.ts";
import type { PlanDraft, PlanProgress } from "./learningPlan.ts";

const deck = { kind: "subscribed" as const, id: 4 };
const ready = (total: number, seen: number): PlanProgress => ({
  state: "ready",
  deck,
  total,
  seen,
  scope: "account_shared",
  metricVersion: "test",
  asOf: "2026-10-05T00:00:00Z",
});
const draft = (over: Partial<PlanDraft> = {}): PlanDraft => ({
  deck,
  startDate: "2026-10-05",
  targetDate: "2026-11-03",
  dailyWords: 10,
  ...over,
});
const run = (d: PlanDraft, p: PlanProgress = ready(360, 72), today = "2026-10-05") =>
  computePlan({ draft: d, progress: p, today });

test("검산: 360/72, 30일, 하루 10개 → 1일 여유, 예상 11/2", () => {
  const r = run(draft());
  assert.equal(r.status, "ahead");
  assert.equal(r.remaining, 288);
  assert.equal(r.daysLeft, 30);
  assert.equal(r.capacity, 300);
  assert.equal(r.daysNeeded, 29);
  assert.equal(r.predictedDate, "2026-11-02");
  assert.equal(r.margin, 1);
  assert.equal(r.minDaily, 10);
  assert.equal(r.progressRatio, 0.2);
  assert.equal(r.capacityBar, 1);
  assert.equal(r.remainingBar, 288 / 300);
});

test("검산: 하루 8개 → 6일 초과, 예상 11/9, 최소량 10", () => {
  const r = run(draft({ dailyWords: 8 }));
  assert.equal(r.status, "late");
  assert.equal(r.capacity, 240);
  assert.equal(r.daysNeeded, 36);
  assert.equal(r.predictedDate, "2026-11-09");
  assert.equal(r.margin, -6);
  assert.equal(r.minDaily, 10);
  // 잔량이 계획보다 많으면 남음 막대가 축(=잔량)을 채운다.
  assert.equal(r.remainingBar, 1);
  assert.equal(r.capacityBar, 240 / 288);
});

test("검산: 14일 하루 21개 → 목표일 일치", () => {
  const r = run(draft({ targetDate: "2026-10-18", dailyWords: 21 }));
  assert.equal(r.span, 14);
  assert.equal(r.capacity, 294);
  assert.equal(r.daysNeeded, 14);
  assert.equal(r.margin, 0);
  assert.equal(r.status, "onTime");
});

test("미확인 진도는 0이 아니라 null", () => {
  for (const state of ["loading", "error", "missing", "unavailable"] as const) {
    const r = run(draft(), { state, deck });
    assert.equal(r.status, "unknown");
    assert.equal(r.total, null);
    assert.equal(r.seen, null);
    assert.equal(r.remaining, null);
    assert.equal(r.capacity, null);
  }
});

test("다른 덱의 응답이나 불일치 응답은 버린다(clamp 없음)", () => {
  assert.equal(readyProgress({ ...ready(10, 3), deck: { kind: "personal", id: 4 } }, deck), null);
  assert.equal(readyProgress(ready(10, 11), deck), null);
  assert.equal(readyProgress(ready(10, -1), deck), null);
  assert.equal(readyProgress(ready(10.5, 1), deck), null);
  assert.equal(run(draft(), ready(10, 11)).status, "unknown");
});

test("빈 덱 / 모두 접함 / 하루 0개에서 NaN·Infinity·가짜 완료 없음", () => {
  const empty = run(draft(), ready(0, 0));
  assert.equal(empty.status, "emptyDeck");
  assert.equal(empty.progressRatio, null);
  assert.equal(empty.capacity, null);

  const all = run(draft(), ready(80, 80));
  assert.equal(all.status, "allSeen");
  assert.equal(all.predictedDate, null);
  assert.equal(all.progressRatio, 1);
  assert.equal(all.remainingBar, 0);

  const paused = run(draft({ dailyWords: 0 }));
  assert.equal(paused.status, "paused");
  assert.equal(paused.capacity, 0);
  assert.equal(paused.daysNeeded, null);
  assert.equal(paused.predictedDate, null);
  for (const r of [empty, all, paused]) {
    for (const v of Object.values(r)) {
      if (typeof v === "number") assert.ok(Number.isFinite(v), JSON.stringify(r));
    }
  }
});

test("날짜·하루량이 틀리면 invalid, 진도는 그대로 보인다", () => {
  const backwards = run(draft({ targetDate: "2026-10-04" }));
  assert.equal(backwards.status, "invalid");
  assert.equal(backwards.dateValid, false);
  assert.equal(backwards.remaining, 288);
  assert.equal(run(draft({ startDate: "2026-02-30" })).status, "invalid");
  assert.equal(run(draft({ dailyWords: null })).status, "invalid");
});

test("같은 날 시작·목표는 1일", () => {
  assert.equal(inclusiveSpan("2026-10-05", "2026-10-05"), 1);
  const r = run(draft({ targetDate: "2026-10-05", dailyWords: 288 }));
  assert.equal(r.daysLeft, 1);
  assert.equal(r.status, "onTime");
});

test("윤년과 연말 경계", () => {
  assert.equal(inclusiveSpan("2028-02-28", "2028-03-01"), 3);
  assert.equal(inclusiveSpan("2026-02-28", "2026-03-01"), 2);
  assert.equal(addDays("2026-12-31", 1), "2027-01-01");
  assert.equal(toDayNumber("2027-02-29"), null);
  assert.equal(targetForPreset("2026-12-20", 14), "2027-01-02");
});

test("과거 시작일은 저장 전후 모두 서울 오늘부터 계산 (C-0 검산표)", () => {
  // 10/5 시작 계획을 10/15에 열었을 때, 접함 172 → 잔량 188.
  const r = run(draft(), ready(360, 172), "2026-10-15");
  assert.equal(r.baseDate, "2026-10-15");
  assert.equal(r.daysLeft, 20);
  assert.equal(r.capacity, 200);
  assert.equal(r.daysNeeded, 19);
  assert.equal(r.predictedDate, "2026-11-02");
  assert.equal(r.margin, 1);
  // 학습량이 그대로면 다음 날도 같은 예상일, 학습하면 그만큼만 바뀐다.
  assert.equal(run(draft(), ready(360, 182), "2026-10-16").predictedDate, "2026-11-02");
  assert.equal(run(draft(), ready(360, 172), "2026-10-16").predictedDate, "2026-11-03");
  // 미래 시작 계획은 시작일 기준.
  assert.equal(run(draft(), ready(360, 72), "2026-10-01").baseDate, "2026-10-05");
});

test("기간이 지난 계획은 만료, 자동 연장·음수 나눗셈 없음", () => {
  const r = run(draft(), ready(360, 72), "2026-11-04");
  assert.equal(r.status, "expired");
  assert.equal(r.daysLeft, 0);
  assert.equal(r.capacity, null);
  assert.equal(r.minDaily, null);
});

test("최소량이 500을 넘으면 조정 제안 없음", () => {
  const r = run(draft({ targetDate: "2026-10-05", dailyWords: 10 }), ready(2000, 0));
  assert.equal(r.status, "late");
  assert.equal(r.minDaily, null);
});

test("하루량 입력 검증: 빈 값/소수/음수/문자/범위", () => {
  assert.equal(parseDailyWords("10"), 10);
  assert.equal(parseDailyWords(" 0 "), 0);
  assert.equal(parseDailyWords("500"), 500);
  assert.equal(parseDailyWords("501"), null);
  assert.equal(parseDailyWords(""), null);
  assert.equal(parseDailyWords("1.5"), null);
  assert.equal(parseDailyWords("-1"), null);
  assert.equal(parseDailyWords("1e2"), null);
  assert.equal(parseDailyWords("열"), null);
  assert.equal(stepDailyWords(500, 1), 500);
  assert.equal(stepDailyWords(0, -1), 0);
  assert.equal(stepDailyWords(null, 1), null);
});

test("프리셋 일치와 서울 오늘", () => {
  assert.equal(matchingPreset("2026-10-05", "2026-11-03"), 30);
  assert.equal(matchingPreset("2026-10-05", "2026-11-04"), null);
  // UTC 15:00 = 서울 다음 날 00:00
  assert.equal(seoulToday(new Date("2026-10-31T14:59:59Z")), "2026-10-31");
  assert.equal(seoulToday(new Date("2026-10-31T15:00:00Z")), "2026-11-01");
  assert.equal(formatLongDate("2026-10-05"), "10월 5일 월요일");
});
