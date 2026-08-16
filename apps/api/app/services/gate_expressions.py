"""Phase 13.3 — safe engineering gate expressions with uncertainty propagation.

This module deliberately does not resolve evidence at mission conditions; Phase 13.4 owns that
step. It accepts only already-resolved property evidence. A caller that feeds a 300 K handbook
value into a 525 K gate has violated the contract and must be rejected by the condition resolver.

No Python ``eval`` is used. Expressions are parsed into a restricted AST consisting only of named
properties, numeric constants and arithmetic operators. Function calls, attribute access,
subscripts, comprehensions and arbitrary names are rejected.
"""
from __future__ import annotations

import ast
import math
import random
from collections.abc import Mapping
from dataclasses import dataclass


class GateExpressionError(ValueError):
    """Raised when a gate expression is unsafe or physically/evidentially unusable."""


@dataclass(frozen=True)
class PropertyEvidence:
    """One condition-resolved scalar distribution supplied to an engineering expression."""

    value: float | None
    distribution: str = "point"
    uncertainty: float | None = None
    lower: float | None = None
    upper: float | None = None
    evidence_tier: str | None = None


@dataclass(frozen=True)
class GateEvaluation:
    status: str
    probability_pass: float | None
    sample_count: int
    expression: str
    comparator: str
    threshold: float
    threshold_upper: float | None
    contributing_properties: tuple[str, ...]
    predicted_only: bool
    reason: str


@dataclass(frozen=True)
class PerformanceIndex:
    key: str
    display_name: str
    expression: str
    function: str
    reference: str


PERFORMANCE_INDICES: dict[str, PerformanceIndex] = {
    "light_stiff_beam": PerformanceIndex(
        "light_stiff_beam", "Light stiff beam", "E**0.5 / rho", "maximize stiffness at low mass",
        "Ashby material-selection performance index",
    ),
    "light_strong_beam": PerformanceIndex(
        "light_strong_beam", "Light strong beam", "sigma_y**(2/3) / rho", "maximize strength at low mass",
        "Ashby material-selection performance index",
    ),
    "thermal_shock_resistance": PerformanceIndex(
        "thermal_shock_resistance", "Thermal shock resistance", "sigma_f * k / (E * alpha)",
        "resist fracture under thermal gradients", "classical thermal-shock material index",
    ),
    "baliga_fom": PerformanceIndex(
        "baliga_fom", "Baliga unipolar power-device FOM", "epsilon * mu * E_c**3",
        "minimize unipolar conduction loss at blocking voltage", "Baliga power semiconductor figure of merit",
    ),
    "johnson_fom": PerformanceIndex(
        "johnson_fom", "Johnson high-frequency FOM", "E_c * v_sat / (2*pi)",
        "maximize high-field switching frequency", "Johnson semiconductor figure of merit",
    ),
    "heat_spreader_mass_limited": PerformanceIndex(
        "heat_spreader_mass_limited", "Mass-limited heat spreader", "k / rho",
        "maximize heat transport per unit mass", "Ashby-style thermal performance index",
    ),
    "spring_energy_storage": PerformanceIndex(
        "spring_energy_storage", "Spring energy storage", "sigma_y**2 / E",
        "maximize elastic energy stored before yield", "Ashby material-selection performance index",
    ),
}

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)
_RESERVED = {"pi": math.pi, "e": math.e}
_MAX_POWER = 8.0


