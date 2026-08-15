> **Phase 12.2 hardening note:** scientific-integrity, provenance and tenant-isolation corrections in `PHASE_12_2_INTEGRITY.md` supersede the corresponding Phase 12/12.1 implementation details.

# Phase 12 — Intake Bench

## What was actually wrong

The scientific core was not broken. Every lab was correctly refusing to run without its inputs, and
there was no way to supply those inputs. That combination produces something indistinguishable from
a broken deployment.

Three defects, in order of how much damage they did.

### 1. Materials could not be created

`POST /materials`, `/materials/{id}/observations`, `/composition`, `/process-state` and `/evidence`
all existed and were all tested. No screen called any of them. The Materials Explorer was a search
box over four fictional seed polymers named "Demo Engineering Polymer P-100". The only route to new
data was a CSV import center.

So the platform was a read-only viewer wrapped around a write-capable API.

### 2. Every lab was gated on a search space no screen could create

`CandidateSearchSpace` is required, and required to be *active*, by candidate generation and by
virtual campaigns. `POST /replacement-projects/{id}/search-spaces` existed. No UI called it.

The consequence, in the code as shipped:

```tsx
// candidate-lab/page.tsx
{active && <div className="card">…Search Space Builder…</div>}   // never rendered
// virtual-lab/page.tsx
<button disabled={create.isPending || !selectedA || !activeSpace}>Create draft campaign</button>
```

A project created through the eight-step wizard had no search space, so the Search Space Builder
card never rendered and the Virtual Experiment Lab's only button was permanently disabled — with no
text anywhere explaining why. Only the single seeded demo project, whose space was written directly
by `seed.py`, ever worked.

### 3. Missing organisation scope silently 404s every lab

Every Phase-3+ endpoint calls `_scoped_project`, which returns 404 when `X-Organisation-ID` is
absent. The web client sends it from `NEXT_PUBLIC_ORGANISATION_ID`. If that variable is unset in the
Vercel project — easy to do, since it is in `.env.vercel.example` as a placeholder — search spaces,
generation runs and virtual campaigns all return "not found" and the labs render empty.

This is correct server behaviour and an invisible client failure.

## What Phase 12 adds

A composition layer over the existing services. It creates and inspects **inputs**. It contains no
evaluator, produces no verdict, and writes no value into the decision path.

### Backend — `app/services/bench/`

| Module | Responsibility |
| --- | --- |
| `catalog.py` | 60+ engineering properties with test standards, datasheet aliases and per-family plausibility ranges |
| `presets.py` | 9 industrial application briefs with realistic requirement sets, stated assumptions and watch-outs |
| `library.py` | 35 real engineering grades across polymer, alloy, ceramic and composite |
| `intake.py` | One-shot transactional material intake with an enforced provenance ladder |
| `derive.py` | Derives a valid, activatable search space from the baseline composition |
| `readiness.py` | Walks each lab's precondition chain and returns a fix per blocker |
| `studies.py` | Study bootstrap; baseline-derived requirements; library installation |

New routes are registered last so they can never shadow a scientific endpoint. The derivation routes
sit at `/replacement-projects/{id}/search-space-derivation` rather than under `/search-spaces/`,
because the generation router owns `GET /search-spaces/{search_space_id}` and is registered first —
a nested literal path would have been captured as a search-space id and 404'd.

### Frontend

| Route | Purpose |
| --- | --- |
| `/materials/new` | Material intake: identity, provenance, composition, properties by engineering domain |
| `/materials/[id]/add-data` | Append a second source without overwriting the first |
| `/studies/new` | Three-step replacement brief that produces a study with a working search space |
| `/projects/[id]` → Readiness tab | Per-lab status with an inline fix button per blocker |

`LabGate` is embedded in the Candidate, Prediction and Virtual labs. `ConfigWarning` names the
missing `NEXT_PUBLIC_ORGANISATION_ID` explicitly instead of letting it look like an empty database.

## Design decisions worth defending

**The data grade is a closed table, not a field.** Each intake declares provenance, and that
declaration sets evidence type, source quality and confidence. The service writes the grade's
confidence and ignores any supplied by the caller. Letting a request assert its own confidence would
have made the whole evidence hierarchy decorative — and making a system easy to put data into is
precisely where that hierarchy tends to get quietly eroded.

Grades claiming external authority (accredited lab, supplier datasheet, published literature) are
refused without a source reference, because an unverifiable provenance claim is worse than an honest
estimate.

