import json

from app.db.seed import sid


def test_passport_has_phase2_graph(client):
    response = client.get(f"/materials/{sid('material:demo-polymer-baseline')}")
    assert response.status_code == 200
    body = response.json()
    assert len(body["identifiers"]) >= 2
    assert len(body["components"]) >= 3
    assert body["process_states"]
    assert any(o["condition_set"] for o in body["observations"])


def test_conflict_and_provenance_endpoints(client):
    conflicts = client.get(f"/materials/{sid('material:demo-polymer-b')}/conflicts?property_key=density")
    assert conflicts.status_code == 200
    assert len(conflicts.json()) == 1
    observation_id = sid("obs:demo-polymer-a:tensile_strength")
    provenance = client.get(f"/observations/{observation_id}/provenance")
    assert provenance.status_code == 200
    chain = provenance.json()["chain"]
    assert [x["stage"] for x in chain] == ["provider_record", "evidence", "observation"]
    assert chain[0]["raw_checksum"]


def test_selection_preview_is_condition_aware(client):
    response = client.post(
        "/properties/tensile_strength/selection-preview",
        json={"material_id": sid("material:demo-polymer-a"), "context": {"temperature_value": 23, "temperature_unit": "degC", "material_state": "conditioned molded specimen"}},
    )
    assert response.status_code == 200
    assert response.json()["selected"]["numeric_value"] == 74.0


def test_private_import_does_not_leak_without_scope(client):
    external_id = "api-private-scope-001"
    content = json.dumps({"materials": [{
        "external_record_id": external_id, "canonical_name": "api-private-scope-mat", "display_name": "API Private Material",
        "material_family": "polymer", "visibility": "private",
        "identifiers": [{"namespace": "customer_code", "value": "API-PRIVATE-001", "is_primary": True}],
        "composition": [], "process_states": [],
        "evidence": [{"key": "e1", "evidence_type": "user_provided", "title": "Private evidence"}],
        "observations": [{"property_key": "density", "value_type": "numeric", "numeric_value": 1111, "unit": "kg/m^3", "evidence_key": "e1"}]
    }]})
    request = {"organisation_id": sid("org"), "input_format": "json", "content": content, "provider_key": "local_import"}
    preview = client.post("/imports/preview", json=request)
    assert preview.status_code == 200 and preview.json()["valid"] is True
    committed = client.post("/imports", json=request)
    assert committed.status_code == 201
    public_list = client.get("/materials?q=API%20Private").json()
    assert public_list == []
    scoped_list = client.get("/materials?q=API%20Private", headers={"X-Organisation-ID": sid("org")}).json()
    assert len(scoped_list) == 1


def test_project_comparison_returns_selection_provenance(client):
    response = client.get(f"/replacement-projects/{sid('project')}/comparison")
    assert response.status_code == 200
    candidate_a = next(x for x in response.json() if x["material_id"] == sid("material:demo-polymer-a"))
    tensile = next(x for x in candidate_a["constraints"] if x["property_key"] == "tensile_strength")
    assert tensile["selected_observation_id"] == sid("obs:demo-polymer-a:tensile_strength")
    assert tensile["applicability"] == "exact"
    assert tensile["selection_rationale"]


def test_material_selection_summary_and_usage_are_scope_safe(client):
    material_id = sid("material:demo-polymer-baseline")

    summary = client.get(f"/material-selection-summary/{material_id}")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert isinstance(summary_body, list)
    assert summary_body
    assert all("property_key" in row for row in summary_body)
    assert all("rationale" in row for row in summary_body)

    # Projects are organisation-owned and must not leak through a public material passport.
    unscoped_usage = client.get(f"/materials/{material_id}/projects")
    assert unscoped_usage.status_code == 200
    assert unscoped_usage.json() == []

    scoped_usage = client.get(
        f"/materials/{material_id}/projects",
        headers={"X-Organisation-ID": sid("org")},
    )
    assert scoped_usage.status_code == 200
    assert any(row["id"] == sid("project") for row in scoped_usage.json())
