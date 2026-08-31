# Home V5 Asset Manifest

Prepared for the Phase 200 Home pass: darker notebook, larger notebook, and natural contact shadows.

## Use These Assets

- `home-v5-notebook-cover-deep-sage.png`
  - 1183x860.
  - Transparent PNG, alpha preserved.
  - Derived from `../home-v3/home-v3-notebook-cover.png`.
  - Use as the direct replacement for the current pale notebook cover.
  - Do not add a heavy CSS darkening filter; the darker material tone is already baked into this asset.

- `home-v5-notebook-contact-shadow.png`
  - 1600x360.
  - Transparent PNG, alpha preserved.
  - Early fallback only.
  - Prefer the edge-derived shadow below for implementation.

- `home-v5-tab-rail-contact-shadow.png`
  - 1400x260.
  - Transparent PNG, alpha preserved.
  - Early fallback only.
  - Prefer the edge-derived shadow below for implementation.

- `home-v5-notebook-shadow-edge-strong.png`
  - 1455x1122.
  - Transparent PNG, alpha preserved.
  - Derived from the notebook cover alpha, but only from the bottom/right contact edges.
  - Rejected as the default because it was still too faint in the assembled preview.
  - Avoids the rectangular patch caused by full-object blur shadows.

- `home-v5-tab-rail-shadow-edge-strong.png`
  - 2129x1032.
  - Transparent PNG, alpha preserved.
  - Derived from the tab rail alpha, weighted toward the visible lower tab edges.
  - Rejected as the default because it was still too faint in the assembled preview.
  - Keeps the shadow attached to the tabs instead of forming a floating bar.

- `home-v5-notebook-shadow-grounded-visible.png`
  - 1593x1275.
  - Transparent PNG, alpha preserved.
  - Derived from the notebook bottom/right contact edges with a visible contact seam plus a wider floor falloff.
  - Rejected as the default because it was visible but still weaker than the reference mockup cast shadow.

- `home-v5-tab-rail-shadow-grounded-visible.png`
  - 2231x1150.
  - Transparent PNG, alpha preserved.
  - Derived from the visible lower tab edges with a stronger contact seam.
  - Rejected as the default because it was visible but still weaker than the reference mockup cast shadow.

- `home-v5-notebook-shadow-table-cast.png`
  - 1703x1370.
  - Transparent PNG, alpha preserved.
  - Stronger table cast candidate generated from the notebook lower and right edges.
  - Reference-only candidate; superseded by `home-v5-notebook-shadow-mockup-cast.png`.

- `home-v5-tab-rail-shadow-table-cast.png`
  - 2327x1226.
  - Transparent PNG, alpha preserved.
  - Stronger table cast candidate generated from the tab rail lower edges.
  - Reference-only candidate; superseded by `home-v5-tab-rail-shadow-attached.png`.

- `home-v5-notebook-shadow-mockup-cast.png`
  - 1813x1470.
  - Transparent PNG, alpha preserved.
  - Derived from the notebook bottom edge, right edge, and lower-right corner weight.
  - Default notebook shadow asset for implementation.
  - This is the closest asset to the reference mockup's book-on-table shadow.

- `home-v5-tab-rail-shadow-mockup-cast.png`
  - 2397x1296.
  - Transparent PNG, alpha preserved.
  - Derived from the three tab lower edges with a visible contact seam and table falloff.
  - Reference-only candidate; rejected as the default because its larger canvas can place the darkest shadow too far left/down from the actual tab rail.

- `home-v5-tab-rail-shadow-attached.png`
  - 1927x1076.
  - Transparent PNG, alpha preserved.
  - Same width and same origin as `home-v5-shortcut-tab-rail-deeper.png`; only the canvas height extends downward.
  - Derived from each tab's lower torn edge and three separate short cast pools.
  - Default tab rail shadow asset for implementation.

- `home-v5-shortcut-tab-rail-deeper.png`
  - 1927x816.
  - Transparent PNG, alpha preserved.
  - Optional replacement for `../home-v4/home-v4-shortcut-tab-rail-candidate.png`.
  - Tab bodies are deeper and stronger; tape was kept close to the original to avoid rectangular tint artifacts.

## Do Not Use

- Generated preview `call_NMg0gzfTpPVFhymghFSnTsY2.png`.
- Generated preview `call_FdDkux3GBWjsun3wH6TvL49x.png`.

Both preview images were rejected for implementation because they were RGB images without alpha.

## Design Intent

Implement toward `references/mockups/home-phase200-target-deep-sage.png`.

The pass succeeds only if:

- the notebook reads as a darker deep olive/forest sage object,
- the notebook is visibly larger than the current Phase 199 screenshot,
- the notebook and tab rail are grounded by contact shadows,
- no rectangular shadow block is visible,
- the default shadows are `home-v5-notebook-shadow-mockup-cast.png` and `home-v5-tab-rail-shadow-attached.png`, not solid blurred rectangles,
- Shiori is large enough to read as a character peeking from the title-note tape,
- all Home copy remains live DOM text.
