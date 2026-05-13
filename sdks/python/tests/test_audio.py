"""Phase 5a — SDK audio tests for `Client.transcribe()` + `Client.stream_tts()`.

Mirrors the test_client_jobs.py + test_client_stream.py patterns:
- httpx.MockTransport for transcribe (multi-step submit + wait_terminal)
- respx for stream_tts (SSE iteration)

These tests run pure in-memory; no live gateway needed.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
import respx

from loreweave_llm import (
    AudioChunkEvent,
    Client,
    DoneEvent,
    LLMInvalidRequest,
    LLMQuotaExceeded,
    SttResult,
)


GATEWAY = "http://gateway.test"
USER_ID = "00000000-0000-0000-0000-000000000001"
MODEL_REF = "019d5e3c-1234-7890-abcd-1344e148bf7c"
JOB_UUID = "019d5e3c-aaaa-bbbb-cccc-dddddddddddd"
AUDIO_URL = "https://minio.test/voice-uploads/u/s/123.webm"


def _make_client(handler) -> Client:
    transport = httpx.MockTransport(handler)
    return Client(
        base_url=GATEWAY,
        auth_mode="internal",
        internal_token="svc-token",
        user_id=USER_ID,
        transport=transport,
    )


# ── transcribe() ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transcribe_happy_path():
    """submit (202) → wait_terminal poll (completed) → SttResult parsed."""
    captured: dict[str, Any] = {}
    poll_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/internal/llm/jobs":
            captured["submit_body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-04-28T00:00:00.000000000Z",
                },
            )
        if req.method == "GET" and req.url.path == f"/internal/llm/jobs/{JOB_UUID}":
            poll_count["n"] += 1
            return httpx.Response(
                200,
                json={
                    "job_id": JOB_UUID,
                    "operation": "stt",
                    "status": "completed",
                    "result": {
                        "text": "the quick brown fox",
                        "language": "english",
                        "duration_ms": 1234,
                    },
                    "submitted_at": "2026-04-28T00:00:00.000000000Z",
                    "completed_at": "2026-04-28T00:00:01.000000000Z",
                },
            )
        return httpx.Response(404)

    client = _make_client(handler)
    result = await client.transcribe(
        AUDIO_URL,
        model_source="user_model",
        model_ref=MODEL_REF,
        language="en",
    )

    assert isinstance(result, SttResult)
    assert result.text == "the quick brown fox"
    assert result.language == "english"
    assert result.duration_ms == 1234

    # Wire-shape assertions on the submit body
    assert captured["submit_body"]["operation"] == "stt"
    assert captured["submit_body"]["model_source"] == "user_model"
    assert captured["submit_body"]["model_ref"] == MODEL_REF
    assert captured["submit_body"]["input"] == {
        "audio_url": AUDIO_URL,
        "language": "en",
    }
    assert poll_count["n"] >= 1


@pytest.mark.asyncio
async def test_transcribe_failure_raises_mapped_error():
    """Job ends with status=failed + LLM_QUOTA_EXCEEDED → raises LLMQuotaExceeded."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-04-28T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "stt",
                "status": "failed",
                "error": {
                    "code": "LLM_QUOTA_EXCEEDED",
                    "message": "user out of quota",
                },
                "submitted_at": "2026-04-28T00:00:00.000000000Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMQuotaExceeded):
        await client.transcribe(
            AUDIO_URL,
            model_source="user_model",
            model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_transcribe_rejects_malformed_model_ref_before_wire():
    handler_called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_called["n"] += 1
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        await client.transcribe(
            AUDIO_URL,
            model_source="user_model",
            model_ref="not-a-uuid",
        )
    assert handler_called["n"] == 0, "validation must short-circuit before the wire"


# ── stream_tts() ─────────────────────────────────────────────────────


def _sse_body(*frames: tuple[str, str]) -> bytes:
    parts = []
    for event, data in frames:
        parts.append(f"event: {event}\ndata: {data}\n\n")
    return "".join(parts).encode("utf-8")


@pytest.mark.asyncio
async def test_stream_tts_happy_path():
    """SSE: 2 audio-chunk + done → iterator yields 3 events in order."""
    chunk0_b64 = base64.b64encode(b"\xff\xe0\x12\x34").decode()  # mp3-ish bytes
    chunk1_b64 = base64.b64encode(b"\xab\xcd").decode()
    body = _sse_body(
        ("audio-chunk", json.dumps({"event": "audio-chunk", "sequence_id": 0, "data": chunk0_b64, "final": False})),
        ("audio-chunk", json.dumps({"event": "audio-chunk", "sequence_id": 1, "data": chunk1_b64, "final": True})),
        ("done", '{"event":"done"}'),
    )
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream", params={"user_id": USER_ID}).respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = Client(
            base_url=GATEWAY,
            auth_mode="internal",
            internal_token="svc-token",
            user_id=USER_ID,
        )
        events = []
        async for ev in client.stream_tts(
            text="hello",
            model_source="user_model",
            model_ref=MODEL_REF,
        ):
            events.append(ev)
        await client.aclose()

    # Expect: 2 AudioChunkEvent + 1 DoneEvent
    assert len(events) == 3
    assert isinstance(events[0], AudioChunkEvent)
    assert events[0].sequence_id == 0
    assert events[0].final is False
    assert base64.b64decode(events[0].data) == b"\xff\xe0\x12\x34"
    assert isinstance(events[1], AudioChunkEvent)
    assert events[1].sequence_id == 1
    assert events[1].final is True
    assert isinstance(events[2], DoneEvent)


@pytest.mark.asyncio
async def test_stream_tts_error_event_raises():
    body = _sse_body(
        ("error", '{"event":"error","code":"LLM_OPERATION_NOT_SUPPORTED","message":"tts not supported by provider"}'),
    )
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream", params={"user_id": USER_ID}).respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = Client(
            base_url=GATEWAY,
            auth_mode="internal",
            internal_token="svc-token",
            user_id=USER_ID,
        )
        from loreweave_llm import LLMStreamNotSupported  # noqa — kept here so the import is associated with the assertion

        # The mapping is via from_code — LLM_OPERATION_NOT_SUPPORTED is a generic
        # LLMError (no specific subclass exists for "operation not supported"
        # in errors.py); LLMStreamNotSupported is the closest. Assert: ANY
        # LLMError subclass is raised.
        from loreweave_llm import LLMError

        with pytest.raises(LLMError):
            async for _ in client.stream_tts(
                text="hi",
                model_source="user_model",
                model_ref=MODEL_REF,
            ):
                pass
        await client.aclose()


@pytest.mark.asyncio
async def test_stream_tts_rejects_malformed_model_ref():
    client = Client(
        base_url=GATEWAY,
        auth_mode="internal",
        internal_token="svc-token",
        user_id=USER_ID,
    )
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        async for _ in client.stream_tts(
            text="hi",
            model_source="user_model",
            model_ref="not-a-uuid",
        ):
            pass
    await client.aclose()


# ── AudioChunkEvent base64 round-trip ─────────────────────────────────


def test_audio_chunk_event_base64_round_trip():
    raw = b"some random audio bytes \x00\xff\x12\x34"
    encoded = base64.b64encode(raw).decode()
    ev = AudioChunkEvent(event="audio-chunk", sequence_id=42, data=encoded, final=False)
    assert ev.sequence_id == 42
    assert ev.data == encoded
    assert ev.final is False
    decoded = base64.b64decode(ev.data)
    assert decoded == raw
