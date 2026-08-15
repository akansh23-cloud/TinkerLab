#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../apps/api"

python -m alembic upgrade head
python -m app.db.seed
# Phase 12: reference material library. Idempotent, so re-running the bootstrap is safe.
python -m app.db.seed_bench

echo "TinkerLab database migration + deterministic seed completed."
