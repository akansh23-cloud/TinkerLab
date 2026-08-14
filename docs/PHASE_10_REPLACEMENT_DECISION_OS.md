# Phase 10 — Closed-Loop Material Replacement Decision OS

Phase 10 is the layer that turns everything TinkerLab already knows into a decision someone can
defend in a design review. It does not add a new science engine. It consumes the existing ones —
Phase 8 requirement evaluation, Phase 7 industrial viability, Phase 9.1 experimental validation —
and answers three questions they individually cannot:

1. **Where does this replacement programme actually stand?**
2. **What is the single most valuable thing to do next, and why that rather than something else?**
3. **Can I defend this conclusion to a reviewer six months from now?**

## The five subsystems

### 1. Replacement Program Model

A `ReplacementProgram` binds one application role, one incumbent material state, one candidate
portfolio and one decision policy into a single studied object. It wraps an existing
`ReplacementProject` rather than replacing it, so every Phase 1–9.1 contract on that project keeps
working unchanged.

The program state is **resolved, not set**. A client cannot put a program into `DECISION_READY` by
sending a field; the resolver reads the evidence and reports the state the program is genuinely in.
The only two exceptions are `PAUSED` and `ARCHIVED`, which express human intent rather than an
evidence condition, and the API rejects any attempt to override anything else.

Program references are validated for coherence, not just for foreign-key validity. An incumbent
state that belongs to a different material is rejected, because a valid FK there would silently make
every requirement evaluation meaningless.

### 2. Candidate Portfolio & Decision Matrix

The decision matrix is requirement × candidate, and every cell carries the governing origin, the
per-origin outcomes, the coverage score and a plain-language `why`. It is deliberately **not**
collapsible into a single score.

The matrix vocabulary keeps non-answers first class:

| Status | Meaning |
|---|---|
| `pass` | The requirement is met on admissible evidence |
| `fail` | The requirement is definitively not met |
| `unknown` | No evidence exists — this is not a failure |
| `inconclusive` | Evidence exists but does not settle the question |
| `conflicting` | Origins disagree; resolved by investigation, never by preferring one |
| `not_comparable` | Units or states cannot be compared |
| `not_applicable` | The requirement does not apply to this candidate |

Coverage is **availability of evidence, never probability of success**. A candidate can have 100%
coverage on a requirement and still fail it — that is exactly what Candidate B in the demonstration
programme shows.

### 3. Evidence Gap & Next-Best-Action Engine

A gap says required evidence is absent, uncertain, conflicting or not comparable. It is never a
statement that a candidate failed, and the gap engine cannot emit one for a requirement that has
definitively failed.

Actions are proposed deterministically with a transparent priority:

```
priority = decision_impact × decision_value × candidate_relevance / cost_factor
```

Every factor comes from a declared lookup table, the formula travels with each action, and the score
is reproducible from the returned factors alone. This is deliberately **not** an expected value of
information: no probability distribution over experimental outcomes is estimated, and the payload
says so explicitly.

Actions carry dependencies (`RESOLVE_MATERIAL_STATE → COLLECT_REFERENCE_DATA → RUN_PROPERTY_PREDICTION
→ RUN_PHYSICS_SIMULATION → … → RUN_EXPERIMENT`) and the API refuses to mark a dependent action as
executing while a prerequisite is open, because evidence produced out of order cannot be interpreted.

**Recommending an action never starts it.** Expensive or physical work is only ever initiated through
its own product surface with its own authorization.

### 4. Closed-Loop Convergence Engine

Convergence answers "how close is this to a decision I could defend?" — not "how likely is this
replacement to work?". The second question is not answerable from the evidence TinkerLab holds.

States: `EARLY`, `SCREENING`, `EVIDENCE_BUILDING`, `VALIDATION_REQUIRED`, `CONFLICT_RESOLUTION`,
`NEAR_DECISION`, `DECISION_READY`, `NO_VIABLE_CANDIDATE`.

A presentation-only percentage exists for progress bars. It is derived from resolved-work counts,
always shipped beside the counts it came from, and always accompanied by an explicit disclaimer that
it is not a probability and carries no confidence level.

Evidence events are handled synchronously and in-process, with dependency-aware invalidation: a
measurement on one candidate re-evaluates that candidate, and the program-wide convergence
assessment. No message broker is introduced, because adding one to make a single-process
recomputation "event driven" would add operational surface without adding correctness.

### 5. Replacement Recommendation & Technical Dossier

