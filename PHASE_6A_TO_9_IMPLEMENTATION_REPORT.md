# TinkerLab — Phase 6A to Phase 9 Implementation Report

## 1. Executive summary

Four programmes of work were completed in sequence, each gated before the next began.

**Phase 6A — hardening.** Three previously unverifiable claims became genuinely verified because the
required software was installed: PostgreSQL 16, LAMMPS and Quantum ESPRESSO. LAMMPS now runs
end-to-end through the full stack; QE is installed but has a distribution build defect and is
reported as externally unverified with an exact reason. An artifact content store was added, and
three real defects were found and fixed — including a scientific-integrity bug of my own making.

**Phase 7 — Industrial Viability Engine.** Six tables assessing manufacturing, economics, supply
chain, environmental and regulatory evidence across eight dimensions, with comparability enforced
structurally: figures on different currency, basis or jurisdiction are never silently converted.

**Phase 8 — Replacement Reasoning Engine.** Fourteen tables implementing
`Material → State → Feature → Mechanism → Property → Function → Requirement`. A property belongs to a
material in a *state*; a shared formula is not a shared structure; evidence origins stay separate.

**Phase 9 — Experimental Design & Validation OS.** Ten tables covering versioned protocols, sample
provenance, measurements, prediction-versus-experiment comparison, prioritized recommendations and
validation states. The loop closes: new measurements change what the reasoning engine concludes.

## 2. Phase 6A — concrete changes

### Environment
| Component | Status |
| --- | --- |
| PostgreSQL 16.14 | Installed and running. Migration and boot verification is real. |
| LAMMPS 7 Feb 2024 | Installed and exercised end-to-end. |
| Quantum ESPRESSO 6.7 | Installed but **unusable** — fortify buffer-overflow on input parsing. |

### Defects found and fixed

**A test that could not fail correctly.** `test_provider_availability_is_honest` hard-coded "solver
absent" and broke the moment LAMMPS existed. Rewritten to assert the invariant — reported
availability matches binary resolvability — so it now catches an adapter lying in either direction.

**A false-positive solver probe.** The first QE usability probe referenced a nonexistent
pseudopotential, so `pw.x` exited early on a file error and looked healthy. Rewritten to use a real
pseudopotential and the adapter's own argv invocation.

**A scientific-integrity bug introduced in Phase 6.** The MD method declared its output as
`total_energy`, sharing a property key between a dimensionless reduced-unit Lennard-Jones value and a
first-principles energy in rydberg. Silently comparing those is exactly the category error the system
exists to prevent. Split into `md_reduced_potential_energy` and `total_energy`.

**Registered artifacts were decorative.** A potential could be "required" while the solver template
used inline defaults, so a missing artifact changed nothing. LAMMPS now `include`s the registered
potential and the QE builder raises rather than emitting a `MISSING` placeholder.

### Artifact content store
`app/services/artifact_store.py`: digest-addressed content in one controlled root, server-side
ingestion only (unreachable from any route), digest re-verified before every use, `safe_join` on
materialization, nothing ever downloaded.

### LAMMPS end-to-end result
The clearest demonstration of the core invariant in the project: LAMMPS exits 0, a genuine energy of
−1.5 reduced units is parsed, `fmax` returns 1.16e-6 against a 1e-6 tolerance → **unconverged** →
**zero** property estimates. Loosening the tolerance to 1e-4 gives converged and exactly one estimate.

### Security audit
`tests/test_phase6a_security.py` (40 tests): closed executable allowlist, argv-not-shell, bounded
timeouts, path traversal and symlink escape, oversized inputs, output collection outside the workdir,
cleanup outside the controlled root, environment allowlist, artifact digest tampering, non-regular-file
ingestion, a field-by-field check that no API field accepts a command or path, cross-tenant 404s,
pagination bounds, payload size limits.

## 3. Phase 7 — Industrial Viability Engine

