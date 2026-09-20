# Reading V3 Approved Direction

## Authority

- Input state: `reading-v3-input-approved.png`
- Analyzed state: `reading-v3-analyzed-reference.png`
- Desktop scene: `reading-v3-scene-approved-desktop.png` (`1849x851`)
- Tall-desktop scene: `reading-v3-scene-approved-tall-desktop.png` (`1536x1024`)
- The images define composition, hierarchy, material relationships, and state continuity. Text rendered inside the mockups is reference copy only; production text remains live DOM.

## Three Current Failures

1. The existing start state reads as a translucent form card placed over a book photo instead of writing directly on the page.
2. Input and analyzed states use different visual systems, so submitting text causes a structural jump rather than a continuous reading flow.
3. The capped 1672px desktop scene exposes unrelated side strips on wide screens and weakens focus on the book.

## Target Silhouette

One quiet, wide desk scene contains one dominant open notebook. The left page is a direct-on-paper editor that becomes the analyzed reader without changing its text origin. The right page is an idle Shiori guide before analysis and a restrained dictionary ledger after analysis. There are no floating form cards, inserted sheets, ribbons, stamps, or decorative CTA objects.

## Desktop Scene Asset

- Use `reading-v3-scene-approved-desktop.png` unchanged. Its native size is `1849x851`.
- Use `reading-v3-scene-approved-tall-desktop.png` unchanged for desktop viewports whose available scene area is too tall for the wide composition.
- This direct ImageGen scene is the user-approved second candidate. It replaces the rejected flat-band and quilting candidates.
- Preserve its native ratio, book scale, page geometry, desk margins, props, lighting, and shadows. Do not crop, stretch, regenerate, or recomposite it.
- Measure all desktop live-text safe zones against this asset. Do not reuse the V2 `1672x941` percentages.
- Wide and tall desktop scenes require independent safe-zone coordinate sets. Do not reuse percentages between them.
- The approved scene intentionally prioritizes one coherent photograph over the abandoned requirement that every pixel of the old center plate remain unchanged.

## Input State Contract

- Title: `원문 입력`.
- Supporting copy: `일본어 원문을 붙여넣고 함께 읽어보세요.`
- Sample action: text only, `샘플 문장으로 체험`, with one short coral underline. No icon or dot.
- Editor is transparent and direct on the page. No card background, border, rounded container, or shadow.
- Japanese text uses a Mincho stack and a reading measure of roughly 30-34 full-width characters.
- A slim sage rule marks the editor's left edge; only the active paragraph segment becomes slightly stronger.
- Metadata sits below the editor baseline with 14-16px breathing room: privacy note left, character count right.
- Bottom controls stay fixed while only the editor content scrolls: compact 160px deck selector left and 168-176x44px forest-green analysis button right.
- Analyze button uses one subtle inner border and no outer shadow or double border.
- Empty placeholder: `여기에 일본어 원문을 붙여넣으세요.`
- Error text is one line directly above the privacy/count row.
- During analysis, the action area shows progress and cancel without moving the editor, title, metadata, or page geometry.

## State Continuity

- Input text and analyzed reader text share the same desktop x/y origin, width, font family, font size, and line-height.
- Submitting replaces editor semantics with tokenized reader semantics in place; it must not swap to a new card or shift the first line.
- Right-page idle guide occupies the same ledger origin later used by the dictionary view.
- Long text scrolls inside the page reading region. The physical scene, title, metadata, and primary controls do not grow with content.

## Typography

- Japanese reading text: `"Yu Mincho", "Hiragino Mincho ProN", "Noto Serif JP", serif`.
- Korean controls and guidance: the existing Korean Gothic/sans stack.
- Do not add a font asset in the first pass. Reassess only if browser screenshots show materially inconsistent Japanese metrics.

## Preserved Behavior

Preserve all callbacks, analysis chunking/progress/cancel behavior, deck loading and recovery, tokens, selection, basket saving, meaning editing/reporting, session restoration, scroll restoration, localStorage semantics, API contracts, auth, SRS, feedback, and routing. Long source text remains client/localStorage-only; the privacy statement remains true.

## Mobile Boundary

Desktop and mobile remain separate scene silhouettes. Do not derive mobile by scaling or cropping this desktop mockup. First implementation may leave the existing mobile scene and layout unchanged, provided desktop rules are scoped to `min-width: 1024px` and mobile behavior does not regress.

## Failure Criteria

- The first screenshot still reads as a form card over a photo.
- The book is enlarged or cropped to conceal wide-screen side gaps.
- Input and analyzed text origins differ visibly.
- Long content expands the whole scene or pushes fixed controls away.
- A generic pill, oversized CTA, inserted sheet, ribbon, stamp, or gradient is introduced.
- Live labels or reading text are baked into raster assets.
- Functional reading, save, storage, API, auth, or SRS behavior changes.
