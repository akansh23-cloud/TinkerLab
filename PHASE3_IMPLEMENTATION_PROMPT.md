# TinkerLab — Phase 3 Implementation Prompt

## Candidate & Replacement Generation Engine

You are continuing the **actual TinkerLab Phase-2 repository**. Do not rebuild the application from scratch and do not replace the Phase-2 scientific data model with a generic AI architecture.

You are acting as the founding Principal Engineer, Scientific Software Architect, Product Architect, and senior full-stack engineer for TinkerLab.

TinkerLab's long-term goal remains a closed-loop **Material Replacement & Discovery Operating System**.

# THIS IS PHASE 3 ONLY

The purpose of Phase 3 is to add a **bounded, deterministic, explainable Candidate & Replacement Generation Engine** on top of the Phase-2 Materials Knowledge & Evidence Graph.

Phase 3 is the first phase that may create **material hypotheses**, but it must be extremely clear that a generated hypothesis is not a discovered, validated, simulated, or experimentally proven material.

Do **not** implement ML property prediction, MatterGen, DFT, MD, CALPHAD, Bayesian optimisation, evolutionary optimisation, active learning, patent search, synthesis protocols, autonomous laboratories, or robotics.

The key product promise for this phase is:

> Given a replacement project, its current baseline material, an explicitly bounded search space, and curator-approved generation rules, TinkerLab can reproducibly propose replacement hypotheses, explain every change, preserve full lineage, reject structurally invalid proposals, and compare known-material candidates and hypothetical candidates without fabricating scientific properties.

---

# 0. MANDATORY PHASE-2 STABILIZATION GATE

Before adding Phase-3 functionality, verify Phase 2 on a machine with normal package/network and Docker capability.

The supplied Phase-2 repository already passed **34/34 backend tests** in the original sandbox and generated the PostgreSQL migration chain offline, but several environment-dependent checks were unavailable.

You MUST execute the following before Phase-3 acceptance:

## 0.1 Docker and PostgreSQL

1. Start the complete stack using Docker Compose.
2. Start a real PostgreSQL instance.
3. Apply `0001 -> 0002` from a clean database.
4. Seed the database.
5. Restart the services and verify persistence.
6. Create a disposable database representing a Phase-1 schema/data snapshot.
7. Upgrade that database from `0001` to `0002`.
8. Confirm existing Phase-1 project/material/candidate IDs and relationships survive.
9. Exercise a downgrade only in a disposable database and document what data is destructive/lossy.

Do not modify the historical `0001` or `0002` migration to make Phase 3 easier. Add a forward `0003` migration.

## 0.2 Scientific dependencies

Install the declared Python dependencies, including Pint.

Verify that production/local runtime uses the Pint-backed unit implementation rather than relying on the offline compatibility fallback that was necessary in the original sandbox.

Run dedicated tests for:

- MPa ↔ Pa;
- kg/m³ ↔ g/cm³;
- °C conversions;
- pressure units;
- frequency units introduced in Phase 2;
- incompatible-unit rejection.

If the Pint integration exposes any discrepancy, fix it before proceeding.

## 0.3 Backend quality

Run and fix:

```bash
pytest -q
ruff check .
mypy app
```

Do not suppress errors globally merely to pass the gate.

## 0.4 Frontend quality

Install frontend dependencies and run:

```bash
npm run test
npm run typecheck
npm run lint
npm run build
```

Then run the actual UI and perform browser smoke tests for:

- Dashboard;
- replacement project wizard;
- project workspace;
- Materials Explorer;
- Material Passport v2;
- Observation/Provenance Inspector;
- Import Center;
- candidate comparison;
- responsive behaviour;
- browser-console errors.

## 0.5 Phase-2 privacy regression

Verify with API tests and browser/API inspection that:

- private imported materials are not visible without organisation scope;
- private source records are not visible without organisation scope;
- organisation-owned project metadata does not leak through public materials;
- raw source payloads are not exposed in normal API response models.

## 0.6 Gate rule

If any P0/P1 defect is discovered, fix it first.

Document all stabilization changes separately under:

`docs/PHASE2_STABILIZATION_FOR_PHASE3.md`

Only then begin Phase 3.

---

# 1. NON-NEGOTIABLE SCIENTIFIC PRINCIPLES

## 1.1 Hypothesis is not evidence

