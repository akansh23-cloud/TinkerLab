# Replacement Specification

The authoritative representation is typed JSON, not a custom programming language.

The compiler emits:

- `specification_version`
- `project_id`
- baseline identity
- sorted replacement reasons
- sorted hard constraints
- sorted soft constraints
- sorted objectives
- semantic metadata
- `checksum`
- `generated_at`
- canonical JSON payload
- human-readable rendering

## Determinism

The SHA-256 checksum is calculated from canonical JSON with sorted keys and stable entity ordering. `generated_at` is excluded. Two compiles of unchanged semantic project content therefore have the same checksum.
