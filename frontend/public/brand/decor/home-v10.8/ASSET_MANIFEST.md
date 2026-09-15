# Home V10.8 Lower-Edge Structure Recovery

## Status

Final desktop candidate wired for browser validation. V10.7 remains preserved
as the prior production asset. Mobile continues to use V10.5 unchanged.

## Production candidate

- `home-v10.8-scene-desktop.png`
- Dimensions: `1888x833`
- Mode: opaque RGB PNG
- SHA-256:
  `69D6BE29B7DDA304CC10733FEDBFDB619E7356680B5818EBAC1669A5DD2608A1`

## Source and method

- Pixel-preservation base:
  `frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png`
- Base SHA-256:
  `150F585937AF99163C8C671FCE10600E63D540FE899D5E7A13915E3230CBE131`
- Generated structural reference:
  `references/mockups/home-v10.8-prep/home-v10.8-generated-edge-reference.png`,
  a built-in ImageGen precise-object edit used only inside the notebook lower-edge
  envelope; it is not used as a whole-scene replacement.
- Reproducible compositor:
  `references/mockups/home-v10.8-prep/build_codex_edge_candidate.py`

The candidate starts from V10.4 and blends the structural reference only into
the notebook lower-edge envelope. The blend is vertically and horizontally
feathered. The three existing tab/tape regions are restored from the V10.4
base before a second bounded material pass removes residual crushed seams.

The front-cover terminal seam inherits real cloth variation from the cover
above rather than receiving a constant color. The left and right corner returns
use separate interior cloth samples so black wedges are lifted without creating
a constant-width green tube. The cream page block remains the dominant visible
book thickness. The broad desk cast shadow remains from V10.4.

## Pixel bounds

Decoded RGB comparison against V10.4 at max-channel threshold `>2/255`:

- Changed pixels: `41,679`
- Changed fraction: `2.650149%`
- Changed bounding box: `x=518..1423, y=614..689`

No pixel outside that bounding box changes. Scene composition, dimensions,
props, note, CTA, Shiori, bookmark, emboss, and the rest of the notebook remain
from V10.4.

## Rendering contract

- Reuse the existing desktop ratio `1888 / 833` and all overlay coordinates.
- Do not add CSS shadow, filter, gradient, border, mask, or pseudo-element.
- Mobile remains `/brand/decor/home-v10.5/home-v10.5-scene-mobile.png`.
