import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("tinkerlab")

app = FastAPI(
    title="TinkerLab Material Replacement OS",
    version=settings.api_version,
    description="TinkerLab Material Replacement OS through Phase 12.2: evidence, bounded candidates, prediction, simulation, industrial viability, state-aware reasoning, physical validation, deterministic replacement decisions, and licence-aware external scientific data ingestion.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Organisation-ID"],
)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    logger.info("request_complete", extra={"request_id": request_id})
    return response

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID")
    logger.exception("unhandled_exception", extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "Internal server error", "request_id": request_id}},
    )

app.include_router(api_router)
