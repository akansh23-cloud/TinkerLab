# Phase 8 — Material Functional Decomposition & Replacement Reasoning

## The question this phase answers

Not "what material is similar to silicon?" but **"what does silicon actually do here, and does this
candidate do it?"** Chemical similarity is not replacement. The chain the engine reasons over is:

```
Material → State → Structural Feature → Mechanism → Property → Function → Requirement
```

## A property belongs to a material in a STATE

`Silicon` is not a state. `Single-crystal silicon, diamond cubic Fd-3m, undoped, 300 K, Czochralski
as-grown` is. `MaterialState` records composition, structure, phase, polymorph, microstructure,
processing history and conditions, and carries a `state_checksum`.

**Properties do not propagate across incompatible states.** `match_states` returns:

| Quality | Meaning | Property reusable? |
| --- | --- | --- |
| `EXACT` | Same state identity | Yes |
| `COMPATIBLE` | No recorded incompatibility | Yes |
| `DIFFERENT_STATE` | A demonstrated difference (structure, phase, processing, temperature, environment) | **No** |
| `UNKNOWN_STATE` | One side has no recorded state | Not established — reported, never assumed |

A value recorded at 900 K does not satisfy a requirement at 300 K, even when the number would
comfortably pass. That is asserted by test.

## Structural identity is not composition

Diamond and graphite are both carbon. Their composition signatures match; their structure identities
do not. `structure_identity` derives from an actual periodic representation — cell metrics (lengths
and angles, so a rotated frame gives the same answer) plus sorted sites plus space group.

When no structural representation exists, the function returns **None**, not a formula-derived
stand-in. A formula-based identity would make diamond and graphite indistinguishable, which is
precisely the error this phase exists to prevent.

Composition signatures mark dopants explicitly: `Si` and `Si:B[dopant]` are different materials for a
semiconductor role. Stated ranges stay ranges — `10-30 at.%` is never collapsed to 20%, because a
midpoint is a number nobody measured.

## Processing history is ordered

Anneal-then-quench is not quench-then-anneal, and the history checksum reflects that.

## Application decomposition is generic

`Application → Component → MaterialRole → Function → Requirement`. Nothing in the engine branches on
a material, application or domain name — asserted by a test that greps the engine source for
domain-specific conditionals. The semiconductor study is *data*, supplied through the same API any
other domain would use.

Requirement directions: `minimum`, `maximum`, `range`, `target`, `maximize`, `minimize`,
`categorical`. A `target` direction **requires** an explicit tolerance; an arbitrary one is never
invented. An objective (`maximize`/`minimize`) reports `PARTIAL` rather than `PASS`, because ranking
against no threshold is not passing.

## Evidence origins stay separate

Each candidate value is tagged `observed`, `literature`, `predicted`, `simulated`, `experimental`,
`industrial` or `unknown`, and every value is listed individually. Origins are **never averaged**.

When several usable values exist, one *governs* by declared priority (experimental → observed →
literature → simulated → predicted → industrial). Preference decides what is reported as governing;
it never merges values and never hides the others.

Values excluded from use, and why:

* a **prediction outside its declared applicability domain** — the model itself says it does not
  apply here, so the number is shown and not used;
* an **unconverged simulation** — no estimate exists for one anyway (Phase-6 invariant), restated
  here defensively because the cost of being wrong is a fabricated pass;
* a value in a **demonstrably different state**.

Values whose state is merely *unrecorded* are used but flagged: the assessment adds an explicit
assumption that the evidence is not state-qualified. It is neither discarded nor trusted as an exact
match.

## Requirement statuses

`PASS`, `FAIL`, `PARTIAL`, `UNKNOWN`, `INSUFFICIENT_EVIDENCE`, `CONFLICTING_EVIDENCE`,
`STATE_MISMATCH`. When usable sources disagree on whether a requirement is met, the result is
`CONFLICTING_EVIDENCE` — both are retained, neither wins by recency, nothing is averaged.

## The reasoning graph

`ReasoningEdge` links typed endpoints with `edge_kind`, scope, conditions, confidence and provenance.
**An edge with neither linked evidence nor a source reference is refused** — unsourced causal claims
are exactly what this system must not accumulate. Every seeded edge carries a scope, so no link is an
unbounded universal law.

Chain confidence is the **weakest link**, not a product or an average: a chain is only as supported
as its least supported step. When no mechanism is recorded, the result is an empty list and a note
saying so — never a plausible-sounding invented mechanism.

## Structured reasoning before language

`reason_about_candidate` computes every status from stored structured data. Nothing in it calls a
language model. A natural-language explanation may be generated afterwards from this output and
**cannot change a PASS, FAIL or UNKNOWN**. Results are immutable and superseded, never rewritten.

## The semiconductor reference workflow

A power-electronics switching role with four functions (block electric field, limit leakage at
temperature, conduct heat away, carry current) and their requirements.

Two candidates demonstrate the full range of outcomes:

* **Silicon** has *no seeded property values at all*, so every requirement is honestly `UNKNOWN` and
  the overall status is `INSUFFICIENT_EVIDENCE`. This is the real state of the database and a more
  useful demonstration than a fabricated pass.
* A **clearly synthetic candidate** (labelled "SYNTHETIC — not a real material", with observations
  marked "Not a measurement") produces `PASS` on band gap, `FAIL` on thermal conductivity, `PARTIAL`
  on the mobility objective and `UNKNOWN` on breakdown field.

No real property value for silicon is invented anywhere. The requirement thresholds are illustrative
demonstration targets and are labelled as such.
