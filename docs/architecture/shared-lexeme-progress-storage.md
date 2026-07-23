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
- ~~No review-flow integration~~ -- **done in phase 3** (see below): the
  Study tab's card-flip review flow now includes subscribed-deck lexeme
  words, merged in via a `StudyCardItem` adapter layer. `/stats` is still
  entirely `vocab_items`-based (deferred to phase 4/5, see phase 3's
  section below), and `review_logs` is still vocab-only (also phase 4, see
  below) -- both `POST .../review` (lexeme) and `record_review()` (vocab)
  update only their own progress table, with no lexeme-side review-history
  log written anywhere yet.
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

## Phase 3: SRS card integration

Phase 3 wires subscribed shared-deck/JLPT-recommended-deck words into the
actual Study (복습) tab's card-flip review flow, which phase 2 explicitly
left alone. Personal `vocab_items` review is completely unchanged -- this
is additive merging, not a rewrite of the review flow.

### Backend

- **New read-only endpoint**: `GET /study-items/lexemes` (optional
  `shared_deck_id`, `due_only` query params), backed by
  `list_subscribed_lexeme_study_items()` in
  `app/repositories/lexeme_repository.py`. Reuses the already-tested
  `list_shared_deck_words_with_progress()` once per subscribed deck rather
  than a new SQL join, then de-duplicates by `lexeme_id` (the same lexeme
  can be linked into more than one subscribed deck, but a user has at most
  one `user_word_progress` row per lexeme -- it must only ever show up as
  one study card). Excludes `status = 'known'` words, same policy as
  `vocab_items`. Passing a `shared_deck_id` the user isn't actually
  subscribed to returns an empty list rather than leaking that deck's
  words. **Never creates a `user_word_progress` row** -- merely listing the
  queue stays exactly as read-only as the existing deck-detail view.
- **No new write endpoint.** Rating a lexeme study card still calls the
  phase-1 `POST /shared-decks/{shared_deck_id}/words/{lexeme_id}/review`
  endpoint (`record_lexeme_review()`), which already lazily creates/updates
  `user_word_progress` and never touches `vocab_items` or the shared
  `lexemes` row. Nothing changed in that function this phase.
- **Progress-less lexeme words are new-word study material.** A lexeme
  with no `user_word_progress` row overlays as `status: "unclassified"`,
  `review_level: 0`, `next_review_at: null` (unchanged phase-1 overlay
  contract) -- the study queue treats that exactly like a personal
  `vocab_items` row that's never been reviewed.

### Frontend: a common study-card shape, not a rewrite

- `StudyCardItem` (`components/types.ts`) is a strict superset of the
  existing `VocabItem` type (`VocabItem & { item_type, vocab_item_id,
  lexeme_id, shared_deck_id, source_label }`), built via two adapters in
  `app/page.tsx` -- `toVocabStudyCardItem()` (tags an existing
  `/study-items`/`/vocab-items` row `item_type: "vocab"`) and
  `toLexemeStudyCardItem()` (maps a `GET /study-items/lexemes` row into the
  same shape, with a synthetic **negative** `id` (`-lexeme_id`) so it can
  never collide with a real, positive `vocab_items` id in the same list/key
  space). `/study-items`, `/vocab-items`, and their response shapes are
  byte-for-byte unchanged -- the unification happens entirely client-side,
  as an adapter layer over the existing endpoints, per this phase's "add an
  adapter, don't rewrite the flow" brief.
- `StudySection.tsx`'s props widened from `VocabItem[]`/`VocabItem` to
  `StudyCardItem[]`/`StudyCardItem` -- since `StudyCardItem` is a superset,
  every existing render path (front word, reading, meaning, example
  sentence, rating buttons) keeps working unchanged for vocab cards. Two
  small, additive changes only: (1) the card header shows
  `· {source_label}` next to the mode label for a lexeme card, so it's
  visually obvious which deck a subscribed-deck word came from; (2) the
  "뜻 수정"/"뜻 오류 신고" controls only render `if (item_type ===
  "vocab")` -- editing a shared lexeme's common meaning from the study
  card was never in scope (phase 2 already drew this line for the deck
  tab; phase 3 keeps it).
