"""Phase 3 bounded candidate generation and lineage

Revision ID: 0003_phase3
Revises: 0002_phase2
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_phase3"
down_revision = "0002_phase2"
branch_labels = None
depends_on = None
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "candidate_search_spaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("material_family", sa.String(60), nullable=False),
        sa.Column("amount_basis", sa.String(60), nullable=False, server_default="weight_percent"),
        sa.Column("balance_component_key", sa.String(300)),
        sa.Column("total_target", sa.Float()),
        sa.Column("total_tolerance", sa.Float(), nullable=False, server_default="0.001"),
        sa.Column("max_component_count", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("candidate_budget", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("maximum_enumeration", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "version", name="uq_search_space_project_version"),
    )
    op.create_index("ix_candidate_search_spaces_project_id", "candidate_search_spaces", ["project_id"])
    op.create_index("ix_candidate_search_spaces_organisation_id", "candidate_search_spaces", ["organisation_id"])
    op.create_index("ix_candidate_search_spaces_active", "candidate_search_spaces", ["active"])
    op.create_index("ix_candidate_search_spaces_checksum", "candidate_search_spaces", ["checksum"])
    op.create_index("ix_search_space_project_active", "candidate_search_spaces", ["project_id", "active"])

    op.create_table(
        "search_space_component_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("search_space_id", sa.String(36), sa.ForeignKey("candidate_search_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_component_id", sa.String(36), sa.ForeignKey("material_components.id")),
        sa.Column("component_key", sa.String(300), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("role", sa.String(120)),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mutable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prohibited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_amount", sa.Float()), sa.Column("max_amount", sa.Float()), sa.Column("step_amount", sa.Float()),
        sa.Column("amount_unit", sa.String(80)), sa.Column("amount_basis", sa.String(60)),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"), sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("search_space_id", "component_key", name="uq_search_space_component_key"),
    )
    op.create_index("ix_search_space_component_rules_search_space_id", "search_space_component_rules", ["search_space_id"])

    op.create_table(
        "search_space_process_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("search_space_id", sa.String(36), sa.ForeignKey("candidate_search_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parameter_key", sa.String(160), nullable=False), sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=False), sa.Column("max_value", sa.Float(), nullable=False),
        sa.Column("step_value", sa.Float()), sa.Column("unit", sa.String(80), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("search_space_id", "parameter_key", name="uq_search_space_process_key"),
    )
    op.create_index("ix_search_space_process_rules_search_space_id", "search_space_process_rules", ["search_space_id"])

    op.create_table(
        "substitution_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE")),
        sa.Column("material_family", sa.String(60), nullable=False),
        sa.Column("source_component_key", sa.String(300), nullable=False),
        sa.Column("replacement_component_key", sa.String(300), nullable=False),
        sa.Column("replacement_display_name", sa.String(300), nullable=False),
        sa.Column("allowed_min_amount", sa.Float()), sa.Column("allowed_max_amount", sa.Float()),
        sa.Column("amount_basis", sa.String(60)), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_substitution_rules_organisation_id", "substitution_rules", ["organisation_id"])
    op.create_index("ix_substitution_rules_project_id", "substitution_rules", ["project_id"])
    op.create_index("ix_substitution_rules_status", "substitution_rules", ["status"])
    op.create_index("ix_substitution_scope_status", "substitution_rules", ["project_id", "organisation_id", "status"])

    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("replacement_specification_checksum", sa.String(64), nullable=False),
        sa.Column("search_space_id", sa.String(36), sa.ForeignKey("candidate_search_spaces.id"), nullable=False),
        sa.Column("search_space_version", sa.Integer(), nullable=False), sa.Column("search_space_checksum", sa.String(64), nullable=False),
        sa.Column("strategy_key", sa.String(120), nullable=False), sa.Column("strategy_version", sa.String(60), nullable=False),
        sa.Column("configuration_checksum", sa.String(64), nullable=False), sa.Column("random_seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requested_candidate_budget", sa.Integer(), nullable=False), sa.Column("generated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("result_checksum", sa.String(64)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("metadata", JSONB, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for col in ["project_id", "organisation_id", "search_space_id", "strategy_key", "result_checksum", "status"]:
        op.create_index(f"ix_generation_runs_{col}", "generation_runs", [col])
    op.create_index("ix_generation_run_project_status", "generation_runs", ["project_id", "status"])

    op.create_table(
        "candidate_hypotheses",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False), sa.Column("display_label", sa.String(300), nullable=False),
        sa.Column("material_family", sa.String(60), nullable=False), sa.Column("baseline_material_id", sa.String(36), sa.ForeignKey("materials.id"), nullable=False),
        sa.Column("generation_run_id", sa.String(36), sa.ForeignKey("generation_runs.id")), sa.Column("generator_strategy_key", sa.String(120), nullable=False),
        sa.Column("generator_strategy_version", sa.String(60), nullable=False), sa.Column("deterministic_fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint_version", sa.String(30), nullable=False, server_default="candidate-v1"), sa.Column("status", sa.String(40), nullable=False, server_default="proposed"),
        sa.Column("structural_validity", sa.String(30), nullable=False, server_default="valid"), sa.Column("rejection_reason", sa.Text()), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "deterministic_fingerprint", name="uq_hypothesis_project_fingerprint"),
    )
    for col in ["project_id", "organisation_id", "baseline_material_id", "generation_run_id", "deterministic_fingerprint", "status", "structural_validity"]:
        op.create_index(f"ix_candidate_hypotheses_{col}", "candidate_hypotheses", [col])
    op.create_index("ix_hypothesis_project_status", "candidate_hypotheses", ["project_id", "status"])
    op.create_index("ix_hypothesis_generation_run", "candidate_hypotheses", ["generation_run_id"])

    op.add_column("candidates", sa.Column("candidate_kind", sa.String(30), nullable=False, server_default="known_material"))
    op.add_column("candidates", sa.Column("hypothesis_id", sa.String(36), nullable=True))
    op.alter_column("candidates", "material_id", existing_type=sa.String(36), nullable=True)
    op.create_foreign_key("fk_candidate_hypothesis", "candidates", "candidate_hypotheses", ["hypothesis_id"], ["id"], ondelete="CASCADE")
    op.create_unique_constraint("uq_project_candidate_hypothesis", "candidates", ["project_id", "hypothesis_id"])
    op.create_check_constraint("ck_candidate_exactly_one_target", "candidates", "(candidate_kind = 'known_material' AND material_id IS NOT NULL AND hypothesis_id IS NULL) OR (candidate_kind = 'hypothesis' AND material_id IS NULL AND hypothesis_id IS NOT NULL)")
    op.create_index("ix_candidates_candidate_kind", "candidates", ["candidate_kind"])
    op.create_index("ix_candidates_hypothesis_id", "candidates", ["hypothesis_id"])
    op.create_index("ix_candidate_project_kind_status", "candidates", ["project_id", "candidate_kind", "status"])

    op.create_table(
        "candidate_hypothesis_components",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"), sa.Column("component_key", sa.String(300), nullable=False), sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("role", sa.String(120)), sa.Column("amount", sa.Float()), sa.Column("unit", sa.String(80)), sa.Column("basis", sa.String(60)),
        sa.Column("source_baseline_component_id", sa.String(36), sa.ForeignKey("material_components.id")), sa.Column("substitution_rule_id", sa.String(36), sa.ForeignKey("substitution_rules.id")),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("hypothesis_id", "component_key", name="uq_hypothesis_component_key"),
    )
    op.create_index("ix_candidate_hypothesis_components_hypothesis_id", "candidate_hypothesis_components", ["hypothesis_id"])

    op.create_table(
        "candidate_hypothesis_process_parameters",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("process_label", sa.String(200), nullable=False, server_default="proposed process state"), sa.Column("parameter_key", sa.String(160), nullable=False),
        sa.Column("value", sa.Float(), nullable=False), sa.Column("unit", sa.String(80), nullable=False), sa.Column("source_baseline_state_id", sa.String(36), sa.ForeignKey("material_process_states.id")),
        sa.Column("metadata", JSONB, nullable=False), sa.UniqueConstraint("hypothesis_id", "parameter_key", name="uq_hypothesis_process_key"),
    )
    op.create_index("ix_candidate_hypothesis_process_parameters_hypothesis_id", "candidate_hypothesis_process_parameters", ["hypothesis_id"])

    op.create_table(
        "candidate_change_records",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation_run_id", sa.String(36), sa.ForeignKey("generation_runs.id")), sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("change_type", sa.String(80), nullable=False), sa.Column("target_path", sa.String(300), nullable=False), sa.Column("before_value", JSONB, nullable=False),
        sa.Column("after_value", JSONB, nullable=False), sa.Column("substitution_rule_id", sa.String(36), sa.ForeignKey("substitution_rules.id")), sa.Column("rationale", sa.Text(), nullable=False),
    )
    op.create_index("ix_candidate_change_records_hypothesis_id", "candidate_change_records", ["hypothesis_id"])
    op.create_index("ix_change_hypothesis_sequence", "candidate_change_records", ["hypothesis_id", "sequence"])

    op.create_table(
        "candidate_lineage_edges",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("child_hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_material_id", sa.String(36), sa.ForeignKey("materials.id")), sa.Column("parent_candidate_id", sa.String(36), sa.ForeignKey("candidates.id")),
        sa.Column("parent_hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id")), sa.Column("relationship_type", sa.String(60), nullable=False),
        sa.Column("generation_run_id", sa.String(36), sa.ForeignKey("generation_runs.id")), sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"), sa.Column("rationale", sa.Text(), nullable=False),
    )
    op.create_index("ix_candidate_lineage_edges_child_hypothesis_id", "candidate_lineage_edges", ["child_hypothesis_id"])
    op.create_index("ix_lineage_child_sequence", "candidate_lineage_edges", ["child_hypothesis_id", "sequence"])

    op.create_table(
        "generation_run_results",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("generation_run_id", sa.String(36), sa.ForeignKey("generation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("candidate_fingerprint", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="SET NULL")), sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="SET NULL")), sa.Column("disposition", sa.String(40), nullable=False),
        sa.Column("rejection_reason", sa.Text()), sa.Column("metadata", JSONB, nullable=False),
        sa.UniqueConstraint("generation_run_id", "sequence", name="uq_generation_run_result_sequence"),
    )
    op.create_index("ix_generation_run_results_generation_run_id", "generation_run_results", ["generation_run_id"])
    op.create_index("ix_generation_run_results_candidate_id", "generation_run_results", ["candidate_id"])
    op.create_index("ix_generation_run_results_hypothesis_id", "generation_run_results", ["hypothesis_id"])
    op.create_index("ix_generation_result_run_fingerprint", "generation_run_results", ["generation_run_id", "candidate_fingerprint"])


def downgrade():
    op.drop_table("generation_run_results")
    op.drop_table("candidate_lineage_edges")
    op.drop_table("candidate_change_records")
    op.drop_table("candidate_hypothesis_process_parameters")
    op.drop_table("candidate_hypothesis_components")
    op.drop_index("ix_candidate_project_kind_status", table_name="candidates")
    op.drop_index("ix_candidates_hypothesis_id", table_name="candidates")
    op.drop_index("ix_candidates_candidate_kind", table_name="candidates")
    op.drop_constraint("ck_candidate_exactly_one_target", "candidates", type_="check")
    op.drop_constraint("uq_project_candidate_hypothesis", "candidates", type_="unique")
    op.drop_constraint("fk_candidate_hypothesis", "candidates", type_="foreignkey")
    op.drop_column("candidates", "hypothesis_id")
    op.drop_column("candidates", "candidate_kind")
    # Phase-3 hypothesis candidates make restoring NOT NULL material_id lossy unless they are removed first.
    op.execute("DELETE FROM candidates WHERE material_id IS NULL")
    op.alter_column("candidates", "material_id", existing_type=sa.String(36), nullable=False)
    op.drop_table("candidate_hypotheses")
    op.drop_table("generation_runs")
    op.drop_table("substitution_rules")
    op.drop_table("search_space_process_rules")
    op.drop_table("search_space_component_rules")
    op.drop_table("candidate_search_spaces")
