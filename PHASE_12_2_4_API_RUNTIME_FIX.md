# Phase 12.2.4 — TinkerLab API runtime fix

The dashboard rendered, then reported:

> The frontend is running, but the TinkerLab API service is not reachable.
> Request failed (500)

Two independent defects produced that screen. Either one alone is enough to break every
`/api/*` call. Both are fixed here.

---

## Root cause 1 — dependencies were never installed

`apps/web/pyproject.toml` declared the Python dependencies, and there was no `uv.lock`
and no `requirements.txt`.

Vercel's Python builder resolves dependencies with `uv`. When a project contains a
`pyproject.toml` **without** a lockfile, `uv` is selected and the build can complete
**having installed nothing** (`vercel/vercel#14041`). The function is then deployed with
no FastAPI, no SQLAlchemy, no psycopg. `api/index.py` raises `ModuleNotFoundError` at
import, and Vercel answers every request with a platform-level HTTP 500 whose body is an
HTML error page.

That HTML is why the message was so unhelpful. `lib/api.ts` tried to parse the body as
JSON, the parse threw, and the code fell back to its generic string. The `500` you saw
was **not** produced by TinkerLab — the application never ran.

**Fix**

- Added `apps/web/requirements.txt` (and a copy at `apps/web/api/requirements.txt` for
  the entrypoint-adjacent resolver).
- **Deleted `apps/web/pyproject.toml`.** Do not reintroduce it without a committed
  `uv.lock`. The dangerous shape is *pyproject declaring `[project].dependencies`, with no
  lockfile, inside the Vercel Root Directory*.
- `apps/web/.python-version` still pins Python 3.12.

`apps/api/pyproject.toml` is **kept and is safe**: it contains only `[tool.pytest]`,
`[tool.ruff]` and `[tool.mypy]` configuration, with no `[project]` table and no
dependency list, so `uv` never treats it as a project to install. It also sits outside the
Vercel Root Directory. Deleting it would break lint and type-check locally.

## Root cause 2 — bootstrap could never have succeeded on Neon

`alembic/env.py` set the migration URL from the raw `DATABASE_URL`:

```python
config.set_main_option("sqlalchemy.url", get_settings().database_url)
```

Neon and Vercel hand out `postgresql://…`. SQLAlchemy maps that scheme to the **psycopg2**
dialect, which TinkerLab does not ship — it ships psycopg 3. So `alembic upgrade head`
died with `ModuleNotFoundError: No module named 'psycopg2'`.

The application itself connected fine, because `app/db/session.py` normalizes the URL to
`postgresql+psycopg://`. Alembic did not. The result: even after the function booted, the
one-click workspace bootstrap would fail forever, leaving an empty database and a 500 on
every ORM endpoint.

**Fix** — `alembic/env.py` now applies the same `normalize_database_url()` the application
uses. Verified: with `postgresql://…` the migration now reaches the connection attempt
(psycopg 3) instead of failing on a missing driver.

---

## Also fixed

| Area | Change | Why |
|---|---|---|
| `api/index.py` | Guarded import; on failure the function still boots and returns a JSON **503** naming the exact `ImportError` | A boot failure used to be an invisible HTML 500 |
| `lib/api.ts` | Falls back to response **text** when the body is not JSON | This is what hid the real error for so long |
| `deployment.py` | `deployment_status()` catches `Exception`, not just `SQLAlchemyError` | `ArgumentError` / `ModuleNotFoundError` are not `SQLAlchemyError`, so they escaped as 500s |
| `deployment.py` | `safe_error()` reports the message, with credentials stripped | Previously reported only the class name — "CompileError" told nobody anything |
| `deployment.py` | Explicit hint when `DATABASE_URL` is unset | Default was silent SQLite, impossible on a read-only FS with a JSONB schema |
| `deployment.py` | `_run_migrations()` forces absolute `script_location` / `prepend_sys_path` | CWD on Vercel is `apps/web`, whose Next.js `app/` can shadow `python_backend/app` |
| `db/session.py` | `NullPool` when serverless | Frozen functions hold dead connections and exhaust Neon's connection cap |
| `vercel.json` | `"framework": "nextjs"`, `includeFiles: python_backend/**` | Removes preset ambiguity; guarantees the backend and migrations ship |
| `routes/deployment.py` | New `GET /api/deployment/diagnostics` | Secret-safe runtime report: driver, pool, which env vars are present |

Fixes were applied to the canonical `apps/api` **and** the generated
`apps/web/python_backend` mirror, so `scripts/sync-vercel-hybrid-backend.py` will not
revert them.

---

## Vercel project settings

| Setting | Value |
|---|---|
| Root Directory | `apps/web` |
| Framework Preset | Next.js (now also pinned in `vercel.json`) |
| Build Command | default |

### Environment variables

| Name | Value |
|---|---|
| `DATABASE_URL` | **Required.** Your Neon Postgres URL. Prefer the **pooled** host (contains `-pooler`) with `?sslmode=require` |
| `NEXT_PUBLIC_ORGANISATION_ID` | `0b5ec369-282c-57b5-9781-471f818a07c3` |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |
| `MATERIALS_PROJECT_API_KEY` | optional, server-side only |
| `EPA_COMPTOX_API_KEY` | optional, server-side only |

**Remove** `NEXT_PUBLIC_API_BASE_URL` and `API_BASE_URL` unless you deliberately run a
split deployment — a stale value sends the Phase 12 frontend to an older backend.

Either `postgresql://` or `postgresql+psycopg://` now works; both are normalized.

---

## Deploy and verify

1. Redeploy **without** the build cache.
2. Confirm the build log shows dependencies being installed from `requirements.txt` and a
   **Python** function alongside the Node functions.
3. Check, in order:

```
/api/health                  -> {"status":"ok","phase":"12.2.4"}
/api/deployment/diagnostics  -> driver "psycopg", url_configured true
/api/deployment/status       -> database_reachable true
```

4. Open the dashboard. It calls `POST /api/deployment/bootstrap` automatically, which runs
   the migrations to `0013_phase11`, creates the demo organisation, and installs the
   reference library. It is idempotent and advisory-locked.

### Reading failures now

Nothing fails silently any more.

- **HTTP 503, `API_BOOT_FAILED`** — the function booted but could not import the backend.
  Dependencies were not installed, or `python_backend/` was excluded from the bundle.
- **`database_reachable: false`** with a `hint` — a configuration problem; the hint names it.
- **`BOOTSTRAP_FAILED: <real message>`** — migrations ran and something specific went wrong.

If `bootstrap` times out on a cold Neon instance, hit it again; the advisory lock and the
idempotent seed make repeats safe.

---

## Verified before release

- `apps/api` test suite: **519 passed, 6 skipped**
- Frontend: `tsc --noEmit` clean, **86 vitest tests passed**, `next build` succeeds
- Full Alembic chain compiles for Postgres: 13 revisions, 100 tables, head `0013_phase11`
- Gateway reproduced end to end: boot, path normalization, status, diagnostics, bootstrap
