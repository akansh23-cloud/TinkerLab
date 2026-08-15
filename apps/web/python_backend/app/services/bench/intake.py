"""Phase 12 — one-shot material intake.

The API already exposed everything needed to author a material: POST /materials, then identifiers,
then composition, then process state, then evidence, then one observation per property. Six round
trips and an evidence record the user had to construct first. No frontend ever exposed it, so in
practice materials could only arrive through CSV import, and the Materials Explorer was a read-only
window onto seed data.

This service collapses that into a single transactional call shaped like the thing a user actually
has in front of them: a datasheet. Identity, composition, process state and a block of properties,
recorded together, with one evidence record per data grade.

THE DATA GRADE IS THE POINT. Each intake declares where its numbers came from, and that declaration
sets the evidence type, the source quality and the confidence ceiling. A user cannot mark a
handbook figure as an accredited measurement, because the mapping is a closed table here rather
than a free-text field on the request. Everything downstream — selection, conflict detection,
eligibility, the dossier — already reads those fields correctly. This layer simply refuses to lie
to them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import (
    Evidence,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialProcessState,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    ObservationConditionSet,
)
from app.services.bench.catalog import CATALOGUE_BY_KEY, plausibility
from app.services.identity import normalize_identifier
from app.services.units import UnitError, validate_property_unit


class IntakeError(ValueError):
    """Raised for a request the caller can fix. Routed to HTTP 422 with the message intact."""


@dataclass(frozen=True)
class DataGrade:
    key: str
    display_name: str
    evidence_type: str
    source_quality: str
    confidence: float
    evidence_status: str
    description: str
    requires_reference: bool = False


# The closed set of provenance grades. Ordered from strongest to weakest.
#
# `confidence` is a ceiling, not a suggestion: the intake service writes exactly this value and
# ignores any confidence supplied by the caller. Provenance strength is a property of where the
# number came from, and letting a request assert its own confidence would make the whole evidence
# hierarchy decorative.
DATA_GRADES: tuple[DataGrade, ...] = (
    DataGrade(
        key="accredited_laboratory", display_name="Accredited laboratory test report",
        evidence_type="experimental", source_quality="accredited_laboratory", confidence=0.95,
        evidence_status="reviewed", requires_reference=True,
        description="ISO/IEC 17025 accredited test report. The only grade admissible as qualification evidence.",
    ),
    DataGrade(
        key="internal_measurement", display_name="Internal test measurement",
        evidence_type="experimental", source_quality="internal_measurement", confidence=0.85,
        evidence_status="reported",
        description="Measured on your own equipment. Record the instrument and method so it can be defended later.",
    ),
    DataGrade(
        key="supplier_datasheet", display_name="Supplier datasheet",
        evidence_type="supplier", source_quality="supplier_declared", confidence=0.70,
        evidence_status="reported", requires_reference=True,
        description="Declared by the supplier. Typical values, usually dry-as-moulded and flow-direction, rarely guaranteed minima.",
    ),
    DataGrade(
        key="published_literature", display_name="Published literature",
        evidence_type="literature", source_quality="peer_reviewed", confidence=0.65,
        evidence_status="reported", requires_reference=True,
        description="Peer-reviewed publication or standards body data. Cite it.",
    ),
    DataGrade(
        key="handbook_typical", display_name="Handbook / reference typical",
        evidence_type="literature", source_quality="handbook_typical", confidence=0.55,
        evidence_status="reported",
        description="Representative of the material class rather than of any specific grade. Fine for screening, never for qualification.",
    ),
    DataGrade(
        key="engineering_estimate", display_name="Engineering estimate",
        evidence_type="user_provided", source_quality="engineering_estimate", confidence=0.30,
        evidence_status="reported",
        description="A judged value. Recorded honestly as a judgement so nothing downstream mistakes it for a measurement.",
    ),
)

GRADES_BY_KEY: dict[str, DataGrade] = {g.key: g for g in DATA_GRADES}


def ensure_property_definition(db: Session, key: str) -> MaterialPropertyDefinition:
    """Fetch a property definition, creating it from the catalogue when absent.

    Auto-creation matters for deployment: a database migrated before Phase 12 has none of the new
    engineering properties, and requiring a re-seed before a user can record a flexural modulus
    would reproduce exactly the cold-start dead end this phase exists to remove. Only catalogue
    keys are created — an unrecognised key is an error, not an invitation to invent a property.
    """
    existing = db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none()
    if existing is not None:
        return existing
    spec = CATALOGUE_BY_KEY.get(key)
    if spec is None:
        raise IntakeError(
            f"Unknown property '{key}'. Use a key from the property catalogue, or register a "
            "property definition explicitly before recording observations against it."
        )
    definition = MaterialPropertyDefinition(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"tinkerlab:prop:{key}")),
        key=spec.key,
        display_name=spec.display_name,
        quantity_type=spec.quantity_type,
        canonical_unit=spec.canonical_unit,
        description=spec.why_it_matters,
        applicable_material_families=["polymer", "alloy", "composite", "ceramic", "coating", "adhesive",
                                      "crystalline_inorganic", "unknown"],
        allowed_comparators=["boolean"] if spec.quantity_type == "boolean" else ["<", "<=", "=", ">=", ">", "between"],
        allow_negative=spec.allow_negative,
        conflict_policy=spec.conflict_policy,
        conflict_absolute_tolerance=spec.conflict_absolute_tolerance,
        conflict_relative_tolerance=spec.conflict_relative_tolerance,
    )
    db.add(definition)
    db.flush()
    return definition


def _canonical_name(display_name: str, supplier: str | None, grade: str | None) -> str:
    parts = [p.strip().lower().replace(" ", "-") for p in (supplier, display_name, grade) if p and p.strip()]
    return "::".join(parts) or display_name.strip().lower().replace(" ", "-")


def create_evidence(
    db: Session,
    *,
    grade: DataGrade,
    title: str,
    source_reference: str | None,
    method: str | None,
    organisation_id: str | None,
    visibility: str,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Evidence:
    evidence = Evidence(
        evidence_type=grade.evidence_type,
        title=title[:300],
        source_reference=source_reference,
        description=grade.description,
        method=method,
        confidence=grade.confidence,
        metadata_json={"data_grade": grade.key, **(metadata or {})},
        organisation_id=organisation_id,
        visibility=visibility,
        status=grade.evidence_status,
        curator_note=note,
        source_quality=grade.source_quality,
    )
    db.add(evidence)
    db.flush()
    return evidence


@dataclass
class PropertyEntry:
    property_key: str
    value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    temperature_value: float | None = None
    temperature_unit: str | None = None
    method: str | None = None
    note: str | None = None
    uncertainty: float | None = None


def record_observations(
    db: Session,
    *,
    material: Material,
    entries: list[PropertyEntry],
    evidence: Evidence,
    grade: DataGrade,
) -> tuple[list[MaterialPropertyObservation], list[dict[str, Any]]]:
    """Write one observation per entry. Returns (observations, advisory warnings).

    Unit dimension is enforced. Range plausibility is advisory and never blocks: a genuinely novel
    material is precisely the case where a handbook range should be wrong, and refusing the number
    would make the tool useless to the person who actually measured it.
    """
    observations: list[MaterialPropertyObservation] = []
    warnings: list[dict[str, Any]] = []

    for entry in entries:
        definition = ensure_property_definition(db, entry.property_key)
        is_boolean = definition.quantity_type == "boolean"

        if is_boolean:
            if entry.boolean_value is None:
                raise IntakeError(f"Property '{entry.property_key}' is a boolean and needs a true/false value.")
            value_type, numeric_value, boolean_value, unit = "boolean", None, bool(entry.boolean_value), None
        else:
            if entry.value is None:
                raise IntakeError(f"Property '{entry.property_key}' is numeric and needs a value.")
            unit = entry.unit or definition.canonical_unit or ""
            if not unit:
                raise IntakeError(f"Property '{entry.property_key}' needs a unit.")
            try:
                validate_property_unit(entry.property_key, unit, definition.canonical_unit or unit)
            except UnitError as exc:
                raise IntakeError(str(exc)) from exc
            if not definition.allow_negative and entry.value < 0:
                raise IntakeError(f"Negative values are not allowed for '{entry.property_key}'.")
            value_type, numeric_value, boolean_value = "numeric", float(entry.value), None

            flag = plausibility(entry.property_key, float(entry.value), material.material_family)
            if flag is not None:
                warnings.append(flag)

        condition_set = None
        if entry.temperature_value is not None:
            condition_set = ObservationConditionSet(
                temperature_value=entry.temperature_value,
                temperature_unit=entry.temperature_unit or "degC",
                metadata_json={"source": "bench_intake"},
            )
            db.add(condition_set)
            db.flush()

        spec = CATALOGUE_BY_KEY.get(entry.property_key)
        observation = MaterialPropertyObservation(
            material_id=material.id,
            property_definition_id=definition.id,
            value_type=value_type,
            numeric_value=numeric_value,
            boolean_value=boolean_value,
            unit=unit if not is_boolean else None,
            evidence_id=evidence.id,
            conditions={},
            condition_set_id=condition_set.id if condition_set else None,
            method=entry.method or (spec.test_standard if spec else None),
            uncertainty=entry.uncertainty,
            uncertainty_type="absolute" if entry.uncertainty is not None else None,
            confidence=grade.confidence,
            curator_note=entry.note,
            status="active",
        )
        db.add(observation)
        observations.append(observation)

    db.flush()
    return observations, warnings


@dataclass
class IntakeResult:
    material: Material
    observation_count: int
    warnings: list[dict[str, Any]]
    evidence_id: str


def intake_material(
    db: Session,
    *,
    display_name: str,
    material_family: str,
    data_grade: str,
    description: str | None = None,
    supplier: str | None = None,
    grade_code: str | None = None,
    canonical_name: str | None = None,
    identifiers: list[dict[str, str]] | None = None,
    components: list[dict[str, Any]] | None = None,
    process_state: dict[str, Any] | None = None,
    properties: list[PropertyEntry] | None = None,
    source_reference: str | None = None,
    method: str | None = None,
    note: str | None = None,
    organisation_id: str | None = None,
    visibility: str = "public",
    is_seed_data: bool = False,
    material_id: str | None = None,
) -> IntakeResult:
    grade = GRADES_BY_KEY.get(data_grade)
    if grade is None:
        raise IntakeError(
            f"Unknown data grade '{data_grade}'. Expected one of: {', '.join(g.key for g in DATA_GRADES)}."
        )
    if grade.requires_reference and not (source_reference or "").strip():
        raise IntakeError(
            f"The '{grade.display_name}' grade requires a source reference — a report number, "
            "datasheet revision or citation. Without it the provenance claim is not checkable."
        )
    if visibility == "private" and organisation_id is None:
        raise IntakeError("A private material must be owned by an organisation.")

    resolved_canonical = (canonical_name or _canonical_name(display_name, supplier, grade_code)).strip()
    if not resolved_canonical:
        raise IntakeError("A canonical name could not be derived. Provide one explicitly.")

    material = Material(
        id=material_id or str(uuid.uuid4()),
        canonical_name=resolved_canonical,
        display_name=display_name.strip(),
        material_family=material_family,
        description=description,
        composition_summary=_composition_summary(components or []),
        source_type="user_provided" if not is_seed_data else "reference_library",
        is_seed_data=is_seed_data,
        owner_organisation_id=organisation_id,
        visibility=visibility,
    )
    db.add(material)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise IntakeError(
            f"A material with canonical name '{resolved_canonical}' already exists. "
            "Add a supplier or grade code to distinguish it, or record the new data against the existing material."
        ) from exc

    evidence_title = f"{display_name} — {grade.display_name}"
    evidence = create_evidence(
        db, grade=grade, title=evidence_title, source_reference=source_reference, method=method,
        organisation_id=organisation_id, visibility=visibility, note=note,
        metadata={"supplier": supplier, "grade_code": grade_code, "intake": "bench_v1"},
    )

    for spec in identifiers or []:
        namespace = str(spec.get("namespace", "")).strip()
        value = str(spec.get("value", "")).strip()
        if not namespace or not value:
            continue
        db.add(MaterialIdentifier(
            material_id=material.id, namespace=namespace, value=value,
            normalized_value=normalize_identifier(namespace, value),
            is_primary=bool(spec.get("is_primary", False)),
            evidence_id=evidence.id, organisation_id=organisation_id, visibility=visibility,
        ))

    for index, comp in enumerate(components or []):
        name = str(comp.get("component_name", "")).strip()
        if not name:
            continue
        db.add(MaterialComponent(
            material_id=material.id, component_name=name,
            component_identifier=comp.get("component_identifier"),
            component_role=comp.get("component_role"),
            amount_value=comp.get("amount_value"),
            amount_lower=comp.get("amount_lower"),
            amount_upper=comp.get("amount_upper"),
            amount_unit=comp.get("amount_unit") or "%",
            amount_basis=comp.get("amount_basis") or "weight_percent",
            evidence_id=evidence.id,
            is_redacted=bool(comp.get("is_redacted", False)),
            redaction_label=comp.get("redaction_label"),
            sequence=index, notes=comp.get("notes"),
        ))

    if process_state:
        label = str(process_state.get("state_label", "")).strip()
        if label:
            db.add(MaterialProcessState(
                material_id=material.id, state_label=label,
                process_name=process_state.get("process_name"), sequence=0,
                parameters=process_state.get("parameters") or {},
                evidence_id=evidence.id, notes=process_state.get("notes"),
            ))

    observations, warnings = record_observations(
        db, material=material, entries=properties or [], evidence=evidence, grade=grade,
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise IntakeError(f"Material could not be saved: {exc.orig}") from exc

    db.refresh(material)
    return IntakeResult(
        material=material, observation_count=len(observations), warnings=warnings, evidence_id=evidence.id,
    )


def add_property_data(
    db: Session,
    *,
    material: Material,
    data_grade: str,
    properties: list[PropertyEntry],
    source_reference: str | None = None,
    method: str | None = None,
    note: str | None = None,
    organisation_id: str | None = None,
) -> tuple[int, list[dict[str, Any]], str]:
    """Attach a further block of properties to an existing material under a new evidence record.

    A separate evidence record per submission is deliberate. When a supplier datasheet says 180 MPa
    and your own tensile rig says 164 MPa, the system should hold both and surface the conflict —
    the existing conflict detector already does exactly that. Overwriting the first value would
    destroy the most decision-relevant fact in the whole record.
    """
    grade = GRADES_BY_KEY.get(data_grade)
    if grade is None:
        raise IntakeError(f"Unknown data grade '{data_grade}'.")
    if grade.requires_reference and not (source_reference or "").strip():
        raise IntakeError(f"The '{grade.display_name}' grade requires a source reference.")
    if not properties:
        raise IntakeError("No property values were supplied.")

    evidence = create_evidence(
        db, grade=grade, title=f"{material.display_name} — {grade.display_name}",
        source_reference=source_reference, method=method,
        organisation_id=organisation_id or material.owner_organisation_id,
        visibility=material.visibility, note=note, metadata={"intake": "bench_v1_append"},
    )
    observations, warnings = record_observations(
        db, material=material, entries=properties, evidence=evidence, grade=grade,
    )
    db.commit()
    return len(observations), warnings, evidence.id


def _composition_summary(components: list[dict[str, Any]]) -> str | None:
    parts = []
    for comp in components:
        name = str(comp.get("component_name", "")).strip()
        if not name:
            continue
        amount = comp.get("amount_value")
        unit = comp.get("amount_unit") or "%"
        parts.append(f"{name} {amount:g}{unit}" if isinstance(amount, (int, float)) else name)
    return "; ".join(parts) if parts else None
