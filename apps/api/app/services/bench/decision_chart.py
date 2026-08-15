"""Phase 12.1 — chart-ready views of a decision that has already been made elsewhere.

Every status in here comes from the canonical Phase-1/8 evaluator. This module re-shapes that output
for plotting and adds one derived quantity: the signed percentage margin of an observed value
against its own threshold.

The margin is computed here rather than in the browser for one specific reason. A requirement is
stated in the unit the engineer typed (145 degC, 8.5 USD/kg), and the observation is stored in the
unit the datasheet used. Comparing them needs the real unit registry, and a client-side
approximation would silently produce wrong margins for exactly the temperature-offset and
per-mass-cost cases where the conversion is not a plain multiplication.

Signing convention: positive always means better than required, whichever way the comparator points.
UNKNOWN yields `null`, never `0`. Zero would place the candidate exactly on the limit, which asserts
marginality where the truth is an absence of evidence.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entities import Candidate, MaterialPropertyDefinition, ReplacementProject
from app.services.bench.catalog import CATALOGUE_BY_KEY
from app.services.bench.provenance import provenance_category
from app.services.evaluation import evaluate_candidate
from app.services.selection import build_selection_context
from app.services.units import UnitError, convert


def _margin_percent(
    observed_canonical: float | None, target_value: float | None, target_unit: str | None,
    canonical_unit: str | None, comparator: str,
) -> float | None:
    if observed_canonical is None or target_value is None:
        return None
    try:
        target_canonical = (
            convert(float(target_value), target_unit, canonical_unit)
            if target_unit and canonical_unit and target_unit != canonical_unit
            else float(target_value)
        )
    except UnitError:
        return None
    if target_canonical == 0:
        # A zero threshold has no meaningful percentage margin: everything is either infinitely
        # above it or exactly on it. Reported as absent rather than as a huge number.
        return None
    denominator = abs(target_canonical)
    if comparator in (">=", ">"):
        return ((observed_canonical - target_canonical) / denominator) * 100.0
    if comparator in ("<=", "<"):
        return ((target_canonical - observed_canonical) / denominator) * 100.0
    return None




def _canonical_target(
    value: float | None, target_unit: str | None, canonical_unit: str | None,
) -> float | None:
    if value is None:
        return None
    try:
        return (
            convert(float(value), target_unit, canonical_unit)
            if target_unit and canonical_unit and target_unit != canonical_unit
            else float(value)
        )
    except UnitError:
        return None

def decision_chart(db: Session, project_id: str, organisation_id: str | None = None) -> dict[str, Any]:
    project = (
        db.query(ReplacementProject).options(
            selectinload(ReplacementProject.constraints),
            selectinload(ReplacementProject.objectives),
            selectinload(ReplacementProject.baseline_material),
        ).filter(ReplacementProject.id == project_id,
                 ReplacementProject.organisation_id == organisation_id).one_or_none()
    )
    if project is None:
        return {"found": False}

    definitions = {d.key: d for d in db.query(MaterialPropertyDefinition).all()}
    candidates = (
        db.query(Candidate).options(selectinload(Candidate.material), selectinload(Candidate.hypothesis))
        .filter(Candidate.project_id == project.id)
        .order_by(Candidate.created_at, Candidate.id).limit(60).all()
    )
    material_ids = [c.material_id for c in candidates if c.material_id]
    selection_context = build_selection_context(
        db, [project.baseline_material_id, *[m for m in material_ids if m]]
    )

    constraint_by_key = {c.property_key: c for c in project.constraints}
    requirements: list[dict[str, Any]] = []
    for c in sorted(project.constraints, key=lambda c: (c.hard_or_soft != "hard", -c.severity, c.property_key)):
        definition = definitions.get(c.property_key)
        canonical_unit = definition.canonical_unit if definition else None
        requirements.append({
            "property_key": c.property_key,
            "display_name": (definition.display_name if definition else c.property_key.replace("_", " ")),
            "comparator": c.comparator,
            "target_value": c.target_value,
            "target_value_upper": c.target_value_upper,
            "target_boolean": c.target_boolean,
            "target_unit": c.target_unit,
            "canonical_target_value": _canonical_target(c.target_value, c.target_unit, canonical_unit),
            "canonical_target_value_upper": _canonical_target(c.target_value_upper, c.target_unit, canonical_unit),
            "canonical_unit": canonical_unit,
            "hard_or_soft": c.hard_or_soft,
            "severity": c.severity,
            "rationale": c.description,
        })

    rows: list[dict[str, Any]] = []
    excluded_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        try:
            evaluation = evaluate_candidate(db, project, candidate, selection_context=selection_context)
        except Exception:
            excluded_candidates.append({
                "candidate_id": candidate.id,
                "display_name": (
                    candidate.material.display_name if candidate.material is not None
                    else candidate.hypothesis.display_label if candidate.hypothesis is not None
                    else "Unavailable candidate"
                ),
                "reason_code": "EVALUATION_FAILED",
                "message": "The canonical evaluator could not process this candidate. Inspect it in Candidate Lab.",
            })
            continue

        cells: list[dict[str, Any]] = []
        for evaluated in evaluation.get("constraints", []):
            key = evaluated.get("property_key")
            constraint = constraint_by_key.get(key)
            definition = definitions.get(key)
            margin = None
            if constraint is not None and evaluated.get("status") != "UNKNOWN":
                margin = _margin_percent(
                    evaluated.get("canonical_value"),
                    constraint.target_value,
                    constraint.target_unit,
                    definition.canonical_unit if definition else None,
                    constraint.comparator,
                )
            cells.append({
                "property_key": key,
                "status": evaluated.get("status"),
                "observed_value": evaluated.get("observed_value"),
                "observed_unit": evaluated.get("observed_unit"),
                "canonical_value": evaluated.get("canonical_value"),
                "canonical_unit": evaluated.get("canonical_unit"),
                "margin_percent": margin,
                "value_origin": evaluated.get("value_origin"),
                "evidence_type": evaluated.get("evidence_type"),
                "source_quality": evaluated.get("source_quality"),
                "provenance_category": provenance_category(
                    evidence_type=evaluated.get("evidence_type"),
                    source_quality=evaluated.get("source_quality"),
                    value_origin=evaluated.get("value_origin"),
                ),
                "selected_observation_id": evaluated.get("selected_observation_id"),
                "conflict": bool(evaluated.get("conflict")),
                "confidence": evaluated.get("confidence"),
                "unknown_reason": evaluated.get("unknown_reason"),
            })

        origin_mix: dict[str, int] = {}
        provenance_mix: dict[str, int] = {}
        for cell in cells:
            origin = cell["value_origin"] or ("none" if cell["status"] == "UNKNOWN" else "unknown")
            origin_mix[origin] = origin_mix.get(origin, 0) + 1
            provenance = cell["provenance_category"] or "unknown"
            provenance_mix[provenance] = provenance_mix.get(provenance, 0) + 1

        properties = []
        for item in evaluation.get("properties", []):
            copied = dict(item)
            spec = CATALOGUE_BY_KEY.get(copied.get("property_key"))
            copied["direction"] = spec.direction if spec else "neutral"
            properties.append(copied)

        rows.append({
            "candidate_id": evaluation.get("candidate_id"),
            "candidate_kind": evaluation.get("candidate_kind"),
            "display_name": evaluation.get("material_name"),
            "hard_passed": evaluation.get("hard_passed"),
            "hard_failed": evaluation.get("hard_failed"),
            "unknown": evaluation.get("unknown"),
            "completeness": evaluation.get("completeness"),
            "cells": cells,
            "origin_mix": origin_mix,
            "provenance_mix": provenance_mix,
            "properties": properties,
        })

    return {
        "found": True,
        "project_id": project.id,
        "project_name": project.name,
        "baseline": {
            "id": project.baseline_material.id,
            "display_name": project.baseline_material.display_name,
            "material_family": project.baseline_material.material_family,
        },
        "requirements": requirements,
        "candidates": rows,
        "candidate_count": len(rows),
        "candidate_total": len(candidates),
        "excluded_candidate_count": len(excluded_candidates),
        "excluded_candidates": excluded_candidates,
    }
