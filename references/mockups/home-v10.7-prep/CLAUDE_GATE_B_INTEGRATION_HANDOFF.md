# Home V10.7 Lower-Rim Material Recovery - Gate B Integration

Project: `C:\JV_Project\jp_vocab_reader`

Branch: `codex/home-v10-7-rim-tone-prep`

Human decision: **Candidate B is approved.** Integrate that exact decoded image
without regenerating or modifying it. This is a bounded desktop asset wiring
and final-browser-validation task, not another design exploration.

Do not commit, push, merge, or delete the branch. Return the report and wait
for approval.

## Confirmed failure and selected result

1. V10.6's lower leather rim and lower corner returns contained crushed black
   clusters that joined into a marker-like outline.
2. The desk cast shadow and overall scene composition were already correct;
   CSS shadow work was neither necessary nor allowed.
3. Candidate B recovers warm deep-olive leather detail while retaining more
   physical weight than Candidate C and removing more black-line character
   than Candidate A.

The new scene silhouette is identical to V10.6. Only the material response of
the lower leather rim and its two lower corner returns changes.

## Read first

Read only these files initially:

1. `frontend/components/HomeDashboard.tsx`
2. The `.home-v10-scene` and `.home-v10-tab-content` desktop rules in
   `frontend/app/globals.css`
3. `frontend/public/brand/decor/home-v10.7/ASSET_MANIFEST.md`
4. `references/mockups/home-v10.7-prep/home-v10.7-rim-contact-sheet.png`
5. `references/mockups/home-v10.7-prep/CLAUDE_GATE_A_ASSET_HANDOFF.md`

Do not perform broad repository archaeology. Inspect other source files only
if a concrete functional regression is reproduced.

## Selected immutable asset

Approved input:

`frontend/public/brand/decor/home-v10.7/home-v10.7-scene-desktop-b.png`

- Dimensions: `1888x833`
- Mode: 8-bit RGB PNG
- Required SHA-256:
  `3E47D6CD8517C3176C8A0CAF6611DCE6C9788991F1B8B96CF71A83E10AF9D628`

Before doing anything, verify the hash, dimensions, and mode. If any value
differs, stop and report. Do not regenerate a replacement.

## Exact production-file operation

1. Rename Candidate B without re-encoding:

   `home-v10.7-scene-desktop-b.png`
   -> `home-v10.7-scene-desktop.png`

2. Verify the final file hash is still exactly:

   `3E47D6CD8517C3176C8A0CAF6611DCE6C9788991F1B8B96CF71A83E10AF9D628`

3. Delete the two rejected production candidates:

   - `home-v10.7-scene-desktop-a.png`
   - `home-v10.7-scene-desktop-c.png`

4. Keep the Gate A contact sheet under `references/mockups`; it is audit
   evidence and must not be moved into `frontend/public`.
5. Rewrite `frontend/public/brand/decor/home-v10.7/ASSET_MANIFEST.md` from
   candidate status to final production status. Record Candidate B selection,
   source V10.6 hash, final V10.7 hash, dimensions, deterministic bounded-mask
   method, and the rendering contract.

At the end, `frontend/public/brand/decor/home-v10.7/` must contain exactly:

- `home-v10.7-scene-desktop.png`
- `ASSET_MANIFEST.md`

No A/B/C candidate filename may remain in `frontend/public`.

## Exact source wiring

In `frontend/components/HomeDashboard.tsx`:

1. Replace the desktop asset constant/path from V10.6 to V10.7.
2. The desktop `<source media="(min-width: 768px)">` must resolve to:

   `/brand/decor/home-v10.7/home-v10.7-scene-desktop.png`

3. Mobile must continue resolving to:

   `/brand/decor/home-v10.5/home-v10.5-scene-mobile.png`

Only the desktop constant/path and its adjacent version comment may change.
Do not restructure JSX.

## Geometry that must remain byte-for-byte unchanged

Do not edit `frontend/app/globals.css`. Confirm these existing desktop values
instead:

```css
--scene-height: calc(100svh - 50px);
--scene-art-ratio: 1888 / 833;
--scene-art-width: max(100vw, calc(226.65svh - 113.33px));
```

The desktop `.home-v10-tab-content` value must remain:

```css
padding: 18% 8% 14% 10%;
```

All title, sample, CTA, vocab, review, and deck coordinates must remain
unchanged. The V10.7 asset has exactly the same 1888x833 canvas and composition
as V10.6; coordinate recalculation is forbidden.

