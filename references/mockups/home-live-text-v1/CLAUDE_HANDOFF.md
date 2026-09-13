# Home Live Text V1 - Bounded Hierarchy Polish

## Objective

Polish only the live DOM typography over the already approved Home scene.
The scene composition, raster assets, physical shadows, object positions, and
navigation are complete and must remain unchanged.

This is not a scene reconstruction and not an asset-generation phase.

## Why the current screenshot still feels unfinished

1. The title and subtitle are too small for the scale of the notebook and note.
2. The CTA copy has weak contrast and does not read as the primary action.
3. The three desktop shortcut tabs carry long dynamic hints that wrap into tiny,
   fragmented text and weaken their labels.

Reference screenshot:

- `C:\Users\mjwmm\Pictures\Screenshots\스크린샷 2026-09-13 124624.png`

## Hard scope

Allowed source files:

- `frontend/components/HomeDashboard.tsx`
- `frontend/app/globals.css`

Do not edit any other tracked source file unless the build proves it is strictly
required. Do not create or modify any image asset.

## Absolute prohibitions

- Do not modify `home-v10.4-scene-desktop.png` or the V10.5 mobile scene.
- Do not change any `--title-*`, `--sample-*`, `--cta-*`, or `--tab-*`
  positioning/size coordinate.
- Do not change `.home-v10-scene`, its ratio, art width, crop, or scene height.
- Do not add a background, border, box-shadow, drop-shadow, filter, gradient,
  pseudo-element, badge, card, or extra visual wrapper.
- Do not move, resize, recolor, or regenerate the notebook, note, ribbon,
  Shiori, tabs, props, or baked shadows.
- Do not restructure the JSX or change button order, callbacks, routing, auth,
  API calls, SRS, storage, data fetching, or accessibility semantics.
- Do not touch AppShell or Home Nav V1.2.
- Do not make mobile a scaled copy of the desktop typography pass.

## Required implementation

### 1. Desktop title hierarchy

Apply only inside `@media (min-width: 768px)`:

- `.home-v10-title`: `font-size: clamp(16px, 1.45vw, 22px)` and a compact
  `line-height` near `1.22`.
- `.home-v10-subtitle`: `font-size: clamp(10.5px, 0.9vw, 13.5px)` with
  `line-height` near `1.34`.
- Preserve the current two-line title and two-line subtitle clamp.
- The title and subtitle must remain fully inside the existing note safe zone.

### 2. Sample link and CTA

Apply only inside `@media (min-width: 768px)`:

- `.home-v10-sample`: `font-size: clamp(11.5px, 0.9vw, 13.5px)`.
- `.home-v10-cta-content`: `font-size: clamp(12px, 1vw, 15px)`.
- Change CTA foreground to a warm ivory around `#f6eed8`, but verify contrast
  against the real sage ribbon at 1920, 1280, and 1024 before keeping it.
- Keep the existing CTA content box, icon, hit zone, hover scale, and active
  scale unchanged.
- Never use text-shadow to force contrast.

### 3. Stable, compact shortcut copy

Keep the visible labels exactly `단어장`, `복습`, and `덱`.

Replace the current long desktop hint strings with compact state-aware copy:

- Vocab with saved words: `최근 모은 단어 보기`
- Vocab empty: `단어 모으기`
- Review dev/login state: `로그인해 기록 저장`
- Review loading: `복습 확인 중`
- Review due count above zero: `${dueTodayCount}개 복습하기`
- Review with nothing due: `오늘 복습 완료`
- Deck count above zero: `${sharedDeckCount}개 덱 둘러보기`
- Deck empty: `학습 덱 만들기`

Remove the recent Japanese surface word from the visible hint. It produces
unbounded copy and is the direct cause of the broken-looking first tab. Keep
the `recentWords` prop and existing data flow unless removing it is proven safe
and produces no unrelated diff; minimizing the behavioral diff is preferred.

### 4. Desktop shortcut typography

Inside `@media (min-width: 768px)` only:

- Keep every tab hit zone and the baked tab artwork fixed.
- Use a label size around `13px`, hint size around `10px`, and keep the hint at
  a maximum of two lines.
- Preserve the icon circle at `22x22px`; do not enlarge the icon artwork.
- The label must be visually stronger than the hint.
- No text may touch the tape, torn edge, neighboring tab, or tab shadow.
- If the exact requested font sizes do not fit at 1024, reduce only the hint by
  at most `0.5px`. Do not move or enlarge the tab.

### 5. Mobile preservation

The mobile scene and visible icon-only shortcut treatment must remain visually
unchanged at 390, 375, and 320px. The shorter hint text may remain in the
accessibility tree, but no label or hint may become visually exposed on mobile.

## Acceptance sequence

Work in one bounded pass:

1. Capture before screenshots at 1920x960, 1280x960, and 390x844.
2. Apply the typography and compact-copy changes.
3. Capture after screenshots at 1920x960 and 1280x960 first.
4. Make at most one corrective pass for clipping, weak contrast, or collision.
5. Confirm at 1024, 390, 375, and 320.
6. Run `npm run build` once near the end and `git diff --check`.

## Visual acceptance criteria

- The title is the first readable text inside the note, without becoming loud.
- Subtitle remains clearly secondary and does not clip.
- CTA copy is immediately readable on the sage ribbon at normal scale.
- Each shortcut label is readable before its hint.
- All three hints fit within two lines without ellipsis at 1280 and 1920.
- At 1024, no hint may collide or leave the colored tab.
- The Home scene image, crop, physical shadows, and object geometry are pixel
  identical before and after.
- Mobile composition is visually unchanged.
- No horizontal overflow, image 404, or new console warning/error.

## Failure criteria

Fail the phase if any of the following occurs:

- Any scene asset or coordinate changes.
- CTA contrast is achieved using shadow/filter rather than foreground color.
- Tab copy still appears as tiny fragmented text at 1280.
- Text overlaps tape, stitching, torn edges, or adjacent tabs.
- Mobile labels become visible or the mobile scene changes.
- Any Home callback or navigation behavior changes.
- Before/after first impression is effectively identical.

## Required report

1. Exact files and selectors changed
2. Before/after typography values
3. Final compact hint strings and state mapping
4. 1920/1280 visual judgment
5. 1024 fit judgment
6. Mobile unchanged proof at 390/375/320
7. Home click preservation results
8. Build, diff, overflow, 404, and console results
9. Screenshot paths
10. Remaining risks

Do not commit or push. Stop after reporting for approval.
