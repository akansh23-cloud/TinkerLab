"""Phase-6 Simulation Operating System orchestration.

Responsibilities: provider/version lifecycle, the conservative scientific router, deterministic
input snapshots, code-registered workflow templates, bounded execution, parsing, convergence
assessment and property extraction.

Invariants enforced here and asserted by tests:

  * a simulation NEVER creates a ``MaterialPropertyObservation`` or a ``PropertyPrediction``;
  * a property estimate exists only when the scientific status is ``converged``;
  * an unavailable provider, missing artifact or inadequate representation produces a typed refusal,
    never a number;
  * route previews persist nothing;
  * checksums depend on scientific content only — not on timestamps, display names or row ids.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.domain.enums import (
    RepresentationType,
    SimulationArtifactType,
    SimulationJobStatus,
    SimulationRouteStatus,
    SimulationScientificStatus,
    SimulationValueSelectionPolicy,
    SimulationWorkflowStatus,
)
from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    Material,
    MaterialPropertyDefinition,
    RegisteredScientificArtifact,
    ScientificRepresentation,
    SimulationArtifact,
    SimulationInputSnapshot,
    SimulationJob,
    SimulationMethodDefinition,
    SimulationPropertyEstimate,
    SimulationProvider,
    SimulationProviderVersion,
    SimulationResult,
    SimulationRoute,
    SimulationSelectionPolicyRecord,
    SimulationWorkflow,
    SimulationWorkflowStep,
)
from app.services.artifact_store import ArtifactStoreError, materialize
from app.services.representations import (
    FORMAT_TO_TYPE,
    representation_checksum,
    validate_representation,
)
from app.services.simulation_adapters import (
    ADAPTER_CONTRACT_VERSION,
    SIMULATION_WARNING,
    SOFTWARE_FIXTURE_WARNING,
    adapter_descriptor,
    get_adapter,
)
from app.services.simulation_runtime import (
    COMPUTE_BACKEND_KEY,
    MAX_ARTIFACT_BYTES,
    ResourceRequest,
    UnsafeExecutionRequest,
    local_backend,
    safe_join,
    sanitize_command_for_record,
    workdir_token,
)
from app.services.units import UnitError, convert, normalize_unit

logger = logging.getLogger("tinkerlab.simulation")

ROUTER_POLICY_VERSION = "router-v1"
SIMULATION_CHECKSUM_VERSION = "simulation-v1"
UNIT_NORMALIZATION_VERSION = "units-v1"

# Bounded execution. Phase 6 is local and synchronous; no HPC scheduler is introduced.
MAX_WORKFLOW_STEPS = 10
MAX_JOBS_PER_REQUEST = 10
MAX_ROUTE_PREVIEW_TARGETS = 100
MAX_PAGE_SIZE = 200

EVIDENCE_SEPARATION_NOTE = (
    "Simulation results are a distinct scientific origin. They do not create observations, do not "
    "become predictions, and never participate in a comparison without an explicit selection policy."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


def _normalize_conditions(conditions: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(conditions):
        raw = conditions[key]
        if isinstance(raw, dict) and "value" in raw:
            unit = normalize_unit(str(raw["unit"])) if raw.get("unit") else None
            result[key] = {"value": float(raw["value"]), "unit": unit}
        else:
            result[key] = raw
    return result


def condition_checksum(conditions: dict[str, Any]) -> str:
    return checksum({"contract": "conditions-v1", "conditions": _normalize_conditions(conditions)})


# ---------------------------------------------------------------------------------------------
# Code-registered method definitions and workflow templates. Not user-authored.
# ---------------------------------------------------------------------------------------------
METHOD_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "software_fixture_energy_minimization_v1",
        "display_name": "Software-validation reduced-unit energy minimization",
        "method_family": "analytical_fixture",
        "purpose": "software_validation",
        "description": "Deterministic reduced-unit numerical fixture. Validates the Simulation OS, not materials science.",
        "required_representation_types": [RepresentationType.SOFTWARE_VALIDATION_FIXTURE.value],
        "required_parameters": {
            "step_size": {"type": "number", "minimum": 1e-6, "maximum": 1.0},
            "max_iterations": {"type": "integer", "minimum": 1, "maximum": 10000},
            "gradient_tolerance": {"type": "number", "minimum": 1e-12, "maximum": 1.0},
        },
        "optional_parameters": {},
        "output_schema": {"software_fixture_reduced_energy": "number", "final_gradient": "number", "iterations": "integer"},
        "output_property_keys": ["software_fixture_reduced_energy"],
        "output_units": {"software_fixture_reduced_energy": "1"},
        "convergence_semantics": {"criterion": "gradient_magnitude_below_tolerance", "tolerance_parameter": "gradient_tolerance"},
        "known_limitations": [SOFTWARE_FIXTURE_WARNING, "Dimensionless reduced units; not a physical energy."],
        "fidelity": "software_fixture",
        "supported_condition_keys": [],
    },
    {
        "key": "dft_single_point_energy_v1",
        "display_name": "Periodic DFT single-point total energy",
        "method_family": "dft",
        "purpose": "energy_stability",
        "description": "Single-point SCF total energy for a periodic crystalline cell using a reviewed provider.",
        "required_representation_types": [RepresentationType.PERIODIC_ATOMIC_STRUCTURE.value],
        "required_parameters": {
            "ecutwfc_ry": {"type": "number", "minimum": 10.0, "maximum": 200.0},
            "ecutrho_ry": {"type": "number", "minimum": 40.0, "maximum": 1600.0},
            "kpoint_grid": {"type": "array", "length": 3},
            "conv_thr_ry": {"type": "number", "minimum": 1e-12, "maximum": 1e-4},
            "occupations": {"type": "string", "enum": ["fixed", "smearing"]},
        },
        "optional_parameters": {},
        "output_schema": {"total_energy": "number", "scf_converged": "boolean"},
        "output_property_keys": ["total_energy"],
        "output_units": {"total_energy": "Ry"},
        "convergence_semantics": {"criterion": "scf_convergence_flag_and_completion", "requires_flag": True},
        "known_limitations": [
            "Cutoffs and k-point density are explicit scientific parameters, never hidden defaults.",
            "A converged energy is not a synthesizability, manufacturability or safety claim.",
        ],
        "fidelity": "first_principles",
        "supported_condition_keys": [],
    },
    {
        "key": "md_reduced_unit_minimization_v1",
        "display_name": "Atomistic reduced-unit energy minimization",
        "method_family": "md",
        "purpose": "energy_stability",
        "description": "Bounded reduced-unit minimization for an atomistic topology with a registered potential.",
        "required_representation_types": [RepresentationType.MOLECULAR_TOPOLOGY.value],
        "required_parameters": {
            "minimization_energy_tolerance": {"type": "number", "minimum": 1e-12, "maximum": 1.0},
            "minimization_force_tolerance": {"type": "number", "minimum": 1e-12, "maximum": 1.0},
            "max_iterations": {"type": "integer", "minimum": 1, "maximum": 100000},
            "max_force_evaluations": {"type": "integer", "minimum": 1, "maximum": 1000000},
        },
        "optional_parameters": {},
        "output_schema": {"md_reduced_potential_energy": "number", "final_fmax": "number"},
        # Deliberately NOT called "total_energy": this is a dimensionless reduced-unit LJ energy and
        # must never share a property key with a physical first-principles total energy.
        "output_property_keys": ["md_reduced_potential_energy"],
        "output_units": {"md_reduced_potential_energy": "1"},
        "convergence_semantics": {"criterion": "max_force_below_tolerance", "tolerance_parameter": "minimization_force_tolerance"},
        "known_limitations": [
            "Requires an approved registered potential artifact; topology is never invented.",
            "Empirical potential error is a method limitation, not a statistical prediction interval.",
        ],
        "fidelity": "empirical_atomistic",
        "supported_condition_keys": [],
    },
]
METHOD_BY_KEY = {m["key"]: m for m in METHOD_DEFINITIONS}

WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "software_fixture_single_step_v1": {
        "key": "software_fixture_single_step_v1", "version": "1.0",
        "steps": [{"step_key": "fixture_minimize", "requires_convergence": True, "max_retries": 0, "depends_on": []}],
        "supported_method_keys": ["software_fixture_energy_minimization_v1"],
        "reproducibility_version": "workflow-v1",
    },
    "dft_single_point_v1": {
        "key": "dft_single_point_v1", "version": "1.0",
        "steps": [{"step_key": "scf_single_point", "requires_convergence": True, "max_retries": 0, "depends_on": []}],
        "supported_method_keys": ["dft_single_point_energy_v1"],
        "reproducibility_version": "workflow-v1",
    },
    "md_minimize_v1": {
        "key": "md_minimize_v1", "version": "1.0",
        "steps": [{"step_key": "minimize", "requires_convergence": True, "max_retries": 0, "depends_on": []}],
        "supported_method_keys": ["md_reduced_unit_minimization_v1"],
        "reproducibility_version": "workflow-v1",
    },
}


def template_for_method(method_key: str) -> dict[str, Any]:
    for template in WORKFLOW_TEMPLATES.values():
        if method_key in template["supported_method_keys"]:
            return template
    raise ValueError(f"No code-registered workflow template supports method {method_key}")


def workflow_template_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "key": t["key"], "version": t["version"], "supported_method_keys": list(t["supported_method_keys"]),
            "step_keys": [s["step_key"] for s in t["steps"]], "max_steps": len(t["steps"]),
            "reproducibility_version": t["reproducibility_version"],
        }
        for t in sorted(WORKFLOW_TEMPLATES.values(), key=lambda x: str(x["key"]))
    ]


# ---------------------------------------------------------------------------------------------
# Scope helpers
# ---------------------------------------------------------------------------------------------
def _visible_scope(column: Any, organisation_id: str | None) -> Any:
    if organisation_id:
        return or_(column.is_(None), column == organisation_id)
    return column.is_(None)


def visible_providers(db: Session, organisation_id: str | None) -> list[SimulationProvider]:
    return (
        db.query(SimulationProvider)
        .options(selectinload(SimulationProvider.versions))
        .filter(_visible_scope(SimulationProvider.organisation_id, organisation_id))
        .order_by(SimulationProvider.key, SimulationProvider.id)
        .all()
    )


def provider_visible(provider: SimulationProvider, organisation_id: str | None) -> bool:
    return provider.organisation_id is None or (organisation_id is not None and provider.organisation_id == organisation_id)


def representation_visible(row: ScientificRepresentation, organisation_id: str | None) -> bool:
    if row.visibility == "public" and row.organisation_id is None:
        return True
    return organisation_id is not None and row.organisation_id == organisation_id


def get_provider_version(db: Session, version_id: str) -> SimulationProviderVersion | None:
    return (
        db.query(SimulationProviderVersion)
        .options(selectinload(SimulationProviderVersion.provider))
        .filter(SimulationProviderVersion.id == version_id)
        .one_or_none()
    )


def require_provider_version(db: Session, version_id: str) -> SimulationProviderVersion:
    version = get_provider_version(db, version_id)
    if version is None:
        raise ValueError(f"Pinned simulation provider version {version_id} no longer exists")
    return version


# ---------------------------------------------------------------------------------------------
# Provider registry lifecycle
# ---------------------------------------------------------------------------------------------
def artifact_manifest_checksum(manifest: list[dict[str, Any]]) -> str:
    return checksum({"contract": "artifact-manifest-v1", "manifest": sorted(manifest, key=canonical_json)})


def create_provider_version(db: Session, provider: SimulationProvider, values: dict[str, Any]) -> SimulationProviderVersion:
    adapter_key = str(values["adapter_key"])
    adapter = get_adapter(adapter_key)  # code-registered lookup; never an import path
    caps = adapter.capabilities()
    if provider.method_family != caps.method_family:
        raise ValueError("Provider method family does not match the registered adapter capabilities")
    manifest = list(values.get("artifact_manifest") or [])
    version = SimulationProviderVersion(
        provider_id=provider.id,
        version=str(values["version"]),
        adapter_key=adapter_key,
        adapter_contract_version=ADAPTER_CONTRACT_VERSION,
        executable_key=getattr(adapter, "executable_key", None),
        parser_key=adapter.parser_key, parser_version=adapter.parser_version,
        input_builder_key=adapter.builder_key, input_builder_version=adapter.builder_version,
        convergence_evaluator_key=adapter.convergence_key, convergence_evaluator_version=adapter.convergence_version,
        supported_method_keys=list(caps.supported_method_keys),
        supported_material_families=list(caps.supported_material_families),
        supported_representation_types=list(caps.supported_representation_types),
        supported_representation_formats=list(caps.supported_representation_formats),
        supported_property_keys=list(caps.supported_property_keys),
        required_artifact_types=list(caps.required_artifact_types),
        artifact_manifest=manifest,
        artifact_manifest_checksum=artifact_manifest_checksum(manifest),
        environment_manifest=dict(values.get("environment_manifest") or {}),
        fidelity=caps.fidelity, deterministic=caps.deterministic, execution_supported=caps.execution_supported,
        maximum_target_size=caps.maximum_target_size, maximum_wall_time_seconds=caps.maximum_wall_time_seconds,
        resource_class=caps.resource_class, known_limitations=list(caps.known_limitations),
        immutable_metadata=dict(values.get("immutable_metadata") or {}),
    )
    if values.get("id"):
        version.id = str(values["id"])
    db.add(version)
    return version


def provider_version_in_use(db: Session, version: SimulationProviderVersion) -> bool:
    return db.query(SimulationJob).filter(SimulationJob.provider_version_id == version.id).first() is not None


def approve_provider_version(db: Session, version: SimulationProviderVersion) -> SimulationProviderVersion:
    if version.retired_at:
        raise ValueError("A retired provider version cannot be re-approved")
    version.approved_at = version.approved_at or now_utc()
    db.flush()
    return version


def set_provider_status(db: Session, provider: SimulationProvider, status: str) -> SimulationProvider:
    provider.status = status
    db.flush()
    return provider


def provider_version_executable(db: Session, version: SimulationProviderVersion) -> tuple[bool, str | None]:
    """Gate every execution on lifecycle *and* recomputed manifest integrity."""
    if not version.approved_at:
        return False, "Provider version is not approved"
    if version.retired_at:
        return False, "Provider version is retired"
    if version.provider.status != "approved":
        return False, f"Provider lifecycle status is '{version.provider.status}'"
    if artifact_manifest_checksum(version.artifact_manifest) != version.artifact_manifest_checksum:
        return False, "Artifact manifest checksum mismatch"
    if not version.execution_supported:
        return False, "This provider version is an interface-only boundary and cannot execute"
    return True, None


def provider_availability(db: Session, version: SimulationProviderVersion, cache: dict[str, Any] | None = None) -> dict[str, Any]:
    """Probe once per request. Never probe a binary per target or per provider-target pair."""
    cache = cache if cache is not None else {}
    if version.adapter_key in cache:
        return dict(cache[version.adapter_key])
    adapter = get_adapter(version.adapter_key)
    availability = adapter.check_availability()
    payload = {
        "available": availability.available, "reason_code": availability.reason_code, "detail": availability.detail,
        "executable_name": availability.executable_name, "executable_version": availability.executable_version,
    }
    cache[version.adapter_key] = payload
    return dict(payload)


# ---------------------------------------------------------------------------------------------
# Representations
# ---------------------------------------------------------------------------------------------
def create_representation(
    db: Session, *, organisation_id: str, material_id: str | None, hypothesis_id: str | None,
    label: str, representation_format: str, content: dict[str, Any], visibility: str = "private",
    provenance_note: str | None = None, metadata: dict[str, Any] | None = None, row_id: str | None = None,
) -> ScientificRepresentation:
    if bool(material_id) == bool(hypothesis_id):
        raise ValueError("A representation must reference exactly one material or one hypothesis")
    validator, outcome = validate_representation(representation_format, content)
    normalized = outcome.normalized_content or content
    row = ScientificRepresentation(
        organisation_id=organisation_id, visibility=visibility, material_id=material_id, hypothesis_id=hypothesis_id,
        label=label, representation_type=FORMAT_TO_TYPE[representation_format],
        representation_format=representation_format, representation_version=validator.version,
        content=normalized,
        normalized_checksum=representation_checksum(representation_format, validator.key, validator.version, normalized),
        content_bytes=len(canonical_json(normalized).encode()),
        periodicity=outcome.periodicity, dimensionality=outcome.dimensionality, atom_count=outcome.atom_count,
        component_count=outcome.component_count, chemical_elements=outcome.chemical_elements,
        validator_key=validator.key, validator_version=validator.version,
        validation_status=outcome.validation_status, completeness_status=outcome.completeness_status,
        validation_messages=outcome.messages, redaction_flags=outcome.redaction_flags,
        provenance_note=provenance_note, status="active", metadata_json=metadata or {},
    )
    if row_id:
        row.id = row_id
    db.add(row)
    db.flush()
    return row


def representations_for_target(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str | None
) -> list[ScientificRepresentation]:
    query = db.query(ScientificRepresentation).filter(ScientificRepresentation.status == "active")
    if target_kind == "known_material":
        query = query.filter(ScientificRepresentation.material_id == target_id)
    else:
        query = query.filter(ScientificRepresentation.hypothesis_id == target_id)
    rows = query.order_by(ScientificRepresentation.representation_type, ScientificRepresentation.created_at, ScientificRepresentation.id).all()
    return [r for r in rows if representation_visible(r, organisation_id)]


def _representation_context(row: ScientificRepresentation) -> dict[str, Any]:
    return {
        "id": row.id, "representation_type": row.representation_type, "representation_format": row.representation_format,
        "validation_status": row.validation_status, "completeness_status": row.completeness_status,
        "atom_count": row.atom_count, "component_count": row.component_count,
        "chemical_elements": list(row.chemical_elements or []), "content": row.content,
        "checksum": row.normalized_checksum, "redaction_flags": list(row.redaction_flags or []),
    }


# ---------------------------------------------------------------------------------------------
# Registered scientific artifacts
# ---------------------------------------------------------------------------------------------
def approved_artifacts(db: Session, organisation_id: str | None) -> list[RegisteredScientificArtifact]:
    return (
        db.query(RegisteredScientificArtifact)
        .filter(
            RegisteredScientificArtifact.status == "approved",
            _visible_scope(RegisteredScientificArtifact.organisation_id, organisation_id),
        )
        .order_by(RegisteredScientificArtifact.artifact_type, RegisteredScientificArtifact.key, RegisteredScientificArtifact.id)
        .all()
    )


def _artifact_context(artifacts: list[RegisteredScientificArtifact], method_family: str) -> dict[str, Any]:
    relevant = [a for a in artifacts if not a.applies_to_method_families or method_family in a.applies_to_method_families]
    covered_elements: set[str] = set()
    for artifact in relevant:
        if artifact.content_available:
            covered_elements.update(artifact.applies_to_elements or [])
    return {
        # An artifact row with no retrievable content cannot satisfy a requirement: a registry entry
        # is a promise, and Phase 6 does not route on promises.
        "available_artifact_types": sorted({a.artifact_type for a in relevant if a.content_available}),
        "artifact_covered_elements": sorted(covered_elements),
        "artifact_references": [
            {
                "key": a.key, "version": a.version, "artifact_type": a.artifact_type,
                "checksum": a.content_checksum,
                # The on-disk name a solver will see. Server-chosen, never caller-supplied.
                "file_name": str((a.metadata_json or {}).get("file_name") or f"{a.key}.{a.version}.dat"),
                "content_available": bool(a.content_available),
                **({"element": a.applies_to_elements[0]} if a.applies_to_elements else {}),
            }
            for a in relevant
        ],
    }


# ---------------------------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------------------------
@dataclass
class RouteCandidate:
    method_key: str
    provider_version: SimulationProviderVersion
    representation: ScientificRepresentation | None
    status: str
    reasons: list[dict[str, Any]]
    missing_representation_types: list[str]
    missing_artifact_types: list[str]
    fidelity: str
    resource_class: str
    limitations: list[str]
    route_checksum: str
    artifact_references: list[dict[str, Any]]


def _route_checksum(
    *, representation_checksum_value: str | None, purpose: str, property_key: str | None, conditions: dict[str, Any],
    method: dict[str, Any], version: SimulationProviderVersion,
) -> str:
    return checksum({
        "contract": SIMULATION_CHECKSUM_VERSION,
        "representation_checksum": representation_checksum_value,
        "purpose": purpose, "property_key": property_key,
        "conditions": _normalize_conditions(conditions),
        "method": [method["key"], method.get("definition_version", "1.0")],
        "provider_version": [version.provider.key, version.version, version.adapter_key],
        "artifact_manifest_checksum": version.artifact_manifest_checksum,
        "route_policy_version": ROUTER_POLICY_VERSION,
    })


def resolve_target(db: Session, target_kind: str, target_id: str, organisation_id: str | None) -> tuple[str, str] | None:
    """Returns (material_family, display_name) or None when the target is not visible in scope."""
    if target_kind == "known_material":
        material = db.get(Material, target_id)
        if not material:
            return None
        if material.visibility != "public" and material.owner_organisation_id != organisation_id:
            return None
        return material.material_family, material.display_name
    hypothesis = db.get(CandidateHypothesis, target_id)
    if not hypothesis or hypothesis.organisation_id != organisation_id:
        return None
    return hypothesis.material_family, hypothesis.display_label


def preview_routes(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str, purpose: str,
    property_key: str | None = None, conditions: dict[str, Any] | None = None,
    pinned_provider_version_id: str | None = None,
) -> dict[str, Any]:
    """Return ordered routes with transparent reasons. Persists nothing at all."""
    conditions = conditions or {}
    resolved = resolve_target(db, target_kind, target_id, organisation_id)
    if resolved is None:
        # Do not distinguish "absent" from "another tenant's" — that would leak existence.
        raise LookupError("Simulation target not found")
    material_family, display_name = resolved

    representations = representations_for_target(db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id)
    by_type: dict[str, ScientificRepresentation] = {}
    for row in representations:
        by_type.setdefault(row.representation_type, row)

    artifacts = approved_artifacts(db, organisation_id)
    providers = visible_providers(db, organisation_id)
    availability_cache: dict[str, Any] = {}
    routes: list[RouteCandidate] = []

    for provider in providers:
        for version in sorted(provider.versions, key=lambda v: (v.version, v.id)):
            if pinned_provider_version_id and version.id != pinned_provider_version_id:
                continue
            adapter = get_adapter(version.adapter_key)
            caps = adapter.capabilities()
            method_keys = [m for m in version.supported_method_keys if m in METHOD_BY_KEY] or ["__unsupported__"]
            for method_key in method_keys:
                method = METHOD_BY_KEY.get(method_key)
                if method is None:
                    routes.append(RouteCandidate(
                        method_key="unavailable", provider_version=version, representation=None,
                        status=SimulationRouteStatus.PROVIDER_UNAVAILABLE,
                        reasons=[{"code": "NO_EXECUTABLE_METHOD",
                                  "message": f"{provider.display_name} exposes no executable Phase-6 method."}],
                        missing_representation_types=list(caps.supported_representation_types),
                        missing_artifact_types=list(caps.required_artifact_types),
                        fidelity=caps.fidelity, resource_class=caps.resource_class,
                        limitations=list(caps.known_limitations),
                        route_checksum=_route_checksum(
                            representation_checksum_value=None, purpose=purpose, property_key=property_key,
                            conditions=conditions, method={"key": "unavailable"}, version=version),
                        artifact_references=[],
                    ))
                    continue
                if property_key and property_key not in method["output_property_keys"]:
                    continue

                representation = next(
                    (by_type[t] for t in method["required_representation_types"] if t in by_type), None
                )
                artifact_ctx = _artifact_context(artifacts, caps.method_family)
                context = {
                    "representation": _representation_context(representation) if representation else None,
                    "material_family": material_family, "method_key": method_key,
                    "property_key": property_key, "conditions": conditions,
                    "supported_condition_keys": method.get("supported_condition_keys", []),
                    **artifact_ctx,
                }
                decision = adapter.validate_target(context)
                lifecycle_ok, lifecycle_reason = provider_version_executable(db, version)
                availability = provider_availability(db, version, availability_cache)

                reasons = [dict(r) for r in decision.reasons]
                status = decision.status
                if status == "ready" and not lifecycle_ok:
                    status = SimulationRouteStatus.PROVIDER_UNAVAILABLE
                    reasons.append({"code": "PROVIDER_LIFECYCLE_BLOCKED", "message": lifecycle_reason or "Provider version is not executable"})
                if status == "ready" and not availability["available"]:
                    status = SimulationRouteStatus.PROVIDER_UNAVAILABLE
                    reasons.append({"code": "PROVIDER_RUNTIME_UNAVAILABLE", "message": availability["detail"]})
                routes.append(RouteCandidate(
                    method_key=method_key, provider_version=version, representation=representation,
                    status=status, reasons=reasons,
                    missing_representation_types=list(decision.missing_representation_types)
                    or ([] if representation else list(method["required_representation_types"])),
                    missing_artifact_types=list(decision.missing_artifact_types),
                    fidelity=method["fidelity"], resource_class=caps.resource_class,
                    limitations=list(method["known_limitations"]) + list(caps.known_limitations),
                    route_checksum=_route_checksum(
                        representation_checksum_value=representation.normalized_checksum if representation else None,
                        purpose=purpose, property_key=property_key, conditions=conditions,
                        method=method, version=version),
                    artifact_references=artifact_ctx["artifact_references"],
                ))

    # Deterministic ordering: ready first, then applicability completeness, then stable identity.
    # Fidelity is descriptive and never orders routes on its own.
    status_rank: dict[str, int] = {
        SimulationRouteStatus.READY.value: 0, SimulationRouteStatus.INCOMPLETE_REPRESENTATION.value: 1,
        SimulationRouteStatus.MISSING_REGISTERED_ARTIFACT.value: 2, SimulationRouteStatus.PROVIDER_UNAVAILABLE.value: 3,
        SimulationRouteStatus.UNSUPPORTED_CONDITIONS.value: 4, SimulationRouteStatus.UNSUPPORTED_PROPERTY.value: 5,
        SimulationRouteStatus.NOT_APPLICABLE.value: 6,
    }
    routes.sort(key=lambda r: (status_rank.get(str(r.status), 9), len(r.reasons), r.provider_version.provider.key, r.method_key, r.provider_version.version))

    return {
        "target_kind": target_kind, "target_id": target_id, "target_display_name": display_name,
        "material_family": material_family, "requested_purpose": purpose, "requested_property_key": property_key,
        "requested_conditions": _normalize_conditions(conditions),
        "representations_considered": [
            {"id": r.id, "representation_type": r.representation_type, "representation_format": r.representation_format,
             "checksum": r.normalized_checksum, "validation_status": r.validation_status,
             "completeness_status": r.completeness_status}
            for r in representations
        ],
        "routes": [
            {
                "method_key": r.method_key,
                "method_display_name": METHOD_BY_KEY.get(r.method_key, {}).get("display_name", "Unavailable"),
                "method_family": r.provider_version.provider.method_family,
                "provider_key": r.provider_version.provider.key,
                "provider_display_name": r.provider_version.provider.display_name,
                "provider_version_id": r.provider_version.id, "provider_version": r.provider_version.version,
                "adapter_key": r.provider_version.adapter_key,
                "representation_id": r.representation.id if r.representation else None,
                "representation_checksum": r.representation.normalized_checksum if r.representation else None,
                "route_status": r.status, "reasons": r.reasons,
                "missing_representation_types": r.missing_representation_types,
                "missing_artifact_types": r.missing_artifact_types,
                "fidelity": r.fidelity, "estimated_resource_class": r.resource_class,
                "limitations": r.limitations, "route_checksum": r.route_checksum,
                "route_policy_version": ROUTER_POLICY_VERSION,
            }
            for r in routes
        ],
        "warning": SIMULATION_WARNING,
        "evidence_separation": EVIDENCE_SEPARATION_NOTE,
    }


# ---------------------------------------------------------------------------------------------
# Input snapshots and workflow preview
# ---------------------------------------------------------------------------------------------
def _validate_parameters(method: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """A required scientific parameter that is absent is an error. It is never invented."""
    normalized: dict[str, Any] = {}
    problems: list[str] = []
    for key, spec in sorted(method["required_parameters"].items()):
        if key not in parameters:
            problems.append(f"Required scientific parameter '{key}' was not supplied and is never defaulted silently.")
            continue
        value = parameters[key]
        if spec["type"] == "integer":
            value = int(value)
        elif spec["type"] == "number":
            value = float(value)
        elif spec["type"] == "array":
            value = [int(v) for v in value]
            if len(value) != spec.get("length", len(value)):
                problems.append(f"Parameter '{key}' must contain exactly {spec['length']} entries.")
        elif spec["type"] == "string":
            value = str(value)
            if spec.get("enum") and value not in spec["enum"]:
                problems.append(f"Parameter '{key}' must be one of: {', '.join(spec['enum'])}.")
        if spec.get("minimum") is not None and isinstance(value, int | float) and value < spec["minimum"]:
            problems.append(f"Parameter '{key}' is below the reviewed minimum {spec['minimum']}.")
        if spec.get("maximum") is not None and isinstance(value, int | float) and value > spec["maximum"]:
            problems.append(f"Parameter '{key}' exceeds the reviewed maximum {spec['maximum']}.")
        normalized[key] = value
    if problems:
        raise ValueError("; ".join(problems))
    return normalized


def _target_fingerprint(db: Session, target_kind: str, target_id: str) -> str:
    if target_kind == "known_material":
        material = db.get(Material, target_id)
        if material is None:
            raise ValueError("Simulation target material no longer exists")
        return checksum({"kind": "known_material", "canonical_name": material.canonical_name, "family": material.material_family})
    hypothesis = db.get(CandidateHypothesis, target_id)
    if hypothesis is None:
        raise ValueError("Simulation target hypothesis no longer exists")
    return checksum({"kind": "hypothesis", "fingerprint": hypothesis.deterministic_fingerprint,
                     "fingerprint_version": hypothesis.fingerprint_version})


def _input_checksum(payload: dict[str, Any]) -> str:
    return checksum({"contract": SIMULATION_CHECKSUM_VERSION, "input": payload})


def build_workflow_preview(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str, method_key: str,
    provider_version_id: str, parameters: dict[str, Any], conditions: dict[str, Any] | None = None,
    property_key: str | None = None, purpose: str | None = None,
) -> dict[str, Any]:
    """Validate a requested route end-to-end and show the exact input that *would* execute."""
    conditions = conditions or {}
    method = METHOD_BY_KEY.get(method_key)
    if method is None:
        raise ValueError(f"Unknown simulation method: {method_key}")
    version = require_provider_version(db, provider_version_id)
    if not provider_visible(version.provider, organisation_id):
        raise LookupError("Simulation provider version not found")

    preview = preview_routes(
        db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id,
        purpose=purpose or method["purpose"], property_key=property_key, conditions=conditions,
        pinned_provider_version_id=provider_version_id,
    )
    route = next((r for r in preview["routes"] if r["method_key"] == method_key), None)
    if route is None:
        raise ValueError("The requested method/provider combination produced no route for this target")
    problems: list[str] = []
    if route["route_status"] != SimulationRouteStatus.READY:
        problems.append(f"Route status is '{route['route_status']}'; a workflow can only be created from a ready route.")

    normalized_parameters: dict[str, Any] = {}
    try:
        normalized_parameters = _validate_parameters(method, parameters)
    except ValueError as exc:
        problems.append(str(exc))

    representation = db.get(ScientificRepresentation, route["representation_id"]) if route["representation_id"] else None
    input_bundle = None
    input_checksum_value = None
    artifact_references: list[dict[str, Any]] = []
    if representation is not None and not problems:
        adapter = get_adapter(version.adapter_key)
        artifacts = approved_artifacts(db, organisation_id)
        artifact_ctx = _artifact_context(artifacts, version.provider.method_family)
        artifact_references = [
            a for a in artifact_ctx["artifact_references"] if a["artifact_type"] in (version.required_artifact_types or [])
        ]
        bundle = adapter.build_inputs({
            "representation": _representation_context(representation), "parameters": normalized_parameters,
            "artifact_references": artifact_references,
        })
        input_bundle = bundle
        normalized_parameters = dict(bundle.normalized_parameters)
        input_checksum_value = _input_checksum({
            "representation_checksum": representation.normalized_checksum,
            "provider_version": [version.provider.key, version.version, version.adapter_key, version.artifact_manifest_checksum],
            "method": [method["key"], method.get("definition_version", "1.0")],
            "parameters": normalized_parameters,
            "conditions": _normalize_conditions(conditions),
            "artifacts": sorted([a["checksum"] for a in artifact_references]),
            "builder": [bundle.builder_key, bundle.builder_version],
            "unit_normalization_version": UNIT_NORMALIZATION_VERSION,
        })

    template = template_for_method(method_key)
    return {
        "valid": not problems,
        "validation_problems": problems,
        "target_kind": target_kind, "target_id": target_id,
        "route": route,
        "method": {
            "key": method["key"], "display_name": method["display_name"], "fidelity": method["fidelity"],
            "convergence_semantics": method["convergence_semantics"], "known_limitations": method["known_limitations"],
            "output_property_keys": method["output_property_keys"], "output_units": method["output_units"],
        },
        "provider_version": {
            "id": version.id, "provider_key": version.provider.key, "version": version.version,
            "adapter_key": version.adapter_key, "executable_key": version.executable_key,
            "artifact_manifest_checksum": version.artifact_manifest_checksum,
            "parser": [version.parser_key, version.parser_version],
            "input_builder": [version.input_builder_key, version.input_builder_version],
            "convergence_evaluator": [version.convergence_evaluator_key, version.convergence_evaluator_version],
        },
        "representation": {
            "id": representation.id, "checksum": representation.normalized_checksum,
            "representation_type": representation.representation_type,
        } if representation else None,
        "normalized_parameters": normalized_parameters,
        "target_conditions": _normalize_conditions(conditions),
        "input_checksum": input_checksum_value,
        "input_files": sorted(input_bundle.files) if input_bundle else [],
        "input_file_preview": {k: v[:2000] for k, v in (input_bundle.files.items() if input_bundle else [])},
        # The artifact file name is part of provenance and is needed to reproduce the exact input,
        # so it is retained. It is a server-chosen name for approved content, not user data.
        "artifact_references": artifact_references,
        "workflow_template": {"key": template["key"], "version": template["version"],
                              "steps": [s["step_key"] for s in template["steps"]]},
        "resource_request": ResourceRequest(wall_time_seconds=min(version.maximum_wall_time_seconds, 300)).as_dict(),
        "warning": SIMULATION_WARNING,
        "executes_nothing": True,
    }


# ---------------------------------------------------------------------------------------------
# Workflow creation and bounded execution
# ---------------------------------------------------------------------------------------------
def create_workflow(
    db: Session, *, organisation_id: str, created_by: str, target_kind: str, target_id: str,
    method_key: str, provider_version_id: str, parameters: dict[str, Any],
    conditions: dict[str, Any] | None = None, property_key: str | None = None,
    project_id: str | None = None, candidate_id: str | None = None, campaign_id: str | None = None,
    metadata: dict[str, Any] | None = None, workflow_id: str | None = None,
) -> SimulationWorkflow:
    conditions = conditions or {}
    preview = build_workflow_preview(
        db, target_kind=target_kind, target_id=target_id, organisation_id=organisation_id, method_key=method_key,
        provider_version_id=provider_version_id, parameters=parameters, conditions=conditions, property_key=property_key,
    )
    if not preview["valid"]:
        raise ValueError("; ".join(preview["validation_problems"]))

    method = METHOD_BY_KEY[method_key]
    version = require_provider_version(db, provider_version_id)
    representation = db.get(ScientificRepresentation, preview["representation"]["id"])
    if representation is None:
        raise ValueError("Representation disappeared between preview and creation")
    definition = db.query(SimulationMethodDefinition).filter_by(key=method_key).one()

    route_payload = preview["route"]
    route = SimulationRoute(
        organisation_id=organisation_id, target_kind=target_kind, target_scientific_id=target_id,
        requested_purpose=route_payload.get("requested_purpose") or method["purpose"],
        requested_property_key=property_key, requested_conditions=_normalize_conditions(conditions),
        representation_id=representation.id, method_definition_id=definition.id, provider_version_id=version.id,
        route_status=route_payload["route_status"], applicability_reasons=route_payload["reasons"],
        missing_representation_types=route_payload["missing_representation_types"],
        missing_artifact_types=route_payload["missing_artifact_types"],
        fidelity=route_payload["fidelity"], estimated_resource_class=route_payload["estimated_resource_class"],
        route_policy_version=ROUTER_POLICY_VERSION, route_checksum=route_payload["route_checksum"],
    )
    db.add(route); db.flush()

    snapshot = SimulationInputSnapshot(
        organisation_id=organisation_id, target_kind=target_kind, target_scientific_id=target_id,
        target_fingerprint=_target_fingerprint(db, target_kind, target_id),
        representation_id=representation.id, representation_checksum=representation.normalized_checksum,
        method_definition_id=definition.id, method_definition_version=definition.definition_version,
        provider_version_id=version.id, normalized_parameters=preview["normalized_parameters"],
        target_conditions=_normalize_conditions(conditions), condition_checksum=condition_checksum(conditions),
        input_builder_key=version.input_builder_key, input_builder_version=version.input_builder_version,
        artifact_references=preview["artifact_references"],
        artifact_manifest_checksum=version.artifact_manifest_checksum,
        unit_normalization_version=UNIT_NORMALIZATION_VERSION, input_checksum=preview["input_checksum"],
        redaction_flags=list(representation.redaction_flags or []),
    )
    db.add(snapshot); db.flush()

    template = template_for_method(method_key)
    if len(template["steps"]) > MAX_WORKFLOW_STEPS:
        raise ValueError(f"Workflow template exceeds the Phase-6 bound of {MAX_WORKFLOW_STEPS} steps")

    workflow = SimulationWorkflow(
        organisation_id=organisation_id, project_id=project_id, candidate_id=candidate_id, campaign_id=campaign_id,
        target_kind=target_kind, target_scientific_id=target_id, route_id=route.id, input_snapshot_id=snapshot.id,
        provider_version_id=version.id, method_definition_id=definition.id,
        workflow_template_key=template["key"], workflow_template_version=template["version"],
        requested_purpose=method["purpose"], requested_property_key=property_key, requested_fidelity=method["fidelity"],
        max_steps=len(template["steps"]), max_wall_time_seconds=min(version.maximum_wall_time_seconds, 300),
        status=SimulationWorkflowStatus.PREPARED, created_by=created_by,
        metadata_json={**(metadata or {}), "warning": SIMULATION_WARNING},
    )
    if workflow_id:
        workflow.id = workflow_id
    db.add(workflow); db.flush()

    for index, step_spec in enumerate(template["steps"]):
        db.add(SimulationWorkflowStep(
            workflow_id=workflow.id, sequence=index, step_key=step_spec["step_key"], provider_version_id=version.id,
            method_key=method_key, depends_on_step_ids=[], status="prepared", input_checksum=snapshot.input_checksum,
            requires_convergence=bool(step_spec["requires_convergence"]), max_retries=int(step_spec["max_retries"]),
            metadata_json={},
        ))
    db.flush()
    return workflow


def _store_artifact(
    db: Session, *, organisation_id: str, workflow_id: str, job_id: str | None, artifact_type: str,
    content_role: str, file_name: str, body: str, truncated: bool = False, media_type: str = "text/plain",
) -> SimulationArtifact:
    payload = body[:MAX_ARTIFACT_BYTES]
    artifact = SimulationArtifact(
        organisation_id=organisation_id, workflow_id=workflow_id, job_id=job_id, artifact_type=artifact_type,
        content_role=content_role, file_name=file_name, media_type=media_type,
        # Opaque server-side locator. A host filesystem path is never returned through the API.
        storage_reference=f"simulation://{workflow_id}/{content_role}/{file_name}",
        content_checksum=hashlib.sha256(payload.encode()).hexdigest(), content_bytes=len(payload.encode()),
        truncated=truncated or len(body.encode()) > MAX_ARTIFACT_BYTES, is_private=True,
        inline_preview=payload[:4000], metadata_json={},
    )
    db.add(artifact); db.flush()
    return artifact


def _result_checksum(
    *, input_checksum: str, version: SimulationProviderVersion, parsed: dict[str, Any],
    convergence: dict[str, Any], artifact_checksums: list[str],
) -> str:
    """Scientific identity only: no timestamps, ids, elapsed times or display names participate."""
    return checksum({
        "contract": SIMULATION_CHECKSUM_VERSION,
        "input_checksum": input_checksum,
        "provider_identity": [version.provider.key, version.version, version.adapter_key,
                              version.executable_version, version.artifact_manifest_checksum],
        "parser": [version.parser_key, version.parser_version],
        "parse_status": parsed.get("parse_status"),
        "quantities": parsed.get("quantities", {}),
        "convergence": {"status": convergence.get("scientific_status"), "metrics": convergence.get("metrics", {}),
                        "criteria": convergence.get("criteria", {})},
        "output_artifact_checksums": sorted(artifact_checksums),
    })


def _extract_property_estimates(
    db: Session, *, result: SimulationResult, method: dict[str, Any], parsed: dict[str, Any],
    conditions: dict[str, Any], adapter_key: str,
) -> list[SimulationPropertyEstimate]:
    """A property estimate requires converged status, a registered parser and a valid unit mapping."""
    if result.scientific_status != SimulationScientificStatus.CONVERGED:
        return []
    estimates: list[SimulationPropertyEstimate] = []
    for property_key in method["output_property_keys"]:
        quantity = parsed.get("quantities", {}).get(property_key)
        if not quantity:
            continue
        definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
        if definition is None:
            logger.info("simulation_property_mapping_absent", extra={"property_key": property_key})
            continue
        raw_unit = str(quantity.get("unit") or method["output_units"].get(property_key) or "1")
        canonical_unit = definition.canonical_unit or raw_unit
        try:
            canonical_value = convert(float(quantity["value"]), raw_unit, canonical_unit)
        except (UnitError, TypeError, ValueError) as exc:
            # An uncanonicalizable unit yields no estimate. Dimensions are never reinterpreted.
            logger.info("simulation_unit_mapping_rejected", extra={"property_key": property_key, "detail": str(exc)})
            continue
        tolerance = result.convergence_metrics.get("gradient_tolerance") or result.convergence_metrics.get("force_tolerance")
        estimate = SimulationPropertyEstimate(
            simulation_result_id=result.id, property_definition_id=definition.id,
            numeric_value=float(quantity["value"]), raw_unit=raw_unit,
            canonical_value=canonical_value, canonical_unit=canonical_unit,
            numerical_tolerance=float(tolerance) if tolerance is not None else None,
            tolerance_basis="numerical_convergence_criterion" if tolerance is not None else None,
            method_limitations=list(method["known_limitations"]),
            target_conditions=_normalize_conditions(conditions),
            extractor_key=f"{adapter_key}_extractor", extractor_version="1.0",
            estimate_checksum=checksum({
                "result_checksum": result.result_checksum, "property": property_key,
                "value": float(quantity["value"]), "raw_unit": raw_unit,
                "canonical_value": canonical_value, "canonical_unit": canonical_unit,
            }),
        )
        db.add(estimate)
        estimates.append(estimate)
    return estimates


def execute_workflow(db: Session, workflow: SimulationWorkflow) -> SimulationWorkflow:
    """Execute a prepared workflow within Phase-6 bounds. Retries append attempts; nothing is overwritten."""
    if workflow.status not in {SimulationWorkflowStatus.PREPARED, SimulationWorkflowStatus.FAILED}:
        raise ValueError(f"Workflow in status '{workflow.status}' cannot be executed")
    version = require_provider_version(db, workflow.provider_version_id)
    executable, reason = provider_version_executable(db, version)
    if not executable:
        workflow.status = SimulationWorkflowStatus.FAILED
        workflow.failure_code = "provider_not_executable"
        workflow.metadata_json = {**workflow.metadata_json, "failure_detail": reason}
        db.commit()
        return workflow

    adapter = get_adapter(version.adapter_key)
    availability = adapter.check_availability()
    if not availability.available:
        workflow.status = SimulationWorkflowStatus.FAILED
        workflow.failure_code = "provider_unavailable"
        workflow.metadata_json = {**workflow.metadata_json, "failure_detail": availability.detail}
        db.commit()
        return workflow

    snapshot = db.get(SimulationInputSnapshot, workflow.input_snapshot_id)
    representation = db.get(ScientificRepresentation, snapshot.representation_id) if snapshot else None
    definition = db.get(SimulationMethodDefinition, workflow.method_definition_id)
    if snapshot is None or representation is None or definition is None:
        raise ValueError("Workflow is missing its immutable input snapshot")
    method = METHOD_BY_KEY[definition.key]

    steps = sorted(workflow.steps, key=lambda s: s.sequence)
    if len(steps) > MAX_JOBS_PER_REQUEST:
        raise ValueError(f"Workflow exceeds the bound of {MAX_JOBS_PER_REQUEST} jobs per synchronous request")

    workflow.status = SimulationWorkflowStatus.RUNNING
    workflow.started_at = now_utc()
    db.flush()

    bundle = adapter.build_inputs({
        "representation": _representation_context(representation),
        "parameters": snapshot.normalized_parameters,
        "artifact_references": snapshot.artifact_references,
    })
    resource = ResourceRequest(wall_time_seconds=workflow.max_wall_time_seconds)
    step = steps[0]
    attempt = (
        db.query(SimulationJob).filter(SimulationJob.step_id == step.id)
        .order_by(SimulationJob.attempt_number.desc()).first()
    )
    attempt_number = (attempt.attempt_number + 1) if attempt else 1
    token = workdir_token()
    descriptor = adapter.command_descriptor({"timeout_seconds": resource.wall_time_seconds})
    command_record = (
        sanitize_command_for_record(descriptor, availability.executable_name) if descriptor
        else {"executable_key": None, "in_process": True, "shell": False, "argv": []}
    )

    job = SimulationJob(
        workflow_id=workflow.id, step_id=step.id, provider_version_id=version.id, attempt_number=attempt_number,
        workdir_token=token, command_descriptor=command_record, resource_request=resource.as_dict(),
        compute_backend_key=COMPUTE_BACKEND_KEY, status=SimulationJobStatus.RUNNING, started_at=now_utc(),
        operational_checksum=checksum({
            "input_checksum": snapshot.input_checksum, "command": command_record,
            "environment_manifest": version.environment_manifest, "resource": resource.as_dict(),
            "attempt": attempt_number, "executable_version": version.executable_version,
        }),
        metadata_json={},
    )
    db.add(job); db.flush()

    workdir: str | None = None
    try:
        if descriptor is not None:
            workdir = local_backend.prepare_workdir(token)
            local_backend.write_inputs(workdir, bundle.files)
            # Approved artifact content is copied out of the controlled store, with its digest
            # re-verified, under a server-chosen file name. Nothing is fetched from the network.
            subdirectory = getattr(adapter, "artifact_subdirectory", None)
            for reference in snapshot.artifact_references or []:
                if not reference.get("content_available"):
                    continue
                materialize(str(reference["checksum"]), workdir, str(reference["file_name"]), subdirectory)
            for scratch in getattr(adapter, "scratch_subdirectories", ()):  # solver output dirs
                os.makedirs(safe_join(workdir, scratch), mode=0o700, exist_ok=True)
            execution = adapter.execute({"command_descriptor": descriptor, "workdir": workdir})
        else:
            execution = adapter.execute({"normalized_parameters": snapshot.normalized_parameters})
    except UnsafeExecutionRequest as exc:
        execution = {"status": SimulationJobStatus.FAILED, "exit_code": None, "failure_code": "unsafe_execution_request",
                     "stdout": "", "stderr": str(exc)[:500], "stdout_truncated": False, "stderr_truncated": False,
                     "elapsed_seconds": 0.0, "output_files": {}}
    except ArtifactStoreError as exc:
        # A missing or tampered approved artifact fails the job. It never falls back to a default.
        execution = {"status": SimulationJobStatus.FAILED, "exit_code": None, "failure_code": "artifact_content_unavailable",
                     "stdout": "", "stderr": str(exc)[:500], "stdout_truncated": False, "stderr_truncated": False,
                     "elapsed_seconds": 0.0, "output_files": {}}
    finally:
        if workdir:
            local_backend.cleanup(workdir)

    for name, body in sorted(bundle.files.items()):
        _store_artifact(db, organisation_id=workflow.organisation_id, workflow_id=workflow.id, job_id=job.id,
                        artifact_type=SimulationArtifactType.INPUT, content_role="input", file_name=name, body=body)

    job.status = execution["status"]
    job.process_exit_code = execution["exit_code"]
    job.failure_code = execution["failure_code"]
    job.elapsed_seconds = execution["elapsed_seconds"]
    job.completed_at = now_utc()
    stdout_artifact = _store_artifact(
        db, organisation_id=workflow.organisation_id, workflow_id=workflow.id, job_id=job.id,
        artifact_type=SimulationArtifactType.LOG, content_role="stdout", file_name="stdout.log",
        body=execution["stdout"], truncated=execution["stdout_truncated"])
    stderr_artifact = _store_artifact(
        db, organisation_id=workflow.organisation_id, workflow_id=workflow.id, job_id=job.id,
        artifact_type=SimulationArtifactType.LOG, content_role="stderr", file_name="stderr.log",
        body=execution["stderr"], truncated=execution["stderr_truncated"])
    job.stdout_artifact_id = stdout_artifact.id
    job.stderr_artifact_id = stderr_artifact.id
    output_artifacts = [
        _store_artifact(db, organisation_id=workflow.organisation_id, workflow_id=workflow.id, job_id=job.id,
                        artifact_type=SimulationArtifactType.OUTPUT, content_role="output", file_name=name, body=body)
        for name, body in sorted((execution.get("output_files") or {}).items())
    ]
    db.flush()

    # Operational success is not scientific convergence: parse and convergence are separate gates.
    if job.status != SimulationJobStatus.COMPLETED:
        parsed = {"parse_status": "not_attempted", "quantities": {}, "warnings": ["Job did not complete operationally."]}
        convergence = {"scientific_status": SimulationScientificStatus.NOT_APPLICABLE, "metrics": {}, "criteria": {},
                       "warnings": ["No scientific result: the process did not complete."]}
    else:
        parsed = adapter.parse_outputs({
            "stdout": execution["stdout"], "stderr": execution["stderr"],
            "output_files": execution.get("output_files") or {},
        })
        if parsed["parse_status"] != "parsed":
            convergence = {"scientific_status": SimulationScientificStatus.PARSER_FAILED, "metrics": {},
                           "criteria": {"parser": [version.parser_key, version.parser_version]},
                           "warnings": parsed.get("warnings", [])}
        else:
            convergence = adapter.assess_convergence({
                "quantities": parsed["quantities"], "normalized_parameters": snapshot.normalized_parameters,
            })

    artifact_checksums = [a.content_checksum for a in output_artifacts]
    result_checksum = _result_checksum(
        input_checksum=snapshot.input_checksum, version=version, parsed=parsed,
        convergence=convergence, artifact_checksums=artifact_checksums)
    result = SimulationResult(
        organisation_id=workflow.organisation_id, workflow_id=workflow.id, job_id=job.id,
        target_kind=workflow.target_kind, target_scientific_id=workflow.target_scientific_id,
        method_definition_id=definition.id, provider_version_id=version.id,
        operational_status=job.status, scientific_status=convergence["scientific_status"],
        convergence_metrics=convergence.get("metrics", {}), convergence_criteria=convergence.get("criteria", {}),
        convergence_evaluator_version=version.convergence_evaluator_version,
        parser_key=version.parser_key, parser_version=version.parser_version,
        parsed_quantities=parsed.get("quantities", {}),
        warnings=list(parsed.get("warnings", [])) + list(convergence.get("warnings", [])),
        method_limitations=list(method["known_limitations"]),
        output_artifact_checksums=artifact_checksums, result_checksum=result_checksum,
    )
    db.add(result); db.flush()

    _extract_property_estimates(
        db, result=result, method=method, parsed=parsed,
        conditions=snapshot.target_conditions, adapter_key=version.adapter_key)

    step.status = "completed" if job.status == SimulationJobStatus.COMPLETED else "failed"
    step.output_checksum = result_checksum
    workflow.status = (
        SimulationWorkflowStatus.COMPLETED if job.status == SimulationJobStatus.COMPLETED
        else SimulationWorkflowStatus.FAILED
    )
    workflow.failure_code = job.failure_code
    workflow.completed_at = now_utc()
    workflow.workflow_checksum = checksum({
        "contract": SIMULATION_CHECKSUM_VERSION,
        "template": [workflow.workflow_template_key, workflow.workflow_template_version],
        "steps": [{"key": s.step_key, "sequence": s.sequence, "input_checksum": s.input_checksum,
                   "output_checksum": s.output_checksum} for s in sorted(workflow.steps, key=lambda x: x.sequence)],
        "result_checksum": result_checksum, "scientific_status": result.scientific_status,
        "failure_code": workflow.failure_code,
    })
    db.commit()
    db.refresh(workflow)
    logger.info("simulation_workflow_completed", extra={
        "workflow_id": workflow.id, "provider_key": version.provider.key, "provider_version": version.version,
        "method_key": definition.key, "operational_status": job.status,
        "convergence_status": result.scientific_status, "input_checksum_prefix": snapshot.input_checksum[:12],
        "result_checksum_prefix": result_checksum[:12], "artifact_count": len(output_artifacts),
    })
    return workflow


def cancel_workflow(db: Session, workflow: SimulationWorkflow) -> SimulationWorkflow:
    if workflow.status in {SimulationWorkflowStatus.COMPLETED, SimulationWorkflowStatus.FAILED}:
        raise ValueError("A finished workflow cannot be cancelled; history is immutable")
    workflow.status = SimulationWorkflowStatus.CANCELLED
    workflow.failure_code = "cancelled_by_user"
    workflow.completed_at = now_utc()
    db.commit()
    return workflow


# ---------------------------------------------------------------------------------------------
# Read models
# ---------------------------------------------------------------------------------------------
def workflow_detail(db: Session, workflow: SimulationWorkflow) -> dict[str, Any]:
    steps = sorted(workflow.steps, key=lambda s: s.sequence)
    jobs = db.query(SimulationJob).filter_by(workflow_id=workflow.id).order_by(SimulationJob.created_at, SimulationJob.id).all()
    artifacts = db.query(SimulationArtifact).filter_by(workflow_id=workflow.id).order_by(SimulationArtifact.created_at, SimulationArtifact.id).all()
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one_or_none()
    estimates = (
        db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).all() if result else []
    )
    snapshot = db.get(SimulationInputSnapshot, workflow.input_snapshot_id)
    route = db.get(SimulationRoute, workflow.route_id)
    version = require_provider_version(db, workflow.provider_version_id)
    return {
        "workflow": workflow, "steps": steps, "jobs": jobs, "artifacts": artifacts, "result": result,
        "property_estimates": estimates, "input_snapshot": snapshot, "route": route,
        "provider": version.provider, "provider_version": version,
        "warning": SIMULATION_WARNING, "evidence_separation": EVIDENCE_SEPARATION_NOTE,
    }


def target_simulation_history(
    db: Session, *, target_kind: str, target_id: str, organisation_id: str, offset: int = 0, limit: int = 50
) -> dict[str, Any]:
    limit = min(limit, MAX_PAGE_SIZE)
    query = db.query(SimulationWorkflow).filter(
        SimulationWorkflow.organisation_id == organisation_id,
        SimulationWorkflow.target_kind == target_kind,
        SimulationWorkflow.target_scientific_id == target_id,
    )
    total = query.count()
    rows = query.order_by(SimulationWorkflow.created_at.desc(), SimulationWorkflow.id).offset(offset).limit(limit).all()
    results = {
        r.workflow_id: r for r in
        db.query(SimulationResult).filter(SimulationResult.workflow_id.in_([w.id for w in rows])).all()
    } if rows else {}
    items = [
        {
            "workflow_id": w.id, "status": w.status, "failure_code": w.failure_code,
            "method_definition_id": w.method_definition_id, "provider_version_id": w.provider_version_id,
            "requested_property_key": w.requested_property_key, "requested_fidelity": w.requested_fidelity,
            "workflow_checksum": w.workflow_checksum, "created_at": w.created_at,
            "scientific_status": results[w.id].scientific_status if w.id in results else None,
            "result_checksum": results[w.id].result_checksum if w.id in results else None,
            "scientific_origin": "physics_simulation",
        }
        for w in rows
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit, "warning": SIMULATION_WARNING}


def assert_simulation_integrity(db: Session) -> dict[str, Any]:
    """Structural proof that Phase 6 has not manufactured evidence or predictions."""
    from app.models.entities import MaterialPropertyObservation, PropertyPrediction

    converged = db.query(SimulationResult).filter_by(scientific_status=SimulationScientificStatus.CONVERGED).count()
    estimates = db.query(SimulationPropertyEstimate).count()
    non_converged_with_estimates = (
        db.query(SimulationPropertyEstimate)
        .join(SimulationResult, SimulationResult.id == SimulationPropertyEstimate.simulation_result_id)
        .filter(SimulationResult.scientific_status != SimulationScientificStatus.CONVERGED)
        .count()
    )
    return {
        "material_observation_count": db.query(MaterialPropertyObservation).count(),
        "property_prediction_count": db.query(PropertyPrediction).count(),
        "simulation_result_count": db.query(SimulationResult).count(),
        "converged_simulation_result_count": converged,
        "simulation_property_estimate_count": estimates,
        "estimates_from_non_converged_results": non_converged_with_estimates,
        "simulation_created_observations": 0,
        "simulation_created_predictions": 0,
        "warning": SIMULATION_WARNING,
    }


# ---------------------------------------------------------------------------------------------
# Explicit selection policy — default comparison behaviour is unchanged
# ---------------------------------------------------------------------------------------------
def select_simulation_value(
    db: Session, *, project_id: str, property_key: str, target_id: str, organisation_id: str
) -> dict[str, Any]:
    """Return a simulated value ONLY when an explicit selection policy record exists."""
    definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
    if definition is None:
        return {"selected": False, "policy": SimulationValueSelectionPolicy.EVIDENCE_THEN_PREDICTION,
                "reason": "Unknown property definition"}
    policy = db.query(SimulationSelectionPolicyRecord).filter_by(
        project_id=project_id, property_definition_id=definition.id, target_scientific_id=target_id,
        organisation_id=organisation_id,
    ).one_or_none()
    if policy is None:
        return {
            "selected": False, "policy": SimulationValueSelectionPolicy.EVIDENCE_THEN_PREDICTION,
            "reason": "No explicit simulation selection policy exists; evidence-then-prediction behaviour is unchanged.",
        }
    result = db.query(SimulationResult).filter_by(workflow_id=policy.simulation_workflow_id).one_or_none()
    if result is None or result.scientific_status != SimulationScientificStatus.CONVERGED:
        return {"selected": False, "policy": policy.policy_key,
                "reason": "The selected workflow has no converged simulation result."}
    estimate = db.query(SimulationPropertyEstimate).filter_by(
        simulation_result_id=result.id, property_definition_id=definition.id).one_or_none()
    if estimate is None:
        return {"selected": False, "policy": policy.policy_key,
                "reason": "The selected workflow produced no estimate for this property."}
    return {
        "selected": True, "policy": policy.policy_key, "policy_version": policy.policy_version,
        "simulation_workflow_id": policy.simulation_workflow_id, "result_checksum": result.result_checksum,
        "canonical_value": estimate.canonical_value, "canonical_unit": estimate.canonical_unit,
        "numerical_tolerance": estimate.numerical_tolerance, "tolerance_basis": estimate.tolerance_basis,
        "method_limitations": estimate.method_limitations, "scientific_origin": "physics_simulation",
        "reason": "An explicit, versioned simulation selection policy is recorded for this project/property/target.",
    }


def campaign_escalation_targets(db: Session, *, campaign_id: str, organisation_id: str, candidate_ids: list[str]) -> list[dict[str, Any]]:
    """Map campaign candidates to simulation targets. Reads only; campaign history is never touched."""
    rows = (
        db.query(Candidate)
        .options(selectinload(Candidate.material), selectinload(Candidate.hypothesis))
        .filter(Candidate.id.in_(candidate_ids))
        .all()
    )
    targets = []
    for candidate in rows:
        if candidate.candidate_kind == "known_material" and candidate.material_id:
            targets.append({"candidate_id": candidate.id, "target_kind": "known_material",
                            "target_id": candidate.material_id,
                            "display_name": candidate.material.display_name if candidate.material else candidate.material_id})
        elif candidate.hypothesis_id:
            targets.append({"candidate_id": candidate.id, "target_kind": "hypothesis",
                            "target_id": candidate.hypothesis_id,
                            "display_name": candidate.hypothesis.display_label if candidate.hypothesis else candidate.hypothesis_id})
    return targets


def method_descriptors(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "key": row.key, "display_name": row.display_name, "method_family": row.method_family,
            "purpose": row.purpose, "description": row.description, "fidelity": row.fidelity,
            "required_representation_types": row.required_representation_types,
            "required_parameters": row.required_parameters, "output_property_keys": row.output_property_keys,
            "output_units": row.output_units, "convergence_semantics": row.convergence_semantics,
            "known_limitations": row.known_limitations, "status": row.status,
            "definition_version": row.definition_version,
        }
        for row in db.query(SimulationMethodDefinition).order_by(SimulationMethodDefinition.key).all()
    ]


def provider_descriptor(db: Session, provider: SimulationProvider) -> dict[str, Any]:
    return {
        "id": provider.id, "key": provider.key, "display_name": provider.display_name,
        "provider_type": provider.provider_type, "method_family": provider.method_family,
        "description": provider.description, "status": provider.status, "safety_class": provider.safety_class,
        "approved_execution_mode": provider.approved_execution_mode,
        "adapters": [adapter_descriptor(v.adapter_key) for v in provider.versions],
    }
