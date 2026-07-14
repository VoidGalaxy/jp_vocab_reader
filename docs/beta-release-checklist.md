# Beta Release Checklist

A short pre-release smoke test for pushing a build to beta users. For full
environment-variable and platform setup details, see
[deployment-checklist.md](deployment-checklist.md) and
[production-deployment.md](production-deployment.md) — this doc does not
repeat those, only points at what to re-check right before a release.

Do not write real secret values, database URLs, or connection strings into
this file. Use placeholders only.

## 1. Environment

- [ ] Vercel project env vars include `NEXT_PUBLIC_API_BASE_URL` pointing at
      the HTTPS Render backend URL (not `localhost`/`127.0.0.1`).
- [ ] Render service env vars include `DATABASE_URL` (Neon PostgreSQL),
      `JWT_SECRET_KEY` (a real production value, not the
      `dev-only-jwt-secret-change-me` code fallback), and `CORS_ORIGINS`
      containing the exact Vercel origin with `https://`.
- [ ] `GET /health` on the Render backend returns `status: ok`.
- [ ] Neon database is reachable (`scripts/check_postgres_connection.py`, or
      confirm `/health` reports `database: postgresql`).

## 2. Auth

- [ ] Sign up with a new email: brand-tone copy shows, submit succeeds, home
      screen reflects the logged-in state.
- [ ] Log in with an existing account; wrong password shows
      "이메일 또는 비밀번호를 다시 확인해주세요." (no raw error object/stack trace).
- [ ] Refresh the page after login: session persists (no forced re-login).
- [ ] Corrupt the stored token (devtools → Application → Local Storage →
      edit `jp-vocab-reader:access-token`) and refresh: no white screen, no
      stuck loading spinner, a natural "다시 로그인해주세요" message appears.
- [ ] Log out: user info clears, private vocab/study data refreshes to the
      dev/guest view, and the reading tab's in-progress original text is
      still there (logout must not wipe it).

## 3. Core Loop Regression

Use this fixed sentence (do not substitute a different one, so results are
comparable release to release):

```
彼は闇の中で声を聞いた。少女は約束を思い出した。騎士は剣を握り、敵から王を守った。
```

- [ ] Home → sample/guided flow → analyze the sentence above.
- [ ] Click 闇, 約束, 剣 → classify/select-save.
- [ ] Start "방금 저장한 단어 학습" and rate at least one card.
- [ ] Vocab tab shows the saved words with a short example sentence (not the
      full original paragraph).

## 4. Other Account-Gated Features

- [ ] Shared deck import works after login.
- [ ] Feedback submission (app feedback or meaning-report) succeeds and
      shows a natural confirmation message.

## 5. Repo Hygiene

- [ ] `git status --short` shows no `.env`, `backend/vocab.db`,
      `backend/data/jlpt/{raw,work,reviewed,packages}/`, or raw dictionary
      dump files staged.
- [ ] No secret values appear in any diff being pushed.
