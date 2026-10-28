// FSRS 회차 화면 연결 도우미 테스트 (Gate C-2c). 실행: node --test components/fsrsStudy.test.mts
// 순수 함수 검사다. 실제 화면 동작은 REPORT의 브라우저 검사로 따로 확인한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MODE_PROBE_PATH,
  goalReachedText,
  haltText,
  newGoalLine,
  noticeText,
  pendingLaterCount,
  probeOutcome,
  queueFailureKind,
  queuePath,
  queueTargetFor,
  studyCardFromQueueItem,
} from "./fsrsStudy.ts";

test("모드 판별: 409 srs_mode_not_fsrs만 legacy, 200은 FSRS, 그 밖은 오류 (M1, M2)", () => {
  assert.equal(MODE_PROBE_PATH, "/study-queue?limit=1");
  assert.equal(probeOutcome({ kind: "ok", body: {} }), "fsrs");
  assert.equal(probeOutcome({ kind: "http", status: 409, detail: "srs_mode_not_fsrs" }), "legacy");
  for (const result of [
    { kind: "http" as const, status: 409, detail: "something_else" },
    { kind: "http" as const, status: 401, detail: null },
    { kind: "http" as const, status: 404, detail: null },
    { kind: "http" as const, status: 400, detail: "invalid scope" },
    { kind: "http" as const, status: 500, detail: null },
    { kind: "network" as const },
  ]) {
    assert.equal(probeOutcome(result), "error", JSON.stringify(result));
  }
});

test("덱·모드 → 큐 대상: today·new 실제 복습, unknown·uncertain·all 연습, recent는 selected", () => {
  assert.deepEqual(queueTargetFor("all", "today"), { scope: "all", kind: "review", mode: "today", planDailyNew: null });
  assert.deepEqual(queueTargetFor("12", "new", { planDailyNew: 5 }),
    { scope: "personal_deck", deckId: 12, kind: "review", mode: "new", planDailyNew: 5 });
  assert.deepEqual(queueTargetFor("shared:7", "today", { planDailyNew: 3 }),
    { scope: "subscribed_deck", deckId: 7, kind: "review", mode: "today", planDailyNew: 3 });
  // 계획 하루량은 덱 범위에서만
  assert.equal((queueTargetFor("all", "new", { planDailyNew: 5 }) as { planDailyNew: number | null }).planDailyNew, null);
  assert.deepEqual(queueTargetFor("all", "all"), { scope: "all", kind: "practice", statuses: ["unknown", "uncertain"] });
  assert.deepEqual(queueTargetFor("3", "unknown"), { scope: "personal_deck", deckId: 3, kind: "practice", statuses: ["unknown"] });
  assert.deepEqual(queueTargetFor("shared:9", "recent", { recentIds: [5, 5, 6, -1, 0] }), { kind: "selected", cardIds: [5, 6] });
  assert.equal(queueTargetFor("all", "recent", { recentIds: [] }), null);
  assert.equal(queueTargetFor("abc", "today"), null);
  const many = Array.from({ length: 250 }, (_, i) => i + 1);
  const selected = queueTargetFor("all", "recent", { recentIds: many }) as { cardIds: number[] };
  assert.equal(selected.cardIds.length, 200);
  assert.equal(selected.cardIds[0], 51); // 가장 최근 200개
});

test("큐 경로: 첫 페이지(커서 없음), limit 10, 제외 목록 전송 (Q1, L6)", () => {
  const review = queueTargetFor("shared:7", "new", { planDailyNew: 4 });
  assert.ok(review);
  const path = queuePath(review, [["exclude_card", "lexeme:3"], ["exclude_card", "personal:9"]]);
  assert.equal(path,
    "/study-queue?scope=subscribed_deck&deck_id=7&mode=new&limit=10&plan_daily_new=4&exclude_card=lexeme%3A3&exclude_card=personal%3A9");
  assert.ok(!path.includes("cursor"));
  const practice = queueTargetFor("all", "all");
  assert.ok(practice);
  assert.equal(queuePath(practice, []), "/study-queue?scope=all&mode=practice&status=unknown&status=uncertain&limit=100");
  const recent = queueTargetFor("all", "recent", { recentIds: [4, 8] });
  assert.ok(recent);
  assert.equal(queuePath(recent, []), "/study-queue?mode=selected&card_id=4&card_id=8&limit=10");
});

