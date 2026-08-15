"""Phase 10 — Decision policy.

What "ready to advance" means is configuration, not code. A power-semiconductor qualification gate
and a food-contact packaging gate are genuinely different gates, so hardcoding one universal policy
would make TinkerLab wrong for every industry except the one it was tuned on.

Every conclusion in Phase 10 records the policy version that produced it. A historical conclusion is
never recomputed under a newer policy — that would silently rewrite a decision a human already
reviewed. Changing the policy creates a new assessment instead.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    GATING_CRITICALITIES,
    MatrixCellStatus,
    RequirementApprovalStatus,
    RequirementCriticality,
    RequirementStatus,
)
from app.models.entities import (
    CRITICALITY_FROM_REQUIREMENT_KIND,
    DecisionPolicy,
    FunctionalRequirement,
)

DECISION_POLICY_METHODOLOGY = "decision-policy-v1"
DEFAULT_POLICY_KEY = "tinkerlab_default"
DEFAULT_POLICY_VERSION = "1.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Requirement criticality
# ---------------------------------------------------------------------------------------------
# `requirement_kind` remains the authoritative input to the Phase-8/9.1 evaluators. Criticality is
# the Phase-10 gate classification layered on top of it. Legacy rows are backfilled from this exact
# mapping in migration 0012, so introducing criticality changes no pre-Phase-10 outcome.
# Single source of truth, shared with the ORM column default and migration 0012's backfill so that
# a requirement classifies identically however it entered the database.
CRITICALITY_FROM_KIND: dict[str, str] = dict(CRITICALITY_FROM_REQUIREMENT_KIND)

CRITICALITY_ORDER: dict[str, int] = {
    RequirementCriticality.BLOCKING: 0,
    RequirementCriticality.CRITICAL: 1,
    RequirementCriticality.IMPORTANT: 2,
    RequirementCriticality.DESIRABLE: 3,
    RequirementCriticality.INFORMATIONAL: 4,
}


def resolve_criticality(requirement: FunctionalRequirement) -> str:
    """The requirement's declared criticality, falling back to the kind-derived default.

    The fallback exists so a requirement row written before Phase 10 (or by an older client that
    does not send the field) still classifies deterministically instead of raising or defaulting to
    the most permissive value.
    """
    declared = getattr(requirement, "criticality", None)
    if declared and declared in CRITICALITY_ORDER:
        return str(declared)
    return CRITICALITY_FROM_KIND.get(requirement.requirement_kind, RequirementCriticality.IMPORTANT)


def is_authoritative(requirement: FunctionalRequirement) -> bool:
    """A PROPOSED requirement is tracked but never gates a decision until a human accepts it.

    Automated logic (including any LLM drafting assistance) may propose requirements. Treating a
    proposal as user-approved would let the system invent the bar it is then judged against.
    """
    status = getattr(requirement, "approval_status", None) or RequirementApprovalStatus.ACCEPTED
    return str(status) == RequirementApprovalStatus.ACCEPTED


def is_gating(requirement: FunctionalRequirement) -> bool:
    return is_authoritative(requirement) and resolve_criticality(requirement) in GATING_CRITICALITIES


# ---------------------------------------------------------------------------------------------
# Requirement status → decision-matrix cell status
# ---------------------------------------------------------------------------------------------
# A pure re-labelling of the canonical Phase-8 statuses into the matrix vocabulary. No status is
# upgraded: CONFLICTING_EVIDENCE never becomes PASS, and STATE_MISMATCH never becomes FAIL — a
# property measured in an incompatible state says nothing about this state, in either direction.
CELL_STATUS_FROM_REQUIREMENT_STATUS: dict[str, str] = {
    RequirementStatus.PASS: MatrixCellStatus.PASS,
    RequirementStatus.FAIL: MatrixCellStatus.FAIL,
    RequirementStatus.PARTIAL: MatrixCellStatus.INCONCLUSIVE,
    RequirementStatus.UNKNOWN: MatrixCellStatus.UNKNOWN,
    RequirementStatus.INSUFFICIENT_EVIDENCE: MatrixCellStatus.INCONCLUSIVE,
    RequirementStatus.CONFLICTING_EVIDENCE: MatrixCellStatus.CONFLICTING,
    RequirementStatus.STATE_MISMATCH: MatrixCellStatus.NOT_COMPARABLE,
}

# Statuses that are definitive enough to reject a candidate on. Deliberately only FAIL: UNKNOWN,
# INCONCLUSIVE, NOT_COMPARABLE and CONFLICTING mean "more work", not "no".
DEFINITIVE_NEGATIVE_STATUSES: frozenset[str] = frozenset({MatrixCellStatus.FAIL})
# Statuses that leave a gating requirement unresolved rather than decided.
UNRESOLVED_CELL_STATUSES: frozenset[str] = frozenset({
    MatrixCellStatus.UNKNOWN, MatrixCellStatus.INCONCLUSIVE,
    MatrixCellStatus.NOT_COMPARABLE, MatrixCellStatus.CONFLICTING,
})


def cell_status_for(requirement_status: str) -> str:
    return CELL_STATUS_FROM_REQUIREMENT_STATUS.get(str(requirement_status), MatrixCellStatus.UNKNOWN)


# ---------------------------------------------------------------------------------------------
# Default policy
# ---------------------------------------------------------------------------------------------
# Which evidence classes a requirement of each criticality is expected to have before its evidence
# is considered complete. "any_computational" is satisfied by an observation, a prediction or a
# simulation; they are separate origins but any one of them establishes a computational/reference
# value exists. This drives coverage (how much evidence exists), never success (whether it passes).
DEFAULT_EXPECTED_EVIDENCE: dict[str, list[str]] = {
    RequirementCriticality.BLOCKING: ["any_computational", "experimental"],
    RequirementCriticality.CRITICAL: ["any_computational", "experimental"],
    RequirementCriticality.IMPORTANT: ["any_computational"],
    RequirementCriticality.DESIRABLE: ["any_computational"],
    RequirementCriticality.INFORMATIONAL: [],
}

DEFAULT_REQUIRED_GATES: list[str] = [
    "NO_DEFINITIVE_BLOCKING_FAILURE",
    "ALL_BLOCKING_REQUIREMENTS_RESOLVED",
    "CRITICAL_EVIDENCE_COVERAGE_MET",
    "NO_UNRESOLVED_CRITICAL_CONFLICT",
    "INDUSTRIAL_BLOCKERS_RESOLVED",
    "REQUIRED_EXPERIMENTS_COMPLETE",
]

DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "performance_margin": 0.25,
    "industrial_viability": 0.20,
    "cost": 0.15,
    "supply_security": 0.10,
    "manufacturing_fit": 0.10,
    "sustainability": 0.05,
    "evidence_confidence": 0.15,
}

# One-at-a-time deterministic weight sweep. Not a probability distribution over weights — a bounded
# scenario set, so the combinatorial expansion stays at (objectives x multipliers).
DEFAULT_SENSITIVITY_BOUNDS: dict[str, Any] = {
    "multipliers": [0.5, 0.75, 1.25, 2.0],
    "max_scenarios": 64,
    "near_equivalent_margin": 0.02,
}

DEFAULT_MINIMUM_EVIDENCE: dict[str, Any] = {
    "expected_evidence_by_criticality": DEFAULT_EXPECTED_EVIDENCE,
    "minimum_blocking_coverage": 1.0,
    "minimum_critical_coverage": 1.0,
}

DEFAULT_REQUIRED_EXPERIMENTAL_VALIDATION: dict[str, Any] = {
    "criticalities_requiring_experiment": [
        RequirementCriticality.BLOCKING.value, RequirementCriticality.CRITICAL.value,
    ],
    "minimum_replicates": 2,
}

DEFAULT_INDUSTRIAL_GATE: dict[str, Any] = {
    "blocking_overall_states": ["fail", "conflicting_evidence"],
    "require_assessment": True,
    "required_resolved_dimensions": ["manufacturing_compatibility", "regulatory_compatibility"],
    "resolved_dimension_states": ["pass", "partial"],
    # Two dimensions are deliberately excluded from this gate.
    #
    # `experimental_validation` is computed by the Phase-7 engine, which by design cannot see
    # Phase-9 measurements — it is structurally UNKNOWN there and reports so honestly. Requiring it
    # to be resolved here would make the gate permanently unreachable while Phase 10 already tests
    # physical validation directly and far more precisely in REQUIRED_EXPERIMENTS_COMPLETE.
    #
    # `scientific_suitability` reports a coarse Phase-5 feasibility class. Phase 10 evaluates
    # scientific suitability requirement-by-requirement in the decision matrix, so re-testing the
    # coarse version here would double-count it and block candidates that were never screened
    # through a virtual campaign.
    "excluded_dimensions": ["experimental_validation", "scientific_suitability"],
}


def default_policy_payload() -> dict[str, Any]:
    return {
        "key": DEFAULT_POLICY_KEY,
        "display_name": "TinkerLab default replacement decision policy",
        "version": DEFAULT_POLICY_VERSION,
        "description": (
            "Conservative default gates. Blocking and critical requirements must be resolved with "
            "admissible evidence, industrial hard failures block advancement, and unresolved "
            "statuses never advance a candidate by default."
        ),
        "required_gates": list(DEFAULT_REQUIRED_GATES),
        "minimum_evidence_requirements": json.loads(canonical_json(DEFAULT_MINIMUM_EVIDENCE)),
        "required_experimental_validation": json.loads(canonical_json(DEFAULT_REQUIRED_EXPERIMENTAL_VALIDATION)),
        "industrial_gate_requirements": json.loads(canonical_json(DEFAULT_INDUSTRIAL_GATE)),
        # Nothing unresolved is tolerated by default: an operator must widen this deliberately.
        "allowed_unresolved_statuses": [],
        "ranking_weights": dict(DEFAULT_RANKING_WEIGHTS),
        "sensitivity_bounds": json.loads(canonical_json(DEFAULT_SENSITIVITY_BOUNDS)),
        "auto_reject_on_experimental_contradiction": True,
    }


def policy_checksum(payload: dict[str, Any]) -> str:
    return checksum({
        "methodology": DECISION_POLICY_METHODOLOGY,
        "key": payload.get("key"),
        "version": payload.get("version"),
        "required_gates": sorted(payload.get("required_gates") or []),
        "minimum_evidence_requirements": payload.get("minimum_evidence_requirements") or {},
        "required_experimental_validation": payload.get("required_experimental_validation") or {},
        "industrial_gate_requirements": payload.get("industrial_gate_requirements") or {},
        "allowed_unresolved_statuses": sorted(payload.get("allowed_unresolved_statuses") or []),
        "ranking_weights": payload.get("ranking_weights") or {},
        "sensitivity_bounds": payload.get("sensitivity_bounds") or {},
        "auto_reject_on_experimental_contradiction": bool(
            payload.get("auto_reject_on_experimental_contradiction", True)
        ),
    })


def create_policy(
    db: Session, *, organisation_id: str, values: dict[str, Any] | None = None,
    created_by: str | None = None, row_id: str | None = None,
) -> DecisionPolicy:
    payload = default_policy_payload()
    payload.update({k: v for k, v in (values or {}).items() if v is not None})
    fields: dict[str, Any] = {
        "organisation_id": organisation_id, "key": str(payload["key"]),
        "display_name": str(payload["display_name"]), "version": str(payload["version"]),
        "description": payload.get("description"),
        "required_gates": list(payload["required_gates"]),
        "minimum_evidence_requirements": payload["minimum_evidence_requirements"],
        "required_experimental_validation": payload["required_experimental_validation"],
        "industrial_gate_requirements": payload["industrial_gate_requirements"],
        "allowed_unresolved_statuses": list(payload["allowed_unresolved_statuses"]),
        "ranking_weights": payload["ranking_weights"],
        "sensitivity_bounds": payload["sensitivity_bounds"],
        "auto_reject_on_experimental_contradiction": bool(payload["auto_reject_on_experimental_contradiction"]),
        "is_active": True, "policy_checksum": policy_checksum(payload), "created_by": created_by,
    }
    if row_id is not None:
        fields["id"] = row_id
    row = DecisionPolicy(**fields)
    db.add(row)
    db.flush()
    return row


def ensure_default_policy(db: Session, *, organisation_id: str) -> DecisionPolicy:
    """Return the organisation's active default policy, creating it on first use."""
    existing = (
        db.query(DecisionPolicy)
        .filter(DecisionPolicy.organisation_id == organisation_id,
                DecisionPolicy.key == DEFAULT_POLICY_KEY,
                DecisionPolicy.is_active.is_(True))
        .order_by(DecisionPolicy.version.desc(), DecisionPolicy.id)
        .first()
    )
    if existing is not None:
        return existing
    return create_policy(db, organisation_id=organisation_id)


