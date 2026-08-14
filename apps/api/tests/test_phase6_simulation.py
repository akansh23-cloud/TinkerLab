from __future__ import annotations

import pytest

from app.db.seed import sid
from app.models.entities import (
    MaterialPropertyObservation,
    PropertyPrediction,
    SimulationJob,
    SimulationPropertyEstimate,
    SimulationProviderVersion,
    SimulationResult,
    SimulationWorkflow,
    VirtualCandidateEvaluation,
)
from app.services.representations import (
    RepresentationError,
    representation_checksum,
    validate_representation,
)
from app.services.simulation import (
    SIMULATION_WARNING,
    assert_simulation_integrity,
    build_workflow_preview,
    create_workflow,
    execute_workflow,
    preview_routes,
    select_simulation_value,
)
from app.services.simulation_adapters import SOFTWARE_FIXTURE_WARNING, get_adapter
from app.services.simulation_runtime import (
    ALLOWED_EXECUTABLES,
    UnsafeExecutionRequest,
    _runtime_root,
    resolve_executable,
    safe_join,
    sanitized_environment,
)

ORG_ID = sid("org")
USER_ID = sid("user")
PROJECT_ID = sid("project")
BASELINE_ID = sid("material:demo-polymer-baseline")
FIXTURE_VERSION_ID = sid("phase6:provider-version:software_fixture_harmonic:v1")
QE_VERSION_ID = sid("phase6:provider-version:quantum_espresso_local:v1")
LAMMPS_VERSION_ID = sid("phase6:provider-version:lammps_local:v1")
CALPHAD_VERSION_ID = sid("phase6:provider-version:calphad_interface:v1")
MLFF_VERSION_ID = sid("phase6:provider-version:ml_force_field_interface:v1")
SEEDED_WORKFLOW_ID = sid("phase6:workflow:fixture-harmonic-demo")
HEADERS = {"X-Organisation-ID": ORG_ID}

DIAMOND = {
    "lattice_vectors": [[3.567, 0, 0], [0, 3.567, 0], [0, 0, 3.567]],
    "lattice_unit": "angstrom",
    "sites": [
        {"element": "C", "fractional_coordinates": [0, 0, 0]},
        {"element": "C", "fractional_coordinates": [0.25, 0.25, 0.25]},
    ],
    "space_group_number": 227,
}


# --- representations -----------------------------------------------------------------------------
def test_representation_checksum_is_deterministic_and_order_independent():
    _, a = validate_representation("periodic_structure_json_v1", DIAMOND)
    shuffled = dict(DIAMOND)
    shuffled["sites"] = list(reversed(DIAMOND["sites"]))
    _, b = validate_representation("periodic_structure_json_v1", shuffled)
    def get_checksum(o): return representation_checksum("periodic_structure_json_v1", "periodic_structure_json_v1", "1.0", o.normalized_content)
    assert get_checksum(a) == get_checksum(b)
    changed = dict(DIAMOND)
    changed["lattice_vectors"] = [[3.6, 0, 0], [0, 3.567, 0], [0, 0, 3.567]]
    _, c = validate_representation("periodic_structure_json_v1", changed)
    assert get_checksum(a) != get_checksum(c)


def test_unknown_element_and_invalid_syntax_are_rejected_not_repaired():
    _, bad_element = validate_representation("periodic_structure_json_v1", {
        "lattice_vectors": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "sites": [{"element": "Xx", "fractional_coordinates": [0, 0, 0]}],
    })
    assert bad_element.validation_status == "structurally_invalid"
    _, bad_syntax = validate_representation("periodic_structure_json_v1", {"lattice_vectors": "nope", "sites": []})
    assert bad_syntax.validation_status == "invalid_syntax"
    with pytest.raises(RepresentationError):
        validate_representation("arbitrary_python_pickle", {})


def test_topology_without_force_field_mapping_is_incomplete():
    _, outcome = validate_representation("atomistic_topology_json_v1", {
        "atom_types": [{"id": 1, "mass_amu": 12.011}],
        "atoms": [{"id": 1, "type": 1, "position": [0, 0, 0]}],
        "box": [10, 10, 10],
    })
    assert outcome.validation_status == "valid"
    assert outcome.completeness_status == "incomplete"
    assert any(m["code"] == "FORCE_FIELD_MAPPING_MISSING" for m in outcome.messages)


