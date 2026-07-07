import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from testwarden.api.projects import get_project_by_slug
from testwarden.db import get_db
from testwarden.models import ApiTestJob
from testwarden.services.apitest import execute_apitest_job

router = APIRouter(prefix="/api/v1", tags=["api-agent"])


def _payload(job: ApiTestJob) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "spec_url": job.spec_url,
        "base_url": job.base_url,
        "status": job.status,
        "model": job.model,
        "log": job.log or "",
        "code": job.code,
        "summary": job.summary,
        "run_id": job.run_id,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


class ApiTestRequest(BaseModel):
    spec_url: str = Field(min_length=1, description="OpenAPI spec URL or local file path")
    base_url: str = Field(min_length=1, description="Base URL of the API under test")


@router.get("/projects/{slug}/api-agent")
def latest_api_test(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    job = db.scalar(
        select(ApiTestJob)
        .where(ApiTestJob.project_id == project.id)
        .order_by(ApiTestJob.id.desc())
    )
    return {
        "available": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "job": _payload(job) if job else None,
    }


@router.post("/projects/{slug}/api-agent")
def start_api_test(
    slug: str,
    payload: ApiTestRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = get_project_by_slug(slug, db)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="API agent unavailable: set ANTHROPIC_API_KEY on the server",
        )
    active = db.scalar(
        select(ApiTestJob).where(
            ApiTestJob.project_id == project.id,
            ApiTestJob.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")

    job = ApiTestJob(
        project_id=project.id,
        spec_url=payload.spec_url.strip(),
        base_url=payload.base_url.strip().rstrip("/"),
    )
    db.add(job)
    db.commit()
    background.add_task(execute_apitest_job, job.id)
    return _payload(job)


@router.get("/api-agent-jobs/{job_id}")
def get_api_test_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ApiTestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _payload(job)
