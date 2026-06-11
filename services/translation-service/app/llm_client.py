"""Phase 4c-α — translation-service LLM client wrapper.

Thin wrapper around the loreweave_llm SDK Client adding the
'submit + wait_terminal with caller-side retry budget' pattern.
Mirrors knowledge-service's + worker-ai's LLMClient minus per-service
metrics (translation-service has no metrics module yet).

Translation-service uses this to call `loreweave_llm.Client.submit_job`
with `operation="translation"` (gateway routes to chatAggregator) for
buffered translation calls. Streaming translation calls (4c-β) will
go through `Client.stream(...)` directly.
"""

from __future__ import annotations

import asyncio
import contextvars
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
    "set_campaign_id",
]

logger = logging.getLogger(__name__)

# S4a — Auto-Draft Factory cost attribution. The owning campaign for the work
# currently running on THIS async task. A worker sets it once at the top of a
# chapter (set_campaign_id) and submit_and_wait merges it into every provider
# job's job_meta — so a campaign's spend can be summed from the usage events
# (decision C) WITHOUT threading the id through every call site. A ContextVar is
# task-local: concurrent chapters for different campaigns never cross-contaminate
# (each asyncio Task copies the context). Default None ⇒ non-campaign work is
# unchanged (no campaign_id key added).
_campaign_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "translation_campaign_id", default=None,
)


def set_campaign_id(campaign_id: str | None) -> None:
    """Set the owning campaign for provider jobs submitted on this async task.
    Call once at the start of processing a unit of work; pass None to clear (a
    non-campaign message must not inherit a previous campaign's id)."""
    _campaign_id_ctx.set(campaign_id)


class LLMClient:
    """submit_and_wait wrapper. Caller-side retry budget=1 by default
    handles submit-time transients; the SDK's per-poll budget handles
    in-flight transient blips."""

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
        upstream errors. Honors gateway-supplied retry_after_s.

        Returns the terminal Job (status in {completed, failed,
        cancelled}). Caller inspects Job.status + Job.error to decide
        what to do — this method does NOT raise on Job.status=failed.
        """
        # S4a: stamp the owning campaign (if any) onto job_meta so the provider
        # job is attributable to a campaign's cumulative spend. Done centrally
        # here — the one chokepoint every translation LLM call flows through —
        # rather than at each call site, so no site can silently drop attribution.
        # An explicit caller-supplied campaign_id (none today) is left untouched.
        campaign_id = _campaign_id_ctx.get()
        if campaign_id and (job_meta is None or "campaign_id" not in job_meta):
            job_meta = {**(job_meta or {}), "campaign_id": campaign_id}

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
    """Lazy-construct the shared LLMClient. Same per-process singleton
    pattern as knowledge-service + worker-ai.

    Multi-tenant: SDK Client has user_id=None; each submit_and_wait
    passes user_id per-call (translation-service runs jobs for many
    users from one process)."""
    global _client
    if _client is None:
        sdk = SDKClient(
            base_url=settings.provider_registry_internal_url,
            auth_mode="internal",
            internal_token=settings.internal_service_token,
            user_id=None,  # per-call override required (multi-tenant)
            # LLM re-arch Phase 2 — event-driven resume. wait_terminal wakes on
            # the job's terminal event (loreweave:events:llm_job_terminal) instead
            # of pure-polling, degrading to the poll on any Redis fault.
            # Transparent: no call-site change; submit_and_wait stays the adapter.
            event_redis_url=settings.redis_url,
        )
        _client = LLMClient(sdk)
    return _client


async def close_llm_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
