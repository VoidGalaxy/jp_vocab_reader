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
   - `study-flashcard-stack-candidate-web.webp`
   - Use felt board texture for `.study-board-scene`.
   - Flashcard stack is a candidate crop/background for `.study-card-stack`
     or the active card surface, but should not replace rating buttons or
     SRS controls.

## Source PNGs

The PNG files in this folder are original candidates kept for future cropping
or higher-quality reprocessing. Prefer the `*-web.webp` files for CSS usage.

## Guardrails

- Keep all product text live in HTML.
- Keep callbacks, API, SRS, storage, auth, shared-deck policy, and CRUD logic
  untouched.
- Add fallback background colors for every image-backed surface.
- Decorative layers must use `pointer-events: none` when they can overlap
  controls.
