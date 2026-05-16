"""Phase 5c-α — SDK tests for `Client.generate_image()`.

Mirrors test_audio.py's transcribe pattern: httpx.MockTransport for
the submit + wait_terminal loop. No live gateway needed.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from loreweave_llm import (
    Client,
    ImageGenDataItem,
    ImageGenResult,
    LLMImageContentPolicy,
    LLMImageGenerationFailed,
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


# ── generate_image() happy paths ────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_image_happy_path_url_mode():
    """Submit (202) → poll (completed) → ImageGenResult decoded with URL."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/internal/llm/jobs":
            captured["submit_body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        if req.method == "GET" and req.url.path == f"/internal/llm/jobs/{JOB_UUID}":
            return httpx.Response(
                200,
                json={
                    "job_id": JOB_UUID,
                    "operation": "image_gen",
                    "status": "completed",
                    "result": {
                        "created": 1700000000,
                        "data": [
                            {"url": "https://cdn.example/img/abc.png"},
                        ],
                    },
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                    "completed_at": "2026-05-13T00:00:30.000000000Z",
                },
            )
        return httpx.Response(404)

    client = _make_client(handler)
    # n omitted intentionally — verifies the "no n on wire when caller
    # doesn't specify" path. Per Phase 5c-α /review-impl(BUILD) MED#1, the
    # SDK now distinguishes `n=None` (omit; use upstream default) from
    # `n=<int>` (literal; send on wire).
    result = await client.generate_image(
        "a serene mountain lake at dawn",
        model_source="user_model",
        model_ref=MODEL_REF,
        size="1024x1024",
    )

    assert isinstance(result, ImageGenResult)
    assert result.created == 1700000000
    assert len(result.data) == 1
    assert result.data[0].url == "https://cdn.example/img/abc.png"
    assert result.data[0].b64_json is None

    # Wire-shape on submit
    assert captured["submit_body"]["operation"] == "image_gen"
    assert captured["submit_body"]["model_source"] == "user_model"
    assert captured["submit_body"]["model_ref"] == MODEL_REF
    assert captured["submit_body"]["input"]["prompt"] == "a serene mountain lake at dawn"
    assert captured["submit_body"]["input"]["size"] == "1024x1024"
    # n was NOT passed by caller — wire body must omit it so gateway
    # forwards omission to upstream (which then applies its own default).
    assert "n" not in captured["submit_body"]["input"]


@pytest.mark.asyncio
async def test_generate_image_b64_response_format():
    """response_format=b64_json → b64_json populated, url is None."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            body = json.loads(req.content)
            assert body["input"]["response_format"] == "b64_json"
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "image_gen",
                "status": "completed",
                "result": {
                    "created": 1700000001,
                    "data": [{"b64_json": "iVBORw0KGgoAAAANSUhEUg=="}],
                },
                "submitted_at": "2026-05-13T00:00:00.000000000Z",
                "completed_at": "2026-05-13T00:00:30.000000000Z",
            },
        )

    client = _make_client(handler)
    result = await client.generate_image(
        "a forest",
        model_source="user_model",
        model_ref=MODEL_REF,
        response_format="b64_json",
    )
    assert result.data[0].b64_json == "iVBORw0KGgoAAAANSUhEUg=="
    assert result.data[0].url is None


@pytest.mark.asyncio
async def test_generate_image_multi_n_returns_array():
    """n=2 with url-mode result → ImageGenResult.data has 2 entries."""
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            captured["body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "image_gen",
                "status": "completed",
                "result": {
                    "created": 1700000002,
                    "data": [
                        {"url": "https://cdn.example/img/a.png"},
                        {"url": "https://cdn.example/img/b.png"},
                    ],
                },
                "submitted_at": "2026-05-13T00:00:00.000000000Z",
                "completed_at": "2026-05-13T00:01:00.000000000Z",
            },
        )

    client = _make_client(handler)
    result = await client.generate_image(
        "two cats",
        model_source="user_model",
        model_ref=MODEL_REF,
        n=2,
    )
    assert len(result.data) == 2
    assert captured["body"]["input"]["n"] == 2


@pytest.mark.asyncio
async def test_generate_image_explicit_n_one_sends_on_wire():
    """/review-impl(BUILD) MED#1 regression-lock — caller passing
    `n=1` EXPLICITLY MUST send n=1 on the wire (not omit it). The
    prior bug was `if n != 1: include` which dropped explicit n=1,
    silently falling through to upstream's default (which may be
    >1 for DALL-E-2 / local backends), surprising callers asking
    for exactly one image.

    The fix: `if n is not None: include` — explicit pass-through.
    """
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            captured["body"] = json.loads(req.content)
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "image_gen",
                "status": "completed",
                "result": {
                    "created": 1700000003,
                    "data": [{"url": "https://cdn.example/img/single.png"}],
                },
                "submitted_at": "2026-05-13T00:00:00.000000000Z",
                "completed_at": "2026-05-13T00:00:30.000000000Z",
            },
        )

    client = _make_client(handler)
    await client.generate_image(
        "one cat",
        model_source="user_model",
        model_ref=MODEL_REF,
        n=1,  # EXPLICIT — caller wants exactly one image
    )
    # Wire body MUST include n=1, not omit it.
    assert "n" in captured["body"]["input"], \
        "explicit n=1 silently dropped — caller may get >1 from upstream default"
    assert captured["body"]["input"]["n"] == 1


# ── generate_image() validation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_image_rejects_malformed_model_ref_before_wire():
    """Bad UUID rejected client-side; no HTTP call made."""
    handler_called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_called["n"] += 1
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        await client.generate_image(
            "anything",
            model_source="user_model",
            model_ref="not-a-uuid",
        )
    assert handler_called["n"] == 0, "validation must short-circuit before the wire"


@pytest.mark.asyncio
async def test_generate_image_rejects_empty_prompt_before_wire():
    """Empty/whitespace prompt rejected client-side."""
    handler_called = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        handler_called["n"] += 1
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="non-empty"):
        await client.generate_image(
            "   \t\n",
            model_source="user_model",
            model_ref=MODEL_REF,
        )
    assert handler_called["n"] == 0


# ── generate_image() error mapping ──────────────────────────────────


@pytest.mark.asyncio
async def test_generate_image_content_policy_raises_llmimagecontentpolicy():
    """Gateway returns status=failed + LLM_IMAGE_CONTENT_POLICY_VIOLATION
    → SDK raises LLMImageContentPolicy (NOT generic LLMError).
    """

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "image_gen",
                "status": "failed",
                "error": {
                    "code": "LLM_IMAGE_CONTENT_POLICY_VIOLATION",
                    "message": "rejected by safety system",
                },
                "submitted_at": "2026-05-13T00:00:00.000000000Z",
                "completed_at": "2026-05-13T00:00:05.000000000Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMImageContentPolicy, match="rejected"):
        await client.generate_image(
            "anything",
            model_source="user_model",
            model_ref=MODEL_REF,
        )


@pytest.mark.asyncio
async def test_generate_image_generation_failed_raises_llmimagegenerationfailed():
    """Gateway returns LLM_IMAGE_GENERATION_FAILED → dedicated class."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": JOB_UUID,
                    "status": "pending",
                    "submitted_at": "2026-05-13T00:00:00.000000000Z",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "image_gen",
                "status": "failed",
                "error": {
                    "code": "LLM_IMAGE_GENERATION_FAILED",
                    "message": "upstream model failed to load",
                },
                "submitted_at": "2026-05-13T00:00:00.000000000Z",
                "completed_at": "2026-05-13T00:00:05.000000000Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMImageGenerationFailed, match="failed to load"):
        await client.generate_image(
            "anything",
            model_source="user_model",
            model_ref=MODEL_REF,
        )


