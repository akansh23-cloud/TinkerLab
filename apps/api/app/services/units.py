from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class UnitSpec:
    dimension: str
    to_base_factor: float = 1.0
    offset_to_base: float = 0.0
    canonical_symbol: str | None = None


# Pint is the production units backend. The narrow internal registry is a deterministic bootstrap/test
# fallback for environments (such as offline source audits) where third-party packages cannot be installed.
try:
    import pint  # type: ignore[import-not-found]

    _ureg: Any | None = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
    for definition in ("USD = [currency]", "kgCO2e = [carbon_mass]"):
        try:
            _ureg.define(definition)  # type: ignore[union-attr]
        except Exception:
            pass
except Exception:  # pragma: no cover - exercised only in offline/bootstrap environments
    _ureg = None


UNITS: dict[str, UnitSpec] = {
    "Pa": UnitSpec("pressure", 1.0, 0.0, "Pa"),
    "kPa": UnitSpec("pressure", 1e3, 0.0, "Pa"),
    "MPa": UnitSpec("pressure", 1e6, 0.0, "Pa"),
    "GPa": UnitSpec("pressure", 1e9, 0.0, "Pa"),
    "kg/m^3": UnitSpec("density", 1.0, 0.0, "kg/m^3"),
    "g/cm^3": UnitSpec("density", 1000.0, 0.0, "kg/m^3"),
    "K": UnitSpec("temperature", 1.0, 0.0, "K"),
    "degC": UnitSpec("temperature", 1.0, 273.15, "K"),
    "°C": UnitSpec("temperature", 1.0, 273.15, "K"),
    "W/(m*K)": UnitSpec("thermal_conductivity", 1.0, 0.0, "W/(m*K)"),
    "USD/kg": UnitSpec("cost_per_mass", 1.0, 0.0, "USD/kg"),
    "kgCO2e/kg": UnitSpec("carbon_footprint", 1.0, 0.0, "kgCO2e/kg"),
    "%": UnitSpec("percent", 1.0, 0.0, "%"),
    "1": UnitSpec("dimensionless", 1.0, 0.0, "1"),
    "Hz": UnitSpec("frequency", 1.0, 0.0, "Hz"),
    "kHz": UnitSpec("frequency", 1e3, 0.0, "Hz"),
    "MHz": UnitSpec("frequency", 1e6, 0.0, "Hz"),
    # Phase 6 — simulation units. Energies, lengths, times and forces are first-class so that a
    # solver output is never silently reinterpreted into a differently dimensioned property.
    "eV": UnitSpec("energy", 1.602176634e-19, 0.0, "eV"),
    "J": UnitSpec("energy", 1.0, 0.0, "eV"),
    "kJ": UnitSpec("energy", 1e3, 0.0, "eV"),
    "Ry": UnitSpec("energy", 2.1798723611035e-18, 0.0, "eV"),
    "Ha": UnitSpec("energy", 4.3597447222071e-18, 0.0, "eV"),
    "kJ/mol": UnitSpec("molar_energy", 1e3, 0.0, "kJ/mol"),
    "kcal/mol": UnitSpec("molar_energy", 4184.0, 0.0, "kJ/mol"),
    "J/mol": UnitSpec("molar_energy", 1.0, 0.0, "kJ/mol"),
    "m": UnitSpec("length", 1.0, 0.0, "angstrom"),
    "nm": UnitSpec("length", 1e-9, 0.0, "angstrom"),
    "angstrom": UnitSpec("length", 1e-10, 0.0, "angstrom"),
    "pm": UnitSpec("length", 1e-12, 0.0, "angstrom"),
    "s": UnitSpec("time", 1.0, 0.0, "ps"),
    "ps": UnitSpec("time", 1e-12, 0.0, "ps"),
    "fs": UnitSpec("time", 1e-15, 0.0, "ps"),
    "ns": UnitSpec("time", 1e-9, 0.0, "ps"),
    "N": UnitSpec("force", 1.0, 0.0, "eV/angstrom"),
    "eV/angstrom": UnitSpec("force", 1.602176634e-9, 0.0, "eV/angstrom"),
    "nN": UnitSpec("force", 1e-9, 0.0, "eV/angstrom"),
    # Phase 8 registered `breakdown_field` and `electron_mobility` as property definitions but never
    # registered their units, so any evidence carrying them was rejected as a unit-dimension
    # mismatch. The Phase-8 seed happened to leave those properties unmeasured, which hid the gap.
    # These entries close it. Both dimensions are new, so no existing conversion changes behaviour.
    "V/m": UnitSpec("electric_field", 1.0, 0.0, "MV/cm"),
    "kV/mm": UnitSpec("electric_field", 1e6, 0.0, "MV/cm"),
    "MV/cm": UnitSpec("electric_field", 1e8, 0.0, "MV/cm"),
    "V/cm": UnitSpec("electric_field", 100.0, 0.0, "MV/cm"),
    "m^2/(V*s)": UnitSpec("mobility", 1.0, 0.0, "cm^2/(V*s)"),
    "cm^2/(V*s)": UnitSpec("mobility", 1e-4, 0.0, "cm^2/(V*s)"),

    # --- Phase 11: units emitted by external providers -----------------------------------------
    # Added per connector rather than speculatively. Every entry below appears in a real response
    # payload from OPTIMADE, Materials Project, PubChem or CompTox.
    # Energy (DFT codes report in eV, Ry, Ha; thermochemistry in kJ/mol and kcal/mol).
    "meV": UnitSpec("energy", 1.602176634e-22, 0.0, "eV"),
    "J/mol": UnitSpec("molar_energy", 1.0, 0.0, "kJ/mol"),
    "eV/atom": UnitSpec("energy_per_atom", 1.0, 0.0, "eV/atom"),
    "meV/atom": UnitSpec("energy_per_atom", 1e-3, 0.0, "eV/atom"),
    "kJ/mol/atom": UnitSpec("energy_per_atom", 0.010364, 0.0, "eV/atom"),
    # Elastic and mechanical.
    "MPa": UnitSpec("pressure", 1e6, 0.0, "MPa"),
    "bar": UnitSpec("pressure", 1e5, 0.0, "MPa"),
    "atm": UnitSpec("pressure", 101325.0, 0.0, "MPa"),
    "psi": UnitSpec("pressure", 6894.757, 0.0, "MPa"),
    # Electrical conductivity / resistivity.
    "S/m": UnitSpec("conductivity", 1.0, 0.0, "S/cm"),
    "S/cm": UnitSpec("conductivity", 100.0, 0.0, "S/cm"),
    "ohm*m": UnitSpec("resistivity", 1.0, 0.0, "ohm*cm"),
    "ohm*cm": UnitSpec("resistivity", 0.01, 0.0, "ohm*cm"),
    "uohm*cm": UnitSpec("resistivity", 1e-8, 0.0, "ohm*cm"),
    # Thermal.
    "W/(cm*K)": UnitSpec("thermal_conductivity", 100.0, 0.0, "W/(m*K)"),
    "mW/(m*K)": UnitSpec("thermal_conductivity", 1e-3, 0.0, "W/(m*K)"),
    "1/K": UnitSpec("thermal_expansion", 1.0, 0.0, "1e-6/K"),
    "1e-6/K": UnitSpec("thermal_expansion", 1e-6, 0.0, "1e-6/K"),
    "ppm/K": UnitSpec("thermal_expansion", 1e-6, 0.0, "1e-6/K"),
    "J/(kg*K)": UnitSpec("specific_heat", 1.0, 0.0, "J/(kg*K)"),
    "J/(g*K)": UnitSpec("specific_heat", 1000.0, 0.0, "J/(kg*K)"),
    # Molar mass and amount, needed to convert per-mole to per-mass for cost comparisons.
    "g/mol": UnitSpec("molar_mass", 1.0, 0.0, "g/mol"),
    "kg/mol": UnitSpec("molar_mass", 1000.0, 0.0, "g/mol"),
    # Areal / volumetric density used by 2D and battery datasets.
    "mAh/g": UnitSpec("specific_capacity", 1.0, 0.0, "mAh/g"),
    "Ah/kg": UnitSpec("specific_capacity", 1.0, 0.0, "mAh/g"),
    "Wh/kg": UnitSpec("specific_energy", 1.0, 0.0, "Wh/kg"),
    "Wh/L": UnitSpec("energy_density", 1.0, 0.0, "Wh/L"),
    # Magnetic moment as reported by DFT providers.
    "bohr_magneton": UnitSpec("magnetic_moment", 1.0, 0.0, "bohr_magneton"),
    "mu_B": UnitSpec("magnetic_moment", 1.0, 0.0, "bohr_magneton"),
    # Concentration limits used by regulatory thresholds (PFAS, RoHS).
    "ppm": UnitSpec("mass_fraction", 1e-6, 0.0, "ppm"),
    "ppb": UnitSpec("mass_fraction", 1e-9, 0.0, "ppm"),
    "mg/kg": UnitSpec("mass_fraction", 1e-6, 0.0, "ppm"),
    "ug/kg": UnitSpec("mass_fraction", 1e-9, 0.0, "ppm"),
    "wt%": UnitSpec("mass_fraction", 1e-2, 0.0, "ppm"),
    # Supply-chain and trade quantities.
    "tonne": UnitSpec("mass", 1000.0, 0.0, "tonne"),
    "kg": UnitSpec("mass", 1.0, 0.0, "tonne"),
    "kilotonne": UnitSpec("mass", 1e6, 0.0, "tonne"),
    "megatonne": UnitSpec("mass", 1e9, 0.0, "tonne"),
    "USD/tonne": UnitSpec("cost_per_mass", 1e-3, 0.0, "USD/kg"),
    "USD/g": UnitSpec("cost_per_mass", 1000.0, 0.0, "USD/kg"),
}

