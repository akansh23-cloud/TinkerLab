# TinkerLab — Phase 5 Implementation Prompt

## Autonomous Virtual Experiment & Multi-Objective Optimization Brain

You are continuing the **actual TinkerLab Phase-4 repository**. Do not rebuild the product from scratch and do not replace the existing evidence, candidate-generation or property-prediction architecture.

You are acting as the founding Principal Engineer, Scientific Software Architect, Optimization/Materials Informatics Architect, Product Architect and senior full-stack engineer for TinkerLab.

TinkerLab is a closed-loop **Material Replacement & Discovery Operating System**.

# THIS IS PHASE 5 ONLY

Phase 5 introduces an uncertainty-aware **Autonomous Virtual Experiment Brain** that can operate on the bounded Phase-3 candidate search space and the explicit Phase-4 property-prediction contracts.

The objective is **not** to pretend that software predictions are physical experiments or physics simulations.

The Phase-5 product promise is:

> Given a replacement specification, a bounded/versioned candidate search space, explicit objective properties, approved prediction model versions and a strict experiment/candidate budget, TinkerLab can reproducibly generate/evaluate bounded material hypotheses, preserve uncertainty, identify robust Pareto trade-offs, choose the next virtual candidates to explore, mutate only curator-authorized dimensions, explain every decision, and stop safely when its budget or defensible stopping conditions are reached.

A Phase-5 “virtual experiment” is a **model-backed computational evaluation of a candidate hypothesis**, not experimental evidence and not a physics simulation.

Do not implement DFT, molecular dynamics, CALPHAD, ML force fields, HPC scheduling, patent search, synthesis procedures, physical lab automation, robotics or laboratory feedback learning in Phase 5.

---

# 0. MANDATORY PHASE-4 STABILIZATION GATE

Before adding Phase-5 functionality, verify Phase 4 on a normal networked/Docker-enabled machine.

The supplied Phase-4 artifact already passed in the original artifact sandbox:

- **82/82 backend tests**;
- Python application/Alembic compilation;
- PostgreSQL-dialect Alembic static generation through `0004` (**1,059 lines**);
- **35 TypeScript/TSX files with 0 parser diagnostics**;
- a 200-target prediction query/inference profile:
  - preview: 8 SELECTs;
  - execution scientific reads: 10 SELECTs;
  - predictor: 1 batch call / 200 targets;
  - 100-result page: 4 SELECTs.

The original sandbox did **not** have Docker, a live PostgreSQL server, Pint, Ruff, Mypy or frontend `node_modules`.

## 0.1 Docker / PostgreSQL

From a clean checkout:

1. `docker compose up --build`.
2. Apply `0001 -> 0002 -> 0003 -> 0004` on real PostgreSQL.
3. Seed twice and prove idempotency.
4. Restart API/web/PostgreSQL and prove persistence.
5. Create a disposable Phase-3 database snapshot and upgrade `0003 -> 0004`.
6. Confirm all Phase-3 material/candidate/hypothesis/generation IDs survive.
7. Confirm Phase-4 model/prediction constraints and indexes exist.
8. Exercise downgrade only on disposable data and document that Phase-4 prediction data is removed.
9. Do **not** edit migrations `0001`-`0004`.
10. Phase 5 must add a forward `0005_virtual_experiment_brain.py` migration.

## 0.2 Scientific unit runtime

Install declared dependencies and prove Pint-backed unit handling for all existing units.

Run/fix at least:

- MPa / Pa;
- density units;
- temperatures including offset conversion;
- pressure;
- frequency;
- any normalized objective units introduced by Phase 5;
- incompatible-unit rejection.

## 0.3 Backend quality

Run:

```bash
cd apps/api
pytest -q
ruff check .
mypy app
```

Fix root causes. Do not globally suppress errors.

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

Browser-smoke all Phase-1/2/3/4 flows including Prediction Lab, run detail, prediction detail, hypothesis predictions and explicit prediction comparison.

## 0.5 Phase-4 scientific regression

Explicitly prove:

- `PropertyPrediction` is still separate from `MaterialPropertyObservation`;
- prediction execution creates no observations;
- OOD/incomplete targets return no number;
- known evidence remains preferred;
- a prediction is used as comparison fallback only when an explicit prediction run is selected;
- interval-crossing hard constraints return UNKNOWN;
- demo model warning remains visible;
- private feature snapshots/runs/results do not leak unscoped;
- arbitrary pickle/joblib artifacts remain non-executable.

## 0.6 Stabilization output

Create:

`docs/PHASE4_STABILIZATION_FOR_PHASE5.md`

Document exact PASS/FAIL/UNVERIFIED results and every fix.

Do not start optimization work until P0/P1 issues are resolved.

---

# 1. NON-NEGOTIABLE SCIENTIFIC / OPTIMIZATION PRINCIPLES

## 1.1 A virtual experiment is not physical evidence

