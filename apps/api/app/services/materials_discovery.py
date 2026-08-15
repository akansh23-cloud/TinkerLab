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


def preview_materials_project_candidates(
    connector: MaterialsProjectConnector,
    *,
    constraints: list[dict[str, Any]],
    search_filters: dict[str, Any],
    max_candidates: int,
    search_pool: int,
    stable_preferred: bool,
) -> dict[str, Any]:
    """Discover and rank candidates without writing to TinkerLab's database."""

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

        hull = observations.get("energy_above_hull", {}).get("numeric_value")
        hull_sort = float(hull) if isinstance(hull, (int, float)) else float("inf")
        stable = normalized.get("is_stable") is True
        theoretical = normalized.get("is_theoretical") is True

        # Lexicographic ranking is intentional. It avoids presenting an arbitrary weighted
        # score as if it were a calibrated scientific probability.
        sort_key = (
            fail_count,
            unknown_count,
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

    return {
        "preview_only": True,
        "persisted": False,
        "source": "materials_project",
        "source_data_kind": "computed_database",
        "warning": (
            "Discovery rank is a deterministic screening order, not a probability of material "
            "success. Materials Project values are computed database evidence unless explicitly "
            "identified otherwise by their provenance."
        ),
        "ranking_policy": {
            "type": "deterministic_lexicographic",
            "order": [
                "fewest_constraint_failures",
                "fewest_unknown_constraints",
                "highest_constraint_evidence_coverage",
                "stable_material_preferred_when_requested",
                "non_theoretical_material_preferred",
                "lower_energy_above_hull_when_available",
                "material_id_tiebreaker",
            ],
        },
        "constraints": constraints,
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
