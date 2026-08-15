# Phase 12.2.3 — Vercel API Runtime + Wildcard Routing Fix

## Live deployment findings

Phase 12.2.2 successfully produced both runtimes on Vercel (Python + Node.js), but two runtime issues remained:

1. `GET /api/health` was handled by Next.js and returned 404 because `api/index.py` is a Python function route, not an automatic `/api/*` catch-all.
2. Invoking the Python function failed when Vercel supplied a generic `postgresql://` database URL. SQLAlchemy selected the psycopg2 dialect while this repository intentionally ships psycopg 3, producing `ModuleNotFoundError: No module named 'psycopg2'`.

## Fix

- `apps/web/vercel.json` now rewrites `/api` and `/api/:path*` to the Python gateway.
- The gateway preserves the requested API sub-path in a transport-only query parameter, normalizes the ASGI path, strips that internal parameter, and delegates to the canonical FastAPI app.
- Database initialization now normalizes generic `postgres://` and `postgresql://` URLs to `postgresql+psycopg://`. Explicit SQLAlchemy dialect URLs are left unchanged.
- The canonical API and the mirrored Vercel backend contain the same database fix.
- The stale frontend error copy referring to the old repository-root Services deployment has been removed.

## Vercel project settings

Keep:

- Root Directory: `apps/web`
- Framework Preset: `Next.js`
- Build Command: default
- Output Directory: default (override OFF)
- Install Command: default

Required environment variables:

- `DATABASE_URL` — either `postgresql://...` or `postgresql+psycopg://...` is accepted by this release.
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`
- `MATERIALS_PROJECT_API_KEY`
- `MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org`
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`

Remove stale split-deployment variables unless deliberately using external API mode:

- `NEXT_PUBLIC_API_BASE_URL`
- `API_BASE_URL`
- duplicate `mp_api`

## Verification after redeploy

1. `/api/health` → JSON with `status: ok` and `phase: 12.2.3`.
2. `/api/deployment/status` → deployment/database readiness JSON.
3. `/api/external-data/providers` → provider configuration JSON.
4. Vercel deployment metadata should show both Python and Node.js runtimes.
