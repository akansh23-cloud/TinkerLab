# TinkerLab — Phase 4 Implementation Prompt

## Property Prediction & Uncertainty Engine

You are continuing the **actual TinkerLab Phase-3 repository**. Do not rebuild the product from scratch and do not replace the existing replacement, evidence, search-space, candidate-hypothesis, lineage or reproducibility models.

You are acting as the founding Principal Engineer, Scientific Software Architect, ML/Materials Informatics Architect, Product Architect and senior full-stack engineer for TinkerLab.

TinkerLab is a closed-loop **Material Replacement & Discovery Operating System**.

# THIS IS PHASE 4 ONLY

Phase 4 introduces a trustworthy **Property Prediction & Uncertainty Engine** for known materials and Phase-3 candidate hypotheses.

The objective is not to create a universal “MaterialGPT”. It is to establish a production-grade model registry, safe prediction contracts, applicability-domain checks, deterministic feature snapshots, calibrated uncertainty, batch prediction, prediction provenance, and evidence-aware comparison behavior.

The central product promise is:

> Given a specific candidate, a specific property, explicit target conditions and a registered model that is demonstrably applicable, TinkerLab can produce a reproducible model-backed prediction with uncertainty and provenance — while refusing or returning UNKNOWN when the model is not applicable.

Do **not** implement DFT, molecular dynamics, CALPHAD, ML force fields, autonomous experiment optimisation, active learning, patent search, synthesis planning, lab automation or robotics in Phase 4.

---

# 0. MANDATORY PHASE-3 STABILIZATION GATE

Before implementing Phase 4, run Phase 3 on a normal dependency-enabled machine.

The supplied Phase-3 artifact already passed in the original sandbox:

- **56/56 backend tests**;
- Python compilation;
- PostgreSQL-dialect Alembic static generation through `0003` (**810 lines**);
- **26 TypeScript/TSX files with 0 syntax-transpilation diagnostics**;
- a bounded SQLite query-shape profile with 500 hypotheses.

However, the original sandbox did not have Docker, a live PostgreSQL server, Pint, Ruff, Mypy or frontend `node_modules`.

## 0.1 Docker / real PostgreSQL

From a clean checkout:

1. `docker compose up --build`.
2. Apply `0001 -> 0002 -> 0003` on real PostgreSQL.
3. Seed twice and prove idempotency.
4. Restart API/web/PostgreSQL and prove persistence.
5. Create a disposable Phase-2 database snapshot with existing known-material candidate rows.
6. Upgrade `0002 -> 0003` and confirm IDs/relationships survive and candidates become `known_material` without ID churn.
7. Exercise `0003` downgrade only on disposable data and document the intentionally lossy removal of hypothesis candidates.
8. Do not edit historical migrations. Phase 4 must add `0004_property_prediction.py`.

## 0.2 Scientific unit runtime

Install declared Python dependencies and confirm the production/local unit service actually uses Pint.

Run/fix tests for at least:

- MPa ↔ Pa;
- kg/m³ ↔ g/cm³;
- °C conversions;
- pressure;
- frequency;
- any additional property units introduced by Phase 4;
- incompatible-unit rejection.

Remove the need for the sandbox compatibility fallback in a normal environment, but retain a clean failure mode if Pint is genuinely unavailable where appropriate.

## 0.3 Backend quality

Run:

```bash
cd apps/api
pytest -q
ruff check .
mypy app
```

Fix root causes. Do not globally suppress type/lint errors.

## 0.4 Frontend quality

Run:

```bash
cd apps/web
npm install
npm test
npm run typecheck
npm run lint
npm run build
```

Then browser-smoke:

- Dashboard;
- replacement wizard;
- project workspace;
- Materials Explorer;
- Material Passport v2;
- Observation/Provenance Inspector;
- Import Center;
- Candidate Lab;
- search-space validation;
- generation preview;
- generation execution;
- generation-run detail;
- hypothesis detail/lineage;
- mixed known/hypothesis comparison;
- responsive behavior;
- console/network errors.

## 0.5 Privacy regression

Verify that without valid organisation scope no Phase-3 private search space, substitution rule mutation, generation run, hypothesis, lineage or hypothesis-inclusive comparison is exposed.

