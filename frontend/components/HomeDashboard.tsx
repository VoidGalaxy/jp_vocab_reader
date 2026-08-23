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

// Phase 118 (Hard Mockup Reconstruction) -- Phase 54-117's Home kept the
// right *ingredients* (notebook cover, three shortcuts, Shiori corner) but
// wrapped them in UI-panel language the mockup never has: three bordered,
// shadowed, padded cards under the cover read as an admin tile row, not
// "stickers on a desk." This pass throws out the card chrome entirely.
// Mobile: .home-stickers below is bare icon+label pairs sitting directly on
// the page background -- no border, no fill, no shadow, matching
// docs/design/mockups/casual-sticker-reader-mobile.png's Home board exactly
// (icon, one line of text, nothing else). Desktop-only (see globals.css'
// >=1024px block) they become small rotated sticky notes beside the cover,
// matching the desktop mockup's "HOME DESK" panel -- but the *mobile*
// default is intentionally chrome-less. The cover itself is unchanged in
// spirit (title/CTA printed on it, Shiori peeking from the corner) but
// grows taller and drops the inner "page-edge lines" busywork in favor of
// a plainer, larger presence -- it has to fill the screen the way the
// mockup's phone-height notebook does, not share it evenly with the row
// below.
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
      <div className="home-stage">
        {/* Phase 151 -- Home Hero Scene Scale Correction. Phase 145 stacked
            .home-cover-heading (title/CTA) directly above .home-cover-object
            (the book, capped at a small 420px max-width) as two separate
            rows -- a real screenshot at 1280 showed the book sitting alone,
            small, with a huge gap of bare wood between it and the shortcut
            column, and the heading reading as its own block rather than
            attached to the book at all. This restructures .home-cover into
            one physically overlapping cluster instead: the book grows much
            larger (main hero object, not a small accent), and
            .home-cover-heading becomes a paper note pinned across its own
            top edge (negative margin-bottom pulls it down onto the book --
            see globals.css), the same "note glued to a physical object"
            language .home-cover-sticky already used for one small tag. The
            old standalone .home-cover-sticky tag ("오늘도 책장을 열어요")
            is removed rather than kept alongside the new heading note --
            both were doing the same job (a note pinned to the book's top
            edge) in the same spot, and keeping both would have stacked two
            competing notes on top of each other. */}
        <div className="home-cover">
          <div className="home-cover-heading">
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
        </div>

        <div className="home-stickers" role="group" aria-label="바로가기">
          <button
            type="button"
            className="home-sticker home-sticker--vocab"
            onClick={onGoToVocab}
          >
            <span className="home-sticker-icon">
              <CardFileIcon />
            </span>
            <span className="home-sticker-text">
              <span className="home-sticker-label">단어장</span>
              <span className="home-sticker-hint">{vocabHint}</span>
            </span>
          </button>
          <button
            type="button"
            className="home-sticker home-sticker--review"
            onClick={isDevUser ? onOpenAccount : onStartTodayReview}
          >
            <span className="home-sticker-icon home-sticker-icon--character">
              <ShioriCharacter variant="review" size="md" />
            </span>
            <span className="home-sticker-text">
              <span className="home-sticker-label">복습</span>
              <span className="home-sticker-hint">{reviewHint}</span>
            </span>
          </button>
          <button
            type="button"
            className="home-sticker home-sticker--decks"
            onClick={onGoToSharedDecks}
          >
            <span className="home-sticker-icon">
              <BookshelfIcon />
            </span>
            <span className="home-sticker-text">
              <span className="home-sticker-label">덱</span>
              <span className="home-sticker-hint">{decksHint}</span>
            </span>
          </button>
        </div>

        {/* Phase 133 -- the pure-CSS plant/stationery/pen/cup shapes are
            replaced with Phase 131's photographed desk-prop cutouts (real
            leaf sprig, washi tape roll, brass paperclip, pen). No photo
            exists for the old CSS cup, so it's dropped rather than left as
            the one obviously-fake shape in an otherwise-real scene.
            display:none below 1024px in globals.css -- mobile keeps the
            cover as the sole subject. A child of .home-stage (not a
            page-level sibling) so its position:absolute; inset:0 sizes
            against the cover+stickers box it's meant to scatter around, not
            the whole viewport. Each prop is decorative-only: aria-hidden and
            pointer-events:none inherited from .home-desk-props so none of
            them can ever intercept a click.
            Phase 139 -- these were originally four <img src> elements (see
            git history), which fetched all four WebP files unconditionally
            on every page load regardless of viewport, since an ancestor's
            CSS display:none does not stop the browser from requesting an
            <img>'s own src (confirmed via network log: the mobile Home load
            was still pulling ~92KB of desk-prop images that render nowhere
            below 1024px). Home's own sticky notes (.home-sticker--vocab/
            --review/--decks) already avoided this exact problem by using
            CSS background-image inside the >=1024px media query instead of
            an <img> tag -- a media query the browser correctly skips
            fetching behind when it doesn't match. Converted to plain <span>
            + the same background-image pattern here for that reason; each
            prop's actual photo now lives in globals.css'
            .home-desk-prop--leaf/--tape/--paperclip/--pen rules, still
            inside the existing >=1024px block, so mobile now fetches zero
            bytes for any of the four instead of ~92KB it never rendered. */}
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

      <p className="info-strip info-strip-quiet home-footnote">
        <ShieldIcon className="info-strip-icon" />
        원문 전체는 서버에 저장하지 않아요.
      </p>
    </section>
  );
}
