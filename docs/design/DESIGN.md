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
