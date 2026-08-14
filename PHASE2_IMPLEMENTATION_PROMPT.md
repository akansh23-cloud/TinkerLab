# TinkerLab — Phase 2 Implementation Prompt

You are continuing an existing TinkerLab repository. Do **not** rebuild Phase 1 from scratch.

Act as the founding Principal Engineer, Scientific Software Architect, Materials Informatics Engineer, Data Architect, Product Architect, and senior full-stack engineer.

TinkerLab is a Material Replacement & Discovery Operating System. Phase 1 already establishes the replacement-project foundation. Phase 2 must turn the material/evidence layer into a rigorous **Materials Knowledge & Evidence Graph** that future candidate generation, ML prediction, simulation, novelty analysis, and laboratory feedback can trust.

## 0. FIRST: AUDIT AND STABILIZE THE ACTUAL PHASE-1 REPOSITORY

Before implementing any Phase-2 feature, inspect the entire repository and read:

- `README.md`
- `IMPLEMENTATION_REPORT.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_MODEL.md`
- `docs/EVIDENCE_MODEL.md`
- `docs/REPLACEMENT_SPECIFICATION.md`
- `docs/PHASE1_SCOPE.md`
- `docs/FUTURE_ARCHITECTURE.md`
- `docs/ERD.md`

Phase 1 was source-audited in an offline environment. Backend tests passed there, but Docker/PostgreSQL and the dependency-resolved Next build could not be executed. Therefore the **first Phase-2 gate is mandatory**:

1. Install backend and frontend dependencies.
2. Run `docker compose up --build` against PostgreSQL.
3. Run Alembic from an empty PostgreSQL database.
4. Run the deterministic seed twice and prove idempotency.
5. Run all backend tests.
6. Run Ruff and Mypy (or fix/configure them appropriately; do not suppress real defects).
7. Run frontend tests.
8. Run ESLint.
9. Run TypeScript type checking.
10. Run `next build`.
11. Exercise the complete Phase-1 wizard in a browser.
12. Open the seeded material passports.
13. Open comparison and specification views.
14. Confirm there are no browser console errors or API 500s.
15. Fix all P0/P1 issues discovered before starting Phase 2.

Do not mark this gate complete unless it actually passed. If a Phase-1 schema or migration defect must be corrected, add a forward Alembic migration; do not rewrite production history casually after the database has been initialized.

---

# 1. PHASE-2 GOAL

Build a trustworthy **Materials Knowledge & Evidence Graph**.

By the end of Phase 2, TinkerLab should be able to answer:

- What exactly is this material?
- Which identifiers and aliases refer to it?
- What is its composition/formulation representation?
- Which scientific properties have been reported?
- Under what conditions were they reported?
- Where did each observation come from?
- Is the value experimental, supplier-reported, computational, predicted, user-provided, or demo-only?
- What measurement/computational method produced it?
- What is its uncertainty and confidence posture?
- Do multiple sources disagree?
- Which source/observation should be used for a particular comparison context, and why?
- What raw external/imported record produced the normalized TinkerLab entity?
- Has that source record changed since ingestion?
- Can the entire provenance chain be reconstructed later?

This phase is about **knowledge quality, provenance, identity resolution, and evidence selection**.

It is NOT about inventing candidates.

---

# 2. NON-NEGOTIABLE SCIENTIFIC RULES

## 2.1 Never collapse conflicting observations into a fake single truth

If three sources report three tensile-strength values under different conditions, store all three.

Do not average them automatically.

A later selection service may choose the most applicable observation for a specified context, but it must return the selection rationale and alternatives.

## 2.2 Conditions are part of the scientific value

A property observation is not just:

`value + unit`

It is:

`property + value + unit + material state + method + conditions + evidence + uncertainty + provenance`.

Temperature, humidity, pressure, strain rate, sample orientation, processing state, age, wavelength/frequency, etc. may matter depending on the property.

Do not create one giant untyped `conditions` object and call the problem solved. Keep an extensible JSON field if useful, but introduce typed/common condition fields or a well-defined condition schema for the most important Phase-2 cases.

## 2.3 Raw source data must remain traceable

External/imported data must preserve:

- provider/source
- external record identifier
- retrieval/import timestamp
- source URL/reference when permitted
- source version where available
- raw payload checksum
- normalized record checksum
- parser/adapter version
- original raw payload or immutable raw artifact reference where licensing permits

## 2.4 Source confidence is not scientific certainty

Do not turn a supplier sheet into “0.95 truth”.

Separate concepts such as:

- source quality
- evidence type
- measurement uncertainty
- model uncertainty
- applicability/domain similarity
- curator confidence

If Phase 1 has a generic `confidence` field, preserve compatibility but document its semantics and introduce more precise fields rather than overloading it indefinitely.

## 2.5 No fake external integration

If an external provider requires an API key or network connection, implement a real adapter and a deterministic recorded fixture for tests.

Never silently substitute invented provider responses.

---

# 3. DOMAIN MODEL EXPANSION

Extend the existing model with carefully normalized entities. Exact names may change if justified, but preserve the concepts.

## 3.1 MaterialIdentifier

A material can have multiple identifiers/aliases.

Fields/concepts:

- id
- material_id
- namespace/type
- value
- normalized_value
- is_primary
- source/evidence link
- created_at

Namespaces may include:

- internal TinkerLab canonical name
- common name
- trade name
- CAS where applicable
- Materials Project ID where applicable
- DOI-linked material label
- supplier code
- customer code
- custom external namespace

Do not imply every material family has CAS or a crystal database ID.

Add uniqueness policies that make sense per namespace.

## 3.2 MaterialAlias / naming

If aliases can be represented cleanly through `MaterialIdentifier`, do not create a redundant table. If separate naming semantics are needed, justify them.

## 3.3 Composition / formulation representation

Phase 1 has `composition_summary`. Preserve it for display/backward compatibility but add structured representation.

The representation must not pretend all material families are identical.

Support at least a generic component model:

- material_id
- component identifier/name
- component role
- amount/value
- amount unit/basis
- lower/upper range where needed
- uncertainty if applicable
- source/evidence
- ordering/notes

Examples of basis:

- mass fraction
- weight percent
- mole fraction
- atomic percent
- volume fraction
- parts by weight
- qualitative/present

For crystalline materials, leave a clean extension path to lattice/structure representation but do not implement a full crystallography stack unless required for a real provider adapter.

For proprietary formulations, allow components to be redacted or represented by customer-private identifiers without breaking the model.

## 3.4 Processing / material state

Introduce a first-class representation for relevant material state/process history rather than hiding it only in prose.

Possible concepts:

- ProcessDefinition
- MaterialProcessStep
- MaterialState

Examples:

- annealed
- quenched
- aged
- cured
- extruded
- injection molded
- coating thickness/state

Keep Phase-2 scope modest but establish a model that later simulation/manufacturing phases can use.

## 3.5 SourceProvider

Represents an origin/provider, not an individual evidence claim.

Examples:

- TinkerLab user import
- Materials Project
- internal customer dataset
- supplier datasheet collection
- curated demo data

Fields/concepts:

- id
- key
- display_name
- provider_type
- base/reference URL where appropriate
- terms/licensing notes
- enabled
- adapter_version
- created_at / updated_at

## 3.6 SourceRecord / IngestionRecord

Every imported external record should have an immutable ingestion/provenance identity.

Fields/concepts:

- id
- provider_id
- external_record_id
- retrieved_at/imported_at
- source_version
- parser_version
- raw_checksum
- normalized_checksum
- raw_payload / object-store reference / permitted snapshot
- status
- error details if ingestion failed
- metadata

Use JSONB where appropriate, but do not replace normalized scientific entities with raw blobs.

## 3.7 Evidence expansion

Extend existing `Evidence` rather than replacing it without migration.

Add concepts such as:

- provider/source record link
- citation/publication link if applicable
- evidence status (`reported`, `reviewed`, `superseded`, `retracted`, etc. where meaningful)
- evidence date
- curator note
- source-quality classification
- raw artifact/reference
- parent evidence/provenance edge

Do not create an overly complicated ontology; prioritize useful provenance.

## 3.8 Citation / Publication

Create a normalized citation entity suitable for literature-derived evidence.

Suggested fields:

- id
- title
- DOI
- authors (structured JSON or child table; justify choice)
- journal/source
- publication year/date
- URL/reference
- publisher
- metadata

