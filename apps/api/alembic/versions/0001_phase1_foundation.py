"""Phase 1 scientific foundation

Revision ID: 0001_phase1
Revises:
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_phase1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organisations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_table("material_property_definitions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("key", sa.String(120), nullable=False), sa.Column("display_name", sa.String(180), nullable=False), sa.Column("quantity_type", sa.String(80), nullable=False), sa.Column("canonical_unit", sa.String(80)), sa.Column("description", sa.Text()), sa.Column("applicable_material_families", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("allowed_comparators", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("allow_negative", sa.Boolean(), nullable=False), sa.UniqueConstraint("key"))
    op.create_index("ix_material_property_definitions_key", "material_property_definitions", ["key"])
    op.create_table("materials", sa.Column("id", sa.String(36), primary_key=True), sa.Column("canonical_name", sa.String(240), nullable=False), sa.Column("display_name", sa.String(240), nullable=False), sa.Column("material_family", sa.String(60), nullable=False), sa.Column("description", sa.Text()), sa.Column("composition_summary", sa.Text()), sa.Column("source_type", sa.String(60), nullable=False), sa.Column("is_seed_data", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("canonical_name"))
    op.create_index("ix_materials_canonical_name", "materials", ["canonical_name"]); op.create_index("ix_materials_material_family", "materials", ["material_family"]); op.create_index("ix_materials_is_seed_data", "materials", ["is_seed_data"])
    op.create_table("evidence", sa.Column("id", sa.String(36), primary_key=True), sa.Column("evidence_type", sa.String(60), nullable=False), sa.Column("title", sa.String(300), nullable=False), sa.Column("source_reference", sa.Text()), sa.Column("description", sa.Text()), sa.Column("method", sa.Text()), sa.Column("confidence", sa.Float()), sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)))
    op.create_index("ix_evidence_evidence_type", "evidence", ["evidence_type"])
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False), sa.Column("display_name", sa.String(200), nullable=False), sa.Column("email", sa.String(320), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("email"))
    op.create_index("ix_users_organisation_id", "users", ["organisation_id"])
    op.create_table("material_property_observations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False), sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False), sa.Column("value_type", sa.String(20), nullable=False), sa.Column("numeric_value", sa.Float(), nullable=True), sa.Column("boolean_value", sa.Boolean(), nullable=True), sa.Column("unit", sa.String(80), nullable=True), sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id"), nullable=False), sa.Column("uncertainty", sa.Float()), sa.Column("confidence", sa.Float()), sa.Column("created_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("material_id", "property_definition_id", "evidence_id", name="uq_observation_evidence"))
    op.create_index("ix_observation_material", "material_property_observations", ["material_id"]); op.create_index("ix_observation_property", "material_property_observations", ["property_definition_id"]); op.create_index("ix_observation_evidence", "material_property_observations", ["evidence_id"])
    op.create_table("replacement_projects", sa.Column("id", sa.String(36), primary_key=True), sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False), sa.Column("name", sa.String(240), nullable=False), sa.Column("description", sa.Text()), sa.Column("baseline_material_id", sa.String(36), sa.ForeignKey("materials.id"), nullable=False), sa.Column("replacement_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.create_index("ix_project_org", "replacement_projects", ["organisation_id"]); op.create_index("ix_project_baseline", "replacement_projects", ["baseline_material_id"]); op.create_index("ix_project_name", "replacement_projects", ["name"]); op.create_index("ix_project_status", "replacement_projects", ["status"])
    op.create_table("constraints", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False), sa.Column("constraint_type", sa.String(40), nullable=False), sa.Column("property_key", sa.String(120), nullable=False), sa.Column("comparator", sa.String(30), nullable=False), sa.Column("target_value", sa.Float()), sa.Column("target_value_upper", sa.Float()), sa.Column("target_boolean", sa.Boolean()), sa.Column("target_unit", sa.String(80)), sa.Column("severity", sa.Integer(), nullable=False), sa.Column("hard_or_soft", sa.String(20), nullable=False), sa.Column("weight", sa.Float(), nullable=False), sa.Column("description", sa.Text()), sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    op.create_index("ix_constraints_project", "constraints", ["project_id"]); op.create_index("ix_constraints_property", "constraints", ["property_key"])
    op.create_table("objectives", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False), sa.Column("property_key", sa.String(120), nullable=False), sa.Column("direction", sa.String(30), nullable=False), sa.Column("target_value", sa.Float()), sa.Column("target_unit", sa.String(80)), sa.Column("weight", sa.Float(), nullable=False), sa.Column("priority", sa.Integer(), nullable=False), sa.Column("description", sa.Text()))
    op.create_index("ix_objectives_project", "objectives", ["project_id"]); op.create_index("ix_objectives_property", "objectives", ["property_key"])
    op.create_table("candidates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False), sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id"), nullable=False), sa.Column("candidate_source", sa.String(40), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("project_id", "material_id", name="uq_project_candidate_material"))
    op.create_index("ix_candidates_project", "candidates", ["project_id"]); op.create_index("ix_candidates_material", "candidates", ["material_id"])


def downgrade():
    for table in ["candidates", "objectives", "constraints", "replacement_projects", "material_property_observations", "users", "evidence", "materials", "material_property_definitions", "organisations"]:
        op.drop_table(table)
