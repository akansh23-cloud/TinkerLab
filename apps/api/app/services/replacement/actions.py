"""Phase 10 — Next-best scientific action engine.

Given a gap, what should a scientist actually do next? The mapping is a lookup table, not a
judgement call, and it is deliberately so: the value of this engine is that the same evidence state
always produces the same recommended action, and that a reviewer can read why.

**No language model participates in choosing an action.** An LLM may later reword the `reason` text
for a human reader; it cannot change the action type, the priority, or the ordering.

Priority methodology (`next-action-priority-v1`)
------------------------------------------------
    priority = decision_impact x decision_value x candidate_relevance / cost_factor

Every factor comes from a declared lookup table below, and every factor is returned alongside the
score so the arithmetic is reproducible by hand. This is a transparent decision-value model, NOT
expected value of information: no probability distribution over outcomes is estimated anywhere, so
none is claimed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    OPEN_ACTION_STATUSES,
    ActionCostClass,
    DecisionValueClass,
    EvidenceGapClass,
    EvidenceGapKind,
    MatrixCellStatus,
    RequirementCriticality,
    ScientificActionStatus,
    ScientificActionType,
)
from app.models.entities import ScientificAction
from app.services.replacement.context import CandidateView, PortfolioContext
from app.services.replacement.gaps import gaps_for_candidate
from app.services.replacement.policy import CRITICALITY_ORDER

NEXT_ACTION_METHODOLOGY = "next-action-v1"
PRIORITY_METHODOLOGY = "next-action-priority-v1"

# --------------------------------------------------------------------------------------------
# Declared priority factors. Changing any number here changes the methodology version.
# --------------------------------------------------------------------------------------------
DECISION_IMPACT: dict[str, float] = {
    RequirementCriticality.BLOCKING: 1.00,
    RequirementCriticality.CRITICAL: 0.75,
    RequirementCriticality.IMPORTANT: 0.45,
    RequirementCriticality.DESIRABLE: 0.20,
    RequirementCriticality.INFORMATIONAL: 0.05,
}

DECISION_VALUE: dict[str, float] = {
    DecisionValueClass.HIGH: 1.00,
    DecisionValueClass.MEDIUM: 0.60,
    DecisionValueClass.LOW: 0.25,
    DecisionValueClass.NONE: 0.00,
}

# How relevant the candidate still is to the decision. A candidate already blocked by a definitive
# hard failure is not worth expensive new work, but it is not zero either: evidence that overturns a
# blocker is legitimate and occasionally correct.
CANDIDATE_RELEVANCE: dict[str, float] = {
    "eligible": 1.00,
    "unresolved": 0.80,
    "blocked": 0.30,
    "rejected": 0.05,
}

# Declared relative effort of each action class. These are effort classes, not currency or hours —
# TinkerLab does not know what a given experiment costs in a given laboratory.
COST_FACTOR: dict[str, float] = {
    ActionCostClass.LOW: 1.0,
    ActionCostClass.MEDIUM: 1.6,
    ActionCostClass.HIGH: 2.6,
    ActionCostClass.UNKNOWN: 1.3,
}

ACTION_COST_CLASS: dict[str, str] = {
    ScientificActionType.COLLECT_REFERENCE_DATA: ActionCostClass.LOW,
    ScientificActionType.RESOLVE_MATERIAL_STATE: ActionCostClass.LOW,
    ScientificActionType.CHECK_REGULATION: ActionCostClass.LOW,
    ScientificActionType.CHECK_SUPPLY: ActionCostClass.LOW,
    ScientificActionType.ADD_INDUSTRIAL_EVIDENCE: ActionCostClass.LOW,
    ScientificActionType.RUN_PROPERTY_PREDICTION: ActionCostClass.LOW,
    ScientificActionType.INVESTIGATE_CONFLICT: ActionCostClass.MEDIUM,
    ScientificActionType.CREATE_EXPERIMENT_PLAN: ActionCostClass.LOW,
    ScientificActionType.RUN_PHYSICS_SIMULATION: ActionCostClass.MEDIUM,
    ScientificActionType.RUN_ADDITIONAL_SIMULATION: ActionCostClass.MEDIUM,
    ScientificActionType.RUN_EXPERIMENT: ActionCostClass.HIGH,
    ScientificActionType.RUN_ADDITIONAL_REPLICATE: ActionCostClass.MEDIUM,
    ScientificActionType.RUN_CONTROL: ActionCostClass.MEDIUM,
    ScientificActionType.REJECT_CANDIDATE: ActionCostClass.LOW,
    ScientificActionType.ADVANCE_CANDIDATE: ActionCostClass.LOW,
    ScientificActionType.NO_ACTION_REQUIRED: ActionCostClass.LOW,
}

# The dependency chain. An experiment is not planned before the material state is even resolved, and
# a simulation is not launched before a cheap reference lookup has been attempted.
DEPENDENCY_ORDER: list[str] = [
    ScientificActionType.RESOLVE_MATERIAL_STATE,
    ScientificActionType.COLLECT_REFERENCE_DATA,
    ScientificActionType.RUN_PROPERTY_PREDICTION,
    ScientificActionType.RUN_PHYSICS_SIMULATION,
    ScientificActionType.RUN_ADDITIONAL_SIMULATION,
    ScientificActionType.CREATE_EXPERIMENT_PLAN,
    ScientificActionType.RUN_EXPERIMENT,
    ScientificActionType.RUN_ADDITIONAL_REPLICATE,
    ScientificActionType.RUN_CONTROL,
]
DEPENDENCY_INDEX: dict[str, int] = {name: i for i, name in enumerate(DEPENDENCY_ORDER)}

ACTION_DESCRIPTIONS: dict[str, str] = {
    ScientificActionType.COLLECT_REFERENCE_DATA:
        "Locate an existing reference or literature value for this property in a compatible state.",
    ScientificActionType.RUN_PROPERTY_PREDICTION:
        "Run a registered property prediction model to establish an expected value with an interval.",
    ScientificActionType.RUN_PHYSICS_SIMULATION:
        "Run a physics simulation so the requirement rests on more than a statistical estimate.",
    ScientificActionType.RUN_ADDITIONAL_SIMULATION:
        "Run an additional simulation at a different fidelity to test whether the result is robust.",
    ScientificActionType.RESOLVE_MATERIAL_STATE:
        "Declare or correct the material state so existing values become comparable to this study.",
    ScientificActionType.ADD_INDUSTRIAL_EVIDENCE:
        "Record industrial evidence so manufacturing, cost and supply can be assessed at all.",
    ScientificActionType.CHECK_REGULATION:
        "Resolve the regulatory context for the target jurisdictions.",
    ScientificActionType.CHECK_SUPPLY:
        "Resolve supplier availability and concentration for this material.",
    ScientificActionType.CREATE_EXPERIMENT_PLAN:
        "Create an experiment plan against a frozen protocol version for this requirement.",
    ScientificActionType.RUN_EXPERIMENT:
        "Execute the planned run and record the measurement with full provenance.",
    ScientificActionType.RUN_ADDITIONAL_REPLICATE:
        "Execute an additional replicate to satisfy the policy's replicate requirement.",
    ScientificActionType.RUN_CONTROL:
        "Execute the control specified by the protocol so the session is admissible.",
    ScientificActionType.INVESTIGATE_CONFLICT:
        "Investigate why two origins disagree; do not average them or discard the inconvenient one.",
    ScientificActionType.REJECT_CANDIDATE:
        "Record rejection: a blocking requirement has definitively failed under admissible evidence.",
    ScientificActionType.ADVANCE_CANDIDATE:
        "Record advancement to the next gate: every configured gate is satisfied.",
    ScientificActionType.NO_ACTION_REQUIRED:
        "No outstanding scientific action for this candidate under the current policy.",
}


def _decision_value(gap: dict[str, Any]) -> str:
    """Transparent decision-value class. Explicitly not a Bayesian information gain."""
    gap_class = str(gap["gap_class"])
    status = str(gap["governing_status"])
    if gap_class == EvidenceGapClass.BLOCKING_GAP:
        return DecisionValueClass.HIGH
    if status == MatrixCellStatus.CONFLICTING and gap.get("is_gating"):
        return DecisionValueClass.HIGH
    if gap_class == EvidenceGapClass.HIGH_VALUE_GAP:
        return DecisionValueClass.MEDIUM
    if gap_class == EvidenceGapClass.NORMAL_GAP:
        return DecisionValueClass.MEDIUM if gap.get("is_gating") else DecisionValueClass.LOW
    return DecisionValueClass.LOW


def _action_for_gap(gap: dict[str, Any], policy_requires_experiment: bool) -> tuple[str, str]:
    """Deterministic (action_type, reason_code) for one gap. Order of tests is the specification."""
    kinds = set(gap["gap_kinds"])
    experiment_state = gap.get("experiment_state") or {}

    if EvidenceGapKind.REQUIREMENT_NOT_TESTABLE in kinds:
        return ScientificActionType.COLLECT_REFERENCE_DATA, "REQUIREMENT_NOT_BOUND_TO_PROPERTY"
    if EvidenceGapKind.STATE_MISMATCH in kinds:
        return ScientificActionType.RESOLVE_MATERIAL_STATE, "EVIDENCE_ONLY_IN_INCOMPATIBLE_STATE"
    if EvidenceGapKind.UNIT_NOT_COMPARABLE in kinds:
        return ScientificActionType.COLLECT_REFERENCE_DATA, "EVIDENCE_UNITS_NOT_COMPARABLE"
    if EvidenceGapKind.CONFLICTING_EVIDENCE in kinds:
        return ScientificActionType.INVESTIGATE_CONFLICT, "ORIGINS_DISAGREE"
    if EvidenceGapKind.UNRESOLVED_REGULATORY_CONTEXT in kinds:
        return ScientificActionType.CHECK_REGULATION, "REGULATORY_DIMENSION_UNRESOLVED"
    if EvidenceGapKind.UNRESOLVED_SUPPLY_CONTEXT in kinds:
        return ScientificActionType.CHECK_SUPPLY, "SUPPLY_DIMENSION_UNRESOLVED"
    if EvidenceGapKind.MISSING_INDUSTRIAL_EVIDENCE in kinds:
        return ScientificActionType.ADD_INDUSTRIAL_EVIDENCE, "NO_INDUSTRIAL_EVIDENCE_RECORDED"
    if EvidenceGapKind.OUTDATED_EVIDENCE in kinds:
        return ScientificActionType.ADD_INDUSTRIAL_EVIDENCE, "INDUSTRIAL_EVIDENCE_STALE"
    if EvidenceGapKind.MISSING_ALL_EVIDENCE in kinds:
        return ScientificActionType.COLLECT_REFERENCE_DATA, "NO_EVIDENCE_OF_ANY_ORIGIN"
    if EvidenceGapKind.MISSING_COMPUTATIONAL_EVIDENCE in kinds:
        return ScientificActionType.RUN_PROPERTY_PREDICTION, "NO_COMPUTATIONAL_ESTIMATE"
    if EvidenceGapKind.INSUFFICIENT_REPLICATES in kinds:
        return ScientificActionType.RUN_ADDITIONAL_REPLICATE, "REPLICATE_REQUIREMENT_NOT_MET"
    if EvidenceGapKind.MISSING_EXPERIMENT in kinds and policy_requires_experiment:
        if experiment_state.get("has_pending_run") or experiment_state.get("has_active_run"):
            return ScientificActionType.RUN_EXPERIMENT, "PLANNED_RUN_AWAITING_EXECUTION"
        if experiment_state.get("has_plan"):
            return ScientificActionType.RUN_EXPERIMENT, "EXPERIMENT_PLAN_EXISTS_WITHOUT_RUN"
        return ScientificActionType.CREATE_EXPERIMENT_PLAN, "POLICY_REQUIRES_PHYSICAL_MEASUREMENT"
    if EvidenceGapKind.MISSING_SIMULATION in kinds:
        return ScientificActionType.RUN_PHYSICS_SIMULATION, "ONLY_STATISTICAL_ESTIMATE_AVAILABLE"
    if EvidenceGapKind.UNCERTAIN_EVIDENCE in kinds:
        return ScientificActionType.RUN_ADDITIONAL_SIMULATION, "EVIDENCE_STRADDLES_THRESHOLD"
    return ScientificActionType.COLLECT_REFERENCE_DATA, "UNRESOLVED_EVIDENCE"


def _priority(*, criticality: str, decision_value: str, relevance: str, action_type: str) -> tuple[float, dict[str, Any]]:
    impact = DECISION_IMPACT.get(str(criticality), 0.45)
    value = DECISION_VALUE.get(str(decision_value), 0.25)
    candidate_factor = CANDIDATE_RELEVANCE.get(str(relevance), 0.8)
    cost_class = ACTION_COST_CLASS.get(str(action_type), ActionCostClass.UNKNOWN)
    cost = COST_FACTOR.get(str(cost_class), 1.3)
    score = round((impact * value * candidate_factor) / cost, 6)
    return score, {
        "decision_impact": impact,
        "decision_value": value,
        "decision_value_class": decision_value,
        "candidate_relevance": candidate_factor,
        "candidate_relevance_class": relevance,
        "cost_class": cost_class,
        "cost_factor": cost,
        "formula": "priority = decision_impact * decision_value * candidate_relevance / cost_factor",
        "methodology_version": PRIORITY_METHODOLOGY,
        "note": (
            "A transparent decision-value model. No probability distribution over experimental "
            "outcomes is estimated, so no expected value of information is claimed."
        ),
    }


def next_actions_for_candidate(
    context: PortfolioContext, view: CandidateView, *, eligibility: str,
) -> list[dict[str, Any]]:
    """Deterministic action list for one candidate, ordered by priority then by stable key."""
    from app.services.replacement.portfolio import candidate_decision_state

    gaps = gaps_for_candidate(context, view)
    state = candidate_decision_state(context, view)
    criticalities_requiring_experiment = set(
        (context.policy.required_experimental_validation or {}).get(
            "criticalities_requiring_experiment", []
        )
    )

    proposals: list[dict[str, Any]] = []

    # A definitive blocking failure produces a rejection recommendation, not more evidence work.
    if state["definitive_blocking_failures"]:
        score, factors = _priority(
            criticality=RequirementCriticality.BLOCKING, decision_value=DecisionValueClass.HIGH,
            relevance="blocked", action_type=ScientificActionType.REJECT_CANDIDATE,
        )
        blocking_keys = ", ".join(
            str(b.get("requirement_key") or b.get("requirement_id"))
            for b in state["definitive_blocking_failures"]
        )
        proposals.append({
            "action_signature": f"{view.candidate_id}:reject",
            "candidate_id": view.candidate_id, "requirement_id": None,
            "action_type": ScientificActionType.REJECT_CANDIDATE,
            "reason_code": "BLOCKING_REQUIREMENT_DEFINITIVELY_FAILED",
            "reason": (
                f"{ACTION_DESCRIPTIONS[ScientificActionType.REJECT_CANDIDATE]} Failing "
                f"requirement(s): {blocking_keys}."
            ),
            "what_it_could_resolve": "Closes this candidate with a recorded, evidence-linked reason.",
            "resolves_gap_kind": None,
            "priority": score, "priority_factors": factors,
            "decision_value_class": DecisionValueClass.HIGH,
            "cost_class": ACTION_COST_CLASS[ScientificActionType.REJECT_CANDIDATE],
            "depends_on_types": [],
        })

    for gap in gaps:
        criticality = str(gap["criticality"])
        policy_requires_experiment = criticality in criticalities_requiring_experiment
        action_type, reason_code = _action_for_gap(gap, policy_requires_experiment)
        decision_value = _decision_value(gap)
        score, factors = _priority(
            criticality=criticality, decision_value=decision_value,
            relevance=eligibility, action_type=action_type,
        )
        requirement_label = gap.get("requirement_key") or gap.get("requirement_display_name")
        proposals.append({
            "action_signature": f"{view.candidate_id}:{gap['gap_id']}:{action_type}",
            "candidate_id": view.candidate_id,
            "requirement_id": gap.get("requirement_id"),
            "action_type": action_type,
            "reason_code": reason_code,
            "reason": f"{ACTION_DESCRIPTIONS[action_type]} Requirement: {requirement_label}.",
            "what_it_could_resolve": (
                f"Could move '{requirement_label}' from {gap['governing_status']} to a decided status."
                if gap.get("is_gating") else
                f"Would improve confidence on the non-gating requirement '{requirement_label}'."
            ),
            "resolves_gap_kind": gap["gap_kinds"][0] if gap["gap_kinds"] else None,
            "gap_class": gap["gap_class"],
            "priority": score, "priority_factors": factors,
            "decision_value_class": decision_value,
            "cost_class": ACTION_COST_CLASS.get(action_type, ActionCostClass.UNKNOWN),
            "depends_on_types": [
                other for other in DEPENDENCY_ORDER
                if DEPENDENCY_INDEX.get(other, 99) < DEPENDENCY_INDEX.get(action_type, -1)
            ],
        })

    if not proposals:
        if state["eligibility"] == "eligible" and state["gates_satisfied"]:
            score, factors = _priority(
                criticality=RequirementCriticality.BLOCKING, decision_value=DecisionValueClass.HIGH,
                relevance="eligible", action_type=ScientificActionType.ADVANCE_CANDIDATE,
            )
            proposals.append({
                "action_signature": f"{view.candidate_id}:advance",
                "candidate_id": view.candidate_id, "requirement_id": None,
                "action_type": ScientificActionType.ADVANCE_CANDIDATE,
                "reason_code": "ALL_CONFIGURED_GATES_SATISFIED",
                "reason": ACTION_DESCRIPTIONS[ScientificActionType.ADVANCE_CANDIDATE],
                "what_it_could_resolve": "Records the advancement decision with its policy version.",
                "resolves_gap_kind": None,
                "priority": score, "priority_factors": factors,
                "decision_value_class": DecisionValueClass.HIGH,
                "cost_class": ACTION_COST_CLASS[ScientificActionType.ADVANCE_CANDIDATE],
                "depends_on_types": [],
            })
        else:
            proposals.append({
                "action_signature": f"{view.candidate_id}:none",
                "candidate_id": view.candidate_id, "requirement_id": None,
                "action_type": ScientificActionType.NO_ACTION_REQUIRED,
                "reason_code": "NO_OUTSTANDING_GAP",
                "reason": ACTION_DESCRIPTIONS[ScientificActionType.NO_ACTION_REQUIRED],
                "what_it_could_resolve": None, "resolves_gap_kind": None,
                "priority": 0.0,
                "priority_factors": {"methodology_version": PRIORITY_METHODOLOGY},
                "decision_value_class": DecisionValueClass.NONE,
                "cost_class": ActionCostClass.LOW, "depends_on_types": [],
            })

    # Descending priority, then a stable alphabetical tiebreak so equal-priority actions never
    # reorder between two identical requests.
    proposals.sort(key=lambda p: (-float(p["priority"]), str(p["action_signature"])))
    return proposals


def _wire_dependencies(proposals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Link each action to the earlier-stage actions it must wait for, within the same requirement.

    Dependencies are scoped per (candidate, requirement): a simulation for one property does not
    block an experiment for another. Actions with an unmet dependency are BLOCKED, not hidden.
    """
    by_key: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for proposal in proposals:
        key = (str(proposal["candidate_id"]), proposal.get("requirement_id"))
        by_key.setdefault(key, []).append(proposal)

    signature_index = {p["action_signature"]: p for p in proposals}
    for group in by_key.values():
        ordered = sorted(
            group, key=lambda p: DEPENDENCY_INDEX.get(str(p["action_type"]), 99)
        )
        for index, proposal in enumerate(ordered):
            stage = DEPENDENCY_INDEX.get(str(proposal["action_type"]))
            if stage is None:
                proposal["depends_on"] = []
                continue
            depends = [
                other["action_signature"] for other in ordered[:index]
                if DEPENDENCY_INDEX.get(str(other["action_type"]), 99) < stage
            ]
            proposal["depends_on"] = sorted(depends)
    for proposal in proposals:
        proposal.setdefault("depends_on", [])
        unmet = [dep for dep in proposal["depends_on"] if dep in signature_index]
        proposal["status"] = (
            ScientificActionStatus.BLOCKED if unmet else ScientificActionStatus.READY
        )
        proposal["blocked_by"] = sorted(unmet)
    return proposals


