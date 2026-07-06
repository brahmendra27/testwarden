from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from testwarden.db import get_db
from testwarden.models import Project, Run, TestCase

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def get_project_by_slug(slug: str, db: Session) -> Project:
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _run_summary(run: Run) -> dict:
    return {
        "id": run.id,
        "run_uuid": run.run_uuid,
        "status": run.status,
        "framework": run.framework,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "branch": run.branch,
        "commit_sha": run.commit_sha,
        "ci_url": run.ci_url,
        "environment": run.environment,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "skipped": run.skipped,
        "error_count": run.error_count,
        "flaky_count": run.flaky_count,
        "duration_ms": run.duration_ms,
    }


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).order_by(Project.name)).all()
    payload = []
    for project in projects:
        recent = db.scalars(
            select(Run)
            .where(Run.project_id == project.id, Run.status == "completed")
            .order_by(Run.started_at.desc())
            .limit(20)
        ).all()
        flaky_count = db.scalar(
            select(func.count(TestCase.id)).where(
                TestCase.project_id == project.id, TestCase.is_flaky.is_(True)
            )
        )
        sparkline = [
            {
                "run_id": run.id,
                "pass_rate": round(run.passed / run.total, 4) if run.total else None,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            }
            for run in reversed(recent)
        ]
        payload.append(
            {
                "id": project.id,
                "slug": project.slug,
                "name": project.name,
                "repo_url": project.repo_url,
                "flaky_count": flaky_count or 0,
                "last_run": _run_summary(recent[0]) if recent else None,
                "sparkline": sparkline,
            }
        )
    return payload


@router.get("/{slug}")
def project_detail(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    return {
        "id": project.id,
        "slug": project.slug,
        "name": project.name,
        "repo_url": project.repo_url,
    }


@router.get("/{slug}/branches")
def project_branches(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    rows = db.scalars(
        select(Run.branch)
        .where(Run.project_id == project.id, Run.branch.is_not(None))
        .distinct()
    ).all()
    return sorted(rows)


@router.get("/{slug}/flaky")
def flaky_tests(slug: str, db: Session = Depends(get_db)):
    project = get_project_by_slug(slug, db)
    cases = db.scalars(
        select(TestCase)
        .where(TestCase.project_id == project.id, TestCase.is_flaky.is_(True))
        .order_by(TestCase.flake_score.desc())
    ).all()
    return [
        {
            "id": case.id,
            "node_id": case.node_id,
            "file_path": case.file_path,
            "title": case.title,
            "flake_score": case.flake_score,
            "flip_count": case.flip_count,
            "last_status": case.last_status,
            "recent_statuses": case.recent_statuses or [],
            "avg_duration_ms": case.avg_duration_ms,
            "stats_updated_at": case.stats_updated_at.isoformat()
            if case.stats_updated_at
            else None,
        }
        for case in cases
    ]
