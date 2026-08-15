"""Phase 10 — Evidence coverage and the candidate decision matrix.

Two ideas are kept strictly apart here, because conflating them is the most dangerous error a
material-selection tool can make:

  * **Coverage** answers "how much of the evidence this requirement is supposed to have actually
    exists?". It is a completeness measure over evidence origins.
  * **Status** answers "does the evidence that exists say the requirement is met?". It comes
    entirely from the canonical Phase-8 evaluator.

A candidate with `coverage_score = 1.0` and `governing_status = FAIL` is fully evidenced and
definitively unsuitable. A candidate with `coverage_score = 0.0` is not "bad" — it is unmeasured.
Neither number is a probability of anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.enums import (
    EvidenceOriginClass,
    MatrixCellStatus,
    RequirementCriticality,
    StateMatchQuality,
)
from app.services.replacement.context import CandidateView, PortfolioContext
from app.services.replacement.policy import (
    CRITICALITY_ORDER,
    cell_status_for,
    expected_evidence_for,
    is_authoritative,
    resolve_criticality,
)

COVERAGE_METHODOLOGY = "evidence-coverage-v1"
MATRIX_METHODOLOGY = "decision-matrix-v1"

# How old industrial/economic evidence may be before it is flagged. Scientific property values are
# not aged: a correctly measured band gap does not expire, whereas a 2019 price does.
DEFAULT_FRESHNESS_HORIZON_DAYS = 730

COMPUTATIONAL_ORIGINS: frozenset[str] = frozenset({
    EvidenceOriginClass.OBSERVED, EvidenceOriginClass.LITERATURE,
    EvidenceOriginClass.PREDICTED, EvidenceOriginClass.SIMULATED,
})

COVERAGE_NOTE = (
    "Coverage measures how much of the expected evidence exists for a requirement. It is not a "
    "likelihood of success: a fully covered requirement can be a definitive failure."
)

MATRIX_NOTE = (
    "Each cell reports the status produced by the canonical requirement evaluator, with the "
    "evidence that governed it. Cells are never aggregated into a single number that could hide a "
    "hard failure."
)


def _origin_presence(result: dict[str, Any]) -> dict[str, bool]:
    """Which evidence origins contributed a value to this requirement evaluation."""
    counts = result.get("origin_counts") or {}
    present = {origin: int(count) > 0 for origin, count in counts.items()}
    return {
        "observed": bool(present.get(EvidenceOriginClass.OBSERVED)),
        "literature": bool(present.get(EvidenceOriginClass.LITERATURE)),
        "predicted": bool(present.get(EvidenceOriginClass.PREDICTED)),
        "simulated": bool(present.get(EvidenceOriginClass.SIMULATED)),
        "experimental": bool(present.get(EvidenceOriginClass.EXPERIMENTAL)),
    }


def _state_compatible(result: dict[str, Any]) -> bool | None:
    """Whether the governing value's state matches the state being asked about.

    Returns None when there is no governing value at all — "no evidence" is not "incompatible".
    """
    match = result.get("governing_state_match")
    if match is None:
        return None
    return str(match) in {
        StateMatchQuality.EXACT, StateMatchQuality.COMPATIBLE,
        StateMatchQuality.CONDITIONALLY_COMPATIBLE,
    }


def _conditions_comparable(result: dict[str, Any]) -> bool | None:
    """Whether at least one value could actually be compared against the requirement's units.

    A unit-dimension mismatch is a comparability failure, not a scientific failure.
    """
    outcomes = result.get("outcomes")
    if not outcomes:
        return None
    incomparable = [o for o in outcomes if o.get("reason_code") == "UNIT_DIMENSION_MISMATCH"]
    comparable = [o for o in outcomes if o.get("normalized_interval") is not None]
    if comparable:
        return True
    return False if incomparable else None


def _industrial_freshness(context: PortfolioContext, view: CandidateView) -> dict[str, Any]:
    """Freshness of the industrial evidence behind a candidate, from its recorded as-of dates."""
    industrial = context.industrial_for(view)
    snapshot = industrial.get("evidence_snapshot") or {}
    rows = snapshot.get("evidence") or []
    horizon = datetime.now(UTC).date() - timedelta(days=DEFAULT_FRESHNESS_HORIZON_DAYS)
    stale: list[str] = []
    undated: list[str] = []
    for row in rows:
        as_of = row.get("as_of_date")
        if not as_of:
            undated.append(str(row.get("metric_key")))
            continue
        try:
            parsed = datetime.strptime(str(as_of), "%Y-%m-%d").date()
        except ValueError:
            undated.append(str(row.get("metric_key")))
            continue
        if parsed < horizon:
            stale.append(str(row.get("metric_key")))
    return {
        "horizon_days": DEFAULT_FRESHNESS_HORIZON_DAYS,
        "stale_metric_keys": sorted(set(stale)),
        "undated_metric_keys": sorted(set(undated)),
        "any_stale": bool(stale),
    }


def coverage_for_candidate(context: PortfolioContext, view: CandidateView) -> list[dict[str, Any]]:
    """Per-requirement evidence coverage for one candidate."""
    reasoning = context.reasoning_for(view)
    decision = context.decision_for(view)
    industrial = context.industrial_for(view)
    industrial_present = bool((industrial.get("evidence_snapshot") or {}).get("evidence"))
    freshness = _industrial_freshness(context, view)

    experimental_outcomes = {
        str(item.get("requirement_id")): item
        for item in (decision.get("scientific_requirements") or {}).get("requirement_outcomes", [])
    }
    requirements_by_id = context.requirements_by_id

    rows: list[dict[str, Any]] = []
    for result in reasoning["requirement_results"]:
        requirement_id = str(result["requirement_id"])
        requirement = requirements_by_id.get(requirement_id)
        criticality = resolve_criticality(requirement) if requirement else RequirementCriticality.IMPORTANT
        authoritative = is_authoritative(requirement) if requirement else True
        presence = _origin_presence(result)
        outcome = experimental_outcomes.get(requirement_id) or {}
        experimental_present = presence["experimental"] or bool(outcome.get("measurement_outcomes"))

        expected = expected_evidence_for(context.policy, criticality)
        satisfied: list[str] = []
        missing: list[str] = []
        for token in expected:
            if token == "any_computational":
                ok = presence["observed"] or presence["literature"] or presence["predicted"] or presence["simulated"]
            elif token == "experimental":
                ok = experimental_present
            elif token == "industrial":
                ok = industrial_present
            elif token in presence:
                ok = presence[token]
            else:
                # An unrecognised policy token is reported rather than silently treated as met.
                ok = False
            (satisfied if ok else missing).append(token)

        coverage_score = 1.0 if not expected else round(len(satisfied) / len(expected), 6)
        governing_status = cell_status_for(result["status"])
        gating = authoritative and criticality in {
            RequirementCriticality.BLOCKING, RequirementCriticality.CRITICAL
        }
        blocking_gap = bool(
            gating and (missing or governing_status in {
                MatrixCellStatus.UNKNOWN, MatrixCellStatus.INCONCLUSIVE,
                MatrixCellStatus.NOT_COMPARABLE, MatrixCellStatus.CONFLICTING,
            })
        )

        rows.append({
            "requirement_id": requirement_id,
            "requirement_key": result.get("requirement_key"),
            "display_name": result.get("display_name"),
            "property_key": result.get("property_key"),
            "candidate_id": view.candidate_id,
            "criticality": criticality,
            "requirement_kind": result.get("requirement_kind"),
            "approval_status": getattr(requirement, "approval_status", "accepted") if requirement else "accepted",
            "is_gating": gating,
            "observed": presence["observed"] or presence["literature"],
            "predicted": presence["predicted"],
            "simulated": presence["simulated"],
            "industrial": industrial_present,
            "experimental": experimental_present,
            "state_compatible": _state_compatible(result),
            "conditions_comparable": _conditions_comparable(result),
            "fresh_enough": (not freshness["any_stale"]) if industrial_present else None,
            "conflicting": governing_status == MatrixCellStatus.CONFLICTING,
            "governing_status": governing_status,
            "governing_origin": result.get("governing_origin"),
            "expected_evidence": expected,
            "satisfied_evidence": satisfied,
            "missing_evidence": missing,
            "coverage_score": coverage_score,
            "blocking_gap": blocking_gap,
            "coverage_note": COVERAGE_NOTE,
            "methodology_version": COVERAGE_METHODOLOGY,
        })
    return sorted(rows, key=lambda r: (CRITICALITY_ORDER.get(r["criticality"], 9), str(r["requirement_key"])))


def coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate coverage without ever collapsing it into a verdict."""
    gating = [r for r in rows if r["is_gating"]]
    scored = [float(r["coverage_score"]) for r in rows] or [0.0]
    return {
        "requirement_count": len(rows),
        "gating_requirement_count": len(gating),
        "mean_coverage_score": round(sum(scored) / len(scored), 6),
        "fully_covered_count": sum(1 for r in rows if float(r["coverage_score"]) >= 1.0),
        "blocking_gap_count": sum(1 for r in rows if r["blocking_gap"]),
        "experimental_covered_count": sum(1 for r in rows if r["experimental"]),
        "coverage_note": COVERAGE_NOTE,
        "methodology_version": COVERAGE_METHODOLOGY,
    }


