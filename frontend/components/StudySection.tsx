"use client";

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
import { formatNextReview } from "./shared";
import { HighlightedExample } from "./HighlightedExample";
import {
  BookIcon,
  CardsIcon,
  CheckCircleIcon,
  ClockIcon,
  InboxIcon,
  RotateIcon,
  ZapIcon,
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
  onShowAnswer: () => void;
  onReview: (result: ReviewResult) => void;
};

const studyModeLabels: Record<StudyMode, string> = {
  today: "오늘 복습",
  uncertain: "헷갈리는 단어",
  unknown: "모르는 단어",
  all: "전체 학습",
  new: "새 단어 학습",
  recent: "방금 저장한 단어 복습",
};

const emptyMessages: Record<StudyMode, string> = {
  today: "오늘 복습할 단어가 없습니다.",
  uncertain: "헷갈리는 단어가 없습니다.",
  unknown: "모르는 단어가 없습니다.",
  all: "학습할 모르는 단어와 헷갈리는 단어가 없습니다.",
  new: "새로 학습할 단어가 없습니다.",
  recent: "방금 저장한 단어를 찾을 수 없습니다.",
};

const emptySecondaryMessages: Record<StudyMode, string> = {
  today: "새 단어를 추가하거나 전체 학습을 시작해보세요.",
  uncertain: "단어장 탭에서 단어를 추가하거나 분석 탭에서 새 단어를 저장해보세요.",
  unknown: "단어장 탭에서 단어를 추가하거나 분석 탭에서 새 단어를 저장해보세요.",
  all: "단어장 탭에서 단어를 추가하거나 분석 탭에서 새 단어를 저장해보세요.",
  new: "읽기나 분석 탭에서 단어를 저장하면 이곳에서 바로 학습할 수 있습니다.",
  recent: "읽기 탭에서 단어를 다시 저장해 보세요.",
};

const quickStartCta: Array<{
  mode: StudyMode;
  label: string;
  countKey: keyof StudyStats;
}> = [
  { mode: "today", label: "오늘 복습 시작", countKey: "due_today_count" },
  { mode: "new", label: "새 단어 학습", countKey: "new_count" },
  { mode: "uncertain", label: "어려운 단어 복습", countKey: "hard_count" },
  { mode: "all", label: "덱별 학습", countKey: "total_vocab_count" },
];

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
    hint: "오늘 다시 보기",
    className: "rating-again",
    icon: RotateIcon,
  },
  {
    result: "hard",
    label: "어려움",
    hint: "짧게 복습",
    className: "rating-hard",
    icon: ClockIcon,
  },
  {
    result: "good",
    label: "보통",
    hint: "예정 간격 증가",
    className: "rating-good",
    icon: CheckCircleIcon,
  },
  {
    result: "easy",
    label: "쉬움",
    hint: "더 길게 미루기",
    className: "rating-easy",
    icon: ZapIcon,
  },
];

function TodayDashboard({ stats }: { stats: StudyStats | null }) {
  if (!stats) {
    return null;
  }
  return (
    <div className="today-dashboard" role="group" aria-label="오늘 학습 대시보드">
      <div className="today-dashboard-card">
        <span>오늘 복습</span>
        <strong>{stats.due_today_count}개</strong>
      </div>
      <div className="today-dashboard-card">
        <span>오늘 완료</span>
        <strong>{stats.reviewed_today_count}개</strong>
      </div>
      <div className="today-dashboard-card">
        <span>어려운 단어</span>
        <strong>{stats.hard_count}개</strong>
      </div>
      <div className="today-dashboard-card">
        <span>새 단어</span>
        <strong>{stats.new_count}개</strong>
      </div>
    </div>
  );
}

