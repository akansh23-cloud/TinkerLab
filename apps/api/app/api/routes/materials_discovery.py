from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api.deps import scope_organisation
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import Candidate, ReplacementProject, SourceRecord
from app.services.ingest import ConnectorError, LicenceError, ingest
from app.services.ingest.materials_project_v2 import MaterialsProjectConnector
from app.services.ingest.persist import PersistError
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


class AdoptMaterialsProjectCandidateRequest(BaseModel):
    material_id: str = Field(min_length=3, max_length=80, pattern=r"^mp-[A-Za-z0-9-]+$")
    project_id: str = Field(min_length=1, max_length=80)


def _organisation(value: str | None) -> str:
    if not value:
        raise HTTPException(400, "X-Organisation-ID is required to adopt a candidate")
    return value


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


@router.post("/adopt", status_code=201)
def adopt_materials_project_candidate(
    payload: AdoptMaterialsProjectCandidateRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Re-fetch, persist, and attach one reviewed MP record to a replacement project atomically.

    The client supplies only the upstream Materials Project identifier and target project. Property
    values from the discovery preview are never trusted on write: the server re-fetches the record,
    persists its snapshot/source/evidence chain, and records the material as a proposed candidate.
    Computed database values remain computational evidence and are never promoted to measurements.
    """
    org = _organisation(organisation_id)
    project = db.get(ReplacementProject, payload.project_id)
    if project is None or project.organisation_id != org:
        raise HTTPException(404, "Replacement project not found")
    if not settings.materials_project_api_key:
        raise HTTPException(503, "Materials Project API key is not configured on the server")

    connector = MaterialsProjectConnector(
        api_key=settings.materials_project_api_key,
        base_url=settings.materials_project_api_base_url,
    )
    try:
        ingestion = ingest(
            db,
            connector,
            dataset_key="materials_project_candidate_adoption",
            organisation_id=org,
            commercial_context=True,
            material_ids=[payload.material_id],
            max_records=1,
        )
        if ingestion.get("record_count") != 1 or not ingestion.get("results"):
            db.rollback()
            raise HTTPException(404, "Materials Project material was not found")

        persisted = ingestion["results"][0]
        material_id = persisted.get("material_id")
        if not material_id and persisted.get("source_record_id"):
            source_record = db.get(SourceRecord, persisted["source_record_id"])
            material_id = (source_record.metadata_json or {}).get("resolved_material_id") if source_record else None
        if not material_id:
            db.rollback()
            raise HTTPException(409, "Ingested source record did not resolve to a TinkerLab material")

        candidate = (
            db.query(Candidate)
            .filter(Candidate.project_id == project.id, Candidate.material_id == material_id)
            .one_or_none()
        )
        attached = candidate is None
        if candidate is None:
            candidate = Candidate(
                project_id=project.id,
                candidate_kind="known_material",
                material_id=material_id,
                hypothesis_id=None,
                candidate_source="retrieved_future",
                status="proposed",
                notes=(
                    f"Adopted from Materials Project discovery ({payload.material_id}). "
                    "Imported values are computed-database evidence, not experimental measurements."
                ),
            )
            db.add(candidate)
            db.flush()

        db.commit()
        return {
            "project_id": project.id,
            "candidate_id": candidate.id,
            "material_id": material_id,
            "source_material_id": payload.material_id,
            "attached": attached,
            "ingestion_status": persisted.get("status"),
            "dataset_snapshot_id": ingestion.get("dataset_snapshot_id"),
            "source_record_id": persisted.get("source_record_id"),
            "evidence_id": persisted.get("evidence_id"),
            "observations_written": persisted.get("observations", 0),
            "source_data_kind": "computed_database",
            "candidate_status": "proposed",
            "warning": (
                "Materials Project values are computational database evidence. Candidate adoption "
                "does not constitute experimental validation or acceptance."
            ),
        }
    except HTTPException:
        raise
    except LicenceError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except (ConnectorError, PersistError, ValueError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
