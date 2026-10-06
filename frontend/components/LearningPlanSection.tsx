"use client";

// 학습 계획 C 패드 (Gate B). 위쪽 천 제본 패드 한 장 위에 왼쪽은
// 덱 → 기간 → 하루 단어 수, 오른쪽은 덱 진도 → 남음/계획 분량 비교 →
// 여유·초과와 날짜 → 저장/시작. 모든 글자·숫자·막대·버튼은 DOM이다.
//
// 이 컴포넌트는 계산과 표시만 맡는다. 덱 목록·진도 조회·저장·학습 시작은
// 부모가 props로 넘기며, 넘기지 않은 동작은 비활성/미연결로 보인다.
// 진도와 예상 일정은 첫 학습 기준의 임시 지표다(기억 완성/SRS 숙련 아님).
import { useEffect, useId, useRef, useState } from "react";
import { InfoIcon } from "./icons";
import {
  DURATION_PRESETS,
  computePlan,
  deckKey,
  formatLongDate,
  formatShortDate,
  inclusiveSpan,
  matchingPreset,
  parseDailyWords,
  readyProgress,
  stepDailyWords,
  targetForPreset,
  type PlanComputation,
  type PlanDeckOption,
  type PlanDraft,
  type PlanProgress,
  type PlanSaveState,
} from "./learningPlan";

export type LearningPlanSectionProps = {
  /** 서울 기준 오늘 (YYYY-MM-DD). 부모가 seoulToday()로 정한다. */
  today: string;
  /** null = 덱 목록을 아직 확인하지 못함. [] = 확인된 빈 목록. */
  decks: PlanDeckOption[] | null;
  draft: PlanDraft;
  progress: PlanProgress;
  saveState: PlanSaveState;
  /** 저장 데이터 문제·다른 창 변경·로그인 필요 같은 짧은 안내와 명령. */
  notice?: PlanNotice | null;
  /** 정보 펼침에 넣을 저장 위치 설명(저장이 연결됐을 때만). */
  storageNote?: string;
  onDraftChange: (next: PlanDraft) => void;
  onSave?: () => void;
  onStart?: () => void;
  /** 하루 0개·첫 학습 마침일 때 학습 시작 자리의 작은 "오늘 복습". */
  onReviewToday?: () => void;
  isStarting?: boolean;
  /** 진행 중 복습이 있을 때의 확인창. null이면 닫힘. */
  confirm?: PlanStartConfirm | null;
  onConfirmResume?: () => void;
  onConfirmReplace?: () => void;
  onConfirmCancel?: () => void;
  onRetryProgress?: () => void;
  onGoToHistory?: () => void;
  /** 패드 아래, 같은 장면 안의 보조 줄(예: 이전 분류 초안 안내). */
  footer?: React.ReactNode;
  /** 로그인 전: 덱이 "없는" 것이 아니라 아직 고를 수 없는 상태로 표시한다. */
  signedOut?: boolean;
};

export type PlanStartConfirm = {
  mode: "new" | "today";
  remaining: number;
  /** 새 큐를 불러오는 중. 취소만 가능. */
  busy: boolean;
};

export type PlanNotice = {
  text: string;
  tone?: "neutral" | "warning";
  actions?: Array<{ label: string; onClick: () => void }>;
};

function ArrowIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

function statusText(plan: PlanComputation, progress: PlanProgress): { main: string; tail: string } {
  switch (plan.status) {
    case "ahead":
      return { main: `${plan.margin}일`, tail: "여유" };
    case "onTime":
      return { main: "0일", tail: "목표일 일치" };
    case "late":
      return { main: `${Math.abs(plan.margin ?? 0)}일`, tail: "초과" };
    case "paused":
      return { main: "신규 학습 쉬는 중", tail: "" };
    case "allSeen":
      return { main: "첫 학습 마침", tail: "" };
    case "emptyDeck":
      return { main: "빈 덱", tail: "" };
    case "expired":
      return { main: "기간 지남", tail: "목표일을 다시 정해 주세요" };
    case "invalid":
      return { main: "설정 확인 필요", tail: "" };
    default:
      if (progress.state === "missing") return { main: "덱을 찾을 수 없어요", tail: "" };
      return { main: progress.state === "loading" ? "진도 확인 중" : "진도 확인 필요", tail: "" };
  }
}

