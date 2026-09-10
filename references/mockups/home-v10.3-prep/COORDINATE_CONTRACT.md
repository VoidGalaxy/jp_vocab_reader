# Home V10.3 Coordinate Contract

Status: production coordinates wired and browser-verified. Percentages are
relative to each full source image, not the viewport.

## Desktop: 1774x887

Scene ratio: `1774 / 887`.

| Zone | left | top | width | height |
|---|---:|---:|---:|---:|
| Title and subtitle | 26.8% | 26.5% | 14.1% | 11.8% |
| Sample action | 26.5% | 43.4% | 6.8% | 4.0% |
| CTA hit zone | 26.3% | 45.7% | 22.0% | 13.0% |
| Vocabulary tab | 44.3% | 76.4% | 7.7% | 11.3% |
| Review tab | 53.4% | 76.4% | 7.8% | 11.3% |
| Deck tab | 62.6% | 76.4% | 7.6% | 11.3% |

CTA visible content is centered inside its hit zone. Initial box-relative
values: left 24%, top 35%, width 56%, height 39%.

## Mobile: 941x1672

Scene ratio: `941 / 1672`.

| Zone | left | top | width | height |
|---|---:|---:|---:|---:|
| Title and subtitle | 9.0% | 37.4% | 27.1% | 6.9% |
| Sample action | 10.1% | 45.5% | 14.9% | 2.1% |
| CTA hit zone | 8.5% | 47.3% | 31.9% | 5.4% |
| Vocabulary tab | 45.1% | 66.3% | 12.9% | 5.0% |
| Review tab | 60.4% | 66.3% | 13.0% | 5.0% |
| Deck tab | 75.5% | 66.3% | 12.9% | 5.0% |

## Integration rules

1. Replace the source paths and desktop aspect ratio as one atomic change.
2. Apply the desktop and mobile coordinate sets above at the same 768px
   breakpoint used by the `<picture>` source.
3. Do not move the scene image independently from the overlay plane.
4. First visual check: 1920x960 and 390x844.
5. One coordinate correction is allowed only when the rendered live text or
   hit area misses the painted surface.
6. Final QA: 1280, 1024, 390, 375, and 320; verify overflow, image requests,
   console state, and the five Home actions.
