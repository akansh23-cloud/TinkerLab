from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Application,
    ApplicationComponent,
    CandidateReasoningResult,
    FunctionalRequirement,
    MaterialFunction,
    MaterialRole,
    MaterialState,
    Mechanism,
    ProcessingHistory,
    ReplacementProject,
    StructuralFeature,
)
from app.schemas.reasoning import (
    ApplicationComponentCreate,
    ApplicationCreate,
    CandidateReasoningOut,
    FunctionalRequirementCreate,
    MaterialFunctionCreate,
    MaterialRoleCreate,
    MaterialStateCreate,
    MaterialStateOut,
    ProcessingHistoryCreate,
    ReasoningEdgeCreate,
    ReasoningRequest,
)
from app.services.material_states import (
    StateError,
    create_material_state,
    create_processing_history,
    match_states,
    states_for_target,
)
from app.services.reasoning import (
    MAX_PAGE_SIZE,
    ORIGIN_SEPARATION_NOTE,
    ReasoningError,
    create_reasoning_edge,
    property_definition_by_key,
    reason_about_candidate,
    role_decomposition,
)
from app.services.simulation import resolve_target

router = APIRouter(tags=["reasoning"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _require_target(db: Session, target_kind: str, target_id: str, organisation_id: str) -> None:
    if resolve_target(db, target_kind, target_id, organisation_id) is None:
        raise HTTPException(404, "Target not found")


def _scoped_application(db: Session, application_id: str, organisation_id: str) -> Application:
    row = db.get(Application, application_id)
    if not row or (row.organisation_id is not None and row.organisation_id != organisation_id):
        raise HTTPException(404, "Application not found")
    return row


def _scoped_role(db: Session, role_id: str, organisation_id: str) -> MaterialRole:
    role = db.get(MaterialRole, role_id)
    if role is None:
        raise HTTPException(404, "Material role not found")
    component = db.get(ApplicationComponent, role.component_id)
    application = db.get(Application, component.application_id) if component else None
    if application is None or (application.organisation_id is not None
                               and application.organisation_id != organisation_id):
        raise HTTPException(404, "Material role not found")
    return role


# --- material states ---------------------------------------------------------------------------
@router.post("/reasoning/processing-histories", status_code=201)
def create_history(
    payload: ProcessingHistoryCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    history = create_processing_history(
        db, organisation_id=org, display_name=payload.display_name, key=payload.key,
        description=payload.description, steps=[s.model_dump() for s in payload.steps],
    )
    db.commit()
    return {"id": history.id, "history_checksum": history.history_checksum,
            "step_count": len(payload.steps)}


@router.get("/reasoning/processing-histories/{history_id}")
def get_history(
    history_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    row = (
        db.query(ProcessingHistory).options(selectinload(ProcessingHistory.steps))
        .filter(ProcessingHistory.id == history_id).one_or_none()
    )
    if not row or (row.organisation_id is not None and row.organisation_id != organisation_id):
        raise HTTPException(404, "Processing history not found")
    return {
        "id": row.id, "display_name": row.display_name, "history_checksum": row.history_checksum,
        "steps": [
            {"sequence": s.sequence, "step_kind": s.step_kind, "display_name": s.display_name,
             "temperature_k": s.temperature_k, "duration_s": s.duration_s,
             "atmosphere": s.atmosphere, "cooling_rate_k_per_s": s.cooling_rate_k_per_s}
            for s in row.steps
        ],
    }


@router.post("/reasoning/material-states", response_model=MaterialStateOut, status_code=201)
def create_state(
    payload: MaterialStateCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, payload.target_kind, payload.target_id, org)
    values = payload.model_dump(exclude={"target_kind", "target_id", "composition"})
    try:
        state = create_material_state(
            db, organisation_id=org,
            material_id=payload.target_id if payload.target_kind == "known_material" else None,
            hypothesis_id=payload.target_id if payload.target_kind == "hypothesis" else None,
            composition=[c.model_dump() for c in payload.composition], **values,
        )
    except StateError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    db.refresh(state)
    return state


@router.get("/reasoning/material-states", response_model=list[MaterialStateOut])
def list_states(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if target_kind not in {"known_material", "hypothesis"}:
        raise HTTPException(422, "target_kind must be known_material or hypothesis")
    _require_target(db, target_kind, target_id, org)
    return states_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=org)


@router.get("/reasoning/material-states/{state_id}/compare/{other_state_id}")
def compare_states(
    state_id: str, other_state_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """State compatibility, with reasons. This is what decides whether a property may be reused."""
    org = _org(organisation_id)
    first, second = db.get(MaterialState, state_id), db.get(MaterialState, other_state_id)
    for state in (first, second):
        if state is None or (state.organisation_id is not None and state.organisation_id != org):
            raise HTTPException(404, "Material state not found")
    match = match_states(first, second)
    return {
        "state_id": state_id, "other_state_id": other_state_id,
        "match_quality": match.quality, "reasons": list(match.reasons), "usable": match.usable,
        "note": "Only EXACT and COMPATIBLE permit a property recorded in one state to be used for "
                "the other. A shared chemical formula is not a shared structure.",
    }


# --- application decomposition --------------------------------------------------------------------
@router.post("/reasoning/applications", status_code=201)
def create_application(
    payload: ApplicationCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if db.query(Application).filter_by(organisation_id=org, key=payload.key).one_or_none():
        raise HTTPException(409, f"An application with key '{payload.key}' already exists")
    row = Application(organisation_id=org, **payload.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key, "display_name": row.display_name}


@router.get("/reasoning/applications")
def list_applications(
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    from sqlalchemy import or_

    rows = (
        db.query(Application).options(selectinload(Application.components))
        .filter(Application.status == "active")
        .filter(or_(Application.organisation_id.is_(None), Application.organisation_id == organisation_id)
                if organisation_id else Application.organisation_id.is_(None))
        .order_by(Application.key).all()
    )
    return [
        {"id": a.id, "key": a.key, "display_name": a.display_name, "domain": a.domain,
         "description": a.description, "operating_conditions": a.operating_conditions,
         "components": [{"id": c.id, "key": c.key, "display_name": c.display_name} for c in a.components]}
        for a in rows
    ]


@router.post("/reasoning/applications/{application_id}/components", status_code=201)
def create_component(
    application_id: str, payload: ApplicationComponentCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    _scoped_application(db, application_id, _org(organisation_id))
    row = ApplicationComponent(application_id=application_id, **payload.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key}


@router.get("/reasoning/roles")
def list_roles(
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """List visible material roles for candidate-centric reasoning/validation workspaces."""
    org = _org(organisation_id)
    rows = (
        db.query(MaterialRole, ApplicationComponent, Application)
        .join(ApplicationComponent, ApplicationComponent.id == MaterialRole.component_id)
        .join(Application, Application.id == ApplicationComponent.application_id)
        .filter((Application.organisation_id.is_(None)) | (Application.organisation_id == org))
        .filter(Application.status == "active")
        .order_by(Application.display_name, ApplicationComponent.display_name, MaterialRole.display_name)
        .all()
    )
    return [
        {
            "id": role.id, "key": role.key, "display_name": role.display_name,
            "application_id": application.id, "application_name": application.display_name,
            "component_id": component.id, "component_name": component.display_name,
            "incumbent_material_id": role.incumbent_material_id, "incumbent_state_id": role.incumbent_state_id,
        }
        for role, component, application in rows
    ]


@router.post("/reasoning/components/{component_id}/roles", status_code=201)
def create_role(
    component_id: str, payload: MaterialRoleCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    component = db.get(ApplicationComponent, component_id)
    if component is None:
        raise HTTPException(404, "Application component not found")
    _scoped_application(db, component.application_id, org)
    row = MaterialRole(component_id=component_id, **payload.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key}


@router.post("/reasoning/roles/{role_id}/functions", status_code=201)
def create_function(
    role_id: str, payload: MaterialFunctionCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    _scoped_role(db, role_id, _org(organisation_id))
    row = MaterialFunction(role_id=role_id, **payload.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key}


@router.post("/reasoning/functions/{function_id}/requirements", status_code=201)
def create_requirement(
    function_id: str, payload: FunctionalRequirementCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    function = db.get(MaterialFunction, function_id)
    if function is None:
        raise HTTPException(404, "Material function not found")
    _scoped_role(db, function.role_id, org)
    definition = property_definition_by_key(db, payload.property_key) if payload.property_key else None
    if payload.property_key and definition is None:
        raise HTTPException(
            422, f"Unknown property definition '{payload.property_key}'. A requirement must bind to a "
                 "registered property so evidence can be matched to it.")
    row = FunctionalRequirement(
        function_id=function_id, property_definition_id=definition.id if definition else None,
        **payload.model_dump(),
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key, "property_definition_id": row.property_definition_id}


@router.get("/reasoning/roles/{role_id}/decomposition")
def get_decomposition(
    role_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    _scoped_role(db, role_id, _org(organisation_id))
    decomposition = role_decomposition(db, role_id)
    role = decomposition["role"]
    return {
        "application": {"id": decomposition["application"].id, "display_name": decomposition["application"].display_name}
        if decomposition["application"] else None,
        "component": {"id": decomposition["component"].id, "display_name": decomposition["component"].display_name}
        if decomposition["component"] else None,
        "role": {"id": role.id, "key": role.key, "display_name": role.display_name,
                 "incumbent_material_id": role.incumbent_material_id,
                 "incumbent_state_id": role.incumbent_state_id},
        "functions": [
            {"id": f.id, "key": f.key, "display_name": f.display_name, "category": f.category,
             "criticality": f.criticality,
             "requirements": [
                 {"id": r.id, "key": r.key, "display_name": r.display_name,
                  "requirement_kind": r.requirement_kind, "direction": r.direction,
                  "property_key": r.property_key, "target_value": r.target_value,
                  "target_value_upper": r.target_value_upper, "target_unit": r.target_unit,
                  "conditions": r.conditions, "rationale": r.rationale}
                 for r in sorted(f.requirements, key=lambda x: x.key)
             ]}
            for f in decomposition["functions"]
        ],
    }


# --- reasoning graph ---------------------------------------------------------------------------
@router.post("/reasoning/edges", status_code=201)
def create_edge(
    payload: ReasoningEdgeCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    try:
        edge = create_reasoning_edge(db, {"organisation_id": org, **payload.model_dump()})
    except ReasoningError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {"id": edge.id, "edge_kind": edge.edge_kind}


@router.get("/reasoning/features")
def list_features(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    from sqlalchemy import or_

    features = db.query(StructuralFeature).filter(
        or_(StructuralFeature.organisation_id.is_(None), StructuralFeature.organisation_id == organisation_id)
        if organisation_id else StructuralFeature.organisation_id.is_(None)
    ).order_by(StructuralFeature.key).all()
    mechanisms = db.query(Mechanism).filter(
        or_(Mechanism.organisation_id.is_(None), Mechanism.organisation_id == organisation_id)
        if organisation_id else Mechanism.organisation_id.is_(None)
    ).order_by(Mechanism.key).all()
    return {
        "structural_features": [
            {"id": f.id, "key": f.key, "display_name": f.display_name, "scale": f.feature_scale,
             "description": f.description} for f in features
        ],
        "mechanisms": [
            {"id": m.id, "key": m.key, "display_name": m.display_name, "category": m.category,
             "description": m.description} for m in mechanisms
        ],
    }


# --- candidate reasoning -------------------------------------------------------------------------
@router.post("/reasoning/candidate")
def reason_candidate(
    payload: ReasoningRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _scoped_role(db, payload.role_id, org)
    _require_target(db, payload.target_kind, payload.target_id, org)
    if payload.project_id:
        project = db.get(ReplacementProject, payload.project_id)
        if not project or project.organisation_id != org:
            raise HTTPException(404, "Project not found")
    try:
        result = reason_about_candidate(
            db, organisation_id=org, role_id=payload.role_id, target_kind=payload.target_kind,
            target_id=payload.target_id, project_id=payload.project_id,
            candidate_id=payload.candidate_id, state_id=payload.state_id,
            generation_rationale=payload.generation_rationale, persist=payload.persist,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ReasoningError as exc:
        raise HTTPException(422, str(exc)) from exc
    if payload.persist:
        db.commit()
    else:
        db.rollback()
    return result


@router.get("/reasoning/results", response_model=list[CandidateReasoningOut])
def list_reasoning_results(
    role_id: str | None = None, target_id: str | None = None, include_superseded: bool = False,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    query = db.query(CandidateReasoningResult).filter_by(organisation_id=org)
    if role_id:
        query = query.filter(CandidateReasoningResult.role_id == role_id)
    if target_id:
        query = query.filter(CandidateReasoningResult.target_scientific_id == target_id)
    if not include_superseded:
        query = query.filter(CandidateReasoningResult.superseded_by_id.is_(None))
    return (
        query.order_by(CandidateReasoningResult.created_at.desc(), CandidateReasoningResult.id)
        .offset(offset).limit(limit).all()
    )


@router.get("/reasoning/origin-policy")
def origin_policy():
    return {
        "origin_separation_note": ORIGIN_SEPARATION_NOTE,
        "origins": ["observed", "literature", "predicted", "simulated", "experimental", "industrial", "unknown"],
        "statuses": ["pass", "fail", "partial", "unknown", "insufficient_evidence",
                     "conflicting_evidence", "state_mismatch"],
        "structured_first_note": (
            "Requirement statuses are computed from stored structured data. A language model may "
            "narrate them but cannot change them."
        ),
    }
