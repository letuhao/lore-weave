"""Phase 4a-α Step 1 — async-job SDK API tests.

Covers submit_job + get_job + wait_terminal + cancel_job. Uses
httpx.MockTransport so tests run pure in-memory (no live gateway needed).
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from loreweave_llm.client import Client
from loreweave_llm.errors import (
    LLMHttpError,
    LLMInvalidRequest,
    LLMJobNotFound,
    LLMRateLimited,
    LLMTransientRetryNeededError,
)
from loreweave_llm.models import (
    ChunkingConfig,
    Job,
    SubmitJobRequest,
    SubmitJobResponse,
)


VALID_UUID = "019d5e3c-1234-7890-abcd-1344e148bf7c"
JOB_UUID = "019d5e3c-aaaa-bbbb-cccc-dddddddddddd"


def _make_client(
    handler,
    *,
    auth_mode: str = "internal",
) -> Client:
    transport = httpx.MockTransport(handler)
    if auth_mode == "internal":
        return Client(
            base_url="http://gateway.test",
            auth_mode="internal",
            internal_token="svc-token",
            user_id="00000000-0000-0000-0000-000000000001",
            transport=transport,
        )
    return Client(
        base_url="http://gateway.test",
        auth_mode="jwt",
        bearer_token="test-jwt",
        transport=transport,
    )


def _stream_request_input() -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.0,
    }


# ── submit_job ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_job_internal_auth_carries_user_id_query():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            202,
            json={
                "job_id": JOB_UUID,
                "status": "pending",
                "submitted_at": "2026-04-26T00:00:00.000000000Z",
            },
        )

    client = _make_client(handler, auth_mode="internal")
    request = SubmitJobRequest(
        operation="entity_extraction",
        model_source="user_model",
        model_ref=VALID_UUID,
        input=_stream_request_input(),
        chunking=ChunkingConfig(strategy="paragraphs", size=15),
        trace_id="t-1",
    )
    resp = await client.submit_job(request)

    assert isinstance(resp, SubmitJobResponse)
    assert str(resp.job_id) == JOB_UUID
    assert resp.status == "pending"
    assert "/internal/llm/jobs" in captured["url"]
    assert "user_id=00000000" in captured["url"]
    assert captured["headers"]["x-internal-token"] == "svc-token"
    assert captured["body"]["operation"] == "entity_extraction"
    assert captured["body"]["chunking"] == {"strategy": "paragraphs", "size": 15}
    assert captured["body"]["trace_id"] == "t-1"


@pytest.mark.asyncio
async def test_submit_job_jwt_auth_routes_v1_path():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["headers"] = dict(req.headers)
        return httpx.Response(
            202,
            json={
                "job_id": JOB_UUID,
                "status": "pending",
                "submitted_at": "2026-04-26T00:00:00.000000000Z",
            },
        )

    client = _make_client(handler, auth_mode="jwt")
    await client.submit_job(
        SubmitJobRequest(
            operation="chat",
            model_source="user_model",
            model_ref=VALID_UUID,
            input=_stream_request_input(),
        )
    )

    assert "/v1/llm/jobs" in captured["url"]
    assert "user_id" not in captured["url"]
    assert captured["headers"]["authorization"] == "Bearer test-jwt"


@pytest.mark.asyncio
async def test_submit_job_rejects_malformed_model_ref_before_wire():
    # Per ADR §5.1 MED#5 — extractor sigs stay str, SDK validates UUID-shape.
    handler_called = False

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal handler_called
        handler_called = True
        return httpx.Response(202, json={})

    client = _make_client(handler)
    with pytest.raises(LLMInvalidRequest, match="UUID-shaped"):
        await client.submit_job(
            SubmitJobRequest(
                operation="chat",
                model_source="user_model",
                model_ref="not-a-uuid",
                input=_stream_request_input(),
            )
        )
    assert not handler_called, "validation must short-circuit before the wire call"


@pytest.mark.asyncio
async def test_submit_job_drops_none_optional_fields_from_wire_payload():
    # exclude_none keeps the gateway request tight + matches openapi
    # nullable-field handling (callback / chunking / trace_id all optional).
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            202,
            json={"job_id": JOB_UUID, "status": "pending", "submitted_at": "x"},
        )

    client = _make_client(handler)
    await client.submit_job(
        SubmitJobRequest(
            operation="chat",
            model_source="user_model",
            model_ref=VALID_UUID,
            input=_stream_request_input(),
        )
    )

    assert "callback" not in captured["body"]
    assert "chunking" not in captured["body"]
    assert "trace_id" not in captured["body"]
    assert "job_meta" not in captured["body"]


# ── get_job ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_returns_typed_job_envelope():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "entity_extraction",
                "status": "completed",
                "result": {"entities": [{"name": "Holmes", "kind": "person"}]},
                "submitted_at": "2026-04-26T00:00:00Z",
                "completed_at": "2026-04-26T00:00:30Z",
            },
        )

    client = _make_client(handler)
    job = await client.get_job(JOB_UUID)

    assert isinstance(job, Job)
    assert job.is_terminal()
    assert job.status == "completed"
    assert job.result == {"entities": [{"name": "Holmes", "kind": "person"}]}


@pytest.mark.asyncio
async def test_get_job_404_raises_job_not_found():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "LLM_JOB_NOT_FOUND", "message": "no such job"})

    client = _make_client(handler)
    with pytest.raises(LLMJobNotFound):
        await client.get_job(JOB_UUID)


# ── wait_terminal ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wait_terminal_polls_until_completed():
    state = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        state["polls"] += 1
        status = "completed" if state["polls"] >= 3 else "running"
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "chat",
                "status": status,
                "submitted_at": "2026-04-26T00:00:00Z",
            },
        )

    client = _make_client(handler)
    job = await client.wait_terminal(JOB_UUID, poll_interval_s=0.001, max_poll_interval_s=0.001)
    assert job.status == "completed"
    assert state["polls"] == 3


@pytest.mark.asyncio
async def test_wait_terminal_raises_transient_retry_on_failed_with_transient_code():
    # ADR §3.3 D3c — caller-side retry budget bridge.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "entity_extraction",
                "status": "failed",
                "error": {
                    "code": "LLM_UPSTREAM_ERROR",
                    "message": "provider returned 502",
                },
                "submitted_at": "2026-04-26T00:00:00Z",
                "completed_at": "2026-04-26T00:00:01Z",
            },
        )

    client = _make_client(handler)
    with pytest.raises(LLMTransientRetryNeededError) as excinfo:
        await client.wait_terminal(JOB_UUID, poll_interval_s=0.001)
    assert excinfo.value.underlying_code == "LLM_UPSTREAM_ERROR"
    assert excinfo.value.job_id == JOB_UUID


@pytest.mark.asyncio
async def test_wait_terminal_returns_failed_job_for_non_transient_code():
    # Permanent errors (LLM_INVALID_REQUEST, LLM_AUTH_FAILED, etc.) are
    # NOT bridged via TransientRetryNeeded — caller inspects Job.status.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "chat",
                "status": "failed",
                "error": {"code": "LLM_INVALID_REQUEST", "message": "bad model_ref"},
                "submitted_at": "2026-04-26T00:00:00Z",
                "completed_at": "2026-04-26T00:00:01Z",
            },
        )

    client = _make_client(handler)
    job = await client.wait_terminal(JOB_UUID, poll_interval_s=0.001)
    assert job.status == "failed"
    assert job.error.code == "LLM_INVALID_REQUEST"


@pytest.mark.asyncio
async def test_wait_terminal_returns_cancelled_job():
    # ADR §5.5 cancel-race correctness — wait_terminal MUST return the
    # cancelled Job so caller's orchestrator can flip extraction_jobs to
    # cancelled (not raise as failure).
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "entity_extraction",
                "status": "cancelled",
                "submitted_at": "2026-04-26T00:00:00Z",
                "completed_at": "2026-04-26T00:00:05Z",
            },
        )

    client = _make_client(handler)
    job = await client.wait_terminal(JOB_UUID, poll_interval_s=0.001)
    assert job.status == "cancelled"
    assert job.is_terminal()


@pytest.mark.asyncio
async def test_wait_terminal_http_failure_within_budget_recovers():
    state = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        state["polls"] += 1
        if state["polls"] == 1:
            raise httpx.ConnectError("transient blip")
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "chat",
                "status": "completed",
                "submitted_at": "2026-04-26T00:00:00Z",
            },
        )

    client = _make_client(handler)
    job = await client.wait_terminal(
        JOB_UUID, poll_interval_s=0.001, transient_retry_budget=1
    )
    assert job.status == "completed"
    assert state["polls"] == 2


@pytest.mark.asyncio
async def test_wait_terminal_http_failure_beyond_budget_propagates():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gateway down")

    client = _make_client(handler)
    with pytest.raises(LLMHttpError):
        await client.wait_terminal(JOB_UUID, poll_interval_s=0.001, transient_retry_budget=1)


@pytest.mark.asyncio
async def test_wait_terminal_backoff_grows_then_caps():
    # Smoke test that interval grows. We can't easily measure the actual
    # sleeps without slowing tests, so test that 5+ polls all happen
    # within a small clamp — exponential backoff to a tiny cap exits fast.
    state = {"polls": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        state["polls"] += 1
        status = "completed" if state["polls"] >= 5 else "running"
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "chat",
                "status": status,
                "submitted_at": "2026-04-26T00:00:00Z",
            },
        )

    client = _make_client(handler)
    started = time.monotonic()
    await client.wait_terminal(JOB_UUID, poll_interval_s=0.001, max_poll_interval_s=0.005, poll_backoff=2.0)
    elapsed = time.monotonic() - started
    assert state["polls"] == 5
    # 4 sleeps clamped to 0.005s each = ~20ms ceiling; allow some slack.
    assert elapsed < 0.5, f"elapsed {elapsed}s suggests backoff didn't cap"


# ── cancel_job ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_job_204_returns_none():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        return httpx.Response(204)

    client = _make_client(handler)
    result = await client.cancel_job(JOB_UUID)
    assert result is None


@pytest.mark.asyncio
async def test_cancel_job_409_terminal_treated_idempotent():
    # Already-terminal jobs return 409 — caller's desired state (job not
    # running) is true either way; we don't raise.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={"code": "LLM_JOB_TERMINAL", "message": "job already cancelled"},
        )

    client = _make_client(handler)
    result = await client.cancel_job(JOB_UUID)
    assert result is None


@pytest.mark.asyncio
async def test_cancel_job_404_raises_not_found():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "LLM_JOB_NOT_FOUND", "message": "no such job"})

    client = _make_client(handler)
    with pytest.raises(LLMJobNotFound):
        await client.cancel_job(JOB_UUID)


# ── Multi-tenant per-call user_id override ───────────────────────────


@pytest.mark.asyncio
async def test_internal_auth_requires_user_id_per_call_or_construction():
    # Phase 4a-α — knowledge-service constructs Client with user_id=None
    # and passes per-call. Test that omitting both raises clearly.
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    client = Client(
        base_url="http://gateway.test",
        auth_mode="internal",
        internal_token="svc-token",
        user_id=None,  # multi-tenant pattern
        transport=transport,
    )
    with pytest.raises(LLMInvalidRequest, match="user_id"):
        await client.submit_job(
            SubmitJobRequest(
                operation="chat",
                model_source="user_model",
                model_ref=VALID_UUID,
                input=_stream_request_input(),
            )
        )


@pytest.mark.asyncio
async def test_cancel_race_polling_observes_external_cancel():
    """Phase 4a-α Step 5 — explicit cancel-race regression per ADR §5.5.

    Simulates: submit returns running; DELETE issued by external actor
    (the test); next poll observes cancelled status. wait_terminal MUST
    return the cancelled Job so the caller can flip business-job state
    without raising as a failure.
    """
    state = {"polls": 0, "cancelled": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "DELETE":
            state["cancelled"] = True
            return httpx.Response(204)
        # GET — return running until external cancel observed,
        # then cancelled
        state["polls"] += 1
        status = "cancelled" if state["cancelled"] else "running"
        return httpx.Response(
            200,
            json={
                "job_id": JOB_UUID,
                "operation": "entity_extraction",
                "status": status,
                "submitted_at": "2026-04-27T00:00:00Z",
                "completed_at": ("2026-04-27T00:00:01Z" if state["cancelled"] else None),
            },
        )

    client = _make_client(handler)

    # Race: kick off wait + an external cancel concurrently. The cancel
    # should land between polls; wait_terminal sees cancelled status next
    # tick and returns the Job (NOT raises).
    async def external_cancel() -> None:
        await asyncio.sleep(0.01)
        await client.cancel_job(JOB_UUID)

    wait_task = asyncio.create_task(
        client.wait_terminal(JOB_UUID, poll_interval_s=0.005, max_poll_interval_s=0.005)
    )
    cancel_task = asyncio.create_task(external_cancel())
    job, _ = await asyncio.gather(wait_task, cancel_task)

    assert job.status == "cancelled"
    assert job.is_terminal()
    assert state["cancelled"] is True
    assert state["polls"] >= 2, "expected at least 2 polls (running + cancelled)"


@pytest.mark.asyncio
async def test_per_call_user_id_overrides_construction_default():
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        return httpx.Response(
            202,
            json={"job_id": JOB_UUID, "status": "pending", "submitted_at": "x"},
        )

    transport = httpx.MockTransport(handler)
    client = Client(
        base_url="http://gateway.test",
        auth_mode="internal",
        internal_token="svc-token",
        user_id="00000000-0000-0000-0000-000000000DEF",  # default
        transport=transport,
    )
    await client.submit_job(
        SubmitJobRequest(
            operation="chat",
            model_source="user_model",
            model_ref=VALID_UUID,
            input=_stream_request_input(),
        ),
        user_id="11111111-1111-1111-1111-111111111111",  # per-call override
    )
    assert "user_id=11111111" in captured["url"], (
        f"expected per-call user_id in url; got {captured['url']}"
    )
