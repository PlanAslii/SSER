"""Security-related unit tests."""

from __future__ import annotations

import os
import tempfile

tmpdir = tempfile.mkdtemp(prefix="planasli-sec-")
os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["DATA_DIR"] = tmpdir

from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_password_hash_and_verify():
    h = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", h)
    assert not verify_password("wrong-password", h)


def test_jwt_roundtrip():
    token = create_access_token({"sub": "admin", "id": 1})
    data = decode_access_token(token)
    assert data is not None
    assert data["sub"] == "admin"
    assert data["id"] == 1


def test_jwt_invalid():
    assert decode_access_token("not.a.token") is None
