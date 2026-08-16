from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.entities import JSONType, now_utc, uuid_str

class PropertyMeasurementV13(Base):
    __tablename__ = "property_measurements_v13"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    legacy_observation_id: Mapped[str | None] = mapped_column(ForeignKey("material_property_observations.id", ondelete="SET NULL"), nullable=True, unique=True, index=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    reported_numeric_value: Mapped[float | None] = mapped_column(Float); reported_boolean_value: Mapped[bool | None] = mapped_column(Boolean); reported_unit: Mapped[str | None] = mapped_column(String(80))
    canonical_numeric_value: Mapped[float | None] = mapped_column(Float); canonical_unit: Mapped[str | None] = mapped_column(String(80))
    uncertainty_value: Mapped[float | None] = mapped_column(Float); uncertainty_type: Mapped[str | None] = mapped_column(String(40)); uncertainty_lower: Mapped[float | None] = mapped_column(Float); uncertainty_upper: Mapped[float | None] = mapped_column(Float); uncertainty_stddev: Mapped[float | None] = mapped_column(Float)
    distribution: Mapped[str] = mapped_column(String(30), default="unspecified", nullable=False)
    evidence_tier: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True); tier_status: Mapped[str] = mapped_column(String(40), default="UNASSESSED", nullable=False, index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True); source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True, index=True)
    measurement_method: Mapped[str | None] = mapped_column(Text); sample_provenance: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict); source_ref: Mapped[str | None] = mapped_column(Text)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True); migration_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc); updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    envelope: Mapped["PropertyValidityEnvelopeV13 | None"] = relationship(back_populates="measurement", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (Index("ix_property_measurement_v13_material_property", "material_id", "property_definition_id"),)

class PropertyValidityEnvelopeV13(Base):
    __tablename__ = "property_validity_envelopes_v13"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    property_measurement_id: Mapped[str] = mapped_column(ForeignKey("property_measurements_v13.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    temperature_k: Mapped[float | None] = mapped_column(Float); temperature_status: Mapped[str] = mapped_column(String(30), default="UNKNOWN", nullable=False, index=True)
    pressure_pa: Mapped[float | None] = mapped_column(Float); humidity_percent: Mapped[float | None] = mapped_column(Float); stress_state: Mapped[str | None] = mapped_column(String(80)); strain_rate: Mapped[float | None] = mapped_column(Float); frequency_hz: Mapped[float | None] = mapped_column(Float); atmosphere: Mapped[str | None] = mapped_column(String(160)); field_strength_v_per_m: Mapped[float | None] = mapped_column(Float); bias_condition: Mapped[str | None] = mapped_column(Text); time_under_load_s: Mapped[float | None] = mapped_column(Float); direction: Mapped[str | None] = mapped_column(String(160)); material_state: Mapped[str | None] = mapped_column(String(200))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    measurement: Mapped[PropertyMeasurementV13] = relationship(back_populates="envelope")
