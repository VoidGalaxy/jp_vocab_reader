# Browser / Mobile QA Checklist

A repeatable checklist for manual or automated browser QA on this project —
what to check, at what breakpoints, and the tooling traps that produced false
positives/negatives in past QA passes. This is a supplement to
[beta-release-checklist.md](beta-release-checklist.md) (release-day gate) and
[deployment-checklist.md](deployment-checklist.md) (deploy-time smoke test),
not a replacement — use this doc for the *how* of browser/mobile checks that
those two reference more briefly.

**Never write real URLs, tokens, or database values into this file.** Use
`<backend-base-url>` / `<frontend-url>` placeholders.

## 1. Viewports and overflow

Check each screen at these widths: `1280` (desktop), `390` (common phone),
`375` (iPhone SE-class), `320` (smallest common phone).

- [ ] Horizontal overflow check: compare
      `document.documentElement.scrollWidth` against
      `document.documentElement.clientWidth` — not `window.innerWidth` (see
      "Automation gotchas" below for why `innerWidth` can lie mid-session).
      `scrollWidth > clientWidth` means something is overflowing.
- [ ] Fixed bottom nav does not overlap primary CTA / rating buttons —
      check with the page scrolled to the bottom of real content, not just
      the initial viewport.
- [ ] No new console errors or warnings on page load or on the interaction
      being tested.
- [ ] A `fullPage` screenshot showing the fixed bottom nav overlapping
      content can be a **stitching artifact** of the screenshot tool, not a
      real bug — a fixed-position element gets composited into every
      stitched segment. Confirm any nav-overlap finding from a screenshot
      against a live scroll/viewport measurement (actual `scrollY` +
      bounding-rect check, or eyes-on in a real window) before reporting it.

## 2. Long-content regressions

Recurrent regression class: pill/tag/label elements sized to `nowrap`
content overflow their container once real content is longer than the
sample data used during development.

Test with deliberately long values in each of these fields: reading text,
`part_of_speech`, `base_form`, `meaning`, and example sentence — both
individually and in combination on one card/row.

- [ ] `.token-sheet-meta-tag`, `.vocab-item-secondary-tag`, and any similar
      pill/tag class: check they wrap or truncate instead of forcing
      `min-content` overflow on their row.
- [ ] `<select>` options with long text: `width: 100%` on the `select` alone
      is not sufficient — a bare `<select>` can size itself to its longest
      `<option>`'s intrinsic content width regardless of `max-width: 100%`.
      Confirm the actual ellipsis/wrap/truncation behavior, don't assume
      `width: 100%` handles it.
- [ ] Study card: after revealing the answer, rating buttons are not hidden
      behind the fixed bottom nav at any of the four viewports above.

## 3. Vocab management / custom terms flow

- [ ] 더보기 → 덱/공유 관리 → 덱 관리 / 사용자 정의 용어 / 덱 공유 — each
      sub-flow opens and reaches real content (not a blank or stuck panel).
- [ ] Destructive actions (deck delete, custom term delete) still show a
      confirm step — do not silently execute on first tap/click.
- [ ] Delete-button tone is consistent between deck delete and custom term
      delete (same visual weight/color for the same severity of action).
- [ ] Copy is correct for each list state: no deck selected, empty list,
      and list with existing items — three distinct states, not just the
      happy path.
- [ ] Entering "사용자 정의 용어 관리" actually scrolls to / reveals the real
      content list, not just the section header.

## 4. Shared deck long-list flow

Check from **both** an owner's and a subscriber's point of view.

- [ ] Button/state correctness for each condition: published, unpublished,
      import, open, unpublish, republish — verify the button set shown
      matches the deck's actual state and the viewer's relationship to it
      (owner vs. subscriber vs. neither).
- [ ] With 80+ decks in a list, pagination ("더 보기") loads more items
      correctly and doesn't drop or duplicate rows.
- [ ] Both the top and bottom close controls on a long list/detail view
      work.
- [ ] Status `<select>`/filter and search narrow the list correctly.
- [ ] If checking shared-deck policy text against code (e.g. unpublish
      visibility rules), only confirm they still match — do not change
      policy, seed/reseed data, or touch `shared_decks` rows as part of a
      QA pass. See "Shared Deck — Final Test" in
      [beta-release-checklist.md](beta-release-checklist.md#7-shared-deck--final-test)
      for the full policy and its production-transition history.

## 5. Automation gotchas (CDP / no-Playwright environments)

This project has no Playwright (or any browser-automation package) installed
in either the backend venv or frontend `node_modules` as of Phase 47 — prior
QA phases drove headless Chrome directly over the Chrome DevTools Protocol
with a small dependency-free WebSocket client instead of installing one.
If reproducing that setup, keep these in mind:

- [ ] `window.innerWidth`/`innerHeight` can drift to wildly wrong values
      after a mobile-emulated `<select>` interaction involving a long
      option string — observed jumping from `390` to `700+` across further
      interactions in the same session, while `document.documentElement
      .clientWidth` and `window.visualViewport.width` stayed correct. Use
      `clientWidth`, never `innerWidth`, for overflow checks once any long
      `<select>` has been touched in that session.
- [ ] Smooth scrolling (`scrollIntoView({behavior: 'smooth'})`,
      `scrollTo({behavior: 'smooth'})`) can silently no-op in headless or
      off-screen-positioned Chrome — `scrollY` can stay at `0` indefinitely
      even though the same code works in a real, visible browser. Do not
      report a smooth-scroll-triggered auto-scroll as broken based on a
      `scrollY`-in-harness check alone; verify by code review (effect
      dependency array / ref wiring) or a different signal instead, and
      mark the finding inconclusive if that's all you have.
- [ ] Treat automated results as one signal, not the final word: combine
      DOM/`scrollWidth` measurements, screenshots, and (when possible)
      direct manual interaction before reporting a layout or scroll finding
      as confirmed.
