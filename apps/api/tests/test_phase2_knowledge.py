from pydantic import ValidationError

from app.db.seed import sid
from app.schemas.materials import ConditionSetCreate, MaterialComponentCreate
from app.services.conditions import validate_condition_values
from app.services.conflicts import detect_conflicts
from app.services.identity import normalize_identifier, resolve_identity
from app.services.selection import select_observation
from app.services.units import UnitError


def test_identifier_normalization_and_exact_resolution(db):
    assert normalize_identifier("CAS", " 50-00-0 ") == "50-00-0"
    result = resolve_identity(
        db,
        canonical_name=None,
        identifiers=[{"namespace": "tinkerlab", "value": "TL-DEMO-P100"}],
        composition=[],
        organisation_id=sid("org"),
    )
    assert result["match_class"] == "exact"
    assert result["selected_material_id"] == sid("material:demo-polymer-baseline")


def test_redacted_and_quantitative_composition_validation():
    redacted = MaterialComponentCreate(component_name="Private", is_redacted=True, redaction_label="PRIVATE-X")
    assert redacted.is_redacted is True
    quantitative = MaterialComponentCreate(component_name="Matrix", amount_value=80, amount_unit="%", amount_basis="weight_percent")
    assert quantitative.amount_value == 80
    try:
        MaterialComponentCreate(component_name="Broken", amount_basis="weight_percent")
    except ValidationError:
        pass
    else:
        raise AssertionError("quantitative component without amount must be rejected")


def test_condition_units_are_validated():
    valid = ConditionSetCreate(temperature_value=25, temperature_unit="degC", pressure_value=1, pressure_unit="kPa")
    validate_condition_values(valid)
    invalid = ConditionSetCreate(temperature_value=25, temperature_unit="MPa")
    try:
        validate_condition_values(invalid)
    except UnitError:
        pass
    else:
        raise AssertionError("pressure unit must not be accepted as temperature")


def test_selection_prefers_exact_condition_and_excludes_mismatch(db):
    result = select_observation(
        db,
        sid("material:demo-polymer-a"),
        "tensile_strength",
        requested_context={"temperature": {"value": 23.0, "unit": "degC"}, "material_state": "conditioned molded specimen"},
    )
    assert result["selected"]["numeric_value"] == 74.0
    assert result["selected"]["applicability"] == "exact"
    assert any("condition differs" in x["reason"] for x in result["excluded"])


def test_superseded_evidence_is_excluded(db):
    result = select_observation(db, sid("material:demo-polymer-a"), "cost_per_mass")
    assert result["selected"]["numeric_value"] == 4.7
    assert any("evidence status is superseded" in x["reason"] for x in result["excluded"])


def test_conflict_policy_preserves_disagreement_and_curator_preference(db):
    conflicts = detect_conflicts(db, sid("material:demo-polymer-b"), "density")
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["policy"] == "relative"
    assert conflict["resolution_state"] == "curator_preferred"
    assert len(conflict["observation_ids"]) == 2


def test_curator_preference_changes_tied_selection(db):
    # Candidate B's two density values are equally applicable; seeded curator preference selects 1380.
    selected = select_observation(db, sid("material:demo-polymer-b"), "density")
    assert selected["selected"]["numeric_value"] == 1380.0
    assert selected["selected"]["curator_preferred"] is True


def test_unknown_when_no_observation_exists(db):
    result = select_observation(db, sid("material:demo-polymer-c"), "operating_temperature")
    assert result["selected"] is None
    assert result["unknown_reason"] == "no applicable active observation"
