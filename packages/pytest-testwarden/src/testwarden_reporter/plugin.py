"""pytest-testwarden: streams results, retries and artifacts to a TestWarden server.

Design rules:
- The plugin must NEVER fail or slow a session because the server is down;
  all network errors disable reporting with one warning (see client.py).
- pytest-rerunfailures is supported: "rerun" outcomes become failed attempts
  on the same result envelope.
- xdist is not supported in v0.1 (each worker would create its own run).
"""
import os
import uuid
from pathlib import Path

import pytest

from testwarden_reporter import artifacts as artifact_discovery
from testwarden_reporter.client import TestwardenClient

BROWSERS = ("chromium", "firefox", "webkit")
STDIO_CAP = 64 * 1024


def pytest_addoption(parser):
    group = parser.getgroup("testwarden")
    group.addoption("--testwarden-url", default=None, help="TestWarden server URL")
    parser.addini("testwarden_url", "TestWarden server URL", default="")
    parser.addini("testwarden_api_key", "TestWarden project API key", default="")
    parser.addini("testwarden_enabled", "Enable TestWarden reporting", default="auto")
    parser.addini("testwarden_batch_size", "Results per ingestion batch", default="20")
    parser.addini("testwarden_upload_artifacts", "Upload artifacts (screenshots/traces)", default="true")
    parser.addini("testwarden_framework", "Framework label reported to the server", default="")


def _setting(config, ini_name: str, env_name: str) -> str:
    return os.environ.get(env_name) or str(config.getini(ini_name) or "")


def pytest_configure(config):
    url = os.environ.get("TESTWARDEN_URL") or config.getoption("--testwarden-url") or str(
        config.getini("testwarden_url") or ""
    )
    api_key = _setting(config, "testwarden_api_key", "TESTWARDEN_API_KEY")
    enabled = _setting(config, "testwarden_enabled", "TESTWARDEN_ENABLED").lower()
    if enabled in ("false", "0", "no", "off"):
        return
    if not url or not api_key:
        if enabled in ("true", "1", "yes", "on"):
            import warnings

            warnings.warn("testwarden: enabled but testwarden_url/api key missing; reporting off")
        return
    plugin = TestwardenPlugin(config, url, api_key)
    config.pluginmanager.register(plugin, "testwarden-reporter")
    config._testwarden = plugin


def _detect_framework(config) -> str:
    if config.pluginmanager.hasplugin("playwright"):
        return "pytest-playwright"
    return "pytest"


def _ci_metadata() -> dict:
    branch = os.environ.get("TESTWARDEN_BRANCH") or os.environ.get("GITHUB_REF_NAME")
    commit = os.environ.get("TESTWARDEN_COMMIT") or os.environ.get("GITHUB_SHA")
    ci_url = os.environ.get("TESTWARDEN_CI_URL")
    if not ci_url and os.environ.get("GITHUB_RUN_ID"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        ci_url = f"{server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return {
        "branch": branch,
        "commit_sha": commit,
        "ci_url": ci_url,
        "environment": os.environ.get("TESTWARDEN_ENVIRONMENT"),
    }


def _error_info(report) -> tuple[str | None, str | None, str | None]:
    """(error_type, error_message, stack_trace) from a failed report."""
    stack = getattr(report, "longreprtext", "") or None
    crash = getattr(getattr(report, "longrepr", None), "reprcrash", None)
    message = getattr(crash, "message", None)
    error_type = None
    if message and ":" in message.split("\n")[0]:
        candidate = message.split("\n")[0].split(":", 1)[0].strip()
        if candidate and " " not in candidate:
            error_type = candidate
    return error_type, message, stack


class _CaseState:
    __slots__ = ("finished_attempts", "attempt_artifacts", "current_reports", "manual_artifacts")

    def __init__(self):
        self.finished_attempts: list[dict] = []
        self.attempt_artifacts: list[list[tuple[Path, str]]] = []
        self.current_reports: dict[str, object] = {}
        self.manual_artifacts: list[tuple[Path, str]] = []


