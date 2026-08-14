from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel

TargetKind = Literal["known_material", "hypothesis"]


class ManufacturingRouteCreate(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=300)
    process_family: str = Field(max_length=60)
    description: str | None = None
    applies_to_material_families: list[str] = Field(default_factory=list)
    applies_to_elements: list[str] = Field(default_factory=list)
    required_equipment: list[str] = Field(default_factory=list)
    process_temperature_k_min: float | None = None
    process_temperature_k_max: float | None = None
    process_pressure_pa_min: float | None = None
    process_pressure_pa_max: float | None = None
    achievable_thickness_m_min: float | None = None
    achievable_thickness_m_max: float | None = None
    achievable_tolerance_m: float | None = None
    surface_finish_ra_m: float | None = None
    typical_yield_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    throughput_units_per_hour: float | None = Field(default=None, ge=0.0)
    capex_class: str | None = None
    process_maturity: str = "unknown"
    scale_up_maturity: str = "unknown"
    known_limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ordered_bounds(self) -> ManufacturingRouteCreate:
        pairs = (
            ("process_temperature_k", self.process_temperature_k_min, self.process_temperature_k_max),
            ("process_pressure_pa", self.process_pressure_pa_min, self.process_pressure_pa_max),
            ("achievable_thickness_m", self.achievable_thickness_m_min, self.achievable_thickness_m_max),
        )
        for name, low, high in pairs:
            if low is not None and high is not None and low > high:
                raise ValueError(f"{name}_min must not exceed {name}_max")
        return self


class ManufacturingRouteOut(ORMModel):
    id: str
    organisation_id: str | None
    visibility: str
    key: str
    display_name: str
    process_family: str
    description: str | None
    applies_to_material_families: list[str]
    applies_to_elements: list[str]
    required_equipment: list[str]
    process_temperature_k_min: float | None
    process_temperature_k_max: float | None
    process_pressure_pa_min: float | None
    process_pressure_pa_max: float | None
    achievable_thickness_m_min: float | None
    achievable_thickness_m_max: float | None
    achievable_tolerance_m: float | None
    surface_finish_ra_m: float | None
    typical_yield_fraction: float | None
    throughput_units_per_hour: float | None
    capex_class: str | None
    process_maturity: str
    scale_up_maturity: str
    known_limitations: list[str]
    status: str
    created_at: datetime


class IndustrialEvidenceCreate(BaseModel):
    target_kind: TargetKind
    target_id: str
    category: Literal["manufacturing", "economic", "supply_chain", "environmental", "regulatory", "maturity"]
    metric_key: str = Field(min_length=1, max_length=120)
    display_label: str = Field(min_length=1, max_length=300)
    numeric_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    uncertainty: float | None = Field(default=None, ge=0.0)
    unit: str | None = None
    boolean_value: bool | None = None
    categorical_value: str | None = None
    currency: str | None = Field(default=None, max_length=10)
    currency_year: int | None = Field(default=None, ge=1900, le=2200)
    cost_basis: str | None = None
    quantity_basis_value: float | None = None
    quantity_basis_unit: str | None = None
    geography: str | None = None
    jurisdiction: str | None = None
    process_context: str | None = None
    manufacturing_route_id: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    as_of_date: date | None = None
    valid_until: date | None = None
    source_type: str = Field(max_length=60)
    source_reference: str | None = None
    extraction_method: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    is_estimate: bool = False
    notes: str | None = None
    visibility: Literal["private", "public"] = "private"

    @model_validator(mode="after")
    def _one_value_shape_and_ordered_bounds(self) -> IndustrialEvidenceCreate:
        shapes = [
            self.numeric_value is not None or (self.lower_bound is not None and self.upper_bound is not None),
            self.boolean_value is not None,
            self.categorical_value is not None,
        ]
        if sum(1 for s in shapes if s) != 1:
            raise ValueError(
                "Provide exactly one value shape: a numeric value or range, a boolean, or a category. "
                "An industrial claim with no value is not stored, and a value with no shape is ambiguous."
            )
        if self.lower_bound is not None and self.upper_bound is not None and self.lower_bound > self.upper_bound:
            raise ValueError("lower_bound must not exceed upper_bound")
        if self.valid_until and self.as_of_date and self.valid_until < self.as_of_date:
            raise ValueError("valid_until must not precede as_of_date")
        numeric_shape = self.numeric_value is not None or (self.lower_bound is not None and self.upper_bound is not None)
        if self.category == "economic" and numeric_shape:
            if not self.currency or self.currency_year is None or not self.cost_basis:
                raise ValueError(
                    "MONETARY_BASIS_INCOMPLETE: economic numeric evidence requires currency, currency_year and cost_basis"
                )
        return self


