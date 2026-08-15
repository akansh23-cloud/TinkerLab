"""Phase 12 — tell the user why a lab is empty, and exactly what to do about it.

THE FAILURE THIS FIXES. Each lab has a chain of preconditions. When one is missing the page still
renders: the dropdowns are empty, the primary button is disabled, and nothing explains why. To the
user that is indistinguishable from a broken deployment, and it was the single largest source of
"the labs are not proper".

The precondition logic was never the problem — the labs were right to refuse. What was missing was
the diagnosis. This service walks the chain in dependency order and returns, for each requirement,
whether it is satisfied, what it means, and a concrete next action with the endpoint or route that
performs it. A disabled button with a reason and a fix button beside it is a usable product; a
disabled button on its own is a bug report.

Nothing here evaluates science. It reports on the presence and shape of inputs, so it can never
influence a verdict.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Candidate,
    CandidateSearchSpace,
    Constraint,
    GenerationRun,
    Material,
    MaterialPropertyObservation,
    Objective,
    PredictionModelVersion,
    ReplacementProject,
    ScientificRepresentation,
    SimulationProvider,
)
from app.services.bench.derive import derivation_preview

OK = "ok"
BLOCKED = "blocked"
WARNING = "warning"


def _check(
    code: str, label: str, status: str, detail: str,
    fix: dict[str, Any] | None = None, evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "code": code, "label": label, "status": status, "detail": detail,
        "fix": fix, "evidence": evidence or {},
    }


def project_readiness(db: Session, project_id: str, organisation_id: str | None = None) -> dict[str, Any]:
    project = (
        db.query(ReplacementProject).options(
            selectinload(ReplacementProject.constraints),
            selectinload(ReplacementProject.objectives),
        ).filter(ReplacementProject.id == project_id,
                  ReplacementProject.organisation_id == organisation_id).one_or_none()
    )
    if project is None:
        return {
            "project_id": project_id, "found": False, "labs": [],
            "summary": {"blocked": 1, "warnings": 0, "ready_labs": 0, "total_labs": 0},
        }

    baseline = (
        db.query(Material).options(selectinload(Material.components))
        .filter(Material.id == project.baseline_material_id).one_or_none()
    )
    constraints: list[Constraint] = list(project.constraints)
    objectives: list[Objective] = list(project.objectives)
    hard_constraints = [c for c in constraints if c.hard_or_soft == "hard"]

    spaces = db.query(CandidateSearchSpace).filter_by(project_id=project.id).all()
    active_space = next((s for s in spaces if s.active), None)

    baseline_observations = (
        db.query(MaterialPropertyObservation)
        .filter(MaterialPropertyObservation.material_id == project.baseline_material_id,
                MaterialPropertyObservation.status == "active").count()
        if baseline else 0
    )
    constrained_keys = {c.property_key for c in constraints}
    covered_keys: set[str] = set()
    if baseline and constrained_keys:
        rows = (
            db.query(MaterialPropertyObservation)
            .options(selectinload(MaterialPropertyObservation.property_definition))
            .filter(MaterialPropertyObservation.material_id == baseline.id,
                    MaterialPropertyObservation.status == "active").all()
        )
        covered_keys = {r.property_definition.key for r in rows if r.property_definition}
    missing_baseline_keys = sorted(constrained_keys - covered_keys)

    candidate_count = db.query(Candidate).filter_by(project_id=project.id).count()
    run_count = db.query(GenerationRun).filter_by(project_id=project.id).count()

    approved_versions = (
        db.query(PredictionModelVersion)
        .filter(PredictionModelVersion.approved_at.isnot(None),
                PredictionModelVersion.retired_at.is_(None)).all()
    )
    approved_property_keys = sorted({v.target_property_key for v in approved_versions})

    representation_count = (
        db.query(ScientificRepresentation)
        .filter(ScientificRepresentation.material_id == project.baseline_material_id).count()
        if baseline else 0
    )
    # "approved" is the lifecycle status that permits execution; draft and retired providers exist
    # but cannot run, so counting all rows would report a readiness the system would then refuse.
    enabled_providers = db.query(SimulationProvider).filter(SimulationProvider.status == "approved").count()

    # ------------------------------------------------------------------ foundation
    foundation: list[dict[str, Any]] = []

    if baseline is None:
        foundation.append(_check(
            "BASELINE_MISSING", "Baseline material", BLOCKED,
            "This project has no baseline material, so there is nothing to replace.",
            fix={"kind": "navigate", "label": "Add a material", "href": "/materials/new"},
        ))
    else:
        foundation.append(_check(
            "BASELINE_PRESENT", "Baseline material", OK,
            f"{baseline.display_name} ({baseline.material_family}).",
            evidence={"material_id": baseline.id, "component_count": len(baseline.components)},
        ))

    if baseline is not None and baseline_observations == 0:
        foundation.append(_check(
            "BASELINE_NO_PROPERTIES", "Baseline property data", BLOCKED,
            "The baseline has no recorded property values. Every comparison would resolve to UNKNOWN, "
            "which is technically honest and practically useless.",
            fix={"kind": "navigate", "label": "Record baseline properties",
                 "href": f"/materials/{baseline.id}/add-data"},
        ))
    elif missing_baseline_keys:
        foundation.append(_check(
            "BASELINE_PARTIAL_COVERAGE", "Baseline property data", WARNING,
            f"{len(missing_baseline_keys)} constrained propert{'y has' if len(missing_baseline_keys) == 1 else 'ies have'} "
            f"no baseline value: {', '.join(missing_baseline_keys[:6])}"
            f"{'…' if len(missing_baseline_keys) > 6 else ''}. Candidates can still be screened, but you will not be "
            "able to state the delta against the incumbent for those requirements.",
            fix={"kind": "navigate", "label": "Fill baseline gaps",
                 "href": f"/materials/{baseline.id}/add-data"} if baseline else None,
            evidence={"missing_property_keys": missing_baseline_keys},
        ))
    elif baseline is not None:
        foundation.append(_check(
            "BASELINE_COVERAGE_COMPLETE", "Baseline property data", OK,
            f"{baseline_observations} observation(s) recorded; every constrained property has a baseline value.",
        ))

    if not constraints:
        foundation.append(_check(
            "NO_REQUIREMENTS", "Requirements", BLOCKED,
            "No constraints are defined, so no candidate can pass or fail anything.",
            fix={"kind": "navigate", "label": "Open the project", "href": f"/projects/{project.id}"},
        ))
    elif not hard_constraints:
        foundation.append(_check(
            "NO_HARD_REQUIREMENTS", "Requirements", WARNING,
            f"{len(constraints)} requirement(s), all soft. Nothing can eliminate a candidate, so screening "
            "will return the entire population ranked by preference.",
        ))
    else:
        foundation.append(_check(
            "REQUIREMENTS_DEFINED", "Requirements", OK,
            f"{len(hard_constraints)} hard and {len(constraints) - len(hard_constraints)} soft requirement(s).",
        ))

    if not objectives:
        foundation.append(_check(
            "NO_OBJECTIVES", "Optimisation objectives", WARNING,
            "No objectives are set. Candidates can be screened for eligibility but not ranked.",
        ))
    else:
        foundation.append(_check(
            "OBJECTIVES_DEFINED", "Optimisation objectives", OK, f"{len(objectives)} objective(s).",
        ))

    # ------------------------------------------------------------------ search space
    space_checks: list[dict[str, Any]] = []
    derivable = False
    derive_blockers: list[dict[str, Any]] = []

    if active_space is not None:
        space_checks.append(_check(
            "SEARCH_SPACE_ACTIVE", "Active search space", OK,
            f"Version {active_space.version} · {len(active_space.component_rules)} component rule(s).",
            evidence={"search_space_id": active_space.id, "checksum": active_space.checksum},
        ))
    else:
        preview = derivation_preview(db, project) if baseline else {"derivable": False, "blockers": []}
        derivable = bool(preview.get("derivable"))
        derive_blockers = list(preview.get("blockers", []))
        if spaces and not active_space:
            space_checks.append(_check(
                "SEARCH_SPACE_INACTIVE", "Active search space", BLOCKED,
                f"{len(spaces)} search space version(s) exist but none is active. Candidate generation "
                "and virtual campaigns both require an active version.",
                fix={"kind": "api", "label": "Activate the latest version",
                     "endpoint": f"/replacement-projects/{project.id}/search-spaces/"
                                 f"{sorted(spaces, key=lambda s: s.version)[-1].id}/activate",
                     "method": "POST"},
            ))
        elif derivable:
            space_checks.append(_check(
                "SEARCH_SPACE_DERIVABLE", "Active search space", BLOCKED,
                "No search space exists yet. One can be derived automatically from the baseline "
                "composition — conservative bands around the incumbent, matrix as balance.",
                fix={"kind": "api", "label": "Derive from baseline",
                     "endpoint": f"/replacement-projects/{project.id}/search-space-derivation?activate=true",
                     "method": "POST"},
                evidence={"estimated_cardinality": preview.get("estimated_cardinality", 0)},
            ))
        else:
            first = derive_blockers[0] if derive_blockers else {
                "message": "No search space exists and none can be derived.",
                "fix": "Record a baseline composition with numeric amounts.",
            }
            space_checks.append(_check(
                "SEARCH_SPACE_UNDERIVABLE", "Active search space", BLOCKED,
                f"{first.get('message')} {first.get('fix', '')}".strip(),
                fix={"kind": "navigate", "label": "Edit baseline composition",
                     "href": f"/materials/{baseline.id}/add-data"} if baseline else None,
                evidence={"blockers": derive_blockers},
            ))

    # ------------------------------------------------------------------ labs
    def worst(checks: list[dict[str, Any]]) -> str:
        if any(c["status"] == BLOCKED for c in checks):
            return BLOCKED
        if any(c["status"] == WARNING for c in checks):
            return WARNING
        return OK

    foundation_blocking = [c for c in foundation if c["status"] == BLOCKED]

    candidate_lab = foundation + space_checks
    labs: list[dict[str, Any]] = [{
        "key": "candidate_lab",
        "display_name": "Candidate Lab",
        "purpose": "Generate bounded candidate formulations from the baseline within a declared search space.",
        "href": f"/projects/{project.id}/candidate-lab",
        "status": worst(candidate_lab),
        "checks": candidate_lab,
    }]

    prediction_checks = list(foundation_blocking)
    if not approved_versions:
        prediction_checks.append(_check(
            "NO_APPROVED_MODELS", "Approved prediction models", BLOCKED,
            "No approved, unretired prediction model version exists. Property prediction and any "
            "model-driven virtual campaign both require one.",
            fix={"kind": "navigate", "label": "Review prediction models", "href": "/reasoning"},
        ))
    else:
        prediction_checks.append(_check(
            "APPROVED_MODELS_PRESENT", "Approved prediction models", OK,
            f"{len(approved_versions)} approved version(s) covering: {', '.join(approved_property_keys)}.",
            evidence={"property_keys": approved_property_keys},
        ))
    labs.append({
        "key": "prediction_lab",
        "display_name": "Prediction Lab",
        "purpose": "Predict properties for candidates that have no measured value, with an applicability check.",
        "href": f"/projects/{project.id}/prediction-lab",
        "status": worst(prediction_checks),
        "checks": prediction_checks,
    })

    virtual_checks = list(foundation_blocking) + space_checks + [
        c for c in prediction_checks if c["code"] in {"NO_APPROVED_MODELS", "APPROVED_MODELS_PRESENT"}
    ]
    constrained_and_modelled = sorted(constrained_keys & set(approved_property_keys))
    if approved_versions and constrained_keys and not constrained_and_modelled:
        virtual_checks.append(_check(
            "NO_MODEL_FOR_REQUIREMENTS", "Model coverage of requirements", WARNING,
            "No approved model targets any of this project's constrained properties. A campaign can "
            "still run, but it will optimise properties nobody has set a requirement on.",
            evidence={"constrained_keys": sorted(constrained_keys), "modelled_keys": approved_property_keys},
        ))
    elif constrained_and_modelled:
        virtual_checks.append(_check(
            "MODEL_COVERS_REQUIREMENTS", "Model coverage of requirements", OK,
            f"Models cover {len(constrained_and_modelled)} constrained propert"
            f"{'y' if len(constrained_and_modelled) == 1 else 'ies'}: {', '.join(constrained_and_modelled)}.",
        ))
    labs.append({
        "key": "virtual_lab",
        "display_name": "Virtual Experiment Lab",
        "purpose": "Run a bounded, seeded, multi-objective search over the space using approved models.",
        "href": f"/projects/{project.id}/virtual-lab",
        "status": worst(virtual_checks),
        "checks": virtual_checks,
    })

    simulation_checks: list[dict[str, Any]] = []
    if representation_count == 0:
        simulation_checks.append(_check(
            "NO_REPRESENTATION", "Scientific representation", BLOCKED,
            "The baseline has no structural representation, so no physics simulation can be routed to it. "
            "A formulation is not a structure — this is a real modelling boundary, not a missing feature.",
            fix={"kind": "navigate", "label": "Open Simulation Lab", "href": "/simulation"},
        ))
    else:
        simulation_checks.append(_check(
            "REPRESENTATION_PRESENT", "Scientific representation", OK,
            f"{representation_count} representation(s) registered for the baseline.",
        ))
    if enabled_providers == 0:
        simulation_checks.append(_check(
            "NO_SIMULATION_PROVIDER", "Simulation provider", BLOCKED,
            "No approved simulation provider is registered. Draft and retired providers cannot execute.",
            fix={"kind": "navigate", "label": "Open Simulation Lab", "href": "/simulation"},
        ))
    else:
        simulation_checks.append(_check(
            "SIMULATION_PROVIDER_PRESENT", "Simulation provider", OK,
            f"{enabled_providers} approved provider(s).",
        ))
    labs.append({
        "key": "simulation_lab",
        "display_name": "Simulation Lab",
        "purpose": "Run physics simulations as a third evidence origin, distinct from measurement and prediction.",
        "href": "/simulation",
        "status": worst(simulation_checks),
        "checks": simulation_checks,
    })

    decision_checks = list(foundation_blocking)
    if candidate_count == 0:
        decision_checks.append(_check(
            "NO_CANDIDATES", "Candidates", BLOCKED,
            "No candidates exist yet. Generate them in the Candidate Lab, or add known materials directly.",
            fix={"kind": "navigate", "label": "Open Candidate Lab",
                 "href": f"/projects/{project.id}/candidate-lab"},
        ))
    else:
        decision_checks.append(_check(
            "CANDIDATES_PRESENT", "Candidates", OK,
            f"{candidate_count} candidate(s) across {run_count} generation run(s).",
        ))
    labs.append({
        "key": "replacement_decision",
        "display_name": "Replacement Decision",
        "purpose": "Screen, rank and produce an auditable recommendation with its evidence trail.",
        "href": f"/projects/{project.id}/replacement",
        "status": worst(decision_checks),
        "checks": decision_checks,
    })

    all_checks = [c for lab in labs for c in lab["checks"]]
    blocked_codes = {c["code"] for c in all_checks if c["status"] == BLOCKED}
    warning_codes = {c["code"] for c in all_checks if c["status"] == WARNING}

    next_action = None
    for lab in labs:
        for check in lab["checks"]:
            if check["status"] == BLOCKED and check.get("fix"):
                next_action = {**check["fix"], "because": check["detail"], "lab": lab["display_name"]}
                break
        if next_action:
            break

    return {
        "project_id": project.id,
        "project_name": project.name,
        "found": True,
        "labs": labs,
        "next_action": next_action,
        "summary": {
            "blocked": len(blocked_codes),
            "warnings": len(warning_codes),
            "ready_labs": sum(1 for lab in labs if lab["status"] == OK),
            "total_labs": len(labs),
        },
    }


def platform_readiness(db: Session, organisation_id: str | None = None) -> dict[str, Any]:
    """Deployment-level readiness. Answers 'is this instance actually usable yet'."""
    material_query = db.query(Material)
    if organisation_id:
        material_query = material_query.filter(
            or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id)
        )
    else:
        material_query = material_query.filter(Material.visibility == "public")

    total_materials = material_query.count()
    real_materials = material_query.filter(Material.is_seed_data.is_(False)).count()
    project_count = db.query(ReplacementProject).count()
    approved_models = (
        db.query(PredictionModelVersion)
        .filter(PredictionModelVersion.approved_at.isnot(None),
                PredictionModelVersion.retired_at.is_(None)).count()
    )

    checks = [
        _check(
            "MATERIALS_AVAILABLE", "Material library",
            OK if total_materials >= 5 else BLOCKED,
            f"{total_materials} visible material(s), {real_materials} of them user- or library-provided."
            if total_materials else "No materials are visible. Nothing can be studied.",
            fix=None if total_materials >= 5 else {
                "kind": "api", "label": "Install the reference library",
                "endpoint": "/bench/install-reference-library", "method": "POST",
            },
        ),
        _check(
            "PROJECTS_EXIST", "Replacement studies",
            OK if project_count else WARNING,
            f"{project_count} study/studies defined." if project_count
            else "No replacement studies yet. Start one from a baseline material.",
            fix=None if project_count else {
                "kind": "navigate", "label": "Start a study", "href": "/studies/new",
            },
        ),
        _check(
            "MODELS_APPROVED", "Prediction models",
            OK if approved_models else WARNING,
            f"{approved_models} approved model version(s)." if approved_models
            else "No approved prediction models. Screening on measured evidence still works; "
                 "model-driven virtual campaigns do not.",
        ),
    ]
    return {
        "checks": checks,
        "material_count": total_materials,
        "project_count": project_count,
        "approved_model_count": approved_models,
        "status": BLOCKED if any(c["status"] == BLOCKED for c in checks)
        else (WARNING if any(c["status"] == WARNING for c in checks) else OK),
    }
