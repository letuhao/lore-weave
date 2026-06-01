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
    # The post-finish auto-title count read goes through pool.fetchval. A real
    # pool returns an int; default the mock to one > 2 so auto-title is skipped
    # (deterministic, no background task scheduled). Tests that exercise the
    # auto-title or post-finish-failure paths override this.
    pool.fetchval.return_value = 5
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
                       mode: str = "static", tool_defs: list | None = None):
    """Return a MagicMock knowledge client that synthesises a
    KnowledgeContext with the given split. Caller uses this via
    `patch("app.services.stream_service.get_knowledge_client", ...)`.

    K21-B: `stream_response` now `await`s `get_tool_definitions()`, so
    the mocked client must expose it as an AsyncMock — a plain MagicMock
    attribute raises "object MagicMock can't be used in 'await'
    expression". Defaults to `[]` (no tool schemas) so these K18.9
    cache_control tests still exercise the no-tools `_stream_via_gateway`
    path they were written against."""
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
    client.get_tool_definitions = AsyncMock(return_value=tool_defs or [])
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


# ── K21-B: tool-calling integration at the stream_response level ───────────
#
# The tool-calling loop itself is exhaustively covered in
# test_stream_tools.py. These tests cover the SEAM in stream_response:
# the gate (tool_calling_enabled + non-empty tool_defs picks
# _stream_with_tools vs _stream_via_gateway), the `tool_call` chunk →
# `tool-call` SSE event handling, and persistence into the new
# `chat_messages.tool_calls` JSONB column (design D6 / §5).


