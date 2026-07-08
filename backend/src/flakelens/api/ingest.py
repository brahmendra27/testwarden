from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.auth import require_project
from flakelens.config import settings
from flakelens.db import get_db
from flakelens.models import Artifact, Project, Run, TestAttempt, TestResult
from flakelens.schemas.ingest import ResultBatch, RunCreate, RunFinish
from flakelens.services import ingestion
from flakelens.services.stats import finalize_run
from flakelens.services.storage import build_storage_key, storage

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def _get_run(db: Session, project: Project, run_uuid: str) -> Run:
    run = db.scalar(select(Run).where(Run.run_uuid == run_uuid))
    if run is None or run.project_id != project.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/runs")
def create_run(
    payload: RunCreate,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    run, created = ingestion.get_or_create_run(db, project.id, payload)
    db.commit()
    return {"run_id": run.id, "run_uuid": run.run_uuid, "created": created}


@router.post("/runs/{run_uuid}/results")
def ingest_results(
    run_uuid: str,
    batch: ResultBatch,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    run = _get_run(db, project, run_uuid)
    if run.status != "running":
        raise HTTPException(status_code=409, detail=f"Run is {run.status}, not accepting results")
    ref_map = ingestion.ingest_results(db, project.id, run, batch.results)
    db.commit()
    return {"results": ref_map}


@router.post("/runs/{run_uuid}/results/{result_id}/artifacts")
def upload_artifact(
    run_uuid: str,
    result_id: int,
    attempt_index: int = Form(0),
    kind: str = Form("other"),
    file: UploadFile = File(...),
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    run = _get_run(db, project, run_uuid)
    result = db.get(TestResult, result_id)
    if result is None or result.run_id != run.id:
        raise HTTPException(status_code=404, detail="Result not found in this run")
    attempt = db.scalar(
        select(TestAttempt).where(
            TestAttempt.result_id == result.id, TestAttempt.attempt_index == attempt_index
        )
    )
    if attempt is None:
        raise HTTPException(status_code=404, detail=f"Attempt {attempt_index} not found")

    file_name = file.filename or "artifact.bin"
    key = build_storage_key(project.id, run.run_uuid, attempt.id, file_name)
    size = storage.save(key, file.file)
    if size > settings.max_artifact_bytes:
        storage.delete(key)
        raise HTTPException(status_code=413, detail="Artifact exceeds size limit")

    artifact = Artifact(
        attempt_id=attempt.id,
        kind=kind,
        file_name=file_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        storage_key=key,
    )
    db.add(artifact)
    db.commit()
    return {"artifact_id": artifact.id, "size_bytes": size}


@router.post("/runs/{run_uuid}/finish")
def finish_run(
    run_uuid: str,
    payload: RunFinish | None = None,
    project: Project = Depends(require_project),
    db: Session = Depends(get_db),
):
    run = _get_run(db, project, run_uuid)
    if run.status == "completed":
        return {"run_id": run.id, "status": run.status}
    finalize_run(db, run, payload.finished_at if payload else None)
    db.commit()
    return {
        "run_id": run.id,
        "status": run.status,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "flaky": run.flaky_count,
    }
