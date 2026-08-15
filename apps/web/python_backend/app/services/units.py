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

    # --- Phase 12: engineering datasheet units --------------------------------------------------
    # Every unit below appears on a real supplier datasheet or a real ISO/ASTM test report. They
    # are what an engineer types when transcribing a datasheet, so refusing them pushed users into
    # inventing a unit the system did accept — which is how silently wrong numbers get stored.
    # All are declared INTERNAL_ONLY below: pint parses several of them as unrelated quantities
    # (`d` as day vs. deuteron-adjacent contexts, `V` fine but `HV` not, `wk` not at all), and a
    # datasheet transcription is exactly where a silent misparse would be most expensive.
    #
    # Notched impact strength. ISO 180 reports per unit width, ISO 179 per unit area; they are not
    # interconvertible without specimen geometry, so they are deliberately distinct dimensions.
    "J/m": UnitSpec("impact_energy_per_width", 1.0, 0.0, "J/m"),
    "ft*lb/in": UnitSpec("impact_energy_per_width", 53.3787, 0.0, "J/m"),
    "kJ/m^2": UnitSpec("impact_energy_per_area", 1.0, 0.0, "kJ/m^2"),
    "J/m^2": UnitSpec("impact_energy_per_area", 1e-3, 0.0, "kJ/m^2"),
    # Linear-elastic fracture toughness (ASTM E399 / ISO 13586).
    "MPa*m^0.5": UnitSpec("fracture_toughness", 1.0, 0.0, "MPa*m^0.5"),
    "ksi*in^0.5": UnitSpec("fracture_toughness", 1.0988, 0.0, "MPa*m^0.5"),
    # Melt flow (ISO 1133). Mass rate and volume rate are separate quantities; converting between
    # them requires melt density at the test condition, which is not part of the observation.
    "g/10min": UnitSpec("melt_flow_rate", 1.0, 0.0, "g/10min"),
    "cm^3/10min": UnitSpec("melt_volume_rate", 1.0, 0.0, "cm^3/10min"),
    # Electrical. Surface resistivity is reported in ohm (per square); volume resistivity reuses
    # the existing `resistivity` dimension declared above.
    "ohm": UnitSpec("resistance", 1.0, 0.0, "ohm"),
    "Mohm": UnitSpec("resistance", 1e6, 0.0, "ohm"),
    "Gohm": UnitSpec("resistance", 1e9, 0.0, "ohm"),
    "V": UnitSpec("voltage", 1.0, 0.0, "V"),
    "kV": UnitSpec("voltage", 1e3, 0.0, "V"),
    # Service and supply durations (salt-spray hours, lead time, shelf life). Kept dimensionally
    # separate from the femtosecond-scale `time` dimension used by molecular dynamics so a lead
    # time can never be converted into a simulation timestep.
    "h": UnitSpec("duration", 1.0, 0.0, "h"),
    "d": UnitSpec("duration", 24.0, 0.0, "h"),
    "wk": UnitSpec("duration", 168.0, 0.0, "h"),
    "month": UnitSpec("duration", 730.0, 0.0, "h"),
    "yr": UnitSpec("duration", 8760.0, 0.0, "h"),
    # Commercial.
    "USD/m^3": UnitSpec("cost_per_volume", 1.0, 0.0, "USD/m^3"),
    "USD/L": UnitSpec("cost_per_volume", 1000.0, 0.0, "USD/m^3"),
    "EUR/kg": UnitSpec("cost_per_mass_eur", 1.0, 0.0, "EUR/kg"),
    "INR/kg": UnitSpec("cost_per_mass_inr", 1.0, 0.0, "INR/kg"),
    # Embodied energy, the other half of a cradle-to-gate footprint claim.
    "MJ/kg": UnitSpec("embodied_energy", 1.0, 0.0, "MJ/kg"),
    "kWh/kg": UnitSpec("embodied_energy", 3.6, 0.0, "MJ/kg"),
    # Engineering lengths, for thickness-dependent datasheet values.
    "mm": UnitSpec("engineering_length", 1.0, 0.0, "mm"),
    "cm": UnitSpec("engineering_length", 10.0, 0.0, "mm"),
    "um": UnitSpec("engineering_length", 1e-3, 0.0, "mm"),
    "in": UnitSpec("engineering_length", 25.4, 0.0, "mm"),
    # Permeability, for barrier films and packaging.
    "cm^3/(m^2*d*bar)": UnitSpec("gas_permeability", 1.0, 0.0, "cm^3/(m^2*d*bar)"),
    "g/(m^2*d)": UnitSpec("water_vapour_transmission", 1.0, 0.0, "g/(m^2*d)"),
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
    # --- Phase 12 engineering property vocabulary ----------------------------------------------
    # Binding a key to a dimension here is what stops a flexural modulus in GPa being stored
    # against a key whose canonical unit is MPa-with-a-different-meaning. Every key the intake
    # catalogue can write is registered, so no catalogue property reaches the database unchecked.
    "tensile_modulus": "pressure",
    "flexural_strength": "pressure",
    "flexural_modulus": "pressure",
    "compressive_strength": "pressure",
    "shear_strength": "pressure",
    "fatigue_strength_1e7": "pressure",
    "creep_modulus_1000h": "pressure",
    "elongation_at_break": "percent",
    "izod_impact_notched": "impact_energy_per_width",
    "charpy_impact_notched": "impact_energy_per_area",
    "fracture_toughness_k1c": "fracture_toughness",
    "hardness_shore_d": "dimensionless",
    "hardness_rockwell_r": "dimensionless",
    "hardness_vickers": "dimensionless",
    "heat_deflection_temperature_1_8mpa": "temperature",
    "heat_deflection_temperature_0_45mpa": "temperature",
    "vicat_softening_temperature": "temperature",
    "continuous_service_temperature": "temperature",
    "peak_service_temperature": "temperature",
    "melting_temperature": "temperature",
    "oxidation_onset_temperature": "temperature",
    "processing_melt_temperature": "temperature",
    "coefficient_thermal_expansion": "thermal_expansion",
    "volume_resistivity": "resistivity",
    "surface_resistivity": "resistance",
    "dielectric_strength": "electric_field",
    "dissipation_factor": "dimensionless",
    "comparative_tracking_index": "voltage",
    "water_absorption_24h": "percent",
    "moisture_absorption_equilibrium": "percent",
    "limiting_oxygen_index": "percent",
    "salt_spray_resistance": "duration",
    "uv_stability_rating": "dimensionless",
    "chemical_resistance_rating": "dimensionless",
    "melt_flow_index": "melt_flow_rate",
    "mould_shrinkage": "percent",
    "cost_per_volume": "cost_per_volume",
    "lead_time": "duration",
    "supplier_count": "dimensionless",
    "price_volatility_index": "dimensionless",
    "embodied_energy": "embodied_energy",
    "recycled_content": "percent",
    "biobased_content": "percent",
    "recyclability_rating": "dimensionless",
    "oxygen_transmission_rate": "gas_permeability",
    "water_vapour_transmission_rate": "water_vapour_transmission",
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
    # Phase 12 datasheet units. See the rationale block in UNITS above.
    "J/m", "ft*lb/in", "kJ/m^2", "J/m^2",
    "MPa*m^0.5", "ksi*in^0.5",
    "g/10min", "cm^3/10min",
    "ohm", "Mohm", "Gohm", "V", "kV",
    "h", "d", "wk", "month", "yr",
    "USD/m^3", "USD/L", "EUR/kg", "INR/kg",
    "MJ/kg", "kWh/kg",
    "mm", "cm", "um", "in",
    "cm^3/(m^2*d*bar)", "g/(m^2*d)",
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
