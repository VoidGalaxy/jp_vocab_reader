# Home V10.10 Lower-Edge Physical Rebuild

## Current failure in three lines

1. The lower green cover edge reads as a wavy inpaint seam rather than a thin cloth-wrapped lip.
2. The cream page block is flat and blurred, with yellow/red/blue contamination above the tabs and black rectangular voids between them.
3. Tape, tabs, page thickness, and cast shadow use different contact logic, so the tabs appear suspended below the notebook.

## Phase goal

Rebuild the notebook's complete lower physical stack once: front-cover lip, page block, tape attachments, three tab roots, and the shared desk-contact shadow. This is an asset reconstruction phase, not another local blur, recolor, or CSS shadow pass.

## Fixed source and scope

- Production source: `frontend/public/brand/decor/home-v10.9/home-v10.9-scene-desktop.png`
- Source SHA-256: `59103B4E54A74DA974A542ABBA5F9AC4DDAD8EE29D7B490338B4B1D19FC32606`
- Source size: 1888 x 833 RGB
- Editable envelope: `x=500..1435, y=570..750`
- Reference crop: `home-v10.10-lower-edge-source-crop.png`
- 2x diagnostic crop: `home-v10.10-lower-edge-source-2x.png`
- User-marked evidence: `home-v10.10-user-marked-reference.png`

Everything outside the editable envelope must remain pixel-identical to V10.9.

## New physical stack

From top to bottom, the result must read as one object under one light:

1. **Front-cover lip**: 6-10 native pixels of dark forest-green woven cloth. It may taper at the corners but must not become a continuous black or green outline.
2. **Page block**: 24-32 native pixels of warm ivory paper with restrained horizontal page layering, gentle luminance variation, and uninterrupted perspective from left to right.
3. **Tape attachments**: three cream tape pieces visibly contacting the page block. Their shadows must be short and local, never rectangular cavities.
4. **Tab roots and bodies**: retain the approved yellow, coral, and blue body silhouettes, spacing, size, and color. Only the hidden root/contact transition may be reconstructed.
5. **Desk-contact shadow**: one warm-brown lighting system. The notebook receives a broad soft shadow; each tab receives a smaller attached shadow. No black bar and no floating halo.

## Protected geometry

- Notebook position, scale, outer silhouette, top cover, emboss, note, CTA ribbon, Shiori, bookmark, desk, props, and all text safe zones are locked.
- Preserve the visible tab bodies below their attachment line:
  - yellow approximately `x=819..957, y=666..752`
  - coral approximately `x=976..1113, y=666..752`
  - blue approximately `x=1134..1271, y=666..752`
- Preserve tab color and torn-paper outlines. Rebuilding the top roots and tape contact is allowed only where needed to remove the current gaps and bleed.

## Visual acceptance criteria

- The page block is the dominant readable thickness; it must not look like rubber, plastic, or a blurred stripe.
- No yellow, coral, or blue glow may contaminate the page block above a tab.
- No black rectangular void may remain behind or between tab roots.
- No near-black connected horizontal run longer than 40 native pixels may remain inside the reconstructed page/attachment zone.
- The cover lip must retain textile grain and must not form a constant-width line.
- Left and right corners must taper into the existing side volumes without a wedge, tube, or abrupt tonal step.
- Tape and tabs must look physically attached at 100% scale, not only in an enlarged crop.
- No blur patch, clone repetition, hard mask edge, gray halo, or rectangular matte is acceptable.

## Gate sequence

### Gate A: target asset only

- Produce one coherent full-scene candidate at 1888 x 833.
- Do not edit `HomeDashboard.tsx`, `globals.css`, or any production reference.
- Save the candidate under this prep folder, not `frontend/public`.
- Produce one contact sheet containing V10.9 and the candidate at full-scene scale, the native lower-edge crop, 4x left/center/right crops, and a diff heatmap.
- Report changed-pixel containment, near-black runs, page-color contamination, and protected-region identity.

### Gate B: production connection after approval

- Move the approved candidate into a new versioned production folder without re-encoding.
- Change only the desktop scene URL in `HomeDashboard.tsx`.
- Keep mobile V10.5, CSS geometry, coordinates, callbacks, APIs, auth, SRS, storage, and routing unchanged.
- Verify 1920/1280/1024 and mobile 390/375/320, then run one production build.

## Explicitly rejected methods

- Additional CSS shadow, filter, gradient, pseudo-element, or overlay patch
- Editing only the darkness of the existing band
- Reusing the V10.8/V10.9 masks as the final geometry
- Blurring tab colors into the page to simulate reflected light
- Hiding defects with black contact bars or oversized ambient shadow
- Repainting the entire scene when only the bounded lower structure is allowed to change
