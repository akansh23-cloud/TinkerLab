# TinkerLab — Phase 6 Implementation Prompt

## Physics & Simulation Operating System

You are continuing the **actual TinkerLab Phase-5 repository**. Do not rebuild the product from scratch, replace the scientific domain model, flatten the evidence/prediction/campaign distinctions, or start a generic “AI scientist” architecture.

You are acting as the founding Principal Engineer, Scientific Software Architect, Computational Materials Architect, HPC/Scientific Workflow Architect, Product Architect and senior full-stack engineer for TinkerLab.

TinkerLab is a closed-loop **Material Replacement & Discovery Operating System**.

# THIS IS PHASE 6 ONLY

Phase 6 introduces a trustworthy **Physics & Simulation Operating System** on top of the actual Phase-5 candidate, prediction and campaign contracts.

The goal is not to run every physics method for every material. The goal is to create the production-grade substrate that can:

> Take a known material or candidate hypothesis that has an adequate scientific representation, determine whether an available simulation method/provider is scientifically applicable, build a reproducible bounded workflow, execute only reviewed provider commands, preserve complete input/toolchain/artifact/convergence provenance, parse results into a separate simulation-result origin, and refuse cleanly when the requested computation is not scientifically or operationally supported.

A Phase-6 simulation result is **not experimental evidence** and is **not an ML prediction**.

Do not implement physical laboratory automation, synthesis procedures, robotics, patent search, novelty claims, industrial cost/supply/manufacturing scoring, or model retraining in Phase 6.

---

# 0. MANDATORY PHASE-5 STABILIZATION GATE

Before implementing any Phase-6 physics functionality, run the actual Phase-5 artifact on a normal dependency-enabled/Docker-enabled machine.

The supplied Phase-5 artifact already passed in the artifact sandbox:

- **108/108 backend tests**;
- Python application/Alembic compilation;
- PostgreSQL-dialect Alembic static generation through `0005` (**1,295 lines**);
- **41 TypeScript/TSX source/config/test files with 0 parser diagnostics**;
- deterministic two-iteration synthetic virtual campaign;
- 200-candidate / 2-objective profile:
  - preview: 49 SELECTs;
  - iteration execution: 76 SELECTs;
  - 100-evaluation page: 2 SELECTs;
  - exactly 2 Phase-4 prediction batches for 200 targets;
  - O(n²) Pareto sorting bounded to 19,900 pair checks.

The original sandbox did **not** provide Docker, live PostgreSQL, Pint, Ruff, Mypy or installed frontend dependencies.

## 0.1 Docker / live PostgreSQL

From a clean checkout:

1. `docker compose up --build`.
2. Apply `0001 -> 0002 -> 0003 -> 0004 -> 0005` on real PostgreSQL.
3. Seed twice and prove idempotency.
4. Restart API/web/PostgreSQL and prove persistence.
5. Create a disposable Phase-4 data snapshot and upgrade `0004 -> 0005`.
6. Confirm all material/candidate/hypothesis/prediction IDs survive.
7. Confirm Phase-5 campaign tables/indexes/constraints exist.
8. Exercise `0005` downgrade only on disposable data and document that campaign history is removed while Phase-1–4 data survives.
9. Confirm the explicit short `virtual_candidate_evaluations` index names work on PostgreSQL.
10. Do **not** edit migrations `0001`–`0005`.
11. Phase 6 must add a forward `0006_physics_simulation_os.py` migration.

## 0.2 Scientific unit/runtime gate

Install declared Python dependencies and prove Pint-backed unit handling for all existing units plus any simulation units introduced in Phase 6.

At minimum test:

- energy: eV, J, kJ/mol where semantically appropriate;
- length: angstrom, nm, m;
- pressure/stress: Pa, MPa, GPa;
- temperature including offset conversion;
- time: fs, ps, s where appropriate;
- force: eV/angstrom or a canonical equivalent where the unit library supports it;
- density;
- incompatible-unit rejection.

Never manually reinterpret dimensions simply to make a solver output fit a property definition.

## 0.3 Backend quality

Run and fix root causes:

```bash
cd apps/api
pytest -q
ruff check .
mypy app
```

Do not globally suppress lint/type errors.

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

Browser-smoke all Phase-1 through Phase-5 workflows, especially:

- Materials Explorer / Passport;
- Candidate Lab;
- Prediction Lab;
- Virtual Experiment Lab;
- campaign preview/run/iteration/Pareto/lineage;
- tenant-scoping header behavior;
- browser console/network errors;
- responsive behavior.

## 0.5 Phase-5 scientific regression

Explicitly prove before Phase 6:

- virtual evaluation remains separate from observations;
- optimizer consumes Phase-4 `PropertyPrediction` records rather than coefficients;
- uncertainty survives campaign evaluation;
- UNKNOWN never becomes hard PASS;
- campaign mutation remains inside the Phase-3 search space;
- children remain `CandidateHypothesis` records;
- no campaign-created `MaterialPropertyObservation` exists;
- deterministic campaign replay still works;
- private campaign/model/hypothesis data is not exposed unscoped.

## 0.6 Stabilization output

Create:

`docs/PHASE5_STABILIZATION_FOR_PHASE6.md`

Record exact PASS / FAIL / UNVERIFIED results and every stabilization repair.

Do not start new physics implementation while a P0/P1 stabilization defect remains unresolved.

---

# 1. NON-NEGOTIABLE SCIENTIFIC PRINCIPLES

## 1.1 Prediction, simulation and experiment are three different origins

TinkerLab now has at least three distinct scientific postures:

1. `KNOWN EVIDENCE` / `MaterialPropertyObservation`;
2. `MODEL PREDICTION` / `PropertyPrediction`;
3. `PHYSICS SIMULATION` / new Phase-6 simulation result.

Never silently convert one into another.

A simulation result must not automatically create an experimental/literature/supplier observation.

The UI/API must visually and structurally distinguish:

- known evidence;
- model prediction;
- physics simulation;
- unknown.

## 1.2 A simulation is valid only if the target representation is adequate

A formulation name such as:

`Base Resin A + Modifier B2 + Reinforcement C`

