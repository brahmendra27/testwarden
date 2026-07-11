from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.api.projects import get_project_by_slug
from flakelens.db import get_db
from flakelens.models import CrewRun
from flakelens.services.crew import execute_crew_run

router = APIRouter(prefix="/api/v1", tags=["crew"])


def _payload(run: CrewRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "project_id": run.project_id,
        "trigger": run.trigger,
        "status": run.status,
        "log": run.log or "",
        "incidents": run.incidents or [],
        "digest": run.digest,
        "error": run.error,
        "window_start": run.window_start.isoformat() if run.window_start else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/projects/{slug}/crew")
def crew_history(slug: str, limit: int = 20, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    runs = db.scalars(
        select(CrewRun)
        .where(CrewRun.project_id == project.id)
        .order_by(CrewRun.id.desc())
        .limit(min(limit, 100))
    ).all()
    return {"runs": [_payload(r) for r in runs]}


@router.post("/projects/{slug}/crew")
def run_crew(slug: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    active = db.scalar(
        select(CrewRun).where(
            CrewRun.project_id == project.id,
            CrewRun.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail=f"Crew run #{active.id} is already running")
    run = CrewRun(project_id=project.id, trigger="manual")
    db.add(run)
    db.commit()
    background.add_task(execute_crew_run, run.id)
    return _payload(run)


@router.get("/crew-runs/{run_id}")
def get_crew_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(CrewRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Crew run not found")
    return _payload(run)
