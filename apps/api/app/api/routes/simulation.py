from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    CandidateHypothesis,
    Material,
    MaterialPropertyDefinition,
    ReplacementProject,
    ScientificRepresentation,
    SimulationProvider,
    SimulationSelectionPolicyRecord,
    SimulationWorkflow,
    User,
)
from app.schemas.simulation import (
    RegisteredArtifactOut,
    RepresentationCreate,
    RepresentationDetailOut,
    RepresentationOut,
    RepresentationValidateRequest,
    RepresentationValidationOut,
    RoutePreviewRequest,
    SelectionPolicyCreate,
    SimulationProviderOut,
    SimulationProviderVersionOut,
    SimulationWorkflowOut,
    WorkflowCreateRequest,
    WorkflowDetailOut,
    WorkflowPreviewRequest,
)
from app.services.representations import (
    FORMAT_TO_TYPE,
    RepresentationError,
    representation_checksum,
    supported_formats,
    validate_representation,
)
from app.services.simulation import (
    MAX_PAGE_SIZE,
    approved_artifacts,
    assert_simulation_integrity,
    build_workflow_preview,
    campaign_escalation_targets,
    cancel_workflow,
    create_representation,
    create_workflow,
    execute_workflow,
    method_descriptors,
    preview_routes,
    provider_availability,
    provider_descriptor,
    provider_visible,
    representation_visible,
    representations_for_target,
    require_provider_version,
    select_simulation_value,
    target_simulation_history,
    visible_providers,
    workflow_detail,
    workflow_template_descriptors,
)

router = APIRouter(tags=["simulation"])


def _org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(404, "Resource not found")
    return organisation_id


def _default_user(db: Session, organisation_id: str) -> str:
    user = db.query(User).filter_by(organisation_id=organisation_id).order_by(User.created_at).first()
    if not user:
        raise HTTPException(400, "No user exists in this organisation scope")
    return user.id


# --- representations ---------------------------------------------------------------------------
@router.get("/simulation/representation-formats")
def list_representation_formats():
    return {"formats": supported_formats()}


@router.post("/simulation/representations/validate", response_model=RepresentationValidationOut)
def validate_representation_payload(payload: RepresentationValidateRequest):
    try:
        validator, outcome = validate_representation(payload.representation_format, payload.content)
    except RepresentationError as exc:
        raise HTTPException(422, str(exc)) from exc
    normalized = outcome.normalized_content or None
    return RepresentationValidationOut(
        representation_format=payload.representation_format,
        representation_type=FORMAT_TO_TYPE[payload.representation_format],
        validator_key=validator.key, validator_version=validator.version,
        validation_status=outcome.validation_status, completeness_status=outcome.completeness_status,
        usable=outcome.usable, messages=outcome.messages,
        normalized_checksum=representation_checksum(
            payload.representation_format, validator.key, validator.version, normalized) if normalized else None,
        atom_count=outcome.atom_count, component_count=outcome.component_count,
        chemical_elements=outcome.chemical_elements, redaction_flags=outcome.redaction_flags,
    )


def _create_representation_for(
    db: Session, organisation_id: str, payload: RepresentationCreate,
    material_id: str | None, hypothesis_id: str | None,
) -> ScientificRepresentation:
    try:
        return create_representation(
            db, organisation_id=organisation_id, material_id=material_id, hypothesis_id=hypothesis_id,
            label=payload.label, representation_format=payload.representation_format, content=payload.content,
            visibility=payload.visibility, provenance_note=payload.provenance_note, metadata=payload.metadata,
        )
    except RepresentationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/materials/{material_id}/representations", response_model=RepresentationOut, status_code=201)
