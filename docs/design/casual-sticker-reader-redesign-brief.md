# Casual Sticker Reader redesign brief

Phase 54 restarts the UI redesign direction. Stop treating the recent work as small polish on the old boxed layout. The target direction is a broader redesign named **Casual Sticker Reader**.

## Direction

- Combine the feel of **Sticker Vocabulary Journal** and **Focus Reader Flow**.
- The app should feel like a casual personal reading notebook, not an admin dashboard.
- Desktop should feel like a wide desk with an open notebook/manuscript, sticker notes, a word inspector sheet, and deck booklets.
- Mobile should feel like a focus reader plus sticker journal: read, tap a word, lift it into a sticker, save/review it.
- Keep the app practical and readable. Casual does not mean toy-like.

## Character rule

- Use the existing Shiori mascot style only.
- Shiori is a small rounded bookmark spirit with tassel/bookmark details.
- Do not use a human, anime girl, portrait mascot, or new character.
- Shiori should appear as helper sticker, tab marker, corner guide, idle hint, save stamp, or tiny celebration mark.

## Product truth to preserve

- Users paste or load Japanese text, tap words, save vocabulary, edit personal meanings, review saved words, and browse shared decks.
- Do not duplicate full original reading text into secondary UI, cards, summaries, feedback, or saved payloads.
- Do not change backend/API/SRS/schema/storage/shared-deck policy unless explicitly requested.
- Keep ownership/privacy boundaries intact.
- JLPT recommendation decks are learning references, not official lists.

## Mockup files

- Mobile board: `docs/design/mockups/casual-sticker-reader-mobile.png`
- Desktop board: `docs/design/mockups/casual-sticker-reader-desktop.png`

## Implementation order recommendation

1. App Shell + Home: make the first impression a casual notebook/desk, not a dashboard.
2. Reading + Inspector: focus reader layout with floating word inspector and save tray.
3. Vocab: sticker notebook/grid, less list/admin feeling.
4. Study: review card stack with soft sticker rating buttons.
5. Shared Deck: deck shelf/booklet/sticker-pack treatment.

## Phase 54 recommended scope

Start with **design contract + App Shell/Home redesign**. Use the mockups as directional references, not pixel-perfect specs. Preserve existing state, callbacks, tab routing, auth, and data fetching. Prefer CSS and component composition changes over logic changes.

