"""Phase 12.2 regressions for scientific integrity, tenant isolation and evidence semantics."""
from __future__ import annotations

import uuid

import pytest

from app.models.entities import (
    Evidence,
    Material,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    Organisation,
    ReplacementProject,
    User,
)
from app.services.bench.provenance import weaker_provenance


def _ctx(client):
    ctx = client.get("/demo-context").json()
    client.headers["X-Organisation-ID"] = ctx["organisation_id"]
    return ctx


def _library(client):
    response = client.post("/bench/install-reference-library", json={})
    assert response.status_code == 200, response.text


def _library_material(db, canonical_name: str) -> Material:
    return db.query(Material).filter(Material.canonical_name == canonical_name).one()


def _other_tenant(db):
    org = Organisation(id=str(uuid.uuid4()), name=f"Other tenant {uuid.uuid4().hex[:8]}")
    user = User(
        id=str(uuid.uuid4()), organisation_id=org.id,
        display_name="Other tenant engineer", email=f"other-{uuid.uuid4().hex}@example.test",
    )
    db.add_all([org, user])
    db.commit()
    return org, user


def test_adverse_and_positive_regulatory_booleans_target_desirable_state(client, db):
    _ctx(client)
    _library(client)
    brass = _library_material(db, "library::brass-cuzn39pb3")
    body = client.get(f"/bench/materials/{brass.id}/derived-requirements").json()
    by_key = {r["property_key"]: r for r in body["requirements"]}
    assert by_key["reach_svhc_present"]["target_boolean"] is False
    assert by_key["rohs_compliant"]["target_boolean"] is True


def test_handbook_baseline_can_only_seed_soft_requirements(client, db):
    _ctx(client)
    _library(client)
    baseline = _library_material(db, "library::pa66-gf30")
    body = client.get(f"/bench/materials/{baseline.id}/derived-requirements").json()
    density = next(r for r in body["requirements"] if r["property_key"] == "density")
    assert density["hard_or_soft"] == "soft"
    assert density["evidence"]["provenance_category"] == "handbook_typical"
    assert any(w["property_key"] == "density" for w in body["warnings"])


def test_invalid_study_enum_is_rejected_before_creation(client, db):
    ctx = _ctx(client)
    _library(client)
    baseline = _library_material(db, "library::pa66-gf30")
    before = db.query(ReplacementProject).count()
    response = client.post("/bench/studies", json={
        "name": "Malformed comparator probe",
        "baseline_material_id": baseline.id,
        "requirements": [{
            "property_key": "density", "comparator": "BANANA",
            "target_value": 1300.0, "target_unit": "kg/m^3",
        }],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    })
    assert response.status_code == 422
    db.expire_all()
    assert db.query(ReplacementProject).count() == before


def test_dimensionally_wrong_study_target_is_transactional(client, db):
    ctx = _ctx(client)
    _library(client)
    baseline = _library_material(db, "library::pa66-gf30")
    before = db.query(ReplacementProject).count()
    response = client.post("/bench/studies", json={
        "name": "Wrong unit probe",
        "baseline_material_id": baseline.id,
        "requirements": [{
            "property_key": "density", "comparator": "<=",
            "target_value": 1300.0, "target_unit": "seconds",
        }],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    })
    assert response.status_code == 422
    db.expire_all()
    assert db.query(ReplacementProject).count() == before


