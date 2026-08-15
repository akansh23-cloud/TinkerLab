from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    Material,
    MaterialComponent,
    MaterialPropertyDefinition,
    ModelApplicabilityDomain,
    PredictionInputSnapshot,
    PredictionModel,
    PredictionModelVersion,
    PredictionRun,
    PredictionTarget,
    PropertyPrediction,
    ReplacementProject,
    User,
)
from app.services.units import UnitError, convert, normalize_unit

PREDICTOR_CONTRACT_VERSION = "1.0"
FEATURE_NORMALIZATION_VERSION = "features-v1"
UNIT_NORMALIZATION_VERSION = "units-v1"
PREDICTION_CHECKSUM_VERSION = "prediction-v1"
HARD_MAX_PREDICTION_TARGETS = 200
SAFE_ARTIFACT_FORMATS = {"tinkerlab_linear_json_v1"}
DEMO_WARNING = "DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions."
logger = logging.getLogger("tinkerlab.prediction")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


def artifact_checksum(artifact_format: str, artifact_payload: dict[str, Any]) -> str:
    if artifact_format not in SAFE_ARTIFACT_FORMATS:
        raise ValueError("Unsafe or unsupported model artifact format")
    return checksum({"artifact_format": artifact_format, "artifact": artifact_payload})


def feature_schema_checksum(schema_version: str, schema: dict[str, Any]) -> str:
    return checksum({"schema_version": schema_version, "schema": schema})


def condition_checksum(conditions: dict[str, Any]) -> str:
    return checksum({"condition_contract": "conditions-v1", "conditions": _normalize_conditions_for_checksum(conditions)})


