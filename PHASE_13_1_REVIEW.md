# Phase 13.1 review handoff

Branch: `phase13-1-review`

## Current-model audit

- Property observations already carry optional condition-set linkage, uncertainty fields, evidence/source linkage, and unit metadata.
- Condition selection currently allows missing conditions as a lower-ranked `partial` fallback. That is the principal path by which a handbook value with unknown temperature can still reach a scalar gate.
- Project constraints remain scalar (`property_key + comparator + threshold`) and the recommendation engine may advance a candidate when every configured gate returns satisfied.
- Existing functional-requirement and material-state subsystems should be extended by later Phase-13 work rather than duplicated.

## Spec corrections applied in 13.1

1. Temperature cannot be `NOT NULL` during honest legacy migration because unknown temperature is not room temperature. Phase 13 therefore stores `temperature_status` separately and permits null `temperature_k` only for explicit UNKNOWN/NOT_APPLICABLE states.
2. Evidence tier is provenance, not a probability. Phase 13.1 does not derive confidence or P(pass) from tier ordinal.
3. Unknown provenance is not automatically HANDBOOK. The tier remains null/UNASSESSED unless source metadata supports a mapping.
4. Synthetic demonstration evidence receives `NOT_SCIENTIFIC_EVIDENCE`, not a scientific tier.
5. Missing uncertainty does not become a point distribution. It is `unspecified`.

## Production audit informing migration

At implementation time the connected production database contained 592 material-property observations across 35 reference-library materials. All 592 were literature/reference-library observations, all lacked condition sets/legacy conditions, all lacked reported uncertainty, and their shared source explicitly identifies them as handbook/reference typical screening data rather than qualification evidence. These rows can therefore be migrated honestly to `HANDBOOK + temperature UNKNOWN + distribution unspecified + review_required`.

## 13.1 implementation

- Additive `property_measurements_v13` custody table; legacy observations remain untouched.
- One-to-one `property_validity_envelopes_v13` applicability table.
- Evidence-tier and classification enums, including explicit unassessed/non-scientific operational states.
- Conservative legacy-tier classifier.
- Explicit temperature-known/unknown contract.
- Runtime legacy materializer using the audited unit converter when safe.
- PREDICTED-tier blocking-gate guard primitive for later evaluator integration.
- Alembic `0014_phase13_1` migration and matching Vercel-backend mirror.
- Tests covering handbook migration, unknown-temperature honesty, synthetic evidence exclusion, unknown-tier behavior, and predicted-tier blocking-gate prohibition.

## Stop point

No gate evaluator, material identity, property model, interface stack, decision-state, Pareto, discovery, or frontend behavior is changed in this branch. Those remain Phase 13.2+ and require review of this custody layer first.
