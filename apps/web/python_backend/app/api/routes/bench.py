"""Phase 12 routes — the intake bench.

Everything here is a composition of existing, already-tested services. No new evaluator, no new
scientific claim, and nothing in this module participates in a verdict: it creates inputs and
reports on their presence. That separation is deliberate and worth preserving — usability work is
exactly where a decision engine's guarantees tend to get quietly eroded.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import Material, Organisation, ReplacementProject, User
from app.schemas.bench import (
    AppendResponse,
    IntakeResponse,
    LibraryInstallRequest,
    MaterialIntakeRequest,
    PropertyAppendRequest,
    StudyCreateRequest,
)
from app.services.bench.catalog import DOMAINS, PROPERTY_CATALOGUE, resolve_property_key
from app.services.bench.decision_chart import decision_chart
from app.services.bench.derive import derivation_preview, derive_search_space
from app.services.bench.intake import (
    DATA_GRADES,
    IntakeError,
    PropertyEntry,
    add_property_data,
    intake_material,
)
from app.services.bench.library import STARTER_LIBRARY
from app.services.bench.presets import APPLICATION_PRESETS, REPLACEMENT_DRIVERS
from app.services.bench.property_space import axis_options, index_value, indices_for, property_space
from app.services.bench.readiness import platform_readiness, project_readiness
from app.services.bench.studies import (
    create_study,
    derive_requirements_from_baseline,
    install_reference_library,
)

router = APIRouter(tags=["bench"])


def _entries(payload_properties) -> list[PropertyEntry]:
    return [
        PropertyEntry(
            property_key=p.property_key, value=p.value, boolean_value=p.boolean_value, unit=p.unit,
            temperature_value=p.temperature_value, temperature_unit=p.temperature_unit,
            method=p.method, note=p.note, uncertainty=p.uncertainty,
        )
        for p in payload_properties
    ]




def _scoped_project(db: Session, project_id: str, organisation_id: str | None) -> ReplacementProject:
    # Project endpoints are tenant-private.  An absent organisation scope is treated exactly like
    # a wrong scope so project ids cannot be used as bearer secrets.
    if not organisation_id:
        raise HTTPException(404, "Project not found")
    project = (
        db.query(ReplacementProject)
        .filter(ReplacementProject.id == project_id, ReplacementProject.organisation_id == organisation_id)
        .one_or_none()
    )
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


def _request_owner(payload_organisation_id: str | None, organisation_id: str | None) -> str | None:
    if payload_organisation_id and organisation_id and payload_organisation_id != organisation_id:
        raise HTTPException(403, "Payload organisation does not match X-Organisation-ID")
    return payload_organisation_id or organisation_id

def _visible_material(db: Session, material_id: str, organisation_id: str | None) -> Material:
    query = db.query(Material).filter(Material.id == material_id)
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public",
                                 Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    material = query.one_or_none()
    if material is None:
        raise HTTPException(404, "Material not found")
    return material


# ------------------------------------------------------------------------------------ catalogue

@router.get("/bench/property-catalogue")
def property_catalogue(
    domain: str | None = Query(default=None),
    family: str | None = Query(default=None),
):
    """The engineering property vocabulary, grouped for a form rather than for a database."""
    specs = [s for s in PROPERTY_CATALOGUE if domain is None or s.domain == domain]
    if family:
        specs = [s for s in specs if not s.typical_range or family in s.typical_range or s.quantity_type == "boolean"]
    grouped: dict[str, list[dict]] = {}
    for spec in specs:
        grouped.setdefault(spec.domain, []).append(spec.as_dict())
    return {
        "domains": [
            {"key": key, **meta, "properties": grouped.get(key, [])}
            for key, meta in DOMAINS.items()
            if grouped.get(key)
        ],
        "property_count": len(specs),
    }


@router.get("/bench/data-grades")
def data_grades():
    """The closed provenance ladder. Confidence is set by the grade, never by the request."""
    return [
        {
            "key": g.key, "display_name": g.display_name, "description": g.description,
            "evidence_type": g.evidence_type, "source_quality": g.source_quality,
            "confidence": g.confidence, "requires_reference": g.requires_reference,
        }
        for g in DATA_GRADES
    ]


@router.get("/bench/resolve-property")
def resolve_property(label: str = Query(min_length=1)):
    """Map a datasheet label onto a catalogue key. Returns null rather than guessing."""
    return {"label": label, "property_key": resolve_property_key(label)}


@router.get("/bench/application-presets")
def application_presets():
    return [p.as_dict() for p in APPLICATION_PRESETS]


@router.get("/bench/replacement-drivers")
def replacement_drivers():
    return list(REPLACEMENT_DRIVERS)


@router.get("/bench/reference-library")
def reference_library():
    return [m.as_dict() for m in STARTER_LIBRARY]


# ------------------------------------------------------------------------------------ intake

@router.post("/bench/materials", response_model=IntakeResponse, status_code=201)
def create_material_intake(
    payload: MaterialIntakeRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    owner = _request_owner(payload.organisation_id, organisation_id)
    if owner and db.get(Organisation, owner) is None:
        raise HTTPException(422, "Organisation not found")
    try:
        result = intake_material(
            db,
            display_name=payload.display_name,
            material_family=payload.material_family.value,
            data_grade=payload.data_grade,
            description=payload.description,
            supplier=payload.supplier,
            grade_code=payload.grade_code,
            canonical_name=payload.canonical_name,
            identifiers=[i.model_dump() for i in payload.identifiers],
            components=[c.model_dump() for c in payload.components],
            process_state=payload.process_state.model_dump() if payload.process_state else None,
            properties=_entries(payload.properties),
            source_reference=payload.source_reference,
            method=payload.method,
            note=payload.note,
            organisation_id=owner,
            visibility=payload.visibility.value,
        )
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc

    return IntakeResponse(
        material_id=result.material.id, display_name=result.material.display_name,
        canonical_name=result.material.canonical_name, material_family=result.material.material_family,
        observation_count=result.observation_count, evidence_id=result.evidence_id,
        data_grade=payload.data_grade, warnings=result.warnings,
    )


@router.post("/bench/materials/{material_id}/properties", response_model=AppendResponse, status_code=201)
def append_property_data(
    material_id: str,
    payload: PropertyAppendRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    material = _visible_material(db, material_id, organisation_id)
    owner = _request_owner(payload.organisation_id, organisation_id)
    if material.is_seed_data and material.visibility == "public" and material.owner_organisation_id is None:
        raise HTTPException(409, {
            "code": "REFERENCE_MATERIAL_IMMUTABLE",
            "message": "Shared reference-library materials are read-only. Create a tenant-owned material or evidence overlay for your measurements.",
        })
    if material.owner_organisation_id is not None and owner != material.owner_organisation_id:
        # Do not reveal whether a private material exists to another tenant.
        raise HTTPException(404, "Material not found")
    try:
        count, warnings, evidence_id = add_property_data(
            db, material=material, data_grade=payload.data_grade, properties=_entries(payload.properties),
            source_reference=payload.source_reference, method=payload.method, note=payload.note,
            organisation_id=owner,
        )
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc
    return AppendResponse(
        material_id=material.id, observation_count=count, evidence_id=evidence_id, warnings=warnings,
    )


@router.post("/bench/install-reference-library")
def install_library(
    payload: LibraryInstallRequest | None = None,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Install the reference library. Idempotent — re-running skips what is already present.

    The library is installed as public reference data rather than owned by the calling
    organisation: these are published handbook figures for named commercial materials, not
    anybody's proprietary dataset, and scoping them privately would leave every other
    organisation on the deployment looking at an empty explorer again.
    """
    # The starter library is deployment-global, public screening data. Installing it does not
    # create or mutate tenant-owned records, so a missing tenant scope must not block bootstrap.
    return install_reference_library(db, organisation_id=None)


