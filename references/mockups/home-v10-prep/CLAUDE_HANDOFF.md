# Home V10 Full Scene Replacement

## Read First

1. `frontend/components/HomeDashboard.tsx`
2. `frontend/app/globals.css`
3. `frontend/public/brand/decor/home-v10/ASSET_MANIFEST.md`
4. `references/mockups/home-v10-prep/ASSET_ACCEPTANCE.md`

Project: `C:\JV_Project\jp_vocab_reader`

## Current Failure

1. Home is still an assembly of v3/v4/v7/v8 image fragments rather than one physical desk scene.
2. Separately positioned book, tabs, Shiori, and shadow layers repeatedly created visible seams, matte rectangles, floating depth, and breakpoint drift.
3. A passed build and click test did not prevent the screenshot from visibly disagreeing with the approved composition.

## Goal

Replace the Home visual skeleton with the locked V10 full scene. The desktop and mobile assets are the source of truth for scale, overlap, Shiori placement, tab relationships, and every shadow.

## Remove or Redefine

- Remove the Home-only `home-v4-note`, `home-v4-cta`, `home-v4-notebook`, `home-v4-shiori-peek`, and all separate image-art wrappers as visual objects.
- Remove Home runtime references to home-v3, home-v4, home-v7, and home-v8 art.
- Do not retain CSS background/gradient/filter/drop-shadow/pseudo-element attempts for notebook, tabs, or Shiori.
- Rebuild the visual shell as one `.home-v10-scene` positioning root with an opaque scene image behind live DOM overlays.

## Required Runtime Structure

1. Use a `picture` or equivalent responsive image base: V10 desktop at desktop widths, V10 mobile below the chosen mobile breakpoint.
2. Treat that image as decorative and non-interactive (`aria-hidden`, no pointer interception).
3. Keep the existing callbacks exactly unchanged: sample, reading CTA, vocab, review/account branch, and shared decks.
4. Put the existing Korean text, icons, and buttons over the exact safe zones from `ASSET_ACCEPTANCE.md`; calculate percentages from the listed asset dimensions. Do not invent or tune separate coordinates.
5. Preserve accessible names and keyboard focus. Focus/hover feedback may use a subtle outline confined to the DOM hit zone; it cannot paint a physical shadow or alter the scene image.

## Asset Rules

- Do not crop, re-encode, alpha-extract, difference-matte, filter, or otherwise alter either V10 scene image.
- Shiori is already inside the scene. Do not render a second Shiori image.
- The scene has blank paper/tab safe zones intentionally. Do not add text to the raster file.
- No replacement image generation in this implementation phase.

## Exact Failure Conditions

- Any rectangular or black-bar shadow, visible alpha/matte residue, or CSS-drawn contact shadow: fail.
- Any v3/v4/v7/v8 Home art still requested at runtime: fail.
- Desktop simply scaled onto mobile: fail.
- Live text touching tape, torn edges, or shadows: fail.
- A before/after Home screenshot with the same fragmented-object silhouette: fail.

## Boundaries

Presentation work only. Do not change callbacks, API calls, routes, auth,
storage, SRS, shared decks, backend files, schemas, or user data behavior.

## QA

Use 1280 and 390 screenshots first, then 1024, 375, and 320 only after the
scene is visually correct. Check overflow, image 404s, console regressions,
and real clicks for CTA/sample/vocab/review/decks. Run one final build and
`git diff --check`. Save a full 1280 screenshot and compare it directly with
`home-v10-desktop-scene-candidate.png` before reporting completion.

Allow one screenshot-driven correction only. If the scene base or DOM zones do
not match, stop and report the precise mismatch instead of adding CSS patches.
