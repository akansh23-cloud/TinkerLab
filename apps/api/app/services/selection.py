from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entities import MaterialPropertyDefinition, MaterialPropertyObservation
from app.services.conditions import compare_condition_context
from app.services.units import UnitError, convert


@dataclass
class SelectionPolicy:
    allowed_evidence_types: set[str] | None = None


@dataclass
class SelectionContext:
    definitions_by_key: dict[str, MaterialPropertyDefinition]
    observations_by_material_property: dict[tuple[str, str], list[MaterialPropertyObservation]]


def build_selection_context(db: Session, material_ids: list[str] | set[str]) -> SelectionContext:
    ids = list(set(material_ids))
    definitions = db.query(MaterialPropertyDefinition).all()
    definitions_by_id = {d.id: d for d in definitions}
    rows = []
    if ids:
        rows = (
            db.query(MaterialPropertyObservation)
            .options(
                selectinload(MaterialPropertyObservation.evidence),
                selectinload(MaterialPropertyObservation.condition_set),
                selectinload(MaterialPropertyObservation.property_definition),
            )
            .filter(MaterialPropertyObservation.material_id.in_(ids))
            .all()
        )
    grouped: dict[tuple[str, str], list[MaterialPropertyObservation]] = {}
    for row in rows:
        definition = definitions_by_id.get(row.property_definition_id) or row.property_definition
        grouped.setdefault((row.material_id, definition.key), []).append(row)
    return SelectionContext({d.key: d for d in definitions}, grouped)


def _observation_dict(obs: MaterialPropertyObservation, definition: MaterialPropertyDefinition, applicability: str) -> dict[str, Any]:
    canonical_value = None
    if obs.value_type == "numeric" and obs.numeric_value is not None and obs.unit and definition.canonical_unit:
        try:
            canonical_value = convert(obs.numeric_value, obs.unit, definition.canonical_unit)
        except UnitError:
            canonical_value = None
    return {
        "observation_id": obs.id,
        "numeric_value": obs.numeric_value,
        "boolean_value": obs.boolean_value,
        "unit": obs.unit,
        "canonical_value": canonical_value,
        "canonical_unit": definition.canonical_unit,
        "applicability": applicability,
        "evidence_id": obs.evidence_id,
        "confidence": obs.confidence,
        "condition_set_id": obs.condition_set_id,
        "evidence_type": obs.evidence.evidence_type,
        "evidence_title": obs.evidence.title,
        "status": obs.status,
        "curator_preferred": obs.curator_preferred,
    }


def select_from_context(
    context: SelectionContext,
    material_id: str,
    property_key: str,
    *,
    requested_context: dict[str, Any] | None = None,
    policy: SelectionPolicy | None = None,
) -> dict[str, Any]:
    definition = context.definitions_by_key.get(property_key)
    if not definition:
        return {"property_key": property_key, "selected": None, "rationale": [], "alternatives": [], "excluded": [], "conflict": False, "unknown_reason": "unknown property definition"}
    observations = context.observations_by_material_property.get((material_id, property_key), [])
    policy = policy or SelectionPolicy()
    eligible: list[tuple[int, str, MaterialPropertyObservation, list[str]]] = []
    excluded: list[dict[str, Any]] = []
    for obs in observations:
        evidence = obs.evidence
        reasons: list[str] = []
        if obs.status in {"superseded", "retracted"}:
            excluded.append({"observation_id": obs.id, "reason": f"observation status is {obs.status}"}); continue
        if evidence.status in {"superseded", "retracted"}:
            excluded.append({"observation_id": obs.id, "reason": f"evidence status is {evidence.status}"}); continue
        if policy.allowed_evidence_types and evidence.evidence_type not in policy.allowed_evidence_types:
            excluded.append({"observation_id": obs.id, "reason": "evidence type excluded by selection policy"}); continue
        applicability, condition_reasons, condition_score = compare_condition_context(obs.condition_set, requested_context or {})
        reasons.extend(condition_reasons)
        if applicability == "inapplicable":
            excluded.append({"observation_id": obs.id, "reason": "; ".join(reasons)}); continue
        score = condition_score
        if obs.curator_preferred:
            score += 1000; reasons.append("explicit curator preference applied")
        if obs.condition_set is not None:
            score += 2
        eligible.append((score, applicability, obs, reasons))
    if not eligible:
        return {"property_key": property_key, "selected": None, "rationale": [], "alternatives": [], "excluded": excluded, "conflict": False, "unknown_reason": "no applicable active observation"}
    eligible.sort(key=lambda item: (-item[0], item[2].created_at, item[2].id))
    top_score = eligible[0][0]
    top = [x for x in eligible if x[0] == top_score]
    if len(top) > 1 and not any(x[2].curator_preferred for x in top):
        top.sort(key=lambda item: item[2].id)
    selected_score, selected_applicability, selected, rationale = top[0]
    alternatives = [_observation_dict(x[2], definition, x[1]) for x in eligible if x[2].id != selected.id]
    conflict = len(top) > 1
    if conflict:
        rationale = [*rationale, "multiple equally applicable observations remain; selection is deterministic for display and must not be interpreted as scientific consensus"]
    else:
        rationale = [*rationale, f"selected highest applicable observation (policy score {selected_score})"]
    return {
        "property_key": property_key,
        "selected": _observation_dict(selected, definition, selected_applicability),
        "rationale": rationale,
        "alternatives": alternatives,
        "excluded": excluded,
        "conflict": conflict,
        "unknown_reason": None,
    }


def select_observation(
    db: Session,
    material_id: str,
    property_key: str,
    *,
    requested_context: dict[str, Any] | None = None,
    policy: SelectionPolicy | None = None,
) -> dict[str, Any]:
    context = build_selection_context(db, [material_id])
    return select_from_context(context, material_id, property_key, requested_context=requested_context, policy=policy)