**Compliance is boolean, never an objective.** `reach_svhc_present`, `rohs_compliant`,
`pfas_present`, `flammability_ul94_v0` are boolean gates. `create_study` rejects any attempt to make
one an optimisation objective, with the reason stated. Market access does not trade off against a
strength margin, and a weighted score would let it.

**Plausibility warns; it never blocks or corrects.** A value outside the handbook range for its
family produces a warning and is stored exactly as entered. The person entering a genuinely unusual
number is the one you least want to refuse.

**A second source is added, never merged.** Supplier says 180 MPa, your rig says 150 — both are
kept under separate evidence records and the existing conflict detector surfaces the disagreement.
That disagreement is usually the most decision-relevant fact in the record.

**Derivation is conservative and explains its refusals.** Narrow bands around the incumbent, matrix
as balance component, redacted and amount-less components held fixed, step widened automatically
until the enumerated grid fits the safe limit. When the baseline has no usable composition,
derivation returns a named blocker and a fix rather than an invalid space that fails validation
later with an opaque code.

**Library values are graded honestly.** Every observation from the reference library is written as
`evidence_type=literature`, `source_quality=handbook_typical`, `confidence=0.55`, `status=reported`.
The intake service cannot raise that grade. Good enough to shortlist on, never good enough to
certify on, and the system is required to know the difference.

## Reference library contents

35 grades. Polymers: PA66-GF30, PA6-GF30, PBT-GF30, PPA-GF33, PPS-GF40, PEEK, PEI, PC, PC/ABS, ABS,
POM, PP, PP-TD20, HDPE, PET, EVOH, PLA, PTFE, PVDF, TPU. Alloys: 6061-T6, 7075-T6, A380, AZ91D,
Ti-6Al-4V, 316L, 304, S355, CuZn39Pb3. Ceramics: alumina 96%, 3Y-TZP zirconia, sintered SiC.
Composites: CFRP UD, GFRP, SMC.

Three are deliberate regulatory incumbents so restriction-driven studies have something realistic to
replace: **CuZn39Pb3** carries 3% lead (`reach_svhc_present: true`, above the 0.1% threshold and
outside RoHS without exemption), and **PTFE** and **PVDF** carry `pfas_present: true`.

Every polymer entry states that its values are dry-as-moulded, and every glass-filled entry states
that they are flow-direction.

## Application presets

Automotive under-hood polymer · EV battery pack component · Food-contact packaging film · Reusable
medical device housing · Aerospace secondary structural bracket · PFAS-free low-friction coating ·
Consumer appliance housing · Chemical process wetted component · Generic cost-out / dual-source.

Each carries `assumptions` (what was taken for granted) and `watch_outs` (where the numbers mislead)
so an engineer can see immediately where their case differs.

## Verification

- API: **485 tests pass**, up from 450. 35 new Phase-12 tests.
- Web: **46 tests pass**, `tsc --noEmit` clean, production build clean.
- End-to-end: fresh database → install library → record material → create study → derived space
  activated → 12 candidates generated, with readiness reporting correctly at each step.

The Phase-12 suite asserts the two failures directly: `test_study_creation_produces_an_active_search_space`
and `test_readiness_names_the_missing_search_space_as_the_blocker`, the latter also firing the
offered fix and confirming it clears.

### One pre-existing defect fixed

`components/__tests__/validation.test.tsx` asserted that `inconclusive` renders as
"MEASUREMENTS CONFLICT". It does not, and should not: `ValidationState` has a separate
`conflicting_experiments` member. Labelling insufficient evidence as an observed conflict would
assert a disagreement that was never measured — the exact overstatement the badge exists to prevent.
The test now targets `conflicting_experiments`, with a second test asserting `inconclusive` does not
claim a conflict.

## Deployment

```bash
python -m alembic upgrade head
python -m app.db.seed
python -m app.db.seed_bench      # reference library, idempotent
```

`scripts/bootstrap-neon.sh` runs all three. No migration is required: Phase 12 adds no tables, and
missing property definitions are created on demand from the catalogue, so a database migrated before
Phase 12 accepts new engineering properties without a re-seed.

**Set `NEXT_PUBLIC_ORGANISATION_ID` in the web project's Vercel environment variables.** Without it
the labs return 404 and appear empty. The UI now says so explicitly, but the fix is configuration.

---

# Phase 12.1 — Charts

