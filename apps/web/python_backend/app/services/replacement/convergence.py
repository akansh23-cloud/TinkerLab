"""Phase 10 — Convergence engine.

Convergence answers "how close is this program to a decision I could defend?" — not "how likely is
this replacement to work?". Those are different questions and the second one is not answerable from
the evidence TinkerLab holds.

So convergence is a **state plus a set of counted metrics**, never a single number that reads as a
probability. A presentation-only percentage is derived for progress bars, and it is explicitly
labelled as the fraction of resolvable decision work completed, with every underlying count
retained beside it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    OPEN_ACTION_STATUSES,
    CandidateEligibility,
    ConvergenceState,
    EvidenceGapClass,
    MatrixCellStatus,
    RequirementCriticality,
)
from app.models.entities import ConvergenceAssessment, ScientificAction
from app.services.replacement.context import PortfolioContext
from app.services.replacement.coverage import coverage_for_candidate
from app.services.replacement.gaps import gaps_for_candidate
from app.services.replacement.policy import checksum

CONVERGENCE_METHODOLOGY = "convergence-v1"

CONVERGENCE_NOTE = (
    "Convergence measures how much of the decision work is complete and defensible. It is not a "
    "probability of replacement success, and a high percentage is not a prediction that the "
    "candidate will perform."
)


def _candidate_metrics(context: PortfolioContext, view: Any) -> dict[str, Any]:
    from app.services.replacement.portfolio import candidate_decision_state

    state = candidate_decision_state(context, view)
    coverage = coverage_for_candidate(context, view)
    gaps = gaps_for_candidate(context, view)

    blocking = [r for r in coverage if str(r["criticality"]) == RequirementCriticality.BLOCKING]
    critical = [r for r in coverage if str(r["criticality"]) == RequirementCriticality.CRITICAL]
    gating = [r for r in coverage if r["is_gating"]]

    def resolved(rows: list[dict[str, Any]]) -> int:
        return sum(
            1 for r in rows
            if str(r["governing_status"]) in {MatrixCellStatus.PASS, MatrixCellStatus.FAIL}
        )

    industrial = context.industrial_for(view)
    dimension_states = industrial.get("dimension_states") or {}
    resolved_dimensions = sum(
        1 for state_value in dimension_states.values()
        if str(state_value) in {"pass", "partial", "fail"}
    )

    return {
        "candidate_id": view.candidate_id,
        "display_name": view.display_name,
        "eligibility": state["eligibility"],
        "portfolio_state": state["portfolio_state"],
        "gates_satisfied": state["gates_satisfied"],
        "blocking_requirements_total": len(blocking),
        "blocking_requirements_resolved": resolved(blocking),
        "critical_requirements_total": len(critical),
        "critical_requirements_resolved": resolved(critical),
        "gating_requirements_total": len(gating),
        "gating_requirements_with_governing_evidence": sum(
            1 for r in gating if r["governing_origin"] is not None
        ),
        "experimental_requirements_total": sum(
            1 for r in gating if "experimental" in (r["expected_evidence"] or [])
        ),
        "experimental_requirements_validated": sum(
            1 for r in gating
            if "experimental" in (r["expected_evidence"] or []) and r["experimental"]
        ),
        "industrial_dimensions_total": len(dimension_states),
        "industrial_dimensions_resolved": resolved_dimensions,
        "unresolved_conflicts": sum(
            1 for r in coverage if str(r["governing_status"]) == MatrixCellStatus.CONFLICTING
        ),
        "blocking_evidence_gaps": sum(
            1 for g in gaps if str(g["gap_class"]) == EvidenceGapClass.BLOCKING_GAP
        ),
    }


def assess_convergence(context: PortfolioContext) -> dict[str, Any]:
    """Compute the program's convergence state and its metrics. Persists nothing."""
    per_candidate = [_candidate_metrics(context, view) for view in context.candidates]

    open_action_count = (
        context.db.query(ScientificAction)
        .filter(ScientificAction.program_id == context.program.id,
                ScientificAction.organisation_id == context.organisation_id,
                ScientificAction.status.in_(sorted(OPEN_ACTION_STATUSES)))
        .count()
    )

    def total(key: str) -> int:
        return sum(int(row[key]) for row in per_candidate)

    metrics = {
        "candidate_count": len(per_candidate),
        "eligible_candidate_count": sum(
            1 for r in per_candidate if r["eligibility"] == CandidateEligibility.ELIGIBLE
        ),
        "unresolved_candidate_count": sum(
            1 for r in per_candidate if r["eligibility"] == CandidateEligibility.UNRESOLVED
        ),
        "blocked_candidate_count": sum(
            1 for r in per_candidate if r["eligibility"] == CandidateEligibility.BLOCKED
        ),
        "decision_ready_candidate_count": sum(1 for r in per_candidate if r["gates_satisfied"]),
        "blocking_requirements_resolved": total("blocking_requirements_resolved"),
        "blocking_requirements_total": total("blocking_requirements_total"),
        "critical_requirements_resolved": total("critical_requirements_resolved"),
        "critical_requirements_total": total("critical_requirements_total"),
        "requirements_with_governing_evidence": total("gating_requirements_with_governing_evidence"),
        "gating_requirements_total": total("gating_requirements_total"),
        "experimental_requirements_validated": total("experimental_requirements_validated"),
        "experimental_requirements_total": total("experimental_requirements_total"),
        "industrial_dimensions_resolved": total("industrial_dimensions_resolved"),
        "industrial_dimensions_total": total("industrial_dimensions_total"),
        "unresolved_conflicts": total("unresolved_conflicts"),
        "blocking_evidence_gaps": total("blocking_evidence_gaps"),
        "open_mandatory_actions": open_action_count,
    }

    reason_codes: list[str] = []
    reasons: list[str] = []

    # The ladder is evaluated top-down; the first matching condition wins, so the reported state is
    # always the earliest genuine obstacle rather than the most flattering one.
    if not per_candidate:
        state = ConvergenceState.EARLY
        reason_codes.append("NO_CANDIDATES")
        reasons.append("The program has no candidates in its portfolio yet.")
    elif not context.requirements:
        state = ConvergenceState.EARLY
        reason_codes.append("NO_REQUIREMENTS")
        reasons.append("The program has no functional requirements, so nothing can be evaluated.")
    elif metrics["eligible_candidate_count"] == 0 and metrics["unresolved_candidate_count"] == 0:
        state = ConvergenceState.NO_VIABLE_CANDIDATE
        reason_codes.append("ALL_CANDIDATES_BLOCKED")
        reasons.append(
            "Every candidate has a definitive blocking failure or an industrial hard failure. "
            "No candidate remains that further evidence could advance without a change of scope."
        )
    elif metrics["decision_ready_candidate_count"] > 0 and metrics["blocking_evidence_gaps"] == 0:
        state = ConvergenceState.DECISION_READY
        reason_codes.append("GATES_SATISFIED_FOR_AT_LEAST_ONE_CANDIDATE")
        reasons.append(
            f"{metrics['decision_ready_candidate_count']} candidate(s) satisfy every configured "
            "gate with no outstanding blocking evidence gap."
        )
    elif metrics["unresolved_conflicts"] > 0:
        state = ConvergenceState.CONFLICT_RESOLUTION
        reason_codes.append("UNRESOLVED_EVIDENCE_CONFLICTS")
        reasons.append(
            f"{metrics['unresolved_conflicts']} requirement(s) have origins that disagree. A "
            "conflict is resolved by investigation, not by preferring one origin."
        )
    elif metrics["blocking_evidence_gaps"] > 0:
        experimental_shortfall = (
            metrics["experimental_requirements_total"] - metrics["experimental_requirements_validated"]
        )
        if experimental_shortfall > 0 and metrics["requirements_with_governing_evidence"] > 0:
            state = ConvergenceState.VALIDATION_REQUIRED
            reason_codes.append("PHYSICAL_VALIDATION_OUTSTANDING")
            reasons.append(
                f"{experimental_shortfall} requirement(s) need admissible physical measurement "
                "under the current decision policy."
            )
        else:
            state = ConvergenceState.EVIDENCE_BUILDING
            reason_codes.append("BLOCKING_EVIDENCE_GAPS_OPEN")
            reasons.append(
                f"{metrics['blocking_evidence_gaps']} blocking evidence gap(s) remain open."
            )
    elif metrics["eligible_candidate_count"] > 0:
        state = ConvergenceState.NEAR_DECISION
        reason_codes.append("ELIGIBLE_CANDIDATES_AWAITING_FINAL_GATES")
        reasons.append(
            "Eligible candidates exist but at least one configured gate is not yet satisfied."
        )
    else:
        state = ConvergenceState.SCREENING
        reason_codes.append("SCREENING_IN_PROGRESS")
        reasons.append("Candidates are still being screened against the requirement set.")

    if metrics["open_mandatory_actions"] > 0:
        reason_codes.append("OPEN_ACTIONS_OUTSTANDING")

    # Presentation-only progress. Deliberately built from resolved-work counts so that it cannot be
    # read as a success likelihood, and always shipped next to the counts it came from.
    denominators = [
        (metrics["blocking_requirements_resolved"], metrics["blocking_requirements_total"]),
        (metrics["critical_requirements_resolved"], metrics["critical_requirements_total"]),
        (metrics["experimental_requirements_validated"], metrics["experimental_requirements_total"]),
        (metrics["industrial_dimensions_resolved"], metrics["industrial_dimensions_total"]),
    ]
    numerator = sum(n for n, d in denominators if d > 0)
    denominator = sum(d for _n, d in denominators if d > 0)
    progress = round(100.0 * numerator / denominator, 2) if denominator > 0 else 0.0

    payload = {
        "program_id": context.program.id,
        "convergence_state": str(state),
        "metrics": metrics,
        "per_candidate": per_candidate,
        "reason_codes": sorted(set(reason_codes)),
        "reasons": reasons,
        "presentation_progress_percent": progress,
        "decision_policy_version": context.policy.version,
        "methodology_version": CONVERGENCE_METHODOLOGY,
        "note": CONVERGENCE_NOTE,
        "probability_disclaimer": (
            f"{progress}% describes how much of the resolvable decision work is complete. It is not "
            f"a probability: it does not mean there is a {progress}% chance that a replacement "
            "succeeds, and it carries no confidence level."
        ),
    }
    payload["assessment_checksum"] = checksum({
        "methodology": CONVERGENCE_METHODOLOGY,
        "policy": context.policy.version,
        "state": str(state),
        "metrics": metrics,
        "per_candidate": sorted(per_candidate, key=lambda r: str(r["candidate_id"])),
    })
    return payload


