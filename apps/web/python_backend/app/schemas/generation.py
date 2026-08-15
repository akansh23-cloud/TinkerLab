from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class SearchSpaceComponentRuleIn(BaseModel):
    baseline_component_id: str | None = None
    component_key: str = Field(min_length=1, max_length=300)
    display_name: str = Field(min_length=1, max_length=300)
    role: str | None = None
    locked: bool = False
    mutable: bool = False
    required: bool = False
    prohibited: bool = False
    min_amount: float | None = None
    max_amount: float | None = None
    step_amount: float | None = None
    amount_unit: str | None = None
    amount_basis: str | None = None
    sequence: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def shape(self):
        if self.prohibited and (self.required or self.locked or self.mutable):
            raise ValueError("Prohibited component cannot also be required/locked/mutable")
        if self.min_amount is not None and self.max_amount is not None and self.max_amount < self.min_amount:
            raise ValueError("max_amount must be >= min_amount")
        if self.step_amount is not None and self.step_amount <= 0:
            raise ValueError("step_amount must be > 0")
        if self.mutable and (self.min_amount is None or self.max_amount is None):
            raise ValueError("Mutable component requires min_amount and max_amount")
        return self


class SearchSpaceProcessRuleIn(BaseModel):
    parameter_key: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=240)
    min_value: float
    max_value: float
    step_value: float | None = None
    unit: str = Field(min_length=1, max_length=80)
    locked: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def shape(self):
        if self.max_value < self.min_value:
            raise ValueError("max_value must be >= min_value")
        if self.step_value is not None and self.step_value <= 0:
            raise ValueError("step_value must be > 0")
        return self


class SearchSpaceCreate(BaseModel):
    material_family: str
    amount_basis: str = "weight_percent"
    balance_component_key: str | None = None
    total_target: float | None = 100.0
    total_tolerance: float = Field(default=0.001, ge=0)
    max_component_count: int = Field(default=20, ge=1, le=100)
    candidate_budget: int = Field(default=100, ge=1, le=1000)
    maximum_enumeration: int = Field(default=10000, ge=1, le=100000)
    notes: str | None = None
    component_rules: list[SearchSpaceComponentRuleIn] = Field(default_factory=list)
    process_rules: list[SearchSpaceProcessRuleIn] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchSpaceComponentRuleOut(ORMModel):
    id: str
    baseline_component_id: str | None
    component_key: str
    display_name: str
    role: str | None
    locked: bool
    mutable: bool
    required: bool
    prohibited: bool
    min_amount: float | None
    max_amount: float | None
    step_amount: float | None
    amount_unit: str | None
    amount_basis: str | None
    sequence: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class SearchSpaceProcessRuleOut(ORMModel):
    id: str
    parameter_key: str
    display_name: str
    min_value: float
    max_value: float
    step_value: float | None
    unit: str
    locked: bool
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class SearchSpaceOut(ORMModel):
    id: str
    project_id: str
    organisation_id: str
    version: int
    material_family: str
    amount_basis: str
    balance_component_key: str | None
    total_target: float | None
    total_tolerance: float
    max_component_count: int
    candidate_budget: int
    maximum_enumeration: int
    notes: str | None
    active: bool
    checksum: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    component_rules: list[SearchSpaceComponentRuleOut]
    process_rules: list[SearchSpaceProcessRuleOut]


class ValidationIssue(BaseModel):
    code: str
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


class SearchSpaceValidationOut(BaseModel):
    valid: bool
    estimated_cardinality: int
    issues: list[ValidationIssue]
    checksum: str


class SubstitutionRuleCreate(BaseModel):
    material_family: str
    source_component_key: str
    replacement_component_key: str
    replacement_display_name: str
    allowed_min_amount: float | None = None
    allowed_max_amount: float | None = None
    amount_basis: str | None = None
    reason: str = Field(min_length=3)
    evidence_id: str | None = None
    status: Literal["draft", "approved", "disabled"] = "draft"

    @model_validator(mode="after")
    def bounds(self):
        if self.allowed_min_amount is not None and self.allowed_max_amount is not None and self.allowed_max_amount < self.allowed_min_amount:
            raise ValueError("allowed_max_amount must be >= allowed_min_amount")
        if self.source_component_key == self.replacement_component_key:
            raise ValueError("Replacement component must differ from source")
        return self


