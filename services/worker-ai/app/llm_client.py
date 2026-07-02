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
import contextvars
import logging
from collections.abc import Awaitable, Callable
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
    "set_billing_user_id",
    "set_campaign_id",
]

logger = logging.getLogger(__name__)

# S4a — Auto-Draft Factory cost attribution. The owning campaign for the
# extraction job running on THIS async task. process_job sets it once
# (set_campaign_id) and submit_and_wait merges it into every provider job's
# job_meta — so a campaign's extraction spend is summable from the usage events
# (decision C). Task-local: concurrent jobs for different campaigns don't cross
# (each asyncio Task copies the context). Default None ⇒ non-campaign jobs are
# unchanged (no campaign_id key added).
_campaign_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "worker_ai_campaign_id", default=None,
)


def set_campaign_id(campaign_id: str | None) -> None:
    """Set the owning campaign for provider jobs submitted on this async task.
    Call once at the start of processing a job; pass None to clear (a
    non-campaign job must not inherit a previous job's campaign)."""
    _campaign_id_ctx.set(campaign_id)


# E0-3 Phase 2a — BYOK caller-pays. When a book collaborator triggers an
# extraction job, every LLM provider call must resolve under the COLLABORATOR's
# user_id (their key + budget), not the project owner's. process_job binds this
# once per job; submit_and_wait overrides the resolving user_id with it. Task-
# local (each asyncio Task copies the context) so concurrent owner/collaborator
# jobs don't cross. Default None ⇒ owner-triggered jobs use the per-call user_id
# unchanged (legacy single-identity path).
_billing_user_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "worker_ai_billing_user_id", default=None,
)


def set_billing_user_id(billing_user_id: str | None) -> None:
    """Set the billing user (collaborator) for provider jobs on this async task.
    Call once at the start of processing a job; pass None to clear (an owner-
    triggered job must not inherit a previous job's collaborator)."""
    _billing_user_id_ctx.set(billing_user_id)


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
        # bug #34 — optional immediate-cancel hook. The loreweave_extraction
        # extractors ALWAYS forward this kwarg (default None), so this concrete
        # wrapper MUST accept it or every extraction dies with `TypeError:
        # unexpected keyword argument 'cancel_check'` (same SDK-mirror drift the
        # knowledge-service wrapper had). Forwarded to wait_terminal.
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> Job:
        """Submit job + wait_terminal with one retry on transient
        upstream errors (LLM_RATE_LIMITED / LLM_UPSTREAM_ERROR).

        Honors gateway-supplied retry_after_s when present. Returns
        the terminal Job (status in {completed, failed, cancelled}).
        Caller inspects Job.status + Job.error to decide what to do —
        this method does NOT raise on Job.status=failed.
        """
        # S4a: stamp the owning campaign (if any) onto job_meta centrally — this
        # is the one chokepoint every extraction LLM call flows through, so no
        # call site in loreweave_extraction can silently drop attribution.
        campaign_id = _campaign_id_ctx.get()
        if campaign_id and (job_meta is None or "campaign_id" not in job_meta):
            job_meta = {**(job_meta or {}), "campaign_id": campaign_id}

        # E0-3 Phase 2a (BYOK caller-pays): when a collaborator triggered this
        # job, resolve the provider call under THEIR user_id (key + budget), not
        # the owner's. This is the single chokepoint every extraction LLM call
        # flows through, so no loreweave_extraction call site can leak the
        # owner's key. None ⇒ owner-triggered ⇒ per-call user_id unchanged.
        billing_user_id = _billing_user_id_ctx.get()
        if billing_user_id:
            user_id = billing_user_id

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
                        cancel_check=cancel_check,
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

    async def submit_job(
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
    ):
        """LLM re-arch Phase 2b WX-T3b — fire-and-forget submit for the decoupled
        extraction orchestrator: stamp campaign + BYOK caller-pays attribution (the
        SAME chokepoint as submit_and_wait) then return the SDK submit response
        (job_id) WITHOUT waiting. The llm_extract_consumer resumes on the terminal
        event. Routing the decoupled path through this wrapper keeps the attribution
        + caller-pays invariants — no loreweave_extraction call site sees the raw SDK."""
        campaign_id = _campaign_id_ctx.get()
        if campaign_id and (job_meta is None or "campaign_id" not in job_meta):
            job_meta = {**(job_meta or {}), "campaign_id": campaign_id}
        billing_user_id = _billing_user_id_ctx.get()
        if billing_user_id:
            user_id = billing_user_id
        return await self._sdk.submit_job(
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

    async def get_job(self, job_id, *, user_id: str | None = None) -> Job:
        """Fetch the terminal Job (the consumer's resume reads result + status)."""
        return await self._sdk.get_job(job_id, user_id=user_id)


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
            # LLM re-arch Phase 2 — event-driven resume. wait_terminal now wakes
            # on the job's terminal event (loreweave:events:llm_job_terminal)
            # instead of pure-polling, degrading to the poll on any Redis fault.
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
