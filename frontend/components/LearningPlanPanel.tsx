"use client";

// 학습 계획 컨테이너 (Gate C-1a). LearningPlanSection(표시)에 실제 진도 조회와
// 이 기기 저장을 붙인다. 학습 시작(C-1b)과 메뉴 연결(Gate D)은 아직 없다.
//
// 보호 규칙 (references/plans/learning-plan-tab/gate-c0/CONTRACT_REVIEW.md 2절):
// - 로그인 계정(account)이 정해진 뒤에만 그 계정의 키를 읽는다. 로그아웃/개발
//   계정이면 어떤 키도 읽지 않고 계획 없음 + 로그인 안내.
// - 계정·환경 키가 바뀌면 계획·편집값·진도를 즉시 버리고, 이전 키나 이전 덱에
//   대한 늦은 응답은 무시한다.
// - 저장은 명시적 명령만. 실패하면 기존 저장본을 그대로 두고 실패를 알린다.
// - 깨진 데이터는 자동으로 지우지 않는다. 사용자가 확인하면 그 키 하나만 지운다.
// - 다른 창의 같은 키 변경은 편집 중이 아니면 반영, 편집 중이면 안내만 한다.
// - 저장·편집은 진도 조회(GET) 외에 어떤 요청도 보내지 않는다(복습/SRS 무관).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LearningPlanSection, type PlanNotice, type PlanStartConfirm } from "./LearningPlanSection";
import {
  deckKey,
  sameDraft,
  seoulToday,
  targetForPreset,
  type PlanDeckOption,
  type PlanDeckRef,
  type PlanDraft,
  type PlanProgress,
} from "./learningPlan";
import {
  draftFromStored,
  learningPlanStorageKey,
  readStoredPlan,
  removeStoredPlan,
  writeStoredPlan,
} from "./learningPlanStorage";
import type {
  PlanStudyLauncher,
  PlanStudyMode,
  PlanStudyOutcome,
  PlanStudyTarget,
  StudySessionSnapshot,
} from "./planStudyLauncher";

export type LearningPlanProgressResponse = {
  deck_kind: "personal" | "subscribed";
  deck_id: number;
  total: number;
  seen: number;
  progress_scope: "deck_cards" | "account_shared";
  metric_version: string;
  today: string;
  as_of: string;
};

/**
 * 같은 계정에서 탭을 오갈 때 저장하지 않은 편집을 메모리에만 보관한다(기기에
 * 쓰지 않음). 키는 계정별 저장 키. page.tsx가 계정 경계에서 통째로 비운다.
 * baseSaved는 편집을 시작할 때의 저장본: 돌아왔을 때 저장본이 그사이 바뀌었으면
 * (다른 창 저장) 덮지 않고 "다른 창에서 계획이 바뀌었어요"로 안내한다.
 */
export type PlanDraftMemoryEntry = { draft: PlanDraft; baseSaved: PlanDraft | null };
export type PlanDraftMemory = {
  read(key: string): PlanDraftMemoryEntry | null;
  write(key: string, entry: PlanDraftMemoryEntry | null): void;
};

export type LearningPlanPanelProps = {
  /** 로그인한 실제 계정. null = 로그아웃·개발 계정·아직 확인 전. */
  account: { userId: number } | null;
  /** learningPlanStorageScope(API_BASE_URL). */
  storageScope: string;
  /** null = 아직 불러오지 못함. */
  personalDecks: Array<{ id: number; name: string }> | null;
  subscribedDecks: Array<{ id: number; title: string }> | null;
  /** GET 요청. 실패하면 throw. */
  request: (path: string) => Promise<unknown>;
  /** 오류의 HTTP 상태(없으면 null). 404를 "덱을 찾을 수 없어요"로 구분한다. */
  getErrorStatus: (error: unknown) => number | null;
  onOpenAccount?: () => void;
  onGoToHistory?: () => void;
  /** 복습 탭 실행기(page.tsx가 만든 것). 없으면 학습 시작은 미연결. */
  studyLauncher?: PlanStudyLauncher;
  /** 패드 아래 보조 줄(이전 분류 초안 안내 등). 계정과 무관한 기기 자료. */
  footer?: React.ReactNode;
  /** 탭 왕복용 미저장 편집 메모리. 없으면 탭을 떠날 때 편집이 사라진다. */
  draftMemory?: PlanDraftMemory;
  /** 테스트용 시계 주입. 기본은 현재 시각. */
  now?: () => Date;
};