export function LearningPlanSection({
  today,
  decks,
  draft,
  progress,
  saveState,
  notice = null,
  storageNote,
  onDraftChange,
  onSave,
  onStart,
  onReviewToday,
  isStarting = false,
  confirm = null,
  onConfirmResume,
  onConfirmReplace,
  onConfirmCancel,
  footer,
  signedOut = false,
  onRetryProgress,
  onGoToHistory,
}: LearningPlanSectionProps) {
  const uid = useId();
  const ids = {
    deck: `${uid}-deck`,
    start: `${uid}-start`,
    target: `${uid}-target`,
    daily: `${uid}-daily`,
    dateError: `${uid}-date-error`,
    dailyError: `${uid}-daily-error`,
    result: `${uid}-result`,
    basis: `${uid}-basis`,
  };

  // 하루량 입력은 타이핑 중인 원문을 따로 들고 있다("1." 같은 중간값을
  // 숫자로 덮어쓰지 않기 위해). 외부에서 값이 바뀌면 그때만 맞춘다.
  // 렌더 중에 맞춰서(effect가 아니라) 계정 전환·다른 창 불러오기 직후에도
  // 이전 값이 한 프레임 남지 않게 한다.
  const [dailyText, setDailyText] = useState(draft.dailyWords === null ? "" : String(draft.dailyWords));
  const [dailySource, setDailySource] = useState(draft.dailyWords);
  if (draft.dailyWords !== dailySource) {
    setDailySource(draft.dailyWords);
    if (parseDailyWords(dailyText) !== draft.dailyWords) {
      setDailyText(draft.dailyWords === null ? "" : String(draft.dailyWords));
    }
  }

  const [isBasisOpen, setIsBasisOpen] = useState(false);

  const plan = computePlan({ draft, progress, today });
  const known = readyProgress(progress, draft.deck);
  const span = inclusiveSpan(draft.startDate, draft.targetDate);
  const preset = matchingPreset(draft.startDate, draft.targetDate);
  const dailyInvalid = parseDailyWords(dailyText) === null;
  const status = statusText(plan, progress);
  const isLate = plan.status === "late";
  const progressUnknown = known === null;

  const canSave = Boolean(onSave) && draft.deck !== null && plan.dateValid && plan.dailyValid;
  // 미래 시작일도 일정 상태(ahead/onTime/late)라 미리 학습할 수 있다.
  // 진도 조회 실패는 학습을 막지 않는다(덱이 확인된 경우).
  const canStart =
    Boolean(onStart) &&
    !isStarting &&
    !confirm &&
    saveState === "saved" &&
    (plan.status === "ahead" ||
      plan.status === "onTime" ||
      plan.status === "late" ||
      (plan.status === "unknown" && progress.state === "error"));
  // 신규 학습이 없는 상태에서는 학습 시작 자리에 작은 "오늘 복습".
  const showReviewToday =
    Boolean(onReviewToday) &&
    saveState === "saved" &&
    (plan.status === "paused" || plan.status === "allSeen");

  // 확인창 포커스: 열리면 "이어하기", 불러오는 중이면 "취소", 닫히면(취소·Esc·
  // 실패·빈 결과) 확인창을 연 명령으로 돌아간다. 탭이 바뀌면 이 화면은 사라진다.
  const confirmRef = useRef<HTMLButtonElement>(null);
  const confirmCancelRef = useRef<HTMLButtonElement>(null);
  const startRef = useRef<HTMLButtonElement>(null);
  const wasConfirmOpen = useRef(false);
  const isConfirmOpen = Boolean(confirm);
  const isConfirmBusy = Boolean(confirm?.busy);
  useEffect(() => {
    if (isConfirmOpen) {
      (isConfirmBusy ? confirmCancelRef : confirmRef).current?.focus();
    } else if (wasConfirmOpen.current) {
      startRef.current?.focus();
    }
    wasConfirmOpen.current = isConfirmOpen;
  }, [isConfirmOpen, isConfirmBusy]);

  function update(patch: Partial<PlanDraft>) {
    onDraftChange({ ...draft, ...patch });
  }

  function handleDeckChange(value: string) {
    const option = decks?.find((d) => deckKey(d.ref) === value);
    update({ deck: option ? option.ref : null });
  }

  function handleStartChange(value: string) {
    // 시작일을 옮기면 같은 기간을 유지한다(기간이 유효할 때만).
    const nextTarget = span !== null ? targetForPreset(value, span) : null;
    update(nextTarget ? { startDate: value, targetDate: nextTarget } : { startDate: value });
  }

  function handlePreset(days: number) {
    const target = targetForPreset(draft.startDate, days);
    if (target) update({ targetDate: target });
  }

  function handleDailyText(value: string) {
    setDailyText(value);
    update({ dailyWords: parseDailyWords(value) });
  }

  function handleStep(delta: number) {
    const next = stepDailyWords(draft.dailyWords, delta);
    if (next === null) return;
    setDailyText(String(next));
    update({ dailyWords: next });
  }

  // ---- 왼쪽: 덱 메타 줄 ----
  let deckMeta: React.ReactNode;
  if (draft.deck === null) {
    deckMeta = signedOut
      ? "로그인하면 덱을 고를 수 있어요"
      : decks && decks.length === 0
        ? "학습할 덱이 없어요"
        : "덱을 선택해 주세요";
  } else if (known) {
    // 구독 덱은 계정 공유 진도: 다른 덱에서 학습한 같은 단어도 접함이다.
    const shared = progress.state === "ready" && progress.scope === "account_shared";
    deckMeta = `전체 ${known.total}개 · 처음 학습한 단어 ${known.seen}개${shared ? " · 다른 덱 학습 포함" : ""}`;
  } else if (progress.state === "missing") {
    deckMeta = "덱을 찾을 수 없어요 · 다른 덱을 골라 주세요";
  } else if (progress.state === "loading") {
    deckMeta = "덱 현황을 불러오는 중";
  } else if (progress.state === "error" || progress.state === "ready") {
    deckMeta = (
      <>
        <span>덱 현황을 불러오지 못했어요</span>
        {onRetryProgress ? (
          <button type="button" className="learning-plan__inline-command" onClick={onRetryProgress}>
            다시 불러오기
          </button>
        ) : null}
      </>
    );
  } else {
    deckMeta = "진도 미연결 · 확인 불가";
  }

  const percent =
    plan.progressRatio === null
      ? "—"
      : // 99.6%를 100%로 올려 "다 접함"처럼 보이지 않게 내림.
        `${plan.seen === plan.total ? 100 : Math.floor(plan.progressRatio * 100)}%`;
  // 최소량 안내: 남은 새 단어 0개 / 빈 덱 / 확인 불가를 서로 다른 문구로.
  let recommendedText: React.ReactNode = "필요 학습량 확인 불가";
  if (known && known.total === 0) {
    recommendedText = "덱에 단어가 없어요";
  } else if (known && known.total === known.seen) {
    recommendedText = "남은 새 단어 없음";
  } else if (plan.minDaily !== null) {
    recommendedText = (
      <>
        기간에 맞는 최소량
        <br />
        <strong>하루 {plan.minDaily}개</strong>
      </>
    );
  }
  const count = (value: number | null) => (value === null ? "—" : String(value));

  const pageState =
    saveState === "saved"
      ? { label: "계획 저장됨", modifier: "saved" }
      : saveState === "saveError"
        ? { label: "저장하지 못함", modifier: "error" }
        : { label: "계획 작성 중", modifier: "draft" };

  let feedback = "";
  if (saveState === "saveError") feedback = "계획을 저장하지 못했어요. 기존 계획은 그대로예요.";
  else if (!onSave && !onStart && !signedOut) feedback = "저장과 학습 시작은 아직 연결되지 않았어요.";
  else if (!onStart && saveState === "saved") feedback = "학습 시작은 아직 연결되지 않았어요.";

  const deckMissingFromList =
    draft.deck !== null && decks !== null && !decks.some((d) => deckKey(d.ref) === deckKey(draft.deck!));

  return (
    <section className="learning-plan" aria-labelledby={`${uid}-title`}>
      <article className="learning-plan__pad">
        <div className="learning-plan__binding" aria-hidden="true" />
        <div className="learning-plan__sheet">
          <header className="learning-plan__head">
            <div>
              <h1 id={`${uid}-title`}>학습 계획</h1>
              <p>{formatLongDate(today)} · 서울 시간 기준</p>
            </div>
            <span className={`learning-plan__state learning-plan__state--${pageState.modifier}`}>
              {pageState.label}
            </span>
          </header>

          <div className="learning-plan__workflow">
            <form
              className="learning-plan__inputs"
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                if (canSave && onSave) onSave();
              }}
              id={`${uid}-form`}
            >
              <section className="learning-plan__step">
                <span className="learning-plan__step-number" aria-hidden="true">
                  1
                </span>
                <h2>
                  <label htmlFor={ids.deck}>학습할 덱</label>
                </h2>
                <select
                  id={ids.deck}
                  className="learning-plan__deck-select"
                  value={draft.deck ? deckKey(draft.deck) : ""}
                  disabled={!decks || decks.length === 0}
                  onChange={(event) => handleDeckChange(event.target.value)}
                >
                  {deckMissingFromList && draft.deck ? (
                    <option value={deckKey(draft.deck)}>찾을 수 없는 덱</option>
                  ) : null}
                  {draft.deck === null || !decks ? (
                    <option value="">
                      {signedOut ? "로그인 필요" : !decks ? "덱 목록 확인 중" : decks.length === 0 ? "덱 없음" : "덱 선택"}
                    </option>
                  ) : null}
                  {(decks ?? []).map((option) => (
                    <option key={deckKey(option.ref)} value={deckKey(option.ref)}>
                      {option.name}
                    </option>
                  ))}
                </select>
                <p className="learning-plan__deck-meta">{deckMeta}</p>
              </section>

              <section className="learning-plan__step">
                <span className="learning-plan__step-number" aria-hidden="true">
                  2
                </span>
                <h2 id={`${uid}-period`}>학습 기간</h2>
                <div className="learning-plan__presets" role="group" aria-labelledby={`${uid}-period`}>
                  {DURATION_PRESETS.map((days) => (
                    <button
                      key={days}
                      type="button"
                      className="learning-plan__preset"
                      aria-pressed={preset === days}
                      onClick={() => handlePreset(days)}
                    >
                      {days}일
                    </button>
                  ))}
                  <button
                    type="button"
                    className="learning-plan__preset"
                    aria-pressed={preset === null}
                    onClick={() => document.getElementById(ids.target)?.focus()}
                  >
                    직접 설정
                  </button>
                </div>
                <div className="learning-plan__dates">
                  <label className="learning-plan__date" htmlFor={ids.start}>
                    <span>시작일</span>
                    <input
                      id={ids.start}
                      type="date"
                      value={draft.startDate}
                      aria-invalid={!plan.dateValid}
                      aria-describedby={plan.dateValid ? undefined : ids.dateError}
                      onChange={(event) => handleStartChange(event.target.value)}
                    />
                  </label>
                  <span className="learning-plan__date-arrow" aria-hidden="true">
                    <ArrowIcon />
                  </span>
                  <label className="learning-plan__date" htmlFor={ids.target}>
                    <span>목표일</span>
                    <input
                      id={ids.target}
                      type="date"
                      value={draft.targetDate}
                      aria-invalid={!plan.dateValid}
                      aria-describedby={plan.dateValid ? undefined : ids.dateError}
                      onChange={(event) => update({ targetDate: event.target.value })}
                    />
                  </label>
                </div>
                {plan.dateValid ? (
                  <p className="learning-plan__caption">총 {span}일 · 시작일 포함</p>
                ) : (
                  <p className="learning-plan__field-error" id={ids.dateError} role="alert">
                    목표일을 시작일 이후로 정해 주세요
                  </p>
                )}
              </section>

              <section className="learning-plan__step">
                <span className="learning-plan__step-number" aria-hidden="true">
                  3
                </span>
                <h2>
                  <label htmlFor={ids.daily}>하루 학습할 단어</label>
                </h2>
                <div className="learning-plan__daily-row">
                  <span className="learning-plan__stepper">
                    <button
                      type="button"
                      aria-label="하루 1개 줄이기"
                      disabled={draft.dailyWords === null || draft.dailyWords <= 0}
                      onClick={() => handleStep(-1)}
                    >
                      <span aria-hidden="true">−</span>
                    </button>
                    <input
                      id={ids.daily}
                      type="text"
                      inputMode="numeric"
                      autoComplete="off"
                      value={dailyText}
                      aria-invalid={dailyInvalid}
                      aria-describedby={dailyInvalid ? ids.dailyError : undefined}
                      onChange={(event) => handleDailyText(event.target.value)}
                    />
                    <span className="learning-plan__unit" aria-hidden="true">
                      개
                    </span>
                    <button
                      type="button"
                      aria-label="하루 1개 늘리기"
                      disabled={draft.dailyWords === null || draft.dailyWords >= 500}
                      onClick={() => handleStep(1)}
                    >
                      <span aria-hidden="true">+</span>
                    </button>
                  </span>
                  <p className="learning-plan__recommended">
                    {recommendedText}
                  </p>
                </div>
                {dailyInvalid ? (
                  <p className="learning-plan__field-error" id={ids.dailyError} role="alert">
                    0~500 사이의 정수를 입력해 주세요
                  </p>
                ) : (
                  <p className="learning-plan__caption">새로 학습할 단어 기준 · 필요한 재복습은 별도</p>
                )}
              </section>
            </form>

            <section
              className="learning-plan__result"
              aria-labelledby={ids.result}
              data-late={isLate}
              data-unknown={progressUnknown}
            >
              <div className="learning-plan__result-top">
                <h2 id={ids.result}>덱 진도</h2>
                <span className="learning-plan__basis">첫 학습 기준</span>
              </div>
              <div className="learning-plan__fraction-row">
                <p className="learning-plan__fraction">
                  <strong>{count(plan.seen)}</strong>
                  <span>/ {count(plan.total)}개</span>
                </p>
                <span className="learning-plan__percent">{percent}</span>
              </div>
              <div
                className="learning-plan__meter"
                role="progressbar"
                aria-label="첫 학습 진도"
                aria-valuemin={0}
                aria-valuemax={plan.total ?? undefined}
                aria-valuenow={plan.total ? (plan.seen ?? undefined) : undefined}
                aria-valuetext={plan.progressRatio === null ? "확인 불가" : `${plan.seen} / ${plan.total}개`}
              >
                <i style={{ width: `${(plan.progressRatio ?? 0) * 100}%` }} />
              </div>
              <div className="learning-plan__meter-caption">
                <span>접함</span>
                <span>
                  남음 <b>{count(plan.remaining)}개</b>
                </span>
              </div>

              <section className="learning-plan__capacity" aria-labelledby={`${uid}-capacity`}>
                <h3 id={`${uid}-capacity`}>목표일까지</h3>
                <div className="learning-plan__capacity-row">
                  <span>남음</span>
                  <div className="learning-plan__track" aria-hidden="true">
                    <i style={{ width: `${plan.remainingBar * 100}%` }} />
                  </div>
                  <b>{plan.capacity === null ? "—" : count(plan.remaining)}개</b>
                </div>
                <div className="learning-plan__capacity-row learning-plan__capacity-row--plan">
                  <span>계획</span>
                  <div className="learning-plan__track" aria-hidden="true">
                    <i style={{ width: `${plan.capacityBar * 100}%` }} />
                  </div>
                  <b>{count(plan.capacity)}개</b>
                </div>
                <p className="learning-plan__status" aria-live="polite">
                  <strong>{status.main}</strong>
                  {status.tail ? <span>{status.tail}</span> : null}
                </p>
                {isLate && plan.minDaily !== null ? (
                  <button
                    type="button"
                    className="learning-plan__adjust"
                    onClick={() => {
                      setDailyText(String(plan.minDaily));
                      update({ dailyWords: plan.minDaily });
                    }}
                  >
                    하루 {plan.minDaily}개로 조정
                    <ArrowIcon />
                  </button>
                ) : null}
                <p className="learning-plan__dates-mini">
                  <span>
                    예상<b>{plan.predictedDate ? formatShortDate(plan.predictedDate) : "—"}</b>
                  </span>
                  <span>
                    목표<b>{plan.dateValid ? formatShortDate(draft.targetDate) : "—"}</b>
                  </span>
                </p>
              </section>

              <div className="learning-plan__actions">
                <div className="learning-plan__action-row">
                  <button
                    type="submit"
                    form={`${uid}-form`}
                    className="learning-plan__save"
                    disabled={!canSave}
                  >
                    <CheckIcon />
                    계획 저장
                  </button>
                  {showReviewToday ? (
                    <button
                      ref={startRef}
                      type="button"
                      className="learning-plan__start"
                      disabled={isStarting || Boolean(confirm)}
                      onClick={() => onReviewToday?.()}
                    >
                      {isStarting ? "여는 중" : "오늘 복습"}
                      <ArrowIcon />
                    </button>
                  ) : (
                    <button
                      ref={startRef}
                      type="button"
                      className="learning-plan__start"
                      disabled={!canStart}
                      onClick={() => {
                        if (canStart && onStart) onStart();
                      }}
                    >
                      {isStarting && !confirm ? "시작하는 중" : "학습 시작"}
                      <ArrowIcon />
                    </button>
                  )}
                </div>
                {confirm ? (
                  <div
                    className="learning-plan__confirm"
                    role="alertdialog"
                    aria-labelledby={`${uid}-confirm`}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") onConfirmCancel?.();
                    }}
                  >
                    <p id={`${uid}-confirm`}>
                      {confirm.busy
                        ? confirm.mode === "today"
                          ? "오늘 복습을 불러오는 중이에요."
                          : "새 학습을 불러오는 중이에요."
                        : `진행 중인 복습이 있어요 · 남은 ${confirm.remaining}장`}
                    </p>
                    <div className="learning-plan__confirm-actions">
                      {confirm.busy ? null : (
                        <>
                          <button
                            ref={confirmRef}
                            type="button"
                            className="learning-plan__confirm-primary"
                            onClick={() => onConfirmResume?.()}
                          >
                            이어하기
                          </button>
                          <button type="button" className="learning-plan__inline-command" onClick={() => onConfirmReplace?.()}>
                            {confirm.mode === "today" ? "오늘 복습으로 바꾸기" : "새 학습으로 바꾸기"}
                          </button>
                        </>
                      )}
                      <button
                        ref={confirmCancelRef}
                        type="button"
                        className="learning-plan__inline-command"
                        onClick={() => onConfirmCancel?.()}
                      >
                        취소
                      </button>
                    </div>
                  </div>
                ) : null}
                {feedback ? (
                  <p className="learning-plan__feedback" role="status">
                    {feedback}
                  </p>
                ) : null}
                {notice ? (
                  <div
                    className={`learning-plan__notice${notice.tone === "warning" ? " learning-plan__notice--warning" : ""}`}
                    role="status"
                  >
                    <span>{notice.text}</span>
                    {notice.actions?.map((action) => (
                      <button
                        key={action.label}
                        type="button"
                        className="learning-plan__inline-command"
                        onClick={action.onClick}
                      >
                        {action.label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="learning-plan__tools">
                {onGoToHistory ? (
                  <button type="button" className="learning-plan__history" onClick={onGoToHistory}>
                    학습 기록
                  </button>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  className="learning-plan__info"
                  aria-label="계산과 진도 기준"
                  title="계산과 진도 기준"
                  aria-expanded={isBasisOpen}
                  aria-controls={ids.basis}
                  onClick={() => setIsBasisOpen((open) => !open)}
                >
                  <InfoIcon />
                </button>
              </div>
              <div className="learning-plan__basis-details" id={ids.basis} hidden={!isBasisOpen}>
                <p>
                  진도와 예상일은 단어를 처음 학습했는지만 보는 임시 기준이에요. 충분히 기억했는지는
                  아직 판단하지 않아요.
                </p>
                <p>계획 분량은 남은 기간 × 하루 단어 수예요. 남은 단어보다 많아도 더 배정하지 않아요.</p>
                <p>하루 단어 수는 새 단어 권장량이에요. 다시 볼 복습은 따로 진행돼요.</p>
                <p>구독 덱은 다른 덱에서 학습한 같은 단어도 접한 단어로 세요. 복사한 개인 덱은 이력 없이 시작해요.</p>
                {storageNote ? <p>{storageNote}</p> : null}
              </div>
            </section>
          </div>
        </div>
        <div className="learning-plan__stack" aria-hidden="true">
          <i />
          <i />
        </div>
      </article>
      {footer}
    </section>
  );
}
