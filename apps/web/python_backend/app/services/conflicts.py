from __future__ import annotations

from itertools import combinations
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entities import MaterialPropertyObservation
from app.services.conditions import condition_to_dict
from app.services.units import UnitError, convert


def _condition_signature(obs: MaterialPropertyObservation) -> dict[str, Any]:
    return condition_to_dict(obs.condition_set)


def _same_context(a: MaterialPropertyObservation, b: MaterialPropertyObservation) -> bool:
    return _condition_signature(a) == _condition_signature(b)


def detect_conflicts_from_observations(observations: list[MaterialPropertyObservation], property_key: str | None = None) -> list[dict[str, Any]]:
    if property_key:
        observations = [o for o in observations if o.property_definition.key == property_key]
    by_property: dict[str, list[MaterialPropertyObservation]] = {}
    for obs in observations:
        if obs.status != "active" or obs.evidence.status in {"superseded", "retracted"}:
            continue
        by_property.setdefault(obs.property_definition.key, []).append(obs)

    conflicts: list[dict[str, Any]] = []
    for key, rows in by_property.items():
        definition = rows[0].property_definition
        policy = definition.conflict_policy or "informational"
        if policy == "informational" or len(rows) < 2:
            continue
        involved: set[str] = set(); reasons: list[str] = []; pairs: list[dict[str, Any]] = []
        for a, b in combinations(rows, 2):
            if not _same_context(a, b) or a.value_type != b.value_type:
                continue
            raised = False; reason = ""
            if a.value_type == "boolean":
                raised = a.boolean_value != b.boolean_value; reason = "boolean observations disagree"
            elif a.numeric_value is not None and b.numeric_value is not None and a.unit and b.unit and definition.canonical_unit:
                try:
                    av = convert(a.numeric_value, a.unit, definition.canonical_unit)
                    bv = convert(b.numeric_value, b.unit, definition.canonical_unit)
                except UnitError:
                    continue
                diff = abs(av - bv)
                if policy == "absolute" and definition.conflict_absolute_tolerance is not None:
                    raised = diff > definition.conflict_absolute_tolerance
                    reason = f"absolute difference {diff:.6g} exceeds property tolerance {definition.conflict_absolute_tolerance:.6g}"
                elif policy == "relative" and definition.conflict_relative_tolerance is not None:
                    denom = max(abs(av), abs(bv), 1e-12); rel = diff / denom
                    raised = rel > definition.conflict_relative_tolerance
                    reason = f"relative difference {rel:.4f} exceeds property tolerance {definition.conflict_relative_tolerance:.4f}"
                elif policy == "uncertainty_overlap":
                    a_low = a.uncertainty_lower if a.uncertainty_lower is not None else av - (a.uncertainty or 0)
                    a_high = a.uncertainty_upper if a.uncertainty_upper is not None else av + (a.uncertainty or 0)
                    b_low = b.uncertainty_lower if b.uncertainty_lower is not None else bv - (b.uncertainty or 0)
                    b_high = b.uncertainty_upper if b.uncertainty_upper is not None else bv + (b.uncertainty or 0)
                    raised = max(a_low, b_low) > min(a_high, b_high)
                    reason = "reported uncertainty intervals do not overlap"
            if raised:
                involved.update([a.id, b.id]); reasons.append(reason); pairs.append({"a": a.id, "b": b.id, "reason": reason})
        if involved:
            involved_rows = [r for r in rows if r.id in involved]
            conflicts.append({
                "property_key": key, "policy": policy, "observation_ids": sorted(involved),
                "conditions": _condition_signature(involved_rows[0]), "reasons": sorted(set(reasons)), "pairs": pairs,
                "resolution_state": "curator_preferred" if any(r.curator_preferred for r in involved_rows) else "unresolved",
            })
    return conflicts


def detect_conflicts(db: Session, material_id: str, property_key: str | None = None) -> list[dict[str, Any]]:
    observations = (
        db.query(MaterialPropertyObservation)
        .options(
            selectinload(MaterialPropertyObservation.property_definition),
            selectinload(MaterialPropertyObservation.evidence),
            selectinload(MaterialPropertyObservation.condition_set),
        )
        .filter(MaterialPropertyObservation.material_id == material_id)
        .all()
    )
    return detect_conflicts_from_observations(observations, property_key)