Six graphics, all hand-rolled SVG. No charting library: the bundle stays small, the output is
deterministic and diffable, and — decisively — nothing in a general-purpose library knows that
UNKNOWN is a real answer that must never be drawn as zero.

## The instruments

**Ashby chart** (`/explore`, and on each study's Charts tab). Two properties on log axes, materials
by family, with **material index guide lines**. The guide lines are the whole point: a tie rod is
selected on σ/ρ, a beam in bending on σ^⅔/ρ, a panel on σ^½/ρ, and those lines have different
slopes, so the winning material changes with the loading mode. A scatter without them looks like an
Ashby chart while omitting the reason anyone draws one.

The line is anchored to the material that maximises the selected index, exactly as the construction
is used on paper: everything above and left of the line beats everything below and right, for that
design case.

Verified against the reference library — on E^½/ρ (beam in bending):

```
1. CFRP UD              index=0.2296   E=135,000 MPa   ρ=1600
2. Silicon carbide      index=0.2066   E=410,000 MPa   ρ=3100
3. Alumina 96%          index=0.1480   E=303,000 MPa   ρ=3720
```

SiC has three times the modulus of CFRP and still loses. That inversion is the chart earning its
keep, and it is what ranking on a raw property gets wrong.

**Decision matrix.** Candidates × requirements. Hard requirements are drawn first and ruled off from
soft ones, because one hard failure eliminates a candidate regardless of everything to its right.
Eliminated candidates are marked ⊘.

**Requirement margins.** Signed percentage headroom against each threshold, normalised so positive
always means "better than required" whichever way the comparator points — that is what lets a
≥ 145 °C requirement and a ≤ 8.5 USD/kg requirement share one axis.

**Property deltas.** Candidate against incumbent. Colour follows whether the change *helps*, not
whether the number went up, so a lower density and a higher strength are both green.

**Evidence mix.** What each candidate's answers are actually made of. Two candidates can show the
same pass count while one is backed by measurement and the other by model output over blanks — and
that difference decides whether the next step is a purchase order or a test plan.

**Search space bands** (Candidate Lab). The composition space as bands around the incumbent, with
the enumerated step ticks drawn. Previously visible only as a table of min/max/step and a checksum,
which made it genuinely hard to see whether a derived space was sensibly bounded.

## Rules the charts follow

**UNKNOWN is never zero.** A zero-length margin bar sits exactly on the threshold, which claims the
candidate is marginal when the truth is that nobody measured it. Unmeasured requirements get a
hatched band reading "NOT MEASURED — no margin exists". `margin_percent` is `null`, never `0`.

**Missing data is named, not dropped.** Materials absent from a property-space chart are listed with
the reason and an "Add the data" link. Silently shrinking the population would make the chart look
complete while hiding the gaps.

**Margins are computed server-side.** A requirement is stated in the unit the engineer typed and the
observation is stored in the unit the datasheet used. Comparing them needs the real unit registry —
a client-side approximation would produce silently wrong margins for exactly the temperature-offset
and per-mass-cost cases where the conversion is not a plain multiplication. Verified: a 2400 kg/m³
ceiling against a value recorded as 1.20 g/cm³ reports 50% headroom, not 100%.

**Colour is never the only channel.** Every matrix cell carries a glyph (✓ ✕ ?) as well as a colour,
and every family carries a marker shape as well as a colour. About one man in twelve cannot reliably
separate the red and green used for FAIL and PASS, and this grid is what a qualification decision
gets argued from.

**Prediction never looks like measurement.** Point opacity is set by the weaker of a point's two
coordinate origins — a point is only as trustworthy as its least trustworthy axis.

**Boolean gates have no percentage margin.** A compliance status passes or blocks; a percentage
would imply it can be partially satisfied.

**Log axes, because the data demands it.** Polymer and ceramic moduli differ by ~10³. A linear axis
collapses every polymer into one pixel column; there is a test asserting exactly this.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /bench/property-space` | Points, axes, indices, and named exclusions |
| `GET /bench/property-space/axes` | Only properties ≥2 materials actually have values for |
| `GET /bench/property-space/ranking` | Rank on a material index rather than a raw property |
| `GET /replacement-projects/{id}/decision-chart` | Matrix cells, margins and origin mix |

The decision chart re-shapes the canonical evaluator's output and adds one derived quantity, the
margin. It never re-decides anything — there is a test asserting cell-by-cell agreement with
`/comparison`.

## Verification

API **505 passed**, 6 skipped (was 485). Web **86 passed** (was 46), typecheck and build clean.
