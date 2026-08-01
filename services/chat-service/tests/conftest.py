"""Shared test fixtures for chat-service tests."""
from __future__ import annotations

import os
import pathlib
import sys

# Expose the in-repo SDK (loreweave_safety — the shared safety floor for WS-5.13) from source
# on a host whose Python predates the SDK's requires-python; the container installs it normally.
_SDK = pathlib.Path(__file__).resolve().parents[3] / "sdks" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))
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

# Point every outbound service URL at a closed local port during tests.
#
# The Settings defaults are docker-compose hostnames ("http://ai-gateway:8210",
# "http://book-service:8082", …). Outside the compose network those do not resolve, and a
# FAILED name lookup is not free — measured on a Windows dev host: provider-registry-service
# 1,276 ms, ai-gateway 2,690 ms, book-service 7,259 ms (NetBIOS/LLMNR/suffix-search fallback
# chain), versus 2 ms for 127.0.0.1. Any test that reaches an un-mocked outbound call therefore
# stalls for seconds, and the suite crawls: ~1.4 s/test at ~1 % CPU, i.e. hours instead of
# ~90 s, which reads as a hang rather than as slowness.
#
# 127.0.0.1:1 is closed, so the connection is REFUSED immediately. The test outcome is
# identical — an un-mocked call still fails — it just fails in microseconds instead of seconds.
# This masks nothing: a test that should mock and doesn't still fails, only faster.
#
# setdefault, so a real compose/CI environment that exports these keeps its own values.
_DEAD = "http://127.0.0.1:1"
for _var in (
    "PROVIDER_REGISTRY_INTERNAL_URL",
    "USAGE_BILLING_SERVICE_URL",
    "STATISTICS_SERVICE_INTERNAL_URL",
    "NOTIFICATION_SERVICE_INTERNAL_URL",
    "COMPOSITION_SERVICE_INTERNAL_URL",
    "KNOWLEDGE_SERVICE_URL",
    "AI_GATEWAY_URL",
    "BOOK_SERVICE_URL",
    "AUTH_SERVICE_URL",
    "GLOSSARY_SERVICE_URL",
    "AGENT_REGISTRY_URL",
):
    os.environ.setdefault(_var, _DEAD)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1")

# Collapse the AUXILIARY per-call timeouts for tests.
#
# stream_response makes several best-effort side calls (book steering, user timezone, known
# entities, agent registry, knowledge). Each is deliberately given a small budget in production
# — 0.5–2.0 s — and each is designed to DEGRADE, not fail, when the callee is absent. In a unit
# run the callee is always absent, so every one of those calls burns its full budget, several
# times per test. Measured on tests/test_admin_surface.py: 34.5 s with production budgets vs
# 6.7 s with these — a 5x difference on one file, and the same shape across the suite.
#
# These are TEST-ONLY defaults. Behaviour is unchanged: the calls still fail and the degrade
# path is still what gets exercised — the suite simply stops paying wall-clock to watch each
# one expire. Production values live in app/config.py and are untouched. setdefault again, so
# a test that needs a real budget can export its own.
for _var, _budget in (
    ("BOOK_STEERING_TIMEOUT_S", "0.01"),
    ("USER_TIMEZONE_TIMEOUT_S", "0.01"),
    ("KNOWN_ENTITIES_TIMEOUT_S", "0.01"),
    ("AGENT_REGISTRY_TIMEOUT_S", "0.01"),
    ("KNOWLEDGE_CLIENT_TIMEOUT_S", "0.01"),
    ("KNOWLEDGE_TOOL_TIMEOUT_S", "0.01"),
    ("CANON_CAPTURE_TIMEOUT_S", "0.01"),
):
    os.environ.setdefault(_var, _budget)

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
        "project_id": None,
        "book_id": None,
        "project_ids": [],
        "composer_model_source": None,
        "composer_model_ref": None,
        "planner_model_source": None,
        "planner_model_ref": None,
        "enabled_tools": [],
        "enabled_skills": [],
        "activated_tools": [],
        "pinned_legacy_tools": [],
        # Chat & AI settings override columns (M1a). grounding_enabled defaults to
        # True here so the send path resolves grounding without the account-prefs
        # fallback fetch (real rows are NULL = inherit; tests exercising the
        # inherit path set it None explicitly).
        "grounding_enabled": True,
        "voice_overrides": None,
        "context_overrides": None,
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