def create_material_representation(
    material_id: str, payload: RepresentationCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    material = db.get(Material, material_id)
    if not material or (material.visibility != "public" and material.owner_organisation_id != org):
        raise HTTPException(404, "Material not found")
    row = _create_representation_for(db, org, payload, material_id, None)
    db.commit(); db.refresh(row)
    return row


@router.post("/candidate-hypotheses/{hypothesis_id}/representations", response_model=RepresentationOut, status_code=201)
def create_hypothesis_representation(
    hypothesis_id: str, payload: RepresentationCreate,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    hypothesis = db.get(CandidateHypothesis, hypothesis_id)
    if not hypothesis or hypothesis.organisation_id != org:
        raise HTTPException(404, "Candidate hypothesis not found")
    row = _create_representation_for(db, org, payload, None, hypothesis_id)
    db.commit(); db.refresh(row)
    return row


@router.get("/simulation/targets/{target_kind}/{target_id}/representations", response_model=list[RepresentationOut])
def list_target_representations(
    target_kind: str, target_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    if target_kind not in {"known_material", "hypothesis"}:
        raise HTTPException(422, "target_kind must be known_material or hypothesis")
    return representations_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)


@router.get("/simulation/representations/{representation_id}", response_model=RepresentationDetailOut)
def get_representation(
    representation_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    row = db.get(ScientificRepresentation, representation_id)
    if not row or not representation_visible(row, organisation_id):
        raise HTTPException(404, "Representation not found")
    return row


# --- providers / methods / artifacts ------------------------------------------------------------
@router.get("/simulation/providers", response_model=list[SimulationProviderOut])
def list_simulation_providers(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return visible_providers(db, organisation_id)


@router.get("/simulation/providers/{provider_id}")
def get_simulation_provider(
    provider_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    provider = (
        db.query(SimulationProvider).options(selectinload(SimulationProvider.versions))
        .filter(SimulationProvider.id == provider_id).one_or_none()
    )
    if not provider or not provider_visible(provider, organisation_id):
        raise HTTPException(404, "Simulation provider not found")
    return provider_descriptor(db, provider)


@router.get("/simulation/providers/{provider_id}/versions", response_model=list[SimulationProviderVersionOut])
def list_provider_versions(
    provider_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    provider = (
        db.query(SimulationProvider).options(selectinload(SimulationProvider.versions))
        .filter(SimulationProvider.id == provider_id).one_or_none()
    )
    if not provider or not provider_visible(provider, organisation_id):
        raise HTTPException(404, "Simulation provider not found")
    return sorted(provider.versions, key=lambda v: (v.created_at, v.id))


@router.get("/simulation/provider-versions/{version_id}/availability")
def check_provider_version_availability(
    version_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    try:
        version = require_provider_version(db, version_id)
    except ValueError as exc:
        raise HTTPException(404, "Simulation provider version not found") from exc
    if not provider_visible(version.provider, organisation_id):
        raise HTTPException(404, "Simulation provider version not found")
    return {"provider_version_id": version.id, **provider_availability(db, version)}


@router.get("/simulation/methods")
def list_simulation_methods(db: Session = Depends(get_db)):
    return {"methods": method_descriptors(db), "workflow_templates": workflow_template_descriptors()}


@router.get("/simulation/artifacts", response_model=list[RegisteredArtifactOut])
def list_registered_artifacts(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return approved_artifacts(db, organisation_id)


# --- routing / workflows -------------------------------------------------------------------------
@router.post("/simulation/routes/preview")
def route_preview(
    payload: RoutePreviewRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    try:
        return preview_routes(
            db, target_kind=payload.target_kind, target_id=payload.target_id, organisation_id=org,
            purpose=payload.requested_purpose, property_key=payload.requested_property_key,
            conditions=payload.requested_conditions, pinned_provider_version_id=payload.pinned_provider_version_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/simulation/workflows/preview")
def workflow_preview(
    payload: WorkflowPreviewRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    try:
        return build_workflow_preview(
            db, target_kind=payload.target_kind, target_id=payload.target_id, organisation_id=org,
            method_key=payload.method_key, provider_version_id=payload.provider_version_id,
            parameters=payload.parameters, conditions=payload.requested_conditions,
            property_key=payload.requested_property_key,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/simulation/workflows", response_model=SimulationWorkflowOut, status_code=201)
def create_simulation_workflow(
    payload: WorkflowCreateRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if payload.project_id:
        project = db.get(ReplacementProject, payload.project_id)
        if not project or project.organisation_id != org:
            raise HTTPException(404, "Project not found")
    try:
        workflow = create_workflow(
            db, organisation_id=org, created_by=_default_user(db, org),
            target_kind=payload.target_kind, target_id=payload.target_id, method_key=payload.method_key,
            provider_version_id=payload.provider_version_id, parameters=payload.parameters,
            conditions=payload.requested_conditions, property_key=payload.requested_property_key,
            project_id=payload.project_id, candidate_id=payload.candidate_id, campaign_id=payload.campaign_id,
            metadata=payload.metadata,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.commit(); db.refresh(workflow)
    return workflow


def _scoped_workflow(db: Session, workflow_id: str, organisation_id: str | None) -> SimulationWorkflow:
    org = _org(organisation_id)
    workflow = (
        db.query(SimulationWorkflow).options(selectinload(SimulationWorkflow.steps))
        .filter(SimulationWorkflow.id == workflow_id, SimulationWorkflow.organisation_id == org).one_or_none()
    )
    if not workflow:
        raise HTTPException(404, "Simulation workflow not found")
    return workflow


@router.post("/simulation/workflows/{workflow_id}/execute", response_model=SimulationWorkflowOut)
def execute_simulation_workflow(
    workflow_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    workflow = _scoped_workflow(db, workflow_id, organisation_id)
    try:
        return execute_workflow(db, workflow)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/simulation/workflows/{workflow_id}/cancel", response_model=SimulationWorkflowOut)
def cancel_simulation_workflow(
    workflow_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    workflow = _scoped_workflow(db, workflow_id, organisation_id)
    try:
        return cancel_workflow(db, workflow)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/simulation/workflows", response_model=list[SimulationWorkflowOut])
def list_simulation_workflows(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    return (
        db.query(SimulationWorkflow).filter_by(organisation_id=org)
        .order_by(SimulationWorkflow.created_at.desc(), SimulationWorkflow.id)
        .offset(offset).limit(limit).all()
    )


@router.get("/simulation/workflows/{workflow_id}", response_model=WorkflowDetailOut)
def get_simulation_workflow(
    workflow_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    workflow = _scoped_workflow(db, workflow_id, organisation_id)
    return workflow_detail(db, workflow)


@router.get("/simulation/targets/{target_kind}/{target_id}/history")
def target_history(
    target_kind: str, target_id: str, offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if target_kind not in {"known_material", "hypothesis"}:
        raise HTTPException(422, "target_kind must be known_material or hypothesis")
    return target_simulation_history(db, target_kind=target_kind, target_id=target_id,
                                     organisation_id=org, offset=offset, limit=limit)


@router.post("/virtual-campaigns/{campaign_id}/simulation-escalation")
def campaign_simulation_escalation(
    campaign_id: str, payload: dict,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    """Map selected campaign candidates to simulation targets. Reads only — Phase-5 history is immutable."""
    org = _org(organisation_id)
    from app.models.entities import VirtualExperimentCampaign
    campaign = db.get(VirtualExperimentCampaign, campaign_id)
    if not campaign or campaign.organisation_id != org:
        raise HTTPException(404, "Virtual campaign not found")
    candidate_ids = list(payload.get("candidate_ids") or [])[:MAX_PAGE_SIZE]
    return {
        "campaign_id": campaign_id,
        "targets": campaign_escalation_targets(db, campaign_id=campaign_id, organisation_id=org, candidate_ids=candidate_ids),
        "note": "Escalation is an explicit request for physics assessment. It never replaces Phase-5 predictions "
                "and never reranks completed campaign history.",
    }


@router.post("/simulation/selection-policies", status_code=201)
def create_selection_policy(
    payload: SelectionPolicyCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    project = db.get(ReplacementProject, payload.project_id)
    if not project or project.organisation_id != org:
        raise HTTPException(404, "Project not found")
    workflow = db.query(SimulationWorkflow).filter_by(id=payload.simulation_workflow_id, organisation_id=org).one_or_none()
    if not workflow:
        raise HTTPException(404, "Simulation workflow not found")
    definition = db.query(MaterialPropertyDefinition).filter_by(key=payload.property_key).one_or_none()
    if not definition:
        raise HTTPException(422, "Unknown property definition")
    record = SimulationSelectionPolicyRecord(
        organisation_id=org, project_id=payload.project_id, property_definition_id=definition.id,
        target_scientific_id=payload.target_scientific_id,
        policy_key="explicit_simulation_workflow_v1", policy_version="1.0",
        simulation_workflow_id=payload.simulation_workflow_id, rationale=payload.rationale,
        created_by=_default_user(db, org),
    )
    db.add(record)
    db.commit()
    return {"id": record.id, "policy_key": record.policy_key, "policy_version": record.policy_version}


@router.get("/simulation/selection")
def get_selection(
    project_id: str, property_key: str, target_scientific_id: str,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    return select_simulation_value(db, project_id=project_id, property_key=property_key,
                                   target_id=target_scientific_id, organisation_id=org)


@router.get("/simulation/integrity")
def simulation_integrity(db: Session = Depends(get_db)):
    return assert_simulation_integrity(db)
