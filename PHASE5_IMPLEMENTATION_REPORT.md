# TinkerLab Phase 5 Implementation Report

## Status

Phase 5 is **implementation-complete and code-verified within the artifact sandbox**. The mandatory clean-machine checks that require Docker, live PostgreSQL, Pint/Ruff/Mypy or installed frontend dependencies remain **UNVERIFIED** because those capabilities are not present here. They are not reported as PASS.

Phase 6 must begin with that stabilization gate before adding any physics execution.

---

## Phase-4 stabilization

The unmodified Phase-4 backend baseline was executed before Phase-5 work: **82/82 tests passed**.

Verified Phase-4 scientific regressions remain intact:

- `PropertyPrediction` remains separate from `MaterialPropertyObservation` — PASS.
- prediction execution creates no observation rows — PASS.
- OOD/incomplete prediction outcomes remain numberless — PASS.
- known applicable evidence remains preferred — PASS.
- prediction comparison fallback remains explicit — PASS.
- interval-crossing hard constraints remain `UNKNOWN` — PASS.
- synthetic demo-model warning remains present — PASS.
- arbitrary pickle/joblib model artifact execution remains rejected — PASS.
- prediction privacy/scope regression tests remain green — PASS.

A browser development-scope defect was fixed: CORS now allows `X-Organisation-ID`. This header is still only a development scoping seam and is **not** authentication.

Unavailable and therefore UNVERIFIED: Docker Compose, live PostgreSQL migration/persistence, Pint-backed production unit runtime, Ruff, Mypy, dependency-resolved frontend tests/typecheck/lint/build and browser smoke testing.

See `docs/PHASE4_STABILIZATION_FOR_PHASE5.md`.

---

## Implemented

Phase 5 adds a bounded, deterministic **Autonomous Virtual Experiment & Multi-Objective Optimization Brain** on top of Phase-3 candidate hypotheses and Phase-4 predictions.

Implemented capabilities:

- project/organisation-scoped virtual experiment campaigns;
- frozen replacement-specification and search-space semantics;
- ordered multi-objective definitions with immutable prediction-model pins;
- explicit hard-constraint evidence/prediction policies;
- zero-persistence campaign preview;
- bounded one-iteration execution and bounded multi-iteration execution;
- Phase-4 batched prediction orchestration;
- three-way robust hard feasibility;
- uncertainty-preserving objective vectors;
- conservative multi-objective decision values;
- deterministic non-dominated sorting and persisted Pareto snapshots;
- transparent parent selection under three policy keys;
- bounded Phase-3-compliant hypothesis mutation;
- deterministic child hypothesis identifiers/fingerprints;
- deduplication, structural pre-screening, Phase-3 lineage and typed change records;
- per-candidate virtual-evaluation audit records;
- explicit optimization decision ledger;
- explicit stop semantics and campaign result checksums;
- hypothesis campaign history;
- reproducibility envelope API;
- Virtual Experiment Lab, campaign preview/run detail, Pareto view and decision ledger;
- deterministic synthetic two-objective generic-polymer demonstration.

No physics, physical laboratory execution, synthesis procedure, patent search or online model learning is implemented.

---

## Campaign architecture

### `VirtualExperimentCampaign`

Freezes:

- organisation/project;
- replacement-specification checksum;
- search-space ID/version/checksum;
- policy key/version;
- random seed;
- iteration/parent/child/campaign budgets;
- configuration checksum;
- lifecycle and final stop/result checksum.

### `CampaignObjective`

Stores ordered property objective, direction (`maximize|minimize|target`), optional target/unit, priority/weight and a pinned immutable Phase-4 `PredictionModelVersion`.

### `CampaignConstraintModelPolicy`

Maps existing project constraints to an explicit value-origin policy (`known_evidence`, model fallback hierarchy) and optional pinned model version. It does not redefine the underlying scientific constraint.

### `CampaignIteration`

Stores immutable iteration input/checksums, Phase-4 prediction-run IDs, counts, Pareto snapshot checksum, selected-parent checksum, child/duplicate counts, decision checksum and stop signal/reason.

### `VirtualCandidateEvaluation`

Stores one auditable evaluation per candidate/iteration:

- robust feasibility;
- hard PASS/FAIL/UNKNOWN counts;
- objective point/conservative vector;
- full intervals;
- objective origins/model/prediction IDs;
- Pareto rank/dominance;
- uncertainty/acquisition components;
- parent-selection/disposition;
- rationale;
- deterministic evaluation checksum.

### `ParetoFrontSnapshot`

Persists ordered front membership and objective-space checksum rather than recalculating historical campaign state against potentially changed code/data.

### `OptimizationDecisionRecord`

