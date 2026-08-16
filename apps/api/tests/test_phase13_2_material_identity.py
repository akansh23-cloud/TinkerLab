import uuid

import pytest

from app.domain.material_identity import MaterialIdentityConflict
from app.models.entities import Material
from app.schemas.material_identity import MaterialIdentityV13Create
from app.services.material_identity import (
    assert_directional_property_has_direction,
    assert_no_identity_conflation,
    create_or_replace_identity,
    materialize_legacy_identity,
)


def _material(db, name: str) -> Material:
    suffix = uuid.uuid4().hex[:8]
    material = Material(
        canonical_name=f"{name}-{suffix}",
        display_name=name,
        material_family="semiconductor",
        source_type="test",
        visibility="public",
    )
    db.add(material)
    db.flush()
    return material


def test_sintered_sic_and_4h_sic_are_blocking_identity_conflict(db):
    ceramic = _material(db, "Sintered SiC")
    epitaxy = _material(db, "4H-SiC epitaxial wafer")

    common_composition = {"Si": 1.0, "C": 1.0}
    create_or_replace_identity(
        db,
        material_id=ceramic.id,
        payload=MaterialIdentityV13Create(
            composition=common_composition,
            phase_polytype={"phase": "SiC", "polytype": "mixed_or_unspecified"},
            microstructure={"kind": "polycrystalline", "porosity_fraction": 0.03},
            processing_route={"route": "pressureless_sintering"},
            form_factor={"kind": "bulk_ceramic"},
            crystallographic_orientation={"texture": "random"},
            defect_state={"flaw_population": "ceramic"},
        ),
    )
    create_or_replace_identity(
        db,
        material_id=epitaxy.id,
        payload=MaterialIdentityV13Create(
            composition=common_composition,
            phase_polytype={"phase": "SiC", "polytype": "4H"},
            microstructure={"kind": "single_crystal_epitaxy", "porosity_fraction": 0.0},
            processing_route={"route": "epitaxial_growth"},
            form_factor={"kind": "wafer_epilayer"},
            crystallographic_orientation={"axis": "c"},
            defect_state={"micropipe_density": "declared_separately"},
        ),
    )

    with pytest.raises(MaterialIdentityConflict):
        assert_no_identity_conflation(db, [ceramic.id, epitaxy.id])


def test_legacy_identity_never_parses_composition_summary(db):
    material = _material(db, "Legacy SiC")
    material.composition_summary = "SiC, probably 4H, vendor prose only"
    db.flush()

    identity = materialize_legacy_identity(db, material)
    assert identity.composition == {}
    assert identity.composition_fingerprint is None
    assert identity.identity_fingerprint is None
    assert identity.completeness == "LEGACY_UNKNOWN"
    assert identity.review_required is True
    assert identity.migration_metadata["composition_summary_not_parsed"] is True


def test_direction_policy_is_property_specific(db):
    material = _material(db, "4H-SiC directional fixture")
    identity = create_or_replace_identity(
        db,
        material_id=material.id,
        payload=MaterialIdentityV13Create(
            composition={"Si": 1.0, "C": 1.0},
            phase_polytype={"polytype": "4H"},
            crystallographic_orientation={"axis": "c"},
            direction_required_for=["thermal_conductivity"],
        ),
    )

    with pytest.raises(ValueError):
        assert_directional_property_has_direction(
            identity,
            property_key="thermal_conductivity",
            direction=None,
        )

    result = assert_directional_property_has_direction(
        identity,
        property_key="band_gap",
        direction=None,
    )
    assert result is None
