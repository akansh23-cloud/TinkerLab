# TinkerLab Phase 1 — Implementation Report

## Implemented

- Modular-monolith FastAPI scientific backend and separate Next.js engineering UI.
- Organisation and minimal demo user context.
- Material identity/passport model with controlled material family.
- Property-definition registry with canonical units and comparator policies.
- Typed scalar observations (`numeric` and `boolean`).
- First-class evidence records with evidence type, source, method, confidence and metadata.
- Observation-level conditions, confidence and uncertainty.
- Replacement projects with multiple replacement reasons.
- Hard and soft constraints, including numeric, `between`, and boolean forms.
- Optimisation objectives separate from constraints.
- Deterministic Replacement Specification compiler and semantic SHA-256 checksum.
- Manual/seed candidate attachment only; no generation engine.
- Unit-aware candidate evaluation with transparent PASS / FAIL / UNKNOWN.
- Baseline deltas and percentage deltas when mathematically defined.
- Candidate evidence-completeness metric; no opaque replacement score.
- Material passport UI, dashboard, eight-step replacement wizard, project workspace, requirements, candidates, comparison, evidence and structured specification views.
- Deterministic synthetic polymer demonstration dataset, explicitly marked `seed_demo` and non-scientific.
- REST/OpenAPI endpoints, request IDs, JSON structured logs, basic CORS/security headers.
- SQLAlchemy models and PostgreSQL-oriented Alembic migration.
- Docker Compose for PostgreSQL + API + web.
- Future protocol boundaries without fake implementations.

## Architecture

The build is deliberately a modular monolith. Scientific state and evidence are authoritative in PostgreSQL through SQLAlchemy. The deterministic compiler/evaluator are pure service-layer components. The Next.js client consumes explicit REST contracts. No asynchronous compute infrastructure or later-phase scientific machinery has been introduced.

The units layer uses Pint when installed. A narrow, reviewed deterministic fallback registry exists only so the source bundle can be audited/tested in offline environments where packages cannot be fetched; it does not claim universal units coverage.

## Database

Core tables:

- `organisations`
- `users`
- `materials`
- `material_property_definitions`
- `evidence`
- `material_property_observations`
- `replacement_projects`
- `constraints`
- `objectives`
- `candidates`

Important relationships and cascade decisions are documented in `docs/ERD.md` and `docs/DOMAIN_MODEL.md`.

## Tests — executed in this build environment

Backend command:

```bash
cd apps/api && pytest
```

Result:

```text
16 passed in 0.34s
```

Coverage includes:

- pressure conversion
- density conversion
- affine Celsius/Kelvin conversion
- incompatible-unit rejection
- property/unit dimension rejection
- invalid between constraints
- invalid boolean constraint shapes
- deterministic specification checksum
- hard/soft/objective compilation
- candidate PASS/FAIL/UNKNOWN
- missing-data UNKNOWN semantics
- boolean PASS/FAIL from typed observations
- health/request ID
- seeded project/specification/comparison API workflow
- invalid-unit API rejection
- create project → add constraint → add candidate → compile → compare integration flow

Python bytecode/syntax verification:

```text
python -m compileall -q app tests  -> PASS
```

Frontend source syntax verification used the globally available TypeScript compiler API to transpile every `.ts`/`.tsx` source file without dependency resolution:

```text
TS/TSX syntax transpile: PASS
```

## Verification environment limitation

This execution environment has no package-network access and no Docker daemon. Therefore these commands could not truthfully be marked executed:

- `docker compose up --build`
- PostgreSQL Alembic migration against a live PostgreSQL server
- `npm install`
- `npm run build`
- `npm run lint`
- `npm run typecheck` with Next/React dependency type resolution
- Ruff/Mypy after installing declared developer dependencies
- Pint-backed runtime path (the tested offline path uses the explicit fallback registry)

The repository contains all corresponding configuration and dependencies so CI/a normal networked machine can execute them. No unexecuted check is marked PASS.

## Known limitations

- Phase 1 supports scalar numeric and scalar boolean observations. Rich curves/tensors/distributions are intentionally future work.
- Property applicability is represented but not yet enforced as a material-family policy on every write.
- Candidate comparison uses the most recent observation for a property; future phases need condition-aware evidence selection and conflict resolution.
- Currency conversion is intentionally not attempted. `USD/kg` is a controlled unit, not a live FX system.
- Demo identity is local-only and explicitly not production authentication.
- Activity UI exposes the lack of an enterprise audit-event stream rather than simulating one.
- Material usage endpoint currently reports baseline usage; full candidate/reference reverse indexing can be expanded later.
- No scoring model combines scientific dimensions into a single opaque number.

## Deferred to Phase 2+

- external materials databases
- literature ingestion
- richer evidence graph / citation entities
- candidate generation
- property ML prediction
- DFT / MD / CALPHAD
- HPC
- Bayesian optimisation
- evolutionary search
- active learning
- patent/novelty APIs
- supplier integrations
- autonomous laboratories / robotics
- model training/registry
- vector database
- production SSO
- payments
- Kubernetes

## Run commands

Clean Docker path:

```bash
cp .env.example .env
docker compose up --build
```

Backend tests:

```bash
cd apps/api
pytest
```

Local API with PostgreSQL:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://tinkerlab:tinkerlab@localhost:5432/tinkerlab'
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd apps/web
npm install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

## Phase 1 verification checklist

| Criterion | Status | Evidence / note |
|---|---|---|
| Application runs locally | PARTIAL | FastAPI exercised through TestClient; full Docker stack unverified in offline/no-Docker sandbox |
| Database persists projects | PASS (test DB) | API integration test commits and re-reads project data |
| Project wizard works | SOURCE VERIFIED | TS syntax passes; browser runtime requires npm install |
| Materials represented | PASS | model/API/tests |
| Properties unit-aware | PASS | conversion + incompatibility tests |
| Evidence first-class | PASS | schema, relations, passport/API |
| Hard/soft constraints work | PASS | compiler/evaluator tests |
| Boolean constraints work | PASS | typed boolean PASS/FAIL test |
| Objectives work | PASS | compiler + API model |
| Specification deterministic | PASS | checksum test |
| Candidates attach | PASS | API integration test |
| Candidate comparison works | PASS | API + evaluator tests |
| Missing data produces UNKNOWN | PASS | dedicated test |
| Evidence visible in UI | SOURCE VERIFIED | passport/comparison implementation; browser runtime unverified |
| Seed demo works | PASS (test DB) | deterministic seed exercised by test suite |
| APIs documented | PASS | FastAPI OpenAPI enabled; docs source present |
| PostgreSQL migration works | UNVERIFIED | migration checked in; no PostgreSQL/Docker runtime available |
| Backend tests pass | PASS | 16/16 |
| Frontend dependency-aware tests/build pass | UNVERIFIED | no npm network/dependency install available |
| Documentation matches implementation | PASS (source audit) | architecture/domain/evidence/spec/scope/future/ERD docs written |
