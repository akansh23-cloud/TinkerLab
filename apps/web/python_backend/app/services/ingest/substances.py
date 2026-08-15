"""Phase 11 — Substance identity and regulatory connectors.

`PubChemConnector` resolves substance identity: name, CAS, InChIKey, SMILES. Identity resolution is
unglamorous and it is the join on which everything else depends — a regulatory list keyed on CAS is
useless if the candidate is stored under a trade name.

`CompToxConnector` pulls EPA's curated regulatory lists. This is the connector that makes the
Essential Use story demonstrable rather than merely arguable: it is what lets a programme state that
an incumbent appears on a PFAS list, and that a proposed replacement does not.

A deliberate boundary: neither connector decides anything. A regulatory list membership becomes
`IndustrialEvidence` for the Phase-7 `regulatory` dimension, which the Phase-10 gate then evaluates.
Appearing on a list is evidence, not a verdict — an exemption or an essential-use derogation can
still apply, and only a human reviewing the specific application can determine that.
"""

from __future__ import annotations

from typing import Any

from app.services.ingest.base import (
    Connector,
    ConnectorError,
    FetchResult,
    LicenceTerms,
    connector_registry,
)


@connector_registry.register
class PubChemConnector(Connector):
    """Substance identity resolution via PubChem PUG-REST."""

    key = "pubchem"
    display_name = "PubChem (NIH/NLM)"
    provider_type = "external_api"
    connector_version = "1.0"
    # PubChem asks for no more than roughly five requests per second. Exceeding it gets the calling
    # IP throttled, which in a shared deployment penalises every tenant at once.
    default_rate_limit = 4.0

    licence = LicenceTerms(
        identifier="public-domain",
        url="https://www.ncbi.nlm.nih.gov/home/about/policies/",
        commercial_use_permitted=True,
        redistribution_permitted=True,
        attribution_required=False,
        attribution_text="Chemical identity data from PubChem (NIH/NLM).",
        note=(
            "PubChem aggregates depositor records; individual depositor data may carry its own "
            "terms even though the PubChem compilation does not."
        ),
    )

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    IDENTITY_PROPERTIES = (
        "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,IUPACName"
    )

    def fetch(self, **query: Any) -> FetchResult:
        namespace = query.get("namespace", "name")
        identifier = query.get("identifier")
        if not identifier:
            raise ConnectorError("PubChem requires an `identifier`")
        if namespace not in {"name", "cid", "smiles", "inchikey", "formula"}:
            raise ConnectorError(f"Unsupported PubChem namespace: {namespace}")

        url = (
            f"{self.BASE_URL}/compound/{namespace}/{identifier}/property/"
            f"{self.IDENTITY_PROPERTIES}/JSON"
        )
        payload = self.transport.get_json(url)
        properties = (payload.get("PropertyTable") or {}).get("Properties")
        if not isinstance(properties, list):
            raise ConnectorError("PubChem response contained no PropertyTable")

        return FetchResult(
            records=[r for r in properties if isinstance(r, dict)],
            # PubChem exposes no global dataset version on this endpoint. Recording that honestly
            # is better than inventing a pin we cannot honour.
            provider_version=None,
            query_descriptor={"endpoint": url, "namespace": namespace, "identifier": identifier},
            is_reproducible=False,
            reproducibility_note=(
                "PubChem does not expose a dataset version on the PUG-REST property endpoint. "
                "Records are pinned by CID and retrieval timestamp only."
            ),
            metadata={"namespace": namespace, "identifier": str(identifier)},
        )

    def external_id(self, record: dict[str, Any]) -> str:
        return f"CID{record.get('CID', 'unknown')}"

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        identifiers = []
        if record.get("CID") is not None:
            identifiers.append({"namespace": "pubchem_cid", "value": str(record["CID"]), "is_primary": True})
        for scheme, key in (("inchikey", "InChIKey"), ("inchi", "InChI"), ("smiles", "CanonicalSMILES")):
            if record.get(key):
                identifiers.append({"namespace": scheme, "value": str(record[key]), "is_primary": False})

        observations = []
        weight = record.get("MolecularWeight")
        if weight is not None:
            try:
                observations.append({
                    "property_key": "molar_mass",
                    "numeric_value": float(weight),
                    "unit": "g/mol",
                    "conditions": {},
                    "origin": "database_reference",
                    # Molecular weight here is a provider reference/derived property. It is not
                    # promoted to an experimental measurement merely because PubChem reports it.
                    "computed": None,
                })
            except (TypeError, ValueError):
                pass

        return {
            "source": "pubchem",
            "external_id": str(record.get("CID")),
            "display_name": record.get("IUPACName") or f"CID {record.get('CID')}",
            "chemical_formula": record.get("MolecularFormula"),
            "identifiers": identifiers,
            "observations": observations,
        }


