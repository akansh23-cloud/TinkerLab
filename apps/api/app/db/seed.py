from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import UTC
from datetime import date as dt_date
from datetime import datetime as dt_datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.entities import (
    Application,
    ApplicationComponent,
    Candidate,
    CandidateHypothesis,
    CandidateHypothesisComponent,
    CandidateSearchSpace,
    Constraint,
    Evidence,
    ExperimentPlan,
    ExperimentProtocol,
    ExperimentProtocolVersion,
    FunctionalRequirement,
    GenerationRun,
    IndustrialConstraint,
    IndustrialEvidence,
    Instrument,
    ManufacturingRoute,
    Material,
    MaterialComponent,
    MaterialFunction,
    MaterialIdentifier,
    MaterialProcessCompatibility,
    MaterialProcessState,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialRole,
    MaterialState,
    MaturityAssessment,
    Mechanism,
    ModelApplicabilityDomain,
    Objective,
    ObservationConditionSet,
    Organisation,
    PredictionModel,
    PredictionModelVersion,
    PredictionRun,
    ProcessingHistory,
    ReasoningEdge,
    RegisteredScientificArtifact,
    ReplacementProject,
    Sample,
    ScientificRepresentation,
    SearchSpaceComponentRule,
    SearchSpaceProcessRule,
    SimulationMethodDefinition,
    SimulationProvider,
    SimulationWorkflow,
    SourceProvider,
    SourceRecord,
    StructuralFeature,
    SubstitutionRule,
    User,
    VirtualExperimentCampaign,
)
from app.db.seed_phase10 import seed_phase10
from app.services.artifact_store import ArtifactStoreError, ingest_file
from app.services.experiments import create_campaign, run_campaign
from app.services.experiments_lab import (
    create_plan,
    create_protocol_version,
    create_sample,
    materialize_plan_runs,
    now_utc,
    record_measurement,
)
from app.services.generation import (
    candidate_fingerprint,
    create_manual_hypothesis,
    execute_generation,
    get_search_space,
    search_space_checksum,
)
from app.services.identity import normalize_identifier
from app.services.industrial import create_industrial_evidence
from app.services.material_states import create_material_state, create_processing_history
from app.services.prediction import (
    artifact_checksum,
    execute_prediction_run,
    feature_schema_checksum,
)
from app.services.reasoning import create_reasoning_edge
from app.services.simulation import (
    METHOD_DEFINITIONS,
    approve_provider_version,
    create_provider_version,
    create_representation,
    create_workflow,
    execute_workflow,
)

# Operator-controlled location of pseudopotentials shipped by the host solver package.
SYSTEM_PSEUDO_DIR = os.environ.get("TINKERLAB_SYSTEM_PSEUDO_DIR", "/usr/share/espresso/pseudo")

NS = uuid.UUID("b76d594b-c7a5-46a2-b836-3c82d33c9bf0")


def sid(name: str) -> str:
    return str(uuid.uuid5(NS, name))


def _require[T](value: T | None, label: str) -> T:
    """Seeding is deterministic; a missing row here means the fixture is corrupt, not merely absent."""
    if value is None:
        raise RuntimeError(f"Deterministic seed invariant broken: {label} was not found")
    return value


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


PROPERTY_DEFINITIONS = [
    ("density", "Density", "density", "kg/m^3", False, "relative", None, 0.03),
    ("tensile_strength", "Tensile strength", "pressure", "MPa", False, "relative", None, 0.05),
    ("yield_strength", "Yield strength", "pressure", "MPa", False, "relative", None, 0.05),
    ("operating_temperature", "Operating temperature", "temperature", "degC", True, "absolute", 8.0, None),
    ("thermal_conductivity", "Thermal conductivity", "thermal_conductivity", "W/(m*K)", False, "relative", None, 0.12),
    ("cost_per_mass", "Material cost", "cost_per_mass", "USD/kg", False, "informational", None, None),
    ("carbon_footprint", "Carbon footprint", "carbon_footprint", "kgCO2e/kg", False, "informational", None, None),
    ("existing_equipment_compatible", "Existing equipment compatible", "boolean", None, False, "absolute", 0.0, None),
    # Phase 6: reduced-unit output of the software-validation simulation fixture. Deliberately
    # dimensionless so the synthetic value can never be read as a physical material energy.
    ("software_fixture_reduced_energy", "Software-fixture reduced energy (synthetic)", "dimensionless", "1", True, "informational", None, None),
    # Reduced-unit MD output. Dimensionless by construction so it can never be confused with a
    # physical energy, and deliberately distinct from the first-principles total_energy key.
    ("md_reduced_potential_energy", "Reduced-unit MD potential energy (dimensionless)", "dimensionless", "1", True, "informational", None, None),
    # First-principles total energy in rydberg. A real physical quantity, produced only by DFT.
    ("total_energy", "First-principles total energy", "energy", "Ry", True, "informational", None, None),
    # Phase 8: semiconductor-relevant property vocabulary. Registering a property key is not a claim
    # that any material has a value for it — no silicon property value is seeded anywhere.
    ("band_gap", "Electronic band gap", "energy", "eV", True, "informational", None, None),
    ("thermal_conductivity", "Thermal conductivity", "thermal_conductivity", "W/(m*K)", True, "informational", None, None),
    ("breakdown_field", "Dielectric breakdown field", "electric_field", "MV/cm", True, "informational", None, None),
    ("electron_mobility", "Electron mobility", "mobility", "cm^2/(V*s)", True, "informational", None, None),
]

MATERIALS = [
    ("demo-polymer-baseline", "Demo Engineering Polymer P-100", "Baseline generic engineering polymer formulation. Demonstration data only.", "Generic polymer blend; exact formulation intentionally synthetic."),
    ("demo-polymer-a", "Candidate A — Lightweight Blend", "Seeded alternative emphasizing lower density and cost. Demonstration data only.", "Generic polymer blend A; demonstration only."),
    ("demo-polymer-b", "Candidate B — High-Temperature Blend", "Seeded alternative emphasizing temperature and strength. Demonstration data only.", "Generic polymer blend B; demonstration only."),
    ("demo-polymer-c", "Candidate C — Incomplete Evidence Blend", "Seeded alternative intentionally missing several observations to test UNKNOWN handling.", "Generic polymer blend C; demonstration only."),
]

OBSERVATIONS = {
    "demo-polymer-baseline": {
        "density": (1420, "kg/m^3", 0.99), "tensile_strength": (68, "MPa", 0.99),
        "operating_temperature": (128, "degC", 0.99), "thermal_conductivity": (0.22, "W/(m*K)", 0.99),
        "cost_per_mass": (5.4, "USD/kg", 0.99), "carbon_footprint": (4.2, "kgCO2e/kg", 0.99),
    },
    "demo-polymer-a": {
        "density": (1310, "kg/m^3", 0.92), "tensile_strength": (74, "MPa", 0.90),
        "operating_temperature": (139, "degC", 0.88), "thermal_conductivity": (0.20, "W/(m*K)", 0.85),
        "cost_per_mass": (4.7, "USD/kg", 0.89), "carbon_footprint": (2.8, "kgCO2e/kg", 0.84),
    },
    "demo-polymer-b": {
        "density": (1380, "kg/m^3", 0.94), "tensile_strength": (82, "MPa", 0.93),
        "operating_temperature": (162, "degC", 0.91), "thermal_conductivity": (0.24, "W/(m*K)", 0.88),
        "cost_per_mass": (6.1, "USD/kg", 0.90), "carbon_footprint": (3.3, "kgCO2e/kg", 0.86),
    },
    "demo-polymer-c": {"density": (1295, "kg/m^3", 0.78), "tensile_strength": (66, "MPa", 0.74), "cost_per_mass": (4.1, "USD/kg", 0.71)},
}


