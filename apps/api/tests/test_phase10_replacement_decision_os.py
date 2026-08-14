"""Phase 10 — Closed-Loop Material Replacement Decision OS regression tests.

The tests below are organised around the properties that make the decision defensible rather than
around code structure. The recurring theme is negative: the system must be *unable* to reject on an
UNKNOWN, unable to advance past a blocking failure, unable to turn a conflict into a pass, and
unable to rewrite a conclusion someone already acted on.
"""

from __future__ import annotations

import pytest

from app.domain.enums import (
    CandidateEligibility,
    ConvergenceState,
    EvidenceGapClass,
    MatrixCellStatus,
    ReplacementRecommendationStatus,
    RequirementCriticality,
    ScientificActionStatus,
)
from app.models.entities import (
    Candidate,
    ConvergenceAssessment,
    FunctionalRequirement,
    MaterialState,
    Organisation,
    ReplacementProgram,
    ScientificAction,
)
from app.services.replacement.actions import compute_actions, persist_actions
from app.services.replacement.context import PortfolioContext
from app.services.replacement.convergence import assess_convergence, persist_convergence
from app.services.replacement.coverage import coverage_for_candidate, decision_matrix
from app.services.replacement.dossier import (
    build_snapshot_payload,
    create_snapshot,
    generate_dossier,
)
from app.services.replacement.gaps import gaps_for_candidate, program_gaps
from app.services.replacement.policy import resolve_criticality
from app.services.replacement.portfolio import candidate_decision_state
from app.services.replacement.programs import ProgramError, create_program, resolve_program_state
from app.services.replacement.ranking import pareto_front, rank_candidates, sensitivity_analysis
from app.services.replacement.recommendation import (
    build_recommendation,
    explain_candidate,
    generate_recommendation,
)

DEMO_PROGRAM_KEY = "ht_silicon_replacement_demo"


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
@pytest.fixture()
def program(db):
    row = (
        db.query(ReplacementProgram)
        .filter(ReplacementProgram.key == DEMO_PROGRAM_KEY)
        .one()
    )
    return row


@pytest.fixture()
def context(db, program):
    return PortfolioContext(db, program)


def _candidate_named(context, fragment: str):
    return next(v for v in context.candidates if fragment in v.display_name)


@pytest.fixture()
def candidate_a(context):
    return _candidate_named(context, "alpha")


@pytest.fixture()
def candidate_b(context):
    return _candidate_named(context, "beta")


@pytest.fixture()
def candidate_c(context):
    return _candidate_named(context, "gamma")


# ---------------------------------------------------------------------------------------------
# Program model and references
# ---------------------------------------------------------------------------------------------
def test_program_cannot_reference_another_organisations_project(db, program):
    other_org = Organisation(name="Another organisation")
    db.add(other_org)
    db.flush()
    with pytest.raises(ProgramError) as excinfo:
        create_program(
            db, organisation_id=other_org.id,
            values={"project_id": program.project_id, "key": "stolen", "name": "Stolen programme"},
        )
    assert "PROJECT_NOT_FOUND" in str(excinfo.value)
    db.rollback()


def test_incumbent_state_must_belong_to_incumbent_material(db, program):
    foreign_state = (
        db.query(MaterialState)
        .filter(MaterialState.organisation_id == program.organisation_id,
                MaterialState.material_id.isnot(None),
                MaterialState.material_id != program.incumbent_material_id)
        .first()
    )
    assert foreign_state is not None
    with pytest.raises(ProgramError) as excinfo:
        create_program(
            db, organisation_id=program.organisation_id,
            values={
                "project_id": program.project_id, "key": "mismatched",
                "name": "Mismatched programme",
                "incumbent_material_id": program.incumbent_material_id,
                "incumbent_state_id": foreign_state.id,
            },
        )
    assert "INCUMBENT_STATE_MISMATCH" in str(excinfo.value)
    db.rollback()


def test_program_state_is_resolved_not_set_by_the_client(db, program):
    resolved = resolve_program_state(db, program)
    assert resolved["status"] in {
        "screening", "validating", "experimenting", "converging", "decision_ready", "recommended",
    }
    assert resolved["methodology_version"] == "program-state-v1"


