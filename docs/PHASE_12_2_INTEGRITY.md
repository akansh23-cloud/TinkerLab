# TinkerLab Phase 12.2 — Scientific Integrity, Evidence Semantics & Tenant Hardening

Phase 12.2 is a hardening release for the Phase 12 intake bench and Phase 12.1 decision charts. It deliberately adds no second decision engine: scientific statuses still come from the canonical evaluator. This release fixes unsafe input, provenance, shared-library and organisation-scope behaviour around that evaluator and makes the visual layer describe evidence more faithfully.

## Release goals

1. A malformed study must fail before any replacement project is committed.
2. Baseline-derived requirements must preserve or improve the *desirable* state, not blindly copy the incumbent state.
3. Weak or conflicting evidence must not silently become a hard qualification gate.
4. A project id must never function as a bearer secret across organisations.
5. Shared reference-library materials must be immutable to tenants.
6. Decision charts must distinguish measurement, supplier, literature, computed, simulation, prediction and estimate provenance.
7. Materials Project credentials must remain server-side and ingested data must retain provider identity/provenance.

## Scientific-integrity fixes

### Semantic boolean requirements

The property catalogue already declares whether a boolean's desirable state is true or false. Phase 12.2 uses that semantic polarity during baseline derivation. For example:

- `rohs_compliant` targets `true`.
- `reach_svhc_present` targets `false`.
- `pfas_present` targets `false`.

An adverse incumbent state is therefore something a replacement is allowed and encouraged to improve, not a state the auto-generated constraint preserves.

### Transactional study validation

The Phase 12 study request now uses the same domain vocabulary as the evaluator:

- typed comparators;
- typed hard/soft strength;
- typed objective directions;
- bounded weights, priorities and severities;
- boolean/numeric target-shape validation;
- unit/dimension validation through the existing domain validators.

Every requirement and objective is validated before the project row is created. Invalid input therefore returns `422` without leaving a half-created study.

### Provenance-aware baseline derivation

`app.services.bench.provenance` defines one explicit evidence taxonomy and ordering. It is used for both automatic derivation and chart presentation instead of relying on lexical string ordering.

- accredited/internal measurement: may seed a hard floor;
- supplier declaration: may seed a hard floor but emits an independent-verification warning;
- peer-reviewed literature, physics simulation, computed database, model prediction and handbook/reference values: start soft and require engineering review;
- engineering estimates: start soft;
- unknown/missing provenance: blocked from automatic derivation.

Unresolved evidence conflicts are blocked from auto-derivation rather than resolved by picking whichever observation happens to have the highest confidence.

## Tenant hardening

Private replacement-project endpoints require `X-Organisation-ID` and query the project by both project id and organisation id. This includes readiness, search-space derivation, baseline-derived requirements and decision-chart views. A missing or wrong scope returns `404`.

`/bench/property-space/axes` now counts only public materials plus materials owned by the requesting organisation, so the axis catalogue cannot disclose that another tenant has private property data.

Shared seed/reference-library materials are read-only through the property-append endpoint. Tenant measurements should be attached to a tenant-owned material/evidence overlay rather than changing the global reference record.

## Evidence-safe charts

Decision-chart cells now include selected observation id, evidence type, source quality and a resolved provenance category. The evidence-mix chart uses those categories rather than calling all stored values “measured evidence”.

Ashby/property-space points now expose the selected observation ids, evidence/source quality, conditions and x/y provenance. The point marker uses the semantically weaker of the two evidence sources, not alphabetical `min()` ordering. Older Phase 12.1 responses remain renderable; their generic `known_evidence` bucket is conservatively displayed as uncategorised/declared evidence rather than upgraded to a measurement.

Property-delta colours are directional only when the catalogue declares `higher_is_better` or `lower_is_better`. Neutral, target-band and application-dependent properties are shown as changes without claiming improvement/regression.

Decision-chart candidate evaluation failures are returned under `excluded_candidates` and surfaced in the UI instead of silently reducing the candidate count.

Search-space bands now derive their scale/unit from the search-space amount basis and total target instead of assuming every space is 0–100%.

## Materials Project integration

The existing governed external-ingestion connector is retained and hardened rather than duplicated. Configuration:

```env
MATERIALS_PROJECT_API_KEY=<your key>
MATERIALS_PROJECT_API_BASE_URL=https://api.materialsproject.org
```

Set both only in the API/server environment; never create a `NEXT_PUBLIC_MATERIALS_PROJECT_API_KEY` variable. Provider status is visible at `GET /external-data/providers`, and the Data Sources UI reports whether the server credential is configured without exposing the secret.

The connector uses bounded/paginated summary queries, preserves the Materials Project material identifier, stores content-addressed snapshot metadata and maps computed properties to explicit computational provenance. The API base URL is configurable for test/deployment purposes while defaulting to the official service.

## Deployment metadata

Phase 12.2.1 supersedes the split-deployment guidance below. Production Vercel now uses one Services project and same-origin `/api`; `NEXT_PUBLIC_API_BASE_URL` is not required unless `NEXT_PUBLIC_API_MODE=external` is explicitly selected. See `VERCEL_DEPLOYMENT.md`.

## Verification performed for this release

Backend targeted regression run:

- `tests/test_api.py`
- `tests/test_phase11_external_ingestion.py`
- `tests/test_phase12_bench.py`
- `tests/test_phase12_charts.py`
- `tests/test_phase12_2_integrity.py`

**Result: 134 passed.**

The repository currently collects **521 backend tests**. A single complete-suite run was started during packaging but exceeded the execution window before completion; no full-suite pass is claimed here. The external real-solver tests also depend on local LAMMPS/Quantum ESPRESSO availability.

Ten new Phase 12.2 adversarial tests cover:

1. adverse/positive regulatory boolean polarity;
2. handbook evidence deriving soft gates;
3. malformed comparator rejection before project creation;
4. wrong-dimension target rejection transactionally;
5. cross-organisation project/chart/readiness/search-space access;
6. shared reference-library immutability;
7. private property-axis metadata isolation;
8. unresolved baseline conflict blocking;
9. semantic weakest-provenance ordering;
10. server-side canonicalisation of requirement thresholds used by feasible-region charts.

Python source compiles successfully. Changed frontend TypeScript/TSX files pass a TypeScript syntax-transpile check. A complete frontend typecheck/Vitest run is not claimed because this source ZIP does not contain installed `node_modules`, and the packaging environment does not have all project npm dependencies available offline.

## Remaining boundary

Phase 12.2 makes generic property-space points disclose the selected observation and its conditions, but generic exploration still chooses a representative observation by curation/confidence/recency rather than solving an application-specific condition-matching problem. Qualification decisions should continue to use the study evaluator; the generic Ashby explorer should be treated as exploration, not as a substitute for condition-aware qualification.
