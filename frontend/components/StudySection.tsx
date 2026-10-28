"use client";

import { useEffect, useRef, useState } from "react";
import { classifyMessageTone } from "./coverageUtils";
import type {
  Deck,
  ReviewResult,
  SessionReviewCounts,
  StudyCardItem,
  StudyMode,
} from "./types";
import type { StudyStats } from "./types";
import { StatsPanel } from "./StatsPanel";
import { formatNextReview, formatReviewDelay, getDisplayMeaning } from "./shared";
import { HighlightedExample } from "./HighlightedExample";
import {
  BookmarkIcon,
  CheckCircleIcon,
  PencilIcon,
  SparkleIcon,
} from "./icons";
import { MeaningQuickEdit } from "./MeaningQuickEdit";
import { formatSeoulTime } from "./fsrsStudy";
import type { FsrsPrimary } from "./useFsrsStudy";

// FSRS 계정의 복습 회차 (Gate C-2c, CONTRACT 2-4·4-2·4-4). 이 값이 없으면
// 기존(legacy) 화면을 그대로 그린다. 상태 판단은 studySession.ts가 하고, 여기서는
// 같은 책 지면 안에서 문구와 조작만 바꾼다.
export type FsrsStudySectionState = {
  /** checking: 모드 판별 중(시작 막음), mode_error: 판별 실패(legacy로 바꾸지 않음). */
  phase: "checking" | "mode_error" | "ready" | "session";
  primary: FsrsPrimary | null;
  isPractice: boolean;
  /** 서버 연습 목록이 비었음. 연습은 한 번 이상 복습해 예약이 있는 단어만 나온다(현재 제한). */
  practiceEmpty?: boolean;
  isRecent: boolean;
  attemptStatus: "sending" | "unknown" | null;
  pendingRating: ReviewResult | null;
  noticeText: string;
  errorText: string;
  canReload: boolean;
  goalLine: string | null;
  goalReachedText: string;
  notMigratedNote: boolean;
  nextDueAt: string | null;
  reviewed: number;
  ratings: Record<ReviewResult, number>;
  firstReviews: number;
  deferredCount: number;
  pendingLater: number;
  onRetryProbe: () => void;
  onRetryAttempt: () => void;
  onReload: () => void;
  onEnd: () => void;
  onRestart: () => void;
  onPracticeNext: (again: boolean) => void;
  onPracticeRecent?: () => void;
  /** Gate D-1: 지금 복습·오늘 새 단어 한 줄(이 덱 범위). 확인 중·확인 불가 문구 포함. */
  metricsLine?: string;
  /** 학습 현황 패널용(같은 범위·같은 정의). */
  statsPanel?: { dueNow: string; todayReviews: string; scopeLabel: string };
};

// Review open book (references/mockups/review-redesign/b-book-asset/handoff).
// Desktop reuses the Reading tab's C folio images byte-unchanged and lays the
// two live pages over the book's measured safe rectangles (globals.css,
// "Review open book"). Phones and tablets use the single bound washi sheet,
// not a shrunk spread. The images carry material only -- every word, count
// and hit area below is DOM.
const BOOK_WIDE_ASSET = "/brand/decor/v4/v4-reading-c-folio-desktop-wide.webp";
const BOOK_TALL_ASSET = "/brand/decor/v4/v4-reading-c-folio-desktop-tall.webp";
const BOOK_SHEET_ASSET = "/brand/decor/v4/v4-reading-washi-mobile-c-quiet.webp";

type StudySectionProps = {
  items: StudyCardItem[];
  currentItem?: StudyCardItem;
  currentIndex: number;
  isComplete: boolean;
  isAnswerVisible: boolean;
  isLoading: boolean;
  isReviewing: boolean;
  hasStarted: boolean;
  message: string;
  stats: StudyStats | null;
  isStatsLoading: boolean;
  statsMessage: string;
  sessionCounts: SessionReviewCounts;
  nextUpcomingReviewAt: string | null;
  againNextReviewAt: string | null;
  decks: Deck[];
  // Phase 3 (see docs/architecture/shared-lexeme-progress-storage.md -- "SRS
  // card integration"): subscribed shared decks selectable as a study deck,
  // alongside the personal decks above. `id` is already prefixed
  // ("shared:123") so it can share the same <select> value space as a
  // personal deck's plain numeric id string.
  sharedDeckOptions: Array<{ id: string; title: string }>;
  selectedDeckId: string;
  selectedDeckName: string;
  studyMode: StudyMode;
  meaningEditItemId: number | null;
  meaningEditDraft: string;
  isSavingMeaningEdit: boolean;
  meaningEditMessage: string;
  onStartMeaningEdit: (itemId: number, currentMeaning: string) => void;
  onMeaningEditDraftChange: (value: string) => void;
  onSaveMeaningEdit: () => void;
  onCancelMeaningEdit: () => void;
  onReportMeaning: (item: StudyCardItem) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onStudyModeChange: (mode: StudyMode) => void;
  onQuickStart: (mode: StudyMode) => void;
  onStart: () => void;
  onRestart: () => void;
  onGoToVocab: () => void;
  onGoToReading: () => void;
  onShowAnswer: () => void;
  onReview: (result: ReviewResult) => void;
  // Signed-out visitors study as the shared guest (dev) account, so nothing
  // ever fails with 401 for them; the ready page says so and offers sign-in.
  isGuest?: boolean;
  onOpenAccount?: () => void;
  fsrs?: FsrsStudySectionState;
};

