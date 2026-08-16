"""Phase 13.4 — strict mission-condition evidence resolution.

Resolution order is deliberately narrow:
1. directly applicable Phase-13 measurement at the requested conditions;
2. an explicitly registered property model inside its validity envelope;
3. EVIDENCE_INSUFFICIENT.

Unknown conditions are never silently interpreted as ambient conditions and models never extrapolate.
"""
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
    """Stable content identity for immutable property-model versions."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _model_checksum_payload(model: PropertyModelV13) -> dict[str, Any]:
    return {
        "material_id": model.material_id,
        "property_definition_id": model.property_definition_id,
        "model_key": model.model_key,
        "model_type": model.model_type,
        "equation": model.equation,
        "coefficients": model.coefficients or {},
        "coefficient_units": model.coefficient_units or {},
        "output_unit": model.output_unit,
        "validity_temperature_min_k": model.validity_temperature_min_k,
        "validity_temperature_max_k": model.validity_temperature_max_k,
        "validity_conditions": model.validity_conditions or {},
        "distribution": model.distribution,
        "uncertainty_value": model.uncertainty_value,
        "uncertainty_lower": model.uncertainty_lower,
        "uncertainty_upper": model.uncertainty_upper,
        "evidence_tier": model.evidence_tier,
        "fit_quality": model.fit_quality or {},
        "source_evidence_id": model.source_evidence_id,
        "source_record_id": model.source_record_id,
        "source_ref": model.source_ref,
        "source_kind": model.source_kind,
        "applicability_notes": model.applicability_notes,
        "version": model.version,
    }


def validate_property_model(model: PropertyModelV13) -> None:
    if not model.source_evidence_id and not model.source_record_id and not model.source_ref:
        raise ConditionResolutionError("Property model requires explicit source provenance")
    if model.validity_temperature_min_k is None or model.validity_temperature_max_k is None:
        raise ConditionResolutionError("Property model requires an explicit temperature validity range")
    if model.validity_temperature_min_k > model.validity_temperature_max_k:
        raise ConditionResolutionError("Property model temperature validity range is inverted")
    supported = {"temperature_power_law", "varshni", "temperature_table_linear"}
    if model.model_type not in supported:
        raise ConditionResolutionError(f"Unsupported property model type '{model.model_type}'")

    coefficients = model.coefficients or {}
    required = {
        "temperature_power_law": {"p_ref", "t_ref_k", "n"},
        "varshni": {"p0", "alpha", "beta"},
        "temperature_table_linear": {"points"},
    }[model.model_type]
    missing = sorted(required - set(coefficients))
    if missing:
        raise ConditionResolutionError(f"Property model is missing coefficients: {', '.join(missing)}")
    expected = property_model_checksum(_model_checksum_payload(model))
    if model.checksum != expected:
        raise ConditionResolutionError("Property model checksum does not match immutable model content")


def evaluate_property_model(model: PropertyModelV13, temperature_k: float) -> float:
    validate_property_model(model)
    low = float(model.validity_temperature_min_k)
    high = float(model.validity_temperature_max_k)
    if not low <= temperature_k <= high:
        raise ConditionResolutionError(
            f"Requested temperature {temperature_k:g} K is outside model validity range {low:g}-{high:g} K"
        )
    c = model.coefficients or {}
    if model.model_type == "temperature_power_law":
        p_ref = float(c["p_ref"])
        t_ref = float(c["t_ref_k"])
        exponent = float(c["n"])
        if t_ref <= 0 or temperature_k <= 0:
            raise ConditionResolutionError("Temperature power-law model requires positive absolute temperature")
        result = p_ref * (temperature_k / t_ref) ** exponent
    elif model.model_type == "varshni":
        p0 = float(c["p0"])
        alpha = float(c["alpha"])
        beta = float(c["beta"])
        denominator = temperature_k + beta
        if denominator == 0:
            raise ConditionResolutionError("Varshni model denominator is zero at requested temperature")
        result = p0 - alpha * temperature_k**2 / denominator
    else:
        raw_points = c["points"]
        if not isinstance(raw_points, list) or len(raw_points) < 2:
            raise ConditionResolutionError("Temperature table model requires at least two points")
        points = sorted((float(p["temperature_k"]), float(p["value"])) for p in raw_points)
        if len({t for t, _ in points}) != len(points):
            raise ConditionResolutionError("Temperature table contains duplicate temperatures")
        if temperature_k < points[0][0] or temperature_k > points[-1][0]:
            raise ConditionResolutionError("Temperature table interpolation cannot extrapolate")
        result = points[-1][1]
        for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
            if t0 <= temperature_k <= t1:
                if temperature_k == t0:
                    result = v0
                elif temperature_k == t1:
                    result = v1
                else:
                    fraction = (temperature_k - t0) / (t1 - t0)
                    result = v0 + fraction * (v1 - v0)
                break
    if not math.isfinite(result):
        raise ConditionResolutionError("Property model produced a non-finite value")
    return float(result)


def _requested_temperature(conditions: Mapping[str, Any]) -> float | None:
    value = conditions.get("temperature_k")
    return None if value is None else float(value)


def _measurement_matches(measurement: PropertyMeasurementV13, conditions: Mapping[str, Any]) -> tuple[bool, str]:
    envelope = measurement.envelope
    if envelope is None:
        return False, "measurement has no validity envelope"
    requested_t = _requested_temperature(conditions)
    if requested_t is not None:
        if envelope.temperature_status.upper() != "KNOWN" or envelope.temperature_k is None:
            return False, "measurement temperature is UNKNOWN"
        metadata = envelope.metadata_json or {}
        t_min = metadata.get("temperature_min_k")
        t_max = metadata.get("temperature_max_k")
        if t_min is not None or t_max is not None:
            lower = float(t_min if t_min is not None else envelope.temperature_k)
            upper = float(t_max if t_max is not None else envelope.temperature_k)
            if not lower <= requested_t <= upper:
                return False, "requested temperature is outside measurement validity range"
        elif not math.isclose(float(envelope.temperature_k), requested_t, rel_tol=0.0, abs_tol=1e-9):
            return False, "measurement was recorded at a different temperature"

    scalar_fields = {
        "pressure_pa": envelope.pressure_pa,
        "humidity_percent": envelope.humidity_percent,
        "strain_rate": envelope.strain_rate,
        "frequency_hz": envelope.frequency_hz,
        "field_strength_v_per_m": envelope.field_strength_v_per_m,
        "time_under_load_s": envelope.time_under_load_s,
    }
    text_fields = {
        "stress_state": envelope.stress_state,
        "atmosphere": envelope.atmosphere,
        "bias_condition": envelope.bias_condition,
        "direction": envelope.direction,
        "material_state": envelope.material_state,
    }
    for key, actual in scalar_fields.items():
        if key in conditions:
            if actual is None or not math.isclose(float(actual), float(conditions[key]), rel_tol=1e-9, abs_tol=1e-12):
                return False, f"measurement does not establish requested {key}"
    for key, actual in text_fields.items():
        if key in conditions and (actual is None or str(actual).strip().casefold() != str(conditions[key]).strip().casefold()):
            return False, f"measurement does not establish requested {key}"
    return True, "direct measurement matches requested conditions"


def _model_conditions_match(model: PropertyModelV13, conditions: Mapping[str, Any]) -> tuple[bool, str]:
    requested_t = _requested_temperature(conditions)
    if requested_t is None:
        return False, "strict property-model resolution requires temperature_k"
    if model.validity_temperature_min_k is None or model.validity_temperature_max_k is None:
        return False, "model has no explicit temperature validity range"
    if not float(model.validity_temperature_min_k) <= requested_t <= float(model.validity_temperature_max_k):
        return False, "requested temperature is outside model validity range"
    declared = model.validity_conditions or {}
    for key, requested in conditions.items():
        if key == "temperature_k":
            continue
        if key not in declared:
            return False, f"model does not establish requested {key}"
        actual = declared[key]
        if isinstance(requested, (int, float)) and isinstance(actual, (int, float)):
            if not math.isclose(float(actual), float(requested), rel_tol=1e-9, abs_tol=1e-12):
                return False, f"model validity does not match requested {key}"
        elif str(actual).strip().casefold() != str(requested).strip().casefold():
            return False, f"model validity does not match requested {key}"
    return True, "model validity envelope matches requested conditions"


def resolve_property_at_conditions(
    db: Session,
    *,
    material_id: str,
    property_definition_id: str,
    conditions: Mapping[str, Any],
) -> PropertyResolution:
    requested = dict(conditions)
    measurements = (
        db.query(PropertyMeasurementV13)
        .filter(
            PropertyMeasurementV13.material_id == material_id,
            PropertyMeasurementV13.property_definition_id == property_definition_id,
        )
        .order_by(PropertyMeasurementV13.review_required.asc(), PropertyMeasurementV13.created_at.desc())
        .all()
    )
    rejection_reasons: list[str] = []
    for measurement in measurements:
        matches, reason = _measurement_matches(measurement, requested)
        if not matches:
            rejection_reasons.append(f"measurement {measurement.id}: {reason}")
            continue
        if measurement.canonical_numeric_value is None:
            rejection_reasons.append(f"measurement {measurement.id}: no canonical numeric value")
            continue
        envelope = measurement.envelope
        validity = {
            "temperature_k": envelope.temperature_k if envelope else None,
            "temperature_status": envelope.temperature_status if envelope else "UNKNOWN",
            "metadata": envelope.metadata_json if envelope else {},
        }
        return PropertyResolution(
            status="RESOLVED",
            property_definition_id=property_definition_id,
            requested_conditions=requested,
            value=float(measurement.canonical_numeric_value),
            unit=measurement.canonical_unit,
            distribution=measurement.distribution,
            uncertainty=measurement.uncertainty_stddev or measurement.uncertainty_value,
            lower=measurement.uncertainty_lower,
            upper=measurement.uncertainty_upper,
            evidence_tier=measurement.evidence_tier,
            resolution_path="DIRECT_MEASUREMENT",
            measurement_id=measurement.id,
            source_evidence_id=measurement.evidence_id,
            source_record_id=measurement.source_record_id,
            source_ref=measurement.source_ref,
            validity=validity,
            warnings=("measurement requires review",) if measurement.review_required else (),
            reason=reason,
        )

    models = (
        db.query(PropertyModelV13)
        .filter(
            PropertyModelV13.material_id == material_id,
            PropertyModelV13.property_definition_id == property_definition_id,
            PropertyModelV13.is_active.is_(True),
        )
        .order_by(PropertyModelV13.review_required.asc(), PropertyModelV13.version.desc(), PropertyModelV13.model_key)
        .all()
    )
    for model in models:
        try:
            validate_property_model(model)
        except ConditionResolutionError as exc:
            rejection_reasons.append(f"model {model.id}: {exc}")
            continue
        matches, reason = _model_conditions_match(model, requested)
        if not matches:
            rejection_reasons.append(f"model {model.id}: {reason}")
            continue
        try:
            value = evaluate_property_model(model, float(requested["temperature_k"]))
        except ConditionResolutionError as exc:
            rejection_reasons.append(f"model {model.id}: {exc}")
            continue
        warnings: list[str] = []
        if model.review_required:
            warnings.append("property model requires review")
        if model.distribution.lower() in {"unspecified", "unknown", ""}:
            warnings.append("model has no defensible uncertainty distribution; blocking gate cannot clear")
        return PropertyResolution(
            status="RESOLVED",
            property_definition_id=property_definition_id,
            requested_conditions=requested,
            value=value,
            unit=model.output_unit,
            distribution=model.distribution,
            uncertainty=model.uncertainty_value,
            lower=model.uncertainty_lower,
            upper=model.uncertainty_upper,
            evidence_tier=model.evidence_tier,
            resolution_path="PROPERTY_MODEL",
            model_id=model.id,
            model_key=model.model_key,
            model_version=model.version,
            model_checksum=model.checksum,
            source_evidence_id=model.source_evidence_id,
            source_record_id=model.source_record_id,
            source_ref=model.source_ref,
            validity={
                "temperature_min_k": model.validity_temperature_min_k,
                "temperature_max_k": model.validity_temperature_max_k,
                "conditions": model.validity_conditions or {},
            },
            warnings=tuple(warnings),
            reason=reason,
        )

    reason = "No directly applicable measurement or valid property model exists for requested mission conditions"
    if rejection_reasons:
        reason += "; " + " | ".join(rejection_reasons[:8])
    return PropertyResolution(
        status="EVIDENCE_INSUFFICIENT",
        property_definition_id=property_definition_id,
        requested_conditions=requested,
        value=None,
        unit=None,
        distribution="unspecified",
        uncertainty=None,
        lower=None,
        upper=None,
        evidence_tier=None,
        resolution_path="EVIDENCE_INSUFFICIENT",
        reason=reason,
    )


def resolve_and_evaluate_gate(
    db: Session,
    *,
    material_id: str,
    property_bindings: Mapping[str, str],
    conditions: Mapping[str, Any],
    expression: str,
    comparator: str,
    threshold: float,
    threshold_upper: float | None = None,
    blocking: bool = True,
    samples: int = 10_000,
    pass_probability: float = 0.95,
    fail_probability: float = 0.05,
    seed: int = 13_004,
) -> StrictGateEvaluation:
    resolutions = {
        name: resolve_property_at_conditions(
            db,
            material_id=material_id,
            property_definition_id=property_id,
            conditions=conditions,
        )
        for name, property_id in sorted(property_bindings.items())
    }
    unresolved = [name for name, resolution in resolutions.items() if resolution.status != "RESOLVED"]
    if unresolved:
        gate = GateEvaluation(
            status="EVIDENCE_INSUFFICIENT",
            probability_pass=None,
            sample_count=0,
            expression=expression,
            comparator=comparator,
            threshold=threshold,
            threshold_upper=threshold_upper,
            contributing_properties=tuple(sorted(property_bindings)),
            predicted_only=False,
            reason="Mission-condition evidence unresolved for: " + ", ".join(unresolved),
        )
        return StrictGateEvaluation("PHASE13_STRICT_CONDITION_RESOLVED", gate, resolutions)

    evidence = {
        name: PropertyEvidence(
            value=resolution.value,
            distribution=resolution.distribution,
            uncertainty=resolution.uncertainty,
            lower=resolution.lower,
            upper=resolution.upper,
            evidence_tier=resolution.evidence_tier,
        )
        for name, resolution in resolutions.items()
    }
    gate = evaluate_gate(
        expression=expression,
        properties=evidence,
        comparator=comparator,
        threshold=threshold,
        threshold_upper=threshold_upper,
        blocking=blocking,
        samples=samples,
        pass_probability=pass_probability,
        fail_probability=fail_probability,
        seed=seed,
    )
    return StrictGateEvaluation("PHASE13_STRICT_CONDITION_RESOLVED", gate, resolutions)
