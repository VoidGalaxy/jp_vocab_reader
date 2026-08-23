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
  // Reused only for a light one-word peek in the 단어장 sticker's hint line
  // (desktop only, see .home-sticker-hint) -- no separate "최근 담은 단어"
  // section on Home. Same /vocab-items?sort=created_desc read the 기록 탭
  // already makes, no new API call.
  recentWords: VocabItem[];
};

// Phase 159 (Home v2 Scene Rebuild) -- every prior Home pass (118's card
// chrome removal, 151's scale/overlap correction) still left the shortcuts
// as their own grid column beside the book: `.home-stage { grid-template-
// columns: 1.4fr 0.85fr }`, book on one side, three sticky notes stacked on
// the other. Fixing the book's size and the note's overlap never fixed
// that underlying shape -- two independent tracks read as two clusters (a
// "hero text panel" and a "shortcut column") no matter how tightly they
// were packed, which is exactly what this phase's brief names as the
// remaining failure. There is no grid here any more: `.home-hero-cluster`
// is a single relatively-positioned object sized to the book photo itself,
// and the three shortcuts are `.home-shortcut-tab` elements absolutely
// positioned along the book's own bottom edge, overlapping it like tabs
// tucked under a notebook lying on a desk -- physically part of the same
// object the title note sits on top of, not a second surface beside it.
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
    <section className="tab-panel home-dashboard home-scene" aria-live="polite">
      <div className="home-hero">
        {/* Phase 159 -- home-hero-cluster is the one hero object: sized to
            the book photo itself (.home-cover-object drives the box's
            width), not a grid column. The title note still overlaps the
            book's top edge (Phase 151's technique, unchanged), and the
            three shortcuts (.home-shortcut-tabs, new) are absolutely
            positioned along the book's own bottom edge instead of living in
            a sibling grid track -- see globals.css for how each piece is
            actually pinned. Everything in this cluster shares one
            positioning context, which is what makes it read as a single
            object instead of two. */}
        <div className="home-hero-cluster">
          <div className="home-cover-note">
            <h2 className="home-cover-title">
              오늘도 한 문장,
              <br />한 단어.
            </h2>
            <p className="home-cover-subtitle">
              모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
            </p>
            <button
              type="button"
              className="home-cover-cta"
              onClick={onStartReading}
            >
              <SparkleIcon className="button-icon" />
              원문 읽기 시작 →
            </button>
            <button
              type="button"
              className="home-cover-sample"
              onClick={onTryWithSample}
            >
              샘플로 체험
            </button>
          </div>

          <div className="home-cover-object">
            <span className="home-cover-charm" aria-hidden="true">
              <ShioriCharacter variant="default" size="lg" />
            </span>
          </div>

          {/* Phase 159 -- was .home-stickers, a full sibling grid column
              beside the book (three tall sticky-note cards stacked on
              their own track). Discarded, not resized: these are now
              .home-shortcut-tab elements pinned along the book's bottom
              edge, each overlapping it by a few px like a tab tucked
              under a notebook lying on a desk -- part of the book object
              itself, not a second surface next to it. Same three
              onClick handlers, same dev-user account-panel branch on
              복습, unchanged. */}
          <div className="home-shortcut-tabs" role="group" aria-label="바로가기">
            <button
              type="button"
              className="home-shortcut-tab home-shortcut-tab--vocab"
              onClick={onGoToVocab}
            >
              <span className="home-shortcut-tab-icon">
                <CardFileIcon />
              </span>
              <span className="home-shortcut-tab-text">
                <span className="home-shortcut-tab-label">단어장</span>
                <span className="home-shortcut-tab-hint">{vocabHint}</span>
              </span>
            </button>
            <button
              type="button"
              className="home-shortcut-tab home-shortcut-tab--review"
              onClick={isDevUser ? onOpenAccount : onStartTodayReview}
            >
              <span className="home-shortcut-tab-icon home-shortcut-tab-icon--character">
                <ShioriCharacter variant="review" size="sm" />
              </span>
              <span className="home-shortcut-tab-text">
                <span className="home-shortcut-tab-label">복습</span>
                <span className="home-shortcut-tab-hint">{reviewHint}</span>
              </span>
            </button>
            <button
              type="button"
              className="home-shortcut-tab home-shortcut-tab--decks"
              onClick={onGoToSharedDecks}
            >
              <span className="home-shortcut-tab-icon">
                <BookshelfIcon />
              </span>
              <span className="home-shortcut-tab-text">
                <span className="home-shortcut-tab-label">덱</span>
                <span className="home-shortcut-tab-hint">{decksHint}</span>
              </span>
            </button>
          </div>

          {/* Phase 133/139/151's photographed desk-prop cutouts (leaf,
              washi tape, paperclip, pen), repositioned for Phase 159: with
              the sticky-note column gone, there is no second cluster left
              to bridge -- each prop now anchors a different edge of the
              single hero cluster instead (leaf pins the title note's
              corner, tape+paperclip weight the book's lower-left corner,
              pen tucks between two shortcut tabs). display:none below
              1024px in globals.css, unchanged -- mobile keeps the cover as
              the sole subject. background-image (not <img src>) inside the
              >=1024px block only, so mobile fetches zero bytes for any of
              the four (see the Phase 139 note this comment used to carry,
              still accurate, just condensed here since the full history is
              already in DESIGN.md). */}
          <div className="home-desk-props" aria-hidden="true">
            <span
              aria-hidden="true"
              className="home-desk-prop home-desk-prop--leaf"
            />
            <span
              aria-hidden="true"
              className="home-desk-prop home-desk-prop--tape"
            />
            <span
              aria-hidden="true"
              className="home-desk-prop home-desk-prop--paperclip"
            />
            <span
              aria-hidden="true"
              className="home-desk-prop home-desk-prop--pen"
            />
          </div>
        </div>

        {/* Phase 159 -- was a page-level footer sitting well below the
            whole .home-stage box. Brief requires this stay close enough to
            read as a small desk label, not a footer outside the scene --
            now sits tight under the cluster with its own small "note"
            treatment (see .home-footnote in globals.css) instead of the
            generic full-width info-strip spacing. */}
        <p className="info-strip info-strip-quiet home-footnote">
          <ShieldIcon className="info-strip-icon" />
          원문 전체는 서버에 저장하지 않아요.
        </p>
      </div>
    </section>
  );
}
