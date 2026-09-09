"use client";

import { BookshelfIcon, CardFileIcon, CardsIcon, SparkleIcon } from "./icons";
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
  // Reuses sharedDecks.length page.tsx already fetches up front
  // (refreshUserScopedData) -- no new API call.
  sharedDeckCount: number;
  onGoToSharedDecks: () => void;
  // Reused only for a light one-word peek in the 단어장 shortcut's hint line
  // (desktop only, see .home-v10-shortcut-hint) -- no separate "최근 담은
  // 단어" section on Home. Same /vocab-items?sort=created_desc read the 기록
  // 탭 already makes, no new API call.
  recentWords: VocabItem[];
};

const ASSET_BASE_V10_2 = "/brand/decor/home-v10.2";

// Home V10.1 (full scene replacement) -- every prior Home iteration
// (home-v3/v4/v7/v8) stacked separately-illustrated objects (title note,
// CTA stamp, notebook cover, tab rail, Shiori peek) as CSS-positioned
// siblings over a photographed desk background, each with its own
// drop-shadow/filter. No matter how many rounds of shadow/contact/color
// tuning that structure went through, it kept reading as cut-out PNGs
// glued onto a photo rather than one photographed scene, because the
// objects and their shadows were never guaranteed to agree on geometry or
// light source -- see the old comment history (now removed) for the
// phase-by-phase record of that failing approach.
// This rebuild throws away every Home-only object image and the CSS that
// positioned/shadowed them, and replaces the whole thing with ONE opaque,
// pre-composited scene photo per breakpoint. V10.2 (`home-v10.2-scene-desktop.png`,
// `home-v10.2-scene-mobile.png`) is the same V10.1 scene with three desk
// props (washi tape, paperclip, pen) baked into the same photo at the same
// 1672x940 / 941x1672 size and aspect ratio, so no overlay coordinate below
// changes -- notebook, title note, CTA ticket, Shiori charm, index tabs,
// props, and every shadow are already baked in by the source art under one
// light source. There is nothing left for CSS to draw: `.home-v10-scene` is
// a single relative positioning root holding that one decorative <picture>
// (aria-hidden, pointer-events:none, natural aspect ratio preserved --
// never object-fit:cover) plus plain DOM overlay buttons/text positioned as
// a % of the scene, matching the pixel coordinates measured directly off
// the target mockups (see references/mockups/home-v10.1-prep/DESIGN_DELTA.md
// for the base scene, references/mockups/home-v10.2-prep/ for the prop
// composite). No box-shadow, drop-shadow, filter, gradient, or
// ::before/::after is used anywhere in this scene -- every visual object,
// shadow included, lives in the image.
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

  const vocabHint =
    recentWords.length > 0
      ? `${recentWords[0].surface} 등 모은 단어 보기`
      : "모은 단어 스티커 보기";
  const reviewHint = isDevUser
    ? "로그인하고 기록 저장하기"
    : isStudyStatsLoading
      ? "확인하는 중..."
      : dueTodayCount > 0
        ? "잊기 전에 다시 보기"
        : "오늘은 복습이 없어요";
  const decksHint =
    sharedDeckCount > 0 ? "다른 덱도 둘러보기" : "나만의 학습 덱 만들기";

  return (
    <section className="tab-panel home-dashboard home-v10" aria-live="polite">
      <div className="home-v10-scene">
        <picture className="home-v10-scene-art">
          <source
            media="(min-width: 768px)"
            srcSet={`${ASSET_BASE_V10_2}/home-v10.2-scene-desktop.png`}
          />
          <img
            className="home-v10-scene-img"
            aria-hidden="true"
            src={`${ASSET_BASE_V10_2}/home-v10.2-scene-mobile.png`}
            alt=""
            draggable={false}
          />
        </picture>

        <div className="home-v10-overlay-plane">
          <div className="home-v10-title-zone">
          <h2 className="home-v10-title">
            오늘도 한 문장,
            <br />한 단어.
          </h2>
          <p className="home-v10-subtitle">
            모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
          </p>
          </div>

          <button
          type="button"
          className="home-v10-sample"
          onClick={onTryWithSample}
        >
          샘플로 체험
          </button>

          <button
          type="button"
          className="home-v10-cta"
          onClick={onStartReading}
        >
          <span className="home-v10-cta-content">
            <SparkleIcon className="button-icon" />
            <span>원문 읽기 시작</span>
          </span>
          </button>

          <button
          type="button"
          className="home-v10-tab home-v10-tab--vocab"
          onClick={onGoToVocab}
        >
          <span className="home-v10-tab-content">
            <span className="home-v10-tab-icon">
              <CardFileIcon />
            </span>
            <span className="home-v10-tab-text">
              <span className="home-v10-tab-label">단어장</span>
              <span className="home-v10-tab-hint">{vocabHint}</span>
            </span>
          </span>
          </button>
          <button
          type="button"
          className="home-v10-tab home-v10-tab--review"
          onClick={isDevUser ? onOpenAccount : onStartTodayReview}
        >
          <span className="home-v10-tab-content">
            <span className="home-v10-tab-icon">
              <CardsIcon />
            </span>
            <span className="home-v10-tab-text">
              <span className="home-v10-tab-label">복습</span>
              <span className="home-v10-tab-hint">{reviewHint}</span>
            </span>
          </span>
          </button>
          <button
          type="button"
          className="home-v10-tab home-v10-tab--decks"
          onClick={onGoToSharedDecks}
        >
          <span className="home-v10-tab-content">
            <span className="home-v10-tab-icon">
              <BookshelfIcon />
            </span>
            <span className="home-v10-tab-text">
              <span className="home-v10-tab-label">덱</span>
              <span className="home-v10-tab-hint">{decksHint}</span>
            </span>
          </span>
          </button>
        </div>
      </div>
    </section>
  );
}
