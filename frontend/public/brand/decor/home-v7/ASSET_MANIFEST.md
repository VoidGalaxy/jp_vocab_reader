# Home V7 Asset Manifest

Prepared for the Home final implementation pass: baked notebook+tabs+shadow
scene plate, plus the confirmed Shiori reading-peek pose.

## Assets

- `home-v7-notebook-tabs-shadow-plate.png`
  - 1298x1007, transparent PNG, alpha preserved (verified: corner alpha 0).
  - Copied from the successful baked-plate exploration and promoted here as
    the canonical Home V7 source. The intermediate exploration folder was
    removed during cleanup so future work starts from this manifest and this
    file, not from the failed shadow iteration set.
  - Contains the notebook cover, its bookmark ribbon and emboss mark, all
    three shortcut tabs (with their own tape strips), and every contact
    shadow (notebook bottom/right, each tab's own table shadow) baked into
    ONE image under one consistent light source. Desk background is NOT
    included -- this sits on top of the existing `body:has(.home-v4)`
    desk-surface photo/vignette, which stays unchanged.
  - Replaces the former separate notebook-cover image + separate tab-rail
    image + separate emboss overlay + CSS-drawn
    `.home-v4-notebook::before`/`.home-v4-tab-rail::after` contact shadows
    all at once -- the tab-color-bleed and
    shadow-reads-as-a-rectangle failures of Phases 195-200 were downstream
    of compositing those as separate CSS-positioned layers; a single baked
    plate can't develop that mismatch since the shadow was painted from
    the actual final geometry, not approximated in CSS.
  - Measured tab hit-zone geometry (pixel-scanned, not eyeballed -- see
    globals.css comments on `.home-v4-shortcut--vocab/--review/--decks`
    for the exact percentages derived from this):
    - vocab (yellow): x 368-562
    - review (coral): x 582-778
    - decks (blue): x 800-996
    - tab row: y 850 (tape top) - 990 (torn bottom edge), of 1007 total
    - notebook cover alone (excluding tabs): x 20-1276, y 20-816

- `home-v7-shiori-reading-peek.png`
  - 1024x1050, transparent PNG, alpha preserved.
  - Cropped from `../../shiori/shiori-bookmark-charm.png` (1024x1536,
    confirmed real alpha via corner-pixel sampling, not assumed) --
    candidate 3 from `references/mockups/home-v7-shiori-pose-candidates.png`,
    selected in `references/mockups/home-v7-shiori-selected-reading-peek.png`.
    Crop keeps the charm ring, head,
    hands, open book, and the dangling leaf charm; trims the lower
    body/legs (not needed for a peek-from-behind-tape placement, and
    cropping them out removes the need for a z-index occlusion trick to
    hide them).
  - This is a Home-only asset. It is NOT added to `Shiori.tsx`'s
    `SHIORI_ASSET_MAP` and does not change any other Shiori call site --
    HomeDashboard.tsx renders it as a plain `<img>`, the same pattern
    already used for the notebook/emboss images, not through
    `ShioriCharacter`.

## Source

Both assets came from prior exploration phases and were promoted into this
folder as the final implementation choices. Treat `home-v7/` as the durable
asset boundary; older failed phase folders/previews were intentionally removed.
