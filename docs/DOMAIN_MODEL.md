# Domain Model — Phase 2

## Material identity

`Material` remains the canonical TinkerLab entity. It now has optional organisation ownership and visibility. `MaterialIdentifier` represents namespace-specific IDs/aliases such as TinkerLab ID, common name, supplier/customer code or provider ID.

Identity resolution is conservative: trusted exact external identifiers can produce `exact`; normalized names may produce `probable`; ambiguous signals require review. No LLM or embedding silently merges materials.

## Composition

`MaterialComponent` stores component name/identifier, role, quantitative value/range, unit, basis, uncertainty and evidence. Redacted components retain a private label without requiring disclosure of chemistry.

Supported bases include weight percent, mass fraction, mole fraction, atomic percent, volume fraction, parts by weight and qualitative presence.

## Processing/state

`MaterialProcessState` provides ordered state/process records with structured parameters and evidence linkage. It does not attempt to model a full manufacturing ontology in Phase 2.

## Evidence/provenance

`SourceProvider` → `SourceRecord` → `Evidence` → `MaterialPropertyObservation`.

`Citation` represents bibliographic metadata only; Phase 2 does not ingest copyrighted full paper text.

## Observation

Observations support numeric or boolean values, typed condition sets, legacy free-form conditions, uncertainty fields, method, evidence/source-record linkage, active/superseded/retracted status and curator preference.

## Project objects

Phase-1 `ReplacementProject`, `Constraint`, `Objective` and `Candidate` remain intact. Candidate generation remains excluded. Candidate comparison now resolves evidence through the Phase-2 selection service.

## Phase-3 generation entities

- `CandidateSearchSpace`: versioned bounded generator input.
- `SearchSpaceComponentRule`: component-level mutability/guard/range rule.
- `SearchSpaceProcessRule`: bounded process-state variable.
- `SubstitutionRule`: curator-controlled substitution authorization.
- `GenerationRun`: immutable/auditable generation envelope and summary.
- `GenerationRunResult`: ordered fingerprint/disposition record.
- `CandidateHypothesis`: non-canonical proposed material/formulation.
- `CandidateHypothesisComponent`: concrete proposed component.
- `CandidateHypothesisProcessParameter`: concrete proposed process-state value.
- `CandidateLineageEdge`: explicit parentage/rationale.
- `CandidateChangeRecord`: typed before/after mutation record.

`Candidate` now discriminates `known_material` versus `hypothesis`, with a database invariant requiring exactly one target. Existing Phase-1/2 candidates remain known-material candidates.

## Phase 4 prediction entities

- `PredictionModel` — logical registry entry and lifecycle scope.
- `PredictionModelVersion` — immutable/checksummed predictor artifact contract.
- `ModelApplicabilityDomain` — structured family/feature/condition domain.
- `PredictionTarget` — exactly one known material or candidate hypothesis for one property/condition context.
- `PredictionInputSnapshot` — normalized immutable feature/input provenance.
- `PredictionRun` — bounded auditable batch execution.
- `PropertyPrediction` — model result, applicability, point estimate, uncertainty and result checksum.

These entities intentionally do not inherit from or write to `MaterialPropertyObservation`.

## Phase 5 virtual-experiment entities

- `VirtualExperimentCampaign` — project/organisation-scoped immutable execution envelope containing frozen specification/search-space/policy semantics, seed, budgets, status and result checksum.
- `CampaignObjective` — ordered property objective with direction, optional target and pinned immutable prediction model version.
- `CampaignConstraintModelPolicy` — explicit mapping from a project hard constraint to known-evidence/prediction origin policy and optional pinned model version.
- `CampaignIteration` — auditable iteration input, prediction-run IDs, counts, front/decision checksums, generated children and stop semantics.
- `VirtualCandidateEvaluation` — per-candidate feasibility, objective vectors/intervals/origins, Pareto posture, uncertainty/acquisition components and deterministic evaluation checksum.
- `ParetoFrontSnapshot` — persisted ordered campaign-local non-dominated front and objective-space checksum.
- `OptimizationDecisionRecord` — typed decision ledger for selection, rejection, mutation, duplication and stopping.

