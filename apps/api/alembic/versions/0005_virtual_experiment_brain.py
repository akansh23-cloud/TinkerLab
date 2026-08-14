"""Phase 5 virtual experiment and optimization brain

Revision ID: 0005_phase5
Revises: 0004_phase4
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_phase5"
down_revision = "0004_phase4"
branch_labels = None
depends_on = None
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "virtual_experiment_campaigns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("replacement_specification_checksum", sa.String(64), nullable=False),
        sa.Column("search_space_id", sa.String(36), sa.ForeignKey("candidate_search_spaces.id"), nullable=False),
        sa.Column("search_space_version", sa.Integer(), nullable=False),
        sa.Column("search_space_checksum", sa.String(64), nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.String(60), nullable=False),
        sa.Column("configuration_checksum", sa.String(64), nullable=False),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_iterations", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_total_new_candidates", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_candidates_per_iteration", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("max_parents_per_iteration", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("stop_reason", sa.String(120)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("result_checksum", sa.String(64)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    for c in ["organisation_id", "project_id", "search_space_id", "policy_key", "status", "result_checksum"]:
        op.create_index(f"ix_virtual_experiment_campaigns_{c}", "virtual_experiment_campaigns", [c])
    op.create_index("ix_virtual_campaign_project_status", "virtual_experiment_campaigns", ["project_id", "status"])
    op.create_index("ix_virtual_campaign_org_policy", "virtual_experiment_campaigns", ["organisation_id", "policy_key"])

    op.create_table(
        "campaign_objectives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_key", sa.String(120), nullable=False),
        sa.Column("direction", sa.String(30), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("target_value", sa.Float()),
        sa.Column("target_unit", sa.String(80)),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id"), nullable=False),
        sa.Column("evaluation_mode", sa.String(40), nullable=False, server_default="model_prediction"),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("campaign_id", "sequence", name="uq_campaign_objective_sequence"),
        sa.UniqueConstraint("campaign_id", "property_key", name="uq_campaign_objective_property"),
    )
    for c in ["campaign_id", "property_key", "model_version_id"]:
        op.create_index(f"ix_campaign_objectives_{c}", "campaign_objectives", [c])

    op.create_table(
        "campaign_constraint_model_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("constraint_id", sa.String(36), sa.ForeignKey("constraints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id")),
        sa.Column("allowed_value_origin", sa.String(60), nullable=False, server_default="known_evidence_then_prediction"),
        sa.Column("unknown_handling", sa.String(40), nullable=False, server_default="retain_uncertain"),
        sa.Column("condition_mapping", JSONB, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("campaign_id", "constraint_id", name="uq_campaign_constraint_policy"),
    )
    for c in ["campaign_id", "constraint_id", "model_version_id"]:
        op.create_index(f"ix_campaign_constraint_model_policies_{c}", "campaign_constraint_model_policies", [c])

    op.create_table(
        "campaign_iterations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_number", sa.Integer(), nullable=False),
        sa.Column("input_pool_checksum", sa.String(64), nullable=False),
        sa.Column("parent_selection_checksum", sa.String(64)),
        sa.Column("generation_run_ids", JSONB, nullable=False),
        sa.Column("prediction_run_ids", JSONB, nullable=False),
        sa.Column("evaluated_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feasible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uncertain_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("infeasible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pareto_front_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pareto_front_checksum", sa.String(64)),
        sa.Column("selected_for_exploration_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision_checksum", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("stop_signal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stop_reason", sa.String(120)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("campaign_id", "iteration_number", name="uq_campaign_iteration_number"),
    )
    for c in ["campaign_id", "decision_checksum", "status"]:
        op.create_index(f"ix_campaign_iterations_{c}", "campaign_iterations", [c])
    op.create_index("ix_campaign_iteration_campaign_status", "campaign_iterations", ["campaign_id", "status"])

    op.create_table(
        "virtual_candidate_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_iteration_id", sa.String(36), sa.ForeignKey("campaign_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="SET NULL")),
        sa.Column("feasibility_class", sa.String(40), nullable=False),
        sa.Column("hard_pass_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hard_fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hard_unknown_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("objective_vector", JSONB, nullable=False),
        sa.Column("objective_intervals", JSONB, nullable=False),
        sa.Column("objective_origins", JSONB, nullable=False),
        sa.Column("pareto_rank", sa.Integer()),
        sa.Column("dominance_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diversity_metric", sa.Float()),
        sa.Column("uncertainty_burden", JSONB, nullable=False),
        sa.Column("normalized_utility_components", JSONB, nullable=False),
        sa.Column("acquisition_components", JSONB, nullable=False),
        sa.Column("selected_as_parent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("selected_for_next_evaluation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("disposition", sa.String(60), nullable=False, server_default="evaluated"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("deterministic_evaluation_checksum", sa.String(64), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("campaign_iteration_id", "candidate_id", name="uq_virtual_evaluation_iteration_candidate"),
    )
    evaluation_indexes = {
        "campaign_iteration_id": "ix_virtual_eval_iteration",
        "candidate_id": "ix_virtual_eval_candidate",
        "hypothesis_id": "ix_virtual_eval_hypothesis",
        "feasibility_class": "ix_virtual_eval_feasibility",
        "pareto_rank": "ix_virtual_eval_pareto_rank",
        "deterministic_evaluation_checksum": "ix_virtual_eval_checksum",
    }
    for c, name in evaluation_indexes.items():
        op.create_index(name, "virtual_candidate_evaluations", [c])
    op.create_index("ix_virtual_evaluation_iteration_feasibility", "virtual_candidate_evaluations", ["campaign_iteration_id", "feasibility_class"])
    op.create_index("ix_virtual_evaluation_iteration_pareto", "virtual_candidate_evaluations", ["campaign_iteration_id", "pareto_rank"])

    op.create_table(
        "pareto_front_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_iteration_id", sa.String(36), sa.ForeignKey("campaign_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("front_number", sa.Integer(), nullable=False),
        sa.Column("ordered_candidate_ids", JSONB, nullable=False),
        sa.Column("objective_space_checksum", sa.String(64), nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("campaign_iteration_id", "front_number", name="uq_pareto_iteration_front"),
    )
    op.create_index("ix_pareto_front_snapshots_campaign_iteration_id", "pareto_front_snapshots", ["campaign_iteration_id"])

    op.create_table(
        "optimization_decision_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_iteration_id", sa.String(36), sa.ForeignKey("campaign_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="SET NULL")),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("decision_type", sa.String(80), nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.String(60), nullable=False),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("campaign_iteration_id", "sequence", name="uq_optimization_decision_sequence"),
    )
    for c in ["campaign_id", "campaign_iteration_id", "candidate_id", "hypothesis_id"]:
        op.create_index(f"ix_optimization_decision_records_{c}", "optimization_decision_records", [c])
    op.create_index("ix_optimization_decision_iteration_type", "optimization_decision_records", ["campaign_iteration_id", "decision_type"])


def downgrade():
    op.drop_table("optimization_decision_records")
    op.drop_table("pareto_front_snapshots")
    op.drop_table("virtual_candidate_evaluations")
    op.drop_table("campaign_iterations")
    op.drop_table("campaign_constraint_model_policies")
    op.drop_table("campaign_objectives")
    op.drop_table("virtual_experiment_campaigns")
