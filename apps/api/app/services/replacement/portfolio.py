"""Phase 10 — Candidate portfolio and decision state.

The portfolio is the single persistent list of candidates for a replacement program. It does not
store a second copy of Phase-9.1 validation state: it *consumes* it. `candidate_decision_state`
below reads the canonical next-gate decision, the canonical requirement evaluation and the canonical
industrial assessment, then answers three questions the decision layer needs:

  1. Is this candidate **blocked** (a definitive hard failure), **unresolved** (missing evidence on
     something that gates), or **eligible** (nothing gating is outstanding)?
  2. Which of the policy's configured gates does it satisfy, and why not for the rest?
  3. What portfolio lifecycle state does that add up to?

The eligibility partition is the reason ranking is safe. Ranking only ever runs *inside* the
eligible group, so a candidate cannot score its way past a blocking failure.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import (
    CandidateEligibility,
    MatrixCellStatus,
    PortfolioCandidateState,
    RequirementCriticality,
    ValidationState,
)
from app.services.replacement.context import CandidateView, PortfolioContext
from app.services.replacement.coverage import coverage_for_candidate
from app.services.replacement.policy import CRITICALITY_ORDER

PORTFOLIO_METHODOLOGY = "candidate-portfolio-v1"

# Gate identifiers understood by this implementation. A policy may require any subset; a policy that
# names a gate this build does not implement is reported as UNIMPLEMENTED rather than silently
# treated as satisfied, because silently passing an unknown gate is how a tool becomes unsafe.
IMPLEMENTED_GATES: frozenset[str] = frozenset({
    "NO_DEFINITIVE_BLOCKING_FAILURE",
    "ALL_BLOCKING_REQUIREMENTS_RESOLVED",
    "CRITICAL_EVIDENCE_COVERAGE_MET",
    "NO_UNRESOLVED_CRITICAL_CONFLICT",
    "INDUSTRIAL_BLOCKERS_RESOLVED",
    "REQUIRED_EXPERIMENTS_COMPLETE",
})

# Phase-9.1 validation states mapped onto the portfolio vocabulary. This is a re-labelling for the
# portfolio board only; the authoritative validation state is never overwritten.
VALIDATION_TO_PORTFOLIO: dict[str, str] = {
    ValidationState.COMPUTATIONAL_ONLY: PortfolioCandidateState.COMPUTATION_SUPPORTED,
    ValidationState.SIMULATION_SUPPORTED: PortfolioCandidateState.COMPUTATION_SUPPORTED,
    ValidationState.EXPERIMENT_RECOMMENDED: PortfolioCandidateState.EXPERIMENT_RECOMMENDED,
    ValidationState.EXPERIMENT_PENDING: PortfolioCandidateState.EXPERIMENT_PENDING,
    ValidationState.EXPERIMENT_IN_PROGRESS: PortfolioCandidateState.EXPERIMENT_IN_PROGRESS,
    ValidationState.PARTIALLY_VALIDATED: PortfolioCandidateState.PARTIALLY_VALIDATED,
    ValidationState.EXPERIMENTALLY_SUPPORTED: PortfolioCandidateState.EXPERIMENTALLY_SUPPORTED,
    ValidationState.EXPERIMENTALLY_CONTRADICTED: PortfolioCandidateState.EXPERIMENTALLY_CONTRADICTED,
    ValidationState.CONTRADICTED: PortfolioCandidateState.EXPERIMENTALLY_CONTRADICTED,
    ValidationState.CONFLICTING_EXPERIMENTS: PortfolioCandidateState.INDUSTRIAL_REVIEW,
    ValidationState.INCONCLUSIVE: PortfolioCandidateState.SCREENING,
}


def _gate_result(gate: str, satisfied: bool, reason: str, evidence: Any = None) -> dict[str, Any]:
    return {"gate": gate, "satisfied": satisfied, "reason": reason, "evidence": evidence or []}


def candidate_decision_state(context: PortfolioContext, view: CandidateView) -> dict[str, Any]:
    """The full gate evaluation for one candidate. Memoized per request via the shared context."""
    cache_key = f"decision_state:{view.candidate_id}"
    cached = context.memo.get(cache_key)
    if cached is not None:
        return cached

    coverage_rows = coverage_for_candidate(context, view)
    decision = context.decision_for(view)
    industrial = context.industrial_for(view)
    requirements_by_id = context.requirements_by_id

    gating_rows = [row for row in coverage_rows if row["is_gating"]]
    blocking_rows = [
        row for row in gating_rows
        if str(row["criticality"]) == RequirementCriticality.BLOCKING
    ]

    # --- definitive failures -------------------------------------------------------------------
    # Only FAIL counts. UNKNOWN, INCONCLUSIVE, NOT_COMPARABLE and CONFLICTING are unresolved work,
    # not verdicts, and must never reject a candidate on their own.
    definitive_failures = [
        {
            "requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"],
            "display_name": row["display_name"], "property_key": row["property_key"],
            "criticality": row["criticality"], "status": row["governing_status"],
            "reason_code": "REQUIREMENT_DEFINITIVELY_FAILED",
        }
        for row in gating_rows if str(row["governing_status"]) == MatrixCellStatus.FAIL
    ]

    # Experimental contradiction is surfaced by Phase 9.1 with its own reason code. Under a policy
    # with auto-reject enabled it is a definitive blocker; otherwise it is recorded and left to a human.
    experimental_contradictions = [
        item for item in (decision.get("blocking_requirements") or [])
        if str(item.get("reason_code")) == "EXPERIMENT_CONTRADICTS_REQUIREMENT"
    ]
    if context.policy.auto_reject_on_experimental_contradiction:
        known = {str(f["requirement_id"]) for f in definitive_failures}
        for item in experimental_contradictions:
            requirement_id = str(item.get("requirement_id"))
            if requirement_id in known:
                continue
            requirement = requirements_by_id.get(requirement_id)
            definitive_failures.append({
                "requirement_id": requirement_id,
                "requirement_key": requirement.key if requirement else None,
                "display_name": requirement.display_name if requirement else None,
                "property_key": item.get("property_key"),
                "criticality": context.criticality_of(requirement_id),
                "status": MatrixCellStatus.FAIL,
                "reason_code": "EXPERIMENT_CONTRADICTS_REQUIREMENT",
            })

    unresolved_gating = [
        {
            "requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"],
            "display_name": row["display_name"], "property_key": row["property_key"],
            "criticality": row["criticality"], "status": row["governing_status"],
            "coverage_score": row["coverage_score"], "missing_evidence": row["missing_evidence"],
        }
        for row in gating_rows
        if str(row["governing_status"]) != MatrixCellStatus.PASS
        and str(row["governing_status"]) != MatrixCellStatus.FAIL
    ]
    conflicting_gating = [
        row for row in gating_rows
        if str(row["governing_status"]) == MatrixCellStatus.CONFLICTING
    ]

    # --- gates ---------------------------------------------------------------------------------
    industrial_gate = context.policy.industrial_gate_requirements or {}
    blocking_industrial_states = set(
        industrial_gate.get("blocking_overall_states") or ["fail", "conflicting_evidence"]
    )
    required_dimensions = list(industrial_gate.get("required_resolved_dimensions") or [])
    resolved_dimension_states = set(
        industrial_gate.get("resolved_dimension_states") or ["pass", "partial"]
    )
    industrial_state = str(industrial.get("overall_state") or "not_assessed")
    industrial_dimension_states = industrial.get("dimension_states") or {}
    unresolved_dimensions = [
        {"dimension": dimension, "state": str(industrial_dimension_states.get(dimension, "unknown"))}
        for dimension in required_dimensions
        if str(industrial_dimension_states.get(dimension, "unknown")) not in resolved_dimension_states
    ]
    industrial_assessment_missing = bool(
        industrial_gate.get("require_assessment", True) and industrial_state == "not_assessed"
    )

    minimum_evidence = context.policy.minimum_evidence_requirements or {}
    min_blocking_coverage = float(minimum_evidence.get("minimum_blocking_coverage", 1.0))
    min_critical_coverage = float(minimum_evidence.get("minimum_critical_coverage", 1.0))
    criticalities_requiring_experiment = set(
        (context.policy.required_experimental_validation or {}).get(
            "criticalities_requiring_experiment", []
        )
    )
    minimum_replicates = int(
        (context.policy.required_experimental_validation or {}).get("minimum_replicates", 2)
    )

    under_covered = [
        {"requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"],
         "coverage_score": row["coverage_score"], "missing_evidence": row["missing_evidence"]}
        for row in gating_rows
        if float(row["coverage_score"]) < (
            min_blocking_coverage if str(row["criticality"]) == RequirementCriticality.BLOCKING
            else min_critical_coverage
        )
    ]

    experimental_outcomes = {
        str(item.get("requirement_id")): item
        for item in (decision.get("scientific_requirements") or {}).get("requirement_outcomes", [])
    }
    missing_experiments = []
    for row in gating_rows:
        if str(row["criticality"]) not in criticalities_requiring_experiment:
            continue
        outcome = experimental_outcomes.get(str(row["requirement_id"])) or {}
        replicates = len(outcome.get("measurement_outcomes") or [])
        if replicates < minimum_replicates:
            missing_experiments.append({
                "requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"],
                "admissible_replicates": replicates, "required_replicates": minimum_replicates,
            })

    all_gate_results: dict[str, dict[str, Any]] = {
        "NO_DEFINITIVE_BLOCKING_FAILURE": _gate_result(
            "NO_DEFINITIVE_BLOCKING_FAILURE", not definitive_failures,
            "No gating requirement has definitively failed."
            if not definitive_failures
            else f"{len(definitive_failures)} gating requirement(s) definitively failed.",
            definitive_failures,
        ),
        "ALL_BLOCKING_REQUIREMENTS_RESOLVED": _gate_result(
            "ALL_BLOCKING_REQUIREMENTS_RESOLVED",
            all(str(row["governing_status"]) == MatrixCellStatus.PASS for row in blocking_rows),
            "Every BLOCKING requirement is resolved with a PASS."
            if all(str(row["governing_status"]) == MatrixCellStatus.PASS for row in blocking_rows)
            else "At least one BLOCKING requirement is not yet resolved to PASS.",
            [{"requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"],
              "status": row["governing_status"]}
             for row in blocking_rows if str(row["governing_status"]) != MatrixCellStatus.PASS],
        ),
        "CRITICAL_EVIDENCE_COVERAGE_MET": _gate_result(
            "CRITICAL_EVIDENCE_COVERAGE_MET", not under_covered,
            "Every gating requirement meets the policy's minimum evidence coverage."
            if not under_covered
            else f"{len(under_covered)} gating requirement(s) are below the policy coverage minimum.",
            under_covered,
        ),
        "NO_UNRESOLVED_CRITICAL_CONFLICT": _gate_result(
            "NO_UNRESOLVED_CRITICAL_CONFLICT", not conflicting_gating,
            "No gating requirement has origins that disagree."
            if not conflicting_gating
            else f"{len(conflicting_gating)} gating requirement(s) have conflicting evidence.",
            [{"requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"]}
             for row in conflicting_gating],
        ),
        "INDUSTRIAL_BLOCKERS_RESOLVED": _gate_result(
            "INDUSTRIAL_BLOCKERS_RESOLVED",
            industrial_state not in blocking_industrial_states
            and not industrial_assessment_missing
            and not unresolved_dimensions,
            f"Industrial viability is '{industrial_state}'."
            + (" No industrial assessment exists." if industrial_assessment_missing else "")
            + (
                " Unresolved required dimension(s): "
                + ", ".join(f"{d['dimension']}={d['state']}" for d in unresolved_dimensions) + "."
                if unresolved_dimensions else ""
            ),
            {"overall_state": industrial_state,
             "hard_constraint_failures": industrial.get("hard_constraint_failures") or [],
             "unresolved_required_dimensions": unresolved_dimensions,
             "excluded_dimensions": list(industrial_gate.get("excluded_dimensions") or []),
             "unknown_dimensions": industrial.get("unknown_dimensions") or []},
        ),
        "REQUIRED_EXPERIMENTS_COMPLETE": _gate_result(
            "REQUIRED_EXPERIMENTS_COMPLETE", not missing_experiments,
            "Every requirement that the policy says needs physical measurement has enough "
            "admissible replicates."
            if not missing_experiments
            else f"{len(missing_experiments)} requirement(s) lack the required admissible replicates.",
            missing_experiments,
        ),
    }

    required_gates = list(context.policy.required_gates or [])
    gate_results: list[dict[str, Any]] = []
    for gate in required_gates:
        if gate in all_gate_results:
            gate_results.append(all_gate_results[gate])
        else:
            gate_results.append(_gate_result(
                gate, False,
                "This decision policy requires a gate that this build does not implement. It is "
                "reported as unsatisfied rather than assumed to pass.",
                {"reason_code": "GATE_NOT_IMPLEMENTED"},
            ))
    gates_satisfied = all(g["satisfied"] for g in gate_results)

    # --- eligibility ---------------------------------------------------------------------------
    industrial_hard_fail = industrial_state in blocking_industrial_states
    if definitive_failures or industrial_hard_fail:
        eligibility = CandidateEligibility.BLOCKED
    elif unresolved_gating:
        eligibility = CandidateEligibility.UNRESOLVED
    else:
        eligibility = CandidateEligibility.ELIGIBLE

    # --- portfolio lifecycle state ---------------------------------------------------------------
    validation_state = str(decision.get("experimental_status") or ValidationState.INCONCLUSIVE)
    if eligibility == CandidateEligibility.BLOCKED:
        portfolio_state = (
            PortfolioCandidateState.EXPERIMENTALLY_CONTRADICTED
            if experimental_contradictions else PortfolioCandidateState.REJECT
        )
    elif gates_satisfied:
        portfolio_state = PortfolioCandidateState.DECISION_READY
    elif eligibility == CandidateEligibility.UNRESOLVED:
        portfolio_state = VALIDATION_TO_PORTFOLIO.get(
            validation_state, PortfolioCandidateState.SCREENING
        )
    else:
        portfolio_state = PortfolioCandidateState.INDUSTRIAL_REVIEW

    reason_codes = sorted(set(
        [str(code) for code in (decision.get("reason_codes") or [])]
        + (["DEFINITIVE_BLOCKING_FAILURE"] if definitive_failures else [])
        + (["INDUSTRIAL_HARD_FAILURE"] if industrial_hard_fail else [])
        + (["UNRESOLVED_GATING_REQUIREMENTS"] if unresolved_gating else [])
        + (["ALL_GATES_SATISFIED"] if gates_satisfied else [])
    ))

    state = {
        "candidate_id": view.candidate_id,
        "display_name": view.display_name,
        "candidate_kind": view.candidate_kind,
        "candidate_source": view.candidate_source,
        "state_id": view.state_id,
        "eligibility": str(eligibility),
        "portfolio_state": str(portfolio_state),
        "gates_satisfied": gates_satisfied,
        "gate_results": gate_results,
        "definitive_blocking_failures": definitive_failures,
        "unresolved_gating_requirements": unresolved_gating,
        "conflicting_gating_requirements": [
            {"requirement_id": row["requirement_id"], "requirement_key": row["requirement_key"]}
            for row in conflicting_gating
        ],
        "next_gate_decision": decision.get("decision"),
        "validation_state": validation_state,
        "industrial_state": industrial_state,
        "industrial_assessment_id": decision.get("industrial_assessment_id"),
        "maturity_stage": industrial.get("maturity_stage"),
        "reason_codes": reason_codes,
        "decision_policy_version": context.policy.version,
        "methodology_version": PORTFOLIO_METHODOLOGY,
        "qualification_note": decision.get("qualification_note"),
    }
    context.memo[cache_key] = state
    return state


def portfolio_board(context: PortfolioContext) -> dict[str, Any]:
    """The candidate portfolio board: one row per candidate, with everything a reviewer filters on."""
    from app.services.replacement.actions import next_actions_for_candidate
    from app.services.replacement.gaps import gaps_for_candidate
    from app.services.replacement.ranking import rank_candidates

    ranking = rank_candidates(context)
    rank_by_candidate = {
        str(row["candidate_id"]): row for row in ranking["ranked"]
    }
    pareto_ids = set(ranking["pareto"]["front_candidate_ids"])

    rows: list[dict[str, Any]] = []
    for view in context.candidates:
        state = candidate_decision_state(context, view)
        gaps = gaps_for_candidate(context, view)
        coverage = coverage_for_candidate(context, view)
        actions = next_actions_for_candidate(context, view, eligibility=state["eligibility"])
        gating = [row for row in coverage if row["is_gating"]]
        scored = [float(row["coverage_score"]) for row in coverage] or [0.0]
        rank_row = rank_by_candidate.get(view.candidate_id)
        rows.append({
            **state,
            "blocking_failure_count": len(state["definitive_blocking_failures"]),
            "unknown_count": sum(
                1 for row in coverage
                if str(row["governing_status"]) == MatrixCellStatus.UNKNOWN
            ),
            "conflict_count": sum(
                1 for row in coverage
                if str(row["governing_status"]) == MatrixCellStatus.CONFLICTING
            ),
            "gating_requirement_count": len(gating),
            "evidence_coverage": round(sum(scored) / len(scored), 6),
            "blocking_gap_count": sum(1 for gap in gaps if str(gap["gap_class"]) == "blocking_gap"),
            "gap_count": len(gaps),
            "next_action": actions[0] if actions else None,
            "rank": rank_row["rank"] if rank_row else None,
            "rank_excluded_reason": (
                None if rank_row else "Not ranked: the candidate is not eligible."
            ),
            "pareto_front": view.candidate_id in pareto_ids,
            "dominated_by": (
                ranking["pareto"]["dominated_by"].get(view.candidate_id, []) if view.candidate_id not in pareto_ids else []
            ),
        })

    rows.sort(key=lambda r: (
        {"eligible": 0, "unresolved": 1, "blocked": 2}.get(str(r["eligibility"]), 3),
        r["rank"] if r["rank"] is not None else 10**6,
        str(r["display_name"]),
    ))

    return {
        "program_id": context.program.id,
        "candidates": rows,
        "counts": {
            "total": len(rows),
            "eligible": sum(1 for r in rows if r["eligibility"] == CandidateEligibility.ELIGIBLE),
            "unresolved": sum(1 for r in rows if r["eligibility"] == CandidateEligibility.UNRESOLVED),
            "blocked": sum(1 for r in rows if r["eligibility"] == CandidateEligibility.BLOCKED),
            "decision_ready": sum(1 for r in rows if r["gates_satisfied"]),
            "pareto_front": sum(1 for r in rows if r["pareto_front"]),
        },
        "methodology_version": PORTFOLIO_METHODOLOGY,
        "note": (
            "Portfolio state consumes the canonical Phase-8/9.1 validation and industrial "
            "assessments; it is not a second, independently maintained scientific state."
        ),
    }


CRITICALITY_SORT_ORDER = CRITICALITY_ORDER
