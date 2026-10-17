"""Collect and store system metrics for dashboard charts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psutil
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.metrics import SystemMetric


class MetricsService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def collect_now(self) -> SystemMetric:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        load = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (None, None, None)
        metric = SystemMetric(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=mem.percent,
            memory_used_mb=mem.used / (1024 * 1024),
            memory_total_mb=mem.total / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 ** 3),
            disk_total_gb=disk.total / (1024 ** 3),
            load_1=load[0],
            load_5=load[1],
            load_15=load[2],
        )
        self.db.add(metric)
        self.db.commit()
        self.db.refresh(metric)
        return metric

    def current_snapshot(self) -> dict:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": mem.percent,
            "memory_used_mb": round(mem.used / (1024 * 1024), 1),
            "memory_total_mb": round(mem.total / (1024 * 1024), 1),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        }

    def history(self, hours: int = 24) -> list[SystemMetric]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return (
            self.db.query(SystemMetric)
            .filter(SystemMetric.recorded_at >= since)
            .order_by(SystemMetric.recorded_at.asc())
            .all()
        )

    def prune(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.settings.metrics_retention_days)
        q = self.db.query(SystemMetric).filter(SystemMetric.recorded_at < cutoff)
        count = q.count()
        q.delete(synchronize_session=False)
        self.db.commit()
        return count
