from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Citation,
    Evidence,
    ImportBatch,
    Material,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    SourceProvider,
    SourceRecord,
)
from app.schemas.ingestion import ImportBatchOut, ImportCommitOut, ImportPreviewOut, ImportRequest
from app.schemas.materials import (
    CitationOut,
    IdentityResolveRequest,
    IdentityResolveResponse,
    ObservationOut,
    SelectionPreviewRequest,
    SelectionPreviewResponse,
    SourceProviderOut,
    SourceRecordOut,
)
from app.services.conflicts import detect_conflicts, detect_conflicts_from_observations
from app.services.identity import resolve_identity
from app.services.ingestion import commit_import, preview_import
from app.services.selection import (
    SelectionPolicy,
    build_selection_context,
    select_from_context,
    select_observation,
)

router = APIRouter(tags=["knowledge-graph"])


def _material_visible(db: Session, material_id: str, organisation_id: str | None) -> Material:
    query = db.query(Material).filter(Material.id == material_id)
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    material = query.one_or_none()
    if not material:
        raise HTTPException(404, "Material not found")
    return material




@router.get("/material-explorer")
def material_explorer(q: str | None = Query(default=None), family: str | None = Query(default=None), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    query = db.query(Material).options(
        selectinload(Material.identifiers),
        selectinload(Material.observations).selectinload(MaterialPropertyObservation.property_definition),
        selectinload(Material.observations).selectinload(MaterialPropertyObservation.evidence),
        selectinload(Material.observations).selectinload(MaterialPropertyObservation.condition_set),
    )
    if organisation_id:
        query = query.filter(or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id))
    else:
        query = query.filter(Material.visibility == "public")
    if q:
        query = query.filter(or_(Material.display_name.ilike(f"%{q}%"), Material.canonical_name.ilike(f"%{q}%")))
    if family:
        query = query.filter(Material.material_family == family)
    materials = query.order_by(Material.display_name).limit(200).all()
    return [{
        "id": m.id, "display_name": m.display_name, "canonical_name": m.canonical_name, "material_family": m.material_family,
        "source_type": m.source_type, "is_seed_data": m.is_seed_data, "visibility": m.visibility,
        "identifiers": [{"namespace": i.namespace, "value": i.value, "is_primary": i.is_primary} for i in m.identifiers],
        "observation_count": len(m.observations),
        "evidence_types": sorted({o.evidence.evidence_type for o in m.observations}),
        "conflict_count": len(detect_conflicts_from_observations(m.observations)),
    } for m in materials]



