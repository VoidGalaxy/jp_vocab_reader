# Phase 195 Home Target Assets / Implementation Brief

## Current Failure In 3 Lines

- The current Home screenshot reads as a large photo background with separate PNG UI pieces placed on top.
- Phase 194 pulled the camera too far back: the shortcut tabs became too small, while the notebook cover still feels empty.
- Repeated CSS coordinate changes are no longer the right next move; the target mockup and material assets must become the source of truth.

## Source Of Truth

- Desktop target mockup: `references/mockups/home-phase195-target-mockup.png`
- Mobile target mockup: `references/mockups/home-phase195-target-mobile.png`
- Current failed reference screenshot: `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-08-30 102740.png`

Use the target mockups for scale, overlap, grounding, and material direction. Do not copy generated placeholder text; all UI copy must remain live DOM text.

## New Scene Silhouette

Home should read as one warm oak desk scene with a sage fabric notebook as the central object. The title note and CTA ticket overlap the upper-left notebook cover, while the shortcut tabs tuck under the lower notebook edge as physical tabs. The empty cover area is intentional because of a subtle embossed open-book/leaf mark, not because the UI is unfinished.

Desktop should feel like a photographed desk composition, not a zoomed crop and not a tiny UI cluster. Mobile should be a separate vertical desk-photo composition, not a scaled desktop layout.

## Assets Generated For Phase 195

Recommended to use:

- `frontend/public/brand/decor/home-v4/home-v4-desk-surface-desktop.png`
  - Opaque desktop background plate.
  - Center safe area is clean; props stay near outer edges.
- `frontend/public/brand/decor/home-v4/home-v4-desk-surface-mobile.png`
  - Opaque mobile background plate.
  - Central vertical safe area is clear for notebook/note/CTA/tabs.
- `frontend/public/brand/decor/home-v4/home-v4-shortcut-tab-rail-candidate.png`
  - Transparent PNG, alpha verified at corners.
  - Use as one tab rail asset if replacing the three independent shortcut tab PNGs.
- `frontend/public/brand/decor/home-v4/home-v4-cover-emboss-mark.png`
  - Transparent PNG, alpha verified at corners.
  - Use as a low-opacity overlay on the existing notebook cover.
- `frontend/public/brand/decor/home-v4/home-v4-cta-ticket.png`
  - Transparent PNG, alpha verified at corners.
  - Use only if its heavier baked shadow can be controlled with CSS sizing/filter. Existing `home-v3-cta-stamp.png` is still acceptable if this feels too heavy.

Do not wire directly:

- `frontend/public/brand/decor/home-v4/home-v4-notebook-cover-embossed.png`
- `frontend/public/brand/decor/home-v4/home-v4-notebook-cover-embossed-extracted.png`

Reason: both notebook-cover candidates failed alpha verification; their checkerboard/background is opaque. They are reference-only. The safer implementation path is existing `home-v3-notebook-cover.png` plus `home-v4-cover-emboss-mark.png` overlay.

## Old Structure To Delete Or Role-Redefine

- Stop treating the three shortcut buttons as three separately positioned cards. Either replace them with one `home-v4-shortcut-tab-rail` image anchor plus DOM hit zones, or keep the current button DOM but make the rail geometry drive their placement.
- Stop using camera-distance changes as the main correction tool. Phase 194 made the whole cluster too small; recover tab size and foreground hierarchy using the target mockup.
- Stop relying on notebook-empty-space acceptance alone. Add the emboss overlay so the right cover area reads as branded material, not unused space.
- Stop using the current background photo if it competes with the foreground. Replace it with the new background plates.

## Implementation Direction

- Replace Home body background URLs with the new `home-v4-desk-surface-*` plates.
- Keep the existing transparent notebook cover unless a later clean cutout is generated; add `home-v4-cover-emboss-mark.png` as an absolutely positioned overlay on the lower-right cover.
- Make shortcut tabs significantly larger than the Phase 194 screenshot, closer to the desktop/mobile target mockups.
- Prefer a single rail-level layout anchor for the shortcut tabs. Text and icons stay DOM and must sit inside safe zones.
- Keep Home Shiori removed.
- Keep callbacks, routing, storage, SRS, API, auth, shared-deck, and feedback payloads unchanged.

