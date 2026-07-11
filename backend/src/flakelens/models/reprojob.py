from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flakelens.db import Base
from flakelens.models.project import utcnow
from flakelens.models.types import PortableJSON


class ReproJob(Base):
    """A Reproducer run: search the perturbation space for a minimal condition
    that makes a flaky test fail deterministically."""

    __tablename__ = "repro_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    log: Mapped[str] = mapped_column(Text, default="")
    # Search outcome: 'reproduced' | 'not_reproduced' | 'error'
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # The minimal recipe that reproduces the failure (JSON), plus stats.
    recipe: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    recipe_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    fail_rate: Mapped[float | None] = mapped_column(nullable=True)
    baseline_fail_rate: Mapped[float | None] = mapped_column(nullable=True)
    probes: Mapped[dict | None] = mapped_column(PortableJSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
