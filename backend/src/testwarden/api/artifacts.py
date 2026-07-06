from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from testwarden.db import get_db
from testwarden.models import Artifact
from testwarden.services.storage import storage

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
def download_artifact(artifact_id: int, db: Session = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        fileobj = storage.open(artifact.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="Artifact file is gone")
    disposition = "inline" if artifact.content_type.startswith(("image/", "video/", "text/")) else "attachment"
    return StreamingResponse(
        fileobj,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{artifact.file_name}"'
        },
    )
