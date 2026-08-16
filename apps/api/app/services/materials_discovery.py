"""Read-only candidate discovery over Materials Project.

This module intentionally does not persist materials, evidence, or snapshots. It is a
screening layer: translate explicit engineering constraints into upstream Materials
Project filters, normalize returned computed properties, and rank candidates with a
fully disclosed deterministic policy.

A rank from this module is not a probability of success and is not experimental
evidence. Values retain the Materials Project connector's computed-database origin.
"""

from __future__ import annotations

from typing import Any

from app.services.ingest.materials_project_v2 import MaterialsProjectConnector


# Public TinkerLab property -> Materials Project search parameter stem.
# Keep this deliberately narrow: only properties that are both searchable and currently
# normalized by the connector are eligible for decision-screening here.
_PROPERTY_FILTERS: dict[str, str] = {
    "band_gap": "band_gap",
    "density": "density",
    "energy_above_hull": "energy_above_hull",
    "formation_energy_per_atom": "formation_energy_per_atom",
    "bulk_modulus": "k_vrh",
    "shear_modulus": "g_vrh",
    "magnetic_moment": "total_magnetization",
}

_SEARCH_FILTERS = {
    "formula",
    "chemsys",
    "elements",
    "exclude_elements",
    "is_stable",
    "theoretical",
}


def _observation_map(normalized: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["property_key"]): row
        for row in normalized.get("observations", [])
        if isinstance(row, dict) and row.get("property_key")
    }


