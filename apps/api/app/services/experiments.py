from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CampaignConstraintModelPolicy,
    CampaignIteration,
    CampaignObjective,
    Candidate,
    CandidateChangeRecord,
    CandidateHypothesis,
    CandidateHypothesisComponent,
    CandidateHypothesisProcessParameter,
    CandidateLineageEdge,
    CandidateSearchSpace,
    Constraint,
    Material,
    MaterialPropertyObservation,
    OptimizationDecisionRecord,
    ParetoFrontSnapshot,
    PredictionRun,
    PropertyPrediction,
    ReplacementProject,
    SubstitutionRule,
    User,
    VirtualCandidateEvaluation,
    VirtualExperimentCampaign,
)
from app.services.evaluation import evaluate_constraint
from app.services.generation import (
    FINGERPRINT_VERSION,
    candidate_fingerprint,
    get_search_space,
    structural_screen,
)
from app.services.prediction import (
    execute_prediction_run,
    get_model_version,
    interval_constraint_status,
    model_version_executable,
    prediction_map_for_run,
    preview_prediction_run,
    require_model_version,
)
from app.services.selection import build_selection_context
from app.services.specification import compile_specification
from app.services.units import UnitError, convert

logger = logging.getLogger("tinkerlab.virtual_experiments")

CAMPAIGN_CONTRACT_VERSION = "campaign-v1"
EVALUATION_CHECKSUM_VERSION = "virtual-evaluation-v1"
MAX_SYNC_ITERATIONS = 5
MAX_POOL_SIZE = 200
MAX_PARENTS = 100
MAX_CHILDREN_PER_ITERATION = 200
MAX_TOTAL_NEW_CANDIDATES = 500
VIRTUAL_WARNING = "VIRTUAL EVALUATION — MODEL-BASED; not a physical experiment or physics simulation."


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class PolicyDescriptor:
    key: str
    version: str
    deterministic: bool
    min_objectives: int
    max_objectives: int
    uncertainty_semantics: str
    unknown_handling: str
    maximum_safe_candidate_pool: int = MAX_POOL_SIZE


POLICIES: dict[str, PolicyDescriptor] = {
    "robust_pareto_v1": PolicyDescriptor(
        key="robust_pareto_v1", version="1.0", deterministic=True, min_objectives=1, max_objectives=5,
        uncertainty_semantics="maximize uses lower interval bound; minimize uses upper interval bound; target uses worst interval distance",
        unknown_handling="unknown hard constraints remain uncertain; incomplete objectives are excluded from Pareto sorting",
    ),
    "uncertainty_exploration_v1": PolicyDescriptor(
        key="uncertainty_exploration_v1", version="1.0", deterministic=True, min_objectives=1, max_objectives=5,
        uncertainty_semantics="Pareto uses conservative bounds; parent selection prioritizes non-failed candidates with larger normalized interval widths",
        unknown_handling="hard failures excluded; uncertain candidates can be selected for exploration",
    ),
    "lexicographic_pareto_baseline_v1": PolicyDescriptor(
        key="lexicographic_pareto_baseline_v1", version="1.0", deterministic=True, min_objectives=1, max_objectives=5,
        uncertainty_semantics="Pareto uses conservative bounds; stable lexicographic tie-breaking by objective sequence and candidate identity",
        unknown_handling="unknown hard constraints remain uncertain",
    ),
}


class VirtualExperimentPolicy(Protocol):
    key: str
    version: str

    def validate_campaign(self, campaign: VirtualExperimentCampaign) -> list[dict[str, Any]]: ...


@dataclass
class ObjectiveValue:
    property_key: str
    direction: str
    origin: str
    point: float | None
    lower: float | None
    upper: float | None
    unit: str | None
    applicability: str | None
    model_version_id: str
    prediction_id: str | None
    conservative_value: float | None
    completeness: str
    uncertainty_width: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "property": self.property_key,
            "direction": self.direction,
            "origin": self.origin,
            "point": self.point,
            "lower": self.lower,
            "upper": self.upper,
            "unit": self.unit,
            "applicability": self.applicability,
            "model_version_id": self.model_version_id,
            "prediction_id": self.prediction_id,
            "conservative_value": self.conservative_value,
            "completeness": self.completeness,
            "uncertainty_width": self.uncertainty_width,
        }


def policy_descriptor(key: str) -> PolicyDescriptor:
    if key not in POLICIES:
        raise ValueError("Unknown virtual experiment policy")
    return POLICIES[key]


def _campaign_objectives(db: Session, campaign_id: str) -> list[CampaignObjective]:
    return db.query(CampaignObjective).filter_by(campaign_id=campaign_id).order_by(CampaignObjective.sequence, CampaignObjective.id).all()


def _constraint_policies(db: Session, campaign_id: str) -> list[CampaignConstraintModelPolicy]:
    return db.query(CampaignConstraintModelPolicy).filter_by(campaign_id=campaign_id, enabled=True).order_by(CampaignConstraintModelPolicy.constraint_id).all()


def _candidate_identity(candidate: Candidate) -> str:
    if candidate.candidate_kind == "hypothesis" and candidate.hypothesis:
        return f"hypothesis:{candidate.hypothesis.deterministic_fingerprint}"
    if candidate.material:
        return f"known:{candidate.material.canonical_name}"
    return f"candidate:{candidate.id}"


def _load_candidate_pool(db: Session, campaign: VirtualExperimentCampaign, *, next_pool_ids: list[str] | None = None) -> list[Candidate]:
    configured = list(campaign.metadata_json.get("initial_candidate_ids") or [])
    ids = next_pool_ids if next_pool_ids is not None else configured
    query = db.query(Candidate).options(
        selectinload(Candidate.material).selectinload(Material.observations),
        selectinload(Candidate.hypothesis).selectinload(CandidateHypothesis.components),
        selectinload(Candidate.hypothesis).selectinload(CandidateHypothesis.process_parameters),
    ).filter(Candidate.project_id == campaign.project_id)
    if ids:
        query = query.filter(Candidate.id.in_(ids))
    elif not bool(campaign.metadata_json.get("include_known_candidates", True)):
        query = query.filter(Candidate.candidate_kind == "hypothesis")
    rows = query.all()
    rows = [r for r in rows if r.candidate_kind == "known_material" or (r.hypothesis and r.hypothesis.structural_validity == "valid")]
    rows.sort(key=lambda c: (_candidate_identity(c), c.id))
    return rows[:MAX_POOL_SIZE]


def _campaign_configuration_payload(
    *,
    spec_checksum: str,
    search_space: CandidateSearchSpace,
    policy: PolicyDescriptor,
    random_seed: int,
    max_iterations: int,
    max_total_new_candidates: int,
    max_candidates_per_iteration: int,
    max_parents_per_iteration: int,
    objectives: list[dict[str, Any]],
    constraint_policies: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "campaign_contract": CAMPAIGN_CONTRACT_VERSION,
        "specification_checksum": spec_checksum,
        "search_space": {"id": search_space.id, "version": search_space.version, "checksum": search_space.checksum},
        "policy": {"key": policy.key, "version": policy.version},
        "seed": random_seed,
        "budgets": {
            "max_iterations": max_iterations,
            "max_total_new_candidates": max_total_new_candidates,
            "max_candidates_per_iteration": max_candidates_per_iteration,
            "max_parents_per_iteration": max_parents_per_iteration,
        },
        "objectives": objectives,
        "constraint_policies": constraint_policies,
        "mutation_types": sorted(metadata.get("mutation_types") or []),
        "exploration_enabled": bool(metadata.get("exploration_enabled", True)),
        "initial_candidate_ids": sorted(metadata.get("initial_candidate_ids") or []),
        "include_known_candidates": bool(metadata.get("include_known_candidates", True)),
        "convergence_unchanged_iterations": metadata.get("convergence_unchanged_iterations"),
        "candidate_fingerprint_version": FINGERPRINT_VERSION,
    }


