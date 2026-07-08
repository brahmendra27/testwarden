import re
import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from flakelens.config import settings

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def sanitize(part: str) -> str:
    return _UNSAFE.sub("_", part)[:150] or "file"


class ArtifactStorage(Protocol):
    def save(self, key: str, fileobj: BinaryIO) -> int: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalDiskStorage:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.artifact_dir)

    def _path(self, key: str) -> Path:
        # Keys are built from sanitized parts joined by "/"; keep them under root.
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return path

    def save(self, key: str, fileobj: BinaryIO) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as out:
            shutil.copyfileobj(fileobj, out)
        return path.stat().st_size

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def build_storage_key(project_id: int, run_uuid: str, attempt_id: int, file_name: str) -> str:
    return f"p{project_id}/r{sanitize(run_uuid)}/a{attempt_id}/{sanitize(file_name)}"


storage: ArtifactStorage = LocalDiskStorage()
