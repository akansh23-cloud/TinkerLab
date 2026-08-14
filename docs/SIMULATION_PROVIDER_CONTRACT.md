# Simulation provider contract

## Adapter interface

Every provider implements: `capabilities`, `check_availability`, `validate_target`, `build_inputs`,
`command_descriptor`, `execute`, `parse_outputs`, `assess_convergence`.

Adapters are registered **in code** (`ADAPTERS` in `app/services/simulation_adapters.py`). No API
payload can introduce an adapter, an import path, an executable path or a container image.

## Four honest categories

| Provider | Category | Phase-6 state |
| --- | --- | --- |
| `software_fixture_harmonic` | Implemented, in-process, deterministic | Executable and verified |
| `lammps_local` | Implemented reviewed boundary | Adapter implemented; runtime **unavailable** unless an allowlisted binary and approved potential exist |
| `quantum_espresso_local` | Implemented reviewed boundary | Adapter implemented; runtime **unavailable** without `pw.x` and approved pseudopotentials |
| `calphad_interface` | Interface only | Execution permanently disabled — no reviewed thermodynamic database |
| `ml_force_field_interface` | Interface only | Execution permanently disabled — no licensed registered weights |

"Implemented adapter" and "usable right now" are different claims, and the API reports them separately.

## Version immutability

`simulation_provider_versions` rows are immutable once used by a job. Every execution re-checks:
approval state, retirement, provider lifecycle status, `execution_supported`, and a **recomputed**
`artifact_manifest_checksum`. If the manifest is tampered with, the version stops being executable —
tested directly.

## Availability probing

Availability is probed once per request and cached by adapter key; it is never probed per target or
per provider-target pair. A missing binary produces `available: false` with a reason code, never a
fabricated result.
