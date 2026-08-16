from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.entities import JSONType, Material, now_utc, uuid_str


class MaterialIdentityV13(Base):
    """Engineering identity for a material record.

    Chemical composition is deliberately not unique. Two materials can share composition while
    differing in phase, microstructure, processing, form factor, orientation or defect population.
    Those differences are decision-relevant and therefore part of identity custody.
    """

    __tablename__ = "material_identities_v13"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(
        ForeignKey("materials.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    composition: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict)
    composition_basis: Mapped[str] = mapped_column(String(40), default="atomic_fraction", nullable=False)
    composition_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    phase_polytype: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    microstructure: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    processing_route: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    form_factor: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    crystallographic_orientation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    defect_state: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    symmetry_class: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    direction_required_for: Mapped[list[str]] = mapped_column(JSONType, default=list)
    identity_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    completeness: Mapped[str] = mapped_column(String(30), default="LEGACY_UNKNOWN", nullable=False, index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    material: Mapped[Material] = relationship()

    __table_args__ = (
        Index("ix_material_identity_v13_composition_material", "composition_fingerprint", "material_id"),
    )
