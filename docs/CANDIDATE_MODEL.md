# Candidate Model

## Two candidate kinds

A project candidate is exactly one of:

1. `known_material` — references a canonical Phase-2 `Material`;
2. `hypothesis` — references a Phase-3 `CandidateHypothesis`.

Database check constraints enforce the exactly-one-target invariant.

## CandidateHypothesis

A hypothesis stores identity/status, project/organisation scope, baseline material, generator strategy/version, deterministic fingerprint/version, structural validity and rejection reason. It does **not** store scientific performance claims.

Concrete proposed formulation/process data are structured in:

- `CandidateHypothesisComponent`;
- `CandidateHypothesisProcessParameter`.

Auditability is carried by:

- `CandidateChangeRecord`;
- `CandidateLineageEdge`;
- `GenerationRun` / `GenerationRunResult`.

## Promotion boundary

Generation does not create a canonical `Material`. Future physical validation may justify a separate promotion workflow, but no such promotion exists in Phase 3.
