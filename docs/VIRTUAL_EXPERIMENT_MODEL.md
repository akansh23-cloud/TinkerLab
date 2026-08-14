# Virtual Experiment Model

A Phase-5 virtual experiment is an auditable **model-backed computational evaluation**, not an experiment performed on matter and not a physics simulation.

## Campaign envelope

`VirtualExperimentCampaign` freezes the replacement-spec checksum, active search-space identity/version/checksum, policy key/version, seed, budgets and configuration checksum. `CampaignObjective` pins a property direction and immutable Phase-4 model version. `CampaignConstraintModelPolicy` maps project hard constraints to an explicit evidence/prediction hierarchy.

## Iteration

Each `CampaignIteration` stores its ordered input-pool checksum, prediction-run IDs, counts, Pareto-front checksum, parent-selection checksum, created/duplicate counts, decision checksum and stop signal/reason.

## Candidate evaluation

`VirtualCandidateEvaluation` stores:

- feasibility class and hard PASS/FAIL/UNKNOWN counts;
- complete objective point/conservative values;
- full uncertainty intervals;
- origin/model/prediction IDs;
- Pareto rank/dominance;
- uncertainty and acquisition components;
- parent-selection state;
- rationale;
- deterministic evaluation checksum.

Variable-size vectors use validated structured JSON payloads, while decision-critical fields remain first-class columns.

## Decision ledger

`OptimizationDecisionRecord` makes parent selection, rejection, mutation, duplicate handling and stopping auditable. `ParetoFrontSnapshot` freezes each computed front by ordered candidate IDs and objective-space checksum.

No record created by this layer is an experimental observation.
