# PostgreSQL Readiness

This pass prepares the current SQLite codebase for a later PostgreSQL migration without installing PostgreSQL, connecting to PostgreSQL, adding SQLAlchemy, or adding Alembic.

## Current SQLite Structure

- Runtime database is still SQLite.
- Default local database file is `backend/vocab.db`.
- `DATABASE_URL` may point to a SQLite URL such as `sqlite:///./vocab.db`.
- PostgreSQL URLs are intentionally rejected for now.
- App startup creates missing tables and applies idempotent SQLite compatibility migrations.
- Repository functions use raw `sqlite3` queries and return `sqlite3.Row` data converted to dictionaries.

## Main Tables

- `users`: local/dev users and registered users.
- `decks`: user-owned vocab decks.
- `vocab_items`: user-owned vocabulary, review state, example sentence, dictionary gloss, and AI explanation.
- `custom_terms`: user-owned common or deck-specific custom dictionary terms.
- `shared_decks`: public shared deck metadata.
- `shared_deck_items`: copied vocab metadata for public shared decks.
- `shared_deck_terms`: copied custom terms for public shared decks.
- `shared_deck_imports`: shared deck import history.

## What Changed In Readiness

- DB startup flow is now grouped in `backend/app/database.py`:
  - `create_core_tables()`
  - `create_shared_deck_tables()`
  - `apply_sqlite_migrations()`
  - `seed_dev_user()`
  - `backfill_existing_data_to_dev_user()`
  - `ensure_default_decks_for_users()`
  - `ensure_default_deck_for_user(user_id)`
- SQLite `ALTER TABLE ADD COLUMN` is guarded by:
  - `column_exists(conn, table_name, column_name)`
  - `add_column_if_missing(conn, table_name, column_definition)`
- Existing data is preserved. NULL `user_id` values in personal tables are assigned to the dev user.
- Missing or invalid `vocab_items.deck_id` values are backfilled to each owning user's default deck.
- ISO datetime strings remain the storage format via `now_iso()`.

## SQLite-Specific Code To Revisit

- `sqlite3.connect`, `sqlite3.Row`, and direct `?` placeholders.
- `PRAGMA foreign_keys = ON`.
- `PRAGMA table_info(...)` for schema inspection.
- `INTEGER PRIMARY KEY AUTOINCREMENT`.
- `cursor.lastrowid`.
- `INSERT OR IGNORE`.
- Ad hoc `ALTER TABLE ADD COLUMN` startup migrations.
- ISO datetime string comparison for `next_review_at <= now`.
- `LOWER(...) LIKE ?` search behavior and collation.
- Table rebuild migrations using `CREATE TABLE ..._new`, `DROP TABLE`, and `ALTER TABLE ... RENAME`.

## PostgreSQL Migration Work

1. Add SQLAlchemy models while keeping SQLite as the runtime database.
2. Move repository queries behind SQLAlchemy or a stable DB adapter while preserving API responses.
3. Add Alembic only after models and metadata are stable.
4. Convert SQLite startup migrations into versioned Alembic migrations.
5. Add PostgreSQL connection settings and test against a real PostgreSQL instance.
6. Add deployment DB configuration, backups, connection pooling, and migration runbooks.

## Risks

- Existing data migration from SQLite to PostgreSQL needs a tested export/import or ETL path.
- Any missing `user_id` filter can expose personal decks, vocab, custom terms, study state, stats, or package data.
- Shared deck public/private policy must stay explicit: public shared deck reads are allowed, personal deck reads are user-scoped.
- Datetime strings should become a deliberate `TIMESTAMPTZ` policy before production PostgreSQL.
- Large JMdict files should not be stored in git and may need separate loading/indexing strategy.
- AI usage logging is not yet modeled; future cost/rate-limit policy likely needs `ai_usage_logs`.

## Recommended Order

1. SQLAlchemy models.
2. Same behavior on SQLite through SQLAlchemy.
3. Alembic migrations.
4. PostgreSQL connection.
5. Deployment DB settings and operations.
