"""Insights: incidents, regression alerts, health grade, cross-branch, verdict."""
import uuid


def _run(client, key, results, branch="main"):
    """results: list of (node_id, status). Returns run_id."""
    run_uuid = str(uuid.uuid4())
    client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid, "branch": branch},
                headers={"X-Api-Key": key})
    envelopes = []
    for node, status, *rest in results:
        flaky = rest[0] if rest else False
        attempts = []
        if flaky:
            attempts = [{"index": 0, "status": "failed", "error_type": "TimeoutError",
                         "error_message": "flaky"}, {"index": 1, "status": "passed"}]
        elif status in ("failed", "error"):
            attempts = [{"index": 0, "status": status, "error_type": "AssertionError",
                         "error_message": "the shared root error"}]
        envelopes.append({
            "result_ref": str(uuid.uuid4()), "framework": "pytest",
            "normalized_id": node, "file_path": node.split("::")[0],
            "title": node.split("::")[-1], "status": status, "duration_ms": 100,
            "attempts": attempts,
        })
    client.post(f"/api/v1/ingest/runs/{run_uuid}/results", json={"results": envelopes},
                headers={"X-Api-Key": key})
    return client.post(f"/api/v1/ingest/runs/{run_uuid}/finish",
                       headers={"X-Api-Key": key}).json()["run_id"]


def test_incidents_cluster_by_fingerprint(client, project_key):
    project, key = project_key
    # Two different tests failing with the SAME error -> one incident.
    _run(client, key, [("t.py::a", "failed"), ("t.py::b", "failed"), ("t.py::c", "passed")])
    incidents = client.get(f"/api/v1/projects/{project.slug}/incidents").json()["incidents"]
    assert len(incidents) == 1
    assert incidents[0]["count"] == 2
    assert set(incidents[0]["node_ids"]) == {"t.py::a", "t.py::b"}


def test_regression_alerts_newly_failing(client, project_key):
    project, key = project_key
    _run(client, key, [("t.py::x", "passed"), ("t.py::y", "passed")])
    _run(client, key, [("t.py::x", "failed"), ("t.py::y", "passed")])
    alerts = client.get(f"/api/v1/projects/{project.slug}/alerts").json()["alerts"]
    kinds = {a["kind"] for a in alerts}
    assert "newly_failing" in kinds
    newly = next(a for a in alerts if a["kind"] == "newly_failing")
    assert "t.py::x" in newly["tests"]


def test_health_grade_and_actions(client, project_key):
    project, key = project_key
    for _ in range(3):
        _run(client, key, [("t.py::a", "passed"), ("t.py::b", "passed")])
    health = client.get(f"/api/v1/projects/{project.slug}/health").json()
    assert health["health"]["grade"] == "A"
    assert health["actions"]  # always at least one item

    # Introduce failures → grade should drop and an action should appear.
    _run(client, key, [("t.py::a", "failed"), ("t.py::b", "failed")])
    health2 = client.get(f"/api/v1/projects/{project.slug}/health").json()
    assert health2["health"]["grade"] != "A"
    assert any(act["priority"] == "high" for act in health2["actions"])


def test_cross_branch_compare(client, project_key):
    project, key = project_key
    _run(client, key, [("t.py::a", "passed"), ("t.py::b", "passed")], branch="main")
    _run(client, key, [("t.py::a", "failed"), ("t.py::b", "passed")], branch="feature")
    cmp = client.get(f"/api/v1/projects/{project.slug}/compare-branches",
                     params={"base": "main", "head": "feature"}).json()
    assert cmp["base_branch"] == "main" and cmp["head_branch"] == "feature"
    assert cmp["counts"]["newly_failing"] == 1

    missing = client.get(f"/api/v1/projects/{project.slug}/compare-branches",
                         params={"base": "main", "head": "nope"})
    assert missing.status_code == 404


def test_run_verdict_treats_flaky_as_non_blocking(client, project_key):
    project, key = project_key
    # A run with one hard failure and one flaky-pass.
    rid = _run(client, key, [("t.py::broken", "failed"), ("t.py::wobbly", "passed", True),
                             ("t.py::ok", "passed")])
    verdict = client.get(f"/api/v1/runs/{rid}/verdict").json()
    assert verdict["conclusion"] == "failure"  # the real failure blocks
    assert "t.py::broken" in verdict["blocking"]

    # A run whose only failure is a known-flaky test -> neutral (non-blocking).
    # Make t.py::flake flaky first via history, then fail it.
    for _ in range(6):
        _run(client, key, [("t.py::flake", "passed", True)])
    rid2 = _run(client, key, [("t.py::flake", "failed"), ("t.py::ok", "passed")])
    verdict2 = client.get(f"/api/v1/runs/{rid2}/verdict").json()
    assert verdict2["conclusion"] == "neutral"