# ------------------------------------------------------------------------------------ readiness

@router.get("/bench/readiness")
def readiness(
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    return platform_readiness(db, organisation_id)


@router.get("/replacement-projects/{project_id}/readiness")
def project_readiness_route(
    project_id: str,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    result = project_readiness(db, project_id, organisation_id)
    if not result["found"]:
        raise HTTPException(404, "Project not found")
    return result


# ------------------------------------------------------------------------------------ search space

# Deliberately NOT nested under /search-spaces/: the generation router already owns
# GET /search-spaces/{search_space_id} and is registered first, so a nested literal path
# would be captured as a search-space id and 404.
@router.get("/replacement-projects/{project_id}/search-space-derivation")
def search_space_derivation_preview(
    project_id: str,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    project = _scoped_project(db, project_id, organisation_id)
    return derivation_preview(db, project)


@router.post("/replacement-projects/{project_id}/search-space-derivation", status_code=201)
def derive_space(
    project_id: str,
    activate: bool = Query(default=True),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    project = _scoped_project(db, project_id, organisation_id)
    result = derive_search_space(db, project, activate=activate)
    if not result["created"]:
        raise HTTPException(422, {
            "code": "SEARCH_SPACE_NOT_DERIVABLE",
            "blockers": result["preview"].get("blockers", []),
        })
    return result


# ------------------------------------------------------------------------------------ studies

@router.get("/replacement-projects/{project_id}/baseline-derived-requirements")
def baseline_derived_requirements(
    project_id: str,
    margin: float = Query(default=0.05, ge=0.0, le=0.5),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    project = _scoped_project(db, project_id, organisation_id)
    baseline = db.get(Material, project.baseline_material_id)
    if baseline is None:
        raise HTTPException(404, "Baseline material not found")
    return derive_requirements_from_baseline(db, baseline, margin_fraction=margin)


@router.get("/bench/materials/{material_id}/derived-requirements")
def material_derived_requirements(
    material_id: str,
    margin: float = Query(default=0.05, ge=0.0, le=0.5),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    material = _visible_material(db, material_id, organisation_id)
    return derive_requirements_from_baseline(db, material, margin_fraction=margin)


@router.post("/bench/studies", status_code=201)
def create_study_route(
    payload: StudyCreateRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    org = _request_owner(payload.organisation_id, organisation_id)
    creator = payload.created_by
    if org is None:
        # Demo-only fallback while auth is not wired: choose one organisation, then resolve a user
        # inside that same organisation. Never mix a user from another tenant.
        organisation = db.query(Organisation).order_by(Organisation.name).first()
        if organisation is None:
            raise HTTPException(422, "No organisation exists. Seed the database first.")
        org = organisation.id
    if creator is None:
        user = db.query(User).filter(User.organisation_id == org).order_by(User.display_name).first()
        if user is None:
            raise HTTPException(422, "No user exists in the selected organisation. Seed the database first.")
        creator = user.id
    try:
        return create_study(
            db,
            name=payload.name,
            baseline_material_id=payload.baseline_material_id,
            organisation_id=org,
            created_by=creator,
            drivers=payload.drivers,
            description=payload.description,
            preset_key=payload.preset_key,
            requirements=[r.model_dump() for r in payload.requirements],
            objectives=[o.model_dump() for o in payload.objectives],
            derive_from_baseline=payload.derive_from_baseline,
            baseline_margin=payload.baseline_margin,
            derive_space=payload.derive_space,
        )
    except IntakeError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/bench/materials-index")
def materials_index(
    q: str | None = Query(default=None),
    family: str | None = Query(default=None),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """A compact picker index: enough to choose a baseline, without the explorer's full payload."""
    query = db.query(Material).options(selectinload(Material.observations))
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public",
                                 Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    if q:
        query = query.filter(or_(Material.display_name.ilike(f"%{q}%"),
                                 Material.canonical_name.ilike(f"%{q}%")))
    if family:
        query = query.filter(Material.material_family == family)
    rows = query.order_by(Material.display_name).limit(300).all()
    return [
        {
            "id": m.id, "display_name": m.display_name, "material_family": m.material_family,
            "description": m.description, "is_seed_data": m.is_seed_data,
            "observation_count": sum(1 for o in m.observations if o.status == "active"),
            "source_type": m.source_type,
        }
        for m in rows
    ]


# ------------------------------------------------------------------------------------ property space

@router.get("/bench/property-space/axes")
def property_space_axes(
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Axes backed by values visible in the caller's organisation scope."""
    return axis_options(db, organisation_id=organisation_id)


@router.get("/bench/property-space")
def property_space_route(
    x: str = Query(default="density"),
    y: str = Query(default="tensile_strength"),
    family: str | None = Query(default=None),
    highlight: str | None = Query(default=None),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    try:
        result = property_space(
            db, x_key=x, y_key=y, family=family,
            organisation_id=organisation_id, highlight_material_id=highlight,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return result


@router.get("/bench/property-space/ranking")
def property_space_ranking(
    x: str = Query(default="density"),
    y: str = Query(default="tensile_strength"),
    index_key: str = Query(...),
    family: str | None = Query(default=None),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Rank the plotted materials on one material index rather than on a raw property.

    This is the question an Ashby chart is actually asked: not "which is strongest" but "which wins
    for this loading mode". The ranking is computed from the same plotted points, so a material with
    no recorded value for either axis is absent here too rather than ranked last.
    """
    index = next((i for i in indices_for(x, y) if i.key == index_key), None)
    if index is None:
        raise HTTPException(422, f"No material index '{index_key}' is defined for this axis pair.")
    try:
        space = property_space(db, x_key=x, y_key=y, family=family, organisation_id=organisation_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ranked = [
        {
            "material_id": p["material_id"], "display_name": p["display_name"],
            "material_family": p["material_family"], "index_value": index_value(p["x"], p["y"], index),
            "x": p["x"], "y": p["y"],
            "lowest_origin": p.get("weakest_origin") or p["x_origin"],
        }
        for p in space["points"]
    ]
    ranked.sort(key=lambda r: r["index_value"], reverse=index.maximise)
    return {
        "index": index.as_dict(), "x_axis": space["x_axis"], "y_axis": space["y_axis"],
        "ranking": ranked, "excluded_count": space["excluded_count"],
    }


@router.get("/replacement-projects/{project_id}/decision-chart")
def decision_chart_route(
    project_id: str,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    """Chart-ready view of the decision, with margins computed against each requirement's threshold.

    Statuses come from the canonical evaluator; nothing is re-decided here. The only derived value
    is the signed percentage margin, computed server-side because it needs the real unit registry.
    """
    result = decision_chart(db, project_id, organisation_id)
    if not result.get("found"):
        raise HTTPException(404, "Project not found")
    return result
