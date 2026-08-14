# Phase 9.1-A Implementation Report — Scientific Integrity, Provenance & Decision Correctness

## Status

Implemented and gated before Phase 9.1-B work began.

## Principal changes

- Corrected Phase-5 → Phase-7 feasibility integration to consume `VirtualCandidateEvaluation.feasibility_class` deterministically.
- Added organisation scoping to maturity and reasoning evidence collectors and strengthened candidate/evidence reference checks.
- Added canonical unit normalization before requirement comparison, including the `68 MPa` vs `1 GPa` regression.
- Hardened material-state composition signatures with quantitative fraction/dopant fields and stricter missing-context semantics.
- Added explicit industrial comparability before contradiction detection.
- Closed monetary point/range validation gaps (`currency`, `currency_year`, `cost_basis`).
- Constrained viability composite weights to known finite non-negative dimensions and bounded emitted scores.
- Rolled minimum-maturity constraints into the technology-maturity dimension consistently.
- Replaced nullable three-column manufacturing-compatibility uniqueness with PostgreSQL partial unique indexes.
- Hardened reasoning/provenance cross-reference paths and added regression coverage.

## Migration

`0010_phase9_1a` replaces the ineffective nullable `MaterialProcessCompatibility` unique constraint with two target-specific PostgreSQL partial unique indexes. Existing scientific rows are not rewritten.

## Regression coverage

`tests/test_phase9_1a_integrity.py` covers unit conversion, composition/state identity, cross-tenant evidence, candidate provenance, jurisdiction comparability, monetary validation, composite scoring, Phase-5 feasibility mapping and maturity behavior. Existing Phase-7/8 tests were updated only where prior expectations encoded unsafe semantics.

## Gate result

Phase 9.1-A passed its complete backend gate (apart from the already-expected external solver skips) before Phase 9.1-B implementation began. After both sub-phases, the combined package gate is **318 passed, 6 skipped (324 collected)**; the final package details are recorded in the Phase-9.1-B report.

## Known boundary

Production authentication remains outside this phase; `X-Organisation-ID` is still a development scoping seam. Phase 9.1 ensures data-path scoping under that identity rather than claiming the seam itself is production authentication.
