"""Phase 12 — install the reference material library into a deployed database.

Run after `alembic upgrade head` and the main seed:

    python -m app.db.seed_bench

Idempotent. Deterministic UUID5 ids mean a second run touches the same rows, and an already-present
material is skipped rather than rewritten — a user may have appended their own measured data to a
library material, and a reinstall must never destroy it.
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.services.bench.studies import install_reference_library


def main() -> None:
    db = SessionLocal()
    try:
        result = install_reference_library(db)
        print(
            f"TinkerLab reference library: {result['installed_count']} installed, "
            f"{result['skipped_count']} already present."
        )
        for skipped in result["skipped"]:
            if skipped["reason"] not in {"already installed"}:
                print(f"  skipped {skipped['key']}: {skipped['reason']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
