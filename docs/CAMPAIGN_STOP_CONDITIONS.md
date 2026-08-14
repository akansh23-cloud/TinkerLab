# Campaign Stop Conditions

Every bounded campaign terminates with an explicit auditable reason.

Implemented reasons include:

- `no_applicable_objective_predictions`;
- `no_eligible_parent_candidate`;
- `total_new_candidate_budget_reached`;
- `no_structurally_valid_unique_child_generated`;
- `maximum_iterations_reached`;
- `pareto_front_unchanged_configured_iterations` when an explicit unchanged-front count is configured;
- cancellation at the API/campaign lifecycle level.

Synchronous hard limits are:

- maximum 5 iterations per execution;
- maximum pool/prediction batch 200;
- maximum 100 parents/iteration;
- maximum 200 new hypotheses/iteration;
- maximum 500 new hypotheses/campaign.

A stop reason is a bounded-search result, never a claim that the global material search space has converged.
