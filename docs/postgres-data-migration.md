# PostgreSQL Data Migration And Smoke Test

This guide covers a real PostgreSQL connection smoke test and a one-time copy from
the local SQLite development database to PostgreSQL. Do not commit `.env` files or
hardcode database passwords.

## 1. Set `DATABASE_URL`

Keep SQLite fallback by leaving `DATABASE_URL` empty:

```env
DATABASE_URL=
```

Use PostgreSQL by setting a runtime environment variable:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME
```

Use the hosting provider's secret manager or your local shell. Do not print or
commit the full URL.

## 2. Prepare An Empty PostgreSQL Database

For local PostgreSQL:

```bash
createdb jp_vocab_reader
```

For external PostgreSQL:

- Create a new empty database from the provider dashboard.
- Copy the connection string into a local environment variable only.
- Confirm network allowlists/firewalls permit your backend host.

The migration script is safest against an empty target DB. If target tables
already contain rows, it stops by default.

For the current production preparation, start from a clean PostgreSQL database.
The existing `backend/vocab.db` contains only test data, not meaningful user
data, so SQLite -> PostgreSQL data migration is intentionally skipped.

## 3. Before Starting The Backend

From `backend`:

```bash
pip install -r requirements.txt
python scripts/check_postgres_connection.py
```

The check prints the DB engine, PostgreSQL version, and whether these tables
exist:

- `users`
- `decks`
- `vocab_items`
- `custom_terms`
- `shared_decks`
- `shared_deck_items`
- `shared_deck_terms`
- `shared_deck_imports`

It masks the password and does not print the full `DATABASE_URL`.

## 4. Migrate SQLite Data

Keep `backend/scripts/migrate_sqlite_to_postgres.py` in the repository, but run
it only when the existing SQLite database contains meaningful user data that must
be preserved. For this project stage, the existing SQLite data is test data only,
so do not run the migration for production setup.

Default source:

```bash
python scripts/migrate_sqlite_to_postgres.py
```

Custom SQLite source:

```bash
set SQLITE_DB_PATH=C:\path\to\vocab.db
python scripts/migrate_sqlite_to_postgres.py
```

The script copies:

- `users`
- `decks`
- `vocab_items`
- `custom_terms`
- `shared_decks`
- `shared_deck_items`
- `shared_deck_terms`
- `shared_deck_imports`

It prints row counts before and after migration, preserves `id` values where
possible, and resets PostgreSQL identity sequences after the copy.

If PostgreSQL already has data, the default behavior is to stop. The dangerous
overwrite mode is explicit:

```bash
python scripts/migrate_sqlite_to_postgres.py --allow-overwrite
```

Use that only on a disposable target database, because it truncates the target
PostgreSQL tables before copying.

## 5. PostgreSQL Mode API Smoke List

After starting the backend with PostgreSQL `DATABASE_URL`, verify:

- `GET /health`
- `GET /me`
- `POST /auth/register`
- `POST /auth/login`
- `GET /decks`
- `POST /decks`
- `GET /vocab-items`
- `POST /vocab-items`
- `GET /study-items`
- `POST /study-items/{item_id}/review`
- `GET /stats`
- `GET /custom-terms`
- `POST /custom-terms`
- `GET /shared-decks`
- `POST /decks/{deck_id}/publish`
- `POST /shared-decks/{shared_deck_id}/import`

Check insert-created IDs, duplicate-save behavior, search filters, due-date
filters, and shared-deck publish/import flows.

## 6. Return To SQLite Fallback

Unset `DATABASE_URL`:

```env
DATABASE_URL=
```

Then restart the backend. The app returns to `backend/vocab.db`. Do not delete
the SQLite file after migration until PostgreSQL backup and restore have been
tested.

## 7. Troubleshooting Order

1. Confirm `DATABASE_URL` is set only in the runtime environment and is a
   `postgresql://` or `postgres://` URL.
2. Run `python scripts/check_postgres_connection.py`.
3. Confirm `psycopg[binary]` is installed from `requirements.txt`.
4. Confirm the target database is empty before migration.
5. Run the migration and compare before/after row counts.
6. Start the backend and check `GET /health` shows `database: postgresql`.
7. Smoke test auth, decks, vocab items, study review, stats, custom terms, and
   shared deck import.
8. If anything fails, unset `DATABASE_URL` and restart to return to SQLite.
