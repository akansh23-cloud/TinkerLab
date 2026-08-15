from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.entities import (
    Evidence,
    ImportBatch,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialProcessState,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    ObservationConditionSet,
    Organisation,
    SourceProvider,
    SourceRecord,
)
from app.schemas.materials import ConditionSetCreate, MaterialComponentCreate
from app.services.conditions import validate_condition_values
from app.services.identity import normalize_identifier, normalize_material_name, resolve_identity
from app.services.providers import provider_registry
from app.services.units import UnitError, validate_property_unit

PARSER_VERSION = "phase2-local-import/1.0"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def checksum(value: Any) -> str:
    text = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _parse_json(content: str) -> list[dict[str, Any]]:
    payload = json.loads(content)
    if not isinstance(payload, dict) or not isinstance(payload.get("materials"), list):
        raise ValueError("JSON import requires an object with a materials array")
    rows: list[dict[str, Any]] = [dict(row) for row in payload["materials"] if isinstance(row, dict)]
    if len(rows) != len(payload["materials"]):
        raise ValueError("JSON import materials array must contain objects only")
    return rows


def _parse_csv(content: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content))
    required = {"external_record_id", "canonical_name", "display_name", "material_family"}
    if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
        raise ValueError(f"CSV requires columns: {', '.join(sorted(required))}")
    groups: dict[str, dict[str, Any]] = {}
    for i, row in enumerate(reader, start=2):
        external_id = _clean(row.get("external_record_id"))
        if not external_id:
            raise ValueError(f"CSV row {i}: external_record_id is required")
        material = groups.setdefault(external_id, {
            "external_record_id": external_id,
            "canonical_name": _clean(row.get("canonical_name")),
            "display_name": _clean(row.get("display_name")),
            "material_family": _clean(row.get("material_family")),
            "description": _clean(row.get("description")),
            "visibility": _clean(row.get("visibility")) or "private",
            "identifiers": [], "composition": [], "process_states": [], "evidence": [], "observations": [],
        })
        namespace, identifier = _clean(row.get("identifier_namespace")), _clean(row.get("identifier_value"))
        if namespace and identifier:
            ident = {"namespace": namespace, "value": identifier, "is_primary": str(row.get("identifier_primary", "")).casefold() in {"1", "true", "yes"}}
            if ident not in material["identifiers"]:
                material["identifiers"].append(ident)
        prop = _clean(row.get("property_key"))
        if prop:
            evidence_key = _clean(row.get("evidence_key")) or f"row-{i}"
            evidence = {
                "key": evidence_key,
                "evidence_type": _clean(row.get("evidence_type")) or "user_provided",
                "title": _clean(row.get("evidence_title")) or f"Imported evidence row {i}",
                "source_reference": _clean(row.get("source_reference")),
                "method": _clean(row.get("method")),
            }
            if not any(e.get("key") == evidence_key for e in material["evidence"]):
                material["evidence"].append(evidence)
            value_type = _clean(row.get("value_type")) or "numeric"
            observation: dict[str, Any] = {"property_key": prop, "value_type": value_type, "evidence_key": evidence_key}
            if value_type == "boolean":
                raw_bool = str(row.get("boolean_value", "")).casefold()
                if raw_bool not in {"true", "false", "1", "0", "yes", "no"}:
                    raise ValueError(f"CSV row {i}: invalid boolean_value")
                observation["boolean_value"] = raw_bool in {"true", "1", "yes"}
            else:
                try:
                    observation["numeric_value"] = float(str(row.get("numeric_value", "")))
                except ValueError as exc:
                    raise ValueError(f"CSV row {i}: numeric_value is required for numeric observation") from exc
                observation["unit"] = _clean(row.get("unit"))
            condition: dict[str, Any] = {}
            if _clean(row.get("condition_temperature")):
                condition["temperature_value"] = float(str(row["condition_temperature"]))
                condition["temperature_unit"] = _clean(row.get("condition_temperature_unit")) or "degC"
            if _clean(row.get("condition_pressure")):
                condition["pressure_value"] = float(str(row["condition_pressure"]))
                condition["pressure_unit"] = _clean(row.get("condition_pressure_unit")) or "kPa"
            if condition:
                observation["condition_set"] = condition
            material["observations"].append(observation)
    return list(groups.values())


