# TinkerLab Phase 3 — Implementation Report

## Status

Phase-3 **Candidate & Replacement Generation Engine implementation is complete in the available sandbox**. All checks that can be executed with installed dependencies have been run. Environment-dependent acceptance checks requiring Docker, live PostgreSQL, Pint, Ruff, Mypy or installed frontend packages are explicitly **UNVERIFIED**.

The implementation stops at Phase 3. No property prediction, physics simulation, advanced optimisation, patent search or lab automation has been added.

---

## Phase-2 stabilization

The Phase-2 repository was used as the base rather than regenerated.

Before Phase-3 work:

- existing backend suite: **34/34 PASS**;
- Phase-2 schemas/evidence/selection/import architecture preserved;
- historical `0001` and `0002` migrations preserved unchanged.

Stabilization/privacy corrections made while integrating Phase 3:

- Phase-3 standalone generation-run endpoints require explicit matching organisation scope;
- hypothesis detail/lineage/status require explicit matching organisation scope;
- substitution-rule state changes require explicit matching organisation scope;
- hypothesis-inclusive project comparison requires matching organisation scope;
- the existing known-material-only comparison remains backward compatible by default;
- project `candidates` relation remains known-material-only for Phase-1/2 response compatibility, while Phase-3 mixed candidate access uses the Candidate Lab/all-candidate path.

See `docs/PHASE2_STABILIZATION_FOR_PHASE3.md`.

---

# Implemented

## 1. Known material vs hypothesis architecture

`Candidate` now supports exactly two scientific target kinds:

- `known_material` -> references `Material` and has no hypothesis;
- `hypothesis` -> references `CandidateHypothesis` and has no material.

A database check constraint enforces exactly one target.

Existing candidate IDs remain compatible and default to `known_material` during the `0003` migration.

Generated hypotheses are **not inserted into the canonical `materials` table**.

## 2. CandidateHypothesis graph

Added:

- `CandidateHypothesis`;
- `CandidateHypothesisComponent`;
- `CandidateHypothesisProcessParameter`;
- `CandidateChangeRecord`;
- `CandidateLineageEdge`.

Each hypothesis stores a concrete proposed representation, strategy/version, deterministic fingerprint, structural validity and status. It does not contain material-performance observations.

## 3. Versioned search spaces

Added:

- `CandidateSearchSpace`;
- `SearchSpaceComponentRule`;
- `SearchSpaceProcessRule`.

Search spaces control:

- family;
- component mutability;
- locked/required/prohibited components;
- min/max/step ranges;
- balance component;
- target total/tolerance;
- bounded process variables;
- candidate budget;
- maximum enumeration;
- version/checksum.

Preview validates scientific/search-space structure before generation and persists nothing.

## 4. Curated substitution rules

Added first-class `SubstitutionRule` with:

- organisation/project scope;
- source/replacement keys;
- allowed amount range;
- reason;
- optional evidence;
- draft/approved/disabled lifecycle;
- version.

Automatic generation uses only `approved` rules.

## 5. Generation strategies

Registered deterministic Phase-3 strategies:

### Known material retrieval v1.0

Retrieves visible existing materials and ranks them transparently using known hard-pass/fail/unknown counts, evidence coverage, conflicts and deterministic identifiers. Missing evidence remains UNKNOWN.

### Curated component substitution v1.0

Uses only approved substitutions and records rule provenance in change records.

### Bounded composition variation v1.0

Uses explicit grids/ranges, deterministic seeded subset selection when truncated, locked-component preservation and deterministic balance-component adjustment.

### Bounded process variation v1.0

Varies only configured process-state variables/ranges. These are data-level proposals, not executable synthesis instructions.

### Manual hypothesis v1.0

Scientist-authored hypotheses receive the same fingerprint, structural, lineage and evidence-posture rules.

## 6. Candidate fingerprinting / deduplication

Fingerprint version: **`candidate-v1`**.

Fingerprints use canonical scientific representation rather than timestamps/database IDs/display labels.

They are:

- deterministic across reruns;
- ordering insensitive where ordering is scientifically irrelevant;
- sensitive to meaningful composition/process changes.

Duplicate fingerprints within a project are detected. Duplicates are counted in generation-run results rather than silently discarded.

## 7. Generation runs / reproducibility

Added:

- `GenerationRun`;
- `GenerationRunResult`.

Every run records:

- replacement specification checksum;
- search-space version/checksum;
- strategy key/version;
- configuration checksum;
- random seed;
- requested budget;
- counts;
- ordered candidate fingerprints;
- result checksum.

Automated reproducibility tests prove identical envelopes reproduce identical ordered fingerprint sequences and result checksums.

## 8. Structural screening

Implemented checks for:

- duplicate component identities;
- negative amounts;
- configured amount bounds;
- required/prohibited components;
- maximum component count;
- total/tolerance;
- allowed process parameters;
- process bounds and units;
- duplicate fingerprint.

