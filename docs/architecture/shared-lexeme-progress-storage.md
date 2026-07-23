# Shared Lexeme + User Progress Storage (Phase 1)

## Problem

Before this change, importing a shared/JLPT-recommended deck copied every
word into the importing user's own `vocab_items` table (`import_shared_deck`
in `app/repositories/shared_deck_repository.py`, one `INSERT` per word).
For a deck like "JLPT N1 추천 어휘" (~3,475 words), every user who imports it
adds ~3,475 rows to `vocab_items`. That scales linearly with
`users x imported decks x words per deck` -- fine for a handful of users,
not fine as the app grows.

The JLPT-deck registration script (`scripts/seed_jlpt_shared_decks.py`) had
the same problem one level up: it created the deck as a **personal** deck
for the dev/admin user (copying every word into that user's `vocab_items`),
then published *that* personal deck as the shared deck. So even the act of
publishing a JLPT deck bloated one user's vocabulary.

## What changed

Four new tables, additive only, created via `CREATE TABLE IF NOT EXISTS` in
`app/database.py` (both the SQLite and PostgreSQL branches of
`ensure_schema`/`create_postgres_tables`). Nothing about `decks`,
`vocab_items`, `shared_decks`, `shared_deck_items`, `shared_deck_terms`,
`shared_deck_imports`, or `review_logs` was touched, removed, or migrated.

| Table | Purpose |
| --- | --- |
| `lexemes` | The shared word data itself (surface/base_form/reading/part_of_speech/meaning_ko/dictionary_gloss/jlpt_level), stored **once**. Unique on `(base_form, reading, part_of_speech)`. |
| `shared_deck_words` | Links a `shared_decks` row to the `lexemes` it contains, with a `sort_order`. Unique on `(shared_deck_id, lexeme_id)`. |
| `user_deck_subscriptions` | "This user imported this shared deck." One row per `(user_id, shared_deck_id)` -- **not** one row per word. |
| `user_word_progress` | Per-user status/SRS state for a lexeme (`status`, `review_level`, `next_review_at`, `correct_count`, `wrong_count`, `last_reviewed_at`). Unique on `(user_id, lexeme_id)`, created **lazily** -- only when the user actually does something with that word. |

A shared deck is considered **lexeme-mode** purely by having at least one
`shared_deck_words` row (`is_lexeme_deck()` /
`is_lexeme_deck_in_connection()` in `app/repositories/lexeme_repository.py`
-- no new column on `shared_decks`, no flag to keep in sync). A deck
published the old way (from a personal deck, via `publish_deck`) never gets
one, so it stays on the legacy path automatically, forever, with zero
special-casing required.

### Import (`POST /shared-decks/{id}/import`)

`import_shared_deck()` in `shared_deck_repository.py` now dispatches:

- **Lexeme-mode deck**: `_import_lexeme_shared_deck()` only creates/reuses a
  `user_deck_subscriptions` row (idempotent -- importing twice does not
  duplicate it, does not re-copy anything). No `vocab_items`, no personal
  `decks` row, no `user_word_progress` rows.
- **Legacy deck**: `_import_shared_deck_legacy()` -- byte-for-byte the
  original behavior (personal deck + full `vocab_items`/`custom_terms`
  copy), completely unchanged.

`SharedDeckImportResponse` gained additive fields (`success`, `mode`
("copied" | "subscribed"), `subscribed`, `shared_deck_id`, `word_count`) so
old client code reading only `deck_id`/`deck_name`/`imported_vocab_count`/
`imported_custom_term_count` still gets sane values either way (for a
subscribed import, `deck_id` is the shared deck's own id and
`imported_vocab_count` reports the deck's word count, since nothing was
literally "imported" into a personal deck).

### Reading a deck's words (`GET /shared-decks/{id}`)

For a lexeme-mode deck, `get_shared_deck()` builds `items` from
`shared_deck_words JOIN lexemes LEFT JOIN user_word_progress` (see
`list_shared_deck_words_with_progress()`), keyed on the current user. A word
with no progress row still comes back -- as `status: "unclassified"`,
`review_level: 0`, `next_review_at: null`, `correct_count`/`wrong_count: 0`
-- it is never dropped for lacking progress. `SharedDeckItemResponse` gained
additive optional fields (`lexeme_id`, `jlpt_level`, `status`,
`review_level`, `next_review_at`, `correct_count`, `wrong_count`) that stay
`null` for legacy decks, which never populate them. A `due_only` query
param filters to words that still need review (unclassified/unknown/
uncertain and due), for the minimal review flow below.

### Status change / review rating (lazy create)

Two new endpoints, entirely new routes (zero collision with existing ones):

- `PATCH /shared-decks/{id}/words/{lexeme_id}/progress` -- body `{"status":
  "known" | "uncertain" | "unknown" | "unclassified"}`.
- `POST /shared-decks/{id}/words/{lexeme_id}/review` -- body `{"rating":
  "again" | "hard" | "good" | "easy"}`, uses the exact same fixed-step SRS
  ladder (`compute_review_schedule`) `vocab_items` review already uses.

Both call `get_or_create_progress()` first -- a `user_word_progress` row is
created *only* on the first real action a user takes on that word, never in
bulk at import time. This is the core of the storage-growth fix: importing
a 3,475-word deck costs 1 row (`user_deck_subscriptions`); actually studying
40 of those words costs 40 rows (`user_word_progress`), not 3,475.

### JLPT-level tagging during reading (`/analyze`)

`app/jlpt_level_service.py`'s word -> JLPT-level index used to build itself
only from `shared_deck_items` (deck-title pattern matching). If new JLPT
decks stopped populating that table, the "JLPT 추천 N5" tag shown on words
while reading would have silently stopped working for anything registered
after this change. Fixed additively: the index now also reads
`lexemes.jlpt_level` directly (no deck-title parsing needed there, since
each lexeme already carries its own level) and merges both sources. Legacy
decks are completely unaffected.

## JLPT registration script (`scripts/seed_jlpt_shared_decks.py`)

Default behavior changed: registering a deck package now upserts each word
into `lexemes` and links it via `shared_deck_words`, creates/reuses a public
`shared_decks` row, and touches **no** personal deck or `vocab_items` for
any user -- not even the dev/admin user, unlike before. `--legacy` restores
the exact previous behavior (personal deck copy + `publish_deck`) for
anyone who still needs it. Both modes still default to a read-only dry run;
`--apply` is required to write anything.

Not carried over yet: `custom_terms` in a deck package have no lexeme-mode
equivalent (phase-2 TODO, see below) -- the script prints a note and skips
them when registering in lexeme mode.

## What phase 1 deliberately did not do (superseded by phase 2 below where noted)

- ~~No frontend UI for browsing/studying a subscribed deck's words~~ --
  **done in phase 2** (see below): the deck tab now has an interactive word
  list with status controls for a subscribed deck.
- **No review-flow integration.** Still true after phase 2. `/study-items`,
  `/study-items/{id}/review`, and `/stats` are entirely `vocab_items`-based,
  unchanged. `POST .../review` updates `user_word_progress` directly but does
  **not** write to `review_logs` (that table's `vocab_item_id` column is a
  NOT NULL FK into `vocab_items`, which doesn't fit a lexeme-keyed review).
  A `lexeme_review_logs` table (or a nullable/polymorphic `review_logs`
  redesign), plus actually wiring a subscribed deck into the Study tab's
  card-flip review flow, is left for **phase 3**.
- **No custom-term lexeme equivalent.** Still true. Deck packages can carry
  `custom_terms`; lexeme-mode registration currently skips them.
- **No automatic cleanup of previously-copied vocabulary.** Still true. See
  "Existing data" below.

## Phase 2: frontend learning UI integration

Phase 2 connects the phase-1 API surface to the actual app instead of
leaving it backend-only. Scope, deliberately kept to the shared-deck (덱)
tab -- no changes to VocabSection (노트) or StudySection (복습).

### What's now possible end-to-end

- **Subscribing.** `GET /shared-decks` now returns an additive `mode`
  field (`"copied"` | `"subscribed"`) per deck, computed once via
  `list_lexeme_deck_ids()` -- the frontend knows a deck's storage mode
  *before* the user clicks anything, not just after importing.
  `SharedDeckSummary`/`SharedDeckDetail` (frontend types) carry it through.
- **Deck-card button reflects real state** (`SharedDeckSection.tsx`):
  not-yet-subscribed lexeme deck -> "학습 목록에 추가"; already-subscribed
  lexeme deck -> the same button becomes "열기" and just opens the deck
  (no re-import call, no "다시 가져오기 하시겠어요?" confirm -- there is
  nothing to re-copy). Legacy decks keep their exact previous "내 노트에
  가져오기" / "다시 가져오기" behavior, untouched. The "가져옴" badge reads
  "학습 목록에 있음" for a subscribed deck instead.
- **Opening a subscribed deck shows a real word list**, not a 20-word
  preview: every word in the deck, each with a `<select>` status control
  (known/uncertain/unknown/unclassified, reusing the existing
  `StatusSelect` component from `components/shared.tsx` -- no new UI
  component). A word with no progress row shows "분류되지 않음"
  (unclassified), exactly per the phase-1 overlay contract. The always-empty
  custom-terms column is hidden for subscribed decks (lexeme decks never
  have any).
- **Status change is lazy-create, end to end.** Picking a status calls
  `PATCH /shared-decks/{id}/words/{lexeme_id}/progress`
  (`updateSharedDeckWordStatus` in `app/page.tsx`), which creates the
  `user_word_progress` row on first use, updates it on every later change,
  optimistically updates the dropdown, and rolls back with an error message
  if the request fails. Re-fetching the deck (e.g. after closing and
  reopening it) confirms the status persisted server-side, not just in
  local state.
- **Type separation**: `SharedDeckItem` (the wire shape, additive fields
  only populated for subscribed decks) vs. the new `SharedDeckWordProgress`
  (camelCase, UI-facing, `lexemeId` instead of a bare `id`) -- converted via
  `toSharedDeckWordProgress()` in `SharedDeckSection.tsx`. `VocabularyItem`
  (personal vocab_items row) was not touched; nothing conflates a
  `lexeme_id` with a personal vocab item's `id`.

### What phase 2 deliberately does not do

- **No cross-tab navigation.** Chose the "Option B" design explicitly
  allowed by the phase-2 brief: a subscribed deck's word list lives inside
  the 덱 tab's own existing detail panel (via "열기"), not a new nav
  destination, not a source-mode toggle inside VocabSection, and not a new
  StudySection entry point. `VocabSection.tsx` and `StudySection.tsx` have
  zero changes this phase.
- **No 복습 (Study) tab integration.** A subscribed deck's words cannot be
  selected as a study source in the Study tab yet, and rating a word there
  doesn't touch `user_word_progress` (only the deck tab's own
  status-dropdown does, via `PATCH .../progress`; the `POST .../review`
  rating endpoint from phase 1 exists and is smoke-tested but has no caller
  in the frontend yet). Full SRS/review-flow integration remains phase 3,
  exactly as phase 1 already flagged.
- **No personal meaning edits on lexemes.** Only a status dropdown is
  exposed for a subscribed deck's words; "뜻 수정" stays a personal-vocab
  (`vocab_items`) feature. If a lexeme's shared meaning is wrong, the
  correct phase-2 action would be a "오류 신고" entry point -- not built
  yet (no UI hook added this phase; the existing `/feedback/meaning`
  endpoint is `vocab_items`-scoped, not lexeme-scoped).

## Existing data / migration policy

- **Nothing is deleted, converted, or backfilled in phase 1.** Every
  existing user's `vocab_items` rows (including ones copied from a
  previously-imported shared deck) are left exactly as they are.
