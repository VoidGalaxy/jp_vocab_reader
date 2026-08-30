# Home V4 Asset Manifest

Generated for Phase 195 target-mockup-driven Home reconstruction.

## Recommended Assets

- `home-v4-desk-surface-desktop.png`
  - Desktop opaque oak desk background.
  - 1672x941.
  - Use as Home desktop body/background plate.
- `home-v4-desk-surface-mobile.png`
  - Mobile opaque oak desk background.
  - 941x1672.
  - Use as Home mobile body/background plate.
- `home-v4-shortcut-tab-rail-candidate.png`
  - Transparent shortcut tab rail.
  - 1927x816.
  - Corner/top alpha verified as `0,0,0,0,0`.
  - Use as candidate replacement for three independent tab PNGs.
- `home-v4-cover-emboss-mark.png`
  - Transparent cover emboss overlay.
  - 1367x1150.
  - Corner/top alpha verified as `0,0,0,0,0`.
  - Place over lower-right notebook cover at low opacity.
- `home-v4-cta-ticket.png`
  - Transparent sage CTA ticket.
  - 2014x781.
  - Corner/top alpha verified as `0,0,0,0,0`.
  - Candidate replacement for `home-v3-cta-stamp.png`; compare baked shadow before wiring.

## Reference Only / Do Not Wire

- `home-v4-notebook-cover-embossed.png`
- `home-v4-notebook-cover-embossed-extracted.png`

Both notebook-cover files failed alpha verification: corner/top alpha returned `255,255,255,255,255`. They contain opaque background/checkerboard and should not be wired into the app. Use existing `../home-v3/home-v3-notebook-cover.png` plus `home-v4-cover-emboss-mark.png` instead.

## Design Intent

These assets exist to stop the repeated coordinate-adjustment loop. Home implementation should match `references/mockups/home-phase195-target-mockup.png` and `references/mockups/home-phase195-target-mobile.png`, with generated placeholder text ignored and real UI copy rendered as DOM.
