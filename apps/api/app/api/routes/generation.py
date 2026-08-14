from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    CandidateLineageEdge,
    CandidateSearchSpace,
    GenerationRun,
    GenerationRunResult,
    Material,
    ReplacementProject,
    SearchSpaceComponentRule,
    SearchSpaceProcessRule,
    SubstitutionRule,
)
from app.schemas.generation import (
    CandidateHypothesisOut,
    CandidateListItem,
    CandidatePage,
    GenerationPreviewOut,
    GenerationPreviewRequest,
    GenerationRunCreate,
    GenerationRunOut,
    LineageEdgeOut,
    ManualHypothesisCreate,
    SearchSpaceComponentRuleIn,
    SearchSpaceCreate,
    SearchSpaceOut,
    SearchSpaceProcessRuleIn,
    SearchSpaceValidationOut,
    StrategyDescriptor,
    SubstitutionRuleCreate,
    SubstitutionRuleOut,
)
from app.services.conflicts import detect_conflicts_from_observations
from app.services.evaluation import evaluate_constraint
from app.services.generation import (
    STRATEGIES,
    create_manual_hypothesis,
    execute_generation,
    get_search_space,
    preview_generation,
    search_space_checksum,
    validate_search_space,
)
from app.services.selection import build_selection_context

router = APIRouter(tags=["candidate-generation"])


@dataclass(frozen=True)
class _CandidateDisplay:
    """Resolves the known-material / hypothesis invariant once, explicitly, instead of at every call site."""
    name: str
    posture: str
    structural_validity: str | None
    fingerprint: str | None
    generation_run_id: str | None
    change_count: int


def _candidate_display(candidate: Candidate, *, known_posture: str) -> _CandidateDisplay:
    if candidate.candidate_kind == "known_material":
        material = candidate.material
        if material is None:
            raise HTTPException(500, "Candidate is marked as a known material but has no linked material record")
        return _CandidateDisplay(material.display_name, known_posture, None, None, None, 0)
    hypothesis = candidate.hypothesis
    if hypothesis is None:
        raise HTTPException(500, "Candidate is marked as a hypothesis but has no linked hypothesis record")
    return _CandidateDisplay(
        hypothesis.display_label, "UNKNOWN — NOT YET PREDICTED/TESTED", hypothesis.structural_validity,
        hypothesis.deterministic_fingerprint, hypothesis.generation_run_id, len(hypothesis.changes),
    )



def _scoped_project(db: Session, project_id: str, organisation_id: str | None) -> ReplacementProject:
    # Phase-3 search spaces/runs/hypotheses are organisation-private development resources.
    # X-Organisation-ID is a scoping seam only, not production authentication.
    if not organisation_id:
        raise HTTPException(404, "Project not found")
    query = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
    ).filter(ReplacementProject.id == project_id)
    if organisation_id:
        query = query.filter(ReplacementProject.organisation_id == organisation_id)
    project = query.one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _scoped_search_space(db: Session, project: ReplacementProject, search_space_id: str) -> CandidateSearchSpace:
    row = get_search_space(db, search_space_id)
    if not row or row.project_id != project.id or row.organisation_id != project.organisation_id:
        raise HTTPException(404, "Search space not found")
    return row


def _hypothesis_query(db: Session):
    return db.query(CandidateHypothesis).options(
        selectinload(CandidateHypothesis.components),
        selectinload(CandidateHypothesis.process_parameters),
        selectinload(CandidateHypothesis.changes),
    )


@router.get("/candidate-generation/strategies", response_model=list[StrategyDescriptor])
def strategies():
    return [STRATEGIES[key] for key in sorted(STRATEGIES)]


