# Home V10.12 Final Desktop Polish

## Production asset

- `home-v10.12-scene-desktop.png`
- 1888 x 833, RGB PNG
- SHA-256: `48B97975DB620EF819852DCFACBB232C15089B0C7359F195C035AFF4E6592726`
- Final desktop Home scene. Mobile remains on V10.5.

## Source and containment

- Source: `home-v10.11/home-v10.11-scene-desktop.png`
- Source SHA-256: `71C86CA7C3AEBB055C83CE01FBE83FB97ECCB49A517043EA4ABE6EF7830AEED7`
- Structural reference: `references/mockups/home-v10.12-prep/home-v10.12-final-reference.png`
- Reproducible compositor: `references/mockups/home-v10.12-prep/build_v10_12_final.py`
- Changed-pixel envelope: `x=540..1400, y=635..760`
- Changed pixels outside the envelope: 0

## Final polish scope

- Reduced repetitive horizontal contrast in the warm ivory page block.
- Replaced tiny near-black root gaps with short warm contact shadows.
- Added restrained variation to the three cream tape pieces.
- Lowered tab saturation while preserving the yellow, coral, and blue roles.
- Preserved the green cover lip, both book corners, global shadow, layout, and mobile scene.

## Integration contract

- Keep desktop geometry at 1888 / 833.
- Keep all overlay coordinates, text, callbacks, and application behavior unchanged.
- Keep mobile on `home-v10.5-scene-mobile.png`.
- Do not add CSS shadows, filters, gradients, or separate patch layers.