**Backend:** `app/services/industrial.py`, `app/schemas/industrial.py`,
`app/api/routes/industrial.py`. **Tables:** `manufacturing_routes`, `industrial_evidence`,
`material_process_compatibilities`, `industrial_constraints`, `maturity_assessments`,
`industrial_viability_assessments`. **Tests:** 36.

Key behaviours:

* **Comparability is structural.** Economic evidence without currency and cost basis is rejected at
  the door. USD 5/kg is not evaluated against a EUR 10/kg limit even though 5 < 10 — the result is
  `INSUFFICIENT_EVIDENCE` with the available bases listed.
* **Missing evidence never becomes a pass.** Each constraint declares its own
  `treat_missing_evidence_as` policy.
* **Regulatory status does not transfer between jurisdictions.** EU clearance is not JP clearance.
* **An unrecorded process compatibility is not compatibility.**
* **Elements come only from a declared structural representation**, never parsed from a display name.
* **Roll-up is worst-wins.** A hard FAIL is never averaged away.
* **Composite scores are opt-in**, require a declared methodology, exclude unknown dimensions rather
  than scoring them zero, and stay flagged partial.
* **Maturity is deliberately not called TRL.**
* **Assessments are immutable** and superseded, with evidence and constraint snapshots.

## 4. Phase 8 — Replacement Reasoning Engine

**Backend:** `app/services/material_states.py`, `app/services/reasoning.py`,
`app/schemas/reasoning.py`, `app/api/routes/reasoning.py`. **Tables:** 14. **Tests:** 36.

Key behaviours:

* **A property belongs to a material in a state.** A value recorded at 900 K does not satisfy a 300 K
  requirement, even when the number would pass comfortably.
* **Structural identity is not composition.** Diamond and graphite share a composition signature and
  differ in structure identity. With no structural representation there is **no** identity, rather
  than a formula-derived stand-in.
* **Ranges stay ranges** — `10-30 at.%` is never collapsed to 20%.
* **Processing-history order is part of identity.**
* **Evidence origins are never averaged.** A governing value is selected by declared priority, which
  reports rather than merges; every other value stays listed.
* **Out-of-domain predictions and unconverged simulations are shown but never used.**
* **State-unqualified evidence is used but flagged** as an explicit assumption.
* **An objective reports PARTIAL, never PASS** — ranking against no threshold is not passing.
* **An unsourced causal edge is refused.** Chain confidence is the weakest link.
* **Structured before language.** No language model can change a PASS, FAIL or UNKNOWN.
* **The engine is domain-generic** — a test greps the source for domain-specific branching.

## 5. Phase 9 — Experimental Design & Validation OS

**Backend:** `app/services/experiments_lab.py`, `app/schemas/experiments_lab.py`,
`app/api/routes/experiments_lab.py`. **Tables:** 10. **Tests:** 34 plus 7 cross-phase.

Key behaviours:

* **Protocol versions are immutable**; a run pins the checksum it used.
* **Every measurement traces to a sample**; an untraceable one is `INCOMPLETE_PROVENANCE`, not
  evidence.
* **Calibration is never assumed**; claiming it requires a date and a reference.
* **Unimplemented designs are refused**, not faked — no response-surface, Bayesian optimization or
  active learning.
* **Experiment never overwrites prediction or simulation**; disagreement is exposed, not averaged.
* **Conflicting measurements are both kept**; the later does not win; state becomes `INCONCLUSIVE`.
* **"Validated" is never used for simulation-only support.**
* **Priority is not called expected value of information**, because no such mathematics exists here.
* **No autonomy surface** — asserted by scanning the OpenAPI paths.

## 6. Database changes

| Migration | Adds | Tables after |
| --- | --- | --- |
| `0007_industrial_viability` | 6 industrial tables | 63 |
| `0008_functional_decomposition` | 14 reasoning tables | 77 |
| `0009_experimental_validation` | 10 experiment tables | 87 |

Migrations 0008 and 0009 were autogenerated then **filtered**: autogenerate proposed 121 statements
against Phase 1-7 tables (62 `alter_column`, 27 `drop_index`, 26 `create_index`, 6
`drop_constraint`) reflecting pre-existing schema drift. Applying them would have silently rewritten
earlier phases' schema under cover of adding a new one. They were discarded and the count recorded in
each migration docstring.

