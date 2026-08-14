"""Phase-9 Experimental Design & Validation OS.

TinkerLab does not own a laboratory. This module manages the *record*: protocols, samples, plans,
runs, measurements, and the comparison between what was predicted, what was simulated and what was
measured.

Rules enforced here and asserted by tests:

  * A protocol version is immutable. A run pins the version it used, so editing a protocol later
    cannot change what a historical run says was done.
  * Every measurement traces to a sample. A measurement whose sample provenance is inadequate is
    recorded and marked INCOMPLETE_PROVENANCE — it is not quietly accepted as evidence.
  * Raw and processed artifacts stay distinguishable.
  * An experimental measurement never overwrites a prediction or a simulation. All three are
    retained so they can be compared, and disagreement is exposed rather than averaged.
  * Two experiments that disagree are both kept. Neither is deleted and the later one does not win.
  * 'Validated' is never used when only simulation exists.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.enums import (
    AgreementVerdict,
    ExperimentDesignKind,
    ExperimentRunStatus,
    InstrumentCalibrationStatus,
    MeasurementQuality,
    RequirementKind,
    RequirementStatus,
    ValidationState,
)
from app.models.entities import (
    ExperimentPlan,
    ExperimentProtocol,
    ExperimentProtocolVersion,
    ExperimentRecommendation,
    ExperimentRun,
    FunctionalRequirement,
    IndustrialViabilityAssessment,
    Instrument,
    MaterialPropertyDefinition,
    Measurement,
    Sample,
    ValidationAssessment,
)
from app.services.reasoning import _test_direction, collect_origin_values
from app.services.units import UnitError, convert

VALIDATION_POLICY_VERSION = "validation-v2"
EXPERIMENT_ADMISSIBILITY_VERSION = "experimental-admissibility-v1"
RECOMMENDATION_METHODOLOGY = "explainable_weighted_factors_v1"
MAX_PLAN_RUNS = 200
MAX_PAGE_SIZE = 200

EXPERIMENT_SEPARATION_NOTE = (
    "An experimental measurement is a distinct scientific origin. It does not overwrite a prediction "
    "or a simulation: all three are retained so they can be compared, and disagreement between them "
    "is reported rather than resolved by averaging."
)

NO_AUTONOMY_NOTE = (
    "TinkerLab records and recommends experiments. It does not order them, operate laboratory "
    "hardware, or perform them. Every run recorded here was carried out by a person who entered it."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


class ExperimentError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------------------------
def protocol_checksum(payload: dict[str, Any]) -> str:
    return checksum({"contract": "experiment-protocol-v1", "protocol": payload})


def create_protocol_version(
    db: Session, *, protocol: ExperimentProtocol, version: str, values: dict[str, Any],
    created_by: str | None = None, row_id: str | None = None,
) -> ExperimentProtocolVersion:
    """Create a NEW immutable version. Existing versions are never edited."""
    existing = (
        db.query(ExperimentProtocolVersion)
        .filter_by(protocol_id=protocol.id, version=version).one_or_none()
    )
    if existing:
        raise ExperimentError(
            f"Protocol version '{version}' already exists and is frozen. Create a new version "
            "instead: editing a published protocol would rewrite the history of runs that used it."
        )
    if not values.get("objective"):
        raise ExperimentError("A protocol version requires an explicit objective")
    if not values.get("measurement_procedure"):
        raise ExperimentError(
            "A protocol version requires a measurement procedure; a protocol that does not say how "
            "to measure cannot make a measurement traceable."
        )
    content = {k: values.get(k) for k in (
        "objective", "required_equipment", "sample_requirements", "preparation_steps",
        "controlled_variables", "independent_variables", "dependent_variables",
        "measurement_procedure", "calibration_requirements", "acceptance_criteria",
        "replicate_requirement", "control_requirement",
    )}
    row = ExperimentProtocolVersion(
        protocol_id=protocol.id, version=version, protocol_checksum=protocol_checksum(content),
        is_frozen=True, created_by=created_by, **values,
    )
    if row_id:
        row.id = row_id
    db.add(row)
    db.flush()
    # Earlier versions are superseded, not replaced: their content and checksum stay readable.
    for old in (
        db.query(ExperimentProtocolVersion)
        .filter(ExperimentProtocolVersion.protocol_id == protocol.id,
                ExperimentProtocolVersion.superseded_by_id.is_(None),
                ExperimentProtocolVersion.id != row.id).all()
    ):
        old.superseded_by_id = row.id
    db.flush()
    return row


def current_protocol_version(db: Session, protocol_id: str) -> ExperimentProtocolVersion | None:
    return (
        db.query(ExperimentProtocolVersion)
        .filter(ExperimentProtocolVersion.protocol_id == protocol_id,
                ExperimentProtocolVersion.superseded_by_id.is_(None))
        .order_by(ExperimentProtocolVersion.created_at.desc()).first()
    )


# ---------------------------------------------------------------------------------------------
# Samples
# ---------------------------------------------------------------------------------------------
def assess_sample_provenance(sample_values: dict[str, Any]) -> tuple[bool, list[str]]:
    """Decide whether a sample is traceable enough for its measurements to count as evidence."""
    gaps: list[str] = []
    if not sample_values.get("material_id") and not sample_values.get("hypothesis_id"):
        gaps.append("No material or hypothesis is recorded, so the specimen is not traceable to a substance.")
    if not sample_values.get("material_state_id"):
        gaps.append("No material state is recorded, so measurements cannot be qualified by structure, "
                    "processing history or condition.")
    if not sample_values.get("preparation_date"):
        gaps.append("No preparation date is recorded.")
    if not sample_values.get("batch_reference") and not sample_values.get("parent_sample_id"):
        gaps.append("Neither a batch reference nor a parent sample is recorded, so the specimen's "
                    "origin cannot be traced.")
    return (not gaps), gaps


def create_sample(db: Session, values: dict[str, Any], row_id: str | None = None) -> Sample:
    complete, gaps = assess_sample_provenance(values)
    sample = Sample(**values, provenance_complete=complete, provenance_gaps=gaps)
    if row_id:
        sample.id = row_id
    db.add(sample)
    db.flush()
    return sample


def sample_lineage(db: Session, sample_id: str, max_depth: int = 20) -> list[dict[str, Any]]:
    """Walk parent links to the root specimen. Bounded so a cycle cannot hang the request."""
    lineage: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = db.get(Sample, sample_id)
    while current and current.id not in seen and len(lineage) < max_depth:
        seen.add(current.id)
        lineage.append({
            "sample_id": current.id, "sample_code": current.sample_code,
            "sample_kind": current.sample_kind, "material_id": current.material_id,
            "material_state_id": current.material_state_id, "batch_reference": current.batch_reference,
            "provenance_complete": current.provenance_complete,
            "provenance_gaps": list(current.provenance_gaps or []),
        })
        current = db.get(Sample, current.parent_sample_id) if current.parent_sample_id else None
    return lineage


# ---------------------------------------------------------------------------------------------
# Design of experiments
# ---------------------------------------------------------------------------------------------
def expand_design(design_kind: str, factors: list[dict[str, Any]], replicate_count: int) -> list[dict[str, Any]]:
    """Expand a design into concrete factor-level combinations.

    Only designs this system genuinely implements are supported. Response-surface methods, Bayesian
    optimization and active learning are not offered, because offering a design without its
    mathematics would misrepresent what the software does.
    """
    if replicate_count < 1:
        raise ExperimentError("replicate_count must be at least 1")

    if design_kind == ExperimentDesignKind.SINGLE_RUN:
        combinations: list[dict[str, Any]] = [{}]
    elif design_kind == ExperimentDesignKind.ONE_FACTOR:
        if len(factors) != 1:
            raise ExperimentError("A one-factor design requires exactly one factor")
        factor = factors[0]
        combinations = [{factor["name"]: level} for level in factor["levels"]]
    elif design_kind == ExperimentDesignKind.PARAMETER_SWEEP:
        if len(factors) != 1:
            raise ExperimentError("A parameter sweep requires exactly one factor")
        factor = factors[0]
        combinations = [{factor["name"]: level} for level in factor["levels"]]
    elif design_kind == ExperimentDesignKind.FULL_FACTORIAL:
        if not factors:
            raise ExperimentError("A full factorial design requires at least one factor")
        combinations = [{}]
        for factor in factors:
            expanded: list[dict[str, Any]] = []
            for partial in combinations:
                for level in factor["levels"]:
                    expanded.append({**partial, factor["name"]: level})
            combinations = expanded
    else:
        raise ExperimentError(
            f"Design kind '{design_kind}' is not implemented. Only single-run, one-factor, "
            "parameter-sweep and full-factorial designs are available."
        )

    runs = [
        {"factor_levels": combination, "replicate_index": replicate}
        for combination in combinations
        for replicate in range(1, replicate_count + 1)
    ]
    if len(runs) > MAX_PLAN_RUNS:
        raise ExperimentError(
            f"This design expands to {len(runs)} runs, above the bound of {MAX_PLAN_RUNS}"
        )
    return runs


def create_plan(
    db: Session, *, organisation_id: str, display_name: str, objective: str, design_kind: str,
    protocol_version: ExperimentProtocolVersion, factors: list[dict[str, Any]],
    replicate_count: int = 1, control_plan: str | None = None, project_id: str | None = None,
    candidate_id: str | None = None, role_id: str | None = None, requirement_id: str | None = None,
    created_by: str | None = None,
    row_id: str | None = None,
) -> tuple[ExperimentPlan, list[dict[str, Any]]]:
    """Create a protocol-conformant experiment plan.

    Protocol requirements are executable constraints, not descriptive metadata. A plan that asks for
    fewer replicates than the pinned protocol or omits a required control is rejected before any run
    exists.
    """
    if replicate_count < int(protocol_version.replicate_requirement or 1):
        raise ExperimentError(
            f"PROTOCOL_REPLICATE_REQUIREMENT: protocol requires at least "
            f"{protocol_version.replicate_requirement} replicate(s); plan requested {replicate_count}."
        )
    if protocol_version.control_requirement and not (control_plan and control_plan.strip()):
        raise ExperimentError(
            "PROTOCOL_CONTROL_REQUIRED: the pinned protocol requires a control and the plan does not "
            "declare how that control will be run."
        )

    runs = expand_design(design_kind, factors, replicate_count)
    control_count = 1 if protocol_version.control_requirement else 0
    design = {
        "design_kind": design_kind, "factors": factors, "replicate_count": replicate_count,
        "protocol_checksum": protocol_version.protocol_checksum,
        "run_count": len(runs) + control_count,
        "control_required": bool(protocol_version.control_requirement),
        "control_plan": control_plan,
    }
    plan = ExperimentPlan(
        organisation_id=organisation_id, project_id=project_id, candidate_id=candidate_id, role_id=role_id,
        requirement_id=requirement_id, display_name=display_name, objective=objective,
        design_kind=design_kind, protocol_version_id=protocol_version.id, factors=factors,
        replicate_count=replicate_count, control_plan=control_plan,
        planned_run_count=len(runs) + control_count,
        design_checksum=checksum({"contract": "experiment-design-v2", "design": design}),
        status="planned", created_by=created_by,
    )
    if row_id:
        plan.id = row_id
    db.add(plan)
    db.flush()
    return plan, runs


def materialize_plan_runs(
    db: Session, *, plan: ExperimentPlan, runs: list[dict[str, Any]], run_code_prefix: str,
    sample_id: str | None = None, instrument_id: str | None = None,
) -> list[ExperimentRun]:
    version = db.get(ExperimentProtocolVersion, plan.protocol_version_id)
    if version is None:
        raise ExperimentError("The plan's protocol version no longer exists")
    created: list[ExperimentRun] = []
    for index, spec in enumerate(runs, start=1):
        row = ExperimentRun(
            organisation_id=plan.organisation_id, plan_id=plan.id,
            protocol_version_id=version.id,
            protocol_checksum_at_run=version.protocol_checksum,
            run_code=f"{run_code_prefix}-{index:03d}", sample_id=sample_id, instrument_id=instrument_id,
            replicate_index=int(spec.get("replicate_index", 1)),
            factor_levels=spec.get("factor_levels") or {}, status=ExperimentRunStatus.PLANNED,
        )
        db.add(row)
        created.append(row)

    # A required control is represented as an actual run, not only prose in control_plan. The
    # control may later be assigned a dedicated reference-standard sample by the operator.
    if version.control_requirement:
        control = ExperimentRun(
            organisation_id=plan.organisation_id, plan_id=plan.id,
            protocol_version_id=version.id, protocol_checksum_at_run=version.protocol_checksum,
            run_code=f"{run_code_prefix}-CTRL", sample_id=sample_id, instrument_id=instrument_id,
            replicate_index=1, is_control=True, factor_levels={}, status=ExperimentRunStatus.PLANNED,
            metadata_json={"control_requirement": version.control_requirement,
                           "control_plan": plan.control_plan},
        )
        db.add(control)
        created.append(control)
    db.flush()
    return created


# ---------------------------------------------------------------------------------------------
# Run lifecycle
# ---------------------------------------------------------------------------------------------
ALLOWED_RUN_TRANSITIONS: dict[str, set[str]] = {
    ExperimentRunStatus.PLANNED: {ExperimentRunStatus.READY, ExperimentRunStatus.CANCELLED},
    ExperimentRunStatus.READY: {ExperimentRunStatus.RUNNING, ExperimentRunStatus.CANCELLED},
    ExperimentRunStatus.RUNNING: {ExperimentRunStatus.COMPLETED, ExperimentRunStatus.INVALIDATED},
    ExperimentRunStatus.IN_PROGRESS: {ExperimentRunStatus.COMPLETED, ExperimentRunStatus.INVALIDATED},
    ExperimentRunStatus.COMPLETED: {ExperimentRunStatus.INVALIDATED},
    ExperimentRunStatus.INVALIDATED: set(),
    ExperimentRunStatus.CANCELLED: set(),
    ExperimentRunStatus.ABORTED: set(),
}


def transition_run(db: Session, run: ExperimentRun, target_status: str, reason: str | None = None) -> ExperimentRun:
    current = str(run.status)
    allowed = ALLOWED_RUN_TRANSITIONS.get(current, set())
    if target_status not in allowed:
        raise ExperimentError(
            f"INVALID_RUN_TRANSITION: run '{run.run_code}' cannot transition from '{current}' to '{target_status}'."
        )
    timestamp = now_utc()
    if target_status == ExperimentRunStatus.RUNNING:
        run.started_at = run.started_at or timestamp
    elif target_status == ExperimentRunStatus.COMPLETED:
        if not run.started_at:
            raise ExperimentError("RUN_NOT_STARTED: a run must be started before it can be completed.")
        run.completed_at = timestamp
    elif target_status == ExperimentRunStatus.INVALIDATED:
        if not reason or len(reason.strip()) < 10:
            raise ExperimentError("RUN_INVALIDATION_REASON_REQUIRED: invalidation requires a substantive reason.")
        run.invalidation_reason = reason.strip()
    run.status = target_status
    db.flush()
    if target_status == ExperimentRunStatus.INVALIDATED:
        invalidate_run_measurements(db, run)
    return run


# ---------------------------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class AdmissionDecision:
    quality: str
    codes: tuple[str, ...]
    reasons: tuple[str, ...]


class ExperimentalEvidenceAdmissionService:
    """Central, deterministic admission policy for physical measurements.

    Recording a row and admitting it as governing experimental evidence are intentionally different
    operations. Failed checks keep the record for provenance but prevent it from becoming ACCEPTED.
    """

    @staticmethod
    def _dependent_property_keys(version: ExperimentProtocolVersion) -> set[str]:
        keys: set[str] = set()
        for item in version.dependent_variables or []:
            if not isinstance(item, dict):
                continue
            for field in ("property_key", "key"):
                value = item.get(field)
                if value:
                    keys.add(str(value))
        return keys

    @staticmethod
    def _controlled_variable_mismatches(version: ExperimentProtocolVersion, conditions: dict[str, Any]) -> list[str]:
        mismatches: list[str] = []
        for key, expected in (version.controlled_variables or {}).items():
            if key not in conditions:
                continue
            actual = conditions[key]
            expected_value = expected
            tolerance = None
            if isinstance(expected, dict):
                expected_value = expected.get("target", expected.get("value"))
                tolerance = expected.get("tolerance")
            if expected_value is None:
                continue
            if tolerance is not None and isinstance(actual, (int, float)) and isinstance(expected_value, (int, float)):
                if abs(float(actual) - float(expected_value)) > float(tolerance):
                    mismatches.append(f"{key}={actual!r} is outside protocol target {expected_value!r}±{tolerance}.")
            elif actual != expected_value:
                mismatches.append(f"{key}={actual!r} differs from protocol-controlled value {expected_value!r}.")
        return mismatches


    @staticmethod
    def _sample_requirement_issues(version: ExperimentProtocolVersion, sample: Sample) -> tuple[list[str], list[str]]:
        """Evaluate sample requirements that the current schema can represent without guessing."""
        missing: list[str] = []
        mismatches: list[str] = []
        requirements = version.sample_requirements or {}
        attributes = sample.metadata_json or {}
        dimensions = sample.dimensions or {}
        for key, expected in requirements.items():
            if key == "geometry":
                if not sample.geometry:
                    missing.append("geometry is required by the protocol but is not recorded on the sample")
                elif str(sample.geometry).strip().lower() != str(expected).strip().lower():
                    mismatches.append(f"geometry={sample.geometry!r} does not satisfy required geometry {expected!r}")
                continue
            if key.startswith("min_") or key.startswith("max_"):
                bound_kind, field = key.split("_", 1)
                actual = dimensions.get(field)
                if actual is None:
                    missing.append(f"sample dimension '{field}' required by protocol field '{key}' is not recorded")
                    continue
                if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
                    mismatches.append(f"sample dimension '{field}' cannot be compared numerically with protocol value {expected!r}")
                    continue
                if bound_kind == "min" and float(actual) < float(expected):
                    mismatches.append(f"{field}={actual!r} is below protocol minimum {expected!r}")
                if bound_kind == "max" and float(actual) > float(expected):
                    mismatches.append(f"{field}={actual!r} is above protocol maximum {expected!r}")
                continue
            actual = attributes.get(key)
            if actual is None:
                missing.append(f"sample attribute '{key}' required by the protocol is not recorded")
            elif str(actual).strip().lower() != str(expected).strip().lower():
                mismatches.append(f"sample attribute {key}={actual!r} does not satisfy protocol value {expected!r}")
        return missing, mismatches

    def assess(
        self, db: Session, *, organisation_id: str, run: ExperimentRun,
        property_definition: MaterialPropertyDefinition, unit: str, measured_at: datetime,
        conditions: dict[str, Any], unit_convertible: bool,
    ) -> AdmissionDecision:
        codes: list[str] = []
        reasons: list[str] = []
        hard_reject = False
        incomplete = False
        provisional = False
        invalidated = False

        if run.organisation_id != organisation_id:
            codes.append("EVIDENCE_CROSS_TENANT")
            reasons.append("The run belongs to a different organisation.")
            hard_reject = True

        version = db.get(ExperimentProtocolVersion, run.protocol_version_id)
        protocol = db.get(ExperimentProtocol, version.protocol_id) if version else None
        if version is None or protocol is None or protocol.organisation_id != organisation_id:
            codes.append("PROTOCOL_VERSION_INVALID")
            reasons.append("The pinned protocol version is missing or is not owned by this organisation.")
            hard_reject = True
        elif run.protocol_checksum_at_run != version.protocol_checksum:
            codes.append("PROTOCOL_CHECKSUM_MISMATCH")
            reasons.append("The run's pinned protocol checksum does not match the immutable protocol version.")
            provisional = True

        sample = db.get(Sample, run.sample_id) if run.sample_id else None
        if sample is None:
            codes.append("SAMPLE_NOT_TRACEABLE")
            reasons.append("No sample is attached to the run, so this measurement is not traceable to a specimen.")
            incomplete = True
        else:
            if sample.organisation_id != organisation_id:
                codes.append("SAMPLE_CROSS_TENANT")
                reasons.append("The sample belongs to a different organisation.")
                hard_reject = True
            if not sample.provenance_complete:
                codes.append("SAMPLE_PROVENANCE_INCOMPLETE")
                reasons.append("The sample's provenance is incomplete: " + " ".join(sample.provenance_gaps or []))
                incomplete = True
            if version is not None:
                missing_sample_context, sample_mismatches = self._sample_requirement_issues(version, sample)
                for issue in missing_sample_context:
                    codes.append("SAMPLE_REQUIREMENT_CONTEXT_MISSING")
                    reasons.append(issue + ".")
                    provisional = True
                for issue in sample_mismatches:
                    codes.append("SAMPLE_REQUIREMENT_MISMATCH")
                    reasons.append(issue + ".")
                    hard_reject = True

        instrument = db.get(Instrument, run.instrument_id) if run.instrument_id else None
        if instrument is None:
            codes.append("INSTRUMENT_MISSING")
            reasons.append("No instrument is recorded for the run.")
            provisional = True
        else:
            if instrument.organisation_id != organisation_id:
                codes.append("INSTRUMENT_CROSS_TENANT")
                reasons.append("The instrument belongs to a different organisation.")
                hard_reject = True
            capabilities = set(instrument.measures_property_keys or [])
            if capabilities and property_definition.key not in capabilities:
                codes.append("INSTRUMENT_PROPERTY_MISMATCH")
                reasons.append(
                    f"Instrument '{instrument.key}' does not declare capability for property "
                    f"'{property_definition.key}'."
                )
                hard_reject = True
            elif not capabilities:
                codes.append("INSTRUMENT_CAPABILITY_UNDECLARED")
                reasons.append("The instrument has no declared measurable-property capability.")
                provisional = True

            if version is not None and version.required_equipment:
                declared_equipment = {str(x).strip().lower() for x in (instrument.equipment_capabilities or [])}
                missing_equipment = [
                    str(item) for item in version.required_equipment
                    if str(item).strip().lower() not in declared_equipment
                ]
                if missing_equipment:
                    codes.append("REQUIRED_EQUIPMENT_UNVERIFIED")
                    reasons.append(
                        "The selected measurement system does not declare protocol-required equipment capability: "
                        + ", ".join(missing_equipment) + "."
                    )
                    provisional = True

            if instrument.calibration_status == InstrumentCalibrationStatus.CALIBRATED:
                if not instrument.calibration_date or not instrument.calibration_reference:
                    codes.append("CALIBRATION_PROVENANCE_INCOMPLETE")
                    reasons.append("The calibrated status lacks a calibration date or reference.")
                    provisional = True
                if instrument.calibration_date and measured_at.date() < instrument.calibration_date:
                    codes.append("CALIBRATION_NOT_YET_VALID")
                    reasons.append("The measurement predates the recorded calibration.")
                    provisional = True
                if instrument.calibration_due_date and measured_at.date() > instrument.calibration_due_date:
                    codes.append("CALIBRATION_EXPIRED")
                    reasons.append(
                        f"Calibration expired on {instrument.calibration_due_date.isoformat()} before the "
                        f"measurement date {measured_at.date().isoformat()}."
                    )
                    provisional = True
                if version is not None and instrument.calibration_date:
                    max_age = (version.calibration_requirements or {}).get("instrument_calibration_within_days")
                    if isinstance(max_age, (int, float)) and (measured_at.date() - instrument.calibration_date).days > int(max_age):
                        codes.append("CALIBRATION_EXPIRED_BY_PROTOCOL")
                        reasons.append(
                            f"Protocol requires calibration within {int(max_age)} day(s), but this measurement is "
                            f"{(measured_at.date() - instrument.calibration_date).days} day(s) after calibration."
                        )
                        provisional = True
            elif instrument.calibration_status == InstrumentCalibrationStatus.NOT_APPLICABLE:
                if version and (version.calibration_requirements or {}):
                    codes.append("CALIBRATION_REQUIRED_BY_PROTOCOL")
                    reasons.append("The protocol declares calibration requirements but the instrument is marked not applicable.")
                    provisional = True
            else:
                codes.append("CALIBRATION_NOT_VALID")
                reasons.append(
                    f"The instrument's calibration status is '{instrument.calibration_status}'; calibration is not assumed."
                )
                provisional = True

        if protocol is not None:
            declared = self._dependent_property_keys(version) if version else set()
            protocol_property_matches = protocol.property_definition_id == property_definition.id
            if protocol.property_definition_id and not protocol_property_matches:
                codes.append("PROTOCOL_PROPERTY_MISMATCH")
                reasons.append(
                    f"The protocol is bound to a different property than '{property_definition.key}'."
                )
                hard_reject = True
            elif not protocol.property_definition_id and declared and property_definition.key not in declared:
                codes.append("PROTOCOL_PROPERTY_MISMATCH")
                reasons.append(
                    f"The protocol version does not declare '{property_definition.key}' as a dependent variable."
                )
                hard_reject = True
            elif not protocol.property_definition_id and not declared:
                codes.append("PROTOCOL_PROPERTY_UNDECLARED")
                reasons.append("The protocol does not declare which property this measurement procedure supports.")
                provisional = True

        if not unit_convertible:
            codes.append("UNIT_DIMENSION_MISMATCH")
            reasons.append(
                f"The reported unit '{unit}' could not be converted to the property's canonical unit; units are never reinterpreted."
            )
            incomplete = True

        effective_conditions = {**(run.conditions or {}), **(conditions or {})}
        if version is not None:
            for key in (version.controlled_variables or {}):
                if key not in effective_conditions:
                    codes.append("PROTOCOL_CONDITION_MISSING")
                    reasons.append(f"Protocol-controlled condition '{key}' is not recorded for this measurement.")
                    provisional = True
            for mismatch in self._controlled_variable_mismatches(version, effective_conditions):
                codes.append("PROTOCOL_CONDITION_MISMATCH")
                reasons.append(mismatch)
                provisional = True

            if version.control_requirement and run.plan_id and not run.is_control:
                completed_control = (
                    db.query(ExperimentRun)
                    .filter(ExperimentRun.plan_id == run.plan_id,
                            ExperimentRun.organisation_id == organisation_id,
                            ExperimentRun.is_control.is_(True),
                            ExperimentRun.status == ExperimentRunStatus.COMPLETED)
                    .first()
                )
                if completed_control is None:
                    codes.append("REQUIRED_CONTROL_NOT_COMPLETED")
                    reasons.append("The pinned protocol requires a control, but no completed control run exists for this plan.")
                    provisional = True

        status = str(run.status)
        if status in {ExperimentRunStatus.INVALIDATED, ExperimentRunStatus.CANCELLED, ExperimentRunStatus.ABORTED}:
            codes.append("RUN_INVALIDATED" if status == ExperimentRunStatus.INVALIDATED else "RUN_NOT_ADMISSIBLE")
            reasons.append(f"Run status '{status}' cannot govern experimental evidence.")
            invalidated = True
        elif status in {ExperimentRunStatus.PLANNED, ExperimentRunStatus.READY}:
            codes.append("RUN_NOT_COMPLETED")
            reasons.append(f"Run status '{status}' has not executed; a physical measurement cannot be accepted yet.")
            provisional = True
        elif status in {ExperimentRunStatus.RUNNING, ExperimentRunStatus.IN_PROGRESS}:
            codes.append("RUN_IN_PROGRESS")
            reasons.append("The run is still in progress; the measurement remains provisional until completion.")
            provisional = True
        elif status != ExperimentRunStatus.COMPLETED:
            codes.append("RUN_STATUS_UNKNOWN")
            reasons.append(f"Run status '{status}' is not an admissible completed state.")
            provisional = True

        if invalidated:
            quality = MeasurementQuality.INVALIDATED_SOURCE
        elif hard_reject:
            quality = MeasurementQuality.REJECTED
        elif incomplete:
            quality = MeasurementQuality.INCOMPLETE_PROVENANCE
        elif provisional:
            quality = MeasurementQuality.PROVISIONAL
        else:
            quality = MeasurementQuality.ACCEPTED
        return AdmissionDecision(quality=quality, codes=tuple(dict.fromkeys(codes)), reasons=tuple(reasons))


ADMISSION_SERVICE = ExperimentalEvidenceAdmissionService()


def record_measurement(
    db: Session, *, organisation_id: str, run: ExperimentRun, property_definition: MaterialPropertyDefinition,
    numeric_value: float, unit: str, uncertainty: float | None = None,
    uncertainty_type: str | None = None, method: str | None = None,
    conditions: dict[str, Any] | None = None, replicate_index: int = 1,
    measured_at: datetime | None = None, notes: str | None = None, row_id: str | None = None,
) -> Measurement:
    """Record a measurement and independently decide whether it is admissible evidence."""
    timestamp = measured_at or run.completed_at or now_utc()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    target_unit: str = property_definition.canonical_unit or unit
    canonical_unit: str | None = target_unit
    canonical_value: float | None
    unit_convertible = True
    try:
        canonical_value = convert(float(numeric_value), unit, target_unit)
    except (UnitError, TypeError, ValueError):
        canonical_value = None
        canonical_unit = None
        unit_convertible = False

    effective_conditions = {**(run.conditions or {}), **(conditions or {})}
    decision = ADMISSION_SERVICE.assess(
        db, organisation_id=organisation_id, run=run, property_definition=property_definition,
        unit=unit, measured_at=timestamp, conditions=effective_conditions, unit_convertible=unit_convertible,
    )

    measurement = Measurement(
        organisation_id=organisation_id, run_id=run.id, sample_id=run.sample_id,
        instrument_id=run.instrument_id, property_definition_id=property_definition.id,
        numeric_value=numeric_value, unit=unit, canonical_value=canonical_value,
        canonical_unit=canonical_unit, uncertainty=uncertainty, uncertainty_type=uncertainty_type,
        method=method, conditions=effective_conditions, replicate_index=replicate_index,
        measured_at=timestamp, quality=decision.quality, quality_reasons=list(decision.reasons),
        admissibility_codes=list(decision.codes), scientific_origin="experimental",
        measurement_checksum=checksum({
            "contract": "measurement-v2", "run": run.id, "sample": run.sample_id,
            "property": property_definition.key, "value": numeric_value, "unit": unit,
            "uncertainty": uncertainty, "replicate": replicate_index, "conditions": effective_conditions,
            "measured_at": timestamp.isoformat(), "admissibility": list(decision.codes),
        }),
        notes=notes,
    )
    if row_id:
        measurement.id = row_id
    db.add(measurement)
    db.flush()
    return measurement


def invalidate_run_measurements(db: Session, run: ExperimentRun) -> None:
    """Preserve rows but remove every measurement from the governing accepted evidence set."""
    for measurement in db.query(Measurement).filter(Measurement.run_id == run.id).all():
        measurement.quality = MeasurementQuality.INVALIDATED_SOURCE
        codes = list(measurement.admissibility_codes or [])
        if "RUN_INVALIDATED" not in codes:
            codes.append("RUN_INVALIDATED")
        measurement.admissibility_codes = codes
        reasons = list(measurement.quality_reasons or [])
        if "The source run was invalidated; this measurement is retained for provenance but excluded from governing evidence." not in reasons:
            reasons.append(
                "The source run was invalidated; this measurement is retained for provenance but excluded from governing evidence."
            )
        measurement.quality_reasons = reasons


def accepted_measurements(
    db: Session, *, target_kind: str, target_id: str, property_definition_id: str, organisation_id: str
) -> list[Measurement]:
    query = (
        db.query(Measurement)
        .join(Sample, Sample.id == Measurement.sample_id)
        .join(ExperimentRun, ExperimentRun.id == Measurement.run_id)
        .filter(Measurement.organisation_id == organisation_id,
                Sample.organisation_id == organisation_id,
                ExperimentRun.organisation_id == organisation_id,
                ExperimentRun.status == ExperimentRunStatus.COMPLETED,
                Measurement.property_definition_id == property_definition_id,
                Measurement.quality == MeasurementQuality.ACCEPTED)
    )
    query = query.filter(
        Sample.material_id == target_id if target_kind == "known_material"
        else Sample.hypothesis_id == target_id
    )
    return query.order_by(Measurement.measured_at, Measurement.id).all()


# ---------------------------------------------------------------------------------------------
# Comparison across origins
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ComparableValue:
    origin: str
    value: float
    uncertainty: float | None
    unit: str
    source_id: str

    def interval(self) -> tuple[float, float]:
        spread = self.uncertainty or 0.0
        return self.value - spread, self.value + spread


def compare_values(first: ComparableValue, second: ComparableValue) -> dict[str, Any]:
    """Compare two values from different origins. Never averages them."""
    if first.unit != second.unit:
        return {
            "verdict": AgreementVerdict.INCOMPARABLE,
            "detail": f"Units differ ({first.unit} vs {second.unit}); values are not converted here "
                      "and are not compared.",
        }
    low_a, high_a = first.interval()
    low_b, high_b = second.interval()
    overlap = not (high_a < low_b or high_b < low_a)
    difference = abs(first.value - second.value)
    if overlap:
        verdict = AgreementVerdict.AGREES_WITHIN_UNCERTAINTY
        detail = (f"{first.origin} {first.value}±{first.uncertainty or 0} and {second.origin} "
                  f"{second.value}±{second.uncertainty or 0} {first.unit} overlap within their stated "
                  "uncertainties. They are not combined into one number.")
    else:
        verdict = AgreementVerdict.DISAGREES
        detail = (f"{first.origin} {first.value}±{first.uncertainty or 0} and {second.origin} "
                  f"{second.value}±{second.uncertainty or 0} {first.unit} do NOT overlap "
                  f"(difference {difference:.6g}). Both are retained; neither is discarded and no "
                  "average is taken.")
    return {
        "verdict": verdict, "detail": detail, "absolute_difference": difference,
        "unit": first.unit,
        "first": {"origin": first.origin, "value": first.value, "uncertainty": first.uncertainty,
                  "source_id": first.source_id},
        "second": {"origin": second.origin, "value": second.value, "uncertainty": second.uncertainty,
                   "source_id": second.source_id},
    }


def experimental_comparability(
    first: Measurement, second: Measurement, db: Session | None = None,
) -> dict[str, Any]:
    """Decide whether two experiments address the same scientific context before comparing values."""
    reasons: list[str] = []
    if first.property_definition_id != second.property_definition_id:
        return {"status": "not_comparable", "reasons": ["Measurements address different properties."]}
    if first.canonical_unit != second.canonical_unit:
        return {"status": "not_comparable", "reasons": ["Canonical units differ."]}

    if db is not None:
        sample_a = db.get(Sample, first.sample_id) if first.sample_id else None
        sample_b = db.get(Sample, second.sample_id) if second.sample_id else None
        if sample_a and sample_b:
            if sample_a.material_id != sample_b.material_id or sample_a.hypothesis_id != sample_b.hypothesis_id:
                return {"status": "not_comparable", "reasons": ["Samples trace to different material targets."]}
            if sample_a.material_state_id and sample_b.material_state_id:
                if sample_a.material_state_id != sample_b.material_state_id:
                    return {"status": "not_comparable", "reasons": ["Samples are recorded in different material states."]}
            elif sample_a.material_state_id != sample_b.material_state_id:
                return {"status": "insufficient_context", "reasons": ["Only one sample has a material state."]}

    conditions_a = first.conditions or {}
    conditions_b = second.conditions or {}
    keys = set(conditions_a) | set(conditions_b)
    for key in sorted(keys):
        in_a, in_b = key in conditions_a, key in conditions_b
        if in_a != in_b:
            reasons.append(f"Condition '{key}' is recorded for only one experiment.")
            continue
        if conditions_a[key] != conditions_b[key]:
            return {
                "status": "not_comparable",
                "reasons": [f"Condition '{key}' differs ({conditions_a[key]!r} vs {conditions_b[key]!r})."],
            }
    if reasons:
        return {"status": "insufficient_context", "reasons": reasons}
    return {"status": "comparable", "reasons": ["Property, target state and recorded conditions are comparable."]}


def detect_conflicting_experiments(
    measurements: list[Measurement], db: Session | None = None,
) -> list[dict[str, Any]]:
    """Report contradictions only after the experiments are scientifically comparable."""
    conflicts: list[dict[str, Any]] = []
    for index, first in enumerate(measurements):
        for second in measurements[index + 1:]:
            comparability = experimental_comparability(first, second, db)
            if comparability["status"] != "comparable":
                continue
            if first.canonical_value is None or second.canonical_value is None:
                continue
            low_a = first.canonical_value - (first.uncertainty or 0.0)
            high_a = first.canonical_value + (first.uncertainty or 0.0)
            low_b = second.canonical_value - (second.uncertainty or 0.0)
            high_b = second.canonical_value + (second.uncertainty or 0.0)
            if high_a < low_b or high_b < low_a:
                conflicts.append({
                    "measurement_ids": [first.id, second.id],
                    "values": [first.canonical_value, second.canonical_value],
                    "unit": first.canonical_unit,
                    "methods": [first.method, second.method],
                    "sample_ids": [first.sample_id, second.sample_id],
                    "comparability": comparability,
                    "detail": "Two comparable accepted measurements disagree beyond their stated uncertainties. "
                              "Both are retained with their methods, samples and conditions visible; "
                              "the later measurement does not automatically supersede the earlier.",
                })
    return conflicts


def evaluate_experimental_requirement(
    requirement: FunctionalRequirement, measurement: Measurement,
) -> dict[str, Any]:
    """Determine whether one accepted measurement supports the requirement, contradicts it, or is inconclusive."""
    base = {
        "requirement_id": requirement.id,
        "measurement_id": measurement.id,
        "requirement_kind": requirement.requirement_kind,
        "raw_value": measurement.numeric_value,
        "raw_unit": measurement.unit,
        "canonical_value": measurement.canonical_value,
        "canonical_unit": measurement.canonical_unit,
        "uncertainty": measurement.uncertainty,
    }
    if measurement.canonical_value is None or not measurement.canonical_unit or not requirement.target_unit:
        return {**base, "outcome": "EXPERIMENT_INCONCLUSIVE", "reason_code": "UNIT_DIMENSION_MISMATCH",
                "detail": "The measurement cannot be placed in the requirement's comparison unit."}

    spread = float(measurement.uncertainty or 0.0)
    source_low = float(measurement.canonical_value) - spread
    source_high = float(measurement.canonical_value) + spread
    try:
        low = convert(source_low, str(measurement.canonical_unit), str(requirement.target_unit))
        high = convert(source_high, str(measurement.canonical_unit), str(requirement.target_unit))
    except (UnitError, TypeError, ValueError):
        return {**base, "outcome": "EXPERIMENT_INCONCLUSIVE", "reason_code": "UNIT_DIMENSION_MISMATCH",
                "detail": "The experimental unit is incompatible with the requirement unit."}
    low, high = min(low, high), max(low, high)
    status, detail = _test_direction(requirement, low, high)
    if status == RequirementStatus.PASS:
        outcome, code = "EXPERIMENT_SUPPORTS_REQUIREMENT", "EXPERIMENT_SUPPORTS_REQUIREMENT"
    elif status == RequirementStatus.FAIL:
        outcome, code = "EXPERIMENT_CONTRADICTS_REQUIREMENT", "EXPERIMENT_CONTRADICTS_REQUIREMENT"
    else:
        outcome, code = "EXPERIMENT_INCONCLUSIVE", "EXPERIMENT_INCONCLUSIVE"
    return {
        **base, "normalized_interval": [low, high], "comparison_unit": requirement.target_unit,
        "requirement_status": status, "outcome": outcome, "reason_code": code, "detail": detail,
    }


def _target_run_state(
    db: Session, *, organisation_id: str, role_id: str, target_kind: str, target_id: str,
    candidate_id: str | None = None,
) -> tuple[bool, bool, bool]:
    """Return (has_plan_or_recommendation, has_pending_run, has_active_run) for this target/role."""
    run_query = (
        db.query(ExperimentRun)
        .join(Sample, Sample.id == ExperimentRun.sample_id)
        .filter(ExperimentRun.organisation_id == organisation_id, Sample.organisation_id == organisation_id)
    )
    run_query = run_query.filter(
        Sample.material_id == target_id if target_kind == "known_material" else Sample.hypothesis_id == target_id
    )
    statuses = {str(row.status) for row in run_query.all()}
    has_active = bool(statuses & {ExperimentRunStatus.RUNNING, ExperimentRunStatus.IN_PROGRESS})
    has_pending = bool(statuses & {ExperimentRunStatus.PLANNED, ExperimentRunStatus.READY})
    # Candidate-bound plans are authoritative. Legacy role-level plans are not assumed to belong to
    # this target unless a run/sample resolves that relationship.
    candidate_plan = bool(candidate_id and (
        db.query(ExperimentPlan)
        .filter(ExperimentPlan.organisation_id == organisation_id,
                ExperimentPlan.candidate_id == candidate_id, ExperimentPlan.role_id == role_id)
        .first() is not None
    ))
    has_plan = has_pending or has_active or candidate_plan or (
        db.query(ExperimentRecommendation)
        .filter(ExperimentRecommendation.organisation_id == organisation_id,
                ExperimentRecommendation.role_id == role_id,
                ExperimentRecommendation.target_scientific_id == target_id,
                ExperimentRecommendation.status == "open")
        .first() is not None
    )
    return has_plan, has_pending, has_active


# ---------------------------------------------------------------------------------------------
# Validation assessment
# ---------------------------------------------------------------------------------------------
def assess_validation(
    db: Session, *, organisation_id: str, role_id: str, target_kind: str, target_id: str,
    project_id: str | None = None, candidate_id: str | None = None, persist: bool = False,
) -> dict[str, Any]:
    """Assess experimental support requirement-by-requirement; evidence existence alone never means support."""
    from app.services.reasoning import reason_about_candidate

    reasoning = reason_about_candidate(
        db, organisation_id=organisation_id, role_id=role_id,
        target_kind=target_kind, target_id=target_id, project_id=project_id,
    )
    states_by_id: dict[str, Any] = {}
    comparisons: list[dict[str, Any]] = []
    agreements: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    all_conflicts: list[dict[str, Any]] = []
    requirement_outcomes: list[dict[str, Any]] = []
    experimentally_supported: list[str] = []
    experimentally_contradicted: list[str] = []
    inconclusive_requirements: list[str] = []
    outstanding: list[str] = []
    measurement_ids: list[str] = []
    snapshot_measurements: list[dict[str, Any]] = []

    for result in reasoning["requirement_results"]:
        requirement_id = result["requirement_id"]
        requirement = db.get(FunctionalRequirement, requirement_id)
        property_key = result.get("property_key")
        if not property_key or requirement is None:
            outstanding.append(requirement_id)
            requirement_outcomes.append({"requirement_id": requirement_id, "outcome": "EXPERIMENT_NOT_AVAILABLE",
                                         "reason_code": "PROPERTY_NOT_BOUND"})
            continue
        definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
        if definition is None:
            outstanding.append(requirement_id)
            requirement_outcomes.append({"requirement_id": requirement_id, "outcome": "EXPERIMENT_NOT_AVAILABLE",
                                         "reason_code": "PROPERTY_NOT_REGISTERED"})
            continue

        measurements = accepted_measurements(
            db, target_kind=target_kind, target_id=target_id,
            property_definition_id=definition.id, organisation_id=organisation_id,
        )
        conflicts = detect_conflicting_experiments(measurements, db=db)
        all_conflicts.extend(conflicts)
        measurement_ids.extend(m.id for m in measurements)

        experimental_results = [evaluate_experimental_requirement(requirement, m) for m in measurements]
        outcome_set = {item["outcome"] for item in experimental_results}
        if conflicts or ("EXPERIMENT_SUPPORTS_REQUIREMENT" in outcome_set and
                         "EXPERIMENT_CONTRADICTS_REQUIREMENT" in outcome_set):
            requirement_outcome = "EXPERIMENT_CONFLICTING"
            reason_code = "EXPERIMENT_CONFLICTING"
            outstanding.append(requirement_id)
            inconclusive_requirements.append(requirement_id)
        elif "EXPERIMENT_CONTRADICTS_REQUIREMENT" in outcome_set:
            requirement_outcome = "EXPERIMENT_CONTRADICTS_REQUIREMENT"
            reason_code = "EXPERIMENT_CONTRADICTS_REQUIREMENT"
            experimentally_contradicted.append(requirement_id)
        elif experimental_results and outcome_set == {"EXPERIMENT_SUPPORTS_REQUIREMENT"}:
            requirement_outcome = "EXPERIMENT_SUPPORTS_REQUIREMENT"
            reason_code = "EXPERIMENT_SUPPORTS_REQUIREMENT"
            experimentally_supported.append(requirement_id)
        elif experimental_results:
            requirement_outcome = "EXPERIMENT_INCONCLUSIVE"
            reason_code = "EXPERIMENT_INCONCLUSIVE"
            outstanding.append(requirement_id)
            inconclusive_requirements.append(requirement_id)
        else:
            requirement_outcome = "EXPERIMENT_NOT_AVAILABLE"
            reason_code = "EXPERIMENT_NOT_AVAILABLE"
            outstanding.append(requirement_id)

        requirement_outcomes.append({
            "requirement_id": requirement_id, "property_key": property_key,
            "requirement_kind": requirement.requirement_kind, "reasoning_status": result["status"],
            "outcome": requirement_outcome, "reason_code": reason_code,
            "measurement_outcomes": experimental_results,
            "conflicting_measurements": conflicts,
        })

        other_values = collect_origin_values(
            db, target_kind=target_kind, target_id=target_id,
            property_definition_id=definition.id, required_state=None, states_by_id=states_by_id,
            organisation_id=organisation_id,
        )
        experimental = [
            ComparableValue("experimental", float(m.canonical_value), m.uncertainty,
                            str(m.canonical_unit), m.id)
            for m in measurements if m.canonical_value is not None and m.canonical_unit
        ]
        comparable_others = [
            ComparableValue(v.origin, float(v.value), None, str(v.unit), v.source_id)
            for v in other_values
            if v.is_usable and v.value is not None and v.unit
            and v.origin in {"predicted", "simulated", "observed", "literature"}
        ]
        pairwise = [compare_values(measured, other) for measured in experimental for other in comparable_others]
        for comparison in pairwise:
            if comparison["verdict"] == AgreementVerdict.AGREES_WITHIN_UNCERTAINTY:
                agreements.append({"requirement_id": requirement_id, "property_key": property_key, **comparison})
            elif comparison["verdict"] == AgreementVerdict.DISAGREES:
                disagreements.append({"requirement_id": requirement_id, "property_key": property_key, **comparison})

        for measurement in measurements:
            run = db.get(ExperimentRun, measurement.run_id)
            instrument = db.get(Instrument, measurement.instrument_id) if measurement.instrument_id else None
            snapshot_measurements.append({
                "measurement_id": measurement.id, "measurement_checksum": measurement.measurement_checksum,
                "admissibility": measurement.quality, "admissibility_codes": list(measurement.admissibility_codes or []),
                "run_id": measurement.run_id, "run_status": run.status if run else None,
                "protocol_version_id": run.protocol_version_id if run else None,
                "protocol_checksum": run.protocol_checksum_at_run if run else None,
                "sample_id": measurement.sample_id, "instrument_id": measurement.instrument_id,
                "calibration_reference": instrument.calibration_reference if instrument else None,
                "calibration_due_date": str(instrument.calibration_due_date) if instrument and instrument.calibration_due_date else None,
            })

        comparisons.append({
            "requirement_id": requirement_id, "property_key": property_key,
            "requirement_status": result["status"], "experimental_outcome": requirement_outcome,
            "experimental_values": [
                {"measurement_id": m.id, "value": m.canonical_value, "unit": m.canonical_unit,
                 "raw_value": m.numeric_value, "raw_unit": m.unit, "uncertainty": m.uncertainty,
                 "method": m.method, "sample_id": m.sample_id, "conditions": m.conditions,
                 "admissibility": m.quality, "admissibility_codes": list(m.admissibility_codes or [])}
                for m in measurements
            ],
            "other_origin_values": [v.as_dict() for v in other_values],
            "pairwise_comparisons": pairwise, "conflicting_experiments": conflicts,
            "note": EXPERIMENT_SEPARATION_NOTE,
        })

    has_plan, has_pending_run, has_active_run = _target_run_state(
        db, organisation_id=organisation_id, role_id=role_id,
        target_kind=target_kind, target_id=target_id, candidate_id=candidate_id,
    )
    state, rationale = _validation_state(
        reasoning=reasoning, requirement_outcomes=requirement_outcomes,
        experimentally_supported=experimentally_supported,
        experimentally_contradicted=experimentally_contradicted,
        outstanding=outstanding, conflicts=all_conflicts,
        has_plan=has_plan, has_pending_run=has_pending_run, has_active_run=has_active_run,
    )

    evidence_snapshot = {
        "methodology_version": EXPERIMENT_ADMISSIBILITY_VERSION,
        "candidate_id": candidate_id, "project_id": project_id,
        "target": {"kind": target_kind, "id": target_id},
        "reasoning_checksum": reasoning["reasoning_checksum"],
        "measurements": sorted(snapshot_measurements, key=lambda item: item["measurement_id"]),
    }
    payload = {
        "role_id": role_id, "candidate_id": candidate_id, "target_kind": target_kind, "target_id": target_id,
        "validation_state": state, "rationale": rationale,
        "per_property_comparisons": comparisons,
        "agreements": agreements, "disagreements": disagreements,
        "conflicting_experiments": all_conflicts,
        "requirement_outcomes": requirement_outcomes,
        "experimentally_supported_requirements": experimentally_supported,
        "experimentally_contradicted_requirements": experimentally_contradicted,
        "inconclusive_requirements": inconclusive_requirements,
        "outstanding_requirements": sorted(set(outstanding)),
        "measurement_ids": sorted(set(measurement_ids)),
        "reasoning_checksum": reasoning["reasoning_checksum"],
        "policy_version": VALIDATION_POLICY_VERSION,
        "methodology_version": EXPERIMENT_ADMISSIBILITY_VERSION,
        "evidence_snapshot": evidence_snapshot,
        "separation_note": EXPERIMENT_SEPARATION_NOTE,
        "autonomy_note": NO_AUTONOMY_NOTE,
    }
    payload["assessment_checksum"] = checksum({
        "contract": VALIDATION_POLICY_VERSION, "methodology": EXPERIMENT_ADMISSIBILITY_VERSION,
        "role": role_id, "target": [target_kind, target_id], "state": state,
        "outcomes": requirement_outcomes, "measurements": sorted(set(measurement_ids)),
        "reasoning_checksum": reasoning["reasoning_checksum"],
    })

    if persist:
        row = ValidationAssessment(
            organisation_id=organisation_id, project_id=project_id, candidate_id=candidate_id, role_id=role_id,
            target_kind=target_kind, target_scientific_id=target_id, validation_state=state,
            per_property_comparisons=comparisons, agreements=agreements, disagreements=disagreements,
            conflicting_experiments=all_conflicts,
            experimentally_supported_requirements=experimentally_supported,
            outstanding_requirements=sorted(set(outstanding)), measurement_ids=sorted(set(measurement_ids)),
            requirement_outcomes=requirement_outcomes, evidence_snapshot=evidence_snapshot,
            rationale=rationale, policy_version=VALIDATION_POLICY_VERSION,
            methodology_version=EXPERIMENT_ADMISSIBILITY_VERSION,
            assessment_checksum=payload["assessment_checksum"],
        )
        db.add(row)
        db.flush()
        for old in (
            db.query(ValidationAssessment)
            .filter(ValidationAssessment.organisation_id == organisation_id,
                    ValidationAssessment.role_id == role_id,
                    ValidationAssessment.target_kind == target_kind,
                    ValidationAssessment.target_scientific_id == target_id,
                    ValidationAssessment.superseded_by_id.is_(None),
                    ValidationAssessment.id != row.id).all()
        ):
            old.superseded_by_id = row.id
        db.flush()
        payload["validation_assessment_id"] = row.id
    return payload


def _validation_state(
    *, reasoning: dict[str, Any], requirement_outcomes: list[dict[str, Any]] | None = None,
    experimentally_supported: list[str] | None = None, experimentally_contradicted: list[str] | None = None,
    outstanding: list[str] | None = None, conflicts: list[dict[str, Any]] | None = None,
    has_plan: bool = False, has_pending_run: bool = False, has_active_run: bool = False,
    disagreements: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Deterministic candidate validation state derived from requirement outcomes, never mere row presence.

    The defaults retain compatibility with Phase-9 callers that invoked this internal helper before
    requirement-level experimental outcomes existed. `disagreements` is accepted only as a legacy
    argument and cannot itself create an experimentally validated state.
    """
    requirement_outcomes = requirement_outcomes or []
    experimentally_supported = experimentally_supported or []
    experimentally_contradicted = experimentally_contradicted or []
    outstanding = outstanding or []
    conflicts = conflicts or []
    origins = reasoning.get("origin_breakdown") or {}
    has_simulation = bool(origins.get("simulated"))
    has_any_evidence = bool(origins)
    hard_contradictions = [
        item for item in requirement_outcomes
        if item.get("outcome") == "EXPERIMENT_CONTRADICTS_REQUIREMENT"
        and item.get("requirement_kind") == RequirementKind.HARD_CONSTRAINT
    ]
    any_experimental_conflict = conflicts or any(
        item.get("outcome") == "EXPERIMENT_CONFLICTING" for item in requirement_outcomes
    )

    if any_experimental_conflict:
        return ValidationState.CONFLICTING_EXPERIMENTS, (
            "Comparable accepted experiments disagree. Every measurement is retained and no automatic winner "
            "is selected, so the candidate remains in a conflicting-experiments state."
        )
    if hard_contradictions or experimentally_contradicted:
        return ValidationState.EXPERIMENTALLY_CONTRADICTED, (
            f"Physical experimental evidence contradicts {len(experimentally_contradicted)} requirement(s). "
            "A failed experimental requirement is never relabelled as support or averaged away."
        )
    if experimentally_supported and not outstanding:
        return ValidationState.EXPERIMENTALLY_SUPPORTED, (
            "Every experimentally gated property requirement on file is supported by accepted physical "
            "measurements. This is scientific support, not commercial qualification or approval."
        )
    if experimentally_supported:
        return ValidationState.PARTIALLY_VALIDATED, (
            f"{len(experimentally_supported)} requirement(s) are experimentally supported and "
            f"{len(set(outstanding))} remain unresolved or untested."
        )
    if has_active_run:
        return ValidationState.EXPERIMENT_IN_PROGRESS, (
            "A physical experiment for this candidate is currently running; measurements are provisional "
            "until the run reaches a valid completed state."
        )
    if has_pending_run or has_plan:
        return ValidationState.EXPERIMENT_PENDING, (
            "An experiment has been recommended or planned but no admissible completed measurement yet "
            "supports the candidate's requirements."
        )
    if has_simulation:
        return ValidationState.SIMULATION_SUPPORTED, (
            "Physics simulation supports at least one requirement and no admissible physical measurement "
            "exists. This is explicitly not experimental validation."
        )
    if has_any_evidence:
        return ValidationState.COMPUTATIONAL_ONLY, (
            "Only computational, literature or non-admissible experimental records exist for this candidate."
        )
    return ValidationState.COMPUTATIONAL_ONLY, "No evidence of any origin addresses this role's requirements."