is **not enough information** to run DFT or molecular dynamics.

Before routing a simulation, require the scientifically necessary representation for that method, for example:

- periodic crystal structure for many solid-state DFT workflows;
- atomistic coordinates + topology/force-field mapping for atomistic MD;
- phase/component/thermodynamic description for CALPHAD;
- mesh/material constitutive model/boundary conditions for continuum/FEA later.

If a representation is absent, incomplete, redacted or incompatible, return `not_applicable` / `incomplete_representation`. Do not infer atoms, topology, force fields, phases or boundary conditions.

## 1.3 The simulation router must be conservative

The router may propose only scientifically declared routes.

Examples:

- crystalline periodic target + supported energy/stability purpose -> DFT-like route may be eligible;
- atomistic topology + supported potential -> MD route may be eligible;
- formulation-only generic polymer -> DFT route must be rejected;
- no supported provider -> `provider_unavailable`, not a fake calculation.

Do not use an LLM to decide scientific applicability.

## 1.4 A completed process is not necessarily a scientifically converged simulation

Separate operational state from scientific result state.

Examples:

- process exit code 0 but SCF not converged -> simulation is scientifically unconverged;
- MD process completes but target equilibration/convergence criterion fails -> result is not accepted as converged;
- parser failure -> no parsed property estimate;
- resource timeout -> failed attempt, not UNKNOWN physics value.

Never produce a property number simply because a command completed.

## 1.5 Every solver/provider/version is immutable and reproducible

Persist enough provenance to reproduce or audit:

- provider key/version;
- method/fidelity;
- executable version;
- executable checksum/container image digest where available;
- code-defined command template version;
- input template checksum;
- target representation checksum;
- parameter checksum;
- pseudopotential/force-field/thermodynamic database checksums where applicable;
- environment/toolchain metadata;
- resource request;
- exact normalized input snapshot;
- parser version;
- convergence criteria/version;
- output artifact checksums;
- result checksum.

Do not rely on “whatever executable is installed today” without recording its identity/version.

## 1.6 Never execute arbitrary user shell commands

This is mandatory.

Do not expose an endpoint that accepts:

- arbitrary shell command;
- command path;
- Python source;
- arbitrary script;
- arbitrary Docker image;
- arbitrary plugin import;
- unreviewed executable artifact.

Provider execution must be code-registered and command construction must use allowlisted templates/arguments.

Never use `shell=True` with untrusted content.

Use isolated working directories, explicit timeouts, resource limits where available, safe path handling and sanitized logs.

## 1.7 No arbitrary external downloads during a simulation

A run must not silently download:

- pseudopotentials;
- force fields;
- model weights;
- thermodynamic databases;
- scripts;
- executables.

Required artifacts must be pre-registered, checksummed and approved.

If missing, the route is unavailable.

## 1.8 Numerical uncertainty and model limitations are explicit

Physics calculations have methodological/numerical uncertainty and approximation limits that differ from Phase-4 statistical prediction intervals.

Represent separately where meaningful:

- numerical/convergence tolerance;
- discretization/cutoff/k-point sensitivity metadata;
- finite-size limitations;
- potential/functional/database identity;
- parser/result warnings;
- validation/calibration status if a method has one.

Do not invent a confidence percentage.

## 1.9 A physics simulation cannot prove synthesizability

Even a stable/converged computational result does not automatically mean:

- synthesizable;
- manufacturable;
- safe;
- scalable;
- economical;
- experimentally correct.

UI copy must remain conservative.

## 1.10 No unsafe synthesis or laboratory procedures

Phase 6 may create computational input files only for reviewed simulation providers.

Do not generate hazardous chemical synthesis procedures, reaction recipes, operating instructions for laboratory apparatus, or autonomous lab commands.

---

# 2. PRESERVE THE ACTUAL PHASE-5 ARCHITECTURE

Do not replace:

- FastAPI / Pydantic v2 / SQLAlchemy 2 / Alembic modular monolith;
- PostgreSQL target;
- typed units;
- Materials Knowledge & Evidence Graph;
- evidence selection/conflict logic;
- Replacement Specification compiler/checksum;
- Phase-3 search spaces, `CandidateHypothesis`, candidate-v1 fingerprinting, lineage/change records;
- Phase-4 model registry, feature snapshots, applicability, prediction runs/results/uncertainty;
- Phase-5 campaigns, robust feasibility, Pareto ranking, decision ledger and bounded mutation;
- existing UI labs and privacy scoping seams.

Add a logical `simulation` module inside the modular monolith.

Do not create microservice/Kubernetes/HPC complexity yet.

---

# 3. SCIENTIFIC REPRESENTATION LAYER

Phase 6 needs a representation model because formulation-level composition is not sufficient for many physics methods.

Add a first-class representation object rather than stuffing arbitrary simulation input into `CandidateHypothesis.metadata`.

## 3.1 `ScientificRepresentation`

Represents a specific structured scientific representation of exactly one target:

- known `Material`; or
- `CandidateHypothesis`.

Suggested fields:

- id;
- organisation_id nullable/global visibility where appropriate;
- material_id nullable;
- hypothesis_id nullable;
- representation_type;
- format;
- representation_version;
- dimensionality/periodicity metadata where relevant;
- atom/component count where relevant;
- content/artifact reference;
- normalized representation checksum;
- parser/validator key/version;
- validation status;
- completeness status;
- provenance/evidence/source-record link where relevant;
- redaction flags;
- status;
- created_at.

Enforce exactly one target (`material_id xor hypothesis_id`).

Do not embed arbitrarily large files directly in normal API rows if object storage/artifact abstraction is more appropriate.

## 3.2 Representation types

At minimum define extensible controlled concepts such as:

- `periodic_atomic_structure`;
- `molecular_topology`;
- `coarse_grained_topology`;
- `phase_description`;
- `continuum_model` (future-facing only);
- `formulation_only`;
- `software_validation_fixture`.

A `formulation_only` representation should explicitly block atomistic DFT/MD routes.

## 3.3 Representation validation

Validation should be deterministic and format-specific.

Do not claim chemistry correctness merely because a file parses.

Separate:

- syntax parse status;
- structural completeness;
- method applicability.