const DEFAULT_DAILY_WORDS = 10;
const DEFAULT_SPAN_DAYS = 30;
const METRIC_VERSION = "first-review-v1";

function safeStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function defaultDraft(today: string, deck: PlanDeckRef | null): PlanDraft {
  return {
    deck,
    startDate: today,
    targetDate: targetForPreset(today, DEFAULT_SPAN_DAYS) ?? today,
    dailyWords: DEFAULT_DAILY_WORDS,
  };
}

function isValidProgress(body: unknown, deck: PlanDeckRef): body is LearningPlanProgressResponse {
  if (!body || typeof body !== "object") return false;
  const b = body as Record<string, unknown>;
  return (
    b.deck_kind === deck.kind &&
    b.deck_id === deck.id &&
    b.metric_version === METRIC_VERSION &&
    (b.progress_scope === "deck_cards" || b.progress_scope === "account_shared") &&
    typeof b.today === "string" &&
    typeof b.as_of === "string" &&
    Number.isSafeInteger(b.total) &&
    Number.isSafeInteger(b.seen)
  );
}

export function LearningPlanPanel({
  account,
  storageScope,
  personalDecks,
  subscribedDecks,
  request,
  getErrorStatus,
  onOpenAccount,
  onGoToHistory,
  studyLauncher,
  footer,
  draftMemory,
  now = () => new Date(),
}: LearningPlanPanelProps) {
  const storageKey = account ? learningPlanStorageKey(storageScope, account.userId) : null;

  const decks: PlanDeckOption[] | null = useMemo(() => {
    if (!account) return [];
    if (personalDecks === null || subscribedDecks === null) return null;
    return [
      ...personalDecks.map((d) => ({ ref: { kind: "personal" as const, id: d.id }, name: d.name })),
      ...subscribedDecks.map((d) => ({ ref: { kind: "subscribed" as const, id: d.id }, name: d.title })),
    ];
  }, [account, personalDecks, subscribedDecks]);

  const [localToday, setLocalToday] = useState(() => seoulToday(now()));
  const [draft, setDraft] = useState<PlanDraft>(() => defaultDraft(localToday, null));
  const [saved, setSaved] = useState<PlanDraft | null>(null);
  const [saveError, setSaveError] = useState(false);
  const [readIssue, setReadIssue] = useState<"corrupt" | "unavailable" | null>(null);
  const [externalPlan, setExternalPlan] = useState<PlanDraft | null | "removed">(null);
  const [touched, setTouched] = useState(false);
  const [progress, setProgress] = useState<PlanProgress>({ state: "unavailable", deck: null });
  const [serverToday, setServerToday] = useState<string | null>(null);
  const [retryToken, setRetryToken] = useState(0);
  // 지금 화면 상태가 어느 키에서 읽은 것인지. 다르면(계정 전환 직후의 첫
  // 렌더) 이전 계정의 계획을 한 프레임도 보여 주지 않는다.
  const [loadedKey, setLoadedKey] = useState<string | null | undefined>(undefined);
  const isLoaded = loadedKey === storageKey;
  // 실행 상태: 확인창, 진행 중 표시, 결과 안내.
  const [confirmState, setConfirmState] = useState<{
    target: PlanStudyTarget;
    session: StudySessionSnapshot;
    busy: boolean;
  } | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [launchMessage, setLaunchMessage] = useState("");

  // 계정·환경 경계. 진도 요청은 이 세대와 요청 번호가 모두 맞을 때만 반영.
  const epochRef = useRef(0);
  const requestRef = useRef(0);

  // ---- 계정/키가 바뀌면 그 키의 저장본만 읽는다 ----
  useEffect(() => {
    epochRef.current += 1;
    requestRef.current += 1;
    const today = seoulToday(now());
    setLocalToday(today);
    setServerToday(null);
    setSaveError(false);
    setExternalPlan(null);
    setTouched(false);
    setProgress({ state: "unavailable", deck: null });
    // 계정 경계: 진행 중인 실행 조회 결과를 버리고 확인창을 닫는다.
    studyLauncher?.cancel();
    setConfirmState(null);
    setIsStarting(false);
    setLaunchMessage("");
    setLoadedKey(storageKey);
    if (!storageKey) {
      setSaved(null);
      setReadIssue(null);
      setDraft(defaultDraft(today, null));
      return;
    }
    const result = readStoredPlan(safeStorage(), storageKey);
    const stored = result.kind === "ok" ? draftFromStored(result.plan) : null;
    if (stored) {
      setSaved(stored);
      setDraft(stored);
      setReadIssue(null);
      // 첫 화면부터 "확인 중"으로: 미연결/0처럼 보이는 프레임을 만들지 않는다.
      setProgress({ state: "loading", deck: stored.deck });
    } else {
      setSaved(null);
      setDraft(defaultDraft(today, null));
      setReadIssue(result.kind === "corrupt" || result.kind === "unavailable" ? result.kind : null);
    }
    // 같은 계정에서 탭을 다시 열면 메모리의 미저장 편집을 이어 간다.
    const remembered = draftMemory?.read(storageKey) ?? null;
    if (remembered) {
      setDraft(remembered.draft);
      setTouched(true);
      if (remembered.draft.deck) setProgress({ state: "loading", deck: remembered.draft.deck });
      const sameBase =
        remembered.baseSaved === null
          ? stored === null
          : stored !== null && sameDraft(remembered.baseSaved, stored);
      // 떠나 있는 동안 다른 창이 저장했다면 편집을 덮지 않고 안내한다.
      if (!sameBase && result.kind !== "corrupt" && result.kind !== "unavailable") {
        setExternalPlan(stored ?? "removed");
      }
    }
    // now는 테스트 주입용이라 의존성에서 뺀다.
  }, [storageKey]);

  // 저장본이 없고 아직 손대지 않았으면, 덱 목록이 오면 첫 덱을 제안한다(저장 안 함).
  useEffect(() => {
    if (!isLoaded || !account || saved || touched || draft.deck || !decks || decks.length === 0) return;
    setDraft((current) => ({ ...current, deck: decks[0].ref }));
  }, [isLoaded, account, saved, touched, draft.deck, decks]);

  // ---- 서울 날짜 갱신: 자정이 지나거나 기기가 다시 활성화될 때 ----
  useEffect(() => {
    const check = () => {
      const today = seoulToday(now());
      setLocalToday((current) => (current === today ? current : today));
    };
    const timer = window.setInterval(check, 60_000);
    document.addEventListener("visibilitychange", check);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  }, []);

  // ---- 진도 조회 (읽기 전용) ----
  const currentDeckKey = draft.deck ? deckKey(draft.deck) : null;
  useEffect(() => {
    const deck = draft.deck;
    if (!isLoaded) return;
    if (!account || !deck) {
      requestRef.current += 1;
      setProgress({ state: "unavailable", deck: deck ?? null });
      return;
    }
    const epoch = epochRef.current;
    const id = ++requestRef.current;
    setProgress({ state: "loading", deck });
    const path = `/learning-plan/progress?deck_kind=${deck.kind}&deck_id=${deck.id}`;
    request(path).then(
      (body) => {
        if (epoch !== epochRef.current || id !== requestRef.current) return;
        if (!isValidProgress(body, deck) || body.seen > body.total) {
          setProgress({ state: "error", deck });
          return;
        }
        setServerToday(body.today);
        setProgress({
          state: "ready",
          deck,
          total: body.total,
          seen: body.seen,
          scope: body.progress_scope,
          metricVersion: body.metric_version,
          asOf: body.as_of,
        });
      },
      (error) => {
        if (epoch !== epochRef.current || id !== requestRef.current) return;
        setProgress({ state: getErrorStatus(error) === 404 ? "missing" : "error", deck });
      },
    );
    // request/getErrorStatus는 부모가 매번 새로 만들 수 있어 의존성에서 뺀다.
  }, [isLoaded, account?.userId, storageKey, currentDeckKey, retryToken, localToday]);

  // ---- 다른 창의 같은 키 변경 ----
  const isDirty = !(saved ? sameDraft(saved, draft) : !touched);
  const dirtyRef = useRef(isDirty);
  dirtyRef.current = isDirty;
  useEffect(() => {
    if (!storageKey) return;
    const onStorage = (event: StorageEvent) => {
      if (event.key !== storageKey) return;
      const result = readStoredPlan(safeStorage(), storageKey);
      const next = result.kind === "ok" ? draftFromStored(result.plan) : result.kind === "empty" ? "removed" : null;
      if (next === null) {
        setReadIssue("corrupt");
        return;
      }
      if (dirtyRef.current) {
        setExternalPlan(next);
        return;
      }
      applyExternal(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [storageKey]);

  const applyExternal = useCallback(
    (next: PlanDraft | "removed") => {
      setExternalPlan(null);
      setSaveError(false);
      setReadIssue(null);
      if (storageKey) draftMemory?.write(storageKey, null);
      if (next === "removed") {
        setSaved(null);
        setTouched(false);
        setDraft(defaultDraft(seoulToday(now()), decks && decks[0] ? decks[0].ref : null));
      } else {
        setSaved(next);
        setDraft(next);
      }
    },
    [decks, storageKey, draftMemory],
  );

  // ---- 명령 ----
  function handleDraftChange(next: PlanDraft) {
    setTouched(true);
    setSaveError(false);
    setDraft(next);
    // 메모리에만 보관(기기에 자동 저장하지 않음). 기준 저장본을 같이 남긴다.
    if (storageKey && isLoaded && account) {
      const prior = draftMemory?.read(storageKey);
      draftMemory?.write(storageKey, { draft: next, baseSaved: prior ? prior.baseSaved : saved });
    }
  }

  function handleSave() {
    if (!storageKey) return;
    const result = writeStoredPlan(safeStorage(), storageKey, draft, now());
    if (result.kind === "ok") {
      setSaved(draftFromStored(result.plan));
      setSaveError(false);
      setReadIssue(null);
      setExternalPlan(null);
      draftMemory?.write(storageKey, null);
    } else {
      setSaveError(true); // 기존 저장본(saved)은 그대로 둔다.
    }
  }

  // ---- 학습 시작 / 오늘 복습 (세션 보호는 studyLauncher가 맡음) ----
  function emptyMessage(mode: PlanStudyMode) {
    return mode === "new" ? "지금 학습할 새 단어가 없어요." : "오늘 복습할 단어가 없어요.";
  }

  function applyOutcome(target: PlanStudyTarget, outcome: PlanStudyOutcome) {
    switch (outcome.kind) {
      case "needsConfirm":
        setConfirmState({ target, session: outcome.session, busy: false });
        return;
      case "busy":
        return; // 이미 실행 중: 두 번째 클릭은 무시
      case "started":
      case "resumed":
      case "cancelled":
      case "stale":
        setConfirmState(null);
        setLaunchMessage("");
        return;
      case "empty":
        setConfirmState(null);
        setLaunchMessage(emptyMessage(target.mode));
        return;
      case "failed":
        setConfirmState(null);
        setLaunchMessage("학습 대상을 불러오지 못했어요. 지금 복습은 그대로예요.");
        return;
      case "sessionChanged":
        setConfirmState(null);
        setLaunchMessage("그사이 복습이 바뀌었어요. 다시 눌러 주세요.");
    }
  }

  async function launch(mode: PlanStudyMode) {
    if (!studyLauncher || !saved?.deck) return;
    const target: PlanStudyTarget = { deck: saved.deck, mode };
    const epoch = epochRef.current;
    setLaunchMessage("");
    setIsStarting(true);
    const outcome = await studyLauncher.start(target);
    if (epoch !== epochRef.current) return;
    if (outcome.kind !== "busy") setIsStarting(false);
    applyOutcome(target, outcome);
  }

  async function handleConfirmReplace() {
    if (!studyLauncher || !confirmState) return;
    const { target, session } = confirmState;
    const epoch = epochRef.current;
    setConfirmState({ target, session, busy: true });
    setIsStarting(true);
    const outcome = await studyLauncher.replace(target, session);
    if (epoch !== epochRef.current) return;
    if (outcome.kind !== "busy") setIsStarting(false);
    applyOutcome(target, outcome);
  }

  function handleConfirmResume() {
    if (!studyLauncher || !confirmState) return;
    applyOutcome(confirmState.target, studyLauncher.resume());
  }

  function handleConfirmCancel() {
    if (studyLauncher) studyLauncher.cancel();
    setIsStarting(false);
    setConfirmState(null);
  }

  function handleClearCorrupt() {
    if (!storageKey) return;
    if (!window.confirm("이 기기에 저장된 학습 계획을 지울까요? 다른 학습 기록은 그대로예요.")) return;
    if (removeStoredPlan(safeStorage(), storageKey)) setReadIssue(null);
  }

  // ---- 화면 상태 ----
  const today = serverToday && progress.state === "ready" ? serverToday : localToday;
  const saveState = saveError ? "saveError" : saved && sameDraft(saved, draft) ? "saved" : "draft";

  let notice: PlanNotice | null = null;
  if (account && launchMessage) {
    notice = { text: launchMessage };
  } else if (!account) {
    notice = {
      text: "로그인하면 이 기기에 계획을 저장할 수 있어요.",
      actions: onOpenAccount ? [{ label: "로그인", onClick: onOpenAccount }] : undefined,
    };
  } else if (externalPlan !== null) {
    notice = {
      text: "다른 창에서 계획이 바뀌었어요.",
      actions: [{ label: "바뀐 계획 불러오기", onClick: () => applyExternal(externalPlan) }],
    };
  } else if (readIssue === "corrupt") {
    notice = {
      text: "저장된 계획을 읽지 못했어요. 새로 저장하면 바뀌어요.",
      tone: "warning",
      actions: [{ label: "저장된 계획 지우기", onClick: handleClearCorrupt }],
    };
  } else if (readIssue === "unavailable") {
    notice = { text: "이 브라우저에서는 계획을 저장할 수 없어요.", tone: "warning" };
  }

  if (!isLoaded) {
    // 계정 경계 직후: 아무 계정의 계획·진도도 보이지 않는 빈 지면.
    return (
      <LearningPlanSection
        today={localToday}
        decks={null}
        draft={defaultDraft(localToday, null)}
        progress={{ state: "loading", deck: null }}
        saveState="draft"
        onDraftChange={() => undefined}
      />
    );
  }

  return (
    <LearningPlanSection
      today={today}
      decks={decks}
      draft={draft}
      progress={progress}
      saveState={saveState}
      notice={notice}
      storageNote={account ? "계획은 이 기기에만 저장돼요. 다른 기기와 동기화되지 않아요." : undefined}
      onDraftChange={handleDraftChange}
      onSave={account ? handleSave : undefined}
      onStart={account && studyLauncher ? () => void launch("new") : undefined}
      onReviewToday={account && studyLauncher ? () => void launch("today") : undefined}
      isStarting={isStarting}
      confirm={
        confirmState
          ? ({
              mode: confirmState.target.mode,
              remaining: confirmState.session.remaining,
              busy: confirmState.busy,
            } satisfies PlanStartConfirm)
          : null
      }
      onConfirmResume={handleConfirmResume}
      onConfirmReplace={() => void handleConfirmReplace()}
      onConfirmCancel={handleConfirmCancel}
      footer={footer}
      signedOut={!account}
      onRetryProgress={() => setRetryToken((n) => n + 1)}
      onGoToHistory={onGoToHistory}
    />
  );
}
