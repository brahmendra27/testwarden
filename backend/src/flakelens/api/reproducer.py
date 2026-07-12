import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import ReproJob, TestCase
from flakelens.services.reproducer_exec import execute_repro_job
from flakelens.services.llm import llm_available

router = APIRouter(prefix="/api/v1", tags=["reproducer"])


def _payload(job: ReproJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "test_case_id": job.test_case_id,
        "status": job.status,
        "outcome": job.outcome,
        "log": job.log or "",
        "recipe": job.recipe,
        "recipe_label": job.recipe_label,
        "fail_rate": job.fail_rate,
        "baseline_fail_rate": job.baseline_fail_rate,
        "probes": job.probes or [],
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/tests/{case_id}/reproducer")
def latest_reproducer(case_id: int, db: Session = Depends(get_db)):
    job = db.scalar(
        select(ReproJob).where(ReproJob.test_case_id == case_id).order_by(ReproJob.id.desc())
    )
    return {"available": llm_available(), "job": _payload(job)}


@router.post("/tests/{case_id}/reproducer")
def start_reproducer(
    case_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
):
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Test case not found")
    if not llm_available():
        # The reproducer itself needs no LLM, but a repo_url + browser runtime is
        # required; gate on the same server-configured signal for consistency.
        pass
    active = db.scalar(
        select(ReproJob).where(
            ReproJob.test_case_id == case_id, ReproJob.status.in_(("queued", "running"))
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")
    job = ReproJob(test_case_id=case_id)
    db.add(job)
    db.commit()
    background.add_task(execute_repro_job, job.id)
    return _payload(job)


@router.get("/reproducer-jobs/{job_id}")
def get_reproducer_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ReproJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _payload(job)
