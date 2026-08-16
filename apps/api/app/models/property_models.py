from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.entities import JSONType, now_utc, uuid_str


class PropertyModelV13(Base):
    """Versioned, provenance-bound model for resolving a property at mission conditions.

    A model is evidence only inside its declared validity envelope. Coefficients are stored exactly
    as supplied by the cited source; this table never manufactures fit parameters or extrapolates.
    The checksum is immutable content identity used by strict decision traces.
    """

    __tablename__ = "property_models_v13"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, index=True)
    property_definition_id: Mapped[str] = mapped_column(
        ForeignKey("material_property_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    model_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    equation: Mapped[str] = mapped_column(Text, nullable=False)
    coefficients: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    coefficient_units: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    output_unit: Mapped[str | None] = mapped_column(String(100))
    validity_temperature_min_k: Mapped[float | None] = mapped_column(Float)
    validity_temperature_max_k: Mapped[float | None] = mapped_column(Float)
    validity_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    distribution: Mapped[str] = mapped_column(String(30), default="unspecified", nullable=False)
    uncertainty_value: Mapped[float | None] = mapped_column(Float)
    uncertainty_lower: Mapped[float | None] = mapped_column(Float)
    uncertainty_upper: Mapped[float | None] = mapped_column(Float)
    evidence_tier: Mapped[str | None] = mapped_column(String(40), index=True)
    fit_quality: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    source_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"), index=True)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id", ondelete="SET NULL"), index=True)
    source_ref: Mapped[str | None] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(40), default="UNSPECIFIED", nullable=False)
    applicability_notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("material_id", "property_definition_id", "model_key", "version", name="uq_property_model_v13_version"),
        Index("ix_property_model_v13_material_property", "material_id", "property_definition_id"),
    )
