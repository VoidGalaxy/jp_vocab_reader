# Home Nav V1.1 Density and Grounding Pass

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-nav-density-pass`

Current screenshot: `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 002030.png`

Approved direction reference: `references/mockups/home-nav-prep/home-nav-target.png`

Read only these files first:

1. `frontend/components/AppShell.tsx`
2. The desktop `.page`, `.app-shell-content`, and `.app-toolbar*` rules in `frontend/app/globals.css`
3. `frontend/public/brand/decor/home-nav-v1/ASSET_MANIFEST.md`
4. `references/mockups/home-nav-prep/NAV_DESIGN_CONTRACT.md`
5. The current screenshot and approved direction reference above

Do not perform broad repository archaeology.

## Current failure in three lines

The 56px paper strip and 40px linen patch are too thick and visually heavy compared with the Home scene.
The paper is too bright, the embossed separators read as gray rules, and the active patch dominates the inactive labels.
The material system is correct, so replacing the structure or applying arbitrary CSS-only scaling would introduce new regressions.

## Goal

Produce a thinner, warmer, quieter Home Nav V1.1 while preserving the full-width stable frame and the physical paper/linen design.

## Locked structure that must not change

- Keep `.page` as the viewport-wide desktop shell and `.app-shell-content` as the per-screen content-width owner.
- On every desktop tab, `.app-toolbar` must remain `x:0`, `y:0`, and exactly the viewport width.
- Keep the current seven-tab order, `navItems`, callbacks, icons, live Korean labels, `aria-current`, feedback, and account behavior.
- Keep the orange pin removed. Do not reintroduce `.app-toolbar-pin` markup or styling.
- Keep each navigation slot width fixed at 106px in every state. The active asset may shrink inside the slot, but activating a tab must never move any neighboring tab.
- Keep the mobile/tablet hamburger and drawer unchanged below 1024px.

## Mandatory asset-first execution

Do not overwrite `home-nav-v1`. Create a sibling folder:

`frontend/public/brand/decor/home-nav-v1.1/`

Derive the new assets deterministically from the approved V1 assets. Do not ask an image model to redraw them.

Create:

1. `home-nav-paper-strip.png`
   - Canvas: 1920×56 RGBA.
   - Intended toolbar host height: 50px, with the lower 6px extending over the scene.
   - Preserve the current paper fibers and deckled silhouette.
   - Make the paper approximately 4–6% warmer/darker so it does not outshine the notebook scene.
   - Bake a narrow warm contact shade immediately beneath the deckled edge: strongest within 1px, fully faded by 3px.
   - No rectangular shadow, blur band, gray halo, gradient-generated paper, or opaque background outside the silhouette.

2. `home-nav-active-linen.png`
   - Canvas: 98×36 RGBA.
   - Downsample from the current V1 patch; preserve the dark forest-green linen and cream stitching.
   - Keep stitching approximately 1 rendered pixel and all four corner alpha values at zero.
   - No new shadow, outline, recolor, text, or icon.

3. `home-nav-divider-emboss.png`
   - Canvas: 10×30 RGBA.
   - The actual pressed mark should occupy only 14–16px vertically.
   - Reduce visible contrast by approximately 40% from V1.
   - It must read as a shallow paper highlight/shade pair, not ink or a gray rule.

4. `home-nav-asset-preview.png`
   - 1280px-wide text-free assembly at real rendered scale.
   - Show the 50px strip, one 98×36 active patch inside a 106px slot, and all dividers.

Add an `ASSET_MANIFEST.md` recording source assets, dimensions, alpha checks, hashes, and the exact deterministic transforms.

## Gate A: stop before production code

First create only the V1.1 assets and text-free preview. Inspect the preview at 100% scale and magnify all alpha edges. Report:

- preview path
- four asset dimensions
- paper edge/contact-shade result
- active-patch stitch result
- divider contrast result
- corner alpha and matte/halo checks

Do not edit `AppShell.tsx` or `globals.css` until the user approves Gate A.

## Gate B: integration after approval

After approval, wire only the V1.1 assets into the existing desktop rules:

- Toolbar host height: 50px.
- Paper pseudo-layer: 56px total, extending 6px below the host over the scene.
- Navigation slot: 106×36px, still fixed in all states.
- Active background: centered 98×36px V1.1 linen asset.
- Icon: 15px. Label: 12.5px, weight 700, letter-spacing 0.
- First tab left edge: approximately 20px at 1280 and 1024.
- Divider: use the V1.1 image at 10×30px; do not compensate with CSS opacity, borders, or gradients.
- Align feedback/account controls to the same 36px visual row without changing their behavior.

## Forbidden methods and outcomes

- No CSS-only material recreation, filter, gradient, box-shadow, drop-shadow, or generic border pretending to be paper, linen, stitching, embossing, or contact shade.
- No generated redraw of the approved assets.
- No structural rollback of the full-width frame fix from commit `427b6ba`.
- No tab-dependent toolbar width, height, x-position, button width, or button x-position.
- No orange/coral marks, individual pills for inactive tabs, full-height separators, baked text/icons, or mobile drawer changes.
- No edits to backend, API, auth, routing, SRS, storage, Home scene assets, or tab content.
- A screenshot that looks nearly identical in thickness and visual weight to the current screenshot is failure.

## Final validation after Gate B

Use real browser geometry, not screenshot dimensions alone.

- 1280×800 and 1024×768: cycle through all seven tabs and record toolbar `[x,y,width,height]` plus every slot `[x,width,height]`.
- Expected toolbar on every desktop tab: `[0,0,viewportWidth,50]`.
- Expected slot size in every state: `[106,36]`, with identical x positions across all tabs.
- Confirm the paper edge visibly overlaps the scene by 6px with no empty gap.
- Compare Home and Reading screenshots directly for identical navigation framing.
- 390×844, 375×812, and 320×700: existing hamburger/drawer only, no V1.1 asset request and no horizontal overflow.
- Check image 404s, new console errors, keyboard focus, feedback/account access, and all seven tab clicks.
- Run `npm run build` once near the end and `git diff --check`.
- Use no Neon or production database.

Allow one corrective pass after screenshot judgment. If the target still misses, stop and identify the exact asset decision instead of entering repeated CSS adjustments.

Report briefly in this order:

1. Superseded V1 measurements
2. V1.1 asset derivation and alpha validation
3. Before/after first impression
4. Desktop thickness and frame stability
5. Divider/icon/active-state judgment
6. Mobile preservation
7. Behavior preservation
8. Build/browser QA
9. Remaining risks

Do not commit or push.
