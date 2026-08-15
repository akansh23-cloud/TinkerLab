"""Request/response contracts for the Phase-12 intake bench."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import (
    Comparator,
    ConstraintStrength,
    MaterialFamily,
    ObjectiveDirection,
    Visibility,
)


class PropertyValueIn(BaseModel):
    property_key: str = Field(min_length=1, max_length=120)
    value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    temperature_value: float | None = None
    temperature_unit: str | None = "degC"
    method: str | None = None
    note: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_value(self) -> PropertyValueIn:
        if self.value is None and self.boolean_value is None:
            raise ValueError(f"Property '{self.property_key}' needs either a numeric or a boolean value.")
        if self.value is not None and self.boolean_value is not None:
            raise ValueError(f"Property '{self.property_key}' cannot be both numeric and boolean.")
        return self


class ComponentIn(BaseModel):
    component_name: str = Field(min_length=1, max_length=300)
    component_identifier: str | None = None
    component_role: str | None = None
    amount_value: float | None = None
    amount_lower: float | None = None
    amount_upper: float | None = None
    amount_unit: str | None = "%"
    amount_basis: str | None = "weight_percent"
    is_redacted: bool = False
    redaction_label: str | None = None
    notes: str | None = None


class IdentifierIn(BaseModel):
    namespace: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=300)
    is_primary: bool = False


class ProcessStateIn(BaseModel):
    state_label: str = Field(min_length=1, max_length=160)
    process_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class MaterialIntakeRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=240)
    material_family: MaterialFamily
    data_grade: str = Field(min_length=2, max_length=60)
    description: str | None = None
    supplier: str | None = None
    grade_code: str | None = None
    canonical_name: str | None = None
    source_reference: str | None = None
    method: str | None = None
    note: str | None = None
    identifiers: list[IdentifierIn] = Field(default_factory=list)
    components: list[ComponentIn] = Field(default_factory=list)
    process_state: ProcessStateIn | None = None
    properties: list[PropertyValueIn] = Field(default_factory=list)
    organisation_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC


class PropertyAppendRequest(BaseModel):
    data_grade: str = Field(min_length=2, max_length=60)
    properties: list[PropertyValueIn] = Field(min_length=1)
    source_reference: str | None = None
    method: str | None = None
    note: str | None = None
    organisation_id: str | None = None


class IntakeResponse(BaseModel):
    material_id: str
    display_name: str
    canonical_name: str
    material_family: str
    observation_count: int
    evidence_id: str
    data_grade: str
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class AppendResponse(BaseModel):
    material_id: str
    observation_count: int
    evidence_id: str
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class RequirementIn(BaseModel):
    property_key: str = Field(min_length=1, max_length=120)
    comparator: Comparator = Comparator.GTE
    target_value: float | None = None
    target_value_upper: float | None = None
    target_boolean: bool | None = None
    target_unit: str | None = None
    hard_or_soft: ConstraintStrength = ConstraintStrength.HARD
    weight: float = Field(default=1.0, ge=0, le=100)
    severity: int = Field(default=4, ge=1, le=5)
    rationale: str | None = None

    @model_validator(mode="after")
    def _validate_requirement_shape(self) -> RequirementIn:
        if self.comparator == Comparator.BOOLEAN:
            if self.target_boolean is None:
                raise ValueError("Boolean comparator requires target_boolean")
            if self.target_value is not None or self.target_value_upper is not None or self.target_unit is not None:
                raise ValueError("Boolean requirement cannot use numeric targets or units")
        elif self.comparator == Comparator.BETWEEN:
            if self.target_value is None or self.target_value_upper is None or self.target_unit is None:
                raise ValueError("Between requires lower value, upper value and unit")
            if self.target_value_upper < self.target_value:
                raise ValueError("Between upper bound must be >= lower bound")
        else:
            if self.target_value is None or self.target_unit is None:
                raise ValueError("Numeric requirement requires target_value and target_unit")
        return self


class ObjectiveIn(BaseModel):
    property_key: str = Field(min_length=1, max_length=120)
    direction: ObjectiveDirection = ObjectiveDirection.MINIMIZE
    weight: float = Field(default=1.0, gt=0, le=100)
    priority: int = Field(default=1, ge=1, le=100)
    target_value: float | None = None
    target_unit: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _target_requires_value(self) -> ObjectiveIn:
        if self.direction == ObjectiveDirection.TARGET and (self.target_value is None or self.target_unit is None):
            raise ValueError("Target objective requires target_value and target_unit")
        return self


class StudyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    baseline_material_id: str
    drivers: list[str] = Field(default_factory=lambda: ["cost"])
    description: str | None = None
    preset_key: str | None = None
    requirements: list[RequirementIn] = Field(default_factory=list)
    objectives: list[ObjectiveIn] = Field(default_factory=list)
    derive_from_baseline: bool = False
    baseline_margin: float = Field(default=0.05, ge=0.0, le=0.5)
    derive_space: bool = True
    organisation_id: str | None = None
    created_by: str | None = None


class LibraryInstallRequest(BaseModel):
    organisation_id: str | None = None