- **Rating submission branches on `item_type`** in
  `submitStudyReview()` (`app/page.tsx`): a `"vocab"` card keeps calling
  `POST /study-items/{id}/review` exactly as before; a `"lexeme"` card
  calls `POST /shared-decks/{shared_deck_id}/words/{lexeme_id}/review`
  instead and patches only the matching `studyItems` entry (never
  `setVocabItems`, since a lexeme rating is not a `vocab_items` row).
- **Where lexeme words get merged into the queue**: for the "오늘 복습"
  (today) and "새 단어 학습" (new) modes with no specific *personal* deck
  selected, `fetchStudyItems()` merges in every subscribed deck's due (today)
  or `status === "unclassified"` (new) lexeme words alongside the vocab
  ones. Selecting one specific personal deck keeps that session scoped to
  that deck's own `vocab_items`, same as before -- lexeme words only mix in
  for the "everything" view.
- **Subscribed decks are selectable for "덱별 학습"**: the existing deck
  `<select>` in `StudySection.tsx` gained an `<optgroup label="학습
  목록">` listing every actively-subscribed shared deck (`sharedDecks`
  already fetched via `GET /shared-decks`, filtered to
  `mode === "subscribed" && imported_at`), value-prefixed `shared:<id>` so
  it shares the same string-keyed `<select>` value space as a personal
  deck's plain numeric id. Picking one studies only that deck's lexeme
  words, with `today`/`new`/`uncertain`/`unknown`/`all` filtering the same
  status values a lexeme's `user_word_progress` can hold (identical
  `VALID_STATUSES` set to `vocab_items`). "방금 담은 단어 복습" (recent) is
  a personal-vocab-only concept and returns no items for a selected shared
  deck.
- **Wording**: only "가져온 덱" / "학습 목록" / a deck's own title are
  used; no "복사된 단어" phrasing (there's nothing copied), no "공식
  JLPT" phrasing anywhere in the new code or UI strings.

### review_logs: still vocab-only, lexeme logging now in Phase 4

`review_logs.vocab_item_id` is a `NOT NULL` FK into `vocab_items` -- a
lexeme rating has no row to point that at. As phase 1 already flagged, this
phase (3) does not touch `review_logs` at all: a lexeme rating updates only
`user_word_progress`, with no reviewed-word history log written anywhere
yet. Phase 4 (see below) adds that log via a new, separate, additive table
instead of retrofitting `review_logs` itself.

### stats/dashboard: intentionally not touched this phase

`GET /stats`/`build_stats()` stays entirely `vocab_items`-based, unchanged.
Full lexeme-aware stats (e.g. "오늘 복습" including subscribed-deck due
words in the dashboard's own count, not just the study queue actually
studying them) is **deferred to phase 4/5** -- mixing an approximate,
possibly-inconsistent lexeme count into `/stats`' existing, precisely
`vocab_items`-scoped numbers was judged riskier than useful for this phase.
The Study tab's own in-session counters (session rating counts, "N / M"
progress) already reflect the merged queue correctly, since those are
computed from `studyItems.length`/`sessionCounts` client-side, not from
`/stats`.

### Storage regression, extended

`check_shared_deck_storage_regression.py` and
`check_shared_deck_publish_storage_regression.py` (both already existing)
still pass unchanged after this phase. A new companion script,
`backend/scripts/check_shared_deck_srs_regression.py`, additionally guards
that:

- Merely **listing** the study queue (`list_subscribed_lexeme_study_items()`
  / `GET /study-items/lexemes`) creates **zero** `user_word_progress` rows,
  at any deck size (verified at 200 and 1000 words) -- only an actual
  rating submission does.
- One rating on one lexeme item lazily creates exactly **one**
  `user_word_progress` row, and rating that same item again **updates that
  row in place** (no duplicate).
