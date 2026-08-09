# Beta Release Checklist

Final pre-release check before opening the service to beta users. Target
deployment shape: Vercel (frontend), Render (backend), Neon PostgreSQL
(database). For full environment-variable and platform setup details, see
[deployment-checklist.md](deployment-checklist.md) and
[production-deployment.md](production-deployment.md) — this doc is a
short, checkable list for release day, not a replacement for those. For the
*how* of viewport/mobile/long-content browser QA referenced in section 6
below (breakpoints, overflow-check method, automation tooling gotchas), see
[qa-browser-checklist.md](qa-browser-checklist.md).

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
- [ ] Importing a shared deck succeeds. A lexeme-mode deck (the current
      JLPT recommended decks, and anything published after the Phase 6
      lexeme migration) lands in "학습 목록" and should complete quickly
      regardless of deck size. A legacy copy-mode deck (published before
      that migration, if any still exist) lands in the vocab tab and can
      still take noticeably longer for large word counts — see the updated
      known-risk note below before assuming either case is stuck.
- [ ] An already-imported deck shows the "가져옴" badge with its import
      date.
- [ ] Re-importing an already-imported deck prompts a confirmation instead
      of silently duplicating.
- [ ] A deck the current user published can be unpublished / share-canceled
      (soft-unpublish only — the deck disappears from public list/detail/
      import for new users, but an already-subscribed user can keep
      reviewing its words; see policy below).
- [ ] After unpublish, an existing subscriber's review/status writes for
      that deck's words still return 200 and their study queue still
      serves the words (not a 404 dead card).
- [ ] After unpublish, a user who never imported the deck gets 404 on its
      list/detail/import.
- [ ] After unpublish, the owner and any already-subscribed user still see
      the deck in their own shared-deck bookshelf/list and detail, tagged
      with a calm "공유 중단됨" badge — it does not vanish from their own
      view, only from a brand new user's.
- [ ] In that unpublished detail view, the owner sees a "다시 공유하기"
      button (no "공유 취소" button); a subscriber sees the badge plus
      "열기"/status controls but never a republish button.
- [ ] Republishing (owner-only; non-owner gets 403) flips the deck back to
      public: the badge disappears, "공유 취소" reappears, and a brand new
      user can list/view/import it again.

**Resolved (Phase 6 Round 0-3, 2026-07-29):** owner unpublish is now a
soft-unpublish (`shared_decks.visibility` flips away from `'public'`; the
row itself is never deleted) — closed to new users, but an existing
subscriber keeps reference-based review/status access through their own
`user_deck_subscriptions`/`user_word_progress` rows, no bulk copy. See
"Owner unpublish policy" in
`docs/architecture/shared-lexeme-progress-storage.md` for the full design
and `backend/scripts/smoke_test_shared_lexeme_progress.py`'s
`run_unpublish_boundary_checks()` for the regression coverage.

**Resolved (Phase 7, 2026-07-29):** the owner's and existing subscribers'
own list/detail views were reopened for an unpublished deck (`is_published`
response field + "공유 중단됨" badge), and an owner-only `POST
/shared-decks/{id}/republish` was added and wired to a "다시 공유하기"
button in the unpublished detail view — a pure `visibility` flip back to
`'public'`, still no bulk copy and no change to `import_shared_deck()`'s
public-only new-user gate. See the same "Owner unpublish policy" section
for the full Round 1-9 history.

**Known risk (confirmed 2026-07-14) — re-assessed (Phase 8 Round 7,
2026-07-29):** the original finding below measured the *legacy* copy-mode
import path only. `import_shared_deck()` dispatches on `is_lexeme_deck()`
(`backend/app/repositories/shared_deck_repository.py`): a shared deck with
no `shared_deck_words` rows still falls through to
`_import_shared_deck_legacy()`, which inserts each vocab/custom-term row
with its own `connection.execute(...)` call in a Python loop, so wall-clock
time still scales with word count and per-statement DB latency — the
original 684-word N5 measurement (~2 minutes) and the projected 5-10+
minutes for N1 (3.5k words) still apply to any deck that takes this path.

