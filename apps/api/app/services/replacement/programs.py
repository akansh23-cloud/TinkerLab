"""Phase 10 — Replacement program lifecycle, timeline and domain events.

The program is the object the whole workflow hangs from: one application, one incumbent material
state, one candidate portfolio, one decision policy. It wraps an existing `ReplacementProject`
rather than replacing it, so every Phase 1–9.1 contract on that project keeps working.

Two behaviours are worth calling out.

**The program state is resolved, not set.** A frontend cannot put a program into
`DECISION_READY` by clicking a button; the resolver reads the evidence and says what state the
program is actually in. The only exceptions are PAUSED and ARCHIVED, which express human intent
rather than an evidence condition.

**Events are synchronous and in-process.** When a measurement is accepted, the program recomputes
the affected candidate and appends a timeline row. No broker is introduced: adding Kafka to make a
single-process recomputation "event driven" would add operational surface without adding correctness.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    OPERATOR_SET_PROGRAM_STATES,
    CandidateEligibility,
    ConvergenceState,
    ProgramEventKind,
    ProgramState,
)
from app.models.entities import (
    Application,
    ApplicationComponent,
    Candidate,
    MaterialRole,
    MaterialState,
    ProgramTimelineEvent,
    ReplacementProgram,
    ReplacementProject,
    ReplacementRecommendation,
)
from app.services.replacement.context import PortfolioContext
from app.services.replacement.policy import ensure_default_policy, resolve_policy

PROGRAM_STATE_METHODOLOGY = "program-state-v1"


class ProgramError(ValueError):
    """Raised when a program definition is internally inconsistent."""


# ---------------------------------------------------------------------------------------------
# Tenant-scoped lookups
# ---------------------------------------------------------------------------------------------
def scoped_program(db: Session, program_id: str, organisation_id: str) -> ReplacementProgram | None:
    """A program from another tenant is reported as absent, never as forbidden."""
    row = db.get(ReplacementProgram, program_id)
    if row is None or row.organisation_id != organisation_id:
        return None
    return row


def validate_program_references(
    db: Session, *, organisation_id: str, project_id: str, role_id: str | None,
    incumbent_material_id: str | None, incumbent_state_id: str | None,
) -> None:
    """Reject a program whose parts do not actually belong together.

    A valid foreign key is not the same as a coherent study: an incumbent state that describes a
    different material would silently make every requirement evaluation meaningless.
    """
    project = db.get(ReplacementProject, project_id)
    if project is None or project.organisation_id != organisation_id:
        raise ProgramError("PROJECT_NOT_FOUND: the project does not exist in this organisation")

    if role_id:
        role = db.get(MaterialRole, role_id)
        if role is None:
            raise ProgramError("ROLE_NOT_FOUND: the material role does not exist")
        component = db.get(ApplicationComponent, role.component_id)
        application = db.get(Application, component.application_id) if component else None
        if application is None or (
            application.organisation_id is not None
            and application.organisation_id != organisation_id
        ):
            raise ProgramError("ROLE_NOT_VISIBLE: the material role is not visible in this organisation")

    if incumbent_state_id:
        state = db.get(MaterialState, incumbent_state_id)
        if state is None or state.organisation_id != organisation_id:
            raise ProgramError("INCUMBENT_STATE_NOT_FOUND: the incumbent state is not visible here")
        if incumbent_material_id and state.material_id != incumbent_material_id:
            raise ProgramError(
                "INCUMBENT_STATE_MISMATCH: the incumbent state does not belong to the incumbent material"
            )


def create_program(
    db: Session, *, organisation_id: str, values: dict[str, Any], created_by: str | None = None,
    row_id: str | None = None,
) -> ReplacementProgram:
    validate_program_references(
        db, organisation_id=organisation_id, project_id=str(values["project_id"]),
        role_id=values.get("role_id"), incumbent_material_id=values.get("incumbent_material_id"),
        incumbent_state_id=values.get("incumbent_state_id"),
    )
    policy = (
        resolve_policy(db, organisation_id=organisation_id, policy_id=values.get("decision_policy_id"))
        if values.get("decision_policy_id")
        else ensure_default_policy(db, organisation_id=organisation_id)
    )
    fields: dict[str, Any] = {
        "organisation_id": organisation_id,
        "project_id": str(values["project_id"]),
        "key": str(values["key"]),
        "name": str(values["name"]),
        "description": values.get("description"),
        "application_id": values.get("application_id"),
        "application_component_id": values.get("application_component_id"),
        "role_id": values.get("role_id"),
        "application_name": values.get("application_name"),
        "application_domain": values.get("application_domain"),
        "application_context": values.get("application_context") or {},
        "incumbent_material_id": values.get("incumbent_material_id"),
        "incumbent_state_id": values.get("incumbent_state_id"),
        "decision_policy_id": policy.id,
        "decision_policy_version": policy.version,
        "status": ProgramState.DRAFT.value,
        "status_reason_codes": ["PROGRAM_CREATED"],
        "validation_strategy": values.get("validation_strategy") or {},
        "is_demonstration_data": bool(values.get("is_demonstration_data", False)),
        "created_by": created_by,
    }
    if row_id is not None:
        fields["id"] = row_id
    row = ReplacementProgram(**fields)
    db.add(row)
    db.flush()
    record_event(
        db, program=row, kind=ProgramEventKind.PROGRAM_CREATED,
        summary=f"Replacement program '{row.name}' created.",
        payload={"project_id": row.project_id, "role_id": row.role_id,
                 "decision_policy_version": policy.version},
        actor_user_id=created_by,
    )
    return row


# ---------------------------------------------------------------------------------------------
# Deterministic program state resolution
# ---------------------------------------------------------------------------------------------
def resolve_program_state(db: Session, program: ReplacementProgram) -> dict[str, Any]:
    """Derive the program's lifecycle state from its own evidence.

    Evaluated as an ordered ladder so the reported state is the earliest genuine stage the program
    has actually reached, rather than the most advanced stage it could arguably claim.
    """
    if program.status_override and str(program.status_override) in OPERATOR_SET_PROGRAM_STATES:
        return {
            "status": str(program.status_override),
            "reason_codes": ["OPERATOR_SET_STATE"],
            "reason": "The program state was set deliberately by an operator.",
            "methodology_version": PROGRAM_STATE_METHODOLOGY,
        }

    context = PortfolioContext(db, program)
    requirement_count = len(context.requirements)
    candidate_count = (
        db.query(Candidate).filter(Candidate.project_id == program.project_id).count()
    )

    if program.role_id is None or requirement_count == 0:
        return {
            "status": ProgramState.DRAFT.value if program.role_id is None
            else ProgramState.REQUIREMENTS_DEFINED.value,
            "reason_codes": ["NO_ROLE_SELECTED"] if program.role_id is None else ["NO_REQUIREMENTS"],
            "reason": (
                "No material role is attached, so the program has nothing to evaluate against."
                if program.role_id is None
                else "The role has no functional requirements yet."
            ),
            "methodology_version": PROGRAM_STATE_METHODOLOGY,
        }

    if candidate_count == 0:
        return {
            "status": ProgramState.REQUIREMENTS_DEFINED.value,
            "reason_codes": ["NO_CANDIDATES"],
            "reason": "Requirements are defined but the candidate portfolio is empty.",
            "methodology_version": PROGRAM_STATE_METHODOLOGY,
        }

    latest_recommendation = (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == program.id,
                ReplacementRecommendation.organisation_id == program.organisation_id,
                ReplacementRecommendation.superseded_by_id.is_(None))
        .order_by(ReplacementRecommendation.version.desc())
        .first()
    )

    from app.services.replacement.convergence import assess_convergence

    convergence = assess_convergence(context)
    convergence_state = str(convergence["convergence_state"])
    metrics = convergence["metrics"]

    if convergence_state == ConvergenceState.NO_VIABLE_CANDIDATE:
        status, codes, reason = (
            ProgramState.NO_SUITABLE_CANDIDATE.value, ["ALL_CANDIDATES_BLOCKED"],
            "Every candidate in the portfolio has a definitive blocking failure.",
        )
    elif latest_recommendation is not None and latest_recommendation.status in {
        "advance_candidate", "advance_multiple_candidates"
    }:
        status, codes, reason = (
            ProgramState.RECOMMENDED.value, ["RECOMMENDATION_ISSUED"],
            "A current recommendation advances at least one candidate.",
        )
    elif convergence_state == ConvergenceState.DECISION_READY:
        status, codes, reason = (
            ProgramState.DECISION_READY.value, ["GATES_SATISFIED"],
            "At least one candidate satisfies every configured gate.",
        )
    elif convergence_state in {ConvergenceState.NEAR_DECISION, ConvergenceState.CONFLICT_RESOLUTION}:
        status, codes, reason = (
            ProgramState.CONVERGING.value, [convergence["reason_codes"][0]] if convergence["reason_codes"] else [],
            convergence["reasons"][0] if convergence["reasons"] else "The program is converging.",
        )
    elif metrics["experimental_requirements_validated"] > 0 or (
        convergence_state == ConvergenceState.VALIDATION_REQUIRED
    ):
        status, codes, reason = (
            ProgramState.EXPERIMENTING.value, ["PHYSICAL_VALIDATION_IN_SCOPE"],
            "Physical validation is under way or required by the decision policy.",
        )
    elif metrics["requirements_with_governing_evidence"] > 0:
        status, codes, reason = (
            ProgramState.VALIDATING.value, ["COMPUTATIONAL_EVIDENCE_PRESENT"],
            "Candidates carry governing computational evidence and are being evaluated.",
        )
    elif metrics["eligible_candidate_count"] or metrics["unresolved_candidate_count"]:
        status, codes, reason = (
            ProgramState.SCREENING.value, ["SCREENING_IN_PROGRESS"],
            "Candidates exist and are being screened against the requirement set.",
        )
    else:
        status, codes, reason = (
            ProgramState.CANDIDATES_GENERATED.value, ["CANDIDATES_PRESENT"],
            "Candidates exist but no evidence has been evaluated yet.",
        )

    return {
        "status": status,
        "reason_codes": sorted(set(codes)),
        "reason": reason,
        "convergence_state": convergence_state,
        "methodology_version": PROGRAM_STATE_METHODOLOGY,
    }


def refresh_program_state(db: Session, program: ReplacementProgram) -> dict[str, Any]:
    """Resolve and store the program state, emitting nothing when it has not changed."""
    resolved = resolve_program_state(db, program)
    if program.status != resolved["status"]:
        program.status = resolved["status"]
        program.status_reason_codes = list(resolved["reason_codes"])
        db.flush()
    else:
        program.status_reason_codes = list(resolved["reason_codes"])
    return resolved


def set_program_override(
    db: Session, program: ReplacementProgram, *, override: str | None, actor_user_id: str | None = None
) -> ReplacementProgram:
    if override is not None and str(override) not in OPERATOR_SET_PROGRAM_STATES:
        raise ProgramError(
            "INVALID_OVERRIDE: only PAUSED and ARCHIVED may be set directly; every other program "
            "state is resolved from evidence"
        )
    program.status_override = override
    refresh_program_state(db, program)
    db.flush()
    return program


# ---------------------------------------------------------------------------------------------
# Timeline and events
# ---------------------------------------------------------------------------------------------
def record_event(
    db: Session, *, program: ReplacementProgram, kind: str, summary: str,
    payload: dict[str, Any] | None = None, candidate_id: str | None = None,
    requirement_id: str | None = None, reference_kind: str | None = None,
    reference_id: str | None = None, actor_user_id: str | None = None,
) -> ProgramTimelineEvent:
    """Append one immutable timeline row. Timeline rows are written once and never updated."""
    row = ProgramTimelineEvent(
        organisation_id=program.organisation_id, program_id=program.id,
        candidate_id=candidate_id, requirement_id=requirement_id,
        event_kind=str(kind), summary=summary, payload=payload or {},
        reference_kind=reference_kind, reference_id=reference_id, actor_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def timeline(
    db: Session, *, organisation_id: str, program_id: str, candidate_id: str | None = None,
    limit: int = 200,
) -> list[ProgramTimelineEvent]:
    query = (
        db.query(ProgramTimelineEvent)
        .filter(ProgramTimelineEvent.organisation_id == organisation_id,
                ProgramTimelineEvent.program_id == program_id)
    )
    if candidate_id:
        query = query.filter(ProgramTimelineEvent.candidate_id == candidate_id)
    return (
        query.order_by(ProgramTimelineEvent.occurred_at.desc(), ProgramTimelineEvent.id)
        .limit(min(int(limit), 500))
        .all()
    )


def emit_evidence_event(
    db: Session, *, program: ReplacementProgram, kind: str, summary: str,
    candidate_ids: list[str] | None = None, payload: dict[str, Any] | None = None,
    reference_kind: str | None = None, reference_id: str | None = None,
    actor_user_id: str | None = None, recompute: bool = True,
) -> dict[str, Any]:
    """Handle a domain event: record it, then recompute only what it can have affected.

    Dependency-aware invalidation is the point here. A measurement on one candidate cannot change
    another candidate's requirement outcomes, so only the affected candidates are re-evaluated. The
    convergence assessment is program-wide and is always recomputed, because a single candidate
    advancing or being blocked changes the program's position.
    """
    affected = sorted(set(candidate_ids or []))
    for candidate_id in affected or [None]:
        record_event(
            db, program=program, kind=kind, summary=summary, payload=payload,
            candidate_id=candidate_id, reference_kind=reference_kind, reference_id=reference_id,
            actor_user_id=actor_user_id,
        )
    if not recompute:
        return {"recomputed": False, "affected_candidate_ids": affected}

    from app.services.replacement.actions import compute_actions, persist_actions
    from app.services.replacement.convergence import assess_convergence, persist_convergence

    # A scoped context when the event names its candidates, a full one when it does not.
    scoped = PortfolioContext(db, program, candidate_ids=affected or None)
    actions = compute_actions(scoped)
    action_changes = persist_actions(db, scoped, actions)

    full = PortfolioContext(db, program)
    convergence_payload = assess_convergence(full)
    convergence_row = persist_convergence(db, full, convergence_payload)
    record_event(
        db, program=program, kind=ProgramEventKind.CONVERGENCE_ASSESSED,
        summary=f"Convergence reassessed as {convergence_payload['convergence_state']}.",
        payload={"convergence_state": convergence_payload["convergence_state"],
                 "reason_codes": convergence_payload["reason_codes"]},
        reference_kind="convergence_assessment", reference_id=convergence_row.id,
    )
    refresh_program_state(db, program)
    return {
        "recomputed": True,
        "affected_candidate_ids": affected,
        "action_changes": action_changes,
        "convergence_assessment_id": convergence_row.id,
        "convergence_state": convergence_payload["convergence_state"],
        "program_status": program.status,
    }


def program_header(db: Session, program: ReplacementProgram) -> dict[str, Any]:
    """The mission-control header. Every figure is a count or a resolved state; none is invented."""
    from app.services.replacement.convergence import latest_convergence
    from app.services.replacement.portfolio import candidate_decision_state

    context = PortfolioContext(db, program)
    convergence_row = latest_convergence(
        db, organisation_id=program.organisation_id, program_id=program.id
    )
    material = context.incumbent_material()
    state = context.incumbent_state()

    active = 0
    blocked = 0
    blocking_gaps = 0
    if program.role_id:
        from app.services.replacement.gaps import gaps_for_candidate

        for view in context.candidates:
            decision_state = candidate_decision_state(context, view)
            if decision_state["eligibility"] == CandidateEligibility.BLOCKED:
                blocked += 1
            else:
                active += 1
            blocking_gaps += sum(
                1 for gap in gaps_for_candidate(context, view)
                if str(gap["gap_class"]) == "blocking_gap"
            )

    last_event = (
        db.query(ProgramTimelineEvent)
        .filter(ProgramTimelineEvent.program_id == program.id)
        .order_by(ProgramTimelineEvent.occurred_at.desc(), ProgramTimelineEvent.id)
        .first()
    )

    return {
        "program_id": program.id,
        "name": program.name,
        "key": program.key,
        "project_id": program.project_id,
        "application_name": program.application_name,
        "application_domain": program.application_domain,
        "role_id": program.role_id,
        "incumbent_material": {
            "id": material.id if material else None,
            "display_name": material.display_name if material else None,
        },
        "incumbent_state": {
            "id": state.id if state else None,
            "label": state.label if state else None,
        },
        "program_state": program.status,
        "program_state_reason_codes": list(program.status_reason_codes or []),
        "convergence_state": convergence_row.convergence_state if convergence_row else None,
        "convergence_progress_percent": (
            convergence_row.presentation_progress_percent if convergence_row else None
        ),
        "active_candidates": active,
        "blocked_candidates": blocked,
        "blocking_gaps": blocking_gaps,
        "decision_policy_version": program.decision_policy_version,
        "is_demonstration_data": program.is_demonstration_data,
        "last_evidence_update": last_event.occurred_at if last_event else None,
        "last_event_kind": last_event.event_kind if last_event else None,
    }
