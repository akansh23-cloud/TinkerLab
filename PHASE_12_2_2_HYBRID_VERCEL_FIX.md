# Phase 12.2.2 — Hybrid Vercel API Fix

## Root cause verified on the live deployment

The live `tinker-lab` build emitted only Node.js functions. `/api/*` therefore fell through to Next.js and returned 404. The previous Services-based `vercel.json` was not being activated by the current Vercel project configuration.

## Fix

This release uses Vercel's documented hybrid layout inside the project's existing Root Directory (`apps/web`):

- Next.js remains in `apps/web/app/`.
- `apps/web/api/index.py` is the Python catch-all for `/api/*`.
- The FastAPI code and Alembic migrations required by that function are packaged under `apps/web/python_backend/`.
- `apps/web/pyproject.toml` declares Python runtime dependencies.
- `apps/web/vercel.json` configures the Python function duration/bundle.

No Vercel Services framework preset is required for this release.

## Vercel project settings

Keep **Root Directory = `apps/web`**.
Use normal Next.js/automatic framework detection. Do not select Services.

Required environment variables:

- `DATABASE_URL`
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`
- `MATERIALS_PROJECT_API_KEY`
- `MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org`
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`

Remove stale `NEXT_PUBLIC_API_BASE_URL`, `API_BASE_URL`, and `mp_api` unless deliberately using an external backend.

After redeploy, verify:

- `/api/health`
- `/api/deployment/status`
- `/api/external-data/providers`

The Vercel deployment metadata/build output should contain a Python function in addition to Node.js functions.
