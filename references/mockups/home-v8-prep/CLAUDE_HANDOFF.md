# Home V8 Target-Asset Handoff

## 3-Line Failure Diagnosis

- The current production plate still contains visible white/gray matte residue around the notebook right and bottom edge, so the browser can show a hard edge even when CSS changes.
- CSS-only shadows and full-plate shadow PNGs both failed: on a wood texture they reveal rectangular boundaries, black bars, or shadows that do not look attached to the notebook.
- The desired design is already defined by the target mockup, but implementation kept changing code around a flawed asset instead of replacing the asset first.

## Target Image

Use `references/mockups/home-v8-prep/home-v8-final-target-desktop.png` as the visual target.

This target defines:

- dark forest-green notebook color and woven texture,
- notebook scale and position,
- natural table-contact shadow along the notebook bottom and right edge,
- separated yellow/coral/blue tabs with their own shadows,
- no white/gray matte residue around the notebook or tabs,
- Shiori reading-peek direction from `references/mockups/home-v8-prep/home-v8-shiori-selected-reference.png`.

## Required Asset-First Work

Before editing layout CSS, create or replace the production notebook plate asset.

Required new asset:

- `frontend/public/brand/decor/home-v8/home-v8-notebook-tabs-grounded-plate.png`

Prepared candidate:

- `frontend/public/brand/decor/home-v8/home-v8-notebook-tabs-grounded-plate.png`
  - Generated deterministically by `references/mockups/home-v8-prep/build_home_v8_plate_candidate.py`.
  - Source: current v7 plate, with border-connected white/gray matte removed and contact shadow baked into the same transparent PNG.
  - Validation: passes `validate_home_v8_plate.py`.
  - Visual status: candidate, not final approval. It removes the right/bottom matte residue and moves shadow into the plate, but must still be compared against the target mockup before wiring.

Asset requirements:

- True transparent PNG with an alpha channel.
- Contains only notebook + bookmark ribbon + emboss mark + three separated tabs + tab tape + natural contact shadows.
- Does not contain the desk background, nav, note paper, CTA ribbon, Shiori, Korean/Japanese text, or fake UI labels.
- Shadow must be baked into this asset under one consistent light source:
  - darkest at the notebook bottom/right contact edge,
  - gradually fading outward,
  - separate soft underside shadows for each tab,
  - no rectangular canvas boundary,
  - no black bar under the tab row.
- Remove the current production plate's right/bottom white matte residue. Do not keep those pixels and try to hide them with CSS.
- Evidence: the validator fails on `frontend/public/brand/decor/home-v7/home-v7-notebook-tabs-shadow-plate.png` with bright edge residue, and passes on the prepared v8 candidate.

Rejected approaches:

- Do not solve this with `box-shadow`, `filter: drop-shadow`, `radial-gradient`, `linear-gradient`, or pseudo-element shadow maps.
- Do not generate a full-scene screenshot and call it a transparent asset if the background/checkerboard is baked into RGB pixels.
- Do not keep using `home-v7-notebook-tabs-shadow-plate.png` as the final production plate unless the matte residue is removed and contact shadow is rebuilt inside the asset.

## Implementation After Asset Passes Validation

- Replace the Home notebook image source with `home-v8-notebook-tabs-grounded-plate.png`.
- Remove `.home-v4-notebook::before` and `.home-v4-notebook::after` shadow CSS.
- Keep all live Korean text and all shortcut labels/hints in DOM.
- Keep existing callbacks and behavior unchanged:
  - CTA -> reading,
  - sample -> reading sample,
  - vocab shortcut -> vocab panel,
  - review shortcut -> review/account branch,
  - decks shortcut -> shared deck section.
- Recalculate shortcut hit zones from the new plate pixels after the asset is final; do not reuse old percentages blindly.
- Prepared candidate tab measurements from `measure_plate_tabs.py`:
  - plate size: 1538x1247
  - yellow: x 488-682, y 998-1092 (`left:31.73%; top:80.03%; width:12.61%; height:7.54%`)
  - coral: x 702-897, y 996-1092 (`left:45.64%; top:79.87%; width:12.68%; height:7.70%`)
  - blue: x 919-1116, y 999-1092 (`left:59.75%; top:80.11%; width:12.81%; height:7.46%`)
- Keep Shiori as a separate Home-only image unless a later approved asset explicitly bakes her into the note/tape group. Match the selected reference pose and make her clearly visible, not a tiny mark.

## Required Validation Before Coding

Run the validation script:

```bash
C:\Users\mjwmm\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe references/mockups/home-v8-prep/validate_home_v8_plate.py frontend/public/brand/decor/home-v8/home-v8-notebook-tabs-grounded-plate.png
```

Do not proceed to implementation unless it reports:

- RGBA or LA mode,
- transparent corners,
- no checkerboard/RGB background,
- no bright opaque border residue.

## Browser QA After Implementation

- Check 1280, 1024, 390, 375, and 320 widths.
- Confirm `scrollWidth === clientWidth`.
- Confirm no image 404.
- Confirm old shadow PNGs and CSS shadow pseudo-elements are not wired.
- Real-click CTA, sample, vocab, review, and decks.
- Compare screenshot first impression against `home-v8-final-target-desktop.png` before calling it done.
