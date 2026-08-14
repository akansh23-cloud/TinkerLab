# Phase 9.1-B Implementation Report — Experimental Admissibility, Closed-Loop Validation & Product Integration

## Status

Implemented on top of the green Phase 9.1-A gate.

## Principal changes

- Added explicit experiment run lifecycle and server-side transition validation.
- Added centralized `ExperimentalEvidenceAdmissionService` with structured reason codes.
- Enforced protocol property, instrument capability, required equipment declarations, calibration applicability/maximum age, sample provenance/target/geometry/representable requirements, controlled conditions, controls and unit compatibility before governing evidence can be accepted.
- Added `admissibility_codes` to measurements; planned/running/invalidated evidence retains history without masquerading as accepted evidence.
- Invalidating a run now propagates non-governing status without deleting measurements.
- Added experimental comparability before conflict detection.
- Replaced “measurement exists = requirement supported” with deterministic support/contradict/inconclusive/conflicting/not-available outcomes.
- Added explicit validation states for pending/in-progress/contradicted/conflicting experiments.
- Added candidate IDs to plans and validation assessments and immutable validation evidence snapshots/methodology metadata.
- Added candidate-scoped plan/run/sample/measurement listing.
- Added a transparent candidate-centric replacement next-gate endpoint that keeps scientific validation separate from commercial authorization.
- Upgraded Industrial Viability and project Scientific Validation UI paths to select project candidates rather than arbitrary global materials.
- Added a candidate Scientific Validation workspace with requirement outcomes, raw→canonical evidence, experiment recommendation→plan flow, legal run actions, provenance visibility and next-gate blockers.

## Migration

`0011_phase9_1b` adds candidate references to experiment plans and validation assessments, measurement admissibility reason codes, validation requirement/evidence snapshots, and explicit instrument equipment capabilities used by protocol admission. Legacy rows are explicitly backfilled with empty/legacy metadata instead of fabricated scientific context.

## Regression coverage

`tests/test_phase9_1b_experimental_hardening.py` covers run-state admissibility, protocol/instrument mismatch, required equipment, calibration expiry/protocol age, required controlled conditions, executable sample requirements, incompatible units, invalidation propagation, support/contradiction/uncertainty, condition comparability, replicate/control enforcement, tenant isolation, candidate state-machine reachability, semantic sample/candidate validation, candidate-scoped workflow APIs and transparent replacement decisions.

## Final verification

Backend: **318 passed, 6 skipped (324 collected)**. The six skips are the pre-existing external LAMMPS / Quantum ESPRESSO runtime cases.

Python: `python -m compileall apps/api/app apps/api/tests` **PASS**. Repository `git diff --check` **PASS**.

PostgreSQL-targeted Alembic offline upgrade **PASS** through `0011_phase9_1b (head)`; generated SQL is **3,093 lines**. Plain SQLite offline compilation is not a supported equivalent because the pre-existing schema uses PostgreSQL `JSONB`.

Frontend source parser verification: **62 TS/TSX files, 0 syntax diagnostics**. `apps/web/node_modules` was absent, so dependency-resolved Vitest/ESLint/Next typecheck/build is **not claimed** in this environment.

External Phase-6 scientific-runtime tests that require local LAMMPS / Quantum ESPRESSO executables remain explicitly skipped when those binaries are unavailable; no solver output is fabricated.

## Remaining known limitations

- `X-Organisation-ID` remains a development identity/scoping seam rather than production authentication.
- Manual experimental record entry is implemented; LIMS, instrument API, robotic platform and contract-lab integrations remain future adapter boundaries.
- Experimental comparability is conservative and based on the structured state/conditions currently represented; property-specific standards may require richer future context models.
- `READY_FOR_NEXT_GATE` is not certification, regulatory approval or commercial production authorization.
- Frontend dependency-resolved test/build status is only claimed when dependencies are present in the verification environment.

## Phase-10 readiness

**YES for Phase-10 engineering work, subject to deployment CI gates; not a production/commercial authorization.** The Phase-9.1 backend scientific-integrity gate is green. A release environment must still run the PostgreSQL migration against its real database, dependency-resolved frontend CI, and external solver/runtime validation where those solvers are required.
