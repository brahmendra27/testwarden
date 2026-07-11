"""Tests for the Reproducer: pure ladder search + endpoints."""
import uuid

from flakelens.services.reproducer import (
    is_repro,
    label_recipe,
    merge_recipes,
    minimize_candidates,
)
from flakelens.services.reproducer_exec import search_reproducer


def test_is_repro_thresholds():
    assert is_repro(0.8, baseline=0.1) is True
    assert is_repro(0.5, baseline=0.1) is False  # below 60%
    assert is_repro(0.7, baseline=0.5) is False  # lift too small
    assert is_repro(1.0, baseline=0.0) is True


def test_label_recipe():
    assert "CPU 4×" in label_recipe({"cpu_throttle": 4})
    assert "+500ms" in label_recipe({"network": [{"url": "**/*", "delay_ms": 500}]})
    assert label_recipe({}) == "no perturbation"


def test_merge_recipes_concats_network():
    merged = merge_recipes([
        {"network": [{"url": "a", "delay_ms": 1}]},
        {"network": [{"url": "b", "delay_ms": 2}]},
        {"cpu_throttle": 4},
    ])
    assert len(merged["network"]) == 2
    assert merged["cpu_throttle"] == 4


def test_minimize_candidates_gets_gentler():
    delays = [c[0]["network"][0]["delay_ms"] for c in minimize_candidates("network")]
    assert delays == sorted(delays, reverse=True)  # gentlest last


def test_search_reproduces_a_network_race():
    """Synthetic flake: only fails when network latency >= 200ms."""
    def run_fn(recipe):
        for rule in recipe.get("network", []) or []:
            if rule.get("delay_ms", 0) >= 200:
                return True
        return False

    result = search_reproducer(run_fn, log=lambda _l: None, baseline_runs=4, probe_runs=4)
    assert result["outcome"] == "reproduced"
    assert result["baseline_fail_rate"] == 0.0
    # minimized to the gentlest network delay that still triggers (200ms)
    assert result["recipe"]["network"][0]["delay_ms"] == 200


def test_search_gives_up_on_true_randomness():
    """A coin-flip flake no perturbation can pin down."""
    import random

    rng = random.Random(1)

    def run_fn(recipe):
        return rng.random() < 0.4  # ~40% regardless of recipe

    result = search_reproducer(run_fn, log=lambda _l: None, baseline_runs=6, probe_runs=6)
    assert result["outcome"] == "not_reproduced"


def test_search_flags_deterministic_break_as_not_flaky():
    result = search_reproducer(lambda r: True, log=lambda _l: None, baseline_runs=4, probe_runs=4)
    assert result["outcome"] == "not_reproduced"
    assert "deterministic" in (result["note"] or "")


def _make_flaky_case(client, key):
    node = "tests/test_r.py::test_racy"
    for index in range(6):
        run_uuid = str(uuid.uuid4())
        client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid},
                    headers={"X-Api-Key": key})
        status = "passed" if index % 2 == 0 else "failed"
        client.post(
            f"/api/v1/ingest/runs/{run_uuid}/results",
            json={"results": [{
                "result_ref": str(uuid.uuid4()), "framework": "pytest",
                "normalized_id": node, "file_path": "tests/test_r.py",
                "title": "test_racy", "status": status, "duration_ms": 50,
                "attempts": [] if status == "passed" else
                [{"index": 0, "status": "failed", "error_type": "TimeoutError",
                  "error_message": "race"}],
            }]},
            headers={"X-Api-Key": key},
        )
        client.post(f"/api/v1/ingest/runs/{run_uuid}/finish", headers={"X-Api-Key": key})
    from sqlalchemy import select
    from flakelens.models import TestCase
    return node


def test_reproducer_endpoints(client, project_key, db, monkeypatch):
    project, key = project_key
    _make_flaky_case(client, key)
    from sqlalchemy import select
    from flakelens.models import TestCase
    case_id = db.scalar(select(TestCase.id).where(TestCase.project_id == project.id))

    executed = []
    monkeypatch.setattr(
        "flakelens.api.reproducer.execute_repro_job", lambda job_id: executed.append(job_id)
    )
    body = client.post(f"/api/v1/tests/{case_id}/reproducer").json()
    assert body["status"] == "queued"
    assert executed == [body["id"]]

    latest = client.get(f"/api/v1/tests/{case_id}/reproducer").json()
    assert latest["job"]["id"] == body["id"]
    assert client.get(f"/api/v1/reproducer-jobs/{body['id']}").json()["test_case_id"] == case_id

    # active job blocks a duplicate
    assert client.post(f"/api/v1/tests/{case_id}/reproducer").status_code == 409
