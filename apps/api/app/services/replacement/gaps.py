"""Phase 10 — Evidence gap engine.

A gap is the difference between the evidence a requirement is supposed to have under the decision
policy and the evidence that actually exists. Gaps are what turn "we don't know" from an
embarrassing silence into an actionable work item.

Classification is deterministic and derives entirely from (criticality x what is missing x what the
existing evidence says). Nothing here consults a language model, and nothing here upgrades a status:
a CONFLICTING requirement produces a conflict gap, never a quiet pass.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import (
    EvidenceGapClass,
    EvidenceGapKind,
    MatrixCellStatus,
    RequirementCriticality,
)
from app.models.entities import ExperimentPlan, ExperimentRun
from app.services.replacement.context import CandidateView, PortfolioContext
from app.services.replacement.coverage import coverage_for_candidate
from app.services.replacement.policy import CRITICALITY_ORDER, checksum

EVIDENCE_GAP_METHODOLOGY = "evidence-gap-v1"

GAP_CLASS_ORDER: dict[str, int] = {
    EvidenceGapClass.BLOCKING_GAP: 0,
    EvidenceGapClass.HIGH_VALUE_GAP: 1,
    EvidenceGapClass.NORMAL_GAP: 2,
    EvidenceGapClass.OPTIONAL_GAP: 3,
}

# Criticality decides how loudly a gap is reported. It never decides whether the gap exists.
CLASS_BY_CRITICALITY: dict[str, str] = {
    RequirementCriticality.BLOCKING: EvidenceGapClass.BLOCKING_GAP,
    RequirementCriticality.CRITICAL: EvidenceGapClass.HIGH_VALUE_GAP,
    RequirementCriticality.IMPORTANT: EvidenceGapClass.NORMAL_GAP,
    RequirementCriticality.DESIRABLE: EvidenceGapClass.OPTIONAL_GAP,
    RequirementCriticality.INFORMATIONAL: EvidenceGapClass.OPTIONAL_GAP,
}

GAP_EXPLANATIONS: dict[str, str] = {
    EvidenceGapKind.MISSING_ALL_EVIDENCE:
        "No value of any origin exists for this property in a compatible state.",
    EvidenceGapKind.MISSING_COMPUTATIONAL_EVIDENCE:
        "No reference value, prediction or simulation exists to establish an expected value.",
    EvidenceGapKind.MISSING_SIMULATION:
        "No physics simulation supports this requirement, so the only evidence is a statistical estimate.",
    EvidenceGapKind.MISSING_EXPERIMENT:
        "The decision policy requires physical measurement for this criticality and none is admissible.",
    EvidenceGapKind.INSUFFICIENT_REPLICATES:
        "Fewer admissible replicates exist than the decision policy requires.",
    EvidenceGapKind.UNCERTAIN_EVIDENCE:
        "Evidence exists but straddles the threshold or carries an interval too wide to decide on.",
    EvidenceGapKind.CONFLICTING_EVIDENCE:
        "Sources of different origin disagree on whether this requirement is met.",
    EvidenceGapKind.OUTDATED_EVIDENCE:
        "The supporting industrial evidence is older than the declared freshness horizon.",
    EvidenceGapKind.STATE_MISMATCH:
        "Values exist only for a material state that is not compatible with the state under study.",
    EvidenceGapKind.UNIT_NOT_COMPARABLE:
        "Values exist but their units cannot be compared with the requirement without guessing.",
    EvidenceGapKind.MISSING_INDUSTRIAL_EVIDENCE:
        "No industrial evidence has been recorded for this candidate.",
    EvidenceGapKind.UNRESOLVED_REGULATORY_CONTEXT:
        "The regulatory dimension is unresolved, so a regulatory blocker cannot be ruled out.",
    EvidenceGapKind.UNRESOLVED_SUPPLY_CONTEXT:
        "The supply dimension is unresolved, so a supply blocker cannot be ruled out.",
    EvidenceGapKind.REQUIREMENT_NOT_TESTABLE:
        "The requirement is not bound to a registered property definition, so no evidence can match it.",
}


def _replicate_count(context: PortfolioContext, view: CandidateView, property_key: str | None) -> int:
    """Count admissible measurements behind one property for one candidate.

    Derived from the Phase-9.1 validation payload rather than by re-querying measurements, so the
    admissibility rules (calibration, provenance, run validity) are applied in exactly one place.
    Only measurements that Phase 9.1 admitted appear in `measurement_outcomes`.
    """
    if not property_key:
        return 0
    decision = context.decision_for(view)
    outcomes = (decision.get("scientific_requirements") or {}).get("requirement_outcomes", [])
    for outcome in outcomes:
        if str(outcome.get("property_key")) == str(property_key):
            return len(outcome.get("measurement_outcomes") or [])
    return 0


def _has_experiment_plan(context: PortfolioContext, view: CandidateView, requirement_id: str) -> dict[str, bool]:
    """Whether an experiment plan/run already exists, so the action engine does not re-plan."""
    plans = (
        context.db.query(ExperimentPlan)
        .filter(ExperimentPlan.organisation_id == context.organisation_id,
                ExperimentPlan.candidate_id == view.candidate_id,
                ExperimentPlan.requirement_id == requirement_id)
        .all()
    )
    plan_ids = [p.id for p in plans]
    runs: list[ExperimentRun] = []
    if plan_ids:
        runs = (
            context.db.query(ExperimentRun)
            .filter(ExperimentRun.plan_id.in_(plan_ids))
            .all()
        )
    return {
        "has_plan": bool(plans),
        "has_pending_run": any(r.status in {"planned", "ready"} for r in runs),
        "has_active_run": any(r.status in {"running", "in_progress"} for r in runs),
        "has_completed_run": any(r.status == "completed" for r in runs),
    }


def _classify(criticality: str, kinds: list[str], status: str) -> str:
    base = CLASS_BY_CRITICALITY.get(str(criticality), EvidenceGapClass.NORMAL_GAP)
    if base == EvidenceGapClass.BLOCKING_GAP:
        return base
    # A conflict on a CRITICAL requirement is escalated: two origins contradicting each other on a
    # requirement that gates advancement is not routine housekeeping.
    if str(criticality) == RequirementCriticality.CRITICAL and status == MatrixCellStatus.CONFLICTING:
        return EvidenceGapClass.BLOCKING_GAP
    if EvidenceGapKind.CONFLICTING_EVIDENCE in kinds and base == EvidenceGapClass.NORMAL_GAP:
        return EvidenceGapClass.HIGH_VALUE_GAP
    return base


def gaps_for_candidate(context: PortfolioContext, view: CandidateView) -> list[dict[str, Any]]:
    """Every unresolved-evidence condition for one candidate, with the reason it is unresolved."""
    coverage_rows = coverage_for_candidate(context, view)
    industrial = context.industrial_for(view)
    industrial_states = industrial.get("dimension_states") or {}
    policy_replicates = int(
        (context.policy.required_experimental_validation or {}).get("minimum_replicates", 2)
    )
    criticalities_requiring_experiment = set(
        (context.policy.required_experimental_validation or {}).get(
            "criticalities_requiring_experiment", []
        )
    )

    gaps: list[dict[str, Any]] = []
    for row in coverage_rows:
        kinds: list[str] = []
        status = str(row["governing_status"])
        criticality = str(row["criticality"])
        property_key = row.get("property_key")

        if not property_key:
            kinds.append(EvidenceGapKind.REQUIREMENT_NOT_TESTABLE)
        no_computational = not (row["observed"] or row["predicted"] or row["simulated"])
        if no_computational and not row["experimental"]:
            kinds.append(EvidenceGapKind.MISSING_ALL_EVIDENCE)
        elif no_computational:
            kinds.append(EvidenceGapKind.MISSING_COMPUTATIONAL_EVIDENCE)

        if "experimental" in row["missing_evidence"]:
            kinds.append(EvidenceGapKind.MISSING_EXPERIMENT)
        if criticality in criticalities_requiring_experiment and row["experimental"]:
            replicates = _replicate_count(context, view, property_key)
            if replicates < policy_replicates:
                kinds.append(EvidenceGapKind.INSUFFICIENT_REPLICATES)
        if row["predicted"] and not row["simulated"] and criticality in {
            RequirementCriticality.BLOCKING, RequirementCriticality.CRITICAL
        }:
            kinds.append(EvidenceGapKind.MISSING_SIMULATION)
        if status == MatrixCellStatus.CONFLICTING:
            kinds.append(EvidenceGapKind.CONFLICTING_EVIDENCE)
        if status == MatrixCellStatus.NOT_COMPARABLE:
            kinds.append(EvidenceGapKind.STATE_MISMATCH)
        if row["conditions_comparable"] is False:
            kinds.append(EvidenceGapKind.UNIT_NOT_COMPARABLE)
        if status == MatrixCellStatus.INCONCLUSIVE and EvidenceGapKind.UNIT_NOT_COMPARABLE not in kinds:
            kinds.append(EvidenceGapKind.UNCERTAIN_EVIDENCE)
        if row["fresh_enough"] is False:
            kinds.append(EvidenceGapKind.OUTDATED_EVIDENCE)

        if not kinds:
            continue

        experiment_state = _has_experiment_plan(context, view, str(row["requirement_id"]))
        gap_class = _classify(criticality, kinds, status)
        gaps.append({
            "gap_id": f"{view.candidate_id}:{row['requirement_id']}",
            "candidate_id": view.candidate_id,
            "candidate_display_name": view.display_name,
            "requirement_id": row["requirement_id"],
            "requirement_key": row["requirement_key"],
            "requirement_display_name": row["display_name"],
            "property_key": property_key,
            "criticality": criticality,
            "is_gating": row["is_gating"],
            "governing_status": status,
            "gap_class": gap_class,
            "gap_kinds": sorted(set(kinds)),
            "why_unresolved": " ".join(
                GAP_EXPLANATIONS[k] for k in sorted(set(kinds)) if k in GAP_EXPLANATIONS
            ),
            "existing_evidence": {
                "observed": row["observed"], "predicted": row["predicted"],
                "simulated": row["simulated"], "experimental": row["experimental"],
                "industrial": row["industrial"],
            },
            "missing_evidence": row["missing_evidence"],
            "coverage_score": row["coverage_score"],
            "experiment_state": experiment_state,
            # Effort metadata is only reported when it genuinely exists in the platform.
            "estimated_effort": "unknown",
            "methodology_version": EVIDENCE_GAP_METHODOLOGY,
        })

    # Program-level industrial gaps are attached to the candidate rather than invented as pseudo
    # requirements, so they cannot be mistaken for scientific requirements.
    for dimension, gap_kind in (
        ("regulatory_compatibility", EvidenceGapKind.UNRESOLVED_REGULATORY_CONTEXT),
        ("supply_resilience", EvidenceGapKind.UNRESOLVED_SUPPLY_CONTEXT),
    ):
        state = str(industrial_states.get(dimension, "unknown"))
        if state in {"unknown", "insufficient_evidence", "not_assessed"}:
            gaps.append({
                "gap_id": f"{view.candidate_id}:industrial:{dimension}",
                "candidate_id": view.candidate_id,
                "candidate_display_name": view.display_name,
                "requirement_id": None, "requirement_key": None,
                "requirement_display_name": f"Industrial dimension: {dimension}",
                "property_key": None,
                "criticality": RequirementCriticality.CRITICAL,
                "is_gating": True,
                "governing_status": MatrixCellStatus.UNKNOWN,
                "gap_class": EvidenceGapClass.HIGH_VALUE_GAP,
                "gap_kinds": [gap_kind],
                "why_unresolved": GAP_EXPLANATIONS[gap_kind],
                "existing_evidence": {"industrial": bool(
                    (industrial.get("evidence_snapshot") or {}).get("evidence")
                )},
                "missing_evidence": ["industrial"],
                "coverage_score": 0.0,
                "experiment_state": {"has_plan": False, "has_pending_run": False,
                                     "has_active_run": False, "has_completed_run": False},
                "estimated_effort": "unknown",
                "methodology_version": EVIDENCE_GAP_METHODOLOGY,
            })

    if not (industrial.get("evidence_snapshot") or {}).get("evidence"):
        gaps.append({
            "gap_id": f"{view.candidate_id}:industrial:missing",
            "candidate_id": view.candidate_id,
            "candidate_display_name": view.display_name,
            "requirement_id": None, "requirement_key": None,
            "requirement_display_name": "Industrial evidence",
            "property_key": None,
            "criticality": RequirementCriticality.IMPORTANT,
            "is_gating": False,
            "governing_status": MatrixCellStatus.UNKNOWN,
            "gap_class": EvidenceGapClass.NORMAL_GAP,
            "gap_kinds": [EvidenceGapKind.MISSING_INDUSTRIAL_EVIDENCE],
            "why_unresolved": GAP_EXPLANATIONS[EvidenceGapKind.MISSING_INDUSTRIAL_EVIDENCE],
            "existing_evidence": {"industrial": False},
            "missing_evidence": ["industrial"],
            "coverage_score": 0.0,
            "experiment_state": {"has_plan": False, "has_pending_run": False,
                                 "has_active_run": False, "has_completed_run": False},
            "estimated_effort": "unknown",
            "methodology_version": EVIDENCE_GAP_METHODOLOGY,
        })

    return sorted(gaps, key=lambda g: (
        GAP_CLASS_ORDER.get(str(g["gap_class"]), 9),
        CRITICALITY_ORDER.get(str(g["criticality"]), 9),
        str(g["gap_id"]),
    ))


def program_gaps(context: PortfolioContext) -> dict[str, Any]:
    """Gap set for the whole portfolio, grouped by class for the mission-control gap view."""
    per_candidate: dict[str, list[dict[str, Any]]] = {}
    all_gaps: list[dict[str, Any]] = []
    for view in context.candidates:
        rows = gaps_for_candidate(context, view)
        per_candidate[view.candidate_id] = rows
        all_gaps.extend(rows)

    grouped: dict[str, list[dict[str, Any]]] = {c.value: [] for c in EvidenceGapClass}
    for gap in all_gaps:
        grouped[str(gap["gap_class"])].append(gap)

    # Blocking gaps first, then high-value, then the rest. A reviewer opening this view should see
    # the work that actually gates a decision before the work that merely improves confidence.
    class_order = {c.value: index for index, c in enumerate(EvidenceGapClass)}
    all_gaps.sort(key=lambda gap: (
        class_order[str(gap["gap_class"])],
        str(gap["candidate_display_name"]),
        str(gap["requirement_key"]),
    ))

    return {
        "program_id": context.program.id,
        "gaps": all_gaps,
        "by_class": grouped,
        "by_candidate": per_candidate,
        "counts": {name: len(rows) for name, rows in grouped.items()},
        "blocking_gap_count": len(grouped[EvidenceGapClass.BLOCKING_GAP.value]),
        "methodology_version": EVIDENCE_GAP_METHODOLOGY,
        "note": (
            "A gap states that required evidence is absent, uncertain, conflicting or not "
            "comparable. It is never a statement that a candidate has failed."
        ),
    }


def gap_checksum(gaps: list[dict[str, Any]]) -> str:
    return checksum({
        "methodology": EVIDENCE_GAP_METHODOLOGY,
        "gaps": sorted(
            [{"gap_id": g["gap_id"], "class": g["gap_class"], "kinds": g["gap_kinds"],
              "status": g["governing_status"]} for g in gaps],
            key=lambda g: str(g["gap_id"]),
        ),
    })
