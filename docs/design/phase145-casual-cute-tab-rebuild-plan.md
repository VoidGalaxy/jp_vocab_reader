# Phase 145+ Casual Cute Tab Rebuild Plan

Reference mockup:

- `docs/design/mockups/phase145-casual-cute-mockup-board.png`

Generated implementation assets:

- `frontend/public/brand/decor/phase145/home-cute-notebook-cover-object.webp`
- `frontend/public/brand/decor/phase145/reading-selected-memo-strip.webp`
- `frontend/public/brand/decor/phase145/study-light-mint-felt-board.webp`
- `frontend/public/brand/decor/phase145/vocab-physical-index-tabs.webp`
- `frontend/public/brand/decor/phase145/deck-cute-cover-tile-atlas.webp`

## Direction

The next phases should not lightly reskin the existing layout. Each tab should remove the remaining old panel/card language when it conflicts with the mockup. The target is a casual, cute study notebook: physical paper tabs, loose memo strips, small book covers, lighter felt, and simple direct actions.

## Tab Comparison

| Tab | Current problem | Target structure | Asset |
| --- | --- | --- | --- |
| Home | The book and wood background still feel composited; bottom dots and bottom white gap weaken the scene. | One soft green notebook object on wood, no dots, no lower white blank zone, shortcuts as cute notes. | `home-cute-notebook-cover-object.webp` |
| Reading | The selected-word/save area is too blended into the page; one-book feeling is good but needs a clearer functional strip. | Open notebook stays unified, but selected words live on a loose memo strip below the page. | `reading-selected-memo-strip.webp` |
| Study | Top action area still reads like an old rigid box; dark green felt dominates the impression. | Light mint board, small pinned mode tabs, card/rating as the hero. | `study-light-mint-felt-board.webp` |
| Vocab | Filter tabs are ambiguous: neither clearly controls nor naturally part of the image. | Real protruding index tabs on the notebook edge, with live labels over physical tabs. | `vocab-physical-index-tabs.webp` |
| Deck | Deck cards are too large and filled by mostly meaningless solid color blocks. | Smaller book-cover cards with meaningful cover art crops and compact shelf labels. | `deck-cute-cover-tile-atlas.webp` |
| Reading/Classify IA | Reading and Classify may not need to be two equal primary tabs. | Treat card-making/classification as a Reading workflow, opened from selected words or a card tray. | Mockup panel 6 only; no asset yet. |

## Implementation Guardrails

- Preserve callbacks, API contracts, SRS, storage keys, auth, shared-deck policy, and feedback payload rules unless a phase explicitly asks for product behavior changes.
- Use generated images as decorative material surfaces only. Do not bake live text into images.
- Keep Shiori as the only app character. Generated assets must not introduce other mascots, animals, people, faces, or Shiori-like substitutes; if a cute character moment is needed, compose the existing Shiori component over the decorative surface.
- Remove old boxes when they compete with the physical mockup surface. Do not stack image assets underneath unchanged admin cards.
- Every visual phase must verify 1280, 390, 375, and 320 widths with real browser checks, `scrollWidth === clientWidth`, and console errors equal to zero.

## Suggested Phase Order

1. Home scene correction.
2. Vocab physical filter tabs.
3. Deck cover/card downsizing.
4. Study top/board rebuild.
5. Reading selected-word strip visibility.
6. Reading/Classify IA decision and prototype.
