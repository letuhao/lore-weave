"""Phase 5d — SDK tests for `Client.generate_video()`.

Mirrors test_image_gen.py's pattern: httpx.MockTransport for the
submit + wait_terminal loop. No live gateway needed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from loreweave_llm import (
    Client,
    LLMInvalidRequest,
    LLMVideoContentPolicy,
    LLMVideoGenerationFailed,
    VideoGenDataItem,
    VideoGenResult,
)
from loreweave_llm.errors import _CODE_TO_EXC


GATEWAY = "http://gateway.test"
USER_ID = "00000000-0000-0000-0000-000000000001"
MODEL_REF = "019d5e3c-1234-7890-abcd-1344e148bf7c"
JOB_UUID = "019d5e3c-aaaa-bbbb-cccc-dddddddddddd"


def _make_client(handler) -> Client:
    transport = httpx.MockTransport(handler)
    return Client(
        base_url=GATEWAY,
        auth_mode="internal",
        internal_token="svc-token",
        user_id=USER_ID,
        transport=transport,
    )


# ── generate_video() happy paths ───────────────────────────────────


@pytest.mark.asyncio
async def test_generate_video_happy_path_url_mode():
    """txt2vid: submit (202) → poll completed → VideoGenResult parsed."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/internal/llm/jobs":
            captured["submit_body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-14T00:00:00.000000000Z",
                },
            )
        if req.method == "GET" and req.url.path == f"/internal/llm/jobs/{JOB_UUID}":
            return httpx.Response(
                200,
                json={
                    "job_id": JOB_UUID,
                    "operation": "video_gen",
                    "status": "completed",
                    "result": {
                        "created": 1700000000,
                        "data": [{"url": "https://cdn.example/video.mp4"}],
                    },
                    "submitted_at": "2026-05-14T00:00:00.000000000Z",
                    "completed_at": "2026-05-14T00:05:00.000000000Z",
                },
            )
        return httpx.Response(404)

    client = _make_client(handler)
    result = await client.generate_video(
        "a cinematic landscape pan at dawn",
        model_source="user_model",
        model_ref=MODEL_REF,
        size="1920x1080",
        duration=5,
    )

    assert isinstance(result, VideoGenResult)
    assert result.created == 1700000000
    assert len(result.data) == 1
    assert result.data[0].url == "https://cdn.example/video.mp4"

    # Wire-shape on submit
    body = captured["submit_body"]
    assert body["operation"] == "video_gen"
    assert body["input"]["prompt"] == "a cinematic landscape pan at dawn"
    assert body["input"]["size"] == "1920x1080"
    assert body["input"]["duration"] == 5
    # init_image NOT included in txt2vid path
    assert "init_image" not in body["input"]


# TestGenerateVideo_Img2VidIncludesInitImageField — /review-impl(DESIGN)
# HIGH#1 regression-lock: caller passes `init_image=` (NOT `image=`); SDK
# forwards it to wire body as `init_image` (NOT `image`).
@pytest.mark.asyncio
async def test_generate_video_img2vid_includes_init_image_field():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            captured["body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-14T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "video_gen",
                "status": "completed",
                "result": {
                    "created": 1700000001,
                    "data": [{"url": "https://cdn.example/i2v.mp4"}],
                },
                "submitted_at": "2026-05-14T00:00:00.000000000Z",
                "completed_at": "2026-05-14T00:05:00.000000000Z",
            },
        )

    client = _make_client(handler)
    await client.generate_video(
        "animate this scene with a slow pan",
        model_source="user_model",
        model_ref=MODEL_REF,
        init_image="iVBORw0KGgo...",  # base64-ish placeholder
    )
    body = captured["body"]
    # Field name is `init_image`, NOT `image` (HIGH#1 fix lock)
    assert body["input"]["init_image"] == "iVBORw0KGgo..."
    assert "image" not in body["input"], "should use init_image NOT image (HIGH#1)"


# ── generate_video() validation ────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_video_rejects_malformed_model_ref_before_wire():
    handler_called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_called["n"] += 1
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        await client.generate_video(
            "anything",
            model_source="user_model",
            model_ref="not-a-uuid",
        )
    assert handler_called["n"] == 0


@pytest.mark.asyncio
async def test_generate_video_rejects_empty_prompt_before_wire():
    handler_called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_called["n"] += 1
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="non-empty"):
        await client.generate_video(
            "   \t\n",
            model_source="user_model",
            model_ref=MODEL_REF,
        )
    assert handler_called["n"] == 0


