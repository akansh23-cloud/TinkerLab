# Campaign Reproducibility

All scientific checksums use canonical JSON + SHA-256 and exclude display labels/timestamps where they do not alter scientific meaning.

## Configuration checksum

Pins:

- replacement-spec checksum;
- search-space ID/version/checksum;
- ordered objectives and pinned model versions/artifact semantics;
- constraint-model policies;
- policy key/version;
- random seed;
- iteration/candidate/parent budgets;
- mutation/exploration configuration.

## Iteration input checksum

Includes ordered candidate scientific identities/fingerprints and iteration number. Prediction runs are Phase-4 persisted records and their result checksums feed the Phase-5 decision checksum.

## Evaluation checksum

Includes candidate scientific identity, prediction-result checksums, feasibility, objective vectors/intervals, Pareto rank/dominance, uncertainty/acquisition components and policy/version.

## Decision checksum

Includes campaign configuration checksum, iteration input checksum, ordered prediction-run result checksums, selected parent scientific identities, generated child fingerprints, Pareto-front checksum and stop reason.

## Campaign result checksum

Includes the immutable campaign configuration checksum, ordered iteration decision checksums, final-front checksum and final stop reason.

Campaign-created hypothesis IDs are deterministic from `project_id + candidate-v1 fingerprint`; scientific checksums depend on fingerprints rather than random candidate database IDs.

The synthetic fixture has deterministic replay tests; changing meaningful configuration such as seed/objectives changes the configuration/result envelope as expected.
