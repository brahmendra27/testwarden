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
    projects,
    quarantine,
    reproducer,
    runs,
    tests,
)
from flakelens.services.stats import sweep_interrupted_runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent for dev/SQLite; Postgres deployments should also run alembic.
    Base.metadata.create_all(engine)
    apply_additive_migrations(engine)
    with SessionLocal() as db:
        sweep_interrupted_runs(db, settings.interrupted_run_ttl_minutes)
    yield


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