Avoid scraping full copyrighted paper text into the database in Phase 2.

## 3.9 Observation expansion

Upgrade `MaterialPropertyObservation` so it can represent scientific context without breaking Phase 1.

Consider fields/entities for:

- value type
- numeric/boolean value
- canonicalized value cache if useful
- reported unit
- measurement/computation method
- sample/material state
- condition set
- uncertainty type
- uncertainty lower/upper or standard deviation where appropriate
- evidence ID
- source record ID
- validity/supersession status
- observed/reported date
- ingestion timestamp

Do not store both reported and canonical values unless there is a clear consistency strategy.

## 3.10 ObservationConditionSet

Create an explicit typed condition representation or controlled schema.

At minimum Phase 2 should understand commonly useful conditions such as:

- temperature
- pressure
- humidity
- strain rate
- sample orientation
- frequency
- material/process state

Not every field applies to every property. Null is acceptable. Extensibility metadata is acceptable for property-specific dimensions.

Units must be validated.

---

# 4. MATERIAL IDENTITY AND DEDUPLICATION

Implement a deterministic material identity service.

It should help decide whether an incoming record:

- matches an existing material confidently
- is a possible match requiring human review
- is new

Use conservative rules.

Possible signals:

- exact trusted external identifier
- canonical normalized name
- structured composition similarity
- source-specific IDs

Do NOT use an LLM or embedding similarity to silently merge scientific entities.

Provide:

- match reason
- confidence class (`exact`, `probable`, `ambiguous`, `none`) rather than fake probability if not calibrated
- candidate matches

Ambiguous matches require explicit user/curator action.

Create merge support only if it is safe and fully provenance-preserving. A merge must never discard evidence or source records.

---

# 5. PROPERTY OBSERVATION SELECTION ENGINE

Phase 1 uses the most recent observation. Replace that simplistic rule with an explicit **ObservationSelectionService**.

Input:

- material
- property key
- desired condition context
- allowed evidence types/source policies
- optional minimum evidence requirements

Output:

- selected observation OR `UNKNOWN`
- selection rationale
- applicability score/class
- alternative observations considered
- conflicts detected
- excluded observations and reasons

Do not invent a universal scientific ranking.

Start with transparent deterministic policy such as:

1. exact condition match beats unknown condition
2. experimental/literature/supplier/computational categories are not globally ranked without policy; allow project/provider policy
3. non-superseded beats superseded
4. more complete conditions can be preferred when relevant
5. explicit curator preference can override with audit trail
6. ties remain conflicts, not silently averaged

Candidate comparison must call this service rather than selecting the newest row directly.

Add tests proving condition-aware selection changes the chosen observation when appropriate.

---

# 6. EVIDENCE CONFLICT DETECTION

Implement transparent conflict detection.

For a material/property/context, identify when multiple applicable observations disagree materially.

Do not hardcode one universal percentage threshold for all scientific properties.

Support property-definition conflict policies, such as:

- absolute tolerance
- relative tolerance
- uncertainty-overlap rule
- informational-only/no auto-conflict policy

Output a structured conflict object:

- property
- observations involved
- normalized values
- conditions
- uncertainty
- reason conflict was raised
- resolution state

UI must expose conflicts clearly.

---

# 7. INGESTION FRAMEWORK

Implement a `MaterialDataProvider` system using the existing protocol boundary, now with real provider contracts.

Required concepts:

- provider registry
- provider capabilities
- fetch/search/normalize methods as appropriate
- adapter version
- rate-limit/error handling
- raw source record persistence
- deterministic normalization
- idempotent ingestion
- dry-run preview
- import report

Do not introduce Kafka/Celery/Kubernetes in Phase 2.

A synchronous API/CLI ingestion path is enough for modest datasets. If a lightweight background job is genuinely needed for UX, keep it simple and explain why.

## 7.1 Local CSV/JSON import — REQUIRED

Implement a robust user-facing import flow before depending on external APIs.

Support a documented schema for:

- materials
- identifiers
- compositions
- property observations
- evidence/source references
- conditions

Provide:

- validation preview
- row-level errors
- dry run
- import commit
- import summary
- idempotency key/checksum

