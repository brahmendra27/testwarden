from pathlib import Path

import pytest

import flakelens_reporter.plugin as plugin_module

pytest_plugins = ["pytester"]


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, base_url, api_key, timeout=10.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.disabled = False
        self.runs: list[dict] = []
        self.batches: list[list[dict]] = []
        self.artifacts: list[tuple] = []
        self.finished = False
        self._next_id = 0
        FakeClient.instances.append(self)

    @property
    def envelopes(self) -> list[dict]:
        return [envelope for batch in self.batches for envelope in batch]

    def create_run(self, payload):
        self.runs.append(payload)
        return True

    def post_results(self, run_uuid, envelopes):
        self.batches.append(envelopes)
        ref_map = {}
        for envelope in envelopes:
            self._next_id += 1
            ref_map[envelope["result_ref"]] = self._next_id
        return ref_map

    def upload_artifact(self, run_uuid, result_id, attempt_index, kind, path):
        self.artifacts.append((result_id, attempt_index, kind, Path(path).name))

    def finish_run(self, run_uuid):
        self.finished = True
        return {"run_id": 1, "total": 0, "passed": 0, "flaky": 0, "status": "completed"}

    def close(self):
        pass


@pytest.fixture()
def fake_client(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(plugin_module, "FlakelensClient", FakeClient)
    monkeypatch.setenv("FLAKELENS_URL", "http://flakelens.local")
    monkeypatch.setenv("FLAKELENS_API_KEY", "flk_test")
    # pytest-playwright (installed for the sample project) wraps every test in a
    # soft-assertion scope that breaks pytester's nested in-process sessions;
    # disable it in the inner runs since these tests don't use a browser.
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p no:playwright")
    yield FakeClient