- **Every shared deck published before this change stays on the legacy
  path forever** (it has no `shared_deck_words` rows, so
  `is_lexeme_deck()` is always `False` for it) -- importing it still copies
  into `vocab_items`, exactly like before this change shipped.
- **Only newly-registered decks** (via `seed_jlpt_shared_decks.py` without
  `--legacy`) use the new structure, starting now.
- A future phase-2 migration could backfill existing legacy shared decks
  into `lexemes`/`shared_deck_words` and, separately, decide whether/how to
  reconcile already-copied personal `vocab_items` rows against the new
  progress table. Deliberately not attempted here -- it would need its own
  review (in particular: what happens to a user's existing
  `review_level`/`next_review_at` history for a word that also becomes a
  lexeme).

## Goal: every new shared deck, not just JLPT decks, should be lexeme-based

The intent of this storage model is that **any newly created shared deck**
-- JLPT-recommended or user-published -- stores its words once in
`lexemes` + `shared_deck_words`, so import always costs one
`user_deck_subscriptions` row regardless of deck size, and `user_word_progress`
is always created lazily, only on a real status change or review.

- **JLPT-recommended decks**: already lexeme-based by default. Registering a
  deck package via `scripts/seed_jlpt_shared_decks.py` (no `--legacy` flag)
  upserts each word into `lexemes` and links it via `shared_deck_words`; see
  "JLPT registration script" above.
