from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Candidate,
    ExperimentPlan,
    ExperimentProtocol,
    ExperimentProtocolVersion,
    ExperimentRecommendation,
    ExperimentRun,
    FunctionalRequirement,
    Instrument,
    MaterialFunction,
    MaterialPropertyDefinition,
    MaterialRole,
    MaterialState,
    Measurement,
    ProcessingHistory,
    ReplacementProject,
    Sample,
    User,
    ValidationAssessment,
)
from app.schemas.experiments_lab import (
    InstrumentCreate,
    InstrumentOut,
    MeasurementCreate,
    MeasurementOut,
    PlanCreate,
    PlanOut,
    ProtocolCreate,
    ProtocolVersionCreate,
    ProtocolVersionOut,
    RecommendationRequest,
    ReplacementDecisionRequest,
    RunOut,
    SampleCreate,
    SampleOut,
    ValidationRequest,
)
from app.services.experiments_lab import (
    EXPERIMENT_SEPARATION_NOTE,
    MAX_PAGE_SIZE,
    NO_AUTONOMY_NOTE,
    ExperimentError,
    assess_validation,
    create_plan,
    create_protocol_version,
    create_sample,
    detect_conflicting_experiments,
    invalidate_run_measurements,
    materialize_plan_runs,
    recommend_experiments,
    replacement_decision,
    record_measurement,
    transition_run,
    sample_lineage,
)
from app.services.simulation import resolve_target