class TestK21BToolCallingIntegration:
    @pytest.mark.asyncio
    async def test_tools_enabled_with_defs_uses_tool_loop(self):
        """tool_calling_enabled=True + knowledge-service serves schemas
        → stream_response routes through _stream_with_tools, not
        _stream_via_gateway."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "tool-loop answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway") as gateway_mock:
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                events.append(e)

        loop_mock.assert_called_once()
        gateway_mock.assert_not_called()
        # The tools array reached the loop.
        assert loop_mock.call_args.kwargs["tools"] == [
            {"type": "function", "function": {"name": "memory_search"}}
        ]
        text = [e for e in events if "text-delta" in e]
        assert any("tool-loop answer" in e for e in text)

    @pytest.mark.asyncio
    async def test_tool_calling_disabled_skips_definitions_and_uses_gateway(self):
        """tool_calling_enabled=False → stream_response neither fetches
        tool definitions nor enters the loop; it uses the plain
        _stream_via_gateway path (design D9 gate)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        from app.client.knowledge_client import KnowledgeContext
        kctx = KnowledgeContext(
            mode="static", context="", recent_message_count=50,
            token_count=0, tool_calling_enabled=False,
        )
        kc = MagicMock()
        kc.build_context = AsyncMock(return_value=kctx)
        kc.get_tool_definitions = AsyncMock(return_value=[
            {"type": "function", "function": {"name": "memory_search"}}
        ])

        async def fake_gateway(**kwargs):
            yield {"content": "plain answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_via_gateway", side_effect=fake_gateway) as gateway_mock, \
             patch("app.services.stream_service._stream_with_tools") as loop_mock:
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                pass

        # Gate is off → definitions are never fetched, loop never entered.
        kc.get_tool_definitions.assert_not_awaited()
        loop_mock.assert_not_called()
        gateway_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_tool_defs_falls_back_to_gateway(self):
        """tool_calling_enabled=True but knowledge-service serves no
        schemas (fetch failed → []) → the turn runs tool-free via
        _stream_via_gateway (design D1 degrade)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        # tool_defs default is [] in the helper.
        kc = _patched_knowledge(mode="static", tool_defs=[])

        async def fake_gateway(**kwargs):
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_via_gateway", side_effect=fake_gateway) as gateway_mock, \
             patch("app.services.stream_service._stream_with_tools") as loop_mock:
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                pass

        # Definitions were fetched (gate on), but the empty result
        # means use_tools is False → gateway path.
        kc.get_tool_definitions.assert_awaited_once()
        loop_mock.assert_not_called()
        gateway_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_call_chunk_emits_sse_event(self):
        """A `tool_call` chunk from the loop → a `tool-call` SSE event
        carrying tool name + ok status (design D3)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"tool_call": {"iteration": 0, "tool": "memory_search",
                                 "args": {"query": "Kai"}, "ok": True,
                                 "result": {"hit": 1}, "error": None}}
            yield {"content": "Kai is a knight.", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(2, 3)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Who is Kai?",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                events.append(e)

        tool_events = [e for e in events if '"tool-call"' in e]
        assert len(tool_events) == 1
        payload = json.loads(tool_events[0].removeprefix("data: ").strip())
        assert payload["type"] == "tool-call"
        assert payload["tool"] == "memory_search"
        assert payload["ok"] is True

    @pytest.mark.asyncio
    async def test_tool_calls_persisted_to_column(self):
        """K21.6 / D6: the per-turn tool-call history is persisted to
        the new chat_messages.tool_calls JSONB column."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        tool_call = {"iteration": 0, "tool": "memory_search",
                     "args": {"query": "Kai"}, "ok": True,
                     "result": {"hit": 1}, "error": None}

        async def fake_tool_loop(**kwargs):
            yield {"tool_call": tool_call}
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Who is Kai?",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                pass

        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        assert len(insert_calls) == 1
        # The INSERT SQL writes the tool_calls column.
        assert "tool_calls" in insert_calls[0].args[0]
        # The last positional arg is the tool_calls JSON ($11).
        tool_calls_json = insert_calls[0].args[-1]
        assert tool_calls_json is not None
        assert json.loads(tool_calls_json) == [tool_call]

    @pytest.mark.asyncio
    async def test_tool_calls_column_null_when_no_tool_calls(self):
        """A tool-enabled turn where the model made NO tool calls →
        tool_calls column is NULL (design D6)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            # No tool_call chunk — model answered directly.
            yield {"content": "direct answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                pass

        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        assert len(insert_calls) == 1
        # tool_calls JSON ($11, last arg) is None when no calls were made.
        assert insert_calls[0].args[-1] is None

    @pytest.mark.asyncio
    async def test_tool_call_chunk_excluded_from_assistant_content(self):
        """A `tool_call` chunk carries no text — it must not leak into
        the persisted assistant `content` (the loop's `continue`)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "Let me check. ", "reasoning_content": "",
                   "finish_reason": None, "usage": None}
            yield {"tool_call": {"iteration": 0, "tool": "memory_search",
                                 "args": {}, "ok": True, "result": {}, "error": None}}
            yield {"content": "Found it.", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                pass

        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        # conn.execute args are (sql, $1..$11); content is $4 → args[4].
        persisted_content = insert_calls[0].args[4]
        assert persisted_content == "Let me check. Found it."


def _event_types(events: list[str]) -> list[str]:
    """Parse the AG-UI `type` of each SSE data line (skips [DONE])."""
    out = []
    for e in events:
        payload = e.removeprefix("data: ").strip()
        if payload == "[DONE]":
            out.append("[DONE]")
        elif payload:
            out.append(json.loads(payload)["type"])
    return out


def _parse_event(line: str) -> dict:
    return json.loads(line.removeprefix("data: ").strip())


class TestStreamFormatNegotiation:
    """ARCH-1 C3 — stream_response selects the wire-event format per request
    via the stream_format param. Legacy is the default and must be byte-for-byte
    unchanged; agui emits the AG-UI protocol over the same SSE transport."""

    @pytest.mark.asyncio
    async def test_legacy_is_the_default_and_unchanged(self):
        """The golden legacy event sequence for a reason→text→finish turn. This
        is the primary regression guard that the emitter refactor changed nothing
        on the default path."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        # message_count > 2 so the auto-title task isn't created (keeps the
        # event sequence deterministic for the strict assertion below).
        pool.fetchval.return_value = 5
        chunks = [
            _dict_chunk(reasoning="hmm "),
            _dict_chunk(content="Hi"),
            _make_chunk(None, usage=_Usage(1, 2)),
        ]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                events.append(e)
        types = _event_types(events)
        assert types == [
            "memory-mode", "reasoning-delta", "text-delta",
            "data", "finish-message", "[DONE]",
        ]
        # Byte-level guard (not just `type`): the two events with nested payloads
        # must keep their exact shape/key-order so the legacy FE parser, which
        # was written against these literals, never silently drifts.
        data_event = _parse_event(next(e for e in events if '"type": "data"' in e))
        assert list(data_event.keys()) == ["type", "data"]
        inner = data_event["data"][0]
        # message_id always present; output_id present because "Hi" is a text
        # artifact; has_reasoning present because the turn reasoned.
        assert inner["message_id"]
        assert inner["has_reasoning"] is True
        finish_event = _parse_event(next(e for e in events if '"finish-message"' in e))
        assert list(finish_event.keys()) == ["type", "finishReason", "usage", "timing"]
        assert finish_event["type"] == "finish-message"
        assert finish_event["finishReason"] == "stop"
        assert finish_event["usage"] == {"promptTokens": 1, "completionTokens": 2}
        assert set(finish_event["timing"].keys()) == {"responseTimeMs", "timeToFirstTokenMs"}

    @pytest.mark.asyncio
    async def test_agui_happy_path_frames_run_and_messages(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5  # skip auto-title (deterministic sequence)
        chunks = [
            _dict_chunk(reasoning="hmm "),
            _dict_chunk(content="Hi"),
            _make_chunk(None, usage=_Usage(1, 2)),
        ]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        # Run opens first, memory-mode is CUSTOM, reasoning frames then closes,
        # text frames, run finishes — and NO [DONE] sentinel in agui mode.
        assert types[0] == "RUN_STARTED"
        assert types[1] == "CUSTOM"  # memoryMode
        assert types == [
            "RUN_STARTED", "CUSTOM",
            "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
            "REASONING_MESSAGE_END", "REASONING_END",
            "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
            "CUSTOM",  # persisted — emitted AFTER the message is framed closed
            "RUN_FINISHED",
        ]
        assert "[DONE]" not in types
        # RUN_FINISHED carries usage + timing in result.
        finished = _parse_event(events[-1])
        assert finished["result"]["usage"] == {"promptTokens": 1, "completionTokens": 2}
        assert "responseTimeMs" in finished["result"]["timing"]

    @pytest.mark.asyncio
    async def test_agui_tool_turn_emits_tool_call_sequence_with_propagated_id(self):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5  # skip auto-title

        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )
        tool_call = {"id": "call_7", "iteration": 0, "tool": "memory_search",
                     "args": {"query": "Kai"}, "ok": True,
                     "result": {"hit": 1}, "error": None}

        async def fake_tool_loop(**kwargs):
            yield {"tool_call": tool_call}
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Who is Kai?",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        assert "TOOL_CALL_START" in types
        assert types.count("TOOL_CALL_START") == 1
        # the 4-event tool sequence appears in order
        tool_seq = [t for t in types if t.startswith("TOOL_CALL_")]
        assert tool_seq == ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_RESULT"]
        # toolCallId is the propagated provider id
        start = next(_parse_event(e) for e in events if '"TOOL_CALL_START"' in e)
        result = next(_parse_event(e) for e in events if '"TOOL_CALL_RESULT"' in e)
        assert start["toolCallId"] == "call_7"
        assert result["toolCallId"] == "call_7"

    @pytest.mark.asyncio
    async def test_agui_error_emits_run_error_no_done(self):
        pool = AsyncMock()
        pool.fetch.return_value = []
        pool.fetchrow.return_value = {"system_prompt": None, "generation_params": {}}
        with patch("app.services.stream_service._stream_via_gateway", side_effect=Exception("API down")):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        run_errors = [e for e in events if '"RUN_ERROR"' in e]
        assert len(run_errors) == 1
        assert "API down" in run_errors[0]
        assert "[DONE]" not in types

    @pytest.mark.asyncio
    async def test_agui_post_finish_db_failure_does_not_double_terminate(self):
        """/review-impl #1 — a DB hiccup in the post-finish auto-title read must
        NOT emit RUN_ERROR after RUN_FINISHED (a run terminates exactly once)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        # The post-finish auto-title count read raises; everything before it
        # (persistence inside conn) already succeeded.
        pool.fetchval.side_effect = Exception("pool dropped after commit")
        chunks = [_dict_chunk(content="Hi"), _make_chunk(None, usage=_Usage(1, 2))]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        # Exactly one terminator, and it's RUN_FINISHED — no RUN_ERROR after it.
        assert types.count("RUN_FINISHED") == 1
        assert "RUN_ERROR" not in types
        assert types[-1] == "RUN_FINISHED"

    @pytest.mark.asyncio
    async def test_agui_reasoning_only_turn_frames_and_finishes(self):
        """End-to-end reasoning-only turn: reasoning frames, closes, run finishes
        — no TEXT_MESSAGE_* and no orphaned open message."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        chunks = [_dict_chunk(reasoning="just thinking"), _make_chunk(None, usage=_Usage(1, 1))]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        assert "TEXT_MESSAGE_START" not in types
        # reasoning is opened and properly closed before the run finishes
        assert types[-1] == "RUN_FINISHED"
        assert types.index("REASONING_MESSAGE_END") < types.index("RUN_FINISHED")
        assert types.index("REASONING_END") < types.index("RUN_FINISHED")

    @pytest.mark.asyncio
    async def test_agui_multiple_tool_calls_share_one_open_text_message(self):
        """Two tool calls in one turn → two distinct 4-event sequences, but the
        single assistant text message opens once and closes once."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "Let me check. ", "reasoning_content": "",
                   "finish_reason": None, "usage": None}
            yield {"tool_call": {"id": "call_a", "iteration": 0, "tool": "memory_search",
                                 "args": {"q": "Kai"}, "ok": True, "result": {"h": 1}, "error": None}}
            yield {"tool_call": {"id": "call_b", "iteration": 0, "tool": "memory_search",
                                 "args": {"q": "Mira"}, "ok": True, "result": {"h": 2}, "error": None}}
            yield {"content": "Done.", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Who?",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
            ):
                events.append(e)
        types = _event_types(events)
        # two independent tool-call sequences
        assert types.count("TOOL_CALL_START") == 2
        assert types.count("TOOL_CALL_RESULT") == 2
        # but exactly one text message framing across both calls
        assert types.count("TEXT_MESSAGE_START") == 1
        assert types.count("TEXT_MESSAGE_END") == 1
        # distinct ids
        start_ids = [_parse_event(e)["toolCallId"] for e in events if '"TOOL_CALL_START"' in e]
        assert start_ids == ["call_a", "call_b"]
