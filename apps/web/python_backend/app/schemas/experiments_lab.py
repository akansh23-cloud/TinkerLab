from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel

TargetKind = Literal["known_material", "hypothesis"]


class ProtocolCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=10)
    property_key: str | None = None


class ProtocolVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    objective: str = Field(min_length=10)
    required_equipment: list[str] = Field(default_factory=list)
    sample_requirements: dict[str, Any] = Field(default_factory=dict)
    preparation_steps: list[dict[str, Any]] = Field(default_factory=list)
    controlled_variables: dict[str, Any] = Field(default_factory=dict)
    independent_variables: list[dict[str, Any]] = Field(default_factory=list)
    dependent_variables: list[dict[str, Any]] = Field(default_factory=list)
    measurement_procedure: list[dict[str, Any]] = Field(min_length=1)
    calibration_requirements: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: dict[str, Any] = Field(default_factory=dict)
    safety_notes: str | None = None
    replicate_requirement: int = Field(default=1, ge=1, le=100)
    control_requirement: str | None = None


class ProtocolVersionOut(ORMModel):
    id: str
    protocol_id: str
    version: str
    objective: str
    required_equipment: list[str]
    sample_requirements: dict[str, Any]
    preparation_steps: list[dict[str, Any]]
    controlled_variables: dict[str, Any]
    independent_variables: list[dict[str, Any]]
    dependent_variables: list[dict[str, Any]]
    measurement_procedure: list[dict[str, Any]]
    calibration_requirements: dict[str, Any]
    acceptance_criteria: dict[str, Any]
    safety_notes: str | None
    replicate_requirement: int
    control_requirement: str | None
    protocol_checksum: str
    is_frozen: bool
    superseded_by_id: str | None
    created_at: datetime


class InstrumentCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    instrument_type: str = Field(max_length=120)
    manufacturer: str | None = None
    model: str | None = None
    asset_reference: str | None = None
    measures_property_keys: list[str] = Field(default_factory=list)
    equipment_capabilities: list[str] = Field(default_factory=list)
    measurement_unit: str | None = None
    stated_uncertainty: float | None = Field(default=None, ge=0.0)
    stated_uncertainty_unit: str | None = None
    calibration_status: Literal["calibrated", "overdue", "not_applicable", "unknown"] = "unknown"
    calibration_date: date | None = None
    calibration_due_date: date | None = None
    calibration_reference: str | None = None
    integration_kind: Literal["manual_entry", "lims", "instrument_api", "robotic_platform",
                              "contract_laboratory"] = "manual_entry"

    @model_validator(mode="after")
    def _calibration_claim_needs_evidence(self) -> InstrumentCreate:
        if self.calibration_status == "calibrated" and not (self.calibration_date and self.calibration_reference):
            raise ValueError(
                "Claiming an instrument is calibrated requires a calibration date and a reference. "
                "Calibration is never assumed or fabricated."
            )
        return self


class InstrumentOut(ORMModel):
    id: str
    key: str
    display_name: str
    instrument_type: str
    manufacturer: str | None
    model: str | None
    measures_property_keys: list[str]
    equipment_capabilities: list[str]
    measurement_unit: str | None
    stated_uncertainty: float | None
    calibration_status: str
    calibration_date: date | None
    calibration_due_date: date | None
    calibration_reference: str | None
    integration_kind: str
    status: str
    created_at: datetime


class SampleCreate(BaseModel):
    sample_code: str = Field(min_length=1, max_length=160)
    display_name: str | None = None
    sample_kind: Literal["synthesized", "procured", "subdivided", "reference_standard",
                         "control", "unknown"] = "unknown"
    target_kind: TargetKind | None = None
    target_id: str | None = None
    material_state_id: str | None = None
    candidate_id: str | None = None
    parent_sample_id: str | None = None
    batch_reference: str | None = None
    synthesis_reference: str | None = None
    processing_history_id: str | None = None
    geometry: str | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    mass_kg: float | None = Field(default=None, ge=0.0)
    preparation_date: date | None = None
    storage_conditions: str | None = None
    provenance_note: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class SampleOut(ORMModel):
    id: str
    candidate_id: str | None
    sample_code: str
    display_name: str | None
    sample_kind: str
    material_id: str | None
    hypothesis_id: str | None
    material_state_id: str | None
    parent_sample_id: str | None
    batch_reference: str | None
    geometry: str | None
    dimensions: dict[str, Any]
    mass_kg: float | None
    preparation_date: date | None
    provenance_complete: bool
    provenance_gaps: list[str]
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime


class PlanCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=10)
    design_kind: Literal["single_run", "one_factor", "full_factorial", "parameter_sweep"]
    protocol_version_id: str
    factors: list[dict[str, Any]] = Field(default_factory=list)
    replicate_count: int = Field(default=1, ge=1, le=50)
    control_plan: str | None = None
    project_id: str | None = None
    candidate_id: str | None = None
    role_id: str | None = None
    requirement_id: str | None = None
    sample_id: str | None = None
    instrument_id: str | None = None
    run_code_prefix: str = Field(default="RUN", max_length=40)

    @model_validator(mode="after")
    def _factors_are_well_formed(self) -> PlanCreate:
        for factor in self.factors:
            if not factor.get("name") or not isinstance(factor.get("levels"), list) or not factor["levels"]:
                raise ValueError("Every factor requires a name and a non-empty list of levels")
        if self.design_kind in {"one_factor", "parameter_sweep"} and len(self.factors) != 1:
            raise ValueError(f"design '{self.design_kind}' requires exactly one factor")
        if self.design_kind == "full_factorial" and not self.factors:
            raise ValueError("A full factorial design requires at least one factor")
        return self


class PlanOut(ORMModel):
    id: str
    project_id: str | None
    candidate_id: str | None
    role_id: str | None
    requirement_id: str | None
    display_name: str
    objective: str
    design_kind: str
    protocol_version_id: str
    factors: list[dict[str, Any]]
    replicate_count: int
    control_plan: str | None
    planned_run_count: int
    design_checksum: str
    status: str
    created_at: datetime


class RunOut(ORMModel):
    id: str
    plan_id: str | None
    protocol_version_id: str
    protocol_checksum_at_run: str
    run_code: str
    sample_id: str | None
    instrument_id: str | None
    replicate_index: int
    is_control: bool
    factor_levels: dict[str, Any]
    conditions: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    status: str
    deviation_notes: str | None
    invalidation_reason: str | None
    integration_kind: str
    created_at: datetime


class MeasurementCreate(BaseModel):
    run_id: str
    property_key: str
    numeric_value: float
    unit: str = Field(min_length=1, max_length=80)
    uncertainty: float | None = Field(default=None, ge=0.0)
    uncertainty_type: str | None = None
    method: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    replicate_index: int = Field(default=1, ge=1)
    measured_at: datetime | None = None
    notes: str | None = None


class MeasurementOut(ORMModel):
    id: str
    run_id: str
    sample_id: str | None
    instrument_id: str | None
    property_definition_id: str
    numeric_value: float | None
    unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    uncertainty: float | None
    uncertainty_type: str | None
    method: str | None
    conditions: dict[str, Any]
    replicate_index: int
    measured_at: datetime | None
    quality: str
    quality_reasons: list[str]
    admissibility_codes: list[str]
    scientific_origin: str
    measurement_checksum: str
    notes: str | None
    created_at: datetime


class ValidationRequest(BaseModel):
    role_id: str
    candidate_id: str | None = None
    target_kind: TargetKind | None = None
    target_id: str | None = None
    project_id: str | None = None
    persist: bool = False

    @model_validator(mode="after")
    def _candidate_or_target(self) -> "ValidationRequest":
        if self.candidate_id:
            return self
        if not self.target_kind or not self.target_id:
            raise ValueError("Provide candidate_id, or both target_kind and target_id")
        return self


class RecommendationRequest(ValidationRequest):
    pass


class ReplacementDecisionRequest(BaseModel):
    role_id: str
    candidate_id: str
    persist_validation: bool = False
