"""Phase 13.1 property evidence envelopes and evidence tiers.

Revision ID: 0014_phase13_1
Revises: 0013_phase11

Additive migration. Legacy observations are not rewritten or deleted. Unknown conditions remain
UNKNOWN; the migration never invents room-temperature applicability.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0014_phase13_1"
down_revision = "0013_phase11"
branch_labels = None
depends_on = None
JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _classify_tier(evidence_type: Any, source_quality: Any, metadata: Any, material_source_type: Any):
    meta = _json(metadata)
    data_grade = str(meta.get("data_grade") or "").lower()
    et = str(evidence_type or "").lower()
    sq = str(source_quality or "").lower()
    mst = str(material_source_type or "").lower()
    if et in {"seed_demo", "seed_demonstration", "demonstration"} or meta.get("demo_only") is True:
        return None, "NOT_SCIENTIFIC_EVIDENCE", "synthetic/demonstration evidence excluded from scientific tiering"
    if data_grade == "handbook_typical" or sq == "handbook_typical" or mst == "reference_library":
        return "HANDBOOK", "ASSESSED", "explicit handbook/reference typical provenance"
    if data_grade == "supplier_datasheet" or sq == "supplier_declared" or et in {"supplier", "vendor"}:
        return "VENDOR_TYPICAL", "ASSESSED", "supplier/vendor typical provenance"
    if data_grade == "published_literature" or sq == "peer_reviewed":
        return "PEER_REVIEWED", "ASSESSED", "peer-reviewed provenance"
    if et in {"computed_database", "prediction", "predicted", "dft", "ml_prediction"}:
        return "PREDICTED", "ASSESSED", "computed/predicted provenance"
    if et == "experimental" or data_grade in {"accredited_laboratory", "internal_measurement"}:
        if meta.get("exact_lot") is True or meta.get("measured_this_lot") is True:
            return "MEASURED_THIS_LOT", "ASSESSED", "explicit exact-lot metadata"
        return "MEASURED_EQUIVALENT", "ASSESSED", "experimental provenance without exact-lot proof"
    return None, "UNASSESSED", "legacy provenance cannot be mapped honestly"


def _temperature(conditions: Any, condition_row: Any):
    if condition_row is not None:
        value = condition_row.get("temperature_value")
        unit = str(condition_row.get("temperature_unit") or "").strip().lower()
        if value is not None and unit in {"k", "kelvin"}:
            return float(value), "KNOWN", "condition_set"
        if value is not None and unit in {"degc", "c", "°c", "celsius"}:
            return float(value) + 273.15, "KNOWN", "condition_set"
    raw = _json(conditions)
    if isinstance(raw.get("temperature_k"), (int, float)):
        return float(raw["temperature_k"]), "KNOWN", "legacy_conditions.temperature_k"
    temp = raw.get("temperature")
    if isinstance(temp, dict) and isinstance(temp.get("value"), (int, float)):
        unit = str(temp.get("unit") or "").strip().lower()
        if unit in {"k", "kelvin"}:
            return float(temp["value"]), "KNOWN", "legacy_conditions.temperature"
        if unit in {"degc", "c", "°c", "celsius"}:
            return float(temp["value"]) + 273.15, "KNOWN", "legacy_conditions.temperature"
    return None, "UNKNOWN", "not_reported"


def upgrade() -> None:
    op.create_table(
        "property_measurements_v13",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legacy_observation_id", sa.String(36), sa.ForeignKey("material_property_observations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_definition_id", sa.String(36), sa.ForeignKey("material_property_definitions.id"), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("reported_numeric_value", sa.Float()), sa.Column("reported_boolean_value", sa.Boolean()), sa.Column("reported_unit", sa.String(80)),
        sa.Column("canonical_numeric_value", sa.Float()), sa.Column("canonical_unit", sa.String(80)),
        sa.Column("uncertainty_value", sa.Float()), sa.Column("uncertainty_type", sa.String(40)), sa.Column("uncertainty_lower", sa.Float()), sa.Column("uncertainty_upper", sa.Float()), sa.Column("uncertainty_stddev", sa.Float()),
        sa.Column("distribution", sa.String(30), nullable=False, server_default="unspecified"),
        sa.Column("evidence_tier", sa.String(40)), sa.Column("tier_status", sa.String(40), nullable=False, server_default="UNASSESSED"),
        sa.Column("evidence_id", sa.String(36), sa.ForeignKey("evidence.id"), nullable=False), sa.Column("source_record_id", sa.String(36), sa.ForeignKey("source_records.id")),
        sa.Column("measurement_method", sa.Text()), sa.Column("sample_provenance", JSON, nullable=False, server_default=sa.text("'{}'")), sa.Column("source_ref", sa.Text()),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("migration_metadata", JSON, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("legacy_observation_id", name="uq_property_measurements_v13_legacy_observation"),
    )
    op.create_index("ix_property_measurement_v13_material_property", "property_measurements_v13", ["material_id", "property_definition_id"])
    op.create_index("ix_property_measurements_v13_evidence_tier", "property_measurements_v13", ["evidence_tier"])
    op.create_index("ix_property_measurements_v13_tier_status", "property_measurements_v13", ["tier_status"])
    op.create_index("ix_property_measurements_v13_review_required", "property_measurements_v13", ["review_required"])
    op.create_table(
        "property_validity_envelopes_v13",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("property_measurement_id", sa.String(36), sa.ForeignKey("property_measurements_v13.id", ondelete="CASCADE"), nullable=False),
        sa.Column("temperature_k", sa.Float()), sa.Column("temperature_status", sa.String(30), nullable=False, server_default="UNKNOWN"), sa.Column("pressure_pa", sa.Float()), sa.Column("humidity_percent", sa.Float()),
        sa.Column("stress_state", sa.String(80)), sa.Column("strain_rate", sa.Float()), sa.Column("frequency_hz", sa.Float()), sa.Column("atmosphere", sa.String(160)), sa.Column("field_strength_v_per_m", sa.Float()),
        sa.Column("bias_condition", sa.Text()), sa.Column("time_under_load_s", sa.Float()), sa.Column("direction", sa.String(160)), sa.Column("material_state", sa.String(200)),
        sa.Column("metadata", JSON, nullable=False, server_default=sa.text("'{}'")), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("property_measurement_id", name="uq_property_validity_envelope_v13_measurement"),
    )
    op.create_index("ix_property_validity_envelopes_v13_measurement", "property_validity_envelopes_v13", ["property_measurement_id"])
    op.create_index("ix_property_validity_envelopes_v13_temperature_status", "property_validity_envelopes_v13", ["temperature_status"])

    bind = op.get_bind(); meta = sa.MetaData()
    obs = sa.Table("material_property_observations", meta, autoload_with=bind); evidence = sa.Table("evidence", meta, autoload_with=bind)
    materials = sa.Table("materials", meta, autoload_with=bind); definitions = sa.Table("material_property_definitions", meta, autoload_with=bind)
    conditions = sa.Table("observation_condition_sets", meta, autoload_with=bind); pm = sa.Table("property_measurements_v13", meta, autoload_with=bind); env = sa.Table("property_validity_envelopes_v13", meta, autoload_with=bind)
    for row in bind.execute(sa.select(obs)).mappings().all():
        ev = bind.execute(sa.select(evidence).where(evidence.c.id == row["evidence_id"])).mappings().first(); mat = bind.execute(sa.select(materials).where(materials.c.id == row["material_id"])).mappings().first(); definition = bind.execute(sa.select(definitions).where(definitions.c.id == row["property_definition_id"])).mappings().first()
        cs = bind.execute(sa.select(conditions).where(conditions.c.id == row["condition_set_id"])).mappings().first() if row.get("condition_set_id") else None
        tier, tier_status, tier_reason = _classify_tier(ev.get("evidence_type") if ev else None, ev.get("source_quality") if ev else None, ev.get("metadata") if ev else None, mat.get("source_type") if mat else None)
        temp_k, temp_status, temp_source = _temperature(row.get("conditions"), cs)
        canonical_unit = definition.get("canonical_unit") if definition else None
        canonical_value = float(row["numeric_value"]) if row.get("numeric_value") is not None and row.get("unit") and canonical_unit and str(row["unit"]) == str(canonical_unit) else None
        ev_meta = _json(ev.get("metadata") if ev else {}); declared_dist = str(ev_meta.get("distribution") or "").lower(); distribution = declared_dist if declared_dist in {"normal", "lognormal", "uniform", "weibull", "point"} else "unspecified"
        if distribution == "unspecified" and str(row.get("uncertainty_type") or "").lower() in {"std_dev", "standard_deviation", "standard"} and row.get("uncertainty_stddev") is not None: distribution = "normal"
        bind.execute(pm.insert().values(id=row["id"], legacy_observation_id=row["id"], material_id=row["material_id"], property_definition_id=row["property_definition_id"], value_type=row["value_type"], reported_numeric_value=row.get("numeric_value"), reported_boolean_value=row.get("boolean_value"), reported_unit=row.get("unit"), canonical_numeric_value=canonical_value, canonical_unit=canonical_unit, uncertainty_value=row.get("uncertainty"), uncertainty_type=row.get("uncertainty_type"), uncertainty_lower=row.get("uncertainty_lower"), uncertainty_upper=row.get("uncertainty_upper"), uncertainty_stddev=row.get("uncertainty_stddev"), distribution=distribution, evidence_tier=tier, tier_status=tier_status, evidence_id=row["evidence_id"], source_record_id=row.get("source_record_id"), measurement_method=row.get("method") or (ev.get("method") if ev else None), sample_provenance={}, source_ref=ev.get("source_reference") if ev else None, review_required=True, migration_metadata={"source":"material_property_observations","legacy_observation_id":row["id"],"tier_reason":tier_reason,"temperature_source":temp_source,"temperature_not_imputed":temp_status=="UNKNOWN","canonical_value_not_imputed":canonical_value is None and row.get("numeric_value") is not None}))
        bind.execute(env.insert().values(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tinkerlab:phase13:envelope:{row['id']}")), property_measurement_id=row["id"], temperature_k=temp_k, temperature_status=temp_status, pressure_pa=float(cs["pressure_value"]) if cs and cs.get("pressure_value") is not None and str(cs.get("pressure_unit") or "").lower()=="pa" else None, humidity_percent=cs.get("humidity_percent") if cs else None, strain_rate=cs.get("strain_rate") if cs else None, frequency_hz=float(cs["frequency_value"]) if cs and cs.get("frequency_value") is not None and str(cs.get("frequency_unit") or "").lower()=="hz" else None, direction=cs.get("sample_orientation") if cs else None, material_state=cs.get("material_state") if cs else None, metadata={"migrated_from_legacy":True,"review_required":True}))


def downgrade() -> None:
    op.drop_index("ix_property_validity_envelopes_v13_temperature_status", table_name="property_validity_envelopes_v13"); op.drop_index("ix_property_validity_envelopes_v13_measurement", table_name="property_validity_envelopes_v13"); op.drop_table("property_validity_envelopes_v13")
    op.drop_index("ix_property_measurements_v13_review_required", table_name="property_measurements_v13"); op.drop_index("ix_property_measurements_v13_tier_status", table_name="property_measurements_v13"); op.drop_index("ix_property_measurements_v13_evidence_tier", table_name="property_measurements_v13"); op.drop_index("ix_property_measurement_v13_material_property", table_name="property_measurements_v13"); op.drop_table("property_measurements_v13")
