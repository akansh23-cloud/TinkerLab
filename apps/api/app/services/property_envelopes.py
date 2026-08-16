from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domain.evidence_engine import (
    DistributionType,
    TemperatureStatus,
    classify_legacy_evidence_tier,
)
from app.models.entities import MaterialPropertyObservation
from app.models.evidence_engine import PropertyMeasurementV13, PropertyValidityEnvelopeV13
from app.services.units import UnitError, convert


def _temperature_from_legacy(
    observation: MaterialPropertyObservation,
) -> tuple[float | None, TemperatureStatus, str]:
    cs = observation.condition_set
    if cs is not None and cs.temperature_value is not None and cs.temperature_unit:
        try:
            return (
                float(convert(float(cs.temperature_value), cs.temperature_unit, "K")),
                TemperatureStatus.KNOWN,
                "condition_set",
            )
        except UnitError:
            return None, TemperatureStatus.UNKNOWN, "condition_set_temperature_unit_not_convertible"
    conditions = observation.conditions or {}
    if isinstance(conditions.get("temperature_k"), (int, float)):
        return (
            float(conditions["temperature_k"]),
            TemperatureStatus.KNOWN,
            "legacy_conditions.temperature_k",
        )
    temperature = conditions.get("temperature")
    if (
        isinstance(temperature, dict)
        and isinstance(temperature.get("value"), (int, float))
        and temperature.get("unit")
    ):
        try:
            return (
                float(convert(float(temperature["value"]), str(temperature["unit"]), "K")),
                TemperatureStatus.KNOWN,
                "legacy_conditions.temperature",
            )
        except UnitError:
            pass
    return None, TemperatureStatus.UNKNOWN, "not_reported"


def _distribution_from_legacy(observation: MaterialPropertyObservation) -> DistributionType:
    metadata = observation.evidence.metadata_json or {}
    declared = str(metadata.get("distribution") or "").strip().lower()
    if declared in {x.value for x in DistributionType if x is not DistributionType.UNSPECIFIED}:
        return DistributionType(declared)
    uncertainty_type = str(observation.uncertainty_type or "").strip().lower()
    if (
        uncertainty_type in {"std_dev", "standard_deviation", "standard"}
        and observation.uncertainty_stddev is not None
    ):
        return DistributionType.NORMAL
    return DistributionType.UNSPECIFIED


def materialize_phase13_measurement(
    db: Session,
    observation: MaterialPropertyObservation,
    *,
    review_required: bool = True,
) -> PropertyMeasurementV13:
    """Project one legacy observation into Phase-13 custody without mutating the legacy row."""
    existing = (
        db.query(PropertyMeasurementV13)
        .filter(PropertyMeasurementV13.legacy_observation_id == observation.id)
        .one_or_none()
    )
    if existing is not None:
        return existing
    evidence = observation.evidence
    material = observation.material
    definition = observation.property_definition
    tier, tier_status, tier_reason = classify_legacy_evidence_tier(
        evidence_type=evidence.evidence_type,
        source_quality=evidence.source_quality,
        evidence_metadata=evidence.metadata_json,
        material_source_type=material.source_type,
    )
    canonical_value = None
    canonical_unit = definition.canonical_unit
    if (
        observation.value_type == "numeric"
        and observation.numeric_value is not None
        and observation.unit
        and canonical_unit
    ):
        try:
            canonical_value = float(
                convert(float(observation.numeric_value), observation.unit, canonical_unit)
            )
        except UnitError:
            canonical_value = None
    temperature_k, temperature_status, temperature_source = _temperature_from_legacy(observation)
    measurement = PropertyMeasurementV13(
        id=observation.id,
        legacy_observation_id=observation.id,
        material_id=observation.material_id,
        property_definition_id=observation.property_definition_id,
        value_type=observation.value_type,
        reported_numeric_value=observation.numeric_value,
        reported_boolean_value=observation.boolean_value,
        reported_unit=observation.unit,
        canonical_numeric_value=canonical_value,
        canonical_unit=canonical_unit,
        uncertainty_value=observation.uncertainty,
        uncertainty_type=observation.uncertainty_type,
        uncertainty_lower=observation.uncertainty_lower,
        uncertainty_upper=observation.uncertainty_upper,
        uncertainty_stddev=observation.uncertainty_stddev,
        distribution=_distribution_from_legacy(observation).value,
        evidence_tier=tier.value if tier else None,
        tier_status=tier_status.value,
        evidence_id=observation.evidence_id,
        source_record_id=observation.source_record_id,
        measurement_method=observation.method or evidence.method,
        sample_provenance={},
        source_ref=evidence.source_reference,
        review_required=review_required,
        migration_metadata={
            "source": "material_property_observations",
            "legacy_observation_id": observation.id,
            "tier_reason": tier_reason,
            "temperature_source": temperature_source,
            "temperature_not_imputed": temperature_status == TemperatureStatus.UNKNOWN,
        },
    )
    db.add(measurement)
    db.flush()
    measurement.envelope = PropertyValidityEnvelopeV13(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tinkerlab:phase13:envelope:{observation.id}")),
        property_measurement_id=measurement.id,
        temperature_k=temperature_k,
        temperature_status=temperature_status.value,
        humidity_percent=(
            getattr(observation.condition_set, "humidity_percent", None)
            if observation.condition_set
            else None
        ),
        strain_rate=(
            getattr(observation.condition_set, "strain_rate", None)
            if observation.condition_set
            else None
        ),
        direction=(
            getattr(observation.condition_set, "sample_orientation", None)
            if observation.condition_set
            else None
        ),
        material_state=(
            getattr(observation.condition_set, "material_state", None)
            if observation.condition_set
            else None
        ),
        metadata_json={"migrated_from_legacy": True, "review_required": review_required},
    )
    db.flush()
    return measurement
