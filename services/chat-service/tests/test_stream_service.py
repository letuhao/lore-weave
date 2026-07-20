"""Tests for stream_service.

Phase 1c-ii: stream_service migrated from direct litellm/AsyncOpenAI to
`loreweave_llm.Client.stream()` via the new `_stream_via_gateway`
helper. Tests now patch `_stream_via_gateway` instead of `acompletion` /
`AsyncOpenAI`. Chunks yielded by `_stream_via_gateway` are plain dicts:
`{content, reasoning_content, finish_reason, usage}`.
"""
from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models import ProviderCredentials
from app.services.stream_service import (
    stream_response,
    _Usage,
    _thinking_pref,
    _apply_reasoning_kwargs,
    parse_inline_effort,
)
from tests.conftest import TEST_SESSION_ID, TEST_USER_ID, TEST_MODEL_REF


def insert_param(call, column: str):
    """Read an INSERT's bound parameter BY COLUMN NAME, from the SQL the code actually ran.

    Replaces positional reads like `args[-2]`. Those needed a comment to survive
    ("$12, second-to-last since response_id was appended as $13") and broke anyway every
    time a column was appended — `exclude_from_memory`/`local_date` shifted the payload two
    slots left, so `args[-2]` started returning a bool and json.loads() raised TypeError.
    Binding by name tracks the statement instead of guessing at its shape.

    Returns the bound arg for `$N`, or the inline literal when the column is hardcoded in
    VALUES (e.g. `branch_id` → `0`).
    """
    sql = call.args[0]
    m = re.search(r"INSERT INTO \w+\s*\(([^)]*)\)\s*VALUES\s*\(([^)]*)\)", sql, re.S)
    assert m, f"could not parse the INSERT statement:\n{sql}"
    columns = [c.strip() for c in m.group(1).split(",")]
    values = [v.strip() for v in m.group(2).split(",")]
    assert len(columns) == len(values), (
        f"INSERT lists {len(columns)} columns but {len(values)} values — the statement is "
        f"malformed or this parse is too naive for it:\n{sql}"
    )
    assert column in columns, f"{column!r} is not in the INSERT: {columns}"
    token = values[columns.index(column)]
    if (pm := re.match(r"\$(\d+)", token)) is None:
        return token.strip("'")          # an inline literal, not a bound param
    return call.args[int(pm.group(1))]   # args[0] is the SQL, so $N lands on args[N]


# ── RE: reasoning-effort wiring (the chat thinking no-op fix) ──────────────


def test_thinking_pref_mapping():
    # request toggle wins; True→medium (legacy enabled→medium), False→off.
    assert _thinking_pref(True, {}) == "medium"
    assert _thinking_pref(False, {}) == "off"
    # None → session generation_params default, else platform "off".
    assert _thinking_pref(None, {}) == "off"
    assert _thinking_pref(None, {"reasoning_effort": "high"}) == "high"
    assert _thinking_pref(None, {"thinking": True}) == "medium"


def test_thinking_pref_request_effort_precedence():
    # W4 — the per-message reasoning_effort (fast|standard|deep) beats the
    # legacy thinking boolean AND the session default.
    assert _thinking_pref(None, {}, "fast") == "off"
    assert _thinking_pref(None, {}, "standard") == "medium"
    assert _thinking_pref(None, {}, "deep") == "high"
    # beats thinking=True/False when both ride the request
    assert _thinking_pref(True, {}, "fast") == "off"
    assert _thinking_pref(False, {}, "deep") == "high"
    # beats the session default
    assert _thinking_pref(None, {"reasoning_effort": "low"}, "deep") == "high"
    # unknown/None value → falls through to the legacy path
    assert _thinking_pref(True, {}, None) == "medium"
    assert _thinking_pref(None, {"reasoning_effort": "high"}, None) == "high"


def test_send_message_request_reasoning_effort_field():
    # W4 — SendMessageRequest carries the closed-set reasoning_effort.
    from pydantic import ValidationError

    from app.models import SendMessageRequest

    assert SendMessageRequest(content="hi").reasoning_effort is None
    assert SendMessageRequest(content="hi", reasoning_effort="deep").reasoning_effort == "deep"
    with pytest.raises(ValidationError):
        SendMessageRequest(content="hi", reasoning_effort="max")  # not in the enum


def test_apply_reasoning_kwargs_forwards_only_when_present():
    # The wiring that was missing: stashed reasoning fields reach the request kwargs.
    rk: dict = {}
    _apply_reasoning_kwargs(rk, {"reasoning_effort": "high",
                                 "chat_template_kwargs": {"thinking": True, "enable_thinking": True}})
    assert rk["reasoning_effort"] == "high"
    assert rk["chat_template_kwargs"] == {"thinking": True, "enable_thinking": True}
    # No reasoning in gen_params → nothing added (adaptive/non-reasoning models).
    empty: dict = {}
    _apply_reasoning_kwargs(empty, {"temperature": 0.5})
    assert "reasoning_effort" not in empty and "chat_template_kwargs" not in empty


