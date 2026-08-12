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
  admin box. Candidate/word list redesigned in Phase 56 (see below).
- **Reading candidate word list** (Phase 56) — `ReadingVocabPanel`'s
  full-width row list is now a flex-wrap sticker tray
  (`.reading-vocab-tray`/`.reading-vocab-sticker*`): each word is a small
  content-sized note with an alternating tilt, a round pin toggle (was a
  square checkbox) that gets a stamped ✓ seal when selected instead of an
  inset accent bar, and a muted check-circle placeholder (not a blank
  spacer) on already-known words so "why can't I add this" stays visible.
  Search/filter/quick-select are now underline text-tabs, not bordered pill
  buttons, to read as labels on the tray rather than a toolbar.
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
  deliberately minimal for the same reason.
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
  untouched.
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
`>=1024px` tier as Phase 65/66 and leaves mobile/tablet unchanged. See the
brief's "Implementation order recommendation" for any further polish
passes (Shared Deck shelf, Analyze/Stats/Feedback).
