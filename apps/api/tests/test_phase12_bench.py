"""Phase 12 — intake bench.

These tests are written around the two failures Phase 12 exists to fix:

  1. Materials could not be created through any user-facing path.
  2. Every lab was gated on an active search space that no screen could produce, so a project
     created through the wizard reached a permanently disabled Virtual Experiment Lab.

The provenance tests matter at least as much as the workflow ones. Making a system easy to put data
into is exactly the change most likely to erode the evidence hierarchy underneath it, so the grade
ceiling and the boolean-gate rule are asserted explicitly rather than assumed.
"""

from __future__ import annotations

import uuid

import pytest

from app.db.session import SessionLocal
from app.models.entities import (
    Constraint,
    Evidence,
    Material,
    MaterialPropertyObservation,
    Objective,
)
from app.services.bench.catalog import CATALOGUE_BY_KEY, plausibility, resolve_property_key
from app.services.bench.intake import GRADES_BY_KEY
from app.services.bench.library import STARTER_LIBRARY


def _ctx(client):
    ctx = client.get("/demo-context").json()
    # Phase-3+ resources are organisation-scoped: search spaces, generation runs and virtual
    # campaigns all 404 without this header. That is by design server-side, but it means a web
    # deployment with NEXT_PUBLIC_ORGANISATION_ID unset sees every lab return "not found" — which
    # is a second, independent cause of the labs appearing broken.
    client.headers["X-Organisation-ID"] = ctx["organisation_id"]
    return ctx


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------------------------

def test_property_catalogue_is_grouped_and_documented(client):
    body = client.get("/bench/property-catalogue").json()
    assert body["property_count"] > 50
    domains = {d["key"] for d in body["domains"]}
    assert {"mechanical", "thermal", "electrical", "regulatory", "commercial"} <= domains
    for domain in body["domains"]:
        for prop in domain["properties"]:
            # Every property must justify its own existence to the user. A catalogue entry that
            # cannot say why an engineer would record it is noise in a form that is already long.
            assert prop["why_it_matters"], prop["key"]
            assert prop["direction"] in {"higher_is_better", "lower_is_better", "target_band", "neutral"}


def test_every_catalogue_unit_is_dimensionally_valid():
    """A catalogue entry offering a unit the unit service rejects would be a trap in the UI."""
    from app.services.units import UnitError, validate_property_unit

    for spec in CATALOGUE_BY_KEY.values():
        if spec.quantity_type == "boolean":
            assert spec.canonical_unit is None
            continue
        assert spec.canonical_unit, spec.key
        for unit in spec.accepted_units:
            try:
                validate_property_unit(spec.key, unit, spec.canonical_unit)
            except UnitError as exc:  # pragma: no cover - failure path is the assertion
                pytest.fail(f"{spec.key}: unit {unit} rejected — {exc}")


def test_datasheet_aliases_resolve():
    assert resolve_property_key("UTS") == "tensile_strength"
    assert resolve_property_key("Young's Modulus") == "tensile_modulus"
    assert resolve_property_key("HDT A") == "heat_deflection_temperature_1_8mpa"
    assert resolve_property_key("CTE") == "coefficient_thermal_expansion"
    # An unrecognised label returns nothing rather than a plausible-looking guess.
    assert resolve_property_key("sparkle factor") is None


def test_plausibility_warns_without_blocking():
    assert plausibility("density", 1360.0, "polymer") is None
    flag = plausibility("density", 99000.0, "polymer")
    assert flag is not None and flag["severity"] == "warning"


# ---------------------------------------------------------------------------------------------
# Material intake
# ---------------------------------------------------------------------------------------------

