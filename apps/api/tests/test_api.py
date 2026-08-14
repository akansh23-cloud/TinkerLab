def test_health_has_request_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-request-id")


def test_seeded_project_workflow(client):
    projects = client.get("/replacement-projects")
    assert projects.status_code == 200
    project = projects.json()[0]
    detail = client.get(f"/replacement-projects/{project['id']}")
    assert detail.status_code == 200
    spec = client.get(f"/replacement-projects/{project['id']}/specification")
    assert spec.status_code == 200
    assert len(spec.json()["checksum"]) == 64
    comparison = client.get(f"/replacement-projects/{project['id']}/comparison")
    assert comparison.status_code == 200
    assert len(comparison.json()) == 3


def test_invalid_unit_rejected(client):
    project = client.get("/replacement-projects").json()[0]
    response = client.post(
        f"/replacement-projects/{project['id']}/constraints",
        json={
            "constraint_type": "property", "property_key": "density", "comparator": "<=",
            "target_value": 10, "target_unit": "MPa", "hard_or_soft": "hard",
        },
    )
    assert response.status_code == 422


def test_create_project_add_constraint_candidate_and_compare(client):
    projects = client.get("/replacement-projects").json()
    seed = client.get(f"/replacement-projects/{projects[0]['id']}").json()
    materials = client.get("/materials").json()
    baseline = next(m for m in materials if m["canonical_name"] == "demo-polymer-baseline")
    candidate = next(m for m in materials if "Lightweight" in m["display_name"])
    created = client.post("/replacement-projects", json={
        "organisation_id": seed["organisation_id"], "created_by": seed["created_by"],
        "name": "API Integration Replacement Study", "description": "Integration test",
        "baseline_material_id": baseline["id"], "replacement_reasons": ["cost"], "status": "draft",
    })
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    c = client.post(f"/replacement-projects/{pid}/constraints", json={
        "constraint_type": "property", "property_key": "density", "comparator": "<=",
        "target_value": 1.35, "target_unit": "g/cm^3", "hard_or_soft": "hard", "weight": 1,
    })
    assert c.status_code == 201, c.text
    cand = client.post(f"/replacement-projects/{pid}/candidates", json={"material_id": candidate["id"]})
    assert cand.status_code == 201, cand.text
    spec = client.get(f"/replacement-projects/{pid}/specification")
    assert spec.status_code == 200
    comparison = client.get(f"/replacement-projects/{pid}/comparison")
    assert comparison.status_code == 200
    assert comparison.json()[0]["constraints"][0]["status"] == "PASS"
