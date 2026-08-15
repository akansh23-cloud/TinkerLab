"""Phase 11 — Structural and computed-property connectors.

Two connectors with deliberately different jobs:

`OptimadeConnector` federates across the OPTIMADE network — one filter grammar over roughly two
dozen providers. It is the cheapest way to widen candidate coverage, and because it is a *standard*
rather than a vendor API, adding a provider is configuration rather than code.

`MaterialsProjectConnector` goes deep on one provider that OPTIMADE only exposes shallowly.
OPTIMADE standardises structure, not properties; band gaps, formation energies and elastic tensors
need the native API.

Neither connector ever writes a property value without attaching the computational method that
produced it. See `methods.py` for why that matters more than it might appear.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import SourceProvider

from app.services.ingest.base import (
    Connector,
    ConnectorError,
    FetchResult,
    LicenceTerms,
    connector_registry,
)

# OPTIMADE standardises these structural fields across every provider.
OPTIMADE_RESPONSE_FIELDS = (
    "chemical_formula_reduced,chemical_formula_descriptive,chemical_formula_anonymous,"
    "elements,nelements,nsites,lattice_vectors,cartesian_site_positions,species_at_sites,"
    "structure_features,last_modified"
)


@connector_registry.register
class OptimadeConnector(Connector):
    """Federated structure search across the OPTIMADE network."""

    key = "optimade"
    display_name = "OPTIMADE federated materials databases"
    provider_type = "federated_api"
    connector_version = "1.0"
    default_rate_limit = 2.0

    # Licence is per-provider, which the federation does not harmonise. This connector therefore
    # records the *federation* position and requires the caller to name the sub-provider, whose
    # own terms are captured in the snapshot metadata.
    licence = LicenceTerms(
        identifier="per-provider",
        url="https://providers.optimade.org/",
        commercial_use_permitted=True,
        redistribution_permitted=False,
        attribution_required=True,
        attribution_text=(
            "Structural data retrieved via the OPTIMADE API. Individual records remain subject to "
            "the licence of the originating database."
        ),
        note=(
            "OPTIMADE is a specification, not a licensor. Each provider sets its own terms; "
            "redistribution is therefore marked not-permitted by default and must be cleared "
            "per sub-provider before any record reaches a customer deliverable."
        ),
    )

    # Providers whose terms have been individually reviewed. Anything not on this list is fetched
    # but flagged, because an unreviewed licence is not the same as a permissive one.
    REVIEWED_SUBPROVIDERS: dict[str, str] = {
        "mp": "CC-BY-4.0",
        "cod": "CC0-1.0",
        "oqmd": "CC-BY-4.0",
        "aflow": "CC-BY-4.0",
        "jarvis": "US-Gov-Public-Domain",
        "nmd": "CC-BY-4.0",
        "mcloud": "CC-BY-4.0",
        "alexandria": "CC-BY-4.0",
    }

    def __init__(self, transport=None, *, base_url: str, provider_id: str = "unknown", **kwargs):
        super().__init__(transport, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.provider_id = provider_id

    def ensure_provider(self, db: Session) -> SourceProvider:
        """Register the originating OPTIMADE database, not the federation, as the licensor.

        OPTIMADE standardises an API; it does not grant rights to the underlying records. Unknown
        sub-provider terms therefore remain unreviewed and are blocked by the common ingest gate.
        """
        provider_key = f"optimade:{self.provider_id}"
        provider = db.query(SourceProvider).filter_by(key=provider_key).one_or_none()
        if provider is None:
            provider = SourceProvider(
                key=provider_key,
                display_name=f"OPTIMADE provider {self.provider_id}",
                provider_type=self.provider_type,
            )
            db.add(provider)
        provider.display_name = f"OPTIMADE provider {self.provider_id}"
        provider.provider_type = self.provider_type
        provider.adapter_version = self.connector_version
        provider.reference_url = self.base_url
        provider.rate_limit_per_second = self.default_rate_limit

        connector_managed = (
            provider.license_reviewed_by is None
            or str(provider.license_reviewed_by).startswith("connector:")
        )
        if connector_managed:
            reviewed_licence = self.REVIEWED_SUBPROVIDERS.get(self.provider_id)
            provider.license_identifier = reviewed_licence
            provider.license_url = self.licence.url
            provider.commercial_use_permitted = True if reviewed_licence else None
            provider.redistribution_permitted = True if reviewed_licence else None
            provider.attribution_required = True
            provider.attribution_text = (
                f"Structural data retrieved from OPTIMADE provider '{self.provider_id}'. "
                f"Originating licence: {reviewed_licence}." if reviewed_licence else
                f"Structural data retrieved from OPTIMADE provider '{self.provider_id}'. "
                "Licence requires curator review before ingestion."
            )
            provider.licensing_notes = self.licence.note
            provider.license_reviewed_at = datetime.now(UTC) if reviewed_licence else None
            provider.license_reviewed_by = (
                f"connector:{self.key}@{self.connector_version}" if reviewed_licence else None
            )
        db.flush()
        return provider

    @staticmethod
    def _dataset_version(meta: dict[str, Any]) -> str | None:
        """Use only explicit dataset/database release fields; never OPTIMADE `api_version`."""
        provider_meta = meta.get("provider") or {}
        for container in (meta, provider_meta):
            for key in ("database_version", "db_version", "dataset_version", "data_version"):
                value = container.get(key) if isinstance(container, dict) else None
                if value:
                    return str(value)
        return None

    def fetch(self, **query: Any) -> FetchResult:
        filter_expression = query.get("filter")
        if not filter_expression:
            raise ConnectorError("OPTIMADE requires a `filter` expression")
        page_limit = max(1, min(int(query.get("page_limit", 50)), 500))
        max_pages = max(1, min(int(query.get("max_pages", 100)), 1000))

        params = {
            "filter": filter_expression,
            "page_limit": page_limit,
            "response_fields": query.get("response_fields", OPTIMADE_RESPONSE_FIELDS),
        }
        endpoint = f"{self.base_url}/v1/structures"
        payload = self.transport.get_json(endpoint, params=params)
        if not isinstance(payload, dict):
            raise ConnectorError("OPTIMADE response was not a JSON object")

        records: list[dict[str, Any]] = []
        first_meta = payload.get("meta") or {}
        complete = True
        page_count = 0
        seen_next: set[str] = set()
        current = payload
        while True:
            page_count += 1
            data = current.get("data")
            if not isinstance(data, list):
                raise ConnectorError("OPTIMADE response contained no `data` array")
            records.extend(r for r in data if isinstance(r, dict))

            meta = current.get("meta") or {}
            more = bool(meta.get("more_data_available"))
            links = current.get("links") or {}
            next_link = links.get("next") if isinstance(links, dict) else None
            if isinstance(next_link, dict):
                next_link = next_link.get("href")
            if not more and not next_link:
                break
            if page_count >= max_pages:
                complete = False
                break
            if not next_link:
                # The spec says more data exists but provides no traversable next link. Do not
                # pretend this partial response is a complete snapshot.
                complete = False
                break
            next_url = str(next_link)
            if next_url in seen_next:
                complete = False
                break
            seen_next.add(next_url)
            current = self.transport.get_json(next_url)
            if not isinstance(current, dict):
                raise ConnectorError("OPTIMADE pagination returned a non-object response")

        api_version = str(first_meta.get("api_version") or "") or None
        provider_meta = first_meta.get("provider") or {}
        version = self._dataset_version(first_meta)
        licence = self.REVIEWED_SUBPROVIDERS.get(self.provider_id)
        reproducible = bool(version) and complete
        notes: list[str] = []
        if not version:
            notes.append(
                "This OPTIMADE provider exposes no explicit dataset/database version; api_version "
                "identifies the API implementation and is not a dataset pin."
            )
        if not complete:
            notes.append("The provider indicated additional records but the full result set was not retrieved.")

        return FetchResult(
            records=records,
            provider_version=version,
            query_descriptor={
                "endpoint": endpoint, "filter": filter_expression, "page_limit": page_limit,
                "max_pages": max_pages, "response_fields": params["response_fields"],
                "sub_provider": self.provider_id,
            },
            is_reproducible=reproducible,
            reproducibility_note=" ".join(notes) or None,
            metadata={
                "sub_provider": self.provider_id,
                "sub_provider_licence": licence or "UNREVIEWED",
                "licence_reviewed": licence is not None,
                "provider_meta": provider_meta,
                "api_version": api_version,
                "pages_retrieved": page_count,
                "data_returned": len(records),
                "complete_result_set": complete,
            },
        )

    def external_id(self, record: dict[str, Any]) -> str:
        return f"{self.provider_id}:{record.get('id', 'unknown')}"

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        attributes = record.get("attributes") or {}
        elements = attributes.get("elements") or []
        chemical_formula = (
            attributes.get("chemical_formula_reduced")
            or attributes.get("chemical_formula_descriptive")
        )
        display_formula = chemical_formula or attributes.get("chemical_formula_anonymous")
        lattice = attributes.get("lattice_vectors")

        return {
            "source": "optimade",
            "sub_provider": self.provider_id,
            "external_id": record.get("id"),
            "display_name": display_formula or str(record.get("id")),
            "chemical_formula": chemical_formula,
            "formula_is_anonymous": chemical_formula is None and bool(attributes.get("chemical_formula_anonymous")),
            "elements": list(elements),
            "identifiers": [{
                "namespace": "materials_project" if self.provider_id == "mp" else f"optimade_{self.provider_id}",
                "value": str(record.get("id")),
                "is_primary": True,
            }] if record.get("id") is not None else [],
            "n_elements": attributes.get("nelements"),
            "n_sites": attributes.get("nsites"),
            "lattice_vectors": lattice,
            "site_positions": attributes.get("cartesian_site_positions"),
            "species_at_sites": attributes.get("species_at_sites"),
            "structure_features": attributes.get("structure_features") or [],
            "last_modified": attributes.get("last_modified"),
            # OPTIMADE carries structure, not properties. Property ingestion is a separate,
            # provider-native concern — see MaterialsProjectConnector.
            "observations": [],
        }


# Materials Project field -> (TinkerLab property key, unit). Only fields whose unit is unambiguous
# in the MP schema are mapped; anything requiring interpretation is deliberately left out rather
# than guessed at.
MP_PROPERTY_MAP: dict[str, tuple[str, str]] = {
    "band_gap": ("band_gap", "eV"),
    "formation_energy_per_atom": ("formation_energy_per_atom", "eV/atom"),
    "energy_above_hull": ("energy_above_hull", "eV/atom"),
    "density": ("density", "g/cm^3"),
    "bulk_modulus_vrh": ("bulk_modulus", "GPa"),
    "shear_modulus_vrh": ("shear_modulus", "GPa"),
    "total_magnetization": ("magnetic_moment", "bohr_magneton"),
}


@connector_registry.register
class MaterialsProjectConnector(Connector):
    """Computed properties and structures from the Materials Project."""

    key = "materials_project"
    display_name = "Materials Project"
    provider_type = "external_api"
    connector_version = "1.0"
    default_rate_limit = 3.0

    licence = LicenceTerms(
        identifier="CC-BY-4.0",
        url="https://next-gen.materialsproject.org/about/terms",
        commercial_use_permitted=True,
        redistribution_permitted=True,
        attribution_required=True,
        attribution_text=(
            "Data from the Materials Project (materialsproject.org), licensed under CC-BY 4.0."
        ),
        note=(
            "Attribution is mandatory on any derived output. The terms explicitly prohibit "
            "scraping the website; all access must go through the documented API."
        ),
    )

    BASE_URL = "https://api.materialsproject.org"

    def __init__(self, transport=None, *, api_key: str | None = None, base_url: str | None = None, **kwargs):
        super().__init__(transport, api_key=api_key, **kwargs)
        self.base_url = (base_url or self.BASE_URL).rstrip("/")

    def fetch(self, **query: Any) -> FetchResult:
        if not self.api_key:
            raise ConnectorError(
                "Materials Project requires an API key. Obtain one from "
                "https://next-gen.materialsproject.org/api"
            )
        max_records = max(1, min(int(query.get("max_records", query.get("limit", 5000))), 50000))
        page_size = max(1, min(int(query.get("page_size", min(max_records, 1000))), 1000))
        fields = query.get("fields", ",".join(
            ["material_id", "formula_pretty", "elements", "nelements", "symmetry",
             "is_stable", "theoretical", "database_IDs", "last_updated"]
            + list(MP_PROPERTY_MAP)
        ))
        base_params: dict[str, Any] = {"_limit": page_size, "_fields": fields}
        for key in ("formula", "elements", "chemsys", "material_ids", "band_gap_min", "band_gap_max"):
            if query.get(key) is not None:
                base_params[key] = query[key]

        endpoint = f"{self.base_url}/materials/summary/"
        records: list[dict[str, Any]] = []
        offset = 0
        first_meta: dict[str, Any] = {}
        total_doc: int | None = None
        complete = True
        while len(records) < max_records:
            params = dict(base_params)
            params["_skip"] = offset
            payload = self.transport.get_json(
                endpoint, params=params, headers={"X-API-KEY": self.api_key},
            )
            if not isinstance(payload, dict):
                raise ConnectorError("Materials Project response was not a JSON object")
            data = payload.get("data")
            if not isinstance(data, list):
                raise ConnectorError("Materials Project response contained no `data` array")
            if not first_meta:
                first_meta = payload.get("meta") or {}
                try:
                    total_doc = int(first_meta.get("total_doc")) if first_meta.get("total_doc") is not None else None
                except (TypeError, ValueError):
                    total_doc = None
            page = [r for r in data if isinstance(r, dict)]
            remaining = max_records - len(records)
            records.extend(page[:remaining])
            offset += len(data)
            if not data or (total_doc is not None and offset >= total_doc):
                break
            if len(data) < page_size and total_doc is None:
                break
            if len(records) >= max_records:
                complete = total_doc is not None and offset >= total_doc
                break

        meta = first_meta
        # `api_version` is software/API provenance. Only an explicit database/data release can pin
        # the upstream dataset.
        version = meta.get("db_version") or meta.get("database_version") or meta.get("data_version")
        if total_doc is not None and len(records) < total_doc:
            complete = False
        reproducible = bool(version) and complete
        notes: list[str] = []
        if not version:
            notes.append("No database version was returned; this snapshot is time-stamped, not pinned.")
        if not complete:
            notes.append(
                f"Result set was capped at {len(records)} of {total_doc if total_doc is not None else 'unknown'} records."
            )

        return FetchResult(
            records=records,
            provider_version=str(version) if version else None,
            query_descriptor={
                "endpoint": endpoint,
                "params": {k: v for k, v in base_params.items() if k != "_fields"},
                "fields": fields, "max_records": max_records, "page_size": page_size,
            },
            is_reproducible=reproducible,
            reproducibility_note=" ".join(notes) or None,
            metadata={
                "total_doc": total_doc, "api_version": meta.get("api_version"),
                "records_retrieved": len(records), "complete_result_set": complete,
            },
        )

    def external_id(self, record: dict[str, Any]) -> str:
        return str(record.get("material_id") or record.get("task_id") or "unknown")

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        symmetry = record.get("symmetry") or {}
        observations: list[dict[str, Any]] = []

        calculation_provenance = record.get("calculation_provenance") or {}
        for mp_field, (property_key, unit) in MP_PROPERTY_MAP.items():
            value = record.get(mp_field)
            nested_value: dict[str, Any] | None = value if isinstance(value, dict) else None
            if value is None:
                continue
            if isinstance(value, dict):  # elastic moduli and enriched values may arrive nested
                value = value.get("vrh") or value.get("value")
            if not isinstance(value, (int, float)):
                continue

            # The normalized contract supports property-specific calculation provenance. Some
            # provider endpoints aggregate values generated by different workflows; a record-level
            # method label is therefore not automatically copied onto every observation.
            property_provenance: dict[str, Any] = {}
            if isinstance(calculation_provenance, dict):
                candidate = calculation_provenance.get(mp_field) or calculation_provenance.get(property_key)
                if isinstance(candidate, dict):
                    property_provenance.update(candidate)
            if nested_value is not None:
                nested_method = nested_value.get("calculation_provenance") or nested_value.get("provenance")
                if isinstance(nested_method, dict):
                    property_provenance.update(nested_method)
                for descriptor in ("functional", "xc_functional", "run_type", "calc_type", "method"):
                    if nested_value.get(descriptor) is not None:
                        property_provenance[descriptor] = nested_value[descriptor]

            observations.append({
                "property_key": property_key,
                "numeric_value": float(value),
                "unit": unit,
                # Every computed value carries the conditions it was computed at. 0 K static
                # lattice is the honest description of a standard MP calculation.
                "conditions": {"temperature_k": 0.0, "pressure_pa": 0.0},
                "origin": "computed_database",
                "computed": True,
                "calculation_provenance": property_provenance,
            })

        return {
            "source": "materials_project",
            "external_id": record.get("material_id"),
            "display_name": record.get("formula_pretty") or record.get("material_id"),
            "chemical_formula": record.get("formula_pretty"),
            "elements": list(record.get("elements") or []),
            "identifiers": (
                [{"namespace": "materials_project", "value": str(record.get("material_id")), "is_primary": True}]
                if record.get("material_id") is not None else []
            ) + [
                {"namespace": str(namespace), "value": str(value), "is_primary": False}
                for namespace, values in (record.get("database_IDs") or {}).items()
                for value in (values if isinstance(values, list) else [values])
                if value is not None
            ],
            "n_elements": record.get("nelements"),
            "crystal_system": symmetry.get("crystal_system"),
            "space_group_symbol": symmetry.get("symbol"),
            "space_group_number": symmetry.get("number"),
            "is_stable": record.get("is_stable"),
            # `theoretical` marks a structure that has never been synthesised. A replacement
            # candidate that does not exist yet is a very different proposition from one that does,
            # and the portfolio must be able to tell them apart.
            "is_theoretical": bool(record.get("theoretical", False)),
            "external_database_ids": record.get("database_IDs") or {},
            "last_updated": record.get("last_updated"),
            # Preserve provider-level calculation descriptors if the selected endpoint exposes them.
            # Unknown method stays unknown downstream; it is never silently promoted to PBE.
            "run_type": record.get("run_type"),
            "calc_type": record.get("calc_type"),
            "functional": record.get("functional"),
            "xc_functional": record.get("xc_functional"),
            "calculation_provenance": record.get("calculation_provenance") or {},
            "observations": observations,
        }
