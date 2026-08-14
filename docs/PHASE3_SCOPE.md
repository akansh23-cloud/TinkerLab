# Phase 3 Scope

Phase 3 introduces a **bounded Candidate & Replacement Generation Engine** on top of the Phase-2 knowledge/evidence graph.

## Included

- known-material retrieval;
- candidate hypotheses separate from canonical materials;
- versioned/search-space configuration;
- approved substitution rules;
- bounded composition variation;
- bounded process-state variation;
- manual hypothesis capture;
- deterministic fingerprints and deduplication;
- structural pre-screening;
- generation-run reproducibility envelope;
- candidate lineage and typed change records;
- Candidate Lab UI;
- privacy scoping for search spaces, runs and hypotheses.

## Explicitly excluded

No Phase-3 component performs:

- ML property prediction;
- generative foundation-model material invention;
- DFT, MD, CALPHAD or ML force-field calculations;
- Bayesian/evolutionary/active-learning optimisation;
- patent/novelty search;
- synthesis protocol generation;
- robotics/laboratory execution;
- production SSO/billing/Kubernetes.

The stop condition is a trustworthy candidate-generation substrate. Phase 4 is reserved for model-backed property prediction and uncertainty.
