from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    CandidateHypothesis,
    Material,
    PredictionModel,
    PredictionModelVersion,
    PredictionRun,
    PredictionTarget,
    PropertyPrediction,
    ReplacementProject,
)
from app.schemas.prediction import (
    ApplicabilityAssessRequest,
    ApplicabilityOut,
    PredictionModelCreate,
    PredictionModelOut,
    PredictionModelVersionCreate,
    PredictionModelVersionOut,
    PredictionResultPage,
    PredictionRunCreate,
    PredictionRunOut,
    PredictionRunPreviewOut,
    PredictionRunPreviewRequest,
)
from app.services.prediction import (
    approve_model_version,
    assess_applicability,
    create_model_version,
    execute_prediction_run,
    get_model_version,
    get_run,
    prediction_detail,
    predictions_for_run,
    preview_prediction_run,
    resolve_target_snapshot,
)

router = APIRouter(tags=["prediction"])


def _require_org(organisation_id: str | None) -> str:
    if not organisation_id:
        raise HTTPException(400, "X-Organisation-ID is required for private prediction workflows")
    return organisation_id


def _model_visible(model: PredictionModel, organisation_id: str | None) -> bool:
    return model.organisation_id is None or (organisation_id is not None and model.organisation_id == organisation_id)


def _require_visible_model(db: Session, model_id: str, organisation_id: str | None) -> PredictionModel:
    model = db.get(PredictionModel, model_id)
    if not model or not _model_visible(model, organisation_id):
        raise HTTPException(404, "Prediction model not found")
    return model


def _require_visible_version(db: Session, version_id: str, organisation_id: str | None) -> PredictionModelVersion:
    version = get_model_version(db, version_id)
    if not version or not _model_visible(version.model, organisation_id):
        raise HTTPException(404, "Prediction model version not found")
    return version