`X-Organisation-ID` is still only a development scoping seam. Do not call it production authentication.

## 0.6 Stabilization output

Create:

`docs/PHASE3_STABILIZATION_FOR_PHASE4.md`

Document exact PASS/FAIL/UNVERIFIED results and every stabilization fix.

Only then implement Phase 4.

---

# 1. NON-NEGOTIABLE SCIENTIFIC PRINCIPLES

## 1.1 Prediction is not measurement

A model-backed prediction must never be stored or displayed as if it were experimental, literature, supplier or physics-simulation evidence.

UI/API must distinguish at least:

- `KNOWN EVIDENCE`;
- `MODEL PREDICTION`;
- `UNKNOWN`.

Do not silently create `MaterialPropertyObservation` rows from predictions.

Keep predictions first-class and separate.

## 1.2 No model may predict outside its declared applicability without explicit handling

Every prediction request must first evaluate model applicability.

Applicability statuses should support concepts such as:

- `in_domain`;
- `borderline`;
- `out_of_domain`;
- `incomplete_inputs`;
- `unsupported_property`;
- `unsupported_material_family`;
- `unsupported_conditions`.

Default behavior:

- `in_domain` -> prediction allowed;
- `borderline` -> prediction may be returned with a prominent warning if model policy permits;
- `out_of_domain` / incomplete / unsupported -> do not invent a number; result remains UNKNOWN.

## 1.3 Uncertainty is mandatory

A Phase-4 numeric prediction is incomplete without uncertainty.

Every model version must declare its uncertainty method.

Support one or more honest methods such as:

- calibrated residual interval;
- quantile bounds;
- conformal interval;
- ensemble spread;
- explicitly documented fixed validation interval for the synthetic demo model.

Do not create a confidence percentage with no calibration meaning.

## 1.4 Conditions are part of the prediction target

A prediction for tensile strength at 23 °C is not automatically a prediction at 80 °C.

Target conditions must be represented using the Phase-2 condition model or a compatible typed prediction-target condition representation.

The model must declare which conditions are required/supported and the allowed range/domain.

## 1.5 Model versions are immutable scientific artifacts

A model update creates a new version.

Do not mutate coefficients/artifact/checksum/calibration metadata of a model version that has produced persisted predictions.

Historical predictions must remain reproducible from their recorded model version and input snapshot.

## 1.6 Input snapshot/provenance is required

Every persisted prediction must record exactly what the model saw.

At minimum:

- candidate/material identity;
- hypothesis fingerprint or known-material scientific input checksum;
- feature schema version;
- normalized feature snapshot checksum;
- model/version/artifact checksum;
- target property;
- target conditions;
- unit normalization version;
- prediction configuration checksum.

Do not rely on “current candidate state” for historical reproducibility.

## 1.7 Missing/redacted inputs are not guessed

If a model requires a composition/process feature that is redacted or unavailable, applicability becomes `incomplete_inputs` and the property remains UNKNOWN.

No LLM filling.

No mean imputation unless a particular approved model explicitly declares/documented imputation as part of its immutable pipeline; if used later, expose it in provenance.

The Phase-4 demo predictor should avoid hidden imputation.

## 1.8 Prediction does not erase known evidence

Known Phase-2 evidence remains visible and authoritative according to explicit selection policy.

If a known material has applicable measured/reported evidence and also a prediction, show both with separate origins.

Do not silently overwrite the evidence-selected value with a model result.

## 1.9 Conservative constraint interpretation under uncertainty

For a predicted numeric property and a hard threshold:

- if the **entire declared prediction interval** satisfies the constraint -> predicted PASS may be shown;
- if the **entire interval** violates it -> predicted FAIL may be shown;
- if the interval crosses the requirement boundary -> constraint result should remain `UNKNOWN`/`UNCERTAIN`, not be forced to PASS based on the point estimate.

For equality/target/between constraints, implement similarly defensible interval-aware behavior and document it.

Keep the existing machine status compatibility (`PASS | FAIL | UNKNOWN`) where practical, but add a required `basis`/`value_origin` field so the UI can render `Predicted PASS` versus `Evidence PASS`.

## 1.10 No unsafe model artifact execution

Do not accept arbitrary pickle/joblib files from users and execute them.

Prefer safe explicit model formats for Phase 4, for example:

- validated JSON coefficient artifacts for the transparent demo predictor;
- ONNX or another constrained runtime later if justified;
- code-shipped, reviewed predictor implementations with immutable artifact hashes.

---

# 2. PRESERVE PHASE-1/2/3 ARCHITECTURE

Do not replace:

- FastAPI/Pydantic/SQLAlchemy/Alembic modular monolith;
- PostgreSQL target;
- typed unit handling;
- Materials Knowledge & Evidence Graph;
- condition-aware observation selection;
- conflict policies;
- Replacement Specification compiler/checksum;
- CandidateSearchSpace / generation runs;
- CandidateHypothesis separation from Material;
- fingerprints/lineage/change records;
- Candidate Lab;
- Phase-3 privacy seams.

Do not create a microservice explosion or Kubernetes deployment.

Phase 4 should be a logical `prediction` module inside the modular monolith with explicit future extraction seams.

---

# 3. PHASE-4 DOMAIN MODEL — FORWARD `0004`

Add a forward migration:

`0004_property_prediction.py`

Do not modify `0001`, `0002` or `0003`.

Exact names may improve if justified, but the following concepts are required.

## 3.1 PredictionModel

Represents a logical model family/registry entry.

Suggested fields:

- id;
- organisation scope nullable for globally curated models;
- key;
- display_name;
- description;
- model_type;
- owner/provider;
- status (`draft | approved | disabled | retired`);
- material families supported;
- property keys supported;
- created_at / updated_at.

Only approved model versions may be used for normal automatic prediction.

## 3.2 PredictionModelVersion

Immutable versioned scientific artifact.

Suggested fields:

- id;
- model_id;
- version;
- predictor_key;
- predictor_contract_version;
- artifact_format;
- artifact_uri/reference where applicable;
- artifact_checksum;
- feature_schema_version;
- feature_schema/checksum;
- target_property_key;
- canonical_output_unit;
- uncertainty_method;
- applicability policy/version;
- training-data descriptor/checksum (metadata only; do not copy proprietary training data blindly);
- calibration metrics;
- validation metrics;
- approved_at;
- retired_at nullable;
- immutable metadata;
- created_at.

Enforce unique `(model_id, version)`.

Do not allow in-place artifact edits after use.

## 3.3 ModelApplicabilityDomain

Do not hide applicability in a free-text note.

Support structured constraints such as:

- material families;
- required feature keys;
- numeric feature min/max;
- allowed categorical values;
- required composition roles/component keys where model-specific;
- target-condition min/max with units;
- unsupported/redacted-input policy;
- optional domain-distance method/configuration;
- borderline tolerance.

JSON is acceptable for model-specific extensibility only after a typed top-level schema exists.

## 3.4 PredictionTarget

A prediction target must reference exactly one candidate scientific object:

- known `Material`; or
- `CandidateHypothesis`.

It should include:

- target property definition;
- requested condition set/context;
- requested output unit if supported;
- project/candidate association where relevant.

Do not make target identity ambiguous.

## 3.5 PredictionInputSnapshot

Persist the normalized input state used for inference.

Suggested fields:

- id;
- target kind/id;
- model version;
- feature schema version;
- normalized feature payload;
- feature checksum;
- source entity fingerprint/checksum;
- target-condition checksum;
- missing-feature list;
- redaction flags;
- created_at.

Feature payload may be JSON because model feature vectors vary, but validate it against the immutable model version schema before persistence.

Never store unnecessary secret raw customer payloads.

## 3.6 PredictionRun

Auditable request/batch execution.

Suggested fields:

- id;
- project_id/organisation_id where relevant;
- model version id;
- property key;
- configuration checksum;
- target-condition checksum;
- requested target count;
- predicted count;
- inapplicable count;
- failed count;
- run status;
- run seed only if a model genuinely requires controlled randomness;
- started/completed timestamps;
- created_by;
- result checksum;
- metadata.

Phase 4 may run bounded batches synchronously. No distributed queue is required.

## 3.7 PropertyPrediction

Persist prediction outputs separately from Phase-2 observations.

At minimum:

- id;
- prediction_run_id;
- prediction_target/reference;
- model_version_id;
- input_snapshot_id;
- property_definition_id;
- applicability status;
- applicability rationale;
- domain distance/score only if scientifically defined;
- numeric point estimate nullable;
- output unit;
- canonical value nullable;
- canonical unit;
- uncertainty lower/upper;
- uncertainty standard deviation nullable;
- uncertainty method;
- calibrated coverage level nullable;
- warnings;
- status (`predicted | inapplicable | failed | superseded`);
- deterministic result checksum;
- created_at.

If applicability rejects inference, point estimate/interval must remain null.

## 3.8 PredictionSelectionPolicy (optional but recommended)

If project comparisons may use predictions as fallback, make policy explicit/versioned rather than hidden.

Example policy:

- known applicable evidence always displayed;
- model prediction may fill a missing evidence slot only when user enables prediction support;
- required model/version may be pinned by project/run;
- inapplicable predictions never fill values;
- uncertainty-crossing constraints remain UNKNOWN.

Do not silently change historical comparison semantics.

---

# 4. PROPERTY PREDICTOR CONTRACT

Upgrade the existing future `PropertyPredictor` protocol into a real Phase-4 contract.

Conceptually:

```python
class PropertyPredictor(Protocol):
    key: str
    contract_version: str

    def capabilities(...) -> ...
    def featurize(...) -> FeatureSnapshot
    def assess_applicability(...) -> ApplicabilityResult
    def predict_batch(...) -> list[PredictionOutput]
```

Every registered predictor must declare:

- supported model artifact format;
- supported material families/properties;
- required feature schema;
- deterministic/stochastic behavior;
- unit contract;
- uncertainty contract;
- maximum safe batch size;
- whether target conditions are required;
- failure semantics.

Predictors are explicitly registered. Do not import arbitrary executable plugins by path supplied by users.

---

# 5. FEATURE EXTRACTION

Create a deterministic feature-extraction layer that can read both:

- canonical known materials;
- Phase-3 candidate hypotheses.

The feature extractor must preserve the distinction between known/hypothesis origin.

For the Phase-4 generic polymer demonstration, a narrowly scoped feature schema may use synthetic generic formulation fields such as:

- Base Resin A fraction;
- Modifier B or B2 fraction;
- Reinforcement C fraction;
- generic process temperature if present.

Do not derive ungrounded chemistry descriptors from generic demo component names.

For known materials, structured composition/process state comes from Phase 2.

For hypotheses, concrete proposed composition/process state comes from Phase 3.

Requirements:

- deterministic ordering;
- canonical units;
- feature schema validation;
- explicit missing features;
- explicit redacted features;
- input checksum;
- no hidden defaulting.

---

# 6. APPLICABILITY ENGINE

Implement applicability before inference.

At minimum evaluate:

1. model status/version approval;
2. target property support;
3. material-family support;
4. required feature presence;
5. redaction/missing-input policy;
6. numeric feature range domain;
7. categorical domain;
8. requested condition support/range;
9. model-specific domain-distance rule if one exists.

Return structured results, e.g.:

```json
{
  "status": "out_of_domain",
  "reasons": [
    {
      "code": "FEATURE_OUTSIDE_TRAINING_RANGE",
      "feature": "modifier_fraction",
      "value": 31.0,
      "allowed": [10.0, 25.0]
    }
  ]
}
```

No generic 500s for scientific inapplicability.

---

# 7. PHASE-4 DEMO PREDICTOR — TRANSPARENT AND SYNTHETIC

Phase 4 needs an executable end-to-end prediction path, but do not pretend a synthetic demo model is industrially validated.

Implement one narrowly scoped, transparent **DEMO-ONLY** predictor for the existing synthetic engineering-polymer fixture.

Recommended approach:

- immutable JSON coefficient/artifact representation;
- deterministic linear or similarly interpretable function;
- no arbitrary Python pickle;
- coefficients/fixture inputs derived from a deterministic synthetic demonstration dataset, not presented as real chemistry;
- one or two properties at most (for example the generic demo `tensile_strength` and/or `density` only if the existing property schema supports them cleanly);
- explicit feature ranges defining applicability;
- held-out synthetic validation fixture;
- recorded synthetic MAE/RMSE and interval coverage;
- uncertainty interval derived from the documented synthetic validation residual policy.

Every API/UI location must label the model:

`DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions.`

The purpose is to validate the prediction operating system, not claim scientific discovery.

Architecture must allow a later scientifically validated model version to be registered without changing prediction storage/evaluation contracts.

---

# 8. MODEL REGISTRY / APPROVAL

Build a model registry with safe lifecycle.

Required behavior:

- create/register draft model metadata;
- create immutable version;
- validate artifact/schema/checksums;
- approve version;
- disable/retire future use;
- historical predictions remain readable;
- version/artifact checksum visible;
- model cannot be modified in place after a prediction exists.

For Phase 4, model artifact registration may be admin/seed driven rather than open upload.

Do not implement arbitrary user-uploaded executable models.

---

# 9. PREDICTION PREVIEW

Before execution, support preview with no prediction persistence.

Preview should report:

- requested model/version;
- target candidate count;
- property;
- target conditions;
- feature-schema version;
- input-completeness summary;
- applicability counts estimated or fully assessed for bounded batch;
- in-domain/borderline/out-of-domain counts;
- expected model executions;
- configuration checksum;
- candidate/input checksum summary;
- validation problems.

Preview must not create `PropertyPrediction` rows.

---

# 10. BOUNDED BATCH PREDICTION

Support bounded synchronous prediction runs.

Suggested default maximum: 200 targets per run, with a documented hard limit.

Do not introduce Celery/Kafka/distributed inference in this phase unless the stabilization audit proves a real current need.

Batch implementation must avoid:

- query per candidate per feature;
- loading the same model artifact repeatedly;
- recomputing identical feature snapshots unnecessarily;
- unbounded response/persistence loops.

Persist every target outcome, including `inapplicable` results, so users can understand why a number was not produced.

---

# 11. PREDICTION RESULT CHECKSUM / REPRODUCIBILITY

A prediction result checksum should depend on immutable scientific inputs such as:

- model version/artifact checksum;
- predictor contract version;
- feature/input checksum;
- property key;
- condition checksum;
- prediction configuration;
- deterministic model result + uncertainty representation.

Same immutable inputs must reproduce the same result checksum for deterministic models.

A changed candidate fingerprint, feature, condition, model version or configuration must change the appropriate input/result checksum.

Do not include timestamps/display labels in scientific checksums.

---

# 12. COMPARISON / CONSTRAINT INTEGRATION

Extend existing candidate evaluation without breaking Phase-1/2/3 consumers.

## 12.1 Known materials

Continue to show Phase-2 selected evidence.

If a prediction exists, show it separately. Do not replace applicable known evidence by default.

## 12.2 Hypotheses

Before Phase 4 prediction:

`UNKNOWN — NOT YET PREDICTED/TESTED`

After an applicable prediction:

show point estimate, interval, model/version, applicability and prediction provenance.

No prediction for a property -> UNKNOWN remains.

## 12.3 Constraint basis

Add fields such as:

- `value_origin: known_evidence | model_prediction | none`;
- `prediction_id`;
- `model_version`;
- `prediction_interval`;
- `applicability_status`;
- `uncertainty_crosses_constraint`.

A PASS/FAIL based on model output must be visibly rendered as **Predicted PASS/FAIL**, never visually identical to evidence-backed PASS/FAIL.

If uncertainty crosses the requirement threshold, return machine status UNKNOWN with a reason such as `PREDICTION_INTERVAL_CROSSES_CONSTRAINT`.

## 12.4 Selection policy

Do not globally turn on prediction fallback for historical calls.

Use an explicit request/project policy, for example:

`?prediction_run_id=...`

or a typed comparison policy body/version.

Default comparison behavior should remain backwards compatible.

---

# 13. API REQUIREMENTS

Exact URLs may improve, but implement capabilities equivalent to:

## Registry

- `GET /prediction-models`
- `GET /prediction-models/{id}`
- `GET /prediction-model-versions/{id}`
- create/register draft model/version in an appropriately scoped admin/demo path;
- approve/disable/retire lifecycle actions.

## Applicability

- assess one target/model/property without executing/persisting a prediction.

## Prediction preview

`POST /replacement-projects/{id}/prediction-runs/preview`

## Prediction execution

`POST /replacement-projects/{id}/prediction-runs`

## Run history

