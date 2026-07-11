"""Tests for the maintenance crew: pure triage logic + endpoints."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from flakelens.services.crew import (
    build_incidents,
    parse_classification,
    render_digest,
)


def _res(rid, fp, err="boom", etype="AssertionError"):
    return SimpleNamespace(id=rid, failure_fingerprint=fp, error_type=etype, error_message=err)


def _case(cid, node, flake=0.0):
    return SimpleNamespace(id=cid, node_id=node, flake_score=flake)


def test_build_incidents_clusters_by_fingerprint():
    rows = [
        (_res(1, "fp-A"), _case(10, "t.py::a")),
        (_res(2, "fp-A"), _case(11, "t.py::b")),
        (_res(3, "fp-A"), _case(10, "t.py::a")),
        (_res(4, "fp-B"), _case(12, "t.py::c")),
    ]
    incidents = build_incidents(rows)
    assert len(incidents) == 2
    # ordered by blast radius: fp-A (3 failures across 2 tests) first
    assert incidents[0]["fingerprint"] == "fp-A"
    assert incidents[0]["count"] == 3
    assert incidents[0]["node_ids"] == ["t.py::a", "t.py::b"]
    assert incidents[1]["count"] == 1


def test_build_incidents_no_fingerprint_clusters_per_case():
    rows = [
        (_res(1, None), _case(10, "t.py::a")),
        (_res(2, None), _case(10, "t.py::a")),
        (_res(3, None), _case(11, "t.py::b")),
    ]
    incidents = build_incidents(rows)
    assert len(incidents) == 2
    assert incidents[0]["count"] == 2  # case 10 has two failures


def test_build_incidents_tracks_worst_flake_score():
    rows = [
        (_res(1, "fp"), _case(10, "t.py::a", flake=0.2)),
        (_res(2, "fp"), _case(11, "t.py::b", flake=0.9)),
    ]
    incident = build_incidents(rows)[0]
    assert incident["worst_case_id"] == 11  # highest flake score


def test_parse_classification():
    assert parse_classification("## Classification\nTEST_BUG — the locator is stale") == "TEST_BUG"
    assert parse_classification("This is an APP_BUG in checkout") == "APP_BUG"
    assert parse_classification("nothing conclusive") == "UNKNOWN"


def test_render_digest_all_quiet():
    digest = render_digest("Demo", datetime(2026, 1, 1, tzinfo=timezone.utc), [], 5, 0)
    assert "All quiet" in digest


def test_render_digest_with_incidents():
    incidents = [{
        "node_ids": ["t.py::a", "t.py::b"],
        "count": 4,
        "classification": "TEST_BUG",
        "error_type": "AssertionError",
        "error_message": "stale locator",
        "action": {"kind": "selfheal", "status": "completed", "pr_url": "http://pr/1"},
    }]
    digest = render_digest("Demo", datetime(2026, 1, 1, tzinfo=timezone.utc), incidents, 3, 4)
    assert "Incident 1" in digest
    assert "TEST_BUG" in digest
    assert "selfheal" in digest
    assert "+1 more tests" in digest


def _ingest_failure(client, key, node, fingerprint_err="the same error"):
    run_uuid = str(uuid.uuid4())
    client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid}, headers={"X-Api-Key": key})
    client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [{
            "result_ref": str(uuid.uuid4()), "framework": "pytest",
            "normalized_id": node, "file_path": node.split("::")[0],
            "title": node.split("::")[-1], "status": "failed", "duration_ms": 10,
            "attempts": [{"index": 0, "status": "failed", "error_type": "AssertionError",
                          "error_message": fingerprint_err}],
        }]},
        headers={"X-Api-Key": key},
    )
    client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers={"X-Api-Key": key})


def test_crew_endpoints(client, project_key, monkeypatch):
    project, key = project_key
    _ingest_failure(client, key, "tests/test_c.py::test_one")

    executed = []
    monkeypatch.setattr(
        "flakelens.api.crew.execute_crew_run", lambda run_id: executed.append(run_id)
    )
    body = client.post(f"/api/v1/projects/{project.slug}/crew").json()
    assert body["status"] == "queued"
    assert body["trigger"] == "manual"
    assert executed == [body["id"]]

    history = client.get(f"/api/v1/projects/{project.slug}/crew").json()
    assert history["runs"][0]["id"] == body["id"]
    assert client.get(f"/api/v1/crew-runs/{body['id']}").json()["project_id"] == project.id

    # active run blocks a duplicate
    assert client.post(f"/api/v1/projects/{project.slug}/crew").status_code == 409


def test_crew_run_without_ai_reports_only(client, project_key, monkeypatch, db):
    """End-to-end pipeline with no ANTHROPIC_API_KEY: clusters + digests, no actions."""
    from flakelens.models import CrewRun
    from flakelens.services.crew import execute_crew_run

    project, key = project_key
    _ingest_failure(client, key, "tests/test_c.py::test_a")
    _ingest_failure(client, key, "tests/test_c.py::test_a")  # same test, clusters together

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    run = CrewRun(project_id=project.id, trigger="manual")
    db.add(run)
    db.commit()
    execute_crew_run(run.id)

    db.refresh(run)
    assert run.status == "completed"
    assert run.incidents
    assert run.incidents[0]["classification"] == "UNANALYZED"
    assert "no ANTHROPIC_API_KEY" in run.incidents[0]["action_reason"]
    assert run.digest and "maintenance crew" in run.digest
