"""Phase-6 scientific representation layer.

A formulation name such as "Base Resin A + Modifier B2 + Reinforcement C" is not enough
information to run DFT or molecular dynamics. This module turns a submitted payload into a
normalized, checksummed representation and states *separately*:

  1. syntax parse status      -- did the payload parse against the declared format?
  2. structural completeness  -- does it contain everything the format requires?
  3. method applicability     -- decided later by the router, never here.

Nothing in this module infers atoms, topology, force fields, phases or boundary conditions.
A file that parses is not thereby chemically correct, and we never claim it is.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import (
    RepresentationCompleteness,
    RepresentationType,
    RepresentationValidationStatus,
)

REPRESENTATION_CONTRACT_VERSION = "representation-v1"
MAX_REPRESENTATION_BYTES = 512_000
MAX_ATOM_COUNT = 512

# Element symbols accepted by the structural validators. Deliberately an explicit allowlist:
# an unrecognised symbol is a validation error, never a silently accepted "custom element".
ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S", "Cl",
    "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As",
    "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd", "Ag", "Cd", "In",
    "Sn", "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb",
    "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl",
    "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa", "U",
}

SAFE_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


class RepresentationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _finite(value: Any, path: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RepresentationError(f"{path} must be numeric") from exc
    if not math.isfinite(number):
        raise RepresentationError(f"{path} must be finite")
    return float(f"{number:.12g}")


@dataclass
class ValidationOutcome:
    """Syntax, completeness and derived structure are reported separately and never merged."""
    validation_status: str
    completeness_status: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    normalized_content: dict[str, Any] = field(default_factory=dict)
    periodicity: str | None = None
    dimensionality: int | None = None
    atom_count: int | None = None
    component_count: int | None = None
    chemical_elements: list[str] = field(default_factory=list)
    redaction_flags: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return (
            self.validation_status == RepresentationValidationStatus.VALID
            and self.completeness_status == RepresentationCompleteness.COMPLETE
        )


class RepresentationValidator:
    """Deterministic, format-specific validator. Subclasses never guess missing science."""

    key: str = "abstract"
    version: str = "1.0"
    representation_type: str = RepresentationType.FORMULATION_ONLY

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:  # pragma: no cover - abstract
        raise NotImplementedError


class SoftwareFixtureValidator(RepresentationValidator):
    """Reduced-unit numerical fixture used to validate the operating system, not materials science."""

    key = "software_fixture_json_v1"
    version = "1.0"
    representation_type = RepresentationType.SOFTWARE_VALIDATION_FIXTURE

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:
        messages: list[dict[str, Any]] = []
        fixture_key = content.get("fixture_key")
        if not isinstance(fixture_key, str) or not SAFE_KEY_PATTERN.match(fixture_key):
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "FIXTURE_KEY_INVALID", "path": "fixture_key", "message": "A safe fixture_key string is required."}],
            )
        params = content.get("parameters")
        if not isinstance(params, dict):
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "PARAMETERS_INVALID", "path": "parameters", "message": "parameters must be an object."}],
            )
        required = ("stiffness", "initial_displacement")
        missing = [k for k in required if k not in params]
        normalized_params = {k: _finite(v, f"parameters.{k}") for k, v in sorted(params.items())}
        if normalized_params.get("stiffness", 1.0) <= 0:
            messages.append({"code": "NON_POSITIVE_STIFFNESS", "path": "parameters.stiffness",
                             "message": "Reduced-unit stiffness must be positive."})
            return ValidationOutcome(RepresentationValidationStatus.STRUCTURALLY_INVALID,
                                     RepresentationCompleteness.INCOMPLETE, messages)
        normalized = {
            "fixture_key": fixture_key,
            "parameters": normalized_params,
            "unit_basis": "reduced_dimensionless",
            "declaration": "SOFTWARE VALIDATION SIMULATION FIXTURE — not a validated real-material physics model.",
        }
        if missing:
            messages.append({"code": "INCOMPLETE_FIXTURE_PARAMETERS", "path": "parameters",
                             "message": f"Missing required reduced-unit parameters: {', '.join(missing)}."})
            return ValidationOutcome(RepresentationValidationStatus.VALID,
                                     RepresentationCompleteness.INCOMPLETE, messages, normalized)
        return ValidationOutcome(
            RepresentationValidationStatus.VALID, RepresentationCompleteness.COMPLETE, messages, normalized,
            periodicity="not_applicable", dimensionality=0, atom_count=None, component_count=len(normalized_params),
        )


class PeriodicStructureValidator(RepresentationValidator):
    """Periodic crystal cell: 3x3 lattice in angstrom plus fractional sites with known elements."""

    key = "periodic_structure_json_v1"
    version = "1.0"
    representation_type = RepresentationType.PERIODIC_ATOMIC_STRUCTURE

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:
        messages: list[dict[str, Any]] = []
        lattice = content.get("lattice_vectors")
        sites = content.get("sites")
        if not isinstance(lattice, list) or len(lattice) != 3 or not all(isinstance(r, list) and len(r) == 3 for r in lattice):
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "LATTICE_INVALID", "path": "lattice_vectors",
                  "message": "lattice_vectors must be a 3x3 array of numbers in angstrom."}],
            )
        if not isinstance(sites, list) or not sites:
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "SITES_MISSING", "path": "sites", "message": "At least one atomic site is required."}],
            )
        if len(sites) > MAX_ATOM_COUNT:
            return ValidationOutcome(
                RepresentationValidationStatus.STRUCTURALLY_INVALID, RepresentationCompleteness.INCOMPLETE,
                [{"code": "TOO_MANY_SITES", "path": "sites",
                  "message": f"Phase-6 local routes are bounded to {MAX_ATOM_COUNT} atomic sites."}],
            )
        unit = str(content.get("lattice_unit", "angstrom"))
        if unit != "angstrom":
            return ValidationOutcome(
                RepresentationValidationStatus.STRUCTURALLY_INVALID, RepresentationCompleteness.INCOMPLETE,
                [{"code": "LATTICE_UNIT_UNSUPPORTED", "path": "lattice_unit",
                  "message": "Lattice vectors must be supplied in angstrom; units are never reinterpreted."}],
            )
        normalized_lattice = [[_finite(v, f"lattice_vectors[{i}][{j}]") for j, v in enumerate(row)] for i, row in enumerate(lattice)]
        normalized_sites: list[dict[str, Any]] = []
        elements: set[str] = set()
        for index, site in enumerate(sites):
            if not isinstance(site, dict):
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "SITE_INVALID", "path": f"sites[{index}]", "message": "Each site must be an object."}],
                )
            element = str(site.get("element", "")).strip()
            if element not in ELEMENT_SYMBOLS:
                return ValidationOutcome(
                    RepresentationValidationStatus.STRUCTURALLY_INVALID, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "UNKNOWN_ELEMENT", "path": f"sites[{index}].element",
                      "message": f"Element symbol '{element}' is not recognised; atom identity is never inferred."}],
                )
            coords = site.get("fractional_coordinates")
            if not isinstance(coords, list) or len(coords) != 3:
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "COORDINATES_INVALID", "path": f"sites[{index}].fractional_coordinates",
                      "message": "Exactly three fractional coordinates are required."}],
                )
            normalized_sites.append({
                "element": element,
                "fractional_coordinates": [_finite(c, f"sites[{index}].fractional_coordinates") for c in coords],
            })
            elements.add(element)
        # Stable ordering makes the checksum independent of submission order without altering science.
        normalized_sites.sort(key=lambda s: (s["element"], s["fractional_coordinates"]))
        normalized = {
            "lattice_vectors": normalized_lattice,
            "lattice_unit": "angstrom",
            "sites": normalized_sites,
            "periodicity": "3d",
            "space_group_number": content.get("space_group_number"),
        }
        if content.get("space_group_number") is None:
            messages.append({"code": "SPACE_GROUP_NOT_SUPPLIED", "path": "space_group_number",
                             "message": "Space group was not supplied; symmetry is not inferred from coordinates."})
        return ValidationOutcome(
            RepresentationValidationStatus.VALID, RepresentationCompleteness.COMPLETE, messages, normalized,
            periodicity="3d", dimensionality=3, atom_count=len(normalized_sites),
            component_count=len(elements), chemical_elements=sorted(elements),
        )


class MolecularTopologyValidator(RepresentationValidator):
    """Atomistic topology: typed atoms, bonds and an explicit force-field mapping key."""

    key = "atomistic_topology_json_v1"
    version = "1.0"
    representation_type = RepresentationType.MOLECULAR_TOPOLOGY

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:
        messages: list[dict[str, Any]] = []
        atoms = content.get("atoms")
        atom_types = content.get("atom_types")
        box = content.get("box")
        if not isinstance(atoms, list) or not atoms or not isinstance(atom_types, list) or not atom_types:
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "TOPOLOGY_INVALID", "path": "atoms",
                  "message": "atoms and atom_types arrays are both required."}],
            )
        if len(atoms) > MAX_ATOM_COUNT:
            return ValidationOutcome(
                RepresentationValidationStatus.STRUCTURALLY_INVALID, RepresentationCompleteness.INCOMPLETE,
                [{"code": "TOO_MANY_ATOMS", "path": "atoms",
                  "message": f"Phase-6 local routes are bounded to {MAX_ATOM_COUNT} atoms."}],
            )
        type_ids: set[int] = set()
        normalized_types: list[dict[str, Any]] = []
        for index, entry in enumerate(atom_types):
            if not isinstance(entry, dict):
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "ATOM_TYPE_INVALID", "path": f"atom_types[{index}]", "message": "Each atom type must be an object."}],
                )
            type_id = entry.get("id")
            if not isinstance(type_id, int):
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "ATOM_TYPE_ID_INVALID", "path": f"atom_types[{index}].id", "message": "Integer atom type id required."}],
                )
            type_ids.add(type_id)
            normalized_types.append({
                "id": type_id, "label": str(entry.get("label", f"type{type_id}")),
                "mass_amu": _finite(entry.get("mass_amu", 0.0), f"atom_types[{index}].mass_amu"),
            })
        normalized_atoms: list[dict[str, Any]] = []
        for index, atom in enumerate(atoms):
            if not isinstance(atom, dict) or atom.get("type") not in type_ids:
                return ValidationOutcome(
                    RepresentationValidationStatus.STRUCTURALLY_INVALID, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "ATOM_TYPE_UNMAPPED", "path": f"atoms[{index}].type",
                      "message": "Every atom must reference a declared atom type; types are never invented."}],
                )
            position = atom.get("position")
            if not isinstance(position, list) or len(position) != 3:
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "ATOM_POSITION_INVALID", "path": f"atoms[{index}].position",
                      "message": "Three cartesian coordinates in angstrom are required."}],
                )
            normalized_atoms.append({
                "id": int(atom.get("id", index + 1)), "type": int(atom["type"]),
                "position": [_finite(c, f"atoms[{index}].position") for c in position],
            })
        normalized_atoms.sort(key=lambda a: int(a["id"]))
        force_field_key = content.get("force_field_key")
        outcome_messages = list(messages)
        completeness = RepresentationCompleteness.COMPLETE
        if not isinstance(force_field_key, str) or not SAFE_KEY_PATTERN.match(force_field_key):
            outcome_messages.append({
                "code": "FORCE_FIELD_MAPPING_MISSING", "path": "force_field_key",
                "message": "An explicit force-field mapping key is required; potentials are never inferred from labels.",
            })
            completeness = RepresentationCompleteness.INCOMPLETE
        if not isinstance(box, list) or len(box) != 3:
            outcome_messages.append({"code": "BOX_MISSING", "path": "box",
                                     "message": "A three-component simulation box in angstrom is required."})
            completeness = RepresentationCompleteness.INCOMPLETE
        normalized = {
            "atom_types": sorted(normalized_types, key=lambda t: int(t["id"])),
            "atoms": normalized_atoms,
            "bonds": sorted(
                [[int(b[0]), int(b[1])] for b in content.get("bonds", []) if isinstance(b, list) and len(b) == 2]
            ),
            "box": [_finite(v, "box") for v in box] if isinstance(box, list) and len(box) == 3 else None,
            "box_unit": "angstrom",
            "force_field_key": force_field_key if isinstance(force_field_key, str) else None,
        }
        return ValidationOutcome(
            RepresentationValidationStatus.VALID, completeness, outcome_messages, normalized,
            periodicity=str(content.get("periodicity", "periodic")), dimensionality=3,
            atom_count=len(normalized_atoms), component_count=len(normalized_types),
        )


class PhaseDescriptionValidator(RepresentationValidator):
    """Component/phase description for future CALPHAD routing. No phase diagram is computed here."""

    key = "phase_description_json_v1"
    version = "1.0"
    representation_type = RepresentationType.PHASE_DESCRIPTION

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:
        components = content.get("components")
        if not isinstance(components, list) or not components:
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "COMPONENTS_MISSING", "path": "components", "message": "At least one component is required."}],
            )
        normalized_components: list[dict[str, Any]] = []
        for index, component in enumerate(components):
            if not isinstance(component, dict) or not str(component.get("element", "")).strip():
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "COMPONENT_INVALID", "path": f"components[{index}]",
                      "message": "Each component requires an element symbol."}],
                )
            normalized_components.append({
                "element": str(component["element"]).strip(),
                "mole_fraction": _finite(component.get("mole_fraction", 0.0), f"components[{index}].mole_fraction"),
            })
        normalized_components.sort(key=lambda c: str(c["element"]))
        phases = sorted({str(p) for p in content.get("phases", []) if str(p).strip()})
        messages: list[dict[str, Any]] = []
        completeness = RepresentationCompleteness.COMPLETE
        if not phases:
            messages.append({"code": "PHASES_NOT_DECLARED", "path": "phases",
                             "message": "Candidate phases must be declared; they are never inferred."})
            completeness = RepresentationCompleteness.INCOMPLETE
        normalized = {"components": normalized_components, "phases": phases,
                      "temperature_range_k": content.get("temperature_range_k")}
        return ValidationOutcome(
            RepresentationValidationStatus.VALID, completeness, messages, normalized,
            periodicity="not_applicable", dimensionality=0, component_count=len(normalized_components),
            chemical_elements=[c["element"] for c in normalized_components if c["element"] in ELEMENT_SYMBOLS],
        )


class FormulationOnlyValidator(RepresentationValidator):
    """Formulation-level composition. Explicitly and permanently inadequate for atomistic methods."""

    key = "formulation_summary_json_v1"
    version = "1.0"
    representation_type = RepresentationType.FORMULATION_ONLY

    def validate(self, content: dict[str, Any]) -> ValidationOutcome:
        components = content.get("components")
        if not isinstance(components, list) or not components:
            return ValidationOutcome(
                RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                [{"code": "COMPONENTS_MISSING", "path": "components", "message": "At least one component is required."}],
            )
        normalized_components: list[dict[str, Any]] = []
        redactions: list[str] = []
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "COMPONENT_INVALID", "path": f"components[{index}]", "message": "Each component must be an object."}],
                )
            key = str(component.get("component_key", "")).strip()
            if not key:
                return ValidationOutcome(
                    RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
                    [{"code": "COMPONENT_KEY_MISSING", "path": f"components[{index}].component_key",
                      "message": "component_key is required."}],
                )
            if component.get("is_redacted"):
                redactions.append(key)
            amount = component.get("amount")
            normalized_components.append({
                "component_key": key,
                "display_name": str(component.get("display_name", key)),
                "amount": _finite(amount, f"components[{index}].amount") if amount is not None else None,
                "unit": component.get("unit"),
                "basis": component.get("basis"),
                "is_redacted": bool(component.get("is_redacted")),
            })
        normalized_components.sort(key=lambda c: str(c["component_key"]))
        normalized = {
            "components": normalized_components,
            "atomistic_detail_present": False,
            "declaration": "Formulation-level composition only. Atomic identities, topology and force-field "
                           "mappings are absent and are never inferred from component labels.",
        }
        return ValidationOutcome(
            RepresentationValidationStatus.VALID,
            RepresentationCompleteness.REDACTED if redactions else RepresentationCompleteness.COMPLETE,
            [{"code": "FORMULATION_ONLY", "path": "components",
              "message": "This representation is adequate for bookkeeping only; atomistic methods must refuse it."}],
            normalized, periodicity="not_applicable", dimensionality=0,
            component_count=len(normalized_components),
            redaction_flags=[f"redacted_component:{k}" for k in sorted(redactions)],
        )


VALIDATORS: dict[str, RepresentationValidator] = {
    v.key: v for v in (
        SoftwareFixtureValidator(),
        PeriodicStructureValidator(),
        MolecularTopologyValidator(),
        PhaseDescriptionValidator(),
        FormulationOnlyValidator(),
    )
}

# A representation format implies its type. Callers cannot relabel a formulation as a crystal.
FORMAT_TO_TYPE: dict[str, str] = {key: validator.representation_type for key, validator in VALIDATORS.items()}


def supported_formats() -> list[dict[str, str]]:
    return [
        {"format": v.key, "validator_version": v.version, "representation_type": v.representation_type}
        for v in sorted(VALIDATORS.values(), key=lambda x: x.key)
    ]


def validate_representation(representation_format: str, content: dict[str, Any]) -> tuple[RepresentationValidator, ValidationOutcome]:
    validator = VALIDATORS.get(representation_format)
    if validator is None:
        raise RepresentationError(f"Unsupported representation format: {representation_format}")
    payload = canonical_json(content)
    if len(payload.encode()) > MAX_REPRESENTATION_BYTES:
        raise RepresentationError(
            f"Representation payload exceeds the {MAX_REPRESENTATION_BYTES}-byte Phase-6 bound"
        )
    try:
        outcome = validator.validate(content)
    except RepresentationError as exc:
        outcome = ValidationOutcome(
            RepresentationValidationStatus.INVALID_SYNTAX, RepresentationCompleteness.INCOMPLETE,
            [{"code": "PARSE_ERROR", "path": "content", "message": str(exc)}],
        )
    return validator, outcome


def representation_checksum(
    representation_format: str, validator_key: str, validator_version: str, normalized_content: dict[str, Any]
) -> str:
    """Content identity only. Labels, timestamps and ownership never take part."""
    return checksum({
        "contract": REPRESENTATION_CONTRACT_VERSION,
        "format": representation_format,
        "validator": [validator_key, validator_version],
        "content": normalized_content,
    })
