# Phase 10 — Decision Methodology

This document states exactly how each Phase-10 conclusion is computed, so that a reviewer can
reproduce any number the system reports and challenge any judgement it embeds. Every methodology
carries a version string that travels with the output.

| Methodology | Version |
|---|---|
| Portfolio / eligibility | `candidate-portfolio-v1` |
| Decision matrix | `decision-matrix-v1` |
| Evidence coverage | `evidence-coverage-v1` |
| Evidence gap | `evidence-gap-v1` |
| Next action | `next-action-v1` |
| Next-action priority | `next-action-priority-v1` |
| Convergence | `convergence-v1` |
| Ranking | `candidate-ranking-v1` |
| Pareto | `pareto-front-v1` |
| Sensitivity | `ranking-sensitivity-v1` |
| Recommendation | `replacement-recommendation-v1` |
| Decision delta | `decision-delta-v1` |
| Explainability | `explainability-v1` |
| Snapshot | `program-snapshot-v1` |
| Dossier | `technical-dossier-v1` |
| Program state | `program-state-v1` |

---

## 1. Requirement criticality

`criticality` is a decision-gate axis layered on top of Phase 8's `requirement_kind`. They are
different concepts: a hard gate and an optimization objective are not the same thing, and merging
them into the existing `weight` would have destroyed that distinction.

Criticality levels, in gating order: `BLOCKING`, `CRITICAL`, `IMPORTANT`, `DESIRABLE`,
`INFORMATIONAL`. Only `BLOCKING` and `CRITICAL` gate a decision. The rest inform ranking.

Legacy rows are backfilled deterministically from `requirement_kind`:

| requirement_kind | criticality |
|---|---|
| `hard_constraint` | `blocking` |
| `soft_constraint` | `important` |
| `objective`, `preference` | `desirable` |
| `informational` | `informational` |

This mapping lives in exactly one place (`CRITICALITY_FROM_REQUIREMENT_KIND` in
`app/models/entities.py`) and is used by the ORM column default, migration 0012's backfill and
`resolve_criticality()` alike, so a requirement classifies identically however it entered the
database. **Consequence:** no pre-Phase-10 conclusion changes when the migration runs.

A requirement whose `approval_status` is `PROPOSED` is tracked but never gates a decision. Nothing in
the system promotes a proposed requirement to accepted — that would let automated logic invent the
bar it is then judged against.

## 2. Evidence coverage

For each requirement × candidate, the policy declares which evidence types are expected for that
criticality. Coverage is the fraction present:

```
coverage_score = |expected_evidence_types present| / |expected_evidence_types|
```

For `BLOCKING` requirements the default expectation is both a computational origin and an
experimental one, so an unmeasured candidate sits at 0.5 rather than 1.0.

**Coverage is availability, not success.** This is the single most important thing not to misread.
Candidate B in the demonstration programme has coverage 1.0 on breakdown field and is simultaneously
unsuitable for it.

## 3. Eligibility partition

Every candidate lands in exactly one bucket before anything is ranked:

- **BLOCKED** — a gating requirement definitively `FAIL`ed, or an industrial hard constraint failed.
- **UNRESOLVED** — a gating requirement is not settled (`UNKNOWN`, `INCONCLUSIVE`, `CONFLICTING`,
  `NOT_COMPARABLE`).
- **ELIGIBLE** — nothing gating is outstanding.

Only a definitive `FAIL` may appear as a blocking failure. `UNKNOWN` and its relatives are
outstanding work, not verdicts, and a test asserts this directly.

Experimental contradiction is treated as a definitive blocker only when the policy's
`auto_reject_on_experimental_contradiction` is set; otherwise it is recorded and left to a human.

## 4. Decision gates

The policy names which gates must be satisfied. Six are implemented:

