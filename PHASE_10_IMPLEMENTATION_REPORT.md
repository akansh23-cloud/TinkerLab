# Phase 10 — Implementation Report

## 1. Architecture summary

Phase 10 is a **decision layer**, not a new science engine. It consumes the canonical outputs of
Phase 8 (requirement evaluation), Phase 7 (industrial viability) and Phase 9.1 (experimental
validation) and composes them into a defensible replacement decision. It reimplements none of them.

A single `PortfolioContext` batches and memoizes every upstream call for one request, which is what
keeps an N-requirement × M-candidate matrix from collapsing into an N×M reasoning explosion.

```
ReplacementProgram ──┬── PortfolioContext (batching / memoization)
                     │      ├── reasoning.reason_about_candidate   (Phase 8)
                     │      ├── experiments_lab.replacement_decision (Phase 9.1)
                     │      └── industrial.assess_industrial_viability (Phase 7)
                     │
                     ├── coverage.py    → decision matrix, evidence coverage
                     ├── portfolio.py   → eligibility partition, decision gates
                     ├── gaps.py        → evidence gap classification
                     ├── actions.py     → deterministic next-best action
                     ├── ranking.py     → hierarchical ranking, Pareto, sensitivity
                     ├── convergence.py → convergence state and metrics
                     ├── recommendation.py → recommendation, decision delta, explainability
                     ├── programs.py    → lifecycle, timeline, evidence events
                     └── dossier.py     → snapshots and the 21-section dossier
```

## 2. Files added

**Backend services** (`apps/api/app/services/replacement/`, 4,033 lines)

| File | Lines | Responsibility |
|---|---|---|
| `policy.py` | 311 | Versioned decision policy, criticality resolution, checksums |
| `context.py` | 317 | Batching/memoizing layer over Phase 7/8/9.1 |
| `coverage.py` | 365 | Evidence coverage and the decision matrix |
| `portfolio.py` | 405 | Eligibility partition, gate evaluation, portfolio board |
| `gaps.py` | 323 | Gap classification and ordering |
| `actions.py` | 523 | Deterministic next-best-action engine |
| `ranking.py` | 417 | Ranking, Pareto front, sensitivity sweep |
| `convergence.py` | 283 | Convergence state and metrics |
| `programs.py` | 445 | Program lifecycle, timeline, evidence events |
| `recommendation.py` | 669 | Recommendation, decision delta, explainability |
| `dossier.py` | 649 | Snapshots and the technical dossier |

**Other new files**

| File | Lines |
|---|---|
| `app/api/routes/replacement.py` | 765 |
| `app/schemas/replacement.py` | 294 |
| `app/db/seed_phase10.py` | 525 |
| `alembic/versions/0012_phase10_replacement_decision_os.py` | 403 |
| `tests/test_phase10_replacement_decision_os.py` | 765 |
| `tests/test_phase10_golden_workflow.py` | 289 |
| `docs/PHASE_10_*.md` (3 documents) | — |
| `apps/web/app/projects/[id]/replacement/page.tsx` | 1 flagship screen |
| `apps/web/components/` | 6 new components |
| `apps/web/components/__tests__/ReplacementDecisionUI.test.tsx` | 9 tests |

## 3. Files modified

| File | Change |
|---|---|
| `app/domain/enums.py` | ~20 new StrEnums appended; nothing existing altered |
| `app/models/entities.py` | 10 new models; 7 new columns on `FunctionalRequirement`; shared `CRITICALITY_FROM_REQUIREMENT_KIND` mapping |
| `app/api/router.py` | Registered `replacement_router` |
| `app/db/seed.py` | Calls `seed_phase10` |
| `app/services/units.py` | **Bug fix** — registered missing electric-field and mobility units |
| `apps/web/lib/api.ts` | Phase-10 response types appended |
| `apps/web/app/projects/[id]/page.tsx` | Added Mission Control navigation link |

## 4. Migration

`0012_phase10` — revision `0012_phase10`, down-revision `0011_phase9_1b`, now at head. Forward-only
and additive: no previous migration is edited and no existing column is dropped or retyped.

Creates 10 tables: `decision_policies`, `replacement_programs`, `scientific_actions`,
`evidence_gap_snapshots`, `convergence_assessments`, `replacement_recommendations`,
`decision_deltas`, `replacement_program_snapshots`, `technical_dossiers`, `program_timeline_events`.

Adds 7 columns to `functional_requirements` with a deterministic backfill from `requirement_kind`
(see the methodology document). **No pre-Phase-10 conclusion changes when the migration runs.**

Verified by generating offline PostgreSQL DDL: 10 `CREATE TABLE`, 55 `JSONB` columns, correct
`ALTER … SET NOT NULL` ordering after backfill.

## 5. New models

`DecisionPolicy`, `ReplacementProgram`, `ScientificAction`, `EvidenceGapSnapshot`,
`ConvergenceAssessment`, `ReplacementRecommendation`, `DecisionDelta`, `ReplacementProgramSnapshot`,
`TechnicalDossier`, `ProgramTimelineEvent`.

## 6. API routes

**33 routes** registered under `/replacement-programs`, `/decision-policies` and
`/functional-requirements/{id}/decision-gate`. All organisation-scoped from request context;
cross-tenant access returns **404, not 403**.

## 7–8. Methodologies and security

See `PHASE_10_DECISION_METHODOLOGY.md` for all 16 versioned methodologies.

Security guarantees, each covered by a test:

- Organisation scope is taken from the request context, never from a client-supplied field.
- Cross-tenant program, recommendation, snapshot, dossier, timeline, portfolio, matrix, gap,
  convergence and action access all return 404.
- A request with no organisation scope is refused.
- An event naming a candidate outside the program's portfolio is refused.
- A program cannot be created against another organisation's project.
- An incumbent state belonging to a different material is refused.

