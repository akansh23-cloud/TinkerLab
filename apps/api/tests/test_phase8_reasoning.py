"""Phase-8 tests: material states, structural identity, and replacement reasoning.

The invariants under test are the ones that make replacement reasoning honest: a shared formula is
not a shared structure, a property does not travel across an incompatible state, evidence origins
stay separate, and an absent value stays absent instead of becoming a pass or a failure.
"""
from __future__ import annotations

import pytest

from app.db.seed import sid
from app.domain.enums import RequirementStatus, StateMatchQuality
from app.models.entities import (
    CandidateReasoningResult,
    Evidence,
    FunctionalRequirement,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialState,
    ReasoningEdge,
)
from app.services.material_states import (
    StateError,
    composition_signature,
    create_material_state,
    create_processing_history,
    match_states,
    normalize_composition,
    processing_history_checksum,
    reference_state,
    structure_identity,
)
from app.services.reasoning import (
    ReasoningError,
    create_reasoning_edge,
    evaluate_requirement,
    mechanism_paths_for_property,
    reason_about_candidate,
    role_decomposition,
)

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
PROJECT_ID = sid("project")
SILICON_ID = sid("material:silicon")
DEMO_CANDIDATE_ID = sid("material:demo-wide-gap-synthetic")
ROLE_ID = sid("phase8:role:switching-material")
SILICON_STATE_ID = sid("phase8:state:silicon-single-crystal-300k")
DEMO_STATE_ID = sid("phase8:state:demo-wide-gap-300k")
HEADERS = {"X-Organisation-ID": ORG_ID}
HOSTILE_HEADERS = {"X-Organisation-ID": OTHER_ORG}

DIAMOND_CELL = {
    "lattice_vectors": [[3.567, 0, 0], [0, 3.567, 0], [0, 0, 3.567]],
    "lattice_unit": "angstrom",
    "sites": [{"element": "C", "fractional_coordinates": [0, 0, 0]},
              {"element": "C", "fractional_coordinates": [0.25, 0.25, 0.25]}],
    "space_group_number": 227,
}
GRAPHITE_CELL = {
    "lattice_vectors": [[2.46, 0, 0], [-1.23, 2.13, 0], [0, 0, 6.71]],
    "lattice_unit": "angstrom",
    "sites": [{"element": "C", "fractional_coordinates": [0, 0, 0]},
              {"element": "C", "fractional_coordinates": [0.333333, 0.666667, 0]}],
    "space_group_number": 194,
}


def _representation(db, content, material_id=SILICON_ID):
    from app.services.simulation import create_representation

    return create_representation(
        db, organisation_id=ORG_ID, material_id=material_id, hypothesis_id=None,
        label="test cell", representation_format="periodic_structure_json_v1", content=content,
    )


# --- composition and structural identity --------------------------------------------------------
def test_composition_signature_distinguishes_dopants():
    """Si and Si:B are not the same material for a semiconductor role."""
    pure = composition_signature([{"element": "Si", "role": "host", "stoichiometry": 1.0}])
    doped = composition_signature([
        {"element": "Si", "role": "host", "stoichiometry": 1.0},
        {"element": "B", "role": "dopant", "concentration_value": 1e16},
    ])
    assert pure == "Si"
    assert doped != pure
    assert "dopant" in doped


def test_composition_ranges_are_not_collapsed_to_a_midpoint():
    normalized = normalize_composition([
        {"element": "Cr", "role": "alloying", "atomic_fraction_min": 0.10,
         "atomic_fraction_max": 0.30, "original_representation": "10-30 at.%"},
    ])
    component = normalized[0]
    assert component["atomic_fraction_min"] == 0.10
    assert component["atomic_fraction_max"] == 0.30
    assert component["atomic_fraction"] is None, "a range must not become a single invented number"
    assert component["original_representation"] == "10-30 at.%"


def test_inverted_composition_range_is_refused():
    with pytest.raises(StateError, match="exceeds"):
        normalize_composition([{"element": "Cr", "atomic_fraction_min": 0.9, "atomic_fraction_max": 0.1}])


