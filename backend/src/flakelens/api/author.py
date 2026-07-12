import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.api.projects import get_project_by_slug
from flakelens.db import get_db
from flakelens.models import AuthorJob
from flakelens.services.author import execute_author_job
from flakelens.services.llm import llm_available

router = APIRouter(prefix="/api/v1", tags=["author"])


def _payload(job: AuthorJob) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "description": job.description,
        "url": job.url,
        "status": job.status,
        "model": job.model,
        "log": job.log or "",
        "code": job.code,
        "file_path": job.file_path,
        "verified": job.verified,
        "branch": job.branch,
        "pr_url": job.pr_url,
        "summary": job.summary,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


class AuthorRequest(BaseModel):
    description: str = Field(min_length=3, description="Plain-English description of the test")
    url: str = Field(min_length=1, description="Starting URL of the app under test")


@router.get("/projects/{slug}/author")
def latest_author(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    job = db.scalar(
        select(AuthorJob).where(AuthorJob.project_id == project.id).order_by(AuthorJob.id.desc())
    )
    return {"available": llm_available(),
            "job": _payload(job) if job else None}


@router.post("/projects/{slug}/author")
def start_author(slug: str, payload: AuthorRequest, background: BackgroundTasks,
                 db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    if not llm_available():
        raise HTTPException(status_code=503, detail="Author agent unavailable: set ANTHROPIC_API_KEY or FLAKELENS_LLM_BASE_URL")
    active = db.scalar(
        select(AuthorJob).where(AuthorJob.project_id == project.id,
                                AuthorJob.status.in_(("queued", "running")))
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Job #{active.id} is already running")
    job = AuthorJob(project_id=project.id, description=payload.description.strip(),
                    url=payload.url.strip())
    db.add(job)
    db.commit()
    background.add_task(execute_author_job, job.id)
    return _payload(job)


@router.get("/author-jobs/{job_id}")
def get_author_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(AuthorJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _payload(job)
