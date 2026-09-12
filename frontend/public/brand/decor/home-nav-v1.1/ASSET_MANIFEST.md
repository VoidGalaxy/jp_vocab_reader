# Home Navigation V1.1 Asset Manifest — Density and Grounding Pass

Status: **Gate A approved, Gate B wired.** Live in `AppShell.tsx` via
`globals.css`'s `@media (min-width: 1024px)` toolbar rules. `home-nav-v1/`
is untouched and no longer referenced by production CSS.

Brief: `references/mockups/home-nav-prep/CLAUDE_DENSITY_PASS.md`.

## Gate B correction (one alpha pass, per approval)

At real 1280px scale the Gate A divider (peak alpha 33/20, a ~40%
reduction from V1) was effectively illegible between icon and label.
Per the approved correction allowance, `home-nav-divider-emboss.png`'s
alpha channel only was re-scaled (multiplier `×1.55` on top of the same
12×36→10×30 resize — no re-resize, no recolor, no size change, no CSS
line substitute): new peak alpha 54 (highlight column) / 33 (shadow
column), SHA-256 `74c9893753cd1efea8789ebd403e4606a287391ed7d2d1786a0d25fea19d55e8`.
This lands within a couple points of V1's own native peak alpha (57/32)
— matching V1's established subtlety (and NAV_DESIGN_CONTRACT.md's
0.12–0.2 opacity range: 54/255≈21%, 33/255≈13%) rather than exceeding
it. No further correction was made after this one pass.

All four assets below were derived **deterministically** from the approved
`home-nav-v1/` source files using `sharp` (resize + per-pixel arithmetic on
raw RGBA buffers). No image model was asked to redraw any asset.

## 1. `home-nav-paper-strip.png`

- Source: `home-nav-v1/home-nav-paper-strip.png` (1920×64 RGBA, SHA-256
  `cd18a0fbb2f6b34f043a816a23d0d587cf283c69bec4afe4df15b55a96fa50ee`).
- Output: **1920×56 RGBA**. SHA-256:
  `569cbbaf10b76cff11b811a1cc91142c78698d10d6c83d01909bab417404684b`.
- Transform (applied in order):
  1. Vertical resize 64px → 56px (0.875×), width unchanged, `lanczos3`
     kernel, `fit: fill` — proportionally compresses the existing fiber
     texture and deckled silhouette rather than redrawing it.
  2. Global warm/dark tint on RGB only (alpha untouched):
     `R *= 0.98`, `G *= 0.96`, `B *= 0.92`. Measured on the flat opaque
     core (rows unaffected by the edge shade below): average darkening
     **4.71%**, disproportionate blue reduction reads as warmer. Within
     the requested 4–6% range.
  3. Per-column baked warm contact shade on the last opaque rows before
     the deckle fade, computed independently for each of the 1920
     columns (the deckle line is irregular, so this is a contour-hugging
     shade, not a rectangular band): for each column, find `edgeY` = the
     last row with alpha ≥ 250. Multiply RGB at `edgeY` by `0.55`
     (+ extra `×0.88` on blue), at `edgeY-1` by `0.75` (+ extra `×0.92`
     on blue), at `edgeY-2` by `0.9` (+ extra `×0.97` on blue); rows
     further from the edge are untouched. This puts peak shading at the
     row closest to the edge and fades it out within 3 rows, per spec
     ("strongest within 1px, fully faded by 3px"). No new alpha is
     added — the shade lives entirely inside the existing opaque
     silhouette, so there is no rectangular shadow, blur band, gray
     halo, or opaque fill outside the paper's own shape.
- Alpha check: corners and the deckle tail remain fully transparent
  (alpha 0) exactly as in V1; the semi-transparent deckle fringe (alpha
  1–252) is preserved from the resize, unedited by the shade step (shade
  only touches alpha ≥ 250 pixels).
- Visual check: magnified 4× composite over a contrasting background
  shows the V1 edge carries a **bright** anti-aliasing fringe right at
  the deckle line (reads as a thin halo); V1.1 replaces that with a
  **warm brown** contact shade hugging the same contour — a visible
  grounding improvement, not just a resize.

## 2. `home-nav-active-linen.png`

- Source: `home-nav-v1/home-nav-active-linen.png` (106×40 RGBA, SHA-256
  `8226ae26e9e94b99e520e11c119539a572cbd9c4d36f125c876d7bbd6b88a5a3`).
- Output: **98×36 RGBA**. SHA-256:
  `c7cf4351b81ec1798a5a3c4b1b8bc9c477e74f6642bb65178ca1a49540db627a`.
- Transform: direct resize 106×40 → 98×36, `lanczos3` kernel, `fit: fill`
  (no recolor, no new shadow/outline, no text/icon added). The four
  corner pixels are then force-zeroed (defensive against any resize
  interpolation residue).
- Alpha check: all four corner pixels confirmed `(0,0,0,0)` after the
  explicit zeroing step.
