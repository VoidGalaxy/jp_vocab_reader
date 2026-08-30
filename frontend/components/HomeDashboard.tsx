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
  // (desktop only, see .home-v4-shortcut-hint) -- no separate "최근 담은
  // 단어" section on Home. Same /vocab-items?sort=created_desc read the 기록
  // 탭 already makes, no new API call.
  recentWords: VocabItem[];
};

const ASSET_BASE = "/brand/decor/home-v3";

// Phase 192 (skeleton replacement) -- reskin failed; phases 177-190 kept
// patching the same flat `scene > [note, cta, notebook, shortcuts,
// privacy]` sibling structure, which is exactly why the shortcut tabs'
// "tucked into the notebook" depth cue kept breaking across breakpoints:
// the tabs were positioned as a % of the SCENE/cluster box, but needed to
// line up with the NOTEBOOK's own edge, and those two boxes scale
// differently as the viewport changes (cluster height comes from an
// svh-based clamp, notebook height from its own width via aspect-ratio).
// This rebuilds the DOM around one rule: anything that has to line up
// with the notebook lives INSIDE it. `.home-v4-notebook` is now a true
// composite -- its cover image and the shortcut tab group are siblings
// inside the SAME box, so the tabs' overlap is a % of the notebook's own
// dimensions, not the cluster's. That makes the overlap amount constant
// across every viewport width without any per-breakpoint tuning, and it's
// also what makes the "hidden sliver" genuinely safe: the cover image
// only visually covers the part of a tab that falls inside the notebook's
// own box, so a tab's icon/label -- which live in the part deliberately
// positioned OUTSIDE that box -- can never be covered by construction,
// not by tuning a number to avoid it.
// The old `home-v3-*` family is retired for Home (other tabs/asset
// manifests are untouched) in favor of `home-v4-*`; the previous
// `.home-v3-scene` + `.home-v3-cluster` double wrapper is also collapsed
// into one `.home-v4-scene` root, since the two boxes had drifted into
// doing the same job (a single positioning root for the note/CTA/
// notebook/privacy layer).
// Phase 194 (physical contact rebuild) -- the notebook-composite skeleton
// from Phase 192 was structurally right (tabs nested inside the notebook,
// positioned against its own box) but the actual camera distance/contact
// depth still read as a photo with PNGs pasted on: the notebook filled
// too much of the frame (cropping the desk instead of sitting on it), and
// note/CTA only barely grazed the notebook's edge instead of visibly
// resting on it. This pass only re-tunes scale/overlap and renames the
// tab group (`.home-v4-shortcuts` -> `.home-v4-tab-rail`, see below) to
// name what it actually is -- no new DOM nesting was needed since
// Phase 192's notebook-relative structure already solved the coordinate-
// mismatch bug this exists to avoid re-introducing.
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
    <section className="tab-panel home-dashboard home-v4" aria-live="polite">
      <div className="home-v4-scene">
        <div className="home-v4-note">
          <img
            className="home-v4-note-img"
            src={`${ASSET_BASE}/home-v3-title-note.png`}
            alt=""
            draggable={false}
          />
          <div className="home-v4-note-content">
            <h2 className="home-v4-title">
              오늘도 한 문장,
              <br />한 단어.
            </h2>
            <p className="home-v4-subtitle">
              모르는 단어를 눌러두면, 읽으면서 단어장이 자연스럽게 쌓여요.
            </p>
            <button
              type="button"
              className="home-v4-sample"
              onClick={onTryWithSample}
            >
              샘플로 체험
            </button>
          </div>
        </div>

        <button type="button" className="home-v4-cta" onClick={onStartReading}>
          <img
            className="home-v4-cta-img"
            src={`${ASSET_BASE}/home-v3-cta-stamp.png`}
            alt=""
            draggable={false}
          />
          <span className="home-v4-cta-content">
            <SparkleIcon className="button-icon" />
            <span>원문 읽기 시작</span>
          </span>
        </button>

        {/* .home-v4-notebook is the notebook COMPOSITE: cover image +
            tab rail live in the same box on purpose, so the tabs'
            overlap-with-the-cover math is a % of THIS box, not the outer
            scene. `.home-v4-tab-rail` (was `.home-v4-shortcuts`) names
            what it actually is: the strip of the notebook's own bottom
            edge the tabs ride along and poke out from, not a generic
            "group of shortcut buttons" floating near the notebook. */}
        <div className="home-v4-notebook">
          <img
            className="home-v4-notebook-img"
            aria-hidden="true"
            src={`${ASSET_BASE}/home-v3-notebook-cover.png`}
            alt=""
            draggable={false}
          />
          <div className="home-v4-tab-rail" role="group" aria-label="바로가기">
            <button
              type="button"
              className="home-v4-shortcut home-v4-shortcut--vocab"
              onClick={onGoToVocab}
            >
              <img
                className="home-v4-shortcut-img"
                src={`${ASSET_BASE}/home-v3-shortcut-tab-yellow.png`}
                alt=""
                draggable={false}
              />
              <span className="home-v4-shortcut-content">
                <span className="home-v4-shortcut-icon">
                  <CardFileIcon />
                </span>
                <span className="home-v4-shortcut-text">
                  <span className="home-v4-shortcut-label">단어장</span>
                  <span className="home-v4-shortcut-hint">{vocabHint}</span>
                </span>
              </span>
            </button>
            <button
              type="button"
              className="home-v4-shortcut home-v4-shortcut--review"
              onClick={isDevUser ? onOpenAccount : onStartTodayReview}
            >
              <img
                className="home-v4-shortcut-img"
                src={`${ASSET_BASE}/home-v3-shortcut-tab-coral.png`}
                alt=""
                draggable={false}
              />
              <span className="home-v4-shortcut-content">
                <span className="home-v4-shortcut-icon">
                  <CardsIcon />
                </span>
                <span className="home-v4-shortcut-text">
                  <span className="home-v4-shortcut-label">복습</span>
                  <span className="home-v4-shortcut-hint">{reviewHint}</span>
                </span>
              </span>
            </button>
            <button
              type="button"
              className="home-v4-shortcut home-v4-shortcut--decks"
              onClick={onGoToSharedDecks}
            >
              <img
                className="home-v4-shortcut-img"
                src={`${ASSET_BASE}/home-v3-shortcut-tab-blue.png`}
                alt=""
                draggable={false}
              />
              <span className="home-v4-shortcut-content">
                <span className="home-v4-shortcut-icon">
                  <BookshelfIcon />
                </span>
                <span className="home-v4-shortcut-text">
                  <span className="home-v4-shortcut-label">덱</span>
                  <span className="home-v4-shortcut-hint">{decksHint}</span>
                </span>
              </span>
            </button>
          </div>
        </div>

        {/* home-v3-privacy-label.png already bakes in its own shield badge
            (see ASSET_MANIFEST.md), so this carries no separate DOM
            ShieldIcon -- one shield, not two. */}
        <p className="home-v4-privacy">
          <img
            className="home-v4-privacy-img"
            src={`${ASSET_BASE}/home-v3-privacy-label.png`}
            alt=""
            draggable={false}
          />
          <span className="home-v4-privacy-text">
            원문 전체는 서버에 저장하지 않아요.
          </span>
        </p>
      </div>
    </section>
  );
}