def create_campaign(db: Session, project: ReplacementProject, payload: dict[str, Any]) -> VirtualExperimentCampaign:
    if not db.get(User, payload["created_by"]):
        raise ValueError("created_by user not found")
    if payload["max_iterations"] > MAX_SYNC_ITERATIONS:
        raise ValueError(f"Phase-5 campaign maximum is {MAX_SYNC_ITERATIONS} iterations")
    if payload["max_total_new_candidates"] > MAX_TOTAL_NEW_CANDIDATES:
        raise ValueError(f"Phase-5 campaign maximum is {MAX_TOTAL_NEW_CANDIDATES} new candidates")
    if payload["max_candidates_per_iteration"] > MAX_CHILDREN_PER_ITERATION:
        raise ValueError(f"Phase-5 maximum children per iteration is {MAX_CHILDREN_PER_ITERATION}")
    if payload["max_parents_per_iteration"] > MAX_PARENTS:
        raise ValueError(f"Phase-5 maximum parents per iteration is {MAX_PARENTS}")
    search_space = get_search_space(db, payload["search_space_id"])
    if not search_space or search_space.project_id != project.id or search_space.organisation_id != project.organisation_id:
        raise ValueError("Search space not found in project scope")
    policy = policy_descriptor(payload["policy_key"])
    spec = compile_specification(project)
    objectives_payload: list[dict[str, Any]] = []
    for sequence, objective in enumerate(payload["objectives"]):
        version = get_model_version(db, objective["model_version_id"])
        if not version:
            raise ValueError(f"Objective {objective['property_key']} references unknown model version")
        if version.model.organisation_id not in {None, project.organisation_id}:
            raise ValueError(f"Objective {objective['property_key']} references a model outside organisation scope")
        executable, reason = model_version_executable(version)
        if not executable:
            raise ValueError(f"Objective {objective['property_key']} model is not executable: {reason}")
        if version.target_property_key != objective["property_key"]:
            raise ValueError(f"Objective model property mismatch for {objective['property_key']}")
        objectives_payload.append({
            "property_key": objective["property_key"], "direction": objective["direction"], "weight": objective["weight"],
            "priority": objective["priority"], "target_value": objective.get("target_value"), "target_unit": objective.get("target_unit"),
            "model_version_id": objective["model_version_id"], "evaluation_mode": objective.get("evaluation_mode", "model_prediction"),
            "sequence": sequence, "metadata": objective.get("metadata") or {}, "artifact_checksum": version.artifact_checksum,
        })
    if not (policy.min_objectives <= len(objectives_payload) <= policy.max_objectives):
        raise ValueError("Campaign objective count is outside selected policy capability")
    constraint_payload: list[dict[str, Any]] = []
    project_constraints = {c.id: c for c in project.constraints}
    for item in payload.get("constraint_policies") or []:
        constraint = project_constraints.get(item["constraint_id"])
        if not constraint:
            raise ValueError("Constraint policy references a constraint outside the project")
        model_id = item.get("model_version_id")
        artifact = None
        if model_id:
            version = get_model_version(db, model_id)
            if not version:
                raise ValueError("Constraint policy references unknown model version")
            if version.model.organisation_id not in {None, project.organisation_id}:
                raise ValueError("Constraint policy references a model outside organisation scope")
            executable, reason = model_version_executable(version)
            if not executable:
                raise ValueError(f"Constraint model is not executable: {reason}")
            if version.target_property_key != constraint.property_key:
                raise ValueError("Constraint model property does not match project constraint")
            artifact = version.artifact_checksum
        constraint_payload.append({**item, "artifact_checksum": artifact})
    metadata = {
        **(payload.get("metadata") or {}),
        "initial_candidate_ids": list(payload.get("initial_candidate_ids") or []),
        "include_known_candidates": bool(payload.get("include_known_candidates", True)),
        "exploration_enabled": bool(payload.get("exploration_enabled", True)),
        "mutation_types": list(payload.get("mutation_types") or []),
        "convergence_unchanged_iterations": payload.get("convergence_unchanged_iterations"),
        "virtual_warning": VIRTUAL_WARNING,
    }
    config_payload = _campaign_configuration_payload(
        spec_checksum=spec["checksum"], search_space=search_space, policy=policy, random_seed=payload["random_seed"],
        max_iterations=payload["max_iterations"], max_total_new_candidates=payload["max_total_new_candidates"],
        max_candidates_per_iteration=payload["max_candidates_per_iteration"], max_parents_per_iteration=payload["max_parents_per_iteration"],
        objectives=objectives_payload, constraint_policies=constraint_payload, metadata=metadata,
    )
    campaign = VirtualExperimentCampaign(
        **({"id": payload["id"]} if payload.get("id") else {}),
        organisation_id=project.organisation_id, project_id=project.id, name=payload["name"], description=payload.get("description"),
        replacement_specification_checksum=spec["checksum"], search_space_id=search_space.id, search_space_version=search_space.version,
        search_space_checksum=search_space.checksum, policy_key=policy.key, policy_version=policy.version,
        configuration_checksum=checksum(config_payload), random_seed=payload["random_seed"], max_iterations=payload["max_iterations"],
        max_total_new_candidates=payload["max_total_new_candidates"], max_candidates_per_iteration=payload["max_candidates_per_iteration"],
        max_parents_per_iteration=payload["max_parents_per_iteration"], status="draft", created_by=payload["created_by"], metadata_json=metadata,
    )
    db.add(campaign); db.flush()
    for item in objectives_payload:
        meta = item.pop("metadata"); item.pop("artifact_checksum", None)
        db.add(CampaignObjective(campaign_id=campaign.id, **item, metadata_json=meta))
    for item in payload.get("constraint_policies") or []:
        meta = item.get("metadata") or {}
        values = {k: v for k, v in item.items() if k != "metadata"}
        db.add(CampaignConstraintModelPolicy(campaign_id=campaign.id, **values, metadata_json=meta))
    db.commit(); db.refresh(campaign)
    return campaign


