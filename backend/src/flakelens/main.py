from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flakelens.config import settings
from flakelens.db import Base, SessionLocal, apply_additive_migrations, engine
from flakelens.api import (
    analysis,
    apitest,
    artifacts,
    autofix,
    compare,
    ingest,
    crew,
    projects,
    quarantine,
    reproducer,
    runs,
    tests,
)
from flakelens.services.crew import execute_crew_run
from flakelens.services.stats import sweep_interrupted_runs


async def _nightly_crew_scheduler():
    """Fire a crew pass for every project once a day at settings.crew_hour.
    Simple wall-clock loop — good enough for a single-instance self-host."""
    import asyncio
    from datetime import datetime

    from sqlalchemy import select

    from flakelens.models import CrewRun, Project

    fired_on = None
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        if now.hour != settings.crew_hour or now.date() == fired_on:
            continue
        fired_on = now.date()
        with SessionLocal() as db:
            project_ids = list(db.scalars(select(Project.id)).all())
        for pid in project_ids:
            with SessionLocal() as db:
                run = CrewRun(project_id=pid, trigger="scheduled")
                db.add(run)
                db.commit()
                run_id = run.id
            await asyncio.to_thread(execute_crew_run, run_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio

    # Idempotent for dev/SQLite; Postgres deployments should also run alembic.
    Base.metadata.create_all(engine)
    apply_additive_migrations(engine)
    with SessionLocal() as db:
        sweep_interrupted_runs(db, settings.interrupted_run_ttl_minutes)
    scheduler = None
    if 0 <= settings.crew_hour <= 23:
        scheduler = asyncio.create_task(_nightly_crew_scheduler())
    yield
    if scheduler is not None:
        scheduler.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="FlakeLens", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(ingest.router)
    app.include_router(projects.router)
    app.include_router(runs.router)
    app.include_router(tests.router)
    app.include_router(compare.router)
    app.include_router(artifacts.router)
    app.include_router(analysis.router)
    app.include_router(autofix.router)
    app.include_router(apitest.router)
    app.include_router(quarantine.router)
    app.include_router(reproducer.router)
    app.include_router(crew.router)

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA from static_dir (single-image deploy). Unknown non-API
    paths fall back to index.html so client-side routing works on refresh."""
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    if not settings.static_dir:
        return
    static_root = Path(settings.static_dir)
    index = static_root / "index.html"
    if not index.is_file():
        return
    assets = static_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = (static_root / full_path).resolve()
        if candidate.is_file() and static_root.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
