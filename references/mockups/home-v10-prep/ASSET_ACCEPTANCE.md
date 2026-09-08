# Home V10 Asset Acceptance Contract

## Locked References

- Desktop composition: `../home-approved/home-grounded-scene-target.png` (1672x940)
- Mobile composition: `home-v10-mobile-scene-candidate.png` (941x1672)
- Shiori pose: `../home-approved/home-shiori-reading-pose-3.png`
- Shadow behavior: `../home-approved/home-ground-contact-shadow-reference.png`

These are opaque, full-scene references. They are not sources for
difference-matting or transparent foreground extraction.

## Production Asset Shape

Create two opaque scene images with the same blank physical safe zones:

- `home-v10-scene-desktop.png`, 1672x940
- `home-v10-scene-mobile.png`, 941x1672

The notebook, title note, CTA ticket, three tabs, Shiori, and every contact
shadow belong to the scene image under one light source. Korean/Japanese text,
icons, and click targets remain live DOM overlays.

## Desktop Overlay Anchors (1672x940)

| Overlay | Safe rectangle in pixels |
| --- | --- |
| Title content | x=392..650, y=260..413 |
| Sample action | x=425..535, y=416..451 |
| CTA label | x=500..718, y=506..560 |
| Vocab tab content | x=746..868, y=753..806 |
| Review tab content | x=926..1048, y=753..806 |
| Decks tab content | x=1096..1217, y=753..806 |

## Mobile Overlay Anchors (941x1672)

| Overlay | Safe rectangle in pixels |
| --- | --- |
| Title content | x=132..418, y=575..748 |
| Sample action | x=145..270, y=751..782 |
| CTA label | x=205..420, y=840..886 |
| Vocab tab content | x=300..420, y=1307..1352 |
| Review tab content | x=470..590, y=1307..1352 |
| Decks tab content | x=644..764, y=1307..1352 |

## Non-Negotiable Asset Gates

1. No transparent foreground plate, difference-matting, or CSS-created shadow.
2. The only runtime visual base is the opaque scene image; it must contain no
   text, icons, browser UI, or rectangular compositing residue.
3. Notebook contact: narrow dark seam at its lower/right edges, then a warm
   soft falloff; it must fade to zero without a visible line or black bar.
4. Each tab has a separate, smaller contact shadow. Tab colors never bleed
   across torn edges or under neighboring tabs.
5. Shiori is part of the scene and physically tucked behind the title-note
   tape. She cannot be a separately positioned overlay.
6. Review the candidate as the full scene at actual desktop and mobile scale
   before any Home component or CSS is changed.
