"use client";

import { BrandReadingFlowIllustration, BrandSectionBadge } from "./BrandElements";
import {
  BookIcon,
  CardsIcon,
  FolderIcon,
  ShareIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import type { StudyStats } from "./types";

type HomeDashboardProps = {
  isDevUser: boolean;
  studyStats: StudyStats | null;
  isStudyStatsLoading: boolean;
  recentlySavedVocabItemIdsCount: number;
  hasReadingSession: boolean;
  onStartReading: () => void;
  onTryWithSample: () => void;
  onStartTodayReview: () => void;
  onScrollToAccount: () => void;
  onStartRecentlySaved: () => void;
  onGoToVocab: () => void;
  onGoToShared: () => void;
};

const usageSteps = [
  {
    icon: BookIcon,
    title: "원문 붙여넣기",
    description: "읽고 싶은 일본어 문장을 붙여넣고 분석합니다.",
  },
  {
    icon: FolderIcon,
    title: "모르는 단어 저장",
    description: "뜻과 읽기를 확인하고, 모르는 단어만 단어장에 저장합니다.",
  },
  {
    icon: CardsIcon,
    title: "문맥 예문으로 복습",
    description: "단어가 나온 짧은 문장과 함께 SRS로 복습합니다.",
  },
];

const quickEntries = [
  {
    icon: BookIcon,
    label: "원문 읽기",
    description: "일본어 문장을 붙여넣고 모르는 단어를 골라보세요.",
  },
  {
    icon: CardsIcon,
    label: "오늘 복습",
    description: "저장한 단어를 문맥 예문과 함께 복습합니다.",
  },
  {
    icon: FolderIcon,
    label: "내 단어장",
    description: "모르는 단어와 헷갈리는 단어를 관리합니다.",
  },
  {
    icon: ShareIcon,
    label: "공유덱",
    description: "JLPT 추천 어휘와 공유된 덱을 가져옵니다.",
  },
] as const;

const startGuideSteps = [
  "원문 읽기 시작",
  "모르는 단어 저장",
  "문맥 예문으로 복습",
];

export function HomeDashboard({
  isDevUser,
  studyStats,
  isStudyStatsLoading,
  recentlySavedVocabItemIdsCount,
  hasReadingSession,
  onStartReading,
  onTryWithSample,
  onStartTodayReview,
  onScrollToAccount,
  onStartRecentlySaved,
  onGoToVocab,
  onGoToShared,
}: HomeDashboardProps) {
  const quickEntryHandlers: Record<string, () => void> = {
    "원문 읽기": onStartReading,
    "오늘 복습": onStartTodayReview,
    "내 단어장": onGoToVocab,
    공유덱: onGoToShared,
  };

  const continueCard = recentlySavedVocabItemIdsCount > 0
    ? {
        title: "방금 저장한 단어 학습",
        description: `방금 읽기 탭에서 저장한 단어 ${recentlySavedVocabItemIdsCount}개를 바로 복습할 수 있어요.`,
        actionLabel: "방금 저장한 단어 학습하기",
        icon: CardsIcon,
        onAction: onStartRecentlySaved,
      }
    : hasReadingSession
      ? {
          title: "읽던 원문 이어보기",
          description: "지난번 읽던 원문과 선택한 단어가 그대로 남아있어요.",
          actionLabel: "읽기 이어서 하기",
          icon: BookIcon,
          onAction: onStartReading,
        }
      : {
          title: "첫 원문 읽기 시작하기",
          description: "일본어 원문을 붙여넣으면 학습할 단어를 바로 추천해드려요.",
          actionLabel: "원문 읽기 시작",
          icon: SparkleIcon,
          onAction: onStartReading,
        };

  const hasRecentActivity = hasReadingSession || recentlySavedVocabItemIdsCount > 0;

  return (
    <section className="tab-panel home-dashboard" aria-live="polite">
      <div className="home-dashboard-layout">
        <div className="home-dashboard-main">
          <section className="panel-card hero-card home-hero-card">
            <div className="home-hero-layout">
              <div className="home-hero-main">
                <span className="home-hero-badge">
                  <BookIcon className="home-hero-badge-icon" />
                  일본어 원문 학습
                </span>
                <h2 className="landing-hero-title">
                  일본어 원문을 읽으며
                  <br />
                  나만의 단어장을 만들어보세요.
                </h2>
                <p className="landing-hero-subtitle">
                  웹소설, 원서, 기사 속 모르는 단어를 골라 문맥 예문과 함께
                  복습합니다.
                </p>
                <div className="landing-hero-actions">
                  <button type="button" onClick={onStartReading}>
                    <SparkleIcon className="button-icon" />
                    원문 읽기 시작
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={isDevUser ? onScrollToAccount : onStartTodayReview}
                  >
                    <CardsIcon className="button-icon" />
                    오늘 복습하기
                  </button>
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={onTryWithSample}
                  >
                    <SparkleIcon className="button-icon" />
                    샘플로 체험하기
                  </button>
                </div>
              </div>
              <BrandReadingFlowIllustration />
            </div>
          </section>

          <section className="panel-card home-quickentry-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">
                <BrandSectionBadge icon={SparkleIcon} />
                빠른 진입
              </h3>
            </div>
            <div className="home-quick-entry-grid">
              {quickEntries.map((entry) => (
                <button
                  type="button"
                  className="home-quick-entry-card"
                  key={entry.label}
                  onClick={quickEntryHandlers[entry.label]}
                >
                  <span className="home-quick-entry-icon-wrap">
                    <entry.icon className="home-quick-entry-icon" />
                  </span>
                  <span className="home-quick-entry-label">{entry.label}</span>
                  <span className="home-quick-entry-description">
                    {entry.description}
                  </span>
                </button>
              ))}
            </div>
          </section>

          <section className="panel-card home-continue-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">
                <BrandSectionBadge icon={CardsIcon} />
                이어서 학습하기
              </h3>
              {recentlySavedVocabItemIdsCount > 0 ? (
                <span className="home-continue-count-badge">
                  {recentlySavedVocabItemIdsCount}개 대기 중
                </span>
              ) : null}
            </div>
            <div className="home-continue-body">
              <continueCard.icon className="home-continue-icon" />
              <div>
                <strong>{continueCard.title}</strong>
                <p className="muted-text">{continueCard.description}</p>
              </div>
            </div>
            <button
              type="button"
              className="secondary-button home-continue-button"
              onClick={continueCard.onAction}
            >
              {continueCard.actionLabel}
            </button>
          </section>

          <section className="panel-card home-steps-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">사용 흐름 3단계</h3>
            </div>
            <div className="landing-steps">
              {usageSteps.map((step, index) => (
                <div className="landing-step-card" key={step.title}>
                  <div className="landing-step-heading">
                    <span className="landing-step-number">{index + 1}</span>
                    <span className="landing-step-icon-wrap">
                      <step.icon className="landing-step-icon" />
                    </span>
                  </div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="home-dashboard-side">
          <section className="panel-card home-today-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">오늘 학습</h3>
            </div>
            {studyStats ? (
              <div className="home-today-stats">
                <div className="home-today-stat">
                  <span>오늘 복습</span>
                  <strong>{studyStats.due_today_count}개</strong>
                </div>
                <div className="home-today-stat">
                  <span>오늘 완료</span>
                  <strong>{studyStats.reviewed_today_count}개</strong>
                </div>
                <div className="home-today-stat">
                  <span>새 단어</span>
                  <strong>{studyStats.new_count}개</strong>
                </div>
                <div className="home-today-stat">
                  <span>어려운 단어</span>
                  <strong>{studyStats.hard_count}개</strong>
                </div>
              </div>
            ) : (
              <p className="muted-text">
                {isStudyStatsLoading
                  ? "학습 통계를 불러오는 중입니다..."
                  : "아직 학습 통계가 없습니다. 단어를 저장하면 이곳에 표시돼요."}
              </p>
            )}
            <button
              type="button"
              className="ghost-button compact-button home-today-cta"
              onClick={isDevUser ? onScrollToAccount : onStartTodayReview}
            >
              오늘 복습하기
            </button>
          </section>

          <section className="panel-card note-card home-guide-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">시작 가이드</h3>
            </div>
            <ol className="home-guide-list">
              {startGuideSteps.map((step, index) => (
                <li key={step}>
                  <span className="home-guide-number">{index + 1}</span>
                  {step}
                </li>
              ))}
            </ol>
          </section>

          <section className="panel-card note-card home-trust-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">저장 정책 안내</h3>
            </div>
            <p className="landing-trust-note">
              <ShieldIcon className="landing-trust-note-icon" />
              <span className="home-trust-list-wrap">
                <span>원문 전체는 서버에 저장하지 않습니다.</span>
                <span>단어와 짧은 문맥 예문만 단어장에 저장됩니다.</span>
                <span>공유덱에는 원문 전체가 포함되지 않습니다.</span>
              </span>
            </p>
          </section>

          <section className="panel-card home-recent-card">
            <div className="panel-card-header">
              <h3 className="panel-card-title">최근 활동</h3>
            </div>
            {hasRecentActivity ? (
              <ul className="home-recent-list">
                {hasReadingSession ? (
                  <li>읽던 원문 작업이 남아있어요.</li>
                ) : null}
                {recentlySavedVocabItemIdsCount > 0 ? (
                  <li>
                    방금 저장한 단어 {recentlySavedVocabItemIdsCount}개가
                    학습을 기다리고 있어요.
                  </li>
                ) : null}
              </ul>
            ) : (
              <p className="muted-text home-recent-empty">
                아직 최근 작업이 없습니다. 원문을 읽고 단어를 저장하면 여기에
                이어서 할 일이 표시됩니다.
              </p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
