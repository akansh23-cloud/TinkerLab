# TinkerLab — Phase 2 Implementation Report

**Phase:** Materials Knowledge & Evidence Graph  
**Date:** 2026-08-12  
**Repository:** `tinkerlab-phase2`

## Executive result

Phase 2 extends the Phase-1 Material Replacement Project OS into an evidence-first materials knowledge layer without implementing candidate generation, ML property prediction, physics simulation, autonomous optimisation, patent search, or laboratory automation.

The central scientific behaviour is now:

> A material property is not a naked number. It is an observation tied to evidence, source provenance, conditions, status, uncertainty/confidence, and an explicit selection policy. Missing or inapplicable evidence remains `UNKNOWN`.

### Verified in this execution environment

- **34/34 backend tests PASS.**
- Python application and test source compiles successfully.
- **19/19 TypeScript/TSX source files** pass TypeScript syntax transpilation with **0 syntax diagnostics**.
- PostgreSQL-targeted Alembic offline generation successfully emits the full `0001 -> 0002` migration chain (**480 lines of PostgreSQL DDL**).
- Deterministic seed reruns without changing core entity counts.
- Canonical source-record checksums remain stable across JSON key ordering.
- Seeded project comparison selects condition-applicable evidence rather than the latest database row.
- Seeded comparison query profile is **23 SQL statements** for 3 candidates in the SQLite profiling harness (measured ~28.8 ms in this sandbox; timing is environment-specific).
- Private imported material data does not appear in unscoped material discovery.
- Organisation-owned project metadata is not exposed through a public material when no organisation scope is provided.

### Explicitly unverified here

The sandbox does not provide Docker or installable frontend/scientific dependencies, so the following are **UNVERIFIED**, not PASS:

- live Docker Compose startup;
- live PostgreSQL migration/upgrade against a running PostgreSQL server;
- Pint-backed runtime rather than the local compatibility fallback;
- Ruff;
- Mypy;
- dependency-resolved frontend Vitest suite;
- full TypeScript typecheck with React/Next dependency types installed;
- ESLint;
- production `next build`;
- browser smoke/responsive inspection.

These are mandatory stabilization gates at the start of Phase 3.

---

# Implemented

## 1. Materials Knowledge Graph

Phase 2 adds first-class entities for:

- material identifiers and aliases;
- organisation/private ownership seams;
- structured material components/composition;
- process/material state;
- source providers;
- immutable-ish imported source records with checksums;
- citations;
- expanded evidence metadata;
- typed observation condition sets;
- richer property observations;
- import batches;
- property-specific conflict policies.

The Phase-1 material/project/candidate model remains intact.

## 2. Material identity resolution

A conservative deterministic identity resolver was implemented.

Supported signals include:

- exact trusted identifier match;
- normalized canonical-name match;
- exact structured-composition signature comparison.

It deliberately does **not** use an LLM, embeddings, or fuzzy autonomous merging. Ambiguous/probable matches remain reviewable rather than being silently merged.

## 3. Structured composition and process state

Materials can now carry:

- named components;
- amount/min/max;
- unit/basis;
- role;
- sequence;
- redaction flag;
- structured metadata;
- process/state records.

Redacted composition is represented explicitly rather than replaced with fabricated values.

## 4. Typed scientific conditions

Observations may carry reusable condition sets including common fields such as:

- temperature;
- pressure;
- frequency;
- humidity;
- material/specimen state;
- additional structured metadata.

Condition units are validated.

## 5. Evidence and provenance

Evidence is now linked to provider/source-record/citation concepts and supports:

- evidence type;
- evidence status;
- source quality;
- evidence date;
- curator notes;
- visibility/organisation scope;
- source record;
- parent evidence relationship.

Source records retain:

- provider;
- external record identifier;
- raw checksum;
- normalized checksum;
- parser version;
- source status;
- scoped visibility;
- original structured payload in the database.

The public/source-record API schema intentionally does **not** expose raw imported payloads.

## 6. Observation selection engine

Phase-1's implicit single/latest-observation assumption was replaced with an explicit selection service.

