"""Phase-8 material states and structural identity.

Two ideas do the work here:

  **A property belongs to a material in a state.** 'Silicon' is not a state; 'single-crystal
  silicon, diamond cubic, undoped, at 300 K' is. When the reasoning engine looks for evidence it
  must know whether the evidence's state is the state being asked about, and when it cannot show
  compatibility it reports STATE_MISMATCH rather than borrowing the number.

  **Structural identity is not composition.** Diamond and graphite are both carbon. Their
  composition signatures match and their structure identities do not, so no code path here treats
  a shared formula as evidence of a shared structure.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import ComponentRole, StateMatchQuality
from app.models.entities import (
    MaterialState,
    MicrostructureDescriptor,
    ProcessingHistory,
    ProcessingStep,
    ScientificRepresentation,
    StateCompositionComponent,
)

STATE_CONTRACT_VERSION = "material-state-v1"
STRUCTURE_IDENTITY_VERSION = "structure-identity-v1"

# Conditions closer than these are treated as the same condition for state matching. They are
# tolerances for *identity*, not claims that properties are insensitive over the interval.
TEMPERATURE_TOLERANCE_K = 5.0
PRESSURE_RELATIVE_TOLERANCE = 0.05


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _round(value: float | None, digits: int = 8) -> float | None:
    if value is None:
        return None
    return float(f"{value:.{digits}g}")


class StateError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------------------------
def composition_signature(components: list[dict[str, Any]]) -> str:
    """Canonical composition identity that preserves declared quantities.

    Stoichiometric formulas retain the concise legacy representation, while alloy fractions and
    dopant concentrations are encoded explicitly so materially different formulations cannot alias.
    """
    ordered = sorted(components, key=lambda c: (str(c.get("element", "")), str(c.get("role", ""))))
    has_quantitative_nonstoich = any(
        c.get("atomic_fraction") is not None or c.get("atomic_fraction_min") is not None
        or c.get("atomic_fraction_max") is not None or c.get("concentration_value") is not None
        for c in ordered
    )
    if not has_quantitative_nonstoich:
        hosts: list[str] = []
        minors: list[str] = []
        for component in ordered:
            element = str(component.get("element", "")).strip()
            if not element:
                continue
            role = str(component.get("role") or ComponentRole.HOST)
            amount = component.get("stoichiometry")
            if role in {ComponentRole.HOST, ComponentRole.ALLOYING, ComponentRole.MATRIX, ComponentRole.REINFORCEMENT}:
                hosts.append(f"{element}{_format_amount(amount)}")
            else:
                minors.append(f"{element}[{role}]")
        signature = "".join(hosts) if hosts else "unspecified"
        return signature + ((":" + ",".join(minors)) if minors else "")

    parts: list[str] = []
    for component in ordered:
        element = str(component.get("element", "")).strip()
        if not element:
            continue
        role = str(component.get("role") or ComponentRole.HOST)
        qualifiers: list[str] = [f"role={role}"]
        for key, label in (("stoichiometry", "stoich"), ("atomic_fraction", "af"),
                           ("atomic_fraction_min", "af_min"), ("atomic_fraction_max", "af_max"),
                           ("concentration_value", "conc")):
            if component.get(key) is not None:
                qualifiers.append(f"{label}={_round(float(component[key])):g}")
        if component.get("concentration_value") is not None:
            qualifiers.append(f"conc_unit={component.get('concentration_unit') or 'unspecified'}")
        parts.append(f"{element}[{';'.join(qualifiers)}]")
    return "|".join(parts) if parts else "unspecified"

def _format_amount(amount: Any) -> str:
    if amount is None:
        return ""
    value = float(amount)
    if math.isclose(value, round(value), abs_tol=1e-9):
        rendered = str(int(round(value)))
        return "" if rendered == "1" else rendered
    return f"{value:g}"


def normalize_composition(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize for identity without destroying what was submitted.

    A stated range stays a range: it is never collapsed to a midpoint, because a midpoint is a
    number nobody measured.
    """
    normalized: list[dict[str, Any]] = []
    for component in components:
        element = str(component.get("element", "")).strip()
        if not element:
            raise StateError("Every composition component requires an element symbol")
        low = component.get("atomic_fraction_min")
        high = component.get("atomic_fraction_max")
        if low is not None and high is not None and float(low) > float(high):
            raise StateError(f"{element}: atomic_fraction_min exceeds atomic_fraction_max")
        normalized.append({
            "element": element,
            "role": str(component.get("role") or ComponentRole.HOST),
            "stoichiometry": _round(component.get("stoichiometry")),
            "atomic_fraction": _round(component.get("atomic_fraction")),
            "atomic_fraction_min": _round(low),
            "atomic_fraction_max": _round(high),
            "concentration_value": _round(component.get("concentration_value")),
            "concentration_unit": component.get("concentration_unit"),
            "original_representation": component.get("original_representation"),
        })
    normalized.sort(key=lambda c: (str(c["element"]), str(c["role"])))
    return normalized


