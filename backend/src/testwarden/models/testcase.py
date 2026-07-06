from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from testwarden.db import Base
from testwarden.models.types import PortableJSON


class TestCase(Base):
    """A logical test with stable identity across runs, plus materialized rolling stats."""

    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("project_id", "case_key", name="uq_testcase_project_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    case_key: Mapped[str] = mapped_column(String(64))
    node_id: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text)
    suite: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    framework: Mapped[str] = mapped_column(String(50), default="pytest")

    first_seen_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    last_seen_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)

    # Materialized rolling stats over the last STATS_WINDOW final results.
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recent_statuses: Mapped[list] = mapped_column(PortableJSON, default=list)
    flip_count: Mapped[int] = mapped_column(default=0)
    flake_score: Mapped[float] = mapped_column(default=0.0)
    is_flaky: Mapped[bool] = mapped_column(default=False, index=True)
    avg_duration_ms: Mapped[int] = mapped_column(default=0)
    p95_duration_ms: Mapped[int] = mapped_column(default=0)
    stats_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