A generated candidate hypothesis must never automatically receive a `MaterialPropertyObservation` merely because its parent material has one.

Examples:

- If the baseline has tensile strength 74 MPa and a component amount changes, the hypothesis tensile strength is **UNKNOWN**.
- If a substitution rule replaces Modifier B with Modifier B2, the child does not inherit the parent's thermal or mechanical values.
- A process variation invalidates assumptions about properties unless there is independent evidence for that exact candidate/state.

Phase 3 must make this visually and structurally obvious.

## 1.2 Generated candidates are proposals, not canonical materials

Do not pollute the Phase-2 `materials` knowledge graph by inserting every generated candidate as if it were a known material.

Introduce a first-class **CandidateHypothesis** representation separate from canonical/known material records.

A candidate attached to a replacement project may represent either:

- a **known material** backed by the Phase-2 knowledge graph; or
- a **hypothesis** created by Phase-3 generation.

Later phases may predict/simulate/test a hypothesis. Physical validation may eventually justify promoting it to a material record. That is not Phase 3.

## 1.3 Every generated change needs lineage

No generated candidate may appear without a deterministic lineage record answering:

- which project/specification produced it;
- which generation run produced it;
- which strategy and strategy version produced it;
- which parent/baseline it came from;
- which rule was applied;
- what fields changed;
- before/after values;
- why the change was allowed;
- what evidence or curator configuration authorised the rule;
- random seed, if sampling was required;
- candidate fingerprint.

## 1.4 Search space must be bounded explicitly

Do not let a prompt/LLM freely invent chemical components.

A Phase-3 generation run operates only over an explicit user/curator-defined search space such as:

- approved alternative components;
- concentration bounds;
- locked components;
- balance/compensation component;
- permitted process variables;
- process parameter bounds;
- allowed known-material families;
- prohibited component identifiers;
- maximum candidate budget.

If the search space is insufficient, the engine should refuse to generate rather than invent missing chemistry.

## 1.5 Redacted or incomplete composition is not silently inferred

If the Phase-2 baseline contains redacted or incomplete composition:

- known-material retrieval may still operate where appropriate;
- manual hypothesis capture may still operate;
- component mutation must refuse to mutate unavailable/redacted content unless a curator explicitly supplies a valid mutable search representation.

Never guess a redacted amount or identity.

## 1.6 Determinism before sophistication

The same:

- project specification checksum;
- search-space version;
- generation strategy version;
- run configuration;
- random seed

must reproduce the same ordered candidate fingerprints.

This phase is about a trustworthy generation substrate, not the most advanced optimiser.

## 1.7 No unsafe synthesis instructions

Phase 3 may represent composition/process hypotheses at an engineering-data level, but must not generate detailed hazardous synthesis protocols, reaction procedures, operating instructions, or autonomous lab commands.

---

# 2. PRESERVE THE PHASE-2 ARCHITECTURE

The current repository contains:

- FastAPI + Pydantic v2 + SQLAlchemy 2;
- PostgreSQL target and Alembic migrations;
- Next.js + TypeScript frontend;
- evidence/provenance graph;
- typed conditions;
- observation selection;
- conflict policies;
- local controlled ingestion;
- Material Passport v2;
- Materials Explorer;
- project replacement specification and comparison;
- modular-monolith architecture.

Do not replace those foundations.

Continue using strong logical modules while keeping deployment simple.

No Kubernetes and no microservice explosion.

---

# 3. PHASE-3 DOMAIN MODEL

Design a forward `0003_candidate_generation.py` migration.

Do not modify migrations `0001` or `0002`.

The exact names may improve if justified, but the concepts below are required.

## 3.1 Candidate kind

The existing Phase-1 `Candidate` currently points to a non-null `material_id`.

Migrate it safely so a project candidate can represent exactly one of:

1. a known material;
2. a generated/manual hypothesis.

Recommended shape:

- `candidate_kind`: `known_material | hypothesis`
- `material_id`: nullable for hypothesis candidates
- `hypothesis_id`: nullable for known-material candidates

Enforce at the database level where practical:

> exactly one of `material_id` or `hypothesis_id` must be populated.

Preserve all existing Phase-1/2 candidates as `known_material`.

Do not lose their IDs.

## 3.2 CandidateHypothesis

Create a first-class candidate hypothesis entity.

Suggested fields:

