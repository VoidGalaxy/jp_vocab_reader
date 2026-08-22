# Phase 145 Casual Cute Asset Set

Purpose: support the next hard redesign passes, using the casual-cute mockup board as the visual target:
`docs/design/mockups/phase145-casual-cute-mockup-board.png`.

Use the `.webp` files for implementation. The `.png` files are retained as generated sources for review/cropping.

## Assets

| Asset | Intended screen | Use |
| --- | --- | --- |
| `home-cute-notebook-cover-object.webp` | Home | Replace the current flat cover surface with a real object-like notebook cover, including edge, thickness, strap, snap, and soft shadow. |
| `reading-selected-memo-strip.webp` | Reading | Replace the under-separated selected-word/save-dock strip with a loose memo-paper strip so it reads as its own surface. Contains no character art; place the official Shiori component separately if a mascot moment is needed. |
| `study-light-mint-felt-board.webp` | Study | Replace the dark felt board image with a lighter mint board that feels casual and cute instead of heavy. |
| `vocab-physical-index-tabs.webp` | Vocab | Replace ambiguous filter pills/text-on-image treatment with real protruding index tabs. |
| `deck-cute-cover-tile-atlas.webp` | Deck | Replace oversized solid-color deck rectangles with smaller cute book-cover crops. This is a 2x5 atlas; crop each tile by CSS background-position or by deriving per-cover assets. Contains no character or animal motifs. |

## Generated Source Notes

- `deck-cute-cover-tile-atlas.webp` is the usable deck-cover asset. Earlier transparent/cutout attempts produced unwanted background gradients and character/animal motifs, so they are not saved here.
- `vocab-physical-index-tabs.webp` contains seven blank tabs, suitable for live labels over the tabs.
- `reading-selected-memo-strip.webp` includes decorative blank pills; implementation should keep live text on top and should not bake UI copy into the image.
- All assets are decorative. They must use `pointer-events: none` if rendered as elements.
- Character policy: only the official Shiori assets may appear as app characters. Generated decorative assets must not introduce rabbits, cats, people, faces, or Shiori-like substitute mascots.
