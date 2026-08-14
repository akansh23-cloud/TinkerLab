from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    CandidateSource,
    CandidateStatus,
    Comparator,
    ConstraintKind,
    ConstraintStrength,
    ObjectiveDirection,
    ProjectStatus,
    ReplacementReason,
)
from app.schemas.common import ORMModel
from app.schemas.materials import MaterialSummary


class ProjectCreate(BaseModel):
    organisation_id: str
    name: str = Field(min_length=3, max_length=240)
    description: str | None = None
    baseline_material_id: str
    replacement_reasons: list[ReplacementReason] = Field(min_length=1)
    created_by: str
    status: ProjectStatus = ProjectStatus.DRAFT


class ConstraintCreate(BaseModel):
    constraint_type: ConstraintKind = ConstraintKind.PROPERTY
    property_key: str = Field(min_length=1, max_length=120)
    comparator: Comparator
    target_value: float | None = None
    target_value_upper: float | None = None
    target_boolean: bool | None = None
    target_unit: str | None = None
    severity: int = Field(default=1, ge=1, le=5)
    hard_or_soft: ConstraintStrength = ConstraintStrength.HARD
    weight: float = Field(default=1.0, ge=0, le=100)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_shape(self) -> ConstraintCreate:
        if self.comparator == Comparator.BOOLEAN:
            if self.target_boolean is None:
                raise ValueError("Boolean comparator requires target_boolean")
            if self.target_value is not None or self.target_unit is not None:
                raise ValueError("Boolean constraint cannot use numeric target/unit")
        elif self.comparator == Comparator.BETWEEN:
            if self.target_value is None or self.target_value_upper is None or self.target_unit is None:
                raise ValueError("Between requires lower value, upper value and unit")
            if self.target_value_upper < self.target_value:
                raise ValueError("Between upper bound must be >= lower bound")
        else:
            if self.target_value is None or self.target_unit is None:
                raise ValueError("Numeric comparator requires target_value and target_unit")
        return self


class ConstraintOut(ORMModel):
    id: str
    project_id: str
    constraint_type: str
    property_key: str
    comparator: str
    target_value: float | None
    target_value_upper: float | None
    target_boolean: bool | None
    target_unit: str | None
    severity: int
    hard_or_soft: str
    weight: float
    description: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class ObjectiveCreate(BaseModel):
    property_key: str = Field(min_length=1, max_length=120)
    direction: ObjectiveDirection
    target_value: float | None = None
    target_unit: str | None = None
    weight: float = Field(default=1.0, gt=0, le=100)
    priority: int = Field(default=1, ge=1, le=100)
    description: str | None = None

    @model_validator(mode="after")
    def target_requires_value(self) -> ObjectiveCreate:
        if self.direction == ObjectiveDirection.TARGET and (self.target_value is None or self.target_unit is None):
            raise ValueError("Target objective requires target_value and target_unit")
        return self


class ObjectiveOut(ORMModel):
    id: str
    project_id: str
    property_key: str
    direction: str
    target_value: float | None
    target_unit: str | None
    weight: float
    priority: int
    description: str | None


class CandidateCreate(BaseModel):
    material_id: str
    candidate_source: CandidateSource = CandidateSource.MANUAL
    status: CandidateStatus = CandidateStatus.PROPOSED
    notes: str | None = None


class CandidateHypothesisSummary(ORMModel):
    id: str
    display_label: str
    material_family: str
    deterministic_fingerprint: str
    status: str
    structural_validity: str
    generation_run_id: str | None = None


class CandidateOut(ORMModel):
    id: str
    project_id: str
    candidate_kind: str = "known_material"
    material_id: str | None
    hypothesis_id: str | None = None
    candidate_source: str
    status: str
    notes: str | None
    created_at: datetime
    material: MaterialSummary | None = None
    hypothesis: CandidateHypothesisSummary | None = None


class ProjectSummary(ORMModel):
    id: str
    name: str
    description: str | None
    baseline_material_id: str
    replacement_reasons: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    baseline_material: MaterialSummary
    constraint_count: int = 0
    candidate_count: int = 0


class ProjectDetail(ORMModel):
    id: str
    organisation_id: str
    name: str
    description: str | None
    baseline_material_id: str
    replacement_reasons: list[str]
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    baseline_material: MaterialSummary
    constraints: list[ConstraintOut]
    objectives: list[ObjectiveOut]
    candidates: list[CandidateOut]


class SpecificationConstraint(BaseModel):
    property: str
    operator: str
    value: float | bool | None
    upper_value: float | None = None
    unit: str | None = None
    weight: float
    severity: int


class SpecificationObjective(BaseModel):
    property: str
    direction: str
    value: float | None = None
    unit: str | None = None
    weight: float
    priority: int


class ReplacementSpecificationOut(BaseModel):
    specification_version: str
    project_id: str
    baseline: dict[str, str]
    reasons: list[str]
    hard_constraints: list[SpecificationConstraint]
    soft_constraints: list[SpecificationConstraint]
    objectives: list[SpecificationObjective]
    metadata: dict[str, Any]
    generated_at: str
    checksum: str
    canonical_payload: dict[str, Any]
    human_readable: str


class ConstraintEvaluationOut(BaseModel):
    constraint_id: str
    property_key: str
    status: str
    observed_value: float | bool | None
    observed_unit: str | None
    canonical_value: float | None
    canonical_unit: str | None
    target: dict[str, Any]
    evidence_id: str | None
    confidence: float | None
    unknown_reason: str | None = None
    selected_observation_id: str | None = None
    selection_rationale: list[str] = []
    applicability: str | None = None
    alternatives_count: int = 0
    conflict: bool = False
    value_origin: str = "known_evidence"
    prediction_id: str | None = None
    model_version: str | None = None
    prediction_interval: dict[str, Any] | None = None
    applicability_status: str | None = None
    uncertainty_crosses_constraint: bool = False


class PropertyComparisonOut(BaseModel):
    property_key: str
    display_name: str
    baseline_value: float | None
    candidate_value: float | None
    canonical_unit: str | None
    delta: float | None
    percentage_delta: float | None
    evidence_id: str | None
    confidence: float | None
    selected_observation_id: str | None = None
    selection_rationale: list[str] = []
    applicability: str | None = None
    alternatives_count: int = 0
    conflict: bool = False
    value_origin: str = "known_evidence"
    prediction_id: str | None = None
    model_version: str | None = None
    prediction_interval: dict[str, Any] | None = None
    applicability_status: str | None = None


class CandidateEvaluationOut(BaseModel):
    candidate_id: str
    candidate_kind: str = "known_material"
    material_id: str | None = None
    hypothesis_id: str | None = None
    material_name: str
    evidence_posture: str = "KNOWN EVIDENCE"
    hard_passed: int
    hard_failed: int
    unknown: int
    soft_passed: int
    completeness: float
    constraints: list[ConstraintEvaluationOut]
    properties: list[PropertyComparisonOut]
    objective_comparisons: list[dict[str, Any]]
    prediction_coverage: int = 0
