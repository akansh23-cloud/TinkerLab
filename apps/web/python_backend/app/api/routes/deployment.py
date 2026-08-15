import os
import sys

from fastapi import APIRouter, HTTPException

from app.db.session import database_url_is_configured, engine, is_serverless
from app.services.deployment import (
    EXPECTED_ALEMBIC_HEAD,
    bootstrap_workspace,
    deployment_status,
    safe_error,
)

router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.get("/status")
def status():
    return deployment_status()


@router.get("/diagnostics")
def diagnostics():
    """Answer 'why is the API broken' without ever revealing a secret.

    Only booleans and non-sensitive runtime facts are returned. No environment
    variable value is echoed, and the connection string is never included.
    """
    return {
        "service": "tinkerlab-api",
        "phase": "12.2.4",
        "python_version": sys.version.split()[0],
        "serverless": is_serverless(),
        "expected_alembic_head": EXPECTED_ALEMBIC_HEAD,
        "database": {
            "url_configured": database_url_is_configured(),
            "dialect": engine.dialect.name,
            "driver": engine.dialect.driver,
            "pool_class": type(engine.pool).__name__,
        },
        "environment_present": {
            key: bool(os.environ.get(key))
            for key in (
                "DATABASE_URL",
                "NEXT_PUBLIC_ORGANISATION_ID",
                "MATERIALS_PROJECT_API_KEY",
                "EPA_COMPTOX_API_KEY",
                "ENVIRONMENT",
            )
        },
    }


@router.post("/bootstrap")
def bootstrap():
    try:
        return bootstrap_workspace()
    except Exception as exc:
        # Report what actually went wrong. safe_error strips anything resembling
        # credentials from the driver message, so the browser gets a diagnosable
        # string without ever seeing the connection string.
        raise HTTPException(
            status_code=500,
            detail={
                "code": "BOOTSTRAP_FAILED",
                "message": f"Workspace bootstrap failed. {safe_error(exc)}",
            },
        ) from exc