- `vocab_items` never grows, at any point in this flow (import, listing,
  first rating, repeated rating).
- A lexeme shared by two different subscribed decks appears as exactly
  **one** de-duplicated study card, not two.
- A shared deck the user never subscribed to never leaks its words into
  the study queue, even if its id is passed explicitly.

## Phase 4: lexeme review logs

Phase 4 gives a subscribed shared-deck/JLPT word's review history somewhere
to live, without ever touching `review_logs` (the existing, vocab-only
review-history table phases 1-3 all deliberately left alone -- see above).

### The new table: `lexeme_review_logs`

Purely additive, created via `CREATE TABLE IF NOT EXISTS` in both the
SQLite and PostgreSQL branches of `ensure_schema`/`create_postgres_tables`
(`app/database.py`), exactly like every other table this project's lexeme
storage has added. Never touches or migrates `review_logs`.

| Column | Notes |
| --- | --- |
| `id` | PK |
| `user_id` | FK -> `users(id)` |
| `lexeme_id` | FK -> `lexemes(id)` |
| `shared_deck_id` | FK -> `shared_decks(id)`, **nullable** -- which deck the rating was made through, if known |
| `rating` | `"again"` \| `"hard"` \| `"good"` \| `"easy"` |
| `previous_review_level` / `new_review_level` | before/after the SRS step this rating applied |
| `previous_next_review_at` / `new_next_review_at` | before/after `next_review_at` |
| `previous_status` / `new_status` | before/after `user_word_progress.status` -- currently always equal, since rating a word (lexeme or vocab) has never changed its status in this codebase; logged anyway for schema completeness / in case that ever changes |
| `created_at` | when this rating was recorded |

Indexes: `(user_id, created_at)`, `(user_id, lexeme_id)`,
`(user_id, shared_deck_id)`, `(lexeme_id)` -- mirrors `review_logs`' own
`(user_id, reviewed_at)` / `(vocab_item_id)` index shape, adapted for the
extra `shared_deck_id` dimension a lexeme rating has that a vocab one
doesn't.

### `record_lexeme_review()`: one call, two writes

`app/repositories/lexeme_repository.py`'s `record_lexeme_review()` gained
one new parameter, `shared_deck_id: int | None = None`, and now does two
things in the same function call (same as `vocab_repository.record_review()`
already does for `vocab_items` + `review_logs`):

1. Everything it already did in phase 1-3, unchanged: lazily create
   `user_word_progress` via `get_or_create_progress()` if it doesn't exist,
   apply `compute_review_schedule()` (same fixed-step SRS ladder as
   `vocab_items`), `UPDATE user_word_progress`.
2. **New**: capture `previous_review_level`/`previous_next_review_at`/
   `previous_status` *before* the update, and `new_review_level`/
   `new_next_review_at`/`new_status` *after* it, then `INSERT INTO
   lexeme_review_logs` with both, plus `user_id`/`lexeme_id`/
   `shared_deck_id`/`rating`/`created_at`.

Both writes happen inside the same `with get_connection() as connection:`
block as the existing progress update -- a rating always produces both
rows together, never one without the other. `POST
/shared-decks/{shared_deck_id}/words/{lexeme_id}/review`
(`app/main.py`) passes its own path parameter straight through as
`shared_deck_id`, so a rating made from a specific deck's card is logged
with that deck's id; a caller with only a `lexeme_id` (no deck context)
can still log, with `shared_deck_id = NULL`.

**Never created by a read.** `get_or_create_progress()` itself (called
from `update_word_status()` too, and from listing overlays) does not
insert into `lexeme_review_logs` -- only `record_lexeme_review()` does,
and only for an actual rating submission. Listing the study queue
(`GET /study-items/lexemes`) or opening a subscribed deck's word list
creates zero `lexeme_review_logs` rows, exactly like it already creates
zero `user_word_progress` rows.

### API / frontend: unchanged

