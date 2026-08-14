# Phase 6 Implementation Report — Physics & Simulation Operating System

## 1. Gate results

| Gate | Result |
| --- | --- |
| `pytest` (apps/api) | **136 passed** (108 Phase 1-5 + 28 Phase 6) |
| `ruff check .` | **All checks passed** |
| `mypy app` | **Success — no issues in 54 source files** |
| `vitest` (apps/web) | **18 passed** (13 existing + 5 Phase 6) |
| `tsc --noEmit` | clean |
| `eslint .` | 0 errors, 0 warnings |
| `next build` | compiles; `/simulation` and `/simulation/workflows/[id]` render |
| Seed idempotency | verified (2× seed: 5 providers, 5 versions, 3 representations, 1 workflow, unchanged) |
| Migration DDL | `alembic upgrade head --sql` on PostgreSQL: 1,881 lines, 58 tables, 253 indexes |
| API surface | 122 routes total; 24 Phase-6 routes |

## 2. Provider availability — the honest classification

This is the part most likely to be overstated, so it is stated plainly.

| Provider | Adapter | Execution supported | Available on this host | Why |
| --- | --- | --- | --- | --- |
| `software_fixture_harmonic` | Implemented, in-process | Yes | **Yes** | Deterministic reduced-unit fixture; no external binary |
| `lammps_local` | **Implemented, reviewed** | Yes | **No** | `executable_not_installed` — no allowlisted LAMMPS binary on this machine |
| `quantum_espresso_local` | **Implemented, reviewed** | Yes | **No** | `executable_not_installed` — no `pw.x` on this machine |
| `calphad_interface` | **Interface only** | No | No | No reviewed thermodynamic database; execution permanently disabled in Phase 6 |
| `ml_force_field_interface` | **Interface only** | No | No | No licensed registered weights; execution permanently disabled in Phase 6 |

"Adapter implemented" and "usable right now" are different claims. The LAMMPS and QE adapters have
real input builders, code-defined templates, output parsers and convergence evaluators, all unit
tested. Their **end-to-end execution against a real solver is UNVERIFIED**, because neither binary
exists in this environment. That is reported as UNVERIFIED, never as PASS.

The only executed workflow in the seed is the software-validation fixture, and every surface that
displays it carries: `SOFTWARE VALIDATION SIMULATION FIXTURE — not a validated real-material physics model.`

## 3. Verification checklist

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Representation validators are deterministic | PASS | `test_representation_checksum_is_deterministic_and_order_independent` |
| 2 | Checksums are order-independent but content-sensitive | PASS | same test — reordered sites match, changed lattice differs |
| 3 | Unknown elements rejected, never repaired | PASS | `test_unknown_element_and_invalid_syntax_are_rejected_not_repaired` |
| 4 | Syntax vs completeness vs applicability reported separately | PASS | `ValidationOutcome` fields; `test_topology_without_force_field_mapping_is_incomplete` |
| 5 | Force-field mapping never inferred | PASS | same test — `FORCE_FIELD_MAPPING_MISSING` |
| 6 | Redaction flagged, never filled in | PASS | `test_redacted_formulation_is_flagged_not_silently_repaired` |
| 7 | Formulation-only refused by DFT and MD | PASS | `test_formulation_only_polymer_is_refused_by_dft_and_md` |
| 8 | Route preview persists nothing | PASS | `test_route_preview_persists_nothing` |
| 9 | Every refusal carries explicit reasons | PASS | same test asserts non-empty reasons on all refusals |
| 10 | Route ordering deterministic | PASS | `test_route_ordering_is_deterministic` |
| 11 | Cross-tenant returns 404 not 403 | PASS | `test_cross_tenant_target_is_not_found` |
| 12 | Provider availability honest | PASS | `test_provider_availability_is_honest` |
| 13 | Provider version immutable after use | PASS | `test_provider_version_is_immutable_after_use` (manifest tamper → not executable) |
| 14 | Path traversal rejected | PASS | `test_path_traversal_and_arbitrary_executables_are_rejected` |
| 15 | Arbitrary executables impossible | PASS | same test — `bash`, absolute paths resolve to nothing |
| 16 | No `shell=True` anywhere | PASS | `grep` clean; job records assert `shell: false` |
| 17 | Environment allowlisted | PASS | `test_environment_is_allowlisted` (planted secret dropped) |
| 18 | No API field accepts a command/path/image | PASS | `test_workflow_api_rejects_unsafe_payload_shapes`; schema review |
| 19 | Workflow preview executes nothing | PASS | `test_workflow_preview_executes_nothing` |
| 20 | Required parameters never defaulted silently | PASS | `test_missing_required_parameter_is_an_error_not_a_default` |
| 21 | Deterministic replay reproduces result checksum | PASS | `test_deterministic_replay_reproduces_result_checksum` |
| 22 | Changed parameter changes checksum | PASS | `test_changed_parameter_changes_checksums` |
| 23 | Convergence ≠ exit code zero | PASS | `test_unconverged_fixture_yields_no_property_estimate` (completed + unconverged) |
| 24 | Unconverged → no property estimate | PASS | same test — zero estimates |
| 25 | Parser failure / NaN → no value | PASS | `test_parser_failure_yields_no_estimate` |
| 26 | Completed workflow immutable | PASS | `test_retry_appends_attempt_and_never_overwrites` |
| 27 | Zero observations, zero predictions created | PASS | `test_simulation_creates_zero_observations_and_zero_predictions` |
| 28 | Fixture warning unmistakable | PASS | `test_fixture_warning_is_unmistakable` |
| 29 | Phase-5 campaign history unchanged | PASS | `test_campaign_history_is_unchanged_by_simulation` (byte-identical checksums) |
| 30 | Escalation read-only | PASS | `test_campaign_escalation_maps_candidates_without_mutating` |
| 31 | Selection policy explicit opt-in | PASS | `test_selection_policy_is_explicit_opt_in` |
| 32 | Target history scoped | PASS | `test_target_history_is_scoped_and_labelled` |
| 33 | No host paths leak through API | PASS | `test_seeded_workflow_is_converged_with_full_provenance` scans payload for `/tmp/` |
| 34 | Migration is forward-only, 0001-0005 untouched | PASS | `git diff` on prior migrations empty; static DDL generation |
| 35 | **Live PostgreSQL migration** | **UNVERIFIED** | No Docker/PostgreSQL server in this environment |
| 36 | **Docker compose clean-machine run** | **UNVERIFIED** | No `docker` binary available |
| 37 | **LAMMPS end-to-end execution** | **UNVERIFIED** | Binary not installed; adapter reports `executable_not_installed` |
| 38 | **Quantum ESPRESSO end-to-end execution** | **UNVERIFIED** | Binary not installed; adapter reports `executable_not_installed` |
| 39 | CALPHAD numerical results | **NOT IMPLEMENTED (by design)** | Interface-only; execution permanently disabled |
| 40 | ML force-field numerical results | **NOT IMPLEMENTED (by design)** | Interface-only; execution permanently disabled |

