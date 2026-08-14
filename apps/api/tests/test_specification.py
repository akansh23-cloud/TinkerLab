from sqlalchemy.orm import selectinload

from app.models.entities import ReplacementProject
from app.services.specification import compile_specification


def load_project(db):
    return db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
    ).filter(ReplacementProject.name == "Demo Polymer Replacement Study").one()


def test_specification_checksum_is_semantically_deterministic(db):
    project = load_project(db)
    a = compile_specification(project)
    b = compile_specification(project)
    assert a["checksum"] == b["checksum"]
    assert a["canonical_payload"] == b["canonical_payload"]
    assert a["generated_at"] != ""


def test_spec_contains_hard_soft_and_objectives(db):
    spec = compile_specification(load_project(db))
    assert len(spec["hard_constraints"]) >= 5
    assert len(spec["soft_constraints"]) >= 1
    assert len(spec["objectives"]) >= 3
