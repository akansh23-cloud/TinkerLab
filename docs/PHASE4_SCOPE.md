# Phase 4 Scope — Property Prediction & Uncertainty

Phase 4 adds trustworthy model-backed property prediction without physics simulation or autonomous optimization.

## Implemented

- model registry and lifecycle metadata;
- immutable/checksummed model versions;
- safe reviewed JSON model artifacts only;
- typed applicability domains;
- deterministic known-material/hypothesis feature snapshots;
- explicit missing/redacted inputs;
- condition-aware applicability assessment before inference;
- bounded preview and synchronous batch execution (max 200 targets);
- separate prediction targets/input snapshots/runs/results;
- mandatory prediction uncertainty;
- deterministic result/run checksums;
- explicit prediction fallback in comparison;
- conservative interval-aware PASS/FAIL/UNKNOWN;
- Prediction Lab, run and prediction provenance views;
- synthetic demo predictor with unmistakable warning.

## Not implemented

No DFT, MD, CALPHAD, ML force field, autonomous experiment selection, Bayesian/evolutionary optimization, active learning, patent/novelty search, synthesis planning, lab execution, robotics, training pipeline, Kubernetes or microservice decomposition.