Phase-5 evaluations must be explicitly labelled:

`VIRTUAL EVALUATION — MODEL-BASED`

They must never create experimental `Evidence` or `MaterialPropertyObservation` records.

Do not use wording such as:

- experimentally validated;
- lab confirmed;
- physically proven;
- simulation validated;
- discovered material.

unless a later phase actually provides that evidence.

## 1.2 Preserve Phase-4 uncertainty

Optimization must never reduce a prediction to only its point estimate internally and forget the interval.

Every decision service must have access to:

- prediction point;
- lower/upper interval;
- applicability status;
- uncertainty method/coverage where available;
- model/version identity;
- origin.

## 1.3 Do not reward unknown as success

Hard-constraint posture must support at least:

- robustly feasible;
- uncertain/unknown;
- robustly infeasible.

A missing or inapplicable prediction is **not PASS**.

Do not silently eliminate UNKNOWN candidates without recording why and whether campaign policy allows keeping them for exploration.

## 1.4 Do not claim a global optimum

Phase-5 search is bounded by the configured search space, models, candidate budget and policies.

UI/API should say:

- best candidate observed in this campaign;
- Pareto-optimal within evaluated campaign candidates;
- no further unique candidate under configured mutation policy;

not:

- globally optimal material;
- best possible material;
- solved chemistry.

## 1.5 Optimization cannot escape the Phase-3 search space

Autonomous mutation may modify only:

- components already declared mutable;
- curator-approved substitution alternatives;
- configured amount ranges/step sizes;
- configured balance/normalisation rules;
- configured process parameter ranges.

No LLM or optimizer may introduce an undeclared chemical/component identity.

Redacted content remains non-inferable.

## 1.6 Every autonomous decision must be explainable

For every selected/rejected/parent/mutated candidate, preserve:

- campaign/iteration;
- input prediction IDs;
- model versions;
- objective values/intervals;
- hard-constraint posture;
- Pareto rank;
- acquisition/selection components;
- policy/version;
- random seed if any;
- rationale;
- parent/child lineage;
- checksums.

No opaque `AI score` is allowed.

## 1.7 Determinism is the default

The same immutable:

- project specification checksum;
- search-space checksum/version;
- campaign policy/version;
- objective definitions;
- pinned model versions;
- candidate pool;
- seed;
- budget

must reproduce the same ordered decisions/fingerprints for deterministic policies.

## 1.8 Model applicability limits campaign applicability

If the models needed to evaluate a campaign objective/constraint are inapplicable to a candidate, the campaign must record that limitation.

Do not extrapolate a model merely because optimization requires a number.

## 1.9 Multi-objective means explicit trade-offs

Do not collapse multiple objectives into a single unexplained score.

The primary Phase-5 presentation should expose:

- objective vectors;
- intervals;
- Pareto front/rank;
- feasibility class;
- optional transparent normalized utility components where a policy needs tie-breaking.

## 1.10 Physical experimentation is deferred

Phase 5 may create a future-facing `recommended_for_validation` decision state, but it must **not** create hazardous protocols, lab requests, robotics commands or experimental results.

The physical closed loop belongs to Phase 9.

---

# 2. PRESERVE THE ACTUAL PHASE-4 ARCHITECTURE

Do not replace:

- FastAPI/Pydantic/SQLAlchemy/Alembic modular monolith;
- PostgreSQL target;
- unit service;
- Phase-2 knowledge/evidence graph;
- observation selection/conflict policy;
- replacement-specification compiler/checksum;
- Phase-3 CandidateSearchSpace, CandidateHypothesis, fingerprinting, lineage and generation runs;
- Phase-4 PredictionModel/Version, applicability, feature snapshots, prediction runs/results and uncertainty logic;
- Candidate Lab and Prediction Lab;
- privacy scoping seams.

Add a logical `experiments` or `optimization` module inside the modular monolith.

No Kubernetes or microservice decomposition.

---

# 3. PHASE-5 DOMAIN MODEL — FORWARD `0005`

Add:

`0005_virtual_experiment_brain.py`

Do not modify `0001`-`0004`.

The exact names may improve if justified, but the following concepts are required.

## 3.1 VirtualExperimentCampaign

A versioned/auditable project-scoped optimization campaign.

Suggested fields:

- id;
- organisation_id;
- project_id;
- name;
- description;
- replacement_specification_checksum;
- search_space_id;
- search_space_version;
- search_space_checksum;
- policy_key;
- policy_version;
- configuration checksum;
- random seed;
- max_iterations;
- max_total_new_candidates;
- max_candidates_per_iteration;
- status;
- stop_reason nullable;
- created_by;
- started_at;
- completed_at;
- result checksum;
- metadata;
- created_at.

Status:

- draft;
- ready;
- running;
- completed;
- stopped;
- failed;
- cancelled.

Do not use `validated`, `discovered`, or `proven` as campaign status.

## 3.2 CampaignObjective

Typed objective definition.

