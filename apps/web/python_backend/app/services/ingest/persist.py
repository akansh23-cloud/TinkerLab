"""Phase 11 — Persisting external records into the TinkerLab evidence chain.

The rule this module enforces: **nothing reaches `MaterialPropertyObservation` without a
`SourceRecord`, an `Evidence` row, a `DatasetSnapshot` and — for computed values — a
`ComputationalMethod`.** Bulk-loading straight into observations would be faster and would destroy
the only thing that makes the platform worth anything.

Two behaviours worth calling out.

**Computed values get a 0 K state, not an ambient one.** A Materials Project band gap describes a
static lattice at absolute zero. Recording it as though it were measured at room temperature would
defeat Phase 8's state matching, which is the mechanism that catches exactly this error.

**Applicability warnings ride with the evidence.** A PBE band gap is stored with a high-severity
warning attached, so the decision layer can refuse to treat it as governing evidence for a band-gap
requirement while still using it for screening.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import (
    ComputationalMethod,
    DatasetSnapshot,
    Evidence,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialState,
    SourceProvider,
    SourceRecord,
)
from app.services.identity import normalize_identifier, normalize_material_name, resolve_identity
from app.services.ingest.composition import identity_composition, state_composition
from app.services.ingest.base import checksum
from app.services.ingest.methods import (
    applicability_warnings,
    ensure_methods,
    method_for_observation,
    method_for_provider_record,
)
from app.services.units import UnitError, validate_property_unit

PERSIST_VERSION = "phase11-persist/1.0"


class PersistError(RuntimeError):
    """Raised when a normalized record cannot be safely persisted."""


def _canonical_name(display_name: str, provider_key: str, external_id: str) -> str:
    base = normalize_material_name(display_name) or "external-material"
    provider = normalize_material_name(provider_key) or "external"
    suffix = "".join(ch if ch.isalnum() else "-" for ch in str(external_id)).strip("-")[:40]
    return f"{base}-{provider}-{suffix}" if suffix else f"{base}-{provider}"


def _resolve_property_definition(
    db: Session, property_key: str
) -> MaterialPropertyDefinition | None:
    return db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()


def persist_record(
    db: Session, *, provider: SourceProvider, snapshot: DatasetSnapshot,
    normalized: dict[str, Any], organisation_id: str, visibility: str = "private",
    requirement_temperature_k: float | None = None,
) -> dict[str, Any]:
    """Persist one normalized record, returning a summary of what was written."""
    external_id = str(normalized.get("_external_id") or normalized.get("external_id") or "")
    if not external_id:
        raise PersistError("Normalized record carries no external identifier")

    raw_checksum = str(normalized.get("_raw_checksum") or checksum(normalized))
    normalized_checksum = checksum(
        {k: v for k, v in sorted(normalized.items()) if not k.startswith("_")}
    )

    # Idempotency: the same provider record at the same upstream checksum is never written twice.
    existing = (
        db.query(SourceRecord)
        .filter_by(provider_id=provider.id, external_record_id=external_id,
                   organisation_id=organisation_id, raw_checksum=raw_checksum)
        .one_or_none()
    )
    if existing is not None:
        return {"external_id": external_id, "status": "already_ingested",
                "source_record_id": existing.id, "observations": 0, "industrial_evidence": 0}

    source_record = SourceRecord(
        provider_id=provider.id, organisation_id=organisation_id, visibility=visibility,
        external_record_id=external_id, source_version=snapshot.provider_version,
        dataset_snapshot_id=snapshot.id, parser_version=PERSIST_VERSION,
        raw_checksum=raw_checksum, normalized_checksum=normalized_checksum,
        raw_payload=normalized.get("_raw_record") or {
            k: v for k, v in normalized.items() if not k.startswith("_")
        },
        status="normalized",
        metadata_json={"connector": provider.key, "dataset_key": snapshot.dataset_key},
    )
    db.add(source_record)
    db.flush()

    methods = ensure_methods(db)
    method_key = method_for_provider_record(provider.key, normalized)
    method: ComputationalMethod = methods[method_key]

    material, identity = _upsert_material(
        db, normalized, external_id, organisation_id, visibility, provider.key
    )
    _upsert_identifiers(db, material, normalized, organisation_id, visibility)
    source_record.metadata_json = {
        **(source_record.metadata_json or {}),
        "identity_resolution": identity,
        "resolved_material_id": material.id,
    }

    state = _ensure_computed_state(db, material, normalized, method, organisation_id)

    computational = method.method_family in {"dft", "machine_learning"}
    evidence_type = {
        "reference_data": "external_reference",
        "regulatory_reference": "external_regulatory",
        "structure_reference": "external_structure",
    }.get(method.method_family, "external_computational" if computational else "external_ingest")
    source_quality = {
        "reference_data": "reference_database",
        "regulatory_reference": "regulatory_authority",
        "structure_reference": "structural_database",
    }.get(method.method_family, "computed_database" if computational else "external_database")

    evidence = Evidence(
        evidence_type=evidence_type,
        title=f"{provider.display_name}: {normalized.get('display_name') or external_id}",
        source_reference=f"{provider.key}:{external_id}",
        description=(
            f"Ingested from {provider.display_name} under {provider.license_identifier}. "
            f"{provider.attribution_text or ''}".strip()
        ),
        method=method.display_name,
        provider_id=provider.id, source_record_id=source_record.id,
        organisation_id=organisation_id, visibility=visibility,
        status="reported", evidence_date=datetime.now(UTC),
        computational_method_id=method.id if computational else None,
        dataset_snapshot_id=snapshot.id,
        source_quality=source_quality,
        metadata_json={
            "license_identifier": provider.license_identifier,
            "attribution_required": provider.attribution_required,
            "attribution_text": provider.attribution_text,
            "commercial_use_permitted": provider.commercial_use_permitted,
            "redistribution_permitted": provider.redistribution_permitted,
            "is_theoretical": normalized.get("is_theoretical", False),
            "snapshot_reproducible": snapshot.is_reproducible,
            "method_key": method.key,
            "method_family": method.method_family,
            "calculation_provenance": normalized.get("calculation_provenance") or {},
        },
    )
    db.add(evidence)
    db.flush()
    _upsert_material_components(db, material, normalized, evidence.id)

    written_observations = 0
    all_warnings: list[dict[str, Any]] = []
    observation_evidence_ids: list[str] = []
    state_ids: set[str] = {state.id} if state is not None else set()
    for observation in normalized.get("observations") or []:
        observation_method_key = method_for_observation(provider.key, normalized, observation)
        observation_method = methods[observation_method_key]
        observation_state = state
        observation_evidence = evidence

        # A provider response can aggregate properties from different workflows. If the
        # observation-level provenance resolves differently from the record-level method, bind the
        # property to a child Evidence row with its own ComputationalMethod instead of smearing one
        # method label across the whole record.
        if observation_method.key != method.key:
            observation_state = _ensure_computed_state(
                db, material, normalized, observation_method, organisation_id
            )
            if observation_state is not None:
                state_ids.add(observation_state.id)
            observation_evidence = _method_specific_evidence(
                db, parent=evidence, provider=provider, snapshot=snapshot,
                method=observation_method, observation=observation,
                organisation_id=organisation_id, visibility=visibility,
            )

        result = _write_observation(
            db, material=material, state=observation_state, evidence=observation_evidence,
            method=observation_method, observation=observation,
            requirement_temperature_k=requirement_temperature_k,
        )
        if result is not None:
            written_observations += 1
            observation_evidence_ids.append(observation_evidence.id)
            all_warnings.extend(result)
            if observation_evidence is not evidence:
                observation_evidence.applicability_warnings = result

    if all_warnings:
        # The record-level evidence carries a summary, while a method-specific child evidence row
        # carries the exact warnings for its property. Deduplicate only warnings that describe the
        # same method/property condition.
        deduped: dict[tuple[str, str, str | None], dict[str, Any]] = {}
        for warning in all_warnings:
            code = str(warning.get("code"))
            property_scope = warning.get("property_key") if code in {
                "SYSTEMATIC_METHOD_BIAS", "COMPUTATIONAL_METHOD_UNSPECIFIED"
            } else None
            key = (code, str(warning.get("method") or ""), property_scope)
            deduped.setdefault(key, warning)
        evidence.applicability_warnings = sorted(
            deduped.values(),
            key=lambda w: ({"high": 0, "medium": 1, "low": 2}.get(str(w.get("severity")), 3),
                           str(w.get("code")), str(w.get("property_key") or "")),
        )
        all_warnings = list(evidence.applicability_warnings)
        db.flush()

    written_industrial = 0
    for row in normalized.get("industrial_evidence") or []:
        _write_industrial_evidence(db, material, row, organisation_id, provider, evidence)
        written_industrial += 1

    return {
        "external_id": external_id,
        "status": "ingested",
        "source_record_id": source_record.id,
        "material_id": material.id,
        "state_id": state.id if state else None,
        "state_ids": sorted(state_ids),
        "evidence_id": evidence.id,
        "observation_evidence_ids": observation_evidence_ids,
        "computational_method": method.key if computational else None,
        "evidence_method": method.key,
        "identity_match_class": identity.get("match_class"),
        "observations": written_observations,
        "industrial_evidence": written_industrial,
        "applicability_warnings": all_warnings,
    }


def _normalized_identifiers(normalized: dict[str, Any]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for identifier in normalized.get("identifiers") or []:
        namespace = str(identifier.get("namespace") or identifier.get("scheme") or "").strip().casefold()
        value = str(identifier.get("value") or "").strip()
        if namespace and value:
            output.append({"namespace": namespace, "value": value})
    return output


def _upsert_material(
    db: Session, normalized: dict[str, Any], external_id: str,
    organisation_id: str, visibility: str, provider_key: str,
) -> tuple[Material, dict[str, Any]]:
    display_name = str(normalized.get("display_name") or external_id)
    identifiers = _normalized_identifiers(normalized)
    composition = identity_composition(normalized.get("chemical_formula"))
    identity = resolve_identity(
        db, canonical_name=display_name, identifiers=identifiers, composition=composition,
        organisation_id=organisation_id,
    )
    if identity.get("match_class") == "exact" and identity.get("selected_material_id"):
        resolved = db.get(Material, identity["selected_material_id"])
        if resolved is None:
            raise PersistError("Resolved material identity disappeared before persistence")
        return resolved, identity

    # A name or composition-only signal is not enough to merge crystalline materials automatically.
    # Preserve it in the audit metadata, create a provider-scoped material, and let a curator merge
    # later if stronger identity evidence becomes available.
    canonical = _canonical_name(display_name, provider_key, external_id)
    material = db.query(Material).filter_by(canonical_name=canonical).one_or_none()
    if material is None:
        material = Material(
            canonical_name=canonical, display_name=display_name,
            material_family="crystalline_inorganic"
            if normalized.get("source") in {"optimade", "materials_project"} else "chemical",
            composition_summary=normalized.get("chemical_formula"),
            description=(
                "Ingested from an external database. "
                + ("This structure is flagged as theoretical by the source and may never have "
                   "been synthesised." if normalized.get("is_theoretical") else "")
            ).strip(),
            source_type="external_ingest", is_seed_data=False,
            owner_organisation_id=organisation_id, visibility=visibility,
        )
        db.add(material)
        db.flush()
    return material, identity


def _upsert_identifiers(
    db: Session, material: Material, normalized: dict[str, Any],
    organisation_id: str, visibility: str,
) -> None:
    for identifier in normalized.get("identifiers") or []:
        namespace = str(identifier.get("namespace") or identifier.get("scheme") or "").strip().casefold()
        value = str(identifier.get("value") or "").strip()
        if not namespace or not value:
            continue
        try:
            normalized_value = normalize_identifier(namespace, value)
        except Exception:
            normalized_value = value.casefold()
        exists = (
            db.query(MaterialIdentifier)
            .filter(func.lower(MaterialIdentifier.namespace) == namespace,
                    MaterialIdentifier.normalized_value == normalized_value,
                    MaterialIdentifier.organisation_id == organisation_id)
            .one_or_none()
        )
        if exists is not None:
            if exists.material_id != material.id:
                raise PersistError(
                    f"IDENTIFIER_CONFLICT: {namespace}:{value} already resolves to another material"
                )
            continue
        db.add(MaterialIdentifier(
            material_id=material.id, namespace=namespace, value=value,
            normalized_value=normalized_value, is_primary=bool(identifier.get("is_primary", False)),
            organisation_id=organisation_id, visibility=visibility,
        ))
    db.flush()


def _upsert_material_components(
    db: Session, material: Material, normalized: dict[str, Any], evidence_id: str,
) -> None:
    composition = identity_composition(normalized.get("chemical_formula"))
    if not composition:
        return
    existing = db.query(MaterialComponent).filter_by(material_id=material.id).all()
    if existing:
        return
    for sequence, component in enumerate(composition):
        db.add(MaterialComponent(
            material_id=material.id, component_name=str(component["component_name"]),
            component_role="host", amount_value=float(component["amount_value"]),
            amount_basis="stoichiometric", evidence_id=evidence_id, sequence=sequence,
            notes=f"Parsed conservatively from formula {normalized.get('chemical_formula')}",
        ))
    db.flush()


def _ensure_computed_state(
    db: Session, material: Material, normalized: dict[str, Any],
    method: ComputationalMethod, organisation_id: str,
) -> MaterialState | None:
    """Create the state these values actually describe — for DFT, a 0 K static lattice.

    This is the load-bearing honesty in the whole connector layer. Recording a computed value
    against an ambient state would let a 0 K number satisfy a 525 K requirement silently.
    """
    from app.services.material_states import create_material_state

    if not normalized.get("observations"):
        return None
    if method.method_family not in {"dft", "machine_learning"}:
        # Formula-level reference properties (for example PubChem molar mass) do not describe a
        # thermodynamic/material state. Creating an "as reported" state would fabricate context.
        return None

    temperature = method.nominal_temperature_k
    label_suffix = (
        f"{temperature:g} K computed ({method.functional or method.method_family})"
        if temperature is not None else f"as reported ({method.method_family})"
    )
    label = f"{material.display_name} — {label_suffix}"

    existing = (
        db.query(MaterialState)
        .filter_by(material_id=material.id, label=label, organisation_id=organisation_id)
        .one_or_none()
    )
    if existing is not None:
        return existing

    composition = state_composition(normalized.get("chemical_formula"))

    return create_material_state(
        db, organisation_id=organisation_id, material_id=material.id, label=label,
        composition=composition or None,
        crystal_system=normalized.get("crystal_system"),
        space_group_symbol=normalized.get("space_group_symbol"),
        space_group_number=normalized.get("space_group_number"),
        phase="solid" if composition else None,
        temperature_k=temperature,
        pressure_pa=0.0 if temperature == 0.0 else None,
        is_reference_state=False,
        provenance_note=(
            f"State inferred from {method.display_name}. {method.applicability_note or ''} "
            "Conditions describe the calculation, not a measurement."
        ).strip(),
    )


def _method_specific_evidence(
    db: Session, *, parent: Evidence, provider: SourceProvider, snapshot: DatasetSnapshot,
    method: ComputationalMethod, observation: dict[str, Any], organisation_id: str, visibility: str,
) -> Evidence:
    """Create property-scoped evidence when one provider record contains mixed workflows."""
    computational = method.method_family in {"dft", "machine_learning"}
    evidence_type = {
        "reference_data": "external_reference",
        "regulatory_reference": "external_regulatory",
        "structure_reference": "external_structure",
    }.get(method.method_family, "external_computational" if computational else "external_ingest")
    source_quality = {
        "reference_data": "reference_database",
        "regulatory_reference": "regulatory_authority",
        "structure_reference": "structural_database",
    }.get(method.method_family, "computed_database" if computational else "external_database")
    property_key = str(observation.get("property_key") or "external_property")
    row = Evidence(
        evidence_type=evidence_type,
        title=f"{parent.title} — {property_key}",
        source_reference=parent.source_reference,
        description=(
            "Property-scoped provenance derived from the same provider record because this "
            "observation carries a calculation method different from the record-level method."
        ),
        method=method.display_name,
        provider_id=provider.id, source_record_id=parent.source_record_id,
        parent_evidence_id=parent.id, organisation_id=organisation_id, visibility=visibility,
        status="reported", evidence_date=parent.evidence_date,
        computational_method_id=method.id if computational else None,
        dataset_snapshot_id=snapshot.id, source_quality=source_quality,
        metadata_json={
            **(parent.metadata_json or {}),
            "method_key": method.key,
            "method_family": method.method_family,
            "property_key": property_key,
            "calculation_provenance": observation.get("calculation_provenance") or {},
            "property_scoped_method_provenance": True,
        },
    )
    db.add(row)
    db.flush()
    return row



def _write_observation(
    db: Session, *, material: Material, state: MaterialState | None, evidence: Evidence,
    method: ComputationalMethod, observation: dict[str, Any],
    requirement_temperature_k: float | None,
) -> list[dict[str, Any]] | None:
    property_key = str(observation.get("property_key") or "")
    definition = _resolve_property_definition(db, property_key)
    if definition is None:
        # An unknown property is skipped rather than invented. Silently coercing it into an
        # adjacent definition is how a database fills up with values nobody can interpret.
        return None

    value = observation.get("numeric_value")
    unit = str(observation.get("unit") or "")
    if value is None or not unit:
        return None

    try:
        validate_property_unit(property_key, unit, definition.canonical_unit)
    except UnitError:
        # A unit mismatch is a real signal that the mapping is wrong; refuse rather than guess.
        return None

    warnings = applicability_warnings(
        method, property_key, requirement_temperature_k=requirement_temperature_k
    )

    row = MaterialPropertyObservation(
        material_id=material.id,
        property_definition_id=definition.id,
        value_type="numeric",
        numeric_value=float(value),
        unit=unit,
        conditions=observation.get("conditions") or {},
        evidence_id=evidence.id,
        method=method.display_name,
        confidence=None,
        status="active",
        curator_note=(
            (f"Ingested computed value ({method.key}). " if method.method_family in {"dft", "machine_learning"}
             else f"Ingested external reference value ({method.key}); not asserted to be an experimental measurement. ")
            + ("; ".join(w["message"] for w in warnings) if warnings else "No method warnings.")
        )[:2000],
    )
    db.add(row)
    db.flush()
    return warnings


def _write_industrial_evidence(
    db: Session, material: Material, row: dict[str, Any], organisation_id: str,
    provider: SourceProvider, evidence: Evidence,
) -> None:
    from app.services.industrial import create_industrial_evidence

    create_industrial_evidence(db, {
        "organisation_id": organisation_id,
        "visibility": "private",
        "material_id": material.id,
        "hypothesis_id": None,
        "category": row.get("category"),
        "metric_key": row.get("metric_key"),
        "display_label": row.get("display_label"),
        "numeric_value": row.get("numeric_value"),
        "boolean_value": row.get("boolean_value"),
        "unit": row.get("unit"),
        "geography": row.get("geography"),
        "jurisdiction": row.get("jurisdiction"),
        "source_type": row.get("source_type") or "external_database",
        "source_reference": evidence.source_reference,
        "source_record_id": evidence.source_record_id,
        "extraction_method": evidence.method,
        "as_of_date": row.get("as_of_date") or datetime.now(UTC).date(),
        "is_estimate": bool(row.get("is_estimate", False)),
        "notes": row.get("notes"),
        "metadata_json": {
            "provider": provider.key,
            "evidence_id": evidence.id,
            "license_identifier": provider.license_identifier,
        },
    })


def ingest(
    db: Session, connector: Any, *, dataset_key: str, organisation_id: str,
    requirement_temperature_k: float | None = None, commercial_context: bool = True,
    **query: Any,
) -> dict[str, Any]:
    """Run a connector end to end and persist everything it returns."""
    snapshot, normalized_records = connector.run(
        db, dataset_key=dataset_key, organisation_id=organisation_id,
        commercial_context=commercial_context, **query,
    )
    provider = db.get(SourceProvider, snapshot.provider_id)
    results = [
        persist_record(
            db, provider=provider, snapshot=snapshot, normalized=record,
            organisation_id=organisation_id,
            requirement_temperature_k=requirement_temperature_k,
        )
        for record in normalized_records
    ]
    return {
        "dataset_snapshot_id": snapshot.id,
        "provider": provider.key,
        "provider_version": snapshot.provider_version,
        "is_reproducible": snapshot.is_reproducible,
        "reproducibility_note": snapshot.reproducibility_note,
        "record_count": len(results),
        "ingested": sum(1 for r in results if r["status"] == "ingested"),
        "already_ingested": sum(1 for r in results if r["status"] == "already_ingested"),
        "observations": sum(r["observations"] for r in results),
        "industrial_evidence": sum(r["industrial_evidence"] for r in results),
        "results": results,
        "attribution_text": provider.attribution_text,
    }
