"""Phase 10 — Replacement recommendation, decision delta and explainability.

The recommendation is the product's answer, and the single most important property it has is that it
is allowed to be **NO_SUITABLE_CANDIDATE**. A tool that always produces a winner is a tool that will
eventually recommend something unsafe, because the pressure to produce an answer never lets up while
the evidence sometimes does.

Recommendations are immutable and versioned. New evidence produces version N+1 together with a
`DecisionDelta` explaining, in terms of evidence rather than score movement, what changed and why.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    CandidateEligibility,
    ConvergenceState,
    MatrixCellStatus,
    ProgramEventKind,
    ReplacementRecommendationStatus,
)
from app.models.entities import DecisionDelta, ReplacementProgram, ReplacementRecommendation
from app.services.replacement.actions import (
    NEXT_ACTION_METHODOLOGY,
    PRIORITY_METHODOLOGY,
    compute_actions,
)
from app.services.replacement.context import PortfolioContext
from app.services.replacement.convergence import (
    CONVERGENCE_METHODOLOGY,
    assess_convergence,
    persist_convergence,
)
from app.services.replacement.coverage import COVERAGE_METHODOLOGY, MATRIX_METHODOLOGY
from app.services.replacement.gaps import EVIDENCE_GAP_METHODOLOGY, program_gaps
from app.services.replacement.policy import checksum
from app.services.replacement.portfolio import PORTFOLIO_METHODOLOGY, candidate_decision_state
from app.services.replacement.ranking import (
    PARETO_METHODOLOGY,
    RANKING_METHODOLOGY,
    SENSITIVITY_METHODOLOGY,
    rank_candidates,
    sensitivity_analysis,
)

RECOMMENDATION_METHODOLOGY = "replacement-recommendation-v1"
DECISION_DELTA_METHODOLOGY = "decision-delta-v1"
EXPLANATION_METHODOLOGY = "explainability-v1"

QUALIFICATION_NOTE = (
    "TinkerLab recommendations summarize available scientific, industrial and experimental "
    "evidence. They do not replace required regulatory, qualification, safety or customer approval "
    "processes, and they are not authorization to replace the incumbent material in production."
)

METHODOLOGY_VERSIONS = {
    "recommendation": RECOMMENDATION_METHODOLOGY,
    "portfolio": PORTFOLIO_METHODOLOGY,
    "decision_matrix": MATRIX_METHODOLOGY,
    "evidence_coverage": COVERAGE_METHODOLOGY,
    "evidence_gap": EVIDENCE_GAP_METHODOLOGY,
    "next_action": NEXT_ACTION_METHODOLOGY,
    "next_action_priority": PRIORITY_METHODOLOGY,
    "convergence": CONVERGENCE_METHODOLOGY,
    "ranking": RANKING_METHODOLOGY,
    "pareto": PARETO_METHODOLOGY,
    "sensitivity": SENSITIVITY_METHODOLOGY,
    "explainability": EXPLANATION_METHODOLOGY,
}

# What a program can do when nothing is viable. These are suggestions for a human, and none of them
# is ever executed automatically — in particular, a requirement is never relaxed by the system.
NO_CANDIDATE_NEXT_STEPS = [
    "Review whether a blocking requirement threshold reflects a genuine application need.",
    "Generate additional candidates from a wider search space.",
    "Consider an alternative manufacturing route that changes the industrial constraints.",
    "Collect further evidence where a rejection rests on a single origin.",
    "Re-examine the application constraints with the requirement owner.",
]


def build_recommendation(context: PortfolioContext) -> dict[str, Any]:
    """Compute the recommendation payload for a program. Persists nothing."""
    ranking = rank_candidates(context)
    sensitivity = sensitivity_analysis(context)
    gaps = program_gaps(context)
    actions = compute_actions(context)
    convergence = assess_convergence(context)

    per_candidate: list[dict[str, Any]] = []
    blocking_requirements: list[dict[str, Any]] = []
    unresolved_requirements: list[dict[str, Any]] = []
    conflicting_evidence: list[dict[str, Any]] = []

    advance_ids: list[str] = []
    reject_ids: list[str] = []
    hold_ids: list[str] = []

    pareto_ids = set(ranking["pareto"]["front_candidate_ids"])
    rank_by_candidate = {str(row["candidate_id"]): row for row in ranking["ranked"]}

    for view in context.candidates:
        state = candidate_decision_state(context, view)
        decision = context.decision_for(view)
        rank_row = rank_by_candidate.get(view.candidate_id)

        for item in state["definitive_blocking_failures"]:
            blocking_requirements.append({**item, "candidate_id": view.candidate_id})
        for item in state["unresolved_gating_requirements"]:
            unresolved_requirements.append({**item, "candidate_id": view.candidate_id})
        for item in (decision.get("conflicting_evidence") or []):
            conflicting_evidence.append({**item, "candidate_id": view.candidate_id})

        if state["eligibility"] == CandidateEligibility.BLOCKED:
            reject_ids.append(view.candidate_id)
        elif state["gates_satisfied"]:
            advance_ids.append(view.candidate_id)
        else:
            hold_ids.append(view.candidate_id)

        per_candidate.append({
            "candidate_id": view.candidate_id,
            "display_name": view.display_name,
            "candidate_kind": view.candidate_kind,
            "eligibility": state["eligibility"],
            "portfolio_state": state["portfolio_state"],
            "gates_satisfied": state["gates_satisfied"],
            "gate_results": state["gate_results"],
            "scientific_status": decision.get("scientific_requirements", {}).get("validation_state"),
            "simulation_status": decision.get("simulation_status"),
            "industrial_status": state["industrial_state"],
            "experimental_status": state["validation_state"],
            "next_gate_decision": state["next_gate_decision"],
            "blocking_requirements": state["definitive_blocking_failures"],
            "unresolved_requirements": state["unresolved_gating_requirements"],
            "rank": rank_row["rank"] if rank_row else None,
            "score": rank_row["score"] if rank_row else None,
            "pareto_front": view.candidate_id in pareto_ids,
            "reason_codes": state["reason_codes"],
        })

    reason_codes: list[str] = []
    if advance_ids and len(advance_ids) > 1:
        status = ReplacementRecommendationStatus.ADVANCE_MULTIPLE_CANDIDATES
        reason_codes.append("MULTIPLE_CANDIDATES_SATISFY_ALL_GATES")
    elif advance_ids:
        status = ReplacementRecommendationStatus.ADVANCE_CANDIDATE
        reason_codes.append("CANDIDATE_SATISFIES_ALL_GATES")
    elif context.candidates and not hold_ids and reject_ids:
        # Every candidate is definitively blocked. This is a legitimate, useful answer.
        status = ReplacementRecommendationStatus.NO_SUITABLE_CANDIDATE
        reason_codes.append("ALL_CANDIDATES_BLOCKED")
    elif conflicting_evidence and not hold_ids:
        status = ReplacementRecommendationStatus.INCONCLUSIVE
        reason_codes.append("UNRESOLVED_EVIDENCE_CONFLICTS")
    elif hold_ids:
        status = ReplacementRecommendationStatus.HOLD_FOR_EVIDENCE
        reason_codes.append("GATING_REQUIREMENTS_UNRESOLVED")
    else:
        status = ReplacementRecommendationStatus.INCONCLUSIVE
        reason_codes.append("NO_CANDIDATES_TO_ASSESS")

    if reject_ids:
        reason_codes.append("CANDIDATES_REJECTED_ON_DEFINITIVE_FAILURE")
    if str(sensitivity.get("stability")) == "weight_sensitive":
        reason_codes.append("RANKING_IS_WEIGHT_SENSITIVE")
    if gaps["blocking_gap_count"]:
        reason_codes.append("BLOCKING_EVIDENCE_GAPS_OPEN")

    rationale = _rationale(
        status=status, per_candidate=per_candidate, advance_ids=advance_ids,
        reject_ids=reject_ids, hold_ids=hold_ids, actions=actions["actions"],
        convergence=convergence, policy_version=context.policy.version,
    )

    requirement_summary = {
        "requirement_count": len(context.requirements),
        "gating_requirement_count": sum(
            1 for requirement in context.requirements
            if context.criticality_of(requirement.id) in {"blocking", "critical"}
        ),
        "by_criticality": _count_by(
            [context.criticality_of(r.id) for r in context.requirements]
        ),
        "proposed_requirement_count": sum(
            1 for requirement in context.requirements
            if str(getattr(requirement, "approval_status", "accepted")) == "proposed"
        ),
    }

    payload = {
        "program_id": context.program.id,
        "status": str(status),
        "recommended_candidate_ids": sorted(advance_ids),
        "rejected_candidate_ids": sorted(reject_ids),
        "held_candidate_ids": sorted(hold_ids),
        "incumbent_reference": {
            "material_id": context.incumbent_material().id if context.incumbent_material() else None,
            "display_name": (
                context.incumbent_material().display_name if context.incumbent_material() else None
            ),
            "state_id": context.incumbent_state().id if context.incumbent_state() else None,
        },
        "requirement_summary": requirement_summary,
        "per_candidate": per_candidate,
        "blocking_requirements": blocking_requirements,
        "unresolved_requirements": unresolved_requirements,
        "conflicting_evidence": conflicting_evidence,
        "evidence_gaps": gaps["gaps"],
        "next_actions": actions["actions"][:25],
        "ranking": {"ranked": ranking["ranked"], "excluded": ranking["excluded"],
                    "weights": ranking["weights"], "note": ranking["note"]},
        "pareto": ranking["pareto"],
        "sensitivity": sensitivity,
        "convergence_state": convergence["convergence_state"],
        "convergence": convergence,
        "reason_codes": sorted(set(reason_codes)),
        "rationale": rationale,
        "decision_policy_id": context.policy.id,
        "decision_policy_version": context.policy.version,
        "methodology_versions": dict(METHODOLOGY_VERSIONS),
        "qualification_note": QUALIFICATION_NOTE,
        "possible_program_actions": (
            list(NO_CANDIDATE_NEXT_STEPS)
            if status == ReplacementRecommendationStatus.NO_SUITABLE_CANDIDATE else []
        ),
        "requirement_relaxation_note": (
            "TinkerLab never relaxes a requirement automatically. Changing a threshold is a human "
            "decision that creates a new requirement version and a new assessment."
        ),
    }
    payload["recommendation_checksum"] = checksum({
        "methodology": RECOMMENDATION_METHODOLOGY,
        "policy": context.policy.version,
        "policy_checksum": context.policy.policy_checksum,
        "status": str(status),
        "advance": sorted(advance_ids), "reject": sorted(reject_ids), "hold": sorted(hold_ids),
        "per_candidate": sorted(
            [{"candidate_id": row["candidate_id"], "eligibility": row["eligibility"],
              "gates_satisfied": row["gates_satisfied"], "rank": row["rank"]}
             for row in per_candidate],
            key=lambda r: str(r["candidate_id"]),
        ),
        "convergence": convergence["assessment_checksum"],
    })
    return payload


def _count_by(values: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def _rationale(
    *, status: Any, per_candidate: list[dict[str, Any]], advance_ids: list[str],
    reject_ids: list[str], hold_ids: list[str], actions: list[dict[str, Any]],
    convergence: dict[str, Any], policy_version: str,
) -> str:
    """Deterministic prose assembled from reason codes. No language model is involved."""
    by_id = {row["candidate_id"]: row for row in per_candidate}
    sentences: list[str] = []

    for candidate_id in sorted(advance_ids):
        row = by_id[candidate_id]
        sentences.append(
            f"{row['display_name']} is recommended to advance because every configured gate is "
            f"satisfied under the available admissible evidence."
        )
    for candidate_id in sorted(reject_ids):
        row = by_id[candidate_id]
        blockers = ", ".join(
            str(b.get("requirement_key") or b.get("requirement_id"))
            for b in row["blocking_requirements"]
        ) or "an industrial hard constraint"
        sentences.append(
            f"{row['display_name']} is rejected because {blockers} definitively failed."
        )
    for candidate_id in sorted(hold_ids):
        row = by_id[candidate_id]
        unresolved = ", ".join(
            str(u.get("requirement_key") or u.get("requirement_id"))
            for u in row["unresolved_requirements"][:3]
        )
        candidate_action = next(
            (a for a in actions if a["candidate_id"] == candidate_id
             and a["action_type"] not in {"no_action_required"}),
            None,
        )
        tail = (
            f" The highest-value next action is {candidate_action['action_type']}."
            if candidate_action else ""
        )
        sentences.append(
            f"{row['display_name']} remains unresolved because {unresolved or 'gating evidence'} "
            f"is outstanding.{tail}"
        )

    if status == ReplacementRecommendationStatus.NO_SUITABLE_CANDIDATE:
        sentences.append(
            "No candidate in the portfolio is suitable on the current evidence. This is a "
            "conclusion, not a failure to compute one."
        )
    if not sentences:
        sentences.append("No candidate could be assessed against the current requirement set.")

    sentences.append(
        f"This conclusion was generated under decision policy version {policy_version} with the "
        f"program in convergence state {convergence['convergence_state']}."
    )
    return " ".join(sentences)


def persist_recommendation(
    db: Session, context: PortfolioContext, payload: dict[str, Any], *,
    created_by: str | None = None, convergence_assessment_id: str | None = None,
) -> tuple[ReplacementRecommendation, DecisionDelta | None]:
    """Store recommendation version N+1 and, when a previous version exists, its DecisionDelta."""
    previous = (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == context.program.id,
                ReplacementRecommendation.organisation_id == context.organisation_id)
        .order_by(ReplacementRecommendation.version.desc())
        .first()
    )
    version = (previous.version + 1) if previous else 1

    row = ReplacementRecommendation(
        organisation_id=context.organisation_id, program_id=context.program.id, version=version,
        status=str(payload["status"]),
        recommended_candidate_ids=list(payload["recommended_candidate_ids"]),
        rejected_candidate_ids=list(payload["rejected_candidate_ids"]),
        held_candidate_ids=list(payload["held_candidate_ids"]),
        incumbent_reference=payload["incumbent_reference"],
        requirement_summary=payload["requirement_summary"],
        per_candidate=payload["per_candidate"],
        blocking_requirements=payload["blocking_requirements"],
        unresolved_requirements=payload["unresolved_requirements"],
        conflicting_evidence=payload["conflicting_evidence"],
        evidence_gaps=payload["evidence_gaps"],
        next_actions=payload["next_actions"],
        ranking=payload["ranking"], pareto=payload["pareto"], sensitivity=payload["sensitivity"],
        convergence_state=str(payload["convergence_state"]),
        convergence_assessment_id=convergence_assessment_id,
        reason_codes=list(payload["reason_codes"]), rationale=str(payload["rationale"]),
        decision_policy_id=payload["decision_policy_id"],
        decision_policy_version=str(payload["decision_policy_version"]),
        methodology_versions=payload["methodology_versions"],
        assessment_refs={
            "convergence_assessment_id": convergence_assessment_id,
            "policy_checksum": context.policy.policy_checksum,
        },
        qualification_note=QUALIFICATION_NOTE,
        recommendation_checksum=str(payload["recommendation_checksum"]),
        created_by=created_by,
    )
    db.add(row)
    db.flush()

    # The previous recommendation is superseded, never edited. Its rationale must remain readable
    # exactly as it was when someone acted on it.
    if previous is not None:
        previous.superseded_by_id = row.id
        db.flush()

    delta = _build_delta(db, context, previous=previous, new=row) if previous is not None else None
    return row, delta


def _build_delta(
    db: Session, context: PortfolioContext, *, previous: ReplacementRecommendation,
    new: ReplacementRecommendation,
) -> DecisionDelta:
    """Explain the change in terms of requirements, evidence and blockers."""
    previous_by_candidate = {
        str(row["candidate_id"]): row for row in (previous.per_candidate or [])
    }
    new_by_candidate = {str(row["candidate_id"]): row for row in (new.per_candidate or [])}

    changed_requirements: list[dict[str, Any]] = []
    changed_blockers: list[dict[str, Any]] = []
    changed_ranking: list[dict[str, Any]] = []

    for candidate_id, new_row in sorted(new_by_candidate.items()):
        old_row = previous_by_candidate.get(candidate_id)
        if old_row is None:
            changed_requirements.append({
                "candidate_id": candidate_id, "change": "CANDIDATE_ADDED",
                "display_name": new_row.get("display_name"),
            })
            continue
        if old_row.get("eligibility") != new_row.get("eligibility"):
            changed_requirements.append({
                "candidate_id": candidate_id, "change": "ELIGIBILITY_CHANGED",
                "from": old_row.get("eligibility"), "to": new_row.get("eligibility"),
            })
        if old_row.get("experimental_status") != new_row.get("experimental_status"):
            changed_requirements.append({
                "candidate_id": candidate_id, "change": "VALIDATION_STATE_CHANGED",
                "from": old_row.get("experimental_status"), "to": new_row.get("experimental_status"),
            })
        if old_row.get("industrial_status") != new_row.get("industrial_status"):
            changed_requirements.append({
                "candidate_id": candidate_id, "change": "INDUSTRIAL_STATE_CHANGED",
                "from": old_row.get("industrial_status"), "to": new_row.get("industrial_status"),
            })
        old_blockers = {str(b.get("requirement_id")) for b in (old_row.get("blocking_requirements") or [])}
        new_blockers = {str(b.get("requirement_id")) for b in (new_row.get("blocking_requirements") or [])}
        for requirement_id in sorted(new_blockers - old_blockers):
            changed_blockers.append({"candidate_id": candidate_id, "requirement_id": requirement_id,
                                     "change": "BLOCKER_ADDED"})
        for requirement_id in sorted(old_blockers - new_blockers):
            changed_blockers.append({"candidate_id": candidate_id, "requirement_id": requirement_id,
                                     "change": "BLOCKER_CLEARED"})
        if old_row.get("rank") != new_row.get("rank"):
            changed_ranking.append({
                "candidate_id": candidate_id, "from_rank": old_row.get("rank"),
                "to_rank": new_row.get("rank"),
            })

    for candidate_id in sorted(set(previous_by_candidate) - set(new_by_candidate)):
        changed_requirements.append({
            "candidate_id": candidate_id, "change": "CANDIDATE_REMOVED",
            "display_name": previous_by_candidate[candidate_id].get("display_name"),
        })

    # New and invalidated evidence, derived from the measurement identifiers each recommendation saw.
    def measurement_ids(recommendation: ReplacementRecommendation) -> set[str]:
        found: set[str] = set()
        for row in (recommendation.per_candidate or []):
            for item in (row.get("blocking_requirements") or []):
                if item.get("measurement_id"):
                    found.add(str(item["measurement_id"]))
        return found

    old_gap_ids = {str(g.get("gap_id")) for g in (previous.evidence_gaps or [])}
    new_gap_ids = {str(g.get("gap_id")) for g in (new.evidence_gaps or [])}
    new_evidence = [
        {"kind": "gap_closed", "gap_id": gap_id} for gap_id in sorted(old_gap_ids - new_gap_ids)
    ]
    invalidated_evidence = [
        {"kind": "gap_reopened", "gap_id": gap_id} for gap_id in sorted(new_gap_ids - old_gap_ids)
    ]

    reason_codes = sorted(set(
        [item["change"] for item in changed_requirements]
        + [item["change"] for item in changed_blockers]
        + (["RANK_ORDER_CHANGED"] if changed_ranking else [])
        + (["RECOMMENDATION_STATUS_CHANGED"] if previous.status != new.status else [])
    ))

    explanation_parts = [
        f"The recommendation moved from {previous.status} to {new.status}."
        if previous.status != new.status
        else f"The recommendation remains {new.status}."
    ]
    if new_evidence:
        explanation_parts.append(f"{len(new_evidence)} evidence gap(s) closed.")
    if invalidated_evidence:
        explanation_parts.append(
            f"{len(invalidated_evidence)} evidence gap(s) opened or reopened, which usually means "
            "evidence was invalidated or a requirement changed."
        )
    for item in changed_blockers:
        explanation_parts.append(
            f"Blocker {item['requirement_id']} was "
            f"{'added for' if item['change'] == 'BLOCKER_ADDED' else 'cleared for'} "
            f"candidate {item['candidate_id']}."
        )
    if not changed_requirements and not changed_blockers and not changed_ranking:
        explanation_parts.append("No candidate-level conclusion changed between these versions.")

    delta = DecisionDelta(
        organisation_id=context.organisation_id, program_id=context.program.id,
        previous_recommendation_id=previous.id, new_recommendation_id=new.id,
        previous_status=previous.status, new_status=new.status,
        changed_requirements=changed_requirements, new_evidence=new_evidence,
        invalidated_evidence=invalidated_evidence, changed_ranking=changed_ranking,
        changed_blockers=changed_blockers, reason_codes=reason_codes,
        explanation=" ".join(explanation_parts),
        methodology_version=DECISION_DELTA_METHODOLOGY,
    )
    db.add(delta)
    db.flush()
    return delta


def generate_recommendation(
    db: Session, program: ReplacementProgram, *, created_by: str | None = None,
) -> dict[str, Any]:
    """Compute, persist and record a recommendation together with its convergence assessment."""
    from app.services.replacement.actions import compute_actions as _compute
    from app.services.replacement.actions import persist_actions
    from app.services.replacement.programs import record_event, refresh_program_state

    context = PortfolioContext(db, program)
    convergence_payload = assess_convergence(context)
    convergence_row = persist_convergence(db, context, convergence_payload)

    payload = build_recommendation(context)
    row, delta = persist_recommendation(
        db, context, payload, created_by=created_by, convergence_assessment_id=convergence_row.id
    )
    persist_actions(db, context, _compute(context))

    record_event(
        db, program=program, kind=ProgramEventKind.RECOMMENDATION_GENERATED,
        summary=f"Recommendation v{row.version}: {row.status}.",
        payload={"status": row.status, "version": row.version,
                 "reason_codes": list(row.reason_codes or [])},
        reference_kind="replacement_recommendation", reference_id=row.id,
        actor_user_id=created_by,
    )
    refresh_program_state(db, program)

    return {
        **payload,
        "recommendation_id": row.id,
        "version": row.version,
        "convergence_assessment_id": convergence_row.id,
        "decision_delta_id": delta.id if delta else None,
        "created_at": row.created_at,
    }


# ---------------------------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------------------------
def explain_candidate(context: PortfolioContext, candidate_id: str) -> dict[str, Any]:
    """Answer the seven explainability questions from reason codes and provenance.

    Every answer below is assembled from structured data that the deterministic engines already
    produced. An LLM may be layered on top later to reword these strings; it cannot originate them.
    """
    view = context.candidate(candidate_id)
    if view is None:
        raise LookupError("Candidate not found in this program's portfolio")

    from app.services.replacement.actions import next_actions_for_candidate
    from app.services.replacement.coverage import coverage_for_candidate

    state = candidate_decision_state(context, view)
    coverage = coverage_for_candidate(context, view)
    ranking = rank_candidates(context)
    actions = next_actions_for_candidate(context, view, eligibility=state["eligibility"])
    rank_row = next(
        (row for row in ranking["ranked"] if str(row["candidate_id"]) == candidate_id), None
    )

    passed = [
        {"requirement_key": row["requirement_key"], "why": row["governing_origin"],
         "governing_status": row["governing_status"]}
        for row in coverage if str(row["governing_status"]) == MatrixCellStatus.PASS
    ]
    failed = [
        {"requirement_key": row["requirement_key"], "why": row["governing_origin"],
         "governing_status": row["governing_status"]}
        for row in coverage if str(row["governing_status"]) == MatrixCellStatus.FAIL
    ]

    why_proposed = (
        f"Proposed as a {view.candidate_kind.replace('_', ' ')} candidate via "
        f"'{view.candidate_source}'."
    )
    if view.hypothesis_lineage:
        lineage = view.hypothesis_lineage[0]
        why_proposed += (
            f" Generated by strategy {lineage.get('generator_strategy_key')} "
            f"v{lineage.get('generator_strategy_version')} with fingerprint "
            f"{lineage.get('deterministic_fingerprint')}."
        )

    why_blocked = (
        "Not blocked." if state["eligibility"] != CandidateEligibility.BLOCKED
        else "Blocked because: " + "; ".join(
            f"{b.get('requirement_key') or b.get('requirement_id')} ({b.get('reason_code')})"
            for b in state["definitive_blocking_failures"]
        ) or "an industrial hard constraint failed."
    )

    experiment_actions = [
        a for a in actions
        if str(a["action_type"]) in {"create_experiment_plan", "run_experiment",
                                     "run_additional_replicate", "run_control"}
    ]
    why_experiment = (
        "No experiment is currently recommended for this candidate."
        if not experiment_actions
        else "; ".join(f"{a['reason_code']}: {a['reason']}" for a in experiment_actions[:3])
    )

    why_ranked = "Not ranked: the candidate is not eligible."
    if rank_row:
        contributions = sorted(
            (
                (objective, value, float(rank_row["weights"].get(objective, 0.0)))
                for objective, value in rank_row["normalized_factors"].items()
                if value is not None
            ),
            key=lambda item: -(item[1] * item[2]),
        )
        top = ", ".join(
            f"{objective}={value} (weight {weight})" for objective, value, weight in contributions[:3]
        )
        why_ranked = (
            f"Rank {rank_row['rank']} with score {rank_row['score']}. Largest contributions: {top}. "
            f"Dimensions excluded for lack of evidence: "
            f"{', '.join(rank_row['excluded_dimensions']) or 'none'}."
        )

    return {
        "candidate_id": candidate_id,
        "display_name": view.display_name,
        "why_proposed": why_proposed,
        "why_requirements_passed": passed,
        "why_requirements_failed": failed,
        "why_blocked": why_blocked,
        "why_experiment_recommended": why_experiment,
        "why_ranked": why_ranked,
        "gate_results": state["gate_results"],
        "reason_codes": state["reason_codes"],
        "methodology_version": EXPLANATION_METHODOLOGY,
        "llm_boundary_note": (
            "This explanation is generated deterministically from stored reason codes and "
            "provenance. No language model produced or altered any status, rank or action here."
        ),
    }


def explain_recommendation_change(
    db: Session, *, organisation_id: str, program_id: str
) -> dict[str, Any]:
    """Why the recommendation changed, from the persisted DecisionDelta chain."""
    deltas = (
        db.query(DecisionDelta)
        .filter(DecisionDelta.organisation_id == organisation_id,
                DecisionDelta.program_id == program_id)
        .order_by(DecisionDelta.created_at.desc(), DecisionDelta.id)
        .limit(20)
        .all()
    )
    return {
        "program_id": program_id,
        "deltas": [
            {
                "id": delta.id,
                "previous_recommendation_id": delta.previous_recommendation_id,
                "new_recommendation_id": delta.new_recommendation_id,
                "previous_status": delta.previous_status, "new_status": delta.new_status,
                "changed_requirements": delta.changed_requirements or [],
                "new_evidence": delta.new_evidence or [],
                "invalidated_evidence": delta.invalidated_evidence or [],
                "changed_ranking": delta.changed_ranking or [],
                "changed_blockers": delta.changed_blockers or [],
                "reason_codes": delta.reason_codes or [],
                "explanation": delta.explanation,
                "created_at": delta.created_at,
            }
            for delta in deltas
        ],
        "methodology_version": DECISION_DELTA_METHODOLOGY,
    }


CONVERGENCE_STATES = {state.value for state in ConvergenceState}
