# Home V10.8 Lower-Edge Structure Recovery - Gate A

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-v10-8-edge-structure-prep`

Target: desktop Home scene asset only.

This is an asset-first structural reconstruction. Produce three lower-edge
structure candidates and comparison previews, then stop for human selection.
Do not wire a candidate, edit production code, commit, push, or merge.

## Current failure in three lines

1. V10.6 had a near-black lower rim and corner wedges that read as a drawn
   outline rather than leather depth.
2. V10.7 used a color-threshold/lightness recovery over the same incorrect
   geometry, turning the black outline into a thicker green rubber-like border.
3. The correct fix is to rebuild the physical lower-edge layers, not recolor
   the existing band and not add CSS shadow.

Phase goal: reconstruct a thin front-cover bevel, dominant cream page block,
and tapered corner-only rear-cover returns while preserving the approved full
scene and cast shadow.

New physical silhouette: green front cover -> thin irregular textile bevel ->
dominant cream pages -> minimal rear cover in the center -> tapered leather
returns at both corners -> unchanged desk shadow.

Old structure to remove: the continuous black/green terminal band and the
constant-width rounded corner outline. The V10.7 per-pixel color-threshold mask
is superseded and must not be reused.

## Read first

1. `references/mockups/home-v10.8-prep/DESIGN_PLAN.md`
2. `frontend/public/brand/decor/home-v10.4/ASSET_MANIFEST.md`
3. `frontend/public/brand/decor/home-v10.7/ASSET_MANIFEST.md`
4. `references/mockups/home-v10.7-prep/home-v10.7-rim-contact-sheet.png`
5. Current failure screenshot:
   `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 200357.png`

Do not read components, CSS, backend, API, auth, SRS, or storage code in Gate A.
This task changes no application behavior.

## Source of truth

Edit only from:

`frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png`

- Dimensions: `1888x833`
- Mode: opaque RGB PNG
- Required SHA-256:
  `150F585937AF99163C8C671FCE10600E63D540FE899D5E7A13915E3230CBE131`

Why V10.4: it is the byte-preserved 1888x833 approved scene before the V10.6
and V10.7 lower-rim experiments. Starting from V10.7 would compound their
incorrect geometry. Do not edit or overwrite V10.4, V10.6, or V10.7.

Verified historical decoded-pixel comparisons at threshold `>2/255`:

- V10.6 vs V10.4: 11,732 pixels, 0.746%, bbox `x=528..1420, y=622..677`
- V10.7 vs V10.6: 18,321 pixels, 1.1649%, bbox `x=538..1412, y=575..685`
- V10.7 vs V10.4: 23,582 pixels, 1.4995%, bbox `x=528..1420, y=575..685`

Recompute and confirm these values before creating candidates. If they do not
match, stop and report the mismatch.

## Mandatory reconstruction method

Do not use ImageGen and do not apply a global grade. Use deterministic raster
compositing with hand-inspected, layer-specific masks.

### 1. Work crop and safety envelope

- Inspect at 4x and 8x nearest-neighbor scale.
- Primary work crop: `x=500..1445, y=550..710`.
- Every changed pixel must remain inside that crop.
- The crop is a safety envelope, not a rectangular edit mask.

### 2. Build separate semantic masks

Trace these independently by physical role, not by RGB threshold:

- `front-cover-bevel-mask`
- `left-corner-return-mask`
- `right-corner-return-mask`
- `rear-cover-center-mask`
- `page-extension-mask`
- `protected-page-mask`
- `protected-desk-shadow-mask`

A single rule such as `G >= R - 6` is forbidden. Thresholds may assist
inspection but may not define the final mask without manual geometric review.

### 3. Preserve material texture

- Source textile grain from nearby unaffected green cover areas in V10.4.
- Align copied texture with the cover's existing perspective and grain
  direction.
- Where a former black terminal band must become visible page thickness, source
  paper color and grain from the adjacent V10.4 page block and use only the
  dedicated `page-extension-mask`. Existing page pixels remain protected and
  unchanged.
- Preserve local high-frequency variation; no flat fills.
- Blend boundaries inward on the leather surface only. Do not blur the outer
  silhouette into the desk or the leather into the page block.

### 4. Rebuild the physical stack

- Front-cover bevel: thin, irregular, and darker than the cover field; visual
  thickness no more than roughly 25-30% of the local cream page-block height.
- Existing cream page-block pixels: decoded pixels remain identical to V10.4;
  the page block may extend only into pixels assigned to `page-extension-mask`.
- Rear cover through center: absent or extremely narrow; never a continuous
  high-contrast stripe.
- Corner returns: may be thicker than the center but must taper gradually over
  the final 8-10% of each book side.
- Left and right corners must be shaped independently. Mirroring one corner is
  forbidden.
- Desk contact/cast shadow: decoded pixels remain identical to V10.4.

### 5. Tone and edge behavior

- Leather stays deep forest/olive green and subordinate to the cover field.
- Avoid literal RGB black except for tiny natural occlusion points.
- Do not replace the black band with a constant green band.
- No connected near-black (`luminance < 12`) horizontal run longer than 80px
  may remain inside the reconstructed leather masks.
- No constant-color or constant-thickness segment longer than 120px.
- No halo, hard mask contour, airbrushed blur, or rubber/plastic highlight.

## Required structural candidates

Each candidate must be generated independently from untouched V10.4, never
from another candidate.

### Candidate A - Thin Leather Lip

- Narrow front-cover bevel across the width.
- Rear cover barely visible in center, moderately visible at corners.
- Most conservative geometry change.

### Candidate B - Page-Forward Taper

- Thinnest front bevel through the center.
- Rear cover disappears through most of the center.
- Both corner returns taper in gradually and independently.
- This is the recommended target direction, not an automatic selection.

### Candidate C - Heritage Bound Edge

- Slightly fuller leather depth and more visible textile grain than B.
- Still page-dominant and free of continuous dark/green outlining.
- Upper acceptable weight bound; must not look molded or rubberized.

## Output paths

Create:

- `frontend/public/brand/decor/home-v10.8/home-v10.8-scene-desktop-a.png`
- `frontend/public/brand/decor/home-v10.8/home-v10.8-scene-desktop-b.png`
- `frontend/public/brand/decor/home-v10.8/home-v10.8-scene-desktop-c.png`
- `frontend/public/brand/decor/home-v10.8/ASSET_MANIFEST.md`
- `references/mockups/home-v10.8-prep/home-v10.8-edge-contact-sheet.png`
- `references/mockups/home-v10.8-prep/home-v10.8-preview-1920.png`
- `references/mockups/home-v10.8-prep/home-v10.8-preview-1280.png`

Do not place contact sheets or previews in `frontend/public`.

## Comparison-sheet contract

Show rows in this order:

1. V10.4 source
2. V10.7 current production failure
3. Candidate A
4. Candidate B
5. Candidate C

For every row include:

- full scene at identical scale,
- 100% lower-edge crop,
- 4x left corner,
- 4x center edge,
- 4x right corner,
- a high-contrast difference heatmap against V10.4.

The 1920 and 1280 previews must reproduce the current desktop
`object-fit: cover` / centered scene calculation without changing code. Show
A/B/C side by side at realistic browser scale. Do not judge only enlarged
crops; unchanged full-scene first impression is the primary verdict.

## Pixel-integrity contract

- Candidate dimensions and mode: exactly 1888x833 opaque RGB.
- All pixels outside `x=500..1445, y=550..710` must equal V10.4 exactly.
- Protected page, tabs, tape, desk, and cast-shadow masks must equal V10.4
  exactly even inside the work crop.
- Note, CTA, Shiori, bookmark, emboss, props, cover field, composition, and
  crop must have zero changed pixels.
- Exterior silhouette geometry remains unchanged. Edge color may change only
  where the pixel is manually identified as leather; do not move the outline.
- Report changed-pixel count/bbox, protected-pixel count, near-black connected
  run length, and texture variance for every candidate.

## Absolute prohibitions

- No V10.7 color-threshold mask reuse.
- No `RGB * factor`, global curves, global hue shift, blanket lightness floor,
  or rectangular feather as the primary correction.
- No CSS shadow/filter/gradient/mask/border/pseudo-element or extra overlay.
- No HomeDashboard, globals.css, AppShell, nav, mobile, or behavior changes.
- No generative redraw, whole-scene reconstruction, resize, crop, sharpening,
  denoising, or recompression drift outside the work crop.
- No modification or deletion of V10.4, V10.6, or V10.7.
- No frontend/backend server and no Neon access.
- No commit, push, merge, branch switch, or branch creation.

## Gate A validation

1. Record `git status --short` before work.
2. Verify source hashes/dimensions and historical pixel comparisons.
3. Produce the seven semantic masks and save mask previews in the contact sheet,
   not as production assets.
4. Generate A/B/C independently from V10.4.
5. Validate pixel containment and all protected surfaces.
6. Inspect full-scene previews first, then 100% and 4x crops.
7. One technical correction pass is allowed only for mask leakage, halo, or
   broken preservation. Do not use it to iterate aesthetic directions.
8. Run `git diff --check`; do not run the app or build.
9. Return the report and stop for human selection.

## Failure criteria

Fail Gate A if any of these occurs:

- A black outline is merely recolored green or brown.
- The center retains a continuous terminal band.
- Either corner forms a constant-width tube, black wedge, or mirrored shape.
- Page pixels, tabs, tape, desk, or cast shadow change.
- Leather becomes flat, airbrushed, orange, gray, shiny, or plastic-like.
- Full-scene first impression is indistinguishable from V10.7.
- Any production code or mobile file changes.
- More than one technical correction pass is used.

## Required concise report

1. Superseded V10.7 failure mechanism
2. V10.4 source/hash and historical-diff verification
3. Seven semantic-mask construction method
4. Candidate A/B/C physical-layer description
5. Full-scene 1920/1280 verdict
6. Left/center/right 4x verdict
7. Pixel containment/protected-surface metrics
8. Near-black run and texture-variance metrics
9. Recommended candidate and contact-sheet paths
10. Remaining risk

End with `Gate A complete - awaiting structural candidate selection.` Do not
wire, commit, or push.
