# Phase 127 Image Asset Candidates

Generated for the next mockup-alignment pass. These assets are decorative
surface/material candidates only. Do not bake UI text, vocabulary, meanings,
buttons, filters, or status controls into images.

## Highest-priority application targets

1. Shared Deck shelf and deck covers
   - `shared-deck-cover-set-candidate-web.webp`
   - `shared-shelf-wood-strip-web.webp`
   - Use the cover set as a crop source or background-position atlas for
     `BrandDeckCover` / `.brand-deck-cover` variants.
   - Use the shelf strip to replace or strongly reduce CSS-only wood shelf
     gradients in `.shared-library-scene` / `.shelf-section`.

2. Vocab notebook surface
   - `vocab-ring-notebook-spread-web.webp`
   - Candidate for `.vocab-notebook-scene` desktop background.
   - Strong fit for the current 3-column model: left index tabs, center page,
     right clipped detail note.
   - Must preserve list scanability and live HTML rows.

3. Study board and card stack
   - `study-felt-board-texture-web.webp`
   - Use felt board texture for `.study-board-scene`.
   - The flashcard-stack candidate was cropped by Phase 131 into
     `phase131/study-flashcard-stack-clean.webp` (now in production on
     `.study-card-backing-sheet`, applied Phase 132) -- should not
     replace rating buttons or SRS controls.

## Source PNGs (Phase 140 update)

The original PNG candidates that used to sit in this folder were moved
to `docs/design/source-assets/phase127/` in Phase 140 -- nothing in
`frontend/` ever referenced them by URL, so keeping them in
`frontend/public/` only added ~13MB to every deploy for files no
browser would fetch. See that folder's own `README.md` for the full
PNG -> shipped-WebP mapping. Prefer the `*-web.webp` files in this
folder for CSS usage; go to the archive only if a future crop needs a
higher-resolution or differently-framed start point than a currently
shipped WebP already provides.

Also removed in Phase 140: `study-flashcard-stack-candidate-web.webp`
(the WebP export of the same PNG now archived above) -- fully
superseded by Phase 131's individual crop, no unique provenance of its
own.

## Guardrails

- Keep all product text live in HTML.
- Keep callbacks, API, SRS, storage, auth, shared-deck policy, and CRUD logic
  untouched.
- Add fallback background colors for every image-backed surface.
- Decorative layers must use `pointer-events: none` when they can overlap
  controls.