def test_same_formula_different_structure_is_a_different_identity(db):
    """Diamond and graphite are both carbon. The engine must never treat them as the same thing."""
    diamond = _representation(db, DIAMOND_CELL)
    graphite = _representation(db, GRAPHITE_CELL)
    diamond_identity, diamond_basis = structure_identity(diamond, space_group_number=227)
    graphite_identity, _ = structure_identity(graphite, space_group_number=194)
    assert diamond_identity and graphite_identity
    assert diamond_identity != graphite_identity
    assert diamond_basis == "periodic_cell_metrics_and_sites"
    db.rollback()


def test_structure_identity_is_none_without_a_representation():
    """No structural representation means no structural identity — not a formula-derived stand-in."""
    identity, basis = structure_identity(None)
    assert identity is None
    assert basis == "no_structural_representation"


def test_structure_identity_is_stable_under_site_reordering(db):
    reordered = dict(DIAMOND_CELL)
    reordered["sites"] = list(reversed(DIAMOND_CELL["sites"]))
    first = structure_identity(_representation(db, DIAMOND_CELL))[0]
    second = structure_identity(_representation(db, reordered))[0]
    assert first == second
    db.rollback()


def test_processing_history_order_matters():
    anneal_then_quench = [
        {"step_kind": "annealing", "temperature_k": 1073.0},
        {"step_kind": "quenching", "temperature_k": 300.0},
    ]
    assert processing_history_checksum(anneal_then_quench) != processing_history_checksum(
        list(reversed(anneal_then_quench))
    )


# --- state matching -----------------------------------------------------------------------------
def test_state_matching_rejects_different_structures(db):
    diamond_state = create_material_state(
        db, organisation_id=ORG_ID, material_id=SILICON_ID, label="diamond-like",
        composition=[{"element": "C", "role": "host", "stoichiometry": 1.0}],
        representation_id=_representation(db, DIAMOND_CELL).id, space_group_number=227,
    )
    graphite_state = create_material_state(
        db, organisation_id=ORG_ID, material_id=SILICON_ID, label="graphite-like",
        composition=[{"element": "C", "role": "host", "stoichiometry": 1.0}],
        representation_id=_representation(db, GRAPHITE_CELL).id, space_group_number=194,
    )
    match = match_states(diamond_state, graphite_state)
    assert match.quality == StateMatchQuality.DIFFERENT_STATE
    assert match.usable is False
    assert any("different structures" in r for r in match.reasons)
    db.rollback()


def test_matching_composition_without_structure_is_flagged_as_composition_level_only(db):
    # Distinct states (different recorded conditions) sharing a composition but with no structural
    # representation on either side. The match must be composition-level only, and say so.
    first = create_material_state(
        db, organisation_id=ORG_ID, material_id=SILICON_ID, label="a",
        composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}], temperature_k=300.0,
        conditions={"sample": "a"})
    second = create_material_state(
        db, organisation_id=ORG_ID, material_id=SILICON_ID, label="b",
        composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}], temperature_k=300.0,
        conditions={"sample": "b"})
    assert first.state_checksum != second.state_checksum
    match = match_states(first, second)
    assert match.quality == StateMatchQuality.CONDITIONALLY_COMPATIBLE
    assert any("shared formula is not a shared structure" in r for r in match.reasons)
    db.rollback()


def test_state_matching_rejects_different_temperature_and_processing(db):
    base = dict(organisation_id=ORG_ID, material_id=SILICON_ID,
                composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}])
    cold = create_material_state(db, label="cold", temperature_k=300.0, **base)
    hot = create_material_state(db, label="hot", temperature_k=800.0, **base)
    assert match_states(cold, hot).quality == StateMatchQuality.DIFFERENT_STATE

    history_a = create_processing_history(db, organisation_id=ORG_ID, display_name="annealed",
                                          steps=[{"step_kind": "annealing", "temperature_k": 1073.0}])
    history_b = create_processing_history(db, organisation_id=ORG_ID, display_name="quenched",
                                          steps=[{"step_kind": "quenching", "temperature_k": 300.0}])
    annealed = create_material_state(db, label="annealed", processing_history_id=history_a.id, **base)
    quenched = create_material_state(db, label="quenched", processing_history_id=history_b.id, **base)
    match = match_states(annealed, quenched)
    assert match.quality == StateMatchQuality.DIFFERENT_STATE
    assert any("Processing history differs" in r for r in match.reasons)
    db.rollback()


