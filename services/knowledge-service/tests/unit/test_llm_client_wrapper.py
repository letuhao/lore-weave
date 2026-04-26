"""Phase 4a-α — knowledge-service llm_client wrapper unit tests.

Per /review-impl HIGH#2 — exercises the wrapper's actual retry-loop
behavior with a fake SDK Client that drives the LLMTransientRetryNeededError
path through the real wrapper code (NOT mocking the wrapper itself).
The earlier extractor tests bypassed the wrapper by mocking LLMClient
directly; this suite locks the wrapper's contract.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.clients.llm_client import LLMClient
from loreweave_llm.errors import LLMTransientRetryNeededError, LLMUpstreamError
from loreweave_llm.models import (
    Job,
    JobError,
    SubmitJobResponse,
)


def _make_submit_response() -> SubmitJobResponse:
    return SubmitJobResponse(
        job_id="00000000-0000-0000-0000-000000000001",
        status="pending",
        submitted_at="2026-04-27T00:00:00Z",
    )


def _make_job(*, status: str, error_code: str | None = None) -> Job:
    error = JobError(code=error_code, message="upstream blip") if error_code else None
    return Job(
        job_id="00000000-0000-0000-0000-000000000001",
        operation="entity_extraction",
        status=status,  # type: ignore[arg-type]
        result={"entities": []} if status == "completed" else None,
        error=error,
        submitted_at="2026-04-27T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_wrapper_retries_on_transient_then_succeeds():
    """HIGH#2 regression — wrapper MUST resubmit when SDK raises
    LLMTransientRetryNeededError on the first attempt and succeed on
    the second. Earlier code passed budget=0 to SDK, so the exception
    never fired and the loop never iterated."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_make_submit_response())
    sdk.wait_terminal = AsyncMock(side_effect=[
        LLMTransientRetryNeededError(
            "transient blip",
            job_id="00000000-0000-0000-0000-000000000001",
            underlying_code="LLM_UPSTREAM_ERROR",
        ),
        _make_job(status="completed"),
    ])

    wrapper = LLMClient(sdk)
    job = await wrapper.submit_and_wait(
        user_id="00000000-0000-0000-0000-000000000001",
        operation="entity_extraction",
        model_source="user_model",
        model_ref="00000000-0000-0000-0000-000000000001",
        input={"messages": []},
        transient_retry_budget=1,
    )

    assert job.status == "completed"
    assert sdk.submit_job.await_count == 2, "expected resubmit on transient"
    assert sdk.wait_terminal.await_count == 2


@pytest.mark.asyncio
async def test_wrapper_passes_nonzero_budget_to_sdk():
    """HIGH#2 root-cause anchor — the SDK must receive budget>0 so it
    actually raises LLMTransientRetryNeededError on transient terminals.
    Pinning the wire contract prevents a future regression to budget=0."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_make_submit_response())
    sdk.wait_terminal = AsyncMock(return_value=_make_job(status="completed"))

    wrapper = LLMClient(sdk)
    await wrapper.submit_and_wait(
        user_id="00000000-0000-0000-0000-000000000001",
        operation="chat",
        model_source="user_model",
        model_ref="00000000-0000-0000-0000-000000000001",
        input={"messages": []},
    )
    call_kwargs = sdk.wait_terminal.await_args.kwargs
    assert call_kwargs["transient_retry_budget"] >= 1, (
        f"wrapper must forward non-zero budget; got {call_kwargs['transient_retry_budget']}"
    )


@pytest.mark.asyncio
async def test_wrapper_exhausts_budget_then_reraises():
    """When budget=1 and both attempts hit transient, wrapper re-raises
    the LLMTransientRetryNeededError on the second exhaustion."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_make_submit_response())
    sdk.wait_terminal = AsyncMock(side_effect=[
        LLMTransientRetryNeededError(
            "1st", job_id="00000000-0000-0000-0000-000000000001",
            underlying_code="LLM_UPSTREAM_ERROR",
        ),
        LLMTransientRetryNeededError(
            "2nd", job_id="00000000-0000-0000-0000-000000000001",
            underlying_code="LLM_UPSTREAM_ERROR",
        ),
    ])

    wrapper = LLMClient(sdk)
    with pytest.raises(LLMTransientRetryNeededError):
        await wrapper.submit_and_wait(
            user_id="00000000-0000-0000-0000-000000000001",
            operation="entity_extraction",
            model_source="user_model",
            model_ref="00000000-0000-0000-0000-000000000001",
            input={"messages": []},
            transient_retry_budget=1,
        )
    assert sdk.submit_job.await_count == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_wrapper_no_retry_for_non_transient_sdk_error():
    """LLMUpstreamError raised at SUBMIT (not from wait_terminal)
    propagates immediately without retry — only LLMTransientRetryNeededError
    triggers the loop's resubmit path."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(side_effect=LLMUpstreamError("submit-side fail"))
    wrapper = LLMClient(sdk)
    with pytest.raises(LLMUpstreamError):
        await wrapper.submit_and_wait(
            user_id="00000000-0000-0000-0000-000000000001",
            operation="chat",
            model_source="user_model",
            model_ref="00000000-0000-0000-0000-000000000001",
            input={"messages": []},
        )
    assert sdk.submit_job.await_count == 1


@pytest.mark.asyncio
async def test_wrapper_honors_retry_after_s_when_present():
    """When the failed Job carries error.retry_after_s, the wrapper
    sleeps that long before resubmit. We don't measure wall-clock; we
    just verify the path is taken (retry happens after exception)."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_make_submit_response())
    sdk.wait_terminal = AsyncMock(side_effect=[
        LLMTransientRetryNeededError(
            "rate limited",
            job_id="00000000-0000-0000-0000-000000000001",
            underlying_code="LLM_RATE_LIMITED",
            retry_after_s=0.001,  # tiny so test runs fast
        ),
        _make_job(status="completed"),
    ])

    wrapper = LLMClient(sdk)
    job = await wrapper.submit_and_wait(
        user_id="00000000-0000-0000-0000-000000000001",
        operation="chat",
        model_source="user_model",
        model_ref="00000000-0000-0000-0000-000000000001",
        input={"messages": []},
        transient_retry_budget=1,
    )
    assert job.status == "completed"
    assert sdk.submit_job.await_count == 2


@pytest.mark.asyncio
async def test_wrapper_per_call_user_id_threaded_to_sdk():
    """Multi-tenant user_id flows through to both submit_job and
    wait_terminal calls (per-call override pattern)."""
    sdk = AsyncMock()
    sdk.submit_job = AsyncMock(return_value=_make_submit_response())
    sdk.wait_terminal = AsyncMock(return_value=_make_job(status="completed"))

    wrapper = LLMClient(sdk)
    await wrapper.submit_and_wait(
        user_id="11111111-1111-1111-1111-111111111111",
        operation="chat",
        model_source="user_model",
        model_ref="00000000-0000-0000-0000-000000000001",
        input={"messages": []},
    )
    submit_kwargs: dict[str, Any] = sdk.submit_job.await_args.kwargs
    wait_kwargs: dict[str, Any] = sdk.wait_terminal.await_args.kwargs
    assert submit_kwargs["user_id"] == "11111111-1111-1111-1111-111111111111"
    assert wait_kwargs["user_id"] == "11111111-1111-1111-1111-111111111111"