Provides typed records for initial evaluation, robust failure, parent selection, mutation generation, duplicate rejection, structural rejection and stop-related decisions.

---

## Optimization policies

All policies are registered reviewed code, not arbitrary user-loaded executables.

### `robust_pareto_v1` v1.0

Hard feasibility:

1. any hard FAIL => `robustly_infeasible`;
2. otherwise any UNKNOWN => `uncertain`;
3. all hard constraints PASS => `robustly_feasible`.

Objective conservative decision value:

- maximize => lower prediction interval bound;
- minimize => upper prediction interval bound;
- target => worst absolute interval distance from target after unit normalization.

Pareto sorting converts maximize objectives to `-conservative_value` and treats all other decision values as minimization components. A dominates B iff all A components are `<=` B and at least one is `<` B.

Parent selection order:

1. robustly feasible before uncertain;
2. lower Pareto rank;
3. higher aggregate normalized uncertainty when exploration is enabled;
4. stable scientific candidate identity.

Robust hard failures are not parents.

### `uncertainty_exploration_v1` v1.0

Uses the same robust feasibility and conservative Pareto vectors. Among non-hard-failed hypothesis candidates, selection prioritizes lower Pareto rank and larger normalized interval widths. The implementation deliberately calls this **uncertainty priority**, not information gain.

Normalized interval component:

`abs(upper - lower) / max(abs(point), 1e-9)`.

### `lexicographic_pareto_baseline_v1` v1.0

Uses the same feasibility and Pareto algorithm but provides a simple deterministic baseline parent order:

feasibility -> Pareto rank -> lexicographic conservative vector -> stable identity.

### Limitations

The non-dominated sort is O(n²). Under the Phase-5 hard pool cap of 200, that is at most 19,900 unordered pair checks and is accepted as a deliberate bounded implementation. Increasing the pool significantly requires algorithm review.

There is no opaque overall AI score.

---

## Uncertainty handling

Prediction point estimates are never used alone for campaign decisions.

Every model-backed objective retains:

- point;
- lower bound;
- upper bound;
- output unit;
- applicability status;
- model version;
- prediction ID;
- conservative value;
- interval width/completeness.

Hard constraints reuse Phase-4 interval-aware semantics. A boundary-crossing interval remains `UNKNOWN`, so the campaign becomes `uncertain` unless another constraint produces a hard FAIL.

Missing/OOD/incomplete objective predictions receive no inferred number and no standard Pareto vector. They are not imputed.

---

## Autonomous mutation

Autonomous Phase-5 mutation operates only on structurally valid **hypothesis parents**.

Supported bounded mutations are derived from the active Phase-3 search space:

- configured component amount +/- explicit step;
- curator-approved component substitution;
- configured process parameter +/- explicit step;
- deterministic balance-component compensation.

For every persisted child:

- Phase-3 structural validation is reused;
- `candidate-v1` canonical fingerprinting is reused;
- project/campaign duplicate fingerprints are rejected/countable;
- child remains `CandidateHypothesis`;
- no canonical `Material` is created;
- no property observation is inherited or created;
- parent lineage is recorded with `CandidateLineageEdge`;
- typed before/after change records are recorded;
- campaign/iteration provenance is linked through decision records.

Campaign-created hypothesis IDs are deterministic from `project_id + scientific fingerprint`, preventing campaign-generated children from destabilizing historical semantic query ordering and strengthening replay determinism.

---

## Scientific integrity

The primary invariant is:

> **VIRTUAL EVALUATION — MODEL-BASED; not a physical experiment or physics simulation.**

The optimizer calls Phase-4 prediction services and consumes persisted `PropertyPrediction` records. It does **not** access demo-model coefficient artifacts directly.

Tests prove:

- virtual campaigns create zero `MaterialPropertyObservation` rows;
- hypotheses remain outside the canonical material graph;
- Phase-4 OOD predictions remain numberless;
- intervals are preserved into Phase-5 evaluation records;
- UNKNOWN is never counted as hard PASS;
- structural validity is never treated as performance validation;
- demo model surfaces remain explicitly synthetic;
- no `validated`, `verified`, `discovered` material status is introduced by campaign state.

---

## Reproducibility

SHA-256 over canonical JSON is used for scientific configuration/result envelopes.

Checksums cover:

- campaign configuration;
- replacement-spec checksum;
- search-space checksum/version;
- objectives and pinned model versions;
- constraint-model policy;
- policy/version;
- seed and budgets;
- iteration input pool;
- Phase-4 prediction result checksums;
- per-candidate feasibility/objective/uncertainty/Pareto state;
- parent-selection state;
- child fingerprints;
- Pareto-front membership/objective vectors;
- stop reason;
- final ordered iteration result.

