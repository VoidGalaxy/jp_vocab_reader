# Phase 131 Individual Asset Crops

Cropped/cleaned from Phase 126/127 "candidate" source PNGs, which each
bundled multiple objects (or one object with a heavy vignette) in a single
canvas. This phase does not apply any of these to a screen -- it only
produces individually usable files for a future application phase.

## Key finding

The `-web.webp` versions of these candidates (already committed in
`phase126/`/`phase127/`) look vignetted/dark at the edges because that
export flattened the image onto an opaque background, discarding alpha.
The **source PNGs retain real per-pixel alpha transparency** with a clean
matte cutout and a natural soft drop shadow already baked in -- confirmed
by compositing each one onto a plain white background with Pillow, which
revealed a professional-quality cutout, not a vignette. Every crop below
was made directly from the source PNG (not the `-web.webp`), preserving
that real alpha channel into a transparent WebP.

## Assets

All files are transparent WebP (`quality=88, method=6`), cropped from
their source `-candidate.png` using alpha-channel projection analysis
(row/column sums of `alpha > 10`) to find each object's tight bounding
box, then padded outward with a margin clamped so it never bleeds into a
neighboring object still in the same source canvas (see "Sourcing" below
for exact source crop boxes).

| File | Size | From | Center clear for live HTML? |
|---|---|---|---|
| `sticky-note-yellow.webp` | 462x480, 46.5KB | `phase126/sticky-note-set-candidate.png` | Yes -- large blank torn-paper center |
| `sticky-note-blue.webp` | 480x330, 39.3KB | same | Yes |
| `sticky-note-coral.webp` | 480x306, 40.7KB | same | Yes |
| `desk-prop-pen.webp` | 184x400, 11.3KB | `phase126/desk-prop-set-candidate.png` | N/A -- small prop, not a text surface |
| `desk-prop-washi-tape.webp` | 400x353, 24.4KB | same | N/A |
| `desk-prop-paperclip.webp` | 400x378, 28.0KB | same | N/A |
| `desk-prop-leaf.webp` | 223x400, 24.8KB | same | N/A |
| `book-cover-green-object-clean.webp` | 507x700, 94.1KB | `phase126/book-cover-green-object-candidate.png` | N/A -- decorative object, not a text surface |
| `study-flashcard-stack-clean.webp` | 700x473, 28.6KB | `phase127/study-flashcard-stack-candidate.png` | N/A -- decorative backing texture |

All 9 files pass visual QA: no vignette, no bled-in fragment of a
neighboring object, natural soft shadow preserved, transparent background
confirmed by white-background composite test.

## Sourcing (exact crop boxes, source-pixel coordinates)

For reproducibility / re-cropping later if a tighter or looser margin is
ever wanted.

`sticky-note-set-candidate.png` (1536x1024 source):
- yellow: `(0, 89, 786, 905)`
- blue: `(760, 7, 1536, 540)`
- coral: `(760, 529, 1536, 1024)`

`desk-prop-set-candidate.png` (1536x1024 source):
- pen: `(46, 1, 513, 1015)`
- washi tape: `(474, 58, 1064, 579)`
- paperclip: `(474, 571, 885, 959)`
- leaf: `(1059, 138, 1523, 970)`

`book-cover-green-object-candidate.png` (1024x1536 source):
- `(7, 62, 1024, 1466)`

`study-flashcard-stack-candidate.png` (1536x1024 source):
- `(22, 0, 1536, 1022)`

## Guardrails (unchanged from Phase 127's manifest)

- Keep all product text live in HTML -- these are decorative/material
  assets only, never a text carrier.
- No text is baked into any of these crops.
- Add fallback background colors for every image-backed surface these are
  eventually applied to.
- Decorative layers must use `pointer-events: none` when they can overlap
  controls.

## Tooling note

Cropping used Pillow + numpy, installed into an isolated scratch
directory outside the repo (`pip install --target`) rather than added to
`backend/requirements.txt` -- no new project dependency. Not needed again
unless another crop pass is done.

## Phase 140 update

The `phase126/*-candidate.png` and `phase127/*-candidate.png` source
files the "Sourcing" section above describes cropping from are no
longer in `frontend/public/brand/decor/` -- they were never fetched by
the running app (nothing referenced them by URL) and added ~29MB of
dead weight to every deploy, so Phase 140 moved them to
`docs/design/source-assets/` (see that folder's `README.md`). The exact
crop-box coordinates above are still accurate against those same files
at their new location if another crop pass is ever needed.
