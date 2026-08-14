# Optimization Policy Contract

Phase 5 registers policies in code; user-supplied executable policies are not loaded dynamically.

Each policy declares key/version, determinism, objective-count bounds, uncertainty semantics, UNKNOWN handling and maximum candidate-pool size.

## robust_pareto_v1 1.0

1. Preserve prediction intervals.
2. Classify hard feasibility before objective ranking.
3. Build conservative objective vectors.
4. Perform deterministic non-dominated sorting.
5. Eligible mutation parents must be structurally valid hypotheses and not robust hard failures.
6. Parent order: robustly feasible before uncertain, lower Pareto rank first, then larger normalized uncertainty burden, then stable candidate identity.
7. Exploration-disabled campaigns restrict parents to robustly feasible candidates.

## uncertainty_exploration_v1 1.0

Uses the same conservative Pareto ranking and hard-failure exclusion. Parent order is robustly feasible before uncertain, lower Pareto rank, then descending normalized uncertainty width, then stable identity. The value is called `uncertainty_priority`, not information gain.

## lexicographic_pareto_baseline_v1 1.0

Uses the same feasibility and Pareto calculation. Parent order is feasibility class, Pareto rank, lexicographic conservative minimization vector, then stable identity. It provides a deterministic reference behavior independent of the exploration heuristic.

## No AI score

Policies do not return a single opaque quality score. The stored decision state retains objective vectors, intervals, feasibility, rank and acquisition components separately.