Never partially import silently. Use clear transaction/batch semantics.

Provide downloadable example templates in the repository.

## 7.2 Materials Project adapter — OPTIONAL BUT PREFERRED IF CURRENT API ACCESS IS PRACTICAL

Use the current official Materials Project API/documentation only.

Before coding, verify the current client/API requirements from official sources.

If implemented:

- use an environment variable/API key as required
- never commit credentials
- store Materials Project IDs as identifiers
- preserve raw/provider provenance
- normalize only the small set of fields that map cleanly to TinkerLab
- do not pretend computed properties are experimental
- mark evidence as computational/provider-specific
- use recorded deterministic fixtures for tests
- respect provider terms/licensing and document them

If access cannot be verified, implement the provider interface and fixture-backed normalization test but mark live adapter execution as unverified rather than fabricating success.

Do NOT implement broad web scraping.

---

# 8. UNIT SYSTEM HARDENING

Phase 1 has a Pint-backed units layer with an offline fallback.

In a normal networked Phase-2 environment:

1. install and exercise Pint
2. make Pint the required runtime path
3. retain only a very small emergency/test fallback if there is a strong reason; otherwise remove it after verified dependency installation
4. add property-specific unit policies
5. add condition-unit validation
6. add more unit tests
7. ensure offset units are handled correctly
8. ensure percentage/fraction basis is explicit for composition

Do not implement live FX conversion for cost units.

---

# 9. API EXPANSION

Add clean REST endpoints while preserving Phase-1 endpoints.

Suggested resources:

- `/materials/{id}/identifiers`
- `/materials/{id}/composition`
- `/materials/{id}/process-state`
- `/materials/{id}/observations`
- `/materials/{id}/evidence-summary`
- `/materials/{id}/conflicts`
- `/observations/{id}`
- `/observations/{id}/provenance`
- `/source-providers`
- `/source-records/{id}`
- `/citations`
- `/imports`
- `/imports/preview`
- `/imports/{id}`
- `/materials/resolve-identity`
- `/properties/{key}/selection-preview`

Exact routing may differ if you design a cleaner resource model.

Requirements:

- pagination
- filters
- stable response schemas
- structured errors
- no ORM leakage
- correlation IDs
- OpenAPI examples
- authorization seam retained for future enterprise phase

---

# 10. UI / PRODUCT EXPERIENCE

Extend the existing restrained scientific UI.

Do not redesign it into a sci-fi dashboard.

## 10.1 Materials Explorer

Add searchable/filterable material explorer with:

- material name
- family
- identifiers
- evidence coverage
- conflict indicator
- source-provider badges
- seed/demo flag

## 10.2 Material Passport v2

Add sections:

### Identity

- canonical name
- aliases/identifiers
- family
- source providers

### Composition / formulation

- structured component table
- amount + basis
- evidence/source
- redaction state

### Processing/state

- current known process/material-state information

### Properties

For each property show:

- selected observation
- reported value/unit
- canonical value/unit where useful
- conditions
- method
- uncertainty
- evidence type/source
- conflict badge
- number of alternative observations

Clicking opens an observation inspector.

### Evidence

Group evidence by source/provider/type.

### Provenance

Show a readable provenance chain:

`provider record → normalization/import → evidence → observation → selected use in project`

A simple list/timeline is acceptable. Do not build a complex graph visualization unless it improves usability.

## 10.3 Observation Inspector

Show:

- all fields
- conditions
- evidence
- citation
- source record
- raw payload checksum
- normalization/parser version
- alternatives/conflicts

## 10.4 Conflict Review

Provide a screen/panel where a scientist can see conflicting observations and optionally record a curator preference/rationale.

Never delete the rejected observation.

## 10.5 Import Center

Provide:

- upload CSV/JSON
- preview validation
- row errors
- dry-run summary
- commit import
- result report

No fake progress bars.

---

# 11. UPDATE PHASE-1 COMPARISON ENGINE

Candidate evaluation must stop using “latest observation wins”.

Integrate the new observation-selection service.

For every candidate property used in a project comparison, return:

- selected observation ID
- selection rationale
- conditions/applicability
- evidence source
- conflict status
- alternatives count
- canonical value
- uncertainty
- confidence/quality fields with precise semantics