def test_candidate_ids_are_stable_across_repeated_assessment(db, program):
    first = [v.candidate_id for v in PortfolioContext(db, program).candidates]
    second = [v.candidate_id for v in PortfolioContext(db, program).candidates]
    assert first == second
    assert len(set(first)) == len(first)


def test_portfolio_accepts_known_materials_and_hypotheses(db, program):
    context = PortfolioContext(db, program)
    kinds = {v.candidate_kind for v in context.candidates}
    assert kinds.issubset({"known_material", "hypothesis"})
    assert context.candidates, "the demonstration programme must have a populated portfolio"


# ---------------------------------------------------------------------------------------------
# Requirement criticality and origin
# ---------------------------------------------------------------------------------------------
def test_criticality_backfills_deterministically_from_requirement_kind(db):
    for requirement in db.query(FunctionalRequirement).all():
        resolved = resolve_criticality(requirement)
        assert resolved in {c.value for c in RequirementCriticality}
        if requirement.requirement_kind == "hard_constraint":
            assert resolved in {
                RequirementCriticality.BLOCKING, RequirementCriticality.CRITICAL
            }
        if requirement.requirement_kind == "objective":
            assert resolved == RequirementCriticality.DESIRABLE


def test_hard_gates_and_optimization_objectives_are_not_the_same_concept(context, candidate_a):
    rows = coverage_for_candidate(context, candidate_a)
    objective_rows = [r for r in rows if str(r["requirement_kind"]) == "objective"]
    assert objective_rows, "the demonstration set must contain an objective"
    for row in objective_rows:
        assert row["is_gating"] is False


def test_proposed_requirement_is_not_authoritative(db, context, candidate_a):
    requirement = next(
        r for r in context.requirements if resolve_criticality(r) == RequirementCriticality.BLOCKING
    )
    original = requirement.approval_status
    requirement.approval_status = "proposed"
    db.flush()
    try:
        fresh = PortfolioContext(db, context.program)
        view = _candidate_named(fresh, "alpha")
        rows = coverage_for_candidate(fresh, view)
        row = next(r for r in rows if r["requirement_id"] == requirement.id)
        assert row["is_gating"] is False, "a PROPOSED requirement must not gate a decision"
    finally:
        requirement.approval_status = original
        db.flush()


# ---------------------------------------------------------------------------------------------
# Decision matrix and coverage
# ---------------------------------------------------------------------------------------------
def test_matrix_exposes_governing_evidence_per_cell(context, candidate_a):
    matrix = decision_matrix(context)
    row = next(r for r in matrix["rows"] if r["requirement_key"] == "ht_min_band_gap")
    cell = row["cells"][candidate_a.candidate_id]
    assert cell["status"] == MatrixCellStatus.PASS
    assert cell["governing_origin"] is not None
    assert cell["governing_evidence"] is not None
    assert cell["outcomes"], "the cell must carry the per-origin outcomes that produced it"


def test_matrix_is_not_collapsed_into_a_single_score(context):
    matrix = decision_matrix(context)
    assert "rows" in matrix and matrix["rows"]
    assert "score" not in matrix
    for row in matrix["rows"]:
        for cell in row["cells"].values():
            assert cell["status"] in {s.value for s in MatrixCellStatus}


def test_conflicting_evidence_never_becomes_pass(context, candidate_b):
    rows = coverage_for_candidate(context, candidate_b)
    conflicting = [r for r in rows if str(r["governing_status"]) == MatrixCellStatus.CONFLICTING]
    assert conflicting, "candidate B is seeded so an observation and a measurement disagree"
    for row in conflicting:
        assert str(row["governing_status"]) != MatrixCellStatus.PASS


def test_coverage_distinguishes_availability_from_success(context, candidate_b):
    rows = coverage_for_candidate(context, candidate_b)
    row = next(r for r in rows if r["requirement_key"] == "ht_min_breakdown_field")
    # Candidate B is fully evidenced on this requirement and simultaneously not suitable for it.
    assert row["coverage_score"] == 1.0
    assert str(row["governing_status"]) != MatrixCellStatus.PASS


