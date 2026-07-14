# Beta Release Checklist

Final pre-release check before opening the service to beta users. Target
deployment shape: Vercel (frontend), Render (backend), Neon PostgreSQL
(database). For full environment-variable and platform setup details, see
[deployment-checklist.md](deployment-checklist.md) and
[production-deployment.md](production-deployment.md) — this doc is a
short, checkable list for release day, not a replacement for those.

**Never write real URLs, secret values, tokens, or database connection
strings into this file.** Use placeholders / checkmarks only.

## 1. Frontend / Vercel

- [ ] Vercel project points at the intended production domain.
- [ ] `NEXT_PUBLIC_API_BASE_URL` is set in Vercel project settings to the
      `https://` Render backend URL.
- [ ] No `localhost` / `127.0.0.1` URL is hardcoded anywhere outside the
      local-dev fallback in `frontend/app/page.tsx` and `.env.example`
      (those two are expected; anything else is a bug).
- [ ] `npm run build` succeeds with no type errors.

## 2. Backend / Render

- [ ] `DATABASE_URL` is set to the Neon PostgreSQL connection string (not
      empty — an empty value falls back to local SQLite, which must never
      be the production database).
- [ ] `JWT_SECRET_KEY` is set to a real production value — never the
      `dev-only-jwt-secret-change-me` fallback baked into
      `backend/app/settings.py`.
- [ ] `CORS_ORIGINS` (or the legacy `CORS_ALLOW_ORIGINS` alias) includes the
      exact Vercel frontend origin with `https://`.
- [ ] `GET /health` responds and returns `status: ok`.
- [ ] Render logs do not print `DATABASE_URL`, `JWT_SECRET_KEY`,
      `OPENAI_API_KEY`, or any other secret value.

## 3. Database / Neon

- [ ] Backend can connect to the production Neon database (`/health`
      reports `database: postgresql`, or run
      `python scripts/check_postgres_connection.py` against the Render env).
- [ ] Core tables exist and are reachable: users, decks, vocabulary items,
      custom terms, review/study history, shared decks + shared deck
      imports.
- [ ] Confirm `backend/vocab.db` (local SQLite) is not what production is
      actually reading from — check `DATABASE_URL` on Render directly
      rather than assuming.

## 4. CORS / Allowed Origins

- [ ] `CORS_ORIGINS` on Render lists the production Vercel origin exactly
      (scheme + host, no trailing slash mismatch).
- [ ] No `*` wildcard origin in production.
- [ ] A real browser request from the Vercel domain to the Render domain
      completes without a CORS error in devtools.

## 5. Auth — Final Test

- [ ] Sign up with a new email succeeds, brand-tone copy shows correctly.
- [ ] Log in with an existing account succeeds.
- [ ] Refresh the page after login: session persists (no forced re-login).
- [ ] Log out: user info clears, private data refreshes to the dev/guest
      view, and the reading tab's in-progress original text is **not**
      wiped.
- [ ] Wrong password shows a natural message
      ("이메일 또는 비밀번호를 다시 확인해주세요.") — never a raw error object or
      stack trace.
- [ ] A corrupted/expired token does not white-screen the app or leave it
      stuck loading; it clears the token and shows a login-needed message.

## 6. Core Loop — Final Test

Standard sentence (use this exact text so results are comparable release to
release):

```
彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。
```

- [ ] Home → "샘플로 체험하기".
- [ ] Reading tab analyze completes; particles/punctuation are preserved in
      the rendered text (not stripped).
- [ ] 闇, 約束, 剣 are each clickable and open the word detail sheet.
- [ ] Selected-save (선택 저장) succeeds with a clear success message.
- [ ] "방금 저장한 단어 학습" starts a session from just-saved words.
- [ ] Rating (again/hard/good/easy) advances the session correctly.
- [ ] Vocab tab shows the saved words.
- [ ] Each word's `example_sentence` is the short sentence it appeared in,
      not the full three-sentence original:
      - 闇 → `彼は闇の中で声を聞いた。`
      - 約束 → `少女は約束を思い出した。`
      - 剣 → `騎士は剣を握り、敵から王を守った。`

### Long-text variant

Repeat the standard sentence 20-50 times as one pasted block and confirm:

- [ ] Chunked analysis completes with visible progress.
- [ ] Re-clicking analyze mid-run is prevented (no duplicate concurrent
      requests).
