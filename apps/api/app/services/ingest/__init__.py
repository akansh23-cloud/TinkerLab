"""Phase 11 — External data ingestion with licence, snapshot and method provenance."""

from app.services.ingest.base import (
    Connector,
    ConnectorError,
    FixtureTransport,
    HttpTransport,
    LicenceError,
    LicenceTerms,
    RateLimiter,
    Transport,
    connector_registry,
)
from app.services.ingest.persist import ingest, persist_record
from app.services.ingest.structures import OptimadeConnector
from app.services.ingest.materials_project_v2 import MaterialsProjectConnector
from app.services.ingest.substances import CompToxConnector, PubChemConnector

__all__ = [
    "CompToxConnector", "Connector", "ConnectorError", "FixtureTransport", "HttpTransport",
    "LicenceError", "LicenceTerms", "MaterialsProjectConnector", "OptimadeConnector",
    "PubChemConnector", "RateLimiter", "Transport", "connector_registry", "ingest",
    "persist_record",
]
