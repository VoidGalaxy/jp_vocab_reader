# V2 Scene Asset Manifest

These assets are implementation anchors for the V2 scene redesign. They are
not finished UI screenshots. Live Korean/Japanese text, controls, Shiori, and
state must remain in the React/DOM layer.

Generated source PNG masters are preserved in:

- `docs/design/source-assets/v2-generated-png/`

Runtime assets in this folder are WebP conversions at quality 88. Do not use
the PNG masters from `public/`.

## Desktop 16:9 Scene Bases

| Tab | Runtime asset | Use |
| --- | --- | --- |
| Home | `v2-home-notebook-desktop-16x9.webp` | Main notebook hero cluster background/object anchor |
| Reading | `v2-reading-open-book-desktop-16x9.webp` | Open-book reader/start/result scene base |
| Vocab | `v2-vocab-index-notebook-desktop-16x9.webp` | Physical index notebook with wide tab-safe areas |
| Study | `v2-study-felt-board-desktop-16x9.webp` | Light felt-board review scene base |
| Shared Deck | `v2-shared-bookshelf-desktop-16x9.webp` | Dense physical bookshelf/spine scene base |
| Classify | `v2-classify-card-desk-desktop-16x9.webp` | Card-making desk with source slip, stamp, card tray |
| Stats | `v2-stats-logbook-desktop-16x9.webp` | Study logbook / ledger spread scene base |

## Mobile 9:16 Scene Bases

| Tab | Runtime asset | Use |
| --- | --- | --- |
| Home | `v2-home-notebook-mobile-9x16.webp` | Mobile notebook hero with safe paper-note and tab zones |
| Reading | `v2-reading-page-mobile-9x16.webp` | Mobile reading page with inspector-safe lower area |
| Vocab | `v2-vocab-index-mobile-9x16.webp` | Mobile index page with broad side tabs |
| Study | `v2-study-board-mobile-9x16.webp` | Mobile light felt board with memo and flashcard zones |
| Shared Deck | `v2-shared-bookshelf-mobile-9x16.webp` | Mobile packed bookshelf with simple label-safe spines |
| Classify | `v2-classify-card-desk-mobile-9x16.webp` | Mobile source-slip to stamp to card-tray workflow |
| Stats | `v2-stats-logbook-mobile-9x16.webp` | Mobile study journal with stamp, ledger, memo-slip zones |

## Application Rules

- Use these as scene anchors, not as decorative wallpaper behind unchanged
  `panel-card` or `hero-card` structures.
- Do not bake product copy, Japanese vocabulary, counts, icons, or Shiori into
  derived image assets.
- Keep Shiori rendered through the existing Shiori component family.
- If a tab still reads as a web-app panel after applying an asset, remove the
  old DOM silhouette first; do not add more texture.
- Desktop and mobile assets are separate on purpose. Do not force a 16:9 crop
  into mobile or a 9:16 crop into desktop.
