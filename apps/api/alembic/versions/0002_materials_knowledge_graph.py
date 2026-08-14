"""Phase 2 materials knowledge and evidence graph

Revision ID: 0002_phase2
Revises: 0001_phase1
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_phase2"
down_revision = "0001_phase1"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    # Existing entities are expanded in-place to preserve Phase-1 identifiers and references.
    op.add_column("materials", sa.Column("owner_organisation_id", sa.String(36), nullable=True))
    op.add_column("materials", sa.Column("visibility", sa.String(20), nullable=False, server_default="public"))
    op.create_foreign_key("fk_material_owner_org", "materials", "organisations", ["owner_organisation_id"], ["id"])
    op.create_index("ix_materials_owner_organisation_id", "materials", ["owner_organisation_id"])
    op.create_index("ix_materials_visibility", "materials", ["visibility"])
    op.create_index("ix_materials_display_name", "materials", ["display_name"])

    op.add_column("material_property_definitions", sa.Column("conflict_policy", sa.String(40), nullable=False, server_default="informational"))
    op.add_column("material_property_definitions", sa.Column("conflict_absolute_tolerance", sa.Float(), nullable=True))
    op.add_column("material_property_definitions", sa.Column("conflict_relative_tolerance", sa.Float(), nullable=True))

    op.create_table(
        "source_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(120), nullable=False, unique=True),
        sa.Column("display_name", sa.String(240), nullable=False),
        sa.Column("provider_type", sa.String(60), nullable=False),
        sa.Column("reference_url", sa.Text()),
        sa.Column("licensing_notes", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("adapter_version", sa.String(80), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_source_providers_key", "source_providers", ["key"])

    op.create_table(
        "citations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("doi", sa.String(200), unique=True),
        sa.Column("authors", JSONB, nullable=False),
        sa.Column("journal_or_source", sa.String(300)),
        sa.Column("publication_year", sa.Integer()),
        sa.Column("publication_date", sa.DateTime(timezone=True)),
        sa.Column("reference_url", sa.Text()),
        sa.Column("publisher", sa.String(300)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_citations_doi", "citations", ["doi"])

    op.create_table(
        "source_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("source_providers.id"), nullable=False),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("external_record_id", sa.String(300), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("imported_at", sa.DateTime(timezone=True)),
        sa.Column("source_version", sa.String(120)),
        sa.Column("parser_version", sa.String(80), nullable=False),
        sa.Column("raw_checksum", sa.String(64), nullable=False),
        sa.Column("normalized_checksum", sa.String(64), nullable=False),
        sa.Column("raw_payload", JSONB, nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="normalized"),
        sa.Column("error_details", sa.Text()),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider_id", "external_record_id", "organisation_id", "raw_checksum", name="uq_source_record_snapshot"),
    )
    op.create_index("ix_source_record_provider_external", "source_records", ["provider_id", "external_record_id"])
    op.create_index("ix_source_records_provider_id", "source_records", ["provider_id"])
    op.create_index("ix_source_records_organisation_id", "source_records", ["organisation_id"])
    op.create_index("ix_source_records_visibility", "source_records", ["visibility"])
    op.create_index("ix_source_records_raw_checksum", "source_records", ["raw_checksum"])
    op.create_index("ix_source_records_status", "source_records", ["status"])

    for _name, column in [
        ("provider_id", sa.Column("provider_id", sa.String(36), nullable=True)),
        ("source_record_id", sa.Column("source_record_id", sa.String(36), nullable=True)),
        ("citation_id", sa.Column("citation_id", sa.String(36), nullable=True)),
        ("parent_evidence_id", sa.Column("parent_evidence_id", sa.String(36), nullable=True)),
        ("organisation_id", sa.Column("organisation_id", sa.String(36), nullable=True)),
        ("visibility", sa.Column("visibility", sa.String(20), nullable=False, server_default="public")),
        ("status", sa.Column("status", sa.String(40), nullable=False, server_default="reported")),
        ("evidence_date", sa.Column("evidence_date", sa.DateTime(timezone=True), nullable=True)),
        ("curator_note", sa.Column("curator_note", sa.Text(), nullable=True)),
        ("source_quality", sa.Column("source_quality", sa.String(40), nullable=True)),
    ]:
        op.add_column("evidence", column)
    op.create_foreign_key("fk_evidence_provider", "evidence", "source_providers", ["provider_id"], ["id"])
    op.create_foreign_key("fk_evidence_source_record", "evidence", "source_records", ["source_record_id"], ["id"])
    op.create_foreign_key("fk_evidence_citation", "evidence", "citations", ["citation_id"], ["id"])
    op.create_foreign_key("fk_evidence_parent", "evidence", "evidence", ["parent_evidence_id"], ["id"])
    op.create_foreign_key("fk_evidence_org", "evidence", "organisations", ["organisation_id"], ["id"])
    op.create_index("ix_evidence_provider_id", "evidence", ["provider_id"])
    op.create_index("ix_evidence_source_record_id", "evidence", ["source_record_id"])
    op.create_index("ix_evidence_organisation_id", "evidence", ["organisation_id"])
    op.create_index("ix_evidence_visibility", "evidence", ["visibility"])
    op.create_index("ix_evidence_status", "evidence", ["status"])

    op.create_table(
        "material_identifiers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("namespace", sa.String(80), nullable=False),
        sa.Column("value", sa.String(300), nullable=False),
        sa.Column("normalized_value", sa.String(300), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id")),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("namespace", "normalized_value", "organisation_id", name="uq_identifier_namespace_scope"),
    )
    op.create_index("ix_identifier_namespace_value", "material_identifiers", ["namespace", "normalized_value"])
    op.create_index("ix_material_identifiers_material_id", "material_identifiers", ["material_id"])
    op.create_index("ix_material_identifiers_organisation_id", "material_identifiers", ["organisation_id"])
    op.create_index("uq_public_identifier_namespace_value", "material_identifiers", ["namespace", "normalized_value"], unique=True, postgresql_where=sa.text("organisation_id IS NULL"))

    op.create_table(
        "material_components",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_name", sa.String(300), nullable=False),
        sa.Column("component_identifier", sa.String(300)),
        sa.Column("component_role", sa.String(120)),
        sa.Column("amount_value", sa.Float()), sa.Column("amount_lower", sa.Float()), sa.Column("amount_upper", sa.Float()),
        sa.Column("amount_unit", sa.String(80)), sa.Column("amount_basis", sa.String(60), nullable=False),
        sa.Column("uncertainty", sa.Float()), sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id")),
        sa.Column("is_redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("redaction_label", sa.String(200)), sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_material_components_material_id", "material_components", ["material_id"])

    op.create_table(
        "material_process_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("state_label", sa.String(160), nullable=False), sa.Column("process_name", sa.String(160)),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"), sa.Column("parameters", JSONB, nullable=False),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id")), sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_material_process_states_material_id", "material_process_states", ["material_id"])

    op.create_table(
        "observation_condition_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("temperature_value", sa.Float()), sa.Column("temperature_unit", sa.String(40)),
        sa.Column("pressure_value", sa.Float()), sa.Column("pressure_unit", sa.String(40)),
        sa.Column("humidity_percent", sa.Float()), sa.Column("strain_rate", sa.Float()),
        sa.Column("sample_orientation", sa.String(120)), sa.Column("frequency_value", sa.Float()),
        sa.Column("frequency_unit", sa.String(40)), sa.Column("material_state", sa.String(160)),
        sa.Column("metadata", JSONB, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)),
    )

    # Multiple observations per property/evidence become valid in Phase 2 because conditions differ.
    op.drop_constraint("uq_observation_evidence", "material_property_observations", type_="unique")
    for column in [
        sa.Column("condition_set_id", sa.String(36), nullable=True),
        sa.Column("source_record_id", sa.String(36), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("uncertainty_type", sa.String(40), nullable=True),
        sa.Column("uncertainty_lower", sa.Float(), nullable=True),
        sa.Column("uncertainty_upper", sa.Float(), nullable=True),
        sa.Column("uncertainty_stddev", sa.Float(), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="active"),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("curator_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("curator_note", sa.Text(), nullable=True),
    ]:
        op.add_column("material_property_observations", column)
    op.create_foreign_key("fk_observation_condition_set", "material_property_observations", "observation_condition_sets", ["condition_set_id"], ["id"])
    op.create_foreign_key("fk_observation_source_record", "material_property_observations", "source_records", ["source_record_id"], ["id"])
    op.create_index("ix_observation_condition_set_id", "material_property_observations", ["condition_set_id"])
    op.create_index("ix_observation_source_record_id", "material_property_observations", ["source_record_id"])
    op.create_index("ix_observation_status", "material_property_observations", ["status"])
    op.create_index("ix_observation_curator_preferred", "material_property_observations", ["curator_preferred"])
    op.create_index("ix_observation_material_property_status", "material_property_observations", ["material_id", "property_definition_id", "status"])

    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("source_providers.id"), nullable=False),
        sa.Column("input_format", sa.String(20), nullable=False), sa.Column("payload_checksum", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(120)), sa.Column("status", sa.String(40), nullable=False),
        sa.Column("summary", JSONB, nullable=False), sa.Column("errors", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)), sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "payload_checksum", "status", name="uq_import_scope_payload_status"),
    )
    op.create_index("ix_import_batches_organisation_id", "import_batches", ["organisation_id"])
    op.create_index("ix_import_batches_provider_id", "import_batches", ["provider_id"])
    op.create_index("ix_import_batches_payload_checksum", "import_batches", ["payload_checksum"])
    op.create_index("ix_import_batches_status", "import_batches", ["status"])


def downgrade():
    op.drop_table("import_batches")
    for idx in ["ix_observation_material_property_status", "ix_observation_curator_preferred", "ix_observation_status", "ix_observation_source_record_id", "ix_observation_condition_set_id"]:
        op.drop_index(idx, table_name="material_property_observations")
    op.drop_constraint("fk_observation_source_record", "material_property_observations", type_="foreignkey")
    op.drop_constraint("fk_observation_condition_set", "material_property_observations", type_="foreignkey")
    for col in ["curator_note", "curator_preferred", "imported_at", "reported_at", "status", "uncertainty_stddev", "uncertainty_upper", "uncertainty_lower", "uncertainty_type", "method", "source_record_id", "condition_set_id"]:
        op.drop_column("material_property_observations", col)
    op.create_unique_constraint("uq_observation_evidence", "material_property_observations", ["material_id", "property_definition_id", "evidence_id"])
    op.drop_table("observation_condition_sets")
    op.drop_table("material_process_states")
    op.drop_table("material_components")
    op.drop_index("uq_public_identifier_namespace_value", table_name="material_identifiers")
    op.drop_table("material_identifiers")
    for idx in ["ix_evidence_status", "ix_evidence_visibility", "ix_evidence_organisation_id", "ix_evidence_source_record_id", "ix_evidence_provider_id"]:
        op.drop_index(idx, table_name="evidence")
    for fk in ["fk_evidence_org", "fk_evidence_parent", "fk_evidence_citation", "fk_evidence_source_record", "fk_evidence_provider"]:
        op.drop_constraint(fk, "evidence", type_="foreignkey")
    for col in ["source_quality", "curator_note", "evidence_date", "status", "visibility", "organisation_id", "parent_evidence_id", "citation_id", "source_record_id", "provider_id"]:
        op.drop_column("evidence", col)
    op.drop_table("source_records")
    op.drop_table("citations")
    op.drop_table("source_providers")
    for col in ["conflict_relative_tolerance", "conflict_absolute_tolerance", "conflict_policy"]:
        op.drop_column("material_property_definitions", col)
    for idx in ["ix_materials_display_name", "ix_materials_visibility", "ix_materials_owner_organisation_id"]:
        op.drop_index(idx, table_name="materials")
    op.drop_constraint("fk_material_owner_org", "materials", type_="foreignkey")
    op.drop_column("materials", "visibility")
    op.drop_column("materials", "owner_organisation_id")