## 4. What was built

**Backend** — migration `0006_physics_simulation_os.py` (14 tables), `app/services/representations.py`
(5 validators), `app/services/simulation_runtime.py` (bounded runner), `app/services/simulation_adapters.py`
(5 adapters), `app/services/simulation.py` (registry, router, snapshots, workflows, execution, results,
selection, integrity), `app/schemas/simulation.py`, `app/api/routes/simulation.py` (24 routes),
`tests/test_phase6_simulation.py` (28 tests), Phase-6 seed block.

**Frontend** — `/simulation` Simulation Lab with an **Element Composer** (build a periodic cell from
any element, validate it, attach it, and see exactly which methods it unlocks and what each refusal
requires), route table with reasons and method-class industrial context, provider availability table,
workflow history, method registry; `/simulation/workflows/[id]` detail page separating operational
status from convergence, showing "None — and that is correct" when no estimate is warranted, and
listing every artifact with its SHA-256; `SimulationWarning`, `RouteStatusBadge`, `ConvergenceBadge`.

**Docs** — 11 new documents plus updates to README, ARCHITECTURE, DOMAIN_MODEL, ERD,
SCIENTIFIC_INTEGRITY, PRIVACY_MODEL and FUTURE_ARCHITECTURE.

## 5. Deliberate design decisions worth flagging

**The Element Composer gives industrial context at the method-class level, not the composition level.**
The UI explains what converged DFT/MD/CALPHAD results are used for in industry, and what each specific
refusal requires. It does **not** generate property claims, performance estimates or suitability
verdicts for a user's assembled cell — those would be fabricated. The honest answer for an arbitrary
composed structure today is a routing analysis plus a precise statement of what is missing, and that
is what it gives.

**The fixture's analytic minimum is 0.25.** `E(x) = ½·4·x² − 2x + 0.75` has minimum `c − b²/2k = 0.25`.
The seeded workflow converges to it within 1e-6, which is what makes the fixture a real test of the
pipeline rather than a decorative one. The value is dimensionless and mapped to a property definition
explicitly named "synthetic".

**No unsourced real-material property was seeded** to make the lab look impressive. The diamond cell in
the seed exists to demonstrate that a perfectly valid structure still routes to
`missing_registered_artifact` when no pseudopotential is registered.

## 6. Phase 7 boundary

Phase 7 (Industrial Viability Engine) is **not started**. There is no cost model, supply-chain data,
regulatory logic, scale-up reasoning or manufacturability scoring anywhere in the codebase. No Phase-6
output should be read as a claim about any of them.
