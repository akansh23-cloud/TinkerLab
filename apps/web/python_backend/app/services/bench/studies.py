"""Phase 12 — start a replacement study the way a programme actually starts.

The existing new-study wizard has eight steps and asks the user to type property keys and units
into free-text boxes before it will let them proceed. It then creates a project with no search
space, which means every lab it links to is dead on arrival.

This service does the whole thing in one call: project, requirements, objectives, and a derived and
activated search space. Requirements come from one of three places, and which one is recorded on
every requirement so a reviewer can see later where a number came from:

  application_preset   a template for the application class, with realistic opening values
  baseline_derived     thresholds computed from the incumbent's own measured properties
  explicit             typed by the user

BASELINE-DERIVED IS THE ONE THAT MATTERS. For a cost-out or dual-source programme the real
requirement is "hold what we already have". Deriving that from the incumbent's recorded evidence,
with a stated margin, is both more defensible and less work than typing numbers from memory — and
when the incumbent has no measured value for a property, the derivation says so instead of
inventing a threshold.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import ConstraintKind
from app.models.entities import (
    Constraint,
    Material,
    MaterialPropertyObservation,
    Objective,
    Organisation,
    ReplacementProject,
    User,
)
from app.services.bench.catalog import CATALOGUE_BY_KEY
from app.services.bench.derive import derive_search_space
from app.services.bench.intake import (
    IntakeError,
    PropertyEntry,
    ensure_property_definition,
    intake_material,
)
from app.services.bench.library import STARTER_LIBRARY
from app.services.bench.presets import PRESETS_BY_KEY
from app.services.bench.provenance import derivation_policy, provenance_category, provenance_label
from app.services.conflicts import detect_conflicts
from app.schemas.projects import ConstraintCreate, ObjectiveCreate
from app.services.validation import DomainValidationError, validate_constraint, validate_objective

# Requirement floors derived from the incumbent keep a margin: an exact match to the incumbent's
# measured value would eliminate any candidate that is one measurement's worth of scatter below it.
DEFAULT_MARGIN_FRACTION = 0.05


def _observations_by_key(db: Session, material_id: str) -> dict[str, MaterialPropertyObservation]:
    rows = (
        db.query(MaterialPropertyObservation)
        .options(selectinload(MaterialPropertyObservation.property_definition),
                 selectinload(MaterialPropertyObservation.evidence))
        .filter(MaterialPropertyObservation.material_id == material_id,
                MaterialPropertyObservation.status == "active")
        .order_by(MaterialPropertyObservation.curator_preferred.desc(),
                  MaterialPropertyObservation.confidence.desc().nullslast(),
                  MaterialPropertyObservation.created_at.desc())
        .all()
    )
    best: dict[str, MaterialPropertyObservation] = {}
    for row in rows:
        if row.property_definition is None:
            continue
        best.setdefault(row.property_definition.key, row)
    return best


def derive_requirements_from_baseline(
    db: Session, baseline: Material, *, property_keys: list[str] | None = None,
    margin_fraction: float = DEFAULT_MARGIN_FRACTION,
) -> dict[str, Any]:
    """Turn incumbent evidence into reviewable ``hold-or-improve`` requirements.

    Phase 12.2 deliberately refuses two unsafe shortcuts:
    * unresolved conflicting observations never become an automatic threshold;
    * boolean compliance properties use the catalogue's desirable polarity rather than copying the
      incumbent's True/False value (``SVHC present=True`` must never become a target state).

    Provenance also controls whether an automatically derived requirement may start as hard or must
    remain soft pending engineering review.
    """
    observed = _observations_by_key(db, baseline.id)
    keys = property_keys or sorted(observed.keys())
    requirements: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    unresolved_conflicts = {
        conflict["property_key"]: conflict
        for conflict in detect_conflicts(db, baseline.id)
        if conflict.get("resolution_state") == "unresolved"
    }

    for key in keys:
        observation = observed.get(key)
        spec = CATALOGUE_BY_KEY.get(key)
        if observation is None:
            skipped.append({
                "property_key": key,
                "reason": "The baseline has no recorded value for this property, so no threshold can be derived from it.",
            })
            continue
        if key in unresolved_conflicts:
            skipped.append({
                "property_key": key,
                "reason": "Baseline evidence conflicts for this property. Resolve or curate the conflict before deriving a requirement.",
            })
            continue

        evidence_type = observation.evidence.evidence_type if observation.evidence else None
        source_quality = observation.evidence.source_quality if observation.evidence else None
        strength, provenance_warning = derivation_policy(
            evidence_type=evidence_type, source_quality=source_quality,
        )
        category = provenance_category(evidence_type=evidence_type, source_quality=source_quality)
        if strength == "blocked":
            skipped.append({
                "property_key": key,
                "reason": provenance_warning or "Evidence provenance is insufficient for automatic derivation.",
            })
            continue
        if provenance_warning:
            warnings.append({"property_key": key, "code": "DERIVATION_REVIEW_REQUIRED", "message": provenance_warning})

        evidence_meta = {
            "observation_id": observation.id,
            "evidence_id": observation.evidence_id,
            "evidence_type": evidence_type,
            "source_quality": source_quality,
            "provenance_category": category,
            "provenance_label": provenance_label(category),
            "confidence": observation.confidence,
        }

        if observation.value_type == "boolean":
            if spec is None or spec.direction not in {"higher_is_better", "lower_is_better"}:
                skipped.append({
                    "property_key": key,
                    "reason": "This boolean property has no declared desirable polarity and must be set explicitly.",
                })
                continue
            desired = spec.direction == "higher_is_better"
            incumbent = bool(observation.boolean_value)
            state = "already satisfies" if incumbent == desired else "does not satisfy"
            requirements.append({
                "property_key": key, "comparator": "boolean",
                "target_boolean": desired, "target_unit": None,
                "hard_or_soft": strength, "weight": 1.0, "severity": 5,
                "rationale": (
                    f"Incumbent {state} the catalogue's desirable compliance state ({desired}); "
                    "a substitute must preserve or improve that state, never preserve an adverse state."
                ),
                "origin": "baseline_derived",
                "evidence": evidence_meta,
            })
            continue

        value = observation.numeric_value
        if value is None:
            skipped.append({"property_key": key, "reason": "Recorded observation has no numeric value."})
            continue

        direction = spec.direction if spec else "neutral"
        if direction == "higher_is_better":
            comparator, target = ">=", value * (1.0 - margin_fraction)
        elif direction == "lower_is_better":
            comparator, target = "<=", value * (1.0 + margin_fraction)
        else:
            skipped.append({
                "property_key": key,
                "reason": "No universally better direction for this property — the requirement depends on the "
                          "application, so it must be set explicitly rather than derived.",
            })
            continue

        requirements.append({
            "property_key": key, "comparator": comparator,
            "target_value": round(target, 6), "target_unit": observation.unit,
            "hard_or_soft": strength,
            "weight": 1.0, "severity": 4,
            "rationale": f"Incumbent records {value:g} {observation.unit or ''}".strip()
                         + f"; threshold set with a {margin_fraction:.0%} margin from {provenance_label(category).lower()} evidence.",
            "origin": "baseline_derived",
            "evidence": evidence_meta,
        })

    return {
        "requirements": requirements,
        "skipped": skipped,
        "warnings": warnings,
        "baseline_property_count": len(observed),
    }


def create_study(
    db: Session,
    *,
    name: str,
    baseline_material_id: str,
    organisation_id: str,
    created_by: str,
    drivers: list[str],
    description: str | None = None,
    preset_key: str | None = None,
    requirements: list[dict[str, Any]] | None = None,
    objectives: list[dict[str, Any]] | None = None,
    derive_from_baseline: bool = False,
    baseline_margin: float = DEFAULT_MARGIN_FRACTION,
    derive_space: bool = True,
) -> dict[str, Any]:
    baseline = (
        db.query(Material)
        .filter(
            Material.id == baseline_material_id,
            or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id),
        )
        .one_or_none()
    )
    if baseline is None:
        raise IntakeError("Baseline material not found in this organisation scope.")
    if db.get(Organisation, organisation_id) is None:
        raise IntakeError("Organisation not found.")
    creator = db.get(User, created_by)
    if creator is None or creator.organisation_id != organisation_id:
        raise IntakeError("Creating user not found in this organisation.")

    resolved: list[dict[str, Any]] = []
    resolved_objectives: list[dict[str, Any]] = []
    notes: list[str] = []
    skipped: list[dict[str, str]] = []

    preset = PRESETS_BY_KEY.get(preset_key) if preset_key else None
    if preset_key and preset is None:
        raise IntakeError(f"Unknown application preset '{preset_key}'.")
    if preset is not None:
        if preset.expected_family != baseline.material_family:
            notes.append(
                f"The '{preset.display_name}' preset is written for {preset.expected_family} baselines but this "
                f"baseline is a {baseline.material_family}. The requirement values will need review."
            )
        for template in preset.requirements:
            resolved.append({**template.as_dict(), "origin": "application_preset", "preset_key": preset.key})
        for template in preset.objectives:
            resolved_objectives.append({**template.as_dict(), "origin": "application_preset"})

    if derive_from_baseline:
        derived = derive_requirements_from_baseline(db, baseline, margin_fraction=baseline_margin)
        existing_keys = {r["property_key"] for r in resolved}
        for requirement in derived["requirements"]:
            if requirement["property_key"] in existing_keys:
                # An explicit application requirement outranks a "hold what we have" floor: the
                # application states what the part needs, the incumbent only states what it happens
                # to deliver.
                notes.append(
                    f"Baseline-derived floor for {requirement['property_key']} was not applied — the preset "
                    "already states an application requirement for it."
                )
                continue
            resolved.append(requirement)
        skipped.extend(derived["skipped"])
        notes.extend(w["message"] for w in derived.get("warnings", []))

    for requirement in requirements or []:
        resolved = [r for r in resolved if r["property_key"] != requirement.get("property_key")]
        resolved.append({**requirement, "origin": requirement.get("origin", "explicit")})
    for objective in objectives or []:
        resolved_objectives = [
            o for o in resolved_objectives if o["property_key"] != objective.get("property_key")
        ]
        resolved_objectives.append({**objective, "origin": objective.get("origin", "explicit")})

    if not resolved:
        raise IntakeError(
            "A study needs at least one requirement. Choose an application preset, derive requirements "
            "from the baseline, or supply them explicitly."
        )

    validated_requirements: list[tuple[dict[str, Any], ConstraintCreate]] = []
    rejected: list[dict[str, str]] = []
    for requirement in resolved:
        key = requirement.get("property_key")
        if not key:
            continue
        try:
            definition = ensure_property_definition(db, key)
            is_boolean = definition.quantity_type == "boolean"
            comparator = "boolean" if is_boolean else requirement.get("comparator", ">=")
            payload = ConstraintCreate(
                constraint_type=ConstraintKind.BOOLEAN if is_boolean else ConstraintKind.PROPERTY,
                property_key=key,
                comparator=comparator,
                target_value=None if is_boolean else requirement.get("target_value"),
                target_value_upper=None if is_boolean else requirement.get("target_value_upper"),
                target_boolean=requirement.get("target_boolean") if is_boolean else None,
                target_unit=None if is_boolean else (requirement.get("target_unit") or definition.canonical_unit),
                severity=int(requirement.get("severity", 4)),
                hard_or_soft=requirement.get("hard_or_soft", "hard"),
                weight=float(requirement.get("weight", 1.0)),
                description=requirement.get("rationale"),
                metadata={
                    "origin": requirement.get("origin", "explicit"),
                    "preset_key": requirement.get("preset_key"),
                    "evidence": requirement.get("evidence"),
                },
            )
            validate_constraint(db, payload)
            validated_requirements.append((requirement, payload))
        except (IntakeError, DomainValidationError, ValueError) as exc:
            # Explicit caller input is transactional: a malformed requirement must not create a
            # half-valid study. Internal preset/derived issues are surfaced just as loudly because
            # accepting them would be a release-data defect, not a user typo.
            raise IntakeError(f"Invalid requirement '{key or 'unknown'}': {exc}") from exc

    validated_objectives: list[tuple[dict[str, Any], ObjectiveCreate]] = []
    for objective in resolved_objectives:
        key = objective.get("property_key")
        if not key:
            continue
        try:
            definition = ensure_property_definition(db, key)
        except IntakeError as exc:
            raise IntakeError(f"Invalid objective '{key}': {exc}") from exc
        if definition.quantity_type == "boolean":
            rejected.append({
                "property_key": key,
                "reason": "A boolean compliance status cannot be an optimisation objective. It is a gate, "
                          "and treating it as a weighted score would let a strength margin trade against market access.",
            })
            continue
        try:
            payload = ObjectiveCreate(
                property_key=key,
                direction=objective.get("direction", "minimize"),
                target_value=objective.get("target_value"),
                target_unit=objective.get("target_unit") or definition.canonical_unit,
                weight=float(objective.get("weight", 1.0)),
                priority=int(objective.get("priority", 1)),
                description=objective.get("rationale"),
            )
            validate_objective(db, payload)
            validated_objectives.append((objective, payload))
        except (DomainValidationError, ValueError) as exc:
            raise IntakeError(f"Invalid objective '{key}': {exc}") from exc

    if not validated_requirements:
        raise IntakeError("The study has no valid requirements after validation.")

    project = ReplacementProject(
        id=str(uuid.uuid4()), organisation_id=organisation_id, name=name.strip(),
        description=description or (preset.summary if preset else None),
        baseline_material_id=baseline.id, replacement_reasons=sorted(set(drivers)) or ["custom"],
        status="draft", created_by=created_by,
    )
    db.add(project)
    db.flush()

    for requirement, payload in validated_requirements:
        db.add(Constraint(
            project_id=project.id,
            constraint_type=payload.constraint_type.value,
            property_key=payload.property_key,
            comparator=payload.comparator.value,
            target_value=payload.target_value,
            target_value_upper=payload.target_value_upper,
            target_boolean=payload.target_boolean,
            target_unit=payload.target_unit,
            severity=payload.severity,
            hard_or_soft=payload.hard_or_soft.value,
            weight=payload.weight,
            description=payload.description,
            metadata_json=payload.metadata,
        ))

    for _objective, payload in validated_objectives:
        db.add(Objective(
            project_id=project.id,
            property_key=payload.property_key,
            direction=payload.direction.value,
            target_value=payload.target_value,
            target_unit=payload.target_unit,
            weight=payload.weight,
            priority=payload.priority,
            description=payload.description,
        ))

    db.commit()
    db.refresh(project)

    space_result: dict[str, Any] | None = None
    if derive_space:
        space_result = derive_search_space(db, project, activate=True)
        if not space_result.get("created"):
            for blocker in space_result.get("preview", {}).get("blockers", []):
                notes.append(f"Search space not derived: {blocker.get('message')} {blocker.get('fix', '')}".strip())

    return {
        "project_id": project.id,
        "project_name": project.name,
        "requirement_count": db.query(Constraint).filter_by(project_id=project.id).count(),
        "objective_count": db.query(Objective).filter_by(project_id=project.id).count(),
        "search_space_created": bool(space_result and space_result.get("created")),
        "search_space_activated": bool(space_result and space_result.get("activated")),
        "search_space": (space_result or {}).get("search_space"),
        "preset": preset.as_dict() if preset else None,
        "notes": notes,
        "skipped_requirements": skipped,
        "rejected_requirements": rejected,
    }


def install_reference_library(
    db: Session, *, organisation_id: str | None = None, overwrite: bool = False,
) -> dict[str, Any]:
    """Install the reference material library. Idempotent, and safe to run against a live database.

    Deterministic UUID5 ids mean a re-run touches the same rows rather than creating duplicates,
    and an existing material is skipped rather than overwritten. Shared reference rows are immutable to
    tenants; organisation-specific measurements belong on tenant-owned materials/evidence overlays.
    """
    installed: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    warnings: list[dict[str, Any]] = []

    for entry in STARTER_LIBRARY:
        material_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"tinkerlab:library:{entry.key}"))
        existing = db.get(Material, material_id)
        if existing is not None and not overwrite:
            skipped.append({"key": entry.key, "reason": "already installed", "material_id": material_id})
            continue
        if existing is not None:
            skipped.append({"key": entry.key, "reason": "already installed; overwrite is not supported for shared reference data",
                            "material_id": material_id})
            continue

        properties = [
            PropertyEntry(
                property_key=key,
                value=float(payload[0]) if not isinstance(payload[0], bool) else None,
                boolean_value=payload[0] if isinstance(payload[0], bool) else None,
                unit=payload[1],
            )
            for key, payload in entry.properties.items()
        ]
        note = " ".join(entry.caveats) if entry.caveats else None
        try:
            result = intake_material(
                db,
                material_id=material_id,
                display_name=entry.display_name,
                canonical_name=f"library::{entry.key}",
                material_family=entry.family,
                description=entry.description,
                data_grade="handbook_typical",
                identifiers=[{"namespace": n, "value": v} for n, v in entry.identifiers],
                components=[
                    {"component_name": c[0], "component_role": c[1], "amount_value": c[2],
                     "amount_unit": c[3] or "%", "amount_basis": "weight_percent"}
                    for c in entry.components
                ],
                process_state={"state_label": entry.process_state, "process_name": entry.process_state}
                if entry.process_state else None,
                properties=properties,
                source_reference=(
                    "TinkerLab starter screening library — unpinned handbook-typical compilation; "
                    "not qualification evidence."
                ),
                note=note,
                organisation_id=organisation_id,
                visibility="public",
                is_seed_data=True,
            )
            installed.append({"key": entry.key, "material_id": result.material.id,
                              "display_name": entry.display_name})
            if result.warnings:
                warnings.extend(result.warnings)
        except IntakeError as exc:
            db.rollback()
            skipped.append({"key": entry.key, "reason": str(exc)})

    return {
        "installed_count": len(installed), "skipped_count": len(skipped),
        "installed": installed, "skipped": skipped, "warnings": warnings,
    }
