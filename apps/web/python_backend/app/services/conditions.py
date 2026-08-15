from __future__ import annotations

from typing import Any

from app.services.units import UnitError, convert, ensure_compatible


def validate_condition_values(data: Any) -> None:
    """Validate typed condition values without deciding whether a property requires them."""
    if data is None:
        return
    temp_value = getattr(data, "temperature_value", None)
    temp_unit = getattr(data, "temperature_unit", None)
    pressure_value = getattr(data, "pressure_value", None)
    pressure_unit = getattr(data, "pressure_unit", None)
    freq_value = getattr(data, "frequency_value", None)
    freq_unit = getattr(data, "frequency_unit", None)
    humidity = getattr(data, "humidity_percent", None)
    strain_rate = getattr(data, "strain_rate", None)
    for value, unit, canonical, label in (
        (temp_value, temp_unit, "K", "temperature"),
        (pressure_value, pressure_unit, "Pa", "pressure"),
        (freq_value, freq_unit, "Hz", "frequency"),
    ):
        if value is None:
            continue
        if unit is None:
            raise UnitError(f"{label}_value requires an explicit {label}_unit")
        ensure_compatible(str(unit), canonical)
    if humidity is not None and not 0 <= humidity <= 100:
        raise UnitError("humidity_percent must be between 0 and 100")
    if strain_rate is not None and strain_rate < 0:
        raise UnitError("strain_rate must be non-negative")


def condition_to_dict(condition: Any | None) -> dict[str, Any]:
    if condition is None:
        return {}
    if hasattr(condition, "model_dump"):
        raw = condition.model_dump(mode="json")
    else:
        raw = {
            "temperature_value": getattr(condition, "temperature_value", None),
            "temperature_unit": getattr(condition, "temperature_unit", None),
            "pressure_value": getattr(condition, "pressure_value", None),
            "pressure_unit": getattr(condition, "pressure_unit", None),
            "humidity_percent": getattr(condition, "humidity_percent", None),
            "strain_rate": getattr(condition, "strain_rate", None),
            "sample_orientation": getattr(condition, "sample_orientation", None),
            "frequency_value": getattr(condition, "frequency_value", None),
            "frequency_unit": getattr(condition, "frequency_unit", None),
            "material_state": getattr(condition, "material_state", None),
        }
    return {k: v for k, v in raw.items() if v is not None and k != "metadata"}


def _numeric_match(obs_value: float | None, obs_unit: str | None, target_value: float, target_unit: str) -> tuple[str, str]:
    if obs_value is None or obs_unit is None:
        return "unknown", "condition not reported"
    try:
        normalized = convert(obs_value, obs_unit, target_unit)
    except UnitError:
        return "mismatch", "condition unit incompatible"
    tolerance = max(abs(target_value) * 1e-6, 1e-9)
    return ("exact", "condition matches") if abs(normalized - target_value) <= tolerance else ("mismatch", "condition differs")


def compare_condition_context(observation_condition: Any | None, requested: dict[str, Any]) -> tuple[str, list[str], int]:
    """Return applicability class, reasons and deterministic score.

    A reported contradictory condition is inapplicable. Missing reported conditions remain usable as
    fallback but rank below exact matches; this is intentionally conservative and transparent.
    """
    if not requested:
        completeness = 0
        if observation_condition is not None:
            completeness = sum(v is not None for k, v in condition_to_dict(observation_condition).items())
        return "unspecified_context", ["no project condition context supplied"], completeness
    reasons: list[str] = []
    exact = 0
    unknown = 0
    checks = [
        ("temperature", "temperature_value", "temperature_unit"),
        ("pressure", "pressure_value", "pressure_unit"),
        ("frequency", "frequency_value", "frequency_unit"),
    ]
    for label, value_key, unit_key in checks:
        req = requested.get(label)
        if req is None:
            continue
        if isinstance(req, dict):
            req_value, req_unit = req.get("value"), req.get("unit")
        else:
            continue
        result, reason = _numeric_match(
            getattr(observation_condition, value_key, None) if observation_condition else None,
            getattr(observation_condition, unit_key, None) if observation_condition else None,
            float(req_value) if req_value is not None else 0.0, str(req_unit),
        )
        reasons.append(f"{label}: {reason}")
        if result == "mismatch":
            return "inapplicable", reasons, -100
        if result == "exact":
            exact += 1
        else:
            unknown += 1
    simple = [
        ("humidity_percent", "humidity_percent"),
        ("strain_rate", "strain_rate"),
        ("sample_orientation", "sample_orientation"),
        ("material_state", "material_state"),
    ]
    for req_key, attr in simple:
        if req_key not in requested:
            continue
        target = requested[req_key]
        observed = getattr(observation_condition, attr, None) if observation_condition else None
        if observed is None:
            unknown += 1; reasons.append(f"{req_key}: condition not reported"); continue
        if isinstance(target, (int, float)) and isinstance(observed, (int, float)):
            tol = max(abs(float(target)) * 1e-6, 1e-9)
            matches = abs(float(observed) - float(target)) <= tol
        else:
            matches = str(observed).strip().casefold() == str(target).strip().casefold()
        if not matches:
            reasons.append(f"{req_key}: condition differs")
            return "inapplicable", reasons, -100
        exact += 1; reasons.append(f"{req_key}: condition matches")
    if unknown:
        return "partial", reasons, exact * 10 - unknown
    return "exact", reasons, exact * 10 + 100
