import uuid


def _headers(key):
    return {"X-Api-Key": key}


def _run_with_results(client, key, results):
    run_uuid = str(uuid.uuid4())
    client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid, "branch": "main"},
                headers=_headers(key))
    envelopes = []
    for node_id, status, flaky in results:
        attempts = []
        if flaky:
            attempts = [
                {"index": 0, "status": "failed", "duration_ms": 3000,
                 "error_type": "TimeoutError", "error_message": "flaky timeout"},
                {"index": 1, "status": "passed", "duration_ms": 800},
            ]
        elif status in ("failed", "error"):
            attempts = [
                {"index": 0, "status": status, "duration_ms": 700,
                 "error_type": "AssertionError", "error_message": f"{node_id} broke"},
            ]
        envelopes.append({
            "result_ref": str(uuid.uuid4()),
            "framework": "pytest-playwright",
            "normalized_id": node_id,
            "file_path": node_id.split("::")[0],
            "title": node_id.split("::")[-1],
            "status": status,
            "duration_ms": 900,
            "attempts": attempts,
        })
    client.post(f"/api/v1/ingest/runs/{run_uuid}/results",
                json={"results": envelopes}, headers=_headers(key))
    finish = client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers=_headers(key))
    return finish.json()["run_id"]


def test_cross_run_flakiness_materializes(client, project_key):
    project, key = project_key
    node = "tests/test_x.py::test_flippy"
    # Alternate pass/fail across 8 runs -> should be flagged flaky.
    for i in range(8):
        status = "passed" if i % 2 == 0 else "failed"
        _run_with_results(client, key, [(node, status, False)])
    flaky = client.get(f"/api/v1/projects/{project.slug}/flaky").json()
    assert len(flaky) == 1
    assert flaky[0]["node_id"] == node
    assert flaky[0]["flake_score"] >= 0.9


def test_intra_run_retries_materialize_flakiness(client, project_key):
    project, key = project_key
    node = "tests/test_y.py::test_retry_prone"
    for i in range(6):
        _run_with_results(client, key, [(node, "passed", i % 2 == 0)])
    flaky = client.get(f"/api/v1/projects/{project.slug}/flaky").json()
    assert [case["node_id"] for case in flaky] == [node]


def test_stable_tests_are_not_flaky(client, project_key):
    project, key = project_key
    for _ in range(6):
        _run_with_results(client, key, [("tests/test_z.py::test_solid", "passed", False)])
    assert client.get(f"/api/v1/projects/{project.slug}/flaky").json() == []


def test_compare_runs_classification(client, project_key):
    _, key = project_key
    base = _run_with_results(client, key, [
        ("t.py::will_break", "passed", False),
        ("t.py::will_be_fixed", "failed", False),
        ("t.py::still_broken", "failed", False),
        ("t.py::goes_flaky", "passed", False),
        ("t.py::gets_removed", "passed", False),
        ("t.py::stays_green", "passed", False),
    ])
    head = _run_with_results(client, key, [
        ("t.py::will_break", "failed", False),
        ("t.py::will_be_fixed", "passed", False),
        ("t.py::still_broken", "failed", False),
        ("t.py::goes_flaky", "passed", True),
        ("t.py::brand_new", "passed", False),
        ("t.py::stays_green", "passed", False),
    ])
    body = client.get(f"/api/v1/compare?base_run={base}&head_run={head}").json()
    counts = body["counts"]
    assert counts == {
        "newly_failing": 1, "fixed": 1, "newly_flaky": 1,
        "still_failing": 1, "new": 1, "removed": 1,
    }
    assert body["buckets"]["newly_failing"][0]["node_id"] == "t.py::will_break"
    assert body["buckets"]["fixed"][0]["node_id"] == "t.py::will_be_fixed"
