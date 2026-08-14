# Convergence is not exit code zero

This is the single most important distinction in Phase 6.

## Two separate recorded facts

* `operational_status` — did the process complete? (`completed`, `failed`, `timed_out`, `cancelled`)
* `scientific_status` — is the result scientifically usable? (`converged`, `unconverged`, `partial`,
  `parser_failed`, `not_applicable`)

They live in separate columns on `simulation_results` and are displayed separately in the UI. A clean
exit code with an unmet tolerance is `completed` + `unconverged`.

## Three sequential gates

1. **Operational** — did it run? If not, no parse is attempted.
2. **Parse** — did the registered parser extract the required quantities, and are they finite?
   A NaN or a missing marker yields `parser_failed` and **no** property estimate.
3. **Convergence** — did the registered convergence evaluator confirm the method's own criterion?
   For the fixture: gradient magnitude below tolerance. For MD: max force below tolerance. For DFT:
   an explicit SCF convergence flag — `pw.x` exiting cleanly without one is `unconverged`.

## The gate on property estimates

A `simulation_property_estimates` row is created **only** when `scientific_status == converged`, the
quantity maps to a registered property definition, and the unit converts cleanly into the canonical
unit. The integrity endpoint reports `estimates_from_non_converged_results`, which must always be zero.

## What a tolerance is not

`numerical_tolerance` records the numerical convergence criterion of the solver. It is explicitly
**not** a statistical prediction interval and **not** an accuracy claim against experiment. Method
error (functional choice, empirical potential quality, basis-set limitations) is carried separately as
`method_limitations` text, not as a number that could be mistaken for uncertainty quantification.
