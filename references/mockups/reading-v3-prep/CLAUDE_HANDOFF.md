# Reading V3 Full Scene and State-Continuity Replacement

> Superseded for recovery execution: use `READING_V3_EXECUTION_PLAN.md` and
> run `CLAUDE_RECOVERY_GATE_1.md` first. Do not resume this broad Gate B
> prompt until the recovery gates have been independently approved.

Project: `C:\JV_Project\jp_vocab_reader`

Target: Reading tab only. Read these first and stop broad repository archaeology:

1. `references/mockups/reading-v3-prep/DESIGN_SPEC.md`
2. `references/mockups/reading-v3-prep/reading-v3-input-approved.png`
3. `references/mockups/reading-v3-prep/reading-v3-analyzed-reference.png`
4. `references/mockups/reading-v3-prep/reading-v3-scene-approved-desktop.png`
5. `frontend/components/ReadingTab.tsx`
6. `frontend/components/ReadingSourceSlip.tsx`
7. `frontend/components/ReaderMode.tsx`
8. `frontend/components/ReadingVocabPanel.tsx`
9. the Reading-specific blocks in `frontend/app/globals.css`

## Mandatory Opening

Before editing, report exactly:

1. Three lines explaining why the current screenshot fails.
2. One line defining the new physical scene silhouette.
3. The old wrapper/class roles you will remove or redefine.
4. Which approved scene asset and state mockups are the visual authorities.

## Goal

Replace the current translucent-form-on-photo presentation with the approved direct-on-page editor and continuous analyzed-reader layout. The target images are the source of truth for scale, hierarchy, spacing, grounding, and material relationships. This is a silhouette and state-continuity replacement, not a cosmetic CSS pass. A small diff that leaves the first screenshot structurally unchanged is failure.

## Required Work

Gate A is complete. The user selected the second direct ImageGen scene. Do not use, repair, compare against, or reconnect any `reading-v3-scene-candidate-*` quilting artifact.

### Gate B: integration

- Copy `reading-v3-scene-approved-desktop.png` into a new versioned production asset folder without re-encoding it and connect that exact file for desktop.
- Use its native `1849 / 851` ratio. Remeasure all desktop page and overlay coordinates from this asset; do not reuse the V2 percentages.
- Desktop only: rebuild `ReadingSourceSlip` presentation to match `reading-v3-input-approved.png`.
- Remove or role-redefine the physical paper-slip/form-card styling. Keep the component and callbacks if useful; do not preserve a failed visual wrapper merely to minimize the diff.
- Make editor text and analyzed reader text share the same page origin and typographic metrics.
- Make only the content region scroll for long text. Keep title, metadata, deck selector, and analyze/progress action stable.
- Re-map the right idle guide and analyzed dictionary ledger to the same origin.
- Use the exact production copy and constraints in `DESIGN_SPEC.md`.
- Keep mobile source and layout unchanged in this pass unless a desktop selector leaks into mobile.

## Hard Boundaries

- Presentation only. Do not change callbacks, analysis/chunking, cancel, deck recovery, token grouping, selection, save behavior, meaning editing/reporting, API contracts, auth, SRS, routing, storage keys, or persistence rules.
- Never access Neon or production data. Browser QA requiring a backend must use a session-only scratch SQLite `DATABASE_URL`.
- Do not bake Korean/Japanese UI text into images.
- Do not add cards, gradients, ribbons, stamps, folded corners, sticky notes, floating paper sheets, giant CTA objects, or new Shiori artwork.
- Do not add a bundled font during the first pass.
- Do not touch Home or shared navigation design.
- Do not commit or push.

## First-Pass QA

- Judge screenshots at 1280 desktop and 390 mobile first.
- Desktop: verify input, analyzing/progress/cancel, analyzed with no selected word, analyzed with selected word, and long-text internal scrolling.
- Confirm input and analyzed first-line coordinates are visually unchanged.
- Confirm the approved wide scene has no unrelated side strips and is not cropped or stretched.
- Mobile smoke: existing scene, no overflow, core input/analyze flow intact.
- Check `scrollWidth === clientWidth`, console errors/warnings, failed requests/image 404s, representative clicks, and `git diff --check`.
- Run `npm run build` once near the end, not repeatedly during iteration.
- Allow one screenshot-driven correction pass. If the approved silhouette is still not reached, stop and report the missing structural or asset decision.

## Gate B Completion Report

1. Removed or redefined old structure
2. New scene silhouette
3. Before/after first impression
4. Input-to-analysis continuity
5. Preserved behavior
6. Desktop judgment
7. Mobile judgment
8. Failure criteria and QA
9. Remaining risks
10. Screenshot paths

Do not commit or push. Await approval.
