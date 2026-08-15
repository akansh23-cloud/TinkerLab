"""TinkerLab hybrid Vercel API gateway.

The Vercel project root remains ``apps/web`` so Next.js and Python ship together.
``apps/web/vercel.json`` rewrites public ``/api/*`` requests to this Python
function and preserves the requested sub-path in ``__tinker_path``. This gateway
removes the transport-only parameter, normalizes the ASGI path, and delegates to
the canonical FastAPI application mirrored under ``python_backend``.

Phase 12.2.4 — fail-soft boot
-----------------------------
Previously an import failure here (a missing dependency, a backend file left out
of the function bundle) crashed the module. Vercel then answered every ``/api/*``
request with a platform-level HTTP 500 whose body is HTML, so the browser could
only report the generic "Request failed (500)" and the real cause never reached
anyone.

Now the import is guarded. If the canonical app cannot be loaded, this module
still exposes a valid ASGI app that returns a structured JSON 503 naming the
exact failure. The deployment is still broken, but it now says why.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "python_backend"

# Insert at the front so ``app`` always resolves to python_backend/app and never to
# the sibling Next.js ``apps/web/app`` directory, which is a valid namespace package
# candidate on Python 3.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BOOT_ERROR: dict[str, object] | None = None
core_app = None

try:
    from app.main import app as core_app  # noqa: E402
except Exception as exc:  # pragma: no cover - only reachable on a broken deployment
    BOOT_ERROR = {
        "code": "API_BOOT_FAILED",
        "message": f"{type(exc).__name__}: {exc}",
        "backend_root": str(BACKEND_ROOT),
        "backend_root_exists": BACKEND_ROOT.is_dir(),
        "python_version": sys.version.split()[0],
        "traceback": traceback.format_exc().splitlines()[-12:],
    }

app = FastAPI(
    title="TinkerLab Hybrid API Gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _normalize(scope: dict) -> None:
    """Strip the transport-only routing parameter and restore the canonical ASGI path."""
    query_pairs = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)

    routed_path = None
    forwarded_query: list[tuple[str, str]] = []
    for key, value in query_pairs:
        if key == "__tinker_path" and routed_path is None:
            routed_path = value
        else:
            forwarded_query.append((key, value))

    if routed_path is not None:
        normalized = "/" + routed_path.lstrip("/") if routed_path else "/"
    else:
        incoming = scope.get("path", "/")
        normalized = incoming[4:] if incoming.startswith("/api/") else ("/" if incoming == "/api" else incoming)
        if not normalized.startswith("/"):
            normalized = "/" + normalized

    scope["path"] = normalized
    scope["raw_path"] = normalized.encode()
    scope["query_string"] = urlencode(forwarded_query, doseq=True).encode()


@app.middleware("http")
async def normalize_vercel_api_path(request: Request, call_next):
    _normalize(request.scope)
    return await call_next(request)


if BOOT_ERROR is None and core_app is not None:
    # Mount last so middleware path normalization runs before canonical route matching.
    app.mount("/", core_app)
else:
    @app.get("/boot-error")
    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def boot_error(full_path: str = "") -> JSONResponse:
        """Answer every route with the real reason the API could not start."""
        detail = dict(BOOT_ERROR or {})
        detail["hint"] = (
            "The Python function started but could not import the TinkerLab backend. "
            "Most often this means dependencies were not installed (check that "
            "apps/web/requirements.txt exists and that no pyproject.toml without a "
            "uv.lock shadows it), or that python_backend/ was excluded from the "
            "function bundle."
        )
        detail["database_url_configured"] = bool(os.environ.get("DATABASE_URL"))
        return JSONResponse(status_code=503, content={"error": detail})
