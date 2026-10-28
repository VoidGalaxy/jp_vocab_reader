# Gate B-2: transactional reviews and explicit migration

## Verdict and boundaries

Implemented and verified on synthetic SQLite. Stop for Gate B-2 review.
This is NOT a production conversion-readiness verdict: PostgreSQL is not
available locally, and incomplete-history initialization requires approval.

Branch: `codex/fsrs-srs-replacement`.
Unchanged HEAD: `e2c07f8bcc534713587f628cf3f8f9f798bb2e5a`.

Gate B-1's pinned engine and corrected completion/configuration rules were
retained. The four completion conditions remain a simulation-only draft.
No default engine switch, startup replay, actual user migration, frontend
queue/session wiring, staging, commit, push or merge was performed.
All migration apply/rollback executions used synthetic databases.

## Changed files

New implementation:

- `backend/app/srs/storage.py`: shared transaction locks, access checks,
  state serialization, fingerprints and compare-and-swap updates.
- `backend/app/srs/reviews.py`: normalized request receipts and atomic FSRS
  evaluation, first-review evidence and draft completion evidence.
- `backend/app/srs/migration.py`: explicit account/card scope, read-only
  preview, resumable apply and history-preserving rollback.
- `backend/scripts/inspect_srs_migration.py`: read-only preview command,
  restricted to explicitly named synthetic test databases.

Integration:

- `backend/app/database.py`: optional read-only connections. Existing B-1
  additive schema initialization was preserved.
- `backend/app/repositories/vocab_repository.py` and
  `lexeme_repository.py`: transaction dispatch and legacy version increments.
- `backend/app/schemas.py`: optional strict request safety fields and optional
  FSRS response metadata.
- `backend/app/main.py`: same review URLs, new fields forwarded, explicit
  HTTP errors and response models retaining legacy field shape.

Tests:

- `backend/tests/test_srs_transactions.py`: 36 new tests.
- `backend/tests/test_srs_http.py`: one real loopback HTTP server test.
- `backend/tests/test_srs_schema.py`: B-1 legacy assertions adjusted only for
  the additive card-version increment; legacy scheduling assertions retained.

This report and `POSTGRES_HISTORY_PROPOSAL.md` are new. Pre-existing B-1
files, requirements pin and plan documents were not replaced. The user's
existing `docs/roadmap.md` edit, untracked assets and references were preserved.
No frontend product file was changed for B-2.

## Bundle 1: atomic evaluations

### API compatibility

Existing POST URLs remain `/study-items/{item_id}/review` and
`/shared-decks/{shared_deck_id}/words/{lexeme_id}/review`.
Legacy cards keep the original request bodies, classification policy,
schedule calculation and response field shape. Legacy ratings increment
`srs_card_version` so a prepared migration cannot overwrite a later rating.
They do not become receipt-protected FSRS ratings automatically.

An FSRS card requires `request_id`, `expected_card_version`, and `session_id`.
Identifiers have bounded ASCII syntax; the version is a strict nonnegative
integer. Missing safety fields return 422, not an unsafe legacy fallback.
Account identity comes from authentication and rating time from the server.
Session identity is validated as a request identifier, not yet against a
server-issued queue/session registry; that registry/UI wiring is outside B-2.

Current card/account access and current subscription membership are checked
before a receipt can be returned. Permission loss returns 404 even for a
previously accepted request. Same account + same request ID + same normalized
payload returns the stored first response, even after the card version advances.
Changing card, grade, session, expected version, deck context or response timing
with that request ID returns 409 with no writes. Different request IDs using
one card version yield one success and one 409.

### Transaction and concurrency

SQLite uses `BEGIN IMMEDIATE`; PostgreSQL code locks the account row and card
row, and holds the subscription/membership rows through the review transaction.
The PostgreSQL path has not been executed. Account serialization is intentional
for cross-card receipt IDs; its PostgreSQL throughput has not been benchmarked.

CAS card update, one original-table review log, first-review metadata,
first-completion evidence, configuration validation and one receipt commit
together. Injected failures after card/log changes and during receipt insertion
roll back all of them. First Again is one introduction; another rating of the
same card is not another introduction. No daily-goal cap rejects an accepted
card. Seoul introduction totals are derived from first original log timestamps,
including legacy events; migration adds no review events.

Personal and subscribed concurrency tests use actual overlapping threads and
separate SQLite connections, not just sequential retry calls. The first writer
is held inside engine evaluation while the second attempts its transaction.
Duplicate IDs return equal results; competing IDs produce one conflict. Final
card version, log count and receipt count are asserted. One ASGI test also
overlaps HTTP handlers. A separate child Uvicorn process verifies both URLs
over real loopback HTTP, authentication, retry/conflict and revoked access.
Its lifespan is disabled only to avoid unrelated startup dictionary downloads;
review routes, engine, auth and SQL are not mocked.

No claim is made that browser stale-response protection, dynamic FSRS queues,
retry UI or an entire application session is now safe; those are later gates.

## Bundle 2: migration and rollback

### Preview and evidence

Default preview has no run/config/snapshot writes, schema initialization or
progress creation. Read-only SQLite URI mode refuses a missing database instead
of creating it; query-only mode also rejects an injected write. Database bytes
and row counts are unchanged. The read-only CLI requires explicit test database,
account and card IDs, and has no apply switch.