def test_unknown_requirement_reports_no_evidence_rather_than_failure(context, candidate_c):
    rows = coverage_for_candidate(context, candidate_c)
    row = next(r for r in rows if r["requirement_key"] == "ht_min_breakdown_field")
    assert str(row["governing_status"]) == MatrixCellStatus.UNKNOWN
    assert row["coverage_score"] < 1.0


# ---------------------------------------------------------------------------------------------
# Eligibility: the safety property
# ---------------------------------------------------------------------------------------------
def test_definitive_blocking_failure_makes_candidate_ineligible(context, candidate_b):
    state = candidate_decision_state(context, candidate_b)
    assert state["eligibility"] == CandidateEligibility.BLOCKED
    assert state["definitive_blocking_failures"]
    assert state["gates_satisfied"] is False


def test_unknown_does_not_automatically_reject_candidate(context, candidate_c):
    state = candidate_decision_state(context, candidate_c)
    assert state["eligibility"] == CandidateEligibility.UNRESOLVED
    assert state["definitive_blocking_failures"] == []


def test_inconclusive_and_not_comparable_do_not_reject(context):
    for view in context.candidates:
        state = candidate_decision_state(context, view)
        for failure in state["definitive_blocking_failures"]:
            assert str(failure["status"]) == MatrixCellStatus.FAIL, (
                "only a definitive FAIL may appear as a blocking failure"
            )


def test_eligible_candidate_can_reach_decision_ready(context, candidate_a):
    state = candidate_decision_state(context, candidate_a)
    assert state["eligibility"] == CandidateEligibility.ELIGIBLE
    assert state["gates_satisfied"] is True
    assert state["portfolio_state"] == "decision_ready"


def test_every_gate_reports_its_reason(context, candidate_c):
    state = candidate_decision_state(context, candidate_c)
    assert state["gate_results"]
    for gate in state["gate_results"]:
        assert gate["reason"], f"gate {gate['gate']} must explain itself"


def test_unimplemented_policy_gate_is_reported_not_assumed_satisfied(db, context, candidate_a):
    policy = context.policy
    original = list(policy.required_gates or [])
    policy.required_gates = original + ["SOME_FUTURE_GATE"]
    db.flush()
    try:
        fresh = PortfolioContext(db, context.program)
        view = _candidate_named(fresh, "alpha")
        state = candidate_decision_state(fresh, view)
        unknown = next(g for g in state["gate_results"] if g["gate"] == "SOME_FUTURE_GATE")
        assert unknown["satisfied"] is False
        assert unknown["evidence"]["reason_code"] == "GATE_NOT_IMPLEMENTED"
        assert state["gates_satisfied"] is False
    finally:
        policy.required_gates = original
        db.flush()


# ---------------------------------------------------------------------------------------------
# Evidence gaps
# ---------------------------------------------------------------------------------------------
def test_missing_blocking_evidence_generates_blocking_gap(context, candidate_c):
    gaps = gaps_for_candidate(context, candidate_c)
    blocking = [g for g in gaps if str(g["gap_class"]) == EvidenceGapClass.BLOCKING_GAP]
    assert blocking, "an unevidenced BLOCKING requirement must produce a blocking gap"
    assert all(g["why_unresolved"] for g in blocking)


def test_resolved_evidence_produces_no_gap_for_that_requirement(context, candidate_a):
    gaps = gaps_for_candidate(context, candidate_a)
    requirement_gaps = {g["requirement_key"] for g in gaps}
    assert "ht_min_band_gap" not in requirement_gaps


def test_gap_classes_are_ordered_blocking_first(context):
    payload = program_gaps(context)
    classes = [str(g["gap_class"]) for g in payload["gaps"]]
    order = {c.value: i for i, c in enumerate(EvidenceGapClass)}
    assert classes == sorted(classes, key=lambda c: order[c])


def test_gap_never_claims_a_candidate_failed(context):
    payload = program_gaps(context)
    for gap in payload["gaps"]:
        assert str(gap["governing_status"]) != MatrixCellStatus.FAIL


