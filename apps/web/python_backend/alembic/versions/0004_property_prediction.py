"""Phase 4 property prediction and uncertainty engine

Revision ID: 0004_phase4
Revises: 0003_phase3
Create Date: 2026-08-12
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_phase4"
down_revision = "0003_phase3"
branch_labels = None
depends_on = None
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "prediction_models",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=True),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("model_type", sa.String(80), nullable=False),
        sa.Column("owner_provider", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("supported_material_families", JSONB, nullable=False),
        sa.Column("supported_property_keys", JSONB, nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "key", name="uq_prediction_model_scope_key"),
    )
    op.create_index("ix_prediction_models_organisation_id", "prediction_models", ["organisation_id"])
    op.create_index("ix_prediction_models_key", "prediction_models", ["key"])
    op.create_index("ix_prediction_models_status", "prediction_models", ["status"])
    op.create_index("ix_prediction_model_scope_status", "prediction_models", ["organisation_id", "status"])

    op.create_table(
        "prediction_model_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("prediction_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("predictor_key", sa.String(160), nullable=False),
        sa.Column("predictor_contract_version", sa.String(40), nullable=False),
        sa.Column("artifact_format", sa.String(80), nullable=False),
        sa.Column("artifact_payload", JSONB, nullable=False),
        sa.Column("artifact_checksum", sa.String(64), nullable=False),
        sa.Column("feature_schema_version", sa.String(80), nullable=False),
        sa.Column("feature_schema", JSONB, nullable=False),
        sa.Column("feature_schema_checksum", sa.String(64), nullable=False),
        sa.Column("target_property_key", sa.String(120), nullable=False),
        sa.Column("canonical_output_unit", sa.String(80), nullable=False),
        sa.Column("uncertainty_method", sa.String(120), nullable=False),
        sa.Column("applicability_policy_version", sa.String(80), nullable=False),
        sa.Column("training_data_descriptor", JSONB, nullable=False),
        sa.Column("training_data_checksum", sa.String(64)),
        sa.Column("calibration_metrics", JSONB, nullable=False),
        sa.Column("validation_metrics", JSONB, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("immutable_metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("model_id", "version", name="uq_prediction_model_version"),
    )
    for col in ["model_id", "artifact_checksum", "target_property_key"]:
        op.create_index(f"ix_prediction_model_versions_{col}", "prediction_model_versions", [col])
    op.create_index("ix_prediction_model_version_property", "prediction_model_versions", ["target_property_key", "approved_at"])

    op.create_table(
        "model_applicability_domains",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("material_families", JSONB, nullable=False),
        sa.Column("required_feature_keys", JSONB, nullable=False),
        sa.Column("numeric_feature_ranges", JSONB, nullable=False),
        sa.Column("allowed_categorical_values", JSONB, nullable=False),
        sa.Column("required_component_keys", JSONB, nullable=False),
        sa.Column("target_condition_ranges", JSONB, nullable=False),
        sa.Column("redacted_input_policy", sa.String(40), nullable=False, server_default="reject"),
        sa.Column("domain_distance_method", sa.String(120)),
        sa.Column("domain_distance_config", JSONB, nullable=False),
        sa.Column("borderline_tolerance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_model_applicability_domains_model_version_id", "model_applicability_domains", ["model_version_id"], unique=True)

    op.create_table(
        "prediction_targets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE")),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE")),
        sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False),
        sa.Column("requested_conditions", JSONB, nullable=False),
        sa.Column("condition_checksum", sa.String(64), nullable=False),
        sa.Column("requested_output_unit", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)", name="ck_prediction_target_exactly_one_scientific_object"),
    )
    for col in ["organisation_id", "project_id", "candidate_id", "material_id", "hypothesis_id", "property_definition_id"]:
        op.create_index(f"ix_prediction_targets_{col}", "prediction_targets", [col])
    op.create_index("ix_prediction_target_project_property", "prediction_targets", ["project_id", "property_definition_id"])

    op.create_table(
        "prediction_input_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("prediction_target_id", sa.String(36), sa.ForeignKey("prediction_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id"), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("feature_schema_version", sa.String(80), nullable=False),
        sa.Column("normalized_feature_payload", JSONB, nullable=False),
        sa.Column("feature_checksum", sa.String(64), nullable=False),
        sa.Column("source_entity_checksum", sa.String(64), nullable=False),
        sa.Column("target_condition_checksum", sa.String(64), nullable=False),
        sa.Column("missing_features", JSONB, nullable=False),
        sa.Column("redaction_flags", JSONB, nullable=False),
        sa.Column("unit_normalization_version", sa.String(40), nullable=False, server_default="units-v1"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for col in ["prediction_target_id", "model_version_id", "feature_checksum"]:
        op.create_index(f"ix_prediction_input_snapshots_{col}", "prediction_input_snapshots", [col])
    op.create_index("ix_prediction_snapshot_model_feature", "prediction_input_snapshots", ["model_version_id", "feature_checksum"])

    op.create_table(
        "prediction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id"), nullable=False),
        sa.Column("property_key", sa.String(120), nullable=False),
        sa.Column("configuration_checksum", sa.String(64), nullable=False),
        sa.Column("target_condition_checksum", sa.String(64), nullable=False),
        sa.Column("requested_target_count", sa.Integer(), nullable=False),
        sa.Column("predicted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inapplicable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("run_seed", sa.Integer()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("result_checksum", sa.String(64)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for col in ["organisation_id", "project_id", "model_version_id", "property_key", "status", "result_checksum"]:
        op.create_index(f"ix_prediction_runs_{col}", "prediction_runs", [col])
    op.create_index("ix_prediction_run_project_status", "prediction_runs", ["project_id", "status"])
    op.create_index("ix_prediction_run_org_model", "prediction_runs", ["organisation_id", "model_version_id"])

    op.create_table(
        "property_predictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("prediction_run_id", sa.String(36), sa.ForeignKey("prediction_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prediction_target_id", sa.String(36), sa.ForeignKey("prediction_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("prediction_model_versions.id"), nullable=False),
        sa.Column("input_snapshot_id", sa.String(36), sa.ForeignKey("prediction_input_snapshots.id"), nullable=False),
        sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False),
        sa.Column("applicability_status", sa.String(40), nullable=False),
        sa.Column("applicability_rationale", JSONB, nullable=False),
        sa.Column("domain_distance", sa.Float()),
        sa.Column("numeric_point_estimate", sa.Float()),
        sa.Column("output_unit", sa.String(80)),
        sa.Column("canonical_value", sa.Float()),
        sa.Column("canonical_unit", sa.String(80)),
        sa.Column("uncertainty_lower", sa.Float()),
        sa.Column("uncertainty_upper", sa.Float()),
        sa.Column("uncertainty_stddev", sa.Float()),
        sa.Column("uncertainty_method", sa.String(120), nullable=False),
        sa.Column("calibrated_coverage_level", sa.Float()),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("deterministic_result_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("prediction_run_id", "prediction_target_id", name="uq_prediction_run_target"),
    )
    for col in ["prediction_run_id", "prediction_target_id", "model_version_id", "input_snapshot_id", "property_definition_id", "applicability_status", "status", "deterministic_result_checksum"]:
        op.create_index(f"ix_property_predictions_{col}", "property_predictions", [col])
    op.create_index("ix_property_prediction_target_status", "property_predictions", ["prediction_target_id", "status"])
    op.create_index("ix_property_prediction_model_property", "property_predictions", ["model_version_id", "property_definition_id"])


def downgrade():
    op.drop_table("property_predictions")
    op.drop_table("prediction_runs")
    op.drop_table("prediction_input_snapshots")
    op.drop_table("prediction_targets")
    op.drop_table("model_applicability_domains")
    op.drop_table("prediction_model_versions")
    op.drop_table("prediction_models")