router = APIRouter(tags=["experiments"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _default_user(db: Session, organisation_id: str) -> str | None:
    user = db.query(User).filter_by(organisation_id=organisation_id).order_by(User.created_at).first()
    return user.id if user else None


def _scoped_role(db: Session, role_id: str, organisation_id: str) -> MaterialRole:
    from app.api.routes.reasoning import _scoped_role as scoped

    return scoped(db, role_id, organisation_id)


def _property(db: Session, key: str) -> MaterialPropertyDefinition:
    definition = db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none()
    if definition is None:
        raise HTTPException(422, f"Unknown property definition '{key}'")
    return definition


# --- protocols ------------------------------------------------------------------------------
@router.post("/experiments/protocols", status_code=201)
def create_protocol(
    payload: ProtocolCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if db.query(ExperimentProtocol).filter_by(organisation_id=org, key=payload.key).one_or_none():
        raise HTTPException(409, f"A protocol with key '{payload.key}' already exists")
    definition = _property(db, payload.property_key) if payload.property_key else None
    row = ExperimentProtocol(
        organisation_id=org, key=payload.key, display_name=payload.display_name,
        objective=payload.objective, property_definition_id=definition.id if definition else None,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "key": row.key}


@router.get("/experiments/protocols")
def list_protocols(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _org(organisation_id)
    rows = (
        db.query(ExperimentProtocol).options(selectinload(ExperimentProtocol.versions))
        .filter_by(organisation_id=org).order_by(ExperimentProtocol.key).all()
    )
    return [
        {"id": p.id, "key": p.key, "display_name": p.display_name, "objective": p.objective,
         "property_definition_id": p.property_definition_id,
         "versions": [
             {"id": v.id, "version": v.version, "protocol_checksum": v.protocol_checksum,
              "is_frozen": v.is_frozen, "superseded_by_id": v.superseded_by_id,
              "replicate_requirement": v.replicate_requirement, "control_requirement": v.control_requirement,
              "created_at": v.created_at}
             for v in sorted(p.versions, key=lambda x: x.created_at)
         ]}
        for p in rows
    ]


@router.post("/experiments/protocols/{protocol_id}/versions", response_model=ProtocolVersionOut, status_code=201)
def add_protocol_version(
    protocol_id: str, payload: ProtocolVersionCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    protocol = db.query(ExperimentProtocol).filter_by(id=protocol_id, organisation_id=org).one_or_none()
    if protocol is None:
        raise HTTPException(404, "Protocol not found")
    try:
        version = create_protocol_version(
            db, protocol=protocol, version=payload.version,
            values=payload.model_dump(exclude={"version"}), created_by=_default_user(db, org),
        )
    except ExperimentError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    db.refresh(version)
    return version


# --- instruments ----------------------------------------------------------------------------
@router.post("/experiments/instruments", response_model=InstrumentOut, status_code=201)
def create_instrument(
    payload: InstrumentCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if db.query(Instrument).filter_by(organisation_id=org, key=payload.key).one_or_none():
        raise HTTPException(409, f"An instrument with key '{payload.key}' already exists")
    row = Instrument(organisation_id=org, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/experiments/instruments", response_model=list[InstrumentOut])
def list_instruments(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return (
        db.query(Instrument).filter_by(organisation_id=_org(organisation_id))
        .order_by(Instrument.key).all()
    )


# --- samples --------------------------------------------------------------------------------
@router.post("/experiments/samples", response_model=SampleOut, status_code=201)
def register_sample(
    payload: SampleCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if db.query(Sample).filter_by(organisation_id=org, sample_code=payload.sample_code).one_or_none():
        raise HTTPException(409, f"A sample with code '{payload.sample_code}' already exists")
    if bool(payload.target_kind) != bool(payload.target_id):
        raise HTTPException(422, "SAMPLE_TARGET_INCOMPLETE: target_kind and target_id must be supplied together")
    if payload.target_kind and payload.target_id:
        if resolve_target(db, payload.target_kind, payload.target_id, org) is None:
            raise HTTPException(404, "Sample target not found")

    if payload.parent_sample_id:
        parent = db.query(Sample).filter_by(id=payload.parent_sample_id, organisation_id=org).one_or_none()
        if parent is None:
            raise HTTPException(404, "Parent sample not found")
        expected_material = payload.target_id if payload.target_kind == "known_material" else None
        expected_hypothesis = payload.target_id if payload.target_kind == "hypothesis" else None
        if payload.target_id and (parent.material_id != expected_material or parent.hypothesis_id != expected_hypothesis):
            raise HTTPException(422, "SAMPLE_TARGET_MISMATCH: parent sample belongs to a different target")

    if payload.candidate_id:
        candidate = db.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise HTTPException(404, "Candidate not found")
        project = db.get(ReplacementProject, candidate.project_id)
        if project is None or project.organisation_id != org:
            raise HTTPException(404, "Candidate not found")
        expected_kind = candidate.candidate_kind
        expected_target = candidate.material_id if expected_kind == "known_material" else candidate.hypothesis_id
        if payload.target_kind != expected_kind or payload.target_id != expected_target:
            raise HTTPException(422, "CANDIDATE_TARGET_MISMATCH: candidate does not reference the sample target")

    if payload.material_state_id:
        state = db.get(MaterialState, payload.material_state_id)
        if state is None or (state.organisation_id not in {None, org}):
            raise HTTPException(404, "Material state not found")
        expected_material = payload.target_id if payload.target_kind == "known_material" else None
        expected_hypothesis = payload.target_id if payload.target_kind == "hypothesis" else None
        if payload.target_id and (state.material_id != expected_material or state.hypothesis_id != expected_hypothesis):
            raise HTTPException(422, "MATERIAL_STATE_TARGET_MISMATCH: state belongs to a different target")

    if payload.processing_history_id:
        history = db.get(ProcessingHistory, payload.processing_history_id)
        if history is None or history.organisation_id not in {None, org}:
            raise HTTPException(404, "Processing history not found")

    values = payload.model_dump(exclude={"target_kind", "target_id"})
    values["organisation_id"] = org
    values["material_id"] = payload.target_id if payload.target_kind == "known_material" else None
    values["hypothesis_id"] = payload.target_id if payload.target_kind == "hypothesis" else None
    values["prepared_by"] = _default_user(db, org)
    sample = create_sample(db, values)
    db.commit()
    db.refresh(sample)
    return sample


@router.get("/experiments/samples", response_model=list[SampleOut])
def list_samples(
    candidate_id: str | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = db.query(Sample).filter_by(organisation_id=_org(organisation_id))
    if candidate_id:
        query = query.filter(Sample.candidate_id == candidate_id)
    return query.order_by(Sample.sample_code).offset(offset).limit(limit).all()


@router.get("/experiments/samples/{sample_id}/lineage")
def get_sample_lineage(
    sample_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    sample = db.query(Sample).filter_by(id=sample_id, organisation_id=org).one_or_none()
    if sample is None:
        raise HTTPException(404, "Sample not found")
    return {
        "sample_id": sample_id, "lineage": sample_lineage(db, sample_id),
        "note": "Every measurement traces to a sample. A specimen with incomplete provenance is "
                "recorded as such, and its measurements are not admitted as evidence.",
    }


# --- plans and runs ---------------------------------------------------------------------------
@router.post("/experiments/plans", status_code=201)
def create_experiment_plan(
    payload: PlanCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    version = db.get(ExperimentProtocolVersion, payload.protocol_version_id)
    if version is None:
        raise HTTPException(404, "Protocol version not found")
    protocol = db.get(ExperimentProtocol, version.protocol_id)
    if protocol is None or protocol.organisation_id != org:
        raise HTTPException(404, "Protocol version not found")
    if payload.project_id:
        project = db.get(ReplacementProject, payload.project_id)
        if not project or project.organisation_id != org:
            raise HTTPException(404, "Project not found")
    if payload.candidate_id:
        candidate = db.get(Candidate, payload.candidate_id)
        candidate_project = db.get(ReplacementProject, candidate.project_id) if candidate else None
        if candidate is None or candidate_project is None or candidate_project.organisation_id != org:
            raise HTTPException(404, "Candidate not found")
        if payload.project_id and candidate.project_id != payload.project_id:
            raise HTTPException(422, "CANDIDATE_PROJECT_MISMATCH: candidate does not belong to the experiment project")
        if payload.sample_id:
            candidate_target = candidate.material_id if candidate.candidate_kind == "known_material" else candidate.hypothesis_id
            sample = db.query(Sample).filter_by(id=payload.sample_id, organisation_id=org).one_or_none()
            if sample is None:
                raise HTTPException(404, "Sample not found")
            sample_target = sample.material_id if candidate.candidate_kind == "known_material" else sample.hypothesis_id
            if candidate_target != sample_target:
                raise HTTPException(422, "SAMPLE_TARGET_MISMATCH: sample does not belong to the selected candidate")
    if payload.role_id:
        _scoped_role(db, payload.role_id, org)
    if payload.requirement_id:
        requirement = db.get(FunctionalRequirement, payload.requirement_id)
        function = db.get(MaterialFunction, requirement.function_id) if requirement else None
        if requirement is None or function is None:
            raise HTTPException(404, "Requirement not found")
        if payload.role_id and function.role_id != payload.role_id:
            raise HTTPException(422, "REQUIREMENT_ROLE_MISMATCH: requirement does not belong to the selected role")
        if protocol.property_definition_id and requirement.property_definition_id and \
                protocol.property_definition_id != requirement.property_definition_id:
            raise HTTPException(422, "PROTOCOL_PROPERTY_MISMATCH: protocol measures a different property")
    if payload.sample_id:
        sample = db.query(Sample).filter_by(id=payload.sample_id, organisation_id=org).one_or_none()
        if sample is None:
            raise HTTPException(404, "Sample not found")
    if payload.instrument_id:
        instrument = db.query(Instrument).filter_by(id=payload.instrument_id, organisation_id=org).one_or_none()
        if instrument is None:
            raise HTTPException(404, "Instrument not found")
        if protocol.property_definition_id:
            definition = db.get(MaterialPropertyDefinition, protocol.property_definition_id)
            if definition and instrument.measures_property_keys and definition.key not in instrument.measures_property_keys:
                raise HTTPException(422, "INSTRUMENT_PROPERTY_MISMATCH: instrument cannot measure the protocol property")
    try:
        plan, runs = create_plan(
            db, organisation_id=org, display_name=payload.display_name, objective=payload.objective,
            design_kind=payload.design_kind, protocol_version=version, factors=payload.factors,
            replicate_count=payload.replicate_count, control_plan=payload.control_plan,
            project_id=payload.project_id, candidate_id=payload.candidate_id, role_id=payload.role_id,
            requirement_id=payload.requirement_id, created_by=_default_user(db, org),
        )
        created = materialize_plan_runs(
            db, plan=plan, runs=runs, run_code_prefix=payload.run_code_prefix,
            sample_id=payload.sample_id, instrument_id=payload.instrument_id,
        )
    except ExperimentError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit()
    return {
        "plan_id": plan.id, "design_kind": plan.design_kind, "planned_run_count": plan.planned_run_count,
        "design_checksum": plan.design_checksum,
        "runs": [{"id": r.id, "run_code": r.run_code, "factor_levels": r.factor_levels,
                  "replicate_index": r.replicate_index} for r in created],
        "autonomy_note": NO_AUTONOMY_NOTE,
    }


@router.get("/experiments/plans", response_model=list[PlanOut])
def list_plans(
    project_id: str | None = None, candidate_id: str | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = db.query(ExperimentPlan).filter_by(organisation_id=_org(organisation_id))
    if project_id:
        query = query.filter(ExperimentPlan.project_id == project_id)
    if candidate_id:
        query = query.filter(ExperimentPlan.candidate_id == candidate_id)
    return query.order_by(ExperimentPlan.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/experiments/runs", response_model=list[RunOut])
def list_runs(
    plan_id: str | None = None, candidate_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = db.query(ExperimentRun).filter_by(organisation_id=_org(organisation_id))
    if plan_id:
        query = query.filter(ExperimentRun.plan_id == plan_id)
    if candidate_id:
        query = query.join(ExperimentPlan, ExperimentRun.plan_id == ExperimentPlan.id).filter(
            ExperimentPlan.candidate_id == candidate_id, ExperimentPlan.organisation_id == _org(organisation_id)
        )
    return query.order_by(ExperimentRun.run_code).offset(offset).limit(limit).all()


def _run_for_org(db: Session, run_id: str, org: str) -> ExperimentRun:
    run = db.query(ExperimentRun).filter_by(id=run_id, organisation_id=org).one_or_none()
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    return run


def _transition_or_422(db: Session, run: ExperimentRun, status: str, reason: str | None = None) -> ExperimentRun:
    try:
        return transition_run(db, run, status, reason=reason)
    except ExperimentError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/experiments/runs/{run_id}/ready", response_model=RunOut)
def ready_run(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    run = _transition_or_422(db, _run_for_org(db, run_id, _org(organisation_id)), "ready")
    db.commit(); db.refresh(run)
    return run


@router.post("/experiments/runs/{run_id}/start", response_model=RunOut)
def start_run(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    run = _transition_or_422(db, _run_for_org(db, run_id, _org(organisation_id)), "running")
    db.commit(); db.refresh(run)
    return run


@router.post("/experiments/runs/{run_id}/complete", response_model=RunOut)
def complete_run(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    run = _transition_or_422(db, _run_for_org(db, run_id, _org(organisation_id)), "completed")
    db.commit(); db.refresh(run)
    return run


@router.post("/experiments/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    run = _transition_or_422(db, _run_for_org(db, run_id, _org(organisation_id)), "cancelled")
    db.commit(); db.refresh(run)
    return run


@router.post("/experiments/runs/{run_id}/invalidate", response_model=RunOut)
def invalidate_run(
    run_id: str, reason: str = Query(min_length=10),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """Invalidate a run; measurements remain visible but cease to be governing evidence."""
    run = _transition_or_422(db, _run_for_org(db, run_id, _org(organisation_id)), "invalidated", reason=reason)
    db.commit(); db.refresh(run)
    return run


# --- measurements -----------------------------------------------------------------------------
@router.post("/experiments/measurements", response_model=MeasurementOut, status_code=201)
def add_measurement(
    payload: MeasurementCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    run = db.query(ExperimentRun).filter_by(id=payload.run_id, organisation_id=org).one_or_none()
    if run is None:
        raise HTTPException(404, "Experiment run not found")
    definition = _property(db, payload.property_key)
    measurement = record_measurement(
        db, organisation_id=org, run=run, property_definition=definition,
        numeric_value=payload.numeric_value, unit=payload.unit, uncertainty=payload.uncertainty,
        uncertainty_type=payload.uncertainty_type, method=payload.method,
        conditions=payload.conditions, replicate_index=payload.replicate_index,
        measured_at=payload.measured_at, notes=payload.notes,
    )
    db.commit()
    db.refresh(measurement)
    return measurement


@router.get("/experiments/measurements", response_model=list[MeasurementOut])
def list_measurements(
    run_id: str | None = None, candidate_id: str | None = None, property_key: str | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    query = db.query(Measurement).filter_by(organisation_id=org)
    if run_id:
        query = query.filter(Measurement.run_id == run_id)
    if candidate_id:
        query = (query.join(ExperimentRun, Measurement.run_id == ExperimentRun.id)
                 .join(ExperimentPlan, ExperimentRun.plan_id == ExperimentPlan.id)
                 .filter(ExperimentPlan.candidate_id == candidate_id,
                         ExperimentPlan.organisation_id == org,
                         ExperimentRun.organisation_id == org))
    if property_key:
        query = query.filter(Measurement.property_definition_id == _property(db, property_key).id)
    return query.order_by(Measurement.created_at).offset(offset).limit(limit).all()


@router.get("/experiments/measurements/conflicts")
def measurement_conflicts(
    property_key: str, target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    from app.services.experiments_lab import accepted_measurements

    measurements = accepted_measurements(
        db, target_kind=target_kind, target_id=target_id,
        property_definition_id=_property(db, property_key).id, organisation_id=org,
    )
    return {
        "property_key": property_key,
        "measurement_count": len(measurements),
        "conflicts": detect_conflicting_experiments(measurements, db=db),
        "note": "Conflicting measurements are both retained with their methods, samples and "
                "conditions visible. The later measurement does not supersede the earlier.",
    }


# --- validation and recommendation ----------------------------------------------------------------
def _resolve_candidate_or_target(db: Session, payload: ValidationRequest, org: str) -> tuple[str | None, str, str, str | None]:
    """Derive scientific target and project from a trusted candidate when candidate_id is supplied."""
    if payload.candidate_id:
        candidate = db.get(Candidate, payload.candidate_id)
        project = db.get(ReplacementProject, candidate.project_id) if candidate else None
        if candidate is None or project is None or project.organisation_id != org:
            raise HTTPException(404, "Candidate not found")
        if payload.project_id and payload.project_id != candidate.project_id:
            raise HTTPException(422, "CANDIDATE_PROJECT_MISMATCH: candidate does not belong to the requested project")
        target_id = candidate.material_id if candidate.candidate_kind == "known_material" else candidate.hypothesis_id
        if not target_id:
            raise HTTPException(422, "CANDIDATE_TARGET_MISMATCH: candidate has no valid scientific target")
        return candidate.id, candidate.candidate_kind, target_id, candidate.project_id
    assert payload.target_kind and payload.target_id
    if resolve_target(db, payload.target_kind, payload.target_id, org) is None:
        raise HTTPException(404, "Target not found")
    return None, payload.target_kind, payload.target_id, payload.project_id


@router.post("/experiments/validation/assess")
def assess_candidate_validation(
    payload: ValidationRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _scoped_role(db, payload.role_id, org)
    candidate_id, target_kind, target_id, project_id = _resolve_candidate_or_target(db, payload, org)
    result = assess_validation(
        db, organisation_id=org, role_id=payload.role_id, target_kind=target_kind,
        target_id=target_id, project_id=project_id, candidate_id=candidate_id, persist=payload.persist,
    )
    db.commit() if payload.persist else db.rollback()
    return result


@router.get("/experiments/validation/assessments")
def list_validation_assessments(
    role_id: str | None = None, target_id: str | None = None, include_superseded: bool = False,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = db.query(ValidationAssessment).filter_by(organisation_id=_org(organisation_id))
    if role_id:
        query = query.filter(ValidationAssessment.role_id == role_id)
    if target_id:
        query = query.filter(ValidationAssessment.target_scientific_id == target_id)
    if not include_superseded:
        query = query.filter(ValidationAssessment.superseded_by_id.is_(None))
    rows = query.order_by(ValidationAssessment.created_at.desc()).limit(MAX_PAGE_SIZE).all()
    return [
        {"id": r.id, "candidate_id": r.candidate_id, "project_id": r.project_id,
         "role_id": r.role_id, "target_kind": r.target_kind,
         "target_scientific_id": r.target_scientific_id, "validation_state": r.validation_state,
         "rationale": r.rationale, "requirement_outcomes": r.requirement_outcomes,
         "experimentally_supported_requirements": r.experimentally_supported_requirements,
         "outstanding_requirements": r.outstanding_requirements,
         "disagreements": r.disagreements, "conflicting_experiments": r.conflicting_experiments,
         "evidence_snapshot": r.evidence_snapshot, "methodology_version": r.methodology_version,
         "assessment_checksum": r.assessment_checksum, "superseded_by_id": r.superseded_by_id,
         "created_at": r.created_at}
        for r in rows
    ]


@router.post("/experiments/replacement-decision")
def get_replacement_decision(
    payload: ReplacementDecisionRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """Return a candidate-centric transparent decision about readiness for the next gate."""
    org = _org(organisation_id)
    _scoped_role(db, payload.role_id, org)
    candidate = db.get(Candidate, payload.candidate_id)
    project = db.get(ReplacementProject, candidate.project_id) if candidate else None
    if candidate is None or project is None or project.organisation_id != org:
        raise HTTPException(404, "Candidate not found")
    target_id = candidate.material_id if candidate.candidate_kind == "known_material" else candidate.hypothesis_id
    if not target_id:
        raise HTTPException(422, "CANDIDATE_TARGET_MISMATCH: candidate has no valid scientific target")
    result = replacement_decision(
        db, organisation_id=org, role_id=payload.role_id, candidate_id=candidate.id,
        target_kind=candidate.candidate_kind, target_id=target_id, project_id=candidate.project_id,
        persist_validation=payload.persist_validation,
    )
    db.commit() if payload.persist_validation else db.rollback()
    return result


@router.post("/experiments/recommendations")
def get_recommendations(
    payload: RecommendationRequest,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    _scoped_role(db, payload.role_id, org)
    candidate_id, target_kind, target_id, project_id = _resolve_candidate_or_target(db, payload, org)
    result = recommend_experiments(
        db, organisation_id=org, role_id=payload.role_id, target_kind=target_kind,
        target_id=target_id, project_id=project_id, persist=payload.persist,
    )
    result["candidate_id"] = candidate_id
    db.commit() if payload.persist else db.rollback()
    return result


@router.get("/experiments/recommendations")
def list_recommendations(
    role_id: str | None = None, status: str = "open",
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = db.query(ExperimentRecommendation).filter_by(organisation_id=_org(organisation_id))
    if role_id:
        query = query.filter(ExperimentRecommendation.role_id == role_id)
    if status:
        query = query.filter(ExperimentRecommendation.status == status)
    rows = query.order_by(ExperimentRecommendation.priority_score.desc()).limit(MAX_PAGE_SIZE).all()
    return [
        {"id": r.id, "requirement_id": r.requirement_id, "unresolved_status": r.unresolved_status,
         "why_it_matters": r.why_it_matters, "proposed_measurement": r.proposed_measurement,
         "priority_score": r.priority_score, "priority_factors": r.priority_factors,
         "priority_methodology": r.priority_methodology, "status": r.status}
        for r in rows
    ]


@router.get("/experiments/policy")
def experiment_policy():
    return {
        "separation_note": EXPERIMENT_SEPARATION_NOTE,
        "autonomy_note": NO_AUTONOMY_NOTE,
        "implemented_designs": ["single_run", "one_factor", "full_factorial", "parameter_sweep"],
        "not_implemented_designs": [
            "response_surface_methods", "bayesian_optimization", "active_learning",
        ],
        "validation_states": [
            "computational_only", "simulation_supported", "experiment_recommended",
            "experiment_pending", "experiment_in_progress", "partially_validated",
            "experimentally_supported", "experimentally_contradicted",
            "conflicting_experiments", "inconclusive",
        ],
        "integration_boundaries": [
            "manual_entry", "lims", "instrument_api", "robotic_platform", "contract_laboratory",
        ],
        "integration_note": (
            "Only manual entry is implemented. The other integration kinds are declared boundaries "
            "for future adapters; no laboratory system, instrument API or robotic platform is "
            "connected, and none is simulated."
        ),
    }
