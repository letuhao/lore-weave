"""loreweave_llm.Client.stream() — unit tests via respx mocked transport.

Tests cover:
- Happy path: tokens → usage → done
- HTTP error responses → exception classification
- SSE-frame error → exception
- Malformed JSON in SSE → LLMDecodeError
- StreamRequest serialization
- Auth mode routing (jwt → /v1/..., internal → /internal/...)
"""

from __future__ import annotations

import httpx
import pytest
import respx

from loreweave_llm import (
    Client,
    DoneEvent,
    LLMAuthFailed,
    LLMDecodeError,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMUpstreamError,
    StreamRequest,
    TokenEvent,
    UsageEvent,
)


GATEWAY = "http://provider-registry-service:8085"
USER_ID = "00000000-0000-0000-0000-000000000001"
MODEL_REF = "00000000-0000-0000-0000-000000000002"


def make_internal_client() -> Client:
    return Client(
        base_url=GATEWAY,
        auth_mode="internal",
        internal_token="test-internal",
        user_id=USER_ID,
    )


def make_jwt_client() -> Client:
    return Client(
        base_url=GATEWAY,
        auth_mode="jwt",
        bearer_token="test-jwt",
    )


def make_request(**overrides) -> StreamRequest:
    base = dict(
        model_source="user_model",
        model_ref=MODEL_REF,
        messages=[{"role": "user", "content": "hi"}],
    )
    base.update(overrides)
    return StreamRequest(**base)


def sse_body(*frames: tuple[str, str]) -> bytes:
    """Build a wire SSE body. Each frame is (event_name, data_json)."""
    parts = []
    for event, data in frames:
        parts.append(f"event: {event}\ndata: {data}\n\n")
    return "".join(parts).encode("utf-8")


@pytest.mark.asyncio
async def test_stream_happy_path_tokens_usage_done():
    body = sse_body(
        ("token", '{"event":"token","delta":"Hello","index":0}'),
        ("token", '{"event":"token","delta":" world","index":1}'),
        ("usage", '{"event":"usage","input_tokens":10,"output_tokens":2,"reasoning_tokens":null}'),
        ("done", '{"event":"done","finish_reason":"stop"}'),
    )
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream", params={"user_id": USER_ID}).respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        events = []
        async for ev in client.stream(make_request()):
            events.append(ev)
        await client.aclose()

    assert len(events) == 4
    assert isinstance(events[0], TokenEvent) and events[0].delta == "Hello"
    assert isinstance(events[1], TokenEvent) and events[1].delta == " world"
    assert isinstance(events[2], UsageEvent) and events[2].input_tokens == 10
    assert isinstance(events[3], DoneEvent) and events[3].finish_reason == "stop"


@pytest.mark.asyncio
async def test_stream_jwt_mode_calls_v1_path():
    body = sse_body(("done", '{"event":"done","finish_reason":"stop"}'))
    with respx.mock(base_url=GATEWAY) as mock:
        route = mock.post("/v1/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_jwt_client()
        async for _ in client.stream(make_request()):
            pass
        await client.aclose()
        assert route.called
        # JWT mode must NOT pass user_id query
        sent_request = route.calls[0].request
        assert "user_id" not in sent_request.url.params
        assert sent_request.headers.get("authorization") == "Bearer test-jwt"


@pytest.mark.asyncio
async def test_stream_internal_mode_passes_user_id_and_token():
    body = sse_body(("done", '{"event":"done","finish_reason":"stop"}'))
    with respx.mock(base_url=GATEWAY) as mock:
        route = mock.post("/internal/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        async for _ in client.stream(make_request()):
            pass
        await client.aclose()
        assert route.called
        sent_request = route.calls[0].request
        assert sent_request.url.params.get("user_id") == USER_ID
        assert sent_request.headers.get("x-internal-token") == "test-internal"


@pytest.mark.asyncio
async def test_stream_done_event_terminates_iteration():
    # Consumer should not receive events after `done`.
    body = sse_body(
        ("token", '{"event":"token","delta":"a","index":0}'),
        ("done", '{"event":"done","finish_reason":"stop"}'),
        ("token", '{"event":"token","delta":"should-not-arrive","index":1}'),
    )
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        deltas = []
        async for ev in client.stream(make_request()):
            if isinstance(ev, TokenEvent):
                deltas.append(ev.delta)
        await client.aclose()

    assert deltas == ["a"]


@pytest.mark.asyncio
async def test_stream_error_event_raises_typed_exception():
    body = sse_body(
        ("error", '{"event":"error","code":"LLM_UPSTREAM_ERROR","message":"boom"}'),
    )
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        with pytest.raises(LLMUpstreamError) as exc:
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()
        assert "boom" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_auth_failed():
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=401,
            json={"code": "LLM_AUTH_FAILED", "message": "bad token"},
        )
        client = make_internal_client()
        with pytest.raises(LLMAuthFailed):
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()


@pytest.mark.asyncio
async def test_http_402_raises_quota_exceeded():
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=402,
            json={"code": "LLM_QUOTA_EXCEEDED", "message": "out of budget"},
        )
        client = make_internal_client()
        with pytest.raises(LLMQuotaExceeded):
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()