These records reference existing Phase-3 `Candidate` / `CandidateHypothesis` and Phase-4 `PredictionRun` / `PropertyPrediction` objects. They do not create a parallel candidate graph or prediction engine.


## Phase 6 entities

| Entity | Purpose |
| --- | --- |
| `ScientificRepresentation` | Structural description of a target; XOR-constrained to one material or one hypothesis |
| `RegisteredScientificArtifact` | Approved, checksummed potential / pseudopotential / database with licence metadata |
| `SimulationMethodDefinition` | Queryable mirror of the code-registered method contract |
| `SimulationProvider` / `SimulationProviderVersion` | Provider lifecycle; versions are immutable once used |
| `SimulationInputSnapshot` | Immutable record of exactly what was consumed |
| `SimulationRoute` | Persisted routing decision for a created workflow |
| `SimulationWorkflow` / `SimulationWorkflowStep` | Bounded execution plan from a code-registered template |
| `SimulationJob` | One execution attempt; unique on (step, attempt) |
| `SimulationArtifact` | Checksummed input/log/output content |
| `SimulationResult` | Operational status and scientific status, held separately |
| `SimulationPropertyEstimate` | A value — only ever from a converged result |
| `SimulationSelectionPolicyRecord` | Explicit opt-in to use a simulated value in a comparison |

Fourteen tables, 58 in total after migration `0006_phase6`.


## Phase 7 entities

| Entity | Purpose |
| --- | --- |
| `ManufacturingRoute` | A named production route with its declared process window and maturity |
| `MaterialProcessCompatibility` | Whether a target can be made by a route, with a required rationale |
| `IndustrialEvidence` | One industrial claim with currency, basis, geography, jurisdiction and as-of date as columns |
| `IndustrialConstraint` | A project's industrial requirement, including its missing-evidence policy |
| `MaturityAssessment` | An evidence-backed maturity stage; superseded, never rewritten |
| `IndustrialViabilityAssessment` | An immutable per-dimension assessment with evidence and constraint snapshots |

Six tables, 63 in total after migration `0007_phase7`.


## Phase 8 entities

| Entity | Purpose |
| --- | --- |
| `MaterialState` | A material in an identified condition, with structural and composition identity |
| `StateCompositionComponent` | One component with its role; ranges preserved as ranges |
| `ProcessingHistory` / `ProcessingStep` | An ordered route; order is part of identity |
| `MicrostructureDescriptor` | Optional microstructure; every field nullable, unknown stays unknown |
| `Application` / `ApplicationComponent` / `MaterialRole` | Generic application decomposition |
| `MaterialFunction` / `FunctionalRequirement` | What the role must do, and how it is tested |
| `StructuralFeature` / `Mechanism` | Nodes of the reasoning graph |
| `ReasoningEdge` | A scoped, sourced link between typed endpoints |
| `CandidateReasoningResult` | An immutable structured explanation, superseded rather than rewritten |

Fourteen tables, 77 in total after migration `0008_phase8`.


## Phase 9 entities

| Entity | Purpose |
| --- | --- |
| `ExperimentProtocol` / `ExperimentProtocolVersion` | Named procedure; versions are immutable and superseded |
| `Instrument` | Instrument metadata and recorded calibration state |
| `Sample` | A specimen with lineage and an explicit provenance verdict |
| `ExperimentPlan` | A design expanded into runs, with a design checksum |
| `ExperimentRun` | One run, pinning the protocol checksum it used |
| `Measurement` | A physical value with an explicit admissibility quality |
| `ExperimentArtifact` | Raw and processed data, kept distinguishable |
| `ExperimentRecommendation` | A prioritized, explained experiment proposal |
| `ValidationAssessment` | A candidate's validation state and origin comparison |

Ten tables, 87 in total after migration `0009_phase9`.
