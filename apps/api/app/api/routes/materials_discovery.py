from __future__ import annotations

from typing import Any, Literal

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
from app.services.units import UnitError, convert

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

# Units expected by the Materials Project summary search API and by the normalized
# observation contract. Mission constraints are converted into these units before any
# upstream query is made; unsupported conversions remain visible instead of being guessed.
_MISSION_PROPERTY_UNITS: dict[str, str] = {
    "band_gap": "eV",
    "density": "g/cm^3",
    "energy_above_hull": "eV/atom",
    "formation_energy_per_atom": "eV/atom",
    "bulk_modulus": "GPa",
    "shear_modulus": "GPa",
    "magnetic_moment": "bohr_magneton",
}


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


class MissionMaterialsDiscoveryRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=80)
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
    def validate_request(self) -> "MissionMaterialsDiscoveryRequest":
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


def _organisation(value: str | None, purpose: str = "access this mission") -> str:
    if not value:
        raise HTTPException(400, f"X-Organisation-ID is required to {purpose}")
    return value


def _unsupported_constraint(constraint: Any, reason: str, detail: str | None = None) -> dict[str, Any]:
    return {
        "constraint_id": constraint.id,
        "property_key": constraint.property_key,
        "comparator": constraint.comparator,
        "target_value": constraint.target_value,
        "target_value_upper": constraint.target_value_upper,
        "target_unit": constraint.target_unit,
        "hard_or_soft": constraint.hard_or_soft,
        "weight": constraint.weight,
        "severity": constraint.severity,
        "reason": reason,
        "detail": detail,
    }


