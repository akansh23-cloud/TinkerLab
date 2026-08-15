"""Explicit, idempotent flagship demonstration installer.

Deployment bootstrap deliberately installs only schema + organisation + the public reference library.
This module is a separate user-triggered path that installs a clearly labelled synthetic programme
showing the three outcomes TinkerLab must be able to defend: ADVANCE, REJECT, and HOLD FOR EVIDENCE.

No real material receives fabricated properties. The incumbent silicon material is created only as
an identity/state anchor; its property values remain UNKNOWN in the demonstration database.
"""
from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from app.db.seed_phase10 import seed_phase10
from app.models.entities import (
    Material,
    MaterialPropertyDefinition,
    MaterialState,
    Organisation,
    ReplacementProgram,
    ReplacementProject,
    User,
)
from app.services.material_states import create_material_state

NS = uuid.UUID("b76d594b-c7a5-46a2-b836-3c82d33c9bf0")


def sid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


_REQUIRED_PROPERTIES = [
    ("band_gap", "Electronic band gap", "energy", "eV"),
    ("thermal_conductivity", "Thermal conductivity", "thermal_conductivity", "W/(m*K)"),
    ("breakdown_field", "Dielectric breakdown field", "electric_field", "MV/cm"),
    ("electron_mobility", "Electron mobility", "mobility", "cm^2/(V*s)"),
]


def _ensure_property_definitions(db: Session) -> None:
    comparators = ["<", "<=", "=", ">=", ">", "between"]
    for key, display, quantity, unit in _REQUIRED_PROPERTIES:
        if db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none() is not None:
            continue
        db.add(MaterialPropertyDefinition(
            id=sid(f"prop:{key}"),
            key=key,
            display_name=display,
            quantity_type=quantity,
            canonical_unit=unit,
            description=f"Controlled property definition for {display.lower()}.",
            applicable_material_families=["crystalline_inorganic", "ceramic", "semiconductor"],
            allowed_comparators=comparators,
            allow_negative=False,
            conflict_policy="informational",
        ))
    db.commit()


def _ensure_incumbent(db: Session, organisation_id: str) -> None:
    silicon_id = sid("material:silicon")
    if db.get(Material, silicon_id) is None:
        db.add(Material(
            id=silicon_id,
            canonical_name="silicon",
            display_name="Silicon (crystalline, diamond cubic)",
            material_family="crystalline_inorganic",
            description=(
                "Incumbent identity used by the flagship demonstration. TinkerLab deliberately "
                "does not seed silicon property values here; missing incumbent values remain UNKNOWN."
            ),
            composition_summary="Si",
            source_type="seed_reference",
            is_seed_data=True,
            owner_organisation_id=None,
            visibility="public",
        ))
        db.commit()

    state_id = sid("phase8:state:silicon-single-crystal-300k")
    if db.get(MaterialState, state_id) is None:
        create_material_state(
            db,
            organisation_id=organisation_id,
            material_id=silicon_id,
            label="Single-crystal silicon, diamond cubic, undoped, 300 K",
            description="Reference incumbent state for the flagship replacement demonstration.",
            composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}],
            crystal_system="cubic",
            space_group_number=227,
            space_group_symbol="Fd-3m",
            polymorph="diamond_cubic",
            phase="solid",
            temperature_k=300.0,
            pressure_pa=101325.0,
            environment="inert",
            is_reference_state=True,
            provenance_note=(
                "Declared demonstration reference state. This row defines identity and conditions, "
                "not a measured material property."
            ),
            row_id=state_id,
        )
        db.commit()


def install_flagship_demo(db: Session, *, organisation_id: str) -> dict[str, object]:
    org = db.get(Organisation, organisation_id)
    if org is None:
        raise ValueError("Organisation not found")

    user_id = sid("user")
    user = db.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            organisation_id=organisation_id,
            display_name="Demo Scientist",
            email="scientist@demo.tinkerlab.local",
        )
        db.add(user)
        db.commit()

    _ensure_property_definitions(db)
    _ensure_incumbent(db, organisation_id)
    seed_phase10(db, org, user, sid)

    project_id = sid("phase10:project")
    program_id = sid("phase10:program")
    project = db.get(ReplacementProject, project_id)
    program = db.get(ReplacementProgram, program_id)
    if project is None or program is None:
        raise RuntimeError("Flagship demonstration did not finish installing")

    return {
        "status": "ready",
        "project_id": project_id,
        "program_id": program_id,
        "project_name": project.name,
        "program_name": program.name,
        "is_demonstration_data": True,
        "story": {
            "problem": "Replace silicon in a 525 K / 3.3 kV switching application.",
            "candidate_a": "ADVANCE — blocking requirements are supported by consistent replicated evidence.",
            "candidate_b": "REJECT — replicated breakdown-field measurements fail a blocking threshold.",
            "candidate_c": "HOLD — critical evidence is missing, so the engine proposes the next test instead of guessing.",
        },
    }
