"use client";

import { LibraryHeroIllustration, StudyCompanion } from "./BrandElements";
import { getDisplayMeaning } from "./shared";
import {
  BookIcon,
  CardFileIcon,
  CardsIcon,
  ChevronRightIcon,
  ClockIcon,
  FolderIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import type { StudyStats, VocabItem } from "./types";

type HomeDashboardProps = {
  isDevUser: boolean;
  studyStats: StudyStats | null;
  isStudyStatsLoading: boolean;
  recentlySavedVocabItemIdsCount: number;
  hasReadingSession: boolean;
  onStartReading: () => void;
  onTryWithSample: () => void;
  onStartTodayReview: () => void;
  onOpenAccount: () => void;
  onStartRecentlySaved: () => void;
  onGoToVocab: () => void;
  // Index Card Study direction: up to 3 recently-saved words shown as
  // small index cards (same data page.tsx already fetches for the 기록
  // tab's "최근 담은 단어" list -- reused here, no new API call).
  recentWords: VocabItem[];
};

// Lightweight-reader-first home: a hero (title + 1-line subcopy + the 3
// CTAs the core loop actually needs), a 3-chip status row, one compact
// "continue" action row, and a single policy line -- everything else the
// dashboard used to carry (사용 흐름 3단계, 시작 가이드, 빠른 진입 grid, a
// separate 최근 활동 card, a 베타 테스트 card) is either redundant with the
// hero CTAs, redundant with the now-5-item primary nav, or just decoration.
// None of it was a distinct feature -- removing it here only changes what's
// shown on this screen, not any handler/route/data below.
export function HomeDashboard({
  isDevUser,
  studyStats,
  isStudyStatsLoading,
  recentlySavedVocabItemIdsCount,
  hasReadingSession,
  onStartReading,
  onTryWithSample,
  onStartTodayReview,
  onOpenAccount,
  onStartRecentlySaved,
  onGoToVocab,
  recentWords,
}: HomeDashboardProps) {
  const continueRow = recentlySavedVocabItemIdsCount > 0
    ? {
        icon: CardsIcon,
        label: `방금 담은 단어 ${recentlySavedVocabItemIdsCount}개 복습하기`,
        onAction: onStartRecentlySaved,
      }
    : hasReadingSession
      ? {
          icon: BookIcon,
          label: "읽던 원문 이어보기",
          onAction: onStartReading,
        }
      : {
          icon: SparkleIcon,
          label: "첫 원문 읽기 시작하기",
          onAction: onStartReading,
        };

  return (
    <section className="tab-panel home-dashboard" aria-live="polite">
      <section className="panel-card hero-card home-hero-card card-stack-surface">
        <div className="home-hero-main">
          <div className="home-hero-greeting">
            <span className="home-hero-badge">
              <BookIcon className="home-hero-badge-icon" />
              오늘의 책상
            </span>
            <StudyCompanion
              mood="reading"
              size="md"
              className="study-companion-glow home-hero-companion"
            />
          </div>
          <h2 className="landing-hero-title">
            오늘 읽을 원문을
            <br />
            펼쳐볼까요?
          </h2>
          <p className="landing-hero-subtitle">
            모르는 단어를 눌러 노트에 담고, 짧게 복습하세요.
          </p>
          <div className="landing-hero-actions">
            <button type="button" onClick={onStartReading}>
              <SparkleIcon className="button-icon" />
              원문 읽기 시작
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={isDevUser ? onOpenAccount : onStartTodayReview}
            >
              <CardsIcon className="button-icon" />
              오늘 복습하기
            </button>
            <button
              type="button"
              className="ghost-button"
              onClick={onTryWithSample}
            >
              샘플로 체험
            </button>
          </div>
          <div className="home-flow-strip" aria-hidden="true">
            <span className="home-flow-step">
              <BookIcon className="home-flow-icon" />
              읽기
            </span>
            <span className="home-flow-arrow">→</span>
            <span className="home-flow-step">
              <FolderIcon className="home-flow-icon" />
              담기
            </span>
            <span className="home-flow-arrow">→</span>
            <span className="home-flow-step">
              <CardsIcon className="home-flow-icon" />
              복습
            </span>
          </div>
        </div>
        <div className="home-hero-visual" aria-hidden="true">
          <LibraryHeroIllustration />
        </div>
      </section>

      <div className="home-summary-row" role="group" aria-label="오늘 학습 요약">
        <span className="home-summary-chip">
          <CardsIcon className="home-summary-chip-icon" />
          <span>오늘 복습</span>
          <strong>
            {isStudyStatsLoading ? "-" : (studyStats?.due_today_count ?? 0)}
          </strong>
        </span>
        <span className="home-summary-chip">
          <CardFileIcon className="home-summary-chip-icon" />
          <span>최근 담은 단어</span>
          <strong>{recentlySavedVocabItemIdsCount}</strong>
        </span>
        <span className="home-summary-chip">
          <ClockIcon className="home-summary-chip-icon" />
          <span>어려운 단어</span>
          <strong>
            {isStudyStatsLoading ? "-" : (studyStats?.hard_count ?? 0)}
          </strong>
        </span>
      </div>

      {recentWords.length > 0 ? (
        <div className="home-recent-index-row" aria-label="최근 담은 단어">
          {recentWords.map((item) => (
            <div className="index-card-shell home-recent-index-card" key={item.id}>
              <span className="home-recent-index-card-surface">{item.surface}</span>
              {item.reading && item.reading !== item.surface ? (
                <span className="home-recent-index-card-reading">{item.reading}</span>
              ) : null}
              <span className="home-recent-index-card-meaning">
                {getDisplayMeaning(item.meaning_ko)}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <div className="home-desk-memo paper-corner">
        <span className="memo-label">책상 메모</span>
        <button
          type="button"
          className="ghost-button home-continue-row"
          onClick={continueRow.onAction}
        >
          <continueRow.icon className="button-icon" />
          <span>{continueRow.label}</span>
          <ChevronRightIcon className="home-continue-row-arrow" />
        </button>
      </div>

      <p className="info-strip">
        <ShieldIcon className="info-strip-icon" />
        원문 전체는 서버에 저장하지 않아요.
      </p>

      <button
        type="button"
        className="ghost-button compact-button home-vocab-link"
        onClick={onGoToVocab}
      >
        어휘 노트 보기
      </button>
    </section>
  );
}
