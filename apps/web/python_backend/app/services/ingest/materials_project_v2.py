"""Production-hardened Materials Project summary connector.

This adapter extends the Phase-11 connector with query filters that are useful for
materials screening, fixes the current SummaryDoc elastic-field mapping, and carries
Materials Project property-origin task identifiers into normalized provenance.

The adapter deliberately does not infer a DFT functional from a summary record. MP's
`origins` identify contributing property documents/tasks; functional/run-type evidence
must still come from the appropriate calculation/thermo endpoint before TinkerLab may
make a method-specific claim.
"""

from __future__ import annotations

from typing import Any

from app.services.ingest.base import ConnectorError, FetchResult, connector_registry
from app.services.ingest.structures import MaterialsProjectConnector as Phase11MaterialsProjectConnector

_RANGE_FILTERS = frozenset({
    "band_gap", "density", "energy_above_hull", "formation_energy_per_atom", "volume",
    "total_magnetization", "nsites", "nelements", "k_vrh", "g_vrh", "e_total", "e_ionic",
    "e_electronic", "efermi", "homogeneous_poisson", "universal_anisotropy",
})
_LIST_FILTERS = frozenset({"formula", "chemsys", "elements", "exclude_elements", "material_ids", "has_props"})
_BOOLEAN_FILTERS = frozenset({"is_stable", "theoretical", "is_metal", "is_gap_direct", "deprecated"})
_CONTROL_KEYS = frozenset({"max_records", "limit", "page_size", "fields"})

_DEFAULT_FIELDS = (
    "material_id,formula_pretty,elements,nelements,nsites,symmetry,is_stable,theoretical,"
    "database_IDs,last_updated,band_gap,formation_energy_per_atom,energy_above_hull,density,"
    "bulk_modulus,shear_modulus,total_magnetization,origins"
)

_ORIGIN_GROUP_FOR_PROPERTY = {
    "band_gap": "electronic_structure",
    "formation_energy_per_atom": "thermo",
    "energy_above_hull": "thermo",
    "bulk_modulus_vrh": "elasticity",
    "shear_modulus_vrh": "elasticity",
    "total_magnetization": "magnetism",
    "density": "structure",
}


def _csv(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(item) for item in value)
    return str(value)


def _validate_range(name: str, lower: Any, upper: Any) -> None:
    if lower is not None and not isinstance(lower, (int, float)):
        raise ConnectorError(f"Materials Project filter '{name}_min' must be numeric")
    if upper is not None and not isinstance(upper, (int, float)):
        raise ConnectorError(f"Materials Project filter '{name}_max' must be numeric")
    if lower is not None and upper is not None and float(lower) > float(upper):
        raise ConnectorError(
            f"Materials Project filter '{name}' has minimum {lower} greater than maximum {upper}"
        )


@connector_registry.register
class MaterialsProjectConnector(Phase11MaterialsProjectConnector):
    """Constraint-friendly Materials Project connector with strict query semantics."""

    connector_version = "1.1"

    def fetch(self, **query: Any) -> FetchResult:
        if not self.api_key:
            raise ConnectorError(
                "Materials Project requires an API key. Obtain one from "
                "https://next-gen.materialsproject.org/api"
            )

        allowed = set(_CONTROL_KEYS) | set(_LIST_FILTERS) | set(_BOOLEAN_FILTERS)
        for name in _RANGE_FILTERS:
            allowed.add(f"{name}_min")
            allowed.add(f"{name}_max")
        unknown = sorted(set(query) - allowed)
        if unknown:
            raise ConnectorError(
                "Unsupported Materials Project query parameter(s): " + ", ".join(unknown)
            )

        max_records = max(1, min(int(query.get("max_records", query.get("limit", 5000))), 50000))
        page_size = max(1, min(int(query.get("page_size", min(max_records, 1000))), 1000))
        fields = str(query.get("fields") or _DEFAULT_FIELDS)

        base_params: dict[str, Any] = {"_limit": page_size, "_fields": fields}
        for key in _LIST_FILTERS:
            value = query.get(key)
            if value is not None:
                base_params[key] = _csv(value)
        for key in _BOOLEAN_FILTERS:
            value = query.get(key)
            if value is not None:
                if not isinstance(value, bool):
                    raise ConnectorError(f"Materials Project filter '{key}' must be boolean")
                base_params[key] = value
        for name in _RANGE_FILTERS:
            lower = query.get(f"{name}_min")
            upper = query.get(f"{name}_max")
            _validate_range(name, lower, upper)
            if lower is not None:
                base_params[f"{name}_min"] = lower
            if upper is not None:
                base_params[f"{name}_max"] = upper

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
                endpoint,
                params=params,
                headers={"X-API-KEY": self.api_key},
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

            page = [row for row in data if isinstance(row, dict)]
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

        version = first_meta.get("db_version") or first_meta.get("database_version") or first_meta.get("data_version")
        if total_doc is not None and len(records) < total_doc:
            complete = False

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
                "fields": fields,
                "max_records": max_records,
                "page_size": page_size,
                "strict_filter_contract": True,
            },
            is_reproducible=bool(version) and complete,
            reproducibility_note=" ".join(notes) or None,
            metadata={
                "total_doc": total_doc,
                "api_version": first_meta.get("api_version"),
                "records_retrieved": len(records),
                "complete_result_set": complete,
                "screening_filter_count": len(base_params) - 2,
            },
        )

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(record)
        bulk = record.get("bulk_modulus")
        shear = record.get("shear_modulus")
        if isinstance(bulk, dict) and isinstance(bulk.get("vrh"), (int, float)):
            enriched["bulk_modulus_vrh"] = bulk["vrh"]
        if isinstance(shear, dict) and isinstance(shear.get("vrh"), (int, float)):
            enriched["shear_modulus_vrh"] = shear["vrh"]

        origins = record.get("origins") or []
        origin_by_name: dict[str, dict[str, Any]] = {}
        if isinstance(origins, list):
            for origin in origins:
                if not isinstance(origin, dict) or not origin.get("name"):
                    continue
                origin_by_name[str(origin["name"])] = {
                    "provider_origin_name": str(origin["name"]),
                    "task_id": str(origin["task_id"]) if origin.get("task_id") is not None else None,
                    "last_updated": origin.get("last_updated"),
                }

        provenance: dict[str, Any] = {}
        for property_key, group in _ORIGIN_GROUP_FOR_PROPERTY.items():
            if group in origin_by_name:
                provenance[property_key] = origin_by_name[group]
        enriched["calculation_provenance"] = provenance

        normalized = super().normalize(enriched)
        normalized["materials_project_origins"] = origins
        normalized["connector_contract"] = "materials-project-summary/1.1"
        return normalized
