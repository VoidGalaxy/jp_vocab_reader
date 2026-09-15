# Home V10.9 Side Grounding

## Production asset

- `home-v10.9-scene-desktop.png`
- 1888 x 833, RGB PNG
- SHA-256: `59103B4E54A74DA974A542ABBA5F9AC4DDAD8EE29D7B490338B4B1D19FC32606`
- Desktop-only full scene. Mobile remains on the existing V10.5 asset.

## Purpose

V10.8 corrected the lower page structure but retained three dark recessed side
details: two on the left spine and one along the right fore-edge. V10.9 repairs
only those user-marked regions so they read as rounded cloth-covered volume
rather than black slots.

## Source and method

- Pixel source: `home-v10.8/home-v10.8-scene-desktop.png`
- Structural reference:
  `references/mockups/home-v10.9-prep/home-v10.9-side-reference.png`
- Reproducible compositor:
  `references/mockups/home-v10.9-prep/build_codex_side_candidate.py`

The reference was generated from the clean V10.8 production scene with the
user's blue-marked screenshot used only as a location guide. The compositor
blends it through three feathered envelopes and clips the blend to dark
green/neutral notebook material. Desk, note, ribbon, page block, tape, tabs,
Shiori, bookmark, and all other scene pixels remain sourced from V10.8.

No CSS shadow, filter, gradient, or layout-coordinate change is required.

Decoded pixel comparison against V10.8 with a max-channel threshold greater
than 2/255: 38,323 changed pixels (2.436759%), bounded to
`x=514..1413, y=112..686`. The wide aggregate bounding box is the union of the
three separated repair regions; pixels between those regions remain unchanged.
