# Phase 6A — Hardening and real-execution readiness

## What changed in the environment

Three items previously recorded as UNVERIFIED became genuinely verifiable because the required
software was installed from the operating-system archive:

| Component | Status |
| --- | --- |
| PostgreSQL 16.14 | **Installed and running.** Migration and boot verification is now real, not static DDL inspection. |
| LAMMPS (7 Feb 2024) | **Installed and exercised end to end** through the full stack. |
| Quantum ESPRESSO 6.7 | **Installed but unusable** — see below. |

## Real defects found and fixed

**A test that could not fail correctly.** `test_provider_availability_is_honest` hard-coded
"solver absent" and broke the moment LAMMPS existed. It now asserts the actual invariant — reported
availability matches binary resolvability — so it catches an adapter lying in either direction.

**A false-positive solver probe.** The first Quantum ESPRESSO usability probe referenced a
nonexistent pseudopotential, so `pw.x` exited early on a file error and looked healthy. Rewritten to
use a real pseudopotential and the adapter's own argv invocation.

**A scientific-integrity bug in the Phase-6 method registry.** The MD method declared its output as
`total_energy` — but that value is a dimensionless reduced-unit Lennard-Jones energy, and it shared
a property key with first-principles DFT energy in rydberg. Silently comparing those is exactly the
category error the system exists to prevent. Split into `md_reduced_potential_energy`
(dimensionless) and `total_energy` (Ry).

**Registered artifacts were decorative.** A potential could be "required" while the solver template
used inline defaults, so a missing artifact changed nothing. Now LAMMPS `include`s the registered
potential file and the QE builder raises rather than emitting a `MISSING` placeholder — removing the
content fails the job, which is asserted by test.

## Artifact content store

`app/services/artifact_store.py` holds approved potentials, pseudopotentials and databases:

* content is **ingested server-side** from a path the operator chooses; no API payload supplies a
  source path and ingestion is unreachable from any HTTP route;
* content is addressed by its SHA-256 digest inside one controlled root, so a stored filename is
  never attacker-influenced;
* the digest is **re-verified before every use** — a tampered store file fails the job rather than
  silently changing the science;
* materialization into a job workdir goes through `safe_join`;
* nothing is downloaded, ever.

## LAMMPS: verified end to end

A real minimization runs through routing, snapshot, execution, parsing and convergence. The result
is the clearest demonstration of the core invariant available anywhere in the project:

* LAMMPS exits 0 and a genuine energy of −1.5 reduced units is parsed;
* `fmax` comes back at 1.16e-6 against a 1e-6 tolerance;
* scientific status is **unconverged** and **zero** property estimates are created.

A real solver, a real number, correctly refused. Loosening the tolerance to 1e-4 flips it to
converged and produces exactly one estimate of −1.5.

## Quantum ESPRESSO: installed, unusable, honestly reported

`pw.x` is present at `/usr/bin/pw.x` and reports version 6.7MaX, but aborts with a fortify
buffer-overflow (`__snprintf_chk`, SIGABRT/134) while parsing any real input. Attempted workarounds,
all unsuccessful: `-input file`, stdin redirection, `mpirun -np 1`, minimal environment, absolute vs
relative `pseudo_dir`/`outdir`.

This is a distribution build defect, not a TinkerLab adapter fault. The QE end-to-end tests are
**skipped with that exact reason recorded**, never reported as passing. Everything up to execution is
verified: routing, pseudopotential registration and materialization, input generation, and the
failure path — a QE workflow correctly records `failed` / `not_applicable` with no property estimate.

### Reproducing a real QE run elsewhere

```bash
# On a host with a working pw.x build:
export TINKERLAB_SYSTEM_PSEUDO_DIR=/path/to/pseudopotentials
python -m app.db.seed                       # ingests the Si pseudopotential, seeds the Si cell
pytest tests/test_phase6a_real_solvers.py -v # QE tests run instead of skipping
```

## Real PostgreSQL verification

| Check | Result |
| --- | --- |
| empty → head | 63 tables, 290+ indexes, 148 foreign keys |
| empty → 0005 → 0006 (upgrade path) | 43 → 57 tables |
| 0006 → 0005 (rollback) | back to 43, zero Phase-6 tables left behind |
| 0007 → 0006 (rollback) | zero Phase-7 tables left behind |
| model ↔ migration parity | 0 table mismatches, 0 column mismatches |
| `alembic upgrade head && seed && uvicorn` | boots, `/health` returns ok, seed is idempotent |
| live API smoke test | providers, integrity, silicon routing, cross-tenant 404 |

## Docker

`docker` is not installed in this environment, so `docker compose up` is **NOT_RUN**. The exact
command chain from `docker-compose.yml` (`alembic upgrade head && python -m app.db.seed && uvicorn`)
was executed directly against the real PostgreSQL server instead, and passed.

## Security audit

`tests/test_phase6a_security.py` (40 tests) attacks the runtime: closed executable allowlist,
argv-not-shell, bounded timeouts, path traversal and symlink escape, oversized inputs, output
collection outside the workdir, cleanup outside the controlled root, environment allowlist, artifact
digest tampering, non-regular-file ingestion, a field-by-field check that no API field accepts a
command or path, cross-tenant 404s, pagination bounds and payload size limits.
