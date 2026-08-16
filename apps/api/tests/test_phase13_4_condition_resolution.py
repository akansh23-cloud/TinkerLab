"""Phase 13.4 golden tests for mission-condition evidence resolution.

All property-model coefficients in this module are SYNTHETIC TEST FIXTURES. They are deliberately
not literature claims and must never be migrated into the production evidence registry.
"""
from __future__ import annotations

import pytest

from app.models.entities import Evidence, Material, MaterialPropertyDefinition
from app.models.evidence_engine import PropertyMeasurementV13, PropertyValidityEnvelopeV13
from app.models.property_models import PropertyModelV13
from app.services.condition_resolver import (
    _model_checksum_payload,
    property_model_checksum,
    resolve_and_evaluate_gate,
    resolve_property_at_conditions,
)


def _targets(db):
    material = db.query(Material).order_by(Material.id).first()
    prop = db.query(MaterialPropertyDefinition).order_by(MaterialPropertyDefinition.id).first()
    assert material is not None and prop is not None
    return material, prop


def _synthetic_model(
    db,
    *,
    material_id: str,
    property_definition_id: str,
    evidence_tier: str = "SYNTHETIC_TEST",
    t_min: float = 250.0,
    t_max: float = 600.0,
):
    model = PropertyModelV13(
        material_id=material_id,
        property_definition_id=property_definition_id,
        model_key="synthetic_temperature_power_law",
        display_name="Synthetic test-only temperature power law",
        model_type="temperature_power_law",
        equation="P(T)=P_ref*(T/T_ref)^n",
        coefficients={"p_ref": 200.0, "t_ref_k": 300.0, "n": -1.0},
        coefficient_units={"p_ref": "synthetic-unit", "t_ref_k": "K", "n": "1"},
        output_unit="synthetic-unit",
        validity_temperature_min_k=t_min,
        validity_temperature_max_k=t_max,
        validity_conditions={},
        distribution="normal",
        uncertainty_value=2.0,
        uncertainty_lower=None,
        uncertainty_upper=None,
        evidence_tier=evidence_tier,
        fit_quality={"fixture": True, "not_scientific_evidence": True},
        source_evidence_id=None,
        source_record_id=None,
        source_ref="synthetic-test://phase13.4/power-law",
        source_kind="SYNTHETIC_TEST",
        applicability_notes="CI fixture only; never production evidence",
        version=1,
        checksum="pending",
        review_required=False,
        is_active=True,
    )
    model.checksum = property_model_checksum(_model_checksum_payload(model))
    db.add(model)
    db.flush()
    return model


def test_named_model_resolves_different_values_at_300_and_525_k(db):
    material, prop = _targets(db)
    model = _synthetic_model(db, material_id=material.id, property_definition_id=prop.id)

    at_300 = resolve_property_at_conditions(
        db, material_id=material.id, property_definition_id=prop.id, conditions={"temperature_k": 300.0}
    )
    at_525 = resolve_property_at_conditions(
        db, material_id=material.id, property_definition_id=prop.id, conditions={"temperature_k": 525.0}
    )

    assert at_300.status == at_525.status == "RESOLVED"
    assert at_300.resolution_path == at_525.resolution_path == "PROPERTY_MODEL"
    assert at_300.value == pytest.approx(200.0)
    assert at_525.value == pytest.approx(200.0 * 300.0 / 525.0)
    assert at_300.value != at_525.value
    assert at_525.model_id == model.id
    assert at_525.model_checksum == model.checksum
    assert at_525.source_ref == "synthetic-test://phase13.4/power-law"


def test_unknown_temperature_measurement_cannot_clear_525_k_gate(db):
    material, prop = _targets(db)
    evidence = db.query(Evidence).order_by(Evidence.id).first()
    assert evidence is not None
    measurement = PropertyMeasurementV13(
        material_id=material.id,
        property_definition_id=prop.id,
        value_type="numeric",
        reported_numeric_value=999.0,
        reported_unit="synthetic-unit",
        canonical_numeric_value=999.0,
        canonical_unit="synthetic-unit",
        distribution="point",
        evidence_tier="MEASURED",
        tier_status="ASSESSED",
        evidence_id=evidence.id,
        review_required=False,
    )
    db.add(measurement)
    db.flush()
    db.add(PropertyValidityEnvelopeV13(
        property_measurement_id=measurement.id,
        temperature_k=None,
        temperature_status="UNKNOWN",
        metadata_json={},
    ))
    db.flush()

    result = resolve_and_evaluate_gate(
        db,
        material_id=material.id,
        property_bindings={"p": prop.id},
        conditions={"temperature_k": 525.0},
        expression="p",
        comparator=">=",
        threshold=1.0,
        blocking=True,
        samples=1000,
    )
    assert result.gate.status == "EVIDENCE_INSUFFICIENT"
    assert result.resolutions["p"].resolution_path == "EVIDENCE_INSUFFICIENT"
    assert "UNKNOWN" in result.resolutions["p"].reason


def test_outside_every_validity_range_is_evidence_insufficient(db):
    material, prop = _targets(db)
    _synthetic_model(
        db,
        material_id=material.id,
        property_definition_id=prop.id,
        t_min=280.0,
        t_max=400.0,
    )
    resolution = resolve_property_at_conditions(
        db,
        material_id=material.id,
        property_definition_id=prop.id,
        conditions={"temperature_k": 525.0},
    )
    assert resolution.status == "EVIDENCE_INSUFFICIENT"
    assert "outside model validity range" in resolution.reason


def test_predicted_only_model_still_cannot_clear_blocking_gate(db):
    material, prop = _targets(db)
    _synthetic_model(
        db,
        material_id=material.id,
        property_definition_id=prop.id,
        evidence_tier="PREDICTED",
    )
    result = resolve_and_evaluate_gate(
        db,
        material_id=material.id,
        property_bindings={"p": prop.id},
        conditions={"temperature_k": 300.0},
        expression="p",
        comparator=">=",
        threshold=100.0,
        blocking=True,
        samples=2000,
    )
    assert result.gate.probability_pass is not None
    assert result.gate.probability_pass > 0.95
    assert result.gate.status == "EVIDENCE_INSUFFICIENT"
    assert result.gate.predicted_only is True


def test_resolution_is_deterministic_and_provenance_preserving(db):
    material, prop = _targets(db)
    model = _synthetic_model(db, material_id=material.id, property_definition_id=prop.id)
    first = resolve_property_at_conditions(
        db, material_id=material.id, property_definition_id=prop.id, conditions={"temperature_k": 350.0}
    )
    second = resolve_property_at_conditions(
        db, material_id=material.id, property_definition_id=prop.id, conditions={"temperature_k": 350.0}
    )
    assert first == second
    assert first.model_id == model.id
    assert first.model_version == 1
    assert first.model_checksum == model.checksum
    assert first.requested_conditions == {"temperature_k": 350.0}
    assert first.validity == {
        "temperature_min_k": 250.0,
        "temperature_max_k": 600.0,
        "conditions": {},
    }
    assert first.source_ref == "synthetic-test://phase13.4/power-law"
    assert first.audit_dict()["resolution_path"] == "PROPERTY_MODEL"