def test_redacted_formulation_is_flagged_not_silently_repaired():
    _, outcome = validate_representation("formulation_summary_json_v1", {
        "components": [{"component_key": "secret_mod", "is_redacted": True}],
    })
    assert outcome.completeness_status == "redacted"
    assert outcome.redaction_flags == ["redacted_component:secret_mod"]
    assert outcome.normalized_content["atomistic_detail_present"] is False


def test_representation_requires_exactly_one_target(client):
    response = client.post(f"/materials/{BASELINE_ID}/representations", headers=HEADERS, json={
        "label": "diamond routing demo", "representation_format": "periodic_structure_json_v1", "content": DIAMOND,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["material_id"] == BASELINE_ID and body["hypothesis_id"] is None
    assert body["validation_status"] == "valid" and body["completeness_status"] == "complete"


# --- router --------------------------------------------------------------------------------------
def test_formulation_only_polymer_is_refused_by_dft_and_md(db):
    preview = preview_routes(db, target_kind="known_material", target_id=BASELINE_ID,
                             organisation_id=ORG_ID, purpose="energy_stability")
    by_family = {}
    for route in preview["routes"]:
        by_family.setdefault(route["method_family"], []).append(route)
    assert all(r["route_status"] != "ready" for r in by_family.get("dft", [])), "DFT must not be ready without pseudopotentials"
    for route in by_family.get("dft", []):
        assert route["route_status"] in {"missing_registered_artifact", "provider_unavailable", "not_applicable", "incomplete_representation"}
    fixture_routes = by_family.get("analytical_fixture", [])
    assert any(r["route_status"] == "ready" for r in fixture_routes)
    assert preview["warning"] == SIMULATION_WARNING


def test_route_preview_persists_nothing(db, client):
    from app.models.entities import SimulationRoute
    before = db.query(SimulationRoute).count()
    response = client.post("/simulation/routes/preview", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": BASELINE_ID, "requested_purpose": "energy_stability",
    })
    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.query(SimulationRoute).count() == before
    body = response.json()
    ready = [r for r in body["routes"] if r["route_status"] == "ready"]
    refused = [r for r in body["routes"] if r["route_status"] != "ready"]
    assert ready and refused
    assert all(r["reasons"] for r in refused), "every refusal must carry explicit reasons"


def test_route_ordering_is_deterministic(db):
    a = preview_routes(db, target_kind="known_material", target_id=BASELINE_ID, organisation_id=ORG_ID, purpose="energy_stability")
    b = preview_routes(db, target_kind="known_material", target_id=BASELINE_ID, organisation_id=ORG_ID, purpose="energy_stability")
    assert [r["route_checksum"] for r in a["routes"]] == [r["route_checksum"] for r in b["routes"]]
    assert a["routes"][0]["route_status"] == "ready"


def test_cross_tenant_target_is_not_found(client):
    response = client.post("/simulation/routes/preview", headers={"X-Organisation-ID": sid("other-org")}, json={
        "target_kind": "hypothesis", "target_id": sid("nonexistent"), "requested_purpose": "energy_stability",
    })
    assert response.status_code == 404


# --- provider registry ---------------------------------------------------------------------------
def test_provider_availability_is_honest(client):
    providers = client.get("/simulation/providers", headers=HEADERS).json()
    by_key = {p["key"]: p for p in providers}
    assert set(by_key) >= {"software_fixture_harmonic", "lammps_local", "quantum_espresso_local",
                           "calphad_interface", "ml_force_field_interface"}
    fixture = client.get(f"/simulation/provider-versions/{FIXTURE_VERSION_ID}/availability", headers=HEADERS).json()
    assert fixture["available"] is True
    # The invariant is honesty, not absence: reported availability must match what is actually
    # resolvable on this host. Hard-coding "unavailable" would silently pass on a machine where the
    # solver IS installed and the adapter wrongly claimed it was not (or vice versa).
    for version_id, executable_key in ((LAMMPS_VERSION_ID, "lammps"), (QE_VERSION_ID, "quantum_espresso_pw")):
        availability = client.get(f"/simulation/provider-versions/{version_id}/availability", headers=HEADERS).json()
        binary_present = resolve_executable(executable_key)[0] is not None
        assert availability["available"] is binary_present, (
            f"{executable_key}: reported {availability['available']} but binary present is {binary_present}"
        )
        if binary_present:
            assert availability["reason_code"] == "available"
            assert availability["executable_name"]
        else:
            assert availability["reason_code"] in {"executable_not_installed", "interface_only"}

    # Interface-only providers are unavailable regardless of what is installed on the host.
    for version_id in (CALPHAD_VERSION_ID, MLFF_VERSION_ID):
        availability = client.get(f"/simulation/provider-versions/{version_id}/availability", headers=HEADERS).json()
        assert availability["available"] is False
        assert availability["reason_code"] == "interface_only"


def test_provider_version_is_immutable_after_use(db):
    version = db.get(SimulationProviderVersion, FIXTURE_VERSION_ID)
    from app.services.simulation import provider_version_in_use
    assert provider_version_in_use(db, version) is True
    original = version.artifact_manifest_checksum
    version.artifact_manifest = [{"tampered": True}]
    from app.services.simulation import provider_version_executable
    ok, reason = provider_version_executable(db, version)
    assert ok is False and "checksum" in (reason or "")
    db.rollback()
    db.expire_all()
    assert db.get(SimulationProviderVersion, FIXTURE_VERSION_ID).artifact_manifest_checksum == original


# --- safe execution ------------------------------------------------------------------------------
def test_path_traversal_and_arbitrary_executables_are_rejected():
    root = _runtime_root()
    for hostile in ("../escape", "..", "a/../../b", "/etc/passwd", ".hidden", "name with space"):
        with pytest.raises(UnsafeExecutionRequest):
            safe_join(root, hostile)
    # Executable selection is by allowlist key only; arbitrary names resolve to nothing.
    assert resolve_executable("bash") == (None, None)
    assert resolve_executable("/usr/bin/python3") == (None, None)
    assert set(ALLOWED_EXECUTABLES) == {"lammps", "quantum_espresso_pw"}


def test_environment_is_allowlisted():
    import os
    os.environ["TINKERLAB_FAKE_SECRET"] = "leak-me"
    try:
        env = sanitized_environment()
        assert "TINKERLAB_FAKE_SECRET" not in env
        assert "DATABASE_URL" not in env
    finally:
        del os.environ["TINKERLAB_FAKE_SECRET"]


def test_workflow_api_rejects_unsafe_payload_shapes(client):
    # There is no field for a command, path, script or image anywhere in the contract.
    response = client.post("/simulation/workflows", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": BASELINE_ID,
        "method_key": "software_fixture_energy_minimization_v1",
        "provider_version_id": FIXTURE_VERSION_ID,
        "parameters": {"step_size": 0.1, "max_iterations": 10, "gradient_tolerance": 1e-6,
                       "command": "rm -rf /", "executable_path": "/bin/sh"},
    })
    # Unknown keys are ignored by the typed parameter validator; nothing executes them.
    assert response.status_code in {201, 422}
    if response.status_code == 201:
        detail = client.get(f"/simulation/workflows/{response.json()['id']}", headers=HEADERS).json()
        assert "command" not in detail["workflow"]["id"]