def parse_import(input_format: str, content: str) -> list[dict[str, Any]]:
    if input_format == "json":
        return _parse_json(content)
    if input_format == "csv":
        return _parse_csv(content)
    raise ValueError("input_format must be json or csv")


def validate_material_record(db: Session, record: dict[str, Any], row: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    required = ["external_record_id", "canonical_name", "display_name", "material_family"]
    for key in required:
        if not record.get(key):
            errors.append({"row": row, "field": key, "message": "required"})
    visibility = record.get("visibility", "private")
    if visibility not in {"public", "private"}:
        errors.append({"row": row, "field": "visibility", "message": "must be public or private"})
    evidence_keys: set[str] = set()
    for i, evidence in enumerate(record.get("evidence", [])):
        key = evidence.get("key")
        if not key:
            errors.append({"row": row, "field": f"evidence[{i}].key", "message": "required"})
        elif key in evidence_keys:
            errors.append({"row": row, "field": f"evidence[{i}].key", "message": "duplicate key"})
        else:
            evidence_keys.add(key)
        if not evidence.get("title"):
            errors.append({"row": row, "field": f"evidence[{i}].title", "message": "required"})
    for i, component in enumerate(record.get("composition", [])):
        try:
            MaterialComponentCreate.model_validate(component)
        except ValidationError as exc:
            errors.append({"row": row, "field": f"composition[{i}]", "message": str(exc)})
    normalized_observations = []
    for i, observation in enumerate(record.get("observations", [])):
        property_key = observation.get("property_key")
        definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
        if not definition:
            errors.append({"row": row, "field": f"observations[{i}].property_key", "message": f"unknown property {property_key}"}); continue
        evidence_key = observation.get("evidence_key")
        if evidence_key not in evidence_keys:
            errors.append({"row": row, "field": f"observations[{i}].evidence_key", "message": "must reference evidence in same material record"})
        value_type = observation.get("value_type", "numeric")
        if value_type == "numeric":
            if observation.get("numeric_value") is None or not observation.get("unit"):
                errors.append({"row": row, "field": f"observations[{i}]", "message": "numeric observation requires numeric_value and unit"}); continue
            try:
                validate_property_unit(property_key, observation["unit"], definition.canonical_unit or "")
            except UnitError as exc:
                errors.append({"row": row, "field": f"observations[{i}].unit", "message": str(exc)})
        elif value_type == "boolean":
            if observation.get("boolean_value") is None or definition.quantity_type != "boolean":
                errors.append({"row": row, "field": f"observations[{i}]", "message": "invalid boolean observation"})
        else:
            errors.append({"row": row, "field": f"observations[{i}].value_type", "message": "must be numeric or boolean"})
        if observation.get("condition_set"):
            try:
                condition = ConditionSetCreate.model_validate(observation["condition_set"])
                validate_condition_values(condition)
            except (ValidationError, UnitError) as exc:
                errors.append({"row": row, "field": f"observations[{i}].condition_set", "message": str(exc)})
        normalized_observations.append(observation)
    normalized = {**record, "visibility": visibility, "observations": normalized_observations}
    if not record.get("identifiers"):
        warnings.append({"row": row, "message": "no external identifier supplied; identity resolution will rely on canonical name/composition"})
    return (normalized if not errors else None), warnings, errors


def preview_import(db: Session, input_format: str, content: str) -> dict[str, Any]:
    payload_hash = checksum(content)
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    try:
        records = parse_import(input_format, content)
    except (ValueError, json.JSONDecodeError) as exc:
        return {"payload_checksum": payload_hash, "format": input_format, "valid": False, "material_count": 0, "observation_count": 0, "warnings": [], "errors": [{"row": None, "message": str(exc)}], "normalized_preview": []}
    for i, record in enumerate(records, start=1):
        norm, warn, err = validate_material_record(db, record, i)
        warnings.extend(warn); errors.extend(err)
        if norm:
            normalized.append(norm)
    return {
        "payload_checksum": payload_hash,
        "format": input_format,
        "valid": not errors,
        "material_count": len(normalized),
        "observation_count": sum(len(x.get("observations", [])) for x in normalized),
        "warnings": warnings,
        "errors": errors,
        "normalized_preview": normalized[:10],
    }


def _ensure_provider(db: Session, key: str) -> SourceProvider:
    provider = db.query(SourceProvider).filter_by(key=key).one_or_none()
    if not provider:
        raise ValueError(f"unknown source provider {key}")
    if not provider_registry.get(key):
        raise ValueError(f"provider adapter {key} is not registered")
    return provider


def _safe_canonical(base: str, external_id: str) -> str:
    safe = normalize_material_name(base) or "imported-material"
    ext = re.sub(r"[^a-zA-Z0-9]+", "-", external_id).strip("-")[:40]
    return f"{safe}-{ext}" if ext else safe


def commit_import(db: Session, *, organisation_id: str, input_format: str, content: str, provider_key: str, idempotency_key: str | None) -> dict[str, Any]:
    if not db.get(Organisation, organisation_id):
        raise ValueError("organisation not found")
    preview = preview_import(db, input_format, content)
    if not preview["valid"]:
        raise ValueError("import contains validation errors")
    provider = _ensure_provider(db, provider_key)
    payload_hash = preview["payload_checksum"]
    existing = db.query(ImportBatch).filter_by(organisation_id=organisation_id, payload_checksum=payload_hash, status="committed").one_or_none()
    if existing:
        return {"import_id": existing.id, "status": existing.status, "idempotent_replay": True, "payload_checksum": payload_hash, "summary": existing.summary_json, "errors": existing.error_json}

    records = parse_import(input_format, content)
    summary = {"materials_created": 0, "materials_matched": 0, "source_records": 0, "identifiers": 0, "components": 0, "process_states": 0, "evidence": 0, "observations": 0}
    now = datetime.now(UTC)
    batch = ImportBatch(organisation_id=organisation_id, provider_id=provider.id, input_format=input_format, payload_checksum=payload_hash, idempotency_key=idempotency_key, status="committed", summary_json={}, error_json=[], committed_at=now)
    db.add(batch); db.flush()

    for index, raw in enumerate(records, start=1):
        normalized, _, errors = validate_material_record(db, raw, index)
        if errors or normalized is None:
            raise ValueError("validated preview changed during import; aborting transaction")
        adapter = provider_registry.get(provider_key)
        assert adapter is not None
        normalized = adapter.normalize(normalized)
        raw_hash = checksum(raw)
        norm_hash = checksum(normalized)
        source_record = SourceRecord(
            provider_id=provider.id, organisation_id=organisation_id, visibility=normalized.get("visibility", "private"),
            external_record_id=str(normalized["external_record_id"]), parser_version=PARSER_VERSION,
            raw_checksum=raw_hash, normalized_checksum=norm_hash, raw_payload=raw, status="normalized",
            metadata_json={"import_batch_id": batch.id},
        )
        db.add(source_record); db.flush(); summary["source_records"] += 1

        identity = resolve_identity(db, canonical_name=normalized.get("canonical_name"), identifiers=normalized.get("identifiers", []), composition=normalized.get("composition", []), organisation_id=organisation_id)
        if identity["match_class"] == "exact" and identity["selected_material_id"]:
            matched = db.get(Material, identity["selected_material_id"])
            if matched is None:
                raise ValueError("resolved material identity no longer exists; re-run identity resolution")
            material = matched; summary["materials_matched"] += 1
        elif identity["match_class"] in {"probable", "ambiguous"}:
            raise ValueError(f"material {normalized.get('display_name')} requires curator identity review before import")
        else:
            proposed = str(normalized["canonical_name"])
            if db.query(Material).filter_by(canonical_name=proposed).first():
                proposed = _safe_canonical(proposed, str(normalized["external_record_id"]))
            material = Material(
                canonical_name=proposed, display_name=str(normalized["display_name"]), material_family=str(normalized["material_family"]),
                description=normalized.get("description"), composition_summary=normalized.get("composition_summary"), source_type=provider.key,
                is_seed_data=False, owner_organisation_id=organisation_id if normalized.get("visibility", "private") == "private" else None,
                visibility=normalized.get("visibility", "private"),
            )
            db.add(material); db.flush(); summary["materials_created"] += 1

        evidence_by_key: dict[str, Evidence] = {}
        for evidence_raw in normalized.get("evidence", []):
            evidence = Evidence(
                evidence_type=evidence_raw.get("evidence_type", "user_provided"), title=evidence_raw["title"],
                source_reference=evidence_raw.get("source_reference"), description=evidence_raw.get("description"), method=evidence_raw.get("method"),
                confidence=evidence_raw.get("confidence"), metadata_json={"import_batch_id": batch.id}, provider_id=provider.id,
                source_record_id=source_record.id, organisation_id=organisation_id, visibility=normalized.get("visibility", "private"),
                status="reported", source_quality=evidence_raw.get("source_quality"),
            )
            db.add(evidence); db.flush(); evidence_by_key[str(evidence_raw["key"])] = evidence; summary["evidence"] += 1

        for ident in normalized.get("identifiers", []):
            namespace, value = str(ident["namespace"]), str(ident["value"])
            normalized_value = normalize_identifier(namespace, value)
            exists = db.query(MaterialIdentifier).filter_by(namespace=namespace, normalized_value=normalized_value, organisation_id=organisation_id).one_or_none()
            if not exists:
                db.add(MaterialIdentifier(material_id=material.id, namespace=namespace, value=value, normalized_value=normalized_value, is_primary=bool(ident.get("is_primary")), organisation_id=organisation_id, visibility=normalized.get("visibility", "private")))
                summary["identifiers"] += 1

        for seq, component_raw in enumerate(normalized.get("composition", [])):
            comp = MaterialComponentCreate.model_validate(component_raw)
            db.add(MaterialComponent(material_id=material.id, component_name=comp.component_name, component_identifier=comp.component_identifier, component_role=comp.component_role, amount_value=comp.amount_value, amount_lower=comp.amount_lower, amount_upper=comp.amount_upper, amount_unit=comp.amount_unit, amount_basis=comp.amount_basis.value, uncertainty=comp.uncertainty, is_redacted=comp.is_redacted, redaction_label=comp.redaction_label, sequence=comp.sequence or seq, notes=comp.notes))
            summary["components"] += 1

        for seq, state in enumerate(normalized.get("process_states", [])):
            db.add(MaterialProcessState(material_id=material.id, state_label=str(state["state_label"]), process_name=state.get("process_name"), sequence=int(state.get("sequence", seq)), parameters=state.get("parameters", {}), notes=state.get("notes")))
            summary["process_states"] += 1

        for obs_raw in normalized.get("observations", []):
            definition = db.query(MaterialPropertyDefinition).filter_by(key=obs_raw["property_key"]).one()
            condition = None
            if obs_raw.get("condition_set"):
                c = ConditionSetCreate.model_validate(obs_raw["condition_set"])
                validate_condition_values(c)
                condition = ObservationConditionSet(**c.model_dump(exclude={"metadata"}), metadata_json=c.metadata)
                db.add(condition); db.flush()
            evidence = evidence_by_key[str(obs_raw["evidence_key"])]
            observation = MaterialPropertyObservation(
                material_id=material.id, property_definition_id=definition.id, value_type=obs_raw.get("value_type", "numeric"),
                numeric_value=obs_raw.get("numeric_value"), boolean_value=obs_raw.get("boolean_value"), unit=obs_raw.get("unit"),
                conditions=obs_raw.get("conditions", {}), condition_set_id=condition.id if condition else None,
                evidence_id=evidence.id, source_record_id=source_record.id, method=obs_raw.get("method") or evidence.method,
                uncertainty=obs_raw.get("uncertainty"), uncertainty_type=obs_raw.get("uncertainty_type"),
                uncertainty_lower=obs_raw.get("uncertainty_lower"), uncertainty_upper=obs_raw.get("uncertainty_upper"),
                uncertainty_stddev=obs_raw.get("uncertainty_stddev"), confidence=obs_raw.get("confidence"), status="active", imported_at=now,
            )
            db.add(observation); summary["observations"] += 1

    batch.summary_json = summary
    db.commit()
    return {"import_id": batch.id, "status": batch.status, "idempotent_replay": False, "payload_checksum": payload_hash, "summary": summary, "errors": []}