def seed(db: Session) -> None:
    org = Organisation(id=sid("org"), name="TinkerLab Demo Organisation")
    user = User(id=sid("user"), organisation_id=org.id, display_name="Demo Scientist", email="scientist@demo.tinkerlab.local")
    db.merge(org); db.merge(user)

    local_provider = SourceProvider(
        id=sid("provider:local_import"), key="local_import", display_name="TinkerLab Local Import",
        provider_type="user_import", reference_url=None,
        licensing_notes="Data rights remain with the importing organisation; TinkerLab stores provenance and does not infer redistribution rights.",
        enabled=True, adapter_version="2.0",
    )
    demo_provider = SourceProvider(
        id=sid("provider:phase2_demo"), key="phase2_demo", display_name="TinkerLab Phase-2 Demo Dataset",
        provider_type="seed_demo", reference_url=None,
        licensing_notes="Synthetic deterministic fixture only; contains no external scientific claims.", enabled=True, adapter_version="2.0",
    )
    db.merge(local_provider); db.merge(demo_provider)

    numeric_allowed = ["<", "<=", "=", ">=", ">", "between"]
    definitions = {}
    for key, display, quantity, unit, allow_negative, conflict_policy, abs_tol, rel_tol in PROPERTY_DEFINITIONS:
        d = MaterialPropertyDefinition(
            id=sid(f"prop:{key}"), key=key, display_name=display, quantity_type=quantity, canonical_unit=unit,
            description=f"Controlled property definition for {display.lower()}.",
            applicable_material_families=["polymer", "alloy", "composite", "ceramic", "coating", "adhesive"],
            allowed_comparators=["boolean"] if quantity == "boolean" else numeric_allowed, allow_negative=allow_negative,
            conflict_policy=conflict_policy, conflict_absolute_tolerance=abs_tol, conflict_relative_tolerance=rel_tol,
        )
        db.merge(d); definitions[key] = d

    material_by_key = {}
    evidence_by_material = {}
    source_by_material = {}
    for key, display, desc, comp in MATERIALS:
        m = Material(
            id=sid(f"material:{key}"), canonical_name=key, display_name=display, material_family="polymer",
            description=desc, composition_summary=comp, source_type="seed_demo", is_seed_data=True,
            owner_organisation_id=None, visibility="public",
        )
        db.merge(m); material_by_key[key] = m
        raw_payload = {"material_key": key, "dataset": "phase2_demo", "demo_only": True}
        source = SourceRecord(
            id=sid(f"source:{key}"), provider_id=demo_provider.id, organisation_id=None, visibility="public",
            external_record_id=key, source_version="2.0", parser_version="phase2-seed/1.0",
            raw_checksum=digest(raw_payload), normalized_checksum=digest({**raw_payload, "normalized": True}),
            raw_payload=raw_payload, status="normalized", metadata_json={"demo_only": True},
        )
        db.merge(source); source_by_material[key] = source
        e = Evidence(
            id=sid(f"evidence:{key}"), evidence_type="seed_demo", title=f"Demonstration evidence for {display}",
            source_reference="TinkerLab Phase-2 deterministic seed dataset",
            description="Synthetic demonstration values created solely to exercise evidence, condition, conflict, and selection workflows. Not an experimental or literature claim.",
            method="Deterministic seed fixture", confidence=1.0, metadata_json={"demo_only": True, "scientific_claim": False},
            provider_id=demo_provider.id, source_record_id=source.id, visibility="public", status="reviewed", source_quality="demo_fixture",
        )
        db.merge(e); evidence_by_material[key] = e
    db.flush()

    # Multiple identifiers and structured formulation representation.
    identifier_rows = [
        ("demo-polymer-baseline", "tinkerlab", "TL-DEMO-P100", True),
        ("demo-polymer-baseline", "common_name", "Demo P-100", False),
        ("demo-polymer-a", "tinkerlab", "TL-DEMO-A", True),
        ("demo-polymer-b", "tinkerlab", "TL-DEMO-B", True),
        ("demo-polymer-c", "tinkerlab", "TL-DEMO-C", True),
    ]
    for material_key, namespace, value, primary in identifier_rows:
        db.merge(MaterialIdentifier(
            id=sid(f"identifier:{material_key}:{namespace}:{value}"), material_id=material_by_key[material_key].id,
            namespace=namespace, value=value, normalized_value=normalize_identifier(namespace, value), is_primary=primary,
            evidence_id=evidence_by_material[material_key].id, organisation_id=None, visibility="public",
        ))

    component_rows = {
        "demo-polymer-baseline": [("Base Resin A", "base_resin_a", "matrix", 78.0), ("Modifier B", "modifier_b", "modifier", 18.0), ("Reinforcement C", "reinforcement_c", "reinforcement", 4.0)],
        "demo-polymer-a": [("Demo Polymer Matrix A", "demo_matrix_a", "matrix", 84.0), ("Demo Lightweight Filler", "demo_filler_a", "filler", 12.0), ("Demo Additive Package", "demo_additive_a", "additive", 4.0)],
        "demo-polymer-b": [("Demo Heat-Stable Matrix", "demo_matrix_b", "matrix", 76.0), ("Demo Reinforcement", "demo_reinforcement_b", "reinforcement", 20.0), ("Demo Additive Package", "demo_additive_b", "additive", 4.0)],
    }
    for material_key, rows in component_rows.items():
        for seq, (name, identifier, role, amount) in enumerate(rows):
            db.merge(MaterialComponent(
                id=sid(f"component:{material_key}:{seq}"), material_id=material_by_key[material_key].id,
                component_name=name, component_identifier=identifier, component_role=role, amount_value=amount, amount_unit="%", amount_basis="weight_percent",
                evidence_id=evidence_by_material[material_key].id, sequence=seq, notes="Synthetic formulation component for TinkerLab demo workflows.",
            ))
    # Demonstrate proprietary/redacted component support without revealing fake chemistry.
    db.merge(MaterialComponent(
        id=sid("component:demo-polymer-c:redacted"), material_id=material_by_key["demo-polymer-c"].id,
        component_name="Customer-private component", component_role="additive", amount_basis="qualitative",
        is_redacted=True, redaction_label="PRIVATE-COMPONENT-01", sequence=0,
        evidence_id=evidence_by_material["demo-polymer-c"].id, notes="Demonstrates redaction-safe formulation representation.",
    ))

    for key in material_by_key:
        db.merge(MaterialProcessState(
            id=sid(f"state:{key}:molded"), material_id=material_by_key[key].id, state_label="conditioned molded specimen",
            process_name="demo injection molding", sequence=1,
            parameters={"demo_only": True, "details": "synthetic processing state; not a manufacturing protocol"},
            evidence_id=evidence_by_material[key].id, notes="Demonstration process/material state only.",
        ))

    ambient_conditions = {}
    for key in material_by_key:
        condition = ObservationConditionSet(
            id=sid(f"condition:{key}:ambient"), temperature_value=23.0, temperature_unit="degC",
            pressure_value=101.325, pressure_unit="kPa", humidity_percent=50.0,
            material_state="conditioned molded specimen", metadata_json={"demo_only": True},
        )
        db.merge(condition); ambient_conditions[key] = condition

    for material_key, props in OBSERVATIONS.items():
        for prop_key, (numeric_value, unit, confidence) in props.items():
            o = MaterialPropertyObservation(
                id=sid(f"obs:{material_key}:{prop_key}"), material_id=material_by_key[material_key].id,
                property_definition_id=sid(f"prop:{prop_key}"), value_type="numeric", numeric_value=numeric_value, unit=unit,
                conditions={"dataset": "phase2_demo", "note": "synthetic demonstration only"},
                condition_set_id=ambient_conditions[material_key].id,
                evidence_id=evidence_by_material[material_key].id, source_record_id=source_by_material[material_key].id,
                method="Synthetic deterministic fixture", uncertainty=None, confidence=confidence, status="active",
                curator_preferred=(material_key == "demo-polymer-b" and prop_key == "density"),
                curator_note="Preference: seeded curator choice for conflict-review demonstration" if material_key == "demo-polymer-b" and prop_key == "density" else None,
            )
            db.merge(o)

    boolean_observations = {"demo-polymer-baseline": True, "demo-polymer-a": True, "demo-polymer-b": False}
    for material_key, boolean_value in boolean_observations.items():
        db.merge(MaterialPropertyObservation(
            id=sid(f"obs:{material_key}:existing_equipment_compatible"), material_id=material_by_key[material_key].id,
            property_definition_id=sid("prop:existing_equipment_compatible"), value_type="boolean", boolean_value=boolean_value,
            conditions={"dataset": "phase2_demo"}, condition_set_id=ambient_conditions[material_key].id,
            evidence_id=evidence_by_material[material_key].id, source_record_id=source_by_material[material_key].id,
            confidence=0.90, status="active",
        ))

    # Candidate A has a newer-looking high-temperature tensile observation. A 23 C project context must select the ambient record, not this one.
    hot_condition = ObservationConditionSet(
        id=sid("condition:demo-polymer-a:80c"), temperature_value=80.0, temperature_unit="degC",
        pressure_value=101.325, pressure_unit="kPa", humidity_percent=50.0, material_state="conditioned molded specimen",
        metadata_json={"demo_only": True},
    )
    db.merge(hot_condition)
    hot_evidence = Evidence(
        id=sid("evidence:demo-polymer-a:hot"), evidence_type="seed_demo", title="Demo high-temperature tensile observation",
        source_reference="TinkerLab Phase-2 deterministic seed dataset", description="Synthetic evidence at 80 C used to verify condition-aware selection.",
        method="Deterministic seed fixture", confidence=1.0, metadata_json={"demo_only": True}, provider_id=demo_provider.id,
        source_record_id=source_by_material["demo-polymer-a"].id, visibility="public", status="reviewed", source_quality="demo_fixture",
    )
    db.merge(hot_evidence)
    db.merge(MaterialPropertyObservation(
        id=sid("obs:demo-polymer-a:tensile:80c"), material_id=material_by_key["demo-polymer-a"].id,
        property_definition_id=sid("prop:tensile_strength"), value_type="numeric", numeric_value=61.0, unit="MPa",
        condition_set_id=hot_condition.id, evidence_id=hot_evidence.id, source_record_id=source_by_material["demo-polymer-a"].id,
        method="Synthetic deterministic fixture", confidence=0.88, status="active",
    ))

    # Candidate B has two active density observations in the same context that exceed the property-specific conflict tolerance.
    conflict_evidence = Evidence(
        id=sid("evidence:demo-polymer-b:density-conflict"), evidence_type="seed_demo", title="Demo conflicting density observation",
        source_reference="TinkerLab Phase-2 deterministic seed dataset", description="Synthetic disagreement for conflict-policy testing.",
        method="Deterministic seed fixture", confidence=1.0, metadata_json={"demo_only": True}, provider_id=demo_provider.id,
        source_record_id=source_by_material["demo-polymer-b"].id, visibility="public", status="reviewed", source_quality="demo_fixture",
    )
    db.merge(conflict_evidence)
    db.merge(MaterialPropertyObservation(
        id=sid("obs:demo-polymer-b:density:conflict"), material_id=material_by_key["demo-polymer-b"].id,
        property_definition_id=sid("prop:density"), value_type="numeric", numeric_value=1490.0, unit="kg/m^3",
        condition_set_id=ambient_conditions["demo-polymer-b"].id, evidence_id=conflict_evidence.id,
        source_record_id=source_by_material["demo-polymer-b"].id, method="Synthetic deterministic fixture", confidence=0.85, status="active",
    ))

    # Superseded evidence remains stored but is excluded by the selection policy.
    old_cost_evidence = Evidence(
        id=sid("evidence:demo-polymer-a:old-cost"), evidence_type="seed_demo", title="Superseded demo cost record",
        source_reference="TinkerLab Phase-2 deterministic seed dataset", description="Synthetic superseded value retained for provenance testing.",
        method="Deterministic seed fixture", confidence=1.0, metadata_json={"demo_only": True}, provider_id=demo_provider.id,
        source_record_id=source_by_material["demo-polymer-a"].id, visibility="public", status="superseded", source_quality="demo_fixture",
    )
    db.merge(old_cost_evidence)
    db.merge(MaterialPropertyObservation(
        id=sid("obs:demo-polymer-a:old-cost"), material_id=material_by_key["demo-polymer-a"].id,
        property_definition_id=sid("prop:cost_per_mass"), value_type="numeric", numeric_value=5.3, unit="USD/kg",
        condition_set_id=ambient_conditions["demo-polymer-a"].id, evidence_id=old_cost_evidence.id,
        source_record_id=source_by_material["demo-polymer-a"].id, status="active", confidence=0.60,
    ))

    project = ReplacementProject(
        id=sid("project"), organisation_id=org.id, name="Demo Polymer Replacement Study",
        description="Demonstrates condition-aware evidence selection, provenance, unit-aware comparison, conflicts, and PASS/FAIL/UNKNOWN without generative discovery.",
        baseline_material_id=material_by_key["demo-polymer-baseline"].id,
        replacement_reasons=["cost", "sustainability", "performance"], status="active", created_by=user.id,
    )
    db.merge(project)

    constraints = [
        ("density", "<=", 1.35, None, None, "g/cm^3", "hard", 1.0, 5, {}),
        ("tensile_strength", ">=", 70.0, None, None, "MPa", "hard", 1.0, 5, {"conditions": {"temperature": {"value": 23.0, "unit": "degC"}, "material_state": "conditioned molded specimen"}}),
        ("operating_temperature", ">=", 135.0, None, None, "degC", "hard", 1.0, 5, {}),
        ("cost_per_mass", "<=", 5.0, None, None, "USD/kg", "hard", 1.0, 4, {}),
        ("carbon_footprint", "<=", 3.0, None, None, "kgCO2e/kg", "soft", 0.8, 3, {}),
        ("thermal_conductivity", ">=", 0.21, None, None, "W/(m*K)", "soft", 0.4, 2, {}),
        ("existing_equipment_compatible", "boolean", None, None, True, None, "hard", 1.0, 5, {}),
    ]
    for i, (key, comp, val, upper, boolean, unit, strength, weight, severity, metadata) in enumerate(constraints):
        db.merge(Constraint(
            id=sid(f"constraint:{i}"), project_id=project.id, constraint_type="boolean" if comp == "boolean" else "property",
            property_key=key, comparator=comp, target_value=val, target_value_upper=upper, target_boolean=boolean,
            target_unit=unit, severity=severity, hard_or_soft=strength, weight=weight,
            description="Deterministic Phase-2 demonstration constraint.", metadata_json={"demo_only": True, **metadata},
        ))

    objectives = [("density", "minimize", 0.6, 2), ("cost_per_mass", "minimize", 0.8, 1), ("tensile_strength", "maximize", 0.7, 3)]
    for i, (key, direction, weight, priority) in enumerate(objectives):
        db.merge(Objective(id=sid(f"objective:{i}"), project_id=project.id, property_key=key, direction=direction, weight=weight, priority=priority, description="Deterministic Phase-2 demonstration objective."))

    for i, key in enumerate(["demo-polymer-a", "demo-polymer-b", "demo-polymer-c"]):
        db.merge(Candidate(id=sid(f"candidate:{i}"), project_id=project.id, candidate_kind="known_material", material_id=material_by_key[key].id, hypothesis_id=None, candidate_source="seed_demo", status="proposed", notes="Demonstration known-material candidate only; not generated by AI and not experimentally validated."))
    db.commit()
    project = _require(db.get(ReplacementProject, project.id), "seed project")
    org = _require(db.get(Organisation, org.id), "seed organisation")
    user = _require(db.get(User, user.id), "seed user")

    # Phase 3: bounded, deterministic candidate-generation demonstration. No generated hypothesis receives property observations.
    space_id = sid("phase3:search-space:v1")
    if not db.get(CandidateSearchSpace, space_id):
        space = CandidateSearchSpace(
            id=space_id, project_id=project.id, organisation_id=org.id, version=1, material_family="polymer", amount_basis="weight_percent",
            balance_component_key="base_resin_a", total_target=100.0, total_tolerance=0.001, max_component_count=8,
            candidate_budget=20, maximum_enumeration=500, notes="Synthetic Phase-3 search space. Generic labels only.", active=True, checksum="pending",
            metadata_json={"demo_only": True, "scientific_claim": False},
        )
        db.add(space); db.flush()
        component_cfg = [
            ("base_resin_a", "Base Resin A", "matrix", 0, False, False, True, False, None, None, None),
            ("modifier_b", "Modifier B", "modifier", 1, False, True, False, False, 16.0, 20.0, 2.0),
            ("reinforcement_c", "Reinforcement C", "reinforcement", 2, True, False, True, False, None, None, None),
            ("restricted_demo_component", "Restricted Demo Component", "restricted", 3, False, False, False, True, None, None, None),
        ]
        baseline_component_ids = {
            "base_resin_a": sid("component:demo-polymer-baseline:0"),
            "modifier_b": sid("component:demo-polymer-baseline:1"),
            "reinforcement_c": sid("component:demo-polymer-baseline:2"),
        }
        for key, name, role, seq, locked, mutable, required, prohibited, lo, hi, step in component_cfg:
            db.add(SearchSpaceComponentRule(
                id=sid(f"phase3:search-rule:{key}"), search_space_id=space.id, baseline_component_id=baseline_component_ids.get(key),
                component_key=key, display_name=name, role=role, locked=locked, mutable=mutable, required=required, prohibited=prohibited,
                min_amount=lo, max_amount=hi, step_amount=step, amount_unit="%" if not prohibited else None, amount_basis="weight_percent" if not prohibited else None,
                sequence=seq, metadata_json={"demo_only": True},
            ))
        db.add(SearchSpaceProcessRule(
            id=sid("phase3:process-rule:generic_temperature"), search_space_id=space.id, parameter_key="generic_process_temperature",
            display_name="Generic process temperature", min_value=100.0, max_value=120.0, step_value=10.0, unit="degC", locked=False,
            metadata_json={"demo_only": True, "not_operational_instruction": True},
        ))
        db.flush()
        space = _require(get_search_space(db, space.id), "seed search space"); space.checksum = search_space_checksum(space); db.commit()

    rules = [
        ("valid-b2", "modifier_b2", "Alternative Modifier B2", "Curator-approved synthetic alternative used only to demonstrate substitution lineage."),
        ("duplicate-b2", "modifier_b2", "Alternative Modifier B2", "Second approved synthetic rule intentionally creates the same scientific hypothesis to demonstrate deduplication."),
        ("rejected-prohibited", "restricted_demo_component", "Restricted Demo Component", "Approved demo rule intentionally conflicts with the active prohibited-component search constraint to demonstrate structural rejection."),
    ]
    for suffix, replacement_key, replacement_name, reason in rules:
        db.merge(SubstitutionRule(
            id=sid(f"phase3:sub-rule:{suffix}"), organisation_id=org.id, project_id=project.id, material_family="polymer",
            source_component_key="modifier_b", replacement_component_key=replacement_key, replacement_display_name=replacement_name,
            allowed_min_amount=16.0, allowed_max_amount=20.0, amount_basis="weight_percent", reason=reason, evidence_id=None, status="approved", version=1,
        ))
    db.commit()

    # One manual hypothesis passes through the same fingerprint/lineage integrity model.
    manual_components = [
        {"component_key": "base_resin_a", "display_name": "Base Resin A", "role": "matrix", "amount": 79.0, "unit": "%", "basis": "weight_percent", "source_baseline_component_id": sid("component:demo-polymer-baseline:0"), "substitution_rule_id": None, "locked": False, "metadata": {"demo_only": True}},
        {"component_key": "modifier_b", "display_name": "Modifier B", "role": "modifier", "amount": 17.0, "unit": "%", "basis": "weight_percent", "source_baseline_component_id": sid("component:demo-polymer-baseline:1"), "substitution_rule_id": None, "locked": False, "metadata": {"demo_only": True}},
        {"component_key": "reinforcement_c", "display_name": "Reinforcement C", "role": "reinforcement", "amount": 4.0, "unit": "%", "basis": "weight_percent", "source_baseline_component_id": sid("component:demo-polymer-baseline:2"), "substitution_rule_id": None, "locked": True, "metadata": {"demo_only": True}},
    ]
    manual_fp = candidate_fingerprint("polymer", manual_components, [])
    if not db.query(CandidateHypothesis).filter_by(project_id=project.id, deterministic_fingerprint=manual_fp).one_or_none():
        create_manual_hypothesis(db, project, "Manual hypothesis — modest modifier reduction", "polymer", manual_components, [], "Synthetic manual hypothesis for Phase-3 UI and lineage testing.")

    run_id = sid("phase3:generation-run:curated-substitution")
    if not db.get(GenerationRun, run_id):
        space = _require(get_search_space(db, space_id), "seed search space")
        execute_generation(db, project, space, "curated_component_substitution", 314159, 20, {"demo_only": True}, user.id, run_id=run_id)
    db.commit()

    # Phase 4: transparent synthetic prediction model. This is software-validation infrastructure, not real materials science.
    prediction_model_id = sid("phase4:model:demo-polymer-tensile")
    prediction_version_id = sid("phase4:model-version:demo-polymer-tensile:v1")
    demo_artifact = {
        "model_kind": "linear",
        "intercept": 58.0,
        "coefficients": {
            "matrix_fraction_pct": 0.05,
            "primary_modifier_fraction_pct": 0.30,
            "alternative_modifier_fraction_pct": 0.70,
            "reinforcement_fraction_pct": 1.00,
        },
        "uncertainty": {"method": "fixed_validation_interval", "half_width": 2.0, "stddev": 1.2, "coverage": 0.90},
        "demo_only": True,
    }
    demo_schema = {
        "features": {
            "matrix_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "primary_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "alternative_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "total_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "reinforcement_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "component_count": {"type": "integer", "required": True},
        },
        "origin": "synthetic generic-polymer fixture",
    }
    model = db.get(PredictionModel, prediction_model_id)
    if not model:
        model = PredictionModel(
            id=prediction_model_id, organisation_id=None, key="demo-polymer-tensile-linear",
            display_name="Demo Polymer Tensile Predictor",
            description="Transparent deterministic synthetic model used only to validate TinkerLab prediction provenance, applicability and uncertainty workflows.",
            model_type="transparent_demo_linear", owner_provider="TinkerLab synthetic fixture", status="approved",
            supported_material_families=["polymer"], supported_property_keys=["tensile_strength"],
            metadata_json={"demo_only": True, "scientific_claim": False},
        )
        db.add(model); db.flush()
    version = db.get(PredictionModelVersion, prediction_version_id)
    if not version:
        from datetime import datetime
        version = PredictionModelVersion(
            id=prediction_version_id, model_id=model.id, version="1.0.0-demo", predictor_key="demo_linear_json", predictor_contract_version="1.0",
            artifact_format="tinkerlab_linear_json_v1", artifact_payload=demo_artifact, artifact_checksum=artifact_checksum("tinkerlab_linear_json_v1", demo_artifact),
            feature_schema_version="polymer-demo-v1", feature_schema=demo_schema, feature_schema_checksum=feature_schema_checksum("polymer-demo-v1", demo_schema),
            target_property_key="tensile_strength", canonical_output_unit="MPa", uncertainty_method="fixed_validation_interval",
            applicability_policy_version="applicability-v1",
            training_data_descriptor={"kind": "synthetic_deterministic_fixture", "real_material_data": False, "purpose": "software validation only"},
            training_data_checksum=digest({"synthetic_fixture": "phase4-demo-v1"}),
            calibration_metrics={"coverage_target": 0.90, "interval_half_width_MPa": 2.0, "synthetic_only": True},
            validation_metrics={"mae_MPa": 1.25, "rmse_MPa": 1.55, "interval_coverage": 0.90, "synthetic_only": True},
            approved_at=datetime.now(UTC),
            immutable_metadata={"demo_only": True, "warning": "DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions."},
        )
        db.add(version); db.flush()
        db.add(ModelApplicabilityDomain(
            id=sid("phase4:applicability:demo-polymer-tensile:v1"), model_version_id=version.id, material_families=["polymer"],
            required_feature_keys=["matrix_fraction_pct", "primary_modifier_fraction_pct", "alternative_modifier_fraction_pct", "total_modifier_fraction_pct", "reinforcement_fraction_pct", "component_count"],
            numeric_feature_ranges={
                "matrix_fraction_pct": [70.0, 90.0], "primary_modifier_fraction_pct": [0.0, 25.0],
                "alternative_modifier_fraction_pct": [0.0, 25.0], "total_modifier_fraction_pct": [10.0, 25.0],
                "reinforcement_fraction_pct": [0.0, 10.0], "component_count": [2.0, 8.0],
            },
            allowed_categorical_values={}, required_component_keys=[],
            target_condition_ranges={"temperature": {"min": 20.0, "max": 30.0, "unit": "degC", "required": True, "borderline_tolerance": 1.0}},
            redacted_input_policy="reject", domain_distance_method=None, domain_distance_config={}, borderline_tolerance=0.5,
            metadata_json={"demo_only": True},
        ))
        db.commit()

    default_run_id = sid("phase4:prediction-run:demo-tensile")
    if not db.get(PredictionRun, default_run_id):
        valid_sub = (
            db.query(CandidateHypothesis).join(CandidateHypothesisComponent)
            .filter(CandidateHypothesis.project_id == project.id, CandidateHypothesis.structural_validity == "valid", CandidateHypothesisComponent.component_key == "modifier_b2")
            .order_by(CandidateHypothesis.id).first()
        )
        targets = [
            {"material_id": material_by_key["demo-polymer-baseline"].id},
            {"material_id": material_by_key["demo-polymer-c"].id},
        ]
        if valid_sub:
            targets.insert(1, {"hypothesis_id": valid_sub.id})
        execute_prediction_run(
            db, project, version, targets, "tensile_strength",
            {"temperature": {"value": 23.0, "unit": "degC"}}, "MPa", {"demo_only": True}, user.id, org.id, run_id=default_run_id,
        )
    db.commit()

    # Phase 5: second transparent synthetic model for a two-objective virtual-evaluation fixture.
    density_model_id = sid("phase5:model:demo-polymer-density")
    density_version_id = sid("phase5:model-version:demo-polymer-density:v1")
    density_artifact = {
        "model_kind": "linear",
        "intercept": 820.0,
        "coefficients": {
            "matrix_fraction_pct": 3.8,
            "primary_modifier_fraction_pct": 3.0,
            "alternative_modifier_fraction_pct": 8.0,
            "reinforcement_fraction_pct": 9.0,
        },
        "uncertainty": {"method": "fixed_validation_interval", "half_width": 20.0, "stddev": 12.0, "coverage": 0.90},
        "demo_only": True,
    }
    density_schema = {
        "features": {
            "matrix_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "primary_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "alternative_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "total_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "reinforcement_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "component_count": {"type": "integer", "required": True},
        },
        "origin": "synthetic generic-polymer Phase-5 fixture",
    }
    density_model = db.get(PredictionModel, density_model_id)
    if not density_model:
        density_model = PredictionModel(
            id=density_model_id, organisation_id=None, key="demo-polymer-density-linear", display_name="Demo Polymer Density Predictor",
            description="Transparent deterministic synthetic model used only to exercise multi-objective optimization infrastructure.",
            model_type="transparent_demo_linear", owner_provider="TinkerLab synthetic fixture", status="approved",
            supported_material_families=["polymer"], supported_property_keys=["density"], metadata_json={"demo_only": True, "scientific_claim": False},
        )
        db.add(density_model); db.flush()
    density_version = db.get(PredictionModelVersion, density_version_id)
    if not density_version:
        from datetime import datetime
        density_version = PredictionModelVersion(
            id=density_version_id, model_id=density_model.id, version="1.0.0-demo", predictor_key="demo_linear_json", predictor_contract_version="1.0",
            artifact_format="tinkerlab_linear_json_v1", artifact_payload=density_artifact, artifact_checksum=artifact_checksum("tinkerlab_linear_json_v1", density_artifact),
            feature_schema_version="polymer-demo-v1", feature_schema=density_schema, feature_schema_checksum=feature_schema_checksum("polymer-demo-v1", density_schema),
            target_property_key="density", canonical_output_unit="kg/m^3", uncertainty_method="fixed_validation_interval", applicability_policy_version="applicability-v1",
            training_data_descriptor={"kind": "synthetic_deterministic_fixture", "real_material_data": False, "purpose": "software validation only"},
            training_data_checksum=digest({"synthetic_fixture": "phase5-density-demo-v1"}),
            calibration_metrics={"coverage_target": 0.90, "interval_half_width_kg_m3": 20.0, "synthetic_only": True},
            validation_metrics={"mae_kg_m3": 11.0, "rmse_kg_m3": 14.0, "interval_coverage": 0.90, "synthetic_only": True},
            approved_at=datetime.now(UTC),
            immutable_metadata={"demo_only": True, "warning": "DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions."},
        )
        db.add(density_version); db.flush()
        db.add(ModelApplicabilityDomain(
            id=sid("phase5:applicability:demo-polymer-density:v1"), model_version_id=density_version.id, material_families=["polymer"],
            required_feature_keys=["matrix_fraction_pct", "primary_modifier_fraction_pct", "alternative_modifier_fraction_pct", "total_modifier_fraction_pct", "reinforcement_fraction_pct", "component_count"],
            numeric_feature_ranges={
                "matrix_fraction_pct": [70.0, 90.0], "primary_modifier_fraction_pct": [0.0, 25.0],
                "alternative_modifier_fraction_pct": [0.0, 25.0], "total_modifier_fraction_pct": [10.0, 25.0],
                "reinforcement_fraction_pct": [0.0, 10.0], "component_count": [2.0, 8.0],
            },
            allowed_categorical_values={}, required_component_keys=[], target_condition_ranges={}, redacted_input_policy="reject",
            domain_distance_method=None, domain_distance_config={}, borderline_tolerance=0.5, metadata_json={"demo_only": True},
        ))
        db.commit()

    # Phase 5 deterministic virtual campaign. Virtual evaluations are model-backed only and create no material observations.
    campaign_id = sid("phase5:virtual-campaign:demo-robust-pareto")
    if not db.get(VirtualExperimentCampaign, campaign_id):
        constraint_policies = [
            {
                "constraint_id": sid("constraint:0"), "model_version_id": density_version_id,
                "allowed_value_origin": "known_evidence_then_prediction", "unknown_handling": "retain_uncertain",
                "condition_mapping": {}, "enabled": True, "metadata": {"demo_only": True},
            },
            {
                "constraint_id": sid("constraint:1"), "model_version_id": prediction_version_id,
                "allowed_value_origin": "known_evidence_then_prediction", "unknown_handling": "retain_uncertain",
                "condition_mapping": {"temperature": {"value": 23.0, "unit": "degC"}}, "enabled": True, "metadata": {"demo_only": True},
            },
        ]
        payload = {
            "id": campaign_id,
            "name": "Demo Robust Pareto Virtual Campaign",
            "description": "Synthetic Phase-5 campaign validating bounded multi-objective optimization and uncertainty propagation only.",
            "search_space_id": space_id, "policy_key": "robust_pareto_v1", "random_seed": 271828,
            "max_iterations": 2, "max_total_new_candidates": 12, "max_candidates_per_iteration": 6, "max_parents_per_iteration": 3,
            "created_by": user.id,
            "objectives": [
                {"property_key": "tensile_strength", "direction": "maximize", "weight": 1.0, "priority": 1, "target_value": None, "target_unit": None, "model_version_id": prediction_version_id, "evaluation_mode": "model_prediction", "metadata": {"conditions": {"temperature": {"value": 23.0, "unit": "degC"}}, "demo_only": True}},
                {"property_key": "density", "direction": "minimize", "weight": 1.0, "priority": 2, "target_value": None, "target_unit": None, "model_version_id": density_version_id, "evaluation_mode": "model_prediction", "metadata": {"demo_only": True}},
            ],
            "constraint_policies": constraint_policies, "initial_candidate_ids": [], "include_known_candidates": True,
            "exploration_enabled": True, "mutation_types": ["component_amount", "component_substitution", "process_parameter"],
            "convergence_unchanged_iterations": None, "metadata": {"demo_only": True, "scientific_claim": False},
        }
        campaign = create_campaign(db, project, payload)
        run_campaign(db, campaign, max_iterations=2)
    db.commit()

    # Phase 6 — simulation OS fixtures. Simulation results are a third origin and create no observations.
    _seed_phase6(db, org, user, project)

    # Phase 7 — industrial viability fixtures. Industrial evidence is a separate claim class again.
    _seed_phase7(db, org, user, project)

    # Phase 8 — functional decomposition. Generic engine, semiconductor demonstration data.
    _seed_phase8(db, org, user, project)

    # Phase 9 — experimental records. Synthetic measurements on a synthetic candidate only.
    _seed_phase9(db, org, user, project)

    # Phase 10 — a complete, clearly-labelled synthetic replacement programme end to end.
    seed_phase10(db, org, user, sid)


