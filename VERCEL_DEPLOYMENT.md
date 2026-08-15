# TinkerLab Phase 12.2.1 — Vercel single-project deployment

Phase 12.2.1 deploys the Next.js UI and FastAPI service from **one Vercel project** and one domain.
The browser calls `/api/...` on the same origin. This removes the stale Phase-9 API URL/CORS failure
mode that previously appeared as `Failed to fetch`.

## One-time Vercel project settings

Use the existing **tinker-lab** project.

1. **Root Directory:** repository root (`./`, not `apps/web`).
2. **Framework Preset:** `Services`.
3. Deploy the `develop` branch after these settings are saved.

The repository-root `vercel.json` defines two services:

- `web` → `apps/web`
- `api` → `apps/api`, entrypoint `service:app`

Traffic routing:

- `/api/*` → FastAPI service
- everything else → Next.js

The FastAPI wrapper mounts the existing application at `/api`, so the public health check is:

`GET /api/health`

## Environment variables — same `tinker-lab` project

Required:

- `DATABASE_URL`
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`

For Materials Project:

- `MATERIALS_PROJECT_API_KEY`
- `MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org`

Optional:

- `EPA_COMPTOX_API_KEY`
- `LOG_LEVEL=INFO`
- `ENVIRONMENT=production`

### Remove stale split-deployment variables

For this single-project deployment, remove or ignore:

- `NEXT_PUBLIC_API_BASE_URL`
- `API_BASE_URL`
- duplicate `mp_api`

Phase 12.2.1 ignores `NEXT_PUBLIC_API_BASE_URL` in production unless
`NEXT_PUBLIC_API_MODE=external` is explicitly set. This prevents an old Phase-9 backend URL from
silently hijacking a newer frontend.

## First deployment / empty database

The dashboard first calls:

`GET /api/deployment/status`

If the database is empty or incomplete it makes one idempotent call to:

`POST /api/deployment/bootstrap`

Bootstrap performs only deployment prerequisites:

1. Alembic upgrade to the repository head.
2. Create the deterministic demo organisation/user if missing.
3. Install the public, screening-only reference library if missing.

It does **not** create fake replacement projects or silently ingest external providers.
Postgres bootstrap is serialized with an advisory lock so concurrent first loads do not race.

After bootstrap the dashboard should show 30+ reference materials even before any external ingestion.

## Verification

Check these URLs on the deployed `tinker-lab` domain:

- `/api/health`
- `/api/deployment/status`
- `/api/external-data/providers`

Expected provider response: `materials_project.configured` is `true` when
`MATERIALS_PROJECT_API_KEY` is present in the Vercel environment used for the deployment.

Then open **External data sources** and run the default Materials Project SiC query. Provider data is
never fetched merely because an API key exists; ingestion remains an explicit governed action.
