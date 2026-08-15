"""Phase 10 — Seeded demonstration replacement programme.

Everything created here is SYNTHETIC and labelled as such. No value below is a measurement of any
real substance, no literature source is cited, and no real material is given a fabricated property.
The three candidates are invented specifically so the decision engine's three genuine outcomes —
advance, reject, hold — can each be exercised and demonstrated end to end.

Scenario
--------
Replacing silicon in a high-temperature power-electronics switch.

  Candidate A  strong computational evidence, admissible replicated measurements that agree with
               it, and resolved industrial evidence            -> recommended to ADVANCE
  Candidate B  excellent predicted performance, but replicated physical measurement contradicts a
               BLOCKING requirement                            -> REJECTED on experimental evidence
  Candidate C  promising band gap, but breakdown field and thermal conductivity have no evidence at
               all                                             -> HELD, with a next action proposed

Silicon itself deliberately keeps no fabricated property values. The incumbent column in the
comparison view therefore reads UNKNOWN, which is the honest state of this database.
"""

from __future__ import annotations

from datetime import UTC
from datetime import date as dt_date
from datetime import datetime as dt_datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    Application,
    ApplicationComponent,
    Candidate,
    Evidence,
    ExperimentPlan,
    ExperimentProtocol,
    ExperimentProtocolVersion,
    FunctionalRequirement,
    IndustrialEvidence,
    Instrument,
    Material,
    MaterialFunction,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialRole,
    MaterialState,
    MaturityAssessment,
    Organisation,
    ReplacementProgram,
    ReplacementProject,
    Sample,
    User,
)
from app.services.experiments_lab import (
    create_plan,
    create_protocol_version,
    create_sample,
    materialize_plan_runs,
    record_measurement,
)
from app.services.industrial import create_industrial_evidence
from app.services.material_states import create_material_state
from app.services.replacement.policy import ensure_default_policy
from app.services.replacement.programs import create_program, refresh_program_state

SYNTHETIC_NOTE = (
    "SYNTHETIC / DEMONSTRATION DATA. This material does not exist and these values are not "
    "measurements of anything. They exist only to exercise the decision engine."
)


