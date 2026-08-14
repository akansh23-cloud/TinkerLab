"""Phase 9.1-A scientific integrity database invariants.

Revision ID: 0010_phase9_1a
Revises: 0009_phase9
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_phase9_1a"
down_revision = "0009_phase9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL UNIQUE treats NULLs as distinct, so the old three-column target constraint did not
    # enforce one compatibility record per route/material or route/hypothesis. Partial indexes do.
    op.drop_constraint("uq_process_compatibility_target", "material_process_compatibilities", type_="unique")
    op.create_index(
        "uq_process_compatibility_material", "material_process_compatibilities", ["route_id", "material_id"],
        unique=True, postgresql_where=sa.text("material_id IS NOT NULL AND hypothesis_id IS NULL"),
    )
    op.create_index(
        "uq_process_compatibility_hypothesis", "material_process_compatibilities", ["route_id", "hypothesis_id"],
        unique=True, postgresql_where=sa.text("hypothesis_id IS NOT NULL AND material_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_process_compatibility_hypothesis", table_name="material_process_compatibilities")
    op.drop_index("uq_process_compatibility_material", table_name="material_process_compatibilities")
    op.create_unique_constraint(
        "uq_process_compatibility_target", "material_process_compatibilities", ["route_id", "material_id", "hypothesis_id"]
    )