If no applicable evidence exists, return UNKNOWN.

Do not let the knowledge graph create a hidden opaque score.

---

# 12. DATA PRIVACY / CUSTOMER DATA SEAM

Phase 2 is not the enterprise-security phase, but the data model must not make future isolation impossible.

Add organisation ownership/source scope where needed for:

- private material aliases
- private formulations/compositions
- private evidence
- imports
- source records

Do not expose one organisation's private record through global material search accidentally.

The demo organisation can remain simple, but tests must cover basic scope boundaries if new private records are introduced.

---

# 13. MIGRATION STRATEGY

Use forward Alembic migrations from the Phase-1 schema.

Requirements:

- preserve Phase-1 seeded project IDs and material references
- migrate existing observations safely
- populate sensible `value_type`/source defaults
- do not drop evidence
- no destructive migration without explicit justification
- test upgrade from a Phase-1 database snapshot
- test fresh install from zero

Add a migration test or documented automated verification script.

---

# 14. TESTING REQUIREMENTS

Increase test depth substantially.

## Backend unit tests

At minimum:

- material identifier normalization
- duplicate identifier handling
- composition amount/basis validation
- private/redacted component behavior
- condition unit validation
- evidence/source-record linkage
- source record checksum determinism
- idempotent ingestion
- observation selection exact-condition match
- observation selection missing-condition fallback
- conflicting observations remain separate
- conflict detection policy
- superseded evidence exclusion
- curator preference behavior
- UNKNOWN when no applicable observation exists
- boolean observation selection
- numeric unit normalization via Pint

## API integration tests

- import preview with valid and invalid rows
- commit valid import
- repeat import idempotently
- material identity resolution
- fetch passport with identifiers/composition/evidence
- fetch observation provenance
- conflict endpoint
- candidate comparison uses selected observation rather than latest row
- organisation-private record cannot leak into unrelated scope

## Migration tests

- Phase 1 → Phase 2 upgrade preserves seeded project
- fresh DB → head migration
- seed remains idempotent

## Frontend tests

At minimum cover:

- material explorer filter/search behavior
- passport observation selection/conflict display
- observation inspector evidence/provenance
- import validation errors
- conflict review action
- PASS/FAIL/UNKNOWN labels remain explicit

## End-to-end smoke path

Prefer Playwright if introducing it is justified and stable:

1. open dashboard
2. open seeded project
3. open material passport
4. inspect an observation
5. view provenance
6. import a small fixture in dry-run mode
7. commit it
8. see new material/observation
9. compare a candidate using the selected evidence

Do not add a huge E2E framework if it makes the repository unstable; explain the choice.

---

# 15. PERFORMANCE / DATA ACCESS

Add indexes based on actual query paths:

- material identifier namespace/value
- material family/name
- observations by material/property/status
- evidence by provider/type
- source record provider/external ID
- imports by organisation/status/time

Avoid N+1 queries in material passport and comparison APIs.

Measure/query-profile the seeded project path and at least one larger synthetic fixture.

Do not prematurely add Elasticsearch/vector search.

---

# 16. SECURITY BASELINE

Preserve Phase-1 controls and add:

- file upload type/size limits
- safe CSV parsing
- no formula execution
- no arbitrary path writes
- bounded JSON payloads
- provider credential isolation through environment/secrets
- source URL handling that does not become an SSRF primitive
- no raw secret logging
- explicit allowed CORS origins

If importing spreadsheet formulas, treat them as data, never execute them.

---

# 17. DOCUMENTATION

Update existing docs and add:

- `docs/MATERIAL_IDENTITY.md`
- `docs/COMPOSITION_MODEL.md`
- `docs/CONDITIONS_MODEL.md`
- `docs/PROVENANCE.md`
- `docs/OBSERVATION_SELECTION.md`
- `docs/CONFLICT_POLICY.md`
- `docs/INGESTION.md`
- `docs/DATA_PROVIDERS.md`
- `docs/PHASE2_SCOPE.md`

Update ERD and architecture diagrams.

Document clearly which data is:

- reported
- normalized
- selected
- computational
- experimental
- supplier
- user-provided
- demo-only

---

