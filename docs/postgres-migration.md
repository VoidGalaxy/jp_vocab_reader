# PostgreSQL Migration Foundation

This stage adds PostgreSQL connection support while preserving the existing SQLite development fallback.

## 1. SQLite Fallback

If `DATABASE_URL` is empty or unset, the backend continues to use the existing SQLite database at `backend/vocab.db`.

Local development can keep using:

```bash
cd backend
uvicorn app.main:app --reload
```

No existing SQLite data is deleted or migrated by this stage.

## 2. DATABASE_URL

SQLite fallback:

```env
DATABASE_URL=
```

PostgreSQL:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

The backend chooses the database engine at startup:

- Empty `DATABASE_URL`: SQLite
- `sqlite:///...`: SQLite
- `postgresql://...` or `postgres://...`: PostgreSQL through `psycopg`

## 3. What Was Added

- Minimal PostgreSQL dependency: `psycopg[binary]`.
- Connection branching in `backend/app/database.py`.
- Query adapter for repository compatibility:
  - SQLite keeps `?` placeholders.
  - PostgreSQL receives `%s` placeholders.
  - `INSERT OR IGNORE` is adapted to `ON CONFLICT DO NOTHING`.
  - PostgreSQL inserts return `id` so existing `cursor.lastrowid` call sites can keep working.
- PostgreSQL `CREATE TABLE IF NOT EXISTS` schema for:
  - `users`
  - `decks`
  - `vocab_items`
  - `custom_terms`
  - `shared_decks`
  - `shared_deck_items`
  - `shared_deck_terms`
  - `shared_deck_imports`

## 4. API Checks For PostgreSQL

When a real PostgreSQL database is available, verify these APIs:

- `GET /health`
- `GET /me`
- `POST /auth/register`
- `POST /auth/login`
- `POST /analyze`
- `GET /decks`
- `POST /decks`
- `PATCH /decks/{deck_id}`
- `DELETE /decks/{deck_id}`
- `GET /vocab-items`
- `POST /vocab-items`
- `PATCH /vocab-items/{item_id}`
- `DELETE /vocab-items/{item_id}`
- `GET /custom-terms`
- `POST /custom-terms`
- `PATCH /custom-terms/{term_id}`
- `DELETE /custom-terms/{term_id}`
- `GET /study-items`
- `POST /study-items/{item_id}/review`
- `GET /stats`
- `GET /vocab-items/export.csv`
- `GET /decks/{deck_id}/export-package`
- `POST /decks/import-package`
- `POST /decks/{deck_id}/publish`
- `GET /shared-decks`
- `GET /shared-decks/{shared_deck_id}`
- `POST /shared-decks/{shared_deck_id}/import`

## 5. Deferred Data Migration

SQLite data migration is not performed in this stage.

Next stage should add an explicit migration/export/import path for moving existing `backend/vocab.db` data into PostgreSQL. Do not point production traffic at PostgreSQL until migration and rollback have been tested.

## 6. External PostgreSQL Testing

Supabase, Neon, Render PostgreSQL, Railway PostgreSQL, or another managed PostgreSQL service should be tested in the next stage.

This stage does not connect to any external PostgreSQL service.

## 7. Known Follow-Up Work

- Replace startup-time schema creation with versioned migrations.
- Decide whether to introduce SQLAlchemy and Alembic.
- Convert ISO string datetime fields to `TIMESTAMPTZ` after timezone policy is settled.
- Audit repository SQL under a real PostgreSQL database.
- Add backup and restore procedures before production traffic.
