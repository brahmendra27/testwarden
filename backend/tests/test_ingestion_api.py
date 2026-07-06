import io
import uuid


def _headers(key):
    return {"X-Api-Key": key}


def _envelope(node_id="tests/test_a.py::test_one", status="passed", attempts=None, **kwargs):
    file_path = node_id.split("::")[0]
    return {
        "result_ref": str(uuid.uuid4()),
        "framework": "pytest-playwright",
        "normalized_id": node_id,
        "file_path": file_path,
        "title": node_id.split("::")[-1],
        "status": status,
        "duration_ms": 1200,
        "attempts": attempts or [],
        **kwargs,
    }


def _create_run(client, key, **overrides):
    payload = {"run_uuid": str(uuid.uuid4()), "framework": "pytest-playwright", **overrides}
    response = client.post("/api/v1/ingest/runs", json=payload, headers=_headers(key))
    assert response.status_code == 200, response.text
    return payload["run_uuid"]


def test_auth_required(client):
    response = client.post("/api/v1/ingest/runs", json={"run_uuid": str(uuid.uuid4())})
    assert response.status_code == 401
    response = client.post(
        "/api/v1/ingest/runs",
        json={"run_uuid": str(uuid.uuid4())},
        headers=_headers("twk_" + "0" * 40),
    )
    assert response.status_code == 401


def test_run_creation_is_idempotent(client, project_key):
    _, key = project_key
    run_uuid = str(uuid.uuid4())
    first = client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid}, headers=_headers(key))
    second = client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid}, headers=_headers(key))
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["run_id"] == second.json()["run_id"]


def test_full_ingest_flow_with_rerun_flaky(client, project_key):
    project, key = project_key
    run_uuid = _create_run(client, key, branch="main")

    flaky = _envelope(
        "tests/test_a.py::test_flaky",
        status="passed",
        attempts=[
            {"index": 0, "status": "failed", "duration_ms": 5000,
             "error_type": "TimeoutError", "error_message": "timed out",
             "stack_trace": "tests/test_a.py:10: TimeoutError"},
            {"index": 1, "status": "passed", "duration_ms": 900},
        ],
    )
    hard_fail = _envelope(
        "tests/test_a.py::test_broken",
        status="failed",
        attempts=[
            {"index": 0, "status": "failed", "duration_ms": 800,
             "error_type": "AssertionError", "error_message": "expected visible",
             "stack_trace": "tests/test_a.py:20: AssertionError"},
        ],
    )
    passing = _envelope("tests/test_a.py::test_ok")
    skipped = _envelope("tests/test_a.py::test_skipped", status="skipped")

    response = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [flaky, hard_fail, passing, skipped]},
        headers=_headers(key),
    )
    assert response.status_code == 200, response.text
    ref_map = response.json()["results"]
    assert len(ref_map) == 4

    finish = client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers=_headers(key))
    body = finish.json()
    assert body["status"] == "completed"
    assert body["total"] == 4
    assert body["passed"] == 2
    assert body["failed"] == 1
    assert body["flaky"] == 1

    # Result detail carries attempts, flaky derivation, and fingerprint.
    detail = client.get(f"/api/v1/results/{ref_map[flaky['result_ref']]}").json()
    assert detail["is_flaky_in_run"] is True
    assert detail["status"] == "passed"
    assert len(detail["attempts"]) == 2
    assert detail["attempts"][0]["error_type"] == "TimeoutError"

    broken = client.get(f"/api/v1/results/{ref_map[hard_fail['result_ref']]}").json()
    assert broken["failure_fingerprint"] is not None

    # Strip is in execution order with flaky marked amber.
    run_id = body["run_id"]
    strip = client.get(f"/api/v1/runs/{run_id}/strip").json()
    tokens = [entry[1] for entry in strip]
    assert tokens == ["A", "F", "P", "K"]


def test_resent_results_are_idempotent(client, project_key):
    _, key = project_key
    run_uuid = _create_run(client, key)
    envelope = _envelope("tests/test_b.py::test_same")
    first = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [envelope]}, headers=_headers(key),
    ).json()["results"]
    second = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [envelope]}, headers=_headers(key),
    ).json()["results"]
    assert first[envelope["result_ref"]] == second[envelope["result_ref"]]


def test_finished_run_rejects_results(client, project_key):
    _, key = project_key
    run_uuid = _create_run(client, key)
    client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers=_headers(key))
    response = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [_envelope()]}, headers=_headers(key),
    )
    assert response.status_code == 409


def test_artifact_roundtrip(client, project_key):
    _, key = project_key
    run_uuid = _create_run(client, key)
    envelope = _envelope(
        "tests/test_c.py::test_with_artifact",
        status="failed",
        attempts=[{"index": 0, "status": "failed", "duration_ms": 100,
                   "error_type": "AssertionError", "error_message": "boom"}],
    )
    ref_map = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [envelope]}, headers=_headers(key),
    ).json()["results"]
    result_id = ref_map[envelope["result_ref"]]

    content = b"\x89PNG fake screenshot bytes"
    upload = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results/{result_id}/artifacts",
        data={"attempt_index": "0", "kind": "screenshot"},
        files={"file": ("failure.png", io.BytesIO(content), "image/png")},
        headers=_headers(key),
    )
    assert upload.status_code == 200, upload.text
    artifact_id = upload.json()["artifact_id"]

    download = client.get(f"/api/v1/artifacts/{artifact_id}")
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"].startswith("image/png")

    detail = client.get(f"/api/v1/results/{result_id}").json()
    artifacts = detail["attempts"][0]["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "screenshot"


def test_stable_identity_across_runs(client, project_key, db):
    _, key = project_key
    node = "tests/test_d.py::test_identity"
    for _ in range(2):
        run_uuid = _create_run(client, key)
        client.post(
            f"/api/v1/ingest/runs/{run_uuid}/results",
            json={"results": [_envelope(node)]}, headers=_headers(key),
        )
        client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers=_headers(key))
    # Same logical test -> one test case with two history entries.
    from sqlalchemy import select
    from testwarden.models import TestCase
    project_id = project_key[0].id
    cases = db.scalars(select(TestCase).where(TestCase.project_id == project_id)).all()
    assert len(cases) == 1
    history = client.get(f"/api/v1/tests/{cases[0].id}").json()["history"]
    assert len(history) == 2
