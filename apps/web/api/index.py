"""TinkerLab hybrid Vercel entrypoint.

Vercel treats api/index.py as the catch-all Python function for /api/* while
Next.js continues to serve the rest of apps/web.  The canonical API source is
mirrored into python_backend at release packaging time so the current Vercel
Root Directory (apps/web) can deploy both runtimes without Vercel Services.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "python_backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app as core_app  # noqa: E402

app = FastAPI(
    title="TinkerLab Hybrid API Router",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.mount("/api", core_app)
