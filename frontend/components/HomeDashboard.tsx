"use client";

import { ShioriCharacter } from "./Shiori";
import { getDisplayMeaning } from "./shared";
import { BrandDeckCover } from "./BrandElements";
import {
  BookIcon,
  CardFileIcon,
  CardsIcon,
  ShieldIcon,
  SparkleIcon,
} from "./icons";
import type { StudyStats, VocabItem } from "./types";

type HomeDashboardProps = {
  isDevUser: boolean;
  studyStats: StudyStats | null;
  isStudyStatsLoading: boolean;
  onStartReading: () => void;
  onTryWithSample: () => void;
  onStartTodayReview: () => void;
  onOpenAccount: () => void;
  onGoToVocab: () => void;
  // Desk-tools direction: reuses sharedDecks.length page.tsx already fetches
  // up front (refreshUserScopedData) -- no new API call, just a count so the
  // 덱 책장 tile has real content instead of a bare label.
  sharedDeckCount: number;
  onGoToSharedDecks: () => void;
  // Index Card Study direction: up to 3 recently-saved words shown as
  // small index cards (same data page.tsx already fetches for the 기록
  // tab's "최근 담은 단어" list -- reused here, no new API call).
  recentWords: VocabItem[];
};

// Reading-first study desk: a hero (title + 1-line subcopy + one full-width
// primary CTA, one secondary CTA, one quiet sample link) sits on a desk
// "stage" (library-card-stage, the same subtle backdrop the reader/classify
// workspaces already use) together with a row of desk tools -- 단어장 노트,
// 오늘의 복습, 덱 책장 -- so the tools people actually use daily read as
// objects sitting on the desk next to the open book, not a second nav list.
// Below the desk: the 최근 담은 단어 row and a single policy line. Counts that
// used to sit in a separate chip row are folded into the CTA/tool labels
// instead, so the same number never appears twice on one screen.
export function HomeDashboard({
  isDevUser,
  studyStats,
  isStudyStatsLoading,
  onStartReading,
  onTryWithSample,
  onStartTodayReview,
  onOpenAccount,
  onGoToVocab,
  sharedDeckCount,
  onGoToSharedDecks,
  recentWords,
}: HomeDashboardProps) {
  const dueTodayCount = studyStats?.due_today_count ?? 0;
  const totalVocabCount = studyStats?.total_vocab_count ?? 0;
  const vocabValueLabel =
    totalVocabCount > 0 ? `${totalVocabCount}개 저장됨` : "아직 비어있어요";
  const reviewValueLabel = isStudyStatsLoading
    ? "확인 중..."
    : dueTodayCount > 0
      ? `${dueTodayCount}개 대기 중`
      : "오늘은 없어요";
  const sharedValueLabel =
    sharedDeckCount > 0 ? `${sharedDeckCount}개 둘러보기` : "추천 덱 보기";

  return (
    <section className="tab-panel home-dashboard" aria-live="polite">
      <div className="home-desk-stage library-card-stage">
        <section className="panel-card hero-card home-hero-card card-stack-surface">
          <div className="home-hero-main">
            <div className="home-hero-greeting">
              <span className="home-hero-badge">
                <BookIcon className="home-hero-badge-icon" />
                오늘의 책상
              </span>
            </div>
            <h2 className="landing-hero-title">
              오늘 읽을 일본어 원문을
              <br />
              펼쳐볼까요?
            </h2>
            <p className="landing-hero-subtitle">
              모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
            </p>
            <div className="landing-hero-actions">
              <button
                type="button"
                className="home-hero-primary-cta"
                onClick={onStartReading}
              >
                <SparkleIcon className="button-icon" />
                원문 읽기 시작
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={isDevUser ? onOpenAccount : onStartTodayReview}
              >
                <CardsIcon className="button-icon" />
                {isDevUser
                  ? "로그인하고 복습 기록 저장하기"
                  : `오늘 복습하기${isStudyStatsLoading ? "" : ` (${dueTodayCount})`}`}
              </button>
            </div>
            <div className="home-hero-quiet-actions">
              <button
                type="button"
                className="ghost-button compact-button"
                onClick={onTryWithSample}
              >
                샘플로 체험
              </button>
            </div>
          </div>
          <div
            className="home-hero-visual shiori-book-scene shiori-companion--hero"
            aria-hidden="true"
          >
            <ShioriCharacter variant="default" size="hero" />
          </div>
        </section>

        <div className="home-desk-tools" role="group" aria-label="책상 위 학습 도구">
          <button
            type="button"
            className="home-desk-tool home-desk-tool--vocab index-card-shell"
            onClick={onGoToVocab}
          >
            <CardFileIcon className="home-desk-tool-icon" />
            <span className="home-desk-tool-label">단어장 노트</span>
            <span className="home-desk-tool-value">{vocabValueLabel}</span>
          </button>
          <button
            type="button"
            className="home-desk-tool home-desk-tool--review index-card-shell card-stack-surface"
            onClick={onStartTodayReview}
          >
            <CardsIcon className="home-desk-tool-icon" />
            <span className="home-desk-tool-label">오늘의 복습</span>
            <span className="home-desk-tool-value">{reviewValueLabel}</span>
          </button>
          <button
            type="button"
            className="home-desk-tool home-desk-tool--shared index-card-shell"
            onClick={onGoToSharedDecks}
          >
            <BrandDeckCover tone="shared" />
            <span className="home-desk-tool-value">{sharedValueLabel}</span>
          </button>
        </div>
      </div>

      {recentWords.length > 0 ? (
        <div className="home-recent-section">
          <div className="home-recent-section-header">
            <span className="home-recent-section-title">최근 담은 단어</span>
            <button
              type="button"
              className="ghost-button compact-button"
              onClick={onGoToVocab}
            >
              어휘 노트 보기
            </button>
          </div>
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
        </div>
      ) : null}

      <p className="info-strip info-strip-quiet">
        <ShieldIcon className="info-strip-icon" />
        원문 전체는 서버에 저장하지 않아요.
      </p>
    </section>
  );
}
