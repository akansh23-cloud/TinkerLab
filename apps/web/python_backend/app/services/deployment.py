"""Idempotent deployment bootstrap for an empty TinkerLab database.

This is intentionally small: schema migration + the deterministic demo scope +
the public screening reference library. It does not seed synthetic projects or
scientific outcomes.
"""
from __future__ import annotations

import hashlib
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.session import (
    SessionLocal,
    database_url_is_configured,
    engine,
    is_serverless,
)
from app.models.entities import Organisation, User
from app.services.bench.studies import install_reference_library

DEMO_ORGANISATION_ID = "0b5ec369-282c-57b5-9781-471f818a07c3"
DEMO_USER_ID = "18ed22f0-6205-53eb-88c7-a45ae5a69ee8"
EXPECTED_ALEMBIC_HEAD = "0013_phase11"
_LOCK_KEY = int.from_bytes(hashlib.sha256(b"tinkerlab-deployment-bootstrap").digest()[:8], "big", signed=True)

# Anything that looks like credentials inside a driver error must never reach the browser.
_CREDENTIAL_PATTERN = re.compile(r"(?i)(://)[^/\s@]*@")


def safe_error(exc: BaseException) -> str:
    """A useful, non-leaking description of a failure.

    The previous implementation reported only ``exc.__class__.__name__``, which turned
    every deployment problem into an unactionable word like "CompileError". The message
    matters; the connection string does not.
    """
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    message = _CREDENTIAL_PATTERN.sub(r"\1***@", message)[:400]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _configuration_hint() -> str | None:
    """Explain the single most common misconfiguration before the driver has to."""
    if not database_url_is_configured():
        if is_serverless():
            return (
                "DATABASE_URL is not set on this deployment, so TinkerLab fell back to a local "
                "SQLite file. A Vercel Function has a read-only filesystem and the schema uses "
                "Postgres JSONB, so no request that touches the database can succeed. Add a Neon "
                "Postgres DATABASE_URL in Project Settings -> Environment Variables and redeploy."
            )
        return "DATABASE_URL is not set; using the local SQLite development default."
    return None


def _table_names() -> set[str]:
    return set(inspect(engine).get_table_names())


def deployment_status() -> dict[str, Any]:
    """Return a status report even when no application tables exist yet."""
    hint = _configuration_hint()
    try:
        tables = _table_names()
    except Exception as exc:
        # Deliberately broad. A bad URL raises ArgumentError, a missing driver raises
        # ModuleNotFoundError, and DNS failures raise OperationalError - none of which
        # are SQLAlchemyError subclasses across the board. Letting any of them escape
        # turns a diagnosable configuration problem into an opaque HTTP 500.
        return {
            "database_reachable": False,
            "schema_ready": False,
            "bootstrap_required": True,
            "database_url_configured": database_url_is_configured(),
            "driver": engine.dialect.name + "+" + (engine.dialect.driver or "unknown"),
            "error": f"Database connection failed: {safe_error(exc)}",
            "hint": hint,
        }

    schema_ready = {"alembic_version", "organisations", "users", "materials"}.issubset(tables)
    version: str | None = None
    organisation_exists = False
    material_count = 0

    if "alembic_version" in tables:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    if "organisations" in tables:
        with engine.connect() as conn:
            organisation_exists = bool(conn.execute(
                text("SELECT 1 FROM organisations WHERE id = :id LIMIT 1"),
                {"id": DEMO_ORGANISATION_ID},
            ).scalar_one_or_none())
    if "materials" in tables:
        with engine.connect() as conn:
            material_count = int(conn.execute(text("SELECT count(*) FROM materials")).scalar_one())

    return {
        "database_reachable": True,
        "database_url_configured": database_url_is_configured(),
        "driver": engine.dialect.name + "+" + (engine.dialect.driver or "unknown"),
        "hint": hint,
        "schema_ready": schema_ready,
        "alembic_version": version,
        "expected_alembic_head": EXPECTED_ALEMBIC_HEAD,
        "organisation_id": DEMO_ORGANISATION_ID,
        "organisation_exists": organisation_exists,
        "material_count": material_count,
        "reference_library_ready": material_count >= 5,
        "bootstrap_required": not schema_ready or not organisation_exists or material_count < 5,
    }


def _run_migrations() -> None:
    """Apply the migration chain using absolute paths only.

    Alembic resolves ``script_location`` and ``prepend_sys_path`` against the process
    working directory. On Vercel that directory is ``apps/web``, which contains the
    Next.js ``app/`` folder - a namespace-package candidate that can shadow
    ``python_backend/app``. Everything below is therefore made absolute and the backend
    root is put on ``sys.path`` explicitly.
    """
    api_root = Path(__file__).resolve().parents[2]
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))

    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(api_root))
    command.upgrade(cfg, "head")


@contextmanager
def _bootstrap_lock() -> Iterator[None]:
    """Serialize bootstrap on Postgres; SQLite/local tests do not need a DB advisory lock."""
    if engine.dialect.name != "postgresql":
        yield
        return
    conn = engine.connect()
    try:
        conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _LOCK_KEY})
        yield
    finally:
        try:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
        finally:
            conn.close()


def _ensure_demo_scope(db: Session) -> None:
    if db.get(Organisation, DEMO_ORGANISATION_ID) is None:
        db.add(Organisation(id=DEMO_ORGANISATION_ID, name="TinkerLab Demo Organisation"))
    if db.get(User, DEMO_USER_ID) is None:
        db.add(User(
            id=DEMO_USER_ID,
            organisation_id=DEMO_ORGANISATION_ID,
            display_name="Demo Scientist",
            email="scientist@demo.tinkerlab.local",
        ))
    db.commit()


def bootstrap_workspace() -> dict[str, Any]:
    """Bring a fresh database to a usable Phase 12.2 workspace, safely and repeatedly."""
    with _bootstrap_lock():
        before = deployment_status()
        if not before.get("database_reachable"):
            raise RuntimeError(
                before.get("hint") or before.get("error") or "Database is unreachable"
            )
        if not before.get("schema_ready") or before.get("alembic_version") != EXPECTED_ALEMBIC_HEAD:
            _run_migrations()

        with SessionLocal() as db:
            _ensure_demo_scope(db)
            library = install_reference_library(db, organisation_id=None)

        after = deployment_status()
        return {
            "status": "ready" if not after.get("bootstrap_required") else "incomplete",
            "organisation_id": DEMO_ORGANISATION_ID,
            "installed_count": len(library.get("installed", [])),
            "skipped_count": len(library.get("skipped", [])),
            "deployment": after,
        }
