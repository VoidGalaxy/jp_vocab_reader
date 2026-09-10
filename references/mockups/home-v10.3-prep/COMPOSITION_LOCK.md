# Home V10.3 Desktop Composition Lock

Status: `home-v10.3-target-desktop-v3.png` is the preferred review candidate.
It is not a production asset and must not be wired before visual approval.

## Reference roles

- Material/detail source: Home V10.2 desktop scene.
- Geometry/prop source: screenshot captured on 2026-09-06 at 100337.
- Rejected geometry: the V10.2 notebook scale and right-shifted composition.

## Locked desktop silhouette

Coordinates below are relative to the 1774x887 target canvas.

| Object | Target bounds | Canvas share |
|---|---|---|
| Notebook | x 470-1400, y 90-745 | about 52% canvas width |
| Title note | x 420-910, y 175-460 | overlaps notebook upper-left |
| CTA ticket | x 465-855, y 405-520 | attached to note lower edge |
| Tab group | x 785-1245, y 675-785 | centered under notebook |
| Shiori | x 575-660, y 90-205 | small reading pose behind tape |

The notebook center is locked near x=935, only slightly right of the canvas
center. Increasing its size must not move its right edge beyond x=1420.

## Prop relationships

- Washi tape and fabric scrap form one grounded cluster and are cropped by the lower-left edge.
- The cream-and-gold pen is cropped by the right and bottom edges.
- The gold paperclip sits near the upper-right edge.
- Props frame the scene; none may be moved into the central empty desk area merely to keep it visible at every crop.

## Locked mobile silhouette

`home-v10.3-target-mobile-v1.png` is the preferred mobile review candidate.
It uses the required 941x1672 production aspect ratio and is a separate
portrait composition, not a crop of the desktop target.

| Object | Target bounds | Canvas share |
|---|---|---|
| Notebook | x 85-885, y 465-1125 | about 85% canvas width, centered |
| Title note | x 40-440, y 580-820 | overlaps notebook upper-left |
| CTA ticket | x 80-380, y 790-880 | attached to note lower edge |
| Tab group | x 425-835, y 1095-1200 | centered beneath notebook |
| Shiori | x 170-290, y 480-605 | small reading pose behind tape |

- Mobile uses no pen.
- The paperclip stays near the upper-right edge.
- The washi tape and fabric scrap are partially cropped at the lower-left edge.
- Large empty desk areas above and below the notebook are intentional crop
  allowance for short and tall mobile viewports.

## Material and shadow invariants

- Preserve the V10.2 deep forest-green woven cover, cream page block,
  bookmark ribbon, emboss, paper textures, tab colors, and reading-pose Shiori.
- Keep every text surface blank for live DOM text.
- Notebook contact shadow is darkest at the bottom/right contact edge and
  fades softly over roughly 35-55px.
- Each tab and prop has its own silhouette-following contact shadow.
- No CSS shadow, rectangular shadow plate, black bar, halo, or isolated runtime prop image.

## Workflow gate

1. Approve the desktop target.
2. Approve the separate mobile target; do not scale the desktop layout down.
3. Generate final opaque desktop/mobile full-scene assets at 1774x887 and
   941x1672 respectively.
4. Measure new live-text and hit-zone coordinates from the final assets.
5. Wire the assets only after both scene images and coordinate contract pass review.