def _cell(result: dict[str, Any], requirement: Any, coverage_row: dict[str, Any] | None) -> dict[str, Any]:
    status = cell_status_for(result["status"])
    values = result.get("values") or []
    governing_source = result.get("governing_source_id")
    governing = next((v for v in values if v.get("source_id") == governing_source), None)
    other = [v for v in values if v.get("source_id") != governing_source]
    reason_codes: list[str] = []
    if status == MatrixCellStatus.CONFLICTING:
        reason_codes.append("ORIGINS_DISAGREE")
    if status == MatrixCellStatus.NOT_COMPARABLE:
        reason_codes.append("STATE_INCOMPATIBLE")
    if status == MatrixCellStatus.UNKNOWN and not values:
        reason_codes.append("NO_EVIDENCE_OF_ANY_ORIGIN")
    if status == MatrixCellStatus.INCONCLUSIVE:
        reason_codes.append("EVIDENCE_PRESENT_BUT_NOT_DECISIVE")
    if requirement is not None and resolve_criticality(requirement) in {
        RequirementCriticality.DESIRABLE, RequirementCriticality.INFORMATIONAL
    }:
        # Objectives are ranked, not passed. Saying INCONCLUSIVE without this code would read as a
        # deficiency when it is simply the correct answer for a non-gating objective.
        reason_codes.append("OBJECTIVE_RANKED_NOT_GATED")
    return {
        "requirement_id": result["requirement_id"],
        "status": status,
        "requirement_status": result["status"],
        "detail": result.get("detail"),
        "governing_origin": result.get("governing_origin"),
        "governing_evidence": governing,
        "supporting_evidence": other,
        "outcomes": result.get("outcomes") or [],
        "origin_counts": result.get("origin_counts") or {},
        "coverage_score": coverage_row["coverage_score"] if coverage_row else None,
        "is_gating": coverage_row["is_gating"] if coverage_row else False,
        "reason_codes": sorted(set(reason_codes)),
    }