# ---------------------------------------------------------------------------------------------
# Experiment recommendation
# ---------------------------------------------------------------------------------------------
# Declared, inspectable weights. This is NOT expected value of information: no EVSI/EVI mathematics
# is implemented, and calling it that would overstate the method.
PRIORITY_WEIGHTS: dict[str, float] = {
    "requirement_criticality": 0.35,
    "evidence_gap": 0.30,
    "requirement_hardness": 0.20,
    "uncertainty": 0.15,
}

_GAP_SEVERITY: dict[str, float] = {
    "unknown": 1.0,
    "insufficient_evidence": 0.8,
    "state_mismatch": 0.7,
    "conflicting_evidence": 0.9,
}


def replacement_decision(
    db: Session, *, organisation_id: str, role_id: str, candidate_id: str,
    target_kind: str, target_id: str, project_id: str, persist_validation: bool = False,
) -> dict[str, Any]:
    """Return a transparent next-gate decision, never a commercial approval.

    The decision composes scientific/experimental validation with the latest industrial assessment.
    It deliberately exposes blockers and unresolved evidence instead of collapsing them into an
    opaque score. `READY_FOR_NEXT_GATE` means the candidate may proceed to the next product gate;
    it is not an authorization for commercial replacement.
    """
    validation = assess_validation(
        db, organisation_id=organisation_id, role_id=role_id, target_kind=target_kind,
        target_id=target_id, project_id=project_id, candidate_id=candidate_id,
        persist=persist_validation,
    )
    latest_industrial = (
        db.query(IndustrialViabilityAssessment)
        .filter(
            IndustrialViabilityAssessment.organisation_id == organisation_id,
            IndustrialViabilityAssessment.project_id == project_id,
            IndustrialViabilityAssessment.candidate_id == candidate_id,
            IndustrialViabilityAssessment.superseded_by_id.is_(None),
        )
        .order_by(IndustrialViabilityAssessment.created_at.desc())
        .first()
    )

    outcomes = list(validation.get("requirement_outcomes") or [])
    blocking_requirements: list[dict[str, Any]] = []
    unresolved_requirements: list[dict[str, Any]] = []
    for item in outcomes:
        kind = str(item.get("requirement_kind") or "")
        outcome = str(item.get("outcome") or "")
        reasoning_status = str(item.get("reasoning_status") or "")
        if kind == RequirementKind.HARD_CONSTRAINT and (
            outcome == "EXPERIMENT_CONTRADICTS_REQUIREMENT" or reasoning_status == RequirementStatus.FAIL
        ):
            blocking_requirements.append({
                "requirement_id": item.get("requirement_id"),
                "property_key": item.get("property_key"),
                "reason_code": (
                    "EXPERIMENT_CONTRADICTS_REQUIREMENT"
                    if outcome == "EXPERIMENT_CONTRADICTS_REQUIREMENT"
                    else "HARD_SCIENTIFIC_REQUIREMENT_FAILED"
                ),
            })
        elif kind == RequirementKind.HARD_CONSTRAINT and (
            outcome in {"EXPERIMENT_CONFLICTING", "EXPERIMENT_INCONCLUSIVE"}
            or reasoning_status in {
                RequirementStatus.UNKNOWN, RequirementStatus.INSUFFICIENT_EVIDENCE,
                RequirementStatus.CONFLICTING_EVIDENCE, RequirementStatus.STATE_MISMATCH,
            }
        ):
            unresolved_requirements.append({
                "requirement_id": item.get("requirement_id"),
                "property_key": item.get("property_key"),
                "reason_code": outcome or f"SCIENTIFIC_{reasoning_status.upper()}",
            })

    conflicting_evidence = list(validation.get("conflicting_experiments") or [])
    industrial_state = latest_industrial.overall_state if latest_industrial else "not_assessed"
    industrial_conflicts = list(latest_industrial.conflicting_evidence or []) if latest_industrial else []
    conflicting_evidence.extend({"origin": "industrial", **c} for c in industrial_conflicts)

    reason_codes: list[str] = []
    if blocking_requirements:
        reason_codes.append("BLOCKING_SCIENTIFIC_REQUIREMENT")
    if latest_industrial and latest_industrial.overall_state == "fail":
        reason_codes.append("INDUSTRIAL_HARD_CONSTRAINT_FAILED")
    if conflicting_evidence:
        reason_codes.append("CONFLICTING_EVIDENCE")
    if unresolved_requirements:
        reason_codes.append("UNRESOLVED_HARD_REQUIREMENTS")
    if latest_industrial is None:
        reason_codes.append("INDUSTRIAL_ASSESSMENT_MISSING")
    elif latest_industrial.overall_state in {"unknown", "insufficient_evidence", "partial"}:
        reason_codes.append("INDUSTRIAL_ASSESSMENT_INCOMPLETE")

    if blocking_requirements or (latest_industrial and latest_industrial.overall_state == "fail"):
        decision = "REJECTED"
    elif conflicting_evidence:
        decision = "INCONCLUSIVE"
    elif unresolved_requirements or latest_industrial is None or latest_industrial.overall_state != "pass":
        decision = "NOT_READY"
    else:
        decision = "READY_FOR_NEXT_GATE"

    return {
        "candidate_id": candidate_id,
        "project_id": project_id,
        "role_id": role_id,
        "target_kind": target_kind,
        "target_id": target_id,
        "scientific_requirements": {
            "validation_state": validation["validation_state"],
            "requirement_outcomes": outcomes,
            "reasoning_checksum": validation.get("evidence_snapshot", {}).get("reasoning_checksum"),
        },
        "simulation_status": (
            "supported" if validation["validation_state"] == ValidationState.SIMULATION_SUPPORTED else "not_decisive"
        ),
        "industrial_status": industrial_state,
        "industrial_assessment_id": latest_industrial.id if latest_industrial else None,
        "experimental_status": validation["validation_state"],
        "blocking_requirements": blocking_requirements,
        "unresolved_requirements": unresolved_requirements,
        "conflicting_evidence": conflicting_evidence,
        "decision": decision,
        "reason_codes": sorted(set(reason_codes)),
        "methodology_version": "replacement-next-gate-v1",
        "qualification_note": (
            "This is a transparent next-gate decision, not commercial qualification, certification, "
            "regulatory approval, or authorization to replace the incumbent material in production."
        ),
        "validation": validation,
    }