`LexemeWordProgressResponse` (the response shape of both
`PATCH .../progress` and `POST .../review`) was **not changed** -- it
still returns exactly `lexeme_id`, `status`, `review_level`,
`next_review_at`, `correct_count`, `wrong_count`, `last_reviewed_at`. The
frontend's phase-3 `submitStudyReview()` lexeme branch (which already
calls `POST /shared-decks/{shared_deck_id}/words/{lexeme_id}/review` with
the deck id it already has) required **zero changes** this phase -- the
request/response contract it was already built against didn't move.

### Storage regression, extended again

`backend/scripts/check_lexeme_review_logs_regression.py` (new) guards, on
top of everything the phase-1/2/3 scripts already check (all of which
still pass unchanged):

- Import and merely listing the study queue create **zero**
  `lexeme_review_logs` rows.
- One rating creates exactly **one** `user_word_progress` row (lazy
  create, unchanged from phase 3) **and exactly one** `lexeme_review_logs`
  row.
- Rating the *same* lexeme again creates **zero** additional
  `user_word_progress` rows (updated in place) but **one more**
  `lexeme_review_logs` row -- the log is per rating *event*, the progress
  row is per word.
- `vocab_items` never grows at any point.
- A rating with no `shared_deck_id` still logs, with `shared_deck_id =
  NULL`.
- The existing personal `vocab_items` review flow
  (`vocab_repository.record_review()`) still logs to `review_logs` exactly
  as before, and never writes to `lexeme_review_logs`.

### What phase 4 deliberately did not do

- **`/stats` still doesn't read `lexeme_review_logs`.** No lexeme-aware
  stats/dashboard integration this phase either -- still deferred, now to
  **phase 5** (see below).
- **No lexeme meaning-feedback flow.** The existing `/feedback/meaning`
  endpoint is still `vocab_items`-scoped only; reporting a shared lexeme's
  meaning as wrong has no dedicated flow yet.
- **No legacy shared-deck migration.** Decks published before the
  lexeme-mode publish change (phase before this one) still have no
  `shared_deck_words` rows and stay on the legacy `vocab_items`-copying
  import path, untouched.

### Next phase candidates

1. **Lexeme stats/dashboard integration** -- fold `lexeme_review_logs` +
   `user_word_progress` into `/stats`' due/new/reviewed-today counts
   alongside `vocab_items`, once a design exists for how an approximate
   merged number should be presented without undermining trust in the
   existing precise `vocab_items`-only numbers.
2. **Lexeme meaning feedback** -- a "오류 신고" entry point for a shared
   lexeme's common meaning, separate from the existing `vocab_items`-scoped
   one.
3. **Legacy shared-deck migration** -- backfilling pre-lexeme-mode shared
   decks into `lexemes`/`shared_deck_words`, and deciding how (or whether)
   to reconcile already-copied personal `vocab_items` rows against the new
   progress/log tables.

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

## Every new shared deck, not just JLPT decks, is lexeme-based

The intent of this storage model is that **any newly created shared deck**
-- JLPT-recommended or user-published -- stores its words once in
`lexemes` + `shared_deck_words`, so import always costs one
`user_deck_subscriptions` row regardless of deck size, and `user_word_progress`
is always created lazily, only on a real status change or review. As of the
user-publish lexeme-mode change, this now covers both creation paths:

- **JLPT-recommended decks**: lexeme-based by default. Registering a deck
  package via `scripts/seed_jlpt_shared_decks.py` (no `--legacy` flag)
  upserts each word into `lexemes` and links it via `shared_deck_words`; see
  "JLPT registration script" above.
- **User-published shared decks are now lexeme-based too.** `POST
  /decks/{deck_id}/publish` (`publish_deck()` in
  `app/repositories/shared_deck_repository.py`) upserts every one of the
  publisher's `vocab_items` **and** `custom_terms` into `lexemes` and links
  them via `shared_deck_words` (see "custom_terms handling" and
  "Deck-specific meaning/context snapshot" below for exactly how). A brand
  new publish writes **zero** rows to the legacy `shared_deck_items`/
  `shared_deck_terms` tables. `is_lexeme_deck()` is therefore `True` for
  every deck published from now on, so it gets the same import/read
  behavior as a JLPT deck: `import_shared_deck()` only creates a
  `user_deck_subscriptions` row, never bulk-copies into the importer's
  `vocab_items`.