def persist_convergence(
    db: Session, context: PortfolioContext, payload: dict[str, Any]
) -> ConvergenceAssessment:
    """Store an immutable convergence assessment, superseding the previous one."""
    row = ConvergenceAssessment(
        organisation_id=context.organisation_id, program_id=context.program.id,
        convergence_state=str(payload["convergence_state"]), metrics=payload["metrics"],
        per_candidate=payload["per_candidate"], reason_codes=payload["reason_codes"],
        reasons=payload["reasons"],
        presentation_progress_percent=float(payload["presentation_progress_percent"]),
        decision_policy_version=str(payload["decision_policy_version"]),
        methodology_version=CONVERGENCE_METHODOLOGY,
        assessment_checksum=str(payload["assessment_checksum"]),
    )
    db.add(row)
    db.flush()
    for previous in (
        db.query(ConvergenceAssessment)
        .filter(ConvergenceAssessment.program_id == context.program.id,
                ConvergenceAssessment.organisation_id == context.organisation_id,
                ConvergenceAssessment.superseded_by_id.is_(None),
                ConvergenceAssessment.id != row.id)
        .all()
    ):
        previous.superseded_by_id = row.id
    db.flush()
    return row


def latest_convergence(
    db: Session, *, organisation_id: str, program_id: str
) -> ConvergenceAssessment | None:
    return (
        db.query(ConvergenceAssessment)
        .filter(ConvergenceAssessment.organisation_id == organisation_id,
                ConvergenceAssessment.program_id == program_id,
                ConvergenceAssessment.superseded_by_id.is_(None))
        .order_by(ConvergenceAssessment.created_at.desc(), ConvergenceAssessment.id)
        .first()
    )
