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
const ASSET_BASE_V4 = "/brand/decor/home-v4";
const ASSET_BASE_V9 = "/brand/decor/home-v9";

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
// Phase 195 (target-mockup asset replacement) -- coordinate-only passes
// (177-194) hit diminishing returns, so this phase is driven by newly
// generated material instead: a photographed oak desk plate (replacing
// the old kraft-paper plate on `body:has(.home-v4)`), one rail image
// (`home-v4-shortcut-tab-rail-candidate.png`) replacing the three
// separate shortcut-tab PNGs -- the DOM hit zones stay three buttons for
// three handlers/routes, but the ART is one rail an anchor image drives,
// not three independently-tuned card positions -- and a low-opacity
// emboss mark filling the notebook's previously-blank lower-right cover.
// The two "embossed notebook cover" candidates in home-v4/ are NOT wired
// (see ASSET_MANIFEST.md in that folder): both failed alpha verification
// (opaque checkerboard baked in), so the existing transparent
// `home-v3-notebook-cover.png` stays, with the emboss mark layered on
// top as its own overlay image instead.
// Phase 196 (composition lock) -- Phase 195 wired the right assets but
// still read as a photo background with paper glued on: the desk plate's
// own wood grain/light rays out-competed the foreground, the tab rail was
// still small enough to read as a footnote rather than Home's three main
// actions, the emboss was too faint to keep the cover from looking blank,
// and privacy sat far enough from the note/CTA/notebook pile to read as a
// page footer instead of one more object on the desk. No DOM changes this
// phase -- every one of those is a relationship between existing objects
// (background recede-vs-foreground contrast, rail-to-notebook size ratio,
// emboss opacity, privacy's position relative to the note/CTA column),
// not a missing element, so the fix lives entirely in globals.css: a
// background vignette, a bigger rail, a stronger emboss, and privacy
// repositioned into the note/CTA cluster (see the Phase 196 comments on
// each of those rules).
// Phase 197 (Shiori peek / lighting+privacy correction) -- the vignette
// from 196 still read as stage lighting rather than a lit desk, the
// privacy label sat inside the CTA ticket's own box (its shadow/tail
// painted over the label text), and Shiori was reintroduced as a small
// peek behind the title note's tape (candidate F) instead of the earlier
// failed "mascot sitting on the notebook cover" placement -- see the
// Shiori-peek element and its CSS comment below for how the occlusion is
// built. No DOM change for the lighting/privacy fixes, only globals.css.
// Phase 198 (material grounding) -- removed the privacy sticker entirely:
// it was Phase 194-197's fix target for four phases running (small ->
// footer-like -> repositioned into the cluster -> repositioned again off
// the CTA) and this phase's brief judged the object itself unnecessary on
// Home's first screen rather than worth a fifth placement attempt. The
// save-policy line it carried ("원문 전체는 서버에 저장하지 않아요.") is
// UI copy only -- no storage behavior it was describing has changed, the
// line is just no longer shown on Home. `home-v3-privacy-label.png` is
// left in place (untouched) in case a later phase wants the policy line
// somewhere else on Home; the now-unused `.home-v4-privacy*` CSS is
// pruned in globals.css. Shiori's peek size also grows this phase (see
// .home-v4-shiori-peek) -- same tape-occlusion mechanic, just bigger.
// Phase 199 (material weight / natural contact shadow) -- 196-198's
// incremental notebook-size/color/shadow nudges kept measuring as "close
// enough to the previous screenshot to barely register" against this
// phase's own before/after comparison -- confirmed by screenshot, not
// assumed. This phase jumps to explicit target values instead of another
// nudge (notebook width, cover color filter, Shiori peek size -- all in
// globals.css) and replaces the scene-wide `.home-v4-scene::after` shadow
// pool with per-object contact shadows only (`.home-v4-notebook::after`,
// `.home-v4-tab-rail::after`), since a shadow shaped and positioned
// against the whole scene box rather than any specific object was the
// actual cause of the "shadow reads as a rectangle" failure a bigger
// blur radius alone couldn't fix. No DOM change this phase -- everything
// above is a CSS value or a CSS structural removal, not a missing
// element.
// Phase 200 (superseded) proved that recoloring a pale notebook and
// approximating contact shadows as separate layers still left the scene
// looking composited. Those experimental assets were removed in the Home
// V7 cleanup; the durable version below is the baked plate.
// Phase 213 (final implementation / baked scene plate) -- 195-200's model
// (separate notebook-cover image + separate tab-rail image + CSS-drawn
// contact shadows, composited via z-index/percentage math) kept producing
// shadows that looked disconnected from what cast them and tab colors
// that could bleed at their shared edges, because three independently-
// positioned layers have no way to guarantee they agree on geometry.
// `.home-v4-notebook` is now a single baked plate
// (home-v7-notebook-tabs-shadow-plate.png) with the cover, ribbon, emboss,
// and all three tabs under one light source. The DOM keeps exactly the
// three shortcut buttons as
// plain hit zones over the plate's own tab row (see ASSET_MANIFEST.md in
// home-v7/ for the pixel-measured geometry those percentages come from).
// A later surface-map pass moved contact shadows out of raster assets and
// into `.home-v4-notebook::before/::after` so they can ground only the
// visible bottom/right/tab underside zones without exposing a rectangular
// shadow canvas. Nothing else changed about how live text/click targets work.
// Phase 215 (v9 grounded-scene replacement) -- the v8 plate (baked shadow
// on the v7 cover geometry) still failed the brief's own review: the
// contact shadow either vanished or read as a hard dark bar/line rather
// than a soft table-contact falloff, Shiori (a separate small PNG peeking
// above the note's tape) looked pasted on rather than physically tucked
// into the paper, and the three tabs read as small/UI-like rather than
// large paper tabs resting on the desk with their own shadow. Per
// references/mockups/home-v9-prep/CLAUDE_HANDOFF.md, tuning the v8 plate
// further was explicitly rejected as a "failed derivative pipeline" --
// the fix is a from-scratch foreground plate
// (`home-v9-foreground-grounded-plate.png`) built by difference-matting
// the approved `home-v9-composited-target-mockup.png` against the
// production desk background it was composited over
// (`home-v4-desk-surface-desktop.png`, pixel-identical to the mockup's
// own desk layer), which recovers true alpha (including soft shadow
// falloff, since a shadow is just the desk darkened under real alpha, not
// a flat rectangle) directly from the approved artwork instead of
// re-deriving it from the old v7/v8 raster. Same technique isolates a new
// Shiori crop (`home-v9-shiori-reading-peek.png`, diffed against
// `home-v9-approved-scene-target.png` -- the same composition with only a
// small placeholder mark instead of her -- so the diff is exactly her
// silhouette plus the contact shadow she casts on the tape beneath),
// replacing the old flat `filter: drop-shadow` peek with one that has a
// real baked contact shadow. See the .home-v4-shiori-peek comment below
// for why she stays a separate DOM element (not baked into the notebook
// plate itself, despite the asset manifest's literal wording) and
// ASSET_MANIFEST.md in home-v9/ for the pixel-measured tab geometry the
// three buttons further down are positioned from.
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
          {/* Phase 197 -- candidate F: Shiori peeking up from behind the
              note's own taped edge, not a mascot sitting on the notebook
              cover (that placement failed a prior phase -- see the
              top-of-file history). Rendered BEFORE home-v4-note-img in DOM
              order and forced below it in z-index (see
              .home-v4-shiori-peek), so the same "occluder" trick the
              notebook cover already uses for the tab rail applies here:
              the note's own paper only exists inside `.home-v4-note`'s own
              box, so the portion of her that sits above that box (where
              she pokes out above the tape) can never be covered by
              construction, and the portion that overlaps the box is
              always painted over by the note -- no manual clip-path
              tuning needed.
              Phase 213 -- swapped the generic default-variant
              ShioriCharacter for the confirmed reading pose, rendered as a
              plain <img> instead of through ShioriCharacter -- a Home-only
              cropped asset that isn't in Shiori.tsx's SHIORI_ASSET_MAP, so
              every other ShioriCharacter/ShioriMark/ShioriStamp call site
              elsewhere in the app is untouched.
              Phase 215 (v9) -- swapped the crop again
              (home-v9-shiori-reading-peek.png, diff-matted from the
              approved mockup -- see the top-of-file Phase 215 comment) and
              dropped the CSS `filter: drop-shadow` this element used to
              carry: that filter was approximating a contact shadow with a
              generic floating drop-shadow, which is exactly the "pasted
              on" look the v9 brief calls out. The new crop has a real
              contact shadow (her + the flap she sits on, shading onto the
              tape beneath) baked into its own alpha, so no CSS shadow is
              layered on top of it at all now.
              This still stays a separate element positioned against
              `.home-v4-note` (not baked into the notebook plate, even
              though the v9 asset manifest's literal wording lists Shiori
              as notebook-plate content): `.home-v4-note` and
              `.home-v4-notebook` are independently-positioned siblings
              that only visually overlap at the >=1024px tier (see
              `.home-v4-scene`'s absolute-position rules) -- below that,
              they stack in normal flow with no overlap at all, so baking
              her into the notebook plate would leave her sitting on the
              notebook's own top-left corner at mobile (wherever that
              happens to render, below the note and CTA) instead of tucked
              into the note's own tape as the approved mockup shows. Kept
              on the note (which she visually integrates with at every
              breakpoint, exactly as approved) instead. */}
          <img
            className="home-v4-shiori-peek"
            aria-hidden="true"
            src={`${ASSET_BASE_V9}/home-v9-shiori-reading-peek.png`}
            alt=""
            draggable={false}
          />
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
            src={`${ASSET_BASE_V4}/home-v4-cta-ticket.png`}
            alt=""
            draggable={false}
          />
          <span className="home-v4-cta-content">
            <SparkleIcon className="button-icon" />
            <span>원문 읽기 시작</span>
          </span>
        </button>

        {/* Phase 215 (v9 grounded-scene replacement) -- swapped the v8
            plate for `home-v9-foreground-grounded-plate.png`, a from-
            scratch difference-matted extraction from the approved v9
            mockup (see the top-of-file Phase 215 comment): notebook cover
            + bookmark ribbon + emboss + all three tabs + tape + baked
            contact shadow, with no CSS shadow layered behind or on top of
            it anywhere (no `.home-v4-notebook::before/::after`, no
            `filter: drop-shadow`, no gradient). The plate is a complete,
            standalone book cover -- the small area the title note and CTA
            sit on top of at the >=1024px tier is filled with real sampled
            cover color rather than left as a transparent notch, so the
            plate still reads as a whole book (not a book with a bite
            taken out of it) at <1024px, where the note/CTA stack above it
            in normal flow instead of overlapping it. The three buttons
            below stay plain DOM hit zones (icon/label/hint live text)
            positioned from this plate's own pixel-measured tab geometry --
            see ASSET_MANIFEST.md in home-v9/ -- not the old v8
            percentages. */}
        <div className="home-v4-notebook">
          <img
            className="home-v4-notebook-img"
            aria-hidden="true"
            src={`${ASSET_BASE_V9}/home-v9-foreground-grounded-plate.png`}
            alt=""
            draggable={false}
          />
          <button
            type="button"
            className="home-v4-shortcut home-v4-shortcut--vocab"
            onClick={onGoToVocab}
          >
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
    </section>
  );
}