Selection behaviour:

1. excludes superseded/retracted observation/evidence;
2. applies evidence-type policy if configured;
3. evaluates requested test conditions;
4. rejects explicitly incompatible conditions;
5. ranks exact condition matches above missing-condition fallbacks;
6. honours explicit curator preference;
7. retains alternatives and exclusions;
8. provides a human-readable rationale;
9. keeps deterministic ties visible instead of treating them as scientific consensus.

The project replacement comparison now uses this engine.

## 7. Scientific conflict detection

Conflict detection is property-policy driven rather than using one global percentage rule.

Policies implemented:

- relative tolerance;
- absolute tolerance;
- uncertainty-overlap;
- informational/no automatic conflict decision.

Conflicting evidence is preserved. Curator preference changes the selected display observation but does not delete competing evidence.

## 8. Ingestion layer

A controlled local import provider was implemented with JSON and CSV support.

Features include:

- size limits;
- deterministic canonical parsing/checksums;
- dry-run preview;
- validation errors/warnings;
- explicit commit;
- transaction rollback on failure;
- import-batch tracking;
- source-record creation;
- conservative identity resolution;
- idempotent replay detection;
- organisation/private scoping;
- structured composition/process/evidence/observation ingestion.

No arbitrary code/formula execution or filesystem path execution is performed by imported content.

## 9. Provider contracts

A provider registry and `MaterialDataProvider` contract now define a seam for future external databases.

Only a local import provider is implemented in Phase 2.

A live Materials Project adapter was deliberately **not** fabricated because internet/API integration could not be safely verified in this sandbox.

## 10. API expansion

Phase 2 adds or expands endpoints for:

- material explorer;
- Material Passport v2;
- identifiers;
- structured composition;
- process state;
- observations;
- evidence;
- source providers;
- source records;
- citations;
- conservative identity resolution;
- evidence summary;
- conflict inspection;
- condition-aware selection preview;
- observation details;
- observation provenance;
- curator preference;
- import dry run;
- import commit/status;
- project candidate comparison with selection provenance.

## 11. Product UI

The frontend now contains:

### Materials Explorer

Search/filter material records while exposing:

- family;
- identifiers;
- evidence coverage;
- observation count;
- conflict indicators.

### Material Passport v2

Includes:

- identity and aliases;
- structured composition;
- redaction state;
- process state;
- selected observation summaries;
- all observations;
- conditions;
- evidence;
- conflict review;
- curator-preference controls.

### Observation / Provenance Inspector

Displays the provenance chain:

`provider/source record -> evidence -> observation`

including checksums and relevant status metadata.

### Import Center

Supports:

- JSON/CSV selection;
- local file content loading;
- organisation scope;
- dry-run validation;
- errors/warnings;
- commit only after a valid preview;
- idempotency result display.

### Replacement comparison upgrades

The candidate comparison shows:

- selected observation;
- applicability;
- number of alternatives;
- selection rationale;
- conflict state;
- evidence posture.

---

# Important scientific demonstrations in the deterministic seed

## Condition-aware selection

Candidate A contains two tensile-strength observations:

- **74 MPa at 23 °C**;
- **61 MPa at 80 °C**.

The seeded replacement project's tensile requirement includes a 23 °C context. The selection engine chooses the 74 MPa ambient record and excludes the 80 °C record as condition-inapplicable.

This demonstrates that TinkerLab no longer evaluates a candidate using whichever observation happened to be inserted most recently.

## Preserved conflict

Candidate B contains two density observations under equivalent conditions:

- 1380 kg/m³;
- 1490 kg/m³.

The density property's seeded relative conflict tolerance is 3%, so a scientific conflict is surfaced. Both observations remain in the graph; a curator preference identifies the currently preferred display value without erasing the competing record.

## Superseded evidence

Candidate A contains an old superseded cost observation and a current active cost observation. Superseded evidence is excluded from current selection while remaining available for provenance/history.

## Unknown remains unknown

Candidate C intentionally lacks some property evidence. Those requirements remain `UNKNOWN`; the system does not convert absence into failure and does not generate replacement values.

