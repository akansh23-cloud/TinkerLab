"""Phase 12 — the engineering vocabulary an industrial user actually works in.

Everything in this module is *declarative domain knowledge*, not inference. It exists because the
platform's scientific core was reachable only by someone who already knew the internal keys, the
canonical units and the checksum semantics. A materials engineer transcribing a supplier datasheet
knows "Izod notched, ISO 180/1A, 5.4 kJ/m^2" — not `izod_impact_notched` with a canonical unit.

Three things are declared here:

  PROPERTY_CATALOGUE   what an engineer can record, in datasheet vocabulary, with the test standard
                       that produces it and the range that is physically plausible per family.
  APPLICATION_PRESETS  what a real replacement brief looks like, per industrial application.
  STARTER_LIBRARY      a defensible set of reference materials so a fresh deployment is not empty.

A NOTE ON THE NUMBERS. Every value in `typical_range` and every value in `STARTER_LIBRARY` is a
*handbook-typical* figure — the range you would expect across commercial grades of that family.
They are recorded with `source_quality="handbook_typical"` and confidence <= 0.6, never as measured
data, and the intake service refuses to upgrade that grade. Ranges are used only to warn a user
that a typed value looks implausible; they never silently correct it, never populate a missing
value, and never participate in a verdict. That restraint is the whole point: this layer makes the
system usable without making it credulous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Direction = Literal["higher_is_better", "lower_is_better", "target_band", "neutral"]


@dataclass(frozen=True)
class PropertySpec:
    key: str
    display_name: str
    domain: str
    quantity_type: str
    canonical_unit: str | None
    accepted_units: tuple[str, ...]
    direction: Direction
    why_it_matters: str
    test_standard: str | None = None
    datasheet_aliases: tuple[str, ...] = ()
    typical_range: dict[str, tuple[float, float]] = field(default_factory=dict)
    allow_negative: bool = False
    conflict_policy: str = "relative"
    conflict_absolute_tolerance: float | None = None
    conflict_relative_tolerance: float | None = 0.10
    condition_sensitive: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "domain": self.domain,
            "quantity_type": self.quantity_type,
            "canonical_unit": self.canonical_unit,
            "accepted_units": list(self.accepted_units),
            "direction": self.direction,
            "why_it_matters": self.why_it_matters,
            "test_standard": self.test_standard,
            "datasheet_aliases": list(self.datasheet_aliases),
            "typical_range": {k: list(v) for k, v in self.typical_range.items()},
            "allow_negative": self.allow_negative,
            "condition_sensitive": self.condition_sensitive,
        }


DOMAINS: dict[str, dict[str, str]] = {
    "mechanical": {
        "display_name": "Mechanical",
        "description": "Load-bearing behaviour. Governs whether the part survives its duty cycle.",
    },
    "thermal": {
        "display_name": "Thermal",
        "description": "Behaviour against temperature. Usually the first thing that eliminates a drop-in substitute.",
    },
    "electrical": {
        "display_name": "Electrical",
        "description": "Insulation, tracking and dielectric behaviour. Decisive in e-mobility and electronics housings.",
    },
    "chemical": {
        "display_name": "Chemical & environmental",
        "description": "Resistance to fluids, moisture, UV and fire. Where field failures actually originate.",
    },
    "processing": {
        "display_name": "Processing",
        "description": "Whether the substitute runs on the tooling and line you already own.",
    },
    "commercial": {
        "display_name": "Commercial & supply",
        "description": "Landed cost, lead time and supplier depth. A qualified material you cannot buy is not a substitute.",
    },
    "sustainability": {
        "display_name": "Sustainability",
        "description": "Cradle-to-gate burden and circularity, increasingly a contractual requirement rather than a preference.",
    },
    "regulatory": {
        "display_name": "Regulatory & compliance",
        "description": "Binary market-access gates. These do not trade off against performance — they pass or they block.",
    },
    "barrier": {
        "display_name": "Barrier",
        "description": "Permeation behaviour for packaging, sealing and containment applications.",
    },
}


# ---------------------------------------------------------------------------------------------
# Mechanical
# ---------------------------------------------------------------------------------------------
_MECHANICAL = [
    PropertySpec(
        key="density", display_name="Density", domain="mechanical", quantity_type="density",
        canonical_unit="kg/m^3", accepted_units=("kg/m^3", "g/cm^3"), direction="lower_is_better",
        why_it_matters="Sets part mass directly, and part mass drives shipping cost, vehicle range and assembly ergonomics.",
        test_standard="ISO 1183 / ASTM D792", datasheet_aliases=("specific gravity", "sg", "rho"),
        typical_range={"polymer": (800.0, 2200.0), "alloy": (1700.0, 19300.0), "ceramic": (2000.0, 6100.0),
                       "composite": (1100.0, 2200.0), "coating": (900.0, 3000.0), "adhesive": (900.0, 1800.0)},
        conflict_relative_tolerance=0.03,
    ),
    PropertySpec(
        key="tensile_strength", display_name="Tensile strength at break", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi", "kPa"), direction="higher_is_better",
        why_it_matters="The headline strength number. Necessary but rarely sufficient — check elongation and impact alongside it.",
        test_standard="ISO 527 / ASTM D638", datasheet_aliases=("ultimate tensile strength", "uts", "tensile str"),
        typical_range={"polymer": (10.0, 300.0), "alloy": (50.0, 2000.0), "ceramic": (50.0, 1000.0),
                       "composite": (100.0, 3500.0), "adhesive": (1.0, 80.0), "coating": (5.0, 150.0)},
        conflict_relative_tolerance=0.05, condition_sensitive=True,
    ),
    PropertySpec(
        key="yield_strength", display_name="Yield strength", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Onset of permanent deformation. For a dimensionally critical part this matters more than ultimate strength.",
        test_standard="ISO 527 / ASTM E8", datasheet_aliases=("yield stress", "proof stress", "rp0.2", "0.2% offset"),
        typical_range={"polymer": (5.0, 200.0), "alloy": (30.0, 1800.0), "composite": (80.0, 2000.0)},
        conflict_relative_tolerance=0.05, condition_sensitive=True,
    ),
    PropertySpec(
        key="tensile_modulus", display_name="Tensile modulus (Young's)", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Stiffness. Deflection under load scales inversely with it, so a stiffness drop shows up as rattle and creak long before anything breaks.",
        test_standard="ISO 527 / ASTM D638", datasheet_aliases=("young's modulus", "e-modulus", "elastic modulus", "tensile mod"),
        typical_range={"polymer": (100.0, 25000.0), "alloy": (40000.0, 420000.0), "ceramic": (60000.0, 500000.0),
                       "composite": (5000.0, 300000.0)},
        conflict_relative_tolerance=0.08, condition_sensitive=True,
    ),
    PropertySpec(
        key="flexural_strength", display_name="Flexural strength", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Governs ribbed and panel geometries, which is most injection-moulded structure.",
        test_standard="ISO 178 / ASTM D790", datasheet_aliases=("bending strength", "modulus of rupture", "flex str"),
        typical_range={"polymer": (10.0, 400.0), "ceramic": (50.0, 1200.0), "composite": (100.0, 2000.0)},
    ),
    PropertySpec(
        key="flexural_modulus", display_name="Flexural modulus", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="The stiffness figure most polymer datasheets actually lead with. Compare like with like — flexural and tensile moduli are not interchangeable.",
        test_standard="ISO 178 / ASTM D790", datasheet_aliases=("flex mod", "bending modulus"),
        typical_range={"polymer": (200.0, 30000.0), "composite": (5000.0, 250000.0)},
    ),
    PropertySpec(
        key="compressive_strength", display_name="Compressive strength", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Decisive for bearings, seals, gaskets and anything under bolt preload.",
        test_standard="ISO 604 / ASTM D695", datasheet_aliases=("compression strength",),
        typical_range={"polymer": (10.0, 300.0), "ceramic": (300.0, 5000.0), "alloy": (50.0, 2500.0)},
    ),
    PropertySpec(
        key="shear_strength", display_name="Shear strength", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Governs bonded joints, fasteners and snap-fits — the places assemblies actually come apart.",
        test_standard="ASTM D732 / ISO 4587", datasheet_aliases=("lap shear strength", "shear str"),
        typical_range={"polymer": (5.0, 150.0), "adhesive": (1.0, 50.0), "alloy": (30.0, 1200.0)},
    ),
    PropertySpec(
        key="elongation_at_break", display_name="Elongation at break", domain="mechanical", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="higher_is_better",
        why_it_matters="Ductility. A substitute that matches strength but collapses elongation will pass the test bench and shatter in the field.",
        test_standard="ISO 527 / ASTM D638", datasheet_aliases=("strain at break", "elongation", "ductility"),
        typical_range={"polymer": (0.5, 900.0), "alloy": (1.0, 70.0), "ceramic": (0.0, 1.0), "composite": (0.3, 10.0)},
        conflict_relative_tolerance=0.25, condition_sensitive=True,
    ),
    PropertySpec(
        key="izod_impact_notched", display_name="Notched Izod impact strength", domain="mechanical",
        quantity_type="impact_energy_per_width", canonical_unit="J/m", accepted_units=("J/m", "ft*lb/in"),
        direction="higher_is_better",
        why_it_matters="Toughness against a stress concentrator. Every real part has notches — ribs, gates, bosses, weld lines.",
        test_standard="ASTM D256", datasheet_aliases=("izod", "notched izod", "impact strength izod"),
        typical_range={"polymer": (5.0, 1200.0), "composite": (20.0, 900.0)},
        conflict_relative_tolerance=0.20, condition_sensitive=True,
    ),
    PropertySpec(
        key="charpy_impact_notched", display_name="Notched Charpy impact strength", domain="mechanical",
        quantity_type="impact_energy_per_area", canonical_unit="kJ/m^2", accepted_units=("kJ/m^2", "J/m^2"),
        direction="higher_is_better",
        why_it_matters="The ISO equivalent of Izod. Reported per unit area, so it is not convertible to Izod without specimen geometry — do not mix them.",
        test_standard="ISO 179", datasheet_aliases=("charpy", "notched charpy", "izod iso"),
        typical_range={"polymer": (1.0, 100.0), "alloy": (5.0, 300.0), "composite": (5.0, 150.0)},
        conflict_relative_tolerance=0.20, condition_sensitive=True,
    ),
    PropertySpec(
        key="fatigue_strength_1e7", display_name="Fatigue strength at 10^7 cycles", domain="mechanical",
        quantity_type="pressure", canonical_unit="MPa", accepted_units=("MPa", "psi"), direction="higher_is_better",
        why_it_matters="The number that predicts warranty claims on any cyclically loaded part. Almost never on a polymer datasheet, which is itself the finding.",
        test_standard="ISO 1099 / ASTM E466", datasheet_aliases=("endurance limit", "fatigue limit", "s-n at 1e7"),
        typical_range={"polymer": (5.0, 80.0), "alloy": (20.0, 900.0), "composite": (30.0, 800.0)},
        conflict_relative_tolerance=0.15, condition_sensitive=True,
    ),
    PropertySpec(
        key="fracture_toughness_k1c", display_name="Fracture toughness K1c", domain="mechanical",
        quantity_type="fracture_toughness", canonical_unit="MPa*m^0.5", accepted_units=("MPa*m^0.5", "ksi*in^0.5"),
        direction="higher_is_better",
        why_it_matters="Tolerance to a pre-existing flaw. The controlling property for ceramics and any safety-critical metallic part.",
        test_standard="ASTM E399 / ISO 13586", datasheet_aliases=("k1c", "kic", "plane strain fracture toughness"),
        typical_range={"polymer": (0.5, 8.0), "alloy": (10.0, 200.0), "ceramic": (0.5, 15.0), "composite": (5.0, 60.0)},
    ),
    PropertySpec(
        key="creep_modulus_1000h", display_name="Creep modulus at 1000 h", domain="mechanical", quantity_type="pressure",
        canonical_unit="MPa", accepted_units=("MPa", "GPa", "psi"), direction="higher_is_better",
        why_it_matters="Long-term stiffness under sustained load. Short-term modulus flatters a polymer badly here; bolted joints relax and seals leak.",
        test_standard="ISO 899", datasheet_aliases=("creep modulus", "apparent modulus 1000h"),
        typical_range={"polymer": (50.0, 20000.0), "composite": (2000.0, 200000.0)},
        condition_sensitive=True,
    ),
    PropertySpec(
        key="poisson_ratio", display_name="Poisson's ratio", domain="mechanical", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="neutral",
        why_it_matters="Needed for any credible FEA. Assuming a default here quietly invalidates the simulation that justified the switch.",
        test_standard="ISO 527", datasheet_aliases=("nu", "poisson"),
        typical_range={"polymer": (0.30, 0.48), "alloy": (0.20, 0.45), "ceramic": (0.10, 0.35)},
    ),
    PropertySpec(
        key="hardness_shore_d", display_name="Hardness (Shore D)", domain="mechanical", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="Surface indentation resistance for rigid polymers. A dimensionless scale reading — never compare across Shore A/D or Rockwell scales.",
        test_standard="ISO 868 / ASTM D2240", datasheet_aliases=("shore d", "durometer d"),
        typical_range={"polymer": (30.0, 90.0), "adhesive": (10.0, 85.0)},
    ),
    PropertySpec(
        key="hardness_rockwell_r", display_name="Hardness (Rockwell R)", domain="mechanical", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="The common scale for filled engineering thermoplastics. Scale-specific and dimensionless by construction.",
        test_standard="ISO 2039-2 / ASTM D785", datasheet_aliases=("rockwell r", "hrr"),
        typical_range={"polymer": (40.0, 130.0)},
    ),
    PropertySpec(
        key="hardness_vickers", display_name="Hardness (Vickers HV)", domain="mechanical", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="The metals and ceramics scale. Correlates with wear resistance and, for steels, roughly with tensile strength.",
        test_standard="ISO 6507 / ASTM E384", datasheet_aliases=("vickers", "hv", "microhardness"),
        typical_range={"alloy": (20.0, 1200.0), "ceramic": (500.0, 3000.0), "coating": (100.0, 3500.0)},
    ),
]

# ---------------------------------------------------------------------------------------------
# Thermal
# ---------------------------------------------------------------------------------------------
_THERMAL = [
    PropertySpec(
        key="continuous_service_temperature", display_name="Continuous service temperature", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="The long-term ceiling, derived from thermal ageing rather than a single-point softening test. This is the number that decides under-hood viability.",
        test_standard="UL 746B RTI / IEC 60216", datasheet_aliases=("rti", "continuous use temperature", "cut", "max service temp"),
        typical_range={"polymer": (50.0, 300.0), "alloy": (100.0, 1200.0), "ceramic": (400.0, 1800.0), "composite": (60.0, 350.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=8.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="operating_temperature", display_name="Operating temperature (legacy key)", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Retained for continuity with existing projects. Prefer continuous service temperature, which states the ageing basis.",
        test_standard=None, datasheet_aliases=("operating temp",),
        typical_range={"polymer": (50.0, 300.0), "alloy": (100.0, 1200.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=8.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="peak_service_temperature", display_name="Peak/short-term service temperature", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Survivable excursion, not a duty point. Confusing peak with continuous is the single most common substitution error.",
        test_standard=None, datasheet_aliases=("short term temperature", "peak temp", "excursion"),
        typical_range={"polymer": (60.0, 350.0), "alloy": (150.0, 1400.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=10.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="heat_deflection_temperature_1_8mpa", display_name="Heat deflection temperature @ 1.8 MPa", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Short-term load-bearing ceiling at high stress. Useful for screening, misleading if read as a service temperature.",
        test_standard="ISO 75-2 / ASTM D648", datasheet_aliases=("hdt a", "hdt 1.8", "dtul 264 psi"),
        typical_range={"polymer": (40.0, 320.0), "composite": (80.0, 350.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=6.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="heat_deflection_temperature_0_45mpa", display_name="Heat deflection temperature @ 0.45 MPa", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="The low-stress HDT. Always higher than the 1.8 MPa figure — quoting the wrong one flatters a material by tens of degrees.",
        test_standard="ISO 75-2 / ASTM D648", datasheet_aliases=("hdt b", "hdt 0.45", "dtul 66 psi"),
        typical_range={"polymer": (50.0, 340.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=6.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="glass_transition_temperature", display_name="Glass transition temperature (Tg)", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Where an amorphous polymer loses most of its stiffness. Crossing Tg in service is a step change, not a gradual derating.",
        test_standard="ISO 11357 (DSC) / ISO 6721 (DMA)", datasheet_aliases=("tg", "glass transition"),
        typical_range={"polymer": (-120.0, 400.0), "composite": (60.0, 400.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=5.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="melting_temperature", display_name="Melting temperature (Tm)", domain="thermal", quantity_type="temperature",
        canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Sets the processing window for semi-crystalline polymers and the hard ceiling for metals.",
        test_standard="ISO 11357 (DSC)", datasheet_aliases=("tm", "melting point", "melt point"),
        typical_range={"polymer": (60.0, 400.0), "alloy": (200.0, 3400.0), "ceramic": (1000.0, 3900.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=5.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="vicat_softening_temperature", display_name="Vicat softening temperature", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Penetration-based softening point. The most comparable thermal figure across unfilled thermoplastics.",
        test_standard="ISO 306 / ASTM D1525", datasheet_aliases=("vicat", "vst", "vicat b50"),
        typical_range={"polymer": (40.0, 350.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=5.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="thermal_conductivity", display_name="Thermal conductivity", domain="thermal",
        quantity_type="thermal_conductivity", canonical_unit="W/(m*K)",
        accepted_units=("W/(m*K)", "W/(cm*K)", "mW/(m*K)"), direction="neutral",
        why_it_matters="Direction depends entirely on the job: insulation wants it low, a heat-sink or battery housing wants it high.",
        test_standard="ISO 22007 / ASTM E1461", datasheet_aliases=("k", "lambda", "thermal cond"),
        typical_range={"polymer": (0.1, 25.0), "alloy": (5.0, 430.0), "ceramic": (1.0, 400.0), "composite": (0.2, 200.0)},
        conflict_relative_tolerance=0.12, condition_sensitive=True,
    ),
    PropertySpec(
        key="coefficient_thermal_expansion", display_name="Coefficient of linear thermal expansion", domain="thermal",
        quantity_type="thermal_expansion", canonical_unit="1e-6/K", accepted_units=("1e-6/K", "ppm/K", "1/K"),
        direction="lower_is_better",
        why_it_matters="A CTE mismatch across a bolted or bonded interface is what cracks assemblies through thermal cycling, even when every part is individually within spec.",
        test_standard="ISO 11359 / ASTM E831", datasheet_aliases=("cte", "clte", "thermal expansion"),
        typical_range={"polymer": (10.0, 200.0), "alloy": (5.0, 30.0), "ceramic": (0.5, 12.0), "composite": (-1.0, 60.0)},
        allow_negative=True, conflict_relative_tolerance=0.15, condition_sensitive=True,
    ),
    PropertySpec(
        key="specific_heat_capacity", display_name="Specific heat capacity", domain="thermal", quantity_type="specific_heat",
        canonical_unit="J/(kg*K)", accepted_units=("J/(kg*K)", "J/(g*K)"), direction="neutral",
        why_it_matters="Needed for any transient thermal model, and for cooling-time estimates in moulding.",
        test_standard="ISO 11357-4 / ASTM E1269", datasheet_aliases=("cp", "specific heat"),
        typical_range={"polymer": (800.0, 2500.0), "alloy": (100.0, 1000.0), "ceramic": (400.0, 1200.0)},
    ),
    PropertySpec(
        key="oxidation_onset_temperature", display_name="Oxidation onset temperature", domain="thermal",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="higher_is_better",
        why_it_matters="Where thermal-oxidative degradation begins. The practical limit for long-duty parts in air, ahead of any mechanical limit.",
        test_standard="ISO 11357-6 (OIT/OOT)", datasheet_aliases=("oot", "oit onset"),
        typical_range={"polymer": (150.0, 450.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=8.0, conflict_relative_tolerance=None,
    ),
]

# ---------------------------------------------------------------------------------------------
# Electrical
# ---------------------------------------------------------------------------------------------
_ELECTRICAL = [
    PropertySpec(
        key="volume_resistivity", display_name="Volume resistivity", domain="electrical", quantity_type="resistivity",
        canonical_unit="ohm*cm", accepted_units=("ohm*cm", "ohm*m", "uohm*cm"), direction="higher_is_better",
        why_it_matters="Bulk insulation quality. For a conductor the same measurement is read the opposite way — declare the intent in the requirement, not the property.",
        test_standard="IEC 62631 / ASTM D257", datasheet_aliases=("volume resistivity", "bulk resistivity"),
        typical_range={"polymer": (1e6, 1e18), "alloy": (1e-6, 1e-3), "ceramic": (1e2, 1e16)},
        conflict_relative_tolerance=0.50,
    ),
    PropertySpec(
        key="surface_resistivity", display_name="Surface resistivity", domain="electrical", quantity_type="resistance",
        canonical_unit="ohm", accepted_units=("ohm", "Mohm", "Gohm"), direction="higher_is_better",
        why_it_matters="Controls static build-up. ESD-safe enclosures specify a window, not a maximum — too insulating is also a failure.",
        test_standard="IEC 62631-3-2 / ASTM D257", datasheet_aliases=("surface resistivity", "sheet resistance"),
        typical_range={"polymer": (1e3, 1e18)},
        conflict_relative_tolerance=0.50,
    ),
    PropertySpec(
        key="dielectric_strength", display_name="Dielectric strength", domain="electrical", quantity_type="electric_field",
        canonical_unit="kV/mm", accepted_units=("kV/mm", "MV/cm", "V/m", "V/cm"), direction="higher_is_better",
        why_it_matters="Breakdown field. Strongly thickness-dependent, so a value without its specimen thickness is not comparable.",
        test_standard="IEC 60243 / ASTM D149", datasheet_aliases=("breakdown voltage", "electric strength"),
        typical_range={"polymer": (5.0, 100.0), "ceramic": (1.0, 60.0), "coating": (5.0, 120.0)},
        conflict_relative_tolerance=0.15, condition_sensitive=True,
    ),
    PropertySpec(
        key="dielectric_constant", display_name="Relative permittivity (Dk)", domain="electrical",
        quantity_type="dimensionless", canonical_unit="1", accepted_units=("1",), direction="lower_is_better",
        why_it_matters="Signal-integrity driver in high-frequency electronics; must be quoted with its test frequency to mean anything.",
        test_standard="IEC 62631-2-1 / ASTM D150", datasheet_aliases=("dk", "permittivity", "epsilon r"),
        typical_range={"polymer": (1.8, 12.0), "ceramic": (4.0, 12000.0)},
        conflict_relative_tolerance=0.10, condition_sensitive=True,
    ),
    PropertySpec(
        key="dissipation_factor", display_name="Dissipation factor (Df / tan δ)", domain="electrical",
        quantity_type="dimensionless", canonical_unit="1", accepted_units=("1",), direction="lower_is_better",
        why_it_matters="Dielectric loss, so it becomes self-heating at frequency. The property that eliminates otherwise-good polymers from RF work.",
        test_standard="IEC 62631-2-1 / ASTM D150", datasheet_aliases=("tan delta", "loss tangent", "df"),
        typical_range={"polymer": (1e-5, 0.1), "ceramic": (1e-5, 0.05)},
        conflict_relative_tolerance=0.30, condition_sensitive=True,
    ),
    PropertySpec(
        key="comparative_tracking_index", display_name="Comparative tracking index (CTI)", domain="electrical",
        quantity_type="voltage", canonical_unit="V", accepted_units=("V", "kV"), direction="higher_is_better",
        why_it_matters="Resistance to surface tracking under contamination. A hard gate for high-voltage EV connectors and busbar supports.",
        test_standard="IEC 60112", datasheet_aliases=("cti", "pti", "tracking index"),
        typical_range={"polymer": (100.0, 600.0)},
        conflict_relative_tolerance=0.10,
    ),
]

# ---------------------------------------------------------------------------------------------
# Chemical & environmental
# ---------------------------------------------------------------------------------------------
_CHEMICAL = [
    PropertySpec(
        key="water_absorption_24h", display_name="Water absorption (24 h)", domain="chemical", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="lower_is_better",
        why_it_matters="Short-term uptake. For polyamides this is the property that quietly moves every dimension and halves the modulus.",
        test_standard="ISO 62 / ASTM D570", datasheet_aliases=("water absorption", "moisture uptake 24h"),
        typical_range={"polymer": (0.0, 10.0), "composite": (0.0, 5.0), "ceramic": (0.0, 20.0)},
        conflict_relative_tolerance=0.25,
    ),
    PropertySpec(
        key="moisture_absorption_equilibrium", display_name="Moisture absorption at equilibrium", domain="chemical",
        quantity_type="percent", canonical_unit="%", accepted_units=("%",), direction="lower_is_better",
        why_it_matters="The saturated figure at a stated humidity. Datasheet mechanical values are usually dry-as-moulded; conditioned values can be far lower.",
        test_standard="ISO 62 / ASTM D570", datasheet_aliases=("equilibrium moisture", "saturation moisture", "50% rh moisture"),
        typical_range={"polymer": (0.0, 12.0)},
        conflict_relative_tolerance=0.25, condition_sensitive=True,
    ),
    PropertySpec(
        key="limiting_oxygen_index", display_name="Limiting oxygen index (LOI)", domain="chemical", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="higher_is_better",
        why_it_matters="A continuous flammability measure, so unlike a UL 94 rating it can be ranked and optimised.",
        test_standard="ISO 4589 / ASTM D2863", datasheet_aliases=("loi", "oxygen index"),
        typical_range={"polymer": (15.0, 95.0)},
        conflict_relative_tolerance=0.08,
    ),
    PropertySpec(
        key="salt_spray_resistance", display_name="Salt spray resistance", domain="chemical", quantity_type="duration",
        canonical_unit="h", accepted_units=("h", "d", "wk"), direction="higher_is_better",
        why_it_matters="Hours to first defect in neutral salt fog. The accepted corrosion screen for coatings and plated parts.",
        test_standard="ISO 9227 / ASTM B117", datasheet_aliases=("salt spray", "nss hours", "b117"),
        typical_range={"coating": (24.0, 5000.0), "alloy": (24.0, 3000.0)},
        conflict_relative_tolerance=0.30,
    ),
    PropertySpec(
        key="chemical_resistance_rating", display_name="Chemical resistance rating", domain="chemical",
        quantity_type="dimensionless", canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="A curator-assigned 0–5 index against a declared reagent set. Explicitly a judgement, recorded as one — it never carries measurement provenance.",
        test_standard="ISO 175 (immersion basis)", datasheet_aliases=("chemical resistance",),
        typical_range={"polymer": (0.0, 5.0), "coating": (0.0, 5.0)},
        conflict_relative_tolerance=0.20,
    ),
    PropertySpec(
        key="uv_stability_rating", display_name="UV / weathering rating", domain="chemical", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="A curator-assigned 0–5 index for outdoor exposure. Retained property after accelerated weathering is the defensible version of this.",
        test_standard="ISO 4892 / ASTM G154 (basis)", datasheet_aliases=("uv resistance", "weatherability"),
        typical_range={"polymer": (0.0, 5.0), "coating": (0.0, 5.0)},
        conflict_relative_tolerance=0.20,
    ),
]

# ---------------------------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------------------------
_PROCESSING = [
    PropertySpec(
        key="melt_flow_index", display_name="Melt flow index (MFI/MFR)", domain="processing",
        quantity_type="melt_flow_rate", canonical_unit="g/10min", accepted_units=("g/10min",), direction="neutral",
        why_it_matters="Sets whether the grade fills your existing tool. Only comparable at the same temperature and load — always record both.",
        test_standard="ISO 1133 / ASTM D1238", datasheet_aliases=("mfi", "mfr", "melt index", "melt flow"),
        typical_range={"polymer": (0.1, 200.0)},
        conflict_relative_tolerance=0.20, condition_sensitive=True,
    ),
    PropertySpec(
        key="processing_melt_temperature", display_name="Recommended melt temperature", domain="processing",
        quantity_type="temperature", canonical_unit="degC", accepted_units=("degC", "K"), direction="neutral",
        why_it_matters="If the substitute needs a melt temperature your barrel or hot runner cannot reach, the switch is a capital project, not a material change.",
        test_standard=None, datasheet_aliases=("melt temperature", "processing temperature", "barrel temperature"),
        typical_range={"polymer": (150.0, 420.0)},
        allow_negative=True, conflict_policy="absolute", conflict_absolute_tolerance=10.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="mould_shrinkage", display_name="Mould shrinkage", domain="processing", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="lower_is_better",
        why_it_matters="Decides whether existing tooling can be reused. A shrinkage delta beyond roughly 0.1% usually means steel changes.",
        test_standard="ISO 294-4 / ASTM D955", datasheet_aliases=("shrinkage", "mold shrinkage", "linear shrinkage"),
        typical_range={"polymer": (0.0, 4.0), "composite": (0.0, 2.0)},
        conflict_relative_tolerance=0.25, condition_sensitive=True,
    ),
]

# ---------------------------------------------------------------------------------------------
# Commercial & supply
# ---------------------------------------------------------------------------------------------
_COMMERCIAL = [
    PropertySpec(
        key="cost_per_mass", display_name="Material cost (per mass)", domain="commercial", quantity_type="cost_per_mass",
        canonical_unit="USD/kg", accepted_units=("USD/kg", "USD/tonne", "USD/g"), direction="lower_is_better",
        why_it_matters="Resin price, not part cost. Compare on cost per part — a denser or slower-cycling material can be cheaper per kilo and dearer per part.",
        test_standard=None, datasheet_aliases=("price", "resin price", "cost"),
        typical_range={"polymer": (0.8, 200.0), "alloy": (0.5, 500.0), "ceramic": (2.0, 900.0), "composite": (3.0, 500.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="cost_per_volume", display_name="Material cost (per volume)", domain="commercial",
        quantity_type="cost_per_volume", canonical_unit="USD/m^3", accepted_units=("USD/m^3", "USD/L"),
        direction="lower_is_better",
        why_it_matters="The honest basis for comparing materials of different density, because parts are moulded to a volume, not to a mass.",
        test_standard=None, datasheet_aliases=("cost per litre", "volumetric cost"),
        typical_range={"polymer": (800.0, 300000.0), "alloy": (2000.0, 2000000.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="lead_time", display_name="Typical lead time", domain="commercial", quantity_type="duration",
        canonical_unit="wk", accepted_units=("wk", "d", "h", "month"), direction="lower_is_better",
        why_it_matters="A technically perfect substitute on a 26-week lead time cannot support a running line.",
        test_standard=None, datasheet_aliases=("lead time", "delivery time"),
        typical_range={"polymer": (0.5, 52.0), "alloy": (1.0, 78.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="supplier_count", display_name="Qualified supplier count", domain="commercial", quantity_type="dimensionless",
        canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="Single-sourcing is the risk that replacement programmes most often exist to remove. Two qualified sources is usually the real target.",
        test_standard=None, datasheet_aliases=("number of suppliers", "sources"),
        typical_range={"polymer": (1.0, 40.0), "alloy": (1.0, 60.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="price_volatility_index", display_name="Price volatility index", domain="commercial",
        quantity_type="dimensionless", canonical_unit="1", accepted_units=("1",), direction="lower_is_better",
        why_it_matters="A curator-assigned 0–5 index of price stability. Substituting into a more volatile feedstock can erase the saving within a year.",
        test_standard=None, datasheet_aliases=("price stability", "volatility"),
        typical_range={"polymer": (0.0, 5.0), "alloy": (0.0, 5.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
]

# ---------------------------------------------------------------------------------------------
# Sustainability
# ---------------------------------------------------------------------------------------------
_SUSTAINABILITY = [
    PropertySpec(
        key="carbon_footprint", display_name="Cradle-to-gate carbon footprint", domain="sustainability",
        quantity_type="carbon_footprint", canonical_unit="kgCO2e/kg", accepted_units=("kgCO2e/kg",),
        direction="lower_is_better",
        why_it_matters="Increasingly a contractual term rather than a preference. Only comparable when the system boundary and dataset match.",
        test_standard="ISO 14040/14044 (basis)", datasheet_aliases=("gwp", "carbon footprint", "co2e"),
        typical_range={"polymer": (0.5, 30.0), "alloy": (0.3, 80.0), "composite": (2.0, 60.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="embodied_energy", display_name="Embodied energy", domain="sustainability", quantity_type="embodied_energy",
        canonical_unit="MJ/kg", accepted_units=("MJ/kg", "kWh/kg"), direction="lower_is_better",
        why_it_matters="The energy half of the footprint claim, and the one that moves most when a supplier changes their electricity mix.",
        test_standard="ISO 14040/14044 (basis)", datasheet_aliases=("primary energy", "embodied energy"),
        typical_range={"polymer": (30.0, 400.0), "alloy": (20.0, 600.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="recycled_content", display_name="Recycled content", domain="sustainability", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="higher_is_better",
        why_it_matters="Often mandated by customer or regulation. Post-consumer and post-industrial content are not equivalent — record which.",
        test_standard="ISO 14021", datasheet_aliases=("pcr content", "recycled content"),
        typical_range={"polymer": (0.0, 100.0), "alloy": (0.0, 100.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="biobased_content", display_name="Bio-based carbon content", domain="sustainability", quantity_type="percent",
        canonical_unit="%", accepted_units=("%",), direction="higher_is_better",
        why_it_matters="Measurable by radiocarbon assay, unlike most sustainability claims. Bio-based does not imply biodegradable or lower footprint.",
        test_standard="ASTM D6866 / EN 16640", datasheet_aliases=("biobased content", "bio content"),
        typical_range={"polymer": (0.0, 100.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="recyclability_rating", display_name="Recyclability rating", domain="sustainability",
        quantity_type="dimensionless", canonical_unit="1", accepted_units=("1",), direction="higher_is_better",
        why_it_matters="A curator-assigned 0–5 index for end-of-life recovery. Filled and alloyed grades usually score below their base polymer.",
        test_standard=None, datasheet_aliases=("recyclability",),
        typical_range={"polymer": (0.0, 5.0), "composite": (0.0, 5.0)},
        conflict_policy="informational", conflict_relative_tolerance=None,
    ),
]

# ---------------------------------------------------------------------------------------------
# Barrier
# ---------------------------------------------------------------------------------------------
_BARRIER = [
    PropertySpec(
        key="oxygen_transmission_rate", display_name="Oxygen transmission rate (OTR)", domain="barrier",
        quantity_type="gas_permeability", canonical_unit="cm^3/(m^2*d*bar)", accepted_units=("cm^3/(m^2*d*bar)",),
        direction="lower_is_better",
        why_it_matters="Sets shelf life for packaged food and the moisture ingress budget for electronics encapsulation.",
        test_standard="ASTM D3985 / ISO 15105", datasheet_aliases=("otr", "oxygen permeability"),
        typical_range={"polymer": (0.01, 10000.0)},
        conflict_relative_tolerance=0.30, condition_sensitive=True,
    ),
    PropertySpec(
        key="water_vapour_transmission_rate", display_name="Water vapour transmission rate (WVTR)", domain="barrier",
        quantity_type="water_vapour_transmission", canonical_unit="g/(m^2*d)", accepted_units=("g/(m^2*d)",),
        direction="lower_is_better",
        why_it_matters="The other half of the packaging barrier pair. Strongly temperature- and humidity-dependent, so the test condition is part of the value.",
        test_standard="ASTM F1249 / ISO 15106", datasheet_aliases=("wvtr", "mvtr", "moisture barrier"),
        typical_range={"polymer": (0.01, 500.0)},
        conflict_relative_tolerance=0.30, condition_sensitive=True,
    ),
]

# ---------------------------------------------------------------------------------------------
# Regulatory — modelled as booleans on purpose.
#
# A compliance status is a gate, not a score. Representing "REACH SVHC present" as a boolean means
# it can never be traded off against a strength margin by a weighted objective function, which is
# exactly the failure mode that gets a product pulled from a market.
# ---------------------------------------------------------------------------------------------
_REGULATORY = [
    PropertySpec(
        key="reach_svhc_present", display_name="Contains REACH SVHC (>0.1% w/w)", domain="regulatory",
        quantity_type="boolean", canonical_unit=None, accepted_units=(), direction="lower_is_better",
        why_it_matters="Above 0.1% w/w this triggers Article 33 communication duties and, for Annex XIV entries, authorisation. The most common trigger for a replacement programme in the EU.",
        test_standard="EC 1907/2006 (REACH) Art. 33/57", datasheet_aliases=("svhc", "reach svhc"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="rohs_compliant", display_name="RoHS compliant", domain="regulatory", quantity_type="boolean",
        canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="Market access gate for electrical and electronic equipment in the EU and, by adoption, most other markets.",
        test_standard="EU 2011/65 + 2015/863", datasheet_aliases=("rohs",),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="pfas_present", display_name="Contains intentionally added PFAS", domain="regulatory", quantity_type="boolean",
        canonical_unit=None, accepted_units=(), direction="lower_is_better",
        why_it_matters="The restriction proposal under REACH covers a very broad definition. Fluoropolymer processing aids and PTFE-modified grades are both in scope.",
        test_standard="ECHA universal PFAS restriction proposal", datasheet_aliases=("pfas", "fluorinated"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="halogen_free", display_name="Halogen free", domain="regulatory", quantity_type="boolean",
        canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="Required by many OEM specifications for cabling and enclosures, independently of RoHS.",
        test_standard="IEC 61249-2-21", datasheet_aliases=("halogen free", "hf"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="food_contact_compliant", display_name="Food contact compliant", domain="regulatory", quantity_type="boolean",
        canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="EU 10/2011 and FDA 21 CFR are not equivalent. Record which regime the claim refers to in the evidence note.",
        test_standard="EU 10/2011 / FDA 21 CFR 177", datasheet_aliases=("food contact", "food grade"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="biocompatible_usp_vi", display_name="USP Class VI / ISO 10993 assessed", domain="regulatory",
        quantity_type="boolean", canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="Entry gate for medical device contact. Grade-specific and lot-sensitive — never inherit it from the base polymer.",
        test_standard="USP <88> Class VI / ISO 10993", datasheet_aliases=("usp vi", "iso 10993", "biocompatible"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="flammability_ul94_v0", display_name="Meets UL 94 V-0", domain="regulatory", quantity_type="boolean",
        canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="Thickness-specific: a V-0 at 1.5 mm is not a V-0 at 0.75 mm. Record the rated thickness in the evidence note.",
        test_standard="UL 94 / IEC 60695-11-10", datasheet_aliases=("ul94 v0", "v-0", "flame rating"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
    PropertySpec(
        key="existing_equipment_compatible", display_name="Runs on existing equipment", domain="regulatory",
        quantity_type="boolean", canonical_unit=None, accepted_units=(), direction="higher_is_better",
        why_it_matters="Curator-declared: does this run on current tooling and line settings without capital change? Usually the true gate on adoption speed.",
        test_standard=None, datasheet_aliases=("drop-in", "tooling compatible"),
        conflict_policy="absolute", conflict_absolute_tolerance=0.0, conflict_relative_tolerance=None,
    ),
]


PROPERTY_CATALOGUE: tuple[PropertySpec, ...] = tuple(
    _MECHANICAL + _THERMAL + _ELECTRICAL + _CHEMICAL + _PROCESSING
    + _COMMERCIAL + _SUSTAINABILITY + _BARRIER + _REGULATORY
)

CATALOGUE_BY_KEY: dict[str, PropertySpec] = {spec.key: spec for spec in PROPERTY_CATALOGUE}

# Datasheet-label -> catalogue key. Built once so a CSV or a paste can be mapped without the user
# knowing internal keys. Lower-cased and whitespace-normalised at lookup time.
ALIAS_INDEX: dict[str, str] = {}
for _spec in PROPERTY_CATALOGUE:
    ALIAS_INDEX[_spec.display_name.lower()] = _spec.key
    ALIAS_INDEX[_spec.key.lower()] = _spec.key
    for _alias in _spec.datasheet_aliases:
        ALIAS_INDEX.setdefault(_alias.lower(), _spec.key)


def resolve_property_key(label: str) -> str | None:
    """Map a datasheet label onto a catalogue key. Returns None rather than guessing."""
    cleaned = " ".join(label.strip().lower().split())
    if cleaned in ALIAS_INDEX:
        return ALIAS_INDEX[cleaned]
    collapsed = cleaned.replace("-", " ").replace("_", " ")
    return ALIAS_INDEX.get(collapsed)


def plausibility(key: str, value: float, family: str) -> dict[str, Any] | None:
    """Return a warning when a value sits outside the handbook range for its family.

    This is advisory only. It never blocks a write and never alters a value: a genuinely novel
    material is exactly the case where a handbook range should be wrong, and a tool that refused
    the number would be worse than useless to the person who measured it.
    """
    spec = CATALOGUE_BY_KEY.get(key)
    if spec is None:
        return None
    window = spec.typical_range.get(family)
    if window is None:
        return None
    low, high = window
    if low <= value <= high:
        return None
    return {
        "code": "VALUE_OUTSIDE_TYPICAL_RANGE",
        "property_key": key,
        "value": value,
        "material_family": family,
        "typical_min": low,
        "typical_max": high,
        "severity": "warning",
        "message": (
            f"{value:g} is outside the {low:g}–{high:g} range typical for {family} grades. "
            "Recorded as entered — confirm the unit and the test condition."
        ),
    }
