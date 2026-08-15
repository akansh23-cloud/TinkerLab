"""Phase 11 — External connector framework.

Phase 10 guarantees that identical evidence produces an identical conclusion, verified by checksum.
External data threatens that guarantee in a way local imports never did: a provider can update its
database between two runs, so the same query returns different values and a "deterministic" dossier
silently becomes irreproducible.

Three mechanisms in this module close that hole.

**Transport is injected, never constructed.** Every connector takes a `Transport`. In production
that is `HttpTransport`; in tests it is `FixtureTransport`, replaying recorded payloads. No connector
ever reaches for `requests` directly, so the entire ingestion layer is testable without a network
and a failing test can never be explained away as "the API was down".

**Every fetch is bound to a `DatasetSnapshot`.** The snapshot records the provider's own version
string, the exact query, the record count and a content checksum. A dossier can then state which
release of Materials Project it was computed against, and a reviewer can go and fetch that release.
When a provider exposes no version identifier, the snapshot is marked `is_reproducible=False` with a
stated reason rather than pretending otherwise.

**Licence is enforced at ingest, not at export.** A connector whose provider has not been licence-
reviewed refuses to run. Discovering at dossier-generation time that half your evidence cannot be
redistributed is discovering it too late.
"""

from __future__ import annotations

import hashlib
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import DatasetSnapshot, SourceProvider

CONNECTOR_FRAMEWORK_VERSION = "phase11-connector/1.0"


class ConnectorError(RuntimeError):
    """Raised when a connector cannot complete a fetch or normalisation."""