def decision_matrix(context: PortfolioContext) -> dict[str, Any]:
    """Rows are requirements, columns are the incumbent and each candidate.

    The matrix is deliberately the primary artefact rather than a ranked list: a single score can
    hide a hard failure, a table of statuses cannot.
    """
    requirements = context.requirements
    coverage_by_candidate: dict[str, dict[str, dict[str, Any]]] = {}
    for view in context.candidates:
        coverage_by_candidate[view.candidate_id] = {
            row["requirement_id"]: row for row in coverage_for_candidate(context, view)
        }

    incumbent_reasoning = context.incumbent_reasoning()
    incumbent_results = {
        str(r["requirement_id"]): r for r in (incumbent_reasoning or {}).get("requirement_results", [])
    }

    candidate_results: dict[str, dict[str, dict[str, Any]]] = {}
    for view in context.candidates:
        reasoning = context.reasoning_for(view)
        candidate_results[view.candidate_id] = {
            str(r["requirement_id"]): r for r in reasoning["requirement_results"]
        }

    rows: list[dict[str, Any]] = []
    for requirement in requirements:
        criticality = resolve_criticality(requirement)
        incumbent_result = incumbent_results.get(requirement.id)
        row = {
            "requirement_id": requirement.id,
            "requirement_key": requirement.key,
            "display_name": requirement.display_name,
            "property_key": requirement.property_key,
            "requirement_kind": requirement.requirement_kind,
            "criticality": criticality,
            "requirement_origin": getattr(requirement, "requirement_origin", "user_defined"),
            "approval_status": getattr(requirement, "approval_status", "accepted"),
            "direction": requirement.direction,
            "target_value": requirement.target_value,
            "target_value_upper": requirement.target_value_upper,
            "target_unit": requirement.target_unit,
            "conditions": requirement.conditions or {},
            "function_key": None,
            "incumbent": _cell(incumbent_result, requirement, None) if incumbent_result else None,
            "cells": {},
        }
        for view in context.candidates:
            result = candidate_results[view.candidate_id].get(requirement.id)
            if result is None:
                continue
            row["cells"][view.candidate_id] = _cell(
                result, requirement, coverage_by_candidate[view.candidate_id].get(requirement.id)
            )
        rows.append(row)

    # Attach function grouping without a second query per requirement.
    function_of: dict[str, dict[str, Any]] = {}
    for function in context.functions:
        for requirement in function.requirements:
            function_of[requirement.id] = {
                "function_id": function.id, "function_key": function.key,
                "function_display_name": function.display_name, "function_category": function.category,
                "function_criticality": function.criticality,
            }
    for row in rows:
        row.update(function_of.get(str(row["requirement_id"]), {}))

    rows.sort(key=lambda r: (
        CRITICALITY_ORDER.get(str(r["criticality"]), 9),
        str(r.get("function_key") or ""), str(r["requirement_key"]),
    ))

    return {
        "program_id": context.program.id,
        "role_id": context.role.id if context.role else None,
        "incumbent": {
            "material_id": context.incumbent_material().id if context.incumbent_material() else None,
            "display_name": (
                context.incumbent_material().display_name if context.incumbent_material() else None
            ),
            "state_id": context.incumbent_state().id if context.incumbent_state() else None,
            "evaluated": incumbent_reasoning is not None,
        },
        "candidates": [
            {"candidate_id": v.candidate_id, "display_name": v.display_name,
             "candidate_kind": v.candidate_kind, "state_id": v.state_id}
            for v in context.candidates
        ],
        "rows": rows,
        "coverage": {
            view.candidate_id: coverage_summary(list(coverage_by_candidate[view.candidate_id].values()))
            for view in context.candidates
        },
        "methodology_version": MATRIX_METHODOLOGY,
        "coverage_methodology_version": COVERAGE_METHODOLOGY,
        "note": MATRIX_NOTE,
    }