def compute_actions(context: PortfolioContext) -> dict[str, Any]:
    """Whole-program action queue. Pure computation; nothing is persisted here."""
    from app.services.replacement.portfolio import candidate_decision_state

    proposals: list[dict[str, Any]] = []
    for view in context.candidates:
        state = candidate_decision_state(context, view)
        proposals.extend(
            next_actions_for_candidate(context, view, eligibility=state["eligibility"])
        )
    _wire_dependencies(proposals)
    proposals.sort(key=lambda p: (-float(p["priority"]), str(p["action_signature"])))
    return {
        "program_id": context.program.id,
        "actions": proposals,
        "methodology_version": NEXT_ACTION_METHODOLOGY,
        "priority_methodology_version": PRIORITY_METHODOLOGY,
        "determinism_note": (
            "Action selection and ordering are produced by declared lookup tables. No language "
            "model participates in choosing, ranking or filtering these actions."
        ),
        "authorization_note": (
            "Recommending an action never starts it. Simulations and experiments are executed only "
            "through their own authorized platform workflows."
        ),
    }


def persist_actions(
    db: Session, context: PortfolioContext, computed: dict[str, Any], *, created_by: str | None = None,
) -> dict[str, Any]:
    """Reconcile the computed queue with stored actions, superseding rather than deleting.

    An action a human already accepted, deferred or completed is left alone. An open action that the
    engine no longer recommends is superseded with a pointer to whatever replaced it, so the trail of
    "we used to think this mattered, then this measurement arrived" survives.
    """
    existing = (
        db.query(ScientificAction)
        .filter(ScientificAction.program_id == context.program.id,
                ScientificAction.organisation_id == context.organisation_id,
                ScientificAction.superseded_by_id.is_(None))
        .order_by(ScientificAction.id)
        .all()
    )
    by_signature = {row.action_signature: row for row in existing}
    computed_signatures = {str(a["action_signature"]) for a in computed["actions"]}

    created: list[ScientificAction] = []
    updated: list[ScientificAction] = []
    for proposal in computed["actions"]:
        signature = str(proposal["action_signature"])
        current = by_signature.get(signature)
        if current is not None:
            if current.status in OPEN_ACTION_STATUSES:
                # Refresh the mutable decision inputs; identity and history are preserved.
                current.priority = float(proposal["priority"])
                current.priority_factors = proposal["priority_factors"]
                current.decision_value_class = str(proposal["decision_value_class"])
                current.cost_class = str(proposal["cost_class"])
                current.reason_code = str(proposal["reason_code"])
                current.reason = str(proposal["reason"])
                current.depends_on = list(proposal.get("depends_on") or [])
                current.status = str(proposal["status"])
                updated.append(current)
            continue
        row = ScientificAction(
            organisation_id=context.organisation_id, program_id=context.program.id,
            candidate_id=proposal.get("candidate_id"), requirement_id=proposal.get("requirement_id"),
            action_type=str(proposal["action_type"]), action_signature=signature,
            status=str(proposal["status"]), priority=float(proposal["priority"]),
            priority_factors=proposal["priority_factors"],
            decision_value_class=str(proposal["decision_value_class"]),
            cost_class=str(proposal["cost_class"]),
            reason_code=str(proposal["reason_code"]), reason=str(proposal["reason"]),
            resolves_gap_kind=proposal.get("resolves_gap_kind"),
            what_it_could_resolve=proposal.get("what_it_could_resolve"),
            depends_on=list(proposal.get("depends_on") or []),
            methodology_version=NEXT_ACTION_METHODOLOGY,
        )
        db.add(row)
        created.append(row)
    db.flush()

    superseded: list[ScientificAction] = []
    for signature, row in by_signature.items():
        if signature in computed_signatures:
            continue
        if row.status not in OPEN_ACTION_STATUSES:
            continue
        # The action is no longer recommended because the evidence state moved on. It is retained
        # and marked, never deleted: deleting it would erase why the experiment was requested.
        row.status = ScientificActionStatus.SUPERSEDED
        replacement = next(
            (candidate for candidate in created
             if candidate.candidate_id == row.candidate_id
             and candidate.requirement_id == row.requirement_id),
            None,
        )
        if replacement is not None:
            row.superseded_by_id = replacement.id
            replacement.supersedes_id = row.id
        superseded.append(row)
    db.flush()

    return {
        "created": [row.id for row in created],
        "updated": [row.id for row in updated],
        "superseded": [row.id for row in superseded],
    }


