"""Phase 7 industrial viability engine

Revision ID: 0007_phase7
Revises: 0006_phase6
Create Date: 2026-08-13

Forward-only. Migrations 0001-0006 are not edited. Downgrade removes only Phase-7 industrial
tables; no scientific record from Phases 1-6 is created, altered or deleted by this migration.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_phase7"
down_revision = "0006_phase6"
branch_labels = None
depends_on = None
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade():
    op.create_table(
        "manufacturing_routes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("process_family", sa.String(60), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("applies_to_material_families", JSONB, nullable=False),
        sa.Column("applies_to_elements", JSONB, nullable=False),
        sa.Column("required_equipment", JSONB, nullable=False),
        sa.Column("process_temperature_k_min", sa.Float()),
        sa.Column("process_temperature_k_max", sa.Float()),
        sa.Column("process_pressure_pa_min", sa.Float()),
        sa.Column("process_pressure_pa_max", sa.Float()),
        sa.Column("achievable_thickness_m_min", sa.Float()),
        sa.Column("achievable_thickness_m_max", sa.Float()),
        sa.Column("achievable_tolerance_m", sa.Float()),
        sa.Column("surface_finish_ra_m", sa.Float()),
        sa.Column("typical_yield_fraction", sa.Float()),
        sa.Column("throughput_units_per_hour", sa.Float()),
        sa.Column("capex_class", sa.String(60)),
        sa.Column("process_maturity", sa.String(60), nullable=False, server_default="unknown"),
        sa.Column("scale_up_maturity", sa.String(60), nullable=False, server_default="unknown"),
        sa.Column("known_limitations", JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organisation_id", "key", name="uq_manufacturing_route_scope_key"),
    )
    for column in ("organisation_id", "visibility", "key", "process_family", "process_maturity", "status"):
        op.create_index(f"ix_manufacturing_routes_{column}", "manufacturing_routes", [column])
    op.create_index("ix_manufacturing_route_family_status", "manufacturing_routes", ["process_family", "status"])

    op.create_table(
        "industrial_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE")),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("display_label", sa.String(300), nullable=False),
        sa.Column("numeric_value", sa.Float()),
        sa.Column("lower_bound", sa.Float()),
        sa.Column("upper_bound", sa.Float()),
        sa.Column("uncertainty", sa.Float()),
        sa.Column("unit", sa.String(80)),
        sa.Column("boolean_value", sa.Boolean()),
        sa.Column("categorical_value", sa.String(160)),
        sa.Column("currency", sa.String(10)),
        sa.Column("currency_year", sa.Integer()),
        sa.Column("cost_basis", sa.String(40)),
        sa.Column("quantity_basis_value", sa.Float()),
        sa.Column("quantity_basis_unit", sa.String(40)),
        sa.Column("geography", sa.String(120)),
        sa.Column("jurisdiction", sa.String(120)),
        sa.Column("process_context", sa.String(200)),
        sa.Column("manufacturing_route_id", sa.String(36), sa.ForeignKey("manufacturing_routes.id", ondelete="SET NULL")),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("as_of_date", sa.Date()),
        sa.Column("valid_until", sa.Date()),
        sa.Column("source_type", sa.String(60), nullable=False),
        sa.Column("source_reference", sa.Text()),
        sa.Column("source_record_id", sa.String(36), sa.ForeignKey("source_records.id")),
        sa.Column("citation_id", sa.String(36), sa.ForeignKey("citations.id")),
        sa.Column("extraction_method", sa.String(160)),
        sa.Column("confidence", sa.Float()),
        sa.Column("is_estimate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scientific_origin", sa.String(40), nullable=False, server_default="industrial_evidence"),
        sa.Column("notes", sa.Text()),
        sa.Column("content_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_industrial_evidence_exactly_one_target",
        ),
    )
    for column in ("organisation_id", "visibility", "material_id", "hypothesis_id", "category", "metric_key",
                   "geography", "jurisdiction", "manufacturing_route_id", "as_of_date", "source_type",
                   "source_record_id", "citation_id", "is_estimate", "content_checksum", "status"):
        op.create_index(f"ix_industrial_evidence_{column}", "industrial_evidence", [column])
    op.create_index("ix_industrial_evidence_target_metric", "industrial_evidence", ["material_id", "category", "metric_key"])
    op.create_index("ix_industrial_evidence_hypothesis_metric", "industrial_evidence", ["hypothesis_id", "category", "metric_key"])
    op.create_index("ix_industrial_evidence_asof", "industrial_evidence", ["metric_key", "as_of_date"])

    op.create_table(
        "material_process_compatibilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("route_id", sa.String(36), sa.ForeignKey("manufacturing_routes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE")),
        sa.Column("compatibility", sa.String(40), nullable=False, server_default="unknown"),
        sa.Column("rationale", sa.Text()),
        sa.Column("conditions", JSONB, nullable=False),
        sa.Column("industrial_evidence_id", sa.String(36), sa.ForeignKey("industrial_evidence.id", ondelete="SET NULL")),
        sa.Column("as_of_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_process_compatibility_exactly_one_target",
        ),
        sa.UniqueConstraint("route_id", "material_id", "hypothesis_id", name="uq_process_compatibility_target"),
    )
    for column in ("organisation_id", "route_id", "material_id", "hypothesis_id", "compatibility", "industrial_evidence_id"):
        op.create_index(f"ix_material_process_compatibilities_{column}", "material_process_compatibilities", [column])
    op.create_index("ix_process_compatibility_state", "material_process_compatibilities", ["compatibility", "route_id"])

    op.create_table(
        "industrial_constraints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("constraint_kind", sa.String(60), nullable=False),
        sa.Column("metric_key", sa.String(120)),
        sa.Column("display_label", sa.String(300), nullable=False),
        sa.Column("strength", sa.String(20), nullable=False, server_default="hard"),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("target_value", sa.Float()),
        sa.Column("target_value_upper", sa.Float()),
        sa.Column("target_unit", sa.String(80)),
        sa.Column("currency", sa.String(10)),
        sa.Column("currency_year", sa.Integer()),
        sa.Column("cost_basis", sa.String(40)),
        sa.Column("banned_elements", JSONB, nullable=False),
        sa.Column("allowed_jurisdictions", JSONB, nullable=False),
        sa.Column("required_route_keys", JSONB, nullable=False),
        sa.Column("minimum_maturity", sa.String(60)),
        sa.Column("minimum_supplier_count", sa.Integer()),
        sa.Column("treat_missing_evidence_as", sa.String(40), nullable=False, server_default="insufficient_evidence"),
        sa.Column("rationale", sa.Text()),
        sa.Column("metadata", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for column in ("organisation_id", "project_id", "category", "metric_key", "strength"):
        op.create_index(f"ix_industrial_constraints_{column}", "industrial_constraints", [column])
    op.create_index("ix_industrial_constraint_project_category", "industrial_constraints", ["project_id", "category"])

    op.create_table(
        "maturity_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id")),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE")),
        sa.Column("hypothesis_id", sa.String(36), sa.ForeignKey("candidate_hypotheses.id", ondelete="CASCADE")),
        sa.Column("stage", sa.String(60), nullable=False),
        sa.Column("scope", sa.String(200)),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("supporting_evidence_ids", JSONB, nullable=False),
        sa.Column("assessed_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("as_of_date", sa.Date()),
        sa.Column("superseded_by_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_maturity_exactly_one_target",
        ),
    )
    for column in ("organisation_id", "material_id", "hypothesis_id", "stage", "superseded_by_id"):
        op.create_index(f"ix_maturity_assessments_{column}", "maturity_assessments", [column])
    op.create_index("ix_maturity_target_stage", "maturity_assessments", ["material_id", "stage"])

    op.create_table(
        "industrial_viability_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organisation_id", sa.String(36), sa.ForeignKey("organisations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_kind", sa.String(30), nullable=False),
        sa.Column("target_scientific_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id", ondelete="SET NULL")),
        sa.Column("dimension_states", JSONB, nullable=False),
        sa.Column("dimension_details", JSONB, nullable=False),
        sa.Column("hard_constraint_failures", JSONB, nullable=False),
        sa.Column("soft_constraint_results", JSONB, nullable=False),
        sa.Column("unknown_dimensions", JSONB, nullable=False),
        sa.Column("evidence_coverage", JSONB, nullable=False),
        sa.Column("missing_evidence", JSONB, nullable=False),
        sa.Column("conflicting_evidence", JSONB, nullable=False),
        sa.Column("overall_state", sa.String(40), nullable=False),
        sa.Column("composite_score", sa.Float()),
        sa.Column("composite_methodology", sa.String(120)),
        sa.Column("composite_weights", JSONB, nullable=False),
        sa.Column("composite_is_partial", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("maturity_stage", sa.String(60), nullable=False, server_default="unknown"),
        sa.Column("evidence_snapshot", JSONB, nullable=False),
        sa.Column("constraint_snapshot", JSONB, nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False, server_default="industrial-viability-v1"),
        sa.Column("assessment_checksum", sa.String(64), nullable=False),
        sa.Column("superseded_by_id", sa.String(36)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    for column in ("organisation_id", "project_id", "target_scientific_id", "candidate_id",
                   "overall_state", "superseded_by_id"):
        op.create_index(f"ix_industrial_viability_assessments_{column}", "industrial_viability_assessments", [column])
    op.create_index("ix_viability_project_target", "industrial_viability_assessments", ["project_id", "target_scientific_id"])
    op.create_index("ix_viability_checksum", "industrial_viability_assessments", ["assessment_checksum"])


def downgrade():
    # Removes Phase-7 industrial records only. Observations, predictions, campaigns and simulation
    # history from Phases 1-6 are untouched by both directions of this migration.
    op.drop_table("industrial_viability_assessments")
    op.drop_table("maturity_assessments")
    op.drop_table("industrial_constraints")
    op.drop_table("material_process_compatibilities")
    op.drop_table("industrial_evidence")
    op.drop_table("manufacturing_routes")
