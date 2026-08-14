from sqlalchemy.orm import selectinload

from app.models.entities import Candidate, Material, MaterialPropertyObservation, ReplacementProject
from app.services.evaluation import evaluate_candidate


def project_with_data(db):
    return db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material).selectinload(Material.observations).selectinload(MaterialPropertyObservation.property_definition),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
        selectinload(ReplacementProject.candidates).selectinload(Candidate.material).selectinload(Material.observations).selectinload(MaterialPropertyObservation.property_definition),
    ).filter(ReplacementProject.name == "Demo Polymer Replacement Study").one()


def test_candidate_evaluation_has_pass_fail_unknown(db):
    project = project_with_data(db)
    results = [evaluate_candidate(db, project, c) for c in project.candidates]
    statuses = {x["status"] for r in results for x in r["constraints"]}
    assert "PASS" in statuses
    assert "FAIL" in statuses
    assert "UNKNOWN" in statuses


def test_missing_data_is_unknown_not_fail(db):
    project = project_with_data(db)
    incomplete = next(c for c in project.candidates if "Incomplete" in c.material.display_name)
    result = evaluate_candidate(db, project, incomplete)
    operating = next(x for x in result["constraints"] if x["property_key"] == "operating_temperature")
    assert operating["status"] == "UNKNOWN"
    assert "no observation" in operating["unknown_reason"].lower()

def test_boolean_constraint_uses_typed_observation(db):
    project = project_with_data(db)
    by_name = {c.material.display_name: evaluate_candidate(db, project, c) for c in project.candidates}
    a = by_name["Candidate A — Lightweight Blend"]
    b = by_name["Candidate B — High-Temperature Blend"]
    bool_a = next(x for x in a["constraints"] if x["property_key"] == "existing_equipment_compatible")
    bool_b = next(x for x in b["constraints"] if x["property_key"] == "existing_equipment_compatible")
    assert bool_a["status"] == "PASS"
    assert bool_a["observed_value"] is True
    assert bool_b["status"] == "FAIL"
    assert bool_b["observed_value"] is False
