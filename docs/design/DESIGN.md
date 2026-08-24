# DESIGN.md — Casual Sticker Reader

Durable visual direction for 책갈피 (jp_vocab_reader), starting Phase 54. This
replaces the earlier "study desk" direction as the visual authority; treat the
old boxed/card-tile look as evidence of what to avoid, not something to keep
polishing. Source brief: `docs/design/casual-sticker-reader-redesign-brief.md`.
Reference boards: `docs/design/mockups/casual-sticker-reader-mobile.png`,
`docs/design/mockups/casual-sticker-reader-desktop.png` (directional, not
pixel specs).

> **Phase 162 V2 reset:** for new visual redesign work, the current authority is
> `docs/design/V2_SCENE_REDESIGN_BIBLE.md`. This file remains the durable phase
> history and decision log, but older sections that recommend reusing
> `panel-card`, `hero-card`, side widgets, filter panels, or card grids should
> be treated as historical context unless the V2 bible explicitly keeps them.
> The new rule is scene first, then functionality reattached -- not decorating
> the existing app skeleton.

## Principles

- **Casual personal reading notebook, not an admin dashboard.** No dense grids
  of bordered management tiles, no settings-panel energy on primary screens.
- **Casual does not mean toy-like.** Keep copy and information practical and
  readable; playful chrome (tilt, sticky notes, stickers) sits around real
  content, it doesn't replace it.
- **Minimize numbers and management framing on primary screens** (Home
  especially). Prefer a short qualitative line ("잊기 전에 다시 보기") over a
  raw count chip. Exact counts still belong on the screens whose job is
  counting (단어장 필터, 복습 세션, 통계) — this rule is about what greets the
  user first, not about hiding real data everywhere.
- **Desktop = wide desk with an open notebook.** Manuscript/notebook surface,
  sticker notes, a word-inspector sheet, deck booklets.
- **Mobile = focus reader + sticker journal.** Read, tap a word, lift it into
  a sticker, save/review it.

## Shiori usage rules

- Use only the existing PNGs in `frontend/public/brand/shiori/*.png`
  (`ShioriCharacter`/`ShioriMark`/`ShioriStamp`/`ShioriGuideCard` in
  `components/Shiori.tsx`). Never generate, redraw, or otherwise vary the
  character art.
- Shiori is a small rounded bookmark spirit — never a human, anime-girl,
  portrait, or new character.
- Correct roles: helper sticker, tab marker, corner guide, idle hint, save
  stamp, tiny celebration mark.
- Incorrect roles: a large standalone hero illustration competing with the
  primary action for attention. Keep her at a corner/accent size (`sm`–`lg`)
  on primary screens; `hero`/`xl` sizes are for dedicated empty/celebration
  states only, not routine chrome.

## Per-screen direction

- **Home** — one notebook-cover hero (`.home-notebook-cover`): dark cover,
  cream title/CTA printed on the cover itself, a pinned sticky note, Shiori
  peeking from the corner. One primary action ("원문 읽기 시작"). Below it, a
  row of small sticker shortcuts (`.home-sticker-chip`) for 단어장/복습/덱 —
  qualitative subtitles, not counts. No separate "최근 담은 단어" dashboard
  section on Home; that detail lives on the 단어장 tab.
- **App Shell** (Phase 54 structure; Phase 60 finish) — rail/bottom-nav
  structure, tab routing, and account/feedback slots were left unstyled in
  Phase 54 so only Home's content area followed the new direction at the
  time. Phase 60 finished the shell itself: the desktop library rail's brand
  mark is taped down (`.library-rail-brand-tape`), and the active nav link
  reads as a stuck-on bookmark tab (asymmetric corner, slight tilt, a small
  pin dot) instead of a flat filled pill — same strong solid-primary fill,
  so the active state is still unambiguous. The mobile bottom nav's active
  tab picks up a matching pin dot and a rounded-top (not full-pill) shape
  without changing its touch-target size. The topbar's feedback button is
  now a small paper tag (`.app-topbar-feedback-button`) instead of a plain
  ghost button. Tab routing, `activeTab` semantics, and the account
  menu/login flow are untouched.

  **Superseded by Phase 113** (see the "Phase 113" entry in Status below):
  the `.library-rail` sidebar and `.app-bottom-nav` fixed bar described
  above were deleted, not restyled further — replaced by one `.app-toolbar`
  nav surface (full text-tab row at >=1024px, hamburger + slide-in
  `.app-nav-drawer` below that). The material details above (tape, pin
  dots, bookmark-tab active state, paper-tag feedback button) carried
  forward onto the new surface; only the structural rail/bottom-nav/topbar
  split they were describing is gone.
- **Reading + Inspector** (Phase 55) — notebook-page reader (`.reader-paper`,
  `.reader-start-card`) with washi-tape corner accents, a pin-dotted
  sticky-note word inspector (`.bookmark-inspector`, tilted on desktop,
  straight bottom sheet on mobile), a thinner progress bar with a
  bookmark-charm bead, and a dashed-strip save tray instead of a bordered
  admin box. Candidate/word list redesigned in Phase 56 (see below). Phase 93
  restored "원문이 주인공" hierarchy inside `.reader-paper`: the old
  always-on title+hint row, progress+bookmark-actions row, and legend row
  measured a combined 274px on mobile 375 before the first line of Japanese
  text (46% of the reader page was text). Those three rows collapsed into
  one slim `.reader-toolbar` line (title + thin progress bar + the existing
  "옵션" toggle); hint/token-count/legend/bookmark-actions moved into the
  same options popover the focus/JLPT toggles already used (no new
  disclosure mechanism, `isOptionsOpen` is unchanged). Result: first
  Japanese character now at 170px/73.7% text ratio on 375 (320/390
  confirmed at the same numbers). On desktop, `ReaderSaveDock`'s "빠르게
  전체 저장" toggle and the post-analyze "어휘 노트 보기" link no longer
  stretch to the full 944px reader-paper width (a CSS grid
  justify-items:stretch default and an unopposed flex-grow, respectively) --
  both are now content-width and left-aligned, `>=1024px` only, so mobile's
  existing app-wide `button { width: 100% }` touch-target rule is
  untouched. `TokenDetailSheet.tsx`, the candidate tray's Phase 89/91
  horizontal-strip structure, and all save/select/status/API/SRS wiring are
  unchanged. A same-Phase follow-up addressed two risks that pass left
  behind: the options popover (everything the toolbar didn't keep) had
  grown to ~900px tall as one flat list, and the color legend was no
  longer discoverable without opening it. The legend came back as a bare
  compact strip (`.reader-legend-strip` -- dot + 2-3 char label, no pill
  background, unlike the old `.reader-legend`/`.legend-item` it replaces)
  always visible between the toolbar and the text, adding only ~25px
  (measured: first character now at 195px/68.5% text ratio on 375, still
  far below the pre-Phase-93 274px/46%). The popover itself split into 3
  labeled groups -- 표시 (focus/JLPT toggles), 이동 (token count + bookmark
  actions), 원문 관리 (collapse/reset) -- via a shared
  `.reader-mode-toggles-section` class reusing the same dashed-divider
  language the manage row already had, cutting measured popover height to
  437px on mobile 375. The `.reading-summary-cta-button`/
  `.reading-summary-cta-ready`/`.save-tray-quick-save-toggle` desktop
  overrides were also re-scoped under their `.reading-action-dock`/
  `.save-tray-quick-save` ancestors so they win on specificity rather than
  depending on source order (previously flagged as fragile). Phase 94 fixed
  the last "reader disappears" gap: tapping a word on mobile opened
  `.bookmark-inspector` at `max-height: 85vh` over a `rgba(37,43,30,0.4)`
  scrim, leaving only ~15% of the viewport legible -- reading stopped
  rather than paused. Below 640px only (pinned `>=1024px` and the
  641-1023px docked-panel tier, already scrim-free, are untouched), the
  sheet is now capped at `max-height: 42vh` and `.token-sheet-overlay`'s
  background is transparent (matching what the docked tier already used),
  so roughly 58% of the viewport -- the reader text above the sheet --
  stays visible and legible while it's open (measured: 375 -> sheet 42% of
  viewport, 244px of reader text still visible above it). Word/reading,
  meaning, and the 4 status buttons sit within that fold on typical
  content; the example sentence, base-form/part-of-speech/JLPT tags,
  prev/next/first-occurrence nav, and meaning-edit/report controls sit
  below it, reachable through the scroll the card already had
  (`overflow-y: auto`, unchanged) rather than being removed -- a new
  `.token-sheet-fold-divider` ("더 보기") marks where the fold falls,
  CSS-hidden above 640px since pinned/docked have no such cutoff. No new
  React state: `TokenDetailContent` renders identically for all three
  presentations, and the divider is a static, non-interactive marker, not
  a toggle. Phase 95 refined the action hierarchy inside that same compact
  sheet after comparing it to the mockup's "tap a word, lift it into the
  notebook" flow: the save-basket action moved directly under the meaning,
  while the 4-way status classification grid moved below the fold with the
  rest of the detail tools. Classification is still available and unchanged;
  it simply stops being the first decision the reader sees when they only
  meant to peek at a meaning and save the word. Save/status-change,
  `/analyze`, candidate tray, and localStorage/SRS wiring are unchanged.
  Phase 97 removed a duplicate status-bucket save mechanism from
  `ReaderSaveDock`: a "빠르게 전체 저장" toggle that expanded into 5
  new/unknown/uncertain/unclassified/known count pills and 3 immediate-save
  buttons (모르는 단어 저장/모르는+헷갈리는 단어 저장/미분류까지 저장) --
  functionally a second copy of `ReadingVocabPanel`'s quick-select row
  (전체 담기/바구니 비우기/모르는 단어 담기/모르는+헷갈리는 단어 담기/
  미분류까지 담기), except this one saved immediately while the tray's only
  changed the selection, waiting on the dock's own "담은 단어 저장" button.
  Two visibly different flows for the same status buckets. The tray's
  quick-select is now the only place to act on a whole bucket at once; the
  dock only ever saves the current selection (`onSaveSelected`, unchanged --
  same pipeline `saveSelectedReadingTokens`/`persistReadingSaveTargets` in
  `page.tsx` already used). The dock's other immediate-save path
  (`saveReadingTokensBatch`, wired through a now-removed `onSaveBatch` prop)
  and its dead CSS (`.save-tray-quick-save*`, `.save-tray-stat-*`,
  `.reading-summary-actions`/`.reading-summary-save-button`) were deleted
  outright rather than left unreachable. `coverageUtils.ts`'s
  `resolveReadingSaveTargets` helper (that path's target-resolution
  function) is now unused but was left in place -- a shared-utils file
  outside this phase's stated scope, and an unused export doesn't fail the
  build. Selection state, per-word "저장 바구니에 담기", "바로 복습", and
  "어휘 노트 보기" are all unchanged; `ReadingVocabPanel.tsx` needed no
  edits at all.
- **Reading candidate word list** (Phase 56) — `ReadingVocabPanel`'s
  full-width row list is now a flex-wrap sticker tray
  (`.reading-vocab-tray`/`.reading-vocab-sticker*`): each word is a small
  content-sized note with an alternating tilt, a round pin toggle (was a
  square checkbox) that gets a stamped ✓ seal when selected instead of an
  inset accent bar, and a muted check-circle placeholder (not a blank
  spacer) on already-known words so "why can't I add this" stays visible.
  Search/filter/quick-select are now underline text-tabs, not bordered pill
  buttons, to read as labels on the tray rather than a toolbar. Phase 89
  tightened the mobile version only: under `<=640px`, filter chips and
  quick-select buttons stay as one-line horizontal strips instead of
  stacking into a 6-7-line control block before the word stickers appear.
  Labels, handlers, and desktop layout stay unchanged; the container chain
  keeps `min-width: 0` so these strips do not create page-level horizontal
  overflow. Phase 91 checked whether those strips read as scrollable on
  their own: the filter row's trailing label usually gets cut off mid-word
  at 320-390px, but the quick-select row's boundary lands on a word edge
  often enough to look like a complete four-item row. Both strips now carry
  a quiet `mask-image` fade on their right edge (desktop-inert, since it
  only applies inside the same `<=640px` block) so "there's more to
  scroll" reads the same regardless of where a label happens to break.
- **Vocab** (Phase 57) — hero/filter toolbar match the reader's underline
  text-tabs and washi-tape corner (`.vocab-hero-tape`); the word-list row's
  old left-edge status stripe is gone (the bookmark-flag status select
  already shows it) and rows use the same asymmetric "index card" radius as
  the candidate tray; the expanded row's saved-example block is a taped
  note, not a colored-border callout. Deck management/share/custom-term
  panels (already de-boxed onto one shared surface pre-Phase-57) now carry
  a pinned-note tape tab and a small torn "위험 구역" warning tag instead of
  plain caption text. List stays a vertical, non-tilted list (not a
  flex-wrap tray like the reading candidate list) -- an Operate screen with
  20-50 interactive rows needs to stay scannable, and per-row decoration is
  deliberately minimal for the same reason. Phase 87 kept that scannable
  list rule but made the desktop notebook spread feel more complete:
  no-deck/empty states now sit on ruled paper with a pinned Shiori guide
  (`.vocab-desk-empty`, `.vocab-page-guide`), the list drawer picked up a
  subtle `card-stack-surface`, the desktop status filters became page-edge
  tabs scoped to `.vocab-notebook-index`, and the right detail page's idle
  copy became contextual instead of another nested empty box.
- **Study** (Phase 58) — hero card gets the washi-tape corner and the
  deck/mode selects go underline (matching Reading/Vocab). The 4-way rating
  grid is stamp-shaped (asymmetric per-corner radius, alternating tilt,
  permanent inner ring) instead of 4 plain colored buttons -- colors, icons,
  and labels are unchanged, only the chrome reads as a stamp now. Revealing
  the answer pops the whole answer block in as one unit
  (`.study-answer-reveal`, `app-pop`) instead of a bare fragment appearing.
  The saved-example callout is a taped note, not a colored-border callout.
  The completion card's stat row is a perforated "receipt" line with a
  small colored stamp-dot per count instead of a bar-chart-style top
  border. The quick-start tiles and stats-panel disclosure wrapper were
  already well de-boxed pre-Phase-58 and were left as-is; `StatsPanel`'s own
  internal number grid was still a 4-column grid of bordered mini-tiles at
  the time and was addressed later, in Phase 60 (see below).
- **Shared Deck** (Phase 59) — the deck grid reads as a shelf of recommended
  notes/sticker packs (the existing `BrandDeckCover` book-cover treatment was
  already strong and is reused as-is); the hero and card grid gained washi-tape
  and pin accents consistent with the rest of the app. The open deck panel
  (`.shared-deck-detail`) was split off from the card styling into its own
  "opened notebook" look — ruled-paper background, asymmetric corner radius,
  taped top edge — instead of sharing the closed-book spine treatment with the
  grid cards. Unpublished/JLPT-level badges got a slight sticker-style tilt.
  Owner/subscriber/newcomer button conditions, published/unpublished/
  imported/subscribed logic, and the subscribed-mode word-list filter (which
  already reuses Phase 57's Vocab-tab underline-tab styling) were left
  untouched. Phase 88 densified the desktop shelf scene without touching JSX:
  shelf compartments gained a faint plank texture, a CSS bookend prop, and
  paper/card-catalog labels; sparse shelves cap deck cards at a book-like
  width (`minmax(280px, 340px)`) instead of stretching one or two decks across
  the whole compartment. The opened detail panel's shelf ridge is slightly
  stronger, while mobile remains visually unchanged.
- **Stats/Info + StatsPanel + Feedback** (Phase 60) — the 통계 tab's hero
  pairs its title with a small `ShioriStamp` ("학습 기록" postmark), matching
  the "오늘의 스탬프 로그" framing; the 저장 정책 card dropped the app-wide
  `.note-card` colored-border-left accent (an admin-callout pattern) for a
  plain `.panel-card` plus one corner fold, and the deck/word log rows
  picked up the same asymmetric "index card" radius used elsewhere. Deeper
  in `StatsPanel` (surfaced inside Study's "학습 현황 자세히 보기"
  disclosure), the old 4-column grid of 7 bordered `.stat-card` mini-tiles
  is now a wrapped row of quiet label/value pills, and the per-deck
  `.deck-stat-row` boxes became a plain ledger list with a dashed divider
  between rows instead of each deck getting its own bordered/soft-bg card.
  `GlobalFeedbackModal` now reads as a small taped-down memo
  (`.feedback-modal-tape`, asymmetric corner) instead of a centered dialog
  box; its category `<select>` is an underline field (same recipe as the
  reading/vocab/study tabs' own pickers) and its textarea sits on warm note
  paper instead of the app-wide plain sheet background. Submit/cancel
  enablement, validation, and payload fields are unchanged.
- **Analyze + Stats + Feedback deep scene (Phase 71)** — the same `>=1024px`
  "main surface + sticky side rail" structure Phase 65/68/69 use elsewhere
  was extended to the two remaining screens that still read as a flat single
  column at desktop. `AnalyzeSection`'s in-progress card stage
  (`.analyze-work-scene`) puts the flashcard in a main column and moves the
  small toolbar (읽기 탭에서 보기/지금까지 저장) plus a new live
  아는/헷갈리는/모르는/건너뜀 tally (`.analyze-tally`, reusing Study's
  completion-receipt "colored stamp dot + count" recipe) into a sticky
  `.analyze-work-aside`, so classifying reads as working at a desk with a
  tally sheet beside the card instead of a toolbar stacked above a form; the
  opt-in full ledger keeps its Phase 62 table structure, with a small
  drawer-pull accent added above it. `StudyLogPage` (통계 tab,
  `.study-log-scene`) splits into a main journal column (오늘 학습/학습
  일지/서가별 통계) and a sticky `.study-log-scene-aside` holding the 최근
  담은 단어/자주 틀린 단어 word logs, the same two-column notebook-spread
  idea Vocab/Shared Deck already use. Both are pure `>=1024px` CSS
  restructurings — DOM order, data, and all handlers are unchanged, and
  mobile/tablet stay the exact single-column flow from before this Phase.
  `GlobalFeedbackModal` picked up the shared `.paper-corner` fold (already
  used on every other index-card/panel surface) so the memo reads as one
  more note from the same material family rather than a generic dialog;
  its tape, underline select, and warm-paper textarea from Phase 60 were
  otherwise already on-model and are unchanged.

## Forbidden patterns

- Boxed admin-dashboard tiles as the primary Home layout.
- Raw counts as the loudest element of a Home shortcut (a small quiet badge
  elsewhere is fine; a badge is not the tile's whole subtitle).
- A new mascot/character, or a modified/regenerated Shiori asset.
- A large centered Shiori illustration standing in as Home's primary visual.
- Duplicating the full original reading text into any secondary UI, card,
  summary, feedback payload, or saved/localStorage payload.
- Presenting JLPT recommendation decks as an official/authoritative list —
  they are learning references only.
- Changing backend/API/SRS/schema/storage/shared-deck policy as a side effect
  of a visual pass.

## Tokens introduced

- `--notebook-cover`, `--notebook-cover-deep`, `--notebook-cream` (see
  `app/globals.css` `:root`) — the Home notebook-cover hero's fill and ink
  colors. Reuse these for any future notebook-cover-styled surface rather
  than inventing new greens.
- `--desk-wood`, `--desk-wood-deep` (Phase 67) — the App Shell desk scene's
  wood-desk background, only active at the `>=1024px` desktop tier. Reuse
  for any future wood-desk-styled surface rather than inventing another
  brown.
- `--paper-texture-image`/`--paper-texture-repeat`/`--paper-texture-size`
  (Phase 67) — the app's existing warm-paper `body` background, pulled out
  into custom properties so `.page` can reuse the identical texture as a
  "board on the desk" surface at the desktop tier without duplicating the
  gradient stack.

## Status

Phase 54 covered the design contract plus App Shell/Home (App Shell content
only -- rail/bottom-nav/topbar chrome stayed unstyled at the time). Phase 55
covered Reading + Inspector (reader page, start card, word inspector, save
tray). Phase 56 covered the reading candidate word list (sticker tray).
Phase 57 covered the Vocab tab (hero/filters, word list, management
panels). Phase 58 covered the Study tab (hero, rating stamps, answer
reveal, completion receipt). Phase 59 covered the Shared Deck tab (hero,
deck grid, and the opened-notebook detail panel). Phase 60 finished the App
Shell chrome itself (library rail/bottom-nav active states, topbar feedback
button) and covered the Stats/Info tab, the shared `StatsPanel` component,
and the `GlobalFeedbackModal`. Phase 65 restructured Reading + Inspector
again, deeper than Phase 55's visual pass: the word inspector moved from a
modal-only overlay to a real `>=1024px` pinned desk-scene column
(`.reader-desk-scene`/`.reader-inspector-rail`) with an idle guide state,
while mobile keeps the Phase 55 bottom-sheet modal unchanged. Phase 66 did
the same structural pass for Study: the active/complete card now sits in a
real `.study-card-stack` with two backing-sheet siblings on a dark felt
`.study-board-scene`, replacing the single centered `.study-card` on a
light desk tint. Phase 67 extended that same `>=1024px` desk-scene idea to
the App Shell and Home: `body` becomes a wood-desk background and `.page`
(the one wrapper every tab already renders inside) becomes a paper-textured
board resting on it, the library rail's active link reads as a bookmark
tab stuck to the board's edge, the topbar reads as a small paper toolbar
tag, and Home's cover + shortcut notes arrange into one 2-column desk
stage instead of stacking full-width. All of this is gated at the same
`>=1024px` tier as Phase 65/66 and leaves mobile/tablet unchanged. Phase 68
did the same structural pass for Vocab: the note screen becomes a
`.vocab-notebook-scene` spread (filter index rail | word list | a
selected-item note page on the right) instead of row-expansion pushing
detail open inline everywhere; mobile keeps the original inline
expansion, and management/share/custom-term panels moved below the
spread instead of wedging between the filter and the list. Phase 69
extended the same idea to Shared Deck: a `.shared-library-scene` wraps
the shelf sections and the opened detail panel in a wood-cabinet
backdrop (reusing Phase 67's `--desk-wood` tokens) at `>=1024px`, each
`shelf-section` (recommended/mine/other) becomes its own light
compartment card instead of sharing one flat backdrop, and deck cards get
a subtle 1-2deg resting tilt that straightens on hover/selection.
`BrandDeckCover` and every owner/subscriber/import condition are
untouched. Phase 71 closed out the brief's remaining polish passes: the
Analyze tab's card stage and the Stats (통계) tab's `StudyLogPage` each
gained the same `>=1024px` main-surface-plus-sticky-rail structure as
Phase 65/68/69, and `GlobalFeedbackModal` picked up the shared
`.paper-corner` fold so it reads as part of the same note/index-card
family instead of a standalone dialog. See "Analyze + Stats + Feedback
deep scene (Phase 71)" above for specifics. Phase 72 was a motion/delight
pass, not a structural one, on top of that Phase 54-71 visual truth:
Shiori picked up a slow (6-7s), small idle float on the `.shiori-asset-img`
element (never the outer `.shiori-asset` span, which keeps the existing
one-shot `app-pop` entrance) at the three spots she idles rather than
transacts -- Home's corner peek, Reading's idle inspector guide, and
`AppEmptyState`'s empty-illustration moment; Home's shortcut row now
stamps its three stickers in with a staggered `app-pop` (`backwards` fill,
not `both`, so each chip's own resting tilt reasserts once the entrance
ends); Study's rating stamps gained a quick radial "ink" flash on
`:active` on top of their existing Phase 58 hover-lift/press-scale; and
the shared-deck cover fold, the vocab row's own paper-corner fold, and
the home notebook CTA each picked up a small material-specific hover
detail (brightened fold color, deeper warm shadow) instead of leaning on
box-shadow weight alone. All additions are `transform`/`opacity`/
`border-color`/`box-shadow` only, covered by the existing global
`prefers-reduced-motion` rule, and none of them touch layout-driving
properties, component props, handlers, or API/SRS/storage logic. Phase 73
was a desk-prop/scene-density pass on Home/App Shell specifically: against
the mockups, desktop Home read as a wide paper board with only the cover
and three sticker notes on it, missing the mockups' desk-clutter (plant,
tape, pen, cup) that makes their version feel lived-in rather than
laid-out. `home-desk-props` (`>=1024px` only, matching `.home-desk-scene`'s
existing 2-column tier) adds a small plant, a washi-tape-roll-plus-
binder-clip cluster, a pen, and a cup/paper-scrap around the cover and
sticker column -- all pure CSS shapes (gradients/clip-path/box-shadow on
plain `<span>`s, no new images), `pointer-events: none` and `aria-hidden`,
positioned to bleed only into `.page`'s own side padding so they can never
cause real horizontal overflow. The layer renders as the *last* child of
`.home-desk-scene` (not the first) specifically so it paints on top of the
cover/sticker boxes it overlaps at the corners -- earlier in the DOM, the
same-stacking-level cover/chips (later in DOM) would have painted over
most of it. Separately, the cover itself picked up a page-edge line stack
and a small bookmark-tab notch (`.home-notebook-page-edge`/
`.home-notebook-tab`) plus a debossed text-shadow on the title -- these
are real `<span>`s, not `::before`/`::after`, because `.home-notebook-
cover` already spends both pseudo-element slots on `.card-stack-surface`'s
own "pages peeking out" ghost layers; a same-specificity pseudo-element
rule declared later in the file would otherwise silently win the cascade
and erase them (this is exactly what happened on the first pass here, and
is why this shows up as real spans instead). Each of the three home
sticker chips also picked up a small washi-tape accent on whichever
pseudo-element slot its own fold/pin/ghost-sheet detail wasn't already
using, so the row reads as taped-down notes rather than plain cards.
Mobile/tablet get only the cover's page-edge/tab/deboss detail (already
safely contained inside the cover's own `overflow: hidden` box) -- the
desk-prop layer is desktop-only by design, per the brief's "small hint
only" instruction for mobile. `AppShell.tsx`/`page.tsx` were not touched;
everything lives in `HomeDashboard.tsx` and `globals.css`. Phase 74
brought Reading and Study up to the same scene density so Home didn't
stand alone as the only "lived-in" desk: `.reader-desk-scene` (confirmed
free of both pseudo-element slots and `overflow` before touching it)
picked up its own lighter desk-prop layer -- a pen, a paperclip, and a
small paper scrap, deliberately without Home's plant/cup since Reading is
a focused work surface, not a welcome scene -- rendered last (same
paint-order reasoning as Phase 73's Home layer) so it sits on top of
`.reader-paper`/`.reader-inspector-rail` wherever it overlaps their
corners. `.reader-inspector-rail` also picked up a small cascading
index-tab accent (`.reader-inspector-tabs`, one span using `box-shadow`
to draw its 2nd/3rd colors -- no extra DOM) as a *sibling* of the pinned
`TokenDetailSheet`/idle guide rather than a pseudo-element on
`TokenDetailSheet`'s own div, which already stacks `bookmark-inspector`/
`paper-corner`/`card-stack-surface` fighting over the same `::before`/
`::after` slots -- adding a 4th contender there would have risked the
exact silent-cascade-collision failure mode this file's Phase 73 note
above describes, so `TokenDetailSheet.tsx` was left untouched entirely.
`.study-board-scene` got the quietest treatment of the three: one small
leaf-sprig hint (reusing Home's plant-leaf gradient recipe, minus the
pot) on its previously-unused `::after` slot, tucked in a bottom corner
well clear of the card stack/rating tray/completion receipt, dimmer than
Home's leaves since Study is a repeated-use screen. No `StudySection.tsx`
change was needed. Net result: Home reads as the richest "welcome desk,"
Reading as a moderately furnished work surface, and Study as the
quietest of the three -- an intentional density gradient, not a gap.
Phase 75 brought Shared Deck's shelf/cabinet scene up to that same
gradient, entirely in `globals.css` -- `SharedDeckSection.tsx` needed no
changes at all, since `.shared-library-scene`/`.shelf-section` turned out
to have both pseudo-element slots completely free. `.shared-library-scene`
picked up a leaf-sprig hint (top-left) and a small "서가" paper shelf-label
tag (top-right), both anchored via `top` only (never `bottom` -- see the
Phase 73 note on why); the combined padding of the scene (20px) plus
`.desk-surface-section` (16px) gives 36px of buffer before any real shelf
content begins, confirmed against a real (test-fixture-seeded) populated
shelf via exact `getBoundingClientRect()` checks, not just eyeballed.
`.brand-deck-cover` picked up a thin light-catch highlight along its left
edge on its previously-free `::before` slot (contained by the cover's own
`overflow: hidden`) -- applied uniformly to every deck cover rather than
a per-card decorative accent, since a repeated grid of cards is exactly
the kind of "don't over-decorate a repeated tile" context Study's Phase 74
note already covers. `.shared-deck-detail` picked up a small leaf-sprig
hint bleeding from its left edge on its own free `::before` slot (its
`::after` is already taken above 1024px by the existing top-edge
shelf-ledge echo), positioned below the header row so it never risks the
close/import/unpublish/republish buttons or the word-list/filter/
pagination content beneath it. All three pieces are gated the same
`>=1024px` tier `.shared-library-scene`'s wood-cabinet backdrop already
uses, so mobile/tablet render exactly as before this Phase. No owner/
subscriber/newcomer button conditions, import/unpublish/republish logic,
or state copy were touched. Phase 76 brought Vocab's notebook spread up to
the same desk-prop density, entirely in `globals.css` -- `VocabSection.tsx`
needed no changes at all, since `.vocab-notebook-scene`, `.index-card-filter`
(scoped to `.vocab-notebook-index .index-card-filter` so SharedDeckSection's
own reuse of that class for its subscribed-deck word filter stayed
untouched), and `.vocab-notebook-detail` all turned out to have free
`::before`/`::after` slots. `.vocab-notebook-scene` picked up one
top-anchored leaf-sprig hint (top-right, above the note page) rather than a
second full prop cluster -- this scene's own height is set by the word list
column, which can run to 50+ rows, so per the Phase 73 postmortem on this
file the prop had to be anchored via `top` only, never `bottom`. The index
rail's filter box picked up a small washi-tape corner plus a cascading
3-color page-tab accent (box-shadow draws the 2nd/3rd tabs, the same
one-element/no-extra-DOM trick as Reading's `.reader-inspector-tabs`),
echoing the mockup's 최근/모르는 단어/햇갈림 index tabs. The selected-word
note page (`.vocab-notebook-detail`) picked up a small wire paperclip
centered on its own top edge, reusing Reading's `.reader-desk-prop--clip`
nested-ring recipe, positioned away from the scene-level leaf so the two
never collide. All three are gated the same `>=1024px` tier the notebook
spread itself already uses; mobile/tablet render exactly as before this
Phase -- the word list stays a plain scannable list with no per-row
decoration (Phase 57's original reasoning for a 20-50-row Operate screen
still applies) and no new mobile hint was added, matching Phase 74 Study's
"quietest treatment" precedent over risking horizontal overflow on a
smaller viewport. Word/deck CRUD, status select, search/filter/sort, custom
term, and share/export/import logic were all left untouched. Phase 77 was a
mobile-only object pass on Home, closing the gap where mobile still read as
"app card screen" while desktop had picked up Phase 67/73's cover + desk
props. All changes are gated `<=640px` (the app's existing mobile
breakpoint) except one small always-on addition, so desktop's Phase 67/73
cover + side-sticker structure is untouched pixel-for-pixel. The cover
gained `.home-notebook-spine` -- a column of small ring-binding dots along
its inner left edge (a real span, same reasoning as Phase 73's page-edge/
tab spans: `.home-notebook-cover` already spends both pseudo-element slots
on `.card-stack-surface`'s ghost-page layers) -- mirroring
`.home-notebook-page-edge`'s dashes on the right so the cover reads as
spiral-bound on one side, and this one addition is unguarded since it's
just more cover-material realism, not a mobile-vs-desktop layout choice.
Mobile-only: the CTA (`.home-notebook-cta`) becomes a full pill instead of
the app-wide 12px button radius, reading as a label stamped on the cover
rather than a form button; `.home-notebook-sample-link` drops its
outlined-pill chrome for a plain underlined text link (still a 44px tap
target via padding, just invisible) since the app-wide mobile `button {
width: 100% }` touch-target rule had been stretching it into a second
full-width bar under the CTA, reading as two stacked admin actions instead
of one primary action plus a small link -- desktop keeps its existing
auto-width outlined pill untouched. The three `.home-sticker-chip` shortcuts
keep their Phase 54/73 tape/pin/fold/ghost-sheet accents exactly as they
are, but mobile-only picks up a lighter paper-toned border, a flatter
shadow, a wider tilt swing per chip, and each chip's own asymmetric corner
radius (vocab/review/decks now have visibly different silhouettes, not just
different corner decorations) since at phone width the shared border+shadow
card chrome had been reading as "three identical white tiles" despite the
existing per-chip decoration. No copy, callbacks, props, or API/SRS/storage
logic changed; `HomeDashboard.tsx` only gained the one `.home-notebook-spine`
span. Phase 78 was a "character presence" audit, not a new pass -- a full
grep of every `ShioriCharacter`/`ShioriMark`/`ShioriStamp`/`ShioriGuideCard`/
`AppEmptyState` call site found that Phases 54-77 had already placed Shiori
in essentially every empty/idle/loading/complete moment the brief's own
candidate list named: Study's ready/empty/complete states (`AppEmptyState
mood="review"/"empty"` plus the complete card's `ShioriStamp`), Vocab's
desktop idle detail panel (`ShioriGuideCard` in `.vocab-notebook-detail-idle`,
Phase 68), and Analyze's pre-analysis intro plus its result summary
(`ShioriCharacter variant="classify"` in the hero header, `ShioriStamp` on
completion) were all already in place, not gaps. The one genuine miss,
found by diffing every `AppEmptyState` call against the others: Shared
Deck's fetch-failed branch (`SharedDeckSection.tsx`, the `messageTone ===
"error"` case) was the single spot in the whole app still passing a bare
`icon={BookshelfIcon}` instead of `mood`, so a failed deck fetch read as a
harder "system error" beat than its own sibling loading/empty states two
branches away in the same slot. Fixed by switching it to `mood="empty"
moodSize="xl"` -- reusing the same asset the true-empty sibling already
uses (the copy, not the art, is what tells "failed to load" and "nothing to
show" apart), matching that sibling's `xl` size instead of introducing a
new one-off size. No other component changed; this was intentionally not
padded out to 3-4 locations since forcing more insertions where Shiori
already had an established, working placement would have been exactly the
"과한 배치" the brief warned against. Phase 80 ("de-admin utility surfaces")
followed up on Phase 79's full QA pass, which found the big structural
redesign stable but flagged a few remaining "management/form" surfaces.
Three small, independently-scoped fixes, all CSS-first: (1) `.vocab-form-
panel` (단어 직접 추가/사용자 정의 용어 추가/두 inline-edit forms -- the one
remaining plain solid-border/uniform-radius white box in Vocab) switched to
a dashed border and the same asymmetric index-card radius `.vocab-
management-panel`/`.custom-term-section` already use, reading as a slip
tucked in the notebook's back pocket instead of a settings-form card; the
3 JSX call sites also picked up the shared `.paper-corner` fold (its
`::after` slot was free) for the same reason Vocab's own word rows already
use it. (2) `.shared-preview-row`/`.shared-lexeme-row` (the opened Shared
Deck detail's word-preview and 학습 목록 rows) dropped their solid `1px
solid var(--border)` divider -- which cut a hard spreadsheet gridline
across `.shared-deck-detail`'s own ruled-paper background -- for a dashed
line in the same warm ink tone the ruled-paper lines use, so rows read as
notebook lines instead of table rows; the `<=640px` variant went further,
since it turned every row into its own solid-bordered white card once
columns stacked to 1fr (an even harder "admin list" read than desktop's
single divider), and now uses the same dashed-underline treatment at every
width instead of switching to a boxed-card look specifically on phones.
(3) Vocab's mobile hero action row (`.vocab-hero-actions-compact`, gated
`<=640px`) -- Phase 79's QA specifically flagged this as the most
admin/settings-panel-looking screen on mobile, because the app-wide mobile
`button { width: 100% }` touch-target rule stretched all 3 always-visible
buttons ("이 덱 학습하기"/"원문 읽기"/"더보기") full-width, stacking them into
what read as a vertical action list. Only the primary action keeps its
full-width button now; "원문 읽기"/"더보기" become small pill tags reusing
the same soft-bg/pill language this hero's own stat chips
(`.vocab-hero-chip`) already establish just above them, with the 44px tap
target kept via `min-height` (not visual padding) -- the same technique
Phase 77 used for Home's mobile CTA/sample-link split. Desktop is
untouched in all three cases (every rule is either scoped to a class Shared
Deck/other tabs don't reuse, or explicitly gated to the same `<=640px`
breakpoint). A fourth candidate from the Phase 80 brief -- restyling the
shared `.panel-card`/`.hero-card`/button primitives in `globals.css` -- was
deliberately deferred: those classes are reused across every tab, so
changing them carries a blast radius well beyond the "utility surfaces"
this Phase targeted, and the three scoped fixes above already addressed
every concrete gap found without touching global primitives. `VocabSection.
tsx`/`SharedDeckSection.tsx`'s props, callbacks, CRUD handlers, `StatusSelect`
semantics, and shared-deck owner/subscriber/import conditions are all
unchanged; `SharedDeckSection.tsx` itself needed no JSX changes at all.
Phase 87 returned to Vocab after the main notebook spread existed and focused
on the remaining empty/idle states rather than changing CRUD behavior: the
deck-not-selected state became a ruled-paper desk page with a pinned guide,
the list drawer gained a light stacked-paper base, desktop status filters
became page-edge tabs, and the right detail page now explains "no deck",
"no words", or "filtered out" in context instead of showing a generic nested
empty box. Phase 88 was the corresponding Shared Deck shelf-density pass:
one- or two-deck shelves no longer stretch covers to fill the whole
compartment, sparse space gains a faint plank texture and a CSS bookend, and
section headings read as paper catalog labels. All of it is desktop-only CSS
on the existing shelf/detail classes; owner/subscriber/newcomer policy and
buttons were verified as unchanged. Phase 89 addressed the mobile Reading
candidate tray after real `/analyze` QA showed that filter chips plus quick
select buttons could take seven stacked lines on a 320px viewport. The fix
keeps the same labels and handlers but turns those two control rows into
horizontal scroll strips under `<=640px`, with `min-width: 0` added through
the relevant container chain so the strips improve vertical density without
creating page-level horizontal overflow. Desktop Reading and the actual save/
analyze/SRS/storage contracts are untouched.

Phase 99 was a wording/hierarchy pass on the Reading tab's save UX, prompted
by the auto-save policy two phases earlier (classifying a word unknown/
uncertain now saves it immediately -- see `handleReadingStatusChange` in
`page.tsx`) leaving the surrounding copy still describing a manual "add to
basket, then save" flow as if it were the primary path. In
`TokenDetailSheet.tsx`, the classify grid (with a one-line, auto-hiding
`· 모르는·헷갈리는 단어는 자동 저장돼요` hint shown only while a word is
still unclassified) moved above the mobile fold divider, swapping places
with the basket-select toggle, which moved down into the secondary-actions
footer alongside word-nav and meaning-edit/report -- classifying is what a
reader actually does first now, so it's what they see first; the
multi-select tool is secondary, so it reads that way. That toggle's own
copy changed from "저장 바구니에 담기" (reads as an immediate save) to
"저장 대상으로 선택" (reads as queuing for a later batch save), matching
the "선택" language `ReadingVocabPanel`'s checkbox already used; its
success stamp changed from "노트에 담았어요" (implies persisted) to
"선택했어요". `ReadingVocabPanel`'s quick-select buttons ("모르는 단어
담기" etc.) picked up the same swap to "선택", and its two guidance lines
were corrected to describe what tapping a word vs. checking a box actually
does now, rather than the pre-Phase-98 assumption that tapping a word adds
it to the basket. `ReadingTab.tsx`'s `ReaderSaveDock` got the matching
"선택한 단어"/"선택한 단어 저장" relabeling and a corrected idle-state
hint. No component gained a new button, panel, or toggle -- every change is
copy, one CSS override for the relocated basket-row's margin, and a JSX
reorder within `TokenDetailSheet.tsx`; the Phase 89/91 mobile horizontal-
strip tray and Phase 94 compact-sheet sizing are untouched. Also removed:
`resolveReadingSaveTargets` in `coverageUtils.ts`, an orphaned bucket-mode
resolver left over from the Phase 97 removal of its only caller (the old
"빠르게 전체 저장" dock disclosure) -- confirmed dead by grepping every
`.ts`/`.tsx` file for callers before deleting; its still-used siblings
(`resolveSaveTarget`, `toSaveTarget`, `resolveSelectedReadingSaveTargets`,
the `ReadingSaveMode` type) were left in place and their comments updated
to stop pointing at the removed function. Backend, `/analyze`, SRS,
storage, and the actual save/PATCH/dedup decision logic are all unchanged.

Phase 100 picked up where Phase 99 left off on the mobile compact sheet:
classification was already above the fold and the basket-select toggle
already below it, but everything below that fold divider (basket-select,
word-nav, meaning-edit trigger, report-meaning) was still full bordered
buttons, so scrolling even slightly landed on a wall of boxes that read
as a feature panel rather than the mockup's quiet sticky note. All changes
are mobile-only CSS (`@media (max-width: 640px)`, scoped under
`.bookmark-inspector` so the desktop docked panel and pinned desk-scene
inspector, which have real vertical room, keep their original bordered
buttons) plus one JSX change: the "뜻 오류 신고" button in
`TokenDetailSheet.tsx` gained a dedicated `token-sheet-report-meaning`
class so it could be targeted without also catching the active meaning-
edit form's real Save/Cancel buttons, which share its parent
`.meaning-actions-row` and must keep looking like actual buttons. The
basket-select toggle (`.token-sheet-basket-button`) dropped its dashed-
border pill and solid active fill for a plain underlined accent-color
text link (auto width, not full-row) -- the already-visible `ShioriStamp`
"선택했어요" next to it still carries the "selected" signal, so the fill
was redundant. Word-nav buttons (이전/다음/모르는 단어로/첫 등장으로) and
the meaning-edit-trigger/report-meaning pair lost their border/background/
hover-lift and read as muted underlined text now, with nav buttons keeping
their 44px min-height touch target via padding alone. `.context-example-
block` (문맥 예문) lost its bordered/tape-strip card treatment at this
width, becoming a plain labeled paragraph instead of a second boxed card
sitting under the meaning block. Browser QA (scratch SQLite, 390/375/320px,
headless Chrome via CDP) confirmed the default fold view now shows exactly
5 buttons (close + the 4 classify pills) with word/meaning as plain text
above them, all quieted secondary actions remain reachable and functional
by scroll, the meaning-edit Save/Cancel buttons in an active edit are
untouched (still filled/bordered), auto-save-on-unknown/uncertain and no-
save-on-known/unclassified both still hold, and `scrollWidth === clientWidth`
at all three widths with zero console errors. No button, panel, or feature
was removed; no new box was added. Desktop/tablet (>=641px) and pinned
desktop (>=1024px) presentations, the Phase 89/91 candidate tray, and all
backend/API/SRS/save logic are unchanged.

Phase 101 returned to the Phase 89/91 candidate tray itself (`ReadingVocabPanel`),
which real `/analyze` QA at 1280/390/375/320px showed had become the reading
tab's second-largest panel once opened -- a dashed hairline "pull" handle that,
when expanded, revealed a hint line, search, filter tabs, quick-select tabs,
and a grid of sticker cards padded/shadowed/rotated enough to read as full
note cards rather than list entries; at 1280px the 13-word sample needed the
tray's own internal scroll to see past the first two rows. All changes are CSS
only, scoped to classes `ReadingVocabPanel.tsx` already owns (no JSX, copy, or
handler changes, and no touch to `TokenDetailSheet.tsx` per the phase brief).
The closed pull (`.reading-vocab-drawer-pull`) dropped from a 700-weight/12px
label with a 2px dashed top rule to a 600-weight/11.5px label with a 1px rule
and smaller icon/chevron (15px/14px -> 12px/12px), so it reads even more
clearly as a quiet list handle than "어휘 노트 보기" above it -- the chevron
shrink was scoped to `.reading-vocab-drawer-pull .reading-vocab-collapse-icon`
rather than the shared base class, since `VocabSection.tsx`'s own "더보기"
toggle reuses that class and was out of scope. Each sticker
(`.reading-vocab-sticker`) shrank from `padding: 14px 24px 10px 14px` /
`box-shadow: 0 6px 14px` / a 224px max-width to `9px 18px 7px 10px` / `0 2px
6px` / 208px, with the alternating tilt halved (+-1.5/1/0.6deg -> +-0.7/0.5/
0.3deg) so the tray reads as a light paper-grain list instead of a scattered
pile of note cards; the tray's own row gap tightened to match (14px -> 9px
vertical). Net effect confirmed in browser QA: the same 13-word sample now
fits without internal tray scrolling at 1280px, and 390px goes from one
sticker per row to two. The checkbox pin, saved/status/occurrence badges,
goto-text-position icon, and every click handler are unchanged, and mobile's
existing touch-target overrides (24px pin, 34-40px min-height buttons) are
untouched, so nothing shrank below a tappable size. `ReaderSaveDock`
(save-dock strip, "선택한 단어"/"어휘 노트 보기") was left alone --
already visibly heavier than the pull below it, so the hierarchy candidate D
in the phase brief needed no CSS. Verified: `npm run build`, `git diff
--check`, and CDP-driven headless Chrome QA against a scratch SQLite backend
at 1280/390/375/320px -- collapsed/expanded tray, Phase 89/91 filter and
quick-select horizontal strips (`scrollWidth > clientWidth` on the strip
itself, `document.documentElement.scrollWidth === clientWidth` on the page at
every width), quick-select selecting all saveable words, selected-save
landing 13 saved badges in the tray, token-click opening the compact
inspector, and classifying a word unknown auto-saving it, all still hold with
zero console errors/warnings. No backend/API/schema/SRS/shared-deck/auth/
localStorage code was touched.

Phase 102 finished the save dock / post-save CTA weight that Phase 101 had
left alone. `ReaderSaveDock`'s shelf row, idle hint (`ShioriGuideCard`), and
primary save button were already about as light as they could get without
losing the save action's discoverability, so the one real change is to
"어휘 노트 보기": it leaves the reading tab entirely (a jump to the vocab
tab, not a step in the reading -> save -> review loop), yet it was rendered
as a full bordered `ghost-button`/`secondary-button` at every viewport,
including a full-width mobile row and, after a save, a second button sitting
next to "바로 복습" that made the post-save CTA read as a two-button work
panel. One JSX change in `ReadingTab.tsx`'s `ReaderSaveDock`: that button
drops the conditional `ghost-button`/`secondary-button` + `reading-summary-
cta-button` classes for a single new `reading-summary-link-button` class,
same `onGoToVocab` handler, same icon+label, same position. The new CSS
class (`app/globals.css`) strips all button chrome -- no border, no
background, no shadow, no forced min-width/min-height, intrinsic width
instead of the app-wide mobile `button { width: 100% }` touch-target rule --
leaving a `var(--muted)` underlined text action that turns accent-colored on
hover, matching the text-link treatment Phase 100 already used for the
compact inspector's secondary actions. Because the link no longer carries
`.reading-summary-cta-button`, it's unaffected by that class's desktop/mobile
flex-basis rules, so "바로 복습" (still a real button, still gets the accent
box-shadow ring) is now the only boxed element in `.reading-summary-next-
actions` at every width -- idle state shows just the quiet link under the
divider, post-save state shows one primary button with the link beside it on
desktop (>=1024px, same flex row) or under it on mobile (its own line, not
stretched to match the button's width). Verified with `npm run build`,
`git diff --check`, and CDP-driven headless Chrome QA against a scratch
SQLite backend at 1280/390/375/320px: idle state (0 selected) shows the count
badge, saveable chip, idle hint, and link with no primary save button;
selecting all 13 saveable words via the candidate tray's "전체 선택" surfaces
the full-width/capped-width primary save button with the live count; saving
shows the success message, "바로 복습" CTA with its accent ring, and the link
now sitting beside/under it instead of stacked as a second full-width button;
token click still opens the compact inspector; `document.documentElement.
scrollWidth === clientWidth` at all four widths; zero console errors or
network failures. No backend/API/schema/SRS/shared-deck/auth/localStorage
code was touched, quick-save-all and "담기" language stayed removed, and no
button/card/panel was added -- only the existing "어휘 노트 보기" button's
chrome went away.

Phase 104 took the two most severe P2s Phase 103's audit found (both worse
than Reading's pre-Phase-102 save dock: 3-4 real buttons stacking full-width
on mobile) and applied the exact same fix shape Phase 102 proved out --
one kept primary button, everything else in the row demoted to a plain
underlined text action. `.study-actions` is shared by four call sites across
two files (Study's empty-state CTA, its single-button "정답 보기" row, its
completion CTA, and Analyze's `ClassifyResultSummary`), so instead of editing
that shared class, one new scoped class was added -- `.study-actions-link-
button` (`app/globals.css`), styled identically to Reading's `.reading-
summary-link-button` (no border/background/shadow/min-width, intrinsic
width, underlined `var(--muted)` text turning accent-colored on hover) plus
`align-self: flex-start` so it doesn't inherit the mobile `.study-actions
{ align-items: stretch }` column layout's full-width stretch the way a real
button does. Three JSX call sites changed classNames only, same handlers,
same conditions: Study's empty-state row keeps "원문 읽기 시작" as the one
real button (already the row's only unstyled/primary-looking button) and
demotes "어휘 노트 보기"; Study's completion row keeps "한 번 더 복습" (same
reasoning -- already the row's established primary) and demotes "원문 읽기
시작", "어휘 노트 보기", and the conditional "오늘 복습 보기"; Analyze's
`ClassifyResultSummary` already had its real primary ("모르는 단어 노트에
담기") sitting on its own line above `.study-actions`, so both buttons in
that row ("원문 읽기로 이동", "어휘 노트 보기") -- pure navigation, neither
more important than the other -- became links. The single-button "정답
보기" `.study-actions` row never gained the new class since it had nothing
to demote. Verified with `npm run build`, `git diff --check`, and CDP-driven
headless Chrome QA against a scratch SQLite backend at 1280/390/320px:
empty-state and completion states reached via real quick-start/rating-button
flows (not manual DOM state injection), `.study-actions-link-button` click
correctly switched `activeTab` to vocab (functionality preserved), completion
CTA went from up to 4 stacked full-width boxes to 1 button + up to 3 quiet
links, Analyze's summary went from 3 buttons to 1 button + 2 links, and
`document.documentElement.scrollWidth === clientWidth` held at every width
with zero console/network errors caused by these changes. One pre-existing,
out-of-scope issue was surfaced during QA and left untouched per the phase's
backend/logic-change ban: saving classified words from Analyze triggers a
422 from `GET /vocab-items?deck_id=&sort=created_desc` (an internal post-save
list refresh sending an empty `deck_id`) -- reproducible before this phase's
changes too, unrelated to the CTA buttons themselves, and out of scope here.
No backend/API/schema/SRS/study-queue/review-submission/classification-save
logic, button conditions, or global primitives were touched; Reading, Vocab,
and Shared Deck were not modified.

Phase 105 fixed the 422 Phase 104 surfaced. Root cause traced to `app/
page.tsx`'s `saveSelectedTokens` (Analyze's save handler): after saving, it
calls `loadVocabItems()` with no argument, which defaults to the
`selectedVocabDeckId` component state -- deliberately left as `""` until
the user actually opens the Vocab tab (see the Phase-labeled comment at its
declaration: "단어 탭이 아직 열리지 않았으므로"), so any save flow reached
without visiting Vocab first hits this default. Inside `loadVocabItems`,
the "omit deck_id for the all-decks case" guard only excluded the `"all"`
sentinel (`if (safeDeckId !== "all")`), not the empty-string unset state, so
`""` fell through to `params.set("deck_id", "")`, producing `/vocab-items?
deck_id=&sort=created_desc`. The backend's `deck_id: int | None = Query
(default=None)` (`backend/app/main.py`) can't parse an empty string as an
int and isn't given the chance to fall back to its `None` default since the
param is present, just empty -- hence the 422. Save itself was never the
problem; only this post-save refresh call was malformed. The same exact
guard shape existed in two sibling helpers -- `loadCustomTerms` and
`loadStudyStats` -- both reachable via their own no-arg default (`deckId:
string = selectedVocabDeckId` / `= selectedStudyDeckId`); `loadStudyStats`
wasn't actually exploitable today since nothing ever sets `selectedStudyDeckId`
to `""` (default `"all"`), but the identical bug shape made it worth closing
alongside the other two rather than leaving a second latent copy. Fix, in
all three, one line each: `!== "all"` became `!== "all" && !== ""`. No
backend/schema change -- the frontend was sending a request the backend
never should have received, so the fix is entirely "don't build that query
param when there's no id," matching the phase's own preferred direction.
Verified with `npm run build`, `git diff --check`, and CDP-driven headless
Chrome QA against a scratch SQLite backend: reproduced the exact Phase 104
repro (Analyze tab reached directly, without ever visiting Vocab, sample
text classified as all-unknown, save clicked) and confirmed the post-save
refresh now fires as `/vocab-items?sort=created_desc` (deck_id omitted
entirely) with zero failed requests and zero console errors, save success
message unchanged. Also checked for regressions in the two paths sharing
this state: Vocab tab's own deck-picker still sends `deck_id=1` for a real
deck and omits it for "전체" ("all"), both zero-error; Reading's save-then-
"어휘 노트 보기" path (`goToVocabFromReading`, which already passed
`readingSelectedDeckId` explicitly rather than relying on the buggy default)
still sends `deck_id=1&sort=created_desc` correctly, confirming it was never
affected and stays that way. No Analyze classification/save logic, SRS,
storage, shared-deck, auth, or design/CSS was touched.

Phase 106 picked up one of Phase 103's two Shared Deck P2s: the detail
panel's top/bottom "닫기" pair. Round 0 re-read `SharedDeckSection.tsx`
closely first, since the brief called for judgment, not an assumed fix. The
card `.row-actions` P2 turned out to be smaller than Phase 103 estimated --
`showActionButton`'s `!deck.is_owner` guard and `canManageDeck`'s `deck.
is_owner` guard are mutually exclusive, so a card renders at most 2 buttons
(상세 보기 + exactly one of 가져오기/열기/공유 취소/다시 공유하기), never
3; left untouched since there's no real box-stacking problem to fix (noted
as a Phase 103 audit correction, not a new finding). One adjacent, genuine
duplicate turned up instead while reading the subscribed-card branch: for
an already-subscribed deck, both "상세 보기" and "열기" call the exact same
`onSelectDeck(deck.id)` handler -- two differently-labeled buttons doing
the identical thing. Fixing that changes a button's conditional behavior/
count, which this phase's Round 1 bar and forbidden-line list both rule
out; recorded as a Phase 107 candidate rather than touched.

The top/bottom 닫기 pair itself: read as duplicate-feeling only in the top
instance, where it sits in `.heading-actions` next to the deck's real
per-state primary (가져오기/학습 목록에 추가/공유 취소/다시 공유하기) at
equal visual weight, competing for attention with the actual next step. The
bottom instance in `.form-actions` is alone -- no sibling to compete with --
and after a subscribed deck's word list (up to hundreds of words with its
own search/filter/80-item-page "더 보기") a bottom close is a genuine long-
list convenience a prior QA round already flagged as worth keeping. So the
fix only touches the top instance: one className swap in `SharedDeckSection.
tsx` (`secondary-button` -> a new `shared-deck-detail-dismiss`) plus one new
scoped CSS block in `globals.css`, styled like the underlined text-link
treatment Reading/Study/Analyze already established (no border/background/
shadow, intrinsic width via `align-self: flex-end` so it doesn't inherit
the mobile `.heading-actions{align-items:stretch}` full-width stretch). The
shared `.heading-actions` class itself (also used by `VocabSection.tsx`)
was never touched -- only this one button's own class changed. The bottom
닫기 keeps its full `secondary-button` weight, unedited. No condition,
button count, or callback changed anywhere; `onCloseDetail` fires exactly
as before from either button. Verified with `npm run build`, `git diff
--check`, and CDP-driven headless Chrome QA against a scratch SQLite
backend, driving two real registered accounts (owner + subscriber, via
`/auth/register` + localStorage token swap) through actual click flows --
not asserted state -- at 1280/390/320px: owner published/unpublished/
republished detail all show the demoted top 닫기 next to a full-weight
공유 취소/다시 공유하기, and toggling unpublish/republish still updates
`UnpublishedBadge` and button labels correctly (condition logic intact);
newcomer detail shows a clearly prominent "학습 목록에 추가" next to the
quiet 닫기; the demoted link still closes the detail panel on click
(function preserved); post-import detail correctly drops the import button
from the header per its existing condition, leaving only the quiet 닫기
there while the bottom 닫기 keeps full weight beside the word list;
`document.documentElement.scrollWidth === clientWidth` held at every width;
zero console errors (one unrelated `404 /favicon.ico`, present on every page
load regardless of this change). No backend/API/schema/SRS/shared-deck-
policy/auth/localStorage code, owner/subscriber/newcomer button conditions,
or global primitives were touched; Reading/Study/Vocab/Analyze were not
modified.

Phase 107 closed the duplicate-action finding Phase 106 surfaced instead of
just recording it. Round 0 built the full per-state card table first:
`showActionButton` (`!deck.is_owner && (published || (isSubscribedMode &&
alreadyImported))`) and `canManageDeck` (`canManageSharedDecks && deck.
is_owner`) are mutually exclusive, so every card renders 상세 보기/상세
닫기 plus at most one of 공유 취소 / 다시 공유하기 (owner) or 학습 목록에
추가 / 다시 가져오기 / 열기 (non-owner) -- except the one cell where
`!deck.is_owner && isSubscribedMode && alreadyImported`: there, the second
button's onClick branches to `onSelectDeck(deck.id)` (label "열기"), the
exact same call the "상세 보기" button next to it already makes. Tracing
`onSelectDeck` into `page.tsx`'s `loadSharedDeckDetail` confirmed it's not
just visually duplicate -- calling it with an already-selected id runs its
own `if (selectedSharedDeckId === sharedDeckId && selectedSharedDeck) {
closeSharedDeckDetail(); return; }` toggle, so "열기" already opens **and**
closes the same panel "상세 보기"/"상세 닫기" does; the two labels just
disagreed about which state they were in. Went with recommendation A (열기
only): a subscribed-mode deck's detail panel IS its 학습 목록 (search/
filter/status-select, confirmed in Phase 106 QA) once imported, so there's
no separate "preview vs manage" distinction left to justify two buttons --
unlike the newcomer state (상세 보기 = preview, 학습 목록에 추가 = commit,
genuinely different actions) or the non-subscribed-mode "다시 가져오기"
case (calls `handleImportClick`, a real re-copy, not `onSelectDeck` at all).
One `SharedDeckSection.tsx` change: a new `hasDuplicateOpenAction` flag
(`!deck.is_owner && isSubscribedMode && alreadyImported`) gates the "상세
보기"/"상세 닫기" button's rendering -- `null` in that one cell, unchanged
everywhere else (owner, newcomer, non-subscribed-mode all keep both their
existing buttons exactly as before). No condition on `showActionButton`,
`onImportDeck`, `onUnpublishDeck`, `onRepublishSharedDeck`, or any handler
body changed -- only whether one already-redundant button renders. The
remaining "열기" keeps its own toggle behavior (same onClick as before), so
closing is still one click away, on top of the detail panel's own top/
bottom 닫기 controls from Phase 106. Verified with `npm run build`, `git
diff --check`, and CDP-driven headless Chrome QA (two real registered
accounts, scratch SQLite, actual click flows) at 1280/390/320px: owner
published/unpublished/republished card actions are byte-identical to
before (상세 보기 + 공유 취소/다시 공유하기, toggle-open/close via the
card button all still work); newcomer card still shows both 상세 보기 and
학습 목록에 추가; after importing via the card, the card shows exactly one
button ("열기"); clicking it opens the detail panel with the 학습 목록
word list, clicking it again closes it (toggle preserved), and reopening
then closing via the Phase 106 dismiss link also works; `document.
documentElement.scrollWidth === clientWidth` at every width; zero console
errors. No backend/API/schema/SRS/shared-deck-policy/auth/localStorage
code, import/unpublish/republish/word-status logic, or owner/newcomer
button conditions were touched; Reading/Study/Vocab/Analyze were not
modified.

Phase 108 ran the full mobile loop (Home -> Reading sample/analyze -> token
inspect/select/save -> Study empty/active/complete -> Vocab expanded detail
-> Shared Deck) end to end at 390px via real clicks, to check whether
Phase 93-107's per-screen de-boxing work actually reads as one coherent
"simple casual tool" feel rather than Reading being the only light screen.
Reading/Study-CTA/Analyze-CTA/Shared-Deck results from prior phases all
held unchanged. The one real remaining spot: `VocabSection.tsx`'s expanded
`VocabItemDetail` row (`.vocab-item-actions`) still showed 4 full bordered
buttons -- "내 단어장 뜻 수정" (MeaningQuickEdit's trigger), "뜻 오류 신고",
수정, 삭제 -- all stacking full-width on mobile (`.vocab-item-actions`
goes `flex-direction:column` under 640px, same shape every prior phase's
fix addressed). `StudySection.tsx`'s active-card `.meaning-actions-row`
(same trigger + its own "뜻 오류 신고") had the identical problem, one tier
lighter (2 buttons, still both full-width on mobile via `.meaning-actions-
row`'s own column rule) -- explicitly named as candidate B in the phase
brief.

Both share the wrinkle that `MeaningQuickEdit`'s trigger button is also
used by `TokenDetailSheet.tsx` (Reading's word-detail sheet), where Phase
100 deliberately kept it a real button on desktop/tablet and only demoted
it inside the mobile compact sheet -- editing the component's own base
`.meaning-quick-edit-trigger` rule, or the component itself, would have
cascaded into Reading and broken that distinction. Fix instead scopes
entirely through CSS ancestor selectors (`.vocab-item-actions .meaning-
quick-edit-trigger`, `.study-answer-reveal .meaning-quick-edit-trigger`)
so `MeaningQuickEdit.tsx` and `TokenDetailSheet.tsx` are untouched --
Reading's own already-established mobile-only demotion for this exact
button keeps working exactly as before. The two inline "뜻 오류 신고"
buttons (VocabSection.tsx, StudySection.tsx -- not a shared component, just
duplicated JSX in each file) got a single new class, `.report-meaning-
link-button` (`globals.css`), applied directly in each file; TokenDetail
Sheet's own `.token-sheet-report-meaning` version is a separate class and
untouched. All three demoted buttons reuse the same underlined-text-link
visual language Reading/Study/Analyze/Shared-Deck already established in
Phases 102/104/106 (no border/background/shadow, intrinsic width via
`align-self`, muted color turning accent on hover). 수정 and 삭제 keep full
button weight -- 삭제 (`danger-button danger-button-subtle`) is completely
unchanged, per the phase's explicit "don't weaken destructive actions"
instruction. Total: 3 code files (`globals.css`, `VocabSection.tsx`,
`StudySection.tsx`), 0 condition/logic/callback changes.

Also audited and deliberately left alone: Vocab's 덱 관리/고급/덱 공유
management panels (create/delete-deck, custom-term manager, publish-deck
form, backup/CSV export) -- already progressive-disclosure-gated behind
"더보기 -> 관리" plus two more nested toggles (Phase 68's merged "soft note"
treatment), matching the phase brief's own instruction to record this as a
Phase 109 candidate rather than touch it given its condition/risk surface.
Study's quick-start tile grid and 4-way rating buttons, and Vocab's dense
scan-first item list, were confirmed untouched (both explicitly protected).

Verified with `npm run build`, `git diff --check`, and CDP-driven headless
Chrome QA against a scratch SQLite backend, driving the real click flow
(no injected state) at 390px primary with 375/320/1280 spot-checks: full
loop completed with zero console errors and zero failed requests (one
unrelated `favicon.ico` 404); `document.documentElement.scrollWidth ===
clientWidth` at every width; Study's active-card row now measures ~93-106px
(intrinsic) for the two demoted links vs 288px (full mobile width) for the
rating grid siblings' equivalents; Vocab's expanded row shows the same
~93-106px links next to two still-288px real buttons (수정/삭제).
`reachedComplete: true` with `rounds: 13` confirmed the same 13-word sample
flowing correctly through save -> review -> completion, matching every
prior phase's baseline. No backend/API/schema/SRS/storage/shared-deck/auth
code, Study queue/review logic, Vocab CRUD/status/deck/share/custom-term
logic, or destructive-action strength was touched; Reading's Phase 93-102
results and `TokenDetailSheet.tsx` are unmodified.

Phase 109 was a no-code round: Round 0 investigation into Vocab's
management/share/custom-term/backup panels and Shared Deck's remaining
detail/list/pagination controls found no candidate that cleared this
phase's bar (CSS-only, no condition/logic change, no destructive-action
weakening, 1-3 files). Reading the actual code first (not guessing from
class names) showed both areas were already resolved by earlier phases,
not newly discovered box-clutter:

Vocab management: the `.vocab-management-panel`/`.custom-term-section`
CSS carries an explicit Phase 68/80 comment trail confirming 덱 관리/고급/
덱 공유 (and separately 사용자 정의 용어) were already merged from three
bordered `.management-card` boxes into one shared soft "note" surface with
dashed section rules, years before this phase -- there was no "admin
settings screen" left to fix. Every remaining button in that surface falls
into a category this phase's own instructions protect from demotion:
덱 만들기 / 공유 등록 / 사용자 정의 용어 추가 are real submit actions;
현재 덱 삭제 / 용어 삭제 are destructive (danger-button-subtle, already the
established "outline chip, not solid red" treatment); 현재 덱 공유 파일로
내보내기 / 덱 가져오기 / CSV 다운로드 are genuine file-utility actions the
brief explicitly says not to make "overly casual," and they're already
opt-in behind a "고급 백업/파일 내보내기" disclosure toggle, not shown by
default. The only two pure-navigation-style toggles found (사용자 정의
용어 관리, 고급 백업/파일 내보내기) each sit alone in their own section
with no sibling button to stack against, so demoting either to a text link
would not reduce any real box-clutter -- it would just make an otherwise-
normal section header control look understyled. Browser QA (CDP-driven
headless Chrome, scratch SQLite, 390px, real clicks through 더보기 -> 덱/
공유 관리 -> 고급 백업 toggle -> 사용자 정의 용어 관리) confirmed this
visually: the management panel, backup tools, and custom-term panel all
render as one continuous dashed-divided note, not stacked admin cards, at
zero console errors and zero horizontal overflow.

Shared Deck: the word-list search/filter (`.shared-lexeme-word-filter`,
reusing the same "카드함 필터" drawer-tab language as Vocab's own filter),
pagination (`.shared-lexeme-load-more`, a single `secondary-button
compact-button` with only a margin-top rule -- no extra chrome to strip),
and per-word `StatusSelect` dropdowns were already minimal-weight going
into this phase and are explicitly named in the brief as controls whose
functionality matters more than further stylistic thinning ("StatusSelect
같은 form control은... 건드리지 않는 것을 기본값으로 한다"). Combined with
Phase 106/107 already having resolved the detail panel's duplicate close
and the subscribed-card duplicate action, there was nothing left in Shared
Deck within this phase's safe-change bar; not independently re-tested this
round beyond a zero-error tab-load spot check, since nothing in its code
path changed since Phase 107's thorough owner/subscriber QA.

Full mobile loop re-QA (390px, real clicks: Home -> Reading sample/
analyze/token-inspect/select/save -> Study -> Vocab list/management/
backup/custom-term panels -> Shared Deck) also checked the brief's other
stated risk -- "has recent de-boxing gone so far that a primary action
reads as weak" -- and found no such spot: every screen still shows exactly
one clearly-buttoned primary action per state (덱 만들기 / 공유 등록 /
학습하기 / etc.), with only genuinely-secondary/duplicate actions carrying
the lighter text-link treatment from Phases 102/104/106/108. Phase 108's
Vocab expanded-detail fix reconfirmed unchanged (내 단어장 뜻 수정 ~106px,
뜻 오류 신고 ~93px vs. 수정/삭제 at a full 288px). Zero console errors,
zero failed requests (excluding the known unrelated favicon 404), and
`document.documentElement.scrollWidth === clientWidth` held at 390px
throughout. `git status --short` is empty -- no files were changed this
phase.

Phase 110 was a no-code design-review pass: with the Phase 93-109 de-boxing
series apparently at its natural end (Phase 109 found no further
candidates), this phase re-read the original brief
(`casual-sticker-reader-redesign-brief.md`), both mockup boards
(`docs/design/mockups/casual-sticker-reader-{mobile,desktop}.png`), and
this file's own "Principles"/"Per-screen direction" sections, then checked
the live app against them with real browser QA (scratch SQLite, CDP
headless Chrome, 33 screenshots across Home/Reading/Study/Vocab/Shared
Deck/Analyze/Stats/Feedback at 1280/390, plus 375/320 spot-checks on
Reading's inspector and Study's active card) rather than reading code.
Overall verdict: the redesign has substantively reached the brief's
direction. Home, Reading (both the reader page and the compact/pinned
inspector), and Study's card-stack-on-board scene are close, functional
matches to their mockup panels -- notebook-cover hero, one primary CTA,
Shiori as a small corner/idle-hint presence never competing with content,
word-detail-as-sticky-note, 4-way rating stamps. Shared Deck's shelf frame
and Vocab's notebook-spread container (tape corner, ruled-paper card-stack
surface, pinned right-hand detail page) also read the part.

One deliberate, correctly-justified divergence: Vocab's word list renders
as a dense vertical list, not the mockup's tilted sticker grid. This isn't
an oversight -- Phase 57's own DESIGN.md entry already reasoned through it
("an Operate screen with 20-50 interactive rows needs to stay scannable")
and this phase's own brief independently warns against "무리하게 장식화"
of a functionally-important operate UI just because it differs from the
mockup. Confirmed still the right call; not touched.

No P1s. Two P2/P3-tier gaps recorded for a future phase, neither meeting
this phase's no-code-unless-obvious-bug bar: (1) Study's active card, on a
320-390px phone, pushes the 4-way rating grid (the screen's one real
decision) below the fold under word/reading/POS/meaning/tags/edit-links/
example-sentence content -- pre-existing, not a Phase 108 regression (that
phase's link-demotion reduced height, if anything), but worth a content-
priority pass in a dedicated phase rather than a reactive CSS patch here.
(2) Analyze/Stats/Feedback have no mockup panel of their own (the original
6-panel board only covers Home/Reading/Inspector/Vocab/Study/Shared-Deck)
and were extrapolated from the same visual language after the fact --
consistent in execution, but worth a deliberate check against product
intent rather than assumed-fine-by-similarity. A third item was
investigated and ruled a non-issue rather than a gap: the black "N" circle
visible bottom-left in every mobile screenshot is Next.js's own dev-mode
indicator (the same element that showed "1 Issue" during Phase 104's QA),
not app UI -- absent from production builds, not a z-index/overlap bug to
fix.

Nothing should be touched further in Reading/Study/Analyze CTA hierarchy,
Shared Deck close/action de-duplication, or Vocab's list density -- each
already reflects a deliberate, documented decision from Phases 93-109, and
re-opening any of them without new evidence would just re-litigate settled
calls. `git status --short` shows only this file -- no functional code was
touched.

Phase 110's second pass (content-priority) fixed the one real gap the
review found: on 320-390px phones, revealing a Study card's answer stacked
뜻 -> 읽기/품사/기본형 tags -> (personal vocab items only) 뜻 수정/오류
신고 links -> 예문 callout -> the 4-way rating grid in that DOM order
inside `.study-answer-reveal`, and a pre-existing comment in
`StudySection.tsx` (the `ratingGridRef`/`scrollIntoView` effect, "answer
reveal pushes the rating grid below the fold on common phone heights") had
already documented the symptom without fixing the cause. 읽기/품사 are
already shown pre-reveal in `.study-front` regardless, so the tags row
mostly repeats what's already visible; 기본형, the edit/report links, and
the example sentence are all genuinely secondary to the one decision this
screen exists for (다시/어려움/보통/쉬움). Fix is CSS-only, one file
(`app/globals.css`, inside the existing `@media (max-width: 640px)`
block): `.study-answer-reveal` is already `display: grid`, so `order` was
enough to move `.study-rating-grid` (and `.study-reviewing-hint` right
behind it, so the "저장하는 중" message still appears next to the buttons
it's about) directly after the meaning hero, pushing `.study-answer-tags`,
`.study-example-callout`/`.study-example-empty`, and (ancestor-scoped
`.study-answer-reveal .meaning-actions-row`, since that class is shared
with `TokenDetailSheet.tsx`) below -- no JSX/DOM reorder, no new state, no
condition changes; `.study-answer-reveal`'s gap also tightened from 20px to
14px on mobile only. Desktop (`>640px`, outside this media query) keeps
the exact original order and card-stack feel untouched. Verified with
`npm run build`, `git diff --check`, and CDP-driven headless Chrome QA
(scratch SQLite, real click flow: sample text -> analyze -> save -> Study
new-word session -> reveal) at 320/375/390 plus a 1280 desktop regression
check: the rating grid measured fully within the viewport
(`top`/`bottom` both inside `[0, innerHeight]`) at all three phone widths
with only 18px between the meaning box and the grid (vs. 246px still
separating them on unchanged desktop), no scroll needed to reach it in the
common case; clicking a rating button still correctly advanced to the next
card (word changed, answer state reset); 내 단어장 뜻 수정/뜻 오류 신고
remained present and reachable below the fold; zero console errors, zero
failed requests, `scrollWidth === clientWidth` at 320px. Rating button
colors/labels/4-way structure, SRS/review-submission logic, study queue/
new/recent/shared-deck-mode logic, and MeaningQuickEdit/report-meaning
functionality are all unchanged; Reading/Vocab/Shared Deck/Analyze were not
touched.

Phase 111 was the intent check Phase 110 itself asked for: Analyze,
Stats/Info, and the Feedback modal have no dedicated mockup panel (the
6-panel board only covers Home/Reading/Inspector/Vocab/Study/Shared-Deck)
and were extrapolated from the same visual language after the fact, so this
phase re-read `AnalyzeSection.tsx`, `InfoSection.tsx`,
`GlobalFeedbackModal.tsx`, and their scoped `globals.css` rules, then
verified against a real scratch backend rather than trusting the code's own
extensive comment trail. Setup: copied `vocab_claude_scratch_round4.db`
(10 vocab items across 4 decks under a second QA-only user) to a phase-local
scratch db, then reassigned every row's `user_id`/deck ownership to the
dev-fallback user (id 1) so the no-auth-header dev session used by
`get_or_create_dev_user()` would see populated Stats/Analyze-ledger data
instead of an empty account -- a QA-data reshuffle only, not a schema or
product change, and confined to a throwaway sqlite copy. Verified with
CDP-driven headless Chrome (fresh profile) against this scratch backend at
1280/390/375/320: intro -> classify-card -> result-summary -> ledger-toggle
for Analyze, empty and populated Stats, and Feedback modal open/validate
(too-short message correctly keeps 제출 disabled)/cancel (no real submit
sent). Zero console errors across the whole run, zero failed requests, and
`document.documentElement.scrollWidth === clientWidth` held at every width
tested.

Verdict on two of the three screens: non-issues, confirming the code
comments' own account of prior phases' work rather than contradicting it.
Stats/Info renders as the "학습 기록장" journal Phase 71's DESIGN.md entry
already described -- `TodayStudyMemo`'s three chips, `StudyTimeline`'s
diary-style lines, and `DeckProgressJournal`'s paper-corner index-card deck
rows (progress bar + 오늘 복습/모르는 단어 visible, 전체/아는/헷갈리는 behind
a `<details>` disclosure) read as a study log, not a stats dashboard, at
every width; the >=1024px two-column split (main journal + sticky "최근 담은
단어/자주 틀린 단어" aside) matches Reading/Vocab/Shared Deck's own
"surface + side rail" pattern. The Feedback modal is fully in-world since
Phase 60/71 -- paper-note textarea on warm `--paper-bg`, taped-note corner,
underline-style category `<select>`, bottom-sheet-with-stacked-buttons on
mobile -- and Phase 103 already ruled the standard cancel/submit footer a
non-issue; this phase found nothing to add. Analyze's intro stage
(Shiori + hero copy + dashed-paper textarea + one solid primary CTA) and its
post-classification result summary (coverage chips, one solid "모르는 단어
노트에 담기" button, two de-boxed `study-actions-link-button` links per
Phase 104) both hold up the same way, at every width tested, with no
bottom-nav overlap.

One real P1 gap found in Analyze's card stage, the one screen state this
phase actually needed browser QA (not just code-reading) to catch: on every
single card during classification -- not just once per session -- the 4-way
`.classify-action-grid` decision (아는/헷갈리는/모르는/건너뛰기, the whole
screen's one real decision) renders partially *behind* the fixed
`.app-bottom-nav` at 320-390px, not merely below an ordinary fold.
Measured directly via `getBoundingClientRect()` on both the seeded-empty
dev account and the reassigned populated account (10 real words): at 390px
the grid's top edge (`y: 786.6`) sits inside the nav's own vertical span
(`top: 783` to `bottom: 844`), and the grid extends to `y: 966.6` -- around
120-150px of its 180px height is unreachable without scrolling past a
sticky-looking but actually just tall header stack (읽기 탭에서 보기/지금까지
저장 toolbar + word/reading/quality-badge/meaning/meta-tags/context-example,
all rendered above it). This is the same *shape* of bug Phase 110's second
pass fixed for Study's `.study-answer-reveal`, but this phase did not apply
that fix here: Study's fix worked because `.study-answer-reveal`'s meaning/
tags/example/rating-grid are already flat CSS-grid siblings, so a mobile-only
`order` change alone could promote the rating grid ahead of the merely-
secondary tags/example. Analyze's `ClassifyWordCard` instead returns word/
reading/quality-badge/meaning/meta-tags/example as one bundled fragment
inside a single `.classify-word-card-content` grid item (a sibling of
`.classify-actions`, not a parent of it) -- so there is no flat sibling set
for `order` to reshuffle without either (a) restructuring
`AnalyzeSection.tsx` to split that fragment into separate primary
(word/meaning) and secondary (meta-tags/example) top-level children the way
Study already has, or (b) a `display: contents` promotion on
`.classify-word-card-content` to flatten its children into the outer grid
without touching JSX. (b) was seriously considered -- it would have been a
pure-CSS, zero-JSX fix -- but rejected: that same wrapper carries
`.app-slide-up`, a CSS `animation` that needs a real box to animate,
`display: contents` removes exactly that box, and this specific
animation-on-a-`display:contents`-element combination has a known history of
breaking (element/children flashing or failing to animate) in WebKit/Safari,
which this project must support. (a) is a real component restructuring, not
a "CSS-only or 1-2 classNames" change, so it clears this phase's bug bar but
not its implementation bar (1-3 files, no DOM restructuring, low QA burden).
Recorded here rather than patched: a future phase scoped like Phase 110's
two-pass structure (find in Round 0, fix in a dedicated follow-up round with
its own JSX-touching budget) should split `ClassifyWordCard` into flat
primary/secondary siblings of `.classify-actions` and reuse the exact
`order`-based mobile reorder Study already validated.

No other P2/P3s were found worth recording -- the ledger table
(`.classify-ledger`) remains appropriately plain (opt-in via a checkbox,
converts to labeled cards under 640px via existing `.classify-ledger
td::before` rules, matches the brief's explicit "don't over-decorate a
functional data table" instruction) and Shiori's presence (small corner
companion on the classify intro, a success stamp on both the result summary
and the Stats hero) is neither missing nor overused anywhere in these three
screens. `git status --short` is empty -- no functional code was touched
this phase; only this DESIGN.md entry and a throwaway, gitignored
(`*.db`) scratch sqlite copy (deleted after QA) were created. Given one real
P1 remains open, the Phase 54-110 redesign series should not be declared
fully closed yet -- but with Analyze/Stats/Feedback otherwise confirmed
in-world and every other screen already settled across Phases 93-110, a
single dedicated follow-up phase for the Analyze card-stage restructuring
(the item recorded above) should be enough to close it out.

Phase 112 fixed that P1: on 320-390px phones, `ClassifyWordCard` bundled
word/reading/quality-badge/meaning_ko *and* base_form/POS tags/example
sentence into one fragment rendered inside a single
`.classify-word-card-content` grid item, a sibling of `.classify-actions`
(the 4-way 아는/헷갈리는/모르는/건너뛰기 grid) rather than a parent of it --
so, unlike Study's already-flat `.study-answer-reveal` siblings, there was
no flat sibling set for a Phase-110-style mobile `order` rule to reshuffle
without either JSX restructuring or the banned `display: contents`.
`AnalyzeSection.tsx` now splits that one component into
`ClassifyWordPrimary` (word/reading/quality-badge/meaning_ko -- the minimum
needed to decide) and `ClassifyWordSecondary` (base_form/POS tags + example
sentence -- reference, not required for the decision), each wrapped in its
own `.app-slide-up`-animated div keyed independently
(`` `primary-${currentCardIndex}` ``/`` `secondary-${currentCardIndex}` ``
-- an early pass reused the same bare `key={currentCardIndex}` on both
sibling divs, which is invalid: React logged "two children with the same
key" and the resulting reconciliation confusion was masking real card
advancement in this session's own QA polling, caught and fixed before
anything shipped). Source/desktop order is unchanged --
`.classify-word-card`'s children are still progress, primary, secondary,
actions, nav, byte-for-byte the same sequence the old single-fragment
version produced -- so desktop (`>640px`, outside the mobile media query)
renders identically to before this phase. Only inside the existing
`@media (max-width: 640px)` block does `.classify-word-card .classify-actions
{ order: 1 }` and `.classify-word-card-secondary { order: 2 }` move the
decision grid ahead of the now-separate secondary block, the same order-only
technique Phase 110 validated for Study, plus a modest further tightening
this phase added on top (`.classify-word-card` gap 14px->8px and padding
16px->10px on this stage only, not `.classify-result-summary`; `.classify-
word` 38px->28px; `.classify-word-card .token-sheet-meaning-block` margin/
padding trimmed -- scoped to that ancestor so Reading's `TokenDetailSheet`,
which shares the same `.token-sheet-meaning-block` class, is untouched)
since the first order-only pass alone still left the grid's bottom edge
partially behind the fixed `.app-bottom-nav`.

Measured via `getBoundingClientRect()` against a scratch-SQLite backend
(same populated-account setup as Phase 111) at 1280/390/375/320, before and
after: at 390px the grid went from `top: 786.6` (already inside the nav's
own `783-844` span) to `top: 585` / `bottom: 765` -- fully clear, 18px above
the nav; at 320px, the narrowest and hardest case (more text wrapping at
that width pushes content lower than at 390px, so it needed the extra
tightening pass beyond the first order-only cut, which still left ~18px of
the grid's bottom edge behind the nav there), the final grid measured
`bottom: 782.1` against `nav top: 783` -- essentially flush, effectively
zero overlap. `overlap: false` / `gridFullyAboveNav: true` held at all three
mobile widths on both the first and second card in a session (re-measured
after one real classify click, not just the initial render).
`document.documentElement.scrollWidth === clientWidth` held at every width;
zero console errors/warnings after the key fix. Functional verification
(all via real clicks, no injected state): a full 7-token classify session
(아는/헷갈리는/모르는/건너뛰기 cycled across cards) correctly advanced the
displayed word every time and produced the exact expected tally; "모르는
단어 노트에 담기" correctly saved and returned "완벽히 아는 단어 2개,
헷갈리는 단어 1개, 모르는 단어 1개를 저장했습니다."; `ClassifyResultSummary`
and the ledger toggle were unaffected (neither component was touched).
Secondary content (POS tag, example sentence) still renders in full below
the grid on mobile, and the desktop card's screenshot-compared visual
rhythm (word/meaning -> tags/example -> grid -> 이전) is unchanged from
before this phase.

classify/save/status handlers, `currentCardIndex`/progress/result-summary
logic, and every backend/API/schema/SRS/storage/auth path are untouched --
this was a presentational split (one component into two, one CSS class
added, `order`/spacing rules added inside the existing mobile media query)
with no condition, callback, or data-flow change anywhere. `.rating-button`
itself was not touched; the only button-adjacent change was the pre-existing
Analyze-scoped `.classify-word-card` gap/padding tightening, which affects
spacing around buttons, not the buttons' own global rule.
Reading/Study/Vocab/Shared Deck were not touched (`.token-sheet-meaning-
block`'s override is scoped to `.classify-word-card`, and a Reading-tab
screenshot spot-check after the change confirmed no visible or console-level
regression there). Verified with `npm run build` (clean, twice -- once after
the JSX split, once after the final spacing pass) and `git diff --check`
(clean); `git status --short` shows only `frontend/app/globals.css` and
`frontend/components/AnalyzeSection.tsx`.

Remaining risk: the 320px clearance is a ~1px margin, not a generous buffer
-- a future token with an unusually long reading/meaning/POS combination
could theoretically push the grid a few px back into the nav's zone at that
exact width, though the same would have been true (far worse) before this
phase, and 375/390px carry a comfortable double-digit-px margin. No further
action recommended unless a real regression surfaces; chasing a larger
guaranteed-safe margin at 320px would mean shrinking `.classify-word`
further or touching `.rating-button` sizing, both of higher cost than this
phase's actual bug warranted. With this P1 resolved and Phase 111 already
confirming Stats/Feedback and Analyze's other three states (intro/result/
ledger) as non-issues, the Phase 54-112 casual-sticker-reader redesign
series can now be considered closed -- no further candidates are on record
across any screen.

Phase 113 reopened that "closed" conclusion specifically for the App
Shell: Phases 54-73 had progressively re-skinned the *existing* app
structure (a persistent `.library-rail` icon sidebar, a separate slim
`.app-topbar` strip, and a fixed 7-icon `.app-bottom-nav` on mobile) with
casual-sticker-reader materials -- tape, pin dots, a bookmark-tab active
state, a wood-desk `.page` board -- without ever replacing the structure
those materials sat on. Compared directly against the mockup boards
(`docs/design/mockups/casual-sticker-reader-{mobile,desktop}.png`), that
structure was the mismatch: the desktop board shows one rounded toolbar
(brand + every tab as a text link + search/settings/account) sitting
directly on the desk scene, not a sidebar beside it; every mobile board
shows only a two-icon top strip (☰ menu, a right-side icon) and *no*
persistent bottom tab bar at all -- Home's three shortcuts are page
content, not chrome. `.library-rail`, the old `.app-topbar`, and
`.app-bottom-nav` were deleted outright (not restyled) and replaced with
one navigation surface, `.app-toolbar` (`AppShell.tsx`, `globals.css`):
>=1024px renders brand + all 7 tabs as text links + feedback/account in a
single sticky pill row (the same "paper toolbar tag on the wood-desk
board" treatment the old `.app-topbar` had at this tier, just widened to
carry the tabs themselves); below that, seven full-label tabs no longer
fit one row, so they move into a new slide-in `.app-nav-drawer` opened by
a hamburger button, and the fixed bottom bar is simply gone -- reclaiming
the full viewport height for the reader/notebook content the mockup's
mobile boards show. This is a deliberate breakpoint change from the old
rail's 641px cutoff (icon-only, so it fit that width) to 1024px (full text
tabs need real room); noted directly in the CSS rather than left
implicit. `NavAction` gained an optional `shortLabel` so the toolbar can
prefer each tab's existing short `mobileLabel` (fits 7 in one row) while
the drawer, which has vertical space to spare, shows the full `label` --
one `navItems` array still drives both, so there is exactly one nav data
source, per the brief's explicit requirement to keep `activeTab`/
`handleTabChange` and the tab data flow unchanged. The redundant
"피드백" `NavAction` (previously rendered a second time inside the rail/
bottom-nav on top of its own dedicated topbar button) was dropped --
feedback is an action, not a screen, and now renders exactly once, in
whichever of `.app-toolbar-end`/`.app-nav-drawer-footer` fits the current
viewport. `HomeDashboard.tsx` was not touched -- its notebook-cover +
sticker-shortcut scene (Phase 54/67/73) was already reading as "the desk
scene itself," not old-shell card content, so once the rail/topbar/
bottom-nav chrome around it was replaced, Home needed no changes of its
own to match the mockup's board 1. Reading/Vocab/Study/Shared Deck
internals (`.panel-card`/`.hero-card`/`.desk-surface` conventions) were
explicitly out of scope for this phase and are unchanged -- spot-checked
only for "does the new shell break them," not redesigned.

Remaining old-shell traces, by design (deferred, not missed): the tab
*content* inside each screen still uses the pre-113 `.panel-card`/
`.hero-card`/`.desk-surface` card language the brief flagged as a
possible future target ("이번 phase에서 필요한 최소 영향만 확인") --
this phase only replaced the chrome around that content. A future phase
would need to judge whether those per-screen surfaces still read as
"old app card" now that the shell itself no longer does.

Verified with `npm run build` (clean) and `git diff --check` (clean, one
pre-existing unrelated CRLF warning on a `.claude/skills` file). Browser
QA via the project's raw-CDP-over-websocket harness (see
[[project_cdp_browser_qa_without_playwright]]) against a scratch-SQLite
backend, headless Chrome driven by Windows `node.exe`, at 1280/390/375/320:
1280px shows the unified toolbar with `.library-rail`/`.app-bottom-nav`
both absent, all 7 short tab labels present, clicking a tab switches
`activeTab` correctly (`단어` -> `.vocab-panel` present), and the
Phase 67 wood-desk board (`body` background `rgb(201,160,110)` =
`--desk-wood`, `.page` at `max-width:1228.8px`/`margin:20px 25.6px`/
`border-radius:28px`) measured intact via `getComputedStyle`/
`getBoundingClientRect`. 390/375/320px show the hamburger + account-only
top strip (no nav text, no bottom nav), the drawer opening with all 7 full
labels plus a footer feedback button, a drawer nav click both switching
tabs (`.reading-panel` present) and auto-closing the drawer, and 320px's
`<400px` brand-name-hiding safety valve engaging (toolbar measured
296px wide, comfortably inside the 320px viewport). Spot-checked Vocab,
Shared Deck, and a drawer-driven navigation sweep across 단어장/복습/덱 at
375px for "not broken after the shell swap" per the phase brief --
all rendered normally. `document.documentElement.scrollWidth ===
clientWidth` held at every width in every check, and zero console errors
or warnings were recorded across the full run. No backend/API/schema/SRS/
storage/auth/shared-deck code, and no `localStorage` payload, was
touched; `activeTab`/`handleTabChange` and every tab's own props/handlers
are unchanged -- this was a chrome/DOM-structure replacement only.

Phase 114 moved one level in from the shell Phase 113 replaced, into the
old card/panel primitives (`.panel-card`, `.hero-card`, `.desk-surface`,
`.desk-surface-section`, `.library-card-stage`, `.card-stack-surface`)
still used inside individual tabs. Round 0 surveyed every call site of
those six classes across Reading/Vocab/Shared Deck/Analyze/Study/Home/
Info and judged each Replace/Keep/Defer:

- **Replace, implemented this phase:**
  - `ReadingTab.tsx`'s `.reader-workspace.library-card-stage` (wrapped
    ReaderPaper + ReaderSaveDock + the candidate tray in a second bordered/
    shadowed "stage" box with its own dashed ring-spine, on top of the
    `.page` board's own paper texture underneath -- a card sitting on the
    board rather than the board's own content).
  - `ReaderMode.tsx`'s `.reader-paper.hero-card.card-stack-surface` --
    investigated first, since removing a hero-tier class from the screen's
    actual reading surface needed real justification, not just a name
    match. Found that `.reader-paper`'s own rule (declared later in
    `globals.css`, same specificity) already redeclares `border-radius`,
    `box-shadow`, and both `::before`/`::after` (tape corners) that
    `.hero-card`/`.card-stack-surface` set on the same element -- both
    classes were fully shadowed, contributing nothing visible at any
    breakpoint (confirmed via `Emulation`-driven `getComputedStyle` checks
    at 1280/390/375/320 before touching anything). Removed as dead-code
    cleanup with zero visual delta, not a redesign.
  - `VocabSection.tsx`'s `.panel-card.hero-card.vocab-hero-card
    .vocab-hero-compact.card-stack-surface` header (title, live stat
    chips, "이 덱 학습하기"/"원문 읽기"/"더보기") -- unlike the reader
    case, this one's `panel-card`/`hero-card`/`card-stack-surface` were
    fully live (border, radius, shadow, and a real 2-layer ghost card
    stack behind it), a genuine bordered box sitting above the Phase 68
    notebook spread. No mockup board shows a separate header card above
    the notebook scene, so it was flattened to a plain heading strip
    (`.vocab-hero-card` now just `display:grid; gap; border-bottom: 1px
    dashed` -- the same "unboxed section" recipe `.reading-input-open`
    already used post-analyze) sitting directly on the page. The stat
    chips/buttons/labels stayed exactly as they were -- 단어장 is one of
    the screens DESIGN.md's own "minimize numbers" principle exempts
    ("Exact counts still belong on the screens whose job is counting").
    `.vocab-hero-tape` (a washi-tape strip whose whole job was "hold this
    card down") was deleted outright rather than kept floating with
    nothing left to tape down -- an orphaned decoration is exactly what
    the phase brief's "장식보다 composition을 먼저 바꾼다" rules out.
- **Keep:** `.desk-surface`/`.desk-surface-section` wrapping Vocab's word
  list, and `.vocab-list.index-card-drawer.card-stack-surface` (the list
  itself) -- `.desk-surface` has no border/drop-shadow, only an inset
  radial-highlight tint (a page-surface material, not a boxed panel), and
  the brief explicitly preserves Phase 57's vertical scan list. Home's
  `.card-stack-surface` on `.home-notebook-cover`, and TokenDetailSheet's
  `.bookmark-inspector...card-stack-surface` -- both already mockup-
  aligned (Phase 54/65/67/73) and explicitly flagged in earlier phases as
  already juggling multiple pseudo-element consumers; out of scope here.
  Shared Deck's `.shared-deck-card.card-stack-surface` grid cards -- Phase
  41 already suppresses the ghost-stack layers there
  (`.shared-deck-grid .card-stack-surface::before,::after{content:none}`)
  in favor of one shelf-ledge line for the whole grid, so this was never
  a naive old-card instance to begin with.
- **Defer (same fix shape as Vocab's hero, not implemented this phase --
  scope discipline; the brief asks for 1-2 screens done well, not six
  done shallowly):** `SharedDeckSection.tsx`'s `.panel-card.hero-card
  .shared-hero-card.card-stack-surface` header -- checked, and it's the
  live/non-dead case like Vocab's was (`.shared-hero-card` only overrides
  padding/border-top-color, leaving `panel-card`'s border+`hero-card`'s
  shadow+`card-stack-surface`'s ghost layers all live), so it's a strong
  next candidate. `AnalyzeSection.tsx`'s `.classify-stage.hero-card
  .library-card-stage` and `.classify-word-card.card-stack-surface` --
  Analyze has no dedicated mockup board, so the brief calls for caution;
  not investigated deeply enough this phase to judge confidently.
  `InfoSection.tsx`'s `.panel-card.info-panel-card.study-log-policy-card`
  -- Stats/Info wasn't named in this phase's priority list either.
  Study's four `hero-card` call sites were left untouched per the brief's
  explicit instruction to protect the rating-stamp/board scene, which
  already reads close to the mockup.

Verified with `npm run build` (clean) and `git diff --check` (clean).
Browser QA via the same raw-CDP harness as Phase 113
(see [[project_cdp_browser_qa_without_playwright]]), scratch-SQLite
backend seeded with 3 real vocab items (via a small Node script issuing
raw UTF-8 HTTP POSTs to `/vocab-items` -- Windows PowerShell 5.1's default
encoding was mangling the Japanese/Korean JSON body, so `node.exe` was
used instead) so Reading/Vocab rendered real content, not just empty
states. At 1280/390/375/320: a DOM query for
`.reader-workspace.library-card-stage`, `.reader-paper.hero-card`,
`.vocab-hero-card.panel-card`, and `.vocab-hero-tape` returned none of
them anywhere, while `.desk-surface` remained present on Vocab as
expected (confirming the Keep judgment actually held in the running app,
not just in the diff). Screenshots confirmed the reader page now sits
directly on the wood-desk board with the pinned word inspector beside it
(no visible second "workspace" box around either), and Vocab's header
reads as page content above the notebook spread rather than a floating
white card. Loaded the reader via the real sample-text-load ->
analyze-submit flow (not injected state) and opened the desktop pinned
inspector by clicking a token, both working normally. `document.
documentElement.scrollWidth === clientWidth` held at every width, and
Home/Study/Shared Deck were spot-checked via real toolbar/drawer tab
clicks with zero console errors or warnings across the full run. No
backend/API/schema/SRS/storage/auth/shared-deck code or `localStorage`
payload was touched; the Phase 89/91 candidate-tray horizontal strips,
the Phase 94/100 mobile compact-inspector treatment, and the Phase 113
App Shell were all left exactly as they were (confirmed by the toolbar/
drawer still rendering and functioning identically in this same QA run).

Phase 115 picked up the two candidates Phase 114 left on the table:
`SharedDeckSection.tsx`'s hero header and `AnalyzeSection.tsx`'s
`.classify-stage`.

- **Shared Deck hero -- Replace, implemented.** Investigation confirmed
  this was the exact live pattern Phase 114 already suspected (flagged as
  a Defer candidate that phase, "confirmed same live pattern as Vocab's"):
  `.shared-hero-card` only overrode `padding`/`border-top-color`, leaving
  `panel-card`'s border, `hero-card`'s shadow, and `card-stack-surface`'s
  2-layer ghost stack all live and visible above the Phase 69 shelf scene.
  No mockup board shows a separate boxed header above a shelf, so it was
  flattened using the identical recipe Phase 114 used for Vocab: dropped
  `panel-card`/`hero-card`/`card-stack-surface`, kept `shared-hero-card` as
  a plain `display:grid` strip with `border-bottom: 1px dashed
  var(--paper-border)` (the same "unboxed section" language
  `.reading-input-open` established). `.shared-hero-tape` (a washi-tape
  strip whose only job was holding a now-gone card down) was deleted
  outright rather than left as orphaned decoration, same reasoning as
  Vocab's tape removal. Title, description, the "어휘 노트 보기"/
  "새로고침" actions, and the copyright info-strip are all unchanged
  content -- only the box around them is gone. `.shared-library-scene`,
  `.desk-surface-section` (the shelf's own inset-tint background, no
  border/shadow -- same Keep judgment Phase 114 gave Vocab's identical
  class), the shelf-section grouping, `.shared-deck-card`/
  `.selected-shared-deck-card` grid cards, and the opened-notebook detail
  panel (`.shared-deck-detail`) were not touched at all -- confirmed via
  `git diff` showing the change scoped to exactly one JSX line (the outer
  `<section>` className) plus deleting the tape `<span>`.
- **Analyze `.classify-stage` -- investigated, judged Keep (not Replace),
  with one safe cleanup.** Unlike the reader-paper and Vocab/Shared-Deck
  hero cases, this one doesn't reduce to a naive leftover: `.classify-stage`
  redeclares its own `background: panel-bg`/`border`/`border-top-accent`
  (added specifically, per its own existing comment, to replace
  `library-card-stage`'s duller striped fill with an opaque one matching
  `.study-hero-card`'s recipe "so every tab's top card reads as the same
  card system") but does *not* redeclare `border-radius` or `box-shadow`,
  so `.hero-card`'s contribution there is live and was put there on
  purpose for cross-tab consistency with Study's hero card (which Phase
  114 already left untouched as "already reads close to the mockup").
  Analyze has no dedicated mockup board to justify breaking that
  established consistency, so the box itself was judged Keep. What *was*
  dead: `.library-card-stage`'s own striped background, fully overridden
  by `.classify-stage`'s later, same-specificity `background` rule --
  confirmed via the same `getComputedStyle` method Phase 114 used on
  reader-paper. Dropped the classname as pure cleanup, zero visual change.
  The actual card-flip flow (`.classify-word-card.card-stack-surface`,
  reached once analysis completes) was investigated too and judged Keep
  outright: its border/radius/shadow are declared directly on the class
  itself (not inherited from `.hero-card`), so `card-stack-surface`'s
  ghost-stack layers are live and, unlike the reader page, thematically
  fit here -- a stack of cards behind the current one reinforces "more
  cards to flip through" in a flashcard flow. This element is also where
  Phase 112's mobile decision-grid ordering lives, so it was left
  completely alone per the phase brief's explicit regression ban; `git
  diff` confirms nothing below `ClassifyStageIntro`'s own opening tag
  changed.

Verified with `npm run build` (clean) and `git diff --check` (clean).
Browser QA via the same raw-CDP harness as Phase 113/114 (see
[[project_cdp_browser_qa_without_playwright]]), scratch-SQLite backend
seeded with one vocab item and one owner-published shared deck (via
`POST /decks/1/publish`, reached through raw Node HTTP calls for UTF-8
safety -- Windows PowerShell 5.1 mangled the Japanese/Korean JSON body in
Phase 114 too) so Shared Deck's owner-only "내가 공유함" state and a real
word count rendered, not just the empty/newcomer state. At 1280/390/375/
320: `.shared-hero-card.panel-card` and `.shared-hero-tape` were confirmed
absent from the DOM at every checked width while `.desk-surface` remained
present on the shelf as expected; `.classify-stage.library-card-stage`
was confirmed absent while `.classify-stage.hero-card` remained present
during the intro state and correctly gave way to a live
`.classify-word-card` once analysis completed (verified through the real
text-input -> "분류 카드 만들기" submit flow, not injected state; the
first 1280px attempt caught the request still in flight at the original
2.5s poll and needed a longer wait to confirm the same transition already
seen at 390px -- a QA-timing artifact, not a product issue, resolved by
re-polling at 6s). `document.documentElement.scrollWidth ===
clientWidth` held at every width, and zero console errors or warnings
were recorded across the full run. `git diff` on both changed components
confirms owner/subscriber/newcomer conditions, import/unpublish/
republish/`updateWordStatus` callbacks, and Analyze's classify/save/status
handlers were not touched by a single line -- both edits were scoped
entirely to one wrapper `<section>` className plus one deleted decorative
`<span>` each. Phase 112's mobile classify-grid ordering, Phase 113's App
Shell, and Phase 114's Reading/Vocab structure were all confirmed
unchanged in this same QA run (toolbar/drawer navigation, reader page,
and Vocab's flattened header all still rendering and functioning as
Phase 114 left them).

Remaining old-surface candidates for a future phase: none of the
originally-surveyed six classes have a confirmed-live Replace case left
outstanding. `InfoSection.tsx`'s `.panel-card.info-panel-card
.study-log-policy-card` (Stats/Info) was never investigated in Phase
114/115 and has no dedicated mockup board either -- lowest-priority
remaining candidate if a future phase wants to close out the full survey.

Phase 116 was a pure audit -- no code changed (`git status` before and
after is identical to Phase 115's end state) -- comparing every screen
against the two mockup boards side by side in a real browser, not just
re-reading the Phase 113-115 diffs. Judged each screen Match / Minor
residue / Structural residue / Protected divergence:

- **App Shell -- Match.** `.library-rail`/`.app-topbar`/`.app-bottom-nav`
  confirmed absent from the DOM at every checked width (1280/390/375/320,
  via direct `document.querySelector` checks, not just a visual read).
  Desktop toolbar reads as one rounded pill bar with brand+tabs+account,
  matching mockup board 1's toolbar; mobile shows only the hamburger +
  account-icon strip mockup boards 1-6 all share, no generic bottom tab
  bar anywhere. `getBoundingClientRect()` on the sticky toolbar confirmed
  no overlap with page content at any width (e.g. 1280px: toolbar
  `top:46/bottom:102`, page content starts clear of it).
- **Home -- Match.** Notebook cover + 3 sticker shortcuts render as one
  continuous desk scene directly under the toolbar (no visible seam
  between shell and content); shortcuts keep their Phase 77 per-chip
  asymmetric tilt/corner treatment, reading as loose notes rather than a
  uniform 3-up card grid.
- **Reading -- Match.** Screenshotted with a real analyzed result and the
  desktop pinned inspector open (clicked a token, not injected state): the
  reader page now sits directly on the board with no visible second
  "workspace" box around it (Phase 114), closely matching mockup board 2's
  open two-page-plus-note layout. Mobile compact inspector still shows
  ~55% of the reader text above the sheet per Phase 94/100 (screenshot
  confirms word/meaning/status visible above the fold, unchanged this
  phase). `ReadingVocabPanel.tsx` (the Phase 89/91/101 candidate-tray
  strips) was not touched by any of Phase 113-116's diffs -- confirmed by
  `git log`/`git diff` scope, not just visual inspection.
- **Vocab -- Match.** Flattened header (Phase 114) reads as page content
  leading straight into the filter-index/list/detail notebook spread
  (Phase 68/87), closely matching mockup board 3's open notebook. Detail
  panel screenshotted with a real selected word (품사/복습 레벨/문맥 예문/
  수정/삭제 all present and functioning) -- the dense vertical list itself
  (Phase 57's deliberate choice for a 20-50-row Operate screen) is
  unchanged and was not pushed toward a sticker grid.
- **Shared Deck -- Match.** Flattened header (Phase 115) leads into the
  Phase 69 wood-cabinet shelf scene; screenshotted with a real
  owner-published deck ("내가 공유함" badge, 단어 5개, "상세 보기") showing
  the shelf card reads as one shelf item, not a second admin list.
- **Study -- Match, and the closest of any screen to its mockup board.**
  Screenshotted with a real revealed answer + the 4-way rating grid (아는
  단어 학습 quick-start -> "정답 보기", not injected state): dark felt
  board, card stack, and the 다시/어려움/보통/쉬움 stamp colors line up
  almost exactly with mockup board 4's Review panel, both in desktop's
  2x1 row and mobile's 2x2 grid. Untouched this phase per the brief's
  explicit protection, and confirmed still untouched by inspection.
- **Analyze -- Protected divergence, confirmed still reads coherently.**
  No dedicated mockup board exists for this screen. Phase 115's Keep
  judgment (the intro card's border-radius/shadow are a deliberate,
  documented match to `.study-hero-card`'s "same card system," not a
  leftover) was re-checked against the running app rather than just the
  diff: the intro card, the card-flip flow, and the coral tally sidebar
  all read as part of the same warm-paper visual world as every other
  screen, not as a dropped-in admin form. No change made.
- **Stats/Info -- Match (with one small, deliberately out-of-scope
  residue).** The brief asked specifically whether "Stats/Info hero" was
  the last old-card trace; investigation found the actual page-top hero
  (`StudyLogHero`, rendered via `.reading-hero`) was *never* part of the
  `panel-card`/`hero-card` family to begin with -- `.reading-hero` is
  `display:grid; gap:4px; padding:2px 2px 4px` with no border/background/
  shadow of its own, already a flush, unboxed heading (same "just text on
  the page" shape every other screen's header was flattened *toward* this
  phase). The only surviving `panel-card` instance on this screen is a
  small "저장 정책" disclosure note at the very bottom of the page, below
  the main journal/log content -- and DESIGN.md's own Phase 60 record
  shows this was already deliberately reduced to the *lightest* card
  treatment in the app (dropped an admin-callout colored-left-border for
  a plain card + one corner fold) rather than being an untouched
  leftover. Judged **Minor residue**: a real `panel-card` instance exists,
  but it is low-visual-weight, secondary, already-minimized, and outside
  this phase's investigated priority list -- left as a candidate for
  whichever future phase finally closes out the six-class survey
  (grouped with `.classify-word-card`'s sibling `.classify-result-summary`
  if that phase also revisits Analyze), not fixed here since fixing it
  would mean investigating and redesigning a screen this phase didn't
  scope to touch, not a "small CSS/DOM defect."

**How much the "mixed old/new" problem has shrunk:** every screen the
user can reach through the primary navigation (Home, Reading, Vocab,
Study, Shared Deck) now renders zero instances of the six flagged
old-surface classes in their *primary* content -- the only surviving
instances anywhere in the app are Analyze's intentionally-kept hero/card
(a deliberate cross-tab consistency choice, not residue) and one small
secondary policy note on the Stats tab. Going by screen count: 5 of 7
tabs are a clean Match, 1 (Analyze) is a reasoned Protected divergence,
and 1 (Stats) is a Match with a single Minor residue element. No screen
came back Structural residue.

No build was needed (no code changed), but `npm run build` was re-run
anyway to confirm the cumulative Phase 113-115 state still compiles clean
-- it does. Browser QA via the same raw-CDP harness (see
[[project_cdp_browser_qa_without_playwright]]), scratch-SQLite backend
seeded with 5 vocab items across 4 statuses and one owner-published
shared deck, at 1280/390/375/320: `document.documentElement.scrollWidth
=== clientWidth` held at all 15 checked screen/state combinations, zero
console errors or warnings across the entire run, and zero instances of
`.library-rail`/`.app-bottom-nav` found at any width. All six required
screenshot states were captured through real interaction (sample-text
analyze, token click for the inspector, deck-select for Vocab, quick-start
+ "정답 보기" for Study's revealed/rating state, text-submit for Analyze's
card) rather than injected component state.

**Commit-readiness:** yes -- this phase made no code changes, so there is
nothing new to review beyond what Phase 113-115 already left staged; this
entry is a verification record, not a diff.

**Next phase candidates, in priority order:** (1) none required to reach
mockup parity on the primary nav -- the redesign's stated goal is met;
(2) optional polish-only candidate: Stats/Info's bottom "저장 정책" card,
if a future phase wants zero remaining `panel-card` instances anywhere in
the app; (3) optional: revisit Analyze's card system only if/when a
dedicated mockup for that screen is ever produced, since without one
there's no direction to redesign toward.

Phase 124 was a bridge test, not a final asset kit: by Phase 123, Home and
Reading matched the mockup's *structure* (composition, hierarchy, spacing)
but several small decorations were still visibly "CSS pretending to be a
material" -- a flat rotated rectangle standing in for Home's leather
closure strap (`.home-cover-strap`, a straight `linear-gradient` bar with
a filled-circle snap), and a plain filled-circle pin standing in for
"something holding the sticky note down" (`.home-cover-pin`). Both read as
geometry, not stationery, next to the mockup's hand-drawn strap/tape.
Desk props, the reader binding/spine (Phase 122), and the notebook cover's
own gradient were judged to already read acceptably as CSS gradients/
shapes and were left alone -- this phase deliberately touched the fewest
things that would prove the point, not everything the brief's candidate
list named.

No image-generation tool is available in this environment, so the
"generate 3-6 PNG candidates" instruction as literally written wasn't
achievable; confirmed with the user, who redirected to hand-authored SVG
instead (`frontend/public/brand/decor/`) -- vector, transparent, no text
baked in, decorative-only, applied as an addition/replacement for the
existing CSS-only decoration rather than any functional UI. Two assets
were built and adopted: `leather-strap-snap.svg` (a tapered, hand-cut
strap shape with dashed hand-stitch lines and a shaded/highlighted snap,
applied via `background-image` + `background-size: 100% 100%` on the
existing `.home-cover-strap` span -- position/size/rotation unchanged,
only the fill mechanism) and `washi-tape.svg` (a small torn-edge,
semi-transparent tape strip with faint fiber lines, added as a new `<img
aria-hidden alt="">` inside `.home-cover-sticky`, replacing
`.home-cover-pin`). Both are under 2KB.

QA surfaced one real bug worth recording for future asset work: an
`<img>` pointed at an SVG with `width:46px; height:auto` in CSS rendered
as a ~5px sliver instead of erroring -- this Chromium build doesn't
reliably resolve an `<img>`'s intrinsic aspect ratio from an SVG source
for `height:auto` sizing, even with explicit `width`/`height` attributes
on the SVG root (`naturalWidth` read back as 0 despite the network
request succeeding with the correct `image/svg+xml` content-type, and
despite the element visually occupying space). It does not fail loudly,
so a naive `alt`/error-log check would have missed it -- only a
`getBoundingClientRect()` size check against the expected aspect ratio
caught it. Fixed by setting both `width` and `height` explicitly in CSS
(`46px` / `16px`, matching the SVG's own 84:30 ratio) instead of trusting
`height: auto`. Any future `<img>`-embedded SVG on this project should
size both axes explicitly in CSS rather than relying on intrinsic-ratio
`auto` sizing.

Candidate judgments against the brief's list: **Adopt** --
leather-strap-snap (clear, visible material improvement, screenshot-
confirmed both directly and in the before/after comparison), washi-tape
(subtle but real once correctly sized; a genuine torn/deckled edge is not
achievable with CSS `border-radius` alone). **Prototype only** -- a
sticker-note-set for the candidate tray's expanded word list (flagged
separately in Phase 123 as a Design Gap: the tray reads as a flat card
grid, not the mockup's playful rotated stickers) and an
inspector-note-paper texture for `TokenDetailSheet`/`.bookmark-inspector`
-- both plausible next targets but not exercised this phase, since the
brief scoped this round to one screen. **Defer** -- binding-spine-texture
(Phase 122 already gave the reader spine real gutter-shadow/stitch/rivet
depth via layered CSS gradients + one small SVG-free brass fastener; an
image asset there would replace something already judged to work, not fix
a gap) and notebook-cover-texture (the cover's own sage-green gradient
already reads as fabric/paper reasonably well at every size tested; no
evidence a texture PNG/SVG would look different enough to justify the
added asset to maintain). **Reject** -- none outright; nothing tested
made the screen worse, heavier, or less responsive.

Verified: `npm run build` clean, `git diff --check` clean, both SVGs load
(200, correct `image/svg+xml` content-type, confirmed via direct fetch
and via `getBoundingClientRect()` matching the intended rendered size) at
1280/390/375/320 with zero `scrollWidth`/`clientWidth` mismatch and zero
console errors/warnings. `elementFromPoint()` on the exact center of both
decorative elements resolved to `.home-cover` underneath in every case
(`isSelf: false`), confirming `pointer-events: none` fully passes clicks
through -- neither asset can ever intercept a tap. Home's CTA (-> Reading
tab), mobile drawer, account trigger, and feedback slot were all
re-confirmed reachable and functional after the change. Reading was not
touched this phase (no files under `frontend/components/Reader*.tsx`
modified), so no Reading-specific regression risk exists to check.

**Files changed:** `frontend/app/globals.css`, `frontend/components/
HomeDashboard.tsx`, plus two new files: `frontend/public/brand/decor/
leather-strap-snap.svg` and `frontend/public/brand/decor/washi-tape.svg`.

**Commit-readiness:** yes -- build and diff-check clean, before/after
screenshots confirm a real (if intentionally small) material improvement
on Home with zero functional regression.

**Next phase candidates:** candidate-tray sticker restyling (toward the
mockup's rotated playful stickers -- likely the highest-leverage next
asset target, per Phase 123's own Design Gap finding) and an inspector
note-paper texture for `TokenDetailSheet`, both deferred rather than
attempted here since this phase's job was to validate the SVG-asset
approach on one screen first, not to roll it out everywhere at once.

Phase 125 applies the first raster asset-kit pass to the Reading candidate
tray, specifically the Phase 123 Design Gap where the expanded list still
read as a flat white card grid. Three generated, text-free paper textures
were adopted under `frontend/public/brand/decor/`:
`sticker-paper-coral.png`, `sticker-paper-sage.png`, and
`sticker-paper-blue.png`. The original generated files were downsampled to
384px-wide optimized PNGs before entering the repo (about 130-180KB each),
because these are small card backgrounds rather than full-bleed art.

The implementation keeps the real word buttons, checkbox pins, status
badges, save logic, search/filter/quick-select controls, and tray layout in
HTML/CSS. The images provide only the paper material for
`.reading-vocab-sticker`, varied by `nth-child` alongside asymmetric
corners, slightly stronger note tilt, and the existing `washi-tape.svg` as a
small non-interactive tape mark. No text is baked into any image. The goal is
not a photoreal sticker pack, but a visible move away from the flat list-app
card surface toward the mockup's handmade sticker-note language.

Phase 126 moves from small decorative accents (Phase 124's SVGs, Phase
125's tray stickers) to using generated raster images as the dominant
surface of Home's cover and Reading's page/book, replacing CSS
gradients/shapes that Phase 123's own strict QA still judged as
"developer-CSS-simulated" rather than a real physical object. Six WebP
candidates were supplied under `frontend/public/brand/decor/phase126/`
(with source PNGs alongside, unused). Judgments: **Adopt** --
`book-cover-green-surface-web.webp` (a photographed dark-olive cloth
cover texture, spine crease visible near the left edge -- exactly the
"one dominant object" Home's cover needed instead of a two-stop
gradient), `open-book-spread-web.webp` (a photographed two-page ruled
spread with deckled edges and its own soft center crease -- used for both
`.reader-desk-scene` and `.reader-start-scene` at >=1024px), and
`paper-page-texture-web.webp` (plain cream ruled paper, no baked-in
edges -- used for every mobile/input page surface: `.reader-paper` below
1024px, `.reader-start-page textarea`, and the mobile
`.bookmark-inspector` modal card). **Defer** --
`book-cover-green-object-candidate-web.webp` (has a background
vignette/crop the brief flagged as unresolved -- noted as a follow-up
crop candidate, not applied), `sticky-note-set-candidate-web.webp` and
`desk-prop-set-candidate-web.webp` (both need cropping/masking before
they're usable as single decorative elements -- explicitly out of scope
this phase per the brief), `deck-cover-template-candidate-web.webp`
(reserved for a future Shared Deck pass, never in scope here). **Reject**
-- none; every adopted asset was a clear improvement with no legibility
or performance cost.

Home: `.home-cover`'s old `linear-gradient(165deg, var(--notebook-cover),
var(--notebook-cover-deep))` is now `book-cover-green-surface-web.webp`
as a `background-image` layer, with a second `linear-gradient` layer
(dark-to-transparent wash, top-left) stacked above it purely to protect
the title/subtitle's legibility over the photo's texture variance --
`background-color: var(--notebook-cover-deep)` stays as a same-family
fallback if the image ever fails to load. Also removed: the
`.card-stack-surface` class on `.home-cover` (ghost "stack of cards
behind this one" pseudo-element layers). That effect was written for a
flat CSS card that needed a fake-physicality illusion; kept on a real
photographed book-cover object, it would have produced exactly the
"card on top of a card" look this phase's success criteria explicitly
rules out, so it was dropped rather than layered under the photo.

Reading desktop (>=1024px): `.reader-desk-scene` and `.reader-start-scene`
both now use `open-book-spread-web.webp` as their background (previously
flat `var(--paper-bg)`), so the reader/inspector columns and the
pre-analysis textarea all sit as live content on top of one photographed
open book rather than a paper-colored box. This surfaced a real conflict:
Phase 122's `.reader-inspector-rail::before` drew its own CSS gutter
shadow (a 3-layer gradient band) at the grid's actual column boundary
(~73% of the scene width, since the layout is an asymmetric
`minmax(0,1fr) minmax(300px,340px)` split, not a symmetric 50/50 page
split) -- but the photo's own center crease sits at 50% of the image,
which maps close to the *middle* of the wide text column once
`background-size: cover` stretches it to the box (confirmed by computing
`.reader-desk-scene`'s actual `getBoundingClientRect()` and the image's
1183:793 source ratio: horizontally the photo maps ~1:1 to the box, only
cropped vertically, so its crease lands well inside the text column, not
at the grid boundary). Keeping the old CSS gutter shadow at the grid
boundary on top of the photo's own unrelated crease would have read as
two competing seams. Removed the `::before` gradient band entirely;
kept the stitch-tick `::after` and the brass `.reader-spine-clip`
fastener, since both are small discrete hardware objects, not a
background band, and layer over the photo correctly regardless of where
its crease falls. Checked directly via a scaled/clipped screenshot: the
photo's crease falls in blank page space to the right of the (left-
aligned, short-line) Japanese text, never crossing live text -- no
legibility cost. `.reader-paper`'s old `repeating-linear-gradient` ruled-
line background is now `none` at >=1024px (the shared scene background
already supplies real ruled lines) and `paper-page-texture-web.webp`
below 1024px, where there is no shared photo behind it yet.

Reading mobile (<1024px): `.reader-paper` (the original-text surface),
`.reader-start-page textarea` (the pre-analysis input page), and the
`.bookmark-inspector` base rule (the mobile/tablet inspector modal, which
previously used a flat `var(--panel-bg)` fill) all now use
`paper-page-texture-web.webp`. The inspector modal keeps its own
`.card-stack-surface`/`.paper-corner` chrome untouched (a floating sticky-
note-lifted-off-the-page look is a deliberate, different design goal from
Home's single-dominant-object cover, so it wasn't judged to conflict) --
only its flat background color changed to the photographed paper. The
Phase 125 candidate-tray sticker-paper PNGs were left exactly as they
were; nothing from this phase's asset set was mixed into that surface.

Every `background-image` added this phase pairs with an explicit
`background-color` fallback (the CSS variable the old flat/gradient fill
used to be) so a failed image load degrades to the prior look rather than
a broken or blank box, per the brief's explicit requirement.

Verified via headless Chrome (Windows-native, CDP) at 1280/390/375/320:
`npm run build` clean, `git diff --check` clean, zero console
errors/warnings, zero `scrollWidth`/`clientWidth` mismatch at any
viewport. All six referenced assets (`book-cover-green-surface-web.webp`,
`open-book-spread-web.webp`, `paper-page-texture-web.webp`, plus the
Phase 124 SVGs and Phase 125 sticker PNGs, still in use elsewhere on the
same screens) returned 200/304, no 404s. Exercised the full functional
path with no policy/API changes needed: Home -> "원문 읽기 시작" CTA ->
Reading start scene -> sample text -> `/analyze` -> 13 rendered tokens ->
token click -> inspector opens with real meaning/stamps/example data ->
candidate tray opens (13-word sticker grid, Phase 125's own asset
untouched) -- all confirmed working at both viewport tiers. No files
under `backend/`, no SRS/storage/auth logic, and no Shared Deck code were
touched.

**Files changed:** `frontend/app/globals.css`,
`frontend/components/HomeDashboard.tsx`, plus one new directory:
`frontend/public/brand/decor/phase126/` (the three adopted WebP files;
source PNGs and deferred-candidate WebPs sit alongside them, unreferenced
by any CSS).

**Commit-readiness:** yes -- build and diff-check clean, full browser QA
passed at all four required viewports with zero regressions found.

**Next phase candidates:** the deferred `book-cover-green-object-
candidate-web.webp` once cropped/vignette-fixed (a standalone book object
for use elsewhere, e.g. a smaller card treatment), and
`sticky-note-set-candidate-web.webp`/`desk-prop-set-candidate-web.webp`
once cropped/masked into individual usable pieces -- both explicitly
deferred this phase rather than attempted under time pressure with a
"crop later" asset.

Phase 128 applies Phase 127's Shared Deck asset pair -- a 5-cover book
atlas and a photographed wood shelf strip -- to promote `BrandDeckCover`
and `.shared-library-scene` from CSS-simulated surfaces to real
photographed material, since the prior thin color-ribbon cover band still
read as a UI card with a colored header, not a shelved book.

`BrandDeckCover` (BrandElements.tsx) keeps its `tone`/`level`/`Icon`/label
resolution logic completely unchanged; the only JSX change is wrapping the
icon+label in a new `<span className="brand-deck-cover-tag">` so they can
sit as a small pinned plate on the cover instead of stretching across a
thin ribbon. `.brand-deck-cover` (globals.css) goes from a ~30px-tall
`margin:-16px -16px 0; padding:9px 16px` ribbon to a full portrait book
cover via `aspect-ratio: 335/405` (matching the atlas's own per-cover cell
size) with `shared-deck-cover-set-candidate-web.webp` as its
`background-image` -- the photo is now the card's dominant surface, not a
strip above the "real" white card content.

Cropping one of the atlas's 5 covers per tone/level modifier uses the
standard CSS background-position-as-sprite-sheet technique, solved from
the atlas's actual measured geometry (1399x933px, ~335x405px per cell,
found via `file` on the webp -- not eyeballed): shared
`background-size: 417.6% 230.4%` (`= atlas_px / cell_px` in each axis) on
the base rule, then each modifier sets only `background-position`, computed
as `cell_left_px / (atlas_px - cell_px) * 100%` per axis. This only
produces an undistorted crop because `aspect-ratio` forces the container's
own aspect to match one cell's aspect ratio -- confirmed correct on the
first attempt via an isolated 7-variant test page (all 5 JLPT levels +
mine/shared) screenshotted side by side, each showing exactly one cover
with zero bleed from its neighbors. The atlas's 5 covers (sage green,
cream, dusty blue, coral, mustard) don't share one hue family the way the
old N5->N1 gradient ramp did; a real shelf of books doesn't either, so
N5..N1 each get a distinct cover (cream/sage/mustard/coral/blue) instead
of a monochrome progression, and "내가 공유함"/"공유 덱" reuse two of the
five (sage, blue) rather than needing new photos -- safe since a tone
cover and its level-tier photo-double never render in the same shelf row
(tone-based decks have no JLPT level, so they never enter the leveled
shelf). Each modifier keeps a flat `background-color` fallback (the old
gradient's start color) if the atlas fails to load.

The icon+label itself moved into `.brand-deck-cover-tag`: a small pill
with a solid `rgba(28,22,12,0.62)` dark backing (not just a text-shadow),
pinned to the cover's bottom-left corner -- needed because the atlas's 5
cover colors range from pale cream to dark blue, and a fixed-contrast
plate reads reliably over any of them where white text + shadow alone
would not have on the cream cover.

`.shared-library-scene` (>=1024px cabinet backdrop) swaps its
`linear-gradient(165deg, var(--desk-wood), var(--desk-wood-deep))` for
`shared-shelf-wood-strip-web.webp` (`background-size: cover`), and
`.shelf-section`/the ungrouped fallback `.shared-deck-grid` (the lighter
"compartment" recessed inside that cabinet) get the *same* wood photo with
a light warm wash layered on top via a second `linear-gradient` background
layer, preserving the existing "lighter interior shelf inside a darker
cabinet" depth cue the old flat `var(--panel-bg)` fill gave for free.

One real bug caught mid-QA: the first version of that wash used
`rgba(253, 249, 238, 0.72)` -- far too strong. A zoomed screenshot of a
gap area next to the deck cards showed a flat, cool pink-gray wash with
almost no visible wood grain, not the "lighter wood" look intended.
Isolated in a standalone test page (two boxes, same image, one with the
wash and one without) to confirm the wood photo itself was loading and
rendering correctly (it was -- the bare box showed clean, correct
wood-grain) and that the problem was purely the wash's alpha value.
Dropped to `0.3`, re-verified: the compartment now reads as real,
visibly-grained wood, distinctly lighter than the cabinet around it.
Documented here since the same "an overlay meant to be subtle instead
washes out the whole photo" failure mode is easy to reintroduce on any
future wood/paper-photo compartment.

`.shared-deck-card`'s own border/box-shadow/background were deliberately
left untouched -- the grid-scoped `:not(.selected-shared-deck-card)`
override already softened them in Phase 41, and once the cover grew from
a thin ribbon to a full portrait photo, the white meta/button area
underneath shrank from being most of the card to a small strip at the
bottom on its own, achieving the "meta/buttons read like a small label in
front of the shelf" goal without needing new CSS for it.

Verified via headless Chrome (Windows-native, CDP) at 1280/390/375/320
against real seeded data (a registered owner account with a published
deck, and a second account viewing/importing it as a non-owner) rather
than only the empty state: `npm run build` clean, `git diff --check`
clean, zero console errors/warnings, zero `scrollWidth`/`clientWidth`
mismatch at any viewport. Both `shared-deck-cover-set-candidate-web.webp`
and `shared-shelf-wood-strip-web.webp` returned 200, no 404s anywhere.
Real (not just `elementFromPoint`) button clicks confirmed working through
the photographed covers at both 1280 and 390: opening/closing the detail
panel via "상세 보기"/"상세 닫기" toggled `.selected-shared-deck-card`
correctly, and owner-only ("공유 취소"), non-owner-importable ("학습
목록에 추가"), and already-imported ("학습 목록에 있음") card states all
rendered with their correct copy and buttons -- none of that condition
logic in SharedDeckSection.tsx was touched. No files under `backend/`
were modified; no SRS/storage/auth/shared-deck-policy logic changed.

**Files changed:** `frontend/app/globals.css`,
`frontend/components/BrandElements.tsx`. No new asset files -- both used
Phase 127's already-committed `frontend/public/brand/decor/phase127/`
assets directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser QA
against real seeded owner/subscriber data passed at all four required
viewports, one real bug (the overlay wash) found and fixed before
shipping.

**Next phase candidates:** `vocab-ring-notebook-spread-web.webp` for
`.vocab-notebook-scene` (Phase 127's own manifest names this as the next
highest-priority target) and the Study felt-board/flashcard-stack pair --
both untouched this phase, which stayed scoped to Shared Deck only.

Phase 129 applies `vocab-ring-notebook-spread-web.webp` (1399x933 --
colored index tabs down the left page edge, a metal ring spine, a right
page with its own baked-in "clipped card" of folded corners + a red rule
line) to the desktop Vocab notebook spread, per Phase 127's own manifest
naming it the next target after Shared Deck.

Round 0 measured the image against `.vocab-notebook-scene`'s actual
3-column grid (`minmax(150,190) minmax(280,1fr) minmax(260,320)`) and
found a structural mismatch Reading/Shared Deck didn't have: those scenes'
boxes stay close to the source photo's own aspect ratio, but Vocab's
middle list column can run to 50+ rows (far taller than the image's
933:1399 aspect), so a single `background-size: cover` across the whole
scene would badly crop the tabs/card out of view to show mostly a thin
vertical sliver near the ring/spine. Rather than force the image into that
mismatched box, the phase splits the application per-column, directly
answering the brief's own three Round-0 questions with a deliberate
architecture instead of one blanket placement:

- **"이미지 왼쪽 탭 영역이 실제 filter/index와 맞는가?"** -- yes, by
  design: a zoomed crop (`background-size: 480% auto`, tuned by
  screenshot) of the image's own left edge is applied directly to
  `.vocab-notebook-index`, whose content (the deck/search/sort filter +
  status tabs) is naturally bounded in height, unlike the list.
- **"이미지 중앙 링/스파인이 실제 list column을 방해하지 않는가?"** --
  yes, because the ring/spine is never placed anywhere near the list
  column: `.vocab-notebook-pages`/`.index-card-drawer` deliberately do NOT
  carry the photo at all. This was a direct, conservative choice for the
  brief's own explicit scan-safety warning ("Vocab은 Operate 화면이다...
  스캔성이 깨지면 실패다") -- the safest way to guarantee a dense,
  scannable list is never fought by a busy photographic texture is to not
  put one there. The list instead sits on the shared scene's flat
  `var(--paper-bg)` frame (same tone as the photo's own page color), so it
  still reads as "more of the same paper" without literally showing the
  image.
- **"이미지 오른쪽 clipped page가 detail panel과 맞는가?"** -- yes, and
  applied to `.vocab-notebook-detail` itself (not the parent scene) for a
  reason specific to this column: it's `position: sticky`, so as a long
  list scrolls past, the panel stays pinned near the viewport top while
  the *scene's own* background (painted once, scrolling normally with
  the page) would long since have scrolled out of view by the time the
  user is deep in a 50-word list. Painting the card crop on the sticky
  element itself means it stays visually correct at any scroll position,
  not just near the top of the page.

Each of the three photo-backed surfaces keeps a flat `background-color`
fallback (the same tone the old CSS recipe used) if the image fails to
load, per the brief's explicit requirement.

CSS-only decoration removed for directly duplicating what the photo now
supplies: `.vocab-notebook-index .index-card-filter`'s cascading 3-color
`::after` (a `box-shadow`-drawn stack simulating page-edge tabs) is gone
-- the column now has real photographed tabs behind it, and the CSS
stand-in next to the real thing read as two competing tab motifs in one
column. The washi-tape corner `::before` on the same element stays (a
different "pinned note" cue, not a second tab simulation, so it doesn't
conflict). `.vocab-notebook-detail`'s own repeating-gradient ruled-line
background, border, and box-shadow are all dropped -- the photo's own
baked-in card edges are the card now, and a second CSS-drawn rectangle
around the same element would just be an outline a few px off from the
photo's own unrelated corners. The paperclip pseudo-elements
(`::before`/`::after`) stay; they're small hardware, not a background
band, so they layer over the photo fine. `.vocab-desk-empty`'s repeating-
gradient (fake ruled lines for the "no deck picked yet" state) is
simplified to `background: none` -- the shared scene frame already
supplies the page tone directly behind it now.

The one "image background pasted over an unchanged bordered panel"
failure mode the brief explicitly bans was caught in two places and fixed
before it shipped, not after: `.vocab-notebook-pages`'s own `.desk-surface`
class (shared with Study/SharedDeckSection, so overridden with a scoped
`.vocab-notebook-pages .desk-surface` selector rather than edited
directly) carries a tan radial-gradient + inset-shadow "resting on a desk"
tint at every screen that uses it: left as-is, its opaque fill would have
sat as a second panel directly on top of the scene's new paper frame,
hiding it completely behind the list. `.index-card-drawer` (the tinted
box wrapping the row cards, `var(--soft-bg)`) had the same problem for
the same reason. Both go transparent under `.vocab-notebook-pages`
specifically (>=1024px only), letting the scene's flat paper tone show
through the gaps between rows, while the individual `.vocabulary-index-
row` cards -- the actual scan aid -- stay fully opaque and completely
untouched.

`.vocab-notebook-index .index-card-filter`'s own background also needed
one legibility pass mid-QA: a first attempt at `rgba(255, 252, 240, 0.55)`
(a translucent cream wash, protecting the small label text sitting
directly on it) washed the photographed tab colors out almost
completely -- a zoomed screenshot of just that column showed barely any
color. Dropped to `0.22`, re-verified: the tabs now show as faint but
genuinely visible colored slivers at the column's left edge, and the
filter labels stay legible. Smaller version of the same "overlay meant to
be subtle instead hides the photo" mistake Phase 128's wood-shelf
compartment made (there at `0.72`, fixed to `0.3`) -- worth remembering as
a recurring failure mode across every phase that layers a legibility wash
over a photographed surface: start much lower than seems necessary and
verify with an actual zoomed screenshot, not by eye on the full-page shot.

No TSX changes were needed this phase -- every change is CSS-only
(`frontend/app/globals.css`); `VocabSection.tsx`'s row/filter/CRUD/deck-
management markup, handlers, and conditions are byte-for-byte unchanged.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account (15 real vocab items across a mix of all 4 statuses, a second
deck) rather than only the empty state, at 1280 (desktop spread),
1024 (the exact breakpoint, confirms the 3-column grid activates
correctly right at the boundary), 900 (tablet, confirms it correctly
stays the plain pre-existing single-column layout below 1024, no photo),
and 390/375/320 (mobile, same confirmation): `npm run build` clean,
`git diff --check` clean, zero console errors/warnings, zero
`scrollWidth`/`clientWidth` mismatch at any viewport tested.
`vocab-ring-notebook-spread-web.webp` returned 200, no 404s. Exercised
real interaction, not just a static screenshot: search filtered 15 items
down to 1 correctly, a status filter chip toggled correctly, the desktop
detail panel opened with real content (word/reading/meaning/status/tags/
review-meta/example/actions) via a real row-toggle click, the no-deck-
selected empty state rendered correctly on the shared frame, and the
덱/공유 관리 disclosure opened with a real, focusable, typeable input
field. Two `elementFromPoint`-based click-blocking checks that initially
came back `null`/`false` were re-verified with `scrollIntoView()` first
and confirmed to be viewport-scroll artifacts, not real blocking --
following up with an actual `.click()` + a small delay for React's
(batched, not synchronous) re-render showed both the status `<select>`
and the detail panel's "수정" button work correctly, opening the real
inline edit form. No files under `backend/` were touched; no SRS/storage/
auth/shared-deck-policy logic, and no Vocab CRUD/deck-management handler
or condition, changed.

**Files changed:** `frontend/app/globals.css` only. No new asset files --
reused Phase 127's already-committed
`frontend/public/brand/decor/phase127/vocab-ring-notebook-spread-web.webp`
directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser QA
against real seeded data passed at all six required viewports/breakpoints,
one real legibility bug (the 0.55-alpha wash) found and fixed before
shipping, scan-density/list-behavior confirmed unchanged from before this
phase.

**Next phase candidates:** Study's felt-board texture
(`study-felt-board-texture-web.webp`) and flashcard-stack candidate
(`study-flashcard-stack-candidate-web.webp`) are the last unapplied pair
from Phase 127's asset set -- untouched this phase, which stayed scoped to
Vocab only.

Phase 130 applies `study-felt-board-texture-web.webp` to `.study-board-
scene`, the dark-green board every Study state (ready/empty/active/
complete) sits on. Unlike every prior image-asset phase, this needed no
crop/position tuning at all: the source photo (1200x800) is a uniform,
edge-to-edge felt weave with no distinguishing shapes or vignette, so
`background-size: cover` reads correctly at any board aspect ratio the
scene renders at -- including the very short board the ready/empty states
show before any card stack exists. This was the lowest-risk asset
application of the whole Phase 127 set for exactly that reason: no
Round-0 alignment question to answer, no per-column crop math, just a
straight swap.

The old `linear-gradient(165deg, var(--notebook-cover), var(--notebook-
cover-deep))` two-stop gradient became the `background-color` fallback
(same tokens, same tone) with the photo layered on top via `background-
image`. `.study-board-scene::before` -- a faint CSS radial-gradient dot
pattern simulating felt weave -- is removed outright: the board now has
*actual* felt grain, so the fake dot texture was pure duplication, the
exact "CSS texture that now conflicts with the real photo" case the brief
asks to resolve. The soft top-sheen radial-gradient highlight (8% white
alpha, arcing across the board's top edge) stays as a second background
layer painted in front of the photo -- it reads as a light source, not a
material, so it adds depth rather than fighting the felt underneath it.
`.study-board-scene::after` (the quiet leaf-sprig corner accent) is
unrelated material and was left untouched.

`study-flashcard-stack-candidate-web.webp` was evaluated and NOT applied,
per the brief's own explicit allowance to record it as a deferred crop
candidate rather than force a bad fit. The natural target would have been
`.study-card-backing-sheet` (the two ghost sheets peeking out from behind
the active card, giving the stack its "pile of cards" depth) -- but the
photo carries a strong dark vignette blurring all four edges toward
near-black, and the backing sheets are only ever visible as a thin
(~5-10px) sliver at their own edges (the real `.study-card` on top covers
the rest). A `background-size: cover` crop on a box that size would very
likely land on exactly that vignette, most likely rendering as a dark
smudge at the card-stack edge instead of the clean cream sliver the CSS
`var(--panel-bg)` fill currently gives for free. Worked out from the
image's actual composition and how `.study-card-backing-sheet` is
actually sized/positioned/rotated, not just "it has a vignette" in the
abstract -- confirmed by inspection, not tested with a broken screenshot,
since the failure mode was predictable enough not to need shipping it
first. `.study-card-backing-sheet` is unchanged this phase.

Rating stamps (`.rating-button`, `.study-rating-grid`, all four
`.rating-again`/`-hard`/`-good`/`-easy` colors/icons/labels) were not
touched at all -- they're solid-fill buttons with their own colors,
structurally independent of the board background by construction, so
they needed no special protection beyond simply not editing that CSS.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account (5 real vocab items, mixed unknown/uncertain status) at 1280
desktop and 390/375/320 mobile: `npm run build` clean, `git diff --check`
clean, zero console errors/warnings, zero `scrollWidth`/`clientWidth`
mismatch at any viewport. `study-felt-board-texture-web.webp` returned
200, no 404s. Exercised the full review flow with real state transitions,
not static screenshots: ready state -> quick-start ("새 단어 학습") ->
active card -> "정답 보기" reveal -> all 4 rating buttons present and
functional -> repeated through a full 3-5 card session -> completion
state with real session-count stats -> "한 번 더 복습" restart. Two
`elementFromPoint` checks that initially came back `false`/`null` (the
completion screen's restart button, once below the fold) were re-verified
with `scrollIntoView()` first and confirmed to be viewport-scroll
artifacts, not real blocking -- a real click on both the restart button
and a rating button (`hit: true` after scrolling into view) worked
correctly on both 1280 and 390. Board texture legibility was checked at
every width down to 320px -- even where only a thin sliver of board shows
past the near-full-width card, the felt grain stays visibly real, not
flattened to a solid color, and never needed the brief's fallback "tame
it with a light overlay" option since the source photo's own contrast was
already moderate. No files under `backend/` were touched; no SRS/review/
queue/studyMode/shared-deck-study logic, and no rating-button structure,
changed. No `StudySection.tsx` changes at all -- purely a `globals.css`
edit.

**Files changed:** `frontend/app/globals.css` only. No new asset files --
reused Phase 127's already-committed
`frontend/public/brand/decor/phase127/study-felt-board-texture-web.webp`
directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser QA
against a real review session (ready -> active -> rating -> complete ->
restart) passed at all four required viewports, rating-stamp usability
and visual weight confirmed unchanged.

**Next phase candidates:** none remain from Phase 127's original asset
manifest -- all six candidates (Home, Reading x2, Shared Deck x2, Vocab,
Study) have now been either applied or explicitly deferred with a
documented reason (`study-flashcard-stack-candidate-web.webp` above, plus
Phase 126's `book-cover-green-object-candidate`/`sticky-note-set`/
`desk-prop-set` candidates). Any further image-asset work would need a
new generation pass.

Phase 131 is a pure asset-prep pass, no screen changes: it turns the four
"candidate" source images that earlier phases deferred (vignette/crop/
multi-object-atlas problems) into 9 individually usable transparent WebP
files under `frontend/public/brand/decor/phase131/` (full sourcing and
sizes in that folder's own `ASSET_MANIFEST.md`). Nothing in
`frontend/components/` or any screen's CSS was touched.

The key finding that made this tractable: the `-web.webp` versions of
these candidates (already committed and referenced in earlier phases'
own DESIGN.md notes as "has a vignette, deferred") look dark/vignetted at
the edges only because that export step flattened the image onto an
opaque background, discarding alpha. The **source PNGs
(`*-candidate.png`, sitting right next to each `-web.webp` all along)
already carry real per-pixel alpha transparency** with a clean matte
cutout and a natural soft drop shadow baked in -- confirmed by
compositing each one onto a plain white background with Pillow, which
revealed a professional-quality studio cutout, not a vignette at all.
Every Phase 131 crop was made from the source PNG, never the `-web.webp`,
carrying that real alpha straight through into a new transparent WebP.
Worth remembering for any future asset-review pass: check the source PNG
before writing off a `-web.webp` candidate as unusable.

Cropping method: for the two multi-object canvases
(`sticky-note-set-candidate.png`: 3 notes; `desk-prop-set-candidate.png`:
4 props), object boundaries were found programmatically via alpha-channel
projection analysis (row/column sums of `alpha > 10`, gap-detection to
split into segments) rather than eyeballed -- then each object's tight
bounding box was computed by scanning for actual alpha-positive pixels
within its own segment window. A first padding pass (a flat 3% margin on
every edge) produced a real bug caught in QA: the padding on adjacent
objects overlapped, bleeding a sliver of the neighboring note/prop into
the crop (most visible as a thin blue strip inside the yellow sticky-note
crop). Fixed by computing each edge's padding independently, clamped to
stop a few px short of the nearest neighbor's own tight bbox rather than
using one flat margin everywhere -- re-verified clean afterward, no
bleed on any of the 7 multi-object crops. The two single-object images
(`book-cover-green-object-candidate.png`, `study-flashcard-stack-
candidate.png`) had no neighbor-bleed risk and used a plain flat-margin
crop.

Tooling: Pillow + numpy, installed via `pip install --target` into a
scratch directory outside the repo (`C:\JV_Project\qa_phase131\pytools`,
never committed, cleaned up at the end of the phase) rather than added to
`backend/requirements.txt` -- per the brief, no new project dependency.
The backend's own `.venv` Python interpreter was used to run the install
and the crop script since it's the only readily-available local Python
with network access to fetch packages, but neither package was ever
installed *into* that venv itself (`--target` points elsewhere), so
`backend/requirements.txt`/the venv's own site-packages are unaffected.

All 9 outputs visually verified: no vignette, no bled-in neighbor
fragment, natural shadow intact, transparent background confirmed via a
white-background composite test for every file, plus one contextual
sanity check (`study-flashcard-stack-clean.webp` composited onto the
Study board's actual dark-green felt tone) confirming it now reads
exactly as intended for a future `.study-card-backing-sheet` application
-- directly reversing Phase 130's "deferred, vignette risk" call now that
the real cause (flattened `-web.webp` export, not the source art) is
understood and worked around.

**Files changed:** `frontend/public/brand/decor/phase131/` (9 new WebP
files + `ASSET_MANIFEST.md`), this `docs/design/DESIGN.md` entry. No
`.tsx` or screen CSS changed -- `git diff --check` and `npm run build`
both still pass since no code moved, only new static assets and docs.

**Commit-readiness:** yes -- all 9 assets pass visual QA, manifest
documents exact sourcing for reproducibility, no code/behavior changed to
regress.

**Next phase candidates:** apply `study-flashcard-stack-clean.webp` to
`.study-card-backing-sheet` (Study, now unblocked -- was Phase 130's one
deferred item), `sticky-note-yellow/blue/coral.webp` to Home's shortcut
stickers or a future candidate-tray variant, `desk-prop-*.webp` to
Home/Reading's existing pure-CSS desk-prop layers (pen/clip/leaf already
exist as CSS shapes in `.home-desk-prop`/`.reader-desk-prop` -- these
photographed versions are direct drop-in upgrades), and
`book-cover-green-object-clean.webp` for a Home/empty-state accent. None
of these are applied yet; this phase only made them applicable.

Phase 132 applies `study-flashcard-stack-clean.webp` (Phase 131's
transparent crop) to `.study-card-backing-sheet`, closing out the one
item Phase 130 deferred. `.study-card` itself -- the live HTML flashcard
carrying word/meaning/rating grid -- is untouched; only the two ghost
sheets behind it (`-outer`/`-inner`, both sharing this one base rule)
changed.

The backing-sheet box is nearly the same size as the real card sitting on
top of it (`top: 14px; bottom: 0` vs. the real card's own height, offset
only by each instance's few-degree rotation + a handful of px of
translation) -- so in practice only a thin sliver of it is ever visible,
peeking out at the rotated corners. `background-size: cover` was chosen
deliberately over `contain` for exactly that reason: `contain` would
letterbox the image inside a mismatched-aspect box (the box is portrait-
ish, the photo is landscape, ~1.48:1) and risk the photo shrinking into
the dead center where the real card already covers it completely, never
visible at all; `cover` guarantees paint reaches every rotated corner
where the peek actually happens, even though it crops out most of the
source photo's own multi-card illustration in the process. Verified via
a 3x zoomed screenshot of both the top and bottom peeking edges: real
paper grain and a natural, slightly irregular rounded corner are clearly
visible, not a flat color -- confirming the crop-out tradeoff was worth
it, not just a cosmetic gesture.

CSS removed: the flat `background: var(--panel-bg)` fill and the `1px
solid rgba(110, 91, 47, 0.16)` border are both gone from the shared
`.study-card-backing-sheet` rule -- the photo supplies its own paper
tone and its own natural card edge, so a CSS border on top of it would
have doubled that edge unnaturally. The existing `box-shadow: 0 10px 20px
rgba(37, 43, 30, 0.18)` was kept as-is after a visual check: it reads as
the stack lifting off the felt board underneath, not as a duplicate of
the photo's own (much softer, tighter) built-in shadow, so the two don't
visibly compete. `background-color: var(--panel-bg)` (the old flat fill)
stays as a same-family fallback if the image fails to load, per the
brief's explicit requirement.

Both `.study-card-backing-sheet-outer` and `-inner` pull from the same
shared base rule, so both instances get the same photo at their own
existing rotate/translate offset -- two slightly-offset slivers of one
real photographed stack, reading as two more paper cards underneath
rather than one flat image pasted behind a CSS shape. `.study-card-stack`
(the outer pile wrapper), `.study-card` (the live card), `.complete-card`,
`.study-rating-grid`/`.rating-button`/`.study-rating-stamp-tray` (all 4
rating stamps, their colors, icons, and labels), and `.study-board-scene`
(Phase 130's felt board) are all completely unchanged -- this phase only
touched the one shared backing-sheet rule.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account (5 real vocab items) at 1280 desktop and 390/375/320 mobile:
`npm run build` clean, `git diff --check` clean, zero console
errors/warnings, zero `scrollWidth`/`clientWidth` mismatch at any
viewport. `study-flashcard-stack-clean.webp` returned 200, no 404s.
Exercised the full review flow with real state transitions: ready ->
quick-start -> active card (backing sheets visible peeking out) -> "정답
보기" reveal -> real click on a rating button (`hit: true`, confirmed via
`elementFromPoint` resolving to the button itself, not the image) ->
repeated through a full 5-card session -> completion state (same backing-
sheet treatment, shared class) -> real click on "한 번 더 복습" (`hit:
true`). Mobile rating grid confirmed unchanged in size/position/
clickability at all three widths -- the backing sheets are absolutely
positioned behind the card and never participate in its own layout flow,
so there was no mechanism by which this change could have pushed or
resized the rating grid, and the screenshots confirm it didn't. No files
under `backend/` were touched; no SRS/review/queue/studyMode/shared-deck-
study logic, rating-button structure/colors/labels, or `StudySection.tsx`
prop/handler, changed -- in fact `StudySection.tsx` itself was never
opened for editing, only read for Round-0 verification.

**Files changed:** `frontend/app/globals.css` only. No new asset files --
reused Phase 131's already-committed
`frontend/public/brand/decor/phase131/study-flashcard-stack-clean.webp`
directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser QA
against a real review session (ready -> active -> rating -> complete ->
restart) passed at all four required viewports, rating-stamp usability
and visual weight confirmed unchanged, zoomed-edge inspection confirmed
the image crop is a real visible improvement and not just a theoretical
one.

**Next phase candidates:** the remaining three Phase 131 crops --
`sticky-note-yellow/blue/coral.webp`, `desk-prop-pen/washi-tape/
paperclip/leaf.webp`, and `book-cover-green-object-clean.webp` -- are
still unapplied to any screen. Phase 131's own DESIGN.md entry has the
per-asset target-screen suggestions.

Phase 133 applies four of Phase 131's photographed desk-prop crops --
`desk-prop-leaf.webp`, `desk-prop-washi-tape.webp`, `desk-prop-
paperclip.webp`, `desk-prop-pen.webp` -- to Home's desktop-only
`.home-desk-props` layer, replacing the four pure-CSS shapes
(`--plant`, `--stationery`, `--pen`, `--cup`) it held since Phase 118.
Sticky notes are left for a future phase per the brief; not forced in
here.

The old `--stationery` prop packed a washi-tape flag shape and a
paperclip circle into one element's `::before`/`::after`. Since Phase
131 produced the tape and paperclip as two separate photographed
objects, they're now two separate `<img>` elements
(`--tape`/`--paperclip`) rather than one combined shape -- letting each
sit at its own natural angle instead of being forced into a shared
bounding box. `--plant` becomes `--leaf` (the photographed sprig).
`--pen` keeps its name but is now the photo. `--cup` has no
photographed counterpart among Phase 131's crops, so it's dropped
rather than left as the one CSS-drawn shape sitting next to three real
photos -- exactly the "mixed design language" the brief's judgment
criteria warn against. This takes the scene from four props to four
props of a different kind, not four down to three as padding -- the
count was never the point.

`HomeDashboard.tsx`'s `.home-desk-props` container changes from four
empty `<span>`s (each drawing its own shape via CSS pseudo-elements) to
four `<img>` elements pointing at the Phase 131 files, each with empty
`alt`, `aria-hidden="true"`, and inheriting `pointer-events: none` from
the container (verified, not assumed -- see QA below). Positioning
values in `globals.css` were re-derived from each asset's real aspect
ratio (leaf 223x400, tape 400x353, paperclip 400x378, pen 184x400)
rather than reusing the old CSS shapes' arbitrary box sizes, then
placed by eye against real screenshots: leaf top-left near the cover's
own corner (echoing the old plant spot), tape and paperclip low-left
near the sticky-note column (echoing the old stationery spot, now as
two independently-angled objects instead of one combined shape), pen
bottom-right bleeding into the open wood past the sticky-note column
(echoing the old pen spot). No extra `box-shadow`/`filter: drop-shadow`
was added to any of the four -- each source photo already carries its
own natural soft shadow (per `phase131/ASSET_MANIFEST.md`), so a CSS
shadow on top would only double it, the same call Phase 132 made for
the study card-backing photo.

Verified via a 3x zoomed screenshot of both prop clusters: the leaf
reads as a real sprig peeking from behind the cover's corner, the tape
roll and paperclip read as two distinct objects resting near each
other on the wood-textured page background (their bounding boxes
overlap slightly by design -- like a paperclip actually resting near a
tape roll on a desk, not stacked as one shape), and the pen reads as a
single object resting at a natural diagonal. All four read as
photographed objects in one shared flat-lay lighting, not a pile of
independent stickers -- the "실제 물건이 자연스럽게 놓인 단일 장면"
bar the brief set.

Nothing else on Home changed: `.home-cover`, `.home-cover-cta`,
`.home-cover-sample`, `.home-stickers`/`.home-sticker` (including their
`vocab`/`review`/`decks` click handlers), `.home-footnote`, the
`>=1024px` desk-scene grid layout, and every non-prop rule in that
media block are untouched. `page.tsx`'s tab-routing, drawer, account
menu, and feedback modal wiring were not touched -- only exercised in
QA to confirm this phase didn't regress them.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account (`homeqa133@test.local`): `npm run build` clean, `git diff
--check` clean, zero console errors/warnings, zero
`scrollWidth`/`clientWidth` mismatch at 1280/390/375/320. All four new
`.webp` requests returned 200, no 404s. `elementFromPoint` at each
prop's own center resolved to whatever's actually beneath it (the page
background, `.home-cover`, or `.home-stage`), never the prop image
itself -- confirming `pointer-events: none` is honestly inherited, not
just assumed from the CSS. Real clicks (not just hit-tests) confirmed:
CTA routes to Reading (`.reading-panel` appears), all three shortcut
stickers resolve to themselves under `elementFromPoint`, mobile
hamburger opens/closes `.app-nav-drawer` (conditionally rendered, so
DOM presence is a reliable open/closed signal, not just a CSS
visibility toggle), the account-menu trigger opens `.account-menu-panel`
showing the logged-in email and logout option, and the feedback button
opens its modal. Mobile (390/375/320) confirmed via `getBoundingClientRect`
+ `offsetParent` (not `getComputedStyle`, which reports an element's own
`display` value regardless of an ancestor's `display: none` and would
have been a false positive here) that all four props have zero size and
no offset parent below 1024px -- the cover is the sole subject on
mobile, exactly as before this phase. One QA-process finding along the
way: the scratch backend needed `CORS_ORIGINS` explicitly set to the
dev server's actual port (3133) since the backend's CORS default only
allows port 3000 -- without it every authenticated fetch failed
preflight with a 400, surfacing as misleading "Failed to fetch" console
errors that had nothing to do with this phase's actual change (caught
and fixed before treating it as a real regression).

**Files changed:** `frontend/components/HomeDashboard.tsx`,
`frontend/app/globals.css`. No new asset files -- reused Phase 131's
already-committed `frontend/public/brand/decor/phase131/desk-prop-
{leaf,washi-tape,paperclip,pen}.webp` directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser
QA (desktop composition, mobile prop-hiding, CTA/sticker routing,
drawer, account menu, feedback modal, click-through hit-testing on
every prop) passed at all four required viewports with zero console
errors and zero failed requests.

**Next phase candidates:** `sticky-note-yellow/blue/coral.webp` (Home's
shortcut stickers or a future candidate-tray variant) and
`book-cover-green-object-clean.webp` (a Home/empty-state accent) are
the only Phase 131 crops still unapplied.

Phase 134 applies all three Phase 131 sticky-note crops --
`sticky-note-yellow.webp`, `sticky-note-coral.webp`, `sticky-note-
blue.webp` -- to the desktop-only (`>=1024px`) `.home-sticker` cards
(단어장/복습/덱), replacing their flat `background: var(--panel-bg)` +
`1px solid var(--paper-border)` fill with the photographed torn-paper
note as a `background-image`. Mapping: `--vocab` gets yellow (a warm
note color pairing with vocab's existing ink-brown icon),
`--review` gets coral (review already pairs with `--tone-coral`
elsewhere in the app, e.g. `.analyze-panel`), `--decks` gets blue
(matching its existing dusty-blue icon color exactly). Mobile
(`.home-sticker`'s base, pre-1024px rule) is untouched -- these three
`background-image` declarations live entirely inside the existing
`>=1024px` media block, alongside the rest of Phase 118's desktop-only
sticky-note treatment.

The real judgment call this phase turned on: `.home-sticker`'s actual
rendered shape at `>=1024px` is a wide horizontal bar (measured ~411x85,
roughly 4.8:1) while all three note photos are much closer to square
or landscape 1.5:1 (yellow ~1:1, blue ~1.45:1, coral ~1.57:1). Cover-
fitting a near-square photo into a 4.8:1 box crops away most of its
height, which risked losing the note images' whole point -- their
irregular torn-edge silhouette -- and leaving nothing but a flat color
swatch, arguably a regression from the clean existing CSS card. This
was resolved empirically, not by inspection: a 3x zoomed screenshot of
the actual rendered cards (not the full-page shot) showed real paper
grain, mottled color variation, and a visible torn edge silhouette
still surviving at the card's rounded-corner boundary on both left and
right sides -- the photos' texture reads as genuine paper *through* the
aggressive crop even without the full silhouette being visible, so the
photos still outperform a flat CSS fill rather than merely matching it.
All three colors passed this check; none needed to be reverted per the
brief's "억지로 3개 전부 적용하지 말고" allowance for partial
application.

CSS removed: `border: 1px solid var(--paper-border)` (the photo now
supplies its own visible torn/paper edge) and the flat
`background: var(--panel-bg)` fill (replaced by `background-color:
var(--panel-bg)`, kept only as a same-family fallback for a failed
image load, per every prior phase's convention). `overflow: hidden`
was added so the existing `border-radius: 4px 18px 18px 18px` keeps
clipping the photo to the same rounded-card silhouette the mockup's
Home panel uses -- deliberately kept rather than switched to an
irregular/organic outline, since the desktop mockup's own shortcut
notes are clean rounded rectangles, not rustic torn scraps; the photo
supplies real material texture inside that shape rather than replacing
the shape itself. The `::before` washi-tape rectangle (flat semi-
transparent brown box, unchanged since Phase 118) and every rotation/
hover/tilt rule were kept as-is after the same zoomed check confirmed
the tape mark still reads correctly sitting on top of the textured
paper instead of a flat color -- no conflict found, so nothing else was
touched.

Label/hint text legibility (`.home-sticker-label`/`-hint`, using
`var(--text)`/`var(--muted)`) was checked against all three photo
colors directly in the zoomed screenshot rather than assumed: dark text
stays clearly legible on the yellow, coral, and blue paper alike, no
contrast regression versus the old cream `var(--panel-bg)` fill.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account (`homeqa134@test.local`): `npm run build` clean, `git diff
--check` clean, zero console errors/warnings, zero
`scrollWidth`/`clientWidth` mismatch at 1280/390/375/320. All three new
`.webp` requests returned 200, no 404s. `elementFromPoint` hit-tests
(after `scrollIntoView`) confirmed the CTA and all three stickers
resolve to themselves, not the photo. Real clicks confirmed routing is
unchanged: clicking `.home-sticker--vocab` shows `.vocab-panel`,
clicking `.home-sticker--decks` shows `.shared-deck-section`. Mobile
(390/375/320) confirmed via `getComputedStyle` that all three stickers
carry `background-image: none` and `border-width: 0px` at every
mobile width -- this phase's change is provably inert below 1024px,
the cover stays the same 528px-tall sole subject it was before this
phase. `HomeDashboard.tsx` was not opened for editing -- the three
`.home-sticker--vocab/--review/--decks` modifier classes this phase
targets already existed in the JSX (added for icon coloring back in
Phase 118), so no `.tsx` change was needed at all.

**Files changed:** `frontend/app/globals.css` only. No new asset
files -- reused Phase 131's already-committed
`frontend/public/brand/decor/phase131/sticky-note-{yellow,coral,
blue}.webp` directly.

**Commit-readiness:** yes -- build and diff-check clean, full browser
QA (desktop legibility/texture check via zoomed screenshot, click
routing, mobile inertness, hit-testing) passed at all four required
viewports with zero console errors and zero failed requests.

**Next phase candidates:** `book-cover-green-object-clean.webp` is now
the only Phase 131 crop still unapplied to any screen (a candidate for
a Home or empty-state accent, per Phase 131's own manifest notes).

Phase 135 judges `book-cover-green-object-clean.webp` against Home and
**holds** -- no code change. The object crop (507x700, a full closed
green cloth notebook shot straight-on: spine, snap closure, rounded
corners, edge highlight all visible) is a photograph of the *same*
green cloth book `.home-cover` already wears as
`book-cover-green-surface-web.webp` (Phase 126) -- the surface file is
just a tighter, texture-only crop of that same cloth with no spine/
edge/closure visible, chosen specifically because `.home-cover` is a
live interactive card (title, subtitle, CTA, sample link, sticky note,
Shiori charm, strap, dots all rendered as real HTML on top of it) that
needed a *material* to sit on, not a second whole-book silhouette
competing for the same visual role. Applying the object crop anywhere
on Home necessarily reads as a second copy of the one book Home is
already built around, not a different object -- there's no version of
"add this" that isn't "duplicate the hero."

All three brief options were checked against this, not just asserted:

Option A (replace the main cover) doesn't work structurally --
`.home-cover` carries real interactive content baked into the DOM
(title/CTA/subtitle/sticky-note/Shiori/strap/dots), while the object
crop is a single flat photo of a *closed* book with no surface left to
put that content on. Swapping it in would mean either flattening all
of that live content into a fake baked-in look (explicitly against
every prior phase's "never bake text into decorative images" guardrail
-- see Phase 131's own manifest) or cropping the photo down to a
texture-only region anyway, at which point it's just a worse-cropped
duplicate of the surface file already in place.

Option B (a small desktop depth prop, e.g. a second book peeking from
behind the cover) was the one genuinely tempting reading of the brief,
but it runs straight into a decision Phase 126 already made and
documented: that phase explicitly removed `.card-stack-surface` (a
ghost "stack of cards behind this one" pseudo-element layer) from
`.home-cover` specifically because "kept on a real photographed
book-cover object, it would have produced exactly the 'card on top of
a card' look this phase's own success criteria explicitly rules out."
A second real photographed copy of the *same* green book tucked behind
the first is that identical mistake wearing a different implementation
-- not a new depth cue, a regression of one already fixed. Phase 133's
desk props (leaf/tape/paperclip/pen) work as a depth layer precisely
*because* they're different objects a desk plausibly holds; two
identical green notebooks stacked isn't a desk detail, it reads as a
render glitch. The desktop mockup's own "HOME DESK" panel (`docs/
design/mockups/casual-sticker-reader-desktop.png`, panel 1) confirms
this directly -- one notebook, three sticky notes, small props
(plant/tape/clip/pen/cup) -- no second book anywhere in the reference
composition this whole redesign has been chasing since Phase 118.

Option C (decorative/empty-state use elsewhere) is plausible in the
abstract but out of this phase's scope -- the brief frames this
specifically as a Home judgment, and Home has no empty state of its
own that isn't the cover itself. Left as a genuine future candidate
(a different screen's empty state, not Home) rather than forced in
here just because the asset exists -- the brief explicitly rules out
applying something "because assets remain," and this phase treats that
as a hard constraint, not a suggestion.

**Files changed:** `docs/design/DESIGN.md` only. No `.tsx`/`.css`
touched -- `git diff --check` and `npm run build` both still pass since
no code moved.

**Commit-readiness:** yes -- this phase's only output is a documented
judgment; the tree is otherwise identical to Phase 134's committed
state.

**Next phase candidates:** `book-cover-green-object-clean.webp`
remains unapplied, now with an explicit "hold" rationale on record
rather than sitting as an open question -- a future phase could
revisit it for a genuinely different screen's empty state, but not for
Home. No other Phase 131 crop remains uncommitted-but-unapplied; all
nine are now either applied (Phases 132/133/134) or explicitly held
(this phase).

Phase 136 is a full audit pass, not an asset phase: it checks whether
Phases 126-135's image-based redesign actually reads as one integrated
mockup language across every screen, or whether some corner still
shows a photo sitting awkwardly behind unmodified CSS card chrome. No
new assets, no `.tsx`/`.css` changes -- the phase's only output is this
record and the screenshots that back it (not committed; see QA below).

Round 0 started from `grep 'url("/brand'` across `globals.css` (24
locations) rather than trusting memory, to get an exhaustive worklist
instead of only the phases already fresh in context. Reading through
the surrounding CSS at each hit turned up something the brief didn't
expect going in: nearly every seam this audit was designed to catch
had already been found and fixed *in a prior phase*, with the fix's
own reasoning left in a comment at the site. Phase 119 stripped
`.bookmark-inspector-pinned`'s own border/shadow/tilt specifically
because keeping the floating-card look next to the open-book photo
"made this read as a second floating card... instead of the mockup's
single open-book spread." Phase 126 removed `.card-stack-surface` from
`.home-cover` for the same reason. Phase 129 removed
`.vocab-notebook-index .index-card-filter`'s CSS tab-stack accent once
a real photographed page-edge tab sat behind it, "keeping the fake tab
stack next to the real photographed one would read as two competing
tab motifs." This is the exact failure mode this phase was sent to
find -- and in every one of these cases it was already found and fixed
before this phase started, which is why the live-rendered check below
came back clean rather than turning up a backlog of P1 fixes.

Live verification (not just reading comments) covered, at 1280 desktop
and 390/375/320 mobile, against a seeded real account (6 vocab items
across known/uncertain/unknown, a published shared deck, a due-today
review queue): Home (cover, desk props, sticky notes), Reading (start
page, sample-text analyzed result, desktop pinned-inspector idle
state, mobile bottom-sheet `TokenDetailSheet`), Study (ready, active
card mid-review, rating-stamp reveal), Vocab (notebook index/filter
rail, word list, detail rail idle state), Shared Deck (wood shelf,
book-cover cards, inline detail actions), Analyze, Stats/Info, and the
feedback modal. Screenshots were the deciding evidence, not the CSS
comments alone -- e.g. the Vocab detail rail's photographed folded-
corner-and-red-rule-line crop (Phase 129) is visible and legible at
actual render size, not just described as such in a comment.

Per-screen judgment: **Match** for all eight areas in the audit scope
(Home, Reading, Study, Vocab, Shared Deck, Analyze, Stats/Info,
Feedback). No Mixed or Problem findings. Analyze/Stats/Info/Feedback
carry no photo assets (as expected -- these are function-first
screens, not desk-scene screens per the brief's own implementation
order), but read as the same app: same paper-grid page background,
same cream/warm palette, same soft-shadow card language as the
photo-backed screens, not a colder admin-dashboard style breaking the
illusion.

Two things were noticed but are explicitly **not** findings for this
phase's scope, recorded here only so a future pass doesn't waste time
rediscovering them: (1) the Reading start page's placeholder Japanese
sample text renders in the same weight/color as real typed input,
which is a typography/content nit, not an image-vs-CSS mixing issue;
(2) duplicate "여행 단어" shared-deck cards appeared during this
audit's own QA runs -- traced to this session's seed script publishing
the same deck name multiple times across repeated re-seeds, a test-data
artifact of the audit harness, not app behavior, so not reported as a
product finding.

Nothing was fixed because nothing in the P1/P2 sense was found -- per
the brief's own instruction ("정말 작은 수정으로 해결 가능한 경우만
고친다"), a clean audit is a valid outcome, not a sign the audit was
insufficiently thorough. The 24-location CSS inventory plus the
16-screenshot live walkthrough above is offered as the evidence for
that conclusion rather than an assertion of it.

**Files changed:** `docs/design/DESIGN.md` only.

**Commit-readiness:** yes -- `npm run build` and `git diff --check`
both pass since no code moved; the tree is otherwise identical to
Phase 135's committed state.

**Next phase candidates:** none forced by this audit. The one
still-open item from earlier phases is unchanged: `book-cover-green-
object-clean.webp` remains held per Phase 135's explicit reasoning.

Phase 137 closes the one real observation Phase 136 recorded rather
than dismissed: the Reading start page's placeholder Japanese sample
line had no `::placeholder` rule of its own anywhere in the codebase --
it was inheriting `.reader-start-page textarea`'s own `color: var(--text)`
at effectively full weight, via whatever default the browser happened
to apply. The blank page read as "already has a sentence written on
it" rather than "waiting for one," undercutting the exact "원문을 붙인
종이" (a page you're about to paste text onto) feeling the surrounding
photographed ruled-paper texture (Phase 126) was built to sell.

Fix is a single new rule, `.reader-start-page textarea::placeholder`,
using `var(--muted)` (the app's existing de-emphasized-text token,
already used for hint copy elsewhere -- not a new color) plus
`opacity: 0.68` on top, scoped to this one textarea's placeholder
pseudo-element only. Nothing else changed: no font-weight override (the
weight difference perceived before was contrast, not boldness -- the
placeholder was never actually bold), no copy change (same sample
line), no touch to `.reading-note-sheet textarea` (the post-analysis
manuscript-tray re-edit field, out of this phase's scope per the
brief), and critically no touch to the textarea's own `color` rule --
real typed or sample-loaded text renders exactly as before, since
`::placeholder` and the base element color are separate CSS surfaces
that can't cross-affect each other.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account: a 2x-zoomed crop of the same textarea region, once showing the
untouched placeholder and once showing real sample text loaded via the
"샘플 문장으로 체험" chip, confirmed the two are now visibly distinct --
placeholder reads as a light gray guide line, sample/typed text reads
as solid dark ink, at 1280 desktop. Manually typing into the field
(bypassing the sample chip entirely) confirmed real input keeps full
contrast and legibility. `npm run build` and `git diff --check` both
clean. At 1280/390/375/320: zero console errors/warnings, zero failed
network requests, zero `scrollWidth`/`clientWidth` mismatch. Mobile
(390/375/320) confirmed the "샘플 문장으로 체험" corner chip still
sits clear of the placeholder's first line with no overlap, and a real
`elementFromPoint` hit-test on the chip resolved to the chip itself at
every width. Full flow re-verified end to end: sample chip click loads
the real multi-sentence SAMPLE_TEXT into the textarea's actual value
(not just visually), "원문 펼치기" successfully reaches the analyzed
result workspace (`.reader-paper` present, tokens rendered), matching
pre-phase behavior exactly. One QA-process note: the first mobile pass
came back with the sample chip missing entirely -- traced to this
session's own headless Chrome profile still holding a `reading-session`
draft in `localStorage` from an earlier desktop test run in the same
profile (the chip only renders when the field is empty), not a real
regression; fixed by clearing that key before each mobile navigation
in the QA script itself, not in app code.

**Files changed:** `frontend/app/globals.css` only. No `.tsx` file
touched -- `ReadingTab.tsx` was read for Round 0 but never edited,
since the fix is a pure CSS addition with no new class needed.

**Commit-readiness:** yes -- build and diff-check clean, full browser
QA (placeholder-vs-real-text contrast verified via zoomed screenshot,
sample-chip/CTA collision checked, full analyze flow re-verified end to
end) passed at all four required viewports with zero console errors
and zero failed requests.

**Next phase candidates:** none opened by this phase. This was a
narrowly-scoped typography fix closing Phase 136's one recorded
observation; no other loose ends remain from that audit.

Phase 138 is the closeout review for the whole Phase 118-137 arc: does
the app now read as the mockup's casual, desk-scene notebook throughout,
or does old boxed-web-app structure still show through somewhere, and
can this series of phases be declared done. Round 0 leaned on Phase
136's already-fresh, already-exhaustive audit (24 `url("/brand` CSS
locations checked, every one traced to a documented "photo replaces
CSS, conflicting CSS removed" decision) and Phase 137's fix of the one
thing that audit actually found, rather than re-deriving that work from
scratch in the same session it was produced. What this phase added was
a second, independent live-browser pass against a fresh seeded account
and a fresh headless Chrome profile, specifically to catch anything
that regressed between Phase 136 and now (Phase 137 did touch
`globals.css` again) rather than trusting the prior audit's screenshots
were still accurate.

That pass covered, at 1280 desktop, the full product loop rather than
static screens: Home -> Reading (sample text -> analyze -> result
workspace -> word inspector, 13 tokens rendered) -> Study (ready ->
quick-start -> active card -> reveal -> rate all 5 due items through
"보통" -> completion card with the 4/4 breakdown) -> Vocab (deck
selected, populated word list) -> Shared Deck (shelf with the seeded
"여행 단어" cover) -> Analyze -> Stats -> Feedback modal. Separately, at
390/375/320: Home, Reading, Study (including a second live rate-through
to confirm the rating grid lands inside the initial viewport without
scrolling, `y:457-663` inside an 800px-tall viewport at all three
widths), Vocab, Shared Deck, Analyze, Stats, plus an explicit
drawer-open-then-close check confirming `.app-nav-drawer` unmounts
cleanly (it's conditionally rendered, so DOM presence is a reliable
signal, not a CSS visibility toggle that could leave stale state
behind).

Results: zero console errors/warnings, zero failed network requests,
zero `scrollWidth`/`clientWidth` mismatch, and all 17 `/brand/decor/`
image requests returned 200 -- at every one of the four required
viewports, across the entire loop above, not just isolated screens.
Every screen from Phase 136's Match list stayed Match. Per this
review's own six criteria: (1) no leftover CSS structure was found
sitting alongside new image structure unexplained -- the few remaining
pure-CSS elements (Study rating stamps, Vocab's flat word-list rows,
Shared Deck's inline action buttons) are deliberately CSS per Phase 136
and this review's own criterion 4 ("기능 화면의 스캔성은 유지한다"), not
leftovers; (2) every applied image reads as a real object/material in
its scene (book cover, felt board, flashcard stack, wood shelf, desk
props, sticky notes, ruled paper), confirmed again via this phase's own
screenshots, not just re-asserted from Phase 136; (3) mobile keeps a
single clear protagonist on every screen checked (cover/original
text/rating decision/word list/shelf), verified via the rating-grid
viewport-position check and direct screenshot inspection; (4) desktop
reads as one desk scene per screen, not a card grid, on every screen
that has a desk-scene treatment; (5) no CSS-vs-photo conflict was
found, consistent with Phase 136; (6) scan/operate-ability of function
screens (Vocab list, Study stamps, Shared Deck controls) is untouched,
confirmed by real clicks succeeding throughout the walkthrough, not
just visual inspection.

**Closeout verdict: yes.** No code changes this phase -- the review's
own policy ("기본은 no-code review... P1/P2 명확한 문제만 수정") was
followed to the letter: nothing at P1 or P2 surfaced, so nothing was
touched. The temptation to keep polishing (a slightly different desk-
prop angle here, a slightly different color there) was treated as
exactly the "안정된 구조를 다시 흔드는 것" this review's own seventh
criterion warns against, not a missed opportunity.

**Files changed:** `docs/design/DESIGN.md` only.

**Commit-readiness:** yes -- `npm run build` and `git diff --check`
both pass since no code moved; the tree is identical to Phase 137's
committed state.

**Recommended next roadmap:** end the image-asset redesign series here.
The one still-open item (`book-cover-green-object-clean.webp`, held per
Phase 135) is a minor unresolved decorative question, not a blocker --
future work should move to ordinary feature work or QA hygiene
(dependency updates, test coverage, performance) rather than further
visual-language passes over an app this review found already
consistent end to end.

Phase 139 is the performance/loading follow-up Phase 138 recommended:
not a design pass, a check of whether the Phase 126-138 image work
costs more bytes than it needs to, and whether any of it loads at the
wrong time. Round 0 started from a full file inventory of
`frontend/public/brand/decor/` rather than assumption: 31MB total, of
which **29MB is source PNGs no code anywhere references** -- every
`grep` hit for an actual `url("/brand/decor/...")` in `globals.css` or
any `.tsx` resolves to a `-web.webp` or Phase 131 crop, never a raw
`.png`. Those PNGs are the pre-compression originals Phase 126/127/131
deliberately kept alongside their WebP exports for potential re-crops
(Phase 131's own manifest says as much) -- dead weight in terms of
bytes shipped with the repo/deploy artifact, but genuinely never
requested by a browser, since nothing links to their URL. Per the
brief's explicit instruction, they were not deleted -- only recorded
here as a held judgment, same treatment Phase 135 gave the one unused
webp crop.

A second, smaller unused-asset finding: five `-web.webp` files from the
original Phase 126/127 "candidate" pipeline are also unreferenced,
having been superseded by Phase 131's cleaner individual crops --
`phase126/book-cover-green-object-candidate-web.webp` (173KB),
`phase126/deck-cover-template-candidate-web.webp` (78KB, explicitly
"reserved for a future Shared Deck pass" per Phase 126's own entry,
never built), `phase126/desk-prop-set-candidate-web.webp` (35KB),
`phase126/sticky-note-set-candidate-web.webp` (63KB), and
`phase127/study-flashcard-stack-candidate-web.webp` (30KB) -- roughly
380KB combined. Also unreferenced: Phase 131's own
`book-cover-green-object-clean.webp` (96KB), but that one already has
an explicit hold judgment on record from Phase 135, not a new finding
here. None of these six were deleted, for the same reason as the PNGs.

The one thing Round 0 could act on directly, per the brief's own
"CSS media query를 더 정확히 좁혀 불필요한 이미지 로드를 줄이기"
allowance: a real-browser network-log comparison of Home at 1280 vs.
390 (cache cleared before each load, via CDP) showed Home's four desk-
prop `<img>` tags (Phase 133 -- leaf/tape/paperclip/pen) were being
fetched in full on the *mobile* load too, ~92KB across four requests,
despite `.home-desk-props { display: none }` at that width and the
props rendering nowhere on screen. This is a real, measurable browser
behavior difference from Home's own sticky notes
(`.home-sticker--vocab/--review/--decks`), which use CSS
`background-image` inside the same `>=1024px` media query and were
confirmed absent from the same mobile network log -- a browser does
not fetch a `background-image` behind a media query that isn't
currently matched, but an ancestor's `display:none` does not stop it
from fetching an `<img>`'s own `src` attribute. Phase 133 chose `<img>`
for the desk props specifically (unlike every other decorative photo in
the app, which is a CSS background-image) with no stated performance
rationale for that choice -- just implementation convenience -- so
converting it was a mechanism fix, not a design one.

Fix: `HomeDashboard.tsx`'s four `<img src=... />` desk-prop elements
became plain `<span>`s (same `aria-hidden`, same class names, same
position in the DOM -- `pointer-events: none` still inherited from
`.home-desk-props`, nothing about click-safety changed), and each
prop's photo moved into `globals.css` as `background-image` on its
existing `.home-desk-prop--leaf/--tape/--paperclip/--pen` modifier
class, still inside the same `>=1024px` block those rules already
lived in. `background-size: contain` (not `cover`) -- each prop's box
was already sized to its source photo's exact aspect ratio back in
Phase 133, so the two are equivalent here (no crop either way), but
`contain` is the semantically correct choice for "show the whole
cutout object," matching the reasoning Phase 133 itself gave for these
same four props.

Re-verified via the same cache-cleared network-log method: Home mobile
(390px) now shows 5 `/brand/` requests instead of 9, with all four
desk-prop bytes gone entirely (was 9 requests / ~2.20MB total page
weight including Shiori, now 5 requests / ~2.11MB -- the ~92KB/4-request
difference is exactly the four files that used to load invisibly).
Home desktop (1280px) is unchanged -- still 12 requests, same total
byte count, since the props still render there and the media query
still matches. A pixel screenshot comparison and a fresh
`elementFromPoint` hit-test on all four props (all still resolve to
whatever's beneath them, never themselves, confirming
`pointer-events: none` survived the markup change) confirmed the
desktop result is visually and functionally identical to Phase
133/138's already-Match state -- this phase did not reopen that
judgment, only changed how the same pixels get to the screen.

One measurement caveat recorded for future QA sessions in this repo:
an early pass of this same network-log method used
`Network.setCacheDisabled: true` and produced apparent duplicate
fetches of the sticky-note WebP files within a single page load. Tracing
it down: with cache forcibly disabled, a background-image referenced by
exactly one CSS rule (confirmed via `grep -c` -- each sticky-note file
appears exactly once) was still being requested twice, which
`Network.setCacheDisabled` alone can explain (it forces every reference
to hit the network, including ones a normal browser session would
silently serve from its own in-memory resource cache during the same
page's lifetime). Removing that flag (keeping only
`Network.clearBrowserCache` before each fresh scenario, which still
gives an accurate "first visit" byte count without breaking normal
intra-page caching) made the duplicates disappear entirely for the
Home scenario. A separate, much smaller instance of this same shape
persisted afterward -- sticky-note URLs occasionally showed a second
~243-byte response when navigating between tabs within one session --
traced to the dev server's own `Cache-Control: public, max-age=0`
header on every file under `/public` (confirmed via `curl -D -`),
which is standard `next dev` behavior to keep hot-reloading correct,
not a production configuration. A production build behind a real host
(Vercel or any CDN in front of static `/public` assets) typically sends
long-lived immutable cache headers for these files instead, so this
specific 243-byte revalidation blip is expected to not reproduce
outside local dev -- recorded here rather than chased further, since
changing server cache headers is outside this phase's CSS/asset scope
and the actual cost (243 bytes, not a full re-download) is negligible
either way.

Two things were explicitly checked and found already-correct, not
touched: (1) every currently-*used* WebP (12 files, 11KB-169KB each)
already comes from the Phase 125/126/131 compression pipeline
(`quality=88, method=6` per Phase 131's own manifest) -- re-compressing
any of them further risked visible quality loss for marginal byte
savings on files that are already small, which the brief's own
threshold ("실제로 크기 이득이 크고 화질 손상이 없을 때만") rules out;
(2) Shiori's nine PNGs (`frontend/public/brand/shiori/`, ~700KB-1.2MB
each, no `loading="lazy"` attribute on the `<img>` in `Shiori.tsx`) are
the single largest per-screen network cost in the app -- Home alone
loads two full-size variants (`shiori-default.png` + `shiori-review.png`,
~1.9MB combined) just for two small mascot corners -- but the brief
explicitly scoped Shiori to "로드 영향만 확인" (check load impact only,
no changes to the PNGs or the variant mapping), so this is recorded as
a load-impact observation and a candidate for a *future* phase, not
acted on here. A `_backup/` folder sitting alongside the live Shiori
PNGs (another ~8.1MB, an exact set of slightly-different-sized
duplicates, never referenced by any code) was also noticed while
checking Shiori's directory for this report, but falls under the same
"Shiori files, don't touch" scope line -- noted, not removed.

**Files changed:** `frontend/components/HomeDashboard.tsx`,
`frontend/app/globals.css`. No asset files added, removed, or
re-encoded.

**Commit-readiness:** yes -- build and diff-check clean, real-browser
network-log verification (before/after byte counts at 1280 and 390),
pixel-screenshot and hit-test confirmation that desktop is unchanged,
and a full 4-viewport click-through QA pass all came back clean with
zero console errors and zero failed requests.

**Next phase candidates:** (1) the 29MB of unreferenced source PNGs and
~380KB of superseded candidate WebPs in `frontend/public/brand/decor/`
-- a deletion pass, if the team decides the source files are no longer
worth keeping for future re-crops; (2) Shiori's PNG weight and eager
loading (~700KB-1.2MB per variant, no lazy-loading, a `_backup/`
folder of unused duplicates) -- out of this phase's explicit scope but
the largest remaining per-screen cost in the app; (3) `book-cover-
green-object-clean.webp` remains held per Phase 135, unrelated to
performance.

Phase 140 acts on next-phase-candidate (1) above: a real cleanup pass
over the unused assets Phase 139 catalogued, judged file-by-file rather
than deleted wholesale. Round 0 re-extracted the code-referenced set
fresh (`grep -rohE '/brand/decor/...'` across every `.tsx` and
`globals.css`) and confirmed it hadn't changed since Phase 139: exactly
20 files. Every one of the 17 remaining decor files (12 raw PNGs, 5
superseded `-web.webp` exports) was checked with a whole-repo grep for
its literal filename, not just assumed unused from the earlier list --
none turned up as a live `url(...)`/`src=` reference anywhere; the only
hits were prose mentions in `DESIGN.md` and the two
`ASSET_MANIFEST.md` files describing sourcing, which don't depend on
the file's physical path.

Three different dispositions came out of that check, matching the
brief's A/B/C framing per file rather than one blanket decision:

**Deleted (5 files, ~390KB):** the superseded `phase126/*-candidate-
web.webp` and `phase127/study-flashcard-stack-candidate-web.webp`
files. Each is a full-canvas WebP export of a PNG that Phase 131 later
individually-cropped from directly -- the WebP itself carries no
provenance a future re-crop would ever start from (you'd go back to the
PNG, never to an old flattened export of it), so once the PNG is
preserved elsewhere, these have zero remaining value. Confirmed safe:
the build and a full 4-viewport, 404-checking browser walkthrough (see
QA below) both came back clean after removal.

**Moved, not deleted (12 files, ~29MB):** every raw source PNG,
relocated from `frontend/public/brand/decor/{phase126,phase127}/` to
`docs/design/source-assets/{phase126,phase127}/` via `git mv` (history
preserved). This is the brief's own suggested resolution for
provenance-worthy originals -- "public이 아닌 별도 보존 위치/문서화
방안" -- applied literally rather than improvised: ten of these twelve
PNGs are the direct, traceable source of a WebP still in production
today (Home cover, Reading's open-book spread and paper texture,
Study's felt board, Shared Deck's shelf and covers, Vocab's ring
notebook, and the three Phase 131 crop sheets for desk props/sticky
notes/flashcard stack); the other two (`book-cover-green-object-
candidate.png`, `deck-cover-template-candidate.png`) are the source for
Phase 135's held asset and a never-built Shared Deck template
respectively -- lower value but not zero, so treated the same way
rather than singled out for deletion. The brief's own weak-justification
warning ("'언젠가 쓸 수도 있음'만으로 public에 29MB 원본을 계속 두는
것은 약한 근거") was read as an argument against leaving them in the
*deployed, web-served* `public/` tree specifically, not an argument for
deleting genuinely-traceable originals outright -- `docs/design/
source-assets/README.md` (new) documents the full PNG -> shipped-WebP
mapping so the provenance value survives the move, while the ~29MB
stops shipping with every deploy. Both `ASSET_MANIFEST.md` files
(`phase127/`, `phase131/`) got a short update pointing at the new
location rather than silently going stale -- `phase131/
ASSET_MANIFEST.md`'s exact crop-box coordinates are left untouched
since they're still accurate against the same files at their new path.

**Preserved in place, no action (1 file, 96KB):** `phase131/book-cover-
green-object-clean.webp`. Per Phase 135's explicit hold judgment and
the brief's own guidance to prefer preservation/documentation over
deletion for it, this is small, already a finished individual crop
(not a raw source needing archival), and already correctly documented
in both the Phase 131 manifest and Phase 135's DESIGN.md entry --
nothing further to add or move.

The 20 code-referenced production files (WebP/SVG/PNG alike) were not
touched in any way -- not moved, not renamed, not re-encoded.

Net effect: `frontend/public/brand/decor/` drops from 31MB to 1.4MB.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account, at 1280/390/375/320: `npm run build` clean, `git diff --check`
clean, zero console errors/warnings, zero failed network requests, zero
`scrollWidth`/`clientWidth` mismatch, and zero `/brand/` image 404s
across Home -> Reading -> Study -> Vocab -> Shared Deck at every
viewport (20 `/brand/` requests at desktop, 10 at mobile -- consistent
with Phase 139's own counts, confirming this phase changed nothing
about which files load, only what else sits unused in the repo).

**Files changed:** 12 PNGs moved (`git mv`) from `frontend/public/
brand/decor/{phase126,phase127}/` to `docs/design/source-assets/
{phase126,phase127}/`; 5 superseded WebP files deleted from `frontend/
public/brand/decor/{phase126,phase127}/`; `frontend/public/brand/
decor/phase127/ASSET_MANIFEST.md` and `frontend/public/brand/decor/
phase131/ASSET_MANIFEST.md` updated to point at the new archive
location; new `docs/design/source-assets/README.md` documenting the
full mapping; this `docs/design/DESIGN.md` entry. No `.tsx`/`.css`
touched -- no code change was needed since none of the moved/deleted
files were ever referenced.

**Commit-readiness:** yes -- build and diff-check clean, full 4-viewport
browser QA (including an explicit 404 check across every screen this
phase's changes could plausibly have affected) passed with zero
console errors and zero failed requests.

**Next phase candidates:** Shiori's PNG weight and eager loading and
its unused `_backup/` folder (still out of scope per every phase's
"Shiori PNGs/mapping 변경 금지" line, would need its own explicit
phase to touch); `book-cover-green-object-clean.webp` remains held per
Phase 135, unrelated to this cleanup.

Phase 141 is that explicit Shiori phase. Round 0 mapped every call site
of `ShioriCharacter`/`ShioriMark`/`ShioriStamp`/`ShioriGuideCard`/
`AppEmptyState` across the app (`grep` across every `.tsx`, then read
each site's actual `variant`/`mood` prop and its render condition) --
9 variants, all funneled through one shared `<img>` in `Shiori.tsx`'s
`ShioriImage`, each 693KB-1.19MB. That single choke point matters: any
loading-behavior fix applied there covers every one of the 30+ call
sites at once, with no per-site changes needed.

A real network-log sweep (cache cleared before each scenario, same
method as Phase 139/140) across Home/Reading-start/Reading-result/
Study-ready/Study-active/Study-complete/Vocab/Shared-Deck/Analyze/
Stats/Feedback, at both 1280 and 390, found no duplicate same-URL
fetches within any single screen (each variant loads exactly once per
page, confirmed) and no viewport-gating bug like Phase 139's desk
props -- every Shiori call site is genuinely React-conditional
(`mood ? <ShioriCharacter/> : ...`, `isInBasket ? <ShioriStamp/> :
null`), never a CSS-hidden-but-mounted `<img>`, so there was nothing
to gate further. The one real, consistent cost: `shiori-default.png` +
`shiori-review.png` (Home's cover charm + shortcut sticker icon, ~1.9MB
combined) load on *every* cold visit to the app regardless of which
screen the user actually wants, because Home is the SPA's landing
route and every fresh page load starts there before any client-side
tab switch -- confirmed identical at 390px, since Shiori is
intentionally not viewport-gated on Home (the charm/sticker are real
content at every width, not a desktop-only enhancement, per Phase
133/134/138's own screenshots). This is expected product behavior, not
a bug -- Home is supposed to load first -- but it does mean Shiori's
per-PNG weight is the largest fixed cost on the coldest, most-visited
path through the app.

Given that, the safe fix available under this phase's own guardrails
("lazy loading이나 decoding 속성 추가는 안전하면 허용", no PNG
changes, no variant-mapping changes): `loading="lazy"`,
`decoding="async"`, and `fetchPriority="low"` added to `ShioriImage`'s
one `<img>`. All three are loading *hints*, not visual or behavioral
changes -- confirmed via a second network-log pass that byte counts and
request counts are unchanged (a lazy image already in the viewport at
load time is still fetched immediately by the browser; these hints only
change *priority/timing* for the images that aren't, e.g. `AppEmptyState`
mood illustrations that only mount once a list is actually empty, or
`ShioriStamp`'s success/save marks that only mount after an action).
`fetchPriority="low"` reflects that Shiori is always a decorative
companion competing for the same connection as the actual content
(vocab data, analyzed text) the user came for -- deprioritizing it lets
real content win contention first. A `getBoundingClientRect()` check on
Home's cover charm and sticker icon (73x73 / ~40x41, matching every
prior phase's own measurements) and a full-page screenshot confirmed
zero size/position regression at all four required viewports.

**`_backup/` folder:** 9 PNGs, ~8.7MB, sitting in `frontend/public/
brand/shiori/_backup/` with zero code references (confirmed via
`grep -rn "_backup"` across `frontend/`) -- but `md5sum` against each
live same-named file showed every one is genuinely *different* from
its current counterpart, not an accidental duplicate. This is a real
prior generation of the Shiori character art, not junk. Per this
phase's own explicit caution ("backup 폴더 삭제는 매우 조심스럽게
판단... provenance/복구용이면 docs 쪽 이동") and the same treatment
Phase 140 gave the unused decor source PNGs, the folder was moved (not
deleted) via `git mv` to `docs/design/source-assets/shiori-backup/`,
with a note in that archive's `README.md` explaining what it is and
that it should only ever be restored to `frontend/public/` as a
deliberate character-art rollback decision, never casually.

Net effect: `frontend/public/brand/shiori/` drops from 17MB to 8.0MB
(the `_backup/` folder's ~8.7MB was the only reduction available here
-- the 9 live PNGs are explicitly out of scope for re-encoding or
replacement per this phase's own brief, and Round 0 confirmed why: they
render at their own quoted per-PNG sizes with no evidence any of them
is unnecessarily large for what it is, just consistently ~700KB-1.2MB
illustrated art, which recompressing without an explicit go-ahead would
risk visibly degrading the brand character).

Verified via headless Chrome (Windows-native, CDP) against a seeded
account, at 1280/390/375/320: `npm run build` clean (`fetchPriority`
type-checks fine against this project's React/TS DOM types), `git diff
--check` clean, zero console errors/warnings, zero failed requests,
zero `/brand/shiori/` 404s, zero `scrollWidth`/`clientWidth` mismatch,
across Home -> Reading -> Study -> Vocab -> Shared Deck at every
viewport. Byte-for-byte identical Shiori request counts/sizes before
and after the loading-attribute change, confirming it altered priority
hints only, nothing about which files load or when they visually
appear.

**Files changed:** `frontend/components/Shiori.tsx` (three loading
attributes on one `<img>`); `docs/design/source-assets/shiori-backup/`
(9 PNGs moved via `git mv` from `frontend/public/brand/shiori/
_backup/`); `docs/design/source-assets/README.md` updated; this
`docs/design/DESIGN.md` entry. No PNG re-encoded, no variant mapping
touched, no character added or removed.

**Commit-readiness:** yes -- build and diff-check clean, full
4-viewport network-log and visual QA (byte-identical request counts,
zero 404s, unchanged character geometry) passed with zero console
errors and zero failed requests.

**Next phase candidates:** none opened here. The remaining Shiori PNG
weight (the 9 live files themselves) was explicitly evaluated and left
alone -- re-encoding brand character art needs its own deliberate
phase with an explicit quality-tradeoff decision, not a default
performance pass. `book-cover-green-object-clean.webp` remains held
per Phase 135, unrelated to Shiori.

Phase 142 is that deliberate re-encoding phase. Round 0 confirmed the 9
live PNGs' actual specs (no assumptions carried over from Phase 141):
all RGBA with real alpha, ~700x1000px to ~1250x840px, 693KB-1.19MB
each, 8.0MB total -- and cross-checked against `globals.css`'s size
scale (`.shiori-asset--sm` 24px up to `.shiori-asset--hero`
`clamp(180px, 16vw, 220px)`), confirming every one of these ~1000px
source images renders at most at 220px on any real screen, a
5-6x oversample the brief didn't ask this phase to correct (resizing
wasn't on the brief's approved candidate list -- only compression
format changes were, so resolution was left untouched despite the
headroom).

No system image tools were available (no `cwebp`/`avifenc`/
`pngquant`/ImageMagick), so Pillow was installed into an isolated
scratch directory via `pip install --target` (same pattern Phase 131
established) -- never added to `backend/requirements.txt`, no new
project dependency. Two candidates were generated per the brief's own
recommendation, entirely in scratch space first, nothing in
`frontend/public/` touched until a candidate was actually chosen:

- **Lossless PNG re-optimize** (same pixels, best zlib settings):
  only 6.6% average savings across the 9 files -- well under the 30%
  adoption bar, confirming the originals weren't carrying meaningful
  re-compressible slack at the PNG level.
- **Lossless WebP** (same pixels, different container): 49.6% average
  savings (8.0MB -> 4.0MB), comfortably past the bar.

A third, unrequested-but-informative data point was also generated for
context: quality-90 lossy WebP hit 88.7% savings, but was not seriously
considered for adoption -- the lossless candidate already cleared the
30% bar by a wide margin with a strictly stronger quality guarantee
(mathematically zero difference vs. a "should look fine" judgment call
on a lossy file), so there was no reason to take on any lossy-artifact
risk. AVIF was not attempted at all, per the brief's own steer to skip
it when transparency/browser-support risk isn't worth it for a
brand-critical character asset -- lossless WebP already met every goal
without that risk.

The lossless claim was verified, not assumed: `PIL.ImageChops.
difference()` between each original PNG and its candidate WebP (after
decoding both back to RGBA) returned an empty bounding box for all 9
files -- meaning literally zero differing pixels, not just "visually
indistinguishable." This is a stronger guarantee than the brief's own
"확대 비교에서 손상 없음" bar asks for, since a pixel-identical decode
can't fail a zoomed visual comparison by construction. A 4x-zoomed
screenshot of the Home cover charm (`default` variant, `lg` size) and
the "복습" shortcut sticker (`review` variant, `md` size) was still
taken and inspected directly against a real rendered page (not just the
source files) to confirm the browser's own WebP decode path renders
identically to what Chrome showed for the PNGs in every prior phase's
screenshots -- clean line art, sharp alpha edges, no banding or
fringing.

Adopted: all 9 variants converted. `frontend/components/Shiori.tsx`'s
`SHIORI_ASSET_MAP` now points at `/brand/shiori/shiori-<variant>.webp`
instead of `.png` -- the only code change, since every one of the 30+
call sites across the app already goes through this one shared map
(Phase 141's own finding). No variant mapping, size class, or character
geometry touched. The `/design-lab/shiori` internal preview page (not
linked from app nav, reached only by typing the URL) had its own
explanatory Korean prose hardcoded a few `.png` mentions describing the
pipeline to whoever opens it -- updated to `.webp` for accuracy while
already in this file, text-only, no behavior change.

Per this phase's own "원본 PNG를 바로 덮어쓰지 말고" instruction, the 9
PNGs that were live right before this phase were moved (not deleted)
via `git mv` to `docs/design/source-assets/shiori-png-source/` --
distinct from Phase 141's `shiori-backup/` (an older, different
generation of the art) -- documented in that archive's own `README.md`
as the uncompressed master for any future edit, since re-opening and
re-saving a WebP repeatedly risks generational loss the same way
repeated JPEG re-saves do, even though today's WebP is itself lossless.

Net effect: `frontend/public/brand/shiori/` drops from 8.0MB to 4.0MB.
Combined with Phase 141's `_backup/` relocation, the live+deployed
Shiori footprint has gone from 17MB to 4.0MB across the two phases,
while the actual brand art shown to users is provably unchanged.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account, at 1280/390/375/320: `npm run build` clean, `git diff --check`
clean, zero console errors/warnings, zero failed requests, zero
`/brand/shiori/` 404s, zero `scrollWidth`/`clientWidth` mismatch,
across Home -> Reading -> Study -> Vocab -> Shared Deck -> Analyze
(the `classify` variant's own screen) at every viewport -- confirmed
via real network log that `shiori-default.webp`, `-review.webp`,
`-classify.webp`, `-reading.webp`, and `-empty.webp` all served 200 in
this walkthrough, none 404. A `getBoundingClientRect()`-style visual
screenshot of the full Home page matched every prior phase's screenshot
pixel-for-pixel by eye, and the 4x-zoomed crops of the cover charm and
shortcut sticker showed clean, unartifacted line art.

**Files changed:** `frontend/components/Shiori.tsx` (asset map
extensions); `frontend/app/design-lab/shiori/page.tsx` (doc-comment
text only); 9 new `.webp` files added to `frontend/public/brand/
shiori/`; 9 PNGs moved (`git mv`) to `docs/design/source-assets/
shiori-png-source/`; that archive's `README.md` updated; this
`docs/design/DESIGN.md` entry.

**Commit-readiness:** yes -- build and diff-check clean, a verified
(not assumed) lossless pixel-diff plus full 4-viewport network-log and
visual QA (zero 404s, unchanged character geometry, clean zoomed
crops) all passed with zero console errors and zero failed requests.

**Next phase candidates:** none opened here. The 5-6x resolution
oversample noted in Round 0 (source art up to ~1250px, max on-screen
use ~220px) is a real further opportunity but was intentionally left
alone -- resizing wasn't on this phase's approved candidate list, and
changing pixel dimensions (vs. just re-encoding the same pixels) is a
different, larger risk category that deserves its own explicit
decision rather than folding into a "safe re-encoding" phase.
`book-cover-green-object-clean.webp` remains held per Phase 135,
unrelated to Shiori.

Phase 143 is that explicit resizing decision. Round 0 re-measured
rather than assuming: the 9 live WebPs are ~700-1250px, and a fresh
`grep 'size="'` across every real (non-design-lab) call site found the
actual production maximum is `xl` (104px) -- three `moodSize="xl"`
calls in `SharedDeckSection.tsx` for the loading/empty/error states the
brief's own screen list named -- not `hero` (`clamp(180px,16vw,220px)`),
which turned out to be unused on any real screen; only the internal
`/design-lab/shiori` preview renders `size="hero"`. The brief's own
disqualifying rule ("512px이 좋더라도 hero clamp 220px × DPR3 = 660px
기준을 못 맞추면 512px은 보류한다") was applied literally regardless of
that finding -- `size` and `variant` are fully decoupled in
`ShioriCharacter`'s API, so any of the 9 files could be shown at `hero`
size in a future screen without this file ever needing to change, and
the design-lab page is real, reachable code today, not a deleted
fixture.

Two candidates were generated per the brief's own minimum (512px and
768px max-dimension, LANCZOS resampling from the Phase 142 PNG source,
saved lossless-WebP), entirely in scratch space first. Both cleared the
30% savings bar on their own (69.5% and 39.5% respectively against the
Phase 142 baseline), so the deciding factor was quality, not size --
tested three ways, not just eyeballed:

1. **Quantitative, at realistic render sizes.** Rather than comparing
   the candidate files at their own resolution, each candidate was
   *resampled again* (same LANCZOS filter a browser's own image
   scaling uses) down to the actual on-screen pixel sizes that matter --
   312px (today's real max: `xl` 104px x DPR3) and 660px (the unused-
   today but brief-mandated `hero` 220px x DPR3 safety check) -- and
   diffed against the same resample done from the original. At 312px,
   768px scored a mean per-pixel channel difference of 0.8-1.2 (out of
   255) across all 9 files, with under 0.7% of pixels differing by more
   than 20/255 -- consistent with imperceptible. 512px was noticeably
   worse even here (1.4-2.1 mean). At the 660px hero check, 768px held
   up (1.4-2.1 mean, still under 1% of pixels significantly different),
   while 512px broke down clearly -- mean differences of 4.8-7.1, with
   several files hitting the maximum possible 255 difference on some
   pixels and 3-6% of pixels significantly different, i.e. visible
   upscaling softness, exactly what the brief's rule predicted for a
   512px source pushed past its own resolution at 3x. This alone
   disqualifies 512px under the brief's stated bar, independent of any
   visual judgment call.
2. **Visual, face-cropped.** Side-by-side 4x-nearest-neighbor crops of
   the top ~45% (head/face) of four representative variants
   (default/review/classify/empty), each independently rendered at the
   312px real-world target from the original and from the 768px
   candidate, inspected directly -- outline weight, eye/mouth linework,
   the charm ring's highlight, and the alpha edge against a mid-gray
   test background were indistinguishable between the two.
3. **Real browser, real DPR3.** Headless Chrome set to
   `deviceScaleFactor: 3` (not simulated -- an actual 3x render pass),
   navigated to Shared Deck (the screen hosting the real `xl`-sized
   instances), and a 4x-zoomed screenshot crop taken of the live
   `shiori-default.webp` icon actually rendered in that page. Clean line
   art, sharp alpha edge against the page background, no blur or
   banding -- confirming the synthetic Pillow-based tests reflect what
   a real browser's own decode+scale pipeline actually produces, not
   just what a Python resampling library predicts.

**Adopted: 768px max-dimension. Held: 512px** (fails the brief's own
hero/DPR3 bar with real, measured softness -- not a judgment call,
data). No filename or extension changed -- each `shiori-<variant>.webp`
in `frontend/public/brand/shiori/` was replaced in place with its
768px-resized content, so `Shiori.tsx`'s `SHIORI_ASSET_MAP` needed zero
changes; variant mapping, CSS size classes, and character
geometry/position are all untouched.

Preservation, per the brief's explicit "원본 PNG와 Phase 142 무손실
WebP는 보존" instruction: Phase 142's full-resolution lossless WebP
files (the ones live immediately before this phase) were copied to the
new `docs/design/source-assets/shiori-webp-fullsize/` *before* being
overwritten in `frontend/public/`, documented in that archive's
`README.md` as the go-to source if a future screen ever needs more than
768px (rather than re-deriving from the even-larger PNG). The Phase 142
PNG masters in `shiori-png-source/` are untouched by this phase.

Net effect: `frontend/public/brand/shiori/` drops from 4.0MB to 2.5MB.
Across Phases 141-143 together, the live+deployed Shiori footprint has
gone from 17MB (PNGs + unused `_backup/`) to 2.5MB, while every
quality check available -- pixel diff at realistic render sizes, visual
crop comparison, and a real browser DPR3 screenshot -- found no
measurable or visible difference in what a user actually sees.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account: `npm run build` clean, `git diff --check` clean, zero console
errors/warnings, zero failed requests, zero `/brand/shiori/` 404s, zero
`scrollWidth`/`clientWidth` mismatch, at 1280 (both DPR1 and a real
DPR3 pass), 390, 375, and 320, across Home -> Analyze -> Reading ->
Study -> Vocab -> Shared Deck.

**Files changed:** 9 files in `frontend/public/brand/shiori/`
overwritten in place with 768px-resized content (same filenames); new
`docs/design/source-assets/shiori-webp-fullsize/` (9 files, Phase 142's
full-resolution WebPs preserved); that archive's `README.md` updated;
this `docs/design/DESIGN.md` entry. `Shiori.tsx` and `page.tsx`
(design-lab) both read during Round 0 but needed no edits -- the
resize required no code change at all.

**Commit-readiness:** yes -- build and diff-check clean, a
three-method quality verification (quantitative diff at realistic
render sizes, visual face-crop comparison, real-browser DPR3
screenshot) plus full-viewport 404/console/overflow QA all passed.

**Next phase candidates:** none opened here. Both resize tiers the
brief asked for were tried and resolved (768px adopted, 512px held
with data backing the hold); no further Shiori loading/encoding work
is outstanding. `book-cover-green-object-clean.webp` remains held per
Phase 135, unrelated to Shiori.

Phase 144 is the closeout review for the Phase 139-143 performance/
asset-cleanup arc: does everything those five phases changed still
hold, or did something drift/break across them. Every one of the
brief's 10 checklist items was verified directly against current state
rather than recalled from memory, since Phase 143 (the most recent)
could plausibly have touched something Phase 139-141 depended on.

File-level: `grep -rohE '/brand/(decor|shiori)/...'` across every
`.tsx`/`globals.css` produced the same 29-file reference set Phase 140
and 141 already established (20 decor + 9 Shiori), and every one of
those 29 was confirmed present on disk -- zero missing, zero orphaned.
`frontend/public/brand/decor/` holds exactly those 20 referenced files
plus the two `ASSET_MANIFEST.md`s (1.4MB); `frontend/public/brand/
shiori/` holds exactly the 9 Shiori WebPs, each still at its Phase 143
768px-resized byte size, confirmed by direct comparison against that
phase's own recorded output (2.5MB). `docs/design/source-assets/`
holds all five archives Phases 140-143 created
(`phase126/`, `phase127/`, `shiori-backup/`, `shiori-png-source/`,
`shiori-webp-fullsize/`, 50MB total) with nothing missing.

Code-level: Phase 139's `<span>`-based desk props (not `<img>`) are
still in `HomeDashboard.tsx`; Phase 141's `loading="lazy"`/
`decoding="async"`/`fetchPriority="low"` are still on `Shiori.tsx`'s
one shared `<img>`; Phase 142/143's `SHIORI_ASSET_MAP` still points at
`.webp` (not `.png`) for all 9 variants; `/design-lab/shiori/page.tsx`
has zero remaining `.png` mentions, confirmed by direct `grep` rather
than assuming Phase 142's text edit was complete.

Live verification (not just static checks): a real-browser walkthrough
at 1280/390/375/320 through Home -> Reading -> Study -> Vocab -> Shared
Deck -> Analyze -> Stats -> Feedback modal came back with zero console
errors, zero failed requests, zero `/brand/` 404s, and zero
`scrollWidth`/`clientWidth` mismatch at every viewport. Network-log
filtering for `source-assets`/`shiori-backup`/`shiori-png-source`/
`shiori-webp-fullsize` in the URL returned an empty list at every
viewport -- direct confirmation that the docs-level archives are
genuinely inert at runtime, not just assumed inert because nothing
references them in source. A final full-page screenshot of Home matched
every prior phase's screenshot pixel-for-pixel by eye.

No discrepancies were found -- not a documentation mismatch, not a
broken reference, not a regressed behavior. Per this phase's own
"기본은 no-code review" policy, nothing was changed.

**Closeout verdict: yes.** The Phase 139-143 arc is done: `frontend/
public/brand/decor/` (31MB -> 1.4MB), `frontend/public/brand/shiori/`
(17MB -> 2.5MB), combined deployed image footprint roughly 48MB ->
3.9MB, with zero visual or functional regression at any point along
the way and 50MB of genuine provenance preserved outside the deployed
path in `docs/design/source-assets/`.

**Files changed:** none. This phase's only output is verification.

**Commit-readiness:** n/a -- no changes to commit. Tree is identical to
Phase 143's committed state (confirmed via `git status --short`
returning empty before this DESIGN.md entry was added).

**Recommended next roadmap:** end the performance/asset-cleanup series
here, same call Phase 138 made for the visual redesign series. The one
remaining open item across both series (`book-cover-green-object-
clean.webp`, held per Phase 135) is a minor unresolved decorative
question, not a blocker. Future work should move to ordinary feature
work, or a genuinely new concern (e.g. `backend/` performance, test
coverage) rather than continuing to re-audit an asset pipeline this
phase found fully consistent.

Phase 145 opens a new series: a "casual cute" hard redesign against a
fresh mockup board (`docs/design/mockups/phase145-casual-cute-mockup-
board.png`) and asset set (`frontend/public/brand/decor/phase145/`),
explicitly instructed to remove conflicting old structure rather than
lightly reskin it. This entry covers Phase 145 (Home) only.

Round 0 found the new `home-cute-notebook-cover-object.webp` is a
fundamentally different *kind* of asset than the one it replaces:
Phase 126's `book-cover-green-surface-web.webp` was a tileable cloth
*texture* (no inherent shape, used full-bleed under a dark legibility
wash with title text painted on top), while the new asset is a real
photographed *object* -- a closed notebook, elastic strap and brass
snap physically in frame, natural soft shadow baked in (confirmed via
a Pillow composite onto a wood-tan test background before writing any
CSS -- clean alpha cutout, no vignette), landscape at its own fixed
~1.67:1 aspect ratio (1619x971). Doing the actual math on that ratio at
real mobile widths mattered: a box locked to the image's own aspect is
only ~170-210px tall at 320-390px wide, while the title+subtitle+CTA+
sample stack the old design painted onto the cover needs roughly
240px. Forcing the old "wash + white text on the photo" technique onto
this asset would have meant either cropping the object (cutting off
the spine/snap the photo exists to show -- exactly the kind of fake
compositing this whole redesign avoids) or squeezing text past
comfortable reading. Resolved by restructuring rather than
reskinning: `.home-cover-heading` (title/subtitle/CTA/sample, live
dark-ink text, no wash needed since it no longer sits on a photo) now
stacks above `.home-cover-object` (the notebook photo itself, shown
whole via `background-size: contain` at its own real aspect ratio, no
crop). This reads as "today's message, then a real notebook on the
desk below it" rather than "text embossed on a product photo," and
removes the legibility gamble the old wash-on-photo technique always
carried.

Two structures were removed outright because the new photo made them
redundant or explicitly forbidden, not just visually stale:
`.home-cover-strap` (a hand-authored SVG elastic band from Phase 124)
is gone -- the new photo already has its own elastic strap and snap
physically in frame, so the CSS one would have drawn a second,
duplicate strap next to the real one. `.home-cover-dots` (the bottom
pagination dots) is gone per this phase's explicit instruction; removing
them also removed the one thing anchoring `.home-cover`'s old fixed
`padding-bottom: 88px`, which no longer exists either. No CSS
`box-shadow` was added anywhere on the new cover -- the photo's own
baked-in shadow is the grounding cue, matching the "자연스럽게, 귀엽고
가볍게, 과한 luxury shadow 금지" instruction directly: the old
`box-shadow: 0 24px 48px rgba(37,43,30,0.32)` was a deliberately
dramatic, heavy shadow; the new cover has none of its own, only what
the photograph already shows.

A second, independent bug was found and fixed while implementing the
"wood desk to the bottom of the screen" requirement: `:root` (this
file's very first rule, `background: #f7f3ea`) gives `<html>` its own
explicit background, which per the CSS canvas-background-propagation
spec means `<body>`'s background (wood, at >=1024px) only ever painted
within `<body>`'s own content-height box, never propagated to fill the
rest of the scrollable canvas the way it would if `<html>` had no
background of its own. Every other tab's content already exceeds
viewport height, so this was invisible everywhere except Home, whose
short content stopped a full 182px above the bottom of a typical 900px
desktop viewport in the "before" screenshot, showing `:root`'s cream
fallback in a hard seam below the wood. Fixed with one line --
`min-height: 100vh` added to the existing `body` rule inside the same
`@media (min-width: 1024px)` block that already sets the wood
background -- rather than touching `:root` globally, since that keeps
the fix scoped to exactly the rule already responsible for "wood
should be the desktop backdrop," with no risk to any other tab's
layout (a `min-height` floor can only ever add height, never remove
content real screens already need).

Shiori and the washi-tape sticky note both moved from being positioned
against the old tall `.home-cover` to being positioned against the new
`.home-cover-object` specifically (bottom-right corner and top-left
corner of the photographed cover respectively) -- both now read as
resting on the physical book itself, not floating over an unrelated
text block. Desk props (Phase 133/139's leaf/tape/paperclip/pen) and
Home's shortcut sticky notes (Phase 134) needed no position changes at
all -- both are positioned against `.home-stage` independent of
`.home-cover`'s own internal structure, and a zoomed screenshot
confirmed they still cluster naturally around the new, shorter cover
(washi tape roll and paperclip now read as sitting on the desk right
beside the notebook, which if anything looks more intentional than
their old placement against a taller card).

One unrelated file became orphaned by this phase and was left alone
rather than cleaned up: `frontend/public/brand/decor/leather-strap-
snap.svg` (confirmed via `grep`, zero remaining references anywhere in
`frontend/`). Tiny (1.9KB) and out of scope for a Home-reconstruction
phase -- noted here rather than acted on, matching this project's
established "don't casually delete, don't silently ignore either"
convention for newly-unused assets.

Verified via headless Chrome (Windows-native, CDP) against a seeded
account, at 1280/390/375/320: `npm run build` clean, `git diff --check`
clean, zero console errors/warnings, zero failed requests, zero
`scrollWidth`/`clientWidth` mismatch at every viewport (one false-
positive along the way -- deleting `.next` while the dev server was
still running corrupted its build cache mid-session, producing a real
500 error and a misleading `sw:980` overflow reading; traced via the
dev server's own log, fixed by a clean restart, not a code change).
Real click-throughs confirmed the CTA still routes to Reading
(`.reading-panel` appears), all three shortcut stickers and the sample
link resolve to themselves under `elementFromPoint`, mobile drawer
opens then fully unmounts on close, the account menu panel opens, and
the feedback modal opens. A full-page screenshot comparison at all
three widths confirmed wood now reaches the bottom of the desktop
viewport with no seam, no pagination dots anywhere, and the shortcut
stickers are unchanged from Phase 134's already-real sticky-note
treatment.

**Actually removed:** `.home-cover-strap` (redundant with the new
photo's own strap), `.home-cover-dots` + its pagination dots, the dark
legibility-wash gradient + `box-shadow` that used to sit on
`.home-cover`, the old fixed portrait `min-height`/`padding-bottom`
sizing that assumed a tall card shape.

**Closer to the mockup:** the notebook now reads as one real object
resting on a desk that extends the full screen, not a texture-filled
card floating above a cream gap; shadow is light/natural (baked into
the photo) instead of a heavy drop shadow; no pagination UI breaking
the scene.

**Still short of the mockup:** the mockup's book has a character
resting on top of it as part of the illustration -- this phase uses
the real Shiori component in that same spot instead (per this whole
series' hard character-policy line), which is correct per instruction
but means the moment reads slightly less "hand-illustrated" than the
mockup's own art. Not a defect, an intentional divergence already
covered by the project's absolute character rule.

**Files changed:** `frontend/components/HomeDashboard.tsx`,
`frontend/app/globals.css`. New asset files
(`frontend/public/brand/decor/phase145/*`), the mockup board, and the
rebuild plan doc were supplied as phase input, not generated by this
phase -- left in place as-is (the `.png` sources alongside each
`.webp` are explicitly "retained for review/cropping" per that
folder's own `ASSET_MANIFEST.md`, not a leftover this phase should
clean up).

**Commit-readiness:** yes -- build and diff-check clean, full
4-viewport browser QA (hit-testing, real click-throughs on every
preserved interaction, drawer/account/feedback, a zoomed screenshot of
the desk-prop cluster) all passed with zero console errors and zero
failed requests.

**Next phase candidates:** Phase 146 (Vocab physical index tabs), per
the rebuild plan's suggested order. The `body`/`:root` canvas-
background fix in this phase is global (not Home-scoped), so it's
already protecting every other tab from the same latent seam risk --
worth keeping in mind if a future phase ever shortens another tab's
content below viewport height.

## Phase 146 -- Vocab Physical Index Tabs

Phase 146 rebuilds the Vocab tab's status-filter area against
`vocab-physical-index-tabs.webp`, replacing the old CSS-pill filter
chips with real protruding physical tab shapes, scoped to desktop
(`@media (min-width: 1024px)`) only -- the brief's target structure
(`.vocab-notebook-index` as a literal ring-bound index) only exists at
that breakpoint; mobile already uses a flat horizontal chip row that
the brief did not ask to change.

The source sprite has no alpha gaps between its 7 stacked tab shapes
(they're drawn touching/overlapping, unlike Phase 131's multi-object
crops), so the usual alpha-projection boundary scan produced only one
run. Switched to a row-by-row RGB color-boundary scan along a sample
column instead, which cleanly revealed 7 distinct color bands (green/
coral/yellow/blue/purple/orange/mint) and let each tab's true center
be read directly off the color sequence. Each `.vocab-filter-chip`
was then given the same sprite as its own fixed-size
`background-image` with a per-chip `background-position-y` computed
as `-(scaled_tab_center_px - chip_height/2)`; `align-items: flex-start`
was required on the `.vocab-status-filters` flex column so the fixed
chip width actually takes effect instead of being stretched.

Sizing the chips took three real-browser iterations, not source-image
math alone: 118px cut off several long labels into the sprite's spine/
ring area; 150px still cut off the three longest ("완벽히 아는 단어",
"분류되지 않음", "복습 예정만"); the final 172px/11.5px-font/15px-
left-padding state leaves only the very last character of those three
labels lightly touching the decorative ring graphic. Widening further
was capped by the rail's own measured clearance -- `getBoundingClientRect()`
showed the chip's right edge sitting only ~5px inside
`.vocab-notebook-index`'s own right edge at both 1280px and 1024px
(chip right 254 vs rail right 259 at 1280px; 249 vs 254 at 1024px) --
so accepted as a minor cosmetic detail rather than risked overflowing
into the center word-list column. Text stays fully legible at this
size (dark ink over the lighter ring color, full contrast, no
character actually obscured), which is why this was accepted rather
than chased further.

Active state uses a small colored dot (`::after`, 6x6px, reusing each
status's existing color token -- known/uncertain/unknown/unclassified)
plus a 9px `translateX` shift and a saturation/brightness bump, not a
border or box-shadow ring -- per this phase's explicit "표시는 작은
표식/색 강도/위치 이동 정도로, 두꺼운 테두리 버튼 금지" instruction.

**Actually removed/weakened:** `.vocab-notebook-index`'s old
480%-zoomed `vocab-ring-notebook-spread-web.webp` background and its
`border-radius: 4px 12px 12px 4px` (both gone -- the new sprite tabs
are the ring-notebook cue now, so the old zoomed-photo suggestion was
redundant); `.index-card-filter`'s dashed border, tinted background,
and washi-tape corner `::before` pseudo-element (all removed --
boxed panel chrome that visually competed with the new protruding-tab
structure); the old `.vocab-filter-chip` CSS-pill treatment and its
box-shadow active-state ring (replaced by the sprite + small-dot
treatment above).

**Closer to the mockup:** filters now read as real protruding index
tabs reaching out from a ring-bound spine, not rounded button chips
inside a dashed box; active state is a subtle mark/shift instead of a
thick outlined button, matching the mockup's understated "already-open
tab" cue.

**Word-list scannability:** untouched by construction -- no changes
were made to `.index-card-drawer`, `.vocabulary-index-row`, or any
row-level markup/CSS this phase; the center column remains the same
dense list, not a card grid.

**Functionality/API/SRS/storage:** unchanged. All edits this phase
were CSS-only inside `frontend/app/globals.css`'s existing
`@media (min-width: 1024px)` block; no `.tsx` file was touched, no
prop, handler, or backend call was added, removed, or renamed.

Verified via headless Chrome (Windows-native, CDP) against a freshly
seeded account (5 vocab items across mixed statuses), at
1280/1024/390/375/320:

- **Desktop (1280/1024):** zero `scrollWidth`/`clientWidth` mismatch,
  sprite loads (`200` on `vocab-physical-index-tabs.webp`), labels sit
  correctly on their tabs, deck/search/sort read as plain unboxed
  labels, word list and detail panel unchanged, zero console errors.
- **Mobile (390/375/320):** zero `scrollWidth`/`clientWidth` mismatch
  at all three widths; the desktop-only sprite rule does not apply
  (`background-image: none` confirmed via computed style, zero network
  requests for the sprite file); `.vocab-status-filters` stays in its
  original `flex-direction: row` chip layout; zero console
  errors/warnings; a full-page screenshot at 390px confirmed the
  existing mobile filter/search/sort block is visually unchanged from
  before this phase.
- **Interaction QA (real state changes, not just hit-tests):** search
  input actually filters the list (5 rows -> 1, `声` only, confirmed
  via a real `input` event through the native value setter); clicking
  a status tab moves the active class and the small dot to that tab
  and actually filters the list (1 matching row for "완벽히 아는
  단어"); the sort `<select>` firing a `change` event sends the
  correct request (`GET /vocab-items?deck_id=2&sort=wrong_desc`,
  confirmed via `Network.requestWillBeSent`) -- the on-screen order
  didn't visibly change only because all 5 seeded rows share
  `wrong_count: 0`, a seed-data tie, not a filter bug; the deck
  `<select>` lists and switches between real decks; the row toggle
  button (`aria-label*="펼치기"`) expands the row and populates the
  desktop right-hand detail panel; the "내 단어장 뜻 수정" trigger
  opens its textarea; the "삭제" button was confirmed reachable and
  correctly hit-testable via `elementFromPoint()` (not actually
  clicked through, to avoid destroying seed data mid-QA-pass -- delete
  wiring itself was not touched by this phase's CSS-only diff).

`npm run build` clean, `git diff --check` clean.

**Files changed:** `frontend/app/globals.css` only.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (desktop sprite/layout, mobile non-regression,
real interaction state changes across search/filter/sort/deck/expand/
edit/delete-reachability) all passed with zero console errors and
zero failed requests.

**Remaining risk:** the last character of the three longest filter
labels lightly touches the sprite's decorative ring at the chosen
172px chip width -- purely cosmetic (text stays fully legible), and
already at the practical width ceiling the rail's own measured
clearance allows without risking overflow into the center word-list
column.

**Next phase candidates:** Phase 147 (Deck Mini Bookshelf
Reconstruction), per the rebuild plan's suggested order.

## Phase 147 -- Deck Mini Bookshelf Reconstruction

Phase 147 rebuilds the Deck tab's shared-deck cards against
`deck-cute-cover-tile-atlas.webp`, replacing the old large solid-color
cover band with a real 10-cell cute cover atlas (5 cols x 2 rows) and
shrinking the whole grid so decks read as a shelf of small books,
matching the mockup board's Deck panel, instead of a grid of wide
color-blocked cards.

The atlas swap uncovered a real, pre-existing cascade bug rather than a
new one introduced by this phase: `BrandDeckCover` puts both
`brand-deck-cover` and a bare tone/level class (`jlpt-level-n5` etc.) on
the same div, and this exact bare class name is *also* used, completely
unrelated, by the small JLPT badge tag elsewhere on the same card
(`.jlpt-level-tag.jlpt-level-n5`). That badge's own rule --
`.jlpt-level-n5 { background: #a98a5c; }` -- uses the `background`
shorthand, which resets every other `background-*` longhand (image,
size, position) to its initial value for *any* element carrying that
bare class, cover div included. Both this rule and the base
`.brand-deck-cover { background-image: url(...); }` rule sit at the
same (0,1,0) specificity, so the winner was whichever came later in the
file -- the badge rule, as it happens, which silently zeroed out the
cover's background-image/size on every JLPT-tier card. Confirmed via
computed style before any visual fix was attempted (`background-image:
none`, `background-size: auto`, while `.brand-deck-cover.jlpt-level-n5`'s
own `background-color` fallback was still visibly painting flat color).
This collision predates this phase -- the old Phase 128 photo atlas used
the identical class-naming/selector shape and would have hit the same
bug, meaning the "photographed cover" almost certainly never actually
rendered even before this phase touched the file. Fixed by having the
compound `.brand-deck-cover.jlpt-level-n5` (etc.) selectors -- (0,2,0)
specificity, so they win regardless of source order -- redeclare
`background-image`/`background-repeat`/`background-size` themselves
instead of relying on inheritance from the lower-specificity base rule.
`.brand-deck-cover-mine`/`-shared` were never affected (those class
names don't collide with anything else).

The atlas's 10 cells map cleanly to a standard N-cell sprite formula
since the atlas is exactly 1536x1024px over a 5x2 grid (each cell is
exactly 1/5 the width, 1/2 the height): `background-size: 500% 200%`,
and cell (row r, col c) sits at `background-position: (c/4)*100%
(r/1)*100%`. The existing 7 tone/level variants (JLPT N5-N1, "내가
공유함", "공유 덱") were mapped onto 7 of the 10 cells -- N5 through N1
walk left-to-right across the atlas's top row (green -> cream -> coral
-> blue -> purple) so the ramp still reads as one ordered sequence the
way the old flat-color gradient did, just with real cover art; "내가
공유함"/"공유 덱" each got their own distinct bottom-row cell (mint,
gold) instead of reusing a JLPT tile, since the atlas has 3 cells to
spare. `background-color` on every variant is a same-family flat
fallback sampled directly from each chosen tile's fabric, for the case
the atlas fails to load.

Card/grid density: `.shared-deck-grid`'s column minimum shrank from
280px to 148px (desktop) so far more decks fit per shelf row;
`.shared-deck-card`'s own padding dropped from 16px to 12px and
`.brand-deck-cover`'s aspect-ratio changed from 335:405 (~0.83:1, close
to square) to the atlas's native 3:5 (a real portrait book-cover
ratio) -- together these are what make a resting card actually read as
a small book rather than a scaled-down version of the old wide card.
Title/count/imported/JLPT-badge/description were all demoted in place
(font-size only, scoped to `.shared-deck-card` so the opened detail
panel's own larger heading is untouched) to read as a small book-label
under the cover instead of competing with it for attention, matching
the brief's "낮은 위계" instruction. Buttons (owner cards can show up to
3: 상세 보기/가져오기/공유 취소) were left at their existing
`.compact-button` size and `.row-actions`'s existing `flex-wrap: wrap`
was relied on rather than shrunk further -- at ~150-180px card width
they now wrap onto 2 lines instead of staying on one, which is a
visible layout change but not a functional one (every button keeps its
full tap target), and was judged preferable to shrinking already-small
touch targets just to keep a stale one-line layout.

Mobile needed its own fix, not just a smaller version of the desktop
number: a single forced column (`grid-template-columns: 1fr`, unchanged
since long before this phase) combined with the new 3:5 cover ratio
made a full-width mobile card's cover balloon to roughly 500-600px
tall -- one oversized portrait image per row, arguably a bigger miss of
"작은 책들이 꽂힌 책장" than the "cards too small" risk the brief
explicitly names. Measuring the grid's own available width at each
tested mobile breakpoint (not assumed) showed why a single minmax
threshold didn't just work everywhere: 390px and 375px viewports leave
the grid ~300-320px wide (comfortable for two ~150px columns at almost
any reasonable minimum), but 320px leaves only ~248px -- page/detail
padding eats more of the viewport proportionally at the narrowest width
this phase tests, so a minimum higher than ~124px collapses back to one
column there specifically. Settled on `minmax(110px, 1fr)`, verified via
computed `grid-template-columns` to actually produce two columns at
320/375/390px (119px/147px/154px respectively), not just assumed from
the CSS. The existing `.shared-deck-section .shared-deck-card { width:
100% }` mobile override needed no change -- it already means "100% of
this grid cell," not "100% of the page," so it automatically shrank
along with the new column count.

**Actually removed/weakened:** the old large solid-color/photo cover
band at 335:405 (~0.83:1) aspect ratio, full negative-margin bleed onto
a ~280-340px-wide card -- replaced by the small 3:5 atlas-cover
treatment above; the oversized title (16px -> 12px), meta badges (12px
-> 10-11px), and description (unclamped size -> 11px) that used to read
as primary card content now read as a quiet label under the cover; the
single-column forced mobile grid that produced one oversized cover per
screen.

**Atlas tile mapping:** N5=row0/col0 (green), N4=row0/col1 (cream),
N3=row0/col2 (coral), N2=row0/col3 (blue), N1=row0/col4 (purple),
mine=row1/col2 (mint), shared=row1/col3 (gold) -- see the CSS comment
above `.brand-deck-cover.jlpt-level-n5` for the exact formula and the
cascade-bug writeup.

**Desktop (1280/1024):** verified via headless Chrome (Windows-native,
CDP) against two seeded accounts (an owner with a published JLPT-titled
deck, a published non-JLPT deck, and an unpublished deck; a subscriber
who imported one deck and left the JLPT deck un-imported). Zero
`scrollWidth`/`clientWidth` mismatch at both widths, atlas image loads
(`200`), zero console errors, real screenshots at both widths confirm
cards now read as small books resting on the shelf with visible cover
art (washi tape, ribbon, floral/label details from the atlas), not flat
color blocks.

**Mobile (390/375/320):** zero `scrollWidth`/`clientWidth` mismatch at
all three widths, atlas image still loads correctly (decks need it on
mobile too, unlike Phase 146's desktop-only index-tab sprite), zero
console errors. Screenshots at all three widths confirm two book covers
per row (not one oversized cover, not cards too small to read/tap) with
title/count/badge/description/buttons all legible and buttons still
individually reachable even where they wrap to two lines within a
~110-155px-wide card.

**Owner/newcomer/subscriber condition checks (real clicks, not just
hit-tests):** as the owner, 상세 보기 opened the detail panel with the
correct title and word list, then 닫기 closed it; 다시 공유하기 on the
already-unpublished "중단될 덱" (through a real `window.confirm` dialog,
auto-accepted via a `Page.javascriptDialogOpening` handler) flipped the
card to show 공유 취소 and dropped the "공유 중단됨" badge, confirmed via
a real API round-trip; 공유 취소 on the same deck immediately after
flipped it back to its original unpublished state (다시 공유하기 +
"공유 중단됨" badge again), so this test left the seed data exactly as
it found it. As the subscriber, the not-yet-imported JLPT deck's 학습
목록에 추가 button was clicked; afterward the card correctly shows 열기
and the "학습 목록에 있음" badge, confirming a real import went through
(not just a hit-test). One CDP-tooling lesson from this pass, not a
product bug: the first click on a `window.confirm`-gated button (공유
취소/다시 공유하기) hung the whole tab, since headless Chrome blocks
the entire renderer main thread on a native dialog with nothing to
answer it -- fixed by registering a `Page.javascriptDialogOpening` ->
auto-accept listener before any such click, not by changing app code.

**Functionality/API/SRS/storage/shared-deck logic:** unchanged. Every
edit this phase was CSS-only inside `frontend/app/globals.css`; no
`.tsx` file was touched, no button condition, handler, prop, or backend
call was added, removed, or renamed -- the owner/newcomer/subscriber
button matrix above is exactly the pre-existing logic, just visually
smaller.

`npm run build` clean, `git diff --check` clean.

**Files changed:** `frontend/app/globals.css` only.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (desktop cover-art rendering, mobile two-column
non-oversized layout, real owner/newcomer/subscriber interaction state
changes) all passed with zero console errors and zero failed requests.

**Remaining risk:** none identified specific to this phase's own
changes. Worth flagging for whoever next touches `BrandDeckCover` or
its bare tone/level class names: the cascade-bug fix here is scoped to
`.brand-deck-cover`'s own compound selectors, not a rename of the
colliding bare class names themselves (`jlpt-level-n5` etc. are still
shared between the cover and the unrelated badge tag) -- a future rule
added for either one, using the bare class without checking for this,
could reintroduce the same class of bug.

**Next phase candidates:** Phase 148 (Study Cute Board Reconstruction),
per the rebuild plan's suggested order.

## Phase 148 -- Study Cute Board Reconstruction

Phase 148 rebuilds the Study tab against `study-light-mint-felt-board.webp`
and the mockup board's panel 3, replacing the deep-green felt board and
the boxed quick-start card above it with a lighter, casual-cute pairing:
a light-mint board every session state sits on, and a flat heading with
small pinned memo tabs instead of a bordered dashboard widget choosing a
study mode.

`.study-board-scene` (shared by all four session states -- ready/empty/
active/complete, confirmed by reading `StudySection.tsx`'s render tree
before touching anything) swapped `study-felt-board-texture-web.webp`
(Phase 130's dark weave photo, `--notebook-cover-deep` fallback) for
`study-light-mint-felt-board.webp` -- same "uniform edge-to-edge weave,
no distinguishing shapes" property as the old photo, so `background-size:
cover` still needed no per-instance crop/position tuning at any board
height, including the very short boards ready/empty render with no card
stack yet. The top-sheen radial-gradient layer was dropped (it existed to
add depth to a dark surface; on the light photo it just read as a faint
haze), and the heavy `0 16px 34px rgba(37,43,30,0.22)` drop shadow was
cut down to a soft `0 10px 22px rgba(120,98,40,0.12)` -- not an opacity
tweak on the old dark image (the brief's explicit "금지"), a full asset
swap plus a shadow rewrite, matching the "light/natural, not heavy
luxury" shadow language every other Phase 145-147 surface already
adopted. The bottom-left leaf-sprig hint (`::after`, unrelated to the
board photo) needed no color change -- checked via a zoomed crop, the
existing `--sage-green` blobs still read with clear contrast against the
new light mint.

The quick-start hero above the board (`StudyQuickStartHero` /
`.study-hero-card`) was a bordered, shadowed `.hero-card` panel holding a
washi-tape strip at its corner -- the exact boxed-card recipe Phase 115/
146/147 already removed from Home/Vocab/Deck's own top headers, for the
identical reason: it read as an admin panel sitting above the tab's real
content. Flattened to the same unboxed heading-strip recipe those phases
use (a dashed bottom rule, no fill/border/shadow) -- one of this phase's
two JSX edits (the `hero-card` class and the now-meaningless
`.study-hero-tape` span were both removed from `StudySection.tsx`, since
a tape strip that exists to look like it's holding down a card's corner
has nothing left to hold down once that card has no boxed edge; same
call Phase 145 made dropping Home's old elastic-strap SVG for an
identical reason).

The quick-start mode grid (`.study-cta-grid`/`.study-cta-button`, 4
tiles: 오늘 복습 시작/새 단어 학습/어려운 단어 복습/덱별 학습) was a
single bordered/gradient-filled tray -- one dashboard widget choosing a
mode, not "학습 도구" resting on a board. The tray chrome was dropped
entirely (no border/background/shadow on the grid itself, CSS-only, no
JSX change); each tile became its own small pinned memo tab -- a light
`--panel-bg` chip with a colored dot "pin" marker (`::before`) at its top
edge and a slight per-tile rotation, the same "several small hand-placed
paper pieces" language this series already established for Vocab's index
tabs (Phase 146) and Deck's cover tag (Phase 147), done here with plain
CSS shapes since the mockup's tabs are flat-colored notes with no
photographed texture to crop from. Pin colors are purely decorative
markers (primary/`--sand-amber`/`--rose`/`--accent`) and don't reuse the
rating buttons' result colors, so nothing here could read as review-
result meaning. The primary "오늘 복습 시작" tile keeps its existing
solid-teal-gradient fill (now with a white pin dot) so it still visually
outranks the other three, matching the original "one loud action, three
quiet ones" hierarchy exactly -- only the shape changed. Mobile's
existing 3-column-plus-full-width-primary layout (Phase 82, already
CSS-only, already dropped the tray chrome at that breakpoint) needed no
structural change, just its now-orphaned
`.study-cta-button + .study-cta-button::before` divider-line override
removed as dead code once the base rule stopped drawing that divider.

Rating buttons/grid, the SRS review/rating handlers, and the flashcard
backing-sheet photo were deliberately left untouched, per the brief's
explicit protection: `.study-rating-grid`/`.rating-button`'s existing
"4 rubber-stamp seals" treatment (asymmetric radius, alternating tilt,
ink-flash press animation, the rose/sand-amber/primary/sage-green result
colors) already matched "paper stamp" language the brief asks for, so
Phase 148 changes zero lines of that CSS and zero lines of `onReview`/
`onShowAnswer`/`onStart`/`onQuickStart` wiring in `StudySection.tsx`.
`.study-card-backing-sheet` (the cream flashcard-stack photo peeking out
behind the active card) was checked against the new light board via
screenshot rather than assumed safe -- it reads clearly, if anything more
so than against the old dark felt, so it was left as-is exactly per the
brief's "live card readability는 우선한다" instruction (no conflict
found, no change needed).

**Actually removed/weakened:** the deep-green felt board photo + its
heavy 34px drop shadow + top-sheen highlight gradient (replaced by the
light-mint photo + a soft shadow, no highlight layer); `.study-hero-
card`'s border/panel-bg fill/accent-top-border/28px shadow (now a flat
dashed-underline heading strip); `.study-hero-tape`'s washi-tape decor
(removed outright, nothing left for it to hold down); `.study-cta-grid`'s
bordered/gradient-filled tray chrome (now no container styling at all,
each tile carries its own small pinned-tab look instead).

**Board asset application:** `background-image: url(".../study-light-
mint-felt-board.webp")`, `background-size: cover`, single layer (no
second gradient layer, unlike the old two-layer felt rule) -- verified
loading with a `200` via `Network.responseReceived` at every tested
viewport (1280/1024/390/375/320), since (unlike Phase 146's desktop-only
index-tab sprite) this board needs to render at every breakpoint the
same way the old dark board always did.

**Ready/empty/active/complete:** all four verified via headless Chrome
(Windows-native, CDP) against a seeded account (6 vocab items, mixed
statuses, `due_today_count: 4`). Ready (no session started) and empty
(a mode selected with 0 matching items, triggered by re-clicking "오늘
복습 시작" after exhausting it) both render `AppEmptyState` inside the
same light-mint `.study-board-scene`, no dark-board flash between them.
Active renders the flashcard + rating-stamp tray clearly on the mint
board, unchanged in every way except the board color underneath it.
Complete renders the receipt card (stats grid, Shiori success stamp,
restart/원문읽기/어휘노트 links) on the same board. Screenshots at each
state confirm all four now read as one continuous light-board world
instead of the ready/empty/complete states inheriting a heavy dark board
that only the active card's own white sheet ever fully offset visually.

**Rating stamp/SRS protection confirmed:** a full real review flow was
driven end-to-end via CDP click automation, not just visual inspection --
클릭 "오늘 복습 시작" -> 카드 로드 확인 (표면 텍스트 검증) -> "정답 보기"
클릭 -> 뜻/예문/4개 rating 버튼 렌더 확인 -> "보통" 클릭 -> 다음 카드로
실제 전환 확인 (단어 텍스트가 바뀜) -> 남은 카드 반복 rate -> 완료 화면
도달, `study-complete-stats`에 실제 세션 카운트(다시/어려움/보통/쉬움/
총 학습) 반영 확인. Re-run against a second, freshly-seeded account after
the dev-server restart below, with identical results. Zero console
errors/warnings throughout. No rating button class, color, icon, label,
or `onReview`/`onShowAnswer` handler was touched by this phase's diff --
confirmed both by the diff itself (CSS-only outside the two JSX
deletions noted above) and by this click-through actually completing a
session correctly.

**Mobile (390/375/390 heights matched to 812/844/640, plus 320/375/390
widths at the standard 1000px height for the overflow sweep):** zero
`scrollWidth`/`clientWidth` mismatch at every width, board image still
loads correctly (`200`) at every width, zero console errors. The rating
grid's actual concern -- "밀려서 fold 아래로 가려지는지" -- was checked
with real `getBoundingClientRect()` measurements after starting a
session and revealing the answer, at the three device-height combos the
existing `resolveScrollBehavior`/`scrollIntoView` safety-net code
comment already names (320x640, 375x812, 390x844): the rating grid's
full bounding box sits inside the viewport at all three (e.g. 320x640:
grid bottom 623 vs. viewport height 640) without needing that scroll
assist to fire at all, so the existing safety net remains exactly as
much a safety net as before -- unused in the common case, still present
for anything taller than a normal phone chrome/keyboard eats. The
quick-start pinned tabs also verified at mobile: primary tile keeps its
own full-width row, the three secondary tabs sit in their own row below
it with their pin dots and colors intact.

One QA-infrastructure lesson, not a product bug: running `npm run build`
while the QA dev server was still serving the same `frontend/` directory
corrupted its `.next` cache mid-session (the project's own documented
"never build+dev concurrently" quirk) -- surfaced as a real client-side
`__webpack_modules__[moduleId] is not a function` runtime error on the
next screenshot attempt. Confirmed as the known infra artifact (not a
code regression) by cross-checking against the *separate*, already-clean
`next build` output from moments earlier, then fixed by stopping the dev
server, deleting `.next`, and restarting fresh -- after which every
viewport and the full review-flow click-through were re-verified clean
against the new server, and the build's own already-clean output stood
as the actual build-validation result throughout.

`npm run build` clean, `git diff --check` clean.

**Files changed:** `frontend/app/globals.css`,
`frontend/components/StudySection.tsx` (two JSX deletions only: the
`hero-card` class and the `.study-hero-tape` span, both noted above --
no prop, handler, or SRS-facing markup changed).

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (board asset loading, all 4 session states on one
consistent light-board language, mobile rating-grid fold clearance,
pinned quick-start tabs) plus a real end-to-end review-flow click-through
all passed with zero console errors and zero failed requests.

**Remaining risk:** none identified specific to this phase's own changes.
`study-felt-board-texture-web.webp` (Phase 130's now-unreferenced dark
board photo) was left in place rather than deleted, matching this
project's established "note, don't silently clean up" convention for a
newly-orphaned asset -- confirmed via `grep` that no `.tsx`/`.css` file
still references it.

**Next phase candidates:** Phase 149 (Reading Selected Strip
Visibility), per the rebuild plan's suggested order.

## Phase 149 -- Vocab Full Reconstruction / Physical Index Correction

Phase 149 is a correction phase, not the next item on the rebuild
plan's suggested order (that was Reading Selected Strip Visibility --
deferred). Real 1280/1024 screenshots of Phase 146's Vocab tab showed
it landing far short of "index tabbed notebook": the physical-tab
sprite's longest labels still brushed its decorative ring, the top of
the screen still read as a boxed admin panel (stat-pill chip row + a
row of full gradient CTA buttons), and the detail column's stretched
photo crop looked like a decoration bolted onto an otherwise plain
white column, not a page of the same notebook as the list next to it.
The brief explicitly permitted abandoning both photographed-asset
techniques in favor of a more robust CSS-built structure, and this
phase does exactly that.

**Removed/replaced (per the phase brief's own request, listed
first):**
- **`.vocab-hero-card` boxed hero** (`panel-card-header` + a
  `vocab-hero-chip-row` of rounded stat pills + a `landing-hero-actions`
  row of full-gradient webapp buttons) -- gone. Replaced by
  `.vocab-notebook-header`: the same title/subtitle, `.vocab-pinned-notes`
  (small paper tags pinned at a slight alternating rotation, reusing the
  washi-tape `rgba(217,122,74,...)` accent `.vocab-page-guide` already
  established), and `.vocab-bookmark-actions` (small notched bookmark-flag
  labels for 이 덱 학습하기/원문 읽기, reusing the same right-notch
  clip-path `.vocab-item-status-wrap` already established elsewhere in
  the brand system, not a new shape).
- **Phase 145's `vocab-physical-index-tabs.webp` sprite** -- dropped
  entirely (no longer referenced anywhere in `globals.css`). Its
  per-chip fixed 172px width was the actual root cause of the label/ring
  overlap the brief flagged as a correction target, not a minor
  cosmetic detail: a raster crop has no way to grow with a long Korean
  label. Replaced with real CSS-built tabs (flat status-tinted fill,
  `width: 100%` of a widened, fluid rail column) that structurally
  cannot run out of room.
- **Phase 129's `vocab-ring-notebook-spread-web.webp` crop behind the
  detail column** (`background-size: 260% auto`) -- dropped. Replaced
  with the exact same flat `var(--paper-bg)` + repeating-rule-line +
  red-margin-line recipe now shared with the list column, so the two
  columns read as two pages of one notebook instead of "photo column"
  next to "plain column."
- The middle list column's previously bare flat tone (no texture at
  all, the actual "흰 배경 위에 대충" complaint) -- given the same
  ruled-line + margin-rule background as the detail column.

**New structure:**
- `.vocab-notebook-header`: unboxed title, pinned-note stat tags,
  bookmark-flag actions -- see removals above.
- Left rail (`.vocab-notebook-index`): widened
  (`minmax(178px,210px)`, was `minmax(150px,190px)`) so real CSS tabs
  have genuine surface area; each tab is `width: 100%` with a
  status-tinted flat fill (resting) or a deep solid fill (active,
  `.vocab-filter-chip-active`), rounded on its protruding outer corner,
  square on the spine-side inner corner. `VocabSection.tsx` now applies
  each status's color class regardless of active state (was
  active-only), so tabs are color-coded even at rest. A small
  ring/rivet mark (`::after`) sits inside a reserved 28px right-padding
  gutter on every tab -- structurally incapable of touching the label
  text at any label length, unlike the old per-chip pixel math.
- Middle list (`.vocab-notebook-pages`): unchanged dense
  `.vocabulary-index-row` list (scan-first, per the brief), now sitting
  on the shared ruled-paper texture instead of bare flat color.
- Right detail (`.vocab-notebook-detail`, now also `.paper-corner` in
  JSX): same ruled-paper/margin-rule tone as the list, plus the
  existing sticky positioning and wire-paperclip pseudo-elements
  (unchanged, already lightweight CSS, not image-based).

**Two real-browser regressions found and fixed during QA, not just
declared clean from source reading:**
1. Widening the rail to `minmax(196px,248px)` (first attempt) starved
   the middle column at 1024px specifically -- CSS Grid gives
   `minmax(min,max)` tracks their max before handing leftover space to
   the `1fr` track, so the rail ate space the list column needed,
   wrapping "저장된 단어장" into 3 lines and clipping the "복습 예정"
   chip. Fixed by re-measuring actual column widths via
   `getBoundingClientRect()` (not guessing) and settling on
   `minmax(178px,210px)` rail / `minmax(250px,300px)` detail, plus a
   narrow scoped `.vocab-notebook-pages .result-heading { flex-wrap:
   wrap }` (button drops to its own line before the title text wraps --
   `.result-heading` itself is shared with other tabs and was left
   untouched).
2. The bookmark-flag `clip-path` notch used a percentage point (`88%`),
   which scales with element width -- harmless at a normal button
   width, but on mobile where `.vocab-bookmark-action-primary` goes
   full-width (`width: 100%` under the app's existing 640px touch-target
   rule) it turned into a huge arrow spanning much of the button.
   Fixed by switching the notch to a fixed-pixel offset
   (`calc(100% - 16px)`) so the shape reads the same small flag at any
   width.

**Functionality/API/SRS/storage:** unchanged. deck picker, search,
status filter, sort, due-only filter, row expand/detail selection,
meaning edit, meaning report, status update, delete, deck
management/share/custom-term/import/export, and the Reading/Study nav
callbacks are all the same handlers wired to the same props -- only two
small, additive JSX changes touched behavior-adjacent code: the status
filter chips now always carry their color class (was active-only, a
CSS-only visual change) and the due-only chip gained a
`vocab-filter-due` class for its own resting tint.

**Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database** (`backend/vocab.db`, the dev-mode auto-user's
"리제로" deck, 5 items across known/uncertain/unknown, seeded by an
earlier phase -- not the Neon production database):
- **Desktop (1280/1024):** zero old-hero/sprite remnants
  (`.vocab-hero-card` absent, zero requests to either dropped asset
  file), 6 status tabs render at their full color-coded width with the
  longest label ("완벽히 아는 단어") sitting well clear of its ring
  mark, deck picker switches decks, search "가" cut 5 rows to 1, the
  known-status tab filtered to 2 rows and moved its own active
  highlight, sort fired the expected request, row expand populated the
  right-hand detail page (not a separate idle image), meaning-edit
  form opened, delete button hit-test-confirmed reachable (not
  clicked), zero `scrollWidth`/`clientWidth` mismatch at either width,
  zero console errors/warnings, zero failed network requests.
- **Mobile (390/375/320):** zero overflow mismatch at all three
  widths, status filter row stays its original flat `flex-direction:
  row` chip layout (untouched), row expand/meaning-edit-form-open/
  delete-reachability all confirmed via DOM state and a scrolled
  screenshot, primary bookmark action's fixed-pixel notch confirmed
  small and consistent (not the runaway-arrow regression above), zero
  console errors, zero failed requests.

`npm run build` clean (fresh `.next`, dev server stopped first per this
project's WSL/Windows build-vs-dev conflict note), `git diff --check`
clean.

**Files changed:** `frontend/components/VocabSection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural-removal confirmation, real
deck/search/filter/sort/expand/meaning-edit/delete-reachability
interaction QA, two real regressions found and fixed via
`getBoundingClientRect()` measurement rather than assumption) all
passed with zero console errors and zero failed requests.

**Remaining risk:** `vocab-physical-index-tabs.webp` and the desktop
per-column use of `vocab-ring-notebook-spread-web.webp` are now both
unreferenced in `globals.css` (left in place, matching this project's
"note, don't silently clean up" convention rather than deleting
assets outside this phase's explicit scope). The `.result-heading`
button-wraps-first fix is scoped to `.vocab-notebook-pages` only and
was not applied to the equivalent shared heading on other tabs, since
none of them were reported as broken and widening this fix's blast
radius wasn't asked for.

**Next phase candidates:** Phase 150 (Reading Selected Strip
Visibility), continuing the rebuild plan's suggested order now that
this correction phase is resolved.

## Phase 150 -- Reading Full Surface Correction / Open Book Interaction Reconstruction

Phase 150 covers the whole Reading tab in one correction pass -- the
start screen and the result screen's controls together, not "fix the
one button." Real 1280/390 screenshots of the pre-Phase state showed
three concrete problems: the analyze CTA (`.reader-start-cta`) was a
full-`width:100%` gradient pill stretching across the entire open
book, reading as an admin action bar cutting the page in half; the
pre-analyze textarea and the post-analyze reader text both sat
directly on `open-book-spread-web.webp`/used the *same*
`paper-page-texture-web.webp` family the book itself used, so input
surface, reader surface, and book background all read as one
undifferentiated beige; and the result screen's "선택한 단어"/저장
가능" count row sat as plain text on the bare page background with
nothing marking it as its own object, right next to a second full
`width:100%` "원문 펼치기" button on the collapsed re-edit form.

**Removed/replaced (listed first, per the phase brief's own
requirement):**
- **`.reader-start-cta`'s `width: 100%; border-radius: 999px` full-bar
  shape** -- gone. `.reader-start-footer` changed from a
  `justify-items: stretch` grid to a plain flex row (deck picker on
  one side, CTA on the other, neither stretching), and the CTA itself
  is now sized by a new shared `.reader-bookmark-button` class: a
  small notched flag (fixed-pixel `clip-path`, not a percentage
  point -- see below), colored with Reading's own `--screen-accent`
  ink-green instead of the app's generic teal `--primary` gradient, so
  it reads as this book's own stationery action instead of a borrowed
  admin control. The same class was applied to `.reading-open-button`
  (the result screen's own "원문 펼치기", previously already
  `flex: 0 0 auto` but still the same generic teal gradient) so
  start and result use the identical CTA language.
- **The textarea/book-background collision at >=1024px** --
  `.reader-start-page textarea` used to paint the exact same
  `paper-page-texture-web.webp` the surrounding `.reader-start-scene`
  paints via `open-book-spread-web.webp` -- two photos from the same
  paper family, nearly indistinguishable in a real screenshot. At
  1024px+ only (below that, the textarea's photo is the *only* page
  surface on screen, so it was left alone there), the textarea now
  uses a flat `var(--panel-bg)` fill, a repeating-linear-gradient
  ruled-line texture of its own, and an inset shadow -- a real
  material difference (matte pasted sheet vs. the busier photo grain
  around it), not just a different crop of the same photo.
- **The save-dock count row's plain-text-on-bare-page look** -- gone.
  `.save-dock-count` no longer shares `.save-tray-shelf-row` with the
  primary button; it now sits alone inside a new
  `.save-dock-memo-strip`, and the primary save button/`"바로 복습"`
  CTA both moved to the same `.reader-bookmark-button` family as the
  analyze CTA (a small notched tag, not a full gradient button).

**New start-screen structure:** title/subtitle unchanged (Phase 121
already had these right); the form footer is a plain row holding a
small rounded paper-tag deck picker (`.reading-deck-picker`, was a
bare underline field, now a `soft-bg` pill so it reads as a label
rather than a form control) and the small notched analyze CTA,
neither full-width; the textarea itself keeps its "IS the page"
identity below 1024px and becomes a distinctly lighter, ruled,
inset-shadowed "pasted sheet" at 1024px+, clearly layered above (not
blended into) the book photo behind it.

**New result-screen controls structure:** the reader text
(`.reader-text`) gets a soft, mostly-opaque `rgba(253,249,238,0.72)`
wash + very light inset shadow behind it at 1024px+ only (mobile/
tablet already have a single uncontested photo texture with nothing
competing underneath) -- no border, no hard card edge, just enough
lift that the original-text column is unambiguously "the most
legible surface on the page" per the brief's own requirement, without
reading as a second floating panel next to the photo. Below it, the
save dock is now two visually distinct pieces: `.save-dock-memo-strip`
(the count/badges, on `reading-selected-memo-strip.webp`) and, in its
own row below, the primary save button or the idle Shiori hint --
followed by the unchanged post-save message and the
`.reading-summary-cta-ready`/`.reading-summary-link-button` pair
(the review CTA now also a notched bookmark tag; the vocab-note link
stays a plain underlined text link, untouched).

**`reading-selected-memo-strip.webp` (the actual asset determining
this phase's biggest layout change):** committed in Phase 145 and
explicitly reserved by that phase's own rebuild plan for exactly this
spot ("선택한 단어는 loose memo strip 위에"), but never wired up until
now. `.save-dock-memo-strip` uses it as a real `background-image`,
`background-size: 100% 100%` (a deliberate non-uniform stretch, not
`cover` -- the source is a very long, ~13%-decorated-at-each-end
strip, and `cover` would crop one taped end off at most container
aspect ratios), with **percentage** padding (`14px 13%`) reserving
room for the live count/badge text -- the same "don't depend on a
fixed-pixel crop" lesson Phase 149 already learned the hard way on
Vocab's index tabs, applied proactively here instead of being
discovered as a bug. Because the image's own blank center is large
and the content it holds is a single short line, this is much lower-
risk than Phase 146's sprite ever was: no per-item position math,
generous clearance at every width tested.

**Fixed-pixel bookmark notch, not a percentage one:** `.reader-
bookmark-button`'s `clip-path` uses `calc(100% - 18px)` for its notch
point rather than a percentage (Vocab's Phase 149 equivalent used
`88%`). Phase 149 found a percentage notch balloons into a huge arrow
once a button goes full-width on mobile; this phase applied that fix
from the start rather than re-discovering it, which is why
`.save-dock-primary-button` (still intentionally full-width on
mobile, unchanged from before this phase) renders correctly as a
wide bar with a small, constant-size flag cut, not a giant triangle.
`.reader-bookmark-button` deliberately does not set `width` itself --
each call site's own existing width rule (mobile full-bar for the
save button, `width: auto` for the analyze/review CTAs) keeps working
unmodified; `.reader-start-cta` gained an explicit `width: auto` (it
had none before, since it used to always be 100%) so it opts out of
the app-wide mobile `button { width: 100% }` rule -- verified via
`getBoundingClientRect()` at 390/375/320, not assumed: 152px wide at
every mobile width tested, never full-bar.

**Not touched, by design:** `TokenDetailSheet.tsx` (per the brief),
`ReaderMode.tsx` (no `.tsx` edits at all -- every fix here is a CSS
selector or class-name change on markup `ReaderMode.tsx` already
emits), `ReadingVocabPanel.tsx` (the Phase 89/91 candidate-tray
horizontal-strip structure, quick-select, search/filter -- zero edits),
the Phase 122 inspector spine/binding (`.reader-inspector-rail::after`,
`.reader-spine-clip`, `.reader-inspector-tabs`), and every `/analyze`
request/response shape, token-classification policy, unknown/uncertain
auto-save behavior, and known/unclassified local-only policy.

Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database (`backend/vocab.db`, the dev-mode auto-user), with
`localStorage.clear()` before each fresh-state check so no stale
reading-session draft could mask a real regression:

- **Desktop (1280/1024):** old admin-bar CTA confirmed gone both by
  screenshot and by measurement (`.reader-start-cta` 152px wide inside
  a 1106px-wide footer, not full-width); textarea vs. book-photo
  layering confirmed via computed style (`background-color:
  rgb(253,249,238)` + a real inset `box-shadow`, distinct from the
  scene's own photo); start and result screens both read as the same
  open-book world; save-dock memo strip renders correctly with the
  live count/badges clear of its taped corners at both widths; full
  functional loop re-verified end to end: sample fill -> deck select
  (4 real decks listed) -> analyze -> 13 tokens rendered -> token click
  -> inspector opens -> classify "모름" -> real `200` `/vocab-items`
  auto-save request -> candidate tray open -> quick-select "모르는
  단어 선택" (13 selected) -> "선택한 단어 저장" -> real save response
  ("12개를 저장했습니다, 이미 저장된 단어 1개는 건너뛰었습니다") ->
  review CTA appears, now a green notched tag (confirmed via computed
  `clip-path` and `background-color: rgb(63,107,74)`, the ink-green
  `--screen-accent`). Zero `scrollWidth`/`clientWidth` mismatch, zero
  console errors/warnings, zero failed requests at either width.
- **Mobile (390/375/320):** zero overflow mismatch at all three widths
  across start, result, and inspector-open states; CTA/deck-picker/
  sample-sticker/textarea confirmed non-overlapping via
  `getBoundingClientRect()` intersection checks, not just a visual
  read; the analyze CTA measured 152px wide at every one of the three
  widths (the explicit mobile-width-guard requirement) -- an initial
  eyeballed read of a scaled-down full-page screenshot looked like it
  might still be full-width, but a precise clipped re-screenshot of
  just that region at 1:1 scale confirmed the measurement was correct
  and the visual impression was a misjudgment of the small preview
  image, not a real bug; token-click opens the bottom sheet inspector
  with the reader text's top still at `y: 163` (well above the sheet,
  matching Phase 94's untouched 42vh cap -- several lines of original
  text stay legible above it); zero console errors, zero failed
  requests.

`npm run build` clean (dev server stopped and `.next` removed first,
per this project's WSL/Windows build-vs-dev conflict note), `git diff
--check` clean.

**Files changed:** `frontend/components/ReadingTab.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural-removal confirmation via both
screenshot and precise measurement, full functional loop re-verified
including auto-save/quick-select/batch-save/review-CTA, mobile
non-overlap and inspector-visibility checks) all passed with zero
console errors and zero failed requests.

**Remaining risk:** `.save-dock-memo-strip`'s `background-size: 100%
100%` non-uniform stretch was only checked at the four required
viewport widths, not the full range in between -- the source image's
taped corners could look mildly distorted at an untested intermediate
width, though the risk is low given the corners are organic torn/tape
shapes (not geometric ones sensitive to aspect distortion) and the
technique already reads correctly at every width actually tested.
`.reading-summary-cta-ready`'s pre-existing `flex: 2 1 240px` sizing
inside `.reading-summary-next-actions` was left as-is (unrelated to
this phase's named targets) -- it now also carries
`.reader-bookmark-button`'s box-shadow, which a later cascade rule
(`.reading-summary-cta-ready`'s own accent-ring `box-shadow`) still
overrides at rest, so the ring shows at rest and the lift-shadow only
appears on hover; a cosmetic layering quirk, not a functional one.

**Next phase candidates:** Phase 150's own original rebuild-plan slot
(Reading/Classify IA decision -- whether Reading and Classify should
stay two equal primary tabs, per `phase145-casual-cute-tab-rebuild-
plan.md`'s item 6) is the last unaddressed item from that plan; no
further "casual cute" correction passes are currently flagged as
needed on any tab.

## Phase 151 -- Home Hero Scene Scale Correction / Full First-Viewport Reconstruction

Phase 151 is a correction pass on Home's first viewport, not a new
tab rebuild -- Phase 145 already established the right *ingredients*
(a real photographed notebook object, bare icon+label shortcuts, no
boxed cards), but a real 1280 screenshot showed them scattered too
small and too far apart: the book capped at `max-width:420px` sitting
alone inside a much wider (~700px+) grid column, a large band of bare
wood between it and the shortcut column, and the heading text sitting
in its own row above the book with a real gap rather than reading as
attached to it.

**Removed:**
- **The book's `max-width:420px` cap** -- the actual root cause of
  the empty-wood complaint. The book's own grid column was ~700px
  wide at 1280 (a `1.55fr` share of the stage), so the old cap left
  roughly 280-300px of pure bare wood between the book's right edge
  and the sticky-note column, before the grid's own gap even started.
- **`.home-cover`'s `display:grid; gap:18px` stacked-row layout** --
  gone. The heading and the book were two independent rows with real
  space between them; nothing physically connected "text" to "book."
- **`.home-cover-sticky`** (the small standalone "오늘도 책장을
  열어요" tag pinned to the book's corner, plus its washi-tape
  accent) -- removed outright rather than kept alongside the new
  heading note. Both were doing the same job (a note pinned to the
  book's top edge) in the same spot; keeping both would have stacked
  two competing notes on each other.
- **The desk props' Phase 133 scale and edge-only placement** -- a
  58-104px leaf, a 32-48px paperclip, etc., scattered only at the
  book's own four corners, reading as stray specks against the much
  larger scene rather than real objects on the desk.

**New hero cluster structure:** `.home-cover-heading` is now a real
paper note (`var(--panel-bg)` background, soft shadow, a slight
rotation, the same asymmetric-corner language every other pinned
note/index-card in the app already uses) instead of bare text. A
negative `margin-bottom` (`-34px` mobile, `-72px` desktop) pulls it
down to physically overlap the book's own top edge -- `.home-cover`
dropped `display:grid` entirely (plain block flow) specifically so
this margin-based overlap works predictably, rather than fighting
CSS Grid's own track-sizing rules for negative margins. `z-index`
puts the note above the book in paint order (DOM order alone would
have painted the book, which comes second, on top of the note where
they overlap). This is literally the phase brief's own first
suggested direction -- "제목/CTA를 책 위 종이 라벨/스티커 묶음처럼
배치" -- implemented with an existing, established material (a
pinned note) rather than trying to paint live text directly onto the
photographed fabric cover, which risked real contrast problems for
`var(--muted)` subtitle text against a medium-sage-green photo.

**Book scale + column balance (desktop, >=1024px):** `.home-cover-
object`'s max-width raised from 420px to 640px (was capped well
under its own column's real width); `.home-stage`'s column ratio
tightened from `1.55fr/0.9fr` to `1.4fr/0.85fr` and its gap shrunk
from 36px to 22px, closing most of the remaining aisle between the
book and the shortcut column. `.home-stage` switched from
`align-items: start` to `stretch`, and `.home-stickers` gained
`justify-content: space-between` -- the three sticky notes, naturally
shorter than the now much taller book+note cluster, now stretch and
distribute across that full column height instead of clumping at the
top with dead space below them (visible in the pre-Phase screenshot:
stickers stopped around the column's 40% mark while the book column
ran to 100%).

**Desk props:** all four (leaf/tape/paperclip/pen) scaled up roughly
1.5-1.7x. The pen prop moved from `right: -18px` (bleeding off the
far right edge of the *entire* scene, past the shortcut column
entirely) to `left: 61.5%` (roughly the book/shortcut column
boundary, since `.home-desk-props` spans the whole stage via
`inset:0`) -- it's now the one prop that visually bridges the two
clusters instead of every prop orbiting the book alone. The leaf
prop's position was tuned twice: an initial `top:-54px` (matching its
larger new size) put it 3-40px into the desktop toolbar's own box
(caught via `getBoundingClientRect()` on both elements, not
eyeballing), pulled back to `top:-12px` so it clears the toolbar with
a few px to spare, confirmed via a clipped 1:1 screenshot of that
exact corner.

**Not touched, by design:** the desktop toolbar itself (`.app-
toolbar--minimal`'s translucent-strip treatment), routing/tab
callbacks (`onStartReading`/`onTryWithSample`/`onGoToVocab`/
`onStartTodayReview`/`onGoToSharedDecks`/`onOpenAccount` all still
wired to the same buttons, unchanged), the account-modal-on-review-
click behavior for the dev user (`isDevUser ? onOpenAccount :
onStartTodayReview}`, pre-existing, re-verified working), Shiori
usage (`ShioriCharacter variant="default"` on the book,
`variant="review"` on the shortcut -- no new variant, no new
character), and no pagination dots were reintroduced.

Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database (`backend/vocab.db`, the dev-mode auto-user):

- **Desktop (1280/1024):** book confirmed as the dominant object in
  both screenshot and by measurement (640px wide at 1280, was
  420px); heading note visually overlaps the book's top-left corner
  (physical cluster, not two separate rows); sticky notes now
  stretch across the same height as the book column; desk props
  read as real objects at this scale, with the enlarged pen bridging
  the book/shortcut gap; leaf/toolbar clearance re-confirmed via
  `getBoundingClientRect()` after the position fix. Zero
  `scrollWidth`/`clientWidth` mismatch, zero console errors/warnings,
  zero failed requests at either width.
- **Functional loop (1280):** CTA click navigated to Reading (heading
  "원문으로 읽고 바로 노트에 담기"); sample link filled the reading
  textarea with the exact `SAMPLE_TEXT`; 단어장 shortcut navigated to
  Vocab (heading "내 단어장"); 덱 shortcut navigated to Shared Deck
  (heading "덱 책장"); 복습 shortcut correctly opened the account
  panel instead of navigating (`account-menu-panel` appeared in the
  DOM), matching the pre-existing dev-user-only behavior, not a
  regression; toolbar 피드백/로그인 buttons and the mobile drawer
  trigger (aria-label "메뉴 열기") all confirmed present and
  functional.
- **Mobile (390/375/320):** zero overflow mismatch at all three
  widths; book/heading/CTA read as one continuous cluster with no
  visible seam; shortcut row sits directly under the book, not a
  detached card strip; the CTA stayed a rounded pill at its normal
  content width (unchanged from before this phase -- Home's CTA was
  never affected by the admin-bar problem Reading's Phase 150 CTA
  had, since it already used the same family of pill button
  throughout).

`npm run build` clean (dev server stopped and `.next` removed first,
per this project's WSL/Windows build-vs-dev conflict note), `git diff
--check` clean.

**Files changed:** `frontend/components/HomeDashboard.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural composition confirmed via both
screenshot and precise measurement, full functional loop re-verified
including the dev-user account-panel edge case, toolbar/drawer
reachability) all passed with zero console errors and zero failed
requests.

**Remaining risk:** the heading note's negative-margin overlap
amount (`-34px`/`-72px`) was tuned against the specific title/
subtitle copy currently in `HomeDashboard.tsx` ("오늘도 한 문장, 한
단어." + one subtitle line) -- meaningfully longer copy in either
line would grow the note's natural height and could push the overlap
either too shallow (barely touching the book) or, if the note's own
`padding-bottom` isn't also adjusted, too deep into the book's own
visible cover art. Not a concern for the current copy (verified at
all five required widths), but worth re-checking if the heading copy
ever changes. The four desk props' new positions were tuned at the
four required viewports only, not the full range between them.

**Next phase candidates:** Phase 150's own deferred item (Reading/
Classify IA decision, `phase145-casual-cute-tab-rebuild-plan.md`
item 6) remains the last open item from that plan. No further "casual
cute" correction passes are currently flagged as needed on any tab --
Vocab (149), Reading (150), and Home (151) have each had a full
first-viewport correction pass.

## Phase 152 -- Deck Cover Simplification / Bookshelf Density Correction

Phase 152 corrects Phase 147's own "mini bookshelf" cards: the
mockup-aligned *idea* (small book covers on a shelf) was right, but
`deck-cute-cover-tile-atlas.webp` -- a tall 3:5 portrait illustration
per cover, complete with its own baked-in florals/washi-tape/blank
oval "label plate" -- left nowhere for this card's actual live fields
(title, JLPT/unpublished badge, word count, imported badge,
description, up to 3 action buttons) to sit. A real 1280 screenshot
against this project's own seed data (6 real shared decks) showed
every one of those fields pushed below the tall cover, ballooning a
card meant to be ~150-180px wide into ~500-600px tall, with the
atlas's own blank label plate going completely unused.

**Removed:**
- **`deck-cute-cover-tile-atlas.webp` from the shelf-card cover
  entirely** -- not weakened, dropped. The atlas is now referenced
  nowhere in `globals.css` (confirmed via `grep`). It was the direct
  cause of the oversized-card problem: a photographed illustration
  has no way to make room for live text the way a flat CSS surface
  can.
- **The cover's tall `aspect-ratio: 3/5` box and its dark semi-opaque
  icon+label plate** (`.brand-deck-cover-tag`'s old `rgba(28,22,12,
  0.62)` backing, needed only to guarantee contrast against 5 very
  different photographed cover colors) -- both gone along with the
  photo they existed to sit on.
- **`.landing-hero-actions`'s plain `.secondary-button`/`.ghost-button`
  pair** ("어휘 노트 보기"/"새로고침") -- the exact same full boxed
  button chrome as any generic web-app action, which this phase's own
  "웹 알림 바처럼 보이면 실패" instruction flags directly.
- **`.info-strip`'s bordered/filled card chrome** on both the "가져온
  덱은…" and "JLPT 추천 어휘 덱은…" notices -- was a bordered,
  white-filled pill reading as a system alert bar.
- **The `auto-fit` grid's tendency to leave a large bare-wood gap**
  whenever the deck count didn't evenly divide the row (confirmed
  against this project's real 6-deck seed data, not assumed).

**New mini-book/label structure:** `.brand-deck-cover` is now a short
(34px) flat-color band -- a "spine cap", not a full front cover --
using the *exact same* N5-N1 warm ramp colors `.jlpt-level-n5..n1`
already use elsewhere on the same card (one palette, not a second
one), plus two new tones for "내가 공유함"/"공유 덱". The icon+label
tag now sits directly in that band as plain white text (the band's
own flat color is dark enough at every variant for reliable contrast,
confirmed by screenshot, so the separate dark backing plate is no
longer needed). Everything else -- title, badges, word count,
description, buttons -- sits in the label area directly below the
band, completely unchanged in DOM position; shrinking the cover is
what gives this area room to hold everything without pushing content
out of a reasonable card height, not a restructuring of the label
area itself. Real screenshots confirm a shelf card is now ~220-260px
tall (was ~500-600px) with every field visible without scrolling.

**Cascade-bug note carried forward from Phase 147:** the same JLPT
badge tag elsewhere on this card (`.jlpt-level-tag`) still reuses the
bare `jlpt-level-n5`..`n1` class names Phase 147 found colliding with
this cover's own tone modifier (both `.brand-deck-cover` and the badge
put the same bare class on different elements; the badge's `background`
shorthand rule resets any *other* element carrying that class's
background-image to `none`). That collision can no longer actually
break anything here -- there's no `background-image` left on the cover
to reset -- but the compound `.brand-deck-cover.jlpt-level-n5` selector
form is kept anyway (rather than simplified to the bare class) so this
stays true if a future pass ever adds a background-image back.

**Bookshelf density:** `.shared-library-scene .shared-deck-grid`'s
per-card width cap raised from 176px to 210px (the `auto-fit` upper
bound). Confirmed via real screenshot against the 6-deck seed set: at
176px a lightly-stocked row still left a visible bare-wood gap next to
the last card; 210px lets a sparse row's cards absorb more of that
leftover space while staying well short of the 335-420px "big card"
sizes this project has already rejected twice (Phase 128, Phase 147).
A fully-stocked shelf still packs many books at ~150-190px each -- this
is a ceiling for sparse rows, not a new target width.

**Header/notice de-emphasis:** "어휘 노트 보기"/"새로고침" are now
`.shared-deck-tab-action` -- small notched paper tabs, the same
fixed-pixel `clip-path` bookmark-tag family Reading's Phase 150 CTAs
(`.reader-bookmark-button`) and Vocab's Phase 149 tags established
before that (one consistent cross-tab "bookmark/paper action"
language, not a new shape invented per screen), colored with Deck's
own `--screen-accent` (`--tone-dusty-blue`). Both notice paragraphs
gained the already-existing `.info-strip-quiet` modifier (Home's
footnote already used this -- no new CSS needed) to drop their
bordered/filled chrome down to a plain icon+caption line.

**Owner/newcomer/subscriber conditions:** unchanged -- confirmed via
`git diff` that every edit to `SharedDeckSection.tsx` this phase
touches only the header-action buttons and the two notice paragraphs'
class names; not one line inside `renderDeckCard`'s button-condition
logic, the detail panel's owner/subscriber branches, or any
handler/prop was touched.

Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database (`backend/vocab.db`, the dev-mode auto-user, 6
real non-JLPT shared decks -- one owned by the dev user, one
subscribed-mode deck with 85 words):

- **Desktop (1280/1024):** all 6 decks now visible without scrolling
  in a dense 4-wide (1280) / 3-wide (1024) grid instead of 1-2 giant
  cards; covers read as short color-coded bands, not competing
  illustrations; header actions read as small paper tabs, not boxed
  buttons; notices read as plain caption lines. Zero
  `scrollWidth`/`clientWidth` mismatch, zero console errors/warnings,
  zero failed requests, zero requests to the now-unreferenced atlas
  file.
- **Functional loop (1280, real interactions, not just hit-tests):**
  newcomer "학습 목록에 추가" on the QA84 subscribed-mode deck
  actually imported it (confirmed via the card flipping to "열기" +
  a "학습 목록에 있음" badge with a real timestamp, matching Phase
  107's existing open/duplicate-suppression logic unchanged);
  subscriber "상세 보기"/"열기" opened the detail panel with a real
  85-word list (80 shown per the existing page-size cap); search and
  status-filter inputs were exercised and correctly re-filtered the
  list (0 matches for this session's specific query text against this
  specific seed data, not a bug -- the mechanism itself was confirmed
  working); "더 보기" pagination button present and correctly labeled
  with the remaining count; `StatusSelect` confirmed both reachable
  (`elementFromPoint` resolves to the `<select>` itself once scrolled
  into view) and functional (a real value change dispatched an actual
  `PATCH /shared-decks/8/words/1/progress` request, confirmed via
  `Network.requestWillBeSent`); detail-panel close (top button)
  confirmed removing the panel from the DOM. Owner unpublish/republish
  could not be exercised with real clicks this session -- the
  dev-mode auto-user has `canManageSharedDecks={!isDevUser}` = false
  by design (`page.tsx`, pre-existing, unrelated to this phase), so no
  owner-management buttons render for it on any deck. This is the same
  gate Phase 151 hit for Home's review shortcut; the button-rendering
  condition itself (`canManageDeck && published` / `!published`) is
  byte-identical to before this phase per the `git diff` check above,
  and Phase 147 already exercised this exact flow end-to-end with a
  real owner-permission account.
- **Mobile (390/375/320):** zero overflow mismatch at all three
  widths; two-column mini-bookshelf layout holds at all three (matches
  Phase 147's own precedent); header action tabs sit side-by-side, not
  stacked full-width bars; card labels/buttons stay legible with no
  clipped text at 320px, the narrowest width tested.

`npm run build` clean (dev server stopped and `.next` removed first,
per this project's WSL/Windows build-vs-dev conflict note), `git diff
--check` clean.

**Files changed:** `frontend/components/SharedDeckSection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural density/legibility confirmed via
screenshot, real functional interactions including a genuine
StatusSelect PATCH round-trip and a real deck import, owner-condition
code confirmed byte-unchanged via diff) all passed with zero console
errors and zero failed requests.

**Remaining risk:** owner unpublish/republish was verified by code
diff (unchanged) and Phase 147's prior real-click test, not by a fresh
real click this phase, since no available seed account combines
`canManageSharedDecks: true` with an owned published deck in this
session's dev-mode environment -- worth a real-account re-check next
time this screen is touched. This session's QA also performed one
real, non-destructive state change to the shared dev database (the
QA84 deck import for the dev user), left in place rather than
reverted, matching Phase 147's own precedent of treating a real import
as an acceptable one-way test action (unlike a delete).

**Next phase candidates:** Phase 150's Reading/Classify IA decision
(`phase145-casual-cute-tab-rebuild-plan.md` item 6) remains the last
open item from that plan. Vocab (149), Reading (150), Home (151), and
Deck (152) have each now had a full first-viewport/density correction
pass -- Study (148) is the only remaining "casual cute" tab that
hasn't had a post-145 correction pass, though none has been requested.

## Phase 153 -- Study Box Removal 2 / Board Note Reconstruction

Phase 153 is a second correction pass on Study, not a new rebuild:
Phase 148 already fixed the dark-board problem and gave the quick-start
tiles a "pinned memo tab" treatment (a colored dot + slight rotation on
an otherwise still-bordered box), but a real 1280 screenshot showed
that treatment wasn't different enough from a plain button row -- the
four tiles still shared one crisp `border: 1px solid`, sat in an equal
4-column grid, and rotated only 1-1.5deg, so the dominant signal
remained "4 aligned cards," not "several notes pinned to a board." The
ready/empty states had the same underlying issue at a different scale:
both reused the active review flashcard's full `.study-card.hero-card`
shell (640px wide, 28px padding, bordered, shadowed) for what's really
a one- or two-line guidance message.

**Removed:**
- **`.study-cta-button`'s bordered-box identity** -- the `border: 1px
  solid var(--border)` ruled edge is gone (a shadow now carries the
  "paper cutout" read, no ruled line), and so is the equal 4-column
  `display: grid` that forced every tile to the same track width
  regardless of its own label length.
- **`.study-card`/`.hero-card` on the ready and empty states** -- both
  used to carry the exact same 640px-wide bordered flashcard shell the
  active review card uses. Neither state needs that footprint for a
  one-line message, and reusing it was the direct cause of the "큰 흰
  안내 박스" complaint.
- **Mobile's separate dashed-border "ticket" treatment** for the 3
  secondary quick-start tiles (`border: 1px dashed`, its own distinct
  paper language from the desktop tiles) -- replaced with the same
  borderless-cutout-plus-pin family desktop now uses, so there's one
  consistent "pinned memo" identity at every width instead of two.

**New quick-start structure:** `.study-cta-grid` switched from
`display: grid` (equal `1fr` columns) to `display: flex; flex-wrap:
wrap` so each tile's width now follows its own content -- confirmed via
screenshot that "새 단어 학습"/"어려운 단어 복습"/"덱별 학습" render at
three visibly different widths instead of one shared column, which
turned out to be the actual thing breaking the "grid" read (the
existing per-tile rotation/pin dot alone couldn't overcome four
identical-width boxes). Each secondary tile also got: a bigger, more
3D "pin" (13px with a radial-gradient highlight, was a flat 9px dot), a
real per-tile vertical stagger via `translateY` (not rotation alone, so
the row visibly breaks its own straight line -- -8px/+9px/-3px across
the three), wider rotation range (2.5-5deg, was 1-1.6deg), and an
asymmetric corner radius that differs per tile. The primary "오늘 복습
시작" tile grew its own min-height/padding further (70px, was implicit
~60px) so it still visibly outranks the other three now that the
shared border stopped doing part of that job. Mobile keeps Phase 82's
existing full-width primary row + 3-across secondary row structure
(equal-width via `flex: 1 1 0`, not desktop's content-based sizing --
there's no spare row width at phone size to size tiles organically
without risking overflow on the longest label), just restyled with the
same pin/rotation family as desktop instead of the old dashed border.

**New empty-state structure:** a new `.study-board-note` class replaces
`.study-card.hero-card` for the ready and empty `AppEmptyState`
instances only (`StudySection.tsx`'s active-review and completion-
receipt cards are untouched, still `.study-card`/`.complete-card`). It's
a small (`width: min(360px, 92%)`), unbordered, slightly rotated
(-1deg) paper note with a washi-tape strip pinning its top edge (the
same `rgba(217,122,74,...)` accent this series already reuses for every
other "note attached to a surface" moment -- Home's pinned notes,
Vocab's page guide -- not a new motif). `Shiori`'s `moodSize` dropped
from `md`/`lg` to `sm` on both states to match the smaller note.

**Active review / rating stamp protection:** confirmed via `git diff`
that the only two className changes anywhere in `StudySection.tsx` are
the ready/empty `AppEmptyState` calls noted above -- zero lines touched
in the active-review branch, the rating-button map, or any `onReview`/
`onShowAnswer`/`onStart`/`onQuickStart` handler. `.rating-button`/
`.study-rating-grid`/`.study-card-stack`/`.study-card-backing-sheet`
CSS is also completely untouched (confirmed via `git diff` on
`globals.css`, scoped entirely to `.study-cta-*`/`.study-board-note`/
the new mobile override). A full real review session was driven
end-to-end via CDP click automation to confirm this held in practice,
not just in the diff: started "오늘 복습" (18 due) -> revealed and
rated "보통" through all remaining cards (`中` -> `響い` -> `体` ->
`猫` -> ..., confirmed by reading the actual surface text after each
rating, not just counting clicks) -> reached the completion receipt
with correct stats (`다시 0개 · 어려움 0개 · 보통 15개 · 쉬움 0개 ·
총 학습 15개`) -> "한 번 더 복습" correctly returned to the quick-start
hero. Phase 110's mobile rating-grid-above-the-fold protection was
re-verified with real `getBoundingClientRect()` measurements (not
assumed): the grid's bottom edge sat at 662.6px/662.6px/624.6px against
viewport heights 844/812/640 at 390/375/320 respectively -- inside the
fold at all three, same as before this phase.

Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database (`backend/vocab.db`, the dev-mode auto-user):

- **Desktop (1280/1024):** the four quick-start tiles now read as
  scattered pinned notes (varied width/rotation/vertical offset/corner
  radius), not an aligned button row; the ready/empty note reads as a
  small board-pinned slip, not a large white card; the active review
  card and completion receipt are pixel-identical to before this phase
  (confirmed by screenshot comparison). Zero `scrollWidth`/
  `clientWidth` mismatch, zero console errors/warnings, zero failed
  requests.
- **Mobile (390/375/320):** zero overflow mismatch at all three widths,
  across ready and answer-reveal states; quick-start primary stays one
  clear full-width action, the three secondary tiles read as a small
  pinned cluster (not a stacked button bar); rating grid confirmed
  inside the fold at all three widths via real measurement (see above);
  empty-state note stays compact, nowhere near "화면 절반."

`npm run build` clean (dev server stopped and `.next` removed first,
per this project's WSL/Windows build-vs-dev conflict note), `git diff
--check` clean.

**Files changed:** `frontend/components/StudySection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural de-boxing confirmed via screenshot,
a real end-to-end 15-card review session including reveal/rate/advance/
complete/restart, Phase 110's fold protection re-measured, rating-stamp
protection confirmed both by diff and by the session actually
completing correctly) all passed with zero console errors and zero
failed requests.

**Remaining risk:** none identified specific to this phase's own
changes. This session's QA completed one real 15-card review session
on the shared dev database (all rated "보통") as part of verifying the
end-to-end flow -- a genuine, non-destructive SRS state change, left in
place rather than reverted, matching this project's established
precedent (Phase 147/148/152) of treating a real forward-progressing
action as acceptable test state rather than something to roll back.

**Next phase candidates:** Phase 150's Reading/Classify IA decision
(`phase145-casual-cute-tab-rebuild-plan.md` item 6) remains the only
open item from that plan. Every tab in the "casual cute" series (Home,
Reading, Vocab, Deck, Study) has now had at least one post-145
correction pass.

## Phase 154 -- Analyze/Classify IA Reconstruction / Reading-to-Card Flow Redesign

Phase 154 is exactly the item Phase 150 deferred and Phase 153's own
closing note flagged as the last open item from `phase145-casual-cute-
tab-rebuild-plan.md`: Analyze/Classify's intro stage was the sole
remaining boxed hero-panel in the entire app. Phase 115 investigated
this exact element and deliberately judged Keep (not Replace) -- but
specifically *because* it matched `.study-hero-card`'s "same card
system" cross-tab consistency at the time. Every one of those other
tabs (Study itself, Phase 148; Home, Phase 145; Vocab, Phase 114;
Shared Deck, Phase 115 same-day) has since dropped its own version of
that exact boxed panel, so the thing Phase 115's Keep judgment was
protecting no longer exists to protect -- confirming, not overriding,
that decision's own stated condition.

**IA judgment (required by this phase's brief): A -- keep Analyze/
Classify as a separate tab.** Reading and Classify serve genuinely
different mental models, not two skins on the same task: Reading is
slow, in-context, word-by-word exploration while reading actual prose;
Classify is fast, out-of-context, bulk triage of every word in a text
at once, useful specifically *before* deciding whether the text is
worth reading closely, or for processing several texts' vocabulary
back-to-back. Collapsing them would also be a real architecture
change, not a visual one -- Analyze's chunked-session/draft-autosave/
card-index state model and Reading's token-click-in-place model are
different enough that merging them is a dedicated future phase's scope
on its own, which this phase's brief explicitly rules out doing here
("탭 삭제/라우팅 변경은... 후속 phase가 필요합니다"). What this phase
*does* do instead -- and what actually addresses the "왜 두 탭이 따로
있어야 하는지" doubt in the user feedback -- is make the two tabs
share one visual/copy language (open-worksheet textarea, notched
bookmark CTA, quiet text-link secondary actions, matching accent-color
convention) so the *reason* to keep them separate reads as "two related
tools," not "one coherent tab and one forgotten admin form." No nav
label change was made: "분류" already accurately names what this
screen does differently from "읽기." Revisit toward Option B (long-
term absorption into Reading) only if real usage data shows most
Classify sessions are immediately followed by opening the same text in
Reading anyway -- this phase found no such evidence, since it wasn't
in scope to gather it.

**Removed:**
- **`.classify-stage`'s `hero-card` class and its own `border`/
  `background: panel-bg` rules** -- the bordered, opaque, accent-topped
  panel that made the intro stage read as a standalone form. Replaced
  with the same unboxed dashed-bottom heading-strip recipe every other
  tab's top card now uses.
- **The dashed-border tinted textarea** (`border: 1.5px dashed;
  background: var(--surface-stage)`) -- one step removed from a plain
  form field. Replaced with a real "work sheet" surface (see below).
- **The stage-variant submit's identity as `.reading-open-button`** --
  a full form-submit button, functionally fine but visually generic
  (the exact same class Reading's own *secondary* re-analyze form
  uses). Replaced with a dedicated small notched CTA.
- **`.ghost-button.compact-button` on the secondary "이전 분류
  이어하기"/"삭제하고 새로 시작" actions** -- both bordered outline
  buttons, competing for attention with the one real CTA next to them.
  Replaced with a plain underlined text link.
- **A real mobile bug, not just a visual preference:** the post-result
  "원문 수정" toggle and the card-stage toolbar's "읽기 탭에서 보기"/
  "지금까지 저장" links had no `width` rule of their own, so the
  app-wide mobile `button { width: 100% }` rule was the one actually
  winning -- confirmed via a real screenshot showing all three as
  full-width stacked bars at 390px, the exact "quiet action이 admin
  bar가 되지 않도록" regression this phase's brief explicitly warns
  against. Not a hypothetical: this was live in the app before this
  phase touched it.

**New intro/start stage:** modeled directly on Reading's Phase 150
`.reader-start-scene` language, not copy-pasted from it. The heading
(Shiori guide + eyebrow + title + subtitle) sits as plain page content,
no card boundary. The textarea is a real recessed "work sheet" --
`var(--panel-bg)` fill, a repeating ruled-line texture, an inset
shadow -- plus one deliberate difference from Reading's own start
textarea: a coral vertical margin rule (`rgba(193, 105, 74, ...)`, this
tab's own `--screen-accent`) marking it specifically as a ruled index-
card worksheet, not a page of continuous prose. This is also literally
the same `rgba(193, 105, 74, ...)` accent Reading's Phase 150 detail-
page margin rule uses -- one shared material vocabulary across both
tabs, applied to different content, which is the actual "Reading와
이어지는" connective tissue this phase's brief asks for. The submit
("분류 카드 만들기") is now `.classify-bookmark-button`, the same
fixed-pixel-notch `clip-path` bookmark-tag family Reading's `.reader-
bookmark-button` (Phase 150), Vocab's `.vocab-bookmark-action` (Phase
149), Deck's `.shared-deck-tab-action` (Phase 152), and every tab since
has used -- colored with Analyze's own coral accent rather than a
borrowed one. "이전 분류 이어하기"/"삭제하고 새로 시작" are now
`.classify-quiet-link`, a plain underlined text link (same family as
Home's `.home-cover-sample`).

**Classify card stage:** deliberately *not* restructured -- this is
the one screen state the brief explicitly protects (Phase 112's mobile
decision-grid-clear-of-the-fold fix), and it was already the least
boxy-feeling part of Analyze before this phase (a real flashcard-tier
card, matching Study's own protected active-review card, with a live
sticky tally rail at `>=1024px`). Only the toolbar above it (the two
quiet links) got the same mobile-width fix described above. `git diff`
confirms zero lines touched inside `ClassifyWordPrimary`,
`ClassifyWordSecondary`, `ClassifyActionGrid`, or any of their CSS
(`.classify-word-card`, `.classify-actions`, `.rating-classify-*`, the
Phase 110/112 mobile `order` rules).

**Result summary:** left structurally as-is (coverage chips, count
pills, one primary save action, two de-boxed link actions below it) --
already matches Study's own protected completion-receipt card, and the
brief explicitly allows keeping Phase 104's de-boxed link hierarchy.
One small cross-tab consistency fix: the save button ("모르는 단어
노트에 담기") was the app's generic default teal gradient regardless
of which tab it sat on; now `.classify-save-button` uses this tab's
own coral `--screen-accent`, matching how every other tab's primary
action is now colored with its own accent rather than one shared
generic color.

Verified via headless Chrome (Windows-native, CDP) against a local
sqlite dev database (`backend/vocab.db`, the dev-mode auto-user),
including a run against the actual production build (`next build` +
`next start`, not just the dev server) for the final viewport sweep:

- **Desktop (1280/1024):** the large white form panel is confirmed
  gone from both the DOM (no `hero-card`/bordered-panel classes) and
  the screenshot; the intro reads as an open worksheet leading into the
  card-making flow, not an admin form; the card stage and result
  summary are visually unchanged from before this phase (confirmed by
  screenshot comparison). Zero `scrollWidth`/`clientWidth` mismatch,
  zero console errors/warnings, zero failed requests.
- **Functional loop (1280, real interactions):** deck select confirmed
  (4 real decks); show-known checkbox toggled; sample text submitted a
  real `/analyze` request and rendered a 13-token card stack; 5 cards
  classified across all four decision types (아는/헷갈리는/모르는/
  건너뛰기) with the live tally updating correctly after each
  (`완벽히 아는 단어 2 · 헷갈리는 단어 1 · 모르는 단어 1 · 건너뜀 1`,
  exactly matching); a full 13-card session was driven to the result
  summary, which correctly showed all coverage/count numbers; "모르는
  단어 노트에 담기" issued a real save (confirmed via the success
  message reporting the actual saved counts) and correctly reset back
  to the intro stage (existing behavior, unchanged); "이전 분류
  이어하기" was verified as a genuine resume, not just a hit-test --
  created a draft, reloaded the page, confirmed `.draft-status`
  appeared, clicked the link, and landed back on card 2/7 exactly where
  the earlier session left off.
- **Mobile (390/375/320):** zero overflow mismatch at all three widths;
  the intro CTA and secondary link both measured via
  `getBoundingClientRect()` at their real content width (195px/111px),
  not the 362px/347px/292px full-row width they measured before the
  fix; the card-stage toolbar and "원문 수정" toggle likewise confirmed
  small pills, not stacked bars, via the same before/after
  measurement; Phase 112's decision-grid fold clearance re-confirmed
  (grid top well within the viewport at all three widths; no fixed
  bottom-nav element exists in the current app shell at all, so the
  original "hidden behind a fixed nav" failure mode Phase 111/112 fixed
  can no longer occur structurally, independent of this phase's own
  changes).

`npm run build` clean, `git diff --check` clean. `git diff` on
`AnalyzeSection.tsx` confirmed scoped entirely to `className`
changes/one new `className` prop/comments -- zero lines touched in any
`onClick`/`onChange`/`onSubmit` handler wiring, confirmed by grepping
the diff for handler names and finding no matches.

**Files changed:** `frontend/components/AnalyzeSection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build (both `next build` and a real
`next start` production-server QA pass) and diff-check clean, full
5-viewport browser QA (structural de-boxing confirmed via screenshot
and DOM query, a real mobile-width regression found and fixed with
before/after measurement rather than assumed, full functional loop
including draft persistence-and-resume across a page reload) all
passed with zero console errors and zero failed requests.

**Remaining risk:** none identified specific to this phase's own
changes. This session's QA performed one real save (13 words, all
"완벽히 아는 단어") to the dev user's default deck as part of verifying
the end-to-end save flow -- a genuine, non-destructive state change,
left in place rather than reverted, matching this project's
established precedent (Phase 147/148/152/153) of treating a real
forward-progressing action as acceptable test state.

**Next phase candidates:** none currently flagged from the Phase
145 rebuild plan -- every item on it (Home, Reading, Vocab, Deck,
Study, and now Analyze/Classify) has had at least one post-145
correction pass, and the plan's own remaining open item (Reading/
Classify IA) has now been explicitly judged (Option A, this phase).
Future work in this area, if any, should start from real usage data on
how often Classify and Reading sessions chain together for the same
text, not from a code-only investigation.

## Phase 155 -- Stats Brand Alignment / Study Log Reconstruction

Stats ("통계") was functionally sound but, per direct user feedback,
the last tab still reading as an operations dashboard rather than the
"학습 일지/스티커 로그/작은 기록지 묶음" every other rebuilt tab now
commits to: a row of rounded metric pills, a second row of near-
identically-shaped journal chips repeating the same three numbers as
sentences, a stack of individually bordered/shadowed deck-progress
cards each with its own thick rounded bar, a filled `--soft-bg` side
panel holding the word lists, and a bordered `.panel-card` policy box
at the bottom -- five variations on one shape (white, rounded-corner,
thin-bordered box) applied to unrelated content types. The prior
failure mode this phase was explicitly warned against repeating
("기존 dashboard 위에 paper texture 얹기") did not apply here in the
literal sense -- there was no separate paper layer sitting on top --
but the underlying box-repetition was the same admin-list instinct in
plain CSS form.

**Removed:**
- **`.home-summary-chip`** -- the 3-pill metric row (border +
  `panel-bg` fill, `border-radius: 999px`), the single most literal
  "dashboard badge" shape in the tab. No longer used anywhere; the old
  rule block is fully replaced, not left as dead CSS.
- **The mobile-only forced single-column stack on `.records-today-row`**
  (`display: grid; grid-template-columns: minmax(0, 1fr)` below
  640px) -- the exact "메트릭이 dashboard card stack처럼 보이면 실패"
  case named in this phase's brief; every metric pill became a
  full-width bar on phones.
- **`.study-log-journal-list`/`.study-log-journal-line`/
  `.study-log-journal-icon`** -- each diary sentence as its own
  bordered, filled chip, the same rounded-box language as the stat
  pills directly above it, just wider. Two different kinds of content
  (numbers vs. sentences) reading as one repeated shape stacked twice.
- **`.records-deck-log`/`.records-deck-row`** -- each deck its own
  bordered card with `box-shadow`, holding a full rounded 6px
  `.progress-bar` -- a stack of N decks read as a stack of N separate
  analytics widgets, worse the more decks a user has.
- **The aside's filled `background: var(--soft-bg)` box** (`.study-
  log-scene-aside` at `>=1024px`) -- the "최근 담은 단어"/"자주 틀린
  단어" word lists sat inside a tinted panel with its own border-radius,
  reading as a separate dashboard widget parked beside the main column
  rather than part of the same page.
- **`.study-log-policy-card`'s `.panel-card` border + drop-shadow** --
  by the time every other surface on this tab had moved off boxed
  cards, the one bordered card left at the very bottom read as the
  last leftover admin box, even though Phase 60 had already lightened
  it once from the app's default `.note-card` callout.

**Kept as-is (judged already correct, not dashboard-shaped):**
`.records-word-row`/`.paper-corner` word-ticket rows (already an
index-card look, just freed from their filled aside wrapper);
`.records-word-wrong-badge` (a small functional count badge, not a
dashboard pill in the sense the brief targets); the `<details>`
disclosure interaction on each deck row; `StudyLogEmptyState` (already
`AppEmptyState` + Shiori, matches the brief's own empty-state
direction untouched); `.records-level-strip`/`.records-level-bar*`
(confirmed unused in `InfoSection.tsx` -- dead CSS predating this
phase, left alone rather than bundled into an unrelated cleanup).

**New structure:**
- **오늘 학습 → `.study-stamp-tag`:** the same washi-tape-pinned,
  slightly-rotated paper-tag family Home/Vocab/Study's own pinned
  notes already established (`rgba(217, 122, 74, ...)` tape strip,
  alternating `±rotate()` per tag, `var(--soft-bg)` fill with a
  squared-then-rounded corner) -- reused verbatim rather than inventing
  a fourth "small tag" language for the same idea. `.records-today-row`
  now just wraps these as small flex items at every width (`flex-wrap:
  wrap`, no forced mobile grid column), so on narrow screens the three
  tags wrap two-then-one instead of stacking as full-width bars.
- **학습 일지 → `.study-diary-sheet`:** one continuous ruled-paper
  surface (the same `repeating-linear-gradient` rule recipe
  `.shared-deck-detail`'s notebook page already uses, at a tighter
  33px line height suited to short sentences) holding plain
  `.study-diary-line` entries divided by a hairline dashed rule instead
  of each having its own filled box.
- **서가별 통계 → `.records-deck-ledger`:** one shared paper surface
  (`var(--paper-bg)`, single outer border) instead of N separate cards;
  rows (`.records-deck-ledger-row`) are divided by a hairline dashed
  rule between rows rather than each owning its own box edge. The
  progress indicator is now `.records-deck-progress-line`, a 2px
  underline track instead of a 6-9px rounded dashboard bar, filled with
  the tab's own `--screen-accent` (sage green). Same 오늘 복습/모르는
  단어 counts, same "자세히 보기" `<details>` disclosure with the same
  전체/아는 단어/헷갈리는 단어 breakdown, same deck name and percent --
  none of `DeckProgressJournal`'s data or JSX structure below the row
  wrapper changed.
- **최근 담은 단어 / 자주 틀린 단어 aside:** the `--soft-bg` fill and
  its own border-radius were dropped; at `>=1024px` the aside is now
  a plain sticky column separated from the main log by a single thin
  dashed vertical rule (`.study-log-scene-aside`), reading as a margin
  column of the same notebook page rather than a second floating
  surface. The individual `.records-word-row.paper-corner` "ticket"
  rows are unchanged, so word/reading/meaning/wrong-count scan-ability
  is identical to before.
- **저장 정책 card:** kept its own paper fill and folded corner
  (`.paper-corner`) but dropped the `.panel-card` border and drop-
  shadow, so it now reads as the closing page of the same notebook
  rather than a bordered callout box.

**Desktop (1280/1024) results:** confirmed via headless Chrome
screenshot (both viewports) that no bordered/shadowed `.panel-card`-
style box remains anywhere in the populated state except the outer
deck-ledger and diary-sheet surfaces, both of which are now single
shared paper surfaces rather than repeated per-item cards; the metric
tags read as pinned notes, not badges; the aside now visually
continues the main column instead of floating as a separate widget.
`document.documentElement.scrollWidth === clientWidth` at both widths
(1280x1280, 1024x1024).

**Mobile (390/375/320) results:** the three stamp tags wrap
two-then-one instead of stacking as full-width pills; the diary sheet,
deck ledger, and word tickets all flow as single-column content with
no card-in-card boxing; zero overflow at all three widths
(`scrollWidth === clientWidth`: 390x390, 375x375, 320x320). One
pre-existing, non-regression cosmetic edge case noted at 320px: a dev-
QA-only test deck with an unusually long name ("Stability Shared
1783129745082") wraps its "0%" onto a second line inside
`.records-deck-row-head`'s `justify-content: space-between` flex row --
this is unchanged pre-existing row-head layout behavior triggered only
by synthetic test data, not something this phase's ledger restructure
introduced.

**Function/API/stats/storage confirmation:** `git diff` on
`InfoSection.tsx` confirmed scoped entirely to `className` changes,
JSX element restructuring inside `DeckProgressJournal`/`StudyTimeline`/
`TodayStudyMemo`, and comments -- zero lines touched in `StudyLogPage`'s
props, the `journalEntries` construction logic, `DeckStats`/`StudyStats`/
`VocabItem` types, or any data passed in from `page.tsx`
(`loadInfoStats`/`loadInfoWordHighlights`). No backend, API route,
schema, SRS/review-log, or deck-progress-calculation file was touched.
`StatsPanel.tsx` (Study tab's own separate "학습 현황 자세히 보기"
disclosure) was confirmed out of scope and left untouched.

**Build/QA results:** `npm run build` clean (stopped the dev server,
`rm -rf .next` first, per this project's build/dev-concurrency rule).
`git diff --check` clean. Verified via headless Chrome (Windows-native,
CDP) against the running dev server: Stats tab load and populated
state confirmed at 1280/1024/390/375/320; deck-progress `<details>`
disclosure opened via a real click (not a hit-test) and confirmed
`[open]`, screenshotted before/after; recent/difficult word lists
rendered with live word/reading/meaning/wrong-count text
(`.study-stamp-tag`: 3, `.study-diary-line`: 3, `.records-deck-ledger-
row`: 4, aside `.records-word-row`: 8 -- all matching the dev account's
real data); hamburger drawer opened via a real click at 390px width,
confirmed 통계 highlighted as the active tab and both 피드백 and 로그인
reachable from the drawer/toolbar. Zero console errors/warnings, zero
failed network requests, zero image errors, across every viewport
checked.

**Files changed:** `frontend/components/InfoSection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (visual de-boxing confirmed via screenshot,
real disclosure-toggle and drawer-navigation interactions, overflow
and console/network checks at every viewport) all passed with zero
console errors and zero failed requests. Per this project's standing
process, no commit/push was made -- left staged for the user to review
and commit.

**Remaining risk:** the 320px deck-row-head wrap noted above is
cosmetic and limited to a synthetic long-named test deck already
present in the dev database before this phase; real deck names are
unlikely to reach that length, and the underlying flex layout is
unchanged from before this phase. No other risk identified specific to
this phase's changes.

**Next phase candidates:** none currently flagged. With Phase 155,
every tab named in the original Phase 145 rebuild plan (Home, Reading,
Vocab, Deck, Study, Analyze/Classify, and now Stats) has had at least
one post-145 brand-alignment pass judged against the same "학습
노트/기록장" standard. Future work in this area, if any, should start
from a full cross-tab consistency pass rather than a single-tab
correction, since the per-tab pinned-note/ledger/diary-sheet
vocabulary has now converged closely enough across tabs that any
remaining differences are more likely to be real inconsistencies than
intentional per-tab variation.

## Phase 156 -- Analyze/Classify Hard Rework 2 / Card-Making Desk Scene

Phase 154 dropped Analyze/Classify's boxed hero-card panel, but this
phase's own brief judged that pass incomplete: the screen underneath
the unboxed heading was still built around one big textarea, a deck
select, a checkbox, and a CTA -- an input-form silhouette wearing
unboxed clothes, not the "카드 만들기 작업대" the mockup world calls
for. Where Phase 154 asked "what boxes should be removed," this phase
asked "what scene should the first viewport actually read as," with an
explicit, screenshot-checkable failure list (input-form first
impression, textarea as the visual lead, a generic control row, no
card/stamp/desk element visible above the fold, decoration bolted onto
Phase 154's structure instead of a real silhouette change). That list,
not a removal checklist, is what this pass was judged against.

**Removed:**
- **The dual-variant `ClassifyPaperInput` component** -- the intro
  stage and the post-result "원문 수정" compact editor shared one
  function branching on `variant`. Split into `ClassifyCompactEditor`
  (compact-only, unchanged behavior) and a set of new desk components
  (below); the intro no longer shares any markup with the compact
  editor, since they no longer need to look related.
- **`.classify-hero-textarea`** -- a full-width, 140px-tall "work
  sheet" that dominated the first viewport regardless of Phase 154's
  unboxed heading above it. This was the actual "textarea가 화면의
  주인공" failure the brief names, independent of whether it had a
  border around it.
- **`.classify-hero-footer`/`.classify-hero-cta-row`** -- the grouped
  deck-select + checkbox + submit row that read as a form's action bar
  no matter how the submit button itself was styled.
- **`.classify-bookmark-button`** -- Phase 154's notched-flag CTA,
  functionally fine but not distinct enough from a plain submit button
  once the rest of the screen was still form-shaped around it.
  Replaced with a stamp-shaped CTA (below) now that the surrounding
  scene actually needs one.
- **`.draft-status`'s plain centered `<p>`** for the resumeable-draft
  status line + inline discard link -- read as a status paragraph
  competing with the form above it, not part of any scene.
- **`.classification-summary`/`.final-summary`** -- 4 plain rounded
  pills directly under the "완료" heading, the same generic-badge
  shape a dashboard stat strip would use.
- **`.show-results-toggle`'s bordered/filled box** -- one more small
  control reading as a form field, immediately below the now-de-boxed
  result cards.

**New card-making desk silhouette:** the intro (`ClassifyDeskIntro`)
is now `.classify-desk-scene`: a main column (source slip -> paper
chips -> stamp CTA) beside a card tray at `>=1024px` (stacked, main
then tray, below that), the same "main surface + side rail" split
Reading/Stats/Analyze's own card stage already use elsewhere, applied
here to the *intro* for the first time. The textarea is capped at
`max-width: 440px`, 3 rows, with its own tighter ruled-line/inset-
shadow surface and a torn washi-tape pin (`ClassifySourceSlip` /
`.classify-source-slip`) -- one item pinned to the desk, not the
screen's organizing input box. Deck select + "완벽히 아는 단어도 표시"
are two small paper chips (`ClassifyDeskControls`): the select reuses
`.reading-deck-picker`'s existing rounded-pill chip verbatim, and a
new `.classify-desk-checkbox-chip` gives the checkbox label the same
treatment. The CTA (`.classify-stamp-button`) borrows the app's own
established "postmark" recipe (`.shiori-stamp--labeled`'s dashed
border + rotation) instead of the shared notch-flag family, filled
solid with Analyze's coral `--screen-accent` so it still reads
unmistakably as the one primary action. A new `ClassifyCardTray`
(`.classify-card-tray`) sits beside/below the main column: a small
fanned stack of three blank paper-card shapes (`.classify-card-tray-
card`, no text/numbers -- purely decorative, so it can never read as
fake analysis output) previewing "this slip becomes word cards," plus
the resumeable-draft affordance now as a receipt-style
`.classify-draft-chip` (left accent bar, not a status paragraph) with
"이어하기"/"삭제하고 새로 시작" as its own action row. All of this is
visible in the very first viewport, before any text has even been
typed.

**Intro/start stage reconstruction:** same underlying
`text`/`selectedDeckId`/`includeKnown`/`pendingDraft` state and the
same `onTextChange`/`onSelectedDeckChange`/`onIncludeKnownChange`/
`onAnalyze`/`onRestoreDraft`/`onDiscardDraft` callbacks as before this
phase -- only the JSX structure and class names changed. The submit is
still a real `<form onSubmit={onAnalyze}>` around the whole desk scene
(including the tray, whose two buttons are explicitly `type="button"`
so they can't accidentally submit); `handleAnalyze` in `page.tsx`
reads only `event.preventDefault()` plus component state, never form
field DOM values, so moving the fields around the page freely was
confirmed safe before restructuring, not assumed.

**Card stage reconstruction:** deliberately minimal -- Phase 112's
mobile decision-grid-above-the-fold protection (the `order` rules
moving `.classify-actions` ahead of `.classify-word-card-secondary`
below 640px) was explicitly left untouched, confirmed via `git diff`
showing zero lines changed in that media-query block. The one change:
`.classify-progress`'s bare "N / total" text is now
`.classify-progress-marker`, a small rounded chip (same pill-tag
family as `.reading-deck-picker`) with a card icon, so progress reads
as a small work-in-progress marker on the card rather than a bare
number -- everything else (the flashcard-tier `.classify-word-card`,
the 4-way `.classify-actions` grid, the sticky `.analyze-work-aside`
tally rail) was already judged not-generic enough to need
reconstruction and was left alone.

**Result summary reconstruction:** `ClassifyResultSummary`'s heading
copy changed from "단어 나누기를 마쳤어요." to "단어 카드 묶음을 다
만들었어요."; the 4 status pills are now `.classify-result-cards` --
small fanned paper cards (label + bold count), the filled-in
counterpart of `ClassifyCardTray`'s blank preview cards, so the desk
scene reads as slip -> blank card tray -> finished card bundle, not
form -> dashboard summary. The save button's label changed from
"모르는 단어 노트에 담기" to "카드 묶음 노트에 붙이기" -- copy only,
same `onSaveSelected`/`disabled`/`title` wiring. "원문 읽기로
이동"/"어휘 노트 보기" links are unchanged. The opt-in ledger
(`.classify-ledger`, already a de-boxed "pull-tab" receipt-style table
since an earlier phase) was left structurally alone; only its toggle
checkbox lost its bordered/filled box.

**Separate-tab IA judgment (re-recorded per this phase's brief):**
**A -- keep Analyze/Classify as its own tab**, reaffirming Phase 154's
same judgment. Nothing found this phase changes the underlying reasons
(Reading is slow in-context exploration; Classify is fast out-of-
context bulk triage -- genuinely different mental models, not two
skins on one task). What this phase *does* strengthen is the
Reading-connective copy/visual language the brief specifically asks
for: the eyebrow above the intro heading changed from "빠른 분류" to
"읽은 원문에서 카드 만들기" (explicitly naming Reading as the source of
the material being turned into cards), and the subtitle now reads
"원문 slip을 올리면 단어가 카드로 한 장씩 나뉘어요." -- both frame
Classify as the next step after Reading, not a standalone analysis
tool. No nav label change (still "분류" -- accurate, unambiguous). No
merge implemented, per the brief's explicit instruction to record the
IA judgment only.

**Desktop (1280/1024) results:** confirmed via headless Chrome
screenshot at both widths: the first viewport shows the source slip,
two paper chips, the rotated stamp CTA, and the card tray with its
fanned blank cards all above the fold, with no bordered form panel
anywhere -- a card-making desk, not an input-form screen. The textarea
is capped at 440px and visually secondary to the tray/stamp/heading
around it. `document.documentElement.scrollWidth === clientWidth` at
both widths (1265x1265 at the 1280 viewport request -- headless
Chrome's own reported content width, not a mismatch; 1009x1009 at
1024).

**Mobile (390/375/320) results:** measured via `getBoundingClientRect`
(not assumed): the stamp button measured 192px wide against a 362px/
347px/292px container at 390/375/320 -- nowhere near the app-wide
mobile `button { width: 100% }` full-bar width, confirmed because
`.classify-desk-cta-row` sets its own `align-items: center` rather
than reusing `.analyze-cta-row` (whose mobile `align-items: stretch`
was the exact mechanism Phase 154 had to work around for the button
this one replaces) -- there is no stretch-eligible ancestor left to
re-stretch it. `.classify-desk-main`/`.classify-card-tray` bounding
boxes confirmed non-overlapping at all three widths. The 4-way
decision grid's bounding box was confirmed fully within the viewport
at all three widths (`withinViewport: true`), and a real screenshot at
320px shows it clear of any overlap, matching Phase 112's protection.
The result summary flows as fanned result cards -> save stamp button
-> quiet links, not a stacked admin form, at all three widths.

**Function/API/storage confirmation:** `git diff` on
`AnalyzeSection.tsx` (`+371/-267` lines) confirmed scoped to JSX
structure, `className` changes, one component split
(`ClassifyPaperInput` -> `ClassifyCompactEditor` + new desk
components), and comments -- grepped the diff for
`handleAnalyze`/`apiFetch`/`fetch(`/`localStorage`/
`classifyMessageTone`/`computeCoverageStats` and found zero matches,
confirming no business-logic call sites were touched. No backend,
API route, schema, classification/save algorithm, or routing file was
touched. `pendingDraft`/`onRestoreDraft`/`onDiscardDraft` props and
their wiring are unchanged -- only where the resulting UI renders.

**Build/browser QA results:** `npm run build` clean (fresh `.next`,
no dev server running concurrently). `git diff --check` clean.
Verified via headless Chrome (Windows-native, CDP) against the running
dev server and real backend: Analyze tab load; sample text entered via
a real input event (not just state injection); deck select changed to
a real deck id; show-known toggle clicked and confirmed `checked`
both ways; classify started via a real click on the stamp button (a
genuine `POST /analyze` round trip, not a mocked response); card stage
entered; 6 explicit rating clicks across all four action types
(known/uncertain/unknown/skip) plus an auto-loop to completion (11
total tokens); result summary reached and its 4 result cards, save-
button label, and both next-step links confirmed; the opt-in ledger
toggled open and confirmed 11 rendered rows; a real save issued
(`완벽히 아는 단어 8개, 헷갈리는 단어 1개, 모르는 단어 1개를
저장했습니다.`, matching the session's own classification exactly);
previous-session resume confirmed genuine (not a hit-test) by reloading
the page, confirming the draft chip survived the reload, clicking
"이어하기", and landing back on the exact session state (a completed-
but-unsaved classification from an earlier mobile test pass, correctly
restored as the result summary rather than the card stage); discard
confirmed via "삭제하고 새로 시작" removing the draft chip. Zero
console errors/warnings, zero failed requests, zero image errors, at
every viewport checked (1280/1024/390/375/320) -- one non-regression
`404 /favicon.ico` request noted and excluded (no favicon file exists
anywhere in `public/`; this is a pre-existing, app-wide characteristic
unrelated to this phase's changes, not a new failure).

**Remaining risk:** none identified specific to this phase's own
changes. This session's QA performed one real save (10 words:
8 완벽히 아는 단어, 1 헷갈리는 단어, 1 모르는 단어) to the dev user's
default deck as part of verifying the end-to-end save flow -- left in
place rather than reverted, matching this project's established
precedent (Phase 147/148/152/153/154) of treating a real
forward-progressing action as acceptable test state.

**Next phase candidates:** none currently flagged. Every tab in the
original Phase 145 rebuild plan has now had at least one post-145
brand-alignment pass, and Analyze/Classify specifically has had two
(Phase 154's structural de-boxing, this phase's silhouette rework),
reaffirming the same separate-tab IA judgment both times. Future work
here, if any, should revisit that judgment only from real usage data
on how often Classify and Reading sessions chain together for the
same text -- this phase, like Phase 154, found no such evidence in
scope to gather.

## Phase 157 -- Full Mockup Parity Re-audit / Scene-First Failure Scan

Phase 157 is a no-code-by-default audit, not a rebuild: after Phase
149-156's per-tab reconstruction passes, this phase re-judges the
whole product against a stricter, explicitly weighted rubric (하지
말 것 30% / 최종 장면 실루엣 40% / 실패 판정 기준 20% / 기능 보존
10%) instead of build/overflow/console QA, which every prior phase
had already passed without that passing translating into "looks like
the mockup" in a real screenshot. Every required state (Home; Reading
start/result+inspector; Study ready/active-reveal; Vocab
empty/populated/detail; Shared Deck shelf/detail; Analyze
intro/card-stage/result; Stats; Feedback modal) was captured via
headless Chrome at 1280/1024/390/375/320, judged first on scene
silhouette against a real screenshot, only then on function.

**Calibration note (methodology, not a finding):** the first Home/
Reading screenshots were captured at a 1400px viewport height to fit
a whole page in one image, which made the wood-desk/grid-paper area
below the hero content look like a large abandoned empty area --
matching failure criterion #6 on first read. Re-captured at a
realistic 800px laptop fold height, Home's book+note+sticky-note
cluster fills the actual first viewport almost edge to edge with no
excess bare wood, and Reading's open-book scene does the same. This
was an artifact of the audit's own screenshot height, not a real
silhouette failure -- recorded here so a future audit doesn't need to
re-discover it.

**Per-tab verdict table:**

| Tab | Verdict | Why |
|---|---|---|
| Home | Match | Book is the dominant object at a realistic fold height; heading note physically overlaps its top edge; sticky-note shortcuts read as one cluster with the book via the bridging pen prop; no admin control row. |
| Reading | Match | Start stage: open-book photo, textarea as a clearly layered "pasted sheet," small notched CTA. Result stage: token inspector renders as a real margin note on the book's right page (word/reading/뜻/4-way status/예문/저장 action), not a floating detail card; save dock sits on the memo-strip texture. Confirmed at both 1280 and 390 (mobile renders the inspector as a bottom sheet, an expected mobile pattern). |
| Study | Needs Small Fix (fixed this phase) | Active review (board + flashcard + 4 rating stamps) is a strong Match at every width. Ready/empty state's quick-start tiles read as pinned notes reasonably well, but mobile's "원문 읽기"/"어휘 노트 보기" pair had no `width` rule of its own, so the app-wide `button{width:100%}` rule turned them into two stacked full-width admin bars directly under the primary CTA -- a real, screenshot-confirmed instance of failure criterion #8. Fixed in this phase (see below). Remaining P2 (not fixed): the quick-start tiles above the felt board sit on the plain page background, not the board itself -- only the empty-state note actually sits on green felt, so the top and bottom halves of the ready screen read as two materials, not one board scene. |
| Vocab | Match | Physical index tabs (전체/모르는 단어/...) read as stable tabs at both 1280 and 390; populated list is scannable; the right-hand detail page opens as a pinned/paperclipped note sharing the same paper material as the empty-state placeholder it replaces, not a separate floating image. No collision between long labels and decoration observed. |
| Shared Deck | Needs Rework (recorded as next-phase candidate, not fixed) | The wood-shelf photo frame around the deck grid is real and reads well at desktop, but the "books" inside it are flat, uniform-aspect-ratio rounded-corner cards with a thin flat-color header band -- shape-wise indistinguishable from a generic web app card grid sitting on a pretty photo background, which is a direct match for failure criterion #5 ("기존 앱 구조 + 예쁜 재료"). This is worse, not better, at mobile: the wood-shelf frame disappears entirely below 1024px, leaving a bare 2-column card grid with zero shelf/book cues at all. Deck detail (opened via "상세 보기") itself reads fine as a pinned notebook page. Fixing the card shape itself (spine-like proportions, standing/leaning perspective) is a real visual-design change to `.brand-deck-cover`/`.shared-deck-card`, not a 1-2 file correction -- left for a dedicated next phase per this phase's own no-large-rework rule. |
| Analyze/Classify | Match | Re-verified Phase 156's card-making-desk work holds under this phase's stricter rubric: intro's first viewport shows the source slip, chip controls, stamp CTA, and card tray together with no textarea dominance; card stage keeps the 4-way decision grid as the clear lead object; result renders as a fanned card bundle, not a dashboard summary. |
| Stats | Match (P2 noted) | Dashboard/pill/card feeling from before Phase 155 is confirmed gone in a fresh screenshot -- no rounded badges, no bordered per-item cards. Doesn't trigger any of the 10 explicit failure criteria. P2, not blocking: below the three pinned stamp tags at the very top, the rest of the page (diary sheet, deck ledger, word asides, policy note) is mostly flat text with hairline dividers and very little sticker/tag material, so it reads closer to "a plain, well-organized log page" than "a scene with real physical texture" -- thinner on scene character than Home/Reading/Study/Analyze, though not a dashboard regression. |
| App Shell / Toolbar | Match | The toolbar stayed a thin, consistently-sized cream pill bar across every tab and viewport checked, including immersive scenes (Home, Reading's open book) -- it never grew heavier or more app-chrome-like relative to the scene beneath it. Mobile drawer opens via a clearly labeled hamburger (aria-label "메뉴 열기") and lists all 7 tabs plus feedback, confirmed reachable (re-verified in Phase 155/156's own QA, not re-tested fresh this phase since no toolbar code changed). |

**P1 (blocking, real product-facing regression, fixed this phase):**
- Study's mobile "원문 읽기"/"어휘 노트 보기" secondary links rendering
  as two stacked full-width admin bars under the primary CTA (failure
  criterion #8). Root cause: `.study-hero-secondary-link` set
  `min-width: 0` but never `width: auto`, so nothing overrode the
  app-wide mobile `button { width: 100% }` rule. Fixed with a single
  `width: auto` rule inside the existing `max-width: 640px` block in
  `globals.css`, matching the same fix pattern already applied to
  every other tab's equivalent quiet links (`.classify-quiet-link`,
  `.reader-start-cta`, etc.) -- confirmed via before/after screenshot
  and a post-rebuild re-screenshot that the fix survives a real
  production build, not just dev-server hot reload.

**P2 (next-phase candidates, not fixed -- real structural work):**
1. **Shared Deck card shape** -- the deck-shelf cards need an actual
   book-spine silhouette (vertical proportions, standing/leaning
   perspective, or some other real departure from a uniform rounded
   rectangle), not just a colored header band on an otherwise generic
   card. Needs a real visual redesign of `.brand-deck-cover`/
   `.shared-deck-card`, ideally also addressing the mobile case where
   the wood-shelf frame disappears entirely and the grid loses every
   shelf cue.
2. **Study ready-state board unity** -- extend whatever surface holds
   the empty-state note (currently only the green felt board) to also
   visually hold the quick-start tiles above it, so the whole ready
   screen reads as one board scene instead of "tiles on the page
   background, then a board below."
3. **Stats scene texture** -- the log/ledger/aside sections below the
   top stamp-tag row could use a bit more of the sticker/pinned-tag
   material the rest of the app now uses by default, so the tab reads
   less like a well-organized text page and more like the "학습
   일지" scene it targets.

**P3 (minor, cosmetic, not scene-blocking):**
- Reading's "이전 작업 복원됨 · 확인" draft-restore banner is a plain
  white rounded pill notice -- reads slightly like a generic system
  notification bar next to the rest of the tab's paper-note material
  language.
- Shared Deck's detail panel has two "닫기" controls (a text link at
  the panel's top-right and a full button at its bottom) -- redundant,
  not confusing, but worth consolidating in a later pass.
- The dead `.records-level-strip`/`.records-level-bar*` CSS in Stats
  (confirmed unused in `InfoSection.tsx` back in Phase 155) is still
  present -- harmless, but noted again since this audit re-touched the
  same file.

**Not touched, confirmed by design:** every tab's actual data/API
wiring, classification/save/SRS logic, deck-progress calculation,
localStorage draft persistence, and auth/storage layer -- this
phase's only code change is the single `width: auto` CSS rule above.
`git diff` on `globals.css` confirmed exactly one rule block added,
nothing else touched.

**Mobile/desktop cohesion:** with the Study fix applied, no tab
reverts to a full-width control stack at 390/375/320 -- re-confirmed
via a full 7-tab x 5-viewport sweep (`scrollWidth === clientWidth` at
every combination). Scene identity survives the width drop on every
tab except Shared Deck, where the wood-shelf frame's disappearance
below 1024px makes the underlying "it's actually just a card grid"
problem more visible, not less -- consistent with (not a new finding
beyond) the desktop-level Deck verdict above.

**Function/API/storage confirmation:** re-walked the representative
functional paths required by this phase's brief -- Reading analyze
(sample text -> `POST /analyze` -> token inspector opened via a real
click), Study (start today's review -> reveal -> rating stamps
visible and correctly laid out at both 1280 and 390), Vocab (deck
selected via a real `change` event -> populated list -> row expanded
via "펼치기" -> search input typed), Shared Deck (shelf ->
"상세 보기" opened and closed a real detail panel), Analyze (full
intro-to-result classify loop, reusing Phase 156's own verified flow),
Stats load, Feedback modal open (real form fields present: 종류
select, 내용 textarea, 제출/취소) and close (confirmed removed from
DOM). No backend/API/schema/business-logic file was touched this
phase.

**Build/browser QA results:** `npm run build` clean (fresh `.next`,
dev server stopped first). `git diff --check` clean. Full 7-tab x
5-viewport sweep (1280/1024/390/375/320) confirmed zero
`scrollWidth`/`clientWidth` mismatch at every one of the 35
combinations, zero console errors/warnings, and zero failed
requests/image errors across the entire audit session (one
pre-existing, unrelated `/favicon.ico` 404 excluded, consistent with
Phase 155/156's own finding that no favicon file exists anywhere in
`public/`).

**Overall verdict: redesign closeout is NOT yet possible.** Six of
eight scenes (Home, Reading, Study, Vocab, Analyze, App Shell) are
genuine Matches against this phase's stricter silhouette-first rubric,
and Stats is a Match with only cosmetic texture notes. Shared Deck is
the one tab that still reads as "existing web-app card grid + pretty
wood photo" rather than an actual mini bookshelf, at every viewport --
a real, unresolved instance of the exact failure mode this whole
"casual cute" series has been correcting on every other tab since
Phase 145. Closeout should wait for a dedicated Deck card-shape rework
phase before this redesign effort is declared done.

**Files changed:** `frontend/app/globals.css` (one rule block), this
file.

**Commit-readiness:** yes -- build and diff-check clean, the one
fix applied is scoped, tested, and confirmed to survive a real
production build; the no-code audit findings are documented for the
next phase to act on rather than left implicit.

**Remaining risk:** none identified from the one CSS fix made this
phase (a single `width: auto` addition, same pattern used successfully
many times before in this project). The Deck P1 finding is unresolved
by design (explicitly deferred per this phase's own no-large-rework
rule) and should not be read as a regression -- it is a re-confirmation
of an existing condition dating back to Phase 152.

**Next phase candidates (priority order):** (1) Shared Deck card-shape
rework -- give the shelf cards an actual book-spine silhouette instead
of a colored-band card, and restore some shelf cue at mobile widths
where the wood frame currently disappears; (2) Study ready-state board
unity -- extend the board surface to visually hold the quick-start
tiles, not just the empty-state note; (3) Stats scene texture -- a
lighter pass adding more sticker/pinned-tag material to the log/ledger
sections below the top stamp row.

## Phase 158 -- Shared Deck Real Bookshelf Reconstruction / No More Card Grid

Phase 152 dropped `deck-cute-cover-tile-atlas.webp` (a tall, illustrated
cover photo) for a short flat-color "spine cap" band, which fixed that
phase's own oversized-card problem -- but Phase 157's audit named the
result correctly: the cover changed, the structure never did. A deck
was still `cover-band -> title -> meta -> description -> a footer of up
to 3 buttons`, laid out in a CSS Grid of uniform rounded rectangles --
a real card model wearing book-flavored paint. This phase discards that
model outright rather than reskinning it again, per its own explicit
instruction ("card grid model 자체 폐기", not "표지 수정").

**Removed:**
- **`.shared-deck-card`/`.shared-deck-grid`/`.selected-shared-deck-card`/
  `.shared-deck-pin`** -- the entire card-grid item model: a bordered
  rounded-rectangle `<article>`, a CSS Grid with `auto-fill`/`auto-fit`
  tracks (which stretch to fill leftover row width -- the actual
  mechanism that made a sparse row of decks look like empty admin grid
  cells), and a round dot "selected" marker pinned to the card's cover.
- **`BrandDeckCover` and all `.brand-deck-cover*` CSS** (the "spine cap"
  band itself, `DeckCoverTone`, `deckCoverLabels`/`deckCoverIcons`) --
  deleted, not left orphaned. Confirmed via grep this component had
  exactly one call site in the whole app (the card render function just
  removed); nothing else ever imported it.
- **The per-card 3-button footer** (`상세 보기`/`상세 닫기`, the
  import/re-import/open action, and -- for an owner's own deck --
  `공유 취소`/`다시 공유하기`). Reduced to at most one action per shelf
  item (see below); owner-only manage actions are dropped from the
  shelf entirely and now live only in the already-existing detail panel
  controls (unchanged there).
- **Per-card alternating `rotate()` tilt** (Phase 88's "small booklet
  tilt" on resting cards) -- suited loose scattered cards, not upright
  standing spines, which read as broken/falling over when tilted at an
  angle. Real shelved books stand straight, packed tight against their
  neighbors; the new item has no per-item rotation at all.

**New bookshelf scene silhouette:** `.book-shelf-row` (renamed from
`.shared-deck-grid`) is a `display: flex; flex-wrap: wrap; align-items:
flex-end` row, not a grid -- fixed-width items that simply stop and
leave plain shelf surface to their right when a row is sparse, the same
silhouette a lightly-stocked real shelf has, instead of grid tracks
stretching to fill it. Each deck is a `.book-spine`: a narrow standing
rectangle (96px x 196px at desktop) whose *entire* face is filled with
the deck's tone color (the exact same JLPT N5-N1 ramp / 내가 공유함 /
공유 덱 palette the old cover band used, now the whole spine's cover
rather than a 34px cap), with an inset gutter-shadow on one edge and a
light catch on the other so a packed row reads as separate standing
objects touching each other. The outer wood cabinet/shelf compartment
(`.shared-library-scene`, `.shelf-section`, the wood-photo backgrounds)
was kept -- Phase 157's audit never flagged that outer scene, only the
items floating on top of it, so it remains a legitimate layout anchor.

**How the card model was discarded (not reskinned):** every deck field
moved onto the spine itself instead of the label area below a cover
image: `.book-spine-stickers` (level tag, unpublished status) sits at
the spine's top as small light chips against the dark tone fill;
`.book-spine-label` is the spine's own printed title, clamped to 5
lines rather than pushed below a graphic; `.book-spine-face-footer`
holds the word count plus a small "owned" dot instead of a wordy
dashed-border pill (no room for one on a 96px spine); a chevron
indicates the face opens something. The face itself -- not a separate
"상세 보기" button -- is a real `<button>` that toggles the detail
panel (`onSelectDeck`, unchanged handler), so opening a book is "tap
the book," not "find its one small button" among several. At most one
further action, `.book-spine-pulltab`, is fixed to the spine's base
like a label glued on with a perforated (dashed) top edge -- import,
re-import, or open, depending on state (see condition mapping below).
Owner decks get no pull-tab at all: a real shelf book isn't managed
while standing closed on the shelf, you pull it out first, which
tapping the face already does -- unpublish/republish now live only in
the opened detail panel, exactly where Phase 157's audit already found
them (unchanged there).

**Condition mapping, verified against the original render logic line by
line before deleting it:** `showActionButton` (`!deck.is_owner &&
(published || (isSubscribedMode && alreadyImported))`) and
`hasDuplicateOpenAction` (`!deck.is_owner && isSubscribedMode &&
alreadyImported`) are reused unchanged from the old `renderDeckCard`.
The pull-tab renders when `showActionButton && !hasDuplicateOpenAction`
-- in the `hasDuplicateOpenAction` case the old code already called the
exact same `onSelectDeck(deck.id)` from both its "상세 보기" and "열기"
buttons (confirmed by reading both `onClick`s side by side), so
suppressing the now-redundant pull-tab and leaving only the face
(itself `onSelectDeck`) reproduces the old two-controls-collapse-to-one
behavior exactly, just relocated. Every other state (newcomer, legacy
copied-mode re-import, subscribed-not-yet-imported) keeps both the face
and a distinct pull-tab, matching the old two-button count.

**Mobile bookshelf:** `.book-spine` switches to `flex: 0 1 calc(50% -
4px)` at `max-width: 640px` (a real width resize of the same item, not
a layout swap to a card list) -- 2 mini books per row, one of the
brief's own explicitly endorsed mobile directions. Measured via
`getBoundingClientRect()` at all three required widths: spines held a
consistent 2-column width (155px/148px/120px at 390/375/320) with the
tone fill, stickers, label, and pull-tab all still present and legible
-- no degradation to a single-column card list at any width tested.

**Header/detail panel:** left mostly as-is -- Phase 115/152 had already
moved the header (`.shared-hero-card`) to an unboxed heading strip with
small notched paper-tab actions, and the detail panel
(`.shared-deck-detail`) was already an opened-notebook-page treatment
(ruled paper, washi tape, folded corner); neither was named in Phase
157's audit as a card-grid problem, so neither was restructured. One
small cleanup taken up on the brief's own explicit invitation: the
detail panel's bottom "닫기" button was a literal duplicate of the
top-right "닫기" link (same handler, same label) -- rather than delete
it (a long subscribed word list can run to hundreds of rows, and losing
the only close control reachable without scrolling back up would be a
real usability regression, not a cleanup), it's recopied as "책장으로
돌아가기" with the same `onCloseDetail` handler, so it reads as this
book's own closing action instead of an identical second copy.

**Desktop (1280/1024) results:** confirmed via headless Chrome
screenshot at both widths -- the first viewport is unambiguously a
shelf of standing, tightly-packed, individually colored spines sitting
on a real wood ledge inside the cabinet, not a grid of cards. A DOM
query confirmed zero remaining `.shared-deck-card` elements. Tone-color
mapping verified correct by cross-referencing each spine's color
against its actual `deck.is_owner`/`mode` state (e.g. the one
user-owned deck rendered in the "mine" green tone with no pull-tab, an
imported subscribed-mode deck rendered brown with no pull-tab since its
face alone already opens it). The selected spine's "pulled off the
shelf" lift was confirmed as a real 14px `getBoundingClientRect()`
delta, not just a CSS class toggle with no visible effect. `document.
documentElement.scrollWidth === clientWidth` at both widths.

**Mobile (390/375/320) results:** 2-column mini-book grid confirmed at
all three widths via screenshot and measurement; spine tone fill,
title, count, and pull-tab label all stayed legible down to 320px; the
detail panel opened below the shelf with no overlap and its own
selected-spine highlight ring visible in the shelf above it. Zero
`scrollWidth`/`clientWidth` mismatch at any of the three widths.

**Owner/newcomer/subscriber conditions confirmed unchanged:** re-used
`showActionButton`/`hasDuplicateOpenAction`/`isDeckPublished`/
`getJlptLevel`/`getDeckCoverProps` verbatim from the removed function --
`git diff` on `SharedDeckSection.tsx` confirmed these helper functions
and the `SharedDeckSectionProps` callback signatures are byte-identical
to before this phase, changes scoped to the render output only.

**Detail/search/filter/pagination/StatusSelect confirmed working via
real interaction, not just present in the DOM:** opened a subscribed-
mode fixture deck (QA84, 85 words) via a real face click; typed into
the search input (a real `input` event, result count changed); clicked
a status filter chip (real click, result count changed); clicked "더
보기" pagination (80 -> 85 rows, exactly the fixture's real total);
changed a `StatusSelect` dropdown via a real `change` event
(`unknown -> known`) with zero console errors and zero failed
requests, confirming the `PATCH`-triggering `onUpdateWordStatus` path
still fires correctly through the new detail-panel shell (itself
unchanged). Also drove a real import (`내 노트에 담기` pull-tab on a
previously-not-imported deck) and confirmed, on a fresh page load
afterward, that the deck correctly showed as already-imported
(`다시 가져오기`) -- a genuine forward-progressing state change, left
in place rather than reverted, matching this project's established
precedent.

**Function/API/shared-deck-policy/storage confirmation:** no backend,
API route, schema, or shared-deck-policy file was touched. `git diff`
confirmed `onImportDeck`/`onUnpublishDeck`/`onRepublishSharedDeck`/
`onUpdateWordStatus`/`onSelectDeck`/`onCloseDetail`/`onRefresh` are all
called with the exact same arguments as before, only from new JSX call
sites. `toSharedDeckWordProgress`, the subscribed-word
search/filter/pagination `useMemo`/`useState` logic, and the entire
detail-panel word-list JSX are untouched line-for-line.

**Build/browser QA results:** `npm run build` clean (fresh `.next`, no
concurrent dev server). `git diff --check` clean. Verified via headless
Chrome (Windows-native, CDP) against the running dev server and real
backend at 1280/1024/390/375/320: Shared Deck tab load; list refresh;
newcomer import (real click, real state change, re-verified after
reload); subscriber detail open/close (real click, toggled both ways,
confirmed via `aria-expanded`); subscribed word list search/filter/
pagination/StatusSelect (all real interactions, described above);
zero console errors/warnings, zero failed requests, zero image errors
at every viewport (one pre-existing, unrelated `/favicon.ico` 404
excluded, consistent with every prior phase's own finding). A follow-up
full 7-tab x 5-viewport sweep confirmed zero regressions elsewhere in
the app from the `BrandElements.tsx` cleanup (removing the now-unused
`BrandDeckCover` export and its icon imports).

**Failure-criteria pass/fail (this phase's own 10-point list):**
1. Deck item is no longer a rounded-rectangle card -- **pass** (narrow
   standing spine, sharper corners, full-tone fill).
2. Cover/spine is not a top decoration -- **pass** (the tone color fills
   the whole spine; it is the spine, not a cap on a separate card body).
3. Title/meta/action don't read as card-internal UI -- **pass** (title
   is the spine's own label; action is a base-mounted pull-tab, not a
   footer button row).
4. Shelf isn't a background with floating cards on top -- **pass** (flex
   row of fixed-width standing items sitting on a shelf ledge; sparse
   rows leave visible shelf surface rather than stretching to fill it).
5. Mobile doesn't degrade to a card list -- **pass** (2-column mini-book
   grid at 390/375/320, measured, not assumed).
6. Spine/label isn't too small to find actions -- **pass** (pull-tab
   text wraps to stay fully legible rather than truncating; touch target
   spans the full spine width).
7. Owner/newcomer/subscriber conditions unchanged -- **pass** (verified
   via `git diff` on the reused condition variables).
8. StatusSelect/search/filter/pagination unbroken -- **pass** (verified
   via real interaction, not just DOM presence).
9. No non-Shiori character/animal/person -- **pass** (no new character
   assets introduced; the small dot/chevron/sticker elements are all
   CSS, matching this phase's own "lightweight CSS/SVG decorative
   elements 허용" allowance).
10. No text baked into a raster asset -- **pass** (no new image assets
    added at all; the old `deck-cute-cover-tile-atlas.webp` reference
    was already removed in Phase 152 and stays removed).

**Files changed:** `frontend/components/SharedDeckSection.tsx`,
`frontend/components/BrandElements.tsx`, `frontend/app/globals.css`,
this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural silhouette confirmed via screenshot
and DOM/measurement checks, real interaction coverage for every
required flow, condition/handler equivalence confirmed via diff) all
passed with zero console errors and zero failed requests. Per this
project's standing process, no commit/push was made -- left staged for
the user to review and commit alongside Phase 157's own still-
uncommitted changes.

**Remaining risk:** the spine's fixed 196px (desktop) / 158px (mobile)
height means a deck with an unusually long title relies entirely on the
5-line clamp to stay within it -- verified against this project's own
longest real fixture titles (the ~30-character QA/AIUX/Deploy/Stability
timestamp-suffixed names) with no visible clipping (`scrollHeight ===
clientHeight` confirmed via measurement, not just a screenshot glance),
but an even longer real-world title could clamp more aggressively than
ideal. No functional risk -- the full title is still available via the
face's `title` attribute and the opened detail panel's own unclamped
heading.

**Next phase recommendation:** re-run a Phase-157-style scene-first
audit specifically on Shared Deck once this lands, to confirm the new
silhouette holds up under the same strict rubric it was built to pass.
Otherwise, the three P2 items Phase 157 already queued (Study
ready-state board unity, Stats scene texture) remain the next candidates
in priority order once Deck's own re-audit closes out clean.

## Phase 159 -- Home v2 Scene Rebuild / One Hero Object, Not Two Clusters

Phase 151 fixed the book's scale and pulled the title note down to
physically overlap its top edge, but never touched the underlying
shape Phase 145 first built: `.home-stage { grid-template-columns:
1.4fr 0.85fr }`, book on one track, three sticky-note shortcuts
stacked on the other. Tightening that grid's gap and stretching the
shortcut column to match the book's height (both Phase 151) made the
two tracks sit closer together, but they never stopped being two
independent tracks -- a real screenshot still reads as a hero text
panel beside a shortcut column, i.e. an improved landing-page layout,
not a single object-centered scene. This phase discards the grid
entirely rather than tuning it again.

**Removed:**
- **`.home-stage`'s two-column CSS Grid** (`grid-template-columns:
  minmax(0,1.4fr) minmax(260px,0.85fr)`) -- the actual mechanism
  producing two clusters. There is no grid anywhere in the new
  markup; `.home-hero-cluster` is a single relatively-positioned box.
- **`.home-stickers`** -- the shortcut column's own sibling track,
  stretched via `align-items:stretch`/`justify-content:space-between`
  to fill the book's full height. Discarded along with the grid it
  depended on, not resized.
- **`.home-cover-cta`'s `border-radius:999px` plain pill shape** --
  this phase's own explicit failure list names "CTA가 admin button
  또는 generic pill처럼 보이면 실패," and a fully rounded pill button
  is exactly that shape, regardless of color. Home's CTA was the last
  one in the app still using it -- every other tab converted to the
  fixed-pixel clip-path notch family across Phases 149-158.
- **The old desk-prop z-index (`-1`)** -- correct for the two-column
  layout, where props sat in genuinely empty gaps between tracks;
  invisible in the single-cluster scene, where every sensible prop
  position now crosses an opaque sibling (the note or the book photo).
  Confirmed via `elementFromPoint()` that the leaf prop was present in
  the DOM at its intended coordinates with nothing visible -- painted
  entirely behind `.home-cover-note`.

**New one-hero-object silhouette:** `.home-hero-cluster` is sized to
the book photo itself (`.home-cover-object` drives its width via
`max-width`; nothing else in the cluster is independently sized). The
title note still overlaps the book's top-left edge (Phase 151's
technique, unchanged -- it already worked, the note was never the
problem). The three shortcuts are now `.home-shortcut-tab` elements,
absolutely positioned as a fanned row along the book's own bottom-right
edge, overlapping it by ~14-30px depending on viewport -- tabs tucked
under a notebook lying on a desk, not a second surface beside it. Desk
props (leaf/tape/paperclip/pen) reposition around the single cluster's
corners instead of bridging a column gap that no longer exists, now
painted *above* the book photo (see the z-index fix above) so they read
as real objects resting on the cover -- a pen crossing the spine, tape
and a paperclip weighting the lower-left corner, a leaf sprig behind
the top-right corner, opposite the note.

**How book/title/CTA/shortcuts were unified into one object:** every
piece shares the same positioning context (`.home-hero-cluster`,
`position:relative`), so "where does this sit" is always answered in
the same coordinate space the book itself is drawn in -- a percentage
or pixel offset on the note, a tab, or a prop is inherently relative to
the book's own box, not to an independently-sized sibling column.
Concretely: the note's negative `margin-bottom` pulls it onto the
book's top edge (kept from Phase 151); the CTA lives inside that note,
now shaped as a notched bookmark tag instead of a pill so it reads as
part of the note's own stationery rather than a web control sitting on
top of it; the shortcuts are pinned via `position:absolute; bottom`
inside the same cluster box the book fills, so their vertical position
is defined in terms of the book's own bottom edge, not a separate
track's height.

**How the shortcut column was discarded:** `.home-stickers` (flex
column stretched to the book's full height, each sticky note a
same-width tile stacked top-to-bottom) is gone outright. The three
`.home-shortcut-tab` buttons keep the exact same `onClick` handlers
(`onGoToVocab`, the `isDevUser ? onOpenAccount : onStartTodayReview`
branch, `onGoToSharedDecks`) and the same live hint-text logic
(`vocabHint`/`reviewHint`/`decksHint`, computed identically), just
positioned as a fanned row overlapping the book's bottom-right instead
of a column beside it. Mobile uses flat CSS-color tabs (no background-
image fetch); desktop upgrades to the same photographed sticky-note
textures (yellow/coral/blue) the old column used, just repositioned.

**Desktop (1280/1024) results:** confirmed via headless Chrome
screenshot at both widths -- the first viewport is unambiguously one
object: book dominant and centered, note glued to its top-left corner,
CTA shaped as a notched tag instead of a pill, three sticky-note tabs
fanned under the book's bottom-right edge with visible torn-paper
overlap, four props resting visibly on the cover. No separate "text
panel" or "shortcut column" read survives at either width. Iterated on
`.home-hero-cluster`'s `max-width` (720px -> 820px -> settled at 760px)
and `.home-shortcut-tabs`' vertical offset specifically to keep the
whole cluster, tabs included, within a realistic ~900px browser
viewport height without cutting the shortcuts below the fold -- verified
via `getBoundingClientRect()` measurement, not just a screenshot glance,
after finding the first (820px) attempt pushed the tabs' bottom edge to
y=928 against a 900px viewport. `document.documentElement.scrollWidth
=== clientWidth` at both widths.

**Mobile (390/375/320) results:** book, note, CTA, and the three tabs
render as one continuous cover scene at every width tested -- no
vertical section break between them. The CTA's notch shape and the
tabs' torn-paper overlap with the book's bottom edge are both still
legible at 320px. Tuned the mobile tab overlap specifically (`bottom:
4px` measured only ~2px of real overlap with the book's edge; raised to
`bottom: 16px` for a genuine ~14px overlap, confirmed via measurement)
rather than accepting a "close but not attached" result. Zero
`scrollWidth`/`clientWidth` mismatch at any of the three widths.

**Function/routing/storage confirmation:** no backend, API, schema,
SRS, storage, or auth file was touched. `git diff` on
`HomeDashboard.tsx` confirmed the component's prop signature and every
`onClick` handler wiring (`onStartReading`, `onTryWithSample`,
`onGoToVocab`, the dev-user account-panel branch on 복습,
`onGoToSharedDecks`) are unchanged -- only JSX structure, class names,
and comments differ. `vocabHint`/`reviewHint`/`decksHint` computation
is untouched.

**Build/browser QA results:** `npm run build` clean (fresh `.next`, no
concurrent dev server). `git diff --check` clean. Verified via headless
Chrome (Windows-native, CDP) against the running dev server and real
backend at 1280/1024/390/375/320: Home load; CTA click navigated to
Reading (confirmed via the result heading text, not just tab-active
state); sample action confirmed via a real second check after the
first attempt's naive "does a `<textarea>` have this text" assumption
turned out wrong for this app's actual behavior -- `onTryWithSample`
jumps straight to the analyzed reader result, confirmed instead by
reading `.reader-text`'s real content, which matched the sample
sentence; vocab shortcut navigated to 단어; review shortcut correctly
opened the account panel for the dev user (pre-existing behavior,
re-confirmed, not a regression); decks shortcut navigated to 덱;
toolbar 피드백 opened a real modal and 로그인 opened the real account
panel. A `window.confirm()` dialog triggered by chaining a sample-
action test after an already-active reading session (pre-existing
`startSampleReadingFromHome` behavior, unrelated to this phase) was
handled via `Page.handleJavaScriptDialog` rather than worked around by
skipping the check. A follow-up full 7-tab x 5-viewport sweep confirmed
zero regressions elsewhere in the app. Zero console errors/warnings,
zero failed requests, zero image errors throughout (one pre-existing,
unrelated `/favicon.ico` 404 excluded, consistent with every prior
phase's own finding).

**Failure-criteria pass/fail (this phase's own 10-point list):**
1. Title/CTA no longer separated from the book -- **pass** (same
   physical overlap technique as Phase 151, now the CTA itself is also
   shaped as part of the note's stationery rather than a floating
   control).
2. Shortcuts don't read as an independent right-hand column -- **pass**
   (no grid track exists for them to occupy; they are positioned
   directly against the book's own box).
3. The book is a layout anchor, not decoration -- **pass** (every other
   element's position is defined in terms of the book's own box).
4. First impression isn't a landing-page layout -- **pass** (one
   centered object with everything attached, confirmed via screenshot
   at every required width).
5. No wide abandoned empty wood area -- **pass**, with a caveat: side
   margins at 1280 are real but modest (roughly matching a normal
   centered-content margin, not a conspicuous gap) after widening the
   cluster from 720px to 760px specifically to address this; a
   materially wider cluster was tried (820px) and reverted because it
   pushed the shortcut tabs below a realistic fold.
6. Props are large enough to read as a scene -- **pass** (same
   Phase 151 prop sizes, now actually visible after the z-index fix,
   confirmed via screenshot -- pen, tape, and paperclip are clearly
   legible individual objects, not specks).
7. Mobile doesn't split back into vertical sections -- **pass**
   (measured overlap between the tabs and the book's bottom edge at
   390px, not just visually similar spacing).
8. CTA isn't a generic pill -- **pass** (converted to the app's
   established notched-tag CTA family).
9. Shortcut text doesn't read as forced onto an image -- **pass**
   (mobile tabs are flat CSS color, not an image; desktop tabs use the
   same sticky-note photo texture every other tab's equivalent shortcut
   already uses successfully).
10. No non-Shiori character/animal/person -- **pass** (no new character
    assets; Shiori's existing `review`/`default` variants reused
    unchanged, now at `size="sm"` for the smaller review tab icon
    instead of `md`).

**Files changed:** `frontend/components/HomeDashboard.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural silhouette confirmed via screenshot
and `getBoundingClientRect()` measurement at multiple iteration
points, not accepted on the first attempt; full functional click-
through coverage; a real prop-invisibility bug found via
`elementFromPoint()` and fixed, not just visually patched) all passed
with zero console errors and zero failed requests. Per this project's
standing process, no commit/push was made -- left staged for the user
to review and commit alongside Phase 157/158's own still-uncommitted
changes.

**Remaining risk:** the shortcut tabs' overlap with the book's bottom
edge (26-46px offset depending on viewport) was tuned against this
phase's own current copy lengths (온단어/복습/덱, plus their hint
lines) -- meaningfully longer hint text in the future could make a
desktop tab wrap to a third line and grow taller than the space
reserved for it, in the same general category of risk Phase 151's own
closing note already flagged for the title note's copy length. Not a
concern for the current copy (verified at all five required widths).
The 1280 side margins, while much reduced from before this phase,
are a deliberate compromise against fold height rather than fully
eliminated -- a next pass could explore reclaiming more of that width
without growing the book's height (e.g. widening only the prop/shadow
canvas, not the book photo itself) if a future audit still flags it.

**Next phase recommendation:** re-run a Phase-157-style scene-first
audit specifically on Home once this lands, the same close-the-loop
step recommended for Shared Deck in Phase 158. Otherwise the existing
queue holds: Shared Deck card-shape rework (Phase 158's own next-step),
then Study ready-state board unity, then Stats scene texture.

## Phase 160 -- Study v2 Board Unity / One Felt Board Scene

Phase 66 introduced the felt board, Phase 148 lightened it, Phase 153
de-boxed the quick-start tiles and the ready/empty note into pinned-
memo/paper-note language -- but none of those passes ever questioned
where `.study-board-scene` actually started in the DOM. It always
began right before the ready/empty/active/complete states; the
quick-start hero and the 학습 옵션/학습 현황 disclosures rendered as
siblings *above* it, on the plain page background. Every individual
piece looked right in isolation (Phase 153 in particular already made
the quick-start tiles and the ready note read as genuinely pinned
objects), but the actual DOM boundary meant the tab was always
"controls, then a board," regardless of how good each half looked on
its own -- exactly the split this phase's brief names directly. This
phase moves the boundary, not the decoration.

**Removed:**
- **The DOM boundary itself** -- `.study-board-scene` used to open
  right before the ready-state block; it now opens as the very first
  child of `.study-panel`, wrapping the quick-start header, both
  disclosures, the inline message, and every ready/empty/active/
  complete state in one element. This is the actual fix; everything
  else in this phase is downstream of it.
- **`.study-hero-card`'s dashed bottom border** -- existed specifically
  to mark "page content ends here, the board begins below." With the
  heading now rendered *inside* the board, there is no seam left to
  mark, so the rule (and the class name, renamed to `.study-board-
  header`) is gone.
- **Both disclosure summaries' settings-row look** (`border-bottom: 1px
  dashed`, full-width flex row, no surface of its own) -- read as
  settings-panel rows when they sat on the plain page background above
  the board; now that they're rendered on felt, that treatment would
  have been invisible-to-illegible depending on contrast. Replaced with
  small pinned paper tags (see below).
- **The disclosures' flattened-open-panel styling** (`.study-stats-
  collapsible .stats-panel`'s border/shadow stripped to nothing, "to
  continue the board above it") -- that flattening made sense when the
  disclosure sat on a plain page background transitioning into a board;
  now that the closed tag itself sits on felt, the *opened* panel is
  supposed to read as a small note that unfolded off the board, which
  needs its own border/shadow to read as a distinct surface, not a
  flattened extension of the felt.

**New one-board-scene silhouette:** `.study-board-scene` is the only
board on the tab, and it now holds everything: `.study-board-header`
(icon/title/subtitle, the compact progress bar, the four pinned
`.study-cta-button` quick-start tiles -- untouched, they already read
as pinned memos, just relocated -- and the two quiet secondary links),
`.study-board-tag-row` (the two disclosures, now small rotated paper
tags), the inline message if any, and then whichever of ready/empty/
active/complete state applies. Every one of those pieces sits on the
same `study-light-mint-felt-board.webp` texture, in one continuous
`display: grid` flow with no nested "settings area."

**How quick-start was integrated into the board:** `StudyQuickStartHero`
(a `<section className="study-hero-card">` rendered as a sibling above
the board) became `StudyBoardQuickStart`, a plain fragment returning
`<div className="study-board-header">` -- no section wrapper, no
boxed/bordered chrome of its own, meant to be rendered as the first
child inside `.study-board-scene` by the caller. The four quick-start
tiles' own CSS (`.study-cta-grid`/`.study-cta-button`, the per-tile
pin-dot/rotation/stagger) is completely unchanged -- that pinned-memo
language already worked (Phase 153's own fix), the only problem was
which element it was a child of.

**How options/details/deck summary were demoted:** both `<details>`
elements gained a shared `.study-board-tag` class. The closed
`<summary>` is now a small `var(--panel-bg)` paper tag (rounded
asymmetric corners, drop shadow, ±1deg rotation, same family as the
quick-start tiles beside it) instead of a full-width dashed-border row
-- "학습 옵션 · 전체 단어장 · 오늘 복습" and "학습 현황 자세히 보기"
now read as two small pinned labels sitting on the felt next to the
quick-start cluster, not a settings list below it. Opened, each
reveals its existing content (`.study-control-panel`/`StatsPanel`)
restyled as a small unfolded note -- kept its light `panel-bg` card
look (border + soft shadow) rather than flattening it, so it reads as
"this tag opened into a note," not a seam continuing the felt. No
`<select>`, `onChange`, or `onStart` handler was touched -- only the
JSX nesting and the summary/panel CSS.

**Empty/ready/active/completion connectivity:** the ready-state note
(`.study-board-note`, Phase 153's pinned-note treatment) and the
active review card stack (`.study-card-stack`) were already board
children before this phase and needed no restructuring -- moving the
DOM boundary up around everything else is what makes them read as
continuous with the quick-start/tags above them instead of "the one
part of the screen that was already on the board." The completion
state gets this for free from existing logic, not new code:
`isReviewingActive` (`Boolean(currentItem) && !isComplete`) is false
once a session completes, so the quick-start header and both tags
reappear *above* the completion receipt, all still inside the same
`.study-board-scene` -- confirmed via screenshot that a completed
session shows the full quick-start cluster, the "다음 복습이
예약됐어요" message, and the stamped completion card all on one
continuous felt surface, letting a learner start another mode
immediately without leaving the board.

**Desktop (1280/1024) results:** confirmed via headless Chrome
screenshot at both widths -- the first viewport is unambiguously one
felt board: heading, progress bar, four pinned quick-start tiles, two
secondary links, two small disclosure tags, and the ready note all
sit on the same mint-green weave with no visible seam between a
"control area" and "board area." Opened both disclosures in the same
screenshot to confirm their unfolded panels read as notes on the
board, not settings dialogs. `document.documentElement.scrollWidth
=== clientWidth` at both widths.

**Mobile (390/375/320) results:** the same one-board composition holds
at every width -- quick-start's primary tile stays a full-width bar (an
intentional, pre-existing Phase 82/153 choice for the one loud action,
not the "full-width button stack" failure this phase's brief warns
against) while the three secondary tiles and both disclosure tags stay
compact and pinned, not stretched. Verified the mobile answer-reveal
rating grid specifically against Phase 110's own protected concern,
using real phone viewport heights (375x812, 390x844, 320x640, not the
taller 1400px used for full-page screenshots elsewhere in this pass) --
`getBoundingClientRect()` confirmed the 2x2 rating grid's bottom edge
stays within the visible viewport at all three sizes (e.g. 623px bottom
edge against a 640px viewport at 320x640), so the four-way decision is
visible immediately after reveal without scrolling. Zero
`scrollWidth`/`clientWidth` mismatch at any width.

**Rating/SRS/API/storage confirmation:** no backend, API, schema, SRS,
storage, or auth file was touched. `git diff` on `StudySection.tsx`
confirmed `ratingButtons` (labels/colors/hints/icons/handlers),
`onReview`, `onShowAnswer`, `onStart`, `onQuickStart`,
`onSelectedDeckChange`, `onStudyModeChange`, and every other callback
signature are byte-identical to before this phase -- changes scoped to
JSX nesting, class names, and comments. A real review session was
driven end-to-end via CDP click automation (not just diffed): selected
"헷갈리는 단어" mode and the default deck via the real `<select>`
elements inside the reopened options tag, clicked "학습 시작", then
separately drove 5 distinct cards through reveal -> rate -> next-card
on "오늘 복습" (오늘 복습 20개), confirming the progress marker advanced
1/19 -> 5/19 and the surface text actually changed each time (중 ->
響い -> 体 -> 猫 -> 闇), not just that a click handler fired.

**Build/browser QA results:** `npm run build` clean (fresh `.next`, no
concurrent dev server). `git diff --check` clean. Verified via headless
Chrome (Windows-native, CDP) against the running dev server and real
backend at 1280/1024/390/375/320: Study tab load; all four quick-start
tiles rendered and clickable; deck/mode selection via the real options
disclosure; both disclosures opened/closed; a real review session
started, answer revealed, 4-way rating clicked, next card confirmed
distinct; a session driven to natural completion (rating every card
"보통" until `.complete-card` appeared); completion state's restart/
read/vocab links confirmed reachable and not full-width bars; toolbar
피드백 opened a real modal. A follow-up full 7-tab x 5-viewport sweep
confirmed zero regressions elsewhere in the app. Zero console
errors/warnings, zero failed requests, zero image errors throughout
(one pre-existing, unrelated `/favicon.ico` 404 excluded, consistent
with every prior phase's own finding).

**Failure-criteria pass/fail (this phase's own 10-point list):**
1. Quick-start no longer reads as a board-external top control area --
   **pass** (rendered inside `.study-board-scene` as its first child;
   confirmed via `querySelector('.study-board-scene .study-board-
   header')`).
2. Options/details rows don't read as a settings panel -- **pass**
   (small pinned tags replacing full-width dashed-border rows).
3. The empty note isn't a big white card/modal -- **pass** (unchanged
   from Phase 153's own small rotated `.study-board-note`, now simply
   continuous with the rest of the board instead of the one board-
   native element on the tab).
4. The board isn't a decorative backdrop under separately-floating
   controls -- **pass** (every interactive element -- quick-start
   tiles, both disclosure tags, the deck/mode selects, the rating
   grid -- is a DOM descendant of `.study-board-scene`).
5. Ready/empty/active/complete all read as the same board, not just
   the active branch -- **pass**, confirmed via screenshot at all
   four states, including the completion state showing quick-start
   above the receipt on the same felt.
6. Mobile quick-start doesn't degrade to a full-width button stack --
   **pass** (only the one intentional primary tile is full-width, a
   pre-existing choice this phase didn't touch; the three secondary
   tiles and both tags stay compact/pinned).
7. The rating grid doesn't get pushed below the mobile fold -- **pass**
   (measured, not assumed, at three real phone viewport heights).
8. Rating stamp semantics/colors/handlers are unchanged -- **pass**
   (confirmed via `git diff` showing `ratingButtons` and `onReview`
   untouched, and via a real session that correctly saved 다시/어려움/
   보통/쉬움 results).
9. No non-Shiori character/animal/person -- **pass** (no new character
   assets; `ShioriStamp`'s existing `success` variant reused unchanged
   on the completion card).
10. No text baked into a raster asset -- **pass** (no new image assets;
    the existing felt-board photo and flashcard-stack photo are reused
    unchanged, both textures with no text in them).

**Files changed:** `frontend/components/StudySection.tsx`,
`frontend/app/globals.css`, this file.

**Commit-readiness:** yes -- build and diff-check clean, full
5-viewport browser QA (structural unity confirmed via screenshot at
every state including disclosures-open and completion, a full click-
through review session with distinct-card verification, mobile rating-
grid fold position measured at real phone heights rather than assumed)
all passed with zero console errors and zero failed requests. Per this
project's standing process, no commit/push was made -- left staged for
the user to review and commit alongside Phase 157/158/159's own still-
uncommitted changes.

**Remaining risk:** none identified specific to this phase's own
changes -- this was a pure DOM-relocation-plus-restyle pass with no
new interaction logic. The two disclosure tags' `.study-options-
summary-hint` text (deck name · mode label) is now capped at
`max-width: 150px` with ellipsis truncation, tighter than its old
full-row width -- a very long personal deck name could truncate more
aggressively than before, though the full deck/mode selection remains
one tap away inside the opened tag regardless.

**Next phase recommendation:** re-run a Phase-157-style scene-first
audit specifically on Study once this lands, the same close-the-loop
step already recommended for Shared Deck (Phase 158) and Home
(Phase 159). Otherwise the queue holds: Shared Deck card-shape rework
(Phase 158's own next-step, still open), then Stats scene texture
(the one remaining P2 from Phase 157's original audit).

## Phase 162 -- V2 Scene Redesign Bible / Documentation Reset

After Phase 158-161, the core product problem changed: several tabs had
scene-like materials and some real structural wins, but the screenshots
still often read as "old app skeleton plus cute stationery" rather than
a newly designed app. The recurring failure was no longer a missing tape
accent, weak shadow, or single bad button. It was the documentation and
phase prompts continuing to normalize the old skeleton: toolbar -> title
-> controls -> cards/lists -> side panel. This phase therefore stopped
implementation and reset the documentation contract first.

**New authority:** `docs/design/V2_SCENE_REDESIGN_BIBLE.md` is now the
current visual redesign authority for future scene work. Its central
rule is stricter than the original Phase 54 brief: do not reskin the
existing tab UI. Design each tab as a new physical stationery scene, then
reattach the existing behavior inside it. The document defines the target
world (Japanese stationery desk, study planner, flat-lay notebook
objects), the non-negotiables (preserve API/SRS/storage/auth/shared-deck
policy; live text stays DOM text; Shiori is the only character), the
tab-by-tab V2 silhouettes, the asset plan, the motion language, and the
new implementation strategy (new V2 scene components are preferred when
old DOM fights the scene).

**V2 ratio-specific mockups generated:** the first two concept boards
were removed after review because their internal panel ratios did not
match the real implementation viewports; using them as asset/layout
targets encouraged sparse desktop scenes. They were replaced with
individual tab mockups under `docs/design/mockups/v2/`: desktop
`v2-desktop-*-16x9.png` files and mobile `v2-mobile-*-9x16.png` files
for Home, Reading, Vocab, Study, Shared Deck, Analyze/Classify, and
Stats. These are not production UI images; they are first-read
silhouette references at the actual target ratios. Their text-like marks
are placeholders only. Future implementation must keep live UI copy in
DOM and use the existing Shiori component set rather than copying any
generated mascot detail.

**Old documentation demoted, not deleted:** this file remains the durable
phase history; `casual-sticker-reader-redesign-brief.md` remains useful
for product truth and the original Casual Sticker Reader direction;
`phase145-casual-cute-tab-rebuild-plan.md` remains useful for asset
provenance and the symptoms that prompted the cute/stationery turn;
`v4-reader-first-redesign-proposal.md` remains useful IA background; and
`ui-guidelines.md` remains useful for copy, safety, Shiori placement, and
legacy implementation details. But all of them are now historical or
supporting references when they conflict with the V2 bible. In
particular, old guidance that implies default reuse of `panel-card`,
`hero-card`, side widgets, card grids, or filter panels must not override
a scene-first reconstruction brief.

**Deprecated patterns made explicit:** the V2 bible names the patterns
that kept surviving across earlier phases: generic metric chips,
separate right widget panels, filter/settings panels, card grids posing
as shelves, toolbar/banner rows stacked above scene objects, image
textures placed behind unchanged cards, and full-width mobile admin
button stacks. Future implementation reports should start with which of
these old structures were actually removed. If a reconstruction phase
has only a tiny CSS diff and leaves the old skeleton visible, the report
must treat that as a likely design failure rather than a successful
polish.

**Current tab targets recorded:** Home becomes one large green notebook
hero cluster; Reading becomes one open book with input/reader/inspector/
save flow belonging to the same object; Vocab becomes a physical index
notebook; Study becomes a light felt board; Shared Deck becomes a mini
bookshelf; Analyze/Classify becomes a card-making desk; Stats becomes a
study logbook. App Shell should be judged last, after tab scenes are
stable, so shell changes support the scenes rather than becoming another
global frame exercise.

**Files changed:** `docs/design/V2_SCENE_REDESIGN_BIBLE.md`,
`docs/design/DESIGN.md`, `docs/design/casual-sticker-reader-redesign-
brief.md`, `docs/design/phase145-casual-cute-tab-rebuild-plan.md`,
`docs/design/ui-guidelines.md`, plus the ratio-specific V2 mockup set in
`docs/design/mockups/v2/`.

**Next phase recommendation:** begin V2 implementation with the weakest
fresh screenshot, not with another global polish pass. Likely candidates
are **Classify V2** (large empty grid-paper area and small card-making
objects still make the scene weak) or **Vocab V2** (filter/index controls
still risk reading as a management panel). The phase prompt should use
the V2 bible's required four-part opening: new scene silhouette, old
structure to discard, functional core to preserve, and needed material
anchors.

## Phase 163 -- V2 Implementation Asset Kit / Ratio-Specific Scene Bases

Following the Phase 162 documentation reset, this phase generated production-
oriented scene-base assets rather than more UI screenshots. The goal was to
avoid the old failure mode where a single desktop-ish mockup or asset was
cropped into mismatched viewports, leaving the app sparse on desktop or cramped
on mobile.

**Generated runtime kit:** `frontend/public/brand/decor/v2/` now contains
fourteen WebP scene bases: desktop 16:9 and mobile 9:16 versions for Home,
Reading, Vocab, Study, Shared Deck, Analyze/Classify, and Stats. The full list
and application rules are recorded in
`frontend/public/brand/decor/v2/ASSET_MANIFEST.md`. The assets are blank
physical scenes: no UI copy, no Japanese vocabulary, no counts, no icons, no
new mascot, and no Shiori baked into pixels. Shiori must continue to render
through the existing Shiori component set.

**Source preservation and performance:** generated PNG masters were copied to
`docs/design/source-assets/v2-generated-png/` for provenance, then converted to
runtime WebP files at quality 88. The public V2 kit is about 2.46MB total,
instead of roughly 31MB of raw PNGs. This keeps the assets viable for actual
implementation rather than another heavy design-only artifact.

**Scene coverage:** Home has separate notebook hero scenes; Reading has open-
book/page scenes; Vocab has broad index-tab notebook scenes; Study has light
felt-board scenes; Shared Deck has dense bookshelf scenes; Classify has a card-
making desk with source slip, stamp, and tray; Stats has logbook/ledger scenes.
The Shared Deck desktop candidate was regenerated during this phase because an
earlier attempt left too much empty wall space, directly contradicting the V2
goal of avoiding sparse desktop compositions. The Study and Stats mobile
candidates were also regenerated after spotting unsuitable artifacts/text-like
marks.

**Implementation warning:** these images are material anchors, not decoration
to place behind unchanged `panel-card` or `hero-card` structures. Future V2
phases must still begin by deleting the old tab silhouette, then reattaching
existing behavior into the scene. If an implementation keeps the old dashboard,
form, card grid, sidebar, or filter-panel skeleton and merely swaps the
background image, it fails the V2 contract.

**Code impact:** no runtime React/CSS was changed in this phase. It is an asset
and documentation phase only.

**Next phase recommendation:** start implementation with a one-tab V2 pilot
using the new assets and the Phase 162 prompt structure. The likely candidates
remain Classify V2 or Vocab V2, because they are the clearest tests of whether
we can actually replace the old skeleton rather than decorate it.

## Phase 164 -- V2 Asset Contact Sheet / Safe-Zone Review

This phase prepared the implementation handoff after Phase 163's asset kit.
The current work started from a clean `phase-164` branch after the Phase 162-
163 documentation/mockup/asset changes were committed, pushed, fast-forwarded
into `main`, pushed to `origin/main`, and the `phase-162` branch was deleted
locally and remotely.

**Contact sheet created:** `docs/design/mockups/v2/v2-asset-contact-sheet-
safe-zones.png` combines all fourteen V2 runtime assets with green overlay
boxes showing the primary live-DOM safe zones. This is intentionally not a UI
mockup. It is a placement/audit sheet for where live text, buttons, state, and
Shiori components can sit without being baked into raster images.

**Safe-zone review created:** `docs/design/V2_ASSET_SAFE_ZONE_REVIEW.md`
records the tab-by-tab verdicts. All seven tabs pass asset readiness for both
desktop and mobile. The review also names the implementation trap for each
tab: Home must not split back into title column plus book; Reading must keep
input and book material distinct; Vocab must delete the old filter panel;
Study must avoid a white admin card on the board; Shared Deck must use book
spines as deck items; Classify must become source slip -> stamp -> card tray;
Stats must avoid dashboard metric cards.

**No further asset blockers:** no additional raster asset generation is needed
before implementation. Small transparent cutouts may still be generated later
for a specific component if needed, but collecting more decoration now would
delay the real work: replacing old silhouettes.

**Next phase recommendation:** start with **Classify V2** as the first pilot.
It has the clearest old-structure failure and the clearest new scene workflow,
so the screenshot result will make success or failure obvious.

## Phase 165 -- Classify V2 Full Scene Reconstruction (V2 Pilot)

The first real implementation pilot for the V2 scene bible: Classify's intro
stage now renders on top of the actual `v2-classify-card-desk-*` photos
(`frontend/public/brand/decor/v2/`) instead of a CSS-drawn approximation of a
desk. `AnalyzeSection.tsx`'s Phase 156 `ClassifyDeskIntro`/`ClassifySourceSlip`/
`ClassifyDeskControls`/`ClassifyCardTray` were replaced with `ClassifyDeskV2`/
`ClassifySourceSlipV2`/`ClassifyDeskChipRowV2`/`ClassifyCardTrayV2`: the new
`.classify-v2-scene` is an `aspect-ratio` box whose `background-image` is the
photo itself (mobile 9:16 by default, desktop 16:9 swapped in at `>=1024px`,
matching the app's existing desktop-tier split), and every live control --
the source textarea, the deck-select/show-known paper chips, the stamp CTA,
and the draft-resume receipt -- is an absolutely-positioned sibling placed
against that photo's actual paper/stamp/tray objects, independently
positioned per breakpoint since the two photos are different compositions,
not a crop of one image. The textarea itself is transparent so typed text
reads as ink on the photographed ruled paper rather than a white input box
floating over it. `.classify-card-tray`'s old decorative CSS card-fan was
dropped outright -- the photo already shows a real card stack, so the tray
zone now only needs to carry the resumeable-draft receipt (reusing
`.classify-draft-chip`/`.classify-quiet-link` unchanged). The post-analyze
`ClassifyResultSummary` was also de-boxed: it no longer shares
`.classify-word-card`'s bordered/border-top-accent panel rule (a literal
"dashboard card" silhouette flagged by this phase's own failure criteria) --
it's now its own asymmetric-corner-radius, slightly rotated card, and the
four result-count tiles picked up more rotation/vertical stagger so they read
as a small scattered card fan rather than an aligned pill row. The
classify-card decision stage itself (`.classify-word-card`, the 4-way
`.classify-action-grid`, Phase 112's mobile decision-grid protection) was
deliberately left untouched, per this phase's brief.

QA: `npm run build` clean, `git diff --check` clean. Real headless-Chrome
(CDP, no Playwright installed -- see the WSL/CDP memory notes) QA against a
scratch sqlite backend and a fresh registered test user covered 1280/1024/
390/375/320px: desktop loads the 16:9 asset and only the 16:9 asset, mobile
loads the 9:16 asset and only the 9:16 asset, zero horizontal overflow at
every width, zero console errors, zero unexpected failed requests. Full
functional flow verified end-to-end: fill source slip, select deck, toggle
show-known, click the stamp CTA, `/analyze`, enter the card stage, classify 6+
cards mixing all 4 statuses plus skip, reach the result summary, toggle the
ledger, save, and confirm the save message. A second run specifically
verified draft persistence: classify 3/10 cards, reload, confirm the draft
receipt appears in the tray zone (not a full-width banner), click "이어하기",
and confirm it resumes at card 4/10. Phase 112's mobile decision grid was
re-measured mid-flow at 390px and stays fully inside the viewport. One
transient failure mid-session was traced to running `npm run build` while
`npm run dev` was still live in the same directory (the documented `.next`
corruption issue) -- recovered by killing the dev server, `rm -rf .next`, and
restarting, per the existing WSL dev-server memory notes; not a code defect.

Remaining risk: the result-summary de-boxing is a light touch, not a full
V2 scene treatment (no "finished card bundle" photo asset exists yet) -- it
still reads as a soft card rather than a fully physical object, and the
shared `CoverageSummary` component's own bordered box (used by other tabs
too) was left as-is, out of this phase's file scope. Next candidate: Vocab V2
(the remaining tab with the clearest old filter-panel skeleton) or Home V2,
per the bible's recommended order.
