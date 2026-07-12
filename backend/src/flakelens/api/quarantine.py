import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.api.projects import get_project_by_slug
from flakelens.db import get_db
from flakelens.models import AgentJob, TestCase
from flakelens.services.autofix import execute_autofix_job
from flakelens.services.llm import llm_available
from flakelens.services.quarantine import (
    execute_marker_job,
    latest_failing_result,
    latest_result_id,
    release_ready,
)

router = APIRouter(prefix="/api/v1", tags=["quarantine"])

_AGENT_KINDS = ("quarantine", "release", "autofix")


def _require_ai() -> None:
    if not llm_available():
        raise HTTPException(
            status_code=503, detail="Agent unavailable: set ANTHROPIC_API_KEY or FLAKELENS_LLM_BASE_URL on the server"
        )


def _get_case(case_id: int, db: Session) -> TestCase:
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    return case


def _active_job(db: Session, case_result_ids: list[int]) -> AgentJob | None:
    if not case_result_ids:
        return None
    return db.scalar(
        select(AgentJob).where(
            AgentJob.result_id.in_(case_result_ids),
            AgentJob.status.in_(("queued", "running")),
        )
    )


def _case_result_ids(db: Session, case_id: int) -> list[int]:
    from flakelens.models import TestResult

    return list(
        db.scalars(select(TestResult.id).where(TestResult.test_case_id == case_id)).all()
    )


def _latest_job(db: Session, case_id: int) -> AgentJob | None:
    ids = _case_result_ids(db, case_id)
    if not ids:
        return None
    return db.scalar(
        select(AgentJob)
        .where(AgentJob.result_id.in_(ids), AgentJob.kind.in_(_AGENT_KINDS))
        .order_by(AgentJob.id.desc())
    )


def _job_payload(job: AgentJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "branch": job.branch,
        "pr_url": job.pr_url,
        "error": job.error,
        "summary": job.summary,
    }


def _case_payload(db: Session, case: TestCase) -> dict:
    return {
        "id": case.id,
        "node_id": case.node_id,
        "file_path": case.file_path,
        "title": case.title,
        "flake_score": case.flake_score,
        "flip_count": case.flip_count,
        "is_flaky": case.is_flaky,
        "last_status": case.last_status,
        "recent_statuses": case.recent_statuses or [],
        "quarantined_at": case.quarantined_at.isoformat() if case.quarantined_at else None,
        "quarantine_branch": case.quarantine_branch,
        "quarantine_pr_url": case.quarantine_pr_url,
        "release_ready": release_ready(case),
        "latest_job": _job_payload(_latest_job(db, case.id)),
    }


@router.get("/projects/{slug}/quarantine")
def quarantine_board(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    cases = db.scalars(select(TestCase).where(TestCase.project_id == project.id)).all()
    suggestions = [c for c in cases if c.is_flaky and c.quarantined_at is None]
    quarantined = [c for c in cases if c.quarantined_at is not None]
    suggestions.sort(key=lambda c: c.flake_score, reverse=True)
    quarantined.sort(key=lambda c: (not release_ready(c), -c.flake_score))
    return {
        "available": llm_available(),
        "suggestions": [_case_payload(db, c) for c in suggestions],
        "quarantined": [_case_payload(db, c) for c in quarantined],
    }


def _start_marker_job(case_id: int, kind: str, background: BackgroundTasks, db: Session) -> dict:
    _require_ai()
    case = _get_case(case_id, db)
    result_id = latest_result_id(db, case)
    if result_id is None:
        raise HTTPException(status_code=400, detail="Test has no recorded results yet")
    active = _active_job(db, _case_result_ids(db, case_id))
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")
    job = AgentJob(result_id=result_id, kind=kind)
    db.add(job)
    db.commit()
    background.add_task(execute_marker_job, job.id)
    return {"job_id": job.id, "kind": kind, "status": job.status}


@router.post("/tests/{case_id}/quarantine")
def quarantine_test(case_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    case = _get_case(case_id, db)
    if case.quarantined_at is not None:
        raise HTTPException(status_code=400, detail="Test is already quarantined")
    return _start_marker_job(case_id, "quarantine", background, db)


@router.post("/tests/{case_id}/release")
def release_test(case_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    case = _get_case(case_id, db)
    if case.quarantined_at is None:
        raise HTTPException(status_code=400, detail="Test is not quarantined")
    return _start_marker_job(case_id, "release", background, db)


@router.post("/tests/{case_id}/heal")
def heal_test(case_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Run SelfHeal on the test's most recent failing result."""
    _require_ai()
    case = _get_case(case_id, db)
    result = latest_failing_result(db, case)
    if result is None:
        raise HTTPException(status_code=400, detail="No failing result found to heal from")
    active = _active_job(db, _case_result_ids(db, case_id))
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")
    job = AgentJob(result_id=result.id, kind="autofix")
    db.add(job)
    db.commit()
    background.add_task(execute_autofix_job, job.id)
    return {"job_id": job.id, "kind": "autofix", "status": job.status, "result_id": result.id}
