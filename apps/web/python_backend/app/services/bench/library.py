"""Phase 12 — a reference library of real engineering materials.

WHY THIS EXISTS. The platform previously shipped with four fictional materials called things like
"Demo Engineering Polymer P-100". A materials engineer opening that sees a toy and closes the tab.
More seriously, a replacement study needs a *population* to search: with four synthetic polymers
there is nothing to find, so every lab correctly reported that it had nothing to say, which read as
the labs being broken.

WHAT THESE NUMBERS ARE. Handbook-typical figures: the values you would expect across commercial
grades of that material, of the kind found in a materials selection reference or a representative
supplier datasheet. They are useful for screening and for teaching the tool. They are not
measurements of any specific supplier's grade.

HOW THEY ARE RECORDED. Every observation created from this library carries:

    evidence_type   = "literature"
    source_quality  = "handbook_typical"
    confidence      = 0.55
    status          = "reported"      (never "verified")
    source_reference = unpinned starter compilation (screening only)

The intake service refuses to raise that grade, the decision engine sees a low-confidence reported
value like any other, and the dossier exporter can therefore never present one of these as
qualification evidence. A number good enough to shortlist on is not a number good enough to
certify on, and the system is required to know the difference.

POLYMER VALUES ARE DRY-AS-MOULDED unless the entry says otherwise, matching datasheet convention.
For polyamides in particular the conditioned values are materially lower; the `caveats` field says
so on every affected entry rather than leaving the user to discover it in the field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LibraryMaterial:
    key: str
    display_name: str
    family: str
    description: str
    properties: dict[str, tuple[float | bool, str | None]]
    components: tuple[tuple[str, str, float | None, str | None], ...] = ()
    identifiers: tuple[tuple[str, str], ...] = ()
    process_state: str | None = None
    caveats: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "material_family": self.family,
            "description": self.description,
            "properties": {k: {"value": v[0], "unit": v[1]} for k, v in self.properties.items()},
            "components": [
                {"component_name": c[0], "component_role": c[1], "amount_value": c[2], "amount_unit": c[3]}
                for c in self.components
            ],
            "identifiers": [{"namespace": n, "value": v} for n, v in self.identifiers],
            "process_state": self.process_state,
            "caveats": list(self.caveats),
            "tags": list(self.tags),
            "evidence_posture": "screening_only",
            "qualification_eligible": False,
            "source_traceability": "unpinned_starter_compilation",
            "source_note": (
                "Handbook-typical starter value for screening. The exact publication/datasheet is not "
                "pinned in this starter library; replace or enrich it with a cited external snapshot, "
                "supplier source, or measurement before qualification."
            ),
        }


_DRY_AS_MOULDED = "Datasheet convention: values are dry-as-moulded. Conditioned properties differ."
_PA_MOISTURE = (
    "Polyamide: at 50% RH equilibrium, modulus typically falls 40–50% and dimensions grow. "
    "Never size an assembly on the dry values."
)
_GF_ANISOTROPY = (
    "Glass-filled and injection moulded: values are flow-direction. Cross-flow and weld-line "
    "strength are substantially lower."
)


STARTER_LIBRARY: tuple[LibraryMaterial, ...] = (
    # ---------------------------------------------------------------------------------------
    # Engineering thermoplastics
    # ---------------------------------------------------------------------------------------
    LibraryMaterial(
        key="pa66-gf30", display_name="PA66-GF30 (polyamide 66, 30% glass fibre)", family="polymer",
        description="Workhorse under-hood and structural engineering thermoplastic. High strength and stiffness, moisture sensitive.",
        identifiers=(("cas", "32131-17-2"), ("iso1043", "PA66-GF30")),
        components=(("Polyamide 66", "matrix", 70.0, "%"), ("E-glass fibre", "reinforcement", 30.0, "%")),
        process_state="Injection moulded, dry as moulded",
        properties={
            "density": (1360.0, "kg/m^3"), "tensile_strength": (180.0, "MPa"), "tensile_modulus": (9500.0, "MPa"),
            "elongation_at_break": (3.5, "%"), "izod_impact_notched": (100.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (250.0, "degC"), "continuous_service_temperature": (120.0, "degC"),
            "melting_temperature": (262.0, "degC"), "thermal_conductivity": (0.30, "W/(m*K)"),
            "coefficient_thermal_expansion": (30.0, "1e-6/K"), "water_absorption_24h": (1.1, "%"),
            "moisture_absorption_equilibrium": (2.5, "%"), "mould_shrinkage": (0.4, "%"),
            "cost_per_mass": (4.20, "USD/kg"), "carbon_footprint": (8.5, "kgCO2e/kg"),
            "comparative_tracking_index": (600.0, "V"), "reach_svhc_present": (False, None),
            "rohs_compliant": (True, None), "pfas_present": (False, None),
        },
        caveats=(_PA_MOISTURE, _GF_ANISOTROPY),
        tags=("automotive", "structural", "under-hood"),
    ),
    LibraryMaterial(
        key="pa6-gf30", display_name="PA6-GF30 (polyamide 6, 30% glass fibre)", family="polymer",
        description="Lower-cost polyamide alternative to PA66. Easier processing, lower melting point, higher moisture uptake.",
        identifiers=(("cas", "25038-54-4"), ("iso1043", "PA6-GF30")),
        components=(("Polyamide 6", "matrix", 70.0, "%"), ("E-glass fibre", "reinforcement", 30.0, "%")),
        process_state="Injection moulded, dry as moulded",
        properties={
            "density": (1360.0, "kg/m^3"), "tensile_strength": (175.0, "MPa"), "tensile_modulus": (9000.0, "MPa"),
            "elongation_at_break": (3.5, "%"), "izod_impact_notched": (95.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (210.0, "degC"), "continuous_service_temperature": (105.0, "degC"),
            "melting_temperature": (220.0, "degC"), "thermal_conductivity": (0.29, "W/(m*K)"),
            "coefficient_thermal_expansion": (30.0, "1e-6/K"), "water_absorption_24h": (1.9, "%"),
            "moisture_absorption_equilibrium": (3.2, "%"), "mould_shrinkage": (0.4, "%"),
            "cost_per_mass": (3.60, "USD/kg"), "carbon_footprint": (7.8, "kgCO2e/kg"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(_PA_MOISTURE, _GF_ANISOTROPY),
        tags=("automotive", "structural", "cost-down"),
    ),
    LibraryMaterial(
        key="pbt-gf30", display_name="PBT-GF30 (polybutylene terephthalate, 30% glass)", family="polymer",
        description="Dimensionally stable polyester. The standard answer where polyamide moisture uptake is unacceptable.",
        identifiers=(("cas", "24968-12-5"), ("iso1043", "PBT-GF30")),
        components=(("Polybutylene terephthalate", "matrix", 70.0, "%"), ("E-glass fibre", "reinforcement", 30.0, "%")),
        process_state="Injection moulded",
        properties={
            "density": (1530.0, "kg/m^3"), "tensile_strength": (135.0, "MPa"), "tensile_modulus": (10000.0, "MPa"),
            "elongation_at_break": (2.5, "%"), "izod_impact_notched": (80.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (210.0, "degC"), "continuous_service_temperature": (120.0, "degC"),
            "melting_temperature": (225.0, "degC"), "thermal_conductivity": (0.29, "W/(m*K)"),
            "coefficient_thermal_expansion": (25.0, "1e-6/K"), "water_absorption_24h": (0.10, "%"),
            "mould_shrinkage": (0.5, "%"), "cost_per_mass": (4.00, "USD/kg"),
            "carbon_footprint": (6.5, "kgCO2e/kg"), "comparative_tracking_index": (600.0, "V"),
            "dielectric_strength": (25.0, "kV/mm"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(_GF_ANISOTROPY, "Susceptible to hydrolysis in hot, wet service. Check the specific grade's hydrolysis package."),
        tags=("electrical", "automotive", "dimensional-stability"),
    ),
    LibraryMaterial(
        key="ppa-gf33", display_name="PPA-GF33 (polyphthalamide, 33% glass fibre)", family="polymer",
        description="High-temperature semi-aromatic polyamide. Common step up from PA66 when the thermal envelope is exceeded.",
        identifiers=(("iso1043", "PPA-GF33"),),
        components=(("Polyphthalamide", "matrix", 67.0, "%"), ("E-glass fibre", "reinforcement", 33.0, "%")),
        process_state="Injection moulded, dry as moulded",
        properties={
            "density": (1450.0, "kg/m^3"), "tensile_strength": (205.0, "MPa"), "tensile_modulus": (11500.0, "MPa"),
            "elongation_at_break": (2.5, "%"), "izod_impact_notched": (85.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (285.0, "degC"), "continuous_service_temperature": (150.0, "degC"),
            "peak_service_temperature": (220.0, "degC"), "melting_temperature": (310.0, "degC"),
            "coefficient_thermal_expansion": (25.0, "1e-6/K"), "water_absorption_24h": (0.40, "%"),
            "cost_per_mass": (11.50, "USD/kg"), "carbon_footprint": (9.5, "kgCO2e/kg"),
            "comparative_tracking_index": (600.0, "V"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(_GF_ANISOTROPY, "Requires a higher melt temperature than PA66 — confirm the barrel and hot runner can reach it."),
        tags=("automotive", "high-temperature", "under-hood"),
    ),
    LibraryMaterial(
        key="pps-gf40", display_name="PPS-GF40 (polyphenylene sulfide, 40% glass)", family="polymer",
        description="High-temperature, inherently flame-retardant and chemically resistant. Brittle relative to polyamides.",
        identifiers=(("cas", "25212-74-6"), ("iso1043", "PPS-GF40")),
        components=(("Polyphenylene sulfide", "matrix", 60.0, "%"), ("E-glass fibre", "reinforcement", 40.0, "%")),
        process_state="Injection moulded",
        properties={
            "density": (1650.0, "kg/m^3"), "tensile_strength": (190.0, "MPa"), "tensile_modulus": (14000.0, "MPa"),
            "elongation_at_break": (1.9, "%"), "izod_impact_notched": (75.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (265.0, "degC"), "continuous_service_temperature": (200.0, "degC"),
            "melting_temperature": (280.0, "degC"), "thermal_conductivity": (0.30, "W/(m*K)"),
            "coefficient_thermal_expansion": (20.0, "1e-6/K"), "water_absorption_24h": (0.02, "%"),
            "limiting_oxygen_index": (47.0, "%"), "cost_per_mass": (12.50, "USD/kg"),
            "carbon_footprint": (11.0, "kgCO2e/kg"), "chemical_resistance_rating": (4.5, "1"),
            "flammability_ul94_v0": (True, None), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(_GF_ANISOTROPY, "Low elongation. Snap-fits and press-fits that work in polyamide will crack in PPS."),
        tags=("high-temperature", "chemical", "flame-retardant"),
    ),
    LibraryMaterial(
        key="peek-unfilled", display_name="PEEK (polyetheretherketone, unfilled)", family="polymer",
        description="Benchmark high-performance thermoplastic. Excellent across temperature, chemicals and fatigue; priced accordingly.",
        identifiers=(("cas", "31694-16-3"), ("iso1043", "PEEK")),
        components=(("Polyetheretherketone", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (1300.0, "kg/m^3"), "tensile_strength": (97.0, "MPa"), "tensile_modulus": (3700.0, "MPa"),
            "elongation_at_break": (45.0, "%"), "izod_impact_notched": (55.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (152.0, "degC"), "continuous_service_temperature": (250.0, "degC"),
            "glass_transition_temperature": (143.0, "degC"), "melting_temperature": (343.0, "degC"),
            "thermal_conductivity": (0.25, "W/(m*K)"), "coefficient_thermal_expansion": (47.0, "1e-6/K"),
            "water_absorption_24h": (0.14, "%"), "limiting_oxygen_index": (35.0, "%"),
            "chemical_resistance_rating": (5.0, "1"), "cost_per_mass": (90.0, "USD/kg"),
            "carbon_footprint": (30.0, "kgCO2e/kg"), "flammability_ul94_v0": (True, None),
            "biocompatible_usp_vi": (True, None), "reach_svhc_present": (False, None), "pfas_present": (False, None),
        },
        caveats=("Cost usually decides against PEEK before performance does. Compare on cost per part, including cycle time.",),
        tags=("high-performance", "medical", "chemical", "aerospace"),
    ),
    LibraryMaterial(
        key="pei-unfilled", display_name="PEI (polyetherimide, unfilled)", family="polymer",
        description="Amorphous high-temperature polymer with inherent flame retardance and transparency. Notch sensitive.",
        identifiers=(("cas", "61128-46-9"), ("iso1043", "PEI")),
        components=(("Polyetherimide", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (1270.0, "kg/m^3"), "tensile_strength": (105.0, "MPa"), "tensile_modulus": (3200.0, "MPa"),
            "elongation_at_break": (60.0, "%"), "izod_impact_notched": (50.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (200.0, "degC"), "continuous_service_temperature": (170.0, "degC"),
            "glass_transition_temperature": (217.0, "degC"), "thermal_conductivity": (0.22, "W/(m*K)"),
            "coefficient_thermal_expansion": (55.0, "1e-6/K"), "water_absorption_24h": (0.25, "%"),
            "limiting_oxygen_index": (47.0, "%"), "dielectric_strength": (33.0, "kV/mm"),
            "dielectric_constant": (3.15, "1"), "cost_per_mass": (25.0, "USD/kg"),
            "carbon_footprint": (14.0, "kgCO2e/kg"), "flammability_ul94_v0": (True, None),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Notch sensitive and prone to stress cracking with some solvents and cleaning agents.",),
        tags=("high-temperature", "electrical", "flame-retardant", "aerospace"),
    ),
    LibraryMaterial(
        key="pc-unfilled", display_name="PC (polycarbonate, unfilled)", family="polymer",
        description="Transparent, exceptionally tough amorphous polymer. The default for impact-critical clear enclosures.",
        identifiers=(("cas", "25037-45-0"), ("iso1043", "PC")),
        components=(("Bisphenol-A polycarbonate", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (1200.0, "kg/m^3"), "tensile_strength": (65.0, "MPa"), "tensile_modulus": (2350.0, "MPa"),
            "elongation_at_break": (110.0, "%"), "izod_impact_notched": (700.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (128.0, "degC"), "continuous_service_temperature": (115.0, "degC"),
            "glass_transition_temperature": (147.0, "degC"), "thermal_conductivity": (0.20, "W/(m*K)"),
            "coefficient_thermal_expansion": (68.0, "1e-6/K"), "water_absorption_24h": (0.15, "%"),
            "dielectric_strength": (17.0, "kV/mm"), "comparative_tracking_index": (250.0, "V"),
            "mould_shrinkage": (0.6, "%"), "cost_per_mass": (3.20, "USD/kg"),
            "carbon_footprint": (6.0, "kgCO2e/kg"), "rohs_compliant": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=(
            "Environmental stress cracking with alcohols, alkalis and many disinfectants — a recurring failure in medical enclosures.",
            "CTI of 250 V rules it out of high-voltage tracking applications without modification.",
        ),
        tags=("transparent", "impact", "consumer", "electrical"),
    ),
    LibraryMaterial(
        key="pc-abs", display_name="PC/ABS blend", family="polymer",
        description="Balances polycarbonate toughness and heat with ABS processability and cost. Common automotive interior and enclosure material.",
        identifiers=(("iso1043", "PC+ABS"),),
        components=(("Polycarbonate", "matrix", 60.0, "%"), ("ABS", "matrix", 40.0, "%")),
        process_state="Injection moulded",
        properties={
            "density": (1130.0, "kg/m^3"), "tensile_strength": (55.0, "MPa"), "tensile_modulus": (2400.0, "MPa"),
            "elongation_at_break": (80.0, "%"), "izod_impact_notched": (500.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (105.0, "degC"), "continuous_service_temperature": (100.0, "degC"),
            "coefficient_thermal_expansion": (75.0, "1e-6/K"), "water_absorption_24h": (0.20, "%"),
            "mould_shrinkage": (0.6, "%"), "cost_per_mass": (3.00, "USD/kg"),
            "carbon_footprint": (5.2, "kgCO2e/kg"), "rohs_compliant": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=("Blend ratio varies widely between grades and moves every property. Treat the specific grade, not the blend name, as the material.",),
        tags=("consumer", "automotive-interior", "enclosure"),
    ),
    LibraryMaterial(
        key="abs", display_name="ABS (acrylonitrile butadiene styrene)", family="polymer",
        description="Low-cost, easily moulded, good surface finish. The default consumer enclosure polymer.",
        identifiers=(("cas", "9003-56-9"), ("iso1043", "ABS")),
        components=(("Acrylonitrile butadiene styrene", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (1050.0, "kg/m^3"), "tensile_strength": (45.0, "MPa"), "tensile_modulus": (2300.0, "MPa"),
            "elongation_at_break": (25.0, "%"), "izod_impact_notched": (200.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (88.0, "degC"), "continuous_service_temperature": (80.0, "degC"),
            "glass_transition_temperature": (105.0, "degC"), "thermal_conductivity": (0.17, "W/(m*K)"),
            "coefficient_thermal_expansion": (90.0, "1e-6/K"), "water_absorption_24h": (0.30, "%"),
            "limiting_oxygen_index": (18.5, "%"), "mould_shrinkage": (0.5, "%"),
            "cost_per_mass": (2.20, "USD/kg"), "carbon_footprint": (3.8, "kgCO2e/kg"),
            "recyclability_rating": (3.0, "1"), "rohs_compliant": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=("Poor UV stability unpigmented. Yellows and embrittles outdoors without a stabiliser package.",),
        tags=("consumer", "enclosure", "low-cost"),
    ),
    LibraryMaterial(
        key="pom-copolymer", display_name="POM copolymer (acetal)", family="polymer",
        description="Low friction, high fatigue resistance, excellent dimensional stability. The standard gear and bearing polymer.",
        identifiers=(("cas", "9002-81-7"), ("iso1043", "POM")),
        components=(("Polyoxymethylene copolymer", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (1410.0, "kg/m^3"), "tensile_strength": (62.0, "MPa"), "tensile_modulus": (2700.0, "MPa"),
            "elongation_at_break": (30.0, "%"), "izod_impact_notched": (65.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (95.0, "degC"), "continuous_service_temperature": (100.0, "degC"),
            "melting_temperature": (166.0, "degC"), "thermal_conductivity": (0.31, "W/(m*K)"),
            "coefficient_thermal_expansion": (110.0, "1e-6/K"), "water_absorption_24h": (0.20, "%"),
            "fatigue_strength_1e7": (28.0, "MPa"), "mould_shrinkage": (2.0, "%"),
            "cost_per_mass": (2.60, "USD/kg"), "carbon_footprint": (3.5, "kgCO2e/kg"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "High mould shrinkage at 2%. Substituting into or out of POM almost always means tooling changes.",
            "Degrades releasing formaldehyde if overheated in the barrel. Purge discipline matters.",
        ),
        tags=("bearing", "gear", "fatigue"),
    ),
    LibraryMaterial(
        key="pp-homopolymer", display_name="PP homopolymer", family="polymer",
        description="The commodity baseline. Cheap, chemically resistant, low density, modest mechanical and thermal performance.",
        identifiers=(("cas", "9003-07-0"), ("iso1043", "PP")),
        components=(("Polypropylene", "matrix", 100.0, "%"),),
        process_state="Injection moulded",
        properties={
            "density": (905.0, "kg/m^3"), "tensile_strength": (33.0, "MPa"), "tensile_modulus": (1500.0, "MPa"),
            "elongation_at_break": (250.0, "%"), "izod_impact_notched": (25.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (55.0, "degC"), "continuous_service_temperature": (100.0, "degC"),
            "melting_temperature": (165.0, "degC"), "thermal_conductivity": (0.22, "W/(m*K)"),
            "coefficient_thermal_expansion": (100.0, "1e-6/K"), "water_absorption_24h": (0.02, "%"),
            "limiting_oxygen_index": (17.5, "%"), "melt_flow_index": (12.0, "g/10min"),
            "mould_shrinkage": (1.5, "%"), "cost_per_mass": (1.35, "USD/kg"),
            "carbon_footprint": (1.95, "kgCO2e/kg"), "recyclability_rating": (4.0, "1"),
            "chemical_resistance_rating": (4.0, "1"), "food_contact_compliant": (True, None),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Poor notched impact below 0 °C. Impact-copolymer grades exist specifically to fix this.",),
        tags=("commodity", "packaging", "chemical", "low-cost"),
    ),
    LibraryMaterial(
        key="pp-td20", display_name="PP-TD20 (polypropylene, 20% talc)", family="polymer",
        description="Talc-filled polypropylene. Buys stiffness and heat resistance over unfilled PP at a small cost and density penalty.",
        identifiers=(("iso1043", "PP-TD20"),),
        components=(("Polypropylene", "matrix", 80.0, "%"), ("Talc", "filler", 20.0, "%")),
        process_state="Injection moulded",
        properties={
            "density": (1050.0, "kg/m^3"), "tensile_strength": (28.0, "MPa"), "tensile_modulus": (2600.0, "MPa"),
            "elongation_at_break": (20.0, "%"), "izod_impact_notched": (30.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (75.0, "degC"), "continuous_service_temperature": (105.0, "degC"),
            "melting_temperature": (165.0, "degC"), "coefficient_thermal_expansion": (70.0, "1e-6/K"),
            "water_absorption_24h": (0.05, "%"), "mould_shrinkage": (1.0, "%"),
            "cost_per_mass": (1.55, "USD/kg"), "carbon_footprint": (1.85, "kgCO2e/kg"),
            "recyclability_rating": (3.5, "1"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Talc reduces elongation and notched impact. Confirm cold-temperature impact if the part sees outdoor service.",),
        tags=("automotive-interior", "commodity", "stiffness"),
    ),
    LibraryMaterial(
        key="hdpe", display_name="HDPE (high density polyethylene)", family="polymer",
        description="Tough, chemically inert commodity polyolefin. Dominant in containers, pipe and industrial tanks.",
        identifiers=(("cas", "9002-88-4"), ("iso1043", "PE-HD")),
        components=(("High density polyethylene", "matrix", 100.0, "%"),),
        properties={
            "density": (955.0, "kg/m^3"), "tensile_strength": (28.0, "MPa"), "tensile_modulus": (1100.0, "MPa"),
            "elongation_at_break": (600.0, "%"), "izod_impact_notched": (130.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (45.0, "degC"), "continuous_service_temperature": (80.0, "degC"),
            "melting_temperature": (132.0, "degC"), "thermal_conductivity": (0.45, "W/(m*K)"),
            "water_absorption_24h": (0.01, "%"), "water_vapour_transmission_rate": (0.4, "g/(m^2*d)"),
            "melt_flow_index": (8.0, "g/10min"), "cost_per_mass": (1.30, "USD/kg"),
            "carbon_footprint": (1.90, "kgCO2e/kg"), "recyclability_rating": (5.0, "1"),
            "chemical_resistance_rating": (4.5, "1"), "food_contact_compliant": (True, None),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Environmental stress cracking under combined stress and surfactant exposure is the classic HDPE field failure.",),
        tags=("commodity", "packaging", "chemical", "recyclable"),
    ),
    LibraryMaterial(
        key="pet-bottle", display_name="PET (bottle/packaging grade)", family="polymer",
        description="Clear, stiff polyester with good gas barrier. The dominant beverage packaging polymer with a mature recycling stream.",
        identifiers=(("cas", "25038-59-9"), ("iso1043", "PET")),
        components=(("Polyethylene terephthalate", "matrix", 100.0, "%"),),
        properties={
            "density": (1380.0, "kg/m^3"), "tensile_strength": (60.0, "MPa"), "tensile_modulus": (2900.0, "MPa"),
            "elongation_at_break": (70.0, "%"), "heat_deflection_temperature_1_8mpa": (70.0, "degC"),
            "continuous_service_temperature": (100.0, "degC"), "glass_transition_temperature": (78.0, "degC"),
            "melting_temperature": (250.0, "degC"), "water_absorption_24h": (0.15, "%"),
            "oxygen_transmission_rate": (40.0, "cm^3/(m^2*d*bar)"), "water_vapour_transmission_rate": (1.5, "g/(m^2*d)"),
            "cost_per_mass": (1.45, "USD/kg"), "carbon_footprint": (2.40, "kgCO2e/kg"),
            "recycled_content": (30.0, "%"), "recyclability_rating": (5.0, "1"),
            "food_contact_compliant": (True, None), "reach_svhc_present": (False, None), "pfas_present": (False, None),
        },
        caveats=("Hydrolyses if processed wet. Drying to below 50 ppm moisture is not optional.",),
        tags=("packaging", "barrier", "recyclable", "food-contact"),
    ),
    LibraryMaterial(
        key="evoh-32", display_name="EVOH (32 mol% ethylene)", family="polymer",
        description="Outstanding oxygen barrier used as a thin layer in multilayer packaging. Its own barrier collapses when wet.",
        identifiers=(("cas", "25067-34-9"), ("iso1043", "EVOH")),
        components=(("Ethylene vinyl alcohol copolymer", "matrix", 100.0, "%"),),
        properties={
            "density": (1190.0, "kg/m^3"), "tensile_strength": (60.0, "MPa"), "tensile_modulus": (2500.0, "MPa"),
            "elongation_at_break": (230.0, "%"), "melting_temperature": (183.0, "degC"),
            "continuous_service_temperature": (80.0, "degC"),
            "oxygen_transmission_rate": (0.4, "cm^3/(m^2*d*bar)"), "water_vapour_transmission_rate": (25.0, "g/(m^2*d)"),
            "cost_per_mass": (8.50, "USD/kg"), "carbon_footprint": (4.2, "kgCO2e/kg"),
            "recyclability_rating": (2.0, "1"), "food_contact_compliant": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=(
            "OTR is quoted dry. At high humidity the barrier degrades by an order of magnitude, which is why it is always buried between polyolefin layers.",
            "Its presence is what makes a barrier laminate hard to recycle. Barrier and circularity pull against each other here.",
        ),
        tags=("packaging", "barrier"),
    ),
    LibraryMaterial(
        key="pla", display_name="PLA (polylactic acid)", family="polymer",
        description="Bio-based, industrially compostable polyester. Stiff and clear, with a low thermal ceiling.",
        identifiers=(("cas", "26100-51-6"), ("iso1043", "PLA")),
        components=(("Polylactic acid", "matrix", 100.0, "%"),),
        properties={
            "density": (1240.0, "kg/m^3"), "tensile_strength": (55.0, "MPa"), "tensile_modulus": (3300.0, "MPa"),
            "elongation_at_break": (5.0, "%"), "izod_impact_notched": (20.0, "J/m"),
            "heat_deflection_temperature_1_8mpa": (55.0, "degC"), "continuous_service_temperature": (50.0, "degC"),
            "glass_transition_temperature": (60.0, "degC"), "melting_temperature": (155.0, "degC"),
            "water_absorption_24h": (0.5, "%"), "cost_per_mass": (2.60, "USD/kg"),
            "carbon_footprint": (1.70, "kgCO2e/kg"), "biobased_content": (100.0, "%"),
            "food_contact_compliant": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=(
            "A 50 °C service ceiling. Fails in a hot car, a dishwasher, or a summer warehouse.",
            "Industrially compostable is not home compostable and is not the same as recyclable. It contaminates the PET stream.",
        ),
        tags=("bio-based", "packaging", "sustainability"),
    ),
    LibraryMaterial(
        key="ptfe", display_name="PTFE (polytetrafluoroethylene)", family="polymer",
        description="The chemical and thermal benchmark, and the lowest-friction bulk polymer. Squarely inside the PFAS restriction scope.",
        identifiers=(("cas", "9002-84-0"), ("iso1043", "PTFE")),
        components=(("Polytetrafluoroethylene", "matrix", 100.0, "%"),),
        properties={
            "density": (2170.0, "kg/m^3"), "tensile_strength": (27.0, "MPa"), "tensile_modulus": (500.0, "MPa"),
            "elongation_at_break": (350.0, "%"), "continuous_service_temperature": (260.0, "degC"),
            "melting_temperature": (327.0, "degC"), "thermal_conductivity": (0.25, "W/(m*K)"),
            "coefficient_thermal_expansion": (135.0, "1e-6/K"), "water_absorption_24h": (0.01, "%"),
            "limiting_oxygen_index": (95.0, "%"), "dielectric_constant": (2.1, "1"),
            "dissipation_factor": (0.0002, "1"), "chemical_resistance_rating": (5.0, "1"),
            "cost_per_mass": (22.0, "USD/kg"), "carbon_footprint": (25.0, "kgCO2e/kg"),
            "pfas_present": (True, None), "flammability_ul94_v0": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=(
            "PFAS present. Included as a realistic incumbent for restriction-driven replacement studies, not as a recommendation.",
            "Creeps badly under sustained load. Never size a sealing joint on short-term modulus.",
        ),
        tags=("fluoropolymer", "chemical", "pfas-incumbent", "low-friction"),
    ),
    LibraryMaterial(
        key="pvdf", display_name="PVDF (polyvinylidene fluoride)", family="polymer",
        description="Melt-processable fluoropolymer with strong chemical and UV resistance. Also in PFAS restriction scope.",
        identifiers=(("cas", "24937-79-9"), ("iso1043", "PVDF")),
        components=(("Polyvinylidene fluoride", "matrix", 100.0, "%"),),
        properties={
            "density": (1780.0, "kg/m^3"), "tensile_strength": (50.0, "MPa"), "tensile_modulus": (2100.0, "MPa"),
            "elongation_at_break": (50.0, "%"), "continuous_service_temperature": (150.0, "degC"),
            "melting_temperature": (172.0, "degC"), "thermal_conductivity": (0.19, "W/(m*K)"),
            "water_absorption_24h": (0.04, "%"), "limiting_oxygen_index": (44.0, "%"),
            "chemical_resistance_rating": (5.0, "1"), "uv_stability_rating": (5.0, "1"),
            "cost_per_mass": (20.0, "USD/kg"), "carbon_footprint": (22.0, "kgCO2e/kg"),
            "pfas_present": (True, None), "flammability_ul94_v0": (True, None), "reach_svhc_present": (False, None),
        },
        caveats=("PFAS present. A common incumbent in chemical process and architectural coating replacement studies.",),
        tags=("fluoropolymer", "chemical", "pfas-incumbent"),
    ),
    LibraryMaterial(
        key="tpu-55d", display_name="TPU (thermoplastic polyurethane, Shore 55D)", family="polymer",
        description="Tough, abrasion-resistant elastomer-plastic hybrid. Common in seals, cable jacketing and protective housings.",
        identifiers=(("iso1043", "TPU"),),
        components=(("Thermoplastic polyurethane", "matrix", 100.0, "%"),),
        properties={
            "density": (1200.0, "kg/m^3"), "tensile_strength": (45.0, "MPa"), "elongation_at_break": (450.0, "%"),
            "hardness_shore_d": (55.0, "1"), "continuous_service_temperature": (80.0, "degC"),
            "water_absorption_24h": (0.8, "%"), "cost_per_mass": (5.50, "USD/kg"),
            "carbon_footprint": (5.5, "kgCO2e/kg"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Polyester-based TPU hydrolyses in hot, wet service; polyether-based does not. The grade family matters more than the Shore number.",),
        tags=("elastomer", "abrasion", "sealing"),
    ),

    # ---------------------------------------------------------------------------------------
    # Metals
    # ---------------------------------------------------------------------------------------
    LibraryMaterial(
        key="al-6061-t6", display_name="Aluminium 6061-T6", family="alloy",
        description="General-purpose structural aluminium. Weldable, machinable, corrosion resistant, widely available.",
        identifiers=(("uns", "A96061"), ("en", "EN AW-6061")),
        components=(("Aluminium", "matrix", 97.9, "%"), ("Magnesium", "alloying", 1.0, "%"),
                    ("Silicon", "alloying", 0.6, "%"), ("Copper", "alloying", 0.28, "%")),
        process_state="T6 — solution heat treated and artificially aged",
        properties={
            "density": (2700.0, "kg/m^3"), "tensile_strength": (310.0, "MPa"), "yield_strength": (276.0, "MPa"),
            "tensile_modulus": (68900.0, "MPa"), "elongation_at_break": (12.0, "%"),
            "fatigue_strength_1e7": (96.5, "MPa"), "fracture_toughness_k1c": (29.0, "MPa*m^0.5"),
            "hardness_vickers": (107.0, "1"), "thermal_conductivity": (167.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (23.6, "1e-6/K"), "continuous_service_temperature": (150.0, "degC"),
            "melting_temperature": (582.0, "degC"), "specific_heat_capacity": (896.0, "J/(kg*K)"),
            "salt_spray_resistance": (500.0, "h"), "cost_per_mass": (3.00, "USD/kg"),
            "carbon_footprint": (8.60, "kgCO2e/kg"), "recycled_content": (30.0, "%"),
            "recyclability_rating": (5.0, "1"), "supplier_count": (25.0, "1"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "Loses significant strength above about 150 °C. The T6 temper over-ages in prolonged hot service.",
            "Primary aluminium footprint is around 8.6 kgCO2e/kg; recycled secondary is closer to 0.5–1.5. State which.",
        ),
        tags=("structural", "lightweight", "machinable"),
    ),
    LibraryMaterial(
        key="al-7075-t6", display_name="Aluminium 7075-T6", family="alloy",
        description="High-strength aerospace aluminium. Strength approaching mild steel at a third of the density; poor weldability and corrosion resistance.",
        identifiers=(("uns", "A97075"), ("en", "EN AW-7075")),
        components=(("Aluminium", "matrix", 89.5, "%"), ("Zinc", "alloying", 5.6, "%"),
                    ("Magnesium", "alloying", 2.5, "%"), ("Copper", "alloying", 1.6, "%")),
        process_state="T6 — solution heat treated and artificially aged",
        properties={
            "density": (2810.0, "kg/m^3"), "tensile_strength": (572.0, "MPa"), "yield_strength": (503.0, "MPa"),
            "tensile_modulus": (71700.0, "MPa"), "elongation_at_break": (11.0, "%"),
            "fatigue_strength_1e7": (159.0, "MPa"), "fracture_toughness_k1c": (23.0, "MPa*m^0.5"),
            "hardness_vickers": (175.0, "1"), "thermal_conductivity": (130.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (23.6, "1e-6/K"), "continuous_service_temperature": (120.0, "degC"),
            "cost_per_mass": (5.50, "USD/kg"), "carbon_footprint": (9.20, "kgCO2e/kg"),
            "supplier_count": (12.0, "1"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "Susceptible to stress corrosion cracking in the T6 temper. T73 trades strength for resistance.",
            "Not readily weldable by conventional fusion processes.",
        ),
        tags=("aerospace", "high-strength", "lightweight"),
    ),
    LibraryMaterial(
        key="al-a380", display_name="Aluminium A380 (die casting alloy)", family="alloy",
        description="The dominant aluminium die-casting alloy. Excellent castability and thermal conductivity, limited ductility.",
        identifiers=(("uns", "A03800"), ("en", "EN AC-46000")),
        components=(("Aluminium", "matrix", 85.0, "%"), ("Silicon", "alloying", 9.0, "%"),
                    ("Copper", "alloying", 3.5, "%")),
        process_state="As die cast",
        properties={
            "density": (2740.0, "kg/m^3"), "tensile_strength": (324.0, "MPa"), "yield_strength": (159.0, "MPa"),
            "tensile_modulus": (71000.0, "MPa"), "elongation_at_break": (3.5, "%"),
            "hardness_vickers": (80.0, "1"), "thermal_conductivity": (96.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (21.0, "1e-6/K"), "continuous_service_temperature": (150.0, "degC"),
            "cost_per_mass": (2.60, "USD/kg"), "carbon_footprint": (5.00, "kgCO2e/kg"),
            "recycled_content": (85.0, "%"), "supplier_count": (30.0, "1"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Die-cast porosity limits fatigue performance and makes the part unsuitable for pressure-tight duty without impregnation.",),
        tags=("die-cast", "housing", "thermal", "high-recycled"),
    ),
    LibraryMaterial(
        key="mg-az91d", display_name="Magnesium AZ91D", family="alloy",
        description="The standard magnesium die-casting alloy. The lightest structural metal in common use.",
        identifiers=(("uns", "M11916"),),
        components=(("Magnesium", "matrix", 90.0, "%"), ("Aluminium", "alloying", 9.0, "%"),
                    ("Zinc", "alloying", 0.7, "%")),
        process_state="As die cast",
        properties={
            "density": (1810.0, "kg/m^3"), "tensile_strength": (230.0, "MPa"), "yield_strength": (160.0, "MPa"),
            "tensile_modulus": (45000.0, "MPa"), "elongation_at_break": (3.0, "%"),
            "thermal_conductivity": (72.0, "W/(m*K)"), "coefficient_thermal_expansion": (26.0, "1e-6/K"),
            "continuous_service_temperature": (120.0, "degC"), "hardness_vickers": (70.0, "1"),
            "cost_per_mass": (3.50, "USD/kg"), "carbon_footprint": (18.0, "kgCO2e/kg"),
            "supplier_count": (8.0, "1"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "Galvanic corrosion against steel and aluminium fasteners is severe. Isolation is mandatory, not optional.",
            "High primary carbon footprint, dominated by the reduction process and cover gas.",
        ),
        tags=("lightweight", "die-cast", "automotive"),
    ),
    LibraryMaterial(
        key="ti-6al-4v", display_name="Titanium Ti-6Al-4V (Grade 5)", family="alloy",
        description="The workhorse titanium alloy. Exceptional specific strength, fatigue and corrosion resistance; expensive and hard to machine.",
        identifiers=(("uns", "R56400"), ("astm", "ASTM B265 Gr5")),
        components=(("Titanium", "matrix", 90.0, "%"), ("Aluminium", "alloying", 6.0, "%"),
                    ("Vanadium", "alloying", 4.0, "%")),
        process_state="Annealed",
        properties={
            "density": (4430.0, "kg/m^3"), "tensile_strength": (950.0, "MPa"), "yield_strength": (880.0, "MPa"),
            "tensile_modulus": (113800.0, "MPa"), "elongation_at_break": (14.0, "%"),
            "fatigue_strength_1e7": (510.0, "MPa"), "fracture_toughness_k1c": (75.0, "MPa*m^0.5"),
            "hardness_vickers": (349.0, "1"), "thermal_conductivity": (6.70, "W/(m*K)"),
            "coefficient_thermal_expansion": (8.60, "1e-6/K"), "continuous_service_temperature": (400.0, "degC"),
            "melting_temperature": (1660.0, "degC"), "salt_spray_resistance": (3000.0, "h"),
            "chemical_resistance_rating": (5.0, "1"), "cost_per_mass": (30.0, "USD/kg"),
            "carbon_footprint": (35.0, "kgCO2e/kg"), "supplier_count": (6.0, "1"),
            "biocompatible_usp_vi": (True, None), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "Machining cost frequently exceeds material cost. Compare finished-part cost, not stock price.",
            "Thermal conductivity is very low for a metal, which is why it burns tooling and why it is a poor heat path.",
        ),
        tags=("aerospace", "medical", "high-performance", "corrosion"),
    ),
    LibraryMaterial(
        key="ss-316l", display_name="Stainless steel 316L", family="alloy",
        description="Molybdenum-bearing austenitic stainless. The default where chloride corrosion resistance is required.",
        identifiers=(("uns", "S31603"), ("en", "1.4404")),
        components=(("Iron", "matrix", 65.0, "%"), ("Chromium", "alloying", 17.0, "%"),
                    ("Nickel", "alloying", 12.0, "%"), ("Molybdenum", "alloying", 2.5, "%")),
        process_state="Annealed",
        properties={
            "density": (8000.0, "kg/m^3"), "tensile_strength": (560.0, "MPa"), "yield_strength": (290.0, "MPa"),
            "tensile_modulus": (193000.0, "MPa"), "elongation_at_break": (50.0, "%"),
            "fatigue_strength_1e7": (240.0, "MPa"), "fracture_toughness_k1c": (112.0, "MPa*m^0.5"),
            "hardness_vickers": (155.0, "1"), "thermal_conductivity": (16.3, "W/(m*K)"),
            "coefficient_thermal_expansion": (16.0, "1e-6/K"), "continuous_service_temperature": (550.0, "degC"),
            "melting_temperature": (1400.0, "degC"), "salt_spray_resistance": (2000.0, "h"),
            "chemical_resistance_rating": (4.5, "1"), "cost_per_mass": (4.50, "USD/kg"),
            "carbon_footprint": (5.00, "kgCO2e/kg"), "recycled_content": (60.0, "%"),
            "recyclability_rating": (5.0, "1"), "supplier_count": (40.0, "1"),
            "biocompatible_usp_vi": (True, None), "food_contact_compliant": (True, None),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Nickel content makes the price volatile and drives most 316L cost-reduction studies toward duplex or ferritic grades.",),
        tags=("corrosion", "food-contact", "medical", "process"),
    ),
    LibraryMaterial(
        key="ss-304", display_name="Stainless steel 304", family="alloy",
        description="The general-purpose austenitic stainless. Cheaper than 316L, less resistant to chlorides.",
        identifiers=(("uns", "S30400"), ("en", "1.4301")),
        components=(("Iron", "matrix", 70.0, "%"), ("Chromium", "alloying", 18.5, "%"), ("Nickel", "alloying", 9.0, "%")),
        process_state="Annealed",
        properties={
            "density": (8000.0, "kg/m^3"), "tensile_strength": (515.0, "MPa"), "yield_strength": (205.0, "MPa"),
            "tensile_modulus": (193000.0, "MPa"), "elongation_at_break": (40.0, "%"),
            "fatigue_strength_1e7": (240.0, "MPa"), "hardness_vickers": (150.0, "1"),
            "thermal_conductivity": (16.2, "W/(m*K)"), "coefficient_thermal_expansion": (17.3, "1e-6/K"),
            "continuous_service_temperature": (550.0, "degC"), "salt_spray_resistance": (1000.0, "h"),
            "cost_per_mass": (3.20, "USD/kg"), "carbon_footprint": (4.80, "kgCO2e/kg"),
            "recycled_content": (60.0, "%"), "supplier_count": (50.0, "1"),
            "food_contact_compliant": (True, None), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Pits in chloride service. Substituting 304 for 316L to save cost is the classic false economy in marine and food processing.",),
        tags=("corrosion", "food-contact", "general-purpose"),
    ),
    LibraryMaterial(
        key="steel-s355", display_name="Structural steel S355", family="alloy",
        description="Standard structural carbon steel. The cheapest route to stiffness and strength, if mass and corrosion are acceptable.",
        identifiers=(("en", "EN 10025 S355"),),
        components=(("Iron", "matrix", 98.0, "%"), ("Manganese", "alloying", 1.5, "%"), ("Carbon", "alloying", 0.2, "%")),
        process_state="Hot rolled",
        properties={
            "density": (7850.0, "kg/m^3"), "tensile_strength": (510.0, "MPa"), "yield_strength": (355.0, "MPa"),
            "tensile_modulus": (210000.0, "MPa"), "elongation_at_break": (22.0, "%"),
            "fatigue_strength_1e7": (200.0, "MPa"), "fracture_toughness_k1c": (100.0, "MPa*m^0.5"),
            "hardness_vickers": (160.0, "1"), "thermal_conductivity": (45.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (12.0, "1e-6/K"), "continuous_service_temperature": (400.0, "degC"),
            "cost_per_mass": (0.90, "USD/kg"), "carbon_footprint": (2.30, "kgCO2e/kg"),
            "recycled_content": (30.0, "%"), "recyclability_rating": (5.0, "1"), "supplier_count": (60.0, "1"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("No inherent corrosion resistance. The coating system is part of the material decision, not a detail.",),
        tags=("structural", "low-cost", "construction"),
    ),
    LibraryMaterial(
        key="brass-cuzn39pb3", display_name="Free-cutting brass CuZn39Pb3", family="alloy",
        description="The classic machining brass. Included as a worked example of a lead-driven regulatory replacement study.",
        identifiers=(("en", "CW614N"), ("uns", "C38500")),
        components=(("Copper", "matrix", 57.0, "%"), ("Zinc", "alloying", 39.0, "%"), ("Lead", "alloying", 3.0, "%")),
        process_state="Extruded / drawn",
        properties={
            "density": (8470.0, "kg/m^3"), "tensile_strength": (440.0, "MPa"), "yield_strength": (250.0, "MPa"),
            "tensile_modulus": (96000.0, "MPa"), "elongation_at_break": (20.0, "%"),
            "hardness_vickers": (130.0, "1"), "thermal_conductivity": (123.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (20.9, "1e-6/K"), "continuous_service_temperature": (200.0, "degC"),
            "cost_per_mass": (7.00, "USD/kg"), "carbon_footprint": (4.00, "kgCO2e/kg"),
            "supplier_count": (20.0, "1"), "reach_svhc_present": (True, None), "rohs_compliant": (False, None),
        },
        caveats=(
            "Lead at 3% w/w is far above the REACH SVHC 0.1% threshold and outside the RoHS limit without an exemption.",
            "This is the incumbent in a very large number of live replacement programmes. Low-lead brasses trade machinability for compliance.",
        ),
        tags=("machining", "regulatory-incumbent", "plumbing", "svhc"),
    ),

    # ---------------------------------------------------------------------------------------
    # Ceramics
    # ---------------------------------------------------------------------------------------
    LibraryMaterial(
        key="alumina-96", display_name="Alumina 96% (Al2O3)", family="ceramic",
        description="The commodity technical ceramic. Hard, insulating, thermally stable, and brittle.",
        identifiers=(("cas", "1344-28-1"),),
        components=(("Aluminium oxide", "matrix", 96.0, "%"), ("Silica and glassy phase", "binder", 4.0, "%")),
        process_state="Sintered",
        properties={
            "density": (3720.0, "kg/m^3"), "flexural_strength": (330.0, "MPa"), "tensile_modulus": (303000.0, "MPa"),
            "compressive_strength": (2100.0, "MPa"), "fracture_toughness_k1c": (3.50, "MPa*m^0.5"),
            "hardness_vickers": (1175.0, "1"), "thermal_conductivity": (24.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (8.20, "1e-6/K"), "continuous_service_temperature": (1500.0, "degC"),
            "dielectric_strength": (16.7, "kV/mm"), "dielectric_constant": (9.40, "1"),
            "volume_resistivity": (1e14, "ohm*cm"), "chemical_resistance_rating": (4.5, "1"),
            "cost_per_mass": (20.0, "USD/kg"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Fracture toughness of 3.5 MPa·m^0.5 means design is flaw-governed. Strength figures are statistical, not deterministic — use Weibull data.",),
        tags=("ceramic", "electrical-insulator", "wear", "high-temperature"),
    ),
    LibraryMaterial(
        key="zirconia-3ytzp", display_name="Zirconia 3Y-TZP", family="ceramic",
        description="Transformation-toughened zirconia. By far the toughest common technical ceramic, with low thermal conductivity.",
        identifiers=(("cas", "1314-23-4"),),
        components=(("Zirconium dioxide", "matrix", 95.0, "%"), ("Yttria", "stabiliser", 5.0, "%")),
        process_state="Sintered",
        properties={
            "density": (6050.0, "kg/m^3"), "flexural_strength": (900.0, "MPa"), "tensile_modulus": (210000.0, "MPa"),
            "compressive_strength": (2000.0, "MPa"), "fracture_toughness_k1c": (8.0, "MPa*m^0.5"),
            "hardness_vickers": (1250.0, "1"), "thermal_conductivity": (2.50, "W/(m*K)"),
            "coefficient_thermal_expansion": (10.5, "1e-6/K"), "continuous_service_temperature": (1000.0, "degC"),
            "chemical_resistance_rating": (4.5, "1"), "cost_per_mass": (60.0, "USD/kg"),
            "biocompatible_usp_vi": (True, None), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Low-temperature degradation (ageing) in humid service between roughly 150 and 400 °C is a real and well-documented failure mode.",),
        tags=("ceramic", "toughened", "medical", "wear"),
    ),
    LibraryMaterial(
        key="sic-sintered", display_name="Silicon carbide (sintered SiC)", family="ceramic",
        description="Extremely hard and thermally conductive. The standard for mechanical seal faces and abrasive service.",
        identifiers=(("cas", "409-21-2"),),
        components=(("Silicon carbide", "matrix", 99.0, "%"),),
        process_state="Pressureless sintered",
        properties={
            "density": (3100.0, "kg/m^3"), "flexural_strength": (400.0, "MPa"), "tensile_modulus": (410000.0, "MPa"),
            "compressive_strength": (3900.0, "MPa"), "fracture_toughness_k1c": (4.0, "MPa*m^0.5"),
            "hardness_vickers": (2500.0, "1"), "thermal_conductivity": (120.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (4.0, "1e-6/K"), "continuous_service_temperature": (1600.0, "degC"),
            "chemical_resistance_rating": (5.0, "1"), "cost_per_mass": (80.0, "USD/kg"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Very low thermal expansion combined with high stiffness makes thermal-shock design constraints unusually tight.",),
        tags=("ceramic", "wear", "sealing", "thermal"),
    ),

    # ---------------------------------------------------------------------------------------
    # Composites
    # ---------------------------------------------------------------------------------------
    LibraryMaterial(
        key="cfrp-ud-epoxy", display_name="CFRP unidirectional (carbon/epoxy, 60% Vf)", family="composite",
        description="Unidirectional carbon fibre in epoxy. The highest specific stiffness in routine engineering use.",
        components=(("Carbon fibre (standard modulus)", "reinforcement", 60.0, "%"), ("Epoxy resin", "matrix", 40.0, "%")),
        process_state="Autoclave cured, 0° fibre direction",
        properties={
            "density": (1600.0, "kg/m^3"), "tensile_strength": (1500.0, "MPa"), "tensile_modulus": (135000.0, "MPa"),
            "elongation_at_break": (1.20, "%"), "compressive_strength": (1200.0, "MPa"),
            "fatigue_strength_1e7": (600.0, "MPa"), "thermal_conductivity": (5.0, "W/(m*K)"),
            "coefficient_thermal_expansion": (-0.50, "1e-6/K"), "continuous_service_temperature": (120.0, "degC"),
            "glass_transition_temperature": (130.0, "degC"), "water_absorption_24h": (0.10, "%"),
            "cost_per_mass": (40.0, "USD/kg"), "carbon_footprint": (24.0, "kgCO2e/kg"),
            "recyclability_rating": (1.0, "1"), "supplier_count": (10.0, "1"),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=(
            "These are 0° fibre-direction values. Transverse and shear properties are an order of magnitude lower — a single number cannot describe this material.",
            "Negative longitudinal CTE. Bonded to metal, the interface sees large thermal-cycle strain.",
            "Service ceiling is set by the resin Tg, not the fibre.",
        ),
        tags=("composite", "aerospace", "lightweight", "anisotropic"),
    ),
    LibraryMaterial(
        key="gfrp-epoxy", display_name="GFRP (E-glass/epoxy laminate)", family="composite",
        description="Glass fibre reinforced epoxy. The cost-effective composite where carbon stiffness is unnecessary.",
        components=(("E-glass fibre", "reinforcement", 55.0, "%"), ("Epoxy resin", "matrix", 45.0, "%")),
        process_state="Laminated and cured, quasi-isotropic layup",
        properties={
            "density": (1900.0, "kg/m^3"), "tensile_strength": (400.0, "MPa"), "tensile_modulus": (25000.0, "MPa"),
            "elongation_at_break": (2.0, "%"), "flexural_strength": (450.0, "MPa"),
            "thermal_conductivity": (0.35, "W/(m*K)"), "coefficient_thermal_expansion": (12.0, "1e-6/K"),
            "continuous_service_temperature": (120.0, "degC"), "glass_transition_temperature": (125.0, "degC"),
            "water_absorption_24h": (0.20, "%"), "dielectric_strength": (12.0, "kV/mm"),
            "cost_per_mass": (8.0, "USD/kg"), "carbon_footprint": (6.0, "kgCO2e/kg"),
            "recyclability_rating": (1.0, "1"), "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Quasi-isotropic values shown. A directional layup will differ substantially and the layup is part of the material definition.",),
        tags=("composite", "electrical", "structural", "cost-effective"),
    ),
    LibraryMaterial(
        key="smc-polyester", display_name="SMC (glass/polyester sheet moulding compound)", family="composite",
        description="Compression-moulded chopped-glass thermoset. High-volume structural panels and electrical enclosures.",
        components=(("Chopped E-glass fibre", "reinforcement", 30.0, "%"), ("Unsaturated polyester resin", "matrix", 30.0, "%"),
                    ("Calcium carbonate filler", "filler", 40.0, "%")),
        process_state="Compression moulded",
        properties={
            "density": (1850.0, "kg/m^3"), "tensile_strength": (70.0, "MPa"), "flexural_modulus": (11000.0, "MPa"),
            "flexural_strength": (170.0, "MPa"), "elongation_at_break": (1.0, "%"),
            "heat_deflection_temperature_1_8mpa": (200.0, "degC"), "continuous_service_temperature": (150.0, "degC"),
            "coefficient_thermal_expansion": (20.0, "1e-6/K"), "water_absorption_24h": (0.20, "%"),
            "dielectric_strength": (14.0, "kV/mm"), "comparative_tracking_index": (600.0, "V"),
            "cost_per_mass": (3.50, "USD/kg"), "carbon_footprint": (4.0, "kgCO2e/kg"),
            "recyclability_rating": (1.0, "1"), "flammability_ul94_v0": (True, None),
            "reach_svhc_present": (False, None), "rohs_compliant": (True, None),
        },
        caveats=("Thermoset — not remeltable, and effectively not recyclable beyond grinding into filler.",),
        tags=("composite", "electrical", "automotive", "high-volume"),
    ),
)

LIBRARY_BY_KEY: dict[str, LibraryMaterial] = {m.key: m for m in STARTER_LIBRARY}


# Defaults used when deriving a candidate search space from a baseline material whose composition
# is thin. Bounds are deliberately conservative: a search space that is too wide produces
# combinatorially many candidates that nobody will ever evaluate, which is its own kind of useless.
FAMILY_SEARCH_DEFAULTS: dict[str, dict[str, Any]] = {
    "polymer": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 8,
        "candidate_budget": 60, "maximum_enumeration": 5000,
        "matrix_span": 12.0, "additive_span": 8.0, "step": 1.0,
        "process_rules": [
            {"parameter_key": "melt_temperature", "display_name": "Melt temperature", "min_value": 200.0,
             "max_value": 320.0, "step_value": 10.0, "unit": "degC"},
            {"parameter_key": "mould_temperature", "display_name": "Mould temperature", "min_value": 40.0,
             "max_value": 120.0, "step_value": 10.0, "unit": "degC"},
        ],
    },
    "alloy": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 10,
        "candidate_budget": 60, "maximum_enumeration": 5000,
        "matrix_span": 5.0, "additive_span": 2.0, "step": 0.25,
        "process_rules": [
            {"parameter_key": "ageing_temperature", "display_name": "Ageing temperature", "min_value": 120.0,
             "max_value": 220.0, "step_value": 10.0, "unit": "degC"},
        ],
    },
    "composite": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 6,
        "candidate_budget": 40, "maximum_enumeration": 3000,
        "matrix_span": 10.0, "additive_span": 6.0, "step": 1.0,
        "process_rules": [
            {"parameter_key": "cure_temperature", "display_name": "Cure temperature", "min_value": 80.0,
             "max_value": 180.0, "step_value": 10.0, "unit": "degC"},
        ],
    },
    "ceramic": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 6,
        "candidate_budget": 40, "maximum_enumeration": 3000,
        "matrix_span": 4.0, "additive_span": 2.0, "step": 0.5,
        "process_rules": [
            {"parameter_key": "sintering_temperature", "display_name": "Sintering temperature", "min_value": 1200.0,
             "max_value": 1800.0, "step_value": 50.0, "unit": "degC"},
        ],
    },
    "coating": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 8,
        "candidate_budget": 40, "maximum_enumeration": 3000,
        "matrix_span": 10.0, "additive_span": 5.0, "step": 1.0,
        "process_rules": [
            {"parameter_key": "cure_temperature", "display_name": "Cure temperature", "min_value": 60.0,
             "max_value": 250.0, "step_value": 10.0, "unit": "degC"},
        ],
    },
    "adhesive": {
        "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 8,
        "candidate_budget": 40, "maximum_enumeration": 3000,
        "matrix_span": 10.0, "additive_span": 5.0, "step": 1.0, "process_rules": [],
    },
}

DEFAULT_SEARCH_DEFAULTS: dict[str, Any] = {
    "amount_basis": "weight_percent", "total_target": 100.0, "max_component_count": 8,
    "candidate_budget": 40, "maximum_enumeration": 3000,
    "matrix_span": 8.0, "additive_span": 5.0, "step": 1.0, "process_rules": [],
}


def family_defaults(family: str) -> dict[str, Any]:
    return FAMILY_SEARCH_DEFAULTS.get(family, DEFAULT_SEARCH_DEFAULTS)