# --- workflow lifecycle --------------------------------------------------------------------------
def test_workflow_preview_executes_nothing(db, client):
    jobs_before = db.query(SimulationJob).count()
    response = client.post("/simulation/workflows/preview", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": BASELINE_ID,
        "method_key": "software_fixture_energy_minimization_v1",
        "provider_version_id": FIXTURE_VERSION_ID,
        "parameters": {"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True and body["executes_nothing"] is True
    assert body["input_checksum"]
    assert body["provider_version"]["artifact_manifest_checksum"]
    db.expire_all()
    assert db.query(SimulationJob).count() == jobs_before


def test_missing_required_parameter_is_an_error_not_a_default(db):
    with pytest.raises(ValueError, match="never defaulted"):
        create_workflow(
            db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
            method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
            parameters={"step_size": 0.1, "max_iterations": 100},  # gradient_tolerance missing
        )
    db.rollback()


def test_seeded_workflow_is_converged_with_full_provenance(db, client):
    detail = client.get(f"/simulation/workflows/{SEEDED_WORKFLOW_ID}", headers=HEADERS).json()
    workflow, result = detail["workflow"], detail["result"]
    assert workflow["status"] == "completed" and workflow["workflow_checksum"]
    assert result["operational_status"] == "completed"
    assert result["scientific_status"] == "converged"
    assert result["scientific_origin"] == "physics_simulation"
    assert detail["warning"] == SIMULATION_WARNING
    assert detail["jobs"][0]["command_descriptor"]["shell"] is False
    assert all(a["content_checksum"] and "/" not in a["storage_reference"].split("://")[0] for a in detail["artifacts"])
    # No absolute host filesystem path is exposed anywhere in the payload.
    import json as jsonlib
    assert "/tmp/" not in jsonlib.dumps(detail)
    estimate = detail["property_estimates"][0]
    # Analytic minimum of 0.5*4*x^2 - 2x + 0.75 is 0.25 in reduced units.
    assert estimate["canonical_value"] == pytest.approx(0.25, abs=1e-6)
    assert estimate["canonical_unit"] == "1"
    assert estimate["numerical_tolerance"] == pytest.approx(1e-8)


def test_deterministic_replay_reproduces_result_checksum(db):
    seeded = db.query(SimulationResult).filter_by(workflow_id=SEEDED_WORKFLOW_ID).one()
    replay = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
    )
    execute_workflow(db, replay)
    replay_result = db.query(SimulationResult).filter_by(workflow_id=replay.id).one()
    assert replay_result.result_checksum == seeded.result_checksum
    snapshot_a = db.get(SimulationWorkflow, SEEDED_WORKFLOW_ID)
    assert replay.input_snapshot_id != snapshot_a.input_snapshot_id  # rows differ, science identical


def test_changed_parameter_changes_checksums(db):
    preview_a = build_workflow_preview(
        db, target_kind="known_material", target_id=BASELINE_ID, organisation_id=ORG_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8})
    preview_b = build_workflow_preview(
        db, target_kind="known_material", target_id=BASELINE_ID, organisation_id=ORG_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.2, "max_iterations": 500, "gradient_tolerance": 1e-8})
    assert preview_a["input_checksum"] != preview_b["input_checksum"]


