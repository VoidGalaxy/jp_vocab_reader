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
  // (desktop only, see .home-v3-shortcut-hint) -- no separate "최근 담은
  // 단어" section on Home. Same /vocab-items?sort=created_desc read the 기록
  // 탭 already makes, no new API call.
  recentWords: VocabItem[];
};

const ASSET_BASE = "/brand/decor/home-v3";

// Phase 177-185 -- structure/composition is settled (big notebook cluster,
// note/CTA/shortcuts attached to it); this pass is background/material
// fidelity, not layout.
// Phase 186 (background plate integration) -- Phase 185's DOM prop cutouts
// (leaf/washi-tape/paperclip/pen, borrowed from ../phase131/) are gone --
// the new photographed background plate (home-v3-desk-surface-{desktop,
// mobile}.png, applied via body:has(.home-v3) in globals.css) already
// bakes the same plant/washi-tape/paperclip/pen into its own edges, so
// keeping the DOM copies would have doubled them up. Nothing in this file
// changed beyond removing that dead code -- the plate is a pure background-
// image swap with no new DOM.
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
    <section className="tab-panel home-dashboard home-v3" aria-live="polite">
      <div className="home-v3-scene">
        {/* .home-v3-cluster is the notebook-as-compound-object: every child
            below is positioned as a % of THIS box (see globals.css), not
            the outer scene, so the note/CTA/shortcuts read as
            attachments of the notebook rather than independently-placed
            stickers. DOM order is mobile's *reading* order (vertical
            overlap flow) -- note/CTA before the notebook itself, per the
            brief's "제목 메모를 먼저 읽히게" -- while desktop absolutely
            positions every child by %, so this order has no effect on
            desktop placement (z-index below keeps desktop stacking correct
            regardless of source order). */}
        <div className="home-v3-cluster">
        <div className="home-v3-note">
          <img
            className="home-v3-note-img"
            src={`${ASSET_BASE}/home-v3-title-note.png`}
            alt=""
            draggable={false}
          />
          <div className="home-v3-note-content">
            <h2 className="home-v3-title">
              오늘도 한 문장,
              <br />한 단어.
            </h2>
            <p className="home-v3-subtitle">
              모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
            </p>
            <button
              type="button"
              className="home-v3-sample"
              onClick={onTryWithSample}
            >
              샘플로 체험
            </button>
          </div>
        </div>

        <button type="button" className="home-v3-cta" onClick={onStartReading}>
          <img
            className="home-v3-cta-img"
            src={`${ASSET_BASE}/home-v3-cta-stamp.png`}
            alt=""
            draggable={false}
          />
          <span className="home-v3-cta-content">
            <SparkleIcon className="button-icon" />
            <span>원문 읽기 시작</span>
          </span>
        </button>

        <div className="home-v3-notebook" aria-hidden="true">
          <img
            className="home-v3-notebook-img"
            src={`${ASSET_BASE}/home-v3-notebook-cover.png`}
            alt=""
            draggable={false}
          />
        </div>

        <div className="home-v3-shortcuts" role="group" aria-label="바로가기">
          <button
            type="button"
            className="home-v3-shortcut home-v3-shortcut--vocab"
            onClick={onGoToVocab}
          >
            <img
              className="home-v3-shortcut-img"
              src={`${ASSET_BASE}/home-v3-shortcut-tab-yellow.png`}
              alt=""
              draggable={false}
            />
            <span className="home-v3-shortcut-content">
              <span className="home-v3-shortcut-icon">
                <CardFileIcon />
              </span>
              <span className="home-v3-shortcut-text">
                <span className="home-v3-shortcut-label">단어장</span>
                <span className="home-v3-shortcut-hint">{vocabHint}</span>
              </span>
            </span>
          </button>
          <button
            type="button"
            className="home-v3-shortcut home-v3-shortcut--review"
            onClick={isDevUser ? onOpenAccount : onStartTodayReview}
          >
            <img
              className="home-v3-shortcut-img"
              src={`${ASSET_BASE}/home-v3-shortcut-tab-coral.png`}
              alt=""
              draggable={false}
            />
            <span className="home-v3-shortcut-content">
              <span className="home-v3-shortcut-icon">
                <CardsIcon />
              </span>
              <span className="home-v3-shortcut-text">
                <span className="home-v3-shortcut-label">복습</span>
                <span className="home-v3-shortcut-hint">{reviewHint}</span>
              </span>
            </span>
          </button>
          <button
            type="button"
            className="home-v3-shortcut home-v3-shortcut--decks"
            onClick={onGoToSharedDecks}
          >
            <img
              className="home-v3-shortcut-img"
              src={`${ASSET_BASE}/home-v3-shortcut-tab-blue.png`}
              alt=""
              draggable={false}
            />
            <span className="home-v3-shortcut-content">
              <span className="home-v3-shortcut-icon">
                <BookshelfIcon />
              </span>
              <span className="home-v3-shortcut-text">
                <span className="home-v3-shortcut-label">덱</span>
                <span className="home-v3-shortcut-hint">{decksHint}</span>
              </span>
            </span>
          </button>
        </div>

        {/* home-v3-privacy-label.png already bakes in its own shield badge
            (see ASSET_MANIFEST.md), so unlike the old .home-scene-v2-privacy
            this carries no separate DOM ShieldIcon -- one shield, not two. */}
        <p className="home-v3-privacy">
          <img
            className="home-v3-privacy-img"
            src={`${ASSET_BASE}/home-v3-privacy-label.png`}
            alt=""
            draggable={false}
          />
          <span className="home-v3-privacy-text">
            원문 전체는 서버에 저장하지 않아요.
          </span>
        </p>
        </div>
      </div>
    </section>
  );
}
