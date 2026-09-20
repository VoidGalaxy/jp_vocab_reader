# Reading V3 Recovery Gate 1 - Viewport And Scene Geometry

Project: `C:\JV_Project\jp_vocab_reader`

Read only:

1. `references/mockups/reading-v3-prep/READING_V3_EXECUTION_PLAN.md`
2. `references/mockups/reading-v3-prep/DESIGN_SPEC.md`
3. `references/mockups/reading-v3-prep/reading-v3-scene-approved-desktop.png`
4. `frontend/components/ReadingTab.tsx`
5. the Reading scene, `.library-canvas-reading`, `.app-shell-content`, and `.page` rules in `frontend/app/globals.css`

## Confirmed Failure

The approved `1849x851` scene is connected correctly, but the Reading canvas still uses `width: min(1640px, 100%)` and desktop `.app-shell-content` still caps at `1680px`. The original wide-screen side-strip defect therefore remains at `1920px`, even though it is hidden at the reported `1280px` QA width.

## Goal

Make the approved Reading scene occupy the intended desktop viewport surface at `1920`, `1280`, and `1024` without unrelated side strips, stretching, book enlargement, or accidental crop. This gate is geometry only.

## Allowed Changes

- Reading-only width/max-width/padding rules from viewport to `.library-canvas-reading`.
- `.reading-scene-v2-frame` and image sizing only if required to preserve the approved asset ratio.
- Reading page safe-zone coordinates only if a real screenshot proves they moved outside the photographed paper after the shell correction.

## Forbidden Changes

- Do not alter `ReadingSourceSlip.tsx`, `ReaderMode.tsx`, `ReadingVocabPanel.tsx`, callbacks, copy, input styling, analyzed styling, mobile scene, backend, API, auth, SRS, storage, or other tabs.
- Do not regenerate, crop, stretch, filter, or re-encode `v3-reading-open-book-desktop.png`.
- Do not fix the gap with a body background color, gradient, duplicated image, pseudo-element, or blurred extension.
- Do not commit, push, merge, or delete QA evidence.

## Required Procedure

1. Before editing, report the measured rectangles at `1920x960`: viewport, `.app-shell-content`, `.library-canvas-reading`, `.reading-scene-v2-frame`, and `.reading-scene-v2-media-img`.
2. Explain in no more than three lines which two width constraints cause the defect.
3. Apply the smallest Reading-scoped structural fix. Shared toolbar geometry and other tabs must remain unchanged.
4. Capture full screenshots at `1920x960`, `1280x900`, and `1024x768`.
5. Produce one labeled contact sheet showing all three.
6. Report the same rectangles after the fix and `scrollWidth === clientWidth` at every width.
7. Open the six other tabs once and check only overflow and obvious shared-shell breakage.
8. Run `git diff --check`. Do not run the full build in this gate; it already passed and will run once at final candidate.

## Acceptance

- At `1920x960`, no unrelated striped/body background is visible beside the Reading scene.
- The scene uses the approved native ratio and the book is neither stretched nor enlarged to conceal a strip.
- No horizontal scrollbar.
- `1280` and `1024` retain usable complete book/page framing.
- Other tabs and the toolbar retain their previous width behavior.
- Screenshot files and the contact sheet remain on disk at the paths stated in the report.

If any acceptance item fails after one correction pass, stop and report the exact geometry conflict. Do not continue into input or analyzed-state work.
