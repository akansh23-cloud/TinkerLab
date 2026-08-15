from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.services.ingest import ConnectorError
from app.services.ingest.materials_project_v2 import MaterialsProjectConnector
from app.services.materials_discovery import preview_materials_project_candidates

router = APIRouter(prefix="/external-data/materials-project", tags=["external-data", "discovery"])
settings = get_settings()


PropertyKey = Literal[
    "band_gap",
    "density",
    "energy_above_hull",
    "formation_energy_per_atom",
    "bulk_modulus",
    "shear_modulus",
    "magnetic_moment",
]


class ScreeningConstraint(BaseModel):
    property: PropertyKey
    minimum: float | None = None
    maximum: float | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "ScreeningConstraint":
        if self.minimum is None and self.maximum is None:
            raise ValueError("constraint requires minimum and/or maximum")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("constraint minimum cannot exceed maximum")
        return self


class MaterialsDiscoveryRequest(BaseModel):
    constraints: list[ScreeningConstraint] = Field(default_factory=list, max_length=20)
    formula: str | None = Field(default=None, min_length=1, max_length=120)
    chemsys: str | None = Field(default=None, min_length=1, max_length=180)
    elements: list[str] | None = Field(default=None, max_length=30)
    exclude_elements: list[str] | None = Field(default=None, max_length=30)
    is_stable: bool | None = None
    theoretical: bool | None = None
    stable_preferred: bool = True
    max_candidates: int = Field(default=25, ge=1, le=100)
    search_pool: int = Field(default=100, ge=1, le=500)

    @model_validator(mode="after")
    def validate_request(self) -> "MaterialsDiscoveryRequest":
        seen: set[str] = set()
        for constraint in self.constraints:
            if constraint.property in seen:
                raise ValueError(f"duplicate constraint for {constraint.property}")
            seen.add(constraint.property)
        if self.search_pool < self.max_candidates:
            raise ValueError("search_pool must be greater than or equal to max_candidates")
        for collection_name in ("elements", "exclude_elements"):
            collection = getattr(self, collection_name)
            if collection and any(not value.strip() or len(value.strip()) > 3 for value in collection):
                raise ValueError(f"{collection_name} must contain element symbols")
        return self


@router.post("/discover")
def discover_materials(payload: MaterialsDiscoveryRequest):
    """Screen live Materials Project candidates without persisting any result.

    This endpoint is deliberately read-only. Its ranking is deterministic and transparent,
    and it never upgrades computed database values into experimental evidence.
    """
    if not settings.materials_project_api_key:
        raise HTTPException(503, "Materials Project API key is not configured on the server")

    connector = MaterialsProjectConnector(
        api_key=settings.materials_project_api_key,
        base_url=settings.materials_project_api_base_url,
    )
    filters = {
        "formula": payload.formula,
        "chemsys": payload.chemsys,
        "elements": payload.elements,
        "exclude_elements": payload.exclude_elements,
        "is_stable": payload.is_stable,
        "theoretical": payload.theoretical,
    }
    try:
        return preview_materials_project_candidates(
            connector,
            constraints=[constraint.model_dump() for constraint in payload.constraints],
            search_filters=filters,
            max_candidates=payload.max_candidates,
            search_pool=payload.search_pool,
            stable_preferred=payload.stable_preferred,
        )
    except (ConnectorError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
