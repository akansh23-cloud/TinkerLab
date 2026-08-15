"""Phase 9.1-B experimental admissibility and validation snapshots.

Revision ID: 0011_phase9_1b
Revises: 0010_phase9_1a
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_phase9_1b"
down_revision = "0010_phase9_1a"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("experiment_plans", sa.Column("candidate_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_experiment_plans_candidate", "experiment_plans", "candidates", ["candidate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_experiment_plans_candidate_id", "experiment_plans", ["candidate_id"], unique=False)
    op.add_column("validation_assessments", sa.Column("candidate_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_validation_assessments_candidate", "validation_assessments", "candidates", ["candidate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_validation_assessments_candidate_id", "validation_assessments", ["candidate_id"], unique=False)
    op.add_column("instruments", sa.Column("equipment_capabilities", JSON, nullable=True))
    op.add_column("measurements", sa.Column("admissibility_codes", JSON, nullable=True))
    op.add_column("validation_assessments", sa.Column("requirement_outcomes", JSON, nullable=True))
    op.add_column("validation_assessments", sa.Column("evidence_snapshot", JSON, nullable=True))
    op.add_column("validation_assessments", sa.Column("methodology_version", sa.String(length=40), nullable=True))

    # Existing Phase-9 rows remain historical. Empty values state that legacy admission metadata was
    # unavailable rather than inventing scientific context after the fact.
    op.execute("UPDATE instruments SET equipment_capabilities = '[]' WHERE equipment_capabilities IS NULL")
    op.execute("UPDATE measurements SET admissibility_codes = '[]' WHERE admissibility_codes IS NULL")
    op.execute("UPDATE validation_assessments SET requirement_outcomes = '[]' WHERE requirement_outcomes IS NULL")
    op.execute("UPDATE validation_assessments SET evidence_snapshot = '{}' WHERE evidence_snapshot IS NULL")
    op.execute("UPDATE validation_assessments SET methodology_version = 'legacy-validation-v1' WHERE methodology_version IS NULL")

    op.alter_column("instruments", "equipment_capabilities", nullable=False)
    op.alter_column("measurements", "admissibility_codes", nullable=False)
    op.alter_column("validation_assessments", "requirement_outcomes", nullable=False)
    op.alter_column("validation_assessments", "evidence_snapshot", nullable=False)
    op.alter_column("validation_assessments", "methodology_version", nullable=False)


def downgrade() -> None:
    op.drop_column("validation_assessments", "methodology_version")
    op.drop_column("validation_assessments", "evidence_snapshot")
    op.drop_column("validation_assessments", "requirement_outcomes")
    op.drop_column("measurements", "admissibility_codes")
    op.drop_column("instruments", "equipment_capabilities")
    op.drop_index("ix_validation_assessments_candidate_id", table_name="validation_assessments")
    op.drop_constraint("fk_validation_assessments_candidate", "validation_assessments", type_="foreignkey")
    op.drop_column("validation_assessments", "candidate_id")
    op.drop_index("ix_experiment_plans_candidate_id", table_name="experiment_plans")
    op.drop_constraint("fk_experiment_plans_candidate", "experiment_plans", type_="foreignkey")
    op.drop_column("experiment_plans", "candidate_id")