class TestwardenPlugin:
    def __init__(self, config, url: str, api_key: str):
        self.config = config
        self.run_uuid = str(uuid.uuid4())
        self.client = TestwardenClient(url, api_key)
        self.batch_size = int(_setting(config, "testwarden_batch_size", "TESTWARDEN_BATCH_SIZE") or 20)
        self.upload_artifacts = _setting(
            config, "testwarden_upload_artifacts", "TESTWARDEN_UPLOAD_ARTIFACTS"
        ).lower() not in ("false", "0", "no")
        self.framework = (
            _setting(config, "testwarden_framework", "TESTWARDEN_FRAMEWORK")
            or _detect_framework(config)
        )
        self._states: dict[str, _CaseState] = {}
        self._closed: list[tuple[dict, list[list[tuple[Path, str]]]]] = []
        self._output_snapshot: dict = {}
        self._finish_summary: dict = {}

    # -- output dir (pytest-playwright artifacts land here) -----------------
    def _output_dir(self) -> Path | None:
        try:
            output = self.config.getoption("--output")
        except (ValueError, KeyError):
            return None
        return Path(output) if output else None

    # -- session lifecycle ---------------------------------------------------
    def pytest_sessionstart(self, session):
        payload = {"run_uuid": self.run_uuid, "framework": self.framework, **_ci_metadata()}
        payload = {k: v for k, v in payload.items() if v is not None}
        self.client.create_run(payload)
        output_dir = self._output_dir()
        if output_dir:
            self._output_snapshot = artifact_discovery.snapshot(output_dir)

    def pytest_sessionfinish(self, session, exitstatus):
        # Close any dangling states (e.g. session interrupted mid-test).
        for nodeid in list(self._states):
            self._close_result(nodeid)
        self._flush()
        self._finish_summary = self.client.finish_run(self.run_uuid)
        self.client.close()

    def pytest_terminal_summary(self, terminalreporter):
        if self.client.disabled:
            terminalreporter.write_line("[testwarden] reporting was disabled due to errors")
        elif self._finish_summary:
            summary = self._finish_summary
            terminalreporter.write_line(
                f"[testwarden] run #{summary.get('run_id')} reported to {self.client.base_url} "
                f"({summary.get('passed')}/{summary.get('total')} passed, "
                f"{summary.get('flaky')} flaky)"
            )

    # -- per-test reporting ----------------------------------------------------
    def pytest_runtest_logreport(self, report):
        state = self._states.setdefault(report.nodeid, _CaseState())
        state.current_reports[report.when] = report
        if report.outcome == "rerun":
            # pytest-rerunfailures logs no teardown report for a rerun attempt:
            # the attempt is complete right now; keep the result open for the retry.
            self._record_attempt(report.nodeid, state, is_rerun=True)
            return
        if report.when == "teardown":
            self._close_result(report.nodeid)

    def _collect_new_artifacts(self, state: _CaseState) -> list[tuple[Path, str]]:
        found: list[tuple[Path, str]] = []
        output_dir = self._output_dir()
        if output_dir and self.upload_artifacts:
            current = artifact_discovery.snapshot(output_dir)
            found = artifact_discovery.diff_new_files(self._output_snapshot, current)
            self._output_snapshot = current
        found.extend(state.manual_artifacts)
        state.manual_artifacts = []
        return found

    def _record_attempt(self, nodeid: str, state: _CaseState, is_rerun: bool) -> None:
        reports = state.current_reports
        setup = reports.get("setup")
        call = reports.get("call")
        teardown = reports.get("teardown")

        status = "passed"
        failed_report = None
        if setup is not None and setup.outcome in ("failed", "error", "rerun"):
            status, failed_report = "error", setup
        elif setup is not None and setup.skipped:
            status = "xfailed" if getattr(setup, "wasxfail", None) else "skipped"
        elif call is not None and call.outcome in ("failed", "rerun"):
            status, failed_report = "failed", call
        elif call is not None and call.skipped:
            status = "xfailed" if getattr(call, "wasxfail", None) else "skipped"
        elif call is not None and call.passed and getattr(call, "wasxfail", None):
            status = "xpassed"
        elif teardown is not None and teardown.outcome == "failed":
            status, failed_report = "error", teardown

        duration_ms = int(
            sum(getattr(r, "duration", 0) or 0 for r in reports.values()) * 1000
        )
        error_type, error_message, stack = (
            _error_info(failed_report) if failed_report is not None else (None, None, None)
        )
        source = call or setup
        attempt = {
            "index": len(state.finished_attempts),
            "status": status,
            "duration_ms": duration_ms,
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack,
            "stdout": (getattr(source, "capstdout", "") or "")[:STDIO_CAP] or None,
            "stderr": (getattr(source, "capstderr", "") or "")[:STDIO_CAP] or None,
        }
        state.finished_attempts.append(attempt)
        state.attempt_artifacts.append(self._collect_new_artifacts(state))
        state.current_reports = {}

    def _close_result(self, nodeid: str) -> None:
        state = self._states.pop(nodeid, None)
        if state is None:
            return
        if state.current_reports:
            self._record_attempt(nodeid, state, is_rerun=False)
        if not state.finished_attempts:
            return
        final = state.finished_attempts[-1]
        normalized = nodeid.replace("\\", "/")
        parts = normalized.split("::")
        bracket = normalized[normalized.find("[") + 1 : normalized.rfind("]")] if "[" in normalized else ""
        browser = next((b for b in BROWSERS if b in bracket), None)
        envelope = {
            "result_ref": str(uuid.uuid4()),
            "framework": self.framework,
            "normalized_id": normalized,
            "file_path": parts[0],
            "suite": parts[1] if len(parts) > 2 else None,
            "title": parts[-1],
            "status": final["status"],
            "duration_ms": final["duration_ms"],
            "attempts": state.finished_attempts,
            "extras": {"browser": browser} if browser else {},
        }
        self._closed.append((envelope, state.attempt_artifacts))
        if len(self._closed) >= self.batch_size:
            self._flush()

    def _flush(self) -> None:
        if not self._closed:
            return
        batch, self._closed = self._closed, []
        ref_map = self.client.post_results(self.run_uuid, [envelope for envelope, _ in batch])
        if not ref_map:
            return
        for envelope, per_attempt in batch:
            result_id = ref_map.get(envelope["result_ref"])
            if result_id is None:
                continue
            for attempt_index, files in enumerate(per_attempt):
                for path, kind in files:
                    self.client.upload_artifact(
                        self.run_uuid, result_id, attempt_index, kind, path
                    )


@pytest.fixture
def testwarden_attach(request):
    """Attach an arbitrary file to the current test attempt:
    testwarden_attach("path/to/file.png", kind="screenshot")
    """
    plugin = getattr(request.config, "_testwarden", None)

    def attach(path, kind: str = "other"):
        if plugin is None:
            return
        state = plugin._states.setdefault(request.node.nodeid, _CaseState())
        state.manual_artifacts.append((Path(path), kind))

    return attach