- **User-published shared decks are NOT yet lexeme-based.** `POST
  /decks/{deck_id}/publish` (`publish_deck()` in
  `app/repositories/shared_deck_repository.py`) still only ever copies the
  publishing user's `vocab_items`/`custom_terms` into
  `shared_deck_items`/`shared_deck_terms` -- the legacy structure. It never
  writes `lexemes` or `shared_deck_words`. That means **every shared deck an
  end user creates through the app today is legacy-mode**, and importing it
  will grow the importer's `vocab_items` exactly as before this phase. This
  is a known gap, not an oversight: converting the user-publish path to
  lexeme-mode needs its own design pass (e.g. how to reconcile a publisher's
  personal `meaning_ko`/`context_explanation_ko` edits, which have no home on
  a shared `lexemes` row) and is left as a **TODO for a later phase**, tracked
  alongside the phase-3 review-flow integration item above.
- **Legacy shared decks (JLPT or user-published) already out in the wild
  keep working unchanged** -- converting them to lexeme-mode is a separate,
  deliberately deferred migration phase (see "future phase-2 migration"
  above), not something this phase or the regression test below assumes.

## Storage regression testing

`backend/scripts/check_shared_deck_storage_regression.py` guards the core
storage promise above at scale. It seeds one lexeme-mode shared deck with a
configurable number of test lexemes (`--count`, minimum 100, defaults to
200; also verified at 1000), then asserts, via before/after row-count
snapshots against a disposable local SQLite DB (never `backend/vocab.db`,
never a Neon `DATABASE_URL`):

