# Home B2 Binding Scene

All files are cut from, or only extend the plain desk of, one textless source.
No text, buttons or new art are baked into any image; every word and hit zone
on Home is live DOM (`frontend/components/HomeDashboard.tsx`).

## Source

- `references/mockups/home-b2-original-ac-refined/assets/c-tonal-binding.png`
- 1672 x 941, SHA-256 `0D28F6CB3A3191922F347A2AC06BDDC5BCF2D6C98F8E4873D22A8DDD0B9A2263`
- Composition reference: `references/mockups/home-b2-original-ac-refined/shots/c-1600.png`
- Layout study: `references/mockups/home-b2-binding-final/gateA/`
- Reproducible builder: `references/mockups/home-b2-binding-final/gateB/tools/build_production_assets.py`
  (re-checks the source hash, and that the core of the extended plate is pixel-identical to the source)

## Files

| File | Use | Notes |
|---|---|---|
| `home-binding-scene-desktop.png` | >=1024px | 2312 x 1381. Source at offset (320, 220), unchanged except a 32px feather at its outer desk edge; margin is continued desk tone + grain, no mirroring. |
| `home-binding-cover.png` | <=1023px cover | Source crop x 243-1431, y 126-334, drawn as a 9-slice (slice 12 30 12 262). |
| `home-binding-file-tablet-{1..6}.png` | 641-1023px, 3+3 | One compartment per file (source y 388-800), cut at partition centres; row-edge files use the real outer tray wall. |
| `home-binding-file-mobile-{1..6}.png` | <=640px, 2+2+2 | Same cuts with a plain card-paper band (slice rows 132-272) removed, 262px tall. |
