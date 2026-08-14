# TinkerLab Phase 4 — Implementation Report

## Phase-3 stabilization

The untouched Phase-3 repository was copied forward and **56/56 existing backend tests passed** before Phase-4 implementation.

Available stabilization checks were executed. Docker, live PostgreSQL, Pint, Ruff, Mypy and frontend `node_modules` are unavailable in this artifact sandbox, so the corresponding normal-machine checks remain **UNVERIFIED**, not PASS. Details are in `docs/PHASE3_STABILIZATION_FOR_PHASE4.md`.

No historical migration was edited. Phase 4 adds only `0004_property_prediction.py`.

---

## Implemented

Phase 4 adds a first-class **Property Prediction & Uncertainty Engine** while retaining the Phase-1/2/3 replacement, evidence and candidate architecture.

Implemented capabilities:

- logical prediction model registry;
- immutable/checksummed model versions;
- safe reviewed JSON artifact format;
- explicit predictor registry/contract;
- structured applicability-domain rules;
- deterministic feature extraction for known materials and candidate hypotheses;
- explicit missing/redacted feature handling;
- typed target conditions and condition-domain checks;
- preview-only applicability assessment with zero prediction persistence;
- bounded synchronous prediction runs, hard maximum 200 targets;
- batched scientific data loading and batched model inference;
- immutable prediction targets/input snapshots;
- first-class model predictions stored separately from evidence observations;
- mandatory uncertainty for numeric prediction;
- deterministic prediction/run checksums;
- explicit prediction history by hypothesis/material;
- explicit prediction-run selection for comparison fallback;
- conservative interval-aware PASS/FAIL/UNKNOWN semantics;
- Prediction Lab UI;
- prediction-run detail UI;
- prediction provenance detail UI;
- candidate-hypothesis prediction history;
- explicit DEMO MODEL warnings across API/UI;
- organisation/project privacy scoping seams.

No physics simulation or autonomous optimisation was introduced.

---

## Model architecture

### `PredictionModel`

Logical registry entry with scope, key, owner/provider, lifecycle status, supported material families and supported property keys.

### `PredictionModelVersion`

Immutable scientific execution version containing:

- predictor key/contract version;
- safe artifact format;
- reviewed artifact payload + SHA-256 checksum;
- feature schema/version/checksum;
- target property;
- canonical output unit;
- uncertainty method;
- applicability policy version;
- training-data descriptor/checksum metadata;
- validation/calibration metrics;
- approval/retirement timestamps;
- immutable metadata.

There is no version-update endpoint. Historical versions remain addressable. A current artifact/schema checksum mismatch makes the version non-executable.

### Safe artifact policy

Phase 4 executes only `tinkerlab_linear_json_v1` using the code-registered `demo_linear_json` predictor. Arbitrary `pickle`/`joblib` or user-supplied executable module loading is not supported.

### Predictor contract

The code-registered predictor declares:

- key;
- contract version;
- safe artifact formats;
- deterministic behavior;
- maximum batch size;
- `predict_batch` behavior.

The demo implementation is transparent, deterministic and synthetic.

---

## Applicability

Applicability is assessed before inference using:

1. approved model/model-version lifecycle;
2. property support;
3. material-family support;
4. required feature presence;
5. redaction/missing-input policy;
6. numeric feature range domain;
7. typed target-condition unit/range domain;
8. configured borderline tolerance.

Supported statuses:

- `in_domain`;
- `borderline`;
- `out_of_domain`;
- `incomplete_inputs`;
- `unsupported_property`;
- `unsupported_material_family`;
- `unsupported_conditions`.

`out_of_domain`, `incomplete_inputs`, and unsupported outcomes persist an auditable refusal result with **no numeric point estimate and no interval**.

The seed demonstrates a redacted/incomplete known material that is refused rather than imputed.

---

## Uncertainty

Numeric predictions are incomplete without uncertainty.

The Phase-4 demo predictor uses a **fixed validation residual interval** stored in its immutable synthetic artifact. The seed declares:

- interval half-width: 2.0 MPa;
- synthetic nominal coverage: 0.90;
- synthetic validation/calibration metrics.

These numbers describe a synthetic software fixture only. They are not claims of real polymer-model accuracy or real-world calibration.

Constraint evaluation is conservative:

- entire prediction interval satisfies a hard inequality -> `PASS`, basis `model_prediction`;
- entire interval violates -> `FAIL`, basis `model_prediction`;
- interval crosses the requirement -> `UNKNOWN`, `PREDICTION_INTERVAL_CROSSES_CONSTRAINT`;
- no applicable prediction -> `UNKNOWN`.

