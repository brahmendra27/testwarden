from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from testwarden.db import get_db
from testwarden.models import Artifact, Run, TestAttempt, TestCase, TestResult
from testwarden.api.projects import _run_summary, get_project_by_slug
from testwarden.services.stats import window_token

router = APIRouter(prefix="/api/v1", tags=["runs"])


def _get_run(run_id: int, db: Session) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/projects/{slug}/runs")
def list_runs(
    slug: str,
    branch: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    project = get_project_by_slug(slug, db)
    query = select(Run).where(Run.project_id == project.id)
    if branch:
        query = query.where(Run.branch == branch)
    if status:
        query = query.where(Run.status == status)
    runs = db.scalars(
        query.order_by(Run.started_at.desc()).limit(min(limit, 200)).offset(offset)
    ).all()
    return [_run_summary(run) for run in runs]


@router.get("/runs/{run_id}")
def run_detail(run_id: int, db: Session = Depends(get_db)):
    run = _get_run(run_id, db)
    summary = _run_summary(run)
    summary["project_id"] = run.project_id
    previous = db.scalar(
        select(Run)
        .where(
            Run.project_id == run.project_id,
            Run.started_at < run.started_at,
            Run.status == "completed",
            Run.branch == run.branch if run.branch else True,
        )
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    summary["previous_run_id"] = previous.id if previous else None
    return summary


@router.get("/runs/{run_id}/strip")
def run_strip(run_id: int, db: Session = Depends(get_db)):
    """Compact per-test strip: one entry per result in execution order."""
    _get_run(run_id, db)
    rows = db.execute(
        select(TestResult.test_case_id, TestResult.status, TestResult.is_flaky_in_run, TestCase.node_id)
        .join(TestCase, TestCase.id == TestResult.test_case_id)
        .where(TestResult.run_id == run_id)
        .order_by(TestResult.id)
    ).all()
    strip = []
    for case_id, status, flaky, node_id in rows:
        token = window_token(status, flaky) or ("K" if status in ("skipped", "xfailed") else "P")
        strip.append([case_id, token, node_id])
    return strip


@router.get("/runs/{run_id}/results")
def run_results(
    run_id: int,
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    _get_run(run_id, db)
    query = (
        select(TestResult, TestCase)
        .join(TestCase, TestCase.id == TestResult.test_case_id)
        .where(TestResult.run_id == run_id)
    )
    if status == "flaky":
        query = query.where(TestResult.is_flaky_in_run.is_(True))
    elif status:
        query = query.where(TestResult.status == status)
    if search:
        query = query.where(TestCase.node_id.ilike(f"%{search}%"))
    rows = db.execute(query.order_by(TestCase.file_path, TestCase.node_id)).all()
    return [
        {
            "result_id": result.id,
            "test_case_id": case.id,
            "node_id": case.node_id,
            "file_path": case.file_path,
            "title": case.title,
            "status": result.status,
            "is_flaky_in_run": result.is_flaky_in_run,
            "attempt_count": result.attempt_count,
            "duration_ms": result.duration_ms,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "extras": result.extras or {},
        }
        for result, case in rows
    ]


@router.get("/results/{result_id}")
def result_detail(result_id: int, db: Session = Depends(get_db)):
    result = db.get(TestResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    case = db.get(TestCase, result.test_case_id)
    attempts = db.scalars(
        select(TestAttempt)
        .where(TestAttempt.result_id == result.id)
        .order_by(TestAttempt.attempt_index)
    ).all()
    attempt_ids = [a.id for a in attempts]
    artifacts = (
        db.scalars(select(Artifact).where(Artifact.attempt_id.in_(attempt_ids))).all()
        if attempt_ids
        else []
    )
    artifacts_by_attempt: dict[int, list] = {}
    for artifact in artifacts:
        artifacts_by_attempt.setdefault(artifact.attempt_id, []).append(
            {
                "id": artifact.id,
                "kind": artifact.kind,
                "file_name": artifact.file_name,
                "content_type": artifact.content_type,
                "size_bytes": artifact.size_bytes,
                "url": f"/api/v1/artifacts/{artifact.id}",
            }
        )
    return {
        "result_id": result.id,
        "run_id": result.run_id,
        "test_case_id": case.id,
        "node_id": case.node_id,
        "file_path": case.file_path,
        "title": case.title,
        "status": result.status,
        "is_flaky_in_run": result.is_flaky_in_run,
        "duration_ms": result.duration_ms,
        "error_type": result.error_type,
        "error_message": result.error_message,
        "failure_fingerprint": result.failure_fingerprint,
        "extras": result.extras or {},
        "attempts": [
            {
                "id": attempt.id,
                "attempt_index": attempt.attempt_index,
                "status": attempt.status,
                "duration_ms": attempt.duration_ms,
                "error_type": attempt.error_type,
                "error_message": attempt.error_message,
                "stack_trace": attempt.stack_trace,
                "stdout": attempt.stdout,
                "stderr": attempt.stderr,
                "artifacts": artifacts_by_attempt.get(attempt.id, []),
            }
            for attempt in attempts
        ],
    }
