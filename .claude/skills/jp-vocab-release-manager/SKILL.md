---
name: jp-vocab-release-manager
description: Release and git safety workflow for jp_vocab_reader. Use when deciding branches, commits, pushes, merges, build validation, forbidden file checks, deployment readiness, or whether Claude team output may be accepted.
---

# JP Vocab Release Manager

Use this skill before committing, pushing, merging, or accepting Claude team work.

## Acceptance Bias

Use a conservative release posture:

- Accept small, well-evidenced diffs.
- Reject broad rewrites unless the user explicitly approved them.
- Treat build/test/QA evidence as required for completion claims.
- Keep unrelated cleanup out of release commits.
- Mention unrelated risks, but do not fix them inside the current release unless assigned.

## Required Order

1. Confirm branch.
2. Run `git status --short`.
3. Inspect changed files with `git diff --stat` and targeted `git diff`.
4. Check forbidden files.
5. Run required validation.
6. Decide commit scope.
7. Provide exact `git add` targets.
8. Commit only after approval.
9. Push only after approval.

## Verification Before Completion

Before saying a Claude round is complete, confirm:

- The changed files match the approved scope.
- The original bug or UX issue has a direct evidence path from cause to fix.
- The smallest practical validation ran.
- Browser or Playwright QA ran when the change affects visible reading-tab behavior.
- Any failed or skipped validation is reported plainly.
- Remaining risks are separated into current blockers vs later follow-up.

Do not accept "looks good" reports without changed files, commands, and observable results.

## Forbidden Commit Targets

Never stage or commit:

- `backend/.env`
- `backend/.env.backup-neon`
- `backend/*.db`
- `backend/data/jlpt/raw/`
- `backend/data/jlpt/work/`
- `backend/data/jlpt/reviewed/`
- `backend/data/jlpt/packages/` — except the 5 approved recommended-deck packages below, which are intentionally tracked so Render deploys carry production seed input
- `backend/data/dictionary/jmdict_full.json`
- `backend/data/dictionary/en_ko_full.json`
- `backend/data/dictionary/en_ko_full.json.gz`
- `backend/data/dictionary/kaikki_raw.jsonl`
- `backend/data/dictionary/kaikki_raw.jsonl.gz`
- `backend/data/dictionary/krdict_reverse_full.json`
- `backend/data/dictionary/krdict_reverse_full.json.gz`
- `frontend/.next`
- `frontend/node_modules`
- `node_modules`
- `__pycache__`
- `*.pyc`
- `.claude/settings.local.json`

Treat untracked `.agents/` as a separate tooling decision. Do not include it in feature commits unless the task explicitly adds project skills there.

## Approved packages/ Exceptions

Only these 5 files inside `backend/data/jlpt/packages/` may be staged or committed. Everything else in that directory (intermediate builds, drafts, anything not on this list) stays forbidden:

- `backend/data/jlpt/packages/jlpt_n1_recommended_deck.json`
- `backend/data/jlpt/packages/jlpt_n2_recommended_deck.json`
- `backend/data/jlpt/packages/jlpt_n3_recommended_deck.json`
- `backend/data/jlpt/packages/jlpt_n4_recommended_deck.json`
- `backend/data/jlpt/packages/jlpt_n5_recommended_deck.json`

Before staging any of these, re-run the forbidden-copy search below against them and confirm `deck.name`, `vocab_items` count, and `custom_terms` count match the last verified snapshot — do not accept silent content drift.

## Validation Commands

Frontend:

```powershell
cd C:\JV_Project\jp_vocab_reader\frontend
npm run build
```

Backend, only when backend code changed:

```powershell
cd C:\JV_Project\jp_vocab_reader\backend
.\.venv\Scripts\python.exe -m compileall app scripts
```

Forbidden copy search:

```powershell
cd C:\JV_Project\jp_vocab_reader
Select-String -Path .\frontend\**\* -Pattern "공식 JLPT","official JLPT","source English","MEANING_NEEDS_REVIEW","원문 전체를 저장합니다","원문 전체를 공유합니다","복사된 단어" -SimpleMatch -ErrorAction SilentlyContinue
```

Known exception: `frontend/components/shared.tsx` may contain internal placeholder filter values `meaning_needs_review` and `source english`. If they are not user-facing and not part of the current diff, report them but do not block solely on them.

## Local Backend Safety

Before running a local backend server, avoid production Neon:

```powershell
cd C:\JV_Project\jp_vocab_reader\backend
$env:APP_ENV="development"
$env:DATABASE_URL="sqlite:///./vocab_claude_scratch.db"
.\.venv\Scripts\python.exe -c "import os; u=os.environ.get('DATABASE_URL',''); print('DATABASE_URL=', u); assert u.startswith('sqlite:///'); assert 'neon.tech' not in u"
```

Use `CORS_ORIGINS` or port `3000` when browser testing requires frontend/backend CORS alignment.

## Commit Decision

Commit only when:

- Changed files match the assigned scope.
- Build/tests pass or failures are understood and accepted by the user.
- No forbidden files are staged.
- User-facing copy respects product guardrails.
- `git status --short` has only intentional staged/unstaged items.

Prefer exact path staging. Do not use broad staging commands when untracked tooling files, local settings, DB files, build outputs, or unrelated agent changes exist.