def test_unknown_state_is_not_compatibility(db):
    state = db.get(MaterialState, SILICON_STATE_ID)
    match = match_states(state, None)
    assert match.quality == StateMatchQuality.UNKNOWN_STATE
    assert match.usable is False


def test_state_requires_exactly_one_target(db):
    with pytest.raises(StateError, match="exactly one"):
        create_material_state(db, organisation_id=ORG_ID, label="bad",
                              material_id=SILICON_ID, hypothesis_id=sid("x"))
    db.rollback()


def test_seeded_silicon_state_has_structure_identity(db):
    state = db.get(MaterialState, SILICON_STATE_ID)
    assert state.structure_identity, "the reference state must carry a structural identity"
    assert state.structure_identity_basis == "periodic_cell_metrics_and_sites"
    assert state.composition_signature == "Si"
    assert state.is_reference_state is True
    assert reference_state(db, target_kind="known_material", target_id=SILICON_ID,
                           organisation_id=ORG_ID).id == SILICON_STATE_ID


# --- decomposition ------------------------------------------------------------------------------
def test_role_decomposes_into_functions_and_requirements(db):
    decomposition = role_decomposition(db, ROLE_ID)
    assert decomposition["application"].key == "power_electronic_switch"
    assert decomposition["component"].key == "active_region"
    function_keys = {f.key for f in decomposition["functions"]}
    assert {"block_electric_field", "limit_leakage_at_temperature", "conduct_heat_away"} <= function_keys
    # Functions are ordered most-critical first so the important gaps surface at the top.
    criticalities = [f.criticality for f in decomposition["functions"]]
    assert criticalities == sorted(criticalities, reverse=True)


def test_requirements_bind_to_registered_properties(db):
    requirements = db.query(FunctionalRequirement).all()
    for requirement in requirements:
        if requirement.property_key:
            assert requirement.property_definition_id, (
                f"{requirement.key} names a property but is not bound to a definition, so no "
                "evidence could ever be matched to it"
            )


def test_target_direction_without_tolerance_is_refused(client):
    functions = client.get(f"/reasoning/roles/{ROLE_ID}/decomposition", headers=HEADERS).json()["functions"]
    response = client.post(f"/reasoning/functions/{functions[0]['id']}/requirements", headers=HEADERS, json={
        "key": "bad_target", "display_name": "target without tolerance", "direction": "target",
        "property_key": "band_gap", "target_value": 1.0,
    })
    assert response.status_code == 422
    assert "tolerance" in response.text


def test_requirement_cannot_bind_to_an_unregistered_property(client):
    functions = client.get(f"/reasoning/roles/{ROLE_ID}/decomposition", headers=HEADERS).json()["functions"]
    response = client.post(f"/reasoning/functions/{functions[0]['id']}/requirements", headers=HEADERS, json={
        "key": "bad_property", "display_name": "unknown property", "direction": "minimum",
        "property_key": "unobtainium_index", "target_value": 1.0,
    })
    assert response.status_code == 422
    assert "Unknown property definition" in response.text


# --- reasoning graph ----------------------------------------------------------------------------
def test_unsourced_causal_edge_is_refused(db):
    with pytest.raises(ReasoningError, match="Unsourced causal relationships"):
        create_reasoning_edge(db, {
            "organisation_id": ORG_ID, "edge_kind": "mechanism_governs_property",
            "from_kind": "mechanism", "from_id": "m1", "to_kind": "property", "to_id": "band_gap",
        })
    db.rollback()


def test_seeded_edges_all_carry_scope_and_source(db):
    edges = db.query(ReasoningEdge).all()
    assert edges
    for edge in edges:
        assert edge.source_reference or edge.evidence_id
        assert edge.scope, f"{edge.edge_kind} edge has no scope, making it an unbounded causal claim"


def test_mechanism_path_traverses_state_to_property(db):
    paths = mechanism_paths_for_property(
        db, state_id=SILICON_STATE_ID, property_key="band_gap", organisation_id=ORG_ID)
    assert paths, "a recorded mechanism chain should be discoverable"
    chain = paths[0]["chain"]
    assert [node["kind"] for node in chain] == [
        "material_state", "structural_feature", "mechanism", "property"]
    # Chain confidence is the weakest link, never a product or an average.
    confidences = [e["confidence"] for e in paths[0]["edges"] if e["confidence"] is not None]
    assert paths[0]["weakest_confidence"] == min(confidences)


