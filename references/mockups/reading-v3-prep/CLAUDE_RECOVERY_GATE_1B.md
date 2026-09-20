# Reading V3 Recovery Gate 1B - Responsive Desktop Scene Integration

Project: `C:\JV_Project\jp_vocab_reader`

Read only:

1. `references/mockups/reading-v3-prep/READING_V3_EXECUTION_PLAN.md`
2. `references/mockups/reading-v3-prep/DESIGN_SPEC.md`
3. `references/mockups/reading-v3-prep/GATE1A_TALL_SCENE.md`
4. `references/mockups/reading-v3-prep/reading-v3-scene-approved-desktop.png`
5. `references/mockups/reading-v3-prep/reading-v3-scene-approved-tall-desktop.png`
6. `frontend/components/ReadingTab.tsx`
7. the Reading scene/page geometry and Reading-only shell rules in `frontend/app/globals.css`

## Confirmed State

Gate 1 removed the Reading-only `1640px` canvas cap and parent `1680px` shell cap. This fixed the horizontal strips at `1920x960`, but the single panoramic `1849x851` scene left a large non-photographic area below the image at `1280x900` and `1024x768`. Gate 1A therefore approved a separate `1536x1024` tall-desktop scene.

## Goal

Connect both approved desktop scenes so the Reading tab fills the available area with one coherent photograph at wide and tall desktop aspect ratios. Remeasure page safe zones independently for each image. This gate is still scene geometry only.

## Required Source Selection

Use this source priority:

1. Wide desktop: `min-width:1500px` and `min-aspect-ratio:16/9` -> approved `1849x851` scene.
2. Tall desktop: `min-width:1024px` -> approved `1536x1024` scene.
3. Mobile/tablet below `1024px` -> existing V2 mobile scene unchanged.

The wide condition must appear before the tall fallback in `<picture>` source order. Mirror the same conditions in CSS so each scene uses its own geometry variables and safe-zone coordinates.

## Required Work

1. Copy `reading-v3-scene-approved-tall-desktop.png` into the existing versioned `frontend/public/brand/decor/v3/` folder without re-encoding it.
2. Verify the copied SHA-256 is exactly `498DB4CBAC0DCE7ED209164BC40B7208A7560D9E3BFD58FC393F845333678068`.
3. Add the aspect-aware `<picture>` source selection above.
4. Make the Reading scene frame occupy the available desktop height beneath the 50px toolbar.
5. Use centered `object-fit:cover` only within the selected scene. Crop may consume desk margin but may not touch the notebook.
6. Remeasure left-page and right-page safe zones separately for wide and tall scenes. Do not reuse V2 numbers or copy wide percentages into tall rules.
7. Preserve the current Gate B input/reader presentation without modifying its typography, controls, copy, behavior, or component structure.

## Forbidden Changes

- Do not modify `ReadingSourceSlip.tsx`, `ReaderMode.tsx`, `ReadingVocabPanel.tsx`, callbacks, API, auth, SRS, storage, or other tabs.
- Do not regenerate, resize, crop on disk, filter, or re-encode either approved scene.
- Do not use CSS background duplication, gradients, blur, solid fill, or pseudo-elements to complete the viewport.
- Do not begin Gate 2 or claim input/analyzed parity.
- Do not commit, push, merge, or delete QA evidence.

## Required Browser QA

Capture and retain full screenshots at:

- `1920x960` - must select wide scene.
- `1600x900` - must select wide scene.
- `1440x900` - must select tall scene.
- `1280x900` - must select tall scene.
- `1024x768` - must select tall scene.
- `390x844` - must select existing mobile scene.

For every viewport report:

- `currentSrc` filename.
- viewport, shell, canvas, frame, and image rectangles.
- scene top/bottom gap.
- `scrollWidth` and `clientWidth`.
- whether any crop intersects the notebook bounding box.

Create one labeled contact sheet containing the five desktop screenshots at a consistent scale. Keep individual screenshots, contact sheet, and JSON measurements under `references/mockups/reading-v3-prep/gate1b-qa/`.

Smoke the other six tabs for open/overflow only. Run `git diff --check`; do not run the full build in this gate.

## Acceptance

- No unrelated side or bottom strip at any required desktop viewport.
- One coherent photograph fills the scene area.
- Complete notebook remains visible at every desktop viewport.
- No stretching, visible image switch seam, or horizontal overflow.
- Live content remains inside both photographed pages after independent coordinate measurement.
- Mobile and other tabs remain unchanged.

Allow one correction pass. If a viewport cannot satisfy both full-scene fill and complete-notebook visibility, stop and report the exact conflict rather than adding a CSS patch.
