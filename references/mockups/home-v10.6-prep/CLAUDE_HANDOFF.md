# Home V10.6 Grounding Finish - Final Candidate Validation

Project: `C:\JV_Project\jp_vocab_reader`

Target: Home desktop scene only. The working branch already contains a Codex
implementation. Audit it first; do not replace it with a new interpretation.

## Current failure in three lines

1. The desktop scene previously subtracted the nav asset canvas height (64px)
   instead of the toolbar's real layout height (50px), leaving a bottom strip.
2. Desktop shortcut content used asymmetric padding that placed its live text
   visibly too low inside the three baked paper tabs.
3. V10.4's lower notebook rim contained near-black terminal pixels that read as
   a drawn border rather than warm leather/contact occlusion.

Phase goal: validate that the prepared V10.6 candidate fixes all three defects
without changing the approved scene composition, interaction coordinates, or
mobile design.

Physical scene silhouette: one precomposited warm desk photograph containing
the centered forest-green notebook, note, CTA ribbon, Shiori, props, three tabs,
and all physical shadows under one light source. Live text remains DOM overlay.

Role redefinition: the desktop Home scene now fills the viewport below the real
50px toolbar; the 64px nav paper asset is only a visual overlap and must never be
used as the Home scene's layout-height subtraction.

## Read first, and nothing broader unless a failure is reproduced

1. `frontend/components/HomeDashboard.tsx`
2. The `.home-v10-scene` and `.home-v10-tab-content` blocks in
   `frontend/app/globals.css`
3. `frontend/public/brand/decor/home-v10.6/ASSET_MANIFEST.md`
4. Current reference screenshot:
   `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 180025.png`

Do not perform broad repository archaeology. Do not inspect backend, page data,
SRS, auth, or storage code unless a functional regression is actually
reproduced.

## Prepared implementation that must be present

### Desktop fill geometry

In the desktop `@media (min-width: 768px)` Home block:

```css
--scene-height: calc(100svh - 50px);
--scene-art-ratio: 1888 / 833;
--scene-art-width: max(100vw, calc(226.65svh - 113.33px));
```

The width formula is the exact 1888/833 conversion of `100svh - 50px`. Do not
restore the old `-64px` / `-145.06px` pair and do not solve the gap with negative
margin, fixed positioning, pseudo-elements, or an extra background layer.

### Shortcut text position

The desktop `.home-v10-tab-content` padding must be:

```css
padding: 18% 8% 14% 10%;
```

This moves the content approximately 4-6px upward while preserving the tab hit
zones, icon size, label/hint typography, baked tape, and torn-paper boundaries.

### Desktop asset mapping

`HomeDashboard.tsx` must load:

```text
/brand/decor/home-v10.6/home-v10.6-scene-desktop.png
```

for `min-width: 768px`, while mobile must continue loading:

```text
/brand/decor/home-v10.5/home-v10.5-scene-mobile.png
```

## V10.6 asset integrity contract

Final desktop asset:

- Path: `frontend/public/brand/decor/home-v10.6/home-v10.6-scene-desktop.png`
- Dimensions: 1888x833, RGB PNG
- SHA-256: `3F606A0C500AC9033455381DAA8BD09607CA0E8B542F241A7677B654B49623A0`

Compare against:

- `frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png`
- V10.4 SHA-256:
  `150F585937AF99163C8C671FCE10600E63D540FE899D5E7A13915E3230CBE131`

Expected pixel result at max-channel threshold `>2/255`:

- changed pixels: 11,732
- changed fraction: approximately 0.746%
- changed bounding box: `x=528..1420`, `y=622..677`

Every pixel outside this bounding box must match V10.4. The V10.6 image already
contains the approved bounded rim correction. Do not regenerate, globally grade,
blur, sharpen, resize, crop, or overwrite it. If the hash or pixel bounds do not
match, stop and report the discrepancy instead of creating another asset.

## Absolute prohibitions