@connector_registry.register
class CompToxConnector(Connector):
    """Regulatory list membership from EPA's Computational Toxicology and Exposure APIs."""

    key = "epa_comptox"
    display_name = "EPA CompTox Chemicals Dashboard (CTX APIs)"
    provider_type = "external_api"
    connector_version = "1.0"
    default_rate_limit = 5.0

    licence = LicenceTerms(
        identifier="US-Gov-Public-Domain",
        url="https://www.epa.gov/comptox-tools/computational-toxicology-and-exposure-apis",
        commercial_use_permitted=True,
        redistribution_permitted=True,
        attribution_required=True,
        attribution_text=(
            "Regulatory list data from the U.S. EPA CompTox Chemicals Dashboard (CTX APIs)."
        ),
        note=(
            "EPA states these data are free of copyright restriction and available for both "
            "non-commercial and commercial use. A free API key is required."
        ),
    )

    BASE_URL = "https://api-ccte.epa.gov"

    # Lists that matter to a material-replacement programme. Membership is evidence for the
    # Phase-7 `regulatory` dimension, never an automatic rejection.
    PRIORITY_LISTS: dict[str, str] = {
        "PFASMASTER": "EPA PFAS master list",
        "PFASSTRUCT": "PFAS by structure definition",
        "TSCA_ACTIVE_NCTE_0219": "TSCA active inventory",
        "EPAPCS": "EPA priority chemicals",
    }

    def fetch(self, **query: Any) -> FetchResult:
        if not self.api_key:
            raise ConnectorError(
                "EPA CTX requires an API key. Request a free key from ccte_api@epa.gov"
            )
        mode = query.get("mode", "by_dtxsid")

        if mode == "by_dtxsid":
            dtxsid = query.get("dtxsid")
            if not dtxsid:
                raise ConnectorError("CompTox `by_dtxsid` mode requires a `dtxsid`")
            url = f"{self.BASE_URL}/chemical/list/search/by-dtxsid/{dtxsid}"
        elif mode == "list_contents":
            list_name = query.get("list_name")
            if not list_name:
                raise ConnectorError("CompTox `list_contents` mode requires a `list_name`")
            url = f"{self.BASE_URL}/chemical/list/search/by-name/{list_name}"
        else:
            raise ConnectorError(f"Unsupported CompTox mode: {mode}")

        payload = self.transport.get_json(url, headers={"x-api-key": self.api_key})
        # This endpoint family returns either a bare array or an object wrapping one.
        if isinstance(payload, list):
            records: list[Any] = payload
        elif isinstance(payload, dict):
            records = payload.get("data") or payload.get("results") or [payload]
        else:
            raise ConnectorError("Unexpected CompTox response shape")

        normalized_records = [
            r if isinstance(r, dict) else {"listName": str(r)} for r in records
        ]

        return FetchResult(
            records=normalized_records,
            provider_version=None,
            query_descriptor={"endpoint": url, "mode": mode,
                              **{k: v for k, v in query.items() if k != "mode"}},
            is_reproducible=False,
            reproducibility_note=(
                "EPA list membership changes as lists are revised and does not carry a per-request "
                "version. Pin by retrieval date and re-check before any regulatory filing."
            ),
            metadata={"mode": mode, "record_count": len(normalized_records)},
        )

    def external_id(self, record: dict[str, Any]) -> str:
        # A list is not a substance. Keep the chemical identity load-bearing and include the list
        # name only to distinguish multiple membership records for the same DTXSID.
        dtxsid = str(record.get("dtxsid") or "").strip()
        list_name = str(record.get("listName") or record.get("label") or "").strip()
        if dtxsid and list_name:
            return f"{dtxsid}:{list_name}"
        return dtxsid or list_name or "unknown"

    def normalize(self, record: dict[str, Any]) -> dict[str, Any]:
        list_name = str(record.get("listName") or record.get("label") or "")
        is_priority = list_name.upper() in self.PRIORITY_LISTS
        is_pfas = "PFAS" in list_name.upper()

        dtxsid = str(record.get("dtxsid") or "").strip() or None
        substance_name = (
            record.get("preferredName") or record.get("preferred_name") or record.get("chemicalName")
            or record.get("chemical_name") or dtxsid or "Unknown EPA substance"
        )
        return {
            "source": "epa_comptox",
            "external_id": dtxsid or list_name,
            "display_name": str(substance_name),
            "identifiers": ([{"namespace": "dtxsid", "value": dtxsid, "is_primary": True}] if dtxsid else []),
            "list_name": list_name,
            "list_description": record.get("listDescription") or self.PRIORITY_LISTS.get(
                list_name.upper()
            ),
            "dtxsid": dtxsid,
            "is_priority_list": is_priority,
            "indicates_pfas": is_pfas,
            # Deliberately expressed as evidence for a dimension, not as a verdict. An exemption or
            # an essential-use derogation may still apply, and only a human assessing the specific
            # application can determine that.
            "industrial_evidence": [{
                "category": "regulatory",
                "metric_key": "regulatory_list_membership",
                "display_label": f"Listed on {list_name}" if list_name else "Regulatory listing",
                "boolean_value": True,
                "jurisdiction": "US",
                "geography": "US",
                "source_type": "regulatory_authority",
                "notes": (
                    "Presence on a regulatory list is evidence for review, not an automatic "
                    "rejection. Exemptions and essential-use derogations may apply."
                ),
            }],
            "observations": [],
        }
