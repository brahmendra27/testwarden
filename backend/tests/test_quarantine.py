"""Offline tests for the quarantine-and-heal loop."""
import uuid

from types import SimpleNamespace

from flakelens.services.quarantine import RELEASE_STREAK, release_ready
from flakelens.services.stats import result_token


def _result(status, flaky=False, quarantined=False):
    return SimpleNamespace(
        status=status,
        is_flaky_in_run=flaky,
        extras={"quarantined": True} if quarantined else {},
    )


def test_result_token_honors_quarantine():
    # Normal xfail/xpass are excluded from the window...
    assert result_token(_result("xfailed")) is None
    assert result_token(_result("xpassed")) is None
    # ...but quarantined outcomes keep feeding the healing signal.
    assert result_token(_result("xfailed", quarantined=True)) == "F"
    assert result_token(_result("xpassed", quarantined=True)) == "P"
    assert result_token(_result("passed")) == "P"
    assert result_token(_result("passed", flaky=True)) == "A"


def test_release_ready_requires_clean_streak():
    case = SimpleNamespace(quarantined_at=None, recent_statuses=[{"t": "P"}] * 10)
    assert release_ready(case) is False  # not quarantined

    case = SimpleNamespace(
        quarantined_at="2026-01-01",
        recent_statuses=[{"t": "F"}] + [{"t": "P"}] * (RELEASE_STREAK - 1),
    )
    assert release_ready(case) is False  # streak too short

    case = SimpleNamespace(
        quarantined_at="2026-01-01",
        recent_statuses=[{"t": "F"}] + [{"t": "P"}] * RELEASE_STREAK,
    )
    assert release_ready(case) is True


def _ingest_flaky_case(client, key, node="tests/test_q.py::test_wobbly"):
    """Alternate pass/fail across runs so the case becomes flaky."""
    for index in range(8):
        run_uuid = str(uuid.uuid4())
        client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid},
                    headers={"X-Api-Key": key})
        status = "passed" if index % 2 == 0 else "failed"
        envelope = {
            "result_ref": str(uuid.uuid4()),
            "framework": "pytest",
            "normalized_id": node,
            "file_path": node.split("::")[0],
            "title": node.split("::")[-1],
            "status": status,
            "duration_ms": 100,
            "attempts": (
                [{"index": 0, "status": "failed", "error_type": "AssertionError",
                  "error_message": "boom"}] if status == "failed" else []
            ),
        }
        client.post(f"/api/v1/ingest/runs/{run_uuid}/results",
                    json={"results": [envelope]}, headers={"X-Api-Key": key})
        client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers={"X-Api-Key": key})


def test_quarantine_board_and_actions(client, project_key, monkeypatch):
    project, key = project_key
    _ingest_flaky_case(client, key)

    board = client.get(f"/api/v1/projects/{project.slug}/quarantine").json()
    assert len(board["suggestions"]) == 1
    case_id = board["suggestions"][0]["id"]
    assert board["quarantined"] == []

    # Agent actions refuse cleanly without a key
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post(f"/api/v1/tests/{case_id}/quarantine").status_code == 503

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    executed = []
    monkeypatch.setattr(
        "flakelens.api.quarantine.execute_marker_job", lambda job_id: executed.append(job_id)
    )
    body = client.post(f"/api/v1/tests/{case_id}/quarantine").json()
    assert body["kind"] == "quarantine"
    assert executed == [body["job_id"]]

    # Active job blocks duplicates and shows on the board
    assert client.post(f"/api/v1/tests/{case_id}/quarantine").status_code == 409
    board = client.get(f"/api/v1/projects/{project.slug}/quarantine").json()
    assert board["suggestions"][0]["latest_job"]["kind"] == "quarantine"

    # Release requires the case to actually be quarantined
    assert client.post(f"/api/v1/tests/{case_id}/release").status_code == 400


def test_heal_starts_selfheal_on_latest_failure(client, project_key, monkeypatch):
    project, key = project_key
    _ingest_flaky_case(client, key, node="tests/test_q.py::test_heal_me")
    case_id = client.get(f"/api/v1/projects/{project.slug}/quarantine").json()[
        "suggestions"
    ][0]["id"]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    executed = []
    monkeypatch.setattr(
        "flakelens.api.quarantine.execute_autofix_job", lambda job_id: executed.append(job_id)
    )
    body = client.post(f"/api/v1/tests/{case_id}/heal").json()
    assert body["kind"] == "autofix"
    assert executed == [body["job_id"]]
