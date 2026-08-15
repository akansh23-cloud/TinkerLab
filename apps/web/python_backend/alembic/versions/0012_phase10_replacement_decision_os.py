"""Phase 10 Closed-Loop Material Replacement Decision OS.

Revision ID: 0012_phase10
Revises: 0011_phase9_1b

Forward-only and additive. No previous migration is modified and no existing column is dropped or
retyped, so a Phase-9.1 database upgrades without any pre-Phase-10 conclusion changing.

The one change to an existing table adds decision-gate metadata to `functional_requirements`.
Existing rows are backfilled deterministically from `requirement_kind` using exactly the mapping in
`app/services/replacement/policy.py::CRITICALITY_FROM_KIND`, so criticality introduces no new
behaviour for data that already exists — it only makes the existing behaviour explicit and editable.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0012_phase10"
down_revision = "0011_phase9_1b"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # ------------------------------------------------------------------------------------------
    # Requirement decision-gate metadata
    # ------------------------------------------------------------------------------------------
    op.add_column("functional_requirements", sa.Column("criticality", sa.String(length=30), nullable=True))
    op.add_column("functional_requirements", sa.Column("requirement_origin", sa.String(length=40), nullable=True))
    op.add_column("functional_requirements", sa.Column("approval_status", sa.String(length=20), nullable=True))
    op.add_column("functional_requirements", sa.Column("proposed_by", sa.String(length=80), nullable=True))
    op.add_column("functional_requirements", sa.Column("approved_by", sa.String(length=36), nullable=True))
    op.add_column("functional_requirements", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("functional_requirements", sa.Column("requirement_version", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_functional_requirements_approved_by", "functional_requirements", "users",
        ["approved_by"], ["id"], ondelete="SET NULL",
    )

    # Deterministic backfill. hard_constraint already gated advancement in Phase 8/9.1, so it maps to
    # BLOCKING; objectives were already ranked rather than gated, so they map to DESIRABLE.
    op.execute("UPDATE functional_requirements SET criticality = 'blocking' WHERE requirement_kind = 'hard_constraint' AND criticality IS NULL")
    op.execute("UPDATE functional_requirements SET criticality = 'important' WHERE requirement_kind = 'soft_constraint' AND criticality IS NULL")
    op.execute("UPDATE functional_requirements SET criticality = 'desirable' WHERE requirement_kind IN ('objective', 'preference') AND criticality IS NULL")
    op.execute("UPDATE functional_requirements SET criticality = 'informational' WHERE requirement_kind = 'informational' AND criticality IS NULL")
    op.execute("UPDATE functional_requirements SET criticality = 'important' WHERE criticality IS NULL")
    # Existing rows were created explicitly through the Phase-8 API by a user, so USER_DEFINED and
    # ACCEPTED are the honest backfill. Nothing pre-existing is retroactively labelled as inferred.
    op.execute("UPDATE functional_requirements SET requirement_origin = 'user_defined' WHERE requirement_origin IS NULL")
    op.execute("UPDATE functional_requirements SET approval_status = 'accepted' WHERE approval_status IS NULL")
    op.execute("UPDATE functional_requirements SET requirement_version = 1 WHERE requirement_version IS NULL")

    op.alter_column("functional_requirements", "criticality", nullable=False)
    op.alter_column("functional_requirements", "requirement_origin", nullable=False)
    op.alter_column("functional_requirements", "approval_status", nullable=False)
    op.alter_column("functional_requirements", "requirement_version", nullable=False)
    op.create_index("ix_functional_requirements_criticality", "functional_requirements", ["criticality"])
    op.create_index("ix_functional_requirements_requirement_origin", "functional_requirements", ["requirement_origin"])
    op.create_index("ix_functional_requirements_approval_status", "functional_requirements", ["approval_status"])

    # ------------------------------------------------------------------------------------------
    # Decision policy
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "decision_policies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("required_gates", JSON, nullable=False),
        sa.Column("minimum_evidence_requirements", JSON, nullable=False),
        sa.Column("required_experimental_validation", JSON, nullable=False),
        sa.Column("industrial_gate_requirements", JSON, nullable=False),
        sa.Column("allowed_unresolved_statuses", JSON, nullable=False),
        sa.Column("ranking_weights", JSON, nullable=False),
        sa.Column("sensitivity_bounds", JSON, nullable=False),
        sa.Column("auto_reject_on_experimental_contradiction", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("policy_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organisation_id", "key", "version", name="uq_decision_policy_scope_version"),
    )
    op.create_index("ix_decision_policies_organisation_id", "decision_policies", ["organisation_id"])
    op.create_index("ix_decision_policies_key", "decision_policies", ["key"])
    op.create_index("ix_decision_policies_is_active", "decision_policies", ["is_active"])
    op.create_index("ix_decision_policy_active", "decision_policies", ["organisation_id", "key", "is_active"])

    # ------------------------------------------------------------------------------------------
    # Replacement program
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "replacement_programs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("application_id", sa.String(length=36), sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True),
        sa.Column("application_component_id", sa.String(length=36), sa.ForeignKey("application_components.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_id", sa.String(length=36), sa.ForeignKey("material_roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("application_name", sa.String(length=300), nullable=True),
        sa.Column("application_domain", sa.String(length=120), nullable=True),
        sa.Column("application_context", JSON, nullable=False),
        sa.Column("incumbent_material_id", sa.String(length=36), sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("incumbent_state_id", sa.String(length=36), sa.ForeignKey("material_states.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_policy_id", sa.String(length=36), sa.ForeignKey("decision_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_policy_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("status_override", sa.String(length=40), nullable=True),
        sa.Column("status_reason_codes", JSON, nullable=False),
        sa.Column("validation_strategy", JSON, nullable=False),
        sa.Column("is_demonstration_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organisation_id", "key", name="uq_replacement_program_scope_key"),
    )
    for column in ("organisation_id", "project_id", "key", "application_id", "application_component_id",
                   "role_id", "application_domain", "incumbent_material_id", "incumbent_state_id",
                   "decision_policy_id", "status", "is_demonstration_data"):
        op.create_index(f"ix_replacement_programs_{column}", "replacement_programs", [column])
    op.create_index("ix_replacement_program_project", "replacement_programs", ["project_id", "status"])

    # ------------------------------------------------------------------------------------------
    # Scientific actions
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "scientific_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("requirement_id", sa.String(length=36), sa.ForeignKey("functional_requirements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(length=60), nullable=False),
        sa.Column("action_signature", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Float(), nullable=False),
        sa.Column("priority_factors", JSON, nullable=False),
        sa.Column("decision_value_class", sa.String(length=20), nullable=False),
        sa.Column("cost_class", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolves_gap_kind", sa.String(length=60), nullable=True),
        sa.Column("what_it_could_resolve", sa.Text(), nullable=True),
        sa.Column("depends_on", JSON, nullable=False),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("result_reference", JSON, nullable=False),
        sa.Column("methodology_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("organisation_id", "program_id", "candidate_id", "requirement_id",
                   "action_type", "status", "priority", "supersedes_id", "superseded_by_id"):
        op.create_index(f"ix_scientific_actions_{column}", "scientific_actions", [column])
    op.create_index("ix_scientific_action_scope", "scientific_actions", ["program_id", "candidate_id", "status"])
    op.create_index("ix_scientific_action_signature", "scientific_actions", ["program_id", "action_signature"])

    # ------------------------------------------------------------------------------------------
    # Evidence gap snapshots
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "evidence_gap_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("gaps", JSON, nullable=False),
        sa.Column("blocking_gap_count", sa.Integer(), nullable=False),
        sa.Column("high_value_gap_count", sa.Integer(), nullable=False),
        sa.Column("coverage", JSON, nullable=False),
        sa.Column("methodology_version", sa.String(length=60), nullable=False),
        sa.Column("gap_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evidence_gap_snapshots_organisation_id", "evidence_gap_snapshots", ["organisation_id"])
    op.create_index("ix_evidence_gap_snapshots_program_id", "evidence_gap_snapshots", ["program_id"])
    op.create_index("ix_evidence_gap_snapshots_candidate_id", "evidence_gap_snapshots", ["candidate_id"])
    op.create_index("ix_evidence_gap_snapshot_scope", "evidence_gap_snapshots", ["program_id", "created_at"])

    # ------------------------------------------------------------------------------------------
    # Convergence assessments
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "convergence_assessments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("convergence_state", sa.String(length=40), nullable=False),
        sa.Column("metrics", JSON, nullable=False),
        sa.Column("per_candidate", JSON, nullable=False),
        sa.Column("reason_codes", JSON, nullable=False),
        sa.Column("reasons", JSON, nullable=False),
        sa.Column("presentation_progress_percent", sa.Float(), nullable=False),
        sa.Column("decision_policy_version", sa.String(length=40), nullable=False),
        sa.Column("methodology_version", sa.String(length=60), nullable=False),
        sa.Column("assessment_checksum", sa.String(length=64), nullable=False),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_convergence_assessments_organisation_id", "convergence_assessments", ["organisation_id"])
    op.create_index("ix_convergence_assessments_program_id", "convergence_assessments", ["program_id"])
    op.create_index("ix_convergence_assessments_convergence_state", "convergence_assessments", ["convergence_state"])
    op.create_index("ix_convergence_assessments_superseded_by_id", "convergence_assessments", ["superseded_by_id"])
    op.create_index("ix_convergence_scope", "convergence_assessments", ["program_id", "created_at"])
    op.create_index("ix_convergence_checksum", "convergence_assessments", ["assessment_checksum"])

    # ------------------------------------------------------------------------------------------
    # Replacement recommendations
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "replacement_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("recommended_candidate_ids", JSON, nullable=False),
        sa.Column("rejected_candidate_ids", JSON, nullable=False),
        sa.Column("held_candidate_ids", JSON, nullable=False),
        sa.Column("incumbent_reference", JSON, nullable=False),
        sa.Column("requirement_summary", JSON, nullable=False),
        sa.Column("per_candidate", JSON, nullable=False),
        sa.Column("blocking_requirements", JSON, nullable=False),
        sa.Column("unresolved_requirements", JSON, nullable=False),
        sa.Column("conflicting_evidence", JSON, nullable=False),
        sa.Column("evidence_gaps", JSON, nullable=False),
        sa.Column("next_actions", JSON, nullable=False),
        sa.Column("ranking", JSON, nullable=False),
        sa.Column("pareto", JSON, nullable=False),
        sa.Column("sensitivity", JSON, nullable=False),
        sa.Column("convergence_state", sa.String(length=40), nullable=False),
        sa.Column("convergence_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("reason_codes", JSON, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decision_policy_id", sa.String(length=36), nullable=True),
        sa.Column("decision_policy_version", sa.String(length=40), nullable=False),
        sa.Column("methodology_versions", JSON, nullable=False),
        sa.Column("assessment_refs", JSON, nullable=False),
        sa.Column("qualification_note", sa.Text(), nullable=False),
        sa.Column("recommendation_checksum", sa.String(length=64), nullable=False),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("program_id", "version", name="uq_replacement_recommendation_version"),
    )
    op.create_index("ix_replacement_recommendations_organisation_id", "replacement_recommendations", ["organisation_id"])
    op.create_index("ix_replacement_recommendations_program_id", "replacement_recommendations", ["program_id"])
    op.create_index("ix_replacement_recommendations_status", "replacement_recommendations", ["status"])
    op.create_index("ix_replacement_recommendations_convergence_assessment_id", "replacement_recommendations", ["convergence_assessment_id"])
    op.create_index("ix_replacement_recommendations_decision_policy_id", "replacement_recommendations", ["decision_policy_id"])
    op.create_index("ix_replacement_recommendations_superseded_by_id", "replacement_recommendations", ["superseded_by_id"])
    op.create_index("ix_replacement_recommendation_scope", "replacement_recommendations", ["program_id", "version"])
    op.create_index("ix_replacement_recommendation_checksum", "replacement_recommendations", ["recommendation_checksum"])

    # ------------------------------------------------------------------------------------------
    # Decision deltas
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "decision_deltas",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("previous_recommendation_id", sa.String(length=36), nullable=True),
        sa.Column("new_recommendation_id", sa.String(length=36), nullable=False),
        sa.Column("previous_status", sa.String(length=40), nullable=True),
        sa.Column("new_status", sa.String(length=40), nullable=False),
        sa.Column("changed_requirements", JSON, nullable=False),
        sa.Column("new_evidence", JSON, nullable=False),
        sa.Column("invalidated_evidence", JSON, nullable=False),
        sa.Column("changed_ranking", JSON, nullable=False),
        sa.Column("changed_blockers", JSON, nullable=False),
        sa.Column("reason_codes", JSON, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("methodology_version", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_decision_deltas_organisation_id", "decision_deltas", ["organisation_id"])
    op.create_index("ix_decision_deltas_program_id", "decision_deltas", ["program_id"])
    op.create_index("ix_decision_deltas_previous_recommendation_id", "decision_deltas", ["previous_recommendation_id"])
    op.create_index("ix_decision_deltas_new_recommendation_id", "decision_deltas", ["new_recommendation_id"])
    op.create_index("ix_decision_delta_scope", "decision_deltas", ["program_id", "created_at"])

    # ------------------------------------------------------------------------------------------
    # Program snapshots
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "replacement_program_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("requirements_ref", JSON, nullable=False),
        sa.Column("portfolio_ref", JSON, nullable=False),
        sa.Column("material_states_ref", JSON, nullable=False),
        sa.Column("scientific_evidence_ref", JSON, nullable=False),
        sa.Column("industrial_evidence_ref", JSON, nullable=False),
        sa.Column("experimental_evidence_ref", JSON, nullable=False),
        sa.Column("decision_policy_ref", JSON, nullable=False),
        sa.Column("methodology_versions", JSON, nullable=False),
        sa.Column("convergence_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("recommendation_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_replacement_program_snapshots_organisation_id", "replacement_program_snapshots", ["organisation_id"])
    op.create_index("ix_replacement_program_snapshots_program_id", "replacement_program_snapshots", ["program_id"])
    op.create_index("ix_replacement_program_snapshots_convergence_assessment_id", "replacement_program_snapshots", ["convergence_assessment_id"])
    op.create_index("ix_replacement_program_snapshots_recommendation_id", "replacement_program_snapshots", ["recommendation_id"])
    op.create_index("ix_program_snapshot_scope", "replacement_program_snapshots", ["program_id", "created_at"])
    op.create_index("ix_program_snapshot_checksum", "replacement_program_snapshots", ["snapshot_checksum"])

    # ------------------------------------------------------------------------------------------
    # Technical dossiers
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "technical_dossiers",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("sections", JSON, nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("recommendation_id", sa.String(length=36), nullable=True),
        sa.Column("convergence_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("assessment_ids", JSON, nullable=False),
        sa.Column("evidence_ids", JSON, nullable=False),
        sa.Column("methodology_versions", JSON, nullable=False),
        sa.Column("decision_policy_version", sa.String(length=40), nullable=False),
        sa.Column("llm_narrative_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dossier_checksum", sa.String(length=64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("program_id", "version", name="uq_technical_dossier_version"),
    )
    op.create_index("ix_technical_dossiers_organisation_id", "technical_dossiers", ["organisation_id"])
    op.create_index("ix_technical_dossiers_program_id", "technical_dossiers", ["program_id"])
    op.create_index("ix_technical_dossiers_candidate_id", "technical_dossiers", ["candidate_id"])
    op.create_index("ix_technical_dossiers_snapshot_id", "technical_dossiers", ["snapshot_id"])
    op.create_index("ix_technical_dossiers_recommendation_id", "technical_dossiers", ["recommendation_id"])
    op.create_index("ix_technical_dossiers_convergence_assessment_id", "technical_dossiers", ["convergence_assessment_id"])
    op.create_index("ix_technical_dossier_scope", "technical_dossiers", ["program_id", "created_at"])

    # ------------------------------------------------------------------------------------------
    # Program timeline
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "program_timeline_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("program_id", sa.String(length=36), sa.ForeignKey("replacement_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("requirement_id", sa.String(length=36), nullable=True),
        sa.Column("event_kind", sa.String(length=60), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", JSON, nullable=False),
        sa.Column("reference_kind", sa.String(length=60), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_program_timeline_events_organisation_id", "program_timeline_events", ["organisation_id"])
    op.create_index("ix_program_timeline_events_program_id", "program_timeline_events", ["program_id"])
    op.create_index("ix_program_timeline_events_candidate_id", "program_timeline_events", ["candidate_id"])
    op.create_index("ix_program_timeline_events_requirement_id", "program_timeline_events", ["requirement_id"])
    op.create_index("ix_program_timeline_events_event_kind", "program_timeline_events", ["event_kind"])
    op.create_index("ix_program_timeline_events_reference_id", "program_timeline_events", ["reference_id"])
    op.create_index("ix_program_timeline_events_occurred_at", "program_timeline_events", ["occurred_at"])
    op.create_index("ix_program_timeline_scope", "program_timeline_events", ["program_id", "occurred_at"])
    op.create_index("ix_program_timeline_candidate", "program_timeline_events", ["program_id", "candidate_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("program_timeline_events")
    op.drop_table("technical_dossiers")
    op.drop_table("replacement_program_snapshots")
    op.drop_table("decision_deltas")
    op.drop_table("replacement_recommendations")
    op.drop_table("convergence_assessments")
    op.drop_table("evidence_gap_snapshots")
    op.drop_table("scientific_actions")
    op.drop_table("replacement_programs")
    op.drop_table("decision_policies")

    op.drop_index("ix_functional_requirements_approval_status", table_name="functional_requirements")
    op.drop_index("ix_functional_requirements_requirement_origin", table_name="functional_requirements")
    op.drop_index("ix_functional_requirements_criticality", table_name="functional_requirements")
    op.drop_constraint("fk_functional_requirements_approved_by", "functional_requirements", type_="foreignkey")
    for column in ("requirement_version", "approved_at", "approved_by", "proposed_by",
                   "approval_status", "requirement_origin", "criticality"):
        op.drop_column("functional_requirements", column)