- Importing the deck changes `vocab_items` by exactly **0**, regardless of
  deck size.
- Importing the deck changes `user_deck_subscriptions` by exactly **+1**,
  and re-importing the same deck changes it by **0** (idempotent, no
  duplicate subscription row).
- Importing the deck changes `user_word_progress` by exactly **0** (no
  bulk/eager creation).
- Changing one word's status afterwards changes `user_word_progress` by
  exactly **+1** (lazy create, one row per acted-on word) and still changes
  `vocab_items` by **0**.

Run it locally (always under a session-scoped local-SQLite `DATABASE_URL`
override -- see the repo's local-server safety rules, never against Neon):

```
cd backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL="sqlite:///./vocab_storage_test_scratch.db"
python scripts/check_shared_deck_storage_regression.py
python scripts/check_shared_deck_storage_regression.py --count 1000
```

It exits non-zero with a specific `RegressionFailure` message naming which
table's row-count delta didn't match if the storage promise above is ever
violated (e.g. a future change accidentally reintroduces bulk-copying into
`vocab_items` or eager `user_word_progress` creation on import).

## Operational note: the shared dev/staging Neon database

During phase-1 verification, restarting the local backend dev server (to
pick up these code changes) triggered the app's normal startup-time
`init_db()` against whatever `DATABASE_URL` `backend/.env` has configured
-- which turned out to be a remote Neon PostgreSQL instance the project
already treats as its working dev/staging database, not a local
`vocab.db` file. Because `init_db()`/`create_postgres_tables()` only ever
runs `CREATE TABLE IF NOT EXISTS ...`, this most likely already created the
four new tables (`lexemes`, `shared_deck_words`, `user_deck_subscriptions`,
`user_word_progress`) there, empty, with no data written and no existing
table/row touched. Per instruction, this was not further inspected or
modified from Claude Code -- verify directly via the Neon dashboard if
confirmation is needed. All subsequent verification in this phase
(smoke test script, `compileall`) was pointed at a local, disposable SQLite
file only.
