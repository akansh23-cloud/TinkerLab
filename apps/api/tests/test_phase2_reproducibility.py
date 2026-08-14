from app.db.seed import seed
from app.models.entities import (
    Evidence,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialPropertyObservation,
    ObservationConditionSet,
    SourceProvider,
    SourceRecord,
)
from app.services.ingestion import checksum


def counts(db):
    return {
        "materials": db.query(Material).count(),
        "identifiers": db.query(MaterialIdentifier).count(),
        "components": db.query(MaterialComponent).count(),
        "observations": db.query(MaterialPropertyObservation).count(),
        "conditions": db.query(ObservationConditionSet).count(),
        "evidence": db.query(Evidence).count(),
        "providers": db.query(SourceProvider).count(),
        "source_records": db.query(SourceRecord).count(),
    }


def test_seed_is_idempotent(db):
    before = counts(db)
    seed(db)
    after = counts(db)
    assert after == before


def test_source_checksum_is_canonical():
    a = {"b": 2, "a": {"y": 1, "x": 0}}
    b = {"a": {"x": 0, "y": 1}, "b": 2}
    assert checksum(a) == checksum(b)
