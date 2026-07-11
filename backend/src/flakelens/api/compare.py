from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.api.projects import get_project_by_slug
from flakelens.db import get_db
from flakelens.models import Run
from flakelens.services.comparison import compare_runs

router = APIRouter(prefix="/api/v1", tags=["compare"])


@router.get("/compare")
def compare(base_run: int, head_run: int, db: Session = Depends(get_db)):
    base = db.get(Run, base_run)
    head = db.get(Run, head_run)
    if base is None or head is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if base.project_id != head.project_id:
        raise HTTPException(status_code=400, detail="Runs belong to different projects")
    payload = compare_runs(db, base_run, head_run)
    payload["base_run_id"] = base_run
    payload["head_run_id"] = head_run
    return payload


def _latest_run_on_branch(db: Session, project_id: int, branch: str) -> Run | None:
    return db.scalar(
        select(Run).where(Run.project_id == project_id, Run.branch == branch,
                          Run.status == "completed")
        .order_by(Run.started_at.desc()).limit(1)
    )


@router.get("/projects/{slug}/compare-branches")
def compare_branches(slug: str, base: str, head: str, db: Session = Depends(get_db)):
    """Compare the latest completed run on two branches (e.g. main vs a feature)."""
    project = get_project_by_slug(slug, db)
    base_run = _latest_run_on_branch(db, project.id, base)
    head_run = _latest_run_on_branch(db, project.id, head)
    if base_run is None:
        raise HTTPException(status_code=404, detail=f"No completed run on branch '{base}'")
    if head_run is None:
        raise HTTPException(status_code=404, detail=f"No completed run on branch '{head}'")
    payload = compare_runs(db, base_run.id, head_run.id)
    payload["base_run_id"] = base_run.id
    payload["head_run_id"] = head_run.id
    payload["base_branch"] = base
    payload["head_branch"] = head
    return payload
