# Candidate Generation

## Strategy registry

Strategies are explicitly registered with a key, version, supported families, required inputs, deterministic contract and safe candidate maximum.

### `known_material_retrieval` v1.0

Retrieves existing visible materials. Ranking is transparent and ordered by fewer known hard failures, more known hard passes, fewer unknown hard constraints, greater evidence coverage, fewer conflicts, then canonical identifier. Missing evidence remains UNKNOWN.

### `curated_component_substitution` v1.0

Uses only approved `SubstitutionRule` records. Rule provenance is copied into typed change records. Structural screening may reject an otherwise approved rule when the resulting candidate violates the active search space.

### `bounded_composition_variation` v1.0

Enumerates explicit amount grids. When the grid exceeds budget, a deterministic seeded subset is chosen. A configured balance component is adjusted deterministically to meet the target total. No chemistry is invented outside the configured representation.

### `bounded_process_variation` v1.0

Varies only configured numeric process-state parameters/ranges. Output is engineering data, never an executable recipe.

### `manual_hypothesis` v1.0

Scientist-authored concrete hypotheses receive the same fingerprint, structural checks, lineage and UNKNOWN evidence posture.

## Structural pre-screen

Checks include duplicate identities, negative amounts, search-space range violations, total tolerance, required/prohibited components, maximum component count, process parameter/range/unit validity and duplicate fingerprint.

Structural PASS must not be interpreted as predicted performance.
