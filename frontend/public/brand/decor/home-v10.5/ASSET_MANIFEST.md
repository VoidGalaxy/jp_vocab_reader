# Home V10.5 Scene Asset

Status: V1.1 mobile-safe extension, wired into `HomeDashboard.tsx`. V2 was
rejected and is not present in this repository.

## File

- `home-v10.5-scene-mobile.png`: 850x2090, opaque RGB.
- Mobile-only role: used exclusively by the mobile `<img>` in
  `HomeDashboard.tsx`. Desktop keeps the existing V10.4 desktop asset
  (`home-v10.4-scene-desktop.png`) unchanged.

## Source

Copied byte-for-byte from:

- `references/mockups/home-v10.5-prep/home-v10.5-mobile-candidate-v1-1.png`

SHA-256 (identical for source and production copy):

```
0d33eac20c81ce9e50ec3ee753c54b44aa9081bc5ab53f2a912b9c3d9421eab4
```

## Guardrails

- The original V1 center region is preserved pixel-for-pixel from source
  rows 80 through 1769; only the empty desk beyond its top/bottom edges is
  blended into the taller canvas.
- Do not crop, resize, sharpen, filter, or recompress this file.
- Do not overwrite or delete the V10.4 desktop asset or wire the rejected
  V2 candidate.
- Mobile coordinates are re-measured directly from this 850x1850 source,
  not reused from the old 941x1672 V10.3 mobile percentages.
