"use client";

import type { StudyStats } from "./types";

type HomeDashboardProps = {
  isDevUser: boolean;
  studyStats: StudyStats | null;
  isStudyStatsLoading: boolean;
  onStartReading: () => void;
  onTryWithSample: () => void;
  onStartTodayReview: () => void;
  // Plain switch to the study tab, used when nothing is due today -- the
  // cover must not auto-start an empty review queue.
  onGoToStudy: () => void;
  onOpenAccount: () => void;
  onGoToVocab: () => void;
  onGoToSharedDecks: () => void;
  onGoToAnalyze: () => void;
  onGoToStats: () => void;
};

type ReviewState = "login" | "loading" | "zero" | "due";

// Home B2 binding scene (references/mockups/home-b2-binding-final/gateA).
// One textless photographed scene -- a bound cover above a six-file tray --
// with every word and hit zone as live DOM on top of it. Desktop (>=1024px)
// lays the cover and six files over the single scene image at coordinates
// measured off the 1672x941 source; tablet and mobile rebuild the same
// objects instead of shrinking them: the cover becomes a 9-slice of its own
// strip, and each file carries its own compartment cut so rows of 3+3
// (tablet) or 2+2+2 (mobile, compact) stay one continuous tray. No text or
// button is baked into any image.
export function HomeDashboard({
  isDevUser,
  studyStats,
  isStudyStatsLoading,
  onStartReading,
  onTryWithSample,
  onStartTodayReview,
  onGoToStudy,
  onOpenAccount,
  onGoToVocab,
  onGoToSharedDecks,
  onGoToAnalyze,
  onGoToStats,
}: HomeDashboardProps) {
  const dueTodayCount = studyStats?.due_today_count ?? 0;
  const reviewState: ReviewState = isDevUser
    ? "login"
    : isStudyStatsLoading
      ? "loading"
      : dueTodayCount > 0
        ? "due"
        : "zero";

  const review = {
    login: {
      value: "로그인 필요",
      note: "로그인하고 기록 남기기 →",
      label: "로그인하고 복습 기록 남기기",
      onClick: onOpenAccount,
    },
    loading: {
      value: "확인 중",
      note: "잠시만요",
      label: "오늘 복습 수 확인 중",
      onClick: undefined,
    },
    zero: {
      value: "0개",
      note: "오늘은 모두 끝냈어요",
      label: "오늘 복습 0개, 복습 탭으로 이동",
      onClick: onGoToStudy,
    },
    due: {
      value: `${dueTodayCount}개`,
      note: "복습 시작 →",
      label: `오늘 복습 ${dueTodayCount}개 시작하기`,
      onClick: onStartTodayReview,
    },
  }[reviewState];

  const files = [
    { key: "reading", name: "읽기", hint: "원문에서 시작", onClick: onStartReading },
    { key: "vocab", name: "단어장", hint: "모은 단어", onClick: onGoToVocab },
    { key: "study", name: "복습", hint: "다시 익히기", onClick: onGoToStudy },
    { key: "decks", name: "덱", hint: "학습 묶음", onClick: onGoToSharedDecks },
    { key: "analyze", name: "분류", hint: "상태 살피기", onClick: onGoToAnalyze },
    { key: "stats", name: "통계", hint: "기록 보기", onClick: onGoToStats },
  ];

  return (
    <section
      className="tab-panel home-binding"
      aria-labelledby="home-binding-title"
    >
      <div className="home-binding-stage">
        <div className="home-binding-core">
          <div className="home-binding-desk" aria-hidden="true" />

          <div className="home-binding-cover">
            <div className="home-binding-spine" aria-hidden="true">
              읽고
              <br />
              남기는
              <br />
              단어
            </div>
            <div className="home-binding-brand">
              <p className="home-binding-kicker">일본어 원문 읽기 단어장</p>
              <h2 id="home-binding-title" className="home-binding-title">
                책갈피
              </h2>
              <p className="home-binding-desc">
                읽고 모은 단어를 오래 기억하도록
              </p>
              <button
                type="button"
                className="home-binding-sample"
                onClick={onTryWithSample}
              >
                샘플로 체험하기
              </button>
            </div>
            <button
              type="button"
              className={`home-binding-review home-binding-review--${reviewState}`}
              onClick={review.onClick}
              disabled={reviewState === "loading"}
              aria-busy={reviewState === "loading" ? true : undefined}
              aria-label={review.label}
            >
              <span className="home-binding-review-label">오늘 복습</span>
              <strong className="home-binding-review-value">{review.value}</strong>
              <span className="home-binding-review-note">{review.note}</span>
            </button>
          </div>

          <nav className="home-binding-files" aria-label="학습 공간">
            {files.map((file, index) => (
              <button
                key={file.key}
                type="button"
                className={`home-binding-file home-binding-file--${index + 1}`}
                onClick={file.onClick}
              >
                <span className="home-binding-file-name">{file.name}</span>
                <span className="home-binding-file-hint">{file.hint}</span>
              </button>
            ))}
          </nav>
        </div>
      </div>
    </section>
  );
}
