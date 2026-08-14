"""Phase 10 — Golden end-to-end workflow test.

One scenario, walked the whole way: requirements -> candidates -> evidence -> matrix -> gaps ->
actions -> convergence -> recommendation -> snapshot -> dossier. Then the loop is closed by adding
genuinely new evidence for the held candidate and asserting that the system reassesses
deterministically, issues a *new* recommendation version, and explains the change in a decision
delta rather than silently rewriting the old conclusion.

The three candidates in the seeded programme are built so each of the three real outcomes occurs:

    alpha  -> advanced   (evidence complete and consistent, every gate satisfied)
    beta   -> rejected   (replicated measurement contradicts a BLOCKING requirement)
    gamma  -> held       (two BLOCKING requirements have no evidence at all)
"""

from __future__ import annotations

import pytest

from app.domain.enums import (
    CandidateEligibility,
    EvidenceGapClass,
    EvidenceGapKind,
    MatrixCellStatus,
    ReplacementRecommendationStatus,
)
from app.models.entities import (
    DecisionDelta,
    Evidence,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    ReplacementProgram,
    ScientificAction,
)
from app.services.replacement.actions import compute_actions
from app.services.replacement.context import PortfolioContext
from app.services.replacement.convergence import assess_convergence
from app.services.replacement.coverage import coverage_for_candidate, decision_matrix
from app.services.replacement.dossier import (
    build_snapshot_payload,
    create_snapshot,
    generate_dossier,
)
from app.services.replacement.gaps import gaps_for_candidate
from app.services.replacement.portfolio import candidate_decision_state, portfolio_board
from app.services.replacement.programs import emit_evidence_event
from app.services.replacement.ranking import rank_candidates
from app.services.replacement.recommendation import (
    build_recommendation,
    explain_candidate,
    generate_recommendation,
)

DEMO_PROGRAM_KEY = "ht_silicon_replacement_demo"


@pytest.fixture()
def program(db):
    return db.query(ReplacementProgram).filter(ReplacementProgram.key == DEMO_PROGRAM_KEY).one()


def _named(context, fragment):
    return next(v for v in context.candidates if fragment in v.display_name)