- id
- project_id
- display_label
- material_family
- baseline_material_id
- generation_run_id nullable for manual hypotheses
- generator_strategy_key
- generator_strategy_version
- deterministic_fingerprint
- status
- structural_validity
- rejection_reason nullable
- notes
- created_at
- updated_at

Status examples:

- proposed
- accepted_for_screening
- rejected
- archived

Do not call a Phase-3 status `validated`, `verified`, or `discovered`.

## 3.3 CandidateHypothesisComponent

Do not store a concrete formulation only as an opaque JSON blob.

Create structured components similar in spirit to Phase-2 material components.

Fields should support:

- hypothesis_id
- sequence
- component identity/key
- display name
- role
- amount
- unit/basis
- source/baseline component reference where applicable
- substitution_rule_id where applicable
- locked flag
- metadata

A generated hypothesis should contain a **concrete proposal**. Search-space ranges belong in the search-space model, not in the generated candidate component row.

## 3.4 CandidateHypothesisProcessState / ProcessParameter

Represent concrete proposed process changes separately from material knowledge observations.

At minimum support:

- process step/label;
- parameter key;
- value;
- unit;
- source/baseline reference;
- change provenance.

Avoid a free-form script or executable recipe.

## 3.5 GenerationRun

Create an immutable/auditable run record.

Suggested fields:

- id
- project_id
- replacement_specification_checksum
- search_space_id/version/checksum
- strategy_key
- strategy_version
- configuration checksum
- random_seed
- requested_candidate_budget
- generated_count
- accepted_count
- rejected_count
- duplicate_count
- result_checksum
- status
- started_at
- completed_at
- created_by
- metadata

Run status:

- pending
- running
- completed
- failed
- cancelled

Phase 3 can execute bounded runs synchronously. Do not introduce a distributed queue unless the stabilization audit proves there is already a real need.

## 3.6 CandidateSearchSpace

Create a versioned project-scoped search-space definition.

It should explicitly define what the generator is allowed to change.

At minimum support:

- material family restrictions;
- component rules;
- locked components;
- allowed substitutions;
- concentration/amount variation bounds;
- prohibited component keys/identifiers;
- required components;
- balance/compensation component where applicable;
- process-parameter variation bounds;
- maximum component count;
- normalisation/tolerance rules;
- candidate budget;
- notes;
- active/version/checksum;
- created_at.

Do not put everything into one unvalidated JSON field. Use structured child tables for scientifically important values; JSON may hold non-critical extensibility metadata.

## 3.7 SubstitutionRule

A substitution must be a curated, inspectable object.

Suggested fields:

- id
- organisation_id/project scope as appropriate
- material_family
- source_component_key
- replacement_component_key
- allowed_min_amount nullable
- allowed_max_amount nullable
- amount_basis
- reason
- evidence_id nullable
- status
- version
- created_at

Rule status:

- draft
- approved
- disabled

Only approved rules may be used by automatic Phase-3 generation.

A rule with no supporting evidence may still be manually approved in demo/research mode, but the UI must label the provenance as curator-provided rather than scientifically proven.

## 3.8 CandidateLineageEdge

Track parentage explicitly.

A candidate may have a parent that is:

- the baseline material;
- a known-material candidate;
- another hypothesis, if the allowed deterministic strategy is explicitly chaining transformations.

Store:

- child candidate/hypothesis
- parent material or parent candidate/hypothesis
- relationship type
- generation run
- sequence
- rationale

Do not allow lineage cycles.

## 3.9 CandidateChangeRecord

Every mutation should be inspectable.

Store typed/auditable records such as:

- component_substitution
- component_amount_change
- process_parameter_change
- known_material_selection
- manual_hypothesis

At minimum include:

- hypothesis/candidate
- sequence
- change type
- field path or semantic target
- before value/unit
- after value/unit
- rule id if relevant
- rationale

JSON can be used for before/after payloads if the record is typed and validated, but do not make lineage an arbitrary unstructured log.

---

# 4. CANDIDATE FINGERPRINTING AND DEDUPLICATION

Implement deterministic candidate fingerprinting.

A fingerprint must be based on a canonical scientific representation of the candidate, not database IDs or timestamps.

For a formulation hypothesis this should include, as appropriate:

- material family;
- normalized component identities;
- normalized component order;
- normalized amounts/basis/units;
- process-state values;
- relevant immutable generation semantics.

Requirements:

- same scientific candidate -> same fingerprint;
- different JSON key ordering -> same fingerprint;
- irrelevant display label -> does not change fingerprint;
- meaningful composition/process change -> changes fingerprint.

Use a versioned canonicalization algorithm and include the version in documentation.

Prevent duplicate candidates within a project/run using the fingerprint.

Do not silently discard duplicates. Count them in the run result and preserve enough run metadata to explain that they were deduplicated.

---

# 5. GENERATION STRATEGY INTERFACE

Evolve the Phase-1/2 `CandidateGenerator` contract into a real but still deterministic interface.

Example conceptual contract:

```python
class CandidateGenerator(Protocol):
    key: str
    version: str

    def validate_search_space(...): ...
    def generate(...): ...
```

Every strategy must declare:

- key;
- version;
- supported material families;
- required search-space inputs;
- deterministic behaviour contract;
- whether it creates hypotheses or selects known materials;
- maximum safe/bounded candidate count.

Strategies must be registered explicitly, not discovered through arbitrary imports.

---

# 6. REQUIRED PHASE-3 STRATEGIES

Implement a small set of high-integrity strategies rather than pretending to solve universal materials design.

## 6.1 Known Material Retrieval Strategy

Purpose:

Find existing materials in the Phase-2 knowledge graph that may be relevant to the replacement project.

This is **retrieval**, not generation.

Rules:

- respect organisation/private visibility;
- exclude the baseline material;
- respect allowed material families;
- evaluate known evidence using the Phase-2 selection engine;
- never fabricate missing properties;
- hard property constraint with missing evidence remains UNKNOWN;
- provide evidence completeness rather than a fake AI score;
- deterministic ordering.

Useful transparent ranking dimensions may include:

- number of hard constraints known-and-passed;
- number known-and-failed;
- number unknown;
- evidence coverage;
- condition applicability;
- conflict count.

Do not collapse this into an opaque single score.

## 6.2 Curated Component Substitution Strategy

Apply only approved `SubstitutionRule` records.

Example generic demo:

`Modifier B -> Alternative Modifier B2`

Requirements:

- preserve lineage;
- attach rule provenance;
- reject prohibited replacement components;
- respect amount bounds;
- preserve/renormalize formulation only according to explicit search-space rules;
- do not infer properties.

## 6.3 Bounded Composition Variation Strategy

Allow configured component amounts to vary only inside explicit user-supplied ranges.

Requirements:

- no random unconstrained chemistry;
- locked components never change;
- redacted components never become inferred values;
- required components remain present;
- prohibited components remain absent;
- percent-based compositions satisfy an explicit total/tolerance rule;
- if a balance component is configured, adjust it deterministically;
- if no valid compensation/normalisation rule exists, reject the combination.

Use a deterministic grid or deterministic seeded sampling when the full Cartesian product exceeds the candidate budget.

Do **not** use Bayesian or evolutionary optimisation in Phase 3.

## 6.4 Bounded Process Variation Strategy

Vary only explicitly listed process parameters/ranges.

Examples at the data-model level:

- generic cure temperature range;
- generic process temperature range;
- generic pressure range;
- generic dwell-time category/value if represented safely.

This phase is not allowed to output an operational hazardous synthesis protocol.

## 6.5 Manual Hypothesis Strategy

Allow a scientist to manually define a candidate hypothesis while still receiving:

- fingerprint;
- structural validation;
- lineage;
- change record;
- project association;
- explicit `manual` provenance.

Manual does not mean evidence-backed.

---

# 7. SEARCH-SPACE VALIDATION

Create a dedicated validation service.

Before a generation run begins, validate at least:

- baseline family compatibility;
- presence of a mutable baseline representation;
- redacted/incomplete baseline restrictions;
- approved substitution rules;
- component identity uniqueness;
- amount range ordering;
- unit/basis compatibility;
- percentage total rules;
- required components;
- prohibited components;
- locked components;
- process parameter range ordering;
- candidate budget boundaries;
- maximum combinatorial search size estimate.

The API should return structured errors such as:

```json
{
  "code": "REDACTED_BASELINE_COMPONENT",
  "path": "components[2]",
  "message": "Component cannot be mutated because its identity or amount is redacted."
}
```

Do not return a generic 500 for scientific validation failures.

---

# 8. STRUCTURAL PRE-SCREENING

Generated hypotheses must pass a transparent structural pre-screen before they become active candidates.

