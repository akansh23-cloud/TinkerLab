"""Phase 6 physics and simulation operating system

Revision ID: 0006_phase6
Revises: 0005_phase5
Create Date: 2026-08-12

Forward-only. Migrations 0001-0005 are not edited. Downgrade removes Phase-6 simulation history
while leaving all Phase-1 to Phase-5 scientific records intact.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_phase6"
down_revision = "0005_phase5"
branch_labels = None
depends_on = None
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "scientific_representations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE")),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("representation_type", sa.String(60), nullable=False),
        sa.Column("representation_format", sa.String(80), nullable=False),
        sa.Column("representation_version", sa.String(40), nullable=False, server_default="1.0"),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("normalized_checksum", sa.String(64), nullable=False),
        sa.Column("content_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("periodicity", sa.String(40)),
        sa.Column("dimensionality", sa.Integer()),
        sa.Column("atom_count", sa.Integer()),
        sa.Column("component_count", sa.Integer()),
        sa.Column("chemical_elements", JSONB, nullable=False),
        sa.Column("validator_key", sa.String(120), nullable=False),
        sa.Column("validator_version", sa.String(40), nullable=False),
        sa.Column("validation_status", sa.String(40), nullable=False),
        sa.Column("completeness_status", sa.String(40), nullable=False),
        sa.Column("validation_messages", JSONB, nullable=False),
        sa.Column("redaction_flags", JSONB, nullable=False),
        sa.Column("provenance_note", sa.Text()),
        sa.Column("source_record_id", sa.String(36), sa.ForeignKey("source_records.id")),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_representation_exactly_one_target",
        ),
    )
    for c in ["organisation_id", "visibility", "material_id", "hypothesis_id", "representation_type",
              "representation_format", "normalized_checksum", "validation_status", "completeness_status", "status"]:
        op.create_index(f"ix_scientific_representations_{c}", "scientific_representations", [c])
    op.create_index("ix_representation_target_type", "scientific_representations", ["representation_type", "status"])
    op.create_index("ix_representation_scope_type", "scientific_representations", ["organisation_id", "representation_type"])

    op.create_table(
        "registered_scientific_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("artifact_type", sa.String(60), nullable=False),
        sa.Column("applies_to_method_families", JSONB, nullable=False),
        sa.Column("applies_to_elements", JSONB, nullable=False),
        sa.Column("applies_to_component_keys", JSONB, nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("content_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_reference", sa.String(200)),
        sa.Column("content_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("license_name", sa.String(200)),
        sa.Column("license_permits_redistribution", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_reference", sa.Text()),
        sa.Column("citation_id", sa.String(36), sa.ForeignKey("citations.id")),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "key", "version", name="uq_registered_artifact_scope_key_version"),
    )
    for c in ["organisation_id", "key", "artifact_type", "content_checksum", "status"]:
        op.create_index(f"ix_registered_scientific_artifacts_{c}", "registered_scientific_artifacts", [c])
    op.create_index("ix_registered_artifact_type_status", "registered_scientific_artifacts", ["artifact_type", "status"])

    op.create_table(
        "simulation_method_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(160), nullable=False, unique=True),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("method_family", sa.String(60), nullable=False),
        sa.Column("purpose", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("required_representation_types", JSONB, nullable=False),
        sa.Column("required_parameters", JSONB, nullable=False),
        sa.Column("optional_parameters", JSONB, nullable=False),
        sa.Column("output_schema", JSONB, nullable=False),
        sa.Column("output_property_keys", JSONB, nullable=False),
        sa.Column("output_units", JSONB, nullable=False),
        sa.Column("convergence_semantics", JSONB, nullable=False),
        sa.Column("known_limitations", JSONB, nullable=False),
        sa.Column("fidelity", sa.String(60), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="approved"),
        sa.Column("definition_version", sa.String(40), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for c in ["key", "method_family", "fidelity", "status"]:
        op.create_index(f"ix_simulation_method_definitions_{c}", "simulation_method_definitions", [c])
    op.create_index("ix_simulation_method_family_status", "simulation_method_definitions", ["method_family", "status"])

    op.create_table(
        "simulation_providers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("provider_type", sa.String(60), nullable=False),
        sa.Column("method_family", sa.String(60), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_project", sa.String(200)),
        sa.Column("safety_class", sa.String(60), nullable=False, server_default="reviewed_code_registered"),
        sa.Column("approved_execution_mode", sa.String(60), nullable=False, server_default="in_process_fixture"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "key", name="uq_simulation_provider_scope_key"),
    )
    for c in ["organisation_id", "key", "provider_type", "method_family", "status"]:
        op.create_index(f"ix_simulation_providers_{c}", "simulation_providers", [c])
    op.create_index("ix_simulation_provider_scope_status", "simulation_providers", ["organisation_id", "status"])

    op.create_table(
        "simulation_provider_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_id", sa.String(36), sa.ForeignKey("simulation_providers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("adapter_key", sa.String(160), nullable=False),
        sa.Column("adapter_contract_version", sa.String(40), nullable=False),
        sa.Column("executable_key", sa.String(120)),
        sa.Column("executable_version", sa.String(120)),
        sa.Column("executable_checksum", sa.String(64)),
        sa.Column("container_image", sa.String(300)),
        sa.Column("container_digest", sa.String(120)),
        sa.Column("parser_key", sa.String(160), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("input_builder_key", sa.String(160), nullable=False),
        sa.Column("input_builder_version", sa.String(40), nullable=False),
        sa.Column("convergence_evaluator_key", sa.String(160), nullable=False),
        sa.Column("convergence_evaluator_version", sa.String(40), nullable=False),
        sa.Column("supported_method_keys", JSONB, nullable=False),
        sa.Column("supported_material_families", JSONB, nullable=False),
        sa.Column("supported_representation_types", JSONB, nullable=False),
        sa.Column("supported_representation_formats", JSONB, nullable=False),
        sa.Column("supported_property_keys", JSONB, nullable=False),
        sa.Column("required_artifact_types", JSONB, nullable=False),
        sa.Column("artifact_manifest", JSONB, nullable=False),
        sa.Column("artifact_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("environment_manifest", JSONB, nullable=False),
        sa.Column("fidelity", sa.String(60), nullable=False),
        sa.Column("deterministic", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("execution_supported", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maximum_target_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximum_wall_time_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("resource_class", sa.String(60), nullable=False, server_default="local_small"),
        sa.Column("known_limitations", JSONB, nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("immutable_metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("provider_id", "version", name="uq_simulation_provider_version"),
    )
    for c in ["provider_id", "adapter_key"]:
        op.create_index(f"ix_simulation_provider_versions_{c}", "simulation_provider_versions", [c])
    op.create_index("ix_simulation_provider_version_adapter", "simulation_provider_versions", ["adapter_key", "approved_at"])

    op.create_table(
        "simulation_input_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("target_fingerprint", sa.String(64), nullable=False),
        sa.Column("representation_id", sa.String(36), sa.ForeignKey("scientific_representations.id"), nullable=False),
        sa.Column("representation_checksum", sa.String(64), nullable=False),
        sa.Column("method_definition_id", sa.String(36), sa.ForeignKey("simulation_method_definitions.id"), nullable=False),
        sa.Column("method_definition_version", sa.String(40), nullable=False),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id"), nullable=False),
        sa.Column("normalized_parameters", JSONB, nullable=False),
        sa.Column("target_conditions", JSONB, nullable=False),
        sa.Column("condition_checksum", sa.String(64), nullable=False),
        sa.Column("input_builder_key", sa.String(160), nullable=False),
        sa.Column("input_builder_version", sa.String(40), nullable=False),
        sa.Column("artifact_references", JSONB, nullable=False),
        sa.Column("artifact_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("unit_normalization_version", sa.String(40), nullable=False, server_default="units-v1"),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("redaction_flags", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for c in ["organisation_id", "target_scientific_id", "representation_id", "method_definition_id",
              "provider_version_id", "input_checksum"]:
        op.create_index(f"ix_simulation_input_snapshots_{c}", "simulation_input_snapshots", [c])
    op.create_index("ix_simulation_snapshot_provider_input", "simulation_input_snapshots", ["provider_version_id", "input_checksum"])

    op.create_table(
        "simulation_routes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("requested_purpose", sa.String(120), nullable=False),
        sa.Column("requested_property_key", sa.String(120)),
        sa.Column("requested_conditions", JSONB, nullable=False),
        sa.Column("representation_id", sa.String(36), sa.ForeignKey("scientific_representations.id")),
        sa.Column("method_definition_id", sa.String(36), sa.ForeignKey("simulation_method_definitions.id")),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id")),
        sa.Column("route_status", sa.String(60), nullable=False),
        sa.Column("applicability_reasons", JSONB, nullable=False),
        sa.Column("missing_representation_types", JSONB, nullable=False),
        sa.Column("missing_artifact_types", JSONB, nullable=False),
        sa.Column("fidelity", sa.String(60)),
        sa.Column("estimated_resource_class", sa.String(60)),
        sa.Column("route_policy_version", sa.String(40), nullable=False, server_default="router-v1"),
        sa.Column("route_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for c in ["organisation_id", "target_scientific_id", "representation_id", "provider_version_id",
              "route_status", "route_checksum"]:
        op.create_index(f"ix_simulation_routes_{c}", "simulation_routes", [c])
    op.create_index("ix_simulation_route_target_status", "simulation_routes", ["target_scientific_id", "route_status"])

    op.create_table(
        "simulation_workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="SET NULL")),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("campaign_id", sa.String(36), sa.ForeignKey("virtual_experiment_campaigns.id", ondelete="SET NULL")),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("route_id", sa.String(36), sa.ForeignKey("simulation_routes.id"), nullable=False),
        sa.Column("input_snapshot_id", sa.String(36), sa.ForeignKey("simulation_input_snapshots.id"), nullable=False),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id"), nullable=False),
        sa.Column("method_definition_id", sa.String(36), sa.ForeignKey("simulation_method_definitions.id"), nullable=False),
        sa.Column("workflow_template_key", sa.String(160), nullable=False),
        sa.Column("workflow_template_version", sa.String(40), nullable=False),
        sa.Column("requested_purpose", sa.String(120), nullable=False),
        sa.Column("requested_property_key", sa.String(120)),
        sa.Column("requested_fidelity", sa.String(60), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_wall_time_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("status", sa.String(30), nullable=False, server_default="prepared"),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("workflow_checksum", sa.String(64)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for c in ["organisation_id", "project_id", "candidate_id", "campaign_id", "target_scientific_id",
              "route_id", "input_snapshot_id", "provider_version_id", "method_definition_id", "status", "workflow_checksum"]:
        op.create_index(f"ix_simulation_workflows_{c}", "simulation_workflows", [c])
    op.create_index("ix_simulation_workflow_org_status", "simulation_workflows", ["organisation_id", "status"])
    op.create_index("ix_simulation_workflow_target", "simulation_workflows", ["target_kind", "target_scientific_id"])

    op.create_table(
        "simulation_workflow_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("simulation_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(120), nullable=False),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id"), nullable=False),
        sa.Column("method_key", sa.String(160), nullable=False),
        sa.Column("depends_on_step_ids", JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="prepared"),
        sa.Column("input_checksum", sa.String(64), nullable=False),
        sa.Column("output_checksum", sa.String(64)),
        sa.Column("requires_convergence", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_policy_version", sa.String(40), nullable=False, server_default="retry-v1"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workflow_id", "sequence", name="uq_simulation_step_sequence"),
    )
    for c in ["workflow_id", "provider_version_id", "status"]:
        op.create_index(f"ix_simulation_workflow_steps_{c}", "simulation_workflow_steps", [c])
    op.create_index("ix_simulation_step_workflow_status", "simulation_workflow_steps", ["workflow_id", "status"])

    op.create_table(
        "simulation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("simulation_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(36), sa.ForeignKey("simulation_workflow_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("workdir_token", sa.String(64), nullable=False),
        sa.Column("command_descriptor", JSONB, nullable=False),
        sa.Column("resource_request", JSONB, nullable=False),
        sa.Column("compute_backend_key", sa.String(60), nullable=False, server_default="local_bounded_v1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("process_exit_code", sa.Integer()),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("elapsed_seconds", sa.Float()),
        sa.Column("stdout_artifact_id", sa.String(36)),
        sa.Column("stderr_artifact_id", sa.String(36)),
        sa.Column("operational_checksum", sa.String(64), nullable=False),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("step_id", "attempt_number", name="uq_simulation_job_attempt"),
    )
    for c in ["workflow_id", "step_id", "provider_version_id", "status"]:
        op.create_index(f"ix_simulation_jobs_{c}", "simulation_jobs", [c])
    op.create_index("ix_simulation_job_workflow_status", "simulation_jobs", ["workflow_id", "status"])

    op.create_table(
        "simulation_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("simulation_workflows.id", ondelete="CASCADE")),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("simulation_jobs.id", ondelete="CASCADE")),
        sa.Column("artifact_type", sa.String(60), nullable=False),
        sa.Column("content_role", sa.String(80), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False, server_default="text/plain"),
        sa.Column("storage_reference", sa.String(200), nullable=False),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("content_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("inline_preview", sa.Text()),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for c in ["organisation_id", "workflow_id", "job_id", "artifact_type"]:
        op.create_index(f"ix_simulation_artifacts_{c}", "simulation_artifacts", [c])
    op.create_index("ix_simulation_artifact_workflow_type", "simulation_artifacts", ["workflow_id", "artifact_type"])
    op.create_index("ix_simulation_artifact_checksum", "simulation_artifacts", ["content_checksum"])

    op.create_table(
        "simulation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("simulation_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("simulation_jobs.id", ondelete="SET NULL")),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("method_definition_id", sa.String(36), sa.ForeignKey("simulation_method_definitions.id"), nullable=False),
        sa.Column("provider_version_id", sa.String(36), sa.ForeignKey("simulation_provider_versions.id"), nullable=False),
        sa.Column("operational_status", sa.String(30), nullable=False),
        sa.Column("scientific_status", sa.String(40), nullable=False),
        sa.Column("convergence_metrics", JSONB, nullable=False),
        sa.Column("convergence_criteria", JSONB, nullable=False),
        sa.Column("convergence_evaluator_version", sa.String(40), nullable=False),
        sa.Column("parser_key", sa.String(160), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("parsed_quantities", JSONB, nullable=False),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("method_limitations", JSONB, nullable=False),
        sa.Column("output_artifact_checksums", JSONB, nullable=False),
        sa.Column("result_checksum", sa.String(64), nullable=False),
        sa.Column("scientific_origin", sa.String(40), nullable=False, server_default="physics_simulation"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workflow_id", name="uq_simulation_result_workflow"),
    )
    for c in ["organisation_id", "workflow_id", "job_id", "target_scientific_id", "method_definition_id",
              "provider_version_id", "operational_status", "scientific_status", "result_checksum"]:
        op.create_index(f"ix_simulation_results_{c}", "simulation_results", [c])
    op.create_index("ix_simulation_result_target_status", "simulation_results", ["target_scientific_id", "scientific_status"])

    op.create_table(
        "simulation_property_estimates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("simulation_result_id", sa.String(36), sa.ForeignKey("simulation_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False),
        sa.Column("numeric_value", sa.Float()),
        sa.Column("raw_unit", sa.String(80)),
        sa.Column("canonical_value", sa.Float()),
        sa.Column("canonical_unit", sa.String(80)),
        sa.Column("numerical_tolerance", sa.Float()),
        sa.Column("tolerance_basis", sa.String(120)),
        sa.Column("method_limitations", JSONB, nullable=False),
        sa.Column("target_conditions", JSONB, nullable=False),
        sa.Column("extractor_key", sa.String(160), nullable=False),
        sa.Column("extractor_version", sa.String(40), nullable=False),
        sa.Column("estimate_checksum", sa.String(64), nullable=False),
        sa.Column("scientific_origin", sa.String(40), nullable=False, server_default="physics_simulation"),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("simulation_result_id", "property_definition_id", name="uq_simulation_estimate_property"),
    )
    for c in ["simulation_result_id", "property_definition_id", "estimate_checksum"]:
        op.create_index(f"ix_simulation_property_estimates_{c}", "simulation_property_estimates", [c])
    op.create_index("ix_simulation_estimate_property", "simulation_property_estimates", ["property_definition_id", "created_at"])

    op.create_table(
        "simulation_selection_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("policy_key", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False, server_default="1.0"),
        sa.Column("simulation_workflow_id", sa.String(36), sa.ForeignKey("simulation_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("project_id", "property_definition_id", "target_scientific_id", name="uq_simulation_selection_scope"),
    )
    for c in ["organisation_id", "project_id", "property_definition_id", "target_scientific_id", "simulation_workflow_id"]:
        op.create_index(f"ix_simulation_selection_policies_{c}", "simulation_selection_policies", [c])


def downgrade():
    # Phase-6 simulation history is removed. Phase-1 to Phase-5 scientific records are untouched:
    # no observation, prediction, hypothesis or campaign row is created or deleted by this migration.
    op.drop_table("simulation_selection_policies")
    op.drop_table("simulation_property_estimates")
    op.drop_table("simulation_results")
    op.drop_table("simulation_artifacts")
    op.drop_table("simulation_jobs")
    op.drop_table("simulation_workflow_steps")
    op.drop_table("simulation_workflows")
    op.drop_table("simulation_routes")
    op.drop_table("simulation_input_snapshots")
    op.drop_table("simulation_provider_versions")
    op.drop_table("simulation_providers")
    op.drop_table("simulation_method_definitions")
    op.drop_table("registered_scientific_artifacts")
    op.drop_table("scientific_representations")