Since the Phase 6 lexeme migration, a deck with at least one
`shared_deck_words` row instead takes `_import_lexeme_shared_deck()`, which
does a small, constant number of queries per import (one visibility check,
one `COUNT(*)` on `shared_deck_words`, one subscription lookup/upsert) —
no per-word insert loop and no `vocab_items` writes at all, so import time
should not meaningfully scale with deck size on this path.
`backend/scripts/seed_jlpt_shared_decks.py`, the current registration
script for the N5-N1 recommended decks, writes every word through
`upsert_lexeme()` + `add_word_to_shared_deck()` — i.e. the lexeme-mode
structure.

**Limitation of this re-assessment:** the above is a code-path /
local-SQLite finding, not a re-measurement against production. Neon access
is out of scope for this check, so whether the live N1-N5 `shared_decks`
rows on Render/Neon currently have `shared_deck_words` populated (vs. still
being pre-migration legacy rows) was not independently confirmed. If they
are confirmed lexeme-mode, the "5-10+ minutes for N1" estimate no longer
applies to them; any shared deck that still predates the lexeme migration
still hits the legacy O(N) path and the original estimate stands for that
deck specifically. Follow-up: run `is_lexeme_deck()` (or the equivalent
`SELECT 1 FROM shared_deck_words WHERE shared_deck_id = ?` check) against
the production N1-N5 deck ids to close this out definitively.

**Resolved (Phase 14):** the production N1-N5 transition described in this
follow-up was executed and confirmed — see "Phase 12/14: production
transition runbook and execution record" below for the execution record and
per-deck `mode: "subscribed"` confirmation.

**Local evidence added (Phase 9 Round 7-9, 2026-07-30):**
`backend/scripts/smoke_test_jlpt_seed_lexeme_mode.py` now calls
`seed_jlpt_shared_decks.py`'s own `run_apply_lexeme()` against a tiny
fixture package (SQLite scratch DB only) and asserts the result is
lexeme-mode (`is_lexeme_deck()` true, `shared_deck_words` populated, no
legacy `shared_deck_items`/`shared_deck_terms` rows) and that a subsequent
import stays subscription-only with no `vocab_items` bulk copy. This
confirms the seed script's *current code path* end to end locally; it does
not change the production-verification follow-up above, which still
requires checking the live Render/Neon N1-N5 rows directly.

**Production verification procedure (Phase 10 Round 4-6; API check executed
in Phase 11 Round 1):** this procedure was originally written before the
production check. The user-approved API result is recorded below; the
read-only DB fallback remains unexecuted.

1. *Purpose.* Confirm whether the live N1-N5 `shared_decks` rows on
   Render/Neon are lexeme-mode (have `shared_deck_words` rows) or still
   legacy-mode (`shared_deck_items` only, pre-lexeme-migration).
2. *Preconditions.* Requires explicit user/Codex approval before running,
   requires production (Render/Neon) access/credentials, must stay
   **read-only** (no writes, no re-seeding, no migration as part of this
   check), and does not relax the local-work rule that this repo's own
   Claude/agent sessions never touch Neon directly.
3. *Option 1 -- API check (lighter weight).* `GET /shared-decks` on the
   deployed Render backend returns a `mode` field per deck
   (`SharedDeckSummaryResponse.mode`, `app/schemas.py`) that the server
   computes from `is_lexeme_deck()` -- this does **not** depend on the
   caller's auth state (it's not user-scoped like `is_owner`/`imported_at`),
   so a single anonymous request is enough; logging in as any particular
   user is not required. Procedure: call `GET /shared-decks`, find each
   N1-N5 title in the response, read its `mode`. `"subscribed"` = lexeme-mode
   confirmed; `"copied"` = still legacy. `GET /shared-decks/{id}` (detail)
   reports the same `mode` per-deck if a narrower check is preferred.