Possible checks:

- duplicate component identities;
- invalid/negative amounts;
- amount outside search-space range;
- percent total outside configured tolerance;
- prohibited component present;
- required component missing;
- locked component changed;
- material-family mismatch;
- invalid process parameter/unit;
- exact duplicate fingerprint.

Store rejection reason(s).

Do not use a generated property estimate to pre-screen in Phase 3.

---

# 9. PROPERTY CONSTRAINT BEHAVIOUR FOR HYPOTHESES

This is critical.

For **known-material candidates**:

- continue using Phase-2 evidence selection and conflict handling.

For **generated hypotheses**:

- property constraints with no independent observation/prediction must be `UNKNOWN`;
- do not copy baseline property observations;
- do not average parent properties;
- do not use heuristic chemistry rules to invent property values;
- do not convert structural validity into scientific performance.

The comparison UI/API should clearly distinguish:

- `KNOWN EVIDENCE`;
- `UNKNOWN — NOT YET PREDICTED/TESTED`.

Phase 4 will introduce property prediction with uncertainty. Do not pre-implement it now.

---

# 10. REPRODUCIBLE GENERATION RUNS

Each generation run must produce a reproducibility envelope containing:

- project id;
- replacement specification checksum;
- search-space checksum/version;
- strategy key/version;
- configuration checksum;
- random seed;
- canonicalization/fingerprint version;
- generated fingerprints in deterministic order;
- result checksum.

Running the same envelope twice must produce the same fingerprints and result checksum.

If the project specification or search space changes, the new run should clearly show that it is based on a different input checksum.

Do not mutate the historical run record.

---

# 11. BOUNDED EXECUTION AND EXPLOSION PROTECTION

Do not allow a user to accidentally generate millions of database rows in Phase 3.

Implement explicit limits.

Suggested defaults, configurable within safe boundaries:

- preview search-space cardinality before run;
- default candidate budget: modest (for example 100);
- hard local Phase-3 maximum: choose and document a defensible value such as 1,000;
- reject/require narrower search space if estimated enumeration is extreme;
- deduplicate before persistence where possible;
- persist run counts for generated/rejected/duplicate/accepted.

No distributed compute is required in Phase 3.

---

# 12. API REQUIREMENTS

Add clean typed endpoints. Exact URL design may improve, but cover these capabilities.

## Search spaces

- create search space for project;
- list versions;
- get version;
- validate search space;
- activate a version;
- clone/edit into a new version rather than mutating an executed version.

Example:

`POST /replacement-projects/{id}/search-spaces`

`POST /replacement-projects/{id}/search-spaces/{id}/validate`

## Substitution rules

- list/create/update draft rule;
- approve/disable rule;
- show evidence/provenance.

## Generation strategies

`GET /candidate-generation/strategies`

Return capabilities/requirements/version, not implementation secrets.

## Generation runs

`POST /replacement-projects/{id}/generation-runs/preview`

Return estimated search size and validation problems without creating candidates.

`POST /replacement-projects/{id}/generation-runs`

Execute a bounded run.

`GET /replacement-projects/{id}/generation-runs`

`GET /generation-runs/{run_id}`

`GET /generation-runs/{run_id}/candidates`

## Candidate hypotheses

- get candidate detail;
- get structured components/process state;
- get changes;
- get lineage;
- accept for later screening;
- reject/archive with reason.

## Manual hypothesis

Provide a typed endpoint that captures a user-created hypothesis through the same fingerprint/validation/lineage system.

## Comparison

Extend project comparison so known candidates and hypothesis candidates can coexist.

Do not break existing Phase-2 response contracts without a versioned/compatible migration strategy.

---

# 13. UI — CANDIDATE LAB

Add a serious engineering workflow to the existing project workspace.

Do not create a gimmicky AI/3D interface.

## 13.1 Candidate Lab overview

Show:

- baseline material;
- current replacement specification checksum/version;
- active search-space version;
- known candidates;
- generated hypotheses;
- latest generation runs;
- unresolved search-space validation issues.

## 13.2 Search Space Builder

The user should be able to inspect the baseline structured composition and configure:

- locked components;
- mutable components;
- permitted amount ranges;
- balance component;
- approved alternative components/rules;
- prohibited/required components;
- permitted process variables/ranges;
- candidate budget.

Redacted components must show a clear warning and cannot be silently edited by automatic generation.

