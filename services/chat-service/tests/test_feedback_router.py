"""Tests for the chat-turn feedback router (track phase Q3)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from tests.conftest import FakeRecord

MSG_ID = str(uuid4())


def _msg_and_insert(conn):
    """Wire conn.fetchrow for the two calls: message-exists check, then the
    feedback INSERT ... RETURNING."""
    conn.fetchrow = AsyncMock(
        side_effect=[
            FakeRecord({"session_id": uuid4()}),  # message exists + owned
            FakeRecord({"id": uuid4(), "created_at": datetime.now(timezone.utc)}),
        ]
    )
    conn.execute = AsyncMock()


class TestSubmitFeedback:
    @pytest.mark.asyncio
    async def test_thumb_up_persists_and_emits_outbox(self, client, mock_pool):
        conn = mock_pool._conn
        _msg_and_insert(conn)
        resp = await client.post(f"/v1/chat/messages/{MSG_ID}/feedback", json={"rating": 1})
        assert resp.status_code == 201
        assert resp.json()["rating"] == 1
        # the outbox event was emitted (transactionally, same conn)
        assert conn.execute.await_count == 1
        emit_sql = conn.execute.await_args.args[0]
        assert "INSERT INTO outbox_events" in emit_sql
        assert "chat.message_feedback" in emit_sql

    @pytest.mark.asyncio
    async def test_message_not_found_404(self, client, mock_pool):
        mock_pool._conn.fetchrow = AsyncMock(return_value=None)
        resp = await client.post(f"/v1/chat/messages/{MSG_ID}/feedback", json={"rating": 1})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_rating_422(self, client, mock_pool):
        resp = await client.post(f"/v1/chat/messages/{MSG_ID}/feedback", json={"rating": 5})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_regenerate_as_negative_in_payload(self, client, mock_pool):
        conn = mock_pool._conn
        _msg_and_insert(conn)
        regen = str(uuid4())
        resp = await client.post(
            f"/v1/chat/messages/{MSG_ID}/feedback",
            json={"rating": -1, "reason": "regenerated", "regenerated_from_message_id": regen},
        )
        assert resp.status_code == 201
        assert resp.json()["rating"] == -1
        # the emitted outbox payload carries the regenerate provenance
        emit_payload = conn.execute.await_args.args[2]
        assert regen in emit_payload
        assert "regenerated" in emit_payload
