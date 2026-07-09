"use client";

import type {
  Deck,
  ReviewResult,
  SessionReviewCounts,
  StudyMode,
  VocabItem,
} from "./types";
import type { StudyStats } from "./types";
import { StatsPanel } from "./StatsPanel";

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
  decks: Deck[];
  selectedDeckId: string;
  selectedDeckName: string;
  studyMode: StudyMode;
  onSelectedDeckChange: (deckId: string) => void;
  onStudyModeChange: (mode: StudyMode) => void;
  onStart: () => void;
  onRestart: () => void;
  onGoToVocab: () => void;
  onGoToAnalyze: () => void;
  onShowAnswer: () => void;
  onReview: (result: ReviewResult) => void;
};

const studyModeLabels: Record<StudyMode, string> = {
  today: "오늘 복습",
  uncertain: "헷갈리는 단어",
  unknown: "모르는 단어",
  all: "전체 학습",
};

const emptyMessages: Record<StudyMode, string> = {
  today: "이 덱에는 오늘 복습할 단어가 없습니다.",
  uncertain: "헷갈리는 단어가 없습니다.",
  unknown: "모르는 단어가 없습니다.",
  all: "학습할 모르는 단어와 헷갈리는 단어가 없습니다.",
};

const ratingButtons: Array<{
  result: ReviewResult;
  label: string;
  hint: string;
  className: string;
}> = [
  { result: "again", label: "다시", hint: "오늘 다시 보기", className: "rating-again" },
  { result: "hard", label: "어려움", hint: "짧게 복습", className: "rating-hard" },
  { result: "good", label: "보통", hint: "예정 간격 증가", className: "rating-good" },
  { result: "easy", label: "쉬움", hint: "더 길게 미루기", className: "rating-easy" },
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
  decks,
  selectedDeckId,
  selectedDeckName,
  studyMode,
  onSelectedDeckChange,
  onStudyModeChange,
  onStart,
  onRestart,
  onGoToVocab,
  onGoToAnalyze,
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

      <StatsPanel
        title="학습 현황"
        stats={stats}
        isLoading={isStatsLoading}
        message={statsMessage}
      />

      <section className="study-control-panel">
        <div className="result-heading">
          <div>
            <h2>학습 모드</h2>
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
              {isLoading ? "불러오는 중..." : "학습 시작"}
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

      {message ? <p className="message">{message}</p> : null}

      {!hasStarted && !currentItem && !isComplete ? (
        <div className="study-card study-ready-card">
          <h3>학습할 단어를 불러오세요</h3>
          <p>
            덱과 학습 모드를 선택한 뒤 학습 시작을 누르면 저장한 단어를 바로
            외울 수 있습니다.
          </p>
        </div>
      ) : null}

      {hasStarted && !currentItem && !isComplete ? (
        <div className="study-card study-ready-card">
          <h3>{emptyMessages[studyMode]}</h3>
          <p>단어장 탭에서 단어를 추가하거나 분석 탭에서 새 단어를 저장해보세요.</p>
          <div className="study-actions">
            <button type="button" className="secondary-button" onClick={onGoToVocab}>
              단어장으로 가기
            </button>
            <button type="button" className="secondary-button" onClick={onGoToAnalyze}>
              분석 탭으로 가기
            </button>
          </div>
        </div>
      ) : null}

      {currentItem && !isComplete ? (
        <div className="study-card">
          <div className="study-card-header">
            <span>{modeLabel}</span>
            <strong>{visibleProgress}</strong>
          </div>
          <div className="study-front">
            <div>{currentItem.surface || currentItem.base_form}</div>
            <span>{currentItem.part_of_speech || "품사 없음"}</span>
          </div>
          {isAnswerVisible ? (
            <>
              <dl className="study-answer">
                <div>
                  <dt>읽기</dt>
                  <dd>{currentItem.reading || "-"}</dd>
                </div>
                <div>
                  <dt>뜻</dt>
                  <dd>{currentItem.meaning_ko || "-"}</dd>
                </div>
                <div>
                  <dt>품사</dt>
                  <dd>{currentItem.part_of_speech || "-"}</dd>
                </div>
                <div>
                  <dt>기본형</dt>
                  <dd>{currentItem.base_form}</dd>
                </div>
                <div className="answer-example">
                  <dt>예문</dt>
                  <dd>{currentItem.example_sentence || "-"}</dd>
                </div>
              </dl>
              <div className="study-rating-grid" role="group" aria-label="복습 평가">
                {ratingButtons.map(({ result, label, hint, className }) => (
                  <button
                    key={result}
                    type="button"
                    className={`rating-button ${className}`}
                    onClick={() => onReview(result)}
                    disabled={isReviewing}
                  >
                    <span className="rating-label">{label}</span>
                    <span className="rating-hint">{hint}</span>
                  </button>
                ))}
              </div>
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
          <h3>학습 완료</h3>
          <div className="study-complete-stats">
            <span>다시 {sessionCounts.again}개</span>
            <span>어려움 {sessionCounts.hard}개</span>
            <span>보통 {sessionCounts.good}개</span>
            <span>쉬움 {sessionCounts.easy}개</span>
            <span>총 학습 {totalStudied}개</span>
          </div>
          <p>이번 세션을 완료했습니다. 다음 학습 흐름을 바로 이어갈 수 있습니다.</p>
          <div className="study-actions">
            <button type="button" onClick={onRestart}>
              다시 학습하기
            </button>
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
