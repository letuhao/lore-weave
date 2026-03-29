"""Unit tests for JWT auth middleware."""
import os
import time

import jwt
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")

from app.config import settings
from app.middleware.auth import get_current_user


def _make_token(sub: str, exp_offset: int = 3600, secret: str | None = None) -> str:
    payload = {"sub": sub, "exp": int(time.time()) + exp_offset}
    return jwt.encode(payload, secret or settings.jwt_secret, algorithm="HS256")


class FakeCreds:
    def __init__(self, token: str):
        self.credentials = token


class TestGetCurrentUser:
    def test_valid_token_returns_user_id(self):
        token = _make_token("user-123")
        result = get_current_user(FakeCreds(token))
        assert result == "user-123"

    def test_expired_token_raises_401(self):
        token = _make_token("user-123", exp_offset=-100)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(FakeCreds(token))
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_invalid_token_raises_401(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(FakeCreds("not-a-real-jwt"))
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        token = _make_token("user-123", secret="wrong-secret")
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(FakeCreds(token))
        assert exc_info.value.status_code == 401

    def test_uuid_sub_works(self):
        from uuid import uuid4
        uid = str(uuid4())
        token = _make_token(uid)
        assert get_current_user(FakeCreds(token)) == uid
