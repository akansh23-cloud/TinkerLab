from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Material, MaterialComponent, MaterialIdentifier


def normalize_identifier(namespace: str, value: str) -> str:
    value = value.strip()
    ns = namespace.strip().casefold()
    if ns in {"cas", "materials_project", "doi", "supplier_code", "customer_code"}:
        return re.sub(r"\s+", "", value).casefold()
    return re.sub(r"\s+", " ", value).strip().casefold()


def normalize_material_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def _visible_materials(db: Session, organisation_id: str | None) -> list[Material]:
    rows = db.query(Material).all()
    return [m for m in rows if m.visibility == "public" or (organisation_id and m.owner_organisation_id == organisation_id)]


def _composition_signature(items: list[dict[str, Any]]) -> set[tuple[str, str, float | None]]:
    result: set[tuple[str, str, float | None]] = set()
    for item in items:
        name = normalize_material_name(str(item.get("component_name") or item.get("name") or ""))
        basis = str(item.get("amount_basis") or "qualitative")
        amount = item.get("amount_value")
        rounded = round(float(amount), 6) if amount is not None else None
        if name:
            result.add((name, basis, rounded))
    return result


def resolve_identity(
    db: Session,
    *,
    canonical_name: str | None,
    identifiers: list[dict[str, str]],
    composition: list[dict[str, Any]],
    organisation_id: str | None,
) -> dict[str, Any]:
    visible = _visible_materials(db, organisation_id)
    visible_ids = {m.id for m in visible}
    candidates: dict[str, dict[str, Any]] = {}

    for ident in identifiers:
        namespace = str(ident.get("namespace", "")).strip().casefold()
        value = str(ident.get("value", "")).strip()
        if not namespace or not value:
            continue
        normalized = normalize_identifier(namespace, value)
        matches = (
            db.query(MaterialIdentifier)
            .filter(func.lower(MaterialIdentifier.namespace) == namespace,
                    MaterialIdentifier.normalized_value == normalized)
            .all()
        )
        for row in matches:
            if row.material_id not in visible_ids:
                continue
            entry = candidates.setdefault(row.material_id, {"reasons": [], "rank": 0})
            entry["reasons"].append(f"exact trusted identifier {namespace}:{value}")
            entry["rank"] = max(entry["rank"], 100)

    if canonical_name:
        normalized_name = normalize_material_name(canonical_name)
        for material in visible:
            if normalize_material_name(material.canonical_name) == normalized_name or normalize_material_name(material.display_name) == normalized_name:
                entry = candidates.setdefault(material.id, {"reasons": [], "rank": 0})
                entry["reasons"].append("normalized canonical/display name match")
                entry["rank"] = max(entry["rank"], 70)

    incoming_sig = _composition_signature(composition)
    if incoming_sig:
        for material in visible:
            rows = db.query(MaterialComponent).filter(MaterialComponent.material_id == material.id, MaterialComponent.is_redacted.is_(False)).all()
            existing_sig = _composition_signature([
                {"component_name": c.component_name, "amount_basis": c.amount_basis, "amount_value": c.amount_value}
                for c in rows
            ])
            if existing_sig and incoming_sig == existing_sig:
                entry = candidates.setdefault(material.id, {"reasons": [], "rank": 0})
                entry["reasons"].append("exact structured composition signature match")
                entry["rank"] = max(entry["rank"], 65)

    ranked = sorted(candidates.items(), key=lambda kv: (-kv[1]["rank"], kv[0]))
    output = []
    for material_id, info in ranked:
        resolved = db.get(Material, material_id)
        if not resolved:
            continue
        material = resolved
        if info["rank"] >= 100:
            match_class = "exact"
        elif info["rank"] >= 70:
            match_class = "probable"
        else:
            match_class = "ambiguous"
        output.append({
            "material_id": material.id,
            "material_name": material.display_name,
            "match_class": match_class,
            "reasons": info["reasons"],
        })

    exacts = [x for x in output if x["match_class"] == "exact"]
    if len(exacts) == 1:
        return {"match_class": "exact", "selected_material_id": exacts[0]["material_id"], "reasons": exacts[0]["reasons"], "candidates": output}
    if len(exacts) > 1:
        return {"match_class": "ambiguous", "selected_material_id": None, "reasons": ["multiple exact identifiers resolve to different materials; curator review required"], "candidates": output}
    probables = [x for x in output if x["match_class"] == "probable"]
    if len(probables) == 1:
        return {"match_class": "probable", "selected_material_id": probables[0]["material_id"], "reasons": probables[0]["reasons"], "candidates": output}
    if output:
        return {"match_class": "ambiguous", "selected_material_id": None, "reasons": ["signals are insufficient for an automatic scientific merge"], "candidates": output}
    return {"match_class": "none", "selected_material_id": None, "reasons": ["no conservative identity match found"], "candidates": []}
