# Home Phase 200 Implementation Kit

This kit exists so the next implementation pass does not depend on visual guesswork.
Use the target mockup and assets below as fixed anchors.

## 1. Target Image

Source of truth:

- `references/mockups/home-phase200-target-deep-sage.png`

Current failure reference:

- Latest user Home screenshot from 2026-08-30 18:32.

Only three visual goals matter for this pass:

- The notebook reads clearly darker: deep olive/forest sage, not pale gray-green.
- The notebook reads clearly larger than the current screenshot.
- The notebook and shortcut rail have mockup-style table cast shadows with no rectangular shadow patch.
- The shadow is clearly visible under the notebook bottom edge, along the notebook right edge, and under each of the three tabs.

## 2. Required Assets

Use these project-local assets:

- `frontend/public/brand/decor/home-v5/home-v5-notebook-cover-deep-sage.png`
  - 1183 x 860
  - alpha preserved
  - replaces the current pale `home-v3-notebook-cover.png`
  - do not re-darken with a heavy CSS filter; the asset already carries the deep sage color

- `frontend/public/brand/decor/home-v5/home-v5-notebook-contact-shadow.png`
  - 1600 x 360
  - transparent PNG
  - max alpha 92
  - fallback only
  - do not use as the default implementation shadow; it can still read as a generic oval/bar

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-contact-shadow.png`
  - 1400 x 260
  - transparent PNG
  - max alpha 72
  - fallback only
  - do not use as the default implementation shadow; it can still read as a generic oval/bar

- `frontend/public/brand/decor/home-v5/home-v5-notebook-shadow-edge-strong.png`
  - 1455 x 1122
  - transparent PNG
  - max alpha 62
  - derived from the notebook alpha contact edge, not the whole rectangle
  - rejected as the default because it was still too faint in the assembled preview

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-shadow-edge-strong.png`
  - 2129 x 1032
  - transparent PNG
  - max alpha 58
  - derived from the visible lower tab edge, not the whole rail box
  - rejected as the default because it was still too faint in the assembled preview

- `frontend/public/brand/decor/home-v5/home-v5-notebook-shadow-grounded-visible.png`
  - 1593 x 1275
  - transparent PNG
  - max alpha 131
  - derived from the notebook bottom/right contact edge
  - combines a visible contact seam and a wider floor falloff
  - rejected as default because the shadow was visible but still weaker than the reference mockup

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-shadow-grounded-visible.png`
  - 2231 x 1150
  - transparent PNG
  - max alpha 124
  - derived from the visible lower tab edge
  - combines a visible contact seam and a short floor falloff
  - rejected as default because the shadow was visible but still weaker than the reference mockup

- `frontend/public/brand/decor/home-v5/home-v5-notebook-shadow-table-cast.png`
  - 1703 x 1370
  - transparent PNG
  - max alpha 157
  - table-cast candidate from notebook lower/right edges
  - reference-only; superseded by `home-v5-notebook-shadow-mockup-cast.png`

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-shadow-table-cast.png`
  - 2327 x 1226
  - transparent PNG
  - max alpha 140
  - table-cast candidate from tab lower edges
  - reference-only; superseded by `home-v5-tab-rail-shadow-attached.png`