def _parse(expression: str) -> tuple[ast.Expression, tuple[str, ...]]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise GateExpressionError(f"Invalid gate expression syntax: {exc.msg}") from exc

    names: set[str] = set()
    allowed_nodes = (ast.Expression, ast.Load, ast.Constant, ast.Name, ast.BinOp, ast.UnaryOp)
    for node in ast.walk(tree):
        if isinstance(node, allowed_nodes):
            pass
        elif isinstance(node, _ALLOWED_BINOPS + _ALLOWED_UNARY):
            pass
        else:
            raise GateExpressionError(f"Unsafe or unsupported expression node: {type(node).__name__}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float)):
            raise GateExpressionError("Only numeric constants are permitted in gate expressions")
        if isinstance(node, ast.Name) and node.id not in _RESERVED:
            if node.id.startswith("_"):
                raise GateExpressionError("Private or magic names are not permitted")
            names.add(node.id)
    return tree, tuple(sorted(names))


def _eval_node(node: ast.AST, values: Mapping[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, values)
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in _RESERVED:
            return float(_RESERVED[node.id])
        if node.id not in values:
            raise GateExpressionError(f"Expression property '{node.id}' has no resolved evidence")
        return float(values[node.id])
    if isinstance(node, ast.UnaryOp):
        value = _eval_node(node.operand, values)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, values)
        right = _eval_node(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise GateExpressionError("Gate expression division by zero")
            return left / right
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_POWER:
                raise GateExpressionError(f"Power magnitude exceeds safe limit {_MAX_POWER:g}")
            result = left**right
            if isinstance(result, complex) or not math.isfinite(float(result)):
                raise GateExpressionError("Gate expression produced a non-real or non-finite value")
            return float(result)
    raise GateExpressionError(f"Unsupported expression node: {type(node).__name__}")


def evaluate_expression(expression: str, values: Mapping[str, float]) -> float:
    """Evaluate a restricted arithmetic expression for one deterministic sample."""
    tree, _ = _parse(expression)
    result = _eval_node(tree, values)
    if not math.isfinite(result):
        raise GateExpressionError("Gate expression produced a non-finite value")
    return result


def _sample(evidence: PropertyEvidence, rng: random.Random) -> float:
    if evidence.value is None:
        raise GateExpressionError("Resolved property evidence has no numeric value")
    distribution = evidence.distribution.lower()
    if distribution == "point":
        return float(evidence.value)
    if distribution == "normal":
        if evidence.uncertainty is None or evidence.uncertainty <= 0:
            raise GateExpressionError("Normal evidence requires a positive standard deviation")
        return rng.gauss(float(evidence.value), float(evidence.uncertainty))
    if distribution == "uniform":
        if evidence.lower is None or evidence.upper is None or evidence.lower >= evidence.upper:
            raise GateExpressionError("Uniform evidence requires lower < upper")
        return rng.uniform(float(evidence.lower), float(evidence.upper))
    if distribution == "lognormal":
        if evidence.value <= 0 or evidence.uncertainty is None or evidence.uncertainty <= 0:
            raise GateExpressionError("Lognormal evidence requires positive mean and spread")
        variance = float(evidence.uncertainty) ** 2
        mean = float(evidence.value)
        sigma2 = math.log1p(variance / (mean * mean))
        mu = math.log(mean) - sigma2 / 2
        return rng.lognormvariate(mu, math.sqrt(sigma2))
    if distribution in {"unspecified", "unknown", ""}:
        raise GateExpressionError("Evidence uncertainty distribution is unspecified")
    raise GateExpressionError(f"Unsupported evidence distribution '{evidence.distribution}'")


def _passes(value: float, comparator: str, threshold: float, upper: float | None) -> bool:
    if comparator == ">=":
        return value >= threshold
    if comparator == ">":
        return value > threshold
    if comparator == "<=":
        return value <= threshold
    if comparator == "<":
        return value < threshold
    if comparator == "range":
        if upper is None:
            raise GateExpressionError("Range gate requires threshold_upper")
        return threshold <= value <= upper
    raise GateExpressionError(f"Unsupported gate comparator '{comparator}'")


def evaluate_gate(
    *,
    expression: str,
    properties: Mapping[str, PropertyEvidence],
    comparator: str,
    threshold: float,
    threshold_upper: float | None = None,
    blocking: bool = True,
    samples: int = 10_000,
    pass_probability: float = 0.95,
    fail_probability: float = 0.05,
    seed: int = 13_003,
) -> GateEvaluation:
    """Evaluate an engineering gate with deterministic Monte Carlo uncertainty propagation.

    PASS means at least ``pass_probability`` of the represented evidence distribution satisfies the
    gate. FAIL means no more than ``fail_probability`` satisfies it. Everything in between is
    INDETERMINATE. If uncertainty is not represented honestly, the result is EVIDENCE_INSUFFICIENT.

    Tier-6 PREDICTED evidence may rank candidates for testing but cannot, by itself, clear a blocking
    gate. This enforcement lives here so UI or API callers cannot accidentally bypass it.
    """
    if samples < 100:
        raise GateExpressionError("Monte Carlo sample count must be at least 100")
    if not 0 < fail_probability < pass_probability < 1:
        raise GateExpressionError("Probability thresholds must satisfy 0 < fail < pass < 1")

    tree, names = _parse(expression)
    missing = [name for name in names if name not in properties]
    if missing:
        return GateEvaluation(
            "EVIDENCE_INSUFFICIENT", None, 0, expression, comparator, threshold, threshold_upper,
            names, False, f"Missing resolved evidence for: {', '.join(missing)}",
        )

    predicted_only = bool(names) and all(
        str(properties[name].evidence_tier or "").upper() == "PREDICTED" for name in names
    )

    for name in names:
        evidence = properties[name]
        if evidence.value is None:
            return GateEvaluation(
                "EVIDENCE_INSUFFICIENT", None, 0, expression, comparator, threshold, threshold_upper,
                names, predicted_only, f"Property '{name}' has no resolved numeric value",
            )
        if evidence.distribution.lower() in {"unspecified", "unknown", ""}:
            return GateEvaluation(
                "EVIDENCE_INSUFFICIENT", None, 0, expression, comparator, threshold, threshold_upper,
                names, predicted_only, f"Property '{name}' has no defensible uncertainty distribution",
            )

    rng = random.Random(seed)
    passed = 0
    valid = 0
    for _ in range(samples):
        values = {name: _sample(properties[name], rng) for name in names}
        try:
            result = _eval_node(tree, values)
        except (OverflowError, ValueError, GateExpressionError):
            continue
        if math.isfinite(result):
            valid += 1
            passed += int(_passes(result, comparator, threshold, threshold_upper))

    if valid < max(100, int(samples * 0.95)):
        return GateEvaluation(
            "EVIDENCE_INSUFFICIENT", None, valid, expression, comparator, threshold, threshold_upper,
            names, predicted_only, "Too many Monte Carlo samples produced invalid/non-finite physics",
        )

    probability = passed / valid
    if probability >= pass_probability:
        status = "PASS"
    elif probability <= fail_probability:
        status = "FAIL"
    else:
        status = "INDETERMINATE"

    if blocking and predicted_only and status == "PASS":
        return GateEvaluation(
            "EVIDENCE_INSUFFICIENT", probability, valid, expression, comparator, threshold,
            threshold_upper, names, True,
            "Blocking gate is supported only by PREDICTED evidence; prediction may rank testing but cannot clear the gate",
        )

    return GateEvaluation(
        status, probability, valid, expression, comparator, threshold, threshold_upper, names,
        predicted_only, f"Monte Carlo P(pass)={probability:.6f} from {valid} valid samples",
    )
