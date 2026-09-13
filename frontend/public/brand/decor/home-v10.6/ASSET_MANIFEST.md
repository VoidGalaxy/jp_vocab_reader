# Home V10.6 Asset Manifest

## Production asset

- `home-v10.6-scene-desktop.png`
- Dimensions: 1888x833
- Color: 8-bit RGB PNG
- Role: desktop Home full-scene image for `min-width: 768px`

## Source

- `frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png`
- Source SHA-256: `150F585937AF99163C8C671FCE10600E63D540FE899D5E7A13915E3230CBE131`
- V10.6 SHA-256: `3F606A0C500AC9033455381DAA8BD09607CA0E8B542F241A7677B654B49623A0`

## Bounded edit

The first image edit was generated from the V10.4 source with a strict request
to soften only the notebook's near-black lower rim and lower corners. Pixel
comparison showed low-level changes across the full canvas, so that output was
not wired directly.

The production V10.6 image keeps V10.4 as its base and blends the generated
lighting reference only into dark pixels inside the lower notebook rim. The
feathered edit is bounded to source coordinates `x=528..1420`, `y=622..677`.
Only 11,732 pixels differ by more than 2/255, or 0.746% of the full canvas.

The desk, props, note, CTA ribbon, Shiori, bookmark, emboss, tabs, tape, broad
cast shadow, composition, crop, object coordinates, and all pixels outside the
bounded rim region remain from V10.4.

## Rendering contract

- Reuse the V10.4 desktop aspect ratio and every overlay coordinate unchanged.
- Do not add CSS shadow, filter, gradient, border, or masking over this asset.
- Mobile continues to use the existing V10.5 scene without modification.
