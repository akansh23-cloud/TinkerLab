"""Phase 13.1 property evidence envelopes and evidence tiers.
Revision ID: 0014_phase13_1
Revises: 0013_phase11
Additive migration; unknown conditions remain UNKNOWN and are never imputed.
"""
from __future__ import annotations
import json, uuid
from typing import Any
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op
revision="0014_phase13_1"; down_revision="0013_phase11"; branch_labels=None; depends_on=None
JSON=sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()),"postgresql")

def _json(v:Any)->dict[str,Any]:
    if isinstance(v,dict): return v
    if isinstance(v,str):
        try:
            p=json.loads(v); return p if isinstance(p,dict) else {}
        except Exception:return {}
    return {}

def _tier(et:Any,sq:Any,md:Any,mst:Any):
    m=_json(md); dg=str(m.get("data_grade") or "").lower(); et=str(et or "").lower(); sq=str(sq or "").lower(); mst=str(mst or "").lower()
    if et in {"seed_demo","seed_demonstration","demonstration"} or m.get("demo_only") is True:return None,"NOT_SCIENTIFIC_EVIDENCE","synthetic/demonstration evidence"
    if dg=="handbook_typical" or sq=="handbook_typical" or mst=="reference_library":return "HANDBOOK","ASSESSED","handbook/reference typical provenance"
    if dg=="supplier_datasheet" or sq=="supplier_declared" or et in {"supplier","vendor"}:return "VENDOR_TYPICAL","ASSESSED","supplier/vendor typical provenance"
    if dg=="published_literature" or sq=="peer_reviewed":return "PEER_REVIEWED","ASSESSED","peer-reviewed provenance"
    if et in {"computed_database","prediction","predicted","dft","ml_prediction"}:return "PREDICTED","ASSESSED","computed/predicted provenance"
    if et=="experimental" or dg in {"accredited_laboratory","internal_measurement"}:
        if m.get("exact_lot") is True or m.get("measured_this_lot") is True:return "MEASURED_THIS_LOT","ASSESSED","explicit exact-lot metadata"
        return "MEASURED_EQUIVALENT","ASSESSED","experimental provenance without exact-lot proof"
    return None,"UNASSESSED","legacy provenance cannot be mapped honestly"

def _temperature(raw:Any,cs:Any):
    if cs:
        v=cs.get("temperature_value"); u=str(cs.get("temperature_unit") or "").strip().lower()
        if v is not None and u in {"k","kelvin"}:return float(v),"KNOWN","condition_set"
        if v is not None and u in {"degc","c","°c","celsius"}:return float(v)+273.15,"KNOWN","condition_set"
    r=_json(raw)
    if isinstance(r.get("temperature_k"),(int,float)):return float(r["temperature_k"]),"KNOWN","legacy_conditions.temperature_k"
    t=r.get("temperature")
    if isinstance(t,dict) and isinstance(t.get("value"),(int,float)):
        u=str(t.get("unit") or "").strip().lower()
        if u in {"k","kelvin"}:return float(t["value"]),"KNOWN","legacy_conditions.temperature"
        if u in {"degc","c","°c","celsius"}:return float(t["value"])+273.15,"KNOWN","legacy_conditions.temperature"
    return None,"UNKNOWN","not_reported"

