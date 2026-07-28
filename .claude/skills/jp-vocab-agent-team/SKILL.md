---
name: jp-vocab-agent-team
description: Coordinate a tmux-based Claude agent team for jp_vocab_reader. Use when planning or running multi-agent project work, assigning frontend/backend/QA/release roles, deciding when to add or close agents, or preparing prompts for team-led implementation.
---

# JP Vocab Agent Team

Use this skill to run `jp_vocab_reader` work through a small, temporary Claude team.

## Lean Operating Principles

Apply these rules before creating agents or editing files:

- Think before coding: state the likely cause, assumptions, and success criteria before implementation.
- Keep changes surgical: every changed line must trace to the assigned task.
- Prefer the smallest working fix over broad rewrites, speculative abstractions, or adjacent cleanup.
- Verify before declaring done: evidence beats confidence.
- Use agents to reduce risk, not to create parallel chatter.

## Token-Saving Mode

Default to one Team Lead plus one worker. Add agents only when the current round has a clear risk that benefits from separation:

- Root-Cause Agent: only when the cause is unclear or disputed.
- Fix Agent: only for the bounded implementation slice.
- QA Agent: only after a fix is ready or when visual/browser evidence is required.
- Safety/Release Agent: only before commit, merge, push, backend/API/DB work, or large diffs.

Avoid long-lived frontend/backend/QA agents for the whole project. Keep the Team Lead persistent for context, then create short-lived workers per round and close them after their report is accepted or rejected.

Require compact reports. Do not paste full diffs, old context, repeated logs, or unrelated file readings. Each worker report should fit this shape:

1. Changed files
2. Root cause or fix summary
3. Validation evidence
4. `git status --short`
5. Remaining risks
6. Commit recommendation

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

For normal rounds after V4 reading-tab recovery, start smaller: Team Lead + one assigned worker. Add QA only when there is something concrete to verify.

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
3. State assumptions, success criteria, forbidden files, and forbidden actions before delegating.
4. Choose the fewest agents needed for this round.
5. Give each worker a disjoint write scope.
6. Require evidence in reports: changed files, commands run, screenshots or DOM checks when relevant.
7. Run final build and safety checks before recommending commit.
8. Report what can be committed and what must remain untracked.

## Skill Creation Rule

Use Skill Creator only for repeated or fragile workflows. Prefer a small project-specific skill over importing a large external system when the rule is unique to `jp_vocab_reader`.

Good candidates:

- SRS review-loop QA
- Reading -> save -> review end-to-end QA
- Backend/API contract safety
- Release checklist updates
- Product wording/privacy checks

Do not create a skill for a one-time fix or a rule that fits in the worker prompt.

## Superpowers-Inspired Checkpoints

Use only the lightweight parts that help this repository:

- Systematic debugging: reproduce or trace the failure before editing.
- Verification before completion: prove the fix through build, test, browser QA, or targeted DOM checks.
- Requesting code review: ask a separate reviewer only for risky diffs or user-facing workflows.
- Finishing a development branch: summarize changed files, validation, risks, and exact commit readiness.

Do not force test-driven development or parallel subagent workflows for every small UI/copy change.

## Worker Prompt Template

```text
Role: <Agent Role>
Project: C:\JV_Project\jp_vocab_reader
Branch: <branch>

Task:
<bounded task>

Success criteria:
<specific observable result>

Allowed files:
<files or directories>

Forbidden:
- git add/commit/push/merge
- backend/.env and all DB/data artifacts
- unrelated refactors
- API/DB/SRS changes unless explicitly assigned
- broad rewrites or speculative abstractions

Report:
1. Changed files
2. Cause or fix summary
3. Validation evidence
4. git status --short
5. Risks and follow-up
6. Commit recommendation
```
