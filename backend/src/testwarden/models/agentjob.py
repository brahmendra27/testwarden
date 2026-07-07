from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from testwarden.db import Base
from testwarden.models.project import utcnow

JOB_STATUSES = ("queued", "running", "completed", "failed")


class AgentJob(Base):
    """One autonomous agent run (kind='autofix': analyze a failure, patch, verify, PR)."""

    __tablename__ = "agent_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("test_results.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="autofix")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    model: Mapped[str] = mapped_column(String(100), default="")
    log: Mapped[str] = mapped_column(Text, default="")
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
