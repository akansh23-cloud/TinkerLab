"""Phase 9.1-B regressions for experimental admission and requirement-level validation."""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.db.seed import sid
from app.domain.enums import MeasurementQuality, ValidationState
from app.models.entities import (
    ExperimentProtocolVersion,
    ExperimentRun,
    FunctionalRequirement,
    Instrument,
    MaterialPropertyDefinition,
    Measurement,
    Sample,
)
from app.services.experiments_lab import (
    ExperimentError,
    _validation_state,
    accepted_measurements,
    create_plan,
    detect_conflicting_experiments,
    evaluate_experimental_requirement,
    record_measurement,
    transition_run,
)

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
ROLE_ID = sid("phase8:role:switching-material")
SILICON_ID = sid("material:silicon")
DEMO_ID = sid("material:demo-wide-gap-synthetic")
SAMPLE_ID = sid("phase9:sample:demo-wide-gap-001")
VERSION_ID = sid("phase9:protocol-version:thermal-conductivity:1.0")
INSTRUMENT_ID = sid("phase9:instrument:demo-thermal-bench")
THERMAL_REQ_ID = sid("phase8:requirement:min_thermal_conductivity")
MEASURED_AT = datetime(2025, 6, 20, 10, 0, tzinfo=UTC)


def _definition(db, key="thermal_conductivity"):
    return db.query(MaterialPropertyDefinition).filter_by(key=key).one()


def _run(db, *, status="completed", instrument_id=INSTRUMENT_ID, sample_id=SAMPLE_ID, code="P91B"):
    version = db.get(ExperimentProtocolVersion, VERSION_ID)
    row = ExperimentRun(
        organisation_id=ORG_ID,
        protocol_version_id=version.id,
        protocol_checksum_at_run=version.protocol_checksum,
        run_code=f"{code}-{sid(code)[:8]}",
        sample_id=sample_id,
        instrument_id=instrument_id,
        status=status,
        started_at=MEASURED_AT if status in {"running", "completed"} else None,
        completed_at=MEASURED_AT if status == "completed" else None,
        conditions={"temperature_k": 300.0, "atmosphere": "air"},
    )
    db.add(row)
    db.flush()
    return row


