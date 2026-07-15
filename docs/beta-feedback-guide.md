# Beta Feedback Guide

How this app collects feedback during the beta, what to ask testers to try,
and what an operator should check when reading submitted feedback. For
release-day checks (env vars, auth, core loop, privacy), see
[beta-release-checklist.md](beta-release-checklist.md) — this doc only
covers the feedback loop itself.

**Never write real URLs, secret values, tokens, or database connection
strings into this file.** Use placeholders / checkmarks only.

## 1. Purpose

The beta's goal is to find, before a wider release:

- Words with an awkward or wrong Korean meaning.
- Steps in the read → save → review loop that are confusing or hard to find.
- Design/mobile issues (overlapping elements, cramped layout, unreadable
  text).
- Bugs — buttons that don't respond, stuck loading states, errors.

Feedback is collected in-app only (the global feedback button + the
per-word "뜻 오류 신고" report), never through a separate form or channel.
Both submissions deliberately exclude the reading tab's original text —
only the current screen name and whatever the tester types by hand is
sent. See [privacy details](#5-privacy-what-is-and-isnt-collected) below.

## 2. Core flows to ask testers to try

1. Sign up or log in.
2. Home → "샘플로 체험하기" (sample text walkthrough).
3. Reading tab: paste real text and analyze it.
4. Click an unfamiliar word to check its meaning/reading.
5. Select a few words and save them (모르는 단어 / 헷갈리는 단어 저장).
6. "방금 저장한 단어 학습" — study the words just saved.
7. Rate a few cards (다시/어려움/보통/쉬움) through to session completion.
8. Check the vocab tab — saved words, search, filter, edit, delete.
9. Shared deck tab — browse a JLPT 추천 어휘 deck and import it.
10. Submit at least one piece of feedback, on purpose, to confirm the flow
    itself feels easy.

## 3. Feedback categories

The feedback modal shows 6 specific options so testers can pick whichever
matches what actually happened, without having to guess a generic "bug"
vs. "UX" split:

| Label (shown to testers) | What it's for |
| --- | --- |
| 사용성/흐름 | Didn't know where to click, unclear what a screen wanted |
| 단어 뜻 오류 | A word's meaning looked wrong, awkward, or the reading was off |
| 저장/복습 문제 | Something odd during save, vocab list, or SRS review |
| 디자인/모바일 | Layout broke, overlapped, or was hard to read (mobile especially) |
| 버그/오류 | A button did nothing, loading got stuck, an error appeared |
| 기타 | Anything else, including feature ideas |

These 6 labels map onto the backend's fixed 5-value category enum
(`bug`/`ux`/`feature`/`meaning`/`other` in
`backend/app/schemas.py::VALID_APP_FEEDBACK_CATEGORIES`) — "사용성/흐름"
and "디자인/모바일" both send `ux`, "저장/복습 문제" and "버그/오류" both
send `bug`. The specific detail lives in the free-text message, not the
category value, so nothing is lost — this mapping is UI-only
(`frontend/components/GlobalFeedbackModal.tsx`) and does not touch the API
payload shape or the stored enum.

## 4. Message to send beta testers

> 안녕하세요. 일본어 원문을 읽으면서 모르는 단어를 저장하고 복습할 수 있는
> 웹서비스 베타 버전입니다.
>
> 가볍게 아래 순서로 사용해보시면 됩니다.
> 1. 회원가입 또는 로그인
> 2. 홈에서 "샘플로 체험하기"
> 3. 원문에서 모르는 단어 클릭
> 4. 단어 저장 후 "방금 저장한 단어 학습"
> 5. 불편한 점은 피드백 버튼으로 남기기
>
> 특히 아래 내용을 알려주시면 좋습니다.
> - 뜻이 어색한 단어
> - 저장/복습 중 헷갈린 부분
> - 모바일에서 화면이 불편한 부분
> - 버튼이 안 되거나 로딩이 멈춘 부분
>
> 참고: 원문 전체는 서버에 저장하지 않고, 단어와 짧은 문맥 예문만
> 저장됩니다.

(This mirrors the announcement in
[beta-release-checklist.md](beta-release-checklist.md#11-beta-user-announcement)
— keep the two in sync if either changes.)

## 5. Privacy: what is and isn't collected

- The global feedback form sends only: category, the tester's typed
  message, the current tab name, and a short path string
  (`backend/app/schemas.py::AppFeedbackRequest` — `category`, `message`,
  `screen`, `path`). No reading-tab original text, no `localStorage`
  session content, no per-word detail beyond what the tester types.
- The per-word "뜻 오류 신고" form (`MeaningFeedbackRequest`) sends the
  word itself, its current/suggested meaning, and an optional reason — a
  single word and its meaning, not the surrounding original text.
- Neither endpoint accepts or stores a full source text field. This isn't
  a client-side convention only — the backend request models simply have
  no field for it, so there is nothing to strip even if a future UI change
  tried to send more.
- Testers can still paste whatever they want into the free-text message —
  the modal's footer note asks them not to, but message content itself
  isn't filtered. If a tester pastes something sensitive by hand, treat it
  the same as any other user-submitted text.

## 6. What an operator should check when reading feedback

There is no admin dashboard for this (intentionally out of scope for the
beta) — feedback rows live in the `app_feedback` and `meaning_feedback`
tables, readable via the repository helpers already used elsewhere
(`backend/app/repositories/feedback_repository.py::list_app_feedback` /
`list_meaning_feedback`), or a direct read-only query against the
configured database (`psql "$DATABASE_URL" -c "select ..."` locally, or
the Neon dashboard's SQL editor in production — never paste the real
connection string into a doc, chat, or script).

When triaging:

- **category** — tells you which of the 6 tester-facing buckets it came
  from (see the mapping table above); use it to route to the right owner
  (뜻 오류 → dictionary/meaning data, 저장/복습 문제 → SRS/vocab flow,
  디자인/모바일 → CSS/layout, 버그/오류 → functional bug).
- **message** — the actual detail; this is free text, so read it as-is.
- **screen** / **path** — which tab the tester was on when they opened the
  feedback modal, useful for reproducing.
- **created_at** — useful for correlating with a deploy or a specific
  testing session.
- **status** — every row starts `'open'`; there is currently no UI to
  change it, so treat all rows as needing a manual look until a triage
  process exists.

If a message references something that sounds like it might contain a
full pasted passage rather than a short pointer, that's a tester ignoring
the footer note, not a data-collection bug — the request schema has no
field that could carry a full original text automatically.
