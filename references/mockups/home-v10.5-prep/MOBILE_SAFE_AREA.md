# Home V10.5 Mobile Safe-Area Preparation

Status: V1.1 validated for implementation. V2 is rejected.

## V1.1 correction

The first 850x1850 V1 wiring still forced a width of about 357px at
320x844. That cropped the title safe zone to 2.6px from the viewport edge
and clipped the subtitle at every measured mobile width. V1.1 extends only
the desk to 850x2090 while preserving the approved center composition.

- Ratio: 850 / 2090 (about 0.4067:1).
- Mobile width: `max(100vw, calc(40.67svh - 28.47px))`.
- No horizontal breakpoint shift.
- Browser-crop previews passed at 390x844, 375x812, 320x844, and 320x700.
- Text coordinates use the note's interior safe area, not its flood-filled
  outer paper boundary.

## Current failure

- The V10.3 mobile scene is 941x1672 (0.5628:1).
- At a 320x844 viewport, Home has about 774px of scene height. The current
  height-cover calculation renders the art about 435.6px wide and crops about
  57.8 screen pixels from each side, equivalent to roughly 125 source pixels.
- The title zone begins at source x=84.7 and the notebook begins near x=85, so
  both are clipped before CSS text coordinates can solve the problem.

## Required V10.5 source geometry

- Create a separate mobile-only full scene at approximately 941x2048
  (0.4595:1) or an exact higher-resolution multiple of that ratio.
- Preserve the current notebook, note, CTA, Shiori, tabs, colors, materials,
  lighting, and shadows unchanged in apparent scale.
- Extend the wooden desk above and below the existing composition instead of
  shrinking the notebook or moving it sideways.
- Keep at least 55 source pixels of horizontal safety around every essential
  object. Keep generous empty desk above and below for vertical crop allowance.

At 320x844 this ratio reduces horizontal source crop to about 47px per side,
keeping the existing notebook and note inside the visible canvas. At 390x844 it
allows modest vertical crop using intentionally empty desk margins rather than
cutting the central composition.

## Locked behavior and implementation rules

- Desktop V10.4 remains unchanged.
- Build and approve a text-free mobile target before changing production code.
- Use one opaque baked scene. Do not add CSS shadows, filters, separate props,
  or runtime image layers.
- Keep Korean labels, hints, icons, and actions as live DOM content.
- Re-measure all mobile overlay coordinates from the approved V10.5 source;
  never reuse V10.3 percentages.
- Preserve callbacks, routing, API, auth, storage, SRS, and backend boundaries.

## Approval and QA gate

1. Generate and visually approve the V10.5 mobile target.
2. Copy the approved target byte-for-byte into a versioned production folder.
3. Connect only the mobile image and mobile coordinate set.
4. First browser judgment at 390x844 and 320x844.
5. Final checks at 390, 375, and 320 plus a desktop V10.4 smoke check.
6. Verify full title visibility, notebook edges, CTA, tabs, overflow, image
   requests, console state, and all five Home actions.
