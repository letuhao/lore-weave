"""FD-2 — internal chat-turn text endpoint (worker-ai fetches turn text for KG)."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.config import settings
from tests.conftest import FakeRecord

MSG_ID = str(uuid4())
PARENT_ID = uuid4()
_AUTH = {"X-Internal-Token": settings.internal_service_token}


@pytest.mark.asyncio
async def test_turn_text_joins_user_and_assistant(client, mock_pool):
    # assistant message (has a parent user message) → then the parent's content.
    mock_pool.fetchrow = AsyncMock(side_effect=[
        FakeRecord({"role": "assistant", "content": "a disgraced knight.",
                    "parent_message_id": PARENT_ID}),
        FakeRecord({"content": "who is Kael?"}),
    ])
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["found"] is True
    assert body["text"] == "who is Kael?\n\na disgraced knight."


@pytest.mark.asyncio
async def test_turn_text_no_parent_returns_assistant_only(client, mock_pool):
    mock_pool.fetchrow = AsyncMock(return_value=FakeRecord(
        {"role": "assistant", "content": "standalone message.", "parent_message_id": None}))
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200 and r.json()["text"] == "standalone message."


@pytest.mark.asyncio
async def test_turn_text_non_assistant_ignores_parent(client, mock_pool):
    # A user message id must NOT walk to its parent (a prior assistant turn) —
    # that would prepend unrelated text. Only the message's own content returns.
    fetchrow = AsyncMock(return_value=FakeRecord(
        {"role": "user", "content": "who is Kael?", "parent_message_id": PARENT_ID}))
    mock_pool.fetchrow = fetchrow
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200 and r.json()["text"] == "who is Kael?"
    # exactly one DB read — the parent lookup is skipped for a non-assistant msg.
    assert fetchrow.await_count == 1


@pytest.mark.asyncio
async def test_turn_text_not_found(client, mock_pool):
    mock_pool.fetchrow = AsyncMock(return_value=None)
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text", headers=_AUTH)
    assert r.status_code == 200
    assert r.json() == {"found": False, "text": ""}


@pytest.mark.asyncio
async def test_turn_text_requires_internal_token(client):
    # no token → 401 (the guard fires before any DB access).
    r = await client.get(f"/internal/chat/turns/{MSG_ID}/text")
    assert r.status_code == 401
    r2 = await client.get(f"/internal/chat/turns/{MSG_ID}/text",
                          headers={"X-Internal-Token": "wrong"})
    assert r2.status_code == 401