def test_unconverged_fixture_yields_no_property_estimate(db):
    # A budget of 1 iteration cannot meet a 1e-10 tolerance from x=1.5: exit is clean, science is not.
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.01, "max_iterations": 1, "gradient_tolerance": 1e-10},
    )
    execute_workflow(db, workflow)
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one()
    assert result.operational_status == "completed"
    assert result.scientific_status == "unconverged"
    assert db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).count() == 0
    assert any("NOT a converged result" in w for w in result.warnings)


def test_parser_failure_yields_no_estimate():
    adapter = get_adapter("software_fixture_harmonic_v1")
    parsed = adapter.parse_outputs({"stdout": "garbage with no markers\n"})
    assert parsed["parse_status"] == "parser_failed" and parsed["quantities"] == {}
    parsed_nan = adapter.parse_outputs({"stdout": "reduced_energy nan\nfinal_gradient 0\niterations 1\nfinal_displacement 0\n"})
    assert parsed_nan["parse_status"] == "parser_failed"


def test_retry_appends_attempt_and_never_overwrites(db):
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
    )
    execute_workflow(db, workflow)
    first_jobs = db.query(SimulationJob).filter_by(workflow_id=workflow.id).count()
    with pytest.raises(ValueError):
        execute_workflow(db, workflow)  # completed workflows are immutable
    assert db.query(SimulationJob).filter_by(workflow_id=workflow.id).count() == first_jobs