- `GET /replacement-projects/{id}/prediction-runs`
- `GET /prediction-runs/{id}`
- `GET /prediction-runs/{id}/results` with pagination.

## Target history

- `GET /candidate-hypotheses/{id}/predictions`
- `GET /materials/{id}/predictions` with correct visibility scope.

## Prediction detail

Expose:

- point/interval/units;
- applicability;
- model/version/artifact checksum;
- feature/input checksum;
- target condition checksum;
- warnings;
- reproducibility checksum;
- clearly marked prediction origin.

## Comparison

Support an explicit prediction run/policy while preserving the default Phase-3 comparison contract.

---

# 14. UI — PREDICTION LAB

Do not build a flashy “AI oracle”. Build an auditable engineering UI.

## 14.1 Candidate Lab extension

For each candidate show:

- known/hypothesis kind;
- known evidence coverage;
- prediction coverage for the selected run;
- model applicability posture;
- hard-constraint evidence/predicted/unknown counts;
- no fake overall score.

## 14.2 Prediction Lab

Add a project-level Prediction Lab that shows:

- available approved model versions;
- model property/family capabilities;
- explicit DEMO MODEL warning where applicable;
- selected property;
- target conditions;
- target candidate selection;
- preview/applicability matrix;
- prediction budget;
- execute button only after valid preview.

## 14.3 Prediction run detail

Show:

- model/version;
- artifact checksum;
- feature schema;
- condition/config checksums;
- requested/predicted/inapplicable/failed counts;
- result checksum;
- paginated result list.

## 14.4 Prediction detail

Show:

- target;
- property;
- point estimate;
- lower/upper uncertainty;
- units/canonical units;
- applicability and rationale;
- feature snapshot summary;
- input checksum;
- model artifact checksum;
- validation/calibration metrics;
- warnings;
- scientific-origin label.

## 14.5 Candidate hypothesis detail

Extend the Phase-3 hypothesis page:

- retain hypothesis warning;
- add a Predictions section;
- distinguish UNKNOWN from predicted;
- show uncertainty and applicability;
- never call prediction validation/verification.

## 14.6 Comparison

Visually distinguish:

- Evidence PASS/FAIL;
- Predicted PASS/FAIL;
- Prediction uncertain -> UNKNOWN;
- No value -> UNKNOWN.

Do not reduce this to one AI score.

---

# 15. SEEDED PHASE-4 DEMONSTRATION

Extend the existing synthetic generic polymer demo only.

Seed deterministically:

- one logical demo prediction model;
- one approved immutable version;
- a safe JSON coefficient artifact or equivalent reviewed representation;
- explicit feature schema;
- applicability ranges;
- synthetic validation/calibration metrics;
- one default project prediction run;
- predictions for a few Phase-3 hypotheses including:
  - at least one in-domain prediction;
  - one candidate whose uncertainty crosses a hard constraint and therefore remains UNKNOWN;
  - one inapplicable/OOD or incomplete-input target with no numeric prediction;
- one known material prediction to demonstrate coexistence with Phase-2 evidence.

All seeded model/prediction content must be labelled synthetic demo data.

Seed twice must be idempotent.

---

# 16. MODEL / DATA PRIVACY

Prediction execution must preserve organisation scope.

At minimum:

- private hypothesis features are not visible outside organisation scope;
- private material features are not exposed through prediction APIs unscoped;
- prediction runs/results are organisation/project scoped;
- feature snapshots containing private composition are not returned wholesale unless the requester is correctly scoped and the response model is explicitly intended to show them;
- logs do not emit raw private feature vectors;
- private customer data is **not** used to train/update global models by default;
- model-training consent/governance is out of scope unless explicitly designed later.

Remember: `X-Organisation-ID` is not production auth.

---

# 17. PERFORMANCE

Phase 4 must batch data access and inference.

Create a bounded profile using, for example:

- 200 candidate hypotheses;
- one model/property;
- prediction preview;
- batch execution;
- paginated result retrieval;
- comparison for a page/selected run.

Document SQL query shape/count and number of model artifact loads/inference batches.

Do not publish arbitrary production latency claims from SQLite or synthetic model execution.

---

# 18. TESTING

Keep **all 56 Phase-1/2/3 backend tests green** and substantially extend coverage.