# ---------------------------------------------------------------------------------------------
# Next-best action
# ---------------------------------------------------------------------------------------------
def test_next_action_is_deterministic(context):
    first = compute_actions(context)
    second = compute_actions(PortfolioContext(context.db, context.program))
    assert [a["action_signature"] for a in first["actions"]] == [
        a["action_signature"] for a in second["actions"]
    ]
    assert [a["priority"] for a in first["actions"]] == [a["priority"] for a in second["actions"]]


def test_priority_is_not_called_expected_value_of_information(context):
    """Priority must be a declared decision-value model, not a probability-weighted EVOI.

    The note field is allowed — and expected — to *deny* being an expected value of information.
    What must not exist is a factor that is one: no probability, no likelihood, no estimated outcome
    distribution feeding the score.
    """
    payload = compute_actions(context)
    banned_factor_terms = ("probability", "likelihood", "expected_value", "confidence", "odds")
    for action in payload["actions"]:
        factors = action["priority_factors"]
        for key in factors:
            assert not any(term in str(key).lower() for term in banned_factor_terms), (
                f"priority factor '{key}' implies a probabilistic estimate"
            )
        # The formula must be reproducible from the declared factors alone.
        assert "priority = " in factors["formula"]
        assert "no expected value of information is claimed" in factors["note"].lower()
        assert "no probability distribution" in factors["note"].lower()


def test_action_priority_factors_reproduce_the_score(context):
    payload = compute_actions(context)
    for action in payload["actions"]:
        factors = action["priority_factors"]
        if "decision_impact" not in factors:
            continue
        expected = round(
            (factors["decision_impact"] * factors["decision_value"] * factors["candidate_relevance"])
            / factors["cost_factor"], 6,
        )
        assert action["priority"] == expected


def test_blocking_gap_outranks_optional_gap(context):
    payload = compute_actions(context)
    blocking = [a for a in payload["actions"] if a.get("gap_class") == EvidenceGapClass.BLOCKING_GAP]
    optional = [a for a in payload["actions"] if a.get("gap_class") == EvidenceGapClass.OPTIONAL_GAP]
    if blocking and optional:
        assert max(a["priority"] for a in blocking) > max(a["priority"] for a in optional)


def test_action_dependencies_prevent_execution_before_prerequisites(context):
    payload = compute_actions(context)
    by_signature = {a["action_signature"]: a for a in payload["actions"]}
    for action in payload["actions"]:
        for dependency in action.get("depends_on", []):
            assert dependency in by_signature
            assert action["status"] == ScientificActionStatus.BLOCKED


def test_no_llm_selects_the_next_action(context):
    payload = compute_actions(context)
    assert "no language model" in payload["determinism_note"].lower()


def test_recommending_an_action_never_starts_it(context):
    payload = compute_actions(context)
    assert "never starts it" in payload["authorization_note"].lower()


def test_actions_are_superseded_not_deleted(db, program, context):
    computed = compute_actions(context)
    persist_actions(db, context, computed)
    db.flush()
    stored = (
        db.query(ScientificAction)
        .filter(ScientificAction.program_id == program.id)
        .all()
    )
    assert stored
    orphan = ScientificAction(
        organisation_id=program.organisation_id, program_id=program.id,
        candidate_id=None, requirement_id=None, action_type="collect_reference_data",
        action_signature="stale:signature:that:is:no:longer:recommended",
        status="proposed", priority=0.1, priority_factors={}, decision_value_class="low",
        cost_class="low", reason_code="STALE", reason="Stale action for the supersession test.",
        depends_on=[], methodology_version="next-action-v1",
    )
    db.add(orphan)
    db.flush()
    persist_actions(db, context, compute_actions(PortfolioContext(db, program)))
    db.flush()
    db.refresh(orphan)
    assert orphan.status == ScientificActionStatus.SUPERSEDED
    assert db.get(ScientificAction, orphan.id) is not None, "actions are never deleted"


# ---------------------------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------------------------
def test_convergence_does_not_treat_unresolved_blocking_as_decision_ready(context):
    payload = assess_convergence(context)
    if payload["metrics"]["blocking_evidence_gaps"] > 0:
        assert payload["convergence_state"] != ConvergenceState.DECISION_READY


