// 학습 계획 → 복습 탭 실행 (Gate C-1b). 진행 중인 복습 세션을 보호한다.
//
// 규칙 (references/plans/learning-plan-tab/gate-c1a/REPORT.md 3-2, C-1b 승인):
// - 진행 중 세션이 있으면 바로 시작하지 않고 needsConfirm을 돌려준다.
//   화면은 이어하기 / 새 학습으로 바꾸기 / 취소를 묻는다.
// - 교체는 새 큐 조회가 성공하고 비어 있지 않을 때만 한다. 실패·빈 큐면
//   기존 세션을 그대로 둔다.
// - 조회하는 동안 세션이 바뀌었으면(다른 시작, 카드 진행) 덮어쓰지 않는다.
// - 계정이 바뀌었거나 취소된 요청의 늦은 응답은 버린다.
// - 실행 중 다시 누르면 busy로 무시한다(요청 1건).
// - 하루량으로 큐를 자르지 않는다. 큐 크기는 기존 모드 규칙 그대로다.
//
// React와 무관한 순수 모듈: page.tsx가 어댑터를 넘기고, 테스트는 가짜
// 어댑터로 돌린다. Node 타입 제거 실행 때문에 값 import를 쓰지 않는다.

import type { PlanDeckRef } from "./learningPlan";

export type PlanStudyMode = "new" | "today";

export type PlanStudyTarget = { deck: PlanDeckRef; mode: PlanStudyMode };

/** 세션 식별: id는 시작/교체/초기화마다 바뀌고, position은 카드 진행마다 바뀐다. */
export type StudySessionSnapshot = {
  id: number;
  position: number;
  /** 아직 평가하지 않은 카드가 남아 있는가. */
  inProgress: boolean;
  remaining: number;
};

export type PlanStudyAdapter<Item> = {
  getSession(): StudySessionSnapshot;
  getAccountEpoch(): number;
  fetchQueue(target: PlanStudyTarget): Promise<Item[]>;
  /** 새 큐로 세션을 바꾸고 복습 탭으로 이동. 성공·비어 있지 않을 때만 호출된다. */
  replaceSession(target: PlanStudyTarget, items: Item[]): void;
  /** 기존 세션 그대로 복습 탭으로 이동. */
  resumeSession(): void;
};

export type PlanStudyOutcome =
  | { kind: "started"; count: number }
  | { kind: "needsConfirm"; session: StudySessionSnapshot }
  | { kind: "resumed" }
  | { kind: "empty" }
  | { kind: "failed" }
  | { kind: "cancelled" }
  | { kind: "busy" }
  | { kind: "stale" }
  | { kind: "sessionChanged" };

export type PlanStudyLauncher = {
  /** 처음 누를 때. 진행 중 세션이 있으면 needsConfirm. */
  start(target: PlanStudyTarget): Promise<PlanStudyOutcome>;
  /** 확인창에서 "새 학습으로 바꾸기". expected는 확인창을 띄울 때의 세션. */
  replace(target: PlanStudyTarget, expected: StudySessionSnapshot): Promise<PlanStudyOutcome>;
  /** 확인창에서 "이어하기". */
  resume(): PlanStudyOutcome;
  /** 확인창 닫기, 또는 조회 중 취소. 진행 중인 조회 결과는 버린다. */
  cancel(): PlanStudyOutcome;
  isBusy(): boolean;
};

function sameSession(a: StudySessionSnapshot, b: StudySessionSnapshot): boolean {
  return a.id === b.id && a.position === b.position;
}

export function createPlanStudyLauncher<Item>(adapter: PlanStudyAdapter<Item>): PlanStudyLauncher {
  let busy = false;
  let ticket = 0;

  async function run(target: PlanStudyTarget, expected: StudySessionSnapshot): Promise<PlanStudyOutcome> {
    if (busy) return { kind: "busy" };
    busy = true;
    const myTicket = ++ticket;
    const epoch = adapter.getAccountEpoch();
    try {
      let items: Item[];
      try {
        items = await adapter.fetchQueue(target);
      } catch {
        if (myTicket !== ticket) return { kind: "cancelled" };
        if (epoch !== adapter.getAccountEpoch()) return { kind: "stale" };
        return { kind: "failed" };
      }
      if (myTicket !== ticket) return { kind: "cancelled" };
      if (epoch !== adapter.getAccountEpoch()) return { kind: "stale" };
      if (!sameSession(adapter.getSession(), expected)) return { kind: "sessionChanged" };
      if (items.length === 0) return { kind: "empty" };
      adapter.replaceSession(target, items);
      return { kind: "started", count: items.length };
    } finally {
      if (myTicket === ticket) busy = false;
    }
  }

  return {
    async start(target) {
      if (busy) return { kind: "busy" };
      const session = adapter.getSession();
      if (session.inProgress) return { kind: "needsConfirm", session };
      return run(target, session);
    },
    replace(target, expected) {
      return run(target, expected);
    },
    resume() {
      adapter.resumeSession();
      return { kind: "resumed" };
    },
    cancel() {
      ticket += 1; // 진행 중인 조회의 결과를 무효로
      busy = false;
      return { kind: "cancelled" };
    },
    isBusy() {
      return busy;
    },
  };
}
