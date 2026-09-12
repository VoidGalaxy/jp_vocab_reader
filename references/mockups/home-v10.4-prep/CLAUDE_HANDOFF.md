# Home V10.4 Wide Crisp Scene Integration

## Objective

Replace only the desktop Home scene with the approved V10.4 candidate. Fix the
current top/bottom crop and soft-looking material detail without redesigning the
approved composition or touching mobile behavior.

## Three-line failure analysis

1. V10.3 desktop art is 1774x887 (2:1), while the 1920x960 content plane is
   roughly 2.14:1, so width-fill crops about 30px from both the top and bottom.
2. The 1774px source is enlarged to about 1914px, softening book cloth, paper
   edges, wood grain, and small props.
3. Coordinate-only CSS changes cannot recover cropped pixels or source detail;
   the approved high-resolution scene must become the desktop source plane.

## Approved source

- `references/mockups/home-v10.4-prep/home-v10.4-wide-candidate-v1.png`
- Exact dimensions: 1888x833, opaque PNG.
- This is the only approved V10.4 candidate. Do not regenerate, reinterpret,
  filter, sharpen, resize, crop, or overwrite it.
- The rejected second generation is intentionally absent and must not be
  recreated or used.

## Required implementation

1. Copy the approved source byte-for-byte to:
   `frontend/public/brand/decor/home-v10.4/home-v10.4-scene-desktop.png`.
2. Add a concise `ASSET_MANIFEST.md` recording the source, dimensions, desktop-
   only role, and SHA-256 equality between source and production copy.
3. In `HomeDashboard.tsx`, wire only the desktop `<source>` to V10.4. Keep the
   mobile `<img>` on the existing V10.3 mobile asset. Do not change JSX
   structure, Korean DOM text, icons, callbacks, conditions, or routing.
4. In the desktop media rule, set:
   - `--scene-art-ratio: 1888 / 833`
   - `--scene-art-width: max(100vw, calc(226.65svh - 145.06px))`
   This keeps the art plane height equal to `calc(100svh - 64px)` and allows
   only horizontal desk-margin crop. Do not use `object-fit: cover`, filters,
   transforms independent of the overlay plane, or additional scene layers.
5. Re-measure the desktop title, sample, CTA hit/content, vocabulary, review,
   and deck zones directly from the 1888x833 candidate. Replace every desktop
   V10.3 coordinate as one atomic set. Do not reuse or estimate from the old
   1774x887 percentages.
6. Keep all mobile image paths, ratio math, and mobile coordinates unchanged.

## Locked visual invariants

- Preserve the candidate's notebook size, near-center placement, dark forest-
  green color, paper/cloth/wood sharpness, Shiori pose, CTA, three tabs, props,
  and baked shadows exactly.
- No CSS `filter`, `drop-shadow`, `box-shadow`, gradient, pseudo-element shadow,
  separate prop image, or runtime color correction.
- All text and icons remain live DOM content and must fit the blank surfaces.
- Do not modify backend, API, auth, SRS, storage, database, or other tabs.

## Failure criteria

- Any top/bottom crop of the notebook, its contact shadow, or tab shadows.
- V10.3 desktop URL still requested, or V10.4 mobile replacement attempted.
- Scene image and overlay plane use different ratio, size, center, or transform.
- Live text misses its painted surface or overlaps stitching/torn edges.
- New blur, halo, matte, black bar, CSS shadow, horizontal overflow, or 404.
- Any functional or unrelated code change.

## Bounded workflow

1. Inspect only `HomeDashboard.tsx`, the Home V10 CSS block, this handoff, and
   the approved candidate.
2. Implement once. First browser judgment at 1920x960 and 1280x960.
3. Allow one coordinate correction only when live DOM content visibly misses a
   painted safe zone.
4. Final smoke at 1024 plus mobile 390/375/320 to prove mobile is unchanged.
5. Run `npm run build` once at the end and `git diff --check`.
6. Do not commit, push, merge, delete branches, or access Neon/prod.

## Required concise report

1. Superseded desktop structure
2. Asset copy/hash result
3. Final desktop coordinate set
4. 1920/1280 visual comparison
5. Mobile unchanged proof
6. Core Home click results
7. Build/diff/overflow/404 result
8. Remaining risk