def test_convergence_does_not_claim_probability(context):
    payload = assess_convergence(context)
    assert "probability" in payload["probability_disclaimer"].lower()
    assert "not a probability" in payload["note"].lower()
    assert 0.0 <= payload["presentation_progress_percent"] <= 100.0


def test_convergence_retains_underlying_metrics(context):
    payload = assess_convergence(context)
    for key in (
        "blocking_requirements_resolved", "blocking_requirements_total",
        "critical_requirements_resolved", "experimental_requirements_validated",
        "industrial_dimensions_resolved", "unresolved_conflicts", "open_mandatory_actions",
    ):
        assert key in payload["metrics"]


def test_convergence_assessment_supersedes_without_rewriting(db, program, context):
    first = persist_convergence(db, context, assess_convergence(context))
    second = persist_convergence(db, context, assess_convergence(PortfolioContext(db, program)))
    db.flush()
    db.refresh(first)
    assert first.superseded_by_id == second.id
    assert db.get(ConvergenceAssessment, first.id) is not None


# ---------------------------------------------------------------------------------------------
# Ranking, Pareto, sensitivity
# ---------------------------------------------------------------------------------------------
def test_weighted_ranking_excludes_blocked_candidates(context, candidate_b):
    ranking = rank_candidates(context)
    ranked_ids = {row["candidate_id"] for row in ranking["ranked"]}
    assert candidate_b.candidate_id not in ranked_ids
    excluded = next(r for r in ranking["excluded"] if r["candidate_id"] == candidate_b.candidate_id)
    assert "blocking" in excluded["reason"].lower()


def test_ranking_reports_every_factor_and_weight(context):
    ranking = rank_candidates(context)
    for row in ranking["ranked"]:
        assert row["normalized_factors"]
        assert row["weights"]
        assert "excluded_dimensions" in row
        assert "hard_blockers" in row
        assert row["methodology_version"] == "candidate-ranking-v1"


def test_ranking_is_not_a_probability(context):
    ranking = rank_candidates(context)
    assert "not a quality score and not a probability" in ranking["note"]


def test_pareto_front_and_domination_are_calculated_correctly():
    normalized = {
        "performance": {"a": 1.0, "b": 0.5, "c": 0.4},
        "cost": {"a": 0.2, "b": 0.9, "c": 0.1},
    }
    result = pareto_front(normalized, ["a", "b", "c"])
    assert set(result["front_candidate_ids"]) == {"a", "b"}
    # c is worse than a on both objectives, so a dominates it.
    assert "a" in result["dominated_by"]["c"]
    assert "c" not in result["front_candidate_ids"]


def test_pareto_skips_objectives_where_evidence_is_missing():
    normalized = {
        "performance": {"a": 1.0, "b": 0.5},
        "cost": {"a": None, "b": 0.9},
    }
    result = pareto_front(normalized, ["a", "b"])
    # Only `performance` is comparable, and a beats b there, so b is dominated on that basis alone.
    assert "a" in result["dominated_by"].get("b", [])
    assert result["front_candidate_ids"] == ["a"]


def test_sensitivity_analysis_is_deterministic_and_bounded(context):
    first = sensitivity_analysis(context)
    second = sensitivity_analysis(PortfolioContext(context.db, context.program))
    assert first["stability"] == second["stability"]
    assert first["scenario_count"] == second["scenario_count"]
    assert first["scenario_count"] <= int(
        (context.policy.sensitivity_bounds or {}).get("max_scenarios", 64)
    )


def test_sensitivity_does_not_fabricate_a_distribution(context):
    payload = sensitivity_analysis(context)
    if payload["scenario_count"]:
        assert "no probability distribution" in payload["note"].lower()


# ---------------------------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------------------------
def test_recommendation_includes_policy_and_methodology_versions(context):
    payload = build_recommendation(context)
    assert payload["decision_policy_version"]
    for key in ("recommendation", "convergence", "ranking", "next_action", "evidence_gap"):
        assert key in payload["methodology_versions"]


def test_recommendation_is_not_commercial_certification(context):
    payload = build_recommendation(context)
    note = payload["qualification_note"].lower()
    assert "do not replace required regulatory" in note
    assert "not authorization" in note


