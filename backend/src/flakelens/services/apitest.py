"""API-testing agent: reads an OpenAPI spec, generates a pytest+httpx suite
(RestAssured-style assertions), verifies it against the live API, then runs it
with the FlakeLens reporter so results land in the dashboard as a normal run.
"""
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

from flakelens.auth import create_api_key
from flakelens.config import settings
from flakelens.db import SessionLocal
from flakelens.models import ApiKey, ApiTestJob, Project, Run
from flakelens.services.autofix import MODEL, run_agent
from flakelens.services.workspace import FixWorkspace, WorkspaceError

SPEC_CHAR_LIMIT = 80_000

SYSTEM_PROMPT = """You are FlakeLens's API-testing agent. Given an OpenAPI spec, you write a \
production-quality pytest + httpx test suite (RestAssured-style: explicit status, header and \
body assertions) and verify it runs against the live API.

Requirements for the suite you generate:
- Put tests under tests/, plus a conftest.py with a `base_url` fixture read from the \
API_BASE_URL environment variable and an httpx.Client fixture with a 10s timeout.
- Cover the main endpoints: happy-path GET requests asserting status code, content-type and \
key response fields/shapes; negative cases (missing auth -> 401/403, unknown resource -> 404, \
invalid payload -> 4xx) where the spec implies them.
- NEVER call destructive or state-changing endpoints (POST/PUT/PATCH/DELETE) with valid data \
unless the spec marks them safe; testing that they REJECT invalid/unauthenticated requests is \
encouraged.
- Tests must be deterministic and independent; no sleeps; small and readable, one behavior per test.
- Use plain pytest + httpx only (both installed). No other libraries.
- Iterate: write the files, then use run_tests to execute them against the live API, and fix \
any failures you caused (assertion too strict, wrong path). A test that fails because the API \
is genuinely broken should stay failing - note it in your summary.
- When the suite runs cleanly (real API bugs excepted), call finish with a summary of coverage."""


def _fetch_spec(spec_url: str) -> str:
    local = Path(spec_url)
    if local.is_file():
        text = local.read_text(encoding="utf-8", errors="replace")
    else:
        response = httpx.get(spec_url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        text = response.text
    if len(text) > SPEC_CHAR_LIMIT:
        text = text[:SPEC_CHAR_LIMIT] + "\n... [spec truncated]"
    return text


def _collect_code(workspace: FixWorkspace) -> str:
    parts = []
    for rel in workspace.list_files("*.py", limit=50):
        parts.append(f"# ===== {rel} =====\n{workspace.read_file(rel)}")
    return "\n\n".join(parts)


def execute_apitest_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(ApiTestJob, job_id)

        def log(line: str) -> None:
            job.log = (job.log or "") + line + "\n"
            db.commit()

        try:
            project = db.get(Project, job.project_id)
            job.status = "running"
            job.model = MODEL
            db.commit()

            log(f"Fetching OpenAPI spec from {job.spec_url} ...")
            spec = _fetch_spec(job.spec_url)

            workdir = Path(settings.artifact_dir).parent / "agent-workspaces" / f"apitest-{job.id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)
            workspace = FixWorkspace("(generated)", workdir)
            workspace.init_empty()
            log(f"Workspace ready. Starting agent ({MODEL}) ...")

            task = (
                f"Target API base URL: {job.base_url}\n"
                f"(run_tests already exports API_BASE_URL={job.base_url})\n\n"
                f"OpenAPI specification:\n{spec}\n\n"
                "Generate the test suite, verify it with run_tests, then call finish."
            )

            import anthropic

            client = anthropic.Anthropic()
            original_run_tests = workspace.run_tests

            def run_tests_with_base_url(args, cwd=".", timeout=300, extra_env=None):
                env = {"API_BASE_URL": job.base_url, **(extra_env or {})}
                return original_run_tests(args, cwd=cwd, timeout=timeout, extra_env=env)

            workspace.run_tests = run_tests_with_base_url  # agent iterations hit the live API

            started = time.monotonic()
            verdict = run_agent(client, workspace, task, log, system=SYSTEM_PROMPT)
            log(f"Agent finished in {time.monotonic() - started:.0f}s: {verdict['outcome']}")

            job.code = _collect_code(workspace) or None
            job.summary = verdict["summary"]
            if not job.code:
                raise WorkspaceError("Agent generated no test files")

            log("Executing final suite with FlakeLens reporting enabled ...")
            key = create_api_key(db, project, name=f"api-agent job {job.id}")
            db.commit()
            try:
                output = original_run_tests(
                    ".",
                    extra_env={
                        "API_BASE_URL": job.base_url,
                        "FLAKELENS_ENABLED": "true",
                        "FLAKELENS_URL": settings.public_url,
                        "FLAKELENS_API_KEY": key,
                        "FLAKELENS_FRAMEWORK": "pytest-httpx",
                        "FLAKELENS_BRANCH": "api-agent",
                    },
                )
                log(output.splitlines()[-1] if output.strip() else "(no output)")
            finally:
                key_row = db.scalar(
                    select(ApiKey).where(ApiKey.key_prefix == key[:12], ApiKey.project_id == project.id)
                )
                if key_row is not None:
                    key_row.revoked_at = datetime.now(timezone.utc)
                    db.commit()

            run = db.scalar(
                select(Run)
                .where(
                    Run.project_id == project.id,
                    Run.framework == "pytest-httpx",
                    Run.started_at >= job.created_at,
                )
                .order_by(Run.id.desc())
            )
            if run is not None:
                job.run_id = run.id
                log(f"Results reported as run #{run.id}.")
            else:
                log("WARNING: no reported run found - check FLAKELENS_URL reachability.")
            job.status = "completed"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:2000]
            log(f"ERROR: {exc}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