function TodayProgress({ stats }: { stats: StudyStats | null }) {
  if (!stats) {
    return null;
  }
  const completed = stats.reviewed_today_count;
  const total = completed + stats.due_today_count;
  const percent = total > 0 ? Math.min(Math.round((completed / total) * 100), 100) : 0;
  return (
    <div className="today-progress">
      <div className="today-progress-label">
        <span>오늘 진행률</span>
        <strong>
          {completed} / {total} 완료
        </strong>
      </div>
      <div className="progress-bar" aria-hidden="true">
        <div style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

function StudyQuickStartGrid({
  stats,
  onQuickStart,
}: {
  stats: StudyStats | null;
  onQuickStart: (mode: StudyMode) => void;
}) {
  return (
    <div className="study-cta-grid" role="group" aria-label="오늘 학습 시작">
      {quickStartCta.map(({ mode, label, countKey }) => (
        <button
          key={mode}
          type="button"
          className="study-cta-button"
          onClick={() => onQuickStart(mode)}
        >
          <span className="study-cta-label">{label}</span>
          <span className="study-cta-hint">
            {stats ? `${stats[countKey]}개` : "-"}
          </span>
        </button>
      ))}
    </div>
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
  onShowAnswer,
  onReview,
}: StudySectionProps) {
  const totalStudied =
    sessionCounts.again + sessionCounts.hard + sessionCounts.good + sessionCounts.easy;
  const modeLabel = studyModeLabels[studyMode];
  const dueCount = stats?.due_today_count ?? 0;
  const uncertainCount = stats?.uncertain_count ?? 0;
  const unknownCount = stats?.unknown_count ?? 0;
  const allStudyCount = uncertainCount + unknownCount;
  const visibleProgress =
    items.length > 0 ? `${Math.min(currentIndex + 1, items.length)} / ${items.length}` : "0 / 0";

  return (
    <section className="tab-panel" aria-live="polite">
      <TodayDashboard stats={stats} />
      <TodayProgress stats={stats} />
      <StudyQuickStartGrid stats={stats} onQuickStart={onQuickStart} />

      <StatsPanel
        title="학습 현황"
        stats={stats}
        isLoading={isStatsLoading}
        message={statsMessage}
      />

      <section className="study-control-panel">
        <div className="result-heading">
          <div>
            <h2>덱과 모드 직접 선택</h2>
            <span>
              {selectedDeckName} · {modeLabel}
            </span>
          </div>
          <div className="heading-actions">
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
            <button type="button" onClick={onStart} disabled={isLoading}>
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
      </section>

      {message ? (
        <p className={`message message--${classifyMessageTone(message)}`}>
          {message}
        </p>
      ) : null}

      {!hasStarted && !currentItem && !isComplete ? (
        <div className="study-card study-ready-card">
          <CardsIcon className="empty-state-icon" />
          <h3>학습할 단어를 불러오세요</h3>
          <p>
            덱과 학습 모드를 선택한 뒤 학습 시작을 누르면 저장한 단어를 바로
            외울 수 있습니다.
          </p>
        </div>
      ) : null}

      {hasStarted && !currentItem && !isComplete ? (
        <div className="study-card study-ready-card">
          <InboxIcon className="empty-state-icon" />
          <h3>{emptyMessages[studyMode]}</h3>
          <p>{emptySecondaryMessages[studyMode]}</p>
          <div className="study-actions">
            <button type="button" onClick={onGoToReading}>
              <BookIcon className="button-icon" />
              원문 읽기 시작
            </button>
            <button type="button" className="secondary-button" onClick={onGoToVocab}>
              내 단어장 보기
            </button>
          </div>
        </div>
      ) : null}

      {currentItem && !isComplete ? (
        <div className="study-card hero-card">
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
              읽기 탭에서 저장한 단어를 바로 복습합니다. ({items.length}개 단어)
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
          <div className="study-front">
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
                  {currentItem.meaning_ko || "뜻 후보 없음"}
                </p>
              </div>
              <dl className="study-answer">
                <div>
                  <dt>읽기</dt>
                  <dd>{currentItem.reading || "-"}</dd>
                </div>
                <div>
                  <dt>품사</dt>
                  <dd>{currentItem.part_of_speech || "-"}</dd>
                </div>
                <div>
                  <dt>기본형</dt>
                  <dd>{currentItem.base_form}</dd>
                </div>
              </dl>
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
                <div className="study-example-callout">
                  <div className="study-example-heading">
                    <span className="study-example-label">문맥 예문</span>
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
                  평가를 저장하는 중입니다...
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
        <div className="study-card complete-card">
          <CheckCircleIcon className="complete-card-icon" />
          <h3>
            {studyMode === "recent" ? "방금 저장한 단어 학습 완료!" : "오늘 학습 완료!"}
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
          {stats ? (
            <p className="muted-text">오늘 완료 {stats.reviewed_today_count}개</p>
          ) : null}
          <p>
            {nextUpcomingReviewAt
              ? formatNextReview(nextUpcomingReviewAt)
              : "다음 복습 단어는 아직 예정되어 있지 않습니다."}
          </p>
          <div className="study-actions">
            <button type="button" onClick={onRestart}>
              다시 학습하기
            </button>
            {studyMode === "recent" ? (
              <>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={onGoToReading}
                >
                  읽기 탭으로 돌아가기
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => onQuickStart("today")}
                >
                  오늘 복습 보기
                </button>
              </>
            ) : null}
            <button type="button" className="secondary-button" onClick={onGoToVocab}>
              단어장으로 가기
            </button>
            <button type="button" className="secondary-button" onClick={onGoToAnalyze}>
              분석 탭으로 가기
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