def _mission_constraints(
    project: ReplacementProject,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Translate hard gates and soft targets without mixing their decision semantics.

    Hard requirements become upstream Materials Project filters only when the exact inclusive
    range semantics can be preserved. Soft requirements never exclude candidates upstream; when
    they can be evaluated from normalized MP properties they become transparent, user-weighted
    ranking preferences. Anything else remains an explicit evidence gap.
    """
    merged_hard: dict[str, dict[str, Any]] = {}
    preferences: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for constraint in project.constraints:
        key = str(constraint.property_key)
        comparator = str(constraint.comparator)
        hard_or_soft = str(constraint.hard_or_soft)
        if str(constraint.constraint_type) != "property":
            unsupported.append(_unsupported_constraint(constraint, "non_property_constraint"))
            continue
        target_unit = _MISSION_PROPERTY_UNITS.get(key)
        if target_unit is None:
            unsupported.append(_unsupported_constraint(constraint, "property_not_searchable_in_materials_project"))
            continue
        if comparator not in {">=", "<=", "between"}:
            unsupported.append(
                _unsupported_constraint(
                    constraint,
                    "comparator_not_losslessly_searchable",
                    "Materials Project range semantics are inclusive; strict/equality/boolean mission semantics are not approximated.",
                )
            )
            continue
        if constraint.target_value is None or not constraint.target_unit:
            unsupported.append(_unsupported_constraint(constraint, "missing_numeric_target_or_unit"))
            continue

        try:
            primary = convert(float(constraint.target_value), str(constraint.target_unit), target_unit)
            upper = (
                convert(float(constraint.target_value_upper), str(constraint.target_unit), target_unit)
                if comparator == "between" and constraint.target_value_upper is not None
                else None
            )
        except (UnitError, TypeError, ValueError) as exc:
            unsupported.append(_unsupported_constraint(constraint, "unit_not_convertible", str(exc)))
            continue

        if comparator == "between" and upper is None:
            unsupported.append(_unsupported_constraint(constraint, "missing_upper_bound"))
            continue

        minimum = primary if comparator in {">=", "between"} else None
        maximum = primary if comparator == "<=" else upper if comparator == "between" else None

        if hard_or_soft == "soft":
            preferences.append(
                {
                    "constraint_id": constraint.id,
                    "property": key,
                    "minimum": minimum,
                    "maximum": maximum,
                    "unit": target_unit,
                    "weight": max(0.0, float(constraint.weight or 1.0)),
                    "severity": int(constraint.severity or 1),
                    "description": constraint.description,
                }
            )
            continue
        if hard_or_soft != "hard":
            unsupported.append(_unsupported_constraint(constraint, "unknown_hard_or_soft_semantics"))
            continue

        row = merged_hard.setdefault(
            key,
            {
                "property": key,
                "minimum": None,
                "maximum": None,
                "unit": target_unit,
                "source_constraint_ids": [],
            },
        )
        row["source_constraint_ids"].append(constraint.id)
        if minimum is not None:
            row["minimum"] = minimum if row["minimum"] is None else max(row["minimum"], minimum)
        if maximum is not None:
            row["maximum"] = maximum if row["maximum"] is None else min(row["maximum"], maximum)

    for row in merged_hard.values():
        if row["minimum"] is not None and row["maximum"] is not None and row["minimum"] > row["maximum"]:
            raise HTTPException(
                422,
                f"Mission has contradictory hard constraints for {row['property']}: minimum exceeds maximum",
            )

    return list(merged_hard.values()), preferences, unsupported


def _connector() -> MaterialsProjectConnector:
    if not settings.materials_project_api_key:
        raise HTTPException(503, "Materials Project API key is not configured on the server")
    return MaterialsProjectConnector(
        api_key=settings.materials_project_api_key,
        base_url=settings.materials_project_api_base_url,
    )


def _discovery_filters(payload: MaterialsDiscoveryRequest | MissionMaterialsDiscoveryRequest) -> dict[str, Any]:
    return {
        "formula": payload.formula,
        "chemsys": payload.chemsys,
        "elements": payload.elements,
        "exclude_elements": payload.exclude_elements,
        "is_stable": payload.is_stable,
        "theoretical": payload.theoretical,
    }


@router.post("/discover")
def discover_materials(payload: MaterialsDiscoveryRequest):
    """Screen live Materials Project candidates without persisting any result."""
    try:
        return preview_materials_project_candidates(
            _connector(),
            constraints=[constraint.model_dump() for constraint in payload.constraints],
            search_filters=_discovery_filters(payload),
            max_candidates=payload.max_candidates,
            search_pool=payload.search_pool,
            stable_preferred=payload.stable_preferred,
        )
    except (ConnectorError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/discover-mission")
def discover_for_replacement_mission(
    payload: MissionMaterialsDiscoveryRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Derive a read-only Materials Project screen directly from a replacement mission."""
    org = _organisation(organisation_id, "screen candidates for a mission")
    project = db.get(ReplacementProject, payload.project_id)
    if project is None or project.organisation_id != org:
        raise HTTPException(404, "Replacement project not found")

    translated, preferences, unsupported = _mission_constraints(project)
    screening = [
        {"property": row["property"], "minimum": row["minimum"], "maximum": row["maximum"]}
        for row in translated
    ]
    filters = _discovery_filters(payload)
    if not screening and not any(value for value in filters.values() if value is not None):
        raise HTTPException(
            422,
            "This mission has no hard constraints or chemistry filters that can bound a Materials Project search. Soft targets alone cannot define a reproducible upstream search pool.",
        )

    try:
        result = preview_materials_project_candidates(
            _connector(),
            constraints=screening,
            preferences=preferences,
            search_filters=filters,
            max_candidates=payload.max_candidates,
            search_pool=payload.search_pool,
            stable_preferred=payload.stable_preferred,
        )
    except (ConnectorError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

    hard_constraints = [constraint for constraint in project.constraints if str(constraint.hard_or_soft) == "hard"]
    soft_constraints = [constraint for constraint in project.constraints if str(constraint.hard_or_soft) == "soft"]
    represented_ids = {source_id for row in translated for source_id in row["source_constraint_ids"]}
    preference_ids = {str(row["constraint_id"]) for row in preferences}
    result["mission_context"] = {
        "project_id": project.id,
        "project_name": project.name,
        "baseline_material_id": project.baseline_material_id,
        "baseline_material_name": project.baseline_material.display_name if project.baseline_material else None,
        "hard_constraint_count": len(hard_constraints),
        "hard_constraints_represented": len(represented_ids),
        "hard_constraint_coverage": round(len(represented_ids) / len(hard_constraints), 4) if hard_constraints else 0.0,
        "soft_constraint_count": len(soft_constraints),
        "soft_preferences_represented": len(preference_ids),
        "soft_preference_coverage": round(len(preference_ids) / len(soft_constraints), 4) if soft_constraints else 0.0,
        "translated_constraints": translated,
        "ranking_preferences": preferences,
        "unsupported_constraints": unsupported,
        "search_semantics": (
            "Losslessly translatable hard numeric requirements define upstream eligibility. "
            "Losslessly evaluable soft requirements are applied only after hard-gate state as mission-authored weighted ranking preferences. "
            "Unsupported, strict, equality, boolean, and non-property requirements remain explicit evidence gaps."
        ),
    }
    return result


@router.post("/adopt", status_code=201)
def adopt_materials_project_candidate(
    payload: AdoptMaterialsProjectCandidateRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Re-fetch, persist, and attach one reviewed MP record to a replacement project atomically."""
    org = _organisation(organisation_id, "adopt a candidate")
    project = db.get(ReplacementProject, payload.project_id)
    if project is None or project.organisation_id != org:
        raise HTTPException(404, "Replacement project not found")
    connector = _connector()

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
