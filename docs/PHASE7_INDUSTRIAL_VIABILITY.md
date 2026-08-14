# Phase 7 — Industrial Viability Engine

## Why this phase exists

A candidate can be scientifically excellent and industrially unusable. It can be cheap and
unmakeable, or makeable and unbuyable. Phase 7 assesses those questions separately from the science
and refuses to blend them.

## Industrial evidence is its own claim class

`IndustrialEvidence` never becomes a `MaterialPropertyObservation`, a `PropertyPrediction` or a
`SimulationResult`, and none of those become industrial evidence. Every row carries
`scientific_origin = industrial_evidence`.

## Comparability is structural, not optional

A cost figure without a currency, currency year and basis is not comparable with anything, so those
are columns and the API **rejects** an economic record that omits them. The same applies to
regulatory evidence without a jurisdiction, and to any time-varying claim without an `as_of_date`.

`CostBasisKey` (currency, currency year, cost basis) must match exactly before two monetary figures
are compared. When a constraint and its evidence disagree on basis, the result is
`INSUFFICIENT_EVIDENCE` with the available bases listed — **never** a silent conversion. USD 5/kg is
not evaluated against a EUR 10/kg limit even though 5 < 10.

## The eight dimensions

| Dimension | Source |
| --- | --- |
| Scientific suitability | Read from the Phase-5 virtual evaluation; never re-derived here |
| Manufacturing compatibility | Declared route compatibility records |
| Economic feasibility | Economic evidence on a matching basis |
| Supply resilience | Supply-chain evidence |
| Environmental evidence | Environmental evidence |
| Regulatory compatibility | Regulatory evidence, per jurisdiction |
| Technology maturity | Evidence-backed maturity assessment |
| Experimental validation | Always UNKNOWN in Phase 7 — physical records arrive in Phase 9 |

Each returns `PASS`, `FAIL`, `PARTIAL`, `UNKNOWN`, `INSUFFICIENT_EVIDENCE` or `CONFLICTING_EVIDENCE`.

## Missing evidence never becomes a pass

An unevaluable constraint reports `INSUFFICIENT_EVIDENCE`. Each constraint declares its own
`treat_missing_evidence_as` policy (`fail`, `unknown` or `insufficient_evidence`) so the choice is
explicit per requirement rather than a global assumption.

Specific cases worth naming:

* An **unrecorded** process compatibility is not compatibility. Silence is not a yes.
* A banned-element check with no declared composition reports insufficient evidence. Elements come
  only from a structural representation — never parsed out of a display name, because
  "silicon carbide substrate" is a label, not a composition.
* EU regulatory clearance is not JP clearance. Regulatory status does not transfer between
  jurisdictions, and evidence for one is not evidence for another.

## Roll-up is worst-wins

A single hard `FAIL` produces an overall `FAIL`. It is never averaged away by other dimensions
passing. Severity order: FAIL > CONFLICTING > INSUFFICIENT_EVIDENCE > UNKNOWN > PARTIAL > PASS.

## The composite score is opt-in and honest

No composite exists unless a methodology is named. The only implemented methodology is
`declared_weighted_mean_v1`, and even then:

* `UNKNOWN`, `INSUFFICIENT_EVIDENCE` and `CONFLICTING_EVIDENCE` dimensions are **excluded** from
  both numerator and denominator — never scored as zero, which would punish missing data, and never
  as full marks, which would reward it;
* the result carries `composite_is_partial` and the list of excluded dimensions;
* the per-dimension states remain the primary output. The number never replaces them.

## Conflicts stay visible

Two records that are comparable and whose ranges do not overlap are reported as
`CONFLICTING_EVIDENCE`. Both are retained. The newer one does not automatically win, nothing is
averaged across the contradiction, and the affected constraint yields no verdict.

Records on *different* bases are not reported as conflicts — incomparable is not the same as
contradictory, and conflating the two would manufacture false alarms.

## Maturity, deliberately not called TRL

Stages run theoretical → computationally evaluated → experimentally demonstrated → laboratory
reproducible → pilot demonstrated → manufacturing demonstrated → industrially established. They are
**not** labelled Technology Readiness Levels: TRL has a formal assessment procedure this system does
not perform, and borrowing the term would overstate what the evidence supports. Assessments are
superseded, never rewritten.

## Assessments are immutable and reproducible

Each assessment stores the evidence snapshot and constraint snapshot that produced it, plus an
`assessment_checksum`. When evidence changes, a new assessment supersedes the old one via
`superseded_by_id`; yesterday's conclusion remains readable and explainable exactly as it was made.
An unchanged evidence set reproduces an identical checksum.

## Seed data honesty

Every seeded industrial record is `source_type = seed_demonstration` and carries
`scientific_claim: false`. The values are synthetic and exist to exercise comparability, staleness,
conflict and constraint logic. They are not claims about the real cost, supply or regulatory status
of any material.
