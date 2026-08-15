"""Idempotent deployment bootstrap for an empty TinkerLab database.

The deployment bootstrap installs only runtime prerequisites: schema, demo scope,
public reference materials, and two transparent synthetic prediction fixtures.
It does not seed synthetic projects, experimental measurements, or scientific outcomes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
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
from app.models.entities import (
    ModelApplicabilityDomain,
    Organisation,
    PredictionModel,
    PredictionModelVersion,
    User,
)
from app.services.bench.studies import install_reference_library
from app.services.prediction import artifact_checksum, feature_schema_checksum

DEMO_ORGANISATION_ID = "0b5ec369-282c-57b5-9781-471f818a07c3"
DEMO_USER_ID = "18ed22f0-6205-53eb-88c7-a45ae5a69ee8"
EXPECTED_ALEMBIC_HEAD = "0013_phase11"
_SEED_NAMESPACE = uuid.UUID("b76d594b-c7a5-46a2-b836-3c82d33c9bf0")
_LOCK_KEY = int.from_bytes(hashlib.sha256(b"tinkerlab-deployment-bootstrap").digest()[:8], "big", signed=True)

# Anything that looks like credentials inside a driver error must never reach the browser.
_CREDENTIAL_PATTERN = re.compile(r"(?i)(://)[^/\s@]*@")


def _sid(name: str) -> str:
    """Use the same deterministic IDs as the full development seed."""
    return str(uuid.uuid5(_SEED_NAMESPACE, name))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def safe_error(exc: BaseException) -> str:
    """A useful, non-leaking description of a failure."""
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    message = _CREDENTIAL_PATTERN.sub(r"\1***@", message)[:400]
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _configuration_hint() -> str | None:
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
    approved_prediction_model_count = 0

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
    if "prediction_model_versions" in tables:
        with engine.connect() as conn:
            approved_prediction_model_count = int(conn.execute(text(
                "SELECT count(*) FROM prediction_model_versions "
                "WHERE approved_at IS NOT NULL AND retired_at IS NULL"
            )).scalar_one())

    prediction_models_ready = approved_prediction_model_count > 0
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
        "approved_prediction_model_count": approved_prediction_model_count,
        "prediction_models_ready": prediction_models_ready,
        "bootstrap_required": (
            not schema_ready
            or not organisation_exists
            or material_count < 5
            or not prediction_models_ready
        ),
    }


def _run_migrations() -> None:
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


def _ensure_demo_prediction_models(db: Session) -> dict[str, int]:
    """Install reviewed, transparent software-validation models without inventing science.

    These are the same deterministic global fixtures used by the development seed. They are
    explicitly synthetic, carry no real-material training claim, and remain bounded to the
    generic polymer applicability domain. Existing or retired versions are never overwritten,
    re-approved, or unretired.
    """
    feature_schema = {
        "features": {
            "matrix_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "primary_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "alternative_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "total_modifier_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "reinforcement_fraction_pct": {"type": "number", "unit": "%", "required": True},
            "component_count": {"type": "integer", "required": True},
        },
        "origin": "synthetic generic-polymer fixture",
    }
    required_features = list(feature_schema["features"].keys())
    ranges = {
        "matrix_fraction_pct": [70.0, 90.0],
        "primary_modifier_fraction_pct": [0.0, 25.0],
        "alternative_modifier_fraction_pct": [0.0, 25.0],
        "total_modifier_fraction_pct": [10.0, 25.0],
        "reinforcement_fraction_pct": [0.0, 10.0],
        "component_count": [2.0, 8.0],
    }
    specs = [
        {
            "model_name": "phase4:model:demo-polymer-tensile",
            "version_name": "phase4:model-version:demo-polymer-tensile:v1",
            "domain_name": "phase4:applicability:demo-polymer-tensile:v1",
            "key": "demo-polymer-tensile-linear",
            "display_name": "Demo Polymer Tensile Predictor",
            "property": "tensile_strength",
            "unit": "MPa",
            "intercept": 58.0,
            "coefficients": {"matrix_fraction_pct": 0.05, "primary_modifier_fraction_pct": 0.30, "alternative_modifier_fraction_pct": 0.70, "reinforcement_fraction_pct": 1.00},
            "half_width": 2.0,
            "stddev": 1.2,
            "training_key": "phase4-demo-v1",
            "conditions": {"temperature": {"min": 20.0, "max": 30.0, "unit": "degC", "required": True, "borderline_tolerance": 1.0}},
        },
        {
            "model_name": "phase5:model:demo-polymer-density",
            "version_name": "phase5:model-version:demo-polymer-density:v1",
            "domain_name": "phase5:applicability:demo-polymer-density:v1",
            "key": "demo-polymer-density-linear",
            "display_name": "Demo Polymer Density Predictor",
            "property": "density",
            "unit": "kg/m^3",
            "intercept": 820.0,
            "coefficients": {"matrix_fraction_pct": 3.8, "primary_modifier_fraction_pct": 3.0, "alternative_modifier_fraction_pct": 8.0, "reinforcement_fraction_pct": 9.0},
            "half_width": 20.0,
            "stddev": 12.0,
            "training_key": "phase5-density-demo-v1",
            "conditions": {},
        },
    ]
    installed = 0
    skipped = 0
    for spec in specs:
        model_id = _sid(spec["model_name"])
        version_id = _sid(spec["version_name"])
        domain_id = _sid(spec["domain_name"])
        model = db.get(PredictionModel, model_id)
        if model is None:
            model = PredictionModel(
                id=model_id,
                organisation_id=None,
                key=spec["key"],
                display_name=spec["display_name"],
                description="Transparent deterministic synthetic model for software-validation workflows only.",
                model_type="transparent_demo_linear",
                owner_provider="TinkerLab synthetic fixture",
                status="approved",
                supported_material_families=["polymer"],
                supported_property_keys=[spec["property"]],
                metadata_json={"demo_only": True, "scientific_claim": False},
            )
            db.add(model)
            db.flush()

        version = db.get(PredictionModelVersion, version_id)
        if version is not None:
            skipped += 1
            continue

        artifact = {
            "model_kind": "linear",
            "intercept": spec["intercept"],
            "coefficients": spec["coefficients"],
            "uncertainty": {
                "method": "fixed_validation_interval",
                "half_width": spec["half_width"],
                "stddev": spec["stddev"],
                "coverage": 0.90,
            },
            "demo_only": True,
        }
        version = PredictionModelVersion(
            id=version_id,
            model_id=model.id,
            version="1.0.0-demo",
            predictor_key="demo_linear_json",
            predictor_contract_version="1.0",
            artifact_format="tinkerlab_linear_json_v1",
            artifact_payload=artifact,
            artifact_checksum=artifact_checksum("tinkerlab_linear_json_v1", artifact),
            feature_schema_version="polymer-demo-v1",
            feature_schema=feature_schema,
            feature_schema_checksum=feature_schema_checksum("polymer-demo-v1", feature_schema),
            target_property_key=spec["property"],
            canonical_output_unit=spec["unit"],
            uncertainty_method="fixed_validation_interval",
            applicability_policy_version="applicability-v1",
            training_data_descriptor={
                "kind": "synthetic_deterministic_fixture",
                "real_material_data": False,
                "purpose": "software validation only",
            },
            training_data_checksum=_digest({"synthetic_fixture": spec["training_key"]}),
            calibration_metrics={"coverage_target": 0.90, "synthetic_only": True},
            validation_metrics={"synthetic_only": True},
            approved_at=datetime.now(UTC),
            immutable_metadata={
                "demo_only": True,
                "scientific_claim": False,
                "warning": "DEMO MODEL — synthetic software-validation fixture; not validated for real material decisions.",
            },
        )
        db.add(version)
        db.flush()
        db.add(ModelApplicabilityDomain(
            id=domain_id,
            model_version_id=version.id,
            material_families=["polymer"],
            required_feature_keys=required_features,
            numeric_feature_ranges=ranges,
            allowed_categorical_values={},
            required_component_keys=[],
            target_condition_ranges=spec["conditions"],
            redacted_input_policy="reject",
            domain_distance_method=None,
            domain_distance_config={},
            borderline_tolerance=0.5,
            metadata_json={"demo_only": True, "scientific_claim": False},
        ))
        installed += 1
    db.commit()
    return {"installed": installed, "skipped": skipped}


def bootstrap_workspace() -> dict[str, Any]:
    """Bring a fresh database to a usable scientific workspace, safely and repeatedly."""
    with _bootstrap_lock():
        before = deployment_status()
        if not before.get("database_reachable"):
            raise RuntimeError(before.get("hint") or before.get("error") or "Database is unreachable")
        if not before.get("schema_ready") or before.get("alembic_version") != EXPECTED_ALEMBIC_HEAD:
            _run_migrations()

        with SessionLocal() as db:
            _ensure_demo_scope(db)
            library = install_reference_library(db, organisation_id=None)
            models = _ensure_demo_prediction_models(db)

        after = deployment_status()
        return {
            "status": "ready" if not after.get("bootstrap_required") else "incomplete",
            "organisation_id": DEMO_ORGANISATION_ID,
            "installed_count": len(library.get("installed", [])),
            "skipped_count": len(library.get("skipped", [])),
            "prediction_models_installed": models["installed"],
            "prediction_models_skipped": models["skipped"],
            "deployment": after,
        }
