# Source asset archive

Phase 140 moved these 12 PNGs out of `frontend/public/brand/decor/`
into this docs-level folder. They are the pre-compression originals
Phase 126/127 generated and Phase 131 later cropped from -- never
referenced by any `.tsx`/`.css` (confirmed via
`grep -rohE '/brand/decor/...'` across the frontend before this move),
so nothing in the running app ever requested them over HTTP. Keeping
them in `frontend/public/` meant every deploy shipped ~29MB of files
no browser would ever fetch. They're kept here instead of deleted
because most of them are the direct source of a WebP file still in
production use today -- real provenance, not a hypothetical "might
need it later." Nothing here is served by the app; this is a
version-controlled archive only.

## Mapping: source PNG -> what it produced

| Source PNG (this folder) | Produced (still in `frontend/public/brand/decor/`) | Status |
|---|---|---|
| `phase126/book-cover-green-surface.png` | `phase126/book-cover-green-surface-web.webp` | In production (Home cover) |
| `phase126/open-book-spread.png` | `phase126/open-book-spread-web.webp` | In production (Reading desk scene) |
| `phase126/paper-page-texture.png` | `phase126/paper-page-texture-web.webp` | In production (Reading start page, bookmark inspector) |
| `phase127/study-felt-board-texture.png` | `phase127/study-felt-board-texture-web.webp` | In production (Study board) |
| `phase127/shared-deck-cover-set-candidate.png` | `phase127/shared-deck-cover-set-candidate-web.webp` | In production (Shared Deck covers) |
| `phase127/shared-shelf-wood-strip.png` | `phase127/shared-shelf-wood-strip-web.webp` | In production (Shared Deck shelf) |
| `phase127/vocab-ring-notebook-spread.png` | `phase127/vocab-ring-notebook-spread-web.webp` | In production (Vocab desktop) |
| `phase126/desk-prop-set-candidate.png` | `phase131/desk-prop-{leaf,washi-tape,paperclip,pen}.webp` | In production (Home desk props, Phase 131 crops) |
| `phase126/sticky-note-set-candidate.png` | `phase131/sticky-note-{yellow,coral,blue}.webp` | In production (Home shortcut stickers, Phase 131 crops) |
| `phase127/study-flashcard-stack-candidate.png` | `phase131/study-flashcard-stack-clean.webp` | In production (Study card backing, Phase 131 crop) |
| `phase126/book-cover-green-object-candidate.png` | `phase131/book-cover-green-object-clean.webp` | Not applied -- held per Phase 135 (would duplicate the Home cover's own object) |
| `phase126/deck-cover-template-candidate.png` | none shipped | Never built -- was "reserved for a future Shared Deck pass" per Phase 126, still unbuilt |

Five other `-web.webp` files that used to sit next to these PNGs in
`frontend/public/` (`book-cover-green-object-candidate-web.webp`,
`deck-cover-template-candidate-web.webp`,
`sticky-note-set-candidate-web.webp`, `desk-prop-set-candidate-web.webp`,
`study-flashcard-stack-candidate-web.webp`) were deleted in Phase 140
rather than archived here -- they were full-canvas WebP exports of the
same PNGs above, entirely superseded by Phase 131's individual crops
and carrying no provenance a re-crop would ever start from (anyone
re-deriving a crop would go back to the PNG, not a derived WebP).

If a future phase needs a different crop or a higher-resolution start
point than a currently-shipped WebP, the PNG here is the one to use.

## `shiori-backup/`

Phase 141 moved `frontend/public/brand/shiori/_backup/`'s 9 PNGs here.
This is a *different* set from the mapping table above -- these are a
prior generation of the Shiori mascot's own artwork (confirmed via
`md5sum`: every file here differs from its same-named counterpart still
live in `frontend/public/brand/shiori/`, so this isn't an accidental
duplicate). No code has ever referenced `_backup/` -- it was dead
weight in the deployed `public/` tree (~8.7MB) with no runtime purpose,
but it's kept here rather than deleted since it's a real prior version
of the brand character, useful as a rollback reference if a future
character-art revision needs to compare against or recover the
previous look. Do not restore these into `frontend/public/` without an
explicit decision to roll back the character art -- the live PNGs are
the current, correct brand asset.