Fields:

- campaign_id;
- property_key;
- direction (`maximize | minimize | target`);
- weight;
- priority;
- target value/unit nullable;
- model_version_id;
- evaluation mode/policy;
- sequence.

Every objective requiring a model must pin an immutable approved Phase-4 model version.

## 3.3 CampaignConstraintModelPolicy

The project already owns constraints. Campaign configuration should map property constraints to evaluation sources without copying/redefining their scientific meaning.

Support:

- project constraint id;
- pinned model version id if prediction fallback is required;
- allowed value origin (`known_evidence`, `model_prediction`, or explicit hierarchy);
- UNKNOWN handling policy;
- condition mapping;
- enabled flag.

Do not silently choose arbitrary latest models.

## 3.4 CampaignIteration

Immutable iteration record.

Suggested fields:

- id;
- campaign_id;
- iteration_number;
- input_pool_checksum;
- parent_selection_checksum;
- generation_run_ids;
- prediction_run_ids;
- evaluated_candidate_count;
- feasible_count;
- uncertain_count;
- infeasible_count;
- pareto_front_count;
- pareto_front_checksum;
- selected_for_exploration_count;
- new_candidate_count;
- duplicate_count;
- decision checksum;
- status;
- started/completed timestamps;
- stop signal/reason nullable;
- metadata.

Unique `(campaign_id, iteration_number)`.

## 3.5 VirtualCandidateEvaluation

One auditable decision record per candidate/iteration.

Suggested fields:

- id;
- campaign_iteration_id;
- candidate_id / hypothesis_id;
- feasibility class;
- hard-pass count;
- hard-fail count;
- hard-unknown count;
- objective vector payload;
- objective interval payload;
- objective origin/model IDs;
- Pareto rank nullable;
- dominance count;
- crowding/diversity metric nullable if used;
- uncertainty burden/components;
- normalized utility components nullable;
- acquisition components;
- selected_as_parent bool;
- selected_for_next_evaluation bool;
- disposition;
- rationale;
- deterministic evaluation checksum.

Keep typed top-level decision fields; JSON is acceptable for variable-size objective vectors/components.

## 3.6 ParetoFrontSnapshot

Recommended if it improves auditability.

Fields may include:

- iteration id;
- rank/front number;
- ordered candidate IDs;
- objective-space checksum;
- policy/version;
- created_at.

Do not rely only on a transient API calculation if campaign history needs to be reproducible.

## 3.7 OptimizationDecisionRecord

Every policy decision should be inspectable.

Change/decision types may include:

- initial_pool_selected;
- robustly_infeasible;
- retained_unknown_for_exploration;
- pareto_front_selected;
- parent_selected;
- mutation_generated;
- duplicate_rejected;
- applicability_rejected;
- budget_stop;
- convergence_stop;
- no_unique_candidate_stop.

Store:

- campaign/iteration;
- candidate/hypothesis nullable;
- sequence;
- decision type;
- policy key/version;
- input checksum;
- metrics/components;
- rationale.

## 3.8 CampaignRunEnvelope

The campaign itself can serve as the run envelope if fields are sufficient. It must pin all mutable external scientific semantics that could otherwise change:

- replacement-spec checksum;
- search-space checksum;
- objective definitions checksum;
- constraint-model policy checksum;
- model version IDs/artifact checksums;
- optimization policy/version;
- seed/budgets;
- canonicalization versions.

Historical campaign execution must remain interpretable if newer model/policy versions appear later.

---

# 4. OPTIMIZATION POLICY CONTRACT

Create an explicitly registered policy interface.

Conceptually:

```python
class VirtualExperimentPolicy(Protocol):
    key: str
    version: str

    def validate_campaign(...): ...
    def evaluate_pool(...): ...
    def pareto_rank(...): ...
    def select_parents(...): ...
    def propose_mutations(...): ...
    def should_stop(...): ...
```

Each policy declares:

- deterministic/stochastic behavior;
- supported objective directions;
- minimum/maximum objective count;
- uncertainty semantics;
- UNKNOWN handling;
- maximum safe candidate pool;
- maximum parents/children;
- reproducibility contract.

Policies must be code-registered, not loaded from arbitrary user code.

---

# 5. REQUIRED PHASE-5 POLICIES

Implement a small number of transparent policies.

## 5.1 `robust_pareto_v1`

This should be the primary policy.

### Feasibility

Classify each candidate using existing project hard constraints plus explicitly pinned evidence/prediction policies:

1. `robustly_feasible` — all required hard constraints are known and wholly satisfied under uncertainty;
2. `uncertain` — no hard failure, but at least one hard constraint is UNKNOWN or interval-crossing;
3. `robustly_infeasible` — at least one hard constraint wholly fails.

Never classify UNKNOWN as feasible.

### Objective value used for robust ranking

For model predictions:

- maximize objective: conservative value = lower interval bound;
- minimize objective: conservative value = upper interval bound;
- target objective: use transparent distance interval to target.

