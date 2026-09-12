# Home Nav V1.2 Edge Finish - Gate B Wiring

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-nav-edge-finish`

## Approved candidate

Candidate B from Gate A is approved.

Source candidate:

`frontend/public/brand/decor/home-nav-v1.2/home-nav-paper-strip-b.png`

It is the only candidate allowed into production.

## Mission

Wire Candidate B without changing navigation geometry or any tab scene. Preserve the 50px toolbar and the paper body's existing visual bottom position. The extra 8px in the 64px asset is transparent shadow padding, not additional paper thickness.

## Production asset cleanup

Before wiring:

1. Rename Candidate B to `home-nav-paper-strip.png` without re-encoding or changing bytes.
2. Remove Candidate A and Candidate C from the production asset folder.
3. Remove `_paper-body-debug.png` from the production asset folder.
4. Move the contact sheet out of `frontend/public/` to:
   `references/mockups/home-nav-prep/home-nav-v1.2-edge-contact-sheet.png`
5. Keep `frontend/public/brand/decor/home-nav-v1.2/` limited to:
   - `home-nav-paper-strip.png`
   - `ASSET_MANIFEST.md`
6. Update the manifest to record Candidate B as selected and wired, with the final filename and unchanged SHA-256.

Do not keep superseded candidates or debug assets in the public runtime tree.

## CSS wiring

Change only the desktop paper-strip reference and its transparent canvas extent in `frontend/app/globals.css`.

Current visual geometry:

- toolbar host: 50px
- paper body: first 56px of the asset
- paper body visual overlap: 6px
- exterior shadow padding: rows 56-63
- total raster canvas: 64px

Wire the pseudo-element so its total box is exactly 64px high:

- keep `top:0`
- keep left/right at `0`
- set the bottom extent to `-14px` relative to the 50px toolbar
- render the background at `100% 64px`
- point only the paper background URL to `/brand/decor/home-nav-v1.2/home-nav-paper-strip.png`

The opaque paper still ends around the same 56px contour as V1.1. Only the exterior shadow may occupy the additional rows. Do not move the paper body down, rescale it to 56px, crop it, or increase toolbar height.

Preserve the V1.1 active linen and divider URLs unchanged.

## Forbidden

- Any change to `AppShell.tsx` or component JSX.
- Any change to toolbar height, slot size, active patch size, icon size, font size, first-tab position, divider position, feedback, or account geometry.
- CSS `box-shadow`, `filter`, `drop-shadow`, gradient, border, outline, mask, clip-path, or pseudo-element added to supplement the raster edge.
- Editing Home or any tab scene.
- Reintroducing removed scene eyebrows/title tags.
- Changing mobile navigation.
- Keeping A/C/debug files in `frontend/public`.
- Re-encoding or visually modifying Candidate B after approval.
- Backend/API/auth/SRS/storage changes or Neon access.
- Commit or push.

## Visual QA

Start with fresh navigation at 1280x960 and inspect at 100% scale:

1. Home warm wood
2. Review mint board
3. Reading cream open-book page

For all three, capture a full screenshot and a native-scale crop of the first 90px.

Pass only if:

- the previous continuous gray/black contour is gone
- the torn paper fiber edge remains visible
- one short warm shadow fades below the edge
- there is no double line
- there is no white halo
- there is no straight uniform band
- there is no gap between paper and scene
- the shadow does not clip at its bottom
- scene content does not visibly move compared with V1.1

Then smoke-check all seven tabs at 1280 and 1024 for seam consistency. Verify no old protruding title tags return.

## Geometry and browser checks

- Toolbar: `[0,0,document.documentElement.clientWidth,50]`
- Every desktop slot: `106x36px` before and after activation
- Active linen: visually 98x36px
- Tab x coordinates unchanged across navigation
- `scrollWidth === clientWidth` at 1280, 1024, 390, 375, and 320
- Mobile does not request the V1.2 desktop paper asset
- No V1.1 paper-strip request remains on desktop
- V1.1 active-linen and divider requests remain valid
- No image 404 or new console error
- Feedback/account and all seven nav clicks still work

## Final validation

- Run `npm run build` once near the end.
- Run `git diff --check`.
- Confirm only `globals.css`, the final V1.2 asset folder, the moved contact sheet, and the two handoff documents are changed/untracked.
- Stop all local servers and browser processes.

## Report

1. Selected asset and hash preservation
2. Removed candidate/debug files
3. Final CSS geometry
4. Home/Review/Reading edge judgment
5. Seven-tab seam result
6. Desktop/mobile geometry result
7. Click/404/console/build/diff result
8. Screenshot paths
9. Remaining risk

Do not commit or push. Stop for approval.
