"""Offline tests for the API-testing agent (fake Claude, no network)."""
import uuid
from types import SimpleNamespace

from flakelens.services.autofix import run_agent
from flakelens.services.apitest import SYSTEM_PROMPT, _collect_code, _fetch_spec
from flakelens.services.workspace import FixWorkspace

GENERATED_TEST = '''import httpx

def test_health(base_url):
    response = httpx.get(f"{base_url}/api/v1/health", timeout=10)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
'''

CONFTEST = '''import os
import pytest

@pytest.fixture()
def base_url():
    return os.environ["API_BASE_URL"].rstrip("/")
'''


def test_fetch_spec_local_file(tmp_path):
    spec = tmp_path / "openapi.json"
    spec.write_text('{"openapi": "3.1.0"}')
    assert _fetch_spec(str(spec)) == '{"openapi": "3.1.0"}'


def test_init_empty_workspace(tmp_path):
    ws = FixWorkspace("(generated)", tmp_path / "w")
    ws.init_empty()
    ws.write_file("tests/test_x.py", "def test_a(): pass\n")
    assert ws.list_files("*.py") == ["tests/test_x.py"]
    code = _collect_code(ws)
    assert "===== tests/test_x.py =====" in code


class FakeClient:
    """Scripted generation: conftest + test file, then finish."""

    def __init__(self):
        self.step = 0
        self.messages = SimpleNamespace(create=self._create)

    def _block(self, name, tool_input):
        return SimpleNamespace(
            type="tool_use", id=f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=tool_input
        )

    def _create(self, **kwargs):
        assert kwargs["system"] == SYSTEM_PROMPT
        script = [
            [
                self._block("write_file", {"path": "conftest.py", "content": CONFTEST}),
                self._block("write_file", {"path": "tests/test_health.py", "content": GENERATED_TEST}),
            ],
            # the loop's finish-gate requires a run_tests after the last write
            [self._block("run_tests", {"args": "--collect-only -q"})],
            [self._block("finish", {"outcome": "fixed", "summary": "1 endpoint covered."})],
        ]
        content = script[self.step]
        self.step += 1
        return SimpleNamespace(content=content, stop_reason="tool_use")


def test_generation_loop_writes_suite(tmp_path):
    ws = FixWorkspace("(generated)", tmp_path / "w")
    ws.init_empty()
    lines = []
    verdict = run_agent(FakeClient(), ws, "generate tests", lines.append, system=SYSTEM_PROMPT)
    assert verdict["outcome"] == "fixed"
    assert set(ws.list_files("*.py")) == {"conftest.py", "tests/test_health.py"}


def test_api_agent_endpoints(client, project_key, monkeypatch):
    project, _ = project_key
    slug = project.slug

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post(
        f"/api/v1/projects/{slug}/api-agent",
        json={"spec_url": "http://x/openapi.json", "base_url": "http://x"},
    )
    assert response.status_code == 503

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    executed = []
    monkeypatch.setattr(
        "flakelens.api.apitest.execute_apitest_job", lambda job_id: executed.append(job_id)
    )
    body = client.post(
        f"/api/v1/projects/{slug}/api-agent",
        json={"spec_url": "http://x/openapi.json", "base_url": "http://x/"},
    ).json()
    assert body["status"] == "queued"
    assert body["base_url"] == "http://x"  # trailing slash stripped
    assert executed == [body["id"]]

    latest = client.get(f"/api/v1/projects/{slug}/api-agent").json()
    assert latest["job"]["id"] == body["id"]
    assert client.get(f"/api/v1/api-agent-jobs/{body['id']}").json()["spec_url"] == "http://x/openapi.json"

    # queued job blocks a duplicate
    dup = client.post(
        f"/api/v1/projects/{slug}/api-agent",
        json={"spec_url": "http://x/openapi.json", "base_url": "http://x"},
    )
    assert dup.status_code == 409
