"""Phase 13.2 structured material identity and collision-safe custody.

Revision ID: 0015_phase13_2
Revises: 0014_phase13_1

Legacy free-text composition summaries are intentionally not parsed into scientific identity facts.
Every existing material receives an explicit LEGACY_UNKNOWN identity shell requiring review.
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_phase13_2"
down_revision = "0014_phase13_1"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "material_identities_v13",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("material_id", sa.String(length=36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("composition", JSON, nullable=False),
        sa.Column("composition_basis", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("composition_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("phase_polytype", JSON, nullable=False),
        sa.Column("microstructure", JSON, nullable=False),
        sa.Column("processing_route", JSON, nullable=False),
        sa.Column("form_factor", JSON, nullable=False),
        sa.Column("crystallographic_orientation", JSON, nullable=False),
        sa.Column("defect_state", JSON, nullable=False),
        sa.Column("symmetry_class", sa.String(length=80), nullable=True),
        sa.Column("direction_required_for", JSON, nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("completeness", sa.String(length=30), nullable=False, server_default="LEGACY_UNKNOWN"),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("migration_metadata", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("material_id", name="uq_material_identity_v13_material"),
    )
    op.create_index("ix_material_identities_v13_material_id", "material_identities_v13", ["material_id"], unique=True)
    op.create_index("ix_material_identities_v13_composition_fingerprint", "material_identities_v13", ["composition_fingerprint"])
    op.create_index("ix_material_identities_v13_identity_fingerprint", "material_identities_v13", ["identity_fingerprint"])
    op.create_index("ix_material_identities_v13_completeness", "material_identities_v13", ["completeness"])
    op.create_index("ix_material_identities_v13_review_required", "material_identities_v13", ["review_required"])
    op.create_index(
        "ix_material_identity_v13_composition_material",
        "material_identities_v13",
        ["composition_fingerprint", "material_id"],
    )

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, composition_summary FROM materials")).mappings().all()
    for row in rows:
        material_id = str(row["id"])
        metadata = {
            "source": "materials",
            "legacy_material_id": material_id,
            "composition_summary_not_parsed": bool(row.get("composition_summary")),
            "reason": "free-text legacy identity cannot be converted to structured identity without review",
        }
        connection.execute(
            sa.text(
                """
                INSERT INTO material_identities_v13 (
                    id, material_id, composition, composition_basis,
                    phase_polytype, microstructure, processing_route, form_factor,
                    crystallographic_orientation, defect_state, direction_required_for,
                    completeness, review_required, migration_metadata
                ) VALUES (
                    :id, :material_id, :composition, :composition_basis,
                    :phase_polytype, :microstructure, :processing_route, :form_factor,
                    :orientation, :defect_state, :direction_required_for,
                    :completeness, :review_required, :migration_metadata
                )
                """
            ),
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"tinkerlab:phase13:identity:{material_id}")),
                "material_id": material_id,
                "composition": json.dumps({}),
                "composition_basis": "unknown",
                "phase_polytype": json.dumps({}),
                "microstructure": json.dumps({}),
                "processing_route": json.dumps({}),
                "form_factor": json.dumps({}),
                "orientation": json.dumps({}),
                "defect_state": json.dumps({}),
                "direction_required_for": json.dumps([]),
                "completeness": "LEGACY_UNKNOWN",
                "review_required": True,
                "migration_metadata": json.dumps(metadata),
            },
        )


def downgrade() -> None:
    op.drop_index("ix_material_identity_v13_composition_material", table_name="material_identities_v13")
    op.drop_index("ix_material_identities_v13_review_required", table_name="material_identities_v13")
    op.drop_index("ix_material_identities_v13_completeness", table_name="material_identities_v13")
    op.drop_index("ix_material_identities_v13_identity_fingerprint", table_name="material_identities_v13")
    op.drop_index("ix_material_identities_v13_composition_fingerprint", table_name="material_identities_v13")
    op.drop_index("ix_material_identities_v13_material_id", table_name="material_identities_v13")
    op.drop_table("material_identities_v13")