def _seed_phase6(db: Session, org: Organisation, user: User, project: ReplacementProject) -> None:
    """Phase-6 deterministic simulation fixtures.

    Seeds exactly what is honest on a clean machine: an executable software-validation fixture with
    one converged workflow; LAMMPS/QE registry entries whose availability is probed, never assumed;
    interface-only CALPHAD/MLFF boundaries; a formulation-only representation whose atomistic routes
    must refuse; and a textbook diamond-carbon cell that stays route-blocked until a pseudopotential
    is registered. No unsourced real material property is seeded to make the lab look impressive.
    """
    for method in METHOD_DEFINITIONS:
        if not db.query(SimulationMethodDefinition).filter_by(key=method["key"]).one_or_none():
            db.add(SimulationMethodDefinition(
                id=sid(f"phase6:method:{method['key']}"), key=method["key"], display_name=method["display_name"],
                method_family=method["method_family"], purpose=method["purpose"], description=method["description"],
                required_representation_types=method["required_representation_types"],
                required_parameters=method["required_parameters"], optional_parameters=method["optional_parameters"],
                output_schema=method["output_schema"], output_property_keys=method["output_property_keys"],
                output_units=method["output_units"], convergence_semantics=method["convergence_semantics"],
                known_limitations=method["known_limitations"], fidelity=method["fidelity"], status="approved",
            ))
    db.flush()

    provider_specs = [
        ("software_fixture_harmonic", "Software-Validation Harmonic Fixture", "software_fixture", "analytical_fixture",
         "software_fixture_harmonic_v1", "Deterministic in-process reduced-unit fixture. Validates the Simulation OS, not materials science."),
        ("lammps_local", "LAMMPS (local, reviewed boundary)", "local_executable", "md",
         "lammps_local_v1", "Reviewed LAMMPS adapter boundary. Unavailable unless an allowlisted binary and an approved potential exist."),
        ("quantum_espresso_local", "Quantum ESPRESSO pw.x (local, reviewed boundary)", "local_executable", "dft",
         "quantum_espresso_local_v1", "Reviewed periodic-DFT boundary. Unavailable without pw.x and approved checksummed pseudopotentials."),
        ("calphad_interface", "CALPHAD (interface only)", "software_fixture", "calphad",
         "calphad_interface_v1", "Interface-only in Phase 6: no reviewed thermodynamic database, therefore no numerical result."),
        ("ml_force_field_interface", "ML force field (interface only)", "software_fixture", "ml_force_field_future",
         "ml_force_field_interface_v1", "Interface-only in Phase 6: no licensed registered weights, therefore provider unavailable."),
    ]
    version_ids: dict[str, str] = {}
    for key, name, ptype, family, adapter_key, description in provider_specs:
        provider_id = sid(f"phase6:provider:{key}")
        provider = db.get(SimulationProvider, provider_id)
        if not provider:
            provider = SimulationProvider(
                id=provider_id, organisation_id=None, key=key, display_name=name, provider_type=ptype,
                method_family=family, description=description, status="approved",
                safety_class="reviewed_code_registered",
                approved_execution_mode="in_process_fixture" if ptype == "software_fixture" else "allowlisted_local_subprocess",
                metadata_json={"phase": 6},
            )
            db.add(provider); db.flush()
        version_id = sid(f"phase6:provider-version:{key}:v1")
        version_ids[key] = version_id
        if not provider.versions:
            version = create_provider_version(db, provider, {
                "id": version_id, "version": "1.0", "adapter_key": adapter_key,
                "immutable_metadata": {"seeded": True, "phase": 6},
            })
            db.flush()
            approve_provider_version(db, version)
    db.commit()

    # A reduced-unit LJ potential fixture for the LAMMPS boundary: synthetic, clearly labelled,
    # nothing downloaded, no real force field claimed.
    artifact_id = sid("phase6:artifact:lj-reduced-fixture:1.0")
    if not db.get(RegisteredScientificArtifact, artifact_id):
        # Real content, ingested into the controlled store: the MD route consumes this file, so a
        # missing or tampered artifact fails the job instead of falling back to inline defaults.
        lj_body = (
            "# TinkerLab reduced-unit Lennard-Jones software-validation potential (synthetic).\n"
            "# epsilon = 1.0, sigma = 1.0 in LJ reduced units. Not a real material force field.\n"
            "pair_coeff * * 1.0 1.0\n"
        )
        lj_path = Path(tempfile.gettempdir()) / "tinkerlab_lj_reduced_fixture.in"
        lj_path.write_text(lj_body)
        lj_checksum, lj_bytes = ingest_file(lj_path)
        db.add(RegisteredScientificArtifact(
            id=artifact_id, organisation_id=None, key="lj_reduced_fixture", version="1.0",
            display_name="Reduced-unit Lennard-Jones software-validation potential (synthetic)",
            artifact_type="force_field", applies_to_method_families=["md"], applies_to_elements=[],
            applies_to_component_keys=[],
            content_checksum=lj_checksum, content_bytes=lj_bytes,
            storage_reference=f"artifact-store://{lj_checksum}", content_available=True,
            license_name="TinkerLab synthetic fixture", license_permits_redistribution=True,
            source_reference="Deterministic reduced-unit fixture; contains no external scientific claims.",
            status="approved",
            metadata_json={"synthetic": True, "file_name": "lj_reduced_fixture.in"},
        ))
    db.commit()

    # --- Real crystalline silicon target -------------------------------------------------------
    # Silicon is the reference semiconductor target. The crystal structure below is the textbook
    # conventional diamond-cubic cell (a = 5.431 angstrom); the pseudopotential, if present, is the
    # one shipped by the operating-system Quantum ESPRESSO package. No property VALUE is seeded for
    # silicon here: structure and pseudopotential are inputs, not scientific claims.
    silicon_id = sid("material:silicon")
    if not db.get(Material, silicon_id):
        db.add(Material(
            id=silicon_id, canonical_name="silicon", display_name="Silicon (crystalline, diamond cubic)",
            material_family="crystalline_inorganic",
            description="Elemental crystalline silicon in the diamond-cubic structure. Seeded as a "
                        "structural target for physics routing; no measured property value is asserted here.",
            composition_summary="Si", source_type="seed_reference", is_seed_data=True,
            owner_organisation_id=None, visibility="public",
        ))
        db.flush()
    silicon_repr_id = sid("phase6:representation:silicon-conventional-cell")
    if not db.get(ScientificRepresentation, silicon_repr_id):
        a = 5.431
        basis = [(0.0, 0.0, 0.0), (0.25, 0.25, 0.25), (0.0, 0.5, 0.5), (0.25, 0.75, 0.75),
                 (0.5, 0.0, 0.5), (0.75, 0.25, 0.75), (0.5, 0.5, 0.0), (0.75, 0.75, 0.25)]
        create_representation(
            db, organisation_id=org.id, material_id=silicon_id, hypothesis_id=None,
            label="Silicon conventional diamond-cubic cell (a = 5.431 A)",
            representation_format="periodic_structure_json_v1",
            content={
                "lattice_vectors": [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, a]],
                "lattice_unit": "angstrom", "space_group_number": 227,
                "sites": [{"element": "Si", "fractional_coordinates": list(c)} for c in basis],
            },
            visibility="private",
            provenance_note="Textbook conventional cell for diamond-cubic silicon, Fd-3m, a = 5.431 angstrom. "
                            "A structural input for routing and simulation; not a measured property claim.",
            row_id=silicon_repr_id,
        )

    # Ingest the operating-system Quantum ESPRESSO pseudopotential when one is actually present.
    # If it is absent the artifact is simply not registered and DFT routes keep refusing — the
    # seed never pretends a pseudopotential exists.
    for element, candidate_names in (("Si", ("Si.pz-vbc.UPF",)),):
        source_path = next(
            (p for p in (Path(SYSTEM_PSEUDO_DIR) / name for name in candidate_names) if p.is_file()), None
        )
        if source_path is None:
            continue
        artifact_id = sid(f"phase6:artifact:qe-pseudo:{element}")
        if db.get(RegisteredScientificArtifact, artifact_id):
            continue
        try:
            content_checksum, content_bytes = ingest_file(source_path)
        except ArtifactStoreError:
            continue
        db.add(RegisteredScientificArtifact(
            id=artifact_id, organisation_id=None, key=f"qe_pseudo_{element.lower()}", version="1.0",
            display_name=f"Quantum ESPRESSO norm-conserving pseudopotential for {element} ({source_path.name})",
            artifact_type="pseudopotential", applies_to_method_families=["dft"],
            applies_to_elements=[element], applies_to_component_keys=[],
            content_checksum=content_checksum, content_bytes=content_bytes,
            storage_reference=f"artifact-store://{content_checksum}", content_available=True,
            license_name="GPL (as distributed with the Quantum ESPRESSO package)",
            license_permits_redistribution=False,
            source_reference=f"Shipped with the host Quantum ESPRESSO installation at {source_path}. "
                             "Ingested locally by the operator; never downloaded by TinkerLab.",
            status="approved", metadata_json={"file_name": source_path.name, "ingested_from_host_package": True},
        ))
    db.commit()

    baseline_id = sid("material:demo-polymer-baseline")
    fixture_repr_id = sid("phase6:representation:fixture-harmonic")
    if not db.get(ScientificRepresentation, fixture_repr_id):
        create_representation(
            db, organisation_id=org.id, material_id=baseline_id, hypothesis_id=None,
            label="Software-validation harmonic fixture (synthetic demo target)",
            representation_format="software_fixture_json_v1",
            content={"fixture_key": "harmonic_demo_v1",
                     "parameters": {"stiffness": 4.0, "initial_displacement": 1.5, "linear_bias": 2.0, "energy_offset": 0.75}},
            visibility="private",
            provenance_note="Deterministic synthetic fixture attached to the demo baseline purely to exercise the Simulation OS.",
            metadata={"synthetic": True}, row_id=fixture_repr_id,
        )
    formulation_repr_id = sid("phase6:representation:baseline-formulation-only")
    if not db.get(ScientificRepresentation, formulation_repr_id):
        components = db.query(MaterialComponent).filter_by(material_id=baseline_id).order_by(MaterialComponent.sequence).all()
        create_representation(
            db, organisation_id=org.id, material_id=baseline_id, hypothesis_id=None,
            label="Formulation-level composition (baseline polymer)",
            representation_format="formulation_summary_json_v1",
            content={"components": [
                {"component_key": c.component_name.lower().replace(" ", "_"), "display_name": c.component_name,
                 "amount": c.amount_value, "unit": c.amount_unit, "basis": c.amount_basis, "is_redacted": c.is_redacted}
                for c in components
            ] or [{"component_key": "generic_polymer_blend", "display_name": "Generic polymer blend", "amount": None}]},
            visibility="private",
            provenance_note="Mirrors the Phase-2 structured composition. Demonstrates that formulation-only targets are refused by atomistic routes.",
            row_id=formulation_repr_id,
        )
    diamond_repr_id = sid("phase6:representation:diamond-carbon-cell")
    if not db.get(ScientificRepresentation, diamond_repr_id):
        create_representation(
            db, organisation_id=org.id, material_id=baseline_id, hypothesis_id=None,
            label="Conventional diamond-carbon cell (routing demonstration only)",
            representation_format="periodic_structure_json_v1",
            content={
                "lattice_vectors": [[3.567, 0.0, 0.0], [0.0, 3.567, 0.0], [0.0, 0.0, 3.567]],
                "lattice_unit": "angstrom", "space_group_number": 227,
                "sites": [
                    {"element": "C", "fractional_coordinates": [0.0, 0.0, 0.0]},
                    {"element": "C", "fractional_coordinates": [0.25, 0.25, 0.25]},
                    {"element": "C", "fractional_coordinates": [0.0, 0.5, 0.5]},
                    {"element": "C", "fractional_coordinates": [0.25, 0.75, 0.75]},
                    {"element": "C", "fractional_coordinates": [0.5, 0.0, 0.5]},
                    {"element": "C", "fractional_coordinates": [0.75, 0.25, 0.75]},
                    {"element": "C", "fractional_coordinates": [0.5, 0.5, 0.0]},
                    {"element": "C", "fractional_coordinates": [0.75, 0.75, 0.25]},
                ],
            },
            visibility="private",
            provenance_note="Textbook conventional diamond cell (Fd-3m, a = 3.567 angstrom). Demonstrates DFT routing gates; "
                            "no pseudopotential is registered, so the QE route stays missing_registered_artifact and no calculation is claimed.",
            row_id=diamond_repr_id,
        )
    db.commit()

    # Atomistic topology for the reduced-unit MD route: four LJ particles in a periodic box.
    # Explicitly a software-validation configuration in reduced units, not a real molecular model.
    topology_repr_id = sid("phase6:representation:lj-reduced-topology")
    if not db.get(ScientificRepresentation, topology_repr_id):
        create_representation(
            db, organisation_id=org.id, material_id=baseline_id, hypothesis_id=None,
            label="Reduced-unit Lennard-Jones test topology (software validation)",
            representation_format="atomistic_topology_json_v1",
            content={
                "atom_types": [{"id": 1, "label": "lj_particle", "mass_amu": 1.0}],
                "atoms": [
                    {"id": 1, "type": 1, "position": [1.0, 1.0, 1.0]},
                    {"id": 2, "type": 1, "position": [2.1, 1.0, 1.0]},
                    {"id": 3, "type": 1, "position": [1.0, 2.2, 1.0]},
                    {"id": 4, "type": 1, "position": [1.0, 1.0, 2.3]},
                ],
                "bonds": [], "box": [10.0, 10.0, 10.0], "periodicity": "periodic",
                "force_field_key": "lj_reduced_fixture",
            },
            visibility="private",
            provenance_note="Reduced-unit LJ configuration used to exercise the MD adapter end to end. "
                            "Dimensionless; it models no real substance.",
            row_id=topology_repr_id,
        )
    db.commit()

    # One deterministic, converged software-fixture workflow: routing, snapshot, job, artifacts,
    # parser, convergence, checksums and a clearly synthetic property estimate.
    workflow_id = sid("phase6:workflow:fixture-harmonic-demo")
    if not db.get(SimulationWorkflow, workflow_id):
        workflow = create_workflow(
            db, organisation_id=org.id, created_by=user.id, target_kind="known_material", target_id=baseline_id,
            method_key="software_fixture_energy_minimization_v1",
            provider_version_id=version_ids["software_fixture_harmonic"],
            parameters={"step_size": 0.1, "max_iterations": 500, "gradient_tolerance": 1e-8},
            project_id=project.id, metadata={"seeded": True, "synthetic": True}, workflow_id=workflow_id,
        )
        execute_workflow(db, workflow)
    db.commit()


