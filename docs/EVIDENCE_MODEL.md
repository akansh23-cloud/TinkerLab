# Evidence Model — Phase 2

Evidence is not synonymous with truth or confidence.

Phase 2 separates:

- `evidence_type`: experimental, literature, supplier, computational, predicted, user-provided, seed-demo.
- `status`: reported/reviewed/superseded/retracted.
- `source_quality`: curator/provider classification when available.
- `confidence`: retained from Phase 1 for compatibility; it must not be interpreted as calibrated scientific certainty.
- observation uncertainty: numeric uncertainty fields belonging to the reported property observation.
- provenance: provider/source-record/parser/checksum chain.

Superseded and retracted evidence remains stored. Default observation selection excludes it but provenance remains inspectable.

Seed evidence is always `seed_demo` with `demo_only=true` and `scientific_claim=false` metadata.
