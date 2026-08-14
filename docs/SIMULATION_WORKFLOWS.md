# Simulation workflows

## Templates are code-registered

`WORKFLOW_TEMPLATES` defines the permitted workflow shapes. A user selects a template implicitly by
choosing a method; they cannot author a workflow graph, add a step type or reorder execution.

| Template | Method | Steps |
| --- | --- | --- |
| `software_fixture_single_step_v1` | `software_fixture_energy_minimization_v1` | `fixture_minimize` |
| `dft_single_point_v1` | `dft_single_point_energy_v1` | `scf_single_point` |
| `md_minimize_v1` | `md_reduced_unit_minimization_v1` | `minimize` |

## Lifecycle

`prepared → running → completed | failed | cancelled`

A completed workflow is immutable: re-execution raises rather than overwriting history. Cancellation
is only possible before completion. Retries append a new job attempt (`step_id`, `attempt_number` is
unique); no prior attempt, artifact or result is ever mutated or deleted.

## Preview versus create versus execute

* **`/simulation/routes/preview`** — what could run. Persists nothing.
* **`/simulation/workflows/preview`** — exactly what *would* run: the normalized parameters, the input
  checksum, the generated input files, the parser/builder/convergence versions. `executes_nothing: true`.
* **`/simulation/workflows`** — persists route, input snapshot, workflow and steps. Still runs nothing.
* **`/simulation/workflows/{id}/execute`** — the only endpoint that executes, within bounds.

## Parameters are never defaulted silently

Every required scientific parameter (cutoffs, k-point grid, tolerances, iteration budgets) must be
supplied explicitly. A missing one is a validation error naming the parameter — a hidden default would
be a fabricated scientific choice. Values are range-checked against reviewed minima and maxima.
