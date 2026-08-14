from __future__ import annotations

import uuid

import pytest

from app.db.seed import seed, sid
from app.models.entities import (
    CampaignIteration,
    Candidate,
    CandidateChangeRecord,
    CandidateHypothesis,
    CandidateLineageEdge,
    MaterialPropertyObservation,
    OptimizationDecisionRecord,
    Organisation,
    ParetoFrontSnapshot,
    PredictionModel,
    PredictionModelVersion,
    PredictionRun,
    PropertyPrediction,
    ReplacementProject,
    VirtualCandidateEvaluation,
    VirtualExperimentCampaign,
)
from app.services.experiments import (
    MAX_SYNC_ITERATIONS,
    POLICIES,
    VIRTUAL_WARNING,
    ObjectiveValue,
    _minimization_vector,
    assert_virtual_evaluation_integrity,
    campaign_reproducibility_envelope,
    create_campaign,
    non_dominated_sort,
    preview_campaign,
    run_campaign,
    validate_campaign,
)
from app.services.prediction import get_model_version

ORG_ID = sid("org")
PROJECT_ID = sid("project")
USER_ID = sid("user")
CAMPAIGN_ID = sid("phase5:virtual-campaign:demo-robust-pareto")
TENSILE_VERSION_ID = sid("phase4:model-version:demo-polymer-tensile:v1")
DENSITY_VERSION_ID = sid("phase5:model-version:demo-polymer-density:v1")
SEARCH_SPACE_ID = sid("phase3:search-space:v1")


def seeded_campaign(db):
    return db.get(VirtualExperimentCampaign, CAMPAIGN_ID)


def test_phase5_demo_campaign_is_explicitly_virtual_and_multistep(db):
    campaign = seeded_campaign(db)
    assert campaign.status == "completed"
    assert campaign.stop_reason == "maximum_iterations_reached"
    assert campaign.policy_key == "robust_pareto_v1"
    assert campaign.result_checksum
    iterations = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID).order_by(CampaignIteration.iteration_number).all()
    assert len(iterations) == 2
    first, second = iterations
    assert first.feasible_count >= 1
    assert first.uncertain_count >= 1
    assert first.infeasible_count >= 1
    assert first.pareto_front_count >= 2
    assert first.new_candidate_count >= 1
    assert first.duplicate_count >= 1
    assert second.stop_signal is True
    assert VIRTUAL_WARNING.startswith("VIRTUAL EVALUATION")


def test_virtual_evaluation_never_creates_observations(db):
    observations_before = db.query(MaterialPropertyObservation).count()
    integrity = assert_virtual_evaluation_integrity(db)
    assert integrity["material_observation_count"] == observations_before
    assert integrity["virtual_evaluation_count"] > 0
    assert "not a physical experiment" in integrity["warning"]
    # Generated Phase-5 children remain hypotheses, not canonical Materials.
    child_ids = [
        d.candidate_id for d in db.query(OptimizationDecisionRecord).filter_by(campaign_id=CAMPAIGN_ID, decision_type="mutation_generated").all()
        if d.candidate_id
    ]
    assert child_ids
    for cid in child_ids:
        candidate = db.get(Candidate, cid)
        assert candidate.candidate_kind == "hypothesis"
        assert candidate.material_id is None
        assert candidate.hypothesis_id is not None
        assert db.query(MaterialPropertyObservation).filter_by(material_id=candidate.material_id).count() == 0


def test_seeded_feasibility_preserves_three_way_posture(db):
    first = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    rows = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=first.id).all()
    classes = {r.feasibility_class for r in rows}
    assert {"robustly_feasible", "uncertain", "robustly_infeasible"}.issubset(classes)
    for row in rows:
        if row.feasibility_class == "robustly_feasible":
            assert row.hard_fail_count == 0 and row.hard_unknown_count == 0
        if row.feasibility_class == "robustly_infeasible":
            assert row.hard_fail_count >= 1
        if row.feasibility_class == "uncertain":
            assert row.hard_fail_count == 0 and row.hard_unknown_count >= 1