const studyModeLabels: Record<StudyMode, string> = {
  today: "오늘 복습",
  uncertain: "헷갈리는 단어",
  unknown: "모르는 단어",
  all: "전체 학습",
  new: "새 단어 학습",
  recent: "방금 담은 단어 복습",
};

type SelectableStudyMode = Extract<
  StudyMode,
  "today" | "uncertain" | "unknown" | "all"
>;

const selectableStudyModes: SelectableStudyMode[] = [
  "today",
  "uncertain",
  "unknown",
  "all",
];

const emptyMessages: Record<StudyMode, string> = {
  today: "오늘은 복습할 단어가 없어요.",
  uncertain: "헷갈리는 단어가 없어요.",
  unknown: "모르는 단어가 없어요.",
  all: "학습할 모르는 단어와 헷갈리는 단어가 없어요.",
  new: "새로 학습할 단어가 없어요.",
  recent: "방금 담은 단어를 찾을 수 없어요.",
};

const emptySecondaryMessages: Record<StudyMode, string> = {
  today: "새 원문을 읽고 모르는 단어를 노트에 담아보세요.",
  uncertain: "어휘 노트에서 단어를 추가하거나 원문을 읽고 새 단어를 담아보세요.",
  unknown: "어휘 노트에서 단어를 추가하거나 원문을 읽고 새 단어를 담아보세요.",
  all: "어휘 노트에서 단어를 추가하거나 원문을 읽고 새 단어를 담아보세요.",
  new: "원문을 읽으며 단어를 담으면 이곳에서 바로 복습할 수 있어요.",
  recent: "원문 읽기에서 단어를 다시 담아보세요.",
};

// Each rating gets its own icon meaning, not just its own color -- 다시
// (책갈피를 다시 꽂아둔다), 어려움 (연필로 메모해 둔다), 보통 (확인 체크),
// 쉬움 (반짝 스탬프) -- so the 4-way choice reads as four different actions
// at a glance, not four same-shape buttons in different colors.
const ratingButtons: Array<{
  result: ReviewResult;
  label: string;
  hint: string;
  icon: (props: { className?: string }) => JSX.Element;
}> = [
  { result: "again", label: "다시", hint: "곧 다시", icon: BookmarkIcon },
  { result: "hard", label: "어려움", hint: "짧게 복습", icon: PencilIcon },
  { result: "good", label: "보통", hint: "다음 예약", icon: CheckCircleIcon },
  { result: "easy", label: "쉬움", hint: "간격 늘리기", icon: SparkleIcon },
];

// meaning_ko is one free-text string, and in real data commas join
// synonyms inside a single sense -- there is no trustworthy sense delimiter.
// It is shown as one numbered sense; the stored value is never rewritten.
function getMeaningSenses(meaningKo: string | null | undefined): string[] {
  return [getDisplayMeaning(meaningKo)];
}

type BookState = "ready" | "empty" | "question" | "answer" | "complete" | "waiting";

