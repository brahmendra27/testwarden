"""pytest-flakelens: streams results, retries and artifacts to a FlakeLens server.

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

from flakelens_reporter import artifacts as artifact_discovery
from flakelens_reporter.client import FlakelensClient

BROWSERS = ("chromium", "firefox", "webkit")
STDIO_CAP = 64 * 1024


def pytest_addoption(parser):
    group = parser.getgroup("flakelens")
    group.addoption("--flakelens-url", default=None, help="FlakeLens server URL")
    parser.addini("flakelens_url", "FlakeLens server URL", default="")
    parser.addini("flakelens_api_key", "FlakeLens project API key", default="")
    parser.addini("flakelens_enabled", "Enable FlakeLens reporting", default="auto")
    parser.addini("flakelens_batch_size", "Results per ingestion batch", default="20")
    parser.addini("flakelens_upload_artifacts", "Upload artifacts (screenshots/traces)", default="true")
    parser.addini("flakelens_framework", "Framework label reported to the server", default="")


def _setting(config, ini_name: str, env_name: str) -> str:
    return os.environ.get(env_name) or str(config.getini(ini_name) or "")


def pytest_collection_modifyitems(config, items):
    """Quarantined tests still run, but under non-strict xfail so CI stays green.

    Their true outcome (xpassed = healthy, xfailed = still broken) is reported
    to FlakeLens, which decides when they are ready to be released.
    """
    for item in items:
        if item.get_closest_marker("quarantine") is not None:
            item.add_marker(
                pytest.mark.xfail(reason="quarantined by FlakeLens", strict=False)
            )
            plugin = getattr(config, "_flakelens", None)
            if plugin is not None:
                plugin.quarantined_nodeids.add(item.nodeid)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "quarantine: test is quarantined by FlakeLens - runs as non-strict xfail so CI stays green",
    )
    url = os.environ.get("FLAKELENS_URL") or config.getoption("--flakelens-url") or str(
        config.getini("flakelens_url") or ""
    )
    api_key = _setting(config, "flakelens_api_key", "FLAKELENS_API_KEY")
    enabled = _setting(config, "flakelens_enabled", "FLAKELENS_ENABLED").lower()
    if enabled in ("false", "0", "no", "off"):
        return
    if not url or not api_key:
        if enabled in ("true", "1", "yes", "on"):
            import warnings

            warnings.warn("flakelens: enabled but flakelens_url/api key missing; reporting off")
        return
    plugin = FlakelensPlugin(config, url, api_key)
    config.pluginmanager.register(plugin, "flakelens-reporter")
    config._flakelens = plugin


def _detect_framework(config) -> str:
    if config.pluginmanager.hasplugin("playwright"):
        return "pytest-playwright"
    return "pytest"


def _ci_metadata() -> dict:
    branch = os.environ.get("FLAKELENS_BRANCH") or os.environ.get("GITHUB_REF_NAME")
    commit = os.environ.get("FLAKELENS_COMMIT") or os.environ.get("GITHUB_SHA")
    ci_url = os.environ.get("FLAKELENS_CI_URL")
    if not ci_url and os.environ.get("GITHUB_RUN_ID"):
        server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        ci_url = f"{server}/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return {
        "branch": branch,
        "commit_sha": commit,
        "ci_url": ci_url,
        "environment": os.environ.get("FLAKELENS_ENVIRONMENT"),
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


class FlakelensPlugin:
    def __init__(self, config, url: str, api_key: str):
        self.config = config
        self.run_uuid = str(uuid.uuid4())
        self.client = FlakelensClient(url, api_key)
        self.batch_size = int(_setting(config, "flakelens_batch_size", "FLAKELENS_BATCH_SIZE") or 20)
        self.upload_artifacts = _setting(
            config, "flakelens_upload_artifacts", "FLAKELENS_UPLOAD_ARTIFACTS"
        ).lower() not in ("false", "0", "no")
        self.framework = (
            _setting(config, "flakelens_framework", "FLAKELENS_FRAMEWORK")
            or _detect_framework(config)
        )
        self.quarantined_nodeids: set[str] = set()
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
            terminalreporter.write_line("[flakelens] reporting was disabled due to errors")
        elif self._finish_summary:
            summary = self._finish_summary
            terminalreporter.write_line(
                f"[flakelens] run #{summary.get('run_id')} reported to {self.client.base_url} "
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
        extras: dict = {}
        if browser:
            extras["browser"] = browser
        if nodeid in self.quarantined_nodeids:
            extras["quarantined"] = True
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
            "extras": extras,
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
def flakelens_attach(request):
    """Attach an arbitrary file to the current test attempt:
    flakelens_attach("path/to/file.png", kind="screenshot")
    """
    plugin = getattr(request.config, "_flakelens", None)

    def attach(path, kind: str = "other"):
        if plugin is None:
            return
        state = plugin._states.setdefault(request.node.nodeid, _CaseState())
        state.manual_artifacts.append((Path(path), kind))

    return attach