def test_seeded_objective_vectors_retain_prediction_intervals_and_models(db):
    first = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    rows = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=first.id).all()
    complete = [r for r in rows if all(v.get("completeness") == "complete" for v in r.objective_vector.values())]
    assert complete
    for row in complete:
        tensile = row.objective_vector["tensile_strength"]
        density = row.objective_vector["density"]
        tensile_interval = row.objective_intervals["tensile_strength"]
        density_interval = row.objective_intervals["density"]
        tensile_origin = row.objective_origins["tensile_strength"]
        density_origin = row.objective_origins["density"]
        assert tensile_interval["lower"] <= tensile["point"] <= tensile_interval["upper"]
        assert density_interval["lower"] <= density["point"] <= density_interval["upper"]
        assert tensile["conservative_value"] == tensile_interval["lower"]  # maximize
        assert density["conservative_value"] == density_interval["upper"]  # minimize
        assert tensile_origin["model_version_id"] == TENSILE_VERSION_ID
        assert density_origin["model_version_id"] == DENSITY_VERSION_ID
        assert tensile_origin["origin"] == "model_prediction"


def test_non_dominated_sort_handles_maximize_and_minimize_deterministically(db):
    # _minimization_vector converts maximize values to negative and minimize values to positive.
    objectives = db.query(__import__("app.models.entities", fromlist=["CampaignObjective"]).CampaignObjective).filter_by(campaign_id=CAMPAIGN_ID).order_by(__import__("app.models.entities", fromlist=["CampaignObjective"]).CampaignObjective.sequence).all()

    def rec(cid: str, strength: float, density: float):
        vals = {
            "tensile_strength": ObjectiveValue("tensile_strength", "maximize", "model_prediction", strength, strength - 1, strength + 1, "MPa", "in_domain", TENSILE_VERSION_ID, cid + "t", strength - 1, "complete", 2.0),
            "density": ObjectiveValue("density", "minimize", "model_prediction", density, density - 5, density + 5, "kg/m^3", "in_domain", DENSITY_VERSION_ID, cid + "d", density + 5, "complete", 10.0),
        }
        return {"candidate": type("C", (), {"id": cid})(), "identity": cid, "objective_values": vals, "pareto_vector": _minimization_vector(vals, objectives)}

    # A and B trade off; C is dominated by A (weaker and denser under conservative values).
    records = [rec("A", 80, 1150), rec("B", 75, 1080), rec("C", 70, 1200)]
    fronts = non_dominated_sort(records)
    assert {r["candidate"].id for r in fronts[0]} == {"A", "B"}
    assert [r["candidate"].id for r in fronts[1]] == ["C"]
    # Replay exact same records/order is stable.
    replay = non_dominated_sort(records)
    assert [[r["candidate"].id for r in f] for f in replay] == [[r["candidate"].id for r in f] for f in fronts]


def test_incomplete_objective_is_not_silently_pareto_ranked(db):
    first = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    rows = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=first.id).all()
    incomplete = [r for r in rows if any(v.get("completeness") != "complete" for v in r.objective_vector.values())]
    assert incomplete
    assert all(r.pareto_rank is None for r in incomplete)


def test_seeded_front_has_tradeoffs_and_selected_parent_rationale(db):
    first = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    front = db.query(ParetoFrontSnapshot).filter_by(campaign_iteration_id=first.id, front_number=1).one()
    assert len(front.ordered_candidate_ids) >= 2
    selected = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=first.id, selected_as_parent=True).all()
    assert selected
    assert all(r.hypothesis_id for r in selected)  # known materials are references, not mutation parents
    assert all(r.rationale and "Pareto" in r.rationale for r in selected)