Also retain point and full interval.

Do not discard point estimate; simply distinguish `point` from `conservative_decision_value`.

### Pareto ranking

Perform deterministic non-dominated sorting over the conservative objective vectors among comparable candidates.

Candidates with missing/inapplicable objective values cannot be silently placed on the normal Pareto front. Put them in an explicit incomplete/uncertain posture.

Use stable candidate fingerprint/id tie-breakers.

### Parent selection

Prioritize:

1. robustly feasible Pareto front;
2. uncertain front where exploration is configured;
3. lower Pareto ranks if parent budget remains.

Expose all tie-break components.

## 5.2 `uncertainty_exploration_v1`

Provide a second transparent policy for selecting uncertain-but-promising candidates.

This is **experiment selection**, not model retraining yet.

A defensible approach:

- reject robust hard failures;
- require applicable predictions for configured objective properties;
- quantify normalized interval width per objective;
- expose uncertainty burden vector;
- prioritize candidates that combine non-dominated/near-front performance with high uncertainty;
- record exact formula/components.

Do not call the output “information gain” unless you actually calculate a valid information-theoretic quantity.

`uncertainty_priority` is safer terminology.

## 5.3 Deterministic baseline policy

Implement a simple deterministic baseline such as:

`lexicographic_pareto_baseline_v1`

Use it to test the campaign substrate independently of exploration heuristics.

No opaque weighted AI score.

---

# 6. MULTI-OBJECTIVE VALUE MODEL

Create a typed internal representation such as:

```text
ObjectiveValue
  property
  direction
  origin
  point
  lower
  upper
  unit
  applicability
  model_version
  conservative_value
  completeness
```

Requirements:

- unit canonicalization before comparison;
- explicit model version;
- explicit origin;
- interval mandatory for Phase-4 predictions;
- no ungrounded value filling;
- target objective handled separately from maximize/minimize.

Do not compare incompatible units.

---

# 7. DEMO MULTI-OBJECTIVE SUPPORT

The current Phase-4 seed contains one transparent synthetic tensile-strength predictor.

To exercise multi-objective infrastructure, Phase 5 may seed **one additional transparent DEMO-ONLY density predictor** using the existing Phase-4 registry/artifact contracts.

Rules:

- same safe JSON artifact approach;
- separate immutable model/version/artifact checksum;
- deterministic synthetic coefficients;
- synthetic validation/calibration fixture;
- explicit applicability ranges;
- mandatory uncertainty;
- same exact DEMO MODEL warning;
- no claim that coefficients describe real polymer chemistry;
- do not train/download a real model just to make the demo look impressive.

This allows a synthetic campaign such as:

- maximize tensile strength;
- minimize density;

while satisfying existing hard constraints.

If adding this model exposes a Phase-4 registry defect, fix the registry generically rather than special-casing density.

---

# 8. INITIAL CANDIDATE POOL

A campaign must start from an explicit pool.

Supported sources:

- existing Phase-3 hypothesis candidates in the project;
- a bounded fresh Phase-3 generation run;
- selected known materials as non-mutating references if useful.

For autonomous mutation, use only hypothesis candidates with concrete non-redacted mutable state.

Record the initial ordered pool checksum.

Do not silently include every material in the global database.

---

# 9. PREDICTION ORCHESTRATION INSIDE CAMPAIGNS

Campaigns must reuse Phase-4 services rather than reimplementing inference.

For each iteration/property:

1. resolve candidate targets;
2. use the pinned model version;
3. preview applicability where needed;
4. create bounded Phase-4 PredictionRun(s);
5. persist prediction IDs/run IDs in the iteration;
6. feed complete intervals into optimization.

Do not directly call demo coefficients from the optimizer.

Respect Phase-4 hard maximum 200 targets/run. If an iteration pool is larger, chunk deterministically into bounded prediction runs and record the ordered run list/checksum.

Do not create predictions for properties not requested by the campaign.

---

# 10. AUTONOMOUS MUTATION ENGINE

Phase 5 may extend generation beyond baseline-only variations by mutating selected **hypothesis parents**, but it must use Phase-3 search-space semantics.

Implement an explicit `HypothesisMutationStrategy` or equivalent.

Allowed mutation operations:

- one configured mutable component amount +/- configured step;
- one curator-approved component substitution;
- one configured process parameter +/- configured step;
- deterministic balance-component compensation when configured.

Optional multi-change mutation may be supported only if bounded and explicitly configured.

Every child must:

- pass Phase-3 structural validation;
- receive a `candidate-v1` fingerprint (or new version only if scientifically necessary and documented);
- deduplicate against project/campaign candidates;
- receive parent hypothesis lineage;
- receive typed `CandidateChangeRecord` entries;
- record campaign/iteration decision provenance;
- remain a `CandidateHypothesis`, not a `Material`;
- receive no inherited properties.

