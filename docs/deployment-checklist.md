# Deployment Checklist

This project is still in the pre-deployment stage. Do not connect production services or switch databases during this check.

## 1. Local Run

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Default local URLs:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:3000`

## 2. Environment Variables

Backend:

- `DATABASE_URL`: Optional for local development. Empty value uses `backend/vocab.db`. Current runtime support is SQLite only. Example: `sqlite:///./vocab.db`.
- `JWT_SECRET_KEY`: Required for production. Never use the development fallback outside local work.
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Optional. Defaults to `10080`.
- `OPENAI_API_KEY`: Optional. Keep it secret. The current main UI does not expose per-word AI explanation.
- `OPENAI_MODEL`: Optional. Defaults to the backend setting.
- `CORS_ORIGINS`: Comma-separated frontend origins. Example: `http://localhost:3000,http://127.0.0.1:3000`.
- `CORS_ALLOW_ORIGINS`: Backward-compatible alias for `CORS_ORIGINS`.

Frontend:

- `NEXT_PUBLIC_API_BASE_URL`: Backend API URL. Local default is `http://127.0.0.1:8000`.

Do not commit `.env`, `.env.local`, `backend/.env`, or `frontend/.env.local`.

## 3. Backend Pre-Deployment Checks

- Confirm `backend/requirements.txt` is installed in the target Python environment.
- Confirm `JWT_SECRET_KEY` is set to a strong production-only value.
- Confirm CORS origins include the deployed frontend origin only.
- Confirm `DATABASE_URL` points to a SQLite path that the backend process can read and write.
- Run `python -m compileall app` from `backend`.
- Start locally with `uvicorn app.main:app --reload` and confirm startup initializes the SQLite schema without deleting data.
- Confirm `GET /health` returns `status: ok`.

## 4. Frontend Pre-Deployment Checks

- Set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL.
- Run `npm run build` from `frontend`.
- Confirm the browser can call the backend without CORS errors.
- Confirm the UI does not expose a per-word AI explanation generation button.

## 5. CORS

Local development defaults allow:

- `http://localhost:3000`
- `http://127.0.0.1:3000`

For deployment, set `CORS_ORIGINS` to exact frontend origins, separated by commas. Avoid `*` with credentialed requests. `CORS_ALLOW_ORIGINS` is still supported for older local env files, but new deployments should use `CORS_ORIGINS`.

## 6. Database

The app currently uses SQLite through `sqlite3`.

- Empty `DATABASE_URL` uses `backend/vocab.db`.
- `sqlite:///./vocab.db` uses a relative SQLite file path from the backend process working directory.
- `sqlite:///C:/path/to/vocab.db` can point to an explicit Windows path.
- Existing data must be backed up before host moves, migrations, or manual DB changes.

## 7. SQLite Notes

- SQLite is acceptable for local development and single-process early testing.
- Multi-instance deployments can corrupt expectations because each instance may have a different local file.
- File permissions and persistent disk behavior matter. Ephemeral containers can lose `vocab.db`.
- Back up `backend/vocab.db` before deployment tests that write data.

## 8. PostgreSQL TODO

Do not set `DATABASE_URL=postgresql://...` yet. PostgreSQL support is intentionally not active.

Before switching:

- Introduce SQLAlchemy models while preserving current behavior.
- Keep SQLite passing through the new DB layer first.
- Add Alembic migrations after model behavior is stable.
- Plan existing SQLite data migration.
- Re-check repository queries that depend on SQLite syntax, row behavior, `?` placeholders, and datetime string comparisons.

## 9. OpenAI API Key

- `OPENAI_API_KEY` is optional for the current user-facing flow.
- Keep the key in the deployment secret manager, not in git.
- If assistant features are exposed later, add usage limits and cost monitoring first.
- Missing `OPENAI_API_KEY` should not prevent normal login, analysis, vocab, study, shared deck, or backup flows.

## 10. Smoke Test Flow

Backend:

```bash
cd backend
python -m compileall app
uvicorn app.main:app --reload
```

Then check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/me
curl http://127.0.0.1:8000/decks
```

Frontend:

```bash
cd frontend
npm run build
npm run dev
```

Browser checks:

- Login/register/logout
- Analyze Japanese text
- Classify and save words
- Vocab list, search, filter, sort
- Start study from a deck and complete a session
- Shared deck list/detail/import
- CSV download and JSON deck package export/import
- Mobile-width tab/card/button layout