def _evaluate_constraints(
    observations: dict[str, dict[str, Any]], constraints: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for constraint in constraints:
        key = str(constraint["property"])
        observation = observations.get(key)
        numeric = observation.get("numeric_value") if observation else None
        minimum = constraint.get("minimum")
        maximum = constraint.get("maximum")
        if not isinstance(numeric, (int, float)):
            status = "unknown"
        elif minimum is not None and float(numeric) < float(minimum):
            status = "fail"
        elif maximum is not None and float(numeric) > float(maximum):
            status = "fail"
        else:
            status = "pass"
        evaluations.append(
            {
                "property": key,
                "minimum": minimum,
                "maximum": maximum,
                "status": status,
                "value": float(numeric) if isinstance(numeric, (int, float)) else None,
                "unit": observation.get("unit") if observation else None,
                "origin": observation.get("origin") if observation else None,
                "computed": observation.get("computed") if observation else None,
                "calculation_provenance": (
                    observation.get("calculation_provenance") or {} if observation else {}
                ),
            }
        )
    return evaluations


def _evaluate_preferences(
    observations: dict[str, dict[str, Any]], preferences: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Evaluate soft mission targets without treating them as hard eligibility gates.

    Preference weights come from the mission author. They are used only to order candidates
    after hard-gate state has been considered; they are never presented as calibrated scientific
    probabilities or as a substitute for missing evidence.
    """
    evaluations = _evaluate_constraints(observations, preferences)
    for evaluation, preference in zip(evaluations, preferences, strict=True):
        evaluation.update(
            {
                "constraint_id": preference.get("constraint_id"),
                "weight": float(preference.get("weight") or 1.0),
                "severity": int(preference.get("severity") or 1),
                "description": preference.get("description"),
            }
        )
    return evaluations


def _preference_summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    pass_count = sum(row["status"] == "pass" for row in evaluations)
    fail_count = sum(row["status"] == "fail" for row in evaluations)
    unknown_count = sum(row["status"] == "unknown" for row in evaluations)
    weights = [max(0.0, float(row.get("weight") or 0.0)) for row in evaluations]
    total_weight = sum(weights)
    pass_weight = sum(weight for row, weight in zip(evaluations, weights, strict=True) if row["status"] == "pass")
    fail_weight = sum(weight for row, weight in zip(evaluations, weights, strict=True) if row["status"] == "fail")
    unknown_weight = sum(weight for row, weight in zip(evaluations, weights, strict=True) if row["status"] == "unknown")
    known_weight = pass_weight + fail_weight
    return {
        "pass": pass_count,
        "fail": fail_count,
        "unknown": unknown_count,
        "total_weight": round(total_weight, 6),
        "pass_weight": round(pass_weight, 6),
        "fail_weight": round(fail_weight, 6),
        "unknown_weight": round(unknown_weight, 6),
        "evidence_coverage": round(known_weight / total_weight, 4) if total_weight else 1.0,
        "known_weight_satisfaction": round(pass_weight / known_weight, 4) if known_weight else None,
    }


def preview_materials_project_candidates(
    connector: MaterialsProjectConnector,
    *,
    constraints: list[dict[str, Any]],
    search_filters: dict[str, Any],
    max_candidates: int,
    search_pool: int,
    stable_preferred: bool,
    preferences: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Discover and rank candidates without writing to TinkerLab's database."""

    preferences = preferences or []
    query: dict[str, Any] = {"max_records": max(search_pool, max_candidates)}
    for key, value in search_filters.items():
        if key in _SEARCH_FILTERS and value is not None:
            query[key] = value

    for constraint in constraints:
        property_key = str(constraint["property"])
        stem = _PROPERTY_FILTERS[property_key]
        if constraint.get("minimum") is not None:
            query[f"{stem}_min"] = float(constraint["minimum"])
        if constraint.get("maximum") is not None:
            query[f"{stem}_max"] = float(constraint["maximum"])

    fetched = connector.fetch(**query)
    candidates: list[dict[str, Any]] = []
    constraint_count = len(constraints)

    for raw in fetched.records:
        normalized = connector.normalize(raw)
        observations = _observation_map(normalized)
        evaluations = _evaluate_constraints(observations, constraints)
        pass_count = sum(row["status"] == "pass" for row in evaluations)
        fail_count = sum(row["status"] == "fail" for row in evaluations)
        unknown_count = sum(row["status"] == "unknown" for row in evaluations)
        coverage = (pass_count + fail_count) / constraint_count if constraint_count else 1.0

        preference_evaluations = _evaluate_preferences(observations, preferences)
        preference_summary = _preference_summary(preference_evaluations)

        hull = observations.get("energy_above_hull", {}).get("numeric_value")
        hull_sort = float(hull) if isinstance(hull, (int, float)) else float("inf")
        stable = normalized.get("is_stable") is True
        theoretical = normalized.get("is_theoretical") is True

        # Multi-stage lexicographic ranking is intentional. Hard-gate state always dominates.
        # Only after that do user-authored soft target weights influence ordering. This avoids
        # hiding a hard failure behind an arbitrary aggregate score and keeps missing evidence
        # distinct from a demonstrated soft-target failure.
        sort_key = (
            fail_count,
            unknown_count,
            float(preference_summary["fail_weight"]),
            float(preference_summary["unknown_weight"]),
            -float(preference_summary["pass_weight"]),
            -coverage,
            0 if (stable or not stable_preferred) else 1,
            1 if theoretical else 0,
            hull_sort,
            str(normalized.get("external_id") or ""),
        )
        candidates.append(
            {
                "material_id": normalized.get("external_id"),
                "display_name": normalized.get("display_name"),
                "chemical_formula": normalized.get("chemical_formula"),
                "elements": normalized.get("elements") or [],
                "is_stable": normalized.get("is_stable"),
                "is_theoretical": normalized.get("is_theoretical"),
                "crystal_system": normalized.get("crystal_system"),
                "space_group_symbol": normalized.get("space_group_symbol"),
                "constraint_summary": {
                    "pass": pass_count,
                    "fail": fail_count,
                    "unknown": unknown_count,
                    "evidence_coverage": round(coverage, 4),
                },
                "constraint_evaluations": evaluations,
                "preference_summary": preference_summary,
                "preference_evaluations": preference_evaluations,
                "observations": list(observations.values()),
                "materials_project_origins": normalized.get("materials_project_origins") or [],
                "last_updated": normalized.get("last_updated"),
                "_sort_key": sort_key,
            }
        )

    candidates.sort(key=lambda row: row["_sort_key"])
    selected = candidates[:max_candidates]
    for rank, candidate in enumerate(selected, start=1):
        candidate.pop("_sort_key", None)
        candidate["rank"] = rank

    ranking_order = [
        "fewest_hard_constraint_failures",
        "fewest_unknown_hard_constraints",
    ]
    if preferences:
        ranking_order.extend(
            [
                "lowest_user_weighted_soft_failure",
                "lowest_user_weighted_soft_unknown",
                "highest_user_weighted_soft_satisfaction",
            ]
        )
    ranking_order.extend(
        [
            "highest_hard_constraint_evidence_coverage",
            "stable_material_preferred_when_requested",
            "non_theoretical_material_preferred",
            "lower_energy_above_hull_when_available",
            "material_id_tiebreaker",
        ]
    )

    return {
        "preview_only": True,
        "persisted": False,
        "source": "materials_project",
        "source_data_kind": "computed_database",
        "warning": (
            "Discovery rank is a deterministic screening order, not a probability of material "
            "success. Soft-target weights are mission-authored priorities, not learned scientific "
            "confidence. Materials Project values are computed database evidence unless explicitly "
            "identified otherwise by their provenance."
        ),
        "ranking_policy": {
            "type": "deterministic_multistage_lexicographic",
            "order": ranking_order,
            "soft_weight_semantics": (
                "Weights order soft target satisfaction only after hard-gate status. Unknown evidence "
                "is kept separate from a demonstrated failure and is never imputed."
            ),
        },
        "constraints": constraints,
        "preferences": preferences,
        "search_filters": search_filters,
        "query_descriptor": fetched.query_descriptor,
        "provider_version": fetched.provider_version,
        "reproducible": fetched.is_reproducible,
        "reproducibility_note": fetched.reproducibility_note,
        "upstream_metadata": fetched.metadata,
        "records_screened": len(fetched.records),
        "candidates_returned": len(selected),
        "candidates": selected,
    }
