from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class RepresentationCreate(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    representation_format: str = Field(min_length=1, max_length=80)
    content: dict[str, Any]
    visibility: Literal["private", "public"] = "private"
    provenance_note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RepresentationValidateRequest(BaseModel):
    representation_format: str
    content: dict[str, Any]


class RepresentationValidationOut(BaseModel):
    representation_format: str
    representation_type: str
    validator_key: str
    validator_version: str
    validation_status: str
    completeness_status: str
    usable: bool
    messages: list[dict[str, Any]]
    normalized_checksum: str | None
    atom_count: int | None
    component_count: int | None
    chemical_elements: list[str]
    redaction_flags: list[str]


class RepresentationOut(ORMModel):
    id: str
    organisation_id: str | None
    visibility: str
    material_id: str | None
    hypothesis_id: str | None
    label: str
    representation_type: str
    representation_format: str
    representation_version: str
    normalized_checksum: str
    content_bytes: int
    periodicity: str | None
    dimensionality: int | None
    atom_count: int | None
    component_count: int | None
    chemical_elements: list[str]
    validator_key: str
    validator_version: str
    validation_status: str
    completeness_status: str
    validation_messages: list[dict[str, Any]]
    redaction_flags: list[str]
    provenance_note: str | None
    status: str
    created_at: datetime


class RepresentationDetailOut(RepresentationOut):
    content: dict[str, Any]


class SimulationProviderOut(ORMModel):
    id: str
    organisation_id: str | None
    key: str
    display_name: str
    provider_type: str
    method_family: str
    description: str | None
    safety_class: str
    approved_execution_mode: str
    status: str
    created_at: datetime


class SimulationProviderVersionOut(ORMModel):
    id: str
    provider_id: str
    version: str
    adapter_key: str
    adapter_contract_version: str
    executable_key: str | None
    executable_version: str | None
    parser_key: str
    parser_version: str
    input_builder_key: str
    input_builder_version: str
    convergence_evaluator_key: str
    convergence_evaluator_version: str
    supported_method_keys: list[str]
    supported_material_families: list[str]
    supported_representation_types: list[str]
    supported_representation_formats: list[str]
    supported_property_keys: list[str]
    required_artifact_types: list[str]
    artifact_manifest_checksum: str
    fidelity: str
    deterministic: bool
    execution_supported: bool
    maximum_target_size: int
    maximum_wall_time_seconds: int
    resource_class: str
    known_limitations: list[str]
    approved_at: datetime | None
    retired_at: datetime | None
    created_at: datetime


class RegisteredArtifactOut(ORMModel):
    id: str
    organisation_id: str | None
    key: str
    version: str
    display_name: str
    artifact_type: str
    applies_to_method_families: list[str]
    applies_to_elements: list[str]
    content_checksum: str
    content_bytes: int
    content_available: bool
    license_name: str | None
    license_permits_redistribution: bool
    status: str
    approved_at: datetime | None
    created_at: datetime


class RoutePreviewRequest(BaseModel):
    target_kind: Literal["known_material", "hypothesis"]
    target_id: str
    requested_purpose: str = Field(default="energy_stability", max_length=120)
    requested_property_key: str | None = None
    requested_conditions: dict[str, Any] = Field(default_factory=dict)
    pinned_provider_version_id: str | None = None


class WorkflowPreviewRequest(BaseModel):
    target_kind: Literal["known_material", "hypothesis"]
    target_id: str
    method_key: str
    provider_version_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_conditions: dict[str, Any] = Field(default_factory=dict)
    requested_property_key: str | None = None


class WorkflowCreateRequest(WorkflowPreviewRequest):
    project_id: str | None = None
    candidate_id: str | None = None
    campaign_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _bounded_metadata(self) -> WorkflowCreateRequest:
        if len(str(self.metadata)) > 4000:
            raise ValueError("Workflow metadata is bounded to 4000 characters")
        return self


class SimulationWorkflowOut(ORMModel):
    id: str
    organisation_id: str
    project_id: str | None
    candidate_id: str | None
    campaign_id: str | None
    target_kind: str
    target_scientific_id: str
    route_id: str
    input_snapshot_id: str
    provider_version_id: str
    method_definition_id: str
    workflow_template_key: str
    workflow_template_version: str
    requested_purpose: str
    requested_property_key: str | None
    requested_fidelity: str
    max_steps: int
    max_wall_time_seconds: int
    status: str
    failure_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    workflow_checksum: str | None
    created_at: datetime


class SimulationStepOut(ORMModel):
    id: str
    workflow_id: str
    sequence: int
    step_key: str
    provider_version_id: str
    method_key: str
    status: str
    input_checksum: str
    output_checksum: str | None
    requires_convergence: bool
    max_retries: int


class SimulationJobOut(ORMModel):
    id: str
    workflow_id: str
    step_id: str
    provider_version_id: str
    attempt_number: int
    command_descriptor: dict[str, Any]
    resource_request: dict[str, Any]
    compute_backend_key: str
    status: str
    process_exit_code: int | None
    failure_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    elapsed_seconds: float | None
    stdout_artifact_id: str | None
    stderr_artifact_id: str | None
    operational_checksum: str


class SimulationArtifactOut(ORMModel):
    id: str
    workflow_id: str | None
    job_id: str | None
    artifact_type: str
    content_role: str
    file_name: str
    media_type: str
    storage_reference: str
    content_checksum: str
    content_bytes: int
    truncated: bool
    is_private: bool
    inline_preview: str | None
    created_at: datetime


class SimulationResultOut(ORMModel):
    id: str
    workflow_id: str
    job_id: str | None
    target_kind: str
    target_scientific_id: str
    method_definition_id: str
    provider_version_id: str
    operational_status: str
    scientific_status: str
    convergence_metrics: dict[str, Any]
    convergence_criteria: dict[str, Any]
    convergence_evaluator_version: str
    parser_key: str
    parser_version: str
    parsed_quantities: dict[str, Any]
    warnings: list[str]
    method_limitations: list[str]
    output_artifact_checksums: list[str]
    result_checksum: str
    scientific_origin: str
    created_at: datetime


class SimulationPropertyEstimateOut(ORMModel):
    id: str
    simulation_result_id: str
    property_definition_id: str
    numeric_value: float | None
    raw_unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    numerical_tolerance: float | None
    tolerance_basis: str | None
    method_limitations: list[str]
    target_conditions: dict[str, Any]
    extractor_key: str
    extractor_version: str
    estimate_checksum: str
    scientific_origin: str


class WorkflowDetailOut(BaseModel):
    workflow: SimulationWorkflowOut
    steps: list[SimulationStepOut]
    jobs: list[SimulationJobOut]
    artifacts: list[SimulationArtifactOut]
    result: SimulationResultOut | None
    property_estimates: list[SimulationPropertyEstimateOut]
    warning: str
    evidence_separation: str


class SelectionPolicyCreate(BaseModel):
    project_id: str
    property_key: str
    target_scientific_id: str
    simulation_workflow_id: str
    rationale: str = Field(min_length=10, max_length=2000)
