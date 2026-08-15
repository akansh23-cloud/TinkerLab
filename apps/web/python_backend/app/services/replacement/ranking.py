"""Phase 10 — Transparent ranking, Pareto analysis and sensitivity.

Ranking is the most dangerous feature in a material-selection tool, because a single number invites
the reader to stop thinking. Three structural decisions keep it honest:

  1. **Hierarchical, not scalar.** Definitive failures are eliminated first, unresolved candidates
     are separated second, and only then are eligible candidates scored. A blocked candidate can
     never out-rank an eligible one by being cheap.
  2. **Every factor is returned.** Rank, each normalized factor, each weight, the excluded
     dimensions and the hard blockers all travel with the result. The arithmetic is reproducible.
  3. **Pareto before preference.** When several candidates are non-dominated, that fact is reported
     rather than resolved by whichever weight vector happened to be configured.

Normalization is min-max across the ranked set, which means a score is a *relative* position within
this program's candidates, not an absolute quality. A dimension with no evidence is excluded from
that candidate's score and named in `excluded_dimensions` — it is never imputed as 0.5 or as zero.
"""

from __future__ import annotations

from typing import Any

from app.domain.enums import (
    CandidateEligibility,
    MatrixCellStatus,
    RankingObjectiveKey,
    RankingStability,
    RequirementCriticality,
)
from app.services.replacement.context import CandidateView, PortfolioContext
from app.services.replacement.coverage import coverage_for_candidate

RANKING_METHODOLOGY = "candidate-ranking-v1"
PARETO_METHODOLOGY = "pareto-front-v1"
SENSITIVITY_METHODOLOGY = "ranking-sensitivity-v1"

# Every objective is expressed as "higher is better" *after* normalization, so cost and other
# minimize-objectives are inverted once, here, rather than in each consumer.
OBJECTIVE_DIRECTION: dict[str, str] = {
    RankingObjectiveKey.PERFORMANCE_MARGIN: "maximize",
    RankingObjectiveKey.INDUSTRIAL_VIABILITY: "maximize",
    RankingObjectiveKey.COST: "minimize",
    RankingObjectiveKey.SUPPLY_SECURITY: "maximize",
    RankingObjectiveKey.MANUFACTURING_FIT: "maximize",
    RankingObjectiveKey.SUSTAINABILITY: "maximize",
    RankingObjectiveKey.EVIDENCE_CONFIDENCE: "maximize",
}

# Industrial dimension states carry an ordinal meaning that the industrial engine already defines.
# Reusing it here keeps one interpretation of "partial" in the system.
INDUSTRIAL_STATE_VALUE: dict[str, float] = {"pass": 1.0, "partial": 0.5, "fail": 0.0}

INDUSTRIAL_DIMENSION_FOR_OBJECTIVE: dict[str, str] = {
    RankingObjectiveKey.COST: "economic_feasibility",
    RankingObjectiveKey.SUPPLY_SECURITY: "supply_resilience",
    RankingObjectiveKey.MANUFACTURING_FIT: "manufacturing_compatibility",
    RankingObjectiveKey.SUSTAINABILITY: "environmental_evidence",
}

RANKING_NOTE = (
    "Ranking applies only to candidates that are already eligible. A rank is a relative position "
    "within this program under the stated weights; it is not a quality score and not a probability."
)


def _performance_margin(context: PortfolioContext, view: CandidateView) -> float | None:
    """Fraction of gating requirements that PASS, weighted toward the most critical ones.

    This is a coarse but honest performance signal: it measures how much of what the application
    actually demands is currently demonstrated, using only requirement outcomes the canonical
    evaluator produced. Requirements with no verdict are excluded from both numerator and
    denominator, so absence of evidence does not read as poor performance.
    """
    rows = [row for row in coverage_for_candidate(context, view) if row["is_gating"]]
    weights = {RequirementCriticality.BLOCKING: 2.0, RequirementCriticality.CRITICAL: 1.0}
    total = passed = 0.0
    for row in rows:
        status = str(row["governing_status"])
        if status not in {MatrixCellStatus.PASS, MatrixCellStatus.FAIL}:
            continue
        weight = weights.get(str(row["criticality"]), 1.0)
        total += weight
        if status == MatrixCellStatus.PASS:
            passed += weight
    if total <= 0:
        return None
    return round(passed / total, 6)


