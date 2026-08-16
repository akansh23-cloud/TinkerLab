"""Phase 13.4 mission-condition property model registry.

Revision ID: 0016_phase13_4
Revises: 0015_phase13_2

This migration is additive. It creates an empty registry and does not infer or seed scientific
coefficients, validity ranges, citations, or uncertainty for historical data.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_phase13_4"
down_revision = "0015_phase13_2"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "property_models_v13",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("material_id", sa.String(length=36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_definition_id", sa.String(length=36), sa.ForeignKey("material_property_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("model_type", sa.String(length=60), nullable=False),
        sa.Column("equation", sa.Text(), nullable=False),
        sa.Column("coefficients", JSON, nullable=False),
        sa.Column("coefficient_units", JSON, nullable=False),
        sa.Column("output_unit", sa.String(length=100), nullable=True),
        sa.Column("validity_temperature_min_k", sa.Float(), nullable=True),
        sa.Column("validity_temperature_max_k", sa.Float(), nullable=True),
        sa.Column("validity_conditions", JSON, nullable=False),
        sa.Column("distribution", sa.String(length=30), nullable=False, server_default="unspecified"),
        sa.Column("uncertainty_value", sa.Float(), nullable=True),
        sa.Column("uncertainty_lower", sa.Float(), nullable=True),
        sa.Column("uncertainty_upper", sa.Float(), nullable=True),
        sa.Column("evidence_tier", sa.String(length=40), nullable=True),
        sa.Column("fit_quality", JSON, nullable=False),
        sa.Column("source_evidence_id", sa.String(length=36), sa.ForeignKey("evidence.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_record_id", sa.String(length=36), sa.ForeignKey("source_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("source_kind", sa.String(length=40), nullable=False, server_default="UNSPECIFIED"),
        sa.Column("applicability_notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("checksum", name="uq_property_models_v13_checksum"),
        sa.UniqueConstraint("material_id", "property_definition_id", "model_key", "version", name="uq_property_model_v13_version"),
    )
    op.create_index("ix_property_models_v13_material_id", "property_models_v13", ["material_id"])
    op.create_index("ix_property_models_v13_property_definition_id", "property_models_v13", ["property_definition_id"])
    op.create_index("ix_property_models_v13_model_type", "property_models_v13", ["model_type"])
    op.create_index("ix_property_models_v13_evidence_tier", "property_models_v13", ["evidence_tier"])
    op.create_index("ix_property_models_v13_source_evidence_id", "property_models_v13", ["source_evidence_id"])
    op.create_index("ix_property_models_v13_source_record_id", "property_models_v13", ["source_record_id"])
    op.create_index("ix_property_models_v13_checksum", "property_models_v13", ["checksum"], unique=True)
    op.create_index("ix_property_models_v13_review_required", "property_models_v13", ["review_required"])
    op.create_index("ix_property_models_v13_is_active", "property_models_v13", ["is_active"])
    op.create_index("ix_property_model_v13_material_property", "property_models_v13", ["material_id", "property_definition_id"])


def downgrade() -> None:
    op.drop_index("ix_property_model_v13_material_property", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_is_active", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_review_required", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_checksum", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_source_record_id", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_source_evidence_id", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_evidence_tier", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_model_type", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_property_definition_id", table_name="property_models_v13")
    op.drop_index("ix_property_models_v13_material_id", table_name="property_models_v13")
    op.drop_table("property_models_v13")