## Absolute prohibitions

- No editing or re-encoding the approved B asset.
- No ImageGen, global grade, blur, sharpen, resize, crop, relighting, or mask
  revision.
- No CSS shadow, filter, gradient, border, mask, pseudo-element, overlay, or
  spacing adjustment.
- No change to `globals.css`, AppShell, nav assets, scene geometry, overlay
  coordinates, text, icon size, typography, or hit zones.
- No change to the V10.5 mobile asset or mobile layout.
- No callback, routing, API, auth, SRS, storage, accessibility, or backend
  change.
- Never start the backend and never access Neon or production data.
- Do not delete or overwrite V10.6.
- Do not commit, push, merge, or create/switch branches.

## Validation sequence

1. Record `git status --short` before work and confirm the only existing
   untracked scope is Home V10.7 preparation material.
2. Verify the approved B hash/dimensions/mode.
3. Perform the exact rename, reject-candidate cleanup, manifest finalization,
   and desktop URL replacement described above.
4. Run `git diff --check` and inspect the complete diff before browser work.
5. Start only the frontend dev server.
6. Fresh-navigate Home and capture full screenshots at `1920x960` and
   `1280x960`. Judge the first impression against the Gate A contact sheet.
7. Confirm desktop geometry at `1024x768`.
8. Confirm mobile source and overflow at `390x844`, `375x812`, and `320x700`.
9. Exercise the five Home hit zones: sample, CTA, vocab, review, and deck.
10. Inspect image requests, console output, and horizontal overflow.
11. Stop the dev server and browser, then run `npm run build` once.
12. Run final `git diff --check`; confirm ports `3000`, `8000`, and `9222` are
    closed; return the report and stop.

If the selected asset looks wrong in the real browser, do not alter it. Report
the exact visual mismatch and stop. One correction is allowed only for a typo
in the asset URL or manifest; no aesthetic correction is authorized in Gate B.

## Acceptance criteria

### Asset and wiring

- Final V10.7 file is 1888x833 RGB and retains the exact approved B hash.
- V10.7 public folder contains only the final PNG and manifest.
- Desktop requests only the final V10.7 URL and receives 200/304.
- V10.6 desktop URL is not requested by production Home.
- Mobile continues to request V10.5 and never requests V10.7.
- No image 404 occurs.

### Desktop visual result

- The lower leather rim reads as textured deep warm olive/green-brown, not a
  continuous pure-black line.
- Both lower corners retain rounded leather depth without black wedges.
- The cream page block remains clearly separated and unchanged.
- The broad desk cast shadow remains unchanged and the notebook remains
  grounded.
- The rim does not become gray, orange, uniformly painted, luminous, or
  rubber-like.
- No hard mask contour, halo, seam, or rectangular edit boundary is visible.
- Scene composition, notebook position/size, props, note, CTA, Shiori, tabs,
  tape, and emboss are unchanged.

### Layout and behavior

- Toolbar height remains 50px.
- Scene starts at y=50 and reaches the viewport bottom with zero bottom strip.
- Art-plane top/bottom deviation remains no more than 0.02px.
- `scrollWidth === clientWidth` at all six target sizes.
- Tab text remains in its current higher position without collision.
- Sample and CTA open Reading; vocab and deck open their sections; review
  follows the existing account/review branch.
- No new console error or warning beyond expected frontend-only API failures.

## Failure criteria

Fail and stop if any of the following occurs:

- Approved B hash changes before or after rename.
- A/C candidates remain in `frontend/public`.
- Any CSS, coordinate, mobile asset, or unrelated behavior changes.
- The rim still reads as a black outline at normal browser scale.
- The book appears lighter overall or loses contact with the desk.
- Page block, cast shadow, tabs, tape, or exterior silhouette visibly changes.
- Bottom strip, horizontal overflow, 404, or click regression appears.
- An aesthetic correction is attempted instead of reporting the mismatch.

## Required concise report

1. Approved B pre/post-rename hash and dimension verification
2. Removed candidate files and final V10.7 folder contents
3. Exact HomeDashboard source change and proof CSS stayed unchanged
4. 1920/1280 lower-rim and corner visual judgment
5. 1024 geometry and bottom-fill result
6. 390/375/320 mobile-source unchanged proof
7. Five Home click results
8. Request/404/console/overflow result
9. Build/diff/process-cleanup result
10. Remaining risk

End with `Gate B complete - awaiting approval.` Do not commit or push.
