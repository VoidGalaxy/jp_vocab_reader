# Home V10.7 Asset Manifest — Final Production

## Status

Production asset. Candidate B was selected by human review at Gate A and is
wired into `HomeDashboard.tsx` for `min-width: 768px` (desktop). Mobile
continues to use the V10.5 scene, unchanged.

## Production asset

- `home-v10.7-scene-desktop.png` (renamed from the approved
  `home-v10.7-scene-desktop-b.png` candidate, byte-for-byte, no re-encode)
- Dimensions: `1888x833`, 8-bit RGB PNG
- Final SHA-256:
  `3E47D6CD8517C3176C8A0CAF6611DCE6C9788991F1B8B96CF71A83E10AF9D628`
- Role: desktop Home full-scene image for `min-width: 768px`

## Source

- `frontend/public/brand/decor/home-v10.6/home-v10.6-scene-desktop.png`
- Source SHA-256:
  `3F606A0C500AC9033455381DAA8BD09607CA0E8B542F241A7677B654B49623A0`

V10.6 is untouched and remains on disk as the prior-version source of truth;
it is no longer requested by production Home.

## Selection

Three candidates (A conservative, B balanced, C maximum) were generated
deterministically from the untouched V10.6 source and compared on a contact
sheet (`references/mockups/home-v10.7-prep/home-v10.7-rim-contact-sheet.png`).
Candidate B was approved: it removes the crushed-black outline character
while retaining more physical weight/grounding than Candidate C and more
correction than Candidate A.

## Method (bounded, deterministic — no ImageGen, no whole-image regrade)

1. **Envelope** (hard safety boundary, union of three boxes): lower rim
   `x=520..1424, y=615..684`; left corner `x=510..589, y=585..699`; right
   corner `x=1350..1434, y=575..699`. No pixel outside this union was ever
   touched.
2. **Semantic leather mask**: a pixel inside the envelope qualifies as
   notebook-cover leather only if its green channel is (near) the maximum
   channel (`G >= R - 6` and `G >= B - 6`), which excludes the cream page
   block, beige tape, yellow/red tabs (red-dominant) and the blue tab
   (blue-dominant) without any hand-drawn polygon.
3. **Crush severity weight**: `clip((45 - luminance) / 45, 0, 1)` (Rec.709
   luminance), 0 at the normal non-crushed cover tone, 1 at true black.
4. **Spatial feather**: the crush-weighted seed was smoothed with a 3-pass
   box blur (radius 4, ≈6-12px effective feather), then hard re-clipped to
   (a) the envelope and (b) the semantic leather mask, so feathering never
   bled onto an adjacent different-colored surface even where that surface
   sits geometrically inside the envelope box.
5. **Local-neighborhood color recovery**: a per-pixel local leather color
   estimate was computed from genuine nearby non-crushed cover pixels only
   (same color test, luminance ≥ baseline) via a weighted local average
   (9px radius, 3-pass box blur), so crushed pixels were reconstructed from
   real surrounding leather texture, never a flat fill.
6. **Warm olive hue bias**: that local estimate was blended toward a fixed
   warm olive/green-brown anchor (Candidate B: midpoint of `#292b1b` and
   `#3b3924`) at blend amount 0.72, kept below 1.0 so real local grain
   survives even at the single most-crushed pixel.
7. Final pixel = `original * (1 - weight) + biased_local_estimate * weight`,
   clipped to `[0,255]`. Weight is 0 for every pixel outside the envelope or
   outside the semantic leather mask, so those pixels are byte-identical to
   V10.6. Core (weight≈1) recovered color measured at approval time:
   RGB(45, 49, 30), lightness 47.1.

## Pixel-integrity result (verified at Gate A, re-verified unchanged by rename)

0 changed pixels outside the envelope, 0 changed pixels outside the semantic
leather mask, 0 changed pixels failing the leather color test, and all four
protected desk/page/tape sample pixels byte-identical to V10.6.

## Rendering contract

- Reuse the V10.6/V10.7 shared desktop aspect ratio (`1888 / 833`) and every
  overlay coordinate unchanged — no coordinate recalculation.
- No CSS shadow, filter, gradient, border, or masking over this asset.
- Mobile continues to use the V10.5 scene, untouched.
