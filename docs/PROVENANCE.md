# Provenance

For imported data, TinkerLab stores:

1. `SourceProvider`
2. `SourceRecord.external_record_id`
3. retrieval/import timestamp
4. source version when supplied
5. parser/adapter version
6. SHA-256 of raw payload
7. SHA-256 of normalized payload
8. raw JSON snapshot where permitted
9. Evidence referencing that source record
10. Observation referencing evidence and optionally the source record directly

The observation inspector exposes checksums and parser version without exposing raw private payloads through the public API.

The source record is a snapshot identity. Re-ingesting changed raw content creates a distinct checksum snapshot rather than overwriting history.