Scope is explicit and limited to one account. Candidate evidence includes card
version, full card fingerprint, original-log fingerprint, last log ID, history
quality and proposed values. Original word contents are not printed by the CLI.
Run metadata fixes engine/library/configuration version and exact candidate scope.
Card snapshots are database audit data, not copied into this report.

Complete replay requires valid grades/times, counters, ordered log-chain
consistency, final card values and, when present, FSRS before/after snapshots.
Short same-grade intervals are flags only, not automatic duplicate removal or
incompleteness. Same-timestamp ambiguous history is conservatively blocked.
No original log, classification or server ID is rewritten or deleted.
Legacy levels are not converted to stability days.

### Apply and resume

Apply requires an explicit approval argument, run key and scoped preview. Each
card is locked and re-inspected; stale reviews, edits or a forged candidate
produce conflict rather than overwriting data. Snapshot, CAS update and persisted
cursor/results commit together. A bounded batch can stop and resume; committed
cards are not applied twice. Mid-batch failure leaves previous committed cards
and resumes from the failed cursor. Run keys cannot be reused for another scope.

The first effective reservation remains the original `next_review_at` and
`srs_effective_due_at`; the engine's independently calculated reservation is
`srs_due_at`. Migration does not create today's introduction events. Existing
known cards become paused only in explicit migration, without changing their
classification. There is no automatic re-entry action.

Incomplete candidates have no applicable values and remain legacy with their
history, learning evidence and schedule intact. The initial Learning/Review/
Relearning state to use on their next actual FSRS rating is NOT approved.
Accordingly, such a transition is blocked rather than silently treating a
previously learned card as new. A malformed FSRS card with history but no engine
state likewise fails closed. This part of the requested policy is pending a
contract decision, not represented as implemented.

Subscribed words without an existing `user_word_progress` row are reported
unavailable rather than creating progress during preview/migration. Opt-in
creation of new FSRS cards belongs to the subsequent queue/activation gate.

### Rollback

Rollback does not copy an old snapshot over a live card. It checks versions and
post-transition log sequence, reconstructs the legacy reservation projection
using the actual subsequent grades/times, and preserves those log rows,
receipts, counters, last-rating time, current edits/classification and first
completion evidence with metric provenance. It increments, never resets, the
card version. Deleted cards are not recreated. Conflicted cards are not forced.
Injected failures roll back the entire rollback transaction.

A rollback run is idempotent. The source apply run is closed after rollback so
a partially applied source cannot resume and undo the rollback unexpectedly.
Re-transition can validate retained FSRS snapshots and replay the unmodified
mixed history. API retry still retrieves its original receipt after rollback,
subject to current access permission; it does not add another review.

## Verification results

All database executions were isolated synthetic SQLite. Environment overrides
were set before application imports. No production, Neon, ordinary local
database or remote PostgreSQL connection was used.

| Check | Result | Evidence scope |
| --- | --- | --- |
| Backend discovery | 144 total: 143 passed, 1 skipped | SQLite + pure engine + mocked SQL guards |
| New B-2 tests | 37 passed, included above | 36 transactional/migration/API + 1 loopback HTTP |
| Frontend tests | 73/73 passed | Existing pure tests; frontend unmodified |
| Frontend typecheck | Passed | Existing application types |
| Existing regression scripts | 7 passed | SQLite and SQL compatibility inspection |
| Current-SRS audit | 15/15 passed | Synthetic SQLite |
| Diff whitespace check | Passed | Product and report edits |
| Real PostgreSQL execution | Not run | No local PostgreSQL; schema test skipped |

Regression scripts: `check_shared_deck_srs_regression.py`,
`check_lexeme_srs_status_policy_regression.py`,
`check_lexeme_review_logs_regression.py`, `check_lexeme_stats_regression.py`,
`check_postgres_boolean_sql_compat.py`, `smoke_test_shared_lexeme_progress.py`,
and `check_database_safety_guard.py`. The boolean compatibility script is NOT
a PostgreSQL server integration test. Learning-plan/history/permission tests
are also included in backend discovery.

The full suite reports a dependency deprecation warning for Starlette's current
httpx TestClient integration, not a test failure. Loopback HTTP error responses
are explicitly closed. No dependency update was made for that warning.
No frontend build was repeated because frontend product code is unchanged.

## Pending contracts and unverified areas

1. Approve the incomplete-history initialization state/policy before implementing
   its first actual FSRS review. Current tooling blocks those candidates.
2. Approve PostgreSQL card-log preservation strategy before changing constraints;
   see `POSTGRES_HISTORY_PROPOSAL.md`. Current PostgreSQL CASCADE remains.
3. Completion conditions still require separate simulation/product approval.
4. Run schema, contention, permission revocation, rollback and deletion tests on
   a guarded empty local PostgreSQL test database before conversion readiness.
5. UI/queue wiring and production conversion are explicitly outside this gate.

SQLite deletion preservation was exercised on real constraints. PostgreSQL
constraints were inspected in source only. The deletion-policy discrepancy is
not repaired or hidden by this report, and no clinical/learning-effectiveness
claim follows from these synthetic engineering tests.

## Cleanup and handoff

The owned loopback server was terminated and waited for. Only B-2-owned
synthetic database directories were removed after final checks. Existing
servers, databases, user changes, untracked references/assets and generated
frontend files were not removed. No credentials, token, database connection
string or actual user source text is included in these artifacts.

Stop at Gate B-2 review. Do not run apply against actual users or proceed to
Gate C based solely on the SQLite pass results.
