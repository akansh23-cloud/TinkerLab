# Composition / Formulation Model

`MaterialComponent` is intentionally generic enough for formulations while not pretending all material families share one representation.

Fields include component name/ID, role, amount value or range, unit, amount basis, uncertainty, evidence, sequence, notes and redaction state.

Phase 2 validates quantitative bases and preserves qualitative/redacted components. Crystallographic lattice/site representation is deferred to a later domain-specific layer.

A composition must not be inferred from `composition_summary`; the legacy summary is display/backward-compatibility text only.