Deterministic replay tests pass. A meaningful configuration change changes the campaign configuration/result envelope as expected.

Current deterministic synthetic seeded campaign:

- campaign status: `completed`;
- stop reason: `maximum_iterations_reached`;
- configuration checksum: `b9e943c9491eeac7e0ee4a72a2c9c63afce15505cb5f2fc859beabf6cd5c01c3`;
- result checksum: `0c6081241afd927f4a33bfb7cd5a7048949b4998ed68639e09956c759282c961`.

Iteration 1:

- evaluated: 5;
- robust feasible / uncertain / infeasible: 1 / 2 / 2;
- Pareto front: 2;
- selected parents: 2;
- new children: 2;
- duplicates: 1.

Iteration 2:

- evaluated: 4;
- robust feasible / uncertain / infeasible: 0 / 4 / 0;
- Pareto front: 3;
- selected parents: 3;
- new children: 1;
- duplicates: 2;
- stop: `maximum_iterations_reached`.

Running the seed twice leaves a single deterministic campaign and stable material/observation/hypothesis counts.

---

## Database

Forward migration: `0005_virtual_experiment_brain.py` (`0005_phase5`, down-revision `0004_phase4`).

New tables:

- `virtual_experiment_campaigns`;
- `campaign_objectives`;
- `campaign_constraint_model_policies`;
- `campaign_iterations`;
- `virtual_candidate_evaluations`;
- `pareto_front_snapshots`;
- `optimization_decision_records`.

Important constraints/indexes include campaign/iteration uniqueness, one evaluation per candidate/iteration, objective/property uniqueness, constraint-policy uniqueness, project/status lookup and short explicit PostgreSQL-safe evaluation index names.

A PostgreSQL static compilation pass caught an initially overlong index name (>63 characters); the Phase-5 migration was fixed without editing historical migrations.

PostgreSQL-targeted Alembic static generation through `0005`: **1,295 DDL lines, PASS**.

Live PostgreSQL migration execution remains UNVERIFIED in this environment.

---

## Tests

Final backend suite: **108/108 tests passed**.

Final TypeScript/TSX source/config/test parser scan: **41 files, 0 diagnostics**. Full dependency-resolved TypeScript/Next typecheck remains UNVERIFIED because frontend dependencies are unavailable.

Phase-5 coverage includes:

- migration/schema invariants via ORM/static migration checks;
- campaign validation and budget caps;
- cross-tenant private model rejection;
- search-space/spec checksum staleness;
- three-way feasibility;
- exact toy Pareto fronts and directions;
- incomplete objective handling;
- robust and uncertainty-aware policy semantics;
- mutation bounds/locks/substitution/lineage/deduplication;
- zero material/observation pollution;
- Phase-4 prediction reuse;
- deterministic campaign replay;
- seed idempotency;
- zero-persistence preview;
- API scope/privacy;
- evaluation pagination/Pareto/decision/history endpoints;
- multiple explicit stop conditions;
- synthetic-model warning and artifact safety.

Frontend source tests were added for the virtual warning and Pareto component, but dependency-resolved Vitest cannot execute in this sandbox and is therefore UNVERIFIED.

---

## Performance profile

Isolated SQLite query/inference-shape profile; **not a production latency benchmark**.

### 200 candidates, two objective models, one iteration

- preview SELECTs: **49**;
- iteration execution SELECTs: **76**;
- 100-result page SELECTs: **2**;
- prediction inference batches: **2 total**:
  - density × 200 targets;
  - tensile strength × 200 targets;
- candidates evaluated: 200;
- Pareto unordered pair checks: 19,900.

### 20-candidate sanity comparison

- preview SELECTs: 49;
- execution SELECTs: 76;
- result page SELECTs: 2;
- prediction inference batches: 2.

The fixed query counts at 20 vs 200 candidates demonstrate there is no query-per-candidate/property scientific read path. Persistence remains naturally linear in targets/results.

The first profile exposed a query-per-candidate campaign constraint-policy lookup. It was fixed by loading the constraint-policy map once per iteration before final profiling.

See `docs/PHASE5_PERFORMANCE_PROFILE.md`.

---

## Privacy / security

- Campaigns/iterations/evaluations/decisions require organisation/project scope.
- Objective and constraint model versions must be public/global or owned by the campaign organisation.
- Cross-tenant private model references are rejected/tested.
- Candidate pools cannot intentionally pull another tenant's private candidates/materials.
- Hypothesis campaign history is scope-protected.
- Raw formulations/features/model artifacts are not emitted by campaign logs.
- Scientific checksums are one-way SHA-256 digests; they do not replace encryption/access control.
- Phase 5 performs no global model training from customer campaign data.
- `X-Organisation-ID` remains a development-only scoping seam, not production authentication/authorization.

