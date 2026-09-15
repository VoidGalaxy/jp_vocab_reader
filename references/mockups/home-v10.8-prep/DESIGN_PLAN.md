# Home V10.8 Lower-Edge Structure Recovery Plan

## Decision

V10.7 is visually superseded for the notebook lower edge. It solved crushed
black values numerically but changed the defect from a black outline into a
thick green outline. Do not continue editing V10.7.

Use the unchanged V10.4 scene as the reconstruction source and rebuild the
lower edge once from its physical layers.

## Why V10.7 failed

1. A color-threshold mask treated every dark green/neutral pixel as the same
   leather material; it did not distinguish front-cover lip, page block,
   back-cover return, corner fold, and cast shadow.
2. The recovered tone was applied across an already incorrect continuous band,
   preserving its geometry and making the band more visible.
3. Both corners received similar thickness and color, creating a molded rubber
   outline instead of tapered leather over a page block.

## Target physical stack

From top to bottom:

1. Forest-green front cover with a thin, irregular textile-wrapped bevel.
2. Dominant cream page block with unchanged warm shading.
3. A very narrow rear-cover return in the center, visible mainly as depth.
4. Slightly fuller but tapered leather returns at the left and right corners.
5. Existing warm desk contact/cast shadow, unchanged.

The center must not contain a continuous black or green marker line. The page
block should carry most of the visible thickness. Corners may remain darker
than the center but must taper into it instead of forming a constant-width
border.

## Candidate directions

### A - Thin Leather Lip

- Keep a narrow front-cover bevel across the width.
- Rear cover is barely visible in the center and slightly fuller at corners.
- Conservative silhouette; strongest page-block emphasis.

### B - Page-Forward Taper (recommended target)

- Front bevel is thinnest through the center and gains depth gradually within
  the final 8-10% of each side.
- Rear cover disappears through most of the center and returns only near the
  rounded corners.
- Best chance of removing the drawn-outline reading while retaining weight.

### C - Heritage Bound Edge

- Slightly more leather depth than B, with visible textile grain and uneven
  handmade edge variation.
- Still forbids a continuous dark band and must remain subordinate to pages.
- Upper acceptable material-weight bound.

## Non-negotiable preservation

- Scene dimensions and composition remain 1888x833.
- Desk, props, note, CTA, Shiori, bookmark, emboss, colored tabs, tape, cover
  field, cream page block, and broad cast shadow remain pixel-identical.
- Only the lower leather structures and their boundary transition may change.
- No CSS or DOM work during candidate creation.
- Mobile remains V10.5 and is outside this phase.

## Staged workflow

1. Gate A: create structural A/B/C candidates from V10.4 and a comparison
   sheet. No production wiring.
2. Human selection: judge full-scene first impression, then 100%/4x crops.
3. Gate B: rename the selected candidate, remove rejects, wire one desktop URL.
4. Final QA: 1920/1280 first, then 1024 and mobile source-preservation checks.
5. Commit, merge, and branch cleanup only after explicit approval.

## Gate A approval questions

- Does the page block visually dominate the book thickness?
- Is the front-cover lip thin and textile-like rather than a drawn stroke?
- Do both corners taper naturally without black wedges or green tubing?
- Is the center free of a continuous near-black or green line?
- Does the unchanged desk shadow still ground the notebook?