def _seed_phase7(db: Session, org: Organisation, user: User, project: ReplacementProject) -> None:
    """Phase-7 industrial demonstration fixtures.

    Every industrial record below is labelled ``seed_demonstration`` and carries an explicit
    as-of date, currency, basis and jurisdiction. The NUMBERS ARE SYNTHETIC: they exist to exercise
    comparability, staleness, conflict and constraint logic, and they are not a claim about the real
    cost, supply or regulatory status of any material. Real industrial data must be ingested through
    a source provider with its own provenance.
    """
    silicon_id = sid("material:silicon")
    baseline_id = sid("material:demo-polymer-baseline")

    routes = [
        ("czochralski_growth", "Czochralski single-crystal growth", "synthesis",
         ["crystalline_inorganic"], ["Si", "Ge"], ["crystal puller", "quartz crucible"],
         1600.0, 1800.0, "high", "industrially_established"),
        ("cvd_thin_film", "Chemical vapour deposition (thin film)", "deposition",
         ["crystalline_inorganic", "ceramic"], [], ["CVD reactor", "gas handling"],
         800.0, 1400.0, "high", "industrially_established"),
        ("injection_moulding", "Polymer injection moulding", "forming",
         ["polymer"], [], ["injection moulding machine", "tooling"],
         420.0, 570.0, "medium", "industrially_established"),
    ]
    route_ids: dict[str, str] = {}
    for key, name, family, families, elements, equipment, t_min, t_max, capex, maturity in routes:
        route_id = sid(f"phase7:route:{key}")
        route_ids[key] = route_id
        if db.get(ManufacturingRoute, route_id):
            continue
        db.add(ManufacturingRoute(
            id=route_id, organisation_id=None, visibility="public", key=key, display_name=name,
            process_family=family, applies_to_material_families=families, applies_to_elements=elements,
            required_equipment=equipment, process_temperature_k_min=t_min, process_temperature_k_max=t_max,
            capex_class=capex, process_maturity=maturity, scale_up_maturity=maturity,
            description=f"Demonstration route definition for {name}. Process windows are illustrative.",
            known_limitations=["Seed demonstration route: process windows are illustrative, not qualified."],
            status="active", metadata_json={"demo_only": True},
        ))
    db.flush()

    # Compatibility verdicts, each with a stated reason. Silicon/Czochralski is declared compatible;
    # silicon/injection-moulding is declared incompatible; the polymer baseline's CVD compatibility
    # is deliberately left UNRECORDED so the engine must report INSUFFICIENT_EVIDENCE rather than
    # assuming either answer.
    compatibilities = [
        (silicon_id, "czochralski_growth", "compatible",
         "Czochralski growth is the established route for single-crystal silicon boules."),
        (silicon_id, "injection_moulding", "incompatible",
         "Injection moulding applies to thermoplastics; it cannot produce a covalent crystalline semiconductor."),
        (baseline_id, "injection_moulding", "compatible",
         "The baseline is a thermoplastic blend suited to injection moulding."),
    ]
    for material_id, route_key, verdict, rationale in compatibilities:
        compat_id = sid(f"phase7:compat:{route_key}:{material_id}")
        if db.get(MaterialProcessCompatibility, compat_id):
            continue
        db.add(MaterialProcessCompatibility(
            id=compat_id, organisation_id=org.id, route_id=route_ids[route_key], material_id=material_id,
            compatibility=verdict, rationale=rationale, conditions={},
            as_of_date=dt_date(2025, 6, 1),
        ))
    db.flush()

    # Industrial evidence. Synthetic values, real structure.
    evidence_rows = [
        # (target, category, metric, label, value, unit, currency, year, basis, geo, juris, as_of, bool, cat, estimate)
        (silicon_id, "economic", "raw_material_cost", "Electronic-grade feedstock cost (synthetic)",
         28.0, "USD/kg", "USD", 2025, "per_kilogram", "global", None, dt_date(2025, 3, 1), None, None, False),
        (silicon_id, "supply_chain", "supplier_count", "Qualified supplier count (synthetic)",
         6.0, "count", None, None, None, "global", None, dt_date(2025, 1, 15), None, None, False),
        (silicon_id, "supply_chain", "geographic_concentration_hhi", "Production concentration HHI (synthetic)",
         0.34, "index", None, None, None, "global", None, dt_date(2025, 1, 15), None, None, True),
        (silicon_id, "environmental", "embodied_energy", "Embodied energy (synthetic)",
         1400.0, "MJ/kg", None, None, None, "global", None, dt_date(2024, 9, 1), None, None, True),
        (silicon_id, "regulatory", "restricted_substance", "Restricted-substance listing (synthetic)",
         None, None, None, None, None, None, "EU", dt_date(2025, 2, 1), False, None, False),
        (baseline_id, "economic", "raw_material_cost", "Baseline resin cost (synthetic)",
         4.2, "USD/kg", "USD", 2025, "per_kilogram", "global", None, dt_date(2025, 3, 1), None, None, False),
        (baseline_id, "supply_chain", "supplier_count", "Qualified supplier count (synthetic)",
         2.0, "count", None, None, None, "global", None, dt_date(2025, 1, 15), None, None, False),
        (baseline_id, "regulatory", "restricted_substance", "Restricted-substance listing (synthetic)",
         None, None, None, None, None, None, "EU", dt_date(2025, 2, 1), False, None, False),
        # A second cost record for the baseline on a DIFFERENT currency-year basis. It is deliberately
        # NOT comparable with the 2025 record, and the engine must refuse to compare rather than convert.
        (baseline_id, "economic", "raw_material_cost", "Baseline resin cost, older basis (synthetic)",
         3.1, "USD/kg", "USD", 2019, "per_kilogram", "global", None, dt_date(2019, 6, 1), None, None, False),
    ]
    for (target, category, metric, label, value, unit, currency, year, basis, geo, juris,
         as_of, boolean_value, categorical, estimate) in evidence_rows:
        evidence_id = sid(f"phase7:evidence:{target}:{metric}:{as_of}:{year}")
        if db.get(IndustrialEvidence, evidence_id):
            continue
        row = create_industrial_evidence(db, {
            "id": evidence_id, "organisation_id": org.id, "visibility": "private",
            "material_id": target, "hypothesis_id": None, "category": category, "metric_key": metric,
            "display_label": label, "numeric_value": value, "unit": unit, "currency": currency,
            "currency_year": year, "cost_basis": basis, "geography": geo, "jurisdiction": juris,
            "as_of_date": as_of, "boolean_value": boolean_value, "categorical_value": categorical,
            "source_type": "seed_demonstration", "is_estimate": estimate,
            "source_reference": "TinkerLab Phase-7 deterministic seed dataset. Synthetic value; not a "
                                "claim about any real market, supply chain or regulatory status.",
            "notes": "Demonstration data only.", "metadata_json": {"demo_only": True, "scientific_claim": False},
        })
        del row
    db.commit()

    # Maturity: silicon is industrially established for its established route; the polymer baseline
    # is deliberately left without a maturity assessment so the engine reports UNKNOWN honestly.
    maturity_id = sid("phase7:maturity:silicon")
    if not db.get(MaturityAssessment, maturity_id):
        db.add(MaturityAssessment(
            id=maturity_id, organisation_id=org.id, material_id=silicon_id,
            stage="industrially_established", scope="Single-crystal wafer production via Czochralski growth",
            justification="Demonstration assessment: single-crystal silicon wafer manufacture is an "
                          "established industrial process with a recorded compatible route. Seeded to "
                          "exercise maturity ordering; it is not an independently sourced judgement.",
            supporting_evidence_ids=[], assessed_by=user.id, as_of_date=dt_date(2025, 6, 1),
        ))
    db.commit()

    # Project industrial constraints exercising each evaluator, including one whose evidence is
    # deliberately absent so the assessment must report INSUFFICIENT_EVIDENCE.
    constraints: list[tuple[Any, ...]] = [
        ("economic", "max_value", "raw_material_cost", "Raw material cost at or below 30 USD/kg (2025 basis)",
         "hard", 30.0, None, "USD/kg", "USD", 2025, "per_kilogram", [], [], [], None, None),
        ("supply_chain", "supplier_diversity", "supplier_count", "At least three qualified suppliers",
         "hard", None, None, None, None, None, None, [], [], [], None, 3),
        ("regulatory", "allowed_jurisdiction", None, "No EU restricted-substance listing",
         "hard", None, None, None, None, None, None, [], ["EU"], [], None, None),
        ("manufacturing", "required_process_compatibility", None, "Must be producible by an existing route",
         "hard", None, None, None, None, None, None, [], [], ["czochralski_growth"], None, None),
        ("maturity", "minimum_maturity", None, "At least pilot demonstrated",
         "soft", None, None, None, None, None, None, [], [], [], "pilot_demonstrated", None),
        ("environmental", "max_value", "embodied_energy", "Embodied energy at or below 2000 MJ/kg",
         "soft", 2000.0, None, "MJ/kg", None, None, None, [], [], [], None, None),
        ("environmental", "max_value", "water_use", "Process water use at or below 50 L/kg",
         "soft", 50.0, None, "L/kg", None, None, None, [], [], [], None, None),
    ]
    for (category, kind, metric, label, strength, value, upper, unit, currency, year, basis,
         banned, jurisdictions, routes_required, min_maturity, min_suppliers) in constraints:
        constraint_key = str(metric or label)
        constraint_id = sid(f"phase7:constraint:{project.id}:{kind}:{constraint_key}")
        if db.get(IndustrialConstraint, constraint_id):
            continue
        db.add(IndustrialConstraint(
            id=constraint_id, organisation_id=org.id, project_id=project.id, category=category,
            constraint_kind=kind, metric_key=metric, display_label=label, strength=strength,
            target_value=value, target_value_upper=upper, target_unit=unit, currency=currency,
            currency_year=year, cost_basis=basis, banned_elements=banned,
            allowed_jurisdictions=jurisdictions, required_route_keys=routes_required,
            minimum_maturity=min_maturity, minimum_supplier_count=min_suppliers,
            treat_missing_evidence_as="insufficient_evidence",
            rationale="Demonstration industrial constraint seeded to exercise the viability engine.",
            metadata_json={"demo_only": True},
        ))
    db.commit()