def resolve_policy(db: Session, *, organisation_id: str, policy_id: str | None) -> DecisionPolicy:
    if policy_id:
        row = db.get(DecisionPolicy, policy_id)
        # A policy from another tenant is treated as absent rather than as forbidden: existence of
        # another organisation's configuration is itself information.
        if row is not None and row.organisation_id == organisation_id:
            return row
    return ensure_default_policy(db, organisation_id=organisation_id)


def expected_evidence_for(policy: DecisionPolicy, criticality: str) -> list[str]:
    table = (policy.minimum_evidence_requirements or {}).get("expected_evidence_by_criticality") or {}
    value = table.get(str(criticality))
    if value is None:
        value = DEFAULT_EXPECTED_EVIDENCE.get(str(criticality), [])
    return [str(item) for item in value]


def policy_summary(policy: DecisionPolicy) -> dict[str, Any]:
    return {
        "decision_policy_id": policy.id, "key": policy.key, "version": policy.version,
        "display_name": policy.display_name,
        "required_gates": list(policy.required_gates or []),
        "minimum_evidence_requirements": policy.minimum_evidence_requirements or {},
        "required_experimental_validation": policy.required_experimental_validation or {},
        "industrial_gate_requirements": policy.industrial_gate_requirements or {},
        "allowed_unresolved_statuses": list(policy.allowed_unresolved_statuses or []),
        "ranking_weights": policy.ranking_weights or {},
        "sensitivity_bounds": policy.sensitivity_bounds or {},
        "auto_reject_on_experimental_contradiction": bool(policy.auto_reject_on_experimental_contradiction),
        "policy_checksum": policy.policy_checksum,
    }
