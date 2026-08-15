from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.models.entities import ReplacementProject

SPEC_VERSION = "1.0"


def _constraint_payload(c) -> dict[str, Any]:
    value: float | bool | None = c.target_boolean if c.comparator == "boolean" else c.target_value
    return {
        "id": c.id,
        "property": c.property_key,
        "operator": c.comparator,
        "value": value,
        "upper_value": c.target_value_upper,
        "unit": c.target_unit,
        "weight": c.weight,
        "severity": c.severity,
    }


def _objective_payload(o) -> dict[str, Any]:
    return {
        "id": o.id,
        "property": o.property_key,
        "direction": o.direction,
        "value": o.target_value,
        "unit": o.target_unit,
        "weight": o.weight,
        "priority": o.priority,
    }


def compile_specification(project: ReplacementProject) -> dict[str, Any]:
    hard = sorted(
        [_constraint_payload(c) for c in project.constraints if c.hard_or_soft == "hard"],
        key=lambda x: (x["property"], x["operator"], x["id"]),
    )
    soft = sorted(
        [_constraint_payload(c) for c in project.constraints if c.hard_or_soft == "soft"],
        key=lambda x: (x["property"], x["operator"], x["id"]),
    )
    objectives = sorted(
        [_objective_payload(o) for o in project.objectives],
        key=lambda x: (x["priority"], x["property"], x["id"]),
    )
    canonical = {
        "specification_version": SPEC_VERSION,
        "project_id": project.id,
        "baseline": {
            "material_id": project.baseline_material.id,
            "canonical_name": project.baseline_material.canonical_name,
            "display_name": project.baseline_material.display_name,
        },
        "reasons": sorted(project.replacement_reasons),
        "hard_constraints": hard,
        "soft_constraints": soft,
        "objectives": objectives,
        "metadata": {"status": project.status},
    }
    semantic_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    checksum = hashlib.sha256(semantic_json.encode()).hexdigest()
    generated_at = datetime.now(UTC).isoformat()
    human_lines = [
        f"Replacement specification for {project.name}",
        f"Baseline: {project.baseline_material.display_name}",
        f"Reasons: {', '.join(sorted(project.replacement_reasons))}",
        "Hard constraints:",
    ]
    for c in hard:
        if c["operator"] == "boolean":
            target = str(c["value"]).lower()
        elif c["operator"] == "between":
            target = f"{c['value']}–{c['upper_value']} {c['unit']}"
        else:
            target = f"{c['operator']} {c['value']} {c['unit']}"
        human_lines.append(f"- {c['property']}: {target}")
    human_lines.append("Soft constraints:")
    for c in soft:
        human_lines.append(f"- {c['property']}: {c['operator']} {c['value']} {c['unit'] or ''}".strip())
    human_lines.append("Objectives:")
    for o in objectives:
        human_lines.append(f"- {o['direction']} {o['property']} (weight {o['weight']})")
    return {
        **canonical,
        "generated_at": generated_at,
        "checksum": checksum,
        "canonical_payload": canonical,
        "human_readable": "\n".join(human_lines),
    }
