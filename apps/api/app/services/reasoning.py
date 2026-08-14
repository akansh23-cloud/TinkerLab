"""Phase-8 replacement reasoning engine.

The question this answers is not "is this material similar?" but "does this candidate preserve what
the incumbent actually does here?"

Decomposition: Application → Component → Material Role → Function → Requirement. A requirement binds
a property, a direction, a threshold and the conditions it must hold under. A candidate is evaluated
requirement by requirement against evidence **in a compatible state**.

Ordering rules that hold everywhere in this module:

  * The structured result is computed first and is authoritative. Natural-language rendering happens
    afterwards and cannot change a PASS, FAIL or UNKNOWN.
  * Evidence origins stay separate. An observation, a prediction, a simulation and an industrial
    record are reported distinctly and are never averaged into a single number.
  * Evidence recorded in an incompatible state produces STATE_MISMATCH, not a value.
  * A requirement with no usable evidence is UNKNOWN. It is not a soft pass and not a soft fail.
  * The engine is domain-generic: there is no branch anywhere on a specific material or application.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import (
    EvidenceOriginClass,
    ReasoningEdgeKind,
    ReasoningNodeKind,
    RequirementDirection,
    RequirementKind,
    RequirementStatus,
    StateMatchQuality,
)
from app.models.entities import (
    Application,
    ApplicationComponent,
    Evidence,
    ExperimentRun,
    FunctionalRequirement,
    MaterialFunction,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialRole,
    MaterialState,
    PredictionTarget,
    PropertyPrediction,
    ReasoningEdge,
    SimulationPropertyEstimate,
    SimulationResult,
    SimulationWorkflow,
)
from app.services.units import UnitError, convert
from app.services.material_states import (
    match_states,
    reference_state,
    states_for_target,
)

REASONING_POLICY_VERSION = "reasoning-v1"
MAX_GRAPH_DEPTH = 6
MAX_PAGE_SIZE = 200

ORIGIN_SEPARATION_NOTE = (
    "Observed, literature, predicted, simulated, experimental and industrial values are reported "
    "separately and are never averaged together. A prediction agreeing with a simulation is still "
    "not a measurement."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class ReasoningError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# Candidate values, tagged by origin and state
# ---------------------------------------------------------------------------------------------
@dataclass
class OriginValue:
    """One value offered for a requirement, carrying where it came from and which state it holds in."""

    origin: str
    value: float | None
    unit: str | None
    lower: float | None
    upper: float | None
    state_id: str | None
    state_match: str
    state_reasons: tuple[str, ...]
    source_id: str
    source_kind: str
    detail: str
    is_usable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin, "value": self.value, "unit": self.unit,
            "interval": [self.lower, self.upper] if self.lower is not None else None,
            "state_id": self.state_id, "state_match": self.state_match,
            "state_reasons": list(self.state_reasons), "source_id": self.source_id,
            "source_kind": self.source_kind, "detail": self.detail, "usable": self.is_usable,
        }


def _observation_values(
    db: Session, *, target_kind: str, target_id: str, property_definition_id: str,
    required_state: MaterialState | None, states_by_id: dict[str, MaterialState],
    organisation_id: str | None = None,
) -> list[OriginValue]:
    if target_kind != "known_material":
        return []
    rows = (
        db.query(MaterialPropertyObservation)
        .join(Evidence, Evidence.id == MaterialPropertyObservation.evidence_id)
        .filter(MaterialPropertyObservation.material_id == target_id,
                MaterialPropertyObservation.property_definition_id == property_definition_id,
                MaterialPropertyObservation.status == "active")
        .filter(
            or_(Evidence.visibility == "public", Evidence.organisation_id.is_(None), Evidence.organisation_id == organisation_id)
            if organisation_id is not None else Evidence.visibility == "public"
        )
        .order_by(MaterialPropertyObservation.created_at, MaterialPropertyObservation.id).all()
    )
    values: list[OriginValue] = []
    for row in rows:
        # Phase 1-2 observations predate the state model and carry no material state. Rather than
        # inventing one, they are reported as state-UNQUALIFIED: usable, but explicitly not shown to
        # hold in the required state, and that limitation is surfaced as an assumption.
        observed_state = states_by_id.get(str(getattr(row, "material_state_id", "") or ""))
        match = match_states(required_state, observed_state)
        origin = (
            EvidenceOriginClass.LITERATURE
            if (row.evidence is not None and row.evidence.evidence_type == "literature")
            else EvidenceOriginClass.OBSERVED
        )
        values.append(OriginValue(
            origin=origin, value=row.numeric_value, unit=row.unit,
            lower=row.uncertainty_lower, upper=row.uncertainty_upper,
            state_id=observed_state.id if observed_state else None,
            state_match=match.quality, state_reasons=match.reasons,
            source_id=row.id, source_kind="material_property_observation",
            detail=f"Recorded observation via {row.method or 'unstated method'}."
                   + ("" if observed_state else " No material state is attached to this observation."),
            # Only a demonstrated state DIFFERENCE disqualifies a value. An unqualified state is
            # reported, not silently discarded and not silently trusted as an exact match.
            is_usable=match.quality != StateMatchQuality.DIFFERENT_STATE,
        ))
    return values


def _prediction_values(
    db: Session, *, target_kind: str, target_id: str, property_definition_id: str,
    organisation_id: str | None = None,
) -> list[OriginValue]:
    query = (
        db.query(PropertyPrediction)
        .join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id)
        .filter(PropertyPrediction.property_definition_id == property_definition_id)
    )
    if organisation_id is not None:
        query = query.filter(PredictionTarget.organisation_id == organisation_id)
    query = query.filter(
        PredictionTarget.material_id == target_id if target_kind == "known_material"
        else PredictionTarget.hypothesis_id == target_id
    )
    values: list[OriginValue] = []
    for row in query.order_by(PropertyPrediction.created_at, PropertyPrediction.id).all():
        in_domain = row.applicability_status == "in_domain"
        values.append(OriginValue(
            origin=EvidenceOriginClass.PREDICTED, value=row.canonical_value, unit=row.canonical_unit,
            lower=row.uncertainty_lower, upper=row.uncertainty_upper,
            state_id=None, state_match=StateMatchQuality.UNKNOWN_STATE,
            state_reasons=("Model predictions are not bound to a material state.",),
            source_id=row.id, source_kind="property_prediction",
            detail=f"Model prediction; applicability status '{row.applicability_status}'."
                   + ("" if in_domain else " OUTSIDE the declared applicability domain."),
            # A model that declares the candidate outside its applicability domain is not evidence
            # about that candidate, however confident the number looks.
            is_usable=in_domain,
        ))
    return values


def _simulation_values(
    db: Session, *, target_id: str, property_definition_id: str, organisation_id: str | None = None,
) -> list[OriginValue]:
    rows = (
        db.query(SimulationPropertyEstimate, SimulationResult)
        .join(SimulationResult, SimulationResult.id == SimulationPropertyEstimate.simulation_result_id)
        .filter(SimulationResult.target_scientific_id == target_id,
                SimulationPropertyEstimate.property_definition_id == property_definition_id)
        .filter(SimulationResult.organisation_id == organisation_id if organisation_id is not None else True)
        .order_by(SimulationPropertyEstimate.id).all()
    )
    values: list[OriginValue] = []
    for estimate, result in rows:
        workflow = db.get(SimulationWorkflow, result.workflow_id)
        # Estimates only ever exist for converged results (Phase-6 invariant). This restates the
        # check rather than trusting it, because the consequence of being wrong is a fabricated pass.
        converged = result.scientific_status == "converged"
        values.append(OriginValue(
            origin=EvidenceOriginClass.SIMULATED, value=estimate.canonical_value,
            unit=estimate.canonical_unit, lower=None, upper=None, state_id=None,
            state_match=StateMatchQuality.UNKNOWN_STATE,
            state_reasons=("The simulated structure is recorded as a representation rather than a state.",),
            source_id=estimate.id, source_kind="simulation_property_estimate",
            detail=(f"Physics simulation via workflow template {workflow.workflow_template_key}."
                    if workflow else "Physics simulation.")
                   + (" Computational evidence, not a physical measurement." if converged
                      else " NOT CONVERGED — not usable."),
            is_usable=converged,
        ))
    return values


def _measurement_values(
    db: Session, *, target_kind: str, target_id: str, property_definition_id: str,
    required_state: MaterialState | None, states_by_id: dict[str, MaterialState],
    organisation_id: str | None = None,
) -> list[OriginValue]:
    """Physical measurements from Phase 9, entering reasoning as their own origin.

    This is the feedback edge that closes the loop: a new measurement changes what the reasoning
    engine concludes. It does not overwrite the prediction or the simulation — those remain listed
    alongside it, and a disagreement between them is surfaced rather than resolved silently.
    """
    from app.models.entities import Measurement, Sample

    query = (
        db.query(Measurement, Sample)
        .join(Sample, Sample.id == Measurement.sample_id)
        .join(ExperimentRun, ExperimentRun.id == Measurement.run_id)
        .filter(Measurement.property_definition_id == property_definition_id,
                Measurement.quality == "accepted",
                ExperimentRun.status == "completed")
    )
    if organisation_id is not None:
        query = query.filter(Measurement.organisation_id == organisation_id,
                             Sample.organisation_id == organisation_id,
                             ExperimentRun.organisation_id == organisation_id)
    query = query.filter(
        Sample.material_id == target_id if target_kind == "known_material"
        else Sample.hypothesis_id == target_id
    )
    values: list[OriginValue] = []
    for measurement, sample in query.order_by(Measurement.measured_at, Measurement.id).all():
        measured_state = states_by_id.get(str(sample.material_state_id or ""))
        match = match_states(required_state, measured_state)
        spread = measurement.uncertainty
        values.append(OriginValue(
            origin=EvidenceOriginClass.EXPERIMENTAL, value=measurement.canonical_value,
            unit=measurement.canonical_unit,
            lower=(measurement.canonical_value - spread) if (spread and measurement.canonical_value is not None) else None,
            upper=(measurement.canonical_value + spread) if (spread and measurement.canonical_value is not None) else None,
            state_id=measured_state.id if measured_state else None,
            state_match=match.quality, state_reasons=match.reasons,
            source_id=measurement.id, source_kind="measurement",
            detail=f"Physical measurement on sample {sample.sample_code} via "
                   f"{measurement.method or 'unstated method'}.",
            is_usable=match.usable if required_state is not None else True,
        ))
    return values


def collect_origin_values(
    db: Session, *, target_kind: str, target_id: str, property_definition_id: str,
    required_state: MaterialState | None, states_by_id: dict[str, MaterialState],
    organisation_id: str | None = None,
) -> list[OriginValue]:
    return (
        _observation_values(db, target_kind=target_kind, target_id=target_id,
                            property_definition_id=property_definition_id,
                            required_state=required_state, states_by_id=states_by_id, organisation_id=organisation_id)
        + _prediction_values(db, target_kind=target_kind, target_id=target_id,
                             property_definition_id=property_definition_id, organisation_id=organisation_id)
        + _simulation_values(db, target_id=target_id, property_definition_id=property_definition_id,
                             organisation_id=organisation_id)
        + _measurement_values(db, target_kind=target_kind, target_id=target_id,
                              property_definition_id=property_definition_id,
                              required_state=required_state, states_by_id=states_by_id,
                              organisation_id=organisation_id)
    )


# ---------------------------------------------------------------------------------------------
# Requirement evaluation
# ---------------------------------------------------------------------------------------------
# Which origin is preferred when several are usable. Preference decides which value is REPORTED as
# governing; it never merges values and never hides the others.
ORIGIN_PRIORITY: dict[str, int] = {
    EvidenceOriginClass.EXPERIMENTAL: 0,
    EvidenceOriginClass.OBSERVED: 1,
    EvidenceOriginClass.LITERATURE: 2,
    EvidenceOriginClass.SIMULATED: 3,
    EvidenceOriginClass.PREDICTED: 4,
    EvidenceOriginClass.INDUSTRIAL: 5,
    EvidenceOriginClass.UNKNOWN: 9,
}


def _interval_of(value: OriginValue) -> tuple[float, float] | None:
    if value.lower is not None and value.upper is not None:
        return float(value.lower), float(value.upper)
    if value.value is not None:
        return float(value.value), float(value.value)
    return None


def _test_direction(
    requirement: FunctionalRequirement, low: float, high: float
) -> tuple[str, str]:
    direction = requirement.direction
    target = requirement.target_value
    upper = requirement.target_value_upper
    unit = requirement.target_unit or ""

    if direction == RequirementDirection.MINIMUM:
        if target is None:
            return RequirementStatus.UNKNOWN, "The requirement declares no threshold."
        if low >= target:
            return RequirementStatus.PASS, f"Observed {low}–{high} {unit} meets the minimum of {target} {unit}.".strip()
        if high < target:
            return RequirementStatus.FAIL, f"Observed {low}–{high} {unit} is below the minimum of {target} {unit}.".strip()
        return RequirementStatus.PARTIAL, (
            f"Observed {low}–{high} {unit} straddles the minimum of {target} {unit}; the requirement "
            "is met only across part of the stated interval.").strip()
    if direction == RequirementDirection.MAXIMUM:
        if target is None:
            return RequirementStatus.UNKNOWN, "The requirement declares no threshold."
        if high <= target:
            return RequirementStatus.PASS, f"Observed {low}–{high} {unit} is within the maximum of {target} {unit}.".strip()
        if low > target:
            return RequirementStatus.FAIL, f"Observed {low}–{high} {unit} exceeds the maximum of {target} {unit}.".strip()
        return RequirementStatus.PARTIAL, (
            f"Observed {low}–{high} {unit} straddles the maximum of {target} {unit}.").strip()
    if direction == RequirementDirection.RANGE:
        if target is None or upper is None:
            return RequirementStatus.UNKNOWN, "The requirement declares an incomplete range."
        if low >= target and high <= upper:
            return RequirementStatus.PASS, f"Observed {low}–{high} {unit} lies inside {target}–{upper} {unit}.".strip()
        if high < target or low > upper:
            return RequirementStatus.FAIL, f"Observed {low}–{high} {unit} lies outside {target}–{upper} {unit}.".strip()
        return RequirementStatus.PARTIAL, f"Observed {low}–{high} {unit} partially overlaps {target}–{upper} {unit}.".strip()
    if direction == RequirementDirection.TARGET:
        if target is None:
            return RequirementStatus.UNKNOWN, "The requirement declares no target."
        tolerance = requirement.tolerance
        if tolerance is None:
            return RequirementStatus.UNKNOWN, (
                "A target requirement without a tolerance cannot be tested; an arbitrary tolerance "
                "is not invented.")
        if low >= target - tolerance and high <= target + tolerance:
            return RequirementStatus.PASS, f"Observed {low}–{high} {unit} is within ±{tolerance} of {target} {unit}.".strip()
        return RequirementStatus.FAIL, f"Observed {low}–{high} {unit} is outside ±{tolerance} of {target} {unit}.".strip()
    if direction in {RequirementDirection.MAXIMIZE, RequirementDirection.MINIMIZE}:
        # An objective has no pass/fail threshold. Reporting it as PASS would invent a bar.
        return RequirementStatus.PARTIAL, (
            f"Objective ({direction}): observed {low}–{high} {unit}. An objective is ranked, not "
            "passed or failed.").strip()
    return RequirementStatus.UNKNOWN, f"Direction '{direction}' has no numeric evaluator."


def evaluate_requirement(
    db: Session, *, requirement: FunctionalRequirement, target_kind: str, target_id: str,
    required_state: MaterialState | None, states_by_id: dict[str, MaterialState],
    organisation_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate one requirement. Every branch returns an explicit, explainable status."""
    base = {
        "requirement_id": requirement.id, "requirement_key": requirement.key,
        "display_name": requirement.display_name, "requirement_kind": requirement.requirement_kind,
        "direction": requirement.direction, "property_key": requirement.property_key,
        "target_value": requirement.target_value, "target_value_upper": requirement.target_value_upper,
        "target_unit": requirement.target_unit, "weight": requirement.weight,
        "conditions": requirement.conditions or {},
    }

    if requirement.property_definition_id is None:
        return {**base, "status": RequirementStatus.UNKNOWN, "values": [],
                "detail": "The requirement is not bound to a registered property definition, so no "
                          "evidence can be matched to it."}

    values = collect_origin_values(
        db, target_kind=target_kind, target_id=target_id,
        property_definition_id=requirement.property_definition_id,
        required_state=required_state, states_by_id=states_by_id, organisation_id=organisation_id,
    )
    serialized = [v.as_dict() for v in values]
    origin_counts: dict[str, int] = {}
    for value in values:
        origin_counts[value.origin] = origin_counts.get(value.origin, 0) + 1

    if not values:
        return {**base, "status": RequirementStatus.UNKNOWN, "values": [], "origin_counts": {},
                "detail": f"No value of any origin exists for '{requirement.property_key}'. "
                          "This is an evidence gap, not a failure and not a pass."}

    usable = [v for v in values if v.is_usable and _interval_of(v) is not None]
    if not usable:
        mismatched = [v for v in values if v.state_match == StateMatchQuality.DIFFERENT_STATE]
        if mismatched:
            return {**base, "status": RequirementStatus.STATE_MISMATCH, "values": serialized,
                    "origin_counts": origin_counts,
                    "detail": "Values exist but only for a different material state: "
                              + "; ".join(mismatched[0].state_reasons)
                              + " A property is not carried across an incompatible state."}
        return {**base, "status": RequirementStatus.INSUFFICIENT_EVIDENCE, "values": serialized,
                "origin_counts": origin_counts,
                "detail": "Values exist but none is usable for this requirement — they are "
                          "out-of-domain, unconverged, or carry no numeric interval."}

    # Evaluate every usable value independently, then look for disagreement between them.
    outcomes = []
    comparable_values: list[OriginValue] = []
    for value in usable:
        interval = _interval_of(value)
        assert interval is not None
        comparison_unit = requirement.target_unit or value.unit
        if comparison_unit and value.unit:
            try:
                if value.unit == comparison_unit:
                    low, high = interval
                else:
                    low = convert(interval[0], value.unit, comparison_unit)
                    high = convert(interval[1], value.unit, comparison_unit)
            except (UnitError, TypeError, ValueError) as exc:
                outcomes.append({
                    "origin": value.origin, "source_id": value.source_id,
                    "status": RequirementStatus.INSUFFICIENT_EVIDENCE,
                    "reason_code": "UNIT_DIMENSION_MISMATCH",
                    "detail": f"Evidence unit '{value.unit}' cannot be compared with requirement unit '{comparison_unit}': {exc}",
                    "raw_interval": [interval[0], interval[1]], "raw_unit": value.unit,
                    "normalized_interval": None, "comparison_unit": comparison_unit,
                })
                continue
        elif comparison_unit != value.unit:
            outcomes.append({
                "origin": value.origin, "source_id": value.source_id,
                "status": RequirementStatus.INSUFFICIENT_EVIDENCE,
                "reason_code": "UNIT_DIMENSION_MISMATCH",
                "detail": "A unit is missing, so this numeric value cannot be compared without guessing.",
                "raw_interval": [interval[0], interval[1]], "raw_unit": value.unit,
                "normalized_interval": None, "comparison_unit": comparison_unit,
            })
            continue
        else:
            low, high = interval
        status, detail = _test_direction(requirement, low, high)
        outcomes.append({"origin": value.origin, "source_id": value.source_id,
                         "status": status, "detail": detail, "unit": comparison_unit,
                         "raw_interval": [interval[0], interval[1]], "raw_unit": value.unit,
                         "normalized_interval": [low, high], "comparison_unit": comparison_unit})
        comparable_values.append(value)

    if not comparable_values:
        return {**base, "status": RequirementStatus.INSUFFICIENT_EVIDENCE, "values": serialized,
                "origin_counts": origin_counts, "outcomes": outcomes,
                "detail": "Values exist, but none has units compatible with this requirement."}

    distinct = {o["status"] for o in outcomes if o["source_id"] in {v.source_id for v in comparable_values}}
    verdicts = distinct & {RequirementStatus.PASS.value, RequirementStatus.FAIL.value}
    if len(verdicts) > 1:
        # A measurement saying pass and a simulation saying fail is a real scientific disagreement.
        # It is surfaced, not resolved by preferring whichever is convenient.
        return {**base, "status": RequirementStatus.CONFLICTING_EVIDENCE, "values": serialized,
                "origin_counts": origin_counts, "outcomes": outcomes,
                "detail": "Sources of different origin disagree on whether this requirement is met. "
                          "Both are retained and neither is averaged away.",
                "governing_origin": None}

    governing = min(comparable_values, key=lambda v: (ORIGIN_PRIORITY.get(v.origin, 9), v.source_id))
    governing_outcome = next(o for o in outcomes if o["source_id"] == governing.source_id)
    return {
        **base, "status": governing_outcome["status"], "values": serialized,
        "origin_counts": origin_counts, "outcomes": outcomes,
        "governing_origin": governing.origin, "governing_source_id": governing.source_id,
        "governing_state_match": governing.state_match,
        "detail": governing_outcome["detail"],
        "origin_note": f"Governing value is {governing.origin}; other origins are listed separately "
                       "and were not merged into it.",
    }