@router.get("/material-selection-summary/{material_id}")
def material_selection_summary(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    material = _material_visible(db, material_id, organisation_id)
    context = build_selection_context(db, [material.id])
    keys = sorted({key for (mid, key) in context.observations_by_material_property if mid == material.id})
    conflicts = {c["property_key"] for c in detect_conflicts_from_observations([o for (mid, _), rows in context.observations_by_material_property.items() if mid == material.id for o in rows])}
    selections = []
    for key in keys:
        result = select_from_context(context, material.id, key)
        result["scientific_conflict"] = key in conflicts
        selections.append(result)
    return selections

@router.get("/source-providers", response_model=list[SourceProviderOut])
def source_providers(db: Session = Depends(get_db)):
    return db.query(SourceProvider).order_by(SourceProvider.display_name).all()


@router.get("/source-records/{record_id}", response_model=SourceRecordOut)
def source_record(record_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    query = db.query(SourceRecord).options(selectinload(SourceRecord.provider)).filter(SourceRecord.id == record_id)
    if organisation_id:
        query = query.filter(or_(SourceRecord.visibility == "public", SourceRecord.organisation_id == organisation_id))
    else:
        query = query.filter(SourceRecord.visibility == "public")
    row = query.one_or_none()
    if not row: raise HTTPException(404, "Source record not found")
    return row


@router.get("/citations", response_model=list[CitationOut])
def citations(q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(Citation)
    if q: query = query.filter(Citation.title.ilike(f"%{q}%"))
    return query.order_by(Citation.publication_year.desc().nullslast(), Citation.title).limit(200).all()


@router.post("/materials/resolve-identity", response_model=IdentityResolveResponse)
def material_identity(payload: IdentityResolveRequest, db: Session = Depends(get_db)):
    return resolve_identity(
        db,
        canonical_name=payload.canonical_name,
        identifiers=payload.identifiers,
        composition=payload.composition,
        organisation_id=payload.organisation_id,
    )


@router.get("/materials/{material_id}/conflicts")
def material_conflicts(material_id: str, property_key: str | None = Query(default=None), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _material_visible(db, material_id, organisation_id)
    return detect_conflicts(db, material_id, property_key)


@router.get("/materials/{material_id}/evidence-summary")
def evidence_summary(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _material_visible(db, material_id, organisation_id)
    rows = (
        db.query(MaterialPropertyObservation)
        .options(selectinload(MaterialPropertyObservation.evidence))
        .filter(MaterialPropertyObservation.material_id == material_id)
        .all()
    )
    by_type: dict[str, int] = {}
    providers: dict[str, int] = {}
    for row in rows:
        by_type[row.evidence.evidence_type] = by_type.get(row.evidence.evidence_type, 0) + 1
        if row.evidence.provider:
            providers[row.evidence.provider.display_name] = providers.get(row.evidence.provider.display_name, 0) + 1
    return {
        "material_id": material_id,
        "observation_count": len(rows),
        "evidence_by_type": by_type,
        "providers": providers,
        "conflict_count": len(detect_conflicts(db, material_id)),
    }


@router.get("/observations/{observation_id}", response_model=ObservationOut)
def observation(observation_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = (
        db.query(MaterialPropertyObservation)
        .options(
            selectinload(MaterialPropertyObservation.property_definition),
            selectinload(MaterialPropertyObservation.condition_set),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.provider),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.source_record),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.citation),
        )
        .filter(MaterialPropertyObservation.id == observation_id)
        .one_or_none()
    )
    if not row: raise HTTPException(404, "Observation not found")
    _material_visible(db, row.material_id, organisation_id)
    return row


@router.get("/observations/{observation_id}/provenance")
def observation_provenance(observation_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = (
        db.query(MaterialPropertyObservation)
        .options(
            selectinload(MaterialPropertyObservation.property_definition),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.provider),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.source_record),
            selectinload(MaterialPropertyObservation.condition_set),
        )
        .filter(MaterialPropertyObservation.id == observation_id)
        .one_or_none()
    )
    if not row: raise HTTPException(404, "Observation not found")
    _material_visible(db, row.material_id, organisation_id)
    source = row.source_record or row.evidence.source_record
    return {
        "observation_id": row.id,
        "property_key": row.property_definition.key,
        "chain": [
            {
                "stage": "provider_record",
                "id": source.id if source else None,
                "provider": source.provider.display_name if source and source.provider else None,
                "external_record_id": source.external_record_id if source else None,
                "raw_checksum": source.raw_checksum if source else None,
                "normalized_checksum": source.normalized_checksum if source else None,
                "parser_version": source.parser_version if source else None,
            },
            {
                "stage": "evidence",
                "id": row.evidence.id,
                "evidence_type": row.evidence.evidence_type,
                "status": row.evidence.status,
                "title": row.evidence.title,
            },
            {
                "stage": "observation",
                "id": row.id,
                "status": row.status,
                "condition_set_id": row.condition_set_id,
                "curator_preferred": row.curator_preferred,
            },
        ],
    }


@router.post("/observations/{observation_id}/curator-preference")
def curator_preference(observation_id: str, preferred: bool, rationale: str = Query(min_length=3, max_length=1000), organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    row = db.get(MaterialPropertyObservation, observation_id)
    if not row: raise HTTPException(404, "Observation not found")
    _material_visible(db, row.material_id, organisation_id)
    if preferred:
        peers = db.query(MaterialPropertyObservation).filter_by(material_id=row.material_id, property_definition_id=row.property_definition_id).all()
        for peer in peers:
            peer.curator_preferred = peer.id == row.id
            if peer.id != row.id and peer.curator_note and peer.curator_note.startswith("Preference:"):
                peer.curator_note = None
        row.curator_note = f"Preference: {rationale}"
    else:
        row.curator_preferred = False
        row.curator_note = f"Preference removed: {rationale}"
    db.commit()
    return {"observation_id": row.id, "curator_preferred": row.curator_preferred, "curator_note": row.curator_note}


@router.post("/properties/{property_key}/selection-preview", response_model=SelectionPreviewResponse)
def selection_preview(property_key: str, payload: SelectionPreviewRequest, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _material_visible(db, payload.material_id, organisation_id)
    definition = db.query(MaterialPropertyDefinition).filter_by(key=property_key).one_or_none()
    if not definition: raise HTTPException(404, "Property definition not found")
    context = {}
    if payload.context:
        raw = payload.context.model_dump(mode="json", exclude_none=True)
        meta = raw.pop("metadata", {})
        if "temperature_value" in raw:
            context["temperature"] = {"value": raw.pop("temperature_value"), "unit": raw.pop("temperature_unit")}
        if "pressure_value" in raw:
            context["pressure"] = {"value": raw.pop("pressure_value"), "unit": raw.pop("pressure_unit")}
        if "frequency_value" in raw:
            context["frequency"] = {"value": raw.pop("frequency_value"), "unit": raw.pop("frequency_unit")}
        context.update(raw); context.update(meta)
    policy = SelectionPolicy(set(payload.allowed_evidence_types)) if payload.allowed_evidence_types else SelectionPolicy()
    return select_observation(db, payload.material_id, property_key, requested_context=context, policy=policy)


@router.post("/imports/preview", response_model=ImportPreviewOut)
def import_preview(payload: ImportRequest, db: Session = Depends(get_db)):
    if not db.query(SourceProvider).filter_by(key=payload.provider_key).one_or_none():
        raise HTTPException(422, "Unknown provider_key")
    return preview_import(db, payload.input_format, payload.content)


@router.post("/imports", response_model=ImportCommitOut, status_code=201)
def import_commit(payload: ImportRequest, db: Session = Depends(get_db)):
    try:
        return commit_import(
            db,
            organisation_id=payload.organisation_id,
            input_format=payload.input_format,
            content=payload.content,
            provider_key=payload.provider_key,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        db.rollback(); raise HTTPException(422, str(exc)) from exc


@router.get("/imports/{import_id}", response_model=ImportBatchOut)
def import_batch(import_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    if not organisation_id:
        raise HTTPException(404, "Import batch not found")
    query = db.query(ImportBatch).filter(ImportBatch.id == import_id, ImportBatch.organisation_id == organisation_id)
    row = query.one_or_none()
    if not row: raise HTTPException(404, "Import batch not found")
    return {
        "id": row.id, "organisation_id": row.organisation_id, "provider_id": row.provider_id,
        "input_format": row.input_format, "payload_checksum": row.payload_checksum, "idempotency_key": row.idempotency_key,
        "status": row.status, "summary": row.summary_json, "errors": row.error_json,
        "created_at": row.created_at, "committed_at": row.committed_at,
    }
