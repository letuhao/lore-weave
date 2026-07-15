"""WS-5.6 / C2 (SD-C2) — the reflection-dismiss internal routes (FastAPI wiring + token gate).

DB-level idempotency/owner-scoping is proven in test_reflection_dismissals_db.py; this proves the
HTTP surface: the token guard, the pydantic validation (empty pattern_key → 422), and the SQL the
handler issues (ON CONFLICT DO NOTHING; owner-scoped read).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import settings
from tests.conftest import FakeRecord

_AUTH = {"X-Internal-Token": settings.internal_service_token}
UID = str(uuid4())


@pytest.mark.asyncio
async def test_dismiss_writes_idempotent_upsert(client, mock_pool):
    mock_pool.execute = AsyncMock(return_value="INSERT 0 1")
    r = await client.put("/internal/chat/assistant/reflection-dismiss", headers=_AUTH,
                         json={"owner_user_id": UID, "pattern_key": "co_occurrence:migration"})
    assert r.status_code == 200
    body = r.json()
    assert body["dismissed"] is True and body["pattern_key"] == "co_occurrence:migration"
    args = mock_pool.execute.await_args.args
    assert "reflection_dismissals" in args[0] and "ON CONFLICT (owner_user_id, pattern_key) DO NOTHING" in args[0]
    # the request's owner + key are the ACTUAL bound params (not some other variable) — LOW-3
    assert args[1] == UID and args[2] == "co_occurrence:migration"


@pytest.mark.asyncio
async def test_dismiss_rejects_empty_pattern_key(client, mock_pool):
    mock_pool.execute = AsyncMock()
    r = await client.put("/internal/chat/assistant/reflection-dismiss", headers=_AUTH,
                         json={"owner_user_id": UID, "pattern_key": "   "})
    assert r.status_code == 422  # blank key never becomes a row
    mock_pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_dismiss_requires_internal_token(client):
    r = await client.put("/internal/chat/assistant/reflection-dismiss",
                         json={"owner_user_id": UID, "pattern_key": "x"})
    assert r.status_code == 401
    r2 = await client.put("/internal/chat/assistant/reflection-dismiss",
                          headers={"X-Internal-Token": "wrong"},
                          json={"owner_user_id": UID, "pattern_key": "x"})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_list_dismissals_is_owner_scoped_read(client, mock_pool):
    mock_pool.fetch = AsyncMock(return_value=[
        FakeRecord({"pattern_key": "co_occurrence:migration"}),
        FakeRecord({"pattern_key": "journaling_gap"}),
    ])
    r = await client.get("/internal/chat/assistant/reflection-dismissals",
                         headers=_AUTH, params={"user_id": UID})
    assert r.status_code == 200
    assert r.json()["pattern_keys"] == ["co_occurrence:migration", "journaling_gap"]
    args = mock_pool.fetch.await_args.args
    assert "WHERE owner_user_id=$1" in args[0]  # scoped to the requested user, never global
    assert args[1] == UID                        # the bound param IS the requested user (LOW-3)
