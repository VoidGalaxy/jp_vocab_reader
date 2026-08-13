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
  // Reused only for a light one-word peek in the 단어장 sticker's subtitle
  // (see vocabSubtitle below) -- no separate "최근 담은 단어" section on Home
  // anymore under the Casual Sticker Reader direction; the full list still
  // lives on the 단어장 tab itself. Same data page.tsx already fetches for
  // the 기록 tab, no new API call.
  recentWords: VocabItem[];
};

// Casual Sticker Reader (Phase 54) -- Home is a notebook cover, not a
// dashboard. One notebook-cover hero card carries the day's single primary
// action ("원문 읽기 시작") printed on the cover itself, a small pinned
// sticky note, and Shiori peeking from the corner (per the character rule:
// a corner guide, never a second hero illustration). Below it, three small
// sticker shortcuts (단어장/복습/덱) stand in for what used to be a row of
// bordered admin tiles -- qualitative one-line subtitles instead of raw
// counts, per docs/design/DESIGN.md's "minimize numbers/management" rule.
// See docs/design/mockups/casual-sticker-reader-*.png for the reference
// boards this follows.
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

  const vocabSubtitle =
    recentWords.length > 0
      ? `${recentWords[0].surface} 등 모은 단어 보기`
      : "모은 단어 스티커 보기";
  const reviewSubtitle = isDevUser
    ? "로그인하고 기록 저장하기"
    : isStudyStatsLoading
      ? "확인하는 중..."
      : dueTodayCount > 0
        ? "잊기 전에 다시 보기"
        : "오늘은 복습이 없어요";
  const decksSubtitle =
    sharedDeckCount > 0 ? "다른 덱도 둘러보기" : "나만의 학습 덱 만들기";

  return (
    <section className="tab-panel home-dashboard" aria-live="polite">
      {/* Casual Sticker Reader (Phase 67) -- home-desk-scene: on wide
          desktop this becomes a 2-column stage (cover + a vertical stack
          of shortcut notes beside it, like the mockup's "cover + floating
          notes" desk arrangement) instead of the cover and the shortcut
          row just stacking full-width one under the other. Below the
          desktop breakpoint this is a plain single-column wrapper --
          mobile/tablet render byte-for-byte the same as before this
          Phase. */}
      <div className="home-desk-scene">
      <section className="home-notebook-cover card-stack-surface">
        <span className="home-notebook-pin" aria-hidden="true" />
        <div className="home-notebook-sticky-note" aria-hidden="true">
          오늘도 책장을 열어요
        </div>
        <div className="home-notebook-body">
          <h2 className="home-notebook-title">
            오늘도 한 문장,
            <br />한 단어.
          </h2>
          <p className="home-notebook-subtitle">
            모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
          </p>
          <button
            type="button"
            className="home-notebook-cta"
            onClick={onStartReading}
          >
            <SparkleIcon className="button-icon" />
            원문 읽기 시작 →
          </button>
          <button
            type="button"
            className="ghost-button compact-button home-notebook-sample-link"
            onClick={onTryWithSample}
          >
            샘플로 체험
          </button>
        </div>
        <div className="home-notebook-shiori-corner" aria-hidden="true">
          <ShioriCharacter variant="default" size="lg" />
        </div>
        {/* Phase 73 -- cover depth details. Real spans, not
            ::before/::after, because this element already spends both
            pseudo-element slots on .card-stack-surface's own "pages
            peeking out" ghost layers (see that class below in globals.css)
            -- a same-specificity, later-declared rule on the same element
            would otherwise silently win the cascade and erase these. */}
        <span className="home-notebook-page-edge" aria-hidden="true" />
        <span className="home-notebook-tab" aria-hidden="true" />
      </section>

      <div className="home-sticker-row" role="group" aria-label="바로가기">
        <button
          type="button"
          className="home-sticker-chip home-sticker-chip--vocab"
          onClick={onGoToVocab}
        >
          <span className="home-sticker-chip-icon">
            <CardFileIcon />
          </span>
          <span className="home-sticker-chip-label">단어장</span>
          <span className="home-sticker-chip-subtitle">{vocabSubtitle}</span>
        </button>
        <button
          type="button"
          className="home-sticker-chip home-sticker-chip--review"
          onClick={isDevUser ? onOpenAccount : onStartTodayReview}
        >
          <span className="home-sticker-chip-icon" aria-hidden="true">
            <ShioriCharacter variant="review" size="md" />
          </span>
          <span className="home-sticker-chip-label">복습</span>
          <span className="home-sticker-chip-subtitle">{reviewSubtitle}</span>
        </button>
        <button
          type="button"
          className="home-sticker-chip home-sticker-chip--decks"
          onClick={onGoToSharedDecks}
        >
          <span className="home-sticker-chip-icon">
            <BookshelfIcon />
          </span>
          <span className="home-sticker-chip-label">덱</span>
          <span className="home-sticker-chip-subtitle">{decksSubtitle}</span>
        </button>
      </div>

      {/* Phase 73 -- desk prop layer: a plant, tape roll + binder clip, a pen,
          and a cup/paper-scrap, all pure-CSS shapes (no new images) sitting
          around the cover/sticker notes like objects left on the desk.
          Rendered last (not first) so it paints on top of the cover/sticker
          boxes it overlaps at the corners -- otherwise the props would be
          clipped to only the sliver that falls outside those boxes.
          pointer-events:none (on the wrapper, inherited by every prop) +
          aria-hidden means it never intercepts clicks or gets announced,
          regardless of paint order. Only rendered at the >=1024px tier
          .home-desk-scene already uses for its 2-column stage. */}
      <div className="home-desk-props" aria-hidden="true">
        <span className="home-desk-prop home-desk-prop--plant" />
        <span className="home-desk-prop home-desk-prop--stationery" />
        <span className="home-desk-prop home-desk-prop--pen" />
        <span className="home-desk-prop home-desk-prop--cup" />
      </div>
      </div>

      <p className="info-strip info-strip-quiet">
        <ShieldIcon className="info-strip-icon" />
        원문 전체는 서버에 저장하지 않아요.
      </p>
    </section>
  );
}