- **Legacy shared decks (JLPT or user-published) already out in the wild
  keep working unchanged.** A deck published *before* this change has no
  `shared_deck_words` rows, so `is_lexeme_deck()` stays `False` for it
  forever, and it continues to be served from
  `shared_deck_items`/`shared_deck_terms` exactly as before -- reading and
  importing it is completely untouched. Converting those existing legacy
  decks to lexeme-mode is a separate, deliberately deferred migration phase
  (see "Existing data / migration policy" above), not something this change
  or the regression tests below assume.
- **Known edge case, not fixed here:** a personal deck with literally zero
  `vocab_items` and zero `custom_terms` produces zero `shared_deck_words`
  rows on publish, so `is_lexeme_deck()` would report it as legacy-mode by
  the same "has at least one row" heuristic used everywhere else. This is
  harmless in practice (an empty deck stays empty and importable either
  way) and not worth a dedicated flag column for a deck with no content.

## custom_terms handling policy

Chose **option A: custom_terms are converted to lexemes**, not kept on a
separate legacy fallback path, because the schemas turned out to line up
closely enough that dropping or side-lining them wasn't necessary --
sharing a user's data (even a custom term) should never silently disappear.

- Mapping: `custom_terms.term` -> `lexemes.surface` **and**
  `lexemes.base_form` (a custom term has no separate base/surface
  distinction); `custom_terms.reading` -> `lexemes.reading`;
  `custom_terms.part_of_speech` -> `lexemes.part_of_speech` (kept as
  whatever grammatical tag the user chose, e.g. `명사`/`동사` -- not
  forced to a literal `"custom"` value, so that information isn't lost);
  `custom_terms.meaning_ko` -> `lexemes.meaning_ko` (only on first
  creation, see the meaning-overwrite policy below); `dictionary_gloss` is
  left empty (custom_terms has no equivalent field).
- `lexemes.source_type = "user_published_custom_term"` marks a lexeme that
  originated from a custom term (as opposed to `"user_published_deck"` for
  a regular vocab item, or `"jlpt"` for a JLPT-registered word) -- purely
  informational bookkeeping, not currently surfaced in any API response.
- Custom terms are linked into the **same** `shared_deck_words` list as
  regular vocab items (`sort_order` continues after the vocab items), not
  kept in a visually separate list. This matches how a lexeme-mode deck
  already works for JLPT decks: `get_shared_deck()`'s lexeme-mode branch
  always returns `custom_terms: []` and puts everything in the unified
  `items` list -- true for a JLPT deck, and now true for a user-published
  deck too. The frontend doesn't need to change to see a converted custom
  term; it just shows up as another word in the deck's word list.
- `custom_terms.description` (a short free-text note) maps to the deck-specific
  `context_explanation_ko` snapshot slot on `shared_deck_words` (see below)
  rather than being dropped, since it's the closest equivalent to a short
  per-word note.
- The publisher's own `custom_terms` rows are never deleted or modified by
  publishing -- exactly like `vocab_items`, they're read-only inputs to the
  upsert, left completely untouched afterward.

## Deck-specific meaning/context snapshot (additive `shared_deck_words` columns)

A publisher's personal wording for a word (their own `meaning_ko`, a short
`example_sentence`, a short `context_explanation_ko`) must be preserved and
shown in *their* deck, but must never be force-written onto the shared
`lexemes` row that other decks/users/publishers share -- two different
publishers sharing the exact same word (same `base_form`/`reading`/
`part_of_speech`) must each keep seeing their own wording, not clobber each
other's.

- Five nullable, additive columns were added to `shared_deck_words` (both
  the SQLite and PostgreSQL branches of `ensure_schema`, plus a SQLite
  `add_column_if_missing`-based migration and a PostgreSQL
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for a table that may already
  exist from before this change): `display_meaning_ko`, `example_sentence`,
  `context_explanation_ko`, `tags_json` (reserved, not populated yet --
  no tagging feature exists on vocab_items to source it from),
  `published_note` (reserved, not populated yet).
