"""Phase 5e-β.2 — SDK tests for `Client.generate_audio()`.

Mirrors test_image_gen.py / test_video_gen.py: httpx.MockTransport for
the submit + wait_terminal loop. No live gateway needed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from loreweave_llm import (
    AudioGenResult,
    Client,
    LLMAudioGenerationFailed,
    LLMInvalidRequest,
)
from loreweave_llm.errors import _CODE_TO_EXC

GATEWAY = "http://gateway.test"
USER_ID = "00000000-0000-0000-0000-000000000001"
MODEL_REF = "019d5e3c-1234-7890-abcd-1344e148bf7c"
JOB_UUID = "019d5e3c-eeee-ffff-0000-111111111111"


def _make_client(handler) -> Client:
    transport = httpx.MockTransport(handler)
    return Client(
        base_url=GATEWAY,
        auth_mode="internal",
        internal_token="svc-token",
        user_id=USER_ID,
        transport=transport,
    )


@pytest.mark.asyncio
async def test_generate_audio_happy_path_b64_default():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/internal/llm/jobs":
            captured["submit_body"] = json.loads(req.content)
            return httpx.Response(202, json={
                "job_id": JOB_UUID, "status": "pending",
                "submitted_at": "2026-05-15T00:00:00.000000000Z",
            })
        if req.method == "GET" and req.url.path == f"/internal/llm/jobs/{JOB_UUID}":
            return httpx.Response(200, json={
                "job_id": JOB_UUID, "operation": "audio_gen", "status": "completed",
                "result": {
                    "created": 1715000000,
                    "data": [{"b64_json": "aGVsbG8=", "content_type": "audio/mpeg", "duration_ms": 1234}],
                },
                "submitted_at": "2026-05-15T00:00:00.000000000Z",
                "completed_at": "2026-05-15T00:00:30.000000000Z",
            })
        return httpx.Response(404)

    client = _make_client(handler)
    result = await client.generate_audio(
        ["hello world"], model_source="user_model", model_ref=MODEL_REF,
    )
    assert isinstance(result, AudioGenResult)
    assert len(result.data) == 1
    assert result.data[0].b64_json == "aGVsbG8="
    assert result.data[0].content_type == "audio/mpeg"
    body = captured["submit_body"]
    assert body["operation"] == "audio_gen"
    assert body["input"]["texts"] == ["hello world"]
    for k in ("voice", "speed", "format", "response_format"):
        assert k not in body["input"], f"{k} should be omitted"


@pytest.mark.asyncio
async def test_generate_audio_explicit_optionals_reach_wire():
    """/review-impl(DESIGN) HIGH#5 — explicit-equal-to-default values must reach the wire."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            captured["submit_body"] = json.loads(req.content)
            return httpx.Response(202, json={
                "job_id": JOB_UUID, "status": "pending",
                "submitted_at": "2026-05-15T00:00:00.000000000Z",
            })
        return httpx.Response(200, json={
            "job_id": JOB_UUID, "operation": "audio_gen", "status": "completed",
            "result": {"created": 1, "data": [{"b64_json": "x", "content_type": "audio/mpeg"}]},
            "submitted_at": "2026-05-15T00:00:00.000000000Z",
            "completed_at": "2026-05-15T00:00:01.000000000Z",
        })

    client = _make_client(handler)
    await client.generate_audio(
        ["hi"], model_source="user_model", model_ref=MODEL_REF,
        voice="alloy", speed=1.0, format="mp3", response_format="b64_json",
    )
    body = captured["submit_body"]
    assert body["input"]["voice"] == "alloy"
    assert body["input"]["speed"] == 1.0
    assert body["input"]["format"] == "mp3"
    assert body["input"]["response_format"] == "b64_json"


@pytest.mark.asyncio
async def test_generate_audio_empty_texts_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    with pytest.raises(LLMInvalidRequest, match="non-empty"):
        await client.generate_audio([], model_source="user_model", model_ref=MODEL_REF)


@pytest.mark.asyncio
async def test_generate_audio_batch_over_cap_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    with pytest.raises(LLMInvalidRequest, match="batch capped"):
        await client.generate_audio(
            ["x"] * 11, model_source="user_model", model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_audio_whitespace_text_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    with pytest.raises(LLMInvalidRequest, match="empty/whitespace"):
        await client.generate_audio(
            ["valid", "   "], model_source="user_model", model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_audio_oversize_text_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    huge = "a" * 4097
    with pytest.raises(LLMInvalidRequest, match="4096-char"):
        await client.generate_audio(
            [huge], model_source="user_model", model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_audio_non_string_text_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    with pytest.raises(LLMInvalidRequest, match="must be str"):
        await client.generate_audio(
            ["valid", 42],  # type: ignore[list-item]
            model_source="user_model", model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_audio_non_uuid_model_ref_rejected():
    client = _make_client(lambda req: httpx.Response(500))
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        await client.generate_audio(
            ["hi"], model_source="user_model", model_ref="not-a-uuid",
        )


@pytest.mark.asyncio
async def test_generate_audio_failed_raises_typed_error():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(202, json={
                "job_id": JOB_UUID, "status": "pending",
                "submitted_at": "2026-05-15T00:00:00.000000000Z",
            })
        return httpx.Response(200, json={
            "job_id": JOB_UUID, "operation": "audio_gen", "status": "failed",
            "error": {"code": "LLM_AUDIO_GENERATION_FAILED", "message": "tts upstream failed"},
            "submitted_at": "2026-05-15T00:00:00.000000000Z",
            "completed_at": "2026-05-15T00:00:01.000000000Z",
        })

    client = _make_client(handler)
    with pytest.raises(LLMAudioGenerationFailed, match="tts upstream failed"):
        await client.generate_audio(
            ["hi"], model_source="user_model", model_ref=MODEL_REF,
        )


def test_audio_gen_code_to_exc_registered():
    """Regression-lock: LLM_AUDIO_GENERATION_FAILED maps to typed class."""
    assert _CODE_TO_EXC["LLM_AUDIO_GENERATION_FAILED"] is LLMAudioGenerationFailed


def test_audio_gen_models_roundtrip():
    raw = {
        "created": 1715000000,
        "data": [
            {"url": "https://example.com/a.mp3", "content_type": "audio/mpeg"},
            {"b64_json": "aGVsbG8=", "content_type": "audio/mpeg", "duration_ms": 500},
        ],
    }
    result = AudioGenResult.model_validate(raw)
    assert len(result.data) == 2
    assert result.data[0].url == "https://example.com/a.mp3"
    assert result.data[1].b64_json == "aGVsbG8="
    out = result.model_dump()
    assert out["data"][0]["url"] == "https://example.com/a.mp3"