4. *Option 2 -- DB check (heavier, only if Option 1 isn't sufficient).*
   Read-only SQL to run manually against the production database (example
   only, not executed here):
   ```sql
   -- find the N1-N5 deck ids/titles
   SELECT id, title FROM shared_decks WHERE title LIKE 'JLPT N%추천 어휘%';
   -- for each id: does it have lexeme-mode word rows?
   SELECT 1 FROM shared_deck_words WHERE shared_deck_id = ?;
   -- for each id: does it still have legacy rows?
   SELECT 1 FROM shared_deck_items WHERE shared_deck_id = ?;
   ```
5. *Interpretation.* `shared_deck_words` row exists / API `mode` is
   `"subscribed"` -> lexeme-mode confirmed for that deck. No
   `shared_deck_words` row / API `mode` is `"copied"` -> that deck is still
   legacy-mode. A mixed result across N1-N5 (some lexeme, some legacy) means
   a per-deck re-registration/migration decision, not a blanket one.
6. *If the result is false (still legacy) for any deck.* Re-running
   `seed_jlpt_shared_decks.py --apply` against production to re-register
   that deck is a **separate, destructive/production-affecting task**
   requiring its own approval -- it is out of scope for this verification
   step and must not be done as a side effect of just checking the state.
7. *Current limitation.* The Phase 9 local smoke
   (`smoke_test_jlpt_seed_lexeme_mode.py`) only proves the seed script's
   *code path* produces lexeme-mode output against a local SQLite fixture.
   It says nothing about what is actually sitting in production today by
   itself; the Phase 11 API check below records the live API state observed
   on 2026-07-30.

**Production API result (Phase 11 Round 1, 2026-07-30):** with user approval,
Codex ran one anonymous read-only `GET /shared-decks` request against the
deployed Render backend. No write endpoint, Neon SQL, or `.env` access was
used. All live N1-N5 shared decks returned `mode: "copied"`, so the live
production data is still legacy-mode even though the current seed script's
local code path now produces lexeme-mode decks.

| deck title | deck id | mode | interpretation | checked_at | endpoint |
| --- | ---: | --- | --- | --- | --- |
| N1어휘모음 | 9 | copied | still legacy-mode | 2026-07-30 | GET /shared-decks |
| N2어휘모음 | 8 | copied | still legacy-mode | 2026-07-30 | GET /shared-decks |
| N3어휘모음 | 7 | copied | still legacy-mode | 2026-07-30 | GET /shared-decks |
| N4어휘모음 | 2 | copied | still legacy-mode | 2026-07-30 | GET /shared-decks |
| N5어휘모음 | 1 | copied | still legacy-mode | 2026-07-30 | GET /shared-decks |

Follow-up: production re-registration or migration to lexeme-mode must be a
separate approved task. Do not re-run `seed_jlpt_shared_decks.py --apply`
against production as part of verification.

### Phase 12/14: production transition runbook and execution record

**Status (re-confirmed Phase 50): this runbook already ran once** — see the
"Phase 14 executed..." execution record below, with the resulting deck
ids/modes/vocab_counts. The Precheck/Execution/Rollback subsections below are
kept as a historical record of that one-time transition, not an outstanding
pre-release task; the `- [ ]` items in Precheck describe what was checked
before that run, not something to redo before every release. Do not re-run
the execution steps (or `seed_jlpt_shared_decks.py --apply`) against
production as part of routine release prep — that would create duplicate
shared decks. See "Phase 16: read-only post-transition health checks" below
for the correct routine (read-only, safe to re-run) way to confirm
production still matches this record.

This section documents the planned procedure for moving the live N1-N5
`shared_decks` rows off the legacy copied-mode path. **This
section was not run against production at Phase 12.** Phase 14 execution is recorded below. The original planning details include
design decisions (Round 0-1) and evidence verified only on a disposable local
SQLite scratch DB (Round 2). Where a claim is local-only evidence, it says so
explicitly.

**Decided strategy (Round 0-1): option A, then option B — never option C.**

1. Create brand new lexeme-mode N1-N5 shared decks (title
   `"JLPT N1 추천 어휘"` through `"JLPT N5 추천 어휘"`, the existing local
   package titles in `backend/data/jlpt/packages/`) via
   `seed_jlpt_shared_decks.py --apply` (no `--legacy`). Because
   `find_shared_deck_by_title()` matches on an exact title string and the
   live decks are titled `"N1어휘모음"`..`"N5어휘모음"` (confirmed different
   strings, Phase 11/Round 1), this creates **new** `shared_decks` rows —
   it does not reuse, overwrite, or in-place-convert the existing rows.
2. Once the new lexeme rows are confirmed healthy (see precheck/steps
   below), soft-unpublish the existing legacy copied-mode N1-N5 rows via
   `POST /shared-decks/{id}` delete (i.e. `delete_shared_deck()` —
   `visibility` flip only, same mechanism as the existing "owner unpublish"
   feature already in production).
3. **Option C (converting an existing legacy row in place by adding
   `shared_deck_words` to it) was rejected in Round 0/1** — reusing an
   existing legacy row's id would flip `is_lexeme_deck()` to `True` for that
   id, and `get_shared_deck()` would switch that id's detail view entirely to
   the lexeme-mode branch (`shared_deck_words` + `user_word_progress`) —
   an already-imported legacy subscriber has no `user_word_progress` row, so
   their real, already-recorded progress (in their own `vocab_items`) would
   appear to vanish from that deck's detail screen even though nothing was
   actually deleted. This risk is why a brand new row (option A) was chosen
   over any in-place approach.
4. **Keep the "both decks visible" window as short as practical.** Round 1
   found the frontend (`getDisplayTitle()`/`getDeckDescription()`/
   `getDeckCoverProps()` in `SharedDeckSection.tsx` and `shared.tsx`) render
   *any* deck matching the JLPT level pattern with the same normalized
   display title (`"JLPT 추천 어휘 {level}"`), same description, same cover
   art — regardless of whether the underlying DB title is
   `"N1어휘모음"` or `"JLPT N1 추천 어휘"`. A new user has effectively no way
   to tell the two N1 cards apart before importing either one. This is a
   known, **not fixed in Phase 12** frontend limitation — it is the reason
   step 2 above should follow step 1 promptly rather than leaving both decks
   public indefinitely, and it is a frontend follow-up candidate for a phase
   after this one (no frontend files were touched in Phase 12).

#### Precheck (must be done, and re-confirmed, before any production write)

- [ ] Re-run the Phase 11 read-only `GET /shared-decks` check to reconfirm
      current production N1-N5 deck id/title/mode/vocab_count immediately
      before executing (state may have changed since 2026-07-30).
- [ ] Confirm the new-deck title policy is still
      `"JLPT N1 추천 어휘"`..`"JLPT N5 추천 어휘"` (from
      `backend/data/jlpt/packages/jlpt_n{1..5}_recommended_deck.json`,
      `deck.name`) and that it still does **not** string-match any live
      production title.
- [ ] **production `owner_user_id` of the existing N1-N5 rows is unconfirmed
      by API alone** (Round 1 finding) — record as "unconfirmed", do not
      assume it matches or differs from the seed script's dev/admin account.
      If this needs resolving, that requires a separate, explicitly approved
      read-only Neon check — never assume it or query it as a side effect of
      an unrelated step.
- [ ] Any check requiring direct Neon SQL access is out of scope for this
      runbook and needs its own separate approval — the API-only checks above
      (`GET /shared-decks`) are the default, lighter-weight path (same
      reasoning as the Phase 10/11 verification procedure above).

#### Execution steps

1. Pick a maintenance window / low-traffic time.
2. Confirm a production database backup/snapshot exists and is recent
   (Render/Neon backup policy — outside this repo's scope to configure from
   here).
3. Run `seed_jlpt_shared_decks.py --apply` (no `--legacy`) against
   production for N1-N5, one deck package at a time.
4. `GET /shared-decks` — confirm 5 new rows exist with the expected titles.
5. Confirm each new row's `mode` is `"subscribed"`.
6. Confirm the existing legacy N1-N5 rows still report `mode: "copied"`
   (untouched) with their original ids/vocab_count.
7. Using a disposable test account, import one new lexeme deck and time it —
   expect near-instant completion (subscription-only, no per-word insert
   loop), unlike the legacy path's documented 5-10+ minute risk for N1-sized
   decks (see the "Known risk" note above).
8. Soft-unpublish the existing legacy copied N1-N5 rows (owner-only unpublish
   call, same mechanism already live for user-published decks).
9. From a logged-out/brand-new-account view, confirm the legacy rows no
   longer appear in `GET /shared-decks` and only the new lexeme rows do.
10. Spot-check at least one real existing user who previously imported a
    legacy N1-N5 deck: confirm their personal deck/vocab_items/review data
    and SRS state are completely unaffected (see "legacy subscriber gap"
    below for the one thing that **does** change for them).

Phase 14 executed the production transition with separate approvals for the
two write steps. First, five new lexeme-mode decks were created from the
checked-in package JSONs. Second, the old copied-mode decks were
soft-unpublished through the owner UI. No Neon SQL was run from Codex, no
`.env` file was read, and the old rows were not deleted.

| level | old copied id/title | final old state | new lexeme id/title | final new state |
| --- | --- | --- | --- | --- |
| N1 | 9 / N1어휘모음 | hidden from public list | 12 / JLPT N1 추천 어휘 | public, mode=subscribed, vocab_count=3475 |
| N2 | 8 / N2어휘모음 | hidden from public list | 13 / JLPT N2 추천 어휘 | public, mode=subscribed, vocab_count=1830 |
| N3 | 7 / N3어휘모음 | hidden from public list | 14 / JLPT N3 추천 어휘 | public, mode=subscribed, vocab_count=1834 |
| N4 | 2 / N4어휘모음 | hidden from public list | 15 / JLPT N4 추천 어휘 | public, mode=subscribed, vocab_count=640 |
| N5 | 1 / N5어휘모음 | hidden from public list | 16 / JLPT N5 추천 어휘 | public, mode=subscribed, vocab_count=684 |

Post-execution read-only `GET /shared-decks` confirmed that only the five new
lexeme-mode JLPT decks are present in the public list. During execution two
seed-script issues were found and fixed before continuing: PostgreSQL insert
id handling for `lexemes`, and per-word connection churn in
`seed_jlpt_shared_decks.py`. After the transition, an additional safeguard was
added so unauthenticated/dev-fallback users cannot see or call owner-only
shared-deck management actions for the newly seeded dev-owned decks.

#### Rollback / abort conditions

- If step 3 does not produce a new `shared_decks` row per deck — stop, do
  not proceed to any later step.
- If a new row's `mode` is not `"subscribed"` — stop; do **not** unpublish
  the corresponding legacy row.
- If importing a new row (step 7) increases the test account's `vocab_items`
  count (i.e. it silently took the legacy/bulk-copy path) — stop and
  investigate before touching any legacy row.
- Do not let both the legacy and new decks stay publicly visible longer than
  necessary to complete steps 4-7 — per the frontend display-collision
  finding above, an extended dual-visible window is itself a UX risk, not
  just an inefficiency.
- If soft-unpublishing a legacy row (step 8) causes an unexpected problem,
  it can be reversed with the existing owner-only republish call (flips
  `visibility` back to `'public'`; never touches
  `shared_deck_items`/`shared_deck_words`/`user_deck_subscriptions`/
  `user_word_progress`) — this reversal is safe to use during the runbook
  itself.
- Deleting or modifying the newly-seeded lexeme rows (as opposed to simply
  not proceeding further) is **out of scope for this runbook** and requires
  its own separate approval — this procedure only ever adds new rows and
  flips existing rows' visibility, nothing more.

#### Legacy subscriber gap (found in Round 2 local smoke, must be disclosed)

- A user who already imported a legacy copied-mode N1-N5 deck keeps their
  personal deck, `vocab_items`, and review/SRS history completely intact,
  regardless of anything done to the original shared deck afterward — this
  was true before Phase 12 and nothing in this runbook changes it.
- However, once the *original* shared deck (the one they imported from) is
  soft-unpublished, that user's own shared-deck bookshelf/list/detail view
  **no longer shows that original shared-deck card** — the same as a brand
  new user would experience. This is because the existing "owner unpublish
  — subscriber keeps seeing it" policy (see "Owner unpublish policy" in
  `docs/architecture/shared-lexeme-progress-storage.md`) was implemented and
  regression-tested only for **lexeme-mode subscriptions**
  (`user_deck_subscriptions`); a legacy-mode import only ever creates a
  `shared_deck_imports` row, which `list_shared_decks()`/`get_shared_deck()`
  never check in their post-unpublish visibility-widening logic.
  Confirmed locally by `smoke_test_jlpt_seed_coexistence.py` check 30
  (see below).
