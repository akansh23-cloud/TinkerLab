"""Regression tests for the single-project Vercel/data bootstrap repair."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import engine
from app.services.deployment import DEMO_ORGANISATION_ID, EXPECTED_ALEMBIC_HEAD
from service import app as service_app


def test_single_project_service_mount_exposes_core_api(database):
    with TestClient(service_app) as service_client:
        response = service_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["phase"] == "12.2.4"


def test_deployment_status_is_safe_before_version_table(client):
    response = client.get("/deployment/status")
    assert response.status_code == 200
    body = response.json()
    assert body["database_reachable"] is True
    assert body["expected_alembic_head"] == EXPECTED_ALEMBIC_HEAD
    assert "bootstrap_required" in body


def test_public_reference_library_install_does_not_require_existing_tenant(client):
    client.headers["X-Organisation-ID"] = str(uuid.uuid4())
    response = client.post("/bench/install-reference-library", json={})
    assert response.status_code == 200, response.text
    assert len(response.json()["installed"]) + len(response.json()["skipped"]) >= 30


def test_bootstrap_repairs_reference_library_and_demo_scope(client):
    # The normal test fixture creates the schema directly. Add the migration marker so bootstrap
    # can exercise its data-initialisation path without trying to recreate already-existing tables.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text("INSERT INTO alembic_version(version_num) VALUES (:v)"), {"v": EXPECTED_ALEMBIC_HEAD})
    try:
        response = client.post("/deployment/bootstrap")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "ready"
        assert body["organisation_id"] == DEMO_ORGANISATION_ID
        assert body["deployment"]["bootstrap_required"] is False
        assert body["deployment"]["material_count"] >= 30
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_flagship_demo_installer_is_explicit_and_idempotent(client):
    org_id = "0b5ec369-282c-57b5-9781-471f818a07c3"
    first = client.post("/bench/install-flagship-demo", json={}, headers={"X-Organisation-ID": org_id})
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "ready"
    assert body["is_demonstration_data"] is True
    assert body["project_id"]
    assert body["program_id"]

    second = client.post("/bench/install-flagship-demo", json={}, headers={"X-Organisation-ID": org_id})
    assert second.status_code == 200
    assert second.json()["project_id"] == body["project_id"]
    assert second.json()["program_id"] == body["program_id"]
