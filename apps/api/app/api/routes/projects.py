from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Candidate,
    Constraint,
    Material,
    Objective,
    Organisation,
    ReplacementProject,
    User,
)
from app.schemas.projects import (
    CandidateCreate,
    CandidateEvaluationOut,
    CandidateOut,
    ConstraintCreate,
    ConstraintOut,
    ObjectiveCreate,
    ObjectiveOut,
    ProjectCreate,
    ProjectDetail,
    ReplacementSpecificationOut,
)
from app.services.evaluation import evaluate_candidate
from app.services.prediction import prediction_map_for_run
from app.services.selection import build_selection_context
from app.services.specification import compile_specification
from app.services.validation import DomainValidationError, validate_constraint, validate_objective

router = APIRouter(prefix="/replacement-projects", tags=["replacement-projects"])


def project_query(db: Session):
    return db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
        selectinload(ReplacementProject.candidates).selectinload(Candidate.material),
        selectinload(ReplacementProject.candidates).selectinload(Candidate.hypothesis),
    )


@router.get("")
def list_projects(q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.candidates),
    )
    if q:
        query = query.filter(ReplacementProject.name.ilike(f"%{q}%"))
    projects = query.order_by(ReplacementProject.updated_at.desc()).limit(100).all()
    return [
        {
            "id": p.id, "name": p.name, "description": p.description,
            "baseline_material_id": p.baseline_material_id,
            "baseline_material": {"id": p.baseline_material.id, "display_name": p.baseline_material.display_name,
                                  "canonical_name": p.baseline_material.canonical_name, "material_family": p.baseline_material.material_family,
                                  "description": p.baseline_material.description, "source_type": p.baseline_material.source_type,
                                  "is_seed_data": p.baseline_material.is_seed_data},
            "replacement_reasons": p.replacement_reasons, "status": p.status,
            "constraint_count": len(p.constraints), "candidate_count": len(p.candidates),
            "created_at": p.created_at, "updated_at": p.updated_at,
        } for p in projects
    ]


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if not db.get(Organisation, payload.organisation_id):
        raise HTTPException(422, "Organisation not found")
    if not db.get(User, payload.created_by):
        raise HTTPException(422, "User not found")
    if not db.get(Material, payload.baseline_material_id):
        raise HTTPException(422, "Baseline material not found")
    values = payload.model_dump(mode="json")
    project = ReplacementProject(**values)
    db.add(project)
    db.commit()
    return project_query(db).filter(ReplacementProject.id == project.id).one()


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = project_query(db).filter(ReplacementProject.id == project_id).one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/{project_id}/constraints", response_model=ConstraintOut, status_code=201)
def add_constraint(project_id: str, payload: ConstraintCreate, db: Session = Depends(get_db)):
    if not db.get(ReplacementProject, project_id):
        raise HTTPException(404, "Project not found")
    try:
        validate_constraint(db, payload)
    except DomainValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    values = payload.model_dump(mode="json")
    metadata = values.pop("metadata")
    constraint = Constraint(project_id=project_id, **values, metadata_json=metadata)
    db.add(constraint)
    db.commit()
    db.refresh(constraint)
    return constraint


@router.post("/{project_id}/objectives", response_model=ObjectiveOut, status_code=201)
def add_objective(project_id: str, payload: ObjectiveCreate, db: Session = Depends(get_db)):
    if not db.get(ReplacementProject, project_id):
        raise HTTPException(404, "Project not found")
    try:
        validate_objective(db, payload)
    except DomainValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    objective = Objective(project_id=project_id, **payload.model_dump(mode="json"))
    db.add(objective)
    db.commit()
    db.refresh(objective)
    return objective


@router.post("/{project_id}/candidates", response_model=CandidateOut, status_code=201)
def add_candidate(project_id: str, payload: CandidateCreate, db: Session = Depends(get_db)):
    if not db.get(ReplacementProject, project_id):
        raise HTTPException(404, "Project not found")
    if not db.get(Material, payload.material_id):
        raise HTTPException(422, "Material not found")
    candidate = Candidate(project_id=project_id, candidate_kind="known_material", hypothesis_id=None, **payload.model_dump(mode="json"))
    db.add(candidate)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Material is already a candidate in this project") from exc
    return project_query(db).filter(ReplacementProject.id == project_id).one().candidates[-1]


@router.get("/{project_id}/specification", response_model=ReplacementSpecificationOut)
def specification(project_id: str, db: Session = Depends(get_db)):
    project = project_query(db).filter(ReplacementProject.id == project_id).one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return compile_specification(project)


@router.get("/{project_id}/comparison", response_model=list[CandidateEvaluationOut])
def comparison(project_id: str, include_hypotheses: bool = Query(default=False), prediction_run_id: str | None = Query(default=None), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = project_query(db).filter(ReplacementProject.id == project_id).one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    candidates = list(project.candidates)
    if include_hypotheses:
        if not organisation_id or organisation_id != project.organisation_id:
            raise HTTPException(404, "Project not found")
        hypothesis_candidates = (
            db.query(Candidate).options(selectinload(Candidate.hypothesis)).filter(
                Candidate.project_id == project.id, Candidate.candidate_kind == "hypothesis"
            ).order_by(Candidate.created_at, Candidate.id).all()
        )
        candidates.extend(hypothesis_candidates)
    known_material_ids = [c.material.id for c in candidates if c.candidate_kind == "known_material" and c.material is not None]
    selection_context = build_selection_context(db, [project.baseline_material.id, *known_material_ids])
    prediction_map = None
    if prediction_run_id:
        if not organisation_id or organisation_id != project.organisation_id:
            raise HTTPException(404, "Project not found")
        try:
            prediction_map = prediction_map_for_run(db, prediction_run_id, project.id, organisation_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
    return [evaluate_candidate(db, project, c, selection_context, prediction_map) for c in candidates]
