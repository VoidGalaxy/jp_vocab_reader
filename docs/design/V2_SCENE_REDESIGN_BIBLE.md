# V2 Scene Redesign Bible

Status: Phase 162 planning authority. This document supersedes the earlier
"polish the current layout" approach for future visual redesign work.

The app should no longer be redesigned by decorating existing panels. The next
round should treat each tab as a new scene and then reconnect the existing
product behavior inside that scene.

Reference mockups generated for this V2 reset:

- Desktop 16:9 tab scenes: `docs/design/mockups/v2/v2-desktop-*-16x9.png`
- Mobile 9:16 tab scenes: `docs/design/mockups/v2/v2-mobile-*-9x16.png`

The earlier two-board contact sheets were removed because their internal panel
ratios did not match the implementation viewports and encouraged sparse
desktop layouts. The current mockups are individual, ratio-specific screen
references for Home, Reading, Vocab, Study, Shared Deck, Analyze/Classify, and
Stats. They are silhouette and mood references, not production screenshots, and
their tiny placeholder marks are not UI copy. Implement live text in DOM, use
existing Shiori components for mascot placement, and do not copy generated
character details as app assets.

## 1. Why We Are Restarting

The recent phases improved materials, images, buttons, and texture, but the
same old silhouettes kept returning:

- top app bar, then tab title, then controls, then cards/lists
- large paper canvas with small UI clusters placed on it
- dashboard rows, side widgets, form panels, and management filters
- decorative assets used as wallpaper behind unchanged UI
- mobile layouts collapsing back into stacked full-width controls

That is why the result still often reads as "a cute web app" instead of a
casual study desk. The next redesign must change the first-read silhouette, not
only the surface style.

## 2. Target Design

Target feeling: casual Japanese stationery desk.

Use these as reference families:

- Japanese stationery shop displays
- study planner and diary pages
- desk flat-lay compositions
- notebook tabs, memo slips, book spines, stamp pads, labels
- cute but practical adult stationery, not toy UI

Do not use:

- SaaS dashboard layouts
- admin panels
- equal-width button grids
- generic card grids
- large empty paper boards with small controls floating in the middle
- decorative images that do not determine layout

The tone should be warmer, cuter, and more handmade than the current polished
notebook look, while keeping Japanese text, word rows, and review decisions
readable.

## 3. Core Method

For every tab, define these before implementation:

1. **New scene silhouette**: what physical object or scene should the screenshot
   read as in the first second?
2. **Old structure to discard**: which existing wrappers, card grids, panels,
   forms, rows, sidebars, or toolbar stacks must not survive?
3. **Functional core to preserve**: which handlers, data flows, storage rules,
   and user tasks must keep working?
4. **Material anchors**: which assets or CSS-built objects determine layout:
   book, open page, index tabs, felt board, shelf, slips, stamps, labels?

Implementation should prefer new V2 scene components when the old component
tree fights the scene. Preserve behavior, not old DOM.

## 4. Non-Negotiables

- Backend/API/schema/SRS/storage/auth/shared-deck policy stay unchanged unless a
  phase explicitly asks for product behavior changes.
- Full original reading text must not be duplicated into secondary cards,
  shared decks, review UI, feedback, or localStorage payloads.
- Live product text stays DOM text. Do not bake Korean/Japanese/UI copy into
  raster assets.
- Shiori is the only character. No other mascots, people, animals, faces, or
  Shiori substitutes.
- Functional QA is required, but it is not design success. A clean build with a
  weak silhouette is still a failed redesign.
- A tiny diff is suspicious in a reconstruction phase. If the old skeleton is
  still visible, report that honestly.

## 5. Global V2 App Structure

The app shell should support scenes, not frame every tab as the same web app.

Keep:

- all tab navigation
- feedback access
- account access
- keyboard and pointer usability
- mobile drawer access

Question or discard later:

- toolbar dominance over immersive scenes
- repeated top spacing that creates dead paper/wood above the scene
- any shell rule that forces every tab into the same centered paper board

Do not start by rebuilding the shell alone. First get tab scenes right, then
reduce the shell if it still weakens them.

## 6. Tab V2 Directions

### Home V2

Scene: one large green notebook/book object as the first-viewport hero.

Discard:

- separate title block plus separate book object
- independent shortcut column
- tiny props scattered around a wide empty desk
- carousel/page dots
- generic hero card

Preserve:

- start reading CTA
- sample flow
- vocab/study/deck shortcuts
- account, feedback, toolbar/drawer access

Assets:

- green notebook object or composite
- sticky shortcut notes attached to the notebook
- larger desk props anchored to the book, not floating in the void

Motion:

- shortcut notes lift a few pixels on hover
- CTA presses like a paper tab/stamp, not a glowing button

