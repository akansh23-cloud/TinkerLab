import uuid

import pytest
from pydantic import ValidationError

from app.domain.evidence_engine import (
    EvidenceTier,
    EvidenceTierStatus,
    TemperatureStatus,
    classify_legacy_evidence_tier,
    tier_can_satisfy_blocking_gate,
)
from app.models.entities import Evidence, Material, MaterialPropertyDefinition, MaterialPropertyObservation
from app.schemas.evidence_engine import PropertyValidityEnvelopeV13Schema
from app.services.property_envelopes import materialize_phase13_measurement


def test_reference_library_maps_to_handbook_without_inventing_temperature(db):
    suffix = uuid.uuid4().hex
    material = Material(
        canonical_name=f"phase13-handbook-{suffix}",
        display_name="Phase 13 handbook fixture",
        material_family="ceramic",
        source_type="reference_library",
        is_seed_data=True,
        visibility="public",
    )
    definition = MaterialPropertyDefinition(
        key=f"phase13_thermal_conductivity_{suffix}",
        display_name="Phase 13 thermal conductivity fixture",
        quantity_type="thermal_conductivity",
        canonical_unit="W/(m*K)",
        applicable_material_families=["ceramic"],
        allowed_comparators=[">="],
    )
    evidence = Evidence(
        evidence_type="literature",
        title="Phase 13 handbook fixture evidence",
        source_reference="Handbook-typical fixture; not qualification evidence.",
        source_quality="handbook_typical",
        metadata_json={"data_grade": "handbook_typical"},
    )
    db.add_all([material, definition, evidence])
    db.flush()
    observation = MaterialPropertyObservation(
        material_id=material.id,
        property_definition_id=definition.id,
        value_type="numeric",
        numeric_value=155.0,
        unit="W/(m*K)",
        conditions={},
        evidence_id=evidence.id,
        method="handbook compilation",
        status="active",
    )
    db.add(observation)
    db.flush()

    measurement = materialize_phase13_measurement(db, observation)
    assert measurement.evidence_tier == EvidenceTier.HANDBOOK.value
    assert measurement.tier_status == EvidenceTierStatus.ASSESSED.value
    assert measurement.review_required is True
    assert measurement.envelope is not None
    assert measurement.envelope.temperature_k is None
    assert measurement.envelope.temperature_status == TemperatureStatus.UNKNOWN.value
    assert measurement.migration_metadata["temperature_not_imputed"] is True
    assert measurement.distribution == "unspecified"


def test_unknown_legacy_provenance_is_not_laundered_into_handbook():
    tier, status, _ = classify_legacy_evidence_tier(
        evidence_type="user_provided",
        source_quality=None,
        evidence_metadata={},
        material_source_type="user_provided",
    )
    assert tier is None
    assert status == EvidenceTierStatus.UNASSESSED


def test_synthetic_demo_is_not_scientific_evidence():
    tier, status, _ = classify_legacy_evidence_tier(
        evidence_type="seed_demo",
        source_quality="synthetic",
        evidence_metadata={"demo_only": True},
        material_source_type="seed_demo",
    )
    assert tier is None
    assert status == EvidenceTierStatus.NOT_SCIENTIFIC_EVIDENCE


def test_predicted_tier_cannot_satisfy_blocking_gate():
    assert tier_can_satisfy_blocking_gate(EvidenceTier.PREDICTED) is False
    assert tier_can_satisfy_blocking_gate(EvidenceTier.PEER_REVIEWED) is True
    assert tier_can_satisfy_blocking_gate(None) is False


def test_known_temperature_requires_value():
    with pytest.raises(ValidationError):
        PropertyValidityEnvelopeV13Schema(temperature_status=TemperatureStatus.KNOWN)


def test_unknown_temperature_forbids_fake_value():
    with pytest.raises(ValidationError):
        PropertyValidityEnvelopeV13Schema(
            temperature_status=TemperatureStatus.UNKNOWN,
            temperature_k=298.15,
        )
