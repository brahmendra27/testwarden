import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.db import get_db
from flakelens.models import ApiKey, Project

KEY_PREFIX_LEN = 12


def generate_api_key() -> str:
    return "flk_" + secrets.token_hex(20)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(db: Session, project: Project, name: str = "default") -> str:
    """Create and persist a key; returns the full key (only shown once)."""
    key = generate_api_key()
    db.add(
        ApiKey(
            project_id=project.id,
            key_prefix=key[:KEY_PREFIX_LEN],
            key_hash=hash_key(key),
            name=name,
        )
    )
    return key


def require_project(
    x_api_key: str = Header(default=""),
    db: Session = Depends(get_db),
) -> Project:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Api-Key header")
    candidates = db.scalars(
        select(ApiKey).where(
            ApiKey.key_prefix == x_api_key[:KEY_PREFIX_LEN],
            ApiKey.revoked_at.is_(None),
        )
    ).all()
    key_hash = hash_key(x_api_key)
    for candidate in candidates:
        if secrets.compare_digest(candidate.key_hash, key_hash):
            return db.get(Project, candidate.project_id)
    raise HTTPException(status_code=401, detail="Invalid API key")
