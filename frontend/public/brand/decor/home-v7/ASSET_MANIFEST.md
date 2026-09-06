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

- `home-v7-notebook-tabs-contact-shadow.png` -- SUPERSEDED, not wired.
  - 1298x1007, transparent PNG, alpha preserved, same canvas size/origin
    as `home-v7-notebook-tabs-shadow-plate.png` so `background-size:100%
    100%` lined the two up without any separate offset math in CSS.
  - Home v7 shadow grounding fix -- generated (not hand-drawn) from the
    cleaned plate's own alpha channel: two blurred, down-right-offset
    copies of the plate's silhouette combined into one shadow -- a tight
    small-radius blur (offset ~5-7px) for a darker near-contact seam, and
    a wider soft-radius blur (offset ~18-26px) for the broader outward
    fade, unioned together and rendered as one dark warm-brown (RGB
    32,22,11) layer.
  - Home v7 target mockup parity pass -- superseded by
    `home-v7-notebook-tabs-contact-shadow-target.png` below: pixel-sampled
    side by side against the confirmed target mockup
    (`home-v7-baked-scene-target.png`), this file's shadow measured
    noticeably weaker and narrower than the target's own (target's
    near-contact brightness dropped to ~60-70 out of a ~140 desk baseline
    over a visibly wide spread; this file's equivalent zone was only a
    few px wide before fading). Its own same-size-as-plate canvas also
    clipped its wider soft layer's tail before it reached zero alpha
    (alpha was still ~33/255 at the very last row). Left on disk for
    reference/audit, not deleted, but no longer referenced from
    globals.css.

- `home-v7-notebook-tabs-contact-shadow-target.png` -- SUPERSEDED, not wired.
  - 1458x1167 (1298+160 x 1007+160), transparent PNG, alpha preserved.
    Canvas is the plate's own 1298x1007 PLUS an 80px padding margin on
    every side -- see below for why.
  - Home v7 target mockup parity pass -- same generation method as the
    superseded file above (two blurred, down-right-offset copies of the
    cleaned plate's alpha channel, tight seam + soft falloff, unioned into
    one dark warm-brown layer), with two changes calibrated against pixel
    samples taken directly from the confirmed target mockup rather than
    guessed: larger blur radii and offsets (tight ~10-14px, soft
    ~38-52px) so the falloff distance/darkness matches the target's own
    measured profile, and an 80px padding margin baked into the canvas so
    that larger spread has room to fully fade to transparent instead of
    being clipped at a same-size-as-plate canvas edge (the exact defect
    found in the superseded file).
  - Applied via `.home-v4-notebook::before` (globals.css), behind
    `.home-v4-notebook-img`'s z-index so only the part that peeks out past
    the plate's own opaque edges is visible -- `pointer-events:none`, does
    not affect the three shortcut buttons' own click targets. Because the
    canvas now has an 80px margin the plate itself doesn't have, the CSS
    rule's own box is NOT `inset:0` any more -- it's offset/sized by that
    80px expressed as a percentage of `.home-v4-notebook`'s box (80/1298 ≈
    6.163% horizontally, 80/1007 ≈ 7.945% vertically; see the CSS comment
    on `.home-v4-notebook::before` for the exact values), not a
    hand-picked number.
  - Rejected approach (unchanged from the prior pass): a
    `filter: drop-shadow(...)` added directly to `.home-v4-notebook-img`
    traces the whole plate's opaque rectangle-ish silhouette rather than a
    true soft falloff, and tuning it previously required compensating
    `--cta-top`/note-padding shifts elsewhere that broke the CTA ribbon's
    visibility on mobile 390 (confirmed broken via screenshot in an
    earlier pass, not assumed). A static shadow-only image avoids that
    failure mode entirely since it has no effect on any other element's
    layout.
  - Home v7 final-target parity pass -- superseded by
    `home-v7-notebook-tabs-contact-shadow-v4.png` below: isolated (hiding
    `.home-v4-notebook-img` and screenshotting `::before` alone), this
    file rendered as a near-opaque copy of the plate's own silhouette with
    only a thin blurred RING around its edge -- i.e. almost the entire
    shadow sat exactly UNDER the opaque plate (invisible by construction,
    since the plate paints over it) and only a ~15px-wide ring peeked out,
    which at the notebook's real render scale (~0.54x at a 1280px
    viewport) shrank to a handful of pixels -- confirmed via a cropped
    screenshot of the notebook's bottom-right corner showing bare desk
    with no visible darkening at all. This is the same "shadow reads as a
    rectangle"/near-invisible failure the brief warned against, just
    baked into a PNG instead of drawn in CSS -- the offset (10-14px tight,
    38-52px soft, in the plate's own 1298px-wide coordinate space) was
    simply too small relative to the plate to read at typical render
    size. Left on disk for audit, no longer referenced from globals.css.

- `home-v7-notebook-tabs-contact-shadow-v4.png` -- current, wired.
  - 1778x1487 (1298+480 x 1007+480), transparent PNG, alpha preserved.
    Canvas is the plate's own 1298x1007 plus a 240px padding margin on
    every side (up from the superseded file's 80px -- the larger
    offset/blur below need more room to fully fade to transparent before
    hitting the canvas edge).
  - Home v7 final-target parity pass -- generated with headless Chrome's
    own Canvas 2D API (`document.createElement('canvas')` + `source-in`
    compositing + `ctx.filter = 'blur(Npx)'`) rather than by hand or via
    an image-editing tool, since neither PIL/Pillow nor ImageMagick was
    available in this environment -- see the generation script referenced
    from this pass's own report for the exact technique. Built from two
    offset+blurred copies of the plate's own alpha silhouette (same
    two-layer method as the superseded file: a tight near-contact seam
    plus a wide soft falloff, unioned into one dark warm-brown layer), but
    with substantially larger offsets and blur radii, tuned by iterating
    against real notebook-scale screenshots (not the plate's own native
    resolution) until the shadow was clearly visible along the bottom and
    right edges, and under each tab individually, at a normal 1280px
    screenshot: tight layer offset (30,40)px / blur 22px / `rgba(15,9,5,
    0.85)`, soft layer offset (125,155)px / blur 85px / `rgba(20,13,7,
    0.58)`. Because the mask comes directly from the plate's own alpha
    channel (including the gaps cut between the three tabs), the
    generated shadow naturally shows each tab with its own separated
    contact shadow rather than one connected rail/bar underneath all
    three.
  - Applied the same way as the superseded file: via
    `.home-v4-notebook::before`, behind `.home-v4-notebook-img`'s
    z-index, `pointer-events:none`. The CSS box's left/top/width/height
    percentages changed to match this file's own 240px-of-1298px /
    240px-of-1007px padding ratio (see the rule's own comment in
    globals.css for the exact values) -- they are NOT the same numbers as
    the superseded file's, since the canvas padding changed.

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
