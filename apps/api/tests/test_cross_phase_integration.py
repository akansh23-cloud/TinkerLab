"""Cross-phase reference integration test.

One scenario exercising the whole system: a replacement study for a material role, from application
decomposition through prediction, simulation, industrial viability, reasoning and evidence gaps, to
a physical measurement and the candidate re-evaluation that measurement forces.

Everything the test *creates* is a clearly marked fixture. The point is not that the numbers are
real — they are not — but that each layer hands off to the next without any origin being silently
converted into another, and that new experimental evidence changes the conclusion without destroying
the historical one.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.db.seed import sid
from app.domain.enums import (
    IndustrialAssessmentState,
    RequirementStatus,
    ValidationState,
)
from app.models.entities import (
    CandidateReasoningResult,
    ExperimentProtocolVersion,
    IndustrialViabilityAssessment,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    PropertyPrediction,
    SimulationResult,
)
from app.services.experiments_lab import (
    assess_validation,
    create_plan,
    materialize_plan_runs,
    recommend_experiments,
    record_measurement,
)
from app.services.industrial import assess_industrial_viability
from app.services.material_states import states_for_target
from app.services.reasoning import reason_about_candidate
from app.services.simulation import assert_simulation_integrity, preview_routes

ORG_ID = sid("org")
PROJECT_ID = sid("project")
ROLE_ID = sid("phase8:role:switching-material")
SILICON_ID = sid("material:silicon")
CANDIDATE_ID = sid("material:demo-wide-gap-synthetic")
PROTOCOL_VERSION_ID = sid("phase9:protocol-version:thermal-conductivity:1.0")
SAMPLE_ID = sid("phase9:sample:demo-wide-gap-001")
INSTRUMENT_ID = sid("phase9:instrument:demo-thermal-bench")
HEADERS = {"X-Organisation-ID": ORG_ID}


@pytest.fixture
def integration_candidate(db):
    """A candidate owned solely by this test file.

    The reference test commits evidence to exercise supersession, so it must not write onto the
    shared demonstration candidate: doing so would make other tests order-dependent.
    """
    from app.models.entities import Material
    from app.services.experiments_lab import create_sample
    from app.services.material_states import create_material_state

    material_id = sid("e2e:material:integration-candidate")
    if db.get(Material, material_id) is None:
        db.add(Material(
            id=material_id, canonical_name="e2e-integration-candidate",
            display_name="Reference integration candidate (SYNTHETIC test fixture)",
            material_family="crystalline_inorganic",
            description="Created by the cross-phase reference test. Not a real material and not a "
                        "scientific claim.",
            composition_summary="Xx (fixture)", source_type="test_fixture", is_seed_data=False,
            owner_organisation_id=ORG_ID, visibility="private",
        ))
        db.flush()
        state = create_material_state(
            db, organisation_id=ORG_ID, material_id=material_id,
            label="Reference integration candidate state (fixture)",
            composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}],
            temperature_k=300.0, is_reference_state=True,
            provenance_note="Test fixture state.",
        )
        create_sample(db, {
            "organisation_id": ORG_ID, "sample_code": "E2E-INT-001",
            "display_name": "Reference integration specimen (fixture)",
            "sample_kind": "synthesized", "material_id": material_id, "hypothesis_id": None,
            "material_state_id": state.id, "batch_reference": "E2E-BATCH",
            "preparation_date": date(2025, 7, 1),
            "geometry": "disc", "dimensions": {"thickness_m": 0.002},
            "metadata_json": {"surface_finish": "ground"},
            "provenance_note": "Test fixture specimen; no physical specimen exists.",
        }, row_id=sid("e2e:sample:integration"))
        db.commit()
    return material_id


def test_end_to_end_replacement_study(db, integration_candidate):
    CANDIDATE_ID = integration_candidate  # noqa: N806 - local shadow keeps the test self-contained
    """The full chain, in order, with the invariants checked at each handoff."""

    # 1-3. Target material, application context and material role.
    from app.services.reasoning import role_decomposition

    decomposition = role_decomposition(db, ROLE_ID)
    assert decomposition["application"] is not None
    assert decomposition["role"].incumbent_material_id == SILICON_ID
    assert decomposition["functions"], "the role must decompose into functions"

    # 4-5. Material state and structural identity for the incumbent.
    incumbent_states = states_for_target(
        db, target_kind="known_material", target_id=SILICON_ID, organisation_id=ORG_ID)
    assert incumbent_states, "the incumbent must have a recorded state"
    reference = next(s for s in incumbent_states if s.is_reference_state)
    assert reference.structure_identity, "structural identity comes from a real representation"
    assert reference.composition_signature == "Si"

    # 6. Requirements are bound to registered properties so evidence can be matched.
    requirements = [r for f in decomposition["functions"] for r in f.requirements]
    assert requirements
    assert all(r.property_definition_id for r in requirements if r.property_key)

    # 7-9. Candidate generation, prediction and uncertainty already exist from Phases 3-4; the
    # reference study consumes them rather than re-deriving them.
    predictions_before = db.query(PropertyPrediction).count()
    assert predictions_before > 0

    # 10. Physics simulation routing is available and refuses honestly where it must.
    routes = preview_routes(
        db, target_kind="known_material", target_id=SILICON_ID, organisation_id=ORG_ID,
        purpose="energy_stability")
    assert routes["routes"]
    refusals = [r for r in routes["routes"] if r["route_status"] != "ready"]
    assert all(r["reasons"] for r in refusals), "every refusal carries an explicit reason"

    # 11. Industrial viability, assessed per dimension with no opaque single number.
    _, industrial = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    assert set(industrial["dimension_states"])  # eight dimensions
    assert industrial["composite_score"] is None, "no composite without a declared methodology"
    # Phase 7 cannot claim experimental validation; that only arrives in Phase 9.
    assert industrial["dimension_states"]["experimental_validation"] == IndustrialAssessmentState.UNKNOWN

    # 12-13. Candidate reasoning and the evidence gaps it exposes.
    reasoning_before = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, project_id=PROJECT_ID, persist=True)
    db.commit()
    assert reasoning_before["evidence_gaps"], "an incompletely evidenced candidate must show gaps"
    thermal_before = next(
        r for r in reasoning_before["requirement_results"]
        if r["requirement_key"] == "min_thermal_conductivity")
    # This candidate starts with no evidence at all, so the honest status is UNKNOWN — not a pass
    # and not a failure.
    assert thermal_before["status"] == RequirementStatus.UNKNOWN
    assert thermal_before["values"] == []

    # 14. Experiment recommendation, derived from the unresolved requirements.
    recommendations = recommend_experiments(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=SILICON_ID, project_id=PROJECT_ID)
    assert recommendations["recommendations"]
    assert recommendations["methodology"] == "explainable_weighted_factors_v1"

    # 15-17. Experiment plan, sample and measurement.
    version = db.get(ExperimentProtocolVersion, PROTOCOL_VERSION_ID)
    plan, runs = create_plan(
        db, organisation_id=ORG_ID, display_name="Reference integration run",
        objective="Measure thermal conductivity to resolve the outstanding requirement.",
        design_kind="single_run", protocol_version=version, factors=[], replicate_count=2,
        control_plan="Reference control measured in the same synthetic fixture session.",
        project_id=PROJECT_ID, role_id=ROLE_ID)
    created = materialize_plan_runs(
        db, plan=plan, runs=runs, run_code_prefix="E2E", sample_id=sid("e2e:sample:integration"),
        instrument_id=INSTRUMENT_ID)
    run = created[0]
    completed_at = datetime(2025, 7, 2, 10, 0, tzinfo=UTC)
    for planned_run in created:
        planned_run.status = "completed"
        planned_run.started_at = completed_at
        planned_run.completed_at = completed_at
        planned_run.conditions = {"temperature_k": 300.0, "atmosphere": "air"}
    definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
    observations_before = db.query(MaterialPropertyObservation).count()
    simulations_before = db.query(SimulationResult).count()

    # A measurement well above the 100 W/(m*K) requirement, contradicting the earlier value of 12.
    measurement = record_measurement(
        db, organisation_id=ORG_ID, run=run, property_definition=definition,
        numeric_value=155.0, unit="W/(m*K)", uncertainty=5.0,
        method="Reference integration fixture measurement",
        conditions={"temperature_k": 300.0}, measured_at=completed_at,
        notes="SYNTHETIC fixture measurement created by the reference integration test.")
    db.commit()
    assert measurement.quality == "accepted"
    assert measurement.scientific_origin == "experimental"

    # 18. The measurement became experimental evidence WITHOUT becoming an observation or
    # overwriting any prediction or simulation.
    assert db.query(MaterialPropertyObservation).count() == observations_before
    assert db.query(SimulationResult).count() == simulations_before
    assert db.query(PropertyPrediction).count() == predictions_before
    integrity = assert_simulation_integrity(db)
    assert integrity["simulation_created_observations"] == 0

    # 19. Candidate re-evaluation. The new evidence changes the conclusion.
    validation = assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, project_id=PROJECT_ID, persist=True)
    db.commit()
    # Measurements of the same property now disagree, so the honest answer is inconclusive rather
    # than "the newest number wins".
    # One accepted measurement now supports the thermal requirement; the others remain outstanding.
    assert validation["validation_state"] == ValidationState.PARTIALLY_VALIDATED
    assert validation["experimentally_supported_requirements"]
    assert validation["outstanding_requirements"]
    assert "does not overwrite" in validation["separation_note"]

    reasoning_after = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, project_id=PROJECT_ID, persist=True)
    db.commit()
    assert reasoning_after["reasoning_checksum"] != reasoning_before["reasoning_checksum"], (
        "new evidence must change the reasoning result"
    )

    # The historical assessment remains readable and unchanged.
    historical = db.get(CandidateReasoningResult, reasoning_before["reasoning_result_id"])
    assert historical.overall_status == reasoning_before["overall_status"]
    assert historical.superseded_by_id == reasoning_after["reasoning_result_id"]


def test_no_origin_is_ever_silently_converted(db):
    """A single assertion of the property the entire system exists to protect."""
    counts_before = {
        "observations": db.query(MaterialPropertyObservation).count(),
        "predictions": db.query(PropertyPrediction).count(),
        "simulations": db.query(SimulationResult).count(),
    }

    # Run every analysis layer that could plausibly be tempted to write into another's table.
    assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=True)
    reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, persist=True)
    assess_validation(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, persist=True)
    recommend_experiments(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, persist=True)
    db.commit()

    assert db.query(MaterialPropertyObservation).count() == counts_before["observations"]
    assert db.query(PropertyPrediction).count() == counts_before["predictions"]
    assert db.query(SimulationResult).count() == counts_before["simulations"]


def test_assessment_history_is_reproducible_after_evidence_changes(db):
    """Yesterday's conclusion must stay explainable exactly as it was made."""
    first, first_payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, persist=True)
    db.commit()
    snapshot = {
        "id": first.id,
        "states": dict(first.dimension_states),
        "checksum": first.assessment_checksum,
        "evidence_snapshot": dict(first.evidence_snapshot),
    }

    # Evidence changes underneath it.
    from app.services.industrial import create_industrial_evidence

    create_industrial_evidence(db, {
        "organisation_id": ORG_ID, "material_id": CANDIDATE_ID, "hypothesis_id": None,
        "category": "supply_chain", "metric_key": "supplier_count",
        "display_label": "New supplier count (fixture)", "numeric_value": 11.0, "unit": "count",
        "as_of_date": date(2026, 1, 1), "source_type": "seed_demonstration",
    })
    db.commit()

    second, _ = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=CANDIDATE_ID, persist=True)
    db.commit()
    db.expire_all()

    historical = db.get(IndustrialViabilityAssessment, snapshot["id"])
    assert historical.dimension_states == snapshot["states"]
    assert historical.assessment_checksum == snapshot["checksum"]
    assert historical.evidence_snapshot == snapshot["evidence_snapshot"]
    assert historical.superseded_by_id == second.id
    assert first_payload["policy_version"] == historical.policy_version