Mutation cannot introduce a component absent from approved rules/search space.

---

# 11. ITERATIVE CAMPAIGN LOOP

A bounded synchronous Phase-5 campaign may conceptually execute:

```text
snapshot campaign inputs
        ↓
initial candidate pool
        ↓
predict required properties with uncertainty
        ↓
robust hard-constraint classification
        ↓
objective vectors
        ↓
Pareto ranking
        ↓
parent / exploration selection
        ↓
bounded search-space mutation
        ↓
deduplicate + structural pre-screen
        ↓
next iteration
        ↓
stop condition
```

Do not silently retrain prediction models between iterations.

Model learning belongs to a later closed-loop phase once experimental outcomes exist.

---

# 12. STOP CONDITIONS

Campaigns must have explicit bounded stop semantics.

Support at least:

- maximum iterations reached;
- total new-candidate budget reached;
- no structurally valid unique child generated;
- no applicable model predictions for required objectives;
- no eligible parent candidate;
- user cancellation;
- repeated Pareto-front checksum/convergence policy if configured.

If implementing convergence:

- make it deterministic;
- require a documented number of unchanged iterations;
- do not call it global convergence;
- record the exact front/checksum comparison.

---

# 13. EXPLOSION PROTECTION

Phase 5 must remain safe locally.

Suggested limits:

- max 5 iterations per synchronous campaign execution;
- max 200 evaluated targets per prediction batch (reuse Phase 4);
- max 100 parents/iteration;
- max 200 new hypotheses/iteration;
- max 500 new hypotheses/campaign;
- reject campaign configurations whose estimated mutation cardinality is unbounded/extreme;
- deduplicate before expensive prediction execution.

Choose defensible exact constants and document them.

No distributed queue is required in Phase 5.

---

# 14. REPRODUCIBILITY

Create canonical checksums for:

## Campaign configuration

Includes:

- specification checksum;
- search-space checksum/version;
- ordered objective definitions;
- model version IDs + artifact checksums;
- constraint prediction policy;
- optimization policy key/version;
- seed;
- budgets;
- mutation configuration;
- canonicalization versions.

## Iteration input

Includes:

- ordered candidate fingerprints;
- previous iteration checksum;
- pinned prediction model/configuration;
- iteration number.

## Evaluation

Includes:

- candidate fingerprint;
- prediction result checksums;
- feasibility classification;
- objective vector/intervals;
- Pareto rank;
- acquisition components;
- policy version.

## Iteration decision

Includes ordered selected parent IDs, new child fingerprints and stop signal.

## Campaign result

Includes ordered iteration result checksums and final front fingerprint/checksum.

Tests must prove replay determinism for the synthetic fixture.

---

# 15. API REQUIREMENTS

Exact URLs may improve, but implement equivalent capabilities.

## Campaign configuration

- create draft campaign;
- get/list project campaigns;
- add/update objectives while draft;
- map/pin model versions;
- configure budgets/policy/seed;
- validate campaign;
- clone campaign configuration rather than mutating a completed campaign.

Examples:

`POST /replacement-projects/{id}/virtual-campaigns`

`GET /replacement-projects/{id}/virtual-campaigns`

`GET /virtual-campaigns/{id}`

## Preview

`POST /virtual-campaigns/{id}/preview`

Return without campaign execution persistence:

- config validity;
- specification/search-space checksums;
- candidate pool size;
- objective/model mappings;
- applicability forecast/counts;
- estimated prediction executions;
- estimated mutation cardinality;
- budgets;
- policy/version;
- validation issues.

Preview must not create iterations, predictions or hypotheses.

## Execute one iteration

`POST /virtual-campaigns/{id}/iterations`

This is useful for audit/debug/control.

## Execute bounded campaign

`POST /virtual-campaigns/{id}/run`

May execute multiple iterations synchronously up to hard Phase-5 limits.

Do not hide individual iteration records.

## Iteration

- get iteration detail;
- get paginated candidate evaluations;
- get Pareto front;
- get decision records;
- get created children/lineage.

## Candidate campaign history

- show campaigns/iterations that evaluated a hypothesis;
- expose its objective vector, feasibility, Pareto rank and selection decisions.

## Reproducibility

Expose campaign/iteration/checksum envelope without exposing private raw composition unnecessarily.

---

# 16. UI — VIRTUAL EXPERIMENT LAB

Add a serious engineering workspace named **Virtual Experiment Lab** or **Optimization Lab**.

Do not make it look like a game, casino, magic AI assistant or animated chemistry oracle.

## 16.1 Campaign overview

Show:

- project/baseline;
- replacement specification checksum;
- search-space version/checksum;
- campaign status;
- policy/version;
- random seed;
- iteration/candidate budgets;
- objective count;
- model versions;
- latest iteration;
- stop reason.

Prominent label:

> Virtual evaluations are model-based. They are not physical experiments or physics simulations.

## 16.2 Campaign Builder

