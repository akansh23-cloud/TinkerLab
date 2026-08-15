from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel

TargetKind = Literal["known_material", "hypothesis"]


class CompositionComponentIn(BaseModel):
    element: str = Field(min_length=1, max_length=8)
    role: Literal["host", "alloying", "dopant", "impurity", "additive", "reinforcement", "matrix", "unknown"] = "host"
    stoichiometry: float | None = None
    atomic_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    atomic_fraction_min: float | None = Field(default=None, ge=0.0, le=1.0)
    atomic_fraction_max: float | None = Field(default=None, ge=0.0, le=1.0)
    concentration_value: float | None = None
    concentration_unit: str | None = None
    original_representation: str | None = None


class ProcessingStepIn(BaseModel):
    step_kind: str = Field(max_length=60)
    display_name: str | None = None
    temperature_k: float | None = Field(default=None, ge=0.0)
    duration_s: float | None = Field(default=None, ge=0.0)
    pressure_pa: float | None = Field(default=None, ge=0.0)
    atmosphere: str | None = None
    cooling_rate_k_per_s: float | None = None
    strain_fraction: float | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class ProcessingHistoryCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=300)
    key: str | None = None
    description: str | None = None
    steps: list[ProcessingStepIn] = Field(min_length=1, max_length=50)


class MaterialStateCreate(BaseModel):
    target_kind: TargetKind
    target_id: str
    label: str = Field(min_length=1, max_length=300)
    description: str | None = None
    composition: list[CompositionComponentIn] = Field(default_factory=list)
    representation_id: str | None = None
    crystal_system: str | None = None
    space_group_number: int | None = Field(default=None, ge=1, le=230)
    space_group_symbol: str | None = None
    lattice_parameters: dict[str, Any] = Field(default_factory=dict)
    polymorph: str | None = None
    phase: str | None = None
    phase_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    microstructure_id: str | None = None
    processing_history_id: str | None = None
    temperature_k: float | None = Field(default=None, ge=0.0)
    pressure_pa: float | None = Field(default=None, ge=0.0)
    environment: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    provenance_note: str | None = None
    is_reference_state: bool = False
    visibility: Literal["private", "public"] = "private"


class MaterialStateOut(ORMModel):
    id: str
    material_id: str | None
    hypothesis_id: str | None
    label: str
    description: str | None
    is_reference_state: bool
    representation_id: str | None
    crystal_system: str | None
    space_group_number: int | None
    space_group_symbol: str | None
    lattice_parameters: dict[str, Any]
    polymorph: str | None
    phase: str | None
    phase_fraction: float | None
    structure_identity: str | None
    structure_identity_basis: str | None
    composition_signature: str | None
    microstructure_id: str | None
    processing_history_id: str | None
    temperature_k: float | None
    pressure_pa: float | None
    environment: str | None
    conditions: dict[str, Any]
    state_checksum: str
    provenance_note: str | None
    status: str
    created_at: datetime


class ApplicationCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    domain: str | None = None
    description: str | None = None
    operating_conditions: dict[str, Any] = Field(default_factory=dict)


class ApplicationComponentCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    operating_conditions: dict[str, Any] = Field(default_factory=dict)


class MaterialRoleCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    incumbent_material_id: str | None = None
    incumbent_state_id: str | None = None


class MaterialFunctionCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    category: Literal["electronic", "thermal", "mechanical", "optical", "magnetic", "chemical",
                      "electrochemical", "barrier", "structural", "processing", "other"] = "other"
    description: str | None = None
    criticality: int = Field(default=1, ge=1, le=5)
    operating_conditions: dict[str, Any] = Field(default_factory=dict)


class FunctionalRequirementCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    requirement_kind: Literal["hard_constraint", "soft_constraint", "objective", "preference", "informational"] = "hard_constraint"
    direction: Literal["minimum", "maximum", "range", "target", "maximize", "minimize", "categorical"]
    property_key: str | None = None
    target_value: float | None = None
    target_value_upper: float | None = None
    target_unit: str | None = None
    categorical_target: str | None = None
    tolerance: float | None = Field(default=None, ge=0.0)
    weight: float = Field(default=1.0, ge=0.0)
    conditions: dict[str, Any] = Field(default_factory=dict)
    rationale: str | None = None

    @model_validator(mode="after")
    def _direction_requires_operands(self) -> FunctionalRequirementCreate:
        if self.direction in {"minimum", "maximum"} and self.target_value is None:
            raise ValueError(f"direction '{self.direction}' requires target_value")
        if self.direction == "range" and (self.target_value is None or self.target_value_upper is None):
            raise ValueError("direction 'range' requires target_value and target_value_upper")
        if self.direction == "target" and self.tolerance is None:
            raise ValueError(
                "direction 'target' requires an explicit tolerance; an arbitrary tolerance is never invented"
            )
        if self.direction == "categorical" and not self.categorical_target:
            raise ValueError("direction 'categorical' requires categorical_target")
        if self.direction not in {"categorical"} and not self.property_key:
            raise ValueError("A testable requirement must name the property it constrains")
        return self


class ReasoningEdgeCreate(BaseModel):
    edge_kind: Literal["state_exhibits_feature", "feature_enables_mechanism", "mechanism_governs_property",
                       "property_delivers_function", "function_satisfies_requirement"]
    from_kind: Literal["material_state", "structural_feature", "mechanism", "property", "function", "requirement"]
    from_id: str
    to_kind: Literal["material_state", "structural_feature", "mechanism", "property", "function", "requirement"]
    to_id: str
    relationship_note: str | None = None
    scope: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_id: str | None = None
    citation_id: str | None = None
    source_type: str = "declared"
    source_reference: str | None = None


class ReasoningRequest(BaseModel):
    role_id: str
    target_kind: TargetKind
    target_id: str
    project_id: str | None = None
    candidate_id: str | None = None
    state_id: str | None = None
    generation_rationale: str | None = None
    persist: bool = False


class CandidateReasoningOut(ORMModel):
    id: str
    project_id: str | None
    role_id: str
    candidate_id: str | None
    target_kind: str
    target_scientific_id: str
    state_id: str | None
    requirement_results: list[dict[str, Any]]
    function_coverage: dict[str, Any]
    satisfied_requirements: list[str]
    failed_requirements: list[str]
    unknown_requirements: list[str]
    evidence_gaps: list[dict[str, Any]]
    origin_breakdown: dict[str, Any]
    assumptions: list[str]
    mechanism_paths: list[dict[str, Any]]
    overall_status: str
    generation_rationale: str | None
    reasoning_checksum: str
    policy_version: str
    superseded_by_id: str | None
    created_at: datetime
