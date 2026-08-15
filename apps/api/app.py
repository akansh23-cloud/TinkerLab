"""Vercel entrypoint for the TinkerLab FastAPI application.

The production application remains defined in app.main; this module exists only so
Vercel's FastAPI runtime can discover the ASGI app when apps/api is configured as
the project Root Directory.
"""
from app.main import app


@app.get("/", include_in_schema=False)
def deployment_root() -> dict[str, str]:
    return {
        "service": "TinkerLab API",
        "version": "0.12.2.1",
        "health": "/health",
        "docs": "/docs",
    }
