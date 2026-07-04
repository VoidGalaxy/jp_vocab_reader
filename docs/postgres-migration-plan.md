# PostgreSQL Migration Plan

## 1. Current SQLite Structure

- The backend currently uses raw `sqlite3` queries and a shared `get_connection()` helper in `backend/app/database.py`.
- The default database is `backend/vocab.db` when `DATABASE_URL` is not set.
- `DATABASE_URL=sqlite:///./vocab.db` can point the app at another SQLite file.
- Repository modules under `backend/app/repositories` keep feature-level data access separated for decks, vocab items, custom terms, stats, shared decks, deck packages, and users.
- App startup still uses idempotent `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` checks instead of a migration tool.
- Personal data is scoped by `user_id` across `decks`, `vocab_items`, and `custom_terms`.
- Shared deck data is stored in `shared_decks`, `shared_deck_items`, `shared_deck_terms`, and `shared_deck_imports`.
- Large dictionary data such as full JMdict remains file-based and should not be moved into the app database in the first PostgreSQL migration.

## 2. Why Move To PostgreSQL

- SQLite is good for local development, but a shared web service needs stronger concurrent write behavior.
- PostgreSQL provides connection pooling support, better indexing, transactional guarantees under load, and mature backup/restore tooling.
- PostgreSQL makes production operations easier for hosted deployments that provide managed databases and `DATABASE_URL`.
- PostgreSQL gives clearer paths for future reporting, shared deck marketplace features, moderation, and user-level operational tooling.

## 3. Required Migration Work

- Decide whether to introduce SQLAlchemy, an async DB layer, or a smaller internal adapter around the current repository functions.
- Decide whether to introduce Alembic for schema migrations. The current startup-time `CREATE TABLE` and `ALTER TABLE` approach should not be the long-term production migration mechanism.
- Map SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` semantics to PostgreSQL `GENERATED ... AS IDENTITY`, `SERIAL`, or `BIGSERIAL`.
- Review `TEXT` and `DATETIME` fields that currently store ISO strings and decide which should become `timestamp with time zone`.
- Decide whether booleans and status values remain text fields or become constrained text / enum-like values.
- Remove SQLite-specific SQL and PRAGMA usage from repository paths that need to run on PostgreSQL.
- Review transaction boundaries, especially deck import/export, shared deck publish/import, delete-with-items, and schema initialization.
- Add connection pooling for the production PostgreSQL connection.
- Make `DATABASE_URL` the deployment source of truth while keeping SQLite as the local default.
- Keep the current API response shapes stable while changing the storage backend.

## 4. Data Migration Strategy

- Back up the existing SQLite file before every migration rehearsal.
- Export SQLite tables in dependency order: `users`, `decks`, `vocab_items`, `custom_terms`, `shared_decks`, `shared_deck_items`, `shared_deck_terms`, and `shared_deck_imports`.
- Preserve existing `user_id` values so personal data ownership stays intact.
- Preserve `shared_decks` and import history so published decks and imported deck references remain meaningful.
- Preserve vocab item learning fields: `status`, `correct_count`, `wrong_count`, `review_level`, `next_review_at`, and `last_reviewed_at`.
- Preserve custom term deck scope, including `deck_id = null` common terms.
- Validate row counts and a small set of representative user/deck records after import.
- Run application-level smoke tests against the PostgreSQL staging database before any production cutover.

## 5. Risks

- Local SQLite files can contain user data; take explicit backups before migration scripts touch them.
- SQLite and PostgreSQL differ in type enforcement, primary key behavior, default values, and constraint handling.
- Date/time strings may parse differently when moved into timestamp columns.
- Japanese/Korean text must remain UTF-8 throughout export/import.
- Existing raw SQL uses SQLite placeholder syntax and may need adapter work before it can target PostgreSQL.
- Shared deck import/publish flows copy data across tables and need transaction safety during migration.
- Full JMdict files should remain on disk or in separate object storage, not in PostgreSQL, unless a later search/indexing design calls for it.

## 6. Recommended Sequence

1. Current stage: `postgres-readiness`.
   - Keep SQLite as the only supported runtime database.
   - Centralize DB URL parsing and connection setup.
   - Document the PostgreSQL migration path.
2. Next stage: migration abstraction.
   - Introduce a narrow DB adapter or repository execution layer without changing API behavior.
   - Identify SQLite-specific SQL that must change.
3. Decide whether to introduce SQLAlchemy and Alembic.
   - If adopted, move schema changes out of startup logic and into versioned migrations.
   - If not adopted, design a small explicit migration runner.
4. Build and test a staging PostgreSQL database.
   - Run schema creation, data import, API smoke tests, and shared deck workflows.
5. Plan production cutover.
   - Freeze writes or schedule a maintenance window.
   - Back up SQLite.
   - Import into PostgreSQL.
   - Point production `DATABASE_URL` at PostgreSQL after the app supports it.
   - Keep rollback instructions and the last SQLite backup available.