@router.post("/replacement-projects/{project_id}/search-spaces", response_model=SearchSpaceOut, status_code=201)
def create_search_space(project_id: str, payload: SearchSpaceCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    latest = db.query(CandidateSearchSpace).filter_by(project_id=project.id).order_by(CandidateSearchSpace.version.desc()).first()
    row = CandidateSearchSpace(
        project_id=project.id, organisation_id=project.organisation_id, version=(latest.version + 1 if latest else 1),
        material_family=payload.material_family, amount_basis=payload.amount_basis, balance_component_key=payload.balance_component_key,
        total_target=payload.total_target, total_tolerance=payload.total_tolerance, max_component_count=payload.max_component_count,
        candidate_budget=payload.candidate_budget, maximum_enumeration=payload.maximum_enumeration, notes=payload.notes,
        active=False, checksum="pending", metadata_json=payload.metadata,
    )
    db.add(row); db.flush()
    for component_rule in payload.component_rules:
        values = component_rule.model_dump(mode="json"); metadata = values.pop("metadata")
        db.add(SearchSpaceComponentRule(search_space_id=row.id, **values, metadata_json=metadata))
    for process_rule in payload.process_rules:
        values = process_rule.model_dump(mode="json"); metadata = values.pop("metadata")
        db.add(SearchSpaceProcessRule(search_space_id=row.id, **values, metadata_json=metadata))
    db.flush(); db.refresh(row, ["component_rules", "process_rules"])
    row.checksum = search_space_checksum(row)
    db.commit()
    return get_search_space(db, row.id)


@router.get("/replacement-projects/{project_id}/search-spaces", response_model=list[SearchSpaceOut])
def list_search_spaces(project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    return db.query(CandidateSearchSpace).options(
        selectinload(CandidateSearchSpace.component_rules), selectinload(CandidateSearchSpace.process_rules)
    ).filter_by(project_id=project.id, organisation_id=project.organisation_id).order_by(CandidateSearchSpace.version.desc()).all()


@router.get("/replacement-projects/{project_id}/search-spaces/{search_space_id}", response_model=SearchSpaceOut)
def get_search_space_route(project_id: str, search_space_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    return _scoped_search_space(db, project, search_space_id)


@router.post("/replacement-projects/{project_id}/search-spaces/{search_space_id}/validate", response_model=SearchSpaceValidationOut)
def validate_search_space_route(project_id: str, search_space_id: str, strategy_key: str | None = Query(default=None), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    row = _scoped_search_space(db, project, search_space_id)
    return validate_search_space(db, row, strategy_key)


@router.post("/replacement-projects/{project_id}/search-spaces/{search_space_id}/activate", response_model=SearchSpaceOut)
def activate_search_space(project_id: str, search_space_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    row = _scoped_search_space(db, project, search_space_id)
    validation = validate_search_space(db, row)
    if not validation["valid"]:
        raise HTTPException(422, {"code": "INVALID_SEARCH_SPACE", "issues": validation["issues"]})
    db.query(CandidateSearchSpace).filter_by(project_id=project.id).update({CandidateSearchSpace.active: False})
    row.active = True; db.commit()
    return get_search_space(db, row.id)


@router.post("/replacement-projects/{project_id}/search-spaces/{search_space_id}/clone", response_model=SearchSpaceOut, status_code=201)
def clone_search_space(project_id: str, search_space_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id); source = _scoped_search_space(db, project, search_space_id)
    payload = SearchSpaceCreate(
        material_family=source.material_family, amount_basis=source.amount_basis, balance_component_key=source.balance_component_key,
        total_target=source.total_target, total_tolerance=source.total_tolerance, max_component_count=source.max_component_count,
        candidate_budget=source.candidate_budget, maximum_enumeration=source.maximum_enumeration, notes=source.notes,
        component_rules=[SearchSpaceComponentRuleIn(
            baseline_component_id=r.baseline_component_id, component_key=r.component_key, display_name=r.display_name,
            role=r.role, locked=r.locked, mutable=r.mutable, required=r.required, prohibited=r.prohibited,
            min_amount=r.min_amount, max_amount=r.max_amount, step_amount=r.step_amount, amount_unit=r.amount_unit,
            amount_basis=r.amount_basis, sequence=r.sequence, metadata=r.metadata_json,
        ) for r in source.component_rules],
        process_rules=[SearchSpaceProcessRuleIn(
            parameter_key=r.parameter_key, display_name=r.display_name, min_value=r.min_value, max_value=r.max_value,
            step_value=r.step_value, unit=r.unit, locked=r.locked, metadata=r.metadata_json,
        ) for r in source.process_rules],
        metadata={**source.metadata_json, "cloned_from": source.id},
    )
    return create_search_space(project_id, payload, project.organisation_id, db)


@router.post("/replacement-projects/{project_id}/substitution-rules", response_model=SubstitutionRuleOut, status_code=201)
def create_substitution_rule(project_id: str, payload: SubstitutionRuleCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    if payload.evidence_id and not db.get(__import__('app.models.entities', fromlist=['Evidence']).Evidence, payload.evidence_id):
        raise HTTPException(422, "Evidence not found")
    row = SubstitutionRule(organisation_id=project.organisation_id, project_id=project.id, **payload.model_dump(mode="json"))
    db.add(row); db.commit(); db.refresh(row); return row


@router.get("/replacement-projects/{project_id}/substitution-rules", response_model=list[SubstitutionRuleOut])
def list_substitution_rules(project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    return db.query(SubstitutionRule).filter(SubstitutionRule.organisation_id == project.organisation_id, or_(SubstitutionRule.project_id == project.id, SubstitutionRule.project_id.is_(None))).order_by(SubstitutionRule.status, SubstitutionRule.source_component_key).all()


@router.post("/substitution-rules/{rule_id}/{action}", response_model=SubstitutionRuleOut)
def set_substitution_rule_status(rule_id: str, action: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if action not in {"approve", "disable", "draft"}: raise HTTPException(404, "Unknown rule action")
    if not organisation_id:
        raise HTTPException(404, "Substitution rule not found")
    row = db.query(SubstitutionRule).filter(SubstitutionRule.id == rule_id).one_or_none()
    if not row or row.organisation_id != organisation_id: raise HTTPException(404, "Substitution rule not found")
    row.status = {"approve": "approved", "disable": "disabled", "draft": "draft"}[action]
    row.version += 1; db.commit(); db.refresh(row); return row


@router.post("/replacement-projects/{project_id}/generation-runs/preview", response_model=GenerationPreviewOut)
def generation_preview(project_id: str, payload: GenerationPreviewRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id); space = _scoped_search_space(db, project, payload.search_space_id)
    try: return preview_generation(db, project, space, payload.strategy_key, payload.random_seed, payload.candidate_budget, payload.configuration)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.post("/replacement-projects/{project_id}/generation-runs", response_model=GenerationRunOut, status_code=201)
def generation_run(project_id: str, payload: GenerationRunCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id); space = _scoped_search_space(db, project, payload.search_space_id)
    try: return execute_generation(db, project, space, payload.strategy_key, payload.random_seed, payload.candidate_budget, payload.configuration, payload.created_by)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/replacement-projects/{project_id}/generation-runs", response_model=list[GenerationRunOut])
def generation_runs(project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    return db.query(GenerationRun).filter_by(project_id=project.id, organisation_id=project.organisation_id).order_by(GenerationRun.created_at.desc()).limit(100).all()


@router.get("/generation-runs/{run_id}", response_model=GenerationRunOut)
def get_generation_run(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Generation run not found")
    row = db.query(GenerationRun).filter(GenerationRun.id == run_id).one_or_none()
    if not row or row.organisation_id != organisation_id: raise HTTPException(404, "Generation run not found")
    return row


@router.get("/generation-runs/{run_id}/candidates", response_model=CandidatePage)
def generation_run_candidates(run_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Generation run not found")
    run = db.query(GenerationRun).filter_by(id=run_id).one_or_none()
    if not run or run.organisation_id != organisation_id: raise HTTPException(404, "Generation run not found")
    query = db.query(GenerationRunResult).filter_by(generation_run_id=run.id)
    total = query.count(); rows = query.order_by(GenerationRunResult.sequence).offset(offset).limit(limit).all()
    candidate_ids = [r.candidate_id for r in rows if r.candidate_id]
    candidates = db.query(Candidate).options(selectinload(Candidate.material), selectinload(Candidate.hypothesis).selectinload(CandidateHypothesis.changes)).filter(Candidate.id.in_(candidate_ids)).all() if candidate_ids else []
    by_id = {c.id: c for c in candidates}
    run_project = db.get(ReplacementProject, run.project_id)
    run_constraint_count = len(run_project.constraints) if run_project else 0
    items = []
    for result in rows:
        candidate = by_id.get(result.candidate_id) if result.candidate_id else None
        if not candidate: continue
        display = _candidate_display(candidate, known_posture="KNOWN EVIDENCE — missing properties remain UNKNOWN")
        name, posture, structural, fp, generation_id = display.name, display.posture, display.structural_validity, display.fingerprint, display.generation_run_id
        matrix = result.metadata_json.get("evidence_matrix", {}) if result.metadata_json else {}
        items.append(CandidateListItem(
            id=candidate.id, project_id=candidate.project_id, candidate_kind=candidate.candidate_kind, material_id=candidate.material_id, hypothesis_id=candidate.hypothesis_id,
            display_name=name, candidate_source=candidate.candidate_source, status=candidate.status, structural_validity=structural,
            deterministic_fingerprint=fp or result.candidate_fingerprint, generation_run_id=generation_id or run.id, evidence_posture=posture,
            change_count=display.change_count,
            hard_passed=matrix.get("hard_constraints_known_pass", 0), hard_failed=matrix.get("hard_constraints_known_fail", 0),
            hard_unknown=matrix.get("hard_constraints_unknown", run_constraint_count if candidate.candidate_kind == "hypothesis" else 0),
            evidence_completeness=(matrix.get("evidence_coverage", 0) / max(run_constraint_count, 1)) if matrix else 0.0,
            scientific_conflicts=matrix.get("scientific_conflicts", 0), created_at=candidate.created_at,
        ))
    return CandidatePage(items=items, total=total, offset=offset, limit=limit)


@router.get("/replacement-projects/{project_id}/candidate-lab", response_model=CandidatePage)
def candidate_lab(project_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    query = db.query(Candidate).options(
        selectinload(Candidate.material).selectinload(Material.observations),
        selectinload(Candidate.hypothesis).selectinload(CandidateHypothesis.changes),
    ).filter_by(project_id=project.id)
    total = query.count(); candidates = query.order_by(Candidate.created_at, Candidate.id).offset(offset).limit(limit).all()
    known_ids = [c.material_id for c in candidates if c.candidate_kind == "known_material" and c.material_id]
    selection_context = build_selection_context(db, [project.baseline_material_id, *known_ids]) if known_ids else build_selection_context(db, [project.baseline_material_id])
    hard_constraints = [c for c in project.constraints if c.hard_or_soft == "hard"]
    known_matrices = {}
    for known in candidates:
        known_material = known.material
        if known.candidate_kind != "known_material" or known_material is None:
            continue
        conflict_keys = {x["property_key"] for x in detect_conflicts_from_observations(known_material.observations)}
        evaluated = [evaluate_constraint(db, known_material, constraint, selection_context.definitions_by_key, selection_context, conflict_keys) for constraint in hard_constraints]
        known_matrices[known.id] = {
            "passed": sum(x["status"] == "PASS" for x in evaluated),
            "failed": sum(x["status"] == "FAIL" for x in evaluated),
            "unknown": sum(x["status"] == "UNKNOWN" for x in evaluated),
            "coverage": sum(x["status"] != "UNKNOWN" for x in evaluated) / max(len(hard_constraints), 1),
            "conflicts": len(conflict_keys),
        }
    items = []
    for candidate in candidates:
        display = _candidate_display(candidate, known_posture="KNOWN EVIDENCE — condition-aware selection applies")
        name, posture, structural, fp, generation_id = display.name, display.posture, display.structural_validity, display.fingerprint, display.generation_run_id
        if candidate.candidate_kind == "known_material":
            matrix = known_matrices[candidate.id]
            hard_passed, hard_failed, hard_unknown = matrix["passed"], matrix["failed"], matrix["unknown"]
            completeness = matrix["coverage"]
            conflicts = matrix["conflicts"]
            change_count = 0
        else:
            hard_passed = hard_failed = conflicts = 0
            hard_unknown = len(project.constraints)
            completeness = 0.0
            change_count = display.change_count
        items.append(CandidateListItem(
            id=candidate.id, project_id=candidate.project_id, candidate_kind=candidate.candidate_kind, material_id=candidate.material_id, hypothesis_id=candidate.hypothesis_id,
            display_name=name, candidate_source=candidate.candidate_source, status=candidate.status, structural_validity=structural, deterministic_fingerprint=fp,
            generation_run_id=generation_id, evidence_posture=posture, change_count=change_count, hard_passed=hard_passed, hard_failed=hard_failed,
            hard_unknown=hard_unknown, evidence_completeness=completeness, scientific_conflicts=conflicts, created_at=candidate.created_at,
        ))
    return CandidatePage(items=items, total=total, offset=offset, limit=limit)


@router.post("/replacement-projects/{project_id}/hypotheses/manual", response_model=CandidateHypothesisOut, status_code=201)
def manual_hypothesis(project_id: str, payload: ManualHypothesisCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _scoped_project(db, project_id, organisation_id)
    try:
        hypothesis, _, _ = create_manual_hypothesis(db, project, payload.display_label, payload.material_family,
            [x.model_dump(mode="json") for x in payload.components], [x.model_dump(mode="json") for x in payload.process_parameters], payload.notes)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    return _hypothesis_query(db).filter_by(id=hypothesis.id).one()


@router.get("/candidate-hypotheses/{hypothesis_id}", response_model=CandidateHypothesisOut)
def get_hypothesis(hypothesis_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Hypothesis not found")
    row = _hypothesis_query(db).filter(CandidateHypothesis.id == hypothesis_id).one_or_none()
    if not row or row.organisation_id != organisation_id: raise HTTPException(404, "Hypothesis not found")
    return row


@router.get("/candidate-hypotheses/{hypothesis_id}/lineage", response_model=list[LineageEdgeOut])
def hypothesis_lineage(hypothesis_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Hypothesis not found")
    hypothesis = db.get(CandidateHypothesis, hypothesis_id)
    if not hypothesis or hypothesis.organisation_id != organisation_id: raise HTTPException(404, "Hypothesis not found")
    return db.query(CandidateLineageEdge).filter_by(child_hypothesis_id=hypothesis.id).order_by(CandidateLineageEdge.sequence).all()


@router.post("/candidate-hypotheses/{hypothesis_id}/status", response_model=CandidateHypothesisOut)
def set_hypothesis_status(hypothesis_id: str, status: str = Query(pattern="^(accepted_for_screening|rejected|archived|proposed)$"), reason: str | None = Query(default=None, max_length=1000), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Hypothesis not found")
    hypothesis = db.get(CandidateHypothesis, hypothesis_id)
    if not hypothesis or hypothesis.organisation_id != organisation_id: raise HTTPException(404, "Hypothesis not found")
    if status == "accepted_for_screening" and hypothesis.structural_validity != "valid": raise HTTPException(422, "Structurally invalid hypothesis cannot be accepted for screening")
    hypothesis.status = status
    if status == "rejected" and reason: hypothesis.rejection_reason = reason
    candidate = db.query(Candidate).filter_by(project_id=hypothesis.project_id, hypothesis_id=hypothesis.id).one_or_none()
    if candidate: candidate.status = "accepted" if status == "accepted_for_screening" else status
    db.commit(); return _hypothesis_query(db).filter_by(id=hypothesis.id).one()