# ---------------------------------------------------------------------------------------------
# Reasoning graph
# ---------------------------------------------------------------------------------------------
@dataclass
class GraphPath:
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)


def mechanism_paths_for_property(
    db: Session, *, state_id: str | None, property_key: str, organisation_id: str | None
) -> list[dict[str, Any]]:
    """Walk state → feature → mechanism → property using only recorded edges.

    An empty result means no mechanism has been recorded, which is reported as such. The engine does
    not invent a plausible mechanism to fill the gap.
    """
    if not state_id:
        return []
    edges = (
        db.query(ReasoningEdge)
        .filter(ReasoningEdge.status == "active")
        .order_by(ReasoningEdge.edge_kind, ReasoningEdge.id).all()
    )
    visible = [
        e for e in edges
        if e.organisation_id is None or (organisation_id is not None and e.organisation_id == organisation_id)
    ]
    by_from: dict[tuple[str, str], list[ReasoningEdge]] = {}
    for edge in visible:
        by_from.setdefault((edge.from_kind, edge.from_id), []).append(edge)

    paths: list[dict[str, Any]] = []
    for feature_edge in by_from.get((ReasoningNodeKind.MATERIAL_STATE, state_id), []):
        if feature_edge.edge_kind != ReasoningEdgeKind.STATE_EXHIBITS_FEATURE:
            continue
        for mechanism_edge in by_from.get((ReasoningNodeKind.STRUCTURAL_FEATURE, feature_edge.to_id), []):
            if mechanism_edge.edge_kind != ReasoningEdgeKind.FEATURE_ENABLES_MECHANISM:
                continue
            for property_edge in by_from.get((ReasoningNodeKind.MECHANISM, mechanism_edge.to_id), []):
                if property_edge.edge_kind != ReasoningEdgeKind.MECHANISM_GOVERNS_PROPERTY:
                    continue
                if property_edge.to_id != property_key:
                    continue
                paths.append({
                    "property_key": property_key,
                    "chain": [
                        {"kind": ReasoningNodeKind.MATERIAL_STATE.value, "id": state_id},
                        {"kind": ReasoningNodeKind.STRUCTURAL_FEATURE.value, "id": feature_edge.to_id},
                        {"kind": ReasoningNodeKind.MECHANISM.value, "id": mechanism_edge.to_id},
                        {"kind": ReasoningNodeKind.PROPERTY.value, "id": property_key},
                    ],
                    "edges": [
                        _edge_summary(feature_edge), _edge_summary(mechanism_edge), _edge_summary(property_edge)
                    ],
                    # Confidence is the weakest link, not a product or an average: a chain is only as
                    # well supported as its least supported step.
                    "weakest_confidence": min(
                        [e.confidence for e in (feature_edge, mechanism_edge, property_edge)
                         if e.confidence is not None] or [0.0]
                    ) or None,
                })
    return paths