def test_planned_run_cannot_produce_accepted_measurement(db):
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=_run(db, status="planned", code="planned"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality != MeasurementQuality.ACCEPTED
    assert "RUN_NOT_COMPLETED" in measurement.admissibility_codes
    db.rollback()


def test_running_run_measurement_is_provisional(db):
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=_run(db, status="running", code="running"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.PROVISIONAL
    assert "RUN_IN_PROGRESS" in measurement.admissibility_codes
    db.rollback()


def test_completed_valid_run_can_produce_accepted_measurement(db):
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=_run(db, status="completed", code="complete"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)",
        conditions={"temperature_k": 300.0, "atmosphere": "air"}, measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.ACCEPTED
    assert measurement.admissibility_codes == []
    db.rollback()


def test_protocol_or_instrument_cannot_accept_unsupported_property(db):
    density = _definition(db, "density")
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=_run(db, status="completed", code="wrong-property"),
        property_definition=density, numeric_value=1000, unit="kg/m^3", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.REJECTED
    assert "PROTOCOL_PROPERTY_MISMATCH" in measurement.admissibility_codes
    assert "INSTRUMENT_PROPERTY_MISMATCH" in measurement.admissibility_codes
    db.rollback()


def test_expired_calibration_prevents_accepted_measurement(db):
    instrument = Instrument(
        organisation_id=ORG_ID, key="expired-thermal", display_name="Expired thermal bench",
        instrument_type="thermal_conductivity_bench", measures_property_keys=["thermal_conductivity"],
        calibration_status="calibrated", calibration_date=date(2024, 1, 1),
        calibration_due_date=date(2024, 12, 31), calibration_reference="CAL-OLD",
    )
    db.add(instrument); db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID,
        run=_run(db, status="completed", instrument_id=instrument.id, code="expired"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality != MeasurementQuality.ACCEPTED
    assert "CALIBRATION_EXPIRED" in measurement.admissibility_codes
    db.rollback()


def test_incompatible_measurement_unit_is_not_accepted(db):
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=_run(db, status="completed", code="badunit"),
        property_definition=_definition(db), numeric_value=7, unit="eV", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.INCOMPLETE_PROVENANCE
    assert "UNIT_DIMENSION_MISMATCH" in measurement.admissibility_codes
    db.rollback()


def test_invalidated_run_measurements_remain_but_stop_governing(db):
    definition = _definition(db)
    run = db.query(ExperimentRun).filter_by(sample_id=SAMPLE_ID, status="completed", is_control=False).first()
    admitted_before = accepted_measurements(
        db, target_kind="known_material", target_id=DEMO_ID,
        property_definition_id=definition.id, organisation_id=ORG_ID,
    )
    ids_before = {m.id for m in admitted_before if m.run_id == run.id}
    assert ids_before

    transition_run(db, run, "invalidated", reason="Fixture instrument fault discovered after the run")
    db.flush()
    admitted_after = accepted_measurements(
        db, target_kind="known_material", target_id=DEMO_ID,
        property_definition_id=definition.id, organisation_id=ORG_ID,
    )
    assert not (ids_before & {m.id for m in admitted_after})
    retained = db.query(Measurement).filter(Measurement.id.in_(ids_before)).all()
    assert retained and all(m.quality == MeasurementQuality.INVALIDATED_SOURCE for m in retained)
    db.rollback()


def test_requirement_outcome_supports_contradicts_and_handles_uncertainty(db):
    requirement = db.get(FunctionalRequirement, THERMAL_REQ_ID)
    base = dict(
        organisation_id=ORG_ID, run_id="r", property_definition_id=requirement.property_definition_id,
        numeric_value=0, unit="W/(m*K)", canonical_unit="W/(m*K)", scientific_origin="experimental",
        measurement_checksum="x" * 64,
    )
    passing = Measurement(**base, canonical_value=120.0, uncertainty=5.0)
    failing = Measurement(**base, canonical_value=40.0, uncertainty=2.0)
    crossing = Measurement(**base, canonical_value=105.0, uncertainty=10.0)
    assert evaluate_experimental_requirement(requirement, passing)["outcome"] == "EXPERIMENT_SUPPORTS_REQUIREMENT"
    assert evaluate_experimental_requirement(requirement, failing)["outcome"] == "EXPERIMENT_CONTRADICTS_REQUIREMENT"
    assert evaluate_experimental_requirement(requirement, crossing)["outcome"] == "EXPERIMENT_INCONCLUSIVE"


def test_different_temperature_experiments_are_not_false_conflicts(db):
    definition = _definition(db)
    first = Measurement(
        id="m1", organisation_id=ORG_ID, run_id="r1", sample_id=SAMPLE_ID,
        property_definition_id=definition.id, canonical_value=40.0, canonical_unit="W/(m*K)",
        numeric_value=40.0, unit="W/(m*K)", uncertainty=1.0, conditions={"temperature_k": 300.0},
        quality="accepted", scientific_origin="experimental", measurement_checksum="a" * 64,
    )
    second = Measurement(
        id="m2", organisation_id=ORG_ID, run_id="r2", sample_id=SAMPLE_ID,
        property_definition_id=definition.id, canonical_value=100.0, canonical_unit="W/(m*K)",
        numeric_value=100.0, unit="W/(m*K)", uncertainty=1.0, conditions={"temperature_k": 900.0},
        quality="accepted", scientific_origin="experimental", measurement_checksum="b" * 64,
    )
    assert detect_conflicting_experiments([first, second], db=db) == []


def test_protocol_replicate_and_control_requirements_are_enforced(db):
    version = db.get(ExperimentProtocolVersion, VERSION_ID)
    with pytest.raises(ExperimentError, match="PROTOCOL_REPLICATE_REQUIREMENT"):
        create_plan(
            db, organisation_id=ORG_ID, display_name="Too few reps", objective="A sufficiently long objective",
            design_kind="single_run", protocol_version=version, factors=[], replicate_count=1,
            control_plan="Reference control", role_id=ROLE_ID,
        )
    with pytest.raises(ExperimentError, match="PROTOCOL_CONTROL_REQUIRED"):
        create_plan(
            db, organisation_id=ORG_ID, display_name="Missing control", objective="A sufficiently long objective",
            design_kind="single_run", protocol_version=version, factors=[], replicate_count=2,
            control_plan=None, role_id=ROLE_ID,
        )
    db.rollback()


def test_candidate_state_machine_does_not_turn_failed_experiment_into_support():
    state, _ = _validation_state(
        reasoning={"origin_breakdown": {"experimental": 1}},
        requirement_outcomes=[{"outcome": "EXPERIMENT_CONTRADICTS_REQUIREMENT", "requirement_kind": "hard_constraint"}],
        experimentally_supported=[], experimentally_contradicted=["req"], outstanding=[], conflicts=[],
        has_plan=False, has_pending_run=False, has_active_run=False,
    )
    assert state == ValidationState.EXPERIMENTALLY_CONTRADICTED


def test_private_experimental_evidence_never_crosses_tenants(db):
    definition = _definition(db)
    assert accepted_measurements(
        db, target_kind="known_material", target_id=DEMO_ID,
        property_definition_id=definition.id, organisation_id=OTHER_ORG,
    ) == []


def test_pending_and_in_progress_states_are_reachable():
    pending, _ = _validation_state(
        reasoning={"origin_breakdown": {"simulated": 1}}, requirement_outcomes=[],
        experimentally_supported=[], experimentally_contradicted=[], outstanding=["r"], conflicts=[],
        has_plan=True, has_pending_run=True, has_active_run=False,
    )
    active, _ = _validation_state(
        reasoning={"origin_breakdown": {"simulated": 1}}, requirement_outcomes=[],
        experimentally_supported=[], experimentally_contradicted=[], outstanding=["r"], conflicts=[],
        has_plan=True, has_pending_run=False, has_active_run=True,
    )
    assert pending == ValidationState.EXPERIMENT_PENDING
    assert active == ValidationState.EXPERIMENT_IN_PROGRESS


def test_all_required_experimental_gates_can_reach_supported_state():
    state, _ = _validation_state(
        reasoning={"origin_breakdown": {"experimental": 2}},
        requirement_outcomes=[
            {"outcome": "EXPERIMENT_SUPPORTS_REQUIREMENT", "requirement_kind": "hard_constraint"},
            {"outcome": "EXPERIMENT_SUPPORTS_REQUIREMENT", "requirement_kind": "soft_constraint"},
        ],
        experimentally_supported=["r1", "r2"], experimentally_contradicted=[],
        outstanding=[], conflicts=[], has_plan=False, has_pending_run=False, has_active_run=False,
    )
    assert state == ValidationState.EXPERIMENTALLY_SUPPORTED


def test_sample_candidate_target_mismatch_is_rejected_by_api(client):
    response = client.post("/experiments/samples", headers={"X-Organisation-ID": ORG_ID}, json={
        "sample_code": "P91B-MISMATCH",
        "sample_kind": "procured",
        "target_kind": "known_material",
        "target_id": SILICON_ID,
        "candidate_id": sid("candidate:0"),
    })
    assert response.status_code == 422
    assert "CANDIDATE_TARGET_MISMATCH" in response.text


def test_replacement_decision_is_candidate_centric_and_not_a_commercial_approval(client):
    response = client.post("/experiments/replacement-decision", headers={"X-Organisation-ID": ORG_ID}, json={
        "role_id": ROLE_ID,
        "candidate_id": sid("candidate:0"),
        "persist_validation": False,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_id"] == sid("candidate:0")
    assert body["project_id"] == sid("project")
    assert body["target_kind"] == "known_material"
    assert body["decision"] in {"READY_FOR_NEXT_GATE", "NOT_READY", "REJECTED", "INCONCLUSIVE"}
    assert body["methodology_version"] == "replacement-next-gate-v1"
    assert "commercial" in body["qualification_note"].lower()
    assert body["industrial_status"] == "not_assessed"
    assert "INDUSTRIAL_ASSESSMENT_MISSING" in body["reason_codes"]


def test_candidate_plan_and_run_listing_are_candidate_scoped(client):
    candidate_id = sid("candidate:0")
    plans = client.get(
        f"/experiments/plans?candidate_id={candidate_id}",
        headers={"X-Organisation-ID": ORG_ID},
    )
    assert plans.status_code == 200
    assert all(row.get("candidate_id") == candidate_id for row in plans.json())
    runs = client.get(
        f"/experiments/runs?candidate_id={candidate_id}",
        headers={"X-Organisation-ID": ORG_ID},
    )
    assert runs.status_code == 200


def test_missing_protocol_controlled_condition_prevents_acceptance(db):
    run = _run(db, status="completed", code="missing-condition")
    run.conditions = {"temperature_k": 300.0}
    db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run,
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)",
        measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.PROVISIONAL
    assert "PROTOCOL_CONDITION_MISSING" in measurement.admissibility_codes
    db.rollback()


def test_protocol_required_equipment_must_be_declared_by_instrument(db):
    instrument = Instrument(
        organisation_id=ORG_ID, key="thermal-no-aux-equipment", display_name="Thermal bench without declared auxiliaries",
        instrument_type="thermal_conductivity_bench", measures_property_keys=["thermal_conductivity"],
        equipment_capabilities=[], calibration_status="calibrated", calibration_date=date(2025, 1, 1),
        calibration_due_date=date(2025, 12, 31), calibration_reference="CAL-NO-EQUIPMENT",
    )
    db.add(instrument); db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID,
        run=_run(db, status="completed", instrument_id=instrument.id, code="missing-equipment"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.PROVISIONAL
    assert "REQUIRED_EQUIPMENT_UNVERIFIED" in measurement.admissibility_codes
    db.rollback()


def test_protocol_sample_requirements_are_executable(db):
    sample = db.get(Sample, SAMPLE_ID)
    assert sample is not None
    sample.geometry = "bar"
    db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID,
        run=_run(db, status="completed", sample_id=sample.id, code="bad-sample-geometry"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.REJECTED
    assert "SAMPLE_REQUIREMENT_MISMATCH" in measurement.admissibility_codes
    db.rollback()


def test_protocol_calibration_age_is_enforced_even_when_due_date_is_future(db):
    instrument = Instrument(
        organisation_id=ORG_ID, key="stale-by-protocol", display_name="Calibrated but stale by protocol",
        instrument_type="thermal_conductivity_bench", measures_property_keys=["thermal_conductivity"],
        equipment_capabilities=["thermal conductivity bench", "calibrated thermocouples"],
        calibration_status="calibrated", calibration_date=date(2024, 1, 1),
        calibration_due_date=date(2026, 12, 31), calibration_reference="CAL-STALE-PROTOCOL",
    )
    db.add(instrument); db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID,
        run=_run(db, status="completed", instrument_id=instrument.id, code="protocol-cal-age"),
        property_definition=_definition(db), numeric_value=120, unit="W/(m*K)", measured_at=MEASURED_AT,
    )
    assert measurement.quality == MeasurementQuality.PROVISIONAL
    assert "CALIBRATION_EXPIRED_BY_PROTOCOL" in measurement.admissibility_codes
    db.rollback()