Configure:

- candidate pool source;
- objective property/direction/weight/priority;
- pinned approved model version per objective;
- project hard-constraint prediction policy;
- policy (`robust_pareto_v1`, etc.);
- exploration setting;
- mutation types;
- max iterations;
- parent/child/campaign budgets;
- seed.

Do not allow unsupported model/property/family combinations.

## 16.3 Preview

Show before execution:

- applicability matrix/counts;
- objective model readiness;
- unknown constraint coverage;
- estimated prediction runs/batches;
- mutation cardinality;
- budget truncation;
- checksums;
- warnings/errors.

Preview does not create virtual evaluation rows, prediction runs or candidates.

## 16.4 Iteration view

Show:

- evaluated pool;
- robust feasible / uncertain / infeasible counts;
- Pareto front count;
- objective ranges;
- prediction runs used;
- selected parent candidates;
- generated/duplicate/rejected children;
- iteration checksums;
- stop signal.

## 16.5 Pareto explorer

For two objectives, add a useful 2D scatter plot if practical.

Requirements:

- x/y objectives labelled with units;
- point estimates visible;
- uncertainty intervals/error bars if practical;
- feasibility visually distinguished with labels, not color alone;
- front/rank inspectable;
- selected parents marked;
- no fake AI score.

For >2 objectives, provide table/rank/objective-vector view rather than forcing a misleading chart.

## 16.6 Candidate evaluation detail

Show:

- candidate/hypothesis link;
- virtual-evaluation warning;
- all objective values/intervals;
- conservative decision value;
- hard-constraint posture;
- prediction IDs/model versions;
- Pareto rank/dominance;
- exploration/utility components;
- decision rationale;
- parent/child campaign lineage;
- evaluation checksum.

## 16.7 Campaign lineage

Show a simple iteration tree/timeline:

`Initial hypotheses -> evaluated -> selected parents -> bounded mutations -> iteration 2 ...`

Reuse Phase-3 lineage rather than creating a disconnected lineage system.

---

# 17. SEEDED PHASE-5 DEMONSTRATION

Extend only the existing **synthetic generic polymer** fixture.

Seed deterministically:

- one additional synthetic DEMO-ONLY density model/version if needed for multi-objective demonstration;
- one draft/ready or completed virtual campaign;
- objectives:
  - maximize synthetic tensile-strength prediction;
  - minimize synthetic density prediction;
- explicit model-version pins;
- `robust_pareto_v1`;
- small max iteration/candidate budgets;
- at least 2 iterations if enough unique valid children exist;
- candidate outcomes including:
  - robustly feasible;
  - uncertain due to interval crossing/UNKNOWN constraint;
  - robustly infeasible;
  - inapplicable candidate;
- at least one Pareto front with more than one trade-off candidate;
- at least one parent-selected child with Phase-3 lineage/change provenance;
- at least one duplicate rejected/countable;
- deterministic final campaign checksum.

Every demo model and virtual-evaluation UI/API record must state synthetic/demo-only status.

Do not introduce unsourced real chemical claims.

Seed twice must be idempotent.

---

# 18. PRIVACY / MULTI-TENANT SEAMS

Maintain Phase-4 scoping.

At minimum:

- campaigns are organisation/project scoped;
- objective/model mapping cannot reference another tenant's private model;
- candidate pool cannot include another organisation's private materials/hypotheses;
- predictions remain scoped;
- campaign evaluations/decision records are scoped;
- lineage must not leak private parents;
- campaign checksums/fingerprints are one-way hashes and must not encode reversible secret content;
- logs must not emit raw formulations, feature vectors or model artifacts.

`X-Organisation-ID` remains a development scoping seam, not production auth.

---

# 19. PERFORMANCE

Create a bounded profile such as:

- 200 candidate hypotheses;
- 2 objective models;
- one campaign iteration;
- Phase-4 predictions chunked/batched correctly;
- Pareto ranking;
- parent selection;
- bounded child generation;
- paginated evaluation retrieval.

Document:

- SELECT query shape/count;
- prediction batch count;
- number of candidates evaluated;
- number of Pareto operations/comparisons if useful;
- child persistence counts;
- no query-per-candidate-property pattern;
- no repeated model artifact load per target.

Do not publish arbitrary production latency from SQLite/synthetic models.

Prefer algorithmic sanity: Pareto ranking should be acceptable for Phase-5 bounded pools. If using O(n²) nondominated sorting, document the bounded maximum and why it is acceptable in this phase.

---

# 20. TESTING

Keep **all 82 Phase-1/2/3/4 backend tests green** and substantially extend coverage.

## 20.1 Migration

- `0004` data survives `0005`;
- material/candidate/hypothesis/prediction IDs unchanged;
- campaign constraints/indexes exist;
- downgrade behavior documented on disposable data.

## 20.2 Campaign validation