For equality/target behavior, an interval spanning a target is not treated as proof of equality.

---

## Scientific integrity

The core invariant is structural:

`PropertyPrediction` and `MaterialPropertyObservation` are different entities/tables.

Prediction execution never writes a `MaterialPropertyObservation`.

Automated tests verify:

- generated hypotheses still receive zero inherited observations;
- prediction runs do not change observation counts;
- inapplicable targets have no fabricated numeric output;
- known evidence default comparison behavior remains unchanged;
- a prediction is used as fallback only when a specific prediction run is explicitly selected;
- known applicable evidence remains preferred even if a prediction also exists;
- prediction UI/API labels use `MODEL PREDICTION`, not experimental/verified language.

The seeded model carries this exact warning:

> DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions.

---

## Reproducibility

### Input feature checksum

Feature snapshots are normalized deterministically from structured material/hypothesis state and exclude irrelevant display metadata.

### Source scientific-object checksum

A separate checksum captures the scientific source representation used to construct the feature vector.

### Condition checksum

Target conditions are normalized with explicit units before hashing.

### Model checksums

Artifact and feature schema have immutable SHA-256 checksums.

### Prediction result checksum

Depends on:

- model version/artifact checksum;
- predictor contract version;
- feature checksum;
- property key;
- target-condition checksum;
- configuration checksum;
- applicability status;
- deterministic point/uncertainty output.

Timestamps and display labels are excluded.

### Run checksum

The prediction-run result checksum is derived from the ordered target-result checksums.

Automated tests prove identical scientific inputs reproduce the same checksum, while a changed target condition changes the checksum.

---

## Database

Forward migration:

`0004_property_prediction.py`

New tables:

- `prediction_models`;
- `prediction_model_versions`;
- `model_applicability_domains`;
- `prediction_targets`;
- `prediction_input_snapshots`;
- `prediction_runs`;
- `property_predictions`.

Important constraints/indexes include:

- unique logical model key per organisation scope;
- unique `(model_id, version)`;
- one applicability domain per model version;
- prediction target exactly-one-of material/hypothesis;
- indexes by project, model version, property, applicability, status and deterministic checksum.

Phase-4 migration only adds new prediction structures; it does not rewrite Phase-3 material/candidate/hypothesis IDs.

PostgreSQL-dialect offline Alembic generation:

- `0001 -> 0002 -> 0003 -> 0004`: **PASS**;
- generated DDL: **1,059 lines**.

Live PostgreSQL execution remains UNVERIFIED in this sandbox.

---

## Tests

Final backend suite:

**82/82 tests PASS**.

Coverage includes all previous phases plus:

- model registry/demo honesty;
- model-version listing;
- safe artifact rejection;
- disabled model refusal;
- deterministic artifact checksum;
- deterministic known-material feature snapshots;
- hypothesis feature extraction from hypothesis state, not parent observations;
- missing/redacted input handling;
- family/property/condition applicability;
- in-domain prediction with uncertainty;
- inapplicable result with no number;
- deterministic result/run checksum;
- changed-condition checksum;
- preview zero-persistence;
- explicit comparison policy;
- interval PASS/FAIL/UNKNOWN semantics;
- scoped prediction detail/run access;
- 200-target API budget;
- Phase-4 seed idempotency;
- zero observation pollution.

Additional checks:

- Python app/Alembic compile: **PASS**.
- TypeScript/TSX parser: **35 files, 0 syntax diagnostics**.
- frontend dependency-resolved tests/typecheck/lint/build: **UNVERIFIED** because `node_modules` cannot be installed in this sandbox.

---

## Performance profile

An isolated SQLite query-shape harness created **200 concrete polymer hypotheses** and executed one prediction property/model/condition batch.

Results:

| Operation | Shape |
|---|---:|
| Preview scientific reads | 8 SELECTs |
| Preview expected executions | 200 |
| Execute scientific reads | 10 SELECTs |
| Inference batch calls | 1 |
| Inference targets in batch | 200 |
| Persisted predictions | 200 |
| 100-result page reads | 4 SELECTs |

Execution also performs linear persistence writes for target/input-snapshot/prediction records (expected by the audit model). The critical improvement is that scientific reads and inference do not scale as query/model-load per target.

These are query-shape measurements from SQLite plus a synthetic deterministic model. **No production latency claim is made.**

---

## Security / privacy

