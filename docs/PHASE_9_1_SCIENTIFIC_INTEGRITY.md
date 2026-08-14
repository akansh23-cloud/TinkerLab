# Phase 9.1 Scientific Integrity Contract

## 1. Evidence-origin separation

Observed/literature, predicted, simulated, industrial and experimental evidence remain separate records with separate provenance. Newer evidence never silently rewrites historical evidence.

## 2. Unit policy

Quantitative requirement evaluation validates unit compatibility and converts evidence into the requirement/comparison unit before numerical comparison. Raw value/unit and normalized value/unit remain available in structured results. Incompatible dimensions are not compared.

## 3. Material-state identity and matching

Canonical composition/state identity includes quantitative composition fields when supplied (stoichiometry, atomic fractions/ranges and dopant concentration/unit) plus state-defining structure/process/condition fields. Missing state-defining context cannot silently yield full compatibility. Matching distinguishes exact, compatible, conditionally compatible, unknown and incompatible outcomes with reasons.

## 4. Tenant evidence policy

Organisation-owned evidence is collected only inside the authenticated/development-scoped organisation. Project/candidate references must belong to the same accessible project/context. Public/global reference rows remain visible only where their model explicitly permits it. Private measurements, maturity assessments, predictions or simulations from another organisation cannot govern reasoning.

## 5. Industrial comparability

Industrial contradiction detection first establishes comparability. Context can include metric/unit, currency/year/basis, quantity basis, geography, jurisdiction, supplier context, manufacturing/process context, validity date and conditions. Evidence from different jurisdictions (for example EU vs Japan regulatory status) is not automatically contradictory.

## 6. Monetary evidence

A numeric economic point or range requires an explicit currency, currency year and cost basis. Missing monetary context is not invented to make legacy data pass validation.

## 7. Composite viability scores

Weights must use known dimensions, be finite and non-negative, and include at least one positive effective weight. Unknown/insufficient dimensions are not silently scored as zero. Effective methodology/weights/denominator are retained and emitted scores are bounded to `[0, 1]`.

## 8. Experimental admissibility

A measurement row is not automatically scientific evidence. The centralized admission policy checks:

- run lifecycle state;
- pinned protocol version/checksum;
- sample ownership/provenance/target;
- protocol property;
- instrument measurable-property capability and selection;
- protocol-required equipment capability declarations;
- calibration status, date validity and protocol-specific maximum calibration age;
- protocol-controlled conditions, including explicit missing-condition handling;
- protocol sample requirements that the current schema can represent (for example geometry, dimensional bounds and declared sample attributes);
- required control execution where configured;
- unit compatibility.

Admission outcomes are `accepted`, `provisional`, `rejected` or `invalidated_source` with structured reason codes.

## 9. Run lifecycle and invalidation

New runs follow `planned → ready → running → completed`, with allowed cancellation/invalidation transitions. Planned/ready rows cannot create accepted physical evidence; running measurements are provisional. Invalidating a run preserves measurements/history but makes them non-governing.

## 10. Experimental comparability

Experimental conflict detection first checks whether measurements are comparable by target/property, material state and recorded conditions. Different temperatures/pressures/etc. are not automatically conflicts. Missing comparison-critical context is treated as insufficient context rather than assumed equality.

## 11. Requirement support vs evidence existence

An admissible measurement is evaluated against the same deterministic requirement contract used by scientific reasoning:

- requirement passes → `EXPERIMENT_SUPPORTS_REQUIREMENT`;
- requirement fails → `EXPERIMENT_CONTRADICTS_REQUIREMENT`;
- uncertainty crosses the decision boundary → `EXPERIMENT_INCONCLUSIVE`;
- comparable experiments disagree → `EXPERIMENT_CONFLICTING`;
- no admissible experiment → `EXPERIMENT_NOT_AVAILABLE`.

A failed measurement can never become experimental support merely because the experiment was well executed.

## 12. Uncertainty

When explicit uncertainty/ranges are supplied they participate in threshold interpretation. Phase 9.1 does not invent statistical confidence or distributional assumptions that were not provided.

## 13. Validation snapshots

Persisted validation assessments retain candidate/project/target identity, requirement outcomes, measurement checksums/admissibility, run/protocol references, sample/instrument/calibration references, reasoning checksum, policy/methodology version and assessment checksum so later evidence does not make the historical decision inexplicable.

## 14. Replacement decision semantics

The replacement-decision endpoint is a transparent **next-gate** decision. It exposes scientific/experimental state, latest industrial state, hard blockers, unresolved hard requirements, conflicts and reason codes. `READY_FOR_NEXT_GATE` is not certification, regulatory approval or authorization for commercial production.

## 15. AI boundary

LLMs may later summarize or explain structured results. They do not decide scientific PASS/FAIL, evidence admissibility, unit conversion, experimental support or replacement-gate status.


## 16. Core experimental admission reason codes

Phase 9.1-B emits structured codes alongside human-readable reasons. Core hardening codes include `RUN_NOT_COMPLETED`, `RUN_INVALIDATED`, `PROTOCOL_PROPERTY_MISMATCH`, `INSTRUMENT_PROPERTY_MISMATCH`, `REQUIRED_EQUIPMENT_UNVERIFIED`, `PROTOCOL_CONDITION_MISSING`, `PROTOCOL_CONDITION_MISMATCH`, `SAMPLE_REQUIREMENT_CONTEXT_MISSING`, `SAMPLE_REQUIREMENT_MISMATCH`, `CALIBRATION_EXPIRED`, `CALIBRATION_EXPIRED_BY_PROTOCOL`, `UNIT_DIMENSION_MISMATCH`, `EXPERIMENT_SUPPORTS_REQUIREMENT`, `EXPERIMENT_CONTRADICTS_REQUIREMENT`, `EXPERIMENT_INCONCLUSIVE` and `EXPERIMENT_CONFLICTING`. Missing context is preserved as missing/provisional rather than fabricated.
