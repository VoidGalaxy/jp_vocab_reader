# DESIGN.md — Casual Sticker Reader

Durable visual direction for 책갈피 (jp_vocab_reader), starting Phase 54. This
replaces the earlier "study desk" direction as the visual authority; treat the
old boxed/card-tile look as evidence of what to avoid, not something to keep
polishing. Source brief: `docs/design/casual-sticker-reader-redesign-brief.md`.
Reference boards: `docs/design/mockups/casual-sticker-reader-mobile.png`,
`docs/design/mockups/casual-sticker-reader-desktop.png` (directional, not
pixel specs).

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
