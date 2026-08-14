# TinkerLab — Architecture Status and Future Direction

This document reflects the repository after **Phase 9.1**. Older phase reports remain historical implementation records; this file and the root README are the current phase-status source of truth.

## Implemented architecture

TinkerLab currently separates five claim/evidence origins:

1. observed / literature evidence;
2. model prediction;
3. physics simulation;
4. industrial evidence;
5. physical experiment measurement.

These origins can be compared by deterministic policy but are never silently merged or used to overwrite one another.

### Phases 1–5

Implemented: evidence/provenance, replacement requirements, bounded candidate/hypothesis generation, versioned predictions with applicability/uncertainty, and bounded virtual multi-objective campaigns.

### Phase 6 — Physics Simulation OS

Implemented: registered simulation methods/providers/artifacts, deterministic software-validation execution, and reviewed local boundaries for LAMMPS and Quantum ESPRESSO. External solver availability is probed and absence remains explicit.

### Phase 7 — Industrial Viability

Implemented: manufacturing routes/process compatibility, industrial evidence, economic/supply/environmental/regulatory constraints, maturity, per-dimension outcomes, explicit missing/conflicting evidence and optional declared composite methodology. Phase 9.1 hardens tenant isolation, Phase-5 feasibility integration, industrial comparability, monetary basis and score safety.

### Phase 8 — Functional Decomposition & Replacement Reasoning

Implemented: application/component/material-role decomposition, functional requirements, material states and processing histories, evidence-aware requirement evaluation, reasoning graph and evidence-gap generation. Phase 9.1 adds canonical unit normalization, quantitative composition identity, stricter state matching and tenant-scoped evidence collection.

### Phase 9 — Experimental Design & Validation

Implemented: immutable protocol versions, instruments/calibration metadata, sample provenance, experiment plans/runs, measurements, experimental recommendations and validation assessments.

### Phase 9.1 — Scientific Integrity & Closed-Loop Hardening

Implemented in two sequential hardening releases:

- **9.1-A:** scientific-unit/state integrity, tenant/provenance integrity, industrial comparability, economic/composite/maturity correctness and database invariants.
- **9.1-B:** centralized experimental admission, explicit run lifecycle, protocol/instrument/calibration enforcement, run invalidation propagation, requirement-level experimental support/contradiction/conflict/inconclusive semantics, immutable validation snapshots, candidate-centric UI and transparent replacement next-gate decisions.

## Current flagship workflow

```text
project → requirements → candidate → prediction → virtual evaluation → simulation
       → industrial viability → reasoning/evidence gaps → experiment recommendation
       → protocol-pinned plan → run → admissible measurement → updated validation
       → transparent next-gate decision
```

The next-gate decision is deliberately not a commercial approval or certification.

## Explicit current boundaries

The current repository does not claim:

- autonomous laboratory operation;
- a live LIMS or instrument/robotics integration unless an adapter is explicitly connected;
- automatic commercial qualification, regulatory approval or certification;
- universal scientific comparability when state/conditions are missing;
- solver availability where LAMMPS/Quantum ESPRESSO binaries or approved artifacts are absent;
- production-grade identity solely from the development `X-Organisation-ID` seam.

## Phase 10 — Closed-Loop Material Replacement Decision OS (implemented)

**Phase 10 is implemented in this repository.** It adds the replacement programme model, candidate
portfolio and decision matrix, evidence gap and next-best-action engine, convergence engine, and the
replacement recommendation and technical dossier. See
[`PHASE_10_REPLACEMENT_DECISION_OS.md`](PHASE_10_REPLACEMENT_DECISION_OS.md).

## Phase 11 — External Data Ingestion (implemented)

**Phase 11 is implemented in this repository.** It adds the connector framework, licence
enforcement, dataset snapshots and computational-method provenance. See
[`PHASE_11_DATA_INGESTION.md`](PHASE_11_DATA_INGESTION.md).

## Phase 12 — Future enterprise hardening

**Phase 12 is not started in this repository.** Its scope should be defined only after Phase-11
verification remains green and the connectors are validated against live endpoints. Likely enterprise concerns include production identity/authorization,
decision-policy governance and authoring surfaces, asynchronous action execution, audit/event
infrastructure, operational scaling, external provider governance and deployment hardening.

No future phase should weaken the Phase-9.1 principle: scientific truth is deterministic and evidence-backed; an LLM may explain a result but does not decide PASS/FAIL.
