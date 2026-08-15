> **Phase 12.2 hardening note:** scientific-integrity, provenance and tenant-isolation corrections in `PHASE_12_2_INTEGRITY.md` supersede the corresponding Phase 12/12.1 implementation details.

# Phase 12.1 — Charts

Six graphics, each answering a question the tables could not. All hand-rolled SVG: no charting
dependency, deterministic output, and — the reason that matters here — full control over how
UNKNOWN is drawn. No general-purpose chart library knows that a missing measurement is a real
answer that must look different from a zero.

## 1. Ashby chart — `/explore`

The working instrument of materials selection. Two properties on **logarithmic** axes, materials
coloured *and shaped* by family.

The **material index guide lines** are the point. Ranking on raw strength answers the wrong
question: a tie rod is selected on σ/ρ, a beam in bending on σ^⅔/ρ, a panel on σ^½/ρ. On log axes
each is a straight line of slope 1/exponent, so the winner changes with the loading mode. Drawing
the scatter without them would look like an Ashby chart while omitting the reason anyone draws one.

The line is anchored to the material that maximises the index, exactly as the construction is used
on paper: everything above and left of it beats everything below and right, for that design case.

Verified against the reference library:

| Rank | Raw tensile strength | Specific strength σ/ρ | Bending σ^⅔/ρ |
| --- | --- | --- | --- |
| 1 | CFRP 1500 MPa | CFRP 0.938 | CFRP 0.082 |
| 2 | Ti-6Al-4V 950 | Ti-6Al-4V 0.214 | GFRP 0.029 |
| 3 | Al 7075 572 | GFRP 0.211 | Al 7075 0.025 |
| 4 | **316L 560** | Al 7075 0.204 | PPA-GF33 0.024 |
| 5 | **304 515** | PPA-GF33 0.141 | PA66-GF30 0.023 |

Steels dominate the raw column and vanish from the other two. Titanium is second on σ/ρ and drops
out of the top five on the bending index — the classic result, and precisely the mistake the chart
exists to prevent.

Indices are declared per axis pair. Offering "specific stiffness" on a cost-versus-lead-time chart
would be noise dressed as expertise, so `indices_for()` returns nothing there.

## 2. Decision matrix — project → Charts

Candidates × requirements. Hard requirements drawn first and ruled off from soft ones, because one
hard failure eliminates a candidate regardless of everything to its right.

Every cell carries a **glyph as well as a colour** (✓ ✕ ? ! ~ ≠). Roughly one man in twelve cannot
reliably separate the red and green, and this is the grid a qualification decision gets argued from.
Colour is the fast channel; the glyph is the reliable one. Conflicting sources get a magenta dot —
shown, never averaged.

## 3. Requirement margins

Signed percentage headroom against each threshold, normalised so **positive always means better than
required** whichever way the comparator points. That is what lets ≥ 145 °C and ≤ 8.5 USD/kg share
one axis without the reader reversing the sign for half the rows.

UNKNOWN renders as a hatched band across the whole track, never a zero-length bar. A zero-length bar
sits exactly on the threshold, which claims the candidate is *marginal* when the truth is that
nobody measured it.

Margins are computed **server-side** (`_margin_percent`) because a requirement is typed in datasheet
units and the observation is stored in its own. A browser-side approximation would silently produce
wrong margins for exactly the temperature-offset and per-mass-cost cases where conversion is not a
plain multiplication. Test `test_decision_chart_margin_survives_a_unit_mismatch` pins this: a 0.2 GPa
observation against a 100 MPa floor must read +100%.

## 4. Property deltas

Candidate vs incumbent per property. Colour follows whether the change **helps**, not whether the
number went up — a lower density and a higher strength are both green. Colouring by sign alone would
make half the chart read backwards.

## 5. Evidence mix

What each candidate's answers are actually made of: measured, predicted, simulated, or nothing.

This is the chart that stops a decision being taken on air. Two candidates can show the same pass
count while one is backed by measurement and the other by model output over blanks — and that
difference decides whether the next step is a purchase order or a test plan.

## 6. Search space bands

The search space drawn as what it is: composition bands around the incumbent, with the incumbent's
own amount marked and the discrete enumeration steps ticked. Previously it existed only as a table
of min/max/step and a checksum, and it was genuinely hard to see whether a derived space was sanely
bounded. Locked components render as a point, not a zero-width band — fixed by a decision (matrix,
redacted, dopant) is not the same as a band that happens to be narrow.

## Backend added

| Endpoint | Purpose |
| --- | --- |
| `GET /bench/property-space` | Points, axes, indices, and the named exclusions |
| `GET /bench/property-space/axes` | Only properties ≥ 2 materials actually have values for |
| `GET /bench/property-space/ranking` | Rank on a material index rather than a raw property |
| `GET /replacement-projects/{id}/decision-chart` | Chart-ready decision view with margins |

`decision_chart` re-shapes the canonical evaluator's output and adds exactly one derived quantity,
the margin. It never re-decides anything — `test_decision_chart_does_not_re_decide_anything` asserts
cell-for-cell agreement with `/comparison`.

## What the charts refuse to do

- **Never plot a material missing an axis value.** It goes to `excluded` with a reason and an "Add
  the data" button. Missing data is a finding, not a gap to close by imputation.
- **Never clamp onto a log axis.** A zero or negative value is excluded and named, because a log
  axis genuinely cannot represent it and clamping would place a point where it does not belong.
- **Never flatten origin.** A measured point and a model prediction differ in opacity and dash; the
  weaker of the two coordinates governs the marker, since a point is only as good as its worst axis.
- **Never let colour be the only channel.** Family carries a distinct marker shape, status carries a
  glyph.

## One thing the charts revealed

A study whose candidates are all generated composition hypotheses renders an entirely UNKNOWN
matrix. That is correct — a hypothesis is a formulation nobody has made, so it has no measurements,
and the platform will not inherit the baseline's properties to fill the grid. The matrix now says so
explicitly and points to the Prediction Lab, rather than looking broken.

## Verification

- API **501 passed, 6 skipped** (was 479 passed / 6 skipped). 22 new chart tests.
- Web **86 tests pass** (was 46). 40 new: 26 on scale/margin maths, 14 on components.
- `tsc --noEmit` clean, production build clean, **zero lint warnings**.

A real hooks-order bug was caught by the build and fixed: `AshbyChart` called `useMemo` after two
early returns, which would have crashed on the first render where the point set became empty.
