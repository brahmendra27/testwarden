from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from flakelens.db import Base
from flakelens.models.project import utcnow


class FailureAnalysis(Base):
    """AI-generated root-cause analysis for a failed test result (phase-2 agent groundwork)."""

    __tablename__ = "failure_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("test_results.id"), index=True)
    model: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
