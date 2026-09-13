# Home V10.7 Lower-Rim Material Recovery - Gate A Asset Candidates

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-v10-7-rim-tone-prep`

This is an asset-only Gate A. Do not wire a candidate into production, do not
edit CSS or JSX, and do not commit or push. Produce three same-size scene
candidates and one comparison sheet, report the evidence, and stop for human
selection.

## Current failure in three lines

1. The notebook's lower leather rim and both lower corners contain clusters of
   near-black pixels that merge into a continuous drawn outline.
2. The broad desk cast shadow is already correct; the defect is inside the
   notebook material, not missing CSS grounding.
3. A global grade, blur, or another generated scene would damage the approved
   desk, props, note, tabs, Shiori, texture, and composition.

## Target first impression

Keep the approved V10.6 scene completely unchanged except for the notebook's
lower leather rim and its two lower corner returns. Those leather surfaces
should read as deep warm green-brown material with visible tonal texture. They
must remain darker than the cream page block and the cover, but must no longer
collapse into a pure-black marker line. The existing desk cast shadow must stay
exactly as it is.

## Source of truth

Use only:

`frontend/public/brand/decor/home-v10.6/home-v10.6-scene-desktop.png`

- Dimensions: `1888x833`
- Mode: RGB PNG
- Required SHA-256:
  `3F606A0C500AC9033455381DAA8BD09607CA0E8B542F241A7677B654B49623A0`

Do not use V10.4 or any earlier scene as the editing source. Do not overwrite
V10.6.

Use this screenshot only to judge the reported visual problem, never as an
editing source:

`C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 180025.png`

## Confirmed diagnostic evidence

The values below were measured from the current V10.6 source with Rec.709
luminance. They are diagnostic rectangles, not permission to grade every pixel
inside a rectangle.

- Lower-rim ROI `x=520..1424, y=620..684`: p01=`0.00`, p05=`0.93`,
  p10=`3.43`, p25=`31.03`; `8,862` pixels have luminance below 20.
- Left lower-corner ROI `x=510..609, y=585..699`: `1,501` pixels below 20.
- Right lower-corner ROI `x=1350..1444, y=575..699`: `1,402` pixels below 20.

These counts include nearby scene pixels and therefore must not be used as a
threshold-only mask. Inspect a 4x or 8x crop and trace the leather/rim surfaces
semantically.

## Mandatory editing method

Use deterministic raster processing only. Do not invoke ImageGen or redraw the
scene.

1. Build a hand-inspected grayscale mask that follows only the notebook's dark
   lower leather rim and the left/right lower leather corner returns.
2. Limit the mask envelope to the union of:
   - lower rim: `x=520..1424, y=615..684`
   - left corner: `x=510..589, y=585..699`
   - right corner: `x=1350..1434, y=575..699`
3. The envelope is only a hard safety boundary. Within it, exclude the cream
   page block, colored tabs, beige tape, desk, cast shadow, and all empty gaps.
4. Feather the correction inward across the leather material by approximately
   6-12px. Do not blur the exterior silhouette and do not spread pixels into
   the desk.
5. Correct only the low-light material response. Preserve high-frequency grain
   and edge texture. Do not paint a flat color over the rim.
6. A naive multiplication such as `RGB * 1.10` is forbidden because black
   pixels remain black. Recover crushed pixels from the local leather
   neighborhood, then raise perceived lightness and bias the darkest material
   toward deep warm olive/green-brown.
7. The tonal transition must be monotonic and smooth: strongest recovery at
   the crushed terminal pixels, tapering to zero before unaffected cover/page
   pixels. No hard mask contour may remain at 4x inspection.

Suggested color family for the recovered darkest leather is approximately
`#292b1b` through `#3b3924`. This is a target family, not a solid fill. Preserve
the original green identity and local texture.

## Three required candidates

Create all three from the untouched V10.6 source. Each must remain exactly
`1888x833` RGB PNG.

### Candidate A - Conservative 10%

- Perceived lightness of the masked leather region: approximately +10% from
  its source baseline.
- Warm hue bias: subtle.
- Purpose: minimum change that breaks up the black-outline reading.

### Candidate B - Balanced 12.5%

- Perceived lightness: approximately +12.5%.
- Warm olive/green-brown bias: clearly visible in the lower rim, still darker
  than the page block.
- Purpose: recommended default balance between grounding and material detail.

### Candidate C - Maximum 15%

- Perceived lightness: no more than +15%.
- Warm hue bias: strongest of the three, without becoming brown/orange or
  creating a luminous halo.
