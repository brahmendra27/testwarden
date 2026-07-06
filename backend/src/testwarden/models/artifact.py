from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from testwarden.db import Base
from testwarden.models.project import utcnow

# Open set on purpose — phase 3 adds kinds like "http_log", "openapi_spec".
ARTIFACT_KINDS = ("screenshot", "trace", "video", "log", "other")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("test_attempts.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), default="other")
    file_name: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(200), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(default=0)
    storage_key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