def test_phase5_children_have_phase3_lineage_and_typed_changes(db):
    child_decision = db.query(OptimizationDecisionRecord).filter_by(campaign_id=CAMPAIGN_ID, decision_type="mutation_generated").order_by(OptimizationDecisionRecord.sequence).first()
    assert child_decision and child_decision.candidate_id
    candidate = db.get(Candidate, child_decision.candidate_id)
    hypothesis = db.get(CandidateHypothesis, candidate.hypothesis_id)
    assert hypothesis.structural_validity == "valid"
    assert hypothesis.deterministic_fingerprint
    lineage = db.query(CandidateLineageEdge).filter_by(child_hypothesis_id=hypothesis.id).all()
    changes = db.query(CandidateChangeRecord).filter_by(hypothesis_id=hypothesis.id).order_by(CandidateChangeRecord.sequence).all()
    assert lineage
    assert changes
    assert all(c.change_type in {"component_amount_change", "component_substitution", "process_parameter_change"} for c in changes)
    assert all("campaign" in (c.rationale or "").lower() or "iteration" in (c.rationale or "").lower() for c in changes)


def test_prediction_orchestration_reuses_phase4_records_and_demo_models(db):
    campaign = seeded_campaign(db)
    iterations = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).all()
    run_ids = [rid for it in iterations for rid in it.prediction_run_ids]
    assert run_ids
    assert all(db.get(PredictionRun, rid) is not None for rid in run_ids)
    predictions = db.query(PropertyPrediction).filter(PropertyPrediction.prediction_run_id.in_(run_ids)).all()
    assert predictions
    assert all(p.uncertainty_method for p in predictions if p.status == "predicted")
    # No physical observation IDs are stored as virtual objective origins.
    evals = db.query(VirtualCandidateEvaluation).join(CampaignIteration).filter(CampaignIteration.campaign_id == campaign.id).all()
    for row in evals:
        for val in row.objective_origins.values():
            assert val.get("origin") in {"model_prediction", "none"}


def test_demo_density_model_is_explicitly_synthetic_and_safe_json(db):
    model = db.get(PredictionModel, sid("phase5:model:demo-polymer-density"))
    version = get_model_version(db, DENSITY_VERSION_ID)
    assert model.status == "approved"
    assert version.artifact_format == "tinkerlab_linear_json_v1"
    assert version.immutable_metadata["demo_only"] is True
    assert "DEMO MODEL" in version.immutable_metadata["warning"]
    assert version.uncertainty_method == "fixed_validation_interval"


def test_campaign_preview_is_zero_persistence(db):
    campaign = seeded_campaign(db)
    before = (
        db.query(CampaignIteration).count(),
        db.query(PredictionRun).count(),
        db.query(PropertyPrediction).count(),
        db.query(CandidateHypothesis).count(),
        db.query(Candidate).count(),
    )
    preview = preview_campaign(db, campaign)
    after = (
        db.query(CampaignIteration).count(),
        db.query(PredictionRun).count(),
        db.query(PropertyPrediction).count(),
        db.query(CandidateHypothesis).count(),
        db.query(Candidate).count(),
    )
    assert preview["valid"] is True
    assert preview["candidate_pool_size"] > 0
    assert preview["objective_count"] == 2
    assert preview["warning"].startswith("VIRTUAL EVALUATION")
    assert before == after


def test_campaign_reproducibility_envelope_pins_models_and_checksums(db):
    campaign = seeded_campaign(db)
    first = campaign_reproducibility_envelope(db, campaign)
    second = campaign_reproducibility_envelope(db, campaign)
    assert first == second
    assert first["configuration_checksum"] == campaign.configuration_checksum
    assert first["result_checksum"] == campaign.result_checksum
    assert {m["id"] for m in first["model_versions"]} == {TENSILE_VERSION_ID, DENSITY_VERSION_ID}
    assert all(m["artifact_checksum"] for m in first["model_versions"])
    assert all(i["decision_checksum"] for i in first["iterations"])


def test_policy_registry_is_explicit_versioned_and_has_no_ai_score():
    assert {"robust_pareto_v1", "uncertainty_exploration_v1", "lexicographic_pareto_baseline_v1"}.issubset(POLICIES)
    assert all(p.version == "1.0" for p in POLICIES.values())
    assert all(p.maximum_safe_candidate_pool == 200 for p in POLICIES.values())
    assert "score" not in POLICIES["robust_pareto_v1"].uncertainty_semantics.lower()


