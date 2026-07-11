from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from flakelens.api.projects import get_project_by_slug
from flakelens.db import get_db
from flakelens.services import insights

router = APIRouter(prefix="/api/v1", tags=["insights"])


@router.get("/projects/{slug}/incidents")
def incidents(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    return {"incidents": insights.project_incidents(db, project.id)}


@router.get("/projects/{slug}/alerts")
def alerts(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    return {"alerts": insights.regression_alerts(db, project.id)}


@router.get("/projects/{slug}/health")
def health(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    return {
        "health": insights.health_grade(db, project.id),
        "actions": insights.action_list(db, project.id, project.repo_url),
    }
