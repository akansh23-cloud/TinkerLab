from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class PredictionModelCreate(BaseModel):
    key: str = Field(min_length=2, max_length=160)
    display_name: str = Field(min_length=2, max_length=300)
    description: str | None = None
    model_type: str = "transparent_demo_linear"
    owner_provider: str = "TinkerLab"
    supported_material_families: list[str]
    supported_property_keys: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictionModelOut(ORMModel):
    id: str
    organisation_id: str | None
    key: str
    display_name: str
    description: str | None
    model_type: str
    owner_provider: str
    status: str
    supported_material_families: list[str]
    supported_property_keys: list[str]
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class ApplicabilityDomainIn(BaseModel):
    material_families: list[str]
    required_feature_keys: list[str]
    numeric_feature_ranges: dict[str, list[float]] = Field(default_factory=dict)
    allowed_categorical_values: dict[str, list[str]] = Field(default_factory=dict)
    required_component_keys: list[str] = Field(default_factory=list)
    target_condition_ranges: dict[str, dict[str, Any]] = Field(default_factory=dict)
    redacted_input_policy: Literal["reject", "allow_if_not_required"] = "reject"
    domain_distance_method: str | None = None
    domain_distance_config: dict[str, Any] = Field(default_factory=dict)
    borderline_tolerance: float = Field(default=0.0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictionModelVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=80)
    predictor_key: str = "demo_linear_json"
    predictor_contract_version: str = "1.0"
    artifact_format: str = "tinkerlab_linear_json_v1"
    artifact_payload: dict[str, Any]
    feature_schema_version: str = "polymer-demo-v1"
    feature_schema: dict[str, Any]
    target_property_key: str
    canonical_output_unit: str
    uncertainty_method: str
    applicability_policy_version: str = "applicability-v1"
    applicability_domain: ApplicabilityDomainIn
    training_data_descriptor: dict[str, Any] = Field(default_factory=dict)
    training_data_checksum: str | None = None
    calibration_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    immutable_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def safe_artifact(self):
        if self.artifact_format not in {"tinkerlab_linear_json_v1"}:
            raise ValueError("Unsupported/safe model artifact format")
        if self.predictor_key != "demo_linear_json":
            raise ValueError("Unregistered predictor_key")
        return self


class ApplicabilityDomainOut(ORMModel):
    id: str
    model_version_id: str
    material_families: list[str]
    required_feature_keys: list[str]
    numeric_feature_ranges: dict[str, Any]
    allowed_categorical_values: dict[str, Any]
    required_component_keys: list[str]
    target_condition_ranges: dict[str, Any]
    redacted_input_policy: str
    domain_distance_method: str | None
    domain_distance_config: dict[str, Any]
    borderline_tolerance: float
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class PredictionModelVersionOut(ORMModel):
    id: str
    model_id: str
    version: str
    predictor_key: str
    predictor_contract_version: str
    artifact_format: str
    artifact_checksum: str
    feature_schema_version: str
    feature_schema: dict[str, Any]
    feature_schema_checksum: str
    target_property_key: str
    canonical_output_unit: str
    uncertainty_method: str
    applicability_policy_version: str
    training_data_descriptor: dict[str, Any]
    training_data_checksum: str | None
    calibration_metrics: dict[str, Any]
    validation_metrics: dict[str, Any]
    approved_at: datetime | None
    retired_at: datetime | None
    immutable_metadata: dict[str, Any]
    created_at: datetime
    applicability_domain: ApplicabilityDomainOut | None = None


class PredictionTargetRequest(BaseModel):
    candidate_id: str | None = None
    material_id: str | None = None
    hypothesis_id: str | None = None

    @model_validator(mode="after")
    def one_target(self):
        if sum(x is not None for x in (self.candidate_id, self.material_id, self.hypothesis_id)) != 1:
            raise ValueError("Exactly one of candidate_id, material_id, hypothesis_id is required")
        return self


class ApplicabilityAssessRequest(BaseModel):
    project_id: str
    property_key: str
    target: PredictionTargetRequest
    conditions: dict[str, Any] = Field(default_factory=dict)


class ApplicabilityIssue(BaseModel):
    code: str
    message: str
    feature: str | None = None
    value: Any = None
    allowed: Any = None


class ApplicabilityOut(BaseModel):
    status: str
    reasons: list[ApplicabilityIssue]
    feature_checksum: str
    source_entity_checksum: str
    missing_features: list[str]
    redaction_flags: list[str]
    target_kind: str
    target_id: str


class PredictionRunPreviewRequest(BaseModel):
    model_version_id: str
    property_key: str
    targets: list[PredictionTargetRequest] = Field(min_length=1, max_length=200)
    conditions: dict[str, Any] = Field(default_factory=dict)
    requested_output_unit: str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)


class PredictionRunCreate(PredictionRunPreviewRequest):
    created_by: str


class PredictionPreviewTarget(BaseModel):
    target_kind: str
    target_id: str
    candidate_id: str | None = None
    applicability_status: str
    reasons: list[ApplicabilityIssue]
    feature_checksum: str
    missing_features: list[str]
    redaction_flags: list[str]


class PredictionRunPreviewOut(BaseModel):
    valid: bool
    model_id: str
    model_version_id: str
    model_version: str
    model_label: str
    demo_warning: str | None
    property_key: str
    feature_schema_version: str
    target_condition_checksum: str
    configuration_checksum: str
    target_count: int
    in_domain_count: int
    borderline_count: int
    inapplicable_count: int
    expected_model_executions: int
    targets: list[PredictionPreviewTarget]
    validation_problems: list[str]


class PredictionRunOut(ORMModel):
    id: str
    organisation_id: str
    project_id: str
    model_version_id: str
    property_key: str
    configuration_checksum: str
    target_condition_checksum: str
    requested_target_count: int
    predicted_count: int
    inapplicable_count: int
    failed_count: int
    status: str
    run_seed: int | None
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str
    result_checksum: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime


class PropertyPredictionOut(ORMModel):
    id: str
    prediction_run_id: str
    prediction_target_id: str
    model_version_id: str
    input_snapshot_id: str
    property_definition_id: str
    applicability_status: str
    applicability_rationale: list[dict[str, Any]]
    domain_distance: float | None
    numeric_point_estimate: float | None
    output_unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    uncertainty_lower: float | None
    uncertainty_upper: float | None
    uncertainty_stddev: float | None
    uncertainty_method: str
    calibrated_coverage_level: float | None
    warnings: list[str]
    status: str
    deterministic_result_checksum: str
    created_at: datetime
    scientific_origin: str = "MODEL PREDICTION"


class PredictionResultDetail(BaseModel):
    prediction: PropertyPredictionOut
    target: dict[str, Any]
    model: dict[str, Any]
    model_version: dict[str, Any]
    feature_snapshot: dict[str, Any]
    demo_warning: str | None


class PredictionResultPage(BaseModel):
    items: list[dict[str, Any]]
    total: int
    offset: int
    limit: int
