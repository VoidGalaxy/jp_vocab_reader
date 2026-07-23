"use client";

import { AppEmptyState } from "./BrandElements";
import { ShioriStamp } from "./Shiori";
import { classifyMessageTone } from "./coverageUtils";
import type {
  Deck,
  ReviewResult,
  SessionReviewCounts,
  StudyMode,
  VocabItem,
} from "./types";
import type { StudyStats } from "./types";
import { StatsPanel } from "./StatsPanel";
import { formatNextReview, getDisplayMeaning } from "./shared";
import { HighlightedExample } from "./HighlightedExample";
import {
  BookIcon,
  BookmarkIcon,
  BookshelfIcon,
  CardsIcon,
  CheckCircleIcon,
  PencilIcon,
  SparkleIcon,
} from "./icons";
import { MeaningQuickEdit } from "./MeaningQuickEdit";

type StudySectionProps = {
  items: VocabItem[];
  currentItem?: VocabItem;
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
  decks: Deck[];
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
  onReportMeaning: (item: VocabItem) => void;
  onSelectedDeckChange: (deckId: string) => void;
  onStudyModeChange: (mode: StudyMode) => void;
  onQuickStart: (mode: StudyMode) => void;
  onStart: () => void;
  onRestart: () => void;
  onGoToVocab: () => void;
  onGoToAnalyze: () => void;
  onGoToReading: () => void;
  onGoToShared: () => void;
  onShowAnswer: () => void;
  onReview: (result: ReviewResult) => void;
};

const studyModeLabels: Record<StudyMode, string> = {
  today: "오늘 복습",
  uncertain: "헷갈리는 단어",
  unknown: "모르는 단어",
  all: "전체 학습",
  new: "새 단어 학습",
  recent: "방금 담은 단어 복습",
};

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

const quickStartCta: Array<{
  mode: StudyMode;
  label: string;
  countKey: keyof StudyStats;
  primary?: boolean;
}> = [
  { mode: "today", label: "오늘 복습 시작", countKey: "due_today_count", primary: true },
  { mode: "new", label: "새 단어 학습", countKey: "new_count" },
  { mode: "uncertain", label: "어려운 단어 복습", countKey: "hard_count" },
  { mode: "all", label: "덱별 학습", countKey: "total_vocab_count" },
];

// Each rating gets its own icon meaning, not just its own color -- 다시
// (책갈피를 다시 꽂아둔다), 어려움 (연필로 메모해 둔다), 보통 (확인 체크),
// 쉬움 (반짝 스탬프) -- so the 4-way choice reads as four different actions
// at a glance, not four same-shape buttons in different colors.
const ratingButtons: Array<{
  result: ReviewResult;
  label: string;
  hint: string;
  className: string;
  icon: (props: { className?: string }) => JSX.Element;
}> = [
  {
    result: "again",
    label: "다시",
    hint: "곧 다시 보기",
    className: "rating-again",
    icon: BookmarkIcon,
  },
  {
    result: "hard",
    label: "어려움",
    hint: "짧게 복습",
    className: "rating-hard",
    icon: PencilIcon,
  },
  {
    result: "good",
    label: "보통",
    hint: "다음 복습 예약",
    className: "rating-good",
    icon: CheckCircleIcon,
  },
  {
    result: "easy",
    label: "쉬움",
    hint: "간격 늘리기",
    className: "rating-easy",
    icon: SparkleIcon,
  },
];

