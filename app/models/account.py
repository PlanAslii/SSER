"""SSH account management model."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccountStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    PENDING = "pending"


class SSHAccount(Base):
    __tablename__ = "ssh_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=AccountStatus.ACTIVE.value, nullable=False, index=True)
    shell: Mapped[str] = mapped_column(String(128), default="/bin/bash", nullable=False)
    home_directory: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_sessions: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    allowed_ips: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    system_user_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp < utcnow()

    @property
    def effective_status(self) -> str:
        if self.status == AccountStatus.DISABLED.value:
            return AccountStatus.DISABLED.value
        if self.is_expired:
            return AccountStatus.EXPIRED.value
        return self.status

    def __repr__(self) -> str:
        return f"<SSHAccount {self.username} ({self.status})>"
