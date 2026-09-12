# Home Nav V1.1 Cross-Scene Seam Repair

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-nav-scene-seam-fix`

## Mission

Repair the integration between the approved Home Nav V1.1 paper strip and every desktop scene. The navigation asset itself is approved. The current failure is that older scene-edge decorations and rounded photo frames protrude from behind the new strip, creating double borders and leftover floating tabs on Reading, Deck, Stats, and potentially other screens.

This is a cross-scene seam repair, not another navigation redesign.

## Current evidence

Review these screenshots before editing:

- `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 011700.png` - Home
- `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 011709.png` - Reading
- `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 011715.png` - Deck
- `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 011720.png` - Stats

The Reading and Deck screenshots clearly show old cream paper tags protruding below the new navigation paper edge. Scene top corners and the viewport-wide torn paper strip also form two unrelated boundaries.

## Mandatory three-line failure analysis

State these facts before implementation:

1. Home Nav V1.1 is 50px high with a 56px paper asset, so only 6px of the next scene is covered.
2. Legacy scene title tags use negative vertical transforms or negative top positions, causing them to protrude behind the new strip.
3. Desktop scene images still have rounded top corners, so the viewport-wide torn paper edge and the capped scene frame create a visible double boundary.

## Approved structure to preserve

- Keep `frontend/public/brand/decor/home-nav-v1.1/` unchanged unless a real asset defect is demonstrated. Do not regenerate or recolor the approved assets.
- Keep the desktop toolbar at exactly 50px.
- Keep the paper image at 56px with its 6px overlap.
- Keep every desktop nav slot at exactly 106x36px.
- Keep the active linen at 98x36px.
- Keep current divider dimensions and opacity.
- Keep nav order, callbacks, icons, live labels, `aria-current`, feedback, account menu, keyboard focus, and mobile drawer behavior.
- Keep Home V10 scene layout and assets unchanged.

## Old structures to remove or role-redefine

Audit all seven desktop screens before editing. At minimum inspect and resolve:

- `ReadingTab.tsx`: `.reading-scene-v2-eyebrow`
- `SharedDeckSection.tsx`: `.shared-scene-v2-eyebrow`
- `InfoSection.tsx`: `.stats-scene-v2-eyebrow`
- `AnalyzeSection.tsx`: `.classify-v2-title-tag`
- `VocabSection.tsx`: `.vocab-v3-title-tag`, including its desktop `top:-3%`
- Review/Study screen: inspect its topmost scene children for any negative `top`, negative `translateY`, hanging tab, tape, or title decoration.

These labels are decorative scene titles duplicated by the active global navigation. On desktop, remove the redundant DOM element and its obsolete CSS when removal does not affect functionality or accessibility. If a label is genuinely needed inside its scene, reposition it fully inside the photographed object with no negative top/translate and prove it does not touch the navigation seam.

Do not merely hide protrusions behind a larger `z-index`, `overflow:hidden`, opaque rectangle, gradient, or extra mask. Remove or redefine the obsolete structure at its source.

## Unified desktop seam contract

At `min-width:1024px`, every scene must follow one physical relationship:

1. The 50px toolbar owns the viewport top.
2. Its 56px paper asset overlaps the next scene by exactly 6px.
3. Scene content begins immediately at toolbar layout y=50px with no margin or blank strip.
4. The paper's torn lower edge is the only visible boundary between navigation and scene.
5. No scene decoration may extend above its own scene plane.
6. Capped scene images must not introduce rounded top-left/top-right corners below the torn edge. Preserve their existing lower corner radii only.

Expected desktop media treatment for framed scenes is equivalent to:

```css
border-radius: 0 0 26px 26px;
```

Use each scene's existing lower radius where it differs; do not force 26px universally. The requirement is zero top radius and preserved lower radius.

Inspect at least these classes:

- `.reading-scene-v2-media-img`
- `.shared-scene-v2-media-img`
- `.stats-scene-v2-media-img`
- `.classify-v2-scene`
- the desktop Vocab scene/frame image
- the desktop Review/Study scene/frame image

Do not flatten mobile scene corners. This seam contract applies only at `min-width:1024px`.

## Scope guardrails

Allowed:

- Removing redundant decorative title-tag spans and their now-unused imports/comments.
- Removing corresponding obsolete CSS.
- Desktop-only top-corner normalization for scene frames.
- Minimal desktop spacing correction required to make scene y=50 meet the paper overlap.

Forbidden:

- Navigation asset redesign or another density pass.
- Increasing toolbar height back to 56px.
- Enlarging the paper overlap just to cover the defects.
- CSS masks, opaque cover strips, gradients, box shadows, filters, or clipping used to conceal old elements.
- Moving, scaling, recoloring, or regenerating scene assets.
- Editing Home V10 composition or its overlay coordinates.
- Editing content inside the photographed scenes beyond the top seam.
- Changing callbacks, routing, APIs, storage, SRS, auth, feedback payloads, data policy, or backend code.
- Accessing Neon or production data.
- Changing mobile navigation or mobile scene composition.
- Committing or pushing.

## Implementation sequence

1. Audit all seven desktop tabs and list every element that enters the first 20px of scene space or uses negative top/translate positioning.
2. Capture a pre-fix 1280 contact sheet of Home, Reading, Review, Vocab, Deck, Classify, and Stats focused on the first 120px below the viewport top.
3. Remove or reposition obsolete hanging scene titles at their source.
4. Normalize desktop scene top corners to zero while retaining lower corners.
5. Verify the toolbar and scene meet at one stable y-coordinate without changing approved nav geometry.
6. Capture an after contact sheet using the same viewport and crop.
7. Allow one corrective pass only if a protrusion or double edge remains.

## Desktop acceptance criteria

At 1280x960 and 1024x768, cycle through all seven tabs and require:

- Toolbar rect is `[0, 0, document.documentElement.clientWidth, 50]`.
- Every nav slot remains 106x36px in inactive and active states.
- Paper lower edge remains continuous across the viewport.
- Scene starts directly beneath/behind the 6px torn-paper overlap.
- No cream tag, Shiori mark, tape fragment, rounded photo corner, or old title decoration appears behind the navigation.
- No second horizontal border runs parallel to the torn paper edge.
- Switching tabs does not move the toolbar, paper edge, or active slot geometry.
- Home and every capped scene read as attached to the same navigation sheet despite different scene widths.

The vertical scrollbar may reduce `clientWidth`; compare the toolbar to `clientWidth`, not `window.innerWidth`.

## Mobile preservation

At 390x844, 375x812, and 320x700:

- Mobile drawer and hamburger behavior remain unchanged.
- Existing mobile scene corner treatment and internal scene labels remain unchanged unless removal is structurally shared and verified harmless.
- `scrollWidth === clientWidth`.
- No new overlap or missing title is introduced.

If desktop-only removal is required while mobile needs the label, preserve the DOM and use a clear breakpoint-specific role. Do not duplicate interactive behavior.

## Functional and technical QA

- Real-click all seven navigation tabs.
- Open/close feedback and account UI.
- Check keyboard focus and `aria-current`.
- Check image 404s and new console errors.
- Run `npm run build` once, near the end.
- Run `git diff --check`.
- Confirm no backend/API/auth/SRS/storage files changed.
- Stop all local frontend/backend/browser processes after QA.

## Required report

1. Removed/redefined legacy top-edge structures
2. Root cause confirmed per affected tab
3. Final unified seam rule
4. Files changed
5. 1280/1024 seven-tab visual verdict
6. Mobile preservation verdict
7. Navigation geometry measurements
8. Functional/build/404/console/diff results
9. Before/after contact-sheet paths
10. Remaining risks

End without committing or pushing.
