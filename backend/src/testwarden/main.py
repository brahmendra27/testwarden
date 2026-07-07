from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from testwarden.config import settings
from testwarden.db import Base, SessionLocal, engine
from testwarden.api import analysis, artifacts, autofix, compare, ingest, projects, runs, tests
from testwarden.services.stats import sweep_interrupted_runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent for dev/SQLite; Postgres deployments should also run alembic.
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sweep_interrupted_runs(db, settings.interrupted_run_ttl_minutes)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TestWarden", version="0.1.0", lifespan=lifespan)
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

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
