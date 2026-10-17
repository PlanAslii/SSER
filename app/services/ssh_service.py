"""SSH account lifecycle management and system integration."""

from __future__ import annotations

import logging
import pwd
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models.account import AccountStatus, SSHAccount
from app.models.audit import AuditEvent

logger = logging.getLogger("planasli.ssh")


class SSHServiceError(Exception):
    pass


class SSHService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def list_accounts(
        self,
        search: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[SSHAccount], int]:
        q = self.db.query(SSHAccount)
        if search:
            like = f"%{search}%"
            q = q.filter(
                (SSHAccount.username.ilike(like))
                | (SSHAccount.display_name.ilike(like))
                | (SSHAccount.email.ilike(like))
            )
        if status:
            q = q.filter(SSHAccount.status == status)
        total = q.count()
        items = q.order_by(SSHAccount.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    def get_account(self, account_id: int) -> SSHAccount | None:
        return self.db.query(SSHAccount).filter(SSHAccount.id == account_id).first()

    def get_by_username(self, username: str) -> SSHAccount | None:
        return self.db.query(SSHAccount).filter(SSHAccount.username == username).first()

    def create_account(
        self,
        username: str,
        password: str | None = None,
        public_key: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
        expires_at: datetime | None = None,
        max_sessions: int = 5,
        notes: str | None = None,
        created_by: str | None = None,
        create_system_user: bool = True,
    ) -> SSHAccount:
        if self.get_by_username(username):
            raise SSHServiceError(f"Username '{username}' already exists")

        count = self.db.query(SSHAccount).count()
        if count >= self.settings.max_accounts:
            raise SSHServiceError(f"Maximum account limit ({self.settings.max_accounts}) reached")

        if not password and not public_key:
            raise SSHServiceError("Either password or public key is required")

        home = str(self.settings.default_home_base / username)
        account = SSHAccount(
            username=username,
            password_hash=hash_password(password) if password else None,
            public_key=public_key,
            display_name=display_name,
            email=email,
            status=AccountStatus.ACTIVE.value,
            shell=self.settings.default_shell,
            home_directory=home,
            max_sessions=max_sessions,
            expires_at=expires_at,
            notes=notes,
            created_by=created_by,
        )

        if create_system_user:
            try:
                self._create_system_user(username, home, password)
                account.system_user_created = True
                try:
                    pw = pwd.getpwnam(username)
                    account.uid = pw.pw_uid
                    account.gid = pw.pw_gid
                except KeyError:
                    pass
            except Exception as exc:
                logger.error("Failed to create system user %s: %s", username, exc)
                raise SSHServiceError(f"Failed to create system user: {exc}") from exc

        if public_key:
            self._write_authorized_key(username, public_key)

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        self._audit(created_by or "system", "account.create", "ssh_account", str(account.id), f"Created {username}")
        return account

    def update_account(self, account: SSHAccount, **kwargs) -> SSHAccount:
        actor = kwargs.pop("updated_by", "system")
        password = kwargs.pop("password", None)
        if password:
            account.password_hash = hash_password(password)
            if account.system_user_created:
                self._set_system_password(account.username, password)

        for key, value in kwargs.items():
            if hasattr(account, key) and key not in ("id", "username", "created_at"):
                setattr(account, key, value)

        if account.is_expired and account.status == AccountStatus.ACTIVE.value:
            account.status = AccountStatus.EXPIRED.value
            self._disable_system_user(account.username)

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        self._audit(actor, "account.update", "ssh_account", str(account.id), f"Updated {account.username}")
        return account

    def disable_account(self, account: SSHAccount, actor: str = "system") -> SSHAccount:
        account.status = AccountStatus.DISABLED.value
        if account.system_user_created:
            self._disable_system_user(account.username)
        self.db.add(account)
        self.db.commit()
        self._audit(actor, "account.disable", "ssh_account", str(account.id), f"Disabled {account.username}")
        return account

    def enable_account(self, account: SSHAccount, actor: str = "system") -> SSHAccount:
        if account.is_expired:
            raise SSHServiceError("Cannot enable an expired account without extending expiry")
        account.status = AccountStatus.ACTIVE.value
        if account.system_user_created:
            self._enable_system_user(account.username)
        self.db.add(account)
        self.db.commit()
        self._audit(actor, "account.enable", "ssh_account", str(account.id), f"Enabled {account.username}")
        return account

    def delete_account(self, account: SSHAccount, actor: str = "system", remove_system_user: bool = True) -> None:
        username = account.username
        if remove_system_user and account.system_user_created:
            self._remove_system_user(username)
        self.db.delete(account)
        self.db.commit()
        self._audit(actor, "account.delete", "ssh_account", str(account.id), f"Deleted {username}")

    def enforce_expiry(self) -> int:
        """Disable accounts that have passed their expiry date. Returns count disabled."""
        now = datetime.now(timezone.utc)
        expired = (
            self.db.query(SSHAccount)
            .filter(
                SSHAccount.status == AccountStatus.ACTIVE.value,
                SSHAccount.expires_at.isnot(None),
                SSHAccount.expires_at < now,
            )
            .all()
        )
        for acc in expired:
            acc.status = AccountStatus.EXPIRED.value
            if acc.system_user_created:
                self._disable_system_user(acc.username)
            self.db.add(acc)
        self.db.commit()
        return len(expired)

    def count_by_status(self) -> dict[str, int]:
        from sqlalchemy import func
        rows = (
            self.db.query(SSHAccount.status, func.count(SSHAccount.id))
            .group_by(SSHAccount.status)
            .all()
        )
        result = {s.value: 0 for s in AccountStatus}
        for status, count in rows:
            result[status] = count
        # Also count effectively expired
        now = datetime.now(timezone.utc)
        expired_active = (
            self.db.query(SSHAccount)
            .filter(
                SSHAccount.status == AccountStatus.ACTIVE.value,
                SSHAccount.expires_at.isnot(None),
                SSHAccount.expires_at < now,
            )
            .count()
        )
        result["expired"] = result.get("expired", 0) + expired_active
        return result

    # ------------------------------------------------------------------
    # System user helpers (require appropriate privileges / update helper)
    # ------------------------------------------------------------------

    def _run(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _create_system_user(self, username: str, home: str, password: str | None) -> None:
        # Prefer calling the restricted update_helper in production
        cmd = ["useradd", "-m", "-d", home, "-s", self.settings.default_shell, username]
        self._run(cmd)
        if password:
            self._set_system_password(username, password)

    def _set_system_password(self, username: str, password: str) -> None:
        proc = subprocess.run(
            ["chpasswd"],
            input=f"{username}:{password}",
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SSHServiceError(f"chpasswd failed: {proc.stderr}")

    def _disable_system_user(self, username: str) -> None:
        self._run(["usermod", "-L", username], check=False)
        self._run(["usermod", "-s", "/usr/sbin/nologin", username], check=False)

    def _enable_system_user(self, username: str) -> None:
        self._run(["usermod", "-U", username], check=False)
        self._run(["usermod", "-s", self.settings.default_shell, username], check=False)

    def _remove_system_user(self, username: str) -> None:
        self._run(["userdel", "-r", username], check=False)

    def _write_authorized_key(self, username: str, public_key: str) -> None:
        ssh_dir = Path(self.settings.default_home_base) / username / ".ssh"
        ssh_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        auth_keys = ssh_dir / "authorized_keys"
        auth_keys.write_text(public_key.strip() + "\n", encoding="utf-8")
        auth_keys.chmod(0o600)
        try:
            pw = pwd.getpwnam(username)
            os_chown = getattr(__import__("os"), "chown")
            os_chown(ssh_dir, pw.pw_uid, pw.pw_gid)
            os_chown(auth_keys, pw.pw_uid, pw.pw_gid)
        except (KeyError, OSError):
            pass

    def _audit(self, actor: str, action: str, resource_type: str, resource_id: str, details: str) -> None:
        event = AuditEvent(
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        self.db.add(event)
        self.db.commit()