PROPERTY_DIMENSIONS: dict[str, str] = {
    "density": "density",
    "tensile_strength": "pressure",
    "yield_strength": "pressure",
    "operating_temperature": "temperature",
    "thermal_conductivity": "thermal_conductivity",
    "cost_per_mass": "cost_per_mass",
    "carbon_footprint": "carbon_footprint",
    # Phase-6 software-validation fixture output. Deliberately dimensionless reduced units so no
    # synthetic number can ever be read as a physical energy claim about a real material.
    "software_fixture_reduced_energy": "dimensionless",
    "total_energy": "energy",
    "lattice_parameter": "length",
    "band_gap": "energy",
    "breakdown_field": "electric_field",
    "electron_mobility": "mobility",
    # --- Phase 11 property vocabulary ----------------------------------------------------------
    "hole_mobility": "mobility",
    "formation_energy_per_atom": "energy_per_atom",
    "energy_above_hull": "energy_per_atom",
    "bulk_modulus": "pressure",
    "shear_modulus": "pressure",
    "youngs_modulus": "pressure",
    "elastic_modulus": "pressure",
    "electrical_conductivity": "conductivity",
    "electrical_resistivity": "resistivity",
    "thermal_expansion_coefficient": "thermal_expansion",
    "specific_heat_capacity": "specific_heat",
    "molar_mass": "molar_mass",
    "specific_capacity": "specific_capacity",
    "specific_energy": "specific_energy",
    "energy_density": "energy_density",
    "magnetic_moment": "magnetic_moment",
    "melting_point": "temperature",
    "glass_transition_temperature": "temperature",
    "dielectric_constant": "dimensionless",
    "refractive_index": "dimensionless",
    "poisson_ratio": "dimensionless",
    "concentration_limit": "mass_fraction",
    "annual_production": "mass",
}