def validate_campaign(db: Session, campaign: VirtualExperimentCampaign) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    project = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material), selectinload(ReplacementProject.constraints), selectinload(ReplacementProject.objectives)
    ).filter_by(id=campaign.project_id, organisation_id=campaign.organisation_id).one_or_none()
    if not project:
        return [{"code": "PROJECT_SCOPE_INVALID", "message": "Campaign project is outside organisation scope", "severity": "error"}]
    spec = compile_specification(project)
    if spec["checksum"] != campaign.replacement_specification_checksum:
        issues.append({"code": "SPECIFICATION_CHECKSUM_MISMATCH", "message": "Project replacement specification changed after campaign creation", "severity": "error"})
    space = get_search_space(db, campaign.search_space_id)
    if not space or space.project_id != project.id or space.organisation_id != project.organisation_id:
        issues.append({"code": "SEARCH_SPACE_SCOPE_INVALID", "message": "Campaign search space is unavailable", "severity": "error"})
    elif space.checksum != campaign.search_space_checksum or space.version != campaign.search_space_version:
        issues.append({"code": "SEARCH_SPACE_CHECKSUM_MISMATCH", "message": "Search-space semantics changed after campaign creation", "severity": "error"})
    try:
        policy = policy_descriptor(campaign.policy_key)
        if campaign.policy_version != policy.version:
            issues.append({"code": "POLICY_VERSION_MISMATCH", "message": "Pinned policy version does not match registered policy", "severity": "error"})
    except ValueError:
        issues.append({"code": "POLICY_UNREGISTERED", "message": "Campaign policy is not registered", "severity": "error"})
        policy = None
    objectives = _campaign_objectives(db, campaign.id)
    if not objectives:
        issues.append({"code": "NO_OBJECTIVES", "message": "Campaign requires at least one objective", "severity": "error"})
    if policy and not (policy.min_objectives <= len(objectives) <= policy.max_objectives):
        issues.append({"code": "OBJECTIVE_COUNT_UNSUPPORTED", "message": "Objective count outside policy capability", "severity": "error"})
    for obj in objectives:
        version = get_model_version(db, obj.model_version_id)
        if not version:
            issues.append({"code": "MODEL_VERSION_NOT_FOUND", "message": f"Model version missing for {obj.property_key}", "severity": "error"}); continue
        if version.model.organisation_id not in {None, campaign.organisation_id}:
            issues.append({"code": "MODEL_SCOPE_INVALID", "message": f"{obj.property_key}: model is outside organisation scope", "severity": "error"})
        executable, reason = model_version_executable(version)
        if not executable:
            issues.append({"code": "MODEL_NOT_EXECUTABLE", "message": f"{obj.property_key}: {reason}", "severity": "error"})
        if version.target_property_key != obj.property_key:
            issues.append({"code": "MODEL_PROPERTY_MISMATCH", "message": f"Model does not predict {obj.property_key}", "severity": "error"})
        if obj.direction == "target" and (obj.target_value is None or not obj.target_unit):
            issues.append({"code": "TARGET_OBJECTIVE_INCOMPLETE", "message": f"Target objective {obj.property_key} needs target value/unit", "severity": "error"})
    project_constraints = {c.id: c for c in project.constraints}
    for constraint_policy in _constraint_policies(db, campaign.id):
        constraint = project_constraints.get(constraint_policy.constraint_id)
        if not constraint:
            issues.append({"code": "CONSTRAINT_POLICY_SCOPE_INVALID", "message": "Constraint policy references a constraint outside project scope", "severity": "error"})
            continue
        if constraint_policy.model_version_id:
            version = get_model_version(db, constraint_policy.model_version_id)
            if not version:
                issues.append({"code": "CONSTRAINT_MODEL_VERSION_NOT_FOUND", "message": f"Model version missing for {constraint.property_key}", "severity": "error"})
                continue
            if version.model.organisation_id not in {None, campaign.organisation_id}:
                issues.append({"code": "CONSTRAINT_MODEL_SCOPE_INVALID", "message": f"{constraint.property_key}: model is outside organisation scope", "severity": "error"})
            if version.target_property_key != constraint.property_key:
                issues.append({"code": "CONSTRAINT_MODEL_PROPERTY_MISMATCH", "message": f"Model does not predict {constraint.property_key}", "severity": "error"})
    if not (1 <= campaign.max_iterations <= MAX_SYNC_ITERATIONS):
        issues.append({"code": "INVALID_ITERATION_BUDGET", "message": "Iteration budget outside Phase-5 limits", "severity": "error"})
    if not (0 <= campaign.max_total_new_candidates <= MAX_TOTAL_NEW_CANDIDATES):
        issues.append({"code": "INVALID_CANDIDATE_BUDGET", "message": "Total new-candidate budget outside Phase-5 limits", "severity": "error"})
    pool = _load_candidate_pool(db, campaign)
    if not pool:
        issues.append({"code": "EMPTY_CANDIDATE_POOL", "message": "Campaign has no eligible candidates", "severity": "error"})
    if len(pool) > MAX_POOL_SIZE:
        issues.append({"code": "POOL_TOO_LARGE", "message": "Candidate pool exceeds Phase-5 bounded maximum", "severity": "error"})
    candidate_ids = {c.id for c in pool}
    configured_ids = set(campaign.metadata_json.get("initial_candidate_ids") or [])
    if configured_ids and not configured_ids.issubset(candidate_ids):
        issues.append({"code": "CANDIDATE_SCOPE_OR_STATE_INVALID", "message": "One or more configured candidates are unavailable/invalid", "severity": "error"})
    return issues


def _objective_conditions(obj: CampaignObjective) -> dict[str, Any]:
    raw = obj.metadata_json.get("conditions") if obj.metadata_json else None
    return raw if isinstance(raw, dict) else {}


def _constraint_conditions(constraint: Constraint, policy: CampaignConstraintModelPolicy | None) -> dict[str, Any]:
    if policy and policy.condition_mapping:
        return policy.condition_mapping
    raw = (constraint.metadata_json or {}).get("conditions")
    return raw if isinstance(raw, dict) else {}


def preview_campaign(db: Session, campaign: VirtualExperimentCampaign) -> dict[str, Any]:
    issues = validate_campaign(db, campaign)
    pool = _load_candidate_pool(db, campaign)
    project = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material), selectinload(ReplacementProject.constraints), selectinload(ReplacementProject.objectives)
    ).filter_by(id=campaign.project_id).one()
    applicability: dict[str, dict[str, int]] = {}
    estimated_runs = 0
    targets = [{"candidate_id": c.id} for c in pool]
    if not any(i["severity"] == "error" for i in issues):
        for obj in _campaign_objectives(db, campaign.id):
            version = require_model_version(db, obj.model_version_id)
            preview = preview_prediction_run(db, project, version, targets, obj.property_key, _objective_conditions(obj), {"campaign_preview": campaign.id, "objective_id": obj.id}, campaign.organisation_id)
            applicability[obj.property_key] = {
                "in_domain": preview["in_domain_count"], "borderline": preview["borderline_count"],
                "inapplicable": preview["inapplicable_count"], "target_count": preview["target_count"],
            }
            estimated_runs += 1
        # Constraint prediction needs are forecast only when not already represented by the same model/property/conditions.
        signatures = {(o.property_key, o.model_version_id, checksum(_objective_conditions(o))) for o in _campaign_objectives(db, campaign.id)}
        constraint_by_id = {c.id: c for c in project.constraints}
        for cp in _constraint_policies(db, campaign.id):
            if not cp.model_version_id:
                continue
            constraint = constraint_by_id.get(cp.constraint_id)
            if not constraint:
                continue
            signature = (constraint.property_key, cp.model_version_id, checksum(_constraint_conditions(constraint, cp)))
            if signature not in signatures:
                estimated_runs += 1; signatures.add(signature)
    space = get_search_space(db, campaign.search_space_id)
    mutation_cardinality = 0
    if space:
        mutable = sum(1 for r in space.component_rules if r.mutable and not r.locked and not r.prohibited)
        mutable += sum(1 for r in space.process_rules if not r.locked)
        approved_subs = db.query(SubstitutionRule).filter(
            SubstitutionRule.organisation_id == campaign.organisation_id,
            SubstitutionRule.status == "approved",
            (SubstitutionRule.project_id == campaign.project_id) | (SubstitutionRule.project_id.is_(None)),
        ).count()
        mutation_cardinality = min(MAX_CHILDREN_PER_ITERATION, len(pool) * max(1, mutable * 2 + approved_subs))
    return {
        "valid": not any(i["severity"] == "error" for i in issues), "campaign_id": campaign.id,
        "policy_key": campaign.policy_key, "policy_version": campaign.policy_version,
        "specification_checksum": campaign.replacement_specification_checksum, "search_space_checksum": campaign.search_space_checksum,
        "configuration_checksum": campaign.configuration_checksum, "candidate_pool_size": len(pool),
        "objective_count": len(_campaign_objectives(db, campaign.id)),
        "objective_models": [{"property_key": o.property_key, "direction": o.direction, "model_version_id": o.model_version_id} for o in _campaign_objectives(db, campaign.id)],
        "applicability_forecast": applicability, "estimated_prediction_runs": estimated_runs,
        "estimated_mutation_cardinality": mutation_cardinality,
        "budgets": {"max_iterations": campaign.max_iterations, "max_total_new_candidates": campaign.max_total_new_candidates, "max_candidates_per_iteration": campaign.max_candidates_per_iteration, "max_parents_per_iteration": campaign.max_parents_per_iteration},
        "validation_issues": issues, "warning": VIRTUAL_WARNING,
    }


def _prediction_signature(property_key: str, model_version_id: str, conditions: dict[str, Any]) -> tuple[str, str, str]:
    return property_key, model_version_id, checksum(conditions)


def _prediction_needs(db: Session, campaign: VirtualExperimentCampaign, project: ReplacementProject) -> list[tuple[tuple[str, str, str], str, str, dict[str, Any], str | None, dict[str, Any]]]:
    needs: dict[tuple[str, str, str], tuple[str, str, dict[str, Any], str | None, dict[str, Any]]] = {}
    for obj in _campaign_objectives(db, campaign.id):
        conditions = _objective_conditions(obj)
        version = require_model_version(db, obj.model_version_id)
        signature = _prediction_signature(obj.property_key, obj.model_version_id, conditions)
        needs[signature] = (obj.property_key, obj.model_version_id, conditions, version.canonical_output_unit, {"campaign_id": campaign.id, "objective_id": obj.id, "purpose": "objective"})
    constraint_by_id = {c.id: c for c in project.constraints}
    for cp in _constraint_policies(db, campaign.id):
        if not cp.model_version_id or cp.allowed_value_origin == "known_evidence_only":
            continue
        c = constraint_by_id.get(cp.constraint_id)
        if not c:
            continue
        conditions = _constraint_conditions(c, cp)
        version = require_model_version(db, cp.model_version_id)
        signature = _prediction_signature(c.property_key, cp.model_version_id, conditions)
        needs.setdefault(signature, (c.property_key, cp.model_version_id, conditions, version.canonical_output_unit, {"campaign_id": campaign.id, "constraint_policy_id": cp.id, "purpose": "hard_constraint"}))
    return [(sig, *values) for sig, values in sorted(needs.items(), key=lambda x: x[0])]