def test_campaign_validation_rejects_stale_search_space_checksum(db):
    campaign = seeded_campaign(db)
    original = campaign.search_space_checksum
    campaign.search_space_checksum = "0" * 64
    db.flush()
    issues = validate_campaign(db, campaign)
    assert any(i["code"] == "SEARCH_SPACE_CHECKSUM_MISMATCH" for i in issues)
    campaign.search_space_checksum = original
    db.rollback()


def test_campaign_budget_guard_rejects_more_than_phase5_limit(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    payload = {
        "name": "Over budget fixture",
        "description": "test",
        "search_space_id": SEARCH_SPACE_ID,
        "policy_key": "robust_pareto_v1",
        "random_seed": 1,
        "max_iterations": MAX_SYNC_ITERATIONS + 1,
        "max_total_new_candidates": 1,
        "max_candidates_per_iteration": 1,
        "max_parents_per_iteration": 1,
        "created_by": USER_ID,
        "objectives": [{"property_key": "density", "direction": "minimize", "weight": 1.0, "priority": 1, "target_value": None, "target_unit": None, "model_version_id": DENSITY_VERSION_ID, "evaluation_mode": "model_prediction", "metadata": {}}],
        "constraint_policies": [], "initial_candidate_ids": [], "include_known_candidates": False,
        "exploration_enabled": True, "mutation_types": ["component_amount"], "convergence_unchanged_iterations": None, "metadata": {},
    }
    with pytest.raises(ValueError, match="maximum"):
        create_campaign(db, project, payload)


def test_phase5_seed_is_idempotent(db):
    before = (
        db.query(PredictionModel).count(),
        db.query(PredictionModelVersion).count(),
        db.query(VirtualExperimentCampaign).count(),
        db.query(CampaignIteration).count(),
        db.query(VirtualCandidateEvaluation).count(),
        db.query(CandidateHypothesis).count(),
        db.query(MaterialPropertyObservation).count(),
    )
    seed(db)
    after = (
        db.query(PredictionModel).count(),
        db.query(PredictionModelVersion).count(),
        db.query(VirtualExperimentCampaign).count(),
        db.query(CampaignIteration).count(),
        db.query(VirtualCandidateEvaluation).count(),
        db.query(CandidateHypothesis).count(),
        db.query(MaterialPropertyObservation).count(),
    )
    assert before == after


def test_virtual_campaign_api_is_scoped_and_auditable(client, db):
    headers = {"X-Organisation-ID": ORG_ID}
    assert client.get(f"/virtual-campaigns/{CAMPAIGN_ID}").status_code == 404
    detail = client.get(f"/virtual-campaigns/{CAMPAIGN_ID}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["campaign"]["id"] == CAMPAIGN_ID
    assert "not physical experiments" in body["warning"]
    assert len(body["iterations"]) == 2
    preview = client.post(f"/virtual-campaigns/{CAMPAIGN_ID}/preview", headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json()["warning"].startswith("VIRTUAL EVALUATION")


def test_virtual_campaign_iteration_apis_expose_pareto_and_decisions(client, db):
    headers = {"X-Organisation-ID": ORG_ID}
    iteration = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    evaluations = client.get(f"/campaign-iterations/{iteration.id}/evaluations?limit=2", headers=headers)
    assert evaluations.status_code == 200
    assert evaluations.json()["total"] == iteration.evaluated_candidate_count
    assert len(evaluations.json()["items"]) == 2
    front = client.get(f"/campaign-iterations/{iteration.id}/pareto", headers=headers)
    assert front.status_code == 200 and front.json()
    decisions = client.get(f"/campaign-iterations/{iteration.id}/decisions", headers=headers)
    assert decisions.status_code == 200 and decisions.json()
    assert any(d["decision_type"] == "parent_selected" for d in decisions.json())
    assert client.get(f"/campaign-iterations/{iteration.id}/evaluations").status_code == 404


def test_candidate_campaign_history_is_private_and_contains_virtual_origin(client, db):
    headers = {"X-Organisation-ID": ORG_ID}
    first = db.query(CampaignIteration).filter_by(campaign_id=CAMPAIGN_ID, iteration_number=1).one()
    hyp_eval = db.query(VirtualCandidateEvaluation).filter(VirtualCandidateEvaluation.campaign_iteration_id == first.id, VirtualCandidateEvaluation.hypothesis_id.is_not(None)).first()
    assert hyp_eval
    assert client.get(f"/candidate-hypotheses/{hyp_eval.hypothesis_id}/virtual-campaign-history").status_code == 404
    response = client.get(f"/candidate-hypotheses/{hyp_eval.hypothesis_id}/virtual-campaign-history", headers=headers)
    assert response.status_code == 200
    assert response.json()
    assert all(row["scientific_origin"] == "VIRTUAL EVALUATION — MODEL-BASED" for row in response.json())


def test_campaign_configuration_checksum_changes_for_meaningful_configuration(db):
    # We do not mutate immutable completed campaign state; create two draft campaign definitions that differ only in seed.
    project = db.get(ReplacementProject, PROJECT_ID)
    base = {
        "name": "Checksum fixture " + uuid.uuid4().hex[:6], "description": "test", "search_space_id": SEARCH_SPACE_ID,
        "policy_key": "lexicographic_pareto_baseline_v1", "random_seed": 11, "max_iterations": 1,
        "max_total_new_candidates": 0, "max_candidates_per_iteration": 1, "max_parents_per_iteration": 0, "created_by": USER_ID,
        "objectives": [{"property_key": "density", "direction": "minimize", "weight": 1.0, "priority": 1, "target_value": None, "target_unit": None, "model_version_id": DENSITY_VERSION_ID, "evaluation_mode": "model_prediction", "metadata": {}}],
        "constraint_policies": [], "initial_candidate_ids": [], "include_known_candidates": False,
        "exploration_enabled": False, "mutation_types": [], "convergence_unchanged_iterations": None, "metadata": {"test_fixture": True},
    }
    one = create_campaign(db, project, base)
    changed = dict(base)
    changed["name"] = "Checksum fixture " + uuid.uuid4().hex[:6]
    changed["random_seed"] = 12
    two = create_campaign(db, project, changed)
    assert one.configuration_checksum != two.configuration_checksum


def test_virtual_campaign_create_api_validates_model_and_budgets(client):
    headers = {"X-Organisation-ID": ORG_ID}
    response = client.post(
        f"/replacement-projects/{PROJECT_ID}/virtual-campaigns",
        headers=headers,
        json={
            "name": "API invalid model campaign", "search_space_id": SEARCH_SPACE_ID, "policy_key": "robust_pareto_v1",
            "random_seed": 9, "max_iterations": 1, "max_total_new_candidates": 1, "max_candidates_per_iteration": 1,
            "max_parents_per_iteration": 1, "created_by": USER_ID,
            "objectives": [{"property_key": "density", "direction": "minimize", "model_version_id": "does-not-exist"}],
            "constraint_policies": [], "include_known_candidates": False, "exploration_enabled": True,
            "mutation_types": ["component_amount"],
        },
    )
    assert response.status_code == 422


def test_no_physics_or_experimental_status_words_are_used_for_campaign_entities(db):
    campaign = seeded_campaign(db)
    assert campaign.status not in {"validated", "verified", "discovered", "proven"}
    iterations = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).all()
    assert all(i.status not in {"validated", "verified", "discovered", "proven"} for i in iterations)


def _stop_fixture_payload(db, *, initial_candidate_ids, max_total_new_candidates=2, mutation_types=None, name_suffix="stop"):
    return {
        "name": f"{name_suffix}-{uuid.uuid4().hex[:8]}", "description": "Phase-5 stop-condition test fixture", "search_space_id": SEARCH_SPACE_ID,
        "policy_key": "robust_pareto_v1", "random_seed": 77, "max_iterations": 2,
        "max_total_new_candidates": max_total_new_candidates, "max_candidates_per_iteration": 2, "max_parents_per_iteration": 1,
        "created_by": USER_ID,
        "objectives": [
            {"property_key": "tensile_strength", "direction": "maximize", "weight": 1.0, "priority": 1, "target_value": None, "target_unit": None, "model_version_id": TENSILE_VERSION_ID, "evaluation_mode": "model_prediction", "metadata": {"conditions": {"temperature": {"value": 23.0, "unit": "degC"}}}},
            {"property_key": "density", "direction": "minimize", "weight": 1.0, "priority": 2, "target_value": None, "target_unit": None, "model_version_id": DENSITY_VERSION_ID, "evaluation_mode": "model_prediction", "metadata": {}},
        ],
        "constraint_policies": [], "initial_candidate_ids": initial_candidate_ids, "include_known_candidates": False,
        "exploration_enabled": True, "mutation_types": mutation_types if mutation_types is not None else ["component_amount"],
        "convergence_unchanged_iterations": None, "metadata": {"test_fixture": True},
    }


def test_stop_condition_total_new_candidate_budget_is_explicit(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    manual = db.query(CandidateHypothesis).filter_by(project_id=PROJECT_ID, display_label="Manual hypothesis — modest modifier reduction").one()
    candidate = db.query(Candidate).filter_by(project_id=PROJECT_ID, hypothesis_id=manual.id).one()
    campaign = create_campaign(db, project, _stop_fixture_payload(db, initial_candidate_ids=[candidate.id], max_total_new_candidates=0, name_suffix="budget-stop"))
    iterations = run_campaign(db, campaign)
    assert iterations[-1].stop_signal is True
    assert iterations[-1].stop_reason == "total_new_candidate_budget_reached"


def test_stop_condition_no_unique_child_is_explicit(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    manual = db.query(CandidateHypothesis).filter_by(project_id=PROJECT_ID, display_label="Manual hypothesis — modest modifier reduction").one()
    candidate = db.query(Candidate).filter_by(project_id=PROJECT_ID, hypothesis_id=manual.id).one()
    campaign = create_campaign(db, project, _stop_fixture_payload(db, initial_candidate_ids=[candidate.id], mutation_types=[], name_suffix="no-child-stop"))
    iterations = run_campaign(db, campaign)
    assert iterations[-1].stop_signal is True
    assert iterations[-1].stop_reason == "no_structurally_valid_unique_child_generated"


def test_stop_condition_no_applicable_objective_predictions_is_explicit(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    material_c_id = sid("material:demo-polymer-c")
    candidate = db.query(Candidate).filter_by(project_id=PROJECT_ID, material_id=material_c_id).one()
    campaign = create_campaign(db, project, _stop_fixture_payload(db, initial_candidate_ids=[candidate.id], mutation_types=[], name_suffix="no-model-stop"))
    iterations = run_campaign(db, campaign)
    assert iterations[-1].stop_signal is True
    assert iterations[-1].stop_reason == "no_applicable_objective_predictions"
    evaluation = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=iterations[-1].id).one()
    assert evaluation.pareto_rank is None
    assert all(v["completeness"] == "incomplete" for v in evaluation.objective_vector.values())


def test_campaign_cannot_pin_another_organisation_private_model(db):
    project = db.get(ReplacementProject, PROJECT_ID)
    other = Organisation(id=str(uuid.uuid4()), name="Other tenant")
    db.add(other); db.flush()
    version = get_model_version(db, DENSITY_VERSION_ID)
    original_scope = version.model.organisation_id
    version.model.organisation_id = other.id
    db.flush()
    payload = _stop_fixture_payload(db, initial_candidate_ids=[], mutation_types=[], name_suffix="cross-tenant-model")
    payload["objectives"] = [{"property_key": "density", "direction": "minimize", "weight": 1.0, "priority": 1, "target_value": None, "target_unit": None, "model_version_id": DENSITY_VERSION_ID, "evaluation_mode": "model_prediction", "metadata": {}}]
    with pytest.raises(ValueError, match="outside organisation scope"):
        create_campaign(db, project, payload)
    version.model.organisation_id = original_scope
    db.rollback()