## Failure Criteria

- First screenshot still reads as PNG pieces floating on a photo.
- Shortcut tabs remain tiny or read as cards lying below the notebook rather than tabs tucked under it.
- Notebook cover stays visually empty without an intentional mark.
- Background props compete with the title, CTA, or tabs.
- Live text crosses tape, torn edges, shadow, notebook edge, or busy photo details.
- Mobile becomes a full-width button stack or a desktop shrink.
- Implementation changes only numeric CSS values and does not use the target assets.

## Bounded QA

- Target Home deep QA only.
- Other tabs smoke QA only: open, overflow, console, obvious scene breakage.
- Check 1280 and 390 first. Check 1024, 375, and 320 for final candidate.
- `scrollWidth === clientWidth`
- console error/warning count
- unexpected failed request/image 404 count
- real clicks: CTA, sample, vocab shortcut, review shortcut, deck shortcut
- `npm run build` once near the end
- `git diff --check`

## Claude Handoff Prompt

Phase 195 - Home Target Asset Replacement / Material Quality Pass

Project: `C:\JV_Project\jp_vocab_reader`
Target tab: Home only

Read first:
- `frontend/components/HomeDashboard.tsx`
- `frontend/app/globals.css`
- `references/mockups/home-phase195-implementation-brief.md`
- `references/mockups/home-phase195-target-mockup.png`
- `references/mockups/home-phase195-target-mobile.png`

One-line history: reskin failed; this phase is target-mockup-driven scene replacement.

Current failure in 3 lines:
- Current Home still reads as separate PNG UI pieces on a photo background.
- Phase 194 pulled the camera too far back, making shortcut tabs too small and the scene feel underfilled.
- The notebook cover lacks intentional brand/detail, so empty space reads as unfinished.

Goal:
Rebuild Home around the Phase 195 target mockups and new assets. This is not another coordinate-only pass.

Must use or evaluate:
- `frontend/public/brand/decor/home-v4/home-v4-desk-surface-desktop.png`
- `frontend/public/brand/decor/home-v4/home-v4-desk-surface-mobile.png`
- `frontend/public/brand/decor/home-v4/home-v4-shortcut-tab-rail-candidate.png`
- `frontend/public/brand/decor/home-v4/home-v4-cover-emboss-mark.png`
- `frontend/public/brand/decor/home-v4/home-v4-cta-ticket.png`

Do not wire directly:
- `frontend/public/brand/decor/home-v4/home-v4-notebook-cover-embossed.png`
- `frontend/public/brand/decor/home-v4/home-v4-notebook-cover-embossed-extracted.png`

Reason: both notebook-cover candidates have opaque checkerboard/background. Use existing `home-v3-notebook-cover.png` plus the new emboss overlay instead.

New silhouette:
Warm oak desk background, sage notebook as the main object, title note and CTA physically biting into the notebook upper-left, shortcut tabs large enough to read and tucked under the notebook lower edge, privacy as a small loose sticker. The right notebook cover should feel intentionally quiet because of a subtle emboss mark.

Required structural change:
Do not end with only CSS number changes. Role-redefine the shortcut area around a rail-level asset/anchor, or explain why the existing DOM can still be made target-faithful. The tab geometry should be anchored to the notebook edge, not independently floated under it.

Preserve:
CTA, sample, vocab/review/deck shortcut handlers, AppShell navigation, account, feedback, drawer, API/storage/SRS/auth/shared-deck/feedback payloads. Keep all visible UI copy as DOM text. No Shiori on Home.

Failure:
If the first screenshot still looks like current Home with slightly different sizes, fail. If tabs are tiny, card-like, or detached from the notebook edge, fail. If the notebook cover stays blank, fail. If mobile is a desktop shrink or full-width button stack, fail.

QA:
Home deep QA at 1280 and 390 first; final candidate at 1024, 375, 320. Other tabs smoke only. Run `npm run build` once near the end and `git diff --check`. Report pass/fail/counts, not raw logs.

Report:
1. Deleted or role-redefined Home structure
2. Assets used and assets rejected
3. New scene silhouette
4. Desktop before/after judgment
5. Mobile before/after judgment
6. Function preservation
7. Failure criteria pass/fail
8. Build/browser QA
9. Remaining risks

Do not commit or push.