def test_recommendation_reports_advance_reject_and_hold_separately(context):
    payload = build_recommendation(context)
    assert payload["status"] == ReplacementRecommendationStatus.ADVANCE_CANDIDATE
    assert len(payload["recommended_candidate_ids"]) == 1
    assert len(payload["rejected_candidate_ids"]) == 1
    assert len(payload["held_candidate_ids"]) == 1


def test_recommendation_rationale_names_requirements_not_scores(context):
    payload = build_recommendation(context)
    assert "ht_min_breakdown_field" in payload["rationale"]
    assert "decision policy version" in payload["rationale"]


def test_recommendation_is_immutable_and_new_evidence_creates_a_new_version(db, program):
    first = generate_recommendation(db, program)
    db.flush()
    second = generate_recommendation(db, program)
    db.flush()
    assert second["version"] == first["version"] + 1
    assert second["recommendation_id"] != first["recommendation_id"]
    assert second["decision_delta_id"] is not None


def test_decision_delta_identifies_what_changed(db, program):
    generate_recommendation(db, program)
    db.flush()
    result = generate_recommendation(db, program)
    db.flush()
    from app.models.entities import DecisionDelta

    delta = db.get(DecisionDelta, result["decision_delta_id"])
    assert delta is not None
    assert delta.methodology_version == "decision-delta-v1"
    assert delta.explanation


def test_no_suitable_candidate_is_reachable(db, program):
    """A portfolio where every candidate is blocked must say so rather than pick a least-bad one."""
    context = PortfolioContext(db, program)
    unblocked = [
        v for v in context.candidates
        if candidate_decision_state(context, v)["eligibility"] != CandidateEligibility.BLOCKED
    ]
    removed = []
    try:
        for view in unblocked:
            row = db.get(Candidate, view.candidate_id)
            removed.append(row)
            db.delete(row)
        db.flush()
        fresh = PortfolioContext(db, program)
        payload = build_recommendation(fresh)
        assert payload["status"] == ReplacementRecommendationStatus.NO_SUITABLE_CANDIDATE
        assert payload["possible_program_actions"], "the user must be told what they could do next"
        assert "never relaxes a requirement automatically" in payload["requirement_relaxation_note"]
    finally:
        db.rollback()


# ---------------------------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------------------------
def test_explanation_answers_the_decision_questions(context, candidate_b):
    payload = explain_candidate(context, candidate_b.candidate_id)
    for key in (
        "why_proposed", "why_requirements_passed", "why_requirements_failed", "why_blocked",
        "why_experiment_recommended", "why_ranked",
    ):
        assert key in payload
    assert "ht_min_breakdown_field" in payload["why_blocked"]
    assert "no language model" in payload["llm_boundary_note"].lower()


# ---------------------------------------------------------------------------------------------
# Snapshots, dossier and reproducibility
# ---------------------------------------------------------------------------------------------
def test_program_snapshot_checksum_is_deterministic(db, program):
    first = build_snapshot_payload(PortfolioContext(db, program))
    second = build_snapshot_payload(PortfolioContext(db, program))
    assert first["snapshot_checksum"] == second["snapshot_checksum"]
    assert len(first["snapshot_checksum"]) == 64


def test_snapshot_captures_the_policy_that_produced_the_decision(db, program):
    payload = build_snapshot_payload(PortfolioContext(db, program))
    assert payload["decision_policy_ref"]["version"]
    assert payload["decision_policy_ref"]["policy_checksum"]
    assert payload["methodology_versions"]["snapshot"] == "program-snapshot-v1"


def test_dossier_contains_only_evidence_linked_to_the_snapshot(db, program):
    snapshot = create_snapshot(db, program, label="test snapshot")
    dossier = generate_dossier(db, program, snapshot_id=snapshot.id)
    db.flush()
    assert len(dossier.sections) == 23
    provenance = next(s for s in dossier.sections if s["number"] == 21)["content"]
    referenced = {
        str(row.get("source_id")) for row in provenance["scientific_evidence_ref"]
        if row.get("source_id")
    }
    for evidence_id in dossier.evidence_ids:
        assert evidence_id in referenced or any(
            evidence_id == str(row.get("measurement_id"))
            for row in provenance["experimental_evidence_ref"]
        ) or any(
            evidence_id == str(row.get("id")) for row in provenance["industrial_evidence_ref"]
        )


