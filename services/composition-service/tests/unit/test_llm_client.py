"""Unit tests for the llm_client submit_and_wait retry loop (fake SDK)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from app.clients.llm_client import LLMClient
from loreweave_llm.errors import LLMHttpError, LLMTransientRetryNeededError


class FakeSDK:
    """Minimal SDK double: submit_job returns a job_id; wait_terminal replays a
    scripted list of behaviours (a Job-like object to return, or an Exception
    instance to raise). submit_job can also be scripted to raise."""

    def __init__(self, wait_behaviors, submit_raises=None):
        self._wait = list(wait_behaviors)
        self._submit_raises = list(submit_raises or [])
        self.submit_calls = 0
        self.wait_calls = 0

    async def submit_job(self, req, *, user_id):
        self.submit_calls += 1
        if self._submit_raises:
            exc = self._submit_raises.pop(0)
            if exc is not None:
                raise exc
        return SimpleNamespace(job_id=f"job{self.submit_calls}")

    async def wait_terminal(self, job_id, *, user_id, transient_retry_budget=1, cancel_check=None):
        self.wait_calls += 1
        self.last_cancel_check = cancel_check  # bug #34 — assert the wrapper forwards it
        b = self._wait.pop(0)
        if isinstance(b, Exception):
            raise b
        return b

    async def aclose(self):
        pass


def _completed():
    return SimpleNamespace(status="completed")


async def _run(sdk, **kw):
    c = LLMClient(sdk)
    return await c.submit_and_wait(
        user_id="u", operation="chat", model_source="platform_model",
        model_ref="m", input={"messages": []}, **kw,
    )


async def test_happy_path_returns_terminal_job():
    sdk = FakeSDK([_completed()])
    job = await _run(sdk)
    assert job.status == "completed"
    assert sdk.submit_calls == 1 and sdk.wait_calls == 1


async def test_cancel_check_is_forwarded_to_wait_terminal():
    # bug #34 — the wrapper must hand its cancel_check to the SDK's wait_terminal
    # so an in-flight LLM call is abortable on user-cancel.
    async def my_check() -> bool:
        return False
    sdk = FakeSDK([_completed()])
    await _run(sdk, cancel_check=my_check)
    assert sdk.last_cancel_check is my_check


async def test_transient_retry_then_success_resubmits():
    transient = LLMTransientRetryNeededError("rate", job_id="j", underlying_code="LLM_RATE_LIMITED")
    sdk = FakeSDK([transient, _completed()])
    job = await _run(sdk, transient_retry_budget=1)
    assert job.status == "completed"
    assert sdk.submit_calls == 2  # re-submitted with same args


async def test_transient_exhausted_raises():
    transient = LLMTransientRetryNeededError("rate", job_id="j", underlying_code="LLM_RATE_LIMITED")
    sdk = FakeSDK([transient])
    with pytest.raises(LLMTransientRetryNeededError):
        await _run(sdk, transient_retry_budget=0)  # max_attempts=1


async def test_http_error_exhausted_raises():
    sdk = FakeSDK([], submit_raises=[LLMHttpError("down")])
    with pytest.raises(LLMHttpError):
        await _run(sdk, transient_retry_budget=0)


# ── D-PLANFORGE-DEFAULT-MODEL — resolve_planner_model ───────────────────────


def _client_with_transport(handler) -> LLMClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LLMClient(FakeSDK([]), http_client=http)


async def test_resolve_planner_model_returns_user_model_id():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Internal-Token")
        return httpx.Response(200, json={"user_model_id": "m-1", "source": "chat_fallback"})

    c = _client_with_transport(handler)
    out = await c.resolve_planner_model("u-1")
    assert out == "m-1"
    assert "user_id=u-1" in seen["url"]


async def test_resolve_planner_model_404_returns_none():
    c = _client_with_transport(lambda r: httpx.Response(404, json={"error": "PLANNER_MODEL_NONE"}))
    assert await c.resolve_planner_model("u-1") is None


async def test_resolve_planner_model_transport_error_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    c = _client_with_transport(handler)
    assert await c.resolve_planner_model("u-1") is None


async def test_resolve_planner_model_bad_json_returns_none():
    c = _client_with_transport(lambda r: httpx.Response(200, content=b"not json"))
    assert await c.resolve_planner_model("u-1") is None


# ── resolve_context_length ───────────────────────────────────────────────────


async def test_resolve_context_length_returns_window():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"context_window": 128000, "resolved": True})

    c = _client_with_transport(handler)
    out = await c.resolve_context_length("user_model", "m-1")
    assert out == 128000
    assert "m-1" in seen["url"] and "context-window" in seen["url"]


async def test_resolve_context_length_unresolved_returns_none():
    c = _client_with_transport(
        lambda r: httpx.Response(200, json={"context_window": None, "resolved": False}),
    )
    assert await c.resolve_context_length("user_model", "m-1") is None


async def test_resolve_context_length_transport_error_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    c = _client_with_transport(handler)
    assert await c.resolve_context_length("user_model", "m-1") is None


async def test_resolve_context_length_bad_json_returns_none():
    c = _client_with_transport(lambda r: httpx.Response(200, content=b"not json"))
    assert await c.resolve_context_length("user_model", "m-1") is None
