import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def normalize_database_url(database_url: str) -> str:
    """Use the psycopg 3 SQLAlchemy dialect for Vercel/Neon Postgres URLs.

    Vercel/Neon commonly supplies ``postgresql://`` (and older providers may supply
    ``postgres://``). SQLAlchemy interprets those generic schemes as the psycopg2
    dialect. TinkerLab ships psycopg 3, so normalize only generic Postgres schemes
    and leave explicit dialect URLs untouched.
    """
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    return database_url


def is_serverless() -> bool:
    """True when running inside a Vercel Function (or an equivalent FaaS runtime)."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def database_url_is_configured() -> bool:
    """Whether an explicit DATABASE_URL was supplied rather than the local SQLite default."""
    return bool(os.environ.get("DATABASE_URL"))


settings = get_settings()
database_url = normalize_database_url(settings.database_url)
is_sqlite = database_url.startswith("sqlite")

connect_args: dict = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs: dict = {}

if is_sqlite:
    engine_kwargs["pool_pre_ping"] = True
elif is_serverless():
    # A Vercel Function is frozen between invocations, so a pooled connection is
    # very often already dead when the next request arrives — and Neon caps the
    # number of concurrent connections. Hold none between invocations and let the
    # Neon pooler (the "-pooler" host) do the pooling instead.
    engine_kwargs["poolclass"] = NullPool
    connect_args["connect_timeout"] = 10
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    connect_args["connect_timeout"] = 10

engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
