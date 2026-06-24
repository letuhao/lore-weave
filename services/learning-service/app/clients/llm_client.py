"""Thin loreweave_llm wrapper for the online LLM judge (track phase Q4b).

The online-eval consumer judges sampled extractions via the provider-registry
gateway. The lifted judge (``loreweave_eval.llm_judge``) annotates its client as
the ``JudgeLLMClient`` Protocol — i.e. it calls ``submit_and_wait``. The SDK
``Client`` exposes ``submit_job`` + ``wait_terminal``; this adds the
``submit_and_wait`` shape (submit + poll-to-terminal with one transient retry).
NO direct provider SDK calls (gateway invariant).
"""

from __future__ import annotations

from typing import Any

from loreweave_llm.client import Client as SDKClient
from loreweave_llm.errors import LLMTransientRetryNeededError
from loreweave_llm.models import Job, SubmitJobRequest


class JudgeClient:
    """Structurally satisfies ``loreweave_eval._client.JudgeLLMClient``."""

    def __init__(self, sdk: SDKClient) -> None:
        self._sdk = sdk

    async def aclose(self) -> None:
        await self._sdk.aclose()

    async def submit_and_wait(
        self,
        *,
        user_id: str,
        operation: str,
        model_source: str,
        model_ref: str,
        input: dict[str, Any],
        chunking: Any | None = None,
        job_meta: dict[str, Any] | None = None,
        transient_retry_budget: int = 1,
    ) -> Job:
        attempts = 0
        max_attempts = 1 + transient_retry_budget
        while attempts < max_attempts:
            attempts += 1
            submit = await self._sdk.submit_job(
                SubmitJobRequest(
                    operation=operation,  # type: ignore[arg-type]
                    model_source=model_source,  # type: ignore[arg-type]
                    model_ref=model_ref,
                    input=input,
                    chunking=chunking,
                    job_meta=job_meta,
                ),
                user_id=user_id,
            )
            try:
                return await self._sdk.wait_terminal(
                    submit.job_id, user_id=user_id, transient_retry_budget=1
                )
            except LLMTransientRetryNeededError:
                if attempts >= max_attempts:
                    raise
                continue
        raise RuntimeError("submit_and_wait loop fell through")  # pragma: no cover


def build_judge_client(*, base_url: str, internal_token: str) -> JudgeClient:
    """Construct a JudgeClient against provider-registry (internal auth,
    per-call user_id for multi-tenant BYOK judge models)."""
    return JudgeClient(build_judge_sdk(base_url=base_url, internal_token=internal_token))


def build_judge_sdk(*, base_url: str, internal_token: str) -> SDKClient:
    """The raw SDK Client (internal auth, multi-tenant per-call user_id) for the
    DECOUPLED judge path (LLM re-arch Phase 3 M1).

    Unlike ``build_judge_client`` (which wraps ``submit_and_wait``, pinning the
    consumer for the whole judge), the decoupled judge SM needs ``submit_job`` +
    ``get_job`` directly: it submits one batch, persists ``provider_job_id``, and
    resumes off the terminal-event stream. No ``event_redis_url`` — resume is the
    learning-service consumer's job, not the SDK's wait."""
    return SDKClient(
        base_url=base_url,
        auth_mode="internal",
        internal_token=internal_token,
        user_id=None,
    )