def test_golden_replacement_workflow_end_to_end(db, program):
    context = PortfolioContext(db, program)

    # --- 1. Requirements exist and are classified for the decision gate ----------------------
    requirement_keys = {r.key for r in context.requirements}
    assert {"ht_min_breakdown_field", "ht_min_band_gap", "ht_min_thermal_conductivity"} <= requirement_keys
    blocking = [r for r in context.requirements if context.criticality_of(r.id) == "blocking"]
    assert len(blocking) == 3

    alpha, beta, gamma = _named(context, "alpha"), _named(context, "beta"), _named(context, "gamma")

    # --- 2. The decision matrix reports per-requirement, per-origin outcomes ------------------
    matrix = decision_matrix(context)
    assert len(matrix["rows"]) == len(context.requirements)
    breakdown_row = next(r for r in matrix["rows"] if r["requirement_key"] == "ht_min_breakdown_field")
    assert breakdown_row["cells"][alpha.candidate_id]["status"] == MatrixCellStatus.PASS
    assert breakdown_row["cells"][beta.candidate_id]["status"] in {
        MatrixCellStatus.FAIL, MatrixCellStatus.CONFLICTING
    }
    assert breakdown_row["cells"][gamma.candidate_id]["status"] == MatrixCellStatus.UNKNOWN

    # The incumbent has no fabricated values, so its column is honestly empty.
    assert "incumbent" in matrix

    # --- 3. Three distinct eligibility outcomes ----------------------------------------------
    alpha_state = candidate_decision_state(context, alpha)
    beta_state = candidate_decision_state(context, beta)
    gamma_state = candidate_decision_state(context, gamma)

    assert alpha_state["eligibility"] == CandidateEligibility.ELIGIBLE
    assert alpha_state["gates_satisfied"] is True

    assert beta_state["eligibility"] == CandidateEligibility.BLOCKED
    assert any(
        f["requirement_key"] == "ht_min_breakdown_field"
        for f in beta_state["definitive_blocking_failures"]
    )

    assert gamma_state["eligibility"] == CandidateEligibility.UNRESOLVED
    assert gamma_state["definitive_blocking_failures"] == [], (
        "missing evidence must never be recorded as a failure"
    )

    # --- 4. Gaps and next actions ------------------------------------------------------------
    gamma_gaps = gaps_for_candidate(context, gamma)
    assert any(str(g["gap_class"]) == EvidenceGapClass.BLOCKING_GAP for g in gamma_gaps)

    actions = compute_actions(context)
    gamma_actions = [a for a in actions["actions"] if a["candidate_id"] == gamma.candidate_id]
    assert gamma_actions, "a held candidate must be told what would resolve it"
    assert gamma_actions[0]["what_it_could_resolve"]

    # --- 5. Ranking excludes what it must ----------------------------------------------------
    ranking = rank_candidates(context)
    ranked_ids = {row["candidate_id"] for row in ranking["ranked"]}
    assert alpha.candidate_id in ranked_ids
    assert beta.candidate_id not in ranked_ids, "a blocked candidate is never ranked"
    assert gamma.candidate_id not in ranked_ids, "an unresolved candidate is never ranked"

    # --- 6. Convergence and recommendation ---------------------------------------------------
    convergence = assess_convergence(context)
    assert convergence["metrics"]["blocked_candidate_count"] == 1
    assert convergence["metrics"]["eligible_candidate_count"] == 1

    recommendation = build_recommendation(context)
    assert recommendation["status"] == ReplacementRecommendationStatus.ADVANCE_CANDIDATE
    assert recommendation["recommended_candidate_ids"] == [alpha.candidate_id]
    assert recommendation["rejected_candidate_ids"] == [beta.candidate_id]
    assert recommendation["held_candidate_ids"] == [gamma.candidate_id]
    assert "ht_min_breakdown_field" in recommendation["rationale"]

    # --- 7. Explainability -------------------------------------------------------------------
    explanation = explain_candidate(context, beta.candidate_id)
    assert "ht_min_breakdown_field" in explanation["why_blocked"]

    # --- 8. Snapshot and dossier -------------------------------------------------------------
    snapshot = create_snapshot(db, program, label="golden workflow")
    db.flush()
    assert len(snapshot.snapshot_checksum) == 64
    dossier = generate_dossier(db, program, snapshot_id=snapshot.id)
    db.flush()
    assert len(dossier.sections) == 23
    assert dossier.llm_narrative_used is False

    board = portfolio_board(context)
    assert board["counts"]["eligible"] == 1
    assert board["counts"]["blocked"] == 1
    assert board["counts"]["unresolved"] == 1


