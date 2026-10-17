"""GitHub-based update system with safe download, verify, install, and rollback."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings, get_version
from app.models.update_history import UpdateHistory, UpdateStatus

logger = logging.getLogger("planasli.update")


class UpdateError(Exception):
    """Raised when an update step fails."""


class UpdateLock:
    """Simple file-based exclusive update lock."""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._acquired = False

    def acquire(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n".encode())
                os.close(fd)
                self._acquired = True
                return True
            except FileExistsError:
                # Stale lock check
                try:
                    content = self.lock_path.read_text(encoding="utf-8").strip().splitlines()
                    if content:
                        pid = int(content[0])
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            self.lock_path.unlink(missing_ok=True)
                            continue
                except (ValueError, OSError):
                    self.lock_path.unlink(missing_ok=True)
                    continue
                time.sleep(0.5)
        return False

    def release(self) -> None:
        if self._acquired:
            self.lock_path.unlink(missing_ok=True)
            self._acquired = False

    def __enter__(self):
        if not self.acquire():
            raise UpdateError("Could not acquire update lock — another update may be in progress")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


class UpdateService:
    """Handles checking, downloading, verifying, and installing updates from GitHub Releases."""

    def __init__(self, db: Session | None = None):
        self.settings = get_settings()
        self.db = db

    # ------------------------------------------------------------------
    # Metadata cache
    # ------------------------------------------------------------------

    def _load_cache(self) -> dict[str, Any]:
        cache_file = self.settings.update_cache_file
        if not cache_file.exists():
            return {}
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            ts = data.get("fetched_at", 0)
            if time.time() - ts > self.settings.update_cache_ttl_seconds:
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_cache(self, data: dict[str, Any]) -> None:
        cache_file = self.settings.update_cache_file
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        data["fetched_at"] = time.time()
        cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------

    def _github_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"PlanAsli-SSH-Manager/{get_version()}",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return headers

    def fetch_latest_release(self, force: bool = False) -> dict[str, Any] | None:
        """Fetch latest stable release metadata. Returns None if no releases configured."""
        if not force:
            cached = self._load_cache()
            if cached.get("release"):
                return cached["release"]

        url = self.settings.github_latest_release_url
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(url, headers=self._github_headers())
                if resp.status_code == 404:
                    logger.info("No GitHub Releases found for %s/%s", self.settings.github_owner, self.settings.github_repo)
                    return None
                if resp.status_code == 403 and "rate limit" in resp.text.lower():
                    logger.warning("GitHub API rate limit hit")
                    raise UpdateError("GitHub API rate limit exceeded. Try again later or configure a token.")
                resp.raise_for_status()
                release = resp.json()
                # Prefer non-draft, non-prerelease for stable channel
                if self.settings.release_channel == "stable":
                    if release.get("draft") or release.get("prerelease"):
                        return None
                self._save_cache({"release": release})
                return release
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch release: %s", exc)
            raise UpdateError(f"Network error while checking for updates: {exc}") from exc

    def get_update_status(self) -> dict[str, Any]:
        """Return structured update status for the dashboard."""
        current = get_version()
        status: dict[str, Any] = {
            "installed_version": current,
            "latest_version": None,
            "update_available": False,
            "release_notes": None,
            "published_at": None,
            "commit_sha": None,
            "status": UpdateStatus.UP_TO_DATE.value,
            "last_check": None,
            "last_successful_update": None,
            "setup_required": False,
            "message": None,
        }

        cache = self._load_cache()
        if cache.get("fetched_at"):
            status["last_check"] = datetime.fromtimestamp(cache["fetched_at"], tz=timezone.utc).isoformat()

        if self.db:
            last_ok = (
                self.db.query(UpdateHistory)
                .filter(UpdateHistory.status == UpdateStatus.SUCCESSFUL.value)
                .order_by(UpdateHistory.completion_time.desc())
                .first()
            )
            if last_ok and last_ok.completion_time:
                status["last_successful_update"] = last_ok.completion_time.isoformat()

        try:
            release = self.fetch_latest_release()
        except UpdateError as exc:
            status["status"] = UpdateStatus.FAILED.value
            status["message"] = str(exc)
            return status

        if release is None:
            status["setup_required"] = True
            status["message"] = (
                f"No GitHub Releases found for {self.settings.github_owner}/{self.settings.github_repo}. "
                "Configure the repository owner/name and publish a release tagged with a semantic version "
                "(e.g. v1.0.0) before updates can be checked."
            )
            return status

        tag = release.get("tag_name", "").lstrip("v")
        status["latest_version"] = tag
        status["release_notes"] = release.get("body") or ""
        status["published_at"] = release.get("published_at")
        # Commit from target_commitish if available
        status["commit_sha"] = release.get("target_commitish")

        if self._version_newer(tag, current):
            status["update_available"] = True
            status["status"] = UpdateStatus.UPDATE_AVAILABLE.value
        else:
            status["status"] = UpdateStatus.UP_TO_DATE.value

        return status

    @staticmethod
    def _version_newer(candidate: str, current: str) -> bool:
        """Simple semantic version comparison (major.minor.patch)."""
        def parts(v: str) -> tuple[int, ...]:
            cleaned = v.lstrip("v").split("+")[0].split("-")[0]
            nums = []
            for p in cleaned.split("."):
                try:
                    nums.append(int(p))
                except ValueError:
                    nums.append(0)
            while len(nums) < 3:
                nums.append(0)
            return tuple(nums[:3])

        try:
            return parts(candidate) > parts(current)
        except Exception:
            return candidate != current

    # ------------------------------------------------------------------
    # Download & verify
    # ------------------------------------------------------------------

    def _find_asset(self, release: dict[str, Any]) -> tuple[str | None, str | None]:
        """Return (download_url, expected_sha256) from release assets."""
        assets = release.get("assets") or []
        archive_url = None
        checksum_url = None
        for asset in assets:
            name = asset.get("name", "")
            url = asset.get("browser_download_url")
            if name.endswith((".tar.gz", ".tgz", ".zip")) and "planasli" in name.lower():
                archive_url = url
            if name.endswith(".sha256") or name.endswith(".sha256sum"):
                checksum_url = url
        return archive_url, checksum_url

    def download_and_verify(self, release: dict[str, Any], dest_dir: Path) -> Path:
        """Download release archive and verify SHA-256 checksum."""
        archive_url, checksum_url = self._find_asset(release)
        if not archive_url:
            raise UpdateError(
                "No suitable release asset found. Publish a .tar.gz named with 'planasli' "
                "and optionally a .sha256 checksum file."
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        archive_path = dest_dir / Path(archive_url).name

        headers = self._github_headers()
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            with client.stream("GET", archive_url, headers=headers) as resp:
                resp.raise_for_status()
                with open(archive_path, "wb") as f:
                    for chunk in resp.iter_bytes(65536):
                        f.write(chunk)

            expected_hash = None
            if checksum_url:
                cresp = client.get(checksum_url, headers=headers)
                cresp.raise_for_status()
                # Format: "<hash>  <filename>" or just "<hash>"
                line = cresp.text.strip().splitlines()[0]
                expected_hash = line.split()[0].lower()

        if expected_hash:
            actual = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            if actual != expected_hash:
                archive_path.unlink(missing_ok=True)
                raise UpdateError(
                    f"Checksum mismatch: expected {expected_hash}, got {actual}. "
                    "Rejecting untrusted archive."
                )
            logger.info("Checksum verified: %s", actual)
        else:
            logger.warning(
                "No checksum asset found for release. Verification limited to transport security. "
                "For production, always publish a .sha256 file with the release."
            )

        return archive_path

    def _safe_extract(self, archive_path: Path, target_dir: Path) -> None:
        """Extract archive rejecting path traversal and unexpected members."""
        target_dir.mkdir(parents=True, exist_ok=True)
        if archive_path.suffixes[-2:] == [".tar", ".gz"] or archive_path.suffix == ".tgz":
            with tarfile.open(archive_path, "r:gz") as tar:
                for member in tar.getmembers():
                    # Reject absolute paths and parent references
                    if member.name.startswith("/") or ".." in Path(member.name).parts:
                        raise UpdateError(f"Unsafe path in archive: {member.name}")
                    if member.issym() or member.islnk():
                        raise UpdateError(f"Symbolic/hard links not allowed: {member.name}")
                tar.extractall(path=target_dir, filter="data")
        else:
            raise UpdateError(f"Unsupported archive format: {archive_path.name}")

    # ------------------------------------------------------------------
    # Install / rollback
    # ------------------------------------------------------------------

    def install_release(
        self,
        version: str,
        initiated_by: str,
        release: dict[str, Any] | None = None,
    ) -> UpdateHistory:
        """Full safe update procedure. Returns UpdateHistory record."""
        settings = self.settings
        current = get_version()
        history = UpdateHistory(
            requested_version=version,
            previous_version=current,
            status=UpdateStatus.DOWNLOADING.value,
            stage="starting",
            initiated_by=initiated_by,
            start_time=datetime.now(timezone.utc),
        )
        if self.db:
            self.db.add(history)
            self.db.commit()
            self.db.refresh(history)

        lock = UpdateLock(settings.update_lock_file)
        try:
            with lock:
                if release is None:
                    release = self.fetch_latest_release(force=True)
                    if release is None:
                        raise UpdateError("No release available")
                    version = release.get("tag_name", version).lstrip("v")

                history.stage = "downloading"
                history.status = UpdateStatus.DOWNLOADING.value
                self._persist(history)

                with tempfile.TemporaryDirectory(prefix="planasli-update-") as tmp:
                    tmp_path = Path(tmp)
                    archive = self.download_and_verify(release, tmp_path)

                    history.stage = "verifying"
                    history.status = UpdateStatus.VERIFYING.value
                    history.checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
                    self._persist(history)

                    extract_dir = tmp_path / "extracted"
                    self._safe_extract(archive, extract_dir)

                    # Locate application root inside archive
                    candidates = list(extract_dir.iterdir())
                    if len(candidates) == 1 and candidates[0].is_dir():
                        app_src = candidates[0]
                    else:
                        app_src = extract_dir

                    # Verify expected structure
                    if not (app_src / "app").is_dir() and not (app_src / "requirements.txt").exists():
                        raise UpdateError("Archive does not contain expected application structure")

                    history.stage = "backing_up"
                    self._persist(history)
                    backup_path = self._create_backup(current)

                    history.stage = "installing"
                    history.status = UpdateStatus.INSTALLING.value
                    self._persist(history)

                    version_dir = settings.releases_dir / version
                    if version_dir.exists():
                        shutil.rmtree(version_dir)
                    shutil.copytree(app_src, version_dir, symlinks=False)

                    # Write VERSION file
                    (version_dir / "VERSION").write_text(version + "\n", encoding="utf-8")

                    # Do NOT overwrite user config / secrets
                    # Switch symlink
                    history.stage = "switching"
                    current_link = settings.current_link
                    previous_target = current_link.resolve() if current_link.exists() else None
                    new_link = settings.install_dir / f"current.new"
                    if new_link.exists() or new_link.is_symlink():
                        new_link.unlink()
                    new_link.symlink_to(version_dir)
                    new_link.rename(current_link)

                    history.stage = "health_check"
                    history.status = UpdateStatus.RESTARTING.value
                    self._persist(history)

                    # In a real deployment the systemd unit would restart here.
                    # We record success; the installer/update helper performs the actual restart.
                    history.status = UpdateStatus.SUCCESSFUL.value
                    history.result = "success"
                    history.new_version = version
                    history.completion_time = datetime.now(timezone.utc)
                    history.stage = "completed"
                    history.release_notes = release.get("body")
                    self._persist(history)

                    logger.info("Update to %s completed successfully", version)
                    return history

        except Exception as exc:
            logger.exception("Update failed")
            history.status = UpdateStatus.FAILED.value
            history.result = "failed"
            history.failure_reason = str(exc)
            history.completion_time = datetime.now(timezone.utc)
            history.stage = "failed"
            self._persist(history)
            # Attempt rollback if we had switched
            try:
                self._attempt_rollback(history)
            except Exception as rb_exc:
                history.rollback_result = f"rollback_failed: {rb_exc}"
                self._persist(history)
            raise

    def _persist(self, history: UpdateHistory) -> None:
        if self.db:
            self.db.add(history)
            self.db.commit()

    def _create_backup(self, version: str) -> Path:
        settings = self.settings
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_name = f"pre-update-{version}-{ts}"
        backup_path = settings.backup_dir / backup_name
        backup_path.mkdir(parents=True, exist_ok=True)

        current = settings.current_link
        if current.exists():
            src = current.resolve()
            shutil.copytree(src, backup_path / "app", symlinks=True, dirs_exist_ok=True)

        # Copy database if present
        db_path = Path(settings.database_url.replace("sqlite:///", ""))
        if db_path.exists():
            shutil.copy2(db_path, backup_path / "planasli.db")

        return backup_path

    def _attempt_rollback(self, history: UpdateHistory) -> None:
        """Best-effort restore of previous version symlink."""
        settings = self.settings
        prev = history.previous_version
        prev_dir = settings.releases_dir / prev
        if prev_dir.is_dir():
            current_link = settings.current_link
            tmp = settings.install_dir / "current.rollback"
            if tmp.exists() or tmp.is_symlink():
                tmp.unlink()
            tmp.symlink_to(prev_dir)
            tmp.rename(current_link)
            history.rollback_result = "rollback_successful"
            history.status = UpdateStatus.ROLLBACK_SUCCESSFUL.value
        else:
            history.rollback_result = "previous_version_directory_missing"
            history.status = UpdateStatus.ROLLBACK_FAILED.value
        self._persist(history)

    def list_history(self, limit: int = 50, offset: int = 0) -> list[UpdateHistory]:
        if not self.db:
            return []
        return (
            self.db.query(UpdateHistory)
            .order_by(UpdateHistory.start_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