## 18.1 Migration

Verify:

- `0003` data survives `0004`;
- no candidate/material/hypothesis IDs change;
- prediction tables/constraints/indexes exist;
- downgrade behavior documented on disposable data.

## 18.2 Model registry

- unique model/version;
- only approved versions executable;
- disabled/retired blocked for new runs;
- artifact checksum deterministic;
- model version immutable after predictions exist;
- arbitrary executable artifact format rejected.

## 18.3 Feature extraction

- known material deterministic features;
- hypothesis deterministic features;
- ordering independent checksum;
- meaningful input change changes checksum;
- units canonicalized;
- missing feature explicit;
- redacted feature explicit;
- no hidden imputation.

## 18.4 Applicability

- supported family/property accepted;
- unsupported property rejected;
- unsupported family rejected;
- missing feature -> incomplete;
- redacted required feature -> incomplete;
- numeric OOD -> out_of_domain;
- condition OOD -> unsupported/out-of-domain;
- borderline logic deterministic.

## 18.5 Prediction

- in-domain result includes point + interval;
- inapplicable result has no numeric value;
- uncertainty ordering lower <= point <= upper where model semantics require;
- units valid/canonical;
- same input/model/config -> same result checksum;
- changed model/input/condition -> changed checksum;
- predictions create zero `MaterialPropertyObservation` rows.

## 18.6 Constraint integration

- known evidence default behavior unchanged;
- prediction fallback only when explicitly requested;
- full prediction interval satisfying threshold -> Predicted PASS;
- full interval failing -> Predicted FAIL;
- interval crossing threshold -> UNKNOWN;
- no prediction -> UNKNOWN;
- UI/API `value_origin` correct.

## 18.7 Demo-model honesty

Automated tests must assert the demo model returns/display metadata containing a clear `DEMO MODEL` / synthetic validation warning.

## 18.8 API

Cover registry, applicability, preview no-persistence, execution, result pagination, history, prediction detail, hypothesis/material history, explicit comparison policy and privacy.

## 18.9 Frontend

Cover at least:

- demo-model warning;
- preview does not execute;
- applicability badges;
- prediction interval rendering;
- Evidence versus Predicted labels;
- interval-crosses-constraint renders UNKNOWN;
- OOD has no fabricated value;
- no fake AI score.

---

# 19. OBSERVABILITY

Add structured prediction events containing only non-secret metadata:

- request/correlation ID;
- prediction run ID;
- project ID;
- model/version ID;
- property key;
- input/condition checksum prefixes;
- target/predicted/inapplicable/failed counts;
- inference batch count;
- duration;
- failure code.

Do not log raw private formulations/features or full model artifacts.

---

# 20. DOCUMENTATION

