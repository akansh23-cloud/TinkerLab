# TinkerLab Phase 12.2.3 — Vercel single-project deployment

Deploy the Next.js UI and FastAPI backend from one Vercel project and one domain.

## Project settings

- Existing project: `tinker-lab`
- Root Directory: `apps/web`
- Framework Preset: `Next.js`
- Build Command: default
- Output Directory: default / override OFF
- Install Command: default

`apps/web/vercel.json` packages Python functions and rewrites all public `/api/*` requests to the hybrid FastAPI gateway.

## Environment variables

Required:

- `DATABASE_URL`
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`
- `MATERIALS_PROJECT_API_KEY`
- `MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org`
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`

Phase 12.2.3 accepts generic `postgresql://` / `postgres://` URLs and normalizes them to SQLAlchemy's psycopg 3 dialect.

Do not set `NEXT_PUBLIC_API_BASE_URL` or `API_BASE_URL` for the same-origin deployment.

## Verify

- `GET /api/health`
- `GET /api/deployment/status`
- `GET /api/external-data/providers`

A successful Vercel build should emit both Node.js and Python runtimes.
