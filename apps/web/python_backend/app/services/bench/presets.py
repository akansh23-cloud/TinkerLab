"""Phase 12 — replacement briefs expressed the way an industrial programme actually states them.

A replacement study does not begin with a search space and a random seed. It begins with a part, a
duty cycle, and a reason someone is being made to change: a regulator listed the additive, the
single supplier raised price 40%, the customer demanded a footprint number, the grade went
end-of-life.

Each preset below encodes one such brief as a typed requirement set. The values are the
requirements a competent engineer would open the discussion with for that application class — a
defensible starting point that the user is expected to edit, not a specification to be adopted
unread. Every preset therefore carries `assumptions`, stating in plain terms what was taken for
granted, so an engineer can see immediately where their case differs.

Hard vs soft is the load-bearing distinction. A hard requirement can eliminate a candidate. A soft
requirement expresses preference and cannot. Compliance items are always hard and always boolean:
market access does not trade off against a strength margin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequirementTemplate:
    property_key: str
    comparator: str
    target_value: float | None = None
    target_value_upper: float | None = None
    target_boolean: bool | None = None
    target_unit: str | None = None
    hard_or_soft: str = "hard"
    weight: float = 1.0
    severity: int = 4
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "property_key": self.property_key,
            "comparator": self.comparator,
            "target_value": self.target_value,
            "target_value_upper": self.target_value_upper,
            "target_boolean": self.target_boolean,
            "target_unit": self.target_unit,
            "hard_or_soft": self.hard_or_soft,
            "weight": self.weight,
            "severity": self.severity,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ObjectiveTemplate:
    property_key: str
    direction: str
    weight: float = 1.0
    priority: int = 1
    rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "property_key": self.property_key,
            "direction": self.direction,
            "weight": self.weight,
            "priority": self.priority,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ApplicationPreset:
    key: str
    display_name: str
    sector: str
    summary: str
    expected_family: str
    typical_drivers: tuple[str, ...]
    requirements: tuple[RequirementTemplate, ...]
    objectives: tuple[ObjectiveTemplate, ...]
    assumptions: tuple[str, ...] = ()
    watch_outs: tuple[str, ...] = ()
    amount_basis: str = "weight_percent"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "display_name": self.display_name,
            "sector": self.sector,
            "summary": self.summary,
            "expected_family": self.expected_family,
            "typical_drivers": list(self.typical_drivers),
            "requirements": [r.as_dict() for r in self.requirements],
            "objectives": [o.as_dict() for o in self.objectives],
            "assumptions": list(self.assumptions),
            "watch_outs": list(self.watch_outs),
            "amount_basis": self.amount_basis,
        }


APPLICATION_PRESETS: tuple[ApplicationPreset, ...] = (
    ApplicationPreset(
        key="automotive_underhood_polymer",
        display_name="Automotive under-hood polymer component",
        sector="Automotive",
        summary=(
            "Bracket, housing or air-path duct in the engine bay. Continuous heat with excursions, "
            "oil and coolant splash, and constant vibration."
        ),
        expected_family="polymer",
        typical_drivers=("cost", "supply_risk", "regulation", "weight"),
        requirements=(
            RequirementTemplate("continuous_service_temperature", ">=", 145.0, target_unit="degC", severity=5,
                                rationale="Under-hood ambient with heat soak after shutdown. Derived from thermal ageing, not a single-point softening test."),
            RequirementTemplate("peak_service_temperature", ">=", 180.0, target_unit="degC", severity=4,
                                rationale="Short excursions near the exhaust manifold during heat soak."),
            RequirementTemplate("tensile_strength", ">=", 90.0, target_unit="MPa", severity=5,
                                rationale="Mounting-boss load path under vibration and bolt preload."),
            RequirementTemplate("tensile_modulus", ">=", 5500.0, target_unit="MPa", severity=4,
                                rationale="Stiffness governs resonance. A softer bracket moves the first mode into the excitation band."),
            RequirementTemplate("izod_impact_notched", ">=", 60.0, target_unit="J/m", severity=4,
                                rationale="Stone impact and service handling. Notched, because every moulded bracket has gates and ribs."),
            RequirementTemplate("coefficient_thermal_expansion", "<=", 60.0, target_unit="1e-6/K", hard_or_soft="soft",
                                weight=0.8, severity=3,
                                rationale="CTE mismatch against the aluminium mating face is what cracks the boss over thermal cycles."),
            RequirementTemplate("water_absorption_24h", "<=", 1.5, target_unit="%", hard_or_soft="soft", weight=0.7, severity=3,
                                rationale="Moisture uptake moves dimensions and halves polyamide modulus. Confirm whether datasheet values are dry-as-moulded."),
            RequirementTemplate("reach_svhc_present", "boolean", target_boolean=False, severity=5,
                                rationale="EU market access. Article 33 duties above 0.1% w/w."),
            RequirementTemplate("cost_per_mass", "<=", 8.5, target_unit="USD/kg", hard_or_soft="soft", weight=0.9, severity=3,
                                rationale="Programme cost envelope. Convert to cost per part before concluding anything."),
        ),
        objectives=(
            ObjectiveTemplate("cost_per_mass", "minimize", 1.0, 1, rationale="Primary commercial driver."),
            ObjectiveTemplate("density", "minimize", 0.7, 2, rationale="Mass reduction carries through to fleet CO2 compliance."),
            ObjectiveTemplate("continuous_service_temperature", "maximize", 0.6, 3, rationale="Thermal headroom for future engine calibrations."),
        ),
        assumptions=(
            "Ambient duty around 120 °C with heat-soak excursions to 180 °C.",
            "Existing aluminium mating face and steel fastener; joint design is not being changed.",
            "Injection moulded on existing tooling; a shrinkage change beyond ~0.1% implies steel rework.",
        ),
        watch_outs=(
            "Polyamide datasheet values are usually dry-as-moulded. Conditioned modulus can be 40–50% lower.",
            "Glass-fibre grades are anisotropic. Flow-direction values overstate performance across the weld line.",
            "Long-term retention after 1000 h at temperature matters more here than any as-moulded number.",
        ),
    ),
    ApplicationPreset(
        key="ev_battery_pack_component",
        display_name="EV battery pack structural / dielectric component",
        sector="E-mobility",
        summary=(
            "Cell holder, busbar support or pack enclosure part. Dominated by flame behaviour, "
            "tracking resistance and dielectric integrity at pack voltage."
        ),
        expected_family="polymer",
        typical_drivers=("regulation", "performance", "supply_risk", "weight"),
        requirements=(
            RequirementTemplate("flammability_ul94_v0", "boolean", target_boolean=True, severity=5,
                                rationale="Pack-level fire containment. Rating is thickness-specific — record the rated wall."),
            RequirementTemplate("comparative_tracking_index", ">=", 600.0, target_unit="V", severity=5,
                                rationale="800 V architectures with condensation and dust require the top CTI band."),
            RequirementTemplate("dielectric_strength", ">=", 20.0, target_unit="kV/mm", severity=5,
                                rationale="Insulation margin at pack voltage. Quote with specimen thickness or the number is not comparable."),
            RequirementTemplate("continuous_service_temperature", ">=", 120.0, target_unit="degC", severity=4,
                                rationale="Fast-charge thermal load plus local hot spots at the busbar interface."),
            RequirementTemplate("limiting_oxygen_index", ">=", 28.0, target_unit="%", hard_or_soft="soft", weight=0.8, severity=4,
                                rationale="A continuous flammability measure, so unlike a UL 94 rating it can actually be ranked."),
            RequirementTemplate("tensile_strength", ">=", 70.0, target_unit="MPa", severity=4,
                                rationale="Cell retention under crash and vibration load cases."),
            RequirementTemplate("halogen_free", "boolean", target_boolean=True, hard_or_soft="soft", weight=0.7, severity=3,
                                rationale="Common OEM specification for pack interiors, independent of RoHS."),
            RequirementTemplate("reach_svhc_present", "boolean", target_boolean=False, severity=5,
                                rationale="EU market access."),
            RequirementTemplate("pfas_present", "boolean", target_boolean=False, hard_or_soft="soft", weight=0.9, severity=4,
                                rationale="Forward-looking against the ECHA universal restriction proposal; fluoropolymer processing aids are in scope."),
        ),
        objectives=(
            ObjectiveTemplate("density", "minimize", 1.0, 1, rationale="Pack mass is the dominant vehicle-level penalty."),
            ObjectiveTemplate("cost_per_mass", "minimize", 0.9, 2, rationale="Pack cost per kWh is the programme metric."),
            ObjectiveTemplate("comparative_tracking_index", "maximize", 0.6, 3, rationale="Insulation margin for future voltage increases."),
        ),
        assumptions=(
            "800 V architecture, so CTI 600 rather than the 400–500 band adequate at 400 V.",
            "Component is not a primary crash structure; retention loads only.",
            "Flame rating claimed at the actual moulded wall thickness, not the datasheet's thinnest qualified section.",
        ),
        watch_outs=(
            "Halogen-free flame retardant packages usually cost mechanical properties. Check impact after ageing.",
            "Red phosphorus and some phosphinate systems interact badly with polyamide hydrolysis resistance.",
            "A V-0 at 3.0 mm tells you nothing about the same grade at 1.0 mm.",
        ),
    ),
    ApplicationPreset(
        key="food_contact_packaging_film",
        display_name="Food contact packaging film",
        sector="Packaging",
        summary="Flexible film or rigid tray in direct food contact. Barrier performance and migration compliance dominate.",
        expected_family="polymer",
        typical_drivers=("sustainability", "regulation", "cost"),
        requirements=(
            RequirementTemplate("food_contact_compliant", "boolean", target_boolean=True, severity=5,
                                rationale="EU 10/2011 and FDA 21 CFR are not equivalent — state which regime in the evidence note."),
            RequirementTemplate("oxygen_transmission_rate", "<=", 50.0, target_unit="cm^3/(m^2*d*bar)", severity=4,
                                rationale="Shelf-life target for an oxygen-sensitive product."),
            RequirementTemplate("water_vapour_transmission_rate", "<=", 5.0, target_unit="g/(m^2*d)", severity=4,
                                rationale="Moisture barrier for texture retention."),
            RequirementTemplate("tensile_strength", ">=", 25.0, target_unit="MPa", severity=4,
                                rationale="Survives the form-fill-seal line without web breaks."),
            RequirementTemplate("elongation_at_break", ">=", 150.0, target_unit="%", severity=3,
                                rationale="Ductility for thermoforming and drop resistance when filled."),
            RequirementTemplate("recyclability_rating", ">=", 4.0, target_unit="1", hard_or_soft="soft", weight=1.0, severity=4,
                                rationale="Mono-material structures score here; multilayer barrier laminates do not."),
            RequirementTemplate("pfas_present", "boolean", target_boolean=False, severity=5,
                                rationale="Grease-proofing fluorochemicals are already restricted in several food-contact jurisdictions."),
            RequirementTemplate("cost_per_mass", "<=", 4.0, target_unit="USD/kg", hard_or_soft="soft", weight=0.9, severity=3,
                                rationale="Commodity packaging economics leave very little headroom."),
        ),
        objectives=(
            ObjectiveTemplate("carbon_footprint", "minimize", 1.0, 1, rationale="Retailer footprint commitments are increasingly contractual."),
            ObjectiveTemplate("cost_per_mass", "minimize", 1.0, 2, rationale="Packaging is cost-led."),
            ObjectiveTemplate("recycled_content", "maximize", 0.8, 3, rationale="PPWR-style recycled content mandates."),
        ),
        assumptions=(
            "Direct food contact, so migration compliance is a gate rather than a preference.",
            "Barrier targets stated at 23 °C / 50% RH; a humid supply chain will be worse.",
            "Mono-material recyclability is being pursued in preference to a barrier laminate.",
        ),
        watch_outs=(
            "Barrier and recyclability pull hard against each other. EVOH improves OTR and damages the recycling stream.",
            "Recycled content in direct food contact needs an EFSA-recognised process, not just a PCR percentage.",
            "OTR is strongly humidity-dependent for EVOH and polyamide. A dry-condition value flatters them.",
        ),
    ),
    ApplicationPreset(
        key="medical_device_housing",
        display_name="Reusable medical device housing",
        sector="Medical",
        summary="Enclosure subject to repeated autoclave or chemical disinfection cycles, with biocompatibility on contact surfaces.",
        expected_family="polymer",
        typical_drivers=("regulation", "performance", "supply_risk"),
        requirements=(
            RequirementTemplate("biocompatible_usp_vi", "boolean", target_boolean=True, severity=5,
                                rationale="Patient contact gate. Grade-specific and lot-sensitive — never inherit it from the base polymer."),
            RequirementTemplate("continuous_service_temperature", ">=", 140.0, target_unit="degC", severity=5,
                                rationale="Repeated 134 °C steam autoclave cycles with margin."),
            RequirementTemplate("chemical_resistance_rating", ">=", 4.0, target_unit="1", severity=4,
                                rationale="Quaternary ammonium and alcohol disinfectants cause environmental stress cracking in several clear polymers."),
            RequirementTemplate("tensile_strength", ">=", 60.0, target_unit="MPa", severity=4,
                                rationale="Drop survival for a handheld enclosure."),
            RequirementTemplate("izod_impact_notched", ">=", 50.0, target_unit="J/m", severity=4,
                                rationale="Toughness must be retained after sterilisation cycling, not just as-moulded."),
            RequirementTemplate("water_absorption_24h", "<=", 0.5, target_unit="%", severity=3,
                                rationale="Dimensional stability across wet sterilisation cycles."),
            RequirementTemplate("reach_svhc_present", "boolean", target_boolean=False, severity=5,
                                rationale="EU MDR technical documentation requires substance disclosure."),
        ),
        objectives=(
            ObjectiveTemplate("izod_impact_notched", "maximize", 1.0, 1, rationale="Drop performance drives field returns."),
            ObjectiveTemplate("cost_per_mass", "minimize", 0.6, 2, rationale="Secondary — requalification cost dominates material cost here."),
        ),
        assumptions=(
            "Steam autoclave at 134 °C, several hundred cycles over device life.",
            "Housing contacts skin only; no implant or blood path.",
            "Change triggers a design change notification, so requalification cost dwarfs any per-kilo saving.",
        ),
        watch_outs=(
            "Post-sterilisation retained impact is the real acceptance test. As-moulded values mislead badly.",
            "Polycarbonate is convenient and cracks under alcohol disinfectants at moulded-in stress.",
            "USP Class VI applies to the specific grade and colourant, not the polymer family.",
        ),
    ),
    ApplicationPreset(
        key="aerospace_structural_bracket",
        display_name="Aerospace secondary structural bracket",
        sector="Aerospace",
        summary="Non-primary metallic or composite bracket. Fatigue and damage tolerance govern; mass is the objective.",
        expected_family="alloy",
        typical_drivers=("weight", "performance", "supply_risk"),
        requirements=(
            RequirementTemplate("yield_strength", ">=", 270.0, target_unit="MPa", severity=5,
                                rationale="Limit-load sizing case with no permanent set."),
            RequirementTemplate("fatigue_strength_1e7", ">=", 110.0, target_unit="MPa", severity=5,
                                rationale="Airframe life is fatigue-driven. Static strength alone certifies nothing."),
            RequirementTemplate("fracture_toughness_k1c", ">=", 25.0, target_unit="MPa*m^0.5", severity=5,
                                rationale="Damage tolerance against an assumed initial flaw."),
            RequirementTemplate("density", "<=", 3000.0, target_unit="kg/m^3", severity=4,
                                rationale="Mass budget; rules out steel substitutions early."),
            RequirementTemplate("continuous_service_temperature", ">=", 120.0, target_unit="degC", severity=4,
                                rationale="Skin temperature plus a system heat source."),
            RequirementTemplate("salt_spray_resistance", ">=", 500.0, target_unit="h", hard_or_soft="soft", weight=0.8, severity=3,
                                rationale="Corrosion protection with the coating system applied."),
            RequirementTemplate("supplier_count", ">=", 2.0, target_unit="1", hard_or_soft="soft", weight=0.9, severity=4,
                                rationale="Dual-source is usually the actual reason the study exists."),
        ),
        objectives=(
            ObjectiveTemplate("density", "minimize", 1.0, 1, rationale="Mass is the aerospace objective function."),
            ObjectiveTemplate("fatigue_strength_1e7", "maximize", 0.9, 2, rationale="Life margin against inspection interval."),
            ObjectiveTemplate("cost_per_mass", "minimize", 0.5, 3, rationale="Real but subordinate to mass and certification cost."),
        ),
        assumptions=(
            "Secondary structure: failure is not catastrophic, but inspection intervals still apply.",
            "Existing fastener pattern and joint design retained.",
            "Specific-strength comparison is the meaningful one, not absolute strength.",
        ),
        watch_outs=(
            "Fatigue data is scarce and specimen-condition dependent. Absence of a value is a finding, not a pass.",
            "Galvanic compatibility with the surrounding structure constrains the choice as hard as strength does.",
            "Certification cost usually exceeds any material saving; substitution needs a qualification pathway, not just numbers.",
        ),
    ),
    ApplicationPreset(
        key="pfas_free_coating",
        display_name="PFAS-free low-friction / release coating",
        sector="Industrial coatings",
        summary="Replacing a fluoropolymer release or low-friction coating ahead of the ECHA universal PFAS restriction.",
        expected_family="coating",
        typical_drivers=("regulation", "sustainability", "supply_risk"),
        requirements=(
            RequirementTemplate("pfas_present", "boolean", target_boolean=False, severity=5,
                                rationale="The entire purpose of the programme. The restriction definition is broad."),
            RequirementTemplate("continuous_service_temperature", ">=", 200.0, target_unit="degC", severity=5,
                                rationale="Bake or process temperature the coated part sees in service."),
            RequirementTemplate("salt_spray_resistance", ">=", 240.0, target_unit="h", severity=4,
                                rationale="Substrate protection where the coating is also the corrosion barrier."),
            RequirementTemplate("hardness_vickers", ">=", 200.0, target_unit="1", hard_or_soft="soft", weight=0.8, severity=3,
                                rationale="Abrasion resistance proxy; the real test is a Taber or pin-on-disc run."),
            RequirementTemplate("chemical_resistance_rating", ">=", 4.0, target_unit="1", severity=4,
                                rationale="Cleaning chemistry and process media exposure."),
            RequirementTemplate("food_contact_compliant", "boolean", target_boolean=True, hard_or_soft="soft", weight=0.7, severity=3,
                                rationale="Needed only if the coated surface is a food or pharma contact face."),
            RequirementTemplate("reach_svhc_present", "boolean", target_boolean=False, severity=5,
                                rationale="Avoid replacing one restricted substance with another."),
        ),
        objectives=(
            ObjectiveTemplate("cost_per_mass", "minimize", 0.8, 2, rationale="Coating cost per part including application yield."),
            ObjectiveTemplate("continuous_service_temperature", "maximize", 1.0, 1, rationale="Thermal headroom is where PFAS-free systems most often fall short."),
        ),
        assumptions=(
            "Release performance is being traded for compliance; some loss is expected and must be quantified.",
            "Existing application line — spray and cure, no new capital equipment.",
            "Substrate and pre-treatment unchanged.",
        ),
        watch_outs=(
            "Coefficient of friction is not in the catalogue as a headline property because it is only meaningful with a stated counterface and load. Record it as a measured observation with conditions.",
            "Silicone and sol-gel alternatives usually give up continuous service temperature. Check the bake cycle first.",
            "'Fluorine-free' marketing claims are not the same as compliance with the proposed restriction definition.",
        ),
    ),
    ApplicationPreset(
        key="consumer_appliance_housing",
        display_name="Consumer appliance housing",
        sector="Consumer durables",
        summary="Visible enclosure with cost, flame rating and surface finish as the governing constraints.",
        expected_family="polymer",
        typical_drivers=("cost", "sustainability", "supply_risk"),
        requirements=(
            RequirementTemplate("flammability_ul94_v0", "boolean", target_boolean=True, severity=5,
                                rationale="Mains-powered enclosure requirement at the moulded wall thickness."),
            RequirementTemplate("heat_deflection_temperature_1_8mpa", ">=", 85.0, target_unit="degC", severity=4,
                                rationale="Internal heat rise plus shipping-container temperatures."),
            RequirementTemplate("izod_impact_notched", ">=", 100.0, target_unit="J/m", severity=4,
                                rationale="Consumer drop and handling abuse."),
            RequirementTemplate("tensile_strength", ">=", 40.0, target_unit="MPa", severity=3,
                                rationale="Snap-fit and boss retention."),
            RequirementTemplate("cost_per_mass", "<=", 3.2, target_unit="USD/kg", severity=4,
                                rationale="Hard commercial gate — consumer BOM cost is unforgiving."),
            RequirementTemplate("recycled_content", ">=", 30.0, target_unit="%", hard_or_soft="soft", weight=1.0, severity=3,
                                rationale="Retailer and eco-label commitments."),
            RequirementTemplate("rohs_compliant", "boolean", target_boolean=True, severity=5,
                                rationale="Electrical equipment market access."),
        ),
        objectives=(
            ObjectiveTemplate("cost_per_mass", "minimize", 1.0, 1, rationale="Dominant driver."),
            ObjectiveTemplate("recycled_content", "maximize", 0.8, 2, rationale="Eco-label and regulatory direction of travel."),
            ObjectiveTemplate("carbon_footprint", "minimize", 0.6, 3, rationale="Corporate reporting commitment."),
        ),
        assumptions=(
            "Visible A-surface, so colour and gloss consistency constrain filler loading.",
            "Existing injection tool; shrinkage must match within about 0.1%.",
            "Recycled content is post-consumer, which carries batch-to-batch impact variation.",
        ),
        watch_outs=(
            "Post-consumer recyclate degrades notched impact and colour consistency. Specify a retained-impact floor, not just a PCR percentage.",
            "Flame-retardant packages and PCR content interact; a compliant virgin grade may not stay compliant at 30% PCR.",
        ),
    ),
    ApplicationPreset(
        key="chemical_process_wetted_part",
        display_name="Chemical process wetted component",
        sector="Process industry",
        summary="Pump, valve or seal component in continuous contact with process fluid at temperature and pressure.",
        expected_family="polymer",
        typical_drivers=("performance", "supply_risk", "regulation", "cost"),
        requirements=(
            RequirementTemplate("chemical_resistance_rating", ">=", 4.5, target_unit="1", severity=5,
                                rationale="Continuous immersion in the declared reagent set."),
            RequirementTemplate("continuous_service_temperature", ">=", 150.0, target_unit="degC", severity=5,
                                rationale="Process temperature with margin for upset conditions."),
            RequirementTemplate("creep_modulus_1000h", ">=", 1200.0, target_unit="MPa", severity=5,
                                rationale="Sustained pressure load. Short-term modulus badly overstates a polymer here; this is why flanges relax and seals weep."),
            RequirementTemplate("compressive_strength", ">=", 80.0, target_unit="MPa", severity=4,
                                rationale="Bolt preload on the seal face."),
            RequirementTemplate("water_absorption_24h", "<=", 0.3, target_unit="%", severity=4,
                                rationale="Dimensional stability of the sealing geometry."),
            RequirementTemplate("pfas_present", "boolean", target_boolean=False, hard_or_soft="soft", weight=0.8, severity=4,
                                rationale="PTFE and PFA are the incumbent answers here, which is precisely why the restriction hurts."),
            RequirementTemplate("lead_time", "<=", 12.0, target_unit="wk", hard_or_soft="soft", weight=0.9, severity=4,
                                rationale="Plant shutdown windows are fixed. A 26-week lead time cannot support a turnaround."),
        ),
        objectives=(
            ObjectiveTemplate("chemical_resistance_rating", "maximize", 1.0, 1, rationale="Failure mode is chemical attack, not mechanical overload."),
            ObjectiveTemplate("lead_time", "minimize", 0.8, 2, rationale="Availability inside the shutdown window."),
            ObjectiveTemplate("cost_per_mass", "minimize", 0.5, 3, rationale="Subordinate to unplanned downtime cost."),
        ),
        assumptions=(
            "Continuous immersion rather than splash contact.",
            "Reagent set declared explicitly in the evidence note; a generic resistance rating is not transferable between chemistries.",
            "Sealing geometry unchanged.",
        ),
        watch_outs=(
            "A chemical resistance rating is a curator judgement against a declared reagent list. It is not a measurement and should not be treated as one.",
            "Environmental stress cracking under combined stress and chemical exposure is not predicted by immersion data alone.",
            "Replacing a fluoropolymer usually costs both temperature and chemical breadth. Expect to narrow the duty envelope.",
        ),
    ),
    ApplicationPreset(
        key="cost_reduction_generic",
        display_name="Generic cost-out / dual-source programme",
        sector="Cross-sector",
        summary=(
            "No application change. The incumbent works; the objective is a cheaper or second-sourced grade "
            "that holds the current performance envelope."
        ),
        expected_family="polymer",
        typical_drivers=("cost", "supply_risk", "availability"),
        requirements=(
            RequirementTemplate("tensile_strength", ">=", 0.0, target_unit="MPa", severity=5,
                                rationale="Placeholder — set from the incumbent's measured value, minus your accepted margin."),
            RequirementTemplate("continuous_service_temperature", ">=", 0.0, target_unit="degC", severity=5,
                                rationale="Placeholder — set from the incumbent's rating."),
            RequirementTemplate("supplier_count", ">=", 2.0, target_unit="1", severity=4,
                                rationale="Dual-source is the point of the programme."),
            RequirementTemplate("reach_svhc_present", "boolean", target_boolean=False, severity=5,
                                rationale="Do not import a compliance problem while chasing a cost saving."),
        ),
        objectives=(
            ObjectiveTemplate("cost_per_mass", "minimize", 1.0, 1, rationale="The programme objective."),
            ObjectiveTemplate("supplier_count", "maximize", 0.7, 2, rationale="Supply resilience."),
        ),
        assumptions=(
            "The incumbent's measured properties define the floor. Load them before running anything.",
            "No design or tooling change is contemplated.",
        ),
        watch_outs=(
            "Placeholder thresholds are set to zero deliberately. Run the baseline-derived brief so the floors come from your own evidence rather than from a template.",
            "Cost per kilogram is the wrong comparison basis across different densities. Use cost per part.",
        ),
    ),
)

PRESETS_BY_KEY: dict[str, ApplicationPreset] = {p.key: p for p in APPLICATION_PRESETS}


REPLACEMENT_DRIVERS: tuple[dict[str, str], ...] = (
    {"key": "regulation", "display_name": "Regulatory restriction",
     "description": "A substance in the incumbent is restricted, listed or proposed for restriction (REACH SVHC, RoHS, PFAS)."},
    {"key": "cost", "display_name": "Cost reduction",
     "description": "The incumbent works but costs more than the programme can carry."},
    {"key": "supply_risk", "display_name": "Supply risk",
     "description": "Single source, geopolitical exposure, allocation, or an end-of-life notice on the grade."},
    {"key": "sustainability", "display_name": "Sustainability commitment",
     "description": "A footprint, recycled content or circularity target that the incumbent cannot meet."},
    {"key": "performance", "display_name": "Performance shortfall",
     "description": "The incumbent is failing in the field or blocks a required duty increase."},
    {"key": "weight", "display_name": "Mass reduction",
     "description": "Vehicle range, fleet emissions or handling ergonomics require a lighter part."},
    {"key": "toxicity", "display_name": "Toxicity / worker exposure",
     "description": "Occupational exposure or customer chemical-policy pressure, ahead of any legal restriction."},
    {"key": "availability", "display_name": "Availability / lead time",
     "description": "Lead times no longer support the production plan."},
)
