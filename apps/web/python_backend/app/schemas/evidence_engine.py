from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.domain.evidence_engine import DistributionType, EvidenceTier, EvidenceTierStatus, TemperatureStatus

class PropertyValidityEnvelopeV13Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    temperature_k: float | None = None
    temperature_status: TemperatureStatus = TemperatureStatus.UNKNOWN
    pressure_pa: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    stress_state: str | None = None
    strain_rate: float | None = Field(default=None, ge=0.0)
    frequency_hz: float | None = Field(default=None, ge=0.0)
    atmosphere: str | None = None
    field_strength_v_per_m: float | None = None
    bias_condition: str | None = None
    time_under_load_s: float | None = Field(default=None, ge=0.0)
    direction: str | None = None
    material_state: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    @model_validator(mode="after")
    def temperature_contract(self):
        if self.temperature_status == TemperatureStatus.KNOWN and self.temperature_k is None:
            raise ValueError("temperature_k is required when temperature_status=KNOWN")
        if self.temperature_status != TemperatureStatus.KNOWN and self.temperature_k is not None:
            raise ValueError("temperature_k must be null unless temperature_status=KNOWN")
        return self

class PropertyMeasurementV13Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    legacy_observation_id: str | None = None
    material_id: str
    property_definition_id: str
    value_type: str
    reported_numeric_value: float | None = None
    reported_boolean_value: bool | None = None
    reported_unit: str | None = None
    canonical_numeric_value: float | None = None
    canonical_unit: str | None = None
    uncertainty_value: float | None = None
    uncertainty_type: str | None = None
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None
    uncertainty_stddev: float | None = None
    distribution: DistributionType = DistributionType.UNSPECIFIED
    evidence_tier: EvidenceTier | None = None
    tier_status: EvidenceTierStatus
    evidence_id: str
    source_record_id: str | None = None
    measurement_method: str | None = None
    sample_provenance: dict[str, Any] = Field(default_factory=dict)
    source_ref: str | None = None
    review_required: bool
    migration_metadata: dict[str, Any] = Field(default_factory=dict)
    envelope: PropertyValidityEnvelopeV13Schema | None = None
