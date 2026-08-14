# Multi-Objective Pareto Semantics

## Conservative values

For a prediction interval `[L, U]` and point estimate `P`:

- maximize: decision value = `L`;
- minimize: decision value = `U`;
- target `T`: after unit normalization, decision value = `max(|L-T|, |U-T|)`.

Point estimate and complete interval are retained; the conservative value is only the ranking representation.

## Canonical minimization vector

- maximize objectives are represented as `-conservative_value`;
- minimize and target-distance objectives use `conservative_value`.

A candidate with any incomplete objective has no normal Pareto vector and is explicitly excluded from standard front sorting. No imputation is performed.

## Dominance

Candidate A dominates B iff every minimization component of A is `<=` B and at least one is `<` B.

`non_dominated_sort` uses deterministic identity ordering and O(n²) pairwise comparisons. This is intentional under the hard Phase-5 pool cap of 200 candidates: at n=200 there are 19,900 unordered pairs. Increasing the pool materially requires algorithmic reassessment.

## Claims

The resulting label is **Pareto-optimal within evaluated campaign candidates**. It is not a statement of global material optimality.
