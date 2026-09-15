# Home V10.11 Lower-Edge Final Polish

## Production asset

- `home-v10.11-scene-desktop.png`
- 1888 x 833, RGB PNG
- SHA-256: `71C86CA7C3AEBB055C83CE01FBE83FB97ECCB49A517043EA4ABE6EF7830AEED7`
- Desktop-only full scene. Mobile remains on the V10.5 scene.

## Source and containment

- Pixel source: `home-v10.10/home-v10.10-scene-desktop.png`
- Source SHA-256: `EF6DF66DA6F3001BF241E7E2F833AC2AA0DB9F55639AD6749186ACEF87C696CC`
- Structural reference: `references/mockups/home-v10.11-prep/home-v10.11-lower-edge-reference.png`
- Reproducible compositor: `references/mockups/home-v10.11-prep/build_v10_11_candidate.py`
- Changed-pixel envelope: `x=490..1440, y=600..740`
- Changed pixels outside the envelope: 0

## Polish scope

- Replaced the uniform cream band with restrained, irregular paper layering.
- Reduced the heavy lower-right green leather taper.
- Varied the short local contact treatment below the three tape pieces.
- Preserved all three visible colored tab bodies byte-for-byte.

## Integration contract

- Keep desktop scene geometry at 1888 / 833.
- Keep all Home overlay coordinates and behavior unchanged.
- Keep mobile on `home-v10.5-scene-mobile.png`.
- Do not add CSS shadows, filters, gradients, or separate lower-edge layers.
