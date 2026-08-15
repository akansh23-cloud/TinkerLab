# Phase 12.6 — Full TinkerLab Command-Center Visual System

This release extends the Phase 12.5 Mission Control / Virtual Lab redesign across the primary product navigation without changing the scientific decision backend.

## New first-class workspaces

- `/materials` — Materials Intelligence card browser with evidence/conflict visibility.
- `/requirements` — blocking gates, soft requirements, and optimization objectives separated visually.
- `/evidence` — experimental measurements, sample provenance, external snapshots, and origin separation.
- `/decisions` — ADVANCE / REJECT / HOLD decision story, requirement outcomes, risk/readiness, and next actions.
- `/reports` — technical dossier versions, checksum/evidence references, methodology manifest, and audit timeline.
- `/settings` — Vercel/FastAPI/Neon health, environment-presence diagnostics, scientific policy, and provider configuration state.

The global sidebar now routes to those workspaces directly. Specialist pages such as `/validation`, `/reasoning`, `/data-sources`, `/studies/new`, and project-specific labs remain available as deeper tools.

## Flagship workflow

Mission Control → Requirements → Materials → Virtual Lab → Evidence → Decisions → Reports.

The visual system is intentionally decision-oriented: each screen should answer what is known, what is blocking, what is unresolved, and what happens next.

## Scientific boundaries preserved

- No generative AI is required or used in the decision loop.
- PASS / FAIL / UNKNOWN remain deterministic evidence states.
- ADVANCE / REJECT / HOLD remain deterministic programme outcomes.
- Experimental, simulation, prediction, and provider origins remain separated.
- Missing evidence remains UNKNOWN rather than being treated as a failure.
- Technical dossiers are structured, versioned, checksummed, and evidence-linked.

## Deployment impact

No new database migration, service, or API key is required by Phase 12.6.

Continue using the existing production variables, including `DATABASE_URL`, `NEXT_PUBLIC_ORGANISATION_ID`, `ENVIRONMENT`, and `LOG_LEVEL`. `MATERIALS_PROJECT_API_KEY` remains optional for real external data ingestion.

## Validation completed

- 92 application TS/TSX files syntax-transpiled: 0 syntax errors.
- Targeted semantic TypeScript check for the new workspaces and shared API types: passed with local framework stubs.
- `app/globals.css` parsed successfully with PostCSS.
- Backend code and database schema were not modified in this release.

A complete `next build` could not be executed in the isolated workspace because npm registry access was unavailable, so the Vercel build remains the final framework/dependency validation step.
