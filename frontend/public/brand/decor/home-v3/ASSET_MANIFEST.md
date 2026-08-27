# Home V3 Asset Kit

Use these assets to rebuild Home as layered stationery objects instead of one large photographic background.

## Core assets

- `home-v3-paper-surface.png`: quiet cream paper background tile/surface.
- `home-v3-notebook-cover.png`: main closed sage notebook object.
- `home-v3-title-note.png`: blank torn title note. Keep Home title and body as DOM text on top.
- `home-v3-cta-stamp.png`: blank green CTA stamp. Keep label text/icon as DOM content.
- `home-v3-shortcut-tab-yellow.png`: blank shortcut paper for vocabulary.
- `home-v3-shortcut-tab-coral.png`: blank shortcut paper for review.
- `home-v3-shortcut-tab-blue.png`: blank shortcut paper for decks.
- `home-v3-privacy-label.png`: blank privacy label. Keep privacy copy as DOM text.

## Optional props

- `home-v3-prop-tape-strip.png`
- `home-v3-prop-paperclip.png`
- `home-v3-prop-pen.png`
- `home-v3-prop-washi-roll.png`
- `home-v3-prop-bookmark.png`

The optional props are useful for composition tests, but prefer the existing clean prop assets in `../phase131/` if any edge matte looks rough in browser QA.

## Implementation notes

- Do not bake Korean/Japanese UI copy into image files. Put text, buttons, links, accessibility labels, and routing targets in the existing React UI.
- Keep Shiori as the existing supplied Shiori asset; do not generate or replace the mascot.
- Use the notebook as a contained hero object, not as a full-screen background image.
- Keep the paper surface visible around the scene so the page does not feel like a cropped banner.
- On mobile, stack title note, CTA, and shortcut tabs around the notebook instead of scaling the whole desktop composition down.

