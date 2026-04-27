"""Phase 4b-γ — worker-ai LLM client wrapper.

Thin wrapper around the loreweave_llm SDK Client adding the
'submit + wait_terminal with caller-side retry budget' pattern that
extractors need. Mirrors knowledge-service's LLMClient minus the
Prometheus counters (worker-ai has no metrics module yet).

Worker-ai uses this to call the loreweave_extraction.extract_pass2(...)
library function directly — replacing the legacy synchronous HTTP call
to knowledge-service's /extract-item endpoint that capped the worker
process for the full LLM wall-time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from loreweave_llm.client import Client as SDKClient
from loreweave_llm.errors import LLMError, LLMTransientRetryNeededError
from loreweave_llm.models import (
    ChunkingConfig,
    Job,
    JobOperation,
    SubmitJobRequest,
)

from app.config import settings

__all__ = [
    "LLMClient",
    "get_llm_client",
    "close_llm_client",
]

logger = logging.getLogger(__name__)


class LLMClient:
    """submit_and_wait wrapper satisfying loreweave_extraction's
    LLMClientProtocol. Uses caller-side retry budget=1 by default
    matching the legacy K17.3 semantic — the SDK's per-poll budget
    handles in-flight transient blips while this loop handles
    submit-time transients.
    """

    def __init__(self, sdk_client: SDKClient) -> None:
        self._sdk = sdk_client

    @property
    def sdk(self) -> SDKClient:
        return self._sdk

    async def aclose(self) -> None:
        await self._sdk.aclose()

    async def submit_and_wait(
        self,
        *,
        user_id: str,
        operation: JobOperation,
        model_source: str,
        model_ref: str,
        input: dict[str, Any],
        chunking: ChunkingConfig | None = None,
        trace_id: str | None = None,
        job_meta: dict[str, Any] | None = None,
        transient_retry_budget: int = 1,
    ) -> Job:
        """Submit job + wait_terminal with one retry on transient
        upstream errors (LLM_RATE_LIMITED / LLM_UPSTREAM_ERROR).

        Honors gateway-supplied retry_after_s when present. Returns
        the terminal Job (status in {completed, failed, cancelled}).
        Caller inspects Job.status + Job.error to decide what to do —
        this method does NOT raise on Job.status=failed.
        """
        attempts = 0
        max_attempts = 1 + transient_retry_budget
        while attempts < max_attempts:
            attempts += 1
            try:
                submit = await self._sdk.submit_job(
                    SubmitJobRequest(
                        operation=operation,
                        model_source=model_source,  # type: ignore[arg-type]
                        model_ref=model_ref,
                        input=input,
                        chunking=chunking,
                        trace_id=trace_id,
                        job_meta=job_meta,
                    ),
                    user_id=user_id,
                )
                try:
                    job = await self._sdk.wait_terminal(
                        submit.job_id,
                        user_id=user_id,
                        transient_retry_budget=1,
                    )
                except LLMTransientRetryNeededError as exc:
                    if attempts >= max_attempts:
                        logger.warning(
                            "submit_and_wait transient retry exhausted op=%s job=%s code=%s",
                            operation, exc.job_id, exc.underlying_code,
                        )
                        raise
                    if exc.retry_after_s and exc.retry_after_s > 0:
                        await asyncio.sleep(exc.retry_after_s)
                    continue
                return job
            except LLMError:
                raise
        raise RuntimeError("submit_and_wait loop fell through")  # pragma: no cover


# ── Module-level singleton ────────────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Lazy-construct the shared LLMClient. Same per-worker singleton
    pattern as knowledge-service's get_llm_client.

    Multi-tenant: the SDK Client has user_id=None at construction; each
    submit_and_wait call passes user_id per-call (worker-ai processes
    extraction jobs for many users from one process).
    """
    global _client
    if _client is None:
        sdk = SDKClient(
            base_url=settings.provider_registry_internal_url,
            auth_mode="internal",
            internal_token=settings.internal_service_token,
            user_id=None,  # per-call override required (multi-tenant)
        )
        _client = LLMClient(sdk)
    return _client


async def close_llm_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