Structural PASS is not treated as a performance prediction.

## 9. Hypothesis property semantics

For generated/manual hypotheses:

- no baseline properties are copied;
- no `MaterialPropertyObservation` is created;
- project properties/constraints remain UNKNOWN unless independent future evidence/prediction exists;
- completeness is zero in Phase 3;
- UI/API states `UNKNOWN — NOT YET PREDICTED/TESTED`.

Known materials continue to use the Phase-2 condition-aware evidence/conflict engine.

## 10. Candidate Lab UI

Added project-level Candidate Lab with:

- baseline/specification checksum;
- active search-space version/checksum;
- search-space component/process controls;
- validation;
- deterministic preview;
- strategy/seed/budget controls;
- bounded execution;
- approved substitution-rule provenance;
- known material + hypothesis table;
- hard PASS/FAIL/UNKNOWN counts;
- evidence completeness/conflicts;
- change counts;
- structural status;
- run lineage links.

## 11. Hypothesis detail UI

Added:

- explicit hypothesis warning;
- structured proposed composition;
- proposed process-state parameters;
- baseline diff/change records;
- complete lineage;
- deterministic fingerprint/version;
- property evidence posture;
- project constraints showing UNKNOWN;
- generation-run reproducibility panel.

## 12. Generation-run UI

Added run summary and ordered candidate results with strategy/version, seed, input checksums, counts and result checksum.

## 13. Observability

Generation logging records IDs, strategy/version, checksum prefixes, seed, counts and duration without logging raw formulations.

Invalid generation logs a structured failure code rather than raw private scientific payloads.

---

# Database

Forward migration:

`0003_candidate_generation.py`

It creates:

- `candidate_search_spaces`;
- `search_space_component_rules`;
- `search_space_process_rules`;
- `substitution_rules`;
- `generation_runs`;
- `candidate_hypotheses`;
- candidate hypothesis component/process tables;
- change/lineage tables;
- `generation_run_results`;
- Candidate discriminator/hypothesis reference/check constraint and indexes.

Historical migrations `0001`/`0002` were not changed.

PostgreSQL-dialect Alembic static generation through `0003`: **PASS, 810 lines of DDL**.

A live PostgreSQL migration execution is **UNVERIFIED** in this sandbox.

Downgrade is intentionally lossy for Phase-3 hypothesis candidates and is documented in migration/comments/docs.

---

# Seeded demonstration

The generic engineering-polymer fixture now includes:

- Base Resin A;
- Modifier B;
- Reinforcement C;
- one active versioned search space;
- locked/required/balance behavior;
- bounded Modifier B range;
- one generic bounded process-temperature variable;
- approved generic substitution rules;
- an intentionally duplicate substitution path;
- an intentionally prohibited replacement path for structural rejection;
- a manual hypothesis;
- a deterministic seeded curated-substitution run.

Seeded run result:

- generated: 3;
- accepted: 1;
- rejected: 1;
- duplicate: 1.

All content is synthetic demonstration data and carries no real chemical-performance claim.

---

# Tests

Final backend result:

**56/56 PASS**

Coverage includes prior Phase-1/2 tests plus:

- exactly-one candidate target invariant;
- deterministic fingerprints;
- search-space checksum/version semantics;
- structural prohibition;
- redacted mutation block;
- preview no persistence;
- same-envelope reproducibility;
- hypothesis UNKNOWN behavior;
- zero fabricated observations;
- deterministic evidence-aware known retrieval;
- approved-only substitution;
- organisation scoping;
- candidate pagination;
- seed idempotency;
- search-space API validation/version cloning;
- scoped substitution lifecycle;
- manual-hypothesis API integrity;
- bounded process values;
- locked component preservation;
- formulation total balancing;
- invalid-hypothesis screening status guard;
- budget cap.

Python source and Alembic modules compile successfully.

Frontend source check:

- **26 TypeScript/TSX files**;
- **0 syntax-transpilation diagnostics** using the installed TypeScript compiler.

Dependency-resolved Vitest/full TypeScript/ESLint/Next build are **UNVERIFIED** because frontend packages are unavailable in this sandbox.

---

# Performance/query-shape profile

A separate synthetic SQLite profile created a bounded search space with estimated cardinality 525 and executed exactly **500 generated hypotheses**.

Final SQL statement counts:

| Operation | SQL statements |
|---|---:|
| Candidate Lab page 1 (200, includes known materials) | 15 |
| Candidate Lab page 2 (200 hypotheses) | 13 |
| One hypothesis detail | 4 |
| One hypothesis lineage | 2 |
| Full project comparison including 500 hypotheses | 26 |

This demonstrates bounded/batched query shape rather than a query-per-hypothesis/property loop. These are **not production latency claims**.

---

# Security / privacy

