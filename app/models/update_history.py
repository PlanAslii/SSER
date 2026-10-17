"""Update history and status tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UpdateStatus(str, Enum):
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    RESTARTING = "restarting"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    ROLLBACK_AVAILABLE = "rollback_available"
    ROLLBACK_IN_PROGRESS = "rollback_in_progress"
    ROLLBACK_SUCCESSFUL = "rollback_successful"
    ROLLBACK_FAILED = "rollback_failed"


class UpdateHistory(Base):
    __tablename__ = "update_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_version: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_version: Mapped[str] = mapped_column(String(64), nullable=False)
    new_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    initiated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completion_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    release_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    artifact_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
