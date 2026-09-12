# Home Navigation Design Contract

## Approved direction

The visual source of truth is `home-nav-target.png`, derived from candidate J.

- Overall structure: one slim continuous ivory handmade-paper strip.
- Inactive tabs: icon and Korean label printed directly on the paper.
- Separation: short, very faint paper-colored blind-embossed grooves between tabs.
- Active tab: one compact dark forest-green linen patch sewn flush into the strip, with cream icon and text.
- Utilities: Feedback and account remain quiet on the right, separated from the primary tabs by one faint embossed groove.
- Remove the orange active pin completely.

## First-impression hierarchy

1. The Home scene remains the main visual subject.
2. The navigation reads as a physical paper index strip attached to that scene.
3. Only the active tab has material weight.
4. Inactive tabs remain calm wayfinding labels, not individual buttons.

## Scope

- Desktop navigation only: `min-width: 1024px`.
- Keep the current mobile/tablet hamburger and drawer behavior unchanged.
- Preserve tab order, labels, icons, callbacks, `aria-current`, feedback, and account behavior.
- Live labels and icons stay in the DOM. Do not bake text or icons into raster assets.

## Required asset system

Create these text-free assets before production integration:

1. `home-nav-paper-strip.png`: stretch-safe ivory paper surface with subtle fibers and a transparent deckled lower edge.
2. `home-nav-active-linen.png`: transparent dark forest-green linen patch with a fine cream stitched inset; no icon or text.
3. `home-nav-divider-emboss.png`: transparent short blind-embossed vertical groove; paper-colored and low contrast.
4. `home-nav-asset-preview.png`: a full-width text-free assembly proving scale, rhythm, and edge treatment.

The strip may stretch only through a clean center region. Corners and the deckled edge must not visibly distort. Use a three-slice/nine-slice arrangement or an equivalent repeat-safe asset implementation.

## Locked visual measurements

- Desktop strip total height: 56px, including a 5px deckled lower edge.
- Active patch visible height: 40px.
- Active patch corner radius: no more than 4px.
- Active patch stitch inset: 4px from its edge, approximately 1px at rendered scale.
- Tab horizontal gap: 2px; inactive tab internal gap between icon and label: 7px.
- Divider visible height: 18px; opacity must remain in the 0.12-0.2 visual range.
- Icons: 16px. Labels: 13px, weight 700, letter-spacing 0.
- Active foreground: warm cream. Inactive foreground: dark warm brown.

Exact widths may follow label content, but no item may shift when active state changes. Reserve active-patch dimensions in the normal layout.

## Interaction states

- Default: printed ink on paper, transparent button background.
- Hover/focus: slightly deepen ink and show a restrained inset paper impression; no pill fill.
- Active: show the linen patch asset and cream foreground.
- Focus-visible: clear accessible outline outside the stitched inset without orange.
- Disabled: preserve layout and reduce ink contrast only.

## Forbidden outcomes

- Orange/coral pins, dots, separators, or accent marks.
- A rounded toolbar capsule or separate pill for every tab.
- CSS gradients pretending to be paper, linen, stitches, or embossing.
- Box shadows that make the strip or patch float above the scene.
- Full-height divider rules.
- Baked Korean labels or icons.
- Changes to the mobile drawer or navigation behavior.
- Broad edits outside `AppShell.tsx`, the desktop toolbar CSS, and the new nav asset folder.

## Acceptance views

- 1280 and 1024: all seven tabs, feedback, and account fit without horizontal scrolling.
- 390, 375, and 320: existing hamburger/drawer presentation is unchanged.
- Active state does not change toolbar width or neighboring tab positions.
- The Home scene remains visually stronger than the navigation strip.

