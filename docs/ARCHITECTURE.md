# Phase 2 Architecture

Phase 2 remains a **modular monolith**. Scientific data quality is increased without adding queues, microservice sprawl or compute infrastructure.

```text
Next.js scientific workspace
        |
FastAPI REST / OpenAPI
        |
+-- replacement project/specification services
+-- observation selection service
+-- conflict detection service
+-- material identity service
+-- local ingestion/provider registry
+-- unit/condition validation
        |
SQLAlchemy domain graph + Alembic
        |
PostgreSQL target
```

## Core flow

```text
raw/imported record
      ↓
SourceProvider + SourceRecord
      ↓
normalization / conservative identity resolution
      ↓
Material + identifiers + composition + process state
      ↓
Evidence
      ↓
MaterialPropertyObservation + ConditionSet
      ↓
ObservationSelectionService
      ↓
project comparison / Material Passport
```

`SourceRecord` is immutable provenance identity. Normalized scientific entities may evolve, while the exact imported snapshot remains recoverable by checksum and parser version.

## Data-access posture

Project comparison builds one selection context for the baseline and all candidates, preloading property definitions and observations before evaluation. Passport selection similarly uses a batch selection context. This avoids a query-per-property selection pattern.

## Deliberately absent

No MatterGen, ML property predictors, DFT, MD, CALPHAD, HPC scheduler, Bayesian/evolutionary optimizer, patent search, robotics, production SSO, billing, Kubernetes or vector database.

## Phase 3 — Candidate generation boundary

Phase 3 adds a logical `generation` module inside the modular monolith. It consumes the replacement specification and Phase-2 knowledge/evidence graph but writes generated proposals to `CandidateHypothesis`, not `Material`.

The synchronous Phase-3 pipeline is:

```text
ReplacementProject + compiled specification
          +
versioned CandidateSearchSpace
          +
approved rules / deterministic strategy
          ↓
search-space validation + cardinality preview
          ↓
bounded proposal generation/retrieval
          ↓
canonical fingerprint + deduplication
          ↓
structural pre-screen
          ↓
CandidateHypothesis + lineage/change records
          ↓
GenerationRunResult ordered audit trail
```

There is intentionally no distributed queue or scientific-compute service in this phase. Later property prediction and simulation modules must consume candidate IDs through explicit contracts rather than embedding their logic inside generation.

## Phase 4 — Prediction boundary

Phase 4 adds a logical `prediction` module to the modular monolith. It consumes canonical materials/hypotheses but does not mutate evidence observations.

```text
Material / CandidateHypothesis
        ↓
deterministic FeatureSnapshot
        ↓
ApplicabilityDomain check
        ↓
approved immutable ModelVersion
        ↓
bounded predict_batch
        ↓
PropertyPrediction + uncertainty
        ↓
explicit comparison policy
```

`MaterialPropertyObservation` and `PropertyPrediction` are separate tables and separate scientific origins. The default comparison path remains evidence-only unless a specific prediction run is selected.

## Phase 5 — Virtual experiment / optimization boundary

Phase 5 adds a logical `experiments` module. It orchestrates Phase-4 prediction services and Phase-3 mutation services; it does not duplicate model inference or candidate fingerprinting.

```text
ReplacementProject + frozen specification
        +
CandidateSearchSpace vN/checksum
        +
Campaign objectives + pinned ModelVersions
        +
Policy vN + seed + budgets
        ↓
zero-persistence preview
        ↓
ordered candidate pool
        ↓
Phase-4 PredictionRun(s), batched per objective/constraint need
        ↓
interval-aware hard feasibility
        ↓
conservative objective vectors
        ↓
non-dominated sorting / Pareto snapshots
        ↓
explicit parent-selection policy
        ↓
Phase-3 bounded mutation / fingerprint / dedupe / lineage
        ↓
next iteration or explicit stop reason
```

`VirtualCandidateEvaluation` is neither evidence nor simulation. The optimization service never accesses model coefficients directly; it consumes persisted Phase-4 predictions. Mutation children remain `CandidateHypothesis` records and create neither canonical materials nor observations.

The Phase-5 data-access path preloads campaign constraint policy once per iteration and uses bounded prediction batches. The 20- and 200-candidate profiles have identical SELECT counts for preview/execution, demonstrating no candidate/property read N+1.


## Phase 6 — Simulation Operating System layer

```
app/services/representations.py      deterministic validators + content checksums
app/services/simulation_runtime.py   bounded local execution (allowlist, no shell, path containment)
app/services/simulation_adapters.py  fixture + LAMMPS/QE boundaries + interface-only seams
app/services/simulation.py           registry, router, snapshots, workflows, results, selection
app/api/routes/simulation.py         API surface (no field accepts a command, path or image)
```

Dependency direction: routes → orchestration → adapters → runtime. The runtime knows nothing about the
ORM; adapters know nothing about HTTP. `ComputeBackend` is the seam where a queue or HPC backend would
be added without changing callers — Phase 6 ships only `local_bounded_v1`.


## Phase 7 — Industrial Viability layer

```
app/services/industrial.py       evidence access, comparability, conflict detection,
                                 constraint evaluation, dimension roll-up, assessment snapshots
app/api/routes/industrial.py     routes, evidence, compatibility, constraints, maturity, assessment
app/schemas/industrial.py        request validation that rejects incomparable claims at the door
```

The industrial engine **reads** scientific conclusions (Phase-5 evaluations, Phase-6 simulation
counts) and never recomputes or overrides them. It forms no scientific opinion of its own.