class SubstitutionRuleOut(ORMModel):
    id: str
    organisation_id: str
    project_id: str | None
    material_family: str
    source_component_key: str
    replacement_component_key: str
    replacement_display_name: str
    allowed_min_amount: float | None
    allowed_max_amount: float | None
    amount_basis: str | None
    reason: str
    evidence_id: str | None
    status: str
    version: int
    created_at: datetime


class StrategyDescriptor(BaseModel):
    key: str
    version: str
    supported_material_families: list[str]
    required_inputs: list[str]
    creates_hypotheses: bool
    deterministic: bool
    maximum_safe_candidate_count: int
    description: str


class GenerationPreviewRequest(BaseModel):
    search_space_id: str
    strategy_key: str
    random_seed: int = 0
    candidate_budget: int | None = Field(default=None, ge=1, le=1000)
    configuration: dict[str, Any] = Field(default_factory=dict)


class GenerationPreviewOut(BaseModel):
    valid: bool
    strategy: StrategyDescriptor
    specification_checksum: str
    search_space_checksum: str
    search_space_version: int
    configuration_checksum: str
    random_seed: int
    candidate_budget: int
    estimated_cardinality: int
    expected_truncation: bool
    issues: list[ValidationIssue]


class GenerationRunCreate(GenerationPreviewRequest):
    created_by: str


class GenerationRunOut(ORMModel):
    id: str
    project_id: str
    organisation_id: str
    replacement_specification_checksum: str
    search_space_id: str
    search_space_version: int
    search_space_checksum: str
    strategy_key: str
    strategy_version: str
    configuration_checksum: str
    random_seed: int
    requested_candidate_budget: int
    generated_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    result_checksum: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_by: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime


class HypothesisComponentInput(BaseModel):
    component_key: str
    display_name: str
    role: str | None = None
    amount: float | None = None
    unit: str | None = None
    basis: str | None = None
    source_baseline_component_id: str | None = None
    substitution_rule_id: str | None = None
    locked: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HypothesisProcessInput(BaseModel):
    process_label: str = "proposed process state"
    parameter_key: str
    value: float
    unit: str
    source_baseline_state_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ManualHypothesisCreate(BaseModel):
    display_label: str = Field(min_length=3, max_length=300)
    material_family: str
    components: list[HypothesisComponentInput] = Field(min_length=1)
    process_parameters: list[HypothesisProcessInput] = Field(default_factory=list)
    notes: str | None = None


class HypothesisComponentOut(ORMModel):
    id: str
    sequence: int
    component_key: str
    display_name: str
    role: str | None
    amount: float | None
    unit: str | None
    basis: str | None
    source_baseline_component_id: str | None
    substitution_rule_id: str | None
    locked: bool
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class HypothesisProcessOut(ORMModel):
    id: str
    process_label: str
    parameter_key: str
    value: float
    unit: str
    source_baseline_state_id: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class ChangeRecordOut(ORMModel):
    id: str
    sequence: int
    change_type: str
    target_path: str
    before_value: dict[str, Any]
    after_value: dict[str, Any]
    substitution_rule_id: str | None
    rationale: str


class LineageEdgeOut(ORMModel):
    id: str
    child_hypothesis_id: str
    parent_material_id: str | None
    parent_candidate_id: str | None
    parent_hypothesis_id: str | None
    relationship_type: str
    generation_run_id: str | None
    sequence: int
    rationale: str


class CandidateHypothesisOut(ORMModel):
    id: str
    project_id: str
    organisation_id: str
    display_label: str
    material_family: str
    baseline_material_id: str
    generation_run_id: str | None
    generator_strategy_key: str
    generator_strategy_version: str
    deterministic_fingerprint: str
    fingerprint_version: str
    status: str
    structural_validity: str
    rejection_reason: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    components: list[HypothesisComponentOut]
    process_parameters: list[HypothesisProcessOut]
    changes: list[ChangeRecordOut]
    warning: str = "Hypothesis — not yet predicted, simulated, or experimentally validated."


class CandidateListItem(BaseModel):
    id: str
    project_id: str
    candidate_kind: str
    material_id: str | None = None
    hypothesis_id: str | None = None
    display_name: str
    candidate_source: str
    status: str
    structural_validity: str | None = None
    deterministic_fingerprint: str | None = None
    generation_run_id: str | None = None
    evidence_posture: str
    change_count: int = 0
    hard_passed: int = 0
    hard_failed: int = 0
    hard_unknown: int = 0
    evidence_completeness: float = 0.0
    scientific_conflicts: int = 0
    created_at: datetime


class CandidatePage(BaseModel):
    items: list[CandidateListItem]
    total: int
    offset: int
    limit: int
