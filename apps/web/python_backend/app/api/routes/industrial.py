from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    IndustrialConstraint,
    IndustrialEvidence,
    IndustrialViabilityAssessment,
    ManufacturingRoute,
    MaterialProcessCompatibility,
    MaturityAssessment,
    ReplacementProject,
    User,
)
from app.schemas.industrial import (
    IndustrialConstraintCreate,
    IndustrialConstraintOut,
    IndustrialEvidenceCreate,
    IndustrialEvidenceOut,
    ManufacturingRouteCreate,
    ManufacturingRouteOut,
    MaturityAssessmentCreate,
    MaturityAssessmentOut,
    ProcessCompatibilityCreate,
    ProcessCompatibilityOut,
    ViabilityAssessmentOut,
    ViabilityAssessmentRequest,
    ViabilityComparisonRequest,
)
from app.services.industrial import (
    ASSESSMENT_DIMENSIONS,
    INDUSTRIAL_SEPARATION_NOTE,
    MAX_PAGE_SIZE,
    IndustrialError,
    assess_industrial_viability,
    compare_industrial_viability,
    compatibilities_for_target,
    create_industrial_evidence,
    current_maturity,
    detect_conflicts,
    industrial_evidence_for_target,
    is_stale,
    resolve_industrial_target,
)

