"""Phase 12 — derive a valid candidate search space from the project baseline.

THE BUG THIS FIXES. Every downstream lab is gated on an *active* candidate search space. The API
could create one; no screen ever did. So a project created through the new-study wizard reached the
Candidate Lab with `active === undefined`, which meant the Search Space Builder card never rendered
and the Virtual Experiment Lab's create button was permanently disabled with no explanation. The
labs were not broken — they were correctly reporting that a required input did not exist, in a way
that looked exactly like being broken. Only the single seeded demo project, whose search space was
written directly by the seed script, ever worked.

Derivation reads the baseline material's own composition and produces bounded variation rules
around it, sized so the enumerated space stays inside the safe limit. It deliberately produces a
*conservative* space: narrow bands around the incumbent, matrix component as balance, additives
free to move a little. That is the honest starting point for a substitution study, and it is a
starting point the user is expected to widen deliberately rather than inherit by accident.

If the baseline has no usable composition, derivation says so and names the fix, rather than
emitting an invalid space that fails validation later with an opaque code.
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CandidateSearchSpace,
    Material,
    ReplacementProject,
    SearchSpaceComponentRule,
    SearchSpaceProcessRule,
)
from app.services.bench.library import family_defaults
from app.services.generation import (
    HARD_MAX_ENUMERATION,
    get_search_space,
    search_space_checksum,
    validate_search_space,
)

# Roles treated as the continuous phase. The balance component absorbs the remainder so every
# generated composition sums to the declared total without the generator having to solve for it.
_MATRIX_ROLES = {"matrix", "host", "base"}
# Roles that must not be varied automatically. Moving a dopant by whole percent is not a
# formulation change, it is a different material, and a redacted component cannot be varied at all.
_LOCKED_ROLES = {"impurity", "dopant"}

_SAFE_ENUMERATION = 4000


def _component_key(name: str, index: int) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip().lower()).strip("_")
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or f"component_{index}"


def _grid_size(low: float, high: float, step: float) -> int:
    if step <= 0 or high <= low:
        return 1
    return int(math.floor((high - low) / step)) + 1


def derivation_preview(db: Session, project: ReplacementProject) -> dict[str, Any]:
    """Describe what would be derived, and why it would fail, without writing anything."""
    baseline = (
        db.query(Material).options(selectinload(Material.components))
        .filter(Material.id == project.baseline_material_id).one_or_none()
    )
    if baseline is None:
        return {
            "derivable": False,
            "blockers": [{
                "code": "BASELINE_NOT_FOUND",
                "message": "The project's baseline material no longer exists.",
                "fix": "Reassign a baseline material to this project.",
            }],
            "component_rules": [], "process_rules": [], "estimated_cardinality": 0,
        }

    defaults = family_defaults(baseline.material_family)
    usable = [
        c for c in sorted(baseline.components, key=lambda c: c.sequence)
        if not c.is_redacted and c.amount_value is not None
    ]
    blockers: list[dict[str, str]] = []
    notes: list[str] = []

    redacted = [c for c in baseline.components if c.is_redacted]
    if redacted:
        notes.append(
            f"{len(redacted)} redacted component(s) are held fixed. Composition variation cannot "
            "move a component whose identity or amount is withheld."
        )
    amountless = [c for c in baseline.components if not c.is_redacted and c.amount_value is None]
    if amountless:
        notes.append(
            f"{len(amountless)} component(s) have no numeric amount and are held fixed. "
            "Add amounts on the baseline material to let them vary."
        )

    if not usable:
        blockers.append({
            "code": "NO_USABLE_BASELINE_COMPOSITION",
            "message": (
                "The baseline material has no components with concrete, unredacted amounts, so "
                "there is nothing to vary."
            ),
            "fix": (
                "Open the baseline material and record its composition — at minimum a matrix "
                "component and one additive, with numeric amounts."
            ),
        })
        return {
            "derivable": False, "blockers": blockers, "notes": notes,
            "baseline_material": {"id": baseline.id, "display_name": baseline.display_name,
                                  "material_family": baseline.material_family},
            "component_rules": [], "process_rules": [], "estimated_cardinality": 0,
        }

    # The matrix is whichever declared matrix/host component carries the largest amount; failing
    # that, simply the largest. It becomes the balance component and is never itself mutable.
    matrix = next(
        (c for c in sorted(usable, key=lambda c: -(c.amount_value or 0.0))
         if (c.component_role or "").lower() in _MATRIX_ROLES),
        max(usable, key=lambda c: c.amount_value or 0.0),
    )

    basis = matrix.amount_basis or defaults["amount_basis"]
    additive_span = float(defaults["additive_span"])
    step = float(defaults["step"])

    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    mutable_grids: list[int] = []

    for index, component in enumerate(sorted(baseline.components, key=lambda c: c.sequence)):
        key = _component_key(component.component_name, index)
        while key in seen:
            key = f"{key}_{index}"
        seen.add(key)

        role = (component.component_role or "").lower()
        is_matrix = component.id == matrix.id
        blocked = (
            component.is_redacted
            or component.amount_value is None
            or role in _LOCKED_ROLES
            or (component.amount_basis or basis) != basis
        )
        mutable = not is_matrix and not blocked

        rule: dict[str, Any] = {
            "baseline_component_id": component.id,
            "component_key": key,
            "display_name": component.component_name,
            "role": component.component_role,
            "locked": bool(blocked or is_matrix),
            "mutable": mutable,
            "required": is_matrix or role in _MATRIX_ROLES,
            "prohibited": False,
            "min_amount": None, "max_amount": None, "step_amount": None,
            "amount_unit": component.amount_unit or "%",
            # Only a mutable rule is checked against the baseline basis, so declaring the basis on
            # a locked rule whose baseline basis differs would create a validation error for a rule
            # that cannot move anyway.
            "amount_basis": basis if mutable else None,
            "sequence": index,
            "metadata": {"derived_from": "baseline_composition", "baseline_amount": component.amount_value},
        }

        if mutable:
            amount = float(component.amount_value or 0.0)
            low = max(0.0, amount - additive_span)
            high = amount + additive_span
            rule["min_amount"] = round(low, 4)
            rule["max_amount"] = round(high, 4)
            rule["step_amount"] = step
            mutable_grids.append(_grid_size(low, high, step))

        rules.append(rule)

    if not any(r["mutable"] for r in rules):
        blockers.append({
            "code": "NO_MUTABLE_COMPONENT",
            "message": (
                "Every baseline component is the matrix, redacted, amount-less or a dopant, so no "
                "component can be varied."
            ),
            "fix": (
                "Record at least one additive or reinforcement on the baseline material with a "
                "numeric amount, or build the search space manually."
            ),
        })

    # Widen the step until the enumerated grid fits inside the safe limit. Coarsening the grid is
    # the right response to an oversized space: narrowing the bands would silently discard the
    # region of the space the user most likely wants to explore.
    cardinality = 1
    for size in mutable_grids:
        cardinality *= max(size, 1)
    guard = 0
    while cardinality > _SAFE_ENUMERATION and guard < 8:
        guard += 1
        step *= 2
        mutable_grids = []
        for rule in rules:
            if rule["mutable"]:
                rule["step_amount"] = step
                mutable_grids.append(_grid_size(rule["min_amount"], rule["max_amount"], step))
        cardinality = 1
        for size in mutable_grids:
            cardinality *= max(size, 1)
        notes.append(f"Step widened to {step:g} to keep the enumerated space under {_SAFE_ENUMERATION}.")

    if cardinality > min(int(defaults["maximum_enumeration"]), HARD_MAX_ENUMERATION):
        blockers.append({
            "code": "SEARCH_SPACE_TOO_LARGE",
            "message": f"Even at the widest automatic step the space enumerates to {cardinality} combinations.",
            "fix": "Reduce the number of varying components, or build the search space manually with tighter bands.",
        })

    process_rules = [
        {**pr, "locked": False, "metadata": {"derived_from": "family_default"}}
        for pr in defaults.get("process_rules", [])
    ]

    return {
        "derivable": not blockers,
        "blockers": blockers,
        "notes": notes,
        "baseline_material": {
            "id": baseline.id, "display_name": baseline.display_name,
            "material_family": baseline.material_family, "component_count": len(baseline.components),
        },
        "material_family": baseline.material_family,
        "amount_basis": basis,
        "balance_component_key": next(
            (r["component_key"] for r in rules if r["baseline_component_id"] == matrix.id), None
        ),
        "total_target": float(defaults["total_target"]),
        "max_component_count": int(defaults["max_component_count"]),
        "candidate_budget": int(defaults["candidate_budget"]),
        "maximum_enumeration": int(defaults["maximum_enumeration"]),
        "component_rules": rules,
        "process_rules": process_rules,
        "estimated_cardinality": cardinality if mutable_grids else 0,
    }


def derive_search_space(
    db: Session, project: ReplacementProject, *, activate: bool = True, notes: str | None = None,
) -> dict[str, Any]:
    """Create — and by default activate — a search space derived from the baseline composition."""
    preview = derivation_preview(db, project)
    if not preview["derivable"]:
        return {"created": False, "preview": preview, "search_space": None, "validation": None}

    latest = (
        db.query(CandidateSearchSpace).filter_by(project_id=project.id)
        .order_by(CandidateSearchSpace.version.desc()).first()
    )
    row = CandidateSearchSpace(
        project_id=project.id,
        organisation_id=project.organisation_id,
        version=(latest.version + 1 if latest else 1),
        material_family=preview["material_family"],
        amount_basis=preview["amount_basis"],
        balance_component_key=preview["balance_component_key"],
        total_target=preview["total_target"],
        total_tolerance=0.001,
        max_component_count=preview["max_component_count"],
        candidate_budget=preview["candidate_budget"],
        maximum_enumeration=preview["maximum_enumeration"],
        notes=notes or "Derived from the baseline material composition by the intake bench.",
        active=False,
        checksum="pending",
        metadata_json={"derived": True, "derivation_version": "bench_v1", "notes": preview.get("notes", [])},
    )
    db.add(row)
    db.flush()

    for rule in preview["component_rules"]:
        metadata = rule.pop("metadata", {})
        db.add(SearchSpaceComponentRule(search_space_id=row.id, **rule, metadata_json=metadata))
    for process_rule in preview["process_rules"]:
        metadata = process_rule.pop("metadata", {})
        db.add(SearchSpaceProcessRule(search_space_id=row.id, **process_rule, metadata_json=metadata))

    db.flush()
    db.refresh(row, ["component_rules", "process_rules"])
    row.checksum = search_space_checksum(row)
    db.flush()

    validation = validate_search_space(db, row, "bounded_composition_variation")
    if activate and validation["valid"]:
        db.query(CandidateSearchSpace).filter_by(project_id=project.id).update(
            {CandidateSearchSpace.active: False}
        )
        row.active = True

    db.commit()
    return {
        "created": True,
        "activated": bool(activate and validation["valid"]),
        "preview": preview,
        "search_space": get_search_space(db, row.id),
        "validation": validation,
    }
