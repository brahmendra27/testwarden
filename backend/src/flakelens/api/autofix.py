import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import AgentJob, Project, TestResult
from flakelens.services.autofix import execute_autofix_job
from flakelens.services.llm import llm_available

router = APIRouter(prefix="/api/v1", tags=["autofix"])


def _payload(job: AgentJob) -> dict:
    return {
        "id": job.id,
        "result_id": job.result_id,
        "kind": job.kind,
        "status": job.status,
        "model": job.model,
        "log": job.log or "",
        "diff": job.diff,
        "summary": job.summary,
        "branch": job.branch,
        "pr_url": job.pr_url,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/results/{result_id}/autofix")
def latest_autofix(result_id: int, db: Session = Depends(get_db)):
    job = db.scalar(
        select(AgentJob)
        .where(AgentJob.result_id == result_id, AgentJob.kind == "autofix")
        .order_by(AgentJob.id.desc())
    )
    return {
        "available": llm_available(),
        "job": _payload(job) if job else None,
    }


@router.post("/results/{result_id}/autofix")
def start_autofix(
    result_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    result = db.get(TestResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    if result.status not in ("failed", "error") and not result.is_flaky_in_run:
        raise HTTPException(status_code=400, detail="Result has no failure to fix")
    if not llm_available():
        raise HTTPException(
            status_code=503,
            detail="Auto-fix unavailable: set ANTHROPIC_API_KEY or FLAKELENS_LLM_BASE_URL on the server",
        )
    active = db.scalar(
        select(AgentJob).where(
            AgentJob.result_id == result_id,
            AgentJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")

    job = AgentJob(result_id=result_id, kind="autofix")
    db.add(job)
    db.commit()
    background.add_task(execute_autofix_job, job.id)
    return _payload(job)


@router.get("/agent-jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(AgentJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _payload(job)


class ProjectUpdate(BaseModel):
    repo_url: str | None = None


@router.patch("/projects/{slug}")
def update_project(slug: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.repo_url is not None:
        project.repo_url = payload.repo_url or None
    db.commit()
    return {"slug": project.slug, "repo_url": project.repo_url}
