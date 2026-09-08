# Home V9 Grounded Scene Handoff

## 3-Line Failure Diagnosis

- The current v8 screen still reads as layered assets: the notebook shadow either disappears or becomes a dark edge instead of a table-contact falloff.
- Shiori is visible, but she feels pasted above the tape rather than physically tucked into the paper/notebook scene.
- The bottom tabs are too compressed and UI-like; they do not read like large paper tabs resting on the desk with their own shadows.

## Target Images

Use these references in this order:

1. `references/mockups/home-v9-prep/home-v9-composited-target-mockup.png`
   - Primary target. This combines the approved overall composition with the selected reading Shiori direction.
2. `references/mockups/home-v9-prep/home-v9-approved-scene-target.png`
   - Original approved scene/shadow reference.
3. `references/mockups/home-v9-prep/home-v9-approved-shiori-pose.png`
   - Approved Shiori pose reference.
4. `references/mockups/home-v9-prep/home-v9-shadow-reference.png`
   - Shadow quality reference.

## Full Scene Replacement: What To Delete Or Supersede

- Supersede the v8 production plate:
  - `frontend/public/brand/decor/home-v8/home-v8-notebook-tabs-grounded-plate.png`
- Do not keep tuning `references/mockups/home-v8-prep/build_home_v8_plate_candidate.py`; it is a failed derivative pipeline from v7 geometry.
- Do not add back `.home-v4-notebook::before` or `.home-v4-notebook::after`.
- Do not use CSS `box-shadow`, `filter: drop-shadow`, `radial-gradient`, or `linear-gradient` to solve notebook/tab grounding.
- Do not create a separate shadow-only layer behind the plate.

## Required V9 Production Assets

Create a new folder:

- `frontend/public/brand/decor/home-v9/`

Required final production asset:

- `home-v9-foreground-grounded-plate.png`

This must be a true transparent PNG containing:

- dark forest-green notebook,
- cream bookmark ribbon,
- embossed book-and-leaf mark,
- three separated yellow/coral/blue paper tabs, large enough for live DOM text,
- tab tape strips,
- selected Shiori reading-peek pose physically tucked behind/into the top tape group,
- natural contact shadows for notebook bottom/right and each tab underside.

It must not contain:

- desk background,
- app toolbar,
- title-note Korean text,
- CTA text,
- shortcut labels/hints,
- any baked UI copy.

## Shadow Requirements

The shadow must look like the target mockup:

- darkest directly under the notebook bottom and right contact edge,
- gradually fades outward into the wood surface,
- tabs have separate soft underside shadows,
- no black horizontal bar under the tab row,
- no rectangular support slab,
- no visible canvas boundary,
- no hard line separating shadow from desk.

Important: the shadow should be created with the new V9 foreground art under one consistent light source, not derived from the old v7/v8 plate after the fact.

## Layout Implementation

After the V9 asset passes visual review:

- Replace the Home notebook image source with `/brand/decor/home-v9/home-v9-foreground-grounded-plate.png`.
- Keep live Korean/Japanese text in DOM.
- Keep existing Home callbacks and behavior unchanged:
  - CTA -> reading,
  - sample -> reading sample,
  - vocab shortcut -> vocab panel,
  - review shortcut -> account/review branch,
  - decks shortcut -> shared deck section.
- Recalculate shortcut hit-zone coordinates from the final V9 plate pixels. Do not reuse v8 percentages.
- If the V9 plate canvas has added transparent shadow bleed, update `.home-v4-notebook` aspect ratio and width from the actual final asset dimensions, not by guessing.

## Validation

Before coding:

- Inspect the V9 plate by itself on a black/transparent preview.
- Inspect it composited over the actual Home desk background.
- Reject it if Shiori floats, if tab colors bleed, if the shadow disappears, or if the shadow forms a slab/bar.

Browser QA after wiring:

- Check 1280, 1024, 390, 375, and 320 widths.
- Confirm `scrollWidth === clientWidth`.
- Confirm no `/brand/decor/` 404.
- Confirm old v8/v7 plate URLs are not requested.
- Confirm `.home-v4-notebook::before/::after` are inactive.
- Real-click CTA, sample, vocab, review, and decks.
- Save one full desktop screenshot and compare first impression against `home-v9-composited-target-mockup.png` before reporting done.

## Report Format

Start the final report with:

1. Deleted/superseded v8 structure
2. New v9 asset(s)
3. Before/after first impression
4. Shadow judgment
5. Shiori judgment
6. Tab judgment
7. Desktop/mobile QA
8. Behavior preserved
9. Remaining risks
