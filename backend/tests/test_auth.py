"""Shared-token auth: opt-in gate over the dashboard APIs."""
import uuid

import pytest
from fastapi.testclient import TestClient

from flakelens.config import settings
from flakelens.main import app

TOKEN = "s3cr3t-dashboard-token"


@pytest.fixture()
def auth_client(monkeypatch):
    monkeypatch.setattr(settings, "access_token", TOKEN)
    with TestClient(app) as c:
        yield c


def test_open_mode_when_no_token(client):
    # The default test settings have no access_token → everything is open.
    assert client.get("/api/v1/auth/status").json()["required"] is False
    assert client.get("/api/v1/projects").status_code == 200


def test_dashboard_requires_token(auth_client):
    status = auth_client.get("/api/v1/auth/status").json()
    assert status["required"] is True and status["authenticated"] is False
    # Protected endpoint blocked without a session.
    assert auth_client.get("/api/v1/projects").status_code == 401


def test_health_and_auth_stay_open(auth_client):
    assert auth_client.get("/api/v1/health").status_code == 200
    assert auth_client.get("/api/v1/auth/status").status_code == 200


def test_ingestion_stays_open_with_project_key(auth_client, db):
    """Test runners never have the dashboard token — ingest must stay key-gated."""
    from flakelens.auth import create_api_key
    from flakelens.models import Project

    project = Project(slug=f"auth-{uuid.uuid4().hex[:8]}", name="Auth Ingest")
    db.add(project)
    db.flush()
    key = create_api_key(db, project)
    db.commit()

    resp = auth_client.post(
        "/api/v1/ingest/runs",
        json={"run_uuid": str(uuid.uuid4())},
        headers={"X-Api-Key": key},
    )
    assert resp.status_code == 200  # no dashboard token needed
    # ...but a bad project key is still rejected by ingest's own auth.
    assert auth_client.post(
        "/api/v1/ingest/runs", json={"run_uuid": str(uuid.uuid4())},
        headers={"X-Api-Key": "flk_" + "0" * 40},
    ).status_code == 401


def test_login_flow(auth_client):
    assert auth_client.post("/api/v1/auth/login", json={"token": "wrong"}).status_code == 401
    ok = auth_client.post("/api/v1/auth/login", json={"token": TOKEN})
    assert ok.status_code == 200 and ok.json()["authenticated"] is True
    # Cookie now set on the client → protected endpoints work.
    assert auth_client.get("/api/v1/auth/status").json()["authenticated"] is True
    assert auth_client.get("/api/v1/projects").status_code == 200
    # Logout clears it.
    auth_client.post("/api/v1/auth/logout")
    assert auth_client.get("/api/v1/projects").status_code == 401


def test_bearer_header_also_works(auth_client):
    """API clients (scripts, CI) can pass the token as a Bearer header."""
    assert auth_client.get(
        "/api/v1/projects", headers={"Authorization": f"Bearer {TOKEN}"}
    ).status_code == 200
    assert auth_client.get(
        "/api/v1/projects", headers={"Authorization": "Bearer nope"}
    ).status_code == 401
