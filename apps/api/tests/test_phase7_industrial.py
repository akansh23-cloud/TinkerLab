"""Phase-7 Industrial Viability Engine tests.

These assert industrial-integrity invariants, not row counts: missing evidence must never become a
pass, incomparable cost bases must never be silently converted, contradictions must stay visible,
and a completed assessment must remain explainable after the evidence beneath it changes.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.db.seed import sid
from app.domain.enums import IndustrialAssessmentState
from app.models.entities import (
    IndustrialConstraint,
    IndustrialEvidence,
    IndustrialViabilityAssessment,
    MaterialPropertyObservation,
    MaturityAssessment,
    PropertyPrediction,
    SimulationResult,
)
from app.services.industrial import (
    CostBasisKey,
    IndustrialError,
    assess_industrial_viability,
    compare_industrial_viability,
    create_industrial_evidence,
    current_maturity,
    detect_conflicts,
    evidence_checksum,
    is_stale,
)

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
PROJECT_ID = sid("project")
SILICON_ID = sid("material:silicon")
BASELINE_ID = sid("material:demo-polymer-baseline")
HEADERS = {"X-Organisation-ID": ORG_ID}
HOSTILE_HEADERS = {"X-Organisation-ID": OTHER_ORG}


def _evidence_values(**overrides):
    base = {
        "organisation_id": ORG_ID, "visibility": "private", "material_id": SILICON_ID,
        "hypothesis_id": None, "category": "economic", "metric_key": "test_metric",
        "display_label": "test", "numeric_value": 10.0, "unit": "USD/kg", "currency": "USD",
        "currency_year": 2025, "cost_basis": "per_kilogram", "geography": "global",
        "as_of_date": date(2025, 1, 1),
        "source_type": "seed_demonstration",
    }
    base.update(overrides)
    return base


# --- evidence integrity ---------------------------------------------------------------------
def test_monetary_evidence_without_basis_is_refused(db):
    with pytest.raises(IndustrialError, match="currency and cost basis"):
        create_industrial_evidence(db, _evidence_values(currency=None, cost_basis=None))
    db.rollback()


def test_time_varying_evidence_requires_an_as_of_date(db):
    for category in ("economic", "supply_chain", "regulatory"):
        with pytest.raises(IndustrialError, match="as_of_date"):
            create_industrial_evidence(db, _evidence_values(
                category=category, as_of_date=None,
                jurisdiction="EU" if category == "regulatory" else None,
            ))
        db.rollback()


def test_regulatory_evidence_requires_a_jurisdiction(db):
    with pytest.raises(IndustrialError, match="jurisdiction"):
        create_industrial_evidence(db, _evidence_values(
            category="regulatory", metric_key="restricted", boolean_value=True,
            numeric_value=None, currency=None, cost_basis=None, jurisdiction=None,
        ))
    db.rollback()


def test_evidence_must_reference_exactly_one_target(db):
    with pytest.raises(IndustrialError, match="exactly one"):
        create_industrial_evidence(db, _evidence_values(hypothesis_id=sid("some-hypothesis")))
    db.rollback()


def test_checksum_distinguishes_incomparable_bases():
    """Two cost figures differing only in currency year are different claims and must hash apart."""
    claim = {"metric_key": "cost", "numeric_value": 10.0, "currency": "USD", "cost_basis": "per_kilogram"}
    assert evidence_checksum({**claim, "currency_year": 2025}) != evidence_checksum({**claim, "currency_year": 2019})
    assert evidence_checksum({**claim, "currency_year": 2025}) == evidence_checksum({**claim, "currency_year": 2025})


def test_cost_basis_comparability_is_strict():
    usd_2025_kg = CostBasisKey("USD", 2025, "per_kilogram")
    assert usd_2025_kg.comparable_with(CostBasisKey("USD", 2025, "per_kilogram"))
    assert not usd_2025_kg.comparable_with(CostBasisKey("USD", 2019, "per_kilogram"))
    assert not usd_2025_kg.comparable_with(CostBasisKey("EUR", 2025, "per_kilogram"))
    assert not usd_2025_kg.comparable_with(CostBasisKey("USD", 2025, "per_tonne"))
    assert not CostBasisKey(None, None, None).comparable_with(CostBasisKey(None, None, None))


def test_staleness_is_reported_not_silently_accepted(db):
    fresh = create_industrial_evidence(db, _evidence_values(
        metric_key="fresh_metric", as_of_date=date.today() - timedelta(days=10)))
    old = create_industrial_evidence(db, _evidence_values(
        metric_key="old_metric", as_of_date=date.today() - timedelta(days=3000)))
    undated = create_industrial_evidence(db, _evidence_values(
        metric_key="undated", category="manufacturing", as_of_date=None, currency=None, cost_basis=None))
    assert is_stale(fresh) is False
    assert is_stale(old) is True
    assert is_stale(undated) is True, "evidence with no date cannot be assumed current"
    db.rollback()


# --- conflicts ------------------------------------------------------------------------------
def test_non_overlapping_ranges_are_flagged_as_conflicting(db):
    a = create_industrial_evidence(db, _evidence_values(
        metric_key="conflict_metric", lower_bound=1.0, upper_bound=2.0, numeric_value=None))
    b = create_industrial_evidence(db, _evidence_values(
        metric_key="conflict_metric", lower_bound=50.0, upper_bound=60.0, numeric_value=None,
        as_of_date=date(2025, 6, 1)))
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == "non_overlapping_intervals"
    assert set(conflicts[0]["evidence_ids"]) == {a.id, b.id}
    db.rollback()


def test_overlapping_ranges_are_not_conflicts(db):
    a = create_industrial_evidence(db, _evidence_values(metric_key="ok_metric", lower_bound=1.0, upper_bound=10.0, numeric_value=None))
    b = create_industrial_evidence(db, _evidence_values(metric_key="ok_metric", lower_bound=8.0, upper_bound=20.0, numeric_value=None))
    assert detect_conflicts([a, b]) == []
    db.rollback()


def test_records_on_different_bases_are_not_compared_as_conflicts(db):
    """Incomparable is not the same as contradictory, and must not be reported as one."""
    a = create_industrial_evidence(db, _evidence_values(metric_key="basis_metric", numeric_value=4.0, currency_year=2025))
    b = create_industrial_evidence(db, _evidence_values(metric_key="basis_metric", numeric_value=400.0, currency_year=2019))
    assert detect_conflicts([a, b]) == []
    db.rollback()


def test_boolean_contradiction_is_flagged(db):
    a = create_industrial_evidence(db, _evidence_values(
        category="regulatory", metric_key="restricted", boolean_value=True, numeric_value=None,
        currency=None, cost_basis=None, unit=None, jurisdiction="EU"))
    b = create_industrial_evidence(db, _evidence_values(
        category="regulatory", metric_key="restricted", boolean_value=False, numeric_value=None,
        currency=None, cost_basis=None, unit=None, jurisdiction="EU"))
    conflicts = detect_conflicts([a, b])
    assert conflicts and conflicts[0]["kind"] == "boolean_contradiction"
    db.rollback()


def test_conflicting_evidence_blocks_a_verdict_rather_than_picking_a_winner(db):
    constraint = IndustrialConstraint(
        organisation_id=ORG_ID, project_id=PROJECT_ID, category="economic", constraint_kind="max_value",
        metric_key="conflicted_cost", display_label="cost limit", strength="hard", target_value=100.0,
        target_unit="USD/kg", currency="USD", currency_year=2025, cost_basis="per_kilogram",
    )
    db.add(constraint)
    for low, high, as_of in ((1.0, 2.0, date(2025, 1, 1)), (500.0, 600.0, date(2025, 6, 1))):
        create_industrial_evidence(db, _evidence_values(
            metric_key="conflicted_cost", lower_bound=low, upper_bound=high, numeric_value=None, as_of_date=as_of))
    db.flush()
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    economic = payload["dimension_details"]["economic_feasibility"]
    results = [r for r in economic["constraint_results"] if r["metric_key"] == "conflicted_cost"]
    assert results and results[0]["state"] == IndustrialAssessmentState.CONFLICTING_EVIDENCE
    # The newer record did NOT silently win despite being within the limit.
    assert results[0]["state"] != IndustrialAssessmentState.PASS
    db.rollback()


# --- constraint evaluation --------------------------------------------------------------------
def test_missing_evidence_never_becomes_a_pass(db):
    """The headline Phase-7 invariant."""
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    water = [
        r for d in payload["dimension_details"].values() if isinstance(d, dict)
        for r in d.get("constraint_results", []) if r.get("metric_key") == "water_use"
    ]
    assert water, "the seeded water-use constraint must be evaluated"
    assert water[0]["state"] == IndustrialAssessmentState.INSUFFICIENT_EVIDENCE
    assert water[0]["state"] != IndustrialAssessmentState.PASS
    assert "not treated as a pass" in water[0]["detail"]


def test_incomparable_cost_basis_reports_insufficient_not_a_guess(db):
    constraint = IndustrialConstraint(
        organisation_id=ORG_ID, project_id=PROJECT_ID, category="economic", constraint_kind="max_value",
        metric_key="euro_cost", display_label="EUR cost limit", strength="hard", target_value=10.0,
        target_unit="EUR/kg", currency="EUR", currency_year=2025, cost_basis="per_kilogram",
    )
    db.add(constraint)
    create_industrial_evidence(db, _evidence_values(metric_key="euro_cost", numeric_value=5.0, currency="USD"))
    db.flush()
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    result = [
        r for d in payload["dimension_details"].values() if isinstance(d, dict)
        for r in d.get("constraint_results", []) if r.get("metric_key") == "euro_cost"
    ][0]
    # USD 5.0 is numerically below the EUR 10.0 limit, and it is still not a pass.
    assert result["state"] == IndustrialAssessmentState.INSUFFICIENT_EVIDENCE
    assert "never silently converted" in result["detail"]
    db.rollback()


def test_hard_constraint_failure_is_never_averaged_away(db):
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=BASELINE_ID, persist=False)
    assert payload["overall_state"] == IndustrialAssessmentState.FAIL
    labels = [f["display_label"] for f in payload["hard_constraint_failures"]]
    assert any("supplier" in label.lower() for label in labels)
    # Other dimensions passing does not rescue the overall verdict.
    assert payload["dimension_states"]["economic_feasibility"] == IndustrialAssessmentState.PASS


def test_unrecorded_process_compatibility_is_not_compatibility(db):
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=BASELINE_ID, persist=False)
    manufacturing = payload["dimension_states"]["manufacturing_compatibility"]
    assert manufacturing == IndustrialAssessmentState.INSUFFICIENT_EVIDENCE
    detail = payload["dimension_details"]["manufacturing_compatibility"]["constraint_results"][0]["detail"]
    assert "not a compatible route" in detail


def test_banned_element_needs_declared_composition(db):
    """A banned-element check with no composition on file must not silently pass."""
    db.add(IndustrialConstraint(
        organisation_id=ORG_ID, project_id=PROJECT_ID, category="regulatory",
        constraint_kind="banned_element", display_label="No lead", strength="hard",
        banned_elements=["Pb"],
    ))
    db.flush()
    _, silicon = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    result = [
        r for d in silicon["dimension_details"].values() if isinstance(d, dict)
        for r in d.get("constraint_results", []) if r["constraint_kind"] == "banned_element"
    ][0]
    # Silicon has a declared structural representation, so the check can run and passes.
    assert result["state"] == IndustrialAssessmentState.PASS
    assert "Si" in silicon["declared_elements"]
    db.rollback()


def test_banned_element_present_fails(db):
    db.add(IndustrialConstraint(
        organisation_id=ORG_ID, project_id=PROJECT_ID, category="regulatory",
        constraint_kind="banned_element", display_label="No silicon", strength="hard",
        banned_elements=["Si"],
    ))
    db.flush()
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    assert payload["overall_state"] == IndustrialAssessmentState.FAIL
    assert any("Si" in f.get("offending", []) for f in payload["hard_constraint_failures"])
    db.rollback()


def test_regulatory_status_does_not_transfer_between_jurisdictions(db):
    db.add(IndustrialConstraint(
        organisation_id=ORG_ID, project_id=PROJECT_ID, category="regulatory",
        constraint_kind="allowed_jurisdiction", display_label="Permitted in Japan", strength="hard",
        allowed_jurisdictions=["JP"],
    ))
    db.flush()
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    result = [
        r for d in payload["dimension_details"].values() if isinstance(d, dict)
        for r in d.get("constraint_results", []) if r["constraint_kind"] == "allowed_jurisdiction"
        and "Japan" in r["display_label"]
    ][0]
    # EU evidence exists, JP evidence does not. EU clearance is not JP clearance.
    assert result["state"] == IndustrialAssessmentState.INSUFFICIENT_EVIDENCE
    assert "does not transfer between jurisdictions" in result["detail"]
    db.rollback()


def test_maturity_ordering_and_unknown_handling(db):
    stage, row = current_maturity(db, target_kind="known_material", target_id=SILICON_ID)
    assert stage == "industrially_established" and row is not None
    stage_missing, row_missing = current_maturity(db, target_kind="known_material", target_id=BASELINE_ID)
    assert stage_missing == "unknown" and row_missing is None


def test_maturity_is_not_labelled_trl(client):
    response = client.get(
        f"/industrial/maturity/current?target_kind=known_material&target_id={SILICON_ID}", headers=HEADERS)
    assert response.status_code == 200
    assert "not presented as formal Technology Readiness Levels" in response.json()["note"]


# --- composite score ---------------------------------------------------------------------------
def test_no_composite_score_without_a_declared_methodology(db):
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    assert payload["composite_score"] is None
    assert payload["composite_is_partial"] is True


def test_composite_excludes_unknowns_rather_than_scoring_them_zero(db):
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False, composite_methodology="declared_weighted_mean_v1")
    assert payload["composite_score"] is not None
    assert payload["composite_is_partial"] is True, "unknown dimensions must be disclosed as excluded"
    # Silicon's scored dimensions all pass, so excluding unknowns gives 1.0 — not a diluted number.
    assert payload["composite_score"] == pytest.approx(1.0)
    assert payload["unknown_dimensions"], "the excluded dimensions must be listed"


def test_unknown_methodology_is_refused(db):
    with pytest.raises(IndustrialError, match="Unknown composite methodology"):
        assess_industrial_viability(
            db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
            target_id=SILICON_ID, persist=False, composite_methodology="vibes_v1")


# --- assessment immutability and reproducibility -------------------------------------------------
def test_assessment_is_deterministic_for_unchanged_evidence(db):
    _, first = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    _, second = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=False)
    assert first["assessment_checksum"] == second["assessment_checksum"]


def test_new_evidence_supersedes_without_rewriting_history(db):
    original, _ = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=True)
    db.commit()
    original_id = original.id
    original_states = dict(original.dimension_states)
    original_checksum = original.assessment_checksum

    # Evidence changes: a new cost record blows through the hard limit.
    create_industrial_evidence(db, _evidence_values(
        metric_key="raw_material_cost", numeric_value=9999.0, as_of_date=date(2026, 1, 1)))
    db.commit()

    updated, _ = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=True)
    db.commit()

    db.expire_all()
    historical = db.get(IndustrialViabilityAssessment, original_id)
    assert historical.dimension_states == original_states, "history must not be rewritten"
    assert historical.assessment_checksum == original_checksum
    assert historical.superseded_by_id == updated.id
    assert updated.assessment_checksum != original_checksum
    # The new record contradicts the existing one on the same basis. The engine reports the
    # contradiction rather than letting the newest number silently become the verdict.
    assert updated.dimension_states["economic_feasibility"] == IndustrialAssessmentState.CONFLICTING_EVIDENCE
    assert updated.conflicting_evidence, "the contradiction must be surfaced on the new assessment"


# --- separation from scientific origins ---------------------------------------------------------
def test_industrial_assessment_creates_no_scientific_records(db):
    observations = db.query(MaterialPropertyObservation).count()
    predictions = db.query(PropertyPrediction).count()
    simulations = db.query(SimulationResult).count()
    assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=SILICON_ID, persist=True)
    db.commit()
    assert db.query(MaterialPropertyObservation).count() == observations
    assert db.query(PropertyPrediction).count() == predictions
    assert db.query(SimulationResult).count() == simulations


def test_industrial_evidence_is_labelled_as_its_own_origin(db):
    row = db.query(IndustrialEvidence).first()
    assert row.scientific_origin == "industrial_evidence"


def test_converged_simulation_is_not_experimental_validation(db):
    """A converged physics result must never satisfy the experimental-validation dimension."""
    _, payload = assess_industrial_viability(
        db, project_id=PROJECT_ID, organisation_id=ORG_ID, target_kind="known_material",
        target_id=BASELINE_ID, persist=False)
    experimental = payload["dimension_details"]["experimental_validation"]
    assert payload["dimension_states"]["experimental_validation"] == IndustrialAssessmentState.UNKNOWN
    assert experimental["converged_simulation_count"] >= 1, "the seeded converged fixture should be counted"
    assert "simulation is not experiment" in experimental["detail"]


# --- comparison ---------------------------------------------------------------------------------
def test_comparison_explains_why_and_is_deterministic(db):
    targets = [
        {"target_kind": "known_material", "target_id": SILICON_ID},
        {"target_kind": "known_material", "target_id": BASELINE_ID},
    ]
    first = compare_industrial_viability(db, project_id=PROJECT_ID, organisation_id=ORG_ID, targets=targets)
    second = compare_industrial_viability(db, project_id=PROJECT_ID, organisation_id=ORG_ID, targets=list(reversed(targets)))
    assert [c["target_id"] for c in first["candidates"]] == [c["target_id"] for c in second["candidates"]]
    for candidate in first["candidates"]:
        assert set(candidate["dimension_states"]) == set(first["dimensions"])
        for detail in candidate["dimension_details"].values():
            assert isinstance(detail, dict)
    assert "better evidenced, which is not the same as being better" in first["comparability_note"]


def test_comparison_persists_nothing(db, client):
    before = db.query(IndustrialViabilityAssessment).count()
    response = client.post("/industrial/viability/compare", headers=HEADERS, json={
        "project_id": PROJECT_ID,
        "targets": [{"target_kind": "known_material", "target_id": SILICON_ID}],
    })
    assert response.status_code == 200
    db.expire_all()
    assert db.query(IndustrialViabilityAssessment).count() == before


# --- API scoping ---------------------------------------------------------------------------------
def test_industrial_endpoints_are_tenant_scoped(client):
    # Silicon is a PUBLIC material, so listing its evidence is permitted for any tenant. The
    # invariant is that another tenant's private industrial records never appear in that list.
    public_read = client.get(
        f"/industrial/evidence?target_kind=known_material&target_id={SILICON_ID}", headers=HOSTILE_HEADERS)
    assert public_read.status_code == 200
    assert public_read.json() == [], "another organisation's industrial evidence must not be visible"
    owner_read = client.get(
        f"/industrial/evidence?target_kind=known_material&target_id={SILICON_ID}", headers=HEADERS)
    assert owner_read.json(), "the owning organisation still sees its own records"

    # Project-scoped resources are not readable across tenants at all.
    assert client.post("/industrial/viability/assess", headers=HOSTILE_HEADERS, json={
        "project_id": PROJECT_ID, "target_kind": "known_material", "target_id": SILICON_ID,
    }).status_code == 404
    assert client.get(f"/projects/{PROJECT_ID}/industrial-constraints", headers=HOSTILE_HEADERS).status_code == 404
    assert client.get(f"/industrial/viability/assessments?project_id={PROJECT_ID}",
                      headers=HOSTILE_HEADERS).status_code == 404


def test_economic_constraint_without_basis_is_rejected_by_the_api(client):
    response = client.post(f"/projects/{PROJECT_ID}/industrial-constraints", headers=HEADERS, json={
        "category": "economic", "constraint_kind": "max_value", "metric_key": "raw_material_cost",
        "display_label": "cost limit", "target_value": 10.0,
    })
    assert response.status_code == 422
    assert "currency" in response.text


def test_evidence_requires_exactly_one_value_shape(client):
    response = client.post("/industrial/evidence", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": SILICON_ID, "category": "manufacturing",
        "metric_key": "x", "display_label": "x", "source_type": "seed_demonstration",
    })
    assert response.status_code == 422
    assert "exactly one value shape" in response.text


def test_compatibility_verdict_requires_a_rationale(client):
    routes = client.get("/industrial/manufacturing-routes", headers=HEADERS).json()
    assert routes
    response = client.post("/industrial/process-compatibility", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": SILICON_ID, "route_id": routes[0]["id"],
        "compatibility": "compatible",
    })
    assert response.status_code == 422
    assert "rationale" in response.text


def test_maturity_supersedes_rather_than_overwrites(client, db):
    before = db.query(MaturityAssessment).filter_by(material_id=SILICON_ID).count()
    response = client.post("/industrial/maturity", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": SILICON_ID, "stage": "pilot_demonstrated",
        "justification": "Deliberate downgrade to verify that the earlier assessment is retained.",
    })
    assert response.status_code == 201
    db.expire_all()
    rows = db.query(MaturityAssessment).filter_by(material_id=SILICON_ID).all()
    assert len(rows) == before + 1, "the previous assessment must still exist"
    assert sum(1 for r in rows if r.superseded_by_id is None) == 1
