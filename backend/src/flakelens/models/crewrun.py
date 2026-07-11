from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flakelens.db import Base
from flakelens.models.project import utcnow
from flakelens.models.types import PortableJSON


class CrewRun(Base):
    """One maintenance-crew pass over a project: triage new failures into
    incidents, classify each, take bounded actions, and produce a digest."""

    __tablename__ = "crew_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | scheduled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    log: Mapped[str] = mapped_column(Text, default="")
    # Structured triage output: [{fingerprint, classification, node_ids, action, ...}]
    incidents: Mapped[list | None] = mapped_column(PortableJSON, nullable=True)
    digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
