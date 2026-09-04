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
  - Home v7 shadow grounding fix -- cleaned: a live Home screenshot showed
    opaque light-grey pixels (RGB ~160-215, all channels within 15 of each
    other, A=255 -- confirmed by pixel sampling, not eyeballed) forming a
    stairstep residue along the notebook's bottom-right corner
    (x:1250-1298, y:780-816). Removed those specific pixels (set to
    transparent) while leaving every other pixel byte-identical to the
    prior version -- verified by re-sampling the page/ribbon/tape/tab-color
    reference points listed below against the pre-cleanup file and finding
    zero differences, so no real cover/page/ribbon/tape/tab-paper content
    was touched, only the residue.
  - Contains the notebook cover, its bookmark ribbon and emboss mark, and
    all three shortcut tabs (with their own tape strips). Desk background
    is NOT included -- this sits on top of the existing `body:has(.home-v4)`
    desk-surface photo/vignette, which stays unchanged. The visible table
    contact shadow is NOT baked into this file (see
    `home-v7-notebook-tabs-contact-shadow.png` below) -- an earlier version
    of this manifest claimed the shadow was baked in here, but the shadow
    that plate actually carried read as too weak/boxy in practice, which is
    what this phase's separate shadow asset replaces.
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

- `home-v7-notebook-tabs-contact-shadow.png`
  - 1298x1007, transparent PNG, alpha preserved, same canvas size/origin
    as `home-v7-notebook-tabs-shadow-plate.png` so `background-size:100%
    100%` lines the two up without any separate offset math in CSS.
  - Home v7 shadow grounding fix -- generated (not hand-drawn) from the
    cleaned plate's own alpha channel: two blurred, down-right-offset
    copies of the plate's silhouette combined into one shadow --
    a tight small-radius blur (offset ~5-7px) for a darker near-contact
    seam, and a wider soft-radius blur (offset ~18-26px) for the broader
    outward fade, unioned together and rendered as one dark warm-brown
    (RGB 32,22,11) layer. Because the shadow comes from the plate's own
    silhouette, the notebook's bottom/right edge AND each of the three
    tabs' own lower torn edges get individually-shaped shadows in one
    pass -- no separate per-tab assets needed, and no risk of the shadow's
    shape disagreeing with the object casting it the way a hand-tuned
    CSS gradient could.
  - Applied via `.home-v4-notebook::before` (globals.css), behind
    `.home-v4-notebook-img`'s z-index so only the part that peeks out past
    the plate's own opaque edges is visible -- `pointer-events:none`, does
    not affect the three shortcut buttons' own click targets.
  - Rejected approach: a `filter: drop-shadow(...)` added directly to
    `.home-v4-notebook-img` was tried first and discarded -- a CSS filter
    on the whole plate traces its opaque rectangle-ish silhouette rather
    than a true soft falloff, and tuning it required compensating
    `--cta-top`/note-padding shifts elsewhere that broke the CTA ribbon's
    visibility on mobile 390 (confirmed broken via screenshot, not
    assumed). This asset avoids that failure mode entirely since it's a
    static shadow layer with no effect on any other element's layout.

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

The notebook plate and Shiori pose came from prior exploration phases and
were promoted into this folder as the final implementation choices. The
contact-shadow PNG was generated in the Home v7 shadow grounding fix pass,
derived directly from the (cleaned) plate's own alpha channel rather than
hand-drawn or sourced from an exploration phase. Treat `home-v7/` as the
durable asset boundary; older failed phase folders/previews were
intentionally removed.