Create/update at minimum:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_MODEL.md`
- `docs/ERD.md`
- `docs/PHASE3_STABILIZATION_FOR_PHASE4.md`
- `docs/PHASE4_SCOPE.md`
- `docs/MODEL_REGISTRY.md`
- `docs/PREDICTOR_CONTRACT.md`
- `docs/FEATURE_SNAPSHOTS.md`
- `docs/APPLICABILITY_DOMAIN.md`
- `docs/PREDICTION_UNCERTAINTY.md`
- `docs/PREDICTION_REPRODUCIBILITY.md`
- `docs/PREDICTION_SELECTION_POLICY.md`
- `docs/SCIENTIFIC_INTEGRITY.md`
- `docs/PRIVACY_MODEL.md`
- `docs/FUTURE_ARCHITECTURE.md`

Document exactly how uncertainty and interval-based constraint decisions work.

---

# 21. EXPLICITLY DO NOT IMPLEMENT IN PHASE 4

Do not implement:

- LLM-based material property invention;
- MatterGen;
- universal graph neural model training;
- arbitrary unreviewed model downloads;
- user-uploaded pickle/joblib execution;
- ML force fields;
- DFT / Quantum ESPRESSO;
- LAMMPS / molecular dynamics;
- CALPHAD;
- HPC scheduling;
- Bayesian optimisation;
- evolutionary optimisation;
- active learning / experiment recommendation;
- reinforcement learning;
- patent/novelty search;
- synthesis recipe generation;
- hazardous operating procedures;
- lab robotics;
- Kubernetes/microservice decomposition;
- production billing/SSO unless required to fix a critical pre-existing security defect.

Phase 5 is the autonomous virtual experiment/optimisation phase. Do not consume it now.

---

# 22. REQUIRED QUALITY CHECK

Before declaring Phase 4 complete:

1. Clean Docker Compose boot.
2. Real PostgreSQL migrations through `0004`.
3. Phase-3 data migration integrity.
4. Seed twice/idempotency.
5. All backend tests.
6. Ruff.
7. Mypy.
8. Pint-backed unit tests.
9. Frontend tests.
10. Full TypeScript typecheck.
11. ESLint.
12. Next production build.
13. Browser smoke test.
14. Model registry/lifecycle smoke test.
15. Prediction preview proves zero persistence.
16. Execute bounded prediction run.
17. Re-run deterministic input and prove same checksum.
18. Change candidate/model/condition and prove checksum changes.
19. Inspect in-domain result with uncertainty.
20. Inspect OOD/incomplete result with **no numeric value**.
21. Verify generated hypothesis still has zero inherited material observations.
22. Verify prediction creates zero `MaterialPropertyObservation` rows.
23. Verify known evidence remains distinct from prediction.
24. Verify interval-crossing constraint returns UNKNOWN.
25. Verify explicit comparison policy/default backward compatibility.
26. Verify private prediction data does not leak.
27. Profile 200-target batch/query behavior.
28. Check browser console/responsiveness.
29. Remove caches/debug/generated junk.
30. Update docs truthfully.

Never mark an unavailable/unexecuted check PASS.

---

# 23. PHASE-4 ACCEPTANCE CRITERIA

Phase 4 is complete only if:

- stabilization gate is completed on real dependencies;
- forward `0004` works;
- model registry/version lifecycle exists;
- model artifacts are immutable/checksummed;
- predictor contract is explicit/registered;
- feature snapshots are deterministic/versioned;
- applicability is assessed before inference;
- OOD/incomplete targets receive no fabricated numeric prediction;
- uncertainty is mandatory;
- synthetic demo predictor is unmistakably labelled demo-only;
- prediction runs are bounded/reproducible;
- predictions are separate from material observations;
- known evidence remains separate/visible;
- hypotheses can receive explicit model-backed prediction records;
- interval-aware constraint evaluation is conservative;
- default Phase-3 comparisons remain compatible;
- privacy scope is maintained;
- Prediction Lab UI is usable/auditable;
- tests/lint/typecheck/build pass in normal environment;
- documentation matches the actual implementation.

---

# 24. FINAL DELIVERY

Return a clean ZIP of the complete Phase-4 repository.

Exclude:

- `node_modules`;
- Python virtual environments;
- `.next`;
- test SQLite databases;
- caches;
- debug dumps;
- local secrets;
- large model artifacts not required by the safe synthetic demo;
- unnecessary binaries.

Provide a detailed implementation report containing:

## Phase-3 stabilization

Exact checks/fixes.

## Implemented

Actual Phase-4 functionality.

## Model architecture

Registry/version/artifact/predictor design.

## Applicability

Exact domain logic and refusal behavior.

## Uncertainty

Exact method(s), calibration meaning and limitations.

## Scientific integrity

How code prevents predictions from masquerading as observations.

## Reproducibility

Feature/model/config/condition/result checksums and proof.

## Database

`0004` tables/constraints/indexes.

## Tests

Exact results/counts.

## Performance profile

Bounded batch/query/inference shape, without unjustified latency claims.

## Security/privacy

Scope and model-artifact safety.

## Known limitations

Be explicit, especially that the synthetic demo model is not scientifically validated.

## Deferred to Phase 5+

List everything deliberately postponed.

## Run commands

Exact clean-machine commands.

## Verification checklist

Every acceptance item marked PASS / FAIL / UNVERIFIED.

Do not claim PASS without execution.

---

# 25. STOP CONDITION

At the end of Phase 4, **stop**.

Do not start Phase 5 automatically.

The completed Phase-4 package must be audited first. Phase 5 will introduce the **Autonomous Virtual Experiment Brain** (multi-objective search, active experiment selection and optimization), and its design must depend on the actual prediction/uncertainty contracts created in Phase 4.