class IndustrialEvidenceOut(ORMModel):
    id: str
    organisation_id: str | None
    visibility: str
    material_id: str | None
    hypothesis_id: str | None
    category: str
    metric_key: str
    display_label: str
    numeric_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    uncertainty: float | None
    unit: str | None
    boolean_value: bool | None
    categorical_value: str | None
    currency: str | None
    currency_year: int | None
    cost_basis: str | None
    quantity_basis_value: float | None
    quantity_basis_unit: str | None
    geography: str | None
    jurisdiction: str | None
    process_context: str | None
    manufacturing_route_id: str | None
    conditions: dict[str, Any]
    as_of_date: date | None
    valid_until: date | None
    source_type: str
    source_reference: str | None
    extraction_method: str | None
    confidence: float | None
    is_estimate: bool
    scientific_origin: str
    notes: str | None
    content_checksum: str
    status: str
    created_at: datetime


class ProcessCompatibilityCreate(BaseModel):
    target_kind: TargetKind
    target_id: str
    route_id: str
    compatibility: Literal["compatible", "conditionally_compatible", "incompatible", "unknown"]
    rationale: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    industrial_evidence_id: str | None = None
    as_of_date: date | None = None

    @model_validator(mode="after")
    def _reason_required_for_verdict(self) -> ProcessCompatibilityCreate:
        if self.compatibility in {"compatible", "incompatible", "conditionally_compatible"} and not self.rationale:
            raise ValueError("A compatibility verdict requires a rationale; an unexplained verdict is not stored")
        return self


class ProcessCompatibilityOut(ORMModel):
    id: str
    route_id: str
    material_id: str | None
    hypothesis_id: str | None
    compatibility: str
    rationale: str | None
    conditions: dict[str, Any]
    industrial_evidence_id: str | None
    as_of_date: date | None
    created_at: datetime


class IndustrialConstraintCreate(BaseModel):
    category: Literal["manufacturing", "economic", "supply_chain", "environmental", "regulatory", "maturity"]
    constraint_kind: Literal[
        "max_value", "min_value", "range", "banned_element", "required_process_compatibility",
        "allowed_jurisdiction", "minimum_maturity", "supplier_diversity",
    ]
    display_label: str = Field(min_length=1, max_length=300)
    metric_key: str | None = None
    strength: Literal["hard", "soft", "preference"] = "hard"
    weight: float = Field(default=1.0, ge=0.0)
    target_value: float | None = None
    target_value_upper: float | None = None
    target_unit: str | None = None
    currency: str | None = None
    currency_year: int | None = None
    cost_basis: str | None = None
    banned_elements: list[str] = Field(default_factory=list)
    allowed_jurisdictions: list[str] = Field(default_factory=list)
    required_route_keys: list[str] = Field(default_factory=list)
    minimum_maturity: str | None = None
    minimum_supplier_count: int | None = Field(default=None, ge=1)
    treat_missing_evidence_as: Literal["fail", "unknown", "insufficient_evidence"] = "insufficient_evidence"
    rationale: str | None = None

    @model_validator(mode="after")
    def _kind_requires_its_operands(self) -> IndustrialConstraintCreate:
        kind = self.constraint_kind
        if kind in {"max_value", "min_value"} and self.target_value is None:
            raise ValueError(f"{kind} requires target_value")
        if kind == "range" and (self.target_value is None or self.target_value_upper is None):
            raise ValueError("range requires both target_value and target_value_upper")
        if kind in {"max_value", "min_value", "range"} and not self.metric_key:
            raise ValueError("A threshold constraint requires metric_key")
        if kind == "banned_element" and not self.banned_elements:
            raise ValueError("banned_element requires at least one element")
        if kind == "allowed_jurisdiction" and not self.allowed_jurisdictions:
            raise ValueError("allowed_jurisdiction requires at least one jurisdiction")
        if kind == "required_process_compatibility" and not self.required_route_keys:
            raise ValueError("required_process_compatibility requires at least one route key")
        if kind == "minimum_maturity" and not self.minimum_maturity:
            raise ValueError("minimum_maturity requires a stage")
        if self.category == "economic" and kind in {"max_value", "min_value", "range"}:
            # A monetary threshold without a basis cannot be compared to any evidence.
            if not self.currency or self.currency_year is None or not self.cost_basis:
                raise ValueError(
                    "MONETARY_BASIS_INCOMPLETE: an economic threshold requires currency, currency_year and cost_basis "
                    "so it can be compared on a like-for-like basis with evidence"
                )
        return self


