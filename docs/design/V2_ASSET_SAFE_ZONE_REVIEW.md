# V2 Asset Safe-Zone Review

Date: 2026-08-24

Branch: `phase-164`

Contact sheet:

- `docs/design/mockups/v2/v2-asset-contact-sheet-safe-zones.png`

Runtime assets:

- `frontend/public/brand/decor/v2/`

Source masters:

- `docs/design/source-assets/v2-generated-png/`

## Review Rule

These assets are not UI screenshots. They are scene anchors. The implementation
must put live DOM text, buttons, state, and Shiori on top of them. If a tab
keeps the old card/form/filter/dashboard skeleton and merely swaps the
background, the asset has been misused.

## Verdict Table

| Tab | Desktop Asset | Mobile Asset | Verdict | Implementation Note |
| --- | --- | --- | --- | --- |
| Home | `v2-home-notebook-desktop-16x9.webp` | `v2-home-notebook-mobile-9x16.webp` | Pass | Use one hero cluster. Title, CTA, shortcuts, and Shiori must overlap the notebook scene, not form a separate header/column. |
| Reading | `v2-reading-open-book-desktop-16x9.webp` | `v2-reading-page-mobile-9x16.webp` | Pass | Keep original text dominant. Input/textarea must become a distinct slip or sheet, not another same-colored book layer. |
| Vocab | `v2-vocab-index-notebook-desktop-16x9.webp` | `v2-vocab-index-mobile-9x16.webp` | Pass | Broad tabs are safe. Delete the old filter panel silhouette instead of restyling it. |
| Study | `v2-study-felt-board-desktop-16x9.webp` | `v2-study-board-mobile-9x16.webp` | Pass | Board is dominant. Quick-start, review card, completion, and rating stamps must live on one board surface. |
| Shared Deck | `v2-shared-bookshelf-desktop-16x9.webp` | `v2-shared-bookshelf-mobile-9x16.webp` | Pass | Use book spines as the deck items. Do not recreate deck cards on top of the shelf. |
| Classify | `v2-classify-card-desk-desktop-16x9.webp` | `v2-classify-card-desk-mobile-9x16.webp` | Pass | Strongest pilot candidate. The flow should read source slip -> stamp -> card tray before any form semantics are noticed. |
| Stats | `v2-stats-logbook-desktop-16x9.webp` | `v2-stats-logbook-mobile-9x16.webp` | Pass | Use ledger rows and memo slips. Do not reintroduce dashboard metric cards or a right widget panel. |

## Safe-Zone Findings

### Home

The desktop and mobile assets both have a strong central notebook object and
usable overlay zones. The implementation risk is not the asset; it is placing
the title and shortcuts outside the notebook context. The home scene should be
one physical cluster.

### Reading

Both assets provide large calm reading surfaces. The desktop book has separate
left/right zones that can support reader text and inspector content. The mobile
page has enough lower room for a compact inspector. Main risk: textarea/input
contrast. Use a visibly separate slip/sheet surface for input.

### Vocab

The Vocab assets directly address the previous tab-label failure: the tabs are
broad and label-safe. Implementation must remove old filter/search panel
framing and make filtering feel like touching physical index tabs.

### Study

The board assets have clear zones for quick-start notes, active review, and
rating stamps. Implementation should avoid placing a large white admin card on
the board. The live review card can be paper-like, but it must look pinned to
the board.

### Shared Deck

The regenerated desktop asset fixes the sparse-right-wall problem. Both
desktop and mobile assets have enough book-spine density to support a real
bookshelf layout. Deck titles and state must be printed on or attached to
spines, not placed in card footers.

### Classify

This is the best first V2 pilot. The source slip, stamp zone, and card tray are
already spatially connected. That gives implementation a clear replacement for
the old form panel: source input becomes the slip, action becomes the stamp,
and result/progress becomes the card tray.

### Stats

The logbook assets provide explicit stamp, ledger, and memo-slip areas. The
desktop asset can support a two-page spread; the mobile asset can support a
single vertical journal page. Do not keep dashboard cards inside the logbook.

## No Further Asset Blockers

No additional raster assets are required before the first implementation phase.
Small transparent cutouts may be generated later only if a specific V2
component needs them, such as a stamp button, pulled-book detail, or finished
card bundle. Do not pause implementation to collect more decoration.

## Recommended First Implementation

Start with **Classify V2**.

Reason:

- It has the clearest old-structure failure: form panel / textarea / summary
  dashboard.
- The new asset gives the clearest replacement workflow: source slip -> stamp
  -> card tray.
- Success or failure will be obvious in screenshots.

Required opening for the implementation prompt:

1. New scene silhouette: card-making desk.
2. Old structure to discard: classify hero card, form-footer row, large
   textarea panel, dashboard result pills, generic secondary button row.
3. Functional core to preserve: deck select, show-known toggle, draft resume,
   `/analyze`, card classification, save flow, ledger/result behavior.
4. Material anchors: `v2-classify-card-desk-*-*.webp`, source slip, stamp CTA,
   card tray, existing Shiori component.