### Reading V2

Scene: one open book where input, reading text, inspector, and save flow belong
to the same reading notebook.

Discard:

- textarea as standalone web form
- giant submit/admin bar
- save/candidate controls as a control strip
- beige-on-beige layers with no hierarchy
- restore/options banners that feel like alerts above the book

Preserve:

- sample fill, analyze, restored session
- token rendering and inspector
- status classify and auto-save policy
- candidate tray, quick select, selected save
- review/vocab navigation

Assets:

- open book spread
- distinct source/input slip
- selected-word memo strip
- bookmark/action tags

Motion:

- inspector lifts in like a note
- selected words tuck into a memo strip
- status stamps depress briefly

### Vocab V2

Scene: physical index notebook. Left side is broad index tabs, middle is a
scan-first word ledger, right side is the same notebook's detail page.

Discard:

- generic three-column app layout
- filter/search/sort management panel
- active filter as button block
- detached right illustration/card
- labels colliding with rings/tabs/edges

Preserve:

- deck picker, search, status filters, sort
- row expand/detail selection
- meaning edit/report, status update, delete
- deck management/share/custom terms/import/export

Assets:

- broad physical index tabs with reserved text area
- ledger paper rows
- detail note/page

Motion:

- selected tab slides out slightly
- selected word row pulls the detail page into focus

### Study V2

Scene: light felt board with pinned notes and rating stamps. The active review
card is a flashcard stack on the board.

Discard:

- top controls detached from board scene
- equal-width button cards
- big white empty guidance modal
- full-width mobile admin action stacks

Preserve:

- four study modes
- deck/mode selection
- answer reveal
- four-way rating semantics and colors
- review submission, progress, completion, restart

Assets:

- light felt board
- pinned memo tiles
- pins/tape
- flashcard stack

Motion:

- memo choices wiggle/lift lightly
- answer reveal flips or slides as a card surface
- rating stamp press is quick and tactile

### Shared Deck V2

Scene: real mini bookshelf. Shared decks are book spines or mini books on a
shelf, not cards with cover decoration.

Discard:

- card grid
- cover plus metadata below as card body
- sparse shelf regions created by stretched cards
- boxed notices/actions above shelf
- covers that compete with live labels

Preserve:

- load/refresh shared decks
- owner unpublish/republish
- newcomer import
- subscriber open/detail/progress
- word list search/filter/pagination
- StatusSelect and shared-deck policy

Assets:

- simple spine system
- shelf background
- pulled-book/detail note

Motion:

- selected spine lifts or pulls forward
- detail opens as a note/book page associated with that spine

### Analyze / Classify V2

Scene: card-making desk. The source text is a pinned slip, controls are paper
chips, CTA is a stamp, and card stacks are visible early.

Discard:

- textarea-dominant form
- select/checkbox/button row as web controls
- empty grid-paper area with no task object
- dashboard result counts

Preserve:

- text input, deck select, show-known toggle
- start classify, resume/delete draft
- card-by-card status selection and skip
- progress, result summary, save
- draft persistence

Assets:

- source slip
- blank card stack
- stamp CTA
- finished card bundle

Motion:

- source slip becomes card stack metaphor
- classify card advances with a paper-card movement, not a generic fade
- save action stamps the finished bundle

### Stats V2

Scene: study logbook. Numbers are stamps/tags, deck progress is ledger writing,
recent/difficult words are memo slips in the same record book.

Discard:

- dashboard metric row
- repeated stat cards
- analytics progress widgets
- separate right widget panel
- boxed policy/info card

Preserve:

- stats load
- today summary
- diary/log text
- deck progress rows and detail disclosure
- recent saved words and difficult words

Assets:

- diary/logbook paper
- date stamps
- ledger rows
- word memo slips

Motion:

- detail disclosure unfolds like a ledger note
- recent word slips can stagger in lightly

## 7. Required Asset Plan

Use existing assets first, but do not force a bad fit. Images must anchor layout
instead of decorating unchanged UI.

Existing asset families:

- Shiori WebP variants in `frontend/public/brand/shiori/`
- Home notebook and sticky notes in `frontend/public/brand/decor/phase145/`
- open-book and paper textures in `frontend/public/brand/decor/phase126/`
- shelf, index, board, and crop assets in `frontend/public/brand/decor/`
- V2 generated scene bases in `frontend/public/brand/decor/v2/`

Potential new assets:

- wider index-tab set with larger label-safe area
- simpler book-spine texture set for shared decks
- classify card-making desk kit: blank cards, stamp pad, card bundle
- logbook paper with clear ledger line system
- shell/nav paper strip, if the toolbar remains visually heavy

The V2 ratio-specific mockups suggest the most useful future assets:

