# Home V10.3 Scene Assets

Status: approved target artwork wired into `HomeDashboard.tsx` and verified
across the supported desktop and mobile breakpoints.

## Files

- `home-v10.3-scene-desktop.png`: 1774x887, opaque RGB, 2:1.
- `home-v10.3-scene-mobile.png`: 941x1672, opaque RGB.

The production files are byte-identical to the approved review targets:

- `references/mockups/home-v10.3-prep/home-v10.3-target-desktop-v3.png`
- `references/mockups/home-v10.3-prep/home-v10.3-target-mobile-v1.png`

## Scene contract

- V10.2 material quality is retained: deep forest-green woven cover, cream
  page block, bookmark ribbon, emboss, handmade paper, sage CTA, and the
  yellow/coral/blue tab set.
- The desktop notebook is larger than the old V8 composition but centered;
  it does not extend into the far-right-heavy V10.2 position.
- Desktop props recreate the earlier photographic framing: washi tape on a
  fabric scrap at lower-left, paperclip near upper-right, and cream/gold pen
  cropped by the right and bottom edges.
- Mobile is a separate portrait scene. It uses the paperclip and washi/fabric
  cluster but intentionally omits the pen.
- Notebook, tabs, and props share one baked light and shadow system. Runtime
  CSS shadows and separate prop images are prohibited.
- All text surfaces are blank. Korean labels, hints, icons, and actions remain
  live DOM content.

## Guardrails

- Do not overwrite or delete V10.2 assets during integration.
- Do not stretch either scene or reuse the V10.2 desktop coordinate set.
- The scene art and DOM overlay plane must use the same source aspect ratio,
  size, center point, and crop calculation.
- Re-measure hit zones from these files and allow at most one screenshot-led
  coordinate correction before final QA.