Phase-3 private resources require explicit development organisation scope.

Tests cover:

- unscoped search-space denial;
- unscoped run denial;
- unscoped hypothesis denial;
- unscoped hypothesis-inclusive comparison denial;
- scoped access success.

Known-material retrieval considers public material records plus private records owned by the project's organisation; it does not include another organisation's private materials.

Generation logs do not include raw formulations.

Important limitation: `X-Organisation-ID` is **not authentication**. Production identity/RBAC is deferred.

---

# Known limitations

1. Live Docker Compose execution unavailable in the sandbox.
2. Real PostgreSQL migration/upgrade/downgrade execution unavailable.
3. Pint is not installed here; Pint-backed runtime remains unverified.
4. Ruff/Mypy unavailable.
5. Frontend `node_modules` unavailable, so full frontend test/typecheck/lint/build is unverified.
6. Browser/responsive/console smoke tests are unverified.
7. Search-space generation is synchronous and intentionally bounded; no distributed scheduler exists.
8. Phase-3 generic component identities are not chemically meaningful descriptors.
9. Structural screening checks configured data integrity only, not thermodynamic/mechanical/chemical feasibility.
10. No property prediction exists yet.
11. No physics simulation exists yet.
12. Development organisation scoping is not production auth.

---

# Deferred to Phase 4+

Explicitly deferred:

- model registry;
- material-property prediction;
- applicability-domain assessment;
- calibrated uncertainty;
- feature snapshots/model provenance;
- DFT/MD/CALPHAD/ML force fields;
- Bayesian/evolutionary/active-learning optimisation;
- autonomous experiment selection;
- patents/novelty;
- synthesis/lab automation;
- enterprise authentication/RBAC/billing;
- Kubernetes/microservice decomposition.

The supplied `PHASE4_IMPLEMENTATION_PROMPT.md` introduces only the **Property Prediction & Uncertainty Engine** next.

---

# Run commands

## Clean Docker path

```bash
cp .env.example .env
docker compose up --build
```

## Backend

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://tinkerlab:tinkerlab@localhost:5432/tinkerlab'
alembic upgrade head
python -m app.db.seed
pytest -q
ruff check .
mypy app
uvicorn app.main:app --reload --port 8000
```

## Frontend

```bash
cd apps/web
npm install
npm test
npm run typecheck
npm run lint
npm run build
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3 \
npm run dev
```

---

# Phase-3 verification checklist

| Acceptance item | Status | Evidence / limitation |
|---|---|---|
| Phase-2 regression suite | PASS | 34/34 before Phase-3 changes |
| Phase-3 full backend suite | PASS | 56/56 |
| Forward `0003` code/static PostgreSQL DDL | PASS | 810-line PostgreSQL DDL generated |
| Live real-PostgreSQL `0003` migration | UNVERIFIED | PostgreSQL server unavailable |
| Existing known candidates survive live migration | UNVERIFIED | Requires real migration snapshot; migration is forward-compatible by design/static review |
| Known/material hypothesis model | PASS | DB model + tests |
| Search spaces typed/versioned/checksummed | PASS | API/service/tests |
| Search-space validation | PASS | structured validation/tests |
| Strategy registry/version metadata | PASS | five explicit strategies |
| Known-material retrieval | PASS | deterministic evidence-aware tests |
| Approved curated substitution | PASS | tests + seeded reject/dedup paths |
| Bounded composition variation | PASS | tests |
| Bounded process variation | PASS | tests |
| Manual hypothesis integrity | PASS | tests/API |
| Fingerprint/dedup | PASS | reproducibility/fingerprint tests |
| Lineage/change provenance | PASS | model/API/UI/seed |
| No fabricated hypothesis observations | PASS | explicit observation-count tests |
| Hypothesis properties remain UNKNOWN | PASS | comparison/API tests |
| Generation reproducibility | PASS | same-envelope ordered fingerprint/result checksum test |
| Bounded execution | PASS | budgets + 500-hypothesis profile |
| Privacy development scope | PASS | API privacy regression tests |
| Candidate Lab source implementation | PASS | UI sources added |
| Frontend syntax transpilation | PASS | 26 files, 0 diagnostics |
| Dependency-resolved frontend tests | UNVERIFIED | `node_modules` unavailable |
| Full TypeScript typecheck | UNVERIFIED | dependencies unavailable |
| ESLint | UNVERIFIED | dependencies unavailable |
| Next production build | UNVERIFIED | dependencies unavailable |
| Browser/responsive/console smoke | UNVERIFIED | runnable frontend unavailable |
| Pint-backed runtime | UNVERIFIED | Pint unavailable |
| Ruff | UNVERIFIED | Ruff unavailable |
| Mypy | UNVERIFIED | Mypy unavailable |
| Docker Compose | UNVERIFIED | Docker unavailable |

No unavailable check is reported as PASS.