@pytest.mark.asyncio
async def test_http_404_raises_model_not_found():
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=404,
            json={"code": "LLM_MODEL_NOT_FOUND", "message": "no such model"},
        )
        client = make_internal_client()
        with pytest.raises(LLMModelNotFound):
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()


@pytest.mark.asyncio
async def test_http_429_raises_rate_limited_with_retry_after():
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=429,
            json={"code": "LLM_RATE_LIMITED", "message": "slow down", "retry_after_s": 12.5},
        )
        client = make_internal_client()
        with pytest.raises(LLMRateLimited) as exc:
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()
        assert exc.value.retry_after_s == 12.5


@pytest.mark.asyncio
async def test_malformed_sse_data_raises_decode_error():
    body = b"event: token\ndata: this-is-not-json\n\n"
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        with pytest.raises(LLMDecodeError):
            async for _ in client.stream(make_request()):
                pass
        await client.aclose()


@pytest.mark.asyncio
async def test_sse_comments_and_event_name_lines_handled():
    # ': keep-alive' comments should be skipped; 'event:' name lines
    # without 'data:' should not produce events.
    body = b": keep-alive\n\nevent: token\ndata: {\"event\":\"token\",\"delta\":\"x\",\"index\":0}\n\n: another comment\n\nevent: done\ndata: {\"event\":\"done\",\"finish_reason\":\"stop\"}\n\n"
    with respx.mock(base_url=GATEWAY) as mock:
        mock.post("/internal/llm/stream").respond(
            status_code=200,
            headers={"Content-Type": "text/event-stream"},
            content=body,
        )
        client = make_internal_client()
        events = []
        async for ev in client.stream(make_request()):
            events.append(ev)
        await client.aclose()

    assert len(events) == 2
    assert isinstance(events[0], TokenEvent) and events[0].delta == "x"
    assert isinstance(events[1], DoneEvent)


def test_request_body_serialization_omits_none_fields():
    req = StreamRequest(
        model_source="user_model",
        model_ref=MODEL_REF,
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
    )
    body = req.to_request_body()
    assert body["model_source"] == "user_model"
    assert body["model_ref"] == MODEL_REF
    assert body["temperature"] == 0.5
    assert "max_tokens" not in body
    assert "trace_id" not in body
    assert body["stream_format"] == "openai"


def test_constructor_validates_auth_inputs():
    with pytest.raises(ValueError, match="bearer_token"):
        Client(base_url=GATEWAY, auth_mode="jwt")
    with pytest.raises(ValueError, match="internal_token and user_id"):
        Client(base_url=GATEWAY, auth_mode="internal")
    with pytest.raises(ValueError, match="internal_token and user_id"):
        Client(base_url=GATEWAY, auth_mode="internal", internal_token="x")


@pytest.mark.asyncio
async def test_submit_job_raises_not_implemented():
    client = make_internal_client()
    with pytest.raises(NotImplementedError):
        await client.submit_job()
    await client.aclose()
