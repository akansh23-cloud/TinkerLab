# Phase 13.1 — Evidence envelopes and evidence tiers

## Scientific correction

Phase 13 begins from a stricter rule: a property without its applicability envelope is not admissible evidence for a condition-specific gate. Legacy TinkerLab selection currently allows missing conditions as a lower-ranked fallback. Phase 13.1 does not change decision semantics yet; it creates an additive custody layer so later phases can make unknown applicability blocking without destroying existing workflows.

## Existing production-data audit

The connected production database contained 592 material-property observations across 35 reference-library materials at implementation time. All 592 were literature/reference-library observations. None had a typed condition set, legacy condition payload, source-record link, or reported uncertainty. Their source reference explicitly identifies them as handbook/reference typical screening data and not qualification evidence.

Therefore an honest migration cannot assign 298.15 K, zero uncertainty, or measured provenance.

## Schema

`property_measurements_v13` is a one-to-one additive projection of legacy `material_property_observations`. It preserves the reported value/unit and provenance, adds explicit evidence tier/tier status, uncertainty distribution status, sample provenance, review state, and migration metadata.

`property_validity_envelopes_v13` stores applicability conditions. Temperature is represented by `temperature_k` plus `temperature_status = KNOWN | UNKNOWN | NOT_APPLICABLE`. Migrated records with no reported temperature receive `UNKNOWN` and null temperature. No temperature is imputed.

## Evidence tiers

The scientific tiers are `MEASURED_THIS_LOT`, `MEASURED_EQUIVALENT`, `PEER_REVIEWED`, `HANDBOOK`, `VENDOR_TYPICAL`, and `PREDICTED`. Tier is nullable because unknown provenance must remain unassessed. Synthetic demonstration rows are explicitly classified `NOT_SCIENTIFIC_EVIDENCE` rather than being laundered into a scientific tier.

Evidence tier is provenance, not a probability. Phase 13.1 does not assign `P(pass)` from a tier number. A helper already enforces the invariant that `PREDICTED` evidence cannot satisfy a blocking gate alone; evaluator wiring belongs to Phase 13.3.

## Migration rules

- Legacy rows are never rewritten or deleted.
- Reference-library / handbook-typical provenance maps to `HANDBOOK`.
- Supplier typical provenance maps to `VENDOR_TYPICAL`.
- Peer-reviewed provenance maps to `PEER_REVIEWED`.
- Computed/DFT/ML provenance maps to `PREDICTED`.
- Experimental evidence maps conservatively to `MEASURED_EQUIVALENT` unless explicit exact-lot metadata exists.
- Synthetic/demo evidence receives no scientific tier.
- Unknown provenance receives no tier and requires review.
- Missing temperature remains `UNKNOWN`.
- Missing uncertainty distribution remains `unspecified`; it is never converted to a point distribution.
- Canonical numeric values are backfilled only when the reported unit already equals the property definition's canonical unit. Runtime materialization may use the audited unit converter for safe conversions.

## Scope boundary

Phase 13.1 intentionally does not alter the current gate evaluator, recommendation state machine, material identity, expression grammar, condition models, stack/interface logic, or frontend. Those are later phases. This keeps the migration independently reviewable and reversible while preserving all working production behavior.
