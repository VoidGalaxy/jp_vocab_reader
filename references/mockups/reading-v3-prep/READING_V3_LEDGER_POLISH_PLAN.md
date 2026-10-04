# Reading V3 Analyzed Workspace Polish Plan

> Historical V3 plan. The current Reading tab has since moved to the V4 C folio;
> use `frontend/components/ReadingTab.tsx` and the active scene assets for
> current behavior and layout. The authorities below apply to this V3 phase.

## Authority

- Analyzed-state visual authority: `reading-v3-analyzed-reference.png`.
- Input-state continuity authority: `reading-v3-input-approved.png`.
- Latest user-observed production state: `C:/Users/mjwmm/Pictures/Screenshots/스크린샷 2026-09-20 184638.png`.
- Desktop scene assets, crop rules, page safe zones, callbacks, storage, API, auth, SRS, and mobile behavior remain unchanged.

## Current Diagnosis

The physical-book silhouette is approved and must not be rebuilt. The remaining gap is inside the live page content:

1. The desktop type scale is too small for the 1920 composition (`reader 16px`, `headword 30px`, most controls and metadata `11-14px`).
2. The right-page hierarchy is compressed into a shallow block: headword, meaning, metadata, example, and status have insufficient contrast in scale and spacing.
3. The four status controls read as generic filled pills instead of printed classification marks.
4. Footer actions also read as web chips, while the approved mockup uses a quiet icon-and-text tool row.
5. The progress ribbon is undersized, and the pink candidate tab is anchored to the viewport edge rather than the photographed book edge.

## Spatial Thesis

- Primary: Japanese source text on the left page.
- Secondary: active headword and Korean meaning on the right page.
- Supporting: status, metadata, and example.
- Utility: fixed page-foot tools and selection count.
- Auxiliary: the pink candidate tab and tray.

The page must read as one printed manuscript spread, not a collection of cards or controls.

## Scope

Allowed production files:

- `frontend/app/globals.css`
- `frontend/components/TokenDetailSheet.tsx`
- `frontend/components/ReaderMode.tsx`
- `frontend/components/ReadingVocabPanel.tsx` only if candidate-tab anchoring requires a role/class adjustment

No backend, API, schema, storage key, auth, SRS, routing, scene asset, Home, toolbar, or mobile redesign changes.

## Desktop Type Targets

Use fixed breakpoint roles, never viewport-scaled font sizes.

| Role | Current | 1024-1439 target | 1440+ target |
| --- | ---: | ---: | ---: |
| Japanese reader | 16/1.9 | 17/2.0 | 18/2.0 |
| Ledger headword | 30/1.2 | 36/1.18 | 42/1.15 |
| Reading | 14 | 15 | 16 |
| Part of speech | 11 | 12 | 12 |
| Primary meaning | 16 | 18 | 20 |
| Example | 14/1.7 | 15.5/1.8 | 16/1.8 |
| Section labels | 11.5 | 12.5 | 13 |
| Metadata/hints | 11-12 | 12 | 12.5 |
| Footer tools | 11.5-12 | 12.5 | 13 |

Keep Japanese in the existing Mincho stack and Korean UI in the existing sans stack. Do not add a font asset.

## Gate A - Right-Page Hierarchy

Reorder the desktop ledger to:

1. selected-word header and navigation;
2. headword, reading, and part of speech;
3. primary meaning;
4. status classification;
5. base form, occurrence count, and JLPT reference;
6. example;
7. optional hint only when relevant.

Add restrained `뜻` and `예문` labels. Use approximately `20-24px` between major groups and `6-10px` inside a group. Never fabricate nuance, meanings, or examples to fill space.

Replace desktop status pills with one transparent four-column printed selector:

- small circular marker before each label;
- outline marker for inactive states;
- filled marker plus stronger label for the active state;
- quiet vertical separators between items;
- `36-40px` stable row height;
- no filled pastel capsules.

Navigation controls use a `30-32px` hit area. Close uses a `32px` hit area. The visual glyph remains smaller than the target.

Stop after 1920 and 1280 screenshots. Do not continue when the headword is still visually similar in weight to the body, the status row still reads as pills, or the ledger occupies only a compressed strip at the page top.

## Gate B - Left-Page Reading

- Move input and analyzed text origins upward together by an initial `20-28px` target.
- Preserve exact input-to-analysis first-line continuity: x delta `<= 1px`, y delta `<= 1px`, same family, size, and line-height.
- Increase reader type according to the table above.
- Keep the sage editor rule but reduce its visual weight.
- Replace box-like selected-token treatment with a faint wash plus a clear underline.
- Lower JLPT superscript contrast so it does not interrupt Japanese reading rhythm.
- Only the internal reader region scrolls for long text.

Stop after short-text and long-text screenshots at 1920, 1280, and 1024.

## Gate C - Page-Foot Tools

- Convert basket/edit/report controls from bordered pills to borderless icon-and-text tools.
- Use thin separators or spacing, not separate capsules, to group actions.
- Keep the selected/saveable counts as one quiet accounting line.
- A save command may gain emphasis only when `selectedCount > 0`.
- Increase the progress ribbon from `52px` to an initial `64-68px` width and the percentage from `14px` to `18px`.
- Keep both page-foot rows fixed while their content regions scroll.

Stop if changing token data, selection count, save messages, or long labels moves either footer.

## Gate D - Candidate Tab and Tray

- Remove viewport-edge `right: 0` anchoring on desktop.
- Measure the photographed book's right edge independently in the wide and tall scene assets.
- Place the pink tab `8-12px` beyond that edge so it reads as inserted into the book.
- Anchor the open tray to the book/right-page geometry, not the viewport.
- Keep the tab closed during ordinary token selection.
- Do not modify the mobile candidate tab or tray.

## Required State Matrix

- no selected word;
- first, middle, and last selected word;
- previous/next enabled and disabled;
- each of the four statuses;
- long meaning, missing example, and missing JLPT;
- selected count 0 and 1+;
- short source and long source;
- options open/closed and re-edit open/closed;
- candidate tray open/closed.

## Visual Failure Criteria

- Headword and meaning remain too small at normal 1920 viewing distance.
- Status controls or footer actions still read as generic pills.
- A card, panel background, shadow box, or inserted sheet appears on either page.
- Input and analyzed first lines move relative to each other.
- Right-page content or footer overlaps, clips, or changes page geometry.
- Candidate tab remains attached to the viewport edge.
- Empty optional data leaves broken separators or unexplained gaps.
- Mobile changes visually or behaviorally.

## Final QA

1. Visual comparison at 1920x960, 1280x900, and 1024x768.
2. Mobile regression at 390x844, 375x812, and 320x720.
3. `scrollWidth === clientWidth` at every width.
4. Core token click, navigation, status, basket, meaning edit, report, options, re-edit, and tray interactions.
5. No unexpected console errors, warnings, failed image requests, or 404s.
6. One final `npm run build` and `git diff --check`.
7. One bundled visual correction pass only, followed by one confirmation pass.

## Approval Boundaries

Each gate stops after its screenshots and measurements. Do not commit, push, merge, delete branches, or continue into the next gate without explicit approval.
