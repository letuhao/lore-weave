"""Tests for the LiteLLM stream service."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import ProviderCredentials
from app.services.stream_service import stream_response
from tests.conftest import TEST_SESSION_ID, TEST_USER_ID, TEST_MODEL_REF


def _make_creds(**overrides) -> ProviderCredentials:
    defaults = {
        "provider_kind": "openai",
        "provider_model_name": "gpt-4",
        "base_url": "https://api.openai.com",
        "api_key": "sk-test",
        "context_length": 8192,
    }
    defaults.update(overrides)
    return ProviderCredentials(**defaults)


def _make_chunk(content: str | None = None, usage=None):
    """Create a fake LiteLLM streaming chunk."""
    chunk = MagicMock()
    choice = MagicMock()
    choice.delta.content = content
    chunk.choices = [choice] if content is not None else []
    chunk.usage = usage
    return chunk


def _make_pool_with_conn():
    """Create a mock pool where pool.acquire() returns a proper async context manager."""
    pool = AsyncMock()
    conn = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    pool.acquire = fake_acquire
    return pool, conn


class TestStreamResponse:
    @pytest.mark.asyncio
    async def test_emits_text_deltas(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        billing = AsyncMock()

        chunks = [_make_chunk("Hello"), _make_chunk(" world"), _make_chunk(None)]

        async def fake_acompletion(**kwargs):
            for c in chunks:
                yield c

        with patch("app.services.stream_service.acompletion", return_value=fake_acompletion()):
            events = []
            async for event in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                events.append(event)

        # Should have text-delta events
        text_deltas = [e for e in events if "text-delta" in e]
        assert len(text_deltas) == 2
        assert '"Hello"' in text_deltas[0]
        assert '" world"' in text_deltas[1]

        # Should have finish-message
        finish_events = [e for e in events if "finish-message" in e]
        assert len(finish_events) == 1

        # Should end with [DONE]
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_persists_assistant_message(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 2

        billing = AsyncMock()

        async def fake_acompletion(**kwargs):
            yield _make_chunk("Response text")

        with patch("app.services.stream_service.acompletion", return_value=fake_acompletion()):
            events = []
            async for event in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                events.append(event)

        # Verify assistant message was inserted
        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        assert len(insert_calls) == 1
        # Verify the content was "Response text"
        args = insert_calls[0].args
        assert "Response text" in args

    @pytest.mark.asyncio
    async def test_extracts_and_persists_outputs(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 2

        billing = AsyncMock()

        response_text = "Here:\n```python\nprint('hi')\n```"

        async def fake_acompletion(**kwargs):
            yield _make_chunk(response_text)

        with patch("app.services.stream_service.acompletion", return_value=fake_acompletion()):
            events = []
            async for event in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Write code",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                events.append(event)

        # Should have inserted output artifacts (text + code = 2)
        output_inserts = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_outputs" in str(c)
        ]
        assert len(output_inserts) == 2

    @pytest.mark.asyncio
    async def test_error_yields_error_event(self):
        pool = AsyncMock()
        pool.fetch.return_value = []

        billing = AsyncMock()

        with patch("app.services.stream_service.acompletion", side_effect=Exception("API down")):
            events = []
            async for event in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                events.append(event)

        error_events = [e for e in events if '"error"' in e]
        assert len(error_events) == 1
        assert "API down" in error_events[0]
        assert events[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_lm_studio_model_string(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        billing = AsyncMock()
        captured_model = []

        async def fake_acompletion(**kwargs):
            captured_model.append(kwargs["model"])
            yield _make_chunk("ok")

        with patch("app.services.stream_service.acompletion", side_effect=fake_acompletion):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="lm_studio", provider_model_name="local-model"),
                pool=pool,
                billing=billing,
            ):
                pass

        assert captured_model[0] == "openai/local-model"

    @pytest.mark.asyncio
    async def test_builds_message_history(self):
        pool, conn = _make_pool_with_conn()
        # The query is ORDER BY sequence_num DESC, then reversed() in code
        # So return in DESC order (reversed in mock means newest first)
        pool.fetch.return_value = [
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "first"},
        ]
        conn.fetchval.return_value = 3

        billing = AsyncMock()
        captured_messages = []

        async def fake_acompletion(**kwargs):
            captured_messages.extend(kwargs["messages"])
            yield _make_chunk("ok")

        with patch("app.services.stream_service.acompletion", side_effect=fake_acompletion):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="new msg",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                pass

        # Should include history (reversed back to ASC) + new message
        assert len(captured_messages) == 3
        assert captured_messages[0]["content"] == "first"
        assert captured_messages[1]["content"] == "reply"
        assert captured_messages[2]["content"] == "new msg"