def _normalize_conditions_for_checksum(conditions: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(conditions):
        raw = conditions[key]
        if isinstance(raw, dict) and "value" in raw:
            unit = normalize_unit(str(raw.get("unit"))) if raw.get("unit") else None
            result[key] = {"value": float(raw["value"]), "unit": unit}
        else:
            result[key] = raw
    return result


@dataclass
class FeatureSnapshotData:
    target_kind: str
    target_id: str
    candidate_id: str | None
    material_family: str
    features: dict[str, Any]
    feature_checksum: str
    source_entity_checksum: str
    missing_features: list[str]
    redaction_flags: list[str]
    component_keys: list[str]


@dataclass
class ApplicabilityResult:
    status: str
    reasons: list[dict[str, Any]]
    domain_distance: float | None = None


class PropertyPredictor(Protocol):
    key: str
    contract_version: str
    artifact_formats: set[str]
    deterministic: bool
    maximum_safe_batch_size: int

    def predict_batch(self, model_version: PredictionModelVersion, features: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


class DemoLinearJsonPredictor:
    key = "demo_linear_json"
    contract_version = PREDICTOR_CONTRACT_VERSION
    artifact_formats = {"tinkerlab_linear_json_v1"}
    deterministic = True
    maximum_safe_batch_size = HARD_MAX_PREDICTION_TARGETS

    def _predict_one(self, model_version: PredictionModelVersion, features: dict[str, Any]) -> dict[str, Any]:
        artifact = model_version.artifact_payload
        if model_version.artifact_format not in self.artifact_formats:
            raise ValueError("Artifact format is not supported by this predictor")
        coefficients = artifact.get("coefficients") or {}
        point = float(artifact.get("intercept", 0.0))
        for key, coefficient in sorted(coefficients.items()):
            if key not in features:
                raise ValueError(f"Required model feature {key} missing during inference")
            point += float(coefficient) * float(features[key])
        uncertainty = artifact.get("uncertainty") or {}
        if uncertainty.get("method") != "fixed_validation_interval":
            raise ValueError("Demo predictor requires fixed_validation_interval uncertainty")
        half_width = float(uncertainty.get("half_width", 0.0))
        if half_width <= 0:
            raise ValueError("Prediction uncertainty half-width must be positive")
        return {
            "point": point,
            "lower": point - half_width,
            "upper": point + half_width,
            "stddev": uncertainty.get("stddev"),
            "coverage": uncertainty.get("coverage"),
            "uncertainty_method": "fixed_validation_interval",
            "warnings": [DEMO_WARNING],
        }

    def predict_batch(self, model_version: PredictionModelVersion, features: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(features) > self.maximum_safe_batch_size:
            raise ValueError("Prediction batch exceeds predictor safe limit")
        return [self._predict_one(model_version, item) for item in features]


PREDICTORS: dict[str, PropertyPredictor] = {DemoLinearJsonPredictor.key: DemoLinearJsonPredictor()}


def predictor_descriptor(key: str) -> dict[str, Any]:
    predictor = PREDICTORS.get(key)
    if not predictor:
        raise ValueError("Unregistered predictor")
    return {
        "key": predictor.key,
        "contract_version": predictor.contract_version,
        "artifact_formats": sorted(predictor.artifact_formats),
        "deterministic": predictor.deterministic,
        "maximum_safe_batch_size": predictor.maximum_safe_batch_size,
    }


def validate_model_version_definition(model: PredictionModel, values: dict[str, Any]) -> None:
    if values["artifact_format"] not in SAFE_ARTIFACT_FORMATS:
        raise ValueError("Unsafe or unsupported model artifact format")
    predictor = PREDICTORS.get(values["predictor_key"])
    if not predictor:
        raise ValueError("Unregistered predictor_key")
    if values["artifact_format"] not in predictor.artifact_formats:
        raise ValueError("Artifact format is not supported by predictor")
    if values["predictor_contract_version"] != predictor.contract_version:
        raise ValueError("Predictor contract version mismatch")
    if values["target_property_key"] not in model.supported_property_keys:
        raise ValueError("Model registry does not declare target property support")
    if not values.get("uncertainty_method"):
        raise ValueError("Uncertainty method is mandatory")
    schema = values.get("feature_schema") or {}
    if not isinstance(schema.get("features"), dict) or not schema["features"]:
        raise ValueError("Feature schema must declare typed features")


def create_model_version(db: Session, model: PredictionModel, values: dict[str, Any]) -> PredictionModelVersion:
    validate_model_version_definition(model, values)
    applicability = values.pop("applicability_domain")
    artifact = values.get("artifact_payload") or {}
    schema = values.get("feature_schema") or {}
    version = PredictionModelVersion(
        model_id=model.id,
        **values,
        artifact_checksum=artifact_checksum(values["artifact_format"], artifact),
        feature_schema_checksum=feature_schema_checksum(values["feature_schema_version"], schema),
    )
    db.add(version)
    db.flush()
    domain = ModelApplicabilityDomain(model_version_id=version.id, **applicability)
    db.add(domain)
    db.flush()
    return version


def approve_model_version(db: Session, model_version: PredictionModelVersion) -> PredictionModelVersion:
    if model_version.retired_at is not None:
        raise ValueError("Retired model version cannot be approved")
    model_version.approved_at = model_version.approved_at or now_utc()
    model_version.model.status = "approved"
    db.flush()
    return model_version


def model_version_executable(model_version: PredictionModelVersion) -> tuple[bool, str | None]:
    model = model_version.model
    if model.status != "approved":
        return False, f"Model status is {model.status}; approved is required"
    if model_version.approved_at is None:
        return False, "Model version has not been approved"
    if model_version.retired_at is not None:
        return False, "Model version is retired"
    if model_version.artifact_format not in SAFE_ARTIFACT_FORMATS:
        return False, "Model artifact format is unsafe/unsupported"
    if artifact_checksum(model_version.artifact_format, model_version.artifact_payload) != model_version.artifact_checksum:
        return False, "Model artifact checksum mismatch"
    if feature_schema_checksum(model_version.feature_schema_version, model_version.feature_schema) != model_version.feature_schema_checksum:
        return False, "Feature schema checksum mismatch"
    return True, None


def get_model_version(db: Session, version_id: str) -> PredictionModelVersion | None:
    return (
        db.query(PredictionModelVersion)
        .options(
            selectinload(PredictionModelVersion.model),
            selectinload(PredictionModelVersion.applicability_domain),
        )
        .filter(PredictionModelVersion.id == version_id)
        .one_or_none()
    )


def require_model_version(db: Session, version_id: str) -> PredictionModelVersion:
    """Strict accessor for call sites that have already persisted a model-version reference.

    A missing row here means the pinned scientific contract has been deleted, which must fail
    loudly rather than silently degrading a prediction, campaign or simulation record.
    """
    version = get_model_version(db, version_id)
    if version is None:
        raise ValueError(f"Pinned prediction model version {version_id} no longer exists")
    return version


def _normalise_component_amount(component: MaterialComponent) -> float | None:
    if component.amount_value is None:
        return None
    if component.amount_basis != "weight_percent":
        return None
    if component.amount_unit not in {"%", None}:
        return None
    return float(component.amount_value)


def _component_features(rows: list[dict[str, Any]], composition_complete: bool) -> tuple[dict[str, Any], list[str]]:
    roles: dict[str, float] = {}
    keys: dict[str, float] = {}
    component_keys: list[str] = []
    for row in rows:
        key = str(row["key"]).strip().lower()
        role = (row.get("role") or "").strip().lower()
        amount = row.get("amount")
        component_keys.append(key)
        if amount is None:
            continue
        keys[key] = keys.get(key, 0.0) + float(amount)
        if role:
            roles[role] = roles.get(role, 0.0) + float(amount)
    features: dict[str, Any] = {
        "component_count": len(rows),
        "matrix_fraction_pct": roles.get("matrix", 0.0) if composition_complete else roles.get("matrix"),
        "primary_modifier_fraction_pct": keys.get("modifier_b", 0.0) if composition_complete else keys.get("modifier_b"),
        "alternative_modifier_fraction_pct": keys.get("modifier_b2", 0.0) if composition_complete else keys.get("modifier_b2"),
        "total_modifier_fraction_pct": roles.get("modifier", 0.0) if composition_complete else roles.get("modifier"),
        "reinforcement_fraction_pct": roles.get("reinforcement", 0.0) if composition_complete else roles.get("reinforcement"),
    }
    return features, sorted(component_keys)


def _known_material_snapshot_from_entity(material: Material, candidate_id: str | None = None) -> FeatureSnapshotData:
    rows: list[dict[str, Any]] = []
    redactions: list[str] = []
    total = 0.0
    amount_complete = True
    for component in sorted(material.components, key=lambda x: (x.sequence, x.id)):
        if component.is_redacted:
            redactions.append(component.component_identifier or component.redaction_label or component.id)
        amount = _normalise_component_amount(component)
        if amount is None:
            amount_complete = False
        else:
            total += amount
        rows.append({"key": component.component_identifier or component.component_name, "role": component.component_role, "amount": amount, "redacted": component.is_redacted})
    composition_complete = bool(rows) and not redactions and amount_complete and abs(total - 100.0) <= 0.01
    features, component_keys = _component_features(rows, composition_complete)
    source_payload = {"source_kind": "known_material", "material_family": material.material_family, "components": rows, "process_states": [{"state_label": p.state_label, "process_name": p.process_name, "sequence": p.sequence, "parameters": p.parameters} for p in sorted(material.process_states, key=lambda x: (x.sequence, x.id))]}
    missing = [k for k, v in features.items() if v is None]
    if not composition_complete:
        missing.append("complete_weight_percent_composition")
    payload = {"normalization_version": FEATURE_NORMALIZATION_VERSION, "features": features}
    return FeatureSnapshotData(target_kind="known_material", target_id=material.id, candidate_id=candidate_id, material_family=material.material_family, features=features, feature_checksum=checksum(payload), source_entity_checksum=checksum(source_payload), missing_features=sorted(set(missing)), redaction_flags=sorted(redactions), component_keys=component_keys)


def _known_material_snapshot(db: Session, material_id: str, candidate_id: str | None = None) -> FeatureSnapshotData:
    material = db.query(Material).options(selectinload(Material.components), selectinload(Material.process_states)).filter(Material.id == material_id).one()
    return _known_material_snapshot_from_entity(material, candidate_id)


def _hypothesis_snapshot_from_entity(hypothesis: CandidateHypothesis, candidate_id: str | None = None) -> FeatureSnapshotData:
    rows: list[dict[str, Any]] = []
    total = 0.0
    complete = True
    for component in sorted(hypothesis.components, key=lambda x: (x.sequence, x.id)):
        amount = float(component.amount) if component.amount is not None and component.basis == "weight_percent" and component.unit in {"%", None} else None
        if amount is None:
            complete = False
        else:
            total += amount
        rows.append({"key": component.component_key, "role": component.role, "amount": amount, "locked": component.locked})
    composition_complete = bool(rows) and complete and abs(total - 100.0) <= 0.01
    features, component_keys = _component_features(rows, composition_complete)
    for process in sorted(hypothesis.process_parameters, key=lambda x: (x.parameter_key, x.id)):
        if process.parameter_key == "generic_process_temperature":
            try:
                features["generic_process_temperature_degC"] = convert(float(process.value), process.unit, "degC")
            except UnitError:
                features["generic_process_temperature_degC"] = None
    missing = [k for k, v in features.items() if v is None]
    if not composition_complete:
        missing.append("complete_weight_percent_composition")
    source_payload = {"source_kind": "hypothesis", "fingerprint": hypothesis.deterministic_fingerprint, "fingerprint_version": hypothesis.fingerprint_version, "components": rows, "process_parameters": [{"parameter_key": p.parameter_key, "value": p.value, "unit": p.unit} for p in sorted(hypothesis.process_parameters, key=lambda x: (x.parameter_key, x.id))]}
    payload = {"normalization_version": FEATURE_NORMALIZATION_VERSION, "features": features}
    return FeatureSnapshotData(target_kind="hypothesis", target_id=hypothesis.id, candidate_id=candidate_id, material_family=hypothesis.material_family, features=features, feature_checksum=checksum(payload), source_entity_checksum=checksum(source_payload), missing_features=sorted(set(missing)), redaction_flags=[], component_keys=component_keys)


def _hypothesis_snapshot(db: Session, hypothesis_id: str, candidate_id: str | None = None) -> FeatureSnapshotData:
    hypothesis = db.query(CandidateHypothesis).options(selectinload(CandidateHypothesis.components), selectinload(CandidateHypothesis.process_parameters)).filter(CandidateHypothesis.id == hypothesis_id).one()
    return _hypothesis_snapshot_from_entity(hypothesis, candidate_id)


def resolve_target_snapshot(db: Session, project: ReplacementProject, target: dict[str, Any], organisation_id: str) -> FeatureSnapshotData:
    return resolve_target_snapshots(db, project, [target], organisation_id)[0]


def resolve_target_snapshots(db: Session, project: ReplacementProject, targets: list[dict[str, Any]], organisation_id: str) -> list[FeatureSnapshotData]:
    if organisation_id != project.organisation_id:
        raise ValueError("Project is outside organisation scope")
    candidate_ids = [str(t["candidate_id"]) for t in targets if t.get("candidate_id")]
    candidates: dict[str, Candidate] = {}
    if candidate_ids:
        rows = db.query(Candidate).filter(Candidate.project_id == project.id, Candidate.id.in_(candidate_ids)).all()
        candidates = {c.id: c for c in rows}
        if len(candidates) != len(set(candidate_ids)):
            raise ValueError("Candidate not found in project")
    material_ids: set[str] = {str(t["material_id"]) for t in targets if t.get("material_id")}
    hypothesis_ids: set[str] = {str(t["hypothesis_id"]) for t in targets if t.get("hypothesis_id")}
    for c in candidates.values():
        if c.candidate_kind == "known_material" and c.material_id:
            material_ids.add(c.material_id)
        elif c.candidate_kind == "hypothesis" and c.hypothesis_id:
            hypothesis_ids.add(c.hypothesis_id)
        else:
            raise ValueError("Candidate target is malformed")
    materials: dict[str, Material] = {}
    if material_ids:
        material_rows = db.query(Material).options(selectinload(Material.components), selectinload(Material.process_states)).filter(Material.id.in_(material_ids)).all()
        materials = {m.id: m for m in material_rows}
    hypotheses: dict[str, CandidateHypothesis] = {}
    if hypothesis_ids:
        hypothesis_rows = db.query(CandidateHypothesis).options(selectinload(CandidateHypothesis.components), selectinload(CandidateHypothesis.process_parameters)).filter(CandidateHypothesis.id.in_(hypothesis_ids), CandidateHypothesis.project_id == project.id, CandidateHypothesis.organisation_id == organisation_id).all()
        hypotheses = {h.id: h for h in hypothesis_rows}
    candidate_by_hyp = {c.hypothesis_id: c.id for c in candidates.values() if c.hypothesis_id}
    direct_hyp_ids = [hid for hid in hypothesis_ids if hid not in candidate_by_hyp]
    if direct_hyp_ids:
        rows = db.query(Candidate).filter(Candidate.project_id == project.id, Candidate.hypothesis_id.in_(direct_hyp_ids)).all()
        candidate_by_hyp.update({c.hypothesis_id: c.id for c in rows if c.hypothesis_id})
    result: list[FeatureSnapshotData] = []
    for target in targets:
        if target.get("candidate_id"):
            candidate = candidates[str(target["candidate_id"])]
            if candidate.candidate_kind == "known_material" and candidate.material_id:
                material = materials.get(candidate.material_id)
                if not material or (material.visibility != "public" and material.owner_organisation_id != organisation_id):
                    raise ValueError("Material outside organisation scope")
                result.append(_known_material_snapshot_from_entity(material, candidate.id))
            else:
                hypothesis = hypotheses.get(str(candidate.hypothesis_id))
                if not hypothesis:
                    raise ValueError("Hypothesis outside organisation scope")
                result.append(_hypothesis_snapshot_from_entity(hypothesis, candidate.id))
        elif target.get("material_id"):
            material = materials.get(str(target["material_id"]))
            if not material:
                raise ValueError("Material not found")
            if material.visibility != "public" and material.owner_organisation_id != organisation_id:
                raise ValueError("Material outside organisation scope")
            result.append(_known_material_snapshot_from_entity(material))
        elif target.get("hypothesis_id"):
            hypothesis = hypotheses.get(str(target["hypothesis_id"]))
            if not hypothesis:
                raise ValueError("Hypothesis not found in project scope")
            result.append(_hypothesis_snapshot_from_entity(hypothesis, candidate_by_hyp.get(hypothesis.id)))
        else:
            raise ValueError("Prediction target is empty")
    return result

def _required_features(model_version: PredictionModelVersion) -> list[str]:
    domain = model_version.applicability_domain
    if domain:
        return list(domain.required_feature_keys)
    schema = model_version.feature_schema.get("features") or {}
    return sorted(k for k, v in schema.items() if isinstance(v, dict) and v.get("required"))


def assess_applicability(model_version: PredictionModelVersion, snapshot: FeatureSnapshotData, property_key: str, conditions: dict[str, Any]) -> ApplicabilityResult:
    reasons: list[dict[str, Any]] = []
    executable, executable_reason = model_version_executable(model_version)
    if not executable:
        reasons.append({"code": "MODEL_NOT_EXECUTABLE", "message": executable_reason})
        return ApplicabilityResult("out_of_domain", reasons)
    model = model_version.model
    if property_key != model_version.target_property_key or property_key not in model.supported_property_keys:
        reasons.append({"code": "UNSUPPORTED_PROPERTY", "message": f"Model version does not support {property_key}"})
        return ApplicabilityResult("unsupported_property", reasons)
    domain = model_version.applicability_domain
    families = (domain.material_families if domain else model.supported_material_families) or model.supported_material_families
    if snapshot.material_family not in families:
        reasons.append({"code": "UNSUPPORTED_MATERIAL_FAMILY", "message": f"Material family {snapshot.material_family} is unsupported", "value": snapshot.material_family, "allowed": families})
        return ApplicabilityResult("unsupported_material_family", reasons)
    required = _required_features(model_version)
    missing = [key for key in required if key not in snapshot.features or snapshot.features.get(key) is None]
    if snapshot.redaction_flags and domain and domain.redacted_input_policy == "reject":
        reasons.append({"code": "REDACTED_REQUIRED_INPUT", "message": "Scientific inputs contain redacted composition fields", "value": snapshot.redaction_flags})
    if missing or "complete_weight_percent_composition" in snapshot.missing_features:
        reasons.append({"code": "MISSING_REQUIRED_FEATURE", "message": "One or more required features are unavailable", "value": sorted(set(missing + snapshot.missing_features))})
    if reasons:
        return ApplicabilityResult("incomplete_inputs", reasons)
    if domain:
        borderline = False
        for key, bounds in sorted((domain.numeric_feature_ranges or {}).items()):
            if key not in snapshot.features:
                continue
            value = snapshot.features[key]
            if value is None:
                continue
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                continue
            lo, hi = float(bounds[0]), float(bounds[1])
            tol = float(domain.borderline_tolerance or 0.0)
            if value < lo:
                if lo - float(value) <= tol:
                    borderline = True
                    reasons.append({"code": "FEATURE_BORDERLINE_LOW", "message": f"{key} is just outside the declared model domain", "feature": key, "value": value, "allowed": [lo, hi]})
                else:
                    reasons.append({"code": "FEATURE_OUTSIDE_TRAINING_RANGE", "message": f"{key} is outside the declared model domain", "feature": key, "value": value, "allowed": [lo, hi]})
            elif value > hi:
                if float(value) - hi <= tol:
                    borderline = True
                    reasons.append({"code": "FEATURE_BORDERLINE_HIGH", "message": f"{key} is just outside the declared model domain", "feature": key, "value": value, "allowed": [lo, hi]})
                else:
                    reasons.append({"code": "FEATURE_OUTSIDE_TRAINING_RANGE", "message": f"{key} is outside the declared model domain", "feature": key, "value": value, "allowed": [lo, hi]})
        if any(r["code"] == "FEATURE_OUTSIDE_TRAINING_RANGE" for r in reasons):
            return ApplicabilityResult("out_of_domain", reasons)
        condition_ranges = domain.target_condition_ranges or {}
        for key, rule in sorted(condition_ranges.items()):
            raw = conditions.get(key)
            if raw is None:
                if rule.get("required", False):
                    reasons.append({"code": "MISSING_TARGET_CONDITION", "message": f"Required target condition {key} is missing", "feature": key})
                continue
            if not isinstance(raw, dict) or "value" not in raw or not raw.get("unit"):
                reasons.append({"code": "INVALID_TARGET_CONDITION", "message": f"Target condition {key} must include value and unit", "feature": key})
                continue
            try:
                value = convert(float(raw["value"]), str(raw["unit"]), str(rule["unit"]))
            except (UnitError, KeyError, ValueError) as exc:
                reasons.append({"code": "UNSUPPORTED_CONDITION_UNIT", "message": str(exc), "feature": key})
                continue
            lo, hi = float(rule["min"]), float(rule["max"])
            tol = float(rule.get("borderline_tolerance", domain.borderline_tolerance or 0.0))
            if value < lo or value > hi:
                distance = lo - value if value < lo else value - hi
                if distance <= tol:
                    borderline = True
                    reasons.append({"code": "CONDITION_BORDERLINE", "message": f"Target condition {key} is borderline", "feature": key, "value": value, "allowed": [lo, hi]})
                else:
                    reasons.append({"code": "CONDITION_OUTSIDE_DOMAIN", "message": f"Target condition {key} is outside model domain", "feature": key, "value": value, "allowed": [lo, hi]})
        if any(r["code"] in {"MISSING_TARGET_CONDITION", "INVALID_TARGET_CONDITION", "UNSUPPORTED_CONDITION_UNIT", "CONDITION_OUTSIDE_DOMAIN"} for r in reasons):
            return ApplicabilityResult("unsupported_conditions", reasons)
        if borderline:
            return ApplicabilityResult("borderline", reasons or [{"code": "BORDERLINE_DOMAIN", "message": "Target lies at the model applicability boundary"}])
    return ApplicabilityResult("in_domain", reasons)


def _model_label(model_version: PredictionModelVersion) -> str:
    return f"{model_version.model.display_name} v{model_version.version}"


def _preview_target(db: Session, project: ReplacementProject, model_version: PredictionModelVersion, target: dict[str, Any], property_key: str, conditions: dict[str, Any], organisation_id: str) -> tuple[FeatureSnapshotData, ApplicabilityResult]:
    snapshot = resolve_target_snapshot(db, project, target, organisation_id)
    applicability = assess_applicability(model_version, snapshot, property_key, conditions)
    return snapshot, applicability


def preview_prediction_run(db: Session, project: ReplacementProject, model_version: PredictionModelVersion, targets: list[dict[str, Any]], property_key: str, conditions: dict[str, Any], configuration: dict[str, Any], organisation_id: str) -> dict[str, Any]:
    if not targets or len(targets) > HARD_MAX_PREDICTION_TARGETS:
        raise ValueError(f"Prediction batch must contain 1..{HARD_MAX_PREDICTION_TARGETS} targets")
    rows = []
    snapshots = resolve_target_snapshots(db, project, targets, organisation_id)
    for snapshot in snapshots:
        applicability = assess_applicability(model_version, snapshot, property_key, conditions)
        rows.append({
            "target_kind": snapshot.target_kind,
            "target_id": snapshot.target_id,
            "candidate_id": snapshot.candidate_id,
            "applicability_status": applicability.status,
            "reasons": applicability.reasons,
            "feature_checksum": snapshot.feature_checksum,
            "missing_features": snapshot.missing_features,
            "redaction_flags": snapshot.redaction_flags,
        })
    in_domain = sum(r["applicability_status"] == "in_domain" for r in rows)
    borderline = sum(r["applicability_status"] == "borderline" for r in rows)
    inapplicable = len(rows) - in_domain - borderline
    executable, issue = model_version_executable(model_version)
    problems = [] if executable else [issue or "Model version is not executable"]
    demo_warning = DEMO_WARNING if model_version.immutable_metadata.get("demo_only") else None
    return {
        "valid": executable and (in_domain + borderline) > 0,
        "model_id": model_version.model_id,
        "model_version_id": model_version.id,
        "model_version": model_version.version,
        "model_label": _model_label(model_version),
        "demo_warning": demo_warning,
        "property_key": property_key,
        "feature_schema_version": model_version.feature_schema_version,
        "target_condition_checksum": condition_checksum(conditions),
        "configuration_checksum": checksum({"configuration": configuration, "requested_property": property_key}),
        "target_count": len(rows),
        "in_domain_count": in_domain,
        "borderline_count": borderline,
        "inapplicable_count": inapplicable,
        "expected_model_executions": in_domain + borderline,
        "targets": rows,
        "validation_problems": problems,
    }


def _create_target_and_snapshot(db: Session, project: ReplacementProject, model_version: PredictionModelVersion, definition: MaterialPropertyDefinition, snapshot: FeatureSnapshotData, applicability: ApplicabilityResult, conditions: dict[str, Any], requested_output_unit: str | None, organisation_id: str) -> tuple[PredictionTarget, PredictionInputSnapshot]:
    target = PredictionTarget(
        organisation_id=organisation_id,
        project_id=project.id,
        candidate_id=snapshot.candidate_id,
        material_id=snapshot.target_id if snapshot.target_kind == "known_material" else None,
        hypothesis_id=snapshot.target_id if snapshot.target_kind == "hypothesis" else None,
        property_definition_id=definition.id,
        requested_conditions=_normalize_conditions_for_checksum(conditions),
        condition_checksum=condition_checksum(conditions),
        requested_output_unit=requested_output_unit,
    )
    db.add(target)
    db.flush()
    input_snapshot = PredictionInputSnapshot(
        prediction_target_id=target.id,
        model_version_id=model_version.id,
        target_kind=snapshot.target_kind,
        target_scientific_id=snapshot.target_id,
        feature_schema_version=model_version.feature_schema_version,
        normalized_feature_payload=snapshot.features,
        feature_checksum=snapshot.feature_checksum,
        source_entity_checksum=snapshot.source_entity_checksum,
        target_condition_checksum=target.condition_checksum,
        missing_features=snapshot.missing_features,
        redaction_flags=snapshot.redaction_flags,
        unit_normalization_version=UNIT_NORMALIZATION_VERSION,
    )
    db.add(input_snapshot)
    db.flush()
    return target, input_snapshot


def _prediction_result_checksum(model_version: PredictionModelVersion, input_snapshot: PredictionInputSnapshot, definition: MaterialPropertyDefinition, applicability: ApplicabilityResult, output: dict[str, Any], configuration_checksum: str) -> str:
    return checksum({
        "version": PREDICTION_CHECKSUM_VERSION,
        "model_version_id": model_version.id,
        "artifact_checksum": model_version.artifact_checksum,
        "predictor_contract_version": model_version.predictor_contract_version,
        "feature_checksum": input_snapshot.feature_checksum,
        "property_key": definition.key,
        "condition_checksum": input_snapshot.target_condition_checksum,
        "configuration_checksum": configuration_checksum,
        "applicability_status": applicability.status,
        "output": output,
    })


def execute_prediction_run(db: Session, project: ReplacementProject, model_version: PredictionModelVersion, targets: list[dict[str, Any]], property_key: str, conditions: dict[str, Any], requested_output_unit: str | None, configuration: dict[str, Any], created_by: str, organisation_id: str, run_id: str | None = None) -> PredictionRun:
    preview = preview_prediction_run(db, project, model_version, targets, property_key, conditions, configuration, organisation_id)
    if not preview["valid"] and preview["expected_model_executions"] == 0:
        # Persisting an all-inapplicable batch is still scientifically useful, so only model lifecycle invalidity blocks it.
        if preview["validation_problems"]:
            raise ValueError("; ".join(preview["validation_problems"]))
    if not db.get(User, created_by):
        raise ValueError("created_by user not found")
    definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
    if not definition:
        raise ValueError("Unknown property definition")
    config_checksum = preview["configuration_checksum"]
    run = PredictionRun(
        id=run_id,
        organisation_id=organisation_id,
        project_id=project.id,
        model_version_id=model_version.id,
        property_key=property_key,
        configuration_checksum=config_checksum,
        target_condition_checksum=preview["target_condition_checksum"],
        requested_target_count=len(targets),
        predicted_count=0,
        inapplicable_count=0,
        failed_count=0,
        status="running",
        run_seed=None,
        started_at=now_utc(),
        created_by=created_by,
        metadata_json={"prediction_contract": PREDICTION_CHECKSUM_VERSION, "demo_warning": preview["demo_warning"]},
    )
    db.add(run)
    db.flush()
    predictor = PREDICTORS[model_version.predictor_key]
    snapshots = resolve_target_snapshots(db, project, targets, organisation_id)
    applicability_results = [assess_applicability(model_version, snapshot, property_key, conditions) for snapshot in snapshots]
    executable_indices = [i for i, item in enumerate(applicability_results) if item.status in {"in_domain", "borderline"}]
    batch_outputs: dict[int, dict[str, Any]] = {}
    if executable_indices:
        try:
            outputs = predictor.predict_batch(model_version, [snapshots[i].features for i in executable_indices])
            if len(outputs) != len(executable_indices):
                raise ValueError("Predictor returned an unexpected batch result count")
            batch_outputs = dict(zip(executable_indices, outputs, strict=True))
        except Exception as exc:
            logger.exception("prediction_batch_failed", extra={"run_id": run.id, "project_id": project.id, "model_version_id": model_version.id})
            batch_outputs = {index: {"failure": type(exc).__name__} for index in executable_indices}
    result_checksums: list[str] = []
    for index, snapshot in enumerate(snapshots):
        applicability = applicability_results[index]
        target, input_snapshot = _create_target_and_snapshot(db, project, model_version, definition, snapshot, applicability, conditions, requested_output_unit, organisation_id)
        output: dict[str, Any] = {"point": None, "lower": None, "upper": None, "unit": requested_output_unit or model_version.canonical_output_unit}
        status = "inapplicable"; warnings: list[str] = []
        point = lower = upper = stddev = coverage = None
        output_unit = requested_output_unit or model_version.canonical_output_unit
        if applicability.status in {"in_domain", "borderline"}:
            predicted = batch_outputs.get(index) or {"failure": "MissingBatchOutput"}
            if predicted.get("failure"):
                status = "failed"; warnings = [f"Prediction execution failed: {predicted['failure']}"]; run.failed_count += 1
                output = {"point": None, "lower": None, "upper": None, "unit": output_unit, "failure": predicted["failure"]}
            else:
                point = float(predicted["point"]); lower = float(predicted["lower"]); upper = float(predicted["upper"])
                stddev = float(predicted["stddev"]) if predicted.get("stddev") is not None else None
                coverage = float(predicted["coverage"]) if predicted.get("coverage") is not None else None
                warnings = list(predicted.get("warnings") or [])
                if applicability.status == "borderline": warnings.append("BORDERLINE APPLICABILITY — prediction should be treated with additional caution.")
                if output_unit != model_version.canonical_output_unit:
                    point = convert(point, model_version.canonical_output_unit, output_unit); lower = convert(lower, model_version.canonical_output_unit, output_unit); upper = convert(upper, model_version.canonical_output_unit, output_unit)
                status = "predicted"; run.predicted_count += 1
                output = {"point": point, "lower": lower, "upper": upper, "unit": output_unit, "coverage": coverage}
        else:
            run.inapplicable_count += 1
        canonical_point = convert(point, output_unit, model_version.canonical_output_unit) if point is not None else None
        result_checksum = _prediction_result_checksum(model_version, input_snapshot, definition, applicability, output, config_checksum)
        prediction = PropertyPrediction(prediction_run_id=run.id, prediction_target_id=target.id, model_version_id=model_version.id, input_snapshot_id=input_snapshot.id, property_definition_id=definition.id, applicability_status=applicability.status, applicability_rationale=applicability.reasons, domain_distance=applicability.domain_distance, numeric_point_estimate=point, output_unit=output_unit if point is not None else model_version.canonical_output_unit, canonical_value=canonical_point, canonical_unit=model_version.canonical_output_unit, uncertainty_lower=lower, uncertainty_upper=upper, uncertainty_stddev=stddev, uncertainty_method=model_version.uncertainty_method, calibrated_coverage_level=coverage, warnings=warnings, status=status, deterministic_result_checksum=result_checksum)
        db.add(prediction); db.flush(); result_checksums.append(result_checksum)
    run.status = "completed"
    run.completed_at = now_utc()
    run.result_checksum = checksum({"prediction_run_result_v1": result_checksums})
    db.commit()
    return run


def get_run(db: Session, run_id: str, organisation_id: str) -> PredictionRun | None:
    return db.query(PredictionRun).filter(PredictionRun.id == run_id, PredictionRun.organisation_id == organisation_id).one_or_none()


def predictions_for_run(db: Session, run_id: str, organisation_id: str, offset: int = 0, limit: int = 100) -> tuple[list[PropertyPrediction], int]:
    run = get_run(db, run_id, organisation_id)
    if not run:
        return [], 0
    query = db.query(PropertyPrediction).join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id).filter(
        PropertyPrediction.prediction_run_id == run_id,
        PredictionTarget.organisation_id == organisation_id,
    )
    total = query.count()
    items = query.order_by(PropertyPrediction.created_at, PropertyPrediction.id).offset(offset).limit(limit).all()
    return items, total


def prediction_map_for_run(db: Session, run_id: str, project_id: str, organisation_id: str) -> dict[tuple[str, str], PropertyPrediction]:
    run = get_run(db, run_id, organisation_id)
    if not run or run.project_id != project_id:
        raise ValueError("Prediction run not found in project scope")
    rows = (
        db.query(PropertyPrediction, PredictionTarget, MaterialPropertyDefinition)
        .join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id)
        .join(MaterialPropertyDefinition, MaterialPropertyDefinition.id == PropertyPrediction.property_definition_id)
        .filter(PropertyPrediction.prediction_run_id == run_id, PredictionTarget.organisation_id == organisation_id)
        .all()
    )
    result: dict[tuple[str, str], PropertyPrediction] = {}
    for prediction, target, definition in rows:
        if target.candidate_id:
            result[(target.candidate_id, definition.key)] = prediction
        elif target.hypothesis_id:
            result[(target.hypothesis_id, definition.key)] = prediction
        elif target.material_id:
            result[(target.material_id, definition.key)] = prediction
    return result


def interval_constraint_status(prediction: PropertyPrediction, comparator: str, target_value: float | None, target_upper: float | None, target_unit: str | None) -> tuple[str, bool, str | None]:
    if prediction.status != "predicted" or prediction.uncertainty_lower is None or prediction.uncertainty_upper is None:
        return "UNKNOWN", False, "NO_APPLICABLE_PREDICTION"
    if target_value is None or not target_unit or not prediction.output_unit:
        return "UNKNOWN", False, "PREDICTION_TARGET_NOT_NUMERIC"
    try:
        lower = convert(prediction.uncertainty_lower, prediction.output_unit, target_unit)
        upper = convert(prediction.uncertainty_upper, prediction.output_unit, target_unit)
    except UnitError:
        return "UNKNOWN", False, "PREDICTION_UNIT_INCOMPATIBLE"
    if lower > upper:
        lower, upper = upper, lower
    crosses = False
    if comparator == ">=":
        if lower >= target_value:
            return "PASS", False, None
        if upper < target_value:
            return "FAIL", False, None
        crosses = True
    elif comparator == ">":
        if lower > target_value:
            return "PASS", False, None
        if upper <= target_value:
            return "FAIL", False, None
        crosses = True
    elif comparator == "<=":
        if upper <= target_value:
            return "PASS", False, None
        if lower > target_value:
            return "FAIL", False, None
        crosses = True
    elif comparator == "<":
        if upper < target_value:
            return "PASS", False, None
        if lower >= target_value:
            return "FAIL", False, None
        crosses = True
    elif comparator == "between" and target_upper is not None:
        if lower >= target_value and upper <= target_upper:
            return "PASS", False, None
        if upper < target_value or lower > target_upper:
            return "FAIL", False, None
        crosses = True
    elif comparator == "=":
        # A continuous interval cannot prove exact equality; if the target is outside it, it fails, otherwise remains uncertain.
        if target_value < lower or target_value > upper:
            return "FAIL", False, None
        crosses = True
    else:
        return "UNKNOWN", False, "PREDICTION_COMPARATOR_UNSUPPORTED"
    if crosses:
        return "UNKNOWN", True, "PREDICTION_INTERVAL_CROSSES_CONSTRAINT"
    return "UNKNOWN", False, "PREDICTION_UNCERTAIN"


def prediction_detail(db: Session, prediction_id: str, organisation_id: str) -> dict[str, Any] | None:
    row = (
        db.query(PropertyPrediction, PredictionTarget, PredictionInputSnapshot, PredictionModelVersion, PredictionModel)
        .join(PredictionTarget, PredictionTarget.id == PropertyPrediction.prediction_target_id)
        .join(PredictionInputSnapshot, PredictionInputSnapshot.id == PropertyPrediction.input_snapshot_id)
        .join(PredictionModelVersion, PredictionModelVersion.id == PropertyPrediction.model_version_id)
        .join(PredictionModel, PredictionModel.id == PredictionModelVersion.model_id)
        .filter(PropertyPrediction.id == prediction_id, PredictionTarget.organisation_id == organisation_id)
        .one_or_none()
    )
    if not row:
        return None
    prediction, target, snapshot, version, model = row
    return {
        "prediction": prediction,
        "target": {
            "id": target.id,
            "candidate_id": target.candidate_id,
            "material_id": target.material_id,
            "hypothesis_id": target.hypothesis_id,
            "requested_conditions": target.requested_conditions,
            "condition_checksum": target.condition_checksum,
        },
        "feature_snapshot": {
            "id": snapshot.id,
            "target_kind": snapshot.target_kind,
            "target_scientific_id": snapshot.target_scientific_id,
            "feature_schema_version": snapshot.feature_schema_version,
            # The full normalized feature vector is only returned on this explicitly scoped detail endpoint.
            "normalized_features": snapshot.normalized_feature_payload,
            "feature_checksum": snapshot.feature_checksum,
            "source_entity_checksum": snapshot.source_entity_checksum,
            "missing_features": snapshot.missing_features,
            "redaction_flags": snapshot.redaction_flags,
            "unit_normalization_version": snapshot.unit_normalization_version,
        },
        "model": {"id": model.id, "key": model.key, "display_name": model.display_name, "status": model.status},
        "model_version": {
            "id": version.id,
            "version": version.version,
            "artifact_checksum": version.artifact_checksum,
            "feature_schema_version": version.feature_schema_version,
            "feature_schema_checksum": version.feature_schema_checksum,
            "uncertainty_method": version.uncertainty_method,
            "calibration_metrics": version.calibration_metrics,
            "validation_metrics": version.validation_metrics,
        },
        "demo_warning": DEMO_WARNING if version.immutable_metadata.get("demo_only") else None,
    }
