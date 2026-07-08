from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flakelens.db import Base
from flakelens.models.types import PortableJSON

RESULT_STATUSES = ("passed", "failed", "skipped", "error", "xfailed", "xpassed")


class TestResult(Base):
    """Final outcome of one test case within one run."""

    __tablename__ = "test_results"
    __table_args__ = (
        UniqueConstraint("run_id", "test_case_id", name="uq_result_run_case"),
        Index("ix_results_case_id_desc", "test_case_id", "id"),
        Index("ix_results_run_status", "run_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    test_case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))
    is_flaky_in_run: Mapped[bool] = mapped_column(default=False)
    attempt_count: Mapped[int] = mapped_column(default=1)
    duration_ms: Mapped[int] = mapped_column(default=0)
    # Denormalized from the final failing attempt for cheap list views.
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase-2 hook: groups similar failures for analysis / dedup.
    failure_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    extras: Mapped[dict] = mapped_column(PortableJSON, default=dict)

    attempts: Mapped[list["TestAttempt"]] = relationship(
        back_populates="result", order_by="TestAttempt.attempt_index"
    )


class TestAttempt(Base):
    """One physical execution attempt (retries produce multiple attempts per result)."""

    __tablename__ = "test_attempts"
    __table_args__ = (UniqueConstraint("result_id", "attempt_index", name="uq_attempt_result_idx"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("test_results.id"), index=True)
    attempt_index: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20))
    duration_ms: Mapped[int] = mapped_column(default=0)
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)

    result: Mapped[TestResult] = relationship(back_populates="attempts")
