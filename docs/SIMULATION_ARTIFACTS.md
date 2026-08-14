# Simulation artifacts

Every input file, stdout, stderr and output file is stored as a row with a SHA-256 content checksum,
byte count and truncation flag.

## Storage references are opaque

`simulation://{workflow_id}/{role}/{file_name}`. A host filesystem path is never returned through the
API — asserted by a test that scans the whole workflow-detail payload for absolute paths.

## Redaction and tenancy

Artifacts are private by default and scoped to the owning organisation. Representation redaction flags
propagate into the input snapshot, so a redacted component is visible as *redacted*, never as content.

## Truncation is disclosed

Output caps (64 KB stdout, 32 KB stderr, 256 KB artifact) are applied at write time and the artifact
row carries `truncated: true` plus an explicit marker in the stored text. Silent truncation would make
a parser failure look like a solver failure.

## Checksums feed the result

`output_artifact_checksums` on the result is the sorted list of output-artifact checksums, and it
participates in the result checksum. Changing an output changes the result identity.
