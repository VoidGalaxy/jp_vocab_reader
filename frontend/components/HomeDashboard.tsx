"use client";

import { ShioriCharacter } from "./Shiori";
import { BookshelfIcon, CardFileIcon, ShieldIcon, SparkleIcon } from "./icons";
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
  // (desktop only, see .home-scene-v2-shortcut-hint) -- no separate "최근
  // 담은 단어" section on Home. Same /vocab-items?sort=created_desc read the
  // 기록 탭 already makes, no new API call.
  recentWords: VocabItem[];
};

// Phase 168 (Home V2 Full Scene Replacement) -- Phase 159 fixed the
// shortcuts reading as a second cluster beside the book, but the book
// itself was still a CSS-drawn cutout (.home-cover-object, a transparent
// PNG at max-width:760px) sitting inside a centered column, which is
// exactly the "hero card in the middle of a wide empty wood board" shape
// the V2 bible names as a failure -- the desktop screenshot still read as
// an app hero panel with a photo behind it, not a desk. This pass throws
// out that whole object/column model: `.home-scene-v2-frame` is now a
// single full-bleed <picture> of the real V2 desk photograph (mobile
// notebook-with-torn-note-and-sticky-tabs shot below 1024px, desktop
// notebook-cover-on-a-full-desk shot at/above it), sized to the photo's
// own aspect ratio at 100% of the available width instead of capped at a
// fixed px hero size -- so the scene itself fills the first viewport
// however wide the page box is, rather than leaving wood on either side
// of a narrow centered card. Every live piece (title note, CTA, three
// shortcuts, Shiori, privacy line) is absolutely positioned as a percent
// of that same photo, calibrated per breakpoint against where that
// specific photo actually has paper/cover/tab room -- not a shared layout
// reused across two differently-composed images.
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
    <section className="tab-panel home-dashboard home-scene-v2" aria-live="polite">
      <div className="home-scene-v2-frame">
        {/* Two separate photographs, not one crop of the other -- the
            mobile shot already has a torn paper note and three sticky
            tabs built into the composition, the desktop shot is a plain
            cover with room fanned out beside it. <picture> means only the
            breakpoint-matched file is ever requested. */}
        <picture className="home-scene-v2-media">
          <source
            media="(min-width: 1024px)"
            srcSet="/brand/decor/v2/v2-home-notebook-desktop-16x9.webp"
          />
          <img
            className="home-scene-v2-media-img"
            src="/brand/decor/v2/v2-home-notebook-mobile-9x16.webp"
            alt=""
            draggable={false}
          />
        </picture>

        <div className="home-scene-v2-cover-field">
          <div className="home-scene-v2-note">
            <h2 className="home-scene-v2-title">
              오늘도 한 문장,
              <br />한 단어.
            </h2>
            <p className="home-scene-v2-subtitle">
              모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
            </p>
            <button
              type="button"
              className="home-scene-v2-sample"
              onClick={onTryWithSample}
            >
              샘플로 체험
            </button>
          </div>

          <button
            type="button"
            className="home-scene-v2-stamp"
            onClick={onStartReading}
          >
            <SparkleIcon className="button-icon" />
            <span>원문 읽기 시작</span>
          </button>

          <p className="home-scene-v2-privacy">
            <ShieldIcon className="home-scene-v2-privacy-icon" />
            원문 전체는 서버에 저장하지 않아요.
          </p>
        </div>

        <div className="home-scene-v2-edge-field">
          <div className="home-scene-v2-shortcuts" role="group" aria-label="바로가기">
            <button
              type="button"
              className="home-scene-v2-shortcut home-scene-v2-shortcut--vocab"
              onClick={onGoToVocab}
            >
              <span className="home-scene-v2-shortcut-icon">
                <CardFileIcon />
              </span>
              <span className="home-scene-v2-shortcut-text">
                <span className="home-scene-v2-shortcut-label">단어장</span>
                <span className="home-scene-v2-shortcut-hint">{vocabHint}</span>
              </span>
            </button>
            <button
              type="button"
              className="home-scene-v2-shortcut home-scene-v2-shortcut--review"
              onClick={isDevUser ? onOpenAccount : onStartTodayReview}
            >
              <span className="home-scene-v2-shortcut-icon home-scene-v2-shortcut-icon--character">
                <ShioriCharacter variant="review" size="sm" />
              </span>
              <span className="home-scene-v2-shortcut-text">
                <span className="home-scene-v2-shortcut-label">복습</span>
                <span className="home-scene-v2-shortcut-hint">{reviewHint}</span>
              </span>
            </button>
            <button
              type="button"
              className="home-scene-v2-shortcut home-scene-v2-shortcut--decks"
              onClick={onGoToSharedDecks}
            >
              <span className="home-scene-v2-shortcut-icon">
                <BookshelfIcon />
              </span>
              <span className="home-scene-v2-shortcut-text">
                <span className="home-scene-v2-shortcut-label">덱</span>
                <span className="home-scene-v2-shortcut-hint">{decksHint}</span>
              </span>
            </button>
          </div>

          <span className="home-scene-v2-charm" aria-hidden="true">
            <ShioriCharacter variant="default" size="md" />
          </span>
        </div>
      </div>
    </section>
  );
}