- No CSS box-shadow, drop-shadow, filter, gradient, mask, border overlay, dark
  bar, pseudo-element, or extra shadow image.
- No new ImageGen run and no global image reconstruction.
- No changes to scene ratio, overlay coordinates, note/CTA/tab hit zones,
  Shiori, props, title text, CTA text, shortcut copy, or typography.
- No JSX restructuring and no callback, routing, API, auth, SRS, storage, or
  accessibility changes.
- No AppShell or Home Nav V1.2 edits.
- No mobile asset, coordinate, crop, or layout edits.
- Never start the backend and never access Neon or production data.
- Do not discard or rewrite existing working-tree changes.

## Validation sequence

This is a final-candidate audit, not an exploration phase.

1. Record `git status --short` and inspect the existing diff.
2. Verify both image hashes, dimensions, pixel count, and changed bounding box.
3. Start only the frontend dev server.
4. Capture and inspect Home at 1920x960 and 1280x960.
5. If and only if a listed acceptance criterion fails, make at most one bounded
   correction inside the allowed files. Do not reinterpret the design.
6. Confirm desktop at 1024x768 and mobile at 390x844, 375x812, and 320x700.
7. Verify representative Home clicks without starting the backend.
8. Stop the dev server and browser before running `npm run build` once.
9. Run `git diff --check` and confirm ports 3000/8000/9222 are closed.
10. Do not commit or push. Stop for approval.

## Acceptance criteria

### Desktop 1920/1280/1024

- Toolbar layout box remains exactly 50px high.
- `.home-v10-scene` starts at y=50 and ends at the viewport bottom.
- `viewportHeight - scene.bottom` equals 0.
- Art-plane top and bottom differ from the scene by no more than 0.02px.
- `scrollWidth === clientWidth`.
- There is no solid strip, exposed body background, seam, or letterbox at the
  bottom edge.
- Shortcut text sits visibly higher than V10.4/V10.5 behavior but stays clear of
  tape, torn edges, neighboring tabs, and tab shadows.
- The lower notebook rim remains dark enough to ground the book, but its lower
  corners and terminal edge read as deep warm olive leather rather than a flat
  pure-black outline.
- The broad desk cast shadow remains present; the notebook must not float.
- No scene object moves and no overlay text leaves its safe zone.

### Mobile 390/375/320

- `currentSrc` remains the V10.5 mobile scene.
- Mobile visible shortcut treatment remains icon-only.
- `scrollWidth === clientWidth`.
- Do not classify any pre-existing mobile bottom spacing as part of this phase;
  this task changes desktop geometry only.

### Requests and behavior

- V10.6 desktop and V10.5 mobile image requests return 200/304 with no 404.
- Sample and CTA still open Reading.
- Vocab and Deck shortcuts still open their existing sections.
- Review still follows the existing account/review branch for the current user.
- No new console warning/error beyond expected frontend-only API fetch failures.

## Failure criteria

Fail and stop if any of the following occurs:

- The V10.6 hash or bounded pixel-diff contract changes.
- Any fix uses a CSS shadow, overlay, mask, gradient, or global image edit.
- Bottom gap remains visible at any desktop target width.
- Tab content touches tape or torn edges after moving upward.
- Book grounding becomes weaker or the cast shadow disappears.
- Mobile source or visual composition changes.
- Any unrelated file or behavior changes.
- More than one correction pass is attempted.

## Required report

Keep the report concise:

1. Existing failure mechanics confirmed
2. V10.6 hash/dimension/pixel-bound verification
3. Desktop fill geometry result at 1920/1280/1024
4. Shortcut vertical-position judgment
5. Notebook rim/grounding visual judgment
6. Mobile unchanged proof at 390/375/320
7. Home click preservation
8. Build/diff/404/console/process-cleanup result
9. Any correction made, or `no correction required`
10. Remaining risk

Do not commit or push. Return the report and wait for approval.