def test_material_intake_creates_material_composition_and_observations(client):
    name = _unique("Bench PA66-GF35")
    response = client.post("/bench/materials", json={
        "display_name": name,
        "material_family": "polymer",
        "data_grade": "supplier_datasheet",
        "supplier": "Test Polymers Ltd",
        "grade_code": "TP-6635",
        "source_reference": "Datasheet rev C, 2026-01",
        "description": "Intake smoke test grade.",
        "identifiers": [{"namespace": "iso1043", "value": _unique("PA66-GF35"), "is_primary": True}],
        "components": [
            {"component_name": "Polyamide 66", "component_role": "matrix", "amount_value": 65.0, "amount_unit": "%"},
            {"component_name": "E-glass fibre", "component_role": "reinforcement", "amount_value": 35.0, "amount_unit": "%"},
        ],
        "process_state": {"state_label": "Injection moulded, dry as moulded"},
        "properties": [
            {"property_key": "density", "value": 1410.0, "unit": "kg/m^3"},
            {"property_key": "tensile_strength", "value": 195.0, "unit": "MPa"},
            {"property_key": "continuous_service_temperature", "value": 125.0, "unit": "degC"},
            {"property_key": "reach_svhc_present", "boolean_value": False},
        ],
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["observation_count"] == 4

    detail = client.get(f"/materials/{body['material_id']}").json()
    assert len(detail["components"]) == 2
    assert len(detail["process_states"]) == 1
    assert {o["property_definition"]["key"] for o in detail["observations"]} == {
        "density", "tensile_strength", "continuous_service_temperature", "reach_svhc_present",
    }
    # The material is immediately visible in the explorer the user is looking at.
    explorer = client.get(f"/material-explorer?q={name.split()[-1]}").json()
    assert any(m["id"] == body["material_id"] for m in explorer)


def test_intake_records_units_in_datasheet_form_and_converts_nothing_silently(client):
    """A user types g/cm^3 because that is what the datasheet says. It must be stored as given."""
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench density units"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "properties": [{"property_key": "density", "value": 1.41, "unit": "g/cm^3"}],
    })
    assert response.status_code == 201, response.text
    detail = client.get(f"/materials/{response.json()['material_id']}").json()
    observation = detail["observations"][0]
    assert observation["unit"] == "g/cm^3"
    assert observation["numeric_value"] == pytest.approx(1.41)


def test_data_grade_sets_confidence_and_cannot_be_inflated_by_the_request(client):
    """Provenance strength is a property of the source, not a field the caller may assert."""
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench estimate grade"),
        "material_family": "polymer",
        "data_grade": "engineering_estimate",
        "properties": [{"property_key": "tensile_strength", "value": 70.0, "unit": "MPa"}],
    })
    assert response.status_code == 201
    detail = client.get(f"/materials/{response.json()['material_id']}").json()
    observation = detail["observations"][0]
    grade = GRADES_BY_KEY["engineering_estimate"]
    assert observation["confidence"] == pytest.approx(grade.confidence)
    assert observation["evidence"]["source_quality"] == grade.source_quality
    assert observation["evidence"]["evidence_type"] == "user_provided"
    assert observation["evidence"]["status"] == "reported"


def test_grades_claiming_external_authority_require_a_reference(client):
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench no reference"),
        "material_family": "polymer",
        "data_grade": "accredited_laboratory",
        "properties": [{"property_key": "tensile_strength", "value": 70.0, "unit": "MPa"}],
    })
    assert response.status_code == 422
    assert "source reference" in response.json()["detail"].lower()


def test_intake_rejects_a_dimensionally_wrong_unit(client):
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench bad unit"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "properties": [{"property_key": "tensile_strength", "value": 100.0, "unit": "kg/m^3"}],
    })
    assert response.status_code == 422


def test_intake_warns_but_still_stores_an_implausible_value(client):
    """A handbook range must not be able to veto a real measurement."""
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench implausible"),
        "material_family": "polymer",
        "data_grade": "internal_measurement",
        "properties": [{"property_key": "tensile_strength", "value": 4200.0, "unit": "MPa"}],
    })
    assert response.status_code == 201
    body = response.json()
    assert body["observation_count"] == 1
    assert any(w["code"] == "VALUE_OUTSIDE_TYPICAL_RANGE" for w in body["warnings"])


def test_duplicate_canonical_name_is_reported_actionably(client):
    payload = {
        "display_name": "Bench duplicate probe",
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "canonical_name": _unique("bench-duplicate"),
        "properties": [{"property_key": "density", "value": 1200.0, "unit": "kg/m^3"}],
    }
    assert client.post("/bench/materials", json=payload).status_code == 201
    second = client.post("/bench/materials", json=payload)
    assert second.status_code == 422
    assert "already exists" in second.json()["detail"]


