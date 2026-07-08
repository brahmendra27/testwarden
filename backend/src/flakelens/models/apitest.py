from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flakelens.db import Base
from flakelens.models.project import utcnow


class ApiTestJob(Base):
    """One API-testing agent run: OpenAPI spec -> generated pytest+httpx suite -> live run."""

    __tablename__ = "api_test_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    spec_url: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    model: Mapped[str] = mapped_column(String(100), default="")
    log: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