router = APIRouter(tags=["industrial"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _project(db: Session, project_id: str, organisation_id: str) -> ReplacementProject:
    project = db.get(ReplacementProject, project_id)
    if not project or project.organisation_id != organisation_id:
        raise HTTPException(404, "Project not found")
    return project


def _default_user(db: Session, organisation_id: str) -> str | None:
    user = db.query(User).filter_by(organisation_id=organisation_id).order_by(User.created_at).first()
    return user.id if user else None


def _require_target(db: Session, target_kind: str, target_id: str, organisation_id: str) -> None:
    if resolve_industrial_target(db, target_kind, target_id, organisation_id) is None:
        # 404 rather than 403: a foreign target must be indistinguishable from a missing one.
        raise HTTPException(404, "Industrial target not found")


# --- manufacturing routes -------------------------------------------------------------------
@router.get("/industrial/manufacturing-routes", response_model=list[ManufacturingRouteOut])
def list_manufacturing_routes(
    process_family: str | None = None,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    from sqlalchemy import or_

    query = db.query(ManufacturingRoute).filter(ManufacturingRoute.status == "active")
    query = query.filter(
        or_(ManufacturingRoute.organisation_id.is_(None), ManufacturingRoute.organisation_id == organisation_id)
        if organisation_id else ManufacturingRoute.organisation_id.is_(None)
    )
    if process_family:
        query = query.filter(ManufacturingRoute.process_family == process_family)
    return query.order_by(ManufacturingRoute.process_family, ManufacturingRoute.key).all()


@router.post("/industrial/manufacturing-routes", response_model=ManufacturingRouteOut, status_code=201)
def create_manufacturing_route(
    payload: ManufacturingRouteCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    existing = db.query(ManufacturingRoute).filter_by(organisation_id=org, key=payload.key).one_or_none()
    if existing:
        raise HTTPException(409, f"A manufacturing route with key '{payload.key}' already exists in this scope")
    route = ManufacturingRoute(organisation_id=org, **payload.model_dump())
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


# --- industrial evidence --------------------------------------------------------------------
@router.get("/industrial/evidence", response_model=list[IndustrialEvidenceOut])
def list_industrial_evidence(
    target_kind: str, target_id: str, category: str | None = None, metric_key: str | None = None,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if target_kind not in {"known_material", "hypothesis"}:
        raise HTTPException(422, "target_kind must be known_material or hypothesis")
    _require_target(db, target_kind, target_id, org)
    return industrial_evidence_for_target(
        db, target_kind=target_kind, target_id=target_id, organisation_id=org,
        category=category, metric_key=metric_key,
    )


@router.post("/industrial/evidence", response_model=IndustrialEvidenceOut, status_code=201)
def add_industrial_evidence(
    payload: IndustrialEvidenceCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, payload.target_kind, payload.target_id, org)
    values = payload.model_dump(exclude={"target_kind", "target_id"})
    values["material_id"] = payload.target_id if payload.target_kind == "known_material" else None
    values["hypothesis_id"] = payload.target_id if payload.target_kind == "hypothesis" else None
    values["organisation_id"] = org
    try:
        row = create_industrial_evidence(db, values)
    except IndustrialError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    db.refresh(row)
    return row


@router.get("/industrial/evidence/conflicts")
def evidence_conflicts(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """Contradictory records are surfaced, never resolved automatically."""
    org = _org(organisation_id)
    _require_target(db, target_kind, target_id, org)
    rows = industrial_evidence_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=org)
    return {
        "target_kind": target_kind, "target_id": target_id,
        "conflicts": detect_conflicts(rows),
        "stale_evidence_ids": [r.id for r in rows if is_stale(r)],
        "note": "Conflicting records are both retained. The newer record does not automatically win, "
                "and no value is averaged across a contradiction.",
    }


# --- process compatibility ------------------------------------------------------------------
@router.get("/industrial/process-compatibility", response_model=list[ProcessCompatibilityOut])
def list_process_compatibility(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, target_kind, target_id, org)
    return compatibilities_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=org)


@router.post("/industrial/process-compatibility", response_model=ProcessCompatibilityOut, status_code=201)
def set_process_compatibility(
    payload: ProcessCompatibilityCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, payload.target_kind, payload.target_id, org)
    route = db.get(ManufacturingRoute, payload.route_id)
    if not route or (route.organisation_id is not None and route.organisation_id != org):
        raise HTTPException(404, "Manufacturing route not found")
    material_id = payload.target_id if payload.target_kind == "known_material" else None
    hypothesis_id = payload.target_id if payload.target_kind == "hypothesis" else None
    if payload.industrial_evidence_id:
        evidence = db.get(IndustrialEvidence, payload.industrial_evidence_id)
        if not evidence or evidence.organisation_id not in {None, org}:
            raise HTTPException(404, "Supporting industrial evidence not found")
        if (material_id and evidence.material_id != material_id) or (hypothesis_id and evidence.hypothesis_id != hypothesis_id):
            raise HTTPException(422, "CANDIDATE_TARGET_MISMATCH: supporting industrial evidence belongs to a different target")
    existing = db.query(MaterialProcessCompatibility).filter_by(
        route_id=payload.route_id, material_id=material_id, hypothesis_id=hypothesis_id
    ).one_or_none()
    if existing:
        raise HTTPException(409, "A compatibility record already exists for this route and target")
    row = MaterialProcessCompatibility(
        organisation_id=org, route_id=payload.route_id, material_id=material_id, hypothesis_id=hypothesis_id,
        compatibility=payload.compatibility, rationale=payload.rationale, conditions=payload.conditions,
        industrial_evidence_id=payload.industrial_evidence_id, as_of_date=payload.as_of_date,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- constraints ------------------------------------------------------------------------------
@router.get("/projects/{project_id}/industrial-constraints", response_model=list[IndustrialConstraintOut])
def list_industrial_constraints(
    project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _project(db, project_id, org)
    return (
        db.query(IndustrialConstraint).filter_by(project_id=project_id, organisation_id=org)
        .order_by(IndustrialConstraint.category, IndustrialConstraint.id).all()
    )


@router.post("/projects/{project_id}/industrial-constraints", response_model=IndustrialConstraintOut, status_code=201)
def create_industrial_constraint(
    project_id: str, payload: IndustrialConstraintCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _project(db, project_id, org)
    row = IndustrialConstraint(organisation_id=org, project_id=project_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- maturity ---------------------------------------------------------------------------------
@router.get("/industrial/maturity", response_model=list[MaturityAssessmentOut])
def list_maturity(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, target_kind, target_id, org)
    query = db.query(MaturityAssessment).filter(
        (MaturityAssessment.organisation_id == org) | (MaturityAssessment.organisation_id.is_(None))
    )
    query = query.filter(
        MaturityAssessment.material_id == target_id if target_kind == "known_material"
        else MaturityAssessment.hypothesis_id == target_id
    )
    return query.order_by(MaturityAssessment.created_at.desc(), MaturityAssessment.id).all()


@router.post("/industrial/maturity", response_model=MaturityAssessmentOut, status_code=201)
def create_maturity_assessment(
    payload: MaturityAssessmentCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, payload.target_kind, payload.target_id, org)
    material_id = payload.target_id if payload.target_kind == "known_material" else None
    hypothesis_id = payload.target_id if payload.target_kind == "hypothesis" else None
    for evidence_id in payload.supporting_evidence_ids:
        evidence = db.get(IndustrialEvidence, evidence_id)
        if not evidence or evidence.organisation_id not in {None, org}:
            raise HTTPException(404, "Supporting industrial evidence not found")
        if (material_id and evidence.material_id != material_id) or (hypothesis_id and evidence.hypothesis_id != hypothesis_id):
            raise HTTPException(422, "CANDIDATE_TARGET_MISMATCH: maturity evidence belongs to a different target")
    row = MaturityAssessment(
        organisation_id=org,
        material_id=material_id, hypothesis_id=hypothesis_id,
        stage=payload.stage, scope=payload.scope, justification=payload.justification,
        supporting_evidence_ids=payload.supporting_evidence_ids, as_of_date=payload.as_of_date,
        assessed_by=_default_user(db, org),
    )
    db.add(row)
    db.flush()
    # Prior assessments are superseded, never rewritten: the earlier judgement stays readable.
    query = db.query(MaturityAssessment).filter(
        MaturityAssessment.organisation_id == org,
        MaturityAssessment.superseded_by_id.is_(None), MaturityAssessment.id != row.id
    )
    query = query.filter(
        MaturityAssessment.material_id == payload.target_id if payload.target_kind == "known_material"
        else MaturityAssessment.hypothesis_id == payload.target_id
    )
    for old in query.all():
        old.superseded_by_id = row.id
    db.commit()
    db.refresh(row)
    return row


@router.get("/industrial/maturity/current")
def get_current_maturity(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _require_target(db, target_kind, target_id, org)
    stage, row = current_maturity(db, target_kind=target_kind, target_id=target_id, organisation_id=org)
    return {
        "target_kind": target_kind, "target_id": target_id, "stage": stage,
        "assessment_id": row.id if row else None,
        "justification": row.justification if row else None,
        "note": "Maturity stages are evidence-backed labels defined by this system. They are "
                "deliberately not presented as formal Technology Readiness Levels, which require an "
                "assessment procedure TinkerLab does not perform.",
    }


# --- viability assessment -----------------------------------------------------------------------
@router.get("/industrial/dimensions")
def list_dimensions():
    return {
        "dimensions": list(ASSESSMENT_DIMENSIONS),
        "states": ["pass", "fail", "partial", "unknown", "insufficient_evidence", "conflicting_evidence"],
        "separation_note": INDUSTRIAL_SEPARATION_NOTE,
    }


@router.post("/industrial/viability/assess")
def assess_viability(
    payload: ViabilityAssessmentRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _project(db, payload.project_id, org)
    try:
        row, result = assess_industrial_viability(
            db, project_id=payload.project_id, organisation_id=org,
            target_kind=payload.target_kind, target_id=payload.target_id,
            candidate_id=payload.candidate_id, created_by=_default_user(db, org),
            composite_methodology=payload.composite_methodology,
            composite_weights=payload.composite_weights, persist=payload.persist,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except IndustrialError as exc:
        raise HTTPException(422, str(exc)) from exc
    if payload.persist:
        db.commit()
    else:
        db.rollback()
    return result


@router.post("/industrial/viability/compare")
def compare_viability(
    payload: ViabilityComparisonRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _project(db, payload.project_id, org)
    for target in payload.targets:
        if target.get("target_kind") not in {"known_material", "hypothesis"} or not target.get("target_id"):
            raise HTTPException(422, "Each target requires target_kind and target_id")
    try:
        result = compare_industrial_viability(
            db, project_id=payload.project_id, organisation_id=org, targets=payload.targets,
            composite_methodology=payload.composite_methodology, composite_weights=payload.composite_weights,
        )
    except IndustrialError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.rollback()  # comparison never persists
    return result


@router.get("/industrial/viability/assessments", response_model=list[ViabilityAssessmentOut])
def list_assessments(
    project_id: str, target_id: str | None = None, include_superseded: bool = False,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _project(db, project_id, org)
    query = db.query(IndustrialViabilityAssessment).filter_by(project_id=project_id, organisation_id=org)
    if target_id:
        query = query.filter(IndustrialViabilityAssessment.target_scientific_id == target_id)
    if not include_superseded:
        query = query.filter(IndustrialViabilityAssessment.superseded_by_id.is_(None))
    return (
        query.order_by(IndustrialViabilityAssessment.created_at.desc(), IndustrialViabilityAssessment.id)
        .offset(offset).limit(limit).all()
    )


@router.get("/industrial/viability/assessments/{assessment_id}", response_model=ViabilityAssessmentOut)
def get_assessment(
    assessment_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    row = db.query(IndustrialViabilityAssessment).filter_by(id=assessment_id, organisation_id=org).one_or_none()
    if not row:
        raise HTTPException(404, "Industrial viability assessment not found")
    return row
