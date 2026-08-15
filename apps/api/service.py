"""Single-project Vercel Services entrypoint.

Vercel routes /api/* to this Python service while preserving the public request
path.  Mount the existing FastAPI application at /api so the web application can
use a same-origin API without a public backend URL or CORS dependency.
"""
from fastapi import FastAPI

from app.main import app as core_app

app = FastAPI(title="TinkerLab service router", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", core_app)
