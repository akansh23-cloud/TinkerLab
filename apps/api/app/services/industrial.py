"""Phase-7 Industrial Viability Engine.

Scientific feasibility is not industrial feasibility. A candidate can be scientifically excellent
and industrially unusable, and the reverse. This module assesses the industrial dimensions
separately and refuses to collapse them into one number without a declared methodology.

Rules enforced here and asserted by tests:

  * Industrial evidence is its own claim class. It never becomes a MaterialPropertyObservation,
    a PropertyPrediction or a SimulationResult, and none of those become industrial evidence.
  * Missing evidence yields UNKNOWN or INSUFFICIENT_EVIDENCE — never zero, never a default, never
    an average, never an optimistic assumption.
  * Cost figures with different currency, currency year or basis are NOT comparable and are never
    silently converted. A constraint that cannot be compared on a like-for-like basis reports
    INSUFFICIENT_EVIDENCE rather than guessing.
  * Two contradictory records are both retained and surfaced as CONFLICTING_EVIDENCE. The newer one
    does not automatically win.
  * A completed assessment is immutable. New evidence produces a new assessment that supersedes it;
    yesterday's conclusion stays explainable exactly as it was made.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.domain.enums import (
    MATURITY_ORDER,
    IndustrialAssessmentState,
    IndustrialCategory,
    IndustrialConstraintStrength,
    MaturityStage,
    ProcessCompatibility,
)
from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    IndustrialConstraint,
    IndustrialEvidence,
    IndustrialViabilityAssessment,
    ManufacturingRoute,
    Material,
    MaterialProcessCompatibility,
    MaturityAssessment,
)

INDUSTRIAL_POLICY_VERSION = "industrial-viability-v1"
INDUSTRIAL_ORIGIN = "industrial_evidence"
MAX_PAGE_SIZE = 200

# Evidence older than this is still used, but the assessment records that it is stale rather than
# silently treating a decade-old commodity price as current.
DEFAULT_STALENESS_DAYS = 730

INDUSTRIAL_SEPARATION_NOTE = (
    "Industrial evidence is a separate claim class from scientific evidence. It never becomes a "
    "property observation, a model prediction or a simulation result, and none of those become "
    "industrial evidence."
)

ASSESSMENT_DIMENSIONS: tuple[str, ...] = (
    "scientific_suitability",
    "manufacturing_compatibility",
    "economic_feasibility",
    "supply_resilience",
    "environmental_evidence",
    "regulatory_compatibility",
    "technology_maturity",
    "experimental_validation",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


def evidence_checksum(payload: dict[str, Any]) -> str:
    """Content identity for an industrial claim, including every comparability qualifier.

    Two cost records that differ only in currency year are different claims and must hash
    differently, otherwise deduplication would silently merge incomparable facts.
    """
    return checksum({"contract": "industrial-evidence-v1", "claim": payload})


class IndustrialError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# Comparability
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CostBasisKey:
    """The tuple that makes two monetary figures comparable. Any mismatch blocks comparison."""

    currency: str | None
    currency_year: int | None
    cost_basis: str | None

    def comparable_with(self, other: CostBasisKey) -> bool:
        return (
            self.currency is not None
            and self.currency == other.currency
            and self.cost_basis == other.cost_basis
            and self.currency_year == other.currency_year
        )

    def describe(self) -> str:
        return f"{self.currency or 'unspecified currency'} {self.currency_year or 'unspecified year'} per {self.cost_basis or 'unspecified basis'}"


def _basis_of(row: IndustrialEvidence | IndustrialConstraint) -> CostBasisKey:
    return CostBasisKey(row.currency, row.currency_year, row.cost_basis)


def is_stale(row: IndustrialEvidence, reference: date | None = None, horizon_days: int = DEFAULT_STALENESS_DAYS) -> bool:
    if row.as_of_date is None:
        return True
    reference = reference or now_utc().date()
    if row.valid_until and row.valid_until < reference:
        return True
    return (reference - row.as_of_date).days > horizon_days


# ---------------------------------------------------------------------------------------------
# Evidence access
# ---------------------------------------------------------------------------------------------
def _visible(column: Any, organisation_id: str | None) -> Any:
    if organisation_id:
        return or_(column.is_(None), column == organisation_id)
    return column.is_(None)


def industrial_evidence_for_target(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None,
    category: str | None = None, metric_key: str | None = None,
) -> list[IndustrialEvidence]:
    query = db.query(IndustrialEvidence).filter(
        IndustrialEvidence.status == "active",
        _visible(IndustrialEvidence.organisation_id, organisation_id),
    )
    if target_kind == "known_material":
        query = query.filter(IndustrialEvidence.material_id == target_id)
    else:
        query = query.filter(IndustrialEvidence.hypothesis_id == target_id)
    if category:
        query = query.filter(IndustrialEvidence.category == category)
    if metric_key:
        query = query.filter(IndustrialEvidence.metric_key == metric_key)
    return query.order_by(
        IndustrialEvidence.category, IndustrialEvidence.metric_key,
        IndustrialEvidence.as_of_date.desc(), IndustrialEvidence.id,
    ).all()


def create_industrial_evidence(db: Session, values: dict[str, Any]) -> IndustrialEvidence:
    if bool(values.get("material_id")) == bool(values.get("hypothesis_id")):
        raise IndustrialError("Industrial evidence must reference exactly one material or one hypothesis")
    numeric_shape = values.get("numeric_value") is not None or (
        values.get("lower_bound") is not None and values.get("upper_bound") is not None
    )
    if values.get("category") == IndustrialCategory.ECONOMIC and numeric_shape:
        if not values.get("currency") or values.get("currency_year") is None or not values.get("cost_basis"):
            raise IndustrialError(
                "MONETARY_BASIS_INCOMPLETE: economic numeric evidence requires currency and cost basis "
                "plus currency_year; a bare monetary figure or range is not comparable."
            )
    if values.get("as_of_date") is None and values.get("category") in {
        IndustrialCategory.ECONOMIC, IndustrialCategory.SUPPLY_CHAIN, IndustrialCategory.REGULATORY
    }:
        raise IndustrialError(
            "Time-varying industrial evidence (economic, supply chain, regulatory) requires an as_of_date"
        )
    if values.get("category") == IndustrialCategory.REGULATORY and not values.get("jurisdiction"):
        raise IndustrialError("Regulatory evidence without a jurisdiction is incomplete and is not stored")

    claim = {
        "target": values.get("material_id") or values.get("hypothesis_id"),
        "category": values.get("category"), "metric_key": values.get("metric_key"),
        "numeric_value": values.get("numeric_value"), "unit": values.get("unit"),
        "boolean_value": values.get("boolean_value"), "categorical_value": values.get("categorical_value"),
        "lower_bound": values.get("lower_bound"), "upper_bound": values.get("upper_bound"),
        "currency": values.get("currency"), "currency_year": values.get("currency_year"),
        "cost_basis": values.get("cost_basis"), "geography": values.get("geography"),
        "jurisdiction": values.get("jurisdiction"), "as_of_date": values.get("as_of_date"),
        "source_type": values.get("source_type"), "source_reference": values.get("source_reference"),
    }
    row = IndustrialEvidence(**values, content_checksum=evidence_checksum(claim))
    db.add(row)
    db.flush()
    return row


# ---------------------------------------------------------------------------------------------
# Dimension evaluation
# ---------------------------------------------------------------------------------------------
@dataclass
class DimensionOutcome:
    state: str
    reasons: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    constraint_results: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    missing: list[dict[str, Any]] = field(default_factory=list)


def _reason(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def industrial_comparability(first: IndustrialEvidence, second: IndustrialEvidence) -> tuple[str, str]:
    """Return whether two industrial claims describe the same decision context.

    Missing or different jurisdiction/geography/process qualifiers are never silently erased.
    """
    if first.metric_key != second.metric_key or first.category != second.category:
        return "not_comparable", "Different metric/category."
    if first.category == IndustrialCategory.ECONOMIC:
        if not _basis_of(first).comparable_with(_basis_of(second)):
            return "not_comparable", "Currency, currency year or cost basis differs or is incomplete."
        if first.unit != second.unit:
            return "not_comparable", "Economic units differ."
        for field_name in ("quantity_basis_value", "quantity_basis_unit", "geography", "process_context", "manufacturing_route_id"):
            a, b = getattr(first, field_name), getattr(second, field_name)
            if a != b:
                return ("insufficient_context" if a is None or b is None else "not_comparable",
                        f"Economic context differs or is incomplete for {field_name}.")
    elif first.category == IndustrialCategory.REGULATORY:
        if not first.jurisdiction or not second.jurisdiction:
            return "insufficient_context", "Regulatory comparison requires jurisdiction on both claims."
        if first.jurisdiction != second.jurisdiction:
            return "not_comparable", "Regulatory claims describe different jurisdictions."
        for field_name in ("geography", "process_context", "manufacturing_route_id"):
            a, b = getattr(first, field_name), getattr(second, field_name)
            if a != b and (a is not None or b is not None):
                return ("insufficient_context" if a is None or b is None else "not_comparable",
                        f"Regulatory context differs or is incomplete for {field_name}.")
    else:
        for field_name in ("jurisdiction", "geography", "process_context", "manufacturing_route_id"):
            a, b = getattr(first, field_name), getattr(second, field_name)
            if a != b and (a is not None or b is not None):
                return ("insufficient_context" if a is None or b is None else "not_comparable",
                        f"Industrial context differs or is incomplete for {field_name}.")
        if (first.conditions or {}) != (second.conditions or {}):
            return "not_comparable", "Declared industrial conditions differ."
    return "comparable", "Claims share the required industrial comparison context."


def detect_conflicts(rows: list[IndustrialEvidence]) -> list[dict[str, Any]]:
    """Detect contradictions only after an explicit industrial comparability decision."""
    conflicts: list[dict[str, Any]] = []
    ordered = sorted(rows, key=lambda r: (r.metric_key, r.id))
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            if first.metric_key != second.metric_key or first.category != second.category:
                continue
            comparable, comparability_detail = industrial_comparability(first, second)
            if comparable != "comparable":
                continue
            if first.boolean_value is not None and second.boolean_value is not None:
                if first.boolean_value != second.boolean_value:
                    conflicts.append({
                        "metric_key": first.metric_key, "kind": "boolean_contradiction",
                        "evidence_ids": [first.id, second.id], "comparability": comparable,
                        "comparability_detail": comparability_detail,
                        "detail": f"Comparable records disagree on {first.metric_key}: {first.boolean_value} vs {second.boolean_value}.",
                    })
                continue
            if first.categorical_value and second.categorical_value:
                if first.categorical_value != second.categorical_value:
                    conflicts.append({
                        "metric_key": first.metric_key, "kind": "categorical_contradiction",
                        "evidence_ids": [first.id, second.id], "comparability": comparable,
                        "comparability_detail": comparability_detail,
                        "detail": f"Comparable records disagree on {first.metric_key}: '{first.categorical_value}' vs '{second.categorical_value}'.",
                    })
                continue
            low_a, high_a = _interval(first)
            low_b, high_b = _interval(second)
            if None in (low_a, high_a, low_b, high_b) or first.unit != second.unit:
                continue
            if high_a < low_b or high_b < low_a:
                conflicts.append({
                    "metric_key": first.metric_key, "kind": "non_overlapping_intervals",
                    "evidence_ids": [first.id, second.id], "comparability": comparable,
                    "comparability_detail": comparability_detail,
                    "basis": _basis_of(first).describe(),
                    "detail": f"Comparable stated ranges for {first.metric_key} do not overlap: "
                              f"[{low_a}, {high_a}] vs [{low_b}, {high_b}] {first.unit or ''}".strip(),
                })
    return conflicts

def _interval(row: IndustrialEvidence) -> tuple[float | None, float | None]:
    if row.lower_bound is not None and row.upper_bound is not None:
        return row.lower_bound, row.upper_bound
    if row.numeric_value is not None:
        if row.uncertainty:
            return row.numeric_value - row.uncertainty, row.numeric_value + row.uncertainty
        return row.numeric_value, row.numeric_value
    return None, None


def evaluate_constraint(
    constraint: IndustrialConstraint, evidence: list[IndustrialEvidence],
    *, elements: list[str], compatibilities: list[MaterialProcessCompatibility],
    routes_by_id: dict[str, ManufacturingRoute], maturity: str,
) -> dict[str, Any]:
    """Evaluate one industrial constraint. Every path returns an explicit, explainable state."""
    kind = constraint.constraint_kind
    base = {
        "constraint_id": constraint.id, "display_label": constraint.display_label,
        "category": constraint.category, "constraint_kind": kind, "strength": constraint.strength,
        "metric_key": constraint.metric_key, "weight": constraint.weight,
    }

    if kind == "banned_element":
        banned = {e.strip().title() for e in (constraint.banned_elements or [])}
        if not elements:
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": "The target's elemental composition is not recorded, so a banned-element "
                              "constraint cannot be evaluated. Absence of composition is not compliance."}
        present = sorted(banned & {e.title() for e in elements})
        if present:
            return {**base, "state": IndustrialAssessmentState.FAIL,
                    "detail": f"Contains banned element(s): {', '.join(present)}.", "offending": present}
        return {**base, "state": IndustrialAssessmentState.PASS,
                "detail": f"No banned element present among the declared composition ({', '.join(sorted(elements))})."}

    if kind == "minimum_maturity":
        required = constraint.minimum_maturity or MaturityStage.THEORETICAL
        if maturity == MaturityStage.UNKNOWN:
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": "No maturity assessment exists for this target; maturity is not assumed."}
        if required not in MATURITY_ORDER or maturity not in MATURITY_ORDER:
            return {**base, "state": IndustrialAssessmentState.UNKNOWN,
                    "detail": f"Maturity stage '{maturity}' cannot be ordered against '{required}'."}
        ok = MATURITY_ORDER.index(maturity) >= MATURITY_ORDER.index(required)
        return {**base, "state": IndustrialAssessmentState.PASS if ok else IndustrialAssessmentState.FAIL,
                "detail": f"Assessed maturity '{maturity}' versus required minimum '{required}'.",
                "observed": maturity, "required": required}

    if kind == "required_process_compatibility":
        required_keys = list(constraint.required_route_keys or [])
        if not required_keys:
            return {**base, "state": IndustrialAssessmentState.UNKNOWN,
                    "detail": "The constraint declares no required manufacturing route."}
        states: dict[str, str] = {}
        for compatibility in compatibilities:
            route = routes_by_id.get(compatibility.route_id)
            if route and route.key in required_keys:
                states[route.key] = compatibility.compatibility
        missing_keys = [k for k in required_keys if k not in states]
        if any(v == ProcessCompatibility.INCOMPATIBLE for v in states.values()):
            failed = sorted(k for k, v in states.items() if v == ProcessCompatibility.INCOMPATIBLE)
            return {**base, "state": IndustrialAssessmentState.FAIL,
                    "detail": f"Incompatible with required manufacturing route(s): {', '.join(failed)}.",
                    "observed": states}
        if missing_keys or any(v == ProcessCompatibility.UNKNOWN for v in states.values()):
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": "Manufacturing compatibility is not recorded for: "
                              f"{', '.join(sorted(set(missing_keys) | {k for k, v in states.items() if v == ProcessCompatibility.UNKNOWN}))}. "
                              "An unrecorded route is not a compatible route.",
                    "observed": states}
        if any(v == ProcessCompatibility.CONDITIONALLY_COMPATIBLE for v in states.values()):
            return {**base, "state": IndustrialAssessmentState.PARTIAL,
                    "detail": "Compatible only under stated conditions.", "observed": states}
        return {**base, "state": IndustrialAssessmentState.PASS,
                "detail": f"Compatible with all required routes: {', '.join(sorted(states))}.", "observed": states}

    if kind == "allowed_jurisdiction":
        allowed = {j.strip().upper() for j in (constraint.allowed_jurisdictions or [])}
        relevant = [e for e in evidence if e.category == IndustrialCategory.REGULATORY]
        if not relevant:
            return {**base, "state": _missing_state(constraint),
                    "detail": "No regulatory evidence exists for this target in any jurisdiction."}
        outside = sorted({(e.jurisdiction or "").upper() for e in relevant if e.jurisdiction} - allowed)
        restricted = [e for e in relevant if e.boolean_value is True and (e.jurisdiction or "").upper() in allowed]
        if restricted:
            return {**base, "state": IndustrialAssessmentState.FAIL,
                    "detail": "A restriction is recorded within an allowed jurisdiction: "
                              + "; ".join(f"{e.display_label} ({e.jurisdiction})" for e in restricted),
                    "evidence_ids": [e.id for e in restricted]}
        covered = sorted({(e.jurisdiction or "").upper() for e in relevant} & allowed)
        if not covered:
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": f"Regulatory evidence exists only for {', '.join(outside) or 'unstated jurisdictions'}, "
                              f"none of which is in the allowed set. Regulatory status does not transfer between jurisdictions."}
        return {**base, "state": IndustrialAssessmentState.PASS,
                "detail": f"No recorded restriction in the allowed jurisdiction(s): {', '.join(covered)}.",
                "evidence_ids": [e.id for e in relevant]}

    if kind == "supplier_diversity":
        relevant = [e for e in evidence if e.metric_key == (constraint.metric_key or "supplier_count")]
        if not relevant:
            return {**base, "state": _missing_state(constraint),
                    "detail": "No supplier-count evidence is recorded."}
        newest = max(relevant, key=lambda e: (e.as_of_date or date.min, e.id))
        if newest.numeric_value is None:
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": "Supplier evidence exists but records no count."}
        required_suppliers = int(constraint.minimum_supplier_count or 1)
        ok = newest.numeric_value >= required_suppliers
        return {**base, "state": IndustrialAssessmentState.PASS if ok else IndustrialAssessmentState.FAIL,
                "detail": f"{int(newest.numeric_value)} supplier(s) recorded as of {newest.as_of_date}; "
                          f"minimum required is {required_suppliers}.",
                "evidence_ids": [newest.id], "stale": is_stale(newest)}

    # Numeric threshold constraints (max_value / min_value / range).
    relevant = [e for e in evidence if e.metric_key == constraint.metric_key]
    if not relevant:
        return {**base, "state": _missing_state(constraint),
                "detail": f"No industrial evidence recorded for metric '{constraint.metric_key}'. "
                          "Missing evidence is not treated as a pass."}

    constraint_basis = _basis_of(constraint)
    if constraint.category == IndustrialCategory.ECONOMIC:
        comparable = [e for e in relevant if _basis_of(e).comparable_with(constraint_basis)]
        if not comparable:
            available = sorted({_basis_of(e).describe() for e in relevant})
            return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                    "detail": f"No cost evidence shares the constraint's basis ({constraint_basis.describe()}). "
                              f"Available bases: {'; '.join(available)}. Figures on different bases are "
                              "never silently converted.",
                    "evidence_ids": [e.id for e in relevant]}
        relevant = comparable

    unit_mismatch = [e for e in relevant if constraint.target_unit and e.unit and e.unit != constraint.target_unit]
    relevant = [e for e in relevant if not (constraint.target_unit and e.unit and e.unit != constraint.target_unit)]
    if not relevant:
        return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                "detail": f"Evidence exists but not in the required unit '{constraint.target_unit}'.",
                "evidence_ids": [e.id for e in unit_mismatch]}

    conflicts = detect_conflicts(relevant)
    if conflicts:
        return {**base, "state": IndustrialAssessmentState.CONFLICTING_EVIDENCE,
                "detail": "Contradictory evidence is recorded for this metric; both records are retained "
                          "and no automatic winner is chosen.",
                "conflicts": conflicts, "evidence_ids": [e.id for e in relevant]}

    newest = max(relevant, key=lambda e: (e.as_of_date or date.min, e.id))
    low, high = _interval(newest)
    if low is None or high is None:
        return {**base, "state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
                "detail": "Evidence exists but carries no numeric value or range.",
                "evidence_ids": [newest.id]}

    stale = is_stale(newest)
    detail_suffix = " Evidence is stale relative to the staleness horizon." if stale else ""
    if kind == "max_value":
        limit = constraint.target_value
        if limit is None:
            return {**base, "state": IndustrialAssessmentState.UNKNOWN, "detail": "Constraint declares no limit."}
        if high <= limit:
            state = IndustrialAssessmentState.PASS
        elif low > limit:
            state = IndustrialAssessmentState.FAIL
        else:
            state = IndustrialAssessmentState.PARTIAL
        return {**base, "state": state, "evidence_ids": [newest.id], "stale": stale,
                "observed_interval": [low, high], "limit": limit, "unit": newest.unit,
                "detail": f"Observed {low}–{high} {newest.unit or ''} against a maximum of {limit} "
                          f"{constraint.target_unit or ''} (as of {newest.as_of_date}).{detail_suffix}".strip()}
    if kind == "min_value":
        limit = constraint.target_value
        if limit is None:
            return {**base, "state": IndustrialAssessmentState.UNKNOWN, "detail": "Constraint declares no limit."}
        if low >= limit:
            state = IndustrialAssessmentState.PASS
        elif high < limit:
            state = IndustrialAssessmentState.FAIL
        else:
            state = IndustrialAssessmentState.PARTIAL
        return {**base, "state": state, "evidence_ids": [newest.id], "stale": stale,
                "observed_interval": [low, high], "limit": limit, "unit": newest.unit,
                "detail": f"Observed {low}–{high} {newest.unit or ''} against a minimum of {limit} "
                          f"{constraint.target_unit or ''} (as of {newest.as_of_date}).{detail_suffix}".strip()}
    if kind == "range":
        lower, upper = constraint.target_value, constraint.target_value_upper
        if lower is None or upper is None:
            return {**base, "state": IndustrialAssessmentState.UNKNOWN, "detail": "Constraint declares no complete range."}
        if low >= lower and high <= upper:
            state = IndustrialAssessmentState.PASS
        elif high < lower or low > upper:
            state = IndustrialAssessmentState.FAIL
        else:
            state = IndustrialAssessmentState.PARTIAL
        return {**base, "state": state, "evidence_ids": [newest.id], "stale": stale,
                "observed_interval": [low, high], "required_range": [lower, upper], "unit": newest.unit,
                "detail": f"Observed {low}–{high} {newest.unit or ''} against required range "
                          f"{lower}–{upper} {constraint.target_unit or ''}.{detail_suffix}".strip()}

    return {**base, "state": IndustrialAssessmentState.UNKNOWN,
            "detail": f"Constraint kind '{kind}' has no evaluator."}


def _missing_state(constraint: IndustrialConstraint) -> str:
    """How a constraint handles absent evidence is declared per constraint, never assumed globally."""
    declared = constraint.treat_missing_evidence_as
    if declared in {
        IndustrialAssessmentState.FAIL, IndustrialAssessmentState.UNKNOWN,
        IndustrialAssessmentState.INSUFFICIENT_EVIDENCE,
    }:
        return declared
    return IndustrialAssessmentState.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------------------------
# Target context
# ---------------------------------------------------------------------------------------------
def resolve_industrial_target(
    db: Session, target_kind: str, target_id: str, organisation_id: str | None
) -> tuple[str, list[str]] | None:
    """Return (display_name, elements) or None when the target is not visible in this scope."""
    if target_kind == "known_material":
        material = db.get(Material, target_id)
        if not material:
            return None
        if material.visibility != "public" and material.owner_organisation_id != organisation_id:
            return None
        return material.display_name, _declared_elements(db, material_id=target_id)
    hypothesis = db.get(CandidateHypothesis, target_id)
    if not hypothesis or hypothesis.organisation_id != organisation_id:
        return None
    return hypothesis.display_label, _declared_elements(db, hypothesis_id=target_id)


def _declared_elements(db: Session, *, material_id: str | None = None, hypothesis_id: str | None = None) -> list[str]:
    """Elements come from a declared structural representation only.

    They are never parsed out of a display name or a composition summary string: 'Silicon carbide
    substrate' is a label, not a composition, and guessing elements from labels is how a banned
    element check silently passes.
    """
    from app.models.entities import ScientificRepresentation

    query = db.query(ScientificRepresentation).filter(ScientificRepresentation.status == "active")
    query = query.filter(
        ScientificRepresentation.material_id == material_id if material_id
        else ScientificRepresentation.hypothesis_id == hypothesis_id
    )
    elements: set[str] = set()
    for row in query.all():
        elements.update(row.chemical_elements or [])
    return sorted(elements)


def current_maturity(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None = None
) -> tuple[str, MaturityAssessment | None]:
    query = db.query(MaturityAssessment).filter(MaturityAssessment.superseded_by_id.is_(None))
    # Request paths always supply the tenant. The optional unscoped form is retained only for
    # legacy internal/test callers; no API route uses it.
    if organisation_id is not None:
        query = query.filter(_visible(MaturityAssessment.organisation_id, organisation_id))
    query = query.filter(
        MaturityAssessment.material_id == target_id if target_kind == "known_material"
        else MaturityAssessment.hypothesis_id == target_id
    )
    rows = query.order_by(MaturityAssessment.created_at.desc(), MaturityAssessment.id).all()
    if not rows:
        return MaturityStage.UNKNOWN, None
    # The highest justified stage among current assessments, ordered by the declared ladder.
    ranked = [r for r in rows if r.stage in MATURITY_ORDER]
    if not ranked:
        return MaturityStage.UNKNOWN, rows[0]
    best = max(ranked, key=lambda r: MATURITY_ORDER.index(r.stage))
    return best.stage, best


def compatibilities_for_target(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None
) -> list[MaterialProcessCompatibility]:
    query = db.query(MaterialProcessCompatibility).filter(
        _visible(MaterialProcessCompatibility.organisation_id, organisation_id)
    )
    query = query.filter(
        MaterialProcessCompatibility.material_id == target_id if target_kind == "known_material"
        else MaterialProcessCompatibility.hypothesis_id == target_id
    )
    return query.order_by(MaterialProcessCompatibility.route_id).all()


# ---------------------------------------------------------------------------------------------
# Dimension roll-up
# ---------------------------------------------------------------------------------------------
CATEGORY_TO_DIMENSION: dict[str, str] = {
    IndustrialCategory.MANUFACTURING: "manufacturing_compatibility",
    IndustrialCategory.ECONOMIC: "economic_feasibility",
    IndustrialCategory.SUPPLY_CHAIN: "supply_resilience",
    IndustrialCategory.ENVIRONMENTAL: "environmental_evidence",
    IndustrialCategory.REGULATORY: "regulatory_compatibility",
    IndustrialCategory.MATURITY: "technology_maturity",
}

# Worst-wins ordering. A single hard FAIL is never averaged away by other passing dimensions.
_STATE_SEVERITY: dict[str, int] = {
    IndustrialAssessmentState.FAIL: 5,
    IndustrialAssessmentState.CONFLICTING_EVIDENCE: 4,
    IndustrialAssessmentState.INSUFFICIENT_EVIDENCE: 3,
    IndustrialAssessmentState.UNKNOWN: 2,
    IndustrialAssessmentState.PARTIAL: 1,
    IndustrialAssessmentState.PASS: 0,
}


def _roll_up(states: list[str]) -> str:
    if not states:
        return IndustrialAssessmentState.UNKNOWN
    return max(states, key=lambda s: _STATE_SEVERITY.get(s, 2))


def _scientific_dimension(
    db: Session, *, project_id: str, target_kind: str, target_id: str, organisation_id: str
) -> dict[str, Any]:
    """Report the authoritative Phase-5 feasibility class without re-deriving science."""
    from app.models.entities import ReplacementProject, VirtualCandidateEvaluation

    project = db.get(ReplacementProject, project_id)
    if project is None or project.organisation_id != organisation_id:
        raise LookupError("Project not found for organisation")
    candidate = (
        db.query(Candidate)
        .filter(Candidate.project_id == project_id)
        .filter(Candidate.material_id == target_id if target_kind == "known_material" else Candidate.hypothesis_id == target_id)
        .order_by(Candidate.created_at.desc()).first()
    )
    if candidate is None:
        return {"state": IndustrialAssessmentState.UNKNOWN,
                "detail": "This target is not a candidate in this project, so no scientific screening result exists."}
    evaluation = (
        db.query(VirtualCandidateEvaluation)
        .filter(VirtualCandidateEvaluation.candidate_id == candidate.id)
        .order_by(VirtualCandidateEvaluation.created_at.desc()).first()
    )
    if evaluation is None:
        return {"state": IndustrialAssessmentState.INSUFFICIENT_EVIDENCE, "candidate_id": candidate.id,
                "detail": "No virtual evaluation exists for this candidate yet."}
    mapping = {
        "robustly_feasible": IndustrialAssessmentState.PASS,
        "robustly_infeasible": IndustrialAssessmentState.FAIL,
        "uncertain": IndustrialAssessmentState.UNKNOWN,
    }
    state = mapping.get(str(evaluation.feasibility_class), IndustrialAssessmentState.UNKNOWN)
    return {
        "state": state, "candidate_id": candidate.id, "evaluation_id": evaluation.id,
        "campaign_iteration_id": evaluation.campaign_iteration_id,
        "feasibility_class": evaluation.feasibility_class, "rationale": evaluation.rationale,
        "evaluation_checksum": evaluation.deterministic_evaluation_checksum,
        "evaluation_created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
        "detail": (
            "Phase-5 virtual evaluation classified the candidate as robustly feasible." if state == IndustrialAssessmentState.PASS
            else "Phase-5 virtual evaluation classified the candidate as robustly infeasible." if state == IndustrialAssessmentState.FAIL
            else f"Phase-5 virtual evaluation feasibility class '{evaluation.feasibility_class}' does not establish a pass/fail conclusion."
        ),
        "origin_note": "Derived from Phase-5 virtual evaluation; not re-derived by the industrial engine.",
    }

def _experimental_validation_dimension(db: Session, *, target_kind: str, target_id: str) -> dict[str, Any]:
    """Phase 7 can only report that physical validation has not been performed.

    Experimental records arrive in Phase 9. Until then this dimension is honestly UNKNOWN, never
    PASS, and never inferred from a converged simulation.
    """
    from app.models.entities import SimulationResult

    simulated = (
        db.query(SimulationResult)
        .filter(SimulationResult.target_scientific_id == target_id,
                SimulationResult.scientific_status == "converged")
        .count()
    )
    return {
        "state": IndustrialAssessmentState.UNKNOWN,
        "converged_simulation_count": simulated,
        "detail": ("No physical experimental validation is recorded for this target. "
                   + (f"{simulated} converged simulation result(s) exist, and simulation is not experiment."
                      if simulated else "")).strip(),
    }


def assess_industrial_viability(
    db: Session, *, project_id: str, organisation_id: str, target_kind: str, target_id: str,
    candidate_id: str | None = None, created_by: str | None = None,
    composite_methodology: str | None = None, composite_weights: dict[str, float] | None = None,
    persist: bool = True,
) -> tuple[IndustrialViabilityAssessment | None, dict[str, Any]]:
    """Assess one candidate across every industrial dimension.

    Returns (persisted_row_or_None, payload). The payload is fully explainable on its own: each
    dimension carries its state, the constraints that produced it and the evidence behind them.
    """
    resolved = resolve_industrial_target(db, target_kind, target_id, organisation_id)
    if resolved is None:
        raise LookupError("Industrial assessment target not found")
    display_name, elements = resolved

    # Candidate identity is authoritative when supplied; a valid FK to an unrelated target/project is rejected.
    if candidate_id is not None:
        candidate = db.get(Candidate, candidate_id)
        if candidate is None or candidate.project_id != project_id:
            raise IndustrialError("CANDIDATE_TARGET_MISMATCH: candidate does not belong to this project")
        expected_id = candidate.material_id if target_kind == "known_material" else candidate.hypothesis_id
        if candidate.candidate_kind != target_kind or expected_id != target_id:
            raise IndustrialError("CANDIDATE_TARGET_MISMATCH: candidate does not reference the requested target")

    evidence = industrial_evidence_for_target(
        db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id
    )
    constraints = (
        db.query(IndustrialConstraint)
        .filter(IndustrialConstraint.project_id == project_id,
                IndustrialConstraint.organisation_id == organisation_id)
        .order_by(IndustrialConstraint.category, IndustrialConstraint.id).all()
    )
    compatibilities = compatibilities_for_target(
        db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id
    )
    routes_by_id = {r.id: r for r in db.query(ManufacturingRoute).all()}
    maturity_stage, maturity_row = current_maturity(db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)

    constraint_results = [
        evaluate_constraint(c, evidence, elements=elements, compatibilities=compatibilities,
                            routes_by_id=routes_by_id, maturity=maturity_stage)
        for c in constraints
    ]

    dimension_states: dict[str, str] = {}
    dimension_details: dict[str, Any] = {}

    scientific = _scientific_dimension(db, project_id=project_id, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)
    dimension_states["scientific_suitability"] = scientific["state"]
    dimension_details["scientific_suitability"] = scientific

    experimental = _experimental_validation_dimension(db, target_kind=target_kind, target_id=target_id)
    dimension_states["experimental_validation"] = experimental["state"]
    dimension_details["experimental_validation"] = experimental

    dimension_states["technology_maturity"] = (
        IndustrialAssessmentState.UNKNOWN if maturity_stage == MaturityStage.UNKNOWN
        else IndustrialAssessmentState.PASS
    )
    dimension_details["technology_maturity"] = {
        "state": dimension_states["technology_maturity"], "stage": maturity_stage,
        "assessment_id": maturity_row.id if maturity_row else None,
        "justification": maturity_row.justification if maturity_row else None,
        "detail": ("No maturity assessment exists; maturity is not inferred from the presence of other evidence."
                   if maturity_stage == MaturityStage.UNKNOWN
                   else f"Assessed maturity stage: {maturity_stage}."),
    }

    for category, dimension in CATEGORY_TO_DIMENSION.items():
        state: str
        category_constraints = [r for r in constraint_results if r["category"] == category]
        category_evidence = [e for e in evidence if e.category == category]
        conflicts = detect_conflicts(category_evidence)
        if category_constraints:
            states_to_roll = [r["state"] for r in category_constraints]
            if dimension == "technology_maturity" and maturity_stage != MaturityStage.UNKNOWN:
                states_to_roll.append(IndustrialAssessmentState.PASS)
            state = _roll_up(states_to_roll)
        elif dimension == "technology_maturity":
            state = IndustrialAssessmentState.UNKNOWN if maturity_stage == MaturityStage.UNKNOWN else IndustrialAssessmentState.PASS
        elif conflicts:
            state = IndustrialAssessmentState.CONFLICTING_EVIDENCE.value
        elif category_evidence:
            # Evidence with no constraint to test it against is information, not a verdict.
            state = IndustrialAssessmentState.PARTIAL.value
        else:
            state = IndustrialAssessmentState.UNKNOWN.value
        dimension_states[dimension] = state
        dimension_details[dimension] = {
            "state": state,
            "constraint_results": category_constraints,
            "evidence_ids": [e.id for e in category_evidence],
            "evidence_count": len(category_evidence),
            "stale_evidence_ids": [e.id for e in category_evidence if is_stale(e)],
            "estimate_evidence_ids": [e.id for e in category_evidence if e.is_estimate],
            "conflicts": conflicts,
            "stage": maturity_stage if dimension == "technology_maturity" else None,
            "assessment_id": maturity_row.id if (dimension == "technology_maturity" and maturity_row) else None,
            "justification": maturity_row.justification if (dimension == "technology_maturity" and maturity_row) else None,
            "detail": ("No industrial evidence and no constraint exist for this dimension."
                       if state == IndustrialAssessmentState.UNKNOWN else
                       "Evidence is recorded but no project constraint tests it, so no verdict is implied."
                       if state == IndustrialAssessmentState.PARTIAL and not category_constraints else None),
        }

    hard_failures = [
        r for r in constraint_results
        if r["strength"] == IndustrialConstraintStrength.HARD and r["state"] == IndustrialAssessmentState.FAIL
    ]
    soft_results = [r for r in constraint_results if r["strength"] != IndustrialConstraintStrength.HARD]
    unknown_dimensions = sorted(
        d for d, s in dimension_states.items()
        if s in {IndustrialAssessmentState.UNKNOWN, IndustrialAssessmentState.INSUFFICIENT_EVIDENCE}
    )
    all_conflicts = [c for d in dimension_details.values() if isinstance(d, dict) for c in d.get("conflicts", [])]

    overall: str
    if hard_failures:
        overall = IndustrialAssessmentState.FAIL.value
    else:
        overall = _roll_up(list(dimension_states.values()))

    composite_score, is_partial = _composite(
        dimension_states, composite_methodology, composite_weights or {}
    )

    payload = {
        "project_id": project_id, "target_kind": target_kind, "target_id": target_id,
        "target_display_name": display_name, "declared_elements": elements,
        "dimension_states": dimension_states, "dimension_details": dimension_details,
        "hard_constraint_failures": hard_failures, "soft_constraint_results": soft_results,
        "unknown_dimensions": unknown_dimensions, "conflicting_evidence": all_conflicts,
        "overall_state": overall, "maturity_stage": maturity_stage,
        "composite_score": composite_score,
        "composite_methodology": composite_methodology,
        "composite_weights": composite_weights or {},
        "composite_is_partial": is_partial,
        "evidence_coverage": {
            "total_records": len(evidence),
            "by_category": {c: len([e for e in evidence if e.category == c]) for c in sorted({e.category for e in evidence})},
            "stale_records": len([e for e in evidence if is_stale(e)]),
            "estimate_records": len([e for e in evidence if e.is_estimate]),
            "dimensions_with_no_evidence": sorted(
                d for cat, d in CATEGORY_TO_DIMENSION.items() if not any(e.category == cat for e in evidence)
            ),
        },
        "missing_evidence": [
            {"constraint_id": r["constraint_id"], "display_label": r["display_label"],
             "metric_key": r.get("metric_key"), "category": r["category"], "state": r["state"],
             "detail": r.get("detail")}
            for r in constraint_results
            if r["state"] in {IndustrialAssessmentState.INSUFFICIENT_EVIDENCE, IndustrialAssessmentState.UNKNOWN}
        ],
        "policy_version": INDUSTRIAL_POLICY_VERSION,
        "separation_note": INDUSTRIAL_SEPARATION_NOTE,
    }

    # The snapshot fixes exactly which evidence and constraints produced this conclusion, so the
    # assessment stays explainable after the underlying evidence changes.
    evidence_snapshot = {
        "evidence": sorted(
            [{"id": e.id, "metric_key": e.metric_key, "category": e.category,
              "checksum": e.content_checksum, "as_of_date": str(e.as_of_date) if e.as_of_date else None}
             for e in evidence], key=lambda x: (x["category"], x["metric_key"], x["id"])
        ),
        "compatibilities": sorted(
            [{"route_id": c.route_id, "compatibility": c.compatibility} for c in compatibilities],
            key=lambda x: x["route_id"]
        ),
        "maturity_assessment_id": maturity_row.id if maturity_row else None,
    }
    constraint_snapshot = {
        "constraints": sorted(
            [{"id": c.id, "kind": c.constraint_kind, "category": c.category, "strength": c.strength,
              "metric_key": c.metric_key, "target_value": c.target_value,
              "target_value_upper": c.target_value_upper, "target_unit": c.target_unit,
              "currency": c.currency, "currency_year": c.currency_year, "cost_basis": c.cost_basis,
              "banned_elements": list(c.banned_elements or []),
              "allowed_jurisdictions": list(c.allowed_jurisdictions or []),
              "minimum_maturity": c.minimum_maturity,
              "treat_missing_evidence_as": c.treat_missing_evidence_as}
             for c in constraints], key=lambda x: str(x["id"])
        ),
    }
    assessment_checksum = checksum({
        "contract": INDUSTRIAL_POLICY_VERSION,
        "target": [target_kind, target_id], "project": project_id,
        "evidence_snapshot": evidence_snapshot, "constraint_snapshot": constraint_snapshot,
        "dimension_states": dimension_states, "overall_state": overall,
        "maturity_stage": maturity_stage,
        "composite": {"methodology": composite_methodology, "weights": composite_weights or {},
                      "score": composite_score},
    })
    payload["assessment_checksum"] = assessment_checksum

    if not persist:
        return None, payload

    row = IndustrialViabilityAssessment(
        organisation_id=organisation_id, project_id=project_id, target_kind=target_kind,
        target_scientific_id=target_id, candidate_id=candidate_id,
        dimension_states=dimension_states, dimension_details=dimension_details,
        hard_constraint_failures=hard_failures, soft_constraint_results=soft_results,
        unknown_dimensions=unknown_dimensions, evidence_coverage=payload["evidence_coverage"],
        missing_evidence=payload["missing_evidence"], conflicting_evidence=all_conflicts,
        overall_state=overall, composite_score=composite_score,
        composite_methodology=composite_methodology, composite_weights=composite_weights or {},
        composite_is_partial=is_partial, maturity_stage=maturity_stage,
        evidence_snapshot=evidence_snapshot, constraint_snapshot=constraint_snapshot,
        policy_version=INDUSTRIAL_POLICY_VERSION, assessment_checksum=assessment_checksum,
        created_by=created_by,
    )
    db.add(row)
    db.flush()
    # Supersede rather than overwrite: the previous conclusion remains readable and explainable.
    previous = (
        db.query(IndustrialViabilityAssessment)
        .filter(IndustrialViabilityAssessment.organisation_id == organisation_id,
                IndustrialViabilityAssessment.project_id == project_id,
                IndustrialViabilityAssessment.target_scientific_id == target_id,
                IndustrialViabilityAssessment.superseded_by_id.is_(None),
                IndustrialViabilityAssessment.id != row.id)
        .all()
    )
    for old in previous:
        old.superseded_by_id = row.id
    db.flush()
    payload["assessment_id"] = row.id
    return row, payload


def _composite(
    dimension_states: dict[str, str], methodology: str | None, weights: dict[str, float]
) -> tuple[float | None, bool]:
    """Declared weighted mean with explicit safety bounds and no implicit score for unknowns."""
    if not methodology:
        return None, True
    if methodology != "declared_weighted_mean_v1":
        raise IndustrialError(f"Unknown composite methodology: {methodology}")
    unknown_keys = sorted(set(weights) - set(ASSESSMENT_DIMENSIONS))
    if unknown_keys:
        raise IndustrialError(f"INVALID_COMPOSITE_WEIGHT: unknown dimension(s): {', '.join(unknown_keys)}")
    for key, value in weights.items():
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0:
            raise IndustrialError(f"INVALID_COMPOSITE_WEIGHT: weight for {key} must be finite and >= 0")
    if weights and not any(float(v) > 0 for v in weights.values()):
        raise IndustrialError("INVALID_COMPOSITE_WEIGHT: at least one supplied weight must be > 0")
    contributions = {
        IndustrialAssessmentState.PASS.value: 1.0,
        IndustrialAssessmentState.PARTIAL.value: 0.5,
        IndustrialAssessmentState.FAIL.value: 0.0,
    }
    total_weight = total = 0.0
    scored = 0
    for dimension, state in sorted(dimension_states.items()):
        if str(state) not in contributions:
            continue
        weight = float(weights.get(dimension, 1.0))
        if weight == 0:
            continue
        total += contributions[str(state)] * weight
        total_weight += weight
        scored += 1
    if total_weight <= 0:
        return None, True
    score = total / total_weight
    if not math.isfinite(score) or not (0.0 <= score <= 1.0):
        raise IndustrialError("INVALID_COMPOSITE_WEIGHT: composite score escaped the declared [0, 1] range")
    return round(score, 6), scored < len(dimension_states)

def compare_industrial_viability(
    db: Session, *, project_id: str, organisation_id: str, targets: list[dict[str, str]],
    composite_methodology: str | None = None, composite_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Side-by-side comparison. Ordering is deterministic and never hides an unknown."""
    rows = []
    for target in targets[:MAX_PAGE_SIZE]:
        try:
            _, payload = assess_industrial_viability(
                db, project_id=project_id, organisation_id=organisation_id,
                target_kind=target["target_kind"], target_id=target["target_id"],
                candidate_id=target.get("candidate_id"),
                composite_methodology=composite_methodology, composite_weights=composite_weights,
                persist=False,
            )
        except LookupError:
            continue
        rows.append(payload)
    # Sort by hard failures first, then unknown count, then name. A candidate is never promoted
    # above another because its evidence is merely absent.
    rows.sort(key=lambda p: (
        1 if p["overall_state"] == IndustrialAssessmentState.FAIL else 0,
        len(p["unknown_dimensions"]),
        str(p["target_display_name"]),
    ))
    return {
        "project_id": project_id,
        "dimensions": list(ASSESSMENT_DIMENSIONS),
        "candidates": rows,
        "comparability_note": (
            "Dimensions are reported separately. A candidate with fewer UNKNOWN dimensions is better "
            "evidenced, which is not the same as being better."
        ),
        "separation_note": INDUSTRIAL_SEPARATION_NOTE,
    }
