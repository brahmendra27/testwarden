import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from testwarden.auth import create_api_key
from testwarden.db import get_db
from testwarden.models import Project, Run, TestCase, TestResult

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


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = None
    repo_url: str | None = None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:100] or "project"


@router.post("")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    """Create a project; the ingestion API key is returned ONCE - store it safely."""
    slug = _slugify(payload.slug or payload.name)
    if db.scalar(select(Project).where(Project.slug == slug)) is not None:
        raise HTTPException(status_code=409, detail=f"Project '{slug}' already exists")
    project = Project(slug=slug, name=payload.name, repo_url=payload.repo_url or None)
    db.add(project)
    db.flush()
    api_key = create_api_key(db, project, name="default")
    db.commit()
    return {"slug": project.slug, "name": project.name, "api_key": api_key}


@router.post("/{slug}/keys")
def create_key(slug: str, db: Session = Depends(get_db)):
    """Mint an additional ingestion key (shown once)."""
    project = get_project_by_slug(slug, db)
    api_key = create_api_key(db, project, name="additional")
    db.commit()
    return {"slug": project.slug, "api_key": api_key}


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


@router.get("/{slug}/overview")
def project_overview(slug: str, window: int = 30, db: Session = Depends(get_db)):
    """Health command-center: KPI trends and problem tests over the last N runs."""
    project = get_project_by_slug(slug, db)
    runs = db.scalars(
        select(Run)
        .where(Run.project_id == project.id, Run.status == "completed")
        .order_by(Run.started_at.desc())
        .limit(window)
    ).all()
    runs.reverse()  # oldest -> newest for charts
    run_ids = [run.id for run in runs]

    series = [
        {
            "run_id": run.id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "pass_rate": round(run.passed / run.total, 4) if run.total else None,
            "duration_ms": run.duration_ms,
            "failed": run.failed + run.error_count,
            "flaky": run.flaky_count,
            "total": run.total,
        }
        for run in runs
    ]

    latest = runs[-1] if runs else None
    previous = runs[-2] if len(runs) > 1 else None

    def pass_rate(run):
        return run.passed / run.total if run and run.total else None

    flaky_count = db.scalar(
        select(func.count(TestCase.id)).where(
            TestCase.project_id == project.id, TestCase.is_flaky.is_(True)
        )
    )

    most_failing = []
    if run_ids:
        rows = db.execute(
            select(TestResult.test_case_id, func.count(TestResult.id).label("failures"))
            .where(TestResult.run_id.in_(run_ids), TestResult.status.in_(("failed", "error")))
            .group_by(TestResult.test_case_id)
            .order_by(func.count(TestResult.id).desc())
            .limit(5)
        ).all()
        for case_id, failures in rows:
            case = db.get(TestCase, case_id)
            most_failing.append(
                {
                    "test_case_id": case_id,
                    "node_id": case.node_id,
                    "failures": failures,
                    "window_runs": len(run_ids),
                    "last_status": case.last_status,
                    "is_flaky": case.is_flaky,
                }
            )

    slowest = [
        {
            "test_case_id": case.id,
            "node_id": case.node_id,
            "avg_duration_ms": case.avg_duration_ms,
            "p95_duration_ms": case.p95_duration_ms,
        }
        for case in db.scalars(
            select(TestCase)
            .where(TestCase.project_id == project.id)
            .order_by(TestCase.avg_duration_ms.desc())
            .limit(5)
        ).all()
    ]

    return {
        "project": {"slug": project.slug, "name": project.name},
        "kpis": {
            "pass_rate": pass_rate(latest),
            "pass_rate_prev": pass_rate(previous),
            "flaky_count": flaky_count or 0,
            "last_duration_ms": latest.duration_ms if latest else 0,
            "prev_duration_ms": previous.duration_ms if previous else 0,
            "total_tests": latest.total if latest else 0,
            "last_run_id": latest.id if latest else None,
            "last_failed": (latest.failed + latest.error_count) if latest else 0,
        },
        "series": series,
        "most_failing": most_failing,
        "slowest": slowest,
    }


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
