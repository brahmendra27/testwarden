from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ResultStatus = Literal["passed", "failed", "skipped", "error", "xfailed", "xpassed"]


class RunCreate(BaseModel):
    run_uuid: str = Field(min_length=8, max_length=36)
    framework: str = "pytest"
    started_at: datetime | None = None
    branch: str | None = None
    commit_sha: str | None = None
    ci_url: str | None = None
    environment: str | None = None
    labels: dict = Field(default_factory=dict)


class AttemptIn(BaseModel):
    index: int = 0
    status: str
    duration_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class ResultEnvelope(BaseModel):
    result_ref: str
    framework: str = "pytest"
    normalized_id: str
    file_path: str
    suite: str | None = None
    title: str
    status: ResultStatus
    duration_ms: int = 0
    attempts: list[AttemptIn] = Field(default_factory=list)
    extras: dict = Field(default_factory=dict)


class ResultBatch(BaseModel):
    results: list[ResultEnvelope]


class RunFinish(BaseModel):
    finished_at: datetime | None = None
