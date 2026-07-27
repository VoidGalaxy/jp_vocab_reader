---
name: jp-vocab-product-guard
description: Product, privacy, and copy guardrails for jp_vocab_reader. Use when changing UI copy, reading-tab flow, JLPT wording, sharing, feedback, saved vocabulary, SRS surfaces, or product positioning.
---

# JP Vocab Product Guard

Use this skill to protect product intent and user-facing language.

## Product Center

The reading tab is the core product. Preserve this loop:

1. Paste or load Japanese text.
2. Read the text.
3. Click unknown words.
4. Check meaning, reading, and status.
5. Put words into the basket or vocabulary note.
6. Study saved words through SRS.
7. Return to reading.

AI explanation is optional helper capability, not the main surface.

## Privacy Rules

- Do not imply full source text is saved to the server.
- Do not imply full source text is shared.
- Do not attach full source text to feedback, shared decks, or review cards.
- Source text may live only in temporary frontend state or local reading session storage.
- Saved data should be word information plus short `example_sentence` context.

Allowed copy example:

- "원문 전체는 서버에 저장하지 않아요."

Avoid any copy that says or implies:

- "원문 전체를 저장합니다"
- "원문 전체를 공유합니다"

## JLPT Wording

Never use:

- "공식 JLPT"
- "official JLPT"

Prefer:

- "JLPT 추천 어휘"
- "추천 어휘 덱"
- "JLPT 추천 어휘 덱"

## Other Forbidden Copy

Never use:

- "복사된 단어"

Use neutral product language such as:

- "담은 단어"
- "저장한 단어"
- "어휘 노트"

## UI Tone

- Favor Korean reader-friendly, calm, note-like copy.
- Keep controls direct and action-based.
- Do not expose implementation terms such as enum names or placeholder quality tags.
- Do not add explanatory clutter to the reading surface.
- Keep management actions behind progressive disclosure when they are not part of the reading loop.

## Review Checklist

Before accepting a copy or UI change, check:

- Does this strengthen the reading -> save -> review loop?
- Does it avoid full source-text storage/share implications?
- Does it avoid official JLPT claims?
- Does it avoid implementation placeholders?
- Does it keep AI secondary unless explicitly requested?

