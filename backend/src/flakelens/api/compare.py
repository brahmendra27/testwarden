from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

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