def _run_predictions_for_pool(db: Session, campaign: VirtualExperimentCampaign, project: ReplacementProject, pool: list[Candidate], iteration_number: int) -> tuple[list[str], dict[tuple[tuple[str, str, str], str], PropertyPrediction]]:
    targets = [{"candidate_id": c.id} for c in pool]
    run_ids: list[str] = []
    prediction_lookup: dict[tuple[tuple[str, str, str], str], PropertyPrediction] = {}
    for signature, property_key, model_version_id, conditions, output_unit, config in _prediction_needs(db, campaign, project):
        version = require_model_version(db, model_version_id)
        run = execute_prediction_run(
            db, project, version, targets, property_key, conditions, output_unit,
            {**config, "campaign_iteration": iteration_number, "campaign_configuration_checksum": campaign.configuration_checksum},
            campaign.created_by, campaign.organisation_id,
        )
        run_ids.append(run.id)
        mapping = prediction_map_for_run(db, run.id, project.id, campaign.organisation_id)
        for candidate in pool:
            prediction = mapping.get((candidate.id, property_key))
            if prediction:
                prediction_lookup[(signature, candidate.id)] = prediction
    return run_ids, prediction_lookup


def _known_constraint_results(db: Session, project: ReplacementProject, pool: list[Candidate]) -> dict[str, dict[str, dict[str, Any]]]:
    known = [c for c in pool if c.candidate_kind == "known_material" and c.material]
    material_ids = [project.baseline_material_id, *[c.material_id for c in known if c.material_id]]
    context = build_selection_context(db, material_ids)
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate in known:
        material = candidate.material
        if material is None:
            raise ValueError(f"Known-material candidate {candidate.id} has no linked material record")
        results[candidate.id] = {}
        for constraint in [c for c in project.constraints if c.hard_or_soft == "hard"]:
            results[candidate.id][constraint.id] = evaluate_constraint(db, material, constraint, context.definitions_by_key, context, set())
    return results


def _constraint_prediction(
    constraint: Constraint,
    policy: CampaignConstraintModelPolicy,
    candidate: Candidate,
    prediction_lookup: dict[tuple[tuple[str, str, str], str], PropertyPrediction],
) -> tuple[str, dict[str, Any]]:
    if not policy.model_version_id:
        return "UNKNOWN", {"origin": "none", "reason": "NO_PINNED_MODEL"}
    conditions = _constraint_conditions(constraint, policy)
    signature = _prediction_signature(constraint.property_key, policy.model_version_id, conditions)
    prediction = prediction_lookup.get((signature, candidate.id))
    if not prediction:
        return "UNKNOWN", {"origin": "none", "reason": "NO_PREDICTION"}
    if constraint.comparator == "boolean":
        return "UNKNOWN", {"origin": "model_prediction", "prediction_id": prediction.id, "reason": "NUMERIC_MODEL_CANNOT_EVALUATE_BOOLEAN"}
    status, crosses, reason = interval_constraint_status(prediction, constraint.comparator, constraint.target_value, constraint.target_value_upper, constraint.target_unit)
    return status, {
        "origin": "model_prediction", "prediction_id": prediction.id, "model_version_id": prediction.model_version_id,
        "point": prediction.numeric_point_estimate, "lower": prediction.uncertainty_lower, "upper": prediction.uncertainty_upper,
        "unit": prediction.output_unit, "applicability": prediction.applicability_status,
        "uncertainty_crosses_constraint": crosses, "reason": reason,
    }


def _classify_feasibility(
    db: Session,
    campaign: VirtualExperimentCampaign,
    project: ReplacementProject,
    candidate: Candidate,
    known_results: dict[str, dict[str, dict[str, Any]]],
    prediction_lookup: dict[tuple[tuple[str, str, str], str], PropertyPrediction],
    policies: dict[str, CampaignConstraintModelPolicy],
) -> tuple[str, int, int, int, dict[str, Any]]:
    details: dict[str, Any] = {}
    passes = fails = unknowns = 0
    for constraint in [c for c in project.constraints if c.hard_or_soft == "hard"]:
        policy = policies.get(constraint.id)
        evidence_result = known_results.get(candidate.id, {}).get(constraint.id) if candidate.candidate_kind == "known_material" else None
        chosen_status = "UNKNOWN"; chosen_detail: dict[str, Any] = {"origin": "none", "reason": "NO_APPLICABLE_EVIDENCE_OR_PINNED_MODEL"}
        if policy and policy.allowed_value_origin == "model_prediction_only":
            chosen_status, chosen_detail = _constraint_prediction(constraint, policy, candidate, prediction_lookup)
        elif evidence_result and evidence_result["status"] != "UNKNOWN":
            chosen_status = evidence_result["status"]
            chosen_detail = {"origin": "known_evidence", "observation_id": evidence_result.get("selected_observation_id"), "evidence_id": evidence_result.get("evidence_id"), "value": evidence_result.get("observed_value"), "unit": evidence_result.get("observed_unit")}
        elif policy and policy.allowed_value_origin in {"model_prediction_only", "known_evidence_then_prediction"}:
            chosen_status, chosen_detail = _constraint_prediction(constraint, policy, candidate, prediction_lookup)
        elif evidence_result:
            chosen_detail = {"origin": "known_evidence", "reason": evidence_result.get("unknown_reason")}
        details[constraint.id] = {"property_key": constraint.property_key, "status": chosen_status, **chosen_detail}
        if chosen_status == "PASS": passes += 1
        elif chosen_status == "FAIL": fails += 1
        else: unknowns += 1
    feasibility = "robustly_infeasible" if fails else ("uncertain" if unknowns else "robustly_feasible")
    return feasibility, passes, fails, unknowns, details


def _objective_value(obj: CampaignObjective, prediction: PropertyPrediction | None) -> ObjectiveValue:
    if not prediction or prediction.status != "predicted" or prediction.numeric_point_estimate is None or prediction.uncertainty_lower is None or prediction.uncertainty_upper is None:
        return ObjectiveValue(obj.property_key, obj.direction, "model_prediction", None, None, None, None, prediction.applicability_status if prediction else None, obj.model_version_id, prediction.id if prediction else None, None, "incomplete", None)
    point = float(prediction.numeric_point_estimate); lower = float(prediction.uncertainty_lower); upper = float(prediction.uncertainty_upper)
    unit = prediction.output_unit
    if lower > upper: lower, upper = upper, lower
    if obj.direction == "maximize":
        conservative = lower
    elif obj.direction == "minimize":
        conservative = upper
    else:
        if obj.target_value is None or not obj.target_unit or not unit:
            return ObjectiveValue(obj.property_key, obj.direction, "model_prediction", point, lower, upper, unit, prediction.applicability_status, obj.model_version_id, prediction.id, None, "incomplete", upper-lower)
        try:
            p = convert(point, unit, obj.target_unit); lo = convert(lower, unit, obj.target_unit); hi = convert(upper, unit, obj.target_unit)
        except UnitError:
            return ObjectiveValue(obj.property_key, obj.direction, "model_prediction", point, lower, upper, unit, prediction.applicability_status, obj.model_version_id, prediction.id, None, "incomplete", upper-lower)
        point, lower, upper, unit = p, min(lo, hi), max(lo, hi), obj.target_unit
        conservative = max(abs(lower - obj.target_value), abs(upper - obj.target_value))
    return ObjectiveValue(obj.property_key, obj.direction, "model_prediction", point, lower, upper, unit, prediction.applicability_status, obj.model_version_id, prediction.id, conservative, "complete", upper-lower)


def _objective_signature(obj: CampaignObjective) -> tuple[str, str, str]:
    return _prediction_signature(obj.property_key, obj.model_version_id, _objective_conditions(obj))


