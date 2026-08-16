from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.domain.material_identity import (
    IdentityConflict,
    IdentityConflictSeverity,
    IdentityCompleteness,
    MaterialIdentityConflict,
    composition_fingerprint,
    differing_identity_dimensions,
    engineering_identity_fingerprint,
    normalize_composition,
)
from app.models.entities import Material
from app.models.material_identity import MaterialIdentityV13
from app.schemas.material_identity import MaterialIdentityV13Create


def create_or_replace_identity(
    db: Session,
    *,
    material_id: str,
    payload: MaterialIdentityV13Create,
    review_required: bool = True,
) -> MaterialIdentityV13:
    material = db.get(Material, material_id)
    if material is None:
        raise ValueError(f"material not found: {material_id}")

    normalized = normalize_composition(payload.composition)
    comp_fp = composition_fingerprint(normalized) if normalized else None
    identity_fp = (
        engineering_identity_fingerprint(
            composition=normalized,
            phase_polytype=payload.phase_polytype,
            microstructure=payload.microstructure,
            processing_route=payload.processing_route,
            form_factor=payload.form_factor,
            crystallographic_orientation=payload.crystallographic_orientation,
            defect_state=payload.defect_state,
        )
        if normalized
        else None
    )

    identity = (
        db.query(MaterialIdentityV13)
        .filter(MaterialIdentityV13.material_id == material_id)
        .one_or_none()
    )
    if identity is None:
        identity = MaterialIdentityV13(material_id=material_id)
        db.add(identity)

    identity.composition = normalized
    identity.composition_basis = payload.composition_basis
    identity.composition_fingerprint = comp_fp
    identity.phase_polytype = payload.phase_polytype
    identity.microstructure = payload.microstructure
    identity.processing_route = payload.processing_route
    identity.form_factor = payload.form_factor
    identity.crystallographic_orientation = payload.crystallographic_orientation
    identity.defect_state = payload.defect_state
    identity.symmetry_class = payload.symmetry_class
    identity.direction_required_for = sorted(set(payload.direction_required_for))
    identity.identity_fingerprint = identity_fp
    identity.completeness = payload.completeness.value
    identity.review_required = review_required
    identity.confidence = payload.confidence
    identity.source_ref = payload.source_ref
    db.flush()
    return identity


def materialize_legacy_identity(db: Session, material: Material) -> MaterialIdentityV13:
    """Create an explicit unknown identity shell without parsing prose into scientific facts."""
    existing = (
        db.query(MaterialIdentityV13)
        .filter(MaterialIdentityV13.material_id == material.id)
        .one_or_none()
    )
    if existing is not None:
        return existing

    identity = MaterialIdentityV13(
        material_id=material.id,
        composition={},
        composition_basis="unknown",
        composition_fingerprint=None,
        phase_polytype={},
        microstructure={},
        processing_route={},
        form_factor={},
        crystallographic_orientation={},
        defect_state={},
        symmetry_class=None,
        direction_required_for=[],
        identity_fingerprint=None,
        completeness=IdentityCompleteness.LEGACY_UNKNOWN.value,
        review_required=True,
        migration_metadata={
            "source": "materials",
            "legacy_material_id": material.id,
            "composition_summary_not_parsed": bool(material.composition_summary),
            "reason": "free-text legacy identity cannot be converted to structured identity without review",
        },
    )
    db.add(identity)
    db.flush()
    return identity


def find_identity_conflicts(
    db: Session,
    material_ids: Iterable[str],
) -> list[IdentityConflict]:
    ids = list(dict.fromkeys(material_ids))
    identities = (
        db.query(MaterialIdentityV13)
        .filter(MaterialIdentityV13.material_id.in_(ids))
        .all()
        if ids
        else []
    )
    by_composition: dict[str, list[MaterialIdentityV13]] = {}
    for identity in identities:
        if identity.composition_fingerprint:
            by_composition.setdefault(identity.composition_fingerprint, []).append(identity)

    conflicts: list[IdentityConflict] = []
    for comp_fp, group in by_composition.items():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                differing = differing_identity_dimensions(left, right)
                if differing:
                    conflicts.append(
                        IdentityConflict(
                            left_material_id=left.material_id,
                            right_material_id=right.material_id,
                            composition_fingerprint=comp_fp,
                            differing_dimensions=differing,
                            severity=IdentityConflictSeverity.BLOCKING,
                        )
                    )
    return conflicts


def assert_no_identity_conflation(db: Session, material_ids: Iterable[str]) -> None:
    conflicts = find_identity_conflicts(db, material_ids)
    if not conflicts:
        return
    summary = "; ".join(
        f"{item.left_material_id} vs {item.right_material_id}: {','.join(item.differing_dimensions)}"
        for item in conflicts
    )
    raise MaterialIdentityConflict(f"same chemistry, distinct engineering identity: {summary}")


def property_direction_is_required(identity: MaterialIdentityV13, property_key: str) -> bool:
    return property_key in set(identity.direction_required_for or [])


def assert_directional_property_has_direction(
    identity: MaterialIdentityV13,
    *,
    property_key: str,
    direction: str | None,
) -> None:
    if property_direction_is_required(identity, property_key) and not direction:
        raise ValueError(
            f"property '{property_key}' is direction-sensitive for material {identity.material_id}; "
            "a scalar value without direction is not admissible evidence"
        )