def _evidence_confidence(context: PortfolioContext, view: CandidateView) -> float | None:
    """Mean evidence coverage across gating requirements — availability, never success."""
    rows = [row for row in coverage_for_candidate(context, view) if row["is_gating"]]
    if not rows:
        return None
    scores = [float(row["coverage_score"]) for row in rows]
    return round(sum(scores) / len(scores), 6)


def raw_objectives(context: PortfolioContext, view: CandidateView) -> dict[str, float | None]:
    """Raw (un-normalized, direction-native) objective values. None means genuinely unknown."""
    industrial = context.industrial_for(view)
    dimension_states = industrial.get("dimension_states") or {}

    values: dict[str, float | None] = {
        RankingObjectiveKey.PERFORMANCE_MARGIN.value: _performance_margin(context, view),
        RankingObjectiveKey.EVIDENCE_CONFIDENCE.value: _evidence_confidence(context, view),
    }

    composite = industrial.get("composite_score")
    if composite is None:
        scored = [
            INDUSTRIAL_STATE_VALUE[str(state)]
            for state in dimension_states.values() if str(state) in INDUSTRIAL_STATE_VALUE
        ]
        composite = round(sum(scored) / len(scored), 6) if scored else None
    values[RankingObjectiveKey.INDUSTRIAL_VIABILITY.value] = composite

    for objective, dimension in INDUSTRIAL_DIMENSION_FOR_OBJECTIVE.items():
        state = str(dimension_states.get(dimension, "unknown"))
        raw = INDUSTRIAL_STATE_VALUE.get(state)
        if objective == RankingObjectiveKey.COST and raw is not None:
            # `economic_feasibility` is already "higher is better", so the minimize direction is
            # satisfied by re-expressing it as a cost burden before the shared inversion below.
            raw = 1.0 - raw
        values[objective.value] = raw
    return values


def _normalize(values: dict[str, float | None], objective: str) -> dict[str, float | None]:
    """Min-max normalize one objective across candidates, then orient it so higher is better."""
    present = {cid: v for cid, v in values.items() if v is not None}
    if not present:
        return {cid: None for cid in values}
    low, high = min(present.values()), max(present.values())
    direction = OBJECTIVE_DIRECTION.get(objective, "maximize")
    normalized: dict[str, float | None] = {}
    for cid, value in values.items():
        if value is None:
            normalized[cid] = None
            continue
        if high == low:
            # Every candidate is identical on this objective, so it cannot discriminate between
            # them. Giving them all 1.0 would let a non-discriminating objective inflate scores.
            scaled = 0.5
        else:
            scaled = (value - low) / (high - low)
        normalized[cid] = round(1.0 - scaled if direction == "minimize" else scaled, 6)
    return normalized


def _weighted_score(
    normalized: dict[str, float | None], weights: dict[str, float]
) -> tuple[float | None, list[str], float]:
    """Weighted mean over the objectives that have a value. Missing objectives are excluded."""
    total_weight = total = 0.0
    excluded: list[str] = []
    for objective, value in sorted(normalized.items()):
        weight = float(weights.get(objective, 0.0))
        if weight <= 0:
            continue
        if value is None:
            excluded.append(objective)
            continue
        total += value * weight
        total_weight += weight
    if total_weight <= 0:
        return None, sorted(excluded), 0.0
    return round(total / total_weight, 6), sorted(excluded), round(total_weight, 6)