def _minimization_vector(objective_values: dict[str, ObjectiveValue], objectives: list[CampaignObjective]) -> tuple[float, ...] | None:
    vector: list[float] = []
    for obj in objectives:
        value = objective_values[obj.property_key]
        if value.conservative_value is None:
            return None
        if obj.direction == "maximize": vector.append(-value.conservative_value)
        else: vector.append(value.conservative_value)
    return tuple(vector)


def _dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(x <= y for x, y in zip(a, b, strict=True)) and any(x < y for x, y in zip(a, b, strict=True))


def non_dominated_sort(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    comparable = [r for r in records if r.get("pareto_vector") is not None]
    comparable.sort(key=lambda r: r["identity"])
    domination_counts: dict[str, int] = {r["candidate"].id: 0 for r in comparable}
    dominates_map: dict[str, list[str]] = {r["candidate"].id: [] for r in comparable}
    by_id = {r["candidate"].id: r for r in comparable}
    for i, a in enumerate(comparable):
        for b in comparable[i + 1:]:
            if _dominates(a["pareto_vector"], b["pareto_vector"]):
                dominates_map[a["candidate"].id].append(b["candidate"].id); domination_counts[b["candidate"].id] += 1
            elif _dominates(b["pareto_vector"], a["pareto_vector"]):
                dominates_map[b["candidate"].id].append(a["candidate"].id); domination_counts[a["candidate"].id] += 1
    fronts: list[list[dict[str, Any]]] = []
    current = sorted([by_id[cid] for cid, count in domination_counts.items() if count == 0], key=lambda r: r["identity"])
    while current:
        fronts.append(current)
        next_ids: list[str] = []
        for item in current:
            cid = item["candidate"].id
            for dominated in dominates_map[cid]:
                domination_counts[dominated] -= 1
                if domination_counts[dominated] == 0: next_ids.append(dominated)
        current = sorted([by_id[cid] for cid in set(next_ids)], key=lambda r: r["identity"])
    for rank, front in enumerate(fronts, 1):
        for record in front:
            record["pareto_rank"] = rank
            record["dominance_count"] = sum(1 for other in comparable if other["candidate"].id != record["candidate"].id and _dominates(other["pareto_vector"], record["pareto_vector"]))
    return fronts


def _normalized_uncertainty(values: dict[str, ObjectiveValue]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in values.items():
        if value.point is None or value.uncertainty_width is None:
            result[key] = 1.0
        else:
            scale = max(abs(value.point), 1e-9)
            result[key] = abs(value.uncertainty_width) / scale
    return result


def _select_parents(campaign: VirtualExperimentCampaign, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exploration = bool(campaign.metadata_json.get("exploration_enabled", True))
    eligible = [r for r in records if r["candidate"].candidate_kind == "hypothesis" and r["candidate"].hypothesis and r["candidate"].hypothesis.structural_validity == "valid" and r["feasibility"] != "robustly_infeasible"]
    if not exploration: eligible = [r for r in eligible if r["feasibility"] == "robustly_feasible"]
    if campaign.policy_key == "uncertainty_exploration_v1":
        eligible.sort(key=lambda r: (
            0 if r["feasibility"] == "robustly_feasible" else 1,
            r.get("pareto_rank") or 10_000,
            -sum(r["uncertainty"].values()),
            r["identity"],
        ))
    elif campaign.policy_key == "lexicographic_pareto_baseline_v1":
        eligible.sort(key=lambda r: (
            0 if r["feasibility"] == "robustly_feasible" else 1,
            r.get("pareto_rank") or 10_000,
            r.get("pareto_vector") or tuple([float("inf")]),
            r["identity"],
        ))
    else:
        eligible.sort(key=lambda r: (
            0 if r["feasibility"] == "robustly_feasible" else 1,
            r.get("pareto_rank") or 10_000,
            -sum(r["uncertainty"].values()) if exploration else 0,
            r["identity"],
        ))
    return eligible[: campaign.max_parents_per_iteration]


def _apply_balance(space: CandidateSearchSpace, components: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    if space.total_target is None:
        return components
    total = sum(float(c["amount"]) for c in components if c.get("amount") is not None)
    delta = float(space.total_target) - total
    if abs(delta) <= space.total_tolerance:
        return components
    if not space.balance_component_key:
        return None
    result = [dict(c) for c in components]
    balance = next((c for c in result if c["component_key"] == space.balance_component_key), None)
    if not balance or balance.get("amount") is None:
        return None
    balance["amount"] = round(float(balance["amount"]) + delta, 12)
    return result


def _parent_components(parent: CandidateHypothesis) -> list[dict[str, Any]]:
    return [{
        "component_key": c.component_key, "display_name": c.display_name, "role": c.role, "amount": c.amount,
        "unit": c.unit, "basis": c.basis, "source_baseline_component_id": c.source_baseline_component_id,
        "substitution_rule_id": c.substitution_rule_id, "locked": c.locked, "metadata": c.metadata_json,
    } for c in sorted(parent.components, key=lambda x: (x.sequence, x.id))]


def _require_prediction_run(db: Session, run_id: str) -> PredictionRun:
    run = db.get(PredictionRun, run_id)
    if run is None:
        raise ValueError(f"Prediction run {run_id} referenced by this iteration no longer exists")
    return run


def _require_child_fingerprint(db: Session, candidate_id: str) -> str:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.hypothesis is None:
        raise ValueError(f"Campaign child candidate {candidate_id} no longer resolves to a hypothesis")
    return candidate.hypothesis.deterministic_fingerprint


def _require_search_space(db: Session, campaign: VirtualExperimentCampaign) -> CandidateSearchSpace:
    """The campaign pins a search-space id/version/checksum; a missing row invalidates the campaign."""
    space = get_search_space(db, campaign.search_space_id)
    if space is None:
        raise ValueError(f"Campaign {campaign.id} references search space {campaign.search_space_id}, which no longer exists")
    return space


def _parent_process(parent: CandidateHypothesis) -> list[dict[str, Any]]:
    return [{"process_label": p.process_label, "parameter_key": p.parameter_key, "value": p.value, "unit": p.unit, "source_baseline_state_id": p.source_baseline_state_id, "metadata": p.metadata_json} for p in sorted(parent.process_parameters, key=lambda x: (x.parameter_key, x.id))]


def _mutation_proposals(db: Session, campaign: VirtualExperimentCampaign, parent: CandidateHypothesis, limit: int) -> list[dict[str, Any]]:
    space = _require_search_space(db, campaign)
    components = _parent_components(parent); process = _parent_process(parent)
    rules = {r.component_key: r for r in space.component_rules}
    allowed_mutations = set(campaign.metadata_json.get("mutation_types") or [])
    proposals: list[dict[str, Any]] = []
    if "component_amount" in allowed_mutations:
        for comp in components:
            rule = rules.get(comp["component_key"])
            if not rule or not rule.mutable or rule.locked or rule.prohibited or comp.get("locked") or comp.get("amount") is None:
                continue
            step = rule.step_amount
            if not step or step <= 0: continue
            for sign in (-1, 1):
                value = round(float(comp["amount"]) + sign * step, 12)
                if rule.min_amount is not None and value < rule.min_amount - 1e-12: continue
                if rule.max_amount is not None and value > rule.max_amount + 1e-12: continue
                child = [dict(c) for c in components]
                target = next(c for c in child if c["component_key"] == comp["component_key"]); before = target["amount"]; target["amount"] = value
                balanced = _apply_balance(space, child)
                if balanced is None: continue
                child = balanced
                proposals.append({"kind": "component_amount", "components": child, "process": [dict(p) for p in process], "change": {"change_type": "component_amount_change", "target_path": f"components.{comp['component_key']}.amount", "before": {"value": before, "unit": comp.get("unit")}, "after": {"value": value, "unit": comp.get("unit")}, "rule_id": None, "rationale": "Autonomous bounded +/- one configured step within the active Phase-3 search space."}})
    if "component_substitution" in allowed_mutations:
        approved = db.query(SubstitutionRule).filter(
            SubstitutionRule.organisation_id == campaign.organisation_id, SubstitutionRule.status == "approved",
            (SubstitutionRule.project_id == campaign.project_id) | (SubstitutionRule.project_id.is_(None)),
        ).order_by(SubstitutionRule.source_component_key, SubstitutionRule.replacement_component_key, SubstitutionRule.id).all()
        for substitution in approved:
            source = next((c for c in components if c["component_key"] == substitution.source_component_key), None)
            if not source or source.get("locked"): continue
            if any(c["component_key"] == substitution.replacement_component_key for c in components): continue
            child = [dict(c) for c in components]
            target = next(c for c in child if c["component_key"] == substitution.source_component_key)
            before_key = target["component_key"]; before_name = target["display_name"]
            target["component_key"] = substitution.replacement_component_key; target["display_name"] = substitution.replacement_display_name; target["substitution_rule_id"] = substitution.id
            proposals.append({"kind": "component_substitution", "components": child, "process": [dict(p) for p in process], "change": {"change_type": "component_substitution", "target_path": f"components.{before_key}.identity", "before": {"component_key": before_key, "display_name": before_name}, "after": {"component_key": substitution.replacement_component_key, "display_name": substitution.replacement_display_name}, "rule_id": substitution.id, "rationale": f"Applied approved substitution rule {substitution.id}; no property inheritance is implied."}})
    if "process_parameter" in allowed_mutations:
        by_key = {p["parameter_key"]: p for p in process}
        for process_rule in sorted(space.process_rules, key=lambda r: (r.parameter_key, r.id)):
            if process_rule.locked or not process_rule.step_value or process_rule.step_value <= 0: continue
            current = by_key.get(process_rule.parameter_key)
            if not current: continue
            for sign in (-1, 1):
                value = round(float(current["value"]) + sign * process_rule.step_value, 12)
                if value < process_rule.min_value - 1e-12 or value > process_rule.max_value + 1e-12: continue
                child_process = [dict(p) for p in process]
                target = next(p for p in child_process if p["parameter_key"] == process_rule.parameter_key); before = target["value"]; target["value"] = value
                proposals.append({"kind": "process_parameter", "components": [dict(c) for c in components], "process": child_process, "change": {"change_type": "process_parameter_change", "target_path": f"process.{process_rule.parameter_key}", "before": {"value": before, "unit": process_rule.unit}, "after": {"value": value, "unit": process_rule.unit}, "rule_id": None, "rationale": "Autonomous bounded +/- one configured process step within the active search space; not an operational synthesis instruction."}})
    proposals.sort(key=lambda p: (p["kind"], canonical_json(p["change"]), candidate_fingerprint(parent.material_family, p["components"], p["process"])))
    return proposals[:limit]


def _persist_mutation_child(db: Session, campaign: VirtualExperimentCampaign, iteration: CampaignIteration, parent_candidate: Candidate, proposal: dict[str, Any]) -> tuple[Candidate | None, str, bool, str | None]:
    parent = parent_candidate.hypothesis
    if parent is None:
        raise ValueError(f"Mutation parent candidate {parent_candidate.id} has no linked hypothesis record")
    space = _require_search_space(db, campaign)
    reasons = structural_screen(space, proposal["components"], proposal["process"])
    fp = candidate_fingerprint(parent.material_family, proposal["components"], proposal["process"])
    existing = db.query(CandidateHypothesis).filter_by(project_id=campaign.project_id, deterministic_fingerprint=fp).one_or_none()
    if existing:
        candidate = db.query(Candidate).filter_by(project_id=campaign.project_id, hypothesis_id=existing.id).one()
        return candidate, fp, True, None
    if reasons:
        return None, fp, False, "; ".join(reasons)
    child_id_digest = hashlib.sha256(f"{campaign.project_id}:{fp}".encode()).hexdigest()
    # Phase-5 child IDs are deterministic from scientific identity. The high fixed UUID-like prefix
    # keeps campaign-created hypotheses after legacy random UUID rows in stable lexical listings,
    # while 80 bits of digest entropy retain practical global uniqueness across project+fingerprint.
    child_id = f"ffffffff-ffff-{child_id_digest[:4]}-{child_id_digest[4:8]}-{child_id_digest[8:20]}"
    child = CandidateHypothesis(
        id=child_id, project_id=campaign.project_id, organisation_id=campaign.organisation_id,
        display_label=f"Campaign {campaign.name} mutation {fp[:8]}", material_family=parent.material_family,
        baseline_material_id=parent.baseline_material_id, generation_run_id=None, generator_strategy_key="campaign_parent_mutation",
        generator_strategy_version="1.0", deterministic_fingerprint=fp, fingerprint_version=FINGERPRINT_VERSION,
        status="proposed", structural_validity="valid", rejection_reason=None,
        notes="Virtual-campaign child hypothesis. No material properties are inherited; model predictions remain separate records.",
    )
    db.add(child); db.flush()
    for i, comp in enumerate(proposal["components"]):
        db.add(CandidateHypothesisComponent(
            hypothesis_id=child.id, sequence=i, component_key=comp["component_key"], display_name=comp["display_name"], role=comp.get("role"),
            amount=comp.get("amount"), unit=comp.get("unit"), basis=comp.get("basis"), source_baseline_component_id=comp.get("source_baseline_component_id"),
            substitution_rule_id=comp.get("substitution_rule_id"), locked=bool(comp.get("locked", False)), metadata_json=comp.get("metadata") or {},
        ))
    for proc in proposal["process"]:
        db.add(CandidateHypothesisProcessParameter(
            hypothesis_id=child.id, process_label=proc.get("process_label", "proposed process state"), parameter_key=proc["parameter_key"],
            value=proc["value"], unit=proc["unit"], source_baseline_state_id=proc.get("source_baseline_state_id"), metadata_json=proc.get("metadata") or {},
        ))
    change = proposal["change"]
    db.add(CandidateChangeRecord(
        hypothesis_id=child.id, generation_run_id=None, sequence=0, change_type=change["change_type"], target_path=change["target_path"],
        before_value=change.get("before") or {}, after_value=change.get("after") or {}, substitution_rule_id=change.get("rule_id"),
        rationale=f"{change['rationale']} Campaign={campaign.id}; iteration={iteration.iteration_number}.",
    ))
    db.add(CandidateLineageEdge(
        child_hypothesis_id=child.id, parent_material_id=None, parent_candidate_id=parent_candidate.id, parent_hypothesis_id=parent.id,
        relationship_type="campaign_mutation_from_hypothesis", generation_run_id=None, sequence=0,
        rationale=f"Selected by {campaign.policy_key}/{campaign.policy_version} in campaign {campaign.id} iteration {iteration.iteration_number}; mutation stayed inside search space {campaign.search_space_checksum[:12]}.",
    ))
    candidate = Candidate(
        project_id=campaign.project_id, candidate_kind="hypothesis", material_id=None, hypothesis_id=child.id,
        candidate_source="generated_future", status="proposed", notes="Virtual-campaign hypothesis — model-evaluated only; not physically validated.",
    )
    db.add(candidate); db.flush()
    return candidate, fp, False, None


def _evaluation_checksum(record: dict[str, Any], policy: PolicyDescriptor) -> str:
    return checksum({
        "version": EVALUATION_CHECKSUM_VERSION, "candidate_identity": record["identity"], "feasibility": record["feasibility"],
        "hard_counts": [record["hard_pass"], record["hard_fail"], record["hard_unknown"]],
        "constraint_details": record["constraint_details"], "objectives": {k: v.as_dict() for k, v in sorted(record["objectives"].items())},
        "pareto_rank": record.get("pareto_rank"), "dominance_count": record.get("dominance_count", 0),
        "uncertainty": record["uncertainty"], "policy": {"key": policy.key, "version": policy.version},
    })


def execute_iteration(db: Session, campaign: VirtualExperimentCampaign, *, next_pool_ids: list[str] | None = None) -> CampaignIteration:
    issues = validate_campaign(db, campaign)
    if any(i["severity"] == "error" for i in issues):
        raise ValueError("Campaign invalid: " + "; ".join(i["code"] for i in issues if i["severity"] == "error"))
    existing_count = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).count()
    number = existing_count + 1
    if number > campaign.max_iterations:
        raise ValueError("Campaign maximum iterations reached")
    project = db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material), selectinload(ReplacementProject.constraints), selectinload(ReplacementProject.objectives)
    ).filter_by(id=campaign.project_id).one()
    pool = _load_candidate_pool(db, campaign, next_pool_ids=next_pool_ids)
    if not pool:
        raise ValueError("No eligible candidate pool")
    input_checksum = checksum({"campaign": campaign.configuration_checksum, "iteration": number, "candidate_identities": [_candidate_identity(c) for c in pool]})
    iteration = CampaignIteration(
        campaign_id=campaign.id, iteration_number=number, input_pool_checksum=input_checksum,
        status="running", started_at=now_utc(), metadata_json={"virtual_warning": VIRTUAL_WARNING, "pool_candidate_ids": [c.id for c in pool]},
    )
    db.add(iteration); db.flush()
    campaign.status = "running"; campaign.started_at = campaign.started_at or now_utc(); db.flush()

    run_ids, prediction_lookup = _run_predictions_for_pool(db, campaign, project, pool, number)
    iteration.prediction_run_ids = run_ids
    known_results = _known_constraint_results(db, project, pool)
    objectives = _campaign_objectives(db, campaign.id)
    policy = policy_descriptor(campaign.policy_key)
    records: list[dict[str, Any]] = []
    constraint_policy_map = {p.constraint_id: p for p in _constraint_policies(db, campaign.id)}
    for candidate in pool:
        feasibility, hard_pass, hard_fail, hard_unknown, constraint_details = _classify_feasibility(
            db, campaign, project, candidate, known_results, prediction_lookup, constraint_policy_map
        )
        objective_values: dict[str, ObjectiveValue] = {}
        for obj in objectives:
            prediction = prediction_lookup.get((_objective_signature(obj), candidate.id))
            objective_values[obj.property_key] = _objective_value(obj, prediction)
        record: dict[str, Any] = {
            "candidate": candidate, "identity": _candidate_identity(candidate), "feasibility": feasibility,
            "hard_pass": hard_pass, "hard_fail": hard_fail, "hard_unknown": hard_unknown,
            "constraint_details": constraint_details, "objectives": objective_values,
            "pareto_vector": _minimization_vector(objective_values, objectives), "pareto_rank": None, "dominance_count": 0,
            "uncertainty": _normalized_uncertainty(objective_values),
        }
        records.append(record)
    fronts = non_dominated_sort(records)
    parents = _select_parents(campaign, records)
    parent_ids = [r["candidate"].id for r in parents]
    parent_checksum = checksum({"iteration": number, "policy": [policy.key, policy.version], "parents": [_candidate_identity(r["candidate"]) for r in parents]})
    iteration.parent_selection_checksum = parent_checksum

    decision_sequence = 0
    for record in records:
        selected = record["candidate"].id in parent_ids
        record["selected_as_parent"] = selected
        eval_checksum = _evaluation_checksum(record, policy)
        objective_vector = {k: {"point": v.point, "conservative_value": v.conservative_value, "unit": v.unit, "direction": v.direction, "completeness": v.completeness} for k, v in record["objectives"].items()}
        objective_intervals = {k: {"lower": v.lower, "upper": v.upper, "unit": v.unit, "uncertainty_width": v.uncertainty_width} for k, v in record["objectives"].items()}
        objective_origins = {k: {"origin": v.origin, "prediction_id": v.prediction_id, "model_version_id": v.model_version_id, "applicability": v.applicability} for k, v in record["objectives"].items()}
        rationale = f"{record['feasibility']}; Pareto rank {record.get('pareto_rank') or 'incomplete'}; " + ("selected as bounded mutation parent" if selected else "not selected as parent")
        db.add(VirtualCandidateEvaluation(
            campaign_iteration_id=iteration.id, candidate_id=record["candidate"].id, hypothesis_id=record["candidate"].hypothesis_id,
            feasibility_class=record["feasibility"], hard_pass_count=record["hard_pass"], hard_fail_count=record["hard_fail"], hard_unknown_count=record["hard_unknown"],
            objective_vector=objective_vector, objective_intervals=objective_intervals, objective_origins=objective_origins,
            pareto_rank=record.get("pareto_rank"), dominance_count=record.get("dominance_count", 0), diversity_metric=None,
            uncertainty_burden=record["uncertainty"], normalized_utility_components={}, acquisition_components={
                "policy": campaign.policy_key, "pareto_rank": record.get("pareto_rank"), "feasibility": record["feasibility"],
                "uncertainty_priority": sum(record["uncertainty"].values()),
            }, selected_as_parent=selected, selected_for_next_evaluation=selected, disposition="parent_selected" if selected else "evaluated",
            rationale=rationale, deterministic_evaluation_checksum=eval_checksum,
            metadata_json={"virtual_warning": VIRTUAL_WARNING, "constraint_details": record["constraint_details"]},
        ))
        decision_type = "parent_selected" if selected else ("robustly_infeasible" if record["feasibility"] == "robustly_infeasible" else "initial_pool_selected")
        db.add(OptimizationDecisionRecord(
            campaign_id=campaign.id, campaign_iteration_id=iteration.id, candidate_id=record["candidate"].id, hypothesis_id=record["candidate"].hypothesis_id,
            sequence=decision_sequence, decision_type=decision_type, policy_key=policy.key, policy_version=policy.version,
            input_checksum=eval_checksum, metrics={"feasibility": record["feasibility"], "pareto_rank": record.get("pareto_rank"), "uncertainty": record["uncertainty"]}, rationale=rationale,
        )); decision_sequence += 1
    db.flush()

    front_checksums: list[str] = []
    for rank, front in enumerate(fronts, 1):
        ordered_ids = [r["candidate"].id for r in sorted(front, key=lambda r: r["identity"])]
        front_checksum = checksum({"rank": rank, "objective_vectors": [(r["identity"], r["pareto_vector"]) for r in sorted(front, key=lambda r: r["identity"])]})
        front_checksums.append(front_checksum)
        db.add(ParetoFrontSnapshot(campaign_iteration_id=iteration.id, front_number=rank, ordered_candidate_ids=ordered_ids, objective_space_checksum=front_checksum, policy_key=policy.key, policy_version=policy.version))
    iteration.pareto_front_count = len(fronts[0]) if fronts else 0
    iteration.pareto_front_checksum = front_checksums[0] if front_checksums else checksum({"empty_front": True})

    existing_new = sum(i.new_candidate_count for i in db.query(CampaignIteration).filter(CampaignIteration.campaign_id == campaign.id, CampaignIteration.id != iteration.id).all())
    remaining_campaign_budget = max(0, campaign.max_total_new_candidates - existing_new)
    child_budget = min(campaign.max_candidates_per_iteration, remaining_campaign_budget, MAX_CHILDREN_PER_ITERATION)
    child_ids: list[str] = []; duplicates = 0; rejected = 0
    if child_budget > 0:
        seen_fingerprints: set[str] = set()
        for parent_record in parents:
            if len(child_ids) >= child_budget: break
            parent_candidate = parent_record["candidate"]
            proposals = _mutation_proposals(db, campaign, parent_candidate.hypothesis, child_budget - len(child_ids))
            for proposal in proposals:
                if len(child_ids) >= child_budget: break
                child, fp, duplicate, rejection = _persist_mutation_child(db, campaign, iteration, parent_candidate, proposal)
                if fp in seen_fingerprints: duplicate = True
                seen_fingerprints.add(fp)
                if duplicate:
                    duplicates += 1
                    db.add(OptimizationDecisionRecord(campaign_id=campaign.id, campaign_iteration_id=iteration.id, candidate_id=child.id if child else None, hypothesis_id=child.hypothesis_id if child else None, sequence=decision_sequence, decision_type="duplicate_rejected", policy_key=policy.key, policy_version=policy.version, input_checksum=fp, metrics={"fingerprint": fp}, rationale="Mutation produced a candidate fingerprint already present in the project/campaign; no duplicate scientific hypothesis was inserted.")); decision_sequence += 1
                    continue
                if rejection:
                    rejected += 1
                    db.add(OptimizationDecisionRecord(campaign_id=campaign.id, campaign_iteration_id=iteration.id, candidate_id=None, hypothesis_id=None, sequence=decision_sequence, decision_type="applicability_rejected", policy_key=policy.key, policy_version=policy.version, input_checksum=fp, metrics={"structural_rejection": rejection}, rationale="Mutation failed Phase-3 structural pre-screen and was not persisted as an active hypothesis.")); decision_sequence += 1
                    continue
                if child is None:
                    raise ValueError("Mutation persistence returned no candidate without a duplicate or rejection reason")
                child_ids.append(child.id)
                db.add(OptimizationDecisionRecord(campaign_id=campaign.id, campaign_iteration_id=iteration.id, candidate_id=child.id, hypothesis_id=child.hypothesis_id, sequence=decision_sequence, decision_type="mutation_generated", policy_key=policy.key, policy_version=policy.version, input_checksum=fp, metrics={"fingerprint": fp, "parent_candidate_id": parent_candidate.id}, rationale="Bounded child generated from selected hypothesis parent using only configured Phase-3 search-space dimensions.")); decision_sequence += 1
    iteration.evaluated_candidate_count = len(records)
    iteration.feasible_count = sum(r["feasibility"] == "robustly_feasible" for r in records)
    iteration.uncertain_count = sum(r["feasibility"] == "uncertain" for r in records)
    iteration.infeasible_count = sum(r["feasibility"] == "robustly_infeasible" for r in records)
    iteration.selected_for_exploration_count = len(parents)
    iteration.new_candidate_count = len(child_ids)
    iteration.duplicate_count = duplicates
    iteration.metadata_json = {**iteration.metadata_json, "created_child_candidate_ids": child_ids, "structurally_rejected_mutations": rejected}

    stop_reason = None
    if not any(r["pareto_vector"] is not None for r in records): stop_reason = "no_applicable_objective_predictions"
    elif not parents: stop_reason = "no_eligible_parent_candidate"
    elif remaining_campaign_budget <= len(child_ids): stop_reason = "total_new_candidate_budget_reached"
    elif not child_ids: stop_reason = "no_structurally_valid_unique_child_generated"
    elif number >= campaign.max_iterations: stop_reason = "maximum_iterations_reached"
    convergence_n = campaign.metadata_json.get("convergence_unchanged_iterations")
    if not stop_reason and convergence_n and number >= int(convergence_n):
        recent = db.query(CampaignIteration).filter(CampaignIteration.campaign_id == campaign.id, CampaignIteration.iteration_number >= number - int(convergence_n) + 1).order_by(CampaignIteration.iteration_number).all()
        checks = [r.pareto_front_checksum for r in recent if r.pareto_front_checksum] + [iteration.pareto_front_checksum]
        if len(checks) >= int(convergence_n) and len(set(checks[-int(convergence_n):])) == 1:
            stop_reason = "pareto_front_unchanged_configured_iterations"
    iteration.stop_signal = bool(stop_reason)
    iteration.stop_reason = stop_reason
    iteration.status = "completed"; iteration.completed_at = now_utc()
    iteration.decision_checksum = checksum({
        "campaign": campaign.configuration_checksum, "iteration": number, "input": input_checksum,
        "prediction_runs": [_require_prediction_run(db, rid).result_checksum for rid in run_ids],
        "parents": [_candidate_identity(r["candidate"]) for r in parents],
        "child_fingerprints": [_require_child_fingerprint(db, cid) for cid in child_ids],
        "front": iteration.pareto_front_checksum, "stop_reason": stop_reason,
    })
    db.commit(); db.refresh(iteration)
    return iteration


def run_campaign(db: Session, campaign: VirtualExperimentCampaign, max_iterations: int | None = None) -> list[CampaignIteration]:
    preview = preview_campaign(db, campaign)
    if not preview["valid"]:
        raise ValueError("Campaign preview is invalid: " + "; ".join(i["code"] for i in preview["validation_issues"] if i["severity"] == "error"))
    limit = min(max_iterations or campaign.max_iterations, campaign.max_iterations, MAX_SYNC_ITERATIONS)
    completed: list[CampaignIteration] = []
    previous_pool: list[str] | None = None
    existing = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).order_by(CampaignIteration.iteration_number).all()
    if existing:
        last = existing[-1]
        previous_pool = list(last.metadata_json.get("created_child_candidate_ids") or [])
        if last.stop_signal:
            return existing
    for _ in range(len(existing), limit):
        iteration = execute_iteration(db, campaign, next_pool_ids=previous_pool if previous_pool else None)
        completed.append(iteration)
        if iteration.stop_signal: break
        children = list(iteration.metadata_json.get("created_child_candidate_ids") or [])
        parent_ids = [e.candidate_id for e in db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=iteration.id, selected_as_parent=True).order_by(VirtualCandidateEvaluation.candidate_id).all()]
        previous_pool = (children + parent_ids)[:MAX_POOL_SIZE]
        if not previous_pool: break
    all_iterations = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).order_by(CampaignIteration.iteration_number).all()
    final = all_iterations[-1] if all_iterations else None
    campaign.status = "completed" if final and final.stop_signal else "stopped"
    campaign.stop_reason = final.stop_reason if final else "no_iteration_executed"
    campaign.completed_at = now_utc()
    campaign.result_checksum = checksum({"campaign": campaign.configuration_checksum, "iterations": [i.decision_checksum for i in all_iterations], "final_front": final.pareto_front_checksum if final else None, "stop_reason": campaign.stop_reason})
    db.commit(); db.refresh(campaign)
    return all_iterations


