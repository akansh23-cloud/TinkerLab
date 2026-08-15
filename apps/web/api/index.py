"""TinkerLab hybrid Vercel API gateway.

The Vercel project root remains ``apps/web`` so Next.js and Python ship together.
``apps/web/vercel.json`` rewrites public ``/api/*`` requests to this Python
function and preserves the requested sub-path in ``__tinker_path``. This gateway
removes the transport-only parameter, normalizes the ASGI path, and delegates to
the canonical FastAPI application mirrored under ``python_backend``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from fastapi import FastAPI, Request

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "python_backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app as core_app  # noqa: E402

app = FastAPI(
    title="TinkerLab Hybrid API Gateway",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def normalize_vercel_api_path(request: Request, call_next):
    scope = request.scope
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
    return await call_next(request)


# Mount last so middleware path normalization runs before canonical route matching.
app.mount("/", core_app)
