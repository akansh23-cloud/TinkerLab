from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel

MutationType = Literal["component_amount", "component_substitution", "process_parameter"]
DEFAULT_MUTATION_TYPES: tuple[MutationType, ...] = ("component_amount", "component_substitution", "process_parameter")


class CampaignObjectiveIn(BaseModel):
    property_key: str
    direction: Literal["maximize", "minimize", "target"]
    weight: float = Field(default=1.0, gt=0)
    priority: int = Field(default=1, ge=1)
    target_value: float | None = None
    target_unit: str | None = None
    model_version_id: str
    evaluation_mode: str = "model_prediction"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def target_requirements(self):
        if self.direction == "target" and (self.target_value is None or not self.target_unit):
            raise ValueError("target objectives require target_value and target_unit")
        return self


class CampaignConstraintPolicyIn(BaseModel):
    constraint_id: str
    model_version_id: str | None = None
    allowed_value_origin: Literal[
        "known_evidence_only",
        "model_prediction_only",
        "known_evidence_then_prediction",
    ] = "known_evidence_then_prediction"
    unknown_handling: Literal["retain_uncertain", "exclude_from_parent_selection"] = "retain_uncertain"
    condition_mapping: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class VirtualCampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=300)
    description: str | None = None
    search_space_id: str
    policy_key: Literal["robust_pareto_v1", "uncertainty_exploration_v1", "lexicographic_pareto_baseline_v1"] = "robust_pareto_v1"
    random_seed: int = 0
    max_iterations: int = Field(default=2, ge=1, le=5)
    max_total_new_candidates: int = Field(default=50, ge=0, le=500)
    max_candidates_per_iteration: int = Field(default=25, ge=1, le=200)
    max_parents_per_iteration: int = Field(default=5, ge=0, le=100)
    created_by: str
    objectives: list[CampaignObjectiveIn] = Field(min_length=1, max_length=5)
    constraint_policies: list[CampaignConstraintPolicyIn] = Field(default_factory=list)
    initial_candidate_ids: list[str] = Field(default_factory=list, max_length=200)
    include_known_candidates: bool = True
    exploration_enabled: bool = True
    mutation_types: list[MutationType] = Field(default_factory=lambda: list(DEFAULT_MUTATION_TYPES))
    convergence_unchanged_iterations: int | None = Field(default=None, ge=2, le=5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignObjectiveOut(ORMModel):
    id: str
    campaign_id: str
    property_key: str
    direction: str
    weight: float
    priority: int
    target_value: float | None
    target_unit: str | None
    model_version_id: str
    evaluation_mode: str
    sequence: int
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class CampaignConstraintPolicyOut(ORMModel):
    id: str
    campaign_id: str
    constraint_id: str
    model_version_id: str | None
    allowed_value_origin: str
    unknown_handling: str
    condition_mapping: dict[str, Any]
    enabled: bool
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class VirtualCampaignOut(ORMModel):
    id: str
    organisation_id: str
    project_id: str
    name: str
    description: str | None
    replacement_specification_checksum: str
    search_space_id: str
    search_space_version: int
    search_space_checksum: str
    policy_key: str
    policy_version: str
    configuration_checksum: str
    random_seed: int
    max_iterations: int
    max_total_new_candidates: int
    max_candidates_per_iteration: int
    max_parents_per_iteration: int
    status: str
    stop_reason: str | None
    created_by: str
    started_at: datetime | None
    completed_at: datetime | None
    result_checksum: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class CampaignValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    path: str | None = None


class CampaignPreviewOut(BaseModel):
    valid: bool
    campaign_id: str
    policy_key: str
    policy_version: str
    specification_checksum: str
    search_space_checksum: str
    configuration_checksum: str
    candidate_pool_size: int
    objective_count: int
    objective_models: list[dict[str, Any]]
    applicability_forecast: dict[str, dict[str, int]]
    estimated_prediction_runs: int
    estimated_mutation_cardinality: int
    budgets: dict[str, int]
    validation_issues: list[CampaignValidationIssue]
    warning: str = "VIRTUAL EVALUATION — MODEL-BASED; not a physical experiment or physics simulation."


class CampaignIterationOut(ORMModel):
    id: str
    campaign_id: str
    iteration_number: int
    input_pool_checksum: str
    parent_selection_checksum: str | None
    generation_run_ids: list[str]
    prediction_run_ids: list[str]
    evaluated_candidate_count: int
    feasible_count: int
    uncertain_count: int
    infeasible_count: int
    pareto_front_count: int
    pareto_front_checksum: str | None
    selected_for_exploration_count: int
    new_candidate_count: int
    duplicate_count: int
    decision_checksum: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    stop_signal: bool
    stop_reason: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class VirtualCandidateEvaluationOut(ORMModel):
    id: str
    campaign_iteration_id: str
    candidate_id: str
    hypothesis_id: str | None
    feasibility_class: str
    hard_pass_count: int
    hard_fail_count: int
    hard_unknown_count: int
    objective_vector: dict[str, Any]
    objective_intervals: dict[str, Any]
    objective_origins: dict[str, Any]
    pareto_rank: int | None
    dominance_count: int
    diversity_metric: float | None
    uncertainty_burden: dict[str, Any]
    normalized_utility_components: dict[str, Any]
    acquisition_components: dict[str, Any]
    selected_as_parent: bool
    selected_for_next_evaluation: bool
    disposition: str
    rationale: str
    deterministic_evaluation_checksum: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    scientific_origin: str = "VIRTUAL EVALUATION — MODEL-BASED"


class EvaluationPage(BaseModel):
    items: list[VirtualCandidateEvaluationOut]
    total: int
    offset: int
    limit: int


class ParetoFrontOut(ORMModel):
    id: str
    campaign_iteration_id: str
    front_number: int
    ordered_candidate_ids: list[str]
    objective_space_checksum: str
    policy_key: str
    policy_version: str
    created_at: datetime


class DecisionRecordOut(ORMModel):
    id: str
    campaign_id: str
    campaign_iteration_id: str
    candidate_id: str | None
    hypothesis_id: str | None
    sequence: int
    decision_type: str
    policy_key: str
    policy_version: str
    input_checksum: str
    metrics: dict[str, Any]
    rationale: str
    created_at: datetime


class CampaignRunRequest(BaseModel):
    max_iterations: int | None = Field(default=None, ge=1, le=5)


class CampaignRunResult(BaseModel):
    campaign: VirtualCampaignOut
    iterations: list[CampaignIterationOut]
    final_front_candidate_ids: list[str]
    warning: str = "VIRTUAL EVALUATION — MODEL-BASED; not a physical experiment or physics simulation."
