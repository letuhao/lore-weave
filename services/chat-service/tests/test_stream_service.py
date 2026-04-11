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
        "provider_kind": "anthropic",
        "provider_model_name": "claude-sonnet-4-5",
        "base_url": "",
        "api_key": "sk-ant-test",
        "context_length": 8192,
    }
    defaults.update(overrides)
    return ProviderCredentials(**defaults)


def _make_chunk(content: str | None = None, usage=None, finish_reason=None):
    """Create a fake LiteLLM streaming chunk with proper attribute access."""
    class FakeDelta:
        def __init__(self, c):
            self.content = c
            self.reasoning_content = ""
    class FakeChoice:
        def __init__(self, c, fr):
            self.delta = FakeDelta(c)
            self.finish_reason = fr
    class FakeChunk:
        def __init__(self, c, u, fr):
            self.choices = [FakeChoice(c, fr)] if c is not None else []
            self.usage = u
    return FakeChunk(content, usage, finish_reason)


def _make_pool_with_conn():
    """Create a mock pool where pool.acquire() returns a proper async context manager."""
    pool = AsyncMock()
    conn = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    pool.acquire = fake_acquire
    # Default fetchrow returns a session-like record with required fields
    pool.fetchrow.return_value = {
        "system_prompt": None,
        "generation_params": {},
    }
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
        pool.fetchrow.return_value = {"system_prompt": None, "generation_params": {}}

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
        captured_kwargs = []

        async def fake_stream(model, messages, api_key, base_url, gen_params):
            captured_kwargs.append({"model": model, "base_url": base_url})
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": None}

        with patch("app.services.stream_service._stream_openai_compatible", side_effect=fake_stream):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="lm_studio", provider_model_name="local-model", base_url="http://localhost:1234"),
                pool=pool,
                billing=billing,
            ):
                pass

        assert captured_kwargs[0]["model"] == "local-model"
        assert captured_kwargs[0]["base_url"].endswith("/v1")

    @pytest.mark.asyncio
    async def test_parent_message_id_in_assistant_insert(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 2

        billing = AsyncMock()
        parent_id = str(uuid4())

        async def fake_acompletion(**kwargs):
            yield _make_chunk("Response")

        with patch("app.services.stream_service.acompletion", return_value=fake_acompletion()):
            events = []
            async for event in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Edited msg",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
                parent_message_id=parent_id,
            ):
                events.append(event)

        # Verify assistant INSERT includes parent_message_id
        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c) and "parent_message_id" in str(c)
        ]
        assert len(insert_calls) == 1
        assert parent_id in insert_calls[0].args

    @pytest.mark.asyncio
    async def test_builds_message_history(self):
        pool, conn = _make_pool_with_conn()
        # The query is ORDER BY sequence_num DESC, then reversed() in code.
        # The user message is already persisted in DB before stream_response runs,
        # so it appears in the history fetch (newest first in DESC order).
        pool.fetch.return_value = [
            {"role": "user", "content": "new msg"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "first"},
        ]
        conn.fetchval.return_value = 4

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

        # History reversed back to ASC — user message is from DB, not appended
        assert len(captured_messages) == 3
        assert captured_messages[0]["content"] == "first"
        assert captured_messages[1]["content"] == "reply"
        assert captured_messages[2]["content"] == "new msg"
