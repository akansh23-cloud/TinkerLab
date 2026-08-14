"""Phase-9 tests: protocols, samples, measurements, comparison and validation states.

The invariants: protocol history is immutable, every measurement traces to a sample, an experiment
never overwrites a prediction or a simulation, contradictory experiments are both kept, and
"validated" is never claimed when only simulation exists.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.db.seed import sid
from app.domain.enums import AgreementVerdict, MeasurementQuality, ValidationState
from app.models.entities import (
    ExperimentProtocol,
    ExperimentProtocolVersion,
    ExperimentRun,
    Instrument,
    MaterialPropertyDefinition,
    Measurement,
    PropertyPrediction,
    Sample,
    SimulationResult,
    ValidationAssessment,
)
from app.services.experiments_lab import (
    ComparableValue,
    ExperimentError,
    accepted_measurements,
    assess_sample_provenance,
    assess_validation,
    compare_values,
    create_protocol_version,
    create_sample,
    detect_conflicting_experiments,
    expand_design,
    recommend_experiments,
    record_measurement,
    sample_lineage,
)

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
PROJECT_ID = sid("project")
ROLE_ID = sid("phase8:role:switching-material")
SILICON_ID = sid("material:silicon")
DEMO_CANDIDATE_ID = sid("material:demo-wide-gap-synthetic")
SAMPLE_ID = sid("phase9:sample:demo-wide-gap-001")
ORPHAN_SAMPLE_ID = sid("phase9:sample:orphan")
PROTOCOL_ID = sid("phase9:protocol:thermal-conductivity")
PROTOCOL_VERSION_ID = sid("phase9:protocol-version:thermal-conductivity:1.0")
INSTRUMENT_ID = sid("phase9:instrument:demo-thermal-bench")
HEADERS = {"X-Organisation-ID": ORG_ID}
HOSTILE_HEADERS = {"X-Organisation-ID": OTHER_ORG}


# --- protocol versioning ------------------------------------------------------------------------
def test_protocol_version_cannot_be_overwritten(db):
    protocol = db.get(ExperimentProtocol, PROTOCOL_ID)
    with pytest.raises(ExperimentError, match="frozen"):
        create_protocol_version(db, protocol=protocol, version="1.0", values={
            "objective": "an attempted silent edit of a published protocol",
            "measurement_procedure": [{"step": 1, "description": "x"}],
        })
    db.rollback()


def test_new_protocol_version_supersedes_without_rewriting(db):
    protocol = db.get(ExperimentProtocol, PROTOCOL_ID)
    original = db.get(ExperimentProtocolVersion, PROTOCOL_VERSION_ID)
    original_checksum = original.protocol_checksum
    original_objective = original.objective

    updated = create_protocol_version(db, protocol=protocol, version="2.0", values={
        "objective": "Revised objective with a tighter steady-state criterion.",
        "measurement_procedure": [{"step": 1, "description": "Revised procedure."}],
        "acceptance_criteria": {"steady_state_drift_max_k_per_min": 0.01},
        "replicate_requirement": 3,
    })
    db.flush()
    db.expire_all()

    historical = db.get(ExperimentProtocolVersion, PROTOCOL_VERSION_ID)
    assert historical.protocol_checksum == original_checksum, "history must not be rewritten"
    assert historical.objective == original_objective
    assert historical.superseded_by_id == updated.id
    assert updated.protocol_checksum != original_checksum
    db.rollback()


def test_run_pins_the_protocol_checksum_it_used(db):
    runs = db.query(ExperimentRun).filter(ExperimentRun.protocol_version_id == PROTOCOL_VERSION_ID).all()
    version = db.get(ExperimentProtocolVersion, PROTOCOL_VERSION_ID)
    assert runs
    for run in runs:
        assert run.protocol_checksum_at_run == version.protocol_checksum


def test_protocol_version_requires_a_measurement_procedure(db):
    protocol = db.get(ExperimentProtocol, PROTOCOL_ID)
    with pytest.raises(ExperimentError, match="measurement procedure"):
        create_protocol_version(db, protocol=protocol, version="9.9", values={
            "objective": "a protocol that never says how to measure anything",
            "measurement_procedure": [],
        })
    db.rollback()


# --- sample provenance --------------------------------------------------------------------------
def test_sample_provenance_gaps_are_recorded_not_ignored():
    complete, gaps = assess_sample_provenance({"material_id": SILICON_ID})
    assert complete is False
    assert any("material state" in g for g in gaps)
    assert any("preparation date" in g for g in gaps)
    full, no_gaps = assess_sample_provenance({
        "material_id": SILICON_ID, "material_state_id": "s1",
        "preparation_date": date(2025, 1, 1), "batch_reference": "B1",
    })
    assert full is True and no_gaps == []


def test_seeded_sample_provenance_states_are_correct(db):
    good = db.get(Sample, SAMPLE_ID)
    orphan = db.get(Sample, ORPHAN_SAMPLE_ID)
    assert good.provenance_complete is True and good.provenance_gaps == []
    assert orphan.provenance_complete is False and orphan.provenance_gaps


def test_measurement_from_an_untraceable_sample_is_not_admitted(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    run = ExperimentRun(
        organisation_id=ORG_ID, protocol_version_id=PROTOCOL_VERSION_ID,
        protocol_checksum_at_run="x" * 64, run_code="ORPHAN-RUN-001",
        sample_id=ORPHAN_SAMPLE_ID, instrument_id=INSTRUMENT_ID, status="completed",
    )
    db.add(run)
    db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=999.0, unit="W/(m*K)", uncertainty=1.0,
    )
    assert measurement.quality != MeasurementQuality.ACCEPTED
    assert any("provenance is incomplete" in r for r in measurement.quality_reasons)
    # And it must not appear as evidence.
    admitted = accepted_measurements(
        db, target_kind="known_material", target_id=DEMO_CANDIDATE_ID,
        property_definition_id=definition.id, organisation_id=ORG_ID)
    assert measurement.id not in {m.id for m in admitted}
    db.rollback()


def test_measurement_with_no_sample_is_not_admitted(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    run = ExperimentRun(
        organisation_id=ORG_ID, protocol_version_id=PROTOCOL_VERSION_ID,
        protocol_checksum_at_run="x" * 64, run_code="NOSAMPLE-001",
        sample_id=None, instrument_id=INSTRUMENT_ID, status="completed",
    )
    db.add(run)
    db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=50.0, unit="W/(m*K)")
    assert measurement.quality == MeasurementQuality.INCOMPLETE_PROVENANCE
    assert any("not traceable to a specimen" in r for r in measurement.quality_reasons)
    db.rollback()


def test_uncalibrated_instrument_downgrades_a_measurement(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    instrument = Instrument(
        organisation_id=ORG_ID, key="uncalibrated_bench", display_name="Uncalibrated bench",
        instrument_type="thermal_conductivity_bench", calibration_status="overdue",
    )
    db.add(instrument)
    db.flush()
    run = ExperimentRun(
        organisation_id=ORG_ID, protocol_version_id=PROTOCOL_VERSION_ID,
        protocol_checksum_at_run="x" * 64, run_code="UNCAL-001",
        sample_id=SAMPLE_ID, instrument_id=instrument.id, status="completed",
    )
    db.add(run)
    db.flush()
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=40.0, unit="W/(m*K)")
    assert measurement.quality == MeasurementQuality.PROVISIONAL
    assert any("calibration status" in r for r in measurement.quality_reasons)
    db.rollback()


def test_unconvertible_unit_yields_no_canonical_value(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    run = db.query(ExperimentRun).filter_by(sample_id=SAMPLE_ID).first()
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=7.0, unit="furlongs_per_fortnight")
    assert measurement.canonical_value is None
    assert measurement.quality == MeasurementQuality.INCOMPLETE_PROVENANCE
    assert any("never reinterpreted" in r for r in measurement.quality_reasons)
    db.rollback()


def test_sample_lineage_is_traceable_and_bounded(db):
    child = create_sample(db, {
        "organisation_id": ORG_ID, "sample_code": "DEMO-WG-001-A", "sample_kind": "subdivided",
        "material_id": DEMO_CANDIDATE_ID, "material_state_id": sid("phase8:state:demo-wide-gap-300k"),
        "parent_sample_id": SAMPLE_ID, "preparation_date": date(2025, 6, 20),
    })
    db.flush()
    lineage = sample_lineage(db, child.id)
    assert [entry["sample_id"] for entry in lineage] == [child.id, SAMPLE_ID]
    db.rollback()


# --- design of experiments ------------------------------------------------------------------------
def test_full_factorial_expands_correctly():
    runs = expand_design("full_factorial", [
        {"name": "temperature_k", "levels": [300, 400]},
        {"name": "atmosphere", "levels": ["air", "argon"]},
    ], replicate_count=2)
    assert len(runs) == 8  # 2 x 2 levels x 2 replicates
    assert all(set(r["factor_levels"]) == {"temperature_k", "atmosphere"} for r in runs)


def test_one_factor_and_sweep_require_exactly_one_factor():
    for kind in ("one_factor", "parameter_sweep"):
        with pytest.raises(ExperimentError, match="exactly one factor"):
            expand_design(kind, [{"name": "a", "levels": [1]}, {"name": "b", "levels": [2]}], 1)


def test_unimplemented_designs_are_refused_rather_than_faked():
    """Naming a design without its mathematics would misrepresent what the software does."""
    for kind in ("response_surface", "bayesian_optimization", "active_learning"):
        with pytest.raises(ExperimentError, match="not implemented"):
            expand_design(kind, [{"name": "a", "levels": [1, 2]}], 1)


def test_design_expansion_is_bounded():
    with pytest.raises(ExperimentError, match="above the bound"):
        expand_design("full_factorial", [
            {"name": "a", "levels": list(range(20))},
            {"name": "b", "levels": list(range(20))},
        ], replicate_count=1)


# --- comparison across origins --------------------------------------------------------------------
def test_overlapping_intervals_agree_without_being_merged():
    result = compare_values(
        ComparableValue("experimental", 100.0, 5.0, "W/(m*K)", "m1"),
        ComparableValue("simulated", 103.0, 4.0, "W/(m*K)", "s1"),
    )
    assert result["verdict"] == AgreementVerdict.AGREES_WITHIN_UNCERTAINTY
    assert "not combined into one number" in result["detail"]
    assert "first" in result and "second" in result


def test_disagreement_is_exposed_not_averaged():
    result = compare_values(
        ComparableValue("experimental", 101.0, 4.0, "W/(m*K)", "m1"),
        ComparableValue("predicted", 120.0, 15.0, "W/(m*K)", "p1"),
    )
    # 101±4 = [97,105]; 120±15 = [105,135] — these touch, so they agree.
    assert result["verdict"] == AgreementVerdict.AGREES_WITHIN_UNCERTAINTY
    far = compare_values(
        ComparableValue("experimental", 12.0, 1.0, "W/(m*K)", "m1"),
        ComparableValue("simulated", 128.0, 8.0, "W/(m*K)", "s1"),
    )
    assert far["verdict"] == AgreementVerdict.DISAGREES
    assert "no average is taken" in far["detail"]
    assert far["absolute_difference"] == pytest.approx(116.0)


def test_different_units_are_incomparable_not_converted():
    result = compare_values(
        ComparableValue("experimental", 1.0, None, "W/(m*K)", "m1"),
        ComparableValue("predicted", 1.0, None, "eV", "p1"),
    )
    assert result["verdict"] == AgreementVerdict.INCOMPARABLE
    assert "not converted here" in result["detail"]


def test_conflicting_experiments_are_both_retained(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    run = db.query(ExperimentRun).filter_by(sample_id=SAMPLE_ID).first()
    # The seed already holds 41±2 and 43±2. A 5±1 measurement contradicts both.
    outlier = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=5.0, unit="W/(m*K)", uncertainty=1.0,
        method="Second synthetic method producing a contradictory value")
    db.flush()
    measurements = accepted_measurements(
        db, target_kind="known_material", target_id=DEMO_CANDIDATE_ID,
        property_definition_id=definition.id, organisation_id=ORG_ID)
    conflicts = detect_conflicting_experiments(measurements)
    assert conflicts, "non-overlapping accepted measurements must be reported as conflicting"
    assert outlier.id in {mid for c in conflicts for mid in c["measurement_ids"]}
    assert all("does not automatically supersede" in c["detail"] for c in conflicts)
    # Both records still exist: neither was deleted.
    assert db.query(Measurement).filter_by(id=outlier.id).one_or_none() is not None
    db.rollback()


# --- validation state -------------------------------------------------------------------------------
def test_simulation_alone_is_never_called_validated(db):
    """The single most important Phase-9 wording invariant."""
    result = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=SILICON_ID)
    assert result["validation_state"] != ValidationState.EXPERIMENTALLY_SUPPORTED
    assert result["validation_state"] != ValidationState.PARTIALLY_VALIDATED
    assert result["validation_state"] in {
        ValidationState.COMPUTATIONAL_ONLY, ValidationState.SIMULATION_SUPPORTED}


def test_measurements_that_fail_a_requirement_are_experimentally_contradictory(db):
    result = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    assert result["validation_state"] == ValidationState.EXPERIMENTALLY_CONTRADICTED
    assert sid("phase8:requirement:min_thermal_conductivity") in result["experimentally_contradicted_requirements"]
    assert sid("phase8:requirement:min_thermal_conductivity") not in result["experimentally_supported_requirements"]


def test_experiment_disagreement_with_prior_value_is_surfaced(db):
    result = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    assert result["disagreements"], "a measurement contradicting a prior value must be exposed"
    disagreement = result["disagreements"][0]
    assert disagreement["verdict"] == AgreementVerdict.DISAGREES
    assert "no average is taken" in disagreement["detail"]
    assert "does not overwrite" in result["separation_note"]


def test_conflicting_measurements_make_the_state_inconclusive(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    run = db.query(ExperimentRun).filter_by(sample_id=SAMPLE_ID).first()
    record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=5.0, unit="W/(m*K)", uncertainty=1.0, method="contradictory synthetic method")
    db.flush()
    result = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    assert result["validation_state"] == ValidationState.CONFLICTING_EXPERIMENTS
    assert "no automatic winner" in result["rationale"]
    db.rollback()


def test_experiment_never_overwrites_prediction_or_simulation(db):
    predictions = db.query(PropertyPrediction).count()
    simulations = db.query(SimulationResult).count()
    assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    assert db.query(PropertyPrediction).count() == predictions
    assert db.query(SimulationResult).count() == simulations


def test_validation_assessment_supersedes_without_rewriting(db):
    first = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    first_id = first["validation_assessment_id"]
    original_state = db.get(ValidationAssessment, first_id).validation_state

    second = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    db.expire_all()
    historical = db.get(ValidationAssessment, first_id)
    assert historical.validation_state == original_state
    assert historical.superseded_by_id == second["validation_assessment_id"]


def test_validation_is_deterministic(db):
    first = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    second = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    assert first["assessment_checksum"] == second["assessment_checksum"]


# --- recommendations --------------------------------------------------------------------------------
def test_recommendations_are_prioritized_and_explained(db):
    result = recommend_experiments(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    assert result["recommendations"]
    scores = [r["priority_score"] for r in result["recommendations"]]
    assert scores == sorted(scores, reverse=True)
    for recommendation in result["recommendations"]:
        assert recommendation["why_it_matters"]
        assert recommendation["proposed_measurement"]
        assert recommendation["priority_factors"]
        assert recommendation["current_evidence_summary"] is not None


def test_priority_is_not_called_expected_value_of_information(db):
    """Naming it EVI would claim mathematics this system does not implement."""
    result = recommend_experiments(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    assert result["methodology"] == "explainable_weighted_factors_v1"
    # The phrase may appear only inside the disclaimer that denies it, never as a label.
    for recommendation in result["recommendations"]:
        assert recommendation["priority_methodology"] == "explainable_weighted_factors_v1"
        assert "not called expected value of information" in recommendation["priority_note"]
        without_disclaimer = {k: v for k, v in recommendation.items() if k != "priority_note"}
        blob = str(without_disclaimer).lower()
        assert "expected value of information" not in blob
        assert "evsi" not in blob
        assert "value of information" not in blob
    # Weights are inspectable rather than hidden inside the score.
    assert set(result["weights"]) == {
        "requirement_criticality", "evidence_gap", "requirement_hardness", "uncertainty"}


def test_hard_critical_requirements_outrank_soft_ones(db):
    result = recommend_experiments(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    by_key = {r["requirement_display_name"]: r for r in result["recommendations"]}
    hard = next(v for k, v in by_key.items() if "Band gap" in k)
    soft = next(v for k, v in by_key.items() if "Thermal conductivity" in k)
    assert hard["priority_score"] > soft["priority_score"]


# --- API ----------------------------------------------------------------------------------------------
def test_calibration_claim_requires_evidence(client):
    response = client.post("/experiments/instruments", headers=HEADERS, json={
        "key": "unbacked_claim", "display_name": "Instrument claiming calibration",
        "instrument_type": "bench", "calibration_status": "calibrated",
    })
    assert response.status_code == 422
    assert "never assumed or fabricated" in response.text


def test_experiment_endpoints_are_tenant_scoped(client):
    assert client.get("/experiments/protocols", headers=HOSTILE_HEADERS).json() == []
    assert client.post("/experiments/validation/assess", headers=HOSTILE_HEADERS, json={
        "role_id": ROLE_ID, "target_kind": "known_material", "target_id": SILICON_ID,
    }).status_code == 404
    assert client.get(f"/experiments/samples/{SAMPLE_ID}/lineage", headers=HOSTILE_HEADERS).status_code == 404


def test_policy_endpoint_declares_what_is_not_implemented(client):
    body = client.get("/experiments/policy", headers=HEADERS).json()
    assert "bayesian_optimization" in body["not_implemented_designs"]
    assert "active_learning" in body["not_implemented_designs"]
    assert "no laboratory system" in body["integration_note"]
    assert "does not order them" in body["autonomy_note"]


def test_completed_run_cannot_be_completed_twice(client, db):
    run = db.query(ExperimentRun).filter_by(status="completed").first()
    response = client.post(f"/experiments/runs/{run.id}/complete", headers=HEADERS)
    assert response.status_code == 422


def test_measurement_endpoint_reports_quality_reasons(client, db):
    run = db.query(ExperimentRun).filter_by(sample_id=ORPHAN_SAMPLE_ID).first()
    if run is None:
        plan_run = db.query(ExperimentRun).first()
        run_id = plan_run.id
    else:
        run_id = run.id
    response = client.post("/experiments/measurements", headers=HEADERS, json={
        "run_id": run_id, "property_key": "thermal_conductivity",
        "numeric_value": 33.0, "unit": "W/(m*K)", "uncertainty": 1.5,
    })
    assert response.status_code == 201
    body = response.json()
    assert body["scientific_origin"] == "experimental"
    assert body["quality"] in {"accepted", "provisional", "incomplete_provenance"}
    assert isinstance(body["quality_reasons"], list)
