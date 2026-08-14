import os
import tempfile
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_phase1.sqlite3"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["CORS_ORIGINS"] = "http://testserver"
# Artifact content store is redirected to a disposable directory so tests never touch the
# operator-controlled production store.
TEST_ARTIFACT_STORE = Path(tempfile.mkdtemp(prefix="tinkerlab-test-artifacts-"))
os.environ["TINKERLAB_ARTIFACT_STORE"] = str(TEST_ARTIFACT_STORE)

import pytest
from fastapi.testclient import TestClient

from app.db.base import Base
from app.db.seed import seed
from app.db.session import SessionLocal, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed(db)
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()

@pytest.fixture()
def client(database):
    return TestClient(app)

@pytest.fixture()
def db(database):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