def test_project_chart_and_derived_views_are_tenant_scoped(client, db):
    ctx = _ctx(client)
    _library(client)
    baseline = _library_material(db, "library::pa66-gf30")
    project = client.post("/bench/studies", json={
        "name": "Tenant scoped study",
        "baseline_material_id": baseline.id,
        "requirements": [{
            "property_key": "density", "comparator": "<=",
            "target_value": 1500.0, "target_unit": "kg/m^3",
        }],
        "derive_space": False,
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()
    other_org, _ = _other_tenant(db)
    client.headers["X-Organisation-ID"] = other_org.id
    for path in (
        f"/replacement-projects/{project['project_id']}/readiness",
        f"/replacement-projects/{project['project_id']}/baseline-derived-requirements",
        f"/replacement-projects/{project['project_id']}/decision-chart",
        f"/replacement-projects/{project['project_id']}/search-space-derivation",
    ):
        assert client.get(path).status_code == 404, path


def test_shared_reference_library_is_read_only(client, db):
    _ctx(client)
    _library(client)
    peek = _library_material(db, "library::peek-unfilled")
    before = db.query(MaterialPropertyObservation).filter_by(material_id=peek.id).count()
    response = client.post(f"/bench/materials/{peek.id}/properties", json={
        "data_grade": "internal_measurement",
        "properties": [{"property_key": "density", "value": 9999.0, "unit": "kg/m^3"}],
    })
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REFERENCE_MATERIAL_IMMUTABLE"
    db.expire_all()
    assert db.query(MaterialPropertyObservation).filter_by(material_id=peek.id).count() == before


def test_axis_options_do_not_leak_private_tenant_property_metadata(client, db):
    ctx = _ctx(client)
    definition = MaterialPropertyDefinition(
        id=str(uuid.uuid4()), key=f"tenant_secret_axis_{uuid.uuid4().hex[:8]}",
        display_name="Tenant secret chart property", quantity_type="scalar",
        canonical_unit="MPa", allowed_comparators=[">=", "<="], allow_negative=False,
        conflict_policy="informational",
    )
    evidence = Evidence(
        id=str(uuid.uuid4()), evidence_type="experimental", title="Private measurements",
        source_quality="internal_measurement", organisation_id=ctx["organisation_id"], visibility="private",
    )
    db.add_all([definition, evidence])
    for idx in range(2):
        material = Material(
            id=str(uuid.uuid4()), canonical_name=f"tenant-secret-{uuid.uuid4()}",
            display_name=f"Private axis material {idx}", material_family="polymer",
            owner_organisation_id=ctx["organisation_id"], visibility="private",
        )
        db.add(material)
        db.flush()
        db.add(MaterialPropertyObservation(
            material_id=material.id, property_definition_id=definition.id, value_type="numeric",
            numeric_value=10.0 + idx, unit="MPa", evidence_id=evidence.id, confidence=0.9,
        ))
    db.commit()
    own = client.get("/bench/property-space/axes").json()
    assert any(row["key"] == definition.key for row in own)
    other_org, _ = _other_tenant(db)
    client.headers["X-Organisation-ID"] = other_org.id
    other = client.get("/bench/property-space/axes").json()
    assert all(row["key"] != definition.key for row in other)


def test_unresolved_baseline_conflict_blocks_auto_derivation(client):
    ctx = _ctx(client)
    created = client.post("/bench/materials", json={
        "display_name": f"Conflict baseline {uuid.uuid4().hex[:8]}",
        "material_family": "polymer", "data_grade": "internal_measurement",
        "organisation_id": ctx["organisation_id"], "visibility": "private",
        "properties": [{"property_key": "tensile_strength", "value": 100.0, "unit": "MPa"}],
    }).json()
    appended = client.post(f"/bench/materials/{created['material_id']}/properties", json={
        "data_grade": "internal_measurement",
        "organisation_id": ctx["organisation_id"],
        "properties": [{"property_key": "tensile_strength", "value": 200.0, "unit": "MPa"}],
    })
    assert appended.status_code == 201, appended.text
    body = client.get(f"/bench/materials/{created['material_id']}/derived-requirements").json()
    assert all(r["property_key"] != "tensile_strength" for r in body["requirements"])
    skipped = next(s for s in body["skipped"] if s["property_key"] == "tensile_strength")
    assert "conflict" in skipped["reason"].lower()


def test_weakest_provenance_uses_semantic_rank_not_alphabetical_order():
    assert weaker_provenance("internal_measurement", "physics_simulation") == "physics_simulation"
    assert weaker_provenance("supplier_declared", "engineering_estimate") == "engineering_estimate"
    assert weaker_provenance("peer_reviewed", "model_prediction") == "model_prediction"


def test_decision_chart_exposes_canonical_requirement_thresholds(client, db):
    ctx = _ctx(client)
    _library(client)
    baseline = _library_material(db, "library::pa66-gf30")
    created = client.post("/bench/studies", json={
        "name": "Canonical chart threshold",
        "baseline_material_id": baseline.id,
        "requirements": [{
            "property_key": "continuous_service_temperature", "comparator": ">=",
            "target_value": 373.15, "target_unit": "K",
        }],
        "derive_space": False,
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    })
    assert created.status_code == 201, created.text
    chart = client.get(f"/replacement-projects/{created.json()['project_id']}/decision-chart")
    assert chart.status_code == 200, chart.text
    requirement = chart.json()["requirements"][0]
    assert requirement["canonical_unit"] == "degC"
    assert requirement["canonical_target_value"] == pytest.approx(100.0, abs=1e-9)
