"""Phase 11 — Licence compliance for exported dossiers.

A technical dossier is the artefact a customer files with a regulator or hands to their own
customer. It is the moment TinkerLab's output leaves TinkerLab's control.

If that document embeds data whose licence forbids redistribution, the customer has been handed a
liability by a product that sells defensibility. That is the single worst failure mode available to
this platform, and it is entirely preventable — so it is prevented here, structurally, rather than
left to whoever is assembling the export to remember.

Two outputs:

`licence_audit` walks every piece of evidence a dossier draws on and resolves it to a provider
licence, refusing to guess when a provider has no recorded position.

`attribution_block` produces the credits section that CC-BY and similar licences require. Materials
Project data, for instance, is freely usable commercially — but only with attribution, and an
unattributed dossier is a licence breach even though the data was free.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    DatasetSnapshot,
    Evidence,
    IndustrialEvidence,
    MaterialPropertyObservation,
    SourceProvider,
    SourceRecord,
)

LICENCE_AUDIT_METHODOLOGY = "licence-audit-v1"


class LicenceComplianceError(RuntimeError):
    """Raised when a dossier cannot be exported without breaching a data licence."""


def _provider_position(provider: SourceProvider | None) -> dict[str, Any]:
    if provider is None:
        return {
            "provider_key": None, "license_identifier": None,
            "commercial_use_permitted": None, "redistribution_permitted": None,
            "attribution_required": False, "status": "NO_PROVIDER",
        }
    if provider.commercial_use_permitted is None:
        status = "UNREVIEWED"
    elif not provider.commercial_use_permitted:
        status = "COMMERCIAL_USE_FORBIDDEN"
    elif provider.redistribution_permitted is False:
        status = "REDISTRIBUTION_RESTRICTED"
    else:
        status = "CLEARED"
    return {
        "provider_key": provider.key,
        "provider_name": provider.display_name,
        "license_identifier": provider.license_identifier,
        "license_url": provider.license_url,
        "commercial_use_permitted": provider.commercial_use_permitted,
        "redistribution_permitted": provider.redistribution_permitted,
        "attribution_required": provider.attribution_required,
        "attribution_text": provider.attribution_text,
        "status": status,
    }


def _evidence_rows_for_references(db: Session, reference_ids: list[str]) -> tuple[list[Evidence], list[IndustrialEvidence]]:
    if not reference_ids:
        return [], []
    direct = db.query(Evidence).filter(Evidence.id.in_(reference_ids)).all()
    via_observation = (
        db.query(Evidence)
        .join(MaterialPropertyObservation, MaterialPropertyObservation.evidence_id == Evidence.id)
        .filter(MaterialPropertyObservation.id.in_(reference_ids))
        .all()
    )
    industrial = db.query(IndustrialEvidence).filter(IndustrialEvidence.id.in_(reference_ids)).all()
    evidence_by_id = {row.id: row for row in direct + via_observation}
    # Older Phase-11 rows stored the parent evidence id only in metadata. Preserve auditability for
    # those rows while newer ingestion also writes source_record_id directly.
    metadata_evidence_ids = [
        str((row.metadata_json or {}).get("evidence_id")) for row in industrial
        if not row.source_record_id and (row.metadata_json or {}).get("evidence_id")
    ]
    if metadata_evidence_ids:
        for row in db.query(Evidence).filter(Evidence.id.in_(metadata_evidence_ids)).all():
            evidence_by_id[row.id] = row
    return list(evidence_by_id.values()), industrial


def licence_audit(db: Session, *, evidence_ids: list[str]) -> dict[str, Any]:
    """Resolve every referenced scientific or industrial row to its provider licence position."""
    providers_seen: dict[str, dict[str, Any]] = {}
    blocked_refs: list[str] = []
    evidence_rows, industrial_rows = _evidence_rows_for_references(db, evidence_ids)

    def record_provider(provider: SourceProvider | None, reference_id: str) -> None:
        if provider is None:
            return
        position = _provider_position(provider)
        key = str(position["provider_key"])
        providers_seen.setdefault(key, {**position, "evidence_count": 0})
        providers_seen[key]["evidence_count"] += 1
        if position["status"] in {
            "UNREVIEWED", "COMMERCIAL_USE_FORBIDDEN", "REDISTRIBUTION_RESTRICTED"
        }:
            blocked_refs.append(reference_id)

    for evidence in evidence_rows:
        if evidence.provider_id is not None:
            record_provider(db.get(SourceProvider, evidence.provider_id), evidence.id)

    for industrial in industrial_rows:
        if not industrial.source_record_id:
            continue
        source_record = db.get(SourceRecord, industrial.source_record_id)
        if source_record is not None:
            record_provider(db.get(SourceProvider, source_record.provider_id), industrial.id)

    blocking = [
        position for position in providers_seen.values()
        if position["status"] in {
            "UNREVIEWED", "COMMERCIAL_USE_FORBIDDEN", "REDISTRIBUTION_RESTRICTED"
        }
    ]
    restricted = [
        position for position in providers_seen.values()
        if position["status"] == "REDISTRIBUTION_RESTRICTED"
    ]

    return {
        "providers": sorted(providers_seen.values(), key=lambda p: str(p["provider_key"])),
        "blocking": blocking,
        "restricted": restricted,
        "blocked_evidence_ids": sorted(set(blocked_refs)),
        "export_permitted": not blocking,
        "methodology_version": LICENCE_AUDIT_METHODOLOGY,
        "note": (
            "Providers marked REDISTRIBUTION_RESTRICTED may be used internally, but an export "
            "containing their records is blocked until redistribution rights are explicitly cleared."
        ),
    }


def referenced_snapshot_ids(db: Session, *, evidence_ids: list[str]) -> list[str]:
    """Return only dataset snapshots transitively referenced by the supplied dossier evidence."""
    evidence_rows, industrial_rows = _evidence_rows_for_references(db, evidence_ids)
    snapshot_ids = {
        str(row.dataset_snapshot_id) for row in evidence_rows if row.dataset_snapshot_id
    }
    source_record_ids = {
        str(row.source_record_id) for row in industrial_rows if row.source_record_id
    }
    if source_record_ids:
        for row in db.query(SourceRecord).filter(SourceRecord.id.in_(source_record_ids)).all():
            if row.dataset_snapshot_id:
                snapshot_ids.add(str(row.dataset_snapshot_id))
    return sorted(snapshot_ids)

def attribution_block(db: Session, *, evidence_ids: list[str]) -> dict[str, Any]:
    """The credits section that attribution-required licences oblige a dossier to carry."""
    audit = licence_audit(db, evidence_ids=evidence_ids)
    entries = [
        {
            "provider": position["provider_name"],
            "license": position["license_identifier"],
            "license_url": position["license_url"],
            "attribution": position["attribution_text"],
            "records_used": position["evidence_count"],
        }
        for position in audit["providers"]
        if position.get("attribution_required") and position.get("attribution_text")
    ]
    return {
        "entries": entries,
        "statement": (
            "This dossier incorporates data from the sources listed above, used under the licences "
            "stated. TinkerLab asserts no ownership over third-party data."
            if entries else
            "This dossier incorporates no third-party licensed data requiring attribution."
        ),
        "methodology_version": LICENCE_AUDIT_METHODOLOGY,
    }


def snapshot_manifest(db: Session, *, snapshot_ids: list[str]) -> dict[str, Any]:
    """Which external dataset versions this dossier was computed against.

    Determinism is the platform's core claim. External data can break it silently, so a dossier
    states which release it used — and flags, rather than hides, the snapshots that could not be
    pinned to a provider version.
    """
    snapshots = (
        db.query(DatasetSnapshot).filter(DatasetSnapshot.id.in_(snapshot_ids)).all()
        if snapshot_ids else []
    )
    rows = [
        {
            "snapshot_id": snapshot.id,
            "dataset_key": snapshot.dataset_key,
            "provider_version": snapshot.provider_version,
            "retrieved_at": snapshot.retrieved_at,
            "record_count": snapshot.record_count,
            "connector_version": snapshot.connector_version,
            "content_checksum": snapshot.content_checksum,
            "is_reproducible": snapshot.is_reproducible,
            "reproducibility_note": snapshot.reproducibility_note,
        }
        for snapshot in snapshots
    ]
    rows.sort(key=lambda r: (str(r["dataset_key"]), str(r["snapshot_id"])))
    unpinned = [r for r in rows if not r["is_reproducible"]]
    return {
        "snapshots": rows,
        "unpinned_count": len(unpinned),
        "fully_reproducible": not unpinned,
        "note": (
            "Every external dataset used is listed with the provider version it was retrieved at. "
            + (
                f"{len(unpinned)} dataset(s) could not be pinned to a provider version; those "
                "sources may return different records in future and should be re-checked before "
                "any regulatory filing."
                if unpinned else
                "All external datasets are pinned to a provider version."
            )
        ),
        "methodology_version": LICENCE_AUDIT_METHODOLOGY,
    }