Never infer missing atom identities/topology from generic Phase-3 component labels.

---

# 4. PHASE-6 DOMAIN MODEL — FORWARD `0006`

Add:

`0006_physics_simulation_os.py`

Do not edit migrations `0001`–`0005`.

Exact names may improve, but the following concepts are required.

## 4.1 `SimulationProvider`

Logical reviewed provider/solver family.

Suggested fields:

- id;
- organisation scope nullable for globally curated providers;
- key;
- display_name;
- provider_type (`software_fixture | local_executable | container | remote_hpc_future`);
- method_family (`analytical_fixture | dft | md | calphad | continuum_future | ml_force_field_future`);
- description;
- owner/project;
- status (`draft | approved | disabled | retired`);
- safety_class/approved_execution_mode;
- created_at / updated_at.

## 4.2 `SimulationProviderVersion`

Immutable executable/toolchain contract.

Suggested fields:

- id;
- provider_id;
- version;
- adapter_key;
- adapter_contract_version;
- executable_name/reference;
- executable_version;
- executable checksum nullable when not resolvable;
- container image/digest nullable;
- parser key/version;
- input builder key/version;
- convergence evaluator key/version;
- supported methods;
- supported material families;
- supported representation types/formats;
- supported purposes/property keys;
- artifact manifest checksum;
- environment manifest;
- maximum safe job size;
- maximum wall time;
- approved_at;
- retired_at nullable;
- immutable metadata;
- created_at.

Unique `(provider_id, version)`.

Historical versions that produced jobs/results must not be modified in place.

## 4.3 `SimulationMethodDefinition`

Typed method/purpose registry rather than a free-text field.

Examples:

- structural relaxation;
- single-point energy;
- elastic-property workflow future;
- finite-temperature MD trajectory;
- phase-equilibrium calculation future;
- software-validation numerical fixture.

Fields may include:

- key;
- display name;
- method family;
- required representation types;
- required parameters;
- output schema;
- units;
- convergence semantics;
- known scientific limitations;
- fidelity level/label.

Do not imply universal property support.

## 4.4 `SimulationRoute`

Persist or return a typed route decision.

Fields/concepts:

- target;
- requested purpose/property;
- requested conditions;
- selected method;
- selected provider version;
- route status;
- applicability reasons;
- required/missing representation;
- missing artifacts;
- fidelity;
- estimated resource class;
- route checksum.

Statuses should include:

- `ready`;
- `not_applicable`;
- `incomplete_representation`;
- `provider_unavailable`;
- `missing_registered_artifact`;
- `unsupported_property`;
- `unsupported_conditions`.

## 4.5 `SimulationInputSnapshot`

Immutable normalized input state.

At minimum:

- target kind/id;
- target scientific fingerprint/checksum;
- representation ID/checksum;
- method definition/version;
- provider version;
- normalized simulation parameters;
- target conditions;
- input builder version;
- artifact manifest/checksums;
- unit-normalization version;
- input checksum;
- redaction flags;
- created_at.

The historical result must not depend on the candidate’s current mutable state.

## 4.6 `SimulationWorkflow`

Auditable workflow instance.

Fields:

- id;
- organisation/project/candidate context;
- route/input snapshot;
- workflow template key/version;
- status;
- requested purpose/property;
- requested fidelity;
- max jobs/resources;
- started/completed timestamps;
- result checksum;
- failure code;
- metadata.

A workflow may contain one or more code-defined steps.

## 4.7 `SimulationWorkflowStep`

Structured DAG/ordered workflow step.

Fields:

- workflow id;
- sequence/step key;
- provider version;
- dependency step IDs or typed dependency records;
- status;
- input checksum;
- job id nullable;
- output checksum;
- required convergence;
- retry policy/version;
- metadata.

No arbitrary workflow scripts.

## 4.8 `SimulationJob`

Operational execution record.

Suggested fields:

- id;
- workflow/step;
- provider version;
- attempt number;
- workdir token/reference (not arbitrary user path);
- normalized command descriptor (safe, non-secret);
- resource request;
- status (`queued | running | completed | failed | timed_out | cancelled`);
- process exit code nullable;
- timeout/resource failure code;
- started/completed timestamps;
- stdout artifact id nullable;
- stderr artifact id nullable;
- operational checksum;
- metadata.

Operational success is not scientific convergence.

## 4.9 `SimulationArtifact`

Immutable checksummed artifact metadata.

At minimum:

- id;
- organisation/workflow/job scope;
- artifact_type (`input | output | log | trajectory | structure | force_field | pseudopotential | thermodynamic_database | manifest`);
- format;
- storage reference;
- SHA-256 checksum;
- size;
- MIME/media type;
- sensitive/private flag;
- content role;
- created_at.

Do not expose local absolute filesystem paths in normal APIs.

## 4.10 `SimulationResult`

First-class scientific-computational result separate from observations and predictions.

Suggested fields:

- id;
- workflow/job;
- target;
- method/provider version;
- operational status;
- scientific status (`converged | unconverged | partial | parser_failed | not_applicable`);
- convergence metrics;
- warnings/limitations;
- result checksum;
- created_at.

## 4.11 `SimulationPropertyEstimate`

If a converged workflow yields a property/quantity that can map to a TinkerLab property definition, persist it separately.

Fields:

- simulation result id;
- property definition;
- numeric value nullable;
- raw unit;
- canonical value/unit;
- numerical uncertainty/tolerance nullable;
- method-limitations metadata;
- target conditions;
- parser/extractor version;
- result checksum.

Do not create `MaterialPropertyObservation` automatically.

## 4.12 `SimulationSelectionPolicy`

If comparisons or Phase-5 campaigns may consume simulation results, make the policy explicit/versioned.

Default behavior:

- existing evidence behavior remains unchanged;
- Phase-4 prediction fallback remains unchanged;
- simulation results are displayed separately;
- no historical comparison silently begins preferring simulation values;
- an explicit `simulation_workflow_id` / policy is required to use a simulation estimate for a constraint/objective.

---

# 5. SIMULATION PROVIDER CONTRACT

Upgrade the existing future `SimulationProvider` protocol into a real Phase-6 contract.

