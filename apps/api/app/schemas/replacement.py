"""Phase 10 — API schemas.

Response payloads are intentionally permissive (`dict[str, Any]` for the large analytical
structures) because the engines already produce fully-typed, documented, deterministic content and
re-declaring every nested shape here would duplicate that contract without adding a guarantee. The
*request* schemas are strict, because that is where invalid input can actually enter the system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReplacementProgramCreate(BaseModel):
    project_id: str
    key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    application_id: str | None = None
    application_component_id: str | None = None
    role_id: str | None = None
    application_name: str | None = Field(default=None, max_length=300)
    application_domain: str | None = Field(default=None, max_length=120)
    application_context: dict[str, Any] = Field(default_factory=dict)
    incumbent_material_id: str | None = None
    incumbent_state_id: str | None = None
    decision_policy_id: str | None = None
    validation_strategy: dict[str, Any] = Field(default_factory=dict)
    is_demonstration_data: bool = False
    created_by: str | None = None


class ReplacementProgramUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=300)
    description: str | None = None
    application_id: str | None = None
    application_component_id: str | None = None
    role_id: str | None = None
    application_name: str | None = Field(default=None, max_length=300)
    application_domain: str | None = Field(default=None, max_length=120)
    application_context: dict[str, Any] | None = None
    incumbent_material_id: str | None = None
    incumbent_state_id: str | None = None
    decision_policy_id: str | None = None
    validation_strategy: dict[str, Any] | None = None
    # Only PAUSED and ARCHIVED may be set; every other program state is resolved from evidence.
    status_override: str | None = None


class ReplacementProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organisation_id: str
    project_id: str
    key: str
    name: str
    description: str | None = None
    application_id: str | None = None
    application_component_id: str | None = None
    role_id: str | None = None
    application_name: str | None = None
    application_domain: str | None = None
    application_context: dict[str, Any] = Field(default_factory=dict)
    incumbent_material_id: str | None = None
    incumbent_state_id: str | None = None
    decision_policy_id: str | None = None
    decision_policy_version: str
    status: str
    status_override: str | None = None
    status_reason_codes: list[str] = Field(default_factory=list)
    validation_strategy: dict[str, Any] = Field(default_factory=dict)
    is_demonstration_data: bool = False
    created_at: datetime
    updated_at: datetime


class DecisionPolicyCreate(BaseModel):
    key: str | None = Field(default=None, max_length=120)
    display_name: str | None = Field(default=None, max_length=300)
    version: str | None = Field(default=None, max_length=40)
    description: str | None = None
    required_gates: list[str] | None = None
    minimum_evidence_requirements: dict[str, Any] | None = None
    required_experimental_validation: dict[str, Any] | None = None
    industrial_gate_requirements: dict[str, Any] | None = None
    allowed_unresolved_statuses: list[str] | None = None
    ranking_weights: dict[str, float] | None = None
    sensitivity_bounds: dict[str, Any] | None = None
    auto_reject_on_experimental_contradiction: bool | None = None
    created_by: str | None = None


class DecisionPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organisation_id: str
    key: str
    display_name: str
    version: str
    description: str | None = None
    required_gates: list[str] = Field(default_factory=list)
    minimum_evidence_requirements: dict[str, Any] = Field(default_factory=dict)
    required_experimental_validation: dict[str, Any] = Field(default_factory=dict)
    industrial_gate_requirements: dict[str, Any] = Field(default_factory=dict)
    allowed_unresolved_statuses: list[str] = Field(default_factory=list)
    ranking_weights: dict[str, Any] = Field(default_factory=dict)
    sensitivity_bounds: dict[str, Any] = Field(default_factory=dict)
    auto_reject_on_experimental_contradiction: bool
    is_active: bool
    policy_checksum: str
    created_at: datetime


class RequirementGateUpdate(BaseModel):
    """Set the decision-gate metadata on an existing functional requirement."""

    criticality: str | None = None
    requirement_origin: str | None = None
    approval_status: str | None = None
    proposed_by: str | None = Field(default=None, max_length=80)
    approved_by: str | None = None


class ScientificActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    candidate_id: str | None = None
    requirement_id: str | None = None
    action_type: str
    action_signature: str
    status: str
    priority: float
    priority_factors: dict[str, Any] = Field(default_factory=dict)
    decision_value_class: str
    cost_class: str
    reason_code: str
    reason: str
    resolves_gap_kind: str | None = None
    what_it_could_resolve: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    result_reference: dict[str, Any] = Field(default_factory=dict)
    methodology_version: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ActionTransitionRequest(BaseModel):
    # `execute` records that an authorized platform workflow has begun; it never starts one itself.
    transition: str = Field(pattern="^(accept|defer|cancel|execute|complete|fail)$")
    note: str | None = None
    result_reference: dict[str, Any] = Field(default_factory=dict)


class RecommendationCreateRequest(BaseModel):
    created_by: str | None = None


class SnapshotCreateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200)
    created_by: str | None = None


class DossierCreateRequest(BaseModel):
    candidate_id: str | None = None
    snapshot_id: str | None = None
    created_by: str | None = None


class RecomputeRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list)
    persist: bool = True


class EvidenceEventRequest(BaseModel):
    """Notify the program that upstream evidence changed, triggering scoped reassessment."""

    event_kind: str
    summary: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    reference_kind: str | None = None
    reference_id: str | None = None
    actor_user_id: str | None = None


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    candidate_id: str | None = None
    requirement_id: str | None = None
    event_kind: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reference_kind: str | None = None
    reference_id: str | None = None
    actor_user_id: str | None = None
    occurred_at: datetime


class ReplacementRecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    version: int
    status: str
    recommended_candidate_ids: list[str] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)
    held_candidate_ids: list[str] = Field(default_factory=list)
    incumbent_reference: dict[str, Any] = Field(default_factory=dict)
    requirement_summary: dict[str, Any] = Field(default_factory=dict)
    per_candidate: list[dict[str, Any]] = Field(default_factory=list)
    blocking_requirements: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_requirements: list[dict[str, Any]] = Field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[dict[str, Any]] = Field(default_factory=list)
    ranking: dict[str, Any] = Field(default_factory=dict)
    pareto: dict[str, Any] = Field(default_factory=dict)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    convergence_state: str
    convergence_assessment_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str
    decision_policy_version: str
    methodology_versions: dict[str, Any] = Field(default_factory=dict)
    assessment_refs: dict[str, Any] = Field(default_factory=dict)
    qualification_note: str
    recommendation_checksum: str
    superseded_by_id: str | None = None
    created_at: datetime


class ConvergenceAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    convergence_state: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    per_candidate: list[dict[str, Any]] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    presentation_progress_percent: float
    decision_policy_version: str
    methodology_version: str
    assessment_checksum: str
    created_at: datetime


class ProgramSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    label: str | None = None
    requirements_ref: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_ref: list[dict[str, Any]] = Field(default_factory=list)
    material_states_ref: list[dict[str, Any]] = Field(default_factory=list)
    scientific_evidence_ref: list[dict[str, Any]] = Field(default_factory=list)
    industrial_evidence_ref: list[dict[str, Any]] = Field(default_factory=list)
    experimental_evidence_ref: list[dict[str, Any]] = Field(default_factory=list)
    decision_policy_ref: dict[str, Any] = Field(default_factory=dict)
    methodology_versions: dict[str, Any] = Field(default_factory=dict)
    convergence_assessment_id: str | None = None
    recommendation_id: str | None = None
    snapshot_checksum: str
    created_at: datetime


class TechnicalDossierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    program_id: str
    version: int
    candidate_id: str | None = None
    title: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_id: str | None = None
    recommendation_id: str | None = None
    convergence_assessment_id: str | None = None
    assessment_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    methodology_versions: dict[str, Any] = Field(default_factory=dict)
    decision_policy_version: str
    llm_narrative_used: bool
    dossier_checksum: str
    generated_at: datetime
    created_at: datetime