@router.get("/prediction-models", response_model=list[PredictionModelOut])
def list_prediction_models(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    scope: ColumnElement[bool] = PredictionModel.organisation_id.is_(None)
    if organisation_id:
        scope = or_(scope, PredictionModel.organisation_id == organisation_id)
    query = db.query(PredictionModel).filter(scope)
    return query.order_by(PredictionModel.key, PredictionModel.id).all()


@router.post("/prediction-models", response_model=PredictionModelOut, status_code=201)
def create_prediction_model(payload: PredictionModelCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    model = PredictionModel(organisation_id=org, status="draft", **payload.model_dump(exclude={"metadata"}), metadata_json=payload.metadata)
    db.add(model)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Prediction model key already exists in this organisation") from exc
    db.refresh(model)
    return model


@router.get("/prediction-models/{model_id}", response_model=PredictionModelOut)
def get_prediction_model(model_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return _require_visible_model(db, model_id, organisation_id)


@router.get("/prediction-models/{model_id}/versions", response_model=list[PredictionModelVersionOut])
def list_prediction_model_versions(model_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    model = _require_visible_model(db, model_id, organisation_id)
    rows = (db.query(PredictionModelVersion)
        .options(selectinload(PredictionModelVersion.applicability_domain))
        .filter(PredictionModelVersion.model_id == model.id)
        .order_by(PredictionModelVersion.created_at, PredictionModelVersion.id)
        .all())
    return rows


@router.post("/prediction-models/{model_id}/versions", response_model=PredictionModelVersionOut, status_code=201)
def register_prediction_model_version(model_id: str, payload: PredictionModelVersionCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    model = _require_visible_model(db, model_id, org)
    if model.organisation_id is None:
        raise HTTPException(403, "Global curated model versions cannot be modified through the tenant API")
    values = payload.model_dump()
    domain = values.pop("applicability_domain")
    values["applicability_domain"] = {**domain, "metadata_json": domain.pop("metadata", {})}
    try:
        version = create_model_version(db, model, values)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(422 if isinstance(exc, ValueError) else 409, str(exc)) from exc
    return _require_visible_version(db, version.id, org)


@router.get("/prediction-model-versions/{version_id}", response_model=PredictionModelVersionOut)
def get_prediction_model_version(version_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    return _require_visible_version(db, version_id, organisation_id)


@router.post("/prediction-model-versions/{version_id}/approve", response_model=PredictionModelVersionOut)
def approve_prediction_model_version(version_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    version = _require_visible_version(db, version_id, org)
    if version.model.organisation_id is None:
        raise HTTPException(403, "Global curated model versions cannot be modified through the tenant API")
    try:
        approve_model_version(db, version)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    return _require_visible_version(db, version_id, org)


@router.post("/prediction-models/{model_id}/disable", response_model=PredictionModelOut)
def disable_prediction_model(model_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    model = _require_visible_model(db, model_id, org)
    if model.organisation_id is None:
        raise HTTPException(403, "Global curated model lifecycle is seed/admin controlled")
    model.status = "disabled"
    db.commit(); db.refresh(model)
    return model


@router.post("/prediction-models/{model_id}/retire", response_model=PredictionModelOut)
def retire_prediction_model(model_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    model = _require_visible_model(db, model_id, org)
    if model.organisation_id is None:
        raise HTTPException(403, "Global curated model lifecycle is seed/admin controlled")
    model.status = "retired"
    now = datetime.now(UTC)
    for version in model.versions:
        version.retired_at = version.retired_at or now
    db.commit(); db.refresh(model)
    return model


@router.post("/prediction-model-versions/{version_id}/applicability", response_model=ApplicabilityOut)
def applicability(version_id: str, payload: ApplicabilityAssessRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    project = db.get(ReplacementProject, payload.project_id)
    if not project or project.organisation_id != org:
        raise HTTPException(404, "Project not found")
    version = _require_visible_version(db, version_id, org)
    try:
        snapshot = resolve_target_snapshot(db, project, payload.target.model_dump(exclude_none=True), org)
        result = assess_applicability(version, snapshot, payload.property_key, payload.conditions)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "status": result.status,
        "reasons": result.reasons,
        "feature_checksum": snapshot.feature_checksum,
        "source_entity_checksum": snapshot.source_entity_checksum,
        "missing_features": snapshot.missing_features,
        "redaction_flags": snapshot.redaction_flags,
        "target_kind": snapshot.target_kind,
        "target_id": snapshot.target_id,
    }


@router.post("/replacement-projects/{project_id}/prediction-runs/preview", response_model=PredictionRunPreviewOut)
def prediction_preview(project_id: str, payload: PredictionRunPreviewRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    project = db.get(ReplacementProject, project_id)
    if not project or project.organisation_id != org:
        raise HTTPException(404, "Project not found")
    version = _require_visible_version(db, payload.model_version_id, org)
    try:
        return preview_prediction_run(
            db, project, version, [t.model_dump(exclude_none=True) for t in payload.targets], payload.property_key,
            payload.conditions, payload.configuration, org,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/replacement-projects/{project_id}/prediction-runs", response_model=PredictionRunOut, status_code=201)
def prediction_execute(project_id: str, payload: PredictionRunCreate, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    project = db.get(ReplacementProject, project_id)
    if not project or project.organisation_id != org:
        raise HTTPException(404, "Project not found")
    version = _require_visible_version(db, payload.model_version_id, org)
    try:
        return execute_prediction_run(
            db, project, version, [t.model_dump(exclude_none=True) for t in payload.targets], payload.property_key,
            payload.conditions, payload.requested_output_unit, payload.configuration, payload.created_by, org,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc


@router.get("/replacement-projects/{project_id}/prediction-runs", response_model=list[PredictionRunOut])
def list_project_prediction_runs(project_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    project = db.get(ReplacementProject, project_id)
    if not project or project.organisation_id != org:
        raise HTTPException(404, "Project not found")
    return db.query(PredictionRun).filter(PredictionRun.project_id == project_id, PredictionRun.organisation_id == org).order_by(PredictionRun.created_at.desc()).limit(100).all()


@router.get("/prediction-runs/{run_id}", response_model=PredictionRunOut)
def prediction_run_detail(run_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    run = get_run(db, run_id, org)
    if not run:
        raise HTTPException(404, "Prediction run not found")
    return run


@router.get("/prediction-runs/{run_id}/results", response_model=PredictionResultPage)
def prediction_run_results(run_id: str, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=200), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    items, total = predictions_for_run(db, run_id, org, offset, limit)
    if not get_run(db, run_id, org):
        raise HTTPException(404, "Prediction run not found")
    target_ids = [p.prediction_target_id for p in items]
    targets = {t.id: t for t in db.query(PredictionTarget).filter(PredictionTarget.id.in_(target_ids)).all()} if target_ids else {}
    return {
        "items": [{
            "id": p.id, "prediction_run_id": p.prediction_run_id, "prediction_target_id": p.prediction_target_id,
            "model_version_id": p.model_version_id, "property_definition_id": p.property_definition_id,
            "applicability_status": p.applicability_status, "applicability_rationale": p.applicability_rationale,
            "numeric_point_estimate": p.numeric_point_estimate, "output_unit": p.output_unit,
            "uncertainty_lower": p.uncertainty_lower, "uncertainty_upper": p.uncertainty_upper,
            "uncertainty_method": p.uncertainty_method, "calibrated_coverage_level": p.calibrated_coverage_level,
            "warnings": p.warnings, "status": p.status, "deterministic_result_checksum": p.deterministic_result_checksum,
            "scientific_origin": "MODEL PREDICTION",
            "target": {"candidate_id": targets[p.prediction_target_id].candidate_id, "material_id": targets[p.prediction_target_id].material_id, "hypothesis_id": targets[p.prediction_target_id].hypothesis_id} if p.prediction_target_id in targets else {},
        } for p in items],
        "total": total, "offset": offset, "limit": limit,
    }


@router.get("/predictions/{prediction_id}")
def get_prediction(prediction_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    detail = prediction_detail(db, prediction_id, org)
    if not detail:
        raise HTTPException(404, "Prediction not found")
    prediction = detail["prediction"]
    detail["prediction"] = {
        "id": prediction.id, "prediction_run_id": prediction.prediction_run_id,
        "prediction_target_id": prediction.prediction_target_id, "model_version_id": prediction.model_version_id,
        "input_snapshot_id": prediction.input_snapshot_id, "property_definition_id": prediction.property_definition_id,
        "applicability_status": prediction.applicability_status, "applicability_rationale": prediction.applicability_rationale,
        "numeric_point_estimate": prediction.numeric_point_estimate, "output_unit": prediction.output_unit,
        "canonical_value": prediction.canonical_value, "canonical_unit": prediction.canonical_unit,
        "uncertainty_lower": prediction.uncertainty_lower, "uncertainty_upper": prediction.uncertainty_upper,
        "uncertainty_stddev": prediction.uncertainty_stddev, "uncertainty_method": prediction.uncertainty_method,
        "calibrated_coverage_level": prediction.calibrated_coverage_level, "warnings": prediction.warnings,
        "status": prediction.status, "deterministic_result_checksum": prediction.deterministic_result_checksum,
        "scientific_origin": "MODEL PREDICTION",
    }
    return detail


def _prediction_history(db: Session, organisation_id: str, *, hypothesis_id: str | None = None, material_id: str | None = None):
    query = db.query(PropertyPrediction, PredictionTarget).join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id).filter(PredictionTarget.organisation_id == organisation_id)
    if hypothesis_id:
        query = query.filter(PredictionTarget.hypothesis_id == hypothesis_id)
    if material_id:
        query = query.filter(PredictionTarget.material_id == material_id)
    rows = query.order_by(PropertyPrediction.created_at.desc()).limit(200).all()
    return [{
        "id": p.id, "prediction_run_id": p.prediction_run_id, "model_version_id": p.model_version_id,
        "applicability_status": p.applicability_status, "numeric_point_estimate": p.numeric_point_estimate,
        "output_unit": p.output_unit, "uncertainty_lower": p.uncertainty_lower, "uncertainty_upper": p.uncertainty_upper,
        "status": p.status, "warnings": p.warnings, "scientific_origin": "MODEL PREDICTION",
    } for p, _ in rows]


@router.get("/candidate-hypotheses/{hypothesis_id}/predictions")
def hypothesis_predictions(hypothesis_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    hypothesis = db.get(CandidateHypothesis, hypothesis_id)
    if not hypothesis or hypothesis.organisation_id != org:
        raise HTTPException(404, "Hypothesis not found")
    return _prediction_history(db, org, hypothesis_id=hypothesis_id)


@router.get("/materials/{material_id}/predictions")
def material_predictions(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    org = _require_org(organisation_id)
    material = db.get(Material, material_id)
    if not material or (material.visibility != "public" and material.owner_organisation_id != org):
        raise HTTPException(404, "Material not found")
    return _prediction_history(db, org, material_id=material_id)