def _seed_phase8(db: Session, org: Organisation, user: User, project: ReplacementProject) -> None:
    """Phase-8 functional decomposition fixtures: a silicon replacement study for power electronics.

    This exists to prove the engine is GENERIC. There is no branch anywhere in the engine on
    'silicon' or 'semiconductor'; this seed only supplies data through the same public API shape any
    other domain would use. The requirement thresholds below are illustrative engineering targets
    for the demonstration, and NO property value is seeded for any candidate — so the reasoning
    engine must honestly report UNKNOWN wherever evidence is genuinely absent.
    """
    silicon_id = sid("material:silicon")
    silicon_repr_id = sid("phase6:representation:silicon-conventional-cell")

    # --- Material state: what silicon actually IS in this role -----------------------------------
    history_id = sid("phase8:history:czochralski-undoped")
    if not db.get(ProcessingHistory, history_id):
        create_processing_history(
            db, organisation_id=org.id, key="czochralski_undoped",
            display_name="Czochralski growth, undoped, as-grown",
            description="Illustrative processing route for the demonstration study.",
            steps=[
                {"step_kind": "other", "display_name": "Czochralski single-crystal growth",
                 "temperature_k": 1687.0, "atmosphere": "argon",
                 "notes": "Melt growth of a single-crystal boule."},
                {"step_kind": "annealing", "display_name": "Post-growth anneal",
                 "temperature_k": 1073.0, "duration_s": 3600.0, "atmosphere": "argon"},
            ],
            row_id=history_id,
        )
        db.commit()

    state_id = sid("phase8:state:silicon-single-crystal-300k")
    if not db.get(MaterialState, state_id):
        create_material_state(
            db, organisation_id=org.id, material_id=silicon_id,
            label="Single-crystal silicon, diamond cubic, undoped, 300 K",
            description="Reference state for the power-electronics demonstration study.",
            composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0}],
            representation_id=silicon_repr_id, crystal_system="cubic", space_group_number=227,
            space_group_symbol="Fd-3m", polymorph="diamond_cubic", phase="solid",
            processing_history_id=history_id, temperature_k=300.0, pressure_pa=101325.0,
            environment="inert", is_reference_state=True,
            provenance_note="Declared reference state. The structure comes from the seeded conventional "
                            "cell; conditions are the study's stated operating point.",
            row_id=state_id,
        )
        db.commit()

    # --- Application decomposition ----------------------------------------------------------------
    application_id = sid("phase8:application:power-electronics-switch")
    if not db.get(Application, application_id):
        db.add(Application(
            id=application_id, organisation_id=org.id, visibility="private",
            key="power_electronic_switch", display_name="Power electronic switching device",
            domain="power_electronics",
            description="Demonstration application used to exercise generic functional decomposition.",
            operating_conditions={"junction_temperature_k": 425.0, "blocking_voltage_v": 1200.0},
            status="active",
        ))
        db.flush()

    component_id = sid("phase8:component:active-region")
    if not db.get(ApplicationComponent, component_id):
        db.add(ApplicationComponent(
            id=component_id, application_id=application_id, key="active_region",
            display_name="Active switching region",
            description="The region that must block voltage when off and conduct when on.",
            operating_conditions={"junction_temperature_k": 425.0},
        ))
        db.flush()

    role_id = sid("phase8:role:switching-material")
    if not db.get(MaterialRole, role_id):
        db.add(MaterialRole(
            id=role_id, component_id=component_id, key="switching_material",
            display_name="Switching material",
            description="The material occupying the active region. A replacement must preserve what "
                        "this material DOES here, not merely resemble it chemically.",
            incumbent_material_id=silicon_id, incumbent_state_id=state_id,
        ))
        db.flush()
    db.commit()

    # --- Functions and requirements ----------------------------------------------------------------
    # Illustrative engineering targets for the demonstration. They are requirement thresholds, which
    # are statements of what the application needs — not measurements of any material.
    functions: list[tuple[str, str, str, int, list[tuple[Any, ...]]]] = [
        ("block_electric_field", "Withstand electric field when off", "electronic", 5, [
            ("min_breakdown_field", "Breakdown field at least 0.3 MV/cm", "hard_constraint",
             "minimum", "breakdown_field", 0.3, None, "MV/cm",
             "The active region must not break down under the blocking voltage."),
        ]),
        ("limit_leakage_at_temperature", "Limit leakage at junction temperature", "electronic", 5, [
            ("min_band_gap", "Band gap at least 1.0 eV", "hard_constraint",
             "minimum", "band_gap", 1.0, None, "eV",
             "A wider gap suppresses thermally generated carriers at elevated junction temperature."),
        ]),
        ("conduct_heat_away", "Conduct heat out of the active region", "thermal", 4, [
            ("min_thermal_conductivity", "Thermal conductivity at least 100 W/(m*K)", "soft_constraint",
             "minimum", "thermal_conductivity", 100.0, None, "W/(m*K)",
             "Heat must leave the junction fast enough to hold the operating temperature."),
        ]),
        ("carry_current", "Carry on-state current", "electronic", 3, [
            ("maximise_electron_mobility", "Higher electron mobility is preferred", "objective",
             "maximize", "electron_mobility", None, None, "cm^2/(V*s)",
             "Mobility sets on-state resistance; it is ranked rather than passed or failed."),
        ]),
    ]
    for fkey, fname, category, criticality, requirements in functions:
        function_id = sid(f"phase8:function:{fkey}")
        if not db.get(MaterialFunction, function_id):
            db.add(MaterialFunction(
                id=function_id, role_id=role_id, key=fkey, display_name=fname, category=category,
                criticality=criticality,
                description="Demonstration function for the generic decomposition engine.",
                operating_conditions={"junction_temperature_k": 425.0},
            ))
            db.flush()
        for (rkey, rname, kind, direction, property_key, target, upper, unit, rationale) in requirements:
            requirement_id = sid(f"phase8:requirement:{rkey}")
            if db.get(FunctionalRequirement, requirement_id):
                continue
            definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
            db.add(FunctionalRequirement(
                id=requirement_id, function_id=function_id, key=rkey, display_name=rname,
                requirement_kind=kind, direction=direction,
                property_definition_id=definition.id if definition else None,
                property_key=property_key, target_value=target, target_value_upper=upper,
                target_unit=unit, conditions={"temperature_k": 425.0},
                rationale=rationale + " Illustrative demonstration threshold.",
            ))
    db.commit()

    # --- A synthetic comparison candidate ----------------------------------------------------------
    # Silicon deliberately keeps NO seeded property values: the engine reports UNKNOWN for it, which
    # is the honest state of this database and a useful demonstration in itself. To exercise the
    # PASS / FAIL / STATE_MISMATCH branches without asserting anything about a real substance, a
    # clearly synthetic candidate is seeded with explicitly synthetic observations.
    candidate_id = sid("material:demo-wide-gap-synthetic")
    if not db.get(Material, candidate_id):
        db.add(Material(
            id=candidate_id, canonical_name="demo-wide-gap-synthetic",
            display_name="Demonstration wide-gap semiconductor (SYNTHETIC — not a real material)",
            material_family="crystalline_inorganic",
            description="A fictitious material invented solely to exercise the reasoning engine's "
                        "pass/fail/state-mismatch branches. It does not exist and its values are not "
                        "measurements of anything.",
            composition_summary="Xx (fictitious)", source_type="seed_demo", is_seed_data=True,
            owner_organisation_id=org.id, visibility="private",
        ))
        db.flush()

    demo_evidence_id = sid("phase8:evidence:demo-wide-gap")
    if not db.get(Evidence, demo_evidence_id):
        db.add(Evidence(
            id=demo_evidence_id, evidence_type="seed_demo",
            title="Synthetic demonstration values for the reasoning engine",
            source_reference="TinkerLab Phase-8 deterministic seed dataset",
            description="Fabricated values for a fabricated material. Present only so that PASS, FAIL "
                        "and STATE_MISMATCH outcomes can be demonstrated and tested. Not a scientific claim.",
            method="Deterministic seed fixture", confidence=1.0,
            metadata_json={"demo_only": True, "scientific_claim": False},
        ))
        db.flush()

    demo_state_id = sid("phase8:state:demo-wide-gap-300k")
    if not db.get(MaterialState, demo_state_id):
        create_material_state(
            db, organisation_id=org.id, material_id=candidate_id,
            label="Demonstration wide-gap candidate, 300 K (synthetic)",
            composition=[{"element": "Si", "role": "host", "stoichiometry": 1.0},
                         {"element": "C", "role": "host", "stoichiometry": 1.0}],
            polymorph="demo_polytype", phase="solid", temperature_k=300.0,
            is_reference_state=True,
            provenance_note="Synthetic state for a synthetic material; exists only to exercise state matching.",
            row_id=demo_state_id,
        )
        db.commit()

    # Synthetic observations: band gap PASSES the 1.0 eV requirement, thermal conductivity FAILS the
    # 100 W/(m*K) requirement. Breakdown field is deliberately left absent so one requirement stays
    # honestly UNKNOWN even for the candidate that has data.
    demo_observations = [
        ("band_gap", 3.2, "eV"),
        ("thermal_conductivity", 12.0, "W/(m*K)"),
        ("electron_mobility", 900.0, "cm^2/(V*s)"),
    ]
    for property_key, value, unit in demo_observations:
        observation_id = sid(f"phase8:obs:demo-wide-gap:{property_key}")
        if db.get(MaterialPropertyObservation, observation_id):
            continue
        definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
        if definition is None:
            continue
        db.add(MaterialPropertyObservation(
            id=observation_id, material_id=candidate_id, property_definition_id=definition.id,
            value_type="numeric", numeric_value=value, unit=unit, conditions={"temperature_k": 300.0},
            evidence_id=demo_evidence_id, method="Synthetic seed fixture", confidence=1.0,
            status="active", curator_note="SYNTHETIC demonstration value. Not a measurement.",
        ))
    db.commit()

    # --- Structural features, mechanisms and the reasoning graph -------------------------------------
    features = [
        ("covalent_tetrahedral_network", "Covalent tetrahedral bonding network", "atomic",
         "Four-coordinate covalent network characteristic of the diamond-cubic lattice."),
        ("indirect_band_structure", "Indirect electronic band structure", "electronic",
         "Conduction band minimum displaced from the valence band maximum in k-space."),
    ]
    for key, name, scale, description in features:
        feature_id = sid(f"phase8:feature:{key}")
        if not db.get(StructuralFeature, feature_id):
            db.add(StructuralFeature(id=feature_id, organisation_id=org.id, key=key,
                                     display_name=name, feature_scale=scale, description=description))
    mechanisms = [
        ("phonon_thermal_transport", "Phonon-mediated thermal transport", "thermal",
         "Heat carried by lattice vibrations; limited by phonon scattering."),
        ("thermal_carrier_generation", "Thermal generation of charge carriers across the gap", "electronic",
         "Carrier population generated thermally, controlled by the band gap and temperature."),
        ("avalanche_breakdown", "Impact-ionisation avalanche breakdown", "electronic",
         "Carrier multiplication under high field leading to breakdown."),
    ]
    for key, name, category, description in mechanisms:
        mechanism_id = sid(f"phase8:mechanism:{key}")
        if not db.get(Mechanism, mechanism_id):
            db.add(Mechanism(id=mechanism_id, organisation_id=org.id, key=key, display_name=name,
                             category=category, description=description))
    db.flush()

    # Graph edges. Each carries a scope and a source reference: an unsourced causal claim is refused
    # by create_reasoning_edge, so nothing here is a bare assertion.
    edges = [
        ("state_exhibits_feature", "material_state", state_id,
         "structural_feature", sid("phase8:feature:covalent_tetrahedral_network"),
         "The diamond-cubic reference state exhibits a covalent tetrahedral network.",
         "Diamond-cubic single-crystal states", 0.9),
        ("state_exhibits_feature", "material_state", state_id,
         "structural_feature", sid("phase8:feature:indirect_band_structure"),
         "The reference state exhibits an indirect band structure.",
         "Diamond-cubic silicon", 0.9),
        ("feature_enables_mechanism", "structural_feature", sid("phase8:feature:covalent_tetrahedral_network"),
         "mechanism", sid("phase8:mechanism:phonon_thermal_transport"),
         "A stiff covalent network supports phonon-mediated thermal transport.",
         "Covalent network solids", 0.8),
        ("feature_enables_mechanism", "structural_feature", sid("phase8:feature:indirect_band_structure"),
         "mechanism", sid("phase8:mechanism:thermal_carrier_generation"),
         "The band structure sets the gap that governs thermal carrier generation.",
         "Semiconducting states", 0.8),
        ("feature_enables_mechanism", "structural_feature", sid("phase8:feature:indirect_band_structure"),
         "mechanism", sid("phase8:mechanism:avalanche_breakdown"),
         "Band structure and gap influence impact-ionisation thresholds.",
         "Semiconducting states", 0.6),
        ("mechanism_governs_property", "mechanism", sid("phase8:mechanism:phonon_thermal_transport"),
         "property", "thermal_conductivity",
         "Phonon transport governs thermal conductivity in a non-metallic crystal.",
         "Non-metallic crystalline solids", 0.85),
        ("mechanism_governs_property", "mechanism", sid("phase8:mechanism:thermal_carrier_generation"),
         "property", "band_gap",
         "Thermal carrier generation is governed by the band gap.",
         "Semiconductors", 0.9),
        ("mechanism_governs_property", "mechanism", sid("phase8:mechanism:avalanche_breakdown"),
         "property", "breakdown_field",
         "Avalanche breakdown determines the dielectric breakdown field.",
         "Semiconductors under high field", 0.8),
    ]
    for (edge_kind, from_kind, from_id, to_kind, to_id, note, scope, confidence) in edges:
        existing = db.query(ReasoningEdge).filter_by(
            edge_kind=edge_kind, from_kind=from_kind, from_id=from_id, to_kind=to_kind, to_id=to_id
        ).one_or_none()
        if existing:
            continue
        create_reasoning_edge(db, {
            "organisation_id": org.id, "edge_kind": edge_kind, "from_kind": from_kind,
            "from_id": from_id, "to_kind": to_kind, "to_id": to_id, "relationship_note": note,
            "scope": scope, "confidence": confidence, "source_type": "seed_demonstration",
            "source_reference": "TinkerLab Phase-8 demonstration graph. These are standard textbook "
                                "structure-property relationships recorded as scoped, declared links; "
                                "they are not derived from a literature extraction pipeline.",
            "conditions": {},
        })
    db.commit()