- [ ] Token order matches the original text order.
- [ ] Repeated words are grouped/deduped in the word list, not duplicated
      per occurrence.
- [ ] Selected-save and "방금 저장한 단어 학습" still work at this scale.
- [ ] No horizontal scroll on mobile width while reading the long result.
- [ ] The full pasted text is never written to the database (only short
      per-word example sentences are).

## 7. Shared Deck — Final Test

- [ ] Deck titles/descriptions read "JLPT 추천 어휘" / "추천 어휘 덱", never
      "공식 JLPT 단어장" or "공식 JLPT 덱" as a claim of official status.
- [ ] Importing a shared deck succeeds and lands in the vocab tab. **For
      large decks (N1/N2/N3), expect this to take several minutes — see the
      known risk below before assuming it's stuck.**
- [ ] An already-imported deck shows the "가져옴" badge with its import
      date.
- [ ] Re-importing an already-imported deck prompts a confirmation instead
      of silently duplicating.
- [ ] A deck the current user published can be unpublished / share-canceled
      (and, where supported, deleted).

**Known risk (confirmed 2026-07-14):** importing a large recommended deck is
slow — importing the 684-word N5 deck took ~2 minutes end-to-end against the
Neon backend (`backend/app/repositories/shared_deck_repository.py`
`import_shared_deck` inserts each vocab/custom-term row with its own
`connection.execute(...)` call in a Python loop, so the wall-clock time
scales with word count and per-statement network latency to the DB). N4
(640 words) will be similar; N3/N2 (~1.8k words) and N1 (3.5k words) will
take proportionally longer — plausibly 5-10+ minutes for N1. The UI shows a
"가져오는 중..." state the whole time with no progress indicator, so a beta
user importing N1/N2/N3 may reasonably assume the app is frozen. This is a
pre-existing performance characteristic, not something introduced by this
check — decide before wide beta rollout whether to warn users, recommend
starting with N5/N4, or batch the inserts (out of scope for this checklist
pass; flagged for a follow-up, not fixed here to avoid an unreviewed
backend write-path change this close to launch).

## 8. Feedback — Final Test

- [ ] Global app feedback (하단/사이드바 피드백 버튼) submits successfully.
- [ ] Meaning-error report (뜻 오류 신고) submits successfully from a word's
      detail sheet.
- [ ] Neither feedback payload includes the full reading-tab original text
      — only the current screen name and the user's typed message /
      word-level fields.

## 9. Privacy / Copyright Policy

- [ ] No full original text (sample or user-pasted) is stored server-side.
- [ ] No full original text is included in shared deck packages.
- [ ] No full original text is shown on a review/study card — only the
      short `example_sentence`.
- [ ] No full original text is exposed on home, feedback, or shared-deck
      screens.
- [ ] English gloss text is not surfaced as the primary meaning in the
      default UI (Korean `meaning_ko` only, with the existing quality
      fallback).

## 10. Git Safety

- [ ] `git status --short` shows none of: `.env`, `backend/vocab.db`,
      `frontend/.next`, `node_modules`, `__pycache__`, `*.pyc`.
- [ ] No large dictionary dump is staged: `jmdict_full.json`,
      `en_ko_full.json(.gz)`, `kaikki_raw.jsonl(.gz)`,
      `krdict_reverse_full.json(.gz)`.
- [ ] `backend/data/jlpt/{raw,work,reviewed,packages}/` are not staged.
- [ ] No secret value appears anywhere in the diff being pushed.

## 11. Beta User Announcement

Short, plain message to send when opening access — not a marketing pitch:

> 안녕하세요. 일본어 원문을 읽으면서 모르는 단어를 저장하고 복습할 수 있는
> 웹서비스 베타 버전입니다.
>
> 사용 순서:
> 1. 회원가입 또는 로그인
> 2. 홈에서 "샘플로 체험하기" 클릭
> 3. 원문에서 모르는 단어 클릭
> 4. 단어를 저장한 뒤 "방금 저장한 단어 학습" 진행
> 5. 불편한 점은 피드백 버튼으로 보내주세요.
>
> 참고: 원문 전체는 서버에 저장하지 않습니다. 단어와 짧은 문맥 예문만
> 단어장에 저장됩니다.
>
> 베타 테스트 기간이라 예상치 못한 오류가 있을 수 있습니다. 양해 부탁드립니다.