def test_parse_inline_effort_commands():
    # /no_think → off, stripped.
    assert parse_inline_effort("summarize this /no_think") == ("summarize this", "off")
    # /think → medium, leading command.
    assert parse_inline_effort("/think solve it") == ("solve it", "medium")
    # /effort=high.
    assert parse_inline_effort("plan /effort=high the trip") == ("plan the trip", "high")
    # /effort=none normalizes to "off".
    assert parse_inline_effort("/effort=none go") == ("go", "off")
    # No command → unchanged, None.
    assert parse_inline_effort("just a normal message") == ("just a normal message", None)
    # Not anchored mid-word → NOT matched (the path '/think/x' has no boundary).
    text = "see https://x/think/page"
    assert parse_inline_effort(text) == (text, None)
    # Last command wins.
    assert parse_inline_effort("/think a /no_think b")[1] == "off"
    # Command-ONLY message strips to empty (the caller must guard against an empty
    # user turn — stream_response keeps the original in that case).
    assert parse_inline_effort("/no_think") == ("", "off")


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
            c for c in conn.fetchrow.call_args_list
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
            c for c in conn.fetchrow.call_args_list
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
                       mode: str = "static", tool_defs: list | None = None,
                       sections: dict | None = None):
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
        sections=sections or {},
    )
    client = MagicMock()
    client.build_context = AsyncMock(return_value=kctx)
    client.get_tool_definitions = AsyncMock(return_value=tool_defs or [])
    # MCP-fanout: discovery reads the catalog-meta (availability) synchronously.
    client.get_catalog_meta = lambda: {}
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
    async def test_book_context_advertises_glossary_edit_not_propose_edit(self):
        """Glossary-assistant P3: a book-scoped (non-editor) chat sends
        book_context → stream_response advertises glossary_propose_entity_edit
        (book-scoped) but NOT propose_edit (editor-only)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="rename Nezha",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
                book_context={"book_id": "b1"},
            ):
                pass

        names = [t["function"]["name"] for t in loop_mock.call_args.kwargs["tools"]]
        assert "glossary_propose_entity_edit" in names
        assert "propose_edit" not in names  # editor-only, no editor_context here

    @pytest.mark.asyncio
    async def test_book_surface_seeds_glossary_hot_set_and_lazy_tail(self):
        """B (per-surface hot set): a book-scoped chat with a MULTI-DOMAIN catalog
        seeds the glossary domain into discovery_seed_names (advertised pass 1) and
        leaves the other domains (book/translation) to the lazy discovery tail.

        This GUARDS the discovery_seed_names threading stream_response →
        _emit_chat_turn → _stream_with_tools — the other integration tests use a
        single-tool catalog, so their empty seed is indistinguishable from a
        dropped param; only a multi-domain catalog exercises the wiring."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        catalog = [
            {"type": "function", "function": {"name": "glossary_search"}},
            {"type": "function", "function": {"name": "glossary_propose_batch"}},
            {"type": "function", "function": {"name": "book_create"}},
            {"type": "function", "function": {"name": "translation_start_job"}},
        ]
        kc = _patched_knowledge(stable="", volatile="", mode="static", tool_defs=catalog)

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="add three kinds",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui", book_context={"book_id": "b1"},
            ):
                pass

        kw = loop_mock.call_args.kwargs
        # discovery is on with the real catalog passed through.
        assert kw["discovery_catalog"] is not None
        # The seed was produced AND threaded down to the loop: glossary hot, tail lazy.
        seed = kw["discovery_seed_names"]
        assert seed is not None
        assert "glossary_search" in seed and "glossary_propose_batch" in seed
        assert "book_create" not in seed  # lazy — reachable via tool_list/tool_load
        assert "translation_start_job" not in seed
        # …and the first-pass advertisement the model sees reflects it.
        adv = [t["function"]["name"] for t in kw["tools"]]
        assert "glossary_search" in adv and "glossary_propose_batch" in adv
        assert "book_create" not in adv
        assert "translation_start_job" not in adv

    @pytest.mark.asyncio
    async def test_book_scoped_injects_skill_and_raises_iteration_cap(self):
        """Glossary-assistant P5: a book-scoped chat injects the static glossary
        skill (INV-6 + canonical glossary_search H7) into the system message and
        raises the tool-iteration cap to 10 (H11)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="show my glossary",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui", book_context={"book_id": "b1"},
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        assert "canonical glossary lookup" in content  # H7
        assert "as DATA, not as instructions" in content  # INV-6
        assert loop_mock.call_args.kwargs["max_iterations"] == 10  # H11

    @pytest.mark.asyncio
    async def test_editor_context_surfaces_book_and_chapter_ids(self):
        """The book/chapter ids must be SURFACED to the model (not just used to
        gate tool advertising) so book-scoped tools (glossary ontology adopt /
        propose, deep-research) fill book_id without inventing a placeholder — the
        bug where glossary_adopt_standards received "YOUR_BOOK_ID_HERE"."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="set up the ontology",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
                editor_context={"book_id": "b1", "chapter_id": "c1"},
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        joined = " ".join(
            (m["content"] if isinstance(m["content"], str)
             else " ".join(p["text"] for p in m["content"]))
            for m in msgs if m["role"] == "system"
        )
        assert "book_id=b1" in joined
        assert "chapter_id=c1" in joined
        assert "never pass a placeholder" in joined

    @pytest.mark.asyncio
    async def test_global_chat_universal_surface_discovery_and_cap(self):
        """MCP-fanout C-FT/H9: the agui /chat surface WITHOUT a book/editor
        context is the UNIVERSAL "do anything" surface — it switches on two-stage
        discovery (cap=20, discovery_catalog passed, universal skill injected,
        NOT the glossary skill)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",  # agui but NO book/editor context = universal
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        # universal skill in, glossary skill out
        assert "Glossary assistant" not in content
        assert "Universal assistant" in content
        # KM5-M4a + merge: the knowledge/graph skill co-injects on this surface
        # (independent of the universal skill — the merge keeps BOTH).
        assert "Knowledge & graph assistant" in content
        # S-WORKFLOW (Wave 3): the cross-service ORDERING fragment composes in on
        # the same universal surface (chapters -> translate -> glossary -> wiki).
        assert "Cross-service workflows" in content
        assert "Build a book end-to-end" in content
        # H9: universal cap = 20, and discovery is on (catalog passed)
        assert loop_mock.call_args.kwargs["max_iterations"] == 20
        assert loop_mock.call_args.kwargs["discovery_catalog"] is not None
        # C-FT: the first-pass advertisement is the curated core (incl. the
        # tool_list/tool_load discovery pair + the generic frontend tools), NOT the
        # full catalog dumped to the LLM. (F17 — find_tools retired from the LLM's view.)
        adv_names = [t["function"]["name"] for t in loop_mock.call_args.kwargs["tools"]]
        assert "tool_list" in adv_names and "tool_load" in adv_names
        assert "ui_navigate" in adv_names and "confirm_action" in adv_names
        # Part D (2026-07-07, docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
        # standard.md §8b.9): surface_hot_domains now derives from knowledge_skill's own
        # declared hot_domains (honored everywhere it auto-injects, incl. universal chat)
        # instead of the old hand-authored constants that never included it — memory_search
        # is correctly hot-seeded here now, not left to the lazy discovery tail.
        assert "memory_search" in adv_names

    @pytest.mark.asyncio
    async def test_admin_surface_excludes_knowledge_skill(self):
        """/review-impl LOW-3: the CMS/admin surface advertises ONLY the System-tier
        admin tools, so the project knowledge/graph skill must NOT be injected there
        (it would be guidance for tools that aren't present). The admin skill is."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(stable="", volatile="", mode="static")
        # admin surface fetches the SEPARATE admin catalog (not the user catalog)
        kc.get_admin_tool_definitions = AsyncMock(
            return_value=[{"type": "function", "function": {"name": "glossary_admin_propose_genre"}}]
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="edit system kinds",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui", admin_context={"surface": "cms"}, admin_token="adm-tok",
            ):
                pass

        msgs = loop_mock.call_args.kwargs["messages"]
        system = next((m for m in msgs if m["role"] == "system"), None)
        assert system is not None
        content = system["content"] if isinstance(system["content"], str) \
            else " ".join(p["text"] for p in system["content"])
        # admin skill present, knowledge skill ABSENT (LOW-3)
        assert "System-tier admin assistant" in content
        assert "Knowledge & graph assistant" not in content

    @pytest.mark.asyncio
    async def test_legacy_surface_no_discovery_no_frontend_tools(self):
        """F2: a LEGACY (non-agui) client never gets discovery or frontend tools —
        it advertises only the federated catalog as-is (no find_tools, no ui_*,
        no confirm_action) and never enters the discovery path, so it can't
        suspend on a frontend tool / hang."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "", "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway"):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="legacy",  # legacy → no discovery, no frontend tools
            ):
                pass

        # No discovery, default cap, only the federated catalog advertised.
        assert loop_mock.call_args.kwargs["discovery_catalog"] is None
        assert loop_mock.call_args.kwargs["max_iterations"] == 5
        adv_names = [t["function"]["name"] for t in loop_mock.call_args.kwargs["tools"]]
        assert adv_names == ["memory_search"]
        assert "find_tools" not in adv_names
        for fe in ("ui_navigate", "confirm_action", "propose_record_edit", "propose_edit"):
            assert fe not in adv_names

    @pytest.mark.asyncio
    async def test_disable_tools_advertises_no_tools_compose_mode(self):
        """Editor 'Compose' mode: disable_tools=True advertises NO tools —
        not memory tools, not the editor write-back tool — even though
        tool_calling is enabled, schemas are served, and editor_context is
        present (which would otherwise add propose_edit). The turn runs
        tool-free via the gateway so a reasoning model just drafts prose."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1

        kc = _patched_knowledge(
            stable="", volatile="", mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_gateway(**kwargs):
            yield {"content": "Once upon a time…", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_via_gateway", side_effect=fake_gateway) as gateway_mock, \
             patch("app.services.stream_service._stream_with_tools") as loop_mock:
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Write a vivid paragraph",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
                stream_format="agui",
                editor_context={"book_id": "b1", "chapter_id": "c1"},
                disable_tools=True,
            ):
                pass

        # disable_tools short-circuits the whole tool block: no fetch, no loop,
        # no propose_edit — straight to the plain gateway path.
        kc.get_tool_definitions.assert_not_awaited()
        loop_mock.assert_not_called()
        gateway_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_composer_model_advertises_compose_prose_and_passes_it_down(self):
        """A2A phase-2: when the session has a composer model, stream_response
        adds compose_prose to the tool list and passes composer_model into the
        tool loop."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        # session row carries the composer model columns
        pool.fetchrow.return_value = {
            "system_prompt": None, "generation_params": {}, "project_id": None,
            "composer_model_source": "user_model",
            "composer_model_ref": "11111111-1111-1111-1111-111111111111",
        }

        kc = _patched_knowledge(stable="", volatile="", mode="static", tool_defs=[])

        async def fake_tool_loop(**kwargs):
            yield {"content": "ok", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop) as loop_mock, \
             patch("app.services.stream_service._stream_via_gateway") as gateway_mock:
            async for _ in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Draft a scene",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                pass

        loop_mock.assert_called_once()
        gateway_mock.assert_not_called()
        kwargs = loop_mock.call_args.kwargs
        names = [t["function"]["name"] for t in kwargs["tools"]]
        assert "compose_prose" in names
        assert kwargs["composer_model"] == ("user_model", "11111111-1111-1111-1111-111111111111")

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
            c for c in conn.fetchrow.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        # DBT-CHAT-PERSIST — a tool-loop turn now CHECKPOINTS the assistant row at
        # the tool boundary (finish_reason='streaming') AND writes the final row
        # (upsert by msg_id). Both carry tool_calls; only the FINAL rich upsert
        # carries context_breakdown. Assert the final insert has the full payload.
        assert len(insert_calls) >= 1
        final_insert = insert_calls[-1]
        # The INSERT SQL writes the tool_calls column.
        assert "tool_calls" in final_insert.args[0]
        tool_calls_json = insert_param(final_insert, "tool_calls")
        assert tool_calls_json is not None
        assert json.loads(tool_calls_json) == [tool_call]
        # W1 — the context_breakdown JSONB is persisted and carries the per-category
        # breakdown incl. the tool_results bucket.
        ctx_json = insert_param(final_insert, "context_breakdown")
        assert ctx_json is not None
        ctx = json.loads(ctx_json)
        assert set(ctx) >= {"used_tokens", "pct", "breakdown", "baseline_tokens",
                            "until_compact_pct"}
        assert ctx["breakdown"]["tool_results"] > 0

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
            c for c in conn.fetchrow.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        assert len(insert_calls) == 1
        # tool_calls JSON is None when no calls were made.
        assert insert_param(insert_calls[0], "tool_calls") is None

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
            c for c in conn.fetchrow.call_args_list
            if "INSERT INTO chat_messages" in str(c)
        ]
        # DBT-CHAT-PERSIST — the tool boundary checkpoints a partial row; the FINAL
        # upsert carries the complete content. Assert the final (fetchrow args are
        # (sql, $1..); content is $4 → args[4]).
        persisted_content = insert_calls[-1].args[4]
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
            "RUN_STARTED", "CUSTOM",  # memoryMode
            "CUSTOM", "CUSTOM",  # agentSurface: Curated + SkillInjected
            "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
            "REASONING_MESSAGE_END", "REASONING_END",
            "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END",
            "CUSTOM",  # persisted — emitted AFTER the message is framed closed
            "CUSTOM",  # agentSurface: Idle
            "CUSTOM",  # contextBudget (RAID A2) — emitted just before finish
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


# ── M3 anchoring — working_memory pinned + tail injection ─────────────────────


class TestAnchorInjection:
    @pytest.mark.asyncio
    async def test_seed_anchor_is_pinned_and_tailed(self):
        """A roleplay session (working_memory_seed set, knowledge empty) gets the
        anchor pinned in the system block AND tail-injected before the user turn."""
        import json as _json

        pool, conn = _make_pool_with_conn()
        seed = _json.dumps({
            "version": 1,
            "charter": {
                "goal": "Senior backend interview",
                "phases": ["warmup", "technical"],
                "checklist": ["system design"],
                "time_budget_min": 60,
                "language": "vi",
            },
            "state": {"phase": "", "covered": []},
        })
        pool.fetchrow.return_value = {
            "system_prompt": "You are an interviewer.",
            "generation_params": {},
            "working_memory_seed": seed,
        }
        pool.fetch.return_value = [{"role": "user", "content": "hello"}]
        conn.fetchval.return_value = 5

        captured: list[dict] = []

        async def fake_gw(**kwargs):
            captured.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        with patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(),  # kctx.working_memory == "" → seed path
        ), patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=lambda **k: fake_gw(**k),
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="hello",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="openai"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        # Pinned: the system message carries the anchor + the frozen goal.
        sys_msg = captured[0]
        assert sys_msg["role"] == "system"
        assert "ROLEPLAY SESSION" in sys_msg["content"]
        assert "Senior backend interview" in sys_msg["content"]
        # Tail: the Director note sits immediately before the latest user turn.
        assert captured[-1] == {"role": "user", "content": "hello"}
        assert captured[-2]["role"] == "system"
        assert captured[-2]["content"].startswith("[Director")
        assert "Senior backend interview" in captured[-2]["content"]

    @pytest.mark.asyncio
    async def test_non_roleplay_session_has_no_anchor(self):
        """A plain chat session (no seed) injects neither pin nor tail."""
        pool, conn = _make_pool_with_conn()
        pool.fetchrow.return_value = {"system_prompt": None, "generation_params": {}}
        pool.fetch.return_value = [{"role": "user", "content": "hi"}]
        conn.fetchval.return_value = 5

        captured: list[dict] = []

        async def fake_gw(**kwargs):
            captured.extend(kwargs.get("messages", []))
            yield _make_chunk("ok")
            yield _make_chunk(None)

        with patch(
            "app.services.stream_service.get_knowledge_client",
            return_value=_patched_knowledge(),
        ), patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=lambda **k: fake_gw(**k),
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="hi",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(provider_kind="openai"),
                pool=pool,
                billing=AsyncMock(),
            ):
                pass

        assert not any("[Director" in str(m.get("content", "")) for m in captured)
        assert not any("ROLEPLAY SESSION" in str(m.get("content", "")) for m in captured)


class TestInLoopCompactionWiring:
    """A4 — the tool loop grows `working` each pass; compaction must be re-invoked
    at the top of EVERY pass with the effective_limit, or a long tool turn overflows
    mid-turn. This guards the wire (a silent-no-op guard needs a wiring test)."""

    @pytest.mark.asyncio
    async def test_compaction_invoked_each_tool_pass_with_effective_limit(self):
        import app.services.stream_service as ss
        from loreweave_llm import TokenEvent, ToolCallEvent, DoneEvent

        # find_tools is CONSUMER-LOCAL (no network) → drives a real 2-pass loop:
        # pass 0 calls find_tools (executes in-memory, appends result, loops),
        # pass 1 answers in text.
        passes = {"n": 0}

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                i = passes["n"]
                passes["n"] += 1

                async def gen():
                    if i == 0:
                        yield ToolCallEvent(index=0, id="c1", name=ss.FIND_TOOLS_NAME,
                                            arguments_delta='{"intent":"anything"}')
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="done")
                        yield DoneEvent(finish_reason="stop")
                return gen()

        seen_limits: list = []
        real_compact = ss.compact_messages

        async def spy_compact(msgs, **kw):
            seen_limits.append(kw.get("effective_limit"))
            return await real_compact(msgs, **kw)

        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})  # called sync in the loop

        with patch.object(ss, "Client", FakeClient), \
             patch.object(ss, "compact_messages", side_effect=spy_compact):
            chunks = []
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "hi"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=kc, session_id="s", project_id=None,
                discovery_catalog=[], discovery_seed_names=set(),
                effective_limit=5000,
            ):
                chunks.append(ch)

        # compaction ran on BOTH passes, always with the effective_limit forwarded.
        assert len(seen_limits) >= 2, f"expected ≥2 in-loop compactions, got {seen_limits}"
        assert all(lim == 5000 for lim in seen_limits)

    @pytest.mark.asyncio
    async def test_no_effective_limit_skips_in_loop_compaction(self):
        import app.services.stream_service as ss
        from loreweave_llm import TokenEvent, DoneEvent

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                async def gen():
                    yield TokenEvent(delta="hi")
                    yield DoneEvent(finish_reason="stop")
                return gen()

        seen = []
        real_compact = ss.compact_messages

        async def spy_compact(msgs, **kw):
            seen.append(kw.get("effective_limit"))
            return await real_compact(msgs, **kw)

        with patch.object(ss, "Client", FakeClient), \
             patch.object(ss, "compact_messages", side_effect=spy_compact):
            async for _ in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "hi"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=AsyncMock(), session_id="s", project_id=None,
                effective_limit=None,
            ):
                pass

        assert seen == [], "compaction must not run when effective_limit is None"

    @pytest.mark.asyncio
    async def test_blank_intent_find_tools_capped_within_turn(self):
        """D-FINDTOOLS-BLANK-INTENT-LOOP — reproduces the real production
        session (019f4000-43ee-7201-9d45-e2fafc83696d, gemma-4-26b-a4b-qat)
        where find_tools was called with blank args 7+ times in a row, each
        getting the identical unhelpful note, never escalating. The first
        BLANK_TOOL_ARGS_CAP blank calls still reach find_tools_result_async
        (today's helpful note); every call after that is short-circuited
        BEFORE find_tools_result_async runs, with a directive to stop."""
        import app.services.stream_service as ss
        from loreweave_llm import ToolCallEvent, DoneEvent, TokenEvent

        TOTAL_BLANK_PASSES = 5
        passes = {"n": 0}

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                i = passes["n"]
                passes["n"] += 1

                async def gen():
                    if i < TOTAL_BLANK_PASSES:
                        yield ToolCallEvent(index=0, id=f"c{i}", name=ss.FIND_TOOLS_NAME,
                                            arguments_delta="{}")
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="giving up")
                        yield DoneEvent(finish_reason="stop")
                return gen()

        real_find_tools_result_async = ss.find_tools_result_async
        call_count = {"n": 0}

        async def spy_find_tools(*a, **kw):
            call_count["n"] += 1
            return await real_find_tools_result_async(*a, **kw)

        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})

        tool_call_events = []
        with patch.object(ss, "Client", FakeClient), \
             patch.object(ss, "find_tools_result_async", side_effect=spy_find_tools):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "search the web"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=kc, session_id="s", project_id=None,
                discovery_catalog=[], discovery_seed_names=set(),
            ):
                if "tool_call" in ch:
                    tool_call_events.append(ch["tool_call"])

        # Only the first BLANK_TOOL_ARGS_CAP blank calls actually reach
        # find_tools_result_async — the rest are short-circuited before it.
        assert call_count["n"] == ss.BLANK_TOOL_ARGS_CAP

        capped = [
            e for e in tool_call_events
            if e.get("ok") is False and "STOP calling find_tools" in (e.get("error") or "")
        ]
        assert len(capped) == TOTAL_BLANK_PASSES - ss.BLANK_TOOL_ARGS_CAP, (
            f"expected {TOTAL_BLANK_PASSES - ss.BLANK_TOOL_ARGS_CAP} capped calls, "
            f"got {len(capped)}: {tool_call_events}"
        )
        # The capped calls never reached find_tools_result_async, so they can't
        # have produced its "intent is required" note.
        for e in capped:
            assert e["result"] is None

    @pytest.mark.asyncio
    async def test_non_blank_intent_find_tools_resets_blank_streak(self):
        """A real, well-formed find_tools call between blank ones proves
        forward progress — the blank streak must reset, not just accumulate
        toward the cap regardless of what happens in between."""
        import app.services.stream_service as ss
        from loreweave_llm import ToolCallEvent, DoneEvent, TokenEvent

        # blank, blank, REAL intent, blank, blank — none of these five should
        # ever hit the cap (2), since the real call in the middle resets the
        # streak back to 0.
        script = ["", "", "translate this chapter", "", ""]
        passes = {"n": 0}

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                i = passes["n"]
                passes["n"] += 1

                async def gen():
                    if i < len(script):
                        args = json.dumps({"intent": script[i]}) if script[i] else "{}"
                        yield ToolCallEvent(index=0, id=f"c{i}", name=ss.FIND_TOOLS_NAME,
                                            arguments_delta=args)
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="done")
                        yield DoneEvent(finish_reason="stop")
                return gen()

        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})

        tool_call_events = []
        with patch.object(ss, "Client", FakeClient):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "hi"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=kc, session_id="s", project_id=None,
                discovery_catalog=[], discovery_seed_names=set(),
            ):
                if "tool_call" in ch:
                    tool_call_events.append(ch["tool_call"])

        capped = [
            e for e in tool_call_events
            if e.get("ok") is False and "STOP calling find_tools" in (e.get("error") or "")
        ]
        assert capped == [], f"blank streak should have reset on the real call, got {capped}"

    @pytest.mark.asyncio
    async def test_blank_args_generic_backend_tool_capped_within_turn(self):
        """D-BLANK-TOOL-ARGS-LOOP — the OTHER live-reproduced shape (not
        find_tools): a real production session and an independent live
        re-verification both showed the model calling a REGULAR backend tool
        (glossary_web_search) with blank args repeatedly, each attempt
        tripping the domain service's own "required: missing properties"
        validation error, with NO cap on how many times this can happen in
        one turn. After BLANK_TOOL_ARGS_CAP such failures, a further call is
        short-circuited BEFORE the MCP round trip — mcp_execute_tool must not
        even be invoked again this turn."""
        import app.services.stream_service as ss
        from loreweave_llm import ToolCallEvent, DoneEvent, TokenEvent

        TOTAL_BLANK_PASSES = 5
        passes = {"n": 0}

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                i = passes["n"]
                passes["n"] += 1

                async def gen():
                    if i < TOTAL_BLANK_PASSES:
                        yield ToolCallEvent(index=0, id=f"c{i}", name="glossary_web_search",
                                            arguments_delta="{}")
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="giving up")
                        yield DoneEvent(finish_reason="stop")
                return gen()

        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool = AsyncMock(return_value={
            "success": False,
            "error": 'validating "arguments": validating root: required: missing properties: ["query"]',
        })

        tool_call_events = []
        with patch.object(ss, "Client", FakeClient):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "search the web"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=kc, session_id="s", project_id=None,
                discovery_catalog=[], discovery_seed_names=set(),
            ):
                if "tool_call" in ch:
                    tool_call_events.append(ch["tool_call"])

        # Only the first BLANK_TOOL_ARGS_CAP calls actually reach mcp_execute_tool.
        assert kc.mcp_execute_tool.await_count == ss.BLANK_TOOL_ARGS_CAP

        capped = [
            e for e in tool_call_events
            if e.get("ok") is False and "STOP retrying tool calls" in (e.get("error") or "")
        ]
        assert len(capped) == TOTAL_BLANK_PASSES - ss.BLANK_TOOL_ARGS_CAP, (
            f"expected {TOTAL_BLANK_PASSES - ss.BLANK_TOOL_ARGS_CAP} capped calls, "
            f"got {len(capped)}: {tool_call_events}"
        )

    @pytest.mark.asyncio
    async def test_blank_args_streak_shared_across_find_tools_and_generic_tool(self):
        """The real production session mixed BOTH shapes in one turn:
        glossary_web_search blank x2 then find_tools blank x6. The streak
        MUST be shared — two generic-tool blank failures followed by a
        blank-intent find_tools call should trip the cap on that very
        find_tools call, not reset and grant it a fresh budget."""
        import app.services.stream_service as ss
        from loreweave_llm import ToolCallEvent, DoneEvent, TokenEvent

        # glossary_web_search(blank), glossary_web_search(blank), find_tools(blank), ...
        script = [("glossary_web_search", "{}"), ("glossary_web_search", "{}"),
                  (ss.FIND_TOOLS_NAME, "{}"), (ss.FIND_TOOLS_NAME, "{}")]
        passes = {"n": 0}

        class FakeClient:
            def __init__(self, **kw):
                pass

            async def aclose(self):
                pass

            def stream(self, request):
                i = passes["n"]
                passes["n"] += 1

                async def gen():
                    if i < len(script):
                        name, args = script[i]
                        yield ToolCallEvent(index=0, id=f"c{i}", name=name, arguments_delta=args)
                        yield DoneEvent(finish_reason="tool_calls")
                    else:
                        yield TokenEvent(delta="done")
                        yield DoneEvent(finish_reason="stop")
                return gen()

        kc = AsyncMock()
        kc.get_catalog_meta = MagicMock(return_value={})
        kc.mcp_execute_tool = AsyncMock(return_value={
            "success": False,
            "error": 'validating "arguments": validating root: required: missing properties: ["query"]',
        })

        tool_call_events = []
        with patch.object(ss, "Client", FakeClient):
            async for ch in ss._stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id="u",
                messages=[{"role": "user", "content": "search the web"}],
                gen_params={"max_tokens": 100}, tools=[],
                knowledge_client=kc, session_id="s", project_id=None,
                discovery_catalog=[], discovery_seed_names=set(),
            ):
                if "tool_call" in ch:
                    tool_call_events.append(ch["tool_call"])

        # Both find_tools calls happen AFTER the streak already hit the cap
        # from the two glossary_web_search failures — so BOTH must be capped,
        # and find_tools_result_async's own note must never run for them.
        find_tools_events = [e for e in tool_call_events if e["tool"] == ss.FIND_TOOLS_NAME]
        assert len(find_tools_events) == 2
        assert all(e["ok"] is False for e in find_tools_events)
        assert all("STOP calling find_tools" in e["error"] for e in find_tools_events)
        # Only the two glossary_web_search calls ever reached the MCP transport.
        assert kc.mcp_execute_tool.await_count == 2


# ════════════════════════════════════════════════════════════════════════════
# W1 — Context-Breakdown Spine: the extended contextBudget frame + the
# compaction frame + persistence (integration through stream_response).
# ════════════════════════════════════════════════════════════════════════════


def _custom_events(events: list[str], name: str) -> list[dict]:
    out = []
    for e in events:
        payload = e.removeprefix("data: ").strip()
        if not payload or payload == "[DONE]":
            continue
        ev = json.loads(payload)
        if ev.get("type") == "CUSTOM" and ev.get("name") == name:
            out.append(ev["value"])
    return out


class TestW1ContextBreakdownFrame:
    @pytest.mark.asyncio
    async def test_context_budget_frame_carries_breakdown_additively(self):
        """agui turn → ONE contextBudget CUSTOM frame with the old keys intact
        plus breakdown / baseline_tokens / until_compact_pct; the knowledge
        per-section map nests under memory_knowledge."""
        pool, conn = _make_pool_with_conn()
        # one replayed history row (the just-persisted user turn) → history > 0.
        pool.fetch.return_value = [{"role": "user", "content": "Hi"}]
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        pool.fetchrow.return_value = {
            "system_prompt": "You are a helpful lore assistant.",
            "generation_params": {},
        }
        kc = _patched_knowledge(
            context='<memory mode="static">lore</memory>',
            sections={"glossary_entities": 42, "instructions": 7},
        )
        chunks = [_dict_chunk(content="Hi"), _make_chunk(None, usage=_Usage(1000, 5))]
        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)

        frames = _custom_events(events, "contextBudget")
        assert len(frames) == 1
        frame = frames[0]
        # Old keys byte-identical to the pre-W1 contract (FE meter).
        assert frame["used_tokens"] == 1000
        assert frame["context_length"] == 40_000
        assert frame["effective_limit"] == 40_000 - 512
        assert frame["pct"] == round(1000 / (40_000 - 512), 4)
        # Additive keys.
        assert frame["until_compact_pct"] == round(0.75 - frame["pct"], 4)
        bd = frame["breakdown"]
        assert bd["system_prompt"] > 0
        assert bd["memory_knowledge"]["total"] > 0
        assert bd["memory_knowledge"]["sections"] == {"glossary_entities": 42, "instructions": 7}
        assert bd["history"] > 0  # the user turn replays through history
        assert frame["baseline_tokens"] >= bd["system_prompt"] + bd["memory_knowledge"]["total"]
        # No tools this turn → the schema buckets are 0, present, not missing.
        assert bd["frontend_tool_schemas"] == 0
        assert bd["mcp_tool_schemas"] == 0

    @pytest.mark.asyncio
    async def test_schema_tokens_chunk_folds_into_frame_and_persisted_row(self):
        """The tool loop's schema_tokens chunk lands in the frame's breakdown
        AND in the persisted context_breakdown JSONB."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"schema_tokens": {"frontend_tool_schemas": 111, "mcp_tool_schemas": 2222}}
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(10, 2)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)

        frame = _custom_events(events, "contextBudget")[0]
        assert frame["breakdown"]["frontend_tool_schemas"] == 111
        assert frame["breakdown"]["mcp_tool_schemas"] == 2222
        # baseline includes the schema buckets (fixed overhead before the user word).
        assert frame["baseline_tokens"] >= 111 + 2222
        # And the same payload was persisted on the assistant row ($12, second-to-last
        # arg since the stateful-chain feature appended response_id as $13).
        insert_calls = [c for c in conn.fetchrow.call_args_list
                        if "INSERT INTO chat_messages" in str(c)]
        persisted = json.loads(insert_param(insert_calls[0], "context_breakdown"))
        assert persisted["breakdown"]["mcp_tool_schemas"] == 2222
        assert persisted["used_tokens"] == frame["used_tokens"]

    @pytest.mark.asyncio
    async def test_used_tokens_reflects_true_context_size_not_tool_loop_sum(self):
        """D-CHAT-CONTEXT-METER-OVERCOUNT regression: a tool-loop turn's
        `usage.prompt_tokens` is the SUM of input across every completion in the
        loop (each iteration re-sends the full prompt — real provider billing),
        but the GUI meter's `used_tokens` (persisted + emitted) must reflect
        `context_size` — the true LAST completion's input size — not that sum.
        A real 54-tool-call/30-completion turn once summed to ~936K on an
        actual ~34K context; this fakes the same shape at a small scale (sum=
        3000 across what would be several completions, true last-call size=
        1000) at the `_stream_with_tools` seam, mirroring the real loop's
        terminal-yield contract (see stream_service.py's `context_size` +
        `usage` pairing at every terminal yield)."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "llm_call_count": 3,
                   "context_size": 1000,
                   "usage": _Usage(3000, 5)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)

        frame = _custom_events(events, "contextBudget")[0]
        assert frame["used_tokens"] == 1000  # true occupancy, NOT the 3000 sum
        assert frame["llm_call_count"] == 3
        # /review-impl LOW: raw_tokens (the Inspector's naive-baseline reduction_pct
        # denominator) must track the same occupancy fix, not just used_tokens — no
        # trace savings fired in this fake scenario, so raw_tokens == used_tokens.
        assert frame["raw_tokens"] == 1000

        insert_calls = [c for c in conn.fetchrow.call_args_list
                        if "INSERT INTO chat_messages" in str(c)]
        persisted = json.loads(insert_param(insert_calls[0], "context_breakdown"))
        assert persisted["used_tokens"] == 1000
        assert persisted["caching"]["context_size"] == 1000
        # The billed input_tokens column is a SEPARATE positional param and must
        # still carry the real summed cost (3000) — this fix must not touch
        # billing, only the context-occupancy meter.
        assert insert_calls[0].args[7] == 3000

    @pytest.mark.asyncio
    async def test_legacy_turn_emits_no_custom_frames_but_persists(self):
        """Legacy wire: context_budget/compaction are Protocol no-ops (no frame,
        no AttributeError) — but the row still persists the breakdown."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        chunks = [_dict_chunk(content="Hi"), _make_chunk(None, usage=_Usage(3, 1))]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(),
                pool=pool, billing=AsyncMock(),
            ):
                events.append(e)
        assert all('"CUSTOM"' not in e for e in events)  # legacy vocabulary only
        insert_calls = [c for c in conn.fetchrow.call_args_list
                        if "INSERT INTO chat_messages" in str(c)]
        assert "context_breakdown" in insert_calls[0].args[0]
        # $12, second-to-last arg since response_id trails it as $13.
        assert json.loads(insert_param(insert_calls[0], "context_breakdown"))["breakdown"]["history"] >= 0


class TestW1CompactionFrame:
    @pytest.mark.asyncio
    async def test_compaction_frame_emitted_when_work_happened(self):
        """Pre-send compaction that actually truncated → a `compaction` CUSTOM
        frame precedes the turn's content (previously log-only)."""
        from app.services.compaction import CompactionReport

        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5

        report = CompactionReport(
            triggered=True, turns_truncated=4,
            tokens_before=9000, tokens_after=4000, steps=["hard_truncate"],
        )

        async def fake_compact(messages, **kwargs):
            return messages, report

        chunks = [_dict_chunk(content="Hi"), _make_chunk(None, usage=_Usage(1, 1))]
        with patch("app.services.stream_service.compact_messages", side_effect=fake_compact), \
             patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)
        frames = _custom_events(events, "compaction")
        assert len(frames) == 1
        assert frames[0]["turns_truncated"] == 4
        assert frames[0]["steps"] == ["hard_truncate"]

    @pytest.mark.asyncio
    async def test_no_compaction_frame_when_nothing_happened(self):
        """A small turn (compaction not triggered / no work) emits NO
        compaction frame — the toast only fires on real evictions."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        chunks = [_dict_chunk(content="Hi"), _make_chunk(None, usage=_Usage(1, 1))]
        with patch("app.services.stream_service._stream_via_gateway", return_value=_fake_gateway(chunks)()):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)
        assert _custom_events(events, "compaction") == []

    @pytest.mark.asyncio
    async def test_in_loop_compaction_chunk_surfaces_as_frame(self):
        """A {"compaction": ...} chunk from the tool loop (mid-turn re-compact)
        is re-emitted as the CUSTOM frame by the consumer."""
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        pool.fetchval.return_value = 5
        kc = _patched_knowledge(
            mode="static",
            tool_defs=[{"type": "function", "function": {"name": "memory_search"}}],
        )

        async def fake_tool_loop(**kwargs):
            yield {"compaction": {"triggered": True, "tool_results_cleared": 2,
                                  "turns_truncated": 0, "summarized": False,
                                  "summarize_failed": False, "overflowed": False,
                                  "tokens_before": 8000, "tokens_after": 5000,
                                  "steps": ["microcompact"]}}
            yield {"content": "answer", "reasoning_content": "",
                   "finish_reason": "stop", "usage": _Usage(1, 1)}

        with patch("app.services.stream_service.get_knowledge_client", return_value=kc), \
             patch("app.services.stream_service._stream_with_tools", side_effect=fake_tool_loop):
            events = []
            async for e in stream_response(
                session_id=TEST_SESSION_ID, user_message_content="Hi",
                user_id=TEST_USER_ID, model_source="user_model",
                model_ref=TEST_MODEL_REF, creds=_make_creds(context_length=40_000),
                pool=pool, billing=AsyncMock(), stream_format="agui",
            ):
                events.append(e)
        frames = _custom_events(events, "compaction")
        assert len(frames) == 1
        assert frames[0]["tool_results_cleared"] == 2


class TestResolveAndStashReasoning:
    """review-impl H: session-stored reasoning vocabulary (off|auto|...) is NOT
    wire vocabulary — every gen_params->StreamRequest path must resolve it."""

    def _creds(self, kind="openai", name="gpt-4"):
        from app.models import ProviderCredentials
        return ProviderCredentials(
            provider_kind=kind, provider_model_name=name,
            base_url="http://x", api_key="k", context_length=8192,
        )

    def test_session_off_translates_to_wire_none(self):
        from app.services.stream_service import _resolve_and_stash_reasoning
        gp = {"reasoning_effort": "off"}
        _resolve_and_stash_reasoning(gp, self._creds())
        # "off" is invalid on the wire; the resolved fields use "none".
        assert gp.get("reasoning_effort") in (None, "none")
        assert gp.get("reasoning_effort") != "off"

    def test_session_auto_without_creds_omits_fields(self):
        from app.services.stream_service import _resolve_and_stash_reasoning
        gp = {"reasoning_effort": "auto"}
        _resolve_and_stash_reasoning(gp, None)  # voice path: no creds
        assert "reasoning_effort" not in gp
        assert "chat_template_kwargs" not in gp

    def test_session_medium_survives_resolution(self):
        from app.services.stream_service import _resolve_and_stash_reasoning
        gp = {"reasoning_effort": "medium"}
        _resolve_and_stash_reasoning(gp, self._creds(kind="lm_studio", name="qwen3-35b"))
        assert gp.get("reasoning_effort") == "medium"


class TestGroundingToggle:
    """M3 (spec docs/specs/2026-07-05-chat-ai-settings.md) — the explicit grounding
    switch. When the resolved grounding_enabled is False the turn must fetch NO
    retrieval (build_context called with grounding=False), short-circuiting the
    'always on, no toggle' gate-disabled force-on branch. Default True preserves
    the pre-existing always-grounded behavior."""

    async def _run(self, grounding_enabled: bool):
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kclient = _patched_knowledge(stable="", volatile="")

        async def fake_acompletion(**kwargs):
            yield _make_chunk("ok")
            yield _make_chunk(None)

        with patch(
            "app.services.stream_service.get_knowledge_client", return_value=kclient,
        ), patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=lambda **k: fake_acompletion(**k),
        ):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="where is Harker?",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                grounding_enabled=grounding_enabled,
            ):
                pass
        return kclient

    @pytest.mark.asyncio
    async def test_grounding_disabled_fetches_no_retrieval(self):
        kclient = await self._run(grounding_enabled=False)
        assert kclient.build_context.call_args.kwargs["grounding"] is False

    @pytest.mark.asyncio
    async def test_grounding_enabled_default_pulls_grounding(self):
        kclient = await self._run(grounding_enabled=True)
        assert kclient.build_context.call_args.kwargs["grounding"] is True


class TestContextMode:
    """D-LONG-WORK-CONTEXT-MODE — `context.mode` auto-detect. The env
    `t5_intent_gate_enabled` is now a deploy CEILING (default on); the per-turn
    enablement is the pressure decision. `off` force-disables; `on` forces the
    tiers allowed; `auto` enables only on a big-lore book (large glossary) — so a
    small/no-glossary book keeps the tiers OFF even under `auto`. Whether the T5
    gate ran is observed by whether `detect_entity_presence` was called."""

    async def _run_capture_detect(
        self, *, context_mode: str, glossary_large: bool = False, t5_ceiling: bool = True,
    ) -> bool:
        from app.config import settings
        pool, conn = _make_pool_with_conn()
        pool.fetch.return_value = []
        conn.fetchval.return_value = 1
        kclient = _patched_knowledge(stable="", volatile="")
        # A big-lore book: resolve a book_id + a large known-entity (glossary) set so
        # auto-detect trips the glossary signal. Small/absent → glossary_size 0.
        kclient.resolve_book_id = AsyncMock(return_value="book-1" if glossary_large else None)
        seen = {"called": False}

        def _fake_detect(msg, tokens):
            seen["called"] = True
            from app.services.stream_service import EntityPresence
            return EntityPresence(True, reason="test")

        async def fake_acompletion(**kwargs):
            yield _make_chunk("ok")
            yield _make_chunk(None)

        big = frozenset(f"entity{i}" for i in range(400))  # ≥ GLOSSARY_LARGE (300)
        known = AsyncMock()
        known.get_known_entity_tokens = AsyncMock(return_value=big if glossary_large else frozenset())

        with patch(
            "app.services.stream_service.get_knowledge_client", return_value=kclient,
        ), patch(
            "app.services.stream_service.get_known_entities_client", return_value=known,
        ), patch(
            "app.services.stream_service.resolve_grounding_target",
            return_value=("proj-1", ["proj-1"]),
        ), patch(
            "app.services.stream_service._stream_via_gateway",
            side_effect=lambda **k: fake_acompletion(**k),
        ), patch(
            "app.services.stream_service.detect_entity_presence", side_effect=_fake_detect,
        ), patch.object(settings, "t5_intent_gate_enabled", t5_ceiling):
            async for _ in stream_response(
                session_id=TEST_SESSION_ID,
                user_message_content="q",
                user_id=TEST_USER_ID,
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                creds=_make_creds(),
                pool=pool,
                billing=AsyncMock(),
                context_mode=context_mode,
            ):
                pass
        return seen["called"]

    @pytest.mark.asyncio
    async def test_mode_off_bypasses_t5_gate(self):
        assert await self._run_capture_detect(context_mode="off", glossary_large=True) is False

    @pytest.mark.asyncio
    async def test_mode_on_forces_t5_gate_even_small_book(self):
        assert await self._run_capture_detect(context_mode="on", glossary_large=False) is True

    @pytest.mark.asyncio
    async def test_mode_auto_small_book_keeps_tiers_off(self):
        assert await self._run_capture_detect(context_mode="auto", glossary_large=False) is False

    @pytest.mark.asyncio
    async def test_mode_auto_large_book_enables_tiers(self):
        assert await self._run_capture_detect(context_mode="auto", glossary_large=True) is True

    @pytest.mark.asyncio
    async def test_deploy_ceiling_off_force_disables_even_mode_on(self):
        """The env flag is a deploy KILL-SWITCH: t5_intent_gate_enabled=False must
        force the gate OFF even under mode='on' + a large glossary (effective =
        AND(deploy_ceiling, enablement)). Guards the SET-correct ceiling semantics."""
        # mode='on' + large glossary would enable — but the ceiling is off.
        assert await self._run_capture_detect(
            context_mode="on", glossary_large=True, t5_ceiling=False,
        ) is False