- **This is not data loss** — only the shared-deck-listing entry pointing
  back at the origin disappears from that user's own view; their personal
  vocabulary/progress is untouched and keeps working in the vocab/study
  tabs exactly as before.
- Whether to extend the unpublish-visibility-widening logic to also check
  `shared_deck_imports` (so a legacy importer keeps seeing the origin card
  too, matching lexeme-mode subscribers) is left as a **future phase
  decision** — no backend code was changed in Phase 12 to address this.

#### Round 2 local smoke evidence (`backend/scripts/smoke_test_jlpt_seed_coexistence.py`)

Verified locally only (disposable SQLite scratch DB, 30/30 checks passing as
of Round 2, 2026-07-31) — never against production:

- A simulated legacy copied-mode deck (`"N1어휘모음"`) and a newly seeded
  lexeme-mode deck (`"JLPT N1 추천 어휘"`) coexist as two separate
  `shared_decks` rows with the correct `mode` each (`"copied"` /
  `"subscribed"`).
- Importing the new lexeme deck is subscription-only: `mode: "subscribed"`,
  a `user_deck_subscriptions` row is created, and the importer's
  `vocab_items` count and personal deck count are both unchanged.
- Importing the legacy deck, by contrast, still takes the bulk-copy path:
  `mode: "copied"`, `vocab_items` count increases by the deck's word count,
  and a personal deck is created — reconfirms the legacy performance risk
  documented above still applies to any deck that stays on that path.
