# Phase-4 Stabilization Gate for Phase 5

## Baseline regression

Before Phase-5 implementation, the supplied Phase-4 backend suite was executed unchanged: **82/82 tests passed**.

Verified in this artifact sandbox:

- Python source/Alembic compilation: PASS.
- Historical Phase-1/2/3/4 regression suite: PASS before Phase-5 changes.
- Prediction/observation separation: PASS through existing regression tests.
- Inapplicable/OOD predictions remain numberless: PASS.
- Known evidence remains preferred by default: PASS.
- Prediction comparison fallback remains explicit: PASS.
- Interval-crossing hard constraints remain `UNKNOWN`: PASS.
- demo-model warning remains present: PASS.
- arbitrary pickle/joblib execution remains rejected: PASS.
- private prediction resources remain scope-tested: PASS.

## Environment-dependent gate

The artifact sandbox does not provide Docker, a live PostgreSQL server, Pint, Ruff, Mypy or installed frontend dependencies. Therefore these mandatory clean-machine checks remain **UNVERIFIED**, not PASS:

- `docker compose up --build`;
- live PostgreSQL `0001 -> 0005` execution and restart persistence;
- live upgrade/downgrade exercises;
- Pint-backed production unit path;
- `ruff check .`;
- `mypy app`;
- dependency-resolved `npm test`;
- full `npm run typecheck`;
- `npm run lint`;
- `npm run build`;
- browser/console/responsive smoke test.

The PostgreSQL dialect migration chain was nevertheless generated statically with Alembic. During that check Phase 5 exposed a PostgreSQL-specific identifier-length defect in a new index name; `0005` was corrected to use explicit short index names. Historical migrations `0001`–`0004` were not edited.

## Stabilization fix

The browser development scoping header `X-Organisation-ID` is now explicitly allowed by CORS. This does not turn the header into production authentication; it remains a development-only tenant-scoping seam.

Phase 6 must begin by running every remaining UNVERIFIED gate on a normal dependency-enabled machine before adding physics execution.