# ---------------------------------------------------------------------------------------------
# Structural identity
# ---------------------------------------------------------------------------------------------
def structure_identity(
    representation: ScientificRepresentation | None,
    *, space_group_number: int | None = None, polymorph: str | None = None,
) -> tuple[str | None, str]:
    """Return (identity_hash, basis_description).

    The hash derives from an actual structural representation. When none exists there is NO
    structure identity — the function returns None rather than hashing the formula, because a
    formula-derived identity would make diamond and graphite indistinguishable.
    """
    if representation is None:
        return None, "no_structural_representation"
    if representation.representation_type != "periodic_atomic_structure":
        # A topology or formulation carries structural content but not a periodic cell identity.
        return checksum({
            "contract": STRUCTURE_IDENTITY_VERSION,
            "representation_checksum": representation.normalized_checksum,
            "representation_type": representation.representation_type,
        }), f"representation_checksum:{representation.representation_type}"

    content = representation.content or {}
    lattice = content.get("lattice_vectors")
    sites = content.get("sites") or []
    if not lattice or not sites:
        return None, "incomplete_periodic_structure"

    # Cell metrics (lengths and angles) rather than raw vectors, so an equivalent cell in a rotated
    # frame yields the same identity while a genuinely different cell does not.
    metrics = _cell_metrics(lattice)
    normalized_sites = sorted(
        ({"element": str(s["element"]), "coords": [_round(float(c), 6) for c in s["fractional_coordinates"]]}
         for s in sites),
        key=lambda s: (s["element"], s["coords"]),
    )
    return checksum({
        "contract": STRUCTURE_IDENTITY_VERSION,
        "cell_metrics": metrics,
        "sites": normalized_sites,
        "space_group_number": space_group_number or content.get("space_group_number"),
        "polymorph": polymorph,
    }), "periodic_cell_metrics_and_sites"


def _cell_metrics(lattice: list[list[float]]) -> dict[str, float | None]:
    def norm(v: list[float]) -> float:
        return math.sqrt(sum(float(x) ** 2 for x in v))

    def angle(u: list[float], v: list[float]) -> float:
        denominator = norm(u) * norm(v)
        if denominator == 0:
            return 0.0
        cosine = sum(float(a) * float(b) for a, b in zip(u, v, strict=True)) / denominator
        return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    a, b, c = lattice[0], lattice[1], lattice[2]
    return {
        "a": _round(norm(a), 6), "b": _round(norm(b), 6), "c": _round(norm(c), 6),
        "alpha": _round(angle(b, c), 4), "beta": _round(angle(a, c), 4), "gamma": _round(angle(a, b), 4),
    }


def state_checksum(payload: dict[str, Any]) -> str:
    return checksum({"contract": STATE_CONTRACT_VERSION, "state": payload})


