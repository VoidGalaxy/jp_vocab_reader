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
import { formatNextReview } from "./shared";
import { HighlightedExample } from "./HighlightedExample";

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
  onSelectedDeckChange: (deckId: string) => void;
  onStudyModeChange: (mode: StudyMode) => void;
  onQuickStart: (mode: StudyMode) => void;
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
  new: "새 단어 학습",
  recent: "방금 저장한 단어",
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
  onSelectedDeckChange,
  onStudyModeChange,
  onQuickStart,
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
          <p>{emptySecondaryMessages[studyMode]}</p>
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
              </dl>
              {currentItem.example_sentence ? (
                <div className="study-example-callout">
                  <span className="study-example-label">문맥 예문</span>
                  <p className="study-example-text">
                    <HighlightedExample
                      sentence={currentItem.example_sentence}
                      surface={currentItem.surface}
                      baseForm={currentItem.base_form}
                      normalizedForm={currentItem.normalized_form}
                    />
                  </p>
                </div>
              ) : null}
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
          <h3>오늘 학습 완료!</h3>
          <div className="study-complete-stats">
            <span>다시 {sessionCounts.again}개</span>
            <span>어려움 {sessionCounts.hard}개</span>
            <span>보통 {sessionCounts.good}개</span>
            <span>쉬움 {sessionCounts.easy}개</span>
            <span>총 학습 {totalStudied}개</span>
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
