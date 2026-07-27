---
name: jp-vocab-reading-tab-qa
description: QA workflow for jp_vocab_reader reading tab. Use when validating V4 reading-tab rebuilds, deck select behavior, sample analysis, reader surface, action dock, token selection panel, mobile layout, or Playwright/browser checks.
---

# JP Vocab Reading Tab QA

Use this skill to validate reading-tab behavior before commit or merge.

## Environment

Use a local SQLite backend for browser QA. Do not use Neon.

Backend:

```powershell
cd C:\JV_Project\jp_vocab_reader\backend
$env:APP_ENV="development"
$env:DATABASE_URL="sqlite:///./vocab_claude_scratch.db"
$env:CORS_ORIGINS="http://127.0.0.1:3003,http://localhost:3003"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Frontend:

```powershell
cd C:\JV_Project\jp_vocab_reader\frontend
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8002"
npm run dev -- --hostname 127.0.0.1 --port 3003
```

If using another port, align `CORS_ORIGINS` with the frontend origin.

## Core Acceptance Criteria

Validate all items:

1. Reading tab first screen is one paper card.
2. No top "가이드" disclosure bar.
3. No "원문 관리" top toggle.
4. No `ReaderCompactToolbar` or similar top management toolbar.
5. No top row of "저장 가능 N개 / 바구니 N개" management chips.
6. No floating `ShioriGuideCard`, idle overlay, or right-side guide card before selecting a word.
7. Deck select shows at least one option when `/decks` returns items.
8. Sample text load enables the analyze/open button.
9. Analyze loading appears inside the same card before results.
10. After analysis, reader surface appears.
11. Action dock appears under the reader.
12. Candidate list/caption is collapsed by default.
13. Word detail panel appears only after selecting a token.
14. Basket toggle works for eligible tokens.
15. Quick save details can open without layout breakage.
16. Mobile width has no text, button, or panel overlap.
17. `npm run build` passes.

## Useful DOM Checks

Check these counts in browser tooling:

- `.reader-start-card`
- `.reading-hero`
- `.reader-compact-toolbar`
- `.reader-paper`
- `.reading-action-dock`
- `.token-sheet-overlay-idle`
- `select[aria-label="읽기 덱"] option`

Expected pre-analysis:

- `.reader-start-card` is `1`
- `.reading-hero` is `0`
- `.reader-compact-toolbar` is `0`
- `.token-sheet-overlay-idle` is `0`
- deck option count is greater than `0`

Expected post-analysis:

- `.reader-paper` is `1`
- `.reading-action-dock` is `1`
- token detail sheet is absent until a token is selected

## Report Format

Report:

1. Branch and commit tested.
2. Backend/frontend URLs used.
3. Deck select result.
4. Sample analysis result.
5. Desktop acceptance results.
6. Mobile acceptance results.
7. Build result.
8. Console/network errors.
9. Blocking issues.
10. Commit recommendation.