def processing_history_checksum(steps: list[dict[str, Any]]) -> str:
    """Order matters: anneal-then-quench is not quench-then-anneal."""
    return checksum({
        "contract": "processing-history-v1",
        "steps": [
            {"sequence": index, "kind": step.get("step_kind"),
             "temperature_k": _round(step.get("temperature_k")),
             "duration_s": _round(step.get("duration_s")),
             "pressure_pa": _round(step.get("pressure_pa")),
             "atmosphere": step.get("atmosphere"),
             "cooling_rate_k_per_s": _round(step.get("cooling_rate_k_per_s")),
             "strain_fraction": _round(step.get("strain_fraction")),
             "parameters": step.get("parameters") or {}}
            for index, step in enumerate(steps)
        ],
    })


def microstructure_checksum(values: dict[str, Any]) -> str:
    return checksum({
        "contract": "microstructure-v1",
        "values": {k: _round(v) if isinstance(v, int | float) else v
                   for k, v in sorted(values.items()) if v is not None},
    })


# ---------------------------------------------------------------------------------------------
# State creation
# ---------------------------------------------------------------------------------------------
def create_processing_history(
    db: Session, *, organisation_id: str | None, display_name: str, steps: list[dict[str, Any]],
    key: str | None = None, description: str | None = None, row_id: str | None = None,
) -> ProcessingHistory:
    history = ProcessingHistory(
        organisation_id=organisation_id, key=key, display_name=display_name, description=description,
        history_checksum=processing_history_checksum(steps),
    )
    if row_id:
        history.id = row_id
    db.add(history)
    db.flush()
    for index, step in enumerate(steps):
        db.add(ProcessingStep(
            history_id=history.id, sequence=index, step_kind=str(step["step_kind"]),
            display_name=str(step.get("display_name") or step["step_kind"]),
            temperature_k=step.get("temperature_k"), duration_s=step.get("duration_s"),
            pressure_pa=step.get("pressure_pa"), atmosphere=step.get("atmosphere"),
            cooling_rate_k_per_s=step.get("cooling_rate_k_per_s"),
            strain_fraction=step.get("strain_fraction"), parameters=step.get("parameters") or {},
            notes=step.get("notes"),
        ))
    db.flush()
    return history


def create_microstructure(
    db: Session, *, organisation_id: str | None, values: dict[str, Any], row_id: str | None = None
) -> MicrostructureDescriptor:
    descriptor = MicrostructureDescriptor(
        organisation_id=organisation_id, descriptor_checksum=microstructure_checksum(values), **values
    )
    if row_id:
        descriptor.id = row_id
    db.add(descriptor)
    db.flush()
    return descriptor