Conceptually:

```python
class SimulationAdapter(Protocol):
    key: str
    contract_version: str

    def capabilities(...) -> SimulationCapabilities: ...
    def check_availability(...) -> ProviderAvailability: ...
    def validate_target(...) -> ApplicabilityResult: ...
    def build_inputs(...) -> InputBundle: ...
    def command_descriptor(...) -> SafeCommandDescriptor: ...
    def execute(...) -> ExecutionResult: ...
    def parse_outputs(...) -> ParsedSimulationResult: ...
    def assess_convergence(...) -> ConvergenceResult: ...
```

Every adapter declares:

- method family;
- supported representation types/formats;
- required registered artifacts;
- deterministic/stochastic semantics;
- allowed parameters and units;
- default/constrained resource policy;
- output parser contract;
- convergence contract;
- maximum safe target size;
- executable/container identity behavior;
- failure semantics.

Adapters are explicitly code-registered. No arbitrary import path from user input.

---

# 6. REQUIRED PHASE-6 PROVIDERS / ADAPTER BOUNDARIES

Do **not** pretend all providers are available or scientifically applicable.

## 6.1 Software-validation numerical provider — REQUIRED

Implement one deterministic, transparent provider to exercise the Simulation OS without making a real-material claim.

Example: a small analytical/harmonic/reduced-unit numerical fixture.

Requirements:

- unmistakably labelled:
  `SOFTWARE VALIDATION SIMULATION FIXTURE — not a validated real-material physics model.`
- code-reviewed, deterministic, no external executable required;
- produces a bounded numerical result and convergence metadata;
- uses a `software_validation_fixture` scientific representation;
- never maps its synthetic value to a real material performance claim unless the property itself is explicitly a synthetic demo property;
- used to test routing, snapshots, workflows, jobs, artifacts, parser, convergence, checksum and UI.

This provider validates the operating system, not materials science.

## 6.2 Local LAMMPS adapter boundary — REQUIRED CONTRACT, OPTIONAL EXECUTION

Implement a reviewed `lammps_local_v1` adapter boundary.

Requirements:

- availability check uses a configured/allowlisted executable name, not arbitrary path input;
- captures actual LAMMPS version when available;
- no user-provided shell command;
- no automatic force-field downloads;
- only code-defined input templates/commands;
- target must have an adequate supported atomistic/topological representation and explicitly registered potential/parameter artifact;
- absence of LAMMPS or a potential returns `provider_unavailable` / `missing_registered_artifact`;
- generic Phase-3 polymer formulations without atomistic topology must be rejected;
- if LAMMPS is available on the clean-machine environment, add a tiny reduced-unit/software-validation integration test that does **not** claim a real material property.

Do not invent a polymer topology to make this adapter run.

## 6.3 Quantum ESPRESSO adapter boundary — REQUIRED CONTRACT, EXECUTION ONLY IF SCIENTIFICALLY READY

Implement a reviewed `quantum_espresso_local_v1` boundary for a narrow subset such as periodic crystalline single-point/relaxation workflows.

Requirements:

- periodic atomic structure required;
- curated/checksummed pseudopotentials required;
- code-defined input template;
- explicit cutoffs/k-point/convergence parameters;
- provider availability/version detection;
- safe subprocess execution if available;
- parser/convergence contract;
- no arbitrary pseudopotential download;
- no attempt to run the existing generic polymer formulation through DFT;
- if the executable/pseudopotential fixture is absent, route must remain unavailable rather than faking output.

Do not require the artifact environment to install/run a heavyweight DFT calculation simply to claim PASS.

## 6.4 CALPHAD adapter boundary — INTERFACE ONLY UNLESS DEPENDENCIES/DATA ARE VALID

Create capability/schema boundaries for a future CALPHAD provider.

It must require a phase/component representation plus an approved thermodynamic database artifact.

Do not generate phase diagrams from invented database values.

If no reviewed database exists, no numerical CALPHAD result is produced.

## 6.5 ML force-field provider boundary — INTERFACE ONLY

Create the provider capability seam for a future ML force-field adapter.

Do not download MACE/CHGNet/etc weights in Phase 6 unless separately reviewed and licensed/registered.

No model weights = provider unavailable.

---

# 7. PROVIDER / ARTIFACT REGISTRY SAFETY

## 7.1 Provider lifecycle

Support:

- draft provider metadata;
- immutable provider version;
- availability inspection;
- approve/disable/retire;
- historical jobs/results readable after retirement;
- no mutation of a provider version after use.

## 7.2 External scientific artifacts

Pseudopotentials, force fields, parameter files and thermodynamic databases must have first-class registry/artifact metadata:

- provider/source/license metadata;
- checksum;
- supported method/provider;
- version;
- approval status;
- private/public scope;
- optional citation/provenance.

Do not return copyrighted/licensed artifact content through APIs unless permitted.

## 7.3 Executable safety

Never allow API users to set an arbitrary executable path/command.

Configuration may select from server-admin allowlisted provider executables only.

---

# 8. SIMULATION ROUTER

Create a dedicated scientific routing service.

Router inputs:

- target material/hypothesis;
- available scientific representation(s);
- requested purpose/property;
- target conditions;
- requested/maximum fidelity;
- organisation scope;
- available approved providers/artifacts;
- optional user-pinned provider version.

Router checks at least:

1. target visibility/scope;
2. target representation completeness;
3. method-representation compatibility;
4. material-family applicability;
5. requested property/purpose support;
6. target-condition support;
7. required external artifact availability;
8. provider executable/runtime availability;
9. target size/resource bound;
10. provider approval/lifecycle.

Return ordered compatible routes with transparent reasons.

Do not return a fake generic “best physics method” score.

A defensible deterministic ordering can use explicit fidelity, applicability completeness, provider availability and stable provider key as tie-breakers.

---

# 9. WORKFLOW TEMPLATES

Phase 6 needs reproducible workflows without adopting a large workflow engine prematurely.

Implement a small code-registered workflow-template registry.

Examples:

- `software_fixture_single_step_v1`;
- `dft_single_point_v1` future/conditional;
- `dft_relax_then_single_point_v1` future/conditional;
- `md_equilibrate_then_sample_v1` future/conditional.