- Home: a cleaner notebook composite with label-safe title area and shortcut
  tabs physically tucked into the cover edge.
- Reading: a clearer input slip layer that contrasts with the open-book page.
- Vocab: broad tab assets with text-safe gutters and no decorative collisions.
- Study: felt-board objects that keep memo tiles and flashcards on one surface.
- Shared Deck: real book-spine set with subtle thickness and shelf shadows.
- Classify: source slip, blank card tray, stamp pad, and finished bundle.
- Stats: logbook/ledger paper and reusable memo slips.

Generation rules:

- no baked UI text
- transparent or easy-to-crop backgrounds when used as objects
- no new characters, people, animals, or faces
- Shiori appears only through existing Shiori components
- test assets as small single-screen pilots before applying everywhere

Phase 163 generated a first implementation asset kit from the ratio-specific
mockups. It contains separate desktop 16:9 and mobile 9:16 scene bases for all
seven tabs. Runtime WebP files live in `frontend/public/brand/decor/v2/`, with
source PNG masters preserved under `docs/design/source-assets/v2-generated-png/`.
Treat these files as material anchors for new V2 scene components, not as
wallpaper for old layouts. If a candidate implementation keeps the old tab
skeleton visible, the asset has been misused.

## 8. Motion Rules

Motion should feel like stationery being touched.

Allowed:

- lift, tuck, slide, press, stamp, unfold
- 1-3 degree rotations
- 100-220ms tactile responses
- reduced-motion-safe alternatives

Avoid:

- large bounce
- glowing gradients
- full-screen theatrical transitions
- motion that delays reading or review decisions

## 9. Deprecated Documentation And Patterns

These documents remain useful history, but should not be treated as current
implementation targets when they conflict with this V2 bible:

- `docs/design/casual-sticker-reader-redesign-brief.md`: Phase 54 direction.
  Keep its product truth and Shiori rules, but its "polish current screens"
  implementation order is superseded.
- `docs/design/phase145-casual-cute-tab-rebuild-plan.md`: useful asset and
  symptom record. Superseded because it still assumed patching existing tab
  structures in place.
- `docs/design/v4-reader-first-redesign-proposal.md`: useful IA thinking.
  Superseded for visual implementation because it preserves too much of the old
  card/surface system.
- `docs/design/ui-guidelines.md`: useful for legacy component behavior and
  copy/safety rules. Its old advice to reuse `panel-card`/`hero-card` is not a
  V2 requirement for scene reconstruction.
- `docs/design/DESIGN.md`: durable phase history. Use it to understand why
  decisions were made, not as proof that a current screen is visually finished.

Deprecated patterns:

- `panel-card`/`hero-card` as the default answer to every layout problem
- generic metric chips for primary screen numbers
- separate right widget panels
- filter panels that look like settings forms
- card grids posing as shelves/notebooks
- toolbar or banner rows stacked above scene objects
- image texture placed behind unchanged cards
- full-width mobile admin buttons except for one intentional primary action

## 10. Implementation Strategy

Use V2 scene components when needed:

- `HomeSceneV2`
- `ReadingSceneV2`
- `VocabNotebookV2`
- `StudyBoardV2`
- `SharedBookshelfV2`
- `ClassifyDeskV2`
- `StatsLogbookV2`

These names are suggestions, not mandatory file names. The important point:
do not keep the old DOM just because it exists. Reuse logic, handlers, and data
shape; replace visual structure.

Recommended order:

1. Phase 162: this V2 bible and documentation reset.
2. Phase 163: V2 implementation asset kit: desktop 16:9 and mobile 9:16 scene
   bases for all tabs.
3. Phase 164: Classify V2 or Vocab V2 pilot, whichever looks weakest in fresh
   screenshots.
4. Phase 165: second weakest tab.
5. Continue tab-by-tab, with each phase replacing one old silhouette rather
   than polishing several surfaces.
6. Final phase: App Shell scene support, once tabs have stable V2 silhouettes.

## 11. QA And Reporting

Every implementation phase must report:

1. What old structure was removed
2. New scene silhouette
3. How existing functionality was reattached
4. Desktop and mobile visual judgment
5. Failure criteria pass/fail
6. Functional/build/browser QA
7. Remaining risks
8. Next scene-level candidate

Required checks:

- `npm run build`
- `git diff --check`
- real browser screenshots/inspection at 1280, 1024, 390, 375, 320
- `scrollWidth === clientWidth`
- zero console errors/warnings
- no unexpected failed requests or image 404s
- representative real flow for the target tab

Design acceptance question:

> If the screenshot were shown without context, would it read first as a
> physical stationery scene or as a web app panel with cute materials?

Only the first answer is acceptable for V2.
