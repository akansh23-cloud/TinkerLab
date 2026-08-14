from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    CampaignConstraintModelPolicy,
    CampaignIteration,
    CampaignObjective,
    CandidateHypothesis,
    OptimizationDecisionRecord,
    ParetoFrontSnapshot,
    ReplacementProject,
    VirtualCandidateEvaluation,
    VirtualExperimentCampaign,
)
from app.schemas.experiments import (
    CampaignIterationOut,
    CampaignPreviewOut,
    CampaignRunRequest,
    CampaignRunResult,
    DecisionRecordOut,
    EvaluationPage,
    ParetoFrontOut,
    VirtualCampaignCreate,
    VirtualCampaignOut,
    VirtualCandidateEvaluationOut,
)
from app.services.experiments import (
    POLICIES,
    campaign_reproducibility_envelope,
    create_campaign,
    evaluations_page,
    execute_iteration,
    final_front_ids,
    preview_campaign,
    run_campaign,
    validate_campaign,
)

router = APIRouter(tags=["virtual-experiments"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _project(db: Session, project_id: str, organisation_id: str | None) -> ReplacementProject:
    org = _org(organisation_id)
    row = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
    ).filter(ReplacementProject.id == project_id, ReplacementProject.organisation_id == org).one_or_none()
    if not row:
        raise HTTPException(404, "Project not found")
    return row


def _campaign(db: Session, campaign_id: str, organisation_id: str | None) -> VirtualExperimentCampaign:
    org = _org(organisation_id)
    row = db.query(VirtualExperimentCampaign).filter(
        VirtualExperimentCampaign.id == campaign_id,
        VirtualExperimentCampaign.organisation_id == org,
    ).one_or_none()
    if not row:
        raise HTTPException(404, "Virtual campaign not found")
    return row


def _iteration(db: Session, iteration_id: str, organisation_id: str | None) -> CampaignIteration:
    org = _org(organisation_id)
    row = db.query(CampaignIteration).join(VirtualExperimentCampaign).filter(
        CampaignIteration.id == iteration_id,
        VirtualExperimentCampaign.organisation_id == org,
    ).one_or_none()
    if not row:
        raise HTTPException(404, "Campaign iteration not found")
    return row


@router.get("/virtual-experiment-policies")
def policy_list():
    return [{
        "key": p.key, "version": p.version, "deterministic": p.deterministic,
        "min_objectives": p.min_objectives, "max_objectives": p.max_objectives,
        "uncertainty_semantics": p.uncertainty_semantics, "unknown_handling": p.unknown_handling,
        "maximum_safe_candidate_pool": p.maximum_safe_candidate_pool,
    } for p in sorted(POLICIES.values(), key=lambda x: x.key)]


@router.post("/replacement-projects/{project_id}/virtual-campaigns", response_model=VirtualCampaignOut, status_code=201)
def create_virtual_campaign(project_id: str, payload: VirtualCampaignCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _project(db, project_id, organisation_id)
    try:
        return create_campaign(db, project, payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/replacement-projects/{project_id}/virtual-campaigns", response_model=list[VirtualCampaignOut])
def list_virtual_campaigns(project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    project = _project(db, project_id, organisation_id)
    return db.query(VirtualExperimentCampaign).filter_by(project_id=project.id, organisation_id=project.organisation_id).order_by(VirtualExperimentCampaign.created_at.desc()).all()


@router.get("/virtual-campaigns/{campaign_id}")
def get_virtual_campaign(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    objectives = db.query(CampaignObjective).filter_by(campaign_id=row.id).order_by(CampaignObjective.sequence).all()
    constraints = db.query(CampaignConstraintModelPolicy).filter_by(campaign_id=row.id).order_by(CampaignConstraintModelPolicy.constraint_id).all()
    iterations = db.query(CampaignIteration).filter_by(campaign_id=row.id).order_by(CampaignIteration.iteration_number).all()
    return {
        "campaign": VirtualCampaignOut.model_validate(row),
        "objectives": [{
            "id": o.id, "property_key": o.property_key, "direction": o.direction, "weight": o.weight, "priority": o.priority,
            "target_value": o.target_value, "target_unit": o.target_unit, "model_version_id": o.model_version_id,
            "evaluation_mode": o.evaluation_mode, "sequence": o.sequence, "metadata": o.metadata_json,
        } for o in objectives],
        "constraint_policies": [{
            "id": c.id, "constraint_id": c.constraint_id, "model_version_id": c.model_version_id,
            "allowed_value_origin": c.allowed_value_origin, "unknown_handling": c.unknown_handling,
            "condition_mapping": c.condition_mapping, "enabled": c.enabled, "metadata": c.metadata_json,
        } for c in constraints],
        "iterations": [CampaignIterationOut.model_validate(i) for i in iterations],
        "warning": "Virtual evaluations are model-based. They are not physical experiments or physics simulations.",
    }


@router.post("/virtual-campaigns/{campaign_id}/validate")
def validate_virtual_campaign(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    issues = validate_campaign(db, row)
    return {"valid": not any(i["severity"] == "error" for i in issues), "issues": issues}


@router.post("/virtual-campaigns/{campaign_id}/preview", response_model=CampaignPreviewOut)
def preview_virtual_campaign(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    return preview_campaign(db, row)


@router.post("/virtual-campaigns/{campaign_id}/iterations", response_model=CampaignIterationOut, status_code=201)
def execute_virtual_iteration(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    if row.status in {"completed", "cancelled", "failed"}:
        raise HTTPException(409, "Completed/cancelled/failed campaign cannot be extended; clone configuration instead")
    previous = db.query(CampaignIteration).filter_by(campaign_id=row.id).order_by(CampaignIteration.iteration_number.desc()).first()
    pool = list(previous.metadata_json.get("created_child_candidate_ids") or []) if previous else None
    if previous and previous.stop_signal:
        raise HTTPException(409, f"Campaign has explicit stop signal: {previous.stop_reason}")
    try:
        return execute_iteration(db, row, next_pool_ids=pool or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/virtual-campaigns/{campaign_id}/run", response_model=CampaignRunResult)
def execute_virtual_campaign(campaign_id: str, payload: CampaignRunRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    try:
        iterations = run_campaign(db, row, payload.max_iterations)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return CampaignRunResult(campaign=VirtualCampaignOut.model_validate(row), iterations=[CampaignIterationOut.model_validate(i) for i in iterations], final_front_candidate_ids=final_front_ids(db, row))


@router.post("/virtual-campaigns/{campaign_id}/cancel", response_model=VirtualCampaignOut)
def cancel_virtual_campaign(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    if row.status in {"completed", "cancelled"}:
        return row
    row.status = "cancelled"; row.stop_reason = "user_cancellation"
    from app.services.experiments import now_utc
    row.completed_at = now_utc(); db.commit(); db.refresh(row); return row


@router.post("/virtual-campaigns/{campaign_id}/clone", response_model=VirtualCampaignOut, status_code=201)
def clone_virtual_campaign(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    source = _campaign(db, campaign_id, organisation_id)
    objectives = db.query(CampaignObjective).filter_by(campaign_id=source.id).order_by(CampaignObjective.sequence).all()
    policies = db.query(CampaignConstraintModelPolicy).filter_by(campaign_id=source.id).all()
    project = _project(db, source.project_id, organisation_id)
    payload = {
        "name": f"{source.name} — clone", "description": source.description, "search_space_id": source.search_space_id,
        "policy_key": source.policy_key, "random_seed": source.random_seed, "max_iterations": source.max_iterations,
        "max_total_new_candidates": source.max_total_new_candidates, "max_candidates_per_iteration": source.max_candidates_per_iteration,
        "max_parents_per_iteration": source.max_parents_per_iteration, "created_by": source.created_by,
        "objectives": [{"property_key": o.property_key, "direction": o.direction, "weight": o.weight, "priority": o.priority, "target_value": o.target_value, "target_unit": o.target_unit, "model_version_id": o.model_version_id, "evaluation_mode": o.evaluation_mode, "metadata": o.metadata_json} for o in objectives],
        "constraint_policies": [{"constraint_id": p.constraint_id, "model_version_id": p.model_version_id, "allowed_value_origin": p.allowed_value_origin, "unknown_handling": p.unknown_handling, "condition_mapping": p.condition_mapping, "enabled": p.enabled, "metadata": p.metadata_json} for p in policies],
        "initial_candidate_ids": source.metadata_json.get("initial_candidate_ids") or [], "include_known_candidates": source.metadata_json.get("include_known_candidates", True),
        "exploration_enabled": source.metadata_json.get("exploration_enabled", True), "mutation_types": source.metadata_json.get("mutation_types") or [],
        "convergence_unchanged_iterations": source.metadata_json.get("convergence_unchanged_iterations"), "metadata": {"cloned_from": source.id},
    }
    try:
        return create_campaign(db, project, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/campaign-iterations/{iteration_id}", response_model=CampaignIterationOut)
def get_iteration(iteration_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return _iteration(db, iteration_id, organisation_id)


@router.get("/campaign-iterations/{iteration_id}/evaluations", response_model=EvaluationPage)
def iteration_evaluations(iteration_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _iteration(db, iteration_id, organisation_id)
    rows, total = evaluations_page(db, iteration_id, offset, limit)
    return EvaluationPage(items=[VirtualCandidateEvaluationOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit)


@router.get("/campaign-iterations/{iteration_id}/pareto", response_model=list[ParetoFrontOut])
def iteration_pareto(iteration_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _iteration(db, iteration_id, organisation_id)
    return db.query(ParetoFrontSnapshot).filter_by(campaign_iteration_id=iteration_id).order_by(ParetoFrontSnapshot.front_number).all()


@router.get("/campaign-iterations/{iteration_id}/decisions", response_model=list[DecisionRecordOut])
def iteration_decisions(iteration_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _iteration(db, iteration_id, organisation_id)
    return db.query(OptimizationDecisionRecord).filter_by(campaign_iteration_id=iteration_id).order_by(OptimizationDecisionRecord.sequence).all()


@router.get("/virtual-campaigns/{campaign_id}/reproducibility")
def campaign_reproducibility(campaign_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = _campaign(db, campaign_id, organisation_id)
    return campaign_reproducibility_envelope(db, row)


@router.get("/candidate-hypotheses/{hypothesis_id}/virtual-campaign-history")
def hypothesis_campaign_history(hypothesis_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _org(organisation_id)
    hypothesis = db.query(CandidateHypothesis).filter_by(id=hypothesis_id, organisation_id=org).one_or_none()
    if not hypothesis:
        raise HTTPException(404, "Hypothesis not found")
    rows = db.query(VirtualCandidateEvaluation, CampaignIteration, VirtualExperimentCampaign).join(
        CampaignIteration, CampaignIteration.id == VirtualCandidateEvaluation.campaign_iteration_id
    ).join(VirtualExperimentCampaign, VirtualExperimentCampaign.id == CampaignIteration.campaign_id).filter(
        VirtualCandidateEvaluation.hypothesis_id == hypothesis_id,
        VirtualExperimentCampaign.organisation_id == org,
    ).order_by(VirtualExperimentCampaign.created_at, CampaignIteration.iteration_number).all()
    return [{
        "campaign_id": campaign.id, "campaign_name": campaign.name, "iteration_id": iteration.id,
        "iteration_number": iteration.iteration_number, "feasibility_class": evaluation.feasibility_class,
        "pareto_rank": evaluation.pareto_rank, "selected_as_parent": evaluation.selected_as_parent,
        "objective_vector": evaluation.objective_vector, "objective_intervals": evaluation.objective_intervals,
        "evaluation_checksum": evaluation.deterministic_evaluation_checksum,
        "scientific_origin": "VIRTUAL EVALUATION — MODEL-BASED",
    } for evaluation, iteration, campaign in rows]