def _seed_phase9(db: Session, org: Organisation, user: User, project: ReplacementProject) -> None:
    """Phase-9 experimental fixtures.

    The measurements below are SYNTHETIC, attached to the synthetic demonstration candidate, and
    labelled as such. No measurement is fabricated for silicon or any real material: TinkerLab has
    not measured anything, and the seed must not imply otherwise.

    The fixture deliberately produces a measurement that DISAGREES with the existing observation on
    the same property, so the prediction-versus-experiment machinery and the conflicting-evidence
    path are both exercised rather than merely declared.
    """
    candidate_id = sid("material:demo-wide-gap-synthetic")
    role_id = sid("phase8:role:switching-material")

    # --- Instrument. Calibration is recorded, with a reference; it is never assumed. ------------
    instrument_id = sid("phase9:instrument:demo-thermal-bench")
    if not db.get(Instrument, instrument_id):
        db.add(Instrument(
            id=instrument_id, organisation_id=org.id, key="demo_thermal_bench",
            display_name="Demonstration thermal conductivity bench (fixture)",
            instrument_type="thermal_conductivity_bench",
            manufacturer="TinkerLab demonstration fixture", model="n/a",
            measures_property_keys=["thermal_conductivity"],
            equipment_capabilities=["thermal conductivity bench", "calibrated thermocouples"],
            measurement_unit="W/(m*K)",
            stated_uncertainty=2.0, stated_uncertainty_unit="W/(m*K)",
            calibration_status="calibrated", calibration_date=dt_date(2025, 5, 1),
            calibration_due_date=dt_date(2026, 5, 1),
            calibration_reference="Demonstration calibration record (fixture, not a real certificate)",
            integration_kind="manual_entry", status="active",
        ))
        db.flush()

    # --- Protocol, versioned. A second version proves editing creates a new frozen version. -----
    protocol_id = sid("phase9:protocol:thermal-conductivity")
    protocol = db.get(ExperimentProtocol, protocol_id)
    if not protocol:
        definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one_or_none()
        protocol = ExperimentProtocol(
            id=protocol_id, organisation_id=org.id, key="thermal_conductivity_steady_state",
            display_name="Steady-state thermal conductivity measurement (demonstration)",
            objective="Determine thermal conductivity of a prepared specimen at a stated temperature.",
            property_definition_id=definition.id if definition else None, status="active",
        )
        db.add(protocol)
        db.flush()
        create_protocol_version(
            db, protocol=protocol, version="1.0", created_by=user.id,
            row_id=sid("phase9:protocol-version:thermal-conductivity:1.0"),
            values={
                "objective": "Determine thermal conductivity at a stated temperature using a "
                             "steady-state method on a geometrically characterised specimen.",
                "required_equipment": ["thermal conductivity bench", "calibrated thermocouples"],
                "sample_requirements": {"geometry": "disc", "min_thickness_m": 0.001,
                                        "surface_finish": "ground"},
                "preparation_steps": [
                    {"step": 1, "description": "Grind faces parallel and record thickness."},
                    {"step": 2, "description": "Equilibrate the specimen at the measurement temperature."},
                ],
                "controlled_variables": {"temperature_k": 300.0, "atmosphere": "air"},
                "independent_variables": [],
                "dependent_variables": [{"property_key": "thermal_conductivity", "unit": "W/(m*K)"}],
                "measurement_procedure": [
                    {"step": 1, "description": "Establish a steady temperature gradient across the specimen."},
                    {"step": 2, "description": "Record heat flux and gradient once steady state is reached."},
                    {"step": 3, "description": "Compute conductivity and record the stated uncertainty."},
                ],
                "calibration_requirements": {"instrument_calibration_within_days": 365},
                "acceptance_criteria": {"steady_state_drift_max_k_per_min": 0.05,
                                        "required_replicates": 2},
                "safety_notes": "Demonstration protocol. Follow local safety procedure for hot surfaces.",
                "replicate_requirement": 2,
                "control_requirement": "Include a reference-standard specimen in each session.",
            },
        )
        db.commit()

    # --- Sample with complete provenance ---------------------------------------------------------
    sample_id = sid("phase9:sample:demo-wide-gap-001")
    if not db.get(Sample, sample_id):
        create_sample(db, {
            "organisation_id": org.id, "sample_code": "DEMO-WG-001",
            "display_name": "Demonstration wide-gap specimen 001 (synthetic)",
            "sample_kind": "synthesized", "material_id": candidate_id, "hypothesis_id": None,
            "material_state_id": sid("phase8:state:demo-wide-gap-300k"),
            "batch_reference": "DEMO-BATCH-A", "geometry": "disc",
            "dimensions": {"diameter_m": 0.0125, "thickness_m": 0.002},
            "metadata_json": {"surface_finish": "ground"},
            "preparation_date": dt_date(2025, 6, 15), "prepared_by": user.id,
            "storage_conditions": "Desiccator, ambient temperature",
            "provenance_note": "Synthetic specimen record for a synthetic material. No physical "
                               "specimen exists; this exercises sample provenance handling.",
        }, row_id=sample_id)
        db.commit()

    # --- A sample with DELIBERATELY incomplete provenance ----------------------------------------
    # Its measurements must be marked INCOMPLETE_PROVENANCE rather than admitted as evidence.
    orphan_sample_id = sid("phase9:sample:orphan")
    if not db.get(Sample, orphan_sample_id):
        create_sample(db, {
            "organisation_id": org.id, "sample_code": "DEMO-ORPHAN-001",
            "display_name": "Specimen with missing provenance (demonstration)",
            "sample_kind": "unknown", "material_id": candidate_id, "hypothesis_id": None,
            "provenance_note": "Deliberately incomplete: no state, no batch, no preparation date. "
                               "Demonstrates that such a specimen's measurements are not admitted.",
        }, row_id=orphan_sample_id)
        db.commit()

    # --- Plan, runs and measurements ---------------------------------------------------------------
    plan_id = sid("phase9:plan:thermal-replicates")
    version = db.get(ExperimentProtocolVersion, sid("phase9:protocol-version:thermal-conductivity:1.0"))
    if not db.get(ExperimentPlan, plan_id) and version is not None:
        plan, runs = create_plan(
            db, organisation_id=org.id, display_name="Thermal conductivity, two replicates (demonstration)",
            objective="Resolve the outstanding thermal conductivity requirement for the demonstration candidate.",
            design_kind="single_run", protocol_version=version, factors=[], replicate_count=2,
            control_plan="Reference standard measured in the same session.",
            project_id=project.id, role_id=role_id,
            requirement_id=sid("phase8:requirement:min_thermal_conductivity"),
            created_by=user.id, row_id=plan_id,
        )
        created_runs = materialize_plan_runs(
            db, plan=plan, runs=runs, run_code_prefix="DEMO-TC",
            sample_id=sample_id, instrument_id=instrument_id,
        )
        db.commit()

        definition = db.query(MaterialPropertyDefinition).filter_by(key="thermal_conductivity").one()
        # Freeze the synthetic run date inside the fixture calibration window. The extra control run
        # materialized by Phase 9.1-B is completed in the same synthetic session so the protocol's
        # control requirement is actually represented in the execution record.
        synthetic_time = dt_datetime(2025, 6, 20, 10, 0, tzinfo=UTC)
        for run in created_runs:
            run.status = "completed"
            run.started_at = synthetic_time
            run.completed_at = synthetic_time
            run.conditions = {"temperature_k": 300.0, "atmosphere": "air"}
        db.flush()

        # Two replicates that agree with each other but DISAGREE with the earlier synthetic
        # observation of 12.0 W/(m*K). The system must expose that disagreement, not average it.
        data_runs = [run for run in created_runs if not run.is_control]
        for run, value in zip(data_runs, (41.0, 43.0), strict=False):
            record_measurement(
                db, organisation_id=org.id, run=run, property_definition=definition,
                numeric_value=value, unit="W/(m*K)", uncertainty=2.0, uncertainty_type="standard",
                method="Steady-state comparative method (synthetic fixture)",
                conditions={"temperature_k": 300.0, "atmosphere": "air"},
                replicate_index=run.replicate_index, measured_at=synthetic_time,
                notes="SYNTHETIC demonstration measurement. No physical measurement was performed.",
            )
        db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
        print("Seed complete: deterministic Phases 1–9.1 demonstration data loaded; synthetic and fixture evidence remains explicitly labelled.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
