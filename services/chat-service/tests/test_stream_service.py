"""Tests for stream_service.

Phase 1c-ii: stream_service migrated from direct litellm/AsyncOpenAI to
`loreweave_llm.Client.stream()` via the new `_stream_via_gateway`
helper. Tests now patch `_stream_via_gateway` instead of `acompletion` /
`AsyncOpenAI`. Chunks yielded by `_stream_via_gateway` are plain dicts:
`{content, reasoning_content, finish_reason, usage}`.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import ProviderCredentials
from app.services.stream_service import stream_response, _Usage
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


def _dict_chunk(content: str | None = None, reasoning: str = "", usage=None, finish_reason=None) -> dict:
    """Build a dict in the shape `_stream_via_gateway` yields. Replaces
    the legacy `_make_chunk` litellm-shape helper."""
    return {
        "content": content or "",
        "reasoning_content": reasoning,
        "finish_reason": finish_reason,
        "usage": usage,
    }


def _make_chunk(content: str | None = None, usage=None, finish_reason=None) -> dict:
    """Back-compat shim — same args, dict shape now. Existing tests pass
    `content=None` to mark "end of stream"; we map that to a final dict
    with finish_reason='stop' so consumer's billing path triggers."""
    if content is None:
        return {
            "content": "",
            "reasoning_content": "",
            "finish_reason": finish_reason or "stop",
            "usage": usage,
        }
    return _dict_chunk(content=content, usage=usage, finish_reason=finish_reason)


def _fake_gateway(chunks: list[dict]):
    """Return an async-generator factory matching `_stream_via_gateway`
    signature. Patch with `side_effect=_fake_gateway(chunks)` so each
    test invocation yields the prepared chunks."""
    async def _gen(**kwargs):
        for c in chunks:
            yield c
    return _gen


