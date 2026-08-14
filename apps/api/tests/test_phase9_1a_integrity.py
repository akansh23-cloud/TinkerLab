"""Phase 9.1-A scientific integrity regression tests."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.db.seed import sid
from app.domain.enums import IndustrialAssessmentState, RequirementDirection, RequirementKind, RequirementStatus
from app.models.entities import FunctionalRequirement, IndustrialEvidence, MaturityAssessment, VirtualCandidateEvaluation, Candidate
from app.schemas.industrial import IndustrialEvidenceCreate, IndustrialConstraintCreate, ViabilityAssessmentRequest
from app.services.industrial import IndustrialError, _composite, _scientific_dimension, detect_conflicts
from app.services.material_states import composition_signature
from app.services.reasoning import _test_direction
from app.services.units import convert

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
PROJECT_ID = sid("project")
SILICON_ID = sid("material:silicon")
HEADERS = {"X-Organisation-ID": ORG_ID}
HOSTILE_HEADERS = {"X-Organisation-ID": OTHER_ORG}


def _req(*, value: float, unit: str) -> FunctionalRequirement:
    return FunctionalRequirement(
        id="unit-regression", function_id="f", key="unit-regression", display_name="unit regression",
        requirement_kind=RequirementKind.HARD_CONSTRAINT, direction=RequirementDirection.MINIMUM,
        target_value=value, target_unit=unit, property_key="tensile_strength", weight=1.0,
    )


def test_68_mpa_is_not_68_gpa():
    low = convert(68.0, "MPa", "GPa")
    assert low == pytest.approx(0.068)
    status, _ = _test_direction(_req(value=1.0, unit="GPa"), low, low)
    assert status == RequirementStatus.FAIL


def test_composition_identity_preserves_alloy_fraction_and_dopant_concentration():
    a = composition_signature([
        {"element": "Cu", "role": "alloying", "atomic_fraction": 0.10},
        {"element": "Ni", "role": "alloying", "atomic_fraction": 0.90},
    ])
    b = composition_signature([
        {"element": "Cu", "role": "alloying", "atomic_fraction": 0.90},
        {"element": "Ni", "role": "alloying", "atomic_fraction": 0.10},
    ])
    light = composition_signature([
        {"element": "Si", "role": "host", "atomic_fraction": 1.0},
        {"element": "B", "role": "dopant", "concentration_value": 1e15, "concentration_unit": "cm^-3"},
    ])
    heavy = composition_signature([
        {"element": "Si", "role": "host", "atomic_fraction": 1.0},
        {"element": "B", "role": "dopant", "concentration_value": 1e20, "concentration_unit": "cm^-3"},
    ])
    assert a != b
    assert light != heavy


def test_regulatory_claims_in_different_jurisdictions_are_not_conflicts(db):
    rows = []
    for jurisdiction, value in (("EU", True), ("JP", False)):
        row = IndustrialEvidence(
            organisation_id=ORG_ID, visibility="private", material_id=SILICON_ID, category="regulatory",
            metric_key="restricted", display_label=f"restricted {jurisdiction}", boolean_value=value,
            jurisdiction=jurisdiction, as_of_date=date(2026, 1, 1), source_type="test",
            content_checksum=f"{jurisdiction}-checksum",
        )
        db.add(row); rows.append(row)
    db.flush()
    assert detect_conflicts(rows) == []
    db.rollback()


def test_economic_ranges_and_constraints_require_complete_monetary_basis():
    with pytest.raises(ValidationError, match="MONETARY_BASIS_INCOMPLETE"):
        IndustrialEvidenceCreate(
            target_kind="known_material", target_id="x", category="economic", metric_key="cost",
            display_label="cost", lower_bound=5, upper_bound=8, source_type="quote", as_of_date=date(2026, 1, 1),
        )
    with pytest.raises(ValidationError, match="MONETARY_BASIS_INCOMPLETE"):
        IndustrialConstraintCreate(
            category="economic", constraint_kind="max_value", display_label="cost", metric_key="cost",
            target_value=8, currency="USD", cost_basis="per_kilogram",
        )


def test_composite_weights_are_nonnegative_finite_and_bounded():
    with pytest.raises(ValidationError, match="INVALID_COMPOSITE_WEIGHT"):
        ViabilityAssessmentRequest(
            project_id="p", target_kind="known_material", target_id="m",
            composite_methodology="declared_weighted_mean_v1", composite_weights={"economic_feasibility": -1},
        )
    score, _ = _composite(
        {"economic_feasibility": IndustrialAssessmentState.PASS, "supply_resilience": IndustrialAssessmentState.FAIL},
        "declared_weighted_mean_v1", {"economic_feasibility": 2.0, "supply_resilience": 1.0},
    )
    assert score is not None and 0 <= score <= 1


def test_phase5_feasibility_class_feeds_industrial_scientific_dimension(db):
    evaluation = db.query(VirtualCandidateEvaluation).filter_by(feasibility_class="robustly_feasible").first()
    assert evaluation is not None
    candidate = db.get(Candidate, evaluation.candidate_id)
    assert candidate is not None
    result = _scientific_dimension(
        db, project_id=candidate.project_id, target_kind=candidate.candidate_kind,
        target_id=candidate.material_id or candidate.hypothesis_id, organisation_id=ORG_ID,
    )
    assert result["state"] == IndustrialAssessmentState.PASS
    assert result["feasibility_class"] == "robustly_feasible"
    assert result["evaluation_checksum"]


def test_maturity_is_tenant_scoped_on_api(client):
    owner = client.get(
        f"/industrial/maturity?target_kind=known_material&target_id={SILICON_ID}", headers=HEADERS
    )
    hostile = client.get(
        f"/industrial/maturity?target_kind=known_material&target_id={SILICON_ID}", headers=HOSTILE_HEADERS
    )
    assert owner.status_code == 200 and owner.json()
    assert hostile.status_code == 200
    assert hostile.json() == []
