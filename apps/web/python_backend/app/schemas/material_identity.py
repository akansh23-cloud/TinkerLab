from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.material_identity import IdentityCompleteness


class MaterialIdentityV13Create(BaseModel):
    composition: dict[str, float] = Field(default_factory=dict)
    composition_basis: str = "atomic_fraction"
    phase_polytype: dict[str, Any] = Field(default_factory=dict)
    microstructure: dict[str, Any] = Field(default_factory=dict)
    processing_route: dict[str, Any] = Field(default_factory=dict)
    form_factor: dict[str, Any] = Field(default_factory=dict)
    crystallographic_orientation: dict[str, Any] = Field(default_factory=dict)
    defect_state: dict[str, Any] = Field(default_factory=dict)
    symmetry_class: str | None = None
    direction_required_for: list[str] = Field(default_factory=list)
    completeness: IdentityCompleteness = IdentityCompleteness.PARTIAL
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_ref: str | None = None

    @model_validator(mode="after")
    def validate_microstructure(self):
        if "porosity_fraction" in self.microstructure:
            porosity = self.microstructure["porosity_fraction"]
            if not isinstance(porosity, (int, float)) or not 0.0 <= float(porosity) <= 1.0:
                raise ValueError("microstructure.porosity_fraction must be between 0 and 1")
        return self


class MaterialIdentityV13Schema(MaterialIdentityV13Create):
    model_config = ConfigDict(from_attributes=True)
    id: str
    material_id: str
    composition_fingerprint: str | None = None
    identity_fingerprint: str | None = None
    review_required: bool
    migration_metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityConflictSchema(BaseModel):
    left_material_id: str
    right_material_id: str
    composition_fingerprint: str
    differing_dimensions: list[str]
    severity: str
