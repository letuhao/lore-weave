"""Tests for the messages router."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from tests.conftest import TEST_SESSION_ID, make_message_record, make_session_record


class TestListMessages:
    @pytest.mark.asyncio
    async def test_list_messages_empty(self, client, mock_pool):
        mock_pool.fetchval.return_value = True  # session exists
        mock_pool.fetch.return_value = []
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/messages")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    @pytest.mark.asyncio
    async def test_list_messages_returns_items(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [
            make_message_record(sequence_num=1, content="Hi"),
            make_message_record(sequence_num=2, role="assistant", content="Hello!"),
        ]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/messages")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["role"] == "user"
        assert items[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_list_messages_session_not_found(self, client, mock_pool):
        mock_pool.fetchval.return_value = None
        resp = await client.get(f"/v1/chat/sessions/{uuid4()}/messages")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_messages_with_before_seq(self, client, mock_pool):
        mock_pool.fetchval.return_value = True
        mock_pool.fetch.return_value = [make_message_record(sequence_num=1)]
        resp = await client.get(f"/v1/chat/sessions/{TEST_SESSION_ID}/messages?before_seq=5")
        assert resp.status_code == 200
        # Verify before_seq was passed to the query
        call_args = mock_pool.fetch.call_args
        assert 5 in call_args.args


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_session_not_found(self, client, mock_pool):
        mock_pool.fetchrow.return_value = None
        resp = await client.post(
            f"/v1/chat/sessions/{uuid4()}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_archived_session(self, client, mock_pool):
        mock_pool.fetchrow.return_value = make_session_record(status="archived")
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_send_message_streams_response(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1  # next sequence num (now on conn)

        # Mock provider credentials
        from app.models import ProviderCredentials
        mock_provider.return_value.resolve = AsyncMock(return_value=ProviderCredentials(
            provider_kind="openai",
            provider_model_name="gpt-4",
            base_url="https://api.openai.com",
            api_key="sk-test",
            context_length=8192,
        ))

        # Mock stream to yield SSE events
        async def fake_stream(**kwargs):
            yield 'data: {"type": "text-delta", "delta": "Hi"}\n\n'
            yield 'data: {"type": "finish-message", "finishReason": "stop", "usage": {"promptTokens": 10, "completionTokens": 5}}\n\n'
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    async def test_send_message_provider_not_found(self, mock_provider, client, mock_pool):
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1  # seq (now on conn inside transaction)
        mock_provider.return_value.resolve = AsyncMock(side_effect=ValueError("model not found"))

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_missing_content_returns_422(self, client, mock_pool):
        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_edit_from_sequence_deletes_and_captures_parent(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        """When edit_from_sequence is set, messages after that point are deleted
        and the parent_message_id is captured from the message at that sequence."""
        parent_msg_id = str(uuid4())
        conn = mock_pool._conn

        mock_pool.fetchrow.return_value = make_session_record()
        # All ops inside transaction run on conn:
        # 1st fetchval → parent_message_id, 2nd fetchval → next sequence_num
        conn.fetchval.side_effect = [parent_msg_id, 3]
        # 1st execute → DELETE, 2nd execute → INSERT, 3rd execute → UPDATE
        conn.execute.side_effect = ["DELETE 2", "INSERT", "UPDATE"]

        from app.models import ProviderCredentials
        mock_provider.return_value.resolve = AsyncMock(return_value=ProviderCredentials(
            provider_kind="openai",
            provider_model_name="gpt-4",
            base_url="https://api.openai.com",
            api_key="sk-test",
            context_length=8192,
        ))

        async def fake_stream(**kwargs):
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Edited message", "edit_from_sequence": 2},
        )
        assert resp.status_code == 200

        # All ops (DELETE, INSERT, UPDATE) now run on conn inside transaction
        delete_calls = [
            c for c in conn.execute.call_args_list
            if "DELETE FROM chat_messages" in str(c)
        ]
        assert len(delete_calls) == 1

        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c) and "parent_message_id" in str(c)
        ]
        assert len(insert_calls) == 1
        assert parent_msg_id in insert_calls[0].args

        update_calls = [
            c for c in conn.execute.call_args_list
            if "GREATEST" in str(c)
        ]
        assert len(update_calls) == 1

        # Verify stream_response was called with parent_message_id
        mock_stream.assert_called_once()
        call_kwargs = mock_stream.call_args
        assert call_kwargs.kwargs.get("parent_message_id") == parent_msg_id

    @pytest.mark.asyncio
    @patch("app.routers.messages.get_provider_client")
    @patch("app.routers.messages.get_billing_client")
    @patch("app.routers.messages.stream_response")
    async def test_normal_send_has_no_parent_message_id(
        self, mock_stream, mock_billing, mock_provider, client, mock_pool
    ):
        """Normal message sends should pass parent_message_id=None to stream_response."""
        conn = mock_pool._conn
        mock_pool.fetchrow.return_value = make_session_record()
        conn.fetchval.return_value = 1  # seq (now on conn inside transaction)

        from app.models import ProviderCredentials
        mock_provider.return_value.resolve = AsyncMock(return_value=ProviderCredentials(
            provider_kind="openai",
            provider_model_name="gpt-4",
            base_url="https://api.openai.com",
            api_key="sk-test",
            context_length=8192,
        ))

        async def fake_stream(**kwargs):
            yield "data: [DONE]\n\n"

        mock_stream.return_value = fake_stream()

        resp = await client.post(
            f"/v1/chat/sessions/{TEST_SESSION_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 200

        mock_stream.assert_called_once()
        assert mock_stream.call_args.kwargs.get("parent_message_id") is None