- Prediction runs/results require explicit organisation scope.
- Private hypotheses/materials are scope checked before feature extraction.
- Normal result-list endpoints do not expose complete private feature vectors.
- Full feature snapshot is available only in an explicitly scoped prediction-detail endpoint.
- Logs are designed around IDs/checksum prefixes/counts rather than raw formulations.
- Global synthetic model lifecycle cannot be mutated through tenant endpoints.
- Arbitrary executable model artifacts are rejected.
- Customer data is not automatically used to train/update a global model.

Limitation: `X-Organisation-ID` remains a development scoping seam, not production authentication or authorization.

---

## Known limitations

1. The included predictor is **synthetic and not scientifically validated**.
2. No real trained materials model is bundled.
3. No learned applicability-distance metric exists yet; Phase 4 uses explicit configured domains.
4. No hidden feature imputation exists; incomplete inputs are refused, which is intentional.
5. Only a narrow generic polymer feature schema is executable in the demo.
6. Only one safe reviewed JSON predictor artifact format is executable.
7. Model-registration lifecycle is intentionally basic; production governance/approval workflows are later work.
8. Prediction execution is bounded synchronous work; no distributed inference queue is present.
9. Docker/live PostgreSQL/Pint/Ruff/Mypy/frontend dependency build/browser checks could not be executed in this sandbox.
10. The development organisation header is not production security.

---

## Deferred to Phase 5+

Explicitly deferred:

- multi-objective optimisation;
- Bayesian optimisation;
- evolutionary search;
- active experiment selection;
- experiment-value/information-gain policies;
- autonomous virtual experiment loops;
- ML force fields;
- DFT;
- molecular dynamics/LAMMPS;
- CALPHAD;
- HPC scheduling;
- physics simulation evidence;
- patent/novelty search;
- synthesis planning;
- physical laboratory execution/robotics;
- real model training pipelines;
- production SSO/billing/Kubernetes.

---

## Run commands

### Docker / normal machine

```bash
cp .env.example .env
docker compose up --build
```

### Backend quality

```bash
cd apps/api
pytest -q
ruff check .
mypy app
python -m compileall -q app alembic
```

### Real PostgreSQL

```bash
export DATABASE_URL='postgresql+psycopg://tinkerlab:tinkerlab@localhost:5432/tinkerlab'
alembic upgrade head
python -m app.db.seed
python -m app.db.seed
```

### PostgreSQL static migration check

```bash
DATABASE_URL='postgresql+psycopg://user:pass@localhost/db' alembic upgrade head --sql
```

### Frontend

```bash
cd apps/web
npm install
npm test
npm run typecheck
npm run lint
npm run build
```

---

## Phase-4 verification checklist

| Acceptance item | Result |
|---|---|
| Phase-3 baseline regression | PASS — 56/56 before Phase-4 changes |
| Clean Docker Compose | UNVERIFIED — Docker unavailable |
| Live PostgreSQL through `0004` | UNVERIFIED — server unavailable |
| Phase-3 live migration integrity | UNVERIFIED live; `0004` is additive and static DDL passes |
| Seed idempotency | PASS — automated Phase-4 entity-count regression |
| All backend tests | PASS — 82/82 |
| Ruff | UNVERIFIED — unavailable |
| Mypy | UNVERIFIED — unavailable |
| Pint-backed runtime | UNVERIFIED — Pint unavailable |
| Python compile | PASS |
| Frontend dependency-resolved tests | UNVERIFIED — dependencies absent |
| Full TypeScript typecheck | UNVERIFIED — dependencies absent |
| ESLint | UNVERIFIED — dependencies absent |
| Next production build | UNVERIFIED — dependencies absent |
| TS/TSX syntax parse | PASS — 35/35 |
| Browser smoke/responsive/console | UNVERIFIED |
| Model registry/version lifecycle | PASS at service/API test level |
| Safe artifact policy | PASS |
| Prediction preview zero persistence | PASS |
| Bounded run execution | PASS |
| Deterministic replay | PASS |
| Meaningful condition changes checksum | PASS |
| In-domain uncertainty-bearing result | PASS |
| OOD/incomplete has no numeric result | PASS |
| Hypothesis observation inheritance remains zero | PASS |
| Prediction creates zero observations | PASS |
| Known evidence distinct from prediction | PASS |
| Interval-crossing constraint -> UNKNOWN | PASS |
| Explicit comparison policy/backward compatibility | PASS |
| Prediction data scope/privacy regression | PASS at API test level |
| 200-target batch profile | PASS — 8 preview SELECTs, 10 execute SELECTs, 1 inference batch |
| Documentation updated | PASS |

Phase 4 is implemented and code-level verified in the available environment. The normal-machine dependency/Docker acceptance gate remains mandatory before Phase 5 can be considered production-certified.
