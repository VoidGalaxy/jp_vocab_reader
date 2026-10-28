# PostgreSQL review-history preservation: approval required

## Current evidence

In `backend/app/database.py`, SQLite's `review_logs` and
`lexeme_review_logs` keep integer card identifiers without a card foreign key.
The real synthetic SQLite deletion test confirms that deleting the card does
not remove its evaluation log. Rollback never recreates a missing card.

The PostgreSQL definitions instead contain:

- `review_logs.vocab_item_id`: non-null card reference with `ON DELETE CASCADE`.
- `lexeme_review_logs.lexeme_id`: non-null lexeme reference with `ON DELETE CASCADE`.
- Both log tables retain account references with `ON DELETE CASCADE`.

Therefore PostgreSQL card deletion currently removes the corresponding rating
history. These are source definitions, not an inspection of an actual server's
catalog. A deployed database could have older/different constraints.
No local PostgreSQL was available and no remote database was accessed.

## Recommended contract, NOT implemented

Decouple the historical card/lexeme identifier from the live card foreign key,
while keeping that stable non-null identifier and the log's account ownership.
This aligns card-deletion behavior with SQLite, preserves existing log IDs and
ratings, and avoids bringing deleted cards back. Keep the existing account
deletion policy and account FK unchanged. New evaluations must continue to
validate live card ownership/subscription before inserting logs.

Do not replace IDs with nulls: that loses the grouping identity used for first
introduction and audit/rollback. Do not add card soft-delete/tombstone behavior
in this gate: it expands CRUD, privacy and queue contracts unnecessarily.

Approval must explicitly cover retaining evaluation history after a card is
deleted, the lifetime of receipts/snapshots containing historical audit data,
and the account-erasure behavior. This proposal does not authorize retention
of user content beyond the existing deletion contract or new public access.
Snapshot privacy/account deletion should be audited in that follow-up as well;
the existing B-1 snapshot table has no account FK.

## Follow-up implementation and validation

1. Use only the existing guarded empty local PostgreSQL test database policy.
   Inspect real catalog constraints first; do not assume their generated names.
2. Test the existing CASCADE behavior and then an explicit, reviewed constraint
   migration. Preserve account foreign keys and all original log fields/rows.
3. Verify personal deletion, lexeme deletion, account deletion, history query
   account isolation, first-introduction totals and orphan-history rendering.
4. Verify receipts cannot authorize an evaluation or expose a deleted card.
   Verify rollback leaves deleted cards deleted.
5. Re-run real overlapping reviews/migration/rollback on PostgreSQL, including
   current subscription revocation and failure after intermediate writes.
6. Provide backup/reversal and old-schema compatibility evidence before any
   actual deployment or user migration.

No constraint migration or deletion-policy change was executed in Gate B-2.
Until approved and verified, PostgreSQL conversion readiness is blocked.
