from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import Organisation, User

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "tinkerlab-api", "phase": "12.2"}


@router.get("/demo-context")
def demo_context(db: Session = Depends(get_db)) -> dict[str, str]:
    org = db.query(Organisation).order_by(Organisation.created_at).first()
    user = db.query(User).order_by(User.created_at).first()
    if not org or not user:
        raise HTTPException(404, "Demo context is unavailable; run the seed command first")
    return {"organisation_id": org.id, "user_id": user.id, "display_name": user.display_name}