- `publish_deck()` always snapshots the publisher's own `meaning_ko` (and,
  for regular vocab items, `example_sentence`/`context_explanation_ko`) onto
  `shared_deck_words.display_meaning_ko`/etc for that specific
  `(shared_deck_id, lexeme_id)` row -- regardless of whether the underlying
  `lexemes` row was just created or already existed from an earlier
  publisher.
- `upsert_lexeme()` gained a `refresh_shared_fields: bool = True` parameter.
  The JLPT registration script keeps calling it with the default `True`
  (curated content is *meant* to refresh `meaning_ko`/`dictionary_gloss`
  on re-registration). `publish_deck()` always calls it with
  `refresh_shared_fields=False`: if a matching lexeme already exists, its
  `surface`/`meaning_ko`/`dictionary_gloss` are left exactly as they are
  (only `jlpt_level` is opportunistically filled in via `COALESCE` if it
  was previously unset) -- a publisher can enrich the shared word pool by
  creating a lexeme that doesn't exist yet, but can never overwrite one
  that does.
- Overlay display priority, applied in
  `lexeme_repository._normalize_progress_overlay()`: a word's shown
  `meaning_ko` is `shared_deck_words.display_meaning_ko` if set, otherwise
  `lexemes.meaning_ko`. `example_sentence`/`context_explanation_ko` come
  straight from the `shared_deck_words` snapshot (legacy JLPT-seeded decks
  never set them, so they stay `null` there exactly as before this change).
  `status`/`review_level`/etc keep coming from `user_word_progress` only,
  unaffected.
- Same short-text policy as the existing legacy `shared_deck_items` columns
  applies to these snapshots: `example_sentence` is a short example, not a
  full source passage; `context_explanation_ko` is a short note. Nothing
  about the "no full original text" policy changes -- these columns just
  give a user-published lexeme-mode deck the same per-word display
  richness a legacy deck already had, without touching the shared
  `lexemes` row.

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

### User-published deck storage regression

`backend/scripts/check_shared_deck_publish_storage_regression.py` is the
companion check for the *other* way a shared deck is created: a real user
publishing their own personal deck (`publish_deck()`), rather than the JLPT
registration script. Same disposable-local-SQLite-only setup, same
`--count` flag (>= 100, default 200, also verified at 1000). In addition to
the import/status-change deltas above, it also asserts:

- Publishing a deck with N `vocab_items` + M `custom_terms` creates exactly
  N + M `shared_deck_words` rows, zero new `shared_deck_items`/
  `shared_deck_terms` rows, and leaves the publisher's own `vocab_items`/
  `custom_terms` row counts completely unchanged (retained, not moved or
  deleted).
- The published deck is detected as lexeme-mode (`is_lexeme_deck()` ->
  `True`).
- Every custom term appears in the deck's word list/overlay (via
  `list_shared_deck_words_with_progress`) with its own meaning intact --
  not silently dropped, and `get_shared_deck()`'s `custom_terms` field is
  `[]` (merged into `items` instead, matching the JLPT lexeme-deck
  convention).
- **Meaning-collision protection**: a second publisher publishing a
  different personal deck that happens to contain the exact same
  `(base_form, reading, part_of_speech)` as an existing lexeme does not
  create a duplicate `lexemes` row, does not change that lexeme's shared
  `meaning_ko`, and still shows *their own* wording in *their own* deck via
  the `display_meaning_ko` snapshot -- while the first publisher's deck
  keeps showing the first publisher's original wording.

Run it the same way as the JLPT-deck check, still never against Neon:

```
cd backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL="sqlite:///./vocab_publish_lexeme_scratch.db"
python scripts/check_shared_deck_publish_storage_regression.py
python scripts/check_shared_deck_publish_storage_regression.py --count 1000
```

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
