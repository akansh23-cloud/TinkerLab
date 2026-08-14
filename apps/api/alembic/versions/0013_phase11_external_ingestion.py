"""Phase 11 external data ingestion: licence, snapshot and computational-method provenance.

Revision ID: 0013_phase11
Revises: 0012_phase10

Additive and forward-only. No existing column is dropped or retyped.

The licence columns on `source_providers` are nullable on purpose. `commercial_use_permitted = NULL`
means "nobody has reviewed this", which is deliberately distinct from `FALSE` ("reviewed, and not
permitted"). The dossier export gate treats both as blocking, but only the second is a decision —
the first is an omission, and conflating them would let an unreviewed provider look deliberate.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0013_phase11"
down_revision = "0012_phase10"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    # ------------------------------------------------------------------------------------------
    # Provider licence position
    # ------------------------------------------------------------------------------------------
    op.add_column("source_providers", sa.Column("license_identifier", sa.String(length=80), nullable=True))
    op.add_column("source_providers", sa.Column("license_url", sa.Text(), nullable=True))
    op.add_column("source_providers", sa.Column("commercial_use_permitted", sa.Boolean(), nullable=True))
    op.add_column("source_providers", sa.Column("redistribution_permitted", sa.Boolean(), nullable=True))
    op.add_column("source_providers", sa.Column("attribution_required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("source_providers", sa.Column("attribution_text", sa.Text(), nullable=True))
    op.add_column("source_providers", sa.Column("license_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source_providers", sa.Column("license_reviewed_by", sa.String(length=160), nullable=True))
    op.add_column("source_providers", sa.Column("rate_limit_per_second", sa.Float(), nullable=True))
    op.create_index("ix_source_providers_license_identifier", "source_providers", ["license_identifier"])
    op.create_index("ix_source_providers_commercial_use_permitted", "source_providers", ["commercial_use_permitted"])

    # The pre-existing local_import provider is first-party data, so it is cleared explicitly
    # rather than left NULL — otherwise every existing dossier would fail the new export gate.
    op.execute(
        "UPDATE source_providers SET commercial_use_permitted = true, "
        "redistribution_permitted = true, attribution_required = false, "
        "license_identifier = 'first-party' "
        "WHERE provider_type = 'local' OR key = 'local_import'"
    )

    # ------------------------------------------------------------------------------------------
    # Computational method catalogue
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "computational_methods",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("method_family", sa.String(length=60), nullable=False),
        sa.Column("functional", sa.String(length=80), nullable=True),
        sa.Column("basis_or_code", sa.String(length=160), nullable=True),
        sa.Column("nominal_temperature_k", sa.Float(), nullable=True),
        sa.Column("includes_thermal_expansion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("includes_zero_point_energy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("known_property_bias", JSON, nullable=False),
        sa.Column("applicability_note", sa.Text(), nullable=True),
        sa.Column("reference_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_computational_methods_key", "computational_methods", ["key"], unique=True)
    op.create_index("ix_computational_methods_method_family", "computational_methods", ["method_family"])
    op.create_index("ix_computational_methods_functional", "computational_methods", ["functional"])

    # ------------------------------------------------------------------------------------------
    # Dataset snapshots
    # ------------------------------------------------------------------------------------------
    op.create_table(
        "dataset_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider_id", sa.String(length=36), sa.ForeignKey("source_providers.id"), nullable=False),
        sa.Column("organisation_id", sa.String(length=36), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("dataset_key", sa.String(length=160), nullable=False),
        sa.Column("provider_version", sa.String(length=160), nullable=True),
        sa.Column("query_descriptor", JSON, nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connector_version", sa.String(length=80), nullable=False),
        sa.Column("content_checksum", sa.String(length=64), nullable=False),
        sa.Column("is_reproducible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reproducibility_note", sa.Text(), nullable=True),
        sa.Column("metadata", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dataset_snapshots_provider_id", "dataset_snapshots", ["provider_id"])
    op.create_index("ix_dataset_snapshots_organisation_id", "dataset_snapshots", ["organisation_id"])
    op.create_index("ix_dataset_snapshots_dataset_key", "dataset_snapshots", ["dataset_key"])
    op.create_index("ix_dataset_snapshots_provider_version", "dataset_snapshots", ["provider_version"])
    op.create_index("ix_dataset_snapshots_content_checksum", "dataset_snapshots", ["content_checksum"])
    op.create_index("ix_dataset_snapshot_scope", "dataset_snapshots", ["provider_id", "dataset_key", "retrieved_at"])

    # ------------------------------------------------------------------------------------------
    # Links from the evidence chain
    # ------------------------------------------------------------------------------------------
    op.add_column("source_records", sa.Column("dataset_snapshot_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_source_records_dataset_snapshot", "source_records", "dataset_snapshots",
        ["dataset_snapshot_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_source_records_dataset_snapshot_id", "source_records", ["dataset_snapshot_id"])

    op.add_column("evidence", sa.Column("computational_method_id", sa.String(length=36), nullable=True))
    op.add_column("evidence", sa.Column("dataset_snapshot_id", sa.String(length=36), nullable=True))
    op.add_column("evidence", sa.Column("applicability_warnings", JSON, nullable=True))
    op.create_foreign_key(
        "fk_evidence_computational_method", "evidence", "computational_methods",
        ["computational_method_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_dataset_snapshot", "evidence", "dataset_snapshots",
        ["dataset_snapshot_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_evidence_computational_method_id", "evidence", ["computational_method_id"])
    op.create_index("ix_evidence_dataset_snapshot_id", "evidence", ["dataset_snapshot_id"])
    op.execute("UPDATE evidence SET applicability_warnings = '[]' WHERE applicability_warnings IS NULL")


def downgrade() -> None:
    op.drop_index("ix_evidence_dataset_snapshot_id", table_name="evidence")
    op.drop_index("ix_evidence_computational_method_id", table_name="evidence")
    op.drop_constraint("fk_evidence_dataset_snapshot", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_computational_method", "evidence", type_="foreignkey")
    op.drop_column("evidence", "applicability_warnings")
    op.drop_column("evidence", "dataset_snapshot_id")
    op.drop_column("evidence", "computational_method_id")

    op.drop_index("ix_source_records_dataset_snapshot_id", table_name="source_records")
    op.drop_constraint("fk_source_records_dataset_snapshot", "source_records", type_="foreignkey")
    op.drop_column("source_records", "dataset_snapshot_id")

    op.drop_table("dataset_snapshots")
    op.drop_table("computational_methods")

    op.drop_index("ix_source_providers_commercial_use_permitted", table_name="source_providers")
    op.drop_index("ix_source_providers_license_identifier", table_name="source_providers")
    for column in ("rate_limit_per_second", "license_reviewed_by", "license_reviewed_at",
                   "attribution_text", "attribution_required", "redistribution_permitted",
                   "commercial_use_permitted", "license_url", "license_identifier"):
        op.drop_column("source_providers", column)
