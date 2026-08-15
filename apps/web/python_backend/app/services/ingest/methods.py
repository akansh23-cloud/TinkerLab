"""Phase 11 — Computational method provenance and applicability warnings.

The single most dangerous thing TinkerLab could do with external data is treat a DFT number as a
measurement.

A PBE band gap is typically 40-50% below the experimental value. TinkerLab's demonstration
programme has a BLOCKING requirement of band gap >= 2.5 eV. A candidate whose true gap is 3.2 eV
might compute at 2.1 eV under PBE and be wrongly rejected; a candidate at 2.6 eV true might compute
at 1.7 eV and also be rejected. Worse in the other direction: for properties where the functional
overestimates, a candidate that a real device would fail can pass.

Static-lattice DFT also describes a hypothetical 0 K crystal with no thermal expansion and no
zero-point motion. Comparing it to a 525 K operating requirement is a state mismatch, and Phase 8
already knows how to say so — but only if the state is recorded honestly.

So every computed value ingested here carries its method, and every method carries its documented
biases. The evaluator gets a warning it can surface rather than a number it silently believes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import ComputationalMethod

# Directional method-risk heuristics used only to warn. Magnitude bands are deliberately coarse:
# they vary by chemistry and workflow and must never be treated as universal error bars or silently
# applied as correction factors. Provider-specific provenance remains authoritative when available.
METHOD_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "dft_unspecified_static",
        "display_name": "DFT (functional unspecified), static lattice",
        "method_family": "dft",
        "functional": None,
        "basis_or_code": "unspecified electronic-structure workflow",
        "nominal_temperature_k": 0.0,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {},
        "applicability_note": (
            "The source did not expose enough calculation provenance to identify the functional. "
            "Treat values as screening evidence only until method provenance is recovered."
        ),
        "reference_url": None,
    },
    {
        "key": "dft_pbe_static",
        "display_name": "DFT / PBE (GGA), static lattice",
        "method_family": "dft",
        "functional": "PBE",
        "basis_or_code": "plane-wave (VASP/QE class)",
        "nominal_temperature_k": 0.0,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {
            "band_gap": {
                "direction": "underestimates",
                "typical_relative_error": "40-50%",
                "severity": "high",
                "note": "The band gap problem in semilocal DFT. A PBE gap must not be compared "
                        "directly against an experimental threshold.",
            },
            "bulk_modulus": {
                "direction": "underestimates",
                "typical_relative_error": "5-10%",
                "severity": "low",
                "note": "GGA typically overestimates lattice constants, softening elastic moduli.",
            },
            "lattice_parameter": {
                "direction": "overestimates",
                "typical_relative_error": "1-2%",
                "severity": "low",
                "note": "Standard GGA overbinding correction; usually acceptable for screening.",
            },
            "formation_energy_per_atom": {
                "direction": "variable",
                "typical_relative_error": "50-100 meV/atom",
                "severity": "medium",
                "note": "Reasonable for relative stability ranking, weaker for absolute values.",
            },
        },
        "applicability_note": (
            "Suitable for relative screening and stability ranking. Not suitable as the governing "
            "evidence for a band-gap requirement without experimental or hybrid-functional support."
        ),
        "reference_url": "https://doi.org/10.1103/PhysRevLett.77.3865",
    },
    {
        "key": "dft_scan_static",
        "display_name": "DFT / SCAN (meta-GGA), static lattice",
        "method_family": "dft",
        "functional": "SCAN",
        "basis_or_code": "plane-wave",
        "nominal_temperature_k": 0.0,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {
            "band_gap": {
                "direction": "underestimates",
                "typical_relative_error": "20-30%",
                "severity": "medium",
                "note": "Improves on PBE but still systematically low.",
            },
            "formation_energy_per_atom": {
                "direction": "variable",
                "typical_relative_error": "30-70 meV/atom",
                "severity": "low",
                "note": "Generally better formation energies than PBE.",
            },
        },
        "applicability_note": "Better than PBE for gaps and energetics; still a 0 K static result.",
        "reference_url": "https://doi.org/10.1103/PhysRevLett.115.036402",
    },
    {
        "key": "dft_hse06_static",
        "display_name": "DFT / HSE06 (hybrid), static lattice",
        "method_family": "dft",
        "functional": "HSE06",
        "basis_or_code": "plane-wave",
        "nominal_temperature_k": 0.0,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {
            "band_gap": {
                "direction": "slightly underestimates",
                "typical_relative_error": "5-15%",
                "severity": "low",
                "note": "Much closer to experiment; acceptable supporting evidence for a gap "
                        "requirement, though still not a measurement.",
            },
        },
        "applicability_note": (
            "The most defensible computed band gap in common use. Still 0 K and still computed."
        ),
        "reference_url": "https://doi.org/10.1063/1.1564060",
    },
    {
        "key": "dft_gga_plus_u_static",
        "display_name": "DFT / GGA+U, static lattice",
        "method_family": "dft",
        "functional": "PBE+U",
        "basis_or_code": "plane-wave",
        "nominal_temperature_k": 0.0,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {
            "band_gap": {
                "direction": "variable",
                "typical_relative_error": "highly U-dependent",
                "severity": "high",
                "note": "The gap depends directly on the chosen U parameter, which is fitted. "
                        "Not independent evidence for a gap requirement.",
            },
            "formation_energy_per_atom": {
                "direction": "variable",
                "typical_relative_error": "corrected for transition-metal oxides",
                "severity": "medium",
                "note": "Applied specifically to improve oxide formation energies.",
            },
        },
        "applicability_note": "Used for correlated transition-metal systems; U choice is a fit.",
        "reference_url": "https://doi.org/10.1103/PhysRevB.57.1505",
    },
    {
        "key": "ml_interatomic_potential",
        "display_name": "Machine-learned interatomic potential",
        "method_family": "machine_learning",
        "functional": None,
        "basis_or_code": "MLIP",
        "nominal_temperature_k": None,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {
            "formation_energy_per_atom": {
                "direction": "variable",
                "typical_relative_error": "depends on training-set coverage",
                "severity": "high",
                "note": "Error is not bounded outside the training distribution. Applicability "
                        "must be checked against the training domain, not assumed.",
            },
        },
        "applicability_note": (
            "Fast screening only. A prediction outside the training domain carries no meaningful "
            "error bar and must not gate a decision."
        ),
        "reference_url": None,
    },
    {
        "key": "reference_database_record",
        "display_name": "Reference/database-derived property",
        "method_family": "reference_data",
        "functional": None,
        "basis_or_code": None,
        "nominal_temperature_k": None,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {},
        "applicability_note": (
            "Provider-reported or provider-derived reference data. This classification does not "
            "assert that a physical experiment was performed by the provider."
        ),
        "reference_url": None,
    },
    {
        "key": "regulatory_reference",
        "display_name": "Regulatory authority database record",
        "method_family": "regulatory_reference",
        "functional": None,
        "basis_or_code": None,
        "nominal_temperature_k": None,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {},
        "applicability_note": (
            "Regulatory-list or authority-database evidence. Membership is a review signal, not a "
            "scientific measurement or an automatic regulatory verdict."
        ),
        "reference_url": None,
    },
    {
        "key": "structure_reference",
        "display_name": "External structural database record",
        "method_family": "structure_reference",
        "functional": None,
        "basis_or_code": None,
        "nominal_temperature_k": None,
        "includes_thermal_expansion": False,
        "includes_zero_point_energy": False,
        "known_property_bias": {},
        "applicability_note": (
            "Structural identity/reference data. No property measurement or calculation method is "
            "inferred unless the originating provider explicitly supplies it."
        ),
        "reference_url": None,
    },
    {
        "key": "experimental_measured",
        "display_name": "Experimental measurement (external source)",
        "method_family": "experimental",
        "functional": None,
        "basis_or_code": None,
        "nominal_temperature_k": None,
        "includes_thermal_expansion": True,
        "includes_zero_point_energy": True,
        "known_property_bias": {},
        "applicability_note": (
            "Measured under stated conditions. Conditions still have to match the application; a "
            "measurement at the wrong temperature is still a state mismatch."
        ),
        "reference_url": None,
    },
]

# Severity ordering used when deciding whether a warning should block a requirement from being
# treated as governing evidence.
BLOCKING_BIAS_SEVERITIES: frozenset[str] = frozenset({"high"})


def ensure_methods(db: Session) -> dict[str, ComputationalMethod]:
    """Register the method catalogue. Idempotent on `key`."""
    registered: dict[str, ComputationalMethod] = {}
    for definition in METHOD_DEFINITIONS:
        row = db.query(ComputationalMethod).filter_by(key=definition["key"]).one_or_none()
        if row is None:
            row = ComputationalMethod(key=definition["key"])
            db.add(row)
        for field_name, value in definition.items():
            if field_name != "key":
                setattr(row, field_name, value)
        registered[definition["key"]] = row
    db.flush()
    return registered


def method_for_provider_record(
    provider_key: str, record: dict[str, Any]
) -> str:
    """Classify a provider record without inventing missing calculation provenance.

    Materials Project records whose functional cannot be identified remain
    ``dft_unspecified_static``. Missing provenance is a warning condition, not permission to assume
    the most common functional.
    """
    if provider_key == "pubchem":
        return "reference_database_record"
    if provider_key == "epa_comptox":
        return "regulatory_reference"
    if provider_key.startswith("optimade"):
        return "structure_reference"

    provenance = record.get("calculation_provenance") or {}
    provenance_blob = ""
    if isinstance(provenance, dict):
        provenance_blob = " ".join(
            str(value) for value in provenance.values()
            if value is not None and not isinstance(value, (dict, list, tuple, set))
        )
    blob = " ".join(
        [
            *(str(record.get(key, "")) for key in
              ("functional", "xc_functional", "run_type", "calc_type", "method", "_mp_run_type")),
            provenance_blob,
        ]
    ).upper()

    if "HSE" in blob:
        return "dft_hse06_static"
    if "SCAN" in blob or "R2SCAN" in blob:
        return "dft_scan_static"
    if "+U" in blob or "GGA_U" in blob or "GGAU" in blob:
        return "dft_gga_plus_u_static"
    if "MLIP" in blob or "M3GNET" in blob or "CHGNET" in blob:
        return "ml_interatomic_potential"
    if provider_key == "materials_project":
        # Unknown is kept unknown. Assuming PBE would turn missing provenance into a fabricated
        # method claim, even if PBE is common in the source database.
        return "dft_unspecified_static"
    return "reference_database_record"


def method_for_observation(
    provider_key: str, record: dict[str, Any], observation: dict[str, Any]
) -> str:
    """Resolve calculation provenance at property granularity when the source exposes it.

    A provider record may aggregate properties from different workflows. Observation-level
    descriptors therefore override record-level descriptors. If neither level identifies a method,
    the same conservative unknown classification used for the record is returned.
    """
    explicit = str(observation.get("method_key") or "").strip()
    known = {str(row["key"]) for row in METHOD_DEFINITIONS}
    if explicit in known:
        return explicit

    merged = dict(record)
    observation_provenance = observation.get("calculation_provenance")
    if isinstance(observation_provenance, dict):
        merged["calculation_provenance"] = observation_provenance
        for key in ("functional", "xc_functional", "run_type", "calc_type", "method", "_mp_run_type"):
            if observation_provenance.get(key) is not None:
                merged[key] = observation_provenance[key]
    for key in ("functional", "xc_functional", "run_type", "calc_type", "method", "_mp_run_type"):
        if observation.get(key) is not None:
            merged[key] = observation[key]
    return method_for_provider_record(provider_key, merged)


def applicability_warnings(
    method: ComputationalMethod, property_key: str,
    *, requirement_temperature_k: float | None = None,
) -> list[dict[str, Any]]:
    """Warnings that should travel with a computed value into the evidence chain."""
    warnings: list[dict[str, Any]] = []

    if method.key == "dft_unspecified_static":
        warnings.append({
            "code": "COMPUTATIONAL_METHOD_UNSPECIFIED",
            "property_key": property_key,
            "method": method.key,
            "severity": "high",
            "message": (
                "The provider record did not expose enough calculation provenance to identify "
                "the DFT functional. The value is screening evidence only until provenance is recovered."
            ),
        })

    bias = (method.known_property_bias or {}).get(property_key)
    if bias:
        warnings.append({
            "code": "SYSTEMATIC_METHOD_BIAS",
            "property_key": property_key,
            "method": method.key,
            "direction": bias.get("direction"),
            "typical_relative_error": bias.get("typical_relative_error"),
            "severity": bias.get("severity", "medium"),
            "message": (
                f"{method.display_name} {bias.get('direction')} {property_key} by approximately "
                f"{bias.get('typical_relative_error')}. {bias.get('note', '')}".strip()
            ),
        })

    # A 0 K static-lattice result compared against a hot operating requirement.
    nominal = method.nominal_temperature_k
    if (
        nominal is not None and requirement_temperature_k is not None
        and abs(requirement_temperature_k - nominal) > 50.0
    ):
        warnings.append({
            "code": "COMPUTED_AT_DIFFERENT_TEMPERATURE",
            "property_key": property_key,
            "method": method.key,
            "severity": "high",
            "computed_temperature_k": nominal,
            "required_temperature_k": requirement_temperature_k,
            "message": (
                f"{method.display_name} describes a {nominal:g} K static lattice, but the "
                f"requirement applies at {requirement_temperature_k:g} K. Thermal expansion and "
                "phonon effects are not represented."
            ),
        })

    if method.method_family == "dft" and not method.includes_zero_point_energy:
        warnings.append({
            "code": "NO_ZERO_POINT_ENERGY",
            "property_key": property_key,
            "method": method.key,
            "severity": "low",
            "message": "Zero-point motion is not included in this calculation.",
        })

    return warnings


def has_blocking_warning(warnings: list[dict[str, Any]]) -> bool:
    """Whether these warnings should stop a value being treated as governing evidence."""
    return any(str(w.get("severity")) in BLOCKING_BIAS_SEVERITIES for w in warnings)