- missing objective model rejected;
- unsupported model/property rejected;
- non-approved/retired model rejected;
- search-space checksum mismatch rejected;
- project/spec checksum mismatch detected;
- invalid budgets rejected;
- campaign cannot escape organisation scope;
- impossible objective units rejected.

## 20.3 Feasibility semantics

- all hard constraints interval-safe PASS -> robustly feasible;
- one hard FAIL -> robustly infeasible;
- interval crossing -> uncertain;
- missing/OOD -> uncertain, never pass;
- evidence/prediction origin preserved.

## 20.4 Pareto

- deterministic non-dominated sorting;
- known toy fronts exactly correct;
- maximize/minimize directions correct;
- unit normalization correct;
- dominated candidates ranked lower;
- tie handling stable;
- incomplete objective values excluded/labelled, not silently imputed.

## 20.5 Uncertainty-aware policy

- maximize uses lower bound for conservative value;
- minimize uses upper bound;
- uncertainty components visible;
- robust-Pareto selection deterministic;
- uncertainty-exploration policy excludes hard failures;
- no opaque overall AI score generated.

## 20.6 Mutation

- parent hypothesis required;
- only mutable search-space dimensions change;
- locked components unchanged;
- substitution must be approved;
- component bounds respected;
- process bounds respected;
- balance/total maintained;
- redacted baseline/hypothesis content not guessed;
- child fingerprint deterministic;
- duplicate detected;
- child lineage/change records point to parent and campaign iteration;
- no Material record automatically created;
- no property observations inherited.

## 20.7 Campaign loop

- bounded iteration count;
- candidate budget enforced;
- one-iteration execution auditable;
- multi-iteration deterministic replay;
- no unique child -> explicit stop;
- no applicable predictions -> explicit stop;
- max budget -> explicit stop;
- campaign checksum deterministic;
- meaningful configuration change changes checksum.

## 20.8 Phase-4 regression

Mandatory:

- campaign prediction orchestration uses Phase-4 `PropertyPrediction` records;
- no direct coefficient access in optimizer;
- virtual evaluation creates zero `MaterialPropertyObservation` rows;
- inapplicable prediction remains numberless;
- demo warning retained;
- interval uncertainty retained in evaluation records.

## 20.9 API

Cover create/configure/validate/preview/execute/list/detail/iteration/evaluation/Pareto/history/reproducibility/privacy.

Preview must prove zero iteration/prediction/candidate persistence.

## 20.10 Frontend

Test at least:

- virtual-evaluation warning;
- campaign preview does not execute;
- objective/model validation;
- robust feasible/uncertain/infeasible labels;
- Pareto data rendering;
- uncertainty intervals;
- selected-parent rationale;
- stop reason;
- no “validated material” language;
- no fake AI score.

---

# 21. OBSERVABILITY

Add structured campaign/iteration events containing only non-secret metadata:

- request/correlation ID;
- campaign ID;
- iteration ID/number;
- project ID;
- policy/version;
- spec/search-space checksum prefixes;
- model-version IDs;
- candidate/evaluated/feasible/uncertain/infeasible counts;
- prediction run IDs/count;
- parent/child/duplicate counts;
- Pareto-front count;
- stop reason;
- duration;
- failure code.

Never log full private compositions/features/model artifacts.

---

# 22. DOCUMENTATION

Create/update at minimum:

- `README.md`;
- `docs/ARCHITECTURE.md`;
- `docs/DOMAIN_MODEL.md`;
- `docs/ERD.md`;
- `docs/PHASE4_STABILIZATION_FOR_PHASE5.md`;
- `docs/PHASE5_SCOPE.md`;
- `docs/VIRTUAL_EXPERIMENT_MODEL.md`;
- `docs/OPTIMIZATION_POLICY_CONTRACT.md`;
- `docs/MULTIOBJECTIVE_PARETO.md`;
- `docs/UNCERTAINTY_AWARE_OPTIMIZATION.md`;
- `docs/CAMPAIGN_REPRODUCIBILITY.md`;
- `docs/CAMPAIGN_STOP_CONDITIONS.md`;
- `docs/SCIENTIFIC_INTEGRITY.md`;
- `docs/PRIVACY_MODEL.md`;
- `docs/FUTURE_ARCHITECTURE.md`.

Document exact formulas/ranking/tie-breaking. Do not hide them behind “AI optimization”.

---

# 23. EXPLICITLY DO NOT IMPLEMENT IN PHASE 5

Do not implement:

- DFT;
- Quantum ESPRESSO;
- LAMMPS / molecular dynamics;
- ML force fields;
- CALPHAD;
- finite-element physics;
- HPC scheduler;
- physics-based simulation claims;
- physical lab requests/execution;
- autonomous synthesis;
- hazardous recipes;
- robotics;
- model retraining from experimental data;
- online active-learning model updates;
- patent/novelty search;
- supplier/economic/manufacturing scoring beyond existing data contracts;
- reinforcement-learning agents;
- LLM chemistry invention;
- arbitrary external model downloads;
- vector database unless separately justified;
- Kubernetes/microservice decomposition;
- production SSO/billing unless required to repair a P0 security issue.