## 9. Test results

```
385 passed, 6 skipped
```

- **318** pre-existing Phase 1–9.1 tests — unchanged, no regressions.
- **65** new Phase-10 regression tests.
- **2** golden end-to-end workflow tests.
- **6 skipped** — pre-existing LAMMPS and Quantum-ESPRESSO solver tests. The binaries are absent in
  this environment; the skips predate Phase 10 and are unrelated to it.

Frontend: **9 new component tests pass**; `typecheck`, `lint` and `build` all clean.

## 10. Bugs found and fixed

Three real defects surfaced while building the golden scenario:

**(a) The industrial gate was unreachable.** Phase 7 computes `experimental_validation` without
access to Phase-9 measurements, so it is structurally always `UNKNOWN`; because the roll-up takes
maximum severity, `overall_state == "pass"` was effectively impossible and **no candidate could ever
advance**. The gate was redefined to test specific resolvable dimensions, with the two exclusions
documented in the policy record itself.

**(b) Missing unit registry entries (pre-existing).** Phase 8 registered `breakdown_field` (MV/cm)
and `electron_mobility` (cm²/(V·s)) as property definitions but never added those units to
`app/services/units.py`, so any evidence carrying them was rejected as `UNIT_DIMENSION_MISMATCH`.
The Phase-8 seed happened to leave those properties unmeasured, which hid the gap entirely. Fixed
additively — both dimensions are new, so no existing conversion changed behaviour.

**(c) ORM default silently downgraded hard constraints.** The `criticality` column initially
defaulted to a flat `"important"`, contradicting the migration backfill and quietly removing hard
constraints from the gating set. Now derived from `requirement_kind` through a single shared mapping
used by the ORM default, the migration and `resolve_criticality()` alike.

## 11. Known limitations

- **Two reasoning passes per candidate per request.** Phase 9.1's `replacement_decision` internally
  re-invokes `reason_about_candidate`, and Phase 9.1 must not be modified. `PortfolioContext`
  memoization contains the cost but the duplication is real.
- **Coverage expectations are policy-declared, not derived.**
- **Ranking normalization is programme-relative**, so scores are not comparable across programmes.
- **The industrial gate excludes two Phase-7 dimensions** — a judgement call, made visible and
  overridable in the policy rather than buried in code.
- **Sensitivity is one-at-a-time**; interaction effects between simultaneously changed weights are
  not explored.
- **Events are synchronous and in-process.** No broker is introduced.

### Pre-existing failure not fixed

`apps/web/components/__tests__/validation.test.tsx` fails: it expects `MEASUREMENTS CONFLICT` but
`ValidationStateBadge` renders `INCONCLUSIVE`. Both files predate this work. Fixing it means editing
Phase 9.1 UI behaviour or its test expectations, which the Phase-10 brief explicitly forbids
weakening — so it has been left in place and reported rather than silently made green. It is
unrelated to Phase 10 and does not affect any Phase-10 test.

## 12. Screens

`/projects/{id}/replacement` — **Replacement Mission Control**: header with incumbent and program
state, nine-step workflow stepper, portfolio board with eligibility filters and Pareto markers,
interactive decision matrix with an evidence drawer showing every origin considered, gap view grouped
by class (blocking first), next-action queue with reproducible priorities, convergence dashboard with
its non-probability disclaimer, recommendation view with dossier generation, and a program timeline.

Six new components: `MatrixCellBadge`, `EvidenceGapBadge`, `ProgramStateBadge`, `EligibilityBadge`,
`ActionPriorityBadge`, `QualificationNotice`.

## 13. Demonstration data

A fully labelled synthetic programme — replacing silicon in a 525 K / 3300 V power-electronics
switch — exercising all three real outcomes:

| Candidate | Outcome |
|---|---|
| A (alpha) | **ADVANCE** — evidence complete and consistent, every gate satisfied |
| B (beta) | **REJECT** — replicated measurement contradicts a BLOCKING requirement |
| C (gamma) | **HOLD** — two BLOCKING requirements unevidenced, next action proposed |

Every candidate is fictitious; silicon itself keeps no fabricated property values, so the incumbent
column honestly reads `UNKNOWN`.

## 14. Phase 11 readiness

Phase 10 leaves clean seams for what comes next:

- **Optional LLM narrative.** `TechnicalDossier.llm_narrative_used` already exists and is `False`.
  A narrative layer can reword deterministic strings without ever originating a conclusion.
- **Policy authoring UI.** `DecisionPolicy` is versioned and checksummed; only the editing surface
  is missing.
- **Async execution.** `ScientificAction` already carries status, dependencies and
  `result_reference`; a worker can drive it without schema change.
- **Multi-programme comparison.** Snapshot checksums make cross-programme diffing tractable.
- **Dossier export.** Sections are structured data; PDF/DOCX rendering is a presentation concern.

## 15. Verification commands run

```bash
# Backend
python3 -m pytest                              # 385 passed, 6 skipped
python3 -m compileall -q app alembic tests     # clean
python3 -m ruff check <phase-10 files>         # All checks passed
python3 -m alembic history                     # 0012_phase10 at head
python3 -m alembic upgrade 0011:0012 --sql     # valid PostgreSQL DDL

# Frontend
npm run typecheck                              # clean
npm run lint                                   # clean
npm run build                                  # compiled successfully
npx vitest run components/__tests__/ReplacementDecisionUI.test.tsx   # 9 passed
```

Note: `alembic upgrade head` against SQLite fails in migration `0001` on a pre-existing raw `JSONB`
column in `material_property_definitions`. The chain is PostgreSQL-targeted and predates Phase 10;
Phase-10 DDL was verified by offline PostgreSQL SQL generation instead.
