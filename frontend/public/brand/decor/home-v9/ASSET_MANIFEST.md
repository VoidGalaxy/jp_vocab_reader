# Home V9 Asset Manifest

This folder is for the next Home foreground replacement. V9 exists because V8 still failed visually: the notebook did not feel grounded on the desk, Shiori felt pasted on, and the bottom tabs remained cramped.

## References

- `home-v9-approved-scene-target.png`
  - Original approved full-scene target for composition, notebook scale, tab size, lighting, and grounding.
  - Also doubles as the "before" reference for diff-matting Shiori out (see below): same composition, but with a small placeholder mark instead of her.
- `home-v9-approved-shiori-pose.png`
  - Approved Shiori pose reference.
- `home-v9-composited-target-mockup.png`
  - Generated V9 target mockup combining the approved scene direction with the approved Shiori reading-peek pose. Pixel-identical desk layer to `frontend/public/brand/decor/home-v4/home-v4-desk-surface-desktop.png`.

## Production Assets

- `home-v9-foreground-grounded-plate.png` (968x796, RGBA)
  - Built by difference-matting `home-v9-composited-target-mockup.png` against `home-v4-desk-surface-desktop.png`: any pixel close to the known desk color/hue at that spot is background (alpha 0); a pixel that's a hue-consistent darkening of the desk is real contact shadow (alpha recovered from how much darker it is, color forced to black, which reproduces the source composite exactly when re-composited over the same desk); everything else is opaque foreground using its own real color. This recovers a genuine soft-falloff shadow directly from the approved artwork instead of re-deriving one from the v7/v8 raster.
  - Contains: notebook cover, bookmark ribbon, emboss, three tabs + tape, baked contact shadow. Does NOT contain Shiori (see Shiori asset below and HomeDashboard.tsx's Phase 215 comment for why she stays separate) or the title note / CTA (those remain their own pre-existing assets, unchanged).
  - The small area the title note and CTA ribbon sit on top of (in the mockup) is filled with real cover color sampled from just outside that area (interpolated top-to-bottom to avoid banding) rather than left as a transparent notch -- the plate is a complete, standalone book cover so it also looks correct at <1024px, where the note/CTA stack above it in flow instead of overlapping it.
  - Validated: RGBA, transparent corners, no border matte residue (checked with the same validator logic `validate_home_v8_plate.py` used).
  - Tab measurements (as % of this plate's own 968x796 canvas): yellow `left:27.89%; top:81.16%; width:15.81%; height:10.55%`, coral `left:46.28%; top:81.16%; width:15.50%; height:10.55%`, blue `left:64.05%; top:81.66%; width:15.39%; height:10.05%`.
- `home-v9-shiori-reading-peek.png` (168x167, RGBA)
  - Built the same way, but diffed against `home-v9-approved-scene-target.png` (the same composition with a small placeholder mark instead of her) rather than the bare desk, so the diff is exactly her silhouette plus the real contact shadow she casts on the tape/flap beneath -- not a CSS `filter: drop-shadow` approximation.
  - Replaces `home-v7-shiori-reading-peek.png` on `.home-v4-shiori-peek`; wired the same way (a separate element positioned against `.home-v4-note`, not baked into the notebook plate -- see HomeDashboard.tsx).

## Rejected Approaches

- Reusing or tuning the V8 grounded plate.
- Deriving the final shadow from the old V7/V8 alpha after the fact.
- CSS-only shadows.
- Separate shadow-only PNG layers.
- Any plate with matte residue, hard shadow lines, black tab bars, or rectangular support slabs.

## Implementation Note

Wired into Home per HomeDashboard.tsx and globals.css (Phase 215). Shortcut hit zones and `.home-v4-notebook`'s own aspect-ratio/sizing were recalculated from this plate's real pixel dimensions, not reused from V8.
