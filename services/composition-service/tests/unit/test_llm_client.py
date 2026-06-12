"""Unit tests for the llm_client submit_and_wait retry loop (fake SDK)."""

from __future__ import annotations

from types import SimpleNamespace

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

    async def wait_terminal(self, job_id, *, user_id, transient_retry_budget=1):
        self.wait_calls += 1
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
