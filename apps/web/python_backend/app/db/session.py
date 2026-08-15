from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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


settings = get_settings()
database_url = normalize_database_url(settings.database_url)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