Verified on real PostgreSQL for every migration: forward, model/migration parity (**0 mismatches**),
and rollback leaving **zero** tables behind.

## 7. API changes

177 routes total. New in this programme:

* **Phase 7 (17):** manufacturing routes, industrial evidence + conflicts, process compatibility,
  project industrial constraints, maturity (list/create/current), dimensions, viability
  assess/compare, assessment list/detail.
* **Phase 8 (22):** processing histories, material states + comparison, applications, components,
  roles, functions, requirements, decomposition, reasoning edges, features/mechanisms, candidate
  reasoning, results, origin policy.
* **Phase 9 (21):** protocols + versions, instruments, samples + lineage, plans, runs (+ complete,
  invalidate), measurements + conflicts, validation assess/list, recommendations, policy.

## 8. UI changes

| Workspace | Route |
| --- | --- |
| Industrial Viability | `/projects/[id]/industrial` |
| Replacement Reasoning | `/reasoning` |
| Experimental Validation | `/validation` |

New components: `IndustrialStateBadge`, `IndustrialSeparationNotice`, `EvidenceQualifiers`,
`RequirementStatusBadge`, `OriginBadge`, `ValidationStateBadge`, `MeasurementQualityBadge`.

Every badge renders absence loudly: `UNKNOWN`, `INSUFFICIENT EVIDENCE`, `WRONG MATERIAL STATE`,
`INCOMPLETE PROVENANCE — NOT EVIDENCE`, `SIMULATION SUPPORTED — NOT VALIDATED`. An unrecognised
status is displayed rather than hidden.

## 9. Scientific integrity guarantees

Five claim classes remain separate: **observation**, **model prediction**, **physics simulation**,
**industrial evidence**, **experimental measurement**. Tests assert that each analysis layer creates
zero rows in the others' tables.

Specific guarantees, each test-backed: unknown never becomes zero or a pass; unconverged simulation
produces no property value; incomparable cost bases are never converted; regulatory status does not
transfer jurisdictions; a property does not cross an incompatible material state; origins are never
averaged; contradictions are retained on both sides; historical assessments stay reproducible;
"validated" requires measurement.

## 10. Security

Simulation runtime: closed executable allowlist, argv arrays with `shell=False`, server-generated
workdir tokens with path-traversal and symlink-escape protection, environment allowlist, wall-time
and output caps, no network access during runs. Artifact store: digest-addressed, server-side
ingestion only, digest re-verified before use. API: cross-tenant access returns 404 not 403,
pagination bounds enforced, payload sizes bounded, no field anywhere accepts a command, path, script
or container image.

## 11. Verification

Commands run from `apps/api` and `apps/web`.

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `python -m pytest` | **294 passed, 2 skipped** — PASS |
| Backend lint | `python -m ruff check .` | All checks passed — PASS |
| Backend types | `python -m mypy app` | Success, 65 files — PASS |
| Frontend tests | `npm test` | **36 passed** — PASS |
| Frontend types | `npm run typecheck` | clean — PASS |
| Frontend lint | `npm run lint` | 0 problems — PASS |
| Frontend build | `npm run build` | compiles, all workspaces — PASS |
| Migrations (PostgreSQL) | `alembic upgrade head` | 87 tables, 0 parity mismatches — PASS |
| Rollback (PostgreSQL) | `alembic downgrade` per phase | zero tables left behind — PASS |
| Seed idempotency | `python -m app.db.seed` ×2 | unchanged counts — PASS |
| Live API | `uvicorn` + HTTP smoke test | health, routing, 404 scoping — PASS |
| LAMMPS end-to-end | `pytest tests/test_phase6a_real_solvers.py` | **PASS** (real solver) |
| Quantum ESPRESSO end-to-end | same | **EXTERNALLY_UNVERIFIED** (build defect) |
| Docker compose | `docker compose up` | **NOT_RUN** (no docker binary) |