def open_actions(db: Session, *, organisation_id: str, program_id: str) -> list[ScientificAction]:
    return (
        db.query(ScientificAction)
        .filter(ScientificAction.organisation_id == organisation_id,
                ScientificAction.program_id == program_id,
                ScientificAction.status.in_(sorted(OPEN_ACTION_STATUSES)))
        .order_by(ScientificAction.priority.desc(), ScientificAction.action_signature)
        .all()
    )


def action_out(row: ScientificAction) -> dict[str, Any]:
    return {
        "id": row.id, "program_id": row.program_id, "candidate_id": row.candidate_id,
        "requirement_id": row.requirement_id, "action_type": row.action_type,
        "action_signature": row.action_signature, "status": row.status,
        "priority": row.priority, "priority_factors": row.priority_factors or {},
        "decision_value_class": row.decision_value_class, "cost_class": row.cost_class,
        "reason_code": row.reason_code, "reason": row.reason,
        "resolves_gap_kind": row.resolves_gap_kind,
        "what_it_could_resolve": row.what_it_could_resolve,
        "depends_on": list(row.depends_on or []),
        "supersedes_id": row.supersedes_id, "superseded_by_id": row.superseded_by_id,
        "result_reference": row.result_reference or {},
        "methodology_version": row.methodology_version,
        "created_at": row.created_at, "started_at": row.started_at, "completed_at": row.completed_at,
    }


CRITICALITY_SORT = CRITICALITY_ORDER
