from pathlib import Path

import pytest

import testwarden_reporter.plugin as plugin_module

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
    monkeypatch.setattr(plugin_module, "TestwardenClient", FakeClient)
    monkeypatch.setenv("TESTWARDEN_URL", "http://testwarden.local")
    monkeypatch.setenv("TESTWARDEN_API_KEY", "twk_test")
    yield FakeClient