def _make_pool_with_conn():
    """Create a mock pool where pool.acquire() returns a proper async context manager."""
    pool = AsyncMock()
    conn = AsyncMock()

    @asynccontextmanager
    async def fake_acquire():
        yield conn

    @asynccontextmanager
    async def fake_transaction():
        yield

    pool.acquire = fake_acquire
    conn.transaction = fake_transaction
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

        with patch("app.services.stream_service._stream_via_gateway", return_value=fake_acompletion()):
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

        with patch("app.services.stream_service._stream_via_gateway", return_value=fake_acompletion()):
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

        with patch("app.services.stream_service._stream_via_gateway", return_value=fake_acompletion()):
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

        with patch("app.services.stream_service._stream_via_gateway", side_effect=Exception("API down")):
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
    async def test_lm_studio_routes_to_gateway_with_model_ref(self):
        # Phase 1c-ii: chat-service no longer derives model_string /
        # base_url itself — gateway resolves them. The test now asserts
        # that model_source + model_ref + user_id are forwarded to
        # _stream_via_gateway unchanged.
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        billing = AsyncMock()
        captured: list[dict] = []

        async def fake_gateway(**kwargs):
            captured.append(kwargs)
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": None}

        with patch("app.services.stream_service._stream_via_gateway", side_effect=fake_gateway):
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

        assert captured[0]["model_source"] == "user_model"
        assert captured[0]["model_ref"] == TEST_MODEL_REF
        assert captured[0]["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_parent_message_id_in_assistant_insert(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 2

        billing = AsyncMock()
        parent_id = str(uuid4())

        async def fake_acompletion(**kwargs):
            yield _make_chunk("Response")

        with patch("app.services.stream_service._stream_via_gateway", return_value=fake_acompletion()):
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
    async def test_emits_outbox_event_on_turn_completed(self):
        """K13.2: assistant turn persistence must insert an outbox event in the same transaction."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 2

        billing = AsyncMock()

        async def fake_acompletion(**kwargs):
            yield _make_chunk("Response text")

        with patch("app.services.stream_service._stream_via_gateway", return_value=fake_acompletion()):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="Hello",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=billing,
            ):
                pass

        outbox_inserts = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO outbox_events" in str(c)
        ]
        assert len(outbox_inserts) == 1, "expected exactly one outbox_events INSERT"

        call = outbox_inserts[0]
        # Payload is the 2nd positional arg after the SQL: (sql, aggregate_id, payload_json)
        sql_text = call.args[0]
        assert "chat.turn_completed" in sql_text
        # aggregate_type must be 'chat' so outbox-relay publishes to
        # loreweave:events:chat (consumed by knowledge-service).
        assert "'chat'" in sql_text
        payload_json = call.args[2]
        payload = json.loads(payload_json)
        assert payload["user_id"] == str(TEST_USER_ID)
        assert payload["session_id"] == str(TEST_SESSION_ID)
        assert payload["assistant_content_len"] == len("Response text")

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

        with patch("app.services.stream_service._stream_via_gateway", side_effect=fake_acompletion):
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


# ── K18.9 prompt-caching (cache_control on Anthropic system segments) ──────


def _patched_knowledge(stable: str = "", volatile: str = "", context: str | None = None,
                       mode: str = "static"):
    """Return a MagicMock knowledge client that synthesises a
    KnowledgeContext with the given split. Caller uses this via
    `patch("app.services.stream_service.get_knowledge_client", ...)`."""
    from app.client.knowledge_client import KnowledgeContext
    if context is None:
        context = stable + volatile
    kctx = KnowledgeContext(
        mode=mode, context=context, recent_message_count=50,
        token_count=10,
        stable_context=stable, volatile_context=volatile,
    )
    client = MagicMock()
    client.build_context = AsyncMock(return_value=kctx)
    return client


class TestK18_9PromptCaching:
    @pytest.mark.asyncio
    async def test_anthropic_emits_structured_cache_control(self):
        """K18.9: for Anthropic provider + non-empty stable_context,
        the system message is a list of text parts with cache_control
        on the stable segment."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        stable = "<memory mode=\"static\"><project/>\n"
        volatile = "<instructions>x</instructions></memory>"

        captured_messages = []

        async def fake_acompletion(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            # Minimal stream: one chunk with content, then None to end
            yield _make_chunk("ok")
            yield _make_chunk(None)

        from unittest.mock import patch as _patch

        def fake_acompletion_wrapper(**kwargs):
            return fake_acompletion(**kwargs)

        with _patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(stable=stable, volatile=volatile),
        ), _patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=fake_acompletion_wrapper,
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="anthropic"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        # First captured message is the system one with structured content.
        system_msg = captured_messages[0]
        assert system_msg["role"] == "system"
        parts = system_msg["content"]
        assert isinstance(parts, list)
        assert parts[0]["type"] == "text"
        assert parts[0]["text"] == stable.strip()
        assert parts[0]["cache_control"] == {"type": "ephemeral"}
        assert parts[1]["text"] == volatile.strip()
        # No cache_control on the volatile segment.
        assert "cache_control" not in parts[1]

    @pytest.mark.asyncio
    async def test_anthropic_includes_system_prompt_as_third_segment(self):
        """K18.9 + T2-polish-3 (D-K18.9-01): the session system_prompt
        lands as a third part after stable and volatile, AND carries
        its own cache_control ephemeral marker because the persona is
        stable per-session (doesn't change between turns). Anthropic
        allows up to 4 cache breakpoints; we use 2 — stable memory +
        system prompt — and leave volatile memory uncached because
        it changes per-message. Catches accidental reorderings (stable
        must stay first so cache_control marks the right byte range)."""
        pool, conn = _make_pool_with_conn()
        # Session has a non-null system_prompt this time.
        pool.fetchrow.return_value = {
            "system_prompt": "Write in the voice of a pirate.",
            "generation_params": {},
        }
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        stable = "<memory mode=\"static\"><project/>\n"
        volatile = "<instructions>x</instructions></memory>"

        captured_messages = []

        async def fake_acompletion(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        def fake_wrapper(**kwargs):
            return fake_acompletion(**kwargs)

        from unittest.mock import patch as _patch
        with _patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(stable=stable, volatile=volatile),
        ), _patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=fake_wrapper,
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="anthropic"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        system_msg = captured_messages[0]
        parts = system_msg["content"]
        assert len(parts) == 3
        # Order: stable (cache_control) → volatile (no cache) → system_prompt (cache_control).
        # Two cache breakpoints used out of Anthropic's four — volatile is
        # intentionally uncached because it changes per-message.
        assert parts[0]["cache_control"] == {"type": "ephemeral"}
        assert parts[0]["text"] == stable.strip()
        assert "cache_control" not in parts[1]
        assert parts[1]["text"] == volatile.strip()
        assert parts[2]["cache_control"] == {"type": "ephemeral"}
        assert parts[2]["text"] == "Write in the voice of a pirate."

    @pytest.mark.asyncio
    async def test_anthropic_mode1_all_stable_single_segment(self):
        """Mode-1 case: volatile is empty. Anthropic path still emits
        cache_control on the stable segment but omits the empty
        volatile text part."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        stable = "<memory mode=\"no_project\"><instructions>x</instructions></memory>"

        captured_messages = []

        async def fake_acompletion(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        def fake_wrapper(**kwargs):
            return fake_acompletion(**kwargs)

        from unittest.mock import patch as _patch
        with _patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(stable=stable, volatile="", mode="no_project"),
        ), _patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=fake_wrapper,
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="anthropic"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        system_msg = captured_messages[0]
        parts = system_msg["content"]
        assert len(parts) == 1
        assert parts[0]["cache_control"] == {"type": "ephemeral"}
        assert parts[0]["text"] == stable.strip()

    @pytest.mark.asyncio
    async def test_non_anthropic_uses_string_concat_path(self):
        """Non-Anthropic providers keep the existing plain-string
        system content. cache_control would be ignored by OpenAI
        anyway."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        stable = "<memory><project/>\n"
        volatile = "<instructions>x</instructions></memory>"

        captured_messages: list[dict] = []

        async def fake_gateway(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        from unittest.mock import patch as _patch
        with _patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(stable=stable, volatile=volatile),
        ), _patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=fake_gateway,
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="openai",
                                  provider_model_name="gpt-4",
                                  base_url="https://api.openai.com/v1"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        system_msg = captured_messages[0]
        assert system_msg["role"] == "system"
        # Plain string (not a list of parts).
        assert isinstance(system_msg["content"], str)
        assert (stable + volatile).strip() in system_msg["content"] or \
               stable.strip() in system_msg["content"]

    @pytest.mark.asyncio
    async def test_anthropic_falls_back_to_concat_when_split_empty(self):
        """Degraded / older-server responses carry empty stable/
        volatile. Anthropic path must not emit an empty cache_control
        part — it should fall back to the concat string path."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        captured_messages = []

        async def fake_acompletion(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        def fake_wrapper(**kwargs):
            return fake_acompletion(**kwargs)

        from unittest.mock import patch as _patch
        # Empty stable AND non-empty legacy context (degraded path
        # simulation: old server returned a blob under `context` only).
        with _patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(
                stable="", volatile="",
                context="<memory>legacy blob</memory>",
            ),
        ), _patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=fake_wrapper,
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="anthropic"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        system_msg = captured_messages[0]
        # Fell back to plain-string concat.
        assert isinstance(system_msg["content"], str)
        assert "legacy blob" in system_msg["content"]