def test_absent_mechanism_returns_empty_not_invented(db):
    paths = mechanism_paths_for_property(
        db, state_id=SILICON_STATE_ID, property_key="a_property_with_no_recorded_mechanism",
        organisation_id=ORG_ID)
    assert paths == []


def test_graph_edges_are_tenant_scoped(db):
    paths = mechanism_paths_for_property(
        db, state_id=SILICON_STATE_ID, property_key="band_gap", organisation_id=OTHER_ORG)
    assert paths == [], "another organisation's declared relationships must not be traversable"


# --- candidate reasoning ------------------------------------------------------------------------
def test_absent_evidence_stays_unknown(db):
    """Silicon has no seeded property values. Every requirement must say so plainly."""
    result = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    statuses = {r["status"] for r in result["requirement_results"]}
    assert statuses == {RequirementStatus.UNKNOWN}
    assert result["overall_status"] == RequirementStatus.INSUFFICIENT_EVIDENCE
    assert RequirementStatus.PASS not in statuses
    assert RequirementStatus.FAIL not in statuses
    for gap in result["evidence_gaps"]:
        assert gap["what_would_resolve_it"]


def test_pass_and_fail_are_discriminated(db):
    result = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    by_key = {r["requirement_key"]: r for r in result["requirement_results"]}
    assert by_key["min_band_gap"]["status"] == RequirementStatus.PASS
    assert by_key["min_thermal_conductivity"]["status"] == RequirementStatus.FAIL
    # An objective is ranked, not passed: reporting PASS would invent a threshold nobody set.
    assert by_key["maximise_electron_mobility"]["status"] == RequirementStatus.PARTIAL
    # A requirement with no evidence stays UNKNOWN even when other requirements have data.
    assert by_key["min_breakdown_field"]["status"] == RequirementStatus.UNKNOWN


def test_hard_constraint_failure_drives_the_overall_status(db):
    definition = db.query(MaterialPropertyDefinition).filter_by(key="band_gap").one()
    evidence = db.query(Evidence).first()
    # A band gap of 0.1 eV fails the hard 1.0 eV minimum.
    db.add(MaterialPropertyObservation(
        material_id=DEMO_CANDIDATE_ID, property_definition_id=definition.id, value_type="numeric",
        numeric_value=0.1, unit="eV", evidence_id=evidence.id, method="synthetic conflict fixture",
        status="active",
    ))
    db.flush()
    result = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    band_gap = next(r for r in result["requirement_results"] if r["requirement_key"] == "min_band_gap")
    # Two observations now disagree about whether the requirement is met.
    assert band_gap["status"] == RequirementStatus.CONFLICTING_EVIDENCE
    assert result["overall_status"] == RequirementStatus.CONFLICTING_EVIDENCE
    db.rollback()


def test_origins_are_reported_separately_and_never_averaged(db):
    result = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    band_gap = next(r for r in result["requirement_results"] if r["requirement_key"] == "min_band_gap")
    assert band_gap["governing_origin"] == "observed"
    assert "origin_counts" in band_gap
    # Every contributing value is listed individually with its own origin.
    assert all("origin" in v for v in band_gap["values"])
    assert "not merged into it" in band_gap["origin_note"]
    assert "never averaged together" in result["origin_separation_note"]


def test_out_of_domain_predictions_are_shown_but_not_used(db):
    """A model that says it does not apply here is not evidence about this candidate."""
    from app.services.reasoning import _prediction_values

    values = _prediction_values(
        db, target_kind="known_material", target_id=sid("material:demo-polymer-baseline"),
        property_definition_id=db.query(MaterialPropertyDefinition).filter_by(
            key="tensile_strength").one().id,
    )
    for value in values:
        if value.detail and "OUTSIDE" in value.detail:
            assert value.is_usable is False