Each template declares:

- step keys/order/dependencies;
- required provider method;
- required inputs/artifacts;
- accepted parameter schema;
- convergence gates;
- max retries;
- output parsers;
- reproducibility version.

No user-authored executable DAG/script in Phase 6.

---

# 10. EXECUTION SANDBOX / LOCAL RUNNER

Implement a bounded local runner abstraction suitable for future extraction to an HPC backend.

## 10.1 Safety

- unique server-controlled working directory per attempt;
- path traversal protection;
- fixed allowlisted executable/provider;
- `subprocess` argument arrays, no `shell=True`;
- sanitized environment allowlist;
- explicit timeout;
- stdout/stderr size caps;
- input/output artifact size limits;
- cleanup policy;
- cancellation support where feasible;
- no secrets in command/log records.

## 10.2 Resources

Represent at least:

- CPU count;
- memory request/limit metadata;
- wall-time timeout;
- optional GPU request future-facing;
- working-storage bound.

Actual cgroup/HPC enforcement may be limited locally; document what is metadata versus truly enforced.

## 10.3 Attempts/retries

A retry is a new immutable attempt/job record.

Do not overwrite failed job history.

Automatic retry only for explicitly retryable operational failures; never alter scientific parameters silently to force convergence.

---

# 11. INPUT BUILDERS

Input builders must be deterministic and versioned.

Requirements:

- typed parameter models;
- canonical units;
- stable ordering;
- target representation checksum;
- registered artifact references/checksums;
- provider version;
- no arbitrary text injection into solver control files;
- normalized input-bundle checksum.

If a scientific parameter is required but absent, return a validation error. Do not invent it.

For DFT/MD providers, treat numerical choices such as cutoffs, k-point density, timestep, temperature controls, equilibration length, potential mapping etc. as explicit configured scientific parameters, not hidden defaults unless the provider version documents the default immutably.

---

# 12. OUTPUT PARSERS / CONVERGENCE

Parsers must be provider/version specific and deterministic.

Store:

- raw output artifact checksum;
- parser version;
- parse status;
- parsed quantities;
- convergence metrics;
- warnings;
- result checksum.

Never parse a numeric value and call it valid if required convergence criteria fail.

Examples of conceptual convergence checks:

- DFT: electronic/ionic convergence flags, max force criteria, calculation completion;
- MD: workflow-defined equilibration/sample completeness and finite/nonnan output;
- CALPHAD: solver convergence where supported;
- software fixture: known deterministic tolerance check.

Do not claim universal convergence semantics.

---

# 13. SIMULATION PROPERTY ESTIMATES AND UNITS

A `SimulationPropertyEstimate` may be created only when:

1. target/result linkage is unambiguous;
2. workflow scientific status permits extraction;
3. output parser is registered;
4. property mapping is explicitly supported;
5. unit is valid/canonicalizable;
6. result provenance is complete.

Store simulation-specific numerical tolerance/uncertainty separately from Phase-4 model prediction intervals.

If the method cannot justify an uncertainty/tolerance interval, do not invent one; expose method/convergence limitations instead.

---

# 14. REPRODUCIBILITY CHECKSUMS

Create canonical checksums for:

## Representation

- normalized representation content;
- format/version;
- parser/validator version.

## Route

- target representation checksum;
- requested purpose/property/conditions;
- method definition;
- provider version/artifact manifest;
- route policy/version.

## Input snapshot

- representation checksum;
- provider/method/workflow versions;
- normalized parameters;
- registered scientific artifact checksums;
- conditions;
- input-builder version;
- unit-normalization version.

## Job attempt

- input checksum;
- provider executable/container identity;
- safe command descriptor;
- environment manifest;
- resource request;
- attempt number.

## Result

- input/job checksum;
- relevant output artifact checksums;
- parser version;
- convergence result;
- parsed quantities;
- property-estimate checksums.

## Workflow

- ordered step/job/result checksums;
- final scientific status;
- failure/stop code.

Same immutable deterministic software-fixture input must reproduce the same result checksum.

A changed representation/provider/artifact/parameter/condition must change the relevant checksum.

Timestamps and display names must not alter scientific checksums.

---

# 15. SIMULATION FIDELITY MODEL

Introduce an explicit fidelity concept, but do not pretend all methods are linearly comparable.

Possible labels:

- `software_fixture`;
- `empirical_atomistic`;
- `ml_interatomic_future`;
- `first_principles`;
- `thermodynamic_phase_model`;
- `continuum_future`.

The fidelity label is descriptive, not a universal quality score.

A DFT calculation is not automatically “better” for every property/problem than MD/CALPHAD/continuum.

The router must use method-specific applicability, not fidelity number alone.

---

# 16. PHASE-5 CAMPAIGN INTEGRATION

Integrate carefully.

## 16.1 Escalation from Virtual Experiment Lab

Allow a scientist to select campaign candidates/evaluations and create a **simulation request/route preview**.

This is an explicit escalation, not automatic replacement of Phase-5 predictions.

Example:

`Pareto/uncertain candidate -> request physics assessment -> route preview -> simulation workflow`

## 16.2 No silent reranking

Existing Phase-5 campaign history is immutable.

A newly completed simulation must not retroactively alter historical Pareto ranks/evaluations.

If Phase 6 supports a new campaign/evaluation policy using simulations, it must create a new explicit campaign/iteration or comparison policy.

## 16.3 Recommended-for-simulation state

A candidate may be marked/recommended for simulation as a decision state, but this is not validation.

## 16.4 Simulation-based comparison fallback

If implemented, require an explicit workflow/result selection policy.

Default project comparison behavior remains:

1. known evidence behavior unchanged;
2. prediction fallback only when explicitly selected;
3. simulation values shown separately unless explicitly selected.

Never silently establish an undocumented origin priority.

---

# 17. PHASE-6 SEEDED DEMONSTRATION

Extend the existing deterministic fixtures carefully.

The existing generic polymer demo is **not** an adequate atomistic target. Use that fact as an important routing demonstration.

Seed:

1. the required software-validation simulation provider/version;
2. one `software_validation_fixture` scientific representation attached to a clearly synthetic demo target;
3. one successful deterministic software-fixture route/workflow/job/result/property-like synthetic output;
4. one route refusal for a generic polymer hypothesis because only formulation-level representation exists;
5. one unavailable LAMMPS route/provider status unless LAMMPS + required approved artifact is truly available;
6. one unavailable/not-ready Quantum ESPRESSO route unless executable + approved representation + pseudopotential artifacts are present;
7. complete artifact/checksum/convergence records;
8. explicit synthetic/software-validation warnings everywhere.

Do not seed unsourced real material properties merely to make the Simulation Lab look impressive.

If you add a scientifically real structure/provider fixture, source/provenance it accurately and keep the calculation tiny; do not claim experimental validation.

Seed twice must be idempotent.

---

# 18. API REQUIREMENTS

Exact URLs may improve, but implement equivalent typed capabilities.

## 18.1 Representations

- create/list/get scientific representations;
- validate representation syntax/completeness;
- list target representations;
- scoped artifact metadata;
- no unsafe raw-file path exposure.

Examples:

`POST /materials/{id}/representations`

`POST /candidate-hypotheses/{id}/representations`

## 18.2 Provider registry

- list providers;
- get provider/version/capabilities;
- availability check;
- draft/register version through admin/demo path;
- approve/disable/retire lifecycle;
- scientific artifact registry metadata.

## 18.3 Route preview

`POST /simulation/routes/preview`

Return:

- applicable/not-applicable status;
- reasons;
- representations considered;
- candidate methods/providers;
- missing artifacts/runtime;
- estimated resource class;
- fidelity/method limitations;
- route checksum.

Preview creates no workflow/job.

## 18.4 Workflow preview/create

- validate requested route/parameters;
- show normalized input snapshot/checksum;
- show workflow steps;
- show exact provider versions/artifact checksums;
- create only after valid preview.

## 18.5 Execution

- execute a bounded workflow;
- get workflow detail/status;
- cancel if operationally supported;
- list step/job attempts;
- get sanitized logs/artifact metadata;
- get result/convergence/property estimates.

## 18.6 Target history

- material simulation history;
- candidate-hypothesis simulation history;
- campaign candidate -> simulation history.

## 18.7 Comparison

Support explicit simulation-result selection without breaking existing default evidence/prediction contracts.

---

# 19. UI — SIMULATION LAB

Build a serious scientific-compute workspace.

Do not build a fake animated molecular lab.

## 19.1 Simulation Lab overview

Show:

- target material/hypothesis;
- representation readiness;
- available methods/providers;
- provider availability;
- recent workflows;
- scientific status;
- explicit warning:

> Physics simulation is computational evidence, not a physical experiment or manufacturing proof.

## 19.2 Representation inspector

Show:

- representation type/format;
- target;
- checksum;
- provenance;
- parser/validation status;
- completeness;
- periodicity/size metadata;
- redaction warning;
- method compatibility.

Do not dump huge raw artifacts by default.

## 19.3 Route preview

Show each possible route with:

- method;
- provider/version;
- readiness status;
- reason for rejection/acceptance;
- required/missing representation/artifacts;
- fidelity label;
- resource class;
- limitations.

A refusal must be a first-class useful outcome.

## 19.4 Workflow preview

Before execution show:

- target representation checksum;
- normalized parameters;
- provider/executable identity;
- scientific artifacts/checksums;
- ordered steps/dependencies;
- convergence criteria;
- timeout/resource request;
- input checksum;
- no execution yet.

## 19.5 Workflow detail

Show:

- operational status;
- scientific convergence status;
- step/job attempts;
- provider version;
- input/output checksums;
- sanitized logs;
- warnings;
- artifacts;
- parsed quantities;
- result checksum;
- limitations.

Do not equate exit code 0 with convergence.

## 19.6 Simulation result detail

Visually distinguish:

- `CONVERGED PHYSICS SIMULATION`;
- `UNCONVERGED / PARTIAL`;
- `PROVIDER UNAVAILABLE`;
- `NOT APPLICABLE`.

Never say experimentally verified.

## 19.7 Candidate / campaign integration

Add simulation history/escalation actions to candidate and virtual-campaign detail.

Do not overwrite Phase-5 objective/feasibility history.

---

# 20. BOUNDED EXECUTION / EXPLOSION PROTECTION

Phase 6 remains local/synchronous or simple local-worker scale.

Choose/document hard limits such as:

- max workflow steps: 10;
- max jobs per synchronous request: 10;
- max concurrent local jobs: small/configured;
- max wall-time for software fixture: seconds/minutes;
- provider-specific hard timeouts;
- max input/output/log artifact size;
- max atomic representation size for local fixture/provider route;
- no unbounded trajectory return through API;
- paginated artifact/job/result lists.

Do not introduce an HPC cluster scheduler in Phase 6.

Create a future `ComputeBackend`/`HPCBackend` protocol if useful, but implement only bounded local execution in this phase.

---

# 21. PRIVACY / MULTI-TENANT / ARTIFACT SECURITY

Maintain all prior scoping behavior.

At minimum:

- private representations are organisation-scoped;
- private scientific artifacts cannot be used by another organisation;
- workflows/jobs/results are project/organisation scoped;
- raw private structures/topologies are not exposed in list endpoints;
- working directory paths are never returned as a public locator;
- logs do not expose environment secrets;
- subprocess environment is allowlisted;
- provider/version registry enforces global/private ownership;
- route preview cannot leak existence of another tenant's artifact/provider;
- checksums are one-way identities, not access control;
- downloaded/exported artifacts preserve privacy permissions.

`X-Organisation-ID` remains only a development scoping seam.

---

# 22. PERFORMANCE / QUERY SHAPE

Create bounded profiles for the Simulation OS.

At minimum measure:

1. route-preview for 100 candidate targets with no simulation persistence;
2. representation/provider readiness access;
3. 20 bounded software-fixture workflows;
4. workflow list/pagination;
5. one workflow detail with steps/jobs/artifacts/results.

Document:

- SELECT query shape/count;
- provider availability checks;
- executable launches;
- artifact checksum operations;
- no query-per-target-per-provider pattern;
- no repeated provider binary/version probing per target;
- no raw artifact content loaded unnecessarily.

Do not publish synthetic SQLite/local-executable latency as production performance.

---

# 23. TESTING

Keep **all 108 Phase-1–5 backend tests green** and substantially extend coverage.

## 23.1 Migration

- `0005` data survives `0006` upgrade;
- all material/candidate/hypothesis/prediction/campaign IDs survive;
- new constraints/indexes exist;
- live PostgreSQL migration on normal environment;
- downgrade behavior documented on disposable data.

## 23.2 Scientific representation

- exactly one material/hypothesis target;
- deterministic checksum;
- ordering/format normalization where supported;
- invalid syntax rejected;
- incomplete representation explicit;
- redacted representation not silently repaired;
- generic formulation not treated as atomistic structure.

## 23.3 Provider registry

- provider/version uniqueness;
- only approved versions executable;
- disabled/retired blocked for new jobs;
- historical results readable;
- immutable provider version after use;
- arbitrary executable/provider path rejected;
- arbitrary pickle/script/plugin rejected;
- external artifact checksum required where applicable.

## 23.4 Router

- supported representation/property/provider -> ready;
- formulation-only polymer -> DFT/MD not applicable;
- missing topology -> MD refusal;
- missing pseudopotential -> DFT refusal;
- missing thermodynamic DB -> CALPHAD refusal;
- unavailable executable -> provider unavailable;
- unsupported family/property/conditions -> explicit reason;
- cross-tenant private representation/provider artifact rejected;
- deterministic route ordering/checksum.

## 23.5 Input snapshot

- deterministic normalized input;
- canonical units;
- changed parameter changes checksum;
- changed representation changes checksum;
- changed provider/artifact changes checksum;
- no hidden required parameter invention.

## 23.6 Safe execution

- no shell execution of untrusted command;
- path traversal rejected;
- timeout produces immutable failed/timed-out attempt;
- stdout/stderr capped/sanitized;
- retry creates new attempt rather than overwriting;
- unsafe environment keys not forwarded;
- arbitrary user command text cannot become executable.

## 23.7 Parser/convergence

- software fixture converges deterministically;
- parser failure produces no property estimate;
- operational success + scientific unconvergence produces no accepted converged property;
- NaN/invalid numerical output rejected;
- output unit mapping validated;
- result checksum deterministic.

## 23.8 Scientific integrity

Mandatory tests:

- simulation creates zero experimental observations automatically;
- simulation result is not a `PropertyPrediction`;
- prediction remains separate/visible;
- known evidence remains separate/visible;
- generic polymer hypothesis cannot receive fake DFT/MD number;
- no simulation result if representation/provider/artifact missing;
- synthetic software-validation provider warning is present;
- no “experimentally validated” language for simulation-only target;
- no physical lab/synthesis records created.

## 23.9 Campaign integration

- campaign candidate can be escalated to route preview;
- historical Phase-5 evaluation/Pareto checksum remains unchanged after simulation;
- simulation does not retroactively rerank campaign;
- explicit simulation selection policy only;
- candidate simulation history scope correct.

## 23.10 Reproducibility

Same:

- representation;
- provider version;
- scientific artifact manifest;
- parameters;
- conditions;
- workflow template;
- software fixture

must reproduce the same deterministic input/result/workflow checksum.

Meaningful changed input must change the appropriate checksum.

## 23.11 API

Cover representation create/validate, provider list/version/availability, route preview zero persistence, workflow preview, bounded execution, workflow/job/result detail, artifact metadata, target history, explicit comparison policy and privacy.

## 23.12 Frontend

Test at least:

- simulation-vs-experiment warning;
- representation readiness;
- route refusal reasons;
- provider unavailable state;
- workflow preview does not execute;
- job operational status separate from convergence;
- converged/unconverged distinction;
- artifact/checksum rendering;
- no fake material-validation language;
- campaign history unchanged by simulation.

---

# 24. OBSERVABILITY

Add structured non-secret events:

- request/correlation ID;
- simulation workflow ID;
- step/job/attempt ID;
- target kind/id;
- provider key/version;
- method key;
- route/input checksum prefixes;
- representation checksum prefix;
- operational status;
- convergence status;
- resource request/elapsed class;
- output artifact count/checksum prefixes;
- failure code;
- parser/convergence version.

Never log full private structures, input artifacts, force fields, pseudopotentials, environment secrets or huge stdout/stderr by default.

---

# 25. DOCUMENTATION

Create/update at minimum:

- `README.md`;
- `docs/ARCHITECTURE.md`;
- `docs/DOMAIN_MODEL.md`;
- `docs/ERD.md`;
- `docs/PHASE5_STABILIZATION_FOR_PHASE6.md`;
- `docs/PHASE6_SCOPE.md`;
- `docs/SCIENTIFIC_REPRESENTATIONS.md`;
- `docs/SIMULATION_PROVIDER_CONTRACT.md`;
- `docs/SIMULATION_ROUTER.md`;
- `docs/SIMULATION_WORKFLOWS.md`;
- `docs/SAFE_EXECUTION.md`;
- `docs/SIMULATION_ARTIFACTS.md`;
- `docs/SIMULATION_CONVERGENCE.md`;
- `docs/SIMULATION_REPRODUCIBILITY.md`;
- `docs/SIMULATION_SELECTION_POLICY.md`;
- `docs/SCIENTIFIC_INTEGRITY.md`;
- `docs/PRIVACY_MODEL.md`;
- `docs/FUTURE_ARCHITECTURE.md`.

Document exactly which providers are:

- implemented and executable;
- implemented but unavailable in the current environment;
- interface-only;
- software-validation fixtures.

Never hide that distinction.

---

# 26. EXPLICITLY DO NOT IMPLEMENT IN PHASE 6

Do not implement:

- physical experiment/lab request execution;
- laboratory robotics;
- autonomous synthesis;
- hazardous synthesis recipes;
- experimental feedback/model retraining;
- online active-learning model updates;
- patent/novelty search;
- IP/patentability claims;
- supplier integrations;
- live commodity pricing;
- full manufacturing-process planning;
- LCA/industrial viability score unless already a sourced property in the knowledge graph;
- universal FEA platform;
- unbounded HPC scheduling;
- arbitrary user containers/scripts/commands;
- arbitrary model/potential/pseudopotential downloads;
- LLM-generated scientific solver results;
- Kubernetes/microservice decomposition;
- production billing/SSO unless fixing a P0 security issue.

Phase 7 is the **Industrial Viability Engine**: manufacturing, economics, supply, sustainability and qualification. Do not consume it early.

---

# 27. REQUIRED PHASE-6 QUALITY CHECK

Before declaring Phase 6 complete:

1. Clean Docker Compose boot.
2. Real PostgreSQL migrations through `0006`.
3. Prove Phase-5 data migration integrity.
4. Seed twice/idempotency.
5. Run all backend tests.
6. Run Ruff.
7. Run Mypy.
8. Confirm Pint runtime/unit tests.
9. Run frontend tests.
10. Full TypeScript typecheck.
11. ESLint.
12. Next production build.
13. Browser smoke/responsive/console.
14. Register/inspect simulation provider versions.
15. Create/validate scientific representation.
16. Route preview and prove zero workflow/job persistence.
17. Demonstrate formulation-only generic polymer DFT/MD refusal.
18. Demonstrate missing artifact/provider refusal.
19. Preview a valid software-fixture workflow.
20. Execute bounded software-fixture workflow.
21. Inspect operational job status separately from scientific convergence.
22. Re-run identical fixture and prove deterministic checksums.
23. Change representation/parameter/provider semantics and prove checksum change.
24. Trigger parser/convergence failure test with no accepted property estimate.
25. Confirm simulation creates zero observations/predictions automatically.
26. Confirm evidence/prediction/simulation remain separate in UI/API.
27. Escalate a Phase-5 campaign candidate to simulation preview.
28. Confirm historical campaign result/Pareto checksum is unchanged.
29. Verify provider command safety/path/environment protections.
30. Verify private representation/artifact/workflow data cannot leak.
31. Profile route preview / bounded workflow query shape.
32. If LAMMPS/QE installed, run only the reviewed integration fixture and record exact availability/version; otherwise mark integration UNVERIFIED/UNAVAILABLE, never PASS.
33. Remove caches/debug/generated junk.
34. Update docs truthfully.

Never mark an unavailable/unexecuted check PASS.

---

# 28. PHASE-6 ACCEPTANCE CRITERIA

Phase 6 is complete only if:

- the Phase-5 stabilization gate passes on a normal dependency-enabled environment, or every unavailable item is explicitly gated before production acceptance;
- forward `0006` works without editing prior migrations;
- scientific representation model exists and prevents inappropriate routing;
- provider registry/version lifecycle is immutable/auditable;
- router returns explicit applicability/refusal reasons;
- arbitrary shell/plugin/model execution is impossible through normal API contracts;
- provider artifacts are registered/checksummed rather than silently downloaded;
- input snapshots are deterministic/versioned/checksummed;
- workflows/steps/jobs/attempts/artifacts/results are first-class;
- operational success and scientific convergence are distinct;
- simulation property estimates are separate from observations/predictions;
- no number is produced for an unavailable/inapplicable/unconverged route;
- software-validation simulation fixture is unmistakably labelled synthetic/software-only;
- LAMMPS/QE/CALPHAD/MLFF boundaries are honest about actual availability;
- Phase-5 campaign history remains immutable when simulations are later run;
- explicit simulation-selection policy preserves backward compatibility;
- checksums/replay work;
- privacy/safe execution protections are tested;
- Simulation Lab is usable/auditable;
- all tests/lint/typecheck/build pass on a normal environment;
- documentation matches actual implementation.

---

# 29. FINAL DELIVERY

Return a clean ZIP of the complete Phase-6 repository.

Exclude:

- `node_modules`;
- virtual environments;
- `.next`;
- test SQLite databases;
- simulation working directories;
- generated trajectories/logs not required for tiny fixtures;
- caches;
- debug dumps;
- secrets;
- unlicensed scientific artifacts;
- large binaries/executables;
- downloaded pseudopotentials/force fields unless explicitly permitted and required for the reviewed fixture.

Provide a detailed implementation report containing:

## Phase-5 stabilization

Exact checks/fixes/results.

## Implemented

Actual Phase-6 functionality.

## Scientific representations

What formats/types exist, validation/completeness rules and limitations.

## Provider architecture

Provider/version registry, adapters, executable availability and safe artifact handling.

## Simulation router

Exact applicability/routing rules and refusal behavior.

## Workflow/execution

Workflow templates, job attempts, safe execution, resources/timeouts and retry semantics.

## Convergence/results

Operational vs scientific status, parser/convergence rules, property extraction and limitations.

## Scientific integrity

How evidence, prediction and simulation remain separate.

## Reproducibility

Representation/input/job/output/result/workflow checksum design and replay proof.

## Database

`0006` changes and indexes/constraints.

## Tests

Exact counts/results.

## Provider availability

For each provider classify:

- executable and verified;
- implemented adapter but runtime unavailable;
- interface-only;
- software-validation fixture.

Do not blur these categories.

## Performance profile

Route/workflow/job/result query/execution shape without synthetic latency claims.

## Security/privacy

Command execution, filesystem, environment, artifacts and tenant scope.

## Known limitations

Especially absence of physical validation and unavailable external solvers/artifacts.

## Deferred to Phase 7+

Explicit list.

## Run commands

Exact clean-machine commands including optional provider availability checks.

## Verification checklist

Every acceptance item marked PASS / FAIL / UNVERIFIED with explanation.

Never claim PASS without executing the check.

---

# 30. STOP CONDITION

At the end of Phase 6, **STOP**.

Do not implement Phase 7 automatically.

The completed Phase-6 package must be audited first. Phase 7 will introduce the **Industrial Viability Engine** (manufacturing compatibility, process feasibility, economics, supply/critical-material exposure, sustainability and qualification readiness), and its design must consume actual Phase-6 simulation outputs through explicit evidence-origin contracts rather than assumptions.