Provide a **Validate Search Space** action before generation.

## 13.3 Generation Preview

Before execution show:

- strategies selected;
- estimated combinations;
- candidate budget;
- expected truncation/sampling if applicable;
- rules to be used;
- specification checksum;
- search-space checksum;
- random seed;
- validation errors/warnings.

Do not create candidates during preview.

## 13.4 Generation Run view

Display:

- run status;
- strategy/version;
- seed;
- input checksums;
- generated count;
- structurally rejected count;
- duplicate count;
- accepted count;
- result checksum.

## 13.5 Candidate table

For each candidate clearly label:

- `Known material` or `Hypothesis`;
- source strategy;
- lineage parent;
- number of changes;
- structural status;
- evidence coverage;
- hard constraint PASS/FAIL/UNKNOWN where actually knowable;
- conflicts for known evidence;
- status.

Do not display a fake overall AI score.

## 13.6 Candidate Hypothesis detail

Required sections:

- identity/status;
- hypothesis warning;
- structured composition;
- proposed process-state values;
- diff from baseline;
- change records;
- substitution-rule provenance;
- full lineage;
- property evidence posture;
- project constraints showing UNKNOWN where no evidence exists;
- generation-run reproducibility data;
- deterministic fingerprint.

Use wording such as:

> Hypothesis — not yet predicted, simulated, or experimentally validated.

## 13.7 Lineage visualization

A simple tree/timeline is sufficient.

Example:

`Baseline material -> substitution rule -> amount variation -> Candidate TL-H-0012`

Do not invest in elaborate graph animation.

---

# 14. SEEDED PHASE-3 DEMONSTRATION

Extend the existing generic engineering-polymer demo only with **clearly synthetic, generic component identities**.

Do not introduce unsourced real chemical performance claims.

For example, use generic labels such as:

- Base Resin A;
- Modifier B;
- Reinforcement C;
- Alternative Modifier B2.

Create deterministic demo data containing:

- one active search-space version;
- at least one locked component;
- at least one mutable amount range;
- one balance component;
- at least two approved generic substitution rules;
- one prohibited generic component key;
- one bounded process parameter;
- one manual hypothesis;
- one deterministic generation run;
- enough generated hypotheses to demonstrate deduplication/rejection/lineage without bloating the repository.

Generated hypotheses must have **no fabricated material-property observations**.

The existing known candidate materials retain their Phase-2 evidence.

The seed must remain idempotent.

---

# 15. KNOWN-MATERIAL RETRIEVAL EVIDENCE POSTURE

When the retrieval strategy sources an existing material, report a transparent evidence matrix rather than a single black-box score.

Example:

```text
Hard constraints known/pass: 3
Hard constraints known/fail: 1
Hard constraints unknown: 2
Soft constraints known: 2/4
Scientific conflicts: 1
Exact condition matches: 4
Fallback condition matches: 1
```

Deterministic ordering may use a documented tuple such as:

1. fewer known hard failures;
2. more known hard passes;
3. fewer unknown hard constraints;
4. greater evidence coverage;
5. fewer conflicts;
6. canonical material identifier as stable tie-breaker.

Do not represent unknown as pass.

---

# 16. PRIVACY / MULTI-TENANT SEAMS

Continue Phase-2 visibility/scoping behaviour.

At minimum:

- private project search spaces are organisation-scoped;
- private substitution rules are organisation-scoped;
- generated hypotheses are project/organisation-scoped;
- generation runs cannot be read across organisation scope;
- known-material retrieval cannot use another organisation's private materials;
- lineage cannot expose a private parent/source to an unscoped request;
- fingerprints/checksums must not encode secret raw content in a reversible form.

The existing `X-Organisation-ID` mechanism is still only a development scoping seam, not production authentication. Do not claim otherwise.

---

# 17. PERFORMANCE

Phase 3 introduces potentially many candidates, so explicitly test data-access behaviour.

Requirements:

- no query-per-candidate-per-property loop;
- batch known-material evidence selection;
- batch lineage/change loading;
- paginate candidate lists;
- database indexes for project/run/fingerprint/status;
- deduplicate before unnecessary expensive persistence;
- candidate-generation preview should not insert rows.

Create a bounded synthetic performance test/profile such as:

- 500 generated hypotheses;
- list/paginate candidates;
- retrieve one candidate with lineage;
- compare a page of known/hypothesis candidates.

