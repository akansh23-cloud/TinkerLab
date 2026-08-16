from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IdentityCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    LEGACY_UNKNOWN = "LEGACY_UNKNOWN"


class IdentityConflictSeverity(StrEnum):
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class MaterialIdentityConflict(RuntimeError):
    """Raised when chemically similar records would be conflated across engineering identities."""


@dataclass(frozen=True)
class IdentityConflict:
    left_material_id: str
    right_material_id: str
    composition_fingerprint: str
    differing_dimensions: tuple[str, ...]
    severity: IdentityConflictSeverity = IdentityConflictSeverity.BLOCKING


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalize_composition(composition: dict[str, float]) -> dict[str, float]:
    """Return a deterministic atomic-fraction-like composition representation.

    The function deliberately does not infer stoichiometry from material names. Callers must provide
    the composition they actually know. Values are normalized only when their positive sum is nonzero.
    """
    cleaned = {str(k).strip(): float(v) for k, v in composition.items() if float(v) > 0.0}
    total = sum(cleaned.values())
    if total <= 0.0:
        return {}
    return {key: round(value / total, 12) for key, value in sorted(cleaned.items())}


def composition_fingerprint(composition: dict[str, float]) -> str:
    normalized = normalize_composition(composition)
    return hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()


def engineering_identity_fingerprint(
    *,
    composition: dict[str, float],
    phase_polytype: dict[str, Any],
    microstructure: dict[str, Any],
    processing_route: dict[str, Any],
    form_factor: dict[str, Any],
    crystallographic_orientation: dict[str, Any],
    defect_state: dict[str, Any],
) -> str:
    payload = {
        "composition": normalize_composition(composition),
        "phase_polytype": phase_polytype,
        "microstructure": microstructure,
        "processing_route": processing_route,
        "form_factor": form_factor,
        "crystallographic_orientation": crystallographic_orientation,
        "defect_state": defect_state,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def differing_identity_dimensions(left: Any, right: Any) -> tuple[str, ...]:
    dimensions = (
        "phase_polytype",
        "microstructure",
        "processing_route",
        "form_factor",
        "crystallographic_orientation",
        "defect_state",
    )
    return tuple(name for name in dimensions if getattr(left, name) != getattr(right, name))
