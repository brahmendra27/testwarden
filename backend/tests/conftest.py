import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="testwarden-tests-")
os.environ["TESTWARDEN_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TESTWARDEN_ARTIFACT_DIR"] = f"{_tmp}/artifacts"

import pytest
from fastapi.testclient import TestClient

from testwarden.auth import create_api_key
from testwarden.db import Base, SessionLocal, engine
from testwarden.main import app
from testwarden.models import Project


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


_project_counter = 0


@pytest.fixture()
def project_key(client, db):
    """Fresh project + API key per test; returns (project, full_key)."""
    global _project_counter
    _project_counter += 1
    project = Project(slug=f"proj-{_project_counter}", name=f"Project {_project_counter}")
    db.add(project)
    db.flush()
    key = create_api_key(db, project)
    db.commit()
    return project, key