---

# Database / migration

Phase 2 adds a forward migration:

`0002_materials_knowledge_graph.py`

The Phase-1 `0001_phase1_foundation.py` migration is preserved rather than rewritten.

Important changes include:

- material ownership/visibility fields;
- material identifiers;
- material components;
- material process state;
- source providers;
- citations;
- source records;
- evidence expansion;
- observation condition sets;
- observation provenance/status/uncertainty expansion;
- import batches;
- conflict policy fields;
- scoped identifier uniqueness;
- removal of the Phase-1 one-observation-per-evidence/property restriction so multiple condition-specific observations are representable.

PostgreSQL offline Alembic generation was verified with an explicit PostgreSQL URL and emits 480 lines for the complete migration chain.

A live PostgreSQL server upgrade is not verified in this sandbox.

---

# Tests

## Backend

**34/34 PASS** using the isolated SQLite test database.

Coverage includes Phase-1 regression plus:

- identifier normalization/resolution;
- structured composition validation;
- redaction representation;
- condition-unit validation;
- exact condition selection;
- inapplicable-condition exclusion;
- superseded evidence exclusion;
- missing evidence -> UNKNOWN;
- property-specific conflict detection;
- curator preference;
- JSON import preview;
- import commit;
- import idempotency;
- private import scope;
- source-record provenance;
- project comparison selected-observation provenance;
- public/private material discovery boundaries;
- organisation-owned project metadata scope;
- seed idempotency;
- canonical source-record checksum reproducibility.

## Frontend

Frontend component tests were added for the Materials Explorer and Import Center, and the existing Phase-1 UI test remains.

They are **UNVERIFIED in this sandbox** because `node_modules` is absent and package download is unavailable.

As a bounded source-level check, all **19 TypeScript/TSX files** pass `typescript.transpileModule` syntax parsing with **0 syntax diagnostics** using the globally installed TypeScript compiler.

This is not equivalent to a dependency-resolved typecheck or Next production build.

---

# Performance / query posture

The project comparison path now builds a shared selection context for baseline/candidate observations instead of issuing a property query for every constraint.

A seeded SQLite profiling run for the 3-candidate comparison produced:

- HTTP 200;
- **23 SQL statements**;
- approximately **28.8 ms** in this sandbox.

The timing is not a production benchmark. The relevant architectural result is that the query pattern is bounded around material/project/evidence loading rather than growing as a query per candidate-property pair.

---

# Security and privacy posture

Implemented Phase-2 controls include:

- structured input validation;
- import payload size limit;
- no executable formula/code ingestion;
- no arbitrary imported filesystem execution;
- raw source payload omitted from normal API response models;
- public/private material visibility;
- organisation-scoped private imports;
- scoped private identifiers/evidence;
- private evidence/identifiers cannot be attached to a public material through the Phase-2 API;
- import-batch access requires organisation scope;
- organisation-owned replacement-project metadata is not returned through a public material without explicit organisation scope.

### Important limitation

`X-Organisation-ID` is a Phase-2 scoping seam, **not authentication**. A production identity/authorization layer is deferred. Do not expose the current demo deployment to untrusted multi-tenant traffic as if it were production-secure.

---

# Architecture decisions

## Kept deliberately

- modular monolith;
- FastAPI + SQLAlchemy + PostgreSQL target;
- Next.js/TypeScript frontend;
- deterministic scientific services;
- explicit typed JSON contracts;
- adapter/provider seams;
- evidence/provenance before AI;
- forward-only phase migration.

## Deliberately not introduced

- microservice sprawl;
- Kubernetes;
- vector database;
- LLM material invention;
- MatterGen;
- ML property prediction;
- ML force fields;
- DFT;
- MD;
- CALPHAD;
- Bayesian optimisation;
- evolutionary search;
- active learning;
- patent APIs/search;
- supplier integrations;
- autonomous laboratories;
- robotics;
- production SSO;
- billing.

---

# Known limitations / required stabilization before Phase 3

The following are not hidden and must be resolved on a networked/Docker-capable machine before Phase-3 functionality is accepted:

1. Run Docker Compose with real PostgreSQL.
2. Apply `0001 -> 0002` on PostgreSQL from a clean database.
3. Also test upgrading an actual Phase-1 PostgreSQL snapshot to Phase 2.
4. Install Python dependencies including Pint.
5. Prove Pint-backed unit conversion and remove any need to exercise the offline compatibility fallback in production.
6. Run Ruff.
7. Run Mypy.
8. Install frontend dependencies.
9. Run Vitest.
10. Run full `tsc --noEmit`.
11. Run ESLint.
12. Run `next build`.
13. Perform browser smoke and responsive checks.
14. Exercise import and material-passport workflows against PostgreSQL.
15. Verify migration rollback strategy in a disposable environment.

Any P0/P1 defect found in those checks must be fixed before Phase 3 candidate generation is implemented.

---

# Run commands

## Docker target

```bash
cp .env.example .env
docker compose up --build
```

Then, depending on the Compose service naming:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m app.db.seed
```

## Backend local

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

Tests/checks:

```bash
pytest -q
ruff check .
mypy app
```

## Frontend

```bash
cd apps/web
npm install
npm run test
npm run typecheck
npm run lint
npm run build
npm run dev
```

---

# Phase-2 acceptance checklist

| Criterion | Status | Evidence |
|---|---|---|
| Phase-1 backend regression | PASS | included in 34/34 suite |
| Materials knowledge graph | PASS | entities/routes/tests |
| Structured identifiers | PASS | model + resolver + tests |
| Structured composition | PASS | model/API/import/tests |
| Explicit redaction | PASS | model/seed/tests/UI |
| Process/material state | PASS | model/API/seed/UI |
| Typed conditions | PASS | model/validation/selection/tests |
| Evidence provenance | PASS | provider/source/evidence/observation chain |
| Source-record checksums | PASS | deterministic tests |
| Conservative identity resolution | PASS | deterministic resolver/tests |
| Condition-aware observation selection | PASS | service/seed/tests |
| Superseded/retracted exclusion | PASS | selection tests |
| Scientific conflict preservation | PASS | policy engine/tests/UI |
| Curator preference | PASS | API/tests/UI |
| Missing data -> UNKNOWN | PASS | regression + Phase2 tests |
| JSON ingestion | PASS | preview/commit/tests |
| CSV ingestion | PASS at parser/source level | example fixture + parser; full browser upload unverified |
| Import dry-run | PASS | API/tests/UI source |
| Import idempotency | PASS | test |
| Private import scope | PASS at application seam | tests; not production auth |
| Material Explorer | IMPLEMENTED | full browser runtime unverified |
| Material Passport v2 | IMPLEMENTED | API covered; browser runtime unverified |
| Provenance Inspector | IMPLEMENTED | API covered; browser runtime unverified |
| Import Center | IMPLEMENTED | source syntax verified; browser runtime unverified |
| PostgreSQL migration DDL generation | PASS | 480-line PG offline output |
| Live PostgreSQL upgrade | UNVERIFIED | no PostgreSQL/Docker runtime |
| Docker Compose | UNVERIFIED | Docker unavailable |
| Pint runtime | UNVERIFIED | Pint unavailable in sandbox |
| Ruff | UNVERIFIED | executable unavailable |
| Mypy | UNVERIFIED | executable unavailable |
| Frontend dependency-resolved tests | UNVERIFIED | node_modules unavailable |
| Full frontend typecheck | UNVERIFIED | dependency types unavailable |
| ESLint | UNVERIFIED | dependency unavailable |
| Next production build | UNVERIFIED | Next dependency unavailable |
| Browser/responsive smoke | UNVERIFIED | dependency/runtime unavailable |

---

# Deferred to Phase 3+

Phase 2 intentionally stops before material generation.

The next phase should introduce an **explainable, deterministic Candidate & Replacement Generation Engine** with lineage and bounded search spaces. It must not fabricate property observations for generated hypotheses and must not introduce ML/physics prematurely.

See `PHASE3_IMPLEMENTATION_PROMPT.md` for the exact next implementation contract.
