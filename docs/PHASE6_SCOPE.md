# Phase 6 scope — Physics & Simulation Operating System

## In scope

* Scientific representations (crystal cells, atomistic topologies, phase descriptions, formulation-only,
  software-validation fixtures) with deterministic validators and content checksums.
* A provider registry with immutable versions, lifecycle states and honest availability probing.
* A conservative router that returns typed refusals with explicit reasons.
* Deterministic input snapshots and code-registered workflow templates.
* Bounded local execution: allowlisted executables, argv arrays, no shell, sanitized environment,
  wall-time and output caps, path-traversal protection.
* Separation of operational status from scientific convergence, with property estimates gated on convergence.
* Full checksum provenance from representation to result.
* An explicit, opt-in selection policy for using a simulated value in a project comparison.

## Explicitly NOT in scope

* **Historical Phase-6 boundary:** at the time Phase 6 was delivered, Phase 7 had not started. The current repository now implements Phase 7 through Phase 9.1. No Phase-6 simulation output should be mistaken for cost, supply-chain, regulatory,
  scale-up or manufacturability logic exists in this phase.
* No physical experiment, no lab validation, no synthesizability claim.
* No arbitrary code execution: no API field accepts a command, path, script, container image or import path.
* No downloading of potentials, pseudopotentials, thermodynamic databases or model weights at run time.
* No conversion of a simulation result into evidence or into an ML prediction.
* No reranking or mutation of completed Phase-5 campaign history.
* CALPHAD and ML interatomic potentials are **interface-only**: execution is permanently disabled in Phase 6.

## The core invariant

Evidence, model prediction and physics simulation are three separate scientific origins. They are stored
in separate tables, labelled with distinct `scientific_origin` values, and are never silently converted
into one another. A simulation run creates zero observations and zero predictions — asserted by test and
by the `/simulation/integrity` endpoint.
