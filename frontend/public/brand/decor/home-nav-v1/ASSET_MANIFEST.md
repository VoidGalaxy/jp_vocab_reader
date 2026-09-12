# Home Navigation V1 Asset Manifest

Status: Gate A candidate assets. Not wired into production.

Visual target: `references/mockups/home-nav-prep/home-nav-target.png`.

## Assets

- `home-nav-paper-strip.png` — 1920×64 RGBA. Generated from the approved ivory-paper material direction, then trimmed and alpha-cleaned. The upper 48px is fully opaque; the lower edge retains transparent deckling. SHA-256: `cd18a0fbb2f6b34f043a816a23d0d587cf283c69bec4afe4df15b55a96fa50ee`.
- `home-nav-active-linen.png` — 106×40 RGBA. Generated dark forest-green linen patch, deterministically cropped and masked to remove the generated checkerboard background, then downsampled to rendered size. All four corner alpha values are zero. SHA-256: `8226ae26e9e94b99e520e11c119539a572cbd9c4d36f125c876d7bbd6b88a5a3`.
- `home-nav-divider-emboss.png` — 12×36 RGBA. Deterministic two-layer paper highlight/shadow emboss mark; no ink color or external shadow. All four corner alpha values are zero. SHA-256: `b5dc80e568ca6e3e93b83cfc8c7551410a9cd7bd06811f6222f9a69a180deb50`.
- `home-nav-asset-preview.png` — 1280×72 RGBA. Text-free assembly at the intended desktop scale. SHA-256: `d6f0e88ef0c12954d7dc5d1433224aa123e59f54fb0c3f14310169630f44f913`.

## Integration boundary

- These assets are desktop-only at `min-width: 1024px`.
- Korean labels and icons remain live DOM content.
- Do not regenerate, recolor, blur, shadow, or bake text into these assets during integration.
- The current mobile/tablet hamburger and drawer remain unchanged.

