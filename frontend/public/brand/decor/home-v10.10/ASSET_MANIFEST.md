# Home V10.10 Lower-Edge Physical Rebuild

## Production asset

- `home-v10.10-scene-desktop.png`
- 1888 x 833, RGB PNG
- SHA-256: `EF6DF66DA6F3001BF241E7E2F833AC2AA0DB9F55639AD6749186ACEF87C696CC`
- Desktop-only full scene. Mobile remains on the V10.5 scene.

## Source

- Pixel source: `home-v10.9/home-v10.9-scene-desktop.png`
- Source SHA-256: `59103B4E54A74DA974A542ABBA5F9AC4DDAD8EE29D7B490338B4B1D19FC32606`
- Approved Gate A candidate:
  `references/mockups/home-v10.10-prep/home-v10.10-scene-desktop-candidate.png`
- Structural reference:
  `references/mockups/home-v10.10-prep/home-v10.10-codex-lower-edge-reference.png`
- Reproducible compositor:
  `references/mockups/home-v10.10-prep/build_codex_lower_edge_candidate.py`

The approved candidate was copied into production without re-encoding; its
SHA-256 is identical before and after the copy.

## Reconstruction scope

Only the desktop notebook lower-edge envelope was reconstructed:

- thin cloth-wrapped front-cover lip,
- warm cream page block,
- tape and hidden tab-root contacts,
- local tab and notebook grounding shadows.

The three visible tab bodies are restored from V10.9 and remain byte-identical.
All pixels outside `x=500..1435, y=570..750` remain sourced from V10.9. The
candidate contains no CSS shadow, filter, gradient, pseudo-element, black bar,
procedural ruled-paper pattern, or whole-scene replacement.

## Integration contract

- Keep desktop scene geometry at 1888 / 833.
- Keep all Home overlay coordinates unchanged.
- Keep the mobile source on `home-v10.5-scene-mobile.png`.
- Do not add separate lower-edge or shadow layers in CSS.
