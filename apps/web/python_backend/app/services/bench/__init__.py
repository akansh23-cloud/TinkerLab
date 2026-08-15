"""Phase 12 — the intake bench.

Composition layer over the Phase 1–11 scientific core. It creates and inspects *inputs*: materials,
requirements, search spaces and readiness. It contains no evaluator and produces no verdict, which
is what keeps the determinism guarantees of the decision path intact while the product becomes
usable by someone who has not read the architecture documents.
"""

from app.services.bench import catalog, derive, intake, library, presets, readiness, studies

__all__ = ["catalog", "derive", "intake", "library", "presets", "readiness", "studies"]