Phase 6 is the Physics & Simulation OS. Do not consume it early.

---

# 24. REQUIRED PHASE-5 QUALITY CHECK

Before declaring Phase 5 complete:

1. Clean Docker Compose boot.
2. Real PostgreSQL migrations through `0005`.
3. Prove Phase-4 data migration integrity.
4. Seed twice/idempotency.
5. Run all backend tests.
6. Run Ruff.
7. Run Mypy.
8. Confirm Pint runtime.
9. Run frontend tests.
10. Full TypeScript typecheck.
11. ESLint.
12. Next production build.
13. Browser smoke.
14. Create campaign.
15. Validate objectives/model mappings.
16. Preview and prove zero persistence.
17. Execute one bounded iteration.
18. Inspect prediction runs used.
19. Verify uncertainty survives into objective vectors.
20. Verify hard interval-crossing -> campaign uncertain.
21. Inspect Pareto front and known toy correctness tests.
22. Verify selected-parent rationale/components.
23. Generate child from a parent and inspect Phase-3 lineage/change records.
24. Confirm no canonical Material is created.
25. Confirm no observations are inherited/created.
26. Execute bounded multi-iteration campaign.
27. Re-run same envelope and prove deterministic decisions/checksums.
28. Change objective/model/seed and prove intended checksum/result differences.
29. Trigger at least three stop conditions in tests.
30. Verify private campaign data cannot be read unscoped.
31. Profile 200-candidate / 2-objective query/inference shape.
32. Check browser console/responsive behavior.
33. Remove caches/debug/generated junk.
34. Update docs truthfully.

Never mark an unavailable/unexecuted check PASS.

---

# 25. PHASE-5 ACCEPTANCE CRITERIA

Phase 5 is complete only if:

- Phase-4 stabilization gate is completed on real dependencies;
- `0005` forward migration works;
- campaign/objective/iteration/evaluation models exist;
- campaigns pin immutable spec/search-space/model/policy semantics;
- virtual evaluations remain separate from physical/experimental evidence;
- uncertainty is preserved through all optimization decisions;
- robust feasibility distinguishes feasible/uncertain/infeasible;
- deterministic Pareto ranking works;
- at least two transparent policies are implemented and versioned;
- campaign preview is zero-persistence;
- bounded Phase-4 prediction orchestration is reused;
- optimizer never accesses model coefficients directly;
- parent-selected mutation remains within Phase-3 search space;
- child hypotheses preserve fingerprint/lineage/change provenance;
- no candidate property is fabricated/inherited;
- duplicate/new-candidate budgets are explicit;
- deterministic campaign replay works;
- stop reasons are explicit/auditable;
- privacy scope is maintained;
- Virtual Experiment Lab is usable/auditable;
- all tests/lint/typecheck/build pass in a normal environment;
- documentation matches the actual implementation.

---

# 26. FINAL DELIVERY

Return a clean ZIP of the complete Phase-5 repository.

Exclude:

- `node_modules`;
- virtual environments;
- `.next`;
- test SQLite databases;
- caches;
- debug dumps;
- local secrets;
- unnecessary large model artifacts/binaries.

Provide a detailed implementation report containing:

## Phase-4 stabilization

Exact checks/fixes/results.

## Implemented

Actual Phase-5 functionality.

## Campaign architecture

Campaign/objective/iteration/evaluation/decision design.

## Optimization policies

Exact algorithms/formulas/tie-breaking and limitations.

## Uncertainty handling

How intervals affect feasibility, Pareto values and exploration.

## Autonomous mutation

How search-space boundaries, lineage, fingerprints and deduplication are preserved.

## Scientific integrity

How virtual evaluation remains distinct from evidence/physics/lab validation.

## Reproducibility

All campaign/iteration/evaluation checksums plus deterministic replay proof.

## Database

`0005` changes.

## Tests

Exact counts/results.

## Performance profile

200-candidate / 2-objective query/inference/Pareto shape without false latency claims.

## Privacy/security

Scope and known limitations.

## Known limitations

Especially synthetic demo models and lack of physics/physical validation.

## Deferred to Phase 6+

List everything deliberately postponed.

## Run commands

Exact clean-machine commands.

## Verification checklist

Every acceptance item PASS / FAIL / UNVERIFIED with explanation.

Do not claim PASS without execution.

---

# 27. STOP CONDITION

At the end of Phase 5, **STOP**.

Do not implement Phase 6 automatically.

The completed package must be audited first. Phase 6 will introduce the **Physics & Simulation OS** (simulation routing, reproducible scientific-compute workflows, ML force-field/DFT/MD/CALPHAD adapter boundaries where scientifically appropriate), and its design must depend on the actual Phase-5 campaign/evaluation contracts rather than assumptions.
