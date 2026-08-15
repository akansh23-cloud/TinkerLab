from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import scope_organisation
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import ComputationalMethod, DatasetSnapshot, SourceProvider
from app.schemas.external_data import ExternalIngestRequest
from app.services.ingest import (
    CompToxConnector,
    ConnectorError,
    LicenceError,
    MaterialsProjectConnector,
    OptimadeConnector,
    PubChemConnector,
    ingest,
)
from app.services.ingest.persist import PersistError

router = APIRouter(prefix="/external-data", tags=["external-data"])
settings = get_settings()


def _org(value: str | None) -> str:
    if not value:
        raise HTTPException(400, "X-Organisation-ID is required for external ingestion")
    return value


def _safe_optimade_url(value: str) -> str:
    """Reject obvious SSRF targets before the backend opens an operator-supplied OPTIMADE URL."""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "OPTIMADE base URL must be a credential-free HTTPS URL")
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise HTTPException(422, "Private/local OPTIMADE hosts are not accepted by this API")
    try:
        addresses = {row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise HTTPException(422, "OPTIMADE host could not be resolved") from exc
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(422, "Private/local OPTIMADE hosts are not accepted by this API")
    return value.rstrip("/")


def _snapshot_json(row: DatasetSnapshot, provider: SourceProvider | None) -> dict:
    return {
        "id": row.id,
        "provider": provider.key if provider else None,
        "provider_name": provider.display_name if provider else None,
        "dataset_key": row.dataset_key,
        "provider_version": row.provider_version,
        "query_descriptor": row.query_descriptor or {},
        "record_count": row.record_count,
        "retrieved_at": row.retrieved_at,
        "connector_version": row.connector_version,
        "content_checksum": row.content_checksum,
        "is_reproducible": row.is_reproducible,
        "reproducibility_note": row.reproducibility_note,
        "metadata": row.metadata_json or {},
    }


@router.get("/providers")
def providers(db: Session = Depends(get_db)):
    persisted = {row.key: row for row in db.query(SourceProvider).all()}

    def stored(key: str) -> dict | None:
        row = persisted.get(key)
        if row is None:
            return None
        return {
            "license_identifier": row.license_identifier,
            "commercial_use_permitted": row.commercial_use_permitted,
            "redistribution_permitted": row.redistribution_permitted,
            "license_reviewed_at": row.license_reviewed_at,
            "license_reviewed_by": row.license_reviewed_by,
        }

    return [
        {
            "key": "materials_project", "name": "Materials Project", "requires_api_key": True,
            "configured": bool(settings.materials_project_api_key), "stored_licence": stored("materials_project"),
            "server_side_only": True, "api_key_environment": "MATERIALS_PROJECT_API_KEY",
            "base_url": settings.materials_project_api_base_url,
        },
        {
            "key": "pubchem", "name": "PubChem (NIH/NLM)", "requires_api_key": False,
            "configured": True, "stored_licence": stored("pubchem"),
        },
        {
            "key": "epa_comptox", "name": "EPA CompTox", "requires_api_key": True,
            "configured": bool(settings.epa_comptox_api_key), "stored_licence": stored("epa_comptox"),
        },
        {
            "key": "optimade", "name": "OPTIMADE provider", "requires_api_key": False,
            "configured": True,
            "note": "Licence is resolved per originating OPTIMADE provider; unreviewed providers are blocked at ingest.",
        },
    ]


@router.get("/methods")
def methods(db: Session = Depends(get_db)):
    """Expose the scientific calculation-method catalogue without implying non-computational sources are calculations."""
    rows = (
        db.query(ComputationalMethod)
        .filter(ComputationalMethod.method_family.in_(["dft", "machine_learning"]))
        .order_by(ComputationalMethod.display_name)
        .all()
    )
    return [
        {
            "id": row.id,
            "key": row.key,
            "display_name": row.display_name,
            "method_family": row.method_family,
            "functional": row.functional,
            "basis_or_code": row.basis_or_code,
            "nominal_temperature_k": row.nominal_temperature_k,
            "includes_thermal_expansion": row.includes_thermal_expansion,
            "includes_zero_point_energy": row.includes_zero_point_energy,
            "known_property_bias": row.known_property_bias or {},
            "applicability_note": row.applicability_note,
            "reference_url": row.reference_url,
        }
        for row in rows
    ]


@router.get("/snapshots")
def snapshots(
    provider: str | None = None,
    dataset_key: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    query = db.query(DatasetSnapshot).filter(DatasetSnapshot.organisation_id == org)
    if dataset_key:
        query = query.filter(DatasetSnapshot.dataset_key == dataset_key)
    if provider:
        query = query.join(SourceProvider, DatasetSnapshot.provider_id == SourceProvider.id).filter(
            SourceProvider.key == provider
        )
    rows = query.order_by(DatasetSnapshot.retrieved_at.desc()).limit(limit).all()
    return [_snapshot_json(row, db.get(SourceProvider, row.provider_id)) for row in rows]


@router.get("/snapshots/{snapshot_id}")
def snapshot_detail(
    snapshot_id: str,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    row = db.get(DatasetSnapshot, snapshot_id)
    if row is None or row.organisation_id != org:
        raise HTTPException(404, "Dataset snapshot not found")
    return _snapshot_json(row, db.get(SourceProvider, row.provider_id))


@router.post("/ingest", status_code=201)
def run_external_ingestion(
    payload: ExternalIngestRequest,
    organisation_id: str | None = Depends(scope_organisation),
    db: Session = Depends(get_db),
):
    org = _org(organisation_id)
    if payload.provider == "materials_project":
        if not settings.materials_project_api_key:
            raise HTTPException(503, "Materials Project API key is not configured on the server")
        connector = MaterialsProjectConnector(
            api_key=settings.materials_project_api_key,
            base_url=settings.materials_project_api_base_url,
        )
    elif payload.provider == "epa_comptox":
        if not settings.epa_comptox_api_key:
            raise HTTPException(503, "EPA CompTox API key is not configured on the server")
        connector = CompToxConnector(api_key=settings.epa_comptox_api_key)
    elif payload.provider == "pubchem":
        connector = PubChemConnector()
    else:
        connector = OptimadeConnector(
            base_url=_safe_optimade_url(str(payload.optimade_base_url)),
            provider_id=str(payload.optimade_provider_id),
        )

    try:
        result = ingest(
            db, connector, dataset_key=payload.dataset_key, organisation_id=org,
            commercial_context=payload.commercial_context,
            requirement_temperature_k=payload.requirement_temperature_k,
            **payload.query,
        )
        db.commit()
        return result
    except LicenceError as exc:
        db.rollback()
        raise HTTPException(409, str(exc)) from exc
    except (ConnectorError, PersistError, ValueError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
