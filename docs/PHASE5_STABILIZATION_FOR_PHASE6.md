# Phase 5 stabilization for Phase 6

Phase 6 was not started until the Phase-5 codebase passed a full gate. This records what was found,
what was changed and what remains unverified in this environment.

## Gate results (final)

| Gate | Before | After |
| --- | --- | --- |
| `pytest` (apps/api) | 108 passed | 136 passed (108 Phase 1-5 + 28 Phase 6) |
| `ruff check .` | 2,078 errors | All checks passed |
| `mypy app` | 97 errors | Success (54 source files) |
| `vitest` (apps/web) | 11 of 13 failing | 18 passed (13 existing + 5 Phase 6) |
| `tsc --noEmit` | clean | clean |
| `eslint .` | no config present | 0 errors, 0 warnings |
| `next build` | compiles | compiles |
| Seed idempotency | verified | verified (2x seed, unchanged counts) |

## Real defects fixed (not suppressed)

* Unguarded `db.get()` results in ingestion, identity and seed paths: added a `_require[T]` helper so
  a missing row raises immediately instead of failing later as `NoneType` attribute access.
* `routes/prediction.py` passed a Python `bool` into `or_()`, silently producing a constant filter.
* `services/generation.py` `_grid(None, None)` raised `TypeError` at runtime for unbounded numeric ranges.
* Loop-variable shadowing in substitution-rule processing (`rule` reused for two different entities).
* Frozen-dataclass/Protocol variance error in `providers.py`, fixed by declaring `@property` on the Protocol.
* `zip()` calls without `strict=`, which silently truncated on length mismatch.
* Frontend `vitest.config.ts` lacked the automatic JSX transform, so 11 of 13 tests failed with
  "React is not defined". The tests were never actually running before this phase.

## Suppressions and their rationale

`apps/api/pyproject.toml` ignores exactly four rules, each documented inline: `E501` (line length —
the codebase uses long descriptive scientific strings), `E701`/`E702` (compound statements, used only
in dense ORM construction blocks), and `B008` (FastAPI `Depends()` in defaults is the framework idiom).
`tests/conftest.py` carries a per-file `E402` ignore because environment setup must precede app import.
No rule was disabled to hide a real defect.

## UNVERIFIED in this environment

These are honestly recorded as unverified rather than claimed as passing:

* **Docker / docker compose** — no `docker` binary is available in the build sandbox. The compose
  stack was not started, and no live PostgreSQL server was reached.
* **Live migration against PostgreSQL** — migrations were verified by static DDL generation only
  (`alembic upgrade head --sql` against a PostgreSQL URL: 1,881 lines, 58 tables, 253 indexes).
  Migrations use `postgresql.JSONB` directly and therefore cannot run on SQLite; the test suite uses
  `Base.metadata.create_all` with `JSON.with_variant(JSONB, "postgresql")` instead.
* **LAMMPS and Quantum ESPRESSO integration** — neither binary is installed on this host. Both
  adapters correctly report `executable_not_installed`. Their input builders, parsers and convergence
  evaluators are unit-tested; end-to-end execution against a real solver is **UNVERIFIED**, never PASS.
