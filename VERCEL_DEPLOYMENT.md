# TinkerLab Phase 12.2 — Vercel deployment

Use **two Vercel projects from the same GitHub repository**.

## Web project (`cloud14/tinker-lab`)

- Git repository: `akansh23-cloud/TinkerLab`
- Production branch: `develop` (current project connection)
- Root Directory: `apps/web`
- Framework: Next.js
- Install command: `npm ci`
- Build command: `npm run build`
- Node.js: 22.x is preferred to match the repository Dockerfile

Environment variables:

- `NEXT_PUBLIC_API_BASE_URL=<the deployed Phase 12.2 API origin>`
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`

## API project (Phase 12.2 deployment)

- Git repository: `akansh23-cloud/TinkerLab`
- Root Directory: `apps/api`
- Framework: FastAPI
- Python: 3.12 (`.python-version` is included)
- Vercel entrypoint: `apps/api/app.py`

Set all server-side variables from `.env.vercel.example` **except** the `NEXT_PUBLIC_*` variables.

## Database bootstrap

The production database must be migrated through Alembic revision `0013_phase11` before using data-backed routes.
Run once from `apps/api` in an environment that has the production `DATABASE_URL`:

```bash
alembic upgrade head
python -m app.db.seed
```

The seed is deterministic/idempotent and supplies the demo organisation referenced by
`NEXT_PUBLIC_ORGANISATION_ID`.

## Important

Do not set the Vercel web project Root Directory to the repository root. The repository is a
monorepo and there is no root Next.js application. A repo-root deployment can build as an
"Other" project and still return `404`, which is what the previous deployment did.

Do not expose `DATABASE_URL`, `MATERIALS_PROJECT_API_KEY`, or `EPA_COMPTOX_API_KEY` as
`NEXT_PUBLIC_*` variables.


## Materials Project API

Set `MATERIALS_PROJECT_API_KEY` on the **API Vercel project only**. The connector uses the Materials Project summary endpoint through the server and stores the Materials Project material id, dataset snapshot metadata, source record and computed-property provenance. Keep `MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org` unless you intentionally use a compatible endpoint.

After deployment, `GET /external-data/providers` must report `materials_project.configured: true` before running an ingestion. Use `POST /external-data/ingest` with `provider: "materials_project"`, a bounded query, and your organisation header.
