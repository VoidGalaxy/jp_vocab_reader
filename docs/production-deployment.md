# Production Deployment

This guide captures the production deployment shape that has been tested successfully: Vercel frontend, Render backend, and Neon PostgreSQL. SQLite fallback remains available for local development only.

## 1. Recommended Structure

- Frontend: Vercel.
- Backend: Render.
- Database: Neon PostgreSQL.

Deploy frontend and backend as separate services. The frontend calls the backend through `NEXT_PUBLIC_API_BASE_URL`.

Production deployment is considered successful when:

- Vercel serves the frontend over HTTPS.
- Render serves the FastAPI backend over HTTPS and `GET /health` succeeds.
- The backend uses a Neon PostgreSQL `DATABASE_URL` configured in the host environment.
- The Vercel frontend can register/login, analyze text, save vocabulary, and read saved data through the Render backend.
- CORS allows the exact Vercel frontend origin.

## Post-Deploy Quick Check

After each production deploy, run the fastest read-only checks before deeper browser verification:

1. Confirm `GET /health` succeeds.
2. From `backend`, run `python scripts/run_shared_deck_health_checks.py <backend-base-url>` to verify the public shared-deck list and local JLPT package safety without writes.
3. In the frontend, verify login/logout, one analyze/save flow, and one study session.