# ── Regression-lock for from_code mapping ───────────────────────────


def test_image_errors_have_specific_classes_regression_lock():
    """/review-impl(DESIGN) MED#1 + Phase 5b precedent — every image-gen
    gateway code MUST map to its dedicated exception class via
    from_code, NOT fall through to generic LLMError. If a future refactor
    drops the mapping, this test fails fast.
    """
    assert _CODE_TO_EXC.get("LLM_IMAGE_CONTENT_POLICY_VIOLATION") is LLMImageContentPolicy
    assert _CODE_TO_EXC.get("LLM_IMAGE_GENERATION_FAILED") is LLMImageGenerationFailed

    from loreweave_llm.errors import LLMError, from_code

    e1 = from_code("LLM_IMAGE_CONTENT_POLICY_VIOLATION", "msg")
    e2 = from_code("LLM_IMAGE_GENERATION_FAILED", "msg")
    assert isinstance(e1, LLMImageContentPolicy) and not type(e1) is LLMError
    assert isinstance(e2, LLMImageGenerationFailed) and not type(e2) is LLMError


# ── Model round-trip ────────────────────────────────────────────────


def test_image_gen_result_model_round_trip():
    """ImageGenResult pydantic validates expected shapes."""
    result = ImageGenResult.model_validate(
        {
            "created": 1700000000,
            "data": [
                {"url": "https://cdn.example/img.png", "revised_prompt": "rewritten"},
                {"b64_json": "AAAA"},
            ],
        }
    )
    assert result.created == 1700000000
    assert len(result.data) == 2
    assert result.data[0].url == "https://cdn.example/img.png"
    assert result.data[0].revised_prompt == "rewritten"
    assert result.data[1].b64_json == "AAAA"
    assert result.data[1].url is None


def test_image_gen_data_item_allows_all_fields_none():
    """ImageGenDataItem with no fields populated is technically valid
    (though useless) — pydantic shouldn't reject. Real validation
    happens in caller code checking for url/b64_json presence."""
    item = ImageGenDataItem.model_validate({})
    assert item.url is None
    assert item.b64_json is None
    assert item.revised_prompt is None