The recommendation is the product's answer, and its most important property is that it is allowed to
be **`NO_SUITABLE_CANDIDATE`**. A tool that always produces a winner will eventually recommend
something unsafe, because the pressure to produce an answer never lets up while the evidence
sometimes does. When nothing is viable the system says so and offers program-level options — none of
which is ever executed automatically, and one of which is never "relax the requirement".

Statuses: `ADVANCE_CANDIDATE`, `ADVANCE_MULTIPLE_CANDIDATES`, `HOLD_FOR_EVIDENCE`, `INCONCLUSIVE`,
`NO_SUITABLE_CANDIDATE`, `REJECT_ALL`.

Recommendations are immutable and versioned. New evidence produces version N+1 plus a
`DecisionDelta` explaining the change in terms of requirements, evidence and blockers rather than
score movement. The superseded version is retained verbatim, because a conclusion someone may have
acted on must remain readable exactly as it was.

The technical dossier has 21 sections, every value read from stored platform data. A section with no
evidence renders as an explicit `UNKNOWN` statement rather than being quietly omitted — in the
demonstration programme the incumbent silicon profile reads `UNKNOWN` throughout, because no property
value is seeded for it and inventing a plausible one would be far worse than an honest gap.

## What Phase 10 must never do

These are enforced by tests, not just by convention:

- No LLM decides a PASS/FAIL, a ranking, a rejection, a convergence state, a next action or a
  recommendation. The dossier records `llm_narrative_used=False`.
- `UNKNOWN`, `INCONCLUSIVE`, `NOT_COMPARABLE` and `CONFLICTING` never reject a candidate on their own.
- Conflicting evidence never becomes a pass.
- Ranking never runs across the eligibility partition — a blocked candidate cannot out-rank an
  eligible one by being cheap.
- A requirement is never relaxed automatically.
- A recommendation is never presented as a qualification, regulatory or commercial authorization.

## Demonstration programme

The seed creates a fully labelled synthetic programme: replacing silicon in a high-temperature power
electronics switch (525 K junction, 3300 V blocking). Three BLOCKING requirements (breakdown field
≥ 2.0 MV/cm, band gap ≥ 2.5 eV, thermal conductivity ≥ 150 W/(m·K)) and one DESIRABLE objective
(electron mobility).

| Candidate | Outcome | Why |
|---|---|---|
| A (alpha) | **ADVANCE** | Evidence complete and consistent; every gate satisfied |
| B (beta) | **REJECT** | Replicated measurement (1.10, 1.18 MV/cm) contradicts its own observation (3.3) and the 2.0 threshold |
| C (gamma) | **HOLD** | Two BLOCKING requirements have no evidence at all; next action proposed |

Every candidate material is fictitious and every value is synthetic. Silicon itself deliberately
keeps no fabricated property values.

## API surface

32 routes under `/replacement-programs` and `/decision-policies`. All are organisation-scoped from
the request context; a resource belonging to another tenant returns **404, not 403**, because telling
a caller that a program exists but is forbidden already leaks that another organisation is running a
study.

Key endpoints:

- `GET /replacement-programs/{id}/header` — mission-control header
- `GET /replacement-programs/{id}/portfolio` — candidate board with eligibility partition
- `GET /replacement-programs/{id}/decision-matrix` — requirement × candidate matrix
- `GET /replacement-programs/{id}/evidence-gaps` — gaps grouped by class, blocking first
- `GET /replacement-programs/{id}/actions` — next-action queue
- `GET /replacement-programs/{id}/convergence` — state, metrics and disclaimer
- `GET /replacement-programs/{id}/ranking` — ranking, Pareto front and sensitivity
- `POST /replacement-programs/{id}/recommendation` — generate version N+1
- `POST /replacement-programs/{id}/dossier` — generate a technical dossier
- `POST /replacement-programs/{id}/events` — notify of new evidence, triggering scoped reassessment
- `PATCH /functional-requirements/{id}/decision-gate` — set criticality, origin, approval status

## Frontend

`/projects/{id}/replacement` — Replacement Mission Control. Header, nine-step workflow stepper,
portfolio board with eligibility filters, interactive decision matrix with an evidence drawer,
gap view grouped by class, next-action queue, convergence dashboard with its disclaimer, and the
recommendation view with dossier generation.

The design rule throughout: the interface must not be able to imply more certainty than the evidence
supports. `UNKNOWN` is always rendered explicitly rather than left blank, a rank always appears next
to what was excluded from it, and a recommendation always appears next to the note that it is not a
qualification decision.
