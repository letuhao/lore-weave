"""Shared types for the extraction library — Protocol for the LLM client
shape and a callback type for dropped-item observability."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol

from loreweave_llm.models import ChunkingConfig, Job, JobOperation

__all__ = ["LLMClientProtocol", "DroppedHandler"]


class LLMClientProtocol(Protocol):
    """Structural type the extractors require from an LLM client.

    Knowledge-service's `app.clients.llm_client.LLMClient` wrapper
    satisfies this. Worker-ai (4b-γ) and other services can build
    their own thin wrapper or use the SDK's `Client` directly with
    a small adapter.

    The wrapper is responsible for:
    - submit + wait_terminal sequencing
    - caller-side transient retry budget (default 1)
    - metrics on outcomes (per-service, optional)
    - returning the terminal `Job` (status ∈ completed/failed/cancelled)

    The library never raises — extractors translate errors into
    `ExtractionError`. The wrapper MAY raise `LLMError`/
    `LLMTransientRetryNeededError`; extractors catch both.
    """

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
        ...


# Optional observability callback. Called once per dropped extraction
# item with `(operation, reason)`. Knowledge-service wires this to its
# Prometheus `knowledge_extraction_dropped_total{operation, reason}`
# counter; worker-ai may pass `None` and accept silent drops.
DroppedHandler = Callable[[str, str], None]
