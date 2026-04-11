"""Shared test fixtures for chat-service tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing app modules
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.deps import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_USER_ID = str(uuid4())
TEST_SESSION_ID = str(uuid4())
TEST_MODEL_REF = str(uuid4())


@pytest.fixture
def user_id():
    return TEST_USER_ID


@pytest.fixture
def mock_pool():
    """Async mock that acts like an asyncpg.Pool."""
    pool = AsyncMock()
    conn = AsyncMock()

    # pool.acquire() returns an async context manager (not a coroutine)
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)

    # conn.transaction() returns an async context manager
    txn_cm = MagicMock()
    txn_cm.__aenter__ = AsyncMock(return_value=txn_cm)
    txn_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=txn_cm)

    pool._conn = conn  # expose for test assertions
    return pool


@pytest.fixture
async def client(mock_pool, user_id):
    """Async HTTP test client with mocked deps."""

    async def override_db():
        return mock_pool

    def override_user():
        return user_id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def make_session_record(
    session_id: str | None = None,
    owner_user_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Create a dict that looks like an asyncpg.Record for chat_sessions."""
    now = datetime.now(timezone.utc)
    base = {
        "session_id": session_id or TEST_SESSION_ID,
        "owner_user_id": owner_user_id or TEST_USER_ID,
        "title": "Test Session",
        "model_source": "user_model",
        "model_ref": TEST_MODEL_REF,
        "system_prompt": None,
        "generation_params": {},
        "is_pinned": False,
        "status": "active",
        "message_count": 0,
        "last_message_at": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return FakeRecord(base)


def make_message_record(
    message_id: str | None = None,
    session_id: str | None = None,
    owner_user_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Create a dict that looks like an asyncpg.Record for chat_messages."""
    now = datetime.now(timezone.utc)
    base = {
        "message_id": message_id or str(uuid4()),
        "session_id": session_id or TEST_SESSION_ID,
        "owner_user_id": owner_user_id or TEST_USER_ID,
        "role": "user",
        "content": "Hello",
        "content_parts": None,
        "sequence_num": 1,
        "input_tokens": None,
        "output_tokens": None,
        "model_ref": None,
        "is_error": False,
        "error_detail": None,
        "parent_message_id": None,
        "created_at": now,
    }
    base.update(overrides)
    return FakeRecord(base)


def make_output_record(
    output_id: str | None = None,
    message_id: str | None = None,
    session_id: str | None = None,
    owner_user_id: str | None = None,
    **overrides: Any,
) -> dict:
    """Create a dict that looks like an asyncpg.Record for chat_outputs."""
    now = datetime.now(timezone.utc)
    base = {
        "output_id": output_id or str(uuid4()),
        "message_id": message_id or str(uuid4()),
        "session_id": session_id or TEST_SESSION_ID,
        "owner_user_id": owner_user_id or TEST_USER_ID,
        "output_type": "text",
        "title": None,
        "content_text": "some text content",
        "language": None,
        "storage_key": None,
        "mime_type": None,
        "file_name": None,
        "file_size_bytes": None,
        "metadata": None,
        "created_at": now,
    }
    base.update(overrides)
    return FakeRecord(base)


class FakeRecord(dict):
    """Dict subclass that supports both dict[key] and attribute access like asyncpg.Record."""
    pass