def test_state_mismatch_blocks_property_reuse(db):
    """A value recorded in a demonstrably different state must not satisfy a requirement."""
    definition = db.query(MaterialPropertyDefinition).filter_by(key="breakdown_field").one()
    requirement = db.query(FunctionalRequirement).filter_by(key="min_breakdown_field").one()
    required_state = db.get(MaterialState, SILICON_STATE_ID)

    hot_state = create_material_state(
        db, organisation_id=ORG_ID, material_id=SILICON_ID, label="silicon at 900 K",
        composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}],
        representation_id=required_state.representation_id, space_group_number=227,
        polymorph="diamond_cubic", temperature_k=900.0,
    )
    evidence = db.query(Evidence).first()
    observation = MaterialPropertyObservation(
        material_id=SILICON_ID, property_definition_id=definition.id, value_type="numeric",
        numeric_value=5.0, unit="MV/cm", evidence_id=evidence.id, method="synthetic state fixture",
        status="active",
    )
    # Attach the observation to the hot state so the mismatch is demonstrable rather than unknown.
    observation.material_state_id = hot_state.id  # type: ignore[attr-defined]
    db.add(observation)
    db.flush()

    result = evaluate_requirement(
        db, requirement=requirement, target_kind="known_material", target_id=SILICON_ID,
        required_state=required_state, states_by_id={hot_state.id: hot_state},
    )
    # 5.0 MV/cm would comfortably pass the 0.3 MV/cm minimum if the state were ignored.
    assert result["status"] != RequirementStatus.PASS
    db.rollback()


def test_assumptions_are_stated_explicitly(db):
    result = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID)
    assert result["assumptions"], "assumptions must be surfaced rather than buried"
    assert any("not state-qualified" in a for a in result["assumptions"])


def test_reasoning_is_deterministic_and_structured_first(db):
    first = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    second = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material", target_id=SILICON_ID)
    assert first["reasoning_checksum"] == second["reasoning_checksum"]
    assert "cannot change a PASS, FAIL or UNKNOWN" in first["structured_first_note"]


def test_reasoning_result_supersedes_without_rewriting(db):
    first = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    first_id = first["reasoning_result_id"]
    original_status = db.get(CandidateReasoningResult, first_id).overall_status

    second = reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    db.expire_all()

    historical = db.get(CandidateReasoningResult, first_id)
    assert historical.overall_status == original_status
    assert historical.superseded_by_id == second["reasoning_result_id"]


def test_reasoning_records_no_scientific_values(db):
    observations = db.query(MaterialPropertyObservation).count()
    reason_about_candidate(
        db, organisation_id=ORG_ID, role_id=ROLE_ID, target_kind="known_material",
        target_id=DEMO_CANDIDATE_ID, persist=True)
    db.commit()
    assert db.query(MaterialPropertyObservation).count() == observations


def test_engine_contains_no_domain_specific_branching():
    """The engine must be generic: no branch on a material, application or domain name."""
    import pathlib

    for module in ("app/services/reasoning.py", "app/services/material_states.py"):
        source = pathlib.Path(module).read_text().lower()
        for forbidden in ("== \"silicon\"", "== 'silicon'", "semiconductor\" ==", "if material ==",
                          "== \"power_electronic", "material_id ==  \"si"):
            assert forbidden not in source, f"{module} contains domain-specific branching: {forbidden}"


# --- API ----------------------------------------------------------------------------------------
def test_decomposition_endpoint_is_tenant_scoped(client):
    assert client.get(f"/reasoning/roles/{ROLE_ID}/decomposition", headers=HOSTILE_HEADERS).status_code == 404
    assert client.get(f"/reasoning/roles/{ROLE_ID}/decomposition", headers=HEADERS).status_code == 200


def test_state_comparison_endpoint_explains_itself(client):
    response = client.get(
        f"/reasoning/material-states/{SILICON_STATE_ID}/compare/{DEMO_STATE_ID}", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["match_quality"] == StateMatchQuality.DIFFERENT_STATE
    assert body["usable"] is False
    assert body["reasons"]
    assert "not a shared structure" in body["note"]


def test_candidate_reasoning_endpoint_persists_only_on_request(client, db):
    before = db.query(CandidateReasoningResult).count()
    response = client.post("/reasoning/candidate", headers=HEADERS, json={
        "role_id": ROLE_ID, "target_kind": "known_material", "target_id": SILICON_ID, "persist": False,
    })
    assert response.status_code == 200
    db.expire_all()
    assert db.query(CandidateReasoningResult).count() == before
    assert response.json()["overall_status"] == RequirementStatus.INSUFFICIENT_EVIDENCE
