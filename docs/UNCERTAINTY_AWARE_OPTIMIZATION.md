# Uncertainty-Aware Optimization

Phase 5 never reduces a model result to a point estimate alone.

## Hard constraints

For every project hard constraint, Phase-4 interval-aware evaluation is reused:

- wholly satisfying interval -> PASS;
- wholly violating interval -> FAIL;
- interval crossing, missing value, unsupported/OOD model or incomplete evidence -> UNKNOWN.

Campaign feasibility is then:

- `robustly_infeasible` if at least one hard FAIL exists;
- `uncertain` if no FAIL exists and at least one UNKNOWN exists;
- `robustly_feasible` only when every hard constraint is known PASS.

UNKNOWN is never rewarded as success.

## Objective uncertainty

The full `[lower, point, upper]` state is stored. Conservative ranking uses adverse interval bounds. A normalized uncertainty component is calculated as:

`interval_width / max(abs(point), 1e-9)`

Missing values are marked incomplete and assigned an uncertainty component for exploration bookkeeping, but they do not gain a Pareto vector.

## Exploration

`uncertainty_exploration_v1` may select uncertain-but-not-hard-failed hypotheses if objective predictions are complete. It does not claim information gain and does not retrain any model.