def _edge_summary(edge: ReasoningEdge) -> dict[str, Any]:
    return {
        "edge_id": edge.id, "edge_kind": edge.edge_kind, "scope": edge.scope,
        "confidence": edge.confidence, "source_type": edge.source_type,
        "source_reference": edge.source_reference, "evidence_id": edge.evidence_id,
        "conditions": edge.conditions or {}, "note": edge.relationship_note,
    }


def create_reasoning_edge(db: Session, values: dict[str, Any]) -> ReasoningEdge:
    """Create a graph edge. An edge with neither evidence nor a source reference is refused:
    an unsourced causal claim is exactly what this system must not accumulate."""
    if not values.get("evidence_id") and not values.get("source_reference"):
        raise ReasoningError(
            "A reasoning edge requires either linked evidence or an explicit source reference. "
            "Unsourced causal relationships are not stored."
        )
    edge = ReasoningEdge(**values)
    db.add(edge)
    db.flush()
    return edge


# ---------------------------------------------------------------------------------------------
# Candidate reasoning
# ---------------------------------------------------------------------------------------------
def role_decomposition(db: Session, role_id: str) -> dict[str, Any]:
    role = (
        db.query(MaterialRole)
        .options(selectinload(MaterialRole.functions).selectinload(MaterialFunction.requirements))
        .filter(MaterialRole.id == role_id).one_or_none()
    )
    if role is None:
        raise LookupError("Material role not found")
    component = db.get(ApplicationComponent, role.component_id)
    application = db.get(Application, component.application_id) if component else None
    return {
        "role": role, "component": component, "application": application,
        "functions": sorted(role.functions, key=lambda f: (-f.criticality, f.key)),
    }