| Gate | Satisfied when |
|---|---|
| `NO_DEFINITIVE_BLOCKING_FAILURE` | No gating requirement has definitively failed |
| `ALL_BLOCKING_REQUIREMENTS_RESOLVED` | Every `BLOCKING` requirement is `PASS` |
| `CRITICAL_EVIDENCE_COVERAGE_MET` | Every gating requirement meets the policy coverage minimum |
| `NO_UNRESOLVED_CRITICAL_CONFLICT` | No gating requirement has origins that disagree |
| `INDUSTRIAL_BLOCKERS_RESOLVED` | See below |
| `REQUIRED_EXPERIMENTS_COMPLETE` | Requirements the policy says need measurement have enough admissible replicates |

A policy that names a gate this build does not implement is reported as `GATE_NOT_IMPLEMENTED` and
**unsatisfied** — silently passing an unknown gate is how a tool becomes unsafe.

### The industrial gate, and why it excludes two dimensions

The industrial gate checks that the overall industrial state is not `fail` or `conflicting_evidence`,
that an assessment exists, and that `manufacturing_compatibility` and `regulatory_compatibility` are
resolved to `pass` or `partial`.

It deliberately **excludes** two of Phase 7's eight dimensions:

- `experimental_validation` — the Phase-7 engine by design cannot see Phase-9 measurements, so it is
  structurally always `UNKNOWN` there and reports so honestly. Because the industrial roll-up takes
  maximum severity, requiring this dimension to be resolved would make the gate permanently
  unreachable and **no candidate could ever advance**. Phase 10 tests physical validation directly
  and far more precisely in `REQUIRED_EXPERIMENTS_COMPLETE`.
- `scientific_suitability` — reports a coarse Phase-5 feasibility class that requires a virtual
  campaign to exist. Phase 10 evaluates scientific suitability requirement-by-requirement in the
  decision matrix, so re-testing the coarse version here would double-count it and block candidates
  that were never screened through a virtual campaign.

This exclusion is a genuine judgement call and is stated in the policy record itself so it is
visible, versioned and overridable rather than buried in code.

## 5. Ranking

Hierarchical, in three steps that cannot be reordered:

1. Eliminate BLOCKED candidates.
2. Separate UNRESOLVED candidates.
3. Score only ELIGIBLE candidates.

A blocked candidate can therefore never out-rank an eligible one by scoring well on cost.

Scoring is a weighted mean over normalized objectives. Normalization is min-max **across the ranked
set**, so a score is a relative position within this programme, not an absolute quality. Where an
objective has no evidence for a candidate, it is excluded from that candidate's score and named in
`excluded_dimensions` — never imputed as 0.5 or as zero. Where every candidate is identical on an
objective, all receive 0.5, so a non-discriminating objective cannot inflate scores.

Objectives and directions: `performance_margin` (max), `industrial_viability` (max), `cost` (min),
`supply_security` (max), `manufacturing_fit` (max), `sustainability` (max), `evidence_confidence`
(max). Minimize-objectives are inverted once, centrally, after normalization.

`performance_margin` is the criticality-weighted fraction of gating requirements that `PASS`, counting
only requirements with a verdict — so absence of evidence does not read as poor performance.

**A rank is not a quality score and not a probability.** Every response says so.

## 6. Pareto analysis

Strict dominance over normalized objective vectors. A candidate dominates another when it is at
least as good on every objective **both have a value for** and strictly better on at least one.
Objectives where either candidate lacks a value are skipped for that pair — comparing a measured
value against a missing one would manufacture a dominance relationship out of an evidence gap.

Non-dominated candidates are reported as genuine trade-offs rather than resolved into a single winner
by whichever weight vector happened to be configured.

## 7. Sensitivity

A bounded, deterministic, one-at-a-time weight sweep. Each scenario multiplies exactly one
objective's weight by one declared multiplier (default `0.5, 0.75, 1.25, 2.0`) and re-ranks. That
keeps scenario count at objectives × multipliers rather than exploding combinatorially, and makes
each result attributable to a single nameable change.