---

## Known limitations

1. Both seeded prediction models are transparent **synthetic software-validation fixtures**, not scientifically validated material models.
2. Phase-5 virtual evaluations are model-backed only; there is no DFT/MD/CALPHAD/FEA or other physics validation.
3. There is no physical lab validation or experimental feedback.
4. O(n²) Pareto sorting is intentionally bounded to <=200 evaluated candidates.
5. Campaigns are synchronous/local and capped; no distributed optimizer/HPC scheduler exists.
6. The current uncertainty-exploration policy is a transparent heuristic, not formal expected information gain.
7. Search is local to explicit Phase-3 mutation dimensions and cannot claim global optimality.
8. `X-Organisation-ID` is not production security.
9. Full Docker/PostgreSQL/Pint/frontend quality gates could not run in this sandbox.

---

## Deferred to Phase 6+

Phase 6:

- Physics & Simulation OS;
- simulation routing;
- reproducible solver/provider workflows;
- simulation jobs/artifacts/results;
- scientifically appropriate ML-force-field/DFT/MD/CALPHAD adapter boundaries;
- explicit simulation-vs-prediction-vs-evidence origin handling.

Later phases remain responsible for industrial viability, novelty/IP intelligence, physical laboratory closed loop and enterprise hardening.

Not implemented here: DFT, Quantum ESPRESSO, LAMMPS/MD, CALPHAD, ML force fields, finite-element physics, HPC scheduling, lab automation, synthesis protocols, patent search, supplier/economic/manufacturing scoring, experimental model retraining, reinforcement learning or LLM chemistry invention.

---

## Run commands

### Clean Docker machine

```bash
cp .env.example .env
docker compose up --build
```

### API

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

### Web

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

## Phase-5 verification checklist

| Check | Status | Notes |
|---|---|---|
| Clean Docker Compose boot | UNVERIFIED | Docker unavailable in artifact sandbox. |
| Live PostgreSQL migrations through 0005 | UNVERIFIED | No live PostgreSQL server. Static PostgreSQL DDL generation passes. |
| Phase-4 data migration integrity on live PG | UNVERIFIED | Requires live disposable DB. |
| Seed twice/idempotency | PASS | Deterministic SQLite fixture/test. |
| All backend tests | PASS | 108/108. |
| Ruff | UNVERIFIED | Ruff unavailable. |
| Mypy | UNVERIFIED | Mypy unavailable. |
| Pint runtime | UNVERIFIED | Pint unavailable in artifact sandbox. |
| Frontend tests | UNVERIFIED | `node_modules`/Vitest unavailable. Source tests added. |
| Full TypeScript typecheck | UNVERIFIED | Dependency-resolved Next types unavailable. |
| ESLint | UNVERIFIED | Frontend dependencies unavailable. |
| Next production build | UNVERIFIED | Frontend dependencies unavailable. |
| Browser smoke | UNVERIFIED | Production app stack unavailable. |
| Create/validate campaign | PASS | Service/API tests. |
| Preview zero persistence | PASS | API/service tests. |
| One bounded iteration | PASS | Tests and seed campaign. |
| Phase-4 prediction runs reused | PASS | Regression tests. |
| Uncertainty retained | PASS | Evaluation records/tests. |
| Interval-crossing => uncertain | PASS | Feasibility tests. |
| Pareto correctness | PASS | Toy-front tests. |
| Parent rationale/components | PASS | Evaluation/decision tests. |
| Child Phase-3 lineage/change records | PASS | Tests. |
| No canonical Material created | PASS | Scientific-integrity tests. |
| No observations created/inherited | PASS | Scientific-integrity tests. |
| Multi-iteration campaign | PASS | Seed + tests. |
| Deterministic replay/checksums | PASS | Tests. |
| Meaningful config changes checksum | PASS | Tests. |
| >=3 stop conditions tested | PASS | Budget/no-child/no-prediction plus iteration limit. |
| Campaign privacy scope | PASS | API/cross-tenant tests. |
| 200-candidate/2-objective profile | PASS | 49/76/2 SELECTs; exactly 2 inference batches. |
| Browser console/responsiveness | UNVERIFIED | Browser stack unavailable. |
| Debug/cache cleanup | PASS at packaging | Rechecked immediately before ZIP. |
| Documentation truthfulness | PASS | Phase-5 docs/report updated. |

Because several environment-dependent acceptance items remain UNVERIFIED, this artifact is **not claimed to have passed full clean-machine production acceptance**. It is ready for that stabilization gate and subsequent Phase-6 work.
