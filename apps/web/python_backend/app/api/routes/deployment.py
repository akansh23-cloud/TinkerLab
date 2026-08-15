from fastapi import APIRouter, HTTPException

from app.services.deployment import bootstrap_workspace, deployment_status

router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.get("/status")
def status():
    return deployment_status()


@router.post("/bootstrap")
def bootstrap():
    try:
        return bootstrap_workspace()
    except Exception as exc:
        # Keep the response useful without leaking connection strings or provider secrets.
        raise HTTPException(
            status_code=500,
            detail={
                "code": "BOOTSTRAP_FAILED",
                "message": f"Workspace bootstrap failed: {exc.__class__.__name__}",
            },
        ) from exc