def create_material_state(
    db: Session, *, organisation_id: str, label: str, material_id: str | None = None,
    hypothesis_id: str | None = None, composition: list[dict[str, Any]] | None = None,
    representation_id: str | None = None, crystal_system: str | None = None,
    space_group_number: int | None = None, space_group_symbol: str | None = None,
    lattice_parameters: dict[str, Any] | None = None, polymorph: str | None = None,
    phase: str | None = None, phase_fraction: float | None = None,
    microstructure_id: str | None = None, processing_history_id: str | None = None,
    temperature_k: float | None = None, pressure_pa: float | None = None,
    environment: str | None = None, conditions: dict[str, Any] | None = None,
    description: str | None = None, provenance_note: str | None = None,
    is_reference_state: bool = False, visibility: str = "private", row_id: str | None = None,
) -> MaterialState:
    if bool(material_id) == bool(hypothesis_id):
        raise StateError("A material state must reference exactly one material or one hypothesis")

    normalized_composition = normalize_composition(composition or [])
    representation = db.get(ScientificRepresentation, representation_id) if representation_id else None
    identity, identity_basis = structure_identity(
        representation, space_group_number=space_group_number, polymorph=polymorph
    )
    signature = composition_signature(normalized_composition) if normalized_composition else None

    history = db.get(ProcessingHistory, processing_history_id) if processing_history_id else None
    microstructure = db.get(MicrostructureDescriptor, microstructure_id) if microstructure_id else None

    identity_payload = {
        "target": material_id or hypothesis_id,
        "composition": normalized_composition,
        "structure_identity": identity,
        "space_group_number": space_group_number,
        "polymorph": polymorph, "phase": phase, "phase_fraction": _round(phase_fraction),
        "processing_history_checksum": history.history_checksum if history else None,
        "microstructure_checksum": microstructure.descriptor_checksum if microstructure else None,
        "temperature_k": _round(temperature_k), "pressure_pa": _round(pressure_pa),
        "environment": environment, "conditions": conditions or {},
    }

    state = MaterialState(
        organisation_id=organisation_id, visibility=visibility, material_id=material_id,
        hypothesis_id=hypothesis_id, label=label, description=description,
        is_reference_state=is_reference_state, representation_id=representation_id,
        crystal_system=crystal_system, space_group_number=space_group_number,
        space_group_symbol=space_group_symbol, lattice_parameters=lattice_parameters or {},
        polymorph=polymorph, phase=phase, phase_fraction=phase_fraction,
        structure_identity=identity, structure_identity_basis=identity_basis,
        composition_signature=signature, microstructure_id=microstructure_id,
        processing_history_id=processing_history_id, temperature_k=temperature_k,
        pressure_pa=pressure_pa, environment=environment, conditions=conditions or {},
        state_checksum=state_checksum(identity_payload), provenance_note=provenance_note,
        status="active", metadata_json={},
    )
    if row_id:
        state.id = row_id
    db.add(state)
    db.flush()
    for component in normalized_composition:
        db.add(StateCompositionComponent(
            state_id=state.id, element=str(component["element"]), role=str(component["role"]),
            stoichiometry=component["stoichiometry"], atomic_fraction=component["atomic_fraction"],
            atomic_fraction_min=component["atomic_fraction_min"],
            atomic_fraction_max=component["atomic_fraction_max"],
            concentration_value=component["concentration_value"],
            concentration_unit=component["concentration_unit"],
            original_representation=component["original_representation"],
        ))
    db.flush()
    return state


# ---------------------------------------------------------------------------------------------
# State matching
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class StateMatch:
    quality: str
    reasons: tuple[str, ...]

    @property
    def usable(self) -> bool:
        """Only EXACT and COMPATIBLE permit a property to be used for this state."""
        return self.quality in {StateMatchQuality.EXACT, StateMatchQuality.COMPATIBLE}