- Stitch check: sampled the mid-height row — the cream stitch highlight
  peaks at a single column (~x=3 of 98, alpha 255, RGB ~122/121/97)
  flanked by base dark-green linen on both sides, i.e. renders as
  approximately 1px at native scale, matching V1's proportional inset.
- Color check: dark forest-green base (RGB ~30/47/27, unchanged hue
  from V1) and cream stitching both preserved; no recolor applied.

## 3. `home-nav-divider-emboss.png`

- Source: `home-nav-v1/home-nav-divider-emboss.png` (12×36 RGBA, SHA-256
  `b5dc80e568ca6e3e93b83cfc8c7551410a9cd7bd06811f6222f9a69a180deb50`).
- Output: **10×30 RGBA**. SHA-256 (current, post Gate B correction):
  `74c9893753cd1efea8789ebd403e4606a287391ed7d2d1786a0d25fea19d55e8`.
  (Gate A's original SHA-256 was
  `405fa34378f2b2ad02b2c7fd65498039b7601701ea42b0d428333e4d50882b40`,
  peak alpha 33/20 — superseded by the Gate B alpha correction below.)
- Transform:
  1. Resize 12×36 → 10×30, `lanczos3` kernel, `fit: fill`. The narrow
     1px-highlight / 2px-shadow pair naturally dilutes under this
     resize.
  2. Alpha multiplier on top of the resize: Gate A used `×0.95`
     (~40% below V1's native peak alpha); Gate B corrected this to
     `×1.55` after the `×0.95` version proved illegible at real 1280px
     scale (see "Gate B correction" above) — both are alpha-only, no
     re-resize, no recolor, no size change.
- Contrast check (peak alpha, native render scale, current asset): V1
  highlight column peak alpha 57 → V1.1 peak alpha **54** (5.3% below
  V1). V1 shadow column peak alpha 32 → V1.1 peak alpha **33**
  (~parity with V1, +1). This is intentionally close to V1's own
  native contrast rather than the Gate A ~40%-reduced target, because
  going quieter than V1 made it disappear entirely at real scale.
- Vertical extent check: the flat-peak "core" of the mark (excluding the
  1–2px soft feather at each end) spans rows 8–22 of the 30px canvas =
  **15px**, inside the requested 14–16px range (unaffected by the alpha
  correction, which touches only the alpha channel).
- Color check: highlight column reads warm cream (~80/58/51), shadow
  column reads warm brown (~48/36/12) — no gray, no ink black. Corners
  confirmed `(0,0,0,0)`.
- Visual check: magnified composite over the actual paper tone shows a
  faint, short, warm highlight/shadow pair — reads as a shallow paper
  groove, not a rule, at the same subtlety V1 already shipped with.

## 4. `home-nav-asset-preview.png`

- Output: **1280×56 RGBA** (no source hash — this is a fresh
  text-free assembly, not a derived transform of one V1 file).
  SHA-256: `bd7f4f1fc39843ab6d2be7b7f273e86e5e98c56244a6f5512b02ff6ee90d73f9`.
- Construction: center-cropped 1280px slice of the V1.1 paper strip (the
  stretch-safe center region, avoiding either raw edge) as the
  background, then composited at real rendered scale:
  - One 98×36 active-linen patch, centered inside a 106px-wide slot
    starting at x=20 (matches the Gate B "first tab left edge ≈20px").
  - Six 10×30 divider-emboss marks, one at each boundary between the
    seven 106px slots (x = 20 + 106×n), vertically centered in the
    intended 50px toolbar-host band.
  - No text or icons anywhere in this file.

## Alpha / matte / halo checks (all four assets)

- No asset has any opaque pixel outside its intended silhouette (no
  rectangular background fill).
- No asset's edge carries a light-gray or checkerboard matte fringe —
  verified by compositing each asset over both a strongly contrasting
  color and the actual paper tone at 4–16× magnification.
- Divider and linen corner pixels are exactly `(0,0,0,0)` (checked
  programmatically, not just visually).
- No CSS-only material stand-in was used anywhere — every visual (paper
  fiber, deckle, contact shade, linen weave, stitch, emboss) lives in
  the raster asset itself.

## Guardrails

- `home-nav-v1/` is unchanged and still present; nothing here overwrites
  or deletes it. Production CSS no longer references it anywhere.
- `AppShell.tsx`'s JSX (structure, nav order, callbacks, icons, labels,
  `aria-current`, feedback/account slots) is unchanged by Gate B — only
  `globals.css`'s desktop (`min-width: 1024px`) toolbar rules were
  repointed at these assets and resized to the locked measurements
  (50px host / 56px paper / 6px overlap, 106×36px slots, 98×36px active
  linen, 15px icons, 12.5px labels, ~20px first-tab left edge).
- Korean labels and icons remain live DOM content in production; none of
  these assets bake in text or icons.