def reason_about_candidate(
    db: Session, *, organisation_id: str, role_id: str, target_kind: str, target_id: str,
    project_id: str | None = None, candidate_id: str | None = None, state_id: str | None = None,
    generation_rationale: str | None = None, persist: bool = False,
) -> dict[str, Any]:
    """Produce the structured explanation for one candidate against one role.

    This is the function whose output an LLM may later narrate. The narration cannot change any
    status here, and nothing in this function calls a language model.
    """
    decomposition = role_decomposition(db, role_id)
    role: MaterialRole = decomposition["role"]
    functions: list[MaterialFunction] = decomposition["functions"]

    candidate_states = states_for_target(
        db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id
    )
    states_by_id = {s.id: s for s in candidate_states}
    chosen_state = (
        states_by_id.get(state_id) if state_id
        else reference_state(db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)
    )
    if state_id and chosen_state is None:
        raise LookupError("Material state not found for this candidate")

    incumbent_state = db.get(MaterialState, role.incumbent_state_id) if role.incumbent_state_id else None

    requirement_results: list[dict[str, Any]] = []
    function_coverage: dict[str, Any] = {}
    mechanism_paths: list[dict[str, Any]] = []
    origin_totals: dict[str, int] = {}

    for function in functions:
        function_statuses: list[str] = []
        for requirement in sorted(function.requirements, key=lambda r: r.key):
            result = evaluate_requirement(
                db, requirement=requirement, target_kind=target_kind, target_id=target_id,
                required_state=chosen_state, states_by_id=states_by_id, organisation_id=organisation_id,
            )
            result["function_id"] = function.id
            result["function_key"] = function.key
            result["function_display_name"] = function.display_name
            result["function_criticality"] = function.criticality
            requirement_results.append(result)
            function_statuses.append(result["status"])
            for origin, count in (result.get("origin_counts") or {}).items():
                origin_totals[origin] = origin_totals.get(origin, 0) + count
            if requirement.property_key:
                mechanism_paths.extend(mechanism_paths_for_property(
                    db, state_id=chosen_state.id if chosen_state else None,
                    property_key=requirement.property_key, organisation_id=organisation_id,
                ))
        function_coverage[function.key] = {
            "function_id": function.id, "display_name": function.display_name,
            "category": function.category, "criticality": function.criticality,
            "requirement_count": len(function.requirements),
            "status": _roll_up_function(function_statuses),
            "statuses": function_statuses,
        }

    satisfied = [r["requirement_id"] for r in requirement_results if r["status"] == RequirementStatus.PASS]
    failed = [
        r["requirement_id"] for r in requirement_results
        if r["status"] == RequirementStatus.FAIL
        and r["requirement_kind"] in {RequirementKind.HARD_CONSTRAINT, RequirementKind.SOFT_CONSTRAINT}
    ]
    unknown = [
        r["requirement_id"] for r in requirement_results
        if r["status"] in {RequirementStatus.UNKNOWN, RequirementStatus.INSUFFICIENT_EVIDENCE,
                           RequirementStatus.STATE_MISMATCH}
    ]
    evidence_gaps = [
        {
            "requirement_id": r["requirement_id"], "display_name": r["display_name"],
            "property_key": r["property_key"], "status": r["status"],
            "function_key": r["function_key"], "criticality": r["function_criticality"],
            "requirement_kind": r["requirement_kind"], "detail": r["detail"],
            "what_would_resolve_it": _resolution_hint(r),
        }
        for r in requirement_results
        if r["status"] in {RequirementStatus.UNKNOWN, RequirementStatus.INSUFFICIENT_EVIDENCE,
                           RequirementStatus.STATE_MISMATCH, RequirementStatus.CONFLICTING_EVIDENCE}
    ]

    hard_failures = [
        r for r in requirement_results
        if r["status"] == RequirementStatus.FAIL and r["requirement_kind"] == RequirementKind.HARD_CONSTRAINT
    ]
    if hard_failures:
        overall = RequirementStatus.FAIL
    elif any(r["status"] == RequirementStatus.CONFLICTING_EVIDENCE for r in requirement_results):
        overall = RequirementStatus.CONFLICTING_EVIDENCE
    elif unknown:
        overall = RequirementStatus.INSUFFICIENT_EVIDENCE
    elif satisfied:
        overall = RequirementStatus.PASS
    else:
        overall = RequirementStatus.UNKNOWN

    assumptions = _assumptions(chosen_state, incumbent_state, requirement_results)

    payload = {
        "role": {
            "id": role.id, "key": role.key, "display_name": role.display_name,
            "component": decomposition["component"].display_name if decomposition["component"] else None,
            "application": decomposition["application"].display_name if decomposition["application"] else None,
            "incumbent_material_id": role.incumbent_material_id,
            "incumbent_state_id": role.incumbent_state_id,
        },
        "target_kind": target_kind, "target_id": target_id,
        "state": {
            "id": chosen_state.id, "label": chosen_state.label,
            "structure_identity": chosen_state.structure_identity,
            "composition_signature": chosen_state.composition_signature,
        } if chosen_state else None,
        "state_warning": None if chosen_state else (
            "No material state is recorded for this candidate. Every property comparison is therefore "
            "state-unqualified, and no requirement can be established for a specific condition."
        ),
        "requirement_results": requirement_results,
        "function_coverage": function_coverage,
        "satisfied_requirements": satisfied,
        "failed_requirements": failed,
        "unknown_requirements": unknown,
        "evidence_gaps": evidence_gaps,
        "origin_breakdown": origin_totals,
        "mechanism_paths": mechanism_paths,
        "mechanism_note": (
            "No mechanism chain is recorded linking this state to the required properties."
            if not mechanism_paths else
            "Mechanism chains are recorded links, each with its own scope and source."
        ),
        "assumptions": assumptions,
        "generation_rationale": generation_rationale,
        "overall_status": overall,
        "policy_version": REASONING_POLICY_VERSION,
        "origin_separation_note": ORIGIN_SEPARATION_NOTE,
        "structured_first_note": (
            "This result is computed from stored structured data. Any natural-language explanation is "
            "generated afterwards and cannot change a PASS, FAIL or UNKNOWN recorded here."
        ),
    }
    payload["reasoning_checksum"] = checksum({
        "contract": REASONING_POLICY_VERSION,
        "role": role.id, "target": [target_kind, target_id],
        "state": chosen_state.state_checksum if chosen_state else None,
        "requirements": [
            {"id": r["requirement_id"], "status": r["status"],
             "governing_origin": r.get("governing_origin"),
             "governing_source_id": r.get("governing_source_id")}
            for r in requirement_results
        ],
        "overall": overall,
    })

    if persist:
        from app.models.entities import CandidateReasoningResult

        row = CandidateReasoningResult(
            organisation_id=organisation_id, project_id=project_id, role_id=role_id,
            candidate_id=candidate_id, target_kind=target_kind, target_scientific_id=target_id,
            state_id=chosen_state.id if chosen_state else None,
            requirement_results=requirement_results, function_coverage=function_coverage,
            satisfied_requirements=satisfied, failed_requirements=failed, unknown_requirements=unknown,
            evidence_gaps=evidence_gaps, origin_breakdown=origin_totals, assumptions=assumptions,
            mechanism_paths=mechanism_paths, overall_status=overall,
            generation_rationale=generation_rationale,
            reasoning_checksum=payload["reasoning_checksum"], policy_version=REASONING_POLICY_VERSION,
        )
        db.add(row)
        db.flush()
        previous = (
            db.query(CandidateReasoningResult)
            .filter(CandidateReasoningResult.role_id == role_id,
                    CandidateReasoningResult.target_scientific_id == target_id,
                    CandidateReasoningResult.superseded_by_id.is_(None),
                    CandidateReasoningResult.id != row.id).all()
        )
        for old in previous:
            old.superseded_by_id = row.id
        db.flush()
        payload["reasoning_result_id"] = row.id
    return payload