def recommend_experiments(
    db: Session, *, organisation_id: str, role_id: str, target_kind: str, target_id: str,
    project_id: str | None = None, persist: bool = False,
) -> dict[str, Any]:
    """Turn unresolved requirements into prioritized, explained experiment recommendations."""
    from app.services.reasoning import reason_about_candidate

    reasoning = reason_about_candidate(
        db, organisation_id=organisation_id, role_id=role_id, target_kind=target_kind,
        target_id=target_id, project_id=project_id,
    )
    recommendations: list[dict[str, Any]] = []

    for gap in reasoning["evidence_gaps"]:
        result = next(
            r for r in reasoning["requirement_results"] if r["requirement_id"] == gap["requirement_id"]
        )
        criticality = float(gap.get("criticality") or 1) / 5.0
        gap_severity = _GAP_SEVERITY.get(str(gap["status"]), 0.5)
        hardness = 1.0 if gap["requirement_kind"] == "hard_constraint" else (
            0.6 if gap["requirement_kind"] == "soft_constraint" else 0.3
        )
        # Uncertainty contribution is 0 when nothing is known: an absent value carries no measured
        # spread, and inventing one would fabricate precision.
        uncertainty_factor = 1.0 if gap["status"] == "conflicting_evidence" else 0.0

        factors = {
            "requirement_criticality": round(criticality, 4),
            "evidence_gap": round(gap_severity, 4),
            "requirement_hardness": round(hardness, 4),
            "uncertainty": round(uncertainty_factor, 4),
        }
        score = round(sum(PRIORITY_WEIGHTS[k] * v for k, v in factors.items()), 6)

        definition = (
            db.query(MaterialPropertyDefinition).filter_by(key=gap["property_key"]).one_or_none()
            if gap.get("property_key") else None
        )
        protocol = None
        if definition is not None:
            protocol = (
                db.query(ExperimentProtocol)
                .filter(ExperimentProtocol.organisation_id == organisation_id,
                        ExperimentProtocol.property_definition_id == definition.id,
                        ExperimentProtocol.status == "active")
                .order_by(ExperimentProtocol.key).first()
            )

        recommendation = {
            "requirement_id": gap["requirement_id"],
            "requirement_display_name": gap["display_name"],
            "property_key": gap.get("property_key"),
            "property_definition_id": definition.id if definition else None,
            "unresolved_status": gap["status"],
            "why_it_matters": (
                f"'{gap['display_name']}' is a {gap['requirement_kind'].replace('_', ' ')} of the "
                f"function '{gap['function_key']}' (criticality {gap.get('criticality')}). "
                f"{gap['detail']}"
            ),
            "current_evidence_summary": {
                "origin_counts": result.get("origin_counts") or {},
                "values_on_file": len(result.get("values") or []),
                "status": gap["status"],
            },
            "expected_evidence_type": "experimental",
            "proposed_measurement": gap["what_would_resolve_it"],
            "suggested_protocol_id": protocol.id if protocol else None,
            "suggested_protocol_key": protocol.key if protocol else None,
            "priority_score": score,
            "priority_factors": factors,
            "priority_weights": dict(PRIORITY_WEIGHTS),
            "priority_methodology": RECOMMENDATION_METHODOLOGY,
            "priority_note": (
                "Priority is an explainable weighted combination of declared factors. It is "
                "deliberately not called expected value of information: no EVSI or EVI mathematics "
                "is implemented here."
            ),
        }
        recommendation["recommendation_checksum"] = checksum({
            "contract": RECOMMENDATION_METHODOLOGY, "requirement": gap["requirement_id"],
            "target": [target_kind, target_id], "status": gap["status"], "factors": factors,
        })
        recommendations.append(recommendation)

    recommendations.sort(key=lambda r: (-r["priority_score"], str(r["requirement_id"])))

    if persist:
        for recommendation in recommendations:
            existing = (
                db.query(ExperimentRecommendation)
                .filter_by(role_id=role_id, target_scientific_id=target_id,
                           requirement_id=recommendation["requirement_id"], status="open").one_or_none()
            )
            if existing:
                continue
            db.add(ExperimentRecommendation(
                organisation_id=organisation_id, project_id=project_id, role_id=role_id,
                requirement_id=recommendation["requirement_id"], target_kind=target_kind,
                target_scientific_id=target_id,
                property_definition_id=recommendation["property_definition_id"],
                unresolved_status=recommendation["unresolved_status"],
                why_it_matters=recommendation["why_it_matters"],
                current_evidence_summary=recommendation["current_evidence_summary"],
                expected_evidence_type="experimental",
                proposed_measurement=recommendation["proposed_measurement"],
                suggested_protocol_id=recommendation["suggested_protocol_id"],
                priority_score=recommendation["priority_score"],
                priority_factors=recommendation["priority_factors"],
                priority_methodology=RECOMMENDATION_METHODOLOGY,
                recommendation_checksum=recommendation["recommendation_checksum"],
            ))
        db.flush()

    return {
        "role_id": role_id, "target_kind": target_kind, "target_id": target_id,
        "recommendations": recommendations,
        "methodology": RECOMMENDATION_METHODOLOGY,
        "weights": dict(PRIORITY_WEIGHTS),
        "autonomy_note": NO_AUTONOMY_NOTE,
    }
