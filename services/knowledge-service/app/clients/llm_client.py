"""Phase 4a-α Step 3 — knowledge-service wrapper around the loreweave_llm SDK.

Manages the per-process Client lifecycle (lifespan-scoped singleton) and
exposes typed helpers that knowledge-service extractors / summary jobs
consume instead of touching the raw SDK directly.

Why a thin wrapper instead of importing loreweave_llm.Client directly:
  - Lifespan integration (one Client per worker process; close on
    shutdown) matches the existing get_provider_client / get_glossary_client
    pattern; deps.py + main.py expect the get_*/close_* shape
  - Ergonomic helper methods (`submit_extraction_job`, `wait_for_entities`)
    keep extractor code free of httpx/SDK noise
  - Future swap to a different transport (RabbitMQ subscriber instead of
    polling, Phase 6) only changes this file

Per ADR §3.3 D5 — knowledge-service owns its prompts; the SDK is purely
a transport. This wrapper does NOT load prompts; extractors compose the
`messages` list themselves and pass it as `input.messages`.
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
from app.metrics import (
    knowledge_llm_inflight_jobs,
    knowledge_llm_job_total,
    knowledge_llm_poll_total,
)

__all__ = [
    "LLMClient",
    "get_llm_client",
    "close_llm_client",
]

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around loreweave_llm.Client adding metrics + the
    'submit + wait_terminal with caller-side retry budget' pattern that
    extractors use.

    Caller-side retry budget per ADR §3.3 D3c is ENFORCED HERE (not in
    the SDK) so the budget can be tuned per call site. Default budget=1
    matches K17.3's pre-migration semantic.
    """

    def __init__(self, sdk_client: SDKClient) -> None:
        self._sdk = sdk_client

    @property
    def sdk(self) -> SDKClient:
        """Escape hatch for callers that need direct SDK access (e.g. for
        streaming chat). Most extraction code should NOT touch this."""
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

        The call MUST be re-issued with the same args because the SDK
        does NOT retain inputs — this method does that for you. Honors
        gateway-supplied retry_after_s when present.

        Increments `knowledge_llm_job_total{operation, outcome}` on
        terminal completion. `knowledge_llm_inflight_jobs` gauge is
        bumped/decremented around the wait so operators can see active
        workload (per ADR §6 Q5).

        Returns the terminal Job (status ∈ {completed, failed, cancelled}).
        Caller inspects Job.status + Job.error to decide what to do —
        this method does NOT raise on Job.status=failed (extractor's job).
        """
        # /review-impl HIGH#2 + LOW#7 fix: forward a non-zero budget to
        # the SDK so wait_terminal RAISES on transient terminals — that
        # exception is what drives this loop's resubmit. Earlier code
        # passed budget=0 which silently disabled the entire retry path.
        # Each wrapper attempt gets its own SDK budget=1 so an HTTP-blip
        # mid-poll inside an attempt is also tolerated.
        attempts = 0
        max_attempts = 1 + transient_retry_budget
        while attempts < max_attempts:
            attempts += 1
            knowledge_llm_inflight_jobs.inc()
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
                    knowledge_llm_job_total.labels(
                        operation=operation, outcome="transient_retry"
                    ).inc()
                    if attempts >= max_attempts:
                        # /review-impl LOW#7 — exhausted-transient is also
                        # a terminal failure for dashboard accounting.
                        # Bump `failed` so summing failed-outcome reflects
                        # all failure modes, not just non-transient-only.
                        knowledge_llm_job_total.labels(
                            operation=operation, outcome="failed"
                        ).inc()
                        logger.warning(
                            "submit_and_wait transient retry exhausted op=%s job=%s code=%s",
                            operation, exc.job_id, exc.underlying_code,
                        )
                        raise
                    # Loop and resubmit. Honor gateway-supplied
                    # retry_after_s when present (rare; LM Studio doesn't
                    # send Retry-After, cloud providers do).
                    if exc.retry_after_s and exc.retry_after_s > 0:
                        await asyncio.sleep(exc.retry_after_s)
                    continue

                knowledge_llm_job_total.labels(
                    operation=operation, outcome=job.status
                ).inc()
                knowledge_llm_poll_total.labels(outcome="terminal").inc()
                return job
            except LLMError:
                knowledge_llm_job_total.labels(
                    operation=operation, outcome="sdk_error"
                ).inc()
                raise
            finally:
                knowledge_llm_inflight_jobs.dec()
        # Loop body always returns or raises; this is unreachable.
        raise RuntimeError("submit_and_wait loop fell through")  # pragma: no cover


# ── Module-level singleton ────────────────────────────────────────────

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Lazy-construct the shared LLMClient. Same per-worker singleton
    pattern as get_provider_client (and chat-service Phase 1c-ii).

    Multi-tenant: the SDK Client has user_id=None at construction; each
    submit_and_wait call passes user_id per-call (knowledge-service
    serves many users from one process)."""
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
