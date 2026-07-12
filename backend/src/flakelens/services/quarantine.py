"""Quarantine-and-heal loop.

Lifecycle: flaky test detected -> quarantine agent lands a
`@pytest.mark.quarantine` marker (PR/branch) so CI goes green -> the test keeps
running under xfail and its real outcomes keep feeding the flake window ->
SelfHeal fixes the root cause -> after a clean streak the release agent removes
the marker.
"""
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from flakelens.config import settings
from flakelens.db import SessionLocal
from flakelens.models import AgentJob, Project, Run, TestCase, TestResult
from flakelens.services.autofix import MODEL, run_agent
from flakelens.services.workspace import FixWorkspace, WorkspaceError

# Consecutive clean passes (while quarantined) before we call it healed.
RELEASE_STREAK = 5

QUARANTINE_PROMPT = """You are FlakeLens's quarantine agent. Add the marker \
`@pytest.mark.quarantine` to EXACTLY ONE test function, so this flaky test stops \
failing CI while it awaits a fix.

Rules:
- Locate the test (the recorded file path may be relative to a subproject; use list_files).
- Add the decorator directly above the test function. Add `import pytest` only if missing.
- Change NOTHING else - no other tests, no formatting churn.
- Verify with run_tests using --collect-only that the file still collects without errors.
- Then call finish with a one-line summary."""

RELEASE_PROMPT = """You are FlakeLens's release agent. Remove the \
`@pytest.mark.quarantine` marker from EXACTLY ONE test function - it has been \
verified healthy and should count in CI again.

Rules:
- Locate the test and remove only its quarantine decorator (leave `import pytest` alone).
- Change NOTHING else.
- Verify with run_tests using --collect-only that the file still collects without errors.
- Then call finish with a one-line summary."""


def latest_result_id(db, case: TestCase) -> int | None:
    return db.scalar(
        select(TestResult.id)
        .where(TestResult.test_case_id == case.id)
        .order_by(TestResult.id.desc())
        .limit(1)
    )


def latest_failing_result(db, case: TestCase) -> TestResult | None:
    """Most recent result with a real failure signal (incl. quarantined xfails)."""
    results = db.scalars(
        select(TestResult)
        .where(TestResult.test_case_id == case.id)
        .order_by(TestResult.id.desc())
        .limit(20)
    ).all()
    for result in results:
        if result.status in ("failed", "error") or (
            result.status == "xfailed" and (result.extras or {}).get("quarantined")
        ):
            return result
        if result.is_flaky_in_run:
            return result
    return None


def release_ready(case: TestCase) -> bool:
    """Quarantined and the last RELEASE_STREAK window entries are clean passes."""
    if case.quarantined_at is None:
        return False
    entries = case.recent_statuses or []
    if len(entries) < RELEASE_STREAK:
        return False
    return all(entry["t"] == "P" for entry in entries[-RELEASE_STREAK:])


def execute_marker_job(job_id: int) -> None:
    """Runs the quarantine or release agent for AgentJob kinds 'quarantine'/'release'."""
    db = SessionLocal()
    try:
        job = db.get(AgentJob, job_id)

        def log(line: str) -> None:
            job.log = (job.log or "") + line + "\n"
            db.commit()

        try:
            result = db.get(TestResult, job.result_id)
            case = db.get(TestCase, result.test_case_id)
            run = db.get(Run, result.run_id)
            project = db.get(Project, case.project_id)
            quarantining = job.kind == "quarantine"

            job.status = "running"
            job.model = MODEL
            db.commit()

            if not project.repo_url:
                raise WorkspaceError("Project has no repo_url configured")

            workdir = Path(settings.artifact_dir).parent / "agent-workspaces" / f"job-{job.id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)
            workspace = FixWorkspace(project.repo_url, workdir)
            log(f"Cloning {project.repo_url} ...")
            workspace.clone(commit_sha=run.commit_sha)
            base_branch = workspace.default_branch()
            action = "quarantine" if quarantining else "release"
            branch = f"selfheal/{action}-{case.id}-{job.id}"
            workspace.create_branch(branch)
            job.branch = branch

            task = (
                f"Test: {case.node_id}\n"
                f"Recorded file path (may be relative to a subproject): {case.file_path}\n"
                f"Cross-run flake score: {case.flake_score}\n"
            )
            from flakelens.services.llm import make_client

            client = make_client()
            log(f"Starting {action} agent ({MODEL}) ...")
            started = time.monotonic()
            verdict = run_agent(
                client, workspace, task, log,
                system=QUARANTINE_PROMPT if quarantining else RELEASE_PROMPT,
            )
            log(f"Agent finished in {time.monotonic() - started:.0f}s: {verdict['outcome']}")

            diff = workspace.diff()
            job.summary = verdict["summary"]
            job.diff = diff or None
            if verdict["outcome"] != "fixed" or not diff.strip():
                job.status = "failed"
                job.error = "Agent made no changes" if not diff.strip() else f"Agent outcome: {verdict['outcome']}"
            else:
                workspace.commit(
                    f"{'chore: quarantine' if quarantining else 'chore: release'} "
                    f"{case.title} (FlakeLens SelfHeal #{job.id})"
                )
                token = os.environ.get("FLAKELENS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
                if token and workspace.github_repo():
                    verb = "Quarantine flaky test" if quarantining else "Release healed test"
                    job.pr_url = workspace.push_and_open_pr(
                        branch, base_branch, f"[FlakeLens] {verb}: {case.title}",
                        f"{verdict['summary']}\n\n🤖 FlakeLens quarantine-and-heal loop.",
                        token,
                    )
                    log(f"Pull request opened: {job.pr_url}")
                else:
                    log("No GitHub token / remote - change left on local branch.")
                if quarantining:
                    case.quarantined_at = datetime.now(timezone.utc)
                    case.quarantine_branch = branch
                    case.quarantine_pr_url = job.pr_url
                else:
                    case.quarantined_at = None
                    case.quarantine_branch = None
                    case.quarantine_pr_url = None
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