def rank_candidates(
    context: PortfolioContext, *, weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Hierarchical ranking with Pareto analysis. Blocked candidates are excluded, not scored."""
    cache_key = f"ranking:{sorted((weights or {}).items())}"
    cached = context.memo.get(cache_key)
    if cached is not None:
        return cached

    from app.services.replacement.portfolio import candidate_decision_state

    active_weights = dict(context.policy.ranking_weights or {})
    if weights:
        active_weights.update({k: float(v) for k, v in weights.items()})

    partitions: dict[str, list[CandidateView]] = {
        CandidateEligibility.ELIGIBLE.value: [],
        CandidateEligibility.UNRESOLVED.value: [],
        CandidateEligibility.BLOCKED.value: [],
    }
    states: dict[str, dict[str, Any]] = {}
    for view in context.candidates:
        state = candidate_decision_state(context, view)
        states[view.candidate_id] = state
        partitions[str(state["eligibility"])].append(view)

    # Step 1 and 2 of the hierarchy: eliminate blocked candidates, separate unresolved ones.
    # Only eligible candidates are scored and ranked.
    rankable = partitions[CandidateEligibility.ELIGIBLE.value]
    raw_by_candidate = {view.candidate_id: raw_objectives(context, view) for view in rankable}

    objectives = [key.value for key in RankingObjectiveKey]
    normalized_by_objective: dict[str, dict[str, float | None]] = {}
    for objective in objectives:
        normalized_by_objective[objective] = _normalize(
            {cid: raw_by_candidate[cid].get(objective) for cid in raw_by_candidate}, objective
        )

    scored_rows: list[dict[str, Any]] = []
    for view in rankable:
        normalized = {
            objective: normalized_by_objective[objective][view.candidate_id]
            for objective in objectives
        }
        score, excluded, applied_weight = _weighted_score(normalized, active_weights)
        scored_rows.append({
            "candidate_id": view.candidate_id,
            "display_name": view.display_name,
            "score": score,
            "raw_factors": raw_by_candidate[view.candidate_id],
            "normalized_factors": normalized,
            "weights": {k: float(v) for k, v in sorted(active_weights.items())},
            "applied_weight_total": applied_weight,
            "excluded_dimensions": excluded,
            "hard_blockers": states[view.candidate_id]["definitive_blocking_failures"],
            "methodology_version": RANKING_METHODOLOGY,
        })

    # Deterministic ordering: score descending, then display name, then id. Candidates whose score
    # could not be computed at all sort last rather than being dropped from the list.
    scored_rows.sort(key=lambda r: (
        -(r["score"] if r["score"] is not None else -1.0),
        str(r["display_name"]), str(r["candidate_id"]),
    ))
    for index, row in enumerate(scored_rows, start=1):
        row["rank"] = index

    pareto = pareto_front(normalized_by_objective, [v.candidate_id for v in rankable])

    excluded_rows = [
        {
            "candidate_id": view.candidate_id, "display_name": view.display_name,
            "eligibility": states[view.candidate_id]["eligibility"],
            "reason": (
                "Excluded from ranking: a blocking requirement definitively failed or an industrial "
                "hard constraint failed."
                if states[view.candidate_id]["eligibility"] == CandidateEligibility.BLOCKED
                else "Excluded from ranking: gating requirements are still unresolved, so a rank "
                     "would compare a measured candidate against an unmeasured one."
            ),
            "hard_blockers": states[view.candidate_id]["definitive_blocking_failures"],
            "unresolved_gating_requirements": states[view.candidate_id]["unresolved_gating_requirements"],
        }
        for view in partitions[CandidateEligibility.BLOCKED.value]
        + partitions[CandidateEligibility.UNRESOLVED.value]
    ]
    excluded_rows.sort(key=lambda r: str(r["display_name"]))

    result = {
        "program_id": context.program.id,
        "ranked": scored_rows,
        "excluded": excluded_rows,
        "pareto": pareto,
        "weights": {k: float(v) for k, v in sorted(active_weights.items())},
        "objectives": objectives,
        "objective_directions": {k: v for k, v in sorted(OBJECTIVE_DIRECTION.items())},
        "methodology_version": RANKING_METHODOLOGY,
        "note": RANKING_NOTE,
    }
    context.memo[cache_key] = result
    return result


def pareto_front(
    normalized_by_objective: dict[str, dict[str, float | None]], candidate_ids: list[str]
) -> dict[str, Any]:
    """Strict Pareto dominance over the normalized objective vectors.

    A candidate dominates another when it is at least as good on every objective both of them have a
    value for, and strictly better on at least one. Objectives where either candidate has no value
    are skipped for that pair — comparing a measured value against a missing one would manufacture a
    dominance relationship out of an evidence gap.
    """
    objectives = sorted(normalized_by_objective.keys())
    dominated_by: dict[str, list[str]] = {cid: [] for cid in candidate_ids}

    for candidate in candidate_ids:
        for other in candidate_ids:
            if candidate == other:
                continue
            comparable = [
                objective for objective in objectives
                if normalized_by_objective[objective].get(candidate) is not None
                and normalized_by_objective[objective].get(other) is not None
            ]
            if not comparable:
                continue
            at_least_as_good = all(
                float(normalized_by_objective[o][other]) >= float(normalized_by_objective[o][candidate])
                for o in comparable
            )
            strictly_better = any(
                float(normalized_by_objective[o][other]) > float(normalized_by_objective[o][candidate])
                for o in comparable
            )
            if at_least_as_good and strictly_better:
                dominated_by[candidate].append(other)

    for cid in dominated_by:
        dominated_by[cid] = sorted(dominated_by[cid])
    front = sorted(cid for cid in candidate_ids if not dominated_by[cid])
    return {
        "front_candidate_ids": front,
        "dominated_by": {cid: rows for cid, rows in sorted(dominated_by.items()) if rows},
        "objectives": objectives,
        "methodology_version": PARETO_METHODOLOGY,
        "note": (
            "Non-dominated candidates represent genuine trade-offs. They are reported rather than "
            "resolved into a single winner by the configured weights."
        ),
    }


def sensitivity_analysis(
    context: PortfolioContext, *, weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Deterministic one-at-a-time weight sweep. No probability distribution over weights is used.

    Each scenario multiplies exactly one objective's weight by one declared multiplier and re-ranks.
    That keeps the scenario count at (objectives x multipliers) instead of exploding combinatorially,
    and it makes each result attributable to a single, nameable change.
    """
    baseline = rank_candidates(context, weights=weights)
    if len(baseline["ranked"]) < 2:
        return {
            "program_id": context.program.id,
            "stability": RankingStability.NOT_APPLICABLE,
            "reason": "Fewer than two eligible candidates, so ranking stability is not meaningful.",
            "baseline_winner": baseline["ranked"][0]["candidate_id"] if baseline["ranked"] else None,
            "scenarios": [], "winners": {}, "scenario_count": 0,
            "methodology_version": SENSITIVITY_METHODOLOGY,
        }

    bounds = context.policy.sensitivity_bounds or {}
    multipliers = [float(m) for m in (bounds.get("multipliers") or [0.5, 0.75, 1.25, 2.0])]
    max_scenarios = int(bounds.get("max_scenarios", 64))
    margin = float(bounds.get("near_equivalent_margin", 0.02))

    base_weights = dict(baseline["weights"])
    baseline_winner = baseline["ranked"][0]["candidate_id"]
    baseline_order = [row["candidate_id"] for row in baseline["ranked"]]

    scenarios: list[dict[str, Any]] = []
    winners: dict[str, int] = {}
    for objective in sorted(base_weights):
        for multiplier in multipliers:
            if len(scenarios) >= max_scenarios:
                break
            scenario_weights = dict(base_weights)
            scenario_weights[objective] = round(float(base_weights[objective]) * multiplier, 6)
            scenario = rank_candidates(context, weights=scenario_weights)
            order = [row["candidate_id"] for row in scenario["ranked"]]
            winner = order[0] if order else None
            if winner:
                winners[winner] = winners.get(winner, 0) + 1
            scenarios.append({
                "objective": objective, "multiplier": multiplier,
                "weight": scenario_weights[objective],
                "winner_candidate_id": winner,
                "order": order,
                "order_changed": order != baseline_order,
                "winner_changed": winner != baseline_winner,
            })

    top_scores = sorted(
        (row["score"] for row in baseline["ranked"] if row["score"] is not None), reverse=True
    )
    near_equivalent = bool(
        len(top_scores) >= 2 and abs(top_scores[0] - top_scores[1]) <= margin
    )
    winner_changed = any(s["winner_changed"] for s in scenarios)

    if winner_changed:
        stability = RankingStability.WEIGHT_SENSITIVE
        reason = (
            "At least one declared weight variation changes which candidate ranks first. The "
            "leading position depends on the chosen weights, not on the evidence alone."
        )
    elif near_equivalent:
        stability = RankingStability.NEAR_EQUIVALENT_CANDIDATES
        reason = (
            f"The top two candidates are within {margin} of each other. The ordering is stable but "
            "the separation is not scientifically meaningful."
        )
    else:
        stability = RankingStability.STABLE_WINNER
        reason = (
            "The leading candidate holds first place across every declared weight variation."
        )

    return {
        "program_id": context.program.id,
        "stability": str(stability),
        "reason": reason,
        "baseline_winner": baseline_winner,
        "baseline_order": baseline_order,
        "winners": dict(sorted(winners.items())),
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "multipliers": multipliers,
        "near_equivalent_margin": margin,
        "methodology_version": SENSITIVITY_METHODOLOGY,
        "note": (
            "A bounded deterministic scenario sweep. No probability distribution over weights is "
            "assumed, so no confidence in the ranking is claimed."
        ),
    }