- `frontend/public/brand/decor/home-v5/home-v5-notebook-shadow-mockup-cast.png`
  - 1813 x 1470
  - transparent PNG
  - max alpha 188
  - default notebook shadow asset
  - generated from the notebook bottom edge, right edge, and lower-right corner weight
  - intended to match the reference mockup's clear book-on-table shadow

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-shadow-mockup-cast.png`
  - 2397 x 1296
  - transparent PNG
  - max alpha 171
  - reference-only; rejected as default because its larger canvas can move the darkest area away from the actual three tab feet
  - generated from the visible lower edges of the three tabs

- `frontend/public/brand/decor/home-v5/home-v5-tab-rail-shadow-attached.png`
  - 1927 x 1076
  - transparent PNG
  - max alpha 122
  - default tab rail shadow asset
  - same origin and width as `home-v5-shortcut-tab-rail-deeper.png`
  - generated from each tab's lower torn edge with three separate cast pools

- `frontend/public/brand/decor/home-v5/home-v5-shortcut-tab-rail-deeper.png`
  - 1927 x 816
  - alpha preserved
  - optional replacement for `home-v4-shortcut-tab-rail-candidate.png`
  - tab bodies are deeper; tape remains close to the original to avoid rectangular tint artifacts

Rejected generated previews:

- `call_NMg0gzfTpPVFhymghFSnTsY2.png`
- `call_FdDkux3GBWjsun3wH6TvL49x.png`

Reason: both generated preview files are RGB without alpha. Do not wire them into the app.

## 3. Fixed Composition Target

Desktop 1024+ starting values:

| Object | CSS variable/rule | Start value | Allowed adjustment | Target read |
| --- | --- | ---: | ---: | --- |
| scene | `.home-v4-scene` width | current width or `min(1120px, 78vw)` | +/- 3vw | keep wide desk crop, no zoomed screenshot feel |
| notebook | `--nb-w` | `70%` | `68%` to `71%` | visibly larger hero object |
| notebook | `--nb-left` | `22%` | `21%` to `24%` | enough right desk remains |
| notebook | `--nb-top` | `0%` | `0%` to `2%` | sits close to top of scene, not under nav |
| note | `--note-w` | `52%` | `50%` to `54%` | overlaps notebook upper-left deeply |
| note | `--note-left` | `0%` | fixed | keep title safe zone |
| note | `--note-top` | `-2%` | `-3%` to `0%` | taped paper rests over cover |
| CTA | `--cta-w` | `42%` | `40%` to `44%` | ticket bites note and notebook edge |
| CTA | `--cta-left` | `2%` | `0%` to `4%` | no detached banner feel |
| CTA | `--cta-top` | `39%` | `38%` to `41%` | clear gap above tab rail |
| tab rail | `--rail-w` | `94%` | `92%` to `98%` | wide action anchor, not tiny tags |
| tab rail | `--rail-bottom` | `-31%` | `-28%` to `-34%` | tucked, labels fully visible |
| Shiori | `.home-v4-shiori-peek` size | `90px` | `84px` to `100px` | head and hands visible |
| Shiori | `.home-v4-shiori-peek` left | `50%` | `47%` to `53%` | centered on tape |
| Shiori | `.home-v4-shiori-peek` top | `-32px` | `-28px` to `-40px` | lower body hidden by tape/note |

Mobile starting values:

| Object | Start value | Target read |
| --- | ---: | --- |
| notebook width | `min(350px, 88%)` | larger but not cropped |
| Shiori size | `56px` | visible peek, not tiny dot |
| Shiori top | `-22px` | head/hands visible, body hidden |
| rail width | `92%` | three labels readable |
| rail bottom | `-30%` | tucked but not crushed |

Do not change copy, handlers, API, storage, SRS, auth, or backend.

## 4. Shadow Method

Delete/disable:

- `.home-v4-scene::after`
- any large shared scene shadow
- any solid rectangle plus blur shadow under the notebook or tabs
- any detached oval sitting far below the objects
- any full-object blurred notebook shadow that darkens the whole notebook rectangle
- any shadow that is only barely visible in the screenshot

Notebook shadow:

- Use the PNG asset `home-v5-notebook-shadow-mockup-cast.png`.
- Place it as a local pseudo-element under `.home-v4-notebook`, preferably `::before`.
- Suggested CSS:
  - `left: -12.7%`
  - `top: -17.4%`
  - `width: 153.2%`
  - `height: 170.9%`
  - `background-image: url("/brand/decor/home-v5/home-v5-notebook-shadow-mockup-cast.png")`
  - `background-size: 100% 100%`
  - `z-index: -2`
  - `opacity: 0.9`
- The visible read must match the reference mockup: a dark contact seam under the book, a cast shadow falling down/right, and a clear right-edge table shadow.
- Use the mockup-cast asset, not CSS blur. Keep `.home-v4-notebook` drop-shadow weak or remove it.

Tab rail shadow:

- Use the PNG asset `home-v5-tab-rail-shadow-attached.png`.
- Place it as a local pseudo-element under `.home-v4-tab-rail`, preferably `::after`.
- Suggested CSS:
  - `left: 0`
  - `top: 0`
  - `width: 100%`
  - `height: 131.9%`
  - `background-image: url("/brand/decor/home-v5/home-v5-tab-rail-shadow-attached.png")`
  - `background-size: 100% 100%`
  - `z-index: -1`
  - `opacity: 0.9`
- Each of the three tabs must have a visible table cast immediately below its own lower torn edge. The shadow should not be a single detached bar.
- Use the attached asset, not CSS blur and not the older `mockup-cast` tab rail shadow.

Visual failure checks:

- If a rectangular shadow patch is visible, the implementation fails.
- If the darkest shadow sits far below the notebook/tabs instead of touching them, the implementation fails.
- If the notebook right edge has no visible table shadow, the implementation fails.
- If the three shortcut tabs do not each cast visible shadows that start at their own bottom edges, the implementation fails.
- If the tab shadow appears left-shifted, far below the tabs, or as one long horizontal bar, the implementation fails.
- If the notebook still reads pale, the implementation fails even if CSS values changed.
- If Shiori still reads as a tiny dot, the implementation fails.

Reference assembled previews:

- `references/mockups/home-phase200-target-deep-sage.png`: full target composition.
- `references/mockups/home-phase200-assembled-preview-attached-tab-shadow.png`: current target shadow direction.
- `references/mockups/home-phase200-tab-shadow-attached-crop.png`: close-up validation crop for the three shortcut tab shadows.

Earlier assembled preview candidates were rejected and should not be used as implementation references.
