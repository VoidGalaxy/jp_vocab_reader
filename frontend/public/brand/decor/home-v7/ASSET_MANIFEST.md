# Home V7 Asset Manifest

Canonical Home V7 assets for the physical stationery scene.

## Current Production Assets

- `home-v7-notebook-tabs-shadow-plate.png`
  - 1298x1007 transparent PNG.
  - Contains the dark forest-green notebook, bookmark ribbon, embossed book/leaf mark, three separated torn-paper tabs, and their tape strips.
  - Does not contain live UI text. The three shortcut buttons are still real DOM hit zones placed over the tab artwork.
  - The bottom-right grey residue from an earlier plate version was removed before this pass. Page, cover, ribbon, tape, and tab color pixels were preserved.

- `home-v7-shiori-reading-peek.png`
  - 1024x1050 transparent PNG.
  - Home-only selected Shiori pose: charm ring, head, hands, open book, and dangling leaf charm.
  - Rendered as a plain Home image, not added to `Shiori.tsx`, so other Shiori usages are unchanged.

## Current Shadow Strategy

- No shadow raster file is wired.
- `globals.css` draws the contact shadow with `.home-v4-notebook::before` and `.home-v4-notebook::after`.
- The shadow is a contact-zone map, not a full-plate blur:
  - broad bottom/right falloff,
  - tighter near-contact seam,
  - three separated tab underside shadows.
- This replaces the failed approaches that produced rectangular boundaries, black bars, or barely visible shadows:
  - `filter: drop-shadow(...)` on the notebook image,
  - full alpha-blurred plate shadow PNGs,
  - oversized rectangular shadow layers.

## Removed/Superseded Assets

The following shadow-only PNGs are intentionally removed from the working asset set and must not be referenced from CSS:

- `home-v7-notebook-tabs-contact-shadow.png`
- `home-v7-notebook-tabs-contact-shadow-target.png`
- `home-v7-notebook-tabs-contact-shadow-v4.png`

They were generated during the shadow exploration passes, but live screenshots showed they either became too weak at browser scale or exposed a rectangular canvas boundary on the wood surface.

## Implementation Contract

- Keep Home text live in DOM; do not bake Korean labels into images.
- Preserve Home callbacks, routing, auth, storage, SRS, API, and backend behavior.
- Use the plate as the geometry source for notebook/tab hit zones.
- If the notebook plate changes, re-check shortcut hit-zone coordinates and Shiori tape alignment.
