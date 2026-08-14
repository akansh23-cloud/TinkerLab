from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    Candidate,
    Material,
    MaterialPropertyDefinition,
    PropertyPrediction,
    ReplacementProject,
)
from app.services.conflicts import detect_conflicts
from app.services.selection import SelectionContext, build_selection_context, select_from_context
from app.services.units import UnitError, convert


def _compare(value: float, comparator: str, lower: float | None, upper: float | None) -> bool:
    assert lower is not None
    if comparator == "<": return value < lower
    if comparator == "<=": return value <= lower
    if comparator == "=":
        tolerance = max(abs(lower) * 1e-9, 1e-12)
        return abs(value - lower) <= tolerance
    if comparator == ">=": return value >= lower
    if comparator == ">": return value > lower
    if comparator == "between":
        assert upper is not None
        return lower <= value <= upper
    raise ValueError(f"Unsupported comparator {comparator}")


def _selection_context(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    context = metadata.get("conditions") or metadata.get("condition_context") or {}
    return context if isinstance(context, dict) else {}


def _prediction_lookup(prediction_map: dict[tuple[str, str], PropertyPrediction] | None, candidate: Candidate, property_key: str) -> PropertyPrediction | None:
    if not prediction_map:
        return None
    for key in (candidate.id, candidate.hypothesis_id, candidate.material_id):
        if key and (key, property_key) in prediction_map:
            return prediction_map[(key, property_key)]
    return None


def _base_prediction_fields(origin: str = "known_evidence") -> dict[str, Any]:
    return {
        "value_origin": origin,
        "prediction_id": None,
        "model_version": None,
        "prediction_interval": None,
        "applicability_status": None,
        "uncertainty_crosses_constraint": False,
    }


def evaluate_constraint(db: Session, material: Material, c, definitions: dict[str, MaterialPropertyDefinition], selection_context: SelectionContext, conflict_keys: set[str] | None = None) -> dict[str, Any]:
    definition = definitions.get(c.property_key)
    base_unknown = {
        "constraint_id": c.id, "property_key": c.property_key, "status": "UNKNOWN",
        "observed_value": None, "observed_unit": None, "canonical_value": None,
        "canonical_unit": definition.canonical_unit if definition else None,
        "target": {}, "evidence_id": None, "confidence": None, "unknown_reason": None,
        "selected_observation_id": None, "selection_rationale": [], "applicability": None,
        "alternatives_count": 0, "conflict": False, **_base_prediction_fields("none"),
    }
    if definition is None:
        return {**base_unknown, "unknown_reason": "Unknown property definition"}
    context = _selection_context(c.metadata_json)
    selection = select_from_context(selection_context, material.id, c.property_key, requested_context=context)
    selected = selection["selected"]
    target = {
        "operator": c.comparator,
        "value": c.target_boolean if c.comparator == "boolean" else c.target_value,
        "upper": c.target_value_upper,
        "unit": c.target_unit,
        "conditions": context,
    }
    if selected is None:
        return {
            **base_unknown, "target": target, "selection_rationale": selection["rationale"],
            "alternatives_count": len(selection["alternatives"]), "conflict": selection["conflict"],
            "unknown_reason": f"No observation applicable for this property: {selection['unknown_reason'] or 'no applicable active observation'}",
        }
    common = {
        "constraint_id": c.id, "property_key": c.property_key, "target": target,
        "evidence_id": selected.get("evidence_id"), "confidence": selected.get("confidence"),
        "selected_observation_id": selected["observation_id"], "selection_rationale": selection["rationale"],
        "applicability": selected["applicability"], "alternatives_count": len(selection["alternatives"]),
        "conflict": bool(selection["conflict"] or c.property_key in (conflict_keys or set())), "unknown_reason": None,
        **_base_prediction_fields("known_evidence"),
    }
    if c.comparator == "boolean":
        observed = selected.get("boolean_value")
        if observed is None:
            return {**base_unknown, **common, "status": "UNKNOWN", "observed_value": None, "observed_unit": None, "canonical_value": None, "canonical_unit": None, "unknown_reason": "Selected observation is not boolean"}
        return {**common, "status": "PASS" if observed == c.target_boolean else "FAIL", "observed_value": observed, "observed_unit": None, "canonical_value": None, "canonical_unit": None}
    observed = selected.get("numeric_value")
    unit = selected.get("unit")
    if observed is None or unit is None:
        return {**base_unknown, **common, "status": "UNKNOWN", "unknown_reason": "Selected observation is not numeric"}
    try:
        candidate_canonical = convert(float(observed), unit, definition.canonical_unit or unit)
        lower = convert(c.target_value, c.target_unit, definition.canonical_unit or c.target_unit) if c.target_value is not None and c.target_unit else None
        upper = convert(c.target_value_upper, c.target_unit, definition.canonical_unit or c.target_unit) if c.target_value_upper is not None and c.target_unit else None
    except UnitError as exc:
        return {**base_unknown, **common, "observed_value": observed, "observed_unit": unit, "unknown_reason": str(exc)}
    return {
        **common, "status": "PASS" if _compare(candidate_canonical, c.comparator, lower, upper) else "FAIL",
        "observed_value": observed, "observed_unit": unit, "canonical_value": candidate_canonical,
        "canonical_unit": definition.canonical_unit,
    }


def _prediction_constraint(c, definition: MaterialPropertyDefinition | None, prediction: PropertyPrediction | None) -> dict[str, Any]:
    from app.services.prediction import interval_constraint_status

    context = _selection_context(c.metadata_json)
    base = {
        "constraint_id": c.id, "property_key": c.property_key,
        "observed_value": prediction.numeric_point_estimate if prediction and prediction.status == "predicted" else None,
        "observed_unit": prediction.output_unit if prediction and prediction.status == "predicted" else None,
        "canonical_value": prediction.canonical_value if prediction and prediction.status == "predicted" else None,
        "canonical_unit": definition.canonical_unit if definition else None,
        "target": {"operator": c.comparator, "value": c.target_boolean if c.comparator == "boolean" else c.target_value, "upper": c.target_value_upper, "unit": c.target_unit, "conditions": context},
        "evidence_id": None, "confidence": None, "selected_observation_id": None,
        "alternatives_count": 0, "conflict": False, "value_origin": "model_prediction" if prediction else "none",
        "prediction_id": prediction.id if prediction else None,
        "model_version": prediction.model_version_id if prediction else None,
        "prediction_interval": ({"lower": prediction.uncertainty_lower, "upper": prediction.uncertainty_upper, "unit": prediction.output_unit} if prediction and prediction.status == "predicted" else None),
        "applicability_status": prediction.applicability_status if prediction else None,
        "applicability": prediction.applicability_status if prediction else None,
    }
    if not prediction:
        return {
            **base, "status": "UNKNOWN", "unknown_reason": "Hypothesis has no independent property evidence or selected model prediction.",
            "selection_rationale": ["Generated/manual hypotheses do not inherit baseline material observations."],
            "uncertainty_crosses_constraint": False,
        }
    if c.comparator == "boolean":
        return {
            **base, "status": "UNKNOWN", "unknown_reason": "Phase-4 numeric predictor cannot evaluate boolean constraints.",
            "selection_rationale": ["Prediction exists only for a numeric property."], "uncertainty_crosses_constraint": False,
        }
    status, crosses, reason = interval_constraint_status(prediction, c.comparator, c.target_value, c.target_value_upper, c.target_unit)
    rationale = ["Constraint evaluated conservatively using the complete declared prediction interval."]
    if prediction.applicability_status == "borderline":
        rationale.append("Model applicability is borderline; prediction is retained with warning.")
    return {
        **base, "status": status, "unknown_reason": reason if status == "UNKNOWN" else None,
        "selection_rationale": rationale, "uncertainty_crosses_constraint": crosses,
    }


def compare_property(db: Session, baseline: Material, candidate: Material, definition: MaterialPropertyDefinition, selection_context: SelectionContext, requested_context: dict[str, Any] | None = None, candidate_conflict_keys: set[str] | None = None) -> dict[str, Any]:
    baseline_sel = select_from_context(selection_context, baseline.id, definition.key, requested_context=requested_context or {})
    candidate_sel = select_from_context(selection_context, candidate.id, definition.key, requested_context=requested_context or {})
    b, c = baseline_sel["selected"], candidate_sel["selected"]
    if definition.quantity_type == "boolean":
        return {
            "property_key": definition.key, "display_name": definition.display_name,
            "baseline_value": None, "candidate_value": None, "canonical_unit": None,
            "delta": None, "percentage_delta": None, "evidence_id": c.get("evidence_id") if c else None,
            "confidence": c.get("confidence") if c else None, "selected_observation_id": c.get("observation_id") if c else None,
            "selection_rationale": candidate_sel["rationale"], "applicability": c.get("applicability") if c else None,
            "alternatives_count": len(candidate_sel["alternatives"]), "conflict": bool(candidate_sel["conflict"] or definition.key in (candidate_conflict_keys or set())),
            **_base_prediction_fields("known_evidence" if c else "none"),
        }
    bv = b.get("canonical_value") if b else None
    cv = c.get("canonical_value") if c else None
    delta = cv - bv if cv is not None and bv is not None else None
    pct = (delta / bv * 100.0) if (delta is not None and bv not in (None, 0)) else None
    return {
        "property_key": definition.key, "display_name": definition.display_name,
        "baseline_value": bv, "candidate_value": cv, "canonical_unit": definition.canonical_unit,
        "delta": delta, "percentage_delta": pct, "evidence_id": c.get("evidence_id") if c else None,
        "confidence": c.get("confidence") if c else None, "selected_observation_id": c.get("observation_id") if c else None,
        "selection_rationale": candidate_sel["rationale"], "applicability": c.get("applicability") if c else None,
        "alternatives_count": len(candidate_sel["alternatives"]), "conflict": bool(candidate_sel["conflict"] or definition.key in (candidate_conflict_keys or set())),
        **_base_prediction_fields("known_evidence" if c else "none"),
    }


def _hypothesis_property_comparison(project: ReplacementProject, candidate: Candidate, definition: MaterialPropertyDefinition, selection_context: SelectionContext, prediction: PropertyPrediction | None) -> dict[str, Any]:
    baseline_sel = select_from_context(selection_context, project.baseline_material.id, definition.key, requested_context={})
    baseline = baseline_sel["selected"]
    baseline_value = baseline.get("canonical_value") if baseline and definition.quantity_type != "boolean" else None
    if prediction and prediction.status == "predicted":
        cv = prediction.canonical_value
        delta = cv - baseline_value if cv is not None and baseline_value is not None else None
        pct = delta / baseline_value * 100.0 if delta is not None and baseline_value not in (None, 0) else None
        return {
            "property_key": definition.key, "display_name": definition.display_name,
            "baseline_value": baseline_value, "candidate_value": cv, "canonical_unit": definition.canonical_unit,
            "delta": delta, "percentage_delta": pct, "evidence_id": None, "confidence": None, "selected_observation_id": None,
            "selection_rationale": ["Model prediction is shown separately from scientific observations."],
            "applicability": prediction.applicability_status, "alternatives_count": 0, "conflict": False,
            "value_origin": "model_prediction", "prediction_id": prediction.id, "model_version": prediction.model_version_id,
            "prediction_interval": {"lower": prediction.uncertainty_lower, "upper": prediction.uncertainty_upper, "unit": prediction.output_unit},
            "applicability_status": prediction.applicability_status,
        }
    return {
        "property_key": definition.key, "display_name": definition.display_name,
        "baseline_value": baseline_value, "candidate_value": None, "canonical_unit": definition.canonical_unit,
        "delta": None, "percentage_delta": None, "evidence_id": None, "confidence": None, "selected_observation_id": None,
        "selection_rationale": ["Hypothesis has no independent property evidence or applicable selected prediction."],
        "applicability": prediction.applicability_status if prediction else None, "alternatives_count": 0, "conflict": False,
        "value_origin": "model_prediction" if prediction else "none", "prediction_id": prediction.id if prediction else None,
        "model_version": prediction.model_version_id if prediction else None, "prediction_interval": None,
        "applicability_status": prediction.applicability_status if prediction else None,
    }


def evaluate_candidate(db: Session, project: ReplacementProject, candidate: Candidate, selection_context: SelectionContext | None = None, prediction_map: dict[tuple[str, str], PropertyPrediction] | None = None) -> dict[str, Any]:
    if candidate.candidate_kind == "hypothesis":
        if not candidate.hypothesis:
            raise ValueError("Hypothesis candidate is missing its hypothesis record")
        selection_context = selection_context or build_selection_context(db, [project.baseline_material.id])
        definitions = selection_context.definitions_by_key
        constraints = []
        for c in project.constraints:
            prediction = _prediction_lookup(prediction_map, candidate, c.property_key)
            constraints.append(_prediction_constraint(c, definitions.get(c.property_key), prediction))
        hard_ids = {c.id for c in project.constraints if c.hard_or_soft == "hard"}
        soft_ids = {c.id for c in project.constraints if c.hard_or_soft == "soft"}
        hard = [x for x in constraints if x["constraint_id"] in hard_ids]
        soft = [x for x in constraints if x["constraint_id"] in soft_ids]
        property_keys = sorted({c.property_key for c in project.constraints} | {o.property_key for o in project.objectives})
        comparisons = []
        for key in property_keys:
            definition = definitions.get(key)
            if definition:
                comparisons.append(_hypothesis_property_comparison(project, candidate, definition, selection_context, _prediction_lookup(prediction_map, candidate, key)))
        objective_comparisons = [{
            "objective_id": o.id, "property_key": o.property_key, "direction": o.direction, "weight": o.weight,
            "candidate_value": next((p["candidate_value"] for p in comparisons if p["property_key"] == o.property_key), None),
            "baseline_value": next((p["baseline_value"] for p in comparisons if p["property_key"] == o.property_key), None),
            "canonical_unit": definitions[o.property_key].canonical_unit if o.property_key in definitions else None,
            "status": "PREDICTED" if _prediction_lookup(prediction_map, candidate, o.property_key) else "UNKNOWN",
            "selected_observation_id": None,
        } for o in sorted(project.objectives, key=lambda x: x.priority)]
        prediction_coverage = sum(1 for key in property_keys if _prediction_lookup(prediction_map, candidate, key) is not None)
        evidence_posture = "MODEL PREDICTION + UNKNOWN — predictions are not measurements" if prediction_coverage else "UNKNOWN — NOT YET PREDICTED/TESTED"
        return {
            "candidate_id": candidate.id, "candidate_kind": "hypothesis", "material_id": None, "hypothesis_id": candidate.hypothesis.id,
            "material_name": candidate.hypothesis.display_label, "evidence_posture": evidence_posture,
            "hard_passed": sum(1 for x in hard if x["status"] == "PASS"), "hard_failed": sum(1 for x in hard if x["status"] == "FAIL"),
            "unknown": sum(1 for x in constraints if x["status"] == "UNKNOWN"), "soft_passed": sum(1 for x in soft if x["status"] == "PASS"),
            "completeness": round(sum(x["status"] != "UNKNOWN" for x in constraints) / len(constraints), 4) if constraints else 1.0,
            "constraints": constraints, "properties": comparisons, "objective_comparisons": objective_comparisons, "prediction_coverage": prediction_coverage,
        }

    if candidate.material is None:
        raise ValueError("Known-material candidate is missing material")
    selection_context = selection_context or build_selection_context(db, [project.baseline_material.id, candidate.material.id])
    definitions = selection_context.definitions_by_key
    candidate_conflict_keys = {c["property_key"] for c in detect_conflicts(db, candidate.material.id)}
    constraints = []
    for c in project.constraints:
        evidence_eval = evaluate_constraint(db, candidate.material, c, definitions, selection_context, candidate_conflict_keys)
        prediction = _prediction_lookup(prediction_map, candidate, c.property_key)
        if evidence_eval["status"] == "UNKNOWN" and prediction is not None:
            constraints.append(_prediction_constraint(c, definitions.get(c.property_key), prediction))
        else:
            constraints.append(evidence_eval)
    hard_ids = {c.id for c in project.constraints if c.hard_or_soft == "hard"}
    soft_ids = {c.id for c in project.constraints if c.hard_or_soft == "soft"}
    hard = [x for x in constraints if x["constraint_id"] in hard_ids]
    soft = [x for x in constraints if x["constraint_id"] in soft_ids]
    known = sum(1 for x in constraints if x["status"] != "UNKNOWN")
    completeness = round(known / len(constraints), 4) if constraints else 1.0
    property_keys = sorted({c.property_key for c in project.constraints} | {o.property_key for o in project.objectives})
    context_by_key: dict[str, dict[str, Any]] = {}
    for constraint in project.constraints:
        context = _selection_context(constraint.metadata_json)
        if context:
            context_by_key.setdefault(constraint.property_key, context)
    comparisons = [compare_property(db, project.baseline_material, candidate.material, definitions[k], selection_context, context_by_key.get(k), candidate_conflict_keys) for k in property_keys if k in definitions]
    by_key = {p["property_key"]: p for p in comparisons}
    # Predictions coexist with evidence; only fill a property display when evidence is absent and an explicit run was selected.
    for key in property_keys:
        p = by_key.get(key)
        pred = _prediction_lookup(prediction_map, candidate, key)
        if p and pred:
            p["prediction_id"] = pred.id
            p["model_version"] = pred.model_version_id
            p["applicability_status"] = pred.applicability_status
            p["prediction_interval"] = {"lower": pred.uncertainty_lower, "upper": pred.uncertainty_upper, "unit": pred.output_unit} if pred.status == "predicted" else None
            if p["candidate_value"] is None and pred.status == "predicted":
                p["candidate_value"] = pred.canonical_value
                p["value_origin"] = "model_prediction"
    objective_comparisons = []
    for o in sorted(project.objectives, key=lambda x: x.priority):
        p = by_key.get(o.property_key)
        objective_comparisons.append({
            "objective_id": o.id, "property_key": o.property_key, "direction": o.direction, "weight": o.weight,
            "candidate_value": p["candidate_value"] if p else None, "baseline_value": p["baseline_value"] if p else None,
            "canonical_unit": p["canonical_unit"] if p else None,
            "status": "KNOWN" if p and p["candidate_value"] is not None and p["value_origin"] == "known_evidence" else ("PREDICTED" if p and p["candidate_value"] is not None else "UNKNOWN"),
            "selected_observation_id": p.get("selected_observation_id") if p else None,
        })
    prediction_coverage = sum(1 for key in property_keys if _prediction_lookup(prediction_map, candidate, key) is not None)
    return {
        "candidate_id": candidate.id, "candidate_kind": "known_material", "material_id": candidate.material.id, "hypothesis_id": None, "material_name": candidate.material.display_name,
        "evidence_posture": "KNOWN EVIDENCE — condition-aware selection applies" + ("; model predictions shown separately" if prediction_coverage else ""),
        "hard_passed": sum(1 for x in hard if x["status"] == "PASS"), "hard_failed": sum(1 for x in hard if x["status"] == "FAIL"),
        "unknown": sum(1 for x in constraints if x["status"] == "UNKNOWN"), "soft_passed": sum(1 for x in soft if x["status"] == "PASS"),
        "completeness": completeness, "constraints": constraints, "properties": comparisons, "objective_comparisons": objective_comparisons,
        "prediction_coverage": prediction_coverage,
    }
