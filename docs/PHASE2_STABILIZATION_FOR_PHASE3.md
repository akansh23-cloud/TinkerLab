# Phase-2 Stabilization for Phase 3

## Result

The Phase-2 codebase was used as-is as the Phase-3 base. The original **34/34 backend tests** were rerun before Phase-3 implementation and passed in the available sandbox.

## Checks completed here

- Existing Phase-1/2 backend regression suite: PASS before Phase-3 changes.
- Phase-3 full backend suite after implementation: **56/56 PASS**.
- Python compilation: PASS.
- PostgreSQL-dialect Alembic static generation through `0003`: PASS.
- TypeScript/TSX syntax transpilation using installed TypeScript: PASS.
- Phase-2 privacy regression cases remain covered and Phase-3 privacy tests were added.

## Stabilization/security corrections made while extending Phase 3

- Phase-3 standalone run/hypothesis/substitution-rule resources now require explicit organisation scope.
- Project comparison may include hypotheses only when `X-Organisation-ID` matches the project organisation; the older known-material comparison remains backward compatible.
- Existing project `candidates` relationship remains known-material-only for Phase-1/2 response compatibility; an `all_candidates` relationship and Phase-3 Candidate Lab provide mixed known/hypothesis access.
- No historical `0001` or `0002` migration was edited.

## Environment-dependent checks unavailable here

The sandbox does not provide:

- Docker daemon / Docker Compose execution;
- a live PostgreSQL server;
- Pint installation;
- Ruff;
- Mypy;
- frontend `node_modules` / package resolution.

Therefore the following remain **UNVERIFIED**, not PASS:

- clean Docker Compose boot;
- real PostgreSQL `0001 -> 0002 -> 0003` execution and restart persistence;
- disposable real-PostgreSQL downgrade test;
- Pint-backed runtime unit checks;
- Ruff / Mypy;
- Vitest / full `tsc --noEmit` / ESLint / Next production build;
- browser/responsive/console smoke tests.

These checks are mandatory at the start of Phase 4 on a normal dependency-enabled machine.
