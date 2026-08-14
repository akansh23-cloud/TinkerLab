# Candidate Lineage

Every generated/manual hypothesis is traceable to a parent baseline or explicitly represented parent.

`CandidateLineageEdge` records child, parent kind/reference, relationship type, generation run, sequence and rationale. Phase-3 generation currently uses baseline-parent lineage and does not permit arbitrary cyclic graph construction.

`CandidateChangeRecord` provides typed diffs such as:

- `component_substitution`;
- `component_amount_change`;
- `process_parameter_change`;
- `known_material_selection` where applicable;
- `manual_hypothesis`.

Each change records a semantic target path, before/after payload, optional substitution-rule ID and rationale. Lineage is an audit structure, not scientific evidence of performance.
