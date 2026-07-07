"""loreweave_llm SDK wrapper (composition-service, M3 — M6 engine + critic).

Mirrors knowledge-service's llm_client: a per-process singleton around the
`loreweave_llm` SDK Client. The M6 co-write engine streams via the `.sdk`
escape hatch; the judge_prose critic (and any blocking completion) uses
`submit_and_wait`. The SDK is multi-tenant — `user_id=None` at construction,
passed per call.

Error discipline (memory `feedback_specific_sdk_exception_catches_before_generic`):
catch `LLMHttpError` (transport) FIRST with bounded exponential backoff, then
the generic `LLMError` last so a permanent SDK error isn't demoted to a retry.
This wrapper does NOT raise on `Job.status=failed` — the caller inspects.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from loreweave_llm.client import Client as SDKClient
from loreweave_llm.errors import LLMError, LLMHttpError, LLMTransientRetryNeededError
from loreweave_llm.models import ChunkingConfig, Job, JobOperation, SubmitJobRequest

from app.config import settings
from app.metrics import llm_inflight_jobs, llm_job_total

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "get_llm_client", "close_llm_client"]

_client: "LLMClient | None" = None


class LLMClient:
    def __init__(self, sdk_client: SDKClient, http_client: httpx.AsyncClient | None = None) -> None:
        self._sdk = sdk_client
        # D-PLANFORGE-DEFAULT-MODEL — a plain httpx client for the one-off
        # provider-registry reads (resolve_planner_model) the SDK doesn't cover.
        # Injectable so tests can swap in an httpx.MockTransport.
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))

    @property
    def sdk(self) -> SDKClient:
        """Direct SDK access — used by the M6 engine for streaming chat."""
        return self._sdk

    async def aclose(self) -> None:
        await self._sdk.aclose()
        await self._http.aclose()

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
        cancel_check: Callable[[], Awaitable[bool]] | None = None,
    ) -> Job:
        """Submit a gateway job + wait for a terminal status, re-submitting on a
        transient terminal (the SDK doesn't retain inputs, so this loop re-issues
        the same args). Returns the terminal Job — does NOT raise on
        `status=failed` (the caller decides). Raises on exhausted transient /
        HTTP failure."""
        attempts = 0
        max_attempts = 1 + transient_retry_budget
        while attempts < max_attempts:
            attempts += 1
            llm_inflight_jobs.inc()
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
                        submit.job_id, user_id=user_id, transient_retry_budget=1,
                        cancel_check=cancel_check,
                    )
                except LLMTransientRetryNeededError as exc:
                    llm_job_total.labels(operation=operation, outcome="transient_retry").inc()
                    if attempts >= max_attempts:
                        llm_job_total.labels(operation=operation, outcome="failed").inc()
                        logger.warning(
                            "submit_and_wait transient retry exhausted op=%s code=%s",
                            operation, exc.underlying_code,
                        )
                        raise
                    if exc.retry_after_s and exc.retry_after_s > 0:
                        await asyncio.sleep(exc.retry_after_s)
                    continue
                llm_job_total.labels(operation=operation, outcome=job.status).inc()
                return job
            except LLMHttpError as exc:
                llm_job_total.labels(operation=operation, outcome="http_retry").inc()
                if attempts >= max_attempts:
                    llm_job_total.labels(operation=operation, outcome="failed").inc()
                    logger.warning("submit_and_wait HTTP retry exhausted op=%s err=%s", operation, exc)
                    raise
                backoff_s = min(0.5 * (2 ** (attempts - 1)), 4.0)
                logger.info(
                    "submit_and_wait HTTP retry op=%s attempt=%d/%d backoff=%.1fs",
                    operation, attempts, max_attempts, backoff_s,
                )
                await asyncio.sleep(backoff_s)
                continue
            except LLMError:
                llm_job_total.labels(operation=operation, outcome="sdk_error").inc()
                raise
            finally:
                llm_inflight_jobs.dec()
        raise RuntimeError("submit_and_wait loop fell through")  # pragma: no cover

    async def resolve_context_length(self, model_source: str, model_ref: str) -> int | None:
        """The model's real context window (tokens), or None when provider-registry
        can't determine it — mirrors `resolve_planner_model`'s best-effort pattern.
        Never fabricates a number on failure (see provider-registry-service's
        `getModelContextWindow` docstring); callers supply their own conservative
        default for the genuinely-unknown case."""
        url = f"{settings.llm_gateway_internal_url}/v1/model-registry/models/{model_ref}/context-window"
        try:
            resp = await self._http.get(
                url, params={"model_source": model_source},
                headers={"X-Internal-Token": settings.internal_service_token},
            )
        except httpx.HTTPError as exc:
            logger.warning("resolve_context_length unreachable: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("resolve_context_length → %d", resp.status_code)
            return None
        try:
            cw = resp.json().get("context_window")
            return int(cw) if cw else None
        except (ValueError, AttributeError) as exc:
            logger.warning("resolve_context_length bad JSON: %s", exc)
            return None

    async def resolve_planner_model(self, user_id: str) -> str | None:
        """D-PLANFORGE-DEFAULT-MODEL — mirrors glossary-service's `resolvePlannerModel`
        (glossary-service/internal/api/providerregistry_client.go): reuses provider-
        registry's already-shipped `GET /internal/planner-model` (the user's explicit
        'planner' default, else their best active chat model — MED-6) instead of
        hard-requiring the caller to name a model_ref. Never raises: an unreachable
        provider-registry or a user with zero chat models both return None, and the
        caller surfaces its own clear error (there's genuinely nothing to plan with)."""
        url = f"{settings.llm_gateway_internal_url}/internal/planner-model"
        try:
            resp = await self._http.get(
                url, params={"user_id": user_id},
                headers={"X-Internal-Token": settings.internal_service_token},
            )
        except httpx.HTTPError as exc:
            logger.warning("resolve_planner_model unreachable: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning("resolve_planner_model → %d", resp.status_code)
            return None
        try:
            return resp.json().get("user_model_id") or None
        except (ValueError, AttributeError) as exc:
            logger.warning("resolve_planner_model bad JSON: %s", exc)
            return None


def get_llm_client() -> LLMClient:
    """Lazy per-worker singleton. Multi-tenant: SDK `user_id=None` at
    construction; each `submit_and_wait` passes `user_id` per call."""
    global _client
    if _client is None:
        sdk = SDKClient(
            base_url=settings.llm_gateway_internal_url,
            auth_mode="internal",
            internal_token=settings.internal_service_token,
            user_id=None,
        )
        _client = LLMClient(sdk)
    return _client


async def close_llm_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