def test_dossier_does_not_invent_missing_values(db, program):
    dossier = generate_dossier(db, program)
    db.flush()
    incumbent = next(s for s in dossier.sections if s["number"] == 3)["content"]
    # Silicon has no seeded property values, so the profile must say UNKNOWN rather than guess.
    serialized = str(incumbent)
    assert "UNKNOWN" in serialized
    assert dossier.llm_narrative_used is False


def test_dossier_regeneration_creates_a_new_version(db, program):
    first = generate_dossier(db, program)
    db.flush()
    second = generate_dossier(db, program)
    db.flush()
    assert second.version == first.version + 1
    assert db.get(type(first), first.id) is not None


def test_dossier_states_that_it_is_not_commercial_qualification(db, program):
    dossier = generate_dossier(db, program)
    db.flush()
    recommendation_section = next(s for s in dossier.sections if s["number"] == 19)["content"]
    assert "do not replace required regulatory" in recommendation_section["qualification_note"].lower()


# ---------------------------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------------------------
def test_cross_tenant_program_access_fails(client, db, program):
    response = client.get(
        f"/replacement-programs/{program.id}",
        headers={"X-Organisation-ID": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_cross_tenant_recommendation_and_snapshot_access_fails(client, program):
    headers = {"X-Organisation-ID": "00000000-0000-0000-0000-000000000000"}
    for path in ("recommendation", "snapshots", "dossiers", "timeline", "portfolio",
                 "decision-matrix", "evidence-gaps", "convergence", "actions"):
        response = client.get(f"/replacement-programs/{program.id}/{path}", headers=headers)
        assert response.status_code == 404, path


def test_request_without_organisation_scope_is_refused(client, program):
    assert client.get(f"/replacement-programs/{program.id}").status_code == 404


def test_cross_tenant_evidence_cannot_enter_portfolio_assessment(db, program):
    """A hypothesis owned by another organisation must not be assessed into this portfolio."""
    other_org = Organisation(name="Foreign organisation for isolation test")
    db.add(other_org)
    db.flush()
    context = PortfolioContext(db, program)
    for view in context.candidates:
        if view.target_kind == "hypothesis":
            from app.models.entities import CandidateHypothesis

            hypothesis = db.get(CandidateHypothesis, view.target_id)
            assert hypothesis.organisation_id == program.organisation_id
    db.rollback()


# ---------------------------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------------------------
def test_portfolio_endpoint_returns_requirement_level_comparison(client, program):
    headers = {"X-Organisation-ID": program.organisation_id}
    response = client.get(f"/replacement-programs/{program.id}/decision-matrix", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["rows"]
    assert body["candidates"]
    assert "incumbent" in body


def test_recommendation_endpoint_generates_and_returns_versions(client, program):
    headers = {"X-Organisation-ID": program.organisation_id}
    created = client.post(f"/replacement-programs/{program.id}/recommendation", headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] in {s.value for s in ReplacementRecommendationStatus}
    listed = client.get(f"/replacement-programs/{program.id}/recommendations", headers=headers)
    assert listed.status_code == 200
    assert listed.json()


def test_program_override_rejects_non_operator_states(client, program):
    headers = {"X-Organisation-ID": program.organisation_id}
    response = client.patch(
        f"/replacement-programs/{program.id}", headers=headers,
        json={"status_override": "decision_ready"},
    )
    assert response.status_code == 400
    assert "INVALID_OVERRIDE" in response.json()["detail"]


def test_unknown_event_kind_is_refused(client, program):
    headers = {"X-Organisation-ID": program.organisation_id}
    response = client.post(
        f"/replacement-programs/{program.id}/events", headers=headers,
        json={"event_kind": "definitely_not_a_real_event"},
    )
    assert response.status_code == 400


def test_event_for_foreign_candidate_is_refused(client, program):
    headers = {"X-Organisation-ID": program.organisation_id}
    response = client.post(
        f"/replacement-programs/{program.id}/events", headers=headers,
        json={"event_kind": "measurement_accepted",
              "candidate_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert response.status_code == 404
