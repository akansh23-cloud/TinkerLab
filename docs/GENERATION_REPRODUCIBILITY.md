# Generation Reproducibility

Phase-3 generation is deterministic before sophisticated optimisation is introduced.

## Fingerprint canonicalization

Algorithm version: **`candidate-v1`**.

A fingerprint SHA-256 hashes canonical JSON containing:

- fingerprint version;
- material family;
- normalized component keys/roles;
- normalized numeric amounts;
- unit/basis/locked state;
- normalized process parameter keys/values/units.

Components/process parameters are sorted by semantic keys. Display labels, database IDs and timestamps do not affect the candidate fingerprint. Meaningful composition or process changes do.

## Search-space checksum

Algorithm version: **`search-space-v1`**. The checksum includes the auditable search-space version and all generation-relevant controls; editorial notes do not participate.

## Run envelope

`GenerationRun` stores:

- project/specification checksum;
- search-space ID/version/checksum;
- strategy key/version;
- configuration checksum;
- seed;
- requested budget;
- counts;
- result checksum.

`GenerationRunResult` stores the ordered fingerprints and disposition so duplicates remain visible. Re-running the same envelope produces the same ordered fingerprint sequence/result checksum; already-persisted candidates may be reported as duplicates on replay without changing the scientific sequence.