def test_new_evidence_closes_the_loop_deterministically(db, program):
    """Adding real evidence for the held candidate must reassess and re-explain, not overwrite."""
    context = PortfolioContext(db, program)
    gamma = _named(context, "gamma")
    gamma_material_id = gamma.target_id

    before_state = candidate_decision_state(context, gamma)
    before_gaps = gaps_for_candidate(context, gamma)
    before_blocking_gaps = [
        g for g in before_gaps if str(g["gap_class"]) == EvidenceGapClass.BLOCKING_GAP
    ]
    assert before_state["eligibility"] == CandidateEligibility.UNRESOLVED
    assert before_blocking_gaps

    first = generate_recommendation(db, program)
    db.flush()

    # Same inputs must produce the same conclusion: determinism before anything changes.
    repeat = build_recommendation(PortfolioContext(db, program))
    assert repeat["recommendation_checksum"] == build_recommendation(
        PortfolioContext(db, program)
    )["recommendation_checksum"]

    # --- introduce genuinely new evidence -----------------------------------------------------
    evidence = db.query(Evidence).filter(Evidence.evidence_type == "seed_demo").first()
    definitions = {
        key: db.query(MaterialPropertyDefinition).filter_by(key=key).one()
        for key in ("breakdown_field", "thermal_conductivity")
    }
    added = []
    for property_key, value, unit in (
        ("breakdown_field", 2.6, "MV/cm"),
        ("thermal_conductivity", 310.0, "W/(m*K)"),
    ):
        row = MaterialPropertyObservation(
            material_id=gamma_material_id,
            property_definition_id=definitions[property_key].id,
            value_type="numeric", numeric_value=value, unit=unit,
            conditions={"temperature_k": 525.0}, evidence_id=evidence.id if evidence else None,
            method="Synthetic seed fixture (closed-loop test)", confidence=1.0, status="active",
            curator_note="SYNTHETIC value introduced by the closed-loop regression test.",
        )
        db.add(row)
        added.append(row)
    db.flush()

    result = emit_evidence_event(
        db, program=program, kind="observation_added",
        summary="New computational evidence recorded for the held candidate.",
        candidate_ids=[gamma.candidate_id],
    )
    db.flush()
    assert result["recomputed"] is True
    assert gamma.candidate_id in result["affected_candidate_ids"]

    # --- the held candidate has genuinely moved ------------------------------------------------
    after_context = PortfolioContext(db, program)
    after_gamma = _named(after_context, "gamma")
    after_coverage = coverage_for_candidate(after_context, after_gamma)
    breakdown_row = next(
        r for r in after_coverage if r["requirement_key"] == "ht_min_breakdown_field"
    )
    assert str(breakdown_row["governing_status"]) == MatrixCellStatus.PASS, (
        "the newly supplied evidence must be used, not ignored"
    )
    after_gaps = gaps_for_candidate(after_context, after_gamma)
    after_by_requirement = {g["requirement_key"]: g for g in after_gaps}
    before_by_requirement = {g["requirement_key"]: g for g in before_gaps}

    # The gap does not vanish — the policy still wants physical validation for a BLOCKING
    # requirement — but it must change from "nothing is known" to "the experiment is outstanding",
    # and the coverage score must rise. Anything else would mean the new evidence was ignored.
    before_gap = before_by_requirement["ht_min_breakdown_field"]
    after_gap = after_by_requirement["ht_min_breakdown_field"]
    assert str(EvidenceGapKind.MISSING_ALL_EVIDENCE) in [str(k) for k in before_gap["gap_kinds"]]
    assert str(EvidenceGapKind.MISSING_ALL_EVIDENCE) not in [str(k) for k in after_gap["gap_kinds"]]
    assert str(EvidenceGapKind.MISSING_EXPERIMENT) in [str(k) for k in after_gap["gap_kinds"]]
    assert after_gap["coverage_score"] > before_gap["coverage_score"]

    before_coverage = sum(float(g["coverage_score"]) for g in before_blocking_gaps)
    after_blocking_gaps = [
        g for g in after_gaps if str(g["gap_class"]) == EvidenceGapClass.BLOCKING_GAP
    ]
    after_coverage_total = sum(float(g["coverage_score"]) for g in after_blocking_gaps)
    assert after_coverage_total > before_coverage, "closing evidence must raise coverage"

    # --- a new recommendation version and a decision delta --------------------------------------
    second = generate_recommendation(db, program)
    db.flush()
    assert second["version"] == first["version"] + 1
    assert second["recommendation_id"] != first["recommendation_id"]
    assert second["recommendation_checksum"] != first["recommendation_checksum"], (
        "a changed evidence base must change the recommendation checksum"
    )

    delta = db.get(DecisionDelta, second["decision_delta_id"])
    assert delta is not None
    assert delta.previous_recommendation_id == first["recommendation_id"]
    assert delta.explanation
    assert delta.reason_codes or delta.new_evidence, (
        "the delta must say what changed in evidence terms"
    )

    # The superseded recommendation is retained verbatim.
    from app.models.entities import ReplacementRecommendation

    previous = db.get(ReplacementRecommendation, first["recommendation_id"])
    assert previous is not None
    assert previous.superseded_by_id == second["recommendation_id"]
    assert previous.rationale == first["rationale"], (
        "a conclusion someone may have acted on is never rewritten"
    )

    # --- recomputation is deterministic and actions were refreshed -------------------------------
    snapshot_a = build_snapshot_payload(PortfolioContext(db, program))
    snapshot_b = build_snapshot_payload(PortfolioContext(db, program))
    assert snapshot_a["snapshot_checksum"] == snapshot_b["snapshot_checksum"]

    open_actions = (
        db.query(ScientificAction)
        .filter(ScientificAction.program_id == program.id,
                ScientificAction.candidate_id == gamma.candidate_id,
                ScientificAction.status.in_(["proposed", "ready", "blocked"]))
        .all()
    )
    resolved_signatures = {
        a.action_signature for a in open_actions
        if a.requirement_id and "breakdown" in (a.action_signature or "")
    }
    assert not resolved_signatures or all(
        a.status != "proposed" for a in open_actions if a.action_signature in resolved_signatures
    )

    db.rollback()