- After soft-unpublishing the legacy deck: the row and its
  `shared_deck_items` rows survive untouched, the already-imported legacy
  subscriber's personal `vocab_items`/deck counts are unaffected, and both a
  logged-out caller and a brand-new logged-in user see only the lexeme deck
  in `GET`-equivalent `list_shared_decks()` results — confirming the "A then
  B" strategy's intended new-user-facing outcome.
- The legacy subscriber gap described above (check 30) was also caught by
  this same smoke run.

#### Phase 16: read-only post-transition health checks

This is **not** part of the Phase 12/14 runbook above and does not execute
any of its steps. The runbook describes how the production transition was
performed (a one-time, approved write procedure); this subsection describes
how to *re-confirm afterward*, on a recurring basis, that production still
looks the way the runbook recorded it — a read-only check, safe to re-run
any time, that never calls a write endpoint, never touches Neon SQL
directly, and never reads `.env`.

**Rehearsal status (Phase 50):** these scripts were not actually run this
phase — no production backend base URL was provided in that session, and
this doc's own rule (never write a real URL here) means one can't be
hardcoded to unblock it. Recorded as blocked, not attempted-and-passed. Run
them with an explicitly-provided URL the next time this checklist is worked
end to end before a real release.

Three scripts, all under `backend/scripts/`:

- `run_shared_deck_health_checks.py <backend base URL>` — convenience
  wrapper for routine post-deploy checks. It runs the local package safety
  check first, then the production public-list check, and stops immediately
  if either one fails. Use this after deployments that touch shared-deck
  behavior, JLPT packages, import/review flows, or environment wiring.
- `check_production_shared_decks.py <backend base URL>` — calls exactly one
  endpoint, anonymous `GET /shared-decks` (no `Authorization` header, the
  same view a new visitor gets), and confirms: the five lexeme-mode JLPT
  decks (ids 12-16) are present with the expected title, `mode:
  "subscribed"`, `is_published: true`, and vocab count from the Phase 14
  table above; and the five legacy copied-mode decks (ids 9/8/7/2/1) do
  **not** appear in the public list. Exits non-zero if anything doesn't
  match. The backend base URL is always passed as a CLI argument — never
  hardcode or commit a real production URL (see the rule at the top of this
  file).
- `check_jlpt_package_safety.py` — local-only, no network calls. Confirms
  the 5 approved
  `backend/data/jlpt/packages/jlpt_n{1..5}_recommended_deck.json` files
  exist, `deck.name`/`vocab_items` count/`custom_terms` match the last
  verified snapshot, none of the known forbidden-copy phrases appear, and
  `git check-ignore` still treats each file as **not** ignored (i.e. the
  `.gitignore` exception documented in "Git Safety" below is still wired
  correctly).

If either script reports a failure: stop and report it, the same as any
other check in this document. Do not respond to a failure by re-running
`seed_jlpt_shared_decks.py --apply`, calling `DELETE`/`POST .../republish`,
or editing `packages/` files to make the check pass — a failing check here
means something about production or the local packages drifted from what
was recorded, which needs its own investigation and its own explicit
approval to fix, not a silent patch to match reality.

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
- [ ] `backend/data/jlpt/{raw,work,reviewed}/` and unapproved files under
      `backend/data/jlpt/packages/` are not staged. The five approved
      `backend/data/jlpt/packages/jlpt_n{1..5}_recommended_deck.json`
      packages are allowed after re-checking deck name, item counts, and
      `custom_terms == 0`.
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
