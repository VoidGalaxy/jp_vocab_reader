# Production Deployment

This guide prepares the app for a real hosting platform without changing the current API surface. SQLite fallback remains available for local development, but PostgreSQL is recommended before real public multi-user traffic.

## 1. Recommended Structure

- Frontend: Vercel or another Next.js-capable host.
- Backend: Render, Railway, Fly.io, VPS, or another Python/FastAPI host.
- Database: use PostgreSQL for production. Keep SQLite only for local development or temporary single-instance testing.

Deploy frontend and backend as separate services. The frontend calls the backend through `NEXT_PUBLIC_API_BASE_URL`.

## 2. Frontend Deployment

Use `frontend` as the project root.

Build command:

```bash
npm run build
```

Start command, if the host needs one:

```bash
npm run start
```

Set:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.example
```

For Vercel-style hosting, set the environment variable in the project settings before building.

## 3. Backend Deployment

Use `backend` as the service root.

Install command:

```bash
pip install -r requirements.txt
```

Production start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Local development start command remains:

```bash
uvicorn app.main:app --reload
```

`backend/Procfile` contains the same production command for Procfile-compatible hosts.

## 4. Required Environment Variables

Backend:

```env
DATABASE_URL=
JWT_SECRET_KEY=change-me-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.2
CORS_ORIGINS=http://localhost:3000,https://your-frontend-domain.example
```

Frontend:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.example
```

Never commit real `.env` files. Use the host's secret/environment variable UI.

## 5. CORS

`CORS_ORIGINS` is a comma-separated list of allowed frontend origins.

Local default origins are allowed when the variable is empty:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

Production example:

```env
CORS_ORIGINS=https://your-frontend-domain.example
```

If the browser shows a CORS error, first verify:

- Backend `CORS_ORIGINS` includes the exact frontend origin, including scheme.
- Frontend `NEXT_PUBLIC_API_BASE_URL` points to the backend URL, not the frontend URL.
- The backend service was restarted after changing environment variables.

`CORS_ALLOW_ORIGINS` is still accepted as a backward-compatible alias, but new deployments should use `CORS_ORIGINS`.

## 6. Backend Start Command

Run from the `backend` directory:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Some hosts expose the port as a different variable. If so, adapt only the port expression and keep `app.main:app`.

## 7. Frontend API URL

The frontend reads:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.example
```

If the variable is missing, local development falls back to `http://127.0.0.1:8000`. Do not rely on that fallback in production.

## 8. Database Notes

SQLite remains the fallback when `DATABASE_URL` is empty. It is acceptable for local development and very small single-instance testing, but it has production risks:

- Redeploys can replace or delete the local database file on hosts with ephemeral filesystems.
- Multiple backend instances may not share the same database file.
- Backups are manual unless the host provides persistent disk backup.
- File permissions and working directory changes can point the app at a different SQLite file.

For any real public service, set a PostgreSQL `DATABASE_URL`, run the connection check, migrate existing SQLite data intentionally, and confirm backup/restore before launch.

## 9. PostgreSQL Migration

Before switching production traffic to PostgreSQL:

- Prepare an empty target database.
- Set `DATABASE_URL` through the host secret/environment UI.
- Run `python scripts/check_postgres_connection.py`.
- Run `python scripts/migrate_sqlite_to_postgres.py` from `backend` if existing `backend/vocab.db` data must be copied.
- Re-check insert ID returns, duplicate saves, search filters, date-string due filters, and shared-deck publish/import.
- Add database backups and restore testing.

See [postgres-data-migration.md](postgres-data-migration.md) for the full smoke-test and migration checklist. Do not move production traffic before data migration and managed database smoke tests are complete.

## 10. Smoke Test After Deployment

Backend:

- `GET /health`
- `GET /me`
- `POST /auth/register`
- `POST /auth/login`
- `GET /decks`

Frontend:

- Login/register/logout
- Analyze Japanese text
- Classify and save words
- Confirm saved words in the vocab tab
- Start a study session from a deck
- Open the shared tab and view shared deck detail
- Confirm CSV download and JSON deck package export/import remain available

## 11. Troubleshooting Order

1. Check backend logs for import, dependency, or SQLite file errors.
2. Check `GET /health`.
3. Check `JWT_SECRET_KEY` is set in backend production.
4. Check `CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` together.
5. Check whether the SQLite file path is persistent and writable.
6. Check frontend build-time environment variables.
7. Check browser network responses for `401`, `404`, `500`, or CORS failures.
8. Check OpenAI settings only if assistant endpoints are being used.
