"""K17.2 — ProviderClient unit tests.

Uses httpx.MockTransport injected via the constructor `transport`
test hook (same style as K5's KnowledgeClient test suite) so every
test runs without a real HTTP call. No @patch decorators — the fake
transport captures the outbound request for header/body assertions.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from prometheus_client import REGISTRY

from app.clients.provider_client import (
    ChatCompletionResponse,
    ProviderAuthError,
    ProviderClient,
    ProviderDecodeError,
    ProviderError,
    ProviderInvalidRequest,
    ProviderModelNotFound,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUpstreamError,
)
from app.logging_config import trace_id_var


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_client(
    handler,
    *,
    base_url: str = "http://provider-registry-service:8085",
    internal_token: str = "test-token",
    timeout_s: float = 5.0,
) -> ProviderClient:
    transport = httpx.MockTransport(handler)
    return ProviderClient(
        base_url=base_url,
        internal_token=internal_token,
        timeout_s=timeout_s,
        transport=transport,
    )


def _ok_body(content: str = "hello world", model: str = "gpt-4") -> dict[str, Any]:
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _messages() -> list[dict[str, str]]:
    return [{"role": "user", "content": "ping"}]


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_parsed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body("hello world", "gpt-4"))

    client = _make_client(handler)
    try:
        result = await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
        )
    finally:
        await client.aclose()

    assert isinstance(result, ChatCompletionResponse)
    assert result.content == "hello world"
    assert result.model == "gpt-4"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    assert "choices" in result.raw  # full body preserved


# ── Error classification ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_not_found_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"code": "PROXY_MODEL_NOT_FOUND", "message": "not found"},
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderModelNotFound) as excinfo:
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_auth_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderAuthError) as excinfo:
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_rate_limited_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderRateLimited) as excinfo:
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 429


@pytest.mark.asyncio
async def test_upstream_5xx_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502, json={"code": "PROXY_UPSTREAM_ERROR", "message": "bad gateway"}
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderUpstreamError) as excinfo:
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 502


@pytest.mark.asyncio
async def test_413_body_too_large_raises_upstream_with_explicit_message():
    # K17.2a-R3 (C12): provider-registry's 4 MiB JSON body cap surfaces
    # as HTTP 413 PROXY_BODY_TOO_LARGE. We classify it as
    # ProviderUpstreamError (non-retry) with an explicit message so
    # the cause is obvious in job-failure rows.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413,
            json={"code": "PROXY_BODY_TOO_LARGE", "message": "request body exceeds 4MiB JSON cap"},
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderUpstreamError) as excinfo:
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 413
    assert "body too large" in str(excinfo.value).lower()
    assert "4 mib" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_other_4xx_raises_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": "PROXY_VALIDATION_ERROR"})

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderUpstreamError):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_timeout_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("read timeout", request=request)

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderTimeout):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_connection_refused_raises_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderUpstreamError):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_decode_error_on_missing_choices():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderDecodeError):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_decode_error_on_missing_content():
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ok_body()
        body["choices"][0]["message"].pop("content")
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderDecodeError):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


# ── Phase 3 review Issue 7: 200-with-error body ──────────────────────


@pytest.mark.asyncio
async def test_200_with_rate_error_body_classified_as_rate_limited():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"type": "rate_limit_error", "message": "Too many requests"}},
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderRateLimited):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_200_with_empty_choices_plus_rate_error_classified_as_rate_limited():
    # B5 (R1 review regression): earlier guard `"choices" not in body`
    # wrongly skipped reclassification when choices was an empty list,
    # turning a retry-eligible rate error into ProviderDecodeError.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [],
                "error": {"type": "rate_limit_error", "message": "slow down"},
            },
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderRateLimited):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_200_with_null_error_field_and_valid_choices_returns_ok():
    # Counterpart to the B5 regression: a 200 with {"error": null} and
    # valid choices MUST still succeed. LiteLLM sometimes echoes a null
    # error field alongside a successful response.
    def handler(request: httpx.Request) -> httpx.Response:
        body = _ok_body("hello")
        body["error"] = None
        return httpx.Response(200, json=body)

    client = _make_client(handler)
    try:
        result = await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
        )
    finally:
        await client.aclose()
    assert result.content == "hello"


@pytest.mark.asyncio
async def test_200_with_generic_error_body_classified_as_upstream():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"type": "server_error", "message": "internal"}},
        )

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderUpstreamError):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


# ── Headers + body contents ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_id_forwarded():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_ok_body())

    token = trace_id_var.set("trace-abc-123")
    client = _make_client(handler)
    try:
        await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
        )
    finally:
        await client.aclose()
        trace_id_var.reset(token)

    assert captured["headers"].get("x-trace-id") == "trace-abc-123"


@pytest.mark.asyncio
async def test_internal_token_header_present():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_ok_body())

    client = _make_client(handler, internal_token="super-secret-token")
    try:
        await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
        )
    finally:
        await client.aclose()

    assert captured["headers"].get("x-internal-token") == "super-secret-token"


@pytest.mark.asyncio
async def test_response_format_pass_through():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["url"] = str(request.url)
        return httpx.Response(200, json=_ok_body())

    client = _make_client(handler)
    try:
        await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=512,
        )
    finally:
        await client.aclose()

    body = captured["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 512
    assert body["messages"] == _messages()
    # The model field is a proxy-rewritten placeholder (K17.2a
    # overwrites it server-side). Assert the placeholder is present
    # so a future refactor that drops it trips this test.
    assert body["model"] == "proxy-resolved"
    # URL must carry the resolution query params.
    assert "user_id=u-1" in captured["url"]
    assert "model_source=user_model" in captured["url"]
    assert "model_ref=11111111-1111-1111-1111-111111111111" in captured["url"]


# ── Local validation ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_model_source_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("handler should not be called for invalid args")

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderInvalidRequest):
            await client.chat_completion(
                user_id="u-1",
                model_source="garbage",  # type: ignore[arg-type]
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_empty_messages_raises_invalid_request():
    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("handler should not be called for empty messages")

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderInvalidRequest):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=[],
            )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_invalid_request_is_provider_error_subclass():
    # K17.3 retry wrapper and K16 state machine catch ProviderError
    # broadly. ProviderInvalidRequest MUST be a subclass so local
    # validation failures don't escape the catch net.
    assert issubclass(ProviderInvalidRequest, ProviderError)


# ── Metrics ───────────────────────────────────────────────────────────


def _counter_value(outcome: str) -> float:
    from app.metrics import provider_chat_completion_total
    # prometheus_client.Counter internals — pull the labeled sample.
    return provider_chat_completion_total.labels(outcome=outcome)._value.get()


def _histogram_count(outcome: str) -> float:
    from app.metrics import provider_chat_completion_duration_seconds
    metric = provider_chat_completion_duration_seconds.labels(outcome=outcome)
    return metric._sum.get()


@pytest.mark.asyncio
async def test_metrics_counter_fires_on_success():
    before = _counter_value("ok")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body())

    client = _make_client(handler)
    try:
        await client.chat_completion(
            user_id="u-1",
            model_source="user_model",
            model_ref="11111111-1111-1111-1111-111111111111",
            messages=_messages(),
        )
    finally:
        await client.aclose()

    after = _counter_value("ok")
    assert after == before + 1


@pytest.mark.asyncio
async def test_metrics_counter_fires_on_failure():
    before = _counter_value("not_found")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "PROXY_MODEL_NOT_FOUND"})

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderModelNotFound):
            await client.chat_completion(
                user_id="u-1",
                model_source="user_model",
                model_ref="11111111-1111-1111-1111-111111111111",
                messages=_messages(),
            )
    finally:
        await client.aclose()

    after = _counter_value("not_found")
    assert after == before + 1


@pytest.mark.asyncio
async def test_metrics_counter_fires_on_invalid_request_without_histogram():
    counter_before = _counter_value("invalid_request")

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("handler should not be called")

    client = _make_client(handler)
    try:
        with pytest.raises(ProviderInvalidRequest):
            await client.chat_completion(
                user_id="u-1",
                model_source="garbage",  # type: ignore[arg-type]
                model_ref="x",
                messages=_messages(),
            )
    finally:
        await client.aclose()

    assert _counter_value("invalid_request") == counter_before + 1
    # The histogram for invalid_request is NOT registered — see
    # metrics.py which intentionally skips the labels() call for this
    # outcome so a zero observation would raise KeyError. Assert the
    # label isn't present in the REGISTRY's collected samples.
    from app.metrics import provider_chat_completion_duration_seconds
    collected = provider_chat_completion_duration_seconds.collect()
    sample_labels = {
        tuple(sorted(s.labels.items()))
        for m in collected
        for s in m.samples
    }
    assert (("outcome", "invalid_request"),) not in sample_labels


# ── Lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aclose_is_idempotent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body())

    client = _make_client(handler)
    await client.aclose()
    # Second call must not raise.
    await client.aclose()