Document SQL-query shape/count or another defensible profile. Do not publish arbitrary production latency claims from SQLite.

---

# 18. TESTING

Phase 3 must substantially extend automated tests while keeping every Phase-1/2 test green.

## 18.1 Migration tests

Verify:

- 0002 data survives 0003 upgrade;
- existing candidate rows become `known_material` correctly;
- exactly-one-of material/hypothesis invariant;
- new indexes/constraints.

## 18.2 Fingerprint tests

- deterministic across reruns;
- insensitive to irrelevant ordering/labels;
- sensitive to meaningful composition change;
- process change affects fingerprint where configured;
- duplicate candidate identified.

## 18.3 Search-space validation tests

- invalid range rejected;
- incompatible basis rejected;
- locked component mutation rejected;
- prohibited component rejected;
- required component enforced;
- redacted baseline mutation blocked;
- extreme cardinality rejected/limited;
- invalid process-unit range rejected.

## 18.4 Strategy tests

### Known material retrieval

- baseline excluded;
- private visibility respected;
- deterministic ranking;
- unknown evidence remains unknown;
- conflict state preserved.

### Curated substitution

- only approved rule used;
- disabled/draft rule ignored;
- provenance attached;
- amount bounds enforced.

### Composition variation

- deterministic output;
- within bounds;
- locked components unchanged;
- total normalisation valid;
- candidate budget respected.

### Process variation

- only allowed parameters change;
- bounds/units respected.

### Manual hypothesis

- same validation/fingerprint/lineage requirements.

## 18.5 Reproducibility tests

Same:

- project spec checksum;
- search-space checksum;
- strategy version;
- configuration;
- seed

must produce the exact same ordered fingerprint list/result checksum.

Changing a meaningful input must change the run checksum/results where expected.

## 18.6 Scientific integrity tests

This is mandatory:

- generated hypotheses have zero inherited/fabricated property observations;
- hypothesis property constraints show UNKNOWN;
- known materials still use Phase-2 evidence selection;
- no generated hypothesis is inserted into the canonical materials graph merely by generation;
- hypothesis warning/status returned by API.

## 18.7 API tests

Cover:

- search-space create/version/validate;
- rule approval/disable;
- generation preview;
- run execute;
- run reproducibility;
- candidate pagination;
- hypothesis details;
- lineage/change records;
- accept/reject status;
- manual hypothesis;
- scope/privacy.

## 18.8 Frontend tests

Add tests for:

- Search Space Builder validation state;
- Generation Preview does not execute;
- Generation Run summary;
- hypothesis warning;
- candidate diff/lineage;
- UNKNOWN property posture;
- no fake score.

---

# 19. OBSERVABILITY

Extend the structured logging introduced earlier.

Generation-run events should include:

- request/correlation id;
- generation run id;
- project id;
- strategy key/version;
- spec checksum prefix;
- search-space checksum prefix;
- seed;
- candidate counts;
- duration;
- failure code.

Do not log private raw formulations or imported raw source payloads by default.

---

# 20. DOCUMENTATION

