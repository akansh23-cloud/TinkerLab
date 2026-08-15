# Phase 12.2.1 — Single-project fetch and cold-start fix

## Root causes confirmed on the deployed environment

The Phase 12.2 frontend was deployed successfully, but its current Vercel build contained only the
Next.js application. The separate legacy API deployment answered its old health endpoint but did not
contain Phase 12+ endpoints such as `/external-data/providers`.

Database inspection also found two unusable states: one production Neon project had no public tables,
and the older staging database had the Phase-11 schema but zero organisations/materials/providers.
Therefore fixing only an API key could never populate the dashboard.

## Fixes

- One Vercel project/domain using Services: Next.js + FastAPI.
- Same-origin `/api`; stale legacy API URLs are ignored in production.
- Pre-migration-safe `/deployment/status` endpoint.
- Idempotent `/deployment/bootstrap` endpoint.
- Bootstrap upgrades schema, creates the demo scope, and installs the reference library.
- Postgres advisory lock prevents concurrent bootstrap races.
- Reference-library install no longer depends on a tenant row because the library itself is public.
- Network errors identify the actual API path instead of only saying `Failed to fetch`.
- Python 3.12 incompatibility in the optional deterministic seed helper was corrected.
- Materials Project remains server-side and governed; the bootstrap does not automatically spend
  provider quota or turn external records into evidence without an explicit ingestion request.

## Required deployment change

The Vercel project Root Directory must be repository root and Framework Preset must be Services.
Keeping Root Directory at `apps/web` will continue to deploy only the frontend and `/api/*` will not exist.
