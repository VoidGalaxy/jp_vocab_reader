# Home V10.4 Scene Asset

Status: approved desktop-only replacement, wired into `HomeDashboard.tsx`.

## File

- `home-v10.4-scene-desktop.png`: 1888x833, opaque RGB.
- Desktop-only role: used exclusively by the `(min-width: 768px)` `<source>`
  in `HomeDashboard.tsx`. Mobile keeps the existing V10.3 mobile asset
  (`home-v10.3-scene-mobile.png`) unchanged.

## Source

Copied byte-for-byte from:

- `references/mockups/home-v10.4-prep/home-v10.4-wide-candidate-v1.png`

SHA-256 (identical for source and production copy):

```
150f585937af99163c8c671fce10600e63d540fe899d5e7a13915e3230cbe131
```

## Guardrails

- Do not regenerate, reinterpret, filter, sharpen, resize, or crop this file.
- Do not overwrite or delete the V10.3 desktop/mobile assets.
- Desktop coordinates are re-measured directly from this 1888x833 source, not
  reused from the old 1774x887 V10.3 desktop percentages.
