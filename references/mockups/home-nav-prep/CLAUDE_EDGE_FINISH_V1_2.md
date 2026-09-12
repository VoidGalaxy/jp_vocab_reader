# Home Nav V1.2 Natural Paper Edge Asset Pass

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-nav-edge-finish`

## Gate A only

Create and compare replacement paper-strip candidates. Do not wire any candidate into production CSS or components in this run. Stop for approval after producing the assets, manifest, and comparison previews.

## Current screenshots

- Home: `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 033231.png`
- Review: `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 033242.png`

The old scene-title protrusions are already fixed. The remaining failure is the paper strip's lower contour: it reads as a continuous gray/black ink outline instead of a thin paper edge making soft contact with the scene below.

## Mandatory failure analysis

State these three facts before producing assets:

1. V1.1 multiplies RGB on the last three opaque rows of every deckle column by `0.55`, `0.75`, and `0.9`.
2. That shading is baked inside the opaque paper silhouette, so it remains a crisp dark contour over every background rather than behaving like a cast/contact shadow.
3. A natural result requires a clean paper fiber edge plus a separate low-opacity warm shadow outside the paper alpha, fading with distance.

## Scope

Rebuild only the desktop paper strip.

Preserve without modification:

- `home-nav-active-linen.png`
- `home-nav-divider-emboss.png`
- toolbar height 50px
- 106x36px nav slots
- 98x36px active linen
- icon/text sizing and all nav behavior
- all scene-seam fixes from commit `dc4afe8`
- all Home and tab scene assets
- mobile navigation

Do not modify `globals.css`, `AppShell.tsx`, any component, or any existing V1/V1.1 asset in this Gate A run.

## Deterministic asset construction

Create:

`frontend/public/brand/decor/home-nav-v1.2/`

Use `home-nav-v1/home-nav-paper-strip.png` as the source, not the already darkened V1.1 paper strip. No image-generation model and no manual painted line.

### Paper body

1. Resize the V1 source paper from 1920x64 to a 1920x56 paper body using alpha-correct premultiplied resampling.
2. Apply the approved V1.1 warm/dark core tint only: `R*0.98`, `G*0.96`, `B*0.92`.
3. Do not apply the V1.1 `0.55/0.75/0.9` opaque-edge darkening.
4. Remove bright interpolation contamination from semi-transparent deckle pixels by propagating the nearest interior paper RGB into fringe pixels while preserving their resized alpha. Do not create a white, gray, or black matte.
5. Preserve the original irregular deckled silhouette. Do not smooth it into a wave or straight line.

### Canvas and exterior shadow

- Final candidate canvas: 1920x64 RGBA.
- Place the 1920x56 paper body at `(0,0)` without rescaling it again.
- Rows 56-63 are transparent padding reserved for a short exterior shadow.
- Derive the shadow from the final paper alpha mask.
- Offset downward only. No visible shadow above or along the left/right canvas edges.
- Color must be warm desk brown, never neutral gray or black.
- Remove the paper silhouette from the shadow layer before compositing, so zero shadow darkens any opaque paper pixel.
- Shadow must be strongest within 1-2px outside the torn edge and reach alpha 0 before the final canvas row.
- No continuous 1px stroke is allowed around the paper contour.

## Produce three candidates

Keep paper geometry and color identical. Vary only exterior shadow strength/falloff:

### Candidate A - quiet contact

- warm brown around `#69462d`
- peak effective opacity about 8%
- vertical offset about 1px
- blur/falloff about 2px

### Candidate B - balanced contact

- same color
- peak effective opacity about 12%
- vertical offset about 1.5px
- blur/falloff about 3px

### Candidate C - grounded contact

- same color
- peak effective opacity about 16%
- vertical offset about 2px
- blur/falloff about 4px

Exact implementation parameters may differ slightly because Sharp blur kernels operate discretely, but measured output must match the visual intent and constraints above. Record exact values.

Name them:

- `home-nav-paper-strip-a.png`
- `home-nav-paper-strip-b.png`
- `home-nav-paper-strip-c.png`

## Required comparison preview

Create a contact sheet at:

`frontend/public/brand/decor/home-nav-v1.2/home-nav-edge-contact-sheet.png`

The sheet must show A/B/C at 100% rendered desktop scale over three representative backgrounds:

1. Home warm wood
2. Review mint felt/board
3. Reading cream open-book page

Use actual project scene assets or clean crops from the supplied screenshots. Do not use flat color rectangles as the only test. Keep the same crop, y-position, and scale in every candidate row.

Also include 4x close crops of the torn edge for pixel inspection, but do not judge solely from magnified views. The primary decision is the normal 100% view.

The preview should include the active linen and dividers only if needed for context; reuse V1.1 versions unchanged. Do not bake live Korean labels into any production candidate.

## Programmatic validation

For each candidate verify and report:

- exact dimensions 1920x64 RGBA
- paper body position unchanged across A/B/C
- no shadow overlap on pixels where paper alpha is 255
- no opaque or semi-opaque pixels touching the final row
- no unexpected alpha on the top edge or left/right canvas edges
- warm shadow hue: red channel greater than or equal to green, green greater than blue
- shadow alpha profile decreases as distance from the paper edge increases
- no continuous dark stroke inside the last three opaque paper rows
- no rectangular matte or gray halo over both light and dark test backgrounds
- SHA-256 for source and each output

## Rejection criteria

Reject a candidate if any of these is visible at normal scale:

- black/gray contour line
- double line under the paper
- bright white fringe
- shadow darkening the paper itself
- uniform straight band
- shadow cut off at canvas bottom
- fuzzy halo wider than the paper fibers
- different paper position or thickness between candidates
- an apparent gap between navigation paper and the scene

## Gate A report

Report:

1. Confirmed V1.1 failure mechanism
2. Exact source and transforms
3. A/B/C measured shadow profiles
4. Alpha/matte/stroke validation
5. Contact-sheet path
6. Recommendation with one sentence explaining why
7. Files created and proof that production code is untouched
8. Remaining risk

Do not commit or push. Stop for user approval before Gate B wiring.
