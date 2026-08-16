from __future__ import annotations

from enum import StrEnum
from typing import Any


class EvidenceTier(StrEnum):
    MEASURED_THIS_LOT = "MEASURED_THIS_LOT"
    MEASURED_EQUIVALENT = "MEASURED_EQUIVALENT"
    PEER_REVIEWED = "PEER_REVIEWED"
    HANDBOOK = "HANDBOOK"
    VENDOR_TYPICAL = "VENDOR_TYPICAL"
    PREDICTED = "PREDICTED"


class EvidenceTierStatus(StrEnum):
    ASSESSED = "ASSESSED"
    UNASSESSED = "UNASSESSED"
    NOT_SCIENTIFIC_EVIDENCE = "NOT_SCIENTIFIC_EVIDENCE"


class DistributionType(StrEnum):
    NORMAL = "normal"
    LOGNORMAL = "lognormal"
    UNIFORM = "uniform"
    WEIBULL = "weibull"
    POINT = "point"
    UNSPECIFIED = "unspecified"


class TemperatureStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


def classify_legacy_evidence_tier(
    *,
    evidence_type: str | None,
    source_quality: str | None,
    evidence_metadata: dict[str, Any] | None = None,
    material_source_type: str | None = None,
) -> tuple[EvidenceTier | None, EvidenceTierStatus, str]:
    """Conservatively classify legacy provenance without inventing evidence quality.

    The tier is deliberately nullable. Unknown provenance is not a handbook value, and synthetic
    demonstration rows are not scientific evidence. This function never upgrades a generic
    experimental record to MEASURED_THIS_LOT unless explicit metadata identifies the exact lot.
    """
    metadata = evidence_metadata or {}
    data_grade = str(metadata.get("data_grade") or "").strip().lower()
    evidence_type = str(evidence_type or "").strip().lower()
    source_quality = str(source_quality or "").strip().lower()
    material_source_type = str(material_source_type or "").strip().lower()

    if evidence_type in {"seed_demo", "seed_demonstration", "demonstration"} or metadata.get("demo_only") is True:
        return None, EvidenceTierStatus.NOT_SCIENTIFIC_EVIDENCE, "synthetic/demonstration evidence is excluded from scientific tiering"

    if data_grade == "handbook_typical" or source_quality == "handbook_typical" or material_source_type == "reference_library":
        return EvidenceTier.HANDBOOK, EvidenceTierStatus.ASSESSED, "legacy provenance explicitly identifies a handbook/reference typical value"
    if data_grade == "supplier_datasheet" or source_quality == "supplier_declared" or evidence_type in {"supplier", "vendor"}:
        return EvidenceTier.VENDOR_TYPICAL, EvidenceTierStatus.ASSESSED, "supplier/vendor typical provenance"
    if data_grade == "published_literature" or source_quality == "peer_reviewed":
        return EvidenceTier.PEER_REVIEWED, EvidenceTierStatus.ASSESSED, "peer-reviewed provenance"
    if evidence_type in {"computed_database", "prediction", "predicted", "dft", "ml_prediction"}:
        return EvidenceTier.PREDICTED, EvidenceTierStatus.ASSESSED, "computed or predicted provenance"
    if evidence_type == "experimental" or data_grade in {"accredited_laboratory", "internal_measurement"}:
        if metadata.get("exact_lot") is True or metadata.get("measured_this_lot") is True:
            return EvidenceTier.MEASURED_THIS_LOT, EvidenceTierStatus.ASSESSED, "explicit metadata binds measurement to the candidate lot"
        return EvidenceTier.MEASURED_EQUIVALENT, EvidenceTierStatus.ASSESSED, "experimental provenance exists but exact-lot identity is not proven"

    return None, EvidenceTierStatus.UNASSESSED, "legacy provenance cannot be mapped honestly to a Phase-13 tier"


def tier_can_satisfy_blocking_gate(tier: EvidenceTier | str | None) -> bool:
    """Phase-13 invariant: a prediction alone is never blocking-gate evidence."""
    if tier is None:
        return False
    try:
        parsed = EvidenceTier(str(tier))
    except ValueError:
        return False
    return parsed is not EvidenceTier.PREDICTED
