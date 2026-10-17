"""System metrics for monitoring charts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_mb: Mapped[float] = mapped_column(Float, nullable=False)
    memory_total_mb: Mapped[float] = mapped_column(Float, nullable=False)
    disk_percent: Mapped[float] = mapped_column(Float, nullable=False)
    disk_used_gb: Mapped[float] = mapped_column(Float, nullable=False)
    disk_total_gb: Mapped[float] = mapped_column(Float, nullable=False)
    load_1: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_5: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_15: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
