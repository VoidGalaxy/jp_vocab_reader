# Reading V3 Gate 1A Tall-Desktop Scene

## Candidate

- File: `reading-v3-scene-approved-tall-desktop.png`
- Native size: `1536x1024`
- SHA-256: `498DB4CBAC0DCE7ED209164BC40B7208A7560D9E3BFD58FC393F845333678068`
- Intended viewport range: desktop widths from `1024px` upward when the viewport does not satisfy the wide-scene aspect-ratio condition.
- Wide desktop authority remains `reading-v3-scene-approved-desktop.png` for sufficiently wide desktop viewports.
- Mobile remains the existing V2 mobile scene below `1024px`.

## Visual Direction

The approved wide scene could not fill tall desktop viewports without either leaving a large non-photographic strip below it or cropping the notebook. This candidate provides a separate 3:2 composition: the same warm honey-oak desk, open ruled notebook, upper-left pottery and mat, upper-right leaves, and lower-right cloth, with additional real desk area above and below the notebook.

The notebook is intentionally slightly smaller than in the wide scene so it remains complete at both `1280x900` and `1024x768`. The page surfaces remain large enough for live DOM content, but their safe zones must be remeasured; wide-scene percentages may not be reused.

## Static Crop Previews

- `gate1a-preview-1280x850.png`: the scene region below a 50px desktop toolbar at `1280x900`.
- `gate1a-preview-1024x718.png`: centered cover crop for the scene region below a 50px desktop toolbar at `1024x768`.

Both previews preserve the full notebook, show no separate bottom strip, and retain desk texture to every viewport edge.

## Integration Contract After Approval

- Add a second desktop `<source>` for `min-width:1024px`.
- Select the approved wide source only when both `min-width:1500px` and `min-aspect-ratio:16/9` match. This avoids forcing the panoramic scene onto tall desktop windows.
- Give wide and tall scenes separate native aspect ratios and separate page safe-zone coordinate sets.
- Size the scene to the available desktop height (`100svh - toolbar`) and use a bounded centered cover crop only where required.
- At `1024px`, any crop must remain in desk margin and may not touch the notebook.
- Do not scale the existing wide scene into the tall composition.
- Do not use CSS background duplication, gradients, blur, or a solid fill to complete the viewport.

## Status

Gate 1A approved by the user. No production connection, CSS integration, commit, or push has been performed.
