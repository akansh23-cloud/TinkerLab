from __future__ import annotations

from app.db.seed import sid
from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    CandidateHypothesisComponent,
    MaterialPropertyObservation,
    PredictionInputSnapshot,
    PredictionModel,
    PredictionModelVersion,
    PredictionRun,
    PredictionTarget,
    PropertyPrediction,
    ReplacementProject,
)
from app.services.prediction import (
    DEMO_WARNING,
    artifact_checksum,
    assess_applicability,
    execute_prediction_run,
    get_model_version,
    interval_constraint_status,
    preview_prediction_run,
    resolve_target_snapshot,
)

ORG_ID = sid("org")
PROJECT_ID = sid("project")
USER_ID = sid("user")
MODEL_ID = sid("phase4:model:demo-polymer-tensile")
VERSION_ID = sid("phase4:model-version:demo-polymer-tensile:v1")
RUN_ID = sid("phase4:prediction-run:demo-tensile")
BASELINE_ID = sid("material:demo-polymer-baseline")
C_ID = sid("material:demo-polymer-c")


def alt_hypothesis(db):
    return (
        db.query(CandidateHypothesis)
        .join(CandidateHypothesisComponent)
        .filter(
            CandidateHypothesis.project_id == PROJECT_ID,
            CandidateHypothesis.structural_validity == "valid",
            CandidateHypothesisComponent.component_key == "modifier_b2",
        )
        .order_by(CandidateHypothesis.id)
        .first()
    )


def test_demo_model_registry_is_explicit_and_approved(db):
    model = db.get(PredictionModel, MODEL_ID)
    version = get_model_version(db, VERSION_ID)
    assert model.status == "approved"
    assert version.approved_at is not None
    assert version.immutable_metadata["demo_only"] is True
    assert "DEMO MODEL" in version.immutable_metadata["warning"]
    assert version.uncertainty_method == "fixed_validation_interval"


def test_artifact_checksum_is_deterministic_and_order_independent():
    a = {"intercept": 1, "coefficients": {"b": 2, "a": 1}}
    b = {"coefficients": {"a": 1, "b": 2}, "intercept": 1}
    assert artifact_checksum("tinkerlab_linear_json_v1", a) == artifact_checksum("tinkerlab_linear_json_v1", b)


def test_unsafe_model_artifact_format_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        artifact_checksum("pickle", {"blob": "not-executed"})


