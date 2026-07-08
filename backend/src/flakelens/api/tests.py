from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import Run, TestCase, TestResult

router = APIRouter(prefix="/api/v1/tests", tags=["tests"])

HISTORY_LIMIT = 50


@router.get("/{case_id}")
def test_detail(case_id: int, db: Session = Depends(get_db)):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    rows = db.execute(
        select(TestResult, Run)
        .join(Run, Run.id == TestResult.run_id)
        .where(TestResult.test_case_id == case_id)
        .order_by(TestResult.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = [
        {
            "result_id": result.id,
            "run_id": run.id,
            "run_started_at": run.started_at.isoformat() if run.started_at else None,
            "branch": run.branch,
            "status": result.status,
            "is_flaky_in_run": result.is_flaky_in_run,
            "attempt_count": result.attempt_count,
            "duration_ms": result.duration_ms,
            "error_type": result.error_type,
            "error_message": result.error_message,
            "failure_fingerprint": result.failure_fingerprint,
        }
        for result, run in rows
    ]
    history.reverse()  # oldest -> newest for charts
    return {
        "id": case.id,
        "project_id": case.project_id,
        "node_id": case.node_id,
        "file_path": case.file_path,
        "suite": case.suite,
        "title": case.title,
        "framework": case.framework,
        "last_status": case.last_status,
        "flake_score": case.flake_score,
        "is_flaky": case.is_flaky,
        "flip_count": case.flip_count,
        "avg_duration_ms": case.avg_duration_ms,
        "p95_duration_ms": case.p95_duration_ms,
        "recent_statuses": case.recent_statuses or [],
        "history": history,
    }
