# Home Visual Design Playbook

This document turns the Home redesign failures into rules for future visual work.
It is a decision manual, not a phase history.

## 1. Why earlier passes failed

1. **Implementation started before the target was fixed.** Repeated CSS position and shadow edits optimized a compromised screenshot instead of a single approved composition.
2. **One physical object was split into unrelated layers.** Book, tabs, Shiori, and shadows drifted apart, creating color bleed, matte residue, black seams, and a floating-object look.
3. **Image-generation prompts were asked to preserve pixels.** Generative edits redraw supposedly locked objects. This changed book color, proportions, character details, and edges even when the prompt said not to.
4. **Shadow was judged at asset resolution.** A blur that looked visible on a large PNG collapsed to a few pixels at browser scale, while broad CSS shadows became boxes or horizontal bars.
5. **Outer object bounds were mistaken for text safe zones.** Text then touched deckled edges, tape, stitching, or photo detail.
6. **Responsive claims were trusted without real browser geometry.** A nominal 320 screenshot did not always mean a 320 CSS-pixel viewport, and `cover` cropping invalidated coordinates.
7. **Old experiments remained plausible inputs.** Superseded assets and briefs were accidentally reused because their status was unclear.

## 2. The method that worked

1. **Approve the first impression first.** Make a text-free target mockup before editing production code.
2. **Lock one source of truth.** The approved target defines scale, overlap, crop, material, light direction, and safe zones.
3. **Choose the correct asset boundary.** Static objects under one light source should be baked together. Dynamic states and live text must remain separate but use purpose-built transparent assets.
4. **Preserve pixels deterministically.** If an outpaint is needed, use generation only for the new background area and composite the approved center pixels back unchanged.
5. **Measure rendered geometry.** Convert safe zones from source-image pixels to percentages, then verify actual DOM rectangles in the browser.
6. **Allow one correction pass.** If the first screenshot still has the wrong silhouette, stop and revise the asset or structural decision. Do not enter an open-ended CSS loop.

## 3. Shadow rules

- Use one light direction for every object in the cluster.
- Contact shadow is narrow, dark, and closest to the object; ambient shadow is wider, softer, and lower opacity.
- Derive shadow from the exact object alpha or bake it into the same scene plate.
- Give the shadow canvas enough transparent padding for the falloff to reach zero.
- Tabs need separate torn-edge shadows. Never use one shared black bar beneath them.
- Inspect the shadow at real rendered size against the actual desk texture.
- Reject rectangular bounds, hard terminal lines, gray matte residue, and equal-strength shadow at every distance.

## 4. Crop and coordinate rules

- Record source width, height, aspect ratio, and the exact `contain` or `cover` formula.
- Desktop and mobile may use different images and coordinate sets.
- Safe zones describe text interiors, not paper or button outer bounds.
- At each final viewport, record `clientWidth`, `scrollWidth`, `clientHeight`, image URL, image rectangle, and every interactive hit-zone rectangle.
- Use CDP device emulation for narrow widths; do not infer CSS viewport width from screenshot pixels.
- Required final widths: 1280, 1024, 390, 375, and 320.

## 5. Prompt-writing rules

The first implementation prompt must be short and closed-scope. It contains:

1. Three lines describing the current failure.
2. One sentence naming the replacement goal.
3. The approved target path and what it controls.
4. The old structure to remove or role-redefine.
5. Locked behavior and data boundaries.
6. Forbidden fallback methods.
7. A hard approval gate before production code.

Use direct language such as `replace`, `remove`, `source of truth`, `pixel-locked`, and `unchanged screenshot is failure`. Avoid `polish`, `minor`, `slight`, `tweak`, and `CSS-only if possible`.

Do not put exhaustive QA or long history in the first prompt. Put five-width QA and the full report format in the final-candidate validation step.

## 6. Asset hygiene

- Keep: approved target, production assets, coordinate contract, concise manifest, and final viewport screenshots.
- Delete: rejected candidates, intermediate generations, temporary crops, scratch databases, browser profiles, and superseded handoff drafts.
- A retained legacy asset must be marked `SUPERSEDED, NOT WIRED` in its manifest.
- Production code must request only the current asset version.

## 7. Completion gate

A visual phase is complete only when all are true:

- The first screenshot clearly matches the approved target's hierarchy.
- Live text remains DOM text and fits its safe zones.
- Core clicks and accessibility labels still work.
- No horizontal overflow, asset 404, new console error, matte residue, or shadow clipping exists.
- Build succeeds once near the end and `git diff --check` is clean.
- The final report starts with removed or redefined structure, then before/after first impression.

