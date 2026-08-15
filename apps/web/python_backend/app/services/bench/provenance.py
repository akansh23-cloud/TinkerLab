"""Evidence semantics shared by Phase 12.2 derivation and visualisation.

The evaluator's ``value_origin`` answers *how a value entered the decision* (known evidence,
prediction, simulation).  It is intentionally broad.  This module answers a different question:
*what kind of evidence is this and how directly should a reviewer treat it?*

The rank below is a presentation/derivation policy, not a universal claim that one scientific
method is intrinsically superior to another.  It is deliberately explicit so the UI never falls
back to alphabetical ordering when it needs to identify the weaker of two displayed sources.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceTier:
    key: str
    label: str
    rank: int
    derivation_strength: str  # hard | soft | blocked


TIERS: dict[str, ProvenanceTier] = {
    "accredited_laboratory": ProvenanceTier("accredited_laboratory", "Accredited laboratory", 100, "hard"),
    "internal_measurement": ProvenanceTier("internal_measurement", "Internal measurement", 90, "hard"),
    "supplier_declared": ProvenanceTier("supplier_declared", "Supplier datasheet", 80, "hard"),
    "peer_reviewed": ProvenanceTier("peer_reviewed", "Published literature", 72, "soft"),
    "physics_simulation": ProvenanceTier("physics_simulation", "Physics simulation", 65, "soft"),
    "computed_database": ProvenanceTier("computed_database", "Computed database", 60, "soft"),
    "model_prediction": ProvenanceTier("model_prediction", "Model prediction", 50, "soft"),
    "handbook_typical": ProvenanceTier("handbook_typical", "Reference handbook", 45, "soft"),
    "engineering_estimate": ProvenanceTier("engineering_estimate", "Engineering estimate", 25, "soft"),
    "declared": ProvenanceTier("declared", "Declared / uncategorised", 20, "soft"),
    "unknown": ProvenanceTier("unknown", "Unknown provenance", 0, "blocked"),
    "none": ProvenanceTier("none", "Missing evidence", -1, "blocked"),
}


# Intake grades populate source_quality. External/predicted/simulated paths do not always use the
# same vocabulary, so evidence_type and evaluator origin remain explicit fallbacks.
def provenance_category(
    *,
    evidence_type: str | None = None,
    source_quality: str | None = None,
    value_origin: str | None = None,
) -> str:
    quality = (source_quality or "").strip().casefold()
    evidence = (evidence_type or "").strip().casefold()
    origin = (value_origin or "").strip().casefold()

    aliases = {
        "accredited_laboratory": "accredited_laboratory",
        "internal_measurement": "internal_measurement",
        "supplier_declared": "supplier_declared",
        "supplier_datasheet": "supplier_declared",
        "peer_reviewed": "peer_reviewed",
        "published_literature": "peer_reviewed",
        "handbook_typical": "handbook_typical",
        "reference_handbook": "handbook_typical",
        "engineering_estimate": "engineering_estimate",
        "computed_database": "computed_database",
        "model_prediction": "model_prediction",
        "physics_simulation": "physics_simulation",
    }
    if quality in aliases:
        return aliases[quality]

    if origin == "model_prediction" or evidence == "predicted":
        return "model_prediction"
    if origin == "physics_simulation" or evidence in {"computational", "simulation"}:
        return "physics_simulation"
    if evidence in {"external_computational", "computed_database"}:
        return "computed_database"
    if evidence == "supplier":
        return "supplier_declared"
    if evidence in {"literature", "seed_demo"}:
        return "peer_reviewed" if evidence == "literature" else "handbook_typical"
    if evidence in {"experimental", "measurement"}:
        # Legacy rows do not identify whether the measurement was internal or accredited.  Treat
        # them as internal measurement rather than inventing accreditation.
        return "internal_measurement"
    if origin in {"none", "unknown"}:
        return origin
    if not evidence and not origin:
        return "unknown"
    return "declared"


def provenance_label(category: str) -> str:
    return TIERS.get(category, TIERS["unknown"]).label


def provenance_rank(category: str) -> int:
    return TIERS.get(category, TIERS["unknown"]).rank


def weaker_provenance(a: str | None, b: str | None) -> str:
    left = a or "unknown"
    right = b or "unknown"
    return left if provenance_rank(left) <= provenance_rank(right) else right


def derivation_policy(*, evidence_type: str | None, source_quality: str | None) -> tuple[str, str | None]:
    """Return requirement strength and an optional review warning for one baseline observation."""
    category = provenance_category(evidence_type=evidence_type, source_quality=source_quality)
    tier = TIERS.get(category, TIERS["unknown"])
    if tier.derivation_strength == "blocked":
        return "blocked", f"{tier.label} is not strong enough for automatic requirement derivation."
    if tier.derivation_strength == "soft":
        return "soft", (
            f"Derived from {tier.label.lower()} evidence; created as a soft requirement and requires "
            "engineering review before it can become a qualification gate."
        )
    if category == "supplier_declared":
        return "hard", "Supplier-declared evidence can seed a hard floor, but qualification should verify it independently."
    return "hard", None