export function StudySection({
  items,
  currentItem,
  currentIndex,
  isComplete,
  isAnswerVisible,
  isLoading,
  isReviewing,
  hasStarted,
  message,
  stats,
  isStatsLoading,
  statsMessage,
  sessionCounts,
  nextUpcomingReviewAt,
  againNextReviewAt,
  decks,
  sharedDeckOptions,
  selectedDeckId,
  selectedDeckName,
  studyMode,
  meaningEditItemId,
  meaningEditDraft,
  isSavingMeaningEdit,
  meaningEditMessage,
  onStartMeaningEdit,
  onMeaningEditDraftChange,
  onSaveMeaningEdit,
  onCancelMeaningEdit,
  onReportMeaning,
  onSelectedDeckChange,
  onStudyModeChange,
  onQuickStart,
  onStart,
  onRestart,
  onGoToVocab,
  onGoToReading,
  onShowAnswer,
  onReview,
  isGuest = false,
  onOpenAccount,
  fsrs,
}: StudySectionProps) {
  // 학습 현황 (StatsPanel) used to be a collapsed disclosure on the board;
  // it now opens in place of the right page's content outside a session.
  const [isStatsOpen, setIsStatsOpen] = useState(false);
  // Which of the four ratings is being saved, so that one stays visibly
  // pressed while the other three are disabled.
  const [pendingResult, setPendingResult] = useState<ReviewResult | null>(null);
  const answerRegionRef = useRef<HTMLDivElement>(null);
  const showAnswerRef = useRef<HTMLButtonElement>(null);

  const totalStudied =
    sessionCounts.again + sessionCounts.hard + sessionCounts.good + sessionCounts.easy;
  // One combined line instead of a separate paragraph per rating -- the
  // stat row above already shows each count, so this only needs to say
  // *what happens next* for the ratings that actually occurred this session.
  const completionHintParts: string[] = [];
  if (sessionCounts.again > 0) {
    completionHintParts.push(
      againNextReviewAt
        ? `다시 ${sessionCounts.again}개는 ${formatReviewDelay(againNextReviewAt)} 재등장`
        : `다시 ${sessionCounts.again}개는 곧 재등장`,
    );
  }
  if (sessionCounts.hard > 0) {
    completionHintParts.push(`어려움 ${sessionCounts.hard}개는 곧 재등장`);
  }
  if (sessionCounts.good > 0) {
    completionHintParts.push(`보통 ${sessionCounts.good}개는 다음 복습 예약됨`);
  }
  if (sessionCounts.easy > 0) {
    completionHintParts.push(`쉬움 ${sessionCounts.easy}개는 간격 늘어남`);
  }
  const completionHint = completionHintParts.join(" · ");
  const modeLabel = studyModeLabels[studyMode];
  const dueCount = stats?.due_today_count ?? 0;
  const uncertainCount = stats?.uncertain_count ?? 0;
  const unknownCount = stats?.unknown_count ?? 0;
  const allStudyCount = uncertainCount + unknownCount;
  const studyModeCounts: Record<SelectableStudyMode, number> = {
    today: dueCount,
    uncertain: uncertainCount,
    unknown: unknownCount,
    all: allStudyCount,
  };
  const reviewedToday = stats?.reviewed_today_count ?? 0;
  const todayTotal = reviewedToday + dueCount;
  const visibleProgress =
    items.length > 0 ? `${Math.min(currentIndex + 1, items.length)} / ${items.length}` : "0 / 0";
  // NEW_LEXEME_STUDY_LIMIT (30, page.tsx) only caps shared-deck lexeme
  // "new" sessions -- "all" mode mixes in personal vocab_items' new words
  // too, which have no such cap. Only show it for the one case where
  // "30개" is always true: a single selected shared deck's new-word session.
  const isSharedDeckSelected = selectedDeckId.startsWith("shared:");
  const showNewLexemeLimitHint = studyMode === "new" && isSharedDeckSelected;
  // The rating confirmation describes the card that was just rated, but the
  // next card mounts in the same commit -- so it shows on the next card's
  // question page and clears the moment that card's answer is revealed
  // instead of lingering beside a word it doesn't describe. A failure is
  // not a confirmation: it stays until a retry replaces it, since that card
  // never advanced.
  const messageTone = classifyMessageTone(message);
  const isCardMessageVisible =
    Boolean(message) && (!isAnswerVisible || messageTone === "error");

  const isFsrsSession = fsrs?.phase === "session";
  const bookState: BookState = fsrs
    ? isFsrsSession
      ? fsrs.primary === "ended"
        ? "complete"
        : currentItem
          ? isAnswerVisible
            ? "answer"
            : "question"
          : "waiting"
      : "ready"
    : isComplete
      ? "complete"
      : currentItem
        ? isAnswerVisible
          ? "answer"
          : "question"
        : hasStarted
          ? "empty"
          : "ready";
  const isSessionPage = bookState === "question" || bookState === "answer";
  const showStats = isStatsOpen && !isSessionPage;
  const pressedResult = fsrs ? fsrs.pendingRating : isReviewing ? pendingResult : null;
  const ratingsLocked = fsrs ? fsrs.attemptStatus !== null : isReviewing;
  const fsrsStartBlocked = Boolean(fsrs && fsrs.phase !== "ready" && fsrs.phase !== "session");

  // Revealing the answer or rating a card unmounts the button that had
  // focus. Hand focus to the new page's natural next stop (the answer text,
  // then the 정답 보기 button) instead of dropping it to <body>, without
  // scrolling the sheet.
  useEffect(() => {
    const active = typeof document !== "undefined" ? document.activeElement : null;
    if (active && active !== document.body) {
      return;
    }
    if (bookState === "answer") {
      answerRegionRef.current?.focus({ preventScroll: true });
    } else if (bookState === "question") {
      showAnswerRef.current?.focus({ preventScroll: true });
    }
  }, [bookState, currentItem?.id]);
  // Errors stay wherever they are; a plain status line (a rating
  // confirmation, or the "no cards" notice the empty page already says in
  // its own words) is not repeated outside a card.
  const isErrorMessage = Boolean(message) && messageTone === "error";
  // Stats failing to load is the only signal that the session has lapsed
  // (a 401 becomes the "로그인 후 사용할 수 있습니다" message), so it is
  // shown on the ready page instead of leaving every count at "-".
  const statsProblem = !stats && !isStatsLoading ? statsMessage : "";

  const readyCount: number | null = !stats
    ? null
    : studyMode === "new"
      ? stats.new_count
      : studyMode === "recent"
        ? null
        : studyModeCounts[studyMode];

  const itemSourceLabel = currentItem
    ? currentItem.item_type === "lexeme"
      ? currentItem.source_label
      : "내 단어장"
    : "";
  const isEditingMeaning = Boolean(currentItem) && meaningEditItemId === currentItem?.id;

  const fsrsCount = fsrs
    ? fsrs.isPractice
      ? "연습"
      : `이번 회차 ${fsrs.reviewed}장`
    : "";
  const headCount = isFsrsSession
    ? fsrsCount
    : fsrs
      ? "복습 회차"
      : isSessionPage
    ? visibleProgress
    : bookState === "complete"
      ? `${totalStudied} / ${items.length}`
      : stats
        ? `오늘 ${reviewedToday} / ${todayTotal}`
        : isStatsLoading
          ? "불러오는 중"
          : "오늘 - / -";

  const rightTitle =
    bookState === "question"
      ? "정답 확인"
      : bookState === "answer"
        ? "정답과 평가"
        : bookState === "complete"
          ? fsrs
            ? "이번 회차 기록"
            : "오늘의 기록"
          : "복습 노트";

  const navLinks = (
    <span className="study-book-nav">
      <button type="button" className="study-book-link" onClick={onGoToReading}>
        원문 읽기
      </button>
      <span aria-hidden="true">·</span>
      <button type="button" className="study-book-link" onClick={onGoToVocab}>
        어휘 노트
      </button>
    </span>
  );

  const statsToggle = (
    <button
      type="button"
      className="study-book-link"
      aria-expanded={showStats}
      onClick={() => setIsStatsOpen((open) => !open)}
    >
      {showStats ? "학습 현황 닫기" : "학습 현황"}
    </button>
  );

  const modeList = (
    <div className="study-book-modes">
      <span className="study-book-label" id="study-book-mode-label">
        학습 방법
      </span>
      <div className="study-book-mode-list" role="group" aria-labelledby="study-book-mode-label">
        {selectableStudyModes.map((mode) => (
          <button
            key={mode}
            type="button"
            className="study-book-mode-row"
            aria-pressed={studyMode === mode}
            onClick={() => onStudyModeChange(mode)}
          >
            <span>{studyModeLabels[mode]}</span>
            {fsrs ? null : <b>{stats ? studyModeCounts[mode] : "-"}</b>}
          </button>
        ))}
      </div>
    </div>
  );

  const pageMessage =
    message && !isSessionPage && (isErrorMessage || bookState === "ready") ? (
      <p className={`message message--${messageTone} study-book-message`}>{message}</p>
    ) : null;

  function renderRightBody() {
    if (showStats) {
      return (
        <div className="study-book-scroll study-book-stats">
          <StatsPanel
            title="학습 현황"
            stats={stats}
            isLoading={isStatsLoading}
            message={statsMessage}
            fsrs={fsrs?.statsPanel}
          />
        </div>
      );
    }

    if (bookState === "ready") {
      const fsrsLead = !fsrs
        ? null
        : fsrs.phase === "checking"
          ? "복습 방식을 확인하는 중이에요"
          : fsrs.phase === "mode_error"
            ? "복습 방식을 확인하지 못했어요. 다시 확인해 주세요."
            : fsrs.isPractice
              ? "카드를 넘기며 연습해 볼까요?"
              : studyMode === "recent"
                ? "방금 담은 단어로 복습 회차를 시작해 볼까요?"
                : "복습 회차를 시작해 볼까요?";
      const lead = fsrsLead !== null
        ? fsrsLead
        : readyCount === null
          ? isStatsLoading
            ? "복습 카드를 세는 중이에요"
            : "학습할 카드를 불러와 볼까요?"
          : readyCount > 0
            ? `카드 ${readyCount}장을 넘겨 볼까요?`
            : emptyMessages[studyMode];
      return (
        <div className="study-book-center">
          <span className="study-book-label">{modeLabel}</span>
          <p className="study-book-lead">{lead}</p>
          {fsrs?.phase === "ready" && fsrs.isPractice ? (
            <p className="study-book-explainer">
              연습 · 예약에 반영되지 않아요. 한 번 이상 복습한 단어만 나와요.
            </p>
          ) : null}
          {fsrs?.phase === "ready" && fsrs.metricsLine ? (
            <p className="study-book-explainer study-book-fineprint" role="status">
              {fsrs.metricsLine}
            </p>
          ) : null}
          {statsProblem ? (
            <p
              className={`message message--${classifyMessageTone(statsProblem)} study-book-message`}
              role="status"
            >
              {statsProblem}
            </p>
          ) : null}
          {pageMessage}
          {fsrs?.phase === "mode_error" ? (
            <button type="button" className="study-book-primary" onClick={fsrs.onRetryProbe}>
              다시 확인
            </button>
          ) : (
            <button
              type="button"
              className="study-book-primary"
              onClick={onStart}
              disabled={isLoading || fsrsStartBlocked}
            >
              {fsrs?.phase === "checking"
                ? "확인 중..."
                : isLoading
                  ? "불러오는 중..."
                  : fsrs?.isPractice
                    ? "연습 시작"
                    : studyMode === "today"
                      ? "오늘 복습 시작"
                      : "학습 시작"}
            </button>
          )}
          {studyMode !== "new" ? (
            <button
              type="button"
              className="study-book-secondary"
              onClick={() => onQuickStart("new")}
              disabled={isLoading || fsrsStartBlocked}
            >
              새 단어 학습
            </button>
          ) : null}
          <p className="study-book-explainer">
            <span className="study-book-desk-only">왼쪽에서 학습 방법을 바꿀 수 있어요.</span>
            <span className="study-book-phone-only">위에서 학습 방법을 바꿀 수 있어요.</span>
          </p>
          {isGuest ? (
            <p className="study-book-explainer study-book-fineprint study-book-guest">
              로그인하지 않은 상태예요. 로그인하면 복습 기록이 계정에 이어져요.
              {onOpenAccount ? (
                <>
                  {" "}
                  <button type="button" className="study-book-link" onClick={onOpenAccount}>
                    로그인
                  </button>
                </>
              ) : null}
            </p>
          ) : null}
          {isSharedDeckSelected ? (
            <p className="study-book-explainer study-book-fineprint">
              공유덱 전용 통계는 아직 지원하지 않아, 학습 방법 옆 숫자는 전체 단어장
              기준이에요.
            </p>
          ) : null}
        </div>
      );
    }

    if (bookState === "waiting" && fsrs) {
      return renderFsrsWaiting(fsrs);
    }

    if (bookState === "complete" && fsrs) {
      return (
        <div className="study-book-center">
          <span className="study-book-label">이번 회차 기록</span>
          <p className="study-book-lead">
            {fsrs.isPractice
              ? "연습 회차를 마쳤어요"
              : `이번 회차에서 ${fsrs.reviewed}장을 평가했어요`}
          </p>
          {fsrs.isPractice ? (
            <p className="study-book-explainer">연습은 예약에 반영되지 않아요.</p>
          ) : (
            <>
              <div className="study-book-done-stats">
                {ratingButtons.map(({ result, label }) => (
                  <div key={result} data-tone={result}>
                    {label}
                    <b>{fsrs.ratings[result]}</b>
                  </div>
                ))}
              </div>
              <p className="study-book-explainer">
                처음 평가한 카드 {fsrs.firstReviews}장 · 이번 회차에서 미룬 카드 {fsrs.deferredCount}장
              </p>
              {fsrs.nextDueAt ? (
                <p className="study-book-explainer">{formatNextReview(fsrs.nextDueAt)}</p>
              ) : null}
            </>
          )}
          <button type="button" className="study-book-primary" onClick={fsrs.onRestart}>
            새 회차 시작
          </button>
        </div>
      );
    }

    if (bookState === "empty") {
      return (
        <div className="study-book-center">
          <p className="study-book-lead">
            {message || emptyMessages[studyMode]}
          </p>
          <p className="study-book-explainer">{emptySecondaryMessages[studyMode]}</p>
          <button type="button" className="study-book-primary" onClick={onGoToReading}>
            원문 읽기 시작
          </button>
          <button type="button" className="study-book-secondary" onClick={onGoToVocab}>
            어휘 노트 보기
          </button>
          {studyMode !== "new" ? (
            <button
              type="button"
              className="study-book-secondary"
              onClick={() => onQuickStart("new")}
              disabled={isLoading}
            >
              새 단어 학습
            </button>
          ) : null}
        </div>
      );
    }

    if (bookState === "complete") {
      return (
        <div className="study-book-center">
          <span className="study-book-label">오늘의 기록</span>
          <p className="study-book-lead">
            {studyMode === "recent"
              ? "방금 담은 단어 복습을 마쳤어요"
              : `${totalStudied}장을 모두 넘겼어요`}
          </p>
          <div className="study-book-done-stats">
            {ratingButtons.map(({ result, label }) => (
              <div key={result} data-tone={result}>
                {label}
                <b>{sessionCounts[result]}</b>
              </div>
            ))}
          </div>
          {completionHint ? <p className="study-book-explainer">{completionHint}</p> : null}
          <p className="study-book-explainer">
            {nextUpcomingReviewAt
              ? `이번 세션에서 본 단어 기준 ${formatNextReview(nextUpcomingReviewAt)}`
              : "다음 복습 단어는 아직 예정되어 있지 않아요."}
          </p>
          {pageMessage}
          <button type="button" className="study-book-primary" onClick={onRestart}>
            한 번 더 복습
          </button>
          {studyMode === "recent" ? (
            <button
              type="button"
              className="study-book-secondary"
              onClick={() => onQuickStart("today")}
            >
              오늘 복습 보기
            </button>
          ) : null}
        </div>
      );
    }

    if (bookState === "question" && currentItem) {
      return (
        <div className="study-book-center">
          <span className="study-book-label">뜻을 떠올린 뒤</span>
          <button
            type="button"
            className="study-book-primary"
            onClick={onShowAnswer}
            ref={showAnswerRef}
          >
            정답 보기
          </button>
          {fsrs ? (
            <>
              {fsrs.isPractice ? (
                <p className="study-book-explainer">연습 · 예약에 반영되지 않아요</p>
              ) : null}
              {fsrs.noticeText ? (
                <p className="message message--info study-book-message" role="status">
                  {fsrs.noticeText}
                </p>
              ) : null}
              {fsrs.goalLine && !fsrs.isPractice ? (
                <p className="study-book-explainer study-book-fineprint">{fsrs.goalLine}</p>
              ) : null}
            </>
          ) : null}
          {!fsrs && studyMode === "recent" ? (
            <p className="study-book-explainer">
              원문 읽기에서 담은 단어를 바로 복습해요. ({items.length}개 단어)
            </p>
          ) : null}
          {!fsrs && showNewLexemeLimitHint ? (
            <p className="study-book-explainer">새 단어는 한 번에 30개씩 가볍게 시작해요.</p>
          ) : null}
          {isCardMessageVisible ? (
            <p className={`message message--${messageTone} study-book-message`} role="status">
              {message}
            </p>
          ) : null}
        </div>
      );
    }

    if (bookState === "answer" && currentItem) {
      return (
        <div
          className="study-book-scroll"
          tabIndex={0}
          aria-label="뜻과 예문"
          ref={answerRegionRef}
        >
          <div className="study-book-answer" key={currentItem.id}>
            {isCardMessageVisible ? (
              <p className={`message message--${messageTone} study-book-message`} role="status">
                {message}
              </p>
            ) : null}
            <section className="study-book-meaning">
              <span className="study-book-label">뜻</span>
              <ol className="study-book-senses">
                {getMeaningSenses(currentItem.meaning_ko).map((sense, index) => (
                  <li key={index}>
                    <span className="study-book-sense-no" aria-hidden="true">
                      {index + 1}
                    </span>
                    <span className="study-book-sense-text">{sense}</span>
                  </li>
                ))}
              </ol>
              {currentItem.item_type === "vocab" && isEditingMeaning ? (
                <MeaningQuickEdit
                  isEditing
                  draftValue={meaningEditDraft}
                  isSaving={isSavingMeaningEdit}
                  message={meaningEditMessage}
                  onStartEdit={() =>
                    onStartMeaningEdit(currentItem.id, currentItem.meaning_ko)
                  }
                  onDraftChange={onMeaningEditDraftChange}
                  onSave={onSaveMeaningEdit}
                  onCancel={onCancelMeaningEdit}
                />
              ) : null}
            </section>
            <section className="study-book-example">
              <span className="study-book-label">예문</span>
              {currentItem.example_sentence ? (
                <p className="study-book-example-text" lang="ja">
                  <HighlightedExample
                    sentence={currentItem.example_sentence}
                    surface={currentItem.surface}
                    baseForm={currentItem.base_form}
                    normalizedForm={currentItem.normalized_form}
                  />
                </p>
              ) : (
                <p className="study-book-explainer">저장된 문맥 예문이 없어요.</p>
              )}
            </section>
          </div>
        </div>
      );
    }

    return null;
  }

  function renderFsrsWaiting(state: FsrsStudySectionState) {
    const end = (
      <button type="button" className="study-book-secondary" onClick={state.onEnd}>
        이번 회차 마치기
      </button>
    );
    const again = (
      <button type="button" className="study-book-secondary" onClick={state.onRestart}>
        새 회차로 다시 보기
      </button>
    );
    const practiceRecent =
      state.isRecent && state.pendingLater > 0 && state.onPracticeRecent ? (
        <button type="button" className="study-book-secondary" onClick={state.onPracticeRecent}>
          남은 단어 연습하기
        </button>
      ) : null;
    let label = "복습 회차";
    let lead = "";
    let explainer: string | null = null;
    let actions: JSX.Element | null = end;
    switch (state.primary) {
      case "loading":
        lead = "카드를 불러오는 중이에요";
        actions = null;
        break;
      case "error":
        lead = state.errorText;
        actions = (
          <>
            {state.canReload ? (
              <button type="button" className="study-book-primary" onClick={state.onReload}>
                다시 불러오기
              </button>
            ) : null}
            {end}
          </>
        );
        break;
      case "soon":
        lead = `다음 카드는 ${formatSeoulTime(state.nextDueAt)}에 돌아와요`;
        explainer = "이 화면에서 기다리면 그때 이어서 보여 드려요.";
        break;
      case "deferred_only":
        lead = "이번 회차에서 미룬 단어만 남았어요";
        explainer = "여러 번 다시 본 단어는 이번 회차에서 잠시 미뤘어요. 예약은 그대로예요.";
        actions = (
          <>
            {end}
            {again}
          </>
        );
        break;
      case "deferred_limit":
        lead = "이번 회차에서 미룬 단어가 많아 여기서 회차를 마칠게요";
        actions = (
          <>
            {end}
            {again}
          </>
        );
        break;
      case "new_unknown":
        lead = "오늘 새 단어 수를 확인할 수 없어 새 단어는 멈췄어요";
        actions = (
          <>
            {end}
            {practiceRecent}
          </>
        );
        break;
      case "goal_reached":
        lead = state.goalReachedText;
        actions = (
          <>
            {end}
            {practiceRecent}
          </>
        );
        break;
      case "practice_done":
        label = "연습";
        lead = state.practiceEmpty ? "연습할 단어가 없어요" : "준비한 카드를 모두 넘겼어요";
        explainer = state.practiceEmpty
          ? "연습에는 한 번 이상 복습한 단어만 나와요. 새 단어는 오늘 복습이나 새 단어 학습에서 시작해요."
          : "연습은 예약에 반영되지 않아요.";
        actions = (
          <>
            {end}
            <button type="button" className="study-book-secondary" onClick={state.onRestart}>
              다시 연습하기
            </button>
          </>
        );
        break;
      default:
        lead = "지금 할 복습을 마쳤어요";
        explainer = state.nextDueAt ? formatNextReview(state.nextDueAt) : null;
        actions = (
          <>
            {end}
            {practiceRecent}
          </>
        );
    }
    return (
      <div className="study-book-center">
        <span className="study-book-label">{label}</span>
        <p className="study-book-lead" role="status">
          {lead}
        </p>
        {explainer ? <p className="study-book-explainer">{explainer}</p> : null}
        {state.noticeText ? (
          <p className="message message--info study-book-message">{state.noticeText}</p>
        ) : null}
        {actions}
        {state.goalLine && !state.isPractice ? (
          <p className="study-book-explainer study-book-fineprint">{state.goalLine}</p>
        ) : null}
        {state.notMigratedNote ? (
          <p className="study-book-explainer study-book-fineprint">
            일부 단어는 아직 새 복습 방식으로 옮겨지지 않았어요.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <section
      className="tab-panel study-panel study-book"
      aria-live="polite"
      data-book-state={bookState}
    >
      <div className="study-book-frame">
        <picture className="study-book-media" aria-hidden="true">
          {/* Source conditions must match the safe-zone variables in
              globals.css ("Review open book"). */}
          <source
            media="(min-width: 1500px) and (min-aspect-ratio: 2/1)"
            srcSet={BOOK_WIDE_ASSET}
          />
          <source media="(min-width: 1024px)" srcSet={BOOK_TALL_ASSET} />
          <img
            className="study-book-media-img"
            src={BOOK_SHEET_ASSET}
            alt=""
            draggable={false}
          />
        </picture>

        {/* Left page: deck/mode entry, then the study methods or the
            question word. On phones both pages flow as one sheet. */}
        <div className="study-book-page study-book-page--left">
          <div className="study-book-head">
            <details className="study-book-picker">
              <summary>
                <span className="study-book-picker-text">
                  {selectedDeckName} · {modeLabel}
                </span>
                <span className="study-book-picker-caret" aria-hidden="true">
                  ⌄
                </span>
              </summary>
              <div className="study-book-picker-panel">
                <label className="study-book-field">
                  학습 덱
                  <select
                    value={selectedDeckId}
                    onChange={(event) => onSelectedDeckChange(event.target.value)}
                  >
                    <option value="all">전체 단어장</option>
                    {decks.map((deck) => (
                      <option key={deck.id} value={String(deck.id)}>
                        {deck.name}
                      </option>
                    ))}
                    {sharedDeckOptions.length > 0 ? (
                      <optgroup label="학습 목록">
                        {sharedDeckOptions.map((deck) => (
                          <option key={deck.id} value={deck.id}>
                            {deck.title}
                          </option>
                        ))}
                      </optgroup>
                    ) : null}
                  </select>
                </label>
                <label className="study-book-field">
                  학습 모드
                  <select
                    value={studyMode}
                    onChange={(event) => onStudyModeChange(event.target.value as StudyMode)}
                  >
                    {/* 퀵스타트로 진입한 new/recent 모드도 select가 현재 상태를
                        그대로 보여줄 수 있도록 옵션을 하나 덧붙인다. */}
                    {selectableStudyModes.some((mode) => mode === studyMode) ? null : (
                      <option value={studyMode}>{studyModeLabels[studyMode]}</option>
                    )}
                    {selectableStudyModes.map((mode) => (
                      <option key={mode} value={mode}>
                        {fsrs ? studyModeLabels[mode] : `${studyModeLabels[mode]} (${studyModeCounts[mode]}개)`}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            </details>
            {isSessionPage && !fsrs ? (
              <span
                className="study-book-count"
                role="progressbar"
                aria-label="세션 진행률"
                aria-valuemin={0}
                aria-valuemax={items.length}
                aria-valuenow={Math.min(currentIndex + 1, items.length)}
              >
                {headCount}
              </span>
            ) : (
              <span className="study-book-count">{headCount}</span>
            )}
          </div>

          {isSessionPage && currentItem ? (
            <div className="study-book-word-area" key={currentItem.id}>
              <div className="study-book-word" lang="ja">
                {currentItem.surface || currentItem.base_form}
              </div>
              {currentItem.reading &&
              currentItem.reading !== (currentItem.surface || currentItem.base_form) ? (
                <div className="study-book-reading" lang="ja">
                  {currentItem.reading}
                </div>
              ) : null}
              <div className="study-book-pos">
                {currentItem.part_of_speech || "품사 없음"}
                {currentItem.base_form && currentItem.base_form !== currentItem.surface ? (
                  <>
                    {" · 기본형 "}
                    <span lang="ja">{currentItem.base_form}</span>
                  </>
                ) : null}
              </div>
            </div>
          ) : bookState === "complete" ? (
            <div className="study-book-word-area study-book-word-area--done">
              <p className="study-book-lead">
                {fsrs
                  ? "이번 회차를 마쳤어요"
                  : studyMode === "recent"
                    ? "방금 담은 단어를 다시 봤어요"
                    : "오늘 복습을 마쳤어요"}
              </p>
            </div>
          ) : (
            <div className="study-book-left-body">{modeList}</div>
          )}

          <div className="study-book-foot study-book-desk-only">
            {isSessionPage ? <span>{itemSourceLabel}</span> : statsToggle}
            {navLinks}
          </div>
        </div>

        {/* Right page: answer and the fixed rating row. Only the answer text
            scrolls, so a long meaning never moves the ratings. */}
        <div className="study-book-page study-book-page--right">
          <div className="study-book-head study-book-desk-only">
            <strong>{rightTitle}</strong>
            <span className="study-book-count">{headCount}</span>
          </div>

          {renderRightBody()}

          {bookState === "answer" && currentItem ? (
            <>
              {fsrs?.isPractice ? (
              <div className="study-book-rates study-book-rates--practice" role="group" aria-label="연습">
                <button
                  type="button"
                  className="study-book-rate"
                  data-tone="again"
                  aria-label="다시 볼게요: 이번 연습에서 한 번 더"
                  onClick={() => fsrs.onPracticeNext(true)}
                >
                  <BookmarkIcon className="study-book-rate-icon" />
                  <b>다시 볼게요</b>
                  <small>연습만</small>
                </button>
                <button
                  type="button"
                  className="study-book-rate"
                  data-tone="good"
                  aria-label="알겠어요: 다음 카드로"
                  onClick={() => fsrs.onPracticeNext(false)}
                >
                  <CheckCircleIcon className="study-book-rate-icon" />
                  <b>알겠어요</b>
                  <small>연습만</small>
                </button>
              </div>
              ) : (
              <div className="study-book-rates" role="group" aria-label="복습 평가">
                {ratingButtons.map(({ result, label, hint, icon: Icon }) => (
                  <button
                    key={result}
                    type="button"
                    className="study-book-rate"
                    data-tone={result}
                    data-pressed={pressedResult === result ? "true" : undefined}
                    aria-label={`${label}: ${hint}`}
                    onClick={() => {
                      setPendingResult(result);
                      onReview(result);
                    }}
                    disabled={ratingsLocked}
                  >
                    <Icon className="study-book-rate-icon" />
                    <b>{label}</b>
                    <small>{hint}</small>
                  </button>
                ))}
              </div>
              )}
              {fsrs && (fsrs.isPractice || fsrs.attemptStatus) ? (
                // FSRS 시도 상태는 도구 줄과 따로 둔다(좁은 화면에서 겹치지 않게).
                <div className="study-book-attempt" role="status">
                  {fsrs.isPractice ? <span>연습 · 예약에 반영되지 않아요</span> : null}
                  {fsrs.attemptStatus === "sending" ? <span>저장하는 중...</span> : null}
                  {fsrs.attemptStatus === "unknown" ? (
                    <>
                      <span>저장 여부를 확인하지 못했어요</span>
                      <button type="button" className="study-book-link" onClick={fsrs.onRetryAttempt}>
                        다시 시도
                      </button>
                    </>
                  ) : null}
                </div>
              ) : null}
              <div className="study-book-tools">
                {!fsrs && isReviewing ? (
                  <span className="study-book-saving" role="status">
                    저장하는 중...
                  </span>
                ) : null}
                <span>{itemSourceLabel}</span>
                {/* 뜻 수정/오류 신고는 개인 단어장(vocab_items) 전용 기능 --
                    구독 덱 lexeme 단어의 공용 뜻은 이 화면에서 수정 대상이
                    아님 (see docs/architecture/shared-lexeme-progress-storage.md). */}
                {currentItem.item_type === "vocab" && !isEditingMeaning ? (
                  <>
                    <MeaningQuickEdit
                      isEditing={false}
                      draftValue={meaningEditDraft}
                      isSaving={isSavingMeaningEdit}
                      message=""
                      onStartEdit={() =>
                        onStartMeaningEdit(currentItem.id, currentItem.meaning_ko)
                      }
                      onDraftChange={onMeaningEditDraftChange}
                      onSave={onSaveMeaningEdit}
                      onCancel={onCancelMeaningEdit}
                      triggerLabel="뜻 수정"
                      triggerClassName="study-book-link"
                    />
                    <button
                      type="button"
                      className="study-book-link"
                      onClick={() => onReportMeaning(currentItem)}
                    >
                      오류 신고
                    </button>
                  </>
                ) : null}
              </div>
            </>
          ) : null}

          <div className="study-book-foot">
            <span className="study-book-desk-only" />
            <span className="study-book-desk-only">복습 기록</span>
            <span className="study-book-phone-only">
              {isSessionPage ? "복습 노트" : statsToggle}
            </span>
            <span className="study-book-phone-only">{navLinks}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