class IndustrialConstraintOut(ORMModel):
    id: str
    project_id: str
    category: str
    constraint_kind: str
    metric_key: str | None
    display_label: str
    strength: str
    weight: float
    target_value: float | None
    target_value_upper: float | None
    target_unit: str | None
    currency: str | None
    currency_year: int | None
    cost_basis: str | None
    banned_elements: list[str]
    allowed_jurisdictions: list[str]
    required_route_keys: list[str]
    minimum_maturity: str | None
    minimum_supplier_count: int | None
    treat_missing_evidence_as: str
    rationale: str | None
    created_at: datetime


class MaturityAssessmentCreate(BaseModel):
    target_kind: TargetKind
    target_id: str
    stage: Literal[
        "theoretical", "computationally_evaluated", "experimentally_demonstrated",
        "laboratory_reproducible", "pilot_demonstrated", "manufacturing_demonstrated",
        "industrially_established",
    ]
    scope: str | None = None
    justification: str = Field(min_length=10, max_length=4000)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    as_of_date: date | None = None


class MaturityAssessmentOut(ORMModel):
    id: str
    material_id: str | None
    hypothesis_id: str | None
    stage: str
    scope: str | None
    justification: str
    supporting_evidence_ids: list[str]
    as_of_date: date | None
    superseded_by_id: str | None
    created_at: datetime


ALLOWED_COMPOSITE_DIMENSIONS = {
    "scientific_suitability", "manufacturing_compatibility", "economic_feasibility",
    "supply_resilience", "environmental_evidence", "regulatory_compatibility",
    "technology_maturity", "experimental_validation",
}

def _validate_composite_weights(weights: dict[str, float]) -> dict[str, float]:
    unknown = sorted(set(weights) - ALLOWED_COMPOSITE_DIMENSIONS)
    if unknown:
        raise ValueError(f"INVALID_COMPOSITE_WEIGHT: unknown dimension(s): {', '.join(unknown)}")
    for key, value in weights.items():
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"INVALID_COMPOSITE_WEIGHT: weight for {key} must be finite and >= 0")
    if weights and not any(float(v) > 0 for v in weights.values()):
        raise ValueError("INVALID_COMPOSITE_WEIGHT: at least one supplied weight must be > 0")
    return weights


class ViabilityAssessmentRequest(BaseModel):
    project_id: str
    target_kind: TargetKind
    target_id: str
    candidate_id: str | None = None
    composite_methodology: Literal["declared_weighted_mean_v1"] | None = None
    composite_weights: dict[str, float] = Field(default_factory=dict)
    persist: bool = True

    @model_validator(mode="after")
    def _safe_weights(self) -> "ViabilityAssessmentRequest":
        _validate_composite_weights(self.composite_weights)
        return self


class ViabilityComparisonRequest(BaseModel):
    project_id: str
    targets: list[dict[str, str]] = Field(min_length=1, max_length=50)
    composite_methodology: Literal["declared_weighted_mean_v1"] | None = None
    composite_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _safe_weights(self) -> "ViabilityComparisonRequest":
        _validate_composite_weights(self.composite_weights)
        return self


class ViabilityAssessmentOut(ORMModel):
    id: str
    project_id: str
    target_kind: str
    target_scientific_id: str
    candidate_id: str | None
    dimension_states: dict[str, Any]
    dimension_details: dict[str, Any]
    hard_constraint_failures: list[dict[str, Any]]
    soft_constraint_results: list[dict[str, Any]]
    unknown_dimensions: list[str]
    evidence_coverage: dict[str, Any]
    missing_evidence: list[dict[str, Any]]
    conflicting_evidence: list[dict[str, Any]]
    overall_state: str
    composite_score: float | None
    composite_methodology: str | None
    composite_weights: dict[str, Any]
    composite_is_partial: bool
    maturity_stage: str
    policy_version: str
    assessment_checksum: str
    superseded_by_id: str | None
    created_at: datetime
