# Phase 5 Bounded Performance Profile

The profile uses isolated SQLite and synthetic generic hypotheses. It measures query/inference shape, not production latency.

## 200 candidates / 2 objectives

- preview: 49 SELECTs;
- one iteration execution: 76 SELECTs;
- 100-evaluation page: 2 SELECTs;
- inference batches: exactly 2 — one density batch of 200 targets and one tensile-strength batch of 200 targets;
- evaluated candidates: 200;
- Pareto unordered pairs: 19,900.

## Scaling sanity

The same profile with 20 candidates produced the same 49 preview SELECTs, 76 execution SELECTs and 2 page SELECTs, with exactly two prediction batches. This demonstrates the scientific read path is fixed/batched rather than query-per-candidate/property.

Persistence naturally grows with the number of prediction targets, snapshots, predictions and evaluation rows.

A pre-optimization profile exposed a query-per-candidate lookup of campaign constraint policies. Phase 5 now loads that policy map once per iteration.

The O(n²) Pareto implementation is acceptable only because Phase 5 caps the evaluated pool at 200. No production latency claim is made.