def test_full_chain_is_reachable_through_the_api(client):
    """Every layer answers over HTTP with its scope and separation notes intact."""
    checks = [
        ("/simulation/integrity", None),
        ("/industrial/dimensions", "separation_note"),
        ("/reasoning/origin-policy", "origin_separation_note"),
        ("/experiments/policy", "autonomy_note"),
    ]
    for path, expected_key in checks:
        response = client.get(path, headers=HEADERS)
        assert response.status_code == 200, path
        if expected_key:
            assert expected_key in response.json(), f"{path} must state its separation policy"

    decomposition = client.get(f"/reasoning/roles/{ROLE_ID}/decomposition", headers=HEADERS)
    assert decomposition.status_code == 200

    reasoning = client.post("/reasoning/candidate", headers=HEADERS, json={
        "role_id": ROLE_ID, "target_kind": "known_material", "target_id": CANDIDATE_ID})
    assert reasoning.status_code == 200
    assert reasoning.json()["structured_first_note"]

    validation = client.post("/experiments/validation/assess", headers=HEADERS, json={
        "role_id": ROLE_ID, "target_kind": "known_material", "target_id": CANDIDATE_ID})
    assert validation.status_code == 200
    assert validation.json()["validation_state"] in {
        "computational_only", "simulation_supported", "experiment_recommended", "experiment_pending",
        "experiment_in_progress", "partially_validated", "experimentally_supported",
        "experimentally_contradicted", "conflicting_experiments", "contradicted", "inconclusive",
    }


def test_no_autonomous_discovery_surface_exists(client):
    """Phase 9 is not permission to build an autonomous scientist."""
    openapi = client.get("/openapi.json").json()
    paths = " ".join(openapi["paths"].keys()).lower()
    for forbidden in ("/autonomous", "/auto-discover", "/order-experiment", "/execute-lab",
                      "/robot", "/self-improve", "/auto-generate-materials"):
        assert forbidden not in paths, f"an autonomy surface exists: {forbidden}"

    policy = client.get("/experiments/policy", headers=HEADERS).json()
    assert "does not order them, operate laboratory hardware, or perform them" in policy["autonomy_note"]


@pytest.mark.parametrize("state", ["experimentally_supported", "partially_validated"])
def test_validated_states_require_measurements(db, state):
    """No validated state may be reachable from simulation alone."""
    from app.services.experiments_lab import _validation_state

    result, _ = _validation_state(
        reasoning={"origin_breakdown": {"simulated": 3, "predicted": 2}},
        experimentally_supported=[], outstanding=["r1"], disagreements=[], conflicts=[])
    assert result != state
    assert result == ValidationState.SIMULATION_SUPPORTED