def campaign_reproducibility_envelope(db: Session, campaign: VirtualExperimentCampaign) -> dict[str, Any]:
    objectives = _campaign_objectives(db, campaign.id)
    versions = [require_model_version(db, o.model_version_id) for o in objectives]
    iterations = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).order_by(CampaignIteration.iteration_number).all()
    return {
        "campaign_id": campaign.id,
        "campaign_contract": CAMPAIGN_CONTRACT_VERSION,
        "configuration_checksum": campaign.configuration_checksum,
        "specification_checksum": campaign.replacement_specification_checksum,
        "search_space": {"id": campaign.search_space_id, "version": campaign.search_space_version, "checksum": campaign.search_space_checksum},
        "policy": {"key": campaign.policy_key, "version": campaign.policy_version},
        "seed": campaign.random_seed,
        "model_versions": [{"id": v.id, "artifact_checksum": v.artifact_checksum, "feature_schema_checksum": v.feature_schema_checksum} for v in versions],
        "objectives": [{"property": o.property_key, "direction": o.direction, "model_version_id": o.model_version_id, "sequence": o.sequence} for o in objectives],
        "iterations": [{"number": i.iteration_number, "input_pool_checksum": i.input_pool_checksum, "parent_selection_checksum": i.parent_selection_checksum, "pareto_front_checksum": i.pareto_front_checksum, "decision_checksum": i.decision_checksum, "stop_reason": i.stop_reason} for i in iterations],
        "result_checksum": campaign.result_checksum,
        "warning": VIRTUAL_WARNING,
    }


