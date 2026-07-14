"""WS-4.2a — a voice turn must bill the REAL LLM token counts, not 0/0.

`_stream_via_gateway` delivers the `UsageEvent` on its trailing chunk; the voice
path used to read only `content`/`reasoning_content` and discard usage, so both
the billing row AND the SSE `finish-message` the FE reads reported `0/0`. These
prove the fix by effect at both surfaces.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import ProviderCredentials
import app.services.voice_stream_service as vss


async def _fake_tool_stream(*_a, **_k):
    # WS-4.1-tools — the shared generator yields content, a TOOL_CALL chunk (no 'content' key —
    # voice must NOT KeyError on it), then the trailing usage+finish chunk.
    yield {"content": "Hello ", "reasoning_content": "", "finish_reason": None, "usage": None}
    yield {"tool_call": {"name": "memory_recall"}}  # no 'content' key at all
    yield {"content": "world.", "reasoning_content": "", "finish_reason": None, "usage": None}
    yield {
        "content": "", "reasoning_content": "", "finish_reason": "stop",
        "usage": SimpleNamespace(prompt_tokens=42, completion_tokens=17,
                                 cache_creation_tok=0, cache_read_tok=0),
    }


async def _no_tts(*_a, **_k):
    # an async generator that yields nothing (skip real TTS)
    return
    yield  # pragma: no cover


async def _yielding_tts(*_a, **_k):
    # a fake TTS that yields one audio chunk (event, raw) so tts_chars accumulates
    yield ({"sentenceIndex": 0}, b"\x01\x02")


async def _suspend_stream(*_a, **_k):
    # WS-4.1-tools H1 — content then a SUSPEND chunk (ends the generator, no terminal usage)
    yield {"content": "Let me check", "reasoning_content": "", "finish_reason": None, "usage": None}
    yield {"suspend": {"input_tokens": 30, "output_tokens": 5, "pending_tool_call": {}}}


def _voice_pool(session_kind="chat", project_id=None):
    pool = AsyncMock()
    conn = AsyncMock()
    conn.fetchval.return_value = 1  # sequence_num
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.fetchval.return_value = 1
    pool.fetch.return_value = []  # no history rows
    pool.fetchrow.return_value = {
        "system_prompt": None, "generation_params": {},
        "project_id": project_id, "project_ids": None, "working_memory_seed": None,
        "session_kind": session_kind,
    }
    pool._conn = conn
    return pool


@pytest.fixture
def _patch_pipeline(monkeypatch):
    # voice now consumes _stream_with_tools (WS-4.1-tools); patch it at the source (voice
    # imports it locally at call time).
    monkeypatch.setattr("app.services.stream_service._stream_with_tools", _fake_tool_stream)
    monkeypatch.setattr(vss, "_generate_tts_chunks", _no_tts)
    monkeypatch.setattr(vss, "_transcribe_audio", AsyncMock(return_value=("hello there", 100)))
    monkeypatch.setattr(vss, "resolve_local_date", AsyncMock(return_value=date(2026, 7, 15)))
    monkeypatch.setattr(vss, "emit_voice_turn", AsyncMock())
    monkeypatch.setattr(vss, "_upload_audio_segment", AsyncMock())
    kctx = SimpleNamespace(context="", working_memory=[], recent_message_count=5,
                           canon_capture_enabled=False)
    kc = MagicMock()
    kc.build_context = AsyncMock(return_value=kctx)
    kc.resolve_book_id = AsyncMock(return_value=None)  # no book → capture self-gates to fire=False
    kc.get_tool_definitions = AsyncMock(return_value=[])  # WS-4.1-tools — voice's tool surface
    monkeypatch.setattr(vss, "get_knowledge_client", lambda: kc)
    return SimpleNamespace(kctx=kctx, kc=kc)


async def _run_voice(billing, session_kind="chat", project_id=None):
    pool = _voice_pool(session_kind, project_id)
    creds = ProviderCredentials(
        provider_kind="lm_studio", provider_model_name="m", api_key="x",
        base_url="http://localhost", context_length=8192,
    )
    lines = []
    async for line in vss.voice_stream_response(
        session_id="s1", audio_bytes=b"x" * 100, audio_content_type="audio/webm",
        user_id="u1", model_source="user_model", model_ref="m1",
        creds=creds, pool=pool, billing=billing,
        voice_config={"stt_model_ref": "stt1", "tts_model_ref": "tts1"},
    ):
        lines.append(line)
    return lines


@pytest.mark.asyncio
async def test_finish_message_carries_real_tokens(_patch_pipeline):
    billing = MagicMock()
    billing.log_usage = AsyncMock()
    lines = await _run_voice(billing)
    finish = [l for l in lines if '"finish-message"' in l or '"type": "finish-message"' in l]
    assert finish, f"no finish-message SSE emitted; got: {lines}"
    payload = json.loads(finish[0].split("data: ", 1)[1])
    assert payload["usage"] == {"promptTokens": 42, "completionTokens": 17}


@pytest.mark.asyncio
async def test_wsa1_tools_tool_call_chunk_handled_not_spoken(_patch_pipeline):
    # WS-4.1-tools — a tool_call chunk (no 'content' key) must NOT KeyError; it's surfaced as
    # an SSE 'tool-call' event and never enters the spoken content.
    billing = MagicMock()
    billing.log_usage = AsyncMock()
    lines = await _run_voice(billing)
    assert any('"tool-call"' in l and "memory_recall" in l for l in lines)  # surfaced
    # the spoken text is only the content deltas, never the tool name
    text = "".join(json.loads(l.split("data: ", 1)[1]).get("delta", "")
                    for l in lines if '"text-delta"' in l)
    assert text == "Hello world." and "memory_recall" not in text


@pytest.mark.asyncio
async def test_billing_logged_with_real_tokens(_patch_pipeline):
    billing = MagicMock()
    billing.log_usage = AsyncMock()
    await _run_voice(billing)
    await asyncio.sleep(0)  # let the fire-and-forget create_task run
    # the LLM (chat-purpose) usage carries the real tokens
    calls = [c.kwargs for c in billing.log_usage.await_args_list]
    llm = next(c for c in calls if c.get("purpose", "chat") == "chat")
    assert llm["input_tokens"] == 42 and llm["output_tokens"] == 17


@pytest.mark.asyncio
async def test_wsb_stt_usage_is_plumbed_not_discarded(_patch_pipeline):
    # WS-4.2b — a distinct 'voice_stt' usage record is logged with the audio metering (0
    # token cost, so no faked token-priced charge). TTS is stubbed to no audio here → no
    # tts record; the STT record is the plumbing proof.
    billing = MagicMock()
    billing.log_usage = AsyncMock()
    await _run_voice(billing)
    await asyncio.sleep(0)
    calls = [c.kwargs for c in billing.log_usage.await_args_list]
    stt = next(c for c in calls if c.get("purpose") == "voice_stt")
    assert stt["input_tokens"] == 0 and stt["output_tokens"] == 0  # no faked token cost
    assert "audio_seconds" in stt["input_payload"]


# ── WS-4.1 — a voice turn WIRES canon capture (the real thing, not the WS-4.5 stopgap):
#    maybe_capture_canon is called with the streamed final text + the resolved book, and
#    the decision is persisted so the home strip renders capture ON/OFF with a reason ──
@pytest.mark.asyncio
async def test_voice_turn_wires_canon_capture(_patch_pipeline, monkeypatch):
    import app.services.canon_capture as cc
    _patch_pipeline.kctx.canon_capture_enabled = True
    _patch_pipeline.kc.resolve_book_id = AsyncMock(return_value="book-1")
    seen = {}

    def _fake_maybe(*, ctx, user_id, assistant_turn_count, user_message, assistant_message, model_ref):
        seen["book_id"] = ctx.book_id
        seen["assistant_message"] = assistant_message
        seen["user_message"] = user_message
        return cc.CaptureDecision(fire=True, reason="fire")

    persist_spy = AsyncMock()
    monkeypatch.setattr(cc, "maybe_capture_canon", _fake_maybe)
    monkeypatch.setattr(cc, "persist_capture_status", persist_spy)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    await _run_voice(billing, session_kind="assistant", project_id="proj-1")

    assert seen["assistant_message"] == "Hello world."   # the streamed LLM text
    assert seen["user_message"] == "hello there"          # the STT transcript
    assert seen["book_id"] == "book-1"                    # resolved from the session project
    persist_spy.assert_awaited_once()
    assert persist_spy.await_args.args[2].fire is True    # the real decision is persisted


@pytest.mark.asyncio
async def test_voice_capture_self_gates_when_no_book(_patch_pipeline, monkeypatch):
    # a bookless session → capture RUNS but self-gates to fire=False (reason='no_book'),
    # persisting the visible OFF decision — never a silent skip.
    import app.services.canon_capture as cc
    persist_spy = AsyncMock()
    monkeypatch.setattr(cc, "persist_capture_status", persist_spy)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    await _run_voice(billing, session_kind="chat")  # fixture resolve_book_id → None
    persist_spy.assert_awaited_once()
    assert persist_spy.await_args.args[2].fire is False


@pytest.mark.asyncio
async def test_wsb_tts_billing_branch_records_characters(_patch_pipeline, monkeypatch):
    # WS-4.2b coverage (cold-review M2) — a TTS that yields audio must produce a voice_tts
    # record with tts_characters > 0 (the branch was previously untested).
    import app.services.voice_stream_service as _vss
    monkeypatch.setattr(_vss, "_generate_tts_chunks", _yielding_tts)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    await _run_voice(billing)
    await asyncio.sleep(0)
    calls = [c.kwargs for c in billing.log_usage.await_args_list]
    tts = next(c for c in calls if c.get("purpose") == "voice_tts")
    assert tts["input_payload"]["tts_characters"] > 0
    assert tts["provider_kind"] == ""  # M1 fix — not the chat provider


@pytest.mark.asyncio
async def test_wsa1_suspend_bills_real_tokens_and_surfaces_error(_patch_pipeline, monkeypatch):
    # WS-4.1-tools H1 — a suspend must NOT re-create the 0/0 mis-bill and must surface an error.
    monkeypatch.setattr("app.services.stream_service._stream_with_tools", _suspend_stream)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    lines = await _run_voice(billing)
    await asyncio.sleep(0)
    assert any('"error"' in l and "voice" in l.lower() for l in lines)  # error surfaced
    calls = [c.kwargs for c in billing.log_usage.await_args_list]
    llm = next(c for c in calls if c.get("purpose", "chat") == "chat")
    assert (llm["input_tokens"], llm["output_tokens"]) == (30, 5)  # real tokens, NOT 0/0
