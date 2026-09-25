# Reading V4 desktop paper tone

Gate D candidate B was copied byte-for-byte from `references/mockups/reading-v4-prep/gateD-qa/`.

| Production asset | Dimensions | SHA-256 |
| --- | --- | --- |
| `v4-reading-open-book-desktop.png` | 1849x851 RGB | `9A064826E4F1F5144528A524850B22F74BC7BF6CB5CBA692D522246CAF89046E` |
| `v4-reading-open-book-desktop-tall.png` | 1536x1024 RGB | `7AB6923D461D92BA505679265D4D4077B7B43E98D9BB9CDA3A375A1FEFE16CBD` |

Only inset paper interiors changed relative to the V3 source assets. Desk, props, cover, page edges, and spine retain the source RGB pixels. The V2 mobile source remains in use. Gate D's report and source/candidate visual comparisons are in `references/mockups/reading-v4-prep/`.

## Reading V4 paper-glare Gate B (local comparison candidate)

The approved Gate A candidate B was copied byte-for-byte to comparison filenames. These sources are not selected by `ReadingTab.tsx` in the current release. The mobile source and picture media conditions are unchanged.

| Local comparison asset | Dimensions | SHA-256 |
| --- | --- | --- |
| `v4-reading-open-book-desktop-paper-b.png` | 1849x851 RGB | `3A27BA5DCA6F7258A169AAA2EB2BB1C9F4EC4F6A7EE479C1E6A0B982823E506F` |
| `v4-reading-open-book-desktop-tall-paper-b.png` | 1536x1024 RGB | `5074BC2E097C1613CD794A60164C4B87BB0614F87B2B39BECE85A42F20A8061A` |

Candidate generation, masks, and protected-pixel verification are in `references/mockups/reading-v4-prep/glare-gateA/`. Only page interiors changed; desk, props, cover, spine, and page edges match the Gate D assets pixel-for-pixel.

## Reading V4 matte paper and smooth fold (local comparison candidate)

The initial matte candidate lowered glare but was too dark. Its files remain available for comparison. These are regenerated full-scene images, not masked pixel edits: desk, props, cover, and page edges also differ from the prior files. The mobile source and picture media conditions are unchanged. Preview screenshots and comparison material are in `references/mockups/reading-v4-prep/seam-tone-prep/`.

| Local comparison asset | Dimensions | SHA-256 |
| --- | --- | --- |
| `v4-reading-open-book-desktop-matte-seam.png` | 1849x851 RGB | `5693E2607B15C7BB9E84408DC0A402AB69FC47C0678B9FE1BA99D43197FD89D3` |
| `v4-reading-open-book-desktop-tall-matte-seam.png` | 1536x1024 RGB | `4B48F3FB5636B6C0DB62CFAD4BA277E679FAFA9AB269F725DEC62FB76B50B2EB` |

## Current desktop sources: lighter paper, smooth fold

The selected tall source is the user's preferred lighter variant (`imagegen-tall-reference.png`). The corresponding wide variant was resized by one pixel from 1848 to 1849 pixels so the existing scene dimensions and page mapping stay unchanged. Both remove the dotted center seam while keeping a shallow physical fold. Previous versions remain untouched.

| Production asset | Dimensions | SHA-256 |
| --- | --- | --- |
| `v4-reading-open-book-desktop-soft-seam.png` | 1849x851 RGB | `A1143DE433B1AD47EF2610857C08F86627418F91A78DF0ED62B596B503E5B9DF` |
| `v4-reading-open-book-desktop-tall-soft-seam.png` | 1536x1024 RGB | `1BEE5D45F58583095E1A3413037521F69E47493A13FA20C4C00ABFA3436F7FE2` |
