# Home Physical Navigation Strip Replacement

Implementation status: Gate A and Gate B are complete on `codex/home-nav-embossed-linen`. This handoff is retained as the design contract and must not be re-executed against the completed branch.

Project: `C:\JV_Project\jp_vocab_reader`

Target: desktop Home/app navigation in `frontend/components/AppShell.tsx` and the related desktop block in `frontend/app/globals.css`.

Read first, and only these unless a reproduced problem requires more:

1. `references/mockups/home-nav-prep/home-nav-target.png`
2. `references/mockups/home-nav-prep/NAV_DESIGN_CONTRACT.md`
3. `references/mockups/home-nav-prep/HOME_DESIGN_PLAYBOOK.md`
4. `frontend/components/AppShell.tsx`
5. The `.app-toolbar*` rules in `frontend/app/globals.css`

## Current failure in three lines

The desktop toolbar is a translucent web strip, so it does not share the Home scene's physical stationery language.
Inactive tabs have almost no material separation, while the orange active pin is an unrelated accent.
Direct CSS restyling without approved assets would repeat the earlier Home shadow and texture failures.

## Goal

Replace the desktop toolbar presentation with the approved ivory paper strip, faint blind-embossed dividers, and one forest-green sewn linen active patch shown in `home-nav-target.png`.

## Structure to remove or redefine

- Remove `.app-toolbar-pin` from the desktop navigation markup; do not hide it and leave dead JSX.
- Redefine `.app-toolbar` from translucent browser chrome into the paper-strip host.
- Redefine `.app-toolbar-link-active` from colored text plus pin into the linen-patch state.
- Keep the existing `navItems` map, callbacks, icons, labels, `aria-current`, feedback slot, account slot, hamburger, and drawer behavior.

## Mandatory two-gate execution

Gate A candidate assets have now been prepared under `frontend/public/brand/decor/home-nav-v1/` and are not wired into production. Do not regenerate or modify them unless the user rejects the text-free preview.

### Gate A: assets and text-free preview only

Create the four assets required by `NAV_DESIGN_CONTRACT.md` under `frontend/public/brand/decor/home-nav-v1/`. Build a text-free 1280px preview using those exact assets. Inspect alpha edges at high magnification and at rendered scale. Stop and report the preview path, asset dimensions, stretch/repeat method, and any risk. Do not edit production TSX or CSS before approval.

### Gate B: integration after approval

Wire the approved assets into the existing desktop navigation. Live DOM text/icons must align over asset safe zones. The target image controls material, rhythm, active-state weight, and divider subtlety; the current toolbar does not.

## Hard constraints

- Desktop only at `min-width: 1024px`; mobile/tablet drawer must remain unchanged.
- No CSS gradient, border trick, or generic box-shadow may substitute for paper, linen, stitches, deckled edge, or embossed divider assets.
- No text or icon may be baked into an image.
- No orange/coral marker remains.
- No layout shift when the active tab changes.
- No backend, API, auth, routing, SRS, storage, Home scene, or tab-content changes.
- A small visual diff or an unchanged first screenshot is failure.
- Use at most one corrective pass after screenshot review. If it still misses, stop and identify the missing asset decision.

## Final validation after Gate B

Check 1280 and 1024 deeply, then 390, 375, and 320 as preservation smoke tests. Verify no horizontal overflow, no asset 404, no new console error, active-state switching across every tab, feedback/account access, keyboard focus, and one final build. Do not access Neon or production data.

Report briefly in this order:

1. Removed or redefined old structure
2. Asset set and alpha/stretch validation
3. Before/after first impression
4. Desktop active/inactive/hover/focus judgment
5. Mobile preservation
6. Behavior preservation
7. Build/browser QA
8. Remaining risks

Do not commit or push.