- Purpose: upper acceptable bound.

Measure the lightness increase on the actual nonzero mask-weighted leather
pixels, not on the full rectangular envelope. Report the measurement method and
result for A/B/C.

## Output paths

Create:

- `frontend/public/brand/decor/home-v10.7/home-v10.7-scene-desktop-a.png`
- `frontend/public/brand/decor/home-v10.7/home-v10.7-scene-desktop-b.png`
- `frontend/public/brand/decor/home-v10.7/home-v10.7-scene-desktop-c.png`
- `frontend/public/brand/decor/home-v10.7/ASSET_MANIFEST.md`
- `references/mockups/home-v10.7-prep/home-v10.7-rim-contact-sheet.png`

The contact sheet must contain, in this order:

1. V10.6 current
2. Candidate A
3. Candidate B
4. Candidate C

For each version include:

- the full 1888x833 scene at identical scale,
- a 100% lower-rim crop,
- a 4x nearest-neighbor crop of the left corner, center rim, and right corner,
- clear labels outside the image area.

Do not place the contact sheet in `frontend/public`.

## Pixel-integrity contract

For each candidate compare decoded RGB pixels against V10.6.

- Every changed pixel must lie inside the union envelope defined above.
- Pixels outside the hand-inspected semantic leather mask must be identical,
  even when they lie inside the envelope.
- Scene dimensions, crop, and object coordinates must not change.
- Desk, broad cast shadow, cream page block, tabs, tape, note, CTA, Shiori,
  bookmark, emboss, props, and cover field must have zero changed pixels.
- No resampling, sharpening, denoising, global color grade, or recompression
  drift across unchanged pixels.
- No new pure-black connected stroke may appear.
- The exterior notebook silhouette must remain pixel-identical.

Explicit protected sample pixels that must remain unchanged:

- desk immediately left of the book `(520,620) = RGB(211,138,70)`
- cream page block `(900,655) = RGB(203,150,94)`
- page/tape area `(1200,665) = RGB(162,136,111)`
- desk outside book `(1430,620) = RGB(118,67,19)`

Verify these values from the source before editing. If any value differs, stop
and report instead of guessing.

## Absolute prohibitions

- No CSS `box-shadow`, `drop-shadow`, filter, gradient, mask, pseudo-element,
  border, overlay, or extra shadow asset.
- No edit to `HomeDashboard.tsx`, `globals.css`, AppShell, navigation, mobile
  assets, scene geometry, safe-zone coordinates, live text, or callbacks.
- No generative scene recreation and no whole-image relighting.
- Do not alter the existing cast shadow to make the rim look lighter.
- Do not delete or overwrite V10.6.
- Do not start the frontend or backend for Gate A.
- Never access Neon or production data.
- Do not commit, push, merge, or create another branch.

## Gate A validation

1. Record `git status --short` before work.
2. Verify the V10.6 hash, dimensions, mode, and protected samples.
3. Generate A/B/C deterministically from V10.6.
4. Validate dimensions, changed-pixel bounds, semantic mask containment,
   protected samples, and outside-mask identity.
5. Inspect the contact sheet at full scene, 100%, and 4x crops.
6. If a candidate has a hard contour, flat fill, halo, or altered cast shadow,
   discard and regenerate it once. One technical correction pass maximum.
7. Run `git diff --check`. Do not run the app or build because no production
   source is being changed.
8. Return the report and wait for human candidate selection.

## Failure criteria

Fail Gate A if any of the following is true:

- The full scene is regenerated, resized, shifted, blurred, or globally graded.
- Any pixel outside the semantic leather mask changes.
- The broad cast shadow or exterior silhouette changes.
- The cream page edge loses separation from the rim.
- The rim becomes gray, orange, uniformly painted, or brighter than the cover.
- A hard mask line or halo is visible at 4x.
- Candidate C exceeds the 15% lightness ceiling.
- CSS/JSX/mobile/behavior files are touched.
- More than one technical correction pass is used.

## Required concise report

1. Source hash/dimension/sample verification
2. Confirmed failure mechanism
3. Exact semantic mask method and changed-pixel bounds
4. Candidate A/B/C measured lightness and color shift
5. Full-scene and 4x visual verdict for each candidate
6. Protected pixels and outside-mask identity result
7. Contact-sheet path
8. Files created and production files unchanged proof
9. Recommended candidate with one-sentence reason
10. Remaining risk

End with `Gate A complete - awaiting candidate selection.` Do not continue to
production wiring.
