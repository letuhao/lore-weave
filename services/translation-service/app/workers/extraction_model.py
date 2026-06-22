"""Shared model-capability resolution for the extraction pipeline.

`get_model_context_window` is used by BOTH the executor (worker, for real windowing) and the
pre-job cost estimate (route, to make the planner quote split-aware against the SAME context
the executor will use) — so the quote and the actual run agree on the model's context budget.
Kept here (not in the heavy worker module) so the route can import it without pulling the
worker's LLM/runtime deps.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)

# Conservative fallback when a model doesn't publish a context length (common for local
# models). Mirrors the gateway's context-fit assumption.
FALLBACK_CONTEXT_WINDOW = 8192


async def get_model_context_window(model_source: str | None, model_ref: str | None) -> int:
    """Model context window (tokens) via provider-registry — the same endpoint the translation
    chapter worker uses. Falls back when unknown (local models often don't publish a context
    length). Never raises (best-effort; any failure → the fallback)."""
    if not model_ref:
        return FALLBACK_CONTEXT_WINDOW
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{settings.provider_registry_service_url}"
                f"/v1/model-registry/models/{model_ref}/context-window",
                params={"model_source": model_source or "user_model"},
            )
            if r.status_code == 200:
                return int(r.json().get("context_window") or FALLBACK_CONTEXT_WINDOW)
    except Exception as exc:  # noqa: BLE001 — fall back on any failure
        log.debug("extraction: context_window fetch failed (%s) — fallback %d", exc, FALLBACK_CONTEXT_WINDOW)
    return FALLBACK_CONTEXT_WINDOW