def test_appending_a_second_source_preserves_the_first_and_surfaces_the_conflict(client):
    """Supplier says 180 MPa, our rig says 150. Both are kept; the disagreement is the finding."""
    created = client.post("/bench/materials", json={
        "display_name": _unique("Bench conflict"),
        "material_family": "polymer",
        "data_grade": "supplier_datasheet",
        "source_reference": "Datasheet rev A",
        "properties": [{"property_key": "tensile_strength", "value": 180.0, "unit": "MPa"}],
    })
    material_id = created.json()["material_id"]

    appended = client.post(f"/bench/materials/{material_id}/properties", json={
        "data_grade": "internal_measurement",
        "method": "ISO 527, 5 specimens",
        "properties": [{"property_key": "tensile_strength", "value": 150.0, "unit": "MPa"}],
    })
    assert appended.status_code == 201, appended.text
    assert appended.json()["evidence_id"] != created.json()["evidence_id"]

    detail = client.get(f"/materials/{material_id}").json()
    values = sorted(o["numeric_value"] for o in detail["observations"])
    assert values == [150.0, 180.0]

    conflicts = client.get(f"/materials/{material_id}/conflicts").json()
    assert conflicts, "a 20% disagreement between two sources must be reported, not averaged away"


def test_unknown_property_key_is_refused_rather_than_invented(client):
    response = client.post("/bench/materials", json={
        "display_name": _unique("Bench unknown property"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "properties": [{"property_key": "vibe_index", "value": 7.0, "unit": "1"}],
    })
    assert response.status_code == 422
    assert "vibe_index" in response.json()["detail"]


# ---------------------------------------------------------------------------------------------
# Reference library
# ---------------------------------------------------------------------------------------------

def test_reference_library_installs_idempotently(client):
    first = client.post("/bench/install-reference-library", json={}).json()
    assert first["installed_count"] + first["skipped_count"] == len(STARTER_LIBRARY)
    second = client.post("/bench/install-reference-library", json={}).json()
    assert second["installed_count"] == 0
    assert second["skipped_count"] == len(STARTER_LIBRARY)


def test_library_materials_are_graded_as_handbook_typical_not_measured(client):
    client.post("/bench/install-reference-library", json={})
    session = SessionLocal()
    try:
        material = session.query(Material).filter(
            Material.canonical_name == "library::pa66-gf30"
        ).one_or_none()
        assert material is not None, "the reference library must install PA66-GF30"
        observations = session.query(MaterialPropertyObservation).filter_by(material_id=material.id).all()
        assert observations
        for observation in observations:
            evidence = session.get(Evidence, observation.evidence_id)
            assert evidence.source_quality == "handbook_typical"
            assert evidence.status == "reported"
            assert observation.confidence <= 0.6
    finally:
        session.close()


def test_library_covers_more_than_one_material_family(client):
    families = {m.family for m in STARTER_LIBRARY}
    assert {"polymer", "alloy", "ceramic", "composite"} <= families


def test_library_carries_a_regulatory_incumbent_for_realistic_studies():
    """A replacement platform with no restricted incumbent has nothing to demonstrate."""
    brass = next(m for m in STARTER_LIBRARY if m.key == "brass-cuzn39pb3")
    assert brass.properties["reach_svhc_present"][0] is True
    ptfe = next(m for m in STARTER_LIBRARY if m.key == "ptfe")
    assert ptfe.properties["pfas_present"][0] is True


# ---------------------------------------------------------------------------------------------
# Search space derivation — the fix for the dead labs
# ---------------------------------------------------------------------------------------------

def _library_material_id(client, canonical: str) -> str:
    client.post("/bench/install-reference-library", json={})
    session = SessionLocal()
    try:
        return session.query(Material).filter(Material.canonical_name == canonical).one().id
    finally:
        session.close()


def test_study_creation_produces_an_active_search_space(client):
    """The regression test for the whole phase: a new study must reach its labs usable."""
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    response = client.post("/bench/studies", json={
        "name": _unique("Under-hood bracket"),
        "baseline_material_id": baseline,
        "drivers": ["cost", "supply_risk"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"],
        "created_by": ctx["user_id"],
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requirement_count"] >= 8
    assert body["objective_count"] >= 2
    assert body["search_space_created"] is True
    assert body["search_space_activated"] is True

    spaces = client.get(f"/replacement-projects/{body['project_id']}/search-spaces").json()
    assert any(s["active"] for s in spaces)


def test_derived_space_is_valid_against_the_existing_validator(client):
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pbt-gf30")
    project_id = client.post("/bench/studies", json={
        "name": _unique("PBT study"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"],
        "created_by": ctx["user_id"],
    }).json()["project_id"]

    space = next(s for s in client.get(f"/replacement-projects/{project_id}/search-spaces").json() if s["active"])
    validation = client.post(
        f"/replacement-projects/{project_id}/search-spaces/{space['id']}/validate"
        "?strategy_key=bounded_composition_variation"
    ).json()
    assert validation["valid"] is True, validation["issues"]
    assert validation["estimated_cardinality"] > 0


def test_generation_actually_runs_on_a_derived_space(client):
    """Derivation is only worth anything if the downstream generator accepts the result."""
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa6-gf30")
    project_id = client.post("/bench/studies", json={
        "name": _unique("Generation on derived space"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"],
        "created_by": ctx["user_id"],
    }).json()["project_id"]

    space = next(s for s in client.get(f"/replacement-projects/{project_id}/search-spaces").json() if s["active"])
    preview = client.post(f"/replacement-projects/{project_id}/generation-runs/preview", json={
        "search_space_id": space["id"], "strategy_key": "bounded_composition_variation",
        "random_seed": 42, "candidate_budget": 10, "configuration": {"source": "test"},
    }).json()
    assert preview["valid"] is True, preview["issues"]

    run = client.post(f"/replacement-projects/{project_id}/generation-runs", json={
        "search_space_id": space["id"], "strategy_key": "bounded_composition_variation",
        "random_seed": 42, "candidate_budget": 10, "configuration": {"source": "test"},
        "created_by": ctx["user_id"],
    })
    assert run.status_code == 201, run.text
    assert run.json()["accepted_count"] > 0


def test_derivation_explains_itself_when_the_baseline_has_no_composition(client):
    ctx = _ctx(client)
    bare = client.post("/bench/materials", json={
        "display_name": _unique("Bench bare baseline"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "properties": [{"property_key": "density", "value": 1200.0, "unit": "kg/m^3"}],
    }).json()["material_id"]

    study = client.post("/bench/studies", json={
        "name": _unique("Bare baseline study"),
        "baseline_material_id": bare,
        "drivers": ["cost"],
        "requirements": [{"property_key": "density", "comparator": "<=", "target_value": 1300.0,
                          "target_unit": "kg/m^3"}],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()
    assert study["search_space_created"] is False
    assert study["notes"], "the user must be told why no space was derived"

    preview = client.get(f"/replacement-projects/{study['project_id']}/search-space-derivation").json()
    assert preview["derivable"] is False
    blocker = preview["blockers"][0]
    assert blocker["code"] == "NO_USABLE_BASELINE_COMPOSITION"
    assert blocker["fix"], "a blocker without a fix is just a complaint"


def test_derived_space_holds_redacted_components_fixed(client, db):
    """A composition variation must never move a component whose amount is withheld."""
    ctx = _ctx(client)
    created = client.post("/bench/materials", json={
        "display_name": _unique("Bench redacted"),
        "material_family": "polymer",
        "data_grade": "supplier_datasheet",
        "source_reference": "Confidential datasheet",
        "components": [
            {"component_name": "Base resin", "component_role": "matrix", "amount_value": 80.0, "amount_unit": "%"},
            {"component_name": "Filler", "component_role": "filler", "amount_value": 15.0, "amount_unit": "%"},
            {"component_name": "Proprietary additive package", "component_role": "additive",
             "amount_value": 5.0, "amount_unit": "%", "is_redacted": True, "redaction_label": "Withheld"},
        ],
        "properties": [{"property_key": "density", "value": 1250.0, "unit": "kg/m^3"}],
    }).json()

    project_id = client.post("/bench/studies", json={
        "name": _unique("Redacted study"),
        "baseline_material_id": created["material_id"],
        "drivers": ["cost"],
        "requirements": [{"property_key": "density", "comparator": "<=", "target_value": 1300.0,
                          "target_unit": "kg/m^3"}],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    space = next(s for s in client.get(f"/replacement-projects/{project_id}/search-spaces").json() if s["active"])
    redacted_rule = next(r for r in space["component_rules"] if "Proprietary" in r["display_name"])
    assert redacted_rule["mutable"] is False
    assert redacted_rule["locked"] is True
    assert any(r["mutable"] for r in space["component_rules"])


# ---------------------------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------------------------

def test_baseline_derived_requirements_use_the_right_direction(client):
    baseline = _library_material_id(client, "library::pa66-gf30")
    derived = client.get(f"/bench/materials/{baseline}/derived-requirements?margin=0.05").json()
    by_key = {r["property_key"]: r for r in derived["requirements"]}
    # Strength is a floor; cost and density are ceilings. Getting this backwards would silently
    # invert the study.
    assert by_key["tensile_strength"]["comparator"] == ">="
    assert by_key["tensile_strength"]["target_value"] < 180.0
    assert by_key["cost_per_mass"]["comparator"] == "<="
    assert by_key["density"]["comparator"] == "<="
    assert all(r["origin"] == "baseline_derived" for r in derived["requirements"])


def test_baseline_derivation_declines_direction_free_properties(client):
    """Thermal conductivity has no universally better direction, so no threshold may be invented."""
    baseline = _library_material_id(client, "library::pa66-gf30")
    derived = client.get(f"/bench/materials/{baseline}/derived-requirements").json()
    keys = {r["property_key"] for r in derived["requirements"]}
    assert "thermal_conductivity" not in keys
    assert any(s["property_key"] == "thermal_conductivity" for s in derived["skipped"])


def test_compliance_booleans_are_gates_and_never_objectives(client):
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    study = client.post("/bench/studies", json={
        "name": _unique("Boolean objective probe"),
        "baseline_material_id": baseline,
        "drivers": ["regulation"],
        "requirements": [{"property_key": "reach_svhc_present", "comparator": "boolean",
                          "target_boolean": False}],
        "objectives": [{"property_key": "reach_svhc_present", "direction": "minimize"}],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()
    assert study["objective_count"] == 0
    reason = study["rejected_requirements"][0]["reason"]
    assert "gate" in reason.lower()


def test_preset_requirements_persist_with_their_origin_and_rationale(client, db):
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    project_id = client.post("/bench/studies", json={
        "name": _unique("Preset provenance"),
        "baseline_material_id": baseline,
        "drivers": ["regulation"],
        "preset_key": "ev_battery_pack_component",
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    session = SessionLocal()
    try:
        constraints = session.query(Constraint).filter_by(project_id=project_id).all()
        assert constraints
        for constraint in constraints:
            assert constraint.description, "every templated requirement must state why it exists"
            assert constraint.metadata_json.get("origin") == "application_preset"
            assert constraint.metadata_json.get("preset_key") == "ev_battery_pack_component"
        assert session.query(Objective).filter_by(project_id=project_id).count() >= 2
    finally:
        session.close()


def test_every_preset_creates_a_working_study(client):
    """A preset that cannot be instantiated is worse than no preset at all."""
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    presets = client.get("/bench/application-presets").json()
    assert len(presets) >= 8
    for preset in presets:
        response = client.post("/bench/studies", json={
            "name": _unique(f"preset-{preset['key']}"),
            "baseline_material_id": baseline,
            "drivers": list(preset["typical_drivers"])[:2] or ["cost"],
            "preset_key": preset["key"],
            "derive_space": False,
            "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
        })
        assert response.status_code == 201, f"{preset['key']}: {response.text}"
        body = response.json()
        assert body["requirement_count"] > 0, preset["key"]
        assert not body["rejected_requirements"], f"{preset['key']}: {body['rejected_requirements']}"


def test_preset_family_mismatch_is_flagged_not_silently_accepted(client):
    ctx = _ctx(client)
    aluminium = _library_material_id(client, "library::al-6061-t6")
    body = client.post("/bench/studies", json={
        "name": _unique("Family mismatch"),
        "baseline_material_id": aluminium,
        "drivers": ["weight"],
        "preset_key": "automotive_underhood_polymer",
        "derive_space": False,
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()
    assert any("polymer" in note for note in body["notes"])


# ---------------------------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------------------------

def test_project_readiness_reports_every_lab_with_an_actionable_fix(client):
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    project_id = client.post("/bench/studies", json={
        "name": _unique("Readiness study"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    readiness = client.get(f"/replacement-projects/{project_id}/readiness").json()
    lab_keys = {lab["key"] for lab in readiness["labs"]}
    assert {"candidate_lab", "prediction_lab", "virtual_lab", "simulation_lab",
            "replacement_decision"} == lab_keys

    candidate_lab = next(lab for lab in readiness["labs"] if lab["key"] == "candidate_lab")
    assert any(c["code"] == "SEARCH_SPACE_ACTIVE" and c["status"] == "ok" for c in candidate_lab["checks"])

    # Every blocker anywhere must carry a fix the UI can render as a button.
    for lab in readiness["labs"]:
        for check in lab["checks"]:
            if check["status"] == "blocked":
                assert check["fix"], f"{lab['key']}/{check['code']} blocks with no route out"
                assert check["fix"].get("href") or check["fix"].get("endpoint")


def test_readiness_names_the_missing_search_space_as_the_blocker(client):
    """The exact condition that made the Virtual Experiment Lab look broken."""
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pa66-gf30")
    project_id = client.post("/bench/studies", json={
        "name": _unique("No space study"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "derive_space": False,
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    readiness = client.get(f"/replacement-projects/{project_id}/readiness").json()
    virtual = next(lab for lab in readiness["labs"] if lab["key"] == "virtual_lab")
    assert virtual["status"] == "blocked"
    blocker = next(c for c in virtual["checks"] if c["code"] == "SEARCH_SPACE_DERIVABLE")
    assert blocker["fix"]["method"] == "POST"
    assert readiness["next_action"] is not None

    # And the offered fix genuinely resolves it.
    fixed = client.post(blocker["fix"]["endpoint"])
    assert fixed.status_code == 201, fixed.text
    after = client.get(f"/replacement-projects/{project_id}/readiness").json()
    after_virtual = next(lab for lab in after["labs"] if lab["key"] == "virtual_lab")
    assert not any(c["code"].startswith("SEARCH_SPACE_") and c["status"] == "blocked"
                   for c in after_virtual["checks"])


def test_readiness_flags_baseline_property_gaps_against_requirements(client):
    ctx = _ctx(client)
    thin = client.post("/bench/materials", json={
        "display_name": _unique("Bench thin baseline"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "components": [
            {"component_name": "Resin", "component_role": "matrix", "amount_value": 90.0, "amount_unit": "%"},
            {"component_name": "Filler", "component_role": "filler", "amount_value": 10.0, "amount_unit": "%"},
        ],
        "properties": [{"property_key": "density", "value": 1200.0, "unit": "kg/m^3"}],
    }).json()["material_id"]

    project_id = client.post("/bench/studies", json={
        "name": _unique("Gap study"),
        "baseline_material_id": thin,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    readiness = client.get(f"/replacement-projects/{project_id}/readiness").json()
    checks = {c["code"]: c for lab in readiness["labs"] for c in lab["checks"]}
    gap = checks["BASELINE_PARTIAL_COVERAGE"]
    assert gap["status"] == "warning"
    assert "tensile_strength" in gap["evidence"]["missing_property_keys"]


def test_platform_readiness_offers_library_install_when_empty(client):
    body = client.get("/bench/readiness").json()
    assert body["status"] in {"ok", "warning", "blocked"}
    assert any(c["code"] == "MATERIALS_AVAILABLE" for c in body["checks"])


def test_readiness_404s_for_an_unknown_project(client):
    assert client.get(f"/replacement-projects/{uuid.uuid4()}/readiness").status_code == 404


# ---------------------------------------------------------------------------------------------
# Non-regression: Phase 12 must not touch the decision path
# ---------------------------------------------------------------------------------------------

def test_bench_creates_no_predictions_simulations_or_verdicts(client):
    """The bench builds inputs. If it ever starts producing values, the moat is gone."""
    created = client.post("/bench/materials", json={
        "display_name": _unique("Bench isolation"),
        "material_family": "polymer",
        "data_grade": "internal_measurement",
        "properties": [{"property_key": "density", "value": 1150.0, "unit": "kg/m^3"}],
    }).json()

    detail = client.get(f"/materials/{created['material_id']}").json()
    for observation in detail["observations"]:
        # Never predicted, never computational — an intake value is reported evidence and nothing else.
        assert observation["evidence"]["evidence_type"] not in {"predicted", "computational"}


def test_search_space_derivation_is_deterministic(client):
    ctx = _ctx(client)
    baseline = _library_material_id(client, "library::pp-td20")
    project_id = client.post("/bench/studies", json={
        "name": _unique("Determinism"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "requirements": [{"property_key": "density", "comparator": "<=", "target_value": 1100.0,
                          "target_unit": "kg/m^3"}],
        "derive_space": False,
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    first = client.post(f"/replacement-projects/{project_id}/search-space-derivation?activate=false").json()
    second = client.post(f"/replacement-projects/{project_id}/search-space-derivation?activate=false").json()

    def shape(space):
        return [
            (r["component_key"], r["mutable"], r["locked"], r["min_amount"], r["max_amount"], r["step_amount"])
            for r in sorted(space["component_rules"], key=lambda r: r["sequence"])
        ]

    # The checksum legitimately differs because it covers the version, but the derived content must
    # be identical: derivation reads only the baseline composition and family defaults.
    assert shape(first["search_space"]) == shape(second["search_space"])
    assert first["search_space"]["balance_component_key"] == second["search_space"]["balance_component_key"]
    assert first["search_space"]["version"] != second["search_space"]["version"]