def evaluations_page(db: Session, iteration_id: str, offset: int, limit: int) -> tuple[list[VirtualCandidateEvaluation], int]:
    q = db.query(VirtualCandidateEvaluation).filter_by(campaign_iteration_id=iteration_id)
    total = q.count()
    rows = q.order_by(VirtualCandidateEvaluation.pareto_rank.is_(None), VirtualCandidateEvaluation.pareto_rank, VirtualCandidateEvaluation.feasibility_class, VirtualCandidateEvaluation.candidate_id).offset(offset).limit(limit).all()
    return rows, total


def final_front_ids(db: Session, campaign: VirtualExperimentCampaign) -> list[str]:
    iteration = db.query(CampaignIteration).filter_by(campaign_id=campaign.id).order_by(CampaignIteration.iteration_number.desc()).first()
    if not iteration: return []
    front = db.query(ParetoFrontSnapshot).filter_by(campaign_iteration_id=iteration.id, front_number=1).one_or_none()
    return list(front.ordered_candidate_ids) if front else []


def assert_virtual_evaluation_integrity(db: Session) -> dict[str, Any]:
    return {
        "material_observation_count": db.query(MaterialPropertyObservation).count(),
        "campaign_count": db.query(VirtualExperimentCampaign).count(),
        "virtual_evaluation_count": db.query(VirtualCandidateEvaluation).count(),
        "warning": VIRTUAL_WARNING,
    }
