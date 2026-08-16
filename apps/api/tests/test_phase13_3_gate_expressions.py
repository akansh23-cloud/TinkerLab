from __future__ import annotations

import pytest

from app.services.gate_expressions import (
    PERFORMANCE_INDICES,
    GateExpressionError,
    PropertyEvidence,
    evaluate_expression,
    evaluate_gate,
)


def test_restricted_ast_blocks_function_calls():
    with pytest.raises(GateExpressionError, match="unsupported expression node"):
        evaluate_expression("__import__('os').system('echo unsafe')", {})


def test_baliga_index_is_an_expression_not_hard_coded_material_logic():
    index = PERFORMANCE_INDICES["baliga_fom"]
    value = evaluate_expression(index.expression, {"epsilon": 1.0, "mu": 2.0, "E_c": 3.0})
    assert value == pytest.approx(54.0)


def test_uncertainty_overlap_is_indeterminate_not_pass():
    result = evaluate_gate(
        expression="k",
        properties={
            "k": PropertyEvidence(
                value=155.0,
                distribution="normal",
                uncertainty=62.0,
                evidence_tier="PEER_REVIEWED",
            )
        },
        comparator=">=",
        threshold=150.0,
        samples=20_000,
        seed=1303,
    )
    assert result.status == "INDETERMINATE"
    assert result.probability_pass is not None
    assert 0.45 < result.probability_pass < 0.60


def test_clear_distribution_can_pass_blocking_gate():
    result = evaluate_gate(
        expression="k / rho",
        properties={
            "k": PropertyEvidence(500.0, "normal", 5.0, evidence_tier="MEASURED_THIS_LOT"),
            "rho": PropertyEvidence(3.2, "normal", 0.02, evidence_tier="MEASURED_THIS_LOT"),
        },
        comparator=">=",
        threshold=140.0,
        samples=10_000,
    )
    assert result.status == "PASS"
    assert result.probability_pass is not None and result.probability_pass >= 0.95


def test_predicted_only_evidence_never_clears_blocking_gate():
    result = evaluate_gate(
        expression="E_c * v_sat / (2*pi)",
        properties={
            "E_c": PropertyEvidence(3.0, "normal", 0.01, evidence_tier="PREDICTED"),
            "v_sat": PropertyEvidence(2.0, "normal", 0.01, evidence_tier="PREDICTED"),
        },
        comparator=">=",
        threshold=0.5,
        blocking=True,
        samples=5_000,
    )
    assert result.probability_pass is not None and result.probability_pass >= 0.95
    assert result.status == "EVIDENCE_INSUFFICIENT"
    assert result.predicted_only is True


def test_predicted_only_can_rank_non_blocking_objective():
    result = evaluate_gate(
        expression="E_c * v_sat / (2*pi)",
        properties={
            "E_c": PropertyEvidence(3.0, "normal", 0.01, evidence_tier="PREDICTED"),
            "v_sat": PropertyEvidence(2.0, "normal", 0.01, evidence_tier="PREDICTED"),
        },
        comparator=">=",
        threshold=0.5,
        blocking=False,
        samples=5_000,
    )
    assert result.status == "PASS"
    assert result.predicted_only is True


def test_unspecified_uncertainty_is_not_laundered_into_point_estimate():
    result = evaluate_gate(
        expression="k",
        properties={"k": PropertyEvidence(490.0, "unspecified", evidence_tier="HANDBOOK")},
        comparator=">=",
        threshold=150.0,
    )
    assert result.status == "EVIDENCE_INSUFFICIENT"
    assert result.probability_pass is None


def test_missing_property_returns_evidence_insufficient():
    result = evaluate_gate(
        expression="sigma_f * k / (E * alpha)",
        properties={
            "sigma_f": PropertyEvidence(100.0),
            "k": PropertyEvidence(200.0),
            "E": PropertyEvidence(300.0),
        },
        comparator=">=",
        threshold=1.0,
    )
    assert result.status == "EVIDENCE_INSUFFICIENT"
    assert "alpha" in result.reason


def test_deterministic_seed_reproduces_probability():
    kwargs = dict(
        expression="x",
        properties={"x": PropertyEvidence(10.0, "normal", 2.0, evidence_tier="PEER_REVIEWED")},
        comparator=">=",
        threshold=9.0,
        samples=3_000,
        seed=42,
    )
    first = evaluate_gate(**kwargs)
    second = evaluate_gate(**kwargs)
    assert first.probability_pass == second.probability_pass