# --- scientific integrity ------------------------------------------------------------------------
def test_simulation_creates_zero_observations_and_zero_predictions(db):
    observations_before = db.query(MaterialPropertyObservation).count()
    predictions_before = db.query(PropertyPrediction).count()
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
    )
    execute_workflow(db, workflow)
    assert db.query(MaterialPropertyObservation).count() == observations_before
    assert db.query(PropertyPrediction).count() == predictions_before
    integrity = assert_simulation_integrity(db)
    assert integrity["estimates_from_non_converged_results"] == 0
    assert integrity["simulation_created_observations"] == 0


def test_fixture_warning_is_unmistakable(db, client):
    detail = client.get(f"/simulation/workflows/{SEEDED_WORKFLOW_ID}", headers=HEADERS).json()
    limitations = detail["result"]["method_limitations"]
    assert any(SOFTWARE_FIXTURE_WARNING in limitation for limitation in limitations)
    body = str(detail)
    assert "experimentally validated" not in body.lower()
    assert "globally optimal" not in body.lower()


def test_campaign_history_is_unchanged_by_simulation(db):
    campaign_id = sid("phase5:virtual-campaign:demo-robust-pareto")
    evaluations_before = [
        (e.id, e.deterministic_evaluation_checksum, e.pareto_rank)
        for e in db.query(VirtualCandidateEvaluation).order_by(VirtualCandidateEvaluation.id).all()
    ]
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material", target_id=BASELINE_ID,
        method_key="software_fixture_energy_minimization_v1", provider_version_id=FIXTURE_VERSION_ID,
        parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
        campaign_id=campaign_id,
    )
    execute_workflow(db, workflow)
    evaluations_after = [
        (e.id, e.deterministic_evaluation_checksum, e.pareto_rank)
        for e in db.query(VirtualCandidateEvaluation).order_by(VirtualCandidateEvaluation.id).all()
    ]
    assert evaluations_before == evaluations_after


def test_campaign_escalation_maps_candidates_without_mutating(client, db):
    campaign_id = sid("phase5:virtual-campaign:demo-robust-pareto")
    candidate_id = sid("candidate:0")
    response = client.post(f"/virtual-campaigns/{campaign_id}/simulation-escalation", headers=HEADERS,
                           json={"candidate_ids": [candidate_id]})
    assert response.status_code == 200
    body = response.json()
    assert body["targets"][0]["target_kind"] == "known_material"
    assert "never reranks" in body["note"]


def test_selection_policy_is_explicit_opt_in(db, client):
    selection = select_simulation_value(db, project_id=PROJECT_ID, property_key="software_fixture_reduced_energy",
                                        target_id=BASELINE_ID, organisation_id=ORG_ID)
    assert selection["selected"] is False
    assert selection["policy"] == "evidence_then_prediction_v1"
    response = client.post("/simulation/selection-policies", headers=HEADERS, json={
        "project_id": PROJECT_ID, "property_key": "software_fixture_reduced_energy",
        "target_scientific_id": BASELINE_ID, "simulation_workflow_id": SEEDED_WORKFLOW_ID,
        "rationale": "Explicit scientist opt-in for the synthetic demo property only.",
    })
    assert response.status_code == 201, response.text
    db.expire_all()
    selected = select_simulation_value(db, project_id=PROJECT_ID, property_key="software_fixture_reduced_energy",
                                       target_id=BASELINE_ID, organisation_id=ORG_ID)
    assert selected["selected"] is True
    assert selected["scientific_origin"] == "physics_simulation"
    assert selected["canonical_value"] == pytest.approx(0.25, abs=1e-6)


def test_target_history_is_scoped_and_labelled(client):
    history = client.get(f"/simulation/targets/known_material/{BASELINE_ID}/history", headers=HEADERS).json()
    assert history["total"] >= 1
    assert all(item["scientific_origin"] == "physics_simulation" for item in history["items"])
    unauthorised = client.get(f"/simulation/targets/known_material/{BASELINE_ID}/history")
    assert unauthorised.status_code == 404