def seed_phase10(db: Session, org: Organisation, user: User, sid) -> None:
    """Create the demonstration replacement programme. Idempotent on the deterministic seed ids."""
    silicon_id = sid("material:silicon")
    silicon_state_id = sid("phase8:state:silicon-single-crystal-300k")
    if not db.get(Material, silicon_id):
        return

    ensure_default_policy(db, organisation_id=org.id)
    db.commit()

    # ------------------------------------------------------------------------------------------
    # Project. Separate from the Phase-8 study so the deliberately-sparse Phase-8 fixtures keep
    # demonstrating honest UNKNOWN behaviour without being contaminated by this richer scenario.
    # ------------------------------------------------------------------------------------------
    project_id = sid("phase10:project")
    project = db.get(ReplacementProject, project_id)
    if project is None:
        project = ReplacementProject(
            id=project_id, organisation_id=org.id,
            name="High-temperature silicon replacement (SYNTHETIC DEMONSTRATION)",
            description="Demonstration programme for the Phase-10 replacement decision OS. All "
                        "candidate materials and all evidence in this project are synthetic.",
            baseline_material_id=silicon_id,
            replacement_reasons=["performance", "supply_risk"], status="active", created_by=user.id,
        )
        db.add(project)
        db.commit()

    # ------------------------------------------------------------------------------------------
    # Application context
    # ------------------------------------------------------------------------------------------
    application_id = sid("phase10:application:ht-power-electronics")
    if not db.get(Application, application_id):
        db.add(Application(
            id=application_id, organisation_id=org.id, visibility="private",
            key="high_temperature_power_electronics",
            display_name="High-temperature power electronic switch (demonstration)",
            domain="power_electronics",
            description="Demonstration application: a switching device required to operate at a "
                        "junction temperature well above conventional silicon practice.",
            operating_conditions={
                "junction_temperature_k": 525.0, "blocking_voltage_v": 3300.0,
                "ambient": "sealed module", "lifetime_target_hours": 100000,
            },
            status="active",
        ))
        db.flush()

    component_id = sid("phase10:component:ht-active-region")
    if not db.get(ApplicationComponent, component_id):
        db.add(ApplicationComponent(
            id=component_id, application_id=application_id, key="ht_active_region",
            display_name="High-temperature active switching region",
            description="Blocks voltage when off and conducts when on, at elevated junction "
                        "temperature.",
            operating_conditions={"junction_temperature_k": 525.0},
        ))
        db.flush()

    role_id = sid("phase10:role:ht-switching-material")
    if not db.get(MaterialRole, role_id):
        db.add(MaterialRole(
            id=role_id, component_id=component_id, key="ht_switching_material",
            display_name="High-temperature switching material",
            description="A replacement must preserve what silicon DOES here at a temperature "
                        "silicon is not comfortable at.",
            incumbent_material_id=silicon_id, incumbent_state_id=silicon_state_id,
        ))
        db.flush()
    db.commit()

    # ------------------------------------------------------------------------------------------
    # Functions and requirements. Thresholds are illustrative engineering targets for the
    # demonstration; they are statements of what the application needs, not measurements.
    # ------------------------------------------------------------------------------------------
    functions: list[tuple[str, str, str, int, list[tuple[Any, ...]]]] = [
        ("ht_block_electric_field", "Withstand electric field when off at temperature", "electronic", 5, [
            ("ht_min_breakdown_field", "Breakdown field at least 2.0 MV/cm", "hard_constraint",
             "blocking", "minimum", "breakdown_field", 2.0, "MV/cm",
             "A 3.3 kV blocking requirement in a thin active region needs a high critical field."),
        ]),
        ("ht_limit_leakage", "Limit leakage at 525 K junction temperature", "electronic", 5, [
            ("ht_min_band_gap", "Band gap at least 2.5 eV", "hard_constraint",
             "blocking", "minimum", "band_gap", 2.5, "eV",
             "A wide gap suppresses thermally generated carriers at 525 K."),
        ]),
        ("ht_remove_heat", "Remove heat from the active region", "thermal", 5, [
            ("ht_min_thermal_conductivity", "Thermal conductivity at least 150 W/(m*K)",
             "hard_constraint", "blocking", "minimum", "thermal_conductivity", 150.0, "W/(m*K)",
             "Heat must leave the junction fast enough to hold the operating temperature."),
        ]),
        ("ht_carry_current", "Carry on-state current", "electronic", 3, [
            ("ht_maximise_electron_mobility", "Higher electron mobility is preferred", "objective",
             "desirable", "maximize", "electron_mobility", None, "cm^2/(V*s)",
             "Mobility sets on-state resistance; it is ranked, not passed or failed."),
        ]),
    ]
    for fkey, fname, category, criticality_int, requirements in functions:
        function_id = sid(f"phase10:function:{fkey}")
        if not db.get(MaterialFunction, function_id):
            db.add(MaterialFunction(
                id=function_id, role_id=role_id, key=fkey, display_name=fname, category=category,
                criticality=criticality_int,
                description="Demonstration function for the Phase-10 decision engine.",
                operating_conditions={"junction_temperature_k": 525.0},
            ))
            db.flush()
        for (rkey, rname, kind, crit, direction, property_key, target, unit, rationale) in requirements:
            requirement_id = sid(f"phase10:requirement:{rkey}")
            if db.get(FunctionalRequirement, requirement_id):
                continue
            definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
            db.add(FunctionalRequirement(
                id=requirement_id, function_id=function_id, key=rkey, display_name=rname,
                requirement_kind=kind, direction=direction,
                property_definition_id=definition.id if definition else None,
                property_key=property_key, target_value=target, target_unit=unit,
                conditions={"temperature_k": 525.0},
                criticality=crit, requirement_origin="application_template",
                approval_status="accepted", requirement_version=1,
                rationale=rationale + " Illustrative demonstration threshold.",
            ))
    db.commit()

    # ------------------------------------------------------------------------------------------
    # Three synthetic candidates
    # ------------------------------------------------------------------------------------------
    evidence_id = sid("phase10:evidence:synthetic")
    if not db.get(Evidence, evidence_id):
        db.add(Evidence(
            id=evidence_id, evidence_type="seed_demo",
            title="Synthetic demonstration values for the Phase-10 decision engine",
            source_reference="TinkerLab Phase-10 deterministic seed dataset",
            description=SYNTHETIC_NOTE, method="Deterministic seed fixture", confidence=1.0,
            metadata_json={"demo_only": True, "scientific_claim": False},
        ))
        db.flush()

    # (key, display, band_gap, breakdown_field, thermal_conductivity, electron_mobility)
    # A None entry means no value is seeded at all, so the engine must report UNKNOWN.
    candidate_specs: list[tuple[str, str, float | None, float | None, float | None, float | None]] = [
        ("demo-ht-candidate-a", "Demo Candidate A — wide-gap synthetic alpha (SYNTHETIC)",
         3.26, 2.8, 380.0, 900.0),
        ("demo-ht-candidate-b", "Demo Candidate B — wide-gap synthetic beta (SYNTHETIC)",
         3.40, 3.3, 230.0, 1200.0),
        ("demo-ht-candidate-c", "Demo Candidate C — wide-gap synthetic gamma (SYNTHETIC)",
         2.90, None, None, 700.0),
    ]

    candidate_row_ids: dict[str, str] = {}
    for key, display, band_gap, breakdown, thermal, mobility in candidate_specs:
        material_id = sid(f"material:{key}")
        if not db.get(Material, material_id):
            db.add(Material(
                id=material_id, canonical_name=key, display_name=display,
                material_family="crystalline_inorganic",
                description=SYNTHETIC_NOTE, composition_summary="Xx (fictitious)",
                source_type="seed_demo", is_seed_data=True,
                owner_organisation_id=org.id, visibility="private",
            ))
            db.flush()

        state_id = sid(f"phase10:state:{key}")
        if not db.get(MaterialState, state_id):
            create_material_state(
                db, organisation_id=org.id, material_id=material_id,
                label=f"{display} reference state, 525 K (synthetic)",
                composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0},
                             {"element": "C", "role": "host", "stoichiometry": 1.0}],
                polymorph="demo_polytype", phase="solid", temperature_k=525.0,
                is_reference_state=True,
                provenance_note="Synthetic state for a synthetic material; exists only to exercise "
                                "state matching.",
                row_id=state_id,
            )
            db.commit()

        candidate_id = sid(f"phase10:candidate:{key}")
        candidate_row_ids[key] = candidate_id
        if not db.get(Candidate, candidate_id):
            db.add(Candidate(
                id=candidate_id, project_id=project_id, candidate_kind="known_material",
                material_id=material_id, candidate_source="manual", status="proposed",
                notes=SYNTHETIC_NOTE,
            ))
            db.flush()

        for property_key, value in (
            ("band_gap", band_gap), ("breakdown_field", breakdown),
            ("thermal_conductivity", thermal), ("electron_mobility", mobility),
        ):
            if value is None:
                continue
            observation_id = sid(f"phase10:obs:{key}:{property_key}")
            if db.get(MaterialPropertyObservation, observation_id):
                continue
            definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
            if definition is None:
                continue
            unit = {"band_gap": "eV", "breakdown_field": "MV/cm",
                    "thermal_conductivity": "W/(m*K)", "electron_mobility": "cm^2/(V*s)"}[property_key]
            db.add(MaterialPropertyObservation(
                id=observation_id, material_id=material_id,
                property_definition_id=definition.id, value_type="numeric", numeric_value=value,
                unit=unit, conditions={"temperature_k": 525.0}, evidence_id=evidence_id,
                method="Synthetic seed fixture", confidence=1.0, status="active",
                curator_note="SYNTHETIC demonstration value. Not a measurement.",
            ))
    db.commit()

    # ------------------------------------------------------------------------------------------
    # Industrial evidence and maturity for A and B. Candidate C is deliberately left without
    # industrial evidence so an industrial gap is demonstrated alongside the scientific ones.
    # ------------------------------------------------------------------------------------------
    industrial_rows = [
        ("demo-ht-candidate-a", "manufacturing", "process_yield", "Demonstration wafer yield (synthetic)", 0.82, "fraction"),
        ("demo-ht-candidate-a", "regulatory", "restricted_substance", "Restricted-substance listing (synthetic)", None, None),
        ("demo-ht-candidate-a", "economic", "raw_material_cost", "Feedstock cost (synthetic)", 320.0, "USD/kg"),
        ("demo-ht-candidate-a", "supply_chain", "supplier_count", "Qualified supplier count (synthetic)", 6.0, "count"),
        ("demo-ht-candidate-a", "environmental", "embodied_energy", "Embodied energy (synthetic)", 210.0, "MJ/kg"),
        ("demo-ht-candidate-b", "manufacturing", "process_yield", "Demonstration wafer yield (synthetic)", 0.61, "fraction"),
        ("demo-ht-candidate-b", "regulatory", "restricted_substance", "Restricted-substance listing (synthetic)", None, None),
        ("demo-ht-candidate-b", "economic", "raw_material_cost", "Feedstock cost (synthetic)", 780.0, "USD/kg"),
        ("demo-ht-candidate-b", "supply_chain", "supplier_count", "Qualified supplier count (synthetic)", 2.0, "count"),
    ]
    for key, category, metric_key, title, value, unit in industrial_rows:
        row_id = sid(f"phase10:industrial:{key}:{metric_key}")
        if db.get(IndustrialEvidence, row_id):
            continue
        create_industrial_evidence(db, {
            "id": row_id, "organisation_id": org.id, "visibility": "private",
            "material_id": sid(f"material:{key}"), "hypothesis_id": None,
            "category": category, "metric_key": metric_key, "display_label": title,
            "numeric_value": value, "unit": unit,
            "currency": "USD" if unit == "USD/kg" else None,
            "currency_year": 2026 if unit == "USD/kg" else None,
            "cost_basis": "per_kilogram" if unit == "USD/kg" else None,
            "boolean_value": False if metric_key == "restricted_substance" else None,
            "geography": "global", "jurisdiction": "DEMO",
            "source_type": "seed_demonstration",
            "as_of_date": dt_date(2026, 1, 15), "is_estimate": True,
            "notes": SYNTHETIC_NOTE, "metadata_json": {"demo_only": True, "scientific_claim": False},
        })
    db.commit()

    for key, stage in (("demo-ht-candidate-a", "pilot_scale"), ("demo-ht-candidate-b", "laboratory")):
        maturity_id = sid(f"phase10:maturity:{key}")
        if db.get(MaturityAssessment, maturity_id):
            continue
        db.add(MaturityAssessment(
            id=maturity_id, organisation_id=org.id, material_id=sid(f"material:{key}"),
            hypothesis_id=None, stage=stage,
            justification="Demonstration maturity assessment for a synthetic material. "
                          + SYNTHETIC_NOTE,
            assessed_by=user.id,
        ))
    db.commit()

    # ------------------------------------------------------------------------------------------
    # Physical measurements. Candidate A's replicates agree with its observations; Candidate B's
    # replicates CONTRADICT its breakdown-field observation, which is the point of the fixture.
    # ------------------------------------------------------------------------------------------
    instrument_id = sid("phase10:instrument:demo-breakdown-bench")
    if not db.get(Instrument, instrument_id):
        db.add(Instrument(
            id=instrument_id, organisation_id=org.id, key="demo_breakdown_bench",
            display_name="Demonstration breakdown-field bench (fixture)",
            instrument_type="breakdown_field_bench",
            manufacturer="TinkerLab demonstration fixture", model="n/a",
            measures_property_keys=["breakdown_field", "band_gap", "thermal_conductivity"],
            equipment_capabilities=["high voltage supply", "calibrated probe station",
                                    "thermal conductivity bench", "calibrated thermocouples"],
            measurement_unit="MV/cm", stated_uncertainty=0.1, stated_uncertainty_unit="MV/cm",
            calibration_status="calibrated", calibration_date=dt_date(2026, 1, 5),
            calibration_due_date=dt_date(2027, 1, 5),
            calibration_reference="Demonstration calibration record (fixture, not a certificate)",
            integration_kind="manual_entry", status="active",
        ))
        db.flush()
    db.commit()

    protocol_specs = [
        ("breakdown_field", "MV/cm", "Breakdown field measurement (demonstration)"),
        ("band_gap", "eV", "Optical band gap measurement (demonstration)"),
        ("thermal_conductivity", "W/(m*K)", "Steady-state thermal conductivity (demonstration)"),
    ]
    protocol_versions: dict[str, ExperimentProtocolVersion] = {}
    for property_key, unit, display in protocol_specs:
        protocol_id = sid(f"phase10:protocol:{property_key}")
        protocol = db.get(ExperimentProtocol, protocol_id)
        version_id = sid(f"phase10:protocol-version:{property_key}:1.0")
        if protocol is None:
            definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
            protocol = ExperimentProtocol(
                id=protocol_id, organisation_id=org.id, key=f"phase10_{property_key}",
                display_name=display,
                objective=f"Determine {property_key} of a prepared specimen at a stated temperature.",
                property_definition_id=definition.id if definition else None, status="active",
            )
            db.add(protocol)
            db.flush()
            create_protocol_version(
                db, protocol=protocol, version="1.0", created_by=user.id, row_id=version_id,
                values={
                    "objective": f"Determine {property_key} at a stated temperature.",
                    "required_equipment": ["high voltage supply", "calibrated probe station"]
                    if property_key == "breakdown_field"
                    else ["thermal conductivity bench", "calibrated thermocouples"],
                    "sample_requirements": {"geometry": "disc", "min_thickness_m": 0.001},
                    "preparation_steps": [{"step": 1, "description": "Prepare and characterise the specimen."}],
                    "controlled_variables": {"temperature_k": 525.0, "atmosphere": "inert"},
                    "independent_variables": [],
                    "dependent_variables": [{"property_key": property_key, "unit": unit}],
                    "measurement_procedure": [
                        {"step": 1, "description": "Equilibrate the specimen at the measurement temperature."},
                        {"step": 2, "description": "Record the response and its stated uncertainty."},
                    ],
                    "calibration_requirements": {"instrument_calibration_within_days": 365},
                    "acceptance_criteria": {"required_replicates": 2},
                    "safety_notes": "Demonstration protocol only.",
                    "replicate_requirement": 2,
                    "control_requirement": "Include a reference-standard specimen in each session.",
                },
            )
            db.commit()
        version = db.get(ExperimentProtocolVersion, version_id)
        if version is not None:
            protocol_versions[property_key] = version

    synthetic_time = dt_datetime(2026, 2, 10, 9, 0, tzinfo=UTC)
    # Candidate A's measurements agree with its observations. Candidate B's breakdown-field
    # measurements sit far below the 2.0 MV/cm requirement even though its observation claimed 3.3.
    measurement_plan: list[tuple[str, str, tuple[float, float]]] = [
        ("demo-ht-candidate-a", "breakdown_field", (2.75, 2.83)),
        ("demo-ht-candidate-a", "band_gap", (3.24, 3.28)),
        ("demo-ht-candidate-a", "thermal_conductivity", (372.0, 385.0)),
        ("demo-ht-candidate-b", "breakdown_field", (1.10, 1.18)),
        ("demo-ht-candidate-b", "band_gap", (3.38, 3.42)),
        ("demo-ht-candidate-b", "thermal_conductivity", (228.0, 235.0)),
    ]

    for key, property_key, values in measurement_plan:
        version = protocol_versions.get(property_key)
        if version is None:
            continue
        material_id = sid(f"material:{key}")
        sample_id = sid(f"phase10:sample:{key}:{property_key}")
        if not db.get(Sample, sample_id):
            create_sample(db, {
                "organisation_id": org.id,
                "sample_code": f"P10-{key[-1].upper()}-{property_key[:4].upper()}",
                "display_name": f"Demonstration specimen for {key} / {property_key} (synthetic)",
                "sample_kind": "synthesized", "material_id": material_id, "hypothesis_id": None,
                "material_state_id": sid(f"phase10:state:{key}"),
                "batch_reference": f"P10-BATCH-{key[-1].upper()}", "geometry": "disc",
                "dimensions": {"diameter_m": 0.0125, "thickness_m": 0.002},
                "metadata_json": {"surface_finish": "ground"},
                "preparation_date": dt_date(2026, 2, 1), "prepared_by": user.id,
                "storage_conditions": "Desiccator, ambient temperature",
                "provenance_note": "Synthetic specimen record for a synthetic material. No "
                                   "physical specimen exists.",
            }, row_id=sample_id)
            db.commit()

        plan_id = sid(f"phase10:plan:{key}:{property_key}")
        if db.get(ExperimentPlan, plan_id):
            continue
        requirement_key = {
            "breakdown_field": "ht_min_breakdown_field",
            "band_gap": "ht_min_band_gap",
            "thermal_conductivity": "ht_min_thermal_conductivity",
        }[property_key]
        plan, runs = create_plan(
            db, organisation_id=org.id,
            display_name=f"{property_key} replicates for {key} (demonstration)",
            objective=f"Resolve the {property_key} requirement for the demonstration candidate.",
            design_kind="single_run", protocol_version=version, factors=[], replicate_count=2,
            control_plan="Reference standard measured in the same session.",
            project_id=project_id, role_id=role_id,
            requirement_id=sid(f"phase10:requirement:{requirement_key}"),
            candidate_id=candidate_row_ids[key], created_by=user.id, row_id=plan_id,
        )
        created_runs = materialize_plan_runs(
            db, plan=plan, runs=runs, run_code_prefix=f"P10-{key[-1].upper()}-{property_key[:3].upper()}",
            sample_id=sample_id, instrument_id=instrument_id,
        )
        db.commit()

        definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one()
        for run in created_runs:
            run.status = "completed"
            run.started_at = synthetic_time
            run.completed_at = synthetic_time
            run.conditions = {"temperature_k": 525.0, "atmosphere": "inert"}
        db.flush()

        unit = {"breakdown_field": "MV/cm", "band_gap": "eV",
                "thermal_conductivity": "W/(m*K)"}[property_key]
        uncertainty = {"breakdown_field": 0.05, "band_gap": 0.02,
                       "thermal_conductivity": 5.0}[property_key]
        data_runs = [run for run in created_runs if not run.is_control]
        for run, value in zip(data_runs, values, strict=False):
            record_measurement(
                db, organisation_id=org.id, run=run, property_definition=definition,
                numeric_value=value, unit=unit, uncertainty=uncertainty,
                uncertainty_type="standard",
                method=f"Synthetic {property_key} fixture",
                conditions={"temperature_k": 525.0, "atmosphere": "inert"},
                replicate_index=run.replicate_index, measured_at=synthetic_time,
                notes="SYNTHETIC demonstration measurement. No physical measurement was performed.",
            )
        db.commit()

    # ------------------------------------------------------------------------------------------
    # The programme itself
    # ------------------------------------------------------------------------------------------
    program_id = sid("phase10:program")
    if not db.get(ReplacementProgram, program_id):
        program = create_program(
            db, organisation_id=org.id, created_by=user.id, row_id=program_id,
            values={
                "project_id": project_id,
                "key": "ht_silicon_replacement_demo",
                "name": "High-temperature silicon replacement (SYNTHETIC DEMONSTRATION)",
                "description": "Flagship Phase-10 demonstration programme. Every candidate and "
                               "every value in this programme is synthetic.",
                "application_id": application_id,
                "application_component_id": component_id,
                "role_id": role_id,
                "application_name": "High-temperature power electronic switch (demonstration)",
                "application_domain": "power_electronics",
                "application_context": {
                    "component": "high-temperature active switching region",
                    "functional_role": "block voltage when off, conduct when on",
                    "electrical_conditions": {"blocking_voltage_v": 3300.0},
                    "thermal_conditions": {"junction_temperature_k": 525.0},
                    "lifetime_target_hours": 100000,
                    "regulatory_market": "DEMO",
                    "critical_failure_modes": ["avalanche breakdown", "thermal runaway"],
                    "data_labelling": "SYNTHETIC / DEMONSTRATION DATA",
                },
                "incumbent_material_id": silicon_id,
                "incumbent_state_id": silicon_state_id,
                "validation_strategy": {
                    "physical_validation_required_for": ["blocking", "critical"],
                    "minimum_replicates": 2,
                },
                "is_demonstration_data": True,
            },
        )
        refresh_program_state(db, program)
        db.commit()
