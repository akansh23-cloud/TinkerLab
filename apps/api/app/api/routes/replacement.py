"""Phase 10 — Replacement decision API.

Every endpoint here derives the organisation from the request scope and refuses to trust a
frontend-supplied organisation identifier. A resource belonging to another tenant is reported as
404, not 403: telling a caller that a program exists but is forbidden already leaks the fact that
another organisation is running a study.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.domain.enums import (
    OPEN_ACTION_STATUSES,
    ProgramEventKind,
    RequirementApprovalStatus,
    RequirementCriticality,
    RequirementOrigin,
    ScientificActionStatus,
)
from app.models.entities import (
    ConvergenceAssessment,
    DecisionPolicy,
    FunctionalRequirement,
    MaterialFunction,
    ReplacementProgram,
    ReplacementProgramSnapshot,
    ReplacementRecommendation,
    ScientificAction,
    TechnicalDossier,
)
from app.schemas.replacement import (
    ActionTransitionRequest,
    ConvergenceAssessmentOut,
    DecisionPolicyCreate,
    DecisionPolicyOut,
    DossierCreateRequest,
    EvidenceEventRequest,
    ProgramSnapshotOut,
    RecommendationCreateRequest,
    RecomputeRequest,
    ReplacementProgramCreate,
    ReplacementProgramOut,
    ReplacementProgramUpdate,
    ReplacementRecommendationOut,
    RequirementGateUpdate,
    ScientificActionOut,
    SnapshotCreateRequest,
    TechnicalDossierOut,
    TimelineEventOut,
)
from app.services.replacement.actions import action_out, compute_actions, persist_actions
from app.services.replacement.context import PortfolioContext, PortfolioError
from app.services.replacement.convergence import (
    assess_convergence,
    latest_convergence,
    persist_convergence,
)
from app.services.replacement.coverage import (
    coverage_for_candidate,
    coverage_summary,
    decision_matrix,
)
from app.services.replacement.dossier import create_snapshot, generate_dossier
from app.services.replacement.gaps import gaps_for_candidate, program_gaps
from app.services.replacement.policy import create_policy, ensure_default_policy, policy_summary
from app.services.replacement.portfolio import candidate_decision_state, portfolio_board
from app.services.replacement.programs import (
    ProgramError,
    create_program,
    emit_evidence_event,
    program_header,
    record_event,
    refresh_program_state,
    resolve_program_state,
    scoped_program,
    set_program_override,
    timeline,
    validate_program_references,
)
from app.services.replacement.ranking import rank_candidates, sensitivity_analysis
from app.services.replacement.recommendation import (
    build_recommendation,
    explain_candidate,
    explain_recommendation_change,
    generate_recommendation,
)

router = APIRouter(tags=["replacement"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _program(db: Session, program_id: str, organisation_id: str | None) -> ReplacementProgram:
    program = scoped_program(db, program_id, _org(organisation_id))
    if program is None:
        raise HTTPException(404, "Replacement program not found")
    return program


def _context(db: Session, program: ReplacementProgram, candidate_ids: list[str] | None = None) -> PortfolioContext:
    try:
        return PortfolioContext(db, program, candidate_ids=candidate_ids)
    except PortfolioError as exc:
        raise HTTPException(409, str(exc)) from exc


def _guard(callable_: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return callable_(*args, **kwargs)
    except PortfolioError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---------------------------------------------------------------------------------------------
# Decision policies
# ---------------------------------------------------------------------------------------------
@router.get("/decision-policies", response_model=list[DecisionPolicyOut])
def list_policies(db: Session = Depends(get_db), organisation_id: str | None = Depends(scope_organisation)):
    org = _org(organisation_id)
    ensure_default_policy(db, organisation_id=org)
    db.commit()
    return (
        db.query(DecisionPolicy)
        .filter(DecisionPolicy.organisation_id == org)
        .order_by(DecisionPolicy.key, DecisionPolicy.version)
        .all()
    )


@router.post("/decision-policies", response_model=DecisionPolicyOut, status_code=201)
def create_decision_policy(
    payload: DecisionPolicyCreate, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    org = _org(organisation_id)
    values = payload.model_dump(exclude_none=True)
    created_by = values.pop("created_by", None)
    row = create_policy(db, organisation_id=org, values=values, created_by=created_by)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------------------------
@router.post("/replacement-programs", response_model=ReplacementProgramOut, status_code=201)
def create_replacement_program(
    payload: ReplacementProgramCreate, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    org = _org(organisation_id)
    values = payload.model_dump()
    created_by = values.pop("created_by", None)
    try:
        row = create_program(db, organisation_id=org, values=values, created_by=created_by)
    except ProgramError as exc:
        raise HTTPException(400, str(exc)) from exc
    refresh_program_state(db, row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/replacement-programs", response_model=list[ReplacementProgramOut])
def list_replacement_programs(
    project_id: str | None = Query(default=None), db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    org = _org(organisation_id)
    query = db.query(ReplacementProgram).filter(ReplacementProgram.organisation_id == org)
    if project_id:
        query = query.filter(ReplacementProgram.project_id == project_id)
    return query.order_by(ReplacementProgram.name, ReplacementProgram.id).all()


@router.get("/replacement-programs/{program_id}")
def get_replacement_program(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    resolved = _guard(resolve_program_state, db, program)
    header = _guard(program_header, db, program)
    db.commit()
    return {
        "program": ReplacementProgramOut.model_validate(program).model_dump(),
        "resolved_state": resolved,
        "header": header,
        "decision_policy": policy_summary(
            ensure_default_policy(db, organisation_id=program.organisation_id)
            if program.decision_policy_id is None
            else db.get(DecisionPolicy, program.decision_policy_id)
        ),
    }


@router.patch("/replacement-programs/{program_id}", response_model=ReplacementProgramOut)
def update_replacement_program(
    program_id: str, payload: ReplacementProgramUpdate, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    values = payload.model_dump(exclude_unset=True)
    override = values.pop("status_override", "__unset__")

    if any(k in values for k in ("role_id", "incumbent_material_id", "incumbent_state_id")):
        try:
            validate_program_references(
                db, organisation_id=program.organisation_id, project_id=program.project_id,
                role_id=values.get("role_id", program.role_id),
                incumbent_material_id=values.get("incumbent_material_id", program.incumbent_material_id),
                incumbent_state_id=values.get("incumbent_state_id", program.incumbent_state_id),
            )
        except ProgramError as exc:
            raise HTTPException(400, str(exc)) from exc

    for key, value in values.items():
        setattr(program, key, value)
    if override != "__unset__":
        try:
            set_program_override(db, program, override=override)
        except ProgramError as exc:
            raise HTTPException(400, str(exc)) from exc
    else:
        _guard(refresh_program_state, db, program)
    db.commit()
    db.refresh(program)
    return program


# ---------------------------------------------------------------------------------------------
# Requirement decision-gate metadata
# ---------------------------------------------------------------------------------------------
@router.patch("/functional-requirements/{requirement_id}/decision-gate")
def update_requirement_gate(
    requirement_id: str, payload: RequirementGateUpdate, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    """Set criticality, origin and approval status on a requirement.

    Approving a requirement is an explicit human act. Nothing in the system flips a PROPOSED
    requirement to ACCEPTED on its own, because that would let automated logic invent the bar it is
    then judged against.
    """
    org = _org(organisation_id)
    requirement = db.get(FunctionalRequirement, requirement_id)
    if requirement is None:
        raise HTTPException(404, "Functional requirement not found")
    function = db.get(MaterialFunction, requirement.function_id)
    programs = (
        db.query(ReplacementProgram)
        .filter(ReplacementProgram.organisation_id == org,
                ReplacementProgram.role_id == (function.role_id if function else None))
        .all()
    )
    if not programs:
        raise HTTPException(404, "Functional requirement not found")

    values = payload.model_dump(exclude_none=True)
    if "criticality" in values and values["criticality"] not in {c.value for c in RequirementCriticality}:
        raise HTTPException(400, "INVALID_CRITICALITY")
    if "requirement_origin" in values and values["requirement_origin"] not in {o.value for o in RequirementOrigin}:
        raise HTTPException(400, "INVALID_REQUIREMENT_ORIGIN")
    if "approval_status" in values and values["approval_status"] not in {s.value for s in RequirementApprovalStatus}:
        raise HTTPException(400, "INVALID_APPROVAL_STATUS")

    for key, value in values.items():
        setattr(requirement, key, value)
    if values.get("approval_status") == RequirementApprovalStatus.ACCEPTED.value:
        requirement.approved_at = datetime.now(UTC)
    requirement.requirement_version = int(requirement.requirement_version or 1) + 1
    db.flush()

    # A requirement change invalidates every conclusion that used the old version, for every program
    # that shares this role.
    for program in programs:
        emit_evidence_event(
            db, program=program, kind=ProgramEventKind.REQUIREMENT_CHANGED,
            summary=f"Requirement '{requirement.key}' decision-gate metadata changed.",
            payload={"requirement_id": requirement.id, "changes": values,
                     "requirement_version": requirement.requirement_version},
        )
    db.commit()
    return {
        "requirement_id": requirement.id, "criticality": requirement.criticality,
        "requirement_origin": requirement.requirement_origin,
        "approval_status": requirement.approval_status,
        "requirement_version": requirement.requirement_version,
        "affected_program_ids": sorted(p.id for p in programs),
    }


# ---------------------------------------------------------------------------------------------
# Portfolio, matrix, coverage, gaps
# ---------------------------------------------------------------------------------------------
@router.get("/replacement-programs/{program_id}/portfolio")
def get_portfolio(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return _guard(portfolio_board, _context(db, program))


@router.get("/replacement-programs/{program_id}/decision-matrix")
def get_decision_matrix(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return _guard(decision_matrix, _context(db, program))


@router.get("/replacement-programs/{program_id}/evidence-gaps")
def get_evidence_gaps(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return _guard(program_gaps, _context(db, program))


@router.get("/replacement-programs/{program_id}/ranking")
def get_ranking(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    ranking = _guard(rank_candidates, context)
    return {**ranking, "sensitivity": _guard(sensitivity_analysis, context)}


@router.get("/replacement-programs/{program_id}/convergence")
def get_convergence(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    payload = _guard(assess_convergence, _context(db, program))
    stored = latest_convergence(db, organisation_id=program.organisation_id, program_id=program.id)
    return {
        **payload,
        "latest_persisted": ConvergenceAssessmentOut.model_validate(stored).model_dump()
        if stored else None,
    }


@router.get("/replacement-programs/{program_id}/header")
def get_header(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    header = _guard(program_header, db, program)
    db.commit()
    return header


# ---------------------------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------------------------
@router.get("/replacement-programs/{program_id}/actions", response_model=list[ScientificActionOut])
def list_actions(
    program_id: str, status: str | None = Query(default=None),
    db: Session = Depends(get_db), organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    query = (
        db.query(ScientificAction)
        .filter(ScientificAction.organisation_id == program.organisation_id,
                ScientificAction.program_id == program.id)
    )
    if status == "open":
        query = query.filter(ScientificAction.status.in_(sorted(OPEN_ACTION_STATUSES)))
    elif status:
        query = query.filter(ScientificAction.status == status)
    return query.order_by(ScientificAction.priority.desc(), ScientificAction.action_signature).all()


@router.post("/replacement-programs/{program_id}/actions/recompute")
def recompute_actions(
    program_id: str, payload: RecomputeRequest | None = None, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    request = payload or RecomputeRequest()
    context = _context(db, program, candidate_ids=request.candidate_ids or None)
    computed = _guard(compute_actions, context)
    changes = {"created": [], "updated": [], "superseded": []}
    if request.persist:
        changes = persist_actions(db, context, computed)
        record_event(
            db, program=program, kind=ProgramEventKind.ACTION_PROPOSED,
            summary=f"Action queue recomputed: {len(changes['created'])} new, "
                    f"{len(changes['superseded'])} superseded.",
            payload=changes,
        )
        db.commit()
    return {**computed, "changes": changes}


@router.post("/replacement-programs/{program_id}/actions/{action_id}/transition")
def transition_action(
    program_id: str, action_id: str, payload: ActionTransitionRequest,
    db: Session = Depends(get_db), organisation_id: str | None = Depends(scope_organisation),
):
    """Accept, defer, cancel or record progress on a recommended action.

    `execute` marks that an authorized workflow has been started elsewhere. This endpoint never
    launches a simulation or an experiment: expensive or physical work is only ever initiated
    through its own product surface with its own authorization.
    """
    program = _program(db, program_id, organisation_id)
    action = db.get(ScientificAction, action_id)
    if action is None or action.program_id != program.id or action.organisation_id != program.organisation_id:
        raise HTTPException(404, "Scientific action not found")

    transitions = {
        "accept": ScientificActionStatus.READY,
        "defer": ScientificActionStatus.DEFERRED,
        "cancel": ScientificActionStatus.CANCELLED,
        "execute": ScientificActionStatus.RUNNING,
        "complete": ScientificActionStatus.COMPLETED,
        "fail": ScientificActionStatus.FAILED,
    }
    target = transitions[payload.transition]

    if payload.transition == "execute":
        unmet = [
            dep for dep in (action.depends_on or [])
            if db.query(ScientificAction)
            .filter(ScientificAction.program_id == program.id,
                    ScientificAction.action_signature == dep,
                    ScientificAction.status.in_(sorted(OPEN_ACTION_STATUSES)))
            .count() > 0
        ]
        if unmet:
            # Running a dependent step first would produce evidence that cannot be interpreted.
            raise HTTPException(
                409,
                f"ACTION_DEPENDENCIES_UNMET: {len(unmet)} prerequisite action(s) are still open",
            )
        action.started_at = datetime.now(UTC)
    if payload.transition in {"complete", "fail"}:
        action.completed_at = datetime.now(UTC)
    if payload.result_reference:
        action.result_reference = payload.result_reference

    action.status = str(target)
    db.flush()

    event_kind = {
        "accept": ProgramEventKind.ACTION_ACCEPTED,
        "defer": ProgramEventKind.ACTION_DEFERRED,
        "cancel": ProgramEventKind.ACTION_CANCELLED,
        "execute": ProgramEventKind.ACTION_ACCEPTED,
        "complete": ProgramEventKind.ACTION_COMPLETED,
        "fail": ProgramEventKind.ACTION_COMPLETED,
    }[payload.transition]
    record_event(
        db, program=program, kind=event_kind,
        summary=f"Action {action.action_type} moved to {target}."
                + (f" Note: {payload.note}" if payload.note else ""),
        payload={"action_type": action.action_type, "status": str(target)},
        candidate_id=action.candidate_id, requirement_id=action.requirement_id,
        reference_kind="scientific_action", reference_id=action.id,
    )
    if payload.transition == "complete":
        _guard(
            emit_evidence_event, db, program=program, kind=ProgramEventKind.ACTION_COMPLETED,
            summary=f"Completed action {action.action_type}; affected conclusions reassessed.",
            candidate_ids=[action.candidate_id] if action.candidate_id else [],
            reference_kind="scientific_action", reference_id=action.id,
        )
    db.commit()
    db.refresh(action)
    return action_out(action)


# ---------------------------------------------------------------------------------------------
# Candidate-centric endpoints
# ---------------------------------------------------------------------------------------------
@router.get("/replacement-programs/{program_id}/candidates/{candidate_id}/replacement-state")
def get_candidate_state(
    program_id: str, candidate_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    view = context.candidate(candidate_id)
    if view is None:
        raise HTTPException(404, "Candidate not found in this program's portfolio")
    return _guard(candidate_decision_state, context, view)


@router.get("/replacement-programs/{program_id}/candidates/{candidate_id}/evidence-coverage")
def get_candidate_coverage(
    program_id: str, candidate_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    view = context.candidate(candidate_id)
    if view is None:
        raise HTTPException(404, "Candidate not found in this program's portfolio")
    rows = _guard(coverage_for_candidate, context, view)
    return {"candidate_id": candidate_id, "coverage": rows, "summary": coverage_summary(rows)}


@router.get("/replacement-programs/{program_id}/candidates/{candidate_id}/next-action")
def get_candidate_next_action(
    program_id: str, candidate_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    from app.services.replacement.actions import next_actions_for_candidate

    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    view = context.candidate(candidate_id)
    if view is None:
        raise HTTPException(404, "Candidate not found in this program's portfolio")
    state = _guard(candidate_decision_state, context, view)
    actions = _guard(next_actions_for_candidate, context, view, eligibility=state["eligibility"])
    return {"candidate_id": candidate_id, "next_action": actions[0] if actions else None,
            "actions": actions}


@router.get("/replacement-programs/{program_id}/candidates/{candidate_id}/gaps")
def get_candidate_gaps(
    program_id: str, candidate_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    view = context.candidate(candidate_id)
    if view is None:
        raise HTTPException(404, "Candidate not found in this program's portfolio")
    return {"candidate_id": candidate_id, "gaps": _guard(gaps_for_candidate, context, view)}


@router.get("/replacement-programs/{program_id}/candidates/{candidate_id}/explanation")
def get_candidate_explanation(
    program_id: str, candidate_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return _guard(explain_candidate, _context(db, program), candidate_id)


# ---------------------------------------------------------------------------------------------
# Recommendation, snapshot, dossier, timeline
# ---------------------------------------------------------------------------------------------
@router.get("/replacement-programs/{program_id}/recommendation")
def get_recommendation(
    program_id: str, preview: bool = Query(default=False), db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    if preview:
        return _guard(build_recommendation, _context(db, program))
    row = (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == program.id,
                ReplacementRecommendation.organisation_id == program.organisation_id,
                ReplacementRecommendation.superseded_by_id.is_(None))
        .order_by(ReplacementRecommendation.version.desc())
        .first()
    )
    if row is None:
        raise HTTPException(404, "No recommendation has been generated for this program")
    return ReplacementRecommendationOut.model_validate(row).model_dump()


@router.post("/replacement-programs/{program_id}/recommendation", status_code=201)
def post_recommendation(
    program_id: str, payload: RecommendationCreateRequest | None = None,
    db: Session = Depends(get_db), organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    request = payload or RecommendationCreateRequest()
    result = _guard(generate_recommendation, db, program, created_by=request.created_by)
    db.commit()
    return result


@router.get("/replacement-programs/{program_id}/recommendations",
            response_model=list[ReplacementRecommendationOut])
def list_recommendations(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == program.id,
                ReplacementRecommendation.organisation_id == program.organisation_id)
        .order_by(ReplacementRecommendation.version.desc())
        .all()
    )


@router.get("/replacement-programs/{program_id}/decision-deltas")
def get_decision_deltas(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return explain_recommendation_change(
        db, organisation_id=program.organisation_id, program_id=program.id
    )


@router.post("/replacement-programs/{program_id}/snapshot", response_model=ProgramSnapshotOut,
             status_code=201)
def post_snapshot(
    program_id: str, payload: SnapshotCreateRequest | None = None, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    request = payload or SnapshotCreateRequest()
    row = _guard(create_snapshot, db, program, label=request.label, created_by=request.created_by)
    db.commit()
    db.refresh(row)
    return row


@router.get("/replacement-programs/{program_id}/snapshots", response_model=list[ProgramSnapshotOut])
def list_snapshots(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return (
        db.query(ReplacementProgramSnapshot)
        .filter(ReplacementProgramSnapshot.program_id == program.id,
                ReplacementProgramSnapshot.organisation_id == program.organisation_id)
        .order_by(ReplacementProgramSnapshot.created_at.desc(), ReplacementProgramSnapshot.id)
        .all()
    )


@router.post("/replacement-programs/{program_id}/dossier", response_model=TechnicalDossierOut,
             status_code=201)
def post_dossier(
    program_id: str, payload: DossierCreateRequest | None = None, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    request = payload or DossierCreateRequest()
    row = _guard(
        generate_dossier, db, program, candidate_id=request.candidate_id,
        snapshot_id=request.snapshot_id, created_by=request.created_by,
    )
    db.commit()
    db.refresh(row)
    return row


@router.get("/replacement-programs/{program_id}/dossiers", response_model=list[TechnicalDossierOut])
def list_dossiers(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return (
        db.query(TechnicalDossier)
        .filter(TechnicalDossier.program_id == program.id,
                TechnicalDossier.organisation_id == program.organisation_id)
        .order_by(TechnicalDossier.version.desc())
        .all()
    )


@router.get("/replacement-programs/{program_id}/timeline", response_model=list[TimelineEventOut])
def get_timeline(
    program_id: str, candidate_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500), db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return timeline(
        db, organisation_id=program.organisation_id, program_id=program.id,
        candidate_id=candidate_id, limit=limit,
    )


@router.post("/replacement-programs/{program_id}/events")
def post_evidence_event(
    program_id: str, payload: EvidenceEventRequest, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    """Notify the program that upstream evidence changed, triggering scoped reassessment."""
    program = _program(db, program_id, organisation_id)
    known = {kind.value for kind in ProgramEventKind}
    if payload.event_kind not in known:
        raise HTTPException(400, f"UNKNOWN_EVENT_KIND: {payload.event_kind}")

    context = _context(db, program)
    valid_ids = {view.candidate_id for view in context.candidates}
    unknown = [cid for cid in payload.candidate_ids if cid not in valid_ids]
    if unknown:
        # A candidate from another program or tenant must not be able to trigger a recomputation.
        raise HTTPException(404, "Candidate not found in this program's portfolio")

    result = _guard(
        emit_evidence_event, db, program=program, kind=payload.event_kind,
        summary=payload.summary or f"Evidence event: {payload.event_kind}.",
        candidate_ids=payload.candidate_ids, payload=payload.payload,
        reference_kind=payload.reference_kind, reference_id=payload.reference_id,
        actor_user_id=payload.actor_user_id,
    )
    db.commit()
    return result


@router.post("/replacement-programs/{program_id}/reassess")
def post_reassess(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    """Full deterministic recomputation: actions, convergence and program state."""
    program = _program(db, program_id, organisation_id)
    context = _context(db, program)
    changes = persist_actions(db, context, _guard(compute_actions, context))
    payload = _guard(assess_convergence, context)
    row = persist_convergence(db, context, payload)
    resolved = _guard(refresh_program_state, db, program)
    db.commit()
    return {
        "program_id": program.id, "action_changes": changes,
        "convergence": ConvergenceAssessmentOut.model_validate(row).model_dump(),
        "program_state": resolved,
    }


@router.get("/replacement-programs/{program_id}/convergence-history",
            response_model=list[ConvergenceAssessmentOut])
def get_convergence_history(
    program_id: str, db: Session = Depends(get_db),
    organisation_id: str | None = Depends(scope_organisation),
):
    program = _program(db, program_id, organisation_id)
    return (
        db.query(ConvergenceAssessment)
        .filter(ConvergenceAssessment.program_id == program.id,
                ConvergenceAssessment.organisation_id == program.organisation_id)
        .order_by(ConvergenceAssessment.created_at.desc(), ConvergenceAssessment.id)
        .limit(50)
        .all()
    )
