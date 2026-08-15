import app.models  # noqa: F401
from app.db.base import Base
from app.db.session import engine


def create_all() -> None:
    Base.metadata.create_all(bind=engine)