class LicenceError(ConnectorError):
    """Raised when a provider's licence position blocks the requested use."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def checksum(value: Any) -> str:
    text = value if isinstance(value, str) else canonical_json(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------------------------
class Transport(ABC):
    """Minimal HTTP surface. Deliberately tiny so a fixture implementation is trivial."""

    @abstractmethod
    def get_json(
        self, url: str, *, params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None, timeout: float = 30.0,
    ) -> Any:
        raise NotImplementedError


@dataclass
class RateLimiter:
    """Simple monotonic-clock spacing.

    Providers publish limits (PubChem asks for roughly five requests a second) and exceeding them
    gets an IP blocked, which in a shared deployment punishes every tenant at once. Sleeping is the
    cheapest possible insurance.
    """

    per_second: float | None = None
    _last_call: float = field(default=0.0, repr=False)

    def wait(self) -> None:
        if not self.per_second or self.per_second <= 0:
            return
        interval = 1.0 / self.per_second
        elapsed = time.monotonic() - self._last_call
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_call = time.monotonic()


class HttpTransport(Transport):
    """Production transport. Retries only on transient failures, with bounded backoff."""

    RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self, *, rate_limiter: RateLimiter | None = None, max_retries: int = 3,
        backoff_seconds: float = 1.0, user_agent: str = "TinkerLab/1.0 (+materials-decision-os)",
    ) -> None:
        self.rate_limiter = rate_limiter or RateLimiter()
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.user_agent = user_agent

    def get_json(
        self, url: str, *, params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None, timeout: float = 30.0,
    ) -> Any:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ConnectorError(
                "httpx is required for live ingestion; install it or inject a Transport"
            ) from exc

        merged = {"Accept": "application/json", "User-Agent": self.user_agent}
        merged.update(headers or {})
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                response = httpx.get(url, params=params, headers=merged, timeout=timeout, follow_redirects=True)
            except Exception as exc:  # network-level failure
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2 ** attempt))
                continue

            if response.status_code in self.RETRYABLE_STATUS and attempt < self.max_retries:
                # Honour Retry-After when the provider sends one; guessing is how you get banned.
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if (retry_after or "").replace(".", "", 1).isdigit() \
                    else self.backoff_seconds * (2 ** attempt)
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise ConnectorError(
                    f"{url} returned HTTP {response.status_code}: {response.text[:300]}"
                )
            try:
                return response.json()
            except ValueError as exc:
                raise ConnectorError(f"{url} returned a non-JSON body") from exc

        raise ConnectorError(f"{url} failed after {self.max_retries + 1} attempts: {last_error}")


class FixtureTransport(Transport):
    """Replays recorded payloads. Used by every connector test in this repository.

    Keyed on the url plus its sorted params, so a test that changes a query without updating its
    fixture fails loudly instead of silently replaying the wrong response.
    """

    def __init__(self, fixtures: dict[str, Any], *, strict: bool = True) -> None:
        self.fixtures = fixtures
        self.strict = strict
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @staticmethod
    def key(url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        encoded = "&".join(f"{k}={params[k]}" for k in sorted(params))
        return f"{url}?{encoded}"

    def get_json(
        self, url: str, *, params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None, timeout: float = 30.0,
    ) -> Any:
        self.calls.append((url, dict(params or {})))
        composite = self.key(url, params)
        if composite in self.fixtures:
            return self.fixtures[composite]
        if url in self.fixtures:
            return self.fixtures[url]
        if self.strict:
            raise ConnectorError(
                f"No fixture registered for {composite}. "
                f"Known fixtures: {sorted(self.fixtures)[:5]}"
            )
        return {}


# ---------------------------------------------------------------------------------------------
# Licence enforcement
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LicenceTerms:
    """Structured licence position for a provider, declared in code and persisted at registration."""

    identifier: str
    url: str | None
    commercial_use_permitted: bool
    redistribution_permitted: bool
    attribution_required: bool
    attribution_text: str
    note: str | None = None


def assert_ingest_permitted(provider: SourceProvider, *, commercial_context: bool = True) -> None:
    """Refuse to ingest from a provider whose licence has not been cleared for this use.

    Checked at ingest rather than at export because discovering at dossier-generation time that
    half the evidence cannot be redistributed is discovering it far too late to do anything about.
    """
    if provider.commercial_use_permitted is None:
        raise LicenceError(
            f"LICENCE_NOT_REVIEWED: provider '{provider.key}' has no recorded licence position. "
            "Record one before ingesting."
        )
    if commercial_context and not provider.commercial_use_permitted:
        raise LicenceError(
            f"COMMERCIAL_USE_NOT_PERMITTED: provider '{provider.key}' is licensed as "
            f"'{provider.license_identifier}', which does not permit commercial use."
        )


# ---------------------------------------------------------------------------------------------
# Connector base
# ---------------------------------------------------------------------------------------------
@dataclass
class FetchResult:
    """Raw records plus everything needed to reproduce the fetch later."""

    records: list[dict[str, Any]]
    provider_version: str | None
    query_descriptor: dict[str, Any]
    is_reproducible: bool = True
    reproducibility_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Connector(ABC):
    """Base class for every external data connector.

    Subclasses implement `fetch` (talk to the provider) and `normalize` (map one raw record onto
    TinkerLab's vocabulary). The base class owns snapshotting, licence enforcement and checksums so
    those cannot be forgotten in an individual connector.
    """

    key: str = ""
    display_name: str = ""
    provider_type: str = "external_api"
    connector_version: str = "1.0"
    licence: LicenceTerms | None = None
    default_rate_limit: float | None = None

    def __init__(self, transport: Transport | None = None, *, api_key: str | None = None) -> None:
        self.transport = transport or HttpTransport(
            rate_limiter=RateLimiter(per_second=self.default_rate_limit)
        )
        self.api_key = api_key

    # -- provider registration ------------------------------------------------------------------
    def ensure_provider(self, db: Session) -> SourceProvider:
        """Create or update the provider row, writing the licence position declared in code."""
        if self.licence is None:
            raise LicenceError(
                f"Connector '{self.key}' declares no licence terms and cannot be registered."
            )
        provider = db.query(SourceProvider).filter_by(key=self.key).one_or_none()
        if provider is None:
            provider = SourceProvider(key=self.key, display_name=self.display_name,
                                      provider_type=self.provider_type)
            db.add(provider)
        provider.display_name = self.display_name
        provider.provider_type = self.provider_type
        provider.adapter_version = self.connector_version
        provider.reference_url = self.licence.url
        provider.rate_limit_per_second = self.default_rate_limit

        # Connector declarations are the default review position, not authority to erase a human
        # compliance decision. A connector-managed row is refreshed on every registration; a row
        # explicitly reviewed by a person remains authoritative until that reviewer changes it.
        connector_managed = (
            provider.license_reviewed_by is None
            or str(provider.license_reviewed_by).startswith("connector:")
        )
        if connector_managed:
            provider.license_identifier = self.licence.identifier
            provider.license_url = self.licence.url
            provider.commercial_use_permitted = self.licence.commercial_use_permitted
            provider.redistribution_permitted = self.licence.redistribution_permitted
            provider.attribution_required = self.licence.attribution_required
            provider.attribution_text = self.licence.attribution_text
            provider.licensing_notes = self.licence.note
            provider.license_reviewed_at = datetime.now(UTC)
            provider.license_reviewed_by = f"connector:{self.key}@{self.connector_version}"
        db.flush()
        return provider

    # -- subclass contract ----------------------------------------------------------------------
    @abstractmethod
    def fetch(self, **query: Any) -> FetchResult:
        """Retrieve raw records from the provider."""

    @abstractmethod
    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        """Map one raw provider record onto TinkerLab's normalized shape."""

    def external_id(self, record: dict[str, Any]) -> str:
        """Stable provider-side identifier for a raw record."""
        return str(record.get("id") or checksum(record)[:24])

    # -- snapshotting ---------------------------------------------------------------------------
    def create_snapshot(
        self, db: Session, provider: SourceProvider, result: FetchResult, *,
        dataset_key: str, organisation_id: str | None = None,
    ) -> DatasetSnapshot:
        snapshot = DatasetSnapshot(
            provider_id=provider.id,
            organisation_id=organisation_id,
            dataset_key=dataset_key,
            provider_version=result.provider_version,
            query_descriptor=result.query_descriptor,
            record_count=len(result.records),
            connector_version=f"{self.key}/{self.connector_version}",
            content_checksum=checksum({
                "framework": CONNECTOR_FRAMEWORK_VERSION,
                "connector": f"{self.key}/{self.connector_version}",
                "dataset_key": dataset_key,
                "provider_version": result.provider_version,
                "query_descriptor": result.query_descriptor,
                "records": sorted(
                    ({"external_id": self.external_id(record), "raw_checksum": checksum(record)}
                     for record in result.records),
                    key=lambda row: (str(row["external_id"]), str(row["raw_checksum"])),
                ),
            }),
            is_reproducible=result.is_reproducible,
            reproducibility_note=result.reproducibility_note,
            metadata_json=result.metadata,
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    def run(
        self, db: Session, *, dataset_key: str, organisation_id: str | None = None,
        commercial_context: bool = True, **query: Any,
    ) -> tuple[DatasetSnapshot, list[dict[str, Any]]]:
        """Full ingest cycle: licence check, fetch, snapshot, normalise."""
        provider = self.ensure_provider(db)
        assert_ingest_permitted(provider, commercial_context=commercial_context)
        result = self.fetch(**query)
        snapshot = self.create_snapshot(
            db, provider, result, dataset_key=dataset_key, organisation_id=organisation_id
        )
        normalized = []
        for record in result.records:
            mapped = self.normalize(record)
            mapped["_external_id"] = self.external_id(record)
            mapped["_raw_checksum"] = checksum(record)
            # Preserve the exact provider record separately from the normalized representation.
            # SourceRecord.raw_payload must be auditable raw input, not a second copy of normalized data.
            mapped["_raw_record"] = record
            normalized.append(mapped)
        return snapshot, normalized


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, type[Connector]] = {}

    def register(self, connector_cls: type[Connector]) -> type[Connector]:
        self._connectors[connector_cls.key] = connector_cls
        return connector_cls

    def get(self, key: str) -> type[Connector] | None:
        return self._connectors.get(key)

    def list_keys(self) -> list[str]:
        return sorted(self._connectors)


connector_registry = ConnectorRegistry()