## 12. External dependencies not tested

* **Quantum ESPRESSO execution** — `pw.x` 6.7 is installed but aborts with a fortify
  buffer-overflow (`__snprintf_chk`, SIGABRT/134) while parsing any real input. Attempted and failed:
  `-input file`, stdin redirection, `mpirun -np 1`, minimal environment, absolute vs relative
  `pseudo_dir`/`outdir`. This is a distribution build defect, not an adapter fault. Everything up to
  execution is verified — routing, pseudopotential ingestion and materialization, input generation —
  and the failure path is verified too: a QE workflow correctly records `failed` / `not_applicable`
  with no property estimate. Reproduction instructions on a working host are in
  `docs/PHASE6A_HARDENING.md`.
* **Docker / docker compose** — no `docker` binary in this environment. The exact command chain from
  `docker-compose.yml` was executed directly against real PostgreSQL instead, and passed.
* **CALPHAD and ML interatomic potentials** — interface-only by design; no database or licensed
  weights exist, so no execution path is enabled.
* **Real industrial datasets** — no commodity, lifecycle or regulatory data source is connected. All
  seeded industrial values are synthetic and labelled `seed_demonstration`.
* **Laboratory systems** — no LIMS, instrument API, robotic platform or contract laboratory is
  connected. Only manual entry is implemented.

## 13. Known limitations

1. **Seed data is synthetic where it must be.** No real property value is asserted for silicon or any
   real material. Silicon reports `UNKNOWN` on every requirement because the database genuinely holds
   no measurements for it — this is the honest state, not a gap to be papered over.
2. **Phase 1-2 observations predate the state model.** They carry no `material_state_id`, so they are
   reported as state-unqualified: used, but flagged with an explicit assumption. Retrofitting states
   onto them would require altering earlier phases' schema, which this programme deliberately avoided.
3. **Unit conversion is not attempted across incomparable dimensions** anywhere; incomparable values
   are reported as such rather than converted.
4. **The reasoning graph is populated by declaration**, not by literature extraction. Every edge
   carries a source reference, but those references are demonstration entries, not a mining pipeline.
5. **Composite scoring has one methodology** (`declared_weighted_mean_v1`). It is opt-in and partial.
6. **Pre-existing schema drift** between models and migrations 0001-0007 remains unaddressed; it is
   documented rather than silently "fixed" inside a feature migration.
7. **No authentication beyond organisation scoping.** The `X-Organisation-ID` header is the tenancy
   boundary; there is no user authentication layer.
8. **Experiment recommendation priority is heuristic**, with declared weights. It is not decision
   theory and is not labelled as such.

## 14. Recommended Phase 10

**Do not build autonomous discovery.** The correct next step is to strengthen what the closed loop
rests on, not to remove the human from it.

1. **Evidence ingestion with real provenance.** Connect crystallographic, materials and literature
   databases behind the existing provider boundaries, with per-source licensing, extraction
   confidence and re-ingestion. This is the largest real gap: the system's reasoning is sound and its
   evidence base is a demonstration fixture.
2. **State retrofit for legacy observations.** A dedicated migration attaching material states to
   Phase 1-2 observations, so state-qualification stops being an assumption.
3. **Authentication and authorization.** Real users, roles and audit trails; organisation scoping
   alone is not access control.
4. **Uncertainty propagation across the chain.** Prediction intervals, simulation tolerances and
   measurement uncertainties currently coexist without a principled combination rule. If one is
   added, it must be declared and inspectable, exactly as composite scoring is.
5. **Expected value of information, properly.** If experiment prioritization is to be decision-
   theoretic, implement the mathematics and only then use the name.
6. **A queue-backed compute backend.** The `ComputeBackend` seam exists; an HPC or queue backend
   would let real DFT and MD run at useful scale.
7. **Schema drift reconciliation.** A dedicated, reviewed migration for the 121 drift statements,
   separate from any feature work.

Only after 1-3 would active learning be a responsible thing to build, and even then it should propose
rather than act.
