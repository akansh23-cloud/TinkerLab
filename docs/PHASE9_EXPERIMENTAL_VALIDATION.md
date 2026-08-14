# Phase 9 — Experimental Design & Validation OS

> **Current status:** Phase 9 is implemented and subsequently hardened by Phase 9.1. Where this document describes the Phase-9 baseline, the stricter Phase-9.1 scientific-integrity contract governs current behavior; see `PHASE_9_1_SCIENTIFIC_INTEGRITY.md`.

## What TinkerLab does and does not do

TinkerLab **does not own a laboratory**. It manages the record: protocols, samples, plans, runs,
measurements, and the comparison between what was predicted, what was simulated and what was
measured. It does not order experiments, operate instruments, or perform anything physical. Every
run recorded is one a person carried out and entered.

## Protocol versioning is immutable

A protocol's content lives in versions. Attempting to rewrite a published version raises — editing
creates a **new** version and supersedes the old one, which stays readable with its original
checksum. An `ExperimentRun` stores `protocol_checksum_at_run`, so a later protocol edit cannot
change what a historical run says was done.

A protocol version without a measurement procedure is refused: a protocol that never says how to
measure cannot make a measurement traceable.

## Every measurement traces to a sample

`assess_sample_provenance` requires a substance, a material state, a preparation date, and either a
batch reference or a parent sample. A specimen missing any of these is recorded with its gaps listed.

Measurement admissibility is explicit and, after Phase 9.1, centralized. A measurement is not governing evidence merely because a row was inserted. Admission checks the run lifecycle, pinned protocol/checksum, sample provenance and protocol-representable sample requirements, protocol property, instrument capability and required equipment, calibration validity/maximum age, controlled conditions, controls and unit compatibility.

| Quality | Current meaning |
| --- | --- |
| `ACCEPTED` | All represented governing admission checks passed on a completed valid run |
| `PROVISIONAL` | Recorded evidence exists but an admission prerequisite/context remains unresolved |
| `REJECTED` | A hard scientific/protocol mismatch prevents admission |
| `INCOMPLETE_PROVENANCE` | Essential provenance/unit traceability is incomplete |
| `INVALIDATED_SOURCE` | The measurement is retained historically but its source run cannot govern decisions |

Only `ACCEPTED` measurements from valid completed runs are admitted as governing evidence. Other rows remain visible for provenance and are never quietly counted.

**Calibration is never assumed.** Instruments default to `UNKNOWN`, and claiming `calibrated`
through the API requires a calibration date *and* a reference.

## Design of experiments

Implemented: `single_run`, `one_factor`, `full_factorial`, `parameter_sweep`, with replicates and
controls. Expansion is bounded at 200 runs.

**Not implemented, and refused rather than faked:** response-surface methods, Bayesian optimization,
active learning. Offering a design without its mathematics would misrepresent what the software does.

## Prediction vs simulation vs experiment

All three are retained. `compare_values` reports:

| Verdict | Meaning |
| --- | --- |
| `AGREES_WITHIN_UNCERTAINTY` | Stated intervals overlap — and are still **not** combined into one number |
| `DISAGREES` | Intervals do not overlap; both retained, no average taken |
| `INCOMPARABLE` | Units differ; values are not converted here and not compared |

A measurement never overwrites a prediction or a simulation. Asserted by test.

## Conflicting experiments

Phase 9.1 first determines experimental comparability from target/property, material state and recorded conditions. Only comparable accepted measurements participate in direct contradiction detection. Different temperatures, pressures or other comparison-critical contexts are not automatically conflicts. Genuine comparable conflicts preserve both measurements; the later row does not silently supersede the earlier.

## Validation states

The current deterministic state machine distinguishes `COMPUTATIONAL_ONLY`, `SIMULATION_SUPPORTED`, `EXPERIMENT_RECOMMENDED`, `EXPERIMENT_PENDING`, `EXPERIMENT_IN_PROGRESS`, `PARTIALLY_VALIDATED`, `EXPERIMENTALLY_SUPPORTED`, `EXPERIMENTALLY_CONTRADICTED`, `CONFLICTING_EXPERIMENTS` and `INCONCLUSIVE`. Measurement existence alone does not advance a requirement to supported: each admissible measurement is evaluated against the requirement threshold, including canonical unit conversion and explicit uncertainty.

**"Validated" is never used when only simulation exists** — that is exactly what
`SIMULATION_SUPPORTED` means, and the UI renders it as "SIMULATION SUPPORTED — NOT VALIDATED". A
test asserts no validated state is reachable from simulation alone.

Even `EXPERIMENTALLY_SUPPORTED` describes the evidence on file; it is not a statement that a
candidate is qualified for service.

## Experiment recommendation

Unresolved requirements become prioritized recommendations stating the unresolved requirement, why it
matters, the current evidence, the expected evidence type, the proposed measurement, and the
priority rationale.

Priority is a weighted combination of declared, inspectable factors: requirement criticality (0.35),
evidence gap severity (0.30), requirement hardness (0.20), uncertainty (0.15).

It is **deliberately not called expected value of information**. No EVSI or EVI mathematics is
implemented, and borrowing the term would claim a method this system does not have.

## Closing the loop

Only admissible accepted measurements from valid completed runs feed back into Phase-8 candidate reasoning as the `EXPERIMENTAL` origin. Phase 9.1 evaluates whether those measurements support, contradict or leave a requirement inconclusive; invalidated/provisional/rejected measurements remain historical provenance but cannot govern the candidate decision. Every superseded assessment remains readable with its evidence snapshot and methodology.

This closure was caught by the cross-phase integration test, which failed until the feedback edge
existed. The loop is verified, not asserted.

## Integration boundaries

`manual_entry` is the only implemented path. LIMS, instrument APIs, robotic platforms and contract
laboratories are declared boundaries for future adapters. None is connected, and **none is
simulated**.

## Not autonomous discovery

Phase 9 is not permission to build an autonomous scientist. There is no endpoint that generates
materials autonomously, orders experiments, operates hardware, claims discoveries or self-modifies a
scientific model — asserted by a test that scans the OpenAPI surface. The correct boundary after
Phase 9 is **human-supervised closed-loop readiness**.
