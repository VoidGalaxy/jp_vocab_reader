# Home Navigation V1.2 Natural Paper Edge — Asset Manifest

Status: **Gate A approved, Gate B wired.** Candidate B is selected and
live in production as `home-nav-paper-strip.png`, referenced from
`globals.css`'s desktop `.app-toolbar::before` rule. `home-nav-v1/` and
`home-nav-v1.1/` remain on disk (untouched) but are no longer referenced
by the desktop paper-strip rule; V1.1's active linen and divider assets
are still reused unchanged.

Briefs: `references/mockups/home-nav-prep/CLAUDE_EDGE_FINISH_V1_2.md`
(Gate A) and `CLAUDE_EDGE_FINISH_V1_2_GATE_B.md` (Gate B wiring).

## Gate B: selected candidate

- Candidate B was renamed to `home-nav-paper-strip.png` with **no
  re-encoding** — SHA-256 before and after the rename is identical:
  `27c8a0de2a32f7375f109b753b8e2ae348f39281cc2aba1f6787ecf551bc6b59`.
- Candidates A and C, and the shared `_paper-body-debug.png` reference,
  were deleted from this folder (kept only in git history via this
  manifest's record of their prior SHA-256 values below, and in the
  moved contact sheet). They are not present anywhere under
  `frontend/public/`.
- The comparison contact sheet moved out of the public runtime tree to
  `references/mockups/home-nav-prep/home-nav-v1.2-edge-contact-sheet.png`.
- This folder now contains exactly: `home-nav-paper-strip.png` and this
  `ASSET_MANIFEST.md`.

## Confirmed V1.1 failure mechanism