// "오늘의 복습 준비" hero -- the one card the tab wants seen first. Each
// quick-start tile already shows its own count (오늘 복습/새 단어/어려운
// 단어/전체), so a separate stat-dashboard strip above it would just repeat
// the same numbers twice; the only number that isn't already on a tile is
// "오늘 완료", folded in here as a single compact progress line instead of
// its own stat-grid section.
function StudyQuickStartHero({
  stats,
  onQuickStart,
  onGoToVocab,
  onGoToReading,
}: {
  stats: StudyStats | null;
  onQuickStart: (mode: StudyMode) => void;
  onGoToVocab: () => void;
  onGoToReading: () => void;
}) {
  const completed = stats?.reviewed_today_count ?? 0;
  const total = completed + (stats?.due_today_count ?? 0);
  const percent = total > 0 ? Math.min(Math.round((completed / total) * 100), 100) : 0;

  return (
    <section className="study-hero-card hero-card">
      <div className="study-hero-header">
        <CardsIcon className="study-hero-icon" />
        <div>
          <h2>오늘 복습을 시작해볼까요?</h2>
          <p>담아둔 단어를 문맥 예문과 함께 다시 확인해요.</p>
        </div>
      </div>
      {total > 0 ? (
        <div className="study-compact-progress">
          <div
            className="progress-bar study-compact-progress-bar"
            role="progressbar"
            aria-label="오늘 학습 진행률"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent}
          >
            <div style={{ width: `${percent}%` }} />
          </div>
          <span className="study-compact-progress-label">
            오늘 {completed} / {total} 완료
          </span>
        </div>
      ) : null}
      <div className="study-cta-grid" role="group" aria-label="오늘 학습 시작">
        {quickStartCta.map(({ mode, label, countKey, primary }) => (
          <button
            key={mode}
            type="button"
            className={`study-cta-button${primary ? " study-cta-button-primary" : ""}`}
            onClick={() => onQuickStart(mode)}
          >
            <span className="study-cta-label">{label}</span>
            <span className="study-cta-hint">
              {stats ? `${stats[countKey]}개` : "-"}
            </span>
          </button>
        ))}
      </div>
      <div className="study-hero-secondary-links">
        <button
          type="button"
          className="ghost-button compact-button study-hero-secondary-link"
          onClick={onGoToReading}
        >
          <BookIcon className="button-icon" />
          원문 읽기
        </button>
        <button
          type="button"
          className="ghost-button compact-button study-hero-secondary-link"
          onClick={onGoToVocab}
        >
          어휘 노트 보기
        </button>
      </div>
    </section>
  );
}

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
  decks,
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
  onGoToAnalyze,
  onGoToReading,
  onGoToShared,
  onShowAnswer,
  onReview,
}: StudySectionProps) {
  const totalStudied =
    sessionCounts.again + sessionCounts.hard + sessionCounts.good + sessionCounts.easy;
  // One combined line instead of a separate paragraph per rating -- the
  // stat grid above already shows each count, so this only needs to say
  // *what happens next* for the ratings that actually occurred this session.
  const completionHintParts: string[] = [];
  if (sessionCounts.again > 0) {
    completionHintParts.push(`다시 ${sessionCounts.again}개는 5분 후 재등장`);
  }
  if (sessionCounts.hard > 0) {
    completionHintParts.push(`어려움 ${sessionCounts.hard}개는 곧 재등장`);
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
  const visibleProgress =
    items.length > 0 ? `${Math.min(currentIndex + 1, items.length)} / ${items.length}` : "0 / 0";
  // While a card is actively on screen, the dashboard/CTA chrome above it is
  // hidden -- the review flow should read as one focused flashcard, not a
  // stats screen with a card wedged underneath it.
  const isReviewingActive = Boolean(currentItem) && !isComplete;

  return (
    <section className="tab-panel study-panel" aria-live="polite">
      {!isReviewingActive ? (
        <>
          <StudyQuickStartHero
            stats={stats}
            onQuickStart={onQuickStart}
            onGoToVocab={onGoToVocab}
            onGoToReading={onGoToReading}
          />

          <section className="study-control-panel study-control-panel-compact">
            <div className="study-control-heading">
              <h3>덱과 모드 직접 선택</h3>
              <span>
                {selectedDeckName} · {modeLabel}
              </span>
            </div>

            <div className="study-mode-grid" role="group" aria-label="학습 모드">
              {(["today", "uncertain", "unknown", "all"] as StudyMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={
                    studyMode === mode
                      ? "study-mode-button active-study-mode"
                      : "study-mode-button"
                  }
                  onClick={() => onStudyModeChange(mode)}
                >
                  <span>{studyModeLabels[mode]}</span>
                  <strong>
                    {mode === "today"
                      ? dueCount
                      : mode === "uncertain"
                        ? uncertainCount
                        : mode === "unknown"
                          ? unknownCount
                          : allStudyCount}
                    개
                  </strong>
                </button>
              ))}
            </div>

            <div className="study-control-footer">
              <label className="inline-field">
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
                </select>
              </label>
              <button
                type="button"
                className="study-start-button"
                onClick={onStart}
                disabled={isLoading}
              >
                {isLoading ? (
                  "불러오는 중..."
                ) : (
                  <>
                    <CardsIcon className="button-icon" />
                    학습 시작
                  </>
                )}
              </button>
            </div>
          </section>

          <details className="study-stats-collapsible">
            <summary>학습 현황 자세히 보기</summary>
            <StatsPanel
              title="학습 현황"
              stats={stats}
              isLoading={isStatsLoading}
              message={statsMessage}
            />
          </details>
        </>
      ) : null}

      {message ? (
        <p
          className={`message message--${classifyMessageTone(message)}${
            isReviewingActive ? " study-rating-toast" : ""
          }`}
        >
          {message}
        </p>
      ) : null}

      {/* Desk stage: every "focused single card" state (ready/empty/active/
          complete) shares one wide backdrop instead of each .study-card
          floating alone in the workspace's empty margins -- keeps the card
          itself at its existing centered width/size, just gives the space
          around it a subtle desk surface instead of reading as unfinished
          empty page. */}
      <div className="desk-surface desk-surface-stage">
      {!hasStarted && !currentItem && !isComplete ? (
        <AppEmptyState
          mood="review"
          moodSize="xl"
          className="study-card study-ready-card"
          title="학습할 단어를 불러오세요"
          description="덱과 학습 모드를 선택한 뒤 복습을 시작할 수 있어요."
        />
      ) : null}

      {hasStarted && !currentItem && !isComplete ? (
        <AppEmptyState
          mood="empty"
          moodSize="xl"
          className="study-card study-ready-card"
          title={emptyMessages[studyMode]}
          description={emptySecondaryMessages[studyMode]}
        >
          <div className="study-actions">
            <button type="button" onClick={onGoToReading}>
              <BookIcon className="button-icon" />
              원문 읽기 시작
            </button>
            <button type="button" className="secondary-button" onClick={onGoToVocab}>
              어휘 노트 보기
            </button>
            <button type="button" className="ghost-button" onClick={onGoToShared}>
              <BookshelfIcon className="button-icon" />
              덱 책장 둘러보기
            </button>
          </div>
        </AppEmptyState>
      ) : null}

      {currentItem && !isComplete ? (
        <div className="study-card hero-card paper-corner card-stack-surface">
          <div
            className={`study-card-header${
              studyMode === "recent" ? " study-card-header-recent" : ""
            }`}
          >
            <span>{modeLabel}</span>
            <strong>{visibleProgress}</strong>
          </div>
          {studyMode === "recent" ? (
            <p className="study-card-recent-hint">
              원문 읽기에서 담은 단어를 바로 복습해요. ({items.length}개 단어)
            </p>
          ) : null}
          <div
            className="progress-bar study-card-progress"
            role="progressbar"
            aria-label="세션 진행률"
            aria-valuemin={0}
            aria-valuemax={items.length}
            aria-valuenow={Math.min(currentIndex + 1, items.length)}
          >
            <div
              style={{
                width:
                  items.length > 0
                    ? `${Math.round(
                        (Math.min(currentIndex + 1, items.length) / items.length) * 100,
                      )}%`
                    : "0%",
              }}
            />
          </div>
          <div className="study-front app-slide-up" key={currentItem.id}>
            <div className="study-front-word">
              {currentItem.surface || currentItem.base_form}
            </div>
            {currentItem.reading &&
            currentItem.reading !== (currentItem.surface || currentItem.base_form) ? (
              <div className="study-front-reading">{currentItem.reading}</div>
            ) : null}
            <span>{currentItem.part_of_speech || "품사 없음"}</span>
          </div>
          {isAnswerVisible ? (
            <>
              <div className="study-meaning-hero">
                <span className="study-meaning-label">뜻</span>
                <p className="study-meaning-text">
                  {getDisplayMeaning(currentItem.meaning_ko)}
                </p>
              </div>
              <div className="token-sheet-meta-row study-answer-tags">
                {currentItem.reading ? (
                  <span className="token-sheet-meta-tag">
                    읽기 {currentItem.reading}
                  </span>
                ) : null}
                {currentItem.part_of_speech ? (
                  <span className="token-sheet-meta-tag">
                    {currentItem.part_of_speech}
                  </span>
                ) : null}
                {currentItem.base_form &&
                currentItem.base_form !== currentItem.surface ? (
                  <span className="token-sheet-meta-tag">
                    기본형 {currentItem.base_form}
                  </span>
                ) : null}
              </div>
              <div className="meaning-actions-row">
                <MeaningQuickEdit
                  isEditing={meaningEditItemId === currentItem.id}
                  draftValue={meaningEditDraft}
                  isSaving={isSavingMeaningEdit}
                  message={
                    meaningEditItemId === currentItem.id
                      ? meaningEditMessage
                      : ""
                  }
                  onStartEdit={() =>
                    onStartMeaningEdit(currentItem.id, currentItem.meaning_ko)
                  }
                  onDraftChange={onMeaningEditDraftChange}
                  onSave={onSaveMeaningEdit}
                  onCancel={onCancelMeaningEdit}
                />
                {meaningEditItemId !== currentItem.id ? (
                  <button
                    type="button"
                    className="ghost-button compact-button"
                    onClick={() => onReportMeaning(currentItem)}
                  >
                    뜻 오류 신고
                  </button>
                ) : null}
              </div>
              {currentItem.example_sentence ? (
                <div className="study-example-callout paper-corner">
                  <div className="study-example-heading">
                    <span className="memo-label">예문</span>
                    <span className="study-example-sublabel">
                      이 단어가 나온 문장
                    </span>
                  </div>
                  <p className="study-example-text">
                    <HighlightedExample
                      sentence={currentItem.example_sentence}
                      surface={currentItem.surface}
                      baseForm={currentItem.base_form}
                      normalizedForm={currentItem.normalized_form}
                    />
                  </p>
                </div>
              ) : (
                <p className="study-example-empty">저장된 문맥 예문이 없습니다.</p>
              )}
              <div className="study-rating-grid" role="group" aria-label="복습 평가">
                {ratingButtons.map(({ result, label, hint, className, icon: Icon }) => (
                  <button
                    key={result}
                    type="button"
                    className={`rating-button ${className}`}
                    onClick={() => onReview(result)}
                    disabled={isReviewing}
                  >
                    <Icon className="rating-icon" />
                    <span className="rating-label">{label}</span>
                    <span className="rating-hint">{hint}</span>
                  </button>
                ))}
              </div>
              {isReviewing ? (
                <p className="study-reviewing-hint" role="status" aria-live="polite">
                  복습 결과를 저장하는 중이에요...
                </p>
              ) : null}
            </>
          ) : (
            <div className="study-actions">
              <button type="button" onClick={onShowAnswer}>
                정답 보기
              </button>
            </div>
          )}
        </div>
      ) : null}

      {isComplete ? (
        <div className="study-card complete-card card-stack-surface index-card-shell">
          <ShioriStamp variant="success" label="완료" />
          <h3>
            {studyMode === "recent"
              ? "방금 담은 단어 복습을 마쳤어요."
              : "오늘 복습을 마쳤어요."}
          </h3>
          <div className="study-complete-stats">
            <div className="study-complete-stat study-complete-stat-again">
              <span>다시</span>
              <strong>{sessionCounts.again}개</strong>
            </div>
            <div className="study-complete-stat study-complete-stat-hard">
              <span>어려움</span>
              <strong>{sessionCounts.hard}개</strong>
            </div>
            <div className="study-complete-stat study-complete-stat-good">
              <span>보통</span>
              <strong>{sessionCounts.good}개</strong>
            </div>
            <div className="study-complete-stat study-complete-stat-easy">
              <span>쉬움</span>
              <strong>{sessionCounts.easy}개</strong>
            </div>
            <div className="study-complete-stat study-complete-stat-total">
              <span>총 학습</span>
              <strong>{totalStudied}개</strong>
            </div>
          </div>
          {completionHint ? <p className="muted-text">{completionHint}</p> : null}
          <p>
            {nextUpcomingReviewAt
              ? formatNextReview(nextUpcomingReviewAt)
              : "다음 복습 단어는 아직 예정되어 있지 않습니다."}
          </p>
          <div className="study-actions">
            <button type="button" onClick={onRestart}>
              한 번 더 복습
            </button>
            <button type="button" className="secondary-button" onClick={onGoToReading}>
              <BookIcon className="button-icon" />
              원문 읽기 시작
            </button>
            <button type="button" className="ghost-button" onClick={onGoToVocab}>
              어휘 노트 보기
            </button>
            {studyMode === "recent" ? (
              <button
                type="button"
                className="ghost-button"
                onClick={() => onQuickStart("today")}
              >
                오늘 복습 보기
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
      </div>
    </section>
  );
}
