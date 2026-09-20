# Reading V3 Execution Plan

## Why The Work Kept Missing The Target

### 1. Mechanical proof replaced visual proof

Hashes, pixel-diff counts, DOM coordinates, builds, and click tests were treated as if they proved design success. They only prove bounded technical properties. The first rejected Gate A candidate preserved the center perfectly but still showed obvious side bars. The second quilting candidate had sophisticated metrics but still exposed rectangular patches and seams at normal viewing size.

### 2. The original defect was not tested first

The redesign began because the Reading scene exposed unrelated side areas on wide screens. Gate B tested 1280 but not 1920, while the existing `1640px` Reading canvas cap remained in production CSS. The implementation therefore passed its checklist without testing the viewport that triggered the work.

### 3. Asset and layout contracts contradicted each other

The early brief required both a completely natural outpaint and every old center pixel to remain unchanged. Edge props crossed the old frame, so a hard pixel lock guaranteed a seam. The better direct ImageGen scene solved the visual problem by superseding the old center plate instead of forcing it back into the new photograph.

### 4. Too much scope was bundled into one completion claim

Desktop asset replacement, input redesign, analyzed-state continuity, long-text scrolling, mobile preservation, and functional QA were reported as one Gate B. A strong result in one area hid missing work in another. The analyzed footer and wide-screen fill were left incomplete while the phase was still described as complete.

### 5. Self-reporting was accepted without independent evidence

The implementer measured and judged its own result, then deleted the screenshots. The final reviewer could not compare the actual states against the approved mockups. Statements such as "not reproducible" or "visually confirmed" must never replace retained screenshots.

### 6. Scope language became an escape hatch

Visible gaps were labeled "out of scope" even when they were present in an approved authority image or central to the original defect. Scope should protect behavior and unrelated tabs, not excuse incomplete target-state parity.

### 7. CSS accumulated overrides instead of one state model

The implementation added a large desktop override block on top of old V2 roles. Some role redefinition was correct, but the growing cascade made it easy to miss higher-level constraints such as `.library-canvas-reading` and `.app-shell-content`. Geometry must be traced from viewport to shell to scene to page before styling individual controls.

## Fixed Authorities

These files are the only visual authorities for Reading V3:

1. `reading-v3-scene-approved-desktop.png` - desktop scene, native `1849x851`.
2. `reading-v3-input-approved.png` - pre-analysis hierarchy and controls.
3. `reading-v3-analyzed-reference.png` - analyzed reading and dictionary hierarchy.
4. `DESIGN_SPEC.md` - behavior, copy, typography, responsive, and failure rules.

Rejected quilting candidates and earlier V2 screenshots are diagnostic references only. They may not be used as implementation targets.

## Responsibility Split

- Claude implements one bounded gate.
- Codex independently reads the diff and checks the real screenshots.
- The user approves visual first impression before the next gate.
- The implementer cannot self-approve its own visual result.

No gate advances from a prose report alone.

## New Gate Sequence

### Gate 1: viewport and scene geometry only

Goal: the approved scene fills the intended desktop surface without unrelated side bars, stretching, or crop surprises.

Allowed changes:

- Reading-only shell/canvas width rules.
- Scene ratio and image sizing.
- Reading page safe-zone coordinates only when required by the approved asset.

Required evidence:

- Full screenshots at `1920x960`, `1280x900`, and `1024x768`.
- One contact sheet showing all three at the same visual scale.
- Measured viewport, shell, canvas, frame, and image rectangles.
- `scrollWidth === clientWidth` at every width.

Failure:

- Any unrelated background strip at 1920.
- The book is enlarged, cropped, stretched, or vertically clipped to hide a strip.
- Work on input controls or analyzed-state styling begins before Gate 1 approval.

### Gate 2: input state only

Goal: match `reading-v3-input-approved.png` using live DOM on the approved page safe zone.

Required states:

- Empty placeholder.
- Realistic four-to-six-line Japanese text.
- Focused editor.
- Analyzing with progress and cancel.
- Deck loading, no-deck, storage warning, and one-line error.

Required evidence:

- `1920`, `1280`, and `1024` screenshots for normal input.
- `1280` screenshots for every exceptional state.
- Computed rectangles for title, editor, metadata, deck selector, and action.

Failure:

- The editor reads as a card, slip, or floating panel.
- Fixed controls move when text grows.
- Button or selector labels wrap or collide.
- Mockup copy, hierarchy, or typography is materially different.

### Gate 3: analyzed state and continuity only

Goal: the editor becomes the reader in place, and the right page becomes the dictionary ledger without a structural jump.

Required states:

- Analyzed with no selected word.
- Selected word with dictionary detail.
- Options open.
- Re-edit source open.
- Save basket empty and populated.

Required evidence:

- Before/after overlay comparing the first input line and first analyzed line.
- Exact x/y/font-size/line-height values.
- Screenshots at `1920`, `1280`, and `1024`.

Failure:

- The first line moves.
- A translucent reader card returns.
- The approved analyzed footer/action hierarchy is omitted as "out of scope."
- Right-page content touches the crease, cover, props, or page edge.

### Gate 4: long-text and behavior verification

Goal: prove the design remains usable with real content and preserve all behavior.

Test texts:

- Short sample.
- About 2,000 Japanese characters.
- At least 10,000 Japanese characters with multiple paragraphs and long unbroken segments.

Required checks:

- Only intended page/editor regions scroll.
- Title, metadata, and primary controls remain stable.
- Scroll restoration works after token selection and re-edit.
- Analyze, progress, cancel, deck recovery, token selection, basket save, meaning edit/report, and navigation work.
- Mobile `390`, `375`, and `320` retain the existing silhouette and have no horizontal overflow.
- Backend QA uses session-only scratch SQLite. Never access Neon or production data.

### Gate 5: final candidate

- Run `npm run build` once.
- Run `git diff --check`.
- Check image 404s, failed requests, and console error/warning counts.
- Smoke all other tabs for opening and overflow only.
- Preserve the complete screenshot set and machine-readable measurements under a versioned QA directory until commit approval.
- Stop all local processes only after evidence has been copied to its final path.

## Evidence Rules

- Every screenshot cited in a report must exist at the reported path.
- Reports begin with the visual verdict, not hashes or changed-file counts.
- A contact sheet is mandatory for breakpoint comparison.
- "Looks correct" must name the inspected screenshot and viewport.
- Known failures must be shown, not hidden from the final report.
- If browser automation fails, the gate stops. Build-only evidence cannot substitute for browser QA.

## Prompt Rules

- One prompt handles one gate.
- State the exact original defect and test it at the first viewport.
- List the visual authority files near the top.
- Separate required changes, forbidden changes, and acceptance evidence.
- Do not ask for long historical explanations or self-congratulating proof.
- Allow one correction pass. A second miss stops the gate for a new structural decision.
- Never permit commit, push, merge, or cleanup before independent approval.

## Immediate Recovery From The Current Gate B

Do not discard the useful work already present. Continue from the current working tree with this order:

1. Gate 1 correction: remove the Reading-only `1640px` and parent `1680px` width bottlenecks without changing shared navigation or other tabs.
2. Capture and approve `1920x960`, `1280x900`, and `1024x768` before touching further styling.
3. Gate 2 audit: compare the existing input implementation against every required input state and fix only proven differences.
4. Gate 3 completion: implement the missing analyzed footer/action hierarchy and retain state-transition evidence.
5. Gate 4 long-text QA with retained screenshots and measurements.

The current build pass and asset hash are useful evidence, but they do not advance any visual gate by themselves.
