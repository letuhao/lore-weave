"""Shared best-effort model-context-window resolver.

`GET {base_url}/v1/model-registry/models/{model_ref}/context-window` returns the model's
real, provider-registry-resolved context window — or `context_window: null` when it
genuinely cannot be determined (provider-registry-service's `getModelContextWindow`
deliberately never fabricates a number; see its docstring). Best-effort by design:
returns `None` on missing model_ref, non-200, transport/decode error, AND when the
registry itself reports the window as unresolved. The caller supplies its OWN
conservative fallback for the genuinely-unknown case — never invent one here, that is
exactly the bug class this resolver exists to avoid reintroducing.
"""
from __future__ import annotations

import logging

import httpx

from ._transport import HEADER_INTERNAL_TOKEN, build_timeout

log = logging.getLogger(__name__)


async def resolve_context_length(
    base_url: str,
    model_source: str | None,
    model_ref: str | None,
    *,
    internal_token: str,
    timeout_s: float = 5.0,
) -> int | None:
    """GET {base_url}/v1/model-registry/models/{model_ref}/context-window → context_window.

    Returns `None` on missing model_ref, non-200, or transport/decode failure — never
    raises (best-effort; the caller tolerates a null window and applies its own fallback).
    """
    if not model_ref:
        return None
    url = f"{base_url.rstrip('/')}/v1/model-registry/models/{model_ref}/context-window"
    params = {"model_source": model_source or "user_model"}
    try:
        async with httpx.AsyncClient(timeout=build_timeout(timeout_s)) as client:
            resp = await client.get(
                url, params=params, headers={HEADER_INTERNAL_TOKEN: internal_token},
            )
        if resp.status_code != 200:
            log.debug("context-window %d for %s", resp.status_code, model_ref)
            return None
        cw = resp.json().get("context_window")
        if cw is None:
            return None
        cw_int = int(cw)
        # /review-impl HIGH: a falsy-only check (`if cw else None`) let a stored
        # 0/negative context_length pass through as "resolved" — the DB write path
        # is now validated too, but this stays defense-in-depth against any value
        # that predates that fix or reaches this endpoint some other way.
        return cw_int if cw_int > 0 else None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("context-window resolve failed for %s: %s", model_ref, exc)
        return None