def _roll_up_function(statuses: list[str]) -> str:
    if not statuses:
        return RequirementStatus.UNKNOWN
    severity = {
        RequirementStatus.FAIL.value: 6, RequirementStatus.CONFLICTING_EVIDENCE.value: 5,
        RequirementStatus.STATE_MISMATCH.value: 4, RequirementStatus.INSUFFICIENT_EVIDENCE.value: 3,
        RequirementStatus.UNKNOWN.value: 2, RequirementStatus.PARTIAL.value: 1,
        RequirementStatus.PASS.value: 0,
    }
    return max(statuses, key=lambda s: severity.get(str(s), 2))


def _resolution_hint(result: dict[str, Any]) -> str:
    status = result["status"]
    property_key = result.get("property_key") or "the required property"
    if status == RequirementStatus.STATE_MISMATCH:
        return (f"A value for {property_key} measured or computed in the required state would resolve "
                "this. Existing values are for a different state.")
    if status == RequirementStatus.CONFLICTING_EVIDENCE:
        return (f"Sources disagree on {property_key}. A measurement in the required state would "
                "adjudicate; averaging the existing sources would not.")
    if status == RequirementStatus.INSUFFICIENT_EVIDENCE:
        return (f"Values for {property_key} exist but are unusable (out of applicability domain, "
                "unconverged, or without a numeric interval). A usable determination is needed.")
    return f"No value of any origin exists for {property_key}. Any determination would be new evidence."


