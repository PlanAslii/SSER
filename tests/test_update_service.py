"""Tests for update service version comparison and status handling."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Use temp paths before importing app modules that cache settings
tmpdir = tempfile.mkdtemp(prefix="planasli-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DATA_DIR"] = tmpdir
os.environ["UPDATE_CACHE_FILE"] = f"{tmpdir}/update_cache.json"
os.environ["UPDATE_LOCK_FILE"] = f"{tmpdir}/update.lock"

from app.core.database import init_db
from app.services.update_service import UpdateService


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    yield


def test_version_newer():
    assert UpdateService._version_newer("1.1.0", "1.0.0") is True
    assert UpdateService._version_newer("1.0.0", "1.0.0") is False
    assert UpdateService._version_newer("1.0.0", "1.1.0") is False
    assert UpdateService._version_newer("2.0.0", "1.9.9") is True
    assert UpdateService._version_newer("v1.2.3", "1.2.2") is True


def test_get_update_status_no_releases(monkeypatch):
    svc = UpdateService(db=None)

    def fake_fetch(force=False):
        return None

    monkeypatch.setattr(svc, "fetch_latest_release", fake_fetch)
    status = svc.get_update_status()
    assert status["setup_required"] is True
    assert status["update_available"] is False
    assert "No GitHub Releases" in (status["message"] or "")


def test_safe_extract_rejects_traversal(tmp_path):
    import tarfile
    import io

    svc = UpdateService(db=None)
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo(name="../etc/passwd")
        data = b"x"
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))

    with pytest.raises(Exception):
        svc._safe_extract(archive, tmp_path / "out")