# 18. DO NOT IMPLEMENT IN PHASE 2

Explicitly exclude:

- autonomous candidate generation
- MatterGen
- property ML models
- training pipelines
- DFT execution
- molecular dynamics
- CALPHAD
- HPC orchestration
- Bayesian optimization
- evolutionary search
- active learning experiment selection
- patent novelty search
- autonomous lab control
- robotics
- manufacturing/economic replacement scoring beyond existing transparent values
- production SSO
- billing
- Kubernetes
- vector database unless a concrete Phase-2 requirement proves it necessary (default: no)

Do not sneak these in as “helpers”.

---

# 19. PHASE-2 SEEDED DEMONSTRATION

Extend the existing deterministic demo rather than replacing it.

Create a richer evidence scenario that demonstrates:

- one material with multiple identifiers
- structured composition components
- a process/material state
- at least two observations for the same property under different conditions
- at least one real conflict according to a property conflict policy
- at least one observation superseded or curator-deprioritized
- evidence from multiple types/providers, still clearly demo-only unless genuinely sourced
- one candidate where condition-aware selection changes which observation is used
- one candidate with no applicable observation → UNKNOWN
- a CSV/JSON import fixture that adds a new demo material idempotently

All synthetic values must remain `seed_demo` or equivalent explicit demo provenance.

---

# 20. REQUIRED QUALITY GATE BEFORE COMPLETION

Do not declare Phase 2 complete until all applicable checks actually pass:

1. clean checkout
2. dependency install
3. fresh PostgreSQL start
4. migration from zero
5. deterministic seed
6. migration from Phase-1 snapshot
7. seed idempotency
8. backend unit/integration tests
9. migration tests
10. Ruff
11. Mypy
12. frontend tests
13. ESLint
14. TypeScript typecheck
15. Next production build
16. browser smoke flow
17. import dry run
18. import commit
19. repeated import idempotency
20. passport provenance inspection
21. conflict inspection
22. project comparison using condition-aware observation selection
23. API/OpenAPI review
24. browser console clean
25. no fake buttons / dead code / debug dumps
26. dependency/security review
27. docs match implementation

Do not suppress warnings/errors solely to make CI green.

---

# 21. PHASE-2 ACCEPTANCE CRITERIA

Phase 2 is complete only when:

- Phase-1 functionality remains intact
- full Docker/PostgreSQL stack is verified
- frontend production build is verified
- materials can have multiple identifiers
- structured composition/formulation data exists
- material process/state can be represented
- source providers and immutable ingestion records exist
- evidence is traceable to source records
- citations/publications can be represented without storing copyrighted full text
- observations carry structured conditions
- multiple observations per property are preserved
- condition-aware observation selection works
- conflicting observations are detectable and visible
- selection rationale is returned
- CSV/JSON dry-run and import work
- import is idempotent
- material identity resolution is conservative and reviewable
- candidate comparison uses the selection service
- missing applicable evidence remains UNKNOWN
- organisation-private imported data does not leak
- migrations preserve Phase-1 data
- tests pass
- documentation is current

---

# 22. FINAL DELIVERY

Return a clean ZIP without:

- `node_modules`
- Python virtual environments
- `.next`
- build outputs
- caches
- temporary imports
- raw secrets
- debug dumps
- large downloaded datasets

Before zipping, include a `PHASE2_IMPLEMENTATION_REPORT.md` with:

## Stabilization gate

Exact results of Docker/PostgreSQL/Next verification and every Phase-1 defect fixed.

## Implemented

Actual Phase-2 functionality only.

## Schema/migrations

Forward migrations and preserved compatibility.

## Providers/imports

Which adapters were actually exercised live versus fixture-only.

## Evidence/provenance

How source record → evidence → observation → selection is represented.

## Observation selection

Policy and limitations.

## Conflicts

Detection/resolution behavior.

## Tests

Exact commands and exact results.

## Performance

Any measured query/import results.

## Known limitations

Be explicit.

## Deferred to Phase 3+

List every postponed feature.

## Verification checklist

Mark each acceptance criterion PASS / FAIL / UNVERIFIED. Never claim PASS without execution.

Finally, stop. Do **not** begin Phase 3 candidate generation until the completed Phase-2 repository has been audited.
