# Simulation value selection policy

## Default behaviour is unchanged

By default, project comparisons continue to use the Phase 1-5 behaviour: evidence first, then model
prediction. Simulation results do **not** enter comparisons automatically. Adding Phase 6 changed no
existing campaign, evaluation or ranking — asserted by a test that compares campaign evaluation
checksums byte-for-byte before and after simulation runs.

## Explicit opt-in only

A simulated value is used only when a `simulation_selection_policies` row exists for that exact
`(project, property, target)` triple. Creating one requires a written rationale (minimum 10 characters),
records the creating user, and pins a specific workflow.

Even then, the value is returned only if the pinned workflow has a converged result carrying an
estimate for that property. Otherwise the API returns `selected: false` with the reason.

## Always labelled

A selected value carries `scientific_origin: physics_simulation`, the policy key and version, the
result checksum, the numerical tolerance and its basis, and the method limitations. It is never
displayed as though it were measured evidence.

## Campaign escalation is read-only

`/virtual-campaigns/{id}/simulation-escalation` maps campaign candidates to simulation targets. It
creates nothing and mutates nothing. Escalating to physics assessment never replaces a Phase-5
prediction and never reranks completed campaign history.
