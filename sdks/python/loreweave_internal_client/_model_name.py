"""Shared best-effort model-NAME resolver.

The inventory (P3 SDK-first) found `resolve_model_name` copy-pasted ~byte-identically
across FIVE services (translation / knowledge / composition / campaign / video-gen) —
each `GET /internal/models/{source}/{ref}/info` → `provider_model_name`, each best-effort
(`None` on any failure), differing ONLY in which settings attr holds the target base URL.
This is the single implementation; each service keeps a thin shim wiring its base_url +
token (mirrors the `loreweave_grants` shim pattern).

Best-effort by design: returns `None` on missing source/ref, non-200, or transport/decode
error. A null model NAME is tolerated end-to-end (the Jobs GUI renders null-safe; the
projection COALESCE merge never wipes a previously-set value). Resolve OUTSIDE a job-create
DB transaction (network I/O — never hold a tx across it; H1).
"""
from __future__ import annotations

import logging

import httpx

from ._transport import HEADER_INTERNAL_TOKEN, build_timeout

log = logging.getLogger(__name__)


async def resolve_model_name(
    base_url: str,
    model_source: str | None,
    model_ref: str | None,
    *,
    internal_token: str,
    timeout_s: float = 5.0,
) -> str | None:
    """GET {base_url}/internal/models/{source}/{ref}/info → provider_model_name.

    Returns `None` on missing source/ref, non-200, or transport/decode failure — never
    raises (best-effort; the caller tolerates a null name).
    """
    if not model_source or not model_ref:
        return None
    url = f"{base_url.rstrip('/')}/internal/models/{model_source}/{model_ref}/info"
    try:
        async with httpx.AsyncClient(timeout=build_timeout(timeout_s)) as client:
            resp = await client.get(url, headers={HEADER_INTERNAL_TOKEN: internal_token})
        if resp.status_code != 200:
            log.debug("model-info %d for %s", resp.status_code, model_ref)
            return None
        name = (resp.json().get("provider_model_name") or "").strip()
        return name or None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("model-info resolve failed for %s: %s", model_ref, exc)
        return None