def match_states(required: MaterialState | None, observed: MaterialState | None) -> StateMatch:
    """Compare the state a requirement is asked about with the state evidence was recorded in.

    Silence is never compatibility: if either state is unknown the result is UNKNOWN_STATE, and the
    caller must treat the evidence as not established for this state rather than assuming it carries.
    """
    if required is None or observed is None:
        return StateMatch(StateMatchQuality.UNKNOWN_STATE, (
            "One of the states is not recorded, so state compatibility cannot be established. "
            "A property is not assumed to carry across an unknown state difference.",
        ))
    if required.id == observed.id or required.state_checksum == observed.state_checksum:
        return StateMatch(StateMatchQuality.EXACT, ("Identical state identity.",))

    reasons: list[str] = []
    incompatible: list[str] = []
    unknown_critical: list[str] = []

    if required.structure_identity and observed.structure_identity:
        if required.structure_identity != observed.structure_identity:
            incompatible.append(
                "Structural identity differs: these are different structures, not merely different samples."
            )
        else:
            reasons.append("Structural identity matches.")
    elif required.composition_signature and observed.composition_signature:
        if required.composition_signature != observed.composition_signature:
            incompatible.append(
                f"Composition differs ({observed.composition_signature} vs {required.composition_signature})."
            )
        else:
            reasons.append(
                "Composition matches, but no structural identity is recorded for both states, so this "
                "is a composition-level match only — a shared formula is not a shared structure."
            )
    else:
        return StateMatch(StateMatchQuality.UNKNOWN_STATE, (
            "Neither structural identity nor composition is recorded for both states.",
        ))

    if required.phase and observed.phase and required.phase != observed.phase:
        incompatible.append(f"Phase differs ({observed.phase} vs {required.phase}).")
    if required.polymorph and observed.polymorph and required.polymorph != observed.polymorph:
        incompatible.append(f"Polymorph differs ({observed.polymorph} vs {required.polymorph}).")

    if required.processing_history_id and observed.processing_history_id:
        if required.processing_history_id != observed.processing_history_id:
            incompatible.append(
                "Processing history differs; properties are not propagated across processing routes."
            )
        else:
            reasons.append("Processing history matches.")
    elif required.processing_history_id or observed.processing_history_id:
        unknown_critical.append("Processing history is recorded for only one state.")

    if required.temperature_k is not None and observed.temperature_k is not None:
        if abs(required.temperature_k - observed.temperature_k) > TEMPERATURE_TOLERANCE_K:
            incompatible.append(
                f"Temperature differs ({observed.temperature_k} K vs {required.temperature_k} K)."
            )
        else:
            reasons.append("Temperature matches within tolerance.")
    elif required.temperature_k is not None or observed.temperature_k is not None:
        unknown_critical.append("Temperature is specified for only one state.")

    if required.pressure_pa is not None and observed.pressure_pa is not None:
        reference = max(abs(required.pressure_pa), 1.0)
        if abs(required.pressure_pa - observed.pressure_pa) / reference > PRESSURE_RELATIVE_TOLERANCE:
            incompatible.append(f"Pressure differs ({observed.pressure_pa} Pa vs {required.pressure_pa} Pa).")
        else:
            reasons.append("Pressure matches within tolerance.")
    elif required.pressure_pa is not None or observed.pressure_pa is not None:
        unknown_critical.append("Pressure is specified for only one state.")

    if required.environment and observed.environment:
        if required.environment != observed.environment:
            incompatible.append(f"Environment differs ({observed.environment} vs {required.environment}).")
        else:
            reasons.append("Environment matches.")
    elif required.environment or observed.environment:
        unknown_critical.append("Environment is specified for only one state.")

    for label, a, b in (("Phase", required.phase, observed.phase), ("Polymorph", required.polymorph, observed.polymorph)):
        if (a is None) != (b is None):
            unknown_critical.append(f"{label} is specified for only one state.")

    if incompatible:
        return StateMatch(StateMatchQuality.DIFFERENT_STATE, tuple(incompatible))
    if unknown_critical:
        return StateMatch(StateMatchQuality.UNKNOWN_STATE, tuple(unknown_critical + reasons))
    # Composition-only matches with no structural identity are explicitly conditional, not full compatibility.
    if not (required.structure_identity and observed.structure_identity):
        return StateMatch(StateMatchQuality.CONDITIONALLY_COMPATIBLE, tuple(reasons) or ("Composition-level match only.",))
    return StateMatch(StateMatchQuality.COMPATIBLE, tuple(reasons) or ("No incompatibility recorded.",))


def states_for_target(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None
) -> list[MaterialState]:
    query = db.query(MaterialState).filter(MaterialState.status == "active")
    query = query.filter(
        MaterialState.material_id == target_id if target_kind == "known_material"
        else MaterialState.hypothesis_id == target_id
    )
    rows = query.order_by(MaterialState.is_reference_state.desc(), MaterialState.created_at, MaterialState.id).all()
    return [
        r for r in rows
        if (r.visibility == "public" and r.organisation_id is None)
        or (organisation_id is not None and r.organisation_id == organisation_id)
    ]


def reference_state(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None
) -> MaterialState | None:
    states = states_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)
    for state in states:
        if state.is_reference_state:
            return state
    return states[0] if states else None