def normalize_unit(unit: str) -> str:
    aliases = {
        "g/cm3": "g/cm^3",
        "kg/m3": "kg/m^3",
        "C": "degC",
        "celsius": "degC",
        "°C": "degC",
        "A": "angstrom",
        "Å": "angstrom",
        "ang": "angstrom",
        "Angstrom": "angstrom",
        "electron_volt": "eV",
        "Rydberg": "Ry",
        "Hartree": "Ha",
        "eV/A": "eV/angstrom",
        "eV/Å": "eV/angstrom",
        "dimensionless": "1",
        "reduced": "1",
    }
    cleaned = unit.strip()
    return aliases.get(cleaned, cleaned)


def ensure_known(unit: str) -> str:
    normalized = normalize_unit(unit)
    if normalized not in UNITS:
        raise UnitError(f"Unsupported unit: {unit}")
    return normalized


def ensure_compatible(unit: str, canonical_unit: str) -> None:
    a = UNITS[ensure_known(unit)]
    b = UNITS[ensure_known(canonical_unit)]
    if a.dimension != b.dimension:
        raise UnitError(f"Incompatible units: {unit} and {canonical_unit}")


def _pint_convert(value: float, from_unit: str, to_unit: str) -> float:
    assert _ureg is not None
    try:
        return float(_ureg.Quantity(value, from_unit).to(to_unit).magnitude)
    except Exception as exc:
        raise UnitError(f"Cannot convert {from_unit} to {to_unit}: {exc}") from exc


# Units that must NOT be delegated to pint, for one of two reasons:
#
#   1. pint cannot parse them at all (eV/atom, wt%, USD/tonne, ppb, 1e-6/K).
#   2. pint parses them as something else entirely. `kt` is knots in pint, not kilotonnes — a
#      silent five-order-of-magnitude error in a production figure. That alias has been removed,
#      but the general hazard is why domain units are resolved from our own declared table.
#
# For these, the factors declared in UNITS above are authoritative and are covered by unit tests.
INTERNAL_ONLY_UNITS: frozenset[str] = frozenset({
    "eV/atom", "meV/atom", "kJ/mol/atom",
    "1e-6/K", "ppm/K",
    "ppb", "wt%", "ppm", "mg/kg", "ug/kg",
    "tonne", "kilotonne", "megatonne", "kg",
    "USD/tonne", "USD/g", "USD/kg",
    "mAh/g", "Ah/kg", "Wh/kg", "Wh/L",
    "bohr_magneton", "mu_B",
    "kgCO2e/kg",
})


def _internal_convert(value: float, source: str, target: str) -> float:
    from_u = UNITS[source]
    to_u = UNITS[target]
    base = value * from_u.to_base_factor + from_u.offset_to_base
    return (base - to_u.offset_to_base) / to_u.to_base_factor


def convert(value: float, from_unit: str, to_unit: str) -> float:
    source = ensure_known(from_unit)
    target = ensure_known(to_unit)
    ensure_compatible(source, target)
    if source in INTERNAL_ONLY_UNITS or target in INTERNAL_ONLY_UNITS:
        return _internal_convert(value, source, target)
    if _ureg is not None:
        return _pint_convert(value, source, target)
    return _internal_convert(value, source, target)


def validate_property_unit(property_key: str, unit: str, canonical_unit: str) -> None:
    normalized = ensure_known(unit)
    expected_dimension = PROPERTY_DIMENSIONS.get(property_key)
    if expected_dimension and UNITS[normalized].dimension != expected_dimension:
        raise UnitError(f"Unit {unit} is incompatible with property {property_key}")
    ensure_compatible(unit, canonical_unit)