test("큐 오류: 모드 변경·인증·제외 한도는 정지, 나머지는 다시 불러오기", () => {
  assert.deepEqual(queueFailureKind({ kind: "http", status: 409, detail: "srs_mode_not_fsrs" }), { halt: "mode_changed" });
  assert.deepEqual(queueFailureKind({ kind: "http", status: 401, detail: null }), { halt: "auth" });
  assert.deepEqual(queueFailureKind({ kind: "http", status: 400, detail: "too_many_excluded_cards" }), { halt: "deferred_limit" });
  assert.deepEqual(queueFailureKind({ kind: "http", status: 500, detail: null }), { failure: true });
  assert.deepEqual(queueFailureKind({ kind: "network" }), { failure: true });
  assert.deepEqual(queueFailureKind({ kind: "http", status: 400, detail: "invalid scope" }), { failure: true });
});

test("큐 항목 → 카드 지면: 개인은 양수 id, 구독은 음수 id와 lexeme_id", () => {
  const personal = studyCardFromQueueItem({
    card_kind: "personal", card_id: 5, status: "unknown", source_label: "기본 단어장",
    review: { path: "/study-items/5/review", shared_deck_id: null },
    content: { surface: "猫", base_form: "猫", reading: "ねこ", part_of_speech: "名詞", meaning_ko: "고양이",
      dictionary_gloss: null, example_sentence: "猫がいる", context_explanation_ko: null, jlpt_level: "N5" },
  });
  assert.ok(personal);
  assert.equal(personal.id, 5);
  assert.equal(personal.item_type, "vocab");
  assert.equal(personal.vocab_item_id, 5);
  assert.equal(personal.meaning_ko, "고양이");
  assert.equal(personal.dictionary_gloss, "");
  const lexeme = studyCardFromQueueItem({
    card_kind: "lexeme", card_id: 8, status: "unclassified", source_label: "N5 덱",
    review: { path: "/shared-decks/9/words/8/review", shared_deck_id: 9 }, content: { surface: "犬", meaning_ko: "개" },
  });
  assert.ok(lexeme);
  assert.equal(lexeme.id, -8);
  assert.equal(lexeme.lexeme_id, 8);
  assert.equal(lexeme.shared_deck_id, 9);
  assert.equal(lexeme.item_type, "lexeme");
  for (const bad of [null, 3, { card_kind: "deck", card_id: 1, content: {} }, { card_kind: "personal", card_id: 0, content: {} },
    { card_kind: "personal", card_id: 1 }]) {
    assert.equal(studyCardFromQueueItem(bad), null);
  }
});

test("신규 목표 줄: 확인 불가를 0으로 쓰지 않고 기준을 밝힌다 (M10)", () => {
  assert.equal(newGoalLine({ kind: "exact", basis: "account", introduced: 3, goal: 20, remaining: 17 }),
    "오늘 새 단어 3개 / 목표 20개 · 계정 기준");
  assert.equal(newGoalLine({ kind: "exact", basis: "plan", introduced: 5, goal: 5, remaining: 0 }),
    "오늘 새 단어 5개 / 목표 5개 · 학습 계획 기준");
  const unknown = newGoalLine({ kind: "unknown", basis: "account", atLeast: 2, goal: 20 });
  assert.equal(unknown, "오늘 새 단어: 확인할 수 없음 (적어도 2개) · 목표 20개 · 계정 기준");
  assert.ok(unknown && !/새 단어 0개/.test(unknown));
  assert.equal(newGoalLine(null), null);
  assert.equal(goalReachedText({ kind: "exact", basis: "plan", introduced: 6, goal: 6, remaining: 0 }),
    "오늘 학습 계획의 새 단어 목표 6개를 채웠어요");
  assert.equal(goalReachedText({ kind: "exact", basis: "account", introduced: 20, goal: 20, remaining: 0 }),
    "오늘 새 단어 목표 20개를 채웠어요");
});

test("화면 문구에 '학습 완료'가 없다 (H7)", () => {
  const texts = [
    haltText("deferred_limit"), haltText("mode_changed"), haltText("upgrade_required"), haltText("auth"),
    haltText("request_id_conflict"), haltText("unexpected"),
    noticeText("conflict"), noticeText("unavailable"), noticeText("not_found"), noticeText(null),
  ];
  for (const text of texts) assert.ok(!/학습 완료|완료했/.test(text), text);
  assert.equal(noticeText(null), "");
});

test("미래 대기 수(recent '남은 단어 연습하기')", () => {
  assert.equal(pendingLaterCount({ counts: { pending_later: 3 } }), 3);
  assert.equal(pendingLaterCount({ counts: { pending_later: -1 } }), 0);
  assert.equal(pendingLaterCount({}), 0);
  assert.equal(pendingLaterCount(null), 0);
});