def upgrade()->None:
    op.create_table("property_measurements_v13",sa.Column("id",sa.String(36),primary_key=True),sa.Column("legacy_observation_id",sa.String(36),sa.ForeignKey("material_property_observations.id",ondelete="SET NULL")),sa.Column("material_id",sa.String(36),sa.ForeignKey("materials.id",ondelete="CASCADE"),nullable=False),sa.Column("property_definition_id",sa.String(36),sa.ForeignKey("material_property_definitions.id"),nullable=False),sa.Column("value_type",sa.String(20),nullable=False),sa.Column("reported_numeric_value",sa.Float()),sa.Column("reported_boolean_value",sa.Boolean()),sa.Column("reported_unit",sa.String(80)),sa.Column("canonical_numeric_value",sa.Float()),sa.Column("canonical_unit",sa.String(80)),sa.Column("uncertainty_value",sa.Float()),sa.Column("uncertainty_type",sa.String(40)),sa.Column("uncertainty_lower",sa.Float()),sa.Column("uncertainty_upper",sa.Float()),sa.Column("uncertainty_stddev",sa.Float()),sa.Column("distribution",sa.String(30),nullable=False,server_default="unspecified"),sa.Column("evidence_tier",sa.String(40)),sa.Column("tier_status",sa.String(40),nullable=False,server_default="UNASSESSED"),sa.Column("evidence_id",sa.String(36),sa.ForeignKey("evidence.id"),nullable=False),sa.Column("source_record_id",sa.String(36),sa.ForeignKey("source_records.id")),sa.Column("measurement_method",sa.Text()),sa.Column("sample_provenance",JSON,nullable=False,server_default=sa.text("'{}'")),sa.Column("source_ref",sa.Text()),sa.Column("review_required",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("migration_metadata",JSON,nullable=False,server_default=sa.text("'{}'")),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("legacy_observation_id",name="uq_property_measurements_v13_legacy_observation"))
    op.create_index("ix_property_measurement_v13_material_property","property_measurements_v13",["material_id","property_definition_id"]);op.create_index("ix_property_measurements_v13_evidence_tier","property_measurements_v13",["evidence_tier"]);op.create_index("ix_property_measurements_v13_tier_status","property_measurements_v13",["tier_status"]);op.create_index("ix_property_measurements_v13_review_required","property_measurements_v13",["review_required"])
    op.create_table("property_validity_envelopes_v13",sa.Column("id",sa.String(36),primary_key=True),sa.Column("property_measurement_id",sa.String(36),sa.ForeignKey("property_measurements_v13.id",ondelete="CASCADE"),nullable=False),sa.Column("temperature_k",sa.Float()),sa.Column("temperature_status",sa.String(30),nullable=False,server_default="UNKNOWN"),sa.Column("pressure_pa",sa.Float()),sa.Column("humidity_percent",sa.Float()),sa.Column("stress_state",sa.String(80)),sa.Column("strain_rate",sa.Float()),sa.Column("frequency_hz",sa.Float()),sa.Column("atmosphere",sa.String(160)),sa.Column("field_strength_v_per_m",sa.Float()),sa.Column("bias_condition",sa.Text()),sa.Column("time_under_load_s",sa.Float()),sa.Column("direction",sa.String(160)),sa.Column("material_state",sa.String(200)),sa.Column("metadata",JSON,nullable=False,server_default=sa.text("'{}'")),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("property_measurement_id",name="uq_property_validity_envelope_v13_measurement"))
    op.create_index("ix_property_validity_envelopes_v13_measurement","property_validity_envelopes_v13",["property_measurement_id"]);op.create_index("ix_property_validity_envelopes_v13_temperature_status","property_validity_envelopes_v13",["temperature_status"])
    b=op.get_bind();m=sa.MetaData();o=sa.Table("material_property_observations",m,autoload_with=b);e=sa.Table("evidence",m,autoload_with=b);ma=sa.Table("materials",m,autoload_with=b);d=sa.Table("material_property_definitions",m,autoload_with=b);c=sa.Table("observation_condition_sets",m,autoload_with=b);pm=sa.Table("property_measurements_v13",m,autoload_with=b);env=sa.Table("property_validity_envelopes_v13",m,autoload_with=b)
    for r in b.execute(sa.select(o)).mappings().all():
        ev=b.execute(sa.select(e).where(e.c.id==r["evidence_id"])).mappings().first(); mat=b.execute(sa.select(ma).where(ma.c.id==r["material_id"])).mappings().first(); de=b.execute(sa.select(d).where(d.c.id==r["property_definition_id"])).mappings().first(); cs=b.execute(sa.select(c).where(c.c.id==r["condition_set_id"])).mappings().first() if r.get("condition_set_id") else None
        tier,status,reason=_tier(ev.get("evidence_type") if ev else None,ev.get("source_quality") if ev else None,ev.get("metadata") if ev else None,mat.get("source_type") if mat else None);tk,ts,src=_temperature(r.get("conditions"),cs);cu=de.get("canonical_unit") if de else None;cv=float(r["numeric_value"]) if r.get("numeric_value") is not None and r.get("unit") and cu and str(r["unit"])==str(cu) else None
        dist=str(_json(ev.get("metadata") if ev else {}).get("distribution") or "").lower();dist=dist if dist in {"normal","lognormal","uniform","weibull","point"} else "unspecified"
        b.execute(pm.insert().values(id=r["id"],legacy_observation_id=r["id"],material_id=r["material_id"],property_definition_id=r["property_definition_id"],value_type=r["value_type"],reported_numeric_value=r.get("numeric_value"),reported_boolean_value=r.get("boolean_value"),reported_unit=r.get("unit"),canonical_numeric_value=cv,canonical_unit=cu,uncertainty_value=r.get("uncertainty"),uncertainty_type=r.get("uncertainty_type"),uncertainty_lower=r.get("uncertainty_lower"),uncertainty_upper=r.get("uncertainty_upper"),uncertainty_stddev=r.get("uncertainty_stddev"),distribution=dist,evidence_tier=tier,tier_status=status,evidence_id=r["evidence_id"],source_record_id=r.get("source_record_id"),measurement_method=r.get("method") or (ev.get("method") if ev else None),sample_provenance={},source_ref=ev.get("source_reference") if ev else None,review_required=True,migration_metadata={"source":"material_property_observations","legacy_observation_id":r["id"],"tier_reason":reason,"temperature_source":src,"temperature_not_imputed":ts=="UNKNOWN","canonical_value_not_imputed":cv is None and r.get("numeric_value") is not None}))
        b.execute(env.insert().values(id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"tinkerlab:phase13:envelope:{r['id']}")),property_measurement_id=r["id"],temperature_k=tk,temperature_status=ts,pressure_pa=float(cs["pressure_value"]) if cs and cs.get("pressure_value") is not None and str(cs.get("pressure_unit") or "").lower()=="pa" else None,humidity_percent=cs.get("humidity_percent") if cs else None,strain_rate=cs.get("strain_rate") if cs else None,frequency_hz=float(cs["frequency_value"]) if cs and cs.get("frequency_value") is not None and str(cs.get("frequency_unit") or "").lower()=="hz" else None,direction=cs.get("sample_orientation") if cs else None,material_state=cs.get("material_state") if cs else None,metadata={"migrated_from_legacy":True,"review_required":True}))

def downgrade()->None:
    op.drop_index("ix_property_validity_envelopes_v13_temperature_status",table_name="property_validity_envelopes_v13");op.drop_index("ix_property_validity_envelopes_v13_measurement",table_name="property_validity_envelopes_v13");op.drop_table("property_validity_envelopes_v13");op.drop_index("ix_property_measurements_v13_review_required",table_name="property_measurements_v13");op.drop_index("ix_property_measurements_v13_tier_status",table_name="property_measurements_v13");op.drop_index("ix_property_measurements_v13_evidence_tier",table_name="property_measurements_v13");op.drop_index("ix_property_measurement_v13_material_property",table_name="property_measurements_v13");op.drop_table("property_measurements_v13")
