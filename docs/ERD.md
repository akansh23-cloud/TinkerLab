# Phase 3 ERD

```text
Organisation ──< User
     │
     ├──< ReplacementProject >── baseline Material
     │          ├──< Constraint
     │          ├──< Objective
     │          ├──< Candidate ── exactly one ──> Material (known)
     │          │                              └─> CandidateHypothesis
     │          ├──< CandidateSearchSpace
     │          │      ├──< SearchSpaceComponentRule
     │          │      └──< SearchSpaceProcessRule
     │          ├──< SubstitutionRule >── optional Evidence
     │          └──< GenerationRun
     │                 └──< GenerationRunResult ──> Candidate / Material / Hypothesis
     │
     └──< ImportBatch >── SourceProvider

CandidateHypothesis
 ├──< CandidateHypothesisComponent
 ├──< CandidateHypothesisProcessParameter
 ├──< CandidateChangeRecord
 └──< CandidateLineageEdge >── parent Material / Candidate / Hypothesis

Material
 ├──< MaterialIdentifier
 ├──< MaterialComponent >── Evidence
 ├──< MaterialProcessState >── Evidence
 └──< MaterialPropertyObservation >── MaterialPropertyDefinition
               │          │
               │          └── ObservationConditionSet
               ├── Evidence
               └── SourceRecord

SourceProvider ──< SourceRecord ──< Evidence ──< MaterialPropertyObservation
                                   └── Citation (optional)
```

Forward migration `0003_phase3` preserves existing Phase-1/2 known-candidate IDs and marks them `candidate_kind=known_material`.

## Phase 4 additions

```text
PredictionModel 1 --- * PredictionModelVersion 1 --- 1 ModelApplicabilityDomain
                              |
                              | 1
                              *
                       PredictionRun
                              |
                              *
                       PropertyPrediction
                         |          |
                         |          1
                         |          |
                         *    PredictionInputSnapshot
                         |
                         1
                  PredictionTarget
                   /            \
             Material       CandidateHypothesis
             (xor)               (xor)
```

`PredictionTarget` enforces exactly one scientific object (`material_id` xor `hypothesis_id`).

## Phase 5 additions

```text
ReplacementProject
      |
      *
VirtualExperimentCampaign ----> CandidateSearchSpace
      |                                  |
      |                                  +-- Phase-3 rules/mutation bounds
      |
      +--< CampaignObjective ----------> PredictionModelVersion
      |
      +--< CampaignConstraintModelPolicy --> Constraint
      |                                  \-> PredictionModelVersion (optional)
      |
      +--< CampaignIteration
              |
              +-- prediction_run_ids ----> PredictionRun(s)
              |
              +--< VirtualCandidateEvaluation --> Candidate --> Material OR CandidateHypothesis
              |
              +--< ParetoFrontSnapshot
              |
              +--< OptimizationDecisionRecord --> Candidate/Hypothesis (optional)

CandidateHypothesis child
      ^
      |
Phase-3 CandidateLineageEdge / CandidateChangeRecord
      ^
      |
Phase-5 bounded mutation from selected parent
```

`0005_phase5` adds these tables without modifying migrations `0001`–`0004`. Downgrade removes Phase-5 campaign history while leaving earlier scientific objects intact.


## Phase 6 relationships

```
Material ─┐
          ├─< ScientificRepresentation ─< SimulationInputSnapshot
CandidateHypothesis ─┘                         │
                                               │
SimulationProvider ─< SimulationProviderVersion ┤
                                               │
SimulationMethodDefinition ────────────────────┤
                                               ▼
                    SimulationRoute ──> SimulationWorkflow ─< SimulationWorkflowStep ─< SimulationJob
                                               │                                            │
                                               ├─< SimulationArtifact <─────────────────────┘
                                               ├──> SimulationResult ─< SimulationPropertyEstimate
                                               └──< SimulationSelectionPolicyRecord
```

`ScientificRepresentation` carries a check constraint requiring exactly one of `material_id` or
`hypothesis_id`. `SimulationResult` is unique per workflow; `SimulationPropertyEstimate` is unique per
(result, property definition); `SimulationJob` is unique per (step, attempt number).