See [deployment-checklist.md](deployment-checklist.md) for platform-neutral checks and [Section 10](#10-smoke-test-after-deployment) for the fuller smoke list.

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

For Vercel, set the environment variable in the project settings before building. The value must be the HTTPS Render backend URL. Do not use `http://` in production; a Vercel HTTPS page calling an HTTP API can fail with `Failed to fetch` or a browser mixed content block.

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
APP_ENV=production
DATABASE_URL=
JWT_SECRET_KEY=change-me-in-production
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=10080
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.2
CORS_ORIGINS=http://localhost:3000,https://your-frontend-domain.example
JMDICT_FULL_JSON_URL=
EN_KO_DICTIONARY_URL=
```

`APP_ENV=production` is required on Render whenever `DATABASE_URL` points at Neon/PostgreSQL -- the backend refuses to start against a Neon `DATABASE_URL` unless `APP_ENV` is exactly `production` (see [docs/operations/database-safety.md](operations/database-safety.md)). This exists specifically to stop a local dev server from accidentally initializing/writing to the shared Neon database.

Frontend:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.example
```

Never commit real `.env` files. Use the host's secret/environment variable UI. Do not write real `DATABASE_URL`, `JWT_SECRET_KEY`, API keys, Render URLs, Vercel URLs, or Neon connection strings into this document.

`JMDICT_FULL_JSON_URL` is optional. Set it only when the Render backend should download `jmdict_full.json` at startup. Plain `.json` and `.json.zip` / `.zip` URLs are supported. Do not put `sha256:...` hash text in this variable, and do not commit the downloaded file.

`EN_KO_DICTIONARY_URL` is optional. Set it only when the Render backend should download the Kaikki/Wiktionary-derived `en_ko_full.json` at startup. Plain `.json`, gzipped `.json.gz`/`.gz`, and zipped `.json.zip`/`.zip` URLs are supported. `EN_KO_DICTIONARY_PATH` optionally overrides the local storage path. If the URL is missing or the download/validation fails, the backend keeps running with the committed `en_ko_sample.json` fallback.

## 5. CORS

`CORS_ORIGINS` is a comma-separated list of allowed frontend origins.

Local default origins are allowed when the variable is empty:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

Production example:

```env
CORS_ORIGINS=https://your-frontend-domain.example
```

For the tested Vercel + Render deployment, `CORS_ORIGINS` must include the Vercel origin with `https://`. If the backend still uses the compatibility alias, put the same HTTPS Vercel origin in `CORS_ALLOW_ORIGINS`.

If the browser shows a CORS error, first verify:

- Backend `CORS_ORIGINS` includes the exact frontend origin, including scheme.
- Frontend `NEXT_PUBLIC_API_BASE_URL` points to the backend URL, not the frontend URL.
- The backend service was restarted after changing environment variables.

`CORS_ALLOW_ORIGINS` is still accepted as a backward-compatible alias, but new deployments should use `CORS_ORIGINS`.

## 6. Backend Start Command

This is the same production start command introduced in [Section 3](#3-backend-deployment), restated here as a standalone reference. Run from the `backend` directory:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Some hosts expose the port as a different variable. If so, adapt only the port expression and keep `app.main:app`.

## 7. Frontend API URL

This is the same `NEXT_PUBLIC_API_BASE_URL` set in [Section 2](#2-frontend-deployment); this section adds the local-fallback behavior to be aware of. The frontend reads:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-backend-domain.example
```

In production this must be the HTTPS Render backend URL. If the variable is missing, local development falls back to `http://127.0.0.1:8000`. Do not rely on that fallback in production.

## 8. Database Notes

SQLite remains the fallback when `DATABASE_URL` is empty. It is for local development only. The tested production deployment uses Neon PostgreSQL.

- Redeploys can replace or delete the local database file on hosts with ephemeral filesystems.
- Multiple backend instances may not share the same database file.
- Backups are manual unless the host provides persistent disk backup.
- File permissions and working directory changes can point the app at a different SQLite file.

For production, set a Neon PostgreSQL `DATABASE_URL`, run the connection check, and confirm backup/restore before launch. The current SQLite database contains only test data, so production starts from a clean PostgreSQL database.

## 9. PostgreSQL Migration

Before switching production traffic to PostgreSQL:

- Prepare an empty target database.
- Set `DATABASE_URL` through the host secret/environment UI.
- Run `python scripts/check_postgres_connection.py`.
- Keep `python scripts/migrate_sqlite_to_postgres.py` available, but run it only if existing `backend/vocab.db` data must be preserved. For the current deployment, skip it because the SQLite data is test data only.
- Re-check insert ID returns, duplicate saves, search filters, date-string due filters, and shared-deck publish/import.
- Add database backups and restore testing.

See [postgres-data-migration.md](postgres-data-migration.md) for the full smoke-test and migration checklist. Do not move production traffic before data migration and managed database smoke tests are complete.

## 10. Smoke Test After Deployment

Backend:

- `GET /health`
- Confirm `/health` shows `dictionary.source` as `full` when full dictionary delivery is enabled.
- Confirm `/health` shows `dictionary.en_ko.source` as `full` when `EN_KO_DICTIONARY_URL` is configured, or `sample`/`fallback` otherwise.
- Confirm analyzed results still show a Korean fallback meaning (not a raw English gloss) in the UI when `meaning_ko` is empty.
- If dictionary delivery fails or analysis returns `500`, check Render logs for download, ZIP/GZIP extraction, or JSON validation errors.
- `GET /me`
- `POST /auth/register`
- `POST /auth/login`
- `GET /decks`

Frontend:

- Login/register/logout
- Analyze Japanese text
- Confirm analyzed tokens can receive `meaning_ko` or `dictionary_gloss` from the active local dictionary.
- Classify and save words
- Confirm saved words in the vocab tab
- Start a study session from a deck
- Open the shared tab and view shared deck detail
- Confirm CSV download and JSON deck package export/import remain available

Read-only health checks (safe to re-run anytime, no writes):

- Run after each production deploy that touches shared decks, JLPT packages,
  shared-deck import/review logic, or deployment configuration. It is also
  safe to run as a lightweight recurring check:

```bash
cd backend
python scripts/run_shared_deck_health_checks.py https://<backend-base-url>
```

- `backend/scripts/check_production_shared_decks.py <backend base URL>` calls
  a single anonymous `GET /shared-decks` against the deployed backend to
  confirm the public shared-deck list still matches the last verified state.
- `backend/scripts/check_jlpt_package_safety.py` checks the local approved
  JLPT package JSON files only, no network calls.

See "Phase 16: read-only post-transition health checks" in
[beta-release-checklist.md](beta-release-checklist.md) for the full
procedure and what each script verifies.

## 11. Troubleshooting Order

1. Check backend logs for import, dependency, or SQLite file errors.
2. Check `GET /health`.
3. Check `JWT_SECRET_KEY` is set in backend production.
4. Check `CORS_ORIGINS` and `NEXT_PUBLIC_API_BASE_URL` together.
5. Check that `NEXT_PUBLIC_API_BASE_URL` uses `https://` and points to the Render backend URL.
6. Check that `CORS_ORIGINS` or `CORS_ALLOW_ORIGINS` includes the Vercel frontend origin with `https://` (see [Section 5](#5-cors) for the full CORS troubleshooting list).
7. Check whether the SQLite file path is accidentally being used instead of Neon PostgreSQL.
8. Check frontend build-time environment variables.
9. Check browser network responses for `401`, `404`, `500`, CORS failures, `Failed to fetch`, or mixed content.
10. Check OpenAI settings only if assistant endpoints are being used.
