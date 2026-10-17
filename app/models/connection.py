"""Connection tracking and authentication log models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActiveConnection(Base):
    __tablename__ = "active_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    client_info: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ConnectionHistory(Base):
    __tablename__ = "connection_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    remote_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    remote_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disconnect_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AuthLog(Base):
    __tablename__ = "auth_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    remote_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)  # password, publickey, none
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
