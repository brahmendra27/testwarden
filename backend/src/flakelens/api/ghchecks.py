import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import Project, Run
from flakelens.services.ghchecks import compute_verdict, post_check

router = APIRouter(prefix="/api/v1", tags=["gh-checks"])


@router.get("/runs/{run_id}/verdict")
def run_verdict(run_id: int, db: Session = Depends(get_db)):
    """The flakiness-adjusted merge verdict for a run (no GitHub call)."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return compute_verdict(db, run)


@router.post("/runs/{run_id}/post-check")
def post_run_check(run_id: int, db: Session = Depends(get_db)):
    """Post the verdict to GitHub as a check-run on the run's commit."""
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    project = db.get(Project, run.project_id)
    token = os.environ.get("FLAKELENS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Set GITHUB_TOKEN on the server to post checks")
    if not run.commit_sha:
        raise HTTPException(status_code=400, detail="Run has no commit_sha to attach a check to")
    if not project.repo_url:
        raise HTTPException(status_code=400, detail="Project has no repo_url configured")
    verdict = compute_verdict(db, run)
    try:
        url = post_check(project.repo_url, run.commit_sha, verdict, token)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub check failed: {exc}")
    return {"posted": True, "check_url": url, "conclusion": verdict["conclusion"]}