def test_known_material_feature_snapshot_is_deterministic(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    first = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    second = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    assert first.feature_checksum == second.feature_checksum
    assert first.source_entity_checksum == second.source_entity_checksum
    assert first.features["matrix_fraction_pct"] == 78.0
    assert first.features["total_modifier_fraction_pct"] == 18.0
    assert first.redaction_flags == []


def test_hypothesis_feature_snapshot_uses_hypothesis_not_parent_observations(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    hypothesis = alt_hypothesis(db)
    snapshot = resolve_target_snapshot(db, project, {"hypothesis_id": hypothesis.id}, ORG_ID)
    assert snapshot.target_kind == "hypothesis"
    assert snapshot.features["alternative_modifier_fraction_pct"] == 18.0
    assert snapshot.features["primary_modifier_fraction_pct"] == 0.0
    assert snapshot.source_entity_checksum != hypothesis.baseline_material_id


def test_redacted_material_is_incomplete_not_imputed(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": C_ID}, ORG_ID)
    assert snapshot.redaction_flags
    assert "complete_weight_percent_composition" in snapshot.missing_features


def test_applicability_in_domain_and_condition_aware(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    result = assess_applicability(version, snapshot, "tensile_strength", {"temperature": {"value": 23, "unit": "degC"}})
    assert result.status == "in_domain"


def test_applicability_rejects_unsupported_condition(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    result = assess_applicability(version, snapshot, "tensile_strength", {"temperature": {"value": 80, "unit": "degC"}})
    assert result.status == "unsupported_conditions"
    assert any(r["code"] == "CONDITION_OUTSIDE_DOMAIN" for r in result.reasons)


def test_applicability_rejects_unsupported_property(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    result = assess_applicability(version, snapshot, "density", {"temperature": {"value": 23, "unit": "degC"}})
    assert result.status == "unsupported_property"


def test_applicability_marks_redacted_material_incomplete(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": C_ID}, ORG_ID)
    result = assess_applicability(version, snapshot, "tensile_strength", {"temperature": {"value": 23, "unit": "degC"}})
    assert result.status == "incomplete_inputs"


def test_seeded_prediction_run_has_prediction_uncertainty_and_refusal(db):
    run = db.get(PredictionRun, RUN_ID)
    assert run.predicted_count >= 2
    assert run.inapplicable_count >= 1
    rows = db.query(PropertyPrediction).filter_by(prediction_run_id=RUN_ID).all()
    predicted = [p for p in rows if p.status == "predicted"]
    refused = [p for p in rows if p.status == "inapplicable"]
    assert predicted and refused
    assert all(p.uncertainty_lower <= p.numeric_point_estimate <= p.uncertainty_upper for p in predicted)
    assert all(DEMO_WARNING in p.warnings for p in predicted)
    assert all(p.numeric_point_estimate is None and p.uncertainty_lower is None for p in refused)


def test_prediction_creates_zero_material_property_observations(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    hypothesis = alt_hypothesis(db)
    before = db.query(MaterialPropertyObservation).count()
    execute_prediction_run(
        db, project, version, [{"hypothesis_id": hypothesis.id}], "tensile_strength",
        {"temperature": {"value": 23.0, "unit": "degC"}}, "MPa", {"test": "no-observation"}, USER_ID, ORG_ID,
    )
    after = db.query(MaterialPropertyObservation).count()
    assert after == before


def test_reproducible_prediction_result_checksum(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    hypothesis = alt_hypothesis(db)
    args = ([{"hypothesis_id": hypothesis.id}], "tensile_strength", {"temperature": {"value": 23.0, "unit": "degC"}}, "MPa", {"repro": 1}, USER_ID, ORG_ID)
    first = execute_prediction_run(db, project, version, *args)
    second = execute_prediction_run(db, project, version, *args)
    assert first.result_checksum == second.result_checksum
    p1 = db.query(PropertyPrediction).filter_by(prediction_run_id=first.id).one()
    p2 = db.query(PropertyPrediction).filter_by(prediction_run_id=second.id).one()
    assert p1.deterministic_result_checksum == p2.deterministic_result_checksum


def test_changed_condition_changes_prediction_checksum(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    hypothesis = alt_hypothesis(db)
    first = execute_prediction_run(db, project, version, [{"hypothesis_id": hypothesis.id}], "tensile_strength", {"temperature": {"value": 23.0, "unit": "degC"}}, "MPa", {"condition-change": True}, USER_ID, ORG_ID)
    second = execute_prediction_run(db, project, version, [{"hypothesis_id": hypothesis.id}], "tensile_strength", {"temperature": {"value": 24.0, "unit": "degC"}}, "MPa", {"condition-change": True}, USER_ID, ORG_ID)
    assert first.result_checksum != second.result_checksum


def test_interval_constraint_crossing_is_unknown(db):
    prediction = (
        db.query(PropertyPrediction, PredictionTarget)
        .join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id)
        .filter(PropertyPrediction.prediction_run_id == RUN_ID, PredictionTarget.material_id == BASELINE_ID)
        .one()[0]
    )
    status, crosses, reason = interval_constraint_status(prediction, ">=", 70.0, None, "MPa")
    assert status == "UNKNOWN"
    assert crosses is True
    assert reason == "PREDICTION_INTERVAL_CROSSES_CONSTRAINT"


def test_interval_fully_satisfying_threshold_is_predicted_pass(db):
    hypothesis = alt_hypothesis(db)
    prediction = (
        db.query(PropertyPrediction, PredictionTarget)
        .join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id)
        .filter(PropertyPrediction.prediction_run_id == RUN_ID, PredictionTarget.hypothesis_id == hypothesis.id)
        .one()[0]
    )
    status, crosses, reason = interval_constraint_status(prediction, ">=", 70.0, None, "MPa")
    assert status == "PASS"
    assert crosses is False
    assert reason is None


def test_interval_fully_violating_threshold_is_predicted_fail(db):
    p = PropertyPrediction(
        status="predicted", applicability_status="in_domain", uncertainty_lower=60.0, uncertainty_upper=65.0,
        output_unit="MPa", uncertainty_method="fixture", deterministic_result_checksum="x" * 64,
    )
    status, crosses, reason = interval_constraint_status(p, ">=", 70.0, None, "MPa")
    assert status == "FAIL" and crosses is False and reason is None


def test_preview_is_zero_persistence(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    hypothesis = alt_hypothesis(db)
    before_targets = db.query(PredictionTarget).count()
    before_snapshots = db.query(PredictionInputSnapshot).count()
    before_predictions = db.query(PropertyPrediction).count()
    result = preview_prediction_run(db, project, version, [{"hypothesis_id": hypothesis.id}], "tensile_strength", {"temperature": {"value": 23, "unit": "degC"}}, {"preview": True}, ORG_ID)
    assert result["expected_model_executions"] == 1
    assert db.query(PredictionTarget).count() == before_targets
    assert db.query(PredictionInputSnapshot).count() == before_snapshots
    assert db.query(PropertyPrediction).count() == before_predictions


def test_api_prediction_registry_and_preview(client, db):
    hypothesis = alt_hypothesis(db)
    headers = {"X-Organisation-ID": ORG_ID}
    models = client.get("/prediction-models", headers=headers)
    assert models.status_code == 200
    assert any(m["id"] == MODEL_ID for m in models.json())
    before = db.query(PropertyPrediction).count()
    response = client.post(
        f"/replacement-projects/{PROJECT_ID}/prediction-runs/preview",
        headers=headers,
        json={
            "model_version_id": VERSION_ID, "property_key": "tensile_strength",
            "targets": [{"hypothesis_id": hypothesis.id}],
            "conditions": {"temperature": {"value": 23, "unit": "degC"}},
            "requested_output_unit": "MPa", "configuration": {"api-preview": True},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expected_model_executions"] == 1
    assert "DEMO MODEL" in body["demo_warning"]
    assert db.query(PropertyPrediction).count() == before


def test_api_prediction_execution_and_detail_are_scoped(client, db):
    hypothesis = alt_hypothesis(db)
    headers = {"X-Organisation-ID": ORG_ID}
    response = client.post(
        f"/replacement-projects/{PROJECT_ID}/prediction-runs",
        headers=headers,
        json={
            "model_version_id": VERSION_ID, "property_key": "tensile_strength", "targets": [{"hypothesis_id": hypothesis.id}],
            "conditions": {"temperature": {"value": 23, "unit": "degC"}}, "requested_output_unit": "MPa",
            "configuration": {"api-execute": True}, "created_by": USER_ID,
        },
    )
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    results = client.get(f"/prediction-runs/{run_id}/results", headers=headers)
    assert results.status_code == 200 and results.json()["total"] == 1
    prediction_id = results.json()["items"][0]["id"]
    assert client.get(f"/predictions/{prediction_id}").status_code == 400
    detail = client.get(f"/predictions/{prediction_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["prediction"]["scientific_origin"] == "MODEL PREDICTION"


def test_explicit_prediction_comparison_preserves_default_unknown(client, db):
    hypothesis = alt_hypothesis(db)
    candidate = db.query(Candidate).filter_by(project_id=PROJECT_ID, hypothesis_id=hypothesis.id).one()
    headers = {"X-Organisation-ID": ORG_ID}
    default = client.get(f"/replacement-projects/{PROJECT_ID}/comparison?include_hypotheses=true", headers=headers)
    assert default.status_code == 200
    default_item = next(x for x in default.json() if x["candidate_id"] == candidate.id)
    tensile = next(x for x in default_item["constraints"] if x["property_key"] == "tensile_strength")
    assert tensile["status"] == "UNKNOWN" and tensile["value_origin"] == "none"

    selected = client.get(f"/replacement-projects/{PROJECT_ID}/comparison?include_hypotheses=true&prediction_run_id={RUN_ID}", headers=headers)
    assert selected.status_code == 200, selected.text
    item = next(x for x in selected.json() if x["candidate_id"] == candidate.id)
    tensile = next(x for x in item["constraints"] if x["property_key"] == "tensile_strength")
    assert tensile["status"] == "PASS"
    assert tensile["value_origin"] == "model_prediction"
    assert tensile["prediction_interval"] is not None


def test_prediction_routes_do_not_leak_private_runs_unscoped(client):
    assert client.get(f"/prediction-runs/{RUN_ID}").status_code == 400
    assert client.get(f"/prediction-runs/{RUN_ID}/results").status_code == 400

def test_api_lists_immutable_model_versions(client):
    headers = {"X-Organisation-ID": ORG_ID}
    response = client.get(f"/prediction-models/{MODEL_ID}/versions", headers=headers)
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1 and rows[0]["id"] == VERSION_ID
    assert rows[0]["artifact_checksum"]
    assert "DEMO MODEL" in rows[0]["immutable_metadata"]["warning"]


def test_disabled_model_is_not_executable(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    version = get_model_version(db, VERSION_ID)
    snapshot = resolve_target_snapshot(db, project, {"material_id": BASELINE_ID}, ORG_ID)
    version.model.status = "disabled"
    db.flush()
    result = assess_applicability(version, snapshot, "tensile_strength", {"temperature": {"value": 23, "unit": "degC"}})
    assert result.status == "out_of_domain"
    assert result.reasons[0]["code"] == "MODEL_NOT_EXECUTABLE"
    db.rollback()


def test_prediction_api_enforces_200_target_budget(client, db):
    hypothesis = alt_hypothesis(db)
    headers = {"X-Organisation-ID": ORG_ID}
    response = client.post(
        f"/replacement-projects/{PROJECT_ID}/prediction-runs/preview",
        headers=headers,
        json={
            "model_version_id": VERSION_ID,
            "property_key": "tensile_strength",
            "targets": [{"hypothesis_id": hypothesis.id}] * 201,
            "conditions": {"temperature": {"value": 23, "unit": "degC"}},
        },
    )
    assert response.status_code == 422

def test_phase4_seed_is_idempotent_for_prediction_entities(db):
    from app.db.seed import seed
    from app.models.entities import ModelApplicabilityDomain
    before = (
        db.query(PredictionModel).count(),
        db.query(PredictionModelVersion).count(),
        db.query(ModelApplicabilityDomain).count(),
        db.query(PredictionRun).count(),
        db.query(PredictionTarget).count(),
        db.query(PredictionInputSnapshot).count(),
        db.query(PropertyPrediction).count(),
    )
    seed(db)
    after = (
        db.query(PredictionModel).count(),
        db.query(PredictionModelVersion).count(),
        db.query(ModelApplicabilityDomain).count(),
        db.query(PredictionRun).count(),
        db.query(PredictionTarget).count(),
        db.query(PredictionInputSnapshot).count(),
        db.query(PropertyPrediction).count(),
    )
    assert after == before