Create/update at minimum:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_MODEL.md`
- `docs/ERD.md`
- `docs/PHASE2_STABILIZATION_FOR_PHASE3.md`
- `docs/PHASE3_SCOPE.md`
- `docs/CANDIDATE_MODEL.md`
- `docs/CANDIDATE_GENERATION.md`
- `docs/SEARCH_SPACE.md`
- `docs/GENERATION_REPRODUCIBILITY.md`
- `docs/CANDIDATE_LINEAGE.md`
- `docs/SCIENTIFIC_INTEGRITY.md`
- `docs/PRIVACY_MODEL.md`
- `docs/FUTURE_ARCHITECTURE.md`

Document the candidate fingerprint canonicalization format/version explicitly.

Update the ERD instead of leaving Phase-3 tables undocumented.

---

# 21. EXPLICITLY DO NOT IMPLEMENT IN PHASE 3

Do not implement:

- LLM material invention;
- internet-wide material generation;
- MatterGen;
- property ML models;
- graph neural property predictors;
- ML force fields;
- DFT;
- Quantum ESPRESSO execution;
- LAMMPS execution;
- molecular dynamics;
- CALPHAD;
- HPC scheduling;
- Bayesian optimisation;
- evolutionary algorithms;
- active learning;
- reinforcement learning;
- patent search;
- novelty claims;
- autonomous synthesis planning;
- hazardous experimental procedures;
- lab robotics;
- model training;
- vector DB without a separately justified need;
- Kubernetes;
- microservice decomposition;
- production SSO/billing unless strictly needed to repair an existing security defect.

Phase 4 is the property-prediction phase. Do not consume it now.

---

# 22. REQUIRED PHASE-3 QUALITY CHECK

Before declaring Phase 3 complete:

1. Run Docker Compose from a clean checkout.
2. Use real PostgreSQL.
3. Apply migrations through `0003`.
4. Prove Phase-1/2 data migration integrity.
5. Run deterministic seed twice.
6. Run all backend tests.
7. Run Ruff.
8. Run Mypy.
9. Run frontend tests.
10. Run full TypeScript typecheck.
11. Run ESLint.
12. Run Next production build.
13. Open the application in a browser.
14. Create/validate a search space.
15. Preview a generation run without persistence.
16. Execute a bounded deterministic run.
17. Rerun with same envelope and prove same fingerprints/checksum.
18. Inspect a generated hypothesis.
19. Confirm no fabricated property observations exist.
20. Confirm project constraints show UNKNOWN for unsupported hypothesis properties.
21. Inspect complete candidate lineage/change history.
22. Confirm known-material candidates still use condition-aware Phase-2 evidence.
23. Confirm private search spaces/runs/hypotheses do not leak unscoped.
24. Profile candidate list/comparison query behaviour.
25. Check browser console.
26. Check responsive behaviour.
27. Remove debug/dead/generated code and caches.
28. Update documentation accurately.

Do not mark an unavailable/unexecuted check PASS.

---

# 23. PHASE-3 ACCEPTANCE CRITERIA

Phase 3 is complete only if:

- Phase-2 stabilization gate is completed on real dependencies;
- forward `0003` migration works;
- existing known candidates survive migration;
- known materials and hypotheses coexist cleanly;
- search spaces are typed/versioned/checksummed;
- search-space validation is explicit;
- generation strategies are registered/versioned;
- known-material retrieval is deterministic/evidence-aware;
- curated substitution works only from approved rules;
- bounded composition variation works;
- bounded process variation works;
- manual hypotheses use the same integrity model;
- every generated hypothesis has deterministic fingerprint;
- duplicates are detected/countable;
- every generated hypothesis has lineage/change provenance;
- generated hypotheses receive no fabricated property observations;
- unknown property evidence remains UNKNOWN;
- generated runs are reproducible from checksum/seed/version envelope;
- run history is immutable/auditable;
- generated candidate counts are bounded;
- privacy scope is maintained;
- Candidate Lab UI is usable;
- tests/lint/typecheck/build pass in a normal dependency environment;
- docs reflect actual implementation.

---

# 24. FINAL DELIVERY

Return a clean ZIP of the complete Phase-3 repository.

Do not include:

- `node_modules`;
- Python virtual environments;
- `.next`;
- build artifacts;
- test SQLite files;
- caches;
- debug dumps;
- local secrets;
- unnecessary binaries.

Provide a detailed implementation report containing:

## Phase-2 stabilization

Exact fixes and exact test/build results.

## Implemented

Actual Phase-3 functionality.

## Candidate architecture

How known materials vs hypotheses are represented.

## Scientific integrity

How the code guarantees generated candidates do not acquire fabricated property evidence.

## Generation strategies

Implemented strategies and limitations.

## Reproducibility

Checksums, versions, seeds, fingerprint algorithm and test proof.

## Database

Migration/table/constraint/index changes.

## Tests

Exact counts/results.

## Performance profile

Bounded candidate/query profile with context.

## Security/privacy

Scope behaviour and known limits.

## Known limitations

Be explicit.

## Deferred to Phase 4+

List everything deliberately postponed.

## Run commands

Exact clean-machine commands.

## Phase-3 verification checklist

Mark every acceptance criterion `PASS`, `FAIL`, or `UNVERIFIED` and explain every non-PASS item.

Do not claim PASS without executing the check.

---

# 25. STOP CONDITION

At the end of Phase 3, **stop**.

Do not start Phase 4 automatically.

The next package will be audited first. Phase 4 will introduce the **Property Prediction & Uncertainty Engine**, and its design must be based on the actual Phase-3 candidate model and any defects discovered during that audit.
