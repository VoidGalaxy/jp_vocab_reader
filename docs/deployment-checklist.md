# Deployment Checklist

This project is not wired to a specific deployment platform yet. Use this checklist before choosing production hosting.

## 1. Local Development

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

Default URLs:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://localhost:3000`

## 2. Required Environment Variables

Backend:

- `DATABASE_URL`: Optional in local development. Defaults to the existing SQLite DB. Example: `sqlite:///./vocab.db`.
- `JWT_SECRET_KEY`: Required in production. Do not use the development fallback in production.
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`: Optional. Defaults to `10080` minutes, or 7 days.
- `OPENAI_API_KEY`: Required only for AI context explanations. Without it, the API returns a clear error for AI explanation requests.
- `CORS_ALLOW_ORIGINS`: Comma-separated frontend origins. Example: `http://localhost:3000,http://127.0.0.1:3000`.

Frontend:

- `NEXT_PUBLIC_API_BASE_URL`: Backend API URL. Example: `http://127.0.0.1:8000`.

## 3. Before Deployment

- Set `JWT_SECRET_KEY` to a strong production-only secret.
- Add the real frontend domain to `CORS_ALLOW_ORIGINS`.
- Set `NEXT_PUBLIC_API_BASE_URL` to the real backend API URL.
- Decide whether `OPENAI_API_KEY` should be enabled for the deployment.
- Confirm `DATABASE_URL`. SQLite is still the only runtime-supported database in this stage.
- Run backend validation: `python -m compileall app`.
- Run frontend validation: `npm run build`.
- Smoke test `/health`, `/me`, login/register, analysis, vocab save, shared deck list/detail/import, and AI explanation behavior.

## 4. Security Notes

- Never commit `.env` files.
- Never use the development JWT secret in production.
- Back up the SQLite DB before deployment, migration, or host changes.
- Limit CORS origins to real frontend domains in production.
- Keep `OPENAI_API_KEY` and future database credentials in the host secret manager.

## 5. Deployment Candidates

- Frontend: Vercel, Netlify, or another static/Next.js-capable host.
- Backend: Render, Fly.io, Railway, VPS, or another Python/FastAPI-capable host.
- DB: SQLite is acceptable only for a single-server early deployment. A service deployment should move to PostgreSQL after the planned migration work.

## 6. Remaining TODO

- Actual PostgreSQL migration.
- Rate limiting.
- AI usage limits and cost controls.
- Email verification and password reset.
- Shared deck reporting and moderation review.
