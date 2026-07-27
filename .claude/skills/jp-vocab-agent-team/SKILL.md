---
name: jp-vocab-agent-team
description: Coordinate a tmux-based Claude agent team for jp_vocab_reader. Use when planning or running multi-agent project work, assigning frontend/backend/QA/release roles, deciding when to add or close agents, or preparing prompts for team-led implementation.
---

# JP Vocab Agent Team

Use this skill to run `jp_vocab_reader` work through a small, temporary Claude team.

## Operating Model

- Keep one Team Lead session active for the current workstream.
- Create worker agents per task round, not for the whole project.
- Close worker agents after they report and their output is integrated or rejected.
- Add agents by risk area, not by generic title.
- Do not let workers run `git add`, `git commit`, `git push`, or `git merge`.
- Treat the user as final approver and the release manager as the final git gate.

## Default Team

Use this team for reading-tab and UI recovery work:

- Team Lead: owns tmux layout, task sequencing, conflict control, final report.
- Root-Cause Agent: finds the actual cause with file and line evidence.
- Fix Agent: edits only the smallest required frontend slice.
- QA Agent: verifies actual screen behavior and build results.
- Safety/Release Agent: checks forbidden files, forbidden copy, diff scope, and commit readiness.

Use fewer agents when the task is small. Start with Root-Cause + Fix + QA for the current V4 reading tab work.

## When To Add Specialists

Add temporary specialists only when the task changes:

- SRS/Domain Agent: review status transitions, review level, next review date, correct/wrong counts, and review logs.
- Backend Contract Guard: protect `/analyze`, `/vocab-items`, `/study-items`, `/decks`, `/shared-decks`, and explanation endpoints.
- Migration/Safety Agent: handle schema or data changes through dry-run planning, never production DB edits.
- Product Copy Guard: check prohibited phrases, source-text privacy language, and Korean reader tone.
- Deployment Agent: check Render, Vercel, Neon env assumptions and `/health` behavior.

## tmux Pattern

Prefer one session per workstream:

```powershell
tmux new -s jp-vocab-v4
tmux rename-window lead
tmux new-window -n root-cause
tmux new-window -n fix
tmux new-window -n qa
tmux new-window -n release
```

If tmux is unavailable on Windows, use separate Claude terminal tabs named with the same roles.

## Team Lead Checklist

1. Confirm branch and starting commit.
2. Confirm `git status --short`.
3. State forbidden files and forbidden actions before delegating.
4. Give each worker a disjoint write scope.
5. Require evidence in reports: changed files, commands run, screenshots or DOM checks when relevant.
6. Run final build and safety checks before recommending commit.
7. Report what can be committed and what must remain untracked.

## Worker Prompt Template

```text
Role: <Agent Role>
Project: C:\JV_Project\jp_vocab_reader
Branch: <branch>

Task:
<bounded task>

Allowed files:
<files or directories>

Forbidden:
- git add/commit/push/merge
- backend/.env and all DB/data artifacts
- unrelated refactors
- API/DB/SRS changes unless explicitly assigned

Report:
1. Cause or result
2. Files inspected
3. Files changed
4. Commands run
5. Validation result
6. Risks and follow-up
```

