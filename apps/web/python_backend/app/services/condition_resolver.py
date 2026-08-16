"""Vercel runtime mirror of Phase 13.4 strict mission-condition resolution."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.evidence_engine import PropertyMeasurementV13
from app.models.property_models import PropertyModelV13
from app.services.gate_expressions import GateEvaluation, PropertyEvidence, evaluate_gate


class ConditionResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class PropertyResolution:
    status: str
    property_definition_id: str
    requested_conditions: dict[str, Any]
    value: float | None
    unit: str | None
    distribution: str
    uncertainty: float | None
    lower: float | None
    upper: float | None
    evidence_tier: str | None
    resolution_path: str
    measurement_id: str | None = None
    model_id: str | None = None
    model_key: str | None = None
    model_version: int | None = None
    model_checksum: str | None = None
    source_evidence_id: str | None = None
    source_record_id: str | None = None
    source_ref: str | None = None
    validity: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def audit_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrictGateEvaluation:
    evaluation_mode: str
    gate: GateEvaluation
    resolutions: dict[str, PropertyResolution]
    legacy_adapter_used: bool = False


def property_model_checksum(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _model_checksum_payload(model: PropertyModelV13) -> dict[str, Any]:
    return {
        "material_id": model.material_id, "property_definition_id": model.property_definition_id,
        "model_key": model.model_key, "model_type": model.model_type, "equation": model.equation,
        "coefficients": model.coefficients or {}, "coefficient_units": model.coefficient_units or {},
        "output_unit": model.output_unit, "validity_temperature_min_k": model.validity_temperature_min_k,
        "validity_temperature_max_k": model.validity_temperature_max_k,
        "validity_conditions": model.validity_conditions or {}, "distribution": model.distribution,
        "uncertainty_value": model.uncertainty_value, "uncertainty_lower": model.uncertainty_lower,
        "uncertainty_upper": model.uncertainty_upper, "evidence_tier": model.evidence_tier,
        "fit_quality": model.fit_quality or {}, "source_evidence_id": model.source_evidence_id,
        "source_record_id": model.source_record_id, "source_ref": model.source_ref,
        "source_kind": model.source_kind, "applicability_notes": model.applicability_notes,
        "version": model.version,
    }


def validate_property_model(model: PropertyModelV13) -> None:
    if not model.source_evidence_id and not model.source_record_id and not model.source_ref:
        raise ConditionResolutionError("Property model requires explicit source provenance")
    if model.validity_temperature_min_k is None or model.validity_temperature_max_k is None:
        raise ConditionResolutionError("Property model requires an explicit temperature validity range")
    if model.validity_temperature_min_k > model.validity_temperature_max_k:
        raise ConditionResolutionError("Property model temperature validity range is inverted")
    required = {
        "temperature_power_law": {"p_ref", "t_ref_k", "n"},
        "varshni": {"p0", "alpha", "beta"},
        "temperature_table_linear": {"points"},
    }
    if model.model_type not in required:
        raise ConditionResolutionError(f"Unsupported property model type '{model.model_type}'")
    missing = sorted(required[model.model_type] - set(model.coefficients or {}))
    if missing:
        raise ConditionResolutionError(f"Property model is missing coefficients: {', '.join(missing)}")
    if model.checksum != property_model_checksum(_model_checksum_payload(model)):
        raise ConditionResolutionError("Property model checksum does not match immutable model content")


def evaluate_property_model(model: PropertyModelV13, temperature_k: float) -> float:
    validate_property_model(model)
    low, high = float(model.validity_temperature_min_k), float(model.validity_temperature_max_k)
    if not low <= temperature_k <= high:
        raise ConditionResolutionError(f"Requested temperature {temperature_k:g} K is outside model validity range {low:g}-{high:g} K")
    c = model.coefficients or {}
    if model.model_type == "temperature_power_law":
        if float(c["t_ref_k"]) <= 0 or temperature_k <= 0:
            raise ConditionResolutionError("Temperature power-law model requires positive absolute temperature")
        result = float(c["p_ref"]) * (temperature_k / float(c["t_ref_k"])) ** float(c["n"])
    elif model.model_type == "varshni":
        denominator = temperature_k + float(c["beta"])
        if denominator == 0:
            raise ConditionResolutionError("Varshni model denominator is zero at requested temperature")
        result = float(c["p0"]) - float(c["alpha"]) * temperature_k**2 / denominator
    else:
        raw = c["points"]
        if not isinstance(raw, list) or len(raw) < 2:
            raise ConditionResolutionError("Temperature table model requires at least two points")
        points = sorted((float(p["temperature_k"]), float(p["value"])) for p in raw)
        if len({t for t, _ in points}) != len(points):
            raise ConditionResolutionError("Temperature table contains duplicate temperatures")
        if temperature_k < points[0][0] or temperature_k > points[-1][0]:
            raise ConditionResolutionError("Temperature table interpolation cannot extrapolate")
        result = points[-1][1]
        for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
            if t0 <= temperature_k <= t1:
                result = v0 if temperature_k == t0 else v1 if temperature_k == t1 else v0 + (temperature_k-t0)/(t1-t0)*(v1-v0)
                break
    if not math.isfinite(result):
        raise ConditionResolutionError("Property model produced a non-finite value")
    return float(result)


def _measurement_matches(m: PropertyMeasurementV13, conditions: Mapping[str, Any]) -> tuple[bool, str]:
    e = m.envelope
    if e is None:
        return False, "measurement has no validity envelope"
    if "temperature_k" in conditions:
        t = float(conditions["temperature_k"])
        if e.temperature_status.upper() != "KNOWN" or e.temperature_k is None:
            return False, "measurement temperature is UNKNOWN"
        meta = e.metadata_json or {}; lo = meta.get("temperature_min_k"); hi = meta.get("temperature_max_k")
        if lo is not None or hi is not None:
            if not float(lo if lo is not None else e.temperature_k) <= t <= float(hi if hi is not None else e.temperature_k):
                return False, "requested temperature is outside measurement validity range"
        elif not math.isclose(float(e.temperature_k), t, rel_tol=0.0, abs_tol=1e-9):
            return False, "measurement was recorded at a different temperature"
    numeric = {"pressure_pa": e.pressure_pa, "humidity_percent": e.humidity_percent, "strain_rate": e.strain_rate,
               "frequency_hz": e.frequency_hz, "field_strength_v_per_m": e.field_strength_v_per_m, "time_under_load_s": e.time_under_load_s}
    text = {"stress_state": e.stress_state, "atmosphere": e.atmosphere, "bias_condition": e.bias_condition,
            "direction": e.direction, "material_state": e.material_state}
    for key, actual in numeric.items():
        if key in conditions and (actual is None or not math.isclose(float(actual), float(conditions[key]), rel_tol=1e-9, abs_tol=1e-12)):
            return False, f"measurement does not establish requested {key}"
    for key, actual in text.items():
        if key in conditions and (actual is None or str(actual).strip().casefold() != str(conditions[key]).strip().casefold()):
            return False, f"measurement does not establish requested {key}"
    return True, "direct measurement matches requested conditions"


def _model_matches(model: PropertyModelV13, conditions: Mapping[str, Any]) -> tuple[bool, str]:
    if "temperature_k" not in conditions:
        return False, "strict property-model resolution requires temperature_k"
    t = float(conditions["temperature_k"])
    if model.validity_temperature_min_k is None or model.validity_temperature_max_k is None or not float(model.validity_temperature_min_k) <= t <= float(model.validity_temperature_max_k):
        return False, "requested temperature is outside model validity range"
    declared = model.validity_conditions or {}
    for key, requested in conditions.items():
        if key == "temperature_k": continue
        if key not in declared: return False, f"model does not establish requested {key}"
        actual = declared[key]
        if isinstance(requested, (int, float)) and isinstance(actual, (int, float)):
            if not math.isclose(float(actual), float(requested), rel_tol=1e-9, abs_tol=1e-12): return False, f"model validity does not match requested {key}"
        elif str(actual).strip().casefold() != str(requested).strip().casefold(): return False, f"model validity does not match requested {key}"
    return True, "model validity envelope matches requested conditions"


def resolve_property_at_conditions(db: Session, *, material_id: str, property_definition_id: str, conditions: Mapping[str, Any]) -> PropertyResolution:
    requested = dict(conditions); rejected: list[str] = []
    rows = db.query(PropertyMeasurementV13).filter(PropertyMeasurementV13.material_id == material_id, PropertyMeasurementV13.property_definition_id == property_definition_id).order_by(PropertyMeasurementV13.review_required.asc(), PropertyMeasurementV13.created_at.desc()).all()
    for m in rows:
        ok, reason = _measurement_matches(m, requested)
        if not ok: rejected.append(f"measurement {m.id}: {reason}"); continue
        if m.canonical_numeric_value is None: rejected.append(f"measurement {m.id}: no canonical numeric value"); continue
        e = m.envelope
        return PropertyResolution("RESOLVED", property_definition_id, requested, float(m.canonical_numeric_value), m.canonical_unit, m.distribution, m.uncertainty_stddev or m.uncertainty_value, m.uncertainty_lower, m.uncertainty_upper, m.evidence_tier, "DIRECT_MEASUREMENT", measurement_id=m.id, source_evidence_id=m.evidence_id, source_record_id=m.source_record_id, source_ref=m.source_ref, validity={"temperature_k": e.temperature_k if e else None, "temperature_status": e.temperature_status if e else "UNKNOWN", "metadata": e.metadata_json if e else {}}, warnings=("measurement requires review",) if m.review_required else (), reason=reason)
    models = db.query(PropertyModelV13).filter(PropertyModelV13.material_id == material_id, PropertyModelV13.property_definition_id == property_definition_id, PropertyModelV13.is_active.is_(True)).order_by(PropertyModelV13.review_required.asc(), PropertyModelV13.version.desc(), PropertyModelV13.model_key).all()
    for model in models:
        try: validate_property_model(model)
        except ConditionResolutionError as exc: rejected.append(f"model {model.id}: {exc}"); continue
        ok, reason = _model_matches(model, requested)
        if not ok: rejected.append(f"model {model.id}: {reason}"); continue
        try: value = evaluate_property_model(model, float(requested["temperature_k"]))
        except ConditionResolutionError as exc: rejected.append(f"model {model.id}: {exc}"); continue
        warnings = (["property model requires review"] if model.review_required else []) + (["model has no defensible uncertainty distribution; blocking gate cannot clear"] if model.distribution.lower() in {"unspecified", "unknown", ""} else [])
        return PropertyResolution("RESOLVED", property_definition_id, requested, value, model.output_unit, model.distribution, model.uncertainty_value, model.uncertainty_lower, model.uncertainty_upper, model.evidence_tier, "PROPERTY_MODEL", model_id=model.id, model_key=model.model_key, model_version=model.version, model_checksum=model.checksum, source_evidence_id=model.source_evidence_id, source_record_id=model.source_record_id, source_ref=model.source_ref, validity={"temperature_min_k": model.validity_temperature_min_k, "temperature_max_k": model.validity_temperature_max_k, "conditions": model.validity_conditions or {}}, warnings=tuple(warnings), reason=reason)
    reason = "No directly applicable measurement or valid property model exists for requested mission conditions"
    if rejected: reason += "; " + " | ".join(rejected[:8])
    return PropertyResolution("EVIDENCE_INSUFFICIENT", property_definition_id, requested, None, None, "unspecified", None, None, None, None, "EVIDENCE_INSUFFICIENT", reason=reason)


def resolve_and_evaluate_gate(db: Session, *, material_id: str, property_bindings: Mapping[str, str], conditions: Mapping[str, Any], expression: str, comparator: str, threshold: float, threshold_upper: float | None = None, blocking: bool = True, samples: int = 10_000, pass_probability: float = 0.95, fail_probability: float = 0.05, seed: int = 13_004) -> StrictGateEvaluation:
    resolutions = {name: resolve_property_at_conditions(db, material_id=material_id, property_definition_id=pid, conditions=conditions) for name, pid in sorted(property_bindings.items())}
    unresolved = [name for name, r in resolutions.items() if r.status != "RESOLVED"]
    if unresolved:
        gate = GateEvaluation("EVIDENCE_INSUFFICIENT", None, 0, expression, comparator, threshold, threshold_upper, tuple(sorted(property_bindings)), False, "Mission-condition evidence unresolved for: " + ", ".join(unresolved))
        return StrictGateEvaluation("PHASE13_STRICT_CONDITION_RESOLVED", gate, resolutions)
    props = {name: PropertyEvidence(r.value, r.distribution, r.uncertainty, r.lower, r.upper, r.evidence_tier) for name, r in resolutions.items()}
    gate = evaluate_gate(expression=expression, properties=props, comparator=comparator, threshold=threshold, threshold_upper=threshold_upper, blocking=blocking, samples=samples, pass_probability=pass_probability, fail_probability=fail_probability, seed=seed)
    return StrictGateEvaluation("PHASE13_STRICT_CONDITION_RESOLVED", gate, resolutions)
