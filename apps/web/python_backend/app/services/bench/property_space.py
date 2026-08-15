"""Phase 12.1 — the material property space behind the Ashby chart.

An Ashby chart is the working instrument of materials selection: two properties on log axes,
materials clustered by family, and straight guide lines marking constant values of a *material
index* — the property group that actually governs a design case. Strength-limited tie rods are
selected on sigma/rho; a beam in bending on sigma^(2/3)/rho; a panel on sigma^(1/2)/rho. The three
lines have different slopes, so the material that wins depends entirely on the loading mode, and a
chart that omits them invites the classic mistake of ranking on raw strength.

Two things this service refuses to do, both of which would make a prettier chart and a worse tool:

  * It never plots a material that lacks a real recorded value for an axis. Missing data is
    returned in `excluded` with the reason, not dropped silently and not imputed to zero.
  * It never mixes origins without saying so. A measured value and a model prediction are both
    returned with their origin and confidence so the chart can render them differently.

Values are converted to each property's canonical unit so points are comparable. A value that
cannot be converted is excluded and named, rather than plotted in the wrong unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Material, MaterialPropertyDefinition, MaterialPropertyObservation
from app.services.bench.catalog import CATALOGUE_BY_KEY
from app.services.bench.provenance import provenance_category, weaker_provenance
from app.services.conditions import condition_to_dict
from app.services.units import UnitError, convert


@dataclass(frozen=True)
class MaterialIndex:
    """A performance index M = y^exponent / x, plotted as a straight line on log-log axes.

    On log axes, M = y^a / x rearranges to log y = (1/a)·log x + (1/a)·log M, so the guide line has
    slope 1/a and different design cases separate cleanly. This is the whole reason the chart is
    drawn on log axes rather than linear ones.
    """

    key: str
    label: str
    design_case: str
    exponent: float
    maximise: bool = True

    @property
    def log_slope(self) -> float:
        return 1.0 / self.exponent

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "design_case": self.design_case,
            "exponent": self.exponent, "log_slope": self.log_slope, "maximise": self.maximise,
        }


# Indices are declared per (x, y) axis pair because an index is only meaningful for the properties
# it is built from. Offering "specific stiffness" on a cost-versus-lead-time chart would be noise
# dressed up as expertise.
MATERIAL_INDICES: dict[tuple[str, str], tuple[MaterialIndex, ...]] = {
    ("density", "tensile_strength"): (
        MaterialIndex("strength_per_density", "σ/ρ", "Tie rod / axially loaded member, strength-limited", 1.0),
        MaterialIndex("strength_beam", "σ^⅔/ρ", "Beam in bending, strength-limited", 2.0 / 3.0),
        MaterialIndex("strength_panel", "σ^½/ρ", "Panel in bending, strength-limited", 0.5),
    ),
    ("density", "yield_strength"): (
        MaterialIndex("yield_per_density", "σy/ρ", "Tie rod, yield-limited", 1.0),
        MaterialIndex("yield_beam", "σy^⅔/ρ", "Beam in bending, yield-limited", 2.0 / 3.0),
    ),
    ("density", "tensile_modulus"): (
        MaterialIndex("stiffness_per_density", "E/ρ", "Tie rod, stiffness-limited", 1.0),
        MaterialIndex("stiffness_beam", "E^½/ρ", "Beam in bending, stiffness-limited", 0.5),
        MaterialIndex("stiffness_panel", "E^⅓/ρ", "Panel in bending, stiffness-limited", 1.0 / 3.0),
    ),
    ("density", "flexural_modulus"): (
        MaterialIndex("flex_stiffness_beam", "E_f^½/ρ", "Beam in bending, stiffness-limited", 0.5),
    ),
    ("cost_per_mass", "tensile_strength"): (
        MaterialIndex("strength_per_cost", "σ/Cm", "Cheapest strength, per unit mass of material", 1.0),
    ),
    ("cost_per_mass", "tensile_modulus"): (
        MaterialIndex("stiffness_per_cost", "E/Cm", "Cheapest stiffness, per unit mass of material", 1.0),
    ),
    ("carbon_footprint", "tensile_strength"): (
        MaterialIndex("strength_per_carbon", "σ/GWP", "Strength per unit embodied carbon", 1.0),
    ),
}


def indices_for(x_key: str, y_key: str) -> tuple[MaterialIndex, ...]:
    return MATERIAL_INDICES.get((x_key, y_key), ())


def _best_observations(
    db: Session, material_ids: list[str], property_keys: set[str]
) -> dict[tuple[str, str], MaterialPropertyObservation]:
    """Highest-confidence active observation per (material, property).

    This is a *charting* selection, not the canonical evaluation selection: it exists to place a
    dot, never to decide anything. The decision path continues to use the Phase-2 selection service
    with its full rationale, and nothing here is written back.
    """
    if not material_ids:
        return {}
    rows = (
        db.query(MaterialPropertyObservation)
        .options(selectinload(MaterialPropertyObservation.property_definition),
                 selectinload(MaterialPropertyObservation.evidence))
        .filter(MaterialPropertyObservation.material_id.in_(material_ids),
                MaterialPropertyObservation.status == "active")
        .order_by(MaterialPropertyObservation.curator_preferred.desc(),
                  MaterialPropertyObservation.confidence.desc().nullslast(),
                  MaterialPropertyObservation.created_at.desc())
        .all()
    )
    best: dict[tuple[str, str], MaterialPropertyObservation] = {}
    for row in rows:
        definition = row.property_definition
        if definition is None or definition.key not in property_keys:
            continue
        best.setdefault((row.material_id, definition.key), row)
    return best


def _axis_meta(db: Session, key: str) -> dict[str, Any]:
    definition = db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none()
    spec = CATALOGUE_BY_KEY.get(key)
    if definition is None and spec is None:
        raise ValueError(f"Unknown property '{key}'.")
    canonical = (definition.canonical_unit if definition else None) or (spec.canonical_unit if spec else None)
    return {
        "key": key,
        "display_name": (spec.display_name if spec else None) or (definition.display_name if definition else key),
        "canonical_unit": canonical,
        "direction": spec.direction if spec else "neutral",
        "quantity_type": (definition.quantity_type if definition else None) or (spec.quantity_type if spec else ""),
        "test_standard": spec.test_standard if spec else None,
        "why_it_matters": spec.why_it_matters if spec else None,
    }


def property_space(
    db: Session,
    *,
    x_key: str,
    y_key: str,
    family: str | None = None,
    organisation_id: str | None = None,
    highlight_material_id: str | None = None,
    limit: int = 400,
) -> dict[str, Any]:
    x_axis = _axis_meta(db, x_key)
    y_axis = _axis_meta(db, y_key)
    for axis in (x_axis, y_axis):
        if axis["quantity_type"] == "boolean":
            raise ValueError(
                f"'{axis['display_name']}' is a compliance gate, not a continuous property. "
                "It cannot be an axis — filter on it instead."
            )

    query = db.query(Material)
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public",
                                 Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    if family:
        query = query.filter(Material.material_family == family)
    materials = query.order_by(Material.display_name).limit(limit).all()

    observations = _best_observations(db, [m.id for m in materials], {x_key, y_key})

    points: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for material in materials:
        x_obs = observations.get((material.id, x_key))
        y_obs = observations.get((material.id, y_key))
        missing = [
            axis["display_name"]
            for axis, obs in ((x_axis, x_obs), (y_axis, y_obs)) if obs is None
        ]
        if missing:
            excluded.append({
                "material_id": material.id, "display_name": material.display_name,
                "reason": f"No recorded value for {' and '.join(missing)}.",
            })
            continue

        converted: dict[str, float] = {}
        failed = False
        for axis_key, axis, obs in ((("x"), x_axis, x_obs), (("y"), y_axis, y_obs)):
            if obs.numeric_value is None:
                excluded.append({"material_id": material.id, "display_name": material.display_name,
                                 "reason": f"{axis['display_name']} has no numeric value."})
                failed = True
                break
            unit = obs.unit or axis["canonical_unit"] or ""
            try:
                converted[axis_key] = convert(float(obs.numeric_value), unit, axis["canonical_unit"] or unit)
            except UnitError as exc:
                excluded.append({"material_id": material.id, "display_name": material.display_name,
                                 "reason": f"{axis['display_name']} could not be converted: {exc}"})
                failed = True
                break
        if failed:
            continue

        # Log axes cannot represent zero or negative values. Rather than clamping — which would put
        # a point somewhere it does not belong — the material is excluded and told why.
        if converted["x"] <= 0 or converted["y"] <= 0:
            excluded.append({
                "material_id": material.id, "display_name": material.display_name,
                "reason": "A zero or negative value cannot be placed on a logarithmic axis.",
            })
            continue

        def origin(obs: MaterialPropertyObservation) -> str:
            evidence_type = obs.evidence.evidence_type if obs.evidence else "unknown"
            if evidence_type == "predicted":
                return "prediction"
            if evidence_type in {"computational", "simulation"}:
                return "simulation"
            if evidence_type in {"experimental", "measurement"}:
                return "measured"
            if evidence_type == "supplier":
                return "supplier"
            if evidence_type in {"literature", "seed_demo"}:
                return "literature"
            if evidence_type == "external_computational":
                return "simulation"
            return "declared"

        def provenance(obs: MaterialPropertyObservation, broad_origin: str) -> str:
            return provenance_category(
                evidence_type=obs.evidence.evidence_type if obs.evidence else None,
                source_quality=obs.evidence.source_quality if obs.evidence else None,
                value_origin={
                    "prediction": "model_prediction",
                    "simulation": "physics_simulation",
                }.get(broad_origin, "known_evidence"),
            )

        x_origin = origin(x_obs)
        y_origin = origin(y_obs)
        x_provenance = provenance(x_obs, x_origin)
        y_provenance = provenance(y_obs, y_origin)
        points.append({
            "material_id": material.id,
            "display_name": material.display_name,
            "material_family": material.material_family,
            "is_seed_data": material.is_seed_data,
            "x": converted["x"],
            "y": converted["y"],
            # Broad origin is retained for backwards compatibility; detailed provenance is the
            # source of truth for evidence styling and weakest-origin resolution.
            "x_origin": x_origin, "y_origin": y_origin,
            "x_provenance": x_provenance, "y_provenance": y_provenance,
            "weakest_origin": weaker_provenance(x_provenance, y_provenance),
            "x_confidence": x_obs.confidence, "y_confidence": y_obs.confidence,
            "x_observation_id": x_obs.id, "y_observation_id": y_obs.id,
            "x_evidence_type": x_obs.evidence.evidence_type if x_obs.evidence else None,
            "y_evidence_type": y_obs.evidence.evidence_type if y_obs.evidence else None,
            "x_source_quality": x_obs.evidence.source_quality if x_obs.evidence else None,
            "y_source_quality": y_obs.evidence.source_quality if y_obs.evidence else None,
            "x_conditions": condition_to_dict(x_obs.condition_set),
            "y_conditions": condition_to_dict(y_obs.condition_set),
            "x_unit": x_axis["canonical_unit"], "y_unit": y_axis["canonical_unit"],
            "highlighted": material.id == highlight_material_id,
        })

    return {
        "x_axis": x_axis,
        "y_axis": y_axis,
        "points": points,
        "excluded": excluded,
        "material_indices": [i.as_dict() for i in indices_for(x_key, y_key)],
        "plotted_count": len(points),
        "excluded_count": len(excluded),
    }


def axis_options(db: Session, organisation_id: str | None = None) -> list[dict[str, Any]]:
    """Continuous properties that at least two visible materials actually have values for.

    Offering an axis with one point behind it produces an empty-looking chart and reads as a bug,
    so the picker is built from what can genuinely be drawn.
    """
    counts: dict[str, int] = {}
    query = (
        db.query(MaterialPropertyObservation)
        .join(Material, MaterialPropertyObservation.material_id == Material.id)
        .options(selectinload(MaterialPropertyObservation.property_definition))
        .filter(MaterialPropertyObservation.status == "active")
    )
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    rows = query.all()
    seen: set[tuple[str, str]] = set()
    for row in rows:
        definition = row.property_definition
        if definition is None or definition.quantity_type == "boolean":
            continue
        pair = (row.material_id, definition.key)
        if pair in seen:
            continue
        seen.add(pair)
        counts[definition.key] = counts.get(definition.key, 0) + 1

    options = []
    for key, count in counts.items():
        if count < 2:
            continue
        spec = CATALOGUE_BY_KEY.get(key)
        options.append({
            "key": key,
            "display_name": spec.display_name if spec else key.replace("_", " "),
            "domain": spec.domain if spec else "other",
            "canonical_unit": spec.canonical_unit if spec else None,
            "material_count": count,
            "direction": spec.direction if spec else "neutral",
        })
    return sorted(options, key=lambda o: (-o["material_count"], o["display_name"]))


def index_value(point_x: float, point_y: float, index: MaterialIndex) -> float:
    """M = y^exponent / x. Used to rank materials on a design case rather than on a raw property."""
    if point_x <= 0:
        return math.nan
    return (point_y ** index.exponent) / point_x
