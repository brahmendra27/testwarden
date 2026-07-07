"""Offline tests for the auto-fix agent: real git workspace, fake Claude client."""
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from testwarden.services.autofix import TOOLS, run_agent
from testwarden.services.workspace import FixWorkspace, WorkspaceError


@pytest.fixture()
def source_repo(tmp_path):
    """A local git repo containing a trivially broken function + test."""
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b  # bug\n")
    (repo / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    for args in (
        ["init", "-b", "main"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "init"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture()
def workspace(source_repo, tmp_path):
    ws = FixWorkspace(str(source_repo), tmp_path / "work")
    ws.clone()
    return ws


def test_clone_branch_edit_diff_commit(workspace):
    assert workspace.default_branch() == "main"
    workspace.create_branch("testwarden/fix-add-1")
    assert "calc.py" in workspace.list_files("*.py")
    assert "return a - b" in workspace.read_file("calc.py")

    workspace.edit_file("calc.py", "return a - b  # bug", "return a + b")
    diff = workspace.diff()
    assert "+    return a + b" in diff
    workspace.commit("fix add")
    assert workspace.diff() == ""  # nothing staged after commit


def test_path_safety(workspace):
    with pytest.raises(WorkspaceError):
        workspace.read_file("../../outside.txt")
    with pytest.raises(WorkspaceError):
        workspace.write_file("..\\escape.txt", "nope")


def test_edit_requires_unique_match(workspace):
    with pytest.raises(WorkspaceError):
        workspace.edit_file("calc.py", "not in file", "x")


def test_run_tests_executes_pytest(workspace):
    output = workspace.run_tests("test_calc.py")
    assert "exit code: 1" in output  # broken on purpose
    workspace.edit_file("calc.py", "return a - b  # bug", "return a + b")
    output = workspace.run_tests("test_calc.py")
    assert "exit code: 0" in output


class FakeClient:
    """Scripted Claude: read the file, fix it, verify, finish."""

    def __init__(self):
        self.step = 0
        self.messages = SimpleNamespace(create=self._create)

    def _block(self, name, tool_input):
        return SimpleNamespace(
            type="tool_use", id=f"toolu_{uuid.uuid4().hex[:8]}", name=name, input=tool_input
        )

    def _create(self, **kwargs):
        script = [
            [self._block("read_file", {"path": "calc.py"})],
            [self._block("edit_file", {
                "path": "calc.py", "old_str": "return a - b  # bug", "new_str": "return a + b",
            })],
            [self._block("run_tests", {"args": "test_calc.py"})],
            [self._block("finish", {"outcome": "fixed", "summary": "Fixed subtraction typo."})],
        ]
        content = script[self.step]
        self.step += 1
        return SimpleNamespace(content=content, stop_reason="tool_use")


def test_agent_loop_with_fake_client(workspace):
    workspace.create_branch("testwarden/fix-add-2")
    log_lines = []
    verdict = run_agent(FakeClient(), workspace, "fix the failing test", log_lines.append)
    assert verdict == {"outcome": "fixed", "summary": "Fixed subtraction typo."}
    assert any("edit_file" in line for line in log_lines)
    assert "+    return a + b" in workspace.diff()


def test_tool_schemas_are_wellformed():
    names = {tool["name"] for tool in TOOLS}
    assert {"list_files", "read_file", "edit_file", "write_file", "run_tests", "finish"} <= names
    for tool in TOOLS:
        assert tool["input_schema"]["type"] == "object"


def test_autofix_endpoints(client, project_key, db, monkeypatch):
    _, key = project_key
    run_uuid = str(uuid.uuid4())
    client.post("/api/v1/ingest/runs", json={"run_uuid": run_uuid}, headers={"X-Api-Key": key})
    envelope = {
        "result_ref": str(uuid.uuid4()),
        "framework": "pytest",
        "normalized_id": "test_calc.py::test_add",
        "file_path": "test_calc.py",
        "title": "test_add",
        "status": "failed",
        "duration_ms": 10,
        "attempts": [{"index": 0, "status": "failed", "error_type": "AssertionError",
                      "error_message": "assert -1 == 5"}],
    }
    ref_map = client.post(
        f"/api/v1/ingest/runs/{run_uuid}/results",
        json={"results": [envelope]}, headers={"X-Api-Key": key},
    ).json()["results"]
    result_id = ref_map[envelope["result_ref"]]

    # Without a key the endpoint refuses cleanly
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post(f"/api/v1/results/{result_id}/autofix").status_code == 503

    # With a key it queues a job (executor stubbed out)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    executed = []
    monkeypatch.setattr(
        "testwarden.api.autofix.execute_autofix_job", lambda job_id: executed.append(job_id)
    )
    body = client.post(f"/api/v1/results/{result_id}/autofix").json()
    assert body["status"] == "queued"
    assert executed == [body["id"]]

    latest = client.get(f"/api/v1/results/{result_id}/autofix").json()
    assert latest["job"]["id"] == body["id"]
    job = client.get(f"/api/v1/agent-jobs/{body['id']}").json()
    assert job["result_id"] == result_id

    # A queued job blocks duplicates
    assert client.post(f"/api/v1/results/{result_id}/autofix").status_code == 409


def test_update_project_repo_url(client, project_key):
    project, _ = project_key
    response = client.patch(
        f"/api/v1/projects/{project.slug}", json={"repo_url": "https://github.com/acme/web"}
    )
    assert response.json()["repo_url"] == "https://github.com/acme/web"
