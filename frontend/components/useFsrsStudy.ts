"use client";

// FSRS 계정의 복습 회차를 화면에 잇는 훅 (Gate C-2c).
//
// 회차 로직은 fsrsStudyController.ts(React 없음, Node 테스트 대상)에 있다. 이 훅은 컨트롤러를
// 한 번 만들고, 다시 그리기와 브라우저 이벤트(대기 타이머·앱 복귀·beforeunload)만 잇는다.

import { useEffect, useRef, useState } from "react";
import * as studySession from "./studySession";
import { pendingLaterCount, queueFailureKind, queuePath, studyCardFromQueueItem } from "./fsrsStudy";
import { createFsrsStudyController } from "./fsrsStudyController";
import type { FsrsStudyController, FsrsStudyDeps } from "./fsrsStudyController";

export type { FsrsPrimary, FsrsSnapshot, PlanEmptyReason, PreparedSession } from "./fsrsStudyController";

function newId(): string {
  const c = typeof crypto !== "undefined" ? crypto : null;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function useFsrsStudy(deps: FsrsStudyDeps): FsrsStudyController {
  const depsRef = useRef(deps);
  depsRef.current = deps;
  const [, setRevision] = useState(0);
  const controllerRef = useRef<FsrsStudyController | null>(null);
  if (!controllerRef.current) {
    controllerRef.current = createFsrsStudyController(
      {
        session: studySession,
        helpers: { pendingLaterCount, queueFailureKind, queuePath, studyCardFromQueueItem },
      },
      {
        getAccountEpoch: () => depsRef.current.getAccountEpoch(),
        get: (path) => depsRef.current.get(path),
        post: (path, body) => depsRef.current.post(path, body),
        loadRecentPracticeCards: (ids) => depsRef.current.loadRecentPracticeCards(ids),
        onReviewSaved: () => depsRef.current.onReviewSaved(),
        onModeChanged: () => depsRef.current.onModeChanged(),
      },
      {
        now: () => Date.now(),
        newId,
        setTimeout: (callback, ms) => window.setTimeout(callback, ms),
        onChange: () => setRevision((value) => value + 1),
      },
    );
  }
  const controller = controllerRef.current;

  // 대기 화면(곧 돌아옴)에서만 next_due_at에 맞춰 한 번 다시 조회한다. 카드가 보이면 걸지 않는다.
  const timer = controller.waitTimer();
  const timerKey = timer ? timer.key : "";
  useEffect(() => {
    const current = controller.waitTimer();
    if (!current) return;
    const id = window.setTimeout(current.fire, current.delay);
    return () => window.clearTimeout(id);
  }, [controller, timerKey]);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") controller.onVisible();
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [controller]);

  // 전송 중·결과 미확정일 때만 등록하고, 끝나면 해제한다. 저장 보장 수단이 아니다.
  const warnBeforeUnload = controller.shouldWarnBeforeUnload();
  useEffect(() => {
    if (!warnBeforeUnload) return;
    function onBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [warnBeforeUnload]);

  return controller;
}
