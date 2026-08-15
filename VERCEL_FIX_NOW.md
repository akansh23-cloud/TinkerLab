# TinkerLab — Vercel Fix (Phase 12.2.1)

The old `apps/web`-only configuration is the reason the UI could render while every Phase-12 API call failed.
Do **not** deploy the web and API as two unrelated production versions for the current `tinker-lab` setup.

Use the existing `cloud14/tinker-lab` project:

1. Settings → Build and Deployment.
2. Set **Root Directory** to the repository root (`./` / blank), not `apps/web`.
3. Set **Framework Preset** to **Services** in Vercel. The repository-root `vercel.json` then declares:
   - `web`: `apps/web` (Next.js)
   - `api`: `apps/api` (FastAPI)
4. Save and redeploy the latest `develop` commit without the old build cache.
5. Keep `DATABASE_URL`, `MATERIALS_PROJECT_API_KEY`, `MATERIALS_PROJECT_API_BASE_URL`,
   `NEXT_PUBLIC_ORGANISATION_ID` and optional provider keys in this same Vercel project.
6. Remove stale `NEXT_PUBLIC_API_BASE_URL`, `API_BASE_URL` and duplicate `mp_api` unless you deliberately
   opt back into a split deployment.

Verification after deploy:

- `/api/health`
- `/api/deployment/status`
- `/api/external-data/providers`

The dashboard automatically performs the idempotent first-workspace bootstrap when the database/schema/reference
library are missing.

Never commit real database URLs or API keys to GitHub.
