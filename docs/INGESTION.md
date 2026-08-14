# Local CSV / JSON Ingestion

## Flow

`preview → validation report → explicit commit → immutable source record → normalized entities`

Phase 2 accepts a maximum 2 MB text payload. The web UI reads `.json` or `.csv` locally and sends text to the API. Imported formulas are data strings; no formula or code execution occurs.

JSON schema is demonstrated in `data/import_examples/phase2-demo-import.json`. CSV supports material identity plus one property observation per row and groups rows by `external_record_id`.

A commit is transactional. Validation errors abort the batch. The committed payload SHA-256 acts as an idempotency key within the organisation; repeating the same committed payload returns the original import batch.

Probable or ambiguous material identity halts import instead of silently merging records.
