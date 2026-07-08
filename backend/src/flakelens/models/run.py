from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flakelens.db import Base
from flakelens.models.types import PortableJSON

RUN_STATUSES = ("running", "completed", "interrupted")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_project_started", "project_id", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    run_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    framework: Mapped[str] = mapped_column(String(50), default="pytest")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ci_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    labels: Mapped[dict] = mapped_column(PortableJSON, default=dict)

    # Denormalized counts, written at finalize.
    total: Mapped[int] = mapped_column(default=0)
    passed: Mapped[int] = mapped_column(default=0)
    failed: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    flaky_count: Mapped[int] = mapped_column(default=0)
    duration_ms: Mapped[int] = mapped_column(default=0)
