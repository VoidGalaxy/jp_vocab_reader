# Database safety guard: blocking accidental Neon connections from local dev

## Problem

`backend/.env`'s `DATABASE_URL` has, at times, pointed at a remote Neon
PostgreSQL instance that the project treats as its working dev/staging
database, not a local SQLite file. Starting the backend locally (`uvicorn
app.main:app --reload`) runs a FastAPI startup hook that calls `init_db()`
(`app/main.py`'s `@app.on_event("startup")`), which -- with no guard --
would run schema creation/migration (`CREATE TABLE IF NOT EXISTS ...`,
`ALTER TABLE ... ADD COLUMN ...`) against whatever `DATABASE_URL` is
currently configured, Neon included. This already happened once during
local verification of an earlier phase (see the "Operational note" in
[shared-lexeme-progress-storage.md](../architecture/shared-lexeme-progress-storage.md)) --
harmless that time (additive `CREATE TABLE IF NOT EXISTS` only, nothing
destructive), but not something to rely on staying harmless.

## What was added

Three pure functions in `backend/app/database.py`, wired into the single
choke point every database access in the app goes through --
`get_connection()` -- so the check runs before *any* connection object
(SQLite or PostgreSQL) is created, and specifically before
`psycopg.connect(...)` for a PostgreSQL URL:

- `is_neon_database_url(database_url: str) -> bool` -- true if the URL
  string contains `neon.tech`. A substring check, not a full URL parse;
  good enough for the one real host this guards against, and doesn't
  require parsing (or logging) the URL itself anywhere.
- `normalize_app_env(app_env: str | None) -> str` -- lowercases/trims
  `APP_ENV`; a missing or blank value normalizes to `"development"`, never
  to `"production"`. An unset `APP_ENV` must never be the thing that lets a
  Neon `DATABASE_URL` slip through.
- `assert_safe_database_url(database_url: str | None, app_env: str | None) -> None`
  -- raises `RuntimeError` if `is_neon_database_url(database_url)` is true
  and `normalize_app_env(app_env)` is not `"production"`. A local SQLite
  `DATABASE_URL`, or no `DATABASE_URL` at all, is always allowed regardless
  of `APP_ENV`.

`get_connection()` calls `assert_safe_database_url(get_database_url(),
get_app_env())` as its first statement, before branching on whether the URL
is PostgreSQL or SQLite. Because `init_db()` -> `initialize_database()` ->
`get_connection()` is the very first thing `init_db()` does, this
transitively blocks `init_db()` (and every other DB operation) before any
connection, schema read, or migration statement runs -- regardless of
whether `init_db()` is reached via the FastAPI startup hook or called
directly by a script (`scripts/seed_jlpt_shared_decks.py`,
`scripts/check_shared_deck_storage_regression.py`, etc. all call it
directly).

`get_app_env()` was added to `backend/app/settings.py` alongside the
existing `get_database_url()`, following the same
`os.getenv(...).strip()` pattern.

## Allow / block matrix

| `APP_ENV` | `DATABASE_URL` | Result |
| --- | --- | --- |
| `production` | Neon (`*.neon.tech`) | **Allowed** |
| (unset/blank) | Neon | **Blocked** |
| `development` | Neon | **Blocked** |
| `local` | Neon | **Blocked** |
| `test` | Neon | **Blocked** |
| any value, including unset | empty / SQLite (`sqlite:///...`) | **Allowed** |

The error, if blocked:

```
Refusing to start: DATABASE_URL points to Neon (host matches neon.tech)
while APP_ENV is not production. Use a local SQLite DATABASE_URL for
development.
```

It never includes the actual `DATABASE_URL` value (which may carry
credentials) -- only that its host matched the Neon marker.

## Local development

```env
APP_ENV=development
DATABASE_URL=sqlite:///./vocab_dev.db
```

Leaving `APP_ENV` unset works identically (it normalizes to
`"development"`); setting it explicitly is just clearer. See
`backend/.env.example`.

## Production (Render)

Render's environment variables must include both:

```env
APP_ENV=production
DATABASE_URL=postgresql+psycopg://...
```

See [production-deployment.md](../production-deployment.md) for the full
required-variables list. Missing `APP_ENV=production` on Render with a Neon
`DATABASE_URL` configured will make the backend refuse to start -- this is
intentional; set the variable rather than working around the guard.

## Testing

`backend/scripts/check_database_safety_guard.py` exercises
`assert_safe_database_url()` directly, as pure string-in/string-out checks
-- it never opens a real database connection (SQLite or PostgreSQL) and
uses a fake, non-functional Neon-shaped hostname
(`postgresql://user:pass@ep-test.neon.tech/db`), never a real credential.
Run it locally under a session-scoped SQLite `DATABASE_URL` override (the
guard itself doesn't need one to run, since it takes its inputs as plain
strings, but this repo's convention is to never leave a session pointed at
Neon regardless):

```
cd backend
.venv\Scripts\Activate.ps1
$env:APP_ENV="development"
$env:DATABASE_URL="sqlite:///./vocab_guard_scratch.db"
python scripts/check_database_safety_guard.py
```
