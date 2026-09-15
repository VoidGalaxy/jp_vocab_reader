# Home V10.10 Lower-Edge Physical Rebuild - Gate A

Project: `C:\JV_Project\jp_vocab_reader`

Target: Home desktop scene lower edge only.

Read first:

1. `references/mockups/home-v10.10-prep/DESIGN_PLAN.md`
2. `references/mockups/home-v10.10-prep/home-v10.10-lower-edge-source-crop.png`
3. `references/mockups/home-v10.10-prep/home-v10.10-lower-edge-source-2x.png`
4. `references/mockups/home-v10.10-prep/home-v10.10-user-marked-reference.png`
5. `frontend/public/brand/decor/home-v10.9/ASSET_MANIFEST.md`

## Current failure

The green cover bottom is a wavy compositing seam.
The cream page block is blurred and polluted by tab colors and black rectangular gaps.
The tape, tabs, page thickness, and shadow do not read as one physical construction.

## Phase goal

Reconstruct the full lower-edge stack as one coherent image asset before touching production code.

## Mandatory execution contract

- Use V10.9 as the full-scene pixel source and preserve its 1888 x 833 canvas.
- Work only inside `x=500..1435, y=570..750`.
- Rebuild the front-cover lip, page block, three tape attachments, tab-root contacts, and their grounding shadow together under one warm upper-left light.
- Preserve the visible yellow/coral/blue tab bodies, their spacing, torn outlines, and color.
- Preserve every pixel outside the envelope. Do not globally re-render the scene.
- Do not modify `HomeDashboard.tsx`, `globals.css`, JSX, coordinates, behavior, backend, API, auth, SRS, storage, or routing.
- Do not use CSS, procedural blur smears, cloned repeated texture, black bars, or gradient patches as substitutes for physical reconstruction.

## Required output

Create exactly one candidate:

- `references/mockups/home-v10.10-prep/home-v10.10-scene-desktop-candidate.png`
- 1888 x 833 RGB PNG

Create one review sheet:

- `references/mockups/home-v10.10-prep/home-v10.10-lower-edge-contact-sheet.png`

The review sheet must show V10.9 and the candidate with identical scale and crop:

1. full scene at a realistic 1920 viewport presentation,
2. native lower-edge crop,
3. 4x left corner,
4. 4x center/tabs,
5. 4x right corner,
6. changed-pixel heatmap.

## Hard failure criteria

Stop and report failure instead of connecting the asset if any item remains:

- a continuous dark/green line across the book bottom,
- a flat or blurred cream stripe without paper layering,
- yellow/red/blue glow inside the page block,
- a black rectangular gap behind tape or between tabs,
- tape or tabs that appear detached,
- a left/right corner wedge, tube, or abrupt seam,
- changed pixels outside the envelope,
- a hard mask edge, matte rectangle, repeated clone pattern, or halo.

## Gate A validation

Report only:

1. confirmed failure mechanics,
2. exact reconstruction method,
3. changed-pixel count and bounding box,
4. outside-envelope changed pixels,
5. longest near-black connected run in the page/attachment zone,
6. tab-color contamination test,
7. protected tab-body identity result,
8. full-scene and 4x visual verdict,
9. contact-sheet path,
10. remaining risk.

Do not run the app, browser QA, or `npm run build` in Gate A. Do not commit or push. End with `Gate A complete - awaiting visual approval.`