# TestGenerateVideo_RejectsB64Format — /review-impl(BUILD) MED#1. The
# SDK signature uses `Literal["url"]` for response_format, which mypy/
# pyright catches at static-check time. But Python doesn't enforce
# Literal at runtime — a caller bypassing type-checks with
# `response_format="b64_json"` reaches the gateway, which validates
# server-side and returns LLM_INVALID_REQUEST. SDK propagates via
# _raise_http_error → LLMInvalidRequest.
@pytest.mark.asyncio
async def test_generate_video_rejects_b64_format_server_side():
    """Type-bypassed `response_format="b64_json"` is rejected by the
    gateway with LLM_INVALID_REQUEST; SDK surfaces it as
    LLMInvalidRequest (not LLMError).
    """
    def handler(req: httpx.Request) -> httpx.Response:
        # Verify the SDK actually sent b64_json on the wire (type-bypass)
        body = json.loads(req.content)
        assert body["input"]["response_format"] == "b64_json", \
            "SDK should send caller's explicit value on wire"
        return httpx.Response(
            400,
            json={
                "code": "LLM_INVALID_REQUEST",
                "message": "video_gen response_format must be \"url\" (b64_json impractical for video; got \"b64_json\")",
            },
        )

    client = _make_client(handler)
    # type: ignore[arg-type] — deliberately bypassing Literal["url"]
    # to simulate a runtime call from a non-type-checked caller.
    with pytest.raises(LLMInvalidRequest, match="b64_json"):
        await client.generate_video(
            "a cat",
            model_source="user_model",
            model_ref=MODEL_REF,
            response_format="b64_json",  # type: ignore[arg-type]
        )


# ── generate_video() error mapping ─────────────────────────────────


@pytest.mark.asyncio
async def test_generate_video_content_policy_raises_llmvideocontentpolicy():
    """Gateway returns status=failed + LLM_VIDEO_CONTENT_POLICY_VIOLATION
    → SDK raises LLMVideoContentPolicy (NOT generic LLMError).
    """

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-14T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "video_gen",
                "status": "failed",
                "error": {
                    "code": "LLM_VIDEO_CONTENT_POLICY_VIOLATION",
                    "message": "rejected by safety system",
                },
                "submitted_at": "2026-05-14T00:00:00.000000000Z",
                "completed_at": "2026-05-14T00:00:05.000000000Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMVideoContentPolicy, match="rejected"):
        await client.generate_video(
            "anything",
            model_source="user_model",
            model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_video_generation_failed_raises_llmvideogenerationfailed():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-14T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "video_gen",
                "status": "failed",
                "error": {
                    "code": "LLM_VIDEO_GENERATION_FAILED",
                    "message": "model failed to load",
                },
                "submitted_at": "2026-05-14T00:00:00.000000000Z",
                "completed_at": "2026-05-14T00:00:05.000000000Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMVideoGenerationFailed, match="failed to load"):
        await client.generate_video(
            "anything",
            model_source="user_model",
            model_ref=MODEL_REF,
        )


# ── Regression-lock for from_code mapping ──────────────────────────


def test_video_errors_have_specific_classes_regression_lock():
    """Mirror of Phase 5c-α regression-lock — every video-gen gateway
    code MUST map to its dedicated exception class via from_code.
    """
    assert _CODE_TO_EXC.get("LLM_VIDEO_CONTENT_POLICY_VIOLATION") is LLMVideoContentPolicy
    assert _CODE_TO_EXC.get("LLM_VIDEO_GENERATION_FAILED") is LLMVideoGenerationFailed

    from loreweave_llm.errors import LLMError, from_code

    e1 = from_code("LLM_VIDEO_CONTENT_POLICY_VIOLATION", "msg")
    e2 = from_code("LLM_VIDEO_GENERATION_FAILED", "msg")
    assert isinstance(e1, LLMVideoContentPolicy) and not type(e1) is LLMError
    assert isinstance(e2, LLMVideoGenerationFailed) and not type(e2) is LLMError


# ── Pydantic model round-trip ──────────────────────────────────────


def test_video_gen_result_model_round_trip():
    """VideoGenResult pydantic validates expected shape (1 data entry)."""
    result = VideoGenResult.model_validate(
        {
            "created": 1700000000,
            "data": [
                {"url": "https://cdn.example/video.mp4", "revised_prompt": "rewritten"},
            ],
        }
    )
    assert result.created == 1700000000
    assert len(result.data) == 1
    assert result.data[0].url == "https://cdn.example/video.mp4"
    assert result.data[0].revised_prompt == "rewritten"


def test_video_gen_data_max_items_1():
    """VideoGenResult enforces max_length=1 (Phase 5d n=1 lock)."""
    with pytest.raises(Exception):  # pydantic ValidationError
        VideoGenResult.model_validate(
            {
                "created": 1700000000,
                "data": [
                    {"url": "a"},
                    {"url": "b"},  # 2 items — should fail
                ],
            }
        )


def test_video_gen_data_item_allows_all_fields_none():
    item = VideoGenDataItem.model_validate({})
    assert item.url is None
    assert item.revised_prompt is None