Outcomes: `STABLE_WINNER`, `WEIGHT_SENSITIVE` (a declared variation changes first place — the leader
depends on the weights, not on the evidence alone), `NEAR_EQUIVALENT_CANDIDATES` (top two within the
margin — stable ordering, but the separation is not scientifically meaningful), `NOT_APPLICABLE`.

No probability distribution over weights is assumed, so no confidence in the ranking is claimed.

## 8. Next-action priority

```
priority = decision_impact × decision_value × candidate_relevance / cost_factor
```

All four factors come from declared lookup tables keyed on criticality, gap class, candidate
eligibility and action cost class. The formula string and every factor are returned with each action,
so the number is reproducible from the payload alone — a regression test recomputes it.

This is **not** an expected value of information. No probability distribution over experimental
outcomes is estimated. The payload states this explicitly, and a test asserts that no priority factor
is named after a probability, likelihood, confidence or expected value.

Actions carry `depends_on` and are `BLOCKED` while prerequisites are open. Superseded actions are
marked `SUPERSEDED`, never deleted.

## 9. Convergence

State is an ordered ladder, evaluated top-down, so the reported state is the earliest genuine
obstacle rather than the most flattering claim:

1. No candidates / no requirements → `EARLY`
2. All candidates blocked → `NO_VIABLE_CANDIDATE`
3. Gates satisfied and no blocking gap → `DECISION_READY`
4. Unresolved conflicts → `CONFLICT_RESOLUTION`
5. Blocking gaps with outstanding physical validation → `VALIDATION_REQUIRED`
6. Blocking gaps otherwise → `EVIDENCE_BUILDING`
7. Eligible candidates awaiting final gates → `NEAR_DECISION`
8. Otherwise → `SCREENING`

The presentation percentage is:

```
progress = 100 × Σ(resolved counts) / Σ(total counts)
```

over blocking requirements, critical requirements, experimental requirements and industrial
dimensions, skipping any category with a zero denominator. It exists for progress bars only and is
always shipped with the disclaimer that it describes completed decision work, is not a probability,
and carries no confidence level.

## 10. Recommendation

Status is decided by a fixed ladder over the eligibility partition:

- Multiple candidates satisfy all gates → `ADVANCE_MULTIPLE_CANDIDATES`
- Exactly one → `ADVANCE_CANDIDATE`
- Candidates exist, none held, some rejected → `NO_SUITABLE_CANDIDATE`
- Conflicts and nothing held → `INCONCLUSIVE`
- Anything held → `HOLD_FOR_EVIDENCE`
- Otherwise → `INCONCLUSIVE`

Rationale prose is assembled deterministically from reason codes. No language model is involved in
producing or altering any status, rank, action or recommendation. An LLM may later reword these
strings; it cannot originate them.

## 11. Reproducibility

The snapshot checksum is computed over sorted canonical content with no timestamps and no generated
identifiers, so identical program state always hashes identically. It captures requirement versions,
the portfolio, material states, every evidence reference, the decision policy and all methodology
versions.

The recommendation checksum covers the policy version and checksum, the status, the three candidate
partitions, per-candidate gate outcomes and the convergence checksum. A changed evidence base
therefore always changes the checksum — the golden workflow test asserts exactly this.

## 12. Known limitations

- **Two reasoning passes per candidate per request.** Phase 9.1's `replacement_decision` internally
  re-invokes `reason_about_candidate`, and Phase 9.1 must not be modified, so the same reasoning runs
  twice. `PortfolioContext` memoizes aggressively to contain the cost, but the duplication is real.
- **Coverage expectations are policy-declared, not derived.** The system does not infer which
  evidence types a given property genuinely requires; an operator declares it in the policy.
- **Normalization is programme-relative.** Scores are not comparable across programmes.
- **The industrial gate excludes two dimensions** (documented above). This is a judgement call, not a
  neutral fact, and a different organisation may reasonably configure it differently.
- **Sensitivity is one-at-a-time.** Interaction effects between two simultaneously changed weights
  are not explored.