1. V1.1 multiplies RGB on the last three opaque rows of every deckle
   column by `0.55`, `0.75`, `0.9` (see `globals.css`'s V1.1 paper-strip
   build history / the V1.1 pass's own script).
2. That shading is baked **inside the opaque paper silhouette itself**,
   so it renders as a crisp dark contour tracing the torn edge over
   *every* background — confirmed visually against both the wood
   (`033231`) and mint felt (`033242`) reference screenshots, where the
   edge reads as a continuous gray/black ink line rather than a soft
   paper edge.
3. Fixing this requires two separately-authored things: (a) a clean
   paper fiber edge with no baked-in darkening, and (b) a low-opacity
   warm shadow living **outside** the paper's own alpha, fading with
   distance — which is what this pass builds.

## Source and transforms

- Source: `home-nav-v1/home-nav-paper-strip.png` (1920×64 RGBA) — **not**
  the already-darkened V1.1 strip. SHA-256:
  `cd18a0fbb2f6b34f043a816a23d0d587cf283c69bec4afe4df15b55a96fa50ee`.

### Paper body (shared identically by all three candidates)

1. Resize 1920×64 → 1920×56 by resizing the full 4-channel RGBA buffer
   in one `sharp`/libvips call (`kernel: lanczos3`), not by splitting
   into separate per-channel raw buffers. (An earlier attempt split R/G/
   B/A into four 1-channel raw resizes; `sharp` silently promotes a
   1-channel raw *output* to 3 channels, which corrupted every row/column
   read — confirmed by an output buffer 3× the expected byte length.
   Resizing the real 4-channel RGBA buffer directly lets libvips's own
   alpha-aware resize handle the equivalent of premultiplied resampling
   internally; verified empirically afterward that fringe pixels blend
   toward each column's real interior tone rather than toward black.)
2. Apply the approved V1.1 core tint only, on RGB: `R*0.98`, `G*0.96`,
   `B*0.92`. The `0.55/0.75/0.9` opaque-edge darkening is **not**
   applied anywhere in this pass.
3. Fringe cleanup: the source art bakes a bright paper-fiber highlight
   into the last couple of solid-ish rows before the deckle cliff (e.g.
   V1 source `x=900` reads `(248,232,215)@α250` then `(249,242,231)@α252`
   right before the alpha cliff, against a flat interior of
   `~(244,226,208)`) — resizing concentrates that highlight into fewer
   rows, so it reads as a bright rim rather than the artist's subtle fuzz.
   The true deckle transition never starts before source row ≈57/64
   (89%), which maps to resized row ≈50/56 — so row 20 is a safe,
   universally-flat "interior" sample for every column. Rows 44–55 (12
   rows of margin before the earliest possible transition) get that same
   column's own row-20 RGB forced in, **alpha untouched**. This is a
   per-column fill (follows each column's real fiber tone via its own
   row-20 sample), not a flat matte.
4. The original irregular deckled alpha silhouette is never smoothed,
   blurred, or redrawn — only resized once, in transform 1.
- Paper-body debug reference (pre-shadow, shared by all 3 candidates):
  `_paper-body-debug.png`, SHA-256
  `1cee7b873e8f7c32d4635aca2e9c32aada8256b6d849f8541f875f81d81f3279`.

### Canvas and exterior shadow (varies per candidate)

- Final canvas: 1920×64 RGBA. Paper body placed at `(0,0)` unscaled.
  Rows 56–63 reserved for the shadow.
- Per column, `edgeY` = the last row (0–55) where paper alpha ≥128 (a
  perceptual "visually solid" threshold — using any-nonzero-alpha instead
  picked up 1–4-value antialiasing noise and made the derived shadow
  wildly inconsistent column to column).
- Shadow alpha at row `y` (`d = y − edgeY`, `d ≥ 1`):
  `alpha = round(peak × exp(−(d − offset)² / (2·σ²)) × 255)`, color fixed
  at `#69462d` (105, 70, 45 — warm desk brown; R≥G, G>B).
- Row 63 is hard-clamped to alpha 0 regardless of the formula.
- Compositing is real alpha "over" (paper over shadow), so the two
  regions correctly blend at boundaries rather than assuming they're
  always disjoint.

## A/B/C measured shadow profiles

Sampled at columns with `edgeY=53` (typical) and `edgeY=50` (an early
deckle dip); `d=0` is the paper's own edge-row alpha, not shadow.

| Candidate | peak / offset / σ (impl.) | measured peak shadow alpha | measured peak location | ~alpha-0 by |
|---|---|---:|---:|---:|
| A — quiet | 0.08 / 1px / σ=1.0 | 23–98 (varies with local fringe blend) / pure-shadow tail ≈12 | d=1 | d=4 |
| B — balanced | 0.12 / 1.5px / σ=1.4 | pure-shadow plateau 29–30 | d=1–2 | d=6 |
| C — grounded | 0.16 / 2px / σ=1.8 | pure-shadow peak 41–42 | d=2 | d=8 |

(Per-column `d=1` values vary because they include a blend with that
column's own already-faint paper fringe, not pure shadow — see the "no
shadow overlap" note below. From `d=2` on, values converge to the same
candidate-specific curve regardless of column.) Exact per-candidate
implementation values: A `peak=0.08, offset=1, σ=1.0`; B
`peak=0.12, offset=1.5, σ=1.4`; C `peak=0.16, offset=2, σ=1.8`. Sharp's
own blur kernel was not used for the shadow (a custom per-pixel Gaussian
was computed directly instead, to guarantee exact control over offset/
falloff/edge and to make the "never above the edge" and "zero at the
final row" guarantees exact rather than approximate).

## Alpha / matte / stroke validation (programmatic, see `_tmp` scripts run during this pass)

For each of A/B/C:

- ✅ exact dimensions 1920×64, 4 channels.
- ✅ paper's opaque (alpha=255) footprint identical across A/B/C — 0
  mismatched pixels comparing all three pairwise.
- ✅ zero color mismatch on any alpha=255 paper pixel vs. the shared
  paper body — i.e. no shadow ever alters an opaque paper pixel.
- ✅ final canvas row (63) fully transparent on all three.
- Top row and left/right canvas-edge columns read alpha 255 — this is
  the paper's own flat (non-deckled) top/side edge, not shadow bleed;
  confirmed by cross-referencing against the paper-body-only debug
  render, which has the same values there.
- ✅ shadow hue on all three: `(105, 70, 45)` — R≥G and G>B (warm brown,
  never gray/black).
- ✅ shadow alpha strictly decreases with distance from the edge in every
  sampled column (spot-checked at 4 columns per candidate).
- ✅ zero "dark stroke" violations: sampled every 10th column, comparing
  the last 3 opaque paper rows against each column's own interior tint —
  no row reads >15 levels darker (the V1.1 0.55/0.75/0.9 darkening is
  simply absent from this build).
- ✅ visual check (contact sheet + 4× crops, see below): no rectangular
  matte or gray halo over wood, mint, or cream backgrounds.
- SHA-256:
  - `home-nav-paper-strip-a.png`: `c5bf4e799bf5b520a9dd16c12c83eda8f31d8716d5407a8c3af37c3800560bd4`
  - `home-nav-paper-strip-b.png`: `27c8a0de2a32f7375f109b753b8e2ae348f39281cc2aba1f6787ecf551bc6b59`
  - `home-nav-paper-strip-c.png`: `28a9f83ca3c3482293ea47cec4b5745fc3cb6d26adff9bc52f75b06832beffd6`

## Contact sheet

`references/mockups/home-nav-prep/home-nav-v1.2-edge-contact-sheet.png`
(moved here per Gate B; was `frontend/public/.../home-nav-edge-contact-sheet.png`
during Gate A review) — A/B/C at 100% native pixel scale
(no resampling of the candidate images themselves) over three real
project-scene crops:

- Home warm wood: cropped directly from the supplied Home reference
  screenshot (`033231`), well below the old nav, notebook-corner-free.
- Review mint felt: cropped from `v2-study-felt-board-desktop-16x9.webp`,
  below its own picture-frame border, pure felt.
- Reading cream page: cropped from
  `v2-reading-open-book-desktop-16x9.webp`, inside the open page (past
  the top wood sliver).

Each row uses the identical crop window, y-position, and 1:1 scale
across A/B/C. A 4th row shows 4× nearest-neighbor close crops of the
torn edge over a flat mid warm-tone background for pixel inspection —
per the brief, this is a supplementary check, not the primary judgment.

## Recommendation

**Candidate B (balanced)** — it's the first of the three where the
contact shadow is clearly, consistently visible against all three
backgrounds (wood, mint, cream) without needing the brightest/highest-
contrast background to notice it, while still reading as distinctly
quieter than V1.1's hard contour; A is safe but nearly invisible against
wood, and C's stronger falloff starts to look slightly "grounded" even
against the darker wood background where less shadow is needed.

## Current files (post Gate B cleanup)

- `frontend/public/brand/decor/home-nav-v1.2/home-nav-paper-strip.png` (formerly `-b.png`, byte-identical rename)
- `frontend/public/brand/decor/home-nav-v1.2/ASSET_MANIFEST.md` (this file)
- `references/mockups/home-nav-prep/home-nav-v1.2-edge-contact-sheet.png` (moved out of `frontend/public/`)

Removed from `frontend/public/` (Gate A candidates no longer needed once
B was selected): `home-nav-paper-strip-a.png` (SHA-256
`c5bf4e799bf5b520a9dd16c12c83eda8f31d8716d5407a8c3af37c3800560bd4`),
`home-nav-paper-strip-c.png` (SHA-256
`28a9f83ca3c3482293ea47cec4b5745fc3cb6d26adff9bc52f75b06832beffd6`), and
`_paper-body-debug.png` (SHA-256
`1cee7b873e8f7c32d4635aca2e9c32aada8256b6d849f8541f875f81d81f3279`).

## Guardrails

- `home-nav-v1/` and `home-nav-v1.1/` folders are unmodified on disk.
  `home-nav-v1.1/home-nav-active-linen.png` and
  `home-nav-v1.1/home-nav-divider-emboss.png` are still the live URLs
  `globals.css` uses for the active tab and dividers — unchanged, not
  copied into this folder. Only the desktop paper-strip URL now points
  at this folder's `home-nav-paper-strip.png` (Candidate B) instead of
  `home-nav-v1.1/home-nav-paper-strip.png`.
- `AppShell.tsx` and all other component/TSX files are untouched; the
  only production code change is the desktop paper-strip URL and its
  transparent canvas extent in `globals.css` (see Gate B section above).
- No image-generation model and no manual painted line were used —
  every pixel in the shipped asset is `sharp`/arithmetic-derived from
  the V1 source (see Source and transforms above).