def _assumptions(
    state: MaterialState | None, incumbent_state: MaterialState | None,
    results: list[dict[str, Any]],
) -> list[str]:
    """Assumptions are stated explicitly rather than being buried in the computation."""
    assumptions: list[str] = []
    if state is None:
        assumptions.append(
            "No material state was selected for the candidate, so property comparisons are not "
            "qualified by structure, processing history or conditions."
        )
    elif state.processing_history_id is None:
        assumptions.append(
            "The candidate state records no processing history, so any property sensitive to "
            "processing is unqualified."
        )
    if incumbent_state is None:
        assumptions.append(
            "The role records no incumbent material state, so requirements are tested against their "
            "declared thresholds rather than against the incumbent's measured behaviour."
        )
    if any(r.get("governing_state_match") == StateMatchQuality.UNKNOWN_STATE for r in results):
        assumptions.append(
            "At least one requirement is governed by a value that is not state-qualified: the "
            "evidence records no material state, so it is not established to hold in the state asked "
            "about. It was not discarded, and it was not treated as an exact state match."
        )
    if any(r.get("governing_origin") == EvidenceOriginClass.PREDICTED for r in results):
        assumptions.append(
            "At least one requirement is governed by a model prediction rather than a measurement."
        )
    if any(r.get("governing_origin") == EvidenceOriginClass.SIMULATED for r in results):
        assumptions.append(
            "At least one requirement is governed by a physics simulation. Simulation is "
            "computational evidence and is not a physical measurement."
        )
    if any(r["status"] == RequirementStatus.PARTIAL for r in results):
        assumptions.append(
            "At least one requirement is only partially met across the stated value interval."
        )
    return assumptions


def property_definition_by_key(db: Session, key: str) -> MaterialPropertyDefinition | None:
    return db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none()
