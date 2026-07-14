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


async def _fake_gateway_stream(*_a, **_k):
    # two content deltas, then the trailing usage+finish chunk (content == "")
    yield {"content": "Hello ", "reasoning_content": "", "finish_reason": None, "usage": None}
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


def _voice_pool(session_kind="chat"):
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
        "project_id": None, "project_ids": None, "working_memory_seed": None,
        "session_kind": session_kind,
    }
    pool._conn = conn
    return pool


@pytest.fixture
def _patch_pipeline(monkeypatch):
    monkeypatch.setattr(vss, "_stream_via_gateway", _fake_gateway_stream)
    monkeypatch.setattr(vss, "_generate_tts_chunks", _no_tts)
    monkeypatch.setattr(vss, "_transcribe_audio", AsyncMock(return_value=("hello there", 100)))
    monkeypatch.setattr(vss, "resolve_local_date", AsyncMock(return_value=date(2026, 7, 15)))
    monkeypatch.setattr(vss, "emit_voice_turn", AsyncMock())
    monkeypatch.setattr(vss, "_upload_audio_segment", AsyncMock())
    kctx = SimpleNamespace(context="", working_memory=[], recent_message_count=5)
    kc = MagicMock()
    kc.build_context = AsyncMock(return_value=kctx)
    monkeypatch.setattr(vss, "get_knowledge_client", lambda: kc)


async def _run_voice(billing, session_kind="chat"):
    pool = _voice_pool(session_kind)
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
async def test_billing_logged_with_real_tokens(_patch_pipeline):
    billing = MagicMock()
    billing.log_usage = AsyncMock()
    await _run_voice(billing)
    await asyncio.sleep(0)  # let the fire-and-forget create_task run
    billing.log_usage.assert_awaited_once()
    kwargs = billing.log_usage.await_args.kwargs
    assert kwargs["input_tokens"] == 42
    assert kwargs["output_tokens"] == 17


# ── WS-4.5 — a directly-invoked voice turn on an assistant session records a
#    SKIPPED-capture decision (never silently drops the spoken diary) ──────────
@pytest.mark.asyncio
async def test_assistant_session_records_voice_path_unsupported(_patch_pipeline, monkeypatch):
    import app.services.canon_capture as cc
    spy = AsyncMock()
    monkeypatch.setattr(cc, "persist_capture_status", spy)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    await _run_voice(billing, session_kind="assistant")
    spy.assert_awaited_once()
    decision = spy.await_args.args[2]
    assert decision.fire is False
    assert decision.reason == "voice_path_unsupported"


@pytest.mark.asyncio
async def test_ordinary_chat_session_does_not_record_skip(_patch_pipeline, monkeypatch):
    import app.services.canon_capture as cc
    spy = AsyncMock()
    monkeypatch.setattr(cc, "persist_capture_status", spy)
    billing = MagicMock(); billing.log_usage = AsyncMock()
    await _run_voice(billing, session_kind="chat")
    spy.assert_not_awaited()
