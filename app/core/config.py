"""Application configuration with environment and file-based settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for PlanAsli SSH Manager."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "PlanAsli SSH Manager"
    app_version: str = "1.0.0"
    debug: bool = False
    secret_key: str = Field(default="change-me-in-production-use-openssl-rand-hex-32")
    host: str = "127.0.0.1"
    port: int = 8080
    base_url: str = "http://127.0.0.1:8080"

    # Paths
    data_dir: Path = Path("/var/lib/planasli-ssh")
    config_dir: Path = Path("/etc/planasli-ssh")
    log_dir: Path = Path("/var/log/planasli-ssh")
    backup_dir: Path = Path("/var/lib/planasli-ssh/backups")
    releases_dir: Path = Path("/opt/planasli-ssh/releases")
    current_link: Path = Path("/opt/planasli-ssh/current")
    install_dir: Path = Path("/opt/planasli-ssh")

    # Database
    database_url: str = "sqlite:////var/lib/planasli-ssh/planasli.db"

    # Authentication
    access_token_expire_minutes: int = 60 * 12
    session_cookie_name: str = "planasli_session"
    session_max_age: int = 60 * 60 * 12
    bcrypt_rounds: int = 12

    # GitHub update system
    github_owner: str = "PlanAsli"
    github_repo: str = "planasli-ssh"
    github_branch: str = "main"
    release_channel: Literal["stable", "beta", "nightly"] = "stable"
    github_api_base: str = "https://api.github.com"
    github_token: str | None = None  # optional for higher rate limits
    update_check_interval_hours: int = 24
    auto_update_check_enabled: bool = True
    unattended_install_enabled: bool = False
    update_lock_file: Path = Path("/var/lib/planasli-ssh/update.lock")
    update_cache_file: Path = Path("/var/lib/planasli-ssh/update_cache.json")
    update_cache_ttl_seconds: int = 3600

    # SSH management
    ssh_config_path: Path = Path("/etc/ssh/sshd_config")
    ssh_authorized_keys_dir: Path = Path("/etc/ssh/authorized_keys")
    default_shell: str = "/bin/bash"
    default_home_base: Path = Path("/home")
    managed_user_prefix: str = "ssh_"
    max_accounts: int = 500

    # Security
    bind_localhost_only: bool = True
    allow_registration: bool = False  # first-run setup only
    rate_limit_login_attempts: int = 5
    rate_limit_window_seconds: int = 300

    # Metrics retention
    metrics_retention_days: int = 30
    auth_log_retention_days: int = 90

    # Localization
    default_language: Literal["fa", "en"] = "fa"
    default_theme: Literal["light", "dark", "system"] = "system"

    # Service account
    service_user: str = "planasli"
    service_group: str = "planasli"

    @field_validator("data_dir", "config_dir", "log_dir", "backup_dir", "releases_dir", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        return Path(v)

    @property
    def is_installed(self) -> bool:
        return (self.data_dir / ".installed").exists()

    @property
    def github_releases_url(self) -> str:
        return f"{self.github_api_base}/repos/{self.github_owner}/{self.github_repo}/releases"

    @property
    def github_latest_release_url(self) -> str:
        if self.release_channel == "stable":
            return f"{self.github_releases_url}/latest"
        return f"{self.github_releases_url}"

    def ensure_directories(self) -> None:
        """Create required runtime directories if they do not exist."""
        for path in (
            self.data_dir,
            self.config_dir,
            self.log_dir,
            self.backup_dir,
            self.releases_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    # Allow override of data paths via environment for development
    env_data = os.environ.get("PLANASLI_DATA_DIR")
    if env_data:
        os.environ.setdefault("DATA_DIR", env_data)
    return Settings()


def get_version() -> str:
    """Return current installed version from package or version file."""
    version_file = Path("/opt/planasli-ssh/current/VERSION")
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    from app import __version__
    return __version__
